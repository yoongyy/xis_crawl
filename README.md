# Multi-source consumer demand research

Local macOS research prototype for collecting Xiaohongshu/XHS posts and comments, filtering for Malaysian property-agent relevance, classifying pain points, and exporting structured data for later AI analysis. MongoDB Atlas is the primary storage backend when `MONGO_URI` is configured; SQLite remains available as a local fallback and migration source.

The project also includes an additive, United States-focused multi-source demand
engine. It uses official/public adapters where practical, conservative request
budgets, manual imports where automation is unreliable, atomic evidence
extraction, independence caps, and evidence-linked reports. Existing XHS
commands and data remain intact. XHS is an early-trend source and never proves
US demand.

This is not a SaaS. It has no frontend, user accounts, billing, proxies, CAPTCHA bypass, posting, DMs, likes, follows, or account automation. It uses your own logged-in XHS account through the open-source `xiaohongshu-cli`.

## macOS Setup

1. Install Homebrew if needed: <https://brew.sh>
2. Install Python 3.11+:
   ```bash
   brew install python@3.11
   ```
3. Install `uv`:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
4. Install the XHS CLI:
   ```bash
   uv tool install xiaohongshu-cli
   ```
5. Log in with your normal browser/XHS account:
   ```bash
   xhs login
   xhs status
   ```
6. Enter this project folder:
   ```bash
   cd /Users/yewyokeyoong/Sites/localhost/xhs_crawl
   ```
7. Create and activate a virtual environment:
   ```bash
   uv venv --python 3.11
   source .venv/bin/activate
   ```
8. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```
9. Create `.env` and configure MongoDB Atlas:
   ```bash
   cp .env.example .env
   ```
   Set `MONGO_URI` in `.env`, including the database name in the URI path. `MONGO_DB` can optionally override it.
10. Check authentication:
   ```bash
   python main.py status
   ```

## Smallest Safe Test

Run a dry test first. This does not crawl XHS:

```bash
python main.py search \
  --config config/property_malaysia.yaml \
  --query-group location \
  --days 90 \
  --max-posts 5 \
  --fetch-comments \
  --max-comments-per-post 20 \
  --dry-run
```

Then run a bounded live test:

```bash
python main.py search \
  --config config/property_malaysia.yaml \
  --query-group location \
  --days 90 \
  --max-posts 5 \
  --fetch-comments \
  --max-comments-per-post 20
```

## Full Research Crawl

```bash
python main.py search \
  --config config/property_malaysia.yaml \
  --days 90 \
  --max-posts 100 \
  --fetch-comments \
  --max-comments-per-post 300
```

Useful options:

```bash
python main.py search --help
```

## Malaysia Insurance Research

The insurance module uses a separate 128-query matrix, staged discovery, value-based detail selection, bounded comment fetching, incremental TTL state, and conservative request budgets. It defaults to one active request at a time and never sends messages.

Preview a daily schedule without crawling:

```bash
python main.py plan-crawl \
  --industry insurance \
  --country malaysia \
  --frequency daily \
  --yes
```

Run the controlled six-query test:

```bash
python main.py research \
  --industry insurance \
  --country malaysia \
  --controlled-test \
  --recent-days 180 \
  --posts-per-query 10 \
  --fetch-comments \
  --max-comments-per-post 30 \
  --max-runtime-minutes 45 \
  --max-detail-posts 30 \
  --max-comment-requests 30
```

Generate both insurance reports without recrawling:

```bash
python main.py insurance-report
```

Insurance outputs include customer-voice and sales-opportunity Markdown/JSON/CSV packages plus anonymized free-summary and source-linked paid-detail JSON interfaces. Public phone numbers are redacted from stored insurance evidence and exports; hidden contact or private profile data is never collected.

Important defaults:

- Request delay: random 2 to 5 seconds
- Default max posts: 50
- Default max comments per post: 100
- Repeated CAPTCHA/risk-control/rate-limit responses stop the crawl
- Failed URLs and keywords are stored in the active database for later retry

## Migrate Existing SQLite Data

The migration uses idempotent upserts, so rerunning it does not duplicate posts, comments, or findings:

```bash
python main.py migrate-to-mongo
```

Use `--replace-existing` only when the cloud collections should be cleared before import.

## Analyze Existing Data

This does not crawl XHS again:

```bash
python main.py analyze \
  --industry property \
  --days 90 \
  --classification-mode rules
```

## Generate Report

```bash
python main.py report \
  --industry property \
  --days 90
```

Outputs:

- `data/reports/property_90_days.md`
- `data/reports/property_90_days.csv`
- `data/reports/property_90_days.json`

Normalized exports:

- `data/normalized/posts.csv`
- `data/normalized/comments.csv`
- `data/normalized/findings.csv`

Raw XHS JSON responses are saved under `data/raw/YYYY-MM-DD/` and are never intentionally overwritten by normalized exports.

## Authentication and Safety Notes

Install and authenticate the CLI separately:

```bash
uv tool install xiaohongshu-cli
xhs login
xhs status
```

The wrapper expects commands shaped like:

```bash
xhs search "<keyword>" --sort latest --json
xhs read "<post-url-or-id>" --json
xhs comments "<post-url>" --all --json
```

The CLI may return direct JSON data or an envelope such as:

```json
{
  "ok": true,
  "schema_version": "1",
  "data": []
}
```

This project handles both forms. If your installed `xiaohongshu-cli` returns a different schema, inspect files under `data/raw/YYYY-MM-DD/` and adjust `src/xhs_client.py`.

## Optional Codex CLI Mode

Rules mode works without any API key and is the default. `--classification-mode llm` uses the local `codex exec` CLI with a JSON schema when `codex` is available on PATH, then falls back to deterministic rules if Codex fails or is unavailable.

```bash
python main.py analyze \
  --industry property \
  --days 90 \
  --classification-mode llm
```

## Tests

```bash
pytest
```

## United States Demand Research

Check adapters and credential/manual-import status:

```bash
python main.py sources status
```

Preview a crawl without making source requests:

```bash
python main.py research plan \
  --pack config/research_packs/adhd_morning_departure_us.yaml \
  --sources reddit,app_store,google_play,youtube,google_trends
```

Run a bounded research pack:

```bash
python main.py research run \
  --pack config/research_packs/adhd_morning_departure_us.yaml \
  --sources reddit,app_store,google_play,youtube,google_trends \
  --recent-days 365 --incremental \
  --max-records 20 --max-comments 200 \
  --max-reddit-comments 200 --max-youtube-comments 100 \
  --max-reviews 100 \
  --max-competitors 5 --max-runtime-minutes 60
```

Re-analyze or report without crawling:

```bash
python main.py research analyze \
  --pack config/research_packs/adhd_morning_departure_us.yaml \
  --classification-mode rules
python main.py research report \
  --pack config/research_packs/adhd_morning_departure_us.yaml
```

Manual CSV/JSON fallback:

```bash
python main.py import reviews --source google_play --file data/imports/alarm_app_reviews.csv
```

The database migration is additive and idempotent. See
`docs/MULTISOURCE_MIGRATION_PLAN.md`. Raw payloads are versioned under
`data/raw/<source>/<YYYY-MM-DD>/`. Rules mode is the default and requires no
paid AI API.

The App Store adapter records the public download price separately from
in-app or subscription pricing. A `free_download` value does not prove that a
product has no paid upgrades. Review and comment records are filtered by the
requested freshness window; older public reviews are not counted in a recent
research run.
