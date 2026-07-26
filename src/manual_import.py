from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .research_models import SourceRecord
from .research_storage import ResearchStorage
from .sources.app_store import AppStoreAdapter
from .sources.google_play import GooglePlayAdapter
from .sources.google_trends import GoogleTrendsAdapter


SOURCE_ALIASES = {
    "app_store": AppStoreAdapter,
    "google_play": GooglePlayAdapter,
    "google_trends": GoogleTrendsAdapter,
}

REQUIRED = {
    "app_store": ({"id", "review_id"}, {"body", "review", "content"}),
    "google_play": ({"reviewId", "review_id", "id"}, {"content", "review", "body"}),
    "google_trends": ({"date", "observed_at"}, {"value", "interest"}),
    "product_hunt": ({"id", "source_id"}, {"name", "title"}),
    "tiktok": ({"id", "source_id"}, {"comment", "body", "text"}),
    "x": ({"id", "source_id"}, {"text", "body"}),
}


def import_records(source: str, path: Path, storage: ResearchStorage, run_id: int) -> dict[str, int]:
    if source not in REQUIRED:
        raise ValueError(f"unsupported import source: {source}")
    rows = _read(path)
    valid = rejected = 0
    for index, raw in enumerate(rows, 1):
        if not isinstance(raw, dict) or not _valid_keys(raw, REQUIRED[source]):
            rejected += 1
            continue
        try:
            record = _normalize(source, raw, index)
            valid += int(storage.save_record(record, run_id))
        except (ValidationError, ValueError, TypeError):
            rejected += 1
    if rejected:
        rejection_path = path.with_suffix(path.suffix + ".rejected.json")
        rejection_path.write_text(json.dumps({"rejected_count": rejected}, indent=2), encoding="utf-8")
    return {"rows": len(rows), "imported": valid, "rejected": rejected}


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("records") or payload.get("reviews") or payload.get("data")
        if not isinstance(payload, list):
            raise ValueError("JSON import must contain a list or records/reviews/data list")
        return payload
    raise ValueError("only CSV and JSON imports are supported")


def _valid_keys(raw, groups) -> bool:
    return all(any(key in raw and raw[key] not in (None, "") for key in group) for group in groups)


def _normalize(source: str, raw: dict[str, Any], index: int) -> SourceRecord:
    if source == "app_store":
        mapped = {
            "id": {"label": raw.get("id") or raw.get("review_id")},
            "title": {"label": raw.get("title") or ""},
            "content": {"label": raw.get("body") or raw.get("review") or raw.get("content")},
            "author": {"name": {"label": raw.get("author") or raw.get("user")}},
            "updated": {"label": raw.get("date") or raw.get("updated")},
            "im:rating": {"label": raw.get("rating") or raw.get("score")},
        }
        return AppStoreAdapter().normalize(mapped, app_id=raw.get("app_id"), app_name=raw.get("app_name"))
    if source == "google_play":
        mapped = dict(raw)
        mapped["reviewId"] = raw.get("reviewId") or raw.get("review_id") or raw.get("id")
        mapped["content"] = raw.get("content") or raw.get("review") or raw.get("body")
        mapped["score"] = raw.get("score") or raw.get("rating")
        return GooglePlayAdapter().normalize(mapped, app_id=raw.get("app_id") or raw.get("appId"))
    if source == "google_trends":
        return GoogleTrendsAdapter().normalize({
            "query": raw.get("query") or raw.get("term") or "manual_import",
            "date": raw.get("date") or raw.get("observed_at"),
            "value": raw.get("value") or raw.get("interest"),
        })
    source_id = str(raw.get("id") or raw.get("source_id"))
    text = raw.get("text") or raw.get("body") or raw.get("comment") or raw.get("description")
    if source == "product_hunt":
        return SourceRecord(
            source=source, source_type="product", source_id=source_id,
            canonical_url=raw.get("url") or raw.get("source_url") or "",
            title=raw.get("name") or raw.get("title"), body=text,
            author_public_name=raw.get("author") or raw.get("maker"),
            published_at=raw.get("published_at") or raw.get("date"),
            language=raw.get("language") or "en",
            product_name=raw.get("name") or raw.get("title"),
            query="manual_import",
            extraction_warnings=["manual Product Hunt import; provenance must be reviewed"],
            extraction_confidence=0.7, raw_payload=raw,
        )
    return SourceRecord(
        source=source, source_type="comment" if source in {"tiktok", "x"} else "post",
        source_id=source_id, canonical_url=raw.get("url") or raw.get("source_url") or "",
        title=raw.get("title") or raw.get("name"), body=text,
        author_public_name=raw.get("author"), published_at=raw.get("published_at") or raw.get("date"),
        language=raw.get("language") or "en", query="manual_import",
        extraction_warnings=["manual import; provenance must be reviewed"],
        extraction_confidence=0.7, raw_payload=raw,
    )
