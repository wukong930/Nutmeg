-- Provider runtime monitoring snapshots.
-- Stores operational signals only; API keys, tokens, and provider secrets must
-- never be persisted here.

CREATE TABLE IF NOT EXISTS provider_runtime_snapshots (
  provider_runtime_snapshot_id BIGSERIAL PRIMARY KEY,
  provider_name TEXT NOT NULL,
  capability TEXT NOT NULL,
  probe_status TEXT NOT NULL CHECK (
    probe_status IN (
      'not_configured',
      'key_configured',
      'ok',
      'limited',
      'auth_failed',
      'rate_limited',
      'unavailable',
      'adapter_planned'
    )
  ),
  key_configured BOOLEAN NOT NULL DEFAULT FALSE,
  live_probe BOOLEAN NOT NULL DEFAULT FALSE,
  safe_to_call_real_provider BOOLEAN NOT NULL DEFAULT FALSE,
  latency_ms INT CHECK (latency_ms IS NULL OR latency_ms >= 0),
  error_rate NUMERIC CHECK (
    error_rate IS NULL OR (error_rate >= 0 AND error_rate <= 1)
  ),
  success_count INT NOT NULL DEFAULT 0 CHECK (success_count >= 0),
  failure_count INT NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
  rate_limit_remaining INT CHECK (
    rate_limit_remaining IS NULL OR rate_limit_remaining >= 0
  ),
  quota_window TEXT,
  fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
  message TEXT NOT NULL DEFAULT '',
  next_action TEXT NOT NULL DEFAULT 'no_action' CHECK (
    next_action IN (
      'no_action',
      'configure_runtime_key',
      'review_provider_plan_limit',
      'check_provider_credentials',
      'retry_after_provider_recovery',
      'adapter_not_ready'
    )
  ),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_snapshots_observed
  ON provider_runtime_snapshots (observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_snapshots_provider_observed
  ON provider_runtime_snapshots (provider_name, capability, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_runtime_snapshots_status_observed
  ON provider_runtime_snapshots (probe_status, observed_at DESC);
