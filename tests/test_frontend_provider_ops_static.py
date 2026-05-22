from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_provider_ops_page_is_wired_to_phase_ten_provider_state() -> None:
    page = (ROOT / "apps/web/app/providers/page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "apps/web/lib/api.ts").read_text(encoding="utf-8")
    workflow_component = (
        ROOT / "apps/web/components/providers/provider-sync-workflow-actions.tsx"
    ).read_text(encoding="utf-8")
    mapped_odds_component = (
        ROOT / "apps/web/components/providers/provider-mapped-odds-actions.tsx"
    ).read_text(encoding="utf-8")
    authorization_review_component = (
        ROOT
        / "apps/web/components/providers/provider-authorization-review-actions.tsx"
    ).read_text(encoding="utf-8")
    runtime_incident_component = (
        ROOT / "apps/web/components/providers/provider-runtime-incident-actions.tsx"
    ).read_text(encoding="utf-8")
    access_component = (
        ROOT / "apps/web/components/providers/provider-ops-access-panel.tsx"
    ).read_text(encoding="utf-8")
    access_auth = (ROOT / "apps/web/lib/provider-ops-auth.ts").read_text(
        encoding="utf-8"
    )
    provider_actions = (ROOT / "apps/web/app/providers/actions.ts").read_text(
        encoding="utf-8"
    )
    api_contract = (ROOT / "apps/web/lib/api-contract.ts").read_text(
        encoding="utf-8"
    )
    runbook_component = (
        ROOT / "apps/web/components/providers/provider-ops-runbook.tsx"
    ).read_text(encoding="utf-8")
    audit_migration = (
        ROOT / "db/migrations/0028_provider_ops_audit_events.sql"
    ).read_text(encoding="utf-8")
    runtime_monitoring_migration = (
        ROOT / "db/migrations/0029_provider_runtime_monitoring.sql"
    ).read_text(encoding="utf-8")
    vps_compose = (ROOT / "docker-compose.vps.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    onboarding_script = (
        ROOT / "scripts/vps-provider-onboarding-assessment.sh"
    ).read_text(encoding="utf-8")
    odds_gap_script = (
        ROOT / "scripts/vps-provider-odds-gap-report.sh"
    ).read_text(encoding="utf-8")
    fallback_probe_script = (
        ROOT / "scripts/vps-provider-fallback-odds-probe.sh"
    ).read_text(encoding="utf-8")
    runtime_monitoring_script = (
        ROOT / "scripts/vps-provider-runtime-monitoring.sh"
    ).read_text(encoding="utf-8")
    local_runtime_monitoring_script = (
        ROOT / "scripts/provider-runtime-monitoring-local.sh"
    ).read_text(encoding="utf-8")
    runtime_monitoring_cron_script = (
        ROOT / "scripts/vps-provider-runtime-monitoring-cron.sh"
    ).read_text(encoding="utf-8")
    mapping_bootstrap_script = (
        ROOT / "scripts/vps-provider-mapping-bootstrap.sh"
    ).read_text(encoding="utf-8")
    sportmonks_mapping_bootstrap_script = (
        ROOT / "scripts/vps-provider-sportmonks-mapping-bootstrap.sh"
    ).read_text(encoding="utf-8")
    sportmonks_discovery_script = (
        ROOT / "scripts/vps-provider-sportmonks-discovery.sh"
    ).read_text(encoding="utf-8")
    api_football_discovery_script = (
        ROOT / "scripts/vps-provider-api-football-discovery.sh"
    ).read_text(encoding="utf-8")
    api_football_mapping_bootstrap_script = (
        ROOT / "scripts/vps-provider-api-football-mapping-bootstrap.sh"
    ).read_text(encoding="utf-8")
    seed_migration = (
        ROOT / "db/migrations/0023_provider_sync_workflow_seed_template.sql"
    ).read_text(encoding="utf-8")
    nav = (ROOT / "apps/web/components/layout/app-shell.tsx").read_text(
        encoding="utf-8"
    )

    assert "Provider Ops" in page
    assert "ProviderOpsAccessPanel" in page
    assert "getProviderOpsAccessState" in page
    assert "includeAdmin: access.unlocked" in page
    assert "Provider Ops Access" in access_component
    assert "Provider Ops Audit Trail" in page
    assert "ProviderOpsAuditTrailTable" in page
    assert "auditTrail" in page
    assert "Provider Helper Run History" in page
    assert "ProviderOpsRunHistoryTable" in page
    assert "runHistory" in page
    assert "providerOpsRunHistoryListResponseSchema" in api
    assert "/ops/provider-runs?limit=20" in api
    assert "provider_ops_run_history" in (
        ROOT / "db/migrations/0032_provider_ops_run_history.sql"
    ).read_text(encoding="utf-8")
    assert "Admin controls locked" in access_component
    assert "Admin controls unlocked" in access_component
    assert "NUTMEG_PROVIDER_OPS_UI_TOKEN" in access_auth
    assert "timingSafeEqual" in access_auth
    assert "httpOnly: true" in access_auth
    assert "requireProviderOpsAccess" in provider_actions
    assert "X-Nutmeg-Operator" in provider_actions
    assert "recordProviderOpsAuditEvent" in provider_actions
    assert "provider_ops_unlock" in provider_actions
    assert "provider_ops_lock" in provider_actions
    assert "provider_ops_admin_action" in provider_actions
    assert "/ops/provider-audit/events" in provider_actions
    assert "providerOpsAuditEventResponseSchema" in provider_actions
    assert "NUTMEG_PROVIDER_OPS_UI_TOKEN" in vps_compose
    assert "ProviderOpsRunbook" in page
    assert "Provider 授权状态" in page
    assert "使用策略" in page
    assert "历史/再分发" in page
    assert "Runtime key readiness" in page
    assert "Provider Runtime Monitor" in page
    assert "ProviderRuntimeMonitoringTable" in page
    assert "ProviderRuntimeAlertList" in page
    assert "alert {ops.runtimeMonitoring.alertLevel}" in page
    assert "Provider Runtime Incidents" in page
    assert "ProviderRuntimeIncidentTable" in page
    assert "ProviderRuntimeIncidentActions" in page
    assert "ProviderRuntimeIncidentTrendPanel" in page
    assert "ProviderRuntimeIncidentFilterPanel" in page
    assert "ProviderRuntimeIncidentRunbook" in page
    assert "Runtime incident trend" in page
    assert "Runtime incident filters" in page
    assert "Runtime Incident Runbook" in page
    assert "fallback incidents" in page
    assert "runtimeIncidentStatusTone" in page
    assert "incidentStatus" in page
    assert "acknowledgedBy" in page
    assert "resolvedBy" in page
    assert "incidentAlertSummary" in page
    assert "incidentThresholdSummary" in page
    assert "incidentNotificationSummary" in page
    assert "notificationPayloadJson" in page
    assert "provider_runtime_incident_notification_status" in (
        local_runtime_monitoring_script
    )
    assert "provider_runtime_monitoring_request_failed" in local_runtime_monitoring_script
    assert "subprocess.run" in local_runtime_monitoring_script
    assert "check_output" not in local_runtime_monitoring_script
    assert "NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_ENABLED" in vps_compose
    assert "NUTMEG_PROVIDER_RUNTIME_INCIDENT_NOTIFICATION_DRY_RUN" in vps_compose
    assert "meanTimeToResolveMinutes" in page
    assert "runtimeIncidentFiltersFromSearchParams" in page
    assert "runtimeIncidentFilterHref" in page
    assert "Runtime Incident Lifecycle" in runtime_incident_component
    assert "updateProviderRuntimeIncidentStatusAction" in runtime_incident_component
    assert "acknowledged" in runtime_incident_component
    assert "resolved" in runtime_incident_component
    assert "Free API application checklist" in page
    assert "赛事准入状态" in page
    assert "Provider 映射摘要" in page
    assert "Provider 映射审核" in page
    assert "Odds Coverage Gaps" in page
    assert "ProviderOddsGapTable" in page
    assert "Fallback Odds Probe" in page
    assert "ProviderFallbackOddsProbeTable" in page
    assert "Mapping missing" in page
    assert "No odds" in page
    assert "Stale odds" in page
    assert "Provider event unavailable" in page
    assert "fallback:" in page
    assert "Provider 冲突治理" in page
    assert "trusted provider priority" in page
    assert "最近映射关系" in page
    assert "getProviderOps" in api
    assert "/providers/status" in api
    assert "/ops/provider-audit/events?limit=20" in api
    assert "providerOpsAuditEventListResponseSchema" in api
    assert "/providers/runtime/credentials" in api
    assert "/providers/runtime/monitoring?limit=20" in api
    assert "providerRuntimeIncidentPath" in api
    assert "offset" in api_contract
    assert "total_count" in api_contract
    assert "has_more" in api_contract
    assert "runtimeIncidentSummaryFromResponse" in api
    assert "trendBuckets" in api
    assert "providerRuntimeMonitoringResponseSchema" in api
    assert "providerRuntimeIncidentReportListResponseSchema" in api
    assert "providerRuntimeIncidentStatusUpdateResponseSchema" in provider_actions
    assert "/providers/runtime/monitoring/incidents/${incidentId}/status" in (
        provider_actions
    )
    assert "runtimeIncidentsFromResponse" in api
    assert "runtimeMonitoring.alerts.map" in api
    assert "/providers/runtime/api-key-checklist" in api
    assert "/providers/mappings?limit=100" in api
    assert "/providers/mappings/review" in api
    assert "/providers/conflicts/evaluate" in api
    assert "/providers/odds/coverage?competition_id=EPL" in api
    assert "/providers/odds/gaps?competition_id=EPL" in api
    assert "/providers/odds/fallback-probe/sportmonks" in api
    assert "oddsGapReport" in api
    assert "fallbackOddsProbe" in api
    assert "no_odds" in api
    assert "stale_odds" in api
    assert "provider_event_unavailable" in api
    assert "providerEventUnavailableCount" in api
    assert "fallbackCandidates" in api
    assert "as_of_time_utc" in api
    assert "/providers/onboarding/assessments/latest?limit=20" in api
    assert "Provider Ops Runbook" in runbook_component
    assert "Runtime keys" in runbook_component
    assert "Fixture mappings" in runbook_component
    assert "Odds coverage" in runbook_component
    assert "Prediction gate" in runbook_component
    assert "Conflict governance" in runbook_component
    assert "Commit Mapped Odds" in mapped_odds_component
    assert "Commit mapped odds" in mapped_odds_component
    assert "operator approval" in mapped_odds_component
    assert "approve odds snapshot write" in mapped_odds_component
    assert "mapped_odds_commit_write_ack" in provider_actions
    assert "operator_approved" in provider_actions
    assert "Template task review matrix" in workflow_component
    assert "Task preflight issues" in workflow_component
    assert "NUTMEG_PROVIDER_SYNC_ENABLED:-true" in vps_compose
    assert "NUTMEG_PROVIDER_SYNC_WORKFLOW_ENABLED:-true" in vps_compose
    assert "NUTMEG_PROVIDER_SYNC_MOCK_DRY_RUN_ENABLED:-true" in vps_compose
    assert "provider-onboarding-assessment-vps" in makefile
    assert "provider-odds-gap-report-vps" in makefile
    assert "provider-runtime-monitoring-vps" in makefile
    assert "provider-runtime-monitoring-cron-vps" in makefile
    assert "provider-gap-remediation-vps" in makefile
    assert "provider-api-football-discovery-vps" in makefile
    assert "provider-api-football-mapping-bootstrap-vps" in makefile
    assert "provider-sportmonks-discovery-vps" in makefile
    assert "provider-sportmonks-mapping-bootstrap-vps" in makefile
    assert "provider-sportmonks-mapping-backfill-vps" in makefile
    assert "/providers/onboarding/assessments" in onboarding_script
    assert '"dry_run": False' in onboarding_script
    assert "NUTMEG_ONBOARDING_AS_OF_DAYS_AHEAD" in onboarding_script
    assert "/providers/odds/gaps" in odds_gap_script
    assert "provider_odds_gap_report" in odds_gap_script
    assert "event_unavailable" in odds_gap_script
    assert "fallback" in odds_gap_script
    assert "/providers/odds/fallback-probe/sportmonks" in fallback_probe_script
    assert "sportmonks_fallback_odds_probe" in fallback_probe_script
    assert "live_provider_probe" in fallback_probe_script
    assert "scripts/provider-runtime-monitoring-local.sh" in runtime_monitoring_script
    assert "/providers/runtime/monitoring/snapshot" in local_runtime_monitoring_script
    assert "/providers/runtime/monitoring/incidents" in local_runtime_monitoring_script
    assert "/providers/runtime/monitoring/incidents/retention" in (
        local_runtime_monitoring_script
    )
    assert "NUTMEG_PROVIDER_RUNTIME_INCIDENT_THRESHOLD" in (
        local_runtime_monitoring_script
    )
    assert "NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS" in (
        local_runtime_monitoring_script
    )
    assert "nutmeg-provider-runtime-monitoring" in runtime_monitoring_cron_script
    assert "provider-runtime-monitoring.log" in runtime_monitoring_cron_script
    assert "NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS" in (
        runtime_monitoring_cron_script
    )
    assert "NUTMEG_MAPPING_BOOTSTRAP_MAX_PROVIDER_EVENTS" in mapping_bootstrap_script
    assert "provider_fixture_source" in mapping_bootstrap_script
    assert "/providers/mappings/bootstrap/sportmonks-fixtures" in (
        sportmonks_mapping_bootstrap_script
    )
    assert "/providers/mappings/backfill/sportmonks-fixtures" in (
        sportmonks_mapping_bootstrap_script
    )
    assert "NUTMEG_SPORTMONKS_MAPPING_AUTO_DISCOVERY" in (
        sportmonks_mapping_bootstrap_script
    )
    assert "NUTMEG_SPORTMONKS_MAPPING_COMPETITION_ID" in (
        sportmonks_mapping_bootstrap_script
    )
    assert "sportmonks_mapping_bootstrap_ok" in sportmonks_mapping_bootstrap_script
    assert "/providers/sportmonks/discovery/competitions" in sportmonks_discovery_script
    assert "sportmonks_competition_discovery_ok" in sportmonks_discovery_script
    assert "sportmonks_mapping_env" in sportmonks_discovery_script
    assert "NUTMEG_SPORTMONKS_DISCOVERY_MIN_COMPETITION_SCORE" in (
        sportmonks_discovery_script
    )
    assert "/providers/api-football/discovery/competitions" in (
        api_football_discovery_script
    )
    assert "api_football_competition_discovery_ok" in api_football_discovery_script
    assert "api_football_mapping_env" in api_football_discovery_script
    assert "/providers/mappings/bootstrap/api-football-fixtures" in (
        api_football_mapping_bootstrap_script
    )
    assert "api_football_mapping_bootstrap_ok" in api_football_mapping_bootstrap_script
    assert "fixture_result_fallback_research_dry_run" in api
    assert "historicalDataAllowed" in api
    assert "redistributionAllowed" in api
    assert "termsUrl" in api
    assert "authorizationReviews" in api
    assert "Provider Terms Review" in page
    assert "ProviderAuthorizationReviewActions" in page
    assert "Record Terms Review" in authorization_review_component
    assert "terms_review_ack" in authorization_review_component
    assert "provider_ops_manual_terms_review" in authorization_review_component
    assert "recordProviderAuthorizationReviewAction" in provider_actions
    assert '"/providers/authorizations/reviews"' in provider_actions
    assert "providerAuthorizationReviewResponseSchema" in provider_actions
    assert "provider_ops_operator" in provider_actions
    assert "/providers/authorizations/reviews?limit=10" in api
    assert "/ops/provider-sync/approvals?limit=100" in api
    assert "lastReviewedAtUtc" in api
    assert "nextReviewDueAtUtc" in api
    assert "provider_sync_workflow_seed_review" in api
    assert "provider_authorization_reviews" in (
        ROOT / "db/migrations/0027_provider_authorization_reviews.sql"
    ).read_text(encoding="utf-8")
    assert "VPS EPL explicit-ID dry-run" in seed_migration
    assert "provider_sync_workflow_seed_review" in seed_migration
    assert 'href: "/providers"' in nav
    assert "providerOpsAuditEventListResponseSchema" in api_contract
    assert "providerRuntimeMonitoringResponseSchema" in api_contract
    assert "providerRuntimeAlertSeveritySchema" in api_contract
    assert "providerRuntimeIncidentReportListResponseSchema" in api_contract
    assert "providerRuntimeIncidentStatusUpdateResponseSchema" in api_contract
    assert "providerRuntimeIncidentStatusSchema" in api_contract
    assert "incident_status" in api_contract
    assert "provider_ops_audit_events" in audit_migration
    assert "operator_name" in audit_migration
    assert "metadata_json" in audit_migration
    assert "provider_runtime_snapshots" in runtime_monitoring_migration
    assert "latency_ms" in runtime_monitoring_migration
    assert "rate_limit_remaining" in runtime_monitoring_migration


def test_provider_ops_copy_keeps_compliance_boundary() -> None:
    page = (ROOT / "apps/web/app/providers/page.tsx").read_text(encoding="utf-8")
    runbook_component = (
        ROOT / "apps/web/components/providers/provider-ops-runbook.tsx"
    ).read_text(encoding="utf-8")
    mapped_odds_component = (
        ROOT / "apps/web/components/providers/provider-mapped-odds-actions.tsx"
    ).read_text(encoding="utf-8")
    authorization_review_component = (
        ROOT
        / "apps/web/components/providers/provider-authorization-review-actions.tsx"
    ).read_text(encoding="utf-8")
    runtime_incident_component = (
        ROOT / "apps/web/components/providers/provider-runtime-incident-actions.tsx"
    ).read_text(encoding="utf-8")
    access_component = (
        ROOT / "apps/web/components/providers/provider-ops-access-panel.tsx"
    ).read_text(encoding="utf-8")

    assert "不包含自动投注能力" in page
    for forbidden in ["保证盈利", "稳赚", "必胜", "sure win"]:
        assert forbidden not in page
        assert forbidden not in runbook_component
        assert forbidden not in mapped_odds_component
        assert forbidden not in authorization_review_component
        assert forbidden not in runtime_incident_component
        assert forbidden not in access_component
