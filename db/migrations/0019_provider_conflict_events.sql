CREATE TABLE IF NOT EXISTS provider_conflict_events (
  provider_conflict_event_id BIGSERIAL PRIMARY KEY,
  source_review_run_id BIGINT REFERENCES provider_mapping_review_runs(provider_mapping_review_run_id),
  conflict_type TEXT NOT NULL CHECK (
    conflict_type IN ('provider_mapping_conflict', 'provider_observation_conflict')
  ),
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  entity_type TEXT NOT NULL,
  canonical_entity_id TEXT NOT NULL,
  provider_names_json JSONB NOT NULL DEFAULT '[]',
  provider_entity_ids_json JSONB NOT NULL DEFAULT '[]',
  trusted_provider TEXT,
  resolution_status TEXT NOT NULL DEFAULT 'open' CHECK (
    resolution_status IN ('open', 'resolved', 'ignored')
  ),
  data_quality_score_delta NUMERIC NOT NULL DEFAULT 0,
  evidence_json JSONB NOT NULL DEFAULT '{}',
  recommended_action TEXT NOT NULL,
  requested_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_provider_conflict_events_status_created
  ON provider_conflict_events(resolution_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_conflict_events_entity_created
  ON provider_conflict_events(entity_type, canonical_entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_conflict_events_review
  ON provider_conflict_events(source_review_run_id);

CREATE TABLE IF NOT EXISTS provider_trusted_priorities (
  provider_trusted_priority_id BIGSERIAL PRIMARY KEY,
  provider_name TEXT NOT NULL,
  capability TEXT NOT NULL,
  priority_rank INT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  reason TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (provider_name, capability)
);

CREATE INDEX IF NOT EXISTS idx_provider_trusted_priorities_capability_rank
  ON provider_trusted_priorities(capability, priority_rank);
