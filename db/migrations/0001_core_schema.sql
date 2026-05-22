CREATE TABLE IF NOT EXISTS competitions (
  competition_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT,
  region TEXT,
  competition_type TEXT NOT NULL,
  team_type TEXT NOT NULL,
  season_calendar TEXT,
  provider_primary TEXT,
  provider_secondary TEXT,
  coverage_tier TEXT,
  model_status TEXT DEFAULT 'inactive',
  config_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seasons (
  season_id TEXT PRIMARY KEY,
  competition_id TEXT REFERENCES competitions(competition_id),
  name TEXT NOT NULL,
  start_date DATE,
  end_date DATE,
  current_matchday INT,
  status TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
  team_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT,
  team_type TEXT NOT NULL,
  founded INT,
  venue_name TEXT,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_entity_mappings (
  mapping_id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  provider_entity_id TEXT NOT NULL,
  canonical_entity_id TEXT NOT NULL,
  confidence NUMERIC DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(provider, entity_type, provider_entity_id)
);

CREATE TABLE IF NOT EXISTS fixtures (
  fixture_id TEXT PRIMARY KEY,
  competition_id TEXT REFERENCES competitions(competition_id),
  season_id TEXT REFERENCES seasons(season_id),
  stage TEXT,
  round TEXT,
  matchday INT,
  home_team_id TEXT REFERENCES teams(team_id),
  away_team_id TEXT REFERENCES teams(team_id),
  kickoff_time_utc TIMESTAMPTZ NOT NULL,
  venue TEXT,
  neutral_venue BOOLEAN DEFAULT false,
  leg_type TEXT,
  aggregate_context_json JSONB DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'scheduled',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff_time_utc);
CREATE INDEX IF NOT EXISTS idx_fixtures_competition ON fixtures(competition_id);

CREATE TABLE IF NOT EXISTS results (
  fixture_id TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
  home_goals INT NOT NULL,
  away_goals INT NOT NULL,
  halftime_home_goals INT,
  halftime_away_goals INT,
  result_1x2 TEXT NOT NULL,
  settled_at TIMESTAMPTZ,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_provider_payloads (
  payload_id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  entity_type TEXT,
  entity_id_hint TEXT,
  response_json JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_payload_provider_time
  ON raw_provider_payloads(provider, fetched_at DESC);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  odds_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  provider TEXT NOT NULL,
  bookmaker TEXT,
  market_type TEXT NOT NULL,
  line NUMERIC,
  side TEXT,
  outcome TEXT NOT NULL,
  decimal_odds NUMERIC NOT NULL,
  raw_implied_probability NUMERIC,
  fair_probability NUMERIC,
  overround NUMERIC,
  liquidity NUMERIC,
  spread NUMERIC,
  snapshot_time_utc TIMESTAMPTZ NOT NULL,
  is_opening BOOLEAN DEFAULT false,
  is_closing BOOLEAN DEFAULT false,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_odds_fixture_market_time
  ON odds_snapshots(fixture_id, market_type, snapshot_time_utc DESC);

CREATE TABLE IF NOT EXISTS feature_snapshots (
  feature_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  feature_time_utc TIMESTAMPTZ NOT NULL,
  feature_version TEXT NOT NULL,
  features_json JSONB NOT NULL,
  source_snapshot_refs JSONB DEFAULT '{}',
  data_quality_score NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feature_fixture_time
  ON feature_snapshots(fixture_id, feature_time_utc DESC);

CREATE TABLE IF NOT EXISTS model_versions (
  model_version TEXT PRIMARY KEY,
  model_family TEXT NOT NULL,
  status TEXT NOT NULL,
  training_start_date DATE,
  training_end_date DATE,
  feature_version TEXT,
  calibration_version TEXT,
  artifact_uri TEXT,
  metrics_json JSONB DEFAULT '{}',
  params_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  activated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS score_probability_grids (
  score_grid_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  prediction_time_utc TIMESTAMPTZ NOT NULL,
  model_version TEXT REFERENCES model_versions(model_version),
  calibration_version TEXT,
  max_goals INT NOT NULL DEFAULT 8,
  grid_json JSONB NOT NULL,
  tail_mass NUMERIC NOT NULL DEFAULT 0,
  lambda_home NUMERIC,
  lambda_away NUMERIC,
  chaos_prob NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_score_grid_fixture_time
  ON score_probability_grids(fixture_id, prediction_time_utc DESC);

CREATE TABLE IF NOT EXISTS prediction_snapshots (
  prediction_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  prediction_time_utc TIMESTAMPTZ NOT NULL,
  model_version TEXT REFERENCES model_versions(model_version),
  feature_snapshot_id BIGINT REFERENCES feature_snapshots(feature_snapshot_id),
  feature_version TEXT NOT NULL,
  calibration_version TEXT NOT NULL,
  score_grid_id BIGINT REFERENCES score_probability_grids(score_grid_id),
  p_home NUMERIC NOT NULL,
  p_draw NUMERIC NOT NULL,
  p_away NUMERIC NOT NULL,
  market_probabilities_json JSONB NOT NULL DEFAULT '{}',
  uncertainty TEXT,
  data_quality_score NUMERIC,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_prediction_fixture_time
  ON prediction_snapshots(fixture_id, prediction_time_utc DESC);

CREATE TABLE IF NOT EXISTS market_predictions (
  market_prediction_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  line NUMERIC,
  side TEXT,
  outcome TEXT NOT NULL,
  probability NUMERIC NOT NULL,
  fair_odds NUMERIC,
  settlement_rule_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_predictions_fixture
  ON market_predictions(fixture_id, market_type, line);

CREATE TABLE IF NOT EXISTS upset_alerts (
  upset_alert_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  upset_type TEXT NOT NULL,
  target_market_type TEXT,
  target_line NUMERIC,
  target_outcome TEXT,
  model_probability NUMERIC,
  market_probability NUMERIC,
  probability_gap NUMERIC,
  favorite_fragility_score NUMERIC,
  upset_score NUMERIC,
  risk_level TEXT,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parlay_recommendations (
  parlay_recommendation_id BIGSERIAL PRIMARY KEY,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  is_multiple BOOLEAN DEFAULT false,
  unit_stake NUMERIC NOT NULL,
  multiplier INT DEFAULT 1,
  total_atomic_bets INT NOT NULL,
  total_stake NUMERIC NOT NULL,
  hit_probability NUMERIC,
  expected_payout NUMERIC,
  expected_value NUMERIC,
  roi NUMERIC,
  risk_score NUMERIC,
  risk_level TEXT,
  correlation_penalty NUMERIC,
  recommendation_score NUMERIC,
  rule_valid BOOLEAN DEFAULT true,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parlay_legs (
  parlay_leg_id BIGSERIAL PRIMARY KEY,
  parlay_recommendation_id BIGINT REFERENCES parlay_recommendations(parlay_recommendation_id),
  leg_index INT NOT NULL,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  line NUMERIC,
  selected_outcomes_json JSONB NOT NULL,
  probabilities_json JSONB NOT NULL,
  odds_json JSONB,
  confidence TEXT,
  data_quality_score NUMERIC
);

CREATE TABLE IF NOT EXISTS parlay_atomic_bets (
  atomic_bet_id BIGSERIAL PRIMARY KEY,
  parlay_recommendation_id BIGINT REFERENCES parlay_recommendations(parlay_recommendation_id),
  outcomes_json JSONB NOT NULL,
  stake NUMERIC NOT NULL,
  probability NUMERIC,
  odds_product NUMERIC,
  expected_payout NUMERIC,
  expected_value NUMERIC,
  result_status TEXT,
  settled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS prediction_evaluations (
  evaluation_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  actual_home_goals INT NOT NULL,
  actual_away_goals INT NOT NULL,
  actual_result_1x2 TEXT NOT NULL,
  log_loss_1x2 NUMERIC,
  brier_score_1x2 NUMERIC,
  actual_score_probability NUMERIC,
  actual_score_rank INT,
  market_comparison_json JSONB DEFAULT '{}',
  error_tags_json JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now()
);
