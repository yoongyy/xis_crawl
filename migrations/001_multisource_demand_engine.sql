CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  title TEXT,
  body TEXT,
  author_public_name TEXT,
  author_hash TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  country_signal TEXT,
  language TEXT,
  score_or_votes REAL,
  comment_count INTEGER,
  rating REAL,
  app_name TEXT,
  product_name TEXT,
  query TEXT,
  search_rank INTEGER,
  raw_json_path TEXT,
  extraction_confidence REAL,
  extraction_warnings_json TEXT,
  thread_id TEXT,
  parent_id TEXT,
  market_role TEXT,
  not_us_validation INTEGER NOT NULL DEFAULT 0,
  normalized_text_hash TEXT,
  copied_from_record_id INTEGER,
  research_run_id INTEGER,
  UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS evidence_findings (
  finding_id TEXT PRIMARY KEY,
  research_run_id INTEGER,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_record_type TEXT NOT NULL,
  published_at TEXT,
  country TEXT,
  market TEXT NOT NULL,
  author_hash TEXT,
  thread_id TEXT,
  evidence_text TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  problem_category TEXT,
  problem_description TEXT,
  affected_person TEXT,
  situation_or_trigger TEXT,
  current_solution TEXT,
  workaround TEXT,
  competitor_or_product TEXT,
  missing_feature TEXT,
  desired_outcome TEXT,
  purchase_statement TEXT,
  current_spending_statement TEXT,
  price_amount REAL,
  currency TEXT,
  billing_period TEXT,
  willingness_to_pay_statement TEXT,
  cancellation_statement TEXT,
  refund_statement TEXT,
  uninstall_statement TEXT,
  switching_statement TEXT,
  switching_from TEXT,
  switching_to TEXT,
  urgency TEXT,
  emotional_intensity REAL,
  frequency_claim TEXT,
  commercial_consequence TEXT,
  personal_experience INTEGER,
  organic_evidence_weight REAL,
  promotional_probability REAL,
  relevance_score REAL,
  confidence REAL,
  verification_status TEXT,
  verification_notes TEXT,
  prompt_version TEXT
);

CREATE TABLE IF NOT EXISTS research_packs (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  path TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pack_slug TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  options_json TEXT NOT NULL,
  resume_cursor_json TEXT,
  records_discovered INTEGER NOT NULL DEFAULT 0,
  records_valid INTEGER NOT NULL DEFAULT 0,
  duplicate_records INTEGER NOT NULL DEFAULT 0,
  stopped_reason TEXT
);

CREATE TABLE IF NOT EXISTS source_queries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  source TEXT NOT NULL,
  query TEXT NOT NULL,
  purpose TEXT NOT NULL,
  priority INTEGER NOT NULL,
  expected_value REAL NOT NULL,
  maximum_results INTEGER NOT NULL,
  freshness_window_days INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned',
  records_returned INTEGER NOT NULL DEFAULT 0,
  api_calls_estimated REAL NOT NULL DEFAULT 0,
  error_message TEXT,
  UNIQUE(research_run_id, source, query, purpose)
);

CREATE TABLE IF NOT EXISTS competitors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  name TEXT NOT NULL,
  platform TEXT NOT NULL,
  official_url TEXT NOT NULL,
  category TEXT,
  current_price REAL,
  price_currency TEXT,
  price_type TEXT,
  price_checked_at TEXT,
  price_source_url TEXT,
  free_tier INTEGER,
  rating REAL,
  review_count INTEGER,
  last_updated TEXT,
  key_features_json TEXT,
  commonly_praised_json TEXT,
  common_complaints_json TEXT,
  missing_features_json TEXT,
  cancellation_reasons_json TEXT,
  evidence_links_json TEXT,
  source_confidence REAL,
  UNIQUE(research_run_id, platform, name)
);

CREATE TABLE IF NOT EXISTS product_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  app_id TEXT,
  app_name TEXT,
  review_title TEXT,
  review_body TEXT NOT NULL,
  rating REAL,
  version TEXT,
  review_date TEXT,
  language TEXT,
  source_url TEXT NOT NULL,
  UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS trend_series (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  provider TEXT NOT NULL,
  query TEXT NOT NULL,
  geography TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  value REAL,
  series_type TEXT NOT NULL DEFAULT 'interest',
  source_url TEXT,
  UNIQUE(provider, query, geography, observed_at, series_type)
);

CREATE TABLE IF NOT EXISTS opportunity_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  problem_key TEXT NOT NULL,
  classification TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  problem_evidence_score REAL NOT NULL,
  solution_demand_score REAL NOT NULL,
  payment_evidence_score REAL NOT NULL,
  market_gap_score REAL NOT NULL,
  crowding_score REAL NOT NULL,
  risk_score REAL NOT NULL,
  independent_authors INTEGER NOT NULL,
  independent_threads INTEGER NOT NULL,
  independent_platforms INTEGER NOT NULL,
  rationale_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(research_run_id, problem_key)
);

CREATE TABLE IF NOT EXISTS crawl_errors_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  research_run_id INTEGER,
  source TEXT NOT NULL,
  query TEXT,
  stage TEXT NOT NULL,
  error_type TEXT NOT NULL,
  message TEXT NOT NULL,
  retryable INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_rate_limits (
  source TEXT PRIMARY KEY,
  remaining INTEGER,
  reset_at TEXT,
  state TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_records_run ON source_records(research_run_id);
CREATE INDEX IF NOT EXISTS idx_source_records_source_date ON source_records(source, published_at);
CREATE INDEX IF NOT EXISTS idx_source_records_thread ON source_records(source, thread_id);
CREATE INDEX IF NOT EXISTS idx_source_records_author ON source_records(author_hash);
CREATE INDEX IF NOT EXISTS idx_evidence_run_type ON evidence_findings(research_run_id, evidence_type);
CREATE INDEX IF NOT EXISTS idx_evidence_thread_author ON evidence_findings(thread_id, author_hash);
CREATE INDEX IF NOT EXISTS idx_queries_run_status ON source_queries(research_run_id, status);
