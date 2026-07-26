from __future__ import annotations

import os

from pydantic import BaseModel

from ..research_models import EvidenceFinding, SourceRecord
from .evidence_classifier import RulesEvidenceClassifier


class FindingBatch(BaseModel):
    findings: list[EvidenceFinding]


class LLMEvidenceClassifier:
    prompt_version = "openai-evidence-v1"

    def __init__(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for --classification-mode llm")
        from openai import OpenAI
        self.client = OpenAI()
        self.fallback = RulesEvidenceClassifier()

    def classify(self, record: SourceRecord, problem_category: str | None = None) -> list[EvidenceFinding]:
        # Rules produce conservative candidate spans; the LLM may structure them but
        # cannot manufacture evidence absent from the source.
        candidates = self.fallback.classify(record, problem_category)
        if not candidates:
            return []
        response = self.client.responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=[
                {"role": "system", "content": (
                    "Extract only atomic consumer evidence present verbatim in the supplied source. "
                    "Do not infer willingness to pay, do not treat maker claims as demand, and preserve URLs/IDs."
                )},
                {"role": "user", "content": FindingBatch(findings=candidates).model_dump_json()},
            ],
            text_format=FindingBatch,
        )
        parsed = response.output_parsed
        for finding in parsed.findings:
            finding.prompt_version = self.prompt_version
        return parsed.findings
