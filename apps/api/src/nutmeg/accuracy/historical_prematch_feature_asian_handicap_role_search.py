from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_poisson_walk_forward import (
    ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS,
    HistoricalPoissonWalkForwardOptions,
    HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
)
from nutmeg.accuracy.historical_prematch_feature_shadow_comparison import (
    HistoricalPrematchFeatureShadowComparisonOptions,
    HistoricalPrematchFeatureShadowComparisonReport,
    _add_poisson_option_args,
    build_historical_prematch_feature_shadow_comparison_report,
)
from nutmeg.accuracy.historical_prematch_feature_shadow_comparison import (
    _options_from_args as _shadow_options_from_args,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPrematchFeatureAsianHandicapRoleSearchStatus = Literal["generated"]
type HistoricalPrematchFeatureAsianHandicapRoleCandidateStatus = Literal[
    "accepted",
    "control_passed",
    "watchlist",
    "rejected",
]

DEFAULT_ASIAN_HANDICAP_ROLE_SEARCH_ID = (
    "prematch-feature-asian-handicap-role-search-v3.2"
)
DEFAULT_BASELINE_LABEL = "1x2_market_movement_only"
DEFAULT_CANDIDATE_LABEL = "1x2_plus_asian_handicap_market_movement"


class HistoricalPrematchFeatureAsianHandicapRoleSearchOptions(BaseModel):
    role_search_id: str = DEFAULT_ASIAN_HANDICAP_ROLE_SEARCH_ID
    baseline_label: str = DEFAULT_BASELINE_LABEL
    candidate_label: str = DEFAULT_CANDIDATE_LABEL
    poisson_options: HistoricalPoissonWalkForwardOptions = Field(
        default_factory=lambda: HistoricalPoissonWalkForwardOptions(
            lambda_method="prematch_feature_adjusted",
            min_prematch_feature_data_quality_score=70.0,
        )
    )
    asian_handicap_movement_weights: tuple[float, ...] = (
        0.0,
        0.05,
        0.10,
        0.20,
        0.35,
        0.50,
    )
    min_asian_handicap_probability_deltas: tuple[float, ...] = (
        0.0,
        0.02,
        0.04,
        0.06,
    )
    asian_handicap_line_movement_weights: tuple[float, ...] = (
        0.0,
        0.02,
        0.05,
        0.10,
    )
    min_asian_handicap_line_deltas: tuple[float, ...] = (
        0.0,
        0.25,
    )
    asian_handicap_line_movement_scale: float = Field(default=2.0, gt=0.0, le=10.0)
    asian_handicap_line_movement_transforms: tuple[
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
        ...,
    ] = ("linear",)
    min_effective_asian_handicap_weight: float = Field(default=0.01, ge=0.0)
    min_validation_count: int = Field(default=1, ge=0)
    max_brier_score_regression: float = Field(default=0.0, ge=0.0)
    max_log_loss_regression: float = Field(default=0.0, ge=0.0)
    max_expected_calibration_error_regression: float = Field(default=0.0, ge=0.0)
    min_hit_rate_delta: float = 0.0


class HistoricalPrematchFeatureAsianHandicapRoleCandidate(BaseModel):
    rank: int = Field(default=1, ge=1)
    candidate_id: str
    status: HistoricalPrematchFeatureAsianHandicapRoleCandidateStatus
    comparison_report_key: str
    baseline_report_key: str
    candidate_report_key: str
    asian_handicap_movement_weight: float = Field(ge=0.0)
    min_asian_handicap_probability_delta: float = Field(ge=0.0)
    asian_handicap_line_movement_weight: float = Field(ge=0.0)
    min_asian_handicap_line_delta: float = Field(ge=0.0)
    asian_handicap_line_movement_scale: float = Field(gt=0.0)
    asian_handicap_line_movement_transform: (
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform
    ) = "linear"
    effective_asian_handicap_role: bool
    baseline_validation_count: int = Field(ge=0)
    candidate_validation_count: int = Field(ge=0)
    candidate_asian_handicap_feature_coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    passed_non_regression_gate: bool
    ranking_score: float | None = None
    metric_deltas_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAsianHandicapRoleSearchReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapRoleSearchStatus
    role_search_id: str
    baseline_label: str
    candidate_label: str
    baseline_slice_count: int = Field(ge=0)
    candidate_slice_count: int = Field(ge=0)
    baseline_fixture_count: int = Field(ge=0)
    candidate_fixture_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    accepted_nonzero_candidate_count: int = Field(ge=0)
    control_passed_candidate_count: int = Field(ge=0)
    watchlist_candidate_count: int = Field(ge=0)
    best_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate
    best_accepted_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None = None
    best_effective_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None = None
    best_control_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None = None
    candidates: list[HistoricalPrematchFeatureAsianHandicapRoleCandidate] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def load_historical_prematch_feature_asian_handicap_role_search_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    return HistoricalPrematchFeatureAsianHandicapRoleSearchReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_prematch_feature_asian_handicap_role_search_report(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    candidate_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAsianHandicapRoleSearchOptions | None = None,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchReport:
    resolved_options = options or HistoricalPrematchFeatureAsianHandicapRoleSearchOptions()
    candidates = [
        _candidate_from_report(
            build_historical_prematch_feature_shadow_comparison_report(
                baseline_slices,
                candidate_slices,
                options=_comparison_options(
                    resolved_options,
                    candidate_index=candidate_index,
                    asian_handicap_movement_weight=asian_handicap_movement_weight,
                    min_asian_handicap_probability_delta=(
                        min_asian_handicap_probability_delta
                    ),
                    asian_handicap_line_movement_weight=(
                        asian_handicap_line_movement_weight
                    ),
                    min_asian_handicap_line_delta=min_asian_handicap_line_delta,
                    asian_handicap_line_movement_transform=(
                        asian_handicap_line_movement_transform
                    ),
                ),
            ),
            role_options=resolved_options,
            candidate_index=candidate_index,
            asian_handicap_movement_weight=asian_handicap_movement_weight,
            min_asian_handicap_probability_delta=min_asian_handicap_probability_delta,
            asian_handicap_line_movement_weight=asian_handicap_line_movement_weight,
            min_asian_handicap_line_delta=min_asian_handicap_line_delta,
            asian_handicap_line_movement_transform=(
                asian_handicap_line_movement_transform
            ),
        )
        for candidate_index, (
            asian_handicap_movement_weight,
            min_asian_handicap_probability_delta,
            asian_handicap_line_movement_weight,
            min_asian_handicap_line_delta,
            asian_handicap_line_movement_transform,
        ) in enumerate(_role_grid(resolved_options), start=1)
    ]
    if not candidates:
        raise ValueError("Asian-handicap role search produced no candidates")

    ranked_candidates = [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(
            sorted(candidates, key=_candidate_sort_key),
            start=1,
        )
    ]
    accepted_candidates = [
        candidate for candidate in ranked_candidates if candidate.status == "accepted"
    ]
    control_candidates = [
        candidate
        for candidate in ranked_candidates
        if candidate.status == "control_passed"
    ]
    effective_candidates = [
        candidate
        for candidate in ranked_candidates
        if candidate.effective_asian_handicap_role
    ]
    watchlist_count = sum(
        1 for candidate in ranked_candidates if candidate.status == "watchlist"
    )
    report_key = _report_key(
        baseline_slices,
        candidate_slices,
        options=resolved_options,
        candidates=ranked_candidates,
    )
    warnings = _report_warnings(
        ranked_candidates,
        accepted_nonzero_candidate_count=len(accepted_candidates),
        control_passed_candidate_count=len(control_candidates),
    )
    best_candidate = ranked_candidates[0]
    best_accepted_candidate = accepted_candidates[0] if accepted_candidates else None
    best_effective_candidate = effective_candidates[0] if effective_candidates else None
    best_control_candidate = control_candidates[0] if control_candidates else None
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_role_search_v3_2"
        ),
        "report_key": report_key,
        "role_search_id": resolved_options.role_search_id,
        "shadow_only": True,
        "baseline_label": resolved_options.baseline_label,
        "candidate_label": resolved_options.candidate_label,
        "poisson_options": resolved_options.poisson_options.model_dump(mode="json"),
        "asian_handicap_movement_weights": list(
            resolved_options.asian_handicap_movement_weights
        ),
        "min_asian_handicap_probability_deltas": list(
            resolved_options.min_asian_handicap_probability_deltas
        ),
        "asian_handicap_line_movement_weights": list(
            resolved_options.asian_handicap_line_movement_weights
        ),
        "min_asian_handicap_line_deltas": list(
            resolved_options.min_asian_handicap_line_deltas
        ),
        "asian_handicap_line_movement_scale": (
            resolved_options.asian_handicap_line_movement_scale
        ),
        "asian_handicap_line_movement_transforms": list(
            resolved_options.asian_handicap_line_movement_transforms
        ),
        "candidate_count": len(ranked_candidates),
        "accepted_nonzero_candidate_count": len(accepted_candidates),
        "control_passed_candidate_count": len(control_candidates),
        "watchlist_candidate_count": watchlist_count,
        "best_candidate_id": best_candidate.candidate_id,
        "best_candidate_status": best_candidate.status,
        "best_candidate_deltas": best_candidate.metric_deltas_json,
        "best_accepted_candidate_id": (
            best_accepted_candidate.candidate_id if best_accepted_candidate else None
        ),
        "best_effective_candidate_id": (
            best_effective_candidate.candidate_id if best_effective_candidate else None
        ),
        "best_control_candidate_id": (
            best_control_candidate.candidate_id if best_control_candidate else None
        ),
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureAsianHandicapRoleSearchReport(
        report_key=report_key,
        status="generated",
        role_search_id=resolved_options.role_search_id,
        baseline_label=resolved_options.baseline_label,
        candidate_label=resolved_options.candidate_label,
        baseline_slice_count=len(baseline_slices),
        candidate_slice_count=len(candidate_slices),
        baseline_fixture_count=sum(len(item.fixtures) for item in baseline_slices),
        candidate_fixture_count=sum(len(item.fixtures) for item in candidate_slices),
        candidate_count=len(ranked_candidates),
        accepted_nonzero_candidate_count=len(accepted_candidates),
        control_passed_candidate_count=len(control_candidates),
        watchlist_candidate_count=watchlist_count,
        best_candidate=best_candidate,
        best_accepted_candidate=best_accepted_candidate,
        best_effective_candidate=best_effective_candidate,
        best_control_candidate=best_control_candidate,
        candidates=ranked_candidates,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    baseline_loaded = _historical_slices_from_args(
        slice_paths=args.baseline_slice_paths,
        suite_manifest=args.baseline_suite_manifest,
        include_disabled=args.include_disabled,
    )
    candidate_loaded = _historical_slices_from_args(
        slice_paths=args.candidate_slice_paths,
        suite_manifest=args.candidate_suite_manifest,
        include_disabled=args.include_disabled,
    )
    report = build_historical_prematch_feature_asian_handicap_role_search_report(
        baseline_loaded.slices,
        candidate_loaded.slices,
        options=_options_from_args(args),
    )
    if baseline_loaded.manifest_result is not None:
        report.summary_json["baseline_suite_manifest"] = _manifest_summary(
            baseline_loaded.manifest_result
        )
    if candidate_loaded.manifest_result is not None:
        report.summary_json["candidate_suite_manifest"] = _manifest_summary(
            candidate_loaded.manifest_result
        )
    if baseline_loaded.warnings:
        report.warnings.extend(
            f"baseline:{warning}" for warning in baseline_loaded.warnings
        )
        report.summary_json["baseline_manifest_warnings"] = baseline_loaded.warnings
    if candidate_loaded.warnings:
        report.warnings.extend(
            f"candidate:{warning}" for warning in candidate_loaded.warnings
        )
        report.summary_json["candidate_manifest_warnings"] = candidate_loaded.warnings
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


def _comparison_options(
    options: HistoricalPrematchFeatureAsianHandicapRoleSearchOptions,
    *,
    candidate_index: int,
    asian_handicap_movement_weight: float,
    min_asian_handicap_probability_delta: float,
    asian_handicap_line_movement_weight: float,
    min_asian_handicap_line_delta: float,
    asian_handicap_line_movement_transform: (
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform
    ),
) -> HistoricalPrematchFeatureShadowComparisonOptions:
    candidate_suffix = (
        f"ah_weight_{_weight_key(asian_handicap_movement_weight)}"
        f"_min_delta_{_weight_key(min_asian_handicap_probability_delta)}"
        f"_line_weight_{_weight_key(asian_handicap_line_movement_weight)}"
        f"_min_line_{_weight_key(min_asian_handicap_line_delta)}"
        f"_line_transform_{asian_handicap_line_movement_transform}"
    )
    return HistoricalPrematchFeatureShadowComparisonOptions(
        comparison_id=f"{options.role_search_id}:{candidate_suffix}",
        baseline_label=options.baseline_label,
        candidate_label=f"{options.candidate_label}:{candidate_suffix}",
        min_validation_count=options.min_validation_count,
        max_brier_score_regression=options.max_brier_score_regression,
        max_log_loss_regression=options.max_log_loss_regression,
        max_expected_calibration_error_regression=(
            options.max_expected_calibration_error_regression
        ),
        min_hit_rate_delta=options.min_hit_rate_delta,
        poisson_options=options.poisson_options.model_copy(
            update={
                "prematch_feature_asian_handicap_movement_weight": (
                    asian_handicap_movement_weight
                ),
                "prematch_feature_min_asian_handicap_probability_delta": (
                    min_asian_handicap_probability_delta
                ),
                "prematch_feature_asian_handicap_line_movement_weight": (
                    asian_handicap_line_movement_weight
                ),
                "prematch_feature_min_asian_handicap_line_delta": (
                    min_asian_handicap_line_delta
                ),
                "prematch_feature_asian_handicap_line_movement_scale": (
                    options.asian_handicap_line_movement_scale
                ),
                "prematch_feature_asian_handicap_line_movement_transform": (
                    asian_handicap_line_movement_transform
                ),
            }
        ),
    )


def _candidate_from_report(
    report: HistoricalPrematchFeatureShadowComparisonReport,
    *,
    role_options: HistoricalPrematchFeatureAsianHandicapRoleSearchOptions,
    candidate_index: int,
    asian_handicap_movement_weight: float,
    min_asian_handicap_probability_delta: float,
    asian_handicap_line_movement_weight: float,
    min_asian_handicap_line_delta: float,
    asian_handicap_line_movement_transform: (
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform
    ),
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate:
    effective_role = (
        asian_handicap_movement_weight
        >= role_options.min_effective_asian_handicap_weight
        or asian_handicap_line_movement_weight
        >= role_options.min_effective_asian_handicap_weight
    )
    status = _candidate_status(
        report,
        effective_role=effective_role,
    )
    ranking_score = _ranking_score(report.metric_deltas_json)
    candidate_id = (
        f"{role_options.role_search_id}:candidate_{candidate_index:04d}:"
        f"ah_weight_{_weight_key(asian_handicap_movement_weight)}:"
        f"min_delta_{_weight_key(min_asian_handicap_probability_delta)}"
        f":line_weight_{_weight_key(asian_handicap_line_movement_weight)}"
        f":min_line_{_weight_key(min_asian_handicap_line_delta)}"
        f":line_transform_{asian_handicap_line_movement_transform}"
    )
    summary: dict[str, object] = {
        "candidate_id": candidate_id,
        "status": status,
        "comparison_report_key": report.report_key,
        "passed_non_regression_gate": report.passed_non_regression_gate,
        "ranking_score": ranking_score,
        "effective_asian_handicap_role": effective_role,
        "asian_handicap_movement_weight": asian_handicap_movement_weight,
        "min_asian_handicap_probability_delta": min_asian_handicap_probability_delta,
        "asian_handicap_line_movement_weight": asian_handicap_line_movement_weight,
        "min_asian_handicap_line_delta": min_asian_handicap_line_delta,
        "asian_handicap_line_movement_scale": (
            role_options.asian_handicap_line_movement_scale
        ),
        "asian_handicap_line_movement_transform": (
            asian_handicap_line_movement_transform
        ),
        "baseline_validation_count": report.baseline_validation_count,
        "candidate_validation_count": report.candidate_validation_count,
        "candidate_asian_handicap_feature_coverage": (
            report.candidate_asian_handicap_feature_coverage
        ),
        "metric_deltas_json": report.metric_deltas_json,
        "warnings": report.warnings,
    }
    return HistoricalPrematchFeatureAsianHandicapRoleCandidate(
        candidate_id=candidate_id,
        status=status,
        comparison_report_key=report.report_key,
        baseline_report_key=report.baseline_report_key,
        candidate_report_key=report.candidate_report_key,
        asian_handicap_movement_weight=asian_handicap_movement_weight,
        min_asian_handicap_probability_delta=min_asian_handicap_probability_delta,
        asian_handicap_line_movement_weight=asian_handicap_line_movement_weight,
        min_asian_handicap_line_delta=min_asian_handicap_line_delta,
        asian_handicap_line_movement_scale=(
            role_options.asian_handicap_line_movement_scale
        ),
        asian_handicap_line_movement_transform=asian_handicap_line_movement_transform,
        effective_asian_handicap_role=effective_role,
        baseline_validation_count=report.baseline_validation_count,
        candidate_validation_count=report.candidate_validation_count,
        candidate_asian_handicap_feature_coverage=(
            report.candidate_asian_handicap_feature_coverage
        ),
        passed_non_regression_gate=report.passed_non_regression_gate,
        ranking_score=ranking_score,
        metric_deltas_json=report.metric_deltas_json,
        warnings=report.warnings,
        summary_json=summary,
    )


def _candidate_status(
    report: HistoricalPrematchFeatureShadowComparisonReport,
    *,
    effective_role: bool,
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidateStatus:
    if report.passed_non_regression_gate and effective_role:
        return "accepted"
    if report.passed_non_regression_gate:
        return "control_passed"
    if effective_role and _watchlist_candidate(report.metric_deltas_json):
        return "watchlist"
    return "rejected"


def _watchlist_candidate(metric_deltas_json: Mapping[str, object]) -> bool:
    brier_delta = _metric_delta(metric_deltas_json, "brier_score")
    log_loss_delta = _metric_delta(metric_deltas_json, "log_loss")
    hit_rate_delta = _metric_delta(metric_deltas_json, "hit_rate")
    calibration_delta = _metric_delta(metric_deltas_json, "expected_calibration_error")
    average_actual_probability_delta = _metric_delta(
        metric_deltas_json,
        "average_actual_probability",
    )
    improvement_count = sum(
        [
            brier_delta is not None and brier_delta <= 0,
            log_loss_delta is not None and log_loss_delta <= 0,
            hit_rate_delta is not None and hit_rate_delta >= 0,
            calibration_delta is not None and calibration_delta <= 0,
            average_actual_probability_delta is not None
            and average_actual_probability_delta >= 0,
        ]
    )
    return improvement_count >= 2


def _ranking_score(metric_deltas_json: Mapping[str, object]) -> float | None:
    brier_delta = _metric_delta(metric_deltas_json, "brier_score")
    log_loss_delta = _metric_delta(metric_deltas_json, "log_loss")
    hit_rate_delta = _metric_delta(metric_deltas_json, "hit_rate")
    calibration_delta = _metric_delta(metric_deltas_json, "expected_calibration_error")
    average_actual_probability_delta = _metric_delta(
        metric_deltas_json,
        "average_actual_probability",
    )
    if brier_delta is None or log_loss_delta is None or hit_rate_delta is None:
        return None
    return (
        brier_delta
        + 0.25 * log_loss_delta
        + 0.50 * (calibration_delta or 0.0)
        - 0.10 * hit_rate_delta
        - 0.05 * (average_actual_probability_delta or 0.0)
    )


def _candidate_sort_key(
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate,
) -> tuple[int, float, float, float, float, float]:
    status_order = {
        "accepted": 0,
        "control_passed": 1,
        "watchlist": 2,
        "rejected": 3,
    }
    return (
        status_order[candidate.status],
        _none_last(candidate.ranking_score),
        _none_last(_metric_delta(candidate.metric_deltas_json, "brier_score")),
        _none_last(_metric_delta(candidate.metric_deltas_json, "log_loss")),
        _none_last(
            _metric_delta(candidate.metric_deltas_json, "expected_calibration_error")
        ),
        -_none_first(_metric_delta(candidate.metric_deltas_json, "hit_rate")),
    )


def _role_grid(
    options: HistoricalPrematchFeatureAsianHandicapRoleSearchOptions,
) -> list[
    tuple[
        float,
        float,
        float,
        float,
        HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
    ]
]:
    candidates: list[
        tuple[
            float,
            float,
            float,
            float,
            HistoricalPrematchFeatureAsianHandicapLineMovementTransform,
        ]
    ] = []
    seen_payloads: set[str] = set()
    for weight, min_delta, line_weight, min_line_delta, line_transform in product(
        options.asian_handicap_movement_weights,
        options.min_asian_handicap_probability_deltas,
        options.asian_handicap_line_movement_weights,
        options.min_asian_handicap_line_deltas,
        options.asian_handicap_line_movement_transforms,
    ):
        payload = dumps(
            [weight, min_delta, line_weight, min_line_delta, line_transform],
            sort_keys=True,
        )
        if payload in seen_payloads:
            continue
        seen_payloads.add(payload)
        candidates.append((weight, min_delta, line_weight, min_line_delta, line_transform))
    return candidates


def _report_warnings(
    candidates: Sequence[HistoricalPrematchFeatureAsianHandicapRoleCandidate],
    *,
    accepted_nonzero_candidate_count: int,
    control_passed_candidate_count: int,
) -> list[str]:
    warnings: list[str] = []
    if accepted_nonzero_candidate_count == 0:
        warnings.append(
            "prematch_feature_asian_handicap_role_search:no_accepted_nonzero_candidate"
        )
    if control_passed_candidate_count > 0 and accepted_nonzero_candidate_count == 0:
        warnings.append(
            "prematch_feature_asian_handicap_role_search:control_only_passed"
        )
    if any(candidate.candidate_validation_count == 0 for candidate in candidates):
        warnings.append(
            "prematch_feature_asian_handicap_role_search:no_validation_candidate"
        )
    if any(
        "prematch_feature_shadow_comparison:no_asian_handicap_features"
        in candidate.warnings
        for candidate in candidates
    ):
        warnings.append(
            "prematch_feature_asian_handicap_role_search:no_candidate_handicap_features"
        )
    return warnings


def _metric_delta(metric_deltas_json: Mapping[str, object], metric_name: str) -> float | None:
    metric_json = metric_deltas_json.get(metric_name)
    if not isinstance(metric_json, Mapping):
        return None
    value = metric_json.get("delta")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a shadow-only role search for Asian-handicap movement inside "
            "pre-match Poisson lambda adjustment."
        )
    )
    parser.add_argument("--baseline-suite-manifest", type=Path)
    parser.add_argument("--candidate-suite-manifest", type=Path)
    parser.add_argument(
        "--baseline-slice-path",
        dest="baseline_slice_paths",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument(
        "--candidate-slice-path",
        dest="candidate_slice_paths",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--role-search-id", default=DEFAULT_ASIAN_HANDICAP_ROLE_SEARCH_ID)
    parser.add_argument("--baseline-label", default=DEFAULT_BASELINE_LABEL)
    parser.add_argument("--candidate-label", default=DEFAULT_CANDIDATE_LABEL)
    parser.add_argument(
        "--asian-handicap-movement-weights",
        type=_float_tuple,
        default=(0.0, 0.05, 0.10, 0.20, 0.35, 0.50),
    )
    parser.add_argument(
        "--min-asian-handicap-probability-deltas",
        type=_float_tuple,
        default=(0.0, 0.02, 0.04, 0.06),
    )
    parser.add_argument(
        "--asian-handicap-line-movement-weights",
        type=_float_tuple,
        default=(0.0, 0.02, 0.05, 0.10),
    )
    parser.add_argument(
        "--min-asian-handicap-line-deltas",
        type=_float_tuple,
        default=(0.0, 0.25),
    )
    parser.add_argument("--asian-handicap-line-movement-scale", type=float, default=2.0)
    parser.add_argument(
        "--asian-handicap-line-movement-transforms",
        type=_line_transform_tuple,
        default=("linear",),
    )
    parser.add_argument("--min-effective-asian-handicap-weight", type=float, default=0.01)
    parser.add_argument("--min-validation-count", type=int, default=1)
    parser.add_argument("--max-brier-score-regression", type=float, default=0.0)
    parser.add_argument("--max-log-loss-regression", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-regression",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    _add_poisson_option_args(parser)
    args = parser.parse_args(argv)
    if not args.baseline_slice_paths and args.baseline_suite_manifest is None:
        parser.error("provide --baseline-slice-path or --baseline-suite-manifest")
    if not args.candidate_slice_paths and args.candidate_suite_manifest is None:
        parser.error("provide --candidate-slice-path or --candidate-suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapRoleSearchOptions:
    args.comparison_id = args.role_search_id
    shadow_options = _shadow_options_from_args(args)
    return HistoricalPrematchFeatureAsianHandicapRoleSearchOptions(
        role_search_id=args.role_search_id,
        baseline_label=args.baseline_label,
        candidate_label=args.candidate_label,
        poisson_options=shadow_options.poisson_options,
        asian_handicap_movement_weights=args.asian_handicap_movement_weights,
        min_asian_handicap_probability_deltas=(
            args.min_asian_handicap_probability_deltas
        ),
        asian_handicap_line_movement_weights=args.asian_handicap_line_movement_weights,
        min_asian_handicap_line_deltas=args.min_asian_handicap_line_deltas,
        asian_handicap_line_movement_scale=args.asian_handicap_line_movement_scale,
        asian_handicap_line_movement_transforms=(
            args.asian_handicap_line_movement_transforms
        ),
        min_effective_asian_handicap_weight=args.min_effective_asian_handicap_weight,
        min_validation_count=args.min_validation_count,
        max_brier_score_regression=args.max_brier_score_regression,
        max_log_loss_regression=args.max_log_loss_regression,
        max_expected_calibration_error_regression=(
            args.max_expected_calibration_error_regression
        ),
        min_hit_rate_delta=args.min_hit_rate_delta,
    )


def _historical_slices_from_args(
    *,
    slice_paths: Sequence[Path],
    suite_manifest: Path | None,
    include_disabled: bool,
) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            suite_manifest,
            include_disabled=include_disabled,
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
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _report_key(
    baseline_slices: Sequence[HistoricalRecommendationSlice],
    candidate_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAsianHandicapRoleSearchOptions,
    candidates: Sequence[HistoricalPrematchFeatureAsianHandicapRoleCandidate],
) -> str:
    payload = {
        "role_search_id": options.role_search_id,
        "baseline_label": options.baseline_label,
        "candidate_label": options.candidate_label,
        "baseline_slice_ids": [item.metadata.slice_id for item in baseline_slices],
        "candidate_slice_ids": [item.metadata.slice_id for item in candidate_slices],
        "baseline_as_of_times": [
            item.as_of_time_utc.isoformat() for item in baseline_slices
        ],
        "candidate_as_of_times": [
            item.as_of_time_utc.isoformat() for item in candidate_slices
        ],
        "candidate_report_keys": [
            candidate.comparison_report_key for candidate in candidates
        ],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"prematch_feature_asian_handicap_role_search:{digest}"


def _float_tuple(value: str) -> tuple[float, ...]:
    parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    if not parsed:
        raise ValueError("expected at least one comma-separated float")
    return parsed


def _line_transform_tuple(
    value: str,
) -> tuple[HistoricalPrematchFeatureAsianHandicapLineMovementTransform, ...]:
    parsed: list[HistoricalPrematchFeatureAsianHandicapLineMovementTransform] = []
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        if candidate not in ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS:
            allowed = ", ".join(ASIAN_HANDICAP_LINE_MOVEMENT_TRANSFORMS)
            raise ValueError(f"unsupported line transform {candidate!r}; use {allowed}")
        parsed.append(candidate)
    if not parsed:
        raise ValueError("expected at least one comma-separated line transform")
    return tuple(parsed)


def _weight_key(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", "p") or "0"


def _none_last(value: float | None) -> float:
    return 1_000_000_000.0 if value is None else value


def _none_first(value: float | None) -> float:
    return -1_000_000_000.0 if value is None else value
