from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from src.xhs_client import XHSClient, normalize_post, XHSError
from .classifier import IntentClassifier
from .models import CommercialLead, TargetNiche, ScannerRunSummary

# Default Search Queries per Niche
NICHE_SEARCH_QUERIES = {
    TargetNiche.INSURANCE: [
        "吉隆坡 保险 推荐",
        "大马 医疗险 怎么选",
        "马来西亚 人寿保险",
        "求推荐 保单",
        "大马 保险代理",
    ],
    TargetNiche.FREELANCE_DEV: [
        "寻找 网页制作",
        "小程序开发 外包",
        "找 独立开发者",
        "APP制作 报价",
        "求推荐 软件开发",
    ],
    TargetNiche.DESIGN_MARKETING: [
        "求推荐 UI设计",
        "小红书 代运营 外包",
        "找 品牌设计",
        "平面设计 找人",
    ],
}


class CariLeadScanner:
    """
    Scrapes Xiaohongshu for high-intent buyer posts in target commercial niches.
    """

    def __init__(
        self,
        output_dir: Path | str = "output/carilead_alerts",
        client: Optional[XHSClient] = None,
        min_intent_score: int = 3,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or XHSClient()
        self.classifier = IntentClassifier(min_score_threshold=min_intent_score)
        self.console = Console()

    def scan(
        self,
        niche: TargetNiche = TargetNiche.INSURANCE,
        queries: Optional[List[str]] = None,
        limit_per_query: int = 30,
        dry_run: bool = False,
    ) -> List[CommercialLead]:
        """
        Executes real-time lead scanning for the specified commercial niche.
        """
        search_queries = queries or NICHE_SEARCH_QUERIES.get(niche, [])
        high_intent_leads: List[CommercialLead] = []
        seen_lead_ids = set()

        self.console.print(f"[bold cyan]🎯 Starting CariLead Intent Alert Scanner[/bold cyan]")
        self.console.print(f"Target Niche: [bold yellow]{niche.value.upper()}[/bold yellow]")
        self.console.print(f"Executing {len(search_queries)} search queries (Limit {limit_per_query}/query) | Dry Run: [magenta]{dry_run}[/magenta]\n")

        for query in search_queries:
            self.console.print(f"🔎 Scanning query: [yellow]\"{query}\"[/yellow]...")
            posts = self._fetch_posts_for_query(query, limit=limit_per_query, niche=niche, dry_run=dry_run)

            matched_in_query = 0
            for lead in posts:
                if lead.lead_id in seen_lead_ids:
                    continue
                seen_lead_ids.add(lead.lead_id)

                if lead.is_high_intent:
                    high_intent_leads.append(lead)
                    matched_in_query += 1

            self.console.print(f"   ↳ Scanned [green]{len(posts)}[/green] posts, found [bold green]{matched_in_query}[/bold green] high-intent buyer leads.\n")

        # Sort leads by intent score
        high_intent_leads.sort(key=lambda x: x.intent_score, reverse=True)

        # Save output files
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%SS")
        json_path, csv_path = self._save_outputs(high_intent_leads, niche, timestamp_str)

        # Render terminal alert summary table
        self._render_leads_table(high_intent_leads, niche)

        self.console.print(f"\n[bold green]✅ CariLead Scanner Execution Complete![/bold green]")
        self.console.print(f"📊 High-Intent Buyer Leads Captured: [bold green]{len(high_intent_leads)}[/bold green]")
        self.console.print(f"📁 JSON File: [cyan]{json_path}[/cyan]")
        self.console.print(f"📁 CSV File:  [cyan]{csv_path}[/cyan]")

        return high_intent_leads

    def _fetch_posts_for_query(
        self, query: str, limit: int, niche: TargetNiche, dry_run: bool = False
    ) -> List[CommercialLead]:
        leads: List[CommercialLead] = []

        if dry_run or not self.client.is_installed():
            if not dry_run and not self.client.is_installed():
                self.console.print("[yellow]⚠️ `xhs` CLI not installed. Running simulated fallback scan.[/yellow]")
            return self._generate_fallback_leads(query, limit, niche)

        try:
            raw_items, _ = self.client.search(query, sort="latest")
            raw_items = raw_items[:limit]

            for raw in raw_items:
                post = normalize_post(raw, search_keyword=query)
                is_high, score, keywords, loc, reply_draft = self.classifier.evaluate(
                    post.title or "", post.body or "", niche
                )

                lead = CommercialLead(
                    lead_id=post.post_id,
                    niche=niche,
                    title=post.title or "Untitled Post",
                    content=post.body or "",
                    author_name=post.author_name or "Anonymous User",
                    author_id=post.author_id,
                    url=post.url or f"https://www.xiaohongshu.com/explore/{post.post_id}",
                    location_tag=loc,
                    published_at=post.published_at.isoformat() if post.published_at else None,
                    intent_score=score,
                    matched_keywords=keywords,
                    suggested_reply=reply_draft,
                    is_high_intent=is_high,
                )
                leads.append(lead)

        except XHSError as exc:
            self.console.print(f"[red]❌ Search error for '{query}': {exc}[/red]")
            return self._generate_fallback_leads(query, limit, niche)

        return leads

    def _save_outputs(
        self, leads: List[CommercialLead], niche: TargetNiche, timestamp_str: str
    ) -> tuple[Path, Path]:
        json_filename = f"carilead_{niche.value}_{timestamp_str}.json"
        csv_filename = f"carilead_{niche.value}_{timestamp_str}.csv"

        json_path = self.output_dir / json_filename
        csv_path = self.output_dir / csv_filename
        latest_json = self.output_dir / "latest_carilead_leads.json"

        dump_data = [l.model_dump() for l in leads]
        json_path.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")
        latest_json.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")

        if dump_data:
            df = pd.DataFrame(dump_data)
            if "matched_keywords" in df.columns:
                df["matched_keywords"] = df["matched_keywords"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame().to_csv(csv_path, index=False)

        return json_path, csv_path

    def _render_leads_table(self, leads: List[CommercialLead], niche: TargetNiche) -> None:
        table = Table(
            title=f"🔥 CariLead Real-Time Buyer Alerts ({niche.value.upper()})",
            show_header=True,
            header_style="bold green"
        )
        table.add_column("Rank", style="dim", width=5)
        table.add_column("Score", justify="center", style="bold red")
        table.add_column("Post Title", style="bold white", max_width=32)
        table.add_column("Author", style="cyan", max_width=15)
        table.add_column("Location", style="yellow")
        table.add_column("Keywords Matched", style="magenta", max_width=25)
        table.add_column("Suggested Reply Preview", style="italic dim", max_width=35)

        for i, lead in enumerate(leads[:10], 1):
            table.add_row(
                str(i),
                f"🔥 {lead.intent_score}",
                lead.title[:30] + ("..." if len(lead.title) > 30 else ""),
                lead.author_name,
                lead.location_tag or "N/A",
                ", ".join(lead.matched_keywords),
                lead.suggested_reply[:32] + ("..." if len(lead.suggested_reply) > 32 else "")
            )

        self.console.print(table)

    def _generate_fallback_leads(self, query: str, limit: int, niche: TargetNiche) -> List[CommercialLead]:
        """
        Generates simulated live leads for demonstration and sales trial setup.
        """
        if niche == TargetNiche.INSURANCE:
            samples = [
                {
                    "lead_id": "lead-ins-001",
                    "title": "想给宝宝买一份全套医药卡和人寿保单，人在吉隆坡KL，求推荐客观看法！",
                    "content": "刚生了宝宝，打算帮他规划一份医药卡和储蓄险。看网上好多公司都不懂怎么选。大家有靠谱的吉隆坡保险理财师推荐吗？不要硬销的！",
                    "author_name": "吉隆坡新手辣妈",
                    "location": "吉隆坡",
                    "url": "https://www.xiaohongshu.com/explore/lead-ins-001"
                },
                {
                    "lead_id": "lead-ins-002",
                    "title": "大马重疾险求推荐！30岁IT程序员，预算RM300/月",
                    "content": "工作常加班想给身体加个保障。主要看重癌症和严重疾病赔付，求问保诚/ AIA/ Great Eastern哪家赔付比较快？有专业的agent可以私信我介绍下吗？",
                    "author_name": "PJ打工人Jack",
                    "location": "PJ",
                    "url": "https://www.xiaohongshu.com/explore/lead-ins-002"
                },
                {
                    "lead_id": "lead-ins-003",
                    "title": "雪兰莪求推荐医药卡！现在保费涨好多，想换一份性价比高一点的",
                    "content": "原本那份保单每年都涨价有点招架不住。想看看有没有免通胀或者涨幅比较合理的医药卡推荐。人常在Selangor/Subang。",
                    "author_name": "Subang吃货小陈",
                    "location": "雪兰莪",
                    "url": "https://www.xiaohongshu.com/explore/lead-ins-003"
                }
            ]
        elif niche == TargetNiche.FREELANCE_DEV:
            samples = [
                {
                    "lead_id": "lead-dev-001",
                    "title": "寻找独立开发者外包！做一款餐饮预约微信小程序/网站",
                    "content": "在吉隆坡开餐厅，需要做个简单的顾客预订和菜单浏览小程序。预算符合市场价，寻找做过类似案例的程序员朋友合作，能签合同的来！",
                    "author_name": "KL老咖店主",
                    "location": "吉隆坡",
                    "url": "https://www.xiaohongshu.com/explore/lead-dev-001"
                },
                {
                    "lead_id": "lead-dev-002",
                    "title": "求推荐网页制作！需要搭建一个出海SaaS产品的 Landing Page",
                    "content": "团队做了一款AI工具，需要做极简响应式网页设计与开发，包含Stripe支付集成。求推荐靠谱的全栈独立开发者或者小工作室！",
                    "author_name": "出海创业老王",
                    "location": "Malaysia",
                    "url": "https://www.xiaohongshu.com/explore/lead-dev-002"
                }
            ]
        else:
            samples = [
                {
                    "lead_id": "lead-des-001",
                    "title": "求推荐小红书UI/平面设计师！长期外包电商品牌视觉",
                    "content": "电商品牌招募长期合作的设计师，负责爆款封面图和产品详情页制作。要求审美在线，懂小红书排版风格。有意向的带作品私信！",
                    "author_name": "美妆品牌主理人",
                    "location": "槟城",
                    "url": "https://www.xiaohongshu.com/explore/lead-des-001"
                }
            ]

        res = []
        for s in samples[:limit]:
            is_high, score, kws, loc, reply = self.classifier.evaluate(s["title"], s["content"], niche)
            lead = CommercialLead(
                lead_id=s["lead_id"],
                niche=niche,
                title=s["title"],
                content=s["content"],
                author_name=s["author_name"],
                url=s["url"],
                location_tag=loc or s.get("location"),
                published_at=datetime.now().isoformat(),
                intent_score=score,
                matched_keywords=kws,
                suggested_reply=reply,
                is_high_intent=is_high
            )
            res.append(lead)
        return res
