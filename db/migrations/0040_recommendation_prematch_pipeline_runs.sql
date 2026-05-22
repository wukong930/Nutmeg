CREATE TABLE IF NOT EXISTS recommendation_prematch_pipeline_runs (
  recommendation_prematch_pipeline_run_id BIGSERIAL PRIMARY KEY,
  run_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  as_of_time_utc TIMESTAMPTZ NOT NULL,
  window_start_utc TIMESTAMPTZ NOT NULL,
  window_end_utc TIMESTAMPTZ NOT NULL,
  pass_type TEXT,
  mode TEXT,
  strategy TEXT,
  requested_by TEXT,
  mapped_incident_count INT NOT NULL DEFAULT 0,
  stored_incident_count INT NOT NULL DEFAULT 0,
  checked_run_count INT NOT NULL DEFAULT 0,
  triggered_run_count INT NOT NULL DEFAULT 0,
  skipped_run_count INT NOT NULL DEFAULT 0,
  generated_recommendation_run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  prematch_report_key TEXT,
  warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  error_message TEXT,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_prematch_pipeline_v3_1',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recommendation_prematch_pipeline_status_check
    CHECK (status IN ('running', 'completed', 'failed')),
  CONSTRAINT recommendation_prematch_pipeline_mode_check
    CHECK (mode IS NULL OR mode IN ('single', 'multiple')),
  CONSTRAINT recommendation_prematch_pipeline_strategy_check
    CHECK (
      strategy IS NULL OR strategy IN (
        'accuracy_first',
        'value_first',
        'upset_protection',
        'budget_constrained'
      )
    )
);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_pipeline_runs_window
  ON recommendation_prematch_pipeline_runs (window_start_utc, window_end_utc);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_pipeline_runs_status_started
  ON recommendation_prematch_pipeline_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_prematch_pipeline_runs_triggered
  ON recommendation_prematch_pipeline_runs (triggered_run_count DESC, started_at DESC);
