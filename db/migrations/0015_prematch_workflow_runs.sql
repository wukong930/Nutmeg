CREATE TABLE IF NOT EXISTS prematch_workflow_runs (
  prematch_workflow_run_id BIGSERIAL PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  requested_by TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  prediction_job_run_id BIGINT REFERENCES prediction_job_runs(prediction_job_run_id),
  prediction_job_type TEXT,
  prediction_fixture_count INT NOT NULL DEFAULT 0,
  prediction_generated_count INT NOT NULL DEFAULT 0,
  parlay_generated_count INT NOT NULL DEFAULT 0,
  parlay_recommendation_ids_json JSONB NOT NULL DEFAULT '[]',
  warnings_json JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prematch_workflow_runs_status_started
  ON prematch_workflow_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_prematch_workflow_runs_prediction_job
  ON prematch_workflow_runs(prediction_job_run_id);
