from __future__ import annotations

from pathlib import Path
from typing import Any

from src.opportunity_notifications import notify_opportunity_candidates


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id": "email-123"}


def _result() -> dict[str, Any]:
    return {
        "research_status": "COMPLETE",
        "generated_at": "2026-07-27T08:00:00+00:00",
        "candidates": [
            {
                "candidate_key": "simple invoice app",
                "classification": "MALAYSIA_FIRST",
                "research_status": "COMPLETE",
                "independent_authors": 4,
                "payment_or_usage_signals": 3,
                "malaysia_evidence_records": 5,
                "rationale": "Repeated demand in Malaysia",
                "links": ["https://example.com/source"],
            }
        ],
    }


def test_skips_email_when_there_are_no_candidates(tmp_path: Path) -> None:
    called = False

    def fake_post(*args: Any, **kwargs: Any) -> FakeResponse:
        nonlocal called
        called = True
        return FakeResponse()

    status = notify_opportunity_candidates(
        {"candidates": []},
        state_path=tmp_path / "state.json",
        post=fake_post,
    )
    assert status["status"] == "skipped"
    assert called is False


def test_sends_email_and_suppresses_unchanged_candidates(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("RESEND_ALERT_TO_EMAIL", "owner@example.com")
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    state_path = tmp_path / "state.json"
    first = notify_opportunity_candidates(
        _result(), state_path=state_path, post=fake_post
    )
    second = notify_opportunity_candidates(
        _result(), state_path=state_path, post=fake_post
    )

    assert first == {
        "status": "sent",
        "email_id": "email-123",
        "candidate_count": 1,
    }
    assert second["status"] == "skipped"
    assert second["reason"] == "opportunity candidates are unchanged"
    assert len(requests) == 1
    assert requests[0]["json"]["to"] == ["owner@example.com"]
    assert "simple invoice app" in requests[0]["json"]["html"]
