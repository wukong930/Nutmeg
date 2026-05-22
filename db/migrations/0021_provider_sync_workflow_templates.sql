CREATE TABLE IF NOT EXISTS provider_sync_workflow_templates (
  provider_sync_workflow_template_id BIGSERIAL PRIMARY KEY,
  template_name TEXT NOT NULL,
  description TEXT,
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  fixture_sync_json JSONB,
  odds_syncs_json JSONB NOT NULL DEFAULT '[]',
  availability_syncs_json JSONB NOT NULL DEFAULT '[]',
  run_conflict_detection BOOLEAN NOT NULL DEFAULT FALSE,
  conflict_observation_lookback_hours INT NOT NULL DEFAULT 168,
  conflict_limit INT NOT NULL DEFAULT 1000,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_templates_updated
  ON provider_sync_workflow_templates(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_templates_name
  ON provider_sync_workflow_templates(template_name);
