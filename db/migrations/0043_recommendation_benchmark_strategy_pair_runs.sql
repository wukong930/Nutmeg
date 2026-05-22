CREATE TABLE IF NOT EXISTS recommendation_benchmark_strategy_pair_runs (
  recommendation_benchmark_strategy_pair_run_id BIGSERIAL PRIMARY KEY,
  pair_key TEXT NOT NULL,
  status TEXT NOT NULL,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  baseline_strategy TEXT NOT NULL,
  candidate_strategy TEXT NOT NULL,
  baseline_benchmark_key TEXT NOT NULL,
  candidate_benchmark_key TEXT NOT NULL,
  baseline_benchmark_run_id BIGINT,
  candidate_benchmark_run_id BIGINT,
  comparison_key TEXT NOT NULL,
  comparison_status TEXT NOT NULL,
  comparison_passed BOOLEAN NOT NULL DEFAULT FALSE,
  average_core_replay_roi_delta NUMERIC,
  final_hit_rate_delta NUMERIC,
  core_replay_ready_ratio_delta NUMERIC,
  matrix_match BOOLEAN NOT NULL DEFAULT FALSE,
  failed_checks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_benchmark_strategy_pair_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recommendation_benchmark_strategy_pair_status_check
    CHECK (status IN ('passed', 'failed')),
  CONSTRAINT recommendation_benchmark_strategy_pair_baseline_strategy_check
    CHECK (
      baseline_strategy IN (
        'accuracy_first',
        'value_first',
        'upset_protection',
        'budget_constrained'
      )
    ),
  CONSTRAINT recommendation_benchmark_strategy_pair_candidate_strategy_check
    CHECK (
      candidate_strategy IN (
        'accuracy_first',
        'value_first',
        'upset_protection',
        'budget_constrained'
      )
    )
);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_strategy_pair_key_created
  ON recommendation_benchmark_strategy_pair_runs (pair_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_strategy_pair_strategies_created
  ON recommendation_benchmark_strategy_pair_runs (
    baseline_strategy,
    candidate_strategy,
    created_at DESC
  );

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_strategy_pair_status_created
  ON recommendation_benchmark_strategy_pair_runs (comparison_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_strategy_pair_roi_delta
  ON recommendation_benchmark_strategy_pair_runs (
    average_core_replay_roi_delta DESC NULLS LAST,
    created_at DESC
  );
