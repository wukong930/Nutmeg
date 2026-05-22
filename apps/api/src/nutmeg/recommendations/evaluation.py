from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps, loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.parlay.settlement import (
    ParlayAtomicSettlement,
    actual_outcome_for_parlay_leg,
    settle_parlay_atomic_bet,
)

type RecommendationEvaluationStatus = Literal["settled", "partial", "unresolved"]

LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY = """
SELECT
  rr.recommendation_run_id,
  rr.run_key,
  rr.strategy,
  rr.pass_type,
  rr.mode,
  rr.status AS recommendation_status,
  rr.unit_stake,
  COALESCE((rr.parlay_evaluation_json->>'total_stake')::numeric, rr.unit_stake, 0) AS total_stake,
  rr.selected_fixture_ids_json,
  rr.locked_fixture_ids_json,
  rr.parlay_evaluation_json,
  rr.explanation_json,
  rr.created_at
FROM recommendation_runs rr
LEFT JOIN recommendation_run_evaluations rre
  ON rre.recommendation_run_id = rr.recommendation_run_id
WHERE rre.recommendation_run_evaluation_id IS NULL
  AND rr.status = ANY(%(eligible_statuses)s)
  AND NOT EXISTS (
    SELECT 1
    FROM recommendation_runs successor
    WHERE successor.status <> 'invalidated'
      AND successor.explanation_json #>>
        '{internal_trace,successor_recompute,source_recommendation_run_id}'
        = rr.recommendation_run_id::text
  )
ORDER BY rr.created_at ASC, rr.recommendation_run_id ASC
LIMIT %(limit)s
"""

LIST_RESULTS_FOR_RECOMMENDATION_FIXTURES_QUERY = """
SELECT
  fixture_id,
  home_goals,
  away_goals
FROM results
WHERE fixture_id = ANY(%(fixture_ids)s::text[])
ORDER BY fixture_id ASC
"""

UPSERT_RECOMMENDATION_RUN_EVALUATION_QUERY = """
INSERT INTO recommendation_run_evaluations (
  recommendation_run_id,
  run_key,
  strategy,
  pass_type,
  mode,
  recommendation_status,
  evaluation_status,
  total_atomic_bets,
  settled_atomic_bets,
  won_atomic_bets,
  lost_atomic_bets,
  unresolved_atomic_bets,
  unit_stake,
  total_stake,
  gross_payout,
  profit_loss,
  roi,
  hit,
  hit_rate,
  expected_hit_probability_at_recommendation,
  hit_calibration_error,
  expected_value_at_recommendation,
  expected_roi_at_recommendation,
  locked_fixture_count,
  selected_fixture_count,
  evaluation_time_utc,
  settlement_detail_json,
  source
) VALUES (
  %(recommendation_run_id)s,
  %(run_key)s,
  %(strategy)s,
  %(pass_type)s,
  %(mode)s,
  %(recommendation_status)s,
  %(evaluation_status)s,
  %(total_atomic_bets)s,
  %(settled_atomic_bets)s,
  %(won_atomic_bets)s,
  %(lost_atomic_bets)s,
  %(unresolved_atomic_bets)s,
  %(unit_stake)s,
  %(total_stake)s,
  %(gross_payout)s,
  %(profit_loss)s,
  %(roi)s,
  %(hit)s,
  %(hit_rate)s,
  %(expected_hit_probability_at_recommendation)s,
  %(hit_calibration_error)s,
  %(expected_value_at_recommendation)s,
  %(expected_roi_at_recommendation)s,
  %(locked_fixture_count)s,
  %(selected_fixture_count)s,
  %(evaluation_time_utc)s,
  %(settlement_detail_json)s::jsonb,
  %(source)s
)
ON CONFLICT (recommendation_run_id) DO UPDATE SET
  recommendation_status = EXCLUDED.recommendation_status,
  evaluation_status = EXCLUDED.evaluation_status,
  total_atomic_bets = EXCLUDED.total_atomic_bets,
  settled_atomic_bets = EXCLUDED.settled_atomic_bets,
  won_atomic_bets = EXCLUDED.won_atomic_bets,
  lost_atomic_bets = EXCLUDED.lost_atomic_bets,
  unresolved_atomic_bets = EXCLUDED.unresolved_atomic_bets,
  total_stake = EXCLUDED.total_stake,
  gross_payout = EXCLUDED.gross_payout,
  profit_loss = EXCLUDED.profit_loss,
  roi = EXCLUDED.roi,
  hit = EXCLUDED.hit,
  hit_rate = EXCLUDED.hit_rate,
  expected_hit_probability_at_recommendation = EXCLUDED.expected_hit_probability_at_recommendation,
  hit_calibration_error = EXCLUDED.hit_calibration_error,
  expected_value_at_recommendation = EXCLUDED.expected_value_at_recommendation,
  expected_roi_at_recommendation = EXCLUDED.expected_roi_at_recommendation,
  locked_fixture_count = EXCLUDED.locked_fixture_count,
  selected_fixture_count = EXCLUDED.selected_fixture_count,
  evaluation_time_utc = EXCLUDED.evaluation_time_utc,
  settlement_detail_json = EXCLUDED.settlement_detail_json,
  source = EXCLUDED.source
RETURNING recommendation_run_evaluation_id, created_at
"""

LIST_RECOMMENDATION_RUN_EVALUATIONS_QUERY = """
SELECT
  recommendation_run_evaluation_id,
  recommendation_run_id,
  run_key,
  strategy,
  pass_type,
  mode,
  recommendation_status,
  evaluation_status,
  total_atomic_bets,
  settled_atomic_bets,
  won_atomic_bets,
  lost_atomic_bets,
  unresolved_atomic_bets,
  unit_stake,
  total_stake,
  gross_payout,
  profit_loss,
  roi,
  hit,
  hit_rate,
  expected_hit_probability_at_recommendation,
  hit_calibration_error,
  expected_value_at_recommendation,
  expected_roi_at_recommendation,
  locked_fixture_count,
  selected_fixture_count,
  evaluation_time_utc,
  settlement_detail_json,
  created_at
FROM recommendation_run_evaluations
WHERE (%(strategy)s::text IS NULL OR strategy = %(strategy)s::text)
  AND (%(pass_type)s::text IS NULL OR pass_type = %(pass_type)s::text)
  AND (%(mode)s::text IS NULL OR mode = %(mode)s::text)
  AND NOT EXISTS (
    SELECT 1
    FROM recommendation_runs successor
    WHERE successor.status <> 'invalidated'
      AND successor.explanation_json #>>
        '{internal_trace,successor_recompute,source_recommendation_run_id}'
        = recommendation_run_evaluations.recommendation_run_id::text
  )
ORDER BY evaluation_time_utc DESC, recommendation_run_evaluation_id DESC
LIMIT %(limit)s
"""


class RecommendationRunForEvaluation(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    strategy: str
    pass_type: str
    mode: str
    recommendation_status: str
    unit_stake: float = Field(gt=0.0)
    total_stake: float = Field(ge=0.0)
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    parlay_evaluation_json: dict[str, object] = Field(default_factory=dict)
    explanation_json: dict[str, object] = Field(default_factory=dict)
    expected_hit_probability_at_recommendation: float | None = None
    expected_value_at_recommendation: float | None = None
    expected_roi_at_recommendation: float | None = None
    created_at: datetime


class RecommendationAtomicEvaluation(BaseModel):
    atomic_index: int = Field(ge=0)
    result_status: Literal["won", "lost", "unresolved"]
    stake: float = Field(ge=0.0)
    odds_product: float = Field(ge=0.0)
    gross_payout: float = Field(ge=0.0)
    profit_loss: float
    settlement_detail_json: dict[str, object] = Field(default_factory=dict)


class RecommendationFocusMetrics(BaseModel):
    single_focus_hit: bool | None = None
    single_focus_expected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    single_focus_calibration_error: float | None = None
    upset_focus_triggered: bool = False
    upset_focus_captured: bool | None = None
    upset_focus_expected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    upset_focus_calibration_error: float | None = None


class RecommendationRunEvaluation(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    strategy: str
    pass_type: str
    mode: str
    recommendation_status: str
    evaluation_status: RecommendationEvaluationStatus
    total_atomic_bets: int = Field(ge=0)
    settled_atomic_bets: int = Field(ge=0)
    won_atomic_bets: int = Field(ge=0)
    lost_atomic_bets: int = Field(ge=0)
    unresolved_atomic_bets: int = Field(ge=0)
    unit_stake: float = Field(gt=0.0)
    total_stake: float = Field(ge=0.0)
    gross_payout: float = Field(ge=0.0)
    profit_loss: float
    roi: float
    hit: bool | None = None
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_hit_probability_at_recommendation: float | None = Field(default=None, ge=0.0, le=1.0)
    hit_calibration_error: float | None = None
    expected_value_at_recommendation: float | None = None
    expected_roi_at_recommendation: float | None = None
    single_focus_hit: bool | None = None
    single_focus_expected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    single_focus_calibration_error: float | None = None
    upset_focus_triggered: bool = False
    upset_focus_captured: bool | None = None
    upset_focus_expected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    upset_focus_calibration_error: float | None = None
    locked_fixture_count: int = Field(ge=0)
    selected_fixture_count: int = Field(ge=0)
    evaluation_time_utc: datetime
    settlement_detail_json: dict[str, object] = Field(default_factory=dict)


class StoredRecommendationRunEvaluation(BaseModel):
    recommendation_run_evaluation_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    created_at: datetime


class RecommendationStrategyMetrics(BaseModel):
    strategy: str
    pass_type: str
    mode: str
    sample_size: int = Field(ge=0)
    settled_run_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    total_stake: float = Field(ge=0.0)
    gross_payout: float = Field(ge=0.0)
    profit_loss: float
    roi: float
    average_expected_hit_probability: float | None = None
    average_hit_calibration_error: float | None = None
    average_expected_roi: float | None = None
    single_focus_sample_size: int = Field(default=0, ge=0)
    single_focus_hit_count: int = Field(default=0, ge=0)
    single_focus_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_single_focus_calibration_error: float | None = None
    upset_focus_sample_size: int = Field(default=0, ge=0)
    upset_focus_capture_count: int = Field(default=0, ge=0)
    upset_focus_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_upset_focus_calibration_error: float | None = None


class RecommendationEvaluationOptions(BaseModel):
    evaluation_time_utc: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1_000)
    save_partial: bool = False
    eligible_statuses: tuple[str, ...] = (
        "current",
        "locked",
        "confirmed_manual",
        "live",
        "settled",
    )


class RecommendationEvaluationRunResult(BaseModel):
    checked_runs: int = Field(ge=0)
    evaluated_runs: int = Field(ge=0)
    skipped_unresolved_runs: int = Field(ge=0)
    stored_evaluation_ids: list[int] = Field(default_factory=list)
    evaluations: list[RecommendationRunEvaluation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecommendationEvaluationDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read pending recommendation runs and fixture results."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute evaluation writes with RETURNING."""


class RecommendationEvaluationRepository(Protocol):
    def list_pending_runs(
        self,
        *,
        limit: int,
        eligible_statuses: Sequence[str],
    ) -> list[RecommendationRunForEvaluation]:
        """List recommendation runs that have not yet been evaluated."""

    def list_results_for_fixture_ids(
        self,
        fixture_ids: Sequence[str],
    ) -> list[Mapping[str, object]]:
        """Read final results for the fixtures in a recommendation."""

    def save_run_evaluation(
        self,
        evaluation: RecommendationRunEvaluation,
        *,
        source: str = "recommendation_accuracy_loop_v3_1",
    ) -> StoredRecommendationRunEvaluation:
        """Persist a recommendation run evaluation."""


class PostgresRecommendationEvaluationRepository:
    def __init__(self, database: RecommendationEvaluationDatabaseExecutor) -> None:
        self.database = database

    def list_pending_runs(
        self,
        *,
        limit: int = 100,
        eligible_statuses: Sequence[str] = (
            "current",
            "locked",
            "confirmed_manual",
            "live",
            "settled",
        ),
    ) -> list[RecommendationRunForEvaluation]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY,
            {
                "limit": max(1, limit),
                "eligible_statuses": list(eligible_statuses),
            },
        )
        return [_run_for_evaluation_from_row(row) for row in rows]

    def list_results_for_fixture_ids(
        self,
        fixture_ids: Sequence[str],
    ) -> list[Mapping[str, object]]:
        if not fixture_ids:
            return []
        rows = self.database.fetch_all(
            LIST_RESULTS_FOR_RECOMMENDATION_FIXTURES_QUERY,
            {"fixture_ids": sorted(set(fixture_ids))},
        )
        return [dict(row) for row in rows]

    def save_run_evaluation(
        self,
        evaluation: RecommendationRunEvaluation,
        *,
        source: str = "recommendation_accuracy_loop_v3_1",
    ) -> StoredRecommendationRunEvaluation:
        row = _required_row(
            self.database.fetch_one(
                UPSERT_RECOMMENDATION_RUN_EVALUATION_QUERY,
                _evaluation_params(evaluation, source=source),
            )
        )
        return StoredRecommendationRunEvaluation(
            recommendation_run_evaluation_id=_int(row["recommendation_run_evaluation_id"]),
            recommendation_run_id=evaluation.recommendation_run_id,
            created_at=_datetime(row["created_at"]),
        )

    def list_run_evaluations(
        self,
        *,
        limit: int = 100,
        strategy: str | None = None,
        pass_type: str | None = None,
        mode: str | None = None,
    ) -> list[RecommendationRunEvaluation]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_RUN_EVALUATIONS_QUERY,
            {
                "limit": max(1, limit),
                "strategy": strategy,
                "pass_type": pass_type,
                "mode": mode,
            },
        )
        return [_run_evaluation_from_row(row) for row in rows]


def run_recommendation_evaluation(
    repository: RecommendationEvaluationRepository,
    *,
    options: RecommendationEvaluationOptions | None = None,
) -> RecommendationEvaluationRunResult:
    run_options = options or RecommendationEvaluationOptions()
    evaluation_time_utc = _aware_utc(run_options.evaluation_time_utc or datetime.now(tz=UTC))
    pending_runs = repository.list_pending_runs(
        limit=run_options.limit,
        eligible_statuses=run_options.eligible_statuses,
    )
    evaluations: list[RecommendationRunEvaluation] = []
    stored_evaluation_ids: list[int] = []
    warnings: list[str] = []
    skipped_unresolved_runs = 0

    for run in pending_runs:
        result_rows = repository.list_results_for_fixture_ids(
            _recommendation_run_result_fixture_ids(run)
        )
        evaluation = evaluate_recommendation_run(
            run,
            result_rows=result_rows,
            evaluation_time_utc=evaluation_time_utc,
        )
        if evaluation.evaluation_status != "settled" and not run_options.save_partial:
            skipped_unresolved_runs += 1
            warnings.append(f"recommendation_run_unresolved:{run.recommendation_run_id}")
            continue
        stored = repository.save_run_evaluation(evaluation)
        stored_evaluation_ids.append(stored.recommendation_run_evaluation_id)
        evaluations.append(evaluation)

    return RecommendationEvaluationRunResult(
        checked_runs=len(pending_runs),
        evaluated_runs=len(evaluations),
        skipped_unresolved_runs=skipped_unresolved_runs,
        stored_evaluation_ids=stored_evaluation_ids,
        evaluations=evaluations,
        warnings=warnings,
    )


def evaluate_recommendation_run(
    run: RecommendationRunForEvaluation,
    *,
    result_rows: Sequence[Mapping[str, object]],
    evaluation_time_utc: datetime,
) -> RecommendationRunEvaluation:
    atomic_bets = _json_mapping_array(run.parlay_evaluation_json.get("atomic_bets"))
    atomic_evaluations: list[RecommendationAtomicEvaluation] = []
    for index, atomic_bet in enumerate(atomic_bets):
        settlement = _settle_atomic_bet(atomic_bet, result_rows=result_rows)
        atomic_evaluations.append(
            RecommendationAtomicEvaluation(
                atomic_index=index,
                result_status=settlement.result_status,
                stake=_float(atomic_bet["stake"]),
                odds_product=_float(atomic_bet["odds_product"]),
                gross_payout=settlement.gross_payout,
                profit_loss=settlement.profit_loss,
                settlement_detail_json=settlement.detail_json,
            )
        )

    total_atomic_bets = len(atomic_evaluations)
    won_atomic_bets = sum(1 for atomic in atomic_evaluations if atomic.result_status == "won")
    lost_atomic_bets = sum(1 for atomic in atomic_evaluations if atomic.result_status == "lost")
    unresolved_atomic_bets = sum(
        1 for atomic in atomic_evaluations if atomic.result_status == "unresolved"
    )
    settled_atomic_bets = won_atomic_bets + lost_atomic_bets
    gross_payout = sum(atomic.gross_payout for atomic in atomic_evaluations)
    profit_loss = sum(atomic.profit_loss for atomic in atomic_evaluations)
    total_stake = run.total_stake or sum(atomic.stake for atomic in atomic_evaluations)
    roi = profit_loss / total_stake if total_stake > 0 else 0.0
    hit_rate = won_atomic_bets / settled_atomic_bets if settled_atomic_bets > 0 else None
    evaluation_status = _evaluation_status(
        total_atomic_bets=total_atomic_bets,
        unresolved_atomic_bets=unresolved_atomic_bets,
    )
    hit = won_atomic_bets > 0 if evaluation_status == "settled" else None
    hit_calibration_error = _hit_calibration_error(
        hit=hit,
        expected_hit_probability=run.expected_hit_probability_at_recommendation,
    )
    focus_policy_evaluation = _evaluate_focus_policy_answers(
        run,
        result_rows=result_rows,
    )
    focus_metrics = _focus_metrics_from_policy_evaluation(focus_policy_evaluation)
    settlement_detail_json: dict[str, object] = {
        "atomic_evaluations": [atomic.model_dump(mode="json") for atomic in atomic_evaluations],
        "result_fixture_count": len(
            {str(row["fixture_id"]) for row in result_rows if "fixture_id" in row}
        ),
        "calculation_basis": (
            "stored_recommendation_parlay_evaluation_atomic_bets_settled_against_results"
        ),
    }
    if focus_policy_evaluation:
        settlement_detail_json["focus_policy_evaluation"] = focus_policy_evaluation

    return RecommendationRunEvaluation(
        recommendation_run_id=run.recommendation_run_id,
        run_key=run.run_key,
        strategy=run.strategy,
        pass_type=run.pass_type,
        mode=run.mode,
        recommendation_status=run.recommendation_status,
        evaluation_status=evaluation_status,
        total_atomic_bets=total_atomic_bets,
        settled_atomic_bets=settled_atomic_bets,
        won_atomic_bets=won_atomic_bets,
        lost_atomic_bets=lost_atomic_bets,
        unresolved_atomic_bets=unresolved_atomic_bets,
        unit_stake=run.unit_stake,
        total_stake=total_stake,
        gross_payout=gross_payout,
        profit_loss=profit_loss,
        roi=roi,
        hit=hit,
        hit_rate=hit_rate,
        expected_hit_probability_at_recommendation=(run.expected_hit_probability_at_recommendation),
        hit_calibration_error=hit_calibration_error,
        expected_value_at_recommendation=run.expected_value_at_recommendation,
        expected_roi_at_recommendation=run.expected_roi_at_recommendation,
        single_focus_hit=focus_metrics.single_focus_hit,
        single_focus_expected_probability=focus_metrics.single_focus_expected_probability,
        single_focus_calibration_error=focus_metrics.single_focus_calibration_error,
        upset_focus_triggered=focus_metrics.upset_focus_triggered,
        upset_focus_captured=focus_metrics.upset_focus_captured,
        upset_focus_expected_probability=focus_metrics.upset_focus_expected_probability,
        upset_focus_calibration_error=focus_metrics.upset_focus_calibration_error,
        locked_fixture_count=len(set(run.locked_fixture_ids)),
        selected_fixture_count=len(set(run.selected_fixture_ids)),
        evaluation_time_utc=_aware_utc(evaluation_time_utc),
        settlement_detail_json=settlement_detail_json,
    )


def summarize_recommendation_strategy_evaluations(
    evaluations: Sequence[RecommendationRunEvaluation],
) -> list[RecommendationStrategyMetrics]:
    grouped: dict[tuple[str, str, str], list[RecommendationRunEvaluation]] = {}
    for evaluation in evaluations:
        key = (evaluation.strategy, evaluation.pass_type, evaluation.mode)
        grouped.setdefault(key, []).append(evaluation)

    metrics: list[RecommendationStrategyMetrics] = []
    for (strategy, pass_type, mode), items in sorted(grouped.items()):
        settled_items = [item for item in items if item.evaluation_status == "settled"]
        total_stake = sum(item.total_stake for item in settled_items)
        gross_payout = sum(item.gross_payout for item in settled_items)
        profit_loss = sum(item.profit_loss for item in settled_items)
        expected_rois = [
            item.expected_roi_at_recommendation
            for item in items
            if item.expected_roi_at_recommendation is not None
        ]
        expected_hit_probabilities = [
            item.expected_hit_probability_at_recommendation
            for item in items
            if item.expected_hit_probability_at_recommendation is not None
        ]
        calibration_errors = [
            item.hit_calibration_error
            for item in settled_items
            if item.hit_calibration_error is not None
        ]
        single_focus_items = [item for item in items if item.single_focus_hit is not None]
        single_focus_errors = [
            item.single_focus_calibration_error
            for item in single_focus_items
            if item.single_focus_calibration_error is not None
        ]
        upset_focus_items = [item for item in items if item.upset_focus_captured is not None]
        upset_focus_errors = [
            item.upset_focus_calibration_error
            for item in upset_focus_items
            if item.upset_focus_calibration_error is not None
        ]
        metrics.append(
            RecommendationStrategyMetrics(
                strategy=strategy,
                pass_type=pass_type,
                mode=mode,
                sample_size=len(items),
                settled_run_count=len(settled_items),
                hit_count=sum(1 for item in settled_items if item.hit is True),
                total_stake=total_stake,
                gross_payout=gross_payout,
                profit_loss=profit_loss,
                roi=profit_loss / total_stake if total_stake > 0 else 0.0,
                average_expected_hit_probability=(
                    sum(expected_hit_probabilities) / len(expected_hit_probabilities)
                    if expected_hit_probabilities
                    else None
                ),
                average_hit_calibration_error=(
                    sum(calibration_errors) / len(calibration_errors)
                    if calibration_errors
                    else None
                ),
                average_expected_roi=(
                    sum(expected_rois) / len(expected_rois) if expected_rois else None
                ),
                single_focus_sample_size=len(single_focus_items),
                single_focus_hit_count=sum(
                    1 for item in single_focus_items if item.single_focus_hit is True
                ),
                single_focus_hit_rate=(
                    sum(1 for item in single_focus_items if item.single_focus_hit is True)
                    / len(single_focus_items)
                    if single_focus_items
                    else None
                ),
                average_single_focus_calibration_error=(
                    sum(single_focus_errors) / len(single_focus_errors)
                    if single_focus_errors
                    else None
                ),
                upset_focus_sample_size=len(upset_focus_items),
                upset_focus_capture_count=sum(
                    1 for item in upset_focus_items if item.upset_focus_captured is True
                ),
                upset_focus_capture_rate=(
                    sum(1 for item in upset_focus_items if item.upset_focus_captured is True)
                    / len(upset_focus_items)
                    if upset_focus_items
                    else None
                ),
                average_upset_focus_calibration_error=(
                    sum(upset_focus_errors) / len(upset_focus_errors)
                    if upset_focus_errors
                    else None
                ),
            )
        )
    return metrics


def _recommendation_run_result_fixture_ids(run: RecommendationRunForEvaluation) -> list[str]:
    fixture_ids: list[str] = []
    for fixture_id in [*run.selected_fixture_ids, *_focus_answer_fixture_ids(run.explanation_json)]:
        if fixture_id in fixture_ids:
            continue
        fixture_ids.append(fixture_id)
    return fixture_ids


def _focus_answer_fixture_ids(explanation_json: Mapping[str, object]) -> list[str]:
    fixture_ids: list[str] = []
    for answer in _focus_policy_answers(explanation_json).values():
        fixture_id = _optional_str(answer.get("fixture_id"))
        if fixture_id is not None:
            fixture_ids.append(fixture_id)
    return fixture_ids


def _evaluate_focus_policy_answers(
    run: RecommendationRunForEvaluation,
    *,
    result_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    focus_answers = _focus_policy_answers(run.explanation_json)
    if not focus_answers:
        return {}
    payload: dict[str, object] = {
        "calculation_basis": "stored_internal_focus_policy_answers_settled_against_results",
    }
    single_answer = _evaluate_focus_answer(focus_answers.get("single"), result_rows=result_rows)
    if single_answer is not None:
        payload["single"] = single_answer
    upset_answer = _evaluate_focus_answer(focus_answers.get("upset"), result_rows=result_rows)
    if upset_answer is not None:
        payload["upset"] = upset_answer
    return payload


def _evaluate_focus_answer(
    answer: Mapping[str, object] | None,
    *,
    result_rows: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    if not answer:
        return None
    fixture_id = _optional_str(answer.get("fixture_id"))
    market_type = _optional_str(answer.get("market_type"))
    selected_outcome = _optional_str(answer.get("outcome"))
    expected_probability = _optional_float(answer.get("probability"))
    if fixture_id is None or market_type is None or selected_outcome is None:
        return {
            "result_status": "unresolved",
            "hit": None,
            "expected_probability": expected_probability,
            "calibration_error": None,
            "reason": "focus_answer_missing_required_fields",
        }

    result_by_fixture = {
        str(row["fixture_id"]): row
        for row in result_rows
        if row.get("fixture_id") is not None
    }
    result = result_by_fixture.get(fixture_id)
    if result is None:
        return {
            **_focus_answer_identity(answer),
            "result_status": "unresolved",
            "hit": None,
            "actual_outcome": None,
            "expected_probability": expected_probability,
            "calibration_error": None,
            "reason": "result_missing",
        }

    actual_outcome = actual_outcome_for_parlay_leg(answer, result)
    if actual_outcome is None:
        return {
            **_focus_answer_identity(answer),
            "result_status": "unresolved",
            "hit": None,
            "actual_outcome": None,
            "expected_probability": expected_probability,
            "calibration_error": None,
            "reason": "unsupported_or_incomplete_market",
        }

    hit = actual_outcome == selected_outcome
    return {
        **_focus_answer_identity(answer),
        "result_status": "won" if hit else "lost",
        "hit": hit,
        "actual_outcome": actual_outcome,
        "expected_probability": expected_probability,
        "calibration_error": _hit_calibration_error(
            hit=hit,
            expected_hit_probability=expected_probability,
        ),
        "reason": None,
    }


def _focus_answer_identity(answer: Mapping[str, object]) -> dict[str, object]:
    return {
        "fixture_id": _optional_str(answer.get("fixture_id")),
        "market_type": _optional_str(answer.get("market_type")),
        "outcome": _optional_str(answer.get("outcome")),
        "line": _optional_float(answer.get("line")),
        "side": _optional_str(answer.get("side")),
        "decimal_odds": _optional_float(answer.get("decimal_odds")),
        "recommendation_score": _optional_float(answer.get("recommendation_score")),
        "upset_protection_score": _optional_float(answer.get("upset_protection_score")),
        "model_version": _optional_str(answer.get("model_version")),
        "prediction_snapshot_id": _optional_int(answer.get("prediction_snapshot_id")),
    }


def _focus_policy_answers(
    explanation_json: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    payload = explanation_json.get("focus_policy_answers")
    if not isinstance(payload, Mapping):
        internal_trace = explanation_json.get("internal_trace")
        if not isinstance(internal_trace, Mapping):
            return {}
        payload = internal_trace.get("focus_policy_answers")
    if not isinstance(payload, Mapping):
        return {}
    focus_answers: dict[str, Mapping[str, object]] = {}
    for key in ("single", "upset"):
        item = payload.get(key)
        if isinstance(item, Mapping):
            focus_answers[key] = item
    return focus_answers


def _focus_metrics_from_policy_evaluation(
    focus_policy_evaluation: Mapping[str, object],
) -> RecommendationFocusMetrics:
    single = focus_policy_evaluation.get("single")
    upset = focus_policy_evaluation.get("upset")
    single_mapping = single if isinstance(single, Mapping) else {}
    upset_mapping = upset if isinstance(upset, Mapping) else {}
    return RecommendationFocusMetrics(
        single_focus_hit=_optional_bool(single_mapping.get("hit")),
        single_focus_expected_probability=_optional_float(
            single_mapping.get("expected_probability")
        ),
        single_focus_calibration_error=_optional_float(single_mapping.get("calibration_error")),
        upset_focus_triggered=bool(upset_mapping),
        upset_focus_captured=_optional_bool(upset_mapping.get("hit")),
        upset_focus_expected_probability=_optional_float(
            upset_mapping.get("expected_probability")
        ),
        upset_focus_calibration_error=_optional_float(upset_mapping.get("calibration_error")),
    )


def _focus_metrics_from_settlement_detail(
    settlement_detail_json: Mapping[str, object],
) -> RecommendationFocusMetrics:
    focus_policy_evaluation = settlement_detail_json.get("focus_policy_evaluation")
    if not isinstance(focus_policy_evaluation, Mapping):
        return _focus_metrics_from_policy_evaluation({})
    return _focus_metrics_from_policy_evaluation(focus_policy_evaluation)


def _hit_calibration_error(
    *,
    hit: bool | None,
    expected_hit_probability: float | None,
) -> float | None:
    if hit is None or expected_hit_probability is None:
        return None
    return (1.0 if hit else 0.0) - expected_hit_probability


def _settle_atomic_bet(
    atomic_bet: Mapping[str, object],
    *,
    result_rows: Sequence[Mapping[str, object]],
) -> ParlayAtomicSettlement:
    return settle_parlay_atomic_bet(
        _json_mapping_array(atomic_bet.get("legs")),
        result_rows,
        stake=_float(atomic_bet["stake"]),
        odds_product=_float(atomic_bet["odds_product"]),
    )


def _evaluation_status(
    *,
    total_atomic_bets: int,
    unresolved_atomic_bets: int,
) -> RecommendationEvaluationStatus:
    if total_atomic_bets == 0 or unresolved_atomic_bets == total_atomic_bets:
        return "unresolved"
    if unresolved_atomic_bets > 0:
        return "partial"
    return "settled"


def _run_for_evaluation_from_row(row: DatabaseRow) -> RecommendationRunForEvaluation:
    parlay_evaluation_json = _json_object(row.get("parlay_evaluation_json"))
    return RecommendationRunForEvaluation(
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=str(row["mode"]),
        recommendation_status=str(row["recommendation_status"]),
        unit_stake=_float(row["unit_stake"]),
        total_stake=_float(row["total_stake"]),
        selected_fixture_ids=_string_list(row.get("selected_fixture_ids_json")),
        locked_fixture_ids=_string_list(row.get("locked_fixture_ids_json")),
        parlay_evaluation_json=parlay_evaluation_json,
        explanation_json=_json_object(row.get("explanation_json")),
        expected_hit_probability_at_recommendation=_optional_float(
            parlay_evaluation_json.get("hit_probability")
        ),
        expected_value_at_recommendation=_optional_float(
            parlay_evaluation_json.get("expected_value")
        ),
        expected_roi_at_recommendation=_optional_float(parlay_evaluation_json.get("roi")),
        created_at=_datetime(row["created_at"]),
    )


def _run_evaluation_from_row(row: DatabaseRow) -> RecommendationRunEvaluation:
    settlement_detail_json = _json_object(row.get("settlement_detail_json"))
    focus_metrics = _focus_metrics_from_settlement_detail(settlement_detail_json)
    return RecommendationRunEvaluation(
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=str(row["mode"]),
        recommendation_status=str(row["recommendation_status"]),
        evaluation_status=_evaluation_status_literal(row["evaluation_status"]),
        total_atomic_bets=_int(row["total_atomic_bets"]),
        settled_atomic_bets=_int(row["settled_atomic_bets"]),
        won_atomic_bets=_int(row["won_atomic_bets"]),
        lost_atomic_bets=_int(row["lost_atomic_bets"]),
        unresolved_atomic_bets=_int(row["unresolved_atomic_bets"]),
        unit_stake=_float(row["unit_stake"]),
        total_stake=_float(row["total_stake"]),
        gross_payout=_float(row["gross_payout"]),
        profit_loss=_float(row["profit_loss"]),
        roi=_float(row["roi"]),
        hit=_optional_bool(row.get("hit")),
        hit_rate=_optional_float(row.get("hit_rate")),
        expected_hit_probability_at_recommendation=_optional_float(
            row.get("expected_hit_probability_at_recommendation")
        ),
        hit_calibration_error=_optional_float(row.get("hit_calibration_error")),
        expected_value_at_recommendation=_optional_float(
            row.get("expected_value_at_recommendation")
        ),
        expected_roi_at_recommendation=_optional_float(row.get("expected_roi_at_recommendation")),
        single_focus_hit=focus_metrics.single_focus_hit,
        single_focus_expected_probability=focus_metrics.single_focus_expected_probability,
        single_focus_calibration_error=focus_metrics.single_focus_calibration_error,
        upset_focus_triggered=focus_metrics.upset_focus_triggered,
        upset_focus_captured=focus_metrics.upset_focus_captured,
        upset_focus_expected_probability=focus_metrics.upset_focus_expected_probability,
        upset_focus_calibration_error=focus_metrics.upset_focus_calibration_error,
        locked_fixture_count=_int(row["locked_fixture_count"]),
        selected_fixture_count=_int(row["selected_fixture_count"]),
        evaluation_time_utc=_datetime(row["evaluation_time_utc"]),
        settlement_detail_json=settlement_detail_json,
    )


def _evaluation_params(
    evaluation: RecommendationRunEvaluation,
    *,
    source: str,
) -> QueryParams:
    return {
        "recommendation_run_id": evaluation.recommendation_run_id,
        "run_key": evaluation.run_key,
        "strategy": evaluation.strategy,
        "pass_type": evaluation.pass_type,
        "mode": evaluation.mode,
        "recommendation_status": evaluation.recommendation_status,
        "evaluation_status": evaluation.evaluation_status,
        "total_atomic_bets": evaluation.total_atomic_bets,
        "settled_atomic_bets": evaluation.settled_atomic_bets,
        "won_atomic_bets": evaluation.won_atomic_bets,
        "lost_atomic_bets": evaluation.lost_atomic_bets,
        "unresolved_atomic_bets": evaluation.unresolved_atomic_bets,
        "unit_stake": evaluation.unit_stake,
        "total_stake": evaluation.total_stake,
        "gross_payout": evaluation.gross_payout,
        "profit_loss": evaluation.profit_loss,
        "roi": evaluation.roi,
        "hit": evaluation.hit,
        "hit_rate": evaluation.hit_rate,
        "expected_hit_probability_at_recommendation": (
            evaluation.expected_hit_probability_at_recommendation
        ),
        "hit_calibration_error": evaluation.hit_calibration_error,
        "expected_value_at_recommendation": evaluation.expected_value_at_recommendation,
        "expected_roi_at_recommendation": evaluation.expected_roi_at_recommendation,
        "locked_fixture_count": evaluation.locked_fixture_count,
        "selected_fixture_count": evaluation.selected_fixture_count,
        "evaluation_time_utc": evaluation.evaluation_time_utc,
        "settlement_detail_json": _json(evaluation.settlement_detail_json),
        "source": source,
    }


def _evaluation_status_literal(value: object) -> RecommendationEvaluationStatus:
    text = str(value)
    if text not in {"settled", "partial", "unresolved"}:
        raise ValueError(f"unsupported recommendation evaluation status: {text}")
    return text  # type: ignore[return-value]


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    parsed = loads(value) if isinstance(value, str) else value
    if isinstance(parsed, Mapping):
        return dict(parsed)
    raise ValueError(f"expected JSON object, got {type(value).__name__}")


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    parsed = loads(value) if isinstance(value, str) else value
    if isinstance(parsed, Sequence) and not isinstance(parsed, str | bytes | bytearray):
        return list(parsed)
    raise ValueError(f"expected JSON array, got {type(value).__name__}")


def _json_mapping_array(value: object) -> list[Mapping[str, object]]:
    return [item for item in _json_array(value) if isinstance(item, Mapping)]


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_array(value)]


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = str(value).lower()
    if text in {"true", "t", "1", "yes"}:
        return True
    if text in {"false", "f", "0", "no"}:
        return False
    raise ValueError(f"expected boolean value, got {value!r}")
