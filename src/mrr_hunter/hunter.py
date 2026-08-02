from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from src.xhs_client import XHSClient, normalize_post, XHSError
from .filters import MoneyFilter, DEFAULT_REVENUE_KEYWORDS
from .models import MRRPostCandidate, MRRHunterSummary

# Default search keywords targeting Chinese indie hackers and global SaaS stories
TARGET_QUERIES = [
    "独立开发 MRR",
    "一人公司 SaaS",
    "出海 盈利",
    "独立开发者 美元",
    "独立产品 订阅",
    "跑通 MRR",
]


class MRRHunter:
    """
    Independent workflow to hunt micro-SaaS and indie hacker revenue stories on Xiaohongshu.
    Reuses base XHSClient without altering any existing codebase files.
    """

    def __init__(
        self,
        output_dir: Path | str = "output/mrr_candidates",
        client: Optional[XHSClient] = None,
        revenue_keywords: Optional[List[str]] = None,
        max_posts_per_query: int = 50,
        fetch_full_content: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or XHSClient()
        self.money_filter = MoneyFilter(target_keywords=revenue_keywords or DEFAULT_REVENUE_KEYWORDS)
        self.max_posts_per_query = max_posts_per_query
        self.fetch_full_content = fetch_full_content
        self.console = Console()

    def run(
        self,
        queries: Optional[List[str]] = None,
        limit_per_query: Optional[int] = None,
        sort: str = "general",
        dry_run: bool = False,
    ) -> List[MRRPostCandidate]:
        """
        Executes the search and filtering pipeline across target queries.
        """
        search_queries = queries or TARGET_QUERIES
        limit = limit_per_query or self.max_posts_per_query
        all_candidates: List[MRRPostCandidate] = []
        seen_post_ids = set()

        self.console.print(f"[bold cyan]🚀 Starting MRR Hunter Pipeline[/bold cyan]")
        self.console.print(f"Target Queries ({len(search_queries)}): [yellow]{', '.join(search_queries)}[/yellow]")
        self.console.print(f"Limit per Query: [bold green]{limit}[/bold green] posts | Dry Run: [bold magenta]{dry_run}[/bold magenta]\n")

        for query in search_queries:
            self.console.print(f"🔍 Searching for query: [bold yellow]\"{query}\"[/bold yellow]...")
            posts = self._search_and_extract(query, limit=limit, sort=sort, dry_run=dry_run)
            
            query_match_count = 0
            for candidate in posts:
                if candidate.post_id in seen_post_ids:
                    continue
                seen_post_ids.add(candidate.post_id)

                # Apply Money Filter
                candidate = self.money_filter.filter_candidate(candidate)
                if candidate.is_mrr_candidate:
                    all_candidates.append(candidate)
                    query_match_count += 1

            self.console.print(f"   ↳ Found [green]{len(posts)}[/green] posts, [bold green]{query_match_count}[/bold green] matched revenue signals.\n")

        # Sort candidates by revenue score and engagement score
        all_candidates.sort(key=lambda c: (c.revenue_score, c.engagement_score), reverse=True)

        # Save output files
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%SS")
        json_path, csv_path = self._save_outputs(all_candidates, timestamp_str)

        # Render summary table in terminal
        self._render_results_table(all_candidates)

        self.console.print(f"\n[bold green]✅ MRR Hunter Completed Successfully![/bold green]")
        self.console.print(f"📁 JSON Output: [bold cyan]{json_path}[/bold cyan]")
        self.console.print(f"📁 CSV Output:  [bold cyan]{csv_path}[/bold cyan]")

        return all_candidates

    def _search_and_extract(
        self, query: str, limit: int, sort: str = "general", dry_run: bool = False
    ) -> List[MRRPostCandidate]:
        candidates: List[MRRPostCandidate] = []

        if dry_run or not self.client.is_installed():
            if not dry_run and not self.client.is_installed():
                self.console.print("[yellow]⚠️ `xhs` CLI not detected. Running in simulated fallback mode.[/yellow]")
            return self._generate_fallback_candidates(query, limit)

        try:
            raw_items, _ = self.client.search(query, sort=sort)
            raw_items = raw_items[:limit]

            for raw in raw_items:
                post = normalize_post(raw, search_keyword=query)
                
                # Optionally fetch full detail body if text is truncated
                if self.fetch_full_content and post.url and len(post.body or "") < 80:
                    try:
                        read_raw, _ = self.client.read(post.url or post.post_id)
                        full_post = normalize_post(read_raw, search_keyword=query)
                        if full_post.body:
                            post.body = full_post.body
                    except Exception:
                        pass  # Fail gracefully to basic content if detailed read fails

                likes = post.likes or 0
                collects = post.favorites or 0
                comments = post.comment_count or 0
                engagement_score = likes * 2 + collects * 3 + comments

                candidate = MRRPostCandidate(
                    post_id=post.post_id,
                    title=post.title or "Untitled Post",
                    content=post.body or "",
                    author_name=post.author_name or "Unknown Author",
                    author_id=post.author_id,
                    url=post.url or f"https://www.xiaohongshu.com/explore/{post.post_id}",
                    likes=likes,
                    collects=collects,
                    comments=comments,
                    engagement_score=engagement_score,
                    query=query,
                    published_at=post.published_at.isoformat() if post.published_at else None,
                )
                candidates.append(candidate)

        except XHSError as exc:
            self.console.print(f"[red]❌ Error searching for '{query}': {exc}[/red]")
            self.console.print("   ↳ Falling back to target simulation mode.")
            return self._generate_fallback_candidates(query, limit)

        return candidates

    def _save_outputs(self, candidates: List[MRRPostCandidate], timestamp_str: str) -> tuple[Path, Path]:
        json_filename = f"mrr_targets_{timestamp_str}.json"
        csv_filename = f"mrr_targets_{timestamp_str}.csv"
        
        json_path = self.output_dir / json_filename
        csv_path = self.output_dir / csv_filename
        latest_json = self.output_dir / "latest_mrr_targets.json"

        # 1. JSON Dump
        dump_data = [c.model_dump() for c in candidates]
        json_path.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")
        latest_json.write_text(json.dumps(dump_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 2. CSV Dump
        if dump_data:
            df = pd.DataFrame(dump_data)
            # Flatten list fields for clean CSV export
            if "matched_keywords" in df.columns:
                df["matched_keywords"] = df["matched_keywords"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
            if "revenue_snippets" in df.columns:
                df["revenue_snippets"] = df["revenue_snippets"].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        else:
            pd.DataFrame().to_csv(csv_path, index=False)

        return json_path, csv_path

    def _render_results_table(self, candidates: List[MRRPostCandidate]) -> None:
        table = Table(title="🏆 MRR Hunter - Top Revenue Candidates Found", show_header=True, header_style="bold magenta")
        table.add_column("Rank", style="dim", width=5)
        table.add_column("Title", style="bold white", max_width=32)
        table.add_column("Author", style="cyan", max_width=15)
        table.add_column("Likes", justify="right", style="green")
        table.add_column("Collects", justify="right", style="yellow")
        table.add_column("Keywords Matched", style="bold red", max_width=25)
        table.add_column("Revenue Snippet Preview", style="italic dim", max_width=40)

        for i, c in enumerate(candidates[:15], 1):
            snippet = c.revenue_snippets[0] if c.revenue_snippets else c.content[:60]
            table.add_row(
                str(i),
                c.title[:30] + ("..." if len(c.title) > 30 else ""),
                c.author_name,
                str(c.likes),
                str(c.collects),
                ", ".join(c.matched_keywords),
                snippet[:38] + ("..." if len(snippet) > 38 else "")
            )

        self.console.print(table)

    def _generate_fallback_candidates(self, query: str, limit: int) -> List[MRRPostCandidate]:
        """
        Simulated candidate fallback for demonstration and offline testing.
        """
        mock_posts = [
            {
                "post_id": "mrr-demo-101",
                "title": "一人公司第6个月：独立开发SaaS月收入突破$3,500 MRR经验分享",
                "content": "做独立产品6个月了，今天MRR终于突破$3,500美元！主要靠订阅制。刚开始只有零星用户，后来做了海外SEO和ProductHunt发版。分享3点独立开发者做出海SaaS的避坑指南...",
                "author_name": "搞钱研究所_Leo",
                "likes": 842,
                "collects": 1230,
                "comments": 195,
                "url": "https://www.xiaohongshu.com/discovery/item/demo101"
            },
            {
                "post_id": "mrr-demo-102",
                "title": "独立开发者美金上榜：跑通第一个$1000 MRR全过程",
                "content": "不用融资，一人团队如何做到月营收5万/月？核心是选对小众Niche。产品上线第二个月，订阅数突破200个，MRR达到$1,200。记录我的独立开发复盘...",
                "author_name": "IndieHacker_Jack",
                "likes": 612,
                "collects": 940,
                "comments": 88,
                "url": "https://www.xiaohongshu.com/discovery/item/demo102"
            },
            {
                "post_id": "mrr-demo-103",
                "title": "出海盈利实录：写给想赚美元的独立产品开发者",
                "content": "分享一个适合单兵作战的Micro-SaaS方向。我的工具软件定位于海外市场，采用年订阅+月订阅模式。目前ARR达到$45,000美元。主要流量来自Twitter和XHS...",
                "author_name": "全栈出海指南",
                "likes": 420,
                "collects": 610,
                "comments": 64,
                "url": "https://www.xiaohongshu.com/discovery/item/demo103"
            }
        ]
        
        res = []
        for p in mock_posts[:limit]:
            candidate = MRRPostCandidate(
                post_id=p["post_id"],
                title=p["title"],
                content=p["content"],
                author_name=p["author_name"],
                url=p["url"],
                likes=p["likes"],
                collects=p["collects"],
                comments=p["comments"],
                engagement_score=p["likes"] * 2 + p["collects"] * 3 + p["comments"],
                query=query,
                published_at=datetime.now().isoformat()
            )
            res.append(candidate)
        return res
