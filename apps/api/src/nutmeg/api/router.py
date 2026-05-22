from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, Header, HTTPException, Path, Query, Request

from nutmeg.accuracy.dixon_coles_job import DixonColesTrainingBacktestJobOptions
from nutmeg.accuracy.factory import build_accuracy_repository
from nutmeg.accuracy.job_repository import (
    AccuracyJobRunRecord,
    PostgresAccuracyJobRunRepository,
)
from nutmeg.accuracy.jobs import run_audited_accuracy_job
from nutmeg.accuracy.mock_repository import ACTIVE_MODEL_VERSION
from nutmeg.accuracy.weekly_training import WeeklyDixonColesTrainingPipelineOptions
from nutmeg.api.auth import require_admin_token
from nutmeg.api.contract import (
    accuracy_summary_response,
    fixture_prediction_response,
    list_fixture_items,
    parlay_recommendations,
    provider_governance_response,
    score_grid_response,
    upset_list_items,
)
from nutmeg.api.schemas import (
    AccuracyJobRunListResponse,
    AccuracyJobRunRecordPayload,
    AccuracyJobRunRequest,
    AccuracyJobRunResponse,
    AccuracySummaryResponse,
    FixtureListResponse,
    FixturePredictionResponse,
    HealthResponse,
    ParlayEvaluateRequest,
    ParlayGenerateRequest,
    ParlayGenerateResponse,
    ParlayRecommendRequest,
    ParlayRecommendResponse,
    ParlaySettlementRequest,
    ParlaySettlementResponse,
    PredictionJobRunListResponse,
    PredictionJobRunRecordPayload,
    PredictionJobRunRequest,
    PredictionJobRunResponse,
    PrematchWorkflowRunListResponse,
    PrematchWorkflowRunRecordPayload,
    PrematchWorkflowRunRequest,
    PrematchWorkflowRunResponse,
    ProviderApiFootballCompetitionDiscoveryRequest,
    ProviderApiFootballCompetitionDiscoveryResponse,
    ProviderApiFootballFixtureMappingBootstrapRequest,
    ProviderApiKeyChecklistPayload,
    ProviderAuthorizationReviewListResponse,
    ProviderAuthorizationReviewRecordPayload,
    ProviderAuthorizationReviewRequest,
    ProviderAuthorizationReviewResponse,
    ProviderAvailabilityWriteSummaryPayload,
    ProviderCanonicalWriteSummaryPayload,
    ProviderConflictEvaluationRequest,
    ProviderConflictEvaluationResponse,
    ProviderConflictEventListResponse,
    ProviderConflictEventRecordPayload,
    ProviderConflictResolutionRequest,
    ProviderConflictResolutionResponse,
    ProviderEntityMappingListResponse,
    ProviderEventOddsSyncRequest,
    ProviderEventOddsSyncResponse,
    ProviderFixtureAvailabilitySyncRequest,
    ProviderFixtureAvailabilitySyncResponse,
    ProviderFixtureMappingBootstrapResponse,
    ProviderFixtureSyncRequest,
    ProviderFixtureSyncResponse,
    ProviderGovernanceResponse,
    ProviderMappedEventOddsSyncRequest,
    ProviderMappedEventOddsSyncResponse,
    ProviderMappingReviewRequest,
    ProviderMappingReviewResponse,
    ProviderMappingReviewRunListResponse,
    ProviderMappingReviewRunRecordPayload,
    ProviderOddsCoverageGapResponse,
    ProviderOddsCoverageResponse,
    ProviderOddsWriteSummaryPayload,
    ProviderOnboardingAssessmentListItem,
    ProviderOnboardingAssessmentListResponse,
    ProviderOnboardingAssessmentRecordPayload,
    ProviderOnboardingAssessmentRequest,
    ProviderOnboardingAssessmentResponse,
    ProviderOpsAuditEventListResponse,
    ProviderOpsAuditEventRecordPayload,
    ProviderOpsAuditEventRequest,
    ProviderOpsAuditEventResponse,
    ProviderOpsRunHistoryListResponse,
    ProviderOpsRunHistoryRecordPayload,
    ProviderOpsRunHistoryRequest,
    ProviderOpsRunHistoryResponse,
    ProviderRawPayloadSummary,
    ProviderRuntimeCredentialsResponse,
    ProviderRuntimeIncidentReportListResponse,
    ProviderRuntimeIncidentReportRecordPayload,
    ProviderRuntimeIncidentReportRequest,
    ProviderRuntimeIncidentReportResponse,
    ProviderRuntimeIncidentRetentionRequest,
    ProviderRuntimeIncidentRetentionResponse,
    ProviderRuntimeIncidentStatus,
    ProviderRuntimeIncidentStatusUpdateRequest,
    ProviderRuntimeIncidentStatusUpdateResponse,
    ProviderRuntimeIncidentSummaryPayload,
    ProviderRuntimeIncidentTrendBucketPayload,
    ProviderRuntimeMonitoringAlertPayload,
    ProviderRuntimeMonitoringResponse,
    ProviderRuntimeMonitoringSnapshotRecordPayload,
    ProviderRuntimeMonitoringSnapshotRequest,
    ProviderRuntimeMonitoringSummaryPayload,
    ProviderRuntimeMonitoringThresholdPayload,
    ProviderRuntimeProbesResponse,
    ProviderSportMonksCompetitionDiscoveryRequest,
    ProviderSportMonksCompetitionDiscoveryResponse,
    ProviderSportMonksFallbackOddsProbeRequest,
    ProviderSportMonksFallbackOddsProbeResponse,
    ProviderSportMonksFixtureMappingBackfillRequest,
    ProviderSportMonksFixtureMappingBackfillResponse,
    ProviderSportMonksFixtureMappingBootstrapRequest,
    ProviderSyncRunPayload,
    ProviderSyncWorkflowApprovalListResponse,
    ProviderSyncWorkflowApprovalRecordPayload,
    ProviderSyncWorkflowPreflightResponse,
    ProviderSyncWorkflowRunDetailResponse,
    ProviderSyncWorkflowRunListResponse,
    ProviderSyncWorkflowRunRecordPayload,
    ProviderSyncWorkflowRunRequest,
    ProviderSyncWorkflowRunResponse,
    ProviderSyncWorkflowTemplateArchiveRequest,
    ProviderSyncWorkflowTemplateCreateRequest,
    ProviderSyncWorkflowTemplateListResponse,
    ProviderSyncWorkflowTemplateRecordPayload,
    ProviderSyncWorkflowTemplateResponse,
    ProviderSyncWorkflowTemplateUpdateRequest,
    ProviderTheOddsApiFixtureMappingBootstrapRequest,
    RecommendationBenchmarkHistoryResponse,
    RecommendationBenchmarkStrategyPairHistoryResponse,
    RecommendationChainIntegrityRequest,
    RecommendationChainIntegrityResponse,
    RecommendationCoreReplayRequest,
    RecommendationCoreReplayResponse,
    RecommendationEvaluationRunRequest,
    RecommendationEvaluationRunResponse,
    RecommendationGenerateRequest,
    RecommendationGenerateResponse,
    RecommendationGlobalPlannerRequest,
    RecommendationGlobalPlannerResponse,
    RecommendationLifecycleMutationResponse,
    RecommendationLifecycleResponse,
    RecommendationLockLegRequest,
    RecommendationPrematchChangeReportRequest,
    RecommendationPrematchChangeReportResponse,
    RecommendationPrematchPipelineRequest,
    RecommendationPrematchPipelineResponse,
    RecommendationProviderIncidentMappingRequest,
    RecommendationProviderIncidentMappingResponse,
    RecommendationRecomputeTriggerRequest,
    RecommendationRecomputeTriggerResponse,
    RecommendationReleaseLegRequest,
    RecommendationSourceStatusSyncRequest,
    RecommendationSourceStatusSyncResponse,
    RecommendationStatusTransitionRequest,
    RecommendationStrategyGovernanceOverviewResponse,
    RecommendationStrategyReviewRequest,
    RecommendationStrategyReviewResponse,
    RecommendationSuccessorRecomputeRequest,
    RecommendationSuccessorRecomputeResponse,
    ScoreGridResponse,
    UpsetListResponse,
)
from nutmeg.competition import load_competition_configs
from nutmeg.config import Settings
from nutmeg.database import DatabaseReadError, PsycopgSyncDatabaseExecutor
from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.parlay import (
    MarketPredictionParlayGenerationOptions,
    PostgresParlayRecommendationRepository,
    evaluate_parlay,
    parlay_recommendation_input_from_payload,
    run_market_prediction_parlay_generation,
)
from nutmeg.predictions import build_mock_prediction_snapshot_with_context
from nutmeg.predictions.job_repository import (
    PostgresPredictionJobRunRepository,
    PredictionJobRunRecord,
)
from nutmeg.predictions.jobs import run_audited_prediction_job
from nutmeg.predictions.workflow import (
    PostgresPrematchWorkflowRunRepository,
    PrematchWorkflowOptions,
    PrematchWorkflowRunRecord,
    run_audited_prematch_workflow,
)
from nutmeg.providers.api_football import ApiFootballAdapterError
from nutmeg.providers.api_football.discovery import (
    discover_api_football_competition_season,
)
from nutmeg.providers.availability_coverage import (
    FixtureAvailabilityCoverage,
    PostgresAvailabilityCoverageRepository,
)
from nutmeg.providers.availability_sync import (
    SportMonksFixtureAvailabilitySyncResult,
    run_sportmonks_fixture_availability_sync,
)
from nutmeg.providers.conflicts import (
    PostgresProviderConflictEventRepository,
    PostgresProviderObservationRepository,
    ProviderConflictEventRecord,
    ProviderConflictStatus,
    detect_provider_observation_conflicts,
    evaluate_mapping_review_conflicts,
    evaluate_provider_conflict_events,
)
from nutmeg.providers.fallback_odds_probe import run_sportmonks_fallback_odds_probe
from nutmeg.providers.fixture_mapping_bootstrap import (
    run_api_football_fixture_mapping_bootstrap,
    run_sportmonks_fixture_mapping_bootstrap,
    run_the_odds_api_fixture_mapping_bootstrap,
)
from nutmeg.providers.football_data_org import FootballDataOrgAdapterError
from nutmeg.providers.governance.authorization_repository import (
    PostgresProviderAuthorizationRepository,
)
from nutmeg.providers.governance.authorization_reviews import (
    PostgresProviderAuthorizationReviewRepository,
    ProviderAuthorizationReviewInput,
    ProviderAuthorizationReviewRecord,
)
from nutmeg.providers.governance.onboarding import (
    CompetitionOnboardingAssessment,
    CompetitionOnboardingInput,
    assess_competition_onboarding,
)
from nutmeg.providers.governance.onboarding_repository import (
    PostgresCompetitionOnboardingAssessmentRepository,
)
from nutmeg.providers.governance.ops_audit import (
    PostgresProviderOpsAuditEventRepository,
    ProviderOpsAuditEventInput,
    ProviderOpsAuditEventRecord,
)
from nutmeg.providers.governance.run_history import (
    PostgresProviderOpsRunHistoryRepository,
    ProviderOpsRunHistoryInput,
    ProviderOpsRunHistoryRecord,
)
from nutmeg.providers.live_probes import build_provider_runtime_probe_response
from nutmeg.providers.mapped_odds_sync import (
    run_the_odds_api_mapped_event_odds_sync,
)
from nutmeg.providers.mapping_repository import PostgresProviderEntityMappingRepository
from nutmeg.providers.mapping_review import (
    PostgresProviderMappingReviewRunRepository,
    ProviderMappingReviewOptions,
    ProviderMappingReviewRunRecord,
    review_provider_entity_mappings,
)
from nutmeg.providers.mock import get_mock_fixture, list_mock_fixtures
from nutmeg.providers.odds_coverage import (
    CompetitionOddsCoverageReport,
    FixtureOddsCoverage,
    PostgresOddsCoverageRepository,
)
from nutmeg.providers.odds_sync import (
    TheOddsApiEventOddsSyncResult,
    run_the_odds_api_event_odds_sync,
)
from nutmeg.providers.runtime_credentials import (
    build_provider_api_key_checklist_response,
    build_provider_runtime_credential_response,
)
from nutmeg.providers.runtime_monitoring import (
    PostgresProviderRuntimeMonitoringRepository,
    ProviderRuntimeAlertLevel,
    ProviderRuntimeIncidentNotificationStatus,
    ProviderRuntimeIncidentReportInput,
    ProviderRuntimeIncidentReportRecord,
    ProviderRuntimeIncidentSummary,
    ProviderRuntimeMonitoringAlert,
    ProviderRuntimeMonitoringThresholds,
    ProviderRuntimeSnapshotInput,
    ProviderRuntimeSnapshotRecord,
    build_provider_runtime_incident_notification_decision,
    build_provider_runtime_monitoring_alerts,
    provider_runtime_alert_level,
    provider_runtime_snapshot_inputs_from_probe_response,
)
from nutmeg.providers.sportmonks import SportMonksAdapterError
from nutmeg.providers.sportmonks.discovery import (
    discover_sportmonks_competition_season,
)
from nutmeg.providers.sportmonks_mapping_backfill import (
    run_sportmonks_fixture_mapping_backfill,
)
from nutmeg.providers.sync import (
    FootballDataFixtureSyncResult,
    run_football_data_fixture_sync,
)
from nutmeg.providers.the_odds_api import TheOddsApiAdapterError
from nutmeg.providers.workflow import (
    FootballDataFixtureSyncTask,
    PostgresProviderSyncWorkflowRunRepository,
    ProviderSyncWorkflowOptions,
    ProviderSyncWorkflowRunRecord,
    SportMonksFixtureAvailabilitySyncTask,
    TheOddsApiEventOddsSyncTask,
    run_audited_provider_sync_workflow,
)
from nutmeg.providers.workflow_approvals import (
    PostgresProviderSyncWorkflowApprovalRepository,
    ProviderSyncWorkflowApprovalRecord,
)
from nutmeg.providers.workflow_templates import (
    PostgresProviderSyncWorkflowTemplateRepository,
    ProviderSyncWorkflowTemplateDatabase,
    ProviderSyncWorkflowTemplateRecord,
    preflight_provider_sync_workflow,
)
from nutmeg.recommendations import (
    PostgresRecommendationBenchmarkRunRepository,
    PostgresRecommendationBenchmarkStrategyPairRunRepository,
    PostgresRecommendationChainIntegrityRepository,
    PostgresRecommendationEvaluationRepository,
    PostgresRecommendationRepository,
    PostgresRecommendationStrategyGovernanceRepository,
    RecommendationAnswer,
    RecommendationCandidateQueryOptions,
    RecommendationChainIntegrityOptions,
    RecommendationCoreReplayOptions,
    RecommendationEvaluationOptions,
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    RecommendationGlobalPlannerOptions,
    RecommendationGlobalPlannerResult,
    RecommendationGlobalPlanOption,
    RecommendationPrematchChangeReportOptions,
    RecommendationPrematchPipelineOptions,
    RecommendationProviderIncidentMappingOptions,
    RecommendationRecomputeTriggerOptions,
    RecommendationSourceStatusSyncOptions,
    RecommendationStrategyReviewOptions,
    RecommendationSuccessorRecomputeOptions,
    build_candidate_recommendation_answer,
    build_mock_recommendation_strategy_governance_overview,
    build_public_recommendation_answer_set,
    build_recommendation_answer,
    build_recommendation_strategy_governance_overview,
    build_single_focus_policy_config,
    build_upset_focus_policy_config,
    rank_candidates,
    run_recommendation_chain_integrity_check,
    run_recommendation_core_replay,
    run_recommendation_evaluation,
    run_recommendation_generation,
    run_recommendation_global_planner,
    run_recommendation_prematch_change_report,
    run_recommendation_prematch_pipeline,
    run_recommendation_provider_incident_mapping,
    run_recommendation_recompute_trigger,
    run_recommendation_source_status_sync,
    run_recommendation_strategy_review,
    run_recommendation_successor_recompute,
    select_recommendation_strategy_from_governance,
)
from nutmeg.recommendations.lifecycle import RecommendationLifecycleStatus
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationMode,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)

api_router = APIRouter()

type RecommendationGenerationStrategyParam = Literal[
    "auto",
    "accuracy_first",
    "value_first",
    "upset_protection",
    "budget_constrained",
]


@dataclass(frozen=True)
class ResolvedRecommendationLocks:
    candidates: tuple[RecommendationCandidate, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RecommendationLockedCandidateSpec:
    fixture_id: str
    market_type: str | None = None
    outcome: str | None = None


@api_router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="nutmeg-api")


@api_router.get("/providers/status", response_model=ProviderGovernanceResponse)
def provider_status(request: Request) -> ProviderGovernanceResponse:
    settings = request.app.state.settings
    persisted_competition_readiness = None
    provider_authorizations = None
    stale = False
    fallback_used = False
    if settings.provider_governance_repository == "postgres":
        try:
            persisted_competition_readiness = [
                record.assessment
                for record in _build_onboarding_assessment_repository(settings).list_latest(
                    limit=100
                )
            ]
            provider_authorizations = _build_provider_authorization_repository(
                settings
            ).list_authorizations()
        except (DatabaseReadError, RuntimeError):
            stale = True
            fallback_used = True
    return provider_governance_response(
        persisted_competition_readiness=persisted_competition_readiness,
        provider_authorizations=provider_authorizations,
        stale=stale,
        fallback_used=fallback_used,
    )


@api_router.get(
    "/providers/authorizations/reviews",
    response_model=ProviderAuthorizationReviewListResponse,
)
def list_provider_authorization_reviews(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderAuthorizationReviewListResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        records = _build_provider_authorization_review_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider authorization review repository unavailable",
        ) from exc
    return ProviderAuthorizationReviewListResponse(
        items=[_provider_authorization_review_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/authorizations/reviews",
    response_model=ProviderAuthorizationReviewResponse,
)
def record_provider_authorization_review(
    request: Request,
    payload: ProviderAuthorizationReviewRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderAuthorizationReviewResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        record = _build_provider_authorization_review_repository(settings).record_review(
            _provider_authorization_review_input(payload)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider authorization review repository unavailable",
        ) from exc
    return ProviderAuthorizationReviewResponse(
        item=_provider_authorization_review_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/ops/provider-audit/events",
    response_model=ProviderOpsAuditEventListResponse,
)
def list_provider_ops_audit_events(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderOpsAuditEventListResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        records = _build_provider_ops_audit_event_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider ops audit repository unavailable",
        ) from exc
    return ProviderOpsAuditEventListResponse(
        items=[_provider_ops_audit_event_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/ops/provider-audit/events",
    response_model=ProviderOpsAuditEventResponse,
)
def record_provider_ops_audit_event(
    request: Request,
    payload: ProviderOpsAuditEventRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
    x_nutmeg_operator: str | None = Header(
        default=None,
        alias="X-Nutmeg-Operator",
    ),
) -> ProviderOpsAuditEventResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        record = _build_provider_ops_audit_event_repository(settings).record_event(
            _provider_ops_audit_event_input(payload, x_nutmeg_operator)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider ops audit repository unavailable",
        ) from exc
    return ProviderOpsAuditEventResponse(
        item=_provider_ops_audit_event_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/ops/provider-runs",
    response_model=ProviderOpsRunHistoryListResponse,
)
def list_provider_ops_run_history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderOpsRunHistoryListResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        records = _build_provider_ops_run_history_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider ops run history repository unavailable",
        ) from exc
    return ProviderOpsRunHistoryListResponse(
        items=[_provider_ops_run_history_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/ops/provider-runs",
    response_model=ProviderOpsRunHistoryResponse,
)
def record_provider_ops_run_history(
    request: Request,
    payload: ProviderOpsRunHistoryRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
    x_nutmeg_operator: str | None = Header(
        default=None,
        alias="X-Nutmeg-Operator",
    ),
) -> ProviderOpsRunHistoryResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        record = _build_provider_ops_run_history_repository(settings).record_run(
            _provider_ops_run_history_input(payload, x_nutmeg_operator)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider ops run history repository unavailable",
        ) from exc
    return ProviderOpsRunHistoryResponse(
        item=_provider_ops_run_history_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/providers/runtime/credentials",
    response_model=ProviderRuntimeCredentialsResponse,
)
def provider_runtime_credentials(
    request: Request,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeCredentialsResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    return ProviderRuntimeCredentialsResponse(
        **build_provider_runtime_credential_response(settings).model_dump()
    )


@api_router.get(
    "/providers/runtime/api-key-checklist",
    response_model=ProviderApiKeyChecklistPayload,
)
def provider_api_key_checklist(
    request: Request,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderApiKeyChecklistPayload:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    return ProviderApiKeyChecklistPayload(
        **build_provider_api_key_checklist_response(settings).model_dump()
    )


@api_router.get(
    "/providers/runtime/probes",
    response_model=ProviderRuntimeProbesResponse,
)
def provider_runtime_probes(
    request: Request,
    live: bool = Query(default=False),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeProbesResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    return ProviderRuntimeProbesResponse(
        **build_provider_runtime_probe_response(settings, live=live).model_dump()
    )


@api_router.get(
    "/providers/runtime/monitoring",
    response_model=ProviderRuntimeMonitoringResponse,
)
def provider_runtime_monitoring(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeMonitoringResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        records = _build_provider_runtime_monitoring_repository(settings).list_latest_by_provider(
            limit=limit
        )
    except (DatabaseReadError, RuntimeError):
        return _provider_runtime_monitoring_fallback_response(
            settings,
            stale=True,
            fallback_used=True,
        )
    if not records:
        return _provider_runtime_monitoring_fallback_response(
            settings,
            stale=False,
            fallback_used=True,
        )
    return _provider_runtime_monitoring_response_from_records(records, settings=settings)


@api_router.post(
    "/providers/runtime/monitoring/snapshot",
    response_model=ProviderRuntimeMonitoringResponse,
)
def record_provider_runtime_monitoring_snapshot(
    request: Request,
    payload: ProviderRuntimeMonitoringSnapshotRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeMonitoringResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    probe_response = build_provider_runtime_probe_response(
        settings,
        live=payload.live_probe,
    )
    snapshots = provider_runtime_snapshot_inputs_from_probe_response(probe_response)
    try:
        records = _build_provider_runtime_monitoring_repository(settings).record_snapshots(
            snapshots
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime monitoring repository unavailable",
        ) from exc
    return _provider_runtime_monitoring_response_from_records(
        records,
        settings=settings,
        generated_at_utc=probe_response.generated_at_utc,
    )


@api_router.get(
    "/providers/runtime/monitoring/incidents",
    response_model=ProviderRuntimeIncidentReportListResponse,
)
def list_provider_runtime_incident_reports(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    incident_status: ProviderRuntimeIncidentStatus | None = None,
    alert_level: ProviderRuntimeAlertLevel | None = None,
    notification_status: ProviderRuntimeIncidentNotificationStatus | None = None,
    source: str | None = Query(default=None, min_length=1, max_length=120),
    lookback_days: int = Query(default=30, ge=1, le=3650),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeIncidentReportListResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    repository = _build_provider_runtime_monitoring_repository(settings)
    try:
        reports = repository.list_incident_reports(
            limit=limit,
            offset=offset,
            incident_status=incident_status,
            alert_level=alert_level,
            notification_status=notification_status,
            source=source,
        )
        total_count = repository.count_incident_reports(
            incident_status=incident_status,
            alert_level=alert_level,
            notification_status=notification_status,
            source=source,
        )
        summary = repository.summarize_incident_reports(lookback_days=lookback_days)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime incident repository unavailable",
        ) from exc
    return ProviderRuntimeIncidentReportListResponse(
        items=[_provider_runtime_incident_report_payload(report) for report in reports],
        summary=_provider_runtime_incident_summary_payload(summary),
        limit=limit,
        offset=offset,
        total_count=total_count,
        has_more=offset + len(reports) < total_count,
        stale=False,
        fallback_used=False,
    )


@api_router.patch(
    "/providers/runtime/monitoring/incidents/{incident_report_id}/status",
    response_model=ProviderRuntimeIncidentStatusUpdateResponse,
)
def update_provider_runtime_incident_status(
    request: Request,
    incident_report_id: int,
    payload: ProviderRuntimeIncidentStatusUpdateRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
    x_nutmeg_operator: str | None = Header(
        default=None,
        alias="X-Nutmeg-Operator",
    ),
) -> ProviderRuntimeIncidentStatusUpdateResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    updated_by = _safe_operator_name(payload.updated_by or x_nutmeg_operator)
    try:
        report = _build_provider_runtime_monitoring_repository(settings).update_incident_status(
            provider_runtime_incident_report_id=incident_report_id,
            incident_status=payload.incident_status,
            updated_by=updated_by or "nutmeg-ops",
            resolution_note=payload.resolution_note,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail="provider runtime incident report not found",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime incident repository unavailable",
        ) from exc
    return ProviderRuntimeIncidentStatusUpdateResponse(
        item=_provider_runtime_incident_report_payload(report),
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/runtime/monitoring/incidents/retention",
    response_model=ProviderRuntimeIncidentRetentionResponse,
)
def prune_provider_runtime_incident_reports(
    request: Request,
    payload: ProviderRuntimeIncidentRetentionRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderRuntimeIncidentRetentionResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    retention_days = payload.retention_days or settings.provider_runtime_incident_retention_days
    try:
        deleted_count = _build_provider_runtime_monitoring_repository(
            settings
        ).prune_incident_reports(retention_days=retention_days)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime incident repository unavailable",
        ) from exc
    return ProviderRuntimeIncidentRetentionResponse(
        deleted_count=deleted_count,
        retention_days=retention_days,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/runtime/monitoring/incidents",
    response_model=ProviderRuntimeIncidentReportResponse,
)
def record_provider_runtime_incident_report(
    request: Request,
    payload: ProviderRuntimeIncidentReportRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
    x_nutmeg_operator: str | None = Header(
        default=None,
        alias="X-Nutmeg-Operator",
    ),
) -> ProviderRuntimeIncidentReportResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    repository = _build_provider_runtime_monitoring_repository(settings)
    try:
        records = repository.list_latest_by_provider(limit=100)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime monitoring repository unavailable",
        ) from exc
    if not records:
        raise HTTPException(
            status_code=400,
            detail="no provider runtime monitoring snapshots available",
        )
    monitoring = _provider_runtime_monitoring_response_from_records(
        records,
        settings=settings,
    )
    if not _should_record_runtime_incident(
        monitoring.alert_level,
        payload.record_when_alert_level,
    ):
        return ProviderRuntimeIncidentReportResponse(
            recorded=False,
            item=None,
            monitoring=monitoring,
            stale=False,
            fallback_used=False,
        )
    try:
        report = repository.record_incident_report(
            _provider_runtime_incident_report_input(
                payload,
                monitoring,
                operator_header=x_nutmeg_operator,
            )
        )
        notification_decision = build_provider_runtime_incident_notification_decision(
            report,
            enabled=(settings.provider_runtime_incident_notification_enabled),
            adapter=settings.provider_runtime_incident_notification_adapter,
            dry_run=settings.provider_runtime_incident_notification_dry_run,
            destination_configured=(
                settings.provider_runtime_incident_notification_adapter == "provider_ops"
                or bool(settings.provider_runtime_incident_notification_webhook_url)
            ),
            operator=(
                _safe_operator_name(x_nutmeg_operator)
                or report.created_by
                or "provider-runtime-monitor"
            ),
        )
        report = repository.update_incident_notification(
            provider_runtime_incident_report_id=(report.provider_runtime_incident_report_id),
            notification_status=notification_decision.notification_status,
            notification_payload_json=(notification_decision.notification_payload_json),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail="provider runtime incident report not found",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider runtime incident repository unavailable",
        ) from exc
    return ProviderRuntimeIncidentReportResponse(
        recorded=True,
        item=_provider_runtime_incident_report_payload(report),
        monitoring=monitoring,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/api-football/discovery/competitions",
    response_model=ProviderApiFootballCompetitionDiscoveryResponse,
)
def discover_api_football_competitions(
    request: Request,
    payload: ProviderApiFootballCompetitionDiscoveryRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderApiFootballCompetitionDiscoveryResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = discover_api_football_competition_season(
            settings,
            target_competition_name=payload.target_competition_name,
            target_country_name=payload.target_country_name,
            target_season=payload.target_season,
            max_competition_candidates=payload.max_competition_candidates,
            max_season_candidates=payload.max_season_candidates,
            min_competition_score=payload.min_competition_score,
        )
    except ApiFootballAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="API-Football provider unavailable",
        ) from exc
    return ProviderApiFootballCompetitionDiscoveryResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/sportmonks/discovery/competitions",
    response_model=ProviderSportMonksCompetitionDiscoveryResponse,
)
def discover_sportmonks_competitions(
    request: Request,
    payload: ProviderSportMonksCompetitionDiscoveryRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSportMonksCompetitionDiscoveryResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = discover_sportmonks_competition_season(
            settings,
            target_competition_name=payload.target_competition_name,
            target_country_name=payload.target_country_name,
            target_season=payload.target_season,
            max_competition_candidates=payload.max_competition_candidates,
            max_season_candidates=payload.max_season_candidates,
            min_competition_score=payload.min_competition_score,
        )
    except SportMonksAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks provider unavailable",
        ) from exc
    return ProviderSportMonksCompetitionDiscoveryResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.get("/providers/odds/coverage", response_model=ProviderOddsCoverageResponse)
def provider_odds_coverage(
    request: Request,
    competition_id: str = Query(min_length=1),
    window_days: int = Query(default=90, ge=1, le=730),
    max_snapshot_lag_hours: int = Query(default=24, ge=1, le=168),
    as_of_time_utc: str | None = Query(default=None),
) -> ProviderOddsCoverageResponse:
    settings = request.app.state.settings
    try:
        as_of_time = _parse_as_of_time(as_of_time_utc)
        report = _build_odds_coverage_repository(settings).build_competition_report(
            competition_id=competition_id,
            as_of_time_utc=as_of_time,
            window_days=window_days,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="odds coverage repository unavailable",
        ) from exc
    return ProviderOddsCoverageResponse(report=report, stale=False, fallback_used=False)


@api_router.get(
    "/providers/odds/gaps",
    response_model=ProviderOddsCoverageGapResponse,
)
def provider_odds_coverage_gaps(
    request: Request,
    competition_id: str = Query(min_length=1),
    provider: str = Query(default="the-odds-api", min_length=1),
    window_days: int = Query(default=90, ge=1, le=730),
    max_snapshot_lag_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=100, ge=1, le=500),
    as_of_time_utc: str | None = Query(default=None),
) -> ProviderOddsCoverageGapResponse:
    settings = request.app.state.settings
    try:
        as_of_time = _parse_as_of_time(as_of_time_utc)
        report = _build_odds_coverage_repository(settings).build_gap_report(
            competition_id=competition_id,
            provider=provider,
            as_of_time_utc=as_of_time,
            window_days=window_days,
            max_snapshot_lag_hours=max_snapshot_lag_hours,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="odds coverage gap repository unavailable",
        ) from exc
    return ProviderOddsCoverageGapResponse(
        report=report,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/odds/fallback-probe/sportmonks",
    response_model=ProviderSportMonksFallbackOddsProbeResponse,
)
def provider_sportmonks_fallback_odds_probe(
    request: Request,
    payload: ProviderSportMonksFallbackOddsProbeRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSportMonksFallbackOddsProbeResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = run_sportmonks_fallback_odds_probe(
            settings,
            competition_id=payload.competition_id,
            primary_provider=payload.primary_provider,
            window_days=payload.window_days,
            max_snapshot_lag_hours=payload.max_snapshot_lag_hours,
            limit=payload.limit,
            as_of_time_utc=_normalize_optional_as_of_time(payload.as_of_time_utc),
            live_provider_probe=payload.live_provider_probe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportMonksAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks fallback odds probe unavailable",
        ) from exc
    return ProviderSportMonksFallbackOddsProbeResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.get("/providers/mappings", response_model=ProviderEntityMappingListResponse)
def list_provider_entity_mappings(
    request: Request,
    provider: str | None = Query(default=None, min_length=1),
    entity_type: str | None = Query(default=None, min_length=1),
    canonical_entity_id: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> ProviderEntityMappingListResponse:
    settings = request.app.state.settings
    try:
        result = _build_provider_entity_mapping_repository(settings).list_mappings(
            provider=provider,
            entity_type=entity_type,
            canonical_entity_id=canonical_entity_id,
            limit=limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping repository unavailable",
        ) from exc
    return ProviderEntityMappingListResponse(
        items=result.items,
        summary=result.summary,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/mappings/bootstrap/the-odds-api-fixtures",
    response_model=ProviderFixtureMappingBootstrapResponse,
)
def bootstrap_the_odds_api_fixture_mappings(
    request: Request,
    payload: ProviderTheOddsApiFixtureMappingBootstrapRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderFixtureMappingBootstrapResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = run_the_odds_api_fixture_mapping_bootstrap(
            settings,
            provider_competition_id=payload.provider_competition_id,
            canonical_competition_id=payload.canonical_competition_id,
            season=payload.season,
            sport_key=payload.sport_key,
            regions=payload.regions,
            markets=payload.markets,
            bookmakers=payload.bookmakers,
            dry_run=payload.dry_run,
            kickoff_tolerance_minutes=payload.kickoff_tolerance_minutes,
            min_confidence=payload.min_confidence,
            max_provider_events=payload.max_provider_events,
        )
    except FootballDataOrgAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="football-data.org provider unavailable",
        ) from exc
    except TheOddsApiAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="The Odds API provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping bootstrap unavailable",
        ) from exc
    return ProviderFixtureMappingBootstrapResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/mappings/bootstrap/sportmonks-fixtures",
    response_model=ProviderFixtureMappingBootstrapResponse,
)
def bootstrap_sportmonks_fixture_mappings(
    request: Request,
    payload: ProviderSportMonksFixtureMappingBootstrapRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderFixtureMappingBootstrapResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = run_sportmonks_fixture_mapping_bootstrap(
            settings,
            source_provider_competition_id=payload.source_provider_competition_id,
            canonical_competition_id=payload.canonical_competition_id,
            source_season=payload.source_season,
            sportmonks_competition_id=payload.sportmonks_competition_id,
            sportmonks_season=payload.sportmonks_season,
            dry_run=payload.dry_run,
            kickoff_tolerance_minutes=payload.kickoff_tolerance_minutes,
            min_confidence=payload.min_confidence,
            max_provider_fixtures=payload.max_provider_fixtures,
        )
    except FootballDataOrgAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="football-data.org provider unavailable",
        ) from exc
    except SportMonksAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping bootstrap unavailable",
        ) from exc
    return ProviderFixtureMappingBootstrapResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/mappings/backfill/sportmonks-fixtures",
    response_model=ProviderSportMonksFixtureMappingBackfillResponse,
)
def backfill_sportmonks_fixture_mappings(
    request: Request,
    payload: ProviderSportMonksFixtureMappingBackfillRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSportMonksFixtureMappingBackfillResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = run_sportmonks_fixture_mapping_backfill(
            settings,
            source_provider_competition_id=payload.source_provider_competition_id,
            canonical_competition_id=payload.canonical_competition_id,
            source_season=payload.source_season,
            target_competition_name=payload.target_competition_name,
            target_country_name=payload.target_country_name,
            target_season=payload.target_season,
            max_competition_candidates=payload.max_competition_candidates,
            max_season_candidates=payload.max_season_candidates,
            min_competition_score=payload.min_competition_score,
            kickoff_tolerance_minutes=payload.kickoff_tolerance_minutes,
            min_confidence=payload.min_confidence,
            max_provider_fixtures=payload.max_provider_fixtures,
            dry_run=payload.dry_run,
        )
    except FootballDataOrgAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="football-data.org provider unavailable",
        ) from exc
    except SportMonksAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks mapping backfill unavailable",
        ) from exc
    return ProviderSportMonksFixtureMappingBackfillResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/mappings/bootstrap/api-football-fixtures",
    response_model=ProviderFixtureMappingBootstrapResponse,
)
def bootstrap_api_football_fixture_mappings(
    request: Request,
    payload: ProviderApiFootballFixtureMappingBootstrapRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderFixtureMappingBootstrapResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        result = run_api_football_fixture_mapping_bootstrap(
            settings,
            source_provider_competition_id=payload.source_provider_competition_id,
            canonical_competition_id=payload.canonical_competition_id,
            source_season=payload.source_season,
            api_football_league_id=payload.api_football_league_id,
            api_football_season=payload.api_football_season,
            dry_run=payload.dry_run,
            kickoff_tolerance_minutes=payload.kickoff_tolerance_minutes,
            min_confidence=payload.min_confidence,
            max_provider_fixtures=payload.max_provider_fixtures,
        )
    except FootballDataOrgAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="football-data.org provider unavailable",
        ) from exc
    except ApiFootballAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="API-Football provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping bootstrap unavailable",
        ) from exc
    return ProviderFixtureMappingBootstrapResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/mappings/review",
    response_model=ProviderMappingReviewResponse,
)
def review_provider_entity_mappings_request(
    request: Request,
    payload: ProviderMappingReviewRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderMappingReviewResponse:
    settings = request.app.state.settings
    if not payload.dry_run:
        require_admin_token(settings, x_nutmeg_admin_token)
    try:
        mappings = _build_provider_entity_mapping_repository(settings).list_review_candidates(
            provider=payload.provider,
            entity_type=payload.entity_type,
            canonical_entity_id=payload.canonical_entity_id,
            limit=payload.limit,
        )
        result = review_provider_entity_mappings(
            mappings,
            options=ProviderMappingReviewOptions(
                low_confidence_threshold=payload.low_confidence_threshold,
                stale_after_days=payload.stale_after_days,
                as_of_time_utc=_normalize_optional_as_of_time(payload.as_of_time_utc),
            ),
            dry_run=payload.dry_run,
        )
        stored_review = None
        if not payload.dry_run:
            record = _build_provider_mapping_review_run_repository(settings).save_review(
                result=result,
                provider=payload.provider,
                entity_type=payload.entity_type,
                canonical_entity_id=payload.canonical_entity_id,
                requested_by="admin_api",
            )
            stored_review = _provider_mapping_review_run_record_payload(record)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping review repository unavailable",
        ) from exc
    return ProviderMappingReviewResponse(
        result=result,
        stored_review=stored_review,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/providers/mappings/reviews/latest",
    response_model=ProviderMappingReviewRunListResponse,
)
def list_provider_mapping_review_runs(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
) -> ProviderMappingReviewRunListResponse:
    settings = request.app.state.settings
    try:
        records = _build_provider_mapping_review_run_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapping review repository unavailable",
        ) from exc
    return ProviderMappingReviewRunListResponse(
        items=[_provider_mapping_review_run_record_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/conflicts/evaluate",
    response_model=ProviderConflictEvaluationResponse,
)
def evaluate_provider_conflicts_request(
    request: Request,
    payload: ProviderConflictEvaluationRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderConflictEvaluationResponse:
    settings = request.app.state.settings
    if not payload.dry_run:
        require_admin_token(settings, x_nutmeg_admin_token)
    try:
        as_of_time = _normalize_optional_as_of_time(payload.as_of_time_utc)
        mappings = _build_provider_entity_mapping_repository(settings).list_review_candidates(
            provider=payload.provider,
            entity_type=payload.entity_type,
            canonical_entity_id=payload.canonical_entity_id,
            limit=payload.limit,
        )
        mapping_review = review_provider_entity_mappings(
            mappings,
            options=ProviderMappingReviewOptions(
                low_confidence_threshold=payload.low_confidence_threshold,
                stale_after_days=payload.stale_after_days,
                as_of_time_utc=as_of_time,
            ),
            dry_run=True,
        )
        mapping_result = evaluate_mapping_review_conflicts(
            mapping_review,
            dry_run=payload.dry_run,
        )
        events = list(mapping_result.events)
        checked_count = mapping_result.checked_issue_count
        observation_count = 0
        if payload.include_observations:
            observations = _build_provider_observation_repository(settings).list_recent(
                as_of_time_utc=as_of_time,
                lookback_hours=payload.observation_lookback_hours,
                provider_name=payload.provider,
                capability=payload.capability,
                entity_type=payload.entity_type,
                canonical_entity_id=payload.canonical_entity_id,
                limit=payload.limit,
            )
            observation_count = len(observations)
            events.extend(detect_provider_observation_conflicts(observations))
            checked_count += observation_count
        result = evaluate_provider_conflict_events(
            events,
            dry_run=payload.dry_run,
            as_of_time_utc=as_of_time,
            checked_issue_count=checked_count,
            metadata_json={
                "source": "provider_mapping_review_and_observations",
                "mapping_issue_count": mapping_result.checked_issue_count,
                "observation_count": observation_count,
                "quality_policy": "provider_conflict_quality_penalty_v1",
            },
        )
        stored_events: list[ProviderConflictEventRecordPayload] = []
        if not payload.dry_run:
            records = _build_provider_conflict_event_repository(settings).save_events(
                result=result,
                requested_by="admin_api",
            )
            stored_events = [_provider_conflict_event_record_payload(record) for record in records]
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider conflict repository unavailable",
        ) from exc
    return ProviderConflictEvaluationResponse(
        result=result,
        stored_events=stored_events,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/providers/conflicts/latest",
    response_model=ProviderConflictEventListResponse,
)
def list_provider_conflict_events(
    request: Request,
    status: ProviderConflictStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> ProviderConflictEventListResponse:
    settings = request.app.state.settings
    if status not in {None, "open", "resolved", "ignored"}:
        raise HTTPException(status_code=400, detail="invalid conflict status")
    try:
        records = _build_provider_conflict_event_repository(settings).list_latest(
            status=status,
            limit=limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider conflict repository unavailable",
        ) from exc
    return ProviderConflictEventListResponse(
        items=[_provider_conflict_event_record_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.patch(
    "/providers/conflicts/{provider_conflict_event_id}/resolution",
    response_model=ProviderConflictResolutionResponse,
)
def update_provider_conflict_resolution_request(
    request: Request,
    provider_conflict_event_id: int,
    payload: ProviderConflictResolutionRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderConflictResolutionResponse:
    settings = request.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    try:
        record = _build_provider_conflict_event_repository(settings).update_resolution_status(
            provider_conflict_event_id=provider_conflict_event_id,
            resolution_status=payload.resolution_status,
            requested_by="admin_api",
            resolution_note=payload.resolution_note,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider conflict repository unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="provider conflict event not found")
    return ProviderConflictResolutionResponse(
        item=_provider_conflict_event_record_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/onboarding/assessments",
    response_model=ProviderOnboardingAssessmentResponse,
)
def create_provider_onboarding_assessment(
    request: Request,
    payload: ProviderOnboardingAssessmentRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderOnboardingAssessmentResponse:
    settings = request.app.state.settings
    if not payload.dry_run:
        require_admin_token(settings, x_nutmeg_admin_token)

    try:
        as_of_time = _normalize_optional_as_of_time(payload.as_of_time_utc)
        odds_report = _build_odds_coverage_repository(settings).build_competition_report(
            competition_id=payload.competition_id,
            as_of_time_utc=as_of_time,
            window_days=payload.window_days,
            max_snapshot_lag_hours=payload.max_snapshot_lag_hours,
        )
        onboarding_input = _onboarding_input_from_request(payload, odds_report)
        assessment = assess_competition_onboarding(onboarding_input)
        stored_assessment = None
        if not payload.dry_run:
            record = _build_onboarding_assessment_repository(settings).save_assessment(
                payload=onboarding_input,
                assessment=assessment,
            )
            stored_assessment = ProviderOnboardingAssessmentRecordPayload(
                assessment_id=record.assessment_id,
                created_at_utc=record.created_at_utc,
            )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider onboarding repository unavailable",
        ) from exc
    return ProviderOnboardingAssessmentResponse(
        assessment=assessment,
        odds_coverage_report=odds_report,
        stored_assessment=stored_assessment,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/providers/onboarding/assessments/latest",
    response_model=ProviderOnboardingAssessmentListResponse,
)
def list_latest_provider_onboarding_assessments(
    request: Request,
    competition_id: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
) -> ProviderOnboardingAssessmentListResponse:
    settings = request.app.state.settings
    try:
        records = _build_onboarding_assessment_repository(settings).list_latest(
            competition_id=competition_id,
            limit=limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider onboarding repository unavailable",
        ) from exc
    return ProviderOnboardingAssessmentListResponse(
        items=[
            ProviderOnboardingAssessmentListItem(
                assessment=record.assessment,
                stored_assessment=ProviderOnboardingAssessmentRecordPayload(
                    assessment_id=record.assessment_id,
                    created_at_utc=record.created_at_utc,
                ),
            )
            for record in records
        ],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/football-data.org/sync/fixtures",
    response_model=ProviderFixtureSyncResponse,
)
def sync_football_data_fixtures_request(
    request: Request,
    payload: ProviderFixtureSyncRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderFixtureSyncResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    if not payload.dry_run and payload.canonical_competition_id is None:
        raise HTTPException(
            status_code=400,
            detail="canonical_competition_id is required for commit sync",
        )

    try:
        result = run_football_data_fixture_sync(
            settings,
            provider_competition_id=payload.provider_competition_id,
            season=payload.season,
            dry_run=payload.dry_run,
            canonical_competition_id=payload.canonical_competition_id,
        )
    except FootballDataOrgAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="football-data.org provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync repository unavailable",
        ) from exc

    return _provider_fixture_sync_response(result)


@api_router.post(
    "/providers/the-odds-api/sync/event-odds",
    response_model=ProviderEventOddsSyncResponse,
)
def sync_the_odds_api_event_odds_request(
    request: Request,
    payload: ProviderEventOddsSyncRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderEventOddsSyncResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        result = run_the_odds_api_event_odds_sync(
            settings,
            sport_key=payload.sport_key,
            provider_event_id=payload.provider_event_id,
            canonical_fixture_id=payload.canonical_fixture_id,
            regions=payload.regions,
            markets=payload.markets,
            bookmakers=payload.bookmakers,
            dry_run=payload.dry_run,
        )
    except TheOddsApiAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="The Odds API provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync repository unavailable",
        ) from exc

    return _provider_event_odds_sync_response(result)


@api_router.post(
    "/providers/the-odds-api/sync/mapped-event-odds",
    response_model=ProviderMappedEventOddsSyncResponse,
)
def sync_the_odds_api_mapped_event_odds_request(
    request: Request,
    payload: ProviderMappedEventOddsSyncRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderMappedEventOddsSyncResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        result = run_the_odds_api_mapped_event_odds_sync(
            settings,
            canonical_competition_id=payload.canonical_competition_id,
            sport_key=payload.sport_key,
            regions=payload.regions,
            markets=payload.markets,
            bookmakers=payload.bookmakers,
            min_mapping_confidence=payload.min_mapping_confidence,
            max_mappings=payload.max_mappings,
            dry_run=payload.dry_run,
            operator_approved=payload.operator_approved,
            operator_approval_note=payload.operator_approval_note,
        )
        coverage = None
        if payload.include_coverage:
            coverage = _build_odds_coverage_repository(settings).build_competition_report(
                competition_id=payload.canonical_competition_id,
                as_of_time_utc=datetime.now(UTC) + timedelta(days=90),
                window_days=90,
                max_snapshot_lag_hours=payload.max_snapshot_lag_hours,
            )
    except TheOddsApiAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="The Odds API provider unavailable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider mapped odds sync unavailable",
        ) from exc

    return ProviderMappedEventOddsSyncResponse(
        result=result,
        coverage=coverage,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/providers/sportmonks/sync/fixture-availability",
    response_model=ProviderFixtureAvailabilitySyncResponse,
)
def sync_sportmonks_fixture_availability_request(
    request: Request,
    payload: ProviderFixtureAvailabilitySyncRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderFixtureAvailabilitySyncResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    team_mappings = _team_mappings_from_payload(payload)
    try:
        result = run_sportmonks_fixture_availability_sync(
            settings,
            provider_fixture_id=payload.provider_fixture_id,
            canonical_fixture_id=payload.canonical_fixture_id,
            team_mappings=team_mappings,
            dry_run=payload.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SportMonksAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail="SportMonks provider unavailable",
        ) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync repository unavailable",
        ) from exc

    return _provider_fixture_availability_sync_response(result)


@api_router.post(
    "/ops/provider-sync/preflight",
    response_model=ProviderSyncWorkflowPreflightResponse,
)
def preflight_provider_sync_workflow_request(
    request: Request,
    payload: ProviderSyncWorkflowRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowPreflightResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    result = preflight_provider_sync_workflow(_provider_sync_workflow_options(payload))
    return ProviderSyncWorkflowPreflightResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/ops/provider-sync/run",
    response_model=ProviderSyncWorkflowRunResponse,
)
def run_provider_sync_workflow_request(
    request: Request,
    payload: ProviderSyncWorkflowRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowRunResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    if not settings.provider_sync_enabled:
        raise HTTPException(status_code=403, detail="provider sync is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    if payload.run_prematch_workflow and not settings.prediction_jobs_enabled:
        raise HTTPException(status_code=403, detail="prediction jobs are disabled")
    if payload.run_prematch_workflow and not settings.prematch_workflow_enabled:
        raise HTTPException(status_code=403, detail="prematch workflow is disabled")

    approval_record: ProviderSyncWorkflowApprovalRecord | None = None
    approval_repository: PostgresProviderSyncWorkflowApprovalRepository | None = None
    if payload.dry_run and payload.operator_approved:
        try:
            approval_repository = _build_provider_sync_workflow_approval_repository(settings)
            approval_record = approval_repository.record_approval(
                approval_type="provider_sync_workflow_dry_run",
                provider_sync_workflow_template_id=(payload.provider_sync_workflow_template_id),
                approved_by="admin_api",
                approval_note=payload.operator_approval_note,
                request_payload_json=_provider_sync_workflow_request_audit_payload(payload),
                metadata_json={
                    "source": "admin_api",
                    "approval_surface": "provider_ops",
                },
            )
        except (DatabaseReadError, RuntimeError) as exc:
            raise HTTPException(
                status_code=503,
                detail="provider sync approval repository unavailable",
            ) from exc

    try:
        result = run_audited_provider_sync_workflow(
            settings,
            options=_provider_sync_workflow_options(payload),
            requested_by="admin_api",
        )
        run_id = result.provider_sync_workflow_run_id
        if approval_record is not None and run_id is not None:
            result = result.model_copy(
                update={
                    "operator_approval_id": (approval_record.provider_sync_workflow_approval_id)
                }
            )
            if approval_repository is not None:
                approval_repository.link_workflow_run(
                    provider_sync_workflow_approval_id=(
                        approval_record.provider_sync_workflow_approval_id
                    ),
                    provider_sync_workflow_run_id=run_id,
                    metadata_json={"linked_by": "provider_sync_workflow_run"},
                )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync workflow repository unavailable",
        ) from exc
    return ProviderSyncWorkflowRunResponse(result=result, stale=False, fallback_used=False)


@api_router.get(
    "/ops/provider-sync/approvals",
    response_model=ProviderSyncWorkflowApprovalListResponse,
)
def list_provider_sync_workflow_approvals(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowApprovalListResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        records = _build_provider_sync_workflow_approval_repository(settings).list_latest(
            limit=limit
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync approval repository unavailable",
        ) from exc
    return ProviderSyncWorkflowApprovalListResponse(
        items=[_provider_sync_workflow_approval_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/ops/provider-sync/templates",
    response_model=ProviderSyncWorkflowTemplateListResponse,
)
def list_provider_sync_workflow_templates(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowTemplateListResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        records = _build_provider_sync_workflow_template_repository(settings).list_latest(
            limit=limit
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync template repository unavailable",
        ) from exc
    return ProviderSyncWorkflowTemplateListResponse(
        items=[_provider_sync_workflow_template_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/ops/provider-sync/templates",
    response_model=ProviderSyncWorkflowTemplateResponse,
)
def create_provider_sync_workflow_template(
    request: Request,
    payload: ProviderSyncWorkflowTemplateCreateRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowTemplateResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    preflight = preflight_provider_sync_workflow(_provider_sync_workflow_options(payload))
    if not preflight.valid:
        raise HTTPException(status_code=400, detail="provider sync template preflight failed")

    try:
        record = _build_provider_sync_workflow_template_repository(settings).save_template(
            template_name=payload.template_name,
            description=payload.description,
            dry_run=payload.dry_run,
            fixture_sync=(
                payload.fixture_sync.model_dump(mode="json", exclude_none=True)
                if payload.fixture_sync is not None
                else None
            ),
            odds_syncs=[
                item.model_dump(mode="json", exclude_none=True) for item in payload.odds_syncs
            ],
            availability_syncs=[
                item.model_dump(mode="json", exclude_none=True)
                for item in payload.availability_syncs
            ],
            run_conflict_detection=payload.run_conflict_detection,
            conflict_observation_lookback_hours=(payload.conflict_observation_lookback_hours),
            conflict_limit=payload.conflict_limit,
            created_by="admin_api",
            metadata_json={
                "source": "admin_api",
                "preflight_error_count": preflight.error_count,
                "preflight_warning_count": preflight.warning_count,
                "preflight_info_count": preflight.info_count,
            },
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync template repository unavailable",
        ) from exc
    return ProviderSyncWorkflowTemplateResponse(
        item=_provider_sync_workflow_template_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.patch(
    "/ops/provider-sync/templates/{provider_sync_workflow_template_id}",
    response_model=ProviderSyncWorkflowTemplateResponse,
)
def update_provider_sync_workflow_template(
    provider_sync_workflow_template_id: int,
    request: Request,
    payload: ProviderSyncWorkflowTemplateUpdateRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowTemplateResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    preflight = preflight_provider_sync_workflow(_provider_sync_workflow_options(payload))
    if not preflight.valid:
        raise HTTPException(status_code=400, detail="provider sync template preflight failed")

    try:
        record = _build_provider_sync_workflow_template_repository(settings).update_template(
            provider_sync_workflow_template_id=provider_sync_workflow_template_id,
            template_name=payload.template_name,
            description=payload.description,
            dry_run=payload.dry_run,
            fixture_sync=(
                payload.fixture_sync.model_dump(mode="json", exclude_none=True)
                if payload.fixture_sync is not None
                else None
            ),
            odds_syncs=[
                item.model_dump(mode="json", exclude_none=True) for item in payload.odds_syncs
            ],
            availability_syncs=[
                item.model_dump(mode="json", exclude_none=True)
                for item in payload.availability_syncs
            ],
            run_conflict_detection=payload.run_conflict_detection,
            conflict_observation_lookback_hours=(payload.conflict_observation_lookback_hours),
            conflict_limit=payload.conflict_limit,
            updated_by="admin_api",
            metadata_json={
                "source": "admin_api",
                "template_operation": "update",
                "preflight_error_count": preflight.error_count,
                "preflight_warning_count": preflight.warning_count,
                "preflight_info_count": preflight.info_count,
            },
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync template repository unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="provider sync template not found")
    return ProviderSyncWorkflowTemplateResponse(
        item=_provider_sync_workflow_template_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.delete(
    "/ops/provider-sync/templates/{provider_sync_workflow_template_id}",
    response_model=ProviderSyncWorkflowTemplateResponse,
)
def archive_provider_sync_workflow_template(
    provider_sync_workflow_template_id: int,
    request: Request,
    payload: Annotated[
        ProviderSyncWorkflowTemplateArchiveRequest | None,
        Body(),
    ] = None,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowTemplateResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        record = _build_provider_sync_workflow_template_repository(settings).archive_template(
            provider_sync_workflow_template_id=provider_sync_workflow_template_id,
            archived_by="admin_api",
            archive_reason=payload.archive_reason if payload is not None else None,
            metadata_json={
                "source": "admin_api",
                "template_operation": "archive",
            },
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync template repository unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="provider sync template not found")
    return ProviderSyncWorkflowTemplateResponse(
        item=_provider_sync_workflow_template_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/ops/provider-sync/runs",
    response_model=ProviderSyncWorkflowRunListResponse,
)
def list_provider_sync_workflow_runs(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowRunListResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        records = _build_provider_sync_workflow_run_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync workflow repository unavailable",
        ) from exc
    return ProviderSyncWorkflowRunListResponse(
        items=[_provider_sync_workflow_run_record_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/ops/provider-sync/runs/{provider_sync_workflow_run_id}",
    response_model=ProviderSyncWorkflowRunDetailResponse,
)
def get_provider_sync_workflow_run(
    request: Request,
    provider_sync_workflow_run_id: int,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ProviderSyncWorkflowRunDetailResponse:
    settings = request.app.state.settings
    if not settings.provider_sync_workflow_enabled:
        raise HTTPException(status_code=403, detail="provider sync workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        record = _build_provider_sync_workflow_run_repository(settings).get_by_id(
            provider_sync_workflow_run_id=provider_sync_workflow_run_id,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="provider sync workflow repository unavailable",
        ) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="provider sync workflow run not found")
    return ProviderSyncWorkflowRunDetailResponse(
        item=_provider_sync_workflow_run_record_payload(record),
        stale=False,
        fallback_used=False,
    )


@api_router.get("/competitions")
def list_competitions(request: Request) -> dict[str, object]:
    config_dir = request.app.state.settings.competition_config_dir
    competitions = load_competition_configs(config_dir)
    return {"items": [competition.model_dump() for competition in competitions]}


@api_router.post("/predictions/jobs/run", response_model=PredictionJobRunResponse)
def run_prediction_job_request(
    request: Request,
    payload: PredictionJobRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> PredictionJobRunResponse:
    settings = request.app.state.settings
    if not settings.prediction_jobs_enabled:
        raise HTTPException(status_code=403, detail="prediction jobs are disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        result = run_audited_prediction_job(
            settings,
            job_type=payload.job_type,
            fixture_ids=payload.fixture_ids or None,
            competition_id=payload.competition_id,
            dry_run=payload.dry_run,
            as_of_time_utc=_normalize_optional_as_of_time(payload.as_of_time_utc),
            window_hours=payload.window_hours,
            max_snapshot_lag_hours=payload.max_snapshot_lag_hours,
            limit=payload.limit,
            enforce_odds_quality_gate=payload.enforce_odds_quality_gate,
            requested_by="admin_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="prediction job repository unavailable",
        ) from exc

    return PredictionJobRunResponse(**result.model_dump())


@api_router.get("/predictions/jobs/runs", response_model=PredictionJobRunListResponse)
def list_prediction_job_runs(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> PredictionJobRunListResponse:
    settings = request.app.state.settings
    if not settings.prediction_jobs_enabled:
        raise HTTPException(status_code=403, detail="prediction jobs are disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        records = _build_prediction_job_run_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="prediction job repository unavailable",
        ) from exc
    return PredictionJobRunListResponse(
        items=[_prediction_job_run_record_payload(record) for record in records]
    )


@api_router.post(
    "/ops/prematch/run",
    response_model=PrematchWorkflowRunResponse,
)
def run_prematch_workflow_request(
    request: Request,
    payload: PrematchWorkflowRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> PrematchWorkflowRunResponse:
    settings = request.app.state.settings
    if not settings.prematch_workflow_enabled:
        raise HTTPException(status_code=403, detail="prematch workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    if not settings.prediction_jobs_enabled:
        raise HTTPException(status_code=403, detail="prediction jobs are disabled")
    if (
        payload.run_parlay_generation
        and not payload.dry_run
        and settings.parlay_repository != "postgres"
    ):
        raise HTTPException(
            status_code=400,
            detail="committed prematch workflow requires postgres parlay repository",
        )

    try:
        result = run_audited_prematch_workflow(
            settings,
            options=_prematch_workflow_options(payload),
            requested_by="admin_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="prematch workflow repository unavailable",
        ) from exc
    return PrematchWorkflowRunResponse(result=result, stale=False, fallback_used=False)


@api_router.get(
    "/ops/prematch/runs",
    response_model=PrematchWorkflowRunListResponse,
)
def list_prematch_workflow_runs(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> PrematchWorkflowRunListResponse:
    settings = request.app.state.settings
    if not settings.prematch_workflow_enabled:
        raise HTTPException(status_code=403, detail="prematch workflow is disabled")
    require_admin_token(settings, x_nutmeg_admin_token)

    try:
        records = _build_prematch_workflow_run_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="prematch workflow repository unavailable",
        ) from exc
    return PrematchWorkflowRunListResponse(
        items=[_prematch_workflow_run_record_payload(record) for record in records],
        stale=False,
        fallback_used=False,
    )


@api_router.get("/fixtures", response_model=FixtureListResponse)
def list_fixtures(
    request: Request,
    date: str | None = Query(default=None),
    competition_id: str | None = Query(default=None),
) -> FixtureListResponse:
    settings = request.app.state.settings
    odds_freshness, freshness_stale, freshness_fallback, freshness_warnings = (
        _latest_fixture_odds_coverage(
            settings,
            fixture_ids=[fixture["fixture_id"] for fixture in list_mock_fixtures()],
        )
    )
    availability_freshness, availability_stale, availability_fallback, availability_warnings = (
        _latest_fixture_availability_coverage(
            settings,
            fixture_ids=[fixture["fixture_id"] for fixture in list_mock_fixtures()],
        )
    )
    try:
        items = list_fixture_items(
            _build_mock_prediction_snapshots(
                odds_freshness=odds_freshness,
                availability_freshness=availability_freshness,
            ),
            date_filter=date,
            competition_id=competition_id,
            odds_freshness=odds_freshness,
            availability_freshness=availability_freshness,
            freshness_fallback_used=(
                (freshness_stale and freshness_fallback)
                or (availability_stale and availability_fallback)
            ),
            freshness_messages=freshness_warnings + availability_warnings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date filter") from exc
    return FixtureListResponse(items=items)


@api_router.get("/fixtures/{fixture_id}/prediction", response_model=FixturePredictionResponse)
def get_fixture_prediction(request: Request, fixture_id: str) -> FixturePredictionResponse:
    fixture = get_mock_fixture(fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    odds_freshness, freshness_stale, freshness_fallback, freshness_warnings = (
        _latest_fixture_odds_coverage(request.app.state.settings, fixture_ids=[fixture_id])
    )
    availability_freshness, availability_stale, availability_fallback, availability_warnings = (
        _latest_fixture_availability_coverage(
            request.app.state.settings,
            fixture_ids=[fixture_id],
        )
    )
    prediction = build_mock_prediction_snapshot_with_context(
        fixture_id,
        odds_coverage=odds_freshness.get(fixture_id) if odds_freshness is not None else None,
        availability_coverage=(
            availability_freshness.get(fixture_id) if availability_freshness is not None else None
        ),
    )
    if prediction is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return fixture_prediction_response(
        fixture,
        prediction,
        odds_freshness=odds_freshness,
        availability_freshness=availability_freshness,
        freshness_fallback_used=(
            (freshness_stale and freshness_fallback)
            or (availability_stale and availability_fallback)
        ),
        freshness_messages=freshness_warnings + availability_warnings,
    )


@api_router.get("/fixtures/{fixture_id}/score-grid", response_model=ScoreGridResponse)
def get_score_grid(fixture_id: str) -> ScoreGridResponse:
    prediction = build_mock_prediction_snapshot_with_context(fixture_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return score_grid_response(fixture_id, prediction)


@api_router.get("/upsets", response_model=UpsetListResponse)
def list_upsets() -> UpsetListResponse:
    return UpsetListResponse(items=upset_list_items(_build_mock_prediction_snapshots()))


@api_router.post("/parlays/evaluate", response_model=ParlayEvaluation)
def evaluate_parlay_request(request: ParlayEvaluateRequest) -> ParlayEvaluation:
    return evaluate_parlay(
        request.legs,
        pass_type=request.pass_type,
        unit_stake=request.unit_stake,
        multiplier=request.multiplier,
        max_budget=request.max_budget,
        correlation_penalty=request.correlation_penalty,
    )


@api_router.post("/parlays/recommend", response_model=ParlayRecommendResponse)
def recommend_parlays(
    request_context: Request,
    payload: ParlayRecommendRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ParlayRecommendResponse:
    settings = request_context.app.state.settings
    if payload.persist:
        require_admin_token(settings, x_nutmeg_admin_token)
        if settings.parlay_repository != "postgres":
            raise HTTPException(
                status_code=400,
                detail="parlay persistence requires postgres repository mode",
            )
    readiness, stale, fallback_used, warnings = _latest_competition_readiness(settings)
    odds_freshness, odds_stale, odds_fallback, odds_warnings = _latest_fixture_odds_coverage(
        settings,
        fixture_ids=[fixture["fixture_id"] for fixture in list_mock_fixtures()],
    )
    availability_freshness, availability_stale, availability_fallback, availability_warnings = (
        _latest_fixture_availability_coverage(
            settings,
            fixture_ids=[fixture["fixture_id"] for fixture in list_mock_fixtures()],
        )
    )
    response = parlay_recommendations(
        payload,
        _build_mock_prediction_snapshots(
            odds_freshness=odds_freshness,
            availability_freshness=availability_freshness,
        ),
        competition_readiness=readiness,
        odds_freshness=odds_freshness,
        availability_freshness=availability_freshness,
        stale=stale or odds_stale or availability_stale,
        fallback_used=fallback_used or odds_fallback or availability_fallback,
        initial_warnings=warnings + odds_warnings + availability_warnings,
    )
    if not payload.persist:
        return response
    try:
        stored_ids = [
            _build_parlay_repository(settings)
            .save_recommendation(
                parlay_recommendation_input_from_payload(
                    recommendation_key=ticket.recommendation_id,
                    model_version=ticket.model_version,
                    strategy=ticket.strategy,
                    pass_type=ticket.pass_type,
                    is_multiple=ticket.is_multiple,
                    unit_stake=ticket.unit_stake,
                    total_stake=ticket.total_stake,
                    hit_probability=ticket.hit_probability,
                    expected_payout=ticket.expected_payout,
                    expected_value=ticket.ev,
                    roi=ticket.roi,
                    risk_score=ticket.risk_score,
                    risk_level=ticket.risk_level,
                    correlation_penalty=ticket.correlation_penalty,
                    rule_valid=ticket.rule_valid,
                    explanation_json=ticket.explanation_json,
                    atomic_bets=ticket.atomic_bets,
                )
            )
            .parlay_recommendation_id
            for ticket in response.items
        ]
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="parlay recommendation repository unavailable",
        ) from exc
    return response.model_copy(update={"stored_recommendation_ids": stored_ids})


@api_router.post("/parlays/settle", response_model=ParlaySettlementResponse)
def settle_parlay_recommendations(
    request_context: Request,
    payload: ParlaySettlementRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ParlaySettlementResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    if settings.parlay_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="parlay settlement requires postgres repository mode",
        )
    try:
        run = _build_parlay_repository(settings).settle_unsettled_atomic_bets(
            limit=payload.limit,
            model_version=payload.model_version,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="parlay recommendation repository unavailable",
        ) from exc
    return ParlaySettlementResponse(run=run, stale=False, fallback_used=False)


@api_router.post("/parlays/generate", response_model=ParlayGenerateResponse)
def generate_parlay_recommendations_from_market_predictions(
    request_context: Request,
    payload: ParlayGenerateRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> ParlayGenerateResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    if settings.parlay_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="parlay generation requires postgres repository mode",
        )
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_market_prediction_parlay_generation(
            database,
            options=MarketPredictionParlayGenerationOptions(
                as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
                pass_type=payload.pass_type,
                unit_stake=payload.unit_stake,
                max_budget=payload.max_budget,
                competition_id=payload.competition_id,
                model_version=payload.model_version,
                allowed_markets=tuple(payload.allowed_markets),
                min_probability=payload.min_probability,
                min_model_edge=payload.min_model_edge,
                min_data_quality_score=payload.min_data_quality_score,
                candidate_limit=payload.candidate_limit,
                dry_run=payload.dry_run,
            ),
            repository=_build_parlay_repository(settings),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="parlay generation repository unavailable",
        ) from exc
    return ParlayGenerateResponse(result=result, stale=False, fallback_used=False)


@api_router.get("/recommendations/best", response_model=RecommendationGenerateResponse)
def best_recommendation(
    request_context: Request,
    pass_type: str = Query(default="2x1"),
    mode: str = Query(default="single"),
    strategy: str = Query(default="auto"),
    unit_stake: float = Query(default=2.0, gt=0.0),
    max_budget: float | None = Query(default=20.0, gt=0.0),
    competition_id: str | None = Query(default=None, min_length=1),
    model_version: str | None = Query(default=None, min_length=1),
    min_probability: float = Query(default=0.20, ge=0.0, le=1.0),
    min_model_edge: float | None = Query(default=None),
    min_data_quality_score: float = Query(default=50.0, ge=0.0, le=100.0),
    candidate_limit: int = Query(default=200, ge=1, le=2_000),
) -> RecommendationGenerateResponse:
    payload = RecommendationGenerateRequest(
        as_of_time_utc=datetime.now(tz=UTC),
        pass_type=pass_type,
        mode=_recommendation_mode(mode),
        strategy=_recommendation_generation_strategy(strategy),
        unit_stake=unit_stake,
        max_budget=max_budget,
        competition_id=competition_id,
        model_version=model_version,
        min_probability=min_probability,
        min_model_edge=min_model_edge,
        min_data_quality_score=min_data_quality_score,
        candidate_limit=candidate_limit,
        dry_run=True,
    )
    return _run_recommendation_generation_response(request_context, payload)


@api_router.post("/recommendations/generate", response_model=RecommendationGenerateResponse)
def generate_recommendations(
    request_context: Request,
    payload: RecommendationGenerateRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationGenerateResponse:
    settings = request_context.app.state.settings
    if not payload.dry_run:
        require_admin_token(settings, x_nutmeg_admin_token)
    return _run_recommendation_generation_response(request_context, payload)


@api_router.post(
    "/recommendations/global-best",
    response_model=RecommendationGlobalPlannerResponse,
)
def global_best_recommendation(
    request_context: Request,
    payload: RecommendationGlobalPlannerRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationGlobalPlannerResponse:
    settings = request_context.app.state.settings
    if not payload.dry_run:
        require_admin_token(settings, x_nutmeg_admin_token)
    if settings.recommendation_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="recommendation generation requires postgres repository mode",
        )
    try:
        as_of_time_utc = payload.as_of_time_utc or datetime.now(tz=UTC)
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        effective_strategy = (
            "accuracy_first"
            if payload.strategy == "auto"
            else _recommendation_strategy(payload.strategy)
        )
        locked_resolution = _resolve_global_planner_locked_candidates(
            database,
            payload=payload,
            as_of_time_utc=as_of_time_utc,
        )
        result = run_recommendation_global_planner(
            database,
            options=RecommendationGlobalPlannerOptions(
                as_of_time_utc=as_of_time_utc,
                strategy=effective_strategy,
                unit_stake=payload.unit_stake,
                max_budget=payload.max_budget,
                allowed_markets=tuple(payload.allowed_markets),
                pass_types=tuple(payload.pass_types),
                modes=tuple(payload.modes),
                min_probability=payload.min_probability,
                min_model_edge=payload.min_model_edge,
                min_data_quality_score=payload.min_data_quality_score,
                candidate_limit=payload.candidate_limit,
                require_odds=payload.require_odds,
                max_outcomes_per_fixture=payload.max_outcomes_per_fixture,
                min_marginal_quality_gain=payload.min_marginal_quality_gain,
                excluded_fixture_ids=tuple(payload.excluded_fixture_ids),
                locked_candidates=locked_resolution.candidates,
                competition_id=payload.competition_id,
                model_version=payload.model_version,
                dry_run=payload.dry_run,
                internal_trace_json={
                    "strategy_selection": {
                        "requested_strategy": payload.strategy,
                        "selected_strategy": effective_strategy,
                        "source": "global_best_endpoint",
                    }
                },
            ),
            repository=(
                _build_recommendation_repository(settings) if not payload.dry_run else None
            ),
        )
        if locked_resolution.warnings:
            result = result.model_copy(
                update={
                    "warnings": [
                        *locked_resolution.warnings,
                        *result.warnings,
                    ]
                }
            )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    public_result = _public_recommendation_global_planner_result(result)
    primary_answer = _recommendation_answer_from_global_option(
        public_result,
        public_result.best_option,
        max_budget=payload.max_budget,
    )
    answer_set = build_public_recommendation_answer_set(
        primary_answer,
        [
            _recommendation_answer_from_global_option(
                public_result,
                option,
                max_budget=payload.max_budget,
            )
            for option in public_result.alternatives
        ],
    )
    return RecommendationGlobalPlannerResponse(
        result=public_result,
        answer=answer_set.primary_answer,
        alternatives=answer_set.backup_answers,
        answer_set=answer_set,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/evaluate",
    response_model=RecommendationEvaluationRunResponse,
)
def evaluate_recommendations(
    request_context: Request,
    payload: RecommendationEvaluationRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationEvaluationRunResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        result = run_recommendation_evaluation(
            _build_recommendation_evaluation_repository(settings),
            options=RecommendationEvaluationOptions(
                evaluation_time_utc=payload.evaluation_time_utc,
                limit=payload.limit,
                save_partial=payload.save_partial,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation evaluation repository unavailable",
        ) from exc
    return RecommendationEvaluationRunResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/core-replay",
    response_model=RecommendationCoreReplayResponse,
)
def recommendation_core_replay(
    request_context: Request,
    payload: RecommendationCoreReplayRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationCoreReplayResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_core_replay(
            database,
            options=RecommendationCoreReplayOptions(
                window_start_utc=payload.window_start_utc,
                window_end_utc=payload.window_end_utc,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                limit=payload.limit,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation core replay unavailable",
        ) from exc
    return RecommendationCoreReplayResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/chain-integrity",
    response_model=RecommendationChainIntegrityResponse,
)
def recommendation_chain_integrity(
    request_context: Request,
    payload: RecommendationChainIntegrityRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationChainIntegrityResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_chain_integrity_check(
            PostgresRecommendationChainIntegrityRepository(database),
            options=RecommendationChainIntegrityOptions(
                window_start_utc=payload.window_start_utc,
                window_end_utc=payload.window_end_utc,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                limit=payload.limit,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation chain integrity unavailable",
        ) from exc
    return RecommendationChainIntegrityResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/source-status-sync",
    response_model=RecommendationSourceStatusSyncResponse,
)
def recommendation_source_status_sync(
    request_context: Request,
    payload: RecommendationSourceStatusSyncRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationSourceStatusSyncResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_source_status_sync(
            database,
            options=RecommendationSourceStatusSyncOptions(
                window_start_utc=payload.window_start_utc,
                window_end_utc=payload.window_end_utc,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                limit=payload.limit,
                event_time_utc=payload.event_time_utc,
                dry_run=payload.dry_run,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation source status sync unavailable",
        ) from exc
    return RecommendationSourceStatusSyncResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/recommendations/benchmark-runs",
    response_model=RecommendationBenchmarkHistoryResponse,
)
def recommendation_benchmark_history(
    request_context: Request,
    benchmark_key: Annotated[str | None, Query(min_length=1)] = None,
    strategy: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationBenchmarkHistoryResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    normalized_strategy = _recommendation_strategy(strategy) if strategy else None
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        items = PostgresRecommendationBenchmarkRunRepository(database).list_history(
            benchmark_key=benchmark_key,
            strategy=normalized_strategy,
            limit=limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation benchmark history unavailable",
        ) from exc
    return RecommendationBenchmarkHistoryResponse(
        items=items,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/recommendations/benchmark-strategy-pairs",
    response_model=RecommendationBenchmarkStrategyPairHistoryResponse,
)
def recommendation_benchmark_strategy_pair_history(
    request_context: Request,
    pair_key: Annotated[str | None, Query(min_length=1)] = None,
    baseline_strategy: Annotated[str | None, Query()] = None,
    candidate_strategy: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationBenchmarkStrategyPairHistoryResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    normalized_baseline_strategy = (
        _recommendation_strategy(baseline_strategy) if baseline_strategy else None
    )
    normalized_candidate_strategy = (
        _recommendation_strategy(candidate_strategy) if candidate_strategy else None
    )
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        items = PostgresRecommendationBenchmarkStrategyPairRunRepository(
            database
        ).list_history(
            pair_key=pair_key,
            baseline_strategy=normalized_baseline_strategy,
            candidate_strategy=normalized_candidate_strategy,
            limit=limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation benchmark strategy pair history unavailable",
        ) from exc
    return RecommendationBenchmarkStrategyPairHistoryResponse(
        items=items,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/recommendations/strategy-governance",
    response_model=RecommendationStrategyGovernanceOverviewResponse,
)
def recommendation_strategy_governance_overview(
    request_context: Request,
    candidate_strategy: Annotated[list[str] | None, Query()] = None,
    baseline_strategy: Annotated[str, Query()] = "accuracy_first",
    pass_type: Annotated[str, Query()] = "2x1",
    mode: Annotated[str, Query()] = "single",
    window_start_utc: Annotated[datetime | None, Query()] = None,
    window_end_utc: Annotated[datetime | None, Query()] = None,
    minimum_sample_size: Annotated[int, Query(ge=1)] = 30,
    minimum_baseline_sample_size: Annotated[int, Query(ge=1)] = 30,
) -> RecommendationStrategyGovernanceOverviewResponse:
    settings = request_context.app.state.settings
    baseline = _recommendation_strategy(baseline_strategy)
    normalized_mode = _recommendation_mode(mode)
    requested_candidate_strategies = candidate_strategy or [
        "value_first",
        "upset_protection",
        "budget_constrained",
    ]
    candidate_strategies = [
        _recommendation_strategy(strategy)
        for strategy in requested_candidate_strategies
        if strategy != baseline
    ]
    if not candidate_strategies:
        raise HTTPException(status_code=400, detail="candidate strategy list is empty")
    try:
        if settings.recommendation_repository == "postgres":
            overview = build_recommendation_strategy_governance_overview(
                _build_recommendation_strategy_governance_repository(settings),
                candidate_strategies=candidate_strategies,
                baseline_strategy=baseline,
                pass_type=pass_type,
                mode=normalized_mode,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
                minimum_sample_size=minimum_sample_size,
                minimum_baseline_sample_size=minimum_baseline_sample_size,
            )
            return RecommendationStrategyGovernanceOverviewResponse(
                overview=overview,
                stale=False,
                fallback_used=False,
            )
        overview = build_mock_recommendation_strategy_governance_overview(
            candidate_strategies=candidate_strategies,
            baseline_strategy=baseline,
            pass_type=pass_type,
            mode=normalized_mode,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            minimum_sample_size=minimum_sample_size,
            minimum_baseline_sample_size=minimum_baseline_sample_size,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation strategy governance repository unavailable",
        ) from exc
    return RecommendationStrategyGovernanceOverviewResponse(
        overview=overview,
        stale=False,
        fallback_used=True,
    )


@api_router.post(
    "/recommendations/strategy-review",
    response_model=RecommendationStrategyReviewResponse,
)
def review_recommendation_strategy(
    request_context: Request,
    payload: RecommendationStrategyReviewRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationStrategyReviewResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        result = run_recommendation_strategy_review(
            _build_recommendation_strategy_governance_repository(settings),
            options=RecommendationStrategyReviewOptions(
                candidate_strategy=payload.candidate_strategy,
                baseline_strategy=payload.baseline_strategy,
                pass_type=payload.pass_type,
                mode=payload.mode,
                window_start_utc=payload.window_start_utc,
                window_end_utc=payload.window_end_utc,
                minimum_sample_size=payload.minimum_sample_size,
                minimum_baseline_sample_size=payload.minimum_baseline_sample_size,
                min_roi_delta=payload.min_roi_delta,
                min_candidate_roi=payload.min_candidate_roi,
                tolerated_hit_rate_drop=payload.tolerated_hit_rate_drop,
                tolerated_calibration_error_delta=(payload.tolerated_calibration_error_delta),
                rollback_roi_floor=payload.rollback_roi_floor,
                rollback_max_roi_underperformance=(payload.rollback_max_roi_underperformance),
                rollback_calibration_error_ceiling=(payload.rollback_calibration_error_ceiling),
                dry_run=payload.dry_run,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation strategy governance repository unavailable",
        ) from exc
    return RecommendationStrategyReviewResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/provider-incidents/map",
    response_model=RecommendationProviderIncidentMappingResponse,
)
def map_recommendation_provider_incidents(
    request_context: Request,
    payload: RecommendationProviderIncidentMappingRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationProviderIncidentMappingResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_provider_incident_mapping(
            database,
            options=RecommendationProviderIncidentMappingOptions(
                as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
                lookback_hours=payload.lookback_hours,
                provider_name=payload.provider_name,
                canonical_fixture_id=payload.canonical_fixture_id,
                limit=payload.limit,
                critical_availability_confidence=(
                    payload.critical_availability_confidence
                ),
                odds_probability_shift_threshold=(
                    payload.odds_probability_shift_threshold
                ),
                critical_odds_probability_shift_threshold=(
                    payload.critical_odds_probability_shift_threshold
                ),
                dry_run=payload.dry_run,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation provider incident mapping unavailable",
        ) from exc
    return RecommendationProviderIncidentMappingResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/prematch-change-report",
    response_model=RecommendationPrematchChangeReportResponse,
)
def recommendation_prematch_change_report(
    request_context: Request,
    payload: RecommendationPrematchChangeReportRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationPrematchChangeReportResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_prematch_change_report(
            database,
            options=RecommendationPrematchChangeReportOptions(
                window_start_utc=payload.window_start_utc,
                window_end_utc=payload.window_end_utc,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                include_provider_incidents=payload.include_provider_incidents,
                dry_run=payload.dry_run,
                limit=payload.limit,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation prematch change report unavailable",
        ) from exc
    return RecommendationPrematchChangeReportResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/recompute-trigger",
    response_model=RecommendationRecomputeTriggerResponse,
)
def recommendation_recompute_trigger(
    request_context: Request,
    payload: RecommendationRecomputeTriggerRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationRecomputeTriggerResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_recompute_trigger(
            database,
            options=RecommendationRecomputeTriggerOptions(
                as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
                lookback_hours=payload.lookback_hours,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                include_candidate_pool_incidents=(
                    payload.include_candidate_pool_incidents
                ),
                preserve_locked_legs=payload.preserve_locked_legs,
                trigger_locked_successors=payload.trigger_locked_successors,
                dry_run=payload.dry_run,
                source_run_limit=payload.source_run_limit,
                incident_limit=payload.incident_limit,
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation recompute trigger unavailable",
        ) from exc
    return RecommendationRecomputeTriggerResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/{recommendation_run_id}/successor-recompute",
    response_model=RecommendationSuccessorRecomputeResponse,
)
def recommendation_successor_recompute(
    request_context: Request,
    payload: RecommendationSuccessorRecomputeRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationSuccessorRecomputeResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_successor_recompute(
            database,
            options=RecommendationSuccessorRecomputeOptions(
                source_recommendation_run_id=recommendation_run_id,
                as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                unit_stake=payload.unit_stake,
                max_budget=payload.max_budget,
                preserve_locked_legs=payload.preserve_locked_legs,
                excluded_fixture_ids=tuple(payload.excluded_fixture_ids),
                dry_run=payload.dry_run,
            ),
            recommendation_repository=(
                _build_recommendation_repository(settings)
                if not payload.dry_run
                else None
            ),
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation successor recompute unavailable",
        ) from exc
    answer = (
        build_recommendation_answer(
            result.generation_result,
            max_budget=payload.max_budget,
        )
        if result.generation_result is not None
        else RecommendationAnswer(
            status="unavailable",
            generated_at_utc=result.as_of_time_utc,
            warnings=result.warnings,
        )
    )
    return RecommendationSuccessorRecomputeResponse(
        result=result,
        answer=answer,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/prematch-pipeline",
    response_model=RecommendationPrematchPipelineResponse,
)
def recommendation_prematch_pipeline(
    request_context: Request,
    payload: RecommendationPrematchPipelineRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationPrematchPipelineResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        result = run_recommendation_prematch_pipeline(
            database,
            options=RecommendationPrematchPipelineOptions(
                as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
                lookback_hours=payload.lookback_hours,
                pass_type=payload.pass_type,
                mode=payload.mode,
                strategy=payload.strategy,
                provider_name=payload.provider_name,
                canonical_fixture_id=payload.canonical_fixture_id,
                run_provider_incident_mapping=payload.run_provider_incident_mapping,
                run_recompute_trigger=payload.run_recompute_trigger,
                run_prematch_change_report=payload.run_prematch_change_report,
                include_candidate_pool_incidents=(
                    payload.include_candidate_pool_incidents
                ),
                include_provider_incidents_in_report=(
                    payload.include_provider_incidents_in_report
                ),
                preserve_locked_legs=payload.preserve_locked_legs,
                trigger_locked_successors=payload.trigger_locked_successors,
                dry_run=payload.dry_run,
                provider_observation_limit=payload.provider_observation_limit,
                source_run_limit=payload.source_run_limit,
                incident_limit=payload.incident_limit,
                report_limit=payload.report_limit,
                critical_availability_confidence=(
                    payload.critical_availability_confidence
                ),
                odds_probability_shift_threshold=(
                    payload.odds_probability_shift_threshold
                ),
                critical_odds_probability_shift_threshold=(
                    payload.critical_odds_probability_shift_threshold
                ),
            ),
            requested_by="admin_api",
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation prematch pipeline unavailable",
        ) from exc
    return RecommendationPrematchPipelineResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.get(
    "/recommendations/{recommendation_run_id}/lifecycle",
    response_model=RecommendationLifecycleResponse,
)
def recommendation_lifecycle(
    request_context: Request,
    recommendation_run_id: int = Path(..., ge=1),
    event_limit: int = Query(default=100, ge=1, le=1_000),
) -> RecommendationLifecycleResponse:
    settings = request_context.app.state.settings
    _ensure_recommendation_repository_enabled(settings)
    try:
        detail = _build_recommendation_repository(settings).get_lifecycle_detail(
            recommendation_run_id,
            event_limit=event_limit,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    return RecommendationLifecycleResponse(detail=detail, stale=False, fallback_used=False)


@api_router.post(
    "/recommendations/{recommendation_run_id}/lock-leg",
    response_model=RecommendationLifecycleMutationResponse,
)
def lock_recommendation_leg(
    request_context: Request,
    payload: RecommendationLockLegRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationLifecycleMutationResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        result = _build_recommendation_repository(settings).lock_leg(
            recommendation_run_id,
            fixture_id=payload.fixture_id,
            market_type=payload.market_type,
            outcome=payload.outcome,
            locked_at_utc=payload.locked_at_utc or datetime.now(tz=UTC),
            reason_code=payload.reason_code,
            metadata_json=payload.metadata_json,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    return RecommendationLifecycleMutationResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/{recommendation_run_id}/release-leg",
    response_model=RecommendationLifecycleMutationResponse,
)
def release_recommendation_leg(
    request_context: Request,
    payload: RecommendationReleaseLegRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationLifecycleMutationResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        result = _build_recommendation_repository(settings).release_leg(
            recommendation_run_id,
            fixture_id=payload.fixture_id,
            market_type=payload.market_type,
            outcome=payload.outcome,
            released_at_utc=payload.released_at_utc or datetime.now(tz=UTC),
            reason_code=payload.reason_code,
            metadata_json=payload.metadata_json,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    return RecommendationLifecycleMutationResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


@api_router.post(
    "/recommendations/{recommendation_run_id}/confirm-manual",
    response_model=RecommendationLifecycleMutationResponse,
)
def confirm_recommendation_manually(
    request_context: Request,
    payload: RecommendationStatusTransitionRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationLifecycleMutationResponse:
    return _transition_recommendation_lifecycle(
        request_context,
        recommendation_run_id=recommendation_run_id,
        payload=payload,
        to_status="confirmed_manual",
        x_nutmeg_admin_token=x_nutmeg_admin_token,
    )


@api_router.post(
    "/recommendations/{recommendation_run_id}/supersede",
    response_model=RecommendationLifecycleMutationResponse,
)
def supersede_recommendation(
    request_context: Request,
    payload: RecommendationStatusTransitionRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationLifecycleMutationResponse:
    return _transition_recommendation_lifecycle(
        request_context,
        recommendation_run_id=recommendation_run_id,
        payload=payload,
        to_status="superseded",
        x_nutmeg_admin_token=x_nutmeg_admin_token,
    )


@api_router.post(
    "/recommendations/{recommendation_run_id}/invalidate",
    response_model=RecommendationLifecycleMutationResponse,
)
def invalidate_recommendation(
    request_context: Request,
    payload: RecommendationStatusTransitionRequest,
    recommendation_run_id: int = Path(..., ge=1),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> RecommendationLifecycleMutationResponse:
    return _transition_recommendation_lifecycle(
        request_context,
        recommendation_run_id=recommendation_run_id,
        payload=payload,
        to_status="invalidated",
        x_nutmeg_admin_token=x_nutmeg_admin_token,
    )


def _run_recommendation_generation_response(
    request_context: Request,
    payload: RecommendationGenerateRequest,
) -> RecommendationGenerateResponse:
    settings = request_context.app.state.settings
    if settings.recommendation_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="recommendation generation requires postgres repository mode",
        )
    try:
        as_of_time_utc = payload.as_of_time_utc or datetime.now(tz=UTC)
        database = PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
        internal_trace_json: dict[str, object] = {}
        if payload.strategy == "auto":
            overview = build_recommendation_strategy_governance_overview(
                PostgresRecommendationStrategyGovernanceRepository(database),
                candidate_strategies=[
                    "value_first",
                    "upset_protection",
                    "budget_constrained",
                ],
                baseline_strategy="accuracy_first",
                pass_type=payload.pass_type,
                mode=payload.mode,
            )
            strategy_selection = select_recommendation_strategy_from_governance(
                overview,
                requested_strategy="auto",
                baseline_strategy="accuracy_first",
                pass_type=payload.pass_type,
                mode=payload.mode,
            )
            effective_strategy = _recommendation_strategy(strategy_selection.selected_strategy)
            internal_trace_json["strategy_selection"] = strategy_selection.model_dump(
                mode="json"
            )
        else:
            effective_strategy = _recommendation_strategy(payload.strategy)
            internal_trace_json["strategy_selection"] = {
                "requested_strategy": payload.strategy,
                "selected_strategy": effective_strategy,
                "source": "explicit_request",
                "reasons": ["explicit_strategy_request"],
                "warnings": [],
            }
        search_outcome = _run_recommendation_answer_search(
            settings,
            database,
            payload=payload,
            as_of_time_utc=as_of_time_utc,
            effective_strategy=effective_strategy,
            internal_trace_json=internal_trace_json,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    public_result = _public_recommendation_generation_result(search_outcome.result)
    public_alternatives = [
        _public_recommendation_generation_result(result)
        for result in sorted(
            search_outcome.alternative_results,
            key=_recommendation_generation_sort_key,
            reverse=True,
        )
        if result.selection is not None
    ]
    primary_answer = build_recommendation_answer(
        public_result,
        max_budget=payload.max_budget,
    )
    answer_set = build_public_recommendation_answer_set(
        primary_answer,
        [
            build_recommendation_answer(result, max_budget=payload.max_budget)
            for result in public_alternatives
        ],
    )
    return RecommendationGenerateResponse(
        result=public_result,
        answer=answer_set.primary_answer,
        alternatives=answer_set.backup_answers,
        answer_set=answer_set,
        single_answer=build_candidate_recommendation_answer(
            _single_focus_candidate(search_outcome),
            generated_at_utc=as_of_time_utc,
            pass_type="single",
            unit_stake=payload.unit_stake,
            max_budget=payload.max_budget,
            unavailable_warning="single_answer_unavailable_from_current_candidate_pool",
        ),
        upset_answer=build_candidate_recommendation_answer(
            _upset_focus_candidate(search_outcome),
            generated_at_utc=as_of_time_utc,
            pass_type="upset",
            unit_stake=payload.unit_stake,
            max_budget=payload.max_budget,
            unavailable_warning="upset_answer_unavailable_from_current_candidate_pool",
        ),
        stale=False,
        fallback_used=False,
    )


@dataclass(frozen=True)
class RecommendationAnswerSearchOutcome:
    result: RecommendationGenerationResult
    alternative_results: tuple[RecommendationGenerationResult, ...]
    single_focus_candidate: ScoredRecommendationCandidate | None = None
    upset_focus_candidate: ScoredRecommendationCandidate | None = None


def _single_focus_candidate(
    search_outcome: RecommendationAnswerSearchOutcome,
) -> ScoredRecommendationCandidate | None:
    return search_outcome.single_focus_candidate


def _upset_focus_candidate(
    search_outcome: RecommendationAnswerSearchOutcome,
) -> ScoredRecommendationCandidate | None:
    return search_outcome.upset_focus_candidate


def _single_focus_sort_key(
    scored_candidate: ScoredRecommendationCandidate,
) -> tuple[float, float, float, float, str, str, str]:
    candidate = scored_candidate.candidate
    return (
        -scored_candidate.score,
        -candidate.probability,
        -candidate.data_quality_score,
        -candidate.effective_model_edge(),
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
    )


def _upset_focus_sort_key(
    scored_candidate: ScoredRecommendationCandidate,
) -> tuple[float, float, float, float, str, str, str]:
    candidate = scored_candidate.candidate
    return (
        -candidate.upset_protection_score,
        -scored_candidate.score,
        -candidate.probability,
        -candidate.data_quality_score,
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
    )


def _run_recommendation_answer_search(
    settings: Settings,
    database: PsycopgSyncDatabaseExecutor,
    *,
    payload: RecommendationGenerateRequest,
    as_of_time_utc: datetime,
    effective_strategy: RecommendationStrategy,
    internal_trace_json: dict[str, object],
) -> RecommendationAnswerSearchOutcome:
    requested_pass_types = _recommendation_generation_pass_types(payload.pass_type)
    single_focus_candidate, upset_focus_candidate = _recommendation_focus_candidates(
        database,
        payload=payload,
        as_of_time_utc=as_of_time_utc,
        effective_strategy=effective_strategy,
    )
    focus_policy_trace = _recommendation_focus_policy_trace(
        single_focus_candidate=single_focus_candidate,
        upset_focus_candidate=upset_focus_candidate,
    )
    persistent_internal_trace_json = (
        {
            **internal_trace_json,
            "focus_policy_answers": focus_policy_trace,
        }
        if focus_policy_trace
        else internal_trace_json
    )
    if len(requested_pass_types) == 1:
        result = run_recommendation_generation(
            database,
            options=_recommendation_generation_options(
                payload,
                as_of_time_utc=as_of_time_utc,
                pass_type=requested_pass_types[0],
                strategy=effective_strategy,
                dry_run=payload.dry_run,
                internal_trace_json=persistent_internal_trace_json,
            ),
            repository=(
                _build_recommendation_repository(settings) if not payload.dry_run else None
            ),
        )
        return RecommendationAnswerSearchOutcome(
            result=result,
            alternative_results=(result,),
            single_focus_candidate=single_focus_candidate,
            upset_focus_candidate=upset_focus_candidate,
        )

    dry_run_results = [
        run_recommendation_generation(
            database,
            options=_recommendation_generation_options(
                payload,
                as_of_time_utc=as_of_time_utc,
                pass_type=pass_type,
                strategy=effective_strategy,
                dry_run=True,
                internal_trace_json={},
            ),
        )
        for pass_type in requested_pass_types
    ]
    selected_result = max(dry_run_results, key=_recommendation_generation_sort_key)
    answer_search_trace = {
        "requested_pass_type": payload.pass_type,
        "evaluated_pass_types": list(requested_pass_types),
        "selected_pass_type": (
            selected_result.selection.pass_type if selected_result.selection is not None else None
        ),
        "generated_pass_types": [
            result.selection.pass_type
            for result in dry_run_results
            if result.selection is not None
        ],
    }
    if selected_result.selection is None:
        result = selected_result.model_copy(
            update={
                "warnings": [
                    "no_recommendation_answer_for_requested_pass_types",
                    *selected_result.warnings,
                ]
            }
        )
        return RecommendationAnswerSearchOutcome(
            result=result,
            alternative_results=tuple(dry_run_results),
            single_focus_candidate=single_focus_candidate,
            upset_focus_candidate=upset_focus_candidate,
        )
    if payload.dry_run:
        return RecommendationAnswerSearchOutcome(
            result=selected_result,
            alternative_results=tuple(dry_run_results),
            single_focus_candidate=single_focus_candidate,
            upset_focus_candidate=upset_focus_candidate,
        )

    result = run_recommendation_generation(
        database,
        options=_recommendation_generation_options(
            payload,
            as_of_time_utc=as_of_time_utc,
            pass_type=selected_result.selection.pass_type,
            strategy=effective_strategy,
            dry_run=False,
            internal_trace_json={
                **persistent_internal_trace_json,
                "answer_search": answer_search_trace,
            },
        ),
        repository=_build_recommendation_repository(settings),
    )
    return RecommendationAnswerSearchOutcome(
        result=result,
        alternative_results=tuple(dry_run_results),
        single_focus_candidate=single_focus_candidate,
        upset_focus_candidate=upset_focus_candidate,
    )


def _recommendation_focus_candidates(
    database: PsycopgSyncDatabaseExecutor,
    *,
    payload: RecommendationGenerateRequest,
    as_of_time_utc: datetime,
    effective_strategy: RecommendationStrategy,
) -> tuple[ScoredRecommendationCandidate | None, ScoredRecommendationCandidate | None]:
    allowed_markets = tuple(payload.allowed_markets)
    single_policy_config = build_single_focus_policy_config(
        strategy=effective_strategy,
        allowed_markets=allowed_markets,
        min_probability=payload.min_probability,
        min_model_edge=payload.min_model_edge,
        min_data_quality_score=payload.min_data_quality_score,
        require_odds=payload.require_odds,
    )
    upset_policy_config = build_upset_focus_policy_config(
        strategy=effective_strategy,
        allowed_markets=allowed_markets,
        min_probability=payload.min_probability,
        min_model_edge=payload.min_model_edge,
        min_data_quality_score=payload.min_data_quality_score,
        require_odds=payload.require_odds,
    )
    candidates = PostgresRecommendationRepository(database).list_candidates(
        options=RecommendationCandidateQueryOptions(
            as_of_time_utc=as_of_time_utc,
            allowed_markets=allowed_markets,
            min_probability=payload.min_probability,
            min_model_edge=payload.min_model_edge,
            min_data_quality_score=payload.min_data_quality_score,
            require_odds=payload.require_odds,
            candidate_limit=payload.candidate_limit,
            competition_id=payload.competition_id,
            model_version=payload.model_version,
        )
    )
    single_ranked_candidates = rank_candidates(
        candidates,
        config=single_policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    upset_ranked_candidates = rank_candidates(
        candidates,
        config=upset_policy_config,
        as_of_time_utc=as_of_time_utc,
    )
    single_focus = (
        sorted(single_ranked_candidates, key=_single_focus_sort_key)[0]
        if single_ranked_candidates
        else None
    )
    upset_candidates = [
        scored
        for scored in upset_ranked_candidates
        if scored.candidate.upset_protection_score > 0
    ]
    upset_focus = (
        sorted(upset_candidates, key=_upset_focus_sort_key)[0]
        if upset_candidates
        else None
    )
    return single_focus, upset_focus


def _recommendation_focus_policy_trace(
    *,
    single_focus_candidate: ScoredRecommendationCandidate | None,
    upset_focus_candidate: ScoredRecommendationCandidate | None,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    single_payload = _focus_candidate_trace(single_focus_candidate)
    if single_payload:
        payload["single"] = single_payload
    upset_payload = _focus_candidate_trace(upset_focus_candidate)
    if upset_payload:
        payload["upset"] = upset_payload
    return payload


def _focus_candidate_trace(
    scored_candidate: ScoredRecommendationCandidate | None,
) -> dict[str, object] | None:
    if scored_candidate is None:
        return None
    candidate = scored_candidate.candidate
    return {
        "fixture_id": candidate.fixture_id,
        "market_type": candidate.market_type,
        "outcome": candidate.outcome,
        "probability": candidate.probability,
        "decimal_odds": candidate.decimal_odds,
        "market_probability": candidate.market_probability,
        "model_edge": candidate.effective_model_edge(),
        "data_quality_score": candidate.data_quality_score,
        "model_confidence_score": candidate.model_confidence_score,
        "calibration_score": candidate.calibration_score,
        "upset_protection_score": candidate.upset_protection_score,
        "odds_stability_score": candidate.odds_stability_score,
        "volatility_penalty": candidate.volatility_penalty,
        "line": candidate.line,
        "side": candidate.side,
        "candidate_id": candidate.candidate_id,
        "model_version": candidate.model_version,
        "prediction_snapshot_id": candidate.prediction_snapshot_id,
        "prediction_time_utc": _optional_datetime_json(candidate.prediction_time_utc),
        "kickoff_time_utc": _optional_datetime_json(candidate.kickoff_time_utc),
        "correlation_key": candidate.correlation_key,
        "recommendation_score": scored_candidate.score,
        "component_scores": dict(scored_candidate.component_scores),
        "reason_codes": list(scored_candidate.reason_codes),
    }


def _optional_datetime_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_optional_as_of_time(value).isoformat().replace("+00:00", "Z")


def _recommendation_generation_options(
    payload: RecommendationGenerateRequest,
    *,
    as_of_time_utc: datetime,
    pass_type: str,
    strategy: RecommendationStrategy,
    dry_run: bool,
    internal_trace_json: dict[str, object],
) -> RecommendationGenerationOptions:
    return RecommendationGenerationOptions(
        as_of_time_utc=as_of_time_utc,
        pass_type=pass_type,
        mode=payload.mode,
        strategy=strategy,
        unit_stake=payload.unit_stake,
        max_budget=payload.max_budget,
        allowed_markets=tuple(payload.allowed_markets),
        min_probability=payload.min_probability,
        min_model_edge=payload.min_model_edge,
        min_data_quality_score=payload.min_data_quality_score,
        candidate_limit=payload.candidate_limit,
        require_odds=payload.require_odds,
        max_outcomes_per_fixture=payload.max_outcomes_per_fixture,
        min_marginal_quality_gain=payload.min_marginal_quality_gain,
        competition_id=payload.competition_id,
        model_version=payload.model_version,
        dry_run=dry_run,
        internal_trace_json=internal_trace_json,
    )


def _recommendation_generation_pass_types(pass_type: str) -> tuple[str, ...]:
    if pass_type.lower() == "all":
        return ("2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1")
    return (pass_type,)


def _recommendation_generation_sort_key(
    result: RecommendationGenerationResult,
) -> tuple[int, int, float, float, float, float]:
    selection = result.selection
    if selection is None:
        return (0, 0, 0.0, 0.0, -1.0, -1.0)
    evaluation = selection.evaluation
    budget_payload = evaluation.explanation_json.get("budget")
    max_budget = None
    if isinstance(budget_payload, dict):
        raw_budget = budget_payload.get("max_budget")
        if isinstance(raw_budget, int | float) and raw_budget > 0:
            max_budget = float(raw_budget)
    within_budget = max_budget is None or evaluation.total_stake <= max_budget
    return (
        int(evaluation.rule_valid),
        int(within_budget),
        selection.total_score,
        evaluation.hit_probability,
        evaluation.roi,
        -evaluation.risk_score,
    )


def _resolve_global_planner_locked_candidates(
    database: PsycopgSyncDatabaseExecutor,
    *,
    payload: RecommendationGlobalPlannerRequest,
    as_of_time_utc: datetime,
) -> ResolvedRecommendationLocks:
    specs = _global_planner_locked_candidate_specs(payload)
    if not specs:
        return ResolvedRecommendationLocks(candidates=(), warnings=())

    fixture_ids = tuple(spec.fixture_id for spec in specs)
    candidate_limit = min(
        3_000,
        max(payload.candidate_limit, len(fixture_ids) * max(len(payload.allowed_markets), 1) * 8),
    )
    candidates = PostgresRecommendationRepository(database).list_candidates(
        options=RecommendationCandidateQueryOptions(
            as_of_time_utc=as_of_time_utc,
            allowed_markets=_global_planner_locked_allowed_markets(
                payload,
                specs=specs,
            ),
            min_probability=0.0,
            min_model_edge=None,
            min_data_quality_score=0.0,
            require_odds=payload.require_odds,
            candidate_limit=candidate_limit,
            fixture_ids=fixture_ids,
            competition_id=payload.competition_id,
            model_version=payload.model_version,
        )
    )

    resolved_candidates: list[RecommendationCandidate] = []
    warnings: list[str] = []
    for spec in specs:
        candidate = _pick_locked_candidate(
            candidates,
            spec=spec,
            require_odds=payload.require_odds,
        )
        if candidate is None:
            warnings.append(
                "locked_candidate_unavailable:"
                f"{spec.fixture_id}:{spec.market_type or '*'}:{spec.outcome or '*'}"
            )
            continue
        resolved_candidates.append(candidate)
    return ResolvedRecommendationLocks(
        candidates=tuple(resolved_candidates),
        warnings=tuple(warnings),
    )


def _global_planner_locked_allowed_markets(
    payload: RecommendationGlobalPlannerRequest,
    *,
    specs: tuple[RecommendationLockedCandidateSpec, ...],
) -> tuple[RecommendationMarketType, ...]:
    allowed_markets = list(payload.allowed_markets)
    for spec in specs:
        if spec.market_type is not None and spec.market_type not in allowed_markets:
            allowed_markets.append(cast(RecommendationMarketType, spec.market_type))
    return cast(tuple[RecommendationMarketType, ...], tuple(allowed_markets))


def _global_planner_locked_candidate_specs(
    payload: RecommendationGlobalPlannerRequest,
) -> tuple[RecommendationLockedCandidateSpec, ...]:
    specs: list[RecommendationLockedCandidateSpec] = []
    seen_fixture_ids: set[str] = set()
    for candidate in payload.locked_candidates:
        fixture_id = candidate.fixture_id.strip()
        if not fixture_id or fixture_id in seen_fixture_ids:
            continue
        outcome = candidate.outcome.strip() if candidate.outcome else None
        specs.append(
            RecommendationLockedCandidateSpec(
                fixture_id=fixture_id,
                market_type=candidate.market_type,
                outcome=outcome,
            )
        )
        seen_fixture_ids.add(fixture_id)
    for fixture_id in payload.locked_fixture_ids:
        normalized_fixture_id = fixture_id.strip()
        if not normalized_fixture_id or normalized_fixture_id in seen_fixture_ids:
            continue
        specs.append(RecommendationLockedCandidateSpec(fixture_id=normalized_fixture_id))
        seen_fixture_ids.add(normalized_fixture_id)
    return tuple(specs)


def _pick_locked_candidate(
    candidates: list[RecommendationCandidate],
    *,
    spec: RecommendationLockedCandidateSpec,
    require_odds: bool,
) -> RecommendationCandidate | None:
    fixture_candidates = [
        candidate
        for candidate in candidates
        if candidate.fixture_id == spec.fixture_id
        and (not require_odds or candidate.decimal_odds is not None)
    ]
    if spec.market_type is not None:
        fixture_candidates = [
            candidate
            for candidate in fixture_candidates
            if candidate.market_type == spec.market_type
        ]
    if spec.outcome is not None:
        fixture_candidates = [
            candidate for candidate in fixture_candidates if candidate.outcome == spec.outcome
        ]
    if not fixture_candidates:
        return None
    return sorted(fixture_candidates, key=_locked_candidate_sort_key, reverse=True)[0]


def _locked_candidate_sort_key(
    candidate: RecommendationCandidate,
) -> tuple[float, float, float, float, float, float, float, str]:
    return (
        candidate.probability,
        candidate.effective_model_edge(),
        candidate.data_quality_score,
        candidate.model_confidence_score,
        candidate.calibration_score,
        candidate.odds_stability_score,
        -candidate.volatility_penalty,
        candidate.outcome,
    )


def _public_recommendation_generation_result(
    result: RecommendationGenerationResult,
) -> RecommendationGenerationResult:
    selection = result.selection
    if selection is None:
        return result
    public_selection = selection.model_copy(
        update={
            "explanation_json": _public_recommendation_explanation(
                selection.explanation_json
            )
        }
    )
    return result.model_copy(update={"selection": public_selection})


def _public_recommendation_global_planner_result(
    result: RecommendationGlobalPlannerResult,
) -> RecommendationGlobalPlannerResult:
    public_best_option = _public_recommendation_global_option(result.best_option)
    public_alternatives = [
        option
        for option in (
            _public_recommendation_global_option(item)
            for item in result.alternatives
        )
        if option is not None
    ][:2]
    return result.model_copy(
        update={
            "best_option": public_best_option,
            "alternatives": public_alternatives,
            "final_answer_decision_json": _public_final_answer_decision_json(
                result,
                backup_count=len(public_alternatives),
            ),
        }
    )


def _public_recommendation_global_option(
    option: RecommendationGlobalPlanOption | None,
) -> RecommendationGlobalPlanOption | None:
    if option is None:
        return None
    public_selection = option.selection.model_copy(
        update={
            "explanation_json": _public_recommendation_explanation(
                option.selection.explanation_json
            )
        }
    )
    return option.model_copy(
        update={
            "selection": public_selection,
            "explanation_json": _public_recommendation_explanation(
                option.explanation_json
            ),
        }
    )


def _public_final_answer_decision_json(
    result: RecommendationGlobalPlannerResult,
    *,
    backup_count: int,
) -> dict[str, object]:
    best_option = result.best_option
    return {
        "calculation_basis": "public_final_answer_decision_v3_1",
        "evaluated_option_count": result.evaluated_option_count,
        "generated_option_count": result.generated_option_count,
        "selected_pass_type": best_option.pass_type if best_option is not None else None,
        "selected_mode": best_option.mode if best_option is not None else None,
        "selected_answer_type": best_option.option_type if best_option is not None else None,
        "backup_count": backup_count,
        "public_scope": "single_best_answer_with_necessary_backups",
    }


def _recommendation_answer_from_global_option(
    result: RecommendationGlobalPlannerResult,
    option: RecommendationGlobalPlanOption | None,
    *,
    max_budget: float | None,
) -> RecommendationAnswer:
    if option is None:
        return RecommendationAnswer(
            status="unavailable",
            generated_at_utc=result.as_of_time_utc,
            warnings=result.warnings,
        )
    return build_recommendation_answer(
        RecommendationGenerationResult(
            dry_run=result.dry_run,
            as_of_time_utc=result.as_of_time_utc,
            candidate_count=result.candidate_count,
            generated_count=1,
            selection=option.selection,
            stored_run=result.stored_run
            if result.best_option is not None
            and option.option_key == result.best_option.option_key
            else None,
            warnings=[],
        ),
        max_budget=max_budget,
    )


def _public_recommendation_explanation(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _public_recommendation_explanation(item)
            for key, item in value.items()
            if str(key)
            not in {
                "strategy",
                "strategy_selection",
                "internal_trace",
                "global_planner",
                "final_answer_arbitration",
                "short_odds_final_answer_adapter",
                "upset_policy",
            }
        }
    if isinstance(value, list):
        return [_public_recommendation_explanation(item) for item in value]
    return value


def _transition_recommendation_lifecycle(
    request_context: Request,
    *,
    recommendation_run_id: int,
    payload: RecommendationStatusTransitionRequest,
    to_status: RecommendationLifecycleStatus,
    x_nutmeg_admin_token: str | None,
) -> RecommendationLifecycleMutationResponse:
    settings = request_context.app.state.settings
    require_admin_token(settings, x_nutmeg_admin_token)
    _ensure_recommendation_repository_enabled(settings)
    try:
        result = _build_recommendation_repository(settings).transition_run_status(
            recommendation_run_id,
            to_status=to_status,
            event_time_utc=payload.event_time_utc or datetime.now(tz=UTC),
            reason_code=payload.reason_code,
            metadata_json=payload.metadata_json,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="recommendation repository unavailable",
        ) from exc
    return RecommendationLifecycleMutationResponse(
        result=result,
        stale=False,
        fallback_used=False,
    )


def _ensure_recommendation_repository_enabled(settings: Settings) -> None:
    if settings.recommendation_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="recommendation lifecycle requires postgres repository mode",
        )


def _recommendation_strategy(strategy: str) -> RecommendationStrategy:
    allowed = {"accuracy_first", "value_first", "upset_protection", "budget_constrained"}
    if strategy not in allowed:
        raise HTTPException(status_code=422, detail="unsupported recommendation strategy")
    return cast(RecommendationStrategy, strategy)


def _recommendation_generation_strategy(strategy: str) -> RecommendationGenerationStrategyParam:
    if strategy == "auto":
        return "auto"
    return cast(RecommendationGenerationStrategyParam, _recommendation_strategy(strategy))


def _recommendation_mode(mode: str) -> RecommendationMode:
    if mode not in {"single", "multiple"}:
        raise HTTPException(status_code=422, detail="unsupported recommendation mode")
    return cast(RecommendationMode, mode)


@api_router.get("/accuracy/summary", response_model=AccuracySummaryResponse)
def accuracy_summary(
    request: Request,
    model_version: str = Query(default="active"),
    competition_id: str = Query(default="all"),
    market: str = Query(default="all"),
    window: str = Query(default="90d"),
) -> AccuracySummaryResponse:
    settings = request.app.state.settings
    repository = build_accuracy_repository(settings)
    try:
        return accuracy_summary_response(
            model_version=model_version,
            competition_id=competition_id,
            market=market,
            window=window,
            repository=repository,
            active_model_version=ACTIVE_MODEL_VERSION,
        )
    except (DatabaseReadError, RuntimeError) as exc:
        if settings.accuracy_repository == "postgres":
            raise HTTPException(
                status_code=503,
                detail="accuracy repository unavailable",
            ) from exc
        raise


@api_router.post("/accuracy/jobs/run", response_model=AccuracyJobRunResponse)
def run_accuracy_job_request(
    request: Request,
    payload: AccuracyJobRunRequest,
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> AccuracyJobRunResponse:
    settings = request.app.state.settings
    if not settings.accuracy_jobs_enabled:
        raise HTTPException(status_code=403, detail="accuracy jobs are disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    if settings.accuracy_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="accuracy jobs require postgres repository mode",
        )

    try:
        dixon_coles_options = (
            _dixon_coles_training_backtest_options(payload)
            if payload.job_type == "dixon_coles_training_backtest"
            else None
        )
        weekly_training_options = (
            _weekly_dixon_coles_training_pipeline_options(payload)
            if payload.job_type == "weekly_dixon_coles_training_pipeline"
            else None
        )
        result = run_audited_accuracy_job(
            settings,
            job_type=payload.job_type,
            reset=payload.reset,
            requested_by="admin_api",
            dixon_coles_options=dixon_coles_options,
            weekly_training_options=weekly_training_options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="accuracy job repository unavailable",
        ) from exc

    return AccuracyJobRunResponse(**result.model_dump())


@api_router.get("/accuracy/jobs/runs", response_model=AccuracyJobRunListResponse)
def list_accuracy_job_runs(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    x_nutmeg_admin_token: str | None = Header(
        default=None,
        alias="X-Nutmeg-Admin-Token",
    ),
) -> AccuracyJobRunListResponse:
    settings = request.app.state.settings
    if not settings.accuracy_jobs_enabled:
        raise HTTPException(status_code=403, detail="accuracy jobs are disabled")
    require_admin_token(settings, x_nutmeg_admin_token)
    if settings.accuracy_repository != "postgres":
        raise HTTPException(
            status_code=400,
            detail="accuracy jobs require postgres repository mode",
        )

    try:
        records = _build_accuracy_job_run_repository(settings).list_latest(limit=limit)
    except (DatabaseReadError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="accuracy job repository unavailable",
        ) from exc
    return AccuracyJobRunListResponse(
        items=[_accuracy_job_run_record_payload(record) for record in records]
    )


def _build_mock_prediction_snapshots(
    *,
    odds_freshness: dict[str, FixtureOddsCoverage] | None = None,
    availability_freshness: dict[str, FixtureAvailabilityCoverage] | None = None,
) -> dict[str, PredictionSnapshot]:
    snapshots: dict[str, PredictionSnapshot] = {}
    for fixture in list_mock_fixtures():
        fixture_id = fixture["fixture_id"]
        prediction = build_mock_prediction_snapshot_with_context(
            fixture_id,
            odds_coverage=odds_freshness.get(fixture_id) if odds_freshness is not None else None,
            availability_coverage=availability_freshness.get(fixture_id)
            if availability_freshness is not None
            else None,
        )
        if prediction is not None:
            snapshots[fixture["fixture_id"]] = prediction
    return snapshots


def _build_accuracy_job_run_repository(settings: Settings) -> PostgresAccuracyJobRunRepository:
    return PostgresAccuracyJobRunRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _dixon_coles_training_backtest_options(
    payload: AccuracyJobRunRequest,
) -> DixonColesTrainingBacktestJobOptions:
    return DixonColesTrainingBacktestJobOptions(
        as_of_time_utc=payload.as_of_time_utc or datetime.now(tz=UTC),
        competition_id=payload.competition_id,
        limit=payload.limit,
        train_window_days=payload.train_window_days,
        validation_window_days=payload.validation_window_days,
        time_decay_xi=payload.time_decay_xi,
        rho_candidates=tuple(payload.rho_candidates),
        max_goals=payload.max_goals,
        min_training_matches=payload.min_training_matches,
        candidate_model_version=payload.candidate_model_version,
        candidate_feature_version=payload.candidate_feature_version,
        candidate_calibration_version=payload.candidate_calibration_version,
        baseline_model_version=payload.baseline_model_version,
        baseline_log_loss=payload.baseline_log_loss,
        baseline_brier_score=payload.baseline_brier_score,
        baseline_ece=payload.baseline_ece,
        baseline_sample_size=payload.baseline_sample_size,
        baseline_calibration_market_type=payload.baseline_calibration_market_type,
        candidate_brier_score=payload.candidate_brier_score,
        candidate_ece=payload.candidate_ece,
        promotion_minimum_sample_size=payload.promotion_minimum_sample_size,
        promotion_evidence_top_k=payload.promotion_evidence_top_k,
        promotion_evidence_handicap_market_types=tuple(
            payload.promotion_evidence_handicap_market_types
        ),
        core_market_improvement=payload.core_market_improvement,
        upset_precision_at_k_delta=payload.upset_precision_at_k_delta,
        handicap_performance_delta=payload.handicap_performance_delta,
        parlay_simulation_delta=payload.parlay_simulation_delta,
        low_sample_competition_drift=payload.low_sample_competition_drift,
        previous_stable_model_version=payload.previous_stable_model_version,
        report_uri=payload.report_uri,
        dry_run=payload.dry_run,
    )


def _weekly_dixon_coles_training_pipeline_options(
    payload: AccuracyJobRunRequest,
) -> WeeklyDixonColesTrainingPipelineOptions:
    return WeeklyDixonColesTrainingPipelineOptions(
        training_options=_dixon_coles_training_backtest_options(payload),
        scheduled_for_utc=payload.weekly_scheduled_for_utc,
        run_label=payload.weekly_run_label,
    )


def _build_prediction_job_run_repository(
    settings: Settings,
) -> PostgresPredictionJobRunRepository:
    return PostgresPredictionJobRunRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_prematch_workflow_run_repository(
    settings: Settings,
) -> PostgresPrematchWorkflowRunRepository:
    return PostgresPrematchWorkflowRunRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_sync_workflow_run_repository(
    settings: Settings,
) -> PostgresProviderSyncWorkflowRunRepository:
    return PostgresProviderSyncWorkflowRunRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_sync_workflow_template_repository(
    settings: Settings,
) -> PostgresProviderSyncWorkflowTemplateRepository:
    return PostgresProviderSyncWorkflowTemplateRepository(
        ProviderSyncWorkflowTemplateDatabase(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_sync_workflow_approval_repository(
    settings: Settings,
) -> PostgresProviderSyncWorkflowApprovalRepository:
    return PostgresProviderSyncWorkflowApprovalRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_entity_mapping_repository(
    settings: Settings,
) -> PostgresProviderEntityMappingRepository:
    return PostgresProviderEntityMappingRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_mapping_review_run_repository(
    settings: Settings,
) -> PostgresProviderMappingReviewRunRepository:
    return PostgresProviderMappingReviewRunRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_conflict_event_repository(
    settings: Settings,
) -> PostgresProviderConflictEventRepository:
    return PostgresProviderConflictEventRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_observation_repository(
    settings: Settings,
) -> PostgresProviderObservationRepository:
    return PostgresProviderObservationRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_parlay_repository(settings: Settings) -> PostgresParlayRecommendationRepository:
    return PostgresParlayRecommendationRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_recommendation_repository(settings: Settings) -> PostgresRecommendationRepository:
    return PostgresRecommendationRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_recommendation_evaluation_repository(
    settings: Settings,
) -> PostgresRecommendationEvaluationRepository:
    return PostgresRecommendationEvaluationRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_recommendation_strategy_governance_repository(
    settings: Settings,
) -> PostgresRecommendationStrategyGovernanceRepository:
    return PostgresRecommendationStrategyGovernanceRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_odds_coverage_repository(settings: Settings) -> PostgresOddsCoverageRepository:
    return PostgresOddsCoverageRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_availability_coverage_repository(
    settings: Settings,
) -> PostgresAvailabilityCoverageRepository:
    return PostgresAvailabilityCoverageRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_onboarding_assessment_repository(
    settings: Settings,
) -> PostgresCompetitionOnboardingAssessmentRepository:
    return PostgresCompetitionOnboardingAssessmentRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_authorization_repository(
    settings: Settings,
) -> PostgresProviderAuthorizationRepository:
    return PostgresProviderAuthorizationRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_authorization_review_repository(
    settings: Settings,
) -> PostgresProviderAuthorizationReviewRepository:
    return PostgresProviderAuthorizationReviewRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_ops_audit_event_repository(
    settings: Settings,
) -> PostgresProviderOpsAuditEventRepository:
    return PostgresProviderOpsAuditEventRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_ops_run_history_repository(
    settings: Settings,
) -> PostgresProviderOpsRunHistoryRepository:
    return PostgresProviderOpsRunHistoryRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _build_provider_runtime_monitoring_repository(
    settings: Settings,
) -> PostgresProviderRuntimeMonitoringRepository:
    return PostgresProviderRuntimeMonitoringRepository(
        PsycopgSyncDatabaseExecutor(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        )
    )


def _latest_competition_readiness(
    settings: Settings,
) -> tuple[list[CompetitionOnboardingAssessment] | None, bool, bool, list[str]]:
    if settings.provider_governance_repository != "postgres":
        return None, False, False, []
    try:
        records = _build_onboarding_assessment_repository(settings).list_latest(limit=100)
    except (DatabaseReadError, RuntimeError):
        return None, True, True, ["readiness_repository_unavailable"]
    return [record.assessment for record in records], False, False, []


def _latest_fixture_odds_coverage(
    settings: Settings,
    *,
    fixture_ids: list[str],
) -> tuple[dict[str, FixtureOddsCoverage] | None, bool, bool, list[str]]:
    if settings.provider_governance_repository != "postgres":
        return None, False, False, []
    try:
        coverage_items = _build_odds_coverage_repository(settings).list_fixture_coverage(
            fixture_ids=fixture_ids,
            as_of_time_utc=datetime.now(UTC),
            max_snapshot_lag_hours=24,
        )
    except (DatabaseReadError, RuntimeError):
        return None, True, True, ["odds_freshness_repository_unavailable"]
    return {item.fixture_id: item for item in coverage_items}, False, False, []


def _latest_fixture_availability_coverage(
    settings: Settings,
    *,
    fixture_ids: list[str],
) -> tuple[dict[str, FixtureAvailabilityCoverage] | None, bool, bool, list[str]]:
    if settings.provider_governance_repository != "postgres":
        return None, False, False, []
    try:
        coverage_items = _build_availability_coverage_repository(settings).list_fixture_coverage(
            fixture_ids=fixture_ids,
            as_of_time_utc=datetime.now(UTC),
            max_snapshot_lag_hours=24,
        )
    except (DatabaseReadError, RuntimeError):
        return None, True, True, ["availability_freshness_repository_unavailable"]
    return {item.fixture_id: item for item in coverage_items}, False, False, []


def _parse_as_of_time(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid as_of_time_utc") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_optional_as_of_time(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _onboarding_input_from_request(
    payload: ProviderOnboardingAssessmentRequest,
    odds_report: CompetitionOddsCoverageReport,
) -> CompetitionOnboardingInput:
    patch = odds_report.data_quality_component_patch
    return CompetitionOnboardingInput(
        competition_id=payload.competition_id,
        competition_name=payload.competition_name or odds_report.competition_name,
        target_stage=payload.target_stage,
        schedule_coverage=payload.schedule_coverage,
        result_coverage=payload.result_coverage,
        odds_coverage=patch.odds_coverage,
        handicap_coverage=patch.handicap_coverage,
        lineup_injury_coverage=payload.lineup_injury_coverage,
        historical_stats_completeness=payload.historical_stats_completeness,
        provider_consistency=payload.provider_consistency,
        data_freshness=patch.data_freshness,
        historical_sample_size=payload.historical_sample_size,
        complete_seasons=payload.complete_seasons,
        market_resolver_tests_passed=payload.market_resolver_tests_passed,
        score_grid_generation_passed=payload.score_grid_generation_passed,
        log_loss_delta_vs_baseline=payload.log_loss_delta_vs_baseline,
        brier_delta_vs_baseline=payload.brier_delta_vs_baseline,
        calibration_shift=payload.calibration_shift,
    )


def _prematch_workflow_options(
    payload: PrematchWorkflowRunRequest,
) -> PrematchWorkflowOptions:
    return PrematchWorkflowOptions(
        prediction_job_type=payload.prediction_job_type,
        fixture_ids=payload.fixture_ids,
        competition_id=payload.competition_id,
        dry_run=payload.dry_run,
        as_of_time_utc=payload.as_of_time_utc,
        window_hours=payload.window_hours,
        max_snapshot_lag_hours=payload.max_snapshot_lag_hours,
        prediction_limit=payload.prediction_limit,
        enforce_odds_quality_gate=payload.enforce_odds_quality_gate,
        run_parlay_generation=payload.run_parlay_generation,
        parlay_pass_type=payload.parlay_pass_type,
        parlay_unit_stake=payload.parlay_unit_stake,
        parlay_max_budget=payload.parlay_max_budget,
        parlay_allowed_markets=tuple(payload.parlay_allowed_markets),
        parlay_min_probability=payload.parlay_min_probability,
        parlay_min_model_edge=payload.parlay_min_model_edge,
        parlay_min_data_quality_score=payload.parlay_min_data_quality_score,
        parlay_candidate_limit=payload.parlay_candidate_limit,
        parlay_model_version=payload.parlay_model_version,
    )


def _provider_sync_workflow_options(
    payload: ProviderSyncWorkflowRunRequest,
) -> ProviderSyncWorkflowOptions:
    return ProviderSyncWorkflowOptions(
        dry_run=payload.dry_run,
        fixture_sync=(
            FootballDataFixtureSyncTask(**payload.fixture_sync.model_dump())
            if payload.fixture_sync is not None
            else None
        ),
        odds_syncs=tuple(
            TheOddsApiEventOddsSyncTask(**item.model_dump()) for item in payload.odds_syncs
        ),
        availability_syncs=tuple(
            SportMonksFixtureAvailabilitySyncTask(
                provider_fixture_id=item.provider_fixture_id,
                canonical_fixture_id=item.canonical_fixture_id,
                team_mappings={
                    mapping.provider_team_id: mapping.canonical_team_id
                    for mapping in item.team_mappings
                },
            )
            for item in payload.availability_syncs
        ),
        run_conflict_detection=payload.run_conflict_detection,
        conflict_observation_lookback_hours=payload.conflict_observation_lookback_hours,
        conflict_limit=payload.conflict_limit,
        run_prematch_workflow=payload.run_prematch_workflow,
        prematch_options=(
            PrematchWorkflowOptions(
                prediction_job_type=payload.prematch.prediction_job_type,
                fixture_ids=payload.prematch.fixture_ids,
                competition_id=payload.prematch.competition_id,
                dry_run=payload.dry_run,
                as_of_time_utc=payload.prematch.as_of_time_utc,
                window_hours=payload.prematch.window_hours,
                max_snapshot_lag_hours=payload.prematch.max_snapshot_lag_hours,
                prediction_limit=payload.prematch.prediction_limit,
                enforce_odds_quality_gate=payload.prematch.enforce_odds_quality_gate,
                run_parlay_generation=payload.prematch.run_parlay_generation,
                parlay_pass_type=payload.prematch.parlay_pass_type,
                parlay_unit_stake=payload.prematch.parlay_unit_stake,
                parlay_max_budget=payload.prematch.parlay_max_budget,
                parlay_allowed_markets=tuple(payload.prematch.parlay_allowed_markets),
                parlay_min_probability=payload.prematch.parlay_min_probability,
                parlay_min_model_edge=payload.prematch.parlay_min_model_edge,
                parlay_min_data_quality_score=(payload.prematch.parlay_min_data_quality_score),
                parlay_candidate_limit=payload.prematch.parlay_candidate_limit,
                parlay_model_version=payload.prematch.parlay_model_version,
            )
            if payload.prematch is not None
            else None
        ),
    )


def _provider_sync_workflow_request_audit_payload(
    payload: ProviderSyncWorkflowRunRequest,
) -> dict[str, object]:
    return {
        "dry_run": payload.dry_run,
        "fixture_sync": (
            payload.fixture_sync.model_dump(mode="json", exclude_none=True)
            if payload.fixture_sync is not None
            else None
        ),
        "odds_syncs": [
            item.model_dump(mode="json", exclude_none=True) for item in payload.odds_syncs
        ],
        "availability_syncs": [
            item.model_dump(mode="json", exclude_none=True) for item in payload.availability_syncs
        ],
        "run_conflict_detection": payload.run_conflict_detection,
        "conflict_observation_lookback_hours": (payload.conflict_observation_lookback_hours),
        "conflict_limit": payload.conflict_limit,
        "run_prematch_workflow": payload.run_prematch_workflow,
        "provider_sync_workflow_template_id": (payload.provider_sync_workflow_template_id),
        "operator_approved": payload.operator_approved,
    }


def _accuracy_job_run_record_payload(
    record: AccuracyJobRunRecord,
) -> AccuracyJobRunRecordPayload:
    return AccuracyJobRunRecordPayload(
        accuracy_job_run_id=record.accuracy_job_run_id,
        job_type=record.job_type,
        status=record.status,
        reset_requested=record.reset_requested,
        requested_by=record.requested_by,
        started_at_utc=record.started_at,
        completed_at_utc=record.completed_at,
        duration_ms=record.duration_ms,
        fixture_count=record.fixture_count,
        evaluation_count=record.evaluation_count,
        calibration_observation_count=record.calibration_observation_count,
        model_comparison_report_id=record.model_comparison_report_id,
        prediction_snapshot_ids=record.prediction_snapshot_ids,
        evaluation_ids=record.evaluation_ids,
        error_message=record.error_message,
    )


def _prediction_job_run_record_payload(
    record: PredictionJobRunRecord,
) -> PredictionJobRunRecordPayload:
    return PredictionJobRunRecordPayload(
        prediction_job_run_id=record.prediction_job_run_id,
        job_type=record.job_type,
        status=record.status,
        dry_run=record.dry_run,
        requested_by=record.requested_by,
        started_at_utc=record.started_at,
        completed_at_utc=record.completed_at,
        duration_ms=record.duration_ms,
        fixture_count=record.fixture_count,
        generated_count=record.generated_count,
        feature_snapshot_ids=record.feature_snapshot_ids,
        prediction_snapshot_ids=record.prediction_snapshot_ids,
        score_grid_ids=record.score_grid_ids,
        data_quality_scores=record.data_quality_scores,
        skipped_fixture_ids=record.skipped_fixture_ids,
        warnings=record.warnings,
        error_message=record.error_message,
    )


def _prematch_workflow_run_record_payload(
    record: PrematchWorkflowRunRecord,
) -> PrematchWorkflowRunRecordPayload:
    return PrematchWorkflowRunRecordPayload(
        prematch_workflow_run_id=record.prematch_workflow_run_id,
        status=record.status,
        dry_run=record.dry_run,
        requested_by=record.requested_by,
        started_at_utc=record.started_at,
        completed_at_utc=record.completed_at,
        duration_ms=record.duration_ms,
        prediction_job_run_id=record.prediction_job_run_id,
        prediction_job_type=record.prediction_job_type,
        prediction_fixture_count=record.prediction_fixture_count,
        prediction_generated_count=record.prediction_generated_count,
        parlay_generated_count=record.parlay_generated_count,
        parlay_recommendation_ids=record.parlay_recommendation_ids,
        warnings=record.warnings,
        error_message=record.error_message,
    )


def _provider_sync_workflow_run_record_payload(
    record: ProviderSyncWorkflowRunRecord,
) -> ProviderSyncWorkflowRunRecordPayload:
    return ProviderSyncWorkflowRunRecordPayload(
        provider_sync_workflow_run_id=record.provider_sync_workflow_run_id,
        status=record.status,
        dry_run=record.dry_run,
        requested_by=record.requested_by,
        started_at_utc=record.started_at,
        completed_at_utc=record.completed_at,
        duration_ms=record.duration_ms,
        fixture_sync_run_id=record.fixture_sync_run_id,
        odds_sync_run_ids=record.odds_sync_run_ids,
        availability_sync_run_ids=record.availability_sync_run_ids,
        fixture_count=record.fixture_count,
        odds_snapshot_count=record.odds_snapshot_count,
        availability_snapshot_count=record.availability_snapshot_count,
        raw_payload_ids=record.raw_payload_ids,
        canonical_fixture_ids=record.canonical_fixture_ids,
        prematch_workflow_run_id=record.prematch_workflow_run_id,
        warnings=record.warnings,
        error_message=record.error_message,
        metadata_json=record.metadata_json,
    )


def _provider_sync_workflow_template_payload(
    record: ProviderSyncWorkflowTemplateRecord,
) -> ProviderSyncWorkflowTemplateRecordPayload:
    preflight_request = ProviderSyncWorkflowRunRequest.model_validate(
        {
            "dry_run": record.dry_run,
            "fixture_sync": record.fixture_sync,
            "odds_syncs": record.odds_syncs,
            "availability_syncs": record.availability_syncs,
            "run_conflict_detection": record.run_conflict_detection,
            "conflict_observation_lookback_hours": (record.conflict_observation_lookback_hours),
            "conflict_limit": record.conflict_limit,
            "run_prematch_workflow": False,
        }
    )
    return ProviderSyncWorkflowTemplateRecordPayload(
        provider_sync_workflow_template_id=(record.provider_sync_workflow_template_id),
        template_name=record.template_name,
        description=record.description,
        dry_run=record.dry_run,
        fixture_sync=record.fixture_sync,
        odds_syncs=record.odds_syncs,
        availability_syncs=record.availability_syncs,
        run_conflict_detection=record.run_conflict_detection,
        conflict_observation_lookback_hours=(record.conflict_observation_lookback_hours),
        conflict_limit=record.conflict_limit,
        created_by=record.created_by,
        created_at_utc=record.created_at,
        updated_at_utc=record.updated_at,
        archived_at_utc=record.archived_at,
        archived_by=record.archived_by,
        archive_reason=record.archive_reason,
        metadata_json=record.metadata_json,
        preflight_result=preflight_provider_sync_workflow(
            _provider_sync_workflow_options(preflight_request)
        ),
    )


def _provider_sync_workflow_approval_payload(
    record: ProviderSyncWorkflowApprovalRecord,
) -> ProviderSyncWorkflowApprovalRecordPayload:
    return ProviderSyncWorkflowApprovalRecordPayload(
        provider_sync_workflow_approval_id=(record.provider_sync_workflow_approval_id),
        approval_type=record.approval_type,
        approval_status=record.approval_status,
        provider_sync_workflow_template_id=(record.provider_sync_workflow_template_id),
        provider_sync_workflow_run_id=record.provider_sync_workflow_run_id,
        approved_by=record.approved_by,
        approved_at_utc=record.approved_at,
        approval_note=record.approval_note,
        request_payload_json=record.request_payload_json,
        metadata_json=record.metadata_json,
    )


def _provider_authorization_review_input(
    payload: ProviderAuthorizationReviewRequest,
) -> ProviderAuthorizationReviewInput:
    return ProviderAuthorizationReviewInput(
        provider_name=payload.provider_name,
        review_reference=payload.review_reference,
        review_status=payload.review_status,
        reviewed_by=payload.reviewed_by,
        reviewed_at=payload.reviewed_at_utc,
        terms_url=payload.terms_url,
        terms_version_hash=payload.terms_version_hash,
        allowed_use=payload.allowed_use,
        commercial_use_allowed=payload.commercial_use_allowed,
        retention_allowed=payload.retention_allowed,
        historical_data_allowed=payload.historical_data_allowed,
        redistribution_allowed=payload.redistribution_allowed,
        rate_limit=payload.rate_limit,
        next_review_due_at=payload.next_review_due_at_utc,
        owner=payload.owner,
        evidence_json=payload.evidence_json,
        notes=payload.notes,
    )


def _provider_authorization_review_payload(
    record: ProviderAuthorizationReviewRecord,
) -> ProviderAuthorizationReviewRecordPayload:
    return ProviderAuthorizationReviewRecordPayload(
        provider_authorization_review_id=(record.provider_authorization_review_id),
        provider_name=record.provider_name,
        review_reference=record.review_reference,
        review_status=record.review_status,
        reviewed_by=record.reviewed_by,
        reviewed_at_utc=record.reviewed_at,
        terms_url=record.terms_url,
        terms_version_hash=record.terms_version_hash,
        allowed_use=record.allowed_use,
        commercial_use_allowed=record.commercial_use_allowed,
        retention_allowed=record.retention_allowed,
        historical_data_allowed=record.historical_data_allowed,
        redistribution_allowed=record.redistribution_allowed,
        rate_limit=record.rate_limit,
        next_review_due_at_utc=record.next_review_due_at,
        evidence_json=record.evidence_json,
        notes=record.notes,
        created_at_utc=record.created_at,
    )


def _provider_ops_audit_event_input(
    payload: ProviderOpsAuditEventRequest,
    operator_header: str | None,
) -> ProviderOpsAuditEventInput:
    return ProviderOpsAuditEventInput(
        event_type=payload.event_type,
        operator_name=_safe_operator_name(payload.operator_name or operator_header),
        action_surface=payload.action_surface,
        target_type=payload.target_type,
        target_id=payload.target_id,
        outcome=payload.outcome,
        request_path=payload.request_path,
        request_method=payload.request_method,
        metadata_json=_safe_audit_metadata(payload.metadata_json),
    )


def _provider_ops_audit_event_payload(
    record: ProviderOpsAuditEventRecord,
) -> ProviderOpsAuditEventRecordPayload:
    return ProviderOpsAuditEventRecordPayload(
        provider_ops_audit_event_id=record.provider_ops_audit_event_id,
        event_type=record.event_type,
        operator_name=record.operator_name,
        action_surface=record.action_surface,
        target_type=record.target_type,
        target_id=record.target_id,
        outcome=record.outcome,
        request_path=record.request_path,
        request_method=record.request_method,
        metadata_json=record.metadata_json,
        created_at_utc=record.created_at,
    )


def _provider_ops_run_history_input(
    payload: ProviderOpsRunHistoryRequest,
    operator_header: str | None,
) -> ProviderOpsRunHistoryInput:
    return ProviderOpsRunHistoryInput(
        run_name=payload.run_name,
        run_type=payload.run_type,
        source=payload.source,
        status=payload.status,
        operator_name=_safe_operator_name(payload.operator_name or operator_header),
        started_at=payload.started_at_utc,
        completed_at=payload.completed_at_utc,
        duration_ms=payload.duration_ms,
        exit_code=payload.exit_code,
        summary_json=_safe_audit_metadata(payload.summary_json),
        output_excerpt=_safe_output_excerpt(payload.output_excerpt),
        metadata_json=_safe_audit_metadata(payload.metadata_json),
    )


def _provider_ops_run_history_payload(
    record: ProviderOpsRunHistoryRecord,
) -> ProviderOpsRunHistoryRecordPayload:
    return ProviderOpsRunHistoryRecordPayload(
        provider_ops_run_id=record.provider_ops_run_id,
        run_name=record.run_name,
        run_type=record.run_type,
        source=record.source,
        status=record.status,
        operator_name=record.operator_name,
        started_at_utc=record.started_at,
        completed_at_utc=record.completed_at,
        duration_ms=record.duration_ms,
        exit_code=record.exit_code,
        summary_json=record.summary_json,
        output_excerpt=record.output_excerpt,
        metadata_json=record.metadata_json,
        created_at_utc=record.created_at,
    )


def _provider_runtime_monitoring_fallback_response(
    settings: Settings,
    *,
    stale: bool,
    fallback_used: bool,
) -> ProviderRuntimeMonitoringResponse:
    probe_response = build_provider_runtime_probe_response(settings, live=False)
    snapshots = provider_runtime_snapshot_inputs_from_probe_response(probe_response)
    return _provider_runtime_monitoring_response_from_snapshot_inputs(
        snapshots,
        settings=settings,
        generated_at_utc=probe_response.generated_at_utc,
        stale=stale,
        fallback_used=fallback_used,
    )


def _provider_runtime_monitoring_response_from_records(
    records: list[ProviderRuntimeSnapshotRecord],
    *,
    settings: Settings,
    generated_at_utc: datetime | None = None,
    stale: bool = False,
    fallback_used: bool = False,
) -> ProviderRuntimeMonitoringResponse:
    items = [_provider_runtime_monitoring_payload(record) for record in records]
    thresholds = _provider_runtime_monitoring_thresholds(settings)
    alerts = build_provider_runtime_monitoring_alerts(records, thresholds=thresholds)
    return ProviderRuntimeMonitoringResponse(
        items=items,
        summary=_provider_runtime_monitoring_summary(items),
        alert_level=provider_runtime_alert_level(alerts),
        alerts=[_provider_runtime_monitoring_alert_payload(alert) for alert in alerts],
        thresholds=ProviderRuntimeMonitoringThresholdPayload(**thresholds.model_dump()),
        generated_at_utc=generated_at_utc or datetime.now(UTC),
        stale=stale,
        fallback_used=fallback_used,
    )


def _provider_runtime_monitoring_response_from_snapshot_inputs(
    snapshots: list[ProviderRuntimeSnapshotInput],
    *,
    settings: Settings,
    generated_at_utc: datetime,
    stale: bool,
    fallback_used: bool,
) -> ProviderRuntimeMonitoringResponse:
    items = [_provider_runtime_monitoring_payload_from_input(snapshot) for snapshot in snapshots]
    thresholds = _provider_runtime_monitoring_thresholds(settings)
    alerts = build_provider_runtime_monitoring_alerts(snapshots, thresholds=thresholds)
    return ProviderRuntimeMonitoringResponse(
        items=items,
        summary=_provider_runtime_monitoring_summary(items),
        alert_level=provider_runtime_alert_level(alerts),
        alerts=[_provider_runtime_monitoring_alert_payload(alert) for alert in alerts],
        thresholds=ProviderRuntimeMonitoringThresholdPayload(**thresholds.model_dump()),
        generated_at_utc=generated_at_utc,
        stale=stale,
        fallback_used=fallback_used,
    )


def _provider_runtime_monitoring_payload(
    record: ProviderRuntimeSnapshotRecord,
) -> ProviderRuntimeMonitoringSnapshotRecordPayload:
    return ProviderRuntimeMonitoringSnapshotRecordPayload(
        provider_runtime_snapshot_id=record.provider_runtime_snapshot_id,
        provider_name=record.provider_name,
        capability=record.capability,
        probe_status=record.probe_status,
        key_configured=record.key_configured,
        live_probe=record.live_probe,
        safe_to_call_real_provider=record.safe_to_call_real_provider,
        latency_ms=record.latency_ms,
        error_rate=record.error_rate,
        success_count=record.success_count,
        failure_count=record.failure_count,
        rate_limit_remaining=record.rate_limit_remaining,
        quota_window=record.quota_window,
        fallback_used=record.fallback_used,
        message=record.message,
        next_action=record.next_action,
        metadata_json=record.metadata_json,
        observed_at_utc=record.observed_at,
    )


def _provider_runtime_monitoring_payload_from_input(
    snapshot: ProviderRuntimeSnapshotInput,
) -> ProviderRuntimeMonitoringSnapshotRecordPayload:
    return ProviderRuntimeMonitoringSnapshotRecordPayload(
        provider_runtime_snapshot_id=None,
        provider_name=snapshot.provider_name,
        capability=snapshot.capability,
        probe_status=snapshot.probe_status,
        key_configured=snapshot.key_configured,
        live_probe=snapshot.live_probe,
        safe_to_call_real_provider=snapshot.safe_to_call_real_provider,
        latency_ms=snapshot.latency_ms,
        error_rate=snapshot.error_rate,
        success_count=snapshot.success_count,
        failure_count=snapshot.failure_count,
        rate_limit_remaining=snapshot.rate_limit_remaining,
        quota_window=snapshot.quota_window,
        fallback_used=snapshot.fallback_used,
        message=snapshot.message,
        next_action=snapshot.next_action,
        metadata_json=snapshot.metadata_json,
        observed_at_utc=snapshot.observed_at,
    )


def _provider_runtime_monitoring_summary(
    items: list[ProviderRuntimeMonitoringSnapshotRecordPayload],
) -> ProviderRuntimeMonitoringSummaryPayload:
    latencies = [item.latency_ms for item in items if item.latency_ms is not None]
    latest_observed_at = max((item.observed_at_utc for item in items), default=None)
    return ProviderRuntimeMonitoringSummaryPayload(
        provider_count=len(items),
        healthy_count=sum(1 for item in items if item.probe_status in {"ok", "key_configured"}),
        degraded_count=sum(
            1 for item in items if item.probe_status not in {"ok", "key_configured"}
        ),
        rate_limited_count=sum(1 for item in items if item.probe_status == "rate_limited"),
        auth_failed_count=sum(1 for item in items if item.probe_status == "auth_failed"),
        unavailable_count=sum(1 for item in items if item.probe_status == "unavailable"),
        not_configured_count=sum(1 for item in items if item.probe_status == "not_configured"),
        fallback_provider_count=sum(1 for item in items if item.fallback_used),
        average_latency_ms=(round(sum(latencies) / len(latencies), 2) if latencies else None),
        latest_observed_at_utc=latest_observed_at,
    )


def _provider_runtime_monitoring_alert_payload(
    alert: ProviderRuntimeMonitoringAlert,
) -> ProviderRuntimeMonitoringAlertPayload:
    return ProviderRuntimeMonitoringAlertPayload(**alert.model_dump())


def _provider_runtime_monitoring_thresholds(
    settings: Settings,
) -> ProviderRuntimeMonitoringThresholds:
    return ProviderRuntimeMonitoringThresholds(
        provider_latency_p2_ms=settings.provider_runtime_latency_p2_ms,
        provider_latency_p1_ms=settings.provider_runtime_latency_p1_ms,
        provider_error_rate_p1=settings.provider_runtime_error_rate_p1,
        provider_plan_limit_p2=settings.provider_runtime_plan_limit_p2,
        fallback_usage_rate_p1=settings.provider_runtime_fallback_usage_rate_p1,
    )


def _provider_runtime_incident_report_input(
    payload: ProviderRuntimeIncidentReportRequest,
    monitoring: ProviderRuntimeMonitoringResponse,
    *,
    operator_header: str | None,
) -> ProviderRuntimeIncidentReportInput:
    created_by = _safe_operator_name(payload.created_by or operator_header)
    return ProviderRuntimeIncidentReportInput(
        alert_level=monitoring.alert_level,
        alert_count=len(monitoring.alerts),
        snapshot_count=len(monitoring.items),
        summary_json=monitoring.summary.model_dump(mode="json"),
        alerts_json=[alert.model_dump(mode="json") for alert in monitoring.alerts],
        thresholds_json=monitoring.thresholds.model_dump(mode="json"),
        source=payload.source,
        created_by=created_by or "nutmeg-ops",
        metadata_json=_safe_audit_metadata(payload.metadata_json),
    )


def _provider_runtime_incident_report_payload(
    record: ProviderRuntimeIncidentReportRecord,
) -> ProviderRuntimeIncidentReportRecordPayload:
    return ProviderRuntimeIncidentReportRecordPayload(
        provider_runtime_incident_report_id=(record.provider_runtime_incident_report_id),
        alert_level=record.alert_level,
        alert_count=record.alert_count,
        snapshot_count=record.snapshot_count,
        summary_json=record.summary_json,
        alerts_json=record.alerts_json,
        thresholds_json=record.thresholds_json,
        source=record.source,
        created_by=record.created_by,
        metadata_json=record.metadata_json,
        incident_status=record.incident_status,
        acknowledged_by=record.acknowledged_by,
        acknowledged_at_utc=record.acknowledged_at,
        resolved_by=record.resolved_by,
        resolved_at_utc=record.resolved_at,
        resolution_note=record.resolution_note,
        notification_status=record.notification_status,
        notification_payload_json=record.notification_payload_json,
        updated_at_utc=record.updated_at,
        created_at_utc=record.created_at,
    )


def _provider_runtime_incident_summary_payload(
    record: ProviderRuntimeIncidentSummary,
) -> ProviderRuntimeIncidentSummaryPayload:
    return ProviderRuntimeIncidentSummaryPayload(
        lookback_days=record.lookback_days,
        total_count=record.total_count,
        open_count=record.open_count,
        acknowledged_count=record.acknowledged_count,
        resolved_count=record.resolved_count,
        ignored_count=record.ignored_count,
        active_count=record.active_count,
        p0_count=record.p0_count,
        p1_count=record.p1_count,
        p2_count=record.p2_count,
        notification_failed_count=record.notification_failed_count,
        latest_created_at_utc=record.latest_created_at,
        mean_time_to_resolve_minutes=record.mean_time_to_resolve_minutes,
        trend_buckets=[
            ProviderRuntimeIncidentTrendBucketPayload(
                bucket_date=bucket.bucket_date,
                total_count=bucket.total_count,
                open_count=bucket.open_count,
                acknowledged_count=bucket.acknowledged_count,
                resolved_count=bucket.resolved_count,
                ignored_count=bucket.ignored_count,
                active_count=bucket.active_count,
                p0_count=bucket.p0_count,
                p1_count=bucket.p1_count,
                p2_count=bucket.p2_count,
                notification_failed_count=bucket.notification_failed_count,
            )
            for bucket in record.trend_buckets
        ],
    )


def _should_record_runtime_incident(
    alert_level: str,
    threshold: str,
) -> bool:
    if threshold == "always":
        return True
    ranks = {"P0": 0, "P1": 1, "P2": 2, "ok": 3}
    return ranks[alert_level] <= ranks[threshold]


def _safe_operator_name(value: str | None) -> str | None:
    if value is None:
        return None
    safe = "".join(character for character in value if character.isalnum() or character in " .@-_")
    text = safe.strip()[:120]
    return text or None


def _safe_audit_metadata(value: dict[str, object]) -> dict[str, object]:
    secret_markers = ("secret", "token", "key", "password", "credential")
    safe: dict[str, object] = {}
    for key, item in value.items():
        normalized_key = str(key)
        if any(marker in normalized_key.lower() for marker in secret_markers):
            safe[normalized_key] = "[redacted]"
        elif isinstance(item, str):
            safe[normalized_key] = item[:500]
        elif isinstance(item, int | float | bool) or item is None:
            safe[normalized_key] = item
        elif isinstance(item, list):
            safe[normalized_key] = item[:20]
        elif isinstance(item, dict):
            safe[normalized_key] = {
                str(child_key): child_value
                for child_key, child_value in list(item.items())[:20]
                if not any(marker in str(child_key).lower() for marker in secret_markers)
            }
        else:
            safe[normalized_key] = str(item)[:500]
    return safe


def _safe_output_excerpt(value: str | None) -> str | None:
    if value is None:
        return None
    secret_markers = ("secret", "token", "api_key", "password", "credential")
    text = value.strip()
    if not text:
        return None
    if any(marker in text.lower() for marker in secret_markers):
        return "[redacted: sensitive output omitted]"
    return text[:2000]


def _provider_mapping_review_run_record_payload(
    record: ProviderMappingReviewRunRecord,
) -> ProviderMappingReviewRunRecordPayload:
    return ProviderMappingReviewRunRecordPayload(
        provider_mapping_review_run_id=record.provider_mapping_review_run_id,
        provider=record.provider,
        entity_type=record.entity_type,
        canonical_entity_id=record.canonical_entity_id,
        low_confidence_threshold=record.low_confidence_threshold,
        stale_after_days=record.stale_after_days,
        checked_mapping_count=record.checked_mapping_count,
        issue_count=record.issue_count,
        critical_count=record.critical_count,
        warning_count=record.warning_count,
        info_count=record.info_count,
        issues=record.issues,
        requested_by=record.requested_by,
        created_at_utc=record.created_at_utc,
    )


def _provider_conflict_event_record_payload(
    record: ProviderConflictEventRecord,
) -> ProviderConflictEventRecordPayload:
    return ProviderConflictEventRecordPayload(
        provider_conflict_event_id=record.provider_conflict_event_id,
        source_review_run_id=record.source_review_run_id,
        source_issue_id=record.source_issue_id,
        conflict_type=record.conflict_type,
        severity=record.severity,
        entity_type=record.entity_type,
        canonical_entity_id=record.canonical_entity_id,
        provider_names=record.provider_names,
        provider_entity_ids=record.provider_entity_ids,
        trusted_provider=record.trusted_provider,
        resolution_status=record.resolution_status,
        data_quality_score_delta=record.data_quality_score_delta,
        evidence_json=record.evidence_json,
        recommended_action=record.recommended_action,
        requested_by=record.requested_by,
        created_at_utc=record.created_at_utc,
        resolved_at_utc=record.resolved_at_utc,
    )


def _provider_fixture_sync_response(
    result: FootballDataFixtureSyncResult,
) -> ProviderFixtureSyncResponse:
    sync_run_payload = None
    if result.sync_run is not None:
        sync_run_payload = ProviderSyncRunPayload(
            provider_sync_run_id=result.sync_run.provider_sync_run_id,
            status=result.sync_run.status,
            started_at_utc=result.sync_run.started_at,
            completed_at_utc=result.sync_run.completed_at,
            duration_ms=result.sync_run.duration_ms,
            entity_count=result.sync_run.entity_count,
            error_message=result.sync_run.error_message,
        )

    raw_payload = None
    if result.raw_payload is not None:
        raw_payload = ProviderRawPayloadSummary(
            payload_id=result.raw_payload.payload_id,
            endpoint=result.raw_payload.endpoint,
            request_hash=result.raw_payload.request_hash,
        )

    canonical_write = None
    if result.canonical_write is not None:
        canonical_write = ProviderCanonicalWriteSummaryPayload(
            **result.canonical_write.model_dump()
        )

    sample_fixture_ids = (
        result.canonical_write.canonical_fixture_ids[:5]
        if result.canonical_write is not None
        else [fixture.provider_entity_id for fixture in result.fixtures[:5]]
    )

    return ProviderFixtureSyncResponse(
        provider_name=result.provider_name,
        provider_competition_id=result.provider_competition_id,
        canonical_competition_id=result.canonical_competition_id,
        season=result.season,
        dry_run=result.dry_run,
        request_params=result.request_params,
        normalized_fixture_count=len(result.fixtures),
        sync_run=sync_run_payload,
        raw_payload=raw_payload,
        canonical_write=canonical_write,
        sample_fixture_ids=sample_fixture_ids,
        warnings=result.warnings,
        stale=False,
        fallback_used=False,
    )


def _provider_event_odds_sync_response(
    result: TheOddsApiEventOddsSyncResult,
) -> ProviderEventOddsSyncResponse:
    sync_run_payload = None
    if result.sync_run is not None:
        sync_run_payload = ProviderSyncRunPayload(
            provider_sync_run_id=result.sync_run.provider_sync_run_id,
            status=result.sync_run.status,
            started_at_utc=result.sync_run.started_at,
            completed_at_utc=result.sync_run.completed_at,
            duration_ms=result.sync_run.duration_ms,
            entity_count=result.sync_run.entity_count,
            error_message=result.sync_run.error_message,
        )

    raw_payload = None
    if result.raw_payload is not None:
        raw_payload = ProviderRawPayloadSummary(
            payload_id=result.raw_payload.payload_id,
            endpoint=result.raw_payload.endpoint,
            request_hash=result.raw_payload.request_hash,
        )

    odds_write = None
    if result.odds_write is not None:
        odds_write = ProviderOddsWriteSummaryPayload(**result.odds_write.model_dump())

    return ProviderEventOddsSyncResponse(
        provider_name=result.provider_name,
        sport_key=result.sport_key,
        provider_event_id=result.provider_event_id,
        canonical_fixture_id=result.canonical_fixture_id,
        dry_run=result.dry_run,
        request_params=result.request_params,
        normalized_odds_count=len(result.snapshots),
        bookmaker_count=len({snapshot.bookmaker for snapshot in result.snapshots}),
        market_types=sorted({snapshot.market_type for snapshot in result.snapshots}),
        sync_run=sync_run_payload,
        raw_payload=raw_payload,
        odds_write=odds_write,
        warnings=result.warnings,
        stale=False,
        fallback_used=False,
    )


def _provider_fixture_availability_sync_response(
    result: SportMonksFixtureAvailabilitySyncResult,
) -> ProviderFixtureAvailabilitySyncResponse:
    sync_run_payload = None
    if result.sync_run is not None:
        sync_run_payload = ProviderSyncRunPayload(
            provider_sync_run_id=result.sync_run.provider_sync_run_id,
            status=result.sync_run.status,
            started_at_utc=result.sync_run.started_at,
            completed_at_utc=result.sync_run.completed_at,
            duration_ms=result.sync_run.duration_ms,
            entity_count=result.sync_run.entity_count,
            error_message=result.sync_run.error_message,
        )

    availability_write = None
    if result.availability_write is not None:
        availability_write = ProviderAvailabilityWriteSummaryPayload(
            **result.availability_write.model_dump()
        )

    sample_players = [
        item
        for item in [
            *(lineup.player_name for lineup in result.lineups[:3]),
            *(availability.player_name for availability in result.availabilities[:3]),
        ]
        if item is not None
    ][:5]

    return ProviderFixtureAvailabilitySyncResponse(
        provider_name=result.provider_name,
        provider_fixture_id=result.provider_fixture_id,
        canonical_fixture_id=result.canonical_fixture_id,
        provider_team_ids=result.provider_team_ids,
        dry_run=result.dry_run,
        request_params=result.request_params,
        normalized_lineup_count=len(result.lineups),
        normalized_availability_count=len(result.availabilities),
        provider_observation_count=result.provider_observation_count,
        sync_run=sync_run_payload,
        raw_payloads=[
            ProviderRawPayloadSummary(
                payload_id=raw_payload.payload_id,
                endpoint=raw_payload.endpoint,
                request_hash=raw_payload.request_hash,
            )
            for raw_payload in result.raw_payloads
        ],
        availability_write=availability_write,
        sample_players=sample_players,
        warnings=result.warnings,
        stale=False,
        fallback_used=False,
    )


def _team_mappings_from_payload(
    payload: ProviderFixtureAvailabilitySyncRequest,
) -> dict[str, str]:
    team_mappings = {
        item.provider_team_id: item.canonical_team_id for item in payload.team_mappings
    }
    if len(team_mappings) != len(payload.team_mappings):
        raise HTTPException(
            status_code=400,
            detail="duplicate provider_team_id in team_mappings",
        )
    return team_mappings
