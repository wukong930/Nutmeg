CREATE INDEX IF NOT EXISTS idx_feature_snapshots_version_time
  ON feature_snapshots(feature_version, feature_time_utc DESC);

CREATE INDEX IF NOT EXISTS idx_feature_snapshots_quality
  ON feature_snapshots(data_quality_score);
