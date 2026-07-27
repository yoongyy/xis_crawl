from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv


DEFAULT_STATE_PATH = Path("data/reports/global_to_malaysia_email_state.json")


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

    subject = (
        f"[CariLead] {len(candidates)} opportunity candidate"
        f"{'' if len(candidates) == 1 else 's'} found - Global to Malaysia"
    )
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
    cards = []
    for candidate in candidates:
        links = "".join(
            f'<li><a href="{html.escape(str(link), quote=True)}">'
            f"{html.escape(str(link))}</a></li>"
            for link in (candidate.get("links") or [])[:3]
        )
        cards.append(
            """
            <div style="border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin:14px 0">
              <h3 style="margin:0 0 10px;color:#0f172a">{name}</h3>
              <p><strong>Classification:</strong> {classification}</p>
              <p><strong>Research status:</strong> {status}</p>
              <p><strong>Independent authors:</strong> {authors}</p>
              <p><strong>Payment/usage signals:</strong> {payment}</p>
              <p><strong>Malaysia evidence records:</strong> {malaysia}</p>
              <p><strong>Why it matters:</strong> {rationale}</p>
              {links_section}
            </div>
            """.format(
                name=html.escape(str(candidate.get("candidate_key") or "Unnamed candidate")),
                classification=html.escape(str(candidate.get("classification") or "Unclassified")),
                status=html.escape(str(candidate.get("research_status") or "Unknown")),
                authors=html.escape(str(candidate.get("independent_authors") or 0)),
                payment=html.escape(str(candidate.get("payment_or_usage_signals") or 0)),
                malaysia=html.escape(str(candidate.get("malaysia_evidence_records") or 0)),
                rationale=html.escape(str(candidate.get("rationale") or "No rationale recorded")),
                links_section=f"<p><strong>Sources:</strong></p><ul>{links}</ul>" if links else "",
            )
        )
    generated_at = html.escape(str(result.get("generated_at") or "unknown"))
    research_status = html.escape(str(result.get("research_status") or "unknown"))
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#334155">
      <h2 style="color:#0f172a">CariLead opportunity alert</h2>
      <p>The Global-to-Malaysia dig found {len(candidates)} candidate(s) for review.</p>
      <p><strong>Overall research status:</strong> {research_status}<br>
         <strong>Generated:</strong> {generated_at}</p>
      {''.join(cards)}
      <p style="font-size:12px;color:#64748b">
        Candidates are research signals, not guaranteed commercial opportunities.
      </p>
    </div>
    """


def _text_email(result: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    lines = [
        "CariLead opportunity alert",
        "",
        f"Overall research status: {result.get('research_status') or 'unknown'}",
        f"Generated: {result.get('generated_at') or 'unknown'}",
        "",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"{index}. {candidate.get('candidate_key') or 'Unnamed candidate'}",
                f"Classification: {candidate.get('classification') or 'Unclassified'}",
                f"Research status: {candidate.get('research_status') or 'Unknown'}",
                f"Independent authors: {candidate.get('independent_authors') or 0}",
                f"Payment/usage signals: {candidate.get('payment_or_usage_signals') or 0}",
                f"Malaysia evidence records: {candidate.get('malaysia_evidence_records') or 0}",
                f"Why it matters: {candidate.get('rationale') or 'No rationale recorded'}",
            ]
        )
        lines.extend(f"Source: {link}" for link in (candidate.get("links") or [])[:3])
        lines.append("")
    lines.append("Candidates are research signals, not guaranteed commercial opportunities.")
    return "\n".join(lines)
