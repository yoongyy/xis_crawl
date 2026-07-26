from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter, SourceAuthError
from .http import ConservativeHttpClient


class YouTubeAdapter(SourceAdapter):
    name = "youtube"

    def __init__(self) -> None:
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.http = ConservativeHttpClient(0.2)

    def health_check(self) -> dict[str, Any]:
        return {"status": "available" if self.api_key else "unavailable", "credential_required": True,
                "detail": "API key configured" if self.api_key else "set YOUTUBE_API_KEY"}

    def _get(self, endpoint: str, **params: Any) -> dict[str, Any]:
        if not self.api_key:
            raise SourceAuthError("YouTube API key unavailable")
        params["key"] = self.api_key
        return self.http.request("GET", f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params).json()

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        payload = self._get(
            "search", part="snippet", q=query, type="video", relevanceLanguage="en",
            regionCode="US", maxResults=min(options.max_records, 50),
            publishedAfter=(datetime.now(timezone.utc) - timedelta(days=options.recent_days)).isoformat().replace("+00:00", "Z"),
        )
        return [self.normalize(item, query=query, search_rank=i) for i, item in enumerate(payload.get("items", []), 1)]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        video_id = item_id_or_url.split("v=")[-1].split("&")[0].rstrip("/").split("/")[-1]
        items = self._get("videos", part="snippet,statistics", id=video_id).get("items", [])
        return self.normalize(items[0]) if items else None

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        video_id = item_id_or_url.split("v=")[-1].split("&")[0].rstrip("/").split("/")[-1]
        out: list[SourceRecord] = []
        page_token: str | None = None
        while len(out) < options.max_comments:
            params: dict[str, Any] = {
                "part": "snippet,replies", "videoId": video_id, "textFormat": "plainText",
                "maxResults": min(options.max_comments - len(out), 100), "order": "relevance",
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("commentThreads", **params)
            for thread in payload.get("items", []):
                top = thread["snippet"]["topLevelComment"]
                out.append(self.normalize(top, video_id=video_id))
                included = thread.get("replies", {}).get("comments", [])
                for reply in included:
                    if len(out) >= options.max_comments:
                        break
                    out.append(self.normalize(reply, video_id=video_id))
                total_replies = int(thread.get("snippet", {}).get("totalReplyCount") or 0)
                if total_replies > len(included) and len(out) < options.max_comments:
                    self._fetch_comment_replies(
                        str(top.get("id")), video_id, options.max_comments, out,
                        {str(reply.get("id")) for reply in included},
                    )
                if len(out) >= options.max_comments:
                    break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return out[: options.max_comments]

    def _fetch_comment_replies(
        self,
        parent_id: str,
        video_id: str,
        limit: int,
        out: list[SourceRecord],
        seen: set[str],
    ) -> None:
        page_token: str | None = None
        while len(out) < limit:
            params: dict[str, Any] = {
                "part": "snippet", "parentId": parent_id,
                "textFormat": "plainText", "maxResults": min(limit - len(out), 100),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._get("comments", **params)
            for reply in payload.get("items", []):
                if str(reply.get("id")) in seen:
                    continue
                out.append(self.normalize(reply, video_id=video_id))
                if len(out) >= limit:
                    break
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        snippet = raw_record.get("snippet", {})
        if "topLevelComment" in snippet:
            snippet = snippet["topLevelComment"].get("snippet", {})
        source_id = str(raw_record.get("id", {}).get("videoId") if isinstance(raw_record.get("id"), dict) else raw_record.get("id") or "")
        is_comment = "textDisplay" in snippet or "textOriginal" in snippet
        video_id = context.get("video_id") or snippet.get("videoId") or source_id
        return SourceRecord(
            source=self.name, source_type="comment" if is_comment else "video", source_id=source_id,
            canonical_url=f"https://www.youtube.com/watch?v={video_id}" + (f"&lc={source_id}" if is_comment else ""),
            title=None if is_comment else snippet.get("title"),
            body=snippet.get("textOriginal") or snippet.get("textDisplay") or snippet.get("description"),
            author_public_name=snippet.get("authorDisplayName") or snippet.get("channelTitle"),
            published_at=_parse_dt(snippet.get("publishedAt")), country_signal="US-search", language="en",
            score_or_votes=snippet.get("likeCount"), comment_count=raw_record.get("statistics", {}).get("commentCount"),
            query=context.get("query"), search_rank=context.get("search_rank"), thread_id=str(video_id),
            parent_id=snippet.get("parentId"), raw_payload=raw_record,
        )


def _parse_dt(value: str | None):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
