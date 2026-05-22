CREATE TABLE IF NOT EXISTS recommendation_benchmark_cycle_runs (
  recommendation_benchmark_cycle_run_id BIGSERIAL PRIMARY KEY,
  cycle_key TEXT NOT NULL,
  status TEXT NOT NULL,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  schedule_key TEXT NOT NULL,
  benchmark_key TEXT NOT NULL,
  benchmark_run_id BIGINT,
  gate_key TEXT,
  gate_status TEXT,
  gate_passed BOOLEAN,
  historical_suite_quality_gate_key TEXT,
  historical_suite_quality_gate_passed BOOLEAN,
  historical_suite_lifecycle_source_status_synced BOOLEAN,
  historical_suite_lifecycle_effective_leaf_count INT NOT NULL DEFAULT 0,
  historical_suite_lifecycle_active_edge_count INT NOT NULL DEFAULT 0,
  historical_suite_lifecycle_critical_issue_count INT NOT NULL DEFAULT 0,
  historical_suite_lifecycle_source_status_sync_required_count INT NOT NULL DEFAULT 0,
  failed_checks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_benchmark_cycle_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recommendation_benchmark_cycle_status_check
    CHECK (status IN ('passed', 'failed', 'gate_skipped')),
  CONSTRAINT recommendation_benchmark_cycle_gate_status_check
    CHECK (
      gate_status IS NULL
      OR gate_status IN ('passed', 'failed', 'insufficient_history')
    )
);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_cycle_runs_key_created
  ON recommendation_benchmark_cycle_runs (cycle_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_cycle_runs_benchmark_created
  ON recommendation_benchmark_cycle_runs (benchmark_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_cycle_runs_status_created
  ON recommendation_benchmark_cycle_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_cycle_runs_historical_suite
  ON recommendation_benchmark_cycle_runs (
    historical_suite_quality_gate_key,
    created_at DESC
  );
