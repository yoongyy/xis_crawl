from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter
from .http import ConservativeHttpClient


class AppStoreAdapter(SourceAdapter):
    name = "app_store"

    def __init__(self) -> None:
        self.http = ConservativeHttpClient(1.0)

    def health_check(self) -> dict[str, Any]:
        return {"status": "available", "credential_required": False, "detail": "US iTunes Search and public review RSS"}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        payload = self.http.request(
            "GET", "https://itunes.apple.com/search",
            params={"term": query, "country": "us", "entity": "software", "limit": min(options.max_records, 50)},
        ).json()
        return [self.normalize(item, query=query, search_rank=i) for i, item in enumerate(payload.get("results", []), 1)]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        app_id = item_id_or_url.split("/id")[-1].split("?")[0] if "/id" in item_id_or_url else item_id_or_url
        results = self.http.request("GET", "https://itunes.apple.com/lookup", params={"id": app_id, "country": "us"}).json().get("results", [])
        return self.normalize(results[0]) if results else None

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        app_id = item_id_or_url.split("/id")[-1].split("?")[0] if "/id" in item_id_or_url else item_id_or_url
        out: list[SourceRecord] = []
        pages = min(10, (options.max_reviews + 49) // 50)
        for page in range(1, pages + 1):
            url = f"https://itunes.apple.com/us/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
            feed = self.http.request("GET", url).json().get("feed", {})
            for entry in feed.get("entry", []):
                if "im:rating" in entry:
                    out.append(self.normalize(entry, app_id=app_id))
                    if len(out) >= options.max_reviews:
                        return out
        return out

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        is_review = "im:rating" in raw_record
        if is_review:
            app_id = str(context.get("app_id") or "")
            rid = str(_label(raw_record.get("id")) or "")
            return SourceRecord(
                source=self.name, source_type="review", source_id=rid,
                canonical_url=_link(raw_record.get("link")) or f"https://apps.apple.com/us/app/id{app_id}",
                title=_label(raw_record.get("title")), body=_label(raw_record.get("content")),
                author_public_name=_label((raw_record.get("author") or {}).get("name")) if isinstance(raw_record.get("author"), dict) else None,
                published_at=_dt(_label(raw_record.get("updated"))), country_signal="US-storefront", language="en",
                rating=float(_label(raw_record.get("im:rating"))), app_name=context.get("app_name"),
                thread_id=app_id, raw_payload=raw_record,
            )
        app_id = str(raw_record.get("trackId") or "")
        return SourceRecord(
            source=self.name, source_type="app", source_id=app_id,
            canonical_url=raw_record.get("trackViewUrl") or f"https://apps.apple.com/us/app/id{app_id}",
            title=raw_record.get("trackName"), body=raw_record.get("description"),
            author_public_name=raw_record.get("sellerName"), published_at=_dt(raw_record.get("currentVersionReleaseDate")),
            country_signal="US-storefront", language="en", rating=raw_record.get("averageUserRating"),
            app_name=raw_record.get("trackName"), product_name=raw_record.get("trackName"),
            comment_count=raw_record.get("userRatingCount"), query=context.get("query"),
            search_rank=context.get("search_rank"), thread_id=app_id, raw_payload=raw_record,
        )


def _dt(value: str | None):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _label(value: Any) -> Any:
    return value.get("label") if isinstance(value, dict) else value


def _link(value: Any) -> str | None:
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, dict):
            href = item.get("attributes", {}).get("href")
            if href:
                return str(href)
    return None
