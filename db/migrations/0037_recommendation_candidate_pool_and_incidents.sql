CREATE TABLE IF NOT EXISTS recommendation_candidate_pool_snapshots (
  recommendation_candidate_pool_snapshot_id BIGSERIAL PRIMARY KEY,
  recommendation_run_id BIGINT REFERENCES recommendation_runs(recommendation_run_id),
  run_key TEXT NOT NULL,
  as_of_time_utc TIMESTAMPTZ NOT NULL,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  mode TEXT NOT NULL,
  candidate_count INT NOT NULL DEFAULT 0,
  selected_candidate_count INT NOT NULL DEFAULT 0,
  excluded_candidate_count INT NOT NULL DEFAULT 0,
  candidate_query_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'recommendation_engine_v3_1',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(recommendation_run_id)
);

CREATE TABLE IF NOT EXISTS recommendation_candidate_pool_items (
  recommendation_candidate_pool_item_id BIGSERIAL PRIMARY KEY,
  recommendation_candidate_pool_snapshot_id BIGINT
    REFERENCES recommendation_candidate_pool_snapshots(
      recommendation_candidate_pool_snapshot_id
    ),
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
  selected BOOLEAN NOT NULL DEFAULT false,
  locked BOOLEAN NOT NULL DEFAULT false,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_provider_incident_events (
  recommendation_provider_incident_event_id BIGSERIAL PRIMARY KEY,
  provider_incident_key TEXT NOT NULL UNIQUE,
  provider_name TEXT NOT NULL,
  provider_runtime_incident_report_id BIGINT REFERENCES provider_runtime_incident_reports(
    provider_runtime_incident_report_id
  ),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  competition_id TEXT REFERENCES competitions(competition_id),
  incident_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  event_time_utc TIMESTAMPTZ NOT NULL,
  observed_at_utc TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  affects_recommendations BOOLEAN NOT NULL DEFAULT true,
  excluded_fixture_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'recommendation_provider_incident_status_check'
  ) THEN
    ALTER TABLE recommendation_provider_incident_events
      ADD CONSTRAINT recommendation_provider_incident_status_check
      CHECK (status IN ('open', 'acknowledged', 'resolved', 'ignored'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recommendation_candidate_pool_run
  ON recommendation_candidate_pool_snapshots(recommendation_run_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidate_pool_time
  ON recommendation_candidate_pool_snapshots(as_of_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidate_pool_items_snapshot
  ON recommendation_candidate_pool_items(recommendation_candidate_pool_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_candidate_pool_items_fixture
  ON recommendation_candidate_pool_items(fixture_id, market_type, outcome);

CREATE INDEX IF NOT EXISTS idx_recommendation_provider_incidents_time
  ON recommendation_provider_incident_events(event_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_provider_incidents_status_time
  ON recommendation_provider_incident_events(status, event_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_provider_incidents_fixture
  ON recommendation_provider_incident_events(fixture_id, event_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_recommendation_provider_incidents_competition
  ON recommendation_provider_incident_events(competition_id, event_time_utc DESC);
