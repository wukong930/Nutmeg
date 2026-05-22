from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
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
from nutmeg.recommendations.models import (
    RecommendationMarketType,
    RecommendationMode,
    RecommendationStrategy,
)

type HistoricalRecommendationSuiteQualityGateCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalRecommendationSuiteQualityGateStatus = Literal["passed", "failed"]


class HistoricalRecommendationSuiteQualityGateOptions(BaseModel):
    min_slice_count: int = Field(default=1, ge=0)
    min_comparison_count: int = Field(default=1, ge=0)
    min_final_hit_sample_size: int = Field(default=1, ge=0)
    min_final_hit_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    min_candidate_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_candidate_roi: float | None = None
    min_competition_candidate_roi: float | None = None
    max_final_answer_correlation_exposure: int | None = Field(default=None, ge=1)
    min_candidate_dynamic_mixed_final_answer_count: int = Field(default=0, ge=0)
    min_candidate_dynamic_mixed_final_answer_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_candidate_handicap_final_answer_count: int = Field(default=0, ge=0)
    min_candidate_correct_score_final_answer_count: int = Field(default=0, ge=0)
    min_candidate_multiple_choice_final_answer_count: int = Field(default=0, ge=0)
    fail_on_suite_statuses: tuple[str, ...] = ("regressed", "mixed")
    min_final_hit_rate_delta: float | None = 0.0
    min_roi_delta: float | None = None
    min_profit_loss_delta: float | None = None
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_mean_calibration_error_delta: float | None = 0.0
    min_profile_reference_final_hit_rate_delta: float | None = None
    min_profile_reference_roi_delta: float | None = None
    min_profile_reference_profit_loss_delta: float | None = None
    max_profile_reference_brier_score_delta: float | None = None
    max_profile_reference_log_loss_delta: float | None = None
    max_profile_reference_mean_calibration_error_delta: float | None = None
    min_profile_reference_upset_capture_rate_delta: float | None = None
    min_upset_capture_sample_size: int = Field(default=0, ge=0)
    min_upset_capture_rate_delta: float | None = None
    min_upset_final_answer_lane_selected_candidate_count: int = Field(default=0, ge=0)
    min_solver_selected_scenario_count: int = Field(default=0, ge=0)
    min_final_answer_changed_count: int = Field(default=0, ge=0)
    require_lifecycle_quality_cycle: bool = False
    require_lifecycle_persisted_smoke: bool = True
    require_lifecycle_source_status_synced: bool = True
    min_lifecycle_effective_leaf_count: int = Field(default=0, ge=0)
    min_lifecycle_active_edge_count: int = Field(default=0, ge=0)
    max_lifecycle_critical_issue_count: int | None = Field(default=0, ge=0)
    max_lifecycle_source_status_sync_required_count: int | None = Field(
        default=0,
        ge=0,
    )
    require_successor_chain_evaluation: bool = False
    min_successor_effective_leaf_count: int = Field(default=0, ge=0)
    min_successor_active_edge_count: int = Field(default=0, ge=0)
    max_successor_critical_issue_count: int | None = Field(default=0, ge=0)
    max_successor_ambiguous_source_count: int | None = Field(default=0, ge=0)
    max_successor_source_status_sync_required_count: int | None = Field(
        default=0,
        ge=0,
    )
    require_market_movement_runtime_replay: bool = False
    require_market_movement_runtime_replay_allowed: bool = True
    require_market_movement_runtime_replay_passed_status: bool = True
    min_market_movement_runtime_replay_rule_count: int = Field(default=0, ge=0)
    min_market_movement_runtime_replay_selected_rule_count: int = Field(default=0, ge=0)
    min_market_movement_runtime_replay_accepted_count: int = Field(default=0, ge=0)
    min_market_movement_runtime_replay_adjusted_fixture_count: int = Field(
        default=0,
        ge=0,
    )
    min_market_movement_runtime_replay_adjusted_prediction_count: int = Field(
        default=0,
        ge=0,
    )
    min_market_movement_runtime_replay_final_hit_rate_delta: float | None = 0.0
    min_market_movement_runtime_replay_roi_delta: float | None = 0.0
    min_market_movement_runtime_replay_profit_loss_delta: float | None = 0.0
    max_market_movement_runtime_replay_brier_score_delta: float | None = 0.0
    max_market_movement_runtime_replay_log_loss_delta: float | None = 0.0
    max_market_movement_runtime_replay_mean_calibration_error_delta: float | None = 0.0
    require_market_movement_runtime_replay_production_unchanged: bool = True
    require_market_movement_runtime_replay_public_response_unchanged: bool = True
    max_warning_count: int | None = Field(default=None, ge=0)


class HistoricalRecommendationSuiteQualityGateCheck(BaseModel):
    name: str
    status: HistoricalRecommendationSuiteQualityGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalRecommendationSuiteQualityGateResult(BaseModel):
    gate_key: str
    status: HistoricalRecommendationSuiteQualityGateStatus
    passed: bool
    suite_key: str
    suite_status: str
    checks: list[HistoricalRecommendationSuiteQualityGateCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    aggregate_deltas_json: dict[str, object] = Field(default_factory=dict)
    lifecycle_quality_cycle_report_path: Path | None = None
    lifecycle_quality_cycle_present: bool = False
    lifecycle_quality_cycle_passed: bool | None = None
    lifecycle_quality_cycle_summary_json: dict[str, object] = Field(default_factory=dict)
    successor_chain_evaluation_report_path: Path | None = None
    successor_chain_evaluation_present: bool = False
    successor_chain_evaluation_passed: bool | None = None
    successor_chain_evaluation_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    market_movement_runtime_replay_report_path: Path | None = None
    market_movement_runtime_replay_present: bool = False
    market_movement_runtime_replay_passed: bool | None = None
    market_movement_runtime_replay_summary_json: dict[str, object] = Field(
        default_factory=dict
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationLifecycleQualityCycleEvidence(BaseModel):
    cycle_key: str
    passed: bool
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalRecommendationSuccessorChainEvaluationEvidence(BaseModel):
    passed: bool
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRuntimeReplayEvidence(BaseModel):
    passed: bool
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_historical_recommendation_suite_quality_gate(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions | None = None,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None = None,
    lifecycle_quality_cycle: (HistoricalRecommendationLifecycleQualityCycleEvidence | None) = None,
    lifecycle_quality_cycle_report_path: Path | None = None,
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ) = None,
    successor_chain_evaluation_report_path: Path | None = None,
    market_movement_runtime_replay: (
        HistoricalMarketMovementRuntimeReplayEvidence | None
    ) = None,
    market_movement_runtime_replay_report_path: Path | None = None,
) -> HistoricalRecommendationSuiteQualityGateResult:
    resolved_options = options or HistoricalRecommendationSuiteQualityGateOptions()
    checks = _quality_gate_checks(
        suite,
        options=resolved_options,
        reference_suite=reference_suite,
        lifecycle_quality_cycle=lifecycle_quality_cycle,
        successor_chain_evaluation=successor_chain_evaluation,
        market_movement_runtime_replay=market_movement_runtime_replay,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: HistoricalRecommendationSuiteQualityGateStatus = "passed" if passed else "failed"
    warnings = [
        f"historical_suite_quality_gate:failed_check:{check.name}" for check in failed_checks
    ]
    summary = _quality_gate_summary(
        gate_key=_gate_key(
            suite,
            options=resolved_options,
            reference_suite=reference_suite,
            lifecycle_quality_cycle=lifecycle_quality_cycle,
            successor_chain_evaluation=successor_chain_evaluation,
            market_movement_runtime_replay=market_movement_runtime_replay,
        ),
        suite=suite,
        reference_suite=reference_suite,
        lifecycle_quality_cycle=lifecycle_quality_cycle,
        lifecycle_quality_cycle_report_path=lifecycle_quality_cycle_report_path,
        successor_chain_evaluation=successor_chain_evaluation,
        successor_chain_evaluation_report_path=successor_chain_evaluation_report_path,
        market_movement_runtime_replay=market_movement_runtime_replay,
        market_movement_runtime_replay_report_path=market_movement_runtime_replay_report_path,
        checks=checks,
        status=status,
        passed=passed,
        warnings=warnings,
    )
    return HistoricalRecommendationSuiteQualityGateResult(
        gate_key=cast(str, summary["gate_key"]),
        status=status,
        passed=passed,
        suite_key=suite.suite_key,
        suite_status=suite.status,
        checks=checks,
        warnings=warnings,
        aggregate_deltas_json=suite.aggregate_deltas_json,
        lifecycle_quality_cycle_report_path=lifecycle_quality_cycle_report_path,
        lifecycle_quality_cycle_present=lifecycle_quality_cycle is not None,
        lifecycle_quality_cycle_passed=(
            lifecycle_quality_cycle.passed if lifecycle_quality_cycle is not None else None
        ),
        lifecycle_quality_cycle_summary_json=(
            dict(lifecycle_quality_cycle.summary_json)
            if lifecycle_quality_cycle is not None
            else {}
        ),
        successor_chain_evaluation_report_path=successor_chain_evaluation_report_path,
        successor_chain_evaluation_present=successor_chain_evaluation is not None,
        successor_chain_evaluation_passed=(
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else None
        ),
        successor_chain_evaluation_summary_json=(
            dict(successor_chain_evaluation.summary_json)
            if successor_chain_evaluation is not None
            else {}
        ),
        market_movement_runtime_replay_report_path=market_movement_runtime_replay_report_path,
        market_movement_runtime_replay_present=market_movement_runtime_replay is not None,
        market_movement_runtime_replay_passed=(
            market_movement_runtime_replay.passed
            if market_movement_runtime_replay is not None
            else None
        ),
        market_movement_runtime_replay_summary_json=(
            dict(market_movement_runtime_replay.summary_json)
            if market_movement_runtime_replay is not None
            else {}
        ),
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    backtest_options = _backtest_options_from_args(args)
    loaded_slices = _historical_slices_from_args(args)
    suite = run_historical_recommendation_backtest_suite(
        loaded_slices.slices,
        options=backtest_options,
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
    )
    reference_options = _profile_reference_options_from_args(
        backtest_options,
        args=args,
    )
    reference_suite = (
        run_historical_recommendation_backtest_suite(
            loaded_slices.slices,
            options=reference_options,
            baseline_optimizer_profile=cast(
                HistoricalOptimizerProfile,
                args.baseline_optimizer_profile,
            ),
            candidate_optimizer_profile=cast(
                HistoricalOptimizerProfile,
                args.candidate_optimizer_profile,
            ),
        )
        if reference_options is not None
        else None
    )
    lifecycle_quality_cycle = _load_lifecycle_quality_cycle(
        args.lifecycle_quality_cycle_report_path
    )
    successor_chain_evaluation = _load_successor_chain_evaluation(
        args.successor_chain_evaluation_report_path
    )
    market_movement_runtime_replay = _load_market_movement_runtime_replay(
        args.market_movement_runtime_replay_report_path
    )
    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=_options_from_args(args),
        reference_suite=reference_suite,
        lifecycle_quality_cycle=lifecycle_quality_cycle,
        lifecycle_quality_cycle_report_path=args.lifecycle_quality_cycle_report_path,
        successor_chain_evaluation=successor_chain_evaluation,
        successor_chain_evaluation_report_path=args.successor_chain_evaluation_report_path,
        market_movement_runtime_replay=market_movement_runtime_replay,
        market_movement_runtime_replay_report_path=(
            args.market_movement_runtime_replay_report_path
        ),
    )
    if loaded_slices.manifests:
        manifest_summaries = [
            _manifest_summary(manifest_bundle)
            for manifest_bundle in loaded_slices.manifests
        ]
        result.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            result.summary_json["suite_manifest"] = manifest_summaries[0]
    if loaded_slices.warnings:
        result.summary_json["manifest_warnings"] = loaded_slices.warnings
    output = dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _quality_gate_checks(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None = None,
    lifecycle_quality_cycle: (HistoricalRecommendationLifecycleQualityCycleEvidence | None) = None,
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ) = None,
    market_movement_runtime_replay: (
        HistoricalMarketMovementRuntimeReplayEvidence | None
    ) = None,
) -> list[HistoricalRecommendationSuiteQualityGateCheck]:
    checks = [
        _check_minimum(
            name="slice_count",
            actual=suite.slice_count,
            threshold=options.min_slice_count,
            detail="historical suite should cover enough frozen slices",
        ),
        _check_minimum(
            name="comparison_count",
            actual=suite.comparison_count,
            threshold=options.min_comparison_count,
            detail="historical suite should produce enough optimizer comparisons",
        ),
        _check_minimum(
            name="final_hit_sample_size",
            actual=_summary_int(suite.summary_json, "candidate_final_hit_sample_size"),
            threshold=options.min_final_hit_sample_size,
            detail="candidate settled final-hit sample size should meet the minimum",
        ),
        _check_optional_minimum(
            name="final_hit_coverage_ratio",
            actual=_ratio(
                _summary_int(suite.summary_json, "candidate_final_hit_sample_size"),
                suite.comparison_count,
            ),
            threshold=options.min_final_hit_coverage_ratio,
            detail=(
                "candidate settled final-hit samples should cover enough historical "
                "optimizer comparisons"
            ),
        ),
        _check_optional_minimum(
            name="candidate_final_hit_rate",
            actual=_summary_number(suite.summary_json, "candidate_final_hit_rate"),
            threshold=options.min_candidate_final_hit_rate,
            detail="candidate final-answer hit rate should meet the absolute minimum",
        ),
        _check_optional_minimum(
            name="candidate_roi",
            actual=_summary_number(suite.summary_json, "candidate_roi"),
            threshold=options.min_candidate_roi,
            detail="candidate final-answer ROI should meet the absolute minimum",
        ),
        _check_optional_minimum(
            name="competition_candidate_roi",
            actual=_worst_competition_candidate_roi(suite),
            threshold=options.min_competition_candidate_roi,
            detail="each competition final-answer ROI should meet the minimum",
        ),
        _check_optional_maximum(
            name="final_answer_correlation_exposure",
            actual=_max_final_answer_correlation_exposure(suite),
            threshold=options.max_final_answer_correlation_exposure,
            detail="final answers should not concentrate too many legs in one exposure",
        ),
        _check_minimum(
            name="candidate_dynamic_mixed_final_answer_count",
            actual=_summary_int(
                suite.summary_json,
                "candidate_dynamic_mixed_final_answer_count",
            ),
            threshold=options.min_candidate_dynamic_mixed_final_answer_count,
            detail=(
                "candidate final answers should include enough dynamic mixed-market "
                "answers when explicitly required"
            ),
        ),
        _check_optional_minimum(
            name="candidate_dynamic_mixed_final_answer_rate",
            actual=_summary_number(
                suite.summary_json,
                "candidate_dynamic_mixed_final_answer_rate",
            ),
            threshold=options.min_candidate_dynamic_mixed_final_answer_rate,
            detail=(
                "candidate final answers should keep the configured dynamic "
                "mixed-market rate"
            ),
        ),
        _check_minimum(
            name="candidate_handicap_final_answer_count",
            actual=_summary_int(
                suite.summary_json,
                "candidate_handicap_final_answer_count",
            ),
            threshold=options.min_candidate_handicap_final_answer_count,
            detail=(
                "candidate final answers should include enough handicap market "
                "answers when explicitly required"
            ),
        ),
        _check_minimum(
            name="candidate_correct_score_final_answer_count",
            actual=_summary_int(
                suite.summary_json,
                "candidate_correct_score_final_answer_count",
            ),
            threshold=options.min_candidate_correct_score_final_answer_count,
            detail=(
                "candidate final answers should include enough correct-score "
                "answers when explicitly required"
            ),
        ),
        _check_minimum(
            name="candidate_multiple_choice_final_answer_count",
            actual=_summary_int(
                suite.summary_json,
                "candidate_multiple_choice_final_answer_count",
            ),
            threshold=options.min_candidate_multiple_choice_final_answer_count,
            detail=(
                "candidate final answers should include enough multiple-choice "
                "legs when explicitly required"
            ),
        ),
        _check_suite_status(suite, options=options),
        _check_optional_minimum(
            name="final_hit_rate_delta",
            actual=_delta_number(suite, "final_hit_rate_delta"),
            threshold=options.min_final_hit_rate_delta,
            detail="candidate final-hit rate should not regress versus baseline",
        ),
        _check_optional_minimum(
            name="roi_delta",
            actual=_delta_number(suite, "roi_delta"),
            threshold=options.min_roi_delta,
            detail="candidate ROI delta should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="profit_loss_delta",
            actual=_delta_number(suite, "profit_loss_delta"),
            threshold=options.min_profit_loss_delta,
            detail="candidate profit/loss delta should meet the configured minimum",
        ),
        _check_optional_maximum(
            name="brier_score_delta",
            actual=_delta_number(suite, "brier_score_delta"),
            threshold=options.max_brier_score_delta,
            detail="candidate Brier score should not regress versus baseline",
        ),
        _check_optional_maximum(
            name="log_loss_delta",
            actual=_delta_number(suite, "log_loss_delta"),
            threshold=options.max_log_loss_delta,
            detail="candidate log loss should not regress versus baseline",
        ),
        _check_optional_maximum(
            name="mean_calibration_error_delta",
            actual=_delta_number(suite, "mean_calibration_error_delta"),
            threshold=options.max_mean_calibration_error_delta,
            detail="candidate calibration error should not regress versus baseline",
        ),
        _check_optional_minimum(
            name="profile_reference_final_hit_rate_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_final_hit_rate",
            ),
            threshold=options.min_profile_reference_final_hit_rate_delta,
            detail="candidate profile final-hit rate should not regress versus reference",
        ),
        _check_optional_minimum(
            name="profile_reference_roi_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_roi",
            ),
            threshold=options.min_profile_reference_roi_delta,
            detail="candidate profile ROI should meet the reference delta minimum",
        ),
        _check_optional_minimum(
            name="profile_reference_profit_loss_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_profit_loss",
            ),
            threshold=options.min_profile_reference_profit_loss_delta,
            detail=("candidate profile profit/loss should meet the reference delta minimum"),
        ),
        _check_optional_maximum(
            name="profile_reference_brier_score_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_brier_score",
            ),
            threshold=options.max_profile_reference_brier_score_delta,
            detail="candidate profile Brier score should not regress versus reference",
        ),
        _check_optional_maximum(
            name="profile_reference_log_loss_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_log_loss",
            ),
            threshold=options.max_profile_reference_log_loss_delta,
            detail="candidate profile log loss should not regress versus reference",
        ),
        _check_optional_maximum(
            name="profile_reference_mean_calibration_error_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_mean_calibration_error",
            ),
            threshold=options.max_profile_reference_mean_calibration_error_delta,
            detail=("candidate profile calibration error should not regress versus reference"),
        ),
        _check_optional_minimum(
            name="profile_reference_upset_capture_rate_delta",
            actual=_profile_reference_delta_number(
                suite,
                reference_suite,
                "candidate_upset_capture_rate",
            ),
            threshold=options.min_profile_reference_upset_capture_rate_delta,
            detail=("candidate profile upset-capture rate should meet the reference delta minimum"),
        ),
        _check_minimum(
            name="upset_capture_sample_size",
            actual=_summary_int(suite.summary_json, "candidate_upset_opportunity_count"),
            threshold=options.min_upset_capture_sample_size,
            detail="upset-opportunity sample size should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="upset_capture_rate_delta",
            actual=_delta_number(suite, "upset_capture_rate_delta"),
            threshold=options.min_upset_capture_rate_delta,
            detail="candidate upset-capture rate delta should meet the minimum",
        ),
        _check_minimum(
            name="upset_final_answer_lane_selected_candidate_count",
            actual=_summary_int(
                suite.summary_json,
                "candidate_final_answer_upset_final_answer_lane_selected_candidate_count",
            ),
            threshold=options.min_upset_final_answer_lane_selected_candidate_count,
            detail=(
                "upset final-answer lane should select enough candidates when explicitly required"
            ),
        ),
        _check_minimum(
            name="solver_selected_scenario_count",
            actual=_delta_int(suite, "candidate_solver_selected_scenario_count"),
            threshold=options.min_solver_selected_scenario_count,
            detail="solver should influence enough candidate scenarios when required",
        ),
        _check_minimum(
            name="final_answer_changed_count",
            actual=_delta_int(suite, "final_answer_changed_count"),
            threshold=options.min_final_answer_changed_count,
            detail="solver should change enough final answers when required",
        ),
        _check_optional_maximum(
            name="warning_count",
            actual=len(suite.warnings),
            threshold=options.max_warning_count,
            detail="historical suite warnings should stay within the configured limit",
        ),
        _lifecycle_quality_cycle_present_check(
            lifecycle_quality_cycle,
            options=options,
        ),
    ]
    checks.extend(
        _lifecycle_quality_cycle_checks(
            lifecycle_quality_cycle,
            options=options,
        )
    )
    checks.extend(
        _successor_chain_evaluation_checks(
            successor_chain_evaluation,
            options=options,
        )
    )
    checks.extend(
        _market_movement_runtime_replay_checks(
            market_movement_runtime_replay,
            options=options,
        )
    )
    return checks


def _quality_gate_summary(
    *,
    gate_key: str,
    suite: HistoricalRecommendationBacktestSuiteResult,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None,
    lifecycle_quality_cycle: HistoricalRecommendationLifecycleQualityCycleEvidence | None,
    lifecycle_quality_cycle_report_path: Path | None,
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ),
    successor_chain_evaluation_report_path: Path | None,
    market_movement_runtime_replay: HistoricalMarketMovementRuntimeReplayEvidence | None,
    market_movement_runtime_replay_report_path: Path | None,
    checks: Sequence[HistoricalRecommendationSuiteQualityGateCheck],
    status: HistoricalRecommendationSuiteQualityGateStatus,
    passed: bool,
    warnings: Sequence[str],
) -> dict[str, object]:
    failed_checks = [check.name for check in checks if check.status == "failed"]
    lifecycle_summary = (
        lifecycle_quality_cycle.summary_json if lifecycle_quality_cycle is not None else {}
    )
    successor_summary = (
        successor_chain_evaluation.summary_json
        if successor_chain_evaluation is not None
        else {}
    )
    market_movement_summary = (
        market_movement_runtime_replay.summary_json
        if market_movement_runtime_replay is not None
        else {}
    )
    return {
        "calculation_basis": "historical_recommendation_suite_quality_gate_v3_1",
        "gate_key": gate_key,
        "status": status,
        "passed": passed,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "slice_count": suite.slice_count,
        "comparison_count": suite.comparison_count,
        "final_answer_competition_profile_version": suite.summary_json.get(
            "final_answer_competition_profile_version"
        ),
        "final_answer_scenario_variant_count": suite.summary_json.get(
            "final_answer_scenario_variant_count"
        ),
        "baseline_completed_scenario_variant_count": suite.summary_json.get(
            "baseline_completed_scenario_variant_count"
        ),
        "candidate_completed_scenario_variant_count": suite.summary_json.get(
            "candidate_completed_scenario_variant_count"
        ),
        "short_price_negative_edge_guardrail": suite.summary_json.get(
            "short_price_negative_edge_guardrail"
        ),
        "short_price_negative_edge_max_decimal_odds": suite.summary_json.get(
            "short_price_negative_edge_max_decimal_odds"
        ),
        "short_price_negative_edge_min_probability": suite.summary_json.get(
            "short_price_negative_edge_min_probability"
        ),
        "short_price_negative_edge_max_model_edge": suite.summary_json.get(
            "short_price_negative_edge_max_model_edge"
        ),
        "baseline_short_price_negative_edge_guardrail_excluded_candidate_count": (
            suite.summary_json.get(
                "baseline_short_price_negative_edge_guardrail_excluded_candidate_count"
            )
        ),
        "candidate_short_price_negative_edge_guardrail_excluded_candidate_count": (
            suite.summary_json.get(
                "candidate_short_price_negative_edge_guardrail_excluded_candidate_count"
            )
        ),
        "short_price_negative_edge_soft_penalty": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty"
        ),
        "short_price_negative_edge_soft_penalty_strength": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty_strength"
        ),
        "short_price_negative_edge_soft_penalty_competition_ids": suite.summary_json.get(
            "short_price_negative_edge_soft_penalty_competition_ids"
        ),
        "baseline_short_price_negative_edge_soft_penalty_candidate_count": (
            suite.summary_json.get(
                "baseline_short_price_negative_edge_soft_penalty_candidate_count"
            )
        ),
        "candidate_short_price_negative_edge_soft_penalty_candidate_count": (
            suite.summary_json.get(
                "candidate_short_price_negative_edge_soft_penalty_candidate_count"
            )
        ),
        "final_answer_quality_signal_penalty": suite.summary_json.get(
            "final_answer_quality_signal_penalty"
        ),
        "final_answer_quality_signal_penalty_strength": suite.summary_json.get(
            "final_answer_quality_signal_penalty_strength"
        ),
        "final_answer_quality_signal_probability_min": suite.summary_json.get(
            "final_answer_quality_signal_probability_min"
        ),
        "final_answer_quality_signal_probability_max": suite.summary_json.get(
            "final_answer_quality_signal_probability_max"
        ),
        "final_answer_quality_signal_min_decimal_odds": suite.summary_json.get(
            "final_answer_quality_signal_min_decimal_odds"
        ),
        "final_answer_quality_signal_max_decimal_odds": suite.summary_json.get(
            "final_answer_quality_signal_max_decimal_odds"
        ),
        "final_answer_quality_signal_max_model_edge": suite.summary_json.get(
            "final_answer_quality_signal_max_model_edge"
        ),
        "final_answer_quality_signal_score_min": suite.summary_json.get(
            "final_answer_quality_signal_score_min"
        ),
        "final_answer_quality_signal_score_max": suite.summary_json.get(
            "final_answer_quality_signal_score_max"
        ),
        "final_answer_quality_signal_competition_ids": suite.summary_json.get(
            "final_answer_quality_signal_competition_ids"
        ),
        "baseline_final_answer_quality_signal_affected_leg_count": (
            suite.summary_json.get("baseline_final_answer_quality_signal_affected_leg_count")
        ),
        "candidate_final_answer_quality_signal_affected_leg_count": (
            suite.summary_json.get("candidate_final_answer_quality_signal_affected_leg_count")
        ),
        "candidate_final_hit_sample_size": _summary_int(
            suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        "candidate_final_hit_coverage_ratio": _ratio(
            _summary_int(suite.summary_json, "candidate_final_hit_sample_size"),
            suite.comparison_count,
        ),
        "candidate_final_hit_rate": _summary_number(
            suite.summary_json,
            "candidate_final_hit_rate",
        ),
        "candidate_roi": _summary_number(suite.summary_json, "candidate_roi"),
        "competition_candidate_roi": _competition_candidate_roi_map(suite),
        "worst_competition_candidate_roi": _worst_competition_candidate_roi(suite),
        "worst_competition_id": _worst_competition_id(suite),
        "max_final_answer_correlation_exposure": (_max_final_answer_correlation_exposure(suite)),
        "correlated_final_answer_count": _correlated_final_answer_count(suite),
        "baseline_dynamic_mixed_final_answer_count": _summary_int(
            suite.summary_json,
            "baseline_dynamic_mixed_final_answer_count",
        ),
        "candidate_dynamic_mixed_final_answer_count": _summary_int(
            suite.summary_json,
            "candidate_dynamic_mixed_final_answer_count",
        ),
        "baseline_dynamic_mixed_final_answer_rate": _summary_number(
            suite.summary_json,
            "baseline_dynamic_mixed_final_answer_rate",
        ),
        "candidate_dynamic_mixed_final_answer_rate": _summary_number(
            suite.summary_json,
            "candidate_dynamic_mixed_final_answer_rate",
        ),
        "baseline_final_answer_market_type_counts": suite.summary_json.get(
            "baseline_final_answer_market_type_counts",
            {},
        ),
        "candidate_final_answer_market_type_counts": suite.summary_json.get(
            "candidate_final_answer_market_type_counts",
            {},
        ),
        "baseline_handicap_final_answer_count": _summary_int(
            suite.summary_json,
            "baseline_handicap_final_answer_count",
        ),
        "candidate_handicap_final_answer_count": _summary_int(
            suite.summary_json,
            "candidate_handicap_final_answer_count",
        ),
        "baseline_handicap_final_answer_rate": _summary_number(
            suite.summary_json,
            "baseline_handicap_final_answer_rate",
        ),
        "candidate_handicap_final_answer_rate": _summary_number(
            suite.summary_json,
            "candidate_handicap_final_answer_rate",
        ),
        "baseline_correct_score_final_answer_count": _summary_int(
            suite.summary_json,
            "baseline_correct_score_final_answer_count",
        ),
        "candidate_correct_score_final_answer_count": _summary_int(
            suite.summary_json,
            "candidate_correct_score_final_answer_count",
        ),
        "baseline_multiple_choice_final_answer_count": _summary_int(
            suite.summary_json,
            "baseline_multiple_choice_final_answer_count",
        ),
        "candidate_multiple_choice_final_answer_count": _summary_int(
            suite.summary_json,
            "candidate_multiple_choice_final_answer_count",
        ),
        "baseline_final_answer_selected_candidate_count": _summary_int(
            suite.summary_json,
            "baseline_final_answer_selected_candidate_count",
        ),
        "candidate_final_answer_selected_candidate_count": _summary_int(
            suite.summary_json,
            "candidate_final_answer_selected_candidate_count",
        ),
        "baseline_final_answer_multiple_choice_fixture_count": _summary_int(
            suite.summary_json,
            "baseline_final_answer_multiple_choice_fixture_count",
        ),
        "candidate_final_answer_multiple_choice_fixture_count": _summary_int(
            suite.summary_json,
            "candidate_final_answer_multiple_choice_fixture_count",
        ),
        "candidate_profit_loss": _summary_number(
            suite.summary_json,
            "candidate_profit_loss",
        ),
        "candidate_brier_score": _summary_number(
            suite.summary_json,
            "candidate_brier_score",
        ),
        "candidate_log_loss": _summary_number(
            suite.summary_json,
            "candidate_log_loss",
        ),
        "candidate_mean_calibration_error": _summary_number(
            suite.summary_json,
            "candidate_mean_calibration_error",
        ),
        "profile_reference_enabled": reference_suite is not None,
        "profile_reference_suite_key": (
            reference_suite.suite_key if reference_suite is not None else None
        ),
        "profile_reference_upset_final_answer_lane_disabled": (
            _profile_reference_bool_disabled(
                suite,
                reference_suite,
                "upset_final_answer_lane",
            )
        ),
        "profile_reference_correct_score_final_answer_lane_disabled": (
            _profile_reference_bool_disabled(
                suite,
                reference_suite,
                "correct_score_final_answer_lane",
            )
        ),
        "profile_reference_candidate_final_hit_rate": _reference_summary_number(
            reference_suite,
            "candidate_final_hit_rate",
        ),
        "profile_reference_candidate_roi": _reference_summary_number(
            reference_suite,
            "candidate_roi",
        ),
        "profile_reference_candidate_profit_loss": _reference_summary_number(
            reference_suite,
            "candidate_profit_loss",
        ),
        "profile_reference_candidate_brier_score": _reference_summary_number(
            reference_suite,
            "candidate_brier_score",
        ),
        "profile_reference_candidate_log_loss": _reference_summary_number(
            reference_suite,
            "candidate_log_loss",
        ),
        "profile_reference_candidate_mean_calibration_error": (
            _reference_summary_number(
                reference_suite,
                "candidate_mean_calibration_error",
            )
        ),
        "profile_reference_candidate_upset_capture_rate": _reference_summary_number(
            reference_suite,
            "candidate_upset_capture_rate",
        ),
        "profile_reference_deltas": _profile_reference_deltas(
            suite,
            reference_suite,
        ),
        "lifecycle_quality_cycle_present": lifecycle_quality_cycle is not None,
        "lifecycle_quality_cycle_passed": (
            lifecycle_quality_cycle.passed if lifecycle_quality_cycle is not None else None
        ),
        "lifecycle_quality_cycle_report_path": (
            str(lifecycle_quality_cycle_report_path)
            if lifecycle_quality_cycle_report_path is not None
            else None
        ),
        "lifecycle_quality_cycle_key": (
            lifecycle_quality_cycle.cycle_key if lifecycle_quality_cycle is not None else None
        ),
        "lifecycle_persisted_smoke_present": bool(
            lifecycle_summary.get("persisted_lifecycle_smoke_present", False)
        ),
        "lifecycle_persisted_smoke_passed": bool(
            lifecycle_summary.get("persisted_lifecycle_smoke_passed", False)
        ),
        "lifecycle_source_status_synced": bool(
            lifecycle_summary.get("persisted_lifecycle_source_status_synced", False)
        ),
        "lifecycle_effective_leaf_count": _summary_int(
            lifecycle_summary,
            "persisted_lifecycle_effective_leaf_count",
        ),
        "lifecycle_active_edge_count": _summary_int(
            lifecycle_summary,
            "persisted_lifecycle_active_edge_count",
        ),
        "lifecycle_critical_issue_count": _summary_int(
            lifecycle_summary,
            "persisted_lifecycle_critical_issue_count",
        ),
        "lifecycle_source_status_sync_required_count": _summary_int(
            lifecycle_summary,
            "persisted_lifecycle_source_status_sync_required_count",
        ),
        "successor_chain_evaluation_present": successor_chain_evaluation is not None,
        "successor_chain_evaluation_passed": (
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else None
        ),
        "successor_chain_evaluation_report_path": (
            str(successor_chain_evaluation_report_path)
            if successor_chain_evaluation_report_path is not None
            else None
        ),
        "successor_effective_final_only_ready": (
            bool(successor_chain_evaluation.passed)
            and _summary_int(successor_summary, "effective_leaf_count") > 0
            if successor_chain_evaluation is not None
            else False
        ),
        "successor_effective_leaf_count": _summary_int(
            successor_summary,
            "effective_leaf_count",
        ),
        "successor_active_edge_count": _summary_int(
            successor_summary,
            "active_edge_count",
        ),
        "successor_critical_issue_count": _summary_int(
            successor_summary,
            "chain_integrity_critical_issue_count",
        ),
        "successor_ambiguous_source_count": _summary_int(
            successor_summary,
            "ambiguous_successor_source_count",
        ),
        "successor_source_status_sync_required_count": _summary_int(
            successor_summary,
            "source_status_sync_required_count",
        ),
        "market_movement_runtime_replay_present": (
            market_movement_runtime_replay is not None
        ),
        "market_movement_runtime_replay_passed": (
            market_movement_runtime_replay.passed
            if market_movement_runtime_replay is not None
            else None
        ),
        "market_movement_runtime_replay_report_path": (
            str(market_movement_runtime_replay_report_path)
            if market_movement_runtime_replay_report_path is not None
            else None
        ),
        "market_movement_runtime_replay_key": _summary_str(
            market_movement_summary,
            "report_key",
        ),
        "market_movement_runtime_replay_status": _summary_str(
            market_movement_summary,
            "status",
        ),
        "market_movement_runtime_replay_allowed": _summary_bool(
            market_movement_summary,
            "runtime_shadow_replay_allowed",
        ),
        "market_movement_runtime_replay_holdout_allowed": _summary_bool(
            market_movement_summary,
            "holdout_replay_allowed",
        ),
        "market_movement_runtime_replay_rule_count": _summary_int(
            market_movement_summary,
            "rule_count",
        ),
        "market_movement_runtime_replay_selected_rule_count": _summary_int(
            market_movement_summary,
            "selected_rule_count",
        ),
        "market_movement_runtime_replay_candidate_count": _summary_int(
            market_movement_summary,
            "candidate_count",
        ),
        "market_movement_runtime_replay_accepted_count": _summary_int(
            market_movement_summary,
            "accepted_count",
        ),
        "market_movement_runtime_replay_adjusted_fixture_count": _summary_int(
            market_movement_summary,
            "adjusted_fixture_count",
        ),
        "market_movement_runtime_replay_adjusted_prediction_count": _summary_int(
            market_movement_summary,
            "adjusted_prediction_count",
        ),
        "market_movement_runtime_replay_final_hit_rate_delta": _summary_number(
            market_movement_summary,
            "final_hit_rate_delta",
        ),
        "market_movement_runtime_replay_roi_delta": _summary_number(
            market_movement_summary,
            "roi_delta",
        ),
        "market_movement_runtime_replay_profit_loss_delta": _summary_number(
            market_movement_summary,
            "profit_loss_delta",
        ),
        "market_movement_runtime_replay_brier_score_delta": _summary_number(
            market_movement_summary,
            "brier_score_delta",
        ),
        "market_movement_runtime_replay_log_loss_delta": _summary_number(
            market_movement_summary,
            "log_loss_delta",
        ),
        "market_movement_runtime_replay_mean_calibration_error_delta": (
            _summary_number(
                market_movement_summary,
                "mean_calibration_error_delta",
            )
        ),
        "market_movement_runtime_replay_production_changed": _summary_bool(
            market_movement_summary,
            "production_recommendation_changed",
        ),
        "market_movement_runtime_replay_public_changed": _summary_bool(
            market_movement_summary,
            "public_response_changed",
        ),
        "candidate_upset_opportunity_count": _summary_int(
            suite.summary_json,
            "candidate_upset_opportunity_count",
        ),
        "candidate_upset_capture_rate": _summary_number(
            suite.summary_json,
            "candidate_upset_capture_rate",
        ),
        "upset_exposure_reserve": suite.summary_json.get("upset_exposure_reserve"),
        "upset_exposure_reserve_fixture_count": suite.summary_json.get(
            "upset_exposure_reserve_fixture_count"
        ),
        "candidate_candidate_pool_upset_exposure_reserve_candidate_count": (
            _summary_int(
                suite.summary_json,
                "candidate_candidate_pool_upset_exposure_reserve_candidate_count",
            )
        ),
        "candidate_final_answer_upset_exposure_reserve_selected_candidate_count": (
            _summary_int(
                suite.summary_json,
                "candidate_final_answer_upset_exposure_reserve_selected_candidate_count",
            )
        ),
        "upset_final_answer_lane": suite.summary_json.get("upset_final_answer_lane"),
        "upset_final_answer_lane_pass_type": suite.summary_json.get(
            "upset_final_answer_lane_pass_type"
        ),
        "upset_final_answer_lane_mode": suite.summary_json.get("upset_final_answer_lane_mode"),
        "upset_final_answer_lane_candidate_limit": suite.summary_json.get(
            "upset_final_answer_lane_candidate_limit"
        ),
        "upset_final_answer_lane_min_protection_score": suite.summary_json.get(
            "upset_final_answer_lane_min_protection_score"
        ),
        "upset_final_answer_lane_min_probability": suite.summary_json.get(
            "upset_final_answer_lane_min_probability"
        ),
        "upset_final_answer_lane_min_decimal_odds": suite.summary_json.get(
            "upset_final_answer_lane_min_decimal_odds"
        ),
        "upset_final_answer_lane_max_decimal_odds": suite.summary_json.get(
            "upset_final_answer_lane_max_decimal_odds"
        ),
        "upset_final_answer_lane_min_model_edge": suite.summary_json.get(
            "upset_final_answer_lane_min_model_edge"
        ),
        "upset_final_answer_lane_max_model_edge": suite.summary_json.get(
            "upset_final_answer_lane_max_model_edge"
        ),
        "upset_final_answer_lane_competition_ids": suite.summary_json.get(
            "upset_final_answer_lane_competition_ids"
        ),
        "upset_final_answer_lane_excluded_competition_ids": suite.summary_json.get(
            "upset_final_answer_lane_excluded_competition_ids"
        ),
        "upset_final_answer_lane_min_calibration_score": suite.summary_json.get(
            "upset_final_answer_lane_min_calibration_score"
        ),
        "upset_final_answer_lane_min_model_confidence_score": suite.summary_json.get(
            "upset_final_answer_lane_min_model_confidence_score"
        ),
        "upset_final_answer_lane_min_odds_stability_score": suite.summary_json.get(
            "upset_final_answer_lane_min_odds_stability_score"
        ),
        "upset_final_answer_lane_max_volatility_penalty": suite.summary_json.get(
            "upset_final_answer_lane_max_volatility_penalty"
        ),
        "upset_final_answer_lane_max_hit_probability_deficit": (
            suite.summary_json.get("upset_final_answer_lane_max_hit_probability_deficit")
        ),
        "upset_final_answer_lane_max_signal_calibration_risk": (
            suite.summary_json.get("upset_final_answer_lane_max_signal_calibration_risk")
        ),
        "upset_final_answer_lane_min_signal_reliability_score": (
            suite.summary_json.get("upset_final_answer_lane_min_signal_reliability_score")
        ),
        "upset_final_answer_lane_score_boost": suite.summary_json.get(
            "upset_final_answer_lane_score_boost"
        ),
        "candidate_upset_final_answer_lane_candidate_count": _summary_int(
            suite.summary_json,
            "candidate_upset_final_answer_lane_candidate_count",
        ),
        "candidate_candidate_pool_upset_final_answer_lane_candidate_count": (
            _summary_int(
                suite.summary_json,
                "candidate_candidate_pool_upset_final_answer_lane_candidate_count",
            )
        ),
        "candidate_completed_upset_final_answer_lane_count": _summary_int(
            suite.summary_json,
            "candidate_completed_upset_final_answer_lane_count",
        ),
        "candidate_final_answer_upset_final_answer_lane_count": _summary_int(
            suite.summary_json,
            "candidate_final_answer_upset_final_answer_lane_count",
        ),
        "candidate_final_answer_upset_final_answer_lane_selected_candidate_count": (
            _summary_int(
                suite.summary_json,
                "candidate_final_answer_upset_final_answer_lane_selected_candidate_count",
            )
        ),
        "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count": (
            _summary_int(
                suite.summary_json,
                "candidate_upset_final_answer_lane_calibration_guard_blocked_option_count",
            )
        ),
        "aggregate_deltas": suite.aggregate_deltas_json,
        "failed_checks": failed_checks,
        "warnings": list(warnings),
    }


def _lifecycle_quality_cycle_present_check(
    lifecycle_quality_cycle: HistoricalRecommendationLifecycleQualityCycleEvidence | None,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if not options.require_lifecycle_quality_cycle:
        return _skipped_check(
            name="lifecycle_quality_cycle_present",
            actual=lifecycle_quality_cycle is not None,
            detail="lifecycle quality-cycle evidence is optional for this suite gate",
        )
    return HistoricalRecommendationSuiteQualityGateCheck(
        name="lifecycle_quality_cycle_present",
        status="passed" if lifecycle_quality_cycle is not None else "failed",
        actual=lifecycle_quality_cycle is not None,
        threshold=True,
        detail=(
            "candidate lifecycle quality-cycle evidence must be attached before "
            "this historical suite can pass"
        ),
    )


def _lifecycle_quality_cycle_checks(
    lifecycle_quality_cycle: HistoricalRecommendationLifecycleQualityCycleEvidence | None,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> list[HistoricalRecommendationSuiteQualityGateCheck]:
    if lifecycle_quality_cycle is None:
        return []
    summary = lifecycle_quality_cycle.summary_json
    return [
        HistoricalRecommendationSuiteQualityGateCheck(
            name="lifecycle_quality_cycle_passed",
            status="passed" if lifecycle_quality_cycle.passed else "failed",
            actual=lifecycle_quality_cycle.passed,
            threshold=True,
            detail="candidate lifecycle quality cycle should pass",
        ),
        _required_bool_check(
            name="lifecycle_persisted_smoke_present",
            actual=bool(summary.get("persisted_lifecycle_smoke_present", False)),
            required=options.require_lifecycle_persisted_smoke,
            detail="candidate lifecycle gate should include persisted smoke evidence",
        ),
        _required_bool_check(
            name="lifecycle_persisted_smoke_passed",
            actual=bool(summary.get("persisted_lifecycle_smoke_passed", False)),
            required=options.require_lifecycle_persisted_smoke,
            detail="candidate persisted lifecycle smoke should pass",
        ),
        _required_bool_check(
            name="lifecycle_source_status_synced",
            actual=bool(summary.get("persisted_lifecycle_source_status_synced", False)),
            required=options.require_lifecycle_source_status_synced,
            detail="candidate source run should be superseded after successor generation",
        ),
        _check_minimum(
            name="lifecycle_effective_leaf_count",
            actual=_summary_int(summary, "persisted_lifecycle_effective_leaf_count"),
            threshold=options.min_lifecycle_effective_leaf_count,
            detail="candidate lifecycle evidence should include enough effective leaf runs",
        ),
        _check_minimum(
            name="lifecycle_active_edge_count",
            actual=_summary_int(summary, "persisted_lifecycle_active_edge_count"),
            threshold=options.min_lifecycle_active_edge_count,
            detail="candidate lifecycle evidence should include enough active successor edges",
        ),
        _check_optional_maximum(
            name="lifecycle_critical_issue_count",
            actual=_summary_int(summary, "persisted_lifecycle_critical_issue_count"),
            threshold=options.max_lifecycle_critical_issue_count,
            detail="candidate lifecycle critical issues should stay within the limit",
        ),
        _check_optional_maximum(
            name="lifecycle_source_status_sync_required_count",
            actual=_summary_int(
                summary,
                "persisted_lifecycle_source_status_sync_required_count",
            ),
            threshold=options.max_lifecycle_source_status_sync_required_count,
            detail=("candidate lifecycle source-status sync debt should stay within the limit"),
        ),
    ]


def _successor_chain_evaluation_checks(
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ),
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> list[HistoricalRecommendationSuiteQualityGateCheck]:
    checks = [
        _successor_chain_evaluation_present_check(
            successor_chain_evaluation,
            options=options,
        )
    ]
    if successor_chain_evaluation is None:
        return checks
    summary = successor_chain_evaluation.summary_json
    checks.extend(
        [
            HistoricalRecommendationSuiteQualityGateCheck(
                name="successor_chain_evaluation_passed",
                status="passed" if successor_chain_evaluation.passed else "failed",
                actual=successor_chain_evaluation.passed,
                threshold=True,
                detail="successor-chain evaluation should pass",
            ),
            _check_minimum(
                name="successor_effective_leaf_count",
                actual=_summary_int(summary, "effective_leaf_count"),
                threshold=options.min_successor_effective_leaf_count,
                detail=(
                    "successor-chain evidence should include enough final "
                    "effective leaf runs"
                ),
            ),
            _check_minimum(
                name="successor_active_edge_count",
                actual=_summary_int(summary, "active_edge_count"),
                threshold=options.min_successor_active_edge_count,
                detail=(
                    "successor-chain evidence should include enough active "
                    "source->successor edges"
                ),
            ),
            _check_optional_maximum(
                name="successor_critical_issue_count",
                actual=_summary_int(summary, "chain_integrity_critical_issue_count"),
                threshold=options.max_successor_critical_issue_count,
                detail="successor-chain critical issues should stay within the limit",
            ),
            _check_optional_maximum(
                name="successor_ambiguous_source_count",
                actual=_summary_int(summary, "ambiguous_successor_source_count"),
                threshold=options.max_successor_ambiguous_source_count,
                detail=(
                    "ambiguous successor sources should stay within the configured "
                    "limit"
                ),
            ),
            _check_optional_maximum(
                name="successor_source_status_sync_required_count",
                actual=_summary_int(summary, "source_status_sync_required_count"),
                threshold=options.max_successor_source_status_sync_required_count,
                detail=(
                    "successor source-status sync debt should stay within the "
                    "configured limit"
                ),
            ),
        ]
    )
    return checks


def _successor_chain_evaluation_present_check(
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ),
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if not options.require_successor_chain_evaluation:
        return _skipped_check(
            name="successor_chain_evaluation_present",
            actual=successor_chain_evaluation is not None,
            detail="successor-chain evaluation evidence is optional for this suite gate",
        )
    return HistoricalRecommendationSuiteQualityGateCheck(
        name="successor_chain_evaluation_present",
        status="passed" if successor_chain_evaluation is not None else "failed",
        actual=successor_chain_evaluation is not None,
        threshold=True,
        detail=(
            "successor-chain evaluation evidence must be attached before this "
            "historical suite can pass"
        ),
    )


def _market_movement_runtime_replay_checks(
    market_movement_runtime_replay: HistoricalMarketMovementRuntimeReplayEvidence | None,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> list[HistoricalRecommendationSuiteQualityGateCheck]:
    checks = [
        _market_movement_runtime_replay_present_check(
            market_movement_runtime_replay,
            options=options,
        )
    ]
    if market_movement_runtime_replay is None:
        return checks
    summary = market_movement_runtime_replay.summary_json
    checks.extend(
        [
            HistoricalRecommendationSuiteQualityGateCheck(
                name="market_movement_runtime_replay_passed",
                status=(
                    "passed" if market_movement_runtime_replay.passed else "failed"
                ),
                actual=market_movement_runtime_replay.passed,
                threshold=True,
                detail="market-movement runtime replay evidence should pass",
            ),
            _required_bool_check(
                name="market_movement_runtime_replay_allowed",
                actual=_summary_bool(summary, "runtime_shadow_replay_allowed"),
                required=options.require_market_movement_runtime_replay_allowed,
                detail="market-movement runtime replay should be shadow-allowed",
            ),
            _required_bool_check(
                name="market_movement_runtime_replay_passed_status",
                actual=_summary_str(summary, "status")
                == "runtime_shadow_replay_passed",
                required=options.require_market_movement_runtime_replay_passed_status,
                detail="market-movement runtime replay status should be the pass status",
            ),
            _check_minimum(
                name="market_movement_runtime_replay_rule_count",
                actual=_summary_int(summary, "rule_count"),
                threshold=options.min_market_movement_runtime_replay_rule_count,
                detail="market-movement runtime replay should load enough rules",
            ),
            _check_minimum(
                name="market_movement_runtime_replay_selected_rule_count",
                actual=_summary_int(summary, "selected_rule_count"),
                threshold=(
                    options.min_market_movement_runtime_replay_selected_rule_count
                ),
                detail="market-movement runtime replay should select enough rules",
            ),
            _check_minimum(
                name="market_movement_runtime_replay_accepted_count",
                actual=_summary_int(summary, "accepted_count"),
                threshold=options.min_market_movement_runtime_replay_accepted_count,
                detail="market-movement runtime replay should accept enough segments",
            ),
            _check_minimum(
                name="market_movement_runtime_replay_adjusted_fixture_count",
                actual=_summary_int(summary, "adjusted_fixture_count"),
                threshold=(
                    options.min_market_movement_runtime_replay_adjusted_fixture_count
                ),
                detail="market-movement runtime replay should adjust enough fixtures",
            ),
            _check_minimum(
                name="market_movement_runtime_replay_adjusted_prediction_count",
                actual=_summary_int(summary, "adjusted_prediction_count"),
                threshold=(
                    options.min_market_movement_runtime_replay_adjusted_prediction_count
                ),
                detail="market-movement runtime replay should adjust enough predictions",
            ),
            _check_optional_minimum(
                name="market_movement_runtime_replay_final_hit_rate_delta",
                actual=_summary_number(summary, "final_hit_rate_delta"),
                threshold=(
                    options.min_market_movement_runtime_replay_final_hit_rate_delta
                ),
                detail="market-movement runtime replay final-hit rate should not regress",
            ),
            _check_optional_minimum(
                name="market_movement_runtime_replay_roi_delta",
                actual=_summary_number(summary, "roi_delta"),
                threshold=options.min_market_movement_runtime_replay_roi_delta,
                detail="market-movement runtime replay ROI should not regress",
            ),
            _check_optional_minimum(
                name="market_movement_runtime_replay_profit_loss_delta",
                actual=_summary_number(summary, "profit_loss_delta"),
                threshold=options.min_market_movement_runtime_replay_profit_loss_delta,
                detail="market-movement runtime replay profit/loss should not regress",
            ),
            _check_optional_maximum(
                name="market_movement_runtime_replay_brier_score_delta",
                actual=_summary_number(summary, "brier_score_delta"),
                threshold=(
                    options.max_market_movement_runtime_replay_brier_score_delta
                ),
                detail="market-movement runtime replay Brier score should not regress",
            ),
            _check_optional_maximum(
                name="market_movement_runtime_replay_log_loss_delta",
                actual=_summary_number(summary, "log_loss_delta"),
                threshold=options.max_market_movement_runtime_replay_log_loss_delta,
                detail="market-movement runtime replay log loss should not regress",
            ),
            _check_optional_maximum(
                name="market_movement_runtime_replay_mean_calibration_error_delta",
                actual=_summary_number(summary, "mean_calibration_error_delta"),
                threshold=(
                    options.max_market_movement_runtime_replay_mean_calibration_error_delta
                ),
                detail=(
                    "market-movement runtime replay calibration error should not regress"
                ),
            ),
            _required_bool_check(
                name="market_movement_runtime_replay_production_unchanged",
                actual=not _summary_bool(summary, "production_recommendation_changed"),
                required=(
                    options.require_market_movement_runtime_replay_production_unchanged
                ),
                detail="market-movement runtime replay should not change production",
            ),
            _required_bool_check(
                name="market_movement_runtime_replay_public_unchanged",
                actual=not _summary_bool(summary, "public_response_changed"),
                required=(
                    options.require_market_movement_runtime_replay_public_response_unchanged
                ),
                detail="market-movement runtime replay should not change public output",
            ),
        ]
    )
    return checks


def _market_movement_runtime_replay_present_check(
    market_movement_runtime_replay: HistoricalMarketMovementRuntimeReplayEvidence | None,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if not options.require_market_movement_runtime_replay:
        return _skipped_check(
            name="market_movement_runtime_replay_present",
            actual=market_movement_runtime_replay is not None,
            detail="market-movement runtime replay evidence is optional for this suite gate",
        )
    return HistoricalRecommendationSuiteQualityGateCheck(
        name="market_movement_runtime_replay_present",
        status="passed" if market_movement_runtime_replay is not None else "failed",
        actual=market_movement_runtime_replay is not None,
        threshold=True,
        detail=(
            "market-movement runtime replay evidence must be attached before "
            "this historical suite can pass"
        ),
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run a frozen historical suite and enforce accuracy quality gates."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument(
        "--suite-manifest",
        type=Path,
        action="append",
        default=[],
        help="Load historical slice paths from a suite manifest JSON file.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Write the quality gate report JSON to this path.",
    )
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
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
    parser.add_argument("--allowed-markets", default="1x2")
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--upset-exposure-reserve", action="store_true")
    parser.add_argument("--upset-exposure-reserve-fixture-count", type=int, default=0)
    parser.add_argument(
        "--upset-exposure-reserve-max-candidates-per-fixture",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-exposure-reserve-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-exposure-reserve-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane", action="store_true")
    parser.add_argument("--upset-final-answer-lane-pass-type", default="1x1")
    parser.add_argument(
        "--upset-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--upset-final-answer-lane-candidate-limit", type=int, default=24)
    parser.add_argument(
        "--upset-final-answer-lane-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-final-answer-lane-min-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-min-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-max-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-competitions", default="")
    parser.add_argument("--upset-final-answer-lane-excluded-competitions", default="")
    parser.add_argument(
        "--upset-final-answer-lane-min-calibration-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-model-confidence-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-odds-stability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-max-volatility-penalty", type=float)
    parser.add_argument(
        "--upset-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-max-signal-calibration-risk",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-signal-reliability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-score-boost", type=float, default=0.0)
    parser.add_argument("--short-price-negative-edge-guardrail", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--short-price-negative-edge-min-probability",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--short-price-negative-edge-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument("--short-price-negative-edge-soft-penalty", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-strength",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-competitions",
        default="",
    )
    parser.add_argument("--final-answer-quality-signal-penalty", action="store_true")
    parser.add_argument(
        "--final-answer-quality-signal-penalty-strength",
        type=float,
        default=0.04,
    )
    parser.add_argument(
        "--final-answer-quality-signal-probability-min",
        type=float,
        default=0.65,
    )
    parser.add_argument(
        "--final-answer-quality-signal-probability-max",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--final-answer-quality-signal-min-decimal-odds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--final-answer-quality-signal-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-score-min",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-score-max",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--final-answer-quality-signal-competitions",
        default="",
    )
    parser.add_argument("--correct-score-final-answer-lane", action="store_true")
    parser.add_argument("--correct-score-final-answer-lane-pass-types", default="2x1")
    parser.add_argument(
        "--correct-score-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--correct-score-final-answer-lane-modes", default="")
    parser.add_argument(
        "--correct-score-final-answer-lane-candidate-limit",
        type=int,
        default=96,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-min-probability",
        type=float,
        default=0.005,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-min-correct-score-probability",
        type=float,
        default=0.02,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-max-correct-score-per-selection",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-score-boost",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--correct-score-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument("--correct-score-final-answer-lane-min-roi-delta", type=float)
    parser.add_argument("--correct-score-final-answer-lane-outcomes", default="")
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
    parser.add_argument("--min-slice-count", type=int, default=1)
    parser.add_argument("--min-comparison-count", type=int, default=1)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--min-final-hit-coverage-ratio", type=float, default=None)
    parser.add_argument("--min-candidate-final-hit-rate", type=float, default=None)
    parser.add_argument("--min-candidate-roi", type=float, default=None)
    parser.add_argument("--min-competition-candidate-roi", type=float, default=None)
    parser.add_argument("--max-final-answer-correlation-exposure", type=int, default=None)
    parser.add_argument(
        "--min-candidate-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-candidate-dynamic-mixed-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument(
        "--min-candidate-handicap-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-candidate-correct-score-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-candidate-multiple-choice-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=None)
    parser.add_argument("--min-profit-loss-delta", type=float, default=None)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--profile-reference-no-upset-lane", action="store_true")
    parser.add_argument("--profile-reference-no-correct-score-lane", action="store_true")
    parser.add_argument("--lifecycle-quality-cycle-report-path", type=Path)
    parser.add_argument("--require-lifecycle-quality-cycle", action="store_true")
    parser.add_argument("--allow-missing-lifecycle-persisted-smoke", action="store_true")
    parser.add_argument("--allow-unsynced-lifecycle-source-status", action="store_true")
    parser.add_argument("--min-lifecycle-effective-leaf-count", type=int, default=0)
    parser.add_argument("--min-lifecycle-active-edge-count", type=int, default=0)
    parser.add_argument("--max-lifecycle-critical-issue-count", type=int, default=0)
    parser.add_argument(
        "--max-lifecycle-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument("--successor-chain-evaluation-report-path", type=Path)
    parser.add_argument("--require-successor-chain-evaluation", action="store_true")
    parser.add_argument("--min-successor-effective-leaf-count", type=int, default=0)
    parser.add_argument("--min-successor-active-edge-count", type=int, default=0)
    parser.add_argument("--max-successor-critical-issue-count", type=int, default=0)
    parser.add_argument("--max-successor-ambiguous-source-count", type=int, default=0)
    parser.add_argument(
        "--max-successor-source-status-sync-required-count",
        type=int,
        default=0,
    )
    parser.add_argument("--market-movement-runtime-replay-report-path", type=Path)
    parser.add_argument("--require-market-movement-runtime-replay", action="store_true")
    parser.add_argument(
        "--allow-market-movement-runtime-replay-not-allowed",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-replay-non-passed-status",
        action="store_true",
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-selected-rule-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-accepted-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-adjusted-fixture-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-adjusted-prediction-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-final-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-roi-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-market-movement-runtime-replay-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-replay-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-replay-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-market-movement-runtime-replay-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--allow-market-movement-runtime-replay-production-change",
        action="store_true",
    )
    parser.add_argument(
        "--allow-market-movement-runtime-replay-public-change",
        action="store_true",
    )
    parser.add_argument("--min-profile-reference-final-hit-rate-delta", type=float)
    parser.add_argument("--min-profile-reference-roi-delta", type=float)
    parser.add_argument("--min-profile-reference-profit-loss-delta", type=float)
    parser.add_argument("--max-profile-reference-brier-score-delta", type=float)
    parser.add_argument("--max-profile-reference-log-loss-delta", type=float)
    parser.add_argument(
        "--max-profile-reference-mean-calibration-error-delta",
        type=float,
    )
    parser.add_argument("--min-profile-reference-upset-capture-rate-delta", type=float)
    parser.add_argument("--min-upset-capture-sample-size", type=int, default=0)
    parser.add_argument("--min-upset-capture-rate-delta", type=float, default=None)
    parser.add_argument(
        "--min-upset-final-answer-lane-selected-candidate-count",
        type=int,
        default=0,
    )
    parser.add_argument("--min-solver-selected-scenario-count", type=int, default=0)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--max-warning-count", type=int, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest: HistoricalRecommendationSuiteManifestLoadResult | None = None
    manifests: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    slices = [load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths]
    manifest_bundles: list[HistoricalRecommendationSuiteManifestLoadResult] = []
    warnings: list[str] = []
    for suite_manifest in args.suite_manifest or []:
        manifest_bundle = load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        manifest_bundles.append(manifest_bundle)
        warnings.extend(manifest_bundle.warnings)
    manifest_slices = [
        historical_slice
        for manifest_bundle in manifest_bundles
        for historical_slice in manifest_bundle.slices
    ]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *slices],
        manifest=manifest_bundles[0] if len(manifest_bundles) == 1 else None,
        manifests=manifest_bundles,
        warnings=warnings,
    )


def _load_lifecycle_quality_cycle(
    path: Path | None,
) -> HistoricalRecommendationLifecycleQualityCycleEvidence | None:
    if path is None:
        return None
    return HistoricalRecommendationLifecycleQualityCycleEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_successor_chain_evaluation(
    path: Path | None,
) -> HistoricalRecommendationSuccessorChainEvaluationEvidence | None:
    if path is None:
        return None
    return HistoricalRecommendationSuccessorChainEvaluationEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_market_movement_runtime_replay(
    path: Path | None,
) -> HistoricalMarketMovementRuntimeReplayEvidence | None:
    if path is None:
        return None
    from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
        HistoricalMarketMovementRiskFilterRuntimeReplayReport,
    )

    report = HistoricalMarketMovementRiskFilterRuntimeReplayReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    summary = {
        **report.summary_json,
        "report_key": report.report_key,
        "status": report.status,
        "runtime_shadow_replay_allowed": report.runtime_shadow_replay_allowed,
        "holdout_replay_allowed": report.holdout_replay_allowed,
        "source_rule_profile_version": report.source_rule_profile_version,
        "rule_count": report.rule_count,
        "selected_rule_count": report.selected_rule_count,
        "candidate_count": report.candidate_count,
        "accepted_count": report.accepted_count,
        "adjusted_fixture_count": report.adjusted_fixture_count,
        "adjusted_prediction_count": report.adjusted_prediction_count,
        "final_hit_rate_delta": report.final_hit_rate_delta,
        "roi_delta": report.roi_delta,
        "profit_loss_delta": report.profit_loss_delta,
        "brier_score_delta": report.brier_score_delta,
        "log_loss_delta": report.log_loss_delta,
        "mean_calibration_error_delta": report.mean_calibration_error_delta,
        "production_recommendation_changed": (
            report.production_recommendation_changed
        ),
        "public_response_changed": report.public_response_changed,
    }
    return HistoricalMarketMovementRuntimeReplayEvidence(
        passed=(
            report.runtime_shadow_replay_allowed
            and report.status == "runtime_shadow_replay_passed"
        ),
        summary_json=summary,
    )


def _manifest_summary(
    manifest_bundle: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_bundle.manifest_path),
        "suite_id": manifest_bundle.manifest.suite_id,
        "name": manifest_bundle.manifest.name,
        "slice_count": len(manifest_bundle.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_bundle.resolved_slice_paths
        ],
        "warnings": manifest_bundle.warnings,
    }


def _backtest_options_from_args(args: Namespace) -> HistoricalRecommendationBacktestOptions:
    return HistoricalRecommendationBacktestOptions(
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        strategy=cast(RecommendationStrategy, args.strategy),
        unit_stake=args.unit_stake,
        max_budget=args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        allowed_markets=tuple(
            cast(RecommendationMarketType, market)
            for market in _csv(args.allowed_markets)
        ),
        max_outcomes_per_fixture=args.max_outcomes_per_fixture,
        upset_threshold=args.upset_threshold,
        candidate_fixture_limit=args.candidate_fixture_limit,
        max_candidates_per_fixture=args.max_candidates_per_fixture,
        scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
        final_answer_scenario_variant_count=(
            args.final_answer_scenario_variant_count
        ),
        derive_market_context_signals=args.derive_market_context_signals,
        upset_exposure_reserve=args.upset_exposure_reserve,
        upset_exposure_reserve_fixture_count=(args.upset_exposure_reserve_fixture_count),
        upset_exposure_reserve_max_candidates_per_fixture=(
            args.upset_exposure_reserve_max_candidates_per_fixture
        ),
        upset_exposure_reserve_min_protection_score=(
            args.upset_exposure_reserve_min_protection_score
        ),
        upset_exposure_reserve_min_probability=(args.upset_exposure_reserve_min_probability),
        upset_exposure_reserve_max_decimal_odds=(args.upset_exposure_reserve_max_decimal_odds),
        upset_final_answer_lane=args.upset_final_answer_lane,
        upset_final_answer_lane_pass_type=args.upset_final_answer_lane_pass_type,
        upset_final_answer_lane_mode=cast(
            RecommendationMode,
            args.upset_final_answer_lane_mode,
        ),
        upset_final_answer_lane_candidate_limit=(args.upset_final_answer_lane_candidate_limit),
        upset_final_answer_lane_min_protection_score=(
            args.upset_final_answer_lane_min_protection_score
        ),
        upset_final_answer_lane_min_probability=(args.upset_final_answer_lane_min_probability),
        upset_final_answer_lane_min_decimal_odds=(args.upset_final_answer_lane_min_decimal_odds),
        upset_final_answer_lane_max_decimal_odds=(args.upset_final_answer_lane_max_decimal_odds),
        upset_final_answer_lane_min_model_edge=(args.upset_final_answer_lane_min_model_edge),
        upset_final_answer_lane_max_model_edge=(args.upset_final_answer_lane_max_model_edge),
        upset_final_answer_lane_competition_ids=tuple(
            _csv(args.upset_final_answer_lane_competitions)
        ),
        upset_final_answer_lane_excluded_competition_ids=tuple(
            _csv(args.upset_final_answer_lane_excluded_competitions)
        ),
        upset_final_answer_lane_min_calibration_score=(
            args.upset_final_answer_lane_min_calibration_score
        ),
        upset_final_answer_lane_min_model_confidence_score=(
            args.upset_final_answer_lane_min_model_confidence_score
        ),
        upset_final_answer_lane_min_odds_stability_score=(
            args.upset_final_answer_lane_min_odds_stability_score
        ),
        upset_final_answer_lane_max_volatility_penalty=(
            args.upset_final_answer_lane_max_volatility_penalty
        ),
        upset_final_answer_lane_max_hit_probability_deficit=(
            args.upset_final_answer_lane_max_hit_probability_deficit
        ),
        upset_final_answer_lane_max_signal_calibration_risk=(
            args.upset_final_answer_lane_max_signal_calibration_risk
        ),
        upset_final_answer_lane_min_signal_reliability_score=(
            args.upset_final_answer_lane_min_signal_reliability_score
        ),
        upset_final_answer_lane_score_boost=args.upset_final_answer_lane_score_boost,
        short_price_negative_edge_guardrail=args.short_price_negative_edge_guardrail,
        short_price_negative_edge_max_decimal_odds=(
            args.short_price_negative_edge_max_decimal_odds
        ),
        short_price_negative_edge_min_probability=(args.short_price_negative_edge_min_probability),
        short_price_negative_edge_max_model_edge=(args.short_price_negative_edge_max_model_edge),
        short_price_negative_edge_soft_penalty=(args.short_price_negative_edge_soft_penalty),
        short_price_negative_edge_soft_penalty_strength=(
            args.short_price_negative_edge_soft_penalty_strength
        ),
        short_price_negative_edge_soft_penalty_competition_ids=tuple(
            _csv(args.short_price_negative_edge_soft_penalty_competitions)
        ),
        final_answer_quality_signal_penalty=(args.final_answer_quality_signal_penalty),
        final_answer_quality_signal_penalty_strength=(
            args.final_answer_quality_signal_penalty_strength
        ),
        final_answer_quality_signal_probability_min=(
            args.final_answer_quality_signal_probability_min
        ),
        final_answer_quality_signal_probability_max=(
            args.final_answer_quality_signal_probability_max
        ),
        final_answer_quality_signal_min_decimal_odds=(
            args.final_answer_quality_signal_min_decimal_odds
        ),
        final_answer_quality_signal_max_decimal_odds=(
            args.final_answer_quality_signal_max_decimal_odds
        ),
        final_answer_quality_signal_max_model_edge=(
            args.final_answer_quality_signal_max_model_edge
        ),
        final_answer_quality_signal_score_min=(args.final_answer_quality_signal_score_min),
        final_answer_quality_signal_score_max=(args.final_answer_quality_signal_score_max),
        final_answer_quality_signal_competition_ids=tuple(
            _csv(args.final_answer_quality_signal_competitions)
        ),
        correct_score_final_answer_lane=args.correct_score_final_answer_lane,
        correct_score_final_answer_lane_pass_types=tuple(
            _csv(args.correct_score_final_answer_lane_pass_types)
        ),
        correct_score_final_answer_lane_mode=cast(
            RecommendationMode,
            args.correct_score_final_answer_lane_mode,
        ),
        correct_score_final_answer_lane_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.correct_score_final_answer_lane_modes)
        ),
        correct_score_final_answer_lane_candidate_limit=(
            args.correct_score_final_answer_lane_candidate_limit
        ),
        correct_score_final_answer_lane_min_probability=(
            args.correct_score_final_answer_lane_min_probability
        ),
        correct_score_final_answer_lane_min_correct_score_probability=(
            args.correct_score_final_answer_lane_min_correct_score_probability
        ),
        correct_score_final_answer_lane_max_correct_score_per_selection=(
            args.correct_score_final_answer_lane_max_correct_score_per_selection
        ),
        correct_score_final_answer_lane_score_boost=(
            args.correct_score_final_answer_lane_score_boost
        ),
        correct_score_final_answer_lane_max_hit_probability_deficit=(
            args.correct_score_final_answer_lane_max_hit_probability_deficit
        ),
        correct_score_final_answer_lane_min_roi_delta=(
            args.correct_score_final_answer_lane_min_roi_delta
        ),
        correct_score_final_answer_lane_outcomes=tuple(
            _csv(args.correct_score_final_answer_lane_outcomes)
        ),
    )


def _options_from_args(args: Namespace) -> HistoricalRecommendationSuiteQualityGateOptions:
    return HistoricalRecommendationSuiteQualityGateOptions(
        min_slice_count=args.min_slice_count,
        min_comparison_count=args.min_comparison_count,
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_final_hit_coverage_ratio=args.min_final_hit_coverage_ratio,
        min_candidate_final_hit_rate=args.min_candidate_final_hit_rate,
        min_candidate_roi=args.min_candidate_roi,
        min_competition_candidate_roi=args.min_competition_candidate_roi,
        max_final_answer_correlation_exposure=(args.max_final_answer_correlation_exposure),
        min_candidate_dynamic_mixed_final_answer_count=(
            args.min_candidate_dynamic_mixed_final_answer_count
        ),
        min_candidate_dynamic_mixed_final_answer_rate=(
            args.min_candidate_dynamic_mixed_final_answer_rate
        ),
        min_candidate_handicap_final_answer_count=(
            args.min_candidate_handicap_final_answer_count
        ),
        min_candidate_correct_score_final_answer_count=(
            args.min_candidate_correct_score_final_answer_count
        ),
        min_candidate_multiple_choice_final_answer_count=(
            args.min_candidate_multiple_choice_final_answer_count
        ),
        fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        min_profile_reference_final_hit_rate_delta=(
            args.min_profile_reference_final_hit_rate_delta
        ),
        min_profile_reference_roi_delta=args.min_profile_reference_roi_delta,
        min_profile_reference_profit_loss_delta=(args.min_profile_reference_profit_loss_delta),
        max_profile_reference_brier_score_delta=(args.max_profile_reference_brier_score_delta),
        max_profile_reference_log_loss_delta=(args.max_profile_reference_log_loss_delta),
        max_profile_reference_mean_calibration_error_delta=(
            args.max_profile_reference_mean_calibration_error_delta
        ),
        min_profile_reference_upset_capture_rate_delta=(
            args.min_profile_reference_upset_capture_rate_delta
        ),
        min_upset_capture_sample_size=args.min_upset_capture_sample_size,
        min_upset_capture_rate_delta=args.min_upset_capture_rate_delta,
        min_upset_final_answer_lane_selected_candidate_count=(
            args.min_upset_final_answer_lane_selected_candidate_count
        ),
        min_solver_selected_scenario_count=args.min_solver_selected_scenario_count,
        min_final_answer_changed_count=args.min_final_answer_changed_count,
        require_lifecycle_quality_cycle=args.require_lifecycle_quality_cycle,
        require_lifecycle_persisted_smoke=(not args.allow_missing_lifecycle_persisted_smoke),
        require_lifecycle_source_status_synced=(not args.allow_unsynced_lifecycle_source_status),
        min_lifecycle_effective_leaf_count=args.min_lifecycle_effective_leaf_count,
        min_lifecycle_active_edge_count=args.min_lifecycle_active_edge_count,
        max_lifecycle_critical_issue_count=args.max_lifecycle_critical_issue_count,
        max_lifecycle_source_status_sync_required_count=(
            args.max_lifecycle_source_status_sync_required_count
        ),
        require_successor_chain_evaluation=args.require_successor_chain_evaluation,
        min_successor_effective_leaf_count=args.min_successor_effective_leaf_count,
        min_successor_active_edge_count=args.min_successor_active_edge_count,
        max_successor_critical_issue_count=args.max_successor_critical_issue_count,
        max_successor_ambiguous_source_count=args.max_successor_ambiguous_source_count,
        max_successor_source_status_sync_required_count=(
            args.max_successor_source_status_sync_required_count
        ),
        require_market_movement_runtime_replay=(
            args.require_market_movement_runtime_replay
        ),
        require_market_movement_runtime_replay_allowed=(
            not args.allow_market_movement_runtime_replay_not_allowed
        ),
        require_market_movement_runtime_replay_passed_status=(
            not args.allow_market_movement_runtime_replay_non_passed_status
        ),
        min_market_movement_runtime_replay_rule_count=(
            args.min_market_movement_runtime_replay_rule_count
        ),
        min_market_movement_runtime_replay_selected_rule_count=(
            args.min_market_movement_runtime_replay_selected_rule_count
        ),
        min_market_movement_runtime_replay_accepted_count=(
            args.min_market_movement_runtime_replay_accepted_count
        ),
        min_market_movement_runtime_replay_adjusted_fixture_count=(
            args.min_market_movement_runtime_replay_adjusted_fixture_count
        ),
        min_market_movement_runtime_replay_adjusted_prediction_count=(
            args.min_market_movement_runtime_replay_adjusted_prediction_count
        ),
        min_market_movement_runtime_replay_final_hit_rate_delta=(
            args.min_market_movement_runtime_replay_final_hit_rate_delta
        ),
        min_market_movement_runtime_replay_roi_delta=(
            args.min_market_movement_runtime_replay_roi_delta
        ),
        min_market_movement_runtime_replay_profit_loss_delta=(
            args.min_market_movement_runtime_replay_profit_loss_delta
        ),
        max_market_movement_runtime_replay_brier_score_delta=(
            args.max_market_movement_runtime_replay_brier_score_delta
        ),
        max_market_movement_runtime_replay_log_loss_delta=(
            args.max_market_movement_runtime_replay_log_loss_delta
        ),
        max_market_movement_runtime_replay_mean_calibration_error_delta=(
            args.max_market_movement_runtime_replay_mean_calibration_error_delta
        ),
        require_market_movement_runtime_replay_production_unchanged=(
            not args.allow_market_movement_runtime_replay_production_change
        ),
        require_market_movement_runtime_replay_public_response_unchanged=(
            not args.allow_market_movement_runtime_replay_public_change
        ),
        max_warning_count=args.max_warning_count,
    )


def _check_minimum(
    *,
    name: str,
    actual: int,
    threshold: int,
    detail: str,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    return HistoricalRecommendationSuiteQualityGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_minimum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalRecommendationSuiteQualityGateCheck(
        name=name,
        status=("passed" if actual is not None and actual >= float(threshold) else "failed"),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_maximum(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalRecommendationSuiteQualityGateCheck(
        name=name,
        status=("passed" if actual is not None and actual <= float(threshold) else "failed"),
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if not required:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalRecommendationSuiteQualityGateCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _check_suite_status(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    if not options.fail_on_suite_statuses:
        return _skipped_check(
            name="suite_status",
            actual=suite.status,
            detail="suite status blocking is disabled",
        )
    return HistoricalRecommendationSuiteQualityGateCheck(
        name="suite_status",
        status=("failed" if suite.status in set(options.fail_on_suite_statuses) else "passed"),
        actual=suite.status,
        threshold=",".join(options.fail_on_suite_statuses),
        detail="historical suite status should not be in the configured fail list",
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | None,
    detail: str,
) -> HistoricalRecommendationSuiteQualityGateCheck:
    return HistoricalRecommendationSuiteQualityGateCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _gate_key(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalRecommendationSuiteQualityGateOptions,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None = None,
    lifecycle_quality_cycle: HistoricalRecommendationLifecycleQualityCycleEvidence | None = None,
    successor_chain_evaluation: (
        HistoricalRecommendationSuccessorChainEvaluationEvidence | None
    ) = None,
    market_movement_runtime_replay: (
        HistoricalMarketMovementRuntimeReplayEvidence | None
    ) = None,
) -> str:
    payload = "|".join(
        [
            suite.suite_key,
            reference_suite.suite_key if reference_suite is not None else "",
            str(options.min_slice_count),
            str(options.min_comparison_count),
            str(options.min_final_hit_sample_size),
            str(options.min_final_hit_coverage_ratio),
            str(options.min_candidate_final_hit_rate),
            str(options.min_candidate_roi),
            str(options.min_competition_candidate_roi),
            str(options.max_final_answer_correlation_exposure),
            str(options.min_candidate_dynamic_mixed_final_answer_count),
            str(options.min_candidate_dynamic_mixed_final_answer_rate),
            str(options.min_candidate_handicap_final_answer_count),
            str(options.min_candidate_correct_score_final_answer_count),
            str(options.min_candidate_multiple_choice_final_answer_count),
            ",".join(options.fail_on_suite_statuses),
            str(options.min_final_hit_rate_delta),
            str(options.min_roi_delta),
            str(options.min_profit_loss_delta),
            str(options.max_brier_score_delta),
            str(options.max_log_loss_delta),
            str(options.max_mean_calibration_error_delta),
            str(options.min_profile_reference_final_hit_rate_delta),
            str(options.min_profile_reference_roi_delta),
            str(options.min_profile_reference_profit_loss_delta),
            str(options.max_profile_reference_brier_score_delta),
            str(options.max_profile_reference_log_loss_delta),
            str(options.max_profile_reference_mean_calibration_error_delta),
            str(options.min_profile_reference_upset_capture_rate_delta),
            str(options.min_upset_capture_sample_size),
            str(options.min_upset_capture_rate_delta),
            str(options.min_upset_final_answer_lane_selected_candidate_count),
            str(options.min_solver_selected_scenario_count),
            str(options.min_final_answer_changed_count),
            str(options.require_lifecycle_quality_cycle),
            str(options.require_lifecycle_persisted_smoke),
            str(options.require_lifecycle_source_status_synced),
            str(options.min_lifecycle_effective_leaf_count),
            str(options.min_lifecycle_active_edge_count),
            str(options.max_lifecycle_critical_issue_count),
            str(options.max_lifecycle_source_status_sync_required_count),
            lifecycle_quality_cycle.cycle_key if lifecycle_quality_cycle is not None else "",
            str(lifecycle_quality_cycle.passed if lifecycle_quality_cycle is not None else None),
            str(options.require_successor_chain_evaluation),
            str(options.min_successor_effective_leaf_count),
            str(options.min_successor_active_edge_count),
            str(options.max_successor_critical_issue_count),
            str(options.max_successor_ambiguous_source_count),
            str(options.max_successor_source_status_sync_required_count),
            str(
                successor_chain_evaluation.passed
                if successor_chain_evaluation is not None
                else None
            ),
            str(
                _summary_int(
                    successor_chain_evaluation.summary_json,
                    "effective_leaf_count",
                )
                if successor_chain_evaluation is not None
                else 0
            ),
            str(options.require_market_movement_runtime_replay),
            str(options.require_market_movement_runtime_replay_allowed),
            str(options.require_market_movement_runtime_replay_passed_status),
            str(options.min_market_movement_runtime_replay_rule_count),
            str(options.min_market_movement_runtime_replay_selected_rule_count),
            str(options.min_market_movement_runtime_replay_accepted_count),
            str(options.min_market_movement_runtime_replay_adjusted_fixture_count),
            str(options.min_market_movement_runtime_replay_adjusted_prediction_count),
            str(options.min_market_movement_runtime_replay_final_hit_rate_delta),
            str(options.min_market_movement_runtime_replay_roi_delta),
            str(options.min_market_movement_runtime_replay_profit_loss_delta),
            str(options.max_market_movement_runtime_replay_brier_score_delta),
            str(options.max_market_movement_runtime_replay_log_loss_delta),
            str(
                options.max_market_movement_runtime_replay_mean_calibration_error_delta
            ),
            str(options.require_market_movement_runtime_replay_production_unchanged),
            str(
                options.require_market_movement_runtime_replay_public_response_unchanged
            ),
            str(
                market_movement_runtime_replay.passed
                if market_movement_runtime_replay is not None
                else None
            ),
            str(
                _summary_str(
                    market_movement_runtime_replay.summary_json,
                    "report_key",
                )
                if market_movement_runtime_replay is not None
                else ""
            ),
            str(options.max_warning_count),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_recommendation_suite_quality_gate:{digest}"


def _delta_number(
    suite: HistoricalRecommendationBacktestSuiteResult,
    key: str,
) -> float | None:
    return _object_number(suite.aggregate_deltas_json.get(key))


def _delta_int(
    suite: HistoricalRecommendationBacktestSuiteResult,
    key: str,
) -> int:
    value = suite.aggregate_deltas_json.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _summary_bool(summary: dict[str, object], key: str) -> bool:
    value = summary.get(key)
    return value if isinstance(value, bool) else False


def _summary_str(summary: dict[str, object], key: str) -> str | None:
    value = summary.get(key)
    return value if isinstance(value, str) else None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _summary_number(summary: dict[str, object], key: str) -> float | None:
    return _object_number(summary.get(key))


def _reference_summary_number(
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None,
    key: str,
) -> float | None:
    if reference_suite is None:
        return None
    return _summary_number(reference_suite.summary_json, key)


def _profile_reference_delta_number(
    suite: HistoricalRecommendationBacktestSuiteResult,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None,
    key: str,
) -> float | None:
    candidate_value = _summary_number(suite.summary_json, key)
    reference_value = _reference_summary_number(reference_suite, key)
    if candidate_value is None or reference_value is None:
        return None
    return candidate_value - reference_value


def _profile_reference_bool_disabled(
    suite: HistoricalRecommendationBacktestSuiteResult,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None,
    key: str,
) -> bool:
    return (
        reference_suite is not None
        and suite.summary_json.get(key) is True
        and reference_suite.summary_json.get(key) is False
    )


def _profile_reference_deltas(
    suite: HistoricalRecommendationBacktestSuiteResult,
    reference_suite: HistoricalRecommendationBacktestSuiteResult | None,
) -> dict[str, float | None]:
    return {
        "final_hit_rate_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_final_hit_rate",
        ),
        "roi_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_roi",
        ),
        "profit_loss_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_profit_loss",
        ),
        "brier_score_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_brier_score",
        ),
        "log_loss_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_log_loss",
        ),
        "mean_calibration_error_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_mean_calibration_error",
        ),
        "upset_capture_rate_delta": _profile_reference_delta_number(
            suite,
            reference_suite,
            "candidate_upset_capture_rate",
        ),
    }


def _profile_reference_options_from_args(
    options: HistoricalRecommendationBacktestOptions,
    *,
    args: Namespace,
) -> HistoricalRecommendationBacktestOptions | None:
    if not args.profile_reference_no_upset_lane and not (
        args.profile_reference_no_correct_score_lane
    ):
        return None
    reference_options = options
    if args.profile_reference_no_upset_lane:
        reference_options = _profile_reference_no_upset_lane_options(reference_options)
    if args.profile_reference_no_correct_score_lane:
        reference_options = _profile_reference_no_correct_score_lane_options(
            reference_options
        )
    return reference_options


def _profile_reference_no_upset_lane_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "upset_final_answer_lane": False,
            "upset_final_answer_lane_score_boost": 0.0,
        }
    )


def _profile_reference_no_correct_score_lane_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "correct_score_final_answer_lane": False,
            "correct_score_final_answer_lane_score_boost": 0.0,
        }
    )


def _competition_candidate_roi_map(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> dict[str, float]:
    grouped: dict[str, dict[str, float]] = {}
    for comparison in suite.comparisons:
        competition_id = comparison.candidate.summary_json.get("competition_id")
        if not isinstance(competition_id, str) or not competition_id:
            continue
        row = grouped.setdefault(competition_id, {"stake": 0.0, "return": 0.0})
        row["stake"] += comparison.candidate.total_stake
        row["return"] += comparison.candidate.actual_return
    return {
        competition_id: (
            (totals["return"] - totals["stake"]) / totals["stake"] if totals["stake"] > 0 else 0.0
        )
        for competition_id, totals in sorted(grouped.items())
    }


def _worst_competition_candidate_roi(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> float | None:
    roi_map = _competition_candidate_roi_map(suite)
    if not roi_map:
        return None
    return min(roi_map.values())


def _worst_competition_id(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> str | None:
    roi_map = _competition_candidate_roi_map(suite)
    if not roi_map:
        return None
    return min(roi_map, key=roi_map.__getitem__)


def _max_final_answer_correlation_exposure(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    exposure_counts = _final_answer_correlation_exposure_counts(suite)
    return max(exposure_counts, default=0)


def _correlated_final_answer_count(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for exposure_count in _final_answer_correlation_exposure_counts(suite)
        if exposure_count > 1
    )


def _final_answer_correlation_exposure_counts(
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> list[int]:
    exposure_counts: list[int] = []
    for comparison in suite.comparisons:
        final_answer = comparison.candidate.final_answer
        if final_answer is None or final_answer.option is None:
            continue
        exposure_payload = final_answer.option.selection.evaluation.explanation_json.get(
            "correlation_exposures"
        )
        if not isinstance(exposure_payload, dict):
            exposure_counts.append(0)
            continue
        numeric_counts = [
            int(value) for value in exposure_payload.values() if isinstance(value, int | float)
        ]
        exposure_counts.append(max(numeric_counts, default=0))
    return exposure_counts


def _object_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
