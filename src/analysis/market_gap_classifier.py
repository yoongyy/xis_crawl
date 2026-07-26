from __future__ import annotations


def classify_market_gap(missing_feature_count: int, competitor_count: int, dissatisfaction_count: int) -> str:
    if competitor_count >= 10 and missing_feature_count < 3:
        return "crowded_market"
    if missing_feature_count >= 3 and dissatisfaction_count >= 5:
        return "promising_hypothesis"
    return "insufficient_evidence"
