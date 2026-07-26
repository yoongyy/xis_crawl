from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from .base import SourceAdapterError, SourceAuthError, SourceBlockedError


class ConservativeHttpClient:
    def __init__(
        self,
        delay_seconds: float = 1.0,
        timeout: float = 20.0,
        cache_dir: Path = Path("data/cache/http"),
        cache_ttl_seconds: int = 3600,
        max_retries: int = 2,
    ) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.last_request = 0.0
        self.cache_dir = cache_dir
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        self.max_retries = max(0, max_retries)
        self.force_refresh = False

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        method = method.upper()
        cache_path = self._cache_path(method, url, kwargs) if method == "GET" else None
        cached = self._read_cache(cache_path, url)
        if cached is not None:
            return cached
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            wait = self.delay_seconds - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self.client.request(method, url, **kwargs)
                self.last_request = time.monotonic()
            except httpx.RequestError as exc:
                if attempt >= self.max_retries:
                    raise SourceAdapterError(f"network failure from {url}: {exc}") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 401:
                raise SourceAuthError(f"401 from {url}")
            if response.status_code in {403, 429}:
                raise SourceBlockedError(f"{response.status_code} from {url}; source stopped")
            if response.status_code >= 500 and attempt < self.max_retries:
                time.sleep(2 ** attempt)
                continue
            if response.status_code >= 400:
                raise SourceAdapterError(f"{response.status_code} from {url}")
            if _looks_blocked(response):
                raise SourceBlockedError(f"CAPTCHA or risk-control response from {url}; source stopped")
            if cache_path is not None:
                self._write_cache(cache_path, response)
            return response
        raise SourceAdapterError(f"source request failed after retries: {url}")

    def _cache_path(self, method: str, url: str, kwargs: dict[str, Any]) -> Path:
        params = kwargs.get("params") or {}
        key = json.dumps(
            {"method": method, "url": url, "params": params},
            ensure_ascii=False, sort_keys=True, default=str,
        )
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _read_cache(self, path: Path | None, url: str) -> httpx.Response | None:
        if path is None or self.force_refresh or not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.cache_ttl_seconds:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return httpx.Response(
                status_code=int(payload["status_code"]),
                headers=payload.get("headers") or {},
                content=str(payload.get("text") or "").encode("utf-8"),
                request=httpx.Request("GET", url),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _write_cache(self, path: Path, response: httpx.Response) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "status_code": response.status_code,
            "headers": {
                key: value for key, value in response.headers.items()
                if key.lower() in {"content-type", "etag", "last-modified", "x-ratelimit-remaining", "x-ratelimit-reset"}
            },
            "text": response.text,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _looks_blocked(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        return False
    sample = response.text[:10000].lower()
    return any(
        marker in sample
        for marker in ("captcha", "verify you are human", "unusual traffic", "risk control")
    )
