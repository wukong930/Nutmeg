ALTER TABLE provider_authorizations
  ADD COLUMN IF NOT EXISTS allowed_use TEXT NOT NULL DEFAULT 'research_and_development',
  ADD COLUMN IF NOT EXISTS rate_limit TEXT,
  ADD COLUMN IF NOT EXISTS historical_data_allowed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS redistribution_allowed BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS terms_url TEXT,
  ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT 'nutmeg-ops';

UPDATE provider_authorizations
SET
  allowed_use = 'local_development_and_test',
  rate_limit = 'none',
  historical_data_allowed = true,
  redistribution_allowed = true,
  terms_url = NULL,
  owner = 'nutmeg-ops',
  notes = 'Local deterministic fixture provider for development and tests.',
  updated_at = now()
WHERE provider_name = 'mock-local';

UPDATE provider_authorizations
SET
  allowed_use = 'fixtures_results_research_dry_run',
  rate_limit = 'free_plan_provider_defined',
  historical_data_allowed = false,
  redistribution_allowed = false,
  terms_url = 'https://www.football-data.org/terms',
  owner = 'nutmeg-ops',
  updated_at = now()
WHERE provider_name = 'football-data.org';

UPDATE provider_authorizations
SET
  allowed_use = 'odds_snapshot_research_dry_run',
  rate_limit = 'free_plan_provider_defined',
  historical_data_allowed = false,
  redistribution_allowed = false,
  terms_url = 'https://the-odds-api.com/terms.html',
  owner = 'nutmeg-ops',
  updated_at = now()
WHERE provider_name = 'the-odds-api';

UPDATE provider_authorizations
SET
  allowed_use = 'broad_coverage_trial_research',
  rate_limit = 'trial_plan_provider_defined',
  historical_data_allowed = false,
  redistribution_allowed = false,
  terms_url = 'https://www.sportmonks.com/terms-of-service/',
  owner = 'nutmeg-ops',
  updated_at = now()
WHERE provider_name = 'sportmonks';

INSERT INTO provider_authorizations (
  provider_name,
  status,
  capabilities_json,
  terms_checked_at_utc,
  commercial_use_allowed,
  retention_allowed,
  api_key_env_var,
  allowed_use,
  rate_limit,
  historical_data_allowed,
  redistribution_allowed,
  terms_url,
  owner,
  notes
) VALUES (
  'api-football',
  'pending_review',
  '["competitions", "seasons", "fixtures", "results"]'::jsonb,
  '2026-05-08T00:00:00Z',
  false,
  false,
  'API_FOOTBALL_API_KEY',
  'fixture_result_fallback_research_dry_run',
  'free_plan_provider_defined',
  false,
  false,
  'https://www.api-football.com/terms',
  'nutmeg-ops',
  'Candidate broad fixture/result fallback; free plan can be season-limited.'
)
ON CONFLICT (provider_name)
DO UPDATE SET
  status = EXCLUDED.status,
  capabilities_json = EXCLUDED.capabilities_json,
  terms_checked_at_utc = EXCLUDED.terms_checked_at_utc,
  commercial_use_allowed = EXCLUDED.commercial_use_allowed,
  retention_allowed = EXCLUDED.retention_allowed,
  api_key_env_var = EXCLUDED.api_key_env_var,
  allowed_use = EXCLUDED.allowed_use,
  rate_limit = EXCLUDED.rate_limit,
  historical_data_allowed = EXCLUDED.historical_data_allowed,
  redistribution_allowed = EXCLUDED.redistribution_allowed,
  terms_url = EXCLUDED.terms_url,
  owner = EXCLUDED.owner,
  notes = EXCLUDED.notes,
  updated_at = now();
