CREATE TABLE IF NOT EXISTS player_availability_snapshots (
  availability_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  team_id TEXT REFERENCES teams(team_id),
  player_id TEXT,
  player_name TEXT,
  status TEXT NOT NULL,
  reason TEXT,
  expected_return_date DATE,
  source TEXT,
  source_confidence NUMERIC,
  snapshot_time_utc TIMESTAMPTZ NOT NULL,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_player_availability_fixture_time
  ON player_availability_snapshots(fixture_id, snapshot_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_player_availability_team_time
  ON player_availability_snapshots(team_id, snapshot_time_utc DESC);

CREATE TABLE IF NOT EXISTS lineup_snapshots (
  lineup_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  team_id TEXT REFERENCES teams(team_id),
  lineup_type TEXT NOT NULL,
  player_id TEXT,
  player_name TEXT,
  position TEXT,
  probability_start NUMERIC,
  is_starter BOOLEAN,
  source TEXT,
  snapshot_time_utc TIMESTAMPTZ NOT NULL,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lineup_snapshots_fixture_time
  ON lineup_snapshots(fixture_id, snapshot_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_lineup_snapshots_team_time
  ON lineup_snapshots(team_id, snapshot_time_utc DESC);
