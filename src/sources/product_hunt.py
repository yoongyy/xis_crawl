from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter, SourceAuthError
from .http import ConservativeHttpClient


class ProductHuntAdapter(SourceAdapter):
    name = "product_hunt"
    enabled_by_default = False

    def __init__(self) -> None:
        self.token = os.getenv("PRODUCT_HUNT_TOKEN")
        self.http = ConservativeHttpClient(1.0)

    def health_check(self) -> dict[str, Any]:
        return {"status": "optional" if self.token else "unavailable", "credential_required": True,
                "detail": "official API token configured; disabled by default" if self.token else "set PRODUCT_HUNT_TOKEN; disabled by default"}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        if not self.token:
            raise SourceAuthError("Product Hunt token unavailable")
        gql = """query($q:String!,$n:Int!){posts(search:$q,first:$n){edges{node{id name tagline description url votesCount createdAt}}}}"""
        response = self.http.request(
            "POST", "https://api.producthunt.com/v2/api/graphql",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"query": gql, "variables": {"q": query, "n": min(options.max_records, 20)}},
        ).json()
        edges = response.get("data", {}).get("posts", {}).get("edges", [])
        return [self.normalize(e["node"], query=query, search_rank=i) for i, e in enumerate(edges, 1)]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        return None

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        return SourceRecord(
            source=self.name, source_type="product", source_id=str(raw_record.get("id") or ""),
            canonical_url=raw_record.get("url") or "", title=raw_record.get("name"),
            body=raw_record.get("description") or raw_record.get("tagline"),
            published_at=datetime.fromisoformat(raw_record["createdAt"].replace("Z", "+00:00")) if raw_record.get("createdAt") else None,
            language="en", score_or_votes=raw_record.get("votesCount"), product_name=raw_record.get("name"),
            query=context.get("query"), search_rank=context.get("search_rank"), raw_payload=raw_record,
        )
