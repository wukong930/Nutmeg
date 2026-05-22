CREATE TABLE IF NOT EXISTS provider_authorizations (
  provider_name TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (
    status IN ('active', 'pending_review', 'research_only', 'blocked', 'expired')
  ),
  capabilities_json JSONB NOT NULL DEFAULT '[]',
  terms_checked_at_utc TIMESTAMPTZ,
  commercial_use_allowed BOOLEAN NOT NULL DEFAULT false,
  retention_allowed BOOLEAN NOT NULL DEFAULT false,
  api_key_env_var TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_sync_runs (
  provider_sync_run_id BIGSERIAL PRIMARY KEY,
  provider_name TEXT REFERENCES provider_authorizations(provider_name),
  capability TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  entity_count INT NOT NULL DEFAULT 0,
  error_message TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_provider_sync_runs_provider_started
  ON provider_sync_runs(provider_name, started_at DESC);

CREATE TABLE IF NOT EXISTS competition_onboarding_assessments (
  assessment_id BIGSERIAL PRIMARY KEY,
  competition_id TEXT REFERENCES competitions(competition_id),
  competition_name TEXT NOT NULL,
  target_stage TEXT NOT NULL CHECK (target_stage IN ('beta', 'production')),
  decision TEXT NOT NULL CHECK (
    decision IN ('beta_ready', 'production_ready', 'not_ready')
  ),
  schedule_coverage NUMERIC NOT NULL,
  result_coverage NUMERIC NOT NULL,
  odds_coverage NUMERIC NOT NULL,
  handicap_coverage NUMERIC NOT NULL,
  lineup_injury_coverage NUMERIC NOT NULL,
  historical_stats_completeness NUMERIC NOT NULL,
  provider_consistency NUMERIC NOT NULL,
  data_freshness NUMERIC NOT NULL,
  historical_sample_size INT NOT NULL DEFAULT 0,
  complete_seasons INT NOT NULL DEFAULT 0,
  data_quality_score NUMERIC NOT NULL,
  data_quality_grade TEXT NOT NULL,
  market_resolver_tests_passed BOOLEAN NOT NULL DEFAULT false,
  score_grid_generation_passed BOOLEAN NOT NULL DEFAULT false,
  log_loss_delta_vs_baseline NUMERIC,
  brier_delta_vs_baseline NUMERIC,
  calibration_shift NUMERIC,
  reasons_json JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_competition_onboarding_competition_created
  ON competition_onboarding_assessments(competition_id, created_at DESC);

CREATE TABLE IF NOT EXISTS model_promotion_reviews (
  model_promotion_review_id BIGSERIAL PRIMARY KEY,
  candidate_model_version TEXT REFERENCES model_versions(model_version),
  baseline_model_version TEXT REFERENCES model_versions(model_version),
  decision TEXT NOT NULL CHECK (decision IN ('shadow_candidate', 'keep_experiment')),
  next_status TEXT NOT NULL CHECK (next_status IN ('shadow', 'experiment')),
  sample_size INT NOT NULL DEFAULT 0,
  metrics_json JSONB NOT NULL DEFAULT '{}',
  reasons_json JSONB NOT NULL DEFAULT '[]',
  rollback_plan_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_promotion_reviews_candidate_created
  ON model_promotion_reviews(candidate_model_version, created_at DESC);
