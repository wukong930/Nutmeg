INSERT INTO provider_authorizations (
  provider_name,
  status,
  capabilities_json,
  terms_checked_at_utc,
  commercial_use_allowed,
  retention_allowed,
  api_key_env_var,
  notes
) VALUES
  (
    'mock-local',
    'active',
    '[
      "competitions",
      "seasons",
      "fixtures",
      "fixture_detail",
      "results",
      "odds",
      "lineups",
      "injuries",
      "team_stats"
    ]'::jsonb,
    '2026-05-06T00:00:00Z',
    TRUE,
    TRUE,
    NULL,
    'Local deterministic fixture provider for development and tests.'
  ),
  (
    'football-data.org',
    'pending_review',
    '["competitions", "seasons", "fixtures", "results"]'::jsonb,
    '2026-05-06T00:00:00Z',
    FALSE,
    FALSE,
    'FOOTBALL_DATA_API_KEY',
    'Candidate schedule/result provider; legal and retention review required before production.'
  ),
  (
    'the-odds-api',
    'pending_review',
    '["odds"]'::jsonb,
    '2026-05-06T00:00:00Z',
    FALSE,
    FALSE,
    'THE_ODDS_API_KEY',
    'Candidate odds provider; verify historical snapshot retention terms.'
  ),
  (
    'sportmonks',
    'pending_review',
    '["fixtures", "results", "odds", "lineups", "injuries", "team_stats"]'::jsonb,
    '2026-05-06T00:00:00Z',
    FALSE,
    FALSE,
    'SPORTMONKS_API_KEY',
    'Candidate broad coverage provider; production use requires explicit plan and contract check.'
  )
ON CONFLICT (provider_name)
DO UPDATE SET
  status = EXCLUDED.status,
  capabilities_json = EXCLUDED.capabilities_json,
  terms_checked_at_utc = EXCLUDED.terms_checked_at_utc,
  commercial_use_allowed = EXCLUDED.commercial_use_allowed,
  retention_allowed = EXCLUDED.retention_allowed,
  api_key_env_var = EXCLUDED.api_key_env_var,
  notes = EXCLUDED.notes,
  updated_at = now();
