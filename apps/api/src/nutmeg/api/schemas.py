from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.parlay import AtomicBet, ParlayLegSelection
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.model_governance import ModelPromotionReview, ModelRollbackPlan
from nutmeg.parlay import MarketPredictionParlayGenerationResult, ParlaySettlementRun
from nutmeg.predictions.workflow import PrematchWorkflowResult
from nutmeg.providers.api_football.discovery import ApiFootballCompetitionDiscoveryResult
from nutmeg.providers.conflicts import (
    ProviderConflictEvaluationResult,
    ProviderConflictStatus,
)
from nutmeg.providers.fallback_odds_probe import SportMonksFallbackOddsProbeResult
from nutmeg.providers.fixture_mapping_bootstrap import FixtureMappingBootstrapResult
from nutmeg.providers.governance import (
    CompetitionOnboardingAssessment,
    ProviderAuthorizationRecord,
)
from nutmeg.providers.governance.authorization_reviews import (
    ProviderAuthorizationReviewStatus,
)
from nutmeg.providers.governance.ops_audit import ProviderOpsAuditOutcome
from nutmeg.providers.governance.run_history import ProviderOpsRunStatus
from nutmeg.providers.live_probes import ProviderRuntimeProbeResponse
from nutmeg.providers.mapped_odds_sync import TheOddsApiMappedEventOddsSyncResult
from nutmeg.providers.mapping_repository import (
    ProviderEntityMappingRecord,
    ProviderEntityMappingSummary,
)
from nutmeg.providers.mapping_review import (
    ProviderMappingReviewIssue,
    ProviderMappingReviewResult,
)
from nutmeg.providers.odds_coverage import (
    CompetitionOddsCoverageReport,
    OddsCoverageGapReport,
)
from nutmeg.providers.runtime_credentials import (
    ProviderApiKeyChecklistResponse,
    ProviderRuntimeCredentialResponse,
)
from nutmeg.providers.runtime_monitoring import (
    ProviderRuntimeAlertLevel,
    ProviderRuntimeAlertSeverity,
    ProviderRuntimeMonitoringThresholds,
    ProviderRuntimeMonitorNextAction,
    ProviderRuntimeSnapshotStatus,
)
from nutmeg.providers.sportmonks.discovery import SportMonksCompetitionDiscoveryResult
from nutmeg.providers.sportmonks_mapping_backfill import (
    SportMonksFixtureMappingBackfillResult,
)
from nutmeg.providers.workflow import ProviderSyncWorkflowResult
from nutmeg.providers.workflow_templates import ProviderSyncWorkflowPreflightResult
from nutmeg.recommendations import (
    RecommendationAnswer,
    RecommendationAnswerSet,
    RecommendationChainIntegrityReport,
    RecommendationCoreReplayRunResult,
    RecommendationEvaluationRunResult,
    RecommendationGenerationResult,
    RecommendationGlobalPlannerResult,
    RecommendationLifecycleDetail,
    RecommendationLifecycleMutationResult,
    RecommendationPrematchChangeReportRunResult,
    RecommendationPrematchPipelineRunResult,
    RecommendationProviderIncidentMappingResult,
    RecommendationRecomputeTriggerRunResult,
    RecommendationSourceStatusSyncRunResult,
    RecommendationStrategyGovernanceOverview,
    RecommendationStrategyReviewRunResult,
    RecommendationSuccessorRecomputeRunResult,
    StoredRecommendationBenchmarkRun,
    StoredRecommendationBenchmarkStrategyPairRun,
)

type AccuracyJobTypePayload = Literal[
    "mock_postgres_e2e",
    "dixon_coles_training_backtest",
    "weekly_dixon_coles_training_pipeline",
]
type RecommendationMarketPayload = Literal[
    "1x2",
    "cn_handicap_1x2",
    "european_handicap_1x2",
    "correct_score",
]
type RecommendationLifecycleStatusPayload = Literal[
    "candidate",
    "current",
    "superseded",
    "locked",
    "confirmed_manual",
    "live",
    "settled",
    "invalidated",
]


def _default_recommendation_allowed_markets() -> list[RecommendationMarketPayload]:
    return ["1x2", "cn_handicap_1x2"]


def _default_global_planner_allowed_markets() -> list[RecommendationMarketPayload]:
    return ["1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"]


def _default_global_planner_modes() -> list[Literal["single", "multiple"]]:
    return ["single", "multiple"]


class HealthResponse(BaseModel):
    status: str
    service: str


class TeamPayload(BaseModel):
    team_id: str
    name: str


class FixturePayload(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_time_utc: datetime
    home_team: TeamPayload
    away_team: TeamPayload
    status: Literal["scheduled", "stale", "beta"]
    data_quality_score: float = Field(ge=0.0, le=100.0)
    data_quality_grade: Literal["A", "B", "C", "D"]


class FixtureFreshnessPayload(BaseModel):
    odds_available: bool
    odds_fresh_enough: bool
    odds_market_types: list[str] = Field(default_factory=list)
    odds_snapshot_time_utc: datetime | None = None
    odds_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    lineup_available: bool = False
    lineup_fresh_enough: bool = False
    lineup_snapshot_time_utc: datetime | None = None
    lineup_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    injury_available: bool = False
    injury_fresh_enough: bool = False
    injury_snapshot_time_utc: datetime | None = None
    injury_snapshot_lag_hours: float | None = Field(default=None, ge=0.0)
    messages: list[str] = Field(default_factory=list)


class FixturePredictionBrief(BaseModel):
    p_home: float = Field(ge=0.0, le=1.0)
    p_draw: float = Field(ge=0.0, le=1.0)
    p_away: float = Field(ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"]
    model_version: str
    feature_version: str
    calibration_version: str
    prediction_time_utc: datetime
    data_quality_score: float = Field(ge=0.0, le=100.0)
    stale: bool = False
    fallback_used: bool = False
    data_freshness: FixtureFreshnessPayload | None = None


class FixtureListItem(BaseModel):
    fixture_id: str
    competition_id: str
    competition: str
    kickoff_time_utc: datetime
    home_team: TeamPayload
    away_team: TeamPayload
    prediction: FixturePredictionBrief
    badges: list[str] = Field(default_factory=list)


class FixtureListResponse(BaseModel):
    items: list[FixtureListItem]


class CorrectScorePayload(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)
    option_key: str


class MarketProbabilityComparison(BaseModel):
    label: str
    outcome_key: str
    model_probability: float = Field(ge=0.0, le=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    probability_gap: float | None = None
    highlighted: bool = False


class MarketComparisonSet(BaseModel):
    label: str
    items: list[MarketProbabilityComparison]


class UpsetContributionPayload(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0.0, le=100.0)
    description: str


class UpsetExplanationGroupPayload(BaseModel):
    title: str
    items: list[str] = Field(default_factory=list)


class UpsetAlertPayload(BaseModel):
    fixture_id: str
    type: str
    label: str
    target_outcome: str
    favorite: str = "市场热门"
    favorite_model_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    favorite_market_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    model_probability: float = Field(ge=0.0, le=1.0)
    market_probability: float = Field(ge=0.0, le=1.0)
    probability_gap: float
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "medium_high", "high"]
    explanations: list[str]
    contributions: list[UpsetContributionPayload] = Field(default_factory=list)
    explanation_groups: list[UpsetExplanationGroupPayload] = Field(default_factory=list)


class KeyFactorsPayload(BaseModel):
    model: list[str] = Field(default_factory=list)
    market: list[str] = Field(default_factory=list)
    lineup: list[str] = Field(default_factory=list)
    schedule: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


class ModelMetadataPayload(BaseModel):
    model_version: str
    feature_version: str
    calibration_version: str
    prediction_time_utc: datetime
    data_quality_score: float = Field(ge=0.0, le=100.0)
    data_quality_grade: Literal["A", "B", "C", "D"]
    stale: bool = False
    fallback_used: bool = False
    data_freshness: FixtureFreshnessPayload | None = None


class FixturePredictionResponse(BaseModel):
    fixture: FixturePayload
    prediction_snapshot: PredictionSnapshot
    score_top_n: list[CorrectScorePayload]
    market_predictions: dict[str, object]
    odds_comparison: dict[str, MarketComparisonSet]
    upset_alerts: list[UpsetAlertPayload]
    explanations: KeyFactorsPayload
    model_metadata: ModelMetadataPayload
    stale: bool = False
    fallback_used: bool = False


class ScoreGridResponse(BaseModel):
    fixture_id: str
    max_goals: int
    grid: list[list[float]]
    tail_mass: float = Field(ge=0.0, le=1.0)
    lambda_home: float | None = Field(default=None, ge=0.0)
    lambda_away: float | None = Field(default=None, ge=0.0)
    model_version: str
    calibration_version: str
    prediction_time_utc: datetime


class UpsetListItem(UpsetAlertPayload):
    match_label: str
    competition_name: str
    kickoff_time_utc: datetime
    data_quality_score: float = Field(ge=0.0, le=100.0)
    data_quality_grade: Literal["A", "B", "C", "D"]
    model_version: str
    prediction_time_utc: datetime


class UpsetListResponse(BaseModel):
    items: list[UpsetListItem]


class ParlayEvaluateRequest(BaseModel):
    pass_type: str
    unit_stake: float = Field(gt=0.0)
    multiplier: int = Field(default=1, ge=1)
    max_budget: float | None = Field(default=None, gt=0.0)
    correlation_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    legs: list[ParlayLegSelection]


class ParlayRecommendRequest(BaseModel):
    date: str | None = None
    pass_types: list[str] = Field(default_factory=lambda: ["2x1", "3x1", "4x1"])
    strategy: str = "balanced"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    allow_multiple_outcomes_per_fixture: bool = True
    allowed_markets: list[str] = Field(default_factory=lambda: ["1x2", "cn_handicap_1x2"])
    exclude_beta_competitions: bool = False
    persist: bool = False


class ParlayLegPayload(BaseModel):
    fixture_id: str
    match_label: str
    market: str
    outcomes: list[str]


class ParlayTicketPayload(BaseModel):
    recommendation_id: str
    model_version: str | None = None
    strategy: str
    pass_type: str
    is_multiple: bool
    legs: list[ParlayLegPayload]
    atomic_bet_count: int = Field(ge=0)
    unit_stake: float = Field(gt=0.0)
    total_stake: float = Field(ge=0.0)
    hit_probability: float = Field(ge=0.0, le=1.0)
    expected_payout: float
    ev: float
    roi: float
    risk_level: Literal["low", "medium", "medium_high", "high"]
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    correlation_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    rule_valid: bool
    explanations: list[str]
    explanation_json: dict[str, object] = Field(default_factory=dict)
    atomic_bets: list[AtomicBet] = Field(default_factory=list)


class ParlayRecommendResponse(BaseModel):
    items: list[ParlayTicketPayload]
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False
    stored_recommendation_ids: list[int] = Field(default_factory=list)


class ParlaySettlementRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1_000)
    model_version: str | None = Field(default=None, min_length=1)


class ParlaySettlementResponse(BaseModel):
    run: ParlaySettlementRun
    stale: bool = False
    fallback_used: bool = False


class ParlayGenerateRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    pass_type: str = "2x1"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    allowed_markets: list[str] = Field(default_factory=lambda: ["1x2", "cn_handicap_1x2"])
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float = 0.0
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=100, ge=1, le=1_000)
    dry_run: bool = True


class ParlayGenerateResponse(BaseModel):
    result: MarketPredictionParlayGenerationResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationGenerateRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    pass_type: str = "2x1"
    mode: Literal["single", "multiple"] = "single"
    strategy: Literal[
        "auto",
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] = "auto"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    allowed_markets: list[RecommendationMarketPayload] = Field(
        default_factory=_default_recommendation_allowed_markets
    )
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=200, ge=1, le=2_000)
    require_odds: bool = True
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    dry_run: bool = True


class RecommendationGenerateResponse(BaseModel):
    result: RecommendationGenerationResult
    answer: RecommendationAnswer
    alternatives: list[RecommendationAnswer] = Field(default_factory=list)
    answer_set: RecommendationAnswerSet | None = None
    single_answer: RecommendationAnswer | None = None
    upset_answer: RecommendationAnswer | None = None
    stale: bool = False
    fallback_used: bool = False


class RecommendationLockedCandidatePayload(BaseModel):
    fixture_id: str = Field(min_length=1)
    market_type: RecommendationMarketPayload | None = None
    outcome: str | None = Field(default=None, min_length=1)


class RecommendationGlobalPlannerRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    strategy: Literal[
        "auto",
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] = "auto"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    allowed_markets: list[RecommendationMarketPayload] = Field(
        default_factory=_default_global_planner_allowed_markets
    )
    pass_types: list[str] = Field(default_factory=lambda: ["all"])
    modes: list[Literal["single", "multiple"]] = Field(
        default_factory=_default_global_planner_modes
    )
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    require_odds: bool = True
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    locked_fixture_ids: list[str] = Field(default_factory=list)
    locked_candidates: list[RecommendationLockedCandidatePayload] = Field(
        default_factory=list
    )
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True


class RecommendationGlobalPlannerResponse(BaseModel):
    result: RecommendationGlobalPlannerResult
    answer: RecommendationAnswer
    alternatives: list[RecommendationAnswer] = Field(default_factory=list)
    answer_set: RecommendationAnswerSet | None = None
    stale: bool = False
    fallback_used: bool = False


class RecommendationEvaluationRunRequest(BaseModel):
    evaluation_time_utc: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1_000)
    save_partial: bool = False


class RecommendationEvaluationRunResponse(BaseModel):
    result: RecommendationEvaluationRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationCoreReplayRequest(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    limit: int = Field(default=200, ge=1, le=2_000)


class RecommendationCoreReplayResponse(BaseModel):
    result: RecommendationCoreReplayRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationChainIntegrityRequest(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    limit: int = Field(default=500, ge=1, le=5_000)


class RecommendationChainIntegrityResponse(BaseModel):
    result: RecommendationChainIntegrityReport
    stale: bool = False
    fallback_used: bool = False


class RecommendationSourceStatusSyncRequest(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    limit: int = Field(default=500, ge=1, le=5_000)
    event_time_utc: datetime | None = None
    dry_run: bool = True


class RecommendationSourceStatusSyncResponse(BaseModel):
    result: RecommendationSourceStatusSyncRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationBenchmarkHistoryResponse(BaseModel):
    items: list[StoredRecommendationBenchmarkRun] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class RecommendationBenchmarkStrategyPairHistoryResponse(BaseModel):
    items: list[StoredRecommendationBenchmarkStrategyPairRun] = Field(
        default_factory=list
    )
    stale: bool = False
    fallback_used: bool = False


class RecommendationStrategyReviewRequest(BaseModel):
    candidate_strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ]
    baseline_strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] = "accuracy_first"
    pass_type: str = "2x1"
    mode: Literal["single", "multiple"] = "single"
    window_start_utc: datetime | None = None
    window_end_utc: datetime | None = None
    minimum_sample_size: int = Field(default=30, ge=1)
    minimum_baseline_sample_size: int = Field(default=30, ge=1)
    min_roi_delta: float = 0.0
    min_candidate_roi: float = 0.0
    tolerated_hit_rate_drop: float = Field(default=0.02, ge=0.0, le=1.0)
    tolerated_calibration_error_delta: float = Field(default=0.05, ge=0.0)
    rollback_roi_floor: float = -0.10
    rollback_max_roi_underperformance: float = Field(default=0.10, ge=0.0)
    rollback_calibration_error_ceiling: float = Field(default=0.25, ge=0.0)
    dry_run: bool = True


class RecommendationStrategyReviewResponse(BaseModel):
    result: RecommendationStrategyReviewRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationStrategyGovernanceOverviewResponse(BaseModel):
    overview: RecommendationStrategyGovernanceOverview
    stale: bool = False
    fallback_used: bool = False


class RecommendationLockLegRequest(BaseModel):
    fixture_id: str
    market_type: RecommendationMarketPayload
    outcome: str
    locked_at_utc: datetime | None = None
    reason_code: str = "user_locked_leg"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationReleaseLegRequest(BaseModel):
    fixture_id: str
    market_type: RecommendationMarketPayload
    outcome: str
    released_at_utc: datetime | None = None
    reason_code: str = "user_released_leg"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationStatusTransitionRequest(BaseModel):
    event_time_utc: datetime | None = None
    reason_code: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationLifecycleResponse(BaseModel):
    detail: RecommendationLifecycleDetail
    stale: bool = False
    fallback_used: bool = False


class RecommendationLifecycleMutationResponse(BaseModel):
    result: RecommendationLifecycleMutationResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationProviderIncidentMappingRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=720)
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=2_000, ge=1, le=5_000)
    critical_availability_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    odds_probability_shift_threshold: float = Field(default=0.12, ge=0.01, le=1.0)
    critical_odds_probability_shift_threshold: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
    )
    dry_run: bool = True


class RecommendationProviderIncidentMappingResponse(BaseModel):
    result: RecommendationProviderIncidentMappingResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationPrematchChangeReportRequest(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    include_provider_incidents: bool = True
    dry_run: bool = True
    limit: int = Field(default=200, ge=1, le=2_000)


class RecommendationPrematchChangeReportResponse(BaseModel):
    result: RecommendationPrematchChangeReportRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationRecomputeTriggerRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    include_candidate_pool_incidents: bool = True
    preserve_locked_legs: bool = True
    trigger_locked_successors: bool = False
    dry_run: bool = True
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)


class RecommendationRecomputeTriggerResponse(BaseModel):
    result: RecommendationRecomputeTriggerRunResult
    stale: bool = False
    fallback_used: bool = False


class RecommendationSuccessorRecomputeRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    unit_stake: float | None = Field(default=None, gt=0.0)
    max_budget: float | None = Field(default=None, gt=0.0)
    preserve_locked_legs: bool = True
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True


class RecommendationSuccessorRecomputeResponse(BaseModel):
    result: RecommendationSuccessorRecomputeRunResult
    answer: RecommendationAnswer
    stale: bool = False
    fallback_used: bool = False


class RecommendationPrematchPipelineRequest(BaseModel):
    as_of_time_utc: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_type: str | None = Field(default=None, min_length=1)
    mode: Literal["single", "multiple"] | None = None
    strategy: Literal[
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    ] | None = None
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    run_provider_incident_mapping: bool = True
    run_recompute_trigger: bool = True
    run_prematch_change_report: bool = True
    include_candidate_pool_incidents: bool = True
    include_provider_incidents_in_report: bool = True
    preserve_locked_legs: bool = True
    trigger_locked_successors: bool = True
    dry_run: bool = True
    provider_observation_limit: int = Field(default=2_000, ge=1, le=5_000)
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)
    report_limit: int = Field(default=200, ge=1, le=2_000)
    critical_availability_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    odds_probability_shift_threshold: float = Field(default=0.12, ge=0.01, le=1.0)
    critical_odds_probability_shift_threshold: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
    )


class RecommendationPrematchPipelineResponse(BaseModel):
    result: RecommendationPrematchPipelineRunResult
    stale: bool = False
    fallback_used: bool = False


class AccuracySummaryFilters(BaseModel):
    model_version: str
    competition_id: str
    market: str
    window: str


class AccuracyMarketMetrics(BaseModel):
    log_loss: float | None = None
    brier_score: float | None = None
    ece: float | None = None
    sample_size: int = Field(ge=0)


class AccuracyCompetitionMetrics(AccuracyMarketMetrics):
    competition_id: str
    competition_name: str


class CalibrationBucketPayload(BaseModel):
    bucket_start: float = Field(ge=0.0, le=1.0)
    bucket_end: float = Field(ge=0.0, le=1.0)
    average_predicted_probability: float = Field(ge=0.0, le=1.0)
    actual_frequency: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)


class ErrorTypeSummaryPayload(BaseModel):
    tag: str
    label: str
    count: int = Field(ge=0)
    share: float = Field(ge=0.0, le=1.0)
    examples: list[str] = Field(default_factory=list)


class ModelComparisonPayload(BaseModel):
    baseline_model_version: str
    candidate_model_version: str
    baseline_log_loss: float | None = None
    candidate_log_loss: float | None = None
    baseline_brier_score: float | None = None
    candidate_brier_score: float | None = None
    calibration_delta: float | None = None
    sample_size: int = Field(ge=0)
    decision: Literal["promote_candidate", "keep_baseline", "needs_review"]
    reasons: list[str] = Field(default_factory=list)


class AccuracySummaryResponse(BaseModel):
    log_loss: float | None = None
    brier_score: float | None = None
    ece: float | None = None
    sample_size: int = Field(ge=0)
    by_market: dict[str, AccuracyMarketMetrics] = Field(default_factory=dict)
    by_competition: list[AccuracyCompetitionMetrics] = Field(default_factory=list)
    calibration_buckets: list[CalibrationBucketPayload] = Field(default_factory=list)
    error_types: list[ErrorTypeSummaryPayload] = Field(default_factory=list)
    model_comparisons: list[ModelComparisonPayload] = Field(default_factory=list)
    model_version: str
    window: str
    filters: AccuracySummaryFilters
    generated_at_utc: datetime
    stale: bool = False


class AccuracyJobRunRequest(BaseModel):
    job_type: AccuracyJobTypePayload = "mock_postgres_e2e"
    reset: bool = True
    dry_run: bool = True
    competition_id: str | None = Field(default=None, min_length=1)
    as_of_time_utc: datetime | None = None
    limit: int = Field(default=2_000, ge=1, le=20_000)
    train_window_days: int = Field(default=365, ge=31, le=3_650)
    validation_window_days: int = Field(default=90, ge=1, le=365)
    time_decay_xi: float = Field(default=0.0065, ge=0.0, le=1.0)
    rho_candidates: list[float] = Field(
        default_factory=lambda: [-0.15, -0.10, -0.05, 0.0, 0.05, 0.10],
        min_length=1,
    )
    max_goals: int = Field(default=8, ge=1, le=20)
    min_training_matches: int = Field(default=4, ge=1)
    candidate_model_version: str = Field(default="dc-v1.5-candidate", min_length=1)
    candidate_feature_version: str = Field(default="features-m1.2.0", min_length=1)
    candidate_calibration_version: str = Field(default="calibration-m1.0.0", min_length=1)
    baseline_model_version: str = Field(default="poisson-m1.1.0", min_length=1)
    baseline_log_loss: float = Field(default=1.0, ge=0.0)
    baseline_brier_score: float = Field(default=0.25, ge=0.0)
    baseline_ece: float | None = Field(default=None, ge=0.0)
    baseline_sample_size: int | None = Field(default=None, ge=0)
    baseline_calibration_market_type: str = Field(default="1x2", min_length=1)
    candidate_brier_score: float | None = Field(default=None, ge=0.0)
    candidate_ece: float | None = Field(default=None, ge=0.0)
    promotion_minimum_sample_size: int = Field(default=300, ge=1)
    promotion_evidence_top_k: int = Field(default=20, ge=1, le=500)
    promotion_evidence_handicap_market_types: list[str] = Field(
        default_factory=lambda: [
            "cn_handicap_1x2",
            "european_handicap_1x2",
            "asian_handicap",
        ],
        min_length=1,
    )
    core_market_improvement: bool | None = None
    upset_precision_at_k_delta: float | None = None
    handicap_performance_delta: float | None = None
    parlay_simulation_delta: float | None = None
    low_sample_competition_drift: bool = False
    previous_stable_model_version: str | None = Field(default=None, min_length=1)
    weekly_scheduled_for_utc: datetime | None = None
    weekly_run_label: str | None = Field(default=None, min_length=1)
    report_uri: str | None = Field(default=None, min_length=1)


class AccuracyJobRunResponse(BaseModel):
    accuracy_job_run_id: int | None = Field(default=None, gt=0)
    job_type: AccuracyJobTypePayload
    status: Literal["completed"]
    reset: bool
    dry_run: bool = False
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    prediction_snapshot_ids: dict[str, int]
    evaluation_ids: list[int]
    calibration_observation_count: int = Field(ge=0)
    model_comparison_report_id: int | None = None
    backtest_run_id: int | None = Field(default=None, gt=0)
    model_promotion_review_id: int | None = Field(default=None, gt=0)
    candidate_model_version: str | None = None
    baseline_model_version: str | None = None
    selected_rho: float | None = None
    train_sample_size: int | None = Field(default=None, ge=0)
    validation_sample_size: int | None = Field(default=None, ge=0)
    candidate_brier_score: float | None = Field(default=None, ge=0.0)
    candidate_ece: float | None = Field(default=None, ge=0.0)
    baseline_ece: float | None = Field(default=None, ge=0.0)
    baseline_calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    calibration_evidence_json: dict[str, object] = Field(default_factory=dict)
    promotion_evidence_json: dict[str, object] = Field(default_factory=dict)
    model_comparison_decision: str | None = None
    model_promotion_decision: str | None = None
    model_promotion_next_status: str | None = None
    model_promotion_reasons: list[str] = Field(default_factory=list)
    rollback_should_rollback: bool = False
    report_uri: str | None = None
    weekly_training_plan: dict[str, object] = Field(default_factory=dict)
    weekly_training_status: str | None = None
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class AccuracyJobRunRecordPayload(BaseModel):
    accuracy_job_run_id: int = Field(gt=0)
    job_type: AccuracyJobTypePayload
    status: Literal["running", "completed", "failed"]
    reset_requested: bool
    requested_by: str | None = None
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    evaluation_count: int = Field(ge=0)
    calibration_observation_count: int = Field(ge=0)
    model_comparison_report_id: int | None = None
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    evaluation_ids: list[int] = Field(default_factory=list)
    error_message: str | None = None


class AccuracyJobRunListResponse(BaseModel):
    items: list[AccuracyJobRunRecordPayload]
    stale: bool = False
    fallback_used: bool = False


class PredictionJobRunRequest(BaseModel):
    job_type: Literal[
        "mock_prematch_predictions",
        "canonical_prematch_predictions",
    ] = "mock_prematch_predictions"
    fixture_ids: list[str] = Field(default_factory=list)
    competition_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    as_of_time_utc: datetime | None = None
    window_hours: int = Field(default=72, ge=1, le=720)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    limit: int = Field(default=100, ge=1, le=500)
    enforce_odds_quality_gate: bool = True


class PredictionJobRunResponse(BaseModel):
    prediction_job_run_id: int | None = Field(default=None, gt=0)
    job_type: Literal[
        "mock_prematch_predictions",
        "canonical_prematch_predictions",
    ]
    status: Literal["completed"]
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    prediction_time_utc: datetime
    fixture_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    score_grid_ids: dict[str, int] = Field(default_factory=dict)
    data_quality_scores: dict[str, float] = Field(default_factory=dict)
    skipped_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class PredictionJobRunRecordPayload(BaseModel):
    prediction_job_run_id: int = Field(gt=0)
    job_type: Literal[
        "mock_prematch_predictions",
        "canonical_prematch_predictions",
    ]
    status: Literal["running", "completed", "failed"]
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    feature_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    prediction_snapshot_ids: dict[str, int] = Field(default_factory=dict)
    score_grid_ids: dict[str, int] = Field(default_factory=dict)
    data_quality_scores: dict[str, float] = Field(default_factory=dict)
    skipped_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None


class PredictionJobRunListResponse(BaseModel):
    items: list[PredictionJobRunRecordPayload]
    stale: bool = False
    fallback_used: bool = False


class PrematchWorkflowRunRequest(BaseModel):
    prediction_job_type: Literal[
        "mock_prematch_predictions",
        "canonical_prematch_predictions",
    ] = "canonical_prematch_predictions"
    fixture_ids: list[str] = Field(default_factory=list)
    competition_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    as_of_time_utc: datetime | None = None
    window_hours: int = Field(default=72, ge=1, le=720)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    prediction_limit: int = Field(default=100, ge=1, le=500)
    enforce_odds_quality_gate: bool = True
    run_parlay_generation: bool = True
    parlay_pass_type: str = "2x1"
    parlay_unit_stake: float = Field(default=2.0, gt=0.0)
    parlay_max_budget: float | None = Field(default=20.0, gt=0.0)
    parlay_allowed_markets: list[str] = Field(default_factory=lambda: ["1x2", "cn_handicap_1x2"])
    parlay_min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    parlay_min_model_edge: float = 0.0
    parlay_min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    parlay_candidate_limit: int = Field(default=100, ge=1, le=1_000)
    parlay_model_version: str | None = Field(default=None, min_length=1)


class PrematchWorkflowRunResponse(BaseModel):
    result: PrematchWorkflowResult
    stale: bool = False
    fallback_used: bool = False


class PrematchWorkflowRunRecordPayload(BaseModel):
    prematch_workflow_run_id: int = Field(gt=0)
    status: Literal["running", "completed", "failed"]
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    prediction_job_run_id: int | None = Field(default=None, gt=0)
    prediction_job_type: (
        Literal[
            "mock_prematch_predictions",
            "canonical_prematch_predictions",
        ]
        | None
    ) = None
    prediction_fixture_count: int = Field(ge=0)
    prediction_generated_count: int = Field(ge=0)
    parlay_generated_count: int = Field(ge=0)
    parlay_recommendation_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None


class PrematchWorkflowRunListResponse(BaseModel):
    items: list[PrematchWorkflowRunRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderGovernanceResponse(BaseModel):
    providers: list[ProviderAuthorizationRecord]
    competition_readiness: list[CompetitionOnboardingAssessment]
    model_promotion_review: ModelPromotionReview
    rollback_plan: ModelRollbackPlan
    generated_at_utc: datetime
    stale: bool = False
    fallback_used: bool = False


class ProviderAuthorizationReviewRequest(BaseModel):
    provider_name: str = Field(min_length=1)
    review_reference: str = Field(min_length=1, max_length=120)
    review_status: ProviderAuthorizationReviewStatus
    reviewed_by: str = Field(default="admin_api", min_length=1, max_length=120)
    reviewed_at_utc: datetime | None = None
    terms_url: str | None = Field(default=None, max_length=500)
    terms_version_hash: str | None = Field(default=None, max_length=160)
    allowed_use: str = Field(min_length=1, max_length=240)
    commercial_use_allowed: bool = False
    retention_allowed: bool = False
    historical_data_allowed: bool = False
    redistribution_allowed: bool = False
    rate_limit: str | None = Field(default=None, max_length=240)
    next_review_due_at_utc: datetime | None = None
    owner: str = Field(default="nutmeg-ops", min_length=1, max_length=120)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=1_000)


class ProviderAuthorizationReviewRecordPayload(BaseModel):
    provider_authorization_review_id: int = Field(gt=0)
    provider_name: str
    review_reference: str
    review_status: ProviderAuthorizationReviewStatus
    reviewed_by: str
    reviewed_at_utc: datetime
    terms_url: str | None = None
    terms_version_hash: str | None = None
    allowed_use: str
    commercial_use_allowed: bool
    retention_allowed: bool
    historical_data_allowed: bool
    redistribution_allowed: bool
    rate_limit: str | None = None
    next_review_due_at_utc: datetime | None = None
    evidence_json: dict[str, object] = Field(default_factory=dict)
    notes: str = ""
    created_at_utc: datetime


class ProviderAuthorizationReviewResponse(BaseModel):
    item: ProviderAuthorizationReviewRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderAuthorizationReviewListResponse(BaseModel):
    items: list[ProviderAuthorizationReviewRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderOpsAuditEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=120)
    operator_name: str | None = Field(default=None, max_length=120)
    action_surface: str = Field(default="provider_ops", min_length=1, max_length=120)
    target_type: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=240)
    outcome: ProviderOpsAuditOutcome = "success"
    request_path: str | None = Field(default=None, max_length=500)
    request_method: str | None = Field(default=None, max_length=16)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderOpsAuditEventRecordPayload(BaseModel):
    provider_ops_audit_event_id: int = Field(gt=0)
    event_type: str
    operator_name: str | None = None
    action_surface: str
    target_type: str | None = None
    target_id: str | None = None
    outcome: ProviderOpsAuditOutcome
    request_path: str | None = None
    request_method: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at_utc: datetime


class ProviderOpsAuditEventResponse(BaseModel):
    item: ProviderOpsAuditEventRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderOpsAuditEventListResponse(BaseModel):
    items: list[ProviderOpsAuditEventRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderOpsRunHistoryRequest(BaseModel):
    run_name: str = Field(min_length=1, max_length=120)
    run_type: str = Field(default="vps_helper", min_length=1, max_length=80)
    source: str = Field(default="vps", min_length=1, max_length=120)
    status: ProviderOpsRunStatus = "success"
    operator_name: str | None = Field(default=None, max_length=120)
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    exit_code: int | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)
    output_excerpt: str | None = Field(default=None, max_length=2000)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderOpsRunHistoryRecordPayload(BaseModel):
    provider_ops_run_id: int = Field(gt=0)
    run_name: str
    run_type: str
    source: str
    status: ProviderOpsRunStatus
    operator_name: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    exit_code: int | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)
    output_excerpt: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at_utc: datetime


class ProviderOpsRunHistoryResponse(BaseModel):
    item: ProviderOpsRunHistoryRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderOpsRunHistoryListResponse(BaseModel):
    items: list[ProviderOpsRunHistoryRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderRuntimeCredentialsResponse(ProviderRuntimeCredentialResponse):
    pass


class ProviderApiKeyChecklistPayload(ProviderApiKeyChecklistResponse):
    pass


class ProviderRuntimeProbesResponse(ProviderRuntimeProbeResponse):
    pass


class ProviderRuntimeMonitoringSnapshotRequest(BaseModel):
    live_probe: bool = False


ProviderRuntimeIncidentThreshold = Literal["always", "P0", "P1", "P2"]
ProviderRuntimeIncidentStatus = Literal["open", "acknowledged", "resolved", "ignored"]
ProviderRuntimeIncidentNotificationStatus = Literal[
    "not_configured",
    "queued",
    "sent",
    "skipped",
    "failed",
]


class ProviderRuntimeMonitoringSnapshotRecordPayload(BaseModel):
    provider_runtime_snapshot_id: int | None = Field(default=None, gt=0)
    provider_name: str
    capability: str
    probe_status: ProviderRuntimeSnapshotStatus
    key_configured: bool
    live_probe: bool
    safe_to_call_real_provider: bool
    latency_ms: int | None = Field(default=None, ge=0)
    error_rate: float | None = Field(default=None, ge=0, le=1)
    success_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    rate_limit_remaining: int | None = Field(default=None, ge=0)
    quota_window: str | None = None
    fallback_used: bool
    message: str
    next_action: ProviderRuntimeMonitorNextAction
    metadata_json: dict[str, object] = Field(default_factory=dict)
    observed_at_utc: datetime


class ProviderRuntimeMonitoringSummaryPayload(BaseModel):
    provider_count: int = Field(ge=0)
    healthy_count: int = Field(ge=0)
    degraded_count: int = Field(ge=0)
    rate_limited_count: int = Field(ge=0)
    auth_failed_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    not_configured_count: int = Field(ge=0)
    fallback_provider_count: int = Field(ge=0)
    average_latency_ms: float | None = Field(default=None, ge=0)
    latest_observed_at_utc: datetime | None = None


class ProviderRuntimeMonitoringAlertPayload(BaseModel):
    alert_id: str
    severity: ProviderRuntimeAlertSeverity
    provider_name: str | None = None
    capability: str | None = None
    metric: str
    current_value: float | str | None = None
    threshold: float | str | None = None
    message: str
    recommended_action: str


class ProviderRuntimeMonitoringThresholdPayload(ProviderRuntimeMonitoringThresholds):
    pass


class ProviderRuntimeMonitoringResponse(BaseModel):
    items: list[ProviderRuntimeMonitoringSnapshotRecordPayload] = Field(default_factory=list)
    summary: ProviderRuntimeMonitoringSummaryPayload
    alert_level: ProviderRuntimeAlertLevel
    alerts: list[ProviderRuntimeMonitoringAlertPayload] = Field(default_factory=list)
    thresholds: ProviderRuntimeMonitoringThresholdPayload = Field(
        default_factory=ProviderRuntimeMonitoringThresholdPayload
    )
    generated_at_utc: datetime
    stale: bool = False
    fallback_used: bool = False


class ProviderRuntimeIncidentReportRequest(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=120)
    created_by: str = Field(default="nutmeg-ops", min_length=1, max_length=120)
    record_when_alert_level: ProviderRuntimeIncidentThreshold = "P1"
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderRuntimeIncidentReportRecordPayload(BaseModel):
    provider_runtime_incident_report_id: int = Field(gt=0)
    alert_level: ProviderRuntimeAlertLevel
    alert_count: int = Field(ge=0)
    snapshot_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)
    alerts_json: list[dict[str, object]] = Field(default_factory=list)
    thresholds_json: dict[str, object] = Field(default_factory=dict)
    source: str
    created_by: str
    metadata_json: dict[str, object] = Field(default_factory=dict)
    incident_status: ProviderRuntimeIncidentStatus = "open"
    acknowledged_by: str | None = None
    acknowledged_at_utc: datetime | None = None
    resolved_by: str | None = None
    resolved_at_utc: datetime | None = None
    resolution_note: str | None = None
    notification_status: ProviderRuntimeIncidentNotificationStatus = "not_configured"
    notification_payload_json: dict[str, object] = Field(default_factory=dict)
    updated_at_utc: datetime | None = None
    created_at_utc: datetime


class ProviderRuntimeIncidentReportResponse(BaseModel):
    recorded: bool
    item: ProviderRuntimeIncidentReportRecordPayload | None = None
    monitoring: ProviderRuntimeMonitoringResponse
    stale: bool = False
    fallback_used: bool = False


class ProviderRuntimeIncidentTrendBucketPayload(BaseModel):
    bucket_date: str
    total_count: int = Field(default=0, ge=0)
    open_count: int = Field(default=0, ge=0)
    acknowledged_count: int = Field(default=0, ge=0)
    resolved_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)
    active_count: int = Field(default=0, ge=0)
    p0_count: int = Field(default=0, ge=0)
    p1_count: int = Field(default=0, ge=0)
    p2_count: int = Field(default=0, ge=0)
    notification_failed_count: int = Field(default=0, ge=0)


class ProviderRuntimeIncidentSummaryPayload(BaseModel):
    lookback_days: int = Field(default=30, ge=1, le=3650)
    total_count: int = Field(default=0, ge=0)
    open_count: int = Field(default=0, ge=0)
    acknowledged_count: int = Field(default=0, ge=0)
    resolved_count: int = Field(default=0, ge=0)
    ignored_count: int = Field(default=0, ge=0)
    active_count: int = Field(default=0, ge=0)
    p0_count: int = Field(default=0, ge=0)
    p1_count: int = Field(default=0, ge=0)
    p2_count: int = Field(default=0, ge=0)
    notification_failed_count: int = Field(default=0, ge=0)
    latest_created_at_utc: datetime | None = None
    mean_time_to_resolve_minutes: float | None = Field(default=None, ge=0)
    trend_buckets: list[ProviderRuntimeIncidentTrendBucketPayload] = Field(default_factory=list)


class ProviderRuntimeIncidentReportListResponse(BaseModel):
    items: list[ProviderRuntimeIncidentReportRecordPayload] = Field(default_factory=list)
    summary: ProviderRuntimeIncidentSummaryPayload = Field(
        default_factory=ProviderRuntimeIncidentSummaryPayload
    )
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    total_count: int = Field(default=0, ge=0)
    has_more: bool = False
    stale: bool = False
    fallback_used: bool = False


class ProviderRuntimeIncidentRetentionRequest(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class ProviderRuntimeIncidentRetentionResponse(BaseModel):
    deleted_count: int = Field(ge=0)
    retention_days: int = Field(ge=1, le=3650)
    stale: bool = False
    fallback_used: bool = False


class ProviderRuntimeIncidentStatusUpdateRequest(BaseModel):
    incident_status: ProviderRuntimeIncidentStatus
    updated_by: str | None = Field(default=None, min_length=1, max_length=120)
    resolution_note: str | None = Field(default=None, max_length=500)


class ProviderRuntimeIncidentStatusUpdateResponse(BaseModel):
    item: ProviderRuntimeIncidentReportRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderFixtureSyncRequest(BaseModel):
    provider_competition_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    canonical_competition_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True


class ProviderSyncRunPayload(BaseModel):
    provider_sync_run_id: int = Field(gt=0)
    status: Literal["running", "completed", "failed"]
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    entity_count: int = Field(ge=0)
    error_message: str | None = None


class ProviderRawPayloadSummary(BaseModel):
    payload_id: int = Field(gt=0)
    endpoint: str
    request_hash: str


class ProviderCanonicalWriteSummaryPayload(BaseModel):
    competitions: int = Field(ge=0)
    seasons: int = Field(ge=0)
    teams: int = Field(ge=0)
    fixtures: int = Field(ge=0)
    results: int = Field(ge=0)
    provider_mappings: int = Field(ge=0)
    canonical_fixture_ids: list[str] = Field(default_factory=list)


class ProviderFixtureSyncResponse(BaseModel):
    provider_name: str
    provider_competition_id: str
    canonical_competition_id: str
    season: str
    dry_run: bool
    request_params: dict[str, object] = Field(default_factory=dict)
    normalized_fixture_count: int = Field(ge=0)
    sync_run: ProviderSyncRunPayload | None = None
    raw_payload: ProviderRawPayloadSummary | None = None
    canonical_write: ProviderCanonicalWriteSummaryPayload | None = None
    sample_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderEventOddsSyncRequest(BaseModel):
    sport_key: str = Field(min_length=1)
    provider_event_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    regions: str = Field(default="eu", min_length=1)
    markets: str = Field(default="h2h,spreads", min_length=1)
    bookmakers: str | None = Field(default=None, min_length=1)
    dry_run: bool = True


class ProviderOddsWriteSummaryPayload(BaseModel):
    odds_snapshots: int = Field(ge=0)
    inserted_snapshots: int = Field(default=0, ge=0)
    updated_snapshots: int = Field(default=0, ge=0)
    provider_mappings: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    canonical_fixture_id: str


class ProviderEventOddsSyncResponse(BaseModel):
    provider_name: str
    sport_key: str
    provider_event_id: str
    canonical_fixture_id: str
    dry_run: bool
    request_params: dict[str, object] = Field(default_factory=dict)
    normalized_odds_count: int = Field(ge=0)
    bookmaker_count: int = Field(ge=0)
    market_types: list[str] = Field(default_factory=list)
    sync_run: ProviderSyncRunPayload | None = None
    raw_payload: ProviderRawPayloadSummary | None = None
    odds_write: ProviderOddsWriteSummaryPayload | None = None
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderTeamMappingPayload(BaseModel):
    provider_team_id: str = Field(min_length=1)
    canonical_team_id: str = Field(min_length=1)


class ProviderFixtureAvailabilitySyncRequest(BaseModel):
    provider_fixture_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    team_mappings: list[ProviderTeamMappingPayload] = Field(min_length=1)
    dry_run: bool = True


class ProviderAvailabilityWriteSummaryPayload(BaseModel):
    lineup_snapshots: int = Field(ge=0)
    availability_snapshots: int = Field(ge=0)
    provider_mappings: int = Field(ge=0)
    player_mappings: int = Field(ge=0)
    canonical_fixture_id: str
    canonical_team_ids: list[str] = Field(default_factory=list)


class ProviderFixtureAvailabilitySyncResponse(BaseModel):
    provider_name: str
    provider_fixture_id: str
    canonical_fixture_id: str
    provider_team_ids: list[str] = Field(default_factory=list)
    dry_run: bool
    request_params: dict[str, object] = Field(default_factory=dict)
    normalized_lineup_count: int = Field(ge=0)
    normalized_availability_count: int = Field(ge=0)
    provider_observation_count: int = Field(default=0, ge=0)
    sync_run: ProviderSyncRunPayload | None = None
    raw_payloads: list[ProviderRawPayloadSummary] = Field(default_factory=list)
    availability_write: ProviderAvailabilityWriteSummaryPayload | None = None
    sample_players: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderOddsCoverageResponse(BaseModel):
    report: CompetitionOddsCoverageReport
    stale: bool = False
    fallback_used: bool = False


class ProviderOddsCoverageGapResponse(BaseModel):
    report: OddsCoverageGapReport
    stale: bool = False
    fallback_used: bool = False


class ProviderEntityMappingListResponse(BaseModel):
    items: list[ProviderEntityMappingRecord] = Field(default_factory=list)
    summary: list[ProviderEntityMappingSummary] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderTheOddsApiFixtureMappingBootstrapRequest(BaseModel):
    provider_competition_id: str = Field(default="PL", min_length=1)
    canonical_competition_id: str = Field(default="EPL", min_length=1)
    season: str = Field(default="2025", min_length=1)
    sport_key: str = Field(default="soccer_epl", min_length=1)
    regions: str = Field(default="eu", min_length=1)
    markets: str = Field(default="h2h", min_length=1)
    bookmakers: str | None = Field(default=None, min_length=1)
    kickoff_tolerance_minutes: int = Field(default=180, ge=1, le=720)
    min_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    max_provider_events: int = Field(default=100, ge=1, le=500)
    dry_run: bool = True


class ProviderSportMonksFixtureMappingBootstrapRequest(BaseModel):
    source_provider_competition_id: str = Field(default="PL", min_length=1)
    canonical_competition_id: str = Field(default="EPL", min_length=1)
    source_season: str = Field(default="2025", min_length=1)
    sportmonks_competition_id: str = Field(min_length=1)
    sportmonks_season: str = Field(min_length=1)
    kickoff_tolerance_minutes: int = Field(default=180, ge=1, le=720)
    min_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    max_provider_fixtures: int = Field(default=500, ge=1, le=1000)
    dry_run: bool = True


class ProviderSportMonksFixtureMappingBackfillRequest(BaseModel):
    source_provider_competition_id: str = Field(default="PL", min_length=1)
    canonical_competition_id: str = Field(default="EPL", min_length=1)
    source_season: str = Field(default="2025", min_length=1)
    target_competition_name: str = Field(default="Premier League", min_length=1)
    target_country_name: str | None = Field(default="England", min_length=1)
    target_season: str | None = Field(default=None, min_length=1)
    min_competition_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_competition_candidates: int = Field(default=5, ge=1, le=25)
    max_season_candidates: int = Field(default=6, ge=1, le=20)
    kickoff_tolerance_minutes: int = Field(default=180, ge=1, le=720)
    min_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    max_provider_fixtures: int = Field(default=500, ge=1, le=1000)
    dry_run: bool = True


class ProviderApiFootballFixtureMappingBootstrapRequest(BaseModel):
    source_provider_competition_id: str = Field(default="PL", min_length=1)
    canonical_competition_id: str = Field(default="EPL", min_length=1)
    source_season: str = Field(default="2025", min_length=1)
    api_football_league_id: str = Field(default="39", min_length=1)
    api_football_season: str = Field(default="2025", min_length=1)
    kickoff_tolerance_minutes: int = Field(default=180, ge=1, le=720)
    min_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    max_provider_fixtures: int = Field(default=500, ge=1, le=1000)
    dry_run: bool = True


class ProviderApiFootballCompetitionDiscoveryRequest(BaseModel):
    target_competition_name: str = Field(default="Premier League", min_length=1)
    target_country_name: str | None = Field(default="England", min_length=1)
    target_season: str = Field(default="2025", min_length=1)
    min_competition_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_competition_candidates: int = Field(default=5, ge=1, le=25)
    max_season_candidates: int = Field(default=6, ge=1, le=20)


class ProviderApiFootballCompetitionDiscoveryResponse(BaseModel):
    result: ApiFootballCompetitionDiscoveryResult
    stale: bool = False
    fallback_used: bool = False


class ProviderSportMonksCompetitionDiscoveryRequest(BaseModel):
    target_competition_name: str = Field(default="Premier League", min_length=1)
    target_country_name: str | None = Field(default="England", min_length=1)
    target_season: str = Field(default="2025", min_length=1)
    min_competition_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_competition_candidates: int = Field(default=5, ge=1, le=25)
    max_season_candidates: int = Field(default=6, ge=1, le=20)


class ProviderSportMonksCompetitionDiscoveryResponse(BaseModel):
    result: SportMonksCompetitionDiscoveryResult
    stale: bool = False
    fallback_used: bool = False


class ProviderFixtureMappingBootstrapResponse(BaseModel):
    result: FixtureMappingBootstrapResult
    stale: bool = False
    fallback_used: bool = False


class ProviderSportMonksFixtureMappingBackfillResponse(BaseModel):
    result: SportMonksFixtureMappingBackfillResult
    stale: bool = False
    fallback_used: bool = False


class ProviderMappedEventOddsSyncRequest(BaseModel):
    canonical_competition_id: str = Field(default="EPL", min_length=1)
    sport_key: str = Field(default="soccer_epl", min_length=1)
    regions: str = Field(default="eu", min_length=1)
    markets: str = Field(default="h2h,spreads", min_length=1)
    bookmakers: str | None = Field(default=None, min_length=1)
    min_mapping_confidence: float = Field(default=0.82, ge=0.0, le=1.0)
    max_mappings: int = Field(default=20, ge=1, le=100)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    include_coverage: bool = True
    dry_run: bool = True
    operator_approved: bool = False
    operator_approval_note: str | None = Field(default=None, max_length=500)


class ProviderMappedEventOddsSyncResponse(BaseModel):
    result: TheOddsApiMappedEventOddsSyncResult
    coverage: CompetitionOddsCoverageReport | None = None
    stale: bool = False
    fallback_used: bool = False


class ProviderSportMonksFallbackOddsProbeRequest(BaseModel):
    competition_id: str = Field(default="EPL", min_length=1)
    primary_provider: str = Field(default="the-odds-api", min_length=1)
    window_days: int = Field(default=90, ge=1, le=730)
    max_snapshot_lag_hours: int = Field(default=168, ge=1, le=168)
    limit: int = Field(default=50, ge=1, le=100)
    as_of_time_utc: datetime | None = None
    live_provider_probe: bool = False


class ProviderSportMonksFallbackOddsProbeResponse(BaseModel):
    result: SportMonksFallbackOddsProbeResult
    stale: bool = False
    fallback_used: bool = False


class ProviderMappingReviewRequest(BaseModel):
    provider: str | None = Field(default=None, min_length=1)
    entity_type: str | None = Field(default=None, min_length=1)
    canonical_entity_id: str | None = Field(default=None, min_length=1)
    low_confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    stale_after_days: int = Field(default=180, ge=1, le=3650)
    as_of_time_utc: datetime | None = None
    limit: int = Field(default=1000, ge=1, le=2000)
    dry_run: bool = True


class ProviderMappingReviewRunRecordPayload(BaseModel):
    provider_mapping_review_run_id: int = Field(gt=0)
    provider: str | None = None
    entity_type: str | None = None
    canonical_entity_id: str | None = None
    low_confidence_threshold: float = Field(ge=0.0, le=1.0)
    stale_after_days: int = Field(ge=1)
    checked_mapping_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    info_count: int = Field(ge=0)
    issues: list[ProviderMappingReviewIssue] = Field(default_factory=list)
    requested_by: str | None = None
    created_at_utc: datetime


class ProviderMappingReviewResponse(BaseModel):
    result: ProviderMappingReviewResult
    stored_review: ProviderMappingReviewRunRecordPayload | None = None
    stale: bool = False
    fallback_used: bool = False


class ProviderMappingReviewRunListResponse(BaseModel):
    items: list[ProviderMappingReviewRunRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderConflictEvaluationRequest(BaseModel):
    provider: str | None = Field(default=None, min_length=1)
    entity_type: str | None = Field(default=None, min_length=1)
    canonical_entity_id: str | None = Field(default=None, min_length=1)
    capability: str | None = Field(default=None, min_length=1)
    low_confidence_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    stale_after_days: int = Field(default=180, ge=1, le=3650)
    observation_lookback_hours: int = Field(default=168, ge=1, le=8760)
    include_observations: bool = True
    as_of_time_utc: datetime | None = None
    limit: int = Field(default=1000, ge=1, le=2000)
    dry_run: bool = True


class ProviderConflictEventRecordPayload(BaseModel):
    provider_conflict_event_id: int = Field(gt=0)
    source_review_run_id: int | None = None
    source_issue_id: str | None = None
    conflict_type: str
    severity: str
    entity_type: str
    canonical_entity_id: str
    provider_names: list[str] = Field(default_factory=list)
    provider_entity_ids: list[str] = Field(default_factory=list)
    trusted_provider: str | None = None
    resolution_status: ProviderConflictStatus
    data_quality_score_delta: float
    evidence_json: dict[str, object] = Field(default_factory=dict)
    recommended_action: str
    requested_by: str | None = None
    created_at_utc: datetime
    resolved_at_utc: datetime | None = None


class ProviderConflictEvaluationResponse(BaseModel):
    result: ProviderConflictEvaluationResult
    stored_events: list[ProviderConflictEventRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderConflictEventListResponse(BaseModel):
    items: list[ProviderConflictEventRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderConflictResolutionRequest(BaseModel):
    resolution_status: ProviderConflictStatus
    resolution_note: str | None = Field(default=None, max_length=500)


class ProviderConflictResolutionResponse(BaseModel):
    item: ProviderConflictEventRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderOnboardingAssessmentRequest(BaseModel):
    competition_id: str = Field(min_length=1)
    competition_name: str | None = Field(default=None, min_length=1)
    target_stage: Literal["beta", "production"] = "beta"
    window_days: int = Field(default=90, ge=1, le=730)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    as_of_time_utc: datetime | None = None
    schedule_coverage: float = Field(ge=0.0, le=1.0)
    result_coverage: float = Field(ge=0.0, le=1.0)
    lineup_injury_coverage: float = Field(ge=0.0, le=1.0)
    historical_stats_completeness: float = Field(ge=0.0, le=1.0)
    provider_consistency: float = Field(ge=0.0, le=1.0)
    historical_sample_size: int = Field(ge=0)
    complete_seasons: int = Field(default=0, ge=0)
    market_resolver_tests_passed: bool
    score_grid_generation_passed: bool
    log_loss_delta_vs_baseline: float | None = None
    brier_delta_vs_baseline: float | None = None
    calibration_shift: float | None = Field(default=None, ge=0.0)
    dry_run: bool = True


class ProviderOnboardingAssessmentRecordPayload(BaseModel):
    assessment_id: int = Field(gt=0)
    created_at_utc: datetime


class ProviderOnboardingAssessmentResponse(BaseModel):
    assessment: CompetitionOnboardingAssessment
    odds_coverage_report: CompetitionOddsCoverageReport
    stored_assessment: ProviderOnboardingAssessmentRecordPayload | None = None
    stale: bool = False
    fallback_used: bool = False


class ProviderOnboardingAssessmentListItem(BaseModel):
    assessment: CompetitionOnboardingAssessment
    stored_assessment: ProviderOnboardingAssessmentRecordPayload


class ProviderOnboardingAssessmentListResponse(BaseModel):
    items: list[ProviderOnboardingAssessmentListItem] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowFixtureTaskPayload(BaseModel):
    provider_competition_id: str = Field(min_length=1)
    season: str = Field(min_length=1)
    canonical_competition_id: str | None = Field(default=None, min_length=1)


class ProviderSyncWorkflowOddsTaskPayload(BaseModel):
    sport_key: str = Field(min_length=1)
    provider_event_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    regions: str = Field(default="eu", min_length=1)
    markets: str = Field(default="h2h,spreads", min_length=1)
    bookmakers: str | None = Field(default=None, min_length=1)


class ProviderSyncWorkflowAvailabilityTaskPayload(BaseModel):
    provider_fixture_id: str = Field(min_length=1)
    canonical_fixture_id: str = Field(min_length=1)
    team_mappings: list[ProviderTeamMappingPayload] = Field(min_length=1)


class ProviderSyncWorkflowPrematchPayload(BaseModel):
    prediction_job_type: Literal[
        "mock_prematch_predictions",
        "canonical_prematch_predictions",
    ] = "canonical_prematch_predictions"
    fixture_ids: list[str] = Field(default_factory=list)
    competition_id: str | None = Field(default=None, min_length=1)
    as_of_time_utc: datetime | None = None
    window_hours: int = Field(default=72, ge=1, le=720)
    max_snapshot_lag_hours: int = Field(default=24, ge=1, le=168)
    prediction_limit: int = Field(default=100, ge=1, le=500)
    enforce_odds_quality_gate: bool = True
    run_parlay_generation: bool = True
    parlay_pass_type: str = "2x1"
    parlay_unit_stake: float = Field(default=2.0, gt=0.0)
    parlay_max_budget: float | None = Field(default=20.0, gt=0.0)
    parlay_allowed_markets: list[str] = Field(default_factory=lambda: ["1x2", "cn_handicap_1x2"])
    parlay_min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    parlay_min_model_edge: float = 0.0
    parlay_min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    parlay_candidate_limit: int = Field(default=100, ge=1, le=1_000)
    parlay_model_version: str | None = Field(default=None, min_length=1)


class ProviderSyncWorkflowRunRequest(BaseModel):
    dry_run: bool = True
    fixture_sync: ProviderSyncWorkflowFixtureTaskPayload | None = None
    odds_syncs: list[ProviderSyncWorkflowOddsTaskPayload] = Field(default_factory=list)
    availability_syncs: list[ProviderSyncWorkflowAvailabilityTaskPayload] = Field(
        default_factory=list
    )
    run_conflict_detection: bool = False
    conflict_observation_lookback_hours: int = Field(default=168, ge=1, le=8_760)
    conflict_limit: int = Field(default=1_000, ge=1, le=5_000)
    run_prematch_workflow: bool = False
    prematch: ProviderSyncWorkflowPrematchPayload | None = None
    operator_approved: bool = False
    operator_approval_note: str | None = Field(default=None, max_length=500)
    provider_sync_workflow_template_id: int | None = Field(default=None, gt=0)


class ProviderSyncWorkflowPreflightResponse(BaseModel):
    result: ProviderSyncWorkflowPreflightResult
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowRunResponse(BaseModel):
    result: ProviderSyncWorkflowResult
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowRunRecordPayload(BaseModel):
    provider_sync_workflow_run_id: int = Field(gt=0)
    status: Literal["running", "completed", "failed"]
    dry_run: bool
    requested_by: str | None = None
    started_at_utc: datetime
    completed_at_utc: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    fixture_sync_run_id: int | None = Field(default=None, gt=0)
    odds_sync_run_ids: list[int] = Field(default_factory=list)
    availability_sync_run_ids: list[int] = Field(default_factory=list)
    fixture_count: int = Field(ge=0)
    odds_snapshot_count: int = Field(ge=0)
    availability_snapshot_count: int = Field(ge=0)
    raw_payload_ids: list[int] = Field(default_factory=list)
    canonical_fixture_ids: list[str] = Field(default_factory=list)
    prematch_workflow_run_id: int | None = Field(default=None, gt=0)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderSyncWorkflowRunListResponse(BaseModel):
    items: list[ProviderSyncWorkflowRunRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowRunDetailResponse(BaseModel):
    item: ProviderSyncWorkflowRunRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowTemplateCreateRequest(ProviderSyncWorkflowRunRequest):
    template_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ProviderSyncWorkflowTemplateUpdateRequest(ProviderSyncWorkflowTemplateCreateRequest):
    pass


class ProviderSyncWorkflowTemplateArchiveRequest(BaseModel):
    archive_reason: str | None = Field(default=None, max_length=500)


class ProviderSyncWorkflowTemplateRecordPayload(BaseModel):
    provider_sync_workflow_template_id: int = Field(gt=0)
    template_name: str
    description: str | None = None
    dry_run: bool
    fixture_sync: dict[str, object] | None = None
    odds_syncs: list[dict[str, object]] = Field(default_factory=list)
    availability_syncs: list[dict[str, object]] = Field(default_factory=list)
    run_conflict_detection: bool = False
    conflict_observation_lookback_hours: int = Field(ge=1, le=8_760)
    conflict_limit: int = Field(ge=1, le=5_000)
    created_by: str | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
    archived_at_utc: datetime | None = None
    archived_by: str | None = None
    archive_reason: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    preflight_result: ProviderSyncWorkflowPreflightResult


class ProviderSyncWorkflowTemplateResponse(BaseModel):
    item: ProviderSyncWorkflowTemplateRecordPayload
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowTemplateListResponse(BaseModel):
    items: list[ProviderSyncWorkflowTemplateRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False


class ProviderSyncWorkflowApprovalRecordPayload(BaseModel):
    provider_sync_workflow_approval_id: int = Field(gt=0)
    approval_type: str
    approval_status: Literal["approved", "superseded", "revoked"]
    provider_sync_workflow_template_id: int | None = Field(default=None, gt=0)
    provider_sync_workflow_run_id: int | None = Field(default=None, gt=0)
    approved_by: str | None = None
    approved_at_utc: datetime
    approval_note: str | None = None
    request_payload_json: dict[str, object] = Field(default_factory=dict)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class ProviderSyncWorkflowApprovalListResponse(BaseModel):
    items: list[ProviderSyncWorkflowApprovalRecordPayload] = Field(default_factory=list)
    stale: bool = False
    fallback_used: bool = False
