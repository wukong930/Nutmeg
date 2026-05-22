from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.replacement_short_odds_shadow_rerank import (
    HistoricalShortOddsShadowCompetitionSummary,
    HistoricalShortOddsShadowProfileSummary,
    HistoricalShortOddsShadowRerankReport,
)

type HistoricalShortOddsCompetitionGateDecision = Literal[
    "final_answer_gate_ready",
    "holdout_watchlist",
    "isolated_rejected",
]


class HistoricalShortOddsCompetitionGateOptions(BaseModel):
    profile_ids: tuple[str, ...] = ("max_short_odds_within_deficit_v1",)
    min_evaluated_item_count: int = Field(default=5, ge=1)
    min_changed_count_vs_model_top: int = Field(default=1, ge=0)
    min_simulated_actual_hit_delta_count_vs_model_top: int = 1
    min_replacement_leg_hit_delta_count_vs_model_top: int = 1
    min_average_profit_loss_delta_vs_model_top: float = 0.0
    min_average_hit_probability_delta_vs_model_top: float = -0.015
    max_harm_count_vs_model_top: int = Field(default=0, ge=0)
    max_report_candidates: int = Field(default=80, ge=1, le=500)


class HistoricalShortOddsCompetitionGateCandidate(BaseModel):
    candidate_key: str
    profile_id: str
    competition_id: str
    decision: HistoricalShortOddsCompetitionGateDecision
    decision_reasons: list[str] = Field(default_factory=list)
    evaluated_item_count: int = Field(ge=0)
    changed_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_delta_count_vs_model_top: int
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_decimal_odds_delta_vs_model_top: float | None = None
    production_recommendation_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsCompetitionGateSet(BaseModel):
    profile_id: str
    decision: HistoricalShortOddsCompetitionGateDecision
    decision_reasons: list[str] = Field(default_factory=list)
    ready_competition_ids: list[str] = Field(default_factory=list)
    isolated_competition_ids: list[str] = Field(default_factory=list)
    evaluated_item_count: int = Field(ge=0)
    changed_count_vs_model_top: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_delta_count_vs_model_top: int
    improvement_count_vs_model_top: int = Field(ge=0)
    harm_count_vs_model_top: int = Field(ge=0)
    selected_actual_best_count: int = Field(ge=0)
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_decimal_odds_delta_vs_model_top: float | None = None
    production_recommendation_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsCompetitionGateReport(BaseModel):
    report_key: str
    status: str
    source_shadow_report_key: str
    profile_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    final_answer_gate_ready_count: int = Field(ge=0)
    holdout_watchlist_count: int = Field(ge=0)
    isolated_rejected_count: int = Field(ge=0)
    ready_competition_ids: list[str] = Field(default_factory=list)
    isolated_competition_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    candidates: list[HistoricalShortOddsCompetitionGateCandidate] = Field(
        default_factory=list
    )
    profile_sets: list[HistoricalShortOddsCompetitionGateSet] = Field(
        default_factory=list
    )
    best_profile_set: HistoricalShortOddsCompetitionGateSet | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_competition_gate_report(
    shadow_report: HistoricalShortOddsShadowRerankReport,
    *,
    options: HistoricalShortOddsCompetitionGateOptions | None = None,
) -> HistoricalShortOddsCompetitionGateReport:
    resolved_options = options or HistoricalShortOddsCompetitionGateOptions()
    warnings = list(shadow_report.warnings)
    profile_summaries = _selected_profile_summaries(
        shadow_report,
        profile_ids=resolved_options.profile_ids,
    )
    missing_profile_ids = sorted(
        set(resolved_options.profile_ids)
        - {profile.profile_id for profile in profile_summaries}
    )
    for profile_id in missing_profile_ids:
        warnings.append(f"short_odds_competition_gate:missing_profile:{profile_id}")

    candidates = [
        _candidate_from_competition_summary(
            profile_summary,
            competition_summary,
            options=resolved_options,
        )
        for profile_summary in profile_summaries
        for competition_summary in profile_summary.competition_summaries
    ]
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            _decision_rank(candidate.decision),
            candidate.simulated_actual_hit_delta_count_vs_model_top,
            candidate.average_profit_loss_delta_vs_model_top or 0.0,
            -candidate.harm_count_vs_model_top,
            candidate.evaluated_item_count,
            candidate.candidate_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_candidates]
    profile_sets = [
        _profile_set_from_candidates(
            profile_summary.profile_id,
            [
                candidate
                for candidate in candidates
                if candidate.profile_id == profile_summary.profile_id
            ],
        )
        for profile_summary in profile_summaries
    ]
    best_profile_set = _best_profile_set(profile_sets)
    ready_competition_ids = sorted(
        {
            candidate.competition_id
            for candidate in candidates
            if candidate.decision == "final_answer_gate_ready"
        }
    )
    isolated_competition_ids = sorted(
        {
            candidate.competition_id
            for candidate in candidates
            if candidate.decision == "isolated_rejected"
        }
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_competition_gate_v3_1",
        "source_shadow_report_key": shadow_report.report_key,
        "source_shadow_production_recommendation_changed": (
            shadow_report.production_recommendation_changed
        ),
        "profile_ids": list(resolved_options.profile_ids),
        "profile_count": len(profile_summaries),
        "candidate_count": len(candidates),
        "ready_competition_ids": ready_competition_ids,
        "isolated_competition_ids": isolated_competition_ids,
        "best_profile_id": (
            best_profile_set.profile_id if best_profile_set is not None else None
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, sorted_candidates, profile_sets)
    return HistoricalShortOddsCompetitionGateReport(
        report_key=report_key,
        status="generated",
        source_shadow_report_key=shadow_report.report_key,
        profile_count=len(profile_summaries),
        candidate_count=len(candidates),
        final_answer_gate_ready_count=sum(
            1 for candidate in candidates if candidate.decision == "final_answer_gate_ready"
        ),
        holdout_watchlist_count=sum(
            1 for candidate in candidates if candidate.decision == "holdout_watchlist"
        ),
        isolated_rejected_count=sum(
            1 for candidate in candidates if candidate.decision == "isolated_rejected"
        ),
        ready_competition_ids=ready_competition_ids,
        isolated_competition_ids=isolated_competition_ids,
        production_recommendation_changed=False,
        candidates=sorted_candidates,
        profile_sets=profile_sets,
        best_profile_set=best_profile_set,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_shadow_rerank_report(
    path: Path,
) -> HistoricalShortOddsShadowRerankReport:
    return HistoricalShortOddsShadowRerankReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    shadow_report = load_historical_short_odds_shadow_rerank_report(
        args.shadow_report
    )
    report = build_historical_short_odds_competition_gate_report(
        shadow_report,
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


def _selected_profile_summaries(
    shadow_report: HistoricalShortOddsShadowRerankReport,
    *,
    profile_ids: Sequence[str],
) -> list[HistoricalShortOddsShadowProfileSummary]:
    if not profile_ids:
        return [
            profile
            for profile in shadow_report.profile_summaries
            if profile.status != "baseline"
        ]
    requested = set(profile_ids)
    return [
        profile
        for profile in shadow_report.profile_summaries
        if profile.profile_id in requested
    ]


def _candidate_from_competition_summary(
    profile_summary: HistoricalShortOddsShadowProfileSummary,
    competition_summary: HistoricalShortOddsShadowCompetitionSummary,
    *,
    options: HistoricalShortOddsCompetitionGateOptions,
) -> HistoricalShortOddsCompetitionGateCandidate:
    decision, reasons = _decision_for_competition(
        competition_summary,
        options=options,
    )
    candidate_key = f"{profile_summary.profile_id}:{competition_summary.competition_id}"
    return HistoricalShortOddsCompetitionGateCandidate(
        candidate_key=candidate_key,
        profile_id=profile_summary.profile_id,
        competition_id=competition_summary.competition_id,
        decision=decision,
        decision_reasons=reasons,
        evaluated_item_count=competition_summary.evaluated_item_count,
        changed_count_vs_model_top=competition_summary.changed_count_vs_model_top,
        simulated_actual_hit_delta_count_vs_model_top=(
            competition_summary.simulated_actual_hit_delta_count_vs_model_top
        ),
        replacement_leg_hit_delta_count_vs_model_top=(
            competition_summary.replacement_leg_hit_delta_count_vs_model_top
        ),
        improvement_count_vs_model_top=(
            competition_summary.improvement_count_vs_model_top
        ),
        harm_count_vs_model_top=competition_summary.harm_count_vs_model_top,
        selected_actual_best_count=competition_summary.selected_actual_best_count,
        average_profit_loss_delta_vs_model_top=(
            competition_summary.average_profit_loss_delta_vs_model_top
        ),
        average_hit_probability_delta_vs_model_top=(
            competition_summary.average_hit_probability_delta_vs_model_top
        ),
        average_decimal_odds_delta_vs_model_top=(
            competition_summary.average_decimal_odds_delta_vs_model_top
        ),
        production_recommendation_changed=False,
        summary_json={
            "calculation_basis": "historical_short_odds_competition_gate_candidate_v3_1",
            "source_profile_status": profile_summary.status,
            "source_profile_status_reasons": profile_summary.status_reasons,
            "production_recommendation_changed": False,
        },
    )


def _decision_for_competition(
    competition_summary: HistoricalShortOddsShadowCompetitionSummary,
    *,
    options: HistoricalShortOddsCompetitionGateOptions,
) -> tuple[HistoricalShortOddsCompetitionGateDecision, list[str]]:
    reasons: list[str] = []
    if competition_summary.evaluated_item_count < options.min_evaluated_item_count:
        reasons.append("sample_size_below_threshold")
    if (
        competition_summary.changed_count_vs_model_top
        < options.min_changed_count_vs_model_top
    ):
        reasons.append("changed_count_below_threshold")
    if (
        competition_summary.simulated_actual_hit_delta_count_vs_model_top
        < options.min_simulated_actual_hit_delta_count_vs_model_top
    ):
        reasons.append("simulated_actual_hit_delta_below_threshold")
    if (
        competition_summary.replacement_leg_hit_delta_count_vs_model_top
        < options.min_replacement_leg_hit_delta_count_vs_model_top
    ):
        reasons.append("replacement_leg_hit_delta_below_threshold")
    average_profit_delta = (
        competition_summary.average_profit_loss_delta_vs_model_top
    )
    if (
        average_profit_delta is None
        or average_profit_delta
        <= options.min_average_profit_loss_delta_vs_model_top
    ):
        reasons.append("average_profit_loss_delta_vs_model_top_below_threshold")
    average_hit_probability_delta = (
        competition_summary.average_hit_probability_delta_vs_model_top
    )
    if (
        average_hit_probability_delta is None
        or average_hit_probability_delta
        < options.min_average_hit_probability_delta_vs_model_top
    ):
        reasons.append("average_hit_probability_delta_vs_model_top_below_threshold")
    if competition_summary.harm_count_vs_model_top > options.max_harm_count_vs_model_top:
        reasons.append("harm_count_vs_model_top_above_threshold")
    if not reasons:
        return "final_answer_gate_ready", []
    if "harm_count_vs_model_top_above_threshold" in reasons:
        return "isolated_rejected", reasons
    if average_profit_delta is not None and average_profit_delta > 0:
        return "holdout_watchlist", reasons
    return "isolated_rejected", reasons


def _profile_set_from_candidates(
    profile_id: str,
    candidates: Sequence[HistoricalShortOddsCompetitionGateCandidate],
) -> HistoricalShortOddsCompetitionGateSet:
    ready_candidates = [
        candidate
        for candidate in candidates
        if candidate.decision == "final_answer_gate_ready"
    ]
    isolated_candidates = [
        candidate for candidate in candidates if candidate.decision == "isolated_rejected"
    ]
    decision, reasons = _decision_for_profile_set(ready_candidates, isolated_candidates)
    evaluated_count = sum(candidate.evaluated_item_count for candidate in ready_candidates)
    changed_count = sum(candidate.changed_count_vs_model_top for candidate in ready_candidates)
    simulated_hit_delta = sum(
        candidate.simulated_actual_hit_delta_count_vs_model_top
        for candidate in ready_candidates
    )
    replacement_leg_hit_delta = sum(
        candidate.replacement_leg_hit_delta_count_vs_model_top
        for candidate in ready_candidates
    )
    improvement_count = sum(
        candidate.improvement_count_vs_model_top for candidate in ready_candidates
    )
    harm_count = sum(candidate.harm_count_vs_model_top for candidate in ready_candidates)
    selected_actual_best_count = sum(
        candidate.selected_actual_best_count for candidate in ready_candidates
    )
    return HistoricalShortOddsCompetitionGateSet(
        profile_id=profile_id,
        decision=decision,
        decision_reasons=reasons,
        ready_competition_ids=sorted(
            candidate.competition_id for candidate in ready_candidates
        ),
        isolated_competition_ids=sorted(
            candidate.competition_id for candidate in isolated_candidates
        ),
        evaluated_item_count=evaluated_count,
        changed_count_vs_model_top=changed_count,
        simulated_actual_hit_delta_count_vs_model_top=simulated_hit_delta,
        replacement_leg_hit_delta_count_vs_model_top=replacement_leg_hit_delta,
        improvement_count_vs_model_top=improvement_count,
        harm_count_vs_model_top=harm_count,
        selected_actual_best_count=selected_actual_best_count,
        average_profit_loss_delta_vs_model_top=_weighted_average(
            (
                candidate.average_profit_loss_delta_vs_model_top,
                candidate.evaluated_item_count,
            )
            for candidate in ready_candidates
        ),
        average_hit_probability_delta_vs_model_top=_weighted_average(
            (
                candidate.average_hit_probability_delta_vs_model_top,
                candidate.evaluated_item_count,
            )
            for candidate in ready_candidates
        ),
        average_decimal_odds_delta_vs_model_top=_weighted_average(
            (
                candidate.average_decimal_odds_delta_vs_model_top,
                candidate.evaluated_item_count,
            )
            for candidate in ready_candidates
        ),
        production_recommendation_changed=False,
        summary_json={
            "calculation_basis": "historical_short_odds_competition_gate_set_v3_1",
            "production_recommendation_changed": False,
        },
    )


def _decision_for_profile_set(
    ready_candidates: Sequence[HistoricalShortOddsCompetitionGateCandidate],
    isolated_candidates: Sequence[HistoricalShortOddsCompetitionGateCandidate],
) -> tuple[HistoricalShortOddsCompetitionGateDecision, list[str]]:
    reasons: list[str] = []
    if not ready_candidates:
        reasons.append("no_ready_competitions")
    if isolated_candidates:
        reasons.append("isolated_competitions_require_separate_guard")
    if ready_candidates:
        return "final_answer_gate_ready", reasons
    return "isolated_rejected", reasons


def _best_profile_set(
    profile_sets: Sequence[HistoricalShortOddsCompetitionGateSet],
) -> HistoricalShortOddsCompetitionGateSet | None:
    ready_sets = [
        profile_set
        for profile_set in profile_sets
        if profile_set.decision == "final_answer_gate_ready"
    ]
    if not ready_sets:
        return None
    return max(
        ready_sets,
        key=lambda profile_set: (
            len(profile_set.ready_competition_ids),
            profile_set.simulated_actual_hit_delta_count_vs_model_top,
            profile_set.average_profit_loss_delta_vs_model_top or 0.0,
            -profile_set.harm_count_vs_model_top,
            profile_set.profile_id,
        ),
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Gate short-odds shadow rerank results by competition."
    )
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--profile-ids",
        type=str,
        default="max_short_odds_within_deficit_v1",
        help="Comma-separated profile ids to gate; empty means all non-baseline.",
    )
    parser.add_argument("--min-evaluated-item-count", type=int, default=5)
    parser.add_argument("--min-changed-count-vs-model-top", type=int, default=1)
    parser.add_argument(
        "--min-simulated-actual-hit-delta-count-vs-model-top",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-replacement-leg-hit-delta-count-vs-model-top",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-average-profit-loss-delta-vs-model-top",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.015,
    )
    parser.add_argument("--max-harm-count-vs-model-top", type=int, default=0)
    parser.add_argument("--max-report-candidates", type=int, default=80)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsCompetitionGateOptions:
    return HistoricalShortOddsCompetitionGateOptions(
        profile_ids=_csv_values(args.profile_ids),
        min_evaluated_item_count=args.min_evaluated_item_count,
        min_changed_count_vs_model_top=args.min_changed_count_vs_model_top,
        min_simulated_actual_hit_delta_count_vs_model_top=(
            args.min_simulated_actual_hit_delta_count_vs_model_top
        ),
        min_replacement_leg_hit_delta_count_vs_model_top=(
            args.min_replacement_leg_hit_delta_count_vs_model_top
        ),
        min_average_profit_loss_delta_vs_model_top=(
            args.min_average_profit_loss_delta_vs_model_top
        ),
        min_average_hit_probability_delta_vs_model_top=(
            args.min_average_hit_probability_delta_vs_model_top
        ),
        max_harm_count_vs_model_top=args.max_harm_count_vs_model_top,
        max_report_candidates=args.max_report_candidates,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _decision_rank(decision: HistoricalShortOddsCompetitionGateDecision) -> int:
    return {
        "final_answer_gate_ready": 3,
        "holdout_watchlist": 2,
        "isolated_rejected": 1,
    }[decision]


def _weighted_average(values: Iterable[tuple[float | None, int]]) -> float | None:
    total_weight = 0
    weighted_sum = 0.0
    for value, weight in values:
        if value is None or weight <= 0:
            continue
        total_weight += weight
        weighted_sum += value * weight
    if total_weight <= 0:
        return None
    return weighted_sum / total_weight


def _report_key(
    summary: dict[str, object],
    candidates: Sequence[HistoricalShortOddsCompetitionGateCandidate],
    profile_sets: Sequence[HistoricalShortOddsCompetitionGateSet],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "candidates": [
                {
                    "candidate_key": candidate.candidate_key,
                    "decision": candidate.decision,
                    "evaluated_item_count": candidate.evaluated_item_count,
                    "harm_count": candidate.harm_count_vs_model_top,
                }
                for candidate in candidates
            ],
            "profile_sets": [
                {
                    "profile_id": profile_set.profile_id,
                    "decision": profile_set.decision,
                    "ready_competition_ids": profile_set.ready_competition_ids,
                    "isolated_competition_ids": profile_set.isolated_competition_ids,
                }
                for profile_set in profile_sets
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_short_odds_competition_gate:{digest}"
