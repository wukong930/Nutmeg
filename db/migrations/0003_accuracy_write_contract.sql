CREATE UNIQUE INDEX IF NOT EXISTS idx_calibration_buckets_unique_nullable
  ON calibration_buckets (
    model_version,
    market_type,
    outcome,
    competition_id,
    bucket_start,
    bucket_end
  ) NULLS NOT DISTINCT;
