from __future__ import annotations

from .app_store import AppStoreAdapter
from .google_play import GooglePlayAdapter
from .google_trends import GoogleTrendsAdapter
from .hacker_news import HackerNewsAdapter
from .product_hunt import ProductHuntAdapter
from .reddit import RedditAdapter
from .xhs import XHSAdapter
from .youtube import YouTubeAdapter


def build_registry():
    adapters = [
        RedditAdapter(), HackerNewsAdapter(), YouTubeAdapter(), AppStoreAdapter(),
        GooglePlayAdapter(), GoogleTrendsAdapter(), ProductHuntAdapter(), XHSAdapter(),
    ]
    return {adapter.name: adapter for adapter in adapters}
