from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalShortPriceThresholdGridStatus = Literal["generated"]
type HistoricalShortPriceThresholdCandidateStatus = Literal["accepted", "rejected"]


class HistoricalShortPriceThresholdGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    competition_groups: tuple[tuple[str, ...], ...] = ((),)
    max_decimal_odds_values: tuple[float, ...] = (1.35,)
    min_probability_values: tuple[float, ...] = (0.70,)
    max_model_edge_values: tuple[float, ...] = (0.0,)
    strength_values: tuple[float, ...] = (1.0,)
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    fail_on_suite_statuses: tuple[str, ...] = ("regressed", "mixed")
    min_penalized_candidate_count: int = Field(default=1, ge=0)
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    min_upset_capture_rate_delta: float = 0.0
    require_objective_improvement: bool = True
    min_objective_roi_delta: float = 0.0
    min_objective_upset_capture_rate_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)


class HistoricalShortPriceThresholdCandidate(BaseModel):
    candidate_key: str
    status: HistoricalShortPriceThresholdCandidateStatus
    competition_ids: tuple[str, ...] = ()
    max_decimal_odds: float
    min_probability: float
    max_model_edge: float
    strength: float
    suite_key: str
    suite_status: str
    penalized_candidate_count: int = Field(ge=0)
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    roi: float | None = None
    profit_loss: float
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    upset_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_changed_count: int = Field(default=0, ge=0)
    objective_improvement_satisfied: bool = False
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortPriceThresholdGridReport(BaseModel):
    report_key: str
    status: HistoricalShortPriceThresholdGridStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    baseline_suite_key: str
    baseline_suite_status: str
    baseline_summary_json: dict[str, object] = Field(default_factory=dict)
    candidates: list[HistoricalShortPriceThresholdCandidate] = Field(default_factory=list)
    accepted_candidates: list[HistoricalShortPriceThresholdCandidate] = Field(
        default_factory=list
    )
    best_candidate: HistoricalShortPriceThresholdCandidate | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_short_price_threshold_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalShortPriceThresholdGridOptions | None = None,
) -> HistoricalShortPriceThresholdGridReport:
    resolved_options = options or HistoricalShortPriceThresholdGridOptions()
    baseline_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_baseline_backtest_options(resolved_options.backtest_options),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    candidates = [
        _evaluate_threshold_candidate(
            historical_slices,
            baseline_suite=baseline_suite,
            options=resolved_options,
            competition_ids=competition_ids,
            max_decimal_odds=max_decimal_odds,
            min_probability=min_probability,
            max_model_edge=max_model_edge,
            strength=strength,
        )
        for competition_ids in resolved_options.competition_groups
        for max_decimal_odds in resolved_options.max_decimal_odds_values
        for min_probability in resolved_options.min_probability_values
        for max_model_edge in resolved_options.max_model_edge_values
        for strength in resolved_options.strength_values
    ]
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [*baseline_suite.warnings]
    for candidate in candidates:
        if candidate.suite_status in resolved_options.fail_on_suite_statuses:
            warnings.append(f"threshold_grid:candidate_suite_status:{candidate.suite_status}")
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_price_threshold_grid_v3_1",
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "baseline_suite_key": baseline_suite.suite_key,
        "baseline_suite_status": baseline_suite.status,
        "baseline_candidate_final_hit_rate": _summary_number(
            baseline_suite.summary_json,
            "candidate_final_hit_rate",
        ),
        "baseline_candidate_roi": _summary_number(
            baseline_suite.summary_json,
            "candidate_roi",
        ),
        "baseline_candidate_profit_loss": _summary_number(
            baseline_suite.summary_json,
            "candidate_profit_loss",
        ),
        "require_objective_improvement": (
            resolved_options.require_objective_improvement
        ),
        "min_objective_roi_delta": resolved_options.min_objective_roi_delta,
        "min_objective_upset_capture_rate_delta": (
            resolved_options.min_objective_upset_capture_rate_delta
        ),
        "comparison_epsilon": resolved_options.comparison_epsilon,
        "best_candidate_key": best_candidate.candidate_key
        if best_candidate is not None
        else None,
        "best_candidate_status": best_candidate.status
        if best_candidate is not None
        else None,
        "best_candidate_deltas": best_candidate.deltas_json
        if best_candidate is not None
        else {},
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalShortPriceThresholdGridReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        baseline_suite_key=baseline_suite.suite_key,
        baseline_suite_status=baseline_suite.status,
        baseline_summary_json=baseline_suite.summary_json,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_short_price_threshold_grid_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _baseline_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "short_price_negative_edge_guardrail": False,
            "short_price_negative_edge_soft_penalty": False,
            "short_price_negative_edge_soft_penalty_competition_ids": (),
        }
    )


def _evaluate_threshold_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    options: HistoricalShortPriceThresholdGridOptions,
    competition_ids: tuple[str, ...],
    max_decimal_odds: float,
    min_probability: float,
    max_model_edge: float,
    strength: float,
) -> HistoricalShortPriceThresholdCandidate:
    candidate_options = options.backtest_options.model_copy(
        update={
            "short_price_negative_edge_guardrail": False,
            "short_price_negative_edge_max_decimal_odds": max_decimal_odds,
            "short_price_negative_edge_min_probability": min_probability,
            "short_price_negative_edge_max_model_edge": max_model_edge,
            "short_price_negative_edge_soft_penalty": True,
            "short_price_negative_edge_soft_penalty_strength": strength,
            "short_price_negative_edge_soft_penalty_competition_ids": competition_ids,
        }
    )
    suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=candidate_options,
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    deltas = _suite_deltas(baseline_suite, suite)
    objective_metric_codes = _objective_improvement_metric_codes(
        deltas,
        options=options,
    )
    objective_improvement_satisfied = (
        not options.require_objective_improvement or bool(objective_metric_codes)
    )
    reason_codes = _rejection_reason_codes(
        suite,
        deltas=deltas,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=options,
    )
    status: HistoricalShortPriceThresholdCandidateStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_price_threshold_candidate_v3_1",
        "status": status,
        "competition_ids": list(competition_ids),
        "max_decimal_odds": max_decimal_odds,
        "min_probability": min_probability,
        "max_model_edge": max_model_edge,
        "strength": strength,
        "comparison_epsilon": options.comparison_epsilon,
        "require_objective_improvement": options.require_objective_improvement,
        "min_objective_roi_delta": options.min_objective_roi_delta,
        "min_objective_upset_capture_rate_delta": (
            options.min_objective_upset_capture_rate_delta
        ),
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "penalized_candidate_count": _summary_int(
            suite.summary_json,
            "candidate_short_price_negative_edge_soft_penalty_candidate_count",
        ),
        "deltas": deltas,
        "reason_codes": reason_codes,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalShortPriceThresholdCandidate(
        candidate_key=candidate_key,
        status=status,
        competition_ids=competition_ids,
        max_decimal_odds=max_decimal_odds,
        min_probability=min_probability,
        max_model_edge=max_model_edge,
        strength=strength,
        suite_key=suite.suite_key,
        suite_status=suite.status,
        penalized_candidate_count=_summary_int(
            suite.summary_json,
            "candidate_short_price_negative_edge_soft_penalty_candidate_count",
        ),
        final_hit_sample_size=_summary_int(
            suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        final_hit_count=_summary_int(suite.summary_json, "candidate_final_hit_count"),
        final_hit_rate=_summary_number(suite.summary_json, "candidate_final_hit_rate"),
        roi=_summary_number(suite.summary_json, "candidate_roi"),
        profit_loss=_summary_number(suite.summary_json, "candidate_profit_loss") or 0.0,
        brier_score=_summary_number(suite.summary_json, "candidate_brier_score"),
        log_loss=_summary_number(suite.summary_json, "candidate_log_loss"),
        mean_calibration_error=_summary_number(
            suite.summary_json,
            "candidate_mean_calibration_error",
        ),
        upset_capture_rate=_summary_number(
            suite.summary_json,
            "candidate_upset_capture_rate",
        ),
        final_answer_changed_count=_summary_int(
            suite.summary_json,
            "final_answer_changed_count",
        ),
        objective_improvement_satisfied=objective_improvement_satisfied,
        objective_improvement_metric_codes=objective_metric_codes,
        deltas_json=deltas,
        reason_codes=reason_codes,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _suite_deltas(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> dict[str, object]:
    return {
        "final_hit_count_delta": _summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_count",
        )
        - _summary_int(baseline_suite.summary_json, "candidate_final_hit_count"),
        "final_hit_rate_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_final_hit_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_final_hit_rate"),
        ),
        "roi_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_roi"),
            _summary_number(baseline_suite.summary_json, "candidate_roi"),
        ),
        "profit_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_profit_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_profit_loss"),
        ),
        "brier_score_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_brier_score"),
            _summary_number(baseline_suite.summary_json, "candidate_brier_score"),
        ),
        "log_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_log_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_log_loss"),
        ),
        "mean_calibration_error_delta": _optional_delta(
            _summary_number(
                candidate_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
            _summary_number(
                baseline_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
        ),
        "upset_capture_rate_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_upset_capture_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_upset_capture_rate"),
        ),
        "penalized_candidate_count": _summary_int(
            candidate_suite.summary_json,
            "candidate_short_price_negative_edge_soft_penalty_candidate_count",
        ),
    }


def _rejection_reason_codes(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    deltas: Mapping[str, object],
    objective_improvement_satisfied: bool,
    options: HistoricalShortPriceThresholdGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if suite.status in options.fail_on_suite_statuses:
        reason_codes.append(f"threshold_grid:suite_status_{suite.status}")
    if _delta_int(deltas, "penalized_candidate_count") < options.min_penalized_candidate_count:
        reason_codes.append("threshold_grid:penalized_candidate_count_too_low")
    if _delta_int(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append("threshold_grid:final_hit_count_regressed")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="threshold_grid:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="threshold_grid:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="threshold_grid:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="threshold_grid:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="threshold_grid:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code="threshold_grid:mean_calibration_error_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="upset_capture_rate_delta",
        threshold=options.min_upset_capture_rate_delta,
        reason_code="threshold_grid:upset_capture_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    if not objective_improvement_satisfied:
        reason_codes.append("threshold_grid:objective_improvement_missing")
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalShortPriceThresholdGridOptions,
) -> list[str]:
    metric_codes: list[str] = []
    if _minimum_delta_exceeded(
        deltas,
        key="roi_delta",
        threshold=options.min_objective_roi_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("roi_delta")
    if _minimum_delta_exceeded(
        deltas,
        key="upset_capture_rate_delta",
        threshold=options.min_objective_upset_capture_rate_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("upset_capture_rate_delta")
    return metric_codes


def _minimum_delta_exceeded(
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    epsilon: float,
) -> bool:
    value = _delta_number(deltas, key)
    if value is None:
        return False
    return value > threshold + epsilon


def _append_minimum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _delta_number(deltas, key)
    if value is None or value + epsilon < threshold:
        reason_codes.append(reason_code)


def _append_maximum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _delta_number(deltas, key)
    if value is None or value - epsilon > threshold:
        reason_codes.append(reason_code)


def _best_candidate(
    candidates: Sequence[HistoricalShortPriceThresholdCandidate],
) -> HistoricalShortPriceThresholdCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalShortPriceThresholdCandidate,
) -> tuple[int, float, float, float, float, int, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _delta_number(candidate.deltas_json, "roi_delta") or -999.0,
        _delta_number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        _delta_number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        -(_delta_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        candidate.penalized_candidate_count,
        candidate.candidate_key,
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Search short-price favorite negative-edge soft-penalty thresholds."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_HISTORICAL_BACKTEST_MODES))
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--baseline-optimizer-profile",
        choices=["heuristic", "solver"],
        default="heuristic",
    )
    parser.add_argument(
        "--candidate-optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--competition-group", action="append", default=[])
    parser.add_argument("--max-decimal-odds-values", default="1.35")
    parser.add_argument("--min-probability-values", default="0.70")
    parser.add_argument("--max-model-edge-values", default="0.0")
    parser.add_argument("--strength-values", default="1.0")
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-penalized-candidate-count", type=int, default=1)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
        help=(
            "Require at least one promotion objective to improve, currently ROI "
            "or upset capture rate."
        ),
    )
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortPriceThresholdGridOptions:
    return HistoricalShortPriceThresholdGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        competition_groups=_competition_groups_from_args(args.competition_group),
        max_decimal_odds_values=_float_tuple(args.max_decimal_odds_values),
        min_probability_values=_float_tuple(args.min_probability_values),
        max_model_edge_values=_float_tuple(args.max_model_edge_values),
        strength_values=_float_tuple(args.strength_values),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
        min_penalized_candidate_count=args.min_penalized_candidate_count,
        min_final_hit_count_delta=args.min_final_hit_count_delta,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        min_upset_capture_rate_delta=args.min_upset_capture_rate_delta,
        require_objective_improvement=args.require_objective_improvement,
        min_objective_roi_delta=args.min_objective_roi_delta,
        min_objective_upset_capture_rate_delta=(
            args.min_objective_upset_capture_rate_delta
        ),
        comparison_epsilon=args.comparison_epsilon,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    return _LoadedHistoricalSlices(
        slices=[*bundle.slices, *explicit_slices],
        resolved_slice_paths=[*bundle.resolved_slice_paths, *args.slice_paths],
        manifest_result=bundle,
        warnings=bundle.warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _competition_groups_from_args(values: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    if not values:
        return ((),)
    return tuple(tuple(_csv(value)) for value in values)


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary_number(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None and baseline is None:
        return 0.0
    if value is None or baseline is None:
        return None
    return value - baseline


def _delta_number(deltas: Mapping[str, object], key: str) -> float | None:
    value = deltas.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _delta_int(deltas: Mapping[str, object], key: str) -> int:
    value = deltas.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_short_price_threshold_candidate:{digest}"


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "slice_ids": [
                    historical_slice.metadata.slice_id
                    for historical_slice in historical_slices
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_price_threshold_grid:{digest}"
