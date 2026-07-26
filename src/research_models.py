from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


SourceStatus = Literal[
    "available", "unavailable", "optional", "manual-import-only", "temporarily failing"
]
EvidenceType = Literal[
    "explicit_problem", "personal_experience", "active_solution_search",
    "recommendation_request", "explicit_wish", "missing_feature_request",
    "current_paid_solution", "explicit_price", "willingness_to_pay", "cancellation",
    "refund", "uninstall", "switch", "workaround", "repeated_manual_work",
    "commercial_loss", "positive_review", "counterexample", "general_opinion",
    "promotion", "maker_claim", "hypothetical_idea",
]
OpportunityClass = Literal[
    "verified_problem", "promising_hypothesis", "weak_signal", "crowded_market",
    "temporary_trend", "insufficient_evidence", "reject",
]
Recommendation = Literal[
    "investigate_further", "run_manual_price_test", "strong_candidate", "too_crowded",
    "weak_payment_evidence", "temporary_trend", "high_risk", "reject",
]


class SourceRecord(BaseModel):
    source: str
    source_type: str
    source_id: str
    canonical_url: str
    title: str | None = None
    body: str | None = None
    author_public_name: str | None = None
    author_id: str | None = Field(default=None, exclude=True)
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    country_signal: str | None = None
    language: str = "unknown"
    score_or_votes: float | None = None
    comment_count: int | None = None
    rating: float | None = None
    app_name: str | None = None
    product_name: str | None = None
    query: str | None = None
    search_rank: int | None = None
    raw_json_path: str | None = None
    extraction_confidence: float = 1.0
    extraction_warnings: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    parent_id: str | None = None
    market_role: str | None = None
    default_market: str | None = None
    not_us_validation: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict, exclude=True)


class EvidenceFinding(BaseModel):
    finding_id: str
    source: str
    source_id: str
    source_url: str
    source_record_type: str
    published_at: datetime | None = None
    country: str | None = None
    market: str = "United States"
    author_hash: str | None = None
    thread_id: str | None = None
    evidence_text: str
    evidence_type: EvidenceType
    problem_category: str | None = None
    problem_description: str | None = None
    affected_person: str | None = None
    situation_or_trigger: str | None = None
    current_solution: str | None = None
    workaround: str | None = None
    competitor_or_product: str | None = None
    missing_feature: str | None = None
    desired_outcome: str | None = None
    purchase_statement: str | None = None
    current_spending_statement: str | None = None
    price_amount: Decimal | None = None
    currency: str | None = None
    billing_period: str | None = None
    willingness_to_pay_statement: str | None = None
    cancellation_statement: str | None = None
    refund_statement: str | None = None
    uninstall_statement: str | None = None
    switching_statement: str | None = None
    switching_from: str | None = None
    switching_to: str | None = None
    urgency: str | None = None
    emotional_intensity: float = 0.0
    frequency_claim: str | None = None
    commercial_consequence: str | None = None
    personal_experience: bool = False
    organic_evidence_weight: float = 0.5
    promotional_probability: float = 0.0
    relevance_score: float = 0.5
    confidence: float = 0.5
    verification_status: str = "unverified"
    verification_notes: str | None = None
    prompt_version: str = "rules-v1"


class CompetitorProduct(BaseModel):
    name: str
    platform: str
    official_url: str
    category: str | None = None
    current_price: Decimal | None = None
    price_currency: str | None = None
    price_type: str | None = None
    price_checked_at: datetime | None = None
    price_source_url: str | None = None
    free_tier: bool | None = None
    rating: float | None = None
    review_count: int | None = None
    last_updated: datetime | None = None
    key_features: list[str] = Field(default_factory=list)
    commonly_praised: list[str] = Field(default_factory=list)
    common_complaints: list[str] = Field(default_factory=list)
    missing_features: list[str] = Field(default_factory=list)
    cancellation_reasons: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    source_confidence: float = 0.0

    def verified_price(self) -> bool:
        return bool(self.current_price is not None and self.price_source_url and self.price_checked_at)


class PlannedQuery(BaseModel):
    source: str
    query: str
    purpose: str
    priority: int
    expected_value: float
    maximum_results: int = Field(ge=1, le=100)
    freshness_window_days: int = Field(ge=1)


class ResearchPack(BaseModel):
    slug: str
    name: str
    market: dict[str, Any]
    research_questions: list[str]
    keywords: list[str]
    competitor_categories: list[str] = Field(default_factory=list)
    initial_domains: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class CrawlOptions(BaseModel):
    recent_days: int = 365
    max_records: int = 100
    max_comments: int = 500
    max_reddit_comments: int = 500
    max_youtube_comments: int = 300
    max_reviews: int = 300
    max_competitors: int = 15
    max_runtime_minutes: int = 90
    incremental: bool = True
    resume: bool = False
    force_refresh: bool = False
    delay_seconds: float = 1.0
    nested_comment_depth: int = 2
    sort: str = "relevance"
    subreddit_allowlist: list[str] = Field(default_factory=list)
    subreddit_denylist: list[str] = Field(default_factory=list)
