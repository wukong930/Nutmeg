CREATE INDEX IF NOT EXISTS idx_player_availability_payload
  ON player_availability_snapshots(payload_id);

CREATE INDEX IF NOT EXISTS idx_lineup_snapshots_payload
  ON lineup_snapshots(payload_id);

CREATE INDEX IF NOT EXISTS idx_player_availability_source_time
  ON player_availability_snapshots(source, snapshot_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_lineup_snapshots_source_time
  ON lineup_snapshots(source, snapshot_time_utc DESC);
