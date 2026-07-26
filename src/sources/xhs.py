from __future__ import annotations

from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord
from ..xhs_client import XHSClient, normalize_comment, normalize_post
from .base import SourceAdapter


class XHSAdapter(SourceAdapter):
    name = "xhs"
    enabled_by_default = False

    def __init__(self) -> None:
        self.client = XHSClient()

    def health_check(self) -> dict[str, Any]:
        if not self.client.is_installed():
            return {"status": "unavailable", "credential_required": True, "detail": "xhs CLI not installed"}
        try:
            self.client.status()
            return {"status": "optional", "credential_required": True, "detail": "early_trend_scout; never US validation"}
        except Exception as exc:
            return {"status": "temporarily failing", "credential_required": True, "detail": str(exc)[:160]}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        raw, _ = self.client.search(query, sort="latest")
        return [self.normalize(row, query=query, search_rank=i) for i, row in enumerate(raw[: options.max_records], 1)]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        raw, _ = self.client.read(item_id_or_url)
        return self.normalize(raw)

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        raw, _ = self.client.comments(item_id_or_url)
        out = []
        for item in raw:
            for comment in normalize_comment(item, post_id=item_id_or_url, post_url=item_id_or_url):
                out.append(SourceRecord(
                    source=self.name, source_type="comment", source_id=comment.comment_id,
                    canonical_url=comment.url or item_id_or_url, body=comment.text,
                    author_public_name=comment.author_name, author_id=comment.author_id,
                    published_at=comment.created_at, language=comment.language,
                    thread_id=comment.post_id, parent_id=comment.parent_comment_id,
                    market_role="early_trend_scout",
                    default_market="Malaysia or Chinese-speaking users",
                    not_us_validation=True,
                    raw_payload=comment.raw_json,
                ))
        return out[: options.max_comments]

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        post = normalize_post(raw_record, context.get("query"))
        return SourceRecord(
            source=self.name, source_type="post", source_id=post.post_id,
            canonical_url=post.url, title=post.title, body=post.body,
            author_public_name=post.author_name, author_id=post.author_id,
            published_at=post.published_at, language=post.language,
            score_or_votes=post.likes, comment_count=post.comment_count,
            query=context.get("query"), search_rank=context.get("search_rank"),
            thread_id=post.post_id, market_role="early_trend_scout",
            default_market="Malaysia or Chinese-speaking users",
            not_us_validation=True, raw_payload=raw_record,
        )
