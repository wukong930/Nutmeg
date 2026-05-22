CREATE TABLE IF NOT EXISTS provider_mapping_review_runs (
  provider_mapping_review_run_id BIGSERIAL PRIMARY KEY,
  provider TEXT,
  entity_type TEXT,
  canonical_entity_id TEXT,
  low_confidence_threshold NUMERIC NOT NULL,
  stale_after_days INT NOT NULL,
  checked_mapping_count INT NOT NULL DEFAULT 0,
  issue_count INT NOT NULL DEFAULT 0,
  critical_count INT NOT NULL DEFAULT 0,
  warning_count INT NOT NULL DEFAULT 0,
  info_count INT NOT NULL DEFAULT 0,
  issues_json JSONB NOT NULL DEFAULT '[]',
  requested_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_provider_mapping_review_runs_created
  ON provider_mapping_review_runs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_mapping_review_runs_scope
  ON provider_mapping_review_runs(provider, entity_type, canonical_entity_id, created_at DESC);
