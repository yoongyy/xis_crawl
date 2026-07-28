from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .lovable_blockers import blockers_plan, run_lovable_blockers
from .malaysia_opportunities import opportunities_plan, run_global_to_malaysia
from .opportunity_notifications import notify_opportunity_candidates
from .providers.apify_client import ApifyClient, ApifyError
from .providers.apify_registry import ApifyActorRegistry


apify_app = typer.Typer(no_args_is_help=True, help="Inspect and approve configured Apify Actors.")
blockers_app = typer.Typer(no_args_is_help=True, help="Plan or run Lovable Rescue Watch.")
opportunities_app = typer.Typer(
    no_args_is_help=True,
    help="Plan or run the staged Global-to-Malaysia Opportunity Dig.",
)
console = Console()


@apify_app.command("status")
def apify_status(
    config: Path = typer.Option(Path("config/apify_actors.yaml"), help="Actor registry YAML."),
) -> None:
    """Show token presence and Actor configuration without exposing secrets."""
    registry = ApifyActorRegistry(config)
    client = ApifyClient()
    console.print(
        f"APIFY API token pool: [{'green' if client.configured else 'yellow'}]"
        f"{f'configured ({client.token_count})' if client.configured else 'missing'}[/]"
    )
    table = Table("Source", "Actor ID", "Metadata", "Approval", "Executable", "Reason")
    for source in registry.sources():
        actor = registry.actor(source)
        allowed, reason = registry.can_execute(source)
        metadata = bool(
            actor
            and actor.actor_name
            and actor.developer
            and actor.expected_input_schema
            and actor.expected_output_schema
        )
        table.add_row(
            source,
            "configured" if actor and actor.actor_id else f"missing ({actor.actor_id_env if actor else 'unknown'})",
            "complete" if metadata else "incomplete",
            registry.effective_approval(source),
            "yes" if allowed else "no",
            reason,
        )
    console.print(table)


@apify_app.command("test")
def apify_test(
    source: str = typer.Option(..., help="Configured source to test, for example reddit."),
    config: Path = typer.Option(Path("config/apify_actors.yaml"), help="Actor registry YAML."),
) -> None:
    """Run a maximum-three-record Actor test and approve only validated output."""
    registry = ApifyActorRegistry(config)
    client = ApifyClient()
    actor = registry.actor(source)
    if not client.configured:
        console.print("[red]Cannot test: no Apify API token is configured.[/red]")
        raise typer.Exit(code=1)
    ready, reason = registry.can_test(source)
    if not actor or not ready:
        console.print(f"[red]Cannot test {source}: {reason}.[/red]")
        raise typer.Exit(code=1)

    maximum_records = min(3, int(registry.defaults.get("test_maximum_records") or 3))
    actor_input = actor.template("test", maximum_records=maximum_records)
    if actor_input is None:
        console.print(f"[red]Cannot test {source}: small-test input template is missing.[/red]")
        raise typer.Exit(code=1)

    try:
        result = client.collect(
            source=source,
            actor_id=actor.actor_id or "",
            actor_input=actor_input,
            actor_schema=actor.expected_output_schema,
            maximum_records=maximum_records,
            timeout_seconds=int(registry.defaults.get("test_timeout_seconds") or 180),
            estimated_cost_usd=actor.cost_estimate_usd,
            max_cost_usd=_float_or_none(registry.defaults.get("max_test_cost_usd")),
            query="actor approval test",
        )
    except ApifyError as exc:
        registry.save_test(
            source=source,
            actor_id=actor.actor_id or "",
            status="failed",
            records_fetched=0,
            newest_verified_timestamp=None,
            cost_usd=None,
            schema_warnings=[],
            actor_run_id=None,
            error=str(exc),
        )
        console.print(f"[red]Actor test failed:[/red] {exc}")
        raise typer.Exit(code=1)

    warnings = list(result.warnings)
    for record in result.normalized_records:
        warnings.extend(record.extraction_warnings)
    verified = [
        record.published_at
        for record in result.normalized_records
        if record.timestamp_verified and record.published_at
    ]
    newest = max(verified, default=None)
    now = datetime.now(timezone.utc)
    freshness_hours = int(registry.defaults.get("test_freshness_hours") or 168)
    fresh = bool(
        verified
        and all(
            now - timedelta(hours=freshness_hours)
            <= published_at
            <= now + timedelta(minutes=5)
            for published_at in verified
        )
    )
    schema_valid = (
        bool(result.items)
        and len(result.normalized_records) == len(result.items)
        and not any("schema missing required field" in item for item in warnings)
    )
    timestamps_valid = (
        len(verified) == len(result.normalized_records)
        and len(verified) == len(result.items)
    )
    passed = bool(
        result.status == "SUCCEEDED"
        and not result.partial
        and schema_valid
        and timestamps_valid
        and fresh
    )
    if not fresh:
        warnings.append(
            f"newest verified record is not within the {freshness_hours}-hour test window"
        )
    if not timestamps_valid:
        warnings.append("one or more test records lack a verified absolute timestamp")
    actual_cost = _float_or_none(result.request_cost_metadata.get("actual_cost_usd"))
    registry.save_test(
        source=source,
        actor_id=actor.actor_id or "",
        status="passed" if passed else "failed",
        records_fetched=len(result.items),
        newest_verified_timestamp=newest,
        cost_usd=actual_cost,
        schema_warnings=sorted(set(warnings)),
        actor_run_id=result.actor_run_id,
        error=None if passed else "schema, timestamp, freshness, or run validation failed",
    )

    table = Table("Metric", "Value")
    table.add_row("Status", "PASSED" if passed else "FAILED")
    table.add_row("Records fetched", str(len(result.items)))
    table.add_row("Newest verified timestamp", newest.isoformat() if newest else "none")
    table.add_row("Actual test cost", f"${actual_cost:.4f}" if actual_cost is not None else "not reported")
    table.add_row("Warnings", "; ".join(sorted(set(warnings))) or "none")
    console.print(table)
    if not passed:
        raise typer.Exit(code=1)


@blockers_app.command("plan")
def blockers_plan_command(
    platform: str = typer.Option("lovable"),
    provider: str = typer.Option("apify"),
    recent_hours: int = typer.Option(24, min=1, max=168),
    config: Path = typer.Option(Path("config/apify_actors.yaml")),
) -> None:
    """Preview the bounded blocker collection without starting an Actor."""
    if platform.lower() != "lovable":
        raise typer.BadParameter("Only --platform lovable is currently supported")
    _print_plan(blockers_plan(ApifyActorRegistry(config), provider=provider, recent_hours=recent_hours))


@blockers_app.command("run")
def blockers_run_command(
    platform: str = typer.Option("lovable"),
    provider: str = typer.Option("apify"),
    recent_hours: int = typer.Option(24, min=1, max=168),
    config: Path = typer.Option(Path("config/apify_actors.yaml")),
) -> None:
    """Run a bounded, read-only blocker scan and write local reports."""
    if platform.lower() != "lovable":
        raise typer.BadParameter("Only --platform lovable is currently supported")
    result = run_lovable_blockers(
        ApifyActorRegistry(config),
        ApifyClient(),
        provider=provider,
        recent_hours=recent_hours,
    )
    _print_result(result, "Qualifying blockers", len(result.get("qualifying_blockers") or []))


@opportunities_app.command("plan")
def opportunities_plan_command(
    provider: str = typer.Option("apify"),
    target_market: str = typer.Option("malaysia"),
    mode: str = typer.Option("global-transfer"),
    config: Path = typer.Option(Path("config/apify_actors.yaml")),
) -> None:
    """Preview staged opportunity collection without starting Actors."""
    _validate_opportunity_options(target_market, mode)
    _print_plan(
        opportunities_plan(
            ApifyActorRegistry(config),
            provider=provider,
            target_market=target_market,
            mode=mode,
        )
    )


@opportunities_app.command("run")
def opportunities_run_command(
    provider: str = typer.Option("apify"),
    target_market: str = typer.Option("malaysia"),
    mode: str = typer.Option("global-transfer"),
    config: Path = typer.Option(Path("config/apify_actors.yaml")),
) -> None:
    """Run the gated three-stage opportunity workflow and write local reports."""
    _validate_opportunity_options(target_market, mode)
    result = run_global_to_malaysia(
        ApifyActorRegistry(config),
        ApifyClient(),
        provider=provider,
        target_market=target_market,
        mode=mode,
    )
    notification = notify_opportunity_candidates(result)
    if notification["status"] == "sent":
        console.print(
            f"[green]Opportunity summary email sent:[/green] "
            f"{notification['candidate_count']} candidate(s)"
        )
    elif notification["status"] == "failed":
        console.print(
            f"[yellow]Opportunity email failed:[/yellow] {notification['reason']}"
        )
    else:
        console.print(
            f"[dim]Opportunity email skipped: {notification['reason']}[/dim]"
        )
    _print_result(result, "Candidates", len(result.get("candidates") or []))


def register_apify_cli(app: typer.Typer) -> None:
    app.add_typer(apify_app, name="apify")
    app.add_typer(blockers_app, name="blockers")
    app.add_typer(opportunities_app, name="opportunities")


def _print_plan(plan: dict[str, Any]) -> None:
    table = Table("Plan field", "Value")
    for key in (
        "workflow", "provider", "actors_selected", "queries", "estimated_runs",
        "maximum_records", "estimated_cost_usd", "missing_actor_ids",
        "untested_actors", "sources_skipped", "broad_run_allowed",
        "broad_run_blocker",
    ):
        if key in plan:
            table.add_row(key, _display(plan[key]))
    console.print(table)


def _print_result(result: dict[str, Any], count_label: str, count: int) -> None:
    table = Table("Result", "Value")
    table.add_row("Research status", str(result.get("research_status") or "unknown"))
    table.add_row("Records fetched", str(result.get("records_fetched", result.get("stage_a", {}).get("records", 0))))
    table.add_row("Newest verified timestamp", str(result.get("newest_verified_timestamp") or "none"))
    table.add_row(count_label, str(count))
    table.add_row("Report paths", _display(result.get("report_paths") or {}))
    if result.get("reason"):
        table.add_row("Limitation", str(result["reason"]))
    console.print(table)


def _validate_opportunity_options(target_market: str, mode: str) -> None:
    if target_market.lower() != "malaysia":
        raise typer.BadParameter("Only --target-market malaysia is currently supported")
    if mode.lower() != "global-transfer":
        raise typer.BadParameter("Only --mode global-transfer is currently supported")


def _display(value: Any) -> str:
    if value in (None, [], {}):
        return "none"
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
