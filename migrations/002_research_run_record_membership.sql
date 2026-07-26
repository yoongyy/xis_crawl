CREATE TABLE IF NOT EXISTS research_run_source_records (
  research_run_id INTEGER NOT NULL,
  source_record_id INTEGER NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY(research_run_id, source_record_id)
);

INSERT OR IGNORE INTO research_run_source_records(research_run_id, source_record_id, added_at)
SELECT research_run_id, id, fetched_at
FROM source_records
WHERE research_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_run_source_records_run
  ON research_run_source_records(research_run_id, source_record_id);
