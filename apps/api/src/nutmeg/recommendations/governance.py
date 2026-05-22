from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams

type RecommendationStrategyPromotionDecision = Literal[
    "shadow_candidate",
    "keep_experiment",
]
type RecommendationStrategySelectionSource = Literal[
    "explicit_request",
    "governance_overview",
    "baseline_fallback",
]

GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY = """
SELECT
  %(strategy)s AS strategy,
  %(pass_type)s AS pass_type,
  %(mode)s AS mode,
  COUNT(*)::int AS sample_size,
  COUNT(*) FILTER (WHERE evaluation_status = 'settled')::int AS settled_run_count,
  COUNT(*) FILTER (WHERE hit IS TRUE)::int AS hit_count,
  COALESCE(SUM(total_stake), 0) AS total_stake,
  COALESCE(SUM(gross_payout), 0) AS gross_payout,
  COALESCE(SUM(profit_loss), 0) AS profit_loss,
  CASE
    WHEN COALESCE(SUM(total_stake), 0) > 0
      THEN COALESCE(SUM(profit_loss), 0) / SUM(total_stake)
    ELSE NULL
  END AS roi,
  CASE
    WHEN COUNT(*) FILTER (WHERE evaluation_status = 'settled') > 0
      THEN (
        COUNT(*) FILTER (WHERE hit IS TRUE)::numeric
        / COUNT(*) FILTER (WHERE evaluation_status = 'settled')
      )
    ELSE NULL
  END AS hit_rate,
  AVG(expected_roi_at_recommendation) AS average_expected_roi,
  AVG(expected_hit_probability_at_recommendation) AS average_expected_hit_probability,
  AVG(hit_calibration_error) AS average_hit_calibration_error,
  AVG(ABS(hit_calibration_error)) AS mean_absolute_hit_calibration_error,
  COUNT(*) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,single,result_status}'
      IN ('won', 'lost')
  )::int AS single_focus_sample_size,
  COUNT(*) FILTER (
    WHERE (settlement_detail_json #>> '{focus_policy_evaluation,single,hit}')::boolean
      IS TRUE
  )::int AS single_focus_hit_count,
  CASE
    WHEN COUNT(*) FILTER (
      WHERE settlement_detail_json #>> '{focus_policy_evaluation,single,result_status}'
        IN ('won', 'lost')
    ) > 0
      THEN (
        COUNT(*) FILTER (
          WHERE (settlement_detail_json #>> '{focus_policy_evaluation,single,hit}')::boolean
            IS TRUE
        )::numeric
        / COUNT(*) FILTER (
          WHERE settlement_detail_json #>> '{focus_policy_evaluation,single,result_status}'
            IN ('won', 'lost')
        )
      )
    ELSE NULL
  END AS single_focus_hit_rate,
  AVG(
    (settlement_detail_json #>> '{focus_policy_evaluation,single,calibration_error}')::numeric
  ) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,single,calibration_error}'
      IS NOT NULL
  ) AS average_single_focus_calibration_error,
  AVG(
    ABS(
      (settlement_detail_json #>> '{focus_policy_evaluation,single,calibration_error}')::numeric
    )
  ) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,single,calibration_error}'
      IS NOT NULL
  ) AS mean_absolute_single_focus_calibration_error,
  COUNT(*) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,upset,result_status}'
      IN ('won', 'lost')
  )::int AS upset_focus_sample_size,
  COUNT(*) FILTER (
    WHERE (settlement_detail_json #>> '{focus_policy_evaluation,upset,hit}')::boolean
      IS TRUE
  )::int AS upset_focus_capture_count,
  CASE
    WHEN COUNT(*) FILTER (
      WHERE settlement_detail_json #>> '{focus_policy_evaluation,upset,result_status}'
        IN ('won', 'lost')
    ) > 0
      THEN (
        COUNT(*) FILTER (
          WHERE (settlement_detail_json #>> '{focus_policy_evaluation,upset,hit}')::boolean
            IS TRUE
        )::numeric
        / COUNT(*) FILTER (
          WHERE settlement_detail_json #>> '{focus_policy_evaluation,upset,result_status}'
            IN ('won', 'lost')
        )
      )
    ELSE NULL
  END AS upset_focus_capture_rate,
  AVG(
    (settlement_detail_json #>> '{focus_policy_evaluation,upset,calibration_error}')::numeric
  ) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,upset,calibration_error}'
      IS NOT NULL
  ) AS average_upset_focus_calibration_error,
  AVG(
    ABS(
      (settlement_detail_json #>> '{focus_policy_evaluation,upset,calibration_error}')::numeric
    )
  ) FILTER (
    WHERE settlement_detail_json #>> '{focus_policy_evaluation,upset,calibration_error}'
      IS NOT NULL
  ) AS mean_absolute_upset_focus_calibration_error,
  MIN(evaluation_time_utc) AS first_evaluation_time_utc,
  MAX(evaluation_time_utc) AS last_evaluation_time_utc
FROM recommendation_run_evaluations
WHERE strategy = %(strategy)s
  AND pass_type = %(pass_type)s
  AND mode = %(mode)s
  AND evaluation_status = 'settled'
  AND NOT EXISTS (
    SELECT 1
    FROM recommendation_runs successor
    WHERE successor.status <> 'invalidated'
      AND successor.explanation_json #>>
        '{internal_trace,successor_recompute,source_recommendation_run_id}'
        = recommendation_run_evaluations.recommendation_run_id::text
  )
  AND (%(window_start_utc)s::timestamptz IS NULL OR evaluation_time_utc >= %(window_start_utc)s)
  AND (%(window_end_utc)s::timestamptz IS NULL OR evaluation_time_utc <= %(window_end_utc)s)
"""

INSERT_RECOMMENDATION_STRATEGY_REVIEW_QUERY = """
INSERT INTO recommendation_strategy_reviews (
  review_key,
  candidate_strategy,
  baseline_strategy,
  pass_type,
  mode,
  decision,
  next_status,
  sample_size,
  baseline_sample_size,
  candidate_roi,
  baseline_roi,
  candidate_hit_rate,
  baseline_hit_rate,
  candidate_calibration_error,
  baseline_calibration_error,
  metrics_json,
  reasons_json,
  rollback_plan_json,
  window_start_utc,
  window_end_utc,
  source
) VALUES (
  %(review_key)s,
  %(candidate_strategy)s,
  %(baseline_strategy)s,
  %(pass_type)s,
  %(mode)s,
  %(decision)s,
  %(next_status)s,
  %(sample_size)s,
  %(baseline_sample_size)s,
  %(candidate_roi)s,
  %(baseline_roi)s,
  %(candidate_hit_rate)s,
  %(baseline_hit_rate)s,
  %(candidate_calibration_error)s,
  %(baseline_calibration_error)s,
  %(metrics_json)s::jsonb,
  %(reasons_json)s::jsonb,
  %(rollback_plan_json)s::jsonb,
  %(window_start_utc)s,
  %(window_end_utc)s,
  %(source)s
)
ON CONFLICT (review_key) DO UPDATE SET
  decision = EXCLUDED.decision,
  next_status = EXCLUDED.next_status,
  sample_size = EXCLUDED.sample_size,
  baseline_sample_size = EXCLUDED.baseline_sample_size,
  candidate_roi = EXCLUDED.candidate_roi,
  baseline_roi = EXCLUDED.baseline_roi,
  candidate_hit_rate = EXCLUDED.candidate_hit_rate,
  baseline_hit_rate = EXCLUDED.baseline_hit_rate,
  candidate_calibration_error = EXCLUDED.candidate_calibration_error,
  baseline_calibration_error = EXCLUDED.baseline_calibration_error,
  metrics_json = EXCLUDED.metrics_json,
  reasons_json = EXCLUDED.reasons_json,
  rollback_plan_json = EXCLUDED.rollback_plan_json,
  window_start_utc = EXCLUDED.window_start_utc,
  window_end_utc = EXCLUDED.window_end_utc,
  source = EXCLUDED.source
RETURNING recommendation_strategy_review_id, created_at
"""


class RecommendationStrategyEvidence(BaseModel):
    strategy: str
    pass_type: str
    mode: str
    sample_size: int = Field(ge=0)
    settled_run_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    total_stake: float = Field(ge=0.0)
    gross_payout: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_expected_roi: float | None = None
    average_expected_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_hit_calibration_error: float | None = None
    mean_absolute_hit_calibration_error: float | None = Field(default=None, ge=0.0)
    single_focus_sample_size: int = Field(default=0, ge=0)
    single_focus_hit_count: int = Field(default=0, ge=0)
    single_focus_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_single_focus_calibration_error: float | None = None
    mean_absolute_single_focus_calibration_error: float | None = Field(default=None, ge=0.0)
    upset_focus_sample_size: int = Field(default=0, ge=0)
    upset_focus_capture_count: int = Field(default=0, ge=0)
    upset_focus_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_upset_focus_calibration_error: float | None = None
    mean_absolute_upset_focus_calibration_error: float | None = Field(default=None, ge=0.0)
    first_evaluation_time_utc: datetime | None = None
    last_evaluation_time_utc: datetime | None = None


class RecommendationStrategyPromotionReview(BaseModel):
    candidate_strategy: str
    baseline_strategy: str
    pass_type: str
    mode: str
    decision: RecommendationStrategyPromotionDecision
    next_status: Literal["shadow", "experiment"]
    reasons: list[str] = Field(default_factory=list)


class RecommendationStrategyRollbackPlan(BaseModel):
    should_rollback: bool
    target_strategy: str | None = None
    reasons: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class RecommendationStrategyReviewOptions(BaseModel):
    candidate_strategy: str
    baseline_strategy: str = "accuracy_first"
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
    minimum_focus_sample_size: int = Field(default=30, ge=1)
    tolerated_single_focus_hit_rate_drop: float = Field(default=0.03, ge=0.0, le=1.0)
    tolerated_upset_focus_capture_rate_drop: float = Field(default=0.05, ge=0.0, le=1.0)
    tolerated_focus_calibration_error_delta: float = Field(default=0.06, ge=0.0)
    rollback_roi_floor: float = -0.10
    rollback_max_roi_underperformance: float = Field(default=0.10, ge=0.0)
    rollback_calibration_error_ceiling: float = Field(default=0.25, ge=0.0)
    rollback_focus_calibration_error_ceiling: float = Field(default=0.30, ge=0.0)
    dry_run: bool = True

    @property
    def normalized_window_start_utc(self) -> datetime | None:
        return _optional_aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime | None:
        return _optional_aware_utc(self.window_end_utc)


class RecommendationStrategyReviewArtifact(BaseModel):
    review_key: str
    candidate_evidence: RecommendationStrategyEvidence
    baseline_evidence: RecommendationStrategyEvidence
    promotion_review: RecommendationStrategyPromotionReview
    rollback_plan: RecommendationStrategyRollbackPlan
    metrics_json: dict[str, object] = Field(default_factory=dict)
    window_start_utc: datetime | None = None
    window_end_utc: datetime | None = None


class StoredRecommendationStrategyReview(BaseModel):
    recommendation_strategy_review_id: int = Field(gt=0)
    created_at: datetime
    artifact: RecommendationStrategyReviewArtifact


class RecommendationStrategyReviewRunResult(BaseModel):
    dry_run: bool
    stored_review: StoredRecommendationStrategyReview | None = None
    artifact: RecommendationStrategyReviewArtifact
    warnings: list[str] = Field(default_factory=list)


class RecommendationStrategyGovernanceItem(BaseModel):
    candidate_strategy: str
    baseline_strategy: str
    pass_type: str
    mode: str
    artifact: RecommendationStrategyReviewArtifact
    warnings: list[str] = Field(default_factory=list)


class RecommendationStrategyGovernanceOverview(BaseModel):
    generated_at_utc: datetime
    items: list[RecommendationStrategyGovernanceItem] = Field(default_factory=list)


class RecommendationStrategySelectionTrace(BaseModel):
    requested_strategy: str
    selected_strategy: str
    baseline_strategy: str
    pass_type: str
    mode: str
    source: RecommendationStrategySelectionSource
    review_key: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metric_deltas: dict[str, float | None] = Field(default_factory=dict)
    generated_at_utc: datetime


class RecommendationStrategyGovernanceDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute strategy governance reads and writes."""


class RecommendationStrategyGovernanceRepository(Protocol):
    def get_strategy_evidence(
        self,
        *,
        strategy: str,
        pass_type: str,
        mode: str,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> RecommendationStrategyEvidence:
        """Read aggregate recommendation strategy evidence."""

    def save_strategy_review(
        self,
        artifact: RecommendationStrategyReviewArtifact,
    ) -> StoredRecommendationStrategyReview:
        """Persist a recommendation strategy review."""


class PostgresRecommendationStrategyGovernanceRepository:
    def __init__(self, database: RecommendationStrategyGovernanceDatabaseExecutor) -> None:
        self.database = database

    def get_strategy_evidence(
        self,
        *,
        strategy: str,
        pass_type: str,
        mode: str,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> RecommendationStrategyEvidence:
        row = _required_row(
            self.database.fetch_one(
                GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY,
                {
                    "strategy": strategy,
                    "pass_type": pass_type,
                    "mode": mode,
                    "window_start_utc": _optional_aware_utc(window_start_utc),
                    "window_end_utc": _optional_aware_utc(window_end_utc),
                },
            )
        )
        return _strategy_evidence_from_row(row)

    def save_strategy_review(
        self,
        artifact: RecommendationStrategyReviewArtifact,
    ) -> StoredRecommendationStrategyReview:
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_STRATEGY_REVIEW_QUERY,
                _strategy_review_params(artifact),
            )
        )
        return StoredRecommendationStrategyReview(
            recommendation_strategy_review_id=_int(row["recommendation_strategy_review_id"]),
            created_at=_datetime(row["created_at"]),
            artifact=artifact,
        )


def run_recommendation_strategy_review(
    repository: RecommendationStrategyGovernanceRepository,
    *,
    options: RecommendationStrategyReviewOptions,
) -> RecommendationStrategyReviewRunResult:
    candidate_evidence = repository.get_strategy_evidence(
        strategy=options.candidate_strategy,
        pass_type=options.pass_type,
        mode=options.mode,
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
    )
    baseline_evidence = repository.get_strategy_evidence(
        strategy=options.baseline_strategy,
        pass_type=options.pass_type,
        mode=options.mode,
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
    )
    artifact = build_recommendation_strategy_review_artifact(
        candidate_evidence=candidate_evidence,
        baseline_evidence=baseline_evidence,
        options=options,
    )
    warnings = _review_warnings(artifact)
    stored_review = None
    if not options.dry_run:
        stored_review = repository.save_strategy_review(artifact)
    return RecommendationStrategyReviewRunResult(
        dry_run=options.dry_run,
        stored_review=stored_review,
        artifact=artifact,
        warnings=warnings,
    )


def build_recommendation_strategy_governance_overview(
    repository: RecommendationStrategyGovernanceRepository,
    *,
    candidate_strategies: Sequence[str],
    baseline_strategy: str = "accuracy_first",
    pass_type: str = "2x1",
    mode: Literal["single", "multiple"] = "single",
    window_start_utc: datetime | None = None,
    window_end_utc: datetime | None = None,
    minimum_sample_size: int = 30,
    minimum_baseline_sample_size: int = 30,
) -> RecommendationStrategyGovernanceOverview:
    items: list[RecommendationStrategyGovernanceItem] = []
    for candidate_strategy in candidate_strategies:
        options = RecommendationStrategyReviewOptions(
            candidate_strategy=candidate_strategy,
            baseline_strategy=baseline_strategy,
            pass_type=pass_type,
            mode=mode,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            minimum_sample_size=minimum_sample_size,
            minimum_baseline_sample_size=minimum_baseline_sample_size,
            dry_run=True,
        )
        result = run_recommendation_strategy_review(repository, options=options)
        items.append(
            RecommendationStrategyGovernanceItem(
                candidate_strategy=candidate_strategy,
                baseline_strategy=baseline_strategy,
                pass_type=pass_type,
                mode=mode,
                artifact=result.artifact,
                warnings=result.warnings,
            )
        )
    return RecommendationStrategyGovernanceOverview(
        generated_at_utc=datetime.now(tz=UTC),
        items=items,
    )


def build_mock_recommendation_strategy_governance_overview(
    *,
    candidate_strategies: Sequence[str],
    baseline_strategy: str = "accuracy_first",
    pass_type: str = "2x1",
    mode: Literal["single", "multiple"] = "single",
    window_start_utc: datetime | None = None,
    window_end_utc: datetime | None = None,
    minimum_sample_size: int = 30,
    minimum_baseline_sample_size: int = 30,
) -> RecommendationStrategyGovernanceOverview:
    items: list[RecommendationStrategyGovernanceItem] = []
    baseline_evidence = _mock_strategy_evidence(
        baseline_strategy,
        pass_type=pass_type,
        mode=mode,
        sample_size=120,
        roi=0.04,
        hit_rate=0.46,
        calibration_error=0.065,
        single_focus_hit_rate=0.49,
        single_focus_calibration_error=0.070,
        upset_focus_capture_rate=0.27,
        upset_focus_calibration_error=0.120,
    )
    for candidate_strategy in candidate_strategies:
        candidate_evidence = _mock_candidate_strategy_evidence(
            candidate_strategy,
            pass_type=pass_type,
            mode=mode,
        )
        options = RecommendationStrategyReviewOptions(
            candidate_strategy=candidate_strategy,
            baseline_strategy=baseline_strategy,
            pass_type=pass_type,
            mode=mode,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            minimum_sample_size=minimum_sample_size,
            minimum_baseline_sample_size=minimum_baseline_sample_size,
            dry_run=True,
        )
        artifact = build_recommendation_strategy_review_artifact(
            candidate_evidence=candidate_evidence,
            baseline_evidence=baseline_evidence,
            options=options,
        )
        items.append(
            RecommendationStrategyGovernanceItem(
                candidate_strategy=candidate_strategy,
                baseline_strategy=baseline_strategy,
                pass_type=pass_type,
                mode=mode,
                artifact=artifact,
                warnings=[*_review_warnings(artifact), "mock_strategy_governance_evidence"],
            )
        )
    return RecommendationStrategyGovernanceOverview(
        generated_at_utc=datetime.now(tz=UTC),
        items=items,
    )


def select_recommendation_strategy_from_governance(
    overview: RecommendationStrategyGovernanceOverview,
    *,
    requested_strategy: str = "auto",
    baseline_strategy: str = "accuracy_first",
    pass_type: str = "2x1",
    mode: str = "single",
) -> RecommendationStrategySelectionTrace:
    best_item: RecommendationStrategyGovernanceItem | None = None
    best_sort_key: tuple[
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        int,
        str,
    ] | None = None
    for item in overview.items:
        artifact = item.artifact
        if artifact.promotion_review.decision != "shadow_candidate":
            continue
        if artifact.rollback_plan.should_rollback:
            continue
        deltas = _strategy_metric_deltas(artifact.metrics_json)
        roi_delta = deltas.get("roi_delta")
        calibration_delta = deltas.get("mean_absolute_hit_calibration_error_delta")
        hit_rate_delta = deltas.get("hit_rate_delta")
        single_focus_delta = deltas.get("single_focus_hit_rate_delta")
        upset_focus_delta = deltas.get("upset_focus_capture_rate_delta")
        single_focus_calibration_delta = deltas.get(
            "mean_absolute_single_focus_calibration_error_delta"
        )
        upset_focus_calibration_delta = deltas.get(
            "mean_absolute_upset_focus_calibration_error_delta"
        )
        sort_key = (
            roi_delta if roi_delta is not None else -1.0,
            -(calibration_delta if calibration_delta is not None else 1.0),
            hit_rate_delta if hit_rate_delta is not None else -1.0,
            single_focus_delta if single_focus_delta is not None else -1.0,
            upset_focus_delta if upset_focus_delta is not None else -1.0,
            -(
                single_focus_calibration_delta
                if single_focus_calibration_delta is not None
                else 1.0
            ),
            -(
                upset_focus_calibration_delta
                if upset_focus_calibration_delta is not None
                else 1.0
            ),
            artifact.candidate_evidence.sample_size,
            item.candidate_strategy,
        )
        if best_sort_key is None or sort_key > best_sort_key:
            best_item = item
            best_sort_key = sort_key

    if best_item is None:
        return RecommendationStrategySelectionTrace(
            requested_strategy=requested_strategy,
            selected_strategy=baseline_strategy,
            baseline_strategy=baseline_strategy,
            pass_type=pass_type,
            mode=mode,
            source="baseline_fallback",
            reasons=["no_candidate_strategy_passed_governance_gate"],
            warnings=_governance_selection_warnings(overview),
            generated_at_utc=overview.generated_at_utc,
        )

    artifact = best_item.artifact
    return RecommendationStrategySelectionTrace(
        requested_strategy=requested_strategy,
        selected_strategy=best_item.candidate_strategy,
        baseline_strategy=baseline_strategy,
        pass_type=pass_type,
        mode=mode,
        source="governance_overview",
        review_key=artifact.review_key,
        reasons=[
            *artifact.promotion_review.reasons,
            "selected_by_recommendation_strategy_governance",
        ],
        warnings=[*best_item.warnings, *_governance_selection_warnings(overview)],
        metric_deltas=_strategy_metric_deltas(artifact.metrics_json),
        generated_at_utc=overview.generated_at_utc,
    )


def build_recommendation_strategy_review_artifact(
    *,
    candidate_evidence: RecommendationStrategyEvidence,
    baseline_evidence: RecommendationStrategyEvidence,
    options: RecommendationStrategyReviewOptions,
) -> RecommendationStrategyReviewArtifact:
    promotion_review = evaluate_recommendation_strategy_promotion(
        candidate_evidence=candidate_evidence,
        baseline_evidence=baseline_evidence,
        options=options,
    )
    rollback_plan = evaluate_recommendation_strategy_rollback(
        active_evidence=candidate_evidence,
        previous_evidence=baseline_evidence,
        options=options,
    )
    review_key = _strategy_review_key(options)
    return RecommendationStrategyReviewArtifact(
        review_key=review_key,
        candidate_evidence=candidate_evidence,
        baseline_evidence=baseline_evidence,
        promotion_review=promotion_review,
        rollback_plan=rollback_plan,
        metrics_json=_strategy_review_metrics_json(
            candidate_evidence=candidate_evidence,
            baseline_evidence=baseline_evidence,
            options=options,
        ),
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
    )


def evaluate_recommendation_strategy_promotion(
    *,
    candidate_evidence: RecommendationStrategyEvidence,
    baseline_evidence: RecommendationStrategyEvidence,
    options: RecommendationStrategyReviewOptions,
) -> RecommendationStrategyPromotionReview:
    reasons: list[str] = []
    if candidate_evidence.sample_size < options.minimum_sample_size:
        reasons.append("candidate_sample_size_below_minimum")
    if baseline_evidence.sample_size < options.minimum_baseline_sample_size:
        reasons.append("baseline_sample_size_below_minimum")

    candidate_roi = candidate_evidence.roi
    baseline_roi = baseline_evidence.roi
    if candidate_roi is None:
        reasons.append("candidate_roi_unavailable")
    elif candidate_roi < options.min_candidate_roi:
        reasons.append("candidate_roi_below_minimum")
    if (
        candidate_roi is not None
        and baseline_roi is not None
        and candidate_roi - baseline_roi < options.min_roi_delta
    ):
        reasons.append("candidate_roi_not_better_than_baseline")

    candidate_hit_rate = candidate_evidence.hit_rate
    baseline_hit_rate = baseline_evidence.hit_rate
    if candidate_hit_rate is None:
        reasons.append("candidate_hit_rate_unavailable")
    if (
        candidate_hit_rate is not None
        and baseline_hit_rate is not None
        and baseline_hit_rate - candidate_hit_rate > options.tolerated_hit_rate_drop
    ):
        reasons.append("candidate_hit_rate_drop_too_large")

    candidate_calibration = candidate_evidence.mean_absolute_hit_calibration_error
    baseline_calibration = baseline_evidence.mean_absolute_hit_calibration_error
    if candidate_calibration is None:
        reasons.append("candidate_calibration_unavailable")
    if (
        candidate_calibration is not None
        and baseline_calibration is not None
        and candidate_calibration - baseline_calibration > options.tolerated_calibration_error_delta
    ):
        reasons.append("candidate_hit_calibration_worse")
    if _comparable_focus_evidence(
        candidate_evidence.single_focus_sample_size,
        baseline_evidence.single_focus_sample_size,
        minimum_sample_size=options.minimum_focus_sample_size,
    ):
        if (
            candidate_evidence.single_focus_hit_rate is not None
            and baseline_evidence.single_focus_hit_rate is not None
            and baseline_evidence.single_focus_hit_rate
            - candidate_evidence.single_focus_hit_rate
            > options.tolerated_single_focus_hit_rate_drop
        ):
            reasons.append("candidate_single_focus_hit_rate_drop_too_large")
        if (
            candidate_evidence.mean_absolute_single_focus_calibration_error is not None
            and baseline_evidence.mean_absolute_single_focus_calibration_error is not None
            and candidate_evidence.mean_absolute_single_focus_calibration_error
            - baseline_evidence.mean_absolute_single_focus_calibration_error
            > options.tolerated_focus_calibration_error_delta
        ):
            reasons.append("candidate_single_focus_calibration_worse")
    if _comparable_focus_evidence(
        candidate_evidence.upset_focus_sample_size,
        baseline_evidence.upset_focus_sample_size,
        minimum_sample_size=options.minimum_focus_sample_size,
    ):
        if (
            candidate_evidence.upset_focus_capture_rate is not None
            and baseline_evidence.upset_focus_capture_rate is not None
            and baseline_evidence.upset_focus_capture_rate
            - candidate_evidence.upset_focus_capture_rate
            > options.tolerated_upset_focus_capture_rate_drop
        ):
            reasons.append("candidate_upset_focus_capture_rate_drop_too_large")
        if (
            candidate_evidence.mean_absolute_upset_focus_calibration_error is not None
            and baseline_evidence.mean_absolute_upset_focus_calibration_error is not None
            and candidate_evidence.mean_absolute_upset_focus_calibration_error
            - baseline_evidence.mean_absolute_upset_focus_calibration_error
            > options.tolerated_focus_calibration_error_delta
        ):
            reasons.append("candidate_upset_focus_calibration_worse")

    if reasons:
        return RecommendationStrategyPromotionReview(
            candidate_strategy=candidate_evidence.strategy,
            baseline_strategy=baseline_evidence.strategy,
            pass_type=candidate_evidence.pass_type,
            mode=candidate_evidence.mode,
            decision="keep_experiment",
            next_status="experiment",
            reasons=reasons,
        )
    return RecommendationStrategyPromotionReview(
        candidate_strategy=candidate_evidence.strategy,
        baseline_strategy=baseline_evidence.strategy,
        pass_type=candidate_evidence.pass_type,
        mode=candidate_evidence.mode,
        decision="shadow_candidate",
        next_status="shadow",
        reasons=["strategy_passed_first_governance_gate"],
    )


def evaluate_recommendation_strategy_rollback(
    *,
    active_evidence: RecommendationStrategyEvidence,
    previous_evidence: RecommendationStrategyEvidence,
    options: RecommendationStrategyReviewOptions,
) -> RecommendationStrategyRollbackPlan:
    reasons: list[str] = []
    active_roi = active_evidence.roi
    previous_roi = previous_evidence.roi
    active_calibration = active_evidence.mean_absolute_hit_calibration_error
    active_single_focus_calibration = (
        active_evidence.mean_absolute_single_focus_calibration_error
    )
    active_upset_focus_calibration = active_evidence.mean_absolute_upset_focus_calibration_error

    if active_evidence.sample_size >= options.minimum_sample_size:
        if active_roi is not None and active_roi < options.rollback_roi_floor:
            reasons.append("active_strategy_roi_below_floor")
        if (
            active_roi is not None
            and previous_roi is not None
            and previous_roi - active_roi > options.rollback_max_roi_underperformance
        ):
            reasons.append("active_strategy_roi_underperforms_previous")
        if (
            active_calibration is not None
            and active_calibration > options.rollback_calibration_error_ceiling
        ):
            reasons.append("active_strategy_hit_calibration_drift")
        if (
            active_evidence.single_focus_sample_size >= options.minimum_focus_sample_size
            and active_single_focus_calibration is not None
            and active_single_focus_calibration > options.rollback_focus_calibration_error_ceiling
        ):
            reasons.append("active_strategy_single_focus_calibration_drift")
        if (
            active_evidence.upset_focus_sample_size >= options.minimum_focus_sample_size
            and active_upset_focus_calibration is not None
            and active_upset_focus_calibration > options.rollback_focus_calibration_error_ceiling
        ):
            reasons.append("active_strategy_upset_focus_calibration_drift")

    if not reasons:
        return RecommendationStrategyRollbackPlan(should_rollback=False)

    return RecommendationStrategyRollbackPlan(
        should_rollback=True,
        target_strategy=previous_evidence.strategy,
        reasons=reasons,
        steps=[
            "mark_candidate_strategy_experiment_only",
            "restore_baseline_strategy_as_default",
            "pause_candidate_strategy_publication",
            "generate_recommendation_strategy_review_report",
        ],
    )


def _strategy_review_metrics_json(
    *,
    candidate_evidence: RecommendationStrategyEvidence,
    baseline_evidence: RecommendationStrategyEvidence,
    options: RecommendationStrategyReviewOptions,
) -> dict[str, object]:
    return {
        "candidate": candidate_evidence.model_dump(mode="json"),
        "baseline": baseline_evidence.model_dump(mode="json"),
        "deltas": {
            "roi_delta": _optional_delta(candidate_evidence.roi, baseline_evidence.roi),
            "hit_rate_delta": _optional_delta(
                candidate_evidence.hit_rate,
                baseline_evidence.hit_rate,
            ),
            "mean_absolute_hit_calibration_error_delta": _optional_delta(
                candidate_evidence.mean_absolute_hit_calibration_error,
                baseline_evidence.mean_absolute_hit_calibration_error,
            ),
            "single_focus_hit_rate_delta": _optional_delta(
                candidate_evidence.single_focus_hit_rate,
                baseline_evidence.single_focus_hit_rate,
            ),
            "mean_absolute_single_focus_calibration_error_delta": _optional_delta(
                candidate_evidence.mean_absolute_single_focus_calibration_error,
                baseline_evidence.mean_absolute_single_focus_calibration_error,
            ),
            "upset_focus_capture_rate_delta": _optional_delta(
                candidate_evidence.upset_focus_capture_rate,
                baseline_evidence.upset_focus_capture_rate,
            ),
            "mean_absolute_upset_focus_calibration_error_delta": _optional_delta(
                candidate_evidence.mean_absolute_upset_focus_calibration_error,
                baseline_evidence.mean_absolute_upset_focus_calibration_error,
            ),
            "expected_roi_delta": _optional_delta(
                candidate_evidence.average_expected_roi,
                baseline_evidence.average_expected_roi,
            ),
        },
        "thresholds": {
            "minimum_sample_size": options.minimum_sample_size,
            "minimum_baseline_sample_size": options.minimum_baseline_sample_size,
            "min_roi_delta": options.min_roi_delta,
            "min_candidate_roi": options.min_candidate_roi,
            "tolerated_hit_rate_drop": options.tolerated_hit_rate_drop,
            "tolerated_calibration_error_delta": (options.tolerated_calibration_error_delta),
            "minimum_focus_sample_size": options.minimum_focus_sample_size,
            "tolerated_single_focus_hit_rate_drop": (
                options.tolerated_single_focus_hit_rate_drop
            ),
            "tolerated_upset_focus_capture_rate_drop": (
                options.tolerated_upset_focus_capture_rate_drop
            ),
            "tolerated_focus_calibration_error_delta": (
                options.tolerated_focus_calibration_error_delta
            ),
            "rollback_roi_floor": options.rollback_roi_floor,
            "rollback_max_roi_underperformance": (options.rollback_max_roi_underperformance),
            "rollback_calibration_error_ceiling": (options.rollback_calibration_error_ceiling),
            "rollback_focus_calibration_error_ceiling": (
                options.rollback_focus_calibration_error_ceiling
            ),
        },
        "calculation_basis": (
            "settled_recommendation_run_evaluations_grouped_by_strategy_pass_type_mode"
            "_with_focus_policy_evaluation_json"
        ),
    }


def _review_warnings(artifact: RecommendationStrategyReviewArtifact) -> list[str]:
    warnings: list[str] = []
    if artifact.candidate_evidence.sample_size == 0:
        warnings.append("candidate_strategy_has_no_settled_evidence")
    if artifact.baseline_evidence.sample_size == 0:
        warnings.append("baseline_strategy_has_no_settled_evidence")
    if artifact.candidate_evidence.single_focus_sample_size == 0:
        warnings.append("candidate_strategy_has_no_single_focus_evidence")
    if artifact.candidate_evidence.upset_focus_sample_size == 0:
        warnings.append("candidate_strategy_has_no_upset_focus_evidence")
    if artifact.rollback_plan.should_rollback:
        warnings.append("rollback_signal_present")
    return warnings


def _comparable_focus_evidence(
    candidate_sample_size: int,
    baseline_sample_size: int,
    *,
    minimum_sample_size: int,
) -> bool:
    return (
        candidate_sample_size >= minimum_sample_size
        and baseline_sample_size >= minimum_sample_size
    )


def _strategy_review_key(options: RecommendationStrategyReviewOptions) -> str:
    window_start = (
        options.normalized_window_start_utc.isoformat()
        if options.normalized_window_start_utc is not None
        else "open_start"
    )
    window_end = (
        options.normalized_window_end_utc.isoformat()
        if options.normalized_window_end_utc is not None
        else "open_end"
    )
    return (
        f"v3_1_strategy_review_{options.candidate_strategy}_vs_"
        f"{options.baseline_strategy}_{options.pass_type}_{options.mode}_"
        f"{window_start}_{window_end}"
    )


def _strategy_evidence_from_row(row: DatabaseRow) -> RecommendationStrategyEvidence:
    return RecommendationStrategyEvidence(
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=str(row["mode"]),
        sample_size=_int(row["sample_size"]),
        settled_run_count=_int(row["settled_run_count"]),
        hit_count=_int(row["hit_count"]),
        total_stake=_float(row["total_stake"]),
        gross_payout=_float(row["gross_payout"]),
        profit_loss=_float(row["profit_loss"]),
        roi=_optional_float(row.get("roi")),
        hit_rate=_optional_float(row.get("hit_rate")),
        average_expected_roi=_optional_float(row.get("average_expected_roi")),
        average_expected_hit_probability=_optional_float(
            row.get("average_expected_hit_probability")
        ),
        average_hit_calibration_error=_optional_float(row.get("average_hit_calibration_error")),
        mean_absolute_hit_calibration_error=_optional_float(
            row.get("mean_absolute_hit_calibration_error")
        ),
        single_focus_sample_size=_int(row.get("single_focus_sample_size") or 0),
        single_focus_hit_count=_int(row.get("single_focus_hit_count") or 0),
        single_focus_hit_rate=_optional_float(row.get("single_focus_hit_rate")),
        average_single_focus_calibration_error=_optional_float(
            row.get("average_single_focus_calibration_error")
        ),
        mean_absolute_single_focus_calibration_error=_optional_float(
            row.get("mean_absolute_single_focus_calibration_error")
        ),
        upset_focus_sample_size=_int(row.get("upset_focus_sample_size") or 0),
        upset_focus_capture_count=_int(row.get("upset_focus_capture_count") or 0),
        upset_focus_capture_rate=_optional_float(row.get("upset_focus_capture_rate")),
        average_upset_focus_calibration_error=_optional_float(
            row.get("average_upset_focus_calibration_error")
        ),
        mean_absolute_upset_focus_calibration_error=_optional_float(
            row.get("mean_absolute_upset_focus_calibration_error")
        ),
        first_evaluation_time_utc=_optional_datetime(row.get("first_evaluation_time_utc")),
        last_evaluation_time_utc=_optional_datetime(row.get("last_evaluation_time_utc")),
    )


def _strategy_metric_deltas(metrics_json: dict[str, object]) -> dict[str, float | None]:
    raw_deltas = metrics_json.get("deltas")
    if not isinstance(raw_deltas, dict):
        return {}
    keys = (
        "roi_delta",
        "hit_rate_delta",
        "mean_absolute_hit_calibration_error_delta",
        "single_focus_hit_rate_delta",
        "mean_absolute_single_focus_calibration_error_delta",
        "upset_focus_capture_rate_delta",
        "mean_absolute_upset_focus_calibration_error_delta",
        "expected_roi_delta",
    )
    return {key: _optional_float(raw_deltas.get(key)) for key in keys}


def _governance_selection_warnings(
    overview: RecommendationStrategyGovernanceOverview,
) -> list[str]:
    warnings: list[str] = []
    if not overview.items:
        warnings.append("strategy_governance_overview_empty")
    if all(item.artifact.candidate_evidence.sample_size == 0 for item in overview.items):
        warnings.append("strategy_governance_has_no_candidate_evidence")
    return warnings


def _mock_candidate_strategy_evidence(
    strategy: str,
    *,
    pass_type: str,
    mode: str,
) -> RecommendationStrategyEvidence:
    if strategy == "upset_protection":
        return _mock_strategy_evidence(
            strategy,
            pass_type=pass_type,
            mode=mode,
            sample_size=90,
            roi=0.055,
            hit_rate=0.47,
            calibration_error=0.060,
            single_focus_hit_rate=0.53,
            single_focus_calibration_error=0.055,
            upset_focus_capture_rate=0.34,
            upset_focus_calibration_error=0.090,
        )
    if strategy == "value_first":
        return _mock_strategy_evidence(
            strategy,
            pass_type=pass_type,
            mode=mode,
            sample_size=96,
            roi=0.065,
            hit_rate=0.43,
            calibration_error=0.080,
            single_focus_hit_rate=0.46,
            single_focus_calibration_error=0.090,
            upset_focus_capture_rate=0.22,
            upset_focus_calibration_error=0.140,
        )
    if strategy == "budget_constrained":
        return _mock_strategy_evidence(
            strategy,
            pass_type=pass_type,
            mode=mode,
            sample_size=42,
            roi=0.025,
            hit_rate=0.49,
            calibration_error=0.055,
            single_focus_hit_rate=0.50,
            single_focus_calibration_error=0.060,
            upset_focus_capture_rate=0.29,
            upset_focus_calibration_error=0.105,
        )
    return _mock_strategy_evidence(
        strategy,
        pass_type=pass_type,
        mode=mode,
        sample_size=24,
        roi=None,
        hit_rate=None,
        calibration_error=None,
        single_focus_hit_rate=None,
        single_focus_calibration_error=None,
        upset_focus_capture_rate=None,
        upset_focus_calibration_error=None,
    )


def _mock_strategy_evidence(
    strategy: str,
    *,
    pass_type: str,
    mode: str,
    sample_size: int,
    roi: float | None,
    hit_rate: float | None,
    calibration_error: float | None,
    single_focus_hit_rate: float | None = None,
    single_focus_calibration_error: float | None = None,
    upset_focus_capture_rate: float | None = None,
    upset_focus_calibration_error: float | None = None,
) -> RecommendationStrategyEvidence:
    total_stake = sample_size * 2.0
    profit_loss = total_stake * (roi or 0.0)
    single_focus_sample_size = sample_size if single_focus_hit_rate is not None else 0
    upset_focus_sample_size = sample_size if upset_focus_capture_rate is not None else 0
    return RecommendationStrategyEvidence(
        strategy=strategy,
        pass_type=pass_type,
        mode=mode,
        sample_size=sample_size,
        settled_run_count=sample_size,
        hit_count=int(sample_size * (hit_rate or 0.0)),
        total_stake=total_stake,
        gross_payout=total_stake + profit_loss,
        profit_loss=profit_loss,
        roi=roi,
        hit_rate=hit_rate,
        average_expected_roi=roi,
        average_expected_hit_probability=hit_rate,
        average_hit_calibration_error=0.0 if calibration_error is not None else None,
        mean_absolute_hit_calibration_error=calibration_error,
        single_focus_sample_size=single_focus_sample_size,
        single_focus_hit_count=int(single_focus_sample_size * (single_focus_hit_rate or 0.0)),
        single_focus_hit_rate=single_focus_hit_rate,
        average_single_focus_calibration_error=(
            0.0 if single_focus_calibration_error is not None else None
        ),
        mean_absolute_single_focus_calibration_error=single_focus_calibration_error,
        upset_focus_sample_size=upset_focus_sample_size,
        upset_focus_capture_count=int(
            upset_focus_sample_size * (upset_focus_capture_rate or 0.0)
        ),
        upset_focus_capture_rate=upset_focus_capture_rate,
        average_upset_focus_calibration_error=(
            0.0 if upset_focus_calibration_error is not None else None
        ),
        mean_absolute_upset_focus_calibration_error=upset_focus_calibration_error,
        first_evaluation_time_utc=datetime(2026, 5, 1, tzinfo=UTC),
        last_evaluation_time_utc=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _strategy_review_params(
    artifact: RecommendationStrategyReviewArtifact,
) -> QueryParams:
    return {
        "review_key": artifact.review_key,
        "candidate_strategy": artifact.promotion_review.candidate_strategy,
        "baseline_strategy": artifact.promotion_review.baseline_strategy,
        "pass_type": artifact.promotion_review.pass_type,
        "mode": artifact.promotion_review.mode,
        "decision": artifact.promotion_review.decision,
        "next_status": artifact.promotion_review.next_status,
        "sample_size": artifact.candidate_evidence.sample_size,
        "baseline_sample_size": artifact.baseline_evidence.sample_size,
        "candidate_roi": artifact.candidate_evidence.roi,
        "baseline_roi": artifact.baseline_evidence.roi,
        "candidate_hit_rate": artifact.candidate_evidence.hit_rate,
        "baseline_hit_rate": artifact.baseline_evidence.hit_rate,
        "candidate_calibration_error": (
            artifact.candidate_evidence.mean_absolute_hit_calibration_error
        ),
        "baseline_calibration_error": (
            artifact.baseline_evidence.mean_absolute_hit_calibration_error
        ),
        "metrics_json": _json(artifact.metrics_json),
        "reasons_json": _json(artifact.promotion_review.reasons),
        "rollback_plan_json": _json(artifact.rollback_plan.model_dump(mode="json")),
        "window_start_utc": artifact.window_start_utc,
        "window_end_utc": artifact.window_end_utc,
        "source": "recommendation_strategy_governance_v3_1",
    }


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _optional_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float(value)
