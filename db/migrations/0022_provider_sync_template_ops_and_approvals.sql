ALTER TABLE provider_sync_workflow_templates
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS archived_by TEXT,
  ADD COLUMN IF NOT EXISTS archive_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_templates_active_updated
  ON provider_sync_workflow_templates(updated_at DESC)
  WHERE archived_at IS NULL;

CREATE TABLE IF NOT EXISTS provider_sync_workflow_operator_approvals (
  provider_sync_workflow_approval_id BIGSERIAL PRIMARY KEY,
  approval_type TEXT NOT NULL,
  approval_status TEXT NOT NULL DEFAULT 'approved',
  provider_sync_workflow_template_id BIGINT
    REFERENCES provider_sync_workflow_templates(provider_sync_workflow_template_id)
    ON DELETE SET NULL,
  provider_sync_workflow_run_id BIGINT
    REFERENCES provider_sync_workflow_runs(provider_sync_workflow_run_id)
    ON DELETE SET NULL,
  approved_by TEXT,
  approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  approval_note TEXT,
  request_payload_json JSONB NOT NULL DEFAULT '{}',
  metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_approvals_approved
  ON provider_sync_workflow_operator_approvals(approved_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_approvals_template
  ON provider_sync_workflow_operator_approvals(provider_sync_workflow_template_id);

CREATE INDEX IF NOT EXISTS idx_provider_sync_workflow_approvals_run
  ON provider_sync_workflow_operator_approvals(provider_sync_workflow_run_id);
