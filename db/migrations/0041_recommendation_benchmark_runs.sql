CREATE TABLE IF NOT EXISTS recommendation_benchmark_runs (
  recommendation_benchmark_run_id BIGSERIAL PRIMARY KEY,
  benchmark_key TEXT NOT NULL,
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  strategy TEXT NOT NULL,
  scenario_count INT NOT NULL DEFAULT 0,
  completed_count INT NOT NULL DEFAULT 0,
  failed_count INT NOT NULL DEFAULT 0,
  as_of_times_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  pass_types_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  modes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  budgets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  global_best_selected_count INT NOT NULL DEFAULT 0,
  core_replay_ready_count INT NOT NULL DEFAULT 0,
  core_replay_total_run_count INT NOT NULL DEFAULT 0,
  core_replay_total_settled_run_count INT NOT NULL DEFAULT 0,
  final_hit_sample_size INT NOT NULL DEFAULT 0,
  final_hit_count INT NOT NULL DEFAULT 0,
  average_core_replay_roi NUMERIC,
  warning_count INT NOT NULL DEFAULT 0,
  history_comparison_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_benchmark_runner_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT recommendation_benchmark_strategy_check
    CHECK (
      strategy IN (
        'accuracy_first',
        'value_first',
        'upset_protection',
        'budget_constrained'
      )
    )
);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_runs_key_created
  ON recommendation_benchmark_runs (benchmark_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_runs_strategy_created
  ON recommendation_benchmark_runs (strategy, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_runs_roi
  ON recommendation_benchmark_runs (average_core_replay_roi DESC NULLS LAST, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_benchmark_runs_final_hit
  ON recommendation_benchmark_runs (final_hit_count DESC, final_hit_sample_size DESC, created_at DESC);
