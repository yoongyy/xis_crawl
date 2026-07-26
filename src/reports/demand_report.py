from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..analysis.trend_analyzer import classify_trend
from ..research_storage import ResearchStorage


def generate_demand_report(
    storage: ResearchStorage, run_id: int, pack_slug: str, output_dir: Path = Path("data/reports"),
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = storage.frame("source_records", run_id)
    findings = storage.frame("evidence_findings", run_id)
    queries = storage.frame("source_queries", run_id)
    competitors = storage.frame("competitors", run_id)
    candidates = storage.frame("opportunity_candidates", run_id)
    errors = storage.frame("crawl_errors_v2", run_id)
    run_sources = storage.frame("research_run_sources", run_id)
    trends = storage.frame("trend_series", run_id)
    run = storage.frame("research_runs", run_id)
    valid = (
        findings[
            (findings.get("verification_status", pd.Series(dtype=str)) == "verified")
            & (findings.get("organic_evidence_weight", pd.Series(dtype=float)) > 0)
        ]
        if not findings.empty else findings
    )
    candidate = candidates.iloc[-1].to_dict() if not candidates.empty else {}
    coverage = _coverage(records, queries, run_sources, run)
    trend_classification = (
        classify_trend(trends["value"].dropna().astype(float).tolist())
        if not trends.empty else "insufficient_data"
    )
    payload = {
        "pack": pack_slug, "run_id": run_id, "executive_verdict": {
            "classification": candidate.get("classification", "insufficient_evidence"),
            "recommendation": candidate.get("recommendation", "reject"),
            "directly_proven": _proven(valid),
            "inferred": _inferred(candidate),
            "unsupported": _unsupported(valid, candidate),
        },
        "research_coverage": coverage,
        "evidence_type_counts": valid["evidence_type"].value_counts().to_dict() if not valid.empty else {},
        "candidate": candidate,
        "trend": {
            "classification": trend_classification,
            "points": len(trends),
            "queries": int(trends["query"].nunique()) if not trends.empty else 0,
        },
        "limitations": _limitations(queries, errors),
    }
    base = output_dir / f"{pack_slug}_demand_report"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    evidence_path = output_dir / f"{pack_slug}_evidence.csv"
    competitors_path = output_dir / f"{pack_slug}_competitors.csv"
    rejected_path = output_dir / f"{pack_slug}_rejected_hypotheses.csv"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md_path.write_text(_markdown(payload, valid, competitors), encoding="utf-8")
    findings.to_csv(evidence_path, index=False)
    if competitors.empty:
        pd.DataFrame(columns=[
            "name", "platform", "official_url", "current_price", "price_currency",
            "price_source_url", "rating", "review_count", "common_complaints",
            "missing_features", "evidence_links",
        ]).to_csv(competitors_path, index=False)
    else:
        competitors.rename(columns={
            "common_complaints_json": "common_complaints",
            "missing_features_json": "missing_features",
            "cancellation_reasons_json": "cancellation_reasons",
            "evidence_links_json": "evidence_links",
        }).to_csv(competitors_path, index=False)
    rejected_rows = []
    if candidate.get("classification") in {"reject", "insufficient_evidence", "weak_signal", "crowded_market", "temporary_trend"}:
        rejected_rows.append({
            "hypothesis": pack_slug, "classification": candidate.get("classification"),
            "reason": "; ".join(json.loads(candidate.get("rationale_json") or "[]")),
            "evidence_required": "independent US discussions, explicit solution demand, and payment evidence",
        })
    pd.DataFrame(rejected_rows, columns=["hypothesis", "classification", "reason", "evidence_required"]).to_csv(rejected_path, index=False)
    return {
        "markdown": md_path, "json": json_path, "evidence": evidence_path,
        "competitors": competitors_path, "rejected_hypotheses": rejected_path,
    }


def compare_reports(storage: ResearchStorage, pack_runs: dict[str, int], output: Path = Path("data/reports/us_candidate_comparison.md")) -> Path:
    rows = []
    for pack, run_id in pack_runs.items():
        candidates = storage.frame("opportunity_candidates", run_id)
        row = candidates.iloc[-1].to_dict() if not candidates.empty else {}
        rows.append((pack, row))
    lines = [
        "# United States candidate comparison", "",
        "This comparison is evidence-oriented and does not recommend building either candidate automatically.", "",
        "| Candidate | Classification | Recommendation | Independent threads | Payment evidence | Crowding | Risk |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for pack, row in rows:
        lines.append(
            f"| {pack} | {row.get('classification', 'insufficient_evidence')} | "
            f"{row.get('recommendation', 'reject')} | {row.get('independent_threads', 0)} | "
            f"{row.get('payment_evidence_score', 0):.1f} | {row.get('crowding_score', 0):.1f} | "
            f"{row.get('risk_score', 0):.1f} |"
        )
    lines.extend(["", "## Decision", "", "Choose more research unless one candidate has independent, cross-source US evidence plus explicit payment behaviour."])
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _coverage(records, queries, run_sources, run) -> dict[str, Any]:
    source_status = {
        row["source"]: {
            "status": row["status"],
            "credential_required": bool(row["credential_required"]),
            "detail": row["detail"],
        }
        for row in run_sources.to_dict(orient="records")
    } if not run_sources.empty else {}
    run_row = run.iloc[0].to_dict() if not run.empty else {}
    discovered = int(run_row.get("records_discovered") or len(records))
    valid_records = int(run_row.get("records_valid") or len(records))
    duplicates = int(run_row.get("duplicate_records") or 0)
    filtered = max(0, discovered - valid_records - duplicates)
    return {
        "sources_planned": sorted(source_status),
        "source_status": source_status,
        "sources_searched": sorted(queries.loc[queries["status"] == "completed", "source"].unique().tolist()) if not queries.empty else [],
        "queries_run": int((queries["status"] == "completed").sum()) if not queries.empty else 0,
        "records_discovered": discovered,
        "valid_records": valid_records,
        "duplicate_records": duplicates,
        "filtered_out_of_scope": filtered,
        "unique_authors": int(records["author_hash"].dropna().nunique()) if not records.empty else 0,
        "unique_threads": int(records["thread_id"].dropna().nunique()) if not records.empty else 0,
        "date_start": records["published_at"].dropna().min() if not records.empty else None,
        "date_end": records["published_at"].dropna().max() if not records.empty else None,
        "geographic_evidence": records["country_signal"].dropna().value_counts().to_dict() if not records.empty else {},
        "skipped_sources": sorted(queries.loc[queries["status"] == "skipped", "source"].unique().tolist()) if not queries.empty else [],
    }


def _proven(valid) -> list[str]:
    if valid.empty:
        return ["No demand claim is directly proven by the current run."]
    authors = valid["author_hash"].dropna().nunique()
    threads = valid["thread_id"].dropna().nunique()
    return [f"The run contains {len(valid)} verified atomic findings from {authors} identifiable author hashes across {threads} threads."]


def _inferred(candidate) -> list[str]:
    return [f"Aggregate classification is {candidate.get('classification', 'insufficient_evidence')}; scores summarize linked evidence and are not proof."]


def _unsupported(valid, candidate) -> list[str]:
    unsupported = []
    if valid.empty or not (valid["evidence_type"] == "willingness_to_pay").any():
        unsupported.append("No verified explicit willingness-to-pay statement.")
    if valid.empty or valid["source"].nunique() < 2:
        unsupported.append("Cross-platform US demand is not established.")
    if candidate.get("independent_threads", 0) < 30:
        unsupported.append("The 30-independent-discussion verification threshold is not met.")
    return unsupported


def _limitations(queries, errors) -> list[str]:
    result = [
        "Country signals from global communities are probabilistic unless a US storefront or explicit location is present.",
        "Google Trends is supporting attention evidence, never willingness-to-pay evidence.",
        "One thread and repeated authors are capped for independence.",
    ]
    if not queries.empty and (queries["status"] == "skipped").any():
        result.append("Some planned sources were skipped because credentials or a reliable automated provider were unavailable.")
    if not errors.empty:
        result.append(f"{len(errors)} crawl/import error(s) were recorded; affected source claims should be treated as incomplete.")
    return result


def _markdown(payload, findings, competitors) -> str:
    verdict = payload["executive_verdict"]
    coverage = payload["research_coverage"]
    evidence_examples = (
        findings[
            findings["evidence_type"].isin([
                "explicit_problem", "personal_experience", "workaround",
                "repeated_manual_work", "commercial_loss",
            ])
        ].sort_values(["confidence", "organic_evidence_weight"], ascending=False).head(12)
        if not findings.empty else findings
    )
    counterexamples = findings[findings["evidence_type"] == "counterexample"].head(5) if not findings.empty else findings
    active = findings[findings["evidence_type"].isin(["active_solution_search", "recommendation_request", "explicit_wish", "missing_feature_request"])] if not findings.empty else findings
    payment = findings[findings["evidence_type"].isin(["current_paid_solution", "explicit_price", "willingness_to_pay", "cancellation", "refund"])] if not findings.empty else findings
    candidate = payload.get("candidate", {})
    lines = [
        f"# {payload['pack']} demand report", "",
        "# Executive verdict", "",
        f"- Classification: `{verdict['classification']}`",
        f"- Overall recommendation: `{verdict['recommendation']}`",
        "- What is directly proven:",
        *[f"  - {x}" for x in verdict["directly_proven"]],
        "- What remains inferred:",
        *[f"  - {x}" for x in verdict["inferred"]],
        "- What is unsupported:",
        *[f"  - {x}" for x in verdict["unsupported"]],
        "", "# Research coverage", "",
        f"- Sources searched: {', '.join(coverage['sources_searched']) or 'none'}",
        f"- Sources planned: {', '.join(coverage['sources_planned']) or 'unknown'}",
        f"- Credential/provider status: `{json.dumps(coverage['source_status'], default=str)}`",
        f"- Queries completed: {coverage['queries_run']}",
        f"- Records discovered / valid: {coverage['records_discovered']} / {coverage['valid_records']}",
        f"- Duplicates / filtered out of scope: {coverage['duplicate_records']} / {coverage['filtered_out_of_scope']}",
        f"- Unique authors / threads: {coverage['unique_authors']} / {coverage['unique_threads']}",
        f"- Date coverage: {coverage['date_start'] or 'unknown'} to {coverage['date_end'] or 'unknown'}",
        f"- Geographic evidence: `{json.dumps(coverage['geographic_evidence'], default=str)}`",
        f"- Skipped sources: {', '.join(coverage['skipped_sources']) or 'none'}",
        "", "# Repeated problem evidence", "",
    ]
    lines.extend(_evidence_lines(evidence_examples, "No verified repeated problem evidence."))
    lines.extend(["", "## Strongest counterexamples", ""])
    lines.extend(_evidence_lines(counterexamples, "No counterexamples were captured; this is a research limitation, not evidence that none exist."))
    lines.extend(["", "# Active demand", ""])
    lines.extend(_evidence_lines(active, "No verified active solution search, recommendation, wish, or missing-feature request."))
    lines.extend(["", "# Existing payment", ""])
    lines.extend(_evidence_lines(payment, "No verified payment, price, refund, or cancellation evidence."))
    lines.extend(["", "# Competitor landscape", ""])
    if competitors.empty:
        lines.append("No source-linked competitor records were captured. Crowding and pricing are therefore unverified.")
    else:
        for row in competitors.to_dict(orient="records"):
            price = (
                f"{row.get('price_type') or 'price'} "
                f"{row.get('price_currency') or ''} {row.get('current_price')}"
                if row.get("price_source_url") else "unverified"
            )
            complaints = _json_list(row.get("common_complaints_json"))
            lines.append(
                f"- [{row['name']}]({row['official_url']}): price {price}; "
                f"rating {row.get('rating') or 'unknown'} from "
                f"{row.get('review_count') or 'unknown'} rating(s); "
                f"{len(complaints)} linked low-rating complaint(s)."
            )
    lines.extend([
        "", "# Trend direction", "",
        f"Trend classification: `{payload['trend']['classification']}` from "
        f"{payload['trend']['points']} point(s) across {payload['trend']['queries']} query/queries. "
        "Search attention is supporting evidence and must not be read as product demand.",
        "", "# Potential narrow opportunity", "",
    ])
    if candidate.get("classification") in {"verified_problem", "promising_hypothesis"}:
        lines.extend([
            f"- Exact target user and trigger: requires manual synthesis from the linked evidence for `{payload['pack']}`.",
            "- Current workaround and paid alternatives: only those explicitly present in the evidence CSV.",
            "- Simplest product form: not prescribed by this research report.",
            f"- Why it might work: {'; '.join(json.loads(candidate.get('rationale_json') or '[]'))}.",
            "- Why it might fail: payment, retention, safety, and competitor differentiation remain incompletely verified.",
            "- Evidence still required: independent US payment behaviour, current source-linked pricing, and counterexamples.",
        ])
    else:
        lines.append("No narrow opportunity is included because the support threshold was not met.")
    lines.extend([
        "", "# Rejected ideas", "",
        "Attractive interpretations without independent US discussions, active solution demand, and payment evidence are rejected or retained only as hypotheses.",
        "", "# Final next action", "",
        f"**{_next_action(verdict['recommendation'])}**",
        "", "# Limitations", "",
        *[f"- {x}" for x in payload["limitations"]],
    ])
    return "\n".join(lines) + "\n"


def _evidence_lines(frame, empty_message: str) -> list[str]:
    if frame.empty:
        return [empty_message]
    lines = []
    for row in frame.to_dict(orient="records"):
        excerpt = str(row["evidence_text"]).replace("\n", " ")[:240]
        lines.append(f"- `{row['evidence_type']}` — [{excerpt}]({row['source_url']})")
    return lines


def _next_action(recommendation: str) -> str:
    return {
        "run_manual_price_test": "manually ask for payment",
        "strong_candidate": "manually ask for payment",
        "investigate_further": "more research",
        "weak_payment_evidence": "more research",
    }.get(recommendation, "stop")


def _json_list(value: Any) -> list[Any]:
    if not value or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
