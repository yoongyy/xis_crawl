from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
FAILED_STATUSES = {"FAILED", "TIMED-OUT", "ABORTED"}
SENSITIVE_KEYS = {"token", "authorization", "cookie", "api_token", "apiToken"}


class ApifyError(RuntimeError):
    pass


class ApifyConfigurationError(ApifyError):
    pass


class ApifyTimeoutError(ApifyError):
    pass


class ApifyRunFailed(ApifyError):
    pass


class ApifyCostLimitError(ApifyError):
    pass


class ApifySchemaError(ApifyError):
    pass


class ApifyNormalizedRecord(BaseModel):
    source: str
    source_type: str
    source_id: str
    canonical_url: str
    title: str | None = None
    text: str
    author_public_name: str | None = None
    author_hash: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    country: str | None = None
    language: str = "unknown"
    engagement: float | dict[str, Any] | None = None
    rating: float | None = None
    comment_count: int | None = None
    query: str | None = None
    provider: str = "apify"
    actor_id: str
    actor_run_id: str
    raw_json_path: str
    timestamp_verified: bool = False
    extraction_confidence: float = 0.5
    extraction_warnings: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)


class ApifyRunResult(BaseModel):
    source: str
    actor_id: str
    actor_run_id: str
    status: str
    dataset_id: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    normalized_records: list[ApifyNormalizedRecord] = Field(default_factory=list)
    partial: bool = False
    warnings: list[str] = Field(default_factory=list)
    raw_json_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    request_cost_metadata: dict[str, Any] = Field(default_factory=dict)


class ApifyClient:
    base_url = "https://api.apify.com/v2"

    def __init__(
        self,
        *,
        http_client: httpx.Client | Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        poll_interval_seconds: float = 2.0,
        max_retries: int = 3,
        raw_root: Path = Path("data/raw/apify"),
    ) -> None:
        load_dotenv()
        self._token = os.getenv("APIFY_API_TOKEN")
        self.http = http_client or httpx.Client(timeout=30.0)
        self.sleeper = sleeper
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.max_retries = max(0, max_retries)
        self.raw_root = raw_root

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def start_actor(
        self,
        actor_id: str,
        actor_input: dict[str, Any],
        *,
        estimated_cost_usd: float | None = None,
        max_cost_usd: float | None = None,
    ) -> dict[str, Any]:
        self._require_token()
        if (
            max_cost_usd is not None
            and estimated_cost_usd is not None
            and estimated_cost_usd > max_cost_usd
        ):
            raise ApifyCostLimitError(
                f"estimated Actor cost ${estimated_cost_usd:.4f} exceeds limit ${max_cost_usd:.4f}"
            )
        actor_path = quote(actor_id, safe="~")
        params = {"maxTotalChargeUsd": max_cost_usd} if max_cost_usd is not None else None
        payload = self._request(
            "POST", f"/acts/{actor_path}/runs",
            json=actor_input,
            params=params,
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            raise ApifySchemaError("Actor start response is missing data.id")
        return data

    def wait_for_completion(self, actor_run_id: str, *, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + max(1, timeout_seconds)
        while True:
            data = self._run_status(actor_run_id)
            status = str(data.get("status") or "").upper()
            if status in TERMINAL_STATUSES:
                return data
            if time.monotonic() >= deadline:
                raise ApifyTimeoutError(
                    f"Actor run {actor_run_id} did not finish within {timeout_seconds} seconds"
                )
            self.sleeper(min(self.poll_interval_seconds, max(0.1, deadline - time.monotonic())))

    def retrieve_dataset_items(
        self, dataset_id: str, *, maximum_records: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        limit = min(1000, max(1, maximum_records))
        while len(items) < maximum_records:
            page_limit = min(limit, maximum_records - len(items))
            page = self._request(
                "GET", f"/datasets/{quote(dataset_id, safe='')}/items",
                params={
                    "clean": "true", "format": "json",
                    "offset": offset, "limit": page_limit,
                },
                expect_envelope=False,
            )
            if not isinstance(page, list):
                raise ApifySchemaError("dataset endpoint did not return a JSON list")
            valid_page = [row for row in page if isinstance(row, dict)]
            items.extend(valid_page)
            if len(page) < page_limit:
                break
            offset += len(page)
            if not page:
                break
        return items[:maximum_records]

    def collect(
        self,
        *,
        source: str,
        actor_id: str,
        actor_input: dict[str, Any],
        actor_schema: dict[str, Any],
        maximum_records: int,
        timeout_seconds: int,
        estimated_cost_usd: float | None = None,
        max_cost_usd: float | None = None,
        seen_source_ids: set[str] | None = None,
        incremental_after: datetime | None = None,
        query: str | None = None,
    ) -> ApifyRunResult:
        started = self.start_actor(
            actor_id, actor_input,
            estimated_cost_usd=estimated_cost_usd,
            max_cost_usd=max_cost_usd,
        )
        run_id = str(started["id"])
        terminal = self.wait_for_completion(run_id, timeout_seconds=timeout_seconds)
        status = str(terminal.get("status") or "UNKNOWN").upper()
        dataset_id = terminal.get("defaultDatasetId") or started.get("defaultDatasetId")
        items: list[dict[str, Any]] = []
        warnings: list[str] = []
        if dataset_id:
            items = self.retrieve_dataset_items(
                str(dataset_id), maximum_records=maximum_records,
            )
        if status in FAILED_STATUSES:
            if not items:
                raise ApifyRunFailed(f"Actor run {run_id} finished with status {status}")
            warnings.append(f"Actor finished with {status}; retained partial dataset")
        raw_path = self._store_raw(source, run_id, actor_id, terminal, items)
        normalized: list[ApifyNormalizedRecord] = []
        seen = set(seen_source_ids or set())
        for item in items:
            record = normalize_apify_item(
                source=source,
                item=item,
                actor_id=actor_id,
                actor_run_id=run_id,
                raw_json_path=str(raw_path),
                schema=actor_schema,
                query=query,
            )
            if record.source_id in seen:
                continue
            if incremental_after and record.published_at and record.published_at <= incremental_after:
                continue
            seen.add(record.source_id)
            normalized.append(record)
        actual_cost = _extract_cost(terminal)
        if max_cost_usd is not None and actual_cost is not None and actual_cost > max_cost_usd:
            warnings.append(
                f"actual Actor cost ${actual_cost:.4f} exceeded configured limit ${max_cost_usd:.4f}"
            )
        return ApifyRunResult(
            source=source,
            actor_id=actor_id,
            actor_run_id=run_id,
            status=status,
            dataset_id=str(dataset_id) if dataset_id else None,
            items=items,
            normalized_records=normalized,
            partial=status in FAILED_STATUSES,
            warnings=warnings,
            raw_json_path=str(raw_path),
            started_at=_parse_datetime(terminal.get("startedAt") or started.get("startedAt"))[0],
            finished_at=_parse_datetime(terminal.get("finishedAt"))[0],
            request_cost_metadata={
                "estimated_cost_usd": estimated_cost_usd,
                "actual_cost_usd": actual_cost,
                "maximum_cost_usd": max_cost_usd,
                "records_requested": maximum_records,
                "records_returned": len(items),
            },
        )

    def _run_status(self, actor_run_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET", f"/actor-runs/{quote(actor_run_id, safe='')}",
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ApifySchemaError("Actor run response is missing data")
        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        expect_envelope: bool = True,
        **kwargs: Any,
    ) -> Any:
        self._require_token()
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token}"
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries + 1):
            try:
                response = self.http.request(method, url, headers=headers, **kwargs)
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise ApifyError(_redact_message(str(exc), self._token)) from exc
                self.sleeper(2 ** attempt)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                self.sleeper(2 ** attempt)
                continue
            if response.status_code >= 400:
                message = _redact_message(response.text[:500], self._token)
                raise ApifyError(f"Apify API returned {response.status_code}: {message}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise ApifySchemaError("Apify API returned invalid JSON") from exc
            if expect_envelope and not isinstance(payload, dict):
                raise ApifySchemaError("Apify API response envelope is not an object")
            return payload
        raise ApifyError("Apify request failed after retries")

    def _store_raw(
        self,
        source: str,
        run_id: str,
        actor_id: str,
        run_data: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> Path:
        path = self.raw_root / source / date.today().isoformat() / f"{_safe(run_id)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": "apify",
            "source": source,
            "actor_id": actor_id,
            "actor_run_id": run_id,
            "run": redact_secrets(run_data, self._token),
            "items": redact_secrets(items, self._token),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def _require_token(self) -> None:
        if not self._token:
            raise ApifyConfigurationError("APIFY_API_TOKEN is not configured")


DEFAULT_FIELD_MAP: dict[str, list[str]] = {
    "source_type": ["source_type", "type", "itemType", "kind"],
    "source_id": ["source_id", "id", "postId", "commentId", "videoId", "reviewId"],
    "canonical_url": ["canonical_url", "url", "postUrl", "videoUrl", "reviewUrl", "link"],
    "title": ["title", "name", "headline"],
    "text": ["text", "body", "content", "description", "selftext", "reviewText"],
    "author_public_name": ["author_public_name", "author", "username", "userName", "channelTitle"],
    "published_at": ["published_at", "created_utc", "createdAt", "publishedAt", "date", "timestamp"],
    "country": ["country", "location", "region"],
    "language": ["language", "lang"],
    "engagement": ["engagement", "score", "likes", "viewCount", "votes"],
    "rating": ["rating", "scoreValue", "stars"],
    "comment_count": ["comment_count", "num_comments", "commentCount", "commentsCount"],
    "query": ["query", "searchTerm", "searchQuery", "inputQuery", "_input"],
}


def normalize_apify_item(
    *,
    source: str,
    item: dict[str, Any],
    actor_id: str,
    actor_run_id: str,
    raw_json_path: str,
    schema: dict[str, Any],
    query: str | None = None,
) -> ApifyNormalizedRecord:
    configured_map = schema.get("field_map") or {}
    field_map = {
        field: _as_list(configured_map.get(field)) or aliases
        for field, aliases in DEFAULT_FIELD_MAP.items()
    }
    values = {
        field: _first(item, aliases)
        for field, aliases in field_map.items()
    }
    warnings: list[str] = []
    required = set(schema.get("required_fields") or ["source_id", "canonical_url", "text", "published_at"])
    missing = sorted(field for field in required if values.get(field) in (None, ""))
    if missing:
        warnings.append(f"schema missing required field(s): {', '.join(missing)}")
    source_id = str(values.get("source_id") or _fallback_id(source, item))
    canonical_url = str(values.get("canonical_url") or "")
    text = str(values.get("text") or "")
    published_at, verified = _parse_datetime(values.get("published_at"))
    if not verified:
        warnings.append("missing or unverifiable absolute timestamp")
    author = _author_name(values.get("author_public_name"))
    author_hash = (
        hashlib.sha256(f"{source}:{author}".encode()).hexdigest()
        if author else None
    )
    confidence = max(0.0, 1.0 - len(warnings) * 0.25)
    return ApifyNormalizedRecord(
        source=source,
        source_type=str(values.get("source_type") or _default_source_type(source, item)),
        source_id=source_id,
        canonical_url=canonical_url,
        title=str(values["title"]) if values.get("title") not in (None, "") else None,
        text=text,
        author_public_name=author,
        author_hash=author_hash,
        published_at=published_at,
        country=str(values["country"]) if values.get("country") not in (None, "") else None,
        language=str(values.get("language") or "unknown"),
        engagement=_number_or_mapping(values.get("engagement")),
        rating=_float_or_none(values.get("rating")),
        comment_count=_int_or_none(values.get("comment_count")),
        query=str(values["query"]) if values.get("query") not in (None, "") else query,
        actor_id=actor_id,
        actor_run_id=actor_run_id,
        raw_json_path=raw_json_path,
        timestamp_verified=verified,
        extraction_confidence=confidence,
        extraction_warnings=warnings,
        raw_payload=item,
    )


def redact_secrets(value: Any, token: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.lower() in {item.lower() for item in SENSITIVE_KEYS}
                else redact_secrets(item, token)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item, token) for item in value]
    if isinstance(value, str):
        return _redact_message(value, token)
    return value


def _redact_message(value: str, token: str | None) -> str:
    return value.replace(token, "[REDACTED]") if token else value


def _first(item: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        current: Any = item
        for part in alias.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return None


def _parse_datetime(value: Any) -> tuple[datetime | None, bool]:
    if value in (None, ""):
        return None, False
    if isinstance(value, datetime):
        return (
            (value if value.tzinfo else value.replace(tzinfo=timezone.utc)),
            value.tzinfo is not None,
        )
    numeric_value: float | None = None
    if isinstance(value, (int, float)):
        numeric_value = float(value)
    elif isinstance(value, str):
        try:
            numeric_value = float(value.strip())
        except ValueError:
            numeric_value = None
    if numeric_value is not None:
        seconds = numeric_value
        if seconds > 10_000_000_000:
            seconds /= 1000
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc), True
        except (ValueError, OSError, OverflowError):
            return None, False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None, False
    return (
        parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc),
        parsed.tzinfo is not None,
    )


def _extract_cost(data: dict[str, Any]) -> float | None:
    for path in (
        ("usageTotalUsd",),
        ("usage", "TOTAL_USD"),
        ("pricingInfo", "totalUsd"),
    ):
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        result = _float_or_none(current)
        if result is not None:
            return result
    return None


def _fallback_id(source: str, item: dict[str, Any]) -> str:
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    return f"generated:{source}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def _default_source_type(source: str, item: dict[str, Any]) -> str:
    if any(key in item for key in ("commentId", "parentCommentId", "replyTo")):
        return "comment"
    if source in {"app_store", "google_play"} and any(key in item for key in ("reviewId", "rating", "stars")):
        return "review"
    if source == "youtube":
        return "video"
    return "post"


def _author_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name") or value.get("username") or value.get("displayName")
    return str(value) if value not in (None, "") else None


def _number_or_mapping(value: Any) -> float | dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return _float_or_none(value)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value] if isinstance(value, list) else []


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)[:160]
