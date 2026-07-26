from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

import src.providers.apify_client as apify_module
from src.lovable_blockers import (
    run_lovable_blockers,
    score_blocker_final,
    score_blocker_prefilter,
)
from src.malaysia_opportunities import run_global_to_malaysia
from src.providers.apify_client import (
    ApifyClient,
    ApifyCostLimitError,
    ApifyRunFailed,
    ApifyTimeoutError,
    normalize_apify_item,
)
from src.providers.apify_registry import ApifyActorRegistry
from src.research_storage import ResearchStorage


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class FakeHttp:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError(f"unexpected request: {method} {url}")
        return self.responses.pop(0)


def _item(
    source_id: str = "post-1",
    *,
    published_at: datetime | None = None,
    text: str = "Production deploy is blocked for my customer launch",
) -> dict[str, Any]:
    return {
        "id": source_id,
        "url": f"https://example.test/{source_id}",
        "title": "Deployment blocked",
        "body": text,
        "author": "public-user",
        "createdAt": (published_at or datetime.now(timezone.utc)).isoformat(),
        "num_comments": 2,
    }


def _schema() -> dict[str, Any]:
    return {
        "required_fields": ["source_id", "canonical_url", "text", "published_at"],
        "field_map": {
            "source_id": "id",
            "canonical_url": "url",
            "text": "body",
            "published_at": "createdAt",
        },
    }


def _client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    responses: list[FakeResponse],
) -> tuple[ApifyClient, FakeHttp]:
    monkeypatch.setenv("APIFY_API_TOKEN", "fake-test-token")
    fake = FakeHttp(responses)
    return (
        ApifyClient(
            http_client=fake,
            sleeper=lambda _: None,
            poll_interval_seconds=0.1,
            raw_root=tmp_path / "raw",
        ),
        fake,
    )


def _responses(status: str = "SUCCEEDED", items: list[dict[str, Any]] | None = None) -> list[FakeResponse]:
    return [
        FakeResponse(201, {"data": {"id": "run-1", "defaultDatasetId": "dataset-1"}}),
        FakeResponse(
            200,
            {
                "data": {
                    "id": "run-1",
                    "status": status,
                    "defaultDatasetId": "dataset-1",
                    "usageTotalUsd": 0.0123,
                }
            },
        ),
        FakeResponse(200, items if items is not None else [_item()]),
    ]


def test_apify_successful_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(tmp_path, monkeypatch, _responses())
    result = client.collect(
        source="reddit",
        actor_id="developer~reddit",
        actor_input={"startUrls": ["https://reddit.com/r/lovable/new"]},
        actor_schema=_schema(),
        maximum_records=3,
        timeout_seconds=10,
    )

    assert result.status == "SUCCEEDED"
    assert len(result.normalized_records) == 1
    assert result.normalized_records[0].timestamp_verified is True
    assert result.request_cost_metadata["actual_cost_usd"] == pytest.approx(0.0123)
    assert Path(result.raw_json_path or "").exists()
    assert fake.requests[0]["headers"]["Authorization"] == "Bearer fake-test-token"
    assert fake.requests[0]["params"] is None


def test_actor_failure_without_dataset_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(201, {"data": {"id": "run-failed"}}),
        FakeResponse(200, {"data": {"id": "run-failed", "status": "FAILED"}}),
    ]
    client, _ = _client(tmp_path, monkeypatch, responses)
    with pytest.raises(ApifyRunFailed):
        client.collect(
            source="reddit", actor_id="actor", actor_input={},
            actor_schema=_schema(), maximum_records=3, timeout_seconds=10,
        )


def test_actor_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(
        tmp_path,
        monkeypatch,
        [FakeResponse(200, {"data": {"id": "run-1", "status": "RUNNING"}})],
    )
    moments = iter([0.0, 2.0])
    monkeypatch.setattr(apify_module.time, "monotonic", lambda: next(moments))
    with pytest.raises(ApifyTimeoutError):
        client.wait_for_completion("run-1", timeout_seconds=1)


def test_partial_dataset_is_retained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, _responses("FAILED", [_item()]))
    result = client.collect(
        source="reddit", actor_id="actor", actor_input={},
        actor_schema=_schema(), maximum_records=3, timeout_seconds=10,
    )
    assert result.partial is True
    assert len(result.normalized_records) == 1
    assert "retained partial dataset" in result.warnings[0]


def test_schema_change_is_flagged() -> None:
    record = normalize_apify_item(
        source="reddit",
        item={"unexpected": "shape"},
        actor_id="actor",
        actor_run_id="run",
        raw_json_path="raw.json",
        schema=_schema(),
    )
    assert any("schema missing required field" in warning for warning in record.extraction_warnings)
    assert record.extraction_confidence < 1.0


def test_missing_timestamp_is_unverified() -> None:
    item = _item()
    item.pop("createdAt")
    record = normalize_apify_item(
        source="reddit", item=item, actor_id="actor", actor_run_id="run",
        raw_json_path="raw.json", schema=_schema(),
    )
    assert record.published_at is None
    assert record.timestamp_verified is False


def test_numeric_string_reddit_timestamp_is_verified() -> None:
    item = _item()
    item["createdAt"] = str(datetime.now(timezone.utc).timestamp())
    record = normalize_apify_item(
        source="reddit", item=item, actor_id="actor", actor_run_id="run",
        raw_json_path="raw.json", schema=_schema(),
    )
    assert record.published_at is not None
    assert record.timestamp_verified is True


def test_actor_item_query_overrides_batch_fallback() -> None:
    item = _item()
    item["query"] = "specific source query"
    schema = _schema()
    schema["field_map"]["query"] = "query"
    record = normalize_apify_item(
        source="reddit", item=item, actor_id="actor", actor_run_id="run",
        raw_json_path="raw.json", schema=schema, query="combined fallback",
    )
    assert record.query == "specific source query"


def test_stale_reddit_record_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _approved_registry(tmp_path, monkeypatch)
    old = datetime.now(timezone.utc) - timedelta(days=2)
    client, _ = _client(tmp_path, monkeypatch, _responses(items=[_item(published_at=old)]))
    result = run_lovable_blockers(
        registry, client, output_dir=tmp_path / "reports", recent_hours=24,
    )
    assert result["stale_records"] == 1
    assert result["verified_recent_posts"] == 0
    assert result["qualifying_blockers"] == []


def test_lovable_tutorial_is_not_a_rescue_lead() -> None:
    item = _item(
        text=(
            "My users asked for API and CLI access. After adding developer "
            "access, I raised my lifetime deal from $35 to $49."
        )
    )
    item["title"] = "Lovable builders might be focusing on the wrong features"
    record = normalize_apify_item(
        source="reddit", item=item, actor_id="actor", actor_run_id="run",
        raw_json_path="raw.json", schema=_schema(),
    )
    prefilter = score_blocker_prefilter(record)
    final = score_blocker_final(record, prefilter, [])
    assert prefilter["rescue_intent"] is False
    assert prefilter["score"] == 0
    assert final["independent_developer_solvable"] is False


def test_explicit_production_failure_can_qualify_as_rescue() -> None:
    record = normalize_apify_item(
        source="reddit", item=_item(), actor_id="actor", actor_run_id="run",
        raw_json_path="raw.json", schema=_schema(),
    )
    prefilter = score_blocker_prefilter(record)
    final = score_blocker_final(record, prefilter, [])
    assert prefilter["rescue_intent"] is True
    assert prefilter["score"] >= 4
    assert final["score"] >= 6
    assert final["independent_developer_solvable"] is True


def test_collection_deduplicates_source_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(tmp_path, monkeypatch, _responses(items=[_item(), _item()]))
    result = client.collect(
        source="reddit", actor_id="actor", actor_input={},
        actor_schema=_schema(), maximum_records=3, timeout_seconds=10,
    )
    assert len(result.items) == 2
    assert len(result.normalized_records) == 1


def test_token_is_redacted_from_raw_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _item()
    item["cookie"] = "fake-test-token"
    item["body"] = "safe fake-test-token should also be redacted"
    client, _ = _client(tmp_path, monkeypatch, _responses(items=[item]))
    result = client.collect(
        source="reddit", actor_id="actor", actor_input={},
        actor_schema=_schema(), maximum_records=3, timeout_seconds=10,
    )
    raw = Path(result.raw_json_path or "").read_text(encoding="utf-8")
    assert "fake-test-token" not in raw
    assert "[REDACTED]" in raw


def test_cost_limit_stops_before_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake = _client(tmp_path, monkeypatch, [])
    with pytest.raises(ApifyCostLimitError):
        client.start_actor("actor", {}, estimated_cost_usd=0.20, max_cost_usd=0.10)
    assert fake.requests == []


def test_cost_limit_is_forwarded_to_apify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake = _client(
        tmp_path,
        monkeypatch,
        [FakeResponse(201, {"data": {"id": "run-1"}})],
    )
    client.start_actor("actor", {}, estimated_cost_usd=0.05, max_cost_usd=0.10)
    assert fake.requests[0]["params"] == {"maxTotalChargeUsd": 0.10}


def test_opportunity_is_not_researched_until_reddit_is_approved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "actors.yaml"
    config.write_text(
        "defaults: {}\nsources:\n  reddit:\n    actor_id_env: APIFY_REDDIT_ACTOR_ID\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APIFY_REDDIT_ACTOR_ID", raising=False)
    registry = ApifyActorRegistry(
        config, storage=ResearchStorage(db_path=tmp_path / "research.sqlite3"),
    )
    result = run_global_to_malaysia(
        registry, ApifyClient(raw_root=tmp_path / "raw"), output_dir=tmp_path / "reports",
    )
    assert result["research_status"] == "NOT_RESEARCHED"
    assert "blocked until Reddit Actor passes" in result["reason"]


def test_actor_registry_falls_back_to_direct_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Direct:
        def health_check(self) -> dict[str, str]:
            return {"status": "available"}

    config = tmp_path / "actors.yaml"
    config.write_text(
        "defaults: {}\nsources:\n  reddit:\n    actor_id_env: APIFY_REDDIT_ACTOR_ID\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APIFY_REDDIT_ACTOR_ID", raising=False)
    registry = ApifyActorRegistry(
        config,
        storage=ResearchStorage(db_path=tmp_path / "research.sqlite3"),
        direct_registry={"reddit": Direct()},
    )
    selected = registry.select("reddit")
    assert selected.provider == "direct"
    assert "Apify unavailable" in selected.reason


def _approved_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ApifyActorRegistry:
    config = tmp_path / "actors.yaml"
    config.write_text(
        """
defaults:
  blocker_timeout_seconds: 10
  max_actor_run_cost_usd: 1.0
sources:
  reddit:
    actor_id_env: APIFY_REDDIT_ACTOR_ID
    actor_name: Test Reddit Actor
    developer: test-developer
    expected_input_schema:
      type: object
    expected_output_schema:
      required_fields: [source_id, canonical_url, text, published_at]
      field_map:
        source_id: id
        canonical_url: url
        text: body
        published_at: createdAt
    timestamp_field: createdAt
    cost_estimate_usd: 0.01
    approval_status: unconfigured
    input_templates:
      test:
        maximumRecords: "{{maximum_records}}"
      blockers:
        subreddit: lovable
        maximumRecords: "{{maximum_records}}"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APIFY_REDDIT_ACTOR_ID", "test-developer~reddit")
    registry = ApifyActorRegistry(
        config, storage=ResearchStorage(db_path=tmp_path / "research.sqlite3"),
    )
    registry.save_test(
        source="reddit",
        actor_id="test-developer~reddit",
        status="passed",
        records_fetched=1,
        newest_verified_timestamp=datetime.now(timezone.utc),
        cost_usd=0.01,
        schema_warnings=[],
        actor_run_id="approval-run",
    )
    return registry
