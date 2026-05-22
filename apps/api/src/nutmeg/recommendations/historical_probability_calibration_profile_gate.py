from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_probability_calibration_transform import (
    HistoricalProbabilityCalibrationTransformBucket,
    HistoricalProbabilityCalibrationTransformOptions,
    HistoricalProbabilityCalibrationTransformReport,
    _calibrated_probabilities,
    _calibration_buckets,
    build_historical_probability_calibration_transform_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
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
from nutmeg.recommendations.models import RecommendationMode

type HistoricalProbabilityCalibrationProfileGateStatus = Literal["generated"]

DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID = (
    "probability-calibration-profile-gate-shadow-v3.1"
)
ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")


class HistoricalProbabilityCalibrationProfileGateOptions(BaseModel):
    gate_id: str = DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID
    competition_ids: tuple[str, ...] = ()
    require_transform_acceptance: bool = True
    target_outcomes: tuple[str, ...] = ()
    probability_min: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_max: float = Field(default=1.0, ge=0.0, le=1.0)
    min_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_decimal_odds: float | None = Field(default=None, gt=1.0)
    transform_options: HistoricalProbabilityCalibrationTransformOptions = Field(
        default_factory=HistoricalProbabilityCalibrationTransformOptions
    )
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions = Field(
        default_factory=HistoricalRecommendationSuiteQualityGateOptions
    )


class HistoricalProbabilityCalibrationProfileGateReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationProfileGateStatus
    gate_id: str
    transform_report_key: str
    selected_competition_ids: list[str] = Field(default_factory=list)
    rejected_competition_ids: list[str] = Field(default_factory=list)
    baseline_slice_count: int = Field(ge=0)
    adjusted_slice_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    baseline_backtest_cache_hit_count: int = Field(default=0, ge=0)
    baseline_backtest_cache_miss_count: int = Field(default=0, ge=0)
    suite: HistoricalRecommendationBacktestSuiteResult | None = None
    quality_gate: HistoricalRecommendationSuiteQualityGateResult | None = None
    passed_final_answer_gate: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass
class _BaselineBacktestCacheStats:
    hit_count: int = 0
    miss_count: int = 0


def build_historical_probability_calibration_profile_gate_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileGateOptions | None = None,
    transform_report: HistoricalProbabilityCalibrationTransformReport | None = None,
    baseline_backtest_cache: dict[str, HistoricalRecommendationBacktestResult]
    | None = None,
) -> HistoricalProbabilityCalibrationProfileGateReport:
    resolved_options = options or HistoricalProbabilityCalibrationProfileGateOptions()
    resolved_transform_report = (
        transform_report
        or build_historical_probability_calibration_transform_report(
            historical_slices,
            options=resolved_options.transform_options,
        )
    )
    selected_competition_ids = _selected_competition_ids(
        resolved_transform_report,
        options=resolved_options,
    )
    rejected_competition_ids = [
        result.competition_id
        for result in resolved_transform_report.competitions
        if result.competition_id not in selected_competition_ids
    ]
    baseline_slices, adjusted_slices, adjusted_count, skipped_count = (
        _profile_gate_slices(
            historical_slices,
            selected_competition_ids=selected_competition_ids,
            options=resolved_options,
            transform_report_key=resolved_transform_report.report_key,
        )
    )
    warnings = [*resolved_transform_report.warnings]
    if not selected_competition_ids:
        warnings.append(
            "historical_probability_calibration_profile_gate:no_selected_competitions"
        )
    suite: HistoricalRecommendationBacktestSuiteResult | None = None
    quality_gate: HistoricalRecommendationSuiteQualityGateResult | None = None
    passed_final_answer_gate = False
    baseline_cache_stats = _BaselineBacktestCacheStats()
    if baseline_slices and adjusted_slices:
        suite = _profile_gate_suite(
            baseline_slices,
            adjusted_slices=adjusted_slices,
            selected_competition_ids=selected_competition_ids,
            adjusted_fixture_count=adjusted_count,
            skipped_fixture_count=skipped_count,
            options=resolved_options,
            baseline_backtest_cache=baseline_backtest_cache,
            baseline_cache_stats=baseline_cache_stats,
        )
        quality_gate = run_historical_recommendation_suite_quality_gate(
            suite,
            options=resolved_options.quality_gate_options,
        )
        passed_final_answer_gate = quality_gate.passed
        warnings.extend(quality_gate.warnings)
    report_key = _report_key(
        historical_slices,
        transform_report=resolved_transform_report,
        options=resolved_options,
        selected_competition_ids=selected_competition_ids,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_profile_gate_v3_1",
        "report_key": report_key,
        "gate_id": resolved_options.gate_id,
        "shadow_only": True,
        "transform_report_key": resolved_transform_report.report_key,
        "selected_competition_ids": selected_competition_ids,
        "rejected_competition_ids": rejected_competition_ids,
        "target_outcomes": list(resolved_options.target_outcomes),
        "probability_min": resolved_options.probability_min,
        "probability_max": resolved_options.probability_max,
        "min_decimal_odds": resolved_options.min_decimal_odds,
        "max_decimal_odds": resolved_options.max_decimal_odds,
        "segment_mode": resolved_options.transform_options.segment_mode,
        "final_answer_scenario_variant_count": (
            resolved_options.backtest_options.final_answer_scenario_variant_count
        ),
        "baseline_slice_count": len(baseline_slices),
        "adjusted_slice_count": len(adjusted_slices),
        "adjusted_fixture_count": adjusted_count,
        "skipped_fixture_count": skipped_count,
        "baseline_backtest_cache_hit_count": baseline_cache_stats.hit_count,
        "baseline_backtest_cache_miss_count": baseline_cache_stats.miss_count,
        "suite_key": suite.suite_key if suite is not None else None,
        "suite_status": suite.status if suite is not None else None,
        "quality_gate_key": quality_gate.gate_key if quality_gate is not None else None,
        "quality_gate_passed": quality_gate.passed if quality_gate is not None else False,
        "passed_final_answer_gate": passed_final_answer_gate,
        "aggregate_deltas_json": (
            suite.aggregate_deltas_json if suite is not None else {}
        ),
        "transform_competition_decisions": {
            result.competition_id: result.decision
            for result in resolved_transform_report.competitions
        },
        "warnings": warnings,
    }
    return HistoricalProbabilityCalibrationProfileGateReport(
        report_key=report_key,
        status="generated",
        gate_id=resolved_options.gate_id,
        transform_report_key=resolved_transform_report.report_key,
        selected_competition_ids=selected_competition_ids,
        rejected_competition_ids=rejected_competition_ids,
        baseline_slice_count=len(baseline_slices),
        adjusted_slice_count=len(adjusted_slices),
        adjusted_fixture_count=adjusted_count,
        skipped_fixture_count=skipped_count,
        baseline_backtest_cache_hit_count=baseline_cache_stats.hit_count,
        baseline_backtest_cache_miss_count=baseline_cache_stats.miss_count,
        suite=suite,
        quality_gate=quality_gate,
        passed_final_answer_gate=passed_final_answer_gate,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_gate_report(
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
            _stdout_payload(report, summary_only=args.stdout_summary_only),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not report.passed_final_answer_gate and not args.no_fail_process:
        raise SystemExit(1)


def _stdout_payload(
    report: HistoricalProbabilityCalibrationProfileGateReport,
    *,
    summary_only: bool,
) -> dict[str, object]:
    if not summary_only:
        return report.model_dump(mode="json")
    summary = dict(report.summary_json)
    summary.pop("suite_manifest", None)
    quality_gate = report.quality_gate
    suite = report.suite
    return {
        "report_key": report.report_key,
        "status": report.status,
        "gate_id": report.gate_id,
        "transform_report_key": report.transform_report_key,
        "selected_competition_ids": report.selected_competition_ids,
        "rejected_competition_ids": report.rejected_competition_ids,
        "baseline_slice_count": report.baseline_slice_count,
        "adjusted_slice_count": report.adjusted_slice_count,
        "adjusted_fixture_count": report.adjusted_fixture_count,
        "skipped_fixture_count": report.skipped_fixture_count,
        "baseline_backtest_cache_hit_count": (
            report.baseline_backtest_cache_hit_count
        ),
        "baseline_backtest_cache_miss_count": (
            report.baseline_backtest_cache_miss_count
        ),
        "passed_final_answer_gate": report.passed_final_answer_gate,
        "suite": (
            {
                "suite_key": suite.suite_key,
                "status": suite.status,
                "aggregate_deltas_json": suite.aggregate_deltas_json,
                "summary_json": _compact_suite_summary(suite.summary_json),
            }
            if suite is not None
            else None
        ),
        "quality_gate": (
            {
                "gate_key": quality_gate.gate_key,
                "status": quality_gate.status,
                "passed": quality_gate.passed,
                "suite_status": quality_gate.suite_status,
                "failed_checks": [
                    check.name
                    for check in quality_gate.checks
                    if check.status == "failed"
                ],
            }
            if quality_gate is not None
            else None
        ),
        "summary_json": summary,
        "warnings": report.warnings,
    }


def _compact_suite_summary(summary_json: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "comparison_count",
        "slice_count",
        "status",
        "baseline_final_hit_rate",
        "candidate_final_hit_rate",
        "baseline_roi",
        "candidate_roi",
        "baseline_profit_loss",
        "candidate_profit_loss",
        "baseline_brier_score",
        "candidate_brier_score",
        "baseline_log_loss",
        "candidate_log_loss",
        "baseline_mean_calibration_error",
        "candidate_mean_calibration_error",
        "final_answer_changed_count",
        "candidate_solver_selected_scenario_count",
        "baseline_completed_scenario_variant_count",
        "candidate_completed_scenario_variant_count",
    )
    return {key: summary_json[key] for key in keys if key in summary_json}


def _selected_competition_ids(
    transform_report: HistoricalProbabilityCalibrationTransformReport,
    *,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> list[str]:
    requested_competitions = set(options.competition_ids)
    selected: list[str] = []
    for result in transform_report.competitions:
        if requested_competitions and result.competition_id not in requested_competitions:
            continue
        if options.require_transform_acceptance and result.decision != "accepted":
            continue
        selected.append(result.competition_id)
    return sorted(selected)


def _profile_gate_slices(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    selected_competition_ids: Sequence[str],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    transform_report_key: str,
) -> tuple[list[HistoricalRecommendationSlice], list[HistoricalRecommendationSlice], int, int]:
    selected_competitions = set(selected_competition_ids)
    baseline_slices: list[HistoricalRecommendationSlice] = []
    adjusted_slices: list[HistoricalRecommendationSlice] = []
    adjusted_count = 0
    skipped_count = 0
    for competition_id, competition_slices in sorted(
        _slices_by_competition(historical_slices).items()
    ):
        if competition_id not in selected_competitions:
            continue
        sorted_slices = sorted(competition_slices, key=_slice_sort_key)
        training_slices, validation_slices = _split_by_holdout_seasons(
            sorted_slices,
            holdout_season_count=options.transform_options.holdout_season_count,
        )
        if (
            _training_season_count(training_slices)
            < options.transform_options.min_training_season_count
        ):
            continue
        calibration_buckets = _calibration_buckets(
            training_slices,
            options=options.transform_options,
        )
        for historical_slice in validation_slices:
            adjusted_slice, slice_adjusted_count, slice_skipped_count = _adjusted_slice(
                historical_slice,
                calibration_buckets=calibration_buckets,
                options=options,
                transform_report_key=transform_report_key,
            )
            baseline_slices.append(historical_slice)
            adjusted_slices.append(adjusted_slice)
            adjusted_count += slice_adjusted_count
            skipped_count += slice_skipped_count
    return baseline_slices, adjusted_slices, adjusted_count, skipped_count


def _adjusted_slice(
    historical_slice: HistoricalRecommendationSlice,
    *,
    calibration_buckets: Mapping[str, HistoricalProbabilityCalibrationTransformBucket],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    transform_report_key: str,
) -> tuple[HistoricalRecommendationSlice, int, int]:
    adjusted_fixtures: list[HistoricalFixture] = []
    adjusted_count = 0
    skipped_count = 0
    for fixture in historical_slice.fixtures:
        baseline_probabilities = _one_x_two_probabilities(fixture)
        if baseline_probabilities is None:
            adjusted_fixtures.append(fixture)
            skipped_count += 1
            continue
        transformed = _calibrated_probabilities(
            fixture,
            baseline_probabilities,
            calibration_buckets=calibration_buckets,
            options=options.transform_options,
        )
        if transformed is None:
            adjusted_fixtures.append(fixture)
            skipped_count += 1
            continue
        (
            candidate_probabilities,
            applied_bucket_keys,
            fallback_reasons,
            _applied_segment_probabilities,
        ) = transformed
        filtered_probabilities, adjusted_outcomes = _profile_filtered_probabilities(
            fixture,
            baseline_probabilities=baseline_probabilities,
            candidate_probabilities=candidate_probabilities,
            options=options,
        )
        adjusted_fixtures.append(
            _adjusted_fixture(
                fixture,
                candidate_probabilities=filtered_probabilities,
                adjusted_outcomes=adjusted_outcomes,
                applied_bucket_keys=applied_bucket_keys,
                fallback_reasons=fallback_reasons,
                options=options,
                transform_report_key=transform_report_key,
            )
        )
        if adjusted_outcomes:
            adjusted_count += 1
    return (
        historical_slice.model_copy(
            update={
                "metadata": historical_slice.metadata.model_copy(
                    update={
                        "slice_id": _adjusted_slice_id(
                            historical_slice.metadata.slice_id,
                            options=options,
                        ),
                        "notes": [
                            *historical_slice.metadata.notes,
                            (
                                "Shadow-only probability calibration profile "
                                "adjustment for final-answer gate evaluation."
                            ),
                        ],
                    }
                ),
                "fixtures": adjusted_fixtures,
            }
        ),
        adjusted_count,
        skipped_count,
    )


def _adjusted_fixture(
    fixture: HistoricalFixture,
    *,
    candidate_probabilities: dict[str, float],
    adjusted_outcomes: set[str],
    applied_bucket_keys: dict[str, str | None],
    fallback_reasons: Sequence[str],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    transform_report_key: str,
) -> HistoricalFixture:
    return fixture.model_copy(
        update={
            "calibration_version": (
                f"{fixture.calibration_version or 'uncalibrated'}"
                "+probability-calibration-profile-shadow"
            ),
            "predictions": [
                _adjusted_prediction(
                    prediction,
                    candidate_probabilities=candidate_probabilities,
                    adjusted_outcomes=adjusted_outcomes,
                    applied_bucket_keys=applied_bucket_keys,
                    fallback_reasons=fallback_reasons,
                    options=options,
                    transform_report_key=transform_report_key,
                )
                for prediction in fixture.predictions
            ],
        }
    )


def _adjusted_prediction(
    prediction: HistoricalMarketPrediction,
    *,
    candidate_probabilities: dict[str, float],
    adjusted_outcomes: set[str],
    applied_bucket_keys: dict[str, str | None],
    fallback_reasons: Sequence[str],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    transform_report_key: str,
) -> HistoricalMarketPrediction:
    if (
        prediction.market_type != "1x2"
        or prediction.outcome not in candidate_probabilities
        or prediction.outcome not in adjusted_outcomes
    ):
        return prediction
    adjusted_probability = candidate_probabilities[prediction.outcome]
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
                "probability_calibration_profile_shadow_adjusted": True,
                "probability_calibration_profile_gate_id": options.gate_id,
                "probability_calibration_profile_segment_mode": (
                    options.transform_options.segment_mode
                ),
                "probability_calibration_transform_report_key": transform_report_key,
                "probability_calibration_shadow_baseline_probability": (
                    prediction.probability
                ),
                "probability_calibration_shadow_probability": adjusted_probability,
                "probability_calibration_applied_bucket_key": applied_bucket_keys.get(
                    prediction.outcome
                ),
                "probability_calibration_fallback_reasons": list(fallback_reasons),
                "probability_calibration_profile_target_outcomes": (
                    list(options.target_outcomes)
                ),
                "probability_calibration_profile_probability_min": (
                    options.probability_min
                ),
                "probability_calibration_profile_probability_max": (
                    options.probability_max
                ),
                "probability_calibration_profile_min_decimal_odds": (
                    options.min_decimal_odds
                ),
                "probability_calibration_profile_max_decimal_odds": (
                    options.max_decimal_odds
                ),
                "shadow_only": True,
            },
        }
    )


def _profile_filtered_probabilities(
    fixture: HistoricalFixture,
    *,
    baseline_probabilities: dict[str, float],
    candidate_probabilities: dict[str, float],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> tuple[dict[str, float], set[str]]:
    adjusted_probabilities = dict(baseline_probabilities)
    adjusted_outcomes: set[str] = set()
    for prediction in fixture.predictions:
        if prediction.market_type != "1x2" or prediction.outcome not in ONE_X_TWO_OUTCOMES:
            continue
        if not _prediction_matches_profile(prediction, options=options):
            continue
        adjusted_probabilities[prediction.outcome] = candidate_probabilities[
            prediction.outcome
        ]
        adjusted_outcomes.add(prediction.outcome)
    normalized_probabilities = _normalize_probabilities(adjusted_probabilities)
    return normalized_probabilities or baseline_probabilities, adjusted_outcomes


def _prediction_matches_profile(
    prediction: HistoricalMarketPrediction,
    *,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> bool:
    if options.target_outcomes and prediction.outcome not in set(options.target_outcomes):
        return False
    if prediction.probability < options.probability_min:
        return False
    if prediction.probability > options.probability_max:
        return False
    if (
        options.min_decimal_odds is not None
        and prediction.decimal_odds < options.min_decimal_odds
    ):
        return False
    return not (
        options.max_decimal_odds is not None
        and prediction.decimal_odds > options.max_decimal_odds
    )


def _profile_gate_suite(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    *,
    adjusted_slices: Sequence[HistoricalRecommendationSlice],
    selected_competition_ids: Sequence[str],
    adjusted_fixture_count: int,
    skipped_fixture_count: int,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    baseline_backtest_cache: dict[str, HistoricalRecommendationBacktestResult] | None,
    baseline_cache_stats: _BaselineBacktestCacheStats,
) -> HistoricalRecommendationBacktestSuiteResult:
    comparisons: list[HistoricalRecommendationBacktestComparisonResult] = []
    for baseline_slice, adjusted_slice in zip(baseline_slices, adjusted_slices, strict=True):
        baseline = _baseline_backtest_result(
            baseline_slice,
            options=options.backtest_options,
            cache=baseline_backtest_cache,
            stats=baseline_cache_stats,
        )
        candidate = run_historical_recommendation_backtest(
            adjusted_slice,
            options=options.backtest_options,
        )
        comparisons.append(
            _profile_gate_comparison(
                baseline_slice,
                baseline=baseline,
                candidate=candidate,
                options=options,
            )
        )
    aggregate_deltas = _suite_aggregate_deltas(comparisons)
    status = (
        _comparison_status(aggregate_deltas)
        if comparisons
        else "insufficient_samples"
    )
    summary = _suite_summary_json(
        baseline_slices,
        comparisons=comparisons,
        aggregate_deltas=aggregate_deltas,
        status=status,
        baseline_optimizer_profile=options.backtest_options.optimizer_profile,
        candidate_optimizer_profile=options.backtest_options.optimizer_profile,
    )
    summary.update(
        {
            "calculation_basis": (
                "historical_probability_calibration_profile_gate_suite_v3_1"
            ),
            "gate_id": options.gate_id,
            "selected_competition_ids": list(selected_competition_ids),
            "adjusted_fixture_count": adjusted_fixture_count,
            "skipped_fixture_count": skipped_fixture_count,
            "baseline_backtest_cache_hit_count": baseline_cache_stats.hit_count,
            "baseline_backtest_cache_miss_count": baseline_cache_stats.miss_count,
            "shadow_only": True,
        }
    )
    warnings = [
        f"historical_probability_calibration_profile_gate:suite_status:{status}"
    ] if status in {"mixed", "regressed", "insufficient_samples"} else []
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=_suite_key(
            baseline_slices,
            adjusted_slices=adjusted_slices,
            selected_competition_ids=selected_competition_ids,
            options=options,
        ),
        status=status,
        slice_count=len(baseline_slices),
        comparison_count=len(comparisons),
        baseline_optimizer_profile=options.backtest_options.optimizer_profile,
        candidate_optimizer_profile=options.backtest_options.optimizer_profile,
        comparisons=comparisons,
        aggregate_deltas_json=aggregate_deltas,
        warnings=warnings,
        summary_json=summary,
    )


def _baseline_backtest_result(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
    cache: dict[str, HistoricalRecommendationBacktestResult] | None,
    stats: _BaselineBacktestCacheStats,
) -> HistoricalRecommendationBacktestResult:
    if cache is None:
        return run_historical_recommendation_backtest(
            historical_slice,
            options=options,
        )
    cache_key = _baseline_backtest_cache_key(historical_slice, options=options)
    cached = cache.get(cache_key)
    if cached is not None:
        stats.hit_count += 1
        return cached
    result = run_historical_recommendation_backtest(
        historical_slice,
        options=options,
    )
    cache[cache_key] = result
    stats.miss_count += 1
    return result


def _profile_gate_comparison(
    historical_slice: HistoricalRecommendationSlice,
    *,
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> HistoricalRecommendationBacktestComparisonResult:
    deltas = _comparison_deltas(baseline, candidate)
    status = _comparison_status(deltas)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_gate_comparison_v3_1"
        ),
        "slice_id": historical_slice.metadata.slice_id,
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
        comparison_key=_comparison_key(
            historical_slice,
            options=options,
        ),
        slice_id=historical_slice.metadata.slice_id,
        baseline_optimizer_profile=options.backtest_options.optimizer_profile,
        candidate_optimizer_profile=options.backtest_options.optimizer_profile,
        status=status,
        baseline=baseline,
        candidate=candidate,
        deltas_json=deltas,
        summary_json=summary,
    )


def _one_x_two_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    probabilities: dict[str, float] = {}
    for prediction in fixture.predictions:
        if prediction.market_type == "1x2" and prediction.outcome in ONE_X_TWO_OUTCOMES:
            probabilities[prediction.outcome] = prediction.probability
    if set(probabilities) != set(ONE_X_TWO_OUTCOMES):
        return None
    return _normalize_probabilities(probabilities)


def _normalize_probabilities(probabilities: dict[str, float]) -> dict[str, float] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {outcome: probabilities[outcome] / total for outcome in ONE_X_TWO_OUTCOMES}


def _slices_by_competition(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    return grouped


def _slice_sort_key(historical_slice: HistoricalRecommendationSlice) -> tuple[str, str]:
    return (
        historical_slice.metadata.season or "",
        historical_slice.metadata.slice_id,
    )


def _split_by_holdout_seasons(
    sorted_slices: Sequence[HistoricalRecommendationSlice],
    *,
    holdout_season_count: int,
) -> tuple[list[HistoricalRecommendationSlice], list[HistoricalRecommendationSlice]]:
    if not sorted_slices:
        return [], []
    season_order: list[str] = []
    for historical_slice in sorted_slices:
        season = _slice_season(historical_slice)
        if season not in season_order:
            season_order.append(season)
    if len(season_order) == 1 and season_order[0] == "unknown":
        holdout_count = min(holdout_season_count, len(sorted_slices))
        return list(sorted_slices[:-holdout_count]), list(sorted_slices[-holdout_count:])
    holdout_seasons = set(season_order[-holdout_season_count:])
    training_slices = [
        historical_slice
        for historical_slice in sorted_slices
        if _slice_season(historical_slice) not in holdout_seasons
    ]
    validation_slices = [
        historical_slice
        for historical_slice in sorted_slices
        if _slice_season(historical_slice) in holdout_seasons
    ]
    return training_slices, validation_slices


def _training_season_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    seasons: list[str] = []
    for historical_slice in slices:
        season = _slice_season(historical_slice)
        if season not in seasons:
            seasons.append(season)
    if seasons == ["unknown"]:
        return len(slices)
    return len(seasons)


def _slice_season(historical_slice: HistoricalRecommendationSlice) -> str:
    return historical_slice.metadata.season or "unknown"


def _scenario_key(value: object) -> str | None:
    scenario = getattr(value, "scenario", None)
    scenario_key = getattr(scenario, "scenario_key", None)
    return str(scenario_key) if scenario_key is not None else None


def _baseline_backtest_cache_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalRecommendationBacktestOptions,
) -> str:
    payload = {
        "calculation_basis": (
            "historical_probability_calibration_profile_gate_baseline_backtest_cache_v3_1"
        ),
        "slice_id": historical_slice.metadata.slice_id,
        "as_of_time_utc": historical_slice.as_of_time_utc.isoformat(),
        "backtest_options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_gate_baseline_backtest:{digest}"


def _adjusted_slice_id(
    slice_id: str,
    *,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> str:
    digest = sha256(
        dumps(
            {
                "slice_id": slice_id,
                "gate_id": options.gate_id,
                "transform_options": options.transform_options.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:8]
    return f"{slice_id}__probability_calibration_profile_shadow_{digest}"


def _comparison_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> str:
    payload = {
        "slice_id": historical_slice.metadata.slice_id,
        "gate_id": options.gate_id,
        "backtest_options": options.backtest_options.model_dump(mode="json"),
        "transform_options": options.transform_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_gate_comparison:{digest}"


def _suite_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    adjusted_slices: Sequence[HistoricalRecommendationSlice],
    selected_competition_ids: Sequence[str],
    options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> str:
    payload = {
        "slice_ids": [item.metadata.slice_id for item in historical_slices],
        "adjusted_slice_ids": [item.metadata.slice_id for item in adjusted_slices],
        "selected_competition_ids": list(selected_competition_ids),
        "gate_id": options.gate_id,
        "backtest_options": options.backtest_options.model_dump(mode="json"),
        "transform_options": options.transform_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_gate_suite:{digest}"


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    transform_report: HistoricalProbabilityCalibrationTransformReport,
    options: HistoricalProbabilityCalibrationProfileGateOptions,
    selected_competition_ids: Sequence[str],
) -> str:
    payload = {
        "slice_ids": [item.metadata.slice_id for item in historical_slices],
        "transform_report_key": transform_report.report_key,
        "selected_competition_ids": list(selected_competition_ids),
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_gate:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run accepted per-competition probability calibration profiles through "
            "a shadow final-answer gate."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--gate-id", default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID)
    parser.add_argument("--competition-ids", default="")
    parser.add_argument("--include-rejected-transform-competitions", action="store_true")
    parser.add_argument("--target-outcomes", default="")
    parser.add_argument("--probability-min", type=float, default=0.0)
    parser.add_argument("--probability-max", type=float, default=1.0)
    parser.add_argument("--min-decimal-odds", type=float)
    parser.add_argument("--max-decimal-odds", type=float)
    parser.add_argument("--holdout-season-count", type=int, default=1)
    parser.add_argument("--min-training-season-count", type=int, default=2)
    parser.add_argument("--min-validation-sample-size", type=int, default=100)
    parser.add_argument(
        "--segment-mode",
        choices=["probability_bucket", "market_odds_band"],
        default="probability_bucket",
    )
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=30)
    parser.add_argument("--blend-weight", type=float, default=1.0)
    parser.add_argument("--min-calibrated-probability", type=float, default=0.01)
    parser.add_argument("--max-calibrated-probability", type=float, default=0.95)
    parser.add_argument("--group-all-competitions", action="store_true")
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"], default="solver")
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float)
    parser.add_argument("--min-profit-loss-delta", type=float)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument(
        "--stdout-summary-only",
        action="store_true",
        help=(
            "Print a compact report summary to stdout while keeping --output-path "
            "as the full report artifact."
        ),
    )
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalProbabilityCalibrationProfileGateOptions:
    return HistoricalProbabilityCalibrationProfileGateOptions(
        gate_id=args.gate_id,
        competition_ids=_split_csv(args.competition_ids),
        require_transform_acceptance=not args.include_rejected_transform_competitions,
        target_outcomes=_split_csv(args.target_outcomes),
        probability_min=args.probability_min,
        probability_max=args.probability_max,
        min_decimal_odds=args.min_decimal_odds,
        max_decimal_odds=args.max_decimal_odds,
        transform_options=HistoricalProbabilityCalibrationTransformOptions(
            holdout_season_count=args.holdout_season_count,
            min_training_season_count=args.min_training_season_count,
            min_validation_sample_size=args.min_validation_sample_size,
            segment_mode=args.segment_mode,
            bucket_size=args.bucket_size,
            min_bucket_sample_size=args.min_bucket_sample_size,
            blend_weight=args.blend_weight,
            min_calibrated_probability=args.min_calibrated_probability,
            max_calibrated_probability=args.max_calibrated_probability,
            group_by_competition=not args.group_all_competitions,
            prediction_sample_limit=0,
        ),
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=_split_csv(args.pass_types),
            modes=cast(tuple[RecommendationMode, ...], _split_csv(args.modes)),
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            final_answer_scenario_variant_count=(
                args.final_answer_scenario_variant_count
            ),
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=args.min_final_hit_sample_size,
            min_final_hit_rate_delta=args.min_final_hit_rate_delta,
            min_final_answer_changed_count=args.min_final_answer_changed_count,
            min_roi_delta=args.min_roi_delta,
            min_profit_loss_delta=args.min_profit_loss_delta,
            max_brier_score_delta=args.max_brier_score_delta,
            max_log_loss_delta=args.max_log_loss_delta,
            max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
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


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())
