from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.table import Table

from .complaint_classifier import ComplaintClassifier
from .audit import write_data_quality_audit
from .config import load_config
from .deduplicator import Deduplicator
from .extraction_quality import clean_browser_detail
from .insurance_pipeline import InsuranceCrawler
from .insurance_browser_import import import_browser_insurance
from .insurance_queries import (
    CONTROLLED_QUERIES,
    INSURANCE_RESEARCH_QUESTIONS,
    build_crawl_plan,
    insurance_queries,
)
from .insurance_report import generate_insurance_reports
from .malaysia_classifier import MalaysiaClassifier
from .market_report import generate_market_intelligence
from .query_matrix import queries_for
from .report_generator import generate_report
from .storage import COLLECTIONS, Storage
from .config import load_insurance_config
from .utils import clean_text, dump_json, is_recent, random_delay, setup_logging
from .xhs_client import (
    XHSAuthError,
    XHSClient,
    XHSError,
    XHSRateLimitError,
    XHSRiskControlError,
    normalize_comment,
    normalize_post,
)


app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def status() -> None:
    """Check whether the xhs CLI is installed and authenticated."""
    client = XHSClient()
    if not client.is_installed():
        console.print("[yellow]xhs CLI not found.[/yellow]")
        console.print("Install and authenticate with:")
        console.print("  uv tool install xiaohongshu-cli")
        console.print("  xhs login")
        console.print("  xhs status")
        raise typer.Exit(code=1)
    try:
        result = client.status()
    except Exception as exc:
        console.print(f"[red]xhs status failed:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print("[green]xhs CLI responded.[/green]")
    if result.stdout.strip():
        console.print(result.stdout.strip())
    if result.stderr.strip():
        console.print(f"[yellow]{result.stderr.strip()}[/yellow]")


@app.command()
def search(
    config: Path = typer.Option(Path("config/property_malaysia.yaml")),
    days: int = 90,
    max_posts: int = 50,
    fetch_comments: bool = False,
    max_comments_per_post: int = 100,
    sort: Literal["latest", "popular", "general"] = "latest",
    query_group: Literal["all", "location", "industry", "complaint"] = "all",
    delay_min: float | None = None,
    delay_max: float | None = None,
    resume: bool = False,
    dry_run: bool = False,
    classification_mode: Literal["rules", "llm"] = "rules",
    malaysia_threshold: float | None = None,
    research_question: Literal[
        "acquisition", "portal_cost", "lead_quality", "customer_service", "listing_supply",
        "conversion", "follow_up", "platform_switching", "operational_workflow",
        "reputation_and_trust", "buyer_tenant_pain", "landlord_seller_pain",
        "solution_demand", "all",
    ] = "all",
    query_limit: int | None = None,
    posts_per_query: int = 10,
    recent_days: int | None = None,
    min_comments: int = 0,
    min_engagement: int = 0,
    exclude_listings: bool = True,
    exclude_recruitment: bool = True,
    exclude_promotions: bool = True,
) -> None:
    """Search XHS, normalize posts/comments, classify, and persist local research data."""
    setup_logging(Path("data/crawler.log"))
    cfg = load_config(config)
    threshold = malaysia_threshold if malaysia_threshold is not None else cfg.malaysia_threshold
    delay_min = cfg.request_delay.min_seconds if delay_min is None else delay_min
    delay_max = cfg.request_delay.max_seconds if delay_max is None else delay_max
    keywords = queries_for(research_question, query_limit) if research_question != "all" or query_limit else cfg.keywords(query_group)
    days = recent_days if recent_days is not None else days
    storage = Storage()
    client = XHSClient()
    malaysia = MalaysiaClassifier(threshold=threshold, weights=cfg.weights)
    complaints = ComplaintClassifier(industry=cfg.industry, mode=classification_mode)
    post_dedupe = Deduplicator()
    comment_dedupe = Deduplicator()
    raw_dir = Path("data/raw") / date.today().isoformat()

    console.print(f"Loaded {len(keywords)} keyword(s) from {config}")
    if dry_run:
        _print_dry_run(keywords, max_posts, fetch_comments, max_comments_per_post, sort, delay_min, delay_max)
        return
    if not client.is_installed():
        console.print("[red]xhs CLI not found.[/red] Install with: uv tool install xiaohongshu-cli")
        raise typer.Exit(code=1)

    run_id = storage.create_run(cfg.industry, json.dumps(cfg.model_dump(), ensure_ascii=False, default=str))
    total_posts = 0
    consecutive_risk_errors = 0
    try:
        for keyword in keywords:
            if total_posts >= max_posts:
                break
            console.print(f"[bold]Searching:[/bold] {keyword}")
            try:
                raw_posts, envelope = client.search(keyword, sort=sort)
                dump_json(raw_dir / f"search_{run_id}_{_safe(keyword)}.json", envelope)
                storage.save_search_query(run_id, keyword, sort, len(raw_posts))
                consecutive_risk_errors = 0
            except (XHSRiskControlError, XHSRateLimitError) as exc:
                consecutive_risk_errors += 1
                storage.save_error(run_id, "search", str(exc), keyword=keyword, error_type=type(exc).__name__)
                if consecutive_risk_errors >= cfg.risk_control.max_consecutive_errors:
                    console.print("[red]Repeated CAPTCHA/risk-control/rate-limit responses. Stopping crawl.[/red]")
                    break
                continue
            except (XHSAuthError, XHSError, FileNotFoundError) as exc:
                storage.save_error(run_id, "search", str(exc), keyword=keyword, error_type=type(exc).__name__)
                console.print(f"[red]Stopping:[/red] {exc}")
                break

            for raw in raw_posts:
                if total_posts >= max_posts:
                    break
                if total_posts >= posts_per_query * max(1, keywords.index(keyword) + 1):
                    break
                post = normalize_post(raw, search_keyword=keyword)
                if post_dedupe.is_duplicate(post.post_id, post.url, f"{post.title} {post.body}"):
                    continue
                if not is_recent(post.published_at, days):
                    continue
                post = _classify_post(post, malaysia)
                if exclude_recruitment and post.content_origin == "recruitment":
                    continue
                if exclude_promotions and post.content_origin in {"vendor_promotion", "service_advertisement"}:
                    continue
                if exclude_listings and post.content_origin == "property_listing":
                    continue
                storage.save_post(post)
                storage.save_findings(complaints.classify("post", post.post_id, post.url, f"{post.title or ''} {post.body or ''}"))
                total_posts += 1
                console.print(f"Saved post {total_posts}/{max_posts}: {post.post_id}")
                random_delay(delay_min, delay_max)

                if fetch_comments and post.url:
                    _fetch_comments(
                        client, storage, complaints, malaysia, comment_dedupe, run_id,
                        post.post_id, post.url, max_comments_per_post, raw_dir, delay_min, delay_max,
                    )
        storage.finish_run(run_id, "completed")
    except KeyboardInterrupt:
        storage.finish_run(run_id, "interrupted")
        console.print("[yellow]Interrupted. Partial progress was saved.[/yellow]")
    finally:
        storage.export_csvs()
        console.print("Normalized CSVs written to data/normalized/")


@app.command()
def analyze(
    industry: str = "property",
    days: int = 90,
    classification_mode: Literal["rules", "llm"] = "rules",
    malaysia_threshold: float = 0.60,
) -> None:
    """Re-run local rule classification over existing stored posts and comments."""
    storage = Storage()
    malaysia = MalaysiaClassifier(threshold=malaysia_threshold)
    complaints = ComplaintClassifier(industry=industry, mode=classification_mode)
    findings_count = 0
    for _, row in storage.read_frame("posts").iterrows():
        text = clean_text(f"{row.get('title') or ''} {row.get('body') or ''}")
        result = malaysia.classify(text)
        if result.is_relevant:
            found = complaints.classify("post", str(row["post_id"]), row.get("url"), text)
            storage.save_findings(found)
            findings_count += len(found)
    for _, row in storage.read_frame("comments").iterrows():
        text = clean_text(row.get("text"))
        result = malaysia.classify(text)
        if result.is_relevant:
            found = complaints.classify("comment", str(row["comment_id"]), row.get("url"), text)
            storage.save_findings(found)
            findings_count += len(found)
    storage.export_csvs()
    console.print(f"Analysis complete. Added {findings_count} finding(s).")


@app.command("audit-data")
def audit_data() -> None:
    """Inspect current normalized exports and write a data quality audit."""
    path = write_data_quality_audit()
    console.print(f"Wrote audit report: {path}")


@app.command("query-plan")
def query_plan(
    research_question: Literal[
        "acquisition", "portal_cost", "lead_quality", "customer_service", "listing_supply",
        "conversion", "follow_up", "platform_switching", "operational_workflow",
        "reputation_and_trust", "buyer_tenant_pain", "landlord_seller_pain",
        "solution_demand", "all",
    ] = "all",
    query_limit: int | None = None,
) -> None:
    """Show the targeted Malaysia property query matrix without crawling."""
    selected = queries_for(research_question, query_limit)
    table = Table("Rank", "Query")
    for index, query in enumerate(selected, start=1):
        table.add_row(str(index), query)
    console.print(table)
    console.print(f"{len(selected)} query/queries selected.")


@app.command("plan-crawl")
def plan_insurance_crawl(
    industry: str = "insurance",
    country: str = "malaysia",
    frequency: Literal["daily", "weekly", "monthly"] = "daily",
    query_limit: int | None = None,
    posts_per_query: int = 10,
    yes: bool = False,
) -> None:
    """Show a conservative insurance crawl schedule without making XHS requests."""
    if industry.lower() != "insurance" or country.lower() != "malaysia":
        raise typer.BadParameter("This planner currently supports --industry insurance --country malaysia")
    plan = build_crawl_plan(frequency, query_limit, posts_per_query)
    storage = Storage()
    completed_frame = storage.read_frame("query_runs")
    completed = set(completed_frame.get("query", [])) if not completed_frame.empty else set()
    table = Table("#", "Query", "State", "Reason")
    for index, query in enumerate(plan.selected_queries, start=1):
        was_completed = query in completed
        table.add_row(str(index), query, "skip" if was_completed else "selected", "completed previously" if was_completed else "scheduled")
    console.print(table)
    console.print(f"Expected maximum requests: {plan.expected_max_requests}")
    console.print(f"Expected maximum detail opens: {plan.expected_max_post_opens}")
    console.print(f"Estimated runtime: {plan.estimated_runtime_minutes} minute(s)")
    console.print(f"Previously completed: {sum(query in completed for query in plan.selected_queries)}")
    if not yes and not typer.confirm("Approve this crawl plan?"):
        raise typer.Abort()
    console.print("Plan approved. No crawl was started by plan-crawl.")


@app.command("xhs-research")
def insurance_research(
    industry: str = "insurance",
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
    """Run staged, incremental Malaysia insurance research with conservative limits."""
    if industry.lower() != "insurance" or country.lower() != "malaysia":
        raise typer.BadParameter("This command currently supports --industry insurance --country malaysia")
    if research_question not in INSURANCE_RESEARCH_QUESTIONS:
        raise typer.BadParameter(f"--research-question must be one of: {', '.join(INSURANCE_RESEARCH_QUESTIONS)}")
    config = load_insurance_config()
    queries = list(CONTROLLED_QUERIES) if controlled_test else insurance_queries(research_question, query_limit)
    if controlled_test:
        posts_per_query = min(posts_per_query, 10)
        max_comments_per_post = min(max_comments_per_post, 30)
        max_runtime_minutes = min(max_runtime_minutes, 45)
        max_detail_posts = min(max_detail_posts, 30)
        config.crawl_limits.max_detail_posts_per_query = 5
        config.risk_control.stop_on_first_risk_event = True
    elif query_limit:
        queries = queries[:query_limit]
    _print_insurance_plan(
        queries, posts_per_query, max_detail_posts, max_comment_requests,
        max_runtime_minutes, config.open_fraction,
    )
    if dry_run:
        return
    client = XHSClient()
    if not client.is_installed():
        console.print("[red]xhs CLI not found.[/red] Install with: uv tool install xiaohongshu-cli")
        raise typer.Exit(code=1)
    resume_command = (
        "python main.py research --industry insurance --country malaysia "
        f"--research-question {research_question} --recent-days {recent_days} "
        f"--query-limit {len(queries)} --posts-per-query {posts_per_query} --incremental --resume"
    )
    crawler = InsuranceCrawler(Storage(), client, config)
    metrics = crawler.run(
        queries, recent_days=recent_days, posts_per_query=posts_per_query,
        fetch_comments=fetch_comments, max_comments_per_post=max_comments_per_post,
        max_runtime_minutes=max_runtime_minutes, max_total_requests=max_total_requests,
        max_detail_posts=max_detail_posts, max_comment_requests=max_comment_requests,
        incremental=incremental or resume, force_refresh=force_refresh,
        resume_command=resume_command,
    )
    _print_insurance_metrics(metrics)
    if metrics.stopped_reason:
        console.print(f"Resume with: [bold]{resume_command}[/bold]")
    paths = generate_insurance_reports(Storage())
    console.print(f"Generated {len(paths)} insurance report/interface files.")


@app.command("insurance-report")
def insurance_report() -> None:
    """Generate insurance reports from stored data without crawling."""
    paths = generate_insurance_reports(Storage())
    table = Table("Output", "Path")
    for name, path in paths.items():
        table.add_row(name, str(path))
    console.print(table)


@app.command("import-insurance-browser")
def import_insurance_browser(
    discovery_path: Path = Path("data/raw/2026-07-19/insurance/chrome_insurance_discovery.json"),
    details_path: Path = Path("data/raw/2026-07-19/insurance/chrome_insurance_details.json"),
) -> None:
    """Import a controlled Chrome insurance crawl, then regenerate reports."""
    metrics = import_browser_insurance(Storage(), discovery_path, details_path)
    _print_insurance_metrics(metrics)
    paths = generate_insurance_reports(Storage())
    console.print(f"Generated {len(paths)} insurance report/interface files.")


@app.command("repair-browser-raw")
def repair_browser_raw(
    raw_path: Path = Path("data/raw/2026-07-19/chrome_rednote_malaysia_property_5.json"),
    reset_existing: bool = False,
    classification_mode: Literal["rules", "llm"] = "rules",
    malaysia_threshold: float = 0.60,
) -> None:
    """Rebuild normalized data from saved Chrome raw JSON using clean extraction rules."""
    storage = Storage()
    if reset_existing:
        storage.clear_collections(("posts", "comments", "findings", "search_queries", "crawl_runs"))
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    malaysia = MalaysiaClassifier(threshold=malaysia_threshold)
    complaints = ComplaintClassifier(industry="property", mode=classification_mode)
    run_id = storage.create_run("property", json.dumps({"source": "chrome:rednote:clean_repair", "raw_path": str(raw_path)}, ensure_ascii=False))
    keyword = payload.get("keyword") or payload.get("search", {}).get("keyword") or "unknown"
    storage.save_search_query(run_id, keyword, "browser-clean-repair", len(payload.get("search", {}).get("notes", [])))
    post_count = 0
    comment_count = 0
    finding_count = 0
    for detail in payload.get("details", []):
        result = clean_browser_detail(detail)
        if not result.post:
            continue
        post = _classify_post(result.post, malaysia)
        storage.save_post(post)
        post_findings = complaints.classify("post", post.post_id, post.url, f"{post.title or ''} {post.body or ''}")
        for finding in post_findings:
            finding.post_id = post.post_id
            finding.author_name = post.author_name
            finding.content_origin = post.content_origin
            finding.organic_evidence_weight *= post.organic_evidence_weight
        storage.save_findings(post_findings)
        finding_count += len(post_findings)
        post_count += 1
        for comment in result.comments:
            cr = malaysia.classify(comment.text)
            comment.malaysia_score = cr.score
            comment.malaysia_signals = cr.signals
            comment.language = cr.language
            comment.is_malaysia_relevant = cr.is_relevant
            storage.save_comment(comment)
            comment_findings = complaints.classify("comment", comment.comment_id, comment.url, comment.text)
            for finding in comment_findings:
                finding.post_id = post.post_id
                finding.author_name = comment.author_name
                finding.content_origin = "organic_experience" if not comment.is_author_reply else "author_reply"
                finding.independence_weight = 0.0 if comment.is_author_reply else finding.independence_weight
            storage.save_findings(comment_findings)
            finding_count += len(comment_findings)
            comment_count += 1
    storage.finish_run(run_id, "completed")
    storage.export_csvs()
    console.print(f"Clean repair complete: {post_count} posts, {comment_count} comments, {finding_count} findings.")


@app.command("report")
def report_command(industry: str = "property", days: int = 90, top: int = 20) -> None:
    """Generate Markdown, CSV, and JSON reports from existing local data."""
    storage = Storage()
    md_path, csv_path, json_path = generate_report(storage, industry=industry, days=days, top=top)
    table = Table("Output", "Path")
    table.add_row("Markdown", str(md_path))
    table.add_row("CSV", str(csv_path))
    table.add_row("JSON", str(json_path))
    console.print(table)


@app.command("market-report")
def market_report() -> None:
    """Generate the serious Malaysia property market-intelligence report package."""
    paths = generate_market_intelligence(Storage())
    table = Table("Output", "Path")
    for name, path in paths.items():
        table.add_row(name, str(path))
    console.print(table)


@app.command("migrate-to-mongo")
def migrate_to_mongo(
    sqlite_path: Path = Path("data/research.sqlite3"),
    replace_existing: bool = False,
) -> None:
    """Idempotently migrate the existing SQLite research database to MongoDB."""
    storage = Storage(require_mongo=True)
    if replace_existing:
        storage.clear_collections(COLLECTIONS)
    counts = storage.migrate_from_sqlite(sqlite_path)
    table = Table("Collection", "Migrated", "Cloud total")
    for collection, count in counts.items():
        table.add_row(collection, str(count), str(len(storage.read_frame(collection))))
    console.print(f"MongoDB database: [bold]{storage.database_name}[/bold]")
    console.print(table)


def _fetch_comments(
    client: XHSClient,
    storage: Storage,
    complaints: ComplaintClassifier,
    malaysia: MalaysiaClassifier,
    comment_dedupe: Deduplicator,
    run_id: int,
    post_id: str,
    post_url: str,
    max_comments: int,
    raw_dir: Path,
    delay_min: float,
    delay_max: float,
) -> None:
    try:
        raw_comments, envelope = client.comments(post_url, all_comments=True)
        dump_json(raw_dir / f"comments_{run_id}_{_safe(post_id)}.json", envelope)
    except (XHSRiskControlError, XHSRateLimitError, XHSAuthError, XHSError) as exc:
        storage.save_error(run_id, "comments", str(exc), url=post_url, error_type=type(exc).__name__)
        console.print(f"[yellow]Skipping comments for {post_id}: {exc}[/yellow]")
        return
    saved = 0
    for raw_comment in raw_comments:
        for comment in normalize_comment(raw_comment, post_id=post_id, post_url=post_url):
            if saved >= max_comments:
                return
            if comment_dedupe.is_duplicate(comment.comment_id, comment.url, comment.text):
                continue
            result = malaysia.classify(comment.text)
            comment.malaysia_score = result.score
            comment.malaysia_signals = result.signals
            comment.language = result.language
            comment.is_malaysia_relevant = result.is_relevant
            storage.save_comment(comment)
            storage.save_findings(complaints.classify("comment", comment.comment_id, comment.url, comment.text))
            saved += 1
            random_delay(delay_min, delay_max)


def _classify_post(post, classifier: MalaysiaClassifier):
    result = classifier.classify(f"{post.title or ''} {post.body or ''} {' '.join(post.hashtags)}")
    post.malaysia_score = result.score
    post.malaysia_signals = result.signals
    post.language = result.language
    post.is_malaysia_relevant = result.is_relevant
    return post


def _print_dry_run(keywords: list[str], max_posts: int, fetch_comments: bool, max_comments: int, sort: str, delay_min: float, delay_max: float) -> None:
    table = Table("Setting", "Value")
    table.add_row("keywords", str(len(keywords)))
    table.add_row("first keyword", keywords[0] if keywords else "none")
    table.add_row("max_posts", str(max_posts))
    table.add_row("fetch_comments", str(fetch_comments))
    table.add_row("max_comments_per_post", str(max_comments))
    table.add_row("sort", sort)
    table.add_row("delay", f"{delay_min}-{delay_max}s")
    console.print(table)


def _print_insurance_plan(queries, posts_per_query, max_detail_posts, max_comment_requests, runtime, open_fraction) -> None:
    table = Table("#", "Insurance query")
    for index, query in enumerate(queries, start=1):
        table.add_row(str(index), query)
    console.print(table)
    expected_opens = min(max_detail_posts, sum(max(1, int(posts_per_query * open_fraction)) for _ in queries))
    console.print(f"Discovery requests: {len(queries)}")
    console.print(f"Maximum discovered posts: {len(queries) * posts_per_query}")
    console.print(f"Expected maximum detail opens after pre-filtering: {expected_opens}")
    console.print(f"Maximum comment requests: {min(max_comment_requests, expected_opens)}")
    console.print(f"Maximum runtime: {runtime} minute(s); one active request at a time")


def _print_insurance_metrics(metrics) -> None:
    table = Table("Metric", "Count")
    for label, value in (
        ("Discovered posts", metrics.discovered_posts),
        ("Detail posts opened", metrics.detail_posts_opened),
        ("Comment threads fetched", metrics.comment_threads_fetched),
        ("Requests avoided", metrics.requests_avoided),
        ("Duplicate comments", metrics.duplicate_comments),
        ("Rejected promotional posts", metrics.rejected_promotional_posts),
        ("Active purchase requests", metrics.active_purchase_requests),
        ("Recommendation requests", metrics.recommendation_requests),
        ("Switching signals", metrics.switching_signals),
        ("Claim-help signals", metrics.claim_help_signals),
    ):
        table.add_row(label, str(value))
    console.print(table)


def _safe(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)[:80]


# Register the additive multi-source command groups after the legacy command
# functions exist. The research group callback preserves the prior
# `research --industry insurance ...` invocation.
from .us_cli import register_us_cli

register_us_cli(app, insurance_research)
