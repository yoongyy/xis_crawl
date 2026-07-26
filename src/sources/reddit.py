from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

from ..research_models import CrawlOptions, SourceRecord
from .base import RateLimitStatus, SourceAdapter, SourceAuthError
from .http import ConservativeHttpClient


class RedditAdapter(SourceAdapter):
    name = "reddit"

    def __init__(self) -> None:
        self.client_id = os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = os.getenv("REDDIT_USER_AGENT", "local-market-research/0.1")
        self.http = ConservativeHttpClient(1.0)
        self._token: str | None = None
        self._rate = RateLimitStatus()

    def health_check(self) -> dict[str, Any]:
        available = bool(self.client_id and self.client_secret and self.user_agent)
        return {
            "status": "available" if available else "unavailable",
            "credential_required": True,
            "detail": "OAuth credentials configured" if available else "set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET",
        }

    def _headers(self) -> dict[str, str]:
        if not self.client_id or not self.client_secret:
            raise SourceAuthError("Reddit OAuth credentials are unavailable")
        if not self._token:
            response = self.http.request(
                "POST", "https://www.reddit.com/api/v1/access_token",
                auth=(self.client_id, self.client_secret),
                headers={"User-Agent": self.user_agent},
                data={"grant_type": "client_credentials"},
            )
            self._token = response.json()["access_token"]
        return {"Authorization": f"bearer {self._token}", "User-Agent": self.user_agent}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        subreddit = None
        if query.lower().startswith("r/") and " " in query:
            subreddit, query = query.split(" ", 1)
            subreddit = subreddit[2:]
        if subreddit and options.subreddit_allowlist and subreddit.lower() not in {
            s.lower().removeprefix("r/") for s in options.subreddit_allowlist
        }:
            return []
        if subreddit and subreddit.lower() in {
            s.lower().removeprefix("r/") for s in options.subreddit_denylist
        }:
            return []
        endpoint = f"https://oauth.reddit.com/r/{subreddit}/search" if subreddit else "https://oauth.reddit.com/search"
        params = {
            "q": query, "limit": min(options.max_records, 100), "raw_json": 1,
            "sort": options.sort if options.sort in {"relevance", "new", "top", "comments"} else "relevance",
            "t": _reddit_time(options.recent_days),
            "restrict_sr": "true" if subreddit else "false",
        }
        response = self.http.request("GET", endpoint, headers=self._headers(), params=params)
        self._capture_rate(response.headers)
        return [
            self.normalize(child["data"], query=query, search_rank=index)
            for index, child in enumerate(response.json().get("data", {}).get("children", []), 1)
        ]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        item_id = _reddit_item_id(item_id_or_url)
        response = self.http.request(
            "GET", f"https://oauth.reddit.com/by_id/t3_{item_id}",
            headers=self._headers(), params={"raw_json": 1},
        )
        children = response.json().get("data", {}).get("children", [])
        return self.normalize(children[0]["data"]) if children else None

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        path = urlparse(item_id_or_url).path if item_id_or_url.startswith("http") else f"/comments/{item_id_or_url}"
        response = self.http.request(
            "GET", f"https://oauth.reddit.com{path.rstrip('/')}.json",
            headers=self._headers(),
            params={"limit": min(options.max_comments, 500), "depth": min(options.nested_comment_depth, 10), "raw_json": 1},
        )
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        post_id = path.rstrip("/").split("/")[-1]
        records: list[SourceRecord] = []
        _walk_comments(payload[1].get("data", {}).get("children", []), records, self, post_id, options)
        return records[: options.max_comments]

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        kind = "comment" if raw_record.get("body") is not None and raw_record.get("link_id") else "post"
        source_id = str(raw_record.get("id") or raw_record.get("name") or "")
        permalink = raw_record.get("permalink") or ""
        return SourceRecord(
            source=self.name, source_type=kind, source_id=source_id,
            canonical_url=f"https://www.reddit.com{permalink}" if permalink.startswith("/") else str(permalink),
            title=raw_record.get("title"), body=raw_record.get("selftext") if kind == "post" else raw_record.get("body"),
            author_public_name=raw_record.get("author"), author_id=raw_record.get("author_fullname"),
            published_at=datetime.fromtimestamp(raw_record["created_utc"], tz=timezone.utc) if raw_record.get("created_utc") else None,
            country_signal="US-weak", language="en", score_or_votes=raw_record.get("score"),
            comment_count=raw_record.get("num_comments"), query=context.get("query"),
            search_rank=context.get("search_rank"), thread_id=str(raw_record.get("link_id") or source_id).removeprefix("t3_"),
            parent_id=str(raw_record.get("parent_id") or "").removeprefix("t1_") or None,
            raw_payload=raw_record,
        )

    def get_rate_limit_status(self) -> RateLimitStatus:
        return self._rate

    def _capture_rate(self, headers: Any) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        self._rate = RateLimitStatus(
            remaining=int(float(remaining)) if remaining else None,
            reset_at=headers.get("x-ratelimit-reset"), state="healthy",
        )


def _reddit_time(days: int) -> str:
    if days <= 1: return "day"
    if days <= 7: return "week"
    if days <= 31: return "month"
    if days <= 365: return "year"
    return "all"


def _reddit_item_id(value: str) -> str:
    if "/comments/" in value:
        return value.split("/comments/", 1)[1].split("/", 1)[0]
    return value.removeprefix("t3_").rstrip("/").split("/")[-1]


def _walk_comments(children, out, adapter, post_id, options, depth=0) -> None:
    if depth > options.nested_comment_depth or len(out) >= options.max_comments:
        return
    for child in children:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        out.append(adapter.normalize(data))
        replies = data.get("replies")
        if isinstance(replies, dict):
            _walk_comments(replies.get("data", {}).get("children", []), out, adapter, post_id, options, depth + 1)
