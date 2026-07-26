from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .analysis.evidence_classifier import RulesEvidenceClassifier
from .analysis.report_verifier import ReportVerifier
from .deduplicator import Deduplicator
from .discovery.candidate_ranker import CandidateRanker
from .discovery.query_planner import QueryPlanner
from .research_models import CrawlOptions, ResearchPack, SourceRecord
from .research_storage import ResearchStorage
from .sources.base import SourceAdapterError, SourceAuthError, SourceBlockedError
from .sources.registry import build_registry


class ResearchRunner:
    def __init__(self, storage: ResearchStorage | None = None, adapters: dict | None = None) -> None:
        self.storage = storage or ResearchStorage()
        self.adapters = adapters or build_registry()

    def plan(
        self, pack: ResearchPack, sources: list[str], options: CrawlOptions,
    ) -> dict[str, Any]:
        queries = QueryPlanner().plan(pack, sources, options.recent_days, options.max_records)
        by_source: dict[str, dict[str, Any]] = {}
        for source in sources:
            adapter = self.adapters.get(source)
            health = adapter.health_check() if adapter else {"status": "unavailable", "detail": "unknown source"}
            sq = [q for q in queries if q.source == source]
            discovery_calls = sum(adapter.estimate_request_cost(q.query, options)["api_calls"] for q in sq) if adapter else 0
            reply_calls = 0
            reply_records = 0
            if source in {"reddit", "hacker_news", "youtube"}:
                source_comment_limit = options.max_comments
                if source == "reddit":
                    source_comment_limit = min(source_comment_limit, options.max_reddit_comments)
                elif source == "youtube":
                    source_comment_limit = min(source_comment_limit, options.max_youtube_comments)
                reply_calls = min(len(sq) * options.max_records, source_comment_limit)
                reply_records = source_comment_limit
            elif source in {"app_store", "google_play"}:
                reply_calls = options.max_competitors * max(1, (options.max_reviews + 49) // 50)
                reply_records = options.max_competitors * options.max_reviews
            by_source[source] = {
                "status": health["status"], "detail": health.get("detail"),
                "queries": len(sq),
                "estimated_discovery_api_calls": discovery_calls,
                "estimated_reply_or_review_api_calls_upper_bound": reply_calls,
                "estimated_api_calls": discovery_calls + reply_calls,
                "expected_discovery_records": min(
                    len(sq) * options.max_records,
                    sum(int(adapter.estimate_request_cost(q.query, options)["expected_records"]) for q in sq) if adapter else 0,
                ),
                "expected_reply_or_review_records_upper_bound": reply_records,
                "will_skip": health["status"] in {"unavailable", "manual-import-only", "temporarily failing"},
            }
        active_calls = sum(v["estimated_api_calls"] for v in by_source.values() if not v["will_skip"])
        return {
            "pack": pack.slug, "queries": len(queries), "sources": by_source,
            "estimated_runtime_minutes": min(options.max_runtime_minutes, round(active_calls * max(options.delay_seconds, 0.25) / 60 + 1, 1)),
            "credential_requirements": {
                name: self.adapters[name].health_check().get("credential_required", False)
                for name in sources if name in self.adapters
            },
        }

    def run(self, pack: ResearchPack, sources: list[str], options: CrawlOptions) -> dict[str, Any]:
        self.storage.save_pack(pack, Path(f"config/research_packs/{pack.slug}.yaml"))
        run_id = self.storage.latest_resumable_run(pack.slug) if options.resume else None
        if run_id is None:
            run_id = self.storage.create_run(pack.slug, options.model_dump(mode="json"))
            queries = QueryPlanner().plan(pack, sources, options.recent_days, options.max_records)
            self.storage.save_queries(run_id, queries)
        statuses = {
            source: (
                self.adapters[source].health_check()
                if source in self.adapters
                else {"status": "unavailable", "credential_required": False, "detail": "unknown source"}
            )
            for source in sources
        }
        self.storage.save_run_sources(run_id, statuses)
        for adapter in self.adapters.values():
            http = getattr(adapter, "http", None)
            if http is not None and hasattr(http, "force_refresh"):
                http.force_refresh = options.force_refresh
                http.delay_seconds = max(http.delay_seconds, options.delay_seconds)
        started = time.monotonic()
        existing = self.storage.conn.execute(
            """SELECT records_discovered,records_valid,duplicate_records
               FROM research_runs WHERE id=?""", (run_id,),
        ).fetchone()
        discovered, valid, duplicates = (
            (int(existing[0]), int(existing[1]), int(existing[2])) if existing else (0, 0, 0)
        )
        filtered_out_of_scope = 0
        membership_count = self.storage.conn.execute(
            "SELECT count(*) FROM research_run_source_records WHERE research_run_id=?",
            (run_id,),
        ).fetchone()[0]
        valid = max(valid, int(membership_count))
        discovered = max(discovered, valid + duplicates)
        dedupe = Deduplicator()
        for prior in self.storage.frame("source_records", run_id).to_dict(orient="records"):
            prior_url = (
                None if prior.get("source_type") in {"comment", "review"}
                else prior.get("canonical_url")
            )
            dedupe.is_duplicate(
                f"{prior.get('source')}:{prior.get('source_id')}",
                prior_url,
                f"{prior.get('title') or ''} {prior.get('body') or ''}",
            )
        stopped_reason = None
        source_stopped: set[str] = set()
        reply_counts: dict[str, int] = {}
        reply_roots: dict[str, int] = {}
        competitor_ids: dict[str, set[str]] = {}
        for prior in self.storage.frame("source_records", run_id).to_dict(orient="records"):
            if prior.get("source_type") in {"app", "product"}:
                competitor_ids.setdefault(str(prior["source"]), set()).add(str(prior["source_id"]))
        try:
            # Resolve unavailable/manual-only sources once and persist every
            # skipped query before any live source can reach a stop condition.
            availability: dict[str, dict[str, Any]] = {}
            for row in self.storage.pending_queries(run_id):
                source = row["source"]
                if source not in sources:
                    continue
                adapter = self.adapters.get(source)
                health = availability.setdefault(
                    source,
                    statuses.get(source) if adapter else {"status": "unavailable", "detail": "unknown source"},
                )
                if health["status"] in {"unavailable", "manual-import-only", "temporarily failing"}:
                    self.storage.finish_query(row["id"], "skipped", error=health.get("detail"))
                    source_stopped.add(source)
            for row in self.storage.pending_queries(run_id):
                source = row["source"]
                if source not in sources or source in source_stopped:
                    continue
                if time.monotonic() - started >= options.max_runtime_minutes * 60:
                    stopped_reason = "maximum runtime reached"
                    break
                adapter = self.adapters.get(source)
                if not adapter:
                    self.storage.finish_query(row["id"], "skipped", error="unknown source")
                    continue
                health = adapter.health_check()
                if health["status"] in {"unavailable", "manual-import-only", "temporarily failing"}:
                    self.storage.finish_query(row["id"], "skipped", error=health.get("detail"))
                    continue
                query_options = options.model_copy(update={"max_records": min(row["maximum_results"], options.max_records)})
                count = 0
                try:
                    records = adapter.discover(row["query"], query_options)
                    for record in records:
                        discovered += 1
                        if record.source_type in {"app", "product"}:
                            selected_competitors = competitor_ids.setdefault(record.source, set())
                            if (
                                record.source_id not in selected_competitors
                                and len(selected_competitors) >= options.max_competitors
                            ):
                                filtered_out_of_scope += 1
                                continue
                            selected_competitors.add(record.source_id)
                        if dedupe.is_duplicate(
                            f"{record.source}:{record.source_id}",
                            record.canonical_url,
                            f"{record.title or ''} {record.body or ''}",
                        ):
                            duplicates += 1
                            continue
                        self._persist_raw(record)
                        if self.storage.save_record(record, run_id):
                            valid += 1
                            count += 1
                            added, duped = self._fetch_bounded_replies(
                                adapter, record, query_options, run_id, dedupe,
                                reply_counts, reply_roots,
                            )
                            discovered += added + duped
                            valid += added
                            duplicates += duped
                    self.storage.finish_query(row["id"], "completed", count=count)
                    if hasattr(adapter, "get_rate_limit_status"):
                        self.storage.save_rate_limit(source, adapter.get_rate_limit_status())
                except (SourceAuthError, SourceBlockedError) as exc:
                    self.storage.save_error(run_id, source, row["query"], "discover", exc)
                    self.storage.finish_query(row["id"], "stopped", error=str(exc))
                    source_stopped.add(source)
                except SourceAdapterError as exc:
                    self.storage.save_error(run_id, source, row["query"], "discover", exc)
                    self.storage.finish_query(row["id"], "failed", error=str(exc))
                self.storage.update_run_counts(run_id, discovered, valid, duplicates)
                if discovered >= 20 and duplicates / discovered > 0.70:
                    stopped_reason = "duplicate saturation exceeded 70%"
                    break
                if valid >= 50 and self._has_sufficient_evidence(run_id, pack.slug):
                    stopped_reason = "sufficient evidence threshold reached"
                    break
            status = (
                "completed"
                if not stopped_reason or stopped_reason in {
                    "duplicate saturation exceeded 70%",
                    "sufficient evidence threshold reached",
                }
                else "interrupted"
            )
            self.storage.finish_run(run_id, status, stopped_reason)
        except KeyboardInterrupt:
            stopped_reason = "interrupted by user"
            self.storage.update_run_counts(run_id, discovered, valid, duplicates)
            self.storage.finish_run(run_id, "interrupted", stopped_reason)
        final_status = self.storage.conn.execute(
            "SELECT status FROM research_runs WHERE id=?", (run_id,),
        ).fetchone()[0]
        return {
            "run_id": run_id, "status": final_status,
            "records_discovered": discovered, "records_valid": valid,
            "duplicates": duplicates, "filtered_out_of_scope": filtered_out_of_scope,
            "stopped_reason": stopped_reason,
            "elapsed_minutes": round((time.monotonic() - started) / 60, 2),
        }

    def _fetch_bounded_replies(
        self, adapter, record: SourceRecord, options: CrawlOptions, run_id: int,
        dedupe: Deduplicator, reply_counts: dict[str, int], reply_roots: dict[str, int],
    ) -> tuple[int, int]:
        if record.source_type not in {"post", "story", "video", "app"}:
            return 0, 0
        source = record.source
        reply_counts.setdefault(source, 0)
        reply_roots.setdefault(source, 0)
        limit = options.max_reviews * options.max_competitors if source in {"app_store", "google_play"} else options.max_comments
        if source == "youtube":
            limit = min(limit, options.max_youtube_comments)
        if source == "reddit":
            limit = min(limit, options.max_reddit_comments)
        if reply_counts[source] >= limit:
            return 0, 0
        if source in {"app_store", "google_play"} and reply_roots[source] >= options.max_competitors:
            return 0, 0
        remaining = limit - reply_counts[source]
        child_options = options.model_copy(update={
            "max_comments": remaining, "max_reviews": min(remaining, options.max_reviews),
        })
        saved = duplicates = 0
        try:
            replies = adapter.fetch_replies(record.canonical_url or record.source_id, child_options)
            reply_roots[source] += 1
            for reply in replies:
                if reply_counts[source] >= limit:
                    break
                reply_counts[source] += 1
                if not _within_freshness(reply.published_at, options.recent_days):
                    continue
                # Comments/reviews commonly share their parent post or app URL;
                # using it as an atomic-record identity collapses independent
                # evidence. Their stable IDs and text remain dedupe keys.
                reply_url = None if reply.source_type in {"comment", "review"} else reply.canonical_url
                if dedupe.is_duplicate(
                    f"{reply.source}:{reply.source_id}", reply_url, reply.body,
                ):
                    duplicates += 1
                    continue
                if not reply.app_name and record.source_type == "app":
                    reply.app_name = record.app_name or record.title
                if not reply.product_name and record.source_type in {"app", "product"}:
                    reply.product_name = record.product_name or record.title
                self._persist_raw(reply)
                if self.storage.save_record(reply, run_id):
                    saved += 1
        except (SourceAuthError, SourceBlockedError):
            raise
        except Exception as exc:
            self.storage.save_error(run_id, source, record.query, "replies", exc)
        return saved, duplicates

    def _persist_raw(self, record: SourceRecord) -> None:
        raw_dir = Path("data/raw") / record.source / date.today().isoformat()
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in record.source_id)[:120]
        path = raw_dir / f"{record.source_type}_{safe_id}.json"
        if not path.exists():
            path.write_text(json.dumps(record.raw_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        record.raw_json_path = str(path)

    def _has_sufficient_evidence(self, run_id: int, problem_key: str) -> bool:
        classifier = RulesEvidenceClassifier()
        verifier = ReportVerifier()
        findings = []
        for row in self.storage.frame("source_records", run_id).to_dict(orient="records"):
            record = _record_from_row(row)
            findings.extend(
                verifier.verify(finding, record)
                for finding in classifier.classify(record, problem_key)
            )
        assessment = CandidateRanker().assess(problem_key, findings)
        return assessment.recommendation == "strong_candidate"


def _record_from_row(row: dict[str, Any]) -> SourceRecord:
    def clean(value: Any) -> Any:
        if value is None:
            return None
        try:
            return None if pd.isna(value) else value
        except (TypeError, ValueError):
            return value

    return SourceRecord(
        source=row["source"], source_type=row["source_type"], source_id=row["source_id"],
        canonical_url=row["canonical_url"], title=clean(row.get("title")), body=clean(row.get("body")),
        author_public_name=clean(row.get("author_public_name")),
        published_at=clean(row.get("published_at")), fetched_at=clean(row.get("fetched_at")),
        country_signal=clean(row.get("country_signal")), language=clean(row.get("language")) or "unknown",
        score_or_votes=clean(row.get("score_or_votes")), comment_count=clean(row.get("comment_count")),
        rating=clean(row.get("rating")), app_name=clean(row.get("app_name")),
        product_name=clean(row.get("product_name")), query=clean(row.get("query")),
        search_rank=clean(row.get("search_rank")), raw_json_path=clean(row.get("raw_json_path")),
        thread_id=clean(row.get("thread_id")), parent_id=clean(row.get("parent_id")),
        market_role=clean(row.get("market_role")), default_market=clean(row.get("default_market")),
        not_us_validation=bool(row.get("not_us_validation")),
    )


def _within_freshness(value: datetime | None, recent_days: int) -> bool:
    if value is None:
        return True
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware >= datetime.now(timezone.utc) - timedelta(days=recent_days)
