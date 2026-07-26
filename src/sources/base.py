from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

from ..research_models import CrawlOptions, SourceRecord


class SourceAdapterError(RuntimeError):
    pass


class SourceAuthError(SourceAdapterError):
    pass


class SourceBlockedError(SourceAdapterError):
    pass


@dataclass
class RateLimitStatus:
    remaining: int | None = None
    reset_at: str | None = None
    state: str = "unknown"


class SourceAdapter(ABC):
    name: str
    enabled_by_default: bool = True

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    def discover(self, query: str, options: CrawlOptions) -> Iterable[SourceRecord]: ...

    @abstractmethod
    def fetch_item(self, item_id_or_url: str) -> SourceRecord | None: ...

    def fetch_replies(self, item_id_or_url: str, options: CrawlOptions) -> Iterable[SourceRecord]:
        return []

    @abstractmethod
    def normalize(self, raw_record: dict[str, Any], **context: Any) -> SourceRecord: ...

    def estimate_request_cost(self, query: str, options: CrawlOptions) -> dict[str, float]:
        return {"api_calls": 1, "expected_records": min(options.max_records, 100)}

    def supports_incremental(self) -> bool:
        return True

    def get_rate_limit_status(self) -> RateLimitStatus:
        return RateLimitStatus()
