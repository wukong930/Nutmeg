CREATE INDEX IF NOT EXISTS idx_market_predictions_snapshot_market
  ON market_predictions(prediction_snapshot_id, market_type, probability DESC);

CREATE INDEX IF NOT EXISTS idx_market_predictions_fixture_outcome
  ON market_predictions(fixture_id, market_type, line, side, outcome);

CREATE INDEX IF NOT EXISTS idx_prediction_snapshots_model_time
  ON prediction_snapshots(model_version, prediction_time_utc DESC);
