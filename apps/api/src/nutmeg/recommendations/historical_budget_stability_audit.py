from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationMode,
    RecommendationStrategy,
)

type HistoricalBudgetStabilityAuditStatus = Literal["generated"]


class HistoricalBudgetBacktestRunner(Protocol):
    def __call__(
        self,
        historical_slice: HistoricalRecommendationSlice,
        *,
        options: HistoricalRecommendationBacktestOptions,
    ) -> HistoricalRecommendationBacktestResult: ...


class HistoricalBudgetStabilityAuditOptions(BaseModel):
    budgets: tuple[float, ...] = (10.0, 20.0, 50.0)
    reference_budget: float | None = Field(default=None, gt=0.0)
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    heavy_budget_adjustment_quality_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
    )
    top_change_limit: int = Field(default=20, ge=1, le=200)


class HistoricalBudgetRunSummary(BaseModel):
    budget: float = Field(gt=0.0)
    final_answer_count: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_stake: float = Field(ge=0.0)
    profit_loss: float
    roi: float | None = None
    average_total_stake: float | None = Field(default=None, ge=0.0)
    multiple_final_answer_count: int = Field(ge=0)
    budget_adjusted_final_answer_count: int = Field(ge=0)
    heavy_budget_adjusted_final_answer_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)


class HistoricalBudgetStabilitySliceChange(BaseModel):
    slice_id: str
    budget: float = Field(gt=0.0)
    reference_budget: float = Field(gt=0.0)
    signature_changed: bool
    reference_signature: str | None = None
    budget_signature: str | None = None
    reference_scenario_key: str | None = None
    budget_scenario_key: str | None = None
    reference_pass_type: str | None = None
    budget_pass_type: str | None = None
    reference_mode: RecommendationMode | None = None
    budget_mode: RecommendationMode | None = None
    reference_actual_hit: bool | None = None
    budget_actual_hit: bool | None = None
    hit_delta: int = 0
    profit_loss_delta: float = 0.0
    roi_delta: float | None = None
    stake_delta: float = 0.0
    budget_adjustment_applied: bool = False
    budget_adjustment_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    harmful_change: bool = False
    beneficial_change: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalBudgetStabilityComparisonSummary(BaseModel):
    budget: float = Field(gt=0.0)
    reference_budget: float = Field(gt=0.0)
    comparable_count: int = Field(ge=0)
    signature_changed_count: int = Field(ge=0)
    signature_change_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    harmful_change_count: int = Field(ge=0)
    beneficial_change_count: int = Field(ge=0)
    hit_delta_count: int
    profit_loss_delta: float
    roi_delta: float | None = None
    stake_delta: float
    budget_adjusted_change_count: int = Field(ge=0)


class HistoricalBudgetStabilityAuditReport(BaseModel):
    report_key: str
    status: HistoricalBudgetStabilityAuditStatus
    slice_count: int = Field(ge=0)
    budgets: tuple[float, ...]
    reference_budget: float = Field(gt=0.0)
    budget_runs: list[HistoricalBudgetRunSummary] = Field(default_factory=list)
    comparison_summaries: list[HistoricalBudgetStabilityComparisonSummary] = Field(
        default_factory=list
    )
    changed_slice_count: int = Field(ge=0)
    harmful_change_count: int = Field(ge=0)
    beneficial_change_count: int = Field(ge=0)
    top_changes: list[HistoricalBudgetStabilitySliceChange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifests: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


def build_historical_budget_stability_audit_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalBudgetStabilityAuditOptions | None = None,
    backtest_runner: HistoricalBudgetBacktestRunner = run_historical_recommendation_backtest,
) -> HistoricalBudgetStabilityAuditReport:
    resolved_options = options or HistoricalBudgetStabilityAuditOptions()
    budgets = _resolved_budgets(resolved_options)
    reference_budget = _reference_budget(resolved_options, budgets=budgets)
    warnings: list[str] = []
    if reference_budget not in budgets:
        warnings.append("budget_stability:reference_budget_added_to_budget_set")
        budgets = tuple([*budgets, reference_budget])

    results_by_budget = {
        budget: [
            backtest_runner(
                historical_slice,
                options=resolved_options.backtest_options.model_copy(
                    update={"max_budget": budget}
                ),
            )
            for historical_slice in historical_slices
        ]
        for budget in budgets
    }
    budget_runs = [
        _budget_run_summary(
            budget,
            results,
            heavy_budget_adjustment_quality_threshold=(
                resolved_options.heavy_budget_adjustment_quality_threshold
            ),
        )
        for budget, results in results_by_budget.items()
    ]
    reference_results = {
        result.slice_id: result for result in results_by_budget[reference_budget]
    }
    changes = [
        _slice_change(
            budget_result,
            reference_result=reference_results[budget_result.slice_id],
            budget=budget,
            reference_budget=reference_budget,
            heavy_budget_adjustment_quality_threshold=(
                resolved_options.heavy_budget_adjustment_quality_threshold
            ),
        )
        for budget, budget_results in results_by_budget.items()
        if budget != reference_budget
        for budget_result in budget_results
        if budget_result.slice_id in reference_results
    ]
    comparison_summaries = [
        _comparison_summary(
            budget,
            reference_budget=reference_budget,
            changes=[change for change in changes if change.budget == budget],
            budget_run=_budget_run_for_budget(budget_runs, budget),
            reference_run=_budget_run_for_budget(budget_runs, reference_budget),
        )
        for budget in budgets
        if budget != reference_budget
    ]
    changed = [change for change in changes if change.signature_changed]
    top_changes = sorted(
        changed,
        key=lambda change: (
            not change.harmful_change,
            change.profit_loss_delta,
            change.hit_delta,
            change.budget,
            change.slice_id,
        ),
    )[: resolved_options.top_change_limit]
    summary: dict[str, object] = {
        "calculation_basis": "historical_budget_stability_audit_v3_1",
        "slice_count": len(historical_slices),
        "budgets": list(budgets),
        "reference_budget": reference_budget,
        "changed_slice_count": len({change.slice_id for change in changed}),
        "signature_changed_count": len(changed),
        "harmful_change_count": sum(1 for change in changed if change.harmful_change),
        "beneficial_change_count": sum(
            1 for change in changed if change.beneficial_change
        ),
        "budget_runs": [run.model_dump(mode="json") for run in budget_runs],
        "comparison_summaries": [
            summary.model_dump(mode="json") for summary in comparison_summaries
        ],
        "top_change_slice_ids": [change.slice_id for change in top_changes],
        "warnings": warnings,
    }
    report_key = _report_key(summary, top_changes)
    return HistoricalBudgetStabilityAuditReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        budgets=budgets,
        reference_budget=reference_budget,
        budget_runs=budget_runs,
        comparison_summaries=comparison_summaries,
        changed_slice_count=len({change.slice_id for change in changed}),
        harmful_change_count=sum(1 for change in changed if change.harmful_change),
        beneficial_change_count=sum(1 for change in changed if change.beneficial_change),
        top_changes=top_changes,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_budget_stability_audit_report(
    path: Path | str,
) -> HistoricalBudgetStabilityAuditReport:
    return HistoricalBudgetStabilityAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    report = build_historical_budget_stability_audit_report(
        loaded.slices,
        options=_options_from_args(args),
    )
    if loaded.warnings:
        report = report.model_copy(
            update={
                "warnings": [*report.warnings, *loaded.warnings],
                "summary_json": {
                    **report.summary_json,
                    "manifest_warnings": loaded.warnings,
                    "suite_manifests": [
                        _manifest_summary(manifest_bundle)
                        for manifest_bundle in loaded.manifests
                    ],
                },
            }
        )
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


def _budget_run_summary(
    budget: float,
    results: Sequence[HistoricalRecommendationBacktestResult],
    *,
    heavy_budget_adjustment_quality_threshold: float,
) -> HistoricalBudgetRunSummary:
    final_results = [result for result in results if result.final_answer is not None]
    final_hit_count = 0
    multiple_final_answer_count = 0
    for result in final_results:
        final_answer = result.final_answer
        if final_answer is None:
            continue
        if final_answer.actual_hit:
            final_hit_count += 1
        if final_answer.scenario.mode == "multiple":
            multiple_final_answer_count += 1
    total_stake = sum(result.total_stake for result in final_results)
    profit_loss = sum(result.profit_loss for result in final_results)
    budget_adjustment_qualities = [
        quality
        for result in final_results
        for quality in [_budget_adjustment_quality(result)]
        if quality is not None
    ]
    return HistoricalBudgetRunSummary(
        budget=budget,
        final_answer_count=len(final_results),
        final_hit_count=final_hit_count,
        final_hit_rate=_ratio(final_hit_count, len(final_results)),
        total_stake=total_stake,
        profit_loss=profit_loss,
        roi=(profit_loss / total_stake if total_stake > 0 else None),
        average_total_stake=_ratio_float(total_stake, len(final_results)),
        multiple_final_answer_count=multiple_final_answer_count,
        budget_adjusted_final_answer_count=sum(
            1
            for result in final_results
            if _budget_adjustment_payload(result) is not None
        ),
        heavy_budget_adjusted_final_answer_count=sum(
            1
            for quality in budget_adjustment_qualities
            if quality < heavy_budget_adjustment_quality_threshold
        ),
        warning_count=sum(len(result.warnings) for result in results),
    )


def _slice_change(
    budget_result: HistoricalRecommendationBacktestResult,
    *,
    reference_result: HistoricalRecommendationBacktestResult,
    budget: float,
    reference_budget: float,
    heavy_budget_adjustment_quality_threshold: float,
) -> HistoricalBudgetStabilitySliceChange:
    budget_signature = _final_answer_signature(budget_result)
    reference_signature = _final_answer_signature(reference_result)
    signature_changed = budget_signature != reference_signature
    budget_hit = _actual_hit(budget_result)
    reference_hit = _actual_hit(reference_result)
    hit_delta = _hit_int(budget_hit) - _hit_int(reference_hit)
    profit_loss_delta = budget_result.profit_loss - reference_result.profit_loss
    budget_roi = budget_result.roi
    reference_roi = reference_result.roi
    roi_delta = (
        budget_roi - reference_roi
        if budget_roi is not None and reference_roi is not None
        else None
    )
    stake_delta = budget_result.total_stake - reference_result.total_stake
    harmful_change = signature_changed and (
        hit_delta < 0 or profit_loss_delta < -1e-9
    )
    beneficial_change = signature_changed and (
        hit_delta > 0 or profit_loss_delta > 1e-9
    )
    budget_adjustment_quality = _budget_adjustment_quality(budget_result)
    reason_codes = _change_reason_codes(
        signature_changed=signature_changed,
        budget=budget,
        reference_budget=reference_budget,
        hit_delta=hit_delta,
        profit_loss_delta=profit_loss_delta,
        stake_delta=stake_delta,
        budget_adjustment_applied=_budget_adjustment_payload(budget_result)
        is not None,
        budget_adjustment_quality=budget_adjustment_quality,
        heavy_budget_adjustment_quality_threshold=(
            heavy_budget_adjustment_quality_threshold
        ),
        budget_has_final_answer=budget_result.final_answer is not None,
        reference_has_final_answer=reference_result.final_answer is not None,
    )
    return HistoricalBudgetStabilitySliceChange(
        slice_id=budget_result.slice_id,
        budget=budget,
        reference_budget=reference_budget,
        signature_changed=signature_changed,
        reference_signature=reference_signature,
        budget_signature=budget_signature,
        reference_scenario_key=_scenario_key(reference_result),
        budget_scenario_key=_scenario_key(budget_result),
        reference_pass_type=_pass_type(reference_result),
        budget_pass_type=_pass_type(budget_result),
        reference_mode=_mode(reference_result),
        budget_mode=_mode(budget_result),
        reference_actual_hit=reference_hit,
        budget_actual_hit=budget_hit,
        hit_delta=hit_delta,
        profit_loss_delta=profit_loss_delta,
        roi_delta=roi_delta,
        stake_delta=stake_delta,
        budget_adjustment_applied=_budget_adjustment_payload(budget_result) is not None,
        budget_adjustment_quality=budget_adjustment_quality,
        harmful_change=harmful_change,
        beneficial_change=beneficial_change,
        reason_codes=reason_codes,
        summary_json={
            "reference_total_stake": reference_result.total_stake,
            "budget_total_stake": budget_result.total_stake,
            "reference_profit_loss": reference_result.profit_loss,
            "budget_profit_loss": budget_result.profit_loss,
            "reference_selected_outcomes": _selected_outcomes(reference_result),
            "budget_selected_outcomes": _selected_outcomes(budget_result),
            "reason_codes": reason_codes,
        },
    )


def _change_reason_codes(
    *,
    signature_changed: bool,
    budget: float,
    reference_budget: float,
    hit_delta: int,
    profit_loss_delta: float,
    stake_delta: float,
    budget_adjustment_applied: bool,
    budget_adjustment_quality: float | None,
    heavy_budget_adjustment_quality_threshold: float,
    budget_has_final_answer: bool,
    reference_has_final_answer: bool,
) -> list[str]:
    reason_codes: list[str] = []
    reason_codes.append("signature_changed" if signature_changed else "signature_stable")
    if budget < reference_budget:
        reason_codes.append("budget_lower_than_reference")
    elif budget > reference_budget:
        reason_codes.append("budget_higher_than_reference")
    if not reference_has_final_answer:
        reason_codes.append("reference_no_final_answer")
    if not budget_has_final_answer:
        reason_codes.append("budget_no_final_answer")
    if hit_delta < 0:
        reason_codes.append("budget_harmed_hit")
    elif hit_delta > 0:
        reason_codes.append("budget_improved_hit")
    if profit_loss_delta < -1e-9:
        reason_codes.append("budget_profit_loss_lower")
    elif profit_loss_delta > 1e-9:
        reason_codes.append("budget_profit_loss_higher")
    if stake_delta < -1e-9:
        reason_codes.append("budget_stake_lower")
    elif stake_delta > 1e-9:
        reason_codes.append("budget_stake_higher")
    if budget_adjustment_applied:
        reason_codes.append("budget_adjustment_applied")
    if (
        budget_adjustment_quality is not None
        and budget_adjustment_quality < heavy_budget_adjustment_quality_threshold
    ):
        reason_codes.append("heavy_budget_adjustment")
    return reason_codes


def _comparison_summary(
    budget: float,
    *,
    reference_budget: float,
    changes: Sequence[HistoricalBudgetStabilitySliceChange],
    budget_run: HistoricalBudgetRunSummary,
    reference_run: HistoricalBudgetRunSummary,
) -> HistoricalBudgetStabilityComparisonSummary:
    changed = [change for change in changes if change.signature_changed]
    return HistoricalBudgetStabilityComparisonSummary(
        budget=budget,
        reference_budget=reference_budget,
        comparable_count=len(changes),
        signature_changed_count=len(changed),
        signature_change_rate=_ratio(len(changed), len(changes)),
        harmful_change_count=sum(1 for change in changed if change.harmful_change),
        beneficial_change_count=sum(1 for change in changed if change.beneficial_change),
        hit_delta_count=sum(change.hit_delta for change in changes),
        profit_loss_delta=sum(change.profit_loss_delta for change in changes),
        roi_delta=(
            budget_run.roi - reference_run.roi
            if budget_run.roi is not None and reference_run.roi is not None
            else None
        ),
        stake_delta=sum(change.stake_delta for change in changes),
        budget_adjusted_change_count=sum(
            1 for change in changed if change.budget_adjustment_applied
        ),
    )


def _budget_run_for_budget(
    runs: Sequence[HistoricalBudgetRunSummary],
    budget: float,
) -> HistoricalBudgetRunSummary:
    for run in runs:
        if run.budget == budget:
            return run
    raise ValueError(f"missing budget run for {budget}")


def _final_answer_signature(
    result: HistoricalRecommendationBacktestResult,
) -> str | None:
    final_answer = result.final_answer
    if final_answer is None:
        return None
    outcome_parts = [
        f"{fixture_id}:{','.join(outcomes)}"
        for fixture_id, outcomes in sorted(final_answer.selected_outcomes.items())
    ]
    return "|".join(
        [
            final_answer.scenario.scenario_key,
            final_answer.scenario.pass_type,
            final_answer.scenario.mode,
            *outcome_parts,
        ]
    )


def _selected_outcomes(
    result: HistoricalRecommendationBacktestResult,
) -> dict[str, list[str]]:
    if result.final_answer is None:
        return {}
    return {
        fixture_id: list(outcomes)
        for fixture_id, outcomes in result.final_answer.selected_outcomes.items()
    }


def _budget_adjustment_payload(
    result: HistoricalRecommendationBacktestResult,
) -> dict[str, object] | None:
    final_answer = result.final_answer
    if final_answer is None or final_answer.option is None:
        return None
    payload = final_answer.option.selection.explanation_json.get("budget_adjustment")
    return payload if isinstance(payload, dict) else None


def _budget_adjustment_quality(
    result: HistoricalRecommendationBacktestResult,
) -> float | None:
    payload = _budget_adjustment_payload(result)
    if payload is None:
        return None
    raw_quality = payload.get("optimized_quality_score")
    if isinstance(raw_quality, int | float):
        return max(0.0, min(1.0, float(raw_quality)))
    return None


def _actual_hit(result: HistoricalRecommendationBacktestResult) -> bool | None:
    return result.final_answer.actual_hit if result.final_answer is not None else None


def _hit_int(value: bool | None) -> int:
    return 1 if value is True else 0


def _scenario_key(result: HistoricalRecommendationBacktestResult) -> str | None:
    return result.final_answer.scenario.scenario_key if result.final_answer else None


def _pass_type(result: HistoricalRecommendationBacktestResult) -> str | None:
    return result.final_answer.scenario.pass_type if result.final_answer else None


def _mode(result: HistoricalRecommendationBacktestResult) -> RecommendationMode | None:
    return result.final_answer.scenario.mode if result.final_answer else None


def _resolved_budgets(
    options: HistoricalBudgetStabilityAuditOptions,
) -> tuple[float, ...]:
    budgets = tuple(dict.fromkeys(float(budget) for budget in options.budgets))
    if not budgets:
        raise ValueError("provide at least one budget")
    if any(budget <= 0 for budget in budgets):
        raise ValueError("budgets must be positive")
    return budgets


def _reference_budget(
    options: HistoricalBudgetStabilityAuditOptions,
    *,
    budgets: Sequence[float],
) -> float:
    if options.reference_budget is not None:
        return float(options.reference_budget)
    return max(budgets)


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    slices = [load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths]
    manifest_bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in args.suite_manifest
    ]
    manifest_slices = [
        historical_slice
        for manifest_bundle in manifest_bundles
        for historical_slice in manifest_bundle.slices
    ]
    warnings = [
        warning
        for manifest_bundle in manifest_bundles
        for warning in manifest_bundle.warnings
    ]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *slices],
        manifests=manifest_bundles,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_bundle: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_bundle.manifest_path),
        "suite_id": manifest_bundle.manifest.suite_id,
        "slice_count": len(manifest_bundle.slices),
        "warnings": manifest_bundle.warnings,
    }


def _options_from_args(args: Namespace) -> HistoricalBudgetStabilityAuditOptions:
    return HistoricalBudgetStabilityAuditOptions(
        budgets=_float_tuple(args.budgets),
        reference_budget=args.reference_budget,
        heavy_budget_adjustment_quality_threshold=(
            args.heavy_budget_adjustment_quality_threshold
        ),
        top_change_limit=args.top_change_limit,
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=max(_float_tuple(args.budgets)),
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            final_answer_scenario_variant_count=(
                args.final_answer_scenario_variant_count
            ),
            derive_market_context_signals=args.derive_market_context_signals,
        ),
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Audit historical final-answer stability across user budget tiers."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", action="append", type=Path, default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--budgets", default="10,20,50")
    parser.add_argument("--reference-budget", type=float)
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--heavy-budget-adjustment-quality-threshold",
        type=float,
        default=0.50,
    )
    parser.add_argument("--top-change-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _ratio_float(numerator: float, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _report_key(
    summary: dict[str, object],
    top_changes: Sequence[HistoricalBudgetStabilitySliceChange],
) -> str:
    payload = {
        "summary": summary,
        "top_changes": [change.model_dump(mode="json") for change in top_changes],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_budget_stability_audit:{digest}"
