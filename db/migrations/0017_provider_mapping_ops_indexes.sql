CREATE INDEX IF NOT EXISTS idx_provider_entity_mappings_provider_type_updated
  ON provider_entity_mappings(provider, entity_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_entity_mappings_canonical_updated
  ON provider_entity_mappings(entity_type, canonical_entity_id, updated_at DESC);
