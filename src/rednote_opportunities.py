from __future__ import annotations

import html
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv


DEFAULT_CAPTURE_PATH = Path(
    "data/raw/rednote_malaysia/opportunity_capture_latest.json"
)
DEFAULT_REPORT_DIR = Path("data/reports")
DEFAULT_STATE_PATH = Path("data/reports/rednote_malaysia_seen.json")

DEFAULT_QUERIES = [
    "马来西亚 求推荐",
    "马来西亚 找不到 app",
    "马来西亚 太贵 替代",
    "马来西亚 很麻烦 怎么办",
    "马来西亚 留学生 困扰",
    "马来西亚 小生意 痛点",
    "Malaysia recommend app",
    "Malaysia alternative too expensive",
]

MALAYSIA_TERMS = (
    "malaysia",
    "malaysian",
    "马来西亚",
    "大马",
    "吉隆坡",
    "新山",
    "槟城",
    "沙巴",
    "砂拉越",
    "rm",
    "myr",
)
DEMAND_TERMS = (
    "求推荐",
    "推荐",
    "有没有",
    "哪里找",
    "哪里买",
    "需要",
    "想要",
    "looking for",
    "recommend",
    "need a",
    "need an",
    "alternative",
)
PAIN_TERMS = (
    "找不到",
    "太贵",
    "麻烦",
    "困难",
    "踩雷",
    "避雷",
    "被骗",
    "失败",
    "等很久",
    "不好用",
    "不能",
    "没有",
    "frustrat",
    "too expensive",
    "difficult",
    "scam",
    "doesn't work",
    "cannot",
)
PAYMENT_TERMS = (
    "付费",
    "愿意付",
    "预算",
    "价格",
    "收费",
    "多少钱",
    "rm",
    "myr",
    "pay",
    "paid",
    "budget",
    "price",
    "cost",
)
PROMOTION_TERMS = (
    "全攻略",
    "必备",
    "大全",
    "一定要下载",
    "实用分享",
    "实用app",
    "app分享",
    "app总结",
    "国民级",
    "值得下载",
    "研究日记",
    "优惠码",
    "折扣码",
    "私信我",
    "合作",
    "广告",
    "sponsored",
    "promo code",
)

CATEGORY_RULES: list[dict[str, Any]] = [
    {
        "key": "part_time_work",
        "terms": ("parttime", "part time", "兼职", "找工", "工作平台"),
        "opportunity": "Verified part-time work marketplace for Malaysia",
        "customer": (
            "Students and hourly workers need trustworthy short-term jobs; employers "
            "need fast access to verified local applicants."
        ),
        "why_pay": (
            "Employers can pay per verified applicant or successful shift placement "
            "to reduce scams, no-shows, and screening time."
        ),
        "alternatives": "JobStreet, Hiredly, Indeed, Maukerja, and Facebook groups.",
        "offer": (
            "A concierge-backed marketplace that verifies employers and charges "
            "RM50 for each successfully filled shift."
        ),
        "wedge": (
            "Fast matching for Chinese-, Malay-, and English-speaking students, with "
            "employer verification and no-show protection."
        ),
        "validation": (
            "Contact 10 cafes, retailers, and event operators; offer one verified "
            "part-time hire for RM50."
        ),
        "kill": "Kill it if fewer than 3 of 10 employers agree to the RM50 offer.",
    },
    {
        "key": "student_arrival",
        "terms": ("留学", "留学生", "新生", "student", "campus"),
        "opportunity": "Malaysia newcomer concierge for international students",
        "customer": (
            "International students need one reliable workflow for SIM cards, banking, "
            "transport, housing setup, and local administration."
        ),
        "why_pay": (
            "Universities, accommodation operators, and students may pay to reduce "
            "arrival mistakes and support workload."
        ),
        "alternatives": (
            "University international offices, education agents, Grab, Touch 'n Go, "
            "and free RedNote guide posts."
        ),
        "offer": (
            "A RM99 arrival concierge that completes a student's first-week setup "
            "checklist through chat and vetted local partners."
        ),
        "wedge": (
            "One multilingual handoff spanning banking, SIM, transport, housing, and "
            "campus administration instead of disconnected guide posts."
        ),
        "validation": (
            "Offer the RM99 concierge to 10 incoming students and ask two education "
            "agents to distribute it."
        ),
        "kill": "Kill it if fewer than 3 students pay or reserve with a deposit.",
    },
    {
        "key": "vehicle_history",
        "terms": ("二手车", "车况", "事故车", "里程", "vehicle history", "used car"),
        "opportunity": "Clearer used-car risk reports for Malaysian buyers",
        "customer": (
            "Used-car buyers need understandable accident, mileage, ownership, and "
            "flood-risk information before paying a deposit."
        ),
        "why_pay": (
            "Buyers will pay when a report prevents a bad purchase, but defensibility "
            "requires privileged vehicle and insurance data."
        ),
        "alternatives": "SCRUT, OtoFacts, CarHistory.my, and mechanic inspections.",
        "offer": (
            "A RM29 plain-language interpretation and risk checklist layered on top "
            "of an existing vehicle-history report."
        ),
        "wedge": (
            "Explain claim severity, flood and mileage risk, and the exact questions "
            "a buyer should ask before paying a deposit."
        ),
        "validation": (
            "Sell 10 manual RM29 report interpretations before building any data product."
        ),
        "kill": (
            "Kill it if buyers will only pay for proprietary data that cannot be "
            "licensed economically."
        ),
    },
    {
        "key": "small_business_ops",
        "terms": (
            "小生意",
            "小商家",
            "摆摊",
            "开店",
            "invoice",
            "e-invoice",
            "small business",
        ),
        "opportunity": "Simple operations assistant for Malaysian microbusinesses",
        "customer": (
            "Solo sellers and micro-SMEs need lightweight invoicing, order tracking, "
            "payments, and compliance without an accounting team."
        ),
        "why_pay": (
            "They may subscribe if it saves weekly admin time and prevents payment or "
            "e-invoice mistakes."
        ),
        "alternatives": "AutoCount, SQL Account, Bukku, StoreHub, and spreadsheets.",
        "offer": (
            "A RM49/month WhatsApp-first admin assistant for orders, invoices, "
            "payment reminders, and e-invoice handoff."
        ),
        "wedge": (
            "Start as a service for microbusinesses that find accounting software too "
            "heavy, then automate only the repeated workflow."
        ),
        "validation": (
            "Recruit five Malaysian microbusinesses for a paid two-week concierge pilot."
        ),
        "kill": "Kill it if fewer than 2 of 5 businesses pay RM49 for the pilot.",
    },
    {
        "key": "personal_finance",
        "terms": (
            "记账",
            "存钱",
            "预算管理",
            "expense tracker",
            "budget app",
            "personal finance",
        ),
        "opportunity": "Malaysia-first multilingual money and expense tracker",
        "customer": (
            "Malaysian consumers want simple expense tracking that understands local "
            "banks, e-wallets, RM spending, and Chinese, Malay, and English labels."
        ),
        "why_pay": (
            "Users may subscribe for automatic local transaction categorisation, "
            "shared household budgets, and measurable savings."
        ),
        "alternatives": "MAE, GXBank, Money Lover, Spendee, YNAB, and spreadsheets.",
        "offer": (
            "A RM15/month multilingual expense tracker with Malaysian bank and "
            "e-wallet categories plus a weekly savings coach."
        ),
        "wedge": (
            "Local transaction language, household sharing, and advice that reflects "
            "Malaysian banks, e-wallets, and spending patterns."
        ),
        "validation": (
            "Manually onboard 10 users from the evidence into a spreadsheet-backed "
            "RM15/month savings pilot."
        ),
        "kill": "Kill it if fewer than 3 of 10 users pay after a seven-day trial.",
    },
    {
        "key": "rental_housing",
        "terms": (
            "租房",
            "房东",
            "押金",
            "中介",
            "room rental",
            "rent malaysia",
            "landlord",
            "deposit scam",
        ),
        "opportunity": "Verified rental handover and deposit protection for Malaysia",
        "customer": (
            "Students, young workers, and landlords need proof of property condition, "
            "clear handover records, and safer deposit handling."
        ),
        "why_pay": (
            "Tenants and landlords may pay to prevent deposit disputes, scams, and "
            "costly damage arguments."
        ),
        "alternatives": "PropertyGuru, iProperty, SPEEDHOME, agents, and WhatsApp records.",
        "offer": (
            "A RM79 move-in evidence pack with identity checks, timestamped condition "
            "photos, meter readings, and a signed handover record."
        ),
        "wedge": (
            "Focus narrowly on dispute prevention after a tenant has already found a room."
        ),
        "validation": (
            "Sell five manual RM79 move-in evidence packs near one university."
        ),
        "kill": "Kill it if neither tenants nor landlords will pay before key handover.",
    },
    {
        "key": "home_services",
        "terms": (
            "水管",
            "维修",
            "清洁",
            "冷气",
            "装修",
            "找师傅",
            "plumber",
            "cleaner",
            "aircon service",
            "home repair",
        ),
        "opportunity": "Fixed-price trusted home-service booking for Malaysia",
        "customer": (
            "Households need reliable cleaners and repair technicians without opaque "
            "pricing, slow replies, or uncertain workmanship."
        ),
        "why_pay": (
            "Customers will pay a booking premium for verified providers, fixed scopes, "
            "and a service guarantee."
        ),
        "alternatives": "Recommend.my, Kaodim alternatives, local Facebook groups, and contractors.",
        "offer": (
            "A RM20 booking fee for one fixed-scope service with photo proof and a "
            "seven-day workmanship guarantee."
        ),
        "wedge": "Start with one painful job category and one city instead of a broad marketplace.",
        "validation": "Manually fulfil 10 paid bookings in one Kuala Lumpur neighbourhood.",
        "kill": "Kill it if gross margin after provider payout is below RM20 per job.",
    },
    {
        "key": "social_commerce",
        "terms": (
            "小红书卖家",
            "直播卖货",
            "网店",
            "订单",
            "库存",
            "social commerce",
            "online seller",
            "order tracking",
        ),
        "opportunity": "WhatsApp order operations for Malaysian social sellers",
        "customer": (
            "Small RedNote, TikTok, and Instagram sellers need to turn chats into paid "
            "orders without losing inventory and follow-ups."
        ),
        "why_pay": (
            "Sellers may pay when the workflow recovers missed orders and removes daily "
            "manual reconciliation."
        ),
        "alternatives": "EasyStore, SiteGiant, Shopify, StoreHub, and spreadsheets.",
        "offer": (
            "A RM79/month assisted inbox that records chat orders, confirms payment, "
            "updates inventory, and reminds unpaid buyers."
        ),
        "wedge": "Serve chat-first micro-sellers who are not ready to operate a full storefront.",
        "validation": "Run the workflow manually for five sellers for two weeks at RM79.",
        "kill": "Kill it if the pilot does not recover at least RM79 in missed orders per seller.",
    },
]


def run_rednote_opportunity_dig(
    capture_path: Path = DEFAULT_CAPTURE_PATH,
    *,
    report_dir: Path = DEFAULT_REPORT_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
    send_email: bool = True,
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    report = analyze_rednote_capture(capture, state_path=state_path)
    paths = write_rednote_report(report, report_dir)
    report["report_paths"] = {key: str(value) for key, value in paths.items()}
    notification = (
        send_rednote_report(report, post=post)
        if send_email
        else {"status": "skipped", "reason": "email disabled"}
    )
    report["notification"] = notification
    return report


def analyze_rednote_capture(
    capture: dict[str, Any],
    *,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    raw_rows = _capture_rows(capture)
    records_collected = len(raw_rows)
    unique_rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in raw_rows:
        url = _canonical_url(str(row.get("url") or ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        normalized = dict(row)
        normalized["url"] = url
        unique_rows.append(normalized)

    previous = _read_seen(state_path)
    new_urls = seen_urls - previous
    candidates = _build_candidates(unique_rows)
    collection_error = str(capture.get("collection_error") or "").strip() or None
    if collection_error and not unique_rows:
        decision = "NOT AVAILABLE"
    elif any(item["decision"] == "BUILD" for item in candidates):
        decision = "BUILD"
    elif candidates:
        decision = "VALIDATE NOW"
    else:
        decision = "NO BUILD"

    next_action = _next_action(decision, collection_error, candidates)
    report = {
        "workflow": "rednote_malaysia_opportunity_dig",
        "generated_at": capture.get("generated_at")
        or datetime.now(timezone.utc).isoformat(),
        "research_status": "FAILED"
        if collection_error and not unique_rows
        else "COMPLETE",
        "collection_error": collection_error,
        "ceo_decision": decision,
        "records_collected": records_collected,
        "unique_posts": len(unique_rows),
        "new_since_previous_run": len(new_urls),
        "collection_cost_usd": 0.0,
        "queries_run": len((capture.get("queries") or {})),
        "best_bet": candidates[0] if candidates else None,
        "candidates": candidates[:3],
        "next_action": next_action,
    }
    _write_seen(state_path, seen_urls)
    return report


def write_rednote_report(
    report: dict[str, Any],
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "rednote_malaysia_latest.json"
    md_path = report_dir / "rednote_malaysia_latest.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_text_report(report) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def send_rednote_report(
    report: dict[str, Any],
    *,
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("RESEND_FROM_EMAIL", "").strip()
    to_email = os.getenv("RESEND_ALERT_TO_EMAIL", "").strip()
    if not api_key or not from_email or not to_email:
        return {"status": "skipped", "reason": "missing Resend email configuration"}

    decision = str(report.get("ceo_decision") or "NOT AVAILABLE")
    subject = (
        "[CariLead RedNote] RESEARCH RUN FAILED - Malaysia"
        if decision == "NOT AVAILABLE"
        else (
            f"[CariLead RedNote] SOURCE CANDIDATE - "
            f"{(report.get('best_bet') or {}).get('opportunity')}"
            if report.get("best_bet")
            else "[CariLead RedNote] NO BET FOUND - Malaysia"
        )
    )
    payload = {
        "from": f"CariLead Alerts <{from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": _html_report(report),
        "text": _text_report(report),
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
    return {
        "status": "sent",
        "email_id": response_payload.get("id"),
        "recipient": to_email,
        "subject": subject,
    }


def _build_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        evidence_text = _row_text(row)
        query = str(row.get("query") or "").lower()
        if not _contains_any(evidence_text, MALAYSIA_TERMS) and not _contains_any(
            query, MALAYSIA_TERMS
        ):
            continue
        if _contains_any(evidence_text, PROMOTION_TERMS) and not _contains_any(
            evidence_text, DEMAND_TERMS
        ):
            continue
        category = next(
            (
                rule
                for rule in CATEGORY_RULES
                if _contains_any(evidence_text, rule["terms"])
            ),
            None,
        )
        if not category:
            continue
        enriched = dict(row)
        enriched["_demand"] = _term_count(evidence_text, DEMAND_TERMS)
        enriched["_pain"] = _term_count(evidence_text, PAIN_TERMS)
        enriched["_payment"] = _term_count(evidence_text, PAYMENT_TERMS)
        enriched["_score"] = (
            enriched["_demand"] * 3
            + enriched["_pain"] * 3
            + enriched["_payment"] * 4
            + min(5, math.log10(max(1, _engagement(row)) + 1))
        )
        grouped.setdefault(category["key"], []).append(enriched)

    output: list[dict[str, Any]] = []
    rules = {item["key"]: item for item in CATEGORY_RULES}
    for key, evidence in grouped.items():
        evidence.sort(key=lambda item: item["_score"], reverse=True)
        rule = rules[key]
        sources = [
            {
                "title": _clean(str(item.get("title") or "RedNote discussion"))[
                    :140
                ],
                "url": item["url"],
            }
            for item in evidence[:3]
        ]
        demand = sum(int(item["_demand"] > 0) for item in evidence)
        pain = sum(int(item["_pain"] > 0) for item in evidence)
        payment = sum(int(item["_payment"] > 0) for item in evidence)
        independent = len(
            {
                str(item.get("author") or item["url"])
                for item in evidence
            }
        )
        if demand + pain + payment == 0:
            continue
        build = (
            independent >= 5 and demand >= 3 and pain >= 3 and payment >= 2
        )
        decision = "BUILD" if build else "VALIDATE NOW"
        confidence = (
            "STRONG"
            if build
            else "PROMISING"
            if independent >= 3 and demand + pain >= 3
            else "EARLY"
        )
        if build:
            reason = (
                f"{independent} independent RedNote posts include {demand} explicit "
                f"demand signals, {pain} pain signals, and {payment} payment signals. "
                "This clears the initial evidence gate, but paid validation is still required."
            )
        else:
            reason = (
                f"The batch has {independent} independent post(s), {demand} explicit "
                f"demand signal(s), {pain} pain signal(s), and {payment} payment "
                "signal(s). It does not yet prove repeated willingness to pay and a "
                "defensible gap against the named alternatives."
            )
        output.append(
            {
                "opportunity": rule["opportunity"],
                "customer_problem": rule["customer"],
                "why_pay": rule["why_pay"],
                "competitors": rule["alternatives"],
                "offer": rule["offer"],
                "wedge": rule["wedge"],
                "validation_test": rule["validation"],
                "kill_criterion": rule["kill"],
                "decision_reason": reason,
                "decision": decision,
                "confidence": confidence,
                "evidence_records": len(evidence),
                "independent_authors": independent,
                "payment_signals": payment,
                "sources": sources,
                "score": round(sum(float(item["_score"]) for item in evidence), 2),
            }
        )
    return sorted(output, key=lambda item: item["score"], reverse=True)


def _text_report(report: dict[str, Any]) -> str:
    decision = str(report.get("ceo_decision") or "NOT AVAILABLE")
    if decision == "NOT AVAILABLE":
        opening = (
            "Research run failed. CEO decision: NOT AVAILABLE. "
            "No market conclusion was made from an empty collection."
        )
    elif report.get("best_bet"):
        opening = (
            "RedNote source candidate: "
            f"{report['best_bet']['opportunity']}. This is not a second "
            "simultaneous build; the 7:00 AM Daily Opportunity Commander "
            "selects one company-wide validation."
        )
    else:
        opening = "Hey Kenny — no concrete bet survived this collection."
    lines = [
        opening,
        f"CEO move: {decision}.",
        "",
        f"{report.get('records_collected', 0)} RedNote cards collected.",
        f"{report.get('unique_posts', 0)} unique posts.",
        f"{report.get('new_since_previous_run', 0)} were new versus the previous run.",
        "Collection cost: $0.00000 (logged-in browser; no Apify).",
    ]
    if report.get("collection_error"):
        lines.extend(["", f"Collection failure: {report['collection_error']}"])
    candidates = list(report.get("candidates") or [])
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                "",
                (
                    "TODAY'S BET"
                    if index == 1
                    else f"BACKUP BET {index - 1}"
                )
                + f": {candidate['opportunity']}",
                f"Buyer and pain: {candidate['customer_problem']}",
                f"What to sell now: {candidate['offer']}",
                f"Why they pay: {candidate['why_pay']}",
                f"Competitors: {candidate['competitors']}",
                f"Our wedge: {candidate['wedge']}",
                f"Evidence quality: {candidate['confidence']}. "
                f"{candidate['decision_reason']}",
                f"CEO decision: {candidate['decision']}.",
                f"48-hour move: {candidate['validation_test']}",
                f"Kill criterion: {candidate['kill_criterion']}",
            ]
        )
        for source in candidate.get("sources") or []:
            lines.append(f"{source['title']}: {source['url']}")
    lines.extend(["", str(report.get("next_action") or "")])
    return "\n".join(lines)


def _html_report(report: dict[str, Any]) -> str:
    text = _text_report(report)
    paragraphs: list[str] = []
    for line in text.splitlines():
        if not line:
            paragraphs.append("<br>")
            continue
        match = re.match(r"(.+): (https?://\S+)$", line)
        if match:
            paragraphs.append(
                '<p><a href="{url}">{title}</a></p>'.format(
                    url=html.escape(match.group(2), quote=True),
                    title=html.escape(match.group(1)),
                )
            )
        else:
            paragraphs.append(f"<p>{html.escape(line)}</p>")
    return (
        '<div style="font-family:Arial,sans-serif;max-width:700px;margin:auto;'
        'color:#334155;line-height:1.5">'
        + "".join(paragraphs)
        + "</div>"
    )


def _next_action(
    decision: str,
    collection_error: str | None,
    candidates: list[dict[str, Any]],
) -> str:
    if decision == "NOT AVAILABLE":
        return (
            "Next action: restore the logged-in RedNote browser connection and rerun; "
            "do not make a product decision from this failed collection."
        )
    if decision == "BUILD":
        return f"Next action: {candidates[0]['validation_test']}"
    if decision == "VALIDATE NOW":
        return f"Next action: {candidates[0]['validation_test']}"
    return (
        "Next action: do not build from this batch; broaden the Malaysia pain and "
        "alternative searches before the next run."
    )


def _capture_rows(capture: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    queries = capture.get("queries") or {}
    if isinstance(queries, dict):
        for query, values in queries.items():
            for raw in values if isinstance(values, list) else []:
                if isinstance(raw, dict):
                    row = dict(raw)
                    row.setdefault("query", query)
                    rows.append(row)
    for raw in capture.get("records") or []:
        if isinstance(raw, dict):
            rows.append(dict(raw))
    return rows


def _read_seen(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(value) for value in payload.get("urls") or []}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()


def _write_seen(path: Path, urls: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "urls": sorted(urls),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _canonical_url(value: str) -> str:
    if not value.startswith(("https://", "http://")):
        return ""
    parts = urlsplit(value)
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
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


def _row_text(row: dict[str, Any]) -> str:
    comments = row.get("comments") or []
    if isinstance(comments, list):
        comments_text = " ".join(
            str(item.get("text") if isinstance(item, dict) else item)
            for item in comments[:20]
        )
    else:
        comments_text = str(comments)
    return _clean(
        " ".join(
            str(row.get(key) or "")
            for key in ("title", "body", "card_text", "snippet")
        )
        + " "
        + comments_text
    ).lower()


def _engagement(row: dict[str, Any]) -> int:
    value = row.get("engagement") or row.get("likes") or 0
    text = str(value).strip().lower()
    multiplier = 1000 if text.endswith("k") else 1
    text = text.rstrip("k").replace(",", "")
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _term_count(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
