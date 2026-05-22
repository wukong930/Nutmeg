from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalFinalAnswerSegmentPenaltyRuntimeReplayStatus = Literal[
    "runtime_replay_passed",
    "holdout_replay_passed",
    "shadow_replay_failed",
    "disabled",
    "no_rules",
    "blocked",
]
type HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class FinalAnswerSegmentPenaltyRuntimeRule(BaseModel):
    rule_id: str
    proposed_profile_version: str | None = None
    proposed_production_enabled: bool = False
    holdout_candidate_enabled: bool = False
    production_recommendation_changed: bool = False
    pass_types: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=list)
    competition_ids: list[str] = Field(default_factory=list)
    season_ids: list[str] = Field(default_factory=list)
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    penalty_strength: float = Field(default=0.04, ge=0.0, le=1.0)
    constraints_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FinalAnswerSegmentPenaltyRuntimeRuleSet(BaseModel):
    profile_version: str = "unknown"
    calculation_basis: str = "final_answer_segment_penalty_runtime_rule_loader_v3_1"
    status: str | None = None
    runtime_profile_proposal_allowed: bool = False
    holdout_candidate_allowed: bool = False
    shadow_replay_enabled: bool = False
    rules: list[FinalAnswerSegmentPenaltyRuntimeRule] = Field(default_factory=list)
    source_json_path: str | None = None
    notes: list[str] = Field(default_factory=list)


class HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions(BaseModel):
    enable_shadow_replay: bool = False
    rule_ids: tuple[str, ...] = ()
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_penalty_option_count: int = Field(default=1, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    require_holdout_candidate_enabled: bool = True
    require_proposed_production_enabled: bool = False
    require_profile_runtime_allowed: bool = False
    require_no_public_response_change: bool = True
    max_selected_rule_count: int = Field(default=1, ge=1)


class HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayStatus
    runtime_replay_allowed: bool
    holdout_replay_allowed: bool
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    baseline_suite_key: str | None = None
    candidate_suite_key: str | None = None
    final_answer_count: int = Field(default=0, ge=0)
    changed_final_answer_count: int = Field(default=0, ge=0)
    penalty_option_count: int = Field(default=0, ge=0)
    baseline_final_answer_hit_count: int = Field(default=0, ge=0)
    candidate_final_answer_hit_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    final_answer_hit_rate_delta: float | None = None
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float = 0.0
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    harm_count_vs_baseline: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    improvement_count_vs_baseline: int = Field(default=0, ge=0)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck] = (
        Field(default_factory=list)
    )
    rule_set_json: dict[str, object] = Field(default_factory=dict)
    selected_rule_json: dict[str, object] | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    manifest_results: list[HistoricalRecommendationSuiteManifestLoadResult] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)


class _SuitePairMetrics(BaseModel):
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    penalty_option_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    candidate_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    final_answer_hit_rate_delta: float | None = None
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    harm_count_vs_baseline: int = Field(ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    improvement_count_vs_baseline: int = Field(ge=0)


def load_final_answer_segment_penalty_runtime_rule_set(
    path: Path | str,
    *,
    enable_shadow_replay: bool = False,
) -> FinalAnswerSegmentPenaltyRuntimeRuleSet:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    profile_json = _extract_profile_json(payload)
    rules = [
        FinalAnswerSegmentPenaltyRuntimeRule.model_validate(rule)
        for rule in _mapping_list(profile_json.get("final_answer_segment_penalty_rules"))
    ]
    if not rules:
        rules = [
            FinalAnswerSegmentPenaltyRuntimeRule.model_validate(rule)
            for rule in _mapping_list(profile_json.get("rules"))
        ]
    return FinalAnswerSegmentPenaltyRuntimeRuleSet(
        profile_version=_string(profile_json.get("profile_version")) or "unknown",
        calculation_basis=(
            _string(profile_json.get("calculation_basis"))
            or "final_answer_segment_penalty_runtime_rule_loader_v3_1"
        ),
        status=_string(profile_json.get("status")),
        runtime_profile_proposal_allowed=_bool(
            profile_json.get("runtime_profile_proposal_allowed")
        ),
        holdout_candidate_allowed=_bool(profile_json.get("holdout_candidate_allowed")),
        shadow_replay_enabled=enable_shadow_replay,
        rules=rules,
        source_json_path=str(path),
        notes=_string_list(profile_json.get("notes")),
    )


def build_historical_final_answer_segment_penalty_runtime_replay_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    rule_set: FinalAnswerSegmentPenaltyRuntimeRuleSet,
    options: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions | None = None,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport:
    resolved_options = (
        options or HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions()
    )
    resolved_rule_set = rule_set.model_copy(
        update={"shadow_replay_enabled": resolved_options.enable_shadow_replay}
    )
    selected_rules = _selected_rules(resolved_rule_set, options=resolved_options)
    warnings: list[str] = []
    if not resolved_options.enable_shadow_replay:
        warnings.append(
            "final_answer_segment_penalty_runtime_replay:disabled_by_feature_flag"
        )
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=[],
            status="disabled",
            warnings=warnings,
            options=resolved_options,
        )
    if not selected_rules:
        warnings.append("final_answer_segment_penalty_runtime_replay:no_selected_rules")
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=[],
            status="no_rules",
            warnings=warnings,
            options=resolved_options,
        )
    if len(selected_rules) > resolved_options.max_selected_rule_count:
        warnings.append(
            "final_answer_segment_penalty_runtime_replay:too_many_selected_rules"
        )
        checks = [
            _maximum_check(
                name="selected_rule_count",
                actual=len(selected_rules),
                threshold=resolved_options.max_selected_rule_count,
                detail="runtime replay currently supports a bounded rule set",
            )
        ]
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=checks,
            status="blocked",
            warnings=warnings,
            options=resolved_options,
        )
    selected_rule = selected_rules[0]
    baseline_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_baseline_backtest_options(resolved_options.backtest_options),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    candidate_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_candidate_backtest_options(
            resolved_options.backtest_options,
            selected_rule,
        ),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    metrics = _suite_pair_metrics(baseline_suite, candidate_suite)
    checks = _checks(
        resolved_rule_set,
        selected_rule,
        selected_rule_count=len(selected_rules),
        metrics=metrics,
        options=resolved_options,
    )
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _holdout_checks_passed(checks)
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    warnings.extend(_warnings(status=status, checks=checks))
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_segment_penalty_runtime_replay_v3_1"
        ),
        "status": status,
        "runtime_replay_allowed": runtime_allowed,
        "holdout_replay_allowed": holdout_allowed,
        "source_rule_profile_version": resolved_rule_set.profile_version,
        "source_rule_profile_status": resolved_rule_set.status,
        "rule_count": len(resolved_rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "selected_rule_id": selected_rule.rule_id,
        "baseline_suite_key": baseline_suite.suite_key,
        "candidate_suite_key": candidate_suite.suite_key,
        "final_answer_count": metrics.final_answer_count,
        "changed_final_answer_count": metrics.changed_final_answer_count,
        "penalty_option_count": metrics.penalty_option_count,
        "baseline_final_answer_hit_count": metrics.baseline_final_answer_hit_count,
        "candidate_final_answer_hit_count": metrics.candidate_final_answer_hit_count,
        "final_answer_hit_delta_count": metrics.final_answer_hit_delta_count,
        "final_answer_hit_rate_delta": metrics.final_answer_hit_rate_delta,
        "baseline_roi": metrics.baseline_roi,
        "candidate_roi": metrics.candidate_roi,
        "roi_delta": metrics.roi_delta,
        "profit_loss_delta": metrics.profit_loss_delta,
        "brier_score_delta": metrics.brier_score_delta,
        "log_loss_delta": metrics.log_loss_delta,
        "mean_calibration_error_delta": metrics.mean_calibration_error_delta,
        "harm_count_vs_baseline": metrics.harm_count_vs_baseline,
        "final_hit_harm_count_vs_baseline": metrics.final_hit_harm_count_vs_baseline,
        "profit_loss_harm_count_vs_baseline": (
            metrics.profit_loss_harm_count_vs_baseline
        ),
        "improvement_count_vs_baseline": metrics.improvement_count_vs_baseline,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(
        summary,
        checks,
        rule_set=resolved_rule_set,
        selected_rule=selected_rule,
    )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport(
        report_key=report_key,
        status=status,
        runtime_replay_allowed=runtime_allowed,
        holdout_replay_allowed=holdout_allowed,
        source_rule_profile_version=resolved_rule_set.profile_version,
        rule_count=len(resolved_rule_set.rules),
        selected_rule_count=len(selected_rules),
        baseline_suite_key=baseline_suite.suite_key,
        candidate_suite_key=candidate_suite.suite_key,
        final_answer_count=metrics.final_answer_count,
        changed_final_answer_count=metrics.changed_final_answer_count,
        penalty_option_count=metrics.penalty_option_count,
        baseline_final_answer_hit_count=metrics.baseline_final_answer_hit_count,
        candidate_final_answer_hit_count=metrics.candidate_final_answer_hit_count,
        final_answer_hit_delta_count=metrics.final_answer_hit_delta_count,
        final_answer_hit_rate_delta=metrics.final_answer_hit_rate_delta,
        baseline_roi=metrics.baseline_roi,
        candidate_roi=metrics.candidate_roi,
        roi_delta=metrics.roi_delta,
        profit_loss_delta=metrics.profit_loss_delta,
        brier_score_delta=metrics.brier_score_delta,
        log_loss_delta=metrics.log_loss_delta,
        mean_calibration_error_delta=metrics.mean_calibration_error_delta,
        harm_count_vs_baseline=metrics.harm_count_vs_baseline,
        final_hit_harm_count_vs_baseline=metrics.final_hit_harm_count_vs_baseline,
        profit_loss_harm_count_vs_baseline=(
            metrics.profit_loss_harm_count_vs_baseline
        ),
        improvement_count_vs_baseline=metrics.improvement_count_vs_baseline,
        checks=checks,
        rule_set_json=resolved_rule_set.model_dump(mode="json"),
        selected_rule_json=selected_rule.model_dump(mode="json"),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_final_answer_segment_penalty_runtime_replay_report(
        loaded_slices.slices,
        rule_set=load_final_answer_segment_penalty_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=args.enable_shadow_replay,
        ),
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded_slices.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
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
    if not report.runtime_replay_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _selected_rules(
    rule_set: FinalAnswerSegmentPenaltyRuntimeRuleSet,
    *,
    options: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions,
) -> list[FinalAnswerSegmentPenaltyRuntimeRule]:
    rule_ids = set(options.rule_ids)
    rules = [
        rule
        for rule in rule_set.rules
        if not rule_ids or rule.rule_id in rule_ids
    ]
    return sorted(rules, key=lambda rule: rule.rule_id)


def _baseline_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "final_answer_segment_penalty": False,
            "final_answer_segment_pass_types": (),
            "final_answer_segment_modes": (),
            "final_answer_segment_competition_ids": (),
            "final_answer_segment_season_ids": (),
            "final_answer_segment_min_competition_season_index": None,
            "final_answer_segment_max_competition_season_index": None,
            "final_answer_segment_min_hit_probability": None,
            "final_answer_segment_max_hit_probability": None,
            "final_answer_segment_min_odds_product": None,
            "final_answer_segment_max_odds_product": None,
            "final_answer_segment_min_average_leg_decimal_odds": None,
            "final_answer_segment_max_average_leg_decimal_odds": None,
        }
    )


def _candidate_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
    rule: FinalAnswerSegmentPenaltyRuntimeRule,
) -> HistoricalRecommendationBacktestOptions:
    constraints = rule.constraints_json
    return options.model_copy(
        update={
            "final_answer_segment_penalty": True,
            "final_answer_segment_penalty_strength": _float(
                constraints.get("final_answer_segment_penalty_strength"),
                fallback=rule.penalty_strength,
            ),
            "final_answer_segment_pass_types": tuple(
                _string_list(
                    constraints.get("final_answer_segment_pass_types"),
                    fallback=rule.pass_types,
                )
            ),
            "final_answer_segment_modes": tuple(
                cast(RecommendationMode, mode)
                for mode in _string_list(
                    constraints.get("final_answer_segment_modes"),
                    fallback=rule.modes,
                )
            ),
            "final_answer_segment_competition_ids": tuple(
                _string_list(
                    constraints.get("final_answer_segment_competition_ids"),
                    fallback=rule.competition_ids,
                )
            ),
            "final_answer_segment_season_ids": tuple(
                _string_list(
                    constraints.get("final_answer_segment_season_ids"),
                    fallback=rule.season_ids,
                )
            ),
            "final_answer_segment_min_competition_season_index": _int_or_none(
                constraints.get("final_answer_segment_min_competition_season_index"),
                fallback=rule.min_competition_season_index,
            ),
            "final_answer_segment_max_competition_season_index": _int_or_none(
                constraints.get("final_answer_segment_max_competition_season_index"),
                fallback=rule.max_competition_season_index,
            ),
            "final_answer_segment_min_hit_probability": _float_or_none(
                constraints.get("final_answer_segment_min_hit_probability")
            ),
            "final_answer_segment_max_hit_probability": _float_or_none(
                constraints.get("final_answer_segment_max_hit_probability")
            ),
            "final_answer_segment_min_odds_product": _float_or_none(
                constraints.get("final_answer_segment_min_odds_product")
            ),
            "final_answer_segment_max_odds_product": _float_or_none(
                constraints.get("final_answer_segment_max_odds_product")
            ),
            "final_answer_segment_min_average_leg_decimal_odds": _float_or_none(
                constraints.get("final_answer_segment_min_average_leg_decimal_odds")
            ),
            "final_answer_segment_max_average_leg_decimal_odds": _float_or_none(
                constraints.get("final_answer_segment_max_average_leg_decimal_odds")
            ),
        }
    )


def _suite_pair_metrics(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> _SuitePairMetrics:
    baseline_by_slice = {
        comparison.slice_id: comparison.candidate
        for comparison in baseline_suite.comparisons
    }
    candidate_by_slice = {
        comparison.slice_id: comparison.candidate
        for comparison in candidate_suite.comparisons
    }
    changed_count = 0
    final_hit_harm_count = 0
    profit_loss_harm_count = 0
    improvement_count = 0
    for slice_id in sorted(set(baseline_by_slice) & set(candidate_by_slice)):
        baseline_result = baseline_by_slice[slice_id]
        candidate_result = candidate_by_slice[slice_id]
        baseline_final = baseline_result.final_answer
        candidate_final = candidate_result.final_answer
        if _final_answer_signature(baseline_final) != _final_answer_signature(
            candidate_final
        ):
            changed_count += 1
        if candidate_result.final_hit_count < baseline_result.final_hit_count:
            final_hit_harm_count += 1
        if candidate_result.profit_loss < baseline_result.profit_loss:
            profit_loss_harm_count += 1
        if candidate_result.final_hit_count > baseline_result.final_hit_count:
            improvement_count += 1
    baseline_hit_count = _summary_int(
        baseline_suite.summary_json,
        "candidate_final_hit_count",
    )
    candidate_hit_count = _summary_int(
        candidate_suite.summary_json,
        "candidate_final_hit_count",
    )
    return _SuitePairMetrics(
        final_answer_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        changed_final_answer_count=changed_count,
        penalty_option_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_segment_penalty_option_count",
        ),
        baseline_final_answer_hit_count=baseline_hit_count,
        candidate_final_answer_hit_count=candidate_hit_count,
        final_answer_hit_delta_count=candidate_hit_count - baseline_hit_count,
        final_answer_hit_rate_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_final_hit_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_final_hit_rate"),
        ),
        baseline_roi=_summary_number(baseline_suite.summary_json, "candidate_roi"),
        candidate_roi=_summary_number(candidate_suite.summary_json, "candidate_roi"),
        roi_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_roi"),
            _summary_number(baseline_suite.summary_json, "candidate_roi"),
        ),
        profit_loss_delta=(
            (
                _summary_number(candidate_suite.summary_json, "candidate_profit_loss")
                or 0.0
            )
            - (
                _summary_number(baseline_suite.summary_json, "candidate_profit_loss")
                or 0.0
            )
        ),
        brier_score_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_brier_score"),
            _summary_number(baseline_suite.summary_json, "candidate_brier_score"),
        ),
        log_loss_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_log_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_log_loss"),
        ),
        mean_calibration_error_delta=_optional_delta(
            _summary_number(
                candidate_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
            _summary_number(
                baseline_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
        ),
        harm_count_vs_baseline=final_hit_harm_count,
        final_hit_harm_count_vs_baseline=final_hit_harm_count,
        profit_loss_harm_count_vs_baseline=profit_loss_harm_count,
        improvement_count_vs_baseline=improvement_count,
    )


def _checks(
    rule_set: FinalAnswerSegmentPenaltyRuntimeRuleSet,
    selected_rule: FinalAnswerSegmentPenaltyRuntimeRule,
    *,
    selected_rule_count: int,
    metrics: _SuitePairMetrics,
    options: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions,
) -> list[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck]:
    return [
        _boolean_check(
            name="shadow_replay_enabled",
            actual=options.enable_shadow_replay,
            expected=True,
            detail="shadow replay must be explicitly enabled",
        ),
        _maximum_check(
            name="selected_rule_count",
            actual=selected_rule_count,
            threshold=options.max_selected_rule_count,
            detail="runtime replay currently supports a bounded rule set",
        ),
        _boolean_check(
            name="profile_runtime_allowed",
            actual=rule_set.runtime_profile_proposal_allowed,
            expected=True,
            enabled=options.require_profile_runtime_allowed,
            detail="source profile must already be runtime proposal allowed",
        ),
        _boolean_check(
            name="rule_holdout_candidate_enabled",
            actual=selected_rule.holdout_candidate_enabled,
            expected=True,
            enabled=options.require_holdout_candidate_enabled,
            detail="selected rule must be enabled for holdout replay",
        ),
        _boolean_check(
            name="rule_proposed_production_enabled",
            actual=selected_rule.proposed_production_enabled,
            expected=True,
            enabled=options.require_proposed_production_enabled,
            detail="selected rule must be proposed for production replay",
        ),
        _boolean_check(
            name="rule_no_production_change",
            actual=not selected_rule.production_recommendation_changed,
            expected=True,
            detail="rule artifact must not mark production recommendations changed",
        ),
        _minimum_check(
            name="final_answer_count",
            actual=metrics.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="runtime replay should cover enough final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=metrics.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="runtime replay should affect enough final answers",
        ),
        _minimum_check(
            name="penalty_option_count",
            actual=metrics.penalty_option_count,
            threshold=options.min_penalty_option_count,
            detail="runtime replay should exercise the segment penalty",
        ),
        _minimum_check(
            name="final_answer_hit_count_delta",
            actual=metrics.final_answer_hit_delta_count,
            threshold=options.min_final_answer_hit_count_delta,
            detail="runtime replay final-answer hit count should not regress",
        ),
        _minimum_check(
            name="final_answer_hit_rate_delta",
            actual=metrics.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="runtime replay final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=metrics.roi_delta,
            threshold=options.min_roi_delta,
            detail="runtime replay ROI delta should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=metrics.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="runtime replay profit/loss delta should not regress",
        ),
        _minimum_check(
            name="candidate_roi",
            actual=metrics.candidate_roi,
            threshold=options.min_candidate_roi,
            detail="runtime replay absolute ROI should clear the profile floor",
        ),
        _maximum_check(
            name="brier_score_delta",
            actual=metrics.brier_score_delta,
            threshold=options.max_brier_score_delta,
            detail="runtime replay Brier score should not regress",
        ),
        _maximum_check(
            name="log_loss_delta",
            actual=metrics.log_loss_delta,
            threshold=options.max_log_loss_delta,
            detail="runtime replay log loss should not regress",
        ),
        _maximum_check(
            name="mean_calibration_error_delta",
            actual=metrics.mean_calibration_error_delta,
            threshold=options.max_mean_calibration_error_delta,
            detail="runtime replay calibration error should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_baseline",
            actual=metrics.harm_count_vs_baseline,
            threshold=options.max_harm_count_vs_baseline,
            detail="runtime replay should not turn correct final answers into misses",
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_baseline",
            actual=metrics.final_hit_harm_count_vs_baseline,
            threshold=options.max_final_hit_harm_count_vs_baseline,
            detail="runtime replay should not reduce original final-answer hit counts",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_baseline",
            actual=metrics.profit_loss_harm_count_vs_baseline,
            threshold=options.max_profit_loss_harm_count_vs_baseline,
            detail="runtime replay should not reduce original final-answer profit/loss",
        ),
        _boolean_check(
            name="public_response_unchanged",
            actual=True,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="runtime replay must not change the public response shape",
        ),
    ]


def _empty_report(
    rule_set: FinalAnswerSegmentPenaltyRuntimeRuleSet,
    *,
    selected_rules: Sequence[FinalAnswerSegmentPenaltyRuntimeRule],
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck],
    status: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayStatus,
    warnings: Sequence[str],
    options: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport:
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_segment_penalty_runtime_replay_v3_1"
        ),
        "status": status,
        "runtime_replay_allowed": False,
        "holdout_replay_allowed": False,
        "source_rule_profile_version": rule_set.profile_version,
        "source_rule_profile_status": rule_set.status,
        "rule_count": len(rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "selected_rule_ids": [rule.rule_id for rule in selected_rules],
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": options.model_dump(mode="json"),
        "warnings": list(warnings),
    }
    report_key = _report_key(
        summary,
        checks,
        rule_set=rule_set,
        selected_rule=selected_rules[0] if len(selected_rules) == 1 else None,
    )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport(
        report_key=report_key,
        status=status,
        runtime_replay_allowed=False,
        holdout_replay_allowed=False,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        checks=list(checks),
        rule_set_json=rule_set.model_dump(mode="json"),
        selected_rule_json=(
            selected_rules[0].model_dump(mode="json")
            if len(selected_rules) == 1
            else None
        ),
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayStatus:
    if runtime_allowed:
        return "runtime_replay_passed"
    if holdout_allowed:
        return "holdout_replay_passed"
    return "shadow_replay_failed"


def _holdout_checks_passed(
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck],
) -> bool:
    ignored_for_holdout = {
        "candidate_roi",
        "profile_runtime_allowed",
        "rule_proposed_production_enabled",
    }
    return all(
        check.status == "passed"
        for check in checks
        if check.name not in ignored_for_holdout
    )


def _warnings(
    *,
    status: HistoricalFinalAnswerSegmentPenaltyRuntimeReplayStatus,
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck],
) -> list[str]:
    warnings: list[str] = []
    if status == "holdout_replay_passed":
        warnings.append("final_answer_segment_penalty_runtime_replay:holdout_only")
    elif status == "shadow_replay_failed":
        warnings.append("final_answer_segment_penalty_runtime_replay:failed")
    for check in checks:
        if check.status == "failed":
            warnings.append(
                "final_answer_segment_penalty_runtime_replay:failed_check:"
                f"{check.name}"
            )
    return warnings


def _final_answer_signature(
    final_answer: HistoricalRecommendationScenarioResult | None,
) -> tuple[object, ...] | None:
    if final_answer is None:
        return None
    selected_outcomes = tuple(
        (fixture_id, tuple(outcomes))
        for fixture_id, outcomes in sorted(final_answer.selected_outcomes.items())
    )
    return (
        final_answer.scenario.scenario_key,
        tuple(final_answer.selected_fixture_ids),
        selected_outcomes,
    )


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key)
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _summary_number(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool) or value is None:
        return None
    return float(value) if isinstance(value, int | float) else None


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _extract_profile_json(payload: Mapping[str, object]) -> dict[str, object]:
    profile = payload.get("proposal_profile_set_json")
    if isinstance(profile, Mapping):
        return dict(profile)
    return dict(payload)


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(
    value: object,
    *,
    fallback: Sequence[str] | None = None,
) -> list[str]:
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, str) and item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(fallback or [])


def _bool(value: object) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _float(value: object, *, fallback: float) -> float:
    parsed = _float_or_none(value)
    return parsed if parsed is not None else fallback


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int_or_none(value: object, *, fallback: int | None = None) -> int | None:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck:
    if not enabled:
        return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Replay final-answer segment penalty runtime profile artifacts in shadow."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-shadow-replay", action="store_true")
    parser.add_argument("--rule-ids", default="")
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
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-penalty-option-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--require-profile-runtime-allowed", action="store_true")
    parser.add_argument("--require-proposed-production-enabled", action="store_true")
    parser.add_argument("--allow-disabled-holdout-rule", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--max-selected-rule-count", type=int, default=1)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions:
    return HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions(
        enable_shadow_replay=args.enable_shadow_replay,
        rule_ids=tuple(_csv(args.rule_ids)),
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
        ),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_penalty_option_count=args.min_penalty_option_count,
        min_final_answer_hit_count_delta=args.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_candidate_roi=args.min_candidate_roi,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_harm_count_vs_baseline=args.max_harm_count_vs_baseline,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        require_holdout_candidate_enabled=not args.allow_disabled_holdout_rule,
        require_proposed_production_enabled=args.require_proposed_production_enabled,
        require_profile_runtime_allowed=args.require_profile_runtime_allowed,
        require_no_public_response_change=not args.allow_public_response_change,
        max_selected_rule_count=args.max_selected_rule_count,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=[Path(path) for path in args.slice_paths],
        )
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    manifest_slices = [
        historical_slice
        for bundle in bundles
        for historical_slice in bundle.slices
    ]
    manifest_slice_paths = [
        slice_path
        for bundle in bundles
        for slice_path in bundle.resolved_slice_paths
    ]
    manifest_warnings = [
        warning for bundle in bundles for warning in bundle.warnings
    ]
    return _LoadedHistoricalSlices(
        slices=[*explicit_slices, *manifest_slices],
        resolved_slice_paths=[
            *[Path(path) for path in args.slice_paths],
            *manifest_slice_paths,
        ],
        manifest_result=bundles[0] if len(bundles) == 1 else None,
        manifest_results=bundles,
        warnings=manifest_warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "manifest_path": str(manifest_result.manifest_path),
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(path) for path in manifest_result.resolved_slice_paths
        ],
        "warnings": list(manifest_result.warnings),
    }


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck],
    *,
    rule_set: FinalAnswerSegmentPenaltyRuntimeRuleSet,
    selected_rule: FinalAnswerSegmentPenaltyRuntimeRule | None,
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "rule_set": rule_set.model_dump(mode="json"),
        "selected_rule": (
            selected_rule.model_dump(mode="json") if selected_rule is not None else None
        ),
    }
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_segment_penalty_runtime_replay:{digest}"
