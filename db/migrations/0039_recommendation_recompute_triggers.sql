CREATE TABLE IF NOT EXISTS recommendation_recompute_trigger_runs (
  recommendation_recompute_trigger_run_id BIGSERIAL PRIMARY KEY,
  trigger_key TEXT NOT NULL UNIQUE,
  as_of_time_utc TIMESTAMPTZ NOT NULL,
  window_start_utc TIMESTAMPTZ NOT NULL,
  window_end_utc TIMESTAMPTZ NOT NULL,
  checked_run_count INT NOT NULL DEFAULT 0,
  triggered_run_count INT NOT NULL DEFAULT 0,
  skipped_run_count INT NOT NULL DEFAULT 0,
  incident_event_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_recommendation_run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  generated_recommendation_run_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_recompute_trigger_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_recompute_triggers_time
  ON recommendation_recompute_trigger_runs(as_of_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_recompute_triggers_counts
  ON recommendation_recompute_trigger_runs(triggered_run_count DESC, as_of_time_utc DESC);
