from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    _final_answer_signature,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.marginal_loss_driver_candidate_guardrail_ablation import (
    HistoricalMarginalLossDriverCandidateGuardrailAblationOptions,
    _aggregate_deltas,
    _baseline_backtest_options,
    _candidate_backtest_options,
    _historical_slices_from_args,
    _int_delta,
    _manifest_summary,
    _number,
    _objective_improvement_metric_codes,
    _reason_codes,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalMarginalLossDriverCandidateGuardrailGridStatus = Literal[
    "accepted",
    "rejected",
]


class HistoricalMarginalLossDriverCandidateGuardrailGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    competition_groups: tuple[tuple[str, ...], ...] = (("JPN_J1",),)
    probability_min_values: tuple[float, ...] = (0.45, 0.55)
    probability_max_values: tuple[float, ...] = (0.55, 0.65)
    max_decimal_odds_values: tuple[float, ...] = (1.50, 1.80, 2.20)
    max_model_edge_values: tuple[float, ...] = (-0.02, -0.04)
    max_calibration_score_values: tuple[float | None, ...] = (None,)
    max_model_confidence_score_values: tuple[float | None, ...] = (None,)
    max_odds_stability_score_values: tuple[float | None, ...] = (None,)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_indices: tuple[int, ...] = ()
    min_excluded_candidate_count: int = Field(default=1, ge=0)
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_baseline: int | None = Field(default=None, ge=0)
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    min_upset_capture_rate_delta: float = 0.0
    require_objective_improvement: bool = True
    min_objective_final_hit_rate_delta: float = 0.0
    min_objective_roi_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)


class HistoricalMarginalLossDriverCandidateGuardrailGridSpec(BaseModel):
    candidate_index: int = Field(ge=0)
    competition_ids: tuple[str, ...]
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    max_decimal_odds: float = Field(gt=1.0)
    max_model_edge: float
    max_calibration_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_model_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_odds_stability_score: float | None = Field(default=None, ge=0.0, le=1.0)


class HistoricalMarginalLossDriverCandidateGuardrailGridCandidate(BaseModel):
    candidate_key: str
    status: HistoricalMarginalLossDriverCandidateGuardrailGridStatus
    candidate_index: int = Field(ge=0)
    competition_ids: tuple[str, ...]
    probability_min: float
    probability_max: float
    max_decimal_odds: float
    max_model_edge: float
    max_calibration_score: float | None = None
    max_model_confidence_score: float | None = None
    max_odds_stability_score: float | None = None
    excluded_candidate_count: int = Field(ge=0)
    final_answer_changed_count: int = Field(ge=0)
    baseline_final_hit_count: int = Field(ge=0)
    candidate_final_hit_count: int = Field(ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    baseline_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    objective_improvement_satisfied: bool = False
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarginalLossDriverCandidateGuardrailGridReport(BaseModel):
    report_key: str
    status: Literal["generated"]
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    evaluated_candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    candidates: list[HistoricalMarginalLossDriverCandidateGuardrailGridCandidate] = (
        Field(default_factory=list)
    )
    accepted_candidates: list[
        HistoricalMarginalLossDriverCandidateGuardrailGridCandidate
    ] = Field(default_factory=list)
    best_candidate: (
        HistoricalMarginalLossDriverCandidateGuardrailGridCandidate | None
    ) = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: (
        HistoricalMarginalLossDriverCandidateGuardrailGridOptions | None
    ) = None,
) -> HistoricalMarginalLossDriverCandidateGuardrailGridReport:
    resolved_options = (
        options or HistoricalMarginalLossDriverCandidateGuardrailGridOptions()
    )
    candidate_specs = _candidate_specs(resolved_options)
    evaluated_specs = _evaluated_candidate_specs(candidate_specs, resolved_options)
    baseline_options = _baseline_backtest_options(
        _base_ablation_options(resolved_options)
    )
    baseline_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=baseline_options,
        )
        for historical_slice in historical_slices
    ]
    warnings = [
        warning for result in baseline_results for warning in result.warnings
    ]
    candidates = [
        _evaluate_guardrail_candidate(
            historical_slices,
            baseline_results=baseline_results,
            spec=spec,
            options=resolved_options,
        )
        for spec in evaluated_specs
    ]
    warnings.extend(warning for candidate in candidates for warning in candidate.warnings)
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_marginal_loss_driver_candidate_guardrail_grid_v3_1"
        ),
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "candidate_count": len(candidate_specs),
        "evaluated_candidate_count": len(candidates),
        "candidate_selection_mode": (
            "explicit_indices" if resolved_options.candidate_indices else "range"
        ),
        "requested_candidate_indices": list(resolved_options.candidate_indices),
        "unmatched_requested_candidate_indices": [
            candidate_index
            for candidate_index in resolved_options.candidate_indices
            if candidate_index not in {candidate.candidate_index for candidate in candidates}
        ],
        "candidate_start_index": resolved_options.candidate_start_index,
        "candidate_limit": resolved_options.candidate_limit,
        "candidate_indices": [
            candidate.candidate_index for candidate in candidates
        ],
        "missing_candidate_indices": _missing_candidate_indices(
            [candidate.candidate_index for candidate in candidates],
            len(candidate_specs),
        ),
        "next_candidate_start_index": _next_candidate_start_index(
            [candidate.candidate_index for candidate in candidates],
            len(candidate_specs),
        ),
        "is_full_grid": bool(candidate_specs)
        and not _missing_candidate_indices(
            [candidate.candidate_index for candidate in candidates],
            len(candidate_specs),
        ),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "optimizer_profile": resolved_options.optimizer_profile,
        "competition_groups": [
            list(competition_group)
            for competition_group in resolved_options.competition_groups
        ],
        "probability_min_values": list(resolved_options.probability_min_values),
        "probability_max_values": list(resolved_options.probability_max_values),
        "max_decimal_odds_values": list(resolved_options.max_decimal_odds_values),
        "max_model_edge_values": list(resolved_options.max_model_edge_values),
        "max_calibration_score_values": list(
            resolved_options.max_calibration_score_values
        ),
        "max_model_confidence_score_values": list(
            resolved_options.max_model_confidence_score_values
        ),
        "max_odds_stability_score_values": list(
            resolved_options.max_odds_stability_score_values
        ),
        "max_final_hit_harm_count_vs_baseline": (
            resolved_options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            resolved_options.max_profit_loss_harm_count_vs_baseline
        ),
        "require_objective_improvement": (
            resolved_options.require_objective_improvement
        ),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "best_candidate_status": (
            best_candidate.status if best_candidate is not None else None
        ),
        "best_candidate_deltas": (
            best_candidate.deltas_json if best_candidate is not None else {}
        ),
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalMarginalLossDriverCandidateGuardrailGridReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        candidate_count=len(candidate_specs),
        evaluated_candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def merge_historical_marginal_loss_driver_candidate_guardrail_grid_reports(
    reports: Sequence[HistoricalMarginalLossDriverCandidateGuardrailGridReport],
    *,
    source_paths: Sequence[Path] = (),
) -> HistoricalMarginalLossDriverCandidateGuardrailGridReport:
    if not reports:
        raise ValueError("Provide at least one candidate guardrail grid report to merge")
    candidates = sorted(
        [candidate for report in reports for candidate in report.candidates],
        key=lambda candidate: (candidate.candidate_index, candidate.candidate_key),
    )
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    first_report = reports[0]
    candidate_count = max(report.candidate_count for report in reports)
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    warnings = [warning for report in reports for warning in report.warnings]
    warnings.extend(_merge_warnings(reports, candidate_indices, candidate_count))
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_marginal_loss_driver_candidate_guardrail_grid_merged_v3_1"
        ),
        "source_report_count": len(reports),
        "source_report_keys": [report.report_key for report in reports],
        "source_report_paths": [str(path) for path in source_paths],
        "slice_count": first_report.slice_count,
        "fixture_count": first_report.fixture_count,
        "prediction_count": first_report.prediction_count,
        "candidate_count": candidate_count,
        "evaluated_candidate_count": len(candidates),
        "candidate_selection_mode": "merged",
        "candidate_start_index": min(candidate_indices) if candidate_indices else 0,
        "candidate_limit": len(candidates),
        "candidate_indices": candidate_indices,
        "missing_candidate_indices": _missing_candidate_indices(
            candidate_indices,
            candidate_count,
        ),
        "duplicate_candidate_indices": _duplicate_candidate_indices(candidate_indices),
        "is_full_grid": (
            bool(candidates)
            and len(candidates) == candidate_count
            and not _missing_candidate_indices(candidate_indices, candidate_count)
            and not _duplicate_candidate_indices(candidate_indices)
        ),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "best_candidate_status": (
            best_candidate.status if best_candidate is not None else None
        ),
        "best_candidate_deltas": (
            best_candidate.deltas_json if best_candidate is not None else {}
        ),
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "warnings": warnings,
    }
    report_key = _merged_report_key(summary)
    return HistoricalMarginalLossDriverCandidateGuardrailGridReport(
        report_key=report_key,
        status="generated",
        slice_count=first_report.slice_count,
        fixture_count=first_report.fixture_count,
        prediction_count=first_report.prediction_count,
        candidate_count=candidate_count,
        evaluated_candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_marginal_loss_driver_candidate_guardrail_grid_report(
    path: Path | str,
) -> HistoricalMarginalLossDriverCandidateGuardrailGridReport:
    return HistoricalMarginalLossDriverCandidateGuardrailGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded = _historical_slices_from_args(args)
    report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        loaded.slices,
        options=_options_from_args(args),
    )
    if loaded.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
    if loaded.warnings:
        report.warnings.extend(loaded.warnings)
        report.summary_json["manifest_warnings"] = loaded.warnings
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


def merge_main(argv: Sequence[str] | None = None) -> None:
    args = _parse_merge_args(argv)
    reports = [
        load_historical_marginal_loss_driver_candidate_guardrail_grid_report(
            report_path
        )
        for report_path in args.report_paths
    ]
    report = merge_historical_marginal_loss_driver_candidate_guardrail_grid_reports(
        reports,
        source_paths=args.report_paths,
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


def _evaluate_guardrail_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    spec: HistoricalMarginalLossDriverCandidateGuardrailGridSpec,
    options: HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
) -> HistoricalMarginalLossDriverCandidateGuardrailGridCandidate:
    ablation_options = _ablation_options_from_spec(spec, options=options)
    candidate_options = _candidate_backtest_options(ablation_options)
    candidate_results = [
        run_historical_recommendation_backtest(
            historical_slice,
            options=candidate_options,
        )
        for historical_slice in historical_slices
    ]
    deltas = _aggregate_deltas(baseline_results, candidate_results)
    objective_metric_codes = _objective_improvement_metric_codes(
        deltas,
        options=ablation_options,
    )
    objective_improvement_satisfied = (
        not options.require_objective_improvement or bool(objective_metric_codes)
    )
    reason_codes = _reason_codes(
        deltas,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=ablation_options,
    )
    status: HistoricalMarginalLossDriverCandidateGuardrailGridStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    warnings = [
        warning for result in candidate_results for warning in result.warnings
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_marginal_loss_driver_candidate_guardrail_grid_candidate_v3_1"
        ),
        "status": status,
        "candidate_index": spec.candidate_index,
        "competition_ids": list(spec.competition_ids),
        "probability_min": spec.probability_min,
        "probability_max": spec.probability_max,
        "max_decimal_odds": spec.max_decimal_odds,
        "max_model_edge": spec.max_model_edge,
        "max_calibration_score": spec.max_calibration_score,
        "max_model_confidence_score": spec.max_model_confidence_score,
        "max_odds_stability_score": spec.max_odds_stability_score,
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "reason_codes": reason_codes,
        "deltas": deltas,
        "warning_count": len(warnings),
    }
    candidate_key = _candidate_key(summary)
    return HistoricalMarginalLossDriverCandidateGuardrailGridCandidate(
        candidate_key=candidate_key,
        status=status,
        candidate_index=spec.candidate_index,
        competition_ids=spec.competition_ids,
        probability_min=spec.probability_min,
        probability_max=spec.probability_max,
        max_decimal_odds=spec.max_decimal_odds,
        max_model_edge=spec.max_model_edge,
        max_calibration_score=spec.max_calibration_score,
        max_model_confidence_score=spec.max_model_confidence_score,
        max_odds_stability_score=spec.max_odds_stability_score,
        excluded_candidate_count=_int_delta(deltas, "excluded_candidate_count"),
        final_answer_changed_count=_final_answer_changed_count(
            baseline_results,
            candidate_results,
        ),
        baseline_final_hit_count=_int_delta(deltas, "baseline_final_hit_count"),
        candidate_final_hit_count=_int_delta(deltas, "candidate_final_hit_count"),
        final_hit_harm_count_vs_baseline=_int_delta(
            deltas,
            "final_hit_harm_count_vs_baseline",
        ),
        baseline_final_hit_rate=_number(deltas, "baseline_final_hit_rate"),
        candidate_final_hit_rate=_number(deltas, "candidate_final_hit_rate"),
        baseline_roi=_number(deltas, "baseline_roi"),
        candidate_roi=_number(deltas, "candidate_roi"),
        baseline_profit_loss=_number(deltas, "baseline_profit_loss") or 0.0,
        candidate_profit_loss=_number(deltas, "candidate_profit_loss") or 0.0,
        profit_loss_harm_count_vs_baseline=_int_delta(
            deltas,
            "profit_loss_harm_count_vs_baseline",
        ),
        objective_improvement_satisfied=objective_improvement_satisfied,
        objective_improvement_metric_codes=objective_metric_codes,
        deltas_json=deltas,
        reason_codes=reason_codes,
        warnings=warnings,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _base_ablation_options(
    options: HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationOptions:
    return HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
        backtest_options=options.backtest_options,
        optimizer_profile=options.optimizer_profile,
    )


def _ablation_options_from_spec(
    spec: HistoricalMarginalLossDriverCandidateGuardrailGridSpec,
    *,
    options: HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
) -> HistoricalMarginalLossDriverCandidateGuardrailAblationOptions:
    return HistoricalMarginalLossDriverCandidateGuardrailAblationOptions(
        backtest_options=options.backtest_options,
        optimizer_profile=options.optimizer_profile,
        competition_ids=spec.competition_ids,
        probability_min=spec.probability_min,
        probability_max=spec.probability_max,
        max_decimal_odds=spec.max_decimal_odds,
        max_model_edge=spec.max_model_edge,
        max_calibration_score=spec.max_calibration_score,
        max_model_confidence_score=spec.max_model_confidence_score,
        max_odds_stability_score=spec.max_odds_stability_score,
        min_excluded_candidate_count=options.min_excluded_candidate_count,
        min_final_hit_count_delta=options.min_final_hit_count_delta,
        min_final_hit_rate_delta=options.min_final_hit_rate_delta,
        min_roi_delta=options.min_roi_delta,
        min_profit_loss_delta=options.min_profit_loss_delta,
        max_final_hit_harm_count_vs_baseline=(
            options.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            options.max_profit_loss_harm_count_vs_baseline
        ),
        max_brier_score_delta=options.max_brier_score_delta,
        max_log_loss_delta=options.max_log_loss_delta,
        max_mean_calibration_error_delta=options.max_mean_calibration_error_delta,
        min_upset_capture_rate_delta=options.min_upset_capture_rate_delta,
        require_objective_improvement=options.require_objective_improvement,
        min_objective_final_hit_rate_delta=options.min_objective_final_hit_rate_delta,
        min_objective_roi_delta=options.min_objective_roi_delta,
        comparison_epsilon=options.comparison_epsilon,
    )


def _candidate_specs(
    options: HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
) -> list[HistoricalMarginalLossDriverCandidateGuardrailGridSpec]:
    specs: list[HistoricalMarginalLossDriverCandidateGuardrailGridSpec] = []
    for (
        competition_ids,
        probability_min,
        probability_max,
        max_decimal_odds,
        max_model_edge,
        max_calibration_score,
        max_model_confidence_score,
        max_odds_stability_score,
    ) in product(
        options.competition_groups,
        options.probability_min_values,
        options.probability_max_values,
        options.max_decimal_odds_values,
        options.max_model_edge_values,
        options.max_calibration_score_values,
        options.max_model_confidence_score_values,
        options.max_odds_stability_score_values,
    ):
        if not competition_ids or probability_max <= probability_min:
            continue
        specs.append(
            HistoricalMarginalLossDriverCandidateGuardrailGridSpec(
                candidate_index=len(specs),
                competition_ids=competition_ids,
                probability_min=probability_min,
                probability_max=probability_max,
                max_decimal_odds=max_decimal_odds,
                max_model_edge=max_model_edge,
                max_calibration_score=max_calibration_score,
                max_model_confidence_score=max_model_confidence_score,
                max_odds_stability_score=max_odds_stability_score,
            )
        )
    return specs


def _evaluated_candidate_specs(
    specs: Sequence[HistoricalMarginalLossDriverCandidateGuardrailGridSpec],
    options: HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
) -> list[HistoricalMarginalLossDriverCandidateGuardrailGridSpec]:
    if options.candidate_indices:
        requested_indices = set(options.candidate_indices)
        return [
            spec
            for spec in specs
            if spec.candidate_index in requested_indices
        ]
    start = options.candidate_start_index
    end = None if options.candidate_limit is None else start + options.candidate_limit
    return list(specs[start:end])


def _best_candidate(
    candidates: Sequence[HistoricalMarginalLossDriverCandidateGuardrailGridCandidate],
) -> HistoricalMarginalLossDriverCandidateGuardrailGridCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalMarginalLossDriverCandidateGuardrailGridCandidate,
) -> tuple[int, float, float, float, float, int, int, int, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _number(candidate.deltas_json, "roi_delta") or -999.0,
        _number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        _number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        -(_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        -candidate.final_hit_harm_count_vs_baseline,
        -candidate.profit_loss_harm_count_vs_baseline,
        candidate.excluded_candidate_count,
        candidate.candidate_key,
    )


def _final_answer_changed_count(
    baseline_results: Sequence[HistoricalRecommendationBacktestResult],
    candidate_results: Sequence[HistoricalRecommendationBacktestResult],
) -> int:
    return sum(
        1
        for baseline, candidate in zip(baseline_results, candidate_results, strict=True)
        if _final_answer_signature(baseline.final_answer)
        != _final_answer_signature(candidate.final_answer)
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Search narrow marginal loss-driver hard guardrail candidates."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default="2x1")
    parser.add_argument("--modes", default="single,multiple")
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
    parser.add_argument("--max-budget", type=float, default=64.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=80.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=2)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--competitions", default="JPN_J1")
    parser.add_argument("--competition-group", action="append")
    parser.add_argument("--probability-min-values", default="0.45,0.55")
    parser.add_argument("--probability-max-values", default="0.55,0.65")
    parser.add_argument("--max-decimal-odds-values", default="1.50,1.80,2.20")
    parser.add_argument("--max-model-edge-values", default="-0.02,-0.04")
    parser.add_argument("--max-calibration-score-values", default="none")
    parser.add_argument("--max-model-confidence-score-values", default="none")
    parser.add_argument("--max-odds-stability-score-values", default="none")
    parser.add_argument("--candidate-start-index", type=int, default=0)
    parser.add_argument("--candidate-limit", type=int)
    parser.add_argument("--candidate-indices", default="")
    parser.add_argument("--min-excluded-candidate-count", type=int, default=1)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-objective-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarginalLossDriverCandidateGuardrailGridOptions:
    return HistoricalMarginalLossDriverCandidateGuardrailGridOptions(
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
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        competition_groups=_competition_groups_from_args(args),
        probability_min_values=_float_tuple(args.probability_min_values),
        probability_max_values=_float_tuple(args.probability_max_values),
        max_decimal_odds_values=_float_tuple(args.max_decimal_odds_values),
        max_model_edge_values=_float_tuple(args.max_model_edge_values),
        max_calibration_score_values=_optional_float_tuple(
            args.max_calibration_score_values
        ),
        max_model_confidence_score_values=_optional_float_tuple(
            args.max_model_confidence_score_values
        ),
        max_odds_stability_score_values=_optional_float_tuple(
            args.max_odds_stability_score_values
        ),
        candidate_start_index=args.candidate_start_index,
        candidate_limit=args.candidate_limit,
        candidate_indices=_int_tuple(args.candidate_indices),
        min_excluded_candidate_count=args.min_excluded_candidate_count,
        min_final_hit_count_delta=args.min_final_hit_count_delta,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        min_upset_capture_rate_delta=args.min_upset_capture_rate_delta,
        require_objective_improvement=args.require_objective_improvement,
        min_objective_final_hit_rate_delta=args.min_objective_final_hit_rate_delta,
        min_objective_roi_delta=args.min_objective_roi_delta,
        comparison_epsilon=args.comparison_epsilon,
    )


def _competition_groups_from_args(args: Namespace) -> tuple[tuple[str, ...], ...]:
    raw_groups = args.competition_group or [args.competitions]
    groups = tuple(tuple(_csv(raw_group)) for raw_group in raw_groups if _csv(raw_group))
    if not groups:
        raise ValueError("Provide at least one competition group")
    return groups


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in _csv(value))


def _optional_float_tuple(value: str) -> tuple[float | None, ...]:
    parsed: list[float | None] = []
    for item in _csv(value):
        if item.lower() in {"none", "null"}:
            parsed.append(None)
        else:
            parsed.append(float(item))
    return tuple(parsed) or (None,)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_loss_driver_candidate_guardrail_grid:{digest}"


def _parse_merge_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Merge marginal loss-driver candidate guardrail grid reports."
    )
    parser.add_argument("report_paths", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args(argv)


def _merge_warnings(
    reports: Sequence[HistoricalMarginalLossDriverCandidateGuardrailGridReport],
    candidate_indices: Sequence[int],
    candidate_count: int,
) -> list[str]:
    warnings: list[str] = []
    for field_name in ("slice_count", "fixture_count", "prediction_count"):
        values = {getattr(report, field_name) for report in reports}
        if len(values) > 1:
            warnings.append(f"loss_driver_guardrail_grid_merge:inconsistent_{field_name}")
    total_counts = {report.candidate_count for report in reports}
    if len(total_counts) > 1:
        warnings.append("loss_driver_guardrail_grid_merge:inconsistent_candidate_count")
    if _duplicate_candidate_indices(candidate_indices):
        warnings.append("loss_driver_guardrail_grid_merge:duplicate_candidate_indices")
    if _missing_candidate_indices(candidate_indices, candidate_count):
        warnings.append("loss_driver_guardrail_grid_merge:missing_candidate_indices")
    return warnings


def _missing_candidate_indices(
    candidate_indices: Sequence[int],
    candidate_count: int,
) -> list[int]:
    present = set(candidate_indices)
    return [
        candidate_index
        for candidate_index in range(candidate_count)
        if candidate_index not in present
    ]


def _duplicate_candidate_indices(candidate_indices: Sequence[int]) -> list[int]:
    counter: Counter[int] = Counter(candidate_indices)
    return sorted(
        candidate_index for candidate_index, count in counter.items() if count > 1
    )


def _next_candidate_start_index(
    candidate_indices: Sequence[int],
    candidate_count: int,
) -> int | None:
    if not candidate_indices:
        return 0 if candidate_count else None
    next_index = max(candidate_indices) + 1
    return next_index if next_index < candidate_count else None


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    slice_payload = ";".join(
        f"{historical_slice.metadata.slice_id}@{historical_slice.as_of_time_utc.isoformat()}"
        for historical_slice in historical_slices
    )
    payload = dumps({"summary": summary, "slices": slice_payload}, sort_keys=True)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_loss_driver_candidate_guardrail_grid:{digest}"


def _merged_report_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_loss_driver_candidate_guardrail_grid:{digest}"
