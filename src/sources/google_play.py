from __future__ import annotations

from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter, SourceAdapterError


class GooglePlayAdapter(SourceAdapter):
    name = "google_play"

    def health_check(self) -> dict[str, Any]:
        try:
            import google_play_scraper  # noqa: F401
            return {"status": "optional", "credential_required": False, "detail": "conservative optional public library available"}
        except ImportError:
            return {"status": "manual-import-only", "credential_required": False, "detail": "use CSV/JSON import; optional google-play-scraper not installed"}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        try:
            from google_play_scraper import search
        except ImportError as exc:
            raise SourceAdapterError("Google Play automated provider unavailable; use manual import") from exc
        return [self.normalize(item, query=query, search_rank=i) for i, item in enumerate(
            search(query, lang="en", country="us", n_hits=min(options.max_records, 30)), 1
        )]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        try:
            from google_play_scraper import app
        except ImportError as exc:
            raise SourceAdapterError("Google Play automated provider unavailable; use manual import") from exc
        app_id = _app_id(item_id_or_url)
        return self.normalize(app(app_id, lang="en", country="us"))

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        try:
            from google_play_scraper import Sort, reviews
        except ImportError as exc:
            raise SourceAdapterError("Google Play automated provider unavailable; use manual import") from exc
        app_id = _app_id(item_id_or_url)
        result, _ = reviews(
            app_id, lang="en", country="us", sort=Sort.NEWEST,
            count=min(options.max_reviews, 300), filter_score_with=None,
        )
        return [self.normalize(row, app_id=app_id) for row in result]

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        is_review = bool(raw_record.get("reviewId") or context.get("app_id"))
        app_id = str(context.get("app_id") or raw_record.get("appId") or "")
        if is_review:
            return SourceRecord(
                source=self.name, source_type="review", source_id=str(raw_record.get("reviewId") or ""),
                canonical_url=f"https://play.google.com/store/apps/details?id={app_id}&reviewId={raw_record.get('reviewId', '')}",
                body=raw_record.get("content"), author_public_name=raw_record.get("userName"),
                published_at=raw_record.get("at"), country_signal="US-storefront",
                language=raw_record.get("language") or "en", rating=raw_record.get("score"),
                app_name=raw_record.get("appName"), thread_id=app_id, raw_payload=raw_record,
            )
        return SourceRecord(
            source=self.name, source_type="app", source_id=app_id,
            canonical_url=raw_record.get("url") or f"https://play.google.com/store/apps/details?id={app_id}",
            title=raw_record.get("title"), body=raw_record.get("description"),
            author_public_name=raw_record.get("developer"), country_signal="US-storefront", language="en",
            rating=raw_record.get("score"), comment_count=raw_record.get("ratings"),
            app_name=raw_record.get("title"), product_name=raw_record.get("title"),
            query=context.get("query"), search_rank=context.get("search_rank"), thread_id=app_id,
            raw_payload=raw_record,
        )


def _app_id(value: str) -> str:
    return value.split("id=")[-1].split("&")[0]
