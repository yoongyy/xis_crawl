from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import httpx

from src.analysis.competitor_analyzer import validate_competitor
from src.analysis.evidence_classifier import RulesEvidenceClassifier
from src.analysis.report_verifier import ReportVerifier
from src.analysis.trend_analyzer import classify_trend
from src.discovery.candidate_ranker import CandidateRanker
from src.discovery.query_planner import QueryPlanner, load_research_pack
from src.manual_import import import_records
from src.reports.demand_report import generate_demand_report
from src.research_models import CompetitorProduct, CrawlOptions, SourceRecord
from src.research_runner import ResearchRunner
from src.research_analysis import analyze_run
from src.research_storage import ResearchStorage
from src.sources.app_store import AppStoreAdapter
from src.sources.google_play import GooglePlayAdapter
from src.sources.google_trends import GoogleTrendsAdapter
from src.sources.hacker_news import HackerNewsAdapter
from src.sources.reddit import RedditAdapter
from src.sources.youtube import YouTubeAdapter
from src.sources.http import ConservativeHttpClient


def record(text: str, **updates) -> SourceRecord:
    data = dict(
        source="reddit", source_type="post", source_id="p1",
        canonical_url="https://reddit.com/r/apps/comments/p1/example",
        body=text, author_public_name="person", published_at=datetime.now(timezone.utc),
        country_signal="US-weak", language="en", thread_id="p1",
    )
    data.update(updates)
    return SourceRecord(**data)


def findings(text: str, **updates):
    source = record(text, **updates)
    verifier = ReportVerifier()
    return [verifier.verify(f, source) for f in RulesEvidenceClassifier().classify(source, "test")]


def temp_storage(tmp_path: Path) -> ResearchStorage:
    return ResearchStorage(tmp_path / "research.sqlite3")


def test_reddit_normalization() -> None:
    raw = {
        "id": "abc", "title": "Need help", "selftext": "I struggle with mornings",
        "author": "u", "created_utc": 1700000000, "permalink": "/r/ADHD/comments/abc/x/",
        "score": 4, "num_comments": 2,
    }
    item = RedditAdapter().normalize(raw, query="morning", search_rank=1)
    assert item.source_id == "abc"
    assert item.canonical_url.startswith("https://www.reddit.com/")
    assert item.thread_id == "abc"


def test_hacker_news_normalization() -> None:
    item = HackerNewsAdapter().normalize({
        "objectID": "42", "title": "Ask HN", "story_text": "<p>Need a tool</p>",
        "author": "user", "created_at_i": 1700000000, "points": 5,
    })
    assert item.source_type == "story"
    assert item.body == "Need a tool"


def test_youtube_comment_normalization() -> None:
    item = YouTubeAdapter().normalize({
        "id": "c1", "snippet": {
            "videoId": "v1", "textOriginal": "Notifications do not work",
            "authorDisplayName": "a", "publishedAt": "2025-01-01T00:00:00Z",
        },
    }, video_id="v1")
    assert item.source_type == "comment"
    assert item.canonical_url.endswith("&lc=c1")


def test_app_store_review_normalization() -> None:
    item = AppStoreAdapter().normalize({
        "id": {"label": "r1"}, "title": {"label": "Bad"},
        "content": {"label": "Sync is broken"}, "im:rating": {"label": "2"},
        "updated": {"label": "2025-01-01T00:00:00Z"},
        "author": {"name": {"label": "person"}}, "link": {"attributes": {"href": "https://apps.apple.com/review/r1"}},
    }, app_id="123")
    assert item.rating == 2
    assert item.source_type == "review"


def test_app_store_review_string_id_variation() -> None:
    item = AppStoreAdapter().normalize({
        "id": "review-string-id", "title": {"label": "Bad"},
        "content": {"label": "Crashes"}, "im:rating": {"label": "1"},
        "updated": {"label": "2025-01-01T00:00:00Z"},
    }, app_id="123")
    assert item.source_id == "review-string-id"


def test_google_play_review_normalization() -> None:
    item = GooglePlayAdapter().normalize({
        "reviewId": "r1", "content": "Too expensive", "score": 2,
        "userName": "person", "at": datetime(2025, 1, 1),
    }, app_id="com.example")
    assert item.rating == 2
    assert "com.example" in item.canonical_url


def test_google_trends_manual_import(tmp_path: Path) -> None:
    path = tmp_path / "trends.csv"
    path.write_text("query,date,value\nalarm,2025-01-01,55\n", encoding="utf-8")
    storage = temp_storage(tmp_path)
    run_id = storage.create_run("test", {})
    result = import_records("google_trends", path, storage, run_id)
    assert result["imported"] == 1


def test_solution_and_explicit_payment_detection() -> None:
    evidence = findings("Is there an app for this? I paid $12 monthly but cancelled my subscription because sync is broken.")
    types = {f.evidence_type for f in evidence if f.verification_status == "verified"}
    assert {"active_solution_search", "current_paid_solution", "explicit_price", "cancellation"} <= types


def test_weak_interest_is_not_willingness_to_pay() -> None:
    assert not any(f.evidence_type == "willingness_to_pay" for f in findings("I would maybe use this."))
    assert any(f.evidence_type == "willingness_to_pay" for f in findings("I would pay $20 for exactly this."))


def test_current_paid_product_detection() -> None:
    assert any(f.evidence_type == "current_paid_solution" for f in findings("I subscribe to the premium version monthly."))


def test_cancellation_refund_uninstall_detection() -> None:
    types = {f.evidence_type for f in findings("I cancelled because it was buggy, requested a refund, then uninstalled it.")}
    assert {"cancellation", "refund", "uninstall"} <= types


def test_maker_promotion_excluded_from_independent_demand() -> None:
    evidence = findings("I built our app. Download my app; it fixes this frustrating issue.")
    assert all(f.organic_evidence_weight == 0 for f in evidence if f.evidence_type != "promotion")


def test_temporary_viral_spike_classification() -> None:
    assert classify_trend([10] * 8 + [100, 15, 12, 10]) == "temporary_spike"


def test_xhs_only_us_claim_rejected() -> None:
    source = record(
        "I struggle with mornings", source="xhs", source_id="x1",
        canonical_url="https://xhs.example/x1", not_us_validation=True,
    )
    evidence = RulesEvidenceClassifier().classify(source, "test")
    verified = [ReportVerifier().verify(f, source) for f in evidence]
    assert all(f.verification_status == "rejected" for f in verified)


def test_competitor_pricing_requires_recent_source() -> None:
    product = CompetitorProduct(
        name="Example", platform="ios", official_url="https://example.com",
        current_price=10, price_currency="USD",
    )
    warnings = validate_competitor(product)
    assert product.current_price is None
    assert warnings


def test_same_thread_and_author_caps() -> None:
    all_findings = []
    for index in range(10):
        source = record(
            "I struggle with this and nothing works", source_id=f"c{index}",
            source_type="comment", thread_id="same-thread", author_public_name="same-author",
        )
        all_findings.extend(findings(source.body, source_id=source.source_id, source_type="comment",
                                     thread_id=source.thread_id, author_public_name=source.author_public_name))
    assessment = CandidateRanker().assess("test", all_findings)
    assert assessment.independent_authors == 1
    assert assessment.independent_threads == 1


def test_query_planner_limits_explosion() -> None:
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    planned = QueryPlanner(max_queries_per_source=12).plan(pack, ["reddit", "app_store"])
    assert len(planned) <= 24
    assert all(q.maximum_results <= 100 and q.purpose for q in planned)


class FakeAdapter:
    name = "fake"
    enabled_by_default = True
    calls = 0

    def health_check(self):
        return {"status": "available", "credential_required": False}

    def estimate_request_cost(self, query, options):
        return {"api_calls": 1, "expected_records": 1}

    def discover(self, query, options):
        self.calls += 1
        return [record("I struggle with this", source="fake", source_id=f"{self.calls}", thread_id=f"{self.calls}")]

    def fetch_replies(self, item, options):
        return []


def test_conservative_request_limits_and_resume(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    adapter = FakeAdapter()
    runner = ResearchRunner(storage, {"fake": adapter})
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    pack.sources = ["fake"]
    options = CrawlOptions(max_records=1, max_comments=0, max_runtime_minutes=1)
    result = runner.run(pack, ["fake"], options)
    assert result["records_valid"] <= 24
    assert adapter.calls <= 24
    # A completed run is not selected for resume; an interrupted run is.
    run = storage.create_run(pack.slug, {})
    storage.finish_run(run, "interrupted", "test")
    assert storage.latest_resumable_run(pack.slug) == run
    completed = storage.create_run(pack.slug, {})
    storage.finish_run(completed, "completed")
    assert storage.latest_resumable_run(pack.slug) is None


class ReviewAdapter(FakeAdapter):
    def discover(self, query, options):
        self.calls += 1
        return [record(
            "App description", source="app_store", source_type="app",
            source_id="app1", canonical_url="https://apps.apple.com/app/id1", thread_id="app1",
        )]

    def fetch_replies(self, item, options):
        texts = [
            "Notifications never fire and I missed every scheduled reminder.",
            "The subscription costs too much for a basic checklist utility.",
            "Sync deleted my carefully prepared morning routine across devices.",
        ]
        return [
            record(
                text,
                source="app_store", source_type="review", source_id=f"review{i}",
                canonical_url="https://apps.apple.com/app/id1", thread_id="app1",
            )
            for i, text in enumerate(texts)
        ]


def test_reviews_with_shared_app_url_are_not_collapsed(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    adapter = ReviewAdapter()
    runner = ResearchRunner(storage, {"app_store": adapter})
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    pack.sources = ["app_store"]
    runner.run(pack, ["app_store"], CrawlOptions(max_records=1, max_reviews=3, max_competitors=1))
    reviews = storage.frame("source_records")
    assert len(reviews[reviews["source_type"] == "review"]) == 3


def test_old_reviews_are_excluded_by_freshness_window(tmp_path: Path) -> None:
    class DatedReviewAdapter(ReviewAdapter):
        def fetch_replies(self, item, options):
            recent = record(
                "Recent notifications do not work", source="app_store",
                source_type="review", source_id="recent-review",
                canonical_url="https://apps.apple.com/app/id1", thread_id="app1",
                published_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
            old = record(
                "Old sync is broken", source="app_store",
                source_type="review", source_id="old-review",
                canonical_url="https://apps.apple.com/app/id1", thread_id="app1",
                published_at=datetime.now(timezone.utc) - timedelta(days=500),
            )
            return [recent, old]

    storage = temp_storage(tmp_path)
    runner = ResearchRunner(storage, {"app_store": DatedReviewAdapter()})
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    pack.sources = ["app_store"]
    runner.run(
        pack, ["app_store"],
        CrawlOptions(max_records=1, max_reviews=2, max_competitors=1, recent_days=365),
    )
    records = storage.frame("source_records")
    assert "recent-review" in set(records["source_id"])
    assert "old-review" not in set(records["source_id"])


def test_competitor_records_respect_candidate_cap(tmp_path: Path) -> None:
    class ManyAppsAdapter(FakeAdapter):
        name = "app_store"

        def discover(self, query, options):
            self.calls += 1
            return [record(
                f"App {self.calls}", source="app_store", source_type="app",
                source_id=f"app-{self.calls}",
                canonical_url=f"https://apps.apple.com/app/id{self.calls}",
                title=f"App {self.calls}", app_name=f"App {self.calls}",
                thread_id=f"app-{self.calls}",
            )]

        def fetch_replies(self, item, options):
            return []

    storage = temp_storage(tmp_path)
    adapter = ManyAppsAdapter()
    adapter.calls = 0
    runner = ResearchRunner(storage, {"app_store": adapter})
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    pack.sources = ["app_store"]
    runner.run(
        pack, ["app_store"],
        CrawlOptions(max_records=1, max_reviews=0, max_competitors=3),
    )
    competitors = storage.frame("competitors")
    assert len(competitors) == 3


def test_credential_absence_fallback(monkeypatch) -> None:
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    assert RedditAdapter().health_check()["status"] == "unavailable"


def test_manual_import_rejects_malformed_rows(tmp_path: Path) -> None:
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps([{"id": "1"}, {"id": "2", "body": "buggy", "rating": 1}]), encoding="utf-8")
    storage = temp_storage(tmp_path)
    run_id = storage.create_run("test", {})
    result = import_records("app_store", path, storage, run_id)
    assert result["rejected"] == 1
    assert result["imported"] == 1


def test_report_contains_evidence_links(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    run_id = storage.create_run("test", {})
    source = record("I struggle with this. Is there an app for it?")
    storage.save_record(source, run_id)
    for finding in findings(source.body):
        storage.save_finding(finding, run_id)
    paths = generate_demand_report(storage, run_id, "test", tmp_path / "reports")
    report = paths["markdown"].read_text(encoding="utf-8")
    assert source.canonical_url in report
    assert paths["evidence"].exists()


def test_migration_preserves_legacy_rows(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    import sqlite3
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE posts(x); CREATE TABLE comments(x); CREATE TABLE findings(x); INSERT INTO posts VALUES(1);")
    conn.close()
    storage = ResearchStorage(db)
    assert storage.legacy_counts() == {"posts": 1, "comments": 0, "findings": 0}


def test_findings_remain_members_of_multiple_runs(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    source = record("I struggle with this. Is there an app for it?")
    first = storage.create_run("first", {})
    second = storage.create_run("second", {})
    storage.save_record(source, first)
    storage.save_record(source, second)
    finding = findings(source.body)[0]
    storage.save_finding(finding, first)
    storage.save_finding(finding, second)
    assert len(storage.frame("evidence_findings", first)) == 1
    assert len(storage.frame("evidence_findings", second)) == 1


def test_trend_points_remain_members_of_multiple_runs(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    point = GoogleTrendsAdapter().normalize({
        "query": "alarm", "date": datetime(2025, 1, 1, tzinfo=timezone.utc), "value": 55,
    })
    first = storage.create_run("first", {})
    second = storage.create_run("second", {})
    storage.save_record(point, first)
    storage.save_record(point, second)
    assert len(storage.frame("trend_series", first)) == 1
    assert len(storage.frame("trend_series", second)) == 1


def test_interrupted_run_actually_resumes_pending_queries(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    class ResumeAdapter(FakeAdapter):
        def discover(self, query, options):
            self.calls += 1
            return [record(
                f"I struggle with distinct issue {self.calls}: {query}",
                source="fake", source_id=f"resume-{self.calls}", thread_id=f"resume-{self.calls}",
            )]

    adapter = ResumeAdapter()
    adapter.calls = 0
    runner = ResearchRunner(storage, {"fake": adapter})
    pack = load_research_pack(Path("config/research_packs/adhd_morning_departure_us.yaml"))
    pack.sources = ["fake"]
    pack.keywords = ["single resumable query"]
    interrupted = runner.run(
        pack, ["fake"], CrawlOptions(max_records=1, max_comments=0, max_runtime_minutes=0),
    )
    resumed = runner.run(
        pack, ["fake"], CrawlOptions(
            max_records=1, max_comments=0, max_runtime_minutes=1, resume=True,
        ),
    )
    assert interrupted["status"] == "interrupted"
    assert resumed["run_id"] == interrupted["run_id"]
    assert resumed["status"] == "completed"
    assert adapter.calls > 0


def test_analysis_uses_competitor_count_and_links_complaints(tmp_path: Path) -> None:
    storage = temp_storage(tmp_path)
    run_id = storage.create_run("test", {})
    app = record(
        "Routine helper", source="app_store", source_type="app", source_id="app1",
        canonical_url="https://apps.apple.com/us/app/id1", title="Routine Helper",
        app_name="Routine Helper", thread_id="app1",
    )
    app.raw_payload = {"price": 4.99, "currency": "USD"}
    review = record(
        "This app crashes and notifications never fire.",
        source="app_store", source_type="review", source_id="review1",
        canonical_url="https://apps.apple.com/us/app/id1", app_name="Routine Helper",
        thread_id="app1", rating=1,
    )
    storage.save_record(app, run_id)
    storage.save_record(review, run_id)
    result = analyze_run(storage, run_id, "test")
    assert result["assessment"]["crowding_score"] == 7
    competitor = storage.frame("competitors", run_id).iloc[0]
    assert "crashes" in competitor["common_complaints_json"]


def test_http_get_cache_avoids_duplicate_request(tmp_path: Path, monkeypatch) -> None:
    client = ConservativeHttpClient(
        delay_seconds=0, cache_dir=tmp_path / "cache", cache_ttl_seconds=60,
    )
    calls = 0

    def fake_request(method, url, **kwargs):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"ok": True}, headers={"content-type": "application/json"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(client.client, "request", fake_request)
    assert client.request("GET", "https://example.com/data", params={"q": "x"}).json()["ok"]
    assert client.request("GET", "https://example.com/data", params={"q": "x"}).json()["ok"]
    assert calls == 1


def test_youtube_comments_paginate_with_mocked_api(monkeypatch) -> None:
    adapter = YouTubeAdapter()
    pages = iter([
        {
            "items": [{
                "snippet": {
                    "topLevelComment": {"id": "c1", "snippet": {"videoId": "v1", "textOriginal": "first"}},
                    "totalReplyCount": 0,
                },
            }],
            "nextPageToken": "next",
        },
        {
            "items": [{
                "snippet": {
                    "topLevelComment": {"id": "c2", "snippet": {"videoId": "v1", "textOriginal": "second"}},
                    "totalReplyCount": 0,
                },
            }],
        },
    ])
    monkeypatch.setattr(adapter, "_get", lambda endpoint, **params: next(pages))
    comments = list(adapter.fetch_replies("https://youtube.com/watch?v=v1", CrawlOptions(max_comments=2)))
    assert [item.source_id for item in comments] == ["c1", "c2"]
