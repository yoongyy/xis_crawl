from __future__ import annotations

import statistics
from typing import Sequence


def classify_trend(values: Sequence[float]) -> str:
    values = [float(v) for v in values if v is not None]
    if len(values) < 8:
        return "insufficient_data"
    split = max(2, len(values) // 4)
    early = statistics.fmean(values[:split])
    recent = statistics.fmean(values[-split:])
    peak = max(values)
    if peak > max(10, statistics.fmean(values) * 2.5) and recent < peak * 0.45:
        return "temporary_spike"
    if recent > early * 1.4:
        return "recently_accelerating"
    if recent > early * 1.15:
        return "steadily_growing"
    if recent < early * 0.75:
        return "declining"
    return "stable"
