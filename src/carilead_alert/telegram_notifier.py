from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import List, Optional
from .models import CommercialLead, TargetNiche


class TelegramNotifier:
    """
    Formats Commercial Lead alerts into clean Telegram message templates and dispatches alerts to subscribers.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def format_lead_message(self, lead: CommercialLead) -> str:
        niche_label = "马来西亚保险/理财" if lead.niche == TargetNiche.INSURANCE else "软件开发/外包"
        location_str = f"📍 地区: {lead.location_tag}\n" if lead.location_tag else ""
        keywords_str = ", ".join(lead.matched_keywords) if lead.matched_keywords else "意向匹配"

        msg = (
            f"🚨 <b>[CariLead 实时买家预警]</b> ({niche_label})\n"
            f"──────────────────────────\n"
            f"📌 <b>标题:</b> {lead.title}\n"
            f"👤 <b>发帖人:</b> {lead.author_name}\n"
            f"{location_str}"
            f"🔥 <b>意向意图得分:</b> {lead.intent_score}/10\n"
            f"🔑 <b>触发关键词:</b> {keywords_str}\n\n"
            f"📝 <b>建议直接回复草稿:</b>\n"
            f"<i>\"{lead.suggested_reply}\"</i>\n\n"
            f"🔗 <a href=\"{lead.url}\">点击打开小红书原帖跟进</a>"
        )
        return msg

    def send_lead_alert(self, lead: CommercialLead) -> bool:
        if not self.bot_token or not self.chat_id:
            return False

        formatted_msg = self.format_lead_message(lead)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": formatted_msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False
