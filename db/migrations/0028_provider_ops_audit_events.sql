CREATE TABLE IF NOT EXISTS provider_ops_audit_events (
  provider_ops_audit_event_id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  operator_name TEXT,
  action_surface TEXT NOT NULL DEFAULT 'provider_ops',
  target_type TEXT,
  target_id TEXT,
  outcome TEXT NOT NULL DEFAULT 'success',
  request_path TEXT,
  request_method TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provider_ops_audit_events_created
  ON provider_ops_audit_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_ops_audit_events_operator_created
  ON provider_ops_audit_events(operator_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_ops_audit_events_type_created
  ON provider_ops_audit_events(event_type, created_at DESC);
