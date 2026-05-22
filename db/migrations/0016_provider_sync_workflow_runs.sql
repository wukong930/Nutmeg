CREATE TABLE IF NOT EXISTS provider_sync_workflow_runs (
  provider_sync_workflow_run_id BIGSERIAL PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  dry_run BOOLEAN NOT NULL DEFAULT TRUE,
  requested_by TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  duration_ms INT,
  fixture_sync_run_id BIGINT REFERENCES provider_sync_runs(provider_sync_run_id),
  odds_sync_run_ids_json JSONB NOT NULL DEFAULT '[]',
  availability_sync_run_ids_json JSONB NOT NULL DEFAULT '[]',
  fixture_count INT NOT NULL DEFAULT 0,
  odds_snapshot_count INT NOT NULL DEFAULT 0,
  availability_snapshot_count INT NOT NULL DEFAULT 0,
  raw_payload_ids_json JSONB NOT NULL DEFAULT '[]',
  canonical_fixture_ids_json JSONB NOT NULL DEFAULT '[]',
  prematch_workflow_run_id BIGINT REFERENCES prematch_workflow_runs(prematch_workflow_run_id),
  warnings_json JSONB NOT NULL DEFAULT '[]',
  error_message TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_runs_status_started
  ON provider_sync_workflow_runs(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_runs_fixture_sync
  ON provider_sync_workflow_runs(fixture_sync_run_id);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_runs_prematch
  ON provider_sync_workflow_runs(prematch_workflow_run_id);
