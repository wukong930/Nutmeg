from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
)
from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateOptions,
    HistoricalShortOddsFinalAnswerGateReport,
    HistoricalShortOddsFinalAnswerSelectionRule,
    build_historical_short_odds_final_answer_gate_report,
    load_historical_short_odds_competition_gate_report,
)
from nutmeg.recommendations.replacement_short_odds_shadow_rerank import (
    HistoricalShortOddsShadowSelectionRule,
)

type HistoricalReplacementProbabilityPreservingGridStatus = Literal[
    "accepted_candidate_found",
    "shadow_watchlist_candidates",
    "no_candidate",
]
type HistoricalReplacementProbabilityPreservingGridCandidateStatus = Literal[
    "accepted",
    "shadow_watchlist",
    "rejected",
]


class HistoricalReplacementProbabilityPreservingGridOptions(BaseModel):
    profile_id: str = "max_model_edge_within_deficit_v1"
    ready_competition_ids: tuple[str, ...] = ()
    selection_rules: tuple[HistoricalShortOddsFinalAnswerSelectionRule, ...] = (
        "highest_candidate_hit_probability",
    )
    shadow_selection_rules: tuple[HistoricalShortOddsShadowSelectionRule, ...] = (
        "max_model_edge_within_deficit",
        "nearest_model_top_probability",
        "probability_preserving_model_edge",
    )
    min_replacement_probability_values: tuple[float, ...] = (0.35, 0.40, 0.45, 0.50)
    min_replacement_decimal_odds: float | None = Field(default=1.75, gt=1.0)
    max_replacement_decimal_odds_values: tuple[float, ...] = (2.30, 2.10, 1.95)
    min_candidate_hit_probability_delta_vs_model_top_values: tuple[float, ...] = (
        -1.0,
        -0.08,
        -0.05,
        -0.03,
    )
    max_candidate_hit_probability_delta_vs_model_top: float = -0.02
    min_decimal_odds_delta_vs_model_top: float = 0.0
    min_item_hit_probability_delta_vs_original_values: tuple[float, ...] = (
        -0.05,
        -0.03,
        -0.02,
        -0.01,
        0.0,
    )
    min_changed_final_answer_count: int = Field(default=1, ge=1)
    min_final_answer_hit_delta_count_vs_original: int = 0
    min_profit_loss_delta_vs_original: float = 0.0
    min_average_hit_probability_delta_vs_original: float = -0.02
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    exclude_original_hit_harm: bool = True
    max_candidate_count: int = Field(default=500, ge=1, le=5000)
    max_report_candidates: int = Field(default=120, ge=1, le=1000)


class HistoricalReplacementProbabilityPreservingGridCandidate(BaseModel):
    candidate_key: str
    status: HistoricalReplacementProbabilityPreservingGridCandidateStatus
    accepted: bool
    final_answer_gate_report_key: str
    final_answer_gate_decision: str
    final_answer_gate_decision_reasons: list[str] = Field(default_factory=list)
    profile_id: str
    ready_competition_ids: list[str] = Field(default_factory=list)
    selection_rule: HistoricalShortOddsFinalAnswerSelectionRule
    shadow_selection_rule: HistoricalShortOddsShadowSelectionRule
    min_replacement_probability: float
    min_replacement_decimal_odds: float | None = None
    max_replacement_decimal_odds: float
    min_candidate_hit_probability_delta_vs_model_top: float
    max_candidate_hit_probability_delta_vs_model_top: float
    min_decimal_odds_delta_vs_model_top: float
    min_item_hit_probability_delta_vs_original: float
    exclude_original_hit_harm: bool
    candidate_replacement_option_count: int = Field(ge=0)
    original_safe_replacement_option_count: int = Field(ge=0)
    original_safe_excluded_count: int = Field(ge=0)
    original_safe_exclusion_counts_json: dict[str, int] = Field(default_factory=dict)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_delta_count_vs_original: int
    profit_loss_delta_vs_original: float
    harm_count_vs_original: int = Field(ge=0)
    expected_hit_probability_regression_count_vs_original: int = Field(ge=0)
    average_profit_loss_delta_vs_original: float | None = None
    average_hit_probability_delta_vs_original: float | None = None
    production_recommendation_changed: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementProbabilityPreservingGridReport(BaseModel):
    report_key: str
    status: HistoricalReplacementProbabilityPreservingGridStatus
    accepted_candidate_found: bool
    source_audit_report_key: str
    source_competition_gate_report_key: str
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    shadow_watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    candidate_limit_reached: bool = False
    best_candidate_key: str | None = None
    best_candidate: HistoricalReplacementProbabilityPreservingGridCandidate | None = None
    candidates: list[HistoricalReplacementProbabilityPreservingGridCandidate] = Field(
        default_factory=list
    )
    production_recommendation_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_probability_preserving_grid_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    *,
    options: HistoricalReplacementProbabilityPreservingGridOptions | None = None,
) -> HistoricalReplacementProbabilityPreservingGridReport:
    resolved_options = options or HistoricalReplacementProbabilityPreservingGridOptions()
    warnings = [*audit_report.warnings, *competition_gate_report.warnings]
    candidates: list[HistoricalReplacementProbabilityPreservingGridCandidate] = []
    candidate_limit_reached = False
    for grid in _grid_parameters(resolved_options):
        if len(candidates) >= resolved_options.max_candidate_count:
            candidate_limit_reached = True
            warnings.append("replacement_probability_preserving_grid:candidate_limit_reached")
            break
        gate_report = build_historical_short_odds_final_answer_gate_report(
            audit_report,
            competition_gate_report,
            options=_gate_options(resolved_options, grid),
        )
        candidates.append(_candidate(gate_report, grid=grid))

    sorted_candidates = sorted(candidates, key=_candidate_sort_key, reverse=True)
    accepted_count = sum(1 for candidate in candidates if candidate.accepted)
    watchlist_count = sum(
        1 for candidate in candidates if candidate.status == "shadow_watchlist"
    )
    if accepted_count > 0:
        status: HistoricalReplacementProbabilityPreservingGridStatus = (
            "accepted_candidate_found"
        )
    elif watchlist_count > 0:
        status = "shadow_watchlist_candidates"
    else:
        status = "no_candidate"
    report_candidates = sorted_candidates[: resolved_options.max_report_candidates]
    best_candidate = report_candidates[0] if report_candidates else None
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_grid_v3_1"
        ),
        "source_audit_report_key": audit_report.report_key,
        "source_competition_gate_report_key": competition_gate_report.report_key,
        "candidate_count": len(candidates),
        "accepted_count": accepted_count,
        "shadow_watchlist_count": watchlist_count,
        "rejected_count": sum(
            1 for candidate in candidates if candidate.status == "rejected"
        ),
        "candidate_limit_reached": candidate_limit_reached,
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, report_candidates)
    return HistoricalReplacementProbabilityPreservingGridReport(
        report_key=report_key,
        status=status,
        accepted_candidate_found=accepted_count > 0,
        source_audit_report_key=audit_report.report_key,
        source_competition_gate_report_key=competition_gate_report.report_key,
        candidate_count=len(candidates),
        accepted_count=accepted_count,
        shadow_watchlist_count=watchlist_count,
        rejected_count=sum(
            1 for candidate in candidates if candidate.status == "rejected"
        ),
        candidate_limit_reached=candidate_limit_reached,
        best_candidate_key=(
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        best_candidate=best_candidate,
        candidates=report_candidates,
        production_recommendation_changed=False,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_replacement_probability_preserving_grid_report(
    path: Path | str,
) -> HistoricalReplacementProbabilityPreservingGridReport:
    return HistoricalReplacementProbabilityPreservingGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_probability_preserving_grid_report(
        load_historical_candidate_marginal_audit_report(args.audit_report),
        load_historical_short_odds_competition_gate_report(args.competition_gate_report),
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
    if args.require_accepted_candidate and not report.accepted_candidate_found:
        raise SystemExit(1)


def _grid_parameters(
    options: HistoricalReplacementProbabilityPreservingGridOptions,
) -> Iterable[dict[str, object]]:
    for (
        selection_rule,
        shadow_selection_rule,
        min_replacement_probability,
        max_replacement_decimal_odds,
        min_candidate_hit_probability_delta_vs_model_top,
        min_item_hit_probability_delta_vs_original,
    ) in product(
        options.selection_rules,
        options.shadow_selection_rules,
        options.min_replacement_probability_values,
        options.max_replacement_decimal_odds_values,
        options.min_candidate_hit_probability_delta_vs_model_top_values,
        options.min_item_hit_probability_delta_vs_original_values,
    ):
        yield {
            "selection_rule": selection_rule,
            "shadow_selection_rule": shadow_selection_rule,
            "min_replacement_probability": min_replacement_probability,
            "max_replacement_decimal_odds": max_replacement_decimal_odds,
            "min_candidate_hit_probability_delta_vs_model_top": (
                min_candidate_hit_probability_delta_vs_model_top
            ),
            "min_item_hit_probability_delta_vs_original": (
                min_item_hit_probability_delta_vs_original
            ),
        }


def _gate_options(
    options: HistoricalReplacementProbabilityPreservingGridOptions,
    grid: dict[str, object],
) -> HistoricalShortOddsFinalAnswerGateOptions:
    return HistoricalShortOddsFinalAnswerGateOptions(
        profile_id=options.profile_id,
        ready_competition_ids=options.ready_competition_ids,
        selection_rule=str(grid["selection_rule"]),  # type: ignore[arg-type]
        shadow_selection_rule=str(grid["shadow_selection_rule"]),  # type: ignore[arg-type]
        min_changed_final_answer_count=options.min_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            options.min_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=options.min_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            options.min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=options.max_harm_count_vs_original,
        min_item_hit_probability_delta_vs_original=_required_float(
            grid["min_item_hit_probability_delta_vs_original"]
        ),
        exclude_original_hit_harm=options.exclude_original_hit_harm,
        min_replacement_probability=_required_float(grid["min_replacement_probability"]),
        min_replacement_decimal_odds=options.min_replacement_decimal_odds,
        max_replacement_decimal_odds=_required_float(
            grid["max_replacement_decimal_odds"]
        ),
        min_candidate_hit_probability_delta_vs_model_top=_required_float(
            grid["min_candidate_hit_probability_delta_vs_model_top"]
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            options.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=(
            options.min_decimal_odds_delta_vs_model_top
        ),
        max_report_items=500,
    )


def _candidate(
    gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    grid: dict[str, object],
) -> HistoricalReplacementProbabilityPreservingGridCandidate:
    gate_options = gate_report.summary_json.get("options")
    gate_options_json = gate_options if isinstance(gate_options, dict) else {}
    status: HistoricalReplacementProbabilityPreservingGridCandidateStatus
    if gate_report.decision == "final_answer_shadow_candidate":
        status = "accepted"
    elif gate_report.decision == "shadow_watchlist":
        status = "shadow_watchlist"
    else:
        status = "rejected"
    summary = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_grid_candidate_v3_1"
        ),
        "final_answer_gate_report_key": gate_report.report_key,
        "grid": grid,
        "production_recommendation_changed": False,
    }
    candidate_key = _digest_key("replacement_probability_preserving_candidate", summary)
    return HistoricalReplacementProbabilityPreservingGridCandidate(
        candidate_key=candidate_key,
        status=status,
        accepted=status == "accepted",
        final_answer_gate_report_key=gate_report.report_key,
        final_answer_gate_decision=gate_report.decision,
        final_answer_gate_decision_reasons=gate_report.decision_reasons,
        profile_id=gate_report.profile_id,
        ready_competition_ids=gate_report.ready_competition_ids,
        selection_rule=str(grid["selection_rule"]),  # type: ignore[arg-type]
        shadow_selection_rule=str(grid["shadow_selection_rule"]),  # type: ignore[arg-type]
        min_replacement_probability=_required_float(grid["min_replacement_probability"]),
        min_replacement_decimal_odds=_optional_float(
            gate_options_json.get("min_replacement_decimal_odds")
        ),
        max_replacement_decimal_odds=_required_float(
            grid["max_replacement_decimal_odds"]
        ),
        min_candidate_hit_probability_delta_vs_model_top=_required_float(
            grid["min_candidate_hit_probability_delta_vs_model_top"]
        ),
        max_candidate_hit_probability_delta_vs_model_top=_required_float(
            gate_options_json.get(
                "max_candidate_hit_probability_delta_vs_model_top",
                -0.02,
            )
        ),
        min_decimal_odds_delta_vs_model_top=_required_float(
            gate_options_json.get(
                "min_decimal_odds_delta_vs_model_top",
                0.0,
            )
        ),
        min_item_hit_probability_delta_vs_original=_required_float(
            grid["min_item_hit_probability_delta_vs_original"]
        ),
        exclude_original_hit_harm=bool(
            gate_options_json.get(
                "exclude_original_hit_harm",
                False,
            )
        ),
        candidate_replacement_option_count=gate_report.candidate_replacement_option_count,
        original_safe_replacement_option_count=(
            gate_report.original_safe_replacement_option_count
        ),
        original_safe_excluded_count=gate_report.original_safe_excluded_count,
        original_safe_exclusion_counts_json=(
            gate_report.original_safe_exclusion_counts_json
        ),
        changed_final_answer_count=gate_report.changed_final_answer_count,
        final_answer_hit_delta_count_vs_original=(
            gate_report.final_answer_hit_delta_count_vs_original
        ),
        profit_loss_delta_vs_original=gate_report.profit_loss_delta_vs_original,
        harm_count_vs_original=gate_report.harm_count_vs_original,
        expected_hit_probability_regression_count_vs_original=(
            gate_report.expected_hit_probability_regression_count_vs_original
        ),
        average_profit_loss_delta_vs_original=(
            gate_report.average_profit_loss_delta_vs_original
        ),
        average_hit_probability_delta_vs_original=(
            gate_report.average_hit_probability_delta_vs_original
        ),
        production_recommendation_changed=False,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _candidate_sort_key(
    candidate: HistoricalReplacementProbabilityPreservingGridCandidate,
) -> tuple[int, int, float, float, float, int, str]:
    return (
        _status_rank(candidate.status),
        candidate.final_answer_hit_delta_count_vs_original,
        candidate.profit_loss_delta_vs_original,
        candidate.average_hit_probability_delta_vs_original or -1.0,
        candidate.average_profit_loss_delta_vs_original or -1.0,
        -candidate.harm_count_vs_original,
        candidate.candidate_key,
    )


def _status_rank(status: str) -> int:
    return {
        "accepted": 3,
        "shadow_watchlist": 2,
        "rejected": 1,
    }[status]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Search probability-preserving final-answer replacement guard variants."
        )
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--competition-gate-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-id", default="max_model_edge_within_deficit_v1")
    parser.add_argument("--ready-competitions", default="")
    parser.add_argument(
        "--selection-rules",
        default="highest_candidate_hit_probability",
    )
    parser.add_argument(
        "--shadow-selection-rules",
        default=(
            "max_model_edge_within_deficit,nearest_model_top_probability,"
            "probability_preserving_model_edge"
        ),
    )
    parser.add_argument(
        "--min-replacement-probability-values",
        default="0.35,0.40,0.45,0.50",
    )
    parser.add_argument("--min-replacement-decimal-odds", type=float, default=1.75)
    parser.add_argument(
        "--max-replacement-decimal-odds-values",
        default="2.30,2.10,1.95",
    )
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-model-top-values",
        default="-1.0,-0.08,-0.05,-0.03",
    )
    parser.add_argument(
        "--max-candidate-hit-probability-delta-vs-model-top",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--min-decimal-odds-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument(
        "--min-item-hit-probability-delta-vs-original-values",
        default="-0.05,-0.03,-0.02,-0.01,0.0",
    )
    parser.add_argument("--min-changed-final-answer-count", type=int, default=1)
    parser.add_argument(
        "--min-final-answer-hit-delta-count-vs-original",
        type=int,
        default=0,
    )
    parser.add_argument("--min-profit-loss-delta-vs-original", type=float, default=0.0)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--allow-original-hit-harm",
        action="store_true",
        help="Disable the default evaluation-only original-hit harm exclusion.",
    )
    parser.add_argument("--max-candidate-count", type=int, default=500)
    parser.add_argument("--max-report-candidates", type=int, default=120)
    parser.add_argument("--require-accepted-candidate", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementProbabilityPreservingGridOptions:
    return HistoricalReplacementProbabilityPreservingGridOptions(
        profile_id=args.profile_id,
        ready_competition_ids=_csv_values(args.ready_competitions),
        selection_rules=_csv_values(args.selection_rules),  # type: ignore[arg-type]
        shadow_selection_rules=_csv_values(args.shadow_selection_rules),  # type: ignore[arg-type]
        min_replacement_probability_values=_csv_float_values(
            args.min_replacement_probability_values
        ),
        min_replacement_decimal_odds=args.min_replacement_decimal_odds,
        max_replacement_decimal_odds_values=_csv_float_values(
            args.max_replacement_decimal_odds_values
        ),
        min_candidate_hit_probability_delta_vs_model_top_values=_csv_float_values(
            args.min_candidate_hit_probability_delta_vs_model_top_values
        ),
        max_candidate_hit_probability_delta_vs_model_top=(
            args.max_candidate_hit_probability_delta_vs_model_top
        ),
        min_decimal_odds_delta_vs_model_top=args.min_decimal_odds_delta_vs_model_top,
        min_item_hit_probability_delta_vs_original_values=_csv_float_values(
            args.min_item_hit_probability_delta_vs_original_values
        ),
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_delta_count_vs_original=(
            args.min_final_answer_hit_delta_count_vs_original
        ),
        min_profit_loss_delta_vs_original=args.min_profit_loss_delta_vs_original,
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        exclude_original_hit_harm=not args.allow_original_hit_harm,
        max_candidate_count=args.max_candidate_count,
        max_report_candidates=args.max_report_candidates,
    )


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _csv_float_values(value: str) -> tuple[float, ...]:
    return tuple(float(item.strip()) for item in value.split(",") if item.strip())


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _required_float(value: object) -> float:
    if isinstance(value, bool):
        raise TypeError("Boolean values are not valid numeric grid parameters")
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"Unsupported numeric grid parameter: {value!r}")


def _report_key(
    summary: dict[str, object],
    candidates: Sequence[HistoricalReplacementProbabilityPreservingGridCandidate],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "candidates": [
                {
                    "candidate_key": candidate.candidate_key,
                    "status": candidate.status,
                    "gate_key": candidate.final_answer_gate_report_key,
                }
                for candidate in candidates
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_probability_preserving_grid:{digest}"


def _digest_key(prefix: str, payload: dict[str, object]) -> str:
    digest = sha256(
        dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"{prefix}:{digest}"
