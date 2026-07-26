from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from ..research_models import EvidenceFinding, SourceRecord
from .language_patterns import (
    CANCELLATION, DISSATISFACTION, HYPOTHETICAL, PAYMENT_CURRENT, PROBLEM,
    PROMOTION, REFUND, SOLUTION, SWITCH, UNINSTALL, WILLINGNESS,
)

PRICE_RE = re.compile(
    r"(?:(?P<currency>US\$|USD|\$)\s?(?P<amount>\d+(?:\.\d{1,2})?)|"
    r"(?P<amount2>\d+(?:\.\d{1,2})?)\s?(?P<currency2>USD|dollars?))",
    re.I,
)


class RulesEvidenceClassifier:
    prompt_version = "rules-v1"

    def classify(self, record: SourceRecord, problem_category: str | None = None) -> list[EvidenceFinding]:
        text = " ".join(part for part in (record.title, record.body) if part).strip()
        if not text:
            return []
        lowered = text.lower()
        # Store listings and Product Hunt product records are first-party
        # positioning/competitor metadata, never independent consumer demand.
        promotional = (
            record.source_type in {"app", "product"}
            or any(p in lowered for p in PROMOTION)
        )
        types: list[str] = []
        if any(p in lowered for p in PROBLEM) or (record.rating is not None and record.rating <= 3):
            types.append("explicit_problem")
        if any(p in lowered for p in SOLUTION):
            types.append("recommendation_request" if ("recommend" in lowered or "what app" in lowered) else "active_solution_search")
        if "i wish" in lowered or "somebody should make" in lowered:
            types.append("explicit_wish")
        if any(p in lowered for p in DISSATISFACTION):
            types.append("missing_feature_request" if ("missing feature" in lowered or "no android" in lowered or "no iphone" in lowered) else "explicit_problem")
        if any(p in lowered for p in PAYMENT_CURRENT):
            types.append("current_paid_solution")
        if any(p in lowered for p in WILLINGNESS):
            types.append("willingness_to_pay")
        if any(p in lowered for p in CANCELLATION):
            types.append("cancellation")
        if any(p in lowered for p in REFUND):
            types.append("refund")
        if any(p in lowered for p in UNINSTALL):
            types.append("uninstall")
        if any(p in lowered for p in SWITCH):
            types.append("switch")
        if "workaround" in lowered or "manually" in lowered:
            types.append("workaround")
        if promotional:
            types.append("promotion")
            types.append("maker_claim")
        if record.rating is not None and record.rating >= 4 and not promotional:
            types.append("positive_review")
            types.append("counterexample")
        personal = bool(re.search(r"\b(i|my|me|we|our)\b", lowered))
        if personal and not promotional and any(
            kind in types for kind in (
                "explicit_problem", "active_solution_search", "recommendation_request",
                "current_paid_solution", "cancellation", "refund", "uninstall",
                "switch", "workaround",
            )
        ):
            types.append("personal_experience")
        if not types and any(p in lowered for p in HYPOTHETICAL):
            types.append("hypothetical_idea")
        if not types:
            return []
        price = PRICE_RE.search(text)
        if price and "explicit_price" not in types:
            types.append("explicit_price")
        unique_types = list(dict.fromkeys(types))
        author_hash = hashlib.sha256(f"{record.source}:{record.author_id or record.author_public_name or ''}".encode()).hexdigest() if (record.author_id or record.author_public_name) else None
        findings = []
        for evidence_type in unique_types:
            finding_id = hashlib.sha256(f"{record.source}:{record.source_id}:{evidence_type}:{text}".encode()).hexdigest()
            amount = price.group("amount") or price.group("amount2") if price else None
            currency = price.group("currency") or price.group("currency2") if price else None
            findings.append(EvidenceFinding(
                finding_id=finding_id, source=record.source, source_id=record.source_id,
                source_url=record.canonical_url, source_record_type=record.source_type,
                published_at=record.published_at,
                country="United States" if record.country_signal in {"US", "US-storefront", "US-search"} else None,
                author_hash=author_hash, thread_id=record.thread_id, evidence_text=text,
                evidence_type=evidence_type, problem_category=problem_category,
                problem_description=text if evidence_type in {"explicit_problem", "personal_experience"} else None,
                current_solution=(record.app_name or record.product_name) if record.source_type == "review" else None,
                workaround=text if evidence_type == "workaround" else None,
                competitor_or_product=record.app_name or record.product_name,
                missing_feature=text if evidence_type == "missing_feature_request" else None,
                desired_outcome=text if evidence_type in {"active_solution_search", "recommendation_request", "explicit_wish"} else None,
                purchase_statement=text if evidence_type == "current_paid_solution" else None,
                current_spending_statement=text if evidence_type in {"current_paid_solution", "explicit_price"} else None,
                price_amount=Decimal(amount) if amount else None, currency="USD" if currency else None,
                billing_period=_billing_period(lowered),
                willingness_to_pay_statement=text if evidence_type == "willingness_to_pay" else None,
                cancellation_statement=text if evidence_type == "cancellation" else None,
                refund_statement=text if evidence_type == "refund" else None,
                uninstall_statement=text if evidence_type == "uninstall" else None,
                switching_statement=text if evidence_type == "switch" else None,
                personal_experience=personal,
                emotional_intensity=min(1.0, sum(lowered.count(x) for x in ("hate", "frustrat", "tired", "anxious", "!")) * 0.2),
                organic_evidence_weight=0.0 if promotional else (0.3 if record.not_us_validation else 0.8),
                promotional_probability=0.9 if promotional else 0.05,
                relevance_score=0.8 if evidence_type not in {"promotion", "hypothetical_idea"} else 0.2,
                confidence=0.85 if evidence_type not in {"explicit_problem", "missing_feature_request"} else 0.7,
                prompt_version=self.prompt_version,
            ))
        return findings


def _billing_period(text: str) -> str | None:
    for value, aliases in {
        "monthly": ("per month", "/month", "monthly"),
        "annual": ("per year", "/year", "yearly", "annual"),
        "weekly": ("per week", "/week", "weekly"),
        "one_time": ("one-time", "one time", "lifetime"),
    }.items():
        if any(alias in text for alias in aliases):
            return value
    return None
