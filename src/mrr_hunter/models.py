from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class MRRPostCandidate(BaseModel):
    post_id: str
    title: str
    content: str
    author_name: str
    author_id: Optional[str] = None
    url: str
    likes: int = 0
    collects: int = 0
    comments: int = 0
    engagement_score: int = 0
    query: str
    published_at: Optional[str] = None
    extracted_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # Revenue Filter Attributes
    is_mrr_candidate: bool = False
    revenue_score: int = 0
    matched_keywords: List[str] = Field(default_factory=list)
    revenue_snippets: List[str] = Field(default_factory=list)


class MRRHunterSummary(BaseModel):
    timestamp: str
    total_searched: int
    total_candidates: int
    queries_executed: List[str]
    output_json_path: str
    output_csv_path: str
