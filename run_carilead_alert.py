#!/usr/bin/env python3
"""
CariLead Alert Bot Entry Point
Scrapes & filters Xiaohongshu (XHS) for high-intent buyer leads in targeted niches (e.g. Malaysia Insurance, Dev Outsourcing).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.carilead_alert import CariLeadScanner, TargetNiche
from src.carilead_alert.telegram_notifier import TelegramNotifier

app = typer.Typer(
    help="⚡ CariLead Alert: Real-Time Commercial Buying Intent Scanner & Telegram Notifier"
)
console = Console()


@app.command()
def main(
    niche: str = typer.Option(
        "insurance",
        "--niche",
        "-n",
        help="Target commercial niche: 'insurance', 'freelance_dev', or 'design_marketing'.",
    ),
    limit: int = typer.Option(
        30,
        "--limit",
        "-l",
        help="Maximum posts to scan per search query.",
    ),
    output_dir: str = typer.Option(
        "output/carilead_alerts",
        "--output",
        "-o",
        help="Output directory path for captured leads.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run in dry-run/simulated fallback mode.",
    ),
    bot_token: Optional[str] = typer.Option(
        None,
        "--telegram-token",
        help="Optional Telegram Bot API Token for live message dispatch.",
    ),
    chat_id: Optional[str] = typer.Option(
        None,
        "--telegram-chat-id",
        help="Optional Telegram Chat/Channel ID for live message dispatch.",
    ),
):
    """
    Run CariLead Commercial Intent Alert Scanner to extract real-time sales leads.
    """
    # Parse niche enum
    try:
        target_niche = TargetNiche(niche.lower())
    except ValueError:
        console.print(f"[red]❌ Invalid niche '{niche}'. Options: insurance, freelance_dev, design_marketing[/red]")
        raise typer.Exit(code=1)

    scanner = CariLeadScanner(output_dir=output_dir)
    leads = scanner.scan(niche=target_niche, limit_per_query=limit, dry_run=dry_run)

    # If leads were found, render a formatted Telegram notification preview
    if leads:
        notifier = TelegramNotifier(bot_token=bot_token, chat_id=chat_id)
        console.print("\n[bold yellow]📱 TELEGRAM ALERT MESSAGE PREVIEW (COPY & USE FOR TRIAL SALES):[/bold yellow]")
        console.print("=" * 65)
        
        preview_lead = leads[0]
        preview_text = notifier.format_lead_message(preview_lead)
        console.print(preview_text)
        console.print("=" * 65)

        if bot_token and chat_id:
            console.print(f"🚀 Dispatching top alert to Telegram Chat ID [cyan]{chat_id}[/cyan]...")
            success = notifier.send_lead_alert(preview_lead)
            if success:
                console.print("[bold green]✅ Telegram Alert Sent Successfully![/bold green]")
            else:
                console.print("[red]❌ Failed to dispatch Telegram notification.[/red]")


if __name__ == "__main__":
    app()
