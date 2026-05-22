-- Provider runtime incident reports generated from monitoring snapshots.
-- Stores operational summaries and alert metadata only; provider secrets and
-- raw provider payloads must not be written here.

CREATE TABLE IF NOT EXISTS provider_runtime_incident_reports (
  provider_runtime_incident_report_id BIGSERIAL PRIMARY KEY,
  alert_level TEXT NOT NULL CHECK (alert_level IN ('ok', 'P0', 'P1', 'P2')),
  alert_count INT NOT NULL DEFAULT 0 CHECK (alert_count >= 0),
  snapshot_count INT NOT NULL DEFAULT 0 CHECK (snapshot_count >= 0),
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  alerts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  thresholds_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'manual',
  created_by TEXT NOT NULL DEFAULT 'nutmeg-ops',
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_incidents_created
  ON provider_runtime_incident_reports (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_incidents_level_created
  ON provider_runtime_incident_reports (alert_level, created_at DESC);
