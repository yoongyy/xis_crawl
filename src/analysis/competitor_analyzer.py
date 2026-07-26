from __future__ import annotations

from ..research_models import CompetitorProduct


def validate_competitor(product: CompetitorProduct) -> list[str]:
    warnings = []
    if product.current_price is not None and not product.verified_price():
        warnings.append("current pricing omitted: recent source link and checked date required")
        product.current_price = None
        product.price_currency = None
    if not product.evidence_links:
        warnings.append("competitor has no supporting evidence links")
        product.source_confidence = min(product.source_confidence, 0.2)
    return warnings
