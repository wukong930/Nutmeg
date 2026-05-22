WITH ranked_odds_snapshots AS (
  SELECT
    odds_snapshot_id,
    row_number() OVER (
      PARTITION BY
        fixture_id,
        provider,
        bookmaker,
        market_type,
        line,
        side,
        outcome,
        snapshot_time_utc
      ORDER BY created_at DESC, payload_id DESC NULLS LAST, odds_snapshot_id DESC
    ) AS duplicate_rank
  FROM odds_snapshots
)
DELETE FROM odds_snapshots os
USING ranked_odds_snapshots ranked
WHERE os.odds_snapshot_id = ranked.odds_snapshot_id
  AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshots_unique_market_tick
  ON odds_snapshots (
    fixture_id,
    provider,
    bookmaker,
    market_type,
    line,
    side,
    outcome,
    snapshot_time_utc
  )
  NULLS NOT DISTINCT;
