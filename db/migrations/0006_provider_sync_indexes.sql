CREATE INDEX IF NOT EXISTS idx_raw_payload_entity_time
  ON raw_provider_payloads(provider, entity_type, entity_id_hint, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_payload_request_hash
  ON raw_provider_payloads(provider, endpoint, request_hash);

CREATE INDEX IF NOT EXISTS idx_provider_sync_runs_status_started
  ON provider_sync_runs(status, started_at DESC);
