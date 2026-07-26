from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .providers.apify_client import ApifyClient, ApifyError, ApifyNormalizedRecord
from .providers.apify_registry import ApifyActorRegistry


BLOCKER_TOPICS: dict[str, tuple[str, ...]] = {
    "production_or_deployment": (
        "production", "publishing", "publish", "deployment", "deploy", "domain",
    ),
    "cloud_or_export": (
        "lovable cloud", "migration", "github export", "export to github",
    ),
    "backend_or_data": (
        "supabase", "rls", "row level security", "database",
    ),
    "authentication_or_security": (
        "authentication", "auth", "login", "security", "permission",
    ),
    "payments_or_integrations": (
        "stripe", "revenuecat", "webhook", "api", "email",
    ),
    "mobile_launch": (
        "capacitor", "app store", "ios launch", "android launch",
    ),
}

IGNORE_PATTERNS = (
    "prompting", "prompt help", "styling", "css", "beginner ui",
    "showcase", "look what i built", "idea stage", "what should i build",
)
SUPPORT_ONLY_PATTERNS = (
    "billing dispute", "charged twice", "refund my credits", "account suspended",
    "lovable support", "platform outage", "status page",
)
BLOCKED_LANGUAGE = (
    "blocked", "stuck", "cannot", "can't", "doesn't work", "does not work",
    "failed", "error", "broken", "production down",
)
IMPACT_LANGUAGE = (
    "customer", "users", "launch", "production", "revenue", "live",
    "security", "data loss", "deadline",
)


def blockers_plan(
    registry: ApifyActorRegistry,
    *,
    provider: str = "apify",
    recent_hours: int = 24,
) -> dict[str, Any]:
    actor = registry.actor("reddit")
    can_run, reason = registry.can_execute("reddit")
    template_ready = bool(
        actor and actor.template(
            "blockers", subreddit="lovable", maximum_records=50,
            recent_hours=recent_hours,
        )
    )
    return {
        "workflow": "lovable_rescue_watch",
        "provider": provider,
        "actors_selected": [actor.actor_id] if actor and actor.actor_id else [],
        "queries": ["r/lovable"],
        "estimated_runs": 1 if can_run and template_ready else 0,
        "maximum_records": 50,
        "maximum_deep_posts": 10,
        "maximum_comments": 300,
        "estimated_cost_usd": actor.cost_estimate_usd if actor else None,
        "missing_actor_ids": (
            [actor.actor_id_env] if actor and not actor.actor_id else
            ["APIFY_REDDIT_ACTOR_ID"] if not actor else []
        ),
        "untested_actors": (
            [actor.actor_id] if actor and actor.actor_id and registry.effective_approval("reddit") != "approved"
            else []
        ),
        "sources_skipped": [] if can_run and template_ready else [{"source": "reddit", "reason": reason if not can_run else "blockers input template missing"}],
        "recent_hours": recent_hours,
    }


def run_lovable_blockers(
    registry: ApifyActorRegistry,
    client: ApifyClient,
    *,
    provider: str = "apify",
    recent_hours: int = 24,
    output_dir: Path = Path("data/reports"),
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    actor = registry.actor("reddit")
    can_run, reason = registry.can_execute("reddit")
    if provider != "apify":
        return _write_not_researched(
            output_dir, f"provider {provider!r} is not implemented for this workflow"
        )
    if not actor or not can_run:
        return _write_not_researched(output_dir, reason)
    actor_input = actor.template(
        "blockers", subreddit="lovable", maximum_records=50,
        recent_hours=recent_hours,
    )
    if actor_input is None:
        return _write_not_researched(output_dir, "approved Reddit Actor has no blockers input template")
    try:
        result = client.collect(
            source="reddit",
            actor_id=actor.actor_id or "",
            actor_input=actor_input,
            actor_schema=actor.expected_output_schema,
            maximum_records=50,
            timeout_seconds=int(registry.defaults.get("blocker_timeout_seconds") or 900),
            estimated_cost_usd=actor.cost_estimate_usd,
            max_cost_usd=_cost_limit(
                "APIFY_MAX_ACTOR_RUN_COST_USD",
                registry.defaults.get("max_actor_run_cost_usd"),
            ),
            query="r/lovable",
        )
    except ApifyError as exc:
        return _write_not_researched(output_dir, f"Reddit Actor collection failed: {exc}")
    cutoff = now - timedelta(hours=max(1, recent_hours))
    verified_recent: list[ApifyNormalizedRecord] = []
    stale = missing_timestamp = duplicates = 0
    for record in sorted(
        result.normalized_records,
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    ):
        if not record.timestamp_verified or not record.published_at:
            missing_timestamp += 1
            continue
        if record.published_at < cutoff or record.published_at > now + timedelta(minutes=5):
            stale += 1
            continue
        if registry.is_processed("lovable_rescue_watch", "reddit", record.source_id):
            duplicates += 1
            continue
        if record.source_type == "comment":
            continue
        verified_recent.append(record)
    denominator = len(verified_recent) + duplicates
    saturation = duplicates / denominator if denominator else 0.0
    if saturation > 0.80:
        verified_recent = []
    leads: list[dict[str, Any]] = []
    opened = 0
    for record in verified_recent:
        prefilter = score_blocker_prefilter(record)
        comments: list[str] = []
        if prefilter["score"] >= 4 and opened < 10:
            comments = _comments_from_items(record.source_id, result.items)[:300]
            opened += 1
        final = score_blocker_final(record, prefilter, comments)
        if final["score"] >= 6 and final["independent_developer_solvable"]:
            leads.append(_lead_payload(record, prefilter, final, comments))
        registry.mark_processed(
            "lovable_rescue_watch", "reddit", record.source_id,
            result.actor_run_id, record.published_at,
        )
    registry.save_collection_run(
        workflow="lovable_rescue_watch",
        result=result,
        records_accepted=len(verified_recent),
    )
    newest = max(
        (record.published_at for record in verified_recent if record.published_at),
        default=None,
    )
    payload = {
        "workflow": "lovable_rescue_watch",
        "research_status": "COMPLETE" if not result.partial else "PARTIAL",
        "generated_at": now.isoformat(),
        "provider": "apify",
        "source": "reddit",
        "actor_id": result.actor_id,
        "actor_run_id": result.actor_run_id,
        "records_fetched": len(result.items),
        "records_normalized": len(result.normalized_records),
        "verified_recent_posts": len(verified_recent),
        "missing_or_unverified_timestamps": missing_timestamp,
        "stale_records": stale,
        "duplicates": duplicates,
        "duplicate_saturation": round(saturation, 4),
        "newest_verified_timestamp": newest.isoformat() if newest else None,
        "deep_posts_opened": opened,
        "qualifying_blockers": leads,
        "cost": result.request_cost_metadata,
        "warnings": [
            *result.warnings,
            (
                "Comment evidence is available only when the configured single Reddit "
                "Actor run includes comments in its dataset; no second Actor run is made."
            ),
        ],
        "automatic_actions": {
            "public_replies_sent": 0,
            "private_messages_sent": 0,
        },
    }
    return _write_report(output_dir, payload)


def score_blocker_prefilter(record: ApifyNormalizedRecord) -> dict[str, Any]:
    text = f"{record.title or ''} {record.text}".lower()
    ignored = [pattern for pattern in IGNORE_PATTERNS if pattern in text]
    support_only = [pattern for pattern in SUPPORT_ONLY_PATTERNS if pattern in text]
    topics = [
        name for name, patterns in BLOCKER_TOPICS.items()
        if any(pattern in text for pattern in patterns)
    ]
    score = 0
    if topics:
        score += min(3, len(topics))
    if any(pattern in text for pattern in BLOCKED_LANGUAGE):
        score += 2
    if any(pattern in text for pattern in IMPACT_LANGUAGE):
        score += 2
    if record.comment_count and record.comment_count > 0:
        score += 1
    if ignored or support_only:
        score = 0
    return {
        "score": score,
        "topics": topics,
        "ignored_patterns": ignored,
        "support_only_patterns": support_only,
    }


def score_blocker_final(
    record: ApifyNormalizedRecord,
    prefilter: dict[str, Any],
    comments: list[str],
) -> dict[str, Any]:
    text = f"{record.title or ''} {record.text}".lower()
    support_only = bool(prefilter["support_only_patterns"])
    solvable = bool(prefilter["topics"]) and not support_only
    score = int(prefilter["score"])
    if any(word in text for word in ("i ", "my ", "we ", "our ")):
        score += 1
    if comments:
        score += 1
    if solvable:
        score += 1
    return {
        "score": score,
        "independent_developer_solvable": solvable,
        "comment_evidence_count": len(comments),
    }


def _lead_payload(
    record: ApifyNormalizedRecord,
    prefilter: dict[str, Any],
    final: dict[str, Any],
    comments: list[str],
) -> dict[str, Any]:
    topics = prefilter["topics"]
    root_causes, diagnostics, missing = _diagnostics(topics)
    scope = (
        "Fixed-scope diagnostic engagement appears possible; confirm reproduction, "
        "access boundaries, and success criteria before quoting."
    )
    return {
        "source_id": record.source_id,
        "source_url": record.canonical_url,
        "title": record.title,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "prefilter_score": prefilter["score"],
        "final_score": final["score"],
        "blocker_topics": topics,
        "likely_root_causes": root_causes,
        "safe_diagnostic_checks": diagnostics,
        "missing_information": missing,
        "comment_evidence": comments[:10],
        "public_reply_draft": (
            "This looks reproducible enough to narrow down safely. I would first verify "
            f"{'; '.join(diagnostics[:2])}. If you can share the exact error text and "
            "which environment fails, someone can suggest a more precise next check."
        ),
        "private_follow_up": "DO NOT SEND — no automated private outreach is permitted.",
        "internal_fixed_scope_assessment": scope,
    }


def _diagnostics(topics: list[str]) -> tuple[list[str], list[str], list[str]]:
    causes: list[str] = []
    checks: list[str] = []
    missing = [
        "exact error text and timestamp",
        "whether failure occurs in preview, production, or both",
        "minimal reproduction steps",
    ]
    mapping = {
        "production_or_deployment": (
            "environment-specific build, DNS, or deployment configuration mismatch",
            "compare preview and production environment variables without sharing secrets",
        ),
        "cloud_or_export": (
            "migration/export state differs from the source project configuration",
            "verify repository branch, generated files, and migration completion state",
        ),
        "backend_or_data": (
            "schema, policy, or environment mismatch in Supabase",
            "inspect failing request status and relevant RLS policy using a non-production test user",
        ),
        "authentication_or_security": (
            "redirect, session, provider, or permission configuration mismatch",
            "check callback URLs, session expiry, and least-privilege policy paths",
        ),
        "payments_or_integrations": (
            "webhook signature, secret scope, endpoint, or event mismatch",
            "compare provider delivery logs with sanitized server logs and event IDs",
        ),
        "mobile_launch": (
            "native wrapper, entitlement, signing, or store configuration mismatch",
            "reproduce in a clean release build and inspect sanitized native logs",
        ),
    }
    for topic in topics:
        if topic in mapping:
            cause, check = mapping[topic]
            causes.append(cause)
            checks.append(check)
    return causes or ["root cause cannot be narrowed from the public post"], checks or ["request a minimal reproduction before proposing changes"], missing


def _comments_from_items(post_id: str, items: list[dict[str, Any]]) -> list[str]:
    comments: list[str] = []
    for item in items:
        parent = item.get("postId") or item.get("link_id") or item.get("parentPostId")
        if str(parent or "").removeprefix("t3_") == post_id:
            text = item.get("body") or item.get("text") or item.get("content")
            if text:
                comments.append(str(text))
        if str(item.get("id") or item.get("postId") or "") == post_id:
            nested = item.get("comments")
            if isinstance(nested, list):
                for comment in nested:
                    if isinstance(comment, dict):
                        text = comment.get("body") or comment.get("text") or comment.get("content")
                        if text:
                            comments.append(str(text))
    return comments


def _processed_ids(registry: ApifyActorRegistry, workflow: str, source: str) -> set[str]:
    return {
        str(row[0]) for row in registry.storage.conn.execute(
            "SELECT source_id FROM apify_processed_records WHERE workflow=? AND source=?",
            (workflow, source),
        )
    }


def _write_not_researched(output_dir: Path, reason: str) -> dict[str, Any]:
    payload = {
        "workflow": "lovable_rescue_watch",
        "research_status": "NOT_RESEARCHED",
        "reason": reason,
        "records_fetched": 0,
        "newest_verified_timestamp": None,
        "qualifying_blockers": [],
        "automatic_actions": {
            "public_replies_sent": 0,
            "private_messages_sent": 0,
        },
    }
    return _write_report(output_dir, payload)


def _write_report(output_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "lovable_blockers_latest.json"
    md_path = output_dir / "lovable_blockers_latest.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    lines = [
        "# Lovable Rescue Watch", "",
        f"- Research status: `{payload['research_status']}`",
        f"- Records fetched: {payload.get('records_fetched', 0)}",
        f"- Newest verified timestamp: {payload.get('newest_verified_timestamp') or 'none'}",
        f"- Qualifying blockers: {len(payload.get('qualifying_blockers') or [])}",
        "- Automated public replies: 0",
        "- Automated private messages: 0",
    ]
    if payload.get("reason"):
        lines.extend(["", "## Collection limitation", "", str(payload["reason"])])
    for blocker in payload.get("qualifying_blockers") or []:
        lines.extend([
            "", f"## [{blocker.get('title') or blocker['source_id']}]({blocker['source_url']})", "",
            f"- Final score: {blocker['final_score']}",
            f"- Topics: {', '.join(blocker['blocker_topics'])}",
            f"- Likely root causes: {'; '.join(blocker['likely_root_causes'])}",
            f"- Safe checks: {'; '.join(blocker['safe_diagnostic_checks'])}",
            f"- Missing information: {'; '.join(blocker['missing_information'])}",
            "", "### Public reply draft", "",
            blocker["public_reply_draft"],
            "", "### Private follow-up", "",
            blocker["private_follow_up"],
            "", "### Internal fixed-scope assessment", "",
            blocker["internal_fixed_scope_assessment"],
        ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {**payload, "report_paths": {"markdown": str(md_path), "json": str(json_path)}}


def _cost_limit(name: str, default: Any) -> float | None:
    value = os.getenv(name)
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return None
