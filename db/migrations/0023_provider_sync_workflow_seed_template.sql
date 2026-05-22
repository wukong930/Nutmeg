WITH seeded_template AS (
  INSERT INTO provider_sync_workflow_templates (
    template_name,
    description,
    dry_run,
    fixture_sync_json,
    odds_syncs_json,
    availability_syncs_json,
    run_conflict_detection,
    conflict_observation_lookback_hours,
    conflict_limit,
    created_by,
    metadata_json
  )
  SELECT
    'VPS EPL explicit-ID dry-run',
    'Seeded explicit-ID Provider Sync dry-run template for operator review.',
    TRUE,
    '{
      "provider_competition_id": "PL",
      "canonical_competition_id": "EPL",
      "season": "2025"
    }'::jsonb,
    '[
      {
        "sport_key": "soccer_epl",
        "provider_event_id": "event-id",
        "canonical_fixture_id": "fd_fixture_330299",
        "regions": "eu",
        "markets": "h2h,spreads"
      }
    ]'::jsonb,
    '[
      {
        "provider_fixture_id": "sportmonks-fixture-id",
        "canonical_fixture_id": "fd_fixture_330299",
        "team_mappings": [
          {
            "provider_team_id": "57",
            "canonical_team_id": "fd_team_57"
          },
          {
            "provider_team_id": "64",
            "canonical_team_id": "fd_team_64"
          }
        ]
      }
    ]'::jsonb,
    TRUE,
    168,
    1000,
    'system_seed',
    '{
      "source": "migration_0023",
      "seed_only": true,
      "template_operation": "seed"
    }'::jsonb
  WHERE NOT EXISTS (
    SELECT 1
    FROM provider_sync_workflow_templates
    WHERE template_name = 'VPS EPL explicit-ID dry-run'
  )
  RETURNING provider_sync_workflow_template_id
),
target_template AS (
  SELECT provider_sync_workflow_template_id
  FROM seeded_template
  UNION ALL
  SELECT provider_sync_workflow_template_id
  FROM provider_sync_workflow_templates
  WHERE template_name = 'VPS EPL explicit-ID dry-run'
    AND NOT EXISTS (SELECT 1 FROM seeded_template)
  LIMIT 1
)
INSERT INTO provider_sync_workflow_operator_approvals (
  approval_type,
  approval_status,
  provider_sync_workflow_template_id,
  provider_sync_workflow_run_id,
  approved_by,
  approval_note,
  request_payload_json,
  metadata_json
)
SELECT
  'provider_sync_workflow_seed_review',
  'approved',
  provider_sync_workflow_template_id,
  NULL,
  'system_seed',
  'Seeded template review marker; dry-run execution still requires operator approval.',
  '{
    "dry_run": true,
    "operator_approved": false,
    "template_name": "VPS EPL explicit-ID dry-run"
  }'::jsonb,
  '{
    "source": "migration_0023",
    "seed_only": true
  }'::jsonb
FROM target_template
WHERE NOT EXISTS (
  SELECT 1
  FROM provider_sync_workflow_operator_approvals approvals
  WHERE approvals.approval_type = 'provider_sync_workflow_seed_review'
    AND approvals.provider_sync_workflow_template_id =
      target_template.provider_sync_workflow_template_id
);
