from __future__ import annotations

import re
from typing import List, Tuple
from .models import MRRPostCandidate

DEFAULT_REVENUE_KEYWORDS = [
    "MRR",
    "ARR",
    "$",
    "美元",
    "美金",
    "万/月",
    "订阅",
]

# Additional pattern matchers for extra precision (e.g., $1000, 10k MRR, 5万/月)
REVENUE_PATTERNS = [
    r"(?i)\bMRR\b",
    r"(?i)\bARR\b",
    r"\$\s*\d+",
    r"\d+\s*(?:k|w|万)?\s*(?:美元|美金|USD)",
    r"\d+\s*万\s*/\s*月",
    r"\d+\s*(?:月订阅|年订阅|订阅费)",
    r"(?:月入|月收入|月营收|年营收|营收)\s*[\$\d万]",
]


class MoneyFilter:
    """
    Local filtering logic to evaluate revenue signals in Xiaohongshu posts.
    """

    def __init__(self, target_keywords: List[str] | None = None, min_matches: int = 1):
        self.target_keywords = target_keywords or DEFAULT_REVENUE_KEYWORDS
        self.min_matches = min_matches
        self.compiled_patterns = [re.compile(p) for p in REVENUE_PATTERNS]

    def analyze(self, title: str, content: str) -> Tuple[bool, List[str], List[str], int]:
        """
        Analyzes post title and content for revenue signals.
        
        Returns:
            Tuple[is_candidate, matched_keywords, revenue_snippets, revenue_score]
        """
        full_text = f"{title}\n{content}"
        matched_keywords = set()
        matched_snippets = []
        score = 0

        # 1. Exact string keyword check
        for kw in self.target_keywords:
            if kw.lower() in full_text.lower():
                matched_keywords.add(kw)
                score += 1

        # 2. Regex pattern checks for numeric revenue metrics (e.g. $500, 1万/月)
        for pattern in self.compiled_patterns:
            matches = pattern.findall(full_text)
            if matches:
                score += len(matches) * 2

        # 3. Extract sentence snippets containing money signals for quick review
        if matched_keywords or score > 0:
            sentences = re.split(r"[。\n！!？?；;]", full_text)
            for s in sentences:
                s_clean = s.strip()
                if not s_clean:
                    continue
                if any(kw.lower() in s_clean.lower() for kw in self.target_keywords) or any(
                    p.search(s_clean) for p in self.compiled_patterns
                ):
                    if s_clean not in matched_snippets:
                        matched_snippets.append(s_clean[:120])

        is_candidate = len(matched_keywords) >= self.min_matches or score >= 2
        return is_candidate, sorted(list(matched_keywords)), matched_snippets[:5], score

    def filter_candidate(self, candidate: MRRPostCandidate) -> MRRPostCandidate:
        """
        Applies analysis directly to an MRRPostCandidate instance.
        """
        is_candidate, keywords, snippets, score = self.analyze(candidate.title, candidate.content)
        candidate.is_mrr_candidate = is_candidate
        candidate.matched_keywords = keywords
        candidate.revenue_snippets = snippets
        candidate.revenue_score = score
        return candidate
