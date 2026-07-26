from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

import typer
from rich.console import Console
from rich.table import Table

from .discovery.query_planner import QueryPlanner, load_research_pack
from .manual_import import import_records
from .reports.demand_report import compare_reports, generate_demand_report
from .research_analysis import analyze_run
from .research_models import CrawlOptions
from .research_runner import ResearchRunner
from .research_storage import ResearchStorage
from .sources.registry import build_registry


sources_app = typer.Typer(no_args_is_help=True, help="Inspect multi-source adapter availability.")
research_app = typer.Typer(invoke_without_command=True, no_args_is_help=False, help="Plan, run, analyze, and report US demand research.")
import_app = typer.Typer(no_args_is_help=True, help="Safely import manual source exports.")
console = Console()


@sources_app.command("status")
def sources_status() -> None:
    table = Table("Source", "Status", "Credentials", "Role / detail")
    for name, adapter in build_registry().items():
        result = adapter.health_check()
        table.add_row(
            name, result["status"], "required" if result.get("credential_required") else "none",
            str(result.get("detail") or ""),
        )
    console.print(table)


@research_app.command("plan")
def research_plan(
    pack: Path = typer.Option(..., exists=True, dir_okay=False),
    sources: str | None = typer.Option(None, "--sources"),
    source: list[str] | None = typer.Option(None, "--source"),
    recent_days: int = 365,
    max_records: int = 100,
    max_comments: int = 500,
    max_reddit_comments: int = 500,
    max_youtube_comments: int = 300,
    max_reviews: int = 300,
    max_competitors: int = 15,
    max_runtime_minutes: int = 90,
) -> None:
    research_pack = load_research_pack(pack)
    selected = _sources(research_pack.sources, sources, source)
    options = CrawlOptions(
        recent_days=recent_days, max_records=max_records, max_comments=max_comments,
        max_reddit_comments=max_reddit_comments, max_youtube_comments=max_youtube_comments,
        max_reviews=max_reviews, max_competitors=max_competitors,
        max_runtime_minutes=max_runtime_minutes,
    )
    result = ResearchRunner().plan(research_pack, selected, options)
    console.print_json(json.dumps(result))


@research_app.command("run")
def research_run(
    pack: Path = typer.Option(..., exists=True, dir_okay=False),
    sources: str | None = typer.Option(None, "--sources"),
    source: list[str] | None = typer.Option(None, "--source"),
    recent_days: int = 365,
    max_records: int = 100,
    max_comments: int = 500,
    max_reddit_comments: int = 500,
    max_youtube_comments: int = 300,
    max_reviews: int = 300,
    max_competitors: int = 15,
    max_runtime_minutes: int = 90,
    incremental: bool = True,
    resume: bool = False,
    force_refresh: bool = False,
    dry_run: bool = False,
    classification_mode: Literal["rules", "llm"] = "rules",
) -> None:
    research_pack = load_research_pack(pack)
    selected = _sources(research_pack.sources, sources, source)
    options = CrawlOptions(
        recent_days=recent_days, max_records=max_records, max_comments=max_comments,
        max_reddit_comments=max_reddit_comments, max_youtube_comments=max_youtube_comments,
        max_reviews=max_reviews, max_competitors=max_competitors,
        max_runtime_minutes=max_runtime_minutes, incremental=incremental,
        resume=resume, force_refresh=force_refresh,
    )
    runner = ResearchRunner()
    if dry_run:
        console.print_json(json.dumps(runner.plan(research_pack, selected, options)))
        return
    result = runner.run(research_pack, selected, options)
    console.print_json(json.dumps(result))
    if result["status"] == "completed":
        analysis = analyze_run(runner.storage, result["run_id"], research_pack.slug, classification_mode)
        console.print_json(json.dumps(analysis, default=str))


@research_app.command("analyze")
def research_analyze(
    pack: Path = typer.Option(..., exists=True, dir_okay=False),
    classification_mode: Literal["rules", "llm"] = "rules",
    run_id: int | None = None,
) -> None:
    research_pack = load_research_pack(pack)
    storage = ResearchStorage()
    selected_run = run_id or _latest_run(storage, research_pack.slug)
    console.print_json(json.dumps(analyze_run(storage, selected_run, research_pack.slug, classification_mode), default=str))


@research_app.command("report")
def research_report(
    pack: Path = typer.Option(..., exists=True, dir_okay=False),
    run_id: int | None = None,
) -> None:
    research_pack = load_research_pack(pack)
    storage = ResearchStorage()
    selected_run = run_id or _latest_run(storage, research_pack.slug)
    paths = generate_demand_report(storage, selected_run, research_pack.slug)
    table = Table("Output", "Path")
    for name, path in paths.items():
        table.add_row(name, str(path))
    console.print(table)


@research_app.command("compare")
def research_compare(
    packs: list[Path] = typer.Option(..., "--packs", exists=True, dir_okay=False),
) -> None:
    storage = ResearchStorage()
    pack_runs = {}
    for path in packs:
        pack = load_research_pack(path)
        pack_runs[pack.slug] = _latest_run(storage, pack.slug)
    output = compare_reports(storage, pack_runs)
    console.print(f"Wrote comparison: {output}")


@import_app.command("reviews")
def import_reviews(
    source: str = typer.Option(...),
    file: Path = typer.Option(..., exists=True, dir_okay=False),
    pack: str = typer.Option("manual_import_us"),
) -> None:
    storage = ResearchStorage()
    run_id = storage.create_run(pack, {"manual_import": str(file), "source": source})
    try:
        result = import_records(source, file, storage, run_id)
        storage.finish_run(run_id, "completed")
    except Exception as exc:
        storage.finish_run(run_id, "failed", str(exc))
        raise
    console.print_json(json.dumps({"run_id": run_id, **result}))


@import_app.command("records")
def import_generic_records(
    source: str = typer.Option(...),
    file: Path = typer.Option(..., exists=True, dir_okay=False),
    pack: str = typer.Option("manual_import_us"),
) -> None:
    import_reviews(source, file, pack)


def register_us_cli(app: typer.Typer, legacy_research: Callable) -> None:
    app.add_typer(sources_app, name="sources")
    app.add_typer(research_app, name="research")
    app.add_typer(import_app, name="import")

    @research_app.callback()
    def legacy_callback(
        ctx: typer.Context,
        industry: str | None = None,
        country: str = "malaysia",
        research_question: str = "all",
        recent_days: int = 180,
        query_limit: int | None = None,
        posts_per_query: int = 10,
        fetch_comments: bool = False,
        max_comments_per_post: int = 50,
        resume: bool = False,
        incremental: bool = True,
        force_refresh: bool = False,
        max_runtime_minutes: int = 90,
        max_total_requests: int = 250,
        max_detail_posts: int = 100,
        max_comment_requests: int = 150,
        controlled_test: bool = False,
        dry_run: bool = False,
    ) -> None:
        """Without a subcommand, retain the legacy Malaysia XHS insurance workflow."""
        if ctx.invoked_subcommand is not None:
            return
        if industry is None:
            console.print(ctx.get_help())
            raise typer.Exit()
        legacy_research(
            industry=industry, country=country, research_question=research_question,
            recent_days=recent_days, query_limit=query_limit, posts_per_query=posts_per_query,
            fetch_comments=fetch_comments, max_comments_per_post=max_comments_per_post,
            resume=resume, incremental=incremental, force_refresh=force_refresh,
            max_runtime_minutes=max_runtime_minutes, max_total_requests=max_total_requests,
            max_detail_posts=max_detail_posts, max_comment_requests=max_comment_requests,
            controlled_test=controlled_test, dry_run=dry_run,
        )


def _sources(defaults: list[str], csv_sources: str | None, repeated: list[str] | None) -> list[str]:
    if repeated:
        return list(dict.fromkeys(repeated))
    if csv_sources:
        return [s.strip() for s in csv_sources.split(",") if s.strip()]
    return defaults


def _latest_run(storage: ResearchStorage, pack_slug: str) -> int:
    row = storage.conn.execute(
        "SELECT id FROM research_runs WHERE pack_slug=? ORDER BY id DESC LIMIT 1", (pack_slug,),
    ).fetchone()
    if not row:
        raise typer.BadParameter(f"no research run found for {pack_slug}")
    return int(row[0])
