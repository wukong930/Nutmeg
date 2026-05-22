-- Provider runtime incident lifecycle state.
-- This keeps incident handling auditable without adding notification delivery
-- side effects or storing provider secrets.

ALTER TABLE provider_runtime_incident_reports
  ADD COLUMN IF NOT EXISTS incident_status TEXT NOT NULL DEFAULT 'open',
  ADD COLUMN IF NOT EXISTS acknowledged_by TEXT,
  ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolved_by TEXT,
  ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolution_note TEXT,
  ADD COLUMN IF NOT EXISTS notification_status TEXT NOT NULL DEFAULT 'not_configured',
  ADD COLUMN IF NOT EXISTS notification_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'provider_runtime_incident_status_check'
  ) THEN
    ALTER TABLE provider_runtime_incident_reports
      ADD CONSTRAINT provider_runtime_incident_status_check
      CHECK (incident_status IN ('open', 'acknowledged', 'resolved', 'ignored'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'provider_runtime_incident_notification_status_check'
  ) THEN
    ALTER TABLE provider_runtime_incident_reports
      ADD CONSTRAINT provider_runtime_incident_notification_status_check
      CHECK (notification_status IN ('not_configured', 'queued', 'sent', 'skipped', 'failed'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_provider_runtime_incidents_status_created
  ON provider_runtime_incident_reports (incident_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_incidents_updated
  ON provider_runtime_incident_reports (updated_at DESC);
