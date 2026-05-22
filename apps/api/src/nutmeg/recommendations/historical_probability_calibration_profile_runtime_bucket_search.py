from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_probability_calibration_profile_runtime_refinement import (
    HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions,
    _refined_profile_set,
)
from nutmeg.recommendations.historical_probability_calibration_profile_runtime_replay import (
    HistoricalProbabilityCalibrationProfileRuntimeReplayOptions,
    HistoricalProbabilityCalibrationProfileRuntimeReplayReport,
    ProbabilityCalibrationRuntimeProfileSet,
    build_historical_probability_calibration_profile_runtime_replay_report,
    load_probability_calibration_runtime_profile_set,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalProbabilityCalibrationProfileRuntimeBucketSearchDecision = Literal[
    "accepted",
    "rejected",
]
type HistoricalProbabilityCalibrationProfileRuntimeBucketScopeMode = Literal[
    "season",
    "single_bucket",
]


class HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec(BaseModel):
    spec_key: str
    scope_mode: HistoricalProbabilityCalibrationProfileRuntimeBucketScopeMode
    blend_weight: float = Field(ge=0.0, le=1.0)
    target_competition_ids: tuple[str, ...] = ()
    target_season_ids: tuple[str, ...] = ()
    target_outcomes: tuple[str, ...] = ()
    bucket_keys: tuple[str, ...] = ()
    source_group_key: str | None = None
    min_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    max_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )


class HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions(BaseModel):
    profile_keys: tuple[str, ...] = ()
    profile_key_suffix: str = "bucket_search"
    blend_weights: tuple[float, ...] = (0.05, 0.10)
    diagnostics_report_path: Path | None = None
    target_competition_ids: tuple[str, ...] = ()
    target_season_ids: tuple[str, ...] = ()
    bucket_outcomes: tuple[str, ...] = ()
    bucket_scope_modes: tuple[
        HistoricalProbabilityCalibrationProfileRuntimeBucketScopeMode,
        ...,
    ] = ("season", "single_bucket")
    max_diagnostics_groups: int = Field(default=3, ge=1)
    max_candidate_specs: int | None = Field(default=None, ge=1)
    min_group_changed_final_answer_count: int = Field(default=1, ge=0)
    min_group_final_answer_hit_delta: int = 1
    min_group_profit_loss_delta: float = 0.0
    min_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    max_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    candidate_specs: tuple[
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec,
        ...,
    ] = ()
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_final_answer_count: int = Field(default=20, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_adjusted_candidate_count: int = Field(default=1, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = -1.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)


class HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate(BaseModel):
    candidate_key: str
    rank: int = Field(default=0, ge=0)
    decision: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchDecision
    decision_reasons: list[str] = Field(default_factory=list)
    spec: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec
    refined_profile_key: str
    bucket_count: int = Field(default=0, ge=0)
    replay_report_key: str
    replay_status: str
    runtime_replay_allowed: bool = False
    holdout_replay_allowed: bool = False
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_candidate_count: int = Field(default=0, ge=0)
    changed_final_answer_count: int = Field(default=0, ge=0)
    final_answer_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float = 0.0
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    harm_count_vs_baseline: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    replay_failed_checks: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationProfileRuntimeBucketSearchReport(BaseModel):
    report_key: str
    status: str = "generated"
    source_profile_version: str
    selected_profile_key: str
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    best_candidate: (
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate | None
    ) = None
    accepted_candidates: list[
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate
    ] = Field(default_factory=list)
    candidates: list[
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate
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


class _DiagnosticGroupScope(BaseModel):
    group_key: str
    competition_id: str
    season: str
    changed_final_answer_count: int = 0
    final_answer_hit_delta_count: int = 0
    profit_loss_delta: float = 0.0
    quality_regression_score: float = 0.0


def build_historical_probability_calibration_profile_runtime_bucket_search_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    profile_set_path: Path | str,
    options: (
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions | None
    ) = None,
) -> HistoricalProbabilityCalibrationProfileRuntimeBucketSearchReport:
    resolved_options = (
        options or HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions()
    )
    profile_set = load_probability_calibration_runtime_profile_set(profile_set_path)
    selected_profile = _selected_profile(profile_set.profiles, options=resolved_options)
    warnings: list[str] = []
    specs = _candidate_specs(selected_profile, options=resolved_options)
    if not specs:
        warnings.append("probability_calibration_runtime_bucket_search:no_candidate_specs")
    candidates = [
        _search_candidate(
            historical_slices,
            profile_set=profile_set,
            selected_profile=selected_profile,
            spec=spec,
            options=resolved_options,
        )
        for spec in specs
    ]
    candidates = _ranked_candidates(candidates)
    accepted_candidates = [
        candidate for candidate in candidates if candidate.decision == "accepted"
    ]
    best_candidate = accepted_candidates[0] if accepted_candidates else None
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_runtime_bucket_search_v3_1"
        ),
        "source_profile_version": profile_set.profile_version,
        "selected_profile_key": selected_profile.profile_key,
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "diagnostics_report_path": (
            str(resolved_options.diagnostics_report_path)
            if resolved_options.diagnostics_report_path is not None
            else None
        ),
        "blend_weights": list(resolved_options.blend_weights),
        "bucket_scope_modes": list(resolved_options.bucket_scope_modes),
        "bucket_outcomes": list(_target_outcomes(selected_profile, resolved_options)),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, candidates)
    return HistoricalProbabilityCalibrationProfileRuntimeBucketSearchReport(
        report_key=report_key,
        source_profile_version=profile_set.profile_version,
        selected_profile_key=selected_profile.profile_key,
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        best_candidate=best_candidate,
        accepted_candidates=accepted_candidates,
        candidates=candidates,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_runtime_bucket_search_report(
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
    if not report.accepted_candidates and not args.no_fail_process:
        raise SystemExit(1)


def _search_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    profile_set: ProbabilityCalibrationRuntimeProfileSet,
    selected_profile: CandidateProbabilityCalibrationProfile,
    spec: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate:
    buckets = _filtered_buckets(selected_profile, spec)
    changed_fields_json = _spec_changed_fields_json(spec, buckets)
    refined_profile = selected_profile.model_copy(
        update={
            "profile_key": _refined_profile_key(
                selected_profile,
                changed_fields=changed_fields_json,
                suffix=options.profile_key_suffix,
            ),
            "blend_weight": spec.blend_weight,
            "target_competition_ids": spec.target_competition_ids,
            "target_season_ids": spec.target_season_ids,
            "target_outcomes": spec.target_outcomes,
            "buckets": buckets,
            "min_competition_season_index_by_competition_id": (
                spec.min_competition_season_index_by_competition_id
            ),
            "max_competition_season_index_by_competition_id": (
                spec.max_competition_season_index_by_competition_id
            ),
        }
    )
    refined_profile_set = _refined_profile_set(
        profile_set,
        refined_profile=refined_profile,
        options=HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions(
            profile_key_suffix=options.profile_key_suffix,
            preserve_runtime_flags=True,
        ),
    )
    replay_report = build_historical_probability_calibration_profile_runtime_replay_report(
        historical_slices,
        profile_set=refined_profile_set,
        options=_replay_options(options),
    )
    decision_reasons = _decision_reasons(replay_report, options=options)
    if not buckets:
        decision_reasons.append("bucket_count:below_threshold")
    decision: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchDecision = (
        "accepted" if not decision_reasons else "rejected"
    )
    return HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate(
        candidate_key=_candidate_key(spec, refined_profile.profile_key),
        decision=decision,
        decision_reasons=decision_reasons,
        spec=spec,
        refined_profile_key=refined_profile.profile_key,
        bucket_count=len(buckets),
        replay_report_key=replay_report.report_key,
        replay_status=replay_report.status,
        runtime_replay_allowed=replay_report.runtime_replay_allowed,
        holdout_replay_allowed=replay_report.holdout_replay_allowed,
        adjusted_fixture_count=replay_report.adjusted_fixture_count,
        adjusted_candidate_count=replay_report.adjusted_candidate_count,
        changed_final_answer_count=replay_report.changed_final_answer_count,
        final_answer_count=replay_report.final_answer_count,
        final_answer_hit_delta_count=replay_report.final_answer_hit_delta_count,
        final_answer_hit_rate_delta=replay_report.final_answer_hit_rate_delta,
        roi_delta=replay_report.roi_delta,
        profit_loss_delta=replay_report.profit_loss_delta,
        brier_score_delta=replay_report.brier_score_delta,
        log_loss_delta=replay_report.log_loss_delta,
        mean_calibration_error_delta=replay_report.mean_calibration_error_delta,
        harm_count_vs_baseline=replay_report.harm_count_vs_baseline,
        final_hit_harm_count_vs_baseline=(
            replay_report.final_hit_harm_count_vs_baseline
        ),
        profit_loss_harm_count_vs_baseline=(
            replay_report.profit_loss_harm_count_vs_baseline
        ),
        replay_failed_checks=[
            check.name for check in replay_report.checks if check.status == "failed"
        ],
        summary_json={
            "bucket_search": True,
            "changed_fields": changed_fields_json,
            "bucket_keys": [bucket.bucket_key for bucket in buckets],
            "runtime_replay_allowed": replay_report.runtime_replay_allowed,
            "holdout_replay_allowed": replay_report.holdout_replay_allowed,
            "replay_failed_checks": [
                check.name
                for check in replay_report.checks
                if check.status == "failed"
            ],
        },
    )


def _candidate_specs(
    selected_profile: CandidateProbabilityCalibrationProfile,
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> list[HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec]:
    if options.candidate_specs:
        return _dedupe_specs(options.candidate_specs)
    scopes = _candidate_group_scopes(options)
    outcomes = _target_outcomes(selected_profile, options)
    specs: list[HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec] = []
    for scope in scopes:
        for blend_weight in options.blend_weights:
            if "season" in options.bucket_scope_modes:
                specs.append(
                    HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec(
                        spec_key=(
                            "season:"
                            f"{scope.competition_id}:{scope.season}:"
                            f"blend:{blend_weight:.4f}"
                        ),
                        scope_mode="season",
                        blend_weight=blend_weight,
                        target_competition_ids=(scope.competition_id,),
                        target_season_ids=(scope.season,),
                        target_outcomes=outcomes,
                        source_group_key=scope.group_key,
                        min_competition_season_index_by_competition_id=dict(
                            sorted(
                                options.min_competition_season_index_by_competition_id.items()
                            )
                        ),
                        max_competition_season_index_by_competition_id=dict(
                            sorted(
                                options.max_competition_season_index_by_competition_id.items()
                            )
                        ),
                    )
                )
            if "single_bucket" in options.bucket_scope_modes:
                for bucket in _scope_buckets(selected_profile, scope, outcomes=outcomes):
                    specs.append(
                        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec(
                            spec_key=(
                                "single_bucket:"
                                f"{scope.competition_id}:{scope.season}:"
                                f"{bucket.bucket_key}:blend:{blend_weight:.4f}"
                            ),
                            scope_mode="single_bucket",
                            blend_weight=blend_weight,
                            target_competition_ids=(scope.competition_id,),
                            target_season_ids=(scope.season,),
                            target_outcomes=(bucket.outcome,),
                            bucket_keys=(bucket.bucket_key,),
                            source_group_key=scope.group_key,
                            min_competition_season_index_by_competition_id=dict(
                                sorted(
                                    options.min_competition_season_index_by_competition_id.items()
                                )
                            ),
                            max_competition_season_index_by_competition_id=dict(
                                sorted(
                                    options.max_competition_season_index_by_competition_id.items()
                                )
                            ),
                        )
                    )
    deduped = _dedupe_specs(specs)
    if options.max_candidate_specs is not None:
        return deduped[: options.max_candidate_specs]
    return deduped


def _candidate_group_scopes(
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> list[_DiagnosticGroupScope]:
    if options.diagnostics_report_path is not None:
        payload = loads(options.diagnostics_report_path.read_text(encoding="utf-8"))
        raw_groups = payload.get("top_regression_groups")
        groups = raw_groups if isinstance(raw_groups, list) else []
        scopes = [
            scope
            for group in groups
            if (scope := _diagnostic_group_scope(group, options=options)) is not None
        ]
        return sorted(scopes, key=_group_scope_sort_key)[
            : options.max_diagnostics_groups
        ]
    if options.target_competition_ids and options.target_season_ids:
        return [
            _DiagnosticGroupScope(
                group_key=f"manual:{competition_id}:{season}",
                competition_id=competition_id,
                season=season,
            )
            for competition_id in options.target_competition_ids
            for season in options.target_season_ids
        ]
    return []


def _diagnostic_group_scope(
    raw_group: object,
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> _DiagnosticGroupScope | None:
    if not isinstance(raw_group, Mapping):
        return None
    if raw_group.get("group_type") != "competition_season":
        return None
    competition_id = _string(raw_group.get("competition_id"))
    season = _string(raw_group.get("season"))
    if competition_id is None or season is None:
        return None
    changed_count = _int(raw_group.get("changed_final_answer_count"))
    hit_delta = _int(raw_group.get("final_answer_hit_delta_count"))
    profit_delta = _float(raw_group.get("profit_loss_delta"))
    if changed_count < options.min_group_changed_final_answer_count:
        return None
    if hit_delta < options.min_group_final_answer_hit_delta:
        return None
    if profit_delta < options.min_group_profit_loss_delta:
        return None
    return _DiagnosticGroupScope(
        group_key=_string(raw_group.get("group_key")) or f"{competition_id}|{season}",
        competition_id=competition_id,
        season=season,
        changed_final_answer_count=changed_count,
        final_answer_hit_delta_count=hit_delta,
        profit_loss_delta=profit_delta,
        quality_regression_score=_float(raw_group.get("quality_regression_score")),
    )


def _group_scope_sort_key(scope: _DiagnosticGroupScope) -> tuple[float, int, str]:
    return (-scope.profit_loss_delta, -scope.final_answer_hit_delta_count, scope.group_key)


def _target_outcomes(
    selected_profile: CandidateProbabilityCalibrationProfile,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> tuple[str, ...]:
    if options.bucket_outcomes:
        return options.bucket_outcomes
    if selected_profile.target_outcomes:
        return selected_profile.target_outcomes
    return tuple(sorted({bucket.outcome for bucket in selected_profile.buckets}))


def _scope_buckets(
    selected_profile: CandidateProbabilityCalibrationProfile,
    scope: _DiagnosticGroupScope,
    *,
    outcomes: Sequence[str],
) -> list[CandidateProbabilityCalibrationBucket]:
    outcome_set = set(outcomes)
    return [
        bucket
        for bucket in selected_profile.buckets
        if bucket.competition_id == scope.competition_id and bucket.outcome in outcome_set
    ]


def _filtered_buckets(
    selected_profile: CandidateProbabilityCalibrationProfile,
    spec: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec,
) -> list[CandidateProbabilityCalibrationBucket]:
    bucket_key_set = set(spec.bucket_keys)
    target_competition_ids = set(spec.target_competition_ids)
    target_outcomes = set(spec.target_outcomes)
    return [
        bucket
        for bucket in selected_profile.buckets
        if (not bucket_key_set or bucket.bucket_key in bucket_key_set)
        and (
            not target_competition_ids
            or bucket.competition_id in target_competition_ids
        )
        and (not target_outcomes or bucket.outcome in target_outcomes)
    ]


def _spec_changed_fields_json(
    spec: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec,
    buckets: Sequence[CandidateProbabilityCalibrationBucket],
) -> dict[str, object]:
    return {
        "blend_weight": spec.blend_weight,
        "scope_mode": spec.scope_mode,
        "target_competition_ids": list(spec.target_competition_ids),
        "target_season_ids": list(spec.target_season_ids),
        "target_outcomes": list(spec.target_outcomes),
        "bucket_keys": list(spec.bucket_keys),
        "buckets": [bucket.model_dump(mode="json") for bucket in buckets],
        "min_competition_season_index_by_competition_id": dict(
            sorted(spec.min_competition_season_index_by_competition_id.items())
        ),
        "max_competition_season_index_by_competition_id": dict(
            sorted(spec.max_competition_season_index_by_competition_id.items())
        ),
    }


def _decision_reasons(
    replay_report: HistoricalProbabilityCalibrationProfileRuntimeReplayReport,
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> list[str]:
    optional_reasons = [
        _minimum_reason(
            "adjusted_fixture_count",
            replay_report.adjusted_fixture_count,
            options.min_adjusted_fixture_count,
        ),
        _minimum_reason(
            "adjusted_candidate_count",
            replay_report.adjusted_candidate_count,
            options.min_adjusted_candidate_count,
        ),
        _minimum_reason(
            "final_answer_count",
            replay_report.final_answer_count,
            options.min_final_answer_count,
        ),
        _minimum_reason(
            "changed_final_answer_count",
            replay_report.changed_final_answer_count,
            options.min_changed_final_answer_count,
        ),
        _minimum_reason(
            "final_answer_hit_delta_count",
            replay_report.final_answer_hit_delta_count,
            options.min_final_answer_hit_count_delta,
        ),
        _minimum_reason(
            "final_answer_hit_rate_delta",
            replay_report.final_answer_hit_rate_delta,
            options.min_final_answer_hit_rate_delta,
        ),
        _minimum_reason("roi_delta", replay_report.roi_delta, options.min_roi_delta),
        _minimum_reason(
            "profit_loss_delta",
            replay_report.profit_loss_delta,
            options.min_profit_loss_delta,
        ),
        _maximum_reason(
            "brier_score_delta",
            replay_report.brier_score_delta,
            options.max_brier_score_delta,
        ),
        _maximum_reason(
            "log_loss_delta",
            replay_report.log_loss_delta,
            options.max_log_loss_delta,
        ),
        _maximum_reason(
            "mean_calibration_error_delta",
            replay_report.mean_calibration_error_delta,
            options.max_mean_calibration_error_delta,
        ),
        _maximum_reason(
            "harm_count_vs_baseline",
            replay_report.harm_count_vs_baseline,
            options.max_harm_count_vs_baseline,
        ),
        _maximum_reason(
            "final_hit_harm_count_vs_baseline",
            replay_report.final_hit_harm_count_vs_baseline,
            options.max_final_hit_harm_count_vs_baseline,
        ),
        _maximum_reason(
            "profit_loss_harm_count_vs_baseline",
            replay_report.profit_loss_harm_count_vs_baseline,
            options.max_profit_loss_harm_count_vs_baseline,
        ),
    ]
    reasons = [reason for reason in optional_reasons if reason is not None]
    candidate_roi = replay_report.candidate_roi
    if candidate_roi is None or candidate_roi < options.min_candidate_roi:
        reasons.append("candidate_roi:below_threshold")
    return reasons


def _minimum_reason(
    name: str,
    actual: float | int | None,
    threshold: float | int,
) -> str | None:
    if actual is None:
        return f"{name}:missing"
    if actual < threshold:
        return f"{name}:below_threshold"
    return None


def _maximum_reason(
    name: str,
    actual: float | int | None,
    threshold: float | int,
) -> str | None:
    if actual is None:
        return f"{name}:missing"
    if actual > threshold:
        return f"{name}:above_threshold"
    return None


def _replay_options(
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> HistoricalProbabilityCalibrationProfileRuntimeReplayOptions:
    return HistoricalProbabilityCalibrationProfileRuntimeReplayOptions(
        enable_shadow_replay=True,
        backtest_options=options.backtest_options,
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
        min_final_answer_count=options.min_final_answer_count,
        min_changed_final_answer_count=options.min_changed_final_answer_count,
        min_adjusted_fixture_count=options.min_adjusted_fixture_count,
        min_adjusted_candidate_count=options.min_adjusted_candidate_count,
        min_final_answer_hit_count_delta=options.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=options.min_final_answer_hit_rate_delta,
        min_roi_delta=options.min_roi_delta,
        min_profit_loss_delta=options.min_profit_loss_delta,
        min_candidate_roi=options.min_candidate_roi,
        max_brier_score_delta=options.max_brier_score_delta,
        max_log_loss_delta=options.max_log_loss_delta,
        max_mean_calibration_error_delta=options.max_mean_calibration_error_delta,
        max_harm_count_vs_baseline=options.max_harm_count_vs_baseline,
        max_final_hit_harm_count_vs_baseline=(
            options.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            options.max_profit_loss_harm_count_vs_baseline
        ),
        require_holdout_candidate_enabled=True,
        require_profile_runtime_allowed=False,
        require_proposed_production_enabled=False,
        require_active_profile=True,
        require_no_production_change=True,
        require_no_public_response_change=True,
        require_no_internal_strategy_label_exposure=True,
    )


def _selected_profile(
    profiles: Sequence[CandidateProbabilityCalibrationProfile],
    *,
    options: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions,
) -> CandidateProbabilityCalibrationProfile:
    profile_keys = set(options.profile_keys)
    selected = [
        profile for profile in profiles if not profile_keys or profile.profile_key in profile_keys
    ]
    if not selected:
        raise ValueError("No probability calibration profile matched bucket search options")
    if len(selected) > 1:
        raise ValueError("Runtime bucket search expects one profile")
    return selected[0]


def _ranked_candidates(
    candidates: Sequence[
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate
    ],
) -> list[HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate]:
    ranked = sorted(candidates, key=_candidate_sort_key)
    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(ranked)
    ]


def _candidate_sort_key(
    candidate: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate,
) -> tuple[int, float, float, float, str]:
    return (
        0 if candidate.decision == "accepted" else 1,
        -(candidate.final_answer_hit_rate_delta or 0.0),
        -(candidate.roi_delta or 0.0),
        candidate.brier_score_delta or 0.0,
        candidate.candidate_key,
    )


def _dedupe_specs(
    specs: Sequence[HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec],
) -> list[HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec]:
    deduped: dict[str, HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec] = {}
    for spec in specs:
        key = dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        deduped.setdefault(key, spec)
    return list(deduped.values())


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Search selection-aware bucket scopes for probability calibration runtime profiles."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--profile-set", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-keys", default="")
    parser.add_argument("--profile-key-suffix", default="bucket_search")
    parser.add_argument("--diagnostics-report", type=Path)
    parser.add_argument("--target-competitions", default="")
    parser.add_argument("--target-seasons", default="")
    parser.add_argument("--bucket-outcomes", default="")
    parser.add_argument("--bucket-scope-modes", default="season,single_bucket")
    parser.add_argument("--blend-weights", default="0.05,0.10")
    parser.add_argument("--max-diagnostics-groups", type=int, default=3)
    parser.add_argument("--max-candidate-specs", type=int)
    parser.add_argument("--min-group-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-group-final-answer-hit-delta", type=int, default=1)
    parser.add_argument("--min-group-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-competition-season-index-by-competition", default="")
    parser.add_argument("--max-competition-season-index-by-competition", default="")
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
    parser.add_argument("--min-final-answer-count", type=int, default=20)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-adjusted-candidate-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=-1.0)
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
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions:
    return HistoricalProbabilityCalibrationProfileRuntimeBucketSearchOptions(
        profile_keys=tuple(_csv(args.profile_keys)),
        profile_key_suffix=args.profile_key_suffix,
        blend_weights=tuple(_float_csv(args.blend_weights)),
        diagnostics_report_path=args.diagnostics_report,
        target_competition_ids=tuple(_csv(args.target_competitions)),
        target_season_ids=tuple(_csv(args.target_seasons)),
        bucket_outcomes=tuple(_csv(args.bucket_outcomes)),
        bucket_scope_modes=tuple(
            cast(HistoricalProbabilityCalibrationProfileRuntimeBucketScopeMode, mode)
            for mode in _csv(args.bucket_scope_modes)
        ),
        max_diagnostics_groups=args.max_diagnostics_groups,
        max_candidate_specs=args.max_candidate_specs,
        min_group_changed_final_answer_count=(
            args.min_group_changed_final_answer_count
        ),
        min_group_final_answer_hit_delta=args.min_group_final_answer_hit_delta,
        min_group_profit_loss_delta=args.min_group_profit_loss_delta,
        min_competition_season_index_by_competition_id=_competition_index_map(
            args.min_competition_season_index_by_competition
        ),
        max_competition_season_index_by_competition_id=_competition_index_map(
            args.max_competition_season_index_by_competition
        ),
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
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        min_adjusted_candidate_count=args.min_adjusted_candidate_count,
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


def _competition_index_map(value: str | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in _csv(value):
        competition_id, separator, raw_index = item.partition(":")
        if not separator or not competition_id or not raw_index.isdigit():
            raise ValueError(
                "competition season index mappings must use COMPETITION_ID:INDEX"
            )
        index = int(raw_index)
        if index < 1:
            raise ValueError("competition season index mappings must be positive")
        result[competition_id] = index
    return result


def _candidate_key(
    spec: HistoricalProbabilityCalibrationProfileRuntimeBucketSearchSpec,
    refined_profile_key: str,
) -> str:
    digest = sha256(
        dumps(
            {
                "spec": spec.model_dump(mode="json"),
                "refined_profile_key": refined_profile_key,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"runtime_bucket_search_candidate:{digest}"


def _refined_profile_key(
    profile: CandidateProbabilityCalibrationProfile,
    *,
    changed_fields: Mapping[str, object],
    suffix: str,
) -> str:
    digest = sha256(
        dumps(
            {
                "profile_key": profile.profile_key,
                "changed_fields": changed_fields,
                "suffix": suffix,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"{profile.profile_key}:runtime_refinement:{suffix}:{digest}"


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _float_csv(value: str | None) -> list[float]:
    return [float(item) for item in _csv(value)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0


def _float(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _report_key(
    summary: Mapping[str, object],
    candidates: Sequence[
        HistoricalProbabilityCalibrationProfileRuntimeBucketSearchCandidate
    ],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in candidates
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_runtime_bucket_search:{digest}"
