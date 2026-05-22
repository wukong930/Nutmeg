from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalDynamicMixFinalAnswerLaneConstraintProfile,
    HistoricalFinalAnswerStakeEfficiencyScope,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationMarketType,
    RecommendationMode,
    RecommendationStrategy,
)

type HistoricalFinalAnswerMarketConcentrationAuditStatus = Literal["passed", "failed"]
type HistoricalFinalAnswerMarketConcentrationCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]

DEFAULT_FINAL_ANSWER_MARKET_CONCENTRATION_AUDIT_ID = (
    "historical-final-answer-market-concentration-audit-v3.1"
)


class HistoricalFinalAnswerMarketConcentrationAuditOptions(BaseModel):
    audit_id: str = DEFAULT_FINAL_ANSWER_MARKET_CONCENTRATION_AUDIT_ID
    pass_types: tuple[str, ...] = DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES
    modes: tuple[RecommendationMode, ...] = DEFAULT_HISTORICAL_BACKTEST_MODES
    strategy: RecommendationStrategy = "accuracy_first"
    allowed_markets: tuple[RecommendationMarketType, ...] = ("1x2",)
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float = Field(default=20.0, gt=0.0)
    min_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_fixture_limit: int | None = Field(default=None, ge=1)
    max_candidates_per_fixture: int = Field(default=3, ge=1, le=8)
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    scenario_candidate_fixture_buffer: int | None = Field(default=None, ge=0)
    final_answer_scenario_variant_count: int = Field(default=1, ge=1, le=8)
    final_answer_stake_efficiency_guard: bool = False
    final_answer_stake_efficiency_penalty_strength: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
    )
    final_answer_stake_efficiency_max_stake_multiplier: float = Field(
        default=2.0,
        ge=1.0,
    )
    final_answer_stake_efficiency_min_roi: float = 0.0
    final_answer_stake_efficiency_modes: tuple[RecommendationMode, ...] = ("multiple",)
    final_answer_stake_efficiency_scope: HistoricalFinalAnswerStakeEfficiencyScope = (
        "all"
    )
    dynamic_mix_final_answer_lane: bool = False
    dynamic_mix_final_answer_lane_pass_types: tuple[str, ...] = ("2x1",)
    dynamic_mix_final_answer_lane_mode: RecommendationMode = "single"
    dynamic_mix_final_answer_lane_modes: tuple[RecommendationMode, ...] = ()
    dynamic_mix_final_answer_lane_segment_gate_report: Path | None = None
    dynamic_mix_final_answer_lane_admission_gate_report: Path | None = None
    dynamic_mix_final_answer_lane_admitted_pass_types: tuple[str, ...] = ()
    dynamic_mix_final_answer_lane_blocked_pass_types: tuple[str, ...] = ()
    dynamic_mix_final_answer_lane_constraint_profiles: tuple[
        HistoricalDynamicMixFinalAnswerLaneConstraintProfile, ...
    ] = ()
    dynamic_mix_final_answer_lane_min_market_count: int = Field(default=2, ge=2, le=4)
    dynamic_mix_final_answer_lane_candidate_limit: int = Field(default=96, ge=1, le=512)
    dynamic_mix_final_answer_lane_solver_search: bool = False
    dynamic_mix_final_answer_lane_min_probability: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_score_boost: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_max_hit_probability_deficit: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    dynamic_mix_final_answer_lane_min_roi_delta: float | None = None
    correct_score_final_answer_lane: bool = False
    correct_score_final_answer_lane_pass_types: tuple[str, ...] = ("2x1",)
    correct_score_final_answer_lane_mode: RecommendationMode = "single"
    correct_score_final_answer_lane_modes: tuple[RecommendationMode, ...] = ()
    correct_score_final_answer_lane_candidate_limit: int = Field(
        default=96,
        ge=1,
        le=512,
    )
    correct_score_final_answer_lane_min_probability: float = Field(
        default=0.005,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_min_correct_score_probability: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_max_correct_score_per_selection: int = Field(
        default=1,
        ge=1,
        le=3,
    )
    correct_score_final_answer_lane_score_boost: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_max_hit_probability_deficit: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    correct_score_final_answer_lane_min_roi_delta: float | None = None
    correct_score_final_answer_lane_outcomes: tuple[str, ...] = ()
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    slice_limit: int | None = Field(default=None, ge=1)
    min_final_answer_count: int = Field(default=1, ge=0)
    min_market_type_count: int = Field(default=1, ge=0)
    max_dominant_single_market_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_dynamic_mixed_final_answer_count: int = Field(default=0, ge=0)
    min_dynamic_mixed_final_answer_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_correct_score_final_answer_count: int = Field(default=0, ge=0)
    min_multiple_choice_final_answer_count: int = Field(default=0, ge=0)
    min_final_hit_rate_delta: float | None = None
    min_roi_delta: float | None = None
    min_profit_loss_delta: float | None = None
    max_brier_score_delta: float | None = None
    max_log_loss_delta: float | None = None
    max_mean_calibration_error_delta: float | None = None
    top_slice_limit: int = Field(default=20, ge=0, le=200)


class HistoricalFinalAnswerMarketConcentrationCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerMarketConcentrationCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerMarketConcentrationSlice(BaseModel):
    slice_id: str
    competition_id: str | None = None
    final_answer_present: bool
    final_answer_changed: bool
    market_types: list[str] = Field(default_factory=list)
    single_market_type: str | None = None
    dynamic_mixed_market: bool
    scenario_key: str | None = None
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    selected_candidate_count: int = Field(default=0, ge=0)
    multiple_choice_fixture_count: int = Field(default=0, ge=0)
    actual_hit: bool | None = None
    total_stake: float = Field(default=0.0, ge=0.0)
    actual_return: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float | None = None


class HistoricalFinalAnswerMarketConcentrationAuditReport(BaseModel):
    report_key: str
    audit_id: str
    status: HistoricalFinalAnswerMarketConcentrationAuditStatus
    passed: bool
    suite_key: str
    suite_status: str
    slice_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    market_type_count: int = Field(ge=0)
    market_type_counts: dict[str, int] = Field(default_factory=dict)
    market_type_rates: dict[str, float] = Field(default_factory=dict)
    single_market_final_answer_count: int = Field(ge=0)
    single_market_final_answer_rate: float | None = None
    single_market_type_counts: dict[str, int] = Field(default_factory=dict)
    single_market_type_rates: dict[str, float] = Field(default_factory=dict)
    dominant_single_market_type: str | None = None
    dominant_single_market_count: int = Field(default=0, ge=0)
    dominant_single_market_rate: float | None = None
    market_concentration_hhi: float | None = None
    dynamic_mixed_final_answer_count: int = Field(ge=0)
    dynamic_mixed_final_answer_rate: float | None = None
    handicap_final_answer_count: int = Field(ge=0)
    correct_score_final_answer_count: int = Field(ge=0)
    multiple_choice_final_answer_count: int = Field(ge=0)
    candidate_final_hit_rate: float | None = None
    candidate_roi: float | None = None
    candidate_profit_loss: float = 0.0
    aggregate_deltas_json: dict[str, object] = Field(default_factory=dict)
    checks: list[HistoricalFinalAnswerMarketConcentrationCheck] = Field(
        default_factory=list
    )
    single_market_slice_samples: list[HistoricalFinalAnswerMarketConcentrationSlice] = (
        Field(default_factory=list)
    )
    dynamic_mixed_slice_samples: list[HistoricalFinalAnswerMarketConcentrationSlice] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_final_answer_market_concentration_audit_report(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalFinalAnswerMarketConcentrationAuditOptions | None = None,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    resolved_options = options or HistoricalFinalAnswerMarketConcentrationAuditOptions()
    candidate_results = [comparison.candidate for comparison in suite.comparisons]
    final_answer_results = [
        result for result in candidate_results if result.final_answer is not None
    ]
    final_answer_count = len(final_answer_results)
    market_type_counts = _market_type_counts(final_answer_results)
    market_type_rates = _rates(market_type_counts, denominator=final_answer_count)
    single_market_type_counts = _single_market_type_counts(final_answer_results)
    single_market_type_rates = _rates(
        single_market_type_counts,
        denominator=final_answer_count,
    )
    dominant_single_market_type, dominant_single_market_count = _dominant_count(
        single_market_type_counts
    )
    dynamic_mixed_final_answer_count = _true_count(
        final_answer_results,
        "final_answer_dynamic_mixed_market",
    )
    single_market_final_answer_count = final_answer_count - dynamic_mixed_final_answer_count
    checks = _checks(
        suite,
        final_answer_count=final_answer_count,
        market_type_count=len(market_type_counts),
        dominant_single_market_rate=_ratio(
            dominant_single_market_count,
            final_answer_count,
        ),
        dynamic_mixed_final_answer_count=dynamic_mixed_final_answer_count,
        dynamic_mixed_final_answer_rate=_ratio(
            dynamic_mixed_final_answer_count,
            final_answer_count,
        ),
        correct_score_final_answer_count=_true_count(
            final_answer_results,
            "final_answer_has_correct_score_market",
        ),
        multiple_choice_final_answer_count=_positive_count(
            final_answer_results,
            "final_answer_multiple_choice_fixture_count",
        ),
        options=resolved_options,
    )
    passed = not any(check.status == "failed" for check in checks)
    status: HistoricalFinalAnswerMarketConcentrationAuditStatus = (
        "passed" if passed else "failed"
    )
    warnings = _warnings(
        checks,
        final_answer_count=final_answer_count,
        dominant_single_market_rate=_ratio(
            dominant_single_market_count,
            final_answer_count,
        ),
        dynamic_mixed_final_answer_count=dynamic_mixed_final_answer_count,
    )
    single_market_slice_samples = _slice_samples(
        suite,
        dynamic_mixed=False,
        limit=resolved_options.top_slice_limit,
    )
    dynamic_mixed_slice_samples = _slice_samples(
        suite,
        dynamic_mixed=True,
        limit=resolved_options.top_slice_limit,
    )
    report_key = _report_key(
        suite,
        options=resolved_options,
        market_type_counts=market_type_counts,
        single_market_type_counts=single_market_type_counts,
    )
    candidate_profit_loss = _summary_float(suite.summary_json, "candidate_profit_loss") or 0.0
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_market_concentration_audit_v3_1",
        "report_key": report_key,
        "audit_id": resolved_options.audit_id,
        "status": status,
        "passed": passed,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "slice_count": suite.slice_count,
        "comparison_count": suite.comparison_count,
        "final_answer_count": final_answer_count,
        "market_type_count": len(market_type_counts),
        "market_type_counts": dict(sorted(market_type_counts.items())),
        "market_type_rates": dict(sorted(market_type_rates.items())),
        "single_market_final_answer_count": single_market_final_answer_count,
        "single_market_final_answer_rate": _ratio(
            single_market_final_answer_count,
            final_answer_count,
        ),
        "single_market_type_counts": dict(sorted(single_market_type_counts.items())),
        "single_market_type_rates": dict(sorted(single_market_type_rates.items())),
        "dominant_single_market_type": dominant_single_market_type,
        "dominant_single_market_count": dominant_single_market_count,
        "dominant_single_market_rate": _ratio(
            dominant_single_market_count,
            final_answer_count,
        ),
        "market_concentration_hhi": _hhi(single_market_type_rates),
        "dynamic_mixed_final_answer_count": dynamic_mixed_final_answer_count,
        "dynamic_mixed_final_answer_rate": _ratio(
            dynamic_mixed_final_answer_count,
            final_answer_count,
        ),
        "dynamic_mix_final_answer_lane": suite.summary_json.get(
            "dynamic_mix_final_answer_lane",
            False,
        ),
        "max_outcomes_per_fixture": resolved_options.max_outcomes_per_fixture,
        "min_marginal_quality_gain": resolved_options.min_marginal_quality_gain,
        "final_answer_stake_efficiency_guard": suite.summary_json.get(
            "final_answer_stake_efficiency_guard",
            False,
        ),
        "final_answer_stake_efficiency_penalty_strength": suite.summary_json.get(
            "final_answer_stake_efficiency_penalty_strength",
        ),
        "final_answer_stake_efficiency_max_stake_multiplier": suite.summary_json.get(
            "final_answer_stake_efficiency_max_stake_multiplier",
        ),
        "final_answer_stake_efficiency_min_roi": suite.summary_json.get(
            "final_answer_stake_efficiency_min_roi",
        ),
        "final_answer_stake_efficiency_modes": suite.summary_json.get(
            "final_answer_stake_efficiency_modes",
            [],
        ),
        "final_answer_stake_efficiency_scope": suite.summary_json.get(
            "final_answer_stake_efficiency_scope",
        ),
        "candidate_final_answer_stake_efficiency_penalty_option_count": (
            _summary_int(
                suite.summary_json,
                "candidate_final_answer_stake_efficiency_penalty_option_count",
            )
        ),
        "dynamic_mix_final_answer_lane_effective_pass_types": suite.summary_json.get(
            "dynamic_mix_final_answer_lane_effective_pass_types",
            [],
        ),
        "dynamic_mix_final_answer_lane_effective_constraint_profiles": (
            suite.summary_json.get(
                "dynamic_mix_final_answer_lane_effective_constraint_profiles",
                [],
            )
        ),
        "dynamic_mix_final_answer_lane_segment_gate_report": (
            str(resolved_options.dynamic_mix_final_answer_lane_segment_gate_report)
            if resolved_options.dynamic_mix_final_answer_lane_segment_gate_report is not None
            else None
        ),
        "dynamic_mix_final_answer_lane_admission_gate_report": (
            str(resolved_options.dynamic_mix_final_answer_lane_admission_gate_report)
            if resolved_options.dynamic_mix_final_answer_lane_admission_gate_report
            is not None
            else None
        ),
        "dynamic_mix_final_answer_lane_admitted_pass_types": list(
            resolved_options.dynamic_mix_final_answer_lane_admitted_pass_types
        ),
        "dynamic_mix_final_answer_lane_blocked_pass_types": list(
            resolved_options.dynamic_mix_final_answer_lane_blocked_pass_types
        ),
        "dynamic_mix_final_answer_lane_constraint_profiles": [
            profile.model_dump(mode="json")
            for profile in resolved_options.dynamic_mix_final_answer_lane_constraint_profiles
        ],
        "candidate_completed_dynamic_mix_final_answer_lane_count": (
            _summary_int(
                suite.summary_json,
                "candidate_completed_dynamic_mix_final_answer_lane_count",
            )
        ),
        "candidate_final_answer_dynamic_mix_final_answer_lane_count": (
            _summary_int(
                suite.summary_json,
                "candidate_final_answer_dynamic_mix_final_answer_lane_count",
            )
        ),
        "candidate_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count": (
            _summary_int(
                suite.summary_json,
                (
                    "candidate_dynamic_mix_final_answer_lane_"
                    "quality_guard_blocked_option_count"
                ),
            )
        ),
        "correct_score_final_answer_lane": suite.summary_json.get(
            "correct_score_final_answer_lane",
            False,
        ),
        "correct_score_final_answer_lane_pass_types": suite.summary_json.get(
            "correct_score_final_answer_lane_pass_types",
            [],
        ),
        "correct_score_final_answer_lane_modes": suite.summary_json.get(
            "correct_score_final_answer_lane_modes",
            [],
        ),
        "correct_score_final_answer_lane_candidate_limit": suite.summary_json.get(
            "correct_score_final_answer_lane_candidate_limit",
        ),
        "correct_score_final_answer_lane_min_probability": suite.summary_json.get(
            "correct_score_final_answer_lane_min_probability",
        ),
        "correct_score_final_answer_lane_min_correct_score_probability": (
            suite.summary_json.get(
                "correct_score_final_answer_lane_min_correct_score_probability"
            )
        ),
        "correct_score_final_answer_lane_max_correct_score_per_selection": (
            suite.summary_json.get(
                "correct_score_final_answer_lane_max_correct_score_per_selection"
            )
        ),
        "correct_score_final_answer_lane_score_boost": suite.summary_json.get(
            "correct_score_final_answer_lane_score_boost",
        ),
        "correct_score_final_answer_lane_max_hit_probability_deficit": (
            suite.summary_json.get(
                "correct_score_final_answer_lane_max_hit_probability_deficit"
            )
        ),
        "correct_score_final_answer_lane_min_roi_delta": suite.summary_json.get(
            "correct_score_final_answer_lane_min_roi_delta",
        ),
        "candidate_completed_correct_score_final_answer_lane_count": (
            _summary_int(
                suite.summary_json,
                "candidate_completed_correct_score_final_answer_lane_count",
            )
        ),
        "candidate_final_answer_correct_score_final_answer_lane_count": (
            _summary_int(
                suite.summary_json,
                "candidate_final_answer_correct_score_final_answer_lane_count",
            )
        ),
        "candidate_correct_score_final_answer_lane_quality_guard_blocked_option_count": (
            _summary_int(
                suite.summary_json,
                (
                    "candidate_correct_score_final_answer_lane_"
                    "quality_guard_blocked_option_count"
                ),
            )
        ),
        "handicap_final_answer_count": _true_count(
            final_answer_results,
            "final_answer_has_handicap_market",
        ),
        "correct_score_final_answer_count": _true_count(
            final_answer_results,
            "final_answer_has_correct_score_market",
        ),
        "multiple_choice_final_answer_count": _positive_count(
            final_answer_results,
            "final_answer_multiple_choice_fixture_count",
        ),
        "candidate_final_hit_rate": _summary_float(
            suite.summary_json,
            "candidate_final_hit_rate",
        ),
        "candidate_roi": _summary_float(suite.summary_json, "candidate_roi"),
        "candidate_profit_loss": candidate_profit_loss,
        "aggregate_deltas": dict(suite.aggregate_deltas_json),
        "failed_checks": [check.name for check in checks if check.status == "failed"],
        "warnings": warnings,
    }
    return HistoricalFinalAnswerMarketConcentrationAuditReport(
        report_key=report_key,
        audit_id=resolved_options.audit_id,
        status=status,
        passed=passed,
        suite_key=suite.suite_key,
        suite_status=suite.status,
        slice_count=suite.slice_count,
        comparison_count=suite.comparison_count,
        final_answer_count=final_answer_count,
        market_type_count=len(market_type_counts),
        market_type_counts=dict(sorted(market_type_counts.items())),
        market_type_rates=dict(sorted(market_type_rates.items())),
        single_market_final_answer_count=single_market_final_answer_count,
        single_market_final_answer_rate=_ratio(
            single_market_final_answer_count,
            final_answer_count,
        ),
        single_market_type_counts=dict(sorted(single_market_type_counts.items())),
        single_market_type_rates=dict(sorted(single_market_type_rates.items())),
        dominant_single_market_type=dominant_single_market_type,
        dominant_single_market_count=dominant_single_market_count,
        dominant_single_market_rate=_ratio(
            dominant_single_market_count,
            final_answer_count,
        ),
        market_concentration_hhi=_hhi(single_market_type_rates),
        dynamic_mixed_final_answer_count=dynamic_mixed_final_answer_count,
        dynamic_mixed_final_answer_rate=_ratio(
            dynamic_mixed_final_answer_count,
            final_answer_count,
        ),
        handicap_final_answer_count=_true_count(
            final_answer_results,
            "final_answer_has_handicap_market",
        ),
        correct_score_final_answer_count=_true_count(
            final_answer_results,
            "final_answer_has_correct_score_market",
        ),
        multiple_choice_final_answer_count=_positive_count(
            final_answer_results,
            "final_answer_multiple_choice_fixture_count",
        ),
        candidate_final_hit_rate=_summary_float(
            suite.summary_json,
            "candidate_final_hit_rate",
        ),
        candidate_roi=_summary_float(suite.summary_json, "candidate_roi"),
        candidate_profit_loss=candidate_profit_loss,
        aggregate_deltas_json=dict(suite.aggregate_deltas_json),
        checks=checks,
        single_market_slice_samples=single_market_slice_samples,
        dynamic_mixed_slice_samples=dynamic_mixed_slice_samples,
        warnings=warnings,
        summary_json=summary,
    )


def run_historical_final_answer_market_concentration_audit(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerMarketConcentrationAuditOptions | None = None,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    resolved_options = options or HistoricalFinalAnswerMarketConcentrationAuditOptions()
    resolved_slices = (
        list(historical_slices[: resolved_options.slice_limit])
        if resolved_options.slice_limit is not None
        else list(historical_slices)
    )
    suite = run_historical_recommendation_backtest_suite(
        resolved_slices,
        options=_backtest_options(resolved_options),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    return build_historical_final_answer_market_concentration_audit_report(
        suite,
        options=resolved_options,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = run_historical_final_answer_market_concentration_audit(
        _historical_slices_from_args(args),
        options=_options_from_args(args),
    )
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    final_answer_count: int,
    market_type_count: int,
    dominant_single_market_rate: float | None,
    dynamic_mixed_final_answer_count: int,
    dynamic_mixed_final_answer_rate: float | None,
    correct_score_final_answer_count: int,
    multiple_choice_final_answer_count: int,
    options: HistoricalFinalAnswerMarketConcentrationAuditOptions,
) -> list[HistoricalFinalAnswerMarketConcentrationCheck]:
    return [
        _minimum_check(
            name="final_answer_count",
            actual=final_answer_count,
            threshold=options.min_final_answer_count,
            detail="candidate replay should produce enough settled final answers",
        ),
        _minimum_check(
            name="market_type_count",
            actual=market_type_count,
            threshold=options.min_market_type_count,
            detail="final answers should use enough distinct market types across the suite",
        ),
        _optional_maximum_check(
            name="dominant_single_market_rate",
            actual=dominant_single_market_rate,
            threshold=options.max_dominant_single_market_rate,
            detail=(
                "single-market final answers should not be dominated by one "
                "market silo"
            ),
        ),
        _minimum_check(
            name="dynamic_mixed_final_answer_count",
            actual=dynamic_mixed_final_answer_count,
            threshold=options.min_dynamic_mixed_final_answer_count,
            detail="suite should include enough true mixed-market final answers",
        ),
        _optional_minimum_check(
            name="dynamic_mixed_final_answer_rate",
            actual=dynamic_mixed_final_answer_rate,
            threshold=options.min_dynamic_mixed_final_answer_rate,
            detail="suite should meet the configured mixed-market final-answer rate",
        ),
        _minimum_check(
            name="correct_score_final_answer_count",
            actual=correct_score_final_answer_count,
            threshold=options.min_correct_score_final_answer_count,
            detail="suite should include enough correct-score final answers when required",
        ),
        _minimum_check(
            name="multiple_choice_final_answer_count",
            actual=multiple_choice_final_answer_count,
            threshold=options.min_multiple_choice_final_answer_count,
            detail="suite should include enough multiple-choice final answers when required",
        ),
        _optional_minimum_check(
            name="final_hit_rate_delta",
            actual=_delta_float(suite, "final_hit_rate_delta"),
            threshold=options.min_final_hit_rate_delta,
            detail="dynamic-mix work should not regress final-answer hit rate",
        ),
        _optional_minimum_check(
            name="roi_delta",
            actual=_delta_float(suite, "roi_delta"),
            threshold=options.min_roi_delta,
            detail="dynamic-mix work should not regress final-answer ROI",
        ),
        _optional_minimum_check(
            name="profit_loss_delta",
            actual=_delta_float(suite, "profit_loss_delta"),
            threshold=options.min_profit_loss_delta,
            detail="dynamic-mix work should not regress final-answer profit/loss",
        ),
        _optional_maximum_check(
            name="brier_score_delta",
            actual=_delta_float(suite, "brier_score_delta"),
            threshold=options.max_brier_score_delta,
            detail="dynamic-mix work should not regress Brier score",
        ),
        _optional_maximum_check(
            name="log_loss_delta",
            actual=_delta_float(suite, "log_loss_delta"),
            threshold=options.max_log_loss_delta,
            detail="dynamic-mix work should not regress log loss",
        ),
        _optional_maximum_check(
            name="mean_calibration_error_delta",
            actual=_delta_float(suite, "mean_calibration_error_delta"),
            threshold=options.max_mean_calibration_error_delta,
            detail="dynamic-mix work should not regress calibration error",
        ),
    ]


def _minimum_check(
    *,
    name: str,
    actual: int,
    threshold: int,
    detail: str,
) -> HistoricalFinalAnswerMarketConcentrationCheck:
    return HistoricalFinalAnswerMarketConcentrationCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | None,
    threshold: float | None,
    detail: str,
) -> HistoricalFinalAnswerMarketConcentrationCheck:
    if threshold is None:
        return HistoricalFinalAnswerMarketConcentrationCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return HistoricalFinalAnswerMarketConcentrationCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_maximum_check(
    *,
    name: str,
    actual: float | None,
    threshold: float | None,
    detail: str,
) -> HistoricalFinalAnswerMarketConcentrationCheck:
    if threshold is None:
        return HistoricalFinalAnswerMarketConcentrationCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=None,
            detail=detail,
        )
    return HistoricalFinalAnswerMarketConcentrationCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _warnings(
    checks: Sequence[HistoricalFinalAnswerMarketConcentrationCheck],
    *,
    final_answer_count: int,
    dominant_single_market_rate: float | None,
    dynamic_mixed_final_answer_count: int,
) -> list[str]:
    warnings = [
        f"final_answer_market_concentration_audit:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    if final_answer_count == 0:
        warnings.append("final_answer_market_concentration_audit:no_final_answers")
    if dominant_single_market_rate == 1.0:
        warnings.append(
            "final_answer_market_concentration_audit:single_market_final_answer_dominance"
        )
    if dynamic_mixed_final_answer_count == 0:
        warnings.append(
            "final_answer_market_concentration_audit:no_dynamic_mixed_final_answers"
        )
    return _dedupe(warnings)


def _backtest_options(
    options: HistoricalFinalAnswerMarketConcentrationAuditOptions,
) -> HistoricalRecommendationBacktestOptions:
    return HistoricalRecommendationBacktestOptions(
        pass_types=options.pass_types,
        modes=options.modes,
        strategy=options.strategy,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
        min_probability=options.min_probability,
        min_data_quality_score=options.min_data_quality_score,
        allowed_markets=options.allowed_markets,
        candidate_fixture_limit=options.candidate_fixture_limit,
        max_candidates_per_fixture=options.max_candidates_per_fixture,
        max_outcomes_per_fixture=options.max_outcomes_per_fixture,
        min_marginal_quality_gain=options.min_marginal_quality_gain,
        scenario_candidate_fixture_buffer=options.scenario_candidate_fixture_buffer,
        final_answer_scenario_variant_count=options.final_answer_scenario_variant_count,
        final_answer_stake_efficiency_guard=(
            options.final_answer_stake_efficiency_guard
        ),
        final_answer_stake_efficiency_penalty_strength=(
            options.final_answer_stake_efficiency_penalty_strength
        ),
        final_answer_stake_efficiency_max_stake_multiplier=(
            options.final_answer_stake_efficiency_max_stake_multiplier
        ),
        final_answer_stake_efficiency_min_roi=(
            options.final_answer_stake_efficiency_min_roi
        ),
        final_answer_stake_efficiency_modes=(
            options.final_answer_stake_efficiency_modes
        ),
        final_answer_stake_efficiency_scope=(
            options.final_answer_stake_efficiency_scope
        ),
        dynamic_mix_final_answer_lane=options.dynamic_mix_final_answer_lane,
        dynamic_mix_final_answer_lane_pass_types=(
            options.dynamic_mix_final_answer_lane_pass_types
        ),
        dynamic_mix_final_answer_lane_mode=options.dynamic_mix_final_answer_lane_mode,
        dynamic_mix_final_answer_lane_modes=options.dynamic_mix_final_answer_lane_modes,
        dynamic_mix_final_answer_lane_admitted_pass_types=(
            options.dynamic_mix_final_answer_lane_admitted_pass_types
        ),
        dynamic_mix_final_answer_lane_blocked_pass_types=(
            options.dynamic_mix_final_answer_lane_blocked_pass_types
        ),
        dynamic_mix_final_answer_lane_constraint_profiles=(
            options.dynamic_mix_final_answer_lane_constraint_profiles
        ),
        dynamic_mix_final_answer_lane_min_market_count=(
            options.dynamic_mix_final_answer_lane_min_market_count
        ),
        dynamic_mix_final_answer_lane_candidate_limit=(
            options.dynamic_mix_final_answer_lane_candidate_limit
        ),
        dynamic_mix_final_answer_lane_solver_search=(
            options.dynamic_mix_final_answer_lane_solver_search
        ),
        dynamic_mix_final_answer_lane_min_probability=(
            options.dynamic_mix_final_answer_lane_min_probability
        ),
        dynamic_mix_final_answer_lane_score_boost=(
            options.dynamic_mix_final_answer_lane_score_boost
        ),
        dynamic_mix_final_answer_lane_max_hit_probability_deficit=(
            options.dynamic_mix_final_answer_lane_max_hit_probability_deficit
        ),
        dynamic_mix_final_answer_lane_min_roi_delta=(
            options.dynamic_mix_final_answer_lane_min_roi_delta
        ),
        correct_score_final_answer_lane=options.correct_score_final_answer_lane,
        correct_score_final_answer_lane_pass_types=(
            options.correct_score_final_answer_lane_pass_types
        ),
        correct_score_final_answer_lane_mode=(
            options.correct_score_final_answer_lane_mode
        ),
        correct_score_final_answer_lane_modes=(
            options.correct_score_final_answer_lane_modes
        ),
        correct_score_final_answer_lane_candidate_limit=(
            options.correct_score_final_answer_lane_candidate_limit
        ),
        correct_score_final_answer_lane_min_probability=(
            options.correct_score_final_answer_lane_min_probability
        ),
        correct_score_final_answer_lane_min_correct_score_probability=(
            options.correct_score_final_answer_lane_min_correct_score_probability
        ),
        correct_score_final_answer_lane_max_correct_score_per_selection=(
            options.correct_score_final_answer_lane_max_correct_score_per_selection
        ),
        correct_score_final_answer_lane_score_boost=(
            options.correct_score_final_answer_lane_score_boost
        ),
        correct_score_final_answer_lane_max_hit_probability_deficit=(
            options.correct_score_final_answer_lane_max_hit_probability_deficit
        ),
        correct_score_final_answer_lane_min_roi_delta=(
            options.correct_score_final_answer_lane_min_roi_delta
        ),
        correct_score_final_answer_lane_outcomes=(
            options.correct_score_final_answer_lane_outcomes
        ),
    )


def _historical_slices_from_args(args: Namespace) -> list[HistoricalRecommendationSlice]:
    slices = [
        load_historical_recommendation_slice(path) for path in args.slice_paths
    ]
    for manifest_path in args.suite_manifest:
        bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)
        slices.extend(bundle.slices)
    return slices


def _slice_samples(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    dynamic_mixed: bool,
    limit: int,
) -> list[HistoricalFinalAnswerMarketConcentrationSlice]:
    if limit == 0:
        return []
    samples = [
        _slice_sample(comparison)
        for comparison in suite.comparisons
        if comparison.candidate.final_answer is not None
        and (
            comparison.candidate.summary_json.get("final_answer_dynamic_mixed_market")
            is dynamic_mixed
        )
    ]
    samples.sort(key=lambda sample: (sample.competition_id or "", sample.slice_id))
    return samples[:limit]


def _slice_sample(
    comparison: HistoricalRecommendationBacktestComparisonResult,
) -> HistoricalFinalAnswerMarketConcentrationSlice:
    candidate = comparison.candidate
    summary = candidate.summary_json
    market_types = _market_types(candidate)
    final_answer = candidate.final_answer
    scenario_key = summary.get("final_answer_scenario_key")
    return HistoricalFinalAnswerMarketConcentrationSlice(
        slice_id=candidate.slice_id,
        competition_id=_optional_str(summary.get("competition_id")),
        final_answer_present=final_answer is not None,
        final_answer_changed=bool(
            comparison.summary_json.get("final_answer_changed", False)
        ),
        market_types=market_types,
        single_market_type=market_types[0] if len(market_types) == 1 else None,
        dynamic_mixed_market=len(market_types) > 1,
        scenario_key=_optional_str(scenario_key),
        pass_type=final_answer.scenario.pass_type if final_answer is not None else None,
        mode=final_answer.scenario.mode if final_answer is not None else None,
        selected_candidate_count=_summary_int(
            summary,
            "final_answer_selected_candidate_count",
        ),
        multiple_choice_fixture_count=_summary_int(
            summary,
            "final_answer_multiple_choice_fixture_count",
        ),
        actual_hit=final_answer.actual_hit if final_answer is not None else None,
        total_stake=candidate.total_stake,
        actual_return=candidate.actual_return,
        profit_loss=candidate.profit_loss,
        roi=candidate.roi,
    )


def _market_type_counts(
    results: Sequence[HistoricalRecommendationBacktestResult],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        counts.update(_market_types(result))
    return counts


def _single_market_type_counts(
    results: Sequence[HistoricalRecommendationBacktestResult],
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        market_types = _market_types(result)
        if len(market_types) == 1:
            counts[market_types[0]] += 1
    return counts


def _market_types(result: HistoricalRecommendationBacktestResult) -> list[str]:
    raw = result.summary_json.get("final_answer_market_types", [])
    if not isinstance(raw, list):
        return []
    return sorted(str(item) for item in raw if item is not None and str(item))


def _rates(counts: Mapping[str, int], *, denominator: int) -> dict[str, float]:
    if denominator <= 0:
        return {}
    return {key: value / denominator for key, value in counts.items()}


def _dominant_count(counts: Mapping[str, int]) -> tuple[str | None, int]:
    if not counts:
        return None, 0
    key, value = max(sorted(counts.items()), key=lambda item: item[1])
    return key, value


def _hhi(rates: Mapping[str, float]) -> float | None:
    if not rates:
        return None
    return sum(rate * rate for rate in rates.values())


def _true_count(
    results: Sequence[HistoricalRecommendationBacktestResult],
    key: str,
) -> int:
    return sum(1 for result in results if result.summary_json.get(key) is True)


def _positive_count(
    results: Sequence[HistoricalRecommendationBacktestResult],
    key: str,
) -> int:
    return sum(1 for result in results if _summary_int(result.summary_json, key) > 0)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _summary_float(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _delta_float(
    suite: HistoricalRecommendationBacktestSuiteResult,
    key: str,
) -> float | None:
    return _summary_float(suite.aggregate_deltas_json, key)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _report_key(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    options: HistoricalFinalAnswerMarketConcentrationAuditOptions,
    market_type_counts: Mapping[str, int],
    single_market_type_counts: Mapping[str, int],
) -> str:
    payload = {
        "suite_key": suite.suite_key,
        "options": options.model_dump(mode="json"),
        "market_type_counts": dict(sorted(market_type_counts.items())),
        "single_market_type_counts": dict(sorted(single_market_type_counts.items())),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_market_concentration_audit:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Audit whether historical final answers are truly mixed-market or "
            "over-concentrated in one market silo."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--audit-id", default=DEFAULT_FINAL_ANSWER_MARKET_CONCENTRATION_AUDIT_ID)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--allowed-markets", default="1x2")
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--min-marginal-quality-gain", type=float, default=0.0)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--final-answer-stake-efficiency-guard", action="store_true")
    parser.add_argument(
        "--final-answer-stake-efficiency-penalty-strength",
        type=float,
        default=0.08,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-max-stake-multiplier",
        type=float,
        default=2.0,
    )
    parser.add_argument("--final-answer-stake-efficiency-min-roi", type=float, default=0.0)
    parser.add_argument("--final-answer-stake-efficiency-modes", default="multiple")
    parser.add_argument(
        "--final-answer-stake-efficiency-scope",
        choices=["all", "quality_signal_affected"],
        default="all",
    )
    parser.add_argument("--dynamic-mix-final-answer-lane", action="store_true")
    parser.add_argument("--dynamic-mix-final-answer-lane-pass-types", default="2x1")
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--dynamic-mix-final-answer-lane-modes", default="")
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-segment-gate-report",
        type=Path,
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-admission-gate-report",
        type=Path,
    )
    parser.add_argument("--dynamic-mix-final-answer-lane-admitted-pass-types", default="")
    parser.add_argument("--dynamic-mix-final-answer-lane-blocked-pass-types", default="")
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-min-market-count",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-candidate-limit",
        type=int,
        default=96,
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-solver-search",
        action="store_true",
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-min-probability",
        type=float,
        default=0.005,
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-score-boost",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--dynamic-mix-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument("--dynamic-mix-final-answer-lane-min-roi-delta", type=float)
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
    parser.add_argument("--slice-limit", type=int)
    parser.add_argument("--min-final-answer-count", type=int, default=1)
    parser.add_argument("--min-market-type-count", type=int, default=1)
    parser.add_argument("--max-dominant-single-market-rate", type=float)
    parser.add_argument("--min-dynamic-mixed-final-answer-count", type=int, default=0)
    parser.add_argument("--min-dynamic-mixed-final-answer-rate", type=float)
    parser.add_argument("--min-correct-score-final-answer-count", type=int, default=0)
    parser.add_argument("--min-multiple-choice-final-answer-count", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float)
    parser.add_argument("--min-roi-delta", type=float)
    parser.add_argument("--min-profit-loss-delta", type=float)
    parser.add_argument("--max-brier-score-delta", type=float)
    parser.add_argument("--max-log-loss-delta", type=float)
    parser.add_argument("--max-mean-calibration-error-delta", type=float)
    parser.add_argument("--top-slice-limit", type=int, default=20)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerMarketConcentrationAuditOptions:
    admitted_from_report, blocked_from_report = _segment_gate_pass_types_from_args(args)
    (
        admitted_from_admission_gate,
        blocked_from_admission_gate,
        constraint_profiles_from_admission_gate,
    ) = _admission_gate_dynamic_mix_settings_from_args(args)
    return HistoricalFinalAnswerMarketConcentrationAuditOptions(
        audit_id=args.audit_id,
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        strategy=cast(RecommendationStrategy, args.strategy),
        allowed_markets=tuple(
            cast(RecommendationMarketType, market)
            for market in _csv(args.allowed_markets)
        ),
        unit_stake=args.unit_stake,
        max_budget=args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        candidate_fixture_limit=args.candidate_fixture_limit,
        max_candidates_per_fixture=args.max_candidates_per_fixture,
        max_outcomes_per_fixture=args.max_outcomes_per_fixture,
        min_marginal_quality_gain=args.min_marginal_quality_gain,
        scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
        final_answer_scenario_variant_count=args.final_answer_scenario_variant_count,
        final_answer_stake_efficiency_guard=(
            args.final_answer_stake_efficiency_guard
        ),
        final_answer_stake_efficiency_penalty_strength=(
            args.final_answer_stake_efficiency_penalty_strength
        ),
        final_answer_stake_efficiency_max_stake_multiplier=(
            args.final_answer_stake_efficiency_max_stake_multiplier
        ),
        final_answer_stake_efficiency_min_roi=(
            args.final_answer_stake_efficiency_min_roi
        ),
        final_answer_stake_efficiency_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.final_answer_stake_efficiency_modes)
        ),
        final_answer_stake_efficiency_scope=cast(
            HistoricalFinalAnswerStakeEfficiencyScope,
            args.final_answer_stake_efficiency_scope,
        ),
        dynamic_mix_final_answer_lane=args.dynamic_mix_final_answer_lane,
        dynamic_mix_final_answer_lane_pass_types=tuple(
            _csv(args.dynamic_mix_final_answer_lane_pass_types)
        ),
        dynamic_mix_final_answer_lane_mode=cast(
            RecommendationMode,
            args.dynamic_mix_final_answer_lane_mode,
        ),
        dynamic_mix_final_answer_lane_modes=tuple(
            cast(RecommendationMode, mode)
            for mode in _csv(args.dynamic_mix_final_answer_lane_modes)
        ),
        dynamic_mix_final_answer_lane_segment_gate_report=(
            args.dynamic_mix_final_answer_lane_segment_gate_report
        ),
        dynamic_mix_final_answer_lane_admission_gate_report=(
            args.dynamic_mix_final_answer_lane_admission_gate_report
        ),
        dynamic_mix_final_answer_lane_admitted_pass_types=_dedupe_tuple(
            (
                *_csv(args.dynamic_mix_final_answer_lane_admitted_pass_types),
                *admitted_from_report,
                *admitted_from_admission_gate,
            )
        ),
        dynamic_mix_final_answer_lane_blocked_pass_types=_dedupe_tuple(
            (
                *_csv(args.dynamic_mix_final_answer_lane_blocked_pass_types),
                *blocked_from_report,
                *blocked_from_admission_gate,
            )
        ),
        dynamic_mix_final_answer_lane_constraint_profiles=(
            constraint_profiles_from_admission_gate
        ),
        dynamic_mix_final_answer_lane_min_market_count=(
            args.dynamic_mix_final_answer_lane_min_market_count
        ),
        dynamic_mix_final_answer_lane_candidate_limit=(
            args.dynamic_mix_final_answer_lane_candidate_limit
        ),
        dynamic_mix_final_answer_lane_solver_search=(
            args.dynamic_mix_final_answer_lane_solver_search
        ),
        dynamic_mix_final_answer_lane_min_probability=(
            args.dynamic_mix_final_answer_lane_min_probability
        ),
        dynamic_mix_final_answer_lane_score_boost=(
            args.dynamic_mix_final_answer_lane_score_boost
        ),
        dynamic_mix_final_answer_lane_max_hit_probability_deficit=(
            args.dynamic_mix_final_answer_lane_max_hit_probability_deficit
        ),
        dynamic_mix_final_answer_lane_min_roi_delta=(
            args.dynamic_mix_final_answer_lane_min_roi_delta
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
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        slice_limit=args.slice_limit,
        min_final_answer_count=args.min_final_answer_count,
        min_market_type_count=args.min_market_type_count,
        max_dominant_single_market_rate=args.max_dominant_single_market_rate,
        min_dynamic_mixed_final_answer_count=args.min_dynamic_mixed_final_answer_count,
        min_dynamic_mixed_final_answer_rate=args.min_dynamic_mixed_final_answer_rate,
        min_correct_score_final_answer_count=args.min_correct_score_final_answer_count,
        min_multiple_choice_final_answer_count=(
            args.min_multiple_choice_final_answer_count
        ),
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        top_slice_limit=args.top_slice_limit,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_historical_final_answer_market_concentration_audit_report(
    path: Path | str,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    return HistoricalFinalAnswerMarketConcentrationAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _segment_gate_pass_types_from_args(
    args: Namespace,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    path = args.dynamic_mix_final_answer_lane_segment_gate_report
    if path is None:
        return (), ()
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return (), ()
    admitted = _string_tuple(payload.get("promoted_pass_types"))
    blocked = _string_tuple(payload.get("blocked_pass_types"))
    return admitted, blocked


def _admission_gate_dynamic_mix_settings_from_args(
    args: Namespace,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[HistoricalDynamicMixFinalAnswerLaneConstraintProfile, ...],
]:
    path = args.dynamic_mix_final_answer_lane_admission_gate_report
    if path is None:
        return (), (), ()
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return (), (), ()
    effective_pass_types = _string_tuple(payload.get("effective_pass_types"))
    blocked_pass_types = _string_tuple(payload.get("blocked_pass_types"))
    effective_profiles = _constraint_profiles_tuple(
        payload.get("effective_constraint_profiles")
    )
    return effective_pass_types, blocked_pass_types, effective_profiles


def _constraint_profiles_tuple(
    value: object,
) -> tuple[HistoricalDynamicMixFinalAnswerLaneConstraintProfile, ...]:
    if not isinstance(value, list):
        return ()
    profiles: list[HistoricalDynamicMixFinalAnswerLaneConstraintProfile] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        profile = HistoricalDynamicMixFinalAnswerLaneConstraintProfile.model_validate(
            item
        )
        profiles.append(profile)
    return tuple(profiles)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if item is not None and str(item))


def _dedupe_tuple(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return tuple(deduped)


def _dedupe(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
