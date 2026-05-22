CREATE TABLE IF NOT EXISTS accuracy_job_runs (
  accuracy_job_run_id BIGSERIAL PRIMARY KEY,
  job_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  reset_requested BOOLEAN NOT NULL DEFAULT TRUE,
  requested_by TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  fixture_count INT NOT NULL DEFAULT 0,
  evaluation_count INT NOT NULL DEFAULT 0,
  calibration_observation_count INT NOT NULL DEFAULT 0,
  model_comparison_report_id BIGINT REFERENCES model_comparison_reports(comparison_report_id),
  prediction_snapshot_ids_json JSONB NOT NULL DEFAULT '{}',
  evaluation_ids_json JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_accuracy_job_runs_status_started
  ON accuracy_job_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_accuracy_job_runs_type_started
  ON accuracy_job_runs(job_type, started_at DESC);
