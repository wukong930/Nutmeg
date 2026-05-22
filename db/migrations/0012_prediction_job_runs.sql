CREATE TABLE IF NOT EXISTS prediction_job_runs (
  prediction_job_run_id BIGSERIAL PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  requested_by TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  fixture_count INT NOT NULL DEFAULT 0,
  generated_count INT NOT NULL DEFAULT 0,
  feature_snapshot_ids_json JSONB NOT NULL DEFAULT '{}',
  prediction_snapshot_ids_json JSONB NOT NULL DEFAULT '{}',
  score_grid_ids_json JSONB NOT NULL DEFAULT '{}',
  data_quality_scores_json JSONB NOT NULL DEFAULT '{}',
  skipped_fixture_ids_json JSONB NOT NULL DEFAULT '[]',
  warnings_json JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prediction_job_runs_status_started
  ON prediction_job_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_job_runs_type_started
  ON prediction_job_runs(job_type, started_at DESC);
