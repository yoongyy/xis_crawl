from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TargetNiche(str, Enum):
    INSURANCE = "insurance"
    FREELANCE_DEV = "freelance_dev"
    DESIGN_MARKETING = "design_marketing"
    GENERAL_SERVICES = "general_services"


class CommercialLead(BaseModel):
    lead_id: str
    niche: TargetNiche
    title: str
    content: str
    author_name: str
    author_id: Optional[str] = None
    url: str
    location_tag: Optional[str] = None
    published_at: Optional[str] = None
    extracted_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # Commercial Intent Scoring
    intent_score: int = 0  # 1-10 scale
    matched_keywords: List[str] = Field(default_factory=list)
    suggested_reply: str = ""
    is_high_intent: bool = False


class ScannerRunSummary(BaseModel):
    timestamp: str
    niche: TargetNiche
    total_posts_scanned: int
    high_intent_leads_found: int
    output_json_path: str
    output_csv_path: str
