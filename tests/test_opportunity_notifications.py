from __future__ import annotations

from pathlib import Path
from typing import Any

from src.opportunity_notifications import notify_opportunity_candidates


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id": "email-123"}


def _best_bet_result() -> dict[str, Any]:
    return {
        "workflow": "global_opportunity_dig",
        "research_status": "COMPLETE",
        "generated_at": "2026-07-28T08:00:00+00:00",
        "records_collected": 489,
        "unique_posts": 435,
        "new_since_yesterday": 431,
        "actual_apify_cost_usd": 0.29055,
        "ceo_decision": "VALIDATE NOW",
        "candidates": [
            {
                "opportunity": (
                    "Returns-cost recovery audit for small Shopify brands"
                ),
                "problem": (
                    "Small brands lose margin to preventable returns but lack "
                    "the staff to analyze product and reason-level patterns."
                ),
                "offer": (
                    "A RM750 fixed-fee audit that identifies the three highest-"
                    "value return causes and supplies copy or sizing fixes."
                ),
                "why_pay": (
                    "Recovering only a handful of avoidable returns repays the fee."
                ),
                "existing_alternatives": [
                    "Loop Returns",
                    "AfterShip Returns",
                    "manual spreadsheet analysis",
                ],
                "wedge": (
                    "Sell an outcome-focused audit to stores too small for a "
                    "dedicated operations analyst."
                ),
                "decision_reason": (
                    "The service can be sold before software is built and produces "
                    "a measurable margin result."
                ),
                "decision": "VALIDATE NOW",
                "confidence": "PROMISING",
                "validation_test": (
                    "Contact 20 Shopify brands and sell one RM750 audit within 48 hours."
                ),
                "kill_criterion": (
                    "Stop if no owner shares return data or pays a deposit after 20 pitches."
                ),
                "evidence_summary": (
                    "Merchants repeatedly describe return handling as a margin and "
                    "manual-analysis problem."
                ),
                "sources": [
                    {
                        "label": "Open source",
                        "url": "https://example.com/shopify-return-costs?utm_source=email",
                    },
                    {
                        "label": "Open source",
                        "url": "https://example.com/shopify-return-costs",
                    },
                ],
            }
        ],
    }


def _configure_email(monkeypatch: Any) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("RESEND_ALERT_TO_EMAIL", "owner@example.com")


def test_failed_collection_sends_every_run_without_market_decision(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _configure_email(monkeypatch)
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    result = {
        "workflow": "global_to_malaysia_opportunity_dig",
        "research_status": "NOT_RESEARCHED",
        "collection_error": "Provider usage limit reached",
        "records_collected": 0,
        "candidates": [],
    }
    first = notify_opportunity_candidates(
        result, state_path=tmp_path / "state.json", post=fake_post
    )
    second = notify_opportunity_candidates(
        result, state_path=tmp_path / "state.json", post=fake_post
    )

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert len(requests) == 2
    payload = requests[0]["json"]
    assert payload["subject"] == (
        "[CariLead] RESEARCH RUN FAILED - Global to Malaysia"
    )
    assert payload["text"].startswith(
        "Research run failed. No CEO market decision was made"
    )
    assert "CEO move: NOT AVAILABLE." in payload["text"]


def test_sends_actionable_best_bet_on_every_run(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _configure_email(monkeypatch)
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    state_path = tmp_path / "state.json"
    first = notify_opportunity_candidates(
        _best_bet_result(), state_path=state_path, post=fake_post
    )
    second = notify_opportunity_candidates(
        _best_bet_result(), state_path=state_path, post=fake_post
    )

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert len(requests) == 2
    payload = requests[0]["json"]
    assert payload["to"] == ["owner@example.com"]
    assert payload["subject"] == (
        "[CariLead] TODAY'S BEST BET - Returns-cost recovery audit "
        "for small Shopify brands"
    )
    assert payload["text"].startswith(
        "Hey Kenny — today's best bet is: Returns-cost recovery audit"
    )
    assert "CEO move: VALIDATE NOW." in payload["text"]
    assert "CEO decision: VALIDATE NOW" in payload["text"]
    assert "What to sell now: A RM750 fixed-fee audit" in payload["text"]
    assert "Why they pay: Recovering only a handful" in payload["text"]
    assert "Our wedge: Sell an outcome-focused audit" in payload["text"]
    assert "48-hour move: Contact 20 Shopify brands" in payload["text"]
    assert "Kill criterion: Stop if no owner" in payload["text"]
    assert "Records collected: 489." in payload["text"]
    assert "Actual Apify cost: $0.29055." in payload["text"]
    assert "Open source" not in payload["text"]
    assert payload["html"].count(
        "https://example.com/shopify-return-costs"
    ) == 1


def test_abstract_legacy_cluster_is_not_presented_as_a_business(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _configure_email(monkeypatch)
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    result = {
        "workflow": "global_to_malaysia_opportunity_dig",
        "research_status": "COMPLETE",
        "generated_at": "2026-07-28T08:00:00+00:00",
        "candidates": [
            {
                "candidate_key": "tasks remain unnecessarily difficult",
                "classification": "MALAYSIA_FIRST",
                "independent_authors": 46,
                "rationale": "Repeated demand in Malaysia",
                "links": ["https://example.com/source"],
            }
        ],
    }

    notify_opportunity_candidates(
        result, state_path=tmp_path / "state.json", post=fake_post
    )

    text = requests[0]["json"]["text"]
    assert text.startswith("Hey Kenny — no concrete bet survived")
    assert "tasks remain unnecessarily difficult" not in text
    assert "cluster" not in text.lower()
