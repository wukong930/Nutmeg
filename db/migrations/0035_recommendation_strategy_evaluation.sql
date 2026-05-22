CREATE TABLE IF NOT EXISTS recommendation_run_evaluations (
  recommendation_run_evaluation_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT NOT NULL REFERENCES recommendation_runs(recommendation_run_id),
  run_key TEXT NOT NULL,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  recommendation_status TEXT NOT NULL,
  evaluation_status TEXT NOT NULL,
  total_atomic_bets INT NOT NULL DEFAULT 0,
  settled_atomic_bets INT NOT NULL DEFAULT 0,
  won_atomic_bets INT NOT NULL DEFAULT 0,
  lost_atomic_bets INT NOT NULL DEFAULT 0,
  unresolved_atomic_bets INT NOT NULL DEFAULT 0,
  unit_stake NUMERIC NOT NULL,
  total_stake NUMERIC NOT NULL DEFAULT 0,
  gross_payout NUMERIC NOT NULL DEFAULT 0,
  profit_loss NUMERIC NOT NULL DEFAULT 0,
  roi NUMERIC NOT NULL DEFAULT 0,
  hit BOOLEAN,
  hit_rate NUMERIC,
  expected_hit_probability_at_recommendation NUMERIC,
  hit_calibration_error NUMERIC,
  expected_value_at_recommendation NUMERIC,
  expected_roi_at_recommendation NUMERIC,
  locked_fixture_count INT NOT NULL DEFAULT 0,
  selected_fixture_count INT NOT NULL DEFAULT 0,
  evaluation_time_utc TIMESTAMPTZ NOT NULL,
  settlement_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_accuracy_loop_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(recommendation_run_id)
);

CREATE TABLE IF NOT EXISTS recommendation_strategy_metrics (
  recommendation_strategy_metric_id BIGSERIAL PRIMARY KEY,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  window_start_date DATE NOT NULL,
  window_end_date DATE NOT NULL,
  sample_size INT NOT NULL DEFAULT 0,
  settled_run_count INT NOT NULL DEFAULT 0,
  hit_count INT NOT NULL DEFAULT 0,
  total_stake NUMERIC NOT NULL DEFAULT 0,
  gross_payout NUMERIC NOT NULL DEFAULT 0,
  profit_loss NUMERIC NOT NULL DEFAULT 0,
  roi NUMERIC NOT NULL DEFAULT 0,
  average_expected_hit_probability NUMERIC,
  average_hit_calibration_error NUMERIC,
  average_expected_roi NUMERIC,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(strategy, pass_type, mode, window_start_date, window_end_date)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_run_evaluations_strategy_time
  ON recommendation_run_evaluations(strategy, pass_type, mode, evaluation_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_run_evaluations_status_time
  ON recommendation_run_evaluations(evaluation_status, evaluation_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_run_evaluations_roi
  ON recommendation_run_evaluations(strategy, roi DESC, evaluation_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_strategy_metrics_window
  ON recommendation_strategy_metrics(window_start_date, window_end_date, strategy);
