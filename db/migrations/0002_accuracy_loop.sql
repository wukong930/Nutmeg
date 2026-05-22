CREATE TABLE IF NOT EXISTS calibration_buckets (
  calibration_bucket_id BIGSERIAL PRIMARY KEY,
  model_version TEXT NOT NULL REFERENCES model_versions(model_version),
  market_type TEXT NOT NULL,
  outcome TEXT NOT NULL,
  competition_id TEXT REFERENCES competitions(competition_id),
  bucket_start NUMERIC NOT NULL,
  bucket_end NUMERIC NOT NULL,
  sample_size INT NOT NULL DEFAULT 0,
  predicted_probability_sum NUMERIC NOT NULL DEFAULT 0,
  actual_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(model_version, market_type, outcome, competition_id, bucket_start, bucket_end)
);

CREATE INDEX IF NOT EXISTS idx_calibration_buckets_lookup
  ON calibration_buckets(model_version, market_type, outcome, competition_id);

CREATE TABLE IF NOT EXISTS model_backtest_runs (
  backtest_run_id BIGSERIAL PRIMARY KEY,
  model_version TEXT REFERENCES model_versions(model_version),
  mode TEXT NOT NULL,
  as_of_time TEXT,
  train_window_json JSONB,
  validation_window_json JSONB,
  test_window_json JSONB NOT NULL,
  competitions_json JSONB DEFAULT '[]',
  metrics_json JSONB NOT NULL DEFAULT '{}',
  calibration_json JSONB DEFAULT '{}',
  report_uri TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_comparison_reports (
  comparison_report_id BIGSERIAL PRIMARY KEY,
  candidate_model_version TEXT REFERENCES model_versions(model_version),
  baseline_model_version TEXT REFERENCES model_versions(model_version),
  candidate_metrics_json JSONB NOT NULL DEFAULT '{}',
  baseline_metrics_json JSONB NOT NULL DEFAULT '{}',
  decision_stub TEXT NOT NULL,
  reasons_json JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now()
);
