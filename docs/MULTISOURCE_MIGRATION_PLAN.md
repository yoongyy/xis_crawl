# Multi-source demand engine migration plan

## Baseline

- Preserve the existing `posts`, `comments`, `findings`, `crawl_runs`,
  `search_queries`, and `crawl_errors` tables and all MongoDB collections.
- Preserve the XHS CLI, normalization functions, Malaysia classifiers, reports,
  and existing commands.
- Treat XHS as an optional `early_trend_scout`; its evidence cannot validate
  United States demand.

## Additive schema migration

1. Create a `schema_migrations` ledger.
2. Add new tables alongside the legacy schema:
   `source_records`, `evidence_findings`, `research_packs`, `research_runs`,
   `source_queries`, `competitors`, `product_reviews`, `trend_series`,
   `opportunity_candidates`, `crawl_errors_v2`, and `source_rate_limits`.
3. Add uniqueness constraints on stable source IDs and finding IDs so imports
   and resumed runs are idempotent.
4. Add run-membership tables for globally deduplicated source records,
   findings, product reviews, and trend points. This prevents a later run from
   moving or hiding evidence that belongs to an earlier report.
5. Add indexes for pack/run, source, published date, thread, author, and
   evidence type lookups.
6. Store source payload files under
   `data/raw/<source>/<YYYY-MM-DD>/`; store only their path in normalized rows.
7. Do not copy legacy XHS rows automatically. New XHS activity is normalized
   through the adapter. A future, explicit backfill can map legacy records
   without changing or deleting the originals.

## Rollout and rollback

- Apply migrations in a transaction and record the migration version only
  after success.
- Verify legacy row counts before and after migration.
- Rollback is normally unnecessary because the migration is additive. If
  required, restore a database copy or drop only the new tables after exporting
  them; never reset the database.
- MongoDB remains supported by the legacy workflow. The first multi-source
  implementation uses the same local SQLite database to provide transactional
  run state and safe resume behavior.

## Compatibility

- Existing top-level CLI commands remain unchanged.
- New grouped commands use `sources`, `research`, and `import`.
- Rules classification remains the default and needs no paid API.
- Optional credentials and unreliable providers degrade to skipped or
  manual-import-only states rather than failing a research run.
