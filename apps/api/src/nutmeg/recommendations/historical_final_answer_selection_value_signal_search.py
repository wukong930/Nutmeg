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
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    _final_answer_signature,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationMode,
    RecommendationStrategy,
    ScoredRecommendationCandidate,
)

type HistoricalFinalAnswerSelectionValueSignalSearchDecision = Literal[
    "accepted",
    "rejected",
]


class HistoricalFinalAnswerSelectionValueSignalSearchSpec(BaseModel):
    spec_key: str
    competition_ids: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    probability_min: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_max: float = Field(default=1.0, ge=0.0, le=1.0)
    min_decimal_odds: float = Field(default=1.0, ge=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    max_model_edge: float | None = None
    score_min: float = Field(default=0.0, ge=0.0, le=1.0)
    score_max: float = Field(default=1.0, ge=0.0, le=1.0)
    max_hit_probability_deficit: float | None = Field(default=None, ge=0.0, le=1.0)
    min_option_roi: float | None = None
    max_option_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    strength: float = Field(ge=-1.0, le=1.0)
    source_bucket_key: str | None = None
    source_bucket_search_candidate_key: str | None = None


class HistoricalFinalAnswerSelectionValueSignalSearchOptions(BaseModel):
    bucket_search_report_path: Path | None = None
    movement_diagnostics_report_path: Path | None = None
    bucket_keys: tuple[str, ...] = ()
    strength_values: tuple[float, ...] = (0.02, 0.04, 0.08)
    probability_min_values: tuple[float, ...] = (0.0,)
    probability_max_values: tuple[float, ...] = (1.0,)
    max_model_edge_values: tuple[float | None, ...] = (None,)
    score_min_values: tuple[float, ...] = (0.0,)
    score_max_values: tuple[float, ...] = (1.0,)
    max_hit_probability_deficit_values: tuple[float | None, ...] = (None,)
    min_option_roi_values: tuple[float | None, ...] = (None,)
    max_option_risk_score_values: tuple[float | None, ...] = (None,)
    max_source_bucket_candidates: int = Field(default=1, ge=1)
    min_source_final_answer_hit_delta: int = 1
    min_source_profit_loss_delta: float = 0.0
    candidate_specs: tuple[HistoricalFinalAnswerSelectionValueSignalSearchSpec, ...] = ()
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_affected_leg_count: int = Field(default=1, ge=0)
    min_final_answer_count: int = Field(default=20, ge=1)
    min_changed_final_answer_count: int = Field(default=1, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_candidate_roi: float = -1.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    include_movement_diagnostics: bool = False
    movement_diagnostics_limit: int = Field(default=32, ge=1, le=500)
    movement_score_band: float = Field(default=0.0015, ge=0.0, le=0.20)
    max_movement_conditioned_specs: int = Field(default=8, ge=1, le=128)
    movement_conditioned_classes: tuple[str, ...] = ("clean_positive",)


class HistoricalFinalAnswerSelectionValueSignalSearchCandidate(BaseModel):
    candidate_key: str
    rank: int = Field(default=0, ge=0)
    decision: HistoricalFinalAnswerSelectionValueSignalSearchDecision
    decision_reasons: list[str] = Field(default_factory=list)
    spec: HistoricalFinalAnswerSelectionValueSignalSearchSpec
    suite_key: str
    suite_status: str
    affected_leg_count: int = Field(default=0, ge=0)
    guard_blocked_option_count: int = Field(default=0, ge=0)
    final_answer_count: int = Field(default=0, ge=0)
    changed_final_answer_count: int = Field(default=0, ge=0)
    final_answer_hit_delta_count: int = 0
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float = 0.0
    candidate_roi: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    movement_count: int = Field(default=0, ge=0)
    positive_movement_count: int = Field(default=0, ge=0)
    harmful_movement_count: int = Field(default=0, ge=0)
    probability_quality_harm_movement_count: int = Field(default=0, ge=0)
    movement_diagnostics_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerSelectionValueSignalSearchReport(BaseModel):
    report_key: str
    status: str = "generated"
    baseline_suite_key: str
    baseline_suite_status: str
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    best_candidate: (
        HistoricalFinalAnswerSelectionValueSignalSearchCandidate | None
    ) = None
    accepted_candidates: list[
        HistoricalFinalAnswerSelectionValueSignalSearchCandidate
    ] = Field(default_factory=list)
    candidates: list[HistoricalFinalAnswerSelectionValueSignalSearchCandidate] = Field(
        default_factory=list
    )
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


class _SourceBucket(BaseModel):
    bucket_key: str
    competition_id: str
    market_type: str
    outcome: str
    bucket_start: float = Field(gt=0.0, le=1.0)
    bucket_end: float = Field(gt=0.0, le=1.0)
    source_candidate_key: str | None = None
    source_rank: int | None = None
    source_final_answer_hit_delta_count: int = 0
    source_profit_loss_delta: float = 0.0

    @property
    def min_decimal_odds(self) -> float:
        return 1.0 / self.bucket_end

    @property
    def max_decimal_odds(self) -> float:
        return 1.0 / self.bucket_start


def build_historical_final_answer_selection_value_signal_search_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: (
        HistoricalFinalAnswerSelectionValueSignalSearchOptions | None
    ) = None,
) -> HistoricalFinalAnswerSelectionValueSignalSearchReport:
    resolved_options = (
        options or HistoricalFinalAnswerSelectionValueSignalSearchOptions()
    )
    baseline_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_baseline_options(resolved_options.backtest_options),
        baseline_optimizer_profile=resolved_options.baseline_optimizer_profile,
        candidate_optimizer_profile=resolved_options.candidate_optimizer_profile,
    )
    specs = _candidate_specs(resolved_options)
    warnings: list[str] = []
    if not specs:
        warnings.append("final_answer_selection_value_signal_search:no_candidate_specs")
    candidates = [
        _evaluate_candidate(
            historical_slices,
            baseline_suite=baseline_suite,
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
            "historical_final_answer_selection_value_signal_search_v3_1"
        ),
        "baseline_suite_key": baseline_suite.suite_key,
        "baseline_suite_status": baseline_suite.status,
        "bucket_search_report_path": (
            str(resolved_options.bucket_search_report_path)
            if resolved_options.bucket_search_report_path is not None
            else None
        ),
        "movement_diagnostics_report_path": (
            str(resolved_options.movement_diagnostics_report_path)
            if resolved_options.movement_diagnostics_report_path is not None
            else None
        ),
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "strength_values": list(resolved_options.strength_values),
        "probability_min_values": list(resolved_options.probability_min_values),
        "probability_max_values": list(resolved_options.probability_max_values),
        "max_model_edge_values": list(resolved_options.max_model_edge_values),
        "score_min_values": list(resolved_options.score_min_values),
        "score_max_values": list(resolved_options.score_max_values),
        "max_hit_probability_deficit_values": list(
            resolved_options.max_hit_probability_deficit_values
        ),
        "min_option_roi_values": list(resolved_options.min_option_roi_values),
        "max_option_risk_score_values": list(
            resolved_options.max_option_risk_score_values
        ),
        "probability_grid_unchanged": True,
        "include_movement_diagnostics": (
            resolved_options.include_movement_diagnostics
        ),
        "movement_diagnostics_limit": resolved_options.movement_diagnostics_limit,
        "movement_score_band": resolved_options.movement_score_band,
        "max_movement_conditioned_specs": (
            resolved_options.max_movement_conditioned_specs
        ),
        "movement_conditioned_classes": list(
            resolved_options.movement_conditioned_classes
        ),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, candidates)
    return HistoricalFinalAnswerSelectionValueSignalSearchReport(
        report_key=report_key,
        baseline_suite_key=baseline_suite.suite_key,
        baseline_suite_status=baseline_suite.status,
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
    report = build_historical_final_answer_selection_value_signal_search_report(
        loaded_slices.slices,
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


def _evaluate_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    spec: HistoricalFinalAnswerSelectionValueSignalSearchSpec,
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> HistoricalFinalAnswerSelectionValueSignalSearchCandidate:
    candidate_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_candidate_options(options.backtest_options, spec),
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    deltas = _suite_deltas(baseline_suite, candidate_suite)
    movement_diagnostics = _suite_movement_diagnostics(
        baseline_suite,
        candidate_suite,
        include_records=options.include_movement_diagnostics,
        record_limit=options.movement_diagnostics_limit,
    )
    decision_reasons = _decision_reasons(
        candidate_suite,
        deltas=deltas,
        options=options,
    )
    decision: HistoricalFinalAnswerSelectionValueSignalSearchDecision = (
        "accepted" if not decision_reasons else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_selection_value_signal_candidate_v3_1",
        "decision": decision,
        "decision_reasons": decision_reasons,
        "spec": spec.model_dump(mode="json"),
        "suite_key": candidate_suite.suite_key,
        "suite_status": candidate_suite.status,
        "deltas": deltas,
        "movement_diagnostics": movement_diagnostics,
        "probability_grid_unchanged": True,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalFinalAnswerSelectionValueSignalSearchCandidate(
        candidate_key=candidate_key,
        decision=decision,
        decision_reasons=decision_reasons,
        spec=spec,
        suite_key=candidate_suite.suite_key,
        suite_status=candidate_suite.status,
        affected_leg_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_selection_value_signal_affected_leg_count",
        ),
        guard_blocked_option_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_selection_value_signal_guard_blocked_option_count",
        ),
        final_answer_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        changed_final_answer_count=_int_delta(
            deltas,
            "changed_final_answer_count",
        ),
        final_answer_hit_delta_count=_int_delta(
            deltas,
            "final_answer_hit_delta_count",
        ),
        final_answer_hit_rate_delta=_float_delta(deltas, "final_answer_hit_rate_delta"),
        roi_delta=_float_delta(deltas, "roi_delta"),
        profit_loss_delta=_float_delta(deltas, "profit_loss_delta") or 0.0,
        candidate_roi=_summary_number(candidate_suite.summary_json, "candidate_roi"),
        brier_score_delta=_float_delta(deltas, "brier_score_delta"),
        log_loss_delta=_float_delta(deltas, "log_loss_delta"),
        mean_calibration_error_delta=_float_delta(
            deltas,
            "mean_calibration_error_delta",
        ),
        final_hit_harm_count_vs_baseline=_int_delta(
            deltas,
            "final_hit_harm_count_vs_baseline",
        ),
        profit_loss_harm_count_vs_baseline=_int_delta(
            deltas,
            "profit_loss_harm_count_vs_baseline",
        ),
        movement_count=_summary_int(movement_diagnostics, "movement_count"),
        positive_movement_count=_summary_int(
            movement_diagnostics,
            "positive_movement_count",
        ),
        harmful_movement_count=_summary_int(
            movement_diagnostics,
            "harmful_movement_count",
        ),
        probability_quality_harm_movement_count=_summary_int(
            movement_diagnostics,
            "probability_quality_harm_movement_count",
        ),
        movement_diagnostics_json=movement_diagnostics,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _baseline_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(update={"final_answer_selection_value_signal": False})


def _candidate_options(
    options: HistoricalRecommendationBacktestOptions,
    spec: HistoricalFinalAnswerSelectionValueSignalSearchSpec,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "final_answer_selection_value_signal": True,
            "final_answer_selection_value_signal_strength": spec.strength,
            "final_answer_selection_value_signal_probability_min": spec.probability_min,
            "final_answer_selection_value_signal_probability_max": spec.probability_max,
            "final_answer_selection_value_signal_min_decimal_odds": spec.min_decimal_odds,
            "final_answer_selection_value_signal_max_decimal_odds": spec.max_decimal_odds,
            "final_answer_selection_value_signal_max_model_edge": spec.max_model_edge,
            "final_answer_selection_value_signal_score_min": spec.score_min,
            "final_answer_selection_value_signal_score_max": spec.score_max,
            "final_answer_selection_value_signal_competition_ids": spec.competition_ids,
            "final_answer_selection_value_signal_outcomes": spec.outcomes,
            "final_answer_selection_value_signal_max_hit_probability_deficit": (
                spec.max_hit_probability_deficit
            ),
            "final_answer_selection_value_signal_min_option_roi": (
                spec.min_option_roi
            ),
            "final_answer_selection_value_signal_max_option_risk_score": (
                spec.max_option_risk_score
            ),
        }
    )


def _candidate_specs(
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalSearchSpec]:
    if options.candidate_specs:
        return _dedupe_specs(options.candidate_specs)
    if options.movement_diagnostics_report_path is not None:
        movement_specs = _movement_conditioned_specs(options)
        if movement_specs:
            return _dedupe_specs(movement_specs)
    source_buckets = _source_buckets(options)
    specs: list[HistoricalFinalAnswerSelectionValueSignalSearchSpec] = []
    for bucket in source_buckets:
        for probability_min in options.probability_min_values:
            for probability_max in options.probability_max_values:
                if probability_min >= probability_max:
                    continue
                for max_model_edge in options.max_model_edge_values:
                    for score_min in options.score_min_values:
                        for score_max in options.score_max_values:
                            if score_min > score_max:
                                continue
                            for max_hit_probability_deficit in (
                                options.max_hit_probability_deficit_values
                            ):
                                for min_option_roi in options.min_option_roi_values:
                                    for max_option_risk_score in (
                                        options.max_option_risk_score_values
                                    ):
                                        for strength in options.strength_values:
                                            specs.append(
                                                HistoricalFinalAnswerSelectionValueSignalSearchSpec(
                                                    spec_key=(
                                                        "bucket_value_signal:"
                                                        f"{bucket.bucket_key}:"
                                                        f"strength:{strength:.4f}:"
                                                        f"prob:{probability_min:.4f}-{probability_max:.4f}:"
                                                        f"edge:{max_model_edge}:"
                                                        "max_hit_probability_deficit:"
                                                        f"{max_hit_probability_deficit}:"
                                                        f"min_option_roi:{min_option_roi}:"
                                                        "max_option_risk_score:"
                                                        f"{max_option_risk_score}"
                                                    ),
                                                    competition_ids=(
                                                        bucket.competition_id,
                                                    ),
                                                    outcomes=(bucket.outcome,),
                                                    probability_min=probability_min,
                                                    probability_max=probability_max,
                                                    min_decimal_odds=(
                                                        bucket.min_decimal_odds
                                                    ),
                                                    max_decimal_odds=(
                                                        bucket.max_decimal_odds
                                                    ),
                                                    max_model_edge=max_model_edge,
                                                    score_min=score_min,
                                                    score_max=score_max,
                                                    max_hit_probability_deficit=(
                                                        max_hit_probability_deficit
                                                    ),
                                                    min_option_roi=min_option_roi,
                                                    max_option_risk_score=(
                                                        max_option_risk_score
                                                    ),
                                                    strength=strength,
                                                    source_bucket_key=(
                                                        bucket.bucket_key
                                                    ),
                                                    source_bucket_search_candidate_key=(
                                                        bucket.source_candidate_key
                                                    ),
                                                )
                                            )
    return _dedupe_specs(specs)


def _movement_conditioned_specs(
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> list[HistoricalFinalAnswerSelectionValueSignalSearchSpec]:
    if options.movement_diagnostics_report_path is None:
        return []
    payload = loads(options.movement_diagnostics_report_path.read_text(encoding="utf-8"))
    raw_candidates = payload.get("candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    specs: list[HistoricalFinalAnswerSelectionValueSignalSearchSpec] = []
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            continue
        base_spec = _spec_from_raw(raw_candidate.get("spec"))
        if base_spec is None:
            continue
        raw_diagnostics = raw_candidate.get("movement_diagnostics_json")
        if not isinstance(raw_diagnostics, Mapping):
            continue
        raw_records = raw_diagnostics.get("records")
        records = raw_records if isinstance(raw_records, list) else []
        for record in records:
            if len(specs) >= options.max_movement_conditioned_specs:
                return specs
            specs.extend(
                _movement_conditioned_specs_from_record(
                    record,
                    base_spec=base_spec,
                    options=options,
                    remaining_limit=options.max_movement_conditioned_specs - len(specs),
                )
            )
    return specs[: options.max_movement_conditioned_specs]


def _spec_from_raw(
    raw_spec: object,
) -> HistoricalFinalAnswerSelectionValueSignalSearchSpec | None:
    if not isinstance(raw_spec, Mapping):
        return None
    try:
        return HistoricalFinalAnswerSelectionValueSignalSearchSpec.model_validate(
            raw_spec
        )
    except ValueError:
        return None


def _movement_conditioned_specs_from_record(
    raw_record: object,
    *,
    base_spec: HistoricalFinalAnswerSelectionValueSignalSearchSpec,
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
    remaining_limit: int,
) -> list[HistoricalFinalAnswerSelectionValueSignalSearchSpec]:
    if remaining_limit <= 0 or not isinstance(raw_record, Mapping):
        return []
    if raw_record.get("movement_class") not in set(
        options.movement_conditioned_classes
    ):
        return []
    raw_candidate = raw_record.get("candidate")
    if not isinstance(raw_candidate, Mapping):
        return []
    raw_selected_candidates = raw_candidate.get("selected_candidates")
    selected_candidates = (
        raw_selected_candidates if isinstance(raw_selected_candidates, list) else []
    )
    specs: list[HistoricalFinalAnswerSelectionValueSignalSearchSpec] = []
    for raw_leg in selected_candidates:
        if len(specs) >= remaining_limit:
            break
        if not isinstance(raw_leg, Mapping):
            continue
        if not _movement_leg_matches_spec(raw_leg, base_spec):
            continue
        score = _optional_float(raw_leg.get("score"))
        if score is None:
            continue
        score_min = max(0.0, score - options.movement_score_band)
        score_max = min(1.0, score + options.movement_score_band)
        specs.append(
            base_spec.model_copy(
                update={
                    "spec_key": (
                        f"{base_spec.spec_key}:movement_clean_positive:"
                        f"{_string(raw_record.get('slice_id')) or 'unknown'}:"
                        f"{_string(raw_leg.get('fixture_id')) or 'unknown'}:"
                        f"{_string(raw_leg.get('outcome')) or 'unknown'}:"
                        f"score:{score_min:.4f}-{score_max:.4f}"
                    ),
                    "score_min": score_min,
                    "score_max": score_max,
                }
            )
        )
    return specs


def _movement_leg_matches_spec(
    raw_leg: Mapping[str, object],
    spec: HistoricalFinalAnswerSelectionValueSignalSearchSpec,
) -> bool:
    outcome = _string(raw_leg.get("outcome"))
    if spec.outcomes and outcome not in set(spec.outcomes):
        return False
    decimal_odds = _optional_float(raw_leg.get("decimal_odds"))
    if decimal_odds is None:
        return False
    if decimal_odds < spec.min_decimal_odds or decimal_odds > spec.max_decimal_odds:
        return False
    probability = _optional_float(raw_leg.get("probability"))
    if probability is None:
        return False
    if probability < spec.probability_min or probability >= spec.probability_max:
        return False
    model_edge = _optional_float(raw_leg.get("model_edge"))
    return not (
        spec.max_model_edge is not None
        and model_edge is not None
        and model_edge >= spec.max_model_edge
    )


def _source_buckets(
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> list[_SourceBucket]:
    buckets: list[_SourceBucket] = []
    if options.bucket_search_report_path is not None:
        payload = loads(options.bucket_search_report_path.read_text(encoding="utf-8"))
        raw_candidates = payload.get("candidates")
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
        for candidate in candidates:
            buckets.extend(_source_buckets_from_candidate(candidate, options=options))
    buckets.extend(_parse_bucket_key(bucket_key) for bucket_key in options.bucket_keys)
    deduped: dict[str, _SourceBucket] = {}
    for bucket in sorted(buckets, key=_source_bucket_sort_key):
        deduped.setdefault(bucket.bucket_key, bucket)
    return list(deduped.values())[: options.max_source_bucket_candidates]


def _source_buckets_from_candidate(
    raw_candidate: object,
    *,
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> list[_SourceBucket]:
    if not isinstance(raw_candidate, Mapping):
        return []
    hit_delta = _int(raw_candidate.get("final_answer_hit_delta_count"))
    profit_loss_delta = _float(raw_candidate.get("profit_loss_delta"))
    if hit_delta < options.min_source_final_answer_hit_delta:
        return []
    if profit_loss_delta < options.min_source_profit_loss_delta:
        return []
    raw_spec = raw_candidate.get("spec")
    if not isinstance(raw_spec, Mapping):
        return []
    source_candidate_key = _string(raw_candidate.get("candidate_key"))
    source_rank = _optional_int(raw_candidate.get("rank"))
    raw_bucket_keys = raw_spec.get("bucket_keys")
    bucket_keys = raw_bucket_keys if isinstance(raw_bucket_keys, Sequence) else []
    buckets: list[_SourceBucket] = []
    for bucket_key in bucket_keys:
        if not isinstance(bucket_key, str):
            continue
        bucket = _parse_bucket_key(bucket_key).model_copy(
            update={
                "source_candidate_key": source_candidate_key,
                "source_rank": source_rank,
                "source_final_answer_hit_delta_count": hit_delta,
                "source_profit_loss_delta": profit_loss_delta,
            }
        )
        buckets.append(bucket)
    return buckets


def _parse_bucket_key(bucket_key: str) -> _SourceBucket:
    parts = bucket_key.split(":")
    if len(parts) != 4:
        raise ValueError(f"Invalid bucket key: {bucket_key}")
    competition_id, market_type, outcome, raw_range = parts
    raw_start, separator, raw_end = raw_range.partition("-")
    if not separator:
        raise ValueError(f"Invalid bucket key range: {bucket_key}")
    bucket_start = float(raw_start)
    bucket_end = float(raw_end)
    if bucket_start <= 0 or bucket_end <= bucket_start:
        raise ValueError(f"Invalid bucket key bounds: {bucket_key}")
    return _SourceBucket(
        bucket_key=bucket_key,
        competition_id=competition_id,
        market_type=market_type,
        outcome=outcome,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
    )


def _source_bucket_sort_key(bucket: _SourceBucket) -> tuple[int, float, str]:
    return (
        -(bucket.source_final_answer_hit_delta_count),
        -(bucket.source_profit_loss_delta),
        bucket.bucket_key,
    )


def _suite_deltas(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> dict[str, object]:
    return {
        "changed_final_answer_count": _suite_final_answer_changed_count(
            baseline_suite,
            candidate_suite,
        ),
        "final_answer_hit_delta_count": _summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_count",
        )
        - _summary_int(baseline_suite.summary_json, "candidate_final_hit_count"),
        "final_answer_hit_rate_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_final_hit_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_final_hit_rate"),
        ),
        "roi_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_roi"),
            _summary_number(baseline_suite.summary_json, "candidate_roi"),
        ),
        "profit_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_profit_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_profit_loss"),
        ),
        "brier_score_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_brier_score"),
            _summary_number(baseline_suite.summary_json, "candidate_brier_score"),
        ),
        "log_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_log_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_log_loss"),
        ),
        "mean_calibration_error_delta": _optional_delta(
            _summary_number(
                candidate_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
            _summary_number(
                baseline_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
        ),
        "final_hit_harm_count_vs_baseline": _suite_final_hit_harm_count(
            baseline_suite,
            candidate_suite,
        ),
        "profit_loss_harm_count_vs_baseline": _suite_profit_loss_harm_count(
            baseline_suite,
            candidate_suite,
        ),
    }


def _decision_reasons(
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    deltas: Mapping[str, object],
    options: HistoricalFinalAnswerSelectionValueSignalSearchOptions,
) -> list[str]:
    optional_reasons = [
        _minimum_reason(
            "affected_leg_count",
            _summary_int(
                candidate_suite.summary_json,
                "candidate_final_answer_selection_value_signal_affected_leg_count",
            ),
            options.min_affected_leg_count,
        ),
        _minimum_reason(
            "final_answer_count",
            _summary_int(candidate_suite.summary_json, "candidate_final_hit_sample_size"),
            options.min_final_answer_count,
        ),
        _minimum_reason(
            "changed_final_answer_count",
            _int_delta(deltas, "changed_final_answer_count"),
            options.min_changed_final_answer_count,
        ),
        _minimum_reason(
            "final_answer_hit_delta_count",
            _int_delta(deltas, "final_answer_hit_delta_count"),
            options.min_final_answer_hit_count_delta,
        ),
        _minimum_reason(
            "final_answer_hit_rate_delta",
            _float_delta(deltas, "final_answer_hit_rate_delta"),
            options.min_final_answer_hit_rate_delta,
        ),
        _minimum_reason("roi_delta", _float_delta(deltas, "roi_delta"), options.min_roi_delta),
        _minimum_reason(
            "profit_loss_delta",
            _float_delta(deltas, "profit_loss_delta"),
            options.min_profit_loss_delta,
        ),
        _maximum_reason(
            "brier_score_delta",
            _float_delta(deltas, "brier_score_delta"),
            options.max_brier_score_delta,
        ),
        _maximum_reason(
            "log_loss_delta",
            _float_delta(deltas, "log_loss_delta"),
            options.max_log_loss_delta,
        ),
        _maximum_reason(
            "mean_calibration_error_delta",
            _float_delta(deltas, "mean_calibration_error_delta"),
            options.max_mean_calibration_error_delta,
        ),
        _maximum_reason(
            "final_hit_harm_count_vs_baseline",
            _int_delta(deltas, "final_hit_harm_count_vs_baseline"),
            options.max_final_hit_harm_count_vs_baseline,
        ),
        _maximum_reason(
            "profit_loss_harm_count_vs_baseline",
            _int_delta(deltas, "profit_loss_harm_count_vs_baseline"),
            options.max_profit_loss_harm_count_vs_baseline,
        ),
    ]
    reasons = [reason for reason in optional_reasons if reason is not None]
    candidate_roi = _summary_number(candidate_suite.summary_json, "candidate_roi")
    if candidate_roi is None or candidate_roi < options.min_candidate_roi:
        reasons.append("candidate_roi:below_threshold")
    return reasons


def _suite_final_answer_changed_count(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if _final_answer_signature(baseline_comparison.candidate.final_answer)
        != _final_answer_signature(candidate_comparison.candidate.final_answer)
    )


def _suite_final_hit_harm_count(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if candidate_comparison.candidate.final_hit_count
        < baseline_comparison.candidate.final_hit_count
    )


def _suite_profit_loss_harm_count(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if candidate_comparison.candidate.profit_loss
        < baseline_comparison.candidate.profit_loss
    )


def _suite_movement_diagnostics(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    include_records: bool,
    record_limit: int,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    movement_count = 0
    positive_movement_count = 0
    harmful_movement_count = 0
    probability_quality_harm_movement_count = 0
    clean_positive_movement_count = 0
    for baseline_comparison, candidate_comparison in zip(
        baseline_suite.comparisons,
        candidate_suite.comparisons,
        strict=True,
    ):
        baseline_result = baseline_comparison.candidate
        candidate_result = candidate_comparison.candidate
        baseline_signature = _final_answer_signature(baseline_result.final_answer)
        candidate_signature = _final_answer_signature(candidate_result.final_answer)
        if baseline_signature == candidate_signature:
            continue
        movement_count += 1
        movement = _movement_record(
            baseline_comparison,
            candidate_comparison,
            baseline_signature=baseline_signature,
            candidate_signature=candidate_signature,
        )
        if movement["settlement_gain"] is True:
            positive_movement_count += 1
        if movement["harmful_movement"] is True:
            harmful_movement_count += 1
        if movement["probability_quality_harm"] is True:
            probability_quality_harm_movement_count += 1
        if movement["movement_class"] == "clean_positive":
            clean_positive_movement_count += 1
        if include_records and len(records) < record_limit:
            records.append(movement)
    diagnostic: dict[str, object] = {
        "movement_count": movement_count,
        "positive_movement_count": positive_movement_count,
        "harmful_movement_count": harmful_movement_count,
        "probability_quality_harm_movement_count": (
            probability_quality_harm_movement_count
        ),
        "clean_positive_movement_count": clean_positive_movement_count,
        "record_limit": record_limit if include_records else 0,
        "record_count": len(records),
        "truncated": include_records and movement_count > len(records),
    }
    if include_records:
        diagnostic["records"] = records
    return diagnostic


def _movement_record(
    baseline_comparison: HistoricalRecommendationBacktestComparisonResult,
    candidate_comparison: HistoricalRecommendationBacktestComparisonResult,
    *,
    baseline_signature: object,
    candidate_signature: object,
) -> dict[str, object]:
    baseline = baseline_comparison.candidate
    candidate = candidate_comparison.candidate
    final_hit_delta = candidate.final_hit_count - baseline.final_hit_count
    profit_loss_delta = candidate.profit_loss - baseline.profit_loss
    roi_delta = _optional_delta(candidate.roi, baseline.roi)
    brier_score_delta = _optional_delta(candidate.brier_score, baseline.brier_score)
    log_loss_delta = _optional_delta(candidate.log_loss, baseline.log_loss)
    mean_calibration_error_delta = _optional_delta(
        candidate.mean_calibration_error,
        baseline.mean_calibration_error,
    )
    probability_quality_harm = any(
        delta is not None and delta > 0.0
        for delta in (
            brier_score_delta,
            log_loss_delta,
            mean_calibration_error_delta,
        )
    )
    settlement_gain = final_hit_delta > 0 or profit_loss_delta > 0.0
    harmful_movement = final_hit_delta < 0 or profit_loss_delta < 0.0
    return {
        "slice_id": candidate.slice_id,
        "baseline_signature": baseline_signature,
        "candidate_signature": candidate_signature,
        "movement_class": _movement_class(
            settlement_gain=settlement_gain,
            harmful_movement=harmful_movement,
            probability_quality_harm=probability_quality_harm,
        ),
        "settlement_gain": settlement_gain,
        "harmful_movement": harmful_movement,
        "probability_quality_harm": probability_quality_harm,
        "final_hit_delta": final_hit_delta,
        "profit_loss_delta": profit_loss_delta,
        "roi_delta": roi_delta,
        "brier_score_delta": brier_score_delta,
        "log_loss_delta": log_loss_delta,
        "mean_calibration_error_delta": mean_calibration_error_delta,
        "baseline": _final_answer_movement_snapshot(baseline.final_answer),
        "candidate": _final_answer_movement_snapshot(candidate.final_answer),
        "candidate_affected_leg_count": _summary_int(
            candidate.summary_json,
            "final_answer_selection_value_signal_affected_leg_count",
        ),
        "candidate_guard_blocked_option_count": _summary_int(
            candidate.summary_json,
            "final_answer_selection_value_signal_guard_blocked_option_count",
        ),
    }


def _movement_class(
    *,
    settlement_gain: bool,
    harmful_movement: bool,
    probability_quality_harm: bool,
) -> str:
    if harmful_movement:
        return "harmful"
    if settlement_gain and not probability_quality_harm:
        return "clean_positive"
    if settlement_gain:
        return "positive_with_probability_harm"
    if probability_quality_harm:
        return "quality_harm_only"
    return "changed_neutral"


def _final_answer_movement_snapshot(
    final_answer: HistoricalRecommendationScenarioResult | None,
) -> dict[str, object] | None:
    if final_answer is None:
        return None
    return {
        "scenario_key": final_answer.scenario.scenario_key,
        "selected_fixture_ids": list(final_answer.selected_fixture_ids),
        "selected_outcomes": dict(final_answer.selected_outcomes),
        "selected_candidates": _movement_selected_candidates(final_answer),
        "total_stake": final_answer.total_stake,
        "actual_return": final_answer.actual_return,
        "profit_loss": final_answer.profit_loss,
        "roi": final_answer.roi,
        "expected_hit_probability": final_answer.expected_hit_probability,
        "actual_hit": final_answer.actual_hit,
        "brier_score": final_answer.brier_score,
        "log_loss": final_answer.log_loss,
        "calibration_error": final_answer.calibration_error,
    }


def _movement_selected_candidates(
    final_answer: HistoricalRecommendationScenarioResult,
) -> list[dict[str, object]]:
    if final_answer.option is None:
        return []
    return [
        _movement_selected_candidate_snapshot(scored)
        for scored in final_answer.option.selection.selected_candidates
    ]


def _movement_selected_candidate_snapshot(
    scored: ScoredRecommendationCandidate,
) -> dict[str, object]:
    candidate = scored.candidate
    return {
        "fixture_id": candidate.fixture_id,
        "market_type": candidate.market_type,
        "outcome": candidate.outcome,
        "probability": candidate.probability,
        "model_probability": candidate.model_probability,
        "calibrated_probability": candidate.calibrated_probability,
        "probability_source": candidate.probability_source,
        "decimal_odds": candidate.decimal_odds,
        "market_probability": candidate.effective_market_probability(),
        "model_edge": candidate.effective_model_edge(),
        "score": scored.score,
        "data_quality_score": candidate.data_quality_score,
        "model_confidence_score": candidate.model_confidence_score,
        "calibration_score": candidate.calibration_score,
        "odds_stability_score": candidate.odds_stability_score,
        "volatility_penalty": candidate.volatility_penalty,
    }


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


def _ranked_candidates(
    candidates: Sequence[HistoricalFinalAnswerSelectionValueSignalSearchCandidate],
) -> list[HistoricalFinalAnswerSelectionValueSignalSearchCandidate]:
    ranked = sorted(candidates, key=_candidate_sort_key)
    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(ranked)
    ]


def _candidate_sort_key(
    candidate: HistoricalFinalAnswerSelectionValueSignalSearchCandidate,
) -> tuple[int, float, float, float, str]:
    return (
        0 if candidate.decision == "accepted" else 1,
        -(candidate.final_answer_hit_rate_delta or 0.0),
        -(candidate.roi_delta or 0.0),
        candidate.brier_score_delta or 0.0,
        candidate.candidate_key,
    )


def _dedupe_specs(
    specs: Sequence[HistoricalFinalAnswerSelectionValueSignalSearchSpec],
) -> list[HistoricalFinalAnswerSelectionValueSignalSearchSpec]:
    deduped: dict[str, HistoricalFinalAnswerSelectionValueSignalSearchSpec] = {}
    for spec in specs:
        key = dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        deduped.setdefault(key, spec)
    return list(deduped.values())


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Search final-answer selection-side value signals without changing "
            "probabilities."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--bucket-search-report", type=Path)
    parser.add_argument("--movement-diagnostics-report", type=Path)
    parser.add_argument("--bucket-keys", default="")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--strength-values", default="0.02,0.04,0.08")
    parser.add_argument("--probability-min-values", default="0.0")
    parser.add_argument("--probability-max-values", default="1.0")
    parser.add_argument("--max-model-edge-values", default="")
    parser.add_argument("--score-min-values", default="0.0")
    parser.add_argument("--score-max-values", default="1.0")
    parser.add_argument("--max-hit-probability-deficit-values", default="")
    parser.add_argument("--min-option-roi-values", default="")
    parser.add_argument("--max-option-risk-score-values", default="")
    parser.add_argument("--max-source-bucket-candidates", type=int, default=1)
    parser.add_argument("--min-source-final-answer-hit-delta", type=int, default=1)
    parser.add_argument("--min-source-profit-loss-delta", type=float, default=0.0)
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
    parser.add_argument("--min-affected-leg-count", type=int, default=1)
    parser.add_argument("--min-final-answer-count", type=int, default=20)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float, default=-1.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--include-movement-diagnostics", action="store_true")
    parser.add_argument("--movement-diagnostics-limit", type=int, default=32)
    parser.add_argument("--movement-score-band", type=float, default=0.0015)
    parser.add_argument("--max-movement-conditioned-specs", type=int, default=8)
    parser.add_argument("--movement-conditioned-classes", default="clean_positive")
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    if (
        args.bucket_search_report is None
        and args.movement_diagnostics_report is None
        and not _csv(args.bucket_keys)
    ):
        parser.error(
            "provide --bucket-search-report, --movement-diagnostics-report, "
            "or --bucket-keys"
        )
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSelectionValueSignalSearchOptions:
    return HistoricalFinalAnswerSelectionValueSignalSearchOptions(
        bucket_search_report_path=args.bucket_search_report,
        movement_diagnostics_report_path=args.movement_diagnostics_report,
        bucket_keys=tuple(_csv(args.bucket_keys)),
        strength_values=tuple(_float_csv(args.strength_values)),
        probability_min_values=tuple(_float_csv(args.probability_min_values)),
        probability_max_values=tuple(_float_csv(args.probability_max_values)),
        max_model_edge_values=tuple(_optional_float_csv(args.max_model_edge_values)),
        score_min_values=tuple(_float_csv(args.score_min_values)),
        score_max_values=tuple(_float_csv(args.score_max_values)),
        max_hit_probability_deficit_values=tuple(
            _optional_float_csv(args.max_hit_probability_deficit_values)
        ),
        min_option_roi_values=tuple(_optional_float_csv(args.min_option_roi_values)),
        max_option_risk_score_values=tuple(
            _optional_float_csv(args.max_option_risk_score_values)
        ),
        max_source_bucket_candidates=args.max_source_bucket_candidates,
        min_source_final_answer_hit_delta=args.min_source_final_answer_hit_delta,
        min_source_profit_loss_delta=args.min_source_profit_loss_delta,
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
        include_movement_diagnostics=args.include_movement_diagnostics,
        movement_diagnostics_limit=args.movement_diagnostics_limit,
        movement_score_band=args.movement_score_band,
        max_movement_conditioned_specs=args.max_movement_conditioned_specs,
        movement_conditioned_classes=tuple(_csv(args.movement_conditioned_classes)),
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


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0


def _summary_number(summary: Mapping[str, object], key: str) -> float | None:
    return _optional_float(summary.get(key))


def _int_delta(deltas: Mapping[str, object], key: str) -> int:
    return _summary_int(deltas, key)


def _float_delta(deltas: Mapping[str, object], key: str) -> float | None:
    return _optional_float(deltas.get(key))


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return None


def _int(value: object) -> int:
    return _optional_int(value) or 0


def _float(value: object) -> float:
    return _optional_float(value) or 0.0


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _float_csv(value: str | None) -> list[float]:
    return [float(item) for item in _csv(value)]


def _optional_float_csv(value: str | None) -> list[float | None]:
    values = _csv(value)
    if not values:
        return [None]
    return [None if item.lower() == "none" else float(item) for item in values]


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(
        dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"final_answer_selection_value_signal_candidate:{digest}"


def _report_key(
    summary: Mapping[str, object],
    candidates: Sequence[HistoricalFinalAnswerSelectionValueSignalSearchCandidate],
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
    return f"historical_final_answer_selection_value_signal_search:{digest}"
