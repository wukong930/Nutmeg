ALTER TABLE parlay_recommendations
  ADD COLUMN IF NOT EXISTS model_version TEXT REFERENCES model_versions(model_version),
  ADD COLUMN IF NOT EXISTS prediction_snapshot_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'recommendation_engine_v1',
  ADD COLUMN IF NOT EXISTS settlement_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE parlay_legs
  ADD COLUMN IF NOT EXISTS prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  ADD COLUMN IF NOT EXISTS model_version TEXT REFERENCES model_versions(model_version),
  ADD COLUMN IF NOT EXISTS side TEXT;

ALTER TABLE parlay_atomic_bets
  ADD COLUMN IF NOT EXISTS gross_payout NUMERIC,
  ADD COLUMN IF NOT EXISTS profit_loss NUMERIC,
  ADD COLUMN IF NOT EXISTS settlement_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_parlay_recommendations_model_created
  ON parlay_recommendations(model_version, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_parlay_legs_prediction_snapshot
  ON parlay_legs(prediction_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_parlay_atomic_bets_settlement
  ON parlay_atomic_bets(result_status, settled_at);
