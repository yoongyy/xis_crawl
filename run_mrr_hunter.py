#!/usr/bin/env python3
"""
MRR Hunter Entry Point
Scrapes Xiaohongshu for Chinese indie hackers, Micro-SaaS projects, and MRR revenue stories.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.mrr_hunter import MRRHunter
from src.mrr_hunter.hunter import TARGET_QUERIES

app = typer.Typer(
    help="🚀 MRR Hunter: Scrape & Filter Xiaohongshu for Indie Hacker Revenue & SaaS Stories"
)


@app.command()
def main(
    queries: Optional[List[str]] = typer.Option(
        None,
        "--query",
        "-q",
        help="Custom search queries to override default list.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum posts to scrape per query.",
    ),
    output_dir: str = typer.Option(
        "output/mrr_candidates",
        "--output",
        "-o",
        help="Output directory path for CSV/JSON files.",
    ),
    sort: str = typer.Option(
        "general",
        "--sort",
        "-s",
        help="Sort type for XHS search (general or latest).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run in dry-run mode without executing live XHS queries.",
    ),
):
    """
    Run MRR Hunter on Xiaohongshu to find micro-SaaS and indie developer clone targets.
    """
    hunter = MRRHunter(
        output_dir=output_dir,
        max_posts_per_query=limit,
    )
    
    selected_queries = queries if queries else TARGET_QUERIES

    hunter.run(
        queries=selected_queries,
        limit_per_query=limit,
        sort=sort,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    app()
