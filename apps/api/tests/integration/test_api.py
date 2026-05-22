from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

import pytest
from fastapi.testclient import TestClient

from nutmeg import database as database_module
from nutmeg.accuracy.dixon_coles_job import DixonColesTrainingBacktestJobOptions
from nutmeg.accuracy.job_repository import AccuracyJobRunRecord
from nutmeg.accuracy.jobs import AccuracyJobResult
from nutmeg.accuracy.weekly_training import WeeklyDixonColesTrainingPipelineOptions
from nutmeg.api import contract as contract_module
from nutmeg.api import router as router_module
from nutmeg.config import Settings
from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.main import app
from nutmeg.parlay import (
    MarketPredictionParlayGenerationResult,
    ParlaySettlementRun,
    StoredParlayRecommendation,
)
from nutmeg.predictions.jobs import PredictionJobResult
from nutmeg.predictions.workflow import PrematchWorkflowResult, PrematchWorkflowRunRecord
from nutmeg.providers.api_football.discovery import (
    ApiFootballCompetitionDiscoveryCandidate,
    ApiFootballCompetitionDiscoveryResult,
    ApiFootballSeasonDiscoveryCandidate,
)
from nutmeg.providers.availability_coverage import FixtureAvailabilityCoverage
from nutmeg.providers.availability_repository import AvailabilitySnapshotWriteSummary
from nutmeg.providers.availability_sync import SportMonksFixtureAvailabilitySyncResult
from nutmeg.providers.canonical_repository import CanonicalFixtureWriteSummary
from nutmeg.providers.conflicts import (
    ProviderConflictEvaluationResult,
    ProviderConflictEventRecord,
    ProviderObservation,
)
from nutmeg.providers.fallback_odds_probe import SportMonksFallbackOddsProbeResult
from nutmeg.providers.fixture_mapping_bootstrap import (
    FixtureMappingBootstrapResult,
    FixtureMappingMatchCandidate,
)
from nutmeg.providers.football_data_org import normalize_match
from nutmeg.providers.governance.authorization_reviews import (
    ProviderAuthorizationReviewRecord,
)
from nutmeg.providers.governance.contracts import ProviderAuthorizationRecord
from nutmeg.providers.governance.onboarding import (
    CompetitionOnboardingAssessment,
    CompetitionOnboardingInput,
    assess_competition_onboarding,
)
from nutmeg.providers.governance.onboarding_repository import (
    StoredCompetitionOnboardingAssessment,
)
from nutmeg.providers.governance.run_history import ProviderOpsRunHistoryRecord
from nutmeg.providers.mapped_odds_sync import TheOddsApiMappedEventOddsSyncResult
from nutmeg.providers.mapping_repository import (
    ProviderEntityMappingList,
    ProviderEntityMappingRecord,
    ProviderEntityMappingSummary,
)
from nutmeg.providers.mapping_review import (
    ProviderMappingReviewResult,
    ProviderMappingReviewRunRecord,
)
from nutmeg.providers.odds_coverage import (
    CompetitionOddsCoverageReport,
    FixtureOddsCoverage,
    OddsCoverageComponentPatch,
    OddsCoverageFallbackProviderCandidate,
    OddsCoverageGapItem,
    OddsCoverageGapReport,
)
from nutmeg.providers.odds_repository import OddsSnapshotWriteSummary
from nutmeg.providers.odds_sync import TheOddsApiEventOddsSyncResult
from nutmeg.providers.repository import ProviderSyncRunRecord, StoredRawProviderPayload
from nutmeg.providers.runtime_monitoring import (
    ProviderRuntimeIncidentReportRecord,
    ProviderRuntimeIncidentSummary,
    ProviderRuntimeIncidentTrendBucket,
    ProviderRuntimeSnapshotRecord,
)
from nutmeg.providers.sportmonks import normalize_injuries, normalize_lineups
from nutmeg.providers.sportmonks.discovery import (
    SportMonksCompetitionDiscoveryCandidate,
    SportMonksCompetitionDiscoveryResult,
    SportMonksSeasonDiscoveryCandidate,
)
from nutmeg.providers.sportmonks_mapping_backfill import (
    SportMonksFixtureMappingBackfillResult,
)
from nutmeg.providers.sync import FootballDataFixtureSyncResult
from nutmeg.providers.the_odds_api import normalize_event_odds
from nutmeg.providers.workflow import ProviderSyncWorkflowResult, ProviderSyncWorkflowRunRecord
from nutmeg.providers.workflow_approvals import ProviderSyncWorkflowApprovalRecord
from nutmeg.providers.workflow_templates import ProviderSyncWorkflowTemplateRecord
from nutmeg.recommendations import (
    PersistedRecommendationLifecycleReplayResult,
    RecommendationCandidate,
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationCoreReplayOptions,
    RecommendationCoreReplayReport,
    RecommendationCoreReplayRunResult,
    RecommendationEvaluationOptions,
    RecommendationEvaluationRunResult,
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    RecommendationGlobalPlannerOptions,
    RecommendationGlobalPlannerResult,
    RecommendationGlobalPlanOption,
    RecommendationLifecycleDetail,
    RecommendationLifecycleEventRecord,
    RecommendationLifecycleMutationResult,
    RecommendationLockedLegRecord,
    RecommendationPrematchChangeReport,
    RecommendationPrematchChangeReportOptions,
    RecommendationPrematchChangeReportRunResult,
    RecommendationPrematchPipelineOptions,
    RecommendationPrematchPipelineRunResult,
    RecommendationProviderIncidentEventInput,
    RecommendationProviderIncidentMappingOptions,
    RecommendationProviderIncidentMappingResult,
    RecommendationRecomputeTriggerOptions,
    RecommendationRecomputeTriggerRunResult,
    RecommendationRunLifecycleRecord,
    RecommendationSelection,
    RecommendationSourceStatusSyncOptions,
    RecommendationSourceStatusSyncRunResult,
    RecommendationStrategy,
    RecommendationStrategyEvidence,
    RecommendationStrategyPromotionReview,
    RecommendationStrategyReviewArtifact,
    RecommendationStrategyReviewOptions,
    RecommendationStrategyReviewRunResult,
    RecommendationStrategyRollbackPlan,
    RecommendationSuccessorRecomputeOptions,
    RecommendationSuccessorRecomputeRunResult,
    ScoredRecommendationCandidate,
    StoredRecommendationBenchmarkRun,
    StoredRecommendationBenchmarkStrategyPairRun,
    StoredRecommendationRun,
)
from nutmeg.recommendations.lifecycle_replay import (
    PersistedRecommendationLifecycleReplayStage,
)

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nutmeg-api"}


def test_provider_status_endpoint_returns_authorization_and_governance_gates() -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    providers = {provider["provider_name"]: provider for provider in payload["providers"]}
    assert providers["mock-local"]["status"] == "active"
    assert providers["mock-local"]["commercial_use_allowed"] is True
    assert providers["football-data.org"]["api_key_env_var"] == "FOOTBALL_DATA_API_KEY"
    assert "api_key" not in providers["football-data.org"]
    assert providers["the-odds-api"]["capabilities"] == ["odds"]
    assert providers["the-odds-api"]["api_key_env_var"] == "THE_ODDS_API_KEY"
    assert "lineups" in providers["sportmonks"]["capabilities"]
    assert "injuries" in providers["sportmonks"]["capabilities"]
    assert providers["sportmonks"]["api_key_env_var"] == "SPORTMONKS_API_KEY"
    assert providers["api-football"]["api_key_env_var"] == "API_FOOTBALL_API_KEY"
    assert providers["api-football"]["allowed_use"] == ("fixture_result_fallback_research_dry_run")
    assert providers["api-football"]["terms_url"] == "https://www.api-football.com/terms"
    assert providers["api-football"]["historical_data_allowed"] is False
    assert providers["api-football"]["redistribution_allowed"] is False
    assert providers["api-football"]["last_reviewed_at"] == "2026-05-08T00:00:00Z"
    assert providers["api-football"]["next_review_due_at"] == "2026-11-04T00:00:00Z"
    assert providers["api-football"]["owner"] == "nutmeg-ops"

    readiness = payload["competition_readiness"]
    assert readiness[0]["competition_id"] == "EPL"
    assert readiness[0]["decision"] == "beta_ready"
    assert readiness[1]["competition_id"] == "JPN_J1"
    assert readiness[1]["decision"] == "not_ready"
    assert readiness[1]["data_quality"]["parlay_eligible"] is True

    promotion = payload["model_promotion_review"]
    assert promotion["candidate_model_version"] == "poisson-m1.1.0"
    assert promotion["baseline_model_version"] == "poisson-m1.0.0"
    assert promotion["decision"] == "shadow_candidate"
    assert promotion["next_status"] == "shadow"
    assert payload["rollback_plan"]["should_rollback"] is False
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_runtime_credentials_endpoint_reports_modes_without_secret_values() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        admin_api_token="secret",
        provider_sync_mock_dry_run_enabled=True,
        football_data_api_key="football-secret",
    )
    try:
        response = client.get(
            "/api/v1/providers/runtime/credentials",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert "football-secret" not in str(payload)
    assert payload["mock_dry_run_enabled"] is True
    records = {item["provider_name"]: item for item in payload["items"]}
    assert records["mock-local"]["dry_run_mode"] == "local_only"
    assert records["football-data.org"]["runtime_env_var"] == ("NUTMEG_FOOTBALL_DATA_API_KEY")
    assert records["football-data.org"]["key_configured"] is True
    assert records["football-data.org"]["dry_run_mode"] == "real_provider"
    assert records["football-data.org"]["commit_mode"] == "ready"
    assert records["the-odds-api"]["key_configured"] is False
    assert records["the-odds-api"]["dry_run_mode"] == "mock_sample"
    assert records["the-odds-api"]["commit_mode"] == "blocked"
    assert records["sportmonks"]["next_action"] == "apply_api_key_before_real_provider_sync"


def test_provider_runtime_credentials_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.get("/api/v1/providers/runtime/credentials")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_api_key_checklist_endpoint_guides_free_key_setup_without_secrets() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        admin_api_token="secret",
        football_data_api_key="football-secret",
        api_football_api_key="api-football-secret",
    )
    try:
        response = client.get(
            "/api/v1/providers/runtime/api-key-checklist",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert "football-secret" not in str(payload)
    assert "api-football-secret" not in str(payload)
    items = {item["provider_name"]: item for item in payload["items"]}
    assert items["football-data.org"]["adapter_status"] == "supported_now"
    assert items["football-data.org"]["key_configured"] is True
    assert items["football-data.org"]["free_tier_fit"] == "good_for_first_dry_run"
    assert items["api-football"]["adapter_status"] == "supported_now"
    assert items["api-football"]["required_env_var"] == "NUTMEG_API_FOOTBALL_API_KEY"
    assert items["api-football"]["key_configured"] is True
    assert items["sportmonks"]["free_tier_fit"] == "trial_required"
    assert items["the-odds-api"]["free_tier_fit"] == "limited_for_soccer"


def test_provider_runtime_probes_endpoint_checks_key_presence_without_live_calls() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        admin_api_token="secret",
        football_data_api_key="football-secret",
        the_odds_api_key="odds-secret",
        sportmonks_api_key="sportmonks-secret",
        api_football_api_key="api-football-secret",
    )
    try:
        response = client.get(
            "/api/v1/providers/runtime/probes",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert "football-secret" not in str(payload)
    assert "odds-secret" not in str(payload)
    assert "sportmonks-secret" not in str(payload)
    assert "api-football-secret" not in str(payload)
    assert payload["live_probe"] is False
    items = {item["provider_name"]: item for item in payload["items"]}
    assert items["football-data.org"]["status"] == "key_configured"
    assert items["the-odds-api"]["status"] == "key_configured"
    assert items["sportmonks"]["status"] == "key_configured"
    assert items["api-football"]["status"] == "key_configured"


def test_provider_runtime_probes_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.get("/api/v1/providers/runtime/probes")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_ops_run_history_endpoint_records_sanitized_helper_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    class FakeProviderOpsRunHistoryRepository:
        def record_run(self, run) -> ProviderOpsRunHistoryRecord:
            calls.append(
                {
                    "method": "record",
                    "run_name": run.run_name,
                    "operator_name": run.operator_name,
                    "summary_json": run.summary_json,
                    "output_excerpt": run.output_excerpt,
                }
            )
            return ProviderOpsRunHistoryRecord(
                provider_ops_run_id=42,
                run_name=run.run_name,
                run_type=run.run_type,
                source=run.source,
                status=run.status,
                operator_name=run.operator_name,
                started_at=run.started_at,
                completed_at=run.completed_at,
                duration_ms=run.duration_ms,
                exit_code=run.exit_code,
                summary_json=run.summary_json,
                output_excerpt=run.output_excerpt,
                metadata_json=run.metadata_json,
                created_at=datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
            )

        def list_latest(self, *, limit: int) -> list[ProviderOpsRunHistoryRecord]:
            calls.append({"method": "list", "limit": limit})
            return [
                ProviderOpsRunHistoryRecord(
                    provider_ops_run_id=42,
                    run_name="provider-sync-dry-run",
                    run_type="vps_helper",
                    source="vps",
                    status="success",
                    operator_name="nutmeg-vps-helper",
                    duration_ms=1200,
                    exit_code=0,
                    summary_json={"mode": "real_provider_fixture_probe"},
                    output_excerpt="provider_sync_dry_run_ok",
                    metadata_json={"secret_value_not_exposed": True},
                    created_at=datetime(2026, 5, 9, 1, 1, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_ops_run_history_repository",
        lambda settings: FakeProviderOpsRunHistoryRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        record_response = client.post(
            "/api/v1/ops/provider-runs",
            headers={
                "X-Nutmeg-Admin-Token": "secret",
                "X-Nutmeg-Operator": "nutmeg-vps-helper",
            },
            json={
                "run_name": "provider-runtime-monitoring",
                "run_type": "cron",
                "source": "vps",
                "status": "success",
                "duration_ms": 1200,
                "exit_code": 0,
                "summary_json": {
                    "alert_level": "ok",
                    "api_key": "should-not-be-returned",
                },
                "output_excerpt": "provider_runtime_monitoring_alert_level ok token=bad",
                "metadata_json": {"secret_value_not_exposed": True},
            },
        )
        list_response = client.get(
            "/api/v1/ops/provider-runs?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert record_response.status_code == 200
    assert list_response.status_code == 200
    payload = record_response.json()
    assert payload["item"]["summary_json"]["api_key"] == "[redacted]"
    assert payload["item"]["output_excerpt"] == "[redacted: sensitive output omitted]"
    assert list_response.json()["items"][0]["run_name"] == "provider-sync-dry-run"
    assert "should-not-be-returned" not in str(payload)
    assert "token=bad" not in str(payload)
    assert [call["method"] for call in calls] == ["record", "list"]


def test_provider_runtime_incident_status_endpoint_updates_admin_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    class FakeProviderRuntimeMonitoringRepository:
        def update_incident_status(
            self,
            *,
            provider_runtime_incident_report_id: int,
            incident_status: str,
            updated_by: str,
            resolution_note: str | None = None,
        ) -> ProviderRuntimeIncidentReportRecord:
            calls.append(
                {
                    "provider_runtime_incident_report_id": (provider_runtime_incident_report_id),
                    "incident_status": incident_status,
                    "updated_by": updated_by,
                    "resolution_note": resolution_note,
                }
            )
            return ProviderRuntimeIncidentReportRecord(
                provider_runtime_incident_report_id=provider_runtime_incident_report_id,
                alert_level="P1",
                alert_count=2,
                snapshot_count=4,
                summary_json={"provider_count": 4},
                alerts_json=[{"alert_id": "provider_fallback_usage_high"}],
                thresholds_json={"fallback_usage_rate_p1": 0.5},
                source="vps_cron",
                created_by="provider-runtime-monitor",
                metadata_json={"redacted": True},
                incident_status="resolved",
                acknowledged_by="ops-reviewer",
                acknowledged_at=datetime(2026, 5, 9, 5, 0, tzinfo=UTC),
                resolved_by="ops-reviewer",
                resolved_at=datetime(2026, 5, 9, 5, 1, tzinfo=UTC),
                resolution_note="Provider recovered after plan review.",
                notification_status="not_configured",
                notification_payload_json={"destination": "provider_ops"},
                updated_at=datetime(2026, 5, 9, 5, 1, tzinfo=UTC),
                created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_runtime_monitoring_repository",
        lambda settings: FakeProviderRuntimeMonitoringRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.patch(
            "/api/v1/providers/runtime/monitoring/incidents/77/status",
            headers={
                "X-Nutmeg-Admin-Token": "secret",
                "X-Nutmeg-Operator": "ops-reviewer",
            },
            json={
                "incident_status": "resolved",
                "resolution_note": "Provider recovered after plan review.",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "provider_runtime_incident_report_id": 77,
            "incident_status": "resolved",
            "updated_by": "ops-reviewer",
            "resolution_note": "Provider recovered after plan review.",
        }
    ]
    assert payload["item"]["incident_status"] == "resolved"
    assert payload["item"]["resolved_by"] == "ops-reviewer"
    assert payload["item"]["notification_status"] == "not_configured"
    assert "secret" not in str(payload).lower()


def test_provider_runtime_incident_record_endpoint_writes_notification_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    class FakeProviderRuntimeMonitoringRepository:
        def list_latest_by_provider(
            self,
            *,
            limit: int,
        ) -> list[ProviderRuntimeSnapshotRecord]:
            calls.append({"method": "latest", "limit": limit})
            return [
                ProviderRuntimeSnapshotRecord(
                    provider_runtime_snapshot_id=42,
                    provider_name="the-odds-api",
                    capability="odds",
                    probe_status="rate_limited",
                    key_configured=True,
                    live_probe=False,
                    safe_to_call_real_provider=False,
                    latency_ms=5200,
                    error_rate=1.0,
                    success_count=0,
                    failure_count=1,
                    rate_limit_remaining=0,
                    quota_window=None,
                    fallback_used=True,
                    message="Provider returned a rate limit response.",
                    next_action="review_provider_plan_limit",
                    metadata_json={"secret_value_not_exposed": True},
                    observed_at=datetime(2026, 5, 9, 3, 0, tzinfo=UTC),
                )
            ]

        def record_incident_report(self, report):
            calls.append(
                {
                    "method": "record",
                    "alert_level": report.alert_level,
                    "created_by": report.created_by,
                    "source": report.source,
                }
            )
            return ProviderRuntimeIncidentReportRecord(
                provider_runtime_incident_report_id=77,
                alert_level=report.alert_level,
                alert_count=report.alert_count,
                snapshot_count=report.snapshot_count,
                summary_json=report.summary_json,
                alerts_json=report.alerts_json,
                thresholds_json=report.thresholds_json,
                source=report.source,
                created_by=report.created_by,
                metadata_json=report.metadata_json,
                incident_status="open",
                notification_status="not_configured",
                notification_payload_json={},
                created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
            )

        def update_incident_notification(
            self,
            *,
            provider_runtime_incident_report_id: int,
            notification_status: str,
            notification_payload_json: dict[str, object],
        ) -> ProviderRuntimeIncidentReportRecord:
            calls.append(
                {
                    "method": "notification",
                    "provider_runtime_incident_report_id": (provider_runtime_incident_report_id),
                    "notification_status": notification_status,
                    "notification_payload_json": notification_payload_json,
                }
            )
            return ProviderRuntimeIncidentReportRecord(
                provider_runtime_incident_report_id=provider_runtime_incident_report_id,
                alert_level="P1",
                alert_count=2,
                snapshot_count=1,
                summary_json={"provider_count": 1, "degraded_count": 1},
                alerts_json=[{"alert_id": "the-odds-api_provider_error_rate"}],
                thresholds_json={"provider_error_rate_p1": 1.0},
                source="vps_cron",
                created_by="ops-reviewer",
                metadata_json={"secret_value_not_exposed": True},
                incident_status="open",
                notification_status=notification_status,
                notification_payload_json=notification_payload_json,
                created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_runtime_monitoring_repository",
        lambda settings: FakeProviderRuntimeMonitoringRepository(),
    )
    app.state.settings = Settings(
        admin_api_token="secret",
        provider_runtime_incident_notification_enabled=True,
        provider_runtime_incident_notification_dry_run=False,
    )
    try:
        response = client.post(
            "/api/v1/providers/runtime/monitoring/incidents",
            headers={
                "X-Nutmeg-Admin-Token": "secret",
                "X-Nutmeg-Operator": "ops-reviewer",
            },
            json={
                "source": "vps_cron",
                "created_by": "ops-reviewer",
                "record_when_alert_level": "P2",
                "metadata_json": {"secret_value_not_exposed": True},
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    notification_call = calls[2]
    assert [call["method"] for call in calls] == ["latest", "record", "notification"]
    assert notification_call["notification_status"] == "sent"
    assert payload["recorded"] is True
    assert payload["item"]["notification_status"] == "sent"
    assert payload["item"]["notification_payload_json"]["adapter"] == "provider_ops"
    assert (
        payload["item"]["notification_payload_json"]["reason"]
        == "provider_ops_internal_notification_recorded"
    )
    assert payload["item"]["notification_payload_json"]["external_delivery"] is False
    assert "webhook_url" not in str(payload).lower()
    assert "secret" not in str(payload).lower().replace("secret_value_not_exposed", "")


def test_provider_runtime_incident_list_endpoint_returns_summary_and_trend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    class FakeProviderRuntimeMonitoringRepository:
        def list_incident_reports(
            self,
            *,
            limit: int,
            offset: int,
            incident_status: str | None = None,
            alert_level: str | None = None,
            notification_status: str | None = None,
            source: str | None = None,
        ) -> list[ProviderRuntimeIncidentReportRecord]:
            calls.append(
                {
                    "method": "list",
                    "limit": limit,
                    "offset": offset,
                    "incident_status": incident_status,
                    "alert_level": alert_level,
                    "notification_status": notification_status,
                    "source": source,
                }
            )
            return [
                ProviderRuntimeIncidentReportRecord(
                    provider_runtime_incident_report_id=77,
                    alert_level="P1",
                    alert_count=2,
                    snapshot_count=4,
                    summary_json={"provider_count": 4},
                    alerts_json=[{"alert_id": "provider_fallback_usage_high"}],
                    thresholds_json={"fallback_usage_rate_p1": 0.5},
                    source="vps_cron",
                    created_by="provider-runtime-monitor",
                    metadata_json={"redacted": True},
                    incident_status="open",
                    notification_status="not_configured",
                    notification_payload_json={"destination": "provider_ops"},
                    created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
                )
            ]

        def count_incident_reports(
            self,
            *,
            incident_status: str | None = None,
            alert_level: str | None = None,
            notification_status: str | None = None,
            source: str | None = None,
        ) -> int:
            calls.append(
                {
                    "method": "count",
                    "incident_status": incident_status,
                    "alert_level": alert_level,
                    "notification_status": notification_status,
                    "source": source,
                }
            )
            return 3

        def summarize_incident_reports(
            self,
            *,
            lookback_days: int,
        ) -> ProviderRuntimeIncidentSummary:
            calls.append({"method": "summary", "lookback_days": lookback_days})
            return ProviderRuntimeIncidentSummary(
                lookback_days=lookback_days,
                total_count=3,
                open_count=1,
                acknowledged_count=1,
                resolved_count=1,
                ignored_count=0,
                active_count=2,
                p0_count=0,
                p1_count=2,
                p2_count=1,
                notification_failed_count=0,
                latest_created_at=datetime(2026, 5, 9, 3, 30, tzinfo=UTC),
                mean_time_to_resolve_minutes=12.5,
                trend_buckets=[
                    ProviderRuntimeIncidentTrendBucket(
                        bucket_date="2026-05-09",
                        total_count=3,
                        open_count=1,
                        acknowledged_count=1,
                        resolved_count=1,
                        ignored_count=0,
                        active_count=2,
                        p0_count=0,
                        p1_count=2,
                        p2_count=1,
                        notification_failed_count=0,
                    )
                ],
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_runtime_monitoring_repository",
        lambda settings: FakeProviderRuntimeMonitoringRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.get(
            "/api/v1/providers/runtime/monitoring/incidents"
            "?limit=5&offset=10&lookback_days=14&incident_status=open"
            "&alert_level=P1&notification_status=not_configured&source=vps_cron",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "method": "list",
            "limit": 5,
            "offset": 10,
            "incident_status": "open",
            "alert_level": "P1",
            "notification_status": "not_configured",
            "source": "vps_cron",
        },
        {
            "method": "count",
            "incident_status": "open",
            "alert_level": "P1",
            "notification_status": "not_configured",
            "source": "vps_cron",
        },
        {"method": "summary", "lookback_days": 14},
    ]
    assert payload["items"][0]["incident_status"] == "open"
    assert payload["summary"]["lookback_days"] == 14
    assert payload["summary"]["active_count"] == 2
    assert payload["summary"]["trend_buckets"][0]["bucket_date"] == "2026-05-09"
    assert payload["limit"] == 5
    assert payload["offset"] == 10
    assert payload["total_count"] == 3
    assert payload["has_more"] is False
    assert "secret" not in str(payload).lower()


def test_api_football_competition_discovery_endpoint_returns_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        admin_api_token="secret",
        api_football_api_key="secret-key",
    )
    calls: list[dict[str, object]] = []

    def fake_discovery(
        settings: Settings,
        **kwargs: object,
    ) -> ApiFootballCompetitionDiscoveryResult:
        calls.append(kwargs)
        season = ApiFootballSeasonDiscoveryCandidate(
            provider_season_id="2025",
            year=2025,
            score=1.0,
            current=True,
            start="2025-08-15",
            end="2026-05-24",
        )
        competition = ApiFootballCompetitionDiscoveryCandidate(
            provider_competition_id="39",
            name="Premier League",
            country_name="England",
            competition_type="League",
            score=1.0,
            seasons=[season],
            recommended_season=season,
        )
        return ApiFootballCompetitionDiscoveryResult(
            target_competition_name=str(kwargs["target_competition_name"]),
            target_country_name=str(kwargs["target_country_name"]),
            target_season=str(kwargs["target_season"]),
            min_competition_score=float(kwargs["min_competition_score"]),
            checked_competition_count=1,
            candidate_count=1,
            recommended_competition=competition,
            recommended_season=season,
            candidates=[competition],
            generated_at_utc=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "discover_api_football_competition_season",
        fake_discovery,
    )

    try:
        response = client.post(
            "/api/v1/providers/api-football/discovery/competitions",
            json={
                "target_competition_name": "Premier League",
                "target_country_name": "England",
                "target_season": "2025",
                "max_competition_candidates": 5,
                "max_season_candidates": 6,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "target_competition_name": "Premier League",
            "target_country_name": "England",
            "target_season": "2025",
            "max_competition_candidates": 5,
            "max_season_candidates": 6,
            "min_competition_score": 0.75,
        }
    ]
    assert payload["result"]["provider_name"] == "api-football"
    assert payload["result"]["recommended_competition"]["provider_competition_id"] == "39"
    assert payload["result"]["recommended_season"]["provider_season_id"] == "2025"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_sportmonks_competition_discovery_endpoint_returns_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", sportmonks_api_key="secret-key")
    calls: list[dict[str, object]] = []

    def fake_discovery(
        settings: Settings,
        **kwargs: object,
    ) -> SportMonksCompetitionDiscoveryResult:
        calls.append(kwargs)
        season = SportMonksSeasonDiscoveryCandidate(
            provider_season_id="23690",
            name="2025/2026",
            score=0.98,
            is_current=True,
            finished=False,
            starting_at="2025-08-15",
            ending_at="2026-05-24",
        )
        competition = SportMonksCompetitionDiscoveryCandidate(
            provider_competition_id="8",
            name="Premier League",
            country_name="England",
            competition_type="domestic",
            active=True,
            score=1.0,
            seasons=[season],
            recommended_season=season,
        )
        return SportMonksCompetitionDiscoveryResult(
            target_competition_name=str(kwargs["target_competition_name"]),
            target_country_name=str(kwargs["target_country_name"]),
            target_season=str(kwargs["target_season"]),
            min_competition_score=float(kwargs["min_competition_score"]),
            checked_competition_count=1200,
            candidate_count=1,
            recommended_competition=competition,
            recommended_season=season,
            candidates=[competition],
            generated_at_utc=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "discover_sportmonks_competition_season",
        fake_discovery,
    )

    try:
        response = client.post(
            "/api/v1/providers/sportmonks/discovery/competitions",
            json={
                "target_competition_name": "Premier League",
                "target_country_name": "England",
                "target_season": "2025",
                "min_competition_score": 0.75,
                "max_competition_candidates": 5,
                "max_season_candidates": 6,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "target_competition_name": "Premier League",
            "target_country_name": "England",
            "target_season": "2025",
            "max_competition_candidates": 5,
            "max_season_candidates": 6,
            "min_competition_score": 0.75,
        }
    ]
    assert payload["result"]["provider_name"] == "sportmonks"
    assert payload["result"]["recommended_competition"]["provider_competition_id"] == "8"
    assert payload["result"]["recommended_season"]["provider_season_id"] == "23690"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_sportmonks_competition_discovery_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/sportmonks/discovery/competitions",
            json={},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_status_endpoint_merges_persisted_competition_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_governance_repository="postgres")
    persisted_assessment = assess_competition_onboarding(
        CompetitionOnboardingInput(
            competition_id="EPL",
            competition_name="Premier League",
            target_stage="beta",
            schedule_coverage=0.99,
            result_coverage=0.995,
            odds_coverage=0.0,
            handicap_coverage=0.0,
            lineup_injury_coverage=0.70,
            historical_stats_completeness=0.82,
            provider_consistency=0.93,
            data_freshness=0.0,
            historical_sample_size=420,
            complete_seasons=1,
            market_resolver_tests_passed=True,
            score_grid_generation_passed=True,
        )
    )

    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None = None,
            limit: int = 50,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            assert competition_id is None
            assert limit == 100
            return [
                StoredCompetitionOnboardingAssessment(
                    assessment_id=1,
                    created_at_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
                    assessment=persisted_assessment,
                )
            ]

    class FakeAuthorizationRepository:
        def list_authorizations(self) -> list[ProviderAuthorizationRecord]:
            return [
                ProviderAuthorizationRecord(
                    provider_name="api-football",
                    status="pending_review",
                    capabilities=("competitions", "seasons", "fixtures", "results"),
                    terms_checked_at_utc=datetime(2026, 5, 8, tzinfo=UTC),
                    allowed_use="fixture_result_fallback_research_dry_run",
                    rate_limit="free_plan_provider_defined",
                    terms_url="https://www.api-football.com/terms",
                    api_key_env_var="API_FOOTBALL_API_KEY",
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_provider_authorization_repository",
        lambda settings: FakeAuthorizationRepository(),
    )

    try:
        response = client.get("/api/v1/providers/status")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    readiness = {
        (item["competition_id"], item["target_stage"]): item
        for item in payload["competition_readiness"]
    }
    assert readiness[("EPL", "beta")]["decision"] == "not_ready"
    assert readiness[("EPL", "beta")]["data_quality"]["components"]["odds_coverage"] == 0.0
    assert readiness[("EPL", "production")]["target_stage"] == "production"
    assert payload["providers"][0]["provider_name"] == "api-football"
    assert payload["providers"][0]["allowed_use"] == ("fixture_result_fallback_research_dry_run")
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_authorization_reviews_endpoint_lists_recent_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakeProviderAuthorizationReviewRepository:
        def list_latest(self, *, limit: int) -> list[ProviderAuthorizationReviewRecord]:
            calls.append(limit)
            return [_provider_authorization_review_record()]

    monkeypatch.setattr(
        router_module,
        "_build_provider_authorization_review_repository",
        lambda settings: FakeProviderAuthorizationReviewRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.get(
            "/api/v1/providers/authorizations/reviews?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    assert calls == [5]
    payload = response.json()
    assert payload["items"][0]["provider_name"] == "api-football"
    assert payload["items"][0]["review_status"] == "research_only"
    assert payload["items"][0]["terms_url"] == "https://www.api-football.com/terms"
    assert payload["items"][0]["evidence_json"] == {"source": "unit_test"}


def test_provider_authorization_reviews_endpoint_records_admin_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    recorded_payloads: list[object] = []

    class FakeProviderAuthorizationReviewRepository:
        def record_review(self, review: object) -> ProviderAuthorizationReviewRecord:
            recorded_payloads.append(review)
            return _provider_authorization_review_record()

    monkeypatch.setattr(
        router_module,
        "_build_provider_authorization_review_repository",
        lambda settings: FakeProviderAuthorizationReviewRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/authorizations/reviews",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "provider_name": "api-football",
                "review_reference": "manual-2026-05-08",
                "review_status": "research_only",
                "reviewed_by": "ops-reviewer",
                "terms_url": "https://www.api-football.com/terms",
                "allowed_use": "fixture_result_fallback_research_dry_run",
                "rate_limit": "free_plan_provider_defined",
                "next_review_due_at_utc": "2026-11-04T00:00:00Z",
                "evidence_json": {"source": "manual_terms_review"},
                "notes": "Free plan review recorded without storing secret values.",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    assert len(recorded_payloads) == 1
    recorded = recorded_payloads[0]
    assert recorded.provider_name == "api-football"
    assert recorded.review_status == "research_only"
    assert recorded.owner == "nutmeg-ops"
    assert "secret" not in str(response.json()).lower()


def test_provider_authorization_reviews_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.get("/api/v1/providers/authorizations/reviews")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_mappings_endpoint_returns_filtered_mapping_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeProviderMappingRepository:
        def list_mappings(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 100,
        ) -> ProviderEntityMappingList:
            calls.append(
                {
                    "provider": provider,
                    "entity_type": entity_type,
                    "canonical_entity_id": canonical_entity_id,
                    "limit": limit,
                }
            )
            return ProviderEntityMappingList(
                items=[
                    ProviderEntityMappingRecord(
                        mapping_id=101,
                        provider="football-data.org",
                        entity_type="fixture",
                        provider_entity_id="330299",
                        canonical_entity_id="fd_fixture_330299",
                        confidence=1.0,
                        created_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                        updated_at_utc=datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                    )
                ],
                summary=[
                    ProviderEntityMappingSummary(
                        provider="football-data.org",
                        entity_type="fixture",
                        mapping_count=1,
                        average_confidence=1.0,
                        minimum_confidence=1.0,
                        latest_updated_at_utc=datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                    )
                ],
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )

    response = client.get(
        "/api/v1/providers/mappings"
        "?provider=football-data.org&entity_type=fixture"
        "&canonical_entity_id=fd_fixture_330299&limit=25"
    )

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "provider": "football-data.org",
            "entity_type": "fixture",
            "canonical_entity_id": "fd_fixture_330299",
            "limit": 25,
        }
    ]
    assert payload["items"][0]["mapping_id"] == 101
    assert payload["items"][0]["provider_entity_id"] == "330299"
    assert payload["summary"][0]["mapping_count"] == 1
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_mapping_bootstrap_endpoint_returns_match_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", provider_sync_enabled=True)
    calls: list[dict[str, object]] = []

    def fake_bootstrap(settings: Settings, **kwargs: object) -> FixtureMappingBootstrapResult:
        calls.append(kwargs)
        return FixtureMappingBootstrapResult(
            provider_name="the-odds-api",
            dry_run=bool(kwargs["dry_run"]),
            source_provider="football-data.org",
            source_competition_id=str(kwargs["provider_competition_id"]),
            canonical_competition_id=str(kwargs["canonical_competition_id"]),
            source_season=str(kwargs["season"]),
            provider_sport_key=str(kwargs["sport_key"]),
            source_fixture_count=380,
            provider_fixture_count=19,
            matched_count=1,
            persisted_count=0,
            ambiguous_count=0,
            unmatched_provider_fixture_count=18,
            min_confidence=float(kwargs["min_confidence"]),
            kickoff_tolerance_minutes=int(kwargs["kickoff_tolerance_minutes"]),
            matches=[
                FixtureMappingMatchCandidate(
                    provider_name="the-odds-api",
                    provider_fixture_id="event-1",
                    canonical_fixture_id="fd_fixture_330299",
                    confidence=0.99,
                    home_team_score=1.0,
                    away_team_score=1.0,
                    time_delta_minutes=0.0,
                    reasons=["kickoff_exact_or_near_exact"],
                )
            ],
            generated_at_utc=datetime(2026, 5, 8, 3, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "run_the_odds_api_fixture_mapping_bootstrap",
        fake_bootstrap,
    )

    try:
        response = client.post(
            "/api/v1/providers/mappings/bootstrap/the-odds-api-fixtures",
            json={
                "dry_run": True,
                "provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "season": "2025",
                "sport_key": "soccer_epl",
                "regions": "eu",
                "markets": "h2h",
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls[0]["provider_competition_id"] == "PL"
    assert calls[0]["canonical_competition_id"] == "EPL"
    assert calls[0]["sport_key"] == "soccer_epl"
    assert calls[0]["dry_run"] is True
    assert payload["result"]["matched_count"] == 1
    assert payload["result"]["provider_fixture_source"] == "events"
    assert payload["result"]["matches"][0]["provider_fixture_id"] == "event-1"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_sportmonks_provider_mapping_bootstrap_endpoint_returns_match_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", provider_sync_enabled=True)
    calls: list[dict[str, object]] = []

    def fake_bootstrap(settings: Settings, **kwargs: object) -> FixtureMappingBootstrapResult:
        calls.append(kwargs)
        return FixtureMappingBootstrapResult(
            provider_name="sportmonks",
            dry_run=bool(kwargs["dry_run"]),
            source_provider="football-data.org",
            source_competition_id=str(kwargs["source_provider_competition_id"]),
            canonical_competition_id=str(kwargs["canonical_competition_id"]),
            source_season=str(kwargs["source_season"]),
            provider_sport_key=(
                f"sportmonks:{kwargs['sportmonks_competition_id']}:{kwargs['sportmonks_season']}"
            ),
            source_fixture_count=380,
            provider_fixture_count=380,
            provider_fixture_source="fixtures",
            matched_count=1,
            persisted_count=0,
            ambiguous_count=0,
            unmatched_provider_fixture_count=379,
            min_confidence=float(kwargs["min_confidence"]),
            kickoff_tolerance_minutes=int(kwargs["kickoff_tolerance_minutes"]),
            matches=[
                FixtureMappingMatchCandidate(
                    provider_name="sportmonks",
                    provider_fixture_id="sm-fixture-1",
                    canonical_fixture_id="fd_fixture_330299",
                    confidence=0.99,
                    home_team_score=1.0,
                    away_team_score=1.0,
                    time_delta_minutes=0.0,
                    reasons=["kickoff_exact_or_near_exact"],
                )
            ],
            generated_at_utc=datetime(2026, 5, 8, 3, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "run_sportmonks_fixture_mapping_bootstrap",
        fake_bootstrap,
    )

    try:
        response = client.post(
            "/api/v1/providers/mappings/bootstrap/sportmonks-fixtures",
            json={
                "dry_run": True,
                "source_provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "source_season": "2025",
                "sportmonks_competition_id": "8",
                "sportmonks_season": "23690",
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls[0]["source_provider_competition_id"] == "PL"
    assert calls[0]["canonical_competition_id"] == "EPL"
    assert calls[0]["sportmonks_competition_id"] == "8"
    assert calls[0]["sportmonks_season"] == "23690"
    assert calls[0]["dry_run"] is True
    assert payload["result"]["provider_name"] == "sportmonks"
    assert payload["result"]["matched_count"] == 1
    assert payload["result"]["provider_fixture_source"] == "fixtures"
    assert payload["result"]["matches"][0]["provider_fixture_id"] == "sm-fixture-1"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_sportmonks_provider_mapping_backfill_endpoint_discovers_then_bootstraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", provider_sync_enabled=True)
    calls: list[dict[str, object]] = []

    discovery_season = SportMonksSeasonDiscoveryCandidate(
        provider_season_id="23690",
        name="2025/2026",
        score=1.0,
    )
    discovery_competition = SportMonksCompetitionDiscoveryCandidate(
        provider_competition_id="8",
        name="Premier League",
        country_name="England",
        active=True,
        score=0.99,
        seasons=[discovery_season],
        recommended_season=discovery_season,
    )
    discovery = SportMonksCompetitionDiscoveryResult(
        target_competition_name="Premier League",
        target_country_name="England",
        target_season="2025",
        min_competition_score=0.75,
        checked_competition_count=1,
        candidate_count=1,
        recommended_competition=discovery_competition,
        recommended_season=discovery_season,
        candidates=[discovery_competition],
        generated_at_utc=datetime(2026, 5, 8, 3, 0, tzinfo=UTC),
    )
    bootstrap = FixtureMappingBootstrapResult(
        provider_name="sportmonks",
        dry_run=True,
        source_provider="football-data.org",
        source_competition_id="PL",
        canonical_competition_id="EPL",
        source_season="2025",
        provider_sport_key="sportmonks:8:23690",
        source_fixture_count=380,
        provider_fixture_count=380,
        provider_fixture_source="fixtures",
        matched_count=1,
        persisted_count=0,
        ambiguous_count=0,
        unmatched_provider_fixture_count=379,
        min_confidence=0.82,
        kickoff_tolerance_minutes=180,
        matches=[
            FixtureMappingMatchCandidate(
                provider_name="sportmonks",
                provider_fixture_id="sm-fixture-1",
                canonical_fixture_id="fd_fixture_330299",
                confidence=0.99,
                home_team_score=1.0,
                away_team_score=1.0,
                time_delta_minutes=0.0,
            )
        ],
        generated_at_utc=datetime(2026, 5, 8, 3, 1, tzinfo=UTC),
    )

    def fake_backfill(
        settings: Settings,
        **kwargs: object,
    ) -> SportMonksFixtureMappingBackfillResult:
        calls.append(kwargs)
        return SportMonksFixtureMappingBackfillResult(
            status="dry_run",
            dry_run=True,
            target_competition_name=str(kwargs["target_competition_name"]),
            target_country_name=str(kwargs["target_country_name"]),
            target_season=str(kwargs["target_season"]),
            source_provider_competition_id=str(kwargs["source_provider_competition_id"]),
            canonical_competition_id=str(kwargs["canonical_competition_id"]),
            source_season=str(kwargs["source_season"]),
            recommended_competition_id="8",
            recommended_season_id="23690",
            matched_count=1,
            persisted_count=0,
            ambiguous_count=0,
            provider_fixture_count=380,
            unmatched_canonical_fixture_count=379,
            discovery=discovery,
            bootstrap=bootstrap,
            generated_at_utc=datetime(2026, 5, 8, 3, 2, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "run_sportmonks_fixture_mapping_backfill",
        fake_backfill,
    )

    try:
        response = client.post(
            "/api/v1/providers/mappings/backfill/sportmonks-fixtures",
            json={
                "dry_run": True,
                "source_provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "source_season": "2025",
                "target_competition_name": "Premier League",
                "target_country_name": "England",
                "target_season": "2025",
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls[0]["source_provider_competition_id"] == "PL"
    assert calls[0]["target_competition_name"] == "Premier League"
    assert payload["result"]["status"] == "dry_run"
    assert payload["result"]["recommended_competition_id"] == "8"
    assert payload["result"]["bootstrap"]["matches"][0]["provider_fixture_id"] == ("sm-fixture-1")
    assert payload["fallback_used"] is False


def test_api_football_provider_mapping_bootstrap_endpoint_returns_match_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", provider_sync_enabled=True)
    calls: list[dict[str, object]] = []

    def fake_bootstrap(settings: Settings, **kwargs: object) -> FixtureMappingBootstrapResult:
        calls.append(kwargs)
        return FixtureMappingBootstrapResult(
            provider_name="api-football",
            dry_run=bool(kwargs["dry_run"]),
            source_provider="football-data.org",
            source_competition_id=str(kwargs["source_provider_competition_id"]),
            canonical_competition_id=str(kwargs["canonical_competition_id"]),
            source_season=str(kwargs["source_season"]),
            provider_sport_key=(
                f"api-football:{kwargs['api_football_league_id']}:{kwargs['api_football_season']}"
            ),
            source_fixture_count=380,
            provider_fixture_count=380,
            provider_fixture_source="fixtures",
            matched_count=1,
            persisted_count=0,
            ambiguous_count=0,
            unmatched_provider_fixture_count=379,
            min_confidence=float(kwargs["min_confidence"]),
            kickoff_tolerance_minutes=int(kwargs["kickoff_tolerance_minutes"]),
            matches=[
                FixtureMappingMatchCandidate(
                    provider_name="api-football",
                    provider_fixture_id="api-fixture-1",
                    canonical_fixture_id="fd_fixture_330299",
                    confidence=0.99,
                    home_team_score=1.0,
                    away_team_score=1.0,
                    time_delta_minutes=0.0,
                    reasons=["kickoff_exact_or_near_exact"],
                )
            ],
            generated_at_utc=datetime(2026, 5, 8, 3, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "run_api_football_fixture_mapping_bootstrap",
        fake_bootstrap,
    )

    try:
        response = client.post(
            "/api/v1/providers/mappings/bootstrap/api-football-fixtures",
            json={
                "dry_run": True,
                "source_provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "source_season": "2025",
                "api_football_league_id": "39",
                "api_football_season": "2025",
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls[0]["source_provider_competition_id"] == "PL"
    assert calls[0]["canonical_competition_id"] == "EPL"
    assert calls[0]["api_football_league_id"] == "39"
    assert calls[0]["api_football_season"] == "2025"
    assert calls[0]["dry_run"] is True
    assert payload["result"]["provider_name"] == "api-football"
    assert payload["result"]["matched_count"] == 1
    assert payload["result"]["provider_fixture_source"] == "fixtures"
    assert payload["result"]["matches"][0]["provider_fixture_id"] == "api-fixture-1"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_mapping_bootstrap_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret", provider_sync_enabled=True)
    try:
        response = client.post(
            "/api/v1/providers/mappings/bootstrap/the-odds-api-fixtures",
            json={},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_mapping_review_endpoint_returns_dry_run_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeProviderMappingRepository:
        def list_review_candidates(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 1000,
        ) -> list[ProviderEntityMappingRecord]:
            calls.append(
                {
                    "provider": provider,
                    "entity_type": entity_type,
                    "canonical_entity_id": canonical_entity_id,
                    "limit": limit,
                }
            )
            return [
                ProviderEntityMappingRecord(
                    mapping_id=201,
                    provider="football-data.org",
                    entity_type="fixture",
                    provider_entity_id="provider-fixture-a",
                    canonical_entity_id="fix_a",
                    confidence=0.42,
                    created_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )

    response = client.post(
        "/api/v1/providers/mappings/review",
        json={
            "provider": "football-data.org",
            "entity_type": "fixture",
            "low_confidence_threshold": 0.95,
            "stale_after_days": 180,
            "as_of_time_utc": "2026-05-08T12:00:00Z",
            "limit": 25,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "provider": "football-data.org",
            "entity_type": "fixture",
            "canonical_entity_id": None,
            "limit": 25,
        }
    ]
    assert payload["result"]["dry_run"] is True
    assert payload["result"]["checked_mapping_count"] == 1
    assert payload["result"]["issue_count"] == 1
    assert payload["result"]["issues"][0]["issue_type"] == "low_confidence"
    assert payload["result"]["issues"][0]["severity"] == "critical"
    assert payload["stored_review"] is None
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_mapping_review_persist_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/mappings/review",
            json={"dry_run": False},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_mapping_review_endpoint_persists_audit_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    save_calls: list[dict[str, object]] = []

    class FakeProviderMappingRepository:
        def list_review_candidates(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 1000,
        ) -> list[ProviderEntityMappingRecord]:
            return [
                ProviderEntityMappingRecord(
                    mapping_id=202,
                    provider=provider or "football-data.org",
                    entity_type=entity_type or "fixture",
                    provider_entity_id="provider-fixture-b",
                    canonical_entity_id=canonical_entity_id or "fix_b",
                    confidence=0.44,
                    created_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                )
            ]

    class FakeProviderMappingReviewRunRepository:
        def save_review(
            self,
            *,
            result: ProviderMappingReviewResult,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            requested_by: str | None = None,
        ) -> ProviderMappingReviewRunRecord:
            save_calls.append(
                {
                    "provider": provider,
                    "entity_type": entity_type,
                    "canonical_entity_id": canonical_entity_id,
                    "requested_by": requested_by,
                }
            )
            return ProviderMappingReviewRunRecord(
                provider_mapping_review_run_id=401,
                provider=provider,
                entity_type=entity_type,
                canonical_entity_id=canonical_entity_id,
                low_confidence_threshold=0.95,
                stale_after_days=180,
                checked_mapping_count=1,
                issue_count=1,
                critical_count=1,
                warning_count=0,
                info_count=0,
                issues=result.issues,
                requested_by=requested_by,
                created_at_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_provider_mapping_review_run_repository",
        lambda settings: FakeProviderMappingReviewRunRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")

    try:
        response = client.post(
            "/api/v1/providers/mappings/review",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "provider": "football-data.org",
                "entity_type": "fixture",
                "canonical_entity_id": "fix_b",
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is False
    assert payload["stored_review"]["provider_mapping_review_run_id"] == 401
    assert payload["stored_review"]["requested_by"] == "admin_api"
    assert save_calls == [
        {
            "provider": "football-data.org",
            "entity_type": "fixture",
            "canonical_entity_id": "fix_b",
            "requested_by": "admin_api",
        }
    ]


def test_provider_mapping_review_latest_endpoint_returns_audit_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class FakeProviderMappingReviewRunRepository:
        def list_latest(self, *, limit: int = 10) -> list[ProviderMappingReviewRunRecord]:
            calls.append(limit)
            return [
                ProviderMappingReviewRunRecord(
                    provider_mapping_review_run_id=402,
                    provider="football-data.org",
                    entity_type="fixture",
                    canonical_entity_id=None,
                    low_confidence_threshold=0.95,
                    stale_after_days=180,
                    checked_mapping_count=3,
                    issue_count=0,
                    critical_count=0,
                    warning_count=0,
                    info_count=0,
                    issues=[],
                    requested_by="admin_api",
                    created_at_utc=datetime(2026, 5, 8, 2, 30, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_mapping_review_run_repository",
        lambda settings: FakeProviderMappingReviewRunRepository(),
    )

    response = client.get("/api/v1/providers/mappings/reviews/latest?limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert calls == [3]
    assert payload["items"][0]["provider_mapping_review_run_id"] == 402
    assert payload["items"][0]["checked_mapping_count"] == 3
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_conflict_evaluate_endpoint_returns_mapping_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProviderMappingRepository:
        def list_review_candidates(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 1000,
        ) -> list[ProviderEntityMappingRecord]:
            return [
                ProviderEntityMappingRecord(
                    mapping_id=301,
                    provider=provider or "football-data.org",
                    entity_type=entity_type or "fixture",
                    provider_entity_id="provider-fixture-a",
                    canonical_entity_id=canonical_entity_id or "fix_a",
                    confidence=0.41,
                    created_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )

    response = client.post(
        "/api/v1/providers/conflicts/evaluate",
        json={
            "provider": "football-data.org",
            "entity_type": "fixture",
            "as_of_time_utc": "2026-05-08T12:00:00Z",
            "include_observations": False,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is True
    assert payload["result"]["conflict_count"] == 1
    assert payload["result"]["data_quality_score_delta"] == -3.5
    assert payload["result"]["provider_consistency_after_conflicts"] == 0.65
    assert payload["result"]["events"][0]["trusted_provider"] == "football-data.org"
    assert payload["result"]["trusted_priorities"]
    assert payload["stored_events"] == []


def test_provider_conflict_evaluate_endpoint_includes_observation_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProviderMappingRepository:
        def list_review_candidates(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 1000,
        ) -> list[ProviderEntityMappingRecord]:
            return []

    class FakeProviderObservationRepository:
        def list_recent(
            self,
            *,
            as_of_time_utc: datetime,
            lookback_hours: int = 168,
            provider_name: str | None = None,
            capability: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 2000,
        ) -> list[ProviderObservation]:
            assert lookback_hours == 72
            assert provider_name is None
            assert capability == "fixtures"
            assert entity_type == "fixture"
            assert canonical_entity_id == "fix_a"
            return [
                ProviderObservation(
                    provider_name="football-data.org",
                    capability="fixtures",
                    entity_type="fixture",
                    canonical_entity_id="fix_a",
                    provider_entity_id="fd-a",
                    field_name="kickoff_time_utc",
                    value="2026-05-08T18:00:00Z",
                    observed_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                ),
                ProviderObservation(
                    provider_name="sportmonks",
                    capability="fixtures",
                    entity_type="fixture",
                    canonical_entity_id="fix_a",
                    provider_entity_id="sm-a",
                    field_name="kickoff_time_utc",
                    value="2026-05-08T19:00:00Z",
                    observed_at_utc=datetime(2026, 5, 8, 1, 5, tzinfo=UTC),
                ),
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_provider_observation_repository",
        lambda settings: FakeProviderObservationRepository(),
    )

    response = client.post(
        "/api/v1/providers/conflicts/evaluate",
        json={
            "entity_type": "fixture",
            "canonical_entity_id": "fix_a",
            "capability": "fixtures",
            "observation_lookback_hours": 72,
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["checked_issue_count"] == 2
    assert payload["result"]["conflict_count"] == 1
    assert payload["result"]["events"][0]["conflict_type"] == ("provider_observation_conflict")
    assert payload["result"]["events"][0]["trusted_provider"] == "football-data.org"
    assert payload["result"]["metadata_json"]["observation_count"] == 2


def test_provider_conflict_evaluate_persist_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/conflicts/evaluate",
            json={"dry_run": False, "include_observations": False},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_conflict_evaluate_endpoint_persists_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    save_calls: list[dict[str, object]] = []

    class FakeProviderMappingRepository:
        def list_review_candidates(
            self,
            *,
            provider: str | None = None,
            entity_type: str | None = None,
            canonical_entity_id: str | None = None,
            limit: int = 1000,
        ) -> list[ProviderEntityMappingRecord]:
            return [
                ProviderEntityMappingRecord(
                    mapping_id=302,
                    provider=provider or "football-data.org",
                    entity_type=entity_type or "fixture",
                    provider_entity_id="provider-fixture-b",
                    canonical_entity_id=canonical_entity_id or "fix_b",
                    confidence=0.43,
                    created_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    updated_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                )
            ]

    class FakeProviderConflictEventRepository:
        def save_events(
            self,
            *,
            result: ProviderConflictEvaluationResult,
            requested_by: str | None = None,
        ) -> list[ProviderConflictEventRecord]:
            save_calls.append(
                {
                    "event_count": len(result.events),
                    "requested_by": requested_by,
                }
            )
            event = result.events[0]
            return [
                ProviderConflictEventRecord(
                    provider_conflict_event_id=601,
                    source_issue_id=event.source_issue_id,
                    conflict_type=event.conflict_type,
                    severity=event.severity,
                    entity_type=event.entity_type,
                    canonical_entity_id=event.canonical_entity_id,
                    provider_names=event.provider_names,
                    provider_entity_ids=event.provider_entity_ids,
                    trusted_provider=event.trusted_provider,
                    resolution_status="open",
                    data_quality_score_delta=event.data_quality_score_delta,
                    evidence_json=event.evidence_json,
                    recommended_action=event.recommended_action,
                    requested_by=requested_by,
                    created_at_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_entity_mapping_repository",
        lambda settings: FakeProviderMappingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_provider_conflict_event_repository",
        lambda settings: FakeProviderConflictEventRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")

    try:
        response = client.post(
            "/api/v1/providers/conflicts/evaluate",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "provider": "football-data.org",
                "entity_type": "fixture",
                "include_observations": False,
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is False
    assert payload["stored_events"][0]["provider_conflict_event_id"] == 601
    assert payload["stored_events"][0]["requested_by"] == "admin_api"
    assert save_calls == [{"event_count": 1, "requested_by": "admin_api"}]


def test_provider_conflict_latest_endpoint_returns_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeProviderConflictEventRepository:
        def list_latest(
            self,
            *,
            status: str | None = None,
            limit: int = 20,
        ) -> list[ProviderConflictEventRecord]:
            calls.append({"status": status, "limit": limit})
            return [
                ProviderConflictEventRecord(
                    provider_conflict_event_id=602,
                    conflict_type="provider_mapping_conflict",
                    severity="warning",
                    entity_type="fixture",
                    canonical_entity_id="fix_a",
                    provider_names=["football-data.org"],
                    provider_entity_ids=["provider-fixture-a"],
                    trusted_provider="football-data.org",
                    resolution_status="open",
                    data_quality_score_delta=-1.5,
                    evidence_json={"mapping_issue_type": "same_provider_canonical_collision"},
                    recommended_action="confirm_or_split_canonical_mapping",
                    requested_by="admin_api",
                    created_at_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_conflict_event_repository",
        lambda settings: FakeProviderConflictEventRepository(),
    )

    response = client.get("/api/v1/providers/conflicts/latest?status=open&limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert calls == [{"status": "open", "limit": 3}]
    assert payload["items"][0]["provider_conflict_event_id"] == 602
    assert payload["items"][0]["resolution_status"] == "open"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_conflict_resolution_endpoint_updates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    class FakeProviderConflictEventRepository:
        def update_resolution_status(
            self,
            *,
            provider_conflict_event_id: int,
            resolution_status: str,
            requested_by: str | None = None,
            resolution_note: str | None = None,
        ) -> ProviderConflictEventRecord | None:
            calls.append(
                {
                    "provider_conflict_event_id": provider_conflict_event_id,
                    "resolution_status": resolution_status,
                    "requested_by": requested_by,
                    "resolution_note": resolution_note,
                }
            )
            return ProviderConflictEventRecord(
                provider_conflict_event_id=provider_conflict_event_id,
                conflict_type="provider_observation_conflict",
                severity="warning",
                entity_type="fixture",
                canonical_entity_id="fix_a",
                provider_names=["football-data.org", "sportmonks"],
                provider_entity_ids=["fd-a", "sm-a"],
                trusted_provider="football-data.org",
                resolution_status="resolved",
                data_quality_score_delta=-1.5,
                evidence_json={
                    "field_name": "kickoff_time_utc",
                    "resolution_note": resolution_note,
                },
                recommended_action="review_trusted_provider_priority_and_source_payloads",
                requested_by="admin_api",
                created_at_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
                resolved_at_utc=datetime(2026, 5, 8, 3, 0, tzinfo=UTC),
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_conflict_event_repository",
        lambda settings: FakeProviderConflictEventRepository(),
    )
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.patch(
            "/api/v1/providers/conflicts/602/resolution",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "resolution_status": "resolved",
                "resolution_note": "trusted provider payload reviewed",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "provider_conflict_event_id": 602,
            "resolution_status": "resolved",
            "requested_by": "admin_api",
            "resolution_note": "trusted provider payload reviewed",
        }
    ]
    assert payload["item"]["provider_conflict_event_id"] == 602
    assert payload["item"]["resolution_status"] == "resolved"
    assert payload["item"]["resolved_at_utc"] == "2026-05-08T03:00:00Z"


def test_provider_conflict_resolution_endpoint_requires_admin_token() -> None:
    response = client.patch(
        "/api/v1/providers/conflicts/602/resolution",
        json={"resolution_status": "ignored"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token is not configured"


def test_provider_fixture_sync_endpoint_is_disabled_by_default() -> None:
    response = client.post(
        "/api/v1/providers/football-data.org/sync/fixtures",
        json={"provider_competition_id": "PL", "season": "2025"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "provider sync is disabled"


def test_provider_sync_workflow_endpoint_is_disabled_by_default() -> None:
    response = client.post("/api/v1/ops/provider-sync/run", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "provider sync workflow is disabled"


def test_provider_sync_workflow_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        provider_sync_enabled=True,
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post("/api/v1/ops/provider-sync/run", json={})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_sync_workflow_endpoint_runs_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    def fake_run_provider_sync_workflow(
        settings: Settings,
        *,
        options: object,
        requested_by: str | None,
    ) -> ProviderSyncWorkflowResult:
        calls.append(
            {
                "provider_sync_enabled": settings.provider_sync_enabled,
                "dry_run": options.dry_run,
                "fixture_sync": options.fixture_sync.provider_competition_id
                if options.fixture_sync is not None
                else None,
                "odds_count": len(options.odds_syncs),
                "availability_count": len(options.availability_syncs),
                "run_conflict_detection": options.run_conflict_detection,
                "conflict_observation_lookback_hours": (
                    options.conflict_observation_lookback_hours
                ),
                "conflict_limit": options.conflict_limit,
                "run_prematch_workflow": options.run_prematch_workflow,
                "prematch_competition_id": options.prematch_options.competition_id
                if options.prematch_options is not None
                else None,
                "requested_by": requested_by,
            }
        )
        return ProviderSyncWorkflowResult(
            provider_sync_workflow_run_id=501,
            dry_run=options.dry_run,
            requested_by=requested_by,
            fixture_count=2,
            odds_snapshot_count=5,
            availability_snapshot_count=5,
            raw_payload_ids=[31, 32],
            canonical_fixture_ids=["fd_fixture_1", "fd_fixture_2"],
            warnings=["the_odds_api_event_odds:event_1:partial"],
            provider_conflict_evaluation=ProviderConflictEvaluationResult(
                dry_run=options.dry_run,
                as_of_time_utc=datetime(2026, 5, 8, 4, 2, tzinfo=UTC),
                checked_issue_count=2,
                conflict_count=1,
                critical_count=0,
                warning_count=1,
                info_count=0,
                provider_consistency_after_conflicts=0.5,
                data_quality_score_delta=-5.0,
                metadata_json={"source": "unit_test"},
            ),
        )

    monkeypatch.setattr(
        router_module,
        "run_audited_provider_sync_workflow",
        fake_run_provider_sync_workflow,
    )
    app.state.settings = Settings(
        provider_sync_enabled=True,
        provider_sync_workflow_enabled=True,
        prediction_jobs_enabled=True,
        prematch_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/ops/provider-sync/run",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "dry_run": True,
                "fixture_sync": {
                    "provider_competition_id": "PL",
                    "canonical_competition_id": "EPL",
                    "season": "2025",
                },
                "odds_syncs": [
                    {
                        "sport_key": "soccer_epl",
                        "provider_event_id": "event_1",
                        "canonical_fixture_id": "fd_fixture_1",
                    }
                ],
                "availability_syncs": [
                    {
                        "provider_fixture_id": "sm_fixture_1",
                        "canonical_fixture_id": "fd_fixture_1",
                        "team_mappings": [
                            {
                                "provider_team_id": "57",
                                "canonical_team_id": "fd_team_57",
                            }
                        ],
                    }
                ],
                "run_conflict_detection": True,
                "conflict_observation_lookback_hours": 24,
                "conflict_limit": 25,
                "run_prematch_workflow": True,
                "prematch": {"competition_id": "EPL"},
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["provider_sync_workflow_run_id"] == 501
    assert payload["result"]["fixture_count"] == 2
    assert payload["result"]["odds_snapshot_count"] == 5
    assert payload["result"]["availability_snapshot_count"] == 5
    assert payload["result"]["canonical_fixture_ids"] == [
        "fd_fixture_1",
        "fd_fixture_2",
    ]
    assert payload["result"]["provider_conflict_evaluation"]["conflict_count"] == 1
    assert calls == [
        {
            "provider_sync_enabled": True,
            "dry_run": True,
            "fixture_sync": "PL",
            "odds_count": 1,
            "availability_count": 1,
            "run_conflict_detection": True,
            "conflict_observation_lookback_hours": 24,
            "conflict_limit": 25,
            "run_prematch_workflow": True,
            "prematch_competition_id": "EPL",
            "requested_by": "admin_api",
        }
    ]


def test_provider_sync_workflow_endpoint_records_operator_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    approval_calls: list[dict[str, object]] = []
    linked_runs: list[int] = []

    def fake_run_provider_sync_workflow(
        settings: Settings,
        *,
        options: object,
        requested_by: str | None,
    ) -> ProviderSyncWorkflowResult:
        return ProviderSyncWorkflowResult(
            provider_sync_workflow_run_id=501,
            dry_run=options.dry_run,
            requested_by=requested_by,
            fixture_count=0,
            odds_snapshot_count=1,
            availability_snapshot_count=0,
            canonical_fixture_ids=["fd_fixture_1"],
        )

    class FakeProviderSyncWorkflowApprovalRepository:
        def record_approval(self, **kwargs: object) -> ProviderSyncWorkflowApprovalRecord:
            approval_calls.append(kwargs)
            return _provider_sync_workflow_approval_record(
                provider_sync_workflow_template_id=kwargs["provider_sync_workflow_template_id"],
                approval_note=kwargs["approval_note"],
                request_payload_json=kwargs["request_payload_json"],
            )

        def link_workflow_run(self, **kwargs: object) -> ProviderSyncWorkflowApprovalRecord:
            linked_runs.append(int(kwargs["provider_sync_workflow_run_id"]))
            return _provider_sync_workflow_approval_record(
                provider_sync_workflow_run_id=kwargs["provider_sync_workflow_run_id"],
            )

    monkeypatch.setattr(
        router_module,
        "run_audited_provider_sync_workflow",
        fake_run_provider_sync_workflow,
    )
    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_approval_repository",
        lambda settings: FakeProviderSyncWorkflowApprovalRepository(),
    )
    app.state.settings = Settings(
        provider_sync_enabled=True,
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/ops/provider-sync/run",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "dry_run": True,
                "operator_approved": True,
                "operator_approval_note": "reviewed IDs",
                "provider_sync_workflow_template_id": 701,
                "odds_syncs": [
                    {
                        "sport_key": "soccer_epl",
                        "provider_event_id": "event_1",
                        "canonical_fixture_id": "fd_fixture_1",
                    }
                ],
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["operator_approval_id"] == 801
    assert approval_calls[0]["provider_sync_workflow_template_id"] == 701
    assert approval_calls[0]["approval_note"] == "reviewed IDs"
    assert approval_calls[0]["request_payload_json"]["operator_approved"] is True
    assert linked_runs == [501]


def test_provider_sync_workflow_runs_endpoint_returns_audit_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakeProviderSyncWorkflowRepository:
        def list_latest(self, *, limit: int) -> list[ProviderSyncWorkflowRunRecord]:
            calls.append(limit)
            return [
                ProviderSyncWorkflowRunRecord(
                    provider_sync_workflow_run_id=501,
                    status="completed",
                    dry_run=True,
                    requested_by="admin_api",
                    started_at=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
                    duration_ms=1000,
                    fixture_sync_run_id=11,
                    odds_sync_run_ids=[12],
                    availability_sync_run_ids=[13],
                    fixture_count=2,
                    odds_snapshot_count=5,
                    availability_snapshot_count=5,
                    raw_payload_ids=[31, 32],
                    canonical_fixture_ids=["fd_fixture_1", "fd_fixture_2"],
                    prematch_workflow_run_id=44,
                    warnings=["partial"],
                    metadata_json={
                        "source": "admin_api",
                        "fixture_sync_requested": True,
                    },
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_run_repository",
        lambda settings: FakeProviderSyncWorkflowRepository(),
    )
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.get(
            "/api/v1/ops/provider-sync/runs?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [5]
    assert payload["items"][0]["provider_sync_workflow_run_id"] == 501
    assert payload["items"][0]["fixture_sync_run_id"] == 11
    assert payload["items"][0]["odds_sync_run_ids"] == [12]
    assert payload["items"][0]["prematch_workflow_run_id"] == 44
    assert payload["items"][0]["metadata_json"]["fixture_sync_requested"] is True


def test_provider_sync_workflow_run_detail_endpoint_returns_audit_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakeProviderSyncWorkflowRepository:
        def get_by_id(
            self,
            *,
            provider_sync_workflow_run_id: int,
        ) -> ProviderSyncWorkflowRunRecord | None:
            calls.append(provider_sync_workflow_run_id)
            if provider_sync_workflow_run_id == 404:
                return None
            return ProviderSyncWorkflowRunRecord(
                provider_sync_workflow_run_id=501,
                status="failed",
                dry_run=True,
                requested_by="admin_api",
                started_at=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
                duration_ms=1000,
                fixture_count=0,
                odds_snapshot_count=0,
                availability_snapshot_count=0,
                canonical_fixture_ids=["fd_fixture_1"],
                warnings=["provider_conflict_detection:1_open_conflicts"],
                error_message="provider timeout",
                metadata_json={
                    "source": "admin_api",
                    "odds_sync_count": 1,
                    "run_conflict_detection": True,
                },
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_run_repository",
        lambda settings: FakeProviderSyncWorkflowRepository(),
    )
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.get(
            "/api/v1/ops/provider-sync/runs/501",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [501]
    assert payload["item"]["provider_sync_workflow_run_id"] == 501
    assert payload["item"]["status"] == "failed"
    assert payload["item"]["metadata_json"]["odds_sync_count"] == 1
    assert payload["item"]["error_message"] == "provider timeout"


def test_provider_sync_workflow_preflight_endpoint_validates_explicit_tasks() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/ops/provider-sync/preflight",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "dry_run": True,
                "odds_syncs": [
                    {
                        "sport_key": "soccer_epl",
                        "provider_event_id": "event-1",
                        "canonical_fixture_id": "fd_fixture_1",
                    }
                ],
                "run_conflict_detection": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["valid"] is True
    assert payload["result"]["task_count"] == 1
    assert payload["result"]["canonical_fixture_ids"] == ["fd_fixture_1"]
    assert payload["result"]["metadata_json"]["odds_sync_count"] == 1


def test_provider_sync_workflow_template_endpoints_save_and_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    saved_templates: list[dict[str, object]] = []

    class FakeProviderSyncWorkflowTemplateRepository:
        def save_template(self, **kwargs: object) -> ProviderSyncWorkflowTemplateRecord:
            saved_templates.append(kwargs)
            return _provider_sync_workflow_template_record(
                template_name=str(kwargs["template_name"]),
                fixture_sync=kwargs["fixture_sync"],
                odds_syncs=kwargs["odds_syncs"],
                run_conflict_detection=bool(kwargs["run_conflict_detection"]),
                metadata_json=kwargs["metadata_json"],
            )

        def list_latest(
            self,
            *,
            limit: int,
        ) -> list[ProviderSyncWorkflowTemplateRecord]:
            return [_provider_sync_workflow_template_record()]

    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_template_repository",
        lambda settings: FakeProviderSyncWorkflowTemplateRepository(),
    )
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        create_response = client.post(
            "/api/v1/ops/provider-sync/templates",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "template_name": "EPL odds smoke",
                "description": "dry-run template",
                "dry_run": True,
                "fixture_sync": {
                    "provider_competition_id": "PL",
                    "season": "2025",
                    "canonical_competition_id": "EPL",
                },
                "odds_syncs": [
                    {
                        "sport_key": "soccer_epl",
                        "provider_event_id": "event-1",
                        "canonical_fixture_id": "fd_fixture_1",
                    }
                ],
                "run_conflict_detection": True,
            },
        )
        list_response = client.get(
            "/api/v1/ops/provider-sync/templates?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["item"]["template_name"] == "EPL odds smoke"
    assert create_payload["item"]["preflight_result"]["valid"] is True
    assert saved_templates[0]["template_name"] == "EPL odds smoke"
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["items"][0]["provider_sync_workflow_template_id"] == 701
    assert list_payload["items"][0]["preflight_result"]["task_count"] == 2


def test_provider_sync_workflow_template_endpoints_update_and_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    update_calls: list[dict[str, object]] = []
    archive_calls: list[dict[str, object]] = []

    class FakeProviderSyncWorkflowTemplateRepository:
        def update_template(self, **kwargs: object) -> ProviderSyncWorkflowTemplateRecord:
            update_calls.append(kwargs)
            return _provider_sync_workflow_template_record(
                template_name=str(kwargs["template_name"]),
                odds_syncs=kwargs["odds_syncs"],
                run_conflict_detection=bool(kwargs["run_conflict_detection"]),
                metadata_json=kwargs["metadata_json"],
            )

        def archive_template(self, **kwargs: object) -> ProviderSyncWorkflowTemplateRecord:
            archive_calls.append(kwargs)
            return _provider_sync_workflow_template_record(
                archived_at=datetime(2026, 5, 8, 5, 0, tzinfo=UTC),
                archived_by=kwargs["archived_by"],
                archive_reason=kwargs["archive_reason"],
                metadata_json=kwargs["metadata_json"],
            )

    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_template_repository",
        lambda settings: FakeProviderSyncWorkflowTemplateRepository(),
    )
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        update_response = client.patch(
            "/api/v1/ops/provider-sync/templates/701",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "template_name": "EPL odds updated",
                "dry_run": True,
                "odds_syncs": [
                    {
                        "sport_key": "soccer_epl",
                        "provider_event_id": "event-2",
                        "canonical_fixture_id": "fd_fixture_2",
                    }
                ],
                "run_conflict_detection": False,
            },
        )
        archive_response = client.request(
            "DELETE",
            "/api/v1/ops/provider-sync/templates/701",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={"archive_reason": "superseded"},
        )
    finally:
        app.state.settings = original_settings

    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["item"]["template_name"] == "EPL odds updated"
    assert update_calls[0]["provider_sync_workflow_template_id"] == 701
    assert update_calls[0]["metadata_json"]["template_operation"] == "update"
    assert archive_response.status_code == 200
    archive_payload = archive_response.json()
    assert archive_payload["item"]["archived_by"] == "admin_api"
    assert archive_payload["item"]["archive_reason"] == "superseded"
    assert archive_calls[0]["archive_reason"] == "superseded"


def test_provider_sync_workflow_approvals_endpoint_lists_recent_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakeProviderSyncWorkflowApprovalRepository:
        def list_latest(self, *, limit: int) -> list[ProviderSyncWorkflowApprovalRecord]:
            calls.append(limit)
            return [_provider_sync_workflow_approval_record()]

    monkeypatch.setattr(
        router_module,
        "_build_provider_sync_workflow_approval_repository",
        lambda settings: FakeProviderSyncWorkflowApprovalRepository(),
    )
    app.state.settings = Settings(
        provider_sync_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.get(
            "/api/v1/ops/provider-sync/approvals?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["provider_sync_workflow_approval_id"] == 801
    assert payload["items"][0]["approval_status"] == "approved"
    assert payload["items"][0]["provider_sync_workflow_run_id"] == 501
    assert calls == [5]


def test_prediction_job_endpoint_is_disabled_by_default() -> None:
    response = client.post(
        "/api/v1/predictions/jobs/run",
        json={"job_type": "mock_prematch_predictions", "dry_run": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "prediction jobs are disabled"


def test_prematch_workflow_endpoint_is_disabled_by_default() -> None:
    response = client.post("/api/v1/ops/prematch/run", json={})

    assert response.status_code == 403
    assert response.json()["detail"] == "prematch workflow is disabled"


def test_prematch_workflow_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        prematch_workflow_enabled=True,
        prediction_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post("/api/v1/ops/prematch/run", json={})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_prematch_workflow_endpoint_runs_audited_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    def fake_run_workflow(
        settings: Settings,
        *,
        options: object,
        requested_by: str | None,
    ) -> PrematchWorkflowResult:
        calls.append(
            {
                "prediction_jobs_enabled": settings.prediction_jobs_enabled,
                "prediction_job_type": options.prediction_job_type,
                "fixture_ids": options.fixture_ids,
                "competition_id": options.competition_id,
                "dry_run": options.dry_run,
                "enforce_odds_quality_gate": options.enforce_odds_quality_gate,
                "parlay_allowed_markets": options.parlay_allowed_markets,
                "requested_by": requested_by,
            }
        )
        prediction = PredictionJobResult(
            prediction_job_run_id=19,
            job_type=options.prediction_job_type,
            dry_run=options.dry_run,
            requested_by=requested_by,
            prediction_time_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            fixture_count=2,
            generated_count=2,
            data_quality_scores={"fix_a": 82.0, "fix_b": 79.0},
        )
        parlay = MarketPredictionParlayGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            candidate_count=2,
            generated_count=1,
            warnings=["parlay_warning"],
        )
        return PrematchWorkflowResult(
            prematch_workflow_run_id=44,
            dry_run=options.dry_run,
            requested_by=requested_by,
            started_at_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            completed_at_utc=datetime(2026, 5, 8, 2, 1, tzinfo=UTC),
            duration_ms=1000,
            prediction=prediction,
            parlay=parlay,
            warnings=["parlay_warning"],
        )

    monkeypatch.setattr(router_module, "run_audited_prematch_workflow", fake_run_workflow)
    app.state.settings = Settings(
        prematch_workflow_enabled=True,
        prediction_jobs_enabled=True,
        parlay_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/ops/prematch/run",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "prediction_job_type": "canonical_prematch_predictions",
                "fixture_ids": ["fix_a", "fix_b"],
                "competition_id": "EPL",
                "dry_run": True,
                "parlay_allowed_markets": ["1x2"],
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["prematch_workflow_run_id"] == 44
    assert payload["result"]["prediction"]["prediction_job_run_id"] == 19
    assert payload["result"]["parlay"]["generated_count"] == 1
    assert payload["result"]["warnings"] == ["parlay_warning"]
    assert calls == [
        {
            "prediction_jobs_enabled": True,
            "prediction_job_type": "canonical_prematch_predictions",
            "fixture_ids": ["fix_a", "fix_b"],
            "competition_id": "EPL",
            "dry_run": True,
            "enforce_odds_quality_gate": True,
            "parlay_allowed_markets": ("1x2",),
            "requested_by": "admin_api",
        }
    ]


def test_prematch_workflow_runs_endpoint_returns_audited_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakePrematchWorkflowRepository:
        def list_latest(self, *, limit: int) -> list[PrematchWorkflowRunRecord]:
            calls.append(limit)
            return [
                PrematchWorkflowRunRecord(
                    prematch_workflow_run_id=44,
                    status="completed",
                    dry_run=True,
                    requested_by="admin_api",
                    started_at=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 8, 2, 1, tzinfo=UTC),
                    duration_ms=1000,
                    prediction_job_run_id=19,
                    prediction_job_type="canonical_prematch_predictions",
                    prediction_fixture_count=2,
                    prediction_generated_count=2,
                    parlay_generated_count=1,
                    parlay_recommendation_ids=[77],
                    warnings=["parlay_warning"],
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_prematch_workflow_run_repository",
        lambda settings: FakePrematchWorkflowRepository(),
    )
    app.state.settings = Settings(
        prematch_workflow_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.get(
            "/api/v1/ops/prematch/runs?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [5]
    assert payload["items"][0]["prematch_workflow_run_id"] == 44
    assert payload["items"][0]["prediction_job_run_id"] == 19
    assert payload["items"][0]["parlay_recommendation_ids"] == [77]


def test_provider_odds_coverage_endpoint_returns_data_quality_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeOddsCoverageRepository:
        def build_competition_report(
            self,
            *,
            competition_id: str,
            as_of_time_utc: datetime,
            window_days: int,
            max_snapshot_lag_hours: int,
        ) -> CompetitionOddsCoverageReport:
            calls.append(
                {
                    "competition_id": competition_id,
                    "as_of_time_utc": as_of_time_utc,
                    "window_days": window_days,
                    "max_snapshot_lag_hours": max_snapshot_lag_hours,
                }
            )
            return _odds_coverage_report(as_of_time_utc)

    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: FakeOddsCoverageRepository(),
    )

    response = client.get(
        "/api/v1/providers/odds/coverage"
        "?competition_id=EPL&window_days=30&max_snapshot_lag_hours=24"
        "&as_of_time_utc=2026-05-08T12:00:00Z"
    )

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "competition_id": "EPL",
            "as_of_time_utc": datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            "window_days": 30,
            "max_snapshot_lag_hours": 24,
        }
    ]
    assert payload["report"]["competition_id"] == "EPL"
    assert payload["report"]["odds_coverage"] == 0.5
    assert payload["report"]["handicap_coverage"] == 0.5
    assert payload["report"]["data_quality_component_patch"]["data_freshness"] == 0.5
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_odds_coverage_gap_endpoint_returns_mapping_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeOddsCoverageRepository:
        def build_gap_report(
            self,
            *,
            competition_id: str,
            provider: str,
            as_of_time_utc: datetime,
            window_days: int,
            max_snapshot_lag_hours: int,
            limit: int,
        ) -> OddsCoverageGapReport:
            calls.append(
                {
                    "competition_id": competition_id,
                    "provider": provider,
                    "as_of_time_utc": as_of_time_utc,
                    "window_days": window_days,
                    "max_snapshot_lag_hours": max_snapshot_lag_hours,
                    "limit": limit,
                }
            )
            return _odds_coverage_gap_report(as_of_time_utc)

    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: FakeOddsCoverageRepository(),
    )

    response = client.get(
        "/api/v1/providers/odds/gaps"
        "?competition_id=EPL&provider=the-odds-api&window_days=90"
        "&max_snapshot_lag_hours=168&limit=20"
        "&as_of_time_utc=2026-05-08T12:00:00Z"
    )

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "competition_id": "EPL",
            "provider": "the-odds-api",
            "as_of_time_utc": datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            "window_days": 90,
            "max_snapshot_lag_hours": 168,
            "limit": 20,
        }
    ]
    assert payload["report"]["gap_count"] == 2
    assert payload["report"]["no_odds_count"] == 1
    assert payload["report"]["stale_odds_count"] == 1
    assert payload["report"]["provider_event_unavailable_count"] == 1
    assert payload["report"]["items"][0]["issue_types"] == [
        "unmapped",
        "provider_event_unavailable",
        "no_odds",
    ]
    assert payload["report"]["items"][0]["recommended_action"] == (
        "try_fallback_provider_event_mapping"
    )
    assert payload["report"]["items"][0]["fallback_candidates"][0]["provider_name"] == (
        "api-football"
    )
    assert payload["report"]["items"][1]["provider_event_id"] == "odds_event_2"
    assert payload["report"]["items"][1]["recommended_action"] == ("refresh_mapped_event_odds")
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_sportmonks_fallback_odds_probe_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/odds/fallback-probe/sportmonks",
            json={"competition_id": "EPL"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403


def test_provider_sportmonks_fallback_odds_probe_endpoint_returns_probe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_probe(settings: Settings, **kwargs: object) -> SportMonksFallbackOddsProbeResult:
        _ = settings
        calls.append(kwargs)
        return SportMonksFallbackOddsProbeResult(
            competition_id=str(kwargs["competition_id"]),
            primary_provider=str(kwargs["primary_provider"]),
            live_provider_probe=bool(kwargs["live_provider_probe"]),
            provider_key_configured=True,
            checked_gap_count=1,
            provider_event_unavailable_count=1,
            mapped_fallback_count=1,
            probed_fixture_count=1,
            recoverable_fixture_count=1,
            normalized_odds_count=3,
            bookmaker_count=1,
            market_types=["1x2"],
            generated_at_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        )

    monkeypatch.setattr(
        router_module,
        "run_sportmonks_fallback_odds_probe",
        fake_probe,
    )

    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/odds/fallback-probe/sportmonks",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "competition_id": "EPL",
                "primary_provider": "the-odds-api",
                "window_days": 90,
                "max_snapshot_lag_hours": 168,
                "limit": 10,
                "as_of_time_utc": "2026-05-08T12:00:00Z",
                "live_provider_probe": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "competition_id": "EPL",
            "primary_provider": "the-odds-api",
            "window_days": 90,
            "max_snapshot_lag_hours": 168,
            "limit": 10,
            "as_of_time_utc": datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            "live_provider_probe": True,
        }
    ]
    assert payload["result"]["fallback_provider"] == "sportmonks"
    assert payload["result"]["recoverable_fixture_count"] == 1
    assert payload["result"]["normalized_odds_count"] == 3
    assert payload["result"]["market_types"] == ["1x2"]
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_odds_coverage_endpoint_rejects_invalid_as_of_time() -> None:
    response = client.get(
        "/api/v1/providers/odds/coverage?competition_id=EPL&as_of_time_utc=bad-time"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid as_of_time_utc"


def test_provider_onboarding_assessment_dry_run_uses_odds_coverage_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeOddsCoverageRepository:
        def build_competition_report(
            self,
            *,
            competition_id: str,
            as_of_time_utc: datetime,
            window_days: int,
            max_snapshot_lag_hours: int,
        ) -> CompetitionOddsCoverageReport:
            calls.append(
                {
                    "competition_id": competition_id,
                    "as_of_time_utc": as_of_time_utc,
                    "window_days": window_days,
                    "max_snapshot_lag_hours": max_snapshot_lag_hours,
                }
            )
            return _odds_coverage_report(as_of_time_utc)

    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: FakeOddsCoverageRepository(),
    )

    response = client.post(
        "/api/v1/providers/onboarding/assessments",
        json=_onboarding_assessment_request(dry_run=True),
    )

    assert response.status_code == 200
    payload = response.json()
    assert calls == [
        {
            "competition_id": "EPL",
            "as_of_time_utc": datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
            "window_days": 30,
            "max_snapshot_lag_hours": 24,
        }
    ]
    assert payload["assessment"]["competition_id"] == "EPL"
    assert payload["assessment"]["decision"] == "not_ready"
    assert "odds_coverage_below_60" in payload["assessment"]["reasons"]
    assert payload["assessment"]["data_quality"]["components"]["odds_coverage"] == 0.5
    assert payload["assessment"]["data_quality"]["components"]["data_freshness"] == 0.5
    assert payload["odds_coverage_report"]["handicap_coverage"] == 0.5
    assert payload["stored_assessment"] is None
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_onboarding_assessment_persist_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/onboarding/assessments",
            json=_onboarding_assessment_request(dry_run=False),
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_onboarding_assessment_persists_with_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(admin_api_token="secret")
    saved_payloads: list[dict[str, object]] = []

    class FakeOddsCoverageRepository:
        def build_competition_report(
            self,
            *,
            competition_id: str,
            as_of_time_utc: datetime,
            window_days: int,
            max_snapshot_lag_hours: int,
        ) -> CompetitionOddsCoverageReport:
            return _odds_coverage_report(as_of_time_utc)

    class FakeOnboardingRepository:
        def save_assessment(
            self,
            *,
            payload: CompetitionOnboardingInput,
            assessment: CompetitionOnboardingAssessment,
        ) -> StoredCompetitionOnboardingAssessment:
            saved_payloads.append(
                {
                    "odds_coverage": payload.odds_coverage,
                    "handicap_coverage": payload.handicap_coverage,
                    "data_freshness": payload.data_freshness,
                    "decision": assessment.decision,
                }
            )
            return StoredCompetitionOnboardingAssessment(
                assessment_id=77,
                created_at_utc=datetime(2026, 5, 8, 12, 5, tzinfo=UTC),
                assessment=assessment,
            )

    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: FakeOddsCoverageRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )

    try:
        response = client.post(
            "/api/v1/providers/onboarding/assessments",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json=_onboarding_assessment_request(dry_run=False),
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert saved_payloads == [
        {
            "odds_coverage": 0.5,
            "handicap_coverage": 0.5,
            "data_freshness": 0.5,
            "decision": "not_ready",
        }
    ]
    assert payload["stored_assessment"] == {
        "assessment_id": 77,
        "created_at_utc": "2026-05-08T12:05:00Z",
    }


def test_latest_provider_onboarding_assessments_endpoint_returns_persisted_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None,
            limit: int,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            assert competition_id == "EPL"
            assert limit == 5
            assessment = assess_competition_onboarding(
                CompetitionOnboardingInput(
                    competition_id="EPL",
                    competition_name="Premier League",
                    target_stage="beta",
                    schedule_coverage=0.99,
                    result_coverage=0.995,
                    odds_coverage=0.5,
                    handicap_coverage=0.5,
                    lineup_injury_coverage=0.7,
                    historical_stats_completeness=0.82,
                    provider_consistency=0.93,
                    data_freshness=0.5,
                    historical_sample_size=420,
                    complete_seasons=1,
                    market_resolver_tests_passed=True,
                    score_grid_generation_passed=True,
                )
            )
            return [
                StoredCompetitionOnboardingAssessment(
                    assessment_id=78,
                    created_at_utc=datetime(2026, 5, 8, 12, 10, tzinfo=UTC),
                    assessment=CompetitionOnboardingAssessment(**assessment.model_dump()),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )

    response = client.get(
        "/api/v1/providers/onboarding/assessments/latest?competition_id=EPL&limit=5"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["stored_assessment"]["assessment_id"] == 78
    assert payload["items"][0]["assessment"]["competition_id"] == "EPL"
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_provider_fixture_sync_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/football-data.org/sync/fixtures",
            json={"provider_competition_id": "PL", "season": "2025"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_fixture_sync_endpoint_requires_canonical_id_for_commit() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/football-data.org/sync/fixtures",
            json={"provider_competition_id": "PL", "season": "2025", "dry_run": False},
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 400
    assert response.json()["detail"] == "canonical_competition_id is required for commit sync"


def test_provider_fixture_sync_endpoint_runs_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    def fake_run_provider_sync(
        settings: Settings,
        *,
        provider_competition_id: str,
        season: str,
        dry_run: bool,
        canonical_competition_id: str | None = None,
    ) -> FootballDataFixtureSyncResult:
        calls.append(
            {
                "enabled": settings.provider_sync_enabled,
                "provider_competition_id": provider_competition_id,
                "season": season,
                "dry_run": dry_run,
                "canonical_competition_id": canonical_competition_id,
            }
        )
        return FootballDataFixtureSyncResult(
            provider_competition_id=provider_competition_id,
            canonical_competition_id=canonical_competition_id or "EPL",
            season=season,
            dry_run=True,
            fixtures=[normalize_match(_football_data_match())],
            request_params={"season": season},
        )

    monkeypatch.setattr(router_module, "run_football_data_fixture_sync", fake_run_provider_sync)
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/football-data.org/sync/fixtures",
            json={
                "provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "season": "2025",
                "dry_run": True,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert calls == [
        {
            "enabled": True,
            "provider_competition_id": "PL",
            "season": "2025",
            "dry_run": True,
            "canonical_competition_id": "EPL",
        }
    ]
    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["normalized_fixture_count"] == 1
    assert payload["sync_run"] is None
    assert payload["raw_payload"] is None
    assert payload["canonical_write"] is None
    assert payload["sample_fixture_ids"] == ["330299"]


def test_provider_fixture_sync_endpoint_returns_commit_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_provider_sync(
        settings: Settings,
        *,
        provider_competition_id: str,
        season: str,
        dry_run: bool,
        canonical_competition_id: str | None = None,
    ) -> FootballDataFixtureSyncResult:
        assert settings.provider_sync_enabled is True
        assert dry_run is False
        return FootballDataFixtureSyncResult(
            provider_competition_id=provider_competition_id,
            canonical_competition_id=canonical_competition_id or "EPL",
            season=season,
            dry_run=False,
            sync_run=ProviderSyncRunRecord(
                provider_sync_run_id=12,
                provider_name="football-data.org",
                capability="fixtures",
                status="completed",
                started_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 6, 1, 1, tzinfo=UTC),
                duration_ms=1000,
                entity_count=1,
                metadata_json={"canonical_competition_id": "EPL"},
            ),
            raw_payload=StoredRawProviderPayload(
                payload_id=22,
                provider="football-data.org",
                endpoint="/competitions/PL/matches",
                request_hash="abc123",
                entity_type="competition",
                entity_id_hint="PL",
                fetched_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
            ),
            fixtures=[normalize_match(_football_data_match())],
            canonical_write=CanonicalFixtureWriteSummary(
                competitions=1,
                seasons=1,
                teams=2,
                fixtures=1,
                results=0,
                provider_mappings=5,
                canonical_fixture_ids=["fd_fixture_330299"],
            ),
            request_params={"season": season},
        )

    monkeypatch.setattr(router_module, "run_football_data_fixture_sync", fake_run_provider_sync)
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/football-data.org/sync/fixtures",
            json={
                "provider_competition_id": "PL",
                "canonical_competition_id": "EPL",
                "season": "2025",
                "dry_run": False,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["sync_run"]["provider_sync_run_id"] == 12
    assert payload["sync_run"]["status"] == "completed"
    assert payload["raw_payload"]["payload_id"] == 22
    assert payload["canonical_write"]["fixtures"] == 1
    assert payload["canonical_write"]["provider_mappings"] == 5
    assert payload["sample_fixture_ids"] == ["fd_fixture_330299"]


def test_provider_event_odds_sync_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/event-odds",
            json={
                "sport_key": "soccer_epl",
                "provider_event_id": "event_123",
                "canonical_fixture_id": "fix_epl_001",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_event_odds_sync_endpoint_runs_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_odds_sync(
        settings: Settings,
        *,
        sport_key: str,
        provider_event_id: str,
        canonical_fixture_id: str,
        regions: str,
        markets: str,
        bookmakers: str | None,
        dry_run: bool,
    ) -> TheOddsApiEventOddsSyncResult:
        assert settings.provider_sync_enabled is True
        assert dry_run is True
        assert regions == "eu"
        assert markets == "h2h,spreads"
        assert bookmakers is None
        return TheOddsApiEventOddsSyncResult(
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            canonical_fixture_id=canonical_fixture_id,
            dry_run=True,
            snapshots=normalize_event_odds(_the_odds_api_event_payload()),
            request_params={"regions": regions, "markets": markets, "oddsFormat": "decimal"},
        )

    monkeypatch.setattr(router_module, "run_the_odds_api_event_odds_sync", fake_run_odds_sync)
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/event-odds",
            json={
                "sport_key": "soccer_epl",
                "provider_event_id": "event_123",
                "canonical_fixture_id": "fix_epl_001",
                "dry_run": True,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["normalized_odds_count"] == 5
    assert payload["bookmaker_count"] == 1
    assert payload["market_types"] == ["1x2", "asian_handicap"]
    assert payload["sync_run"] is None
    assert payload["raw_payload"] is None
    assert payload["odds_write"] is None


def test_provider_event_odds_sync_endpoint_returns_commit_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_odds_sync(
        settings: Settings,
        *,
        sport_key: str,
        provider_event_id: str,
        canonical_fixture_id: str,
        regions: str,
        markets: str,
        bookmakers: str | None,
        dry_run: bool,
    ) -> TheOddsApiEventOddsSyncResult:
        assert dry_run is False
        return TheOddsApiEventOddsSyncResult(
            sport_key=sport_key,
            provider_event_id=provider_event_id,
            canonical_fixture_id=canonical_fixture_id,
            dry_run=False,
            sync_run=ProviderSyncRunRecord(
                provider_sync_run_id=18,
                provider_name="the-odds-api",
                capability="odds",
                status="completed",
                started_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 6, 1, 1, tzinfo=UTC),
                duration_ms=1000,
                entity_count=5,
                metadata_json={"provider_event_id": provider_event_id},
            ),
            raw_payload=StoredRawProviderPayload(
                payload_id=32,
                provider="the-odds-api",
                endpoint="/sports/soccer_epl/events/event_123/odds",
                request_hash="odds-hash",
                entity_type="fixture",
                entity_id_hint=provider_event_id,
                fetched_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
            ),
            snapshots=normalize_event_odds(_the_odds_api_event_payload()),
            odds_write=OddsSnapshotWriteSummary(
                odds_snapshots=5,
                provider_mappings=1,
                bookmaker_count=1,
                market_types=["1x2", "asian_handicap"],
                canonical_fixture_id=canonical_fixture_id,
            ),
            request_params={"regions": regions, "markets": markets, "oddsFormat": "decimal"},
        )

    monkeypatch.setattr(router_module, "run_the_odds_api_event_odds_sync", fake_run_odds_sync)
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/event-odds",
            json={
                "sport_key": "soccer_epl",
                "provider_event_id": "event_123",
                "canonical_fixture_id": "fix_epl_001",
                "dry_run": False,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["sync_run"]["provider_sync_run_id"] == 18
    assert payload["raw_payload"]["payload_id"] == 32
    assert payload["odds_write"]["odds_snapshots"] == 5
    assert payload["odds_write"]["provider_mappings"] == 1


def test_provider_mapped_event_odds_sync_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/mapped-event-odds",
            json={"canonical_competition_id": "EPL"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_mapped_event_odds_sync_endpoint_rejects_commit_without_operator_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_mapped_odds_sync(
        settings: Settings,
        *,
        canonical_competition_id: str,
        sport_key: str,
        regions: str,
        markets: str,
        bookmakers: str | None,
        min_mapping_confidence: float,
        max_mappings: int,
        dry_run: bool,
        operator_approved: bool = False,
        operator_approval_note: str | None = None,
    ) -> TheOddsApiMappedEventOddsSyncResult:
        raise ValueError("operator approval required for mapped odds commit")

    monkeypatch.setattr(
        router_module,
        "run_the_odds_api_mapped_event_odds_sync",
        fake_run_mapped_odds_sync,
    )
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/mapped-event-odds",
            json={
                "canonical_competition_id": "EPL",
                "dry_run": False,
                "include_coverage": False,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 400
    assert response.json()["detail"] == "operator approval required for mapped odds commit"


def test_provider_mapped_event_odds_sync_endpoint_runs_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_mapped_odds_sync(
        settings: Settings,
        *,
        canonical_competition_id: str,
        sport_key: str,
        regions: str,
        markets: str,
        bookmakers: str | None,
        min_mapping_confidence: float,
        max_mappings: int,
        dry_run: bool,
        operator_approved: bool = False,
        operator_approval_note: str | None = None,
    ) -> TheOddsApiMappedEventOddsSyncResult:
        assert settings.provider_sync_enabled is True
        assert canonical_competition_id == "EPL"
        assert sport_key == "soccer_epl"
        assert regions == "eu"
        assert markets == "h2h,spreads"
        assert bookmakers is None
        assert min_mapping_confidence == 0.82
        assert max_mappings == 20
        assert dry_run is False
        assert operator_approved is True
        assert operator_approval_note == "operator reviewed mapped odds commit"
        return TheOddsApiMappedEventOddsSyncResult(
            sport_key=sport_key,
            canonical_competition_id=canonical_competition_id,
            dry_run=False,
            mapping_count=2,
            fetched_event_count=2,
            synced_event_count=2,
            normalized_odds_count=10,
            odds_snapshot_count=10,
            bookmaker_count=1,
            market_types=["1x2", "asian_handicap"],
            request_params={"regions": regions, "markets": markets},
            sync_run=ProviderSyncRunRecord(
                provider_sync_run_id=19,
                provider_name="the-odds-api",
                capability="mapped_odds",
                status="completed",
                started_at=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
                duration_ms=1000,
                entity_count=10,
                metadata_json={
                    "canonical_competition_id": canonical_competition_id,
                    "operator_approval": {
                        "approved": True,
                        "scope": "mapped_event_odds_commit",
                        "note": operator_approval_note,
                    },
                },
            ),
        )

    monkeypatch.setattr(
        router_module,
        "run_the_odds_api_mapped_event_odds_sync",
        fake_run_mapped_odds_sync,
    )
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/the-odds-api/sync/mapped-event-odds",
            json={
                "canonical_competition_id": "EPL",
                "dry_run": False,
                "operator_approved": True,
                "operator_approval_note": "operator reviewed mapped odds commit",
                "include_coverage": False,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is False
    assert payload["result"]["mapping_count"] == 2
    assert payload["result"]["normalized_odds_count"] == 10
    assert payload["result"]["odds_snapshot_count"] == 10
    assert payload["result"]["sync_run"]["provider_sync_run_id"] == 19
    assert payload["result"]["sync_run"]["metadata_json"]["operator_approval"]["approved"] is True
    assert payload["coverage"] is None


def test_provider_fixture_availability_sync_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/sportmonks/sync/fixture-availability",
            json={
                "provider_fixture_id": "fixture_123",
                "canonical_fixture_id": "fix_epl_001",
                "team_mappings": [
                    {"provider_team_id": "team_1", "canonical_team_id": "fd_team_57"},
                    {"provider_team_id": "team_2", "canonical_team_id": "fd_team_64"},
                ],
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_provider_fixture_availability_sync_endpoint_runs_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[dict[str, object]] = []

    def fake_run_availability_sync(
        settings: Settings,
        *,
        provider_fixture_id: str,
        canonical_fixture_id: str,
        team_mappings: dict[str, str],
        dry_run: bool,
    ) -> SportMonksFixtureAvailabilitySyncResult:
        calls.append(
            {
                "enabled": settings.provider_sync_enabled,
                "provider_fixture_id": provider_fixture_id,
                "canonical_fixture_id": canonical_fixture_id,
                "team_mappings": team_mappings,
                "dry_run": dry_run,
            }
        )
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=provider_fixture_id,
            canonical_fixture_id=canonical_fixture_id,
            provider_team_ids=sorted(team_mappings),
            dry_run=True,
            lineups=normalize_lineups(
                _sportmonks_lineup_payload(),
                provider_fixture_id=provider_fixture_id,
                snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
            ),
            availabilities=normalize_injuries(
                _sportmonks_injury_payload(),
                provider_team_id="team_1",
                provider_fixture_id=provider_fixture_id,
                snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
            ),
            request_params={"provider_team_ids": sorted(team_mappings)},
        )

    monkeypatch.setattr(
        router_module,
        "run_sportmonks_fixture_availability_sync",
        fake_run_availability_sync,
    )
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/sportmonks/sync/fixture-availability",
            json={
                "provider_fixture_id": "fixture_123",
                "canonical_fixture_id": "fix_epl_001",
                "team_mappings": [
                    {"provider_team_id": "team_1", "canonical_team_id": "fd_team_57"},
                    {"provider_team_id": "team_2", "canonical_team_id": "fd_team_64"},
                ],
                "dry_run": True,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert calls == [
        {
            "enabled": True,
            "provider_fixture_id": "fixture_123",
            "canonical_fixture_id": "fix_epl_001",
            "team_mappings": {"team_1": "fd_team_57", "team_2": "fd_team_64"},
            "dry_run": True,
        }
    ]
    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["normalized_lineup_count"] == 2
    assert payload["normalized_availability_count"] == 1
    assert payload["provider_team_ids"] == ["team_1", "team_2"]
    assert payload["sync_run"] is None
    assert payload["raw_payloads"] == []
    assert payload["availability_write"] is None
    assert payload["sample_players"][:2] == ["Home Goalkeeper", "Away Forward"]


def test_provider_fixture_availability_sync_endpoint_returns_commit_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_run_availability_sync(
        settings: Settings,
        *,
        provider_fixture_id: str,
        canonical_fixture_id: str,
        team_mappings: dict[str, str],
        dry_run: bool,
    ) -> SportMonksFixtureAvailabilitySyncResult:
        assert settings.provider_sync_enabled is True
        assert dry_run is False
        assert team_mappings == {"team_1": "fd_team_57", "team_2": "fd_team_64"}
        return SportMonksFixtureAvailabilitySyncResult(
            provider_fixture_id=provider_fixture_id,
            canonical_fixture_id=canonical_fixture_id,
            provider_team_ids=sorted(team_mappings),
            dry_run=False,
            sync_run=ProviderSyncRunRecord(
                provider_sync_run_id=24,
                provider_name="sportmonks",
                capability="lineups_injuries",
                status="completed",
                started_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
                completed_at=datetime(2026, 5, 6, 1, 1, tzinfo=UTC),
                duration_ms=1000,
                entity_count=3,
                metadata_json={"provider_fixture_id": provider_fixture_id},
            ),
            raw_payloads=[
                StoredRawProviderPayload(
                    payload_id=42,
                    provider="sportmonks",
                    endpoint="/football/fixtures/fixture_123/lineups",
                    request_hash="lineup-hash",
                    entity_type="fixture",
                    entity_id_hint=provider_fixture_id,
                    fetched_at=datetime(2026, 5, 6, 1, 0, tzinfo=UTC),
                )
            ],
            lineups=normalize_lineups(
                _sportmonks_lineup_payload(),
                provider_fixture_id=provider_fixture_id,
                snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
            ),
            availabilities=normalize_injuries(
                _sportmonks_injury_payload(),
                provider_team_id="team_1",
                provider_fixture_id=provider_fixture_id,
                snapshot_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
            ),
            availability_write=AvailabilitySnapshotWriteSummary(
                lineup_snapshots=2,
                availability_snapshots=1,
                provider_mappings=6,
                player_mappings=3,
                canonical_fixture_id=canonical_fixture_id,
                canonical_team_ids=["fd_team_57", "fd_team_64"],
            ),
            request_params={"provider_team_ids": sorted(team_mappings)},
        )

    monkeypatch.setattr(
        router_module,
        "run_sportmonks_fixture_availability_sync",
        fake_run_availability_sync,
    )
    app.state.settings = Settings(provider_sync_enabled=True, admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/providers/sportmonks/sync/fixture-availability",
            json={
                "provider_fixture_id": "fixture_123",
                "canonical_fixture_id": "fix_epl_001",
                "team_mappings": [
                    {"provider_team_id": "team_1", "canonical_team_id": "fd_team_57"},
                    {"provider_team_id": "team_2", "canonical_team_id": "fd_team_64"},
                ],
                "dry_run": False,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["sync_run"]["provider_sync_run_id"] == 24
    assert payload["raw_payloads"][0]["payload_id"] == 42
    assert payload["availability_write"]["lineup_snapshots"] == 2
    assert payload["availability_write"]["availability_snapshots"] == 1
    assert payload["availability_write"]["provider_mappings"] == 6


def test_fixture_prediction_endpoint_returns_traceable_prediction() -> None:
    response = client.get("/api/v1/fixtures/fix_epl_001/prediction")

    assert response.status_code == 200
    payload = response.json()
    prediction = payload["prediction_snapshot"]
    fixture = payload["fixture"]
    assert prediction["model_version"] == "poisson-m1.0.0"
    assert prediction["feature_version"] == "features-m1.0.0"
    assert prediction["calibration_version"] == "calibration-m1.0.0"
    assert "score_grid" in prediction
    assert "market_probabilities" in prediction
    assert payload["model_metadata"]["data_quality_score"] == fixture["data_quality_score"]
    assert payload["stale"] is False
    assert payload["fallback_used"] is False
    assert payload["score_top_n"]
    assert payload["upset_alerts"]
    assert "1x2" in payload["odds_comparison"]


def test_fixtures_endpoint_filters_by_date_and_competition() -> None:
    response = client.get("/api/v1/fixtures?date=2026-05-06&competition_id=EPL")

    assert response.status_code == 200
    payload = response.json()
    assert [item["fixture_id"] for item in payload["items"]] == ["fix_epl_001", "fix_epl_002"]
    first_prediction = payload["items"][0]["prediction"]
    total_probability = (
        first_prediction["p_home"] + first_prediction["p_draw"] + first_prediction["p_away"]
    )
    assert total_probability == pytest.approx(1.0)
    assert first_prediction["model_version"] == "poisson-m1.0.0"
    assert first_prediction["prediction_time_utc"] == "2026-05-06T12:00:00Z"


def test_fixtures_endpoint_rejects_invalid_date_filter() -> None:
    response = client.get("/api/v1/fixtures?date=not-a-date")

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid date filter"


def test_score_grid_endpoint_returns_model_metadata() -> None:
    response = client.get("/api/v1/fixtures/fix_epl_001/score-grid")

    assert response.status_code == 200
    payload = response.json()
    grid_mass = sum(sum(row) for row in payload["grid"])
    assert grid_mass == pytest.approx(1.0)
    assert payload["model_version"] == "poisson-m1.0.0"
    assert payload["calibration_version"] == "calibration-m1.0.0"


def test_upsets_endpoint_returns_traceable_alerts() -> None:
    response = client.get("/api/v1/upsets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    first = payload["items"][0]
    assert first["fixture_id"]
    assert first["model_version"] == "poisson-m1.0.0"
    assert first["prediction_time_utc"]
    assert first["data_quality_grade"] in {"A", "B", "C", "D"}
    assert first["favorite"]
    assert first["contributions"]
    assert first["explanation_groups"]


def test_parlay_recommend_endpoint_returns_rule_status_and_costs() -> None:
    response = client.post(
        "/api/v1/parlays/recommend",
        json={
            "date": "2026-05-06",
            "pass_types": ["2x1", "4x1"],
            "strategy": "balanced",
            "unit_stake": 2,
            "max_budget": 20,
            "allow_multiple_outcomes_per_fixture": True,
            "allowed_markets": ["1x2", "cn_handicap_1x2"],
            "exclude_beta_competitions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["warnings"] == []
    assert payload["items"][0]["atomic_bet_count"] == 1
    assert payload["items"][0]["total_stake"] == 2
    assert payload["items"][0]["rule_valid"] is True
    assert payload["items"][0]["model_version"] == "poisson-m1.0.0"
    assert payload["items"][0]["atomic_bets"]
    assert "selected_probability_by_fixture" in payload["items"][0]["explanation_json"]
    assert payload["items"][0]["explanation_json"]["model_lineage"]["model_versions"] == [
        "poisson-m1.0.0"
    ]
    assert payload["items"][0]["risk_score"] >= 0
    assert payload["items"][1]["rule_valid"] is False


def test_parlay_recommend_persist_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "persist": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_parlay_recommend_persists_with_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    saved: list[dict[str, object]] = []

    class FakeParlayRepository:
        def save_recommendation(self, recommendation: object) -> StoredParlayRecommendation:
            saved.append(
                {
                    "model_version": recommendation.model_version,
                    "total_atomic_bets": recommendation.total_atomic_bets,
                }
            )
            return StoredParlayRecommendation(
                parlay_recommendation_id=501,
                parlay_leg_ids=[601, 602],
                atomic_bet_ids=[701],
                created_at=datetime(2026, 5, 7, 12, tzinfo=UTC),
            )

    monkeypatch.setattr(
        router_module,
        "_build_parlay_repository",
        lambda settings: FakeParlayRepository(),
    )
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "persist": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["stored_recommendation_ids"] == [501]
    assert saved == [{"model_version": "poisson-m1.0.0", "total_atomic_bets": 1}]


def test_parlay_recommend_endpoint_can_exclude_beta_competitions() -> None:
    response = client.post(
        "/api/v1/parlays/recommend",
        json={
            "date": "2026-05-06",
            "pass_types": ["2x1", "4x1"],
            "strategy": "balanced",
            "unit_stake": 2,
            "max_budget": 20,
            "allow_multiple_outcomes_per_fixture": True,
            "allowed_markets": ["1x2", "cn_handicap_1x2"],
            "exclude_beta_competitions": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warnings"] == [
        "skipped_2x1:beta_competition_excluded:EPL",
        "skipped_4x1:beta_competition_excluded:EPL,JPN_J1",
    ]


def test_parlay_recommend_endpoint_skips_low_quality_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_get_mock_fixture = contract_module.get_mock_fixture

    def low_quality_fixture(fixture_id: str) -> object:
        fixture = original_get_mock_fixture(fixture_id)
        if fixture is None:
            return None
        if fixture_id == "fix_epl_002":
            return {**fixture, "data_quality_score": 45.0}
        return fixture

    monkeypatch.setattr(contract_module, "get_mock_fixture", low_quality_fixture)

    response = client.post(
        "/api/v1/parlays/recommend",
        json={
            "date": "2026-05-06",
            "pass_types": ["2x1"],
            "strategy": "balanced",
            "unit_stake": 2,
            "max_budget": 20,
            "allow_multiple_outcomes_per_fixture": False,
            "allowed_markets": ["1x2", "cn_handicap_1x2"],
            "exclude_beta_competitions": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warnings"] == ["skipped_2x1:data_quality_below_50:fix_epl_002"]


def test_parlay_recommend_endpoint_uses_persisted_competition_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None = None,
            limit: int = 50,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            assert competition_id is None
            assert limit == 100
            return [
                StoredCompetitionOnboardingAssessment(
                    assessment_id=88,
                    created_at_utc=datetime(2026, 5, 8, 12, 20, tzinfo=UTC),
                    assessment=_competition_onboarding_assessment(
                        competition_id="EPL",
                        odds_coverage=0.0,
                        handicap_coverage=0.0,
                        data_freshness=0.0,
                    ),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [
                _fixture_odds_coverage("fix_epl_001", market_types=["1x2"]),
                _fixture_odds_coverage("fix_epl_002", market_types=["cn_handicap_1x2"]),
            ]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [
                _fixture_availability_coverage("fix_epl_001"),
                _fixture_availability_coverage("fix_epl_002"),
                _fixture_availability_coverage("fix_j1_001"),
            ]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1", "4x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "allow_multiple_outcomes_per_fixture": True,
                "allowed_markets": ["1x2", "cn_handicap_1x2"],
                "exclude_beta_competitions": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warnings"] == [
        "skipped_2x1:competition_not_ready:EPL",
        "skipped_4x1:competition_not_ready:EPL",
    ]
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_parlay_recommend_endpoint_falls_back_when_readiness_repository_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None = None,
            limit: int = 50,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            raise RuntimeError("offline")

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [
                _fixture_odds_coverage("fix_epl_001", market_types=["1x2"]),
                _fixture_odds_coverage("fix_epl_002", market_types=["cn_handicap_1x2"]),
            ]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [
                _fixture_availability_coverage("fix_epl_001"),
                _fixture_availability_coverage("fix_epl_002"),
            ]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "allow_multiple_outcomes_per_fixture": False,
                "allowed_markets": ["1x2", "cn_handicap_1x2"],
                "exclude_beta_competitions": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["warnings"] == ["readiness_repository_unavailable"]
    assert payload["stale"] is True
    assert payload["fallback_used"] is True


def test_fixture_prediction_endpoint_marks_stale_odds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [
                _fixture_odds_coverage(
                    "fix_epl_001",
                    market_types=["1x2", "asian_handicap"],
                    fresh_enough=False,
                    lag_hours=30.0,
                )
            ]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [_fixture_availability_coverage("fix_epl_001")]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.get("/api/v1/fixtures/fix_epl_001/prediction")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["fixture"]["status"] == "stale"
    assert payload["stale"] is True
    assert payload["fallback_used"] is False
    freshness = payload["model_metadata"]["data_freshness"]
    assert freshness["odds_available"] is True
    assert freshness["odds_fresh_enough"] is False
    assert freshness["odds_snapshot_lag_hours"] == 30.0
    assert freshness["messages"] == ["odds_stale:fix_epl_001"]


def test_parlay_recommend_endpoint_skips_stale_fixture_odds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None = None,
            limit: int = 50,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            assert competition_id is None
            assert limit == 100
            return [
                StoredCompetitionOnboardingAssessment(
                    assessment_id=89,
                    created_at_utc=datetime(2026, 5, 8, 12, 25, tzinfo=UTC),
                    assessment=_competition_onboarding_assessment(
                        competition_id="EPL",
                        odds_coverage=0.85,
                        handicap_coverage=0.80,
                        data_freshness=0.80,
                    ),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [
                _fixture_odds_coverage("fix_epl_001", market_types=["1x2"]),
                _fixture_odds_coverage(
                    "fix_epl_002",
                    market_types=["cn_handicap_1x2"],
                    fresh_enough=False,
                    lag_hours=30.0,
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [
                _fixture_availability_coverage("fix_epl_001"),
                _fixture_availability_coverage("fix_epl_002"),
            ]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "allow_multiple_outcomes_per_fixture": False,
                "allowed_markets": ["1x2", "cn_handicap_1x2"],
                "exclude_beta_competitions": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warnings"] == ["skipped_2x1:odds_stale:fix_epl_002"]
    assert payload["stale"] is True
    assert payload["fallback_used"] is False


def test_fixture_prediction_endpoint_marks_missing_lineup_and_injury(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [_fixture_odds_coverage("fix_epl_001", market_types=["1x2", "asian_handicap"])]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [_fixture_availability_coverage("fix_epl_001", has_lineup=False, has_injury=False)]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.get("/api/v1/fixtures/fix_epl_001/prediction")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["stale"] is True
    assert payload["model_metadata"]["data_quality_score"] == 69.03
    assert payload["fixture"]["data_quality_grade"] == "C"
    feature_payload = payload["prediction_snapshot"]["explanation_json"]["feature_snapshot"]
    assert feature_payload["coverage"]["lineup"]["score"] == 0.0
    assert feature_payload["coverage"]["injury"]["score"] == 0.0
    freshness = payload["model_metadata"]["data_freshness"]
    assert freshness["lineup_available"] is False
    assert freshness["injury_available"] is False
    assert freshness["messages"] == [
        "lineup_unavailable:fix_epl_001",
        "injury_unavailable:fix_epl_001",
    ]


def test_parlay_recommend_endpoint_skips_stale_lineup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    class FakeOnboardingRepository:
        def list_latest(
            self,
            *,
            competition_id: str | None = None,
            limit: int = 50,
        ) -> list[StoredCompetitionOnboardingAssessment]:
            assert competition_id is None
            assert limit == 100
            return [
                StoredCompetitionOnboardingAssessment(
                    assessment_id=90,
                    created_at_utc=datetime(2026, 5, 8, 12, 30, tzinfo=UTC),
                    assessment=_competition_onboarding_assessment(
                        competition_id="EPL",
                        odds_coverage=0.85,
                        handicap_coverage=0.80,
                        data_freshness=0.80,
                    ),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "_build_onboarding_assessment_repository",
        lambda settings: FakeOnboardingRepository(),
    )
    monkeypatch.setattr(
        router_module,
        "_build_odds_coverage_repository",
        lambda settings: _FakeFixtureOddsCoverageRepository(
            [
                _fixture_odds_coverage("fix_epl_001", market_types=["1x2"]),
                _fixture_odds_coverage("fix_epl_002", market_types=["cn_handicap_1x2"]),
            ]
        ),
    )
    monkeypatch.setattr(
        router_module,
        "_build_availability_coverage_repository",
        lambda settings: _FakeFixtureAvailabilityCoverageRepository(
            [
                _fixture_availability_coverage("fix_epl_001"),
                _fixture_availability_coverage(
                    "fix_epl_002",
                    lineup_fresh_enough=False,
                    lineup_lag_hours=30.0,
                ),
            ]
        ),
    )
    app.state.settings = Settings(provider_governance_repository="postgres")
    try:
        response = client.post(
            "/api/v1/parlays/recommend",
            json={
                "date": "2026-05-06",
                "pass_types": ["2x1"],
                "strategy": "balanced",
                "unit_stake": 2,
                "max_budget": 20,
                "allow_multiple_outcomes_per_fixture": False,
                "allowed_markets": ["1x2", "cn_handicap_1x2"],
                "exclude_beta_competitions": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warnings"] == ["skipped_2x1:lineup_stale:fix_epl_002"]
    assert payload["stale"] is True
    assert payload["fallback_used"] is False


def test_accuracy_summary_endpoint_returns_model_metrics() -> None:
    response = client.get(
        "/api/v1/accuracy/summary?model_version=active&competition_id=EPL&market=1x2&window=90d"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["log_loss"] is not None
    assert payload["brier_score"] is not None
    assert payload["sample_size"] > 0
    assert "1x2" in payload["by_market"]
    assert payload["by_market"]["1x2"]["sample_size"] > 0
    assert payload["by_competition"]
    assert payload["calibration_buckets"]
    assert isinstance(payload["error_types"], list)
    assert payload["model_comparisons"][0]["decision"] in {
        "promote_candidate",
        "keep_baseline",
        "needs_review",
    }
    assert payload["filters"]["competition_id"] == "EPL"
    assert payload["filters"]["market"] == "1x2"
    assert payload["generated_at_utc"] == "2026-05-06T12:30:00Z"


def test_accuracy_summary_endpoint_reports_unavailable_postgres_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings

    def fake_import_module(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(database_module, "import_module", fake_import_module)
    app.state.settings = Settings(accuracy_repository="postgres")
    try:
        response = client.get("/api/v1/accuracy/summary")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 503
    assert response.json()["detail"] == "accuracy repository unavailable"


def test_accuracy_job_endpoint_is_disabled_by_default() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(accuracy_repository="postgres")
    try:
        response = client.post("/api/v1/accuracy/jobs/run", json={})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "accuracy jobs are disabled"


def test_accuracy_job_endpoint_requires_postgres_repository() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        accuracy_repository="mock",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/accuracy/jobs/run",
            json={},
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 400
    assert response.json()["detail"] == "accuracy jobs require postgres repository mode"


def test_accuracy_job_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        accuracy_repository="postgres",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        missing_response = client.post("/api/v1/accuracy/jobs/run", json={})
        invalid_response = client.post(
            "/api/v1/accuracy/jobs/run",
            json={},
            headers={"X-Nutmeg-Admin-Token": "wrong"},
        )
    finally:
        app.state.settings = original_settings

    assert missing_response.status_code == 403
    assert invalid_response.status_code == 403
    assert missing_response.json()["detail"] == "admin token required"
    assert invalid_response.json()["detail"] == "admin token required"


def test_accuracy_job_endpoint_runs_controlled_postgres_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[tuple[str, bool, str | None]] = []

    def fake_run_accuracy_job(
        settings: Settings,
        *,
        job_type: str,
        reset: bool,
        requested_by: str | None,
        dixon_coles_options: object | None = None,
        weekly_training_options: object | None = None,
    ) -> AccuracyJobResult:
        calls.append((settings.accuracy_repository, reset, requested_by))
        assert job_type == "mock_postgres_e2e"
        assert dixon_coles_options is None
        assert weekly_training_options is None
        return AccuracyJobResult(
            accuracy_job_run_id=9,
            job_type="mock_postgres_e2e",
            reset=reset,
            requested_by=requested_by,
            started_at_utc=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
            completed_at_utc=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
            duration_ms=1000,
            fixture_count=3,
            prediction_snapshot_ids={
                "fix_epl_001": 201,
                "fix_epl_002": 202,
                "fix_j1_001": 203,
            },
            evaluation_ids=[301, 302, 303],
            calibration_observation_count=9,
            model_comparison_report_id=401,
        )

    monkeypatch.setattr(router_module, "run_audited_accuracy_job", fake_run_accuracy_job)
    app.state.settings = Settings(
        accuracy_repository="postgres",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/accuracy/jobs/run",
            json={"job_type": "mock_postgres_e2e", "reset": False},
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert calls == [("postgres", False, "admin_api")]
    assert response.status_code == 200
    payload = response.json()
    assert payload["accuracy_job_run_id"] == 9
    assert payload["status"] == "completed"
    assert payload["reset"] is False
    assert payload["duration_ms"] == 1000
    assert payload["fixture_count"] == 3
    assert payload["evaluation_ids"] == [301, 302, 303]
    assert payload["calibration_observation_count"] == 9
    assert payload["model_comparison_report_id"] == 401
    assert payload["stale"] is False
    assert payload["fallback_used"] is False


def test_accuracy_job_endpoint_accepts_dixon_coles_training_backtest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    options_seen: list[DixonColesTrainingBacktestJobOptions] = []

    def fake_run_accuracy_job(
        settings: Settings,
        *,
        job_type: str,
        reset: bool,
        requested_by: str | None,
        dixon_coles_options: object | None = None,
        weekly_training_options: object | None = None,
    ) -> AccuracyJobResult:
        assert settings.accuracy_repository == "postgres"
        assert job_type == "dixon_coles_training_backtest"
        assert reset is False
        assert requested_by == "admin_api"
        assert dixon_coles_options is not None
        assert weekly_training_options is None
        assert isinstance(dixon_coles_options, DixonColesTrainingBacktestJobOptions)
        options_seen.append(dixon_coles_options)
        return AccuracyJobResult(
            accuracy_job_run_id=10,
            job_type="dixon_coles_training_backtest",
            reset=reset,
            dry_run=True,
            requested_by=requested_by,
            fixture_count=8,
            prediction_snapshot_ids={},
            evaluation_ids=[],
            calibration_observation_count=0,
            model_comparison_report_id=None,
            model_promotion_review_id=None,
            candidate_model_version="dc-v1.5-candidate",
            baseline_model_version="poisson-m1.1.0",
            selected_rho=-0.05,
            train_sample_size=6,
            validation_sample_size=2,
            candidate_brier_score=0.21,
            candidate_ece=0.06,
            baseline_ece=0.08,
            baseline_calibration_evidence_json={"ece_source": "stored_calibration_buckets"},
            calibration_evidence_json={
                "calibration_status": "validation_evidence_only",
                "sample_size": 2,
            },
            model_comparison_decision="needs_review",
            model_promotion_decision="keep_experiment",
            model_promotion_next_status="experiment",
            model_promotion_reasons=["baseline_calibration_unavailable"],
            warnings=["baseline_calibration_unavailable"],
        )

    monkeypatch.setattr(router_module, "run_audited_accuracy_job", fake_run_accuracy_job)
    app.state.settings = Settings(
        accuracy_repository="postgres",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/accuracy/jobs/run",
            json={
                "job_type": "dixon_coles_training_backtest",
                "reset": False,
                "dry_run": True,
                "competition_id": "EPL",
                "as_of_time_utc": "2026-05-08T01:00:00Z",
                "train_window_days": 120,
                "validation_window_days": 30,
                "rho_candidates": [-0.15, -0.05, 0.0, 0.05],
                "promotion_minimum_sample_size": 2,
                "core_market_improvement": True,
                "upset_precision_at_k_delta": 0.0,
                "handicap_performance_delta": 0.0,
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    assert options_seen[0].competition_id == "EPL"
    assert options_seen[0].dry_run is True
    assert options_seen[0].rho_candidates == (-0.15, -0.05, 0.0, 0.05)
    assert options_seen[0].promotion_minimum_sample_size == 2
    assert options_seen[0].core_market_improvement is True
    assert options_seen[0].upset_precision_at_k_delta == 0.0
    payload = response.json()
    assert payload["job_type"] == "dixon_coles_training_backtest"
    assert payload["dry_run"] is True
    assert payload["fixture_count"] == 8
    assert payload["candidate_model_version"] == "dc-v1.5-candidate"
    assert payload["selected_rho"] == -0.05
    assert payload["candidate_brier_score"] == 0.21
    assert payload["candidate_ece"] == 0.06
    assert payload["baseline_ece"] == 0.08
    assert payload["baseline_calibration_evidence_json"]["ece_source"] == (
        "stored_calibration_buckets"
    )
    assert payload["calibration_evidence_json"]["sample_size"] == 2
    assert payload["model_promotion_decision"] == "keep_experiment"
    assert payload["model_promotion_next_status"] == "experiment"
    assert payload["warnings"] == ["baseline_calibration_unavailable"]


def test_accuracy_job_endpoint_accepts_weekly_training_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    weekly_options_seen: list[WeeklyDixonColesTrainingPipelineOptions] = []

    def fake_run_accuracy_job(
        settings: Settings,
        *,
        job_type: str,
        reset: bool,
        requested_by: str | None,
        dixon_coles_options: object | None = None,
        weekly_training_options: object | None = None,
    ) -> AccuracyJobResult:
        assert settings.accuracy_repository == "postgres"
        assert job_type == "weekly_dixon_coles_training_pipeline"
        assert reset is False
        assert requested_by == "admin_api"
        assert dixon_coles_options is None
        assert isinstance(weekly_training_options, WeeklyDixonColesTrainingPipelineOptions)
        weekly_options_seen.append(weekly_training_options)
        return AccuracyJobResult(
            accuracy_job_run_id=11,
            job_type="weekly_dixon_coles_training_pipeline",
            reset=reset,
            dry_run=True,
            requested_by=requested_by,
            fixture_count=8,
            prediction_snapshot_ids={},
            evaluation_ids=[],
            calibration_observation_count=0,
            candidate_model_version="dc-v1.5-candidate",
            baseline_model_version="poisson-m1.1.0",
            selected_rho=-0.05,
            train_sample_size=6,
            validation_sample_size=2,
            candidate_brier_score=0.21,
            candidate_ece=0.06,
            baseline_ece=0.08,
            baseline_calibration_evidence_json={"ece_source": "stored_calibration_buckets"},
            calibration_evidence_json={
                "calibration_status": "validation_evidence_only",
                "sample_size": 2,
            },
            model_comparison_decision="needs_review",
            model_promotion_decision="keep_experiment",
            model_promotion_next_status="experiment",
            weekly_training_status="completed_with_review_artifacts",
            weekly_training_plan={
                "run_label": "weekly-epl-dc",
                "scheduler_status": "operator_controlled_stub",
            },
            warnings=["candidate_brier_unavailable"],
        )

    monkeypatch.setattr(router_module, "run_audited_accuracy_job", fake_run_accuracy_job)
    app.state.settings = Settings(
        accuracy_repository="postgres",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/accuracy/jobs/run",
            json={
                "job_type": "weekly_dixon_coles_training_pipeline",
                "reset": False,
                "dry_run": True,
                "competition_id": "EPL",
                "as_of_time_utc": "2026-05-08T01:00:00Z",
                "weekly_scheduled_for_utc": "2026-05-08T02:00:00Z",
                "weekly_run_label": "weekly-epl-dc",
                "train_window_days": 120,
                "validation_window_days": 30,
                "rho_candidates": [-0.15, -0.05, 0.0, 0.05],
            },
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    assert weekly_options_seen[0].run_label == "weekly-epl-dc"
    assert weekly_options_seen[0].scheduled_for_utc == datetime(2026, 5, 8, 2, 0, tzinfo=UTC)
    assert weekly_options_seen[0].training_options.competition_id == "EPL"
    assert weekly_options_seen[0].training_options.dry_run is True
    payload = response.json()
    assert payload["job_type"] == "weekly_dixon_coles_training_pipeline"
    assert payload["weekly_training_status"] == "completed_with_review_artifacts"
    assert payload["weekly_training_plan"]["run_label"] == "weekly-epl-dc"
    assert payload["weekly_training_plan"]["scheduler_status"] == "operator_controlled_stub"


def test_accuracy_job_runs_endpoint_returns_audited_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    calls: list[int] = []

    class FakeJobRunRepository:
        def list_latest(self, *, limit: int) -> list[AccuracyJobRunRecord]:
            calls.append(limit)
            return [
                AccuracyJobRunRecord(
                    accuracy_job_run_id=9,
                    job_type="mock_postgres_e2e",
                    status="completed",
                    reset_requested=False,
                    requested_by="admin_api",
                    started_at=datetime(2026, 5, 8, 1, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 5, 8, 1, 1, tzinfo=UTC),
                    duration_ms=1000,
                    fixture_count=3,
                    evaluation_count=3,
                    calibration_observation_count=9,
                    model_comparison_report_id=401,
                    prediction_snapshot_ids={"fix_epl_001": 201},
                    evaluation_ids=[301, 302, 303],
                    metadata_json={"source": "api"},
                )
            ]

    def fake_build_repository(settings: Settings) -> FakeJobRunRepository:
        assert settings.accuracy_repository == "postgres"
        return FakeJobRunRepository()

    monkeypatch.setattr(
        router_module,
        "_build_accuracy_job_run_repository",
        fake_build_repository,
    )
    app.state.settings = Settings(
        accuracy_repository="postgres",
        accuracy_jobs_enabled=True,
        admin_api_token="secret",
    )
    try:
        response = client.get(
            "/api/v1/accuracy/jobs/runs?limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert calls == [5]
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["accuracy_job_run_id"] == 9
    assert payload["items"][0]["status"] == "completed"
    assert payload["items"][0]["prediction_snapshot_ids"] == {"fix_epl_001": 201}
    assert payload["items"][0]["evaluation_ids"] == [301, 302, 303]


def test_parlay_evaluate_endpoint_expands_multiple_ticket() -> None:
    response = client.post(
        "/api/v1/parlays/evaluate",
        json={
            "pass_type": "2x1",
            "unit_stake": 2,
            "legs": [
                {
                    "fixture_id": "A",
                    "market_type": "1x2",
                    "outcomes": ["home_win", "draw"],
                    "probabilities": {"home_win": 0.5, "draw": 0.25},
                    "odds": {"home_win": 1.8, "draw": 3.1},
                },
                {
                    "fixture_id": "B",
                    "market_type": "1x2",
                    "outcomes": ["away_win"],
                    "probabilities": {"away_win": 0.45},
                    "odds": {"away_win": 2.1},
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_atomic_bets"] == 2
    assert payload["total_stake"] == 4.0


def test_parlay_settle_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    try:
        response = client.post("/api/v1/parlays/settle", json={"limit": 10})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_parlay_settle_endpoint_runs_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    calls: list[dict[str, object]] = []

    class FakeParlayRepository:
        def settle_unsettled_atomic_bets(
            self,
            *,
            limit: int = 100,
            model_version: str | None = None,
        ) -> ParlaySettlementRun:
            calls.append({"limit": limit, "model_version": model_version})
            return ParlaySettlementRun(
                checked_atomic_bets=2,
                settled_atomic_bets=1,
                unresolved_atomic_bets=1,
            )

    monkeypatch.setattr(
        router_module,
        "_build_parlay_repository",
        lambda settings: FakeParlayRepository(),
    )
    try:
        response = client.post(
            "/api/v1/parlays/settle",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={"limit": 10, "model_version": "poisson-m1.0.0"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["checked_atomic_bets"] == 2
    assert payload["run"]["settled_atomic_bets"] == 1
    assert calls == [{"limit": 10, "model_version": "poisson-m1.0.0"}]


def test_parlay_generate_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    try:
        response = client.post("/api/v1/parlays/generate", json={"dry_run": True})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_parlay_generate_endpoint_runs_market_prediction_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(parlay_repository="postgres", admin_api_token="secret")
    calls: list[dict[str, object]] = []

    def fake_run_generator(
        database: object,
        *,
        options: object,
        repository: object | None = None,
    ) -> MarketPredictionParlayGenerationResult:
        calls.append(
            {
                "pass_type": options.pass_type,
                "dry_run": options.dry_run,
                "repository_provided": repository is not None,
            }
        )
        return MarketPredictionParlayGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.normalized_as_of_time_utc,
            candidate_count=2,
            generated_count=1,
            stored_recommendation_ids=[88],
        )

    monkeypatch.setattr(
        router_module,
        "run_market_prediction_parlay_generation",
        fake_run_generator,
    )
    try:
        response = client.post(
            "/api/v1/parlays/generate",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={"pass_type": "2x1", "dry_run": False},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["candidate_count"] == 2
    assert payload["result"]["stored_recommendation_ids"] == [88]
    assert calls == [{"pass_type": "2x1", "dry_run": False, "repository_provided": True}]


def test_recommendation_best_endpoint_runs_dry_run_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")
    calls: list[dict[str, object]] = []

    def fake_run_recommendation_generation(
        database: object,
        *,
        options: RecommendationGenerationOptions,
        repository: object | None = None,
    ) -> RecommendationGenerationResult:
        calls.append(
            {
                "pass_type": options.pass_type,
                "dry_run": options.dry_run,
                "repository_provided": repository is not None,
            }
        )
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=4,
            generated_count=1,
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_generation",
        fake_run_recommendation_generation,
    )
    _patch_recommendation_focus_repository(monkeypatch, candidates=[])
    try:
        response = client.get(
            "/api/v1/recommendations/best?pass_type=3x1&strategy=accuracy_first"
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["candidate_count"] == 4
    assert payload["result"]["generated_count"] == 1
    assert calls == [{"pass_type": "3x1", "dry_run": True, "repository_provided": False}]


def test_recommendation_generate_endpoint_requires_admin_token_for_persistence() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/recommendations/generate",
            json={"pass_type": "2x1", "dry_run": False},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_generate_endpoint_runs_persistent_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_recommendation_generation(
        database: object,
        *,
        options: RecommendationGenerationOptions,
        repository: object | None = None,
    ) -> RecommendationGenerationResult:
        calls.append(
            {
                "strategy": options.strategy,
                "dry_run": options.dry_run,
                "repository_provided": repository is not None,
                "focus_policy_answers": options.internal_trace_json.get(
                    "focus_policy_answers"
                ),
            }
        )
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=5,
            generated_count=1,
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_generation",
        fake_run_recommendation_generation,
    )
    _patch_recommendation_focus_repository(
        monkeypatch,
        candidates=[
            RecommendationCandidate(
                fixture_id="fix_focus_single",
                market_type="1x2",
                outcome="home_win",
                probability=0.82,
                decimal_odds=1.5,
                data_quality_score=92,
                model_confidence_score=0.80,
                calibration_score=0.78,
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=41,
                prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
            ),
            RecommendationCandidate(
                fixture_id="fix_focus_upset",
                market_type="1x2",
                outcome="away_win",
                probability=0.34,
                decimal_odds=3.2,
                data_quality_score=84,
                model_confidence_score=0.66,
                calibration_score=0.70,
                upset_protection_score=0.91,
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=42,
                prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
            ),
        ],
    )
    try:
        response = client.post(
            "/api/v1/recommendations/generate",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "pass_type": "2x1",
                "strategy": "budget_constrained",
                "dry_run": False,
                "as_of_time_utc": "2026-05-10T10:00:00Z",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["candidate_count"] == 5
    assert len(calls) == 1
    assert calls[0]["strategy"] == "budget_constrained"
    assert calls[0]["dry_run"] is False
    assert calls[0]["repository_provided"] is True
    focus_policy_answers = calls[0]["focus_policy_answers"]
    assert isinstance(focus_policy_answers, dict)
    single_answer = focus_policy_answers["single"]
    upset_answer = focus_policy_answers["upset"]
    assert isinstance(single_answer, dict)
    assert isinstance(upset_answer, dict)
    assert single_answer["fixture_id"] == "fix_focus_single"
    assert single_answer["prediction_time_utc"] == "2026-05-09T09:00:00Z"
    assert upset_answer["fixture_id"] == "fix_focus_upset"
    assert upset_answer["upset_protection_score"] == 0.91


def test_recommendation_global_best_endpoint_runs_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_global_planner(
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: object | None = None,
    ) -> RecommendationGlobalPlannerResult:
        calls.append(
            {
                "strategy": options.strategy,
                "pass_types": options.pass_types,
                "modes": options.modes,
                "dry_run": options.dry_run,
                "repository_provided": repository is not None,
            }
        )
        return RecommendationGlobalPlannerResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=8,
            evaluated_option_count=4,
            generated_option_count=0,
            warnings=["global_planner_no_valid_budget_safe_option"],
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_global_planner",
        fake_run_global_planner,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/global-best",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "strategy": "budget_constrained",
                "pass_types": ["1x1", "2x1", "6x1"],
                "modes": ["single", "multiple"],
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["candidate_count"] == 8
    assert payload["result"]["evaluated_option_count"] == 4
    assert payload["answer"]["status"] == "unavailable"
    assert calls == [
        {
            "strategy": "budget_constrained",
            "pass_types": ("1x1", "2x1", "6x1"),
            "modes": ("single", "multiple"),
            "dry_run": False,
            "repository_provided": True,
        }
    ]


def test_recommendation_global_best_endpoint_returns_public_answer_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")

    def option(
        key: str,
        pass_type: str,
        fixture_ids: list[str],
        *,
        rank: int,
    ) -> RecommendationGlobalPlanOption:
        selection = _recommendation_selection_for_fixture_ids(
            fixture_ids,
            pass_type=pass_type,
        )
        return RecommendationGlobalPlanOption(
            option_key=key,
            option_type="single_parlay",
            pass_type=pass_type,
            mode="single",
            planner_score=0.80 - rank * 0.05,
            within_budget=True,
            selection=selection.model_copy(
                update={
                    "explanation_json": {
                        "strategy": "accuracy_first",
                        "global_planner": {"rank": rank},
                        "final_answer_arbitration": {"rank": rank},
                        "short_odds_final_answer_adapter": {"status": "applied"},
                    }
                }
            ),
            reason_codes=["rule_valid", "within_budget"],
            explanation_json={
                "global_planner": {"rank": rank},
                "final_answer_arbitration": {"rank": rank},
                "short_odds_final_answer_adapter": {"status": "applied"},
            },
        )

    def fake_run_global_planner(
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: object | None = None,
    ) -> RecommendationGlobalPlannerResult:
        return RecommendationGlobalPlannerResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=8,
            evaluated_option_count=4,
            generated_option_count=4,
            best_option=option(
                "single_parlay:2x1:single",
                "2x1",
                ["A", "B"],
                rank=1,
            ),
            alternatives=[
                option("single_parlay:3x1:single", "3x1", ["C", "D", "E"], rank=2),
                option(
                    "single_parlay:4x1:single",
                    "4x1",
                    ["F", "G", "H", "I"],
                    rank=3,
                ),
                option(
                    "single_parlay:5x1:single",
                    "5x1",
                    ["J", "K", "L", "M", "N"],
                    rank=4,
                ),
            ],
            final_answer_decision_json={
                "calculation_basis": "final_answer_arbitrator_v3_1",
                "candidate_option_keys": ["internal-a", "internal-b"],
            },
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_global_planner",
        fake_run_global_planner,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/global-best",
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "pass_types": ["2x1", "3x1", "4x1", "5x1"],
                "modes": ["single"],
                "dry_run": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]["pass_type"] == "2x1"
    assert len(payload["alternatives"]) == 2
    assert payload["answer_set"]["summary_json"]["calculation_basis"] == (
        "public_final_answer_envelope_v3_1"
    )
    assert payload["answer_set"]["summary_json"]["backup_count"] == 2
    assert len(payload["result"]["alternatives"]) == 2
    assert payload["result"]["final_answer_decision_json"] == {
        "calculation_basis": "public_final_answer_decision_v3_1",
        "evaluated_option_count": 4,
        "generated_option_count": 4,
        "selected_pass_type": "2x1",
        "selected_mode": "single",
        "selected_answer_type": "single_parlay",
        "backup_count": 2,
        "public_scope": "single_best_answer_with_necessary_backups",
    }
    assert "strategy" not in str(payload["answer_set"])
    assert "final_answer_arbitration" not in str(payload["result"])
    assert "global_planner" not in str(payload["result"])
    assert "short_odds_final_answer_adapter" not in str(payload["result"])


def test_recommendation_global_best_endpoint_passes_locked_constraints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")
    calls: list[dict[str, object]] = []

    def fake_run_global_planner(
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: object | None = None,
    ) -> RecommendationGlobalPlannerResult:
        calls.append(
            {
                "locked": [
                    (candidate.fixture_id, candidate.market_type, candidate.outcome)
                    for candidate in options.locked_candidates
                ],
                "excluded_fixture_ids": options.excluded_fixture_ids,
                "repository_provided": repository is not None,
            }
        )
        return RecommendationGlobalPlannerResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=4,
            evaluated_option_count=1,
            generated_option_count=0,
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_global_planner",
        fake_run_global_planner,
    )
    _patch_recommendation_focus_repository(
        monkeypatch,
        candidates=[
            RecommendationCandidate(
                fixture_id="fix_a",
                market_type="1x2",
                outcome="home_win",
                probability=0.52,
                decimal_odds=2.05,
            ),
            RecommendationCandidate(
                fixture_id="fix_a",
                market_type="1x2",
                outcome="away_win",
                probability=0.64,
                decimal_odds=1.85,
            ),
            RecommendationCandidate(
                fixture_id="fix_b",
                market_type="1x2",
                outcome="away_win",
                probability=0.71,
                decimal_odds=1.55,
            ),
        ],
    )
    try:
        response = client.post(
            "/api/v1/recommendations/global-best",
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "locked_candidates": [
                    {
                        "fixture_id": "fix_a",
                        "market_type": "1x2",
                        "outcome": "home_win",
                    }
                ],
                "locked_fixture_ids": ["fix_b"],
                "excluded_fixture_ids": ["fix_c"],
                "dry_run": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    assert calls == [
        {
            "locked": [
                ("fix_a", "1x2", "home_win"),
                ("fix_b", "1x2", "away_win"),
            ],
            "excluded_fixture_ids": ("fix_c",),
            "repository_provided": False,
        }
    ]


def test_recommendation_evaluate_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post("/api/v1/recommendations/evaluate", json={"limit": 5})
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_evaluate_endpoint_runs_accuracy_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_recommendation_evaluation(
        repository: object,
        *,
        options: RecommendationEvaluationOptions | None = None,
    ) -> RecommendationEvaluationRunResult:
        assert options is not None
        calls.append(
            {
                "repository_provided": repository is not None,
                "limit": options.limit,
                "save_partial": options.save_partial,
                "evaluation_time_utc": options.evaluation_time_utc,
            }
        )
        return RecommendationEvaluationRunResult(
            checked_runs=2,
            evaluated_runs=1,
            skipped_unresolved_runs=1,
            stored_evaluation_ids=[901],
            warnings=["recommendation_run_unresolved:78"],
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_evaluation",
        fake_run_recommendation_evaluation,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/evaluate",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "limit": 25,
                "save_partial": False,
                "evaluation_time_utc": "2026-05-11T01:00:00Z",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["checked_runs"] == 2
    assert payload["result"]["evaluated_runs"] == 1
    assert payload["result"]["stored_evaluation_ids"] == [901]
    assert calls == [
        {
            "repository_provided": True,
            "limit": 25,
            "save_partial": False,
            "evaluation_time_utc": datetime(2026, 5, 11, 1, tzinfo=UTC),
        }
    ]


def test_recommendation_core_replay_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/recommendations/core-replay",
            json={
                "window_start_utc": "2026-05-01T00:00:00Z",
                "window_end_utc": "2026-05-03T00:00:00Z",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_core_replay_endpoint_runs_core_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_core_replay(
        database: object,
        *,
        options: RecommendationCoreReplayOptions,
    ) -> RecommendationCoreReplayRunResult:
        calls.append(
            {
                "database_provided": database is not None,
                "window_start_utc": options.window_start_utc,
                "window_end_utc": options.window_end_utc,
                "pass_type": options.pass_type,
                "mode": options.mode,
                "strategy": options.strategy,
                "limit": options.limit,
            }
        )
        return RecommendationCoreReplayRunResult(
            report=RecommendationCoreReplayReport(
                report_key="core_replay:unit_test",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                replay=PersistedRecommendationLifecycleReplayResult(
                    summary_json={"stage_count": 0}
                ),
                evaluations=[],
                strategy_metrics=[],
                checks=[],
                result_fixture_count=0,
                summary_json={
                    "run_count": 0,
                    "core_flow_ready": False,
                    "calculation_basis": "unit_test_core_replay",
                },
            ),
            warnings=["no_recommendation_runs_for_core_replay_window"],
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_core_replay",
        fake_run_core_replay,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/core-replay",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "window_start_utc": "2026-05-01T00:00:00Z",
                "window_end_utc": "2026-05-03T00:00:00Z",
                "pass_type": "6x1",
                "mode": "multiple",
                "strategy": "accuracy_first",
                "limit": 50,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["report"]["report_key"] == "core_replay:unit_test"
    assert payload["result"]["report"]["pass_type"] == "6x1"
    assert payload["result"]["report"]["mode"] == "multiple"
    assert payload["result"]["warnings"] == [
        "no_recommendation_runs_for_core_replay_window"
    ]
    assert calls == [
        {
            "database_provided": True,
            "window_start_utc": datetime(2026, 5, 1, tzinfo=UTC),
            "window_end_utc": datetime(2026, 5, 3, tzinfo=UTC),
            "pass_type": "6x1",
            "mode": "multiple",
            "strategy": "accuracy_first",
            "limit": 50,
        }
    ]


def test_recommendation_chain_integrity_endpoint_runs_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[RecommendationChainIntegrityOptions] = []

    def fake_run_chain_integrity(
        repository: object,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> RecommendationChainIntegrityReport:
        assert repository is not None
        calls.append(options)
        return RecommendationChainIntegrityReport(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            ready=True,
            summary_json={
                "run_count": 2,
                "leaf_recommendation_run_ids": [2],
                "source_status_sync_required_count": 1,
                "calculation_basis": "recommendation_chain_integrity_v3_1",
            },
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_chain_integrity_check",
        fake_run_chain_integrity,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/chain-integrity",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "window_start_utc": "2026-05-01T00:00:00Z",
                "window_end_utc": "2026-05-03T00:00:00Z",
                "pass_type": "6x1",
                "mode": "single",
                "strategy": "accuracy_first",
                "limit": 80,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["ready"] is True
    assert payload["result"]["summary_json"]["leaf_recommendation_run_ids"] == [2]
    assert calls[0].pass_type == "6x1"
    assert calls[0].mode == "single"
    assert calls[0].limit == 80


def test_recommendation_source_status_sync_endpoint_runs_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_source_status_sync(
        database: object,
        *,
        options: RecommendationSourceStatusSyncOptions,
    ) -> RecommendationSourceStatusSyncRunResult:
        calls.append(
            {
                "database_provided": database is not None,
                "window_start_utc": options.window_start_utc,
                "window_end_utc": options.window_end_utc,
                "pass_type": options.pass_type,
                "mode": options.mode,
                "strategy": options.strategy,
                "limit": options.limit,
                "dry_run": options.dry_run,
                "event_time_utc": options.event_time_utc,
            }
        )
        report = RecommendationChainIntegrityReport(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            ready=True,
            summary_json={
                "critical_issue_count": 0,
                "source_status_sync_required_count": 1,
                "calculation_basis": "recommendation_chain_integrity_v3_1",
            },
        )
        return RecommendationSourceStatusSyncRunResult(
            dry_run=options.dry_run,
            blocked=False,
            report=report,
            synced_source_recommendation_run_ids=[30],
            summary_json={
                "dry_run": options.dry_run,
                "blocked": False,
                "candidate_count": 1,
                "synced_source_count": 1,
                "chain_integrity_ready": True,
                "calculation_basis": "recommendation_source_status_sync_v3_1",
            },
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_source_status_sync",
        fake_run_source_status_sync,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/source-status-sync",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "window_start_utc": "2026-05-01T00:00:00Z",
                "window_end_utc": "2026-05-03T00:00:00Z",
                "pass_type": "6x1",
                "mode": "multiple",
                "strategy": "accuracy_first",
                "limit": 90,
                "event_time_utc": "2026-05-12T08:00:00Z",
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is False
    assert payload["result"]["blocked"] is False
    assert payload["result"]["synced_source_recommendation_run_ids"] == [30]
    assert payload["result"]["summary_json"]["calculation_basis"] == (
        "recommendation_source_status_sync_v3_1"
    )
    assert calls == [
        {
            "database_provided": True,
            "window_start_utc": datetime(2026, 5, 1, tzinfo=UTC),
            "window_end_utc": datetime(2026, 5, 3, tzinfo=UTC),
            "pass_type": "6x1",
            "mode": "multiple",
            "strategy": "accuracy_first",
            "limit": 90,
            "dry_run": False,
            "event_time_utc": datetime(2026, 5, 12, 8, tzinfo=UTC),
        }
    ]


def test_recommendation_benchmark_history_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.get("/api/v1/recommendations/benchmark-runs")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_benchmark_history_endpoint_lists_recent_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    class FakeBenchmarkRunRepository:
        def __init__(self, database: object) -> None:
            calls.append({"database_provided": database is not None})

        def list_history(
            self,
            *,
            benchmark_key: str | None = None,
            strategy: str | None = None,
            limit: int = 20,
        ) -> list[StoredRecommendationBenchmarkRun]:
            calls.append(
                {
                    "benchmark_key": benchmark_key,
                    "strategy": strategy,
                    "limit": limit,
                }
            )
            return [
                StoredRecommendationBenchmarkRun(
                    recommendation_benchmark_run_id=55,
                    benchmark_key=benchmark_key or "recommendation_benchmark:test",
                    dry_run=True,
                    strategy=strategy or "accuracy_first",
                    scenario_count=6,
                    completed_count=6,
                    failed_count=0,
                    global_best_selected_count=4,
                    core_replay_ready_count=3,
                    core_replay_total_run_count=12,
                    core_replay_total_settled_run_count=10,
                    final_hit_sample_size=3,
                    final_hit_count=2,
                    average_core_replay_roi=0.12,
                    warning_count=1,
                    history_comparison_json={"status": "improved"},
                    summary_json={"history_status": "improved"},
                    created_at=datetime(2026, 5, 10, 8, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "PostgresRecommendationBenchmarkRunRepository",
        FakeBenchmarkRunRepository,
    )
    try:
        response = client.get(
            "/api/v1/recommendations/benchmark-runs"
            "?benchmark_key=recommendation_benchmark%3Atest"
            "&strategy=accuracy_first"
            "&limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["recommendation_benchmark_run_id"] == 55
    assert payload["items"][0]["benchmark_key"] == "recommendation_benchmark:test"
    assert payload["items"][0]["history_comparison_json"]["status"] == "improved"
    assert calls == [
        {"database_provided": True},
        {
            "benchmark_key": "recommendation_benchmark:test",
            "strategy": "accuracy_first",
            "limit": 5,
        },
    ]


def test_recommendation_benchmark_strategy_pair_history_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.get("/api/v1/recommendations/benchmark-strategy-pairs")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_benchmark_strategy_pair_history_endpoint_lists_recent_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    class FakeBenchmarkStrategyPairRunRepository:
        def __init__(self, database: object) -> None:
            calls.append({"database_provided": database is not None})

        def list_history(
            self,
            *,
            pair_key: str | None = None,
            baseline_strategy: str | None = None,
            candidate_strategy: str | None = None,
            limit: int = 20,
        ) -> list[StoredRecommendationBenchmarkStrategyPairRun]:
            baseline_value = cast(
                RecommendationStrategy,
                baseline_strategy or "accuracy_first",
            )
            candidate_value = cast(
                RecommendationStrategy,
                candidate_strategy or "value_first",
            )
            calls.append(
                {
                    "pair_key": pair_key,
                    "baseline_strategy": baseline_strategy,
                    "candidate_strategy": candidate_strategy,
                    "limit": limit,
                }
            )
            return [
                StoredRecommendationBenchmarkStrategyPairRun(
                    recommendation_benchmark_strategy_pair_run_id=77,
                    pair_key=pair_key or "recommendation_benchmark_strategy_pair:test",
                    status="passed",
                    passed=True,
                    baseline_strategy=baseline_value,
                    candidate_strategy=candidate_value,
                    baseline_benchmark_key="recommendation_benchmark:accuracy",
                    candidate_benchmark_key="recommendation_benchmark:value",
                    baseline_benchmark_run_id=55,
                    candidate_benchmark_run_id=56,
                    comparison_key="recommendation_benchmark_strategy_comparison:test",
                    comparison_status="passed",
                    comparison_passed=True,
                    average_core_replay_roi_delta=0.10,
                    final_hit_rate_delta=0.25,
                    core_replay_ready_ratio_delta=0.0,
                    matrix_match=True,
                    failed_checks_json=[],
                    summary_json={"comparison_status": "passed"},
                    warnings_json=[],
                    created_at=datetime(2026, 5, 10, 8, tzinfo=UTC),
                )
            ]

    monkeypatch.setattr(
        router_module,
        "PostgresRecommendationBenchmarkStrategyPairRunRepository",
        FakeBenchmarkStrategyPairRunRepository,
    )
    try:
        response = client.get(
            "/api/v1/recommendations/benchmark-strategy-pairs"
            "?pair_key=recommendation_benchmark_strategy_pair%3Atest"
            "&baseline_strategy=accuracy_first"
            "&candidate_strategy=value_first"
            "&limit=5",
            headers={"X-Nutmeg-Admin-Token": "secret"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["recommendation_benchmark_strategy_pair_run_id"] == 77
    assert payload["items"][0]["pair_key"] == (
        "recommendation_benchmark_strategy_pair:test"
    )
    assert payload["items"][0]["average_core_replay_roi_delta"] == 0.10
    assert calls == [
        {"database_provided": True},
        {
            "pair_key": "recommendation_benchmark_strategy_pair:test",
            "baseline_strategy": "accuracy_first",
            "candidate_strategy": "value_first",
            "limit": 5,
        },
    ]


def test_recommendation_provider_incident_mapping_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/recommendations/provider-incidents/map",
            json={"dry_run": True},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_provider_incident_mapping_endpoint_runs_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[RecommendationProviderIncidentMappingOptions] = []

    def fake_run_mapping(
        database: object,
        *,
        options: RecommendationProviderIncidentMappingOptions,
        **_kwargs: object,
    ) -> RecommendationProviderIncidentMappingResult:
        calls.append(options)
        return RecommendationProviderIncidentMappingResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            observation_count=3,
            mapped_incident_count=1,
            stored_incident_count=0,
            incident_events=[
                RecommendationProviderIncidentEventInput(
                    provider_incident_key="availability:provider_observation:101",
                    provider_name="sportmonks",
                    fixture_id="fix_a",
                    incident_type="player_availability_injured",
                    severity="critical",
                    event_time_utc=options.as_of_time_utc,
                    observed_at_utc=options.as_of_time_utc,
                    excluded_fixture_ids=["fix_a"],
                )
            ],
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_provider_incident_mapping",
        fake_run_mapping,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/provider-incidents/map",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "lookback_hours": 12,
                "provider_name": "sportmonks",
                "canonical_fixture_id": "fix_a",
                "dry_run": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["observation_count"] == 3
    assert payload["result"]["mapped_incident_count"] == 1
    assert payload["result"]["incident_events"][0]["fixture_id"] == "fix_a"
    assert calls[0].lookback_hours == 12
    assert calls[0].provider_name == "sportmonks"
    assert calls[0].canonical_fixture_id == "fix_a"


def test_recommendation_prematch_change_report_endpoint_runs_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[RecommendationPrematchChangeReportOptions] = []

    def fake_run_report(
        database: object,
        *,
        options: RecommendationPrematchChangeReportOptions,
        **_kwargs: object,
    ) -> RecommendationPrematchChangeReportRunResult:
        calls.append(options)
        return RecommendationPrematchChangeReportRunResult(
            dry_run=options.dry_run,
            report=RecommendationPrematchChangeReport(
                report_key="prematch_change:test",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                replay=PersistedRecommendationLifecycleReplayResult(
                    stages=[
                        PersistedRecommendationLifecycleReplayStage(
                            stage_id="run-1",
                            recommendation_run_id=1,
                            run_key="run-1",
                            as_of_time_utc=options.window_start_utc,
                            status="selected",
                            pass_type=options.pass_type or "6x1",
                            mode=options.mode or "single",
                            selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
                            locked_fixture_ids=["A", "B"],
                            preserved_locked_fixture_ids=["A", "B"],
                            started_locked_fixture_ids=["A", "B"],
                            continuation_fixture_ids=["C", "D", "E", "F"],
                            remaining_open_leg_count=4,
                            event_codes=[
                                "locked_fixtures_preserved",
                                "started_locked_fixtures_retained",
                                "remaining_fixtures_continue",
                            ],
                        )
                    ],
                    summary_json={
                        "stage_count": 1,
                        "started_locked_stage_count": 1,
                        "continuation_stage_count": 1,
                        "final_continuation_fixture_ids": ["C", "D", "E", "F"],
                        "final_remaining_open_leg_count": 4,
                    },
                ),
                checkpoint_count=1,
                summary_json={
                    "stage_count": 1,
                    "changed_stage_count": 0,
                    "incident_count": 0,
                    "started_locked_stage_count": 1,
                    "continuation_stage_count": 1,
                    "final_continuation_fixture_ids": ["C", "D", "E", "F"],
                    "final_remaining_open_leg_count": 4,
                },
            ),
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_prematch_change_report",
        fake_run_report,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/prematch-change-report",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "window_start_utc": "2026-05-10T00:00:00Z",
                "window_end_utc": "2026-05-11T00:00:00Z",
                "pass_type": "2x1",
                "mode": "single",
                "strategy": "accuracy_first",
                "dry_run": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["report"]["report_key"] == "prematch_change:test"
    report_payload = payload["result"]["report"]
    assert report_payload["summary_json"]["stage_count"] == 1
    assert report_payload["summary_json"]["continuation_stage_count"] == 1
    assert report_payload["summary_json"]["final_continuation_fixture_ids"] == [
        "C",
        "D",
        "E",
        "F",
    ]
    assert report_payload["summary_json"]["final_remaining_open_leg_count"] == 4
    replay_stage = report_payload["replay"]["stages"][0]
    assert replay_stage["started_locked_fixture_ids"] == ["A", "B"]
    assert replay_stage["continuation_fixture_ids"] == ["C", "D", "E", "F"]
    assert replay_stage["remaining_open_leg_count"] == 4
    assert calls[0].pass_type == "2x1"
    assert calls[0].mode == "single"
    assert calls[0].strategy == "accuracy_first"


def test_recommendation_api_chain_locks_legs_and_reports_continuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    recommendation_run_id = 909
    selected_fixture_ids = ["A", "B", "C", "D", "E", "F"]
    locked_fixture_ids: list[str] = []

    def current_run() -> RecommendationRunLifecycleRecord:
        return RecommendationRunLifecycleRecord(
            recommendation_run_id=recommendation_run_id,
            run_key="api-chain-6x1",
            status="locked" if locked_fixture_ids else "current",
            selected_fixture_ids=selected_fixture_ids,
            locked_fixture_ids=list(locked_fixture_ids),
            created_at=datetime(2026, 5, 12, 0, tzinfo=UTC),
        )

    class FakeRecommendationRepository:
        def lock_leg(
            self,
            recommendation_run_id: int,
            *,
            fixture_id: str,
            market_type: str,
            outcome: str,
            locked_at_utc: datetime,
            reason_code: str = "user_locked_leg",
            metadata_json: dict[str, object] | None = None,
        ) -> RecommendationLifecycleMutationResult:
            assert recommendation_run_id == 909
            if fixture_id not in locked_fixture_ids:
                locked_fixture_ids.append(fixture_id)
            event = RecommendationLifecycleEventRecord(
                recommendation_lifecycle_event_id=500 + len(locked_fixture_ids),
                recommendation_run_id=recommendation_run_id,
                recommendation_key="api-chain-6x1",
                from_status="current",
                to_status="locked",
                reason_code=reason_code,
                event_time_utc=locked_at_utc,
                metadata_json={
                    "fixture_id": fixture_id,
                    "market_type": market_type,
                    "outcome": outcome,
                    **(metadata_json or {}),
                },
            )
            return RecommendationLifecycleMutationResult(
                run=current_run(),
                event=event,
                locked_leg=RecommendationLockedLegRecord(
                    recommendation_locked_leg_id=300 + len(locked_fixture_ids),
                    recommendation_run_id=recommendation_run_id,
                    fixture_id=fixture_id,
                    market_type=market_type,
                    outcome=outcome,
                    locked_at_utc=locked_at_utc,
                    status="locked",
                    metadata_json=metadata_json or {},
                ),
            )

    fake_repository = FakeRecommendationRepository()

    def fake_run_global_planner(
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: object | None = None,
    ) -> RecommendationGlobalPlannerResult:
        assert repository is fake_repository
        selection = _recommendation_selection_for_fixture_ids(
            selected_fixture_ids,
            pass_type="6x1",
        )
        best_option = RecommendationGlobalPlanOption(
            option_key="single_parlay:6x1:single",
            option_type="single_parlay",
            pass_type="6x1",
            mode="single",
            planner_score=0.78,
            within_budget=True,
            selection=selection,
            reason_codes=["rule_valid", "within_budget"],
            explanation_json={"source": "api_chain_test"},
        )
        return RecommendationGlobalPlannerResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=6,
            evaluated_option_count=1,
            generated_option_count=1,
            best_option=best_option,
            stored_run=StoredRecommendationRun(
                recommendation_run_id=recommendation_run_id,
                recommendation_candidate_ids=[1, 2, 3, 4, 5, 6],
                recommendation_candidate_pool_snapshot_id=700,
                recommendation_candidate_pool_item_ids=[11, 12, 13, 14, 15, 16],
                recommendation_lifecycle_event_ids=[800],
                created_at=datetime(2026, 5, 12, 0, tzinfo=UTC),
            ),
        )

    def fake_run_report(
        database: object,
        *,
        options: RecommendationPrematchChangeReportOptions,
        **_kwargs: object,
    ) -> RecommendationPrematchChangeReportRunResult:
        continuation_fixture_ids = [
            fixture_id
            for fixture_id in selected_fixture_ids
            if fixture_id not in locked_fixture_ids
        ]
        replay = PersistedRecommendationLifecycleReplayResult(
            stages=[
                PersistedRecommendationLifecycleReplayStage(
                    stage_id="api-chain-6x1",
                    recommendation_run_id=recommendation_run_id,
                    run_key="api-chain-6x1",
                    as_of_time_utc=options.window_start_utc,
                    status="selected",
                    pass_type="6x1",
                    mode="single",
                    selected_fixture_ids=selected_fixture_ids,
                    locked_fixture_ids=list(locked_fixture_ids),
                    preserved_locked_fixture_ids=list(locked_fixture_ids),
                    continuation_fixture_ids=continuation_fixture_ids,
                    remaining_open_leg_count=len(continuation_fixture_ids),
                    lifecycle_reason_codes=["user_locked_leg"],
                    event_codes=[
                        "initial_persisted_recommendation",
                        "locked_fixtures_preserved",
                        "remaining_fixtures_continue",
                        "user_lock_event_recorded",
                    ],
                )
            ],
            summary_json={
                "stage_count": 1,
                "locked_preservation_stage_count": 1,
                "continuation_stage_count": 1,
                "final_continuation_fixture_ids": continuation_fixture_ids,
                "final_remaining_open_leg_count": len(continuation_fixture_ids),
            },
        )
        return RecommendationPrematchChangeReportRunResult(
            dry_run=options.dry_run,
            report=RecommendationPrematchChangeReport(
                report_key="prematch_change:api-chain-6x1",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                replay=replay,
                checkpoint_count=1,
                summary_json=replay.summary_json,
            ),
        )

    monkeypatch.setattr(
        router_module,
        "_build_recommendation_repository",
        lambda settings: fake_repository,
    )
    monkeypatch.setattr(
        router_module,
        "run_recommendation_global_planner",
        fake_run_global_planner,
    )
    monkeypatch.setattr(
        router_module,
        "run_recommendation_prematch_change_report",
        fake_run_report,
    )
    try:
        generate_response = client.post(
            "/api/v1/recommendations/global-best",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-12T00:00:00Z",
                "strategy": "accuracy_first",
                "pass_types": ["6x1"],
                "modes": ["single"],
                "dry_run": False,
            },
        )
        for fixture_id in ["A", "B"]:
            lock_response = client.post(
                f"/api/v1/recommendations/{recommendation_run_id}/lock-leg",
                headers={"X-Nutmeg-Admin-Token": "secret"},
                json={
                    "fixture_id": fixture_id,
                    "market_type": "1x2",
                    "outcome": "home_win",
                    "locked_at_utc": "2026-05-12T01:00:00Z",
                    "reason_code": "user_locked_leg",
                    "metadata_json": {"source": "api_chain_test"},
                },
            )
            assert lock_response.status_code == 200
        report_response = client.post(
            "/api/v1/recommendations/prematch-change-report",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "window_start_utc": "2026-05-12T00:00:00Z",
                "window_end_utc": "2026-05-13T00:00:00Z",
                "pass_type": "6x1",
                "mode": "single",
                "strategy": "accuracy_first",
                "dry_run": True,
            },
        )
    finally:
        app.state.settings = original_settings

    assert generate_response.status_code == 200
    generate_payload = generate_response.json()
    assert generate_payload["answer"]["status"] == "ready"
    assert generate_payload["answer"]["fixture_count"] == 6
    assert generate_payload["result"]["stored_run"]["recommendation_run_id"] == 909
    assert locked_fixture_ids == ["A", "B"]
    assert report_response.status_code == 200
    report_payload = report_response.json()["result"]["report"]
    assert report_payload["summary_json"]["locked_preservation_stage_count"] == 1
    assert report_payload["summary_json"]["continuation_stage_count"] == 1
    assert report_payload["summary_json"]["final_continuation_fixture_ids"] == [
        "C",
        "D",
        "E",
        "F",
    ]
    assert report_payload["summary_json"]["final_remaining_open_leg_count"] == 4
    replay_stage = report_payload["replay"]["stages"][0]
    assert replay_stage["locked_fixture_ids"] == ["A", "B"]
    assert replay_stage["preserved_locked_fixture_ids"] == ["A", "B"]
    assert replay_stage["continuation_fixture_ids"] == ["C", "D", "E", "F"]
    assert replay_stage["remaining_open_leg_count"] == 4


def test_recommendation_recompute_trigger_endpoint_runs_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[RecommendationRecomputeTriggerOptions] = []

    def fake_run_trigger(
        database: object,
        *,
        options: RecommendationRecomputeTriggerOptions,
        **_kwargs: object,
    ) -> RecommendationRecomputeTriggerRunResult:
        calls.append(options)
        return RecommendationRecomputeTriggerRunResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            window_start_utc=options.window_start_utc,
            window_end_utc=options.as_of_time_utc,
            checked_run_count=1,
            triggered_run_count=1,
            skipped_run_count=0,
            generated_recommendation_run_ids=[88],
            incident_event_keys=["incident-A"],
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_recompute_trigger",
        fake_run_trigger,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/recompute-trigger",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "lookback_hours": 12,
                "pass_type": "2x1",
                "mode": "single",
                "strategy": "accuracy_first",
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["checked_run_count"] == 1
    assert payload["result"]["triggered_run_count"] == 1
    assert payload["result"]["generated_recommendation_run_ids"] == [88]
    assert calls[0].lookback_hours == 12
    assert calls[0].pass_type == "2x1"
    assert calls[0].mode == "single"
    assert calls[0].strategy == "accuracy_first"
    assert calls[0].trigger_locked_successors is False
    assert calls[0].dry_run is False


def test_recommendation_successor_recompute_endpoint_runs_locked_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[RecommendationSuccessorRecomputeOptions] = []

    def fake_run_successor(
        database: object,
        *,
        options: RecommendationSuccessorRecomputeOptions,
        **_kwargs: object,
    ) -> RecommendationSuccessorRecomputeRunResult:
        calls.append(options)
        selection = _recommendation_selection_for_fixture_ids(
            ["A", "B", "C", "D", "E", "F"],
            pass_type=options.pass_type or "6x1",
        ).model_copy(update={"locked_fixture_ids": ["A", "B"]})
        return RecommendationSuccessorRecomputeRunResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            source_recommendation_run_id=99,
            source_run_key="source-99",
            source_selected_fixture_ids=["A", "B", "OLD_C", "OLD_D", "OLD_E", "OLD_F"],
            locked_fixture_ids=["A", "B"],
            continuation_fixture_ids=["C", "D", "E", "F"],
            generated_recommendation_run_id=100,
            generation_result=RecommendationGenerationResult(
                dry_run=options.dry_run,
                as_of_time_utc=options.as_of_time_utc,
                candidate_count=8,
                generated_count=1,
                selection=selection,
                stored_run=StoredRecommendationRun(
                    recommendation_run_id=100,
                    created_at=options.as_of_time_utc,
                ),
            ),
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_successor_recompute",
        fake_run_successor,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/99/successor-recompute",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-12T02:00:00Z",
                "pass_type": "6x1",
                "mode": "single",
                "strategy": "accuracy_first",
                "max_budget": 20,
                "excluded_fixture_ids": ["OLD_C"],
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["source_recommendation_run_id"] == 99
    assert payload["result"]["generated_recommendation_run_id"] == 100
    assert payload["result"]["locked_fixture_ids"] == ["A", "B"]
    assert payload["result"]["continuation_fixture_ids"] == ["C", "D", "E", "F"]
    assert payload["answer"]["status"] == "ready"
    assert payload["answer"]["fixture_count"] == 6
    assert calls[0].source_recommendation_run_id == 99
    assert calls[0].pass_type == "6x1"
    assert calls[0].excluded_fixture_ids == ("OLD_C",)
    assert calls[0].dry_run is False


def test_recommendation_prematch_pipeline_endpoint_runs_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[tuple[RecommendationPrematchPipelineOptions, str | None]] = []

    def fake_run_pipeline(
        database: object,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None = None,
        **_kwargs: object,
    ) -> RecommendationPrematchPipelineRunResult:
        calls.append((options, requested_by))
        return RecommendationPrematchPipelineRunResult(
            recommendation_prematch_pipeline_run_id=301,
            dry_run=options.dry_run,
            as_of_time_utc=options.normalized_as_of_time_utc,
            window_start_utc=options.window_start_utc,
            window_end_utc=options.normalized_as_of_time_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            requested_by=requested_by,
            mapped_incident_count=1,
            stored_incident_count=1,
            checked_run_count=2,
            triggered_run_count=1,
            skipped_run_count=1,
            generated_recommendation_run_ids=[88],
            prematch_report_key="prematch_change:test",
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_prematch_pipeline",
        fake_run_pipeline,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/prematch-pipeline",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "as_of_time_utc": "2026-05-11T01:00:00Z",
                "lookback_hours": 12,
                "pass_type": "6x1",
                "mode": "multiple",
                "strategy": "accuracy_first",
                "provider_name": "sportmonks",
                "canonical_fixture_id": "fix_a",
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["recommendation_prematch_pipeline_run_id"] == 301
    assert payload["result"]["mapped_incident_count"] == 1
    assert payload["result"]["triggered_run_count"] == 1
    assert payload["result"]["generated_recommendation_run_ids"] == [88]
    assert payload["result"]["prematch_report_key"] == "prematch_change:test"
    options, requested_by = calls[0]
    assert options.lookback_hours == 12
    assert options.pass_type == "6x1"
    assert options.mode == "multiple"
    assert options.strategy == "accuracy_first"
    assert options.provider_name == "sportmonks"
    assert options.canonical_fixture_id == "fix_a"
    assert options.trigger_locked_successors is True
    assert options.dry_run is False
    assert requested_by == "admin_api"


def test_recommendation_strategy_review_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/recommendations/strategy-review",
            json={"candidate_strategy": "upset_protection"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_strategy_governance_endpoint_returns_readonly_overview() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="mock")
    try:
        response = client.get(
            "/api/v1/recommendations/strategy-governance",
            params=[
                ("candidate_strategy", "upset_protection"),
                ("candidate_strategy", "budget_constrained"),
                ("baseline_strategy", "accuracy_first"),
                ("pass_type", "3x1"),
                ("mode", "multiple"),
            ],
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["fallback_used"] is True
    assert payload["overview"]["items"][0]["candidate_strategy"] == "upset_protection"
    assert payload["overview"]["items"][0]["pass_type"] == "3x1"
    assert payload["overview"]["items"][0]["mode"] == "multiple"
    assert payload["overview"]["items"][0]["artifact"]["promotion_review"]["decision"] == (
        "shadow_candidate"
    )
    assert payload["overview"]["items"][1]["candidate_strategy"] == "budget_constrained"
    assert "mock_strategy_governance_evidence" in payload["overview"]["items"][1]["warnings"]


def test_best_recommendation_auto_strategy_uses_governance_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")
    generated_strategies: list[str] = []

    def fake_governance_overview(repository: object, **kwargs: object) -> object:
        return router_module.build_mock_recommendation_strategy_governance_overview(
            candidate_strategies=[
                "value_first",
                "upset_protection",
                "budget_constrained",
            ],
            baseline_strategy="accuracy_first",
            pass_type="2x1",
            mode="single",
        )

    def fake_run_recommendation_generation(
        database: object,
        *,
        options: RecommendationGenerationOptions,
        repository: object | None = None,
    ) -> RecommendationGenerationResult:
        generated_strategies.append(options.strategy)
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=0,
            generated_count=0,
        )

    monkeypatch.setattr(
        router_module,
        "build_recommendation_strategy_governance_overview",
        fake_governance_overview,
    )
    monkeypatch.setattr(
        router_module,
        "run_recommendation_generation",
        fake_run_recommendation_generation,
    )
    _patch_recommendation_focus_repository(monkeypatch, candidates=[])
    try:
        response = client.get(
            "/api/v1/recommendations/best",
            params={"strategy": "auto", "pass_type": "2x1", "mode": "single"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert generated_strategies == ["upset_protection"]
    assert "strategy_selection" not in payload["result"]
    assert payload["answer"]["status"] == "unavailable"


def test_recommendation_generate_all_pass_type_returns_best_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")
    generated_pass_types: list[str] = []

    def fake_run_recommendation_generation(
        database: object,
        *,
        options: RecommendationGenerationOptions,
        repository: object | None = None,
    ) -> RecommendationGenerationResult:
        generated_pass_types.append(options.pass_type)
        hit_probability = 0.30 if options.pass_type == "2x1" else 0.42
        total_score = 0.50 if options.pass_type == "2x1" else 0.70
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=4,
            generated_count=1,
            selection=_recommendation_selection(
                pass_type=options.pass_type,
                hit_probability=hit_probability,
                total_score=total_score,
            ),
        )

    monkeypatch.setattr(
        router_module,
        "run_recommendation_generation",
        fake_run_recommendation_generation,
    )
    _patch_recommendation_focus_repository(
        monkeypatch,
        candidates=[
            RecommendationCandidate(
                fixture_id="fix_focus_single",
                market_type="1x2",
                outcome="home_win",
                probability=0.91,
                decimal_odds=1.42,
                data_quality_score=96,
                model_confidence_score=0.82,
                calibration_score=0.80,
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=41,
                prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
            ),
            RecommendationCandidate(
                fixture_id="fix_focus_upset",
                market_type="cn_handicap_1x2",
                outcome="handicap_away_win",
                probability=0.46,
                decimal_odds=2.75,
                data_quality_score=84,
                model_confidence_score=0.68,
                calibration_score=0.72,
                upset_protection_score=0.93,
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=42,
                prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
            ),
        ],
    )
    try:
        response = client.post(
            "/api/v1/recommendations/generate",
            json={
                "pass_type": "all",
                "strategy": "accuracy_first",
                "dry_run": True,
                "as_of_time_utc": "2026-05-10T10:00:00Z",
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert generated_pass_types == ["2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1"]
    assert payload["answer"]["status"] == "ready"
    assert payload["answer"]["pass_type"] == "3x1"
    assert payload["single_answer"]["status"] == "ready"
    assert payload["single_answer"]["pass_type"] == "single"
    assert payload["single_answer"]["legs"][0]["fixture_id"] == "fix_focus_single"
    assert payload["upset_answer"]["status"] == "ready"
    assert payload["upset_answer"]["pass_type"] == "upset"
    assert payload["upset_answer"]["legs"][0]["fixture_id"] == "fix_focus_upset"
    assert len(payload["alternatives"]) == 2
    assert payload["answer_set"]["summary_json"]["backup_count"] == 2
    assert payload["answer_set"]["summary_json"]["public_scope"] == (
        "single_best_answer_with_necessary_backups"
    )
    assert payload["alternatives"][0]["pass_type"] == "4x1"
    assert payload["alternatives"][-1]["pass_type"] == "5x1"
    assert payload["result"]["selection"]["pass_type"] == "3x1"
    assert "strategy" not in payload["result"]["selection"]["explanation_json"]
    assert all("strategy" not in item for item in payload["alternatives"])


def test_recommendation_strategy_review_endpoint_runs_governance_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    def fake_run_recommendation_strategy_review(
        repository: object,
        *,
        options: RecommendationStrategyReviewOptions,
    ) -> RecommendationStrategyReviewRunResult:
        calls.append(
            {
                "repository_provided": repository is not None,
                "candidate_strategy": options.candidate_strategy,
                "baseline_strategy": options.baseline_strategy,
                "pass_type": options.pass_type,
                "mode": options.mode,
                "dry_run": options.dry_run,
            }
        )
        return _strategy_review_run_result(options)

    monkeypatch.setattr(
        router_module,
        "run_recommendation_strategy_review",
        fake_run_recommendation_strategy_review,
    )
    try:
        response = client.post(
            "/api/v1/recommendations/strategy-review",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "candidate_strategy": "upset_protection",
                "baseline_strategy": "accuracy_first",
                "pass_type": "3x1",
                "mode": "multiple",
                "dry_run": False,
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["dry_run"] is False
    assert payload["result"]["artifact"]["promotion_review"]["decision"] == "shadow_candidate"
    assert calls == [
        {
            "repository_provided": True,
            "candidate_strategy": "upset_protection",
            "baseline_strategy": "accuracy_first",
            "pass_type": "3x1",
            "mode": "multiple",
            "dry_run": False,
        }
    ]


def test_recommendation_lifecycle_endpoint_returns_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(recommendation_repository="postgres")

    class FakeRecommendationRepository:
        def get_lifecycle_detail(
            self,
            recommendation_run_id: int,
            *,
            event_limit: int = 100,
        ) -> RecommendationLifecycleDetail:
            assert recommendation_run_id == 77
            assert event_limit == 25
            return _lifecycle_detail()

    monkeypatch.setattr(
        router_module,
        "_build_recommendation_repository",
        lambda settings: FakeRecommendationRepository(),
    )
    try:
        response = client.get("/api/v1/recommendations/77/lifecycle?event_limit=25")
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail"]["run"]["status"] == "locked"
    assert payload["detail"]["locked_legs"][0]["fixture_id"] == "fix_a"
    assert payload["detail"]["events"][0]["reason_code"] == "user_locked_leg"


def test_recommendation_lock_leg_endpoint_requires_admin_token() -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    try:
        response = client.post(
            "/api/v1/recommendations/77/lock-leg",
            json={"fixture_id": "fix_a", "market_type": "1x2", "outcome": "home_win"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 403
    assert response.json()["detail"] == "admin token required"


def test_recommendation_lock_leg_endpoint_records_lifecycle_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    class FakeRecommendationRepository:
        def lock_leg(
            self,
            recommendation_run_id: int,
            *,
            fixture_id: str,
            market_type: str,
            outcome: str,
            locked_at_utc: datetime,
            reason_code: str = "user_locked_leg",
            metadata_json: dict[str, object] | None = None,
        ) -> RecommendationLifecycleMutationResult:
            calls.append(
                {
                    "recommendation_run_id": recommendation_run_id,
                    "fixture_id": fixture_id,
                    "market_type": market_type,
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "metadata_json": metadata_json,
                }
            )
            return _lifecycle_mutation_result(to_status="locked", reason_code=reason_code)

    monkeypatch.setattr(
        router_module,
        "_build_recommendation_repository",
        lambda settings: FakeRecommendationRepository(),
    )
    try:
        response = client.post(
            "/api/v1/recommendations/77/lock-leg",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "fixture_id": "fix_a",
                "market_type": "1x2",
                "outcome": "home_win",
                "reason_code": "user_locked_leg",
                "metadata_json": {"operator": "unit-test"},
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["run"]["status"] == "locked"
    assert calls == [
        {
            "recommendation_run_id": 77,
            "fixture_id": "fix_a",
            "market_type": "1x2",
            "outcome": "home_win",
            "reason_code": "user_locked_leg",
            "metadata_json": {"operator": "unit-test"},
        }
    ]


def test_recommendation_release_leg_endpoint_records_lifecycle_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    class FakeRecommendationRepository:
        def release_leg(
            self,
            recommendation_run_id: int,
            *,
            fixture_id: str,
            market_type: str,
            outcome: str,
            released_at_utc: datetime,
            reason_code: str = "user_released_leg",
            metadata_json: dict[str, object] | None = None,
        ) -> RecommendationLifecycleMutationResult:
            calls.append(
                {
                    "recommendation_run_id": recommendation_run_id,
                    "fixture_id": fixture_id,
                    "market_type": market_type,
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "metadata_json": metadata_json,
                }
            )
            return _lifecycle_mutation_result(
                to_status="current",
                reason_code=reason_code,
                leg_status="released",
            )

    monkeypatch.setattr(
        router_module,
        "_build_recommendation_repository",
        lambda settings: FakeRecommendationRepository(),
    )
    try:
        response = client.post(
            "/api/v1/recommendations/77/release-leg",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={
                "fixture_id": "fix_a",
                "market_type": "1x2",
                "outcome": "home_win",
                "reason_code": "user_released_leg",
                "metadata_json": {"operator": "unit-test"},
            },
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["run"]["status"] == "current"
    assert payload["result"]["locked_leg"]["status"] == "released"
    assert calls == [
        {
            "recommendation_run_id": 77,
            "fixture_id": "fix_a",
            "market_type": "1x2",
            "outcome": "home_win",
            "reason_code": "user_released_leg",
            "metadata_json": {"operator": "unit-test"},
        }
    ]


def test_recommendation_confirm_manual_endpoint_transitions_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_settings = app.state.settings
    app.state.settings = Settings(
        recommendation_repository="postgres",
        admin_api_token="secret",
    )
    calls: list[dict[str, object]] = []

    class FakeRecommendationRepository:
        def transition_run_status(
            self,
            recommendation_run_id: int,
            *,
            to_status: str,
            event_time_utc: datetime,
            reason_code: str,
            metadata_json: dict[str, object] | None = None,
        ) -> RecommendationLifecycleMutationResult:
            calls.append(
                {
                    "recommendation_run_id": recommendation_run_id,
                    "to_status": to_status,
                    "reason_code": reason_code,
                    "metadata_json": metadata_json,
                }
            )
            return _lifecycle_mutation_result(
                to_status="confirmed_manual",
                reason_code=reason_code,
            )

    monkeypatch.setattr(
        router_module,
        "_build_recommendation_repository",
        lambda settings: FakeRecommendationRepository(),
    )
    try:
        response = client.post(
            "/api/v1/recommendations/77/confirm-manual",
            headers={"X-Nutmeg-Admin-Token": "secret"},
            json={"reason_code": "user_confirmed_ticket"},
        )
    finally:
        app.state.settings = original_settings

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["run"]["status"] == "confirmed_manual"
    assert calls == [
        {
            "recommendation_run_id": 77,
            "to_status": "confirmed_manual",
            "reason_code": "user_confirmed_ticket",
            "metadata_json": {},
        }
    ]


def _lifecycle_run(
    status: Literal["current", "locked", "confirmed_manual"] = "locked",
) -> RecommendationRunLifecycleRecord:
    return RecommendationRunLifecycleRecord(
        recommendation_run_id=77,
        run_key="rec-key",
        status=status,
        selected_fixture_ids=["fix_a", "fix_b"],
        locked_fixture_ids=["fix_a"] if status in {"locked", "confirmed_manual"} else [],
        created_at=datetime(2026, 5, 9, 10, tzinfo=UTC),
    )


def _lifecycle_event(
    *,
    to_status: Literal["current", "locked", "confirmed_manual"],
    reason_code: str,
) -> RecommendationLifecycleEventRecord:
    return RecommendationLifecycleEventRecord(
        recommendation_lifecycle_event_id=501,
        recommendation_run_id=77,
        recommendation_key="rec-key",
        from_status="current",
        to_status=to_status,
        reason_code=reason_code,
        event_time_utc=datetime(2026, 5, 9, 11, tzinfo=UTC),
        metadata_json={"source": "unit-test"},
    )


def _locked_leg(status: str = "locked") -> RecommendationLockedLegRecord:
    return RecommendationLockedLegRecord(
        recommendation_locked_leg_id=301,
        recommendation_run_id=77,
        fixture_id="fix_a",
        market_type="1x2",
        outcome="home_win",
        locked_at_utc=datetime(2026, 5, 9, 11, tzinfo=UTC),
        status=status,
        metadata_json={"operator": "unit-test"},
    )


def _lifecycle_detail() -> RecommendationLifecycleDetail:
    return RecommendationLifecycleDetail(
        run=_lifecycle_run(status="locked"),
        locked_legs=[_locked_leg()],
        events=[_lifecycle_event(to_status="locked", reason_code="user_locked_leg")],
    )


def _lifecycle_mutation_result(
    *,
    to_status: Literal["current", "locked", "confirmed_manual"],
    reason_code: str,
    leg_status: str | None = None,
) -> RecommendationLifecycleMutationResult:
    return RecommendationLifecycleMutationResult(
        run=_lifecycle_run(status=to_status),
        event=_lifecycle_event(to_status=to_status, reason_code=reason_code),
        locked_leg=_locked_leg(leg_status or "locked") if to_status != "confirmed_manual" else None,
    )


def _strategy_review_run_result(
    options: RecommendationStrategyReviewOptions,
) -> RecommendationStrategyReviewRunResult:
    candidate_evidence = _strategy_evidence(
        options.candidate_strategy,
        pass_type=options.pass_type,
        mode=options.mode,
        roi=0.12,
    )
    baseline_evidence = _strategy_evidence(
        options.baseline_strategy,
        pass_type=options.pass_type,
        mode=options.mode,
        roi=0.08,
    )
    promotion_review = RecommendationStrategyPromotionReview(
        candidate_strategy=options.candidate_strategy,
        baseline_strategy=options.baseline_strategy,
        pass_type=options.pass_type,
        mode=options.mode,
        decision="shadow_candidate",
        next_status="shadow",
        reasons=["strategy_passed_first_governance_gate"],
    )
    rollback_plan = RecommendationStrategyRollbackPlan(should_rollback=False)
    artifact = RecommendationStrategyReviewArtifact(
        review_key="unit-test-strategy-review",
        candidate_evidence=candidate_evidence,
        baseline_evidence=baseline_evidence,
        promotion_review=promotion_review,
        rollback_plan=rollback_plan,
        metrics_json={
            "deltas": {"roi_delta": 0.04},
            "calculation_basis": "unit_test",
        },
        window_start_utc=None,
        window_end_utc=None,
    )
    return RecommendationStrategyReviewRunResult(
        dry_run=options.dry_run,
        artifact=artifact,
        warnings=[],
    )


def _strategy_evidence(
    strategy: str,
    *,
    pass_type: str,
    mode: str,
    roi: float,
) -> RecommendationStrategyEvidence:
    return RecommendationStrategyEvidence(
        strategy=strategy,
        pass_type=pass_type,
        mode=mode,
        sample_size=60,
        settled_run_count=60,
        hit_count=30,
        total_stake=120.0,
        gross_payout=120.0 * (1.0 + roi),
        profit_loss=120.0 * roi,
        roi=roi,
        hit_rate=0.5,
        average_expected_roi=roi,
        average_expected_hit_probability=0.48,
        average_hit_calibration_error=0.02,
        mean_absolute_hit_calibration_error=0.06,
        first_evaluation_time_utc=datetime(2026, 5, 1, tzinfo=UTC),
        last_evaluation_time_utc=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _football_data_match() -> dict[str, object]:
    return {
        "id": 330299,
        "utcDate": "2026-05-06T19:00:00Z",
        "status": "SCHEDULED",
        "matchday": 34,
        "competition": {"id": 2021, "code": "PL", "name": "Premier League"},
        "season": {"id": 2025, "startDate": "2025-08-15", "endDate": "2026-05-24"},
        "homeTeam": {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS"},
        "awayTeam": {"id": 64, "name": "Liverpool FC", "shortName": "Liverpool", "tla": "LIV"},
        "score": {"fullTime": {"home": None, "away": None}},
    }


def _odds_coverage_report(as_of_time_utc: datetime) -> CompetitionOddsCoverageReport:
    return CompetitionOddsCoverageReport(
        competition_id="EPL",
        competition_name="Premier League",
        window_start_utc=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        as_of_time_utc=as_of_time_utc,
        max_snapshot_lag_hours=24,
        fixture_count=2,
        fixtures_with_any_odds=1,
        fixtures_with_1x2=1,
        fixtures_with_handicap=1,
        fresh_odds_fixture_count=1,
        odds_snapshot_count=5,
        bookmaker_count=2,
        average_bookmakers_per_fixture=1.0,
        odds_coverage=0.5,
        one_x_two_coverage=0.5,
        handicap_coverage=0.5,
        fresh_odds_coverage=0.5,
        market_types=["1x2", "asian_handicap"],
        data_quality_component_patch=OddsCoverageComponentPatch(
            odds_coverage=0.5,
            handicap_coverage=0.5,
            data_freshness=0.5,
        ),
        fixtures=[
            FixtureOddsCoverage(
                fixture_id="fix_epl_001",
                competition_id="EPL",
                competition_name="Premier League",
                kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
                odds_snapshot_count=5,
                bookmaker_count=2,
                has_any_odds=True,
                has_1x2=True,
                has_handicap=True,
                latest_snapshot_time_utc=datetime(2026, 5, 6, 17, 0, tzinfo=UTC),
                latest_snapshot_lag_hours=2.0,
                fresh_enough=True,
                market_types=["1x2", "asian_handicap"],
            )
        ],
        generated_at_utc=as_of_time_utc,
    )


def _odds_coverage_gap_report(as_of_time_utc: datetime) -> OddsCoverageGapReport:
    return OddsCoverageGapReport(
        competition_id="EPL",
        competition_name="Premier League",
        provider="the-odds-api",
        window_start_utc=datetime(2026, 2, 7, 12, 0, tzinfo=UTC),
        as_of_time_utc=as_of_time_utc,
        max_snapshot_lag_hours=168,
        fixture_count=31,
        gap_count=2,
        no_odds_count=1,
        stale_odds_count=1,
        provider_event_unavailable_count=1,
        missing_1x2_count=0,
        missing_handicap_count=1,
        unmapped_fixture_count=1,
        mapped_gap_count=1,
        items=[
            OddsCoverageGapItem(
                fixture_id="fix_epl_001",
                competition_id="EPL",
                competition_name="Premier League",
                kickoff_time_utc=datetime(2026, 5, 10, 14, 0, tzinfo=UTC),
                home_team_name="Arsenal",
                away_team_name="Brighton",
                issue_types=["unmapped", "provider_event_unavailable", "no_odds"],
                recommended_action="try_fallback_provider_event_mapping",
                odds_snapshot_count=0,
                bookmaker_count=0,
                has_1x2=False,
                has_handicap=False,
                fresh_enough=False,
                latest_snapshot_time_utc=None,
                latest_snapshot_lag_hours=None,
                market_types=[],
                has_provider_mapping=False,
                provider="the-odds-api",
                provider_event_id=None,
                provider_mapping_id=None,
                provider_mapping_confidence=None,
                provider_mapping_updated_at_utc=None,
                event_availability_note=(
                    "the-odds-api has no mapped event for this fixture in the current "
                    "provider-event bootstrap window; check fallback provider coverage."
                ),
                fallback_candidates=[
                    OddsCoverageFallbackProviderCandidate(
                        provider_name="api-football",
                        coverage_role="broad_fixture_result_provider_candidate",
                        adapter_status="supported_now",
                        required_env_var="NUTMEG_API_FOOTBALL_API_KEY",
                        recommended_action="bootstrap_api_football_fixture_mapping",
                    )
                ],
            ),
            OddsCoverageGapItem(
                fixture_id="fix_epl_002",
                competition_id="EPL",
                competition_name="Premier League",
                kickoff_time_utc=datetime(2026, 5, 11, 19, 0, tzinfo=UTC),
                home_team_name="Chelsea",
                away_team_name="Everton",
                issue_types=["stale_odds", "missing_market"],
                recommended_action="refresh_mapped_event_odds",
                odds_snapshot_count=3,
                bookmaker_count=1,
                has_1x2=True,
                has_handicap=False,
                fresh_enough=False,
                latest_snapshot_time_utc=datetime(2026, 4, 28, 12, 0, tzinfo=UTC),
                latest_snapshot_lag_hours=317.0,
                market_types=["1x2"],
                has_provider_mapping=True,
                provider="the-odds-api",
                provider_event_id="odds_event_2",
                provider_mapping_id=22,
                provider_mapping_confidence=0.97,
                provider_mapping_updated_at_utc=datetime(2026, 5, 1, 8, 0, tzinfo=UTC),
            ),
        ],
        generated_at_utc=as_of_time_utc,
    )


def _onboarding_assessment_request(*, dry_run: bool) -> dict[str, object]:
    return {
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "target_stage": "beta",
        "window_days": 30,
        "max_snapshot_lag_hours": 24,
        "as_of_time_utc": "2026-05-08T12:00:00Z",
        "schedule_coverage": 0.99,
        "result_coverage": 0.995,
        "lineup_injury_coverage": 0.7,
        "historical_stats_completeness": 0.82,
        "provider_consistency": 0.93,
        "historical_sample_size": 420,
        "complete_seasons": 1,
        "market_resolver_tests_passed": True,
        "score_grid_generation_passed": True,
        "dry_run": dry_run,
    }


def _competition_onboarding_assessment(
    *,
    competition_id: str,
    odds_coverage: float,
    handicap_coverage: float,
    data_freshness: float,
) -> CompetitionOnboardingAssessment:
    return assess_competition_onboarding(
        CompetitionOnboardingInput(
            competition_id=competition_id,
            competition_name="Premier League" if competition_id == "EPL" else competition_id,
            target_stage="beta",
            schedule_coverage=0.99,
            result_coverage=0.995,
            odds_coverage=odds_coverage,
            handicap_coverage=handicap_coverage,
            lineup_injury_coverage=0.70,
            historical_stats_completeness=0.82,
            provider_consistency=0.93,
            data_freshness=data_freshness,
            historical_sample_size=420,
            complete_seasons=1,
            market_resolver_tests_passed=True,
            score_grid_generation_passed=True,
        )
    )


class _FakeFixtureOddsCoverageRepository:
    def __init__(self, items: list[FixtureOddsCoverage]) -> None:
        self.items = items

    def list_fixture_coverage(
        self,
        *,
        fixture_ids: list[str],
        as_of_time_utc: datetime,
        max_snapshot_lag_hours: int,
    ) -> list[FixtureOddsCoverage]:
        assert max_snapshot_lag_hours == 24
        requested = set(fixture_ids)
        return [item for item in self.items if item.fixture_id in requested]


class _FakeFixtureAvailabilityCoverageRepository:
    def __init__(self, items: list[FixtureAvailabilityCoverage]) -> None:
        self.items = items

    def list_fixture_coverage(
        self,
        *,
        fixture_ids: list[str],
        as_of_time_utc: datetime,
        max_snapshot_lag_hours: int,
    ) -> list[FixtureAvailabilityCoverage]:
        assert max_snapshot_lag_hours == 24
        requested = set(fixture_ids)
        return [item for item in self.items if item.fixture_id in requested]


def _fixture_odds_coverage(
    fixture_id: str,
    *,
    market_types: list[str],
    fresh_enough: bool = True,
    lag_hours: float = 2.0,
) -> FixtureOddsCoverage:
    return FixtureOddsCoverage(
        fixture_id=fixture_id,
        competition_id="EPL" if fixture_id.startswith("fix_epl") else "JPN_J1",
        competition_name="Premier League" if fixture_id.startswith("fix_epl") else "J1 League",
        kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        odds_snapshot_count=len(market_types),
        bookmaker_count=1,
        has_any_odds=bool(market_types),
        has_1x2="1x2" in market_types,
        has_handicap=bool(
            {"asian_handicap", "cn_handicap_1x2", "european_handicap_1x2"} & set(market_types)
        ),
        latest_snapshot_time_utc=datetime(2026, 5, 6, 17, 0, tzinfo=UTC),
        latest_snapshot_lag_hours=lag_hours,
        fresh_enough=fresh_enough,
        market_types=market_types,
    )


def _fixture_availability_coverage(
    fixture_id: str,
    *,
    has_lineup: bool = True,
    has_injury: bool = True,
    lineup_fresh_enough: bool = True,
    injury_fresh_enough: bool = True,
    lineup_lag_hours: float = 2.0,
    injury_lag_hours: float = 2.0,
) -> FixtureAvailabilityCoverage:
    return FixtureAvailabilityCoverage(
        fixture_id=fixture_id,
        competition_id="EPL" if fixture_id.startswith("fix_epl") else "JPN_J1",
        competition_name="Premier League" if fixture_id.startswith("fix_epl") else "J1 League",
        kickoff_time_utc=datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        availability_snapshot_count=1 if has_injury else 0,
        lineup_snapshot_count=1 if has_lineup else 0,
        latest_availability_snapshot_time_utc=(
            datetime(2026, 5, 6, 17, 0, tzinfo=UTC) if has_injury else None
        ),
        availability_snapshot_lag_hours=injury_lag_hours if has_injury else None,
        latest_lineup_snapshot_time_utc=(
            datetime(2026, 5, 6, 17, 0, tzinfo=UTC) if has_lineup else None
        ),
        lineup_snapshot_lag_hours=lineup_lag_hours if has_lineup else None,
        has_availability=has_injury,
        has_lineup=has_lineup,
        availability_fresh_enough=has_injury and injury_fresh_enough,
        lineup_fresh_enough=has_lineup and lineup_fresh_enough,
        fresh_enough=(has_injury and has_lineup and injury_fresh_enough and lineup_fresh_enough),
    )


def _sportmonks_lineup_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_10",
                "player": {"name": "Home Goalkeeper"},
                "type": "confirmed starting",
                "position": "Goalkeeper",
                "is_starter": True,
            },
            {
                "fixture_id": "fixture_123",
                "team_id": "team_2",
                "player_id": "player_20",
                "player": {"name": "Away Forward"},
                "type": "expected lineup",
                "probability": 0.72,
            },
        ]
    }


def _provider_sync_workflow_template_record(
    *,
    template_name: str = "EPL odds smoke",
    fixture_sync: object = None,
    odds_syncs: object = None,
    run_conflict_detection: bool = True,
    metadata_json: object = None,
    archived_at: object = None,
    archived_by: object = None,
    archive_reason: object = None,
) -> ProviderSyncWorkflowTemplateRecord:
    return ProviderSyncWorkflowTemplateRecord(
        provider_sync_workflow_template_id=701,
        template_name=template_name,
        description="dry-run template",
        dry_run=True,
        fixture_sync=(
            fixture_sync
            if isinstance(fixture_sync, dict)
            else {
                "provider_competition_id": "PL",
                "season": "2025",
                "canonical_competition_id": "EPL",
            }
        ),
        odds_syncs=(
            odds_syncs
            if isinstance(odds_syncs, list)
            else [
                {
                    "sport_key": "soccer_epl",
                    "provider_event_id": "event-1",
                    "canonical_fixture_id": "fd_fixture_1",
                }
            ]
        ),
        availability_syncs=[],
        run_conflict_detection=run_conflict_detection,
        conflict_observation_lookback_hours=168,
        conflict_limit=1000,
        created_by="admin_api",
        created_at=datetime(2026, 5, 8, 4, 0, tzinfo=UTC),
        updated_at=datetime(2026, 5, 8, 4, 1, tzinfo=UTC),
        archived_at=archived_at if isinstance(archived_at, datetime) else None,
        archived_by=archived_by if isinstance(archived_by, str) else None,
        archive_reason=archive_reason if isinstance(archive_reason, str) else None,
        metadata_json=(
            metadata_json if isinstance(metadata_json, dict) else {"source": "unit_test"}
        ),
    )


def _provider_sync_workflow_approval_record(
    *,
    provider_sync_workflow_template_id: object = 701,
    provider_sync_workflow_run_id: object = 501,
    approval_note: object = "reviewed IDs",
    request_payload_json: object = None,
) -> ProviderSyncWorkflowApprovalRecord:
    return ProviderSyncWorkflowApprovalRecord(
        provider_sync_workflow_approval_id=801,
        approval_type="provider_sync_workflow_dry_run",
        approval_status="approved",
        provider_sync_workflow_template_id=(
            provider_sync_workflow_template_id
            if isinstance(provider_sync_workflow_template_id, int)
            else None
        ),
        provider_sync_workflow_run_id=(
            provider_sync_workflow_run_id
            if isinstance(provider_sync_workflow_run_id, int)
            else None
        ),
        approved_by="admin_api",
        approved_at=datetime(2026, 5, 8, 5, 1, tzinfo=UTC),
        approval_note=approval_note if isinstance(approval_note, str) else None,
        request_payload_json=(
            request_payload_json
            if isinstance(request_payload_json, dict)
            else {"dry_run": True, "operator_approved": True}
        ),
        metadata_json={"source": "unit_test"},
    )


def _provider_authorization_review_record() -> ProviderAuthorizationReviewRecord:
    return ProviderAuthorizationReviewRecord(
        provider_authorization_review_id=901,
        provider_name="api-football",
        review_reference="manual-2026-05-08",
        review_status="research_only",
        reviewed_by="ops-reviewer",
        reviewed_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        terms_url="https://www.api-football.com/terms",
        terms_version_hash=None,
        allowed_use="fixture_result_fallback_research_dry_run",
        commercial_use_allowed=False,
        retention_allowed=False,
        historical_data_allowed=False,
        redistribution_allowed=False,
        rate_limit="free_plan_provider_defined",
        next_review_due_at=datetime(2026, 11, 4, tzinfo=UTC),
        evidence_json={"source": "unit_test"},
        notes="Free plan is research-only until retention terms are approved.",
        created_at=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
    )


def _patch_recommendation_focus_repository(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: list[RecommendationCandidate],
) -> None:
    class FakePostgresRecommendationRepository:
        def __init__(self, database: object) -> None:
            self.database = database

        def list_candidates(self, *, options: object) -> list[RecommendationCandidate]:
            return list(candidates)

    monkeypatch.setattr(
        router_module,
        "PostgresRecommendationRepository",
        FakePostgresRecommendationRepository,
    )


def _recommendation_selection(
    *,
    pass_type: str,
    hit_probability: float,
    total_score: float,
) -> RecommendationSelection:
    return RecommendationSelection(
        pass_type=pass_type,
        mode="single",
        selected_candidates=[
            ScoredRecommendationCandidate(
                candidate=RecommendationCandidate(
                    fixture_id="fix_a",
                    market_type="1x2",
                    outcome="home_win",
                    probability=0.62,
                    decimal_odds=1.8,
                    data_quality_score=88,
                    upset_protection_score=0.64,
                    model_version="poisson-m1.0.0",
                    prediction_snapshot_id=31,
                    prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                    kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
                ),
                score=total_score,
            )
        ],
        evaluation=ParlayEvaluation(
            pass_type=pass_type,
            unit_stake=2,
            total_atomic_bets=1,
            total_stake=2,
            hit_probability=hit_probability,
            expected_payout=6.2,
            expected_value=0.4,
            roi=0.2,
            risk_score=0.35,
            risk_level="medium",
            explanation_json={"budget": {"max_budget": 20}},
        ),
        total_score=total_score,
        candidate_count=2,
        excluded_candidate_count=0,
        explanation_json={"strategy": "accuracy_first"},
    )


def _recommendation_selection_for_fixture_ids(
    fixture_ids: list[str],
    *,
    pass_type: str,
) -> RecommendationSelection:
    selected_candidates = [
        ScoredRecommendationCandidate(
            candidate=RecommendationCandidate(
                fixture_id=fixture_id,
                market_type="1x2",
                outcome="home_win",
                probability=0.68 - index * 0.02,
                decimal_odds=1.78 + index * 0.03,
                data_quality_score=94 - index,
                model_confidence_score=0.82,
                calibration_score=0.80,
                model_version="poisson-v3.1-baseline",
                prediction_snapshot_id=100 + index,
                prediction_time_utc=datetime(2026, 5, 12, 0, tzinfo=UTC),
                kickoff_time_utc=datetime(2026, 5, 13, 12, tzinfo=UTC),
            ),
            score=0.80 - index * 0.02,
        )
        for index, fixture_id in enumerate(fixture_ids, start=1)
    ]
    return RecommendationSelection(
        pass_type=pass_type,
        mode="single",
        selected_candidates=selected_candidates,
        evaluation=ParlayEvaluation(
            pass_type=pass_type,
            unit_stake=2,
            total_atomic_bets=1,
            total_stake=2,
            hit_probability=0.18,
            expected_payout=42.0,
            expected_value=3.5,
            roi=1.75,
            risk_score=0.58,
            risk_level="medium",
            explanation_json={"budget": {"max_budget": 20, "within_budget": True}},
        ),
        total_score=0.78,
        candidate_count=len(fixture_ids),
        excluded_candidate_count=0,
        explanation_json={"strategy": "accuracy_first"},
    )


def _sportmonks_injury_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "fixture_id": "fixture_123",
                "team_id": "team_1",
                "player_id": "player_11",
                "player": {"name": "Home Defender"},
                "type": "injury",
                "reason": "Knee",
            }
        ]
    }


def _the_odds_api_event_payload() -> dict[str, object]:
    return {
        "id": "event_123",
        "sport_key": "soccer_epl",
        "sport_title": "EPL",
        "commence_time": "2026-05-06T19:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": "2026-05-06T07:58:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": "2026-05-06T08:00:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Liverpool", "price": 3.4},
                        ],
                    },
                    {
                        "key": "spreads",
                        "last_update": "2026-05-06T08:01:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.91, "point": -0.5},
                            {"name": "Liverpool", "price": 1.93, "point": 0.5},
                        ],
                    },
                ],
            }
        ],
    }
