from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_probability_calibration_profile_runtime_replay import (
    _calibrated_replay_input,
    _final_answer_signature,
    load_probability_calibration_runtime_profile_set,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroupType = Literal[
    "overall",
    "competition",
    "season",
    "competition_season",
]


class HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions(BaseModel):
    profile_keys: tuple[str, ...] = ()
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_group_sample_size: int = Field(default=1, ge=1)
    top_slice_limit: int = Field(default=30, ge=1, le=500)
    top_group_limit: int = Field(default=30, ge=1, le=500)


class HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem(BaseModel):
    slice_id: str
    competition_id: str
    season: str | None = None
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_candidate_count: int = Field(default=0, ge=0)
    skipped_group_count: int = Field(default=0, ge=0)
    final_answer_changed: bool = False
    baseline_final_hit_sample_size: int = Field(default=0, ge=0)
    candidate_final_hit_sample_size: int = Field(default=0, ge=0)
    baseline_final_hit_count: int = Field(default=0, ge=0)
    candidate_final_hit_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    baseline_total_stake: float = Field(default=0.0, ge=0.0)
    candidate_total_stake: float = Field(default=0.0, ge=0.0)
    baseline_profit_loss: float = 0.0
    candidate_profit_loss: float = 0.0
    profit_loss_delta: float = 0.0
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    baseline_brier_score: float | None = None
    candidate_brier_score: float | None = None
    brier_score_delta: float | None = None
    baseline_log_loss: float | None = None
    candidate_log_loss: float | None = None
    log_loss_delta: float | None = None
    baseline_mean_calibration_error: float | None = None
    candidate_mean_calibration_error: float | None = None
    mean_calibration_error_delta: float | None = None
    quality_regression_score: float = 0.0
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup(BaseModel):
    group_key: str
    group_type: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_candidate_count: int = Field(default=0, ge=0)
    skipped_group_count: int = Field(default=0, ge=0)
    changed_final_answer_count: int = Field(default=0, ge=0)
    final_answer_count: int = Field(default=0, ge=0)
    baseline_final_hit_sample_size: int = Field(default=0, ge=0)
    candidate_final_hit_sample_size: int = Field(default=0, ge=0)
    baseline_final_hit_count: int = Field(default=0, ge=0)
    candidate_final_hit_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    baseline_total_stake: float = Field(default=0.0, ge=0.0)
    candidate_total_stake: float = Field(default=0.0, ge=0.0)
    baseline_profit_loss: float = 0.0
    candidate_profit_loss: float = 0.0
    profit_loss_delta: float = 0.0
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    baseline_brier_score: float | None = None
    candidate_brier_score: float | None = None
    brier_score_delta: float | None = None
    baseline_log_loss: float | None = None
    candidate_log_loss: float | None = None
    log_loss_delta: float | None = None
    baseline_mean_calibration_error: float | None = None
    candidate_mean_calibration_error: float | None = None
    mean_calibration_error_delta: float | None = None
    quality_regression_score: float = 0.0
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationProfileRuntimeDiagnosticReport(BaseModel):
    report_key: str
    status: str
    source_profile_version: str
    selected_profile_key: str
    baseline_suite_key: str
    candidate_suite_key: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_candidate_count: int = Field(default=0, ge=0)
    skipped_group_count: int = Field(default=0, ge=0)
    overall: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup
    by_competition: list[
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup
    ] = Field(default_factory=list)
    by_season: list[
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup
    ] = Field(default_factory=list)
    by_competition_season: list[
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup
    ] = Field(default_factory=list)
    top_regression_slices: list[
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem
    ] = Field(default_factory=list)
    top_regression_groups: list[
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup
    ] = Field(default_factory=list)
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


@dataclass(frozen=True)
class _SliceObservation:
    historical_slice: HistoricalRecommendationSlice
    calibrated_slice: HistoricalRecommendationSlice
    baseline_result: HistoricalRecommendationBacktestResult
    candidate_result: HistoricalRecommendationBacktestResult
    adjusted_fixture_count: int
    adjusted_candidate_count: int
    skipped_group_count: int


def build_historical_probability_calibration_profile_runtime_diagnostic_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    profile_set_path: Path | str,
    options: (
        HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions | None
    ) = None,
) -> HistoricalProbabilityCalibrationProfileRuntimeDiagnosticReport:
    resolved_options = (
        options or HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions()
    )
    profile_set = load_probability_calibration_runtime_profile_set(profile_set_path)
    selected_profile = _selected_profile(profile_set.profiles, options=resolved_options)
    calibration_results = [
        _calibrated_replay_input([historical_slice], profile=selected_profile)
        for historical_slice in historical_slices
    ]
    calibrated_slices = [
        result.slices[0]
        for result in calibration_results
        if result.slices
    ]
    baseline_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=resolved_options.backtest_options,
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    candidate_suite = run_historical_recommendation_backtest_suite(
        calibrated_slices,
        options=resolved_options.backtest_options,
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    observations = [
        _SliceObservation(
            historical_slice=historical_slice,
            calibrated_slice=calibrated_slice,
            baseline_result=baseline_comparison.candidate,
            candidate_result=candidate_comparison.candidate,
            adjusted_fixture_count=calibration_result.adjusted_fixture_count,
            adjusted_candidate_count=calibration_result.adjusted_candidate_count,
            skipped_group_count=calibration_result.skipped_group_count,
        )
        for (
            historical_slice,
            calibrated_slice,
            calibration_result,
            baseline_comparison,
            candidate_comparison,
        ) in zip(
            historical_slices,
            calibrated_slices,
            calibration_results,
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
    ]
    items = [_diagnostic_item(observation) for observation in observations]
    overall = _diagnostic_group(
        "overall",
        "overall",
        "Overall",
        items,
    )
    by_competition = _grouped_diagnostics(
        items,
        group_type="competition",
        key_fn=lambda item: item.competition_id,
        label_fn=lambda key: key,
    )
    by_season = _grouped_diagnostics(
        items,
        group_type="season",
        key_fn=lambda item: item.season or "unknown",
        label_fn=lambda key: key,
    )
    by_competition_season = _grouped_diagnostics(
        items,
        group_type="competition_season",
        key_fn=lambda item: "|".join([item.competition_id, item.season or "unknown"]),
        label_fn=lambda key: key.replace("|", " "),
    )
    top_regression_slices = sorted(
        [item for item in items if item.quality_regression_score > 0],
        key=_item_regression_sort_key,
    )[: resolved_options.top_slice_limit]
    eligible_groups = [
        group
        for group in [*by_competition, *by_season, *by_competition_season]
        if group.slice_count >= resolved_options.min_group_sample_size
        and group.quality_regression_score > 0
    ]
    top_regression_groups = sorted(
        eligible_groups,
        key=_group_regression_sort_key,
    )[: resolved_options.top_group_limit]
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [
        *profile_set.notes,
        *[warning for result in calibration_results for warning in result.warning_codes],
        *baseline_suite.warnings,
        *candidate_suite.warnings,
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_runtime_diagnostics_v3_1"
        ),
        "source_profile_version": profile_set.profile_version,
        "selected_profile_key": selected_profile.profile_key,
        "baseline_suite_key": baseline_suite.suite_key,
        "candidate_suite_key": candidate_suite.suite_key,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "adjusted_fixture_count": sum(
            result.adjusted_fixture_count for result in calibration_results
        ),
        "adjusted_candidate_count": sum(
            result.adjusted_candidate_count for result in calibration_results
        ),
        "skipped_group_count": sum(
            result.skipped_group_count for result in calibration_results
        ),
        "overall_quality_regression_score": overall.quality_regression_score,
        "overall_brier_score_delta": overall.brier_score_delta,
        "overall_log_loss_delta": overall.log_loss_delta,
        "overall_mean_calibration_error_delta": (
            overall.mean_calibration_error_delta
        ),
        "top_regression_group_keys": [
            group.group_key for group in top_regression_groups[:10]
        ],
        "top_regression_slice_ids": [
            item.slice_id for item in top_regression_slices[:10]
        ],
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, overall, top_regression_groups)
    return HistoricalProbabilityCalibrationProfileRuntimeDiagnosticReport(
        report_key=report_key,
        status="generated",
        source_profile_version=profile_set.profile_version,
        selected_profile_key=selected_profile.profile_key,
        baseline_suite_key=baseline_suite.suite_key,
        candidate_suite_key=candidate_suite.suite_key,
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        adjusted_fixture_count=sum(
            result.adjusted_fixture_count for result in calibration_results
        ),
        adjusted_candidate_count=sum(
            result.adjusted_candidate_count for result in calibration_results
        ),
        skipped_group_count=sum(
            result.skipped_group_count for result in calibration_results
        ),
        overall=overall,
        by_competition=by_competition,
        by_season=by_season,
        by_competition_season=by_competition_season,
        top_regression_slices=top_regression_slices,
        top_regression_groups=top_regression_groups,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_runtime_diagnostic_report(
        loaded_slices.slices,
        profile_set_path=args.profile_set,
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


def _selected_profile(
    profiles: Sequence[CandidateProbabilityCalibrationProfile],
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions,
) -> CandidateProbabilityCalibrationProfile:
    profile_keys = set(options.profile_keys)
    selected = [
        profile for profile in profiles if not profile_keys or profile.profile_key in profile_keys
    ]
    if not selected:
        raise ValueError("No probability calibration profile matched diagnostics options")
    if len(selected) > 1:
        raise ValueError("Probability calibration diagnostics expects one profile")
    return selected[0]


def _diagnostic_item(
    observation: _SliceObservation,
) -> HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem:
    baseline = observation.baseline_result
    candidate = observation.candidate_result
    brier_delta = _optional_delta(candidate.brier_score, baseline.brier_score)
    log_loss_delta = _optional_delta(candidate.log_loss, baseline.log_loss)
    ece_delta = _optional_delta(
        candidate.mean_calibration_error,
        baseline.mean_calibration_error,
    )
    return HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem(
        slice_id=observation.historical_slice.metadata.slice_id,
        competition_id=observation.historical_slice.metadata.competition_id,
        season=observation.historical_slice.metadata.season,
        fixture_count=len(observation.historical_slice.fixtures),
        prediction_count=sum(
            len(fixture.predictions) for fixture in observation.historical_slice.fixtures
        ),
        adjusted_fixture_count=observation.adjusted_fixture_count,
        adjusted_candidate_count=observation.adjusted_candidate_count,
        skipped_group_count=observation.skipped_group_count,
        final_answer_changed=(
            _final_answer_signature(baseline.final_answer)
            != _final_answer_signature(candidate.final_answer)
        ),
        baseline_final_hit_count=baseline.final_hit_count,
        candidate_final_hit_count=candidate.final_hit_count,
        baseline_final_hit_sample_size=baseline.final_hit_sample_size,
        candidate_final_hit_sample_size=candidate.final_hit_sample_size,
        final_answer_hit_delta_count=(
            candidate.final_hit_count - baseline.final_hit_count
        ),
        baseline_total_stake=baseline.total_stake,
        candidate_total_stake=candidate.total_stake,
        baseline_profit_loss=baseline.profit_loss,
        candidate_profit_loss=candidate.profit_loss,
        profit_loss_delta=candidate.profit_loss - baseline.profit_loss,
        baseline_roi=baseline.roi,
        candidate_roi=candidate.roi,
        roi_delta=_optional_delta(candidate.roi, baseline.roi),
        baseline_brier_score=baseline.brier_score,
        candidate_brier_score=candidate.brier_score,
        brier_score_delta=brier_delta,
        baseline_log_loss=baseline.log_loss,
        candidate_log_loss=candidate.log_loss,
        log_loss_delta=log_loss_delta,
        baseline_mean_calibration_error=baseline.mean_calibration_error,
        candidate_mean_calibration_error=candidate.mean_calibration_error,
        mean_calibration_error_delta=ece_delta,
        quality_regression_score=_quality_regression_score(
            brier_delta,
            log_loss_delta,
            ece_delta,
        ),
        summary_json={
            "baseline_backtest_key": baseline.backtest_key,
            "candidate_backtest_key": candidate.backtest_key,
            "baseline_final_answer_present": baseline.final_answer is not None,
            "candidate_final_answer_present": candidate.final_answer is not None,
        },
    )


def _diagnostic_group(
    group_key: str,
    group_type: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroupType,
    label: str,
    items: Sequence[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem],
) -> HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup:
    baseline_total_stake = sum(item.baseline_total_stake for item in items)
    candidate_total_stake = sum(item.candidate_total_stake for item in items)
    baseline_profit_loss = sum(item.baseline_profit_loss for item in items)
    candidate_profit_loss = sum(item.candidate_profit_loss for item in items)
    baseline_hit_count = sum(item.baseline_final_hit_count for item in items)
    candidate_hit_count = sum(item.candidate_final_hit_count for item in items)
    baseline_sample_size = sum(item.baseline_final_hit_sample_size for item in items)
    candidate_sample_size = sum(item.candidate_final_hit_sample_size for item in items)
    final_answer_count = candidate_sample_size
    baseline_brier = _weighted_item_average(
        items,
        "baseline_brier_score",
        weight_field_name="baseline_final_hit_sample_size",
    )
    candidate_brier = _weighted_item_average(
        items,
        "candidate_brier_score",
        weight_field_name="candidate_final_hit_sample_size",
    )
    baseline_log_loss = _weighted_item_average(
        items,
        "baseline_log_loss",
        weight_field_name="baseline_final_hit_sample_size",
    )
    candidate_log_loss = _weighted_item_average(
        items,
        "candidate_log_loss",
        weight_field_name="candidate_final_hit_sample_size",
    )
    baseline_ece = _weighted_item_average(
        items,
        "baseline_mean_calibration_error",
        weight_field_name="baseline_final_hit_sample_size",
    )
    candidate_ece = _weighted_item_average(
        items,
        "candidate_mean_calibration_error",
        weight_field_name="candidate_final_hit_sample_size",
    )
    brier_delta = _optional_delta(candidate_brier, baseline_brier)
    log_loss_delta = _optional_delta(candidate_log_loss, baseline_log_loss)
    ece_delta = _optional_delta(candidate_ece, baseline_ece)
    competition_id, season = _group_metadata(group_key, group_type)
    return HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup(
        group_key=group_key,
        group_type=group_type,
        label=label,
        competition_id=competition_id,
        season=season,
        slice_count=len(items),
        fixture_count=sum(item.fixture_count for item in items),
        prediction_count=sum(item.prediction_count for item in items),
        adjusted_fixture_count=sum(item.adjusted_fixture_count for item in items),
        adjusted_candidate_count=sum(item.adjusted_candidate_count for item in items),
        skipped_group_count=sum(item.skipped_group_count for item in items),
        changed_final_answer_count=sum(int(item.final_answer_changed) for item in items),
        final_answer_count=final_answer_count,
        baseline_final_hit_sample_size=baseline_sample_size,
        candidate_final_hit_sample_size=candidate_sample_size,
        baseline_final_hit_count=baseline_hit_count,
        candidate_final_hit_count=candidate_hit_count,
        final_answer_hit_delta_count=candidate_hit_count - baseline_hit_count,
        baseline_total_stake=baseline_total_stake,
        candidate_total_stake=candidate_total_stake,
        baseline_profit_loss=baseline_profit_loss,
        candidate_profit_loss=candidate_profit_loss,
        profit_loss_delta=candidate_profit_loss - baseline_profit_loss,
        baseline_roi=(
            baseline_profit_loss / baseline_total_stake if baseline_total_stake > 0 else None
        ),
        candidate_roi=(
            candidate_profit_loss / candidate_total_stake if candidate_total_stake > 0 else None
        ),
        roi_delta=_optional_delta(
            candidate_profit_loss / candidate_total_stake
            if candidate_total_stake > 0
            else None,
            baseline_profit_loss / baseline_total_stake
            if baseline_total_stake > 0
            else None,
        ),
        baseline_brier_score=baseline_brier,
        candidate_brier_score=candidate_brier,
        brier_score_delta=brier_delta,
        baseline_log_loss=baseline_log_loss,
        candidate_log_loss=candidate_log_loss,
        log_loss_delta=log_loss_delta,
        baseline_mean_calibration_error=baseline_ece,
        candidate_mean_calibration_error=candidate_ece,
        mean_calibration_error_delta=ece_delta,
        quality_regression_score=_quality_regression_score(
            brier_delta,
            log_loss_delta,
            ece_delta,
        ),
        summary_json={
            "quality_regression_slice_count": sum(
                1 for item in items if item.quality_regression_score > 0
            ),
            "baseline_final_hit_rate": _ratio(
                baseline_hit_count,
                baseline_sample_size,
            ),
            "candidate_final_hit_rate": _ratio(
                candidate_hit_count,
                candidate_sample_size,
            ),
            "changed_final_answer_slice_ids": [
                item.slice_id for item in items if item.final_answer_changed
            ][:20],
        },
    )


def _grouped_diagnostics(
    items: Sequence[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem],
    *,
    group_type: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroupType,
    key_fn: (
        Callable[[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem], str]
    ),
    label_fn: Callable[[str], str],
) -> list[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup]:
    grouped: dict[
        str,
        list[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem],
    ] = defaultdict(list)
    for item in items:
        grouped[key_fn(item)].append(item)
    return sorted(
        [
            _diagnostic_group(key, group_type, label_fn(key), grouped_items)
            for key, grouped_items in grouped.items()
        ],
        key=lambda group: group.group_key,
    )


def _group_metadata(
    group_key: str,
    group_type: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroupType,
) -> tuple[str | None, str | None]:
    if group_type == "competition":
        return group_key, None
    if group_type == "season":
        return None, group_key
    if group_type == "competition_season":
        competition_id, _, season = group_key.partition("|")
        return competition_id or None, season or None
    return None, None


def _weighted_item_average(
    items: Sequence[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem],
    field_name: str,
    *,
    weight_field_name: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for item in items:
        value = getattr(item, field_name)
        if value is None:
            continue
        weight = getattr(item, weight_field_name)
        if not isinstance(weight, int) or weight <= 0:
            continue
        numerator += float(value) * weight
        denominator += weight
    if denominator <= 0:
        return None
    return numerator / denominator


def _quality_regression_score(
    brier_delta: float | None,
    log_loss_delta: float | None,
    ece_delta: float | None,
) -> float:
    return sum(
        max(0.0, value)
        for value in (brier_delta, log_loss_delta, ece_delta)
        if value is not None
    )


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _item_regression_sort_key(
    item: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticItem,
) -> tuple[float, float, float, str]:
    return (
        -item.quality_regression_score,
        -(item.log_loss_delta or 0.0),
        -(item.brier_score_delta or 0.0),
        item.slice_id,
    )


def _group_regression_sort_key(
    group: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup,
) -> tuple[float, float, float, str]:
    return (
        -group.quality_regression_score,
        -(group.log_loss_delta or 0.0),
        -(group.brier_score_delta or 0.0),
        group.group_key,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Diagnose probability calibration runtime replay quality regressions."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--profile-set", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-keys", default="")
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
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
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
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument("--top-slice-limit", type=int, default=30)
    parser.add_argument("--top-group-limit", type=int, default=30)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions:
    return HistoricalProbabilityCalibrationProfileRuntimeDiagnosticOptions(
        profile_keys=tuple(_csv(args.profile_keys)),
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
        min_group_sample_size=args.min_group_sample_size,
        top_slice_limit=args.top_slice_limit,
        top_group_limit=args.top_group_limit,
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


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _report_key(
    summary: Mapping[str, object],
    overall: HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup,
    top_groups: Sequence[HistoricalProbabilityCalibrationProfileRuntimeDiagnosticGroup],
) -> str:
    payload = {
        "summary": summary,
        "overall": overall.model_dump(mode="json"),
        "top_groups": [group.model_dump(mode="json") for group in top_groups],
    }
    digest = sha256(
        dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_runtime_diagnostics:{digest}"
