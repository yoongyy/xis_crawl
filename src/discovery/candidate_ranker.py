from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from ..research_models import EvidenceFinding


@dataclass
class CandidateAssessment:
    problem_key: str
    classification: str
    recommendation: str
    problem_evidence_score: float
    solution_demand_score: float
    payment_evidence_score: float
    market_gap_score: float
    crowding_score: float
    risk_score: float
    independent_authors: int
    independent_threads: int
    independent_platforms: int
    rationale: list[str]


class CandidateRanker:
    def assess(
        self,
        problem_key: str,
        findings: Iterable[EvidenceFinding],
        competitor_count: int = 0,
        trend_classification: str = "insufficient_data",
        risk_flags: int = 0,
    ) -> CandidateAssessment:
        valid = [f for f in findings if f.verification_status == "verified" and f.organic_evidence_weight > 0]
        # One author contributes at most two findings; one thread contributes at most three.
        authors, threads, source_counts = Counter(), Counter(), Counter()
        independent = []
        for f in sorted(valid, key=lambda x: (x.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True):
            author = f.author_hash or f"unknown:{f.source_id}"
            thread = f"{f.source}:{f.thread_id or f.source_id}"
            if authors[author] >= 2 or threads[thread] >= 3:
                continue
            if f.source == "hacker_news" and source_counts[f.source] >= 10:
                continue
            authors[author] += 1
            threads[thread] += 1
            source_counts[f.source] += 1
            independent.append(f)
        types = Counter(f.evidence_type for f in independent)
        platforms = {f.source for f in independent}
        personal = sum(f.personal_experience for f in independent)
        recent = sum(
            bool(f.published_at and (datetime.now(timezone.utc) - _aware(f.published_at)).days <= 365)
            for f in independent
        )
        problem = min(100.0, len(threads) * 3 + len(authors) * 2 + personal * 2 + recent + len(platforms) * 5)
        solution = min(100.0, (
            types["active_solution_search"] * 8 + types["recommendation_request"] * 7 +
            types["explicit_wish"] * 5 + types["missing_feature_request"] * 6 +
            types["workaround"] * 3
        ))
        payment = min(100.0, (
            types["current_paid_solution"] * 10 + types["explicit_price"] * 5 +
            types["willingness_to_pay"] * 8 + types["refund"] * 5 +
            types["cancellation"] * 5
        ))
        gap = min(100.0, types["missing_feature_request"] * 8 + types["explicit_problem"] * 2)
        crowding = min(100.0, competitor_count * 7)
        risk = min(100.0, risk_flags * 15 + (20 if trend_classification == "temporary_spike" else 0))
        rationale = [
            f"{len(authors)} capped independent authors across {len(threads)} threads and {len(platforms)} platforms",
            f"{types['active_solution_search'] + types['recommendation_request']} active solution/recommendation requests",
            f"{types['current_paid_solution'] + types['explicit_price']} current-payment or explicit-price signals",
        ]
        if trend_classification == "temporary_spike":
            classification, recommendation = "temporary_trend", "temporary_trend"
        elif crowding >= 70 and gap < 30:
            classification, recommendation = "crowded_market", "too_crowded"
        elif len(threads) >= 30 and len(authors) >= 20 and len(platforms) >= 2 and solution >= 30:
            classification = "verified_problem"
            recommendation = "strong_candidate" if payment >= 30 and gap >= 25 and risk < 40 else "investigate_further"
        elif len(threads) >= 10 and solution >= 15:
            classification, recommendation = "promising_hypothesis", "investigate_further"
        elif payment < 10 and len(threads) >= 5:
            classification, recommendation = "weak_signal", "weak_payment_evidence"
        elif len(threads) < 3:
            classification, recommendation = "insufficient_evidence", "reject"
        else:
            classification, recommendation = "weak_signal", "investigate_further"
        return CandidateAssessment(
            problem_key, classification, recommendation, problem, solution, payment,
            gap, crowding, risk, len(authors), len(threads), len(platforms), rationale,
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
