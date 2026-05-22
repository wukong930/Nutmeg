CREATE INDEX IF NOT EXISTS idx_odds_snapshots_provider_bookmaker_time
  ON odds_snapshots(provider, bookmaker, snapshot_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_payload
  ON odds_snapshots(payload_id);
