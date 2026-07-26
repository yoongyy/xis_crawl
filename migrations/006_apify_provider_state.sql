CREATE TABLE IF NOT EXISTS apify_actor_tests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  tested_at TEXT NOT NULL,
  status TEXT NOT NULL,
  records_fetched INTEGER NOT NULL DEFAULT 0,
  newest_verified_timestamp TEXT,
  cost_usd REAL,
  schema_warnings_json TEXT NOT NULL DEFAULT '[]',
  actor_run_id TEXT,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_apify_actor_tests_source
  ON apify_actor_tests(source, actor_id, tested_at);

CREATE TABLE IF NOT EXISTS apify_collection_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow TEXT NOT NULL,
  source TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  actor_run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  partial INTEGER NOT NULL DEFAULT 0,
  records_fetched INTEGER NOT NULL DEFAULT 0,
  records_accepted INTEGER NOT NULL DEFAULT 0,
  estimated_cost_usd REAL,
  actual_cost_usd REAL,
  raw_json_path TEXT,
  started_at TEXT,
  finished_at TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  UNIQUE(workflow, actor_run_id)
);

CREATE TABLE IF NOT EXISTS apify_processed_records (
  workflow TEXT NOT NULL,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  actor_run_id TEXT NOT NULL,
  published_at TEXT,
  processed_at TEXT NOT NULL,
  PRIMARY KEY(workflow, source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_apify_processed_workflow
  ON apify_processed_records(workflow, source, processed_at);
