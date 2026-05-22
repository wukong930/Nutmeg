from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_probability_calibration_transform import (
    HistoricalProbabilityCalibrationTransformBucket,
    HistoricalProbabilityCalibrationTransformOptions,
    _calibration_buckets,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationMode,
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID,
    HistoricalProbabilityCalibrationProfileGateOptions,
    HistoricalProbabilityCalibrationProfileGateReport,
    build_historical_probability_calibration_profile_gate_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode

DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ARTIFACT_ID = (
    "candidate-probability-calibration-profile-artifact-v3.1"
)


class HistoricalProbabilityCalibrationProfileArtifactOptions(BaseModel):
    artifact_id: str = DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ARTIFACT_ID
    profile_mode: CandidateProbabilityCalibrationMode = "shadow"
    require_passed_final_answer_gate: bool = True
    gate_options: HistoricalProbabilityCalibrationProfileGateOptions = Field(
        default_factory=HistoricalProbabilityCalibrationProfileGateOptions
    )


class HistoricalProbabilityCalibrationProfileArtifactReport(BaseModel):
    report_key: str
    artifact_id: str
    gate_report_key: str
    emitted_profile: bool = False
    profile: CandidateProbabilityCalibrationProfile | None = None
    gate_report: HistoricalProbabilityCalibrationProfileGateReport
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_probability_calibration_profile_artifact_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileArtifactOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileArtifactReport:
    resolved_options = options or HistoricalProbabilityCalibrationProfileArtifactOptions()
    gate_report = build_historical_probability_calibration_profile_gate_report(
        historical_slices,
        options=resolved_options.gate_options,
    )
    warning_codes = list(gate_report.warnings)
    profile: CandidateProbabilityCalibrationProfile | None = None
    if (
        gate_report.passed_final_answer_gate
        or not resolved_options.require_passed_final_answer_gate
    ):
        profile = _candidate_profile(
            historical_slices,
            gate_report=gate_report,
            options=resolved_options,
        )
        if profile is None:
            warning_codes.append(
                "historical_probability_calibration_profile_artifact:no_runtime_buckets"
            )
    else:
        warning_codes.append(
            "historical_probability_calibration_profile_artifact:final_answer_gate_not_passed"
        )
    report_key = _report_key(
        historical_slices,
        gate_report=gate_report,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_artifact_v3_1"
        ),
        "report_key": report_key,
        "artifact_id": resolved_options.artifact_id,
        "gate_report_key": gate_report.report_key,
        "passed_final_answer_gate": gate_report.passed_final_answer_gate,
        "require_passed_final_answer_gate": (
            resolved_options.require_passed_final_answer_gate
        ),
        "emitted_profile": profile is not None,
        "profile_key": profile.profile_key if profile is not None else None,
        "profile_mode": resolved_options.profile_mode,
        "bucket_count": len(profile.buckets) if profile is not None else 0,
        "selected_competition_ids": gate_report.selected_competition_ids,
        "target_outcomes": list(resolved_options.gate_options.target_outcomes),
        "probability_min": resolved_options.gate_options.probability_min,
        "probability_max": resolved_options.gate_options.probability_max,
        "min_decimal_odds": resolved_options.gate_options.min_decimal_odds,
        "max_decimal_odds": resolved_options.gate_options.max_decimal_odds,
        "warning_codes": warning_codes,
    }
    return HistoricalProbabilityCalibrationProfileArtifactReport(
        report_key=report_key,
        artifact_id=resolved_options.artifact_id,
        gate_report_key=gate_report.report_key,
        emitted_profile=profile is not None,
        profile=profile,
        gate_report=gate_report,
        warning_codes=warning_codes,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_artifact_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warning_codes.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    if args.profile_output_path is not None and report.profile is not None:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{report.profile.model_dump_json(indent=2)}\n",
            encoding="utf-8",
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
    if report.profile is None and not args.no_fail_process:
        raise SystemExit(1)


def _candidate_profile(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    gate_report: HistoricalProbabilityCalibrationProfileGateReport,
    options: HistoricalProbabilityCalibrationProfileArtifactOptions,
) -> CandidateProbabilityCalibrationProfile | None:
    buckets = _runtime_buckets(
        historical_slices,
        selected_competition_ids=gate_report.selected_competition_ids,
        transform_options=options.gate_options.transform_options,
    )
    if not buckets:
        return None
    return CandidateProbabilityCalibrationProfile(
        profile_key=_profile_key(gate_report, options=options),
        buckets=buckets,
        source_report_key=gate_report.report_key,
        mode=options.profile_mode,
        segment_mode=options.gate_options.transform_options.segment_mode,
        min_bucket_sample_size=options.gate_options.transform_options.min_bucket_sample_size,
        blend_weight=options.gate_options.transform_options.blend_weight,
        target_competition_ids=tuple(gate_report.selected_competition_ids),
        target_market_types=("1x2",),
        target_outcomes=options.gate_options.target_outcomes,
        min_probability=options.gate_options.probability_min,
        max_probability=options.gate_options.probability_max,
        min_decimal_odds=options.gate_options.min_decimal_odds,
        max_decimal_odds=options.gate_options.max_decimal_odds,
    )


def _runtime_buckets(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    selected_competition_ids: Sequence[str],
    transform_options: HistoricalProbabilityCalibrationTransformOptions,
) -> list[CandidateProbabilityCalibrationBucket]:
    if not selected_competition_ids:
        return []
    selected_competitions = set(selected_competition_ids)
    if not transform_options.group_by_competition:
        training_slices = _training_slices_for_competitions(
            historical_slices,
            selected_competition_ids=selected_competitions,
            transform_options=transform_options,
        )
        return _runtime_buckets_from_transform_buckets(
            list(
                _calibration_buckets(
                    training_slices,
                    options=transform_options,
                ).values()
            ),
            transform_options=transform_options,
        )

    runtime_buckets: list[CandidateProbabilityCalibrationBucket] = []
    for competition_id, competition_slices in sorted(
        _slices_by_competition(historical_slices).items()
    ):
        if competition_id not in selected_competitions:
            continue
        training_slices = _training_slices(
            competition_slices,
            transform_options=transform_options,
        )
        if len(training_slices) < transform_options.min_training_season_count:
            continue
        runtime_buckets.extend(
            _runtime_buckets_from_transform_buckets(
                list(
                    _calibration_buckets(
                        training_slices,
                        options=transform_options,
                    ).values()
                ),
                transform_options=transform_options,
            )
        )
    return sorted(
        runtime_buckets,
        key=lambda bucket: (
            bucket.competition_id or "",
            bucket.outcome,
            bucket.bucket_start,
            bucket.bucket_end,
        ),
    )


def _runtime_buckets_from_transform_buckets(
    buckets: Sequence[HistoricalProbabilityCalibrationTransformBucket],
    *,
    transform_options: HistoricalProbabilityCalibrationTransformOptions,
) -> list[CandidateProbabilityCalibrationBucket]:
    runtime_buckets: list[CandidateProbabilityCalibrationBucket] = []
    for bucket in buckets:
        if bucket.sample_size < transform_options.min_bucket_sample_size:
            continue
        if bucket.calibrated_probability is None:
            continue
        runtime_buckets.append(
            CandidateProbabilityCalibrationBucket(
                competition_id=bucket.competition_id,
                market_type="1x2",
                outcome=bucket.outcome,
                segment_mode=bucket.segment_mode,
                bucket_start=bucket.bucket_start,
                bucket_end=bucket.bucket_end,
                calibrated_probability=bucket.calibrated_probability,
                sample_size=bucket.sample_size,
            )
        )
    return runtime_buckets


def _training_slices_for_competitions(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    selected_competition_ids: set[str],
    transform_options: HistoricalProbabilityCalibrationTransformOptions,
) -> list[HistoricalRecommendationSlice]:
    training_slices: list[HistoricalRecommendationSlice] = []
    for competition_id, competition_slices in sorted(
        _slices_by_competition(historical_slices).items()
    ):
        if competition_id not in selected_competition_ids:
            continue
        training_slices.extend(
            _training_slices(
                competition_slices,
                transform_options=transform_options,
            )
        )
    return training_slices


def _training_slices(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    transform_options: HistoricalProbabilityCalibrationTransformOptions,
) -> list[HistoricalRecommendationSlice]:
    sorted_slices = sorted(historical_slices, key=_slice_sort_key)
    holdout_count = min(transform_options.holdout_season_count, len(sorted_slices))
    return sorted_slices[:-holdout_count]


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


def _profile_key(
    gate_report: HistoricalProbabilityCalibrationProfileGateReport,
    *,
    options: HistoricalProbabilityCalibrationProfileArtifactOptions,
) -> str:
    digest = sha256(
        dumps(
            {
                "artifact_id": options.artifact_id,
                "gate_report_key": gate_report.report_key,
                "profile_mode": options.profile_mode,
                "selected_competition_ids": gate_report.selected_competition_ids,
                "gate_options": options.gate_options.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"candidate_probability_calibration_profile:{digest}"


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    gate_report: HistoricalProbabilityCalibrationProfileGateReport,
    options: HistoricalProbabilityCalibrationProfileArtifactOptions,
) -> str:
    digest = sha256(
        dumps(
            {
                "slice_ids": [item.metadata.slice_id for item in historical_slices],
                "artifact_id": options.artifact_id,
                "gate_report_key": gate_report.report_key,
                "options": options.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_artifact:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a runtime candidate probability calibration profile artifact "
            "from historical shadow final-answer gate evidence."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--artifact-id",
        default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ARTIFACT_ID,
    )
    parser.add_argument("--profile-mode", choices=["active", "shadow"], default="shadow")
    parser.add_argument("--allow-failed-final-answer-gate", action="store_true")
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
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileArtifactOptions:
    return HistoricalProbabilityCalibrationProfileArtifactOptions(
        artifact_id=args.artifact_id,
        profile_mode=args.profile_mode,
        require_passed_final_answer_gate=not args.allow_failed_final_answer_gate,
        gate_options=HistoricalProbabilityCalibrationProfileGateOptions(
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
                optimizer_profile=cast(
                    HistoricalOptimizerProfile,
                    args.optimizer_profile,
                ),
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
                max_mean_calibration_error_delta=(
                    args.max_mean_calibration_error_delta
                ),
            ),
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
        "slice_count": len(manifest_result.slices),
        "warnings": manifest_result.warnings,
    }


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())
