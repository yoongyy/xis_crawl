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
    """Email an action-oriented CEO brief after every opportunity run."""
    candidates = list(result.get("candidates") or [])

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

    decision = _overall_decision(result, candidates)
    narratives = _actionable_narratives(candidates)
    workflow_name = _workflow_name(result)
    fingerprint = _candidate_fingerprint(candidates)
    if decision == "NOT AVAILABLE":
        subject = f"[CariLead] RESEARCH RUN FAILED - {workflow_name}"
    elif narratives:
        label = (
            "TODAY'S ONE COMPANY PRIORITY"
            if _is_daily_commander(result)
            else f"{workflow_name.upper()} SOURCE CANDIDATE"
        )
        subject = f"[CariLead] {label} - {narratives[0]['opportunity']}"
    else:
        subject = f"[CariLead] NO BET FOUND - {workflow_name}"
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
    narratives = _actionable_narratives(candidates)
    sections: list[str] = []
    for index, narrative in enumerate(narratives[:3], start=1):
        links = "".join(
            f'<li><a href="{html.escape(item["url"], quote=True)}">'
            f'{html.escape(item["label"])}</a></li>'
            for item in narrative["sources"]
        )
        prospect_links = "".join(
            f'<li><a href="{html.escape(item["url"], quote=True)}">'
            f'{html.escape(item["label"])}</a></li>'
            for item in narrative["prospect_links"]
        )
        published_links = "".join(
            f'<li><a href="{html.escape(item["url"], quote=True)}">'
            f'{html.escape(item["label"])}</a></li>'
            for item in narrative["published_links"]
        )
        execution = "".join(
            _optional_html_paragraph(label, narrative[key])
            for label, key in (
                ("Why this wins today", "selection_reason"),
                ("First 10 customers", "first_10_customers"),
                ("Where to find them", "lead_sources"),
                ("Contact sequence", "contact_strategy"),
                ("Outreach message", "outreach_script"),
                ("Landing page", "landing_page"),
                ("Marketing content", "marketing_plan"),
                ("7-day scoreboard", "validation_scorecard"),
                ("Validation budget", "validation_budget"),
                ("Generated video", "generated_video_path"),
                ("Publishing blocker", "execution_blocker"),
            )
        )
        sections.append(
            """
            <section style="margin:24px 0">
              <h2 style="font-size:18px;margin:0 0 12px;color:#0f172a">{label}: {opportunity}</h2>
              <p><strong>Buyer and pain:</strong> {problem}</p>
              <p><strong>What to sell now:</strong> {offer}</p>
              <p><strong>Why they pay:</strong> {why_pay}</p>
              <p><strong>Competitors:</strong> {alternatives}</p>
              <p><strong>Our wedge:</strong> {wedge}</p>
              <p><strong>Evidence quality:</strong> {confidence}. {evidence} {reason}</p>
              <p><strong>CEO decision:</strong> {decision}</p>
              <p><strong>48-hour move:</strong> {validation}</p>
              <p><strong>Kill criterion:</strong> {kill}</p>
              {execution}
              {prospect_links_section}
              {published_links_section}
              {links_section}
            </section>
            """.format(
                label="TODAY'S BET" if index == 1 else f"BACKUP BET {index - 1}",
                opportunity=html.escape(narrative["opportunity"]),
                problem=html.escape(narrative["problem"]),
                offer=html.escape(narrative["offer"]),
                why_pay=html.escape(narrative["why_pay"]),
                evidence=html.escape(narrative["evidence"]),
                alternatives=html.escape(narrative["alternatives"]),
                wedge=html.escape(narrative["wedge"]),
                confidence=html.escape(narrative["confidence"]),
                reason=html.escape(narrative["reason"]),
                decision=html.escape(narrative["decision"]),
                validation=html.escape(narrative["validation_test"]),
                kill=html.escape(narrative["kill_criterion"]),
                execution=execution,
                prospect_links_section=(
                    "<p><strong>First 10 customer links:</strong></p>"
                    f"<ol>{prospect_links}</ol>"
                    if prospect_links
                    else ""
                ),
                published_links_section=(
                    "<p><strong>Published campaign links:</strong></p>"
                    f"<ul>{published_links}</ul>"
                    if published_links
                    else ""
                ),
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
    if decision == "NOT AVAILABLE":
        headline = (
            "Research run failed. No CEO market decision was made from an empty collection."
        )
    elif narratives:
        headline = _actionable_headline(result, narratives[0]["opportunity"])
    else:
        headline = "Hey Kenny — no concrete bet survived this collection."
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#334155">
      <p style="font-size:20px;color:#0f172a">
        <strong>{html.escape(headline)}</strong>
      </p>
      <p><strong>CEO move:</strong> {html.escape(decision)}</p>
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
    narratives = _actionable_narratives(candidates)
    if decision == "NOT AVAILABLE":
        opening = (
            "Research run failed. No CEO market decision was made from an empty collection."
        )
    elif narratives:
        opening = _actionable_headline(result, narratives[0]["opportunity"])
    else:
        opening = "Hey Kenny — no concrete bet survived this collection."
    lines = [
        opening,
        f"CEO move: {decision}.",
        "",
        *_collection_summary(result),
        "",
    ]
    for index, narrative in enumerate(narratives[:3], start=1):
        lines.extend(
            [
                (
                    "TODAY'S BET"
                    if index == 1
                    else f"BACKUP BET {index - 1}"
                )
                + f": {narrative['opportunity']}",
                f"Buyer and pain: {narrative['problem']}",
                f"What to sell now: {narrative['offer']}",
                f"Why they pay: {narrative['why_pay']}",
                f"Competitors: {narrative['alternatives']}",
                f"Our wedge: {narrative['wedge']}",
                f"Evidence quality: {narrative['confidence']}. "
                f"{narrative['evidence']} {narrative['reason']}",
                f"CEO decision: {narrative['decision']}",
                f"48-hour move: {narrative['validation_test']}",
                f"Kill criterion: {narrative['kill_criterion']}",
            ]
        )
        lines.extend(
            f"{label}: {narrative[key]}"
            for label, key in (
                ("Why this wins today", "selection_reason"),
                ("First 10 customers", "first_10_customers"),
                ("Where to find them", "lead_sources"),
                ("Contact sequence", "contact_strategy"),
                ("Outreach message", "outreach_script"),
                ("Landing page", "landing_page"),
                ("Marketing content", "marketing_plan"),
                ("7-day scoreboard", "validation_scorecard"),
                ("Validation budget", "validation_budget"),
                ("Generated video", "generated_video_path"),
                ("Publishing blocker", "execution_blocker"),
            )
            if narrative[key]
        )
        if narrative["prospect_links"]:
            lines.append("First 10 customer links:")
            lines.extend(
                f"{index}. {item['label']}: {item['url']}"
                for index, item in enumerate(
                    narrative["prospect_links"], start=1
                )
            )
        if narrative["published_links"]:
            lines.append("Published campaign links:")
            lines.extend(
                f"{item['label']}: {item['url']}"
                for item in narrative["published_links"]
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
    if _collection_failed(result):
        return "NOT AVAILABLE"
    explicit = _normalize_decision(result.get("ceo_decision"))
    if explicit:
        return explicit
    narratives = _actionable_narratives(candidates)
    decisions = {item["decision"] for item in narratives}
    if "BUILD" in decisions:
        return "BUILD"
    if narratives:
        return "VALIDATE NOW"
    return "NO BET"


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
        return {
            "actionable": False,
            "opportunity": "No concrete opportunity identified",
            "problem": (
                "The source grouping does not describe one specific customer problem."
            ),
            "offer": "",
            "why_pay": "",
            "evidence": _evidence_summary(candidate),
            "alternatives": "",
            "wedge": "",
            "reason": (
                "The result does not state what to sell, who would buy it, or why "
                "they would pay."
            ),
            "decision": "REJECT",
            "confidence": "REJECTED",
            "validation_test": "",
            "kill_criterion": "",
            "selection_reason": "",
            "first_10_customers": "",
            "lead_sources": "",
            "contact_strategy": "",
            "outreach_script": "",
            "landing_page": "",
            "marketing_plan": "",
            "validation_scorecard": "",
            "validation_budget": "",
            "generated_video_path": "",
            "execution_blocker": "",
            "prospect_links": _prospect_links(candidate),
            "published_links": _published_links(candidate),
            "sources": _source_links(candidate),
        }
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
    offer = _first_text(
        candidate,
        "offer",
        "what_to_sell",
        "what_to_build",
        "smallest_paid_test",
    ) or f"A manually delivered paid pilot for {opportunity}."
    why_pay = _first_text(
        candidate,
        "why_pay",
        "why_they_pay",
        "willingness_to_pay",
    ) or (
        "They pay only if this removes a measurable cost, delay, risk, or "
        "revenue leak identified in the evidence."
    )
    wedge = _first_text(
        candidate,
        "wedge",
        "competitive_wedge",
        "why_we_win",
    ) or reason
    validation_test = _first_text(
        candidate,
        "validation_test",
        "next_action",
        "forty_eight_hour_move",
    ) or (
        f"Ask 10 target buyers to pay for a manually delivered {opportunity} "
        "pilot before building software."
    )
    kill_criterion = _first_text(
        candidate,
        "kill_criterion",
        "rejection_threshold",
    ) or "Kill it if fewer than 3 of 10 target buyers commit money."
    confidence = _first_text(candidate, "confidence") or _confidence(candidate)
    selection_reason = _first_text(
        candidate,
        "selection_reason",
        "why_this_wins_today",
        "portfolio_comparison",
    )
    first_10_customers = _display_value(
        candidate.get("first_10_customers")
        or candidate.get("first_customers")
        or candidate.get("ideal_customer")
    )
    lead_sources = _display_value(
        candidate.get("lead_sources")
        or candidate.get("where_to_find_customers")
    )
    contact_strategy = _display_value(
        candidate.get("contact_strategy")
        or candidate.get("outreach_sequence")
        or candidate.get("channels")
    )
    outreach_script = _first_text(
        candidate,
        "outreach_script",
        "first_message",
        "dm_script",
    )
    landing_page = _display_value(
        candidate.get("landing_page")
        or candidate.get("landing_page_brief")
    )
    marketing_plan = _display_value(
        candidate.get("marketing_plan")
        or candidate.get("content_plan")
    )
    validation_scorecard = _display_value(
        candidate.get("validation_scorecard")
        or candidate.get("seven_day_scorecard")
        or candidate.get("success_metrics")
    )
    validation_budget = _display_value(
        candidate.get("validation_budget")
        or candidate.get("budget")
    )
    generated_video_path = _first_text(
        candidate,
        "generated_video_path",
        "video_path",
    )
    execution_blocker = _first_text(
        candidate,
        "execution_blocker",
        "publishing_blocker",
    )
    return {
        "actionable": not abstract,
        "opportunity": opportunity,
        "problem": problem,
        "offer": offer,
        "why_pay": why_pay,
        "evidence": _evidence_summary(candidate),
        "alternatives": alternatives,
        "wedge": wedge,
        "reason": reason,
        "decision": decision,
        "confidence": confidence,
        "validation_test": validation_test,
        "kill_criterion": kill_criterion,
        "selection_reason": selection_reason,
        "first_10_customers": first_10_customers,
        "lead_sources": lead_sources,
        "contact_strategy": contact_strategy,
        "outreach_script": outreach_script,
        "landing_page": landing_page,
        "marketing_plan": marketing_plan,
        "validation_scorecard": validation_scorecard,
        "validation_budget": validation_budget,
        "generated_video_path": generated_video_path,
        "execution_blocker": execution_blocker,
        "prospect_links": _prospect_links(candidate),
        "published_links": _published_links(candidate),
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
        return "VALIDATE NOW"
    if classification in {
        "MALAYSIA_FIRST",
        "SEA_COUNTRY_SPECIFIC",
        "GLOBAL_ENGLISH",
    }:
        return "VALIDATE NOW"
    return "VALIDATE NOW"


def _normalize_decision(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("_", " ")
    aliases = {
        "BUILD": "BUILD",
        "NO BUILD": "NO BUILD",
        "RESEARCH": "RESEARCH MORE",
        "RESEARCH MORE": "RESEARCH MORE",
        "CONTINUE RESEARCH": "RESEARCH MORE",
        "VALIDATE": "VALIDATE NOW",
        "VALIDATE NOW": "VALIDATE NOW",
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
    if decision == "NOT AVAILABLE":
        return (
            "Next action: restore collection and rerun; do not invent a market "
            "decision from an empty research run."
        )
    narratives = _actionable_narratives(list(result.get("candidates") or []))
    if narratives:
        return f"Next action: {narratives[0]['validation_test']}"
    return (
        "Next action: expand product-specific pain searches and nominate one "
        "manually deliverable paid test on the next successful run."
    )


def _actionable_narratives(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        narrative
        for candidate in candidates
        if (narrative := _candidate_narrative(candidate))["actionable"]
    ]


def _confidence(candidate: dict[str, Any]) -> str:
    authors = int(candidate.get("independent_authors") or 0)
    payment = int(candidate.get("payment_or_usage_signals") or 0)
    if authors >= 5 and payment >= 2:
        return "STRONG"
    if authors >= 3 and payment >= 1:
        return "PROMISING"
    return "EARLY"


def _collection_failed(result: dict[str, Any]) -> bool:
    if result.get("collection_error"):
        return True
    stage_a = result.get("stage_a") or {}
    stage_c = result.get("stage_c") or {}
    records = int(stage_a.get("records") or 0) + int(stage_c.get("records") or 0)
    return (
        str(result.get("research_status") or "").upper() == "NOT_RESEARCHED"
        and records == 0
    )


def _workflow_name(result: dict[str, Any]) -> str:
    workflow = str(result.get("workflow") or "").lower()
    mode = str(result.get("mode") or "").lower()
    if workflow == "global_opportunity_dig" or mode == "global":
        return "Global Opportunity"
    if workflow == "daily_opportunity_commander":
        return "Daily Opportunity Commander"
    return "Global to Malaysia"


def _is_daily_commander(result: dict[str, Any]) -> bool:
    return (
        str(result.get("workflow") or "").lower()
        == "daily_opportunity_commander"
    )


def _actionable_headline(result: dict[str, Any], opportunity: str) -> str:
    if _is_daily_commander(result):
        return f"Hey Kenny — today's one company priority is: {opportunity}."
    return (
        f"{_workflow_name(result)} source candidate: {opportunity}. "
        "This is not a second simultaneous build; the 7:00 AM Daily Opportunity "
        "Commander selects one company-wide validation."
    )


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


def _prospect_links(candidate: dict[str, Any]) -> list[dict[str, str]]:
    raw_links = candidate.get("prospect_links") or []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_links:
        if isinstance(item, dict):
            raw_url = str(item.get("url") or item.get("href") or "").strip()
            label = str(
                item.get("label")
                or item.get("title")
                or item.get("company")
                or ""
            ).strip()
        else:
            raw_url = str(item).strip()
            label = ""
        canonical = _canonical_url(raw_url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        output.append(
            {
                "label": label or _descriptive_link_label(canonical),
                "url": canonical,
            }
        )
        if len(output) == 10:
            break
    return output


def _published_links(candidate: dict[str, Any]) -> list[dict[str, str]]:
    published = dict(candidate)
    published["prospect_links"] = candidate.get("published_links") or []
    return _prospect_links(published)


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


def _optional_html_paragraph(label: str, value: str) -> str:
    if not value:
        return ""
    return (
        f"<p><strong>{html.escape(label)}:</strong> "
        f"{html.escape(value)}</p>"
    )


def _first_not_none(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)
