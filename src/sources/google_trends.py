from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote_plus

from ..research_models import CrawlOptions, SourceRecord
from .base import SourceAdapter, SourceAdapterError


class ManualGoogleTrendsImportProvider:
    name = "manual"

    @staticmethod
    def review_url(query: str) -> str:
        return f"https://trends.google.com/trends/explore?geo=US&q={quote_plus(query)}"

    def discover(self, query: str, options: CrawlOptions) -> list[dict[str, Any]]:
        raise SourceAdapterError(f"manual import required: {self.review_url(query)}")


class PytrendsProvider:
    name = "pytrends"

    def discover(self, query: str, options: CrawlOptions) -> list[dict[str, Any]]:
        from pytrends.request import TrendReq

        provider = TrendReq(hl="en-US", tz=360, retries=0)
        provider.build_payload([query], timeframe="today 5-y", geo="US")
        frame = provider.interest_over_time()
        rows: list[dict[str, Any]] = [
            {"record_type": "interest", "date": when, "value": row.get(query), "query": query}
            for when, row in frame.tail(min(options.max_records, len(frame))).iterrows()
        ]
        related = provider.related_queries().get(query) or {}
        for relation in ("rising", "top"):
            related_frame = related.get(relation)
            if related_frame is None:
                continue
            for _, row in related_frame.head(20).iterrows():
                rows.append({
                    "record_type": f"related_{relation}", "query": query,
                    "related_query": row.get("query"), "value": row.get("value"),
                })
        regions = provider.interest_by_region(
            resolution="REGION", inc_low_vol=True, inc_geo_code=True,
        )
        for region, row in regions.sort_values(query, ascending=False).head(20).iterrows():
            rows.append({
                "record_type": "region", "query": query, "region": region,
                "geo_code": row.get("geoCode"), "value": row.get(query),
            })
        return rows


class FutureGoogleTrendsProvider:
    name = "future"

    def discover(self, query: str, options: CrawlOptions) -> list[dict[str, Any]]:
        raise SourceAdapterError("future Google Trends provider is not configured")


class GoogleTrendsAdapter(SourceAdapter):
    name = "google_trends"

    def __init__(self) -> None:
        try:
            import pytrends  # noqa: F401
            self.provider = PytrendsProvider()
        except ImportError:
            self.provider = ManualGoogleTrendsImportProvider()

    def health_check(self) -> dict[str, Any]:
        if isinstance(self.provider, PytrendsProvider):
            status, detail = "optional", "PytrendsProvider available; best effort"
        else:
            status, detail = "manual-import-only", "Pytrends unavailable; exact review links and CSV import supported"
        return {"status": status, "credential_required": False, "detail": detail}

    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        try:
            rows = self.provider.discover(query, options)
        except SourceAdapterError:
            raise
        except Exception as exc:
            raise SourceAdapterError(
                f"Pytrends stopped after one failure; import CSV from "
                f"{ManualGoogleTrendsImportProvider.review_url(query)}"
            ) from exc
        return [self.normalize(row) for row in rows]

    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None:
        return None

    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord:
        query = str(raw_record.get("query") or context.get("query") or "")
        date = raw_record.get("date")
        record_type = str(raw_record.get("record_type") or "interest")
        qualifier = raw_record.get("related_query") or raw_record.get("region") or date
        return SourceRecord(
            source=self.name,
            source_type="trend_point" if record_type == "interest" else f"trend_{record_type}",
            source_id=f"{query}:{record_type}:{qualifier}",
            canonical_url=ManualGoogleTrendsImportProvider.review_url(query),
            title=str(raw_record.get("related_query") or raw_record.get("region") or query),
            body=str(raw_record.get("value") if raw_record.get("value") is not None else raw_record.get("interest") or ""),
            published_at=date.to_pydatetime() if hasattr(date, "to_pydatetime") else date,
            country_signal="US", language="en", score_or_votes=raw_record.get("value") or raw_record.get("interest"),
            query=query, thread_id=query, raw_payload=raw_record,
        )

    def supports_incremental(self) -> bool:
        return False
