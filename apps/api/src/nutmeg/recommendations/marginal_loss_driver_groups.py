from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
)

type HistoricalMarginalLossDriverGroupType = Literal[
    "competition",
    "pass_type",
    "mode",
    "selected_probability_band",
    "selected_odds_band",
    "selected_model_edge_band",
    "selected_score_band",
    "profile",
]

type HistoricalMarginalLossDriverDecision = Literal[
    "guard_candidate",
    "watchlist",
    "rejected",
]


class HistoricalMarginalLossDriverOptions(BaseModel):
    min_sample_size: int = Field(default=3, ge=1)
    min_miss_rate: float = Field(default=0.20, ge=0.0, le=1.0)
    min_actual_replacement_opportunity_rate: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
    )
    min_average_actual_best_profit_loss_delta: float = 0.0
    max_model_top_harm_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    include_profile_groups: bool = True


class HistoricalMarginalLossDriverGroup(BaseModel):
    group_key: str
    group_type: HistoricalMarginalLossDriverGroupType
    label: str
    band: str | None = None
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    miss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_loss_count: int = Field(ge=0)
    final_answer_loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    actual_replacement_opportunity_count: int = Field(ge=0)
    actual_replacement_opportunity_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    model_top_replacement_count: int = Field(ge=0)
    model_top_improvement_count: int = Field(ge=0)
    model_top_harm_count: int = Field(ge=0)
    model_top_harm_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_actual_best_profit_loss_delta: float | None = None
    average_model_top_profit_loss_delta: float | None = None
    average_model_top_hit_probability_delta: float | None = None
    average_selected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_selected_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_selected_model_edge: float | None = None
    average_selected_score: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: HistoricalMarginalLossDriverDecision
    decision_reasons: list[str] = Field(default_factory=list)
    item_keys: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarginalLossDriverReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    group_count: int = Field(ge=0)
    guard_candidate_count: int = Field(ge=0)
    watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    actual_replacement_opportunity_count: int = Field(ge=0)
    groups: list[HistoricalMarginalLossDriverGroup] = Field(default_factory=list)
    guard_candidates: list[HistoricalMarginalLossDriverGroup] = Field(default_factory=list)
    watchlist_groups: list[HistoricalMarginalLossDriverGroup] = Field(default_factory=list)
    top_loss_driver_groups: list[HistoricalMarginalLossDriverGroup] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _GroupSpec:
    group_key: str
    group_type: HistoricalMarginalLossDriverGroupType
    label: str
    band: str | None = None


@dataclass
class _GroupAccumulator:
    spec: _GroupSpec
    item_keys: set[str]
    selected_leg_count: int = 0
    missed_leg_count: int = 0
    final_answer_loss_count: int = 0
    actual_replacement_opportunity_count: int = 0
    actual_best_profit_loss_delta_sum: float = 0.0
    actual_best_profit_loss_delta_count: int = 0
    model_top_replacement_count: int = 0
    model_top_improvement_count: int = 0
    model_top_harm_count: int = 0
    model_top_profit_loss_delta_sum: float = 0.0
    model_top_hit_probability_delta_sum: float = 0.0
    selected_probability_sum: float = 0.0
    selected_decimal_odds_sum: float = 0.0
    selected_decimal_odds_count: int = 0
    selected_model_edge_sum: float = 0.0
    selected_score_sum: float = 0.0

    def add(self, item: HistoricalCandidateMarginalAuditItem) -> None:
        self.item_keys.add(item.item_key)
        self.selected_leg_count += 1
        self.missed_leg_count += int(not item.leg_actual_hit)
        self.final_answer_loss_count += int(not item.final_answer_actual_hit)
        self.selected_probability_sum += item.selected_probability
        if item.selected_decimal_odds is not None:
            self.selected_decimal_odds_sum += item.selected_decimal_odds
            self.selected_decimal_odds_count += 1
        self.selected_model_edge_sum += item.selected_model_edge
        self.selected_score_sum += item.selected_score
        actual_best = item.actual_best_replacement
        if actual_best is not None:
            self.actual_best_profit_loss_delta_sum += actual_best.profit_loss_delta
            self.actual_best_profit_loss_delta_count += 1
            self.actual_replacement_opportunity_count += int(
                actual_best.profit_loss_delta > 0
            )
        model_top = item.model_top_replacement
        if model_top is not None:
            self.model_top_replacement_count += 1
            self.model_top_improvement_count += int(model_top.profit_loss_delta > 0)
            self.model_top_harm_count += int(model_top.profit_loss_delta < 0)
            self.model_top_profit_loss_delta_sum += model_top.profit_loss_delta
            self.model_top_hit_probability_delta_sum += model_top.hit_probability_delta

    def group(
        self,
        *,
        options: HistoricalMarginalLossDriverOptions,
    ) -> HistoricalMarginalLossDriverGroup:
        decision, reasons = _decision_for_group(self, options=options)
        return HistoricalMarginalLossDriverGroup(
            group_key=self.spec.group_key,
            group_type=self.spec.group_type,
            label=self.spec.label,
            band=self.spec.band,
            selected_leg_count=self.selected_leg_count,
            missed_leg_count=self.missed_leg_count,
            miss_rate=_ratio(self.missed_leg_count, self.selected_leg_count),
            final_answer_loss_count=self.final_answer_loss_count,
            final_answer_loss_rate=_ratio(
                self.final_answer_loss_count,
                self.selected_leg_count,
            ),
            actual_replacement_opportunity_count=(
                self.actual_replacement_opportunity_count
            ),
            actual_replacement_opportunity_rate=_ratio(
                self.actual_replacement_opportunity_count,
                self.selected_leg_count,
            ),
            model_top_replacement_count=self.model_top_replacement_count,
            model_top_improvement_count=self.model_top_improvement_count,
            model_top_harm_count=self.model_top_harm_count,
            model_top_harm_rate=_ratio(
                self.model_top_harm_count,
                self.model_top_replacement_count,
            ),
            average_actual_best_profit_loss_delta=_ratio(
                self.actual_best_profit_loss_delta_sum,
                self.actual_best_profit_loss_delta_count,
            ),
            average_model_top_profit_loss_delta=_ratio(
                self.model_top_profit_loss_delta_sum,
                self.model_top_replacement_count,
            ),
            average_model_top_hit_probability_delta=_ratio(
                self.model_top_hit_probability_delta_sum,
                self.model_top_replacement_count,
            ),
            average_selected_probability=_ratio(
                self.selected_probability_sum,
                self.selected_leg_count,
            ),
            average_selected_decimal_odds=_ratio(
                self.selected_decimal_odds_sum,
                self.selected_decimal_odds_count,
            ),
            average_selected_model_edge=_ratio(
                self.selected_model_edge_sum,
                self.selected_leg_count,
            ),
            average_selected_score=_ratio(self.selected_score_sum, self.selected_leg_count),
            decision=decision,
            decision_reasons=reasons,
            item_keys=sorted(self.item_keys),
            summary_json={
                "sample_requirement": options.min_sample_size,
                "miss_rate_requirement": options.min_miss_rate,
                "actual_replacement_opportunity_rate_requirement": (
                    options.min_actual_replacement_opportunity_rate
                ),
                "average_actual_best_profit_loss_delta_requirement": (
                    options.min_average_actual_best_profit_loss_delta
                ),
                "model_top_harm_rate_limit": options.max_model_top_harm_rate,
            },
        )


def build_historical_marginal_loss_driver_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalMarginalLossDriverOptions | None = None,
) -> HistoricalMarginalLossDriverReport:
    resolved_options = options or HistoricalMarginalLossDriverOptions()
    accumulators: dict[str, _GroupAccumulator] = {}
    warnings = list(audit_report.warnings)

    for item in audit_report.items:
        for spec in _group_specs_for_item(item, options=resolved_options):
            accumulator = accumulators.setdefault(
                spec.group_key,
                _GroupAccumulator(spec=spec, item_keys=set()),
            )
            accumulator.add(item)

    groups = sorted(
        (
            accumulator.group(options=resolved_options)
            for accumulator in accumulators.values()
        ),
        key=lambda group: (group.group_type, group.group_key),
    )
    guard_candidates = _top_guard_candidates(groups)
    watchlist_groups = _top_watchlist_groups(groups)
    top_loss_driver_groups = _top_loss_driver_groups(groups)
    selected_leg_count = sum(
        group.selected_leg_count for group in groups if group.group_type == "mode"
    )
    missed_leg_count = sum(
        group.missed_leg_count for group in groups if group.group_type == "mode"
    )
    opportunity_count = sum(
        group.actual_replacement_opportunity_count
        for group in groups
        if group.group_type == "mode"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_marginal_loss_driver_groups_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "group_count": len(groups),
        "guard_candidate_count": sum(
            1 for group in groups if group.decision == "guard_candidate"
        ),
        "watchlist_count": sum(1 for group in groups if group.decision == "watchlist"),
        "rejected_count": sum(1 for group in groups if group.decision == "rejected"),
        "selected_leg_count": selected_leg_count,
        "missed_leg_count": missed_leg_count,
        "actual_replacement_opportunity_count": opportunity_count,
        "min_sample_size": resolved_options.min_sample_size,
        "min_miss_rate": resolved_options.min_miss_rate,
        "min_actual_replacement_opportunity_rate": (
            resolved_options.min_actual_replacement_opportunity_rate
        ),
        "min_average_actual_best_profit_loss_delta": (
            resolved_options.min_average_actual_best_profit_loss_delta
        ),
        "max_model_top_harm_rate": resolved_options.max_model_top_harm_rate,
        "include_profile_groups": resolved_options.include_profile_groups,
        "guard_candidate_group_keys": [
            group.group_key for group in guard_candidates
        ],
        "watchlist_group_keys": [group.group_key for group in watchlist_groups],
        "top_loss_driver_group_keys": [
            group.group_key for group in top_loss_driver_groups
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary)
    return HistoricalMarginalLossDriverReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        group_count=len(groups),
        guard_candidate_count=sum(
            1 for group in groups if group.decision == "guard_candidate"
        ),
        watchlist_count=sum(1 for group in groups if group.decision == "watchlist"),
        rejected_count=sum(1 for group in groups if group.decision == "rejected"),
        selected_leg_count=selected_leg_count,
        missed_leg_count=missed_leg_count,
        actual_replacement_opportunity_count=opportunity_count,
        groups=groups,
        guard_candidates=guard_candidates,
        watchlist_groups=watchlist_groups,
        top_loss_driver_groups=top_loss_driver_groups,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_candidate_marginal_audit_report(
    path: Path | str,
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_marginal_loss_driver_report(
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


def _group_specs_for_item(
    item: HistoricalCandidateMarginalAuditItem,
    *,
    options: HistoricalMarginalLossDriverOptions,
) -> list[_GroupSpec]:
    probability_band = _unit_band(item.selected_probability)
    odds_band = _odds_band(item.selected_decimal_odds)
    edge_band = _model_edge_band(item.selected_model_edge)
    score_band = _unit_band(item.selected_score)
    specs = [
        _GroupSpec(
            group_key=f"competition:{item.competition_id}",
            group_type="competition",
            label=item.competition_id,
        ),
        _GroupSpec(
            group_key=f"pass_type:{item.pass_type}",
            group_type="pass_type",
            label=item.pass_type,
        ),
        _GroupSpec(
            group_key=f"mode:{item.mode}",
            group_type="mode",
            label=item.mode,
        ),
        _GroupSpec(
            group_key=f"selected_probability_band:{probability_band}",
            group_type="selected_probability_band",
            label=f"selected probability {probability_band}",
            band=probability_band,
        ),
        _GroupSpec(
            group_key=f"selected_odds_band:{odds_band}",
            group_type="selected_odds_band",
            label=f"selected odds {odds_band}",
            band=odds_band,
        ),
        _GroupSpec(
            group_key=f"selected_model_edge_band:{edge_band}",
            group_type="selected_model_edge_band",
            label=f"selected model edge {edge_band}",
            band=edge_band,
        ),
        _GroupSpec(
            group_key=f"selected_score_band:{score_band}",
            group_type="selected_score_band",
            label=f"selected score {score_band}",
            band=score_band,
        ),
    ]
    if options.include_profile_groups:
        profile_key = "|".join(
            [
                item.competition_id,
                item.pass_type,
                f"probability:{probability_band}",
                f"odds:{odds_band}",
                f"edge:{edge_band}",
                f"score:{score_band}",
            ]
        )
        specs.append(
            _GroupSpec(
                group_key=f"profile:{profile_key}",
                group_type="profile",
                label=profile_key,
            )
        )
    return specs


def _decision_for_group(
    accumulator: _GroupAccumulator,
    *,
    options: HistoricalMarginalLossDriverOptions,
) -> tuple[HistoricalMarginalLossDriverDecision, list[str]]:
    reasons: list[str] = []
    miss_rate = _ratio(accumulator.missed_leg_count, accumulator.selected_leg_count)
    actual_opportunity_rate = _ratio(
        accumulator.actual_replacement_opportunity_count,
        accumulator.selected_leg_count,
    )
    average_actual_best_profit_loss_delta = _ratio(
        accumulator.actual_best_profit_loss_delta_sum,
        accumulator.actual_best_profit_loss_delta_count,
    )
    model_top_harm_rate = _ratio(
        accumulator.model_top_harm_count,
        accumulator.model_top_replacement_count,
    )
    if accumulator.selected_leg_count < options.min_sample_size:
        reasons.append("sample_size_below_threshold")
    if miss_rate is None or miss_rate < options.min_miss_rate:
        reasons.append("miss_rate_below_threshold")
    if (
        actual_opportunity_rate is None
        or actual_opportunity_rate < options.min_actual_replacement_opportunity_rate
    ):
        reasons.append("actual_replacement_opportunity_rate_below_threshold")
    if (
        average_actual_best_profit_loss_delta is None
        or average_actual_best_profit_loss_delta
        < options.min_average_actual_best_profit_loss_delta
    ):
        reasons.append("average_actual_best_profit_loss_delta_below_threshold")
    if (
        options.max_model_top_harm_rate is not None
        and (
            model_top_harm_rate is None
            or model_top_harm_rate > options.max_model_top_harm_rate
        )
    ):
        reasons.append("model_top_harm_rate_above_threshold")
    if not reasons:
        return "guard_candidate", ["guard_candidate_thresholds_satisfied"]
    if (
        accumulator.selected_leg_count >= options.min_sample_size
        and average_actual_best_profit_loss_delta is not None
        and average_actual_best_profit_loss_delta > 0
    ):
        return "watchlist", reasons
    return "rejected", reasons


def _top_guard_candidates(
    groups: Sequence[HistoricalMarginalLossDriverGroup],
) -> list[HistoricalMarginalLossDriverGroup]:
    return sorted(
        (group for group in groups if group.decision == "guard_candidate"),
        key=_loss_driver_sort_key,
        reverse=True,
    )[:20]


def _top_watchlist_groups(
    groups: Sequence[HistoricalMarginalLossDriverGroup],
) -> list[HistoricalMarginalLossDriverGroup]:
    return sorted(
        (group for group in groups if group.decision == "watchlist"),
        key=_loss_driver_sort_key,
        reverse=True,
    )[:20]


def _top_loss_driver_groups(
    groups: Sequence[HistoricalMarginalLossDriverGroup],
) -> list[HistoricalMarginalLossDriverGroup]:
    return sorted(groups, key=_loss_driver_sort_key, reverse=True)[:20]


def _loss_driver_sort_key(
    group: HistoricalMarginalLossDriverGroup,
) -> tuple[float, float, float, int, str]:
    return (
        group.average_actual_best_profit_loss_delta
        if group.average_actual_best_profit_loss_delta is not None
        else -999.0,
        group.actual_replacement_opportunity_rate
        if group.actual_replacement_opportunity_rate is not None
        else -1.0,
        group.miss_rate if group.miss_rate is not None else -1.0,
        group.selected_leg_count,
        group.group_key,
    )


def _unit_band(value: float) -> str:
    if value < 0.20:
        return "very_low"
    if value < 0.40:
        return "low"
    if value < 0.55:
        return "medium"
    if value < 0.65:
        return "medium_high"
    if value < 0.80:
        return "high"
    return "very_high"


def _odds_band(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 1.25:
        return "very_short"
    if value < 1.50:
        return "short"
    if value < 2.00:
        return "medium"
    if value < 3.00:
        return "wide"
    return "long"


def _model_edge_band(value: float) -> str:
    if value < -0.08:
        return "very_negative"
    if value < -0.02:
        return "negative"
    if value < 0.02:
        return "flat"
    if value < 0.08:
        return "positive"
    return "very_positive"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Group selected final-answer legs by marginal loss-driver signals."
    )
    parser.add_argument("--audit-report", required=True, type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-sample-size", type=int, default=3)
    parser.add_argument("--min-miss-rate", type=float, default=0.20)
    parser.add_argument("--min-actual-replacement-opportunity-rate", type=float, default=0.50)
    parser.add_argument(
        "--min-average-actual-best-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--max-model-top-harm-rate", type=float)
    parser.add_argument(
        "--profile-groups",
        action=BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalMarginalLossDriverOptions:
    return HistoricalMarginalLossDriverOptions(
        min_sample_size=args.min_sample_size,
        min_miss_rate=args.min_miss_rate,
        min_actual_replacement_opportunity_rate=(
            args.min_actual_replacement_opportunity_rate
        ),
        min_average_actual_best_profit_loss_delta=(
            args.min_average_actual_best_profit_loss_delta
        ),
        max_model_top_harm_rate=args.max_model_top_harm_rate,
        include_profile_groups=args.profile_groups,
    )


def _report_key(summary: dict[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_loss_driver_groups:{digest}"


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
