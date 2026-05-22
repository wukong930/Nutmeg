CREATE TABLE IF NOT EXISTS recommendation_strategy_reviews (
  recommendation_strategy_review_id BIGSERIAL PRIMARY KEY,
  review_key TEXT NOT NULL UNIQUE,
  candidate_strategy TEXT NOT NULL,
  baseline_strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  decision TEXT NOT NULL,
  next_status TEXT NOT NULL,
  sample_size INT NOT NULL DEFAULT 0,
  baseline_sample_size INT NOT NULL DEFAULT 0,
  candidate_roi NUMERIC,
  baseline_roi NUMERIC,
  candidate_hit_rate NUMERIC,
  baseline_hit_rate NUMERIC,
  candidate_calibration_error NUMERIC,
  baseline_calibration_error NUMERIC,
  metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  rollback_plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  window_start_utc TIMESTAMPTZ,
  window_end_utc TIMESTAMPTZ,
  source TEXT NOT NULL DEFAULT 'recommendation_strategy_governance_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_strategy_reviews_created
  ON recommendation_strategy_reviews(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_strategy_reviews_candidate_scope
  ON recommendation_strategy_reviews(candidate_strategy, pass_type, mode, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_strategy_reviews_decision
  ON recommendation_strategy_reviews(decision, next_status, created_at DESC);
