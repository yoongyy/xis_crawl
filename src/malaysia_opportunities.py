from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis.evidence_classifier import RulesEvidenceClassifier
from .analysis.report_verifier import ReportVerifier
from .providers.apify_client import ApifyClient, ApifyError, ApifyNormalizedRecord
from .providers.apify_registry import ActorConfig, ApifyActorRegistry
from .research_models import SourceRecord


DISCOVERY_QUERIES = [
    ("problem", "I hate that every app"),
    ("problem", "I struggle with this every day"),
    ("problem", "this is frustrating nothing works"),
    ("problem", "why is this so difficult"),
    ("problem", "this takes me hours"),
    ("solution_search", "is there an app for"),
    ("solution_search", "looking for a tool that"),
    ("solution_search", "is there a better alternative"),
    ("solution_search", "how do you solve this"),
    ("solution_search", "I wish there was"),
    ("payment", "I paid for this app"),
    ("payment", "worth the money app"),
    ("payment", "one-time purchase app"),
    ("payment", "I subscribe because"),
    ("cancellation", "cancelled my subscription because"),
    ("cancellation", "requested a refund because"),
    ("cancellation", "uninstalled because"),
    ("workaround", "I do this manually every week"),
    ("workaround", "my workaround for"),
    ("missing_feature", "app missing feature"),
    ("missing_feature", "removed the feature"),
    ("missing_feature", "no Android version"),
    ("missing_feature", "no iPhone version"),
    ("geographic_gap", "not available in Malaysia"),
    ("geographic_gap", "Malaysia alternative app"),
    ("geographic_gap", "does not support Malaysian payments"),
    ("geographic_gap", "Malaysia delivery not available"),
    ("product_traction", "app I use every day"),
    ("product_traction", "best new consumer app"),
    ("product_traction", "I switched to this app"),
]

DISCOVERY_SOURCES = (
    "reddit", "youtube", "tiktok", "app_store", "google_play", "google_trends",
)
DEEP_SOURCES = (
    "reddit", "youtube_comments", "tiktok_comments",
    "app_store", "google_play", "google_trends",
)


def opportunities_plan(
    registry: ApifyActorRegistry,
    *,
    provider: str = "apify",
    target_market: str = "malaysia",
    mode: str = "global-transfer",
) -> dict[str, Any]:
    actors: list[dict[str, Any]] = []
    missing: list[str] = []
    untested: list[str] = []
    skipped: list[dict[str, str]] = []
    estimated_runs = 0
    estimated_cost = 0.0
    cost_known = True
    for source in DISCOVERY_SOURCES:
        actor = registry.actor(source)
        allowed, reason = registry.can_execute(source)
        if actor and actor.actor_id:
            actors.append({
                "source": source, "actor_id": actor.actor_id,
                "actor_name": actor.actor_name, "approval": registry.effective_approval(source),
            })
            if registry.effective_approval(source) != "approved":
                untested.append(actor.actor_id)
        elif actor:
            missing.append(actor.actor_id_env)
        template_ready = bool(allowed and actor and actor.template(
            "discovery", queries=["test"], maximum_records=50,
            target_market=target_market,
        ) is not None)
        if template_ready and actor:
            estimated_runs += 1
            if actor.cost_estimate_usd is None:
                cost_known = False
            else:
                estimated_cost += actor.cost_estimate_usd
        else:
            skipped.append({
                "source": source,
                "reason": reason if not allowed else "discovery input template missing",
            })
    reddit_ready, reddit_reason = registry.can_execute("reddit")
    return {
        "workflow": "global_to_malaysia_opportunity_dig",
        "provider": provider,
        "target_market": target_market,
        "mode": mode,
        "actors_selected": actors,
        "queries": [
            {"purpose": purpose, "query": query}
            for purpose, query in DISCOVERY_QUERIES[:30]
        ],
        "estimated_runs": estimated_runs,
        "maximum_records": 30 * 50,
        "estimated_cost_usd": round(estimated_cost, 4) if cost_known else None,
        "missing_actor_ids": sorted(set(missing)),
        "untested_actors": sorted(set(untested)),
        "sources_skipped": skipped,
        "broad_run_allowed": reddit_ready,
        "broad_run_blocker": None if reddit_ready else reddit_reason,
    }


def run_global_to_malaysia(
    registry: ApifyActorRegistry,
    client: ApifyClient,
    *,
    provider: str = "apify",
    target_market: str = "malaysia",
    mode: str = "global-transfer",
    output_dir: Path = Path("data/reports"),
) -> dict[str, Any]:
    if provider != "apify":
        return _write_opportunity_outputs(
            output_dir,
            _not_researched(f"provider {provider!r} is not implemented"),
            [],
        )
    reddit_ready, reddit_reason = registry.can_execute("reddit")
    if not reddit_ready:
        return _write_opportunity_outputs(
            output_dir,
            _not_researched(
                f"broad workflow blocked until Reddit Actor passes schema, timestamp, and freshness validation: {reddit_reason}"
            ),
            [],
        )
    assignments = _assign_queries(registry)
    if not assignments:
        return _write_opportunity_outputs(
            output_dir,
            _not_researched("no approved discovery Actor with a configured discovery input template"),
            [],
        )
    estimated_total = sum(
        actor.cost_estimate_usd or 0.0 for actor, _ in assignments.values()
    )
    workflow_limit = _cost_limit(
        "APIFY_MAX_WORKFLOW_COST_USD",
        registry.defaults.get("max_workflow_cost_usd"),
    )
    if workflow_limit is not None and estimated_total > workflow_limit:
        return _write_opportunity_outputs(
            output_dir,
            _not_researched(
                f"estimated discovery cost ${estimated_total:.4f} exceeds workflow limit ${workflow_limit:.4f}"
            ),
            [],
        )
    records: list[ApifyNormalizedRecord] = []
    source_status: dict[str, dict[str, Any]] = {}
    runs: list[dict[str, Any]] = []
    for source, (actor, queries) in assignments.items():
        actor_input = actor.template(
            "discovery",
            queries=[query for _, query in queries],
            maximum_records=min(1500, len(queries) * 50),
            target_market=target_market,
        )
        if actor_input is None:
            source_status[source] = {"status": "NOT_RESEARCHED", "reason": "discovery input template missing"}
            continue
        try:
            result = client.collect(
                source=source,
                actor_id=actor.actor_id or "",
                actor_input=actor_input,
                actor_schema=actor.expected_output_schema,
                maximum_records=min(1500, len(queries) * 50),
                timeout_seconds=int(registry.defaults.get("opportunity_timeout_seconds") or 1800),
                estimated_cost_usd=actor.cost_estimate_usd,
                max_cost_usd=_cost_limit(
                    "APIFY_MAX_ACTOR_RUN_COST_USD",
                    registry.defaults.get("max_actor_run_cost_usd"),
                ),
                query=" | ".join(query for _, query in queries),
            )
        except ApifyError as exc:
            source_status[source] = {"status": "NOT_RESEARCHED", "reason": str(exc)}
            continue
        records.extend(result.normalized_records)
        registry.save_collection_run(
            workflow="global_to_malaysia_discovery",
            result=result,
            records_accepted=len(result.normalized_records),
        )
        source_status[source] = {
            "status": "PARTIAL" if result.partial else "COMPLETE",
            "records": len(result.normalized_records),
        }
        runs.append({
            "source": source, "actor_run_id": result.actor_run_id,
            "records": len(result.normalized_records),
            "partial": result.partial,
            "cost": result.request_cost_metadata,
        })
    findings = _classify_records(records)
    shortlist, rejected = _shortlist(records, findings)
    deep_records, deep_status = _deep_evidence(
        registry, client, shortlist, target_market,
    )
    records.extend(deep_records)
    findings = _classify_records(records)
    source_status.update(deep_status)
    candidates = _evaluate_candidates(shortlist, records, findings, source_status)
    required_failed = any(
        value.get("status") == "NOT_RESEARCHED"
        for value in source_status.values()
    )
    research_status = (
        "NOT_RESEARCHED" if required_failed
        else "INSUFFICIENT_EVIDENCE" if not candidates
        else "COMPLETE"
    )
    payload = {
        "workflow": "global_to_malaysia_opportunity_dig",
        "research_status": research_status,
        "provider": "apify",
        "target_market": target_market,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stage_a": {
            "queries": len(DISCOVERY_QUERIES[:30]),
            "records": len(records) - len(deep_records),
            "source_status": source_status,
            "runs": runs,
        },
        "stage_b": {
            "shortlisted": [item["candidate_key"] for item in shortlist],
            "rejected": rejected,
        },
        "stage_c": {
            "records": len(deep_records),
            "source_status": deep_status,
        },
        "candidates": candidates,
        "limitations": [
            "A source failure is recorded as NOT_RESEARCHED and is not negative market evidence.",
            "Malaysia transfer classification requires both origin-market and Malaysia-side evidence.",
            "Search interest is not payment evidence.",
        ],
    }
    return _write_opportunity_outputs(output_dir, payload, records)


def _assign_queries(
    registry: ApifyActorRegistry,
) -> dict[str, tuple[ActorConfig, list[tuple[str, str]]]]:
    available: list[tuple[str, ActorConfig]] = []
    for source in DISCOVERY_SOURCES:
        actor = registry.actor(source)
        allowed, _ = registry.can_execute(source)
        if allowed and actor and actor.template(
            "discovery", queries=["test"], maximum_records=50,
            target_market="malaysia",
        ) is not None:
            available.append((source, actor))
    if not available:
        return {}
    assigned: dict[str, tuple[ActorConfig, list[tuple[str, str]]]] = {
        source: (actor, []) for source, actor in available
    }
    for index, query in enumerate(DISCOVERY_QUERIES[:30]):
        source, _ = available[index % len(available)]
        assigned[source][1].append(query)
    return {source: value for source, value in assigned.items() if value[1]}


def _classify_records(records: list[ApifyNormalizedRecord]) -> list[dict[str, Any]]:
    classifier = RulesEvidenceClassifier()
    verifier = ReportVerifier()
    output: list[dict[str, Any]] = []
    for record in records:
        source_record = _source_record(record)
        for finding in classifier.classify(source_record, "global_to_malaysia"):
            finding = verifier.verify(finding, source_record)
            output.append(finding.model_dump(mode="json"))
    return output


def _shortlist(
    records: list[ApifyNormalizedRecord],
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    finding_by_source: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        finding_by_source[(finding["source"], finding["source_id"])].append(finding)
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _candidate_key(record.query or record.title or record.text)
        if not key:
            continue
        bucket = grouped.setdefault(
            key,
            {
                "candidate_key": key,
                "records": 0,
                "authors": set(),
                "sources": set(),
                "evidence_types": Counter(),
                "links": set(),
            },
        )
        bucket["records"] += 1
        if record.author_hash:
            bucket["authors"].add(record.author_hash)
        bucket["sources"].add(record.source)
        if record.canonical_url:
            bucket["links"].add(record.canonical_url)
        for finding in finding_by_source[(record.source, record.source_id)]:
            if finding["verification_status"] == "verified" and finding["organic_evidence_weight"] > 0:
                bucket["evidence_types"][finding["evidence_type"]] += 1
    ranked: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for key, bucket in grouped.items():
        types = bucket["evidence_types"]
        payment_or_usage = (
            types["current_paid_solution"] + types["explicit_price"]
            + types["positive_review"] + types["personal_experience"]
        )
        solution = (
            types["active_solution_search"] + types["recommendation_request"]
            + types["explicit_wish"] + types["missing_feature_request"]
        )
        reason = None
        if bucket["records"] < 2 or len(bucket["authors"]) < 2:
            reason = "one-post or non-independent signal"
        elif " ai " in f" {key} " or key.endswith(" ai"):
            reason = "generic AI-wrapper framing"
        elif payment_or_usage == 0:
            reason = "no payment or usage evidence"
        if reason:
            rejected.append({"candidate": key, "reason": reason})
            continue
        ranked.append({
            "candidate_key": key,
            "records": bucket["records"],
            "independent_authors": len(bucket["authors"]),
            "source_count": len(bucket["sources"]),
            "payment_or_usage_signals": payment_or_usage,
            "solution_demand_signals": solution,
            "links": sorted(bucket["links"])[:10],
            "score": (
                min(20, len(bucket["authors"]) * 2)
                + min(20, payment_or_usage * 4)
                + min(20, solution * 4)
                + len(bucket["sources"]) * 5
            ),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:3], rejected


def _deep_evidence(
    registry: ApifyActorRegistry,
    client: ApifyClient,
    shortlist: list[dict[str, Any]],
    target_market: str,
) -> tuple[list[ApifyNormalizedRecord], dict[str, dict[str, Any]]]:
    records: list[ApifyNormalizedRecord] = []
    status: dict[str, dict[str, Any]] = {}
    limits = {
        "reddit": 300,
        "youtube_comments": 300,
        "tiktok_comments": 300,
        "app_store": 1500,
        "google_play": 1500,
        "google_trends": 30,
    }
    purposes = {
        "reddit": "deep_comments",
        "youtube_comments": "deep_comments",
        "tiktok_comments": "deep_comments",
        "app_store": "reviews",
        "google_play": "reviews",
        "google_trends": "trends",
    }
    for candidate in shortlist[:3]:
        key = candidate["candidate_key"]
        for source in DEEP_SOURCES:
            actor = registry.actor(source)
            allowed, reason = registry.can_execute(source)
            status_key = f"{key}:{source}"
            if not allowed or not actor:
                status[status_key] = {"status": "NOT_RESEARCHED", "reason": reason}
                continue
            actor_input = actor.template(
                purposes[source],
                query=key,
                queries=[key, f"{key} Malaysia"],
                maximum_records=limits[source],
                maximum_comments=min(300, limits[source]),
                maximum_apps=5,
                maximum_reviews=300,
                trend_keywords=10,
                target_market=target_market,
            )
            if actor_input is None:
                status[status_key] = {"status": "NOT_RESEARCHED", "reason": "deep input template missing"}
                continue
            try:
                result = client.collect(
                    source=source,
                    actor_id=actor.actor_id or "",
                    actor_input=actor_input,
                    actor_schema=actor.expected_output_schema,
                    maximum_records=limits[source],
                    timeout_seconds=int(registry.defaults.get("opportunity_timeout_seconds") or 1800),
                    estimated_cost_usd=actor.cost_estimate_usd,
                    max_cost_usd=_cost_limit(
                        "APIFY_MAX_ACTOR_RUN_COST_USD",
                        registry.defaults.get("max_actor_run_cost_usd"),
                    ),
                    query=key,
                )
            except ApifyError as exc:
                status[status_key] = {"status": "NOT_RESEARCHED", "reason": str(exc)}
                continue
            records.extend(result.normalized_records)
            registry.save_collection_run(
                workflow="global_to_malaysia_deep",
                result=result,
                records_accepted=len(result.normalized_records),
            )
            status[status_key] = {
                "status": "PARTIAL" if result.partial else "COMPLETE",
                "records": len(result.normalized_records),
            }
    return records, status


def _evaluate_candidates(
    shortlist: list[dict[str, Any]],
    records: list[ApifyNormalizedRecord],
    findings: list[dict[str, Any]],
    source_status: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    any_failure = any(value.get("status") == "NOT_RESEARCHED" for value in source_status.values())
    for candidate in shortlist:
        key = candidate["candidate_key"]
        related = [
            record for record in records
            if key in _candidate_key(record.query or record.title or record.text)
        ]
        malaysia = [
            record for record in related
            if (
                (record.country and "malaysia" in record.country.lower())
                or "malaysia" in f"{record.title or ''} {record.text}".lower()
            )
        ]
        sea = [
            record for record in related
            if record.country and record.country.lower() in {
                "singapore", "indonesia", "thailand", "philippines",
                "vietnam", "brunei", "cambodia", "laos", "myanmar",
            }
        ]
        related_ids = {(record.source, record.source_id) for record in related}
        payment_or_usage = sum(
            1
            for finding in findings
            if (finding.get("source"), finding.get("source_id")) in related_ids
            and finding.get("verification_status") == "verified"
            and finding.get("evidence_type") in {
                "current_paid_solution", "explicit_price",
                "positive_review", "personal_experience",
            }
        )
        payment_or_usage = max(candidate["payment_or_usage_signals"], payment_or_usage)
        if any_failure:
            research_status = "NOT_RESEARCHED"
            classification = "NOT_RESEARCHED"
            rationale = "required source collection did not run"
        elif len(related) < 5 or payment_or_usage < 2:
            research_status = "INSUFFICIENT_EVIDENCE"
            classification = "NOT_RESEARCHED"
            rationale = "sources ran, but usable evidence was too weak"
        elif len(malaysia) >= 3:
            research_status = "COMPLETE"
            classification = "MALAYSIA_FIRST"
            rationale = "origin traction and multiple Malaysia-side signals were collected"
        elif len(sea) >= 3:
            research_status = "COMPLETE"
            classification = "SEA_COUNTRY_SPECIFIC"
            rationale = "origin traction and repeated demand signals are specific to another SEA market"
        elif related:
            research_status = "COMPLETE"
            classification = "GLOBAL_ENGLISH"
            rationale = "origin evidence exists, but a Malaysia-specific advantage was not established"
        else:
            research_status = "COMPLETE"
            classification = "REJECT"
            rationale = "adequate collected evidence contradicted or failed to support the transfer"
        output.append({
            **candidate,
            "payment_or_usage_signals": payment_or_usage,
            "research_status": research_status,
            "classification": classification,
            "malaysia_evidence_records": len(malaysia),
            "rationale": rationale,
            "evaluation_dimensions": {
                "origin_market_traction": "not fully verified" if research_status != "COMPLETE" else "partially supported",
                "payment_evidence": candidate["payment_or_usage_signals"],
                "retention_clues": "requires review/cancellation evidence",
                "malaysia_side_demand": len(malaysia),
                "malaysia_competitors": "requires completed Malaysia app/discussion collection",
                "malaysian_pricing_power": "not verified",
                "language_cultural_adaptation": "not verified",
                "local_payment_adaptation": "not verified",
                "regulation": "manual review required",
                "distribution_advantage": "not verified",
                "ip_risk": "manual review required",
                "non_expansion_reason": "not verified",
            },
        })
    return output


def _source_record(record: ApifyNormalizedRecord) -> SourceRecord:
    return SourceRecord(
        source=record.source,
        source_type=record.source_type,
        source_id=record.source_id,
        canonical_url=record.canonical_url,
        title=record.title,
        body=record.text,
        author_public_name=record.author_public_name,
        published_at=record.published_at,
        country_signal=record.country,
        language=record.language,
        score_or_votes=record.engagement if isinstance(record.engagement, float) else None,
        comment_count=record.comment_count,
        rating=record.rating,
        query=record.query,
        raw_json_path=record.raw_json_path,
        extraction_confidence=record.extraction_confidence,
        extraction_warnings=record.extraction_warnings,
        raw_payload=record.raw_payload,
    )


def _candidate_key(value: str) -> str:
    value = re.sub(r"https?://\\S+", " ", value.lower())
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    stop = {
        "i", "a", "an", "the", "for", "to", "of", "is", "there", "this",
        "that", "app", "tool", "my", "because", "with", "every",
    }
    words = [word for word in value.split() if word not in stop and len(word) > 2]
    return " ".join(words[:6])


def _not_researched(reason: str) -> dict[str, Any]:
    return {
        "workflow": "global_to_malaysia_opportunity_dig",
        "research_status": "NOT_RESEARCHED",
        "reason": reason,
        "stage_a": {"records": 0, "runs": []},
        "stage_b": {"shortlisted": [], "rejected": []},
        "stage_c": {"records": 0},
        "candidates": [],
    }


def _write_opportunity_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    records: list[ApifyNormalizedRecord],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "global_to_malaysia_latest.json"
    md_path = output_dir / "global_to_malaysia_latest.md"
    evidence_path = output_dir / "global_to_malaysia_evidence.csv"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    fieldnames = [
        "source", "source_type", "source_id", "canonical_url", "title", "text",
        "author_public_name", "author_hash", "published_at", "fetched_at",
        "country", "language", "engagement", "rating", "comment_count", "query",
        "provider", "actor_id", "actor_run_id", "raw_json_path",
        "timestamp_verified", "extraction_confidence", "extraction_warnings",
    ]
    with evidence_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json", exclude={"raw_payload"})
            row["engagement"] = json.dumps(row.get("engagement"), ensure_ascii=False)
            row["extraction_warnings"] = json.dumps(row.get("extraction_warnings"), ensure_ascii=False)
            writer.writerow({key: row.get(key) for key in fieldnames})
    lines = [
        "# Global-to-Malaysia Opportunity Dig", "",
        f"- Research status: `{payload['research_status']}`",
        f"- Discovery records: {payload.get('stage_a', {}).get('records', 0)}",
        f"- Shortlisted candidates: {len(payload.get('stage_b', {}).get('shortlisted', []))}",
        f"- Deep-evidence records: {payload.get('stage_c', {}).get('records', 0)}",
    ]
    if payload.get("reason"):
        lines.extend(["", "## Collection limitation", "", str(payload["reason"])])
    lines.extend(["", "## Candidates", ""])
    if not payload.get("candidates"):
        lines.append("No candidate can be classified from the completed evidence.")
    for candidate in payload.get("candidates") or []:
        lines.extend([
            f"### {candidate['candidate_key']}", "",
            f"- Research status: `{candidate['research_status']}`",
            f"- Classification: `{candidate['classification']}`",
            f"- Independent authors: {candidate['independent_authors']}",
            f"- Payment/usage signals: {candidate['payment_or_usage_signals']}",
            f"- Malaysia evidence records: {candidate['malaysia_evidence_records']}",
            f"- Rationale: {candidate['rationale']}", "",
        ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        **payload,
        "report_paths": {
            "markdown": str(md_path),
            "json": str(json_path),
            "evidence": str(evidence_path),
        },
    }


def _cost_limit(name: str, default: Any) -> float | None:
    value = os.getenv(name)
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return None
