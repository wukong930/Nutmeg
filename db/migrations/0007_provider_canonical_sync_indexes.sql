CREATE INDEX IF NOT EXISTS idx_provider_entity_mappings_canonical
  ON provider_entity_mappings(entity_type, canonical_entity_id);

CREATE INDEX IF NOT EXISTS idx_fixtures_status_kickoff
  ON fixtures(status, kickoff_time_utc);

CREATE INDEX IF NOT EXISTS idx_results_source
  ON results(source);
