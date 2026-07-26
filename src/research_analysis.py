from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .analysis.evidence_classifier import RulesEvidenceClassifier
from .analysis.report_verifier import ReportVerifier
from .analysis.trend_analyzer import classify_trend
from .discovery.candidate_ranker import CandidateRanker
from .research_models import SourceRecord
from .research_storage import ResearchStorage, now_iso


def analyze_run(storage: ResearchStorage, run_id: int, pack_slug: str, mode: str = "rules") -> dict:
    if mode == "llm":
        from .analysis.llm_classifier import LLMEvidenceClassifier
        classifier = LLMEvidenceClassifier()
    else:
        classifier = RulesEvidenceClassifier()
    verifier = ReportVerifier()
    rows = storage.frame("source_records", run_id)
    findings = []
    for row in rows.to_dict(orient="records"):
        record = SourceRecord(
            source=row["source"], source_type=row["source_type"], source_id=row["source_id"],
            canonical_url=row["canonical_url"], title=_none(row.get("title")), body=_none(row.get("body")),
            author_public_name=_none(row.get("author_public_name")),
            published_at=_dt(row.get("published_at")), fetched_at=_dt(row.get("fetched_at")),
            country_signal=_none(row.get("country_signal")), language=_none(row.get("language")) or "unknown",
            score_or_votes=_none(row.get("score_or_votes")), comment_count=_none(row.get("comment_count")),
            rating=_none(row.get("rating")), app_name=_none(row.get("app_name")), product_name=_none(row.get("product_name")),
            query=_none(row.get("query")), search_rank=_none(row.get("search_rank")),
            raw_json_path=_none(row.get("raw_json_path")), thread_id=_none(row.get("thread_id")),
            parent_id=_none(row.get("parent_id")), market_role=_none(row.get("market_role")),
            default_market=_none(row.get("default_market")),
            not_us_validation=bool(row.get("not_us_validation")),
        )
        for finding in classifier.classify(record, problem_category=pack_slug):
            finding = verifier.verify(finding, record)
            findings.append(finding)
    # Replace only this run's membership after a complete classifier pass.
    # Globally deduplicated findings and other runs remain intact.
    storage.conn.execute(
        "DELETE FROM research_run_evidence_findings WHERE research_run_id=?",
        (run_id,),
    )
    storage.conn.commit()
    for finding in findings:
        storage.save_finding(finding, run_id)
    competitors = storage.frame("competitors", run_id)
    trends = storage.frame("trend_series", run_id)
    trend_classification = (
        classify_trend(trends["value"].dropna().astype(float).tolist())
        if not trends.empty else "insufficient_data"
    )
    risk_flags = sum(
        token in pack_slug.lower()
        for token in ("adhd", "addiction", "detox", "safety", "medical", "legal")
    )
    assessment = CandidateRanker().assess(
        pack_slug, findings,
        competitor_count=int(competitors["name"].nunique()) if not competitors.empty else 0,
        trend_classification=trend_classification,
        risk_flags=risk_flags,
    )
    assessment.rationale.append(f"trend classification: {trend_classification}")
    _update_competitor_analysis(storage, run_id, rows, findings)
    storage.conn.execute(
        """INSERT OR REPLACE INTO opportunity_candidates(
           research_run_id,problem_key,classification,recommendation,problem_evidence_score,
           solution_demand_score,payment_evidence_score,market_gap_score,crowding_score,risk_score,
           independent_authors,independent_threads,independent_platforms,rationale_json,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, assessment.problem_key, assessment.classification, assessment.recommendation,
         assessment.problem_evidence_score, assessment.solution_demand_score,
         assessment.payment_evidence_score, assessment.market_gap_score,
         assessment.crowding_score, assessment.risk_score, assessment.independent_authors,
         assessment.independent_threads, assessment.independent_platforms,
         json.dumps(assessment.rationale), now_iso()),
    )
    storage.conn.commit()
    return {"run_id": run_id, "records_analyzed": len(rows), "findings": len(findings), "assessment": assessment.__dict__}


def _update_competitor_analysis(
    storage: ResearchStorage,
    run_id: int,
    records: pd.DataFrame,
    findings: list,
) -> None:
    if records.empty:
        return
    storage.conn.execute(
        """UPDATE competitors SET common_complaints_json='[]',
           missing_features_json='[]',cancellation_reasons_json='[]'
           WHERE research_run_id=?""",
        (run_id,),
    )
    app_names: dict[tuple[str, str], str] = {}
    for row in records.to_dict(orient="records"):
        if row.get("source_type") == "app":
            app_names[(str(row.get("source")), str(row.get("thread_id")))] = str(
                _none(row.get("app_name")) or _none(row.get("title")) or ""
            )
    record_index = {
        (str(row.get("source")), str(row.get("source_id"))): row
        for row in records.to_dict(orient="records")
    }
    grouped: dict[tuple[str, str], dict[str, set[str]]] = {}
    for finding in findings:
        row = record_index.get((finding.source, finding.source_id), {})
        thread_id = str(_none(row.get("thread_id")) or finding.thread_id or "")
        name = str(_none(row.get("app_name")) or app_names.get((finding.source, thread_id)) or "")
        if not name:
            continue
        bucket = grouped.setdefault(
            (finding.source, name),
            {"complaints": set(), "missing": set(), "cancellations": set(), "links": set()},
        )
        if finding.verification_status != "verified":
            continue
        excerpt = finding.evidence_text.replace("\n", " ")[:500]
        if finding.evidence_type == "explicit_problem":
            bucket["complaints"].add(excerpt)
        elif finding.evidence_type == "missing_feature_request":
            bucket["missing"].add(excerpt)
        elif finding.evidence_type in {"cancellation", "refund", "uninstall", "switch"}:
            bucket["cancellations"].add(excerpt)
        if finding.source_url:
            bucket["links"].add(finding.source_url)
    for (platform, name), values in grouped.items():
        row = storage.conn.execute(
            "SELECT evidence_links_json FROM competitors WHERE research_run_id=? AND platform=? AND name=?",
            (run_id, platform, name),
        ).fetchone()
        prior_links = set(json.loads(row[0] or "[]")) if row else set()
        storage.conn.execute(
            """UPDATE competitors SET common_complaints_json=?,missing_features_json=?,
               cancellation_reasons_json=?,evidence_links_json=?
               WHERE research_run_id=? AND platform=? AND name=?""",
            (
                json.dumps(sorted(values["complaints"])[:20]),
                json.dumps(sorted(values["missing"])[:20]),
                json.dumps(sorted(values["cancellations"])[:20]),
                json.dumps(sorted(prior_links | values["links"])[:50]),
                run_id, platform, name,
            ),
        )
    storage.conn.commit()


def _dt(value):
    value = _none(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _none(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
