from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.rednote_opportunities import (
    _text_report,
    analyze_rednote_capture,
    run_rednote_opportunity_dig,
    send_rednote_report,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"id": "rednote-email-123"}


def _capture() -> dict[str, Any]:
    return {
        "generated_at": "2026-07-28T10:00:00+08:00",
        "queries": {
            "马来西亚 求推荐": [
                {
                    "title": "马来西亚兼职哪里找？差点被骗",
                    "url": "https://www.rednote.com/search_result/post-1?utm_source=a",
                    "author": "user-1",
                    "engagement": "125",
                    "body": "学生需要可靠的part time平台，预算RM20。",
                },
                {
                    "title": "马来西亚兼职哪里找？差点被骗",
                    "url": "https://www.rednote.com/search_result/post-1?utm_source=b",
                    "author": "user-1",
                    "engagement": "125",
                    "body": "duplicate",
                },
                {
                    "title": "大马留学生需要兼职app推荐",
                    "url": "https://www.rednote.com/search_result/post-2",
                    "author": "user-2",
                    "engagement": "40",
                    "body": "现有平台不好用，想要安全的兼职app。",
                },
            ]
        },
    }


def test_analyzes_and_deduplicates_browser_capture(tmp_path: Path) -> None:
    report = analyze_rednote_capture(
        _capture(), state_path=tmp_path / "seen.json"
    )

    assert report["records_collected"] == 3
    assert report["unique_posts"] == 2
    assert report["new_since_previous_run"] == 2
    assert report["ceo_decision"] == "VALIDATE NOW"
    assert report["best_bet"]["opportunity"] == (
        "Verified part-time work marketplace for Malaysia"
    )
    assert report["candidates"][0]["opportunity"] == (
        "Verified part-time work marketplace for Malaysia"
    )
    text = _text_report(report)
    assert text.startswith(
        "Hey Kenny — today's best bet is: "
        "Verified part-time work marketplace for Malaysia"
    )
    assert "What to sell now:" in text
    assert "Why they pay:" in text
    assert "48-hour move:" in text
    assert "Kill criterion:" in text
    assert "JobStreet, Hiredly, Indeed, Maukerja" in text
    assert text.rstrip().splitlines()[-1].startswith("Next action:")


def test_failed_collection_emails_failure_not_market_decision(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("RESEND_ALERT_TO_EMAIL", "owner@example.com")
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    report = {
        "ceo_decision": "NOT AVAILABLE",
        "records_collected": 0,
        "unique_posts": 0,
        "new_since_previous_run": 0,
        "collection_error": "RedNote login unavailable",
        "candidates": [],
        "next_action": "Next action: restore the browser connection and rerun.",
    }
    first = send_rednote_report(report, post=fake_post)
    second = send_rednote_report(report, post=fake_post)

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert len(requests) == 2
    payload = requests[0]["json"]
    assert payload["subject"] == (
        "[CariLead RedNote] RESEARCH RUN FAILED - Malaysia"
    )
    assert payload["text"].startswith(
        "Research run failed. CEO decision: NOT AVAILABLE."
    )
    assert "No market conclusion was made" in payload["text"]


def test_command_workflow_writes_reports_and_sends_email(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("RESEND_ALERT_TO_EMAIL", "owner@example.com")
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(
        json.dumps(_capture(), ensure_ascii=False), encoding="utf-8"
    )
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        return FakeResponse()

    result = run_rednote_opportunity_dig(
        capture_path,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "seen.json",
        post=fake_post,
    )

    assert result["notification"]["email_id"] == "rednote-email-123"
    assert (tmp_path / "reports" / "rednote_malaysia_latest.json").exists()
    assert (tmp_path / "reports" / "rednote_malaysia_latest.md").exists()
