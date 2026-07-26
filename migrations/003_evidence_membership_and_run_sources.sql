CREATE TABLE IF NOT EXISTS research_run_evidence_findings (
  research_run_id INTEGER NOT NULL,
  finding_id TEXT NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY(research_run_id, finding_id)
);

INSERT OR IGNORE INTO research_run_evidence_findings(research_run_id, finding_id, added_at)
SELECT research_run_id, finding_id, COALESCE(published_at, CURRENT_TIMESTAMP)
FROM evidence_findings
WHERE research_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_run_evidence_findings_run
  ON research_run_evidence_findings(research_run_id, finding_id);

CREATE TABLE IF NOT EXISTS research_run_sources (
  research_run_id INTEGER NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  credential_required INTEGER NOT NULL DEFAULT 0,
  detail TEXT,
  checked_at TEXT NOT NULL,
  PRIMARY KEY(research_run_id, source)
);

CREATE INDEX IF NOT EXISTS idx_run_sources_run
  ON research_run_sources(research_run_id, source);

CREATE TABLE IF NOT EXISTS research_run_product_reviews (
  research_run_id INTEGER NOT NULL,
  product_review_id INTEGER NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY(research_run_id, product_review_id)
);

INSERT OR IGNORE INTO research_run_product_reviews(research_run_id, product_review_id, added_at)
SELECT research_run_id, id, COALESCE(review_date, CURRENT_TIMESTAMP)
FROM product_reviews
WHERE research_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS research_run_trend_series (
  research_run_id INTEGER NOT NULL,
  trend_series_id INTEGER NOT NULL,
  added_at TEXT NOT NULL,
  PRIMARY KEY(research_run_id, trend_series_id)
);

INSERT OR IGNORE INTO research_run_trend_series(research_run_id, trend_series_id, added_at)
SELECT research_run_id, id, observed_at
FROM trend_series
WHERE research_run_id IS NOT NULL;
