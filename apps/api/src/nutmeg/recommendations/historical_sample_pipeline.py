from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps
from pathlib import Path
from re import sub
from typing import cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
    HistoricalRecommendationSuiteQualityGateResult,
    run_historical_recommendation_suite_quality_gate,
)
from nutmeg.recommendations.historical_sample_quality import (
    HistoricalRecommendationSampleQualityOptions,
    HistoricalRecommendationSampleQualityResult,
    evaluate_historical_recommendation_sample_quality,
)
from nutmeg.recommendations.historical_slice_builder import (
    HistoricalRecommendationSliceBuildOptions,
    build_historical_recommendation_slice_from_csv,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestRefreshOptions,
    HistoricalRecommendationSuiteManifestRefreshResult,
    refresh_historical_recommendation_suite_manifest,
    resolve_historical_recommendation_suite_manifest_slice_paths,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy


class HistoricalRecommendationSamplePipelineBuildDefaults(BaseModel):
    competition_id: str = Field(min_length=1)
    as_of_time_utc: datetime
    result_source: str = Field(min_length=1)
    odds_source: str = Field(min_length=1)
    prediction_source: str = Field(min_length=1)
    season: str | None = None
    source_urls: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    slice_id_prefix: str = ""
    name_prefix: str = ""
    probability_sum_tolerance: float = Field(default=0.02, ge=0.0)


class HistoricalRecommendationSamplePipelineOptions(BaseModel):
    output_dir: Path
    manifest_path: Path
    build_defaults: HistoricalRecommendationSamplePipelineBuildDefaults
    manifest_refresh_options: HistoricalRecommendationSuiteManifestRefreshOptions = Field(
        default_factory=HistoricalRecommendationSuiteManifestRefreshOptions
    )
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=lambda: HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
        )
    )
    gate_options: HistoricalRecommendationSuiteQualityGateOptions = Field(
        default_factory=HistoricalRecommendationSuiteQualityGateOptions
    )
    sample_quality_options: HistoricalRecommendationSampleQualityOptions = Field(
        default_factory=HistoricalRecommendationSampleQualityOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    run_sample_quality: bool = True
    allow_sample_quality_failures: bool = False
    run_gate: bool = True


class HistoricalRecommendationSamplePipelineBuildRecord(BaseModel):
    input_csv_path: Path
    output_slice_path: Path
    slice_id: str
    row_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    quality_result: HistoricalRecommendationSampleQualityResult | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalRecommendationSamplePipelineResult(BaseModel):
    build_count: int = Field(ge=0)
    builds: list[HistoricalRecommendationSamplePipelineBuildRecord] = Field(
        default_factory=list
    )
    manifest_refresh_result: HistoricalRecommendationSuiteManifestRefreshResult
    suite_result: HistoricalRecommendationBacktestSuiteResult | None = None
    gate_result: HistoricalRecommendationSuiteQualityGateResult | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_historical_recommendation_sample_pipeline(
    input_csv_paths: Sequence[Path | str],
    *,
    options: HistoricalRecommendationSamplePipelineOptions,
) -> HistoricalRecommendationSamplePipelineResult:
    if not input_csv_paths:
        raise ValueError("historical sample pipeline requires at least one input CSV")
    options.output_dir.mkdir(parents=True, exist_ok=True)
    build_records = [
        _build_slice_from_csv(input_csv_path, options=options)
        for input_csv_path in input_csv_paths
    ]
    sample_quality_passed = all(
        build.quality_result is None or build.quality_result.passed
        for build in build_records
    )
    refresh_options = options.manifest_refresh_options
    manifest_write_suppressed = False
    if (
        not sample_quality_passed
        and not options.allow_sample_quality_failures
        and refresh_options.write
    ):
        refresh_options = refresh_options.model_copy(update={"write": False})
        manifest_write_suppressed = True
    refresh_result = refresh_historical_recommendation_suite_manifest(
        options.manifest_path,
        slice_paths=[record.output_slice_path for record in build_records],
        options=refresh_options,
    )
    suite_result: HistoricalRecommendationBacktestSuiteResult | None = None
    gate_result: HistoricalRecommendationSuiteQualityGateResult | None = None
    gate_skipped_for_sample_quality = (
        not sample_quality_passed and not options.allow_sample_quality_failures
    )
    if options.run_gate and not gate_skipped_for_sample_quality:
        suite_slices = [
            load_historical_recommendation_slice(slice_path)
            for slice_path in resolve_historical_recommendation_suite_manifest_slice_paths(
                refresh_result.manifest,
                manifest_path=options.manifest_path,
            )
        ]
        suite_result = run_historical_recommendation_backtest_suite(
            suite_slices,
            options=options.backtest_options,
            baseline_optimizer_profile=options.baseline_optimizer_profile,
            candidate_optimizer_profile=options.candidate_optimizer_profile,
        )
        gate_result = run_historical_recommendation_suite_quality_gate(
            suite_result,
            options=options.gate_options,
        )
    warnings = _pipeline_warnings(
        builds=build_records,
        manifest_refresh_result=refresh_result,
        gate_result=gate_result,
        sample_quality_passed=sample_quality_passed,
        manifest_write_suppressed=manifest_write_suppressed,
        gate_skipped_for_sample_quality=gate_skipped_for_sample_quality,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_recommendation_sample_pipeline_v3_1",
        "build_count": len(build_records),
        "output_dir": str(options.output_dir),
        "manifest_path": str(options.manifest_path),
        "manifest_write": refresh_options.write,
        "manifest_write_suppressed": manifest_write_suppressed,
        "sample_quality_passed": sample_quality_passed,
        "sample_quality_failed_slice_ids": [
            build.slice_id
            for build in build_records
            if build.quality_result is not None and not build.quality_result.passed
        ],
        "registered_slice_ids": refresh_result.registered_slice_ids,
        "registered_slice_paths": refresh_result.registered_slice_paths,
        "manifest_added_count": refresh_result.added_count,
        "manifest_updated_count": refresh_result.updated_count,
        "manifest_unchanged_count": refresh_result.unchanged_count,
        "suite_status": suite_result.status if suite_result is not None else None,
        "gate_status": gate_result.status if gate_result is not None else None,
        "gate_passed": gate_result.passed if gate_result is not None else None,
        "gate_skipped_for_sample_quality": gate_skipped_for_sample_quality,
        "warnings": warnings,
    }
    return HistoricalRecommendationSamplePipelineResult(
        build_count=len(build_records),
        builds=build_records,
        manifest_refresh_result=refresh_result,
        suite_result=suite_result,
        gate_result=gate_result,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = run_historical_recommendation_sample_pipeline(
        args.input_csv_paths,
        options=_options_from_args(args),
    )
    print(
        dumps(
            _cli_summary(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if (
        result.summary_json.get("sample_quality_passed") is False
        and not args.allow_sample_quality_failures
        and not args.no_fail_process
    ):
        raise SystemExit(1)
    if (
        result.gate_result is not None
        and not result.gate_result.passed
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _build_slice_from_csv(
    input_csv_path: Path | str,
    *,
    options: HistoricalRecommendationSamplePipelineOptions,
) -> HistoricalRecommendationSamplePipelineBuildRecord:
    csv_path = Path(input_csv_path)
    slice_id = _slice_id_for_csv(csv_path, prefix=options.build_defaults.slice_id_prefix)
    build_result = build_historical_recommendation_slice_from_csv(
        csv_path,
        options=HistoricalRecommendationSliceBuildOptions(
            slice_id=slice_id,
            name=_name_for_csv(csv_path, prefix=options.build_defaults.name_prefix),
            competition_id=options.build_defaults.competition_id,
            as_of_time_utc=options.build_defaults.as_of_time_utc,
            season=options.build_defaults.season,
            result_source=options.build_defaults.result_source,
            odds_source=options.build_defaults.odds_source,
            prediction_source=options.build_defaults.prediction_source,
            source_urls=options.build_defaults.source_urls,
            notes=options.build_defaults.notes,
            probability_sum_tolerance=(
                options.build_defaults.probability_sum_tolerance
            ),
        ),
    )
    output_path = options.output_dir / f"{slice_id}.json"
    output_path.write_text(
        f"{build_result.slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    quality_result = (
        evaluate_historical_recommendation_sample_quality(
            build_result.slice,
            options=options.sample_quality_options,
        )
        if options.run_sample_quality
        else None
    )
    return HistoricalRecommendationSamplePipelineBuildRecord(
        input_csv_path=csv_path,
        output_slice_path=output_path,
        slice_id=slice_id,
        row_count=build_result.row_count,
        fixture_count=build_result.fixture_count,
        prediction_count=build_result.prediction_count,
        quality_result=quality_result,
        warnings=build_result.warnings,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build historical slices from CSV, refresh a suite manifest, "
            "and optionally run the suite quality gate."
        )
    )
    parser.add_argument("input_csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--as-of-time-utc", required=True)
    parser.add_argument("--season", default=None)
    parser.add_argument("--result-source", required=True)
    parser.add_argument("--odds-source", required=True)
    parser.add_argument("--prediction-source", required=True)
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--slice-id-prefix", default="")
    parser.add_argument("--name-prefix", default="")
    parser.add_argument("--probability-sum-tolerance", type=float, default=0.02)
    parser.add_argument("--manifest-tag", action="append", default=[])
    parser.add_argument("--manifest-note", action="append", default=[])
    parser.add_argument("--manifest-disabled", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--skip-sample-quality", action="store_true")
    parser.add_argument("--allow-sample-quality-failures", action="store_true")
    parser.add_argument("--min-sample-fixture-count", type=int, default=1)
    parser.add_argument("--allow-incomplete-1x2", action="store_true")
    parser.add_argument("--sample-probability-sum-tolerance", type=float, default=0.02)
    parser.add_argument("--require-market-probability", action="store_true")
    parser.add_argument("--min-sample-data-quality-score", type=float, default=None)
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--pass-types", default="2x1")
    parser.add_argument("--modes", default="single")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
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
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalRecommendationSamplePipelineOptions:
    return HistoricalRecommendationSamplePipelineOptions(
        output_dir=args.output_dir,
        manifest_path=args.manifest_path,
        build_defaults=HistoricalRecommendationSamplePipelineBuildDefaults(
            competition_id=args.competition_id,
            as_of_time_utc=_datetime(args.as_of_time_utc),
            season=args.season,
            result_source=args.result_source,
            odds_source=args.odds_source,
            prediction_source=args.prediction_source,
            source_urls=tuple(args.source_url),
            notes=tuple(args.note),
            slice_id_prefix=args.slice_id_prefix,
            name_prefix=args.name_prefix,
            probability_sum_tolerance=args.probability_sum_tolerance,
        ),
        manifest_refresh_options=HistoricalRecommendationSuiteManifestRefreshOptions(
            enabled=not args.manifest_disabled,
            tags=tuple(args.manifest_tag),
            notes=tuple(args.manifest_note),
            write=args.write_manifest,
        ),
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
        ),
        gate_options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=args.min_final_hit_sample_size,
            fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
            min_final_hit_rate_delta=args.min_final_hit_rate_delta,
            max_brier_score_delta=args.max_brier_score_delta,
            max_log_loss_delta=args.max_log_loss_delta,
            max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        ),
        sample_quality_options=HistoricalRecommendationSampleQualityOptions(
            min_fixture_count=args.min_sample_fixture_count,
            require_1x2_complete=not args.allow_incomplete_1x2,
            probability_sum_tolerance=args.sample_probability_sum_tolerance,
            require_market_probability=args.require_market_probability,
            min_data_quality_score=args.min_sample_data_quality_score,
        ),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        run_sample_quality=not args.skip_sample_quality,
        allow_sample_quality_failures=args.allow_sample_quality_failures,
        run_gate=not args.skip_gate,
    )


def _cli_summary(result: HistoricalRecommendationSamplePipelineResult) -> dict[str, object]:
    return {
        **result.summary_json,
        "builds": [build.model_dump(mode="json") for build in result.builds],
        "manifest_refresh": result.manifest_refresh_result.summary_json,
        "suite_summary": (
            result.suite_result.summary_json if result.suite_result is not None else None
        ),
        "gate_summary": (
            result.gate_result.summary_json if result.gate_result is not None else None
        ),
    }


def _pipeline_warnings(
    *,
    builds: Sequence[HistoricalRecommendationSamplePipelineBuildRecord],
    manifest_refresh_result: HistoricalRecommendationSuiteManifestRefreshResult,
    gate_result: HistoricalRecommendationSuiteQualityGateResult | None,
    sample_quality_passed: bool,
    manifest_write_suppressed: bool,
    gate_skipped_for_sample_quality: bool,
) -> list[str]:
    warnings: list[str] = []
    for build in builds:
        warnings.extend(build.warnings)
        if build.quality_result is not None:
            warnings.extend(build.quality_result.warnings)
    warnings.extend(manifest_refresh_result.warnings)
    if gate_result is not None:
        warnings.extend(gate_result.warnings)
    if not sample_quality_passed:
        warnings.append("historical_sample_pipeline:sample_quality_failed")
    if manifest_write_suppressed:
        warnings.append("historical_sample_pipeline:manifest_write_suppressed")
    if gate_skipped_for_sample_quality:
        warnings.append("historical_sample_pipeline:gate_skipped_for_sample_quality")
    return warnings


def _slice_id_for_csv(csv_path: Path, *, prefix: str) -> str:
    slug = _slug(csv_path.stem)
    return f"{prefix}_{slug}" if prefix else slug


def _name_for_csv(csv_path: Path, *, prefix: str) -> str:
    base_name = csv_path.stem.replace("_", " ").replace("-", " ").title()
    return f"{prefix} {base_name}".strip() if prefix else base_name


def _slug(value: str) -> str:
    normalized = sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("cannot derive slice id from empty CSV filename")
    return normalized


def _datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
