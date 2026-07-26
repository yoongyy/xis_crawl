from __future__ import annotations

from ..research_models import EvidenceFinding, SourceRecord


class ReportVerifier:
    def verify(self, finding: EvidenceFinding, record: SourceRecord) -> EvidenceFinding:
        source_text = " ".join(p for p in (record.title, record.body) if p)
        reasons: list[str] = []
        if finding.evidence_text not in source_text and source_text not in finding.evidence_text:
            reasons.append("evidence excerpt is not present in source")
        if finding.evidence_type == "willingness_to_pay" and not finding.willingness_to_pay_statement:
            reasons.append("willingness to pay was inferred")
        if finding.promotional_probability >= 0.7 and finding.evidence_type not in {"promotion", "maker_claim"}:
            reasons.append("maker or promotional claim cannot count as independent demand")
        if record.not_us_validation and finding.market == "United States":
            reasons.append("XHS evidence cannot validate United States demand")
        finding.verification_status = "rejected" if reasons else "verified"
        finding.verification_notes = "; ".join(reasons) or None
        if reasons:
            finding.organic_evidence_weight = 0.0
        return finding
