CREATE INDEX IF NOT EXISTS idx_recommendation_runs_successor_source
  ON recommendation_runs (
    (explanation_json #>> '{internal_trace,successor_recompute,source_recommendation_run_id}')
  )
  WHERE status <> 'invalidated'
    AND explanation_json #>> '{internal_trace,successor_recompute,source_recommendation_run_id}'
      IS NOT NULL;
