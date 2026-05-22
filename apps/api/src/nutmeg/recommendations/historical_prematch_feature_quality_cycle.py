from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridReport,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    HistoricalPrematchFeatureFinalAnswerGateOptions,
    HistoricalPrematchFeatureFinalAnswerGateReport,
    _load_grid_report,
    build_historical_prematch_feature_final_answer_gate_report,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    _options_from_args as _final_answer_gate_options_from_args,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPrematchFeatureQualityCycleStatus = Literal["passed", "failed"]

DEFAULT_PREMATCH_FEATURE_QUALITY_CYCLE_ID = (
    "prematch-feature-quality-cycle-shadow-v3.1"
)


class HistoricalPrematchFeatureQualityCycleOptions(BaseModel):
    cycle_id: str = DEFAULT_PREMATCH_FEATURE_QUALITY_CYCLE_ID
    final_answer_gate_options: HistoricalPrematchFeatureFinalAnswerGateOptions = Field(
        default_factory=HistoricalPrematchFeatureFinalAnswerGateOptions
    )
    require_passing_final_answer_candidate: bool = True
    max_cycle_warning_count: int | None = Field(default=None, ge=0)


class HistoricalPrematchFeatureQualityCycleResult(BaseModel):
    cycle_key: str
    status: HistoricalPrematchFeatureQualityCycleStatus
    passed: bool
    cycle_id: str
    final_answer_gate_report_key: str
    final_answer_gate_report_path: Path | None = None
    grid_report_key: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    evaluated_candidate_count: int = Field(ge=0)
    passing_candidate_count: int = Field(ge=0)
    best_feature_grid_candidate_id: str
    best_feature_grid_rank: int = Field(ge=1)
    best_passed_final_answer_gate: bool
    best_suite_status: str
    best_quality_gate_key: str
    best_quality_gate_passed: bool
    best_failed_quality_check_names: list[str] = Field(default_factory=list)
    best_deltas_json: dict[str, object] = Field(default_factory=dict)
    final_answer_gate_summary_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def run_historical_prematch_feature_quality_cycle(
    historical_slices: Sequence[HistoricalRecommendationSlice] = (),
    *,
    options: HistoricalPrematchFeatureQualityCycleOptions | None = None,
    grid_report: HistoricalPrematchFeatureAblationGridReport | None = None,
    final_answer_gate_report: HistoricalPrematchFeatureFinalAnswerGateReport | None = None,
    final_answer_gate_report_path: Path | None = None,
    final_answer_gate_output_path: Path | None = None,
    extra_warnings: Sequence[str] = (),
) -> HistoricalPrematchFeatureQualityCycleResult:
    resolved_options = options or HistoricalPrematchFeatureQualityCycleOptions()
    gate_report = final_answer_gate_report
    if gate_report is None:
        if not historical_slices:
            raise ValueError(
                "historical slices are required when final_answer_gate_report is not provided"
            )
        gate_report = build_historical_prematch_feature_final_answer_gate_report(
            historical_slices,
            options=resolved_options.final_answer_gate_options,
            grid_report=grid_report,
        )

    if final_answer_gate_output_path is not None:
        final_answer_gate_output_path.parent.mkdir(parents=True, exist_ok=True)
        final_answer_gate_output_path.write_text(
            f"{gate_report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )

    warnings = _cycle_warnings(gate_report, options=resolved_options)
    warnings = _dedupe_strings([*extra_warnings, *warnings])
    passed = _cycle_passed(
        gate_report,
        warnings=warnings,
        options=resolved_options,
    )
    cycle_key = _cycle_key(gate_report, options=resolved_options)
    return _cycle_result(
        cycle_key=cycle_key,
        status="passed" if passed else "failed",
        passed=passed,
        options=resolved_options,
        gate_report=gate_report,
        final_answer_gate_report_path=(
            final_answer_gate_report_path or final_answer_gate_output_path
        ),
        warnings=warnings,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    final_answer_gate_report = _load_final_answer_gate_report(
        args.final_answer_gate_report_path
    )
    grid_report = _load_grid_report(args.grid_report_path)
    result = run_historical_prematch_feature_quality_cycle(
        loaded_slices.slices,
        options=_options_from_args(args),
        grid_report=grid_report,
        final_answer_gate_report=final_answer_gate_report,
        final_answer_gate_report_path=args.final_answer_gate_report_path,
        final_answer_gate_output_path=args.final_answer_gate_output_path,
        extra_warnings=loaded_slices.warnings,
    )
    if loaded_slices.manifest_result is not None:
        result.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{result.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _cycle_result(
    *,
    cycle_key: str,
    status: HistoricalPrematchFeatureQualityCycleStatus,
    passed: bool,
    options: HistoricalPrematchFeatureQualityCycleOptions,
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    final_answer_gate_report_path: Path | None,
    warnings: Sequence[str],
) -> HistoricalPrematchFeatureQualityCycleResult:
    best = gate_report.best_evaluation
    failed_check_names = [
        check.name for check in best.quality_gate.checks if check.status == "failed"
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_quality_cycle_v3_1",
        "cycle_key": cycle_key,
        "cycle_id": options.cycle_id,
        "status": status,
        "passed": passed,
        "shadow_only": True,
        "require_passing_final_answer_candidate": (
            options.require_passing_final_answer_candidate
        ),
        "max_cycle_warning_count": options.max_cycle_warning_count,
        "final_answer_gate_report_key": gate_report.report_key,
        "final_answer_gate_report_path": (
            str(final_answer_gate_report_path)
            if final_answer_gate_report_path is not None
            else None
        ),
        "grid_report_key": gate_report.grid_report_key,
        "slice_count": gate_report.slice_count,
        "fixture_count": gate_report.fixture_count,
        "evaluated_candidate_count": gate_report.evaluated_candidate_count,
        "passing_candidate_count": gate_report.passing_candidate_count,
        "best_feature_grid_candidate_id": best.feature_grid_candidate_id,
        "best_feature_grid_rank": best.feature_grid_rank,
        "best_passed_final_answer_gate": best.passed_final_answer_gate,
        "best_suite_status": best.suite.status,
        "best_quality_gate_key": best.quality_gate.gate_key,
        "best_quality_gate_passed": best.quality_gate.passed,
        "best_failed_quality_check_names": failed_check_names,
        "best_deltas": best.deltas_json,
        "warnings": list(warnings),
    }
    return HistoricalPrematchFeatureQualityCycleResult(
        cycle_key=cycle_key,
        status=status,
        passed=passed,
        cycle_id=options.cycle_id,
        final_answer_gate_report_key=gate_report.report_key,
        final_answer_gate_report_path=final_answer_gate_report_path,
        grid_report_key=gate_report.grid_report_key,
        slice_count=gate_report.slice_count,
        fixture_count=gate_report.fixture_count,
        evaluated_candidate_count=gate_report.evaluated_candidate_count,
        passing_candidate_count=gate_report.passing_candidate_count,
        best_feature_grid_candidate_id=best.feature_grid_candidate_id,
        best_feature_grid_rank=best.feature_grid_rank,
        best_passed_final_answer_gate=best.passed_final_answer_gate,
        best_suite_status=best.suite.status,
        best_quality_gate_key=best.quality_gate.gate_key,
        best_quality_gate_passed=best.quality_gate.passed,
        best_failed_quality_check_names=failed_check_names,
        best_deltas_json=dict(best.deltas_json),
        final_answer_gate_summary_json=dict(gate_report.summary_json),
        warnings=list(warnings),
        summary_json=summary,
    )


def _cycle_passed(
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    *,
    warnings: Sequence[str],
    options: HistoricalPrematchFeatureQualityCycleOptions,
) -> bool:
    if (
        options.require_passing_final_answer_candidate
        and gate_report.passing_candidate_count <= 0
    ):
        return False
    return not (
        options.max_cycle_warning_count is not None
        and len(warnings) > options.max_cycle_warning_count
    )


def _cycle_warnings(
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    *,
    options: HistoricalPrematchFeatureQualityCycleOptions,
) -> list[str]:
    warnings = list(gate_report.warnings)
    if (
        options.require_passing_final_answer_candidate
        and gate_report.passing_candidate_count <= 0
    ):
        warnings.append(
            "prematch_feature_quality_cycle:no_passing_final_answer_candidate"
        )
    if (
        options.max_cycle_warning_count is not None
        and len(warnings) > options.max_cycle_warning_count
    ):
        warnings.append("prematch_feature_quality_cycle:max_warning_count_exceeded")
    return _dedupe_strings(warnings)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run the frozen historical prematch feature final-answer gate as a "
            "compact periodic quality cycle."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--grid-report-path", type=Path)
    parser.add_argument("--final-answer-gate-report-path", type=Path)
    parser.add_argument("--final-answer-gate-output-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--cycle-id", default=DEFAULT_PREMATCH_FEATURE_QUALITY_CYCLE_ID)
    parser.add_argument("--gate-id", default="prematch-feature-final-answer-gate-shadow-v3.1")
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
    parser.add_argument("--allow-no-passing-final-answer-candidate", action="store_true")
    parser.add_argument("--max-cycle-warning-count", type=int)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if (
        not args.slice_paths
        and args.suite_manifest is None
        and args.final_answer_gate_report_path is None
    ):
        parser.error(
            "provide at least one slice path, --suite-manifest, or "
            "--final-answer-gate-report-path"
        )
    return args


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureQualityCycleOptions:
    return HistoricalPrematchFeatureQualityCycleOptions(
        cycle_id=args.cycle_id,
        final_answer_gate_options=_final_answer_gate_options_from_args(args),
        require_passing_final_answer_candidate=(
            not args.allow_no_passing_final_answer_candidate
        ),
        max_cycle_warning_count=args.max_cycle_warning_count,
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


def _load_final_answer_gate_report(
    path: Path | None,
) -> HistoricalPrematchFeatureFinalAnswerGateReport | None:
    if path is None:
        return None
    return HistoricalPrematchFeatureFinalAnswerGateReport.model_validate_json(
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


def _cycle_key(
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    *,
    options: HistoricalPrematchFeatureQualityCycleOptions,
) -> str:
    payload = {
        "cycle_id": options.cycle_id,
        "final_answer_gate_report_key": gate_report.report_key,
        "grid_report_key": gate_report.grid_report_key,
        "slice_count": gate_report.slice_count,
        "fixture_count": gate_report.fixture_count,
        "passing_candidate_count": gate_report.passing_candidate_count,
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_quality_cycle:{digest}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped
