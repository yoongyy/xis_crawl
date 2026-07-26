from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

from ..research_models import PlannedQuery, ResearchPack


EXPANSIONS = {
    "problem": ["{base}", '"{base}" frustrating', '"{base}" nothing works'],
    "solution_search": ["app for {base}", "how do you solve {base}", "better alternative for {base}"],
    "payment": ['paid app for {base}', '"worth the money" {base}', '"one-time purchase" {base}'],
    "cancellation": ['cancelled subscription {base}', '"requested a refund" {base}', '"uninstalled" {base}'],
    "competitor_review": ["{base} app review", "{base} one star review", "{base} too expensive"],
    "missing_feature": ['"{base}" missing feature', '"I wish there was" {base}'],
    "workaround": ["{base} workaround", "how I manage {base} manually"],
}

SOURCE_PURPOSES = {
    "app_store": ("competitor_review",),
    "google_play": ("competitor_review",),
    "google_trends": ("problem",),
    "hacker_news": ("problem", "solution_search", "competitor_review"),
    "youtube": ("problem", "solution_search", "competitor_review", "missing_feature"),
}


def load_research_pack(path: Path) -> ResearchPack:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload.setdefault("slug", path.stem)
    payload.setdefault("name", path.stem.replace("_", " ").title())
    payload.setdefault("market", {"country": "United States", "language": "English", "customer": "individual consumers"})
    return ResearchPack.model_validate(payload)


class QueryPlanner:
    def __init__(self, max_queries_per_source: int = 24) -> None:
        self.max_queries_per_source = max_queries_per_source

    def plan(
        self,
        pack: ResearchPack,
        sources: Iterable[str] | None = None,
        recent_days: int = 365,
        max_results: int = 100,
    ) -> list[PlannedQuery]:
        selected = list(sources or pack.sources or ["reddit", "app_store", "google_play", "google_trends"])
        planned: list[PlannedQuery] = []
        for source in selected:
            seen: set[str] = set()
            purposes = SOURCE_PURPOSES.get(source, tuple(EXPANSIONS))
            bases = list(pack.keywords)
            if source in {"app_store", "google_play", "product_hunt"}:
                bases.extend(category.replace("_", " ") for category in pack.competitor_categories)
            # Cover every base once before spending the remaining budget on
            # alternate intent phrases. This prevents early keywords from
            # consuming the entire plan.
            candidates: list[tuple[int, int, str, str]] = []
            for base_index, base in enumerate(bases):
                purpose = purposes[base_index % len(purposes)]
                candidates.append((1 + min(base_index // 8, 2), base_index, purpose, base))
            round_number = 1
            while len(candidates) < self.max_queries_per_source * 2:
                added = False
                for base_index, base in enumerate(bases):
                    if round_number >= len(purposes):
                        break
                    purpose = purposes[(base_index + round_number) % len(purposes)]
                    candidates.append((2 + round_number + min(base_index // 8, 2), base_index, purpose, base))
                    added = True
                if not added or round_number >= len(purposes):
                    break
                round_number += 1
            for priority, base_index, purpose, base in candidates:
                if source in {"app_store", "google_play", "google_trends", "product_hunt"}:
                    query = base.strip()
                else:
                    templates = EXPANSIONS[purpose]
                    query = templates[base_index % len(templates)].format(base=base).strip()
                if query.lower() in seen:
                    continue
                seen.add(query.lower())
                planned.append(PlannedQuery(
                    source=source, query=query, purpose=purpose,
                    priority=priority,
                    expected_value=max(0.2, 1.0 - priority * 0.06 - base_index * 0.01),
                    maximum_results=min(max_results, 100),
                    freshness_window_days=recent_days,
                ))
                if len(seen) >= self.max_queries_per_source:
                    break
        return sorted(planned, key=lambda q: (q.priority, -q.expected_value, q.source, q.query))
