from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_ablation import (
    HistoricalPrematchFeatureAblationOptions,
    HistoricalPrematchFeatureAblationReport,
    build_historical_prematch_feature_ablation_report,
)
from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridCandidate,
    HistoricalPrematchFeatureAblationGridOptions,
    HistoricalPrematchFeatureAblationGridReport,
    build_historical_prematch_feature_ablation_grid_report,
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

type HistoricalPrematchFeatureFinalAnswerGateStatus = Literal["generated"]

DEFAULT_PREMATCH_FEATURE_FINAL_ANSWER_GATE_ID = (
    "prematch-feature-final-answer-gate-shadow-v3.1"
)


class HistoricalPrematchFeatureFinalAnswerGateOptions(BaseModel):
    gate_id: str = DEFAULT_PREMATCH_FEATURE_FINAL_ANSWER_GATE_ID
    top_candidate_limit: int = Field(default=5, ge=1, le=32)
    require_grid_non_regression_candidate: bool = True
    grid_options: HistoricalPrematchFeatureAblationGridOptions = Field(
        default_factory=HistoricalPrematchFeatureAblationGridOptions
    )
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions = Field(
        default_factory=HistoricalRecommendationSuiteQualityGateOptions
    )


class HistoricalPrematchFeatureFinalAnswerCandidateEvaluation(BaseModel):
    rank: int = Field(ge=1)
    feature_grid_candidate_id: str
    feature_grid_rank: int = Field(ge=1)
    feature_ablation_report_key: str
    passed_grid_non_regression_gate: bool
    adjusted_fixture_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    suite: HistoricalRecommendationBacktestSuiteResult
    quality_gate: HistoricalRecommendationSuiteQualityGateResult
    passed_final_answer_gate: bool
    deltas_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureFinalAnswerGateReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureFinalAnswerGateStatus
    gate_id: str
    grid_report_key: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    grid_candidate_count: int = Field(ge=0)
    evaluated_candidate_count: int = Field(ge=0)
    passing_candidate_count: int = Field(ge=0)
    best_evaluation: HistoricalPrematchFeatureFinalAnswerCandidateEvaluation
    evaluations: list[HistoricalPrematchFeatureFinalAnswerCandidateEvaluation] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_final_answer_gate_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureFinalAnswerGateOptions | None = None,
    grid_report: HistoricalPrematchFeatureAblationGridReport | None = None,
) -> HistoricalPrematchFeatureFinalAnswerGateReport:
    resolved_options = options or HistoricalPrematchFeatureFinalAnswerGateOptions()
    resolved_grid_report = grid_report or build_historical_prematch_feature_ablation_grid_report(
        historical_slices,
        options=resolved_options.grid_options,
    )
    selected_grid_candidates = _selected_grid_candidates(
        resolved_grid_report,
        options=resolved_options,
    )
    if not selected_grid_candidates:
        raise ValueError("prematch feature final-answer gate found no grid candidates")

    evaluations = [
        _candidate_evaluation(
            candidate,
            historical_slices,
            options=resolved_options,
        )
        for candidate in selected_grid_candidates
    ]
    ranked_evaluations = [
        evaluation.model_copy(update={"rank": rank})
        for rank, evaluation in enumerate(
            sorted(evaluations, key=_evaluation_sort_key),
            start=1,
        )
    ]
    best_evaluation = ranked_evaluations[0]
    passing_candidate_count = sum(
        1 for evaluation in ranked_evaluations if evaluation.passed_final_answer_gate
    )
    warnings = _report_warnings(
        ranked_evaluations,
        historical_warnings=[],
    )
    report_key = _report_key(
        historical_slices,
        grid_report=resolved_grid_report,
        options=resolved_options,
        evaluated_candidates=ranked_evaluations,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_final_answer_gate_v3_1",
        "report_key": report_key,
        "gate_id": resolved_options.gate_id,
        "shadow_only": True,
        "grid_report_key": resolved_grid_report.report_key,
        "slice_count": len(historical_slices),
        "fixture_count": sum(len(item.fixtures) for item in historical_slices),
        "grid_candidate_count": resolved_grid_report.candidate_count,
        "evaluated_candidate_count": len(ranked_evaluations),
        "passing_candidate_count": passing_candidate_count,
        "best_feature_grid_candidate_id": best_evaluation.feature_grid_candidate_id,
        "best_feature_grid_rank": best_evaluation.feature_grid_rank,
        "best_passed_final_answer_gate": best_evaluation.passed_final_answer_gate,
        "best_suite_status": best_evaluation.suite.status,
        "best_deltas": best_evaluation.deltas_json,
        "best_quality_gate_key": best_evaluation.quality_gate.gate_key,
        "best_quality_gate_passed": best_evaluation.quality_gate.passed,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureFinalAnswerGateReport(
        report_key=report_key,
        status="generated",
        gate_id=resolved_options.gate_id,
        grid_report_key=resolved_grid_report.report_key,
        slice_count=len(historical_slices),
        fixture_count=sum(len(item.fixtures) for item in historical_slices),
        grid_candidate_count=resolved_grid_report.candidate_count,
        evaluated_candidate_count=len(ranked_evaluations),
        passing_candidate_count=passing_candidate_count,
        best_evaluation=best_evaluation,
        evaluations=ranked_evaluations,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    grid_report = _load_grid_report(args.grid_report_path)
    report = build_historical_prematch_feature_final_answer_gate_report(
        loaded_slices.slices,
        options=_options_from_args(args),
        grid_report=grid_report,
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
    if report.passing_candidate_count <= 0 and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_evaluation(
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureFinalAnswerGateOptions,
) -> HistoricalPrematchFeatureFinalAnswerCandidateEvaluation:
    ablation_options = _ablation_options_from_grid_candidate(
        grid_candidate,
        sample_limit=sum(len(item.fixtures) for item in historical_slices),
    )
    ablation_report = build_historical_prematch_feature_ablation_report(
        historical_slices,
        options=ablation_options,
    )
    adjusted_slices, adjusted_fixture_count = _adjusted_historical_slices(
        historical_slices,
        ablation_report=ablation_report,
        grid_candidate=grid_candidate,
    )
    suite = _feature_candidate_suite(
        historical_slices,
        adjusted_slices=adjusted_slices,
        grid_candidate=grid_candidate,
        adjusted_fixture_count=adjusted_fixture_count,
        backtest_options=options.backtest_options,
    )
    quality_gate = run_historical_recommendation_suite_quality_gate(
        suite,
        options=options.quality_gate_options,
    )
    summary: dict[str, object] = {
        "feature_grid_candidate_id": grid_candidate.candidate_id,
        "feature_grid_rank": grid_candidate.rank,
        "feature_ablation_report_key": ablation_report.report_key,
        "passed_grid_non_regression_gate": (
            grid_candidate.passed_non_regression_gate
        ),
        "adjusted_fixture_count": adjusted_fixture_count,
        "skipped_fixture_count": ablation_report.skipped_count,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "quality_gate_key": quality_gate.gate_key,
        "quality_gate_passed": quality_gate.passed,
        "deltas_json": suite.aggregate_deltas_json,
    }
    return HistoricalPrematchFeatureFinalAnswerCandidateEvaluation(
        rank=grid_candidate.rank,
        feature_grid_candidate_id=grid_candidate.candidate_id,
        feature_grid_rank=grid_candidate.rank,
        feature_ablation_report_key=ablation_report.report_key,
        passed_grid_non_regression_gate=grid_candidate.passed_non_regression_gate,
        adjusted_fixture_count=adjusted_fixture_count,
        skipped_fixture_count=ablation_report.skipped_count,
        suite=suite,
        quality_gate=quality_gate,
        passed_final_answer_gate=quality_gate.passed,
        deltas_json=suite.aggregate_deltas_json,
        summary_json=summary,
    )


def _feature_candidate_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    adjusted_slices: Sequence[HistoricalRecommendationSlice],
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    adjusted_fixture_count: int,
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
            _feature_candidate_comparison(
                baseline_slice,
                baseline=baseline,
                candidate=candidate,
                grid_candidate=grid_candidate,
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
            "calculation_basis": (
                "historical_prematch_feature_final_answer_gate_suite_v3_1"
            ),
            "feature_grid_candidate_id": grid_candidate.candidate_id,
            "feature_grid_rank": grid_candidate.rank,
            "feature_ablation_options": grid_candidate.options_json,
            "adjusted_fixture_count": adjusted_fixture_count,
            "shadow_only": True,
        }
    )
    warnings = _suite_warnings(comparisons=comparisons, status=status)
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=_feature_suite_key(
            historical_slices,
            grid_candidate=grid_candidate,
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


def _feature_candidate_comparison(
    historical_slice: HistoricalRecommendationSlice,
    *,
    baseline: HistoricalRecommendationBacktestResult,
    candidate: HistoricalRecommendationBacktestResult,
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestComparisonResult:
    deltas = _comparison_deltas(baseline, candidate)
    status = _comparison_status(deltas)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_final_answer_gate_comparison_v3_1"
        ),
        "slice_id": historical_slice.metadata.slice_id,
        "feature_grid_candidate_id": grid_candidate.candidate_id,
        "feature_grid_rank": grid_candidate.rank,
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
        comparison_key=_feature_comparison_key(
            historical_slice,
            grid_candidate=grid_candidate,
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


def _adjusted_historical_slices(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    ablation_report: HistoricalPrematchFeatureAblationReport,
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
) -> tuple[list[HistoricalRecommendationSlice], int]:
    sample_by_key = {
        (sample.slice_id, sample.fixture_id): sample
        for sample in ablation_report.sampled_predictions
    }
    adjusted_count = 0
    adjusted_slices: list[HistoricalRecommendationSlice] = []
    for historical_slice in historical_slices:
        adjusted_fixtures: list[HistoricalFixture] = []
        for fixture in historical_slice.fixtures:
            sample = sample_by_key.get((historical_slice.metadata.slice_id, fixture.fixture_id))
            if sample is None:
                adjusted_fixtures.append(fixture)
                continue
            adjusted_fixtures.append(
                _adjusted_fixture(
                    fixture,
                    candidate_probabilities=sample.candidate_probabilities,
                    grid_candidate=grid_candidate,
                    feature_ablation_report_key=ablation_report.report_key,
                )
            )
            adjusted_count += 1
        adjusted_slices.append(
            historical_slice.model_copy(
                update={
                    "metadata": historical_slice.metadata.model_copy(
                        update={
                            "slice_id": _adjusted_slice_id(
                                historical_slice.metadata.slice_id,
                                grid_candidate=grid_candidate,
                            ),
                            "notes": [
                                *historical_slice.metadata.notes,
                                (
                                    "Shadow-only prematch feature probability "
                                    "adjustment for final-answer gate evaluation."
                                ),
                            ],
                        }
                    ),
                    "fixtures": adjusted_fixtures,
                }
            )
        )
    return adjusted_slices, adjusted_count


def _adjusted_fixture(
    fixture: HistoricalFixture,
    *,
    candidate_probabilities: dict[str, float],
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    feature_ablation_report_key: str,
) -> HistoricalFixture:
    return fixture.model_copy(
        update={
            "model_version": f"{fixture.model_version}+prematch-feature-shadow",
            "predictions": [
                _adjusted_prediction(
                    prediction,
                    candidate_probabilities=candidate_probabilities,
                    grid_candidate=grid_candidate,
                    feature_ablation_report_key=feature_ablation_report_key,
                )
                for prediction in fixture.predictions
            ],
        }
    )


def _adjusted_prediction(
    prediction: HistoricalMarketPrediction,
    *,
    candidate_probabilities: dict[str, float],
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    feature_ablation_report_key: str,
) -> HistoricalMarketPrediction:
    if prediction.market_type != "1x2" or prediction.outcome not in candidate_probabilities:
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
                "prematch_feature_shadow_adjusted": True,
                "prematch_feature_shadow_baseline_probability": prediction.probability,
                "prematch_feature_shadow_probability": adjusted_probability,
                "prematch_feature_grid_candidate_id": grid_candidate.candidate_id,
                "prematch_feature_ablation_report_key": feature_ablation_report_key,
                "shadow_only": True,
            },
        }
    )


def _selected_grid_candidates(
    grid_report: HistoricalPrematchFeatureAblationGridReport,
    *,
    options: HistoricalPrematchFeatureFinalAnswerGateOptions,
) -> list[HistoricalPrematchFeatureAblationGridCandidate]:
    candidates = [
        candidate
        for candidate in grid_report.candidates
        if (
            candidate.passed_non_regression_gate
            or not options.require_grid_non_regression_candidate
        )
    ]
    return candidates[: options.top_candidate_limit]


def _ablation_options_from_grid_candidate(
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    *,
    sample_limit: int,
) -> HistoricalPrematchFeatureAblationOptions:
    options = HistoricalPrematchFeatureAblationOptions.model_validate(
        grid_candidate.options_json
    )
    return options.model_copy(update={"prediction_sample_limit": sample_limit})


def _evaluation_sort_key(
    evaluation: HistoricalPrematchFeatureFinalAnswerCandidateEvaluation,
) -> tuple[int, int, float, float, float, int]:
    return (
        0 if evaluation.passed_final_answer_gate else 1,
        0 if evaluation.suite.status != "regressed" else 1,
        -_delta(evaluation.deltas_json, "final_hit_rate_delta"),
        _delta(evaluation.deltas_json, "brier_score_delta"),
        _delta(evaluation.deltas_json, "log_loss_delta"),
        evaluation.feature_grid_rank,
    )


def _suite_warnings(
    *,
    comparisons: Sequence[HistoricalRecommendationBacktestComparisonResult],
    status: str,
) -> list[str]:
    warnings: list[str] = []
    if not comparisons:
        warnings.append("prematch_feature_final_answer_gate:no_comparisons")
    if status == "regressed":
        warnings.append("prematch_feature_final_answer_gate:suite_regressed")
    elif status == "mixed":
        warnings.append("prematch_feature_final_answer_gate:suite_mixed")
    return warnings


def _report_warnings(
    evaluations: Sequence[HistoricalPrematchFeatureFinalAnswerCandidateEvaluation],
    *,
    historical_warnings: Sequence[str],
) -> list[str]:
    warnings = list(historical_warnings)
    if not evaluations:
        warnings.append("prematch_feature_final_answer_gate:no_evaluations")
    if evaluations and all(
        not evaluation.passed_final_answer_gate for evaluation in evaluations
    ):
        warnings.append("prematch_feature_final_answer_gate:no_passing_candidate")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Evaluate structured prematch feature grid candidates with final-answer "
            "historical quality gates."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--grid-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--gate-id", default=DEFAULT_PREMATCH_FEATURE_FINAL_ANSWER_GATE_ID)
    parser.add_argument("--top-candidate-limit", type=int, default=5)
    parser.add_argument("--allow-grid-regression-candidates", action="store_true")
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
    parser.add_argument("--max-warning-count", type=int)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureFinalAnswerGateOptions:
    return HistoricalPrematchFeatureFinalAnswerGateOptions(
        gate_id=args.gate_id,
        top_candidate_limit=args.top_candidate_limit,
        require_grid_non_regression_candidate=not args.allow_grid_regression_candidates,
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


def _load_grid_report(
    path: Path | None,
) -> HistoricalPrematchFeatureAblationGridReport | None:
    if path is None:
        return None
    return HistoricalPrematchFeatureAblationGridReport.model_validate_json(
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


def _feature_suite_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
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
        "feature_grid_candidate_id": grid_candidate.candidate_id,
        "feature_grid_options": grid_candidate.options_json,
        "backtest_options": backtest_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_final_answer_suite:{digest}"


def _feature_comparison_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
    backtest_options: HistoricalRecommendationBacktestOptions,
) -> str:
    payload = {
        "slice_id": historical_slice.metadata.slice_id,
        "as_of_time": historical_slice.as_of_time_utc.isoformat(),
        "feature_grid_candidate_id": grid_candidate.candidate_id,
        "backtest_options": backtest_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_final_answer_comparison:{digest}"


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    grid_report: HistoricalPrematchFeatureAblationGridReport,
    options: HistoricalPrematchFeatureFinalAnswerGateOptions,
    evaluated_candidates: Sequence[HistoricalPrematchFeatureFinalAnswerCandidateEvaluation],
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "grid_report_key": grid_report.report_key,
        "evaluated_candidate_ids": [
            candidate.feature_grid_candidate_id for candidate in evaluated_candidates
        ],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_final_answer_gate:{digest}"


def _adjusted_slice_id(
    slice_id: str,
    *,
    grid_candidate: HistoricalPrematchFeatureAblationGridCandidate,
) -> str:
    digest = sha256(grid_candidate.candidate_id.encode("utf-8")).hexdigest()[:8]
    return f"{slice_id}__prematch_feature_shadow_{digest}"


def _scenario_key(final_answer: HistoricalRecommendationScenarioResult | None) -> str | None:
    return final_answer.scenario.scenario_key if final_answer is not None else None


def _delta(deltas: dict[str, object], key: str) -> float:
    value = deltas.get(key)
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
