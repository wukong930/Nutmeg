from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_roi_floor_spec_plan as spec_plan,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

RoiFloorSpecPlanReport = (
    spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorSpecPlanReport
)
SelectionValueSearchReport = (
    value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport
)

type HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchStatus = Literal[
    "batch_search_passed",
    "batch_search_no_acceptance",
    "source_plan_not_ready",
    "empty_batch",
]


class HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions(BaseModel):
    batch_index: int = Field(default=0, ge=0)
    batch_size: int = Field(default=2, ge=1, le=20)
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_affected_leg_count: int = Field(default=1, ge=0)
    min_final_answer_count: int = Field(default=100, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    include_movement_diagnostics: bool = True
    movement_diagnostics_limit: int = Field(default=12, ge=1, le=500)


class HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchStatus
    source_spec_plan_report_key: str
    source_spec_plan_status: str
    source_roi_floor_gap_report_key: str
    batch_index: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    batch_start: int = Field(ge=0)
    batch_end: int = Field(ge=0)
    planned_spec_count: int = Field(ge=0)
    executed_spec_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    best_candidate_key: str | None = None
    accepted_candidate_keys: list[str] = Field(default_factory=list)
    candidate_roi_floor: float
    strict_thresholds_json: dict[str, object] = Field(default_factory=dict)
    search_report_json: dict[str, object] | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_final_answer_selection_value_signal_roi_floor_batch_search_report(
    path: Path | str,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport:
    return (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def build_historical_final_answer_selection_value_signal_roi_floor_batch_search_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    plan_report: RoiFloorSpecPlanReport,
    options: (
        HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport:
    resolved_options = (
        options
        or HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions()
    )
    batch_start = resolved_options.batch_index * resolved_options.batch_size
    batch_end = min(batch_start + resolved_options.batch_size, plan_report.spec_count)
    warnings: list[str] = []
    search_report: SelectionValueSearchReport | None = None
    if plan_report.status != "plan_ready":
        warnings.append("selection_value_signal_roi_floor_batch_search:plan_not_ready")
        status: HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchStatus = (
            "source_plan_not_ready"
        )
    else:
        planned_specs = plan_report.planned_specs[batch_start:batch_end]
        if not planned_specs:
            warnings.append("selection_value_signal_roi_floor_batch_search:empty_batch")
            status = "empty_batch"
        else:
            search_report = (
                value_search.build_historical_final_answer_selection_value_signal_search_report(
                    historical_slices,
                    options=_search_options(
                        planned_specs,
                        options=resolved_options,
                    ),
                )
            )
            status = (
                "batch_search_passed"
                if search_report.accepted_count > 0
                else "batch_search_no_acceptance"
            )
    accepted_candidate_keys = (
        [candidate.candidate_key for candidate in search_report.accepted_candidates]
        if search_report is not None
        else []
    )
    best_candidate_key = (
        search_report.best_candidate.candidate_key
        if search_report is not None and search_report.best_candidate is not None
        else None
    )
    strict_thresholds = _strict_thresholds_json(resolved_options)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_selection_value_signal_roi_floor_batch_search_v3_1"
        ),
        "status": status,
        "source_spec_plan_report_key": plan_report.report_key,
        "source_spec_plan_status": plan_report.status,
        "source_roi_floor_gap_report_key": plan_report.source_roi_floor_gap_report_key,
        "batch_index": resolved_options.batch_index,
        "batch_size": resolved_options.batch_size,
        "batch_start": batch_start,
        "batch_end": batch_end,
        "planned_spec_count": plan_report.spec_count,
        "executed_spec_count": (
            0 if search_report is None else search_report.candidate_count
        ),
        "accepted_count": 0 if search_report is None else search_report.accepted_count,
        "rejected_count": 0 if search_report is None else search_report.rejected_count,
        "best_candidate_key": best_candidate_key,
        "accepted_candidate_keys": accepted_candidate_keys,
        "candidate_roi_floor": resolved_options.min_candidate_roi,
        "strict_thresholds": strict_thresholds,
        "search_report_key": (
            search_report.report_key if search_report is not None else None
        ),
        "warnings": warnings,
    }
    report_key = _report_key(
        summary,
        search_report.model_dump(mode="json") if search_report is not None else None,
    )
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchReport(
        report_key=report_key,
        status=status,
        source_spec_plan_report_key=plan_report.report_key,
        source_spec_plan_status=plan_report.status,
        source_roi_floor_gap_report_key=plan_report.source_roi_floor_gap_report_key,
        batch_index=resolved_options.batch_index,
        batch_size=resolved_options.batch_size,
        batch_start=batch_start,
        batch_end=batch_end,
        planned_spec_count=plan_report.spec_count,
        executed_spec_count=(
            0 if search_report is None else search_report.candidate_count
        ),
        accepted_count=0 if search_report is None else search_report.accepted_count,
        rejected_count=0 if search_report is None else search_report.rejected_count,
        best_candidate_key=best_candidate_key,
        accepted_candidate_keys=accepted_candidate_keys,
        candidate_roi_floor=resolved_options.min_candidate_roi,
        strict_thresholds_json=strict_thresholds,
        search_report_json=(
            search_report.model_dump(mode="json") if search_report is not None else None
        ),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_final_answer_selection_value_signal_roi_floor_batch_search_report(
        _historical_slices_from_args(args),
        plan_report=spec_plan.load_historical_final_answer_selection_value_signal_roi_floor_spec_plan_report(
            args.spec_plan_report
        ),
        options=_options_from_args(args),
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
    if report.status != "batch_search_passed" and not args.no_fail_process:
        raise SystemExit(1)


def _search_options(
    planned_specs: Sequence[
        spec_plan.HistoricalFinalAnswerSelectionValueSignalRoiFloorPlannedSpec
    ],
    *,
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions,
) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions:
    return value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions(
        candidate_specs=tuple(planned_spec.spec for planned_spec in planned_specs),
        backtest_options=options.backtest_options,
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
        min_affected_leg_count=options.min_affected_leg_count,
        min_final_answer_count=options.min_final_answer_count,
        min_changed_final_answer_count=options.min_changed_final_answer_count,
        min_final_answer_hit_count_delta=options.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=options.min_final_answer_hit_rate_delta,
        min_roi_delta=options.min_roi_delta,
        min_profit_loss_delta=options.min_profit_loss_delta,
        min_candidate_roi=options.min_candidate_roi,
        max_brier_score_delta=options.max_brier_score_delta,
        max_log_loss_delta=options.max_log_loss_delta,
        max_mean_calibration_error_delta=options.max_mean_calibration_error_delta,
        max_final_hit_harm_count_vs_baseline=(
            options.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            options.max_profit_loss_harm_count_vs_baseline
        ),
        include_movement_diagnostics=options.include_movement_diagnostics,
        movement_diagnostics_limit=options.movement_diagnostics_limit,
    )


def _strict_thresholds_json(
    options: HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions,
) -> dict[str, object]:
    return {
        "min_affected_leg_count": options.min_affected_leg_count,
        "min_final_answer_count": options.min_final_answer_count,
        "min_changed_final_answer_count": options.min_changed_final_answer_count,
        "min_final_answer_hit_count_delta": options.min_final_answer_hit_count_delta,
        "min_final_answer_hit_rate_delta": options.min_final_answer_hit_rate_delta,
        "min_roi_delta": options.min_roi_delta,
        "min_profit_loss_delta": options.min_profit_loss_delta,
        "min_candidate_roi": options.min_candidate_roi,
        "max_brier_score_delta": options.max_brier_score_delta,
        "max_log_loss_delta": options.max_log_loss_delta,
        "max_mean_calibration_error_delta": options.max_mean_calibration_error_delta,
        "max_final_hit_harm_count_vs_baseline": (
            options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            options.max_profit_loss_harm_count_vs_baseline
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run a small strict-search batch from ROI-floor planned specs."
    )
    parser.add_argument("spec_plan_report", type=Path)
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument(
        "--pass-types",
        default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES),
    )
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
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=3)
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
    parser.add_argument("--min-affected-leg-count", type=int, default=1)
    parser.add_argument("--min-final-answer-count", type=int, default=100)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--movement-diagnostics-limit", type=int, default=12)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions:
    return HistoricalFinalAnswerSelectionValueSignalRoiFloorBatchSearchOptions(
        batch_index=args.batch_index,
        batch_size=args.batch_size,
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
            final_answer_scenario_variant_count=(
                args.final_answer_scenario_variant_count
            ),
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        min_affected_leg_count=args.min_affected_leg_count,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_count_delta=args.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_candidate_roi=args.min_candidate_roi,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        movement_diagnostics_limit=args.movement_diagnostics_limit,
    )


def _historical_slices_from_args(args: Namespace) -> list[HistoricalRecommendationSlice]:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        return explicit_slices
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    return [
        historical_slice
        for bundle in bundles
        for historical_slice in bundle.slices
    ] + explicit_slices


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _report_key(
    summary: Mapping[str, object],
    search_report_json: Mapping[str, object] | None,
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "search_report": search_report_json,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_selection_value_signal_roi_floor_batch_search:{digest}"


if __name__ == "__main__":
    main()
