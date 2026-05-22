CREATE TABLE IF NOT EXISTS recommendation_policy_configs (
  config_key TEXT PRIMARY KEY,
  strategy TEXT NOT NULL,
  policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_runs (
  recommendation_run_id BIGSERIAL PRIMARY KEY,
  run_key TEXT NOT NULL UNIQUE,
  as_of_time_utc TIMESTAMPTZ NOT NULL,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'current',
  unit_stake NUMERIC NOT NULL,
  max_budget NUMERIC,
  candidate_count INT NOT NULL DEFAULT 0,
  excluded_candidate_count INT NOT NULL DEFAULT 0,
  selected_fixture_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  locked_fixture_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  total_score NUMERIC,
  parlay_evaluation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_engine_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_candidates (
  recommendation_candidate_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  line NUMERIC,
  side TEXT,
  outcome TEXT NOT NULL,
  probability NUMERIC NOT NULL,
  decimal_odds NUMERIC,
  market_probability NUMERIC,
  model_edge NUMERIC,
  data_quality_score NUMERIC NOT NULL,
  model_confidence_score NUMERIC NOT NULL DEFAULT 0.5,
  calibration_score NUMERIC NOT NULL DEFAULT 0.5,
  upset_protection_score NUMERIC NOT NULL DEFAULT 0,
  odds_stability_score NUMERIC NOT NULL DEFAULT 0.5,
  volatility_penalty NUMERIC NOT NULL DEFAULT 0,
  model_version TEXT REFERENCES model_versions(model_version),
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  prediction_time_utc TIMESTAMPTZ,
  kickoff_time_utc TIMESTAMPTZ,
  recommendation_score NUMERIC,
  selected BOOLEAN NOT NULL DEFAULT false,
  locked BOOLEAN NOT NULL DEFAULT false,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_versions (
  recommendation_version_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  revision_id TEXT NOT NULL,
  status TEXT NOT NULL,
  supersedes_revision_id TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(recommendation_run_id, revision_id)
);

CREATE TABLE IF NOT EXISTS recommendation_lifecycle_events (
  recommendation_lifecycle_event_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  recommendation_key TEXT NOT NULL,
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  event_time_utc TIMESTAMPTZ NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_locked_legs (
  recommendation_locked_leg_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  outcome TEXT NOT NULL,
  locked_at_utc TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'locked',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_budget_adjustments (
  recommendation_budget_adjustment_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  original_total_stake NUMERIC NOT NULL,
  optimized_total_stake NUMERIC NOT NULL,
  max_budget NUMERIC,
  removed_options_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  warning_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_created
  ON recommendation_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_runs_strategy_time
  ON recommendation_runs(strategy, as_of_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidates_run_selected
  ON recommendation_candidates(recommendation_run_id, selected);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidates_fixture_market
  ON recommendation_candidates(fixture_id, market_type, outcome);

CREATE INDEX IF NOT EXISTS idx_recommendation_lifecycle_events_run_time
  ON recommendation_lifecycle_events(recommendation_run_id, event_time_utc DESC);
