from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from typing import Any, Iterable
import re

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter
from .http import ConservativeHttpClient


class HackerNewsAdapter(SourceAdapter):
    name = "hacker_news"

    def __init__(self) -> None:
        self.http = ConservativeHttpClient(0.25)

    def health_check(self) -> dict[str, Any]:
        return {"status": "available", "credential_required": False, "detail": "public Firebase/Algolia APIs"}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        tags = None
        lowered = query.lower()
        if lowered.startswith("ask hn"):
            tags, query = "ask_hn", query[6:].strip()
        elif lowered.startswith("show hn"):
            tags, query = "show_hn", query[7:].strip()
        params: dict[str, Any] = {
            "query": query, "hitsPerPage": min(options.max_records, 100),
            "numericFilters": f"created_at_i>{int(datetime.now(timezone.utc).timestamp()) - options.recent_days * 86400}",
        }
        if tags:
            params["tags"] = tags
        payload = self.http.request("GET", "https://hn.algolia.com/api/v1/search_by_date", params=params).json()
        return [self.normalize(hit, query=query, search_rank=i) for i, hit in enumerate(payload.get("hits", []), 1)]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        item_id = item_id_or_url.split("id=")[-1].rstrip("/").split("/")[-1]
        raw = self.http.request("GET", f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").json()
        return self.normalize(raw) if raw else None

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        root = self.fetch_item(item_id_or_url)
        if not root:
            return []
        raw = root.raw_payload
        result: list[SourceRecord] = []
        queue = [(kid, 1) for kid in raw.get("kids", [])]
        while queue and len(result) < options.max_comments:
            kid, depth = queue.pop(0)
            item = self.http.request("GET", f"https://hacker-news.firebaseio.com/v0/item/{kid}.json").json()
            if not item or item.get("deleted") or item.get("dead"):
                continue
            result.append(self.normalize(item, thread_id=root.source_id))
            if depth < options.nested_comment_depth:
                queue.extend((child, depth + 1) for child in item.get("kids", []))
        return result

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        source_id = str(raw_record.get("objectID") or raw_record.get("id") or "")
        kind = "comment" if (raw_record.get("type") == "comment" or raw_record.get("comment_text")) else "story"
        body = raw_record.get("comment_text") or raw_record.get("story_text") or raw_record.get("text")
        title = raw_record.get("title") or raw_record.get("story_title")
        created = raw_record.get("created_at_i") or raw_record.get("time")
        return SourceRecord(
            source=self.name, source_type=kind, source_id=source_id,
            canonical_url=f"https://news.ycombinator.com/item?id={source_id}",
            title=title, body=_strip_html(body), author_public_name=raw_record.get("author") or raw_record.get("by"),
            published_at=datetime.fromtimestamp(created, tz=timezone.utc) if created else None,
            language="en", score_or_votes=raw_record.get("points") or raw_record.get("score"),
            comment_count=raw_record.get("num_comments") or raw_record.get("descendants"),
            query=context.get("query"), search_rank=context.get("search_rank"),
            thread_id=str(context.get("thread_id") or raw_record.get("story_id") or source_id),
            parent_id=str(raw_record.get("parent") or "") or None, raw_payload=raw_record,
        )


def _strip_html(value: Any) -> str | None:
    if value is None:
        return None
    return unescape(re.sub(r"<[^>]+>", " ", str(value))).strip()
