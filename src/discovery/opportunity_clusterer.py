from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ..research_models import EvidenceFinding


def cluster_findings(findings: Iterable[EvidenceFinding]) -> dict[str, list[EvidenceFinding]]:
    clusters: dict[str, list[EvidenceFinding]] = defaultdict(list)
    for finding in findings:
        key = (finding.problem_category or finding.problem_description or "unclassified").strip().lower()
        clusters[key].append(finding)
    return dict(clusters)
