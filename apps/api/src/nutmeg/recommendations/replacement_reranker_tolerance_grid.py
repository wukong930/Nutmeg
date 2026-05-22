from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_reranker_weight_experiment import (
    HistoricalReplacementRerankerProfile,
    HistoricalReplacementRerankerProfileSummary,
    HistoricalReplacementRerankerWeightExperimentOptions,
    build_historical_replacement_reranker_weight_experiment_report,
    default_historical_replacement_reranker_profiles,
)

DEFAULT_HIT_PROBABILITY_TOLERANCE_VALUES = (0.0, -0.005, -0.01, -0.02)


class HistoricalReplacementRerankerToleranceGridOptions(BaseModel):
    hit_probability_delta_thresholds: tuple[float, ...] = Field(
        default=DEFAULT_HIT_PROBABILITY_TOLERANCE_VALUES
    )
    profiles: tuple[HistoricalReplacementRerankerProfile, ...] = Field(
        default_factory=lambda: default_historical_replacement_reranker_profiles()
    )
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_gap: float = 0.0
    min_evaluated_item_count: int = Field(default=30, ge=1)
    min_average_profit_loss_delta_vs_model_top: float = 0.0
    min_simulated_actual_hit_delta_vs_baseline: int = 0
    min_replacement_leg_actual_hit_delta_vs_baseline: int = 0
    max_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_report_items_per_experiment: int = Field(default=120, ge=1, le=500)


class HistoricalReplacementRerankerToleranceGridCandidate(BaseModel):
    candidate_key: str
    hit_probability_delta_threshold: float
    profile_id: str
    status: str
    status_reasons: list[str] = Field(default_factory=list)
    evaluated_item_count: int = Field(ge=0)
    selected_model_top_count: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_count: int = Field(ge=0)
    baseline_simulated_actual_hit_count: int = Field(ge=0)
    simulated_actual_hit_delta_vs_baseline: int
    replacement_leg_actual_hit_count: int = Field(ge=0)
    baseline_replacement_leg_actual_hit_count: int = Field(ge=0)
    replacement_leg_actual_hit_delta_vs_baseline: int
    hit_probability_regression_count: int = Field(ge=0)
    hit_probability_guard_filtered_count: int = Field(ge=0)
    actual_best_capture_rate: float | None = None
    improvement_rate_vs_model_top: float | None = None
    harm_rate_vs_model_top: float | None = None
    simulated_actual_hit_rate: float | None = None
    baseline_simulated_actual_hit_rate: float | None = None
    replacement_leg_actual_hit_rate: float | None = None
    baseline_replacement_leg_actual_hit_rate: float | None = None
    hit_probability_regression_rate: float | None = None
    average_profit_loss_delta: float | None = None
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_risk_score_delta_vs_model_top: float | None = None


class HistoricalReplacementRerankerToleranceGridReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    threshold_count: int = Field(ge=0)
    profile_count: int = Field(ge=0)
    evaluated_candidate_count: int = Field(ge=0)
    profile_candidate_count: int = Field(ge=0)
    watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    baseline_count: int = Field(ge=0)
    best_candidate_key: str | None = None
    candidates: list[HistoricalReplacementRerankerToleranceGridCandidate] = Field(
        default_factory=list
    )
    profile_candidates: list[HistoricalReplacementRerankerToleranceGridCandidate] = (
        Field(default_factory=list)
    )
    watchlist: list[HistoricalReplacementRerankerToleranceGridCandidate] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_reranker_tolerance_grid_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementRerankerToleranceGridOptions | None = None,
) -> HistoricalReplacementRerankerToleranceGridReport:
    resolved_options = options or HistoricalReplacementRerankerToleranceGridOptions()
    thresholds = _unique_thresholds(resolved_options.hit_probability_delta_thresholds)
    profiles = _profiles_with_baseline(resolved_options.profiles)
    warnings = list(audit_report.warnings)
    if not thresholds:
        warnings.append("no_hit_probability_delta_thresholds")

    candidates: list[HistoricalReplacementRerankerToleranceGridCandidate] = []
    for threshold in thresholds:
        experiment_report = build_historical_replacement_reranker_weight_experiment_report(
            audit_report,
            options=HistoricalReplacementRerankerWeightExperimentOptions(
                profiles=profiles,
                min_actual_best_profit_loss_delta=(
                    resolved_options.min_actual_best_profit_loss_delta
                ),
                min_profit_loss_gap=resolved_options.min_profit_loss_gap,
                min_candidate_hit_probability_delta_vs_model_top=threshold,
                min_evaluated_item_count=resolved_options.min_evaluated_item_count,
                max_hit_probability_regression_rate=1.0,
                min_average_profit_loss_delta_vs_model_top=(
                    resolved_options.min_average_profit_loss_delta_vs_model_top
                ),
                max_report_items=resolved_options.max_report_items_per_experiment,
            ),
        )
        baseline_summary = _baseline_summary(experiment_report.profile_summaries)
        if baseline_summary is None:
            warnings.append(f"missing_baseline_summary:{threshold}")
            continue
        for profile_summary in experiment_report.profile_summaries:
            candidates.append(
                _grid_candidate(
                    threshold,
                    profile_summary,
                    baseline_summary=baseline_summary,
                    options=resolved_options,
                )
            )

    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            _status_rank(candidate.status),
            candidate.simulated_actual_hit_delta_vs_baseline,
            candidate.replacement_leg_actual_hit_delta_vs_baseline,
            candidate.average_profit_loss_delta_vs_model_top or 0.0,
            -abs(candidate.hit_probability_delta_threshold),
            candidate.profile_id,
        ),
        reverse=True,
    )
    profile_candidates = [
        candidate for candidate in sorted_candidates if candidate.status == "candidate"
    ]
    watchlist = [
        candidate for candidate in sorted_candidates if candidate.status == "watchlist"
    ]
    best_candidate = profile_candidates[0] if profile_candidates else None
    report_summary: dict[str, object] = {
        "calculation_basis": "historical_replacement_reranker_tolerance_grid_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "thresholds": list(thresholds),
        "profile_ids": [profile.profile_id for profile in profiles],
        "evaluated_candidate_count": len(candidates),
        "profile_candidate_count": len(profile_candidates),
        "watchlist_count": len(watchlist),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(report_summary, sorted_candidates)
    return HistoricalReplacementRerankerToleranceGridReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        threshold_count=len(thresholds),
        profile_count=len(profiles),
        evaluated_candidate_count=len(candidates),
        profile_candidate_count=len(profile_candidates),
        watchlist_count=len(watchlist),
        rejected_count=sum(1 for candidate in candidates if candidate.status == "rejected"),
        baseline_count=sum(1 for candidate in candidates if candidate.status == "baseline"),
        best_candidate_key=best_candidate.candidate_key if best_candidate else None,
        candidates=sorted_candidates,
        profile_candidates=profile_candidates,
        watchlist=watchlist,
        warnings=warnings,
        summary_json={**report_summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_replacement_reranker_tolerance_grid_report(
        audit_report,
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


def _grid_candidate(
    threshold: float,
    summary: HistoricalReplacementRerankerProfileSummary,
    *,
    baseline_summary: HistoricalReplacementRerankerProfileSummary,
    options: HistoricalReplacementRerankerToleranceGridOptions,
) -> HistoricalReplacementRerankerToleranceGridCandidate:
    status, reasons = _candidate_status(
        threshold,
        summary,
        baseline_summary=baseline_summary,
        options=options,
    )
    simulated_hit_delta = (
        summary.simulated_actual_hit_count
        - baseline_summary.simulated_actual_hit_count
    )
    replacement_leg_hit_delta = (
        summary.replacement_leg_actual_hit_count
        - baseline_summary.replacement_leg_actual_hit_count
    )
    return HistoricalReplacementRerankerToleranceGridCandidate(
        candidate_key=f"{summary.profile_id}:hit_probability_delta>={threshold:g}",
        hit_probability_delta_threshold=threshold,
        profile_id=summary.profile_id,
        status=status,
        status_reasons=reasons,
        evaluated_item_count=summary.evaluated_item_count,
        selected_model_top_count=summary.selected_model_top_count,
        selected_actual_best_count=summary.selected_actual_best_count,
        improvement_count_vs_model_top=summary.improvement_count_vs_model_top,
        harm_count_vs_model_top=summary.harm_count_vs_model_top,
        simulated_actual_hit_count=summary.simulated_actual_hit_count,
        baseline_simulated_actual_hit_count=(
            baseline_summary.simulated_actual_hit_count
        ),
        simulated_actual_hit_delta_vs_baseline=simulated_hit_delta,
        replacement_leg_actual_hit_count=summary.replacement_leg_actual_hit_count,
        baseline_replacement_leg_actual_hit_count=(
            baseline_summary.replacement_leg_actual_hit_count
        ),
        replacement_leg_actual_hit_delta_vs_baseline=replacement_leg_hit_delta,
        hit_probability_regression_count=summary.hit_probability_regression_count,
        hit_probability_guard_filtered_count=summary.hit_probability_guard_filtered_count,
        actual_best_capture_rate=summary.actual_best_capture_rate,
        improvement_rate_vs_model_top=summary.improvement_rate_vs_model_top,
        harm_rate_vs_model_top=summary.harm_rate_vs_model_top,
        simulated_actual_hit_rate=summary.simulated_actual_hit_rate,
        baseline_simulated_actual_hit_rate=(
            baseline_summary.simulated_actual_hit_rate
        ),
        replacement_leg_actual_hit_rate=summary.replacement_leg_actual_hit_rate,
        baseline_replacement_leg_actual_hit_rate=(
            baseline_summary.replacement_leg_actual_hit_rate
        ),
        hit_probability_regression_rate=summary.hit_probability_regression_rate,
        average_profit_loss_delta=summary.average_profit_loss_delta,
        average_profit_loss_delta_vs_model_top=(
            summary.average_profit_loss_delta_vs_model_top
        ),
        average_hit_probability_delta_vs_model_top=(
            summary.average_hit_probability_delta_vs_model_top
        ),
        average_risk_score_delta_vs_model_top=(
            summary.average_risk_score_delta_vs_model_top
        ),
    )


def _candidate_status(
    threshold: float,
    summary: HistoricalReplacementRerankerProfileSummary,
    *,
    baseline_summary: HistoricalReplacementRerankerProfileSummary,
    options: HistoricalReplacementRerankerToleranceGridOptions,
) -> tuple[str, list[str]]:
    if summary.status == "baseline":
        return "baseline", ["current_model_top_reference"]
    reasons: list[str] = []
    simulated_hit_delta = (
        summary.simulated_actual_hit_count
        - baseline_summary.simulated_actual_hit_count
    )
    replacement_leg_hit_delta = (
        summary.replacement_leg_actual_hit_count
        - baseline_summary.replacement_leg_actual_hit_count
    )
    if summary.evaluated_item_count < options.min_evaluated_item_count:
        reasons.append("sample_size_below_threshold")
    if simulated_hit_delta < options.min_simulated_actual_hit_delta_vs_baseline:
        reasons.append("simulated_actual_hit_count_regressed")
    if (
        replacement_leg_hit_delta
        < options.min_replacement_leg_actual_hit_delta_vs_baseline
    ):
        reasons.append("replacement_leg_actual_hit_count_regressed")
    if summary.harm_count_vs_model_top > options.max_harm_count_vs_model_top:
        reasons.append("harm_count_vs_model_top_above_threshold")
    if (
        summary.average_profit_loss_delta_vs_model_top is None
        or summary.average_profit_loss_delta_vs_model_top
        <= options.min_average_profit_loss_delta_vs_model_top
    ):
        reasons.append("average_profit_loss_delta_vs_model_top_below_threshold")
    if reasons:
        if (
            summary.average_profit_loss_delta_vs_model_top is not None
            and summary.average_profit_loss_delta_vs_model_top > 0
            and simulated_hit_delta >= 0
        ):
            return "watchlist", reasons
        return "rejected", reasons
    if threshold < 0:
        return "watchlist", ["uses_hit_probability_tolerance"]
    return "candidate", []


def _baseline_summary(
    summaries: Sequence[HistoricalReplacementRerankerProfileSummary],
) -> HistoricalReplacementRerankerProfileSummary | None:
    for summary in summaries:
        if summary.status == "baseline":
            return summary
    return None


def _unique_thresholds(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(sorted({float(value) for value in values}, reverse=True))


def _profiles_with_baseline(
    profiles: Sequence[HistoricalReplacementRerankerProfile],
) -> tuple[HistoricalReplacementRerankerProfile, ...]:
    if any(profile.use_current_model_top for profile in profiles):
        return tuple(profiles)
    baseline = default_historical_replacement_reranker_profiles()[0]
    return (baseline, *tuple(profiles))


def _status_rank(status: str) -> int:
    return {
        "candidate": 4,
        "watchlist": 3,
        "baseline": 2,
        "rejected": 1,
    }.get(status, 0)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run replacement reranker hit-probability tolerance grids."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--hit-probability-delta-thresholds",
        type=str,
        default="0,-0.005,-0.01,-0.02",
        help="Comma-separated per-item hit-probability deltas versus model-top.",
    )
    parser.add_argument(
        "--profile-ids",
        type=str,
        default="",
        help="Comma-separated default profile ids to evaluate; empty means all.",
    )
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-gap", type=float, default=0.0)
    parser.add_argument("--min-evaluated-item-count", type=int, default=30)
    parser.add_argument(
        "--min-average-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-simulated-actual-hit-delta-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--min-replacement-leg-actual-hit-delta-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--max-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-report-items-per-experiment", type=int, default=120)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementRerankerToleranceGridOptions:
    return HistoricalReplacementRerankerToleranceGridOptions(
        hit_probability_delta_thresholds=_parse_float_csv(
            args.hit_probability_delta_thresholds
        ),
        profiles=_selected_profiles(args.profile_ids),
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_gap=args.min_profit_loss_gap,
        min_evaluated_item_count=args.min_evaluated_item_count,
        min_average_profit_loss_delta_vs_model_top=(
            args.min_average_profit_loss_delta_vs_model_top
        ),
        min_simulated_actual_hit_delta_vs_baseline=(
            args.min_simulated_actual_hit_delta_vs_baseline
        ),
        min_replacement_leg_actual_hit_delta_vs_baseline=(
            args.min_replacement_leg_actual_hit_delta_vs_baseline
        ),
        max_harm_count_vs_model_top=args.max_harm_count_vs_model_top,
        max_report_items_per_experiment=args.max_report_items_per_experiment,
    )


def _selected_profiles(
    profile_ids: str,
) -> tuple[HistoricalReplacementRerankerProfile, ...]:
    profiles = default_historical_replacement_reranker_profiles()
    if not profile_ids:
        return profiles
    requested = {profile_id.strip() for profile_id in profile_ids.split(",")}
    requested.discard("")
    selected = tuple(profile for profile in profiles if profile.profile_id in requested)
    missing = requested - {profile.profile_id for profile in selected}
    if missing:
        raise SystemExit(f"Unknown replacement reranker profile ids: {sorted(missing)}")
    return selected


def _parse_float_csv(value: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not values:
        raise SystemExit("At least one hit-probability delta threshold is required.")
    return values


def _report_key(
    summary: dict[str, object],
    candidates: Sequence[HistoricalReplacementRerankerToleranceGridCandidate],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "candidates": [
                {
                    "candidate_key": candidate.candidate_key,
                    "status": candidate.status,
                    "simulated_actual_hit_delta": (
                        candidate.simulated_actual_hit_delta_vs_baseline
                    ),
                    "average_profit_loss_delta_vs_model_top": (
                        candidate.average_profit_loss_delta_vs_model_top
                    ),
                }
                for candidate in candidates
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_reranker_tolerance_grid:{digest}"
