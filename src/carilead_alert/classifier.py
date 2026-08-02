from __future__ import annotations

import re
from typing import List, Tuple
from .models import CommercialLead, TargetNiche

# Target Intent Keywords per Niche
NICHE_KEYWORDS = {
    TargetNiche.INSURANCE: [
        "求推荐医疗险", "求推荐保险", "哪家保险好", "买什么保险", "大马保险",
        "保单分析", "重疾险推荐", "儿童保单", "储蓄险", "保费算高吗",
        "吉隆坡保险", "保单理赔", "人寿保险", "医药卡推荐"
    ],
    TargetNiche.FREELANCE_DEV: [
        "求推荐网页", "寻找程序员", "外包软件", "小程序开发", "找APP制作",
        "独立开发外包", "网站建设", "需要开发", "求推荐系统开发", "代码外包"
    ],
    TargetNiche.DESIGN_MARKETING: [
        "求推荐UI设计", "找平面设计", "寻找小红书运营", "品牌设计外包", "求推荐剪辑师",
        "LOGO设计", "社交媒体代运营", "寻求海报设计"
    ]
}

# General Buying Intent Trigger Expressions
INTENT_TRIGGERS = [
    r"求推荐", r"哪家好", r"求介绍", r"想了解", r"价格多少",
    r"预算", r"寻找", r"有没有推荐", r"私信我", r"怎么选"
]

# Malaysia Location Indicators
MALAYSIA_LOCATIONS = [
    "吉隆坡", "KL", "PJ", "Petaling Jaya", "槟城", "Penang", "柔佛", "JB", "Johor",
    "雪兰莪", "Selangor", "马六甲", "Melaka", "怡保", "Ipoh", "大马", "Malaysia"
]


class IntentClassifier:
    """
    Evaluates raw social posts to identify high-intent buyer leads and generate response drafts.
    """

    def __init__(self, min_score_threshold: int = 4):
        self.min_score_threshold = min_score_threshold
        self.compiled_triggers = [re.compile(p) for p in INTENT_TRIGGERS]

    def evaluate(self, title: str, content: str, niche: TargetNiche) -> Tuple[bool, int, List[str], Optional[str], str]:
        """
        Returns:
            Tuple[is_high_intent, intent_score, matched_keywords, location_tag, suggested_reply]
        """
        full_text = f"{title}\n{content}"
        matched_kw = set()
        score = 0

        # 1. Niche Specific Keyword Matches
        target_kws = NICHE_KEYWORDS.get(niche, [])
        for kw in target_kws:
            if kw.lower() in full_text.lower():
                matched_kw.add(kw)
                score += 3

        # 2. General Intent Triggers
        for trigger in self.compiled_triggers:
            if trigger.search(full_text):
                score += 2

        # 3. Location Detection
        location_tag = None
        for loc in MALAYSIA_LOCATIONS:
            if loc.lower() in full_text.lower():
                location_tag = loc
                score += 1
                break

        is_high_intent = score >= self.min_score_threshold or len(matched_kw) > 0
        suggested_reply = self._generate_reply_draft(niche, full_text) if is_high_intent else ""

        return is_high_intent, score, sorted(list(matched_kw)), location_tag, suggested_reply

    def _generate_reply_draft(self, niche: TargetNiche, text: str) -> str:
        if niche == TargetNiche.INSURANCE:
            return (
                "你好！看到你在了解保单方案。我是大马持牌理财顾问，"
                "可以根据你的预算帮你做一份免费的客观保单对比（包含医疗保障和重疾覆盖），"
                "不强制推销，方便私信聊聊你的具体需求吗？"
            )
        elif niche == TargetNiche.FREELANCE_DEV:
            return (
                "你好！我是独立全栈开发者，精通Web/小程序/APP开发。"
                "看到你在寻找开发资源，我们可以快速做个15分钟沟通，为你定制高性价比 MVP 方案，"
                "欢迎私信了解案例和报价！"
            )
        elif niche == TargetNiche.DESIGN_MARKETING:
            return (
                "你好！我是专业资深设计师，专门提供品牌设计与小红书爆款视觉打造。"
                "可以为你提供精选作品集参考，方便私信沟通你的设计需求吗？"
            )
        return "你好！关注到你的需求，欢迎私信沟通详细合作信息。"
