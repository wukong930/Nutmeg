CREATE INDEX IF NOT EXISTS idx_recommendation_runs_status_created
  ON recommendation_runs(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_locked_legs_run_status
  ON recommendation_locked_legs(recommendation_run_id, status, locked_at_utc DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendation_locked_legs_unique_active
  ON recommendation_locked_legs(recommendation_run_id, fixture_id, market_type, outcome)
  WHERE status = 'locked';

CREATE INDEX IF NOT EXISTS idx_recommendation_lifecycle_events_key_time
  ON recommendation_lifecycle_events(recommendation_key, event_time_utc DESC);
