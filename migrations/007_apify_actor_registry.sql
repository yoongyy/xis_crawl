CREATE TABLE IF NOT EXISTS apify_actor_registry (
  source TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  actor_name TEXT NOT NULL,
  developer TEXT NOT NULL,
  last_successful_test TEXT,
  expected_input_schema_json TEXT NOT NULL,
  expected_output_schema_json TEXT NOT NULL,
  timestamp_field TEXT,
  cost_estimate_usd REAL,
  known_limitations_json TEXT NOT NULL DEFAULT '[]',
  approval_status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(source, actor_id)
);
