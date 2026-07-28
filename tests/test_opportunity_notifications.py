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
        "records_collected": 489,
        "unique_posts": 435,
        "new_since_yesterday": 431,
        "actual_apify_cost_usd": 0.29055,
        "candidates": [
            {
                "candidate_key": "relay app migration",
                "opportunity": (
                    "Relay.app migration service for small automation teams"
                ),
                "problem": (
                    "Paying Relay.app customers must move their automations "
                    "before the shutdown deadline."
                ),
                "existing_alternatives": [
                    "Make offers eligible customers free white-glove migration",
                    "Zapier offers AI-assisted rebuilding",
                ],
                "decision_reason": (
                    "The demand is real, but free migration support closes the "
                    "profitable wedge."
                ),
                "decision": "REJECT",
                "classification": "REJECT",
                "research_status": "COMPLETE",
                "independent_authors": 46,
                "payment_or_usage_signals": 15,
                "malaysia_evidence_records": 27,
                "rationale": "Migration demand exists, but the wedge is closed.",
                "sources": [
                    {
                        "label": "Open source",
                        "url": (
                            "https://www.reddit.com/r/AISEOInsider/comments/"
                            "1v8di0g/i_tested_claude_opus_5_vs_fable_5_side_by_side/"
                            "?utm_source=email"
                        ),
                    },
                    {
                        "label": "Open source",
                        "url": (
                            "https://www.reddit.com/r/AISEOInsider/comments/"
                            "1v8di0g/i_tested_claude_opus_5_vs_fable_5_side_by_side"
                        ),
                    },
                ],
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
    payload = requests[0]["json"]
    assert payload["subject"] == "[CariLead] NO BUILD - Global to Malaysia"
    assert payload["text"].startswith(
        "Completed. CEO decision: NO BUILD today."
    )
    assert (
        "1. Relay.app migration service for small automation teams"
        in payload["text"]
    )
    assert "Problem: Paying Relay.app customers" in payload["text"]
    assert "Existing alternatives: Make offers" in payload["text"]
    assert "Decision: REJECT" in payload["text"]
    assert "Records collected: 489." in payload["text"]
    assert "Unique posts: 435." in payload["text"]
    assert "New versus yesterday: 431." in payload["text"]
    assert "Actual Apify cost: $0.29055." in payload["text"]
    assert "Open source" not in payload["text"]
    assert (
        "Reddit: I tested claude opus 5 vs fable 5 side by side"
        in payload["text"]
    )
    assert payload["html"].count(
        "https://www.reddit.com/r/AISEOInsider/comments/"
        "1v8di0g/i_tested_claude_opus_5_vs_fable_5_side_by_side"
    ) == 1
    assert "Therefore: no landing page, MVP, or marketing." in payload["text"]


def test_rejects_abstract_cluster_instead_of_presenting_it_as_an_opportunity(
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

    result = {
        "research_status": "COMPLETE",
        "generated_at": "2026-07-28T08:00:00+00:00",
        "candidates": [
            {
                "candidate_key": "tasks remain unnecessarily difficult",
                "classification": "MALAYSIA_FIRST",
                "research_status": "COMPLETE",
                "independent_authors": 46,
                "payment_or_usage_signals": 15,
                "malaysia_evidence_records": 27,
                "rationale": "Repeated demand in Malaysia",
                "links": ["https://example.com/source"],
            }
        ],
    }

    notify_opportunity_candidates(
        result,
        state_path=tmp_path / "state.json",
        post=fake_post,
    )

    text = requests[0]["json"]["text"]
    assert text.startswith("Completed. CEO decision: NO BUILD today.")
    assert "No concrete opportunity identified from this cluster" in text
    assert "not one specific customer problem" in text
    assert "Decision: REJECT" in text
    assert "what to build, who would buy it, or why they would pay" in text
