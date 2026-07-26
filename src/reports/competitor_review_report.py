from __future__ import annotations

from pathlib import Path
import pandas as pd


def write_competitor_review_report(competitors: pd.DataFrame, path: Path) -> Path:
    lines = ["# Competitor review report", ""]
    if competitors.empty:
        lines.append("No source-linked competitor evidence is available.")
    else:
        for row in competitors.to_dict(orient="records"):
            lines.append(f"- [{row['name']}]({row['official_url']})")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
