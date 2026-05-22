CREATE TABLE IF NOT EXISTS provider_observations (
  provider_observation_id BIGSERIAL PRIMARY KEY,
  provider_name TEXT NOT NULL,
  capability TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  canonical_entity_id TEXT NOT NULL,
  provider_entity_id TEXT,
  field_name TEXT NOT NULL,
  observed_value TEXT NOT NULL,
  observed_at_utc TIMESTAMPTZ NOT NULL,
  confidence NUMERIC NOT NULL DEFAULT 1.0,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id),
  metadata_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_provider_observations_entity_field_time
  ON provider_observations(entity_type, canonical_entity_id, field_name, observed_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_provider_observations_provider_capability_time
  ON provider_observations(provider_name, capability, observed_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_provider_observations_payload
  ON provider_observations(payload_id);
