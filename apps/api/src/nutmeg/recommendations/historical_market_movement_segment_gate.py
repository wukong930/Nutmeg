from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from math import log
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_market_movement_signal_diagnostics import (
    HistoricalMarketMovementSignalDiagnosticOptions,
    HistoricalMarketMovementSignalDiagnosticReport,
    HistoricalMarketMovementSignalGroup,
    build_historical_market_movement_signal_diagnostic_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    _comparison_deltas,
    _comparison_status,
    _final_answer_signature,
    _suite_aggregate_deltas,
    _suite_summary_json,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
    HistoricalRecommendationSuiteQualityGateResult,
    run_historical_recommendation_suite_quality_gate,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalMarketMovementSegmentGateStatus = Literal["generated"]
type HistoricalMarketMovementSegmentCandidateDecision = Literal["accepted", "rejected"]

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
DEFAULT_LOG_LOSS_EPSILON = 1e-12
DEFAULT_MARKET_MOVEMENT_SEGMENT_GATE_ID = "market-movement-segment-gate-shadow-v3.1"


class HistoricalMarketMovementSegmentGateOptions(BaseModel):
    gate_id: str = DEFAULT_MARKET_MOVEMENT_SEGMENT_GATE_ID
    segment_group_keys: tuple[str, ...] = ()
    top_positive_segment_limit: int = Field(default=5, ge=1, le=32)
    min_segment_sample_size: int = Field(default=20, ge=1)
    max_segment_brier_delta: float = 0.0
    max_segment_log_loss_delta: float = 0.0
    max_segment_calibration_error_delta: float | None = None
    min_segment_closing_improved_rate: float | None = None
    movement_weight: float = Field(default=0.50, ge=0.0, le=2.0)
    max_probability_shift: float = Field(default=0.08, ge=0.0, le=0.35)
    min_single_match_sample_size: int = Field(default=1, ge=1)
    min_single_match_hit_rate_delta: float | None = 0.0
    max_single_match_brier_delta: float | None = 0.0
    max_single_match_log_loss_delta: float | None = 0.0
    diagnostics_options: HistoricalMarketMovementSignalDiagnosticOptions = Field(
        default_factory=HistoricalMarketMovementSignalDiagnosticOptions
    )
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions = Field(
        default_factory=HistoricalRecommendationSuiteQualityGateOptions
    )


class HistoricalMarketMovementSegmentMetricSet(BaseModel):
    sample_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    average_actual_probability: float | None = Field(default=None, ge=0.0, le=1.0)


class HistoricalMarketMovementSegmentCandidate(BaseModel):
    rank: int = Field(ge=1)
    candidate_id: str
    segment_group_key: str
    segment_group_type: str
    segment_label: str
    decision: HistoricalMarketMovementSegmentCandidateDecision
    decision_reasons: list[str] = Field(default_factory=list)
    segment_sample_count: int = Field(ge=0)
    segment_brier_score_delta: float | None = None
    segment_log_loss_delta: float | None = None
    segment_calibration_error_delta: float | None = None
    segment_closing_improved_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    adjusted_fixture_count: int = Field(ge=0)
    adjusted_prediction_count: int = Field(ge=0)
    single_match_sample_count: int = Field(ge=0)
    baseline_single_match_metrics: HistoricalMarketMovementSegmentMetricSet
    candidate_single_match_metrics: HistoricalMarketMovementSegmentMetricSet
    single_match_deltas_json: dict[str, object] = Field(default_factory=dict)
    passed_single_match_gate: bool
    suite: HistoricalRecommendationBacktestSuiteResult
    quality_gate: HistoricalRecommendationSuiteQualityGateResult
    passed_final_answer_gate: bool
    final_answer_deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementSegmentGateReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementSegmentGateStatus
    gate_id: str
    diagnostics_report_key: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    diagnostics_observation_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    best_candidate: HistoricalMarketMovementSegmentCandidate | None = None
    candidates: list[HistoricalMarketMovementSegmentCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _OutcomeMovement:
    outcome: str
    opening_probability: float
    closing_probability: float
    probability_delta: float
    abs_probability_delta: float
    movement_direction: str
    opening_decimal_odds: float | None = None
    closing_decimal_odds: float | None = None
    is_strongest_fixture_movement: bool = False


@dataclass(frozen=True)
class _AdjustedSlices:
    slices: list[HistoricalRecommendationSlice]
    adjusted_fixture_count: int
    adjusted_prediction_count: int
    baseline_metrics: HistoricalMarketMovementSegmentMetricSet
    candidate_metrics: HistoricalMarketMovementSegmentMetricSet
    metric_deltas: dict[str, object]


@dataclass
class _MetricAccumulator:
    sample_count: int = 0
    hit_count: int = 0
    brier_score_sum: float = 0.0
    log_loss_sum: float = 0.0
    actual_probability_sum: float = 0.0

    def observe(self, probabilities: Mapping[str, float], actual_outcome: str) -> None:
        actual_probability = _clamped_probability(probabilities.get(actual_outcome, 0.0))
        predicted_outcome = max(probabilities.items(), key=lambda item: item[1])[0]
        self.sample_count += 1
        self.hit_count += int(predicted_outcome == actual_outcome)
        self.brier_score_sum += _multi_outcome_brier_score(probabilities, actual_outcome)
        self.log_loss_sum += -log(actual_probability)
        self.actual_probability_sum += actual_probability

    def metrics(self) -> HistoricalMarketMovementSegmentMetricSet:
        return HistoricalMarketMovementSegmentMetricSet(
            sample_count=self.sample_count,
            hit_count=self.hit_count,
            hit_rate=_ratio(self.hit_count, self.sample_count),
            brier_score=_float_ratio(self.brier_score_sum, self.sample_count),
            log_loss=_float_ratio(self.log_loss_sum, self.sample_count),
            average_actual_probability=_float_ratio(
                self.actual_probability_sum,
                self.sample_count,
            ),
        )


def build_historical_market_movement_segment_gate_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementSegmentGateOptions | None = None,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport | None = None,
) -> HistoricalMarketMovementSegmentGateReport:
    resolved_options = options or HistoricalMarketMovementSegmentGateOptions()
    resolved_diagnostics_report = (
        diagnostics_report
        or build_historical_market_movement_signal_diagnostic_report(
            historical_slices,
            options=resolved_options.diagnostics_options,
        )
    )
    selected_groups, selection_warnings = _selected_segment_groups(
        resolved_diagnostics_report,
        options=resolved_options,
    )
    candidate_evaluations = [
        _candidate_evaluation(
            group,
            historical_slices,
            diagnostics_report=resolved_diagnostics_report,
            options=resolved_options,
            ordinal=ordinal,
        )
        for ordinal, group in enumerate(selected_groups, start=1)
    ]
    ranked_candidates = [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(
            sorted(candidate_evaluations, key=_candidate_sort_key),
            start=1,
        )
    ]
    best_candidate = ranked_candidates[0] if ranked_candidates else None
    accepted_count = sum(
        1 for candidate in ranked_candidates if candidate.decision == "accepted"
    )
    warnings = _report_warnings(ranked_candidates, selection_warnings)
    report_key = _report_key(
        historical_slices,
        diagnostics_report=resolved_diagnostics_report,
        options=resolved_options,
        candidates=ranked_candidates,
    )
    fixture_count = sum(len(item.fixtures) for item in historical_slices)
    summary: dict[str, object] = {
        "calculation_basis": "historical_market_movement_segment_gate_v3_1",
        "report_key": report_key,
        "gate_id": resolved_options.gate_id,
        "shadow_only": True,
        "diagnostics_report_key": resolved_diagnostics_report.report_key,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "diagnostics_observation_count": (
            resolved_diagnostics_report.observation_count
        ),
        "candidate_count": len(ranked_candidates),
        "accepted_count": accepted_count,
        "rejected_count": len(ranked_candidates) - accepted_count,
        "best_candidate_id": best_candidate.candidate_id if best_candidate else None,
        "best_segment_group_key": (
            best_candidate.segment_group_key if best_candidate else None
        ),
        "best_decision": best_candidate.decision if best_candidate else None,
        "best_decision_reasons": (
            best_candidate.decision_reasons if best_candidate else []
        ),
        "warnings": warnings,
    }
    return HistoricalMarketMovementSegmentGateReport(
        report_key=report_key,
        status="generated",
        gate_id=resolved_options.gate_id,
        diagnostics_report_key=resolved_diagnostics_report.report_key,
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        diagnostics_observation_count=resolved_diagnostics_report.observation_count,
        candidate_count=len(ranked_candidates),
        accepted_count=accepted_count,
        rejected_count=len(ranked_candidates) - accepted_count,
        best_candidate=best_candidate,
        candidates=ranked_candidates,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    diagnostics_report = _load_diagnostics_report(args.diagnostics_report_path)
    report = build_historical_market_movement_segment_gate_report(
        loaded_slices.slices,
        options=_options_from_args(args),
        diagnostics_report=diagnostics_report,
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if report.accepted_count <= 0 and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_evaluation(
    segment_group: HistoricalMarketMovementSignalGroup,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    options: HistoricalMarketMovementSegmentGateOptions,
    ordinal: int,
) -> HistoricalMarketMovementSegmentCandidate:
    candidate_id = _candidate_id(
        segment_group,
        diagnostics_report=diagnostics_report,
        options=options,
    )
    adjusted = _adjusted_historical_slices(
        historical_slices,
        segment_group=segment_group,
        diagnostics_report=diagnostics_report,
        candidate_id=candidate_id,
        options=options,
    )
    suite = _segment_candidate_suite(
        historical_slices,
        adjusted_slices=adjusted.slices,
        segment_group=segment_group,
        candidate_id=candidate_id,
        adjusted_fixture_count=adjusted.adjusted_fixture_count,
        adjusted_prediction_count=adjusted.adjusted_prediction_count,
        backtest_options=options.backtest_options,
    )
    quality_gate = run_historical_recommendation_suite_quality_gate(
        suite,
        options=options.quality_gate_options,
    )
    passed_single_match_gate, single_reasons = _single_match_gate_decision(
        adjusted,
        options=options,
    )
    decision_reasons = [
        *single_reasons,
        *_quality_gate_decision_reasons(quality_gate),
    ]
    decision: HistoricalMarketMovementSegmentCandidateDecision = (
        "accepted"
        if passed_single_match_gate and quality_gate.passed
        else "rejected"
    )
    if decision == "accepted":
        decision_reasons = ["segment_gate:accepted"]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_segment_candidate_gate_v3_1"
        ),
        "candidate_id": candidate_id,
        "segment_group_key": segment_group.group_key,
        "segment_group_type": segment_group.group_type,
        "segment_label": segment_group.label,
        "diagnostics_report_key": diagnostics_report.report_key,
        "segment_sample_count": segment_group.sample_count,
        "adjusted_fixture_count": adjusted.adjusted_fixture_count,
        "adjusted_prediction_count": adjusted.adjusted_prediction_count,
        "single_match_deltas": adjusted.metric_deltas,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "quality_gate_key": quality_gate.gate_key,
        "quality_gate_passed": quality_gate.passed,
        "decision": decision,
        "decision_reasons": decision_reasons,
        "shadow_only": True,
    }
    return HistoricalMarketMovementSegmentCandidate(
        rank=ordinal,
        candidate_id=candidate_id,
        segment_group_key=segment_group.group_key,
        segment_group_type=segment_group.group_type,
        segment_label=segment_group.label,
        decision=decision,
        decision_reasons=decision_reasons,
        segment_sample_count=segment_group.sample_count,
        segment_brier_score_delta=segment_group.brier_score_delta,
        segment_log_loss_delta=segment_group.log_loss_delta,
        segment_calibration_error_delta=segment_group.calibration_error_delta,
        segment_closing_improved_rate=segment_group.closing_improved_rate,
        adjusted_fixture_count=adjusted.adjusted_fixture_count,
        adjusted_prediction_count=adjusted.adjusted_prediction_count,
        single_match_sample_count=adjusted.candidate_metrics.sample_count,
        baseline_single_match_metrics=adjusted.baseline_metrics,
        candidate_single_match_metrics=adjusted.candidate_metrics,
        single_match_deltas_json=adjusted.metric_deltas,
        passed_single_match_gate=passed_single_match_gate,
        suite=suite,
        quality_gate=quality_gate,
        passed_final_answer_gate=quality_gate.passed,
        final_answer_deltas_json=suite.aggregate_deltas_json,
        summary_json=summary,
    )


def _adjusted_historical_slices(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    segment_group: HistoricalMarketMovementSignalGroup,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    candidate_id: str,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> _AdjustedSlices:
    adjusted_fixture_count = 0
    adjusted_prediction_count = 0
    baseline_metrics = _MetricAccumulator()
    candidate_metrics = _MetricAccumulator()
    adjusted_slices: list[HistoricalRecommendationSlice] = []

    for historical_slice in historical_slices:
        adjusted_fixtures: list[HistoricalFixture] = []
        for fixture in historical_slice.fixtures:
            adjusted_fixture, changed_prediction_count = _adjusted_fixture(
                fixture,
                segment_group=segment_group,
                diagnostics_report=diagnostics_report,
                candidate_id=candidate_id,
                options=options,
            )
            adjusted_fixtures.append(adjusted_fixture)
            if changed_prediction_count <= 0:
                continue
            adjusted_fixture_count += 1
            adjusted_prediction_count += changed_prediction_count
            baseline_probs = _one_x_two_probabilities(fixture)
            candidate_probs = _one_x_two_probabilities(adjusted_fixture)
            if baseline_probs is None or candidate_probs is None:
                continue
            actual_outcome = fixture.actual_1x2_outcome
            baseline_metrics.observe(baseline_probs, actual_outcome)
            candidate_metrics.observe(candidate_probs, actual_outcome)

        adjusted_slices.append(
            historical_slice.model_copy(
                update={
                    "metadata": historical_slice.metadata.model_copy(
                        update={
                            "slice_id": _adjusted_slice_id(
                                historical_slice.metadata.slice_id,
                                candidate_id=candidate_id,
                            ),
                            "notes": [
                                *historical_slice.metadata.notes,
                                (
                                    "Shadow-only segmented market movement "
                                    "probability adjustment for final-answer gate "
                                    "evaluation."
                                ),
                            ],
                        }
                    ),
                    "fixtures": adjusted_fixtures,
                }
            )
        )

    baseline = baseline_metrics.metrics()
    candidate = candidate_metrics.metrics()
    return _AdjustedSlices(
        slices=adjusted_slices,
        adjusted_fixture_count=adjusted_fixture_count,
        adjusted_prediction_count=adjusted_prediction_count,
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        metric_deltas=_metric_deltas(baseline, candidate),
    )


def _adjusted_fixture(
    fixture: HistoricalFixture,
    *,
    segment_group: HistoricalMarketMovementSignalGroup,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    candidate_id: str,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> tuple[HistoricalFixture, int]:
    probabilities = _one_x_two_probabilities(fixture)
    if probabilities is None:
        return fixture, 0
    movements = _fixture_movements(fixture, options=options.diagnostics_options)
    if not movements:
        return fixture, 0

    shifts: dict[str, float] = {}
    for outcome, movement in movements.items():
        if not _movement_matches_segment(
            fixture,
            movement,
            segment_group=segment_group,
            options=options,
        ):
            continue
        shift = _clamp(
            movement.probability_delta * options.movement_weight,
            -options.max_probability_shift,
            options.max_probability_shift,
        )
        if abs(shift) <= DEFAULT_LOG_LOSS_EPSILON:
            continue
        shifts[outcome] = shift
    if not shifts:
        return fixture, 0

    adjusted_probabilities = _renormalized_shifted_probabilities(probabilities, shifts)
    if adjusted_probabilities is None:
        return fixture, 0
    changed_prediction_count = sum(
        1
        for outcome in ONE_X_TWO_OUTCOMES
        if abs(adjusted_probabilities[outcome] - probabilities[outcome])
        > DEFAULT_LOG_LOSS_EPSILON
    )
    if changed_prediction_count <= 0:
        return fixture, 0

    update_metadata: dict[str, object] = {
        "market_movement_segment_shadow_adjusted": True,
        "market_movement_segment_gate_id": options.gate_id,
        "market_movement_segment_candidate_id": candidate_id,
        "market_movement_segment_group_key": segment_group.group_key,
        "market_movement_segment_group_type": segment_group.group_type,
        "market_movement_segment_diagnostics_report_key": (
            diagnostics_report.report_key
        ),
        "market_movement_segment_matched_outcomes": sorted(shifts),
        "market_movement_segment_probability_shifts": shifts,
        "shadow_only": True,
    }
    return (
        fixture.model_copy(
            update={
                "model_version": f"{fixture.model_version}+market-movement-segment-shadow",
                "predictions": [
                    _adjusted_prediction(
                        prediction,
                        adjusted_probabilities=adjusted_probabilities,
                        update_metadata=update_metadata,
                    )
                    for prediction in fixture.predictions
                ],
                "metadata_json": {
                    **fixture.metadata_json,
                    **update_metadata,
                },
            }
        ),
        changed_prediction_count,
    )


def _adjusted_prediction(
    prediction: HistoricalMarketPrediction,
    *,
    adjusted_probabilities: Mapping[str, float],
    update_metadata: Mapping[str, object],
) -> HistoricalMarketPrediction:
    if prediction.market_type != "1x2" or prediction.outcome not in adjusted_probabilities:
        return prediction
    adjusted_probability = adjusted_probabilities[prediction.outcome]
    market_probability = (
        prediction.market_probability
        if prediction.market_probability is not None
        else 1.0 / prediction.decimal_odds
    )
    return prediction.model_copy(
        update={
            "probability": adjusted_probability,
            "model_edge": adjusted_probability - market_probability,
            "metadata_json": {
                **prediction.metadata_json,
                **update_metadata,
                "market_movement_segment_baseline_probability": prediction.probability,
                "market_movement_segment_adjusted_probability": adjusted_probability,
            },
        }
    )


def _segment_candidate_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    adjusted_slices: Sequence[HistoricalRecommendationSlice],
    segment_group: HistoricalMarketMovementSignalGroup,
    candidate_id: str,
    adjusted_fixture_count: int,
    adjusted_prediction_count: int,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestSuiteResult:
    comparisons: list[HistoricalRecommendationBacktestComparisonResult] = []
    for baseline_slice, adjusted_slice in zip(historical_slices, adjusted_slices, strict=True):
        baseline = run_historical_recommendation_backtest(
            baseline_slice,
            options=backtest_options,
        )
        candidate = run_historical_recommendation_backtest(
            adjusted_slice,
            options=backtest_options,
        )
        comparisons.append(
            _segment_candidate_comparison(
                baseline_slice,
                baseline=baseline,
                candidate=candidate,
                segment_group=segment_group,
                candidate_id=candidate_id,
                backtest_options=backtest_options,
            )
        )
    aggregate_deltas = _suite_aggregate_deltas(comparisons)
    status = (
        _comparison_status(aggregate_deltas)
        if comparisons
        else "insufficient_samples"
    )
    summary = _suite_summary_json(
        historical_slices,
        comparisons=comparisons,
        aggregate_deltas=aggregate_deltas,
        status=status,
        baseline_optimizer_profile=backtest_options.optimizer_profile,
        candidate_optimizer_profile=backtest_options.optimizer_profile,
    )
    summary.update(
        {
            "calculation_basis": "historical_market_movement_segment_gate_suite_v3_1",
            "candidate_id": candidate_id,
            "segment_group_key": segment_group.group_key,
            "segment_group_type": segment_group.group_type,
            "adjusted_fixture_count": adjusted_fixture_count,
            "adjusted_prediction_count": adjusted_prediction_count,
            "shadow_only": True,
        }
    )
    warnings = _suite_warnings(comparisons=comparisons, status=status)
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=_segment_suite_key(
            historical_slices,
            segment_group=segment_group,
            candidate_id=candidate_id,
            backtest_options=backtest_options,
        ),
        status=status,
        slice_count=len(historical_slices),
        comparison_count=len(comparisons),
        baseline_optimizer_profile=backtest_options.optimizer_profile,
        candidate_optimizer_profile=backtest_options.optimizer_profile,
        comparisons=comparisons,
        aggregate_deltas_json=aggregate_deltas,
        warnings=warnings,
        summary_json=summary,
    )


def _segment_candidate_comparison(
    historical_slice: HistoricalRecommendationSlice,
    *,
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
    segment_group: HistoricalMarketMovementSignalGroup,
    candidate_id: str,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestComparisonResult:
    deltas = _comparison_deltas(baseline, candidate)
    status = _comparison_status(deltas)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_segment_gate_comparison_v3_1"
        ),
        "slice_id": historical_slice.metadata.slice_id,
        "candidate_id": candidate_id,
        "segment_group_key": segment_group.group_key,
        "segment_group_type": segment_group.group_type,
        "baseline_backtest_key": baseline.backtest_key,
        "candidate_backtest_key": candidate.backtest_key,
        "baseline_final_answer_scenario_key": _scenario_key(baseline.final_answer),
        "candidate_final_answer_scenario_key": _scenario_key(candidate.final_answer),
        "final_answer_changed": (
            _final_answer_signature(baseline.final_answer)
            != _final_answer_signature(candidate.final_answer)
        ),
        "deltas": deltas,
        "shadow_only": True,
    }
    return HistoricalRecommendationBacktestComparisonResult(
        comparison_key=_segment_comparison_key(
            historical_slice,
            segment_group=segment_group,
            candidate_id=candidate_id,
            backtest_options=backtest_options,
        ),
        slice_id=historical_slice.metadata.slice_id,
        baseline_optimizer_profile=backtest_options.optimizer_profile,
        candidate_optimizer_profile=backtest_options.optimizer_profile,
        status=status,
        baseline=baseline,
        candidate=candidate,
        deltas_json=deltas,
        summary_json=summary,
    )


def _selected_segment_groups(
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    *,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> tuple[list[HistoricalMarketMovementSignalGroup], list[str]]:
    warnings: list[str] = []
    group_by_key = {group.group_key: group for group in diagnostics_report.groups}
    if options.segment_group_keys:
        selected: list[HistoricalMarketMovementSignalGroup] = []
        for group_key in options.segment_group_keys:
            group = group_by_key.get(group_key)
            if group is None:
                warnings.append(f"market_movement_segment_gate:missing_group:{group_key}")
                continue
            selected.append(group)
        return selected, warnings

    selected = [
        group
        for group in diagnostics_report.top_positive_signal_groups
        if _segment_group_is_eligible(group, options=options)
    ][: options.top_positive_segment_limit]
    if not selected:
        warnings.append("market_movement_segment_gate:no_eligible_positive_segment")
    return selected, warnings


def _segment_group_is_eligible(
    group: HistoricalMarketMovementSignalGroup,
    *,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> bool:
    if group.group_type == "overall":
        return False
    if group.sample_count < options.min_segment_sample_size:
        return False
    if (
        group.brier_score_delta is None
        or group.brier_score_delta > options.max_segment_brier_delta
    ):
        return False
    if (
        group.log_loss_delta is None
        or group.log_loss_delta > options.max_segment_log_loss_delta
    ):
        return False
    if (
        options.max_segment_calibration_error_delta is not None
        and (
            group.calibration_error_delta is None
            or group.calibration_error_delta
            > options.max_segment_calibration_error_delta
        )
    ):
        return False
    return not (
        options.min_segment_closing_improved_rate is not None
        and (
            group.closing_improved_rate is None
            or group.closing_improved_rate
            < options.min_segment_closing_improved_rate
        )
    )


def _fixture_movements(
    fixture: HistoricalFixture,
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> dict[str, _OutcomeMovement]:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return {}
    prematch_context = _mapping(snapshot.features_json.get("prematch_context"))
    if prematch_context is None:
        return {}
    raw_movements = _list_of_mappings(prematch_context.get("odds_movement"))
    movements: dict[str, _OutcomeMovement] = {}
    for raw_movement in raw_movements:
        movement = _outcome_movement(raw_movement, options=options)
        if movement is None:
            continue
        movements[movement.outcome] = movement
    if not movements:
        return {}
    strongest_abs_delta = max(
        movement.abs_probability_delta for movement in movements.values()
    )
    return {
        outcome: movement
        if movement.abs_probability_delta != strongest_abs_delta
        else _OutcomeMovement(
            outcome=movement.outcome,
            opening_probability=movement.opening_probability,
            closing_probability=movement.closing_probability,
            probability_delta=movement.probability_delta,
            abs_probability_delta=movement.abs_probability_delta,
            movement_direction=movement.movement_direction,
            opening_decimal_odds=movement.opening_decimal_odds,
            closing_decimal_odds=movement.closing_decimal_odds,
            is_strongest_fixture_movement=True,
        )
        for outcome, movement in movements.items()
    }


def _outcome_movement(
    movement: Mapping[str, object],
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> _OutcomeMovement | None:
    if movement.get("market_type") != "1x2":
        return None
    outcome = str(movement.get("outcome") or "")
    if outcome not in ONE_X_TWO_OUTCOMES:
        return None
    opening_probability = _first_float(
        movement,
        ("opening_prob", "opening_probability"),
    )
    closing_probability = _first_float(
        movement,
        ("current_prob", "closing_prob", "closing_probability", "current_probability"),
    )
    if opening_probability is None or closing_probability is None:
        return None
    probability_delta = closing_probability - opening_probability
    abs_delta = abs(probability_delta)
    if abs_delta < options.min_abs_probability_delta:
        return None
    return _OutcomeMovement(
        outcome=outcome,
        opening_probability=opening_probability,
        closing_probability=closing_probability,
        probability_delta=probability_delta,
        abs_probability_delta=abs_delta,
        movement_direction=_movement_direction(
            probability_delta,
            epsilon=options.movement_direction_epsilon,
        ),
        opening_decimal_odds=_first_float(
            movement,
            ("opening_decimal_odds", "opening_odds"),
        ),
        closing_decimal_odds=_first_float(
            movement,
            ("current_decimal_odds", "closing_decimal_odds", "closing_odds"),
        ),
    )


def _movement_matches_segment(
    fixture: HistoricalFixture,
    movement: _OutcomeMovement,
    *,
    segment_group: HistoricalMarketMovementSignalGroup,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> bool:
    if segment_group.group_type == "outcome":
        return movement.outcome == segment_group.outcome
    if segment_group.group_type == "movement_direction":
        return movement.movement_direction == segment_group.movement_direction
    if segment_group.group_type == "delta_band":
        return _value_in_band(movement.abs_probability_delta, segment_group.band)
    if segment_group.group_type == "opening_probability_band":
        return _value_in_band(movement.opening_probability, segment_group.band)
    if segment_group.group_type == "strongest_movement_direction":
        return (
            movement.is_strongest_fixture_movement
            and movement.movement_direction == segment_group.movement_direction
        )
    if segment_group.group_type == "competition":
        return fixture.competition_id == segment_group.competition_id
    if segment_group.group_type == "competition_outcome":
        return (
            fixture.competition_id == segment_group.competition_id
            and movement.outcome == segment_group.outcome
        )
    if segment_group.group_type == "competition_direction":
        return (
            fixture.competition_id == segment_group.competition_id
            and movement.movement_direction == segment_group.movement_direction
        )
    return False


def _one_x_two_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    probabilities = {
        prediction.outcome: prediction.probability
        for prediction in fixture.predictions
        if prediction.market_type == "1x2" and prediction.outcome in ONE_X_TWO_OUTCOMES
    }
    if set(probabilities) != set(ONE_X_TWO_OUTCOMES):
        return None
    normalized = _normalize_probabilities(probabilities)
    return normalized if normalized is not None else None


def _renormalized_shifted_probabilities(
    probabilities: Mapping[str, float],
    shifts: Mapping[str, float],
) -> dict[str, float] | None:
    shifted = {
        outcome: max(DEFAULT_LOG_LOSS_EPSILON, probabilities[outcome] + shifts.get(outcome, 0.0))
        for outcome in ONE_X_TWO_OUTCOMES
    }
    return _normalize_probabilities(shifted)


def _normalize_probabilities(
    probabilities: Mapping[str, float],
) -> dict[str, float] | None:
    total = sum(
        max(DEFAULT_LOG_LOSS_EPSILON, probabilities[outcome])
        for outcome in ONE_X_TWO_OUTCOMES
    )
    if total <= DEFAULT_LOG_LOSS_EPSILON:
        return None
    return {
        outcome: max(DEFAULT_LOG_LOSS_EPSILON, probabilities[outcome]) / total
        for outcome in ONE_X_TWO_OUTCOMES
    }


def _metric_deltas(
    baseline: HistoricalMarketMovementSegmentMetricSet,
    candidate: HistoricalMarketMovementSegmentMetricSet,
) -> dict[str, object]:
    return {
        "sample_count_delta": candidate.sample_count - baseline.sample_count,
        "hit_count_delta": candidate.hit_count - baseline.hit_count,
        "hit_rate_delta": _optional_delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _optional_delta(
            candidate.brier_score,
            baseline.brier_score,
        ),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "average_actual_probability_delta": _optional_delta(
            candidate.average_actual_probability,
            baseline.average_actual_probability,
        ),
    }


def _single_match_gate_decision(
    adjusted: _AdjustedSlices,
    *,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if adjusted.adjusted_fixture_count <= 0:
        reasons.append("single_match:no_adjusted_fixtures")
    if adjusted.candidate_metrics.sample_count < options.min_single_match_sample_size:
        reasons.append("single_match:sample_size")
    hit_rate_delta = _number(adjusted.metric_deltas.get("hit_rate_delta"))
    if (
        options.min_single_match_hit_rate_delta is not None
        and (
            hit_rate_delta is None
            or hit_rate_delta < options.min_single_match_hit_rate_delta
        )
    ):
        reasons.append("single_match:hit_rate_delta")
    brier_delta = _number(adjusted.metric_deltas.get("brier_score_delta"))
    if (
        options.max_single_match_brier_delta is not None
        and (
            brier_delta is None
            or brier_delta > options.max_single_match_brier_delta
        )
    ):
        reasons.append("single_match:brier_score_delta")
    log_loss_delta = _number(adjusted.metric_deltas.get("log_loss_delta"))
    if (
        options.max_single_match_log_loss_delta is not None
        and (
            log_loss_delta is None
            or log_loss_delta > options.max_single_match_log_loss_delta
        )
    ):
        reasons.append("single_match:log_loss_delta")
    return not reasons, reasons


def _quality_gate_decision_reasons(
    quality_gate: HistoricalRecommendationSuiteQualityGateResult,
) -> list[str]:
    if quality_gate.passed:
        return []
    return [
        f"quality_gate:{check.name}"
        for check in quality_gate.checks
        if check.status == "failed"
    ] or ["quality_gate:failed"]


def _candidate_sort_key(
    candidate: HistoricalMarketMovementSegmentCandidate,
) -> tuple[int, int, float, float, float, float, int]:
    return (
        0 if candidate.decision == "accepted" else 1,
        0 if candidate.suite.status != "regressed" else 1,
        -_delta(candidate.single_match_deltas_json, "hit_rate_delta"),
        _delta(candidate.single_match_deltas_json, "brier_score_delta"),
        _delta(candidate.final_answer_deltas_json, "brier_score_delta"),
        _delta(candidate.final_answer_deltas_json, "log_loss_delta"),
        candidate.rank,
    )


def _suite_warnings(
    *,
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
    status: str,
) -> list[str]:
    warnings: list[str] = []
    if not comparisons:
        warnings.append("market_movement_segment_gate:no_comparisons")
    if status == "regressed":
        warnings.append("market_movement_segment_gate:suite_regressed")
    elif status == "mixed":
        warnings.append("market_movement_segment_gate:suite_mixed")
    return warnings


def _report_warnings(
    candidates: Sequence[HistoricalMarketMovementSegmentCandidate],
    selection_warnings: Sequence[str],
) -> list[str]:
    warnings = list(selection_warnings)
    if not candidates:
        warnings.append("market_movement_segment_gate:no_candidates")
    if candidates and all(candidate.decision != "accepted" for candidate in candidates):
        warnings.append("market_movement_segment_gate:no_accepted_candidate")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Evaluate segmented market-movement probability adjustments as shadow "
            "recommendation candidates."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--diagnostics-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--gate-id", default=DEFAULT_MARKET_MOVEMENT_SEGMENT_GATE_ID)
    parser.add_argument("--segment-group-keys", default="")
    parser.add_argument("--top-positive-segment-limit", type=int, default=5)
    parser.add_argument("--min-segment-sample-size", type=int, default=20)
    parser.add_argument("--max-segment-brier-delta", type=float, default=0.0)
    parser.add_argument("--max-segment-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-segment-calibration-error-delta", type=float)
    parser.add_argument("--min-segment-closing-improved-rate", type=float)
    parser.add_argument("--movement-weight", type=float, default=0.50)
    parser.add_argument("--max-probability-shift", type=float, default=0.08)
    parser.add_argument("--min-single-match-sample-size", type=int, default=1)
    parser.add_argument("--min-single-match-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-single-match-brier-delta", type=float, default=0.0)
    parser.add_argument("--max-single-match-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-abs-probability-delta", type=float, default=0.0)
    parser.add_argument("--movement-direction-epsilon", type=float, default=0.001)
    parser.add_argument("--delta-bands", default="0.00:0.01,0.01:0.03,0.03:0.06,0.06:")
    parser.add_argument(
        "--opening-probability-bands",
        default="0.00:0.25,0.25:0.45,0.45:0.65,0.65:1.00",
    )
    parser.add_argument("--min-diagnostics-group-sample-size", type=int, default=1)
    parser.add_argument(
        "--include-competition-groups",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--observation-sample-limit", type=int, default=20)
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--min-slice-count", type=int, default=1)
    parser.add_argument("--min-comparison-count", type=int, default=1)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--min-candidate-final-hit-rate", type=float)
    parser.add_argument("--min-candidate-roi", type=float)
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float)
    parser.add_argument("--min-profit-loss-delta", type=float)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--max-warning-count", type=int)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalMarketMovementSegmentGateOptions:
    return HistoricalMarketMovementSegmentGateOptions(
        gate_id=args.gate_id,
        segment_group_keys=tuple(_csv(args.segment_group_keys)),
        top_positive_segment_limit=args.top_positive_segment_limit,
        min_segment_sample_size=args.min_segment_sample_size,
        max_segment_brier_delta=args.max_segment_brier_delta,
        max_segment_log_loss_delta=args.max_segment_log_loss_delta,
        max_segment_calibration_error_delta=(
            args.max_segment_calibration_error_delta
        ),
        min_segment_closing_improved_rate=args.min_segment_closing_improved_rate,
        movement_weight=args.movement_weight,
        max_probability_shift=args.max_probability_shift,
        min_single_match_sample_size=args.min_single_match_sample_size,
        min_single_match_hit_rate_delta=args.min_single_match_hit_rate_delta,
        max_single_match_brier_delta=args.max_single_match_brier_delta,
        max_single_match_log_loss_delta=args.max_single_match_log_loss_delta,
        diagnostics_options=HistoricalMarketMovementSignalDiagnosticOptions(
            min_abs_probability_delta=args.min_abs_probability_delta,
            movement_direction_epsilon=args.movement_direction_epsilon,
            delta_bands=tuple(_csv(args.delta_bands)),
            opening_probability_bands=tuple(_csv(args.opening_probability_bands)),
            min_group_sample_size=args.min_diagnostics_group_sample_size,
            include_competition_groups=args.include_competition_groups,
            observation_sample_limit=args.observation_sample_limit,
        ),
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        ),
        quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
            min_slice_count=args.min_slice_count,
            min_comparison_count=args.min_comparison_count,
            min_final_hit_sample_size=args.min_final_hit_sample_size,
            min_candidate_final_hit_rate=args.min_candidate_final_hit_rate,
            min_candidate_roi=args.min_candidate_roi,
            fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
            min_final_hit_rate_delta=args.min_final_hit_rate_delta,
            min_roi_delta=args.min_roi_delta,
            min_profit_loss_delta=args.min_profit_loss_delta,
            max_brier_score_delta=args.max_brier_score_delta,
            max_log_loss_delta=args.max_log_loss_delta,
            max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
            min_final_answer_changed_count=args.min_final_answer_changed_count,
            max_warning_count=args.max_warning_count,
        ),
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _load_diagnostics_report(
    path: Path | None,
) -> HistoricalMarketMovementSignalDiagnosticReport | None:
    if path is None:
        return None
    return HistoricalMarketMovementSignalDiagnosticReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _segment_suite_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    segment_group: HistoricalMarketMovementSignalGroup,
    candidate_id: str,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "as_of_times": [
            historical_slice.as_of_time_utc.isoformat()
            for historical_slice in historical_slices
        ],
        "segment_group_key": segment_group.group_key,
        "candidate_id": candidate_id,
        "backtest_options": backtest_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_segment_gate_suite:{digest}"


def _segment_comparison_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    segment_group: HistoricalMarketMovementSignalGroup,
    candidate_id: str,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> str:
    payload = {
        "slice_id": historical_slice.metadata.slice_id,
        "as_of_time": historical_slice.as_of_time_utc.isoformat(),
        "segment_group_key": segment_group.group_key,
        "candidate_id": candidate_id,
        "backtest_options": backtest_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_segment_gate_comparison:{digest}"


def _candidate_id(
    segment_group: HistoricalMarketMovementSignalGroup,
    *,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    options: HistoricalMarketMovementSegmentGateOptions,
) -> str:
    payload = {
        "gate_id": options.gate_id,
        "diagnostics_report_key": diagnostics_report.report_key,
        "segment_group_key": segment_group.group_key,
        "movement_weight": options.movement_weight,
        "max_probability_shift": options.max_probability_shift,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{options.gate_id}:{segment_group.group_key}:{digest}"


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    diagnostics_report: HistoricalMarketMovementSignalDiagnosticReport,
    options: HistoricalMarketMovementSegmentGateOptions,
    candidates: Sequence[HistoricalMarketMovementSegmentCandidate],
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "diagnostics_report_key": diagnostics_report.report_key,
        "candidate_ids": [candidate.candidate_id for candidate in candidates],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_segment_gate:{digest}"


def _adjusted_slice_id(slice_id: str, *, candidate_id: str) -> str:
    digest = sha256(candidate_id.encode("utf-8")).hexdigest()[:8]
    return f"{slice_id}__market_movement_segment_shadow_{digest}"


def _scenario_key(final_answer: HistoricalRecommendationScenarioResult | None) -> str | None:
    return final_answer.scenario.scenario_key if final_answer is not None else None


def _multi_outcome_brier_score(
    probabilities: Mapping[str, float],
    actual_outcome: str,
) -> float:
    return sum(
        (
            _clamped_probability(probabilities.get(outcome, 0.0))
            - (1.0 if outcome == actual_outcome else 0.0)
        )
        ** 2
        for outcome in ONE_X_TWO_OUTCOMES
    )


def _value_in_band(value: float, band: str | None) -> bool:
    if band is None:
        return False
    lower, upper = _parse_band(band)
    if lower is not None and value < lower:
        return False
    return not (upper is not None and value >= upper)


def _parse_band(band: str) -> tuple[float | None, float | None]:
    if ":" not in band:
        value = float(band)
        return value, value
    lower_raw, upper_raw = band.split(":", 1)
    lower = float(lower_raw) if lower_raw else None
    upper = float(upper_raw) if upper_raw else None
    return lower, upper


def _movement_direction(delta: float, *, epsilon: float) -> str:
    if delta > epsilon:
        return "probability_shortened"
    if delta < -epsilon:
        return "probability_drifted"
    return "stable"


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _list_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_float(
    mapping: Mapping[str, object],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _clamped_probability(value: float) -> float:
    return _clamp(value, DEFAULT_LOG_LOSS_EPSILON, 1.0 - DEFAULT_LOG_LOSS_EPSILON)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _float_ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _delta(deltas: Mapping[str, object], key: str) -> float:
    return _number(deltas.get(key)) or 0.0


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
