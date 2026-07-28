from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv


DEFAULT_STATE_PATH = Path("data/reports/global_to_malaysia_email_state.json")
GENERIC_LINK_LABELS = {"open source", "read more", "source", "link"}
GENERIC_CANDIDATE_PHRASES = {
    "app missing feature",
    "app use every day",
    "available malaysia",
    "best new consumer app",
    "better alternative",
    "cancelled subscription",
    "every app",
    "how do you solve",
    "how solve",
    "malaysia alternative app",
    "malaysia delivery not available",
    "manually every week",
    "no android version",
    "no iphone version",
    "one time purchase app",
    "paid app",
    "remain unnecessarily difficult",
    "removed feature",
    "requested refund",
    "struggle every day",
    "support malaysian payments",
    "switched app",
    "looking tool",
    "tasks remain unnecessarily difficult",
    "this takes hours",
    "takes hours",
    "uninstalled",
    "why difficult",
    "why so difficult",
    "wish",
    "workaround",
    "worth money app",
}


def notify_opportunity_candidates(
    result: dict[str, Any],
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Email newly changed opportunity candidates without failing the research run."""
    candidates = list(result.get("candidates") or [])
    if not candidates:
        return {"status": "skipped", "reason": "no opportunity candidates"}

    load_dotenv()
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("RESEND_FROM_EMAIL", "").strip()
    to_email = os.getenv("RESEND_ALERT_TO_EMAIL", "").strip()
    if not api_key or not from_email or not to_email:
        missing = [
            name
            for name, value in (
                ("RESEND_API_KEY", api_key),
                ("RESEND_FROM_EMAIL", from_email),
                ("RESEND_ALERT_TO_EMAIL", to_email),
            )
            if not value
        ]
        return {
            "status": "skipped",
            "reason": f"missing email configuration: {', '.join(missing)}",
        }

    fingerprint = _candidate_fingerprint(candidates)
    previous = _read_state(state_path)
    if previous.get("fingerprint") == fingerprint:
        return {"status": "skipped", "reason": "opportunity candidates are unchanged"}

    decision = _overall_decision(result, candidates)
    subject = f"[CariLead] {decision} - Global to Malaysia"
    payload = {
        "from": f"CariLead Alerts <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": _html_email(result, candidates),
        "text": _text_email(result, candidates),
    }
    try:
        response = (post or httpx.post)(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        response_payload = response.json()
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "email_id": response_payload.get("id"),
                "candidate_count": len(candidates),
                "generated_at": result.get("generated_at"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "status": "sent",
        "email_id": response_payload.get("id"),
        "candidate_count": len(candidates),
    }


def _candidate_fingerprint(candidates: list[dict[str, Any]]) -> str:
    material = [
        {
            "candidate_key": item.get("candidate_key"),
            "classification": item.get("classification"),
            "research_status": item.get("research_status"),
            "independent_authors": item.get("independent_authors"),
            "payment_or_usage_signals": item.get("payment_or_usage_signals"),
            "malaysia_evidence_records": item.get("malaysia_evidence_records"),
            "rationale": item.get("rationale"),
            "links": sorted(item.get("links") or []),
            "sources": item.get("sources"),
            "opportunity": item.get("opportunity"),
            "problem": item.get("problem"),
            "existing_alternatives": item.get("existing_alternatives"),
            "decision": item.get("decision"),
            "decision_reason": item.get("decision_reason"),
        }
        for item in candidates
    ]
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_state(state_path: Path) -> dict[str, Any]:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _html_email(result: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    decision = _overall_decision(result, candidates)
    sections = []
    for index, candidate in enumerate(candidates[:3], start=1):
        narrative = _candidate_narrative(candidate)
        links = "".join(
            f'<li><a href="{html.escape(item["url"], quote=True)}">'
            f'{html.escape(item["label"])}</a></li>'
            for item in narrative["sources"]
        )
        sections.append(
            """
            <section style="margin:24px 0">
              <h2 style="font-size:18px;margin:0 0 12px;color:#0f172a">{index}. {opportunity}</h2>
              <p><strong>Problem:</strong> {problem}</p>
              <p><strong>Evidence:</strong> {evidence}</p>
              <p><strong>Existing alternatives:</strong> {alternatives}</p>
              <p><strong>Why we win or reject:</strong> {reason}</p>
              <p><strong>Decision:</strong> {decision}</p>
              {links_section}
            </section>
            """.format(
                index=index,
                opportunity=html.escape(narrative["opportunity"]),
                problem=html.escape(narrative["problem"]),
                evidence=html.escape(narrative["evidence"]),
                alternatives=html.escape(narrative["alternatives"]),
                reason=html.escape(narrative["reason"]),
                decision=html.escape(narrative["decision"]),
                links_section=(
                    f"<p><strong>Evidence links:</strong></p><ul>{links}</ul>"
                    if links
                    else ""
                ),
            )
        )
    summary = "".join(
        f"<li>{html.escape(line)}</li>" for line in _collection_summary(result)
    )
    next_action = html.escape(_next_action(result, decision))
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#334155">
      <p style="font-size:20px;color:#0f172a">
        <strong>Completed. CEO decision: {html.escape(decision)} today.</strong>
      </p>
      <ul>{summary}</ul>
      {''.join(sections)}
      <p style="font-size:17px;color:#0f172a"><strong>{next_action}</strong></p>
      <p style="font-size:12px;color:#64748b">
        Research status: {html.escape(str(result.get("research_status") or "unknown"))}.
        Generated: {html.escape(str(result.get("generated_at") or "unknown"))}.
      </p>
    </div>
    """


def _text_email(result: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    decision = _overall_decision(result, candidates)
    lines = [
        f"Completed. CEO decision: {decision} today.",
        "",
        *_collection_summary(result),
        "",
    ]
    for index, candidate in enumerate(candidates[:3], start=1):
        narrative = _candidate_narrative(candidate)
        lines.extend(
            [
                f"{index}. {narrative['opportunity']}",
                f"Problem: {narrative['problem']}",
                f"Evidence: {narrative['evidence']}",
                f"Existing alternatives: {narrative['alternatives']}",
                f"Why we win or reject: {narrative['reason']}",
                f"Decision: {narrative['decision']}",
            ]
        )
        lines.extend(
            f"{item['label']}: {item['url']}" for item in narrative["sources"]
        )
        lines.append("")
    lines.extend(
        [
            _next_action(result, decision),
            "",
            f"Research status: {result.get('research_status') or 'unknown'}",
            f"Generated: {result.get('generated_at') or 'unknown'}",
        ]
    )
    return "\n".join(lines)


def _overall_decision(
    result: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str:
    explicit = _normalize_decision(result.get("ceo_decision"))
    if explicit:
        return explicit
    decisions = {
        _candidate_narrative(candidate)["decision"] for candidate in candidates[:3]
    }
    if "BUILD" in decisions:
        return "BUILD"
    if decisions & {"RESEARCH MORE", "WATCH"}:
        return "RESEARCH MORE"
    return "NO BUILD"


def _candidate_narrative(candidate: dict[str, Any]) -> dict[str, Any]:
    raw_name = _first_text(
        candidate,
        "opportunity",
        "opportunity_name",
        "opportunity_summary",
        "candidate_key",
    ) or "Unnamed candidate"
    explicit_opportunity = _first_text(
        candidate,
        "opportunity",
        "opportunity_name",
        "opportunity_summary",
        "what_to_build",
    )
    abstract = _is_abstract_candidate(raw_name) and not explicit_opportunity
    if abstract:
        opportunity = "No concrete opportunity identified from this cluster"
        problem = (
            f'The records were grouped under the broad discovery query “{raw_name}”, '
            "not one specific customer problem."
        )
        alternatives = "Not evaluated because the cluster is not a real product category."
        reason = (
            "The result does not state what to build, who would buy it, or why they "
            "would pay. It must not be presented as an opportunity."
        )
        decision = "REJECT"
    else:
        opportunity = explicit_opportunity or raw_name
        problem = _first_text(
            candidate,
            "problem",
            "problem_summary",
            "customer_problem",
        ) or (
            f"Users are discussing {raw_name}, but the exact customer job still "
            "requires validation."
        )
        alternatives = _display_value(
            candidate.get("existing_alternatives")
            or candidate.get("competitors")
            or (candidate.get("evaluation_dimensions") or {}).get(
                "malaysia_competitors"
            )
        ) or "Not established by the collected evidence."
        reason = _first_text(
            candidate,
            "decision_reason",
            "why_we_win_or_reject",
            "wedge",
            "rationale",
        ) or "No defensible wedge has been established."
        decision = _candidate_decision(candidate)
    return {
        "opportunity": opportunity,
        "problem": problem,
        "evidence": _evidence_summary(candidate),
        "alternatives": alternatives,
        "reason": reason,
        "decision": decision,
        "sources": _source_links(candidate),
    }


def _candidate_decision(candidate: dict[str, Any]) -> str:
    explicit = _normalize_decision(candidate.get("decision"))
    if explicit:
        return explicit
    classification = str(candidate.get("classification") or "").upper()
    status = str(candidate.get("research_status") or "").upper()
    if classification == "REJECT":
        return "REJECT"
    if status in {"NOT_RESEARCHED", "INSUFFICIENT_EVIDENCE"}:
        return "RESEARCH MORE"
    if classification in {
        "MALAYSIA_FIRST",
        "SEA_COUNTRY_SPECIFIC",
        "GLOBAL_ENGLISH",
    }:
        return "RESEARCH MORE"
    return "WATCH"


def _normalize_decision(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("_", " ")
    aliases = {
        "BUILD": "BUILD",
        "NO BUILD": "NO BUILD",
        "RESEARCH": "RESEARCH MORE",
        "RESEARCH MORE": "RESEARCH MORE",
        "CONTINUE RESEARCH": "RESEARCH MORE",
        "WATCH": "WATCH",
        "REJECT": "REJECT",
    }
    return aliases.get(normalized)


def _collection_summary(result: dict[str, Any]) -> list[str]:
    stage_a = result.get("stage_a") or {}
    stage_c = result.get("stage_c") or {}
    records = result.get("records_collected")
    if records is None:
        records = int(stage_a.get("records") or 0) + int(stage_c.get("records") or 0)
    unique = _first_not_none(
        result.get("unique_posts"),
        result.get("unique_records"),
        stage_a.get("unique_posts"),
    )
    new = _first_not_none(
        result.get("new_since_yesterday"),
        result.get("new_records"),
        stage_a.get("new_since_yesterday"),
    )
    cost = result.get("actual_apify_cost_usd")
    if cost is None:
        costs = [
            run.get("cost", {}).get("actual_cost_usd")
            for run in stage_a.get("runs") or []
            if isinstance(run, dict) and isinstance(run.get("cost"), dict)
        ]
        known_costs = [float(value) for value in costs if value is not None]
        cost = sum(known_costs) if known_costs else None
    return [
        f"Records collected: {records}.",
        f"Unique posts: {unique if unique is not None else 'not recorded'}.",
        f"New versus yesterday: {new if new is not None else 'not recorded'}.",
        (
            f"Actual Apify cost: ${float(cost):.5f}."
            if cost is not None
            else "Actual Apify cost: not reported."
        ),
    ]


def _evidence_summary(candidate: dict[str, Any]) -> str:
    explicit = _first_text(candidate, "evidence", "evidence_summary")
    if explicit:
        return explicit
    return (
        f"{int(candidate.get('independent_authors') or 0)} independent authors; "
        f"{int(candidate.get('payment_or_usage_signals') or 0)} payment/usage "
        f"signals; {int(candidate.get('malaysia_evidence_records') or 0)} "
        "Malaysia-related records."
    )


def _next_action(result: dict[str, Any], decision: str) -> str:
    explicit = str(result.get("next_action") or "").strip()
    if explicit:
        return explicit
    if decision == "BUILD":
        return "Therefore: define the smallest paid validation before building."
    if decision == "RESEARCH MORE":
        return "Therefore: continue validation; no landing page, MVP, or marketing yet."
    return "Therefore: no landing page, MVP, or marketing."


def _is_abstract_candidate(value: str) -> bool:
    normalized = " ".join(
        word
        for word in value.lower().replace("-", " ").split()
        if word not in {"i", "a", "an", "the", "this", "that", "is", "there"}
    )
    return (
        normalized in GENERIC_CANDIDATE_PHRASES
        or any(phrase in normalized for phrase in GENERIC_CANDIDATE_PHRASES)
    )


def _source_links(candidate: dict[str, Any]) -> list[dict[str, str]]:
    raw_sources = candidate.get("sources") or candidate.get("links") or []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in raw_sources:
        if isinstance(source, dict):
            raw_url = str(source.get("url") or source.get("href") or "").strip()
            label = str(source.get("label") or source.get("title") or "").strip()
        else:
            raw_url = str(source).strip()
            label = ""
        canonical = _canonical_url(raw_url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        if not label or label.lower() in GENERIC_LINK_LABELS:
            label = _descriptive_link_label(canonical)
        output.append({"label": label, "url": canonical})
        if len(output) == 3:
            break
    return output


def _canonical_url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        return ""
    parts = urlsplit(value)
    tracking = {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
    }
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in tracking
        ]
    )
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            query,
            "",
        )
    )


def _descriptive_link_label(value: str) -> str:
    parts = urlsplit(value)
    host = parts.netloc.lower().removeprefix("www.")
    segments = [unquote(item) for item in parts.path.split("/") if item]
    if host.endswith("reddit.com") and "comments" in segments:
        position = segments.index("comments")
        slug = segments[position + 2] if len(segments) > position + 2 else ""
        title = _humanize_slug(slug)
        return f"Reddit: {title or 'discussion'}"
    slug = _humanize_slug(segments[-1] if segments else "")
    brand = host.split(".")[0].replace("-", " ").title()
    return f"{brand}: {slug}" if slug else brand


def _humanize_slug(value: str) -> str:
    words = " ".join(part for part in value.replace("_", " ").split("-") if part)
    return words[:100].strip().capitalize()


def _first_text(candidate: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _display_value(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lower().startswith("requires "):
            return ""
        return normalized
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {item}" for key, item in value.items() if item not in (None, "")
        )
    return ""


def _first_not_none(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)
