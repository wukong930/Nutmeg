-- Provider Ops helper and cron run history.
-- Stores non-secret operational summaries for VPS scripts and scheduled jobs.

CREATE TABLE IF NOT EXISTS provider_ops_run_history (
  provider_ops_run_id BIGSERIAL PRIMARY KEY,
  run_name TEXT NOT NULL,
  run_type TEXT NOT NULL DEFAULT 'vps_helper',
  source TEXT NOT NULL DEFAULT 'vps',
  status TEXT NOT NULL,
  operator_name TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  duration_ms INTEGER,
  exit_code INTEGER,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_excerpt TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT provider_ops_run_history_status_check
    CHECK (status IN ('success', 'failure', 'skipped')),
  CONSTRAINT provider_ops_run_history_duration_check
    CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX IF NOT EXISTS idx_provider_ops_run_history_created
  ON provider_ops_run_history (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_ops_run_history_name_created
  ON provider_ops_run_history (run_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_ops_run_history_status_created
  ON provider_ops_run_history (status, created_at DESC);
