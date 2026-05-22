from __future__ import annotations

from argparse import ArgumentParser, Namespace
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
    HistoricalCandidateReplacementSimulation,
)

type HistoricalMarginalSignalGroupType = Literal[
    "competition",
    "pass_type",
    "mode",
    "selected_probability_band",
    "selected_odds_band",
    "selected_model_edge_band",
    "selected_score_band",
    "replacement_probability_band",
    "replacement_odds_band",
    "replacement_model_edge_band",
    "replacement_quality_band",
    "probability_delta_band",
    "odds_delta_band",
    "model_edge_delta_band",
    "profile",
]

type HistoricalMarginalSignalDecision = Literal[
    "profile_candidate",
    "watchlist",
    "rejected",
]


class HistoricalMarginalSignalGroupOptions(BaseModel):
    min_sample_size: int = Field(default=3, ge=1)
    min_improvement_rate: float = Field(default=0.55, ge=0.0, le=1.0)
    max_harm_rate: float = Field(default=0.30, ge=0.0, le=1.0)
    min_average_profit_loss_delta: float = 0.0
    min_average_hit_probability_delta: float | None = None
    min_replacement_hit_probability_delta: float | None = None
    include_profile_groups: bool = True


class HistoricalMarginalSignalGroup(BaseModel):
    group_key: str
    group_type: HistoricalMarginalSignalGroupType
    label: str
    band: str | None = None
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    model_top_replacement_count: int = Field(ge=0)
    improvement_count: int = Field(ge=0)
    harm_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    improvement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    harm_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    total_profit_loss_delta: float
    average_profit_loss_delta: float | None = None
    average_hit_probability_delta: float | None = None
    average_roi_delta: float | None = None
    average_risk_score_delta: float | None = None
    average_selected_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_selected_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_selected_model_edge: float | None = None
    average_replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_replacement_model_edge: float | None = None
    decision: HistoricalMarginalSignalDecision
    decision_reasons: list[str] = Field(default_factory=list)
    item_keys: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarginalSignalGroupReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    group_count: int = Field(ge=0)
    profile_candidate_count: int = Field(ge=0)
    watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    source_model_top_replacement_count: int = Field(ge=0)
    evaluated_replacement_count: int = Field(ge=0)
    filtered_replacement_count: int = Field(ge=0)
    groups: list[HistoricalMarginalSignalGroup] = Field(default_factory=list)
    profile_candidates: list[HistoricalMarginalSignalGroup] = Field(default_factory=list)
    watchlist_groups: list[HistoricalMarginalSignalGroup] = Field(default_factory=list)
    negative_signal_groups: list[HistoricalMarginalSignalGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _GroupSpec:
    group_key: str
    group_type: HistoricalMarginalSignalGroupType
    label: str
    band: str | None = None


@dataclass
class _GroupAccumulator:
    spec: _GroupSpec
    item_keys: set[str]
    selected_leg_count: int = 0
    missed_leg_count: int = 0
    model_top_replacement_count: int = 0
    improvement_count: int = 0
    harm_count: int = 0
    unchanged_count: int = 0
    profit_loss_delta_sum: float = 0.0
    hit_probability_delta_sum: float = 0.0
    roi_delta_sum: float = 0.0
    risk_score_delta_sum: float = 0.0
    selected_probability_sum: float = 0.0
    selected_decimal_odds_sum: float = 0.0
    selected_decimal_odds_count: int = 0
    selected_model_edge_sum: float = 0.0
    replacement_probability_sum: float = 0.0
    replacement_decimal_odds_sum: float = 0.0
    replacement_decimal_odds_count: int = 0
    replacement_model_edge_sum: float = 0.0

    def add(
        self,
        item: HistoricalCandidateMarginalAuditItem,
        replacement: HistoricalCandidateReplacementSimulation,
    ) -> None:
        self.item_keys.add(item.item_key)
        self.selected_leg_count += 1
        self.missed_leg_count += int(not item.leg_actual_hit)
        self.model_top_replacement_count += 1
        self.improvement_count += int(replacement.profit_loss_delta > 0)
        self.harm_count += int(replacement.profit_loss_delta < 0)
        self.unchanged_count += int(replacement.profit_loss_delta == 0)
        self.profit_loss_delta_sum += replacement.profit_loss_delta
        self.hit_probability_delta_sum += replacement.hit_probability_delta
        self.roi_delta_sum += replacement.roi_delta
        self.risk_score_delta_sum += replacement.risk_score_delta
        self.selected_probability_sum += item.selected_probability
        if item.selected_decimal_odds is not None:
            self.selected_decimal_odds_sum += item.selected_decimal_odds
            self.selected_decimal_odds_count += 1
        self.selected_model_edge_sum += item.selected_model_edge
        self.replacement_probability_sum += replacement.replacement_probability
        if replacement.replacement_decimal_odds is not None:
            self.replacement_decimal_odds_sum += replacement.replacement_decimal_odds
            self.replacement_decimal_odds_count += 1
        self.replacement_model_edge_sum += replacement.replacement_model_edge

    def group(
        self,
        *,
        options: HistoricalMarginalSignalGroupOptions,
    ) -> HistoricalMarginalSignalGroup:
        decision, reasons = _decision_for_group(self, options=options)
        return HistoricalMarginalSignalGroup(
            group_key=self.spec.group_key,
            group_type=self.spec.group_type,
            label=self.spec.label,
            band=self.spec.band,
            selected_leg_count=self.selected_leg_count,
            missed_leg_count=self.missed_leg_count,
            model_top_replacement_count=self.model_top_replacement_count,
            improvement_count=self.improvement_count,
            harm_count=self.harm_count,
            unchanged_count=self.unchanged_count,
            improvement_rate=_ratio(
                self.improvement_count,
                self.model_top_replacement_count,
            ),
            harm_rate=_ratio(self.harm_count, self.model_top_replacement_count),
            total_profit_loss_delta=self.profit_loss_delta_sum,
            average_profit_loss_delta=_ratio(
                self.profit_loss_delta_sum,
                self.model_top_replacement_count,
            ),
            average_hit_probability_delta=_ratio(
                self.hit_probability_delta_sum,
                self.model_top_replacement_count,
            ),
            average_roi_delta=_ratio(self.roi_delta_sum, self.model_top_replacement_count),
            average_risk_score_delta=_ratio(
                self.risk_score_delta_sum,
                self.model_top_replacement_count,
            ),
            average_selected_probability=_ratio(
                self.selected_probability_sum,
                self.model_top_replacement_count,
            ),
            average_selected_decimal_odds=_ratio(
                self.selected_decimal_odds_sum,
                self.selected_decimal_odds_count,
            ),
            average_selected_model_edge=_ratio(
                self.selected_model_edge_sum,
                self.model_top_replacement_count,
            ),
            average_replacement_probability=_ratio(
                self.replacement_probability_sum,
                self.model_top_replacement_count,
            ),
            average_replacement_decimal_odds=_ratio(
                self.replacement_decimal_odds_sum,
                self.replacement_decimal_odds_count,
            ),
            average_replacement_model_edge=_ratio(
                self.replacement_model_edge_sum,
                self.model_top_replacement_count,
            ),
            decision=decision,
            decision_reasons=reasons,
            item_keys=sorted(self.item_keys),
            summary_json={
                "missed_leg_rate": _ratio(
                    self.missed_leg_count,
                    self.selected_leg_count,
                ),
                "sample_requirement": options.min_sample_size,
                "improvement_rate_requirement": options.min_improvement_rate,
                "harm_rate_limit": options.max_harm_rate,
                "average_profit_loss_delta_requirement": (
                    options.min_average_profit_loss_delta
                ),
                "average_hit_probability_delta_requirement": (
                    options.min_average_hit_probability_delta
                ),
            },
        )


def build_historical_marginal_signal_group_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalMarginalSignalGroupOptions | None = None,
) -> HistoricalMarginalSignalGroupReport:
    resolved_options = options or HistoricalMarginalSignalGroupOptions()
    accumulators: dict[str, _GroupAccumulator] = {}
    source_model_top_replacement_count = 0
    evaluated_replacement_count = 0
    filtered_replacement_count = 0
    warnings = list(audit_report.warnings)

    for item in audit_report.items:
        replacement = item.model_top_replacement
        if replacement is None:
            continue
        source_model_top_replacement_count += 1
        if not _include_replacement(replacement, options=resolved_options):
            filtered_replacement_count += 1
            continue
        evaluated_replacement_count += 1
        for spec in _group_specs_for_item(
            item,
            replacement=replacement,
            options=resolved_options,
        ):
            accumulator = accumulators.setdefault(
                spec.group_key,
                _GroupAccumulator(spec=spec, item_keys=set()),
            )
            accumulator.add(item, replacement)

    groups = sorted(
        (
            accumulator.group(options=resolved_options)
            for accumulator in accumulators.values()
        ),
        key=lambda group: (group.group_type, group.group_key),
    )
    profile_candidates = _top_profile_candidates(groups)
    watchlist_groups = _top_watchlist_groups(groups)
    negative_signal_groups = _top_negative_signal_groups(groups)
    summary: dict[str, object] = {
        "calculation_basis": "historical_marginal_signal_groups_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "group_count": len(groups),
        "profile_candidate_count": sum(
            1 for group in groups if group.decision == "profile_candidate"
        ),
        "watchlist_count": sum(1 for group in groups if group.decision == "watchlist"),
        "rejected_count": sum(1 for group in groups if group.decision == "rejected"),
        "source_model_top_replacement_count": source_model_top_replacement_count,
        "evaluated_replacement_count": evaluated_replacement_count,
        "filtered_replacement_count": filtered_replacement_count,
        "min_sample_size": resolved_options.min_sample_size,
        "min_improvement_rate": resolved_options.min_improvement_rate,
        "max_harm_rate": resolved_options.max_harm_rate,
        "min_average_profit_loss_delta": (
            resolved_options.min_average_profit_loss_delta
        ),
        "min_average_hit_probability_delta": (
            resolved_options.min_average_hit_probability_delta
        ),
        "min_replacement_hit_probability_delta": (
            resolved_options.min_replacement_hit_probability_delta
        ),
        "include_profile_groups": resolved_options.include_profile_groups,
        "profile_candidate_group_keys": [
            group.group_key for group in profile_candidates
        ],
        "watchlist_group_keys": [group.group_key for group in watchlist_groups],
        "negative_signal_group_keys": [
            group.group_key for group in negative_signal_groups
        ],
        "warnings": warnings,
    }
    report_key = _report_key(summary)
    return HistoricalMarginalSignalGroupReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        group_count=len(groups),
        profile_candidate_count=sum(
            1 for group in groups if group.decision == "profile_candidate"
        ),
        watchlist_count=sum(1 for group in groups if group.decision == "watchlist"),
        rejected_count=sum(1 for group in groups if group.decision == "rejected"),
        source_model_top_replacement_count=source_model_top_replacement_count,
        evaluated_replacement_count=evaluated_replacement_count,
        filtered_replacement_count=filtered_replacement_count,
        groups=groups,
        profile_candidates=profile_candidates,
        watchlist_groups=watchlist_groups,
        negative_signal_groups=negative_signal_groups,
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
    report = build_historical_marginal_signal_group_report(
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
    replacement: HistoricalCandidateReplacementSimulation,
    options: HistoricalMarginalSignalGroupOptions,
) -> list[_GroupSpec]:
    selected_probability_band = _unit_band(item.selected_probability)
    selected_odds_band = _odds_band(item.selected_decimal_odds)
    selected_edge_band = _model_edge_band(item.selected_model_edge)
    selected_score_band = _unit_band(item.selected_score)
    replacement_probability_band = _unit_band(replacement.replacement_probability)
    replacement_odds_band = _odds_band(replacement.replacement_decimal_odds)
    replacement_edge_band = _model_edge_band(replacement.replacement_model_edge)
    replacement_quality_band = _unit_band(replacement.replacement_quality_score)
    probability_delta_band = _signed_band(
        replacement.replacement_probability - item.selected_probability
    )
    odds_delta_band = _signed_band(
        (
            replacement.replacement_decimal_odds
            if replacement.replacement_decimal_odds is not None
            else 0.0
        )
        - (item.selected_decimal_odds if item.selected_decimal_odds is not None else 0.0)
    )
    edge_delta_band = _signed_band(
        replacement.replacement_model_edge - item.selected_model_edge
    )
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
            group_key=f"selected_probability_band:{selected_probability_band}",
            group_type="selected_probability_band",
            label=f"selected probability {selected_probability_band}",
            band=selected_probability_band,
        ),
        _GroupSpec(
            group_key=f"selected_odds_band:{selected_odds_band}",
            group_type="selected_odds_band",
            label=f"selected odds {selected_odds_band}",
            band=selected_odds_band,
        ),
        _GroupSpec(
            group_key=f"selected_model_edge_band:{selected_edge_band}",
            group_type="selected_model_edge_band",
            label=f"selected model edge {selected_edge_band}",
            band=selected_edge_band,
        ),
        _GroupSpec(
            group_key=f"selected_score_band:{selected_score_band}",
            group_type="selected_score_band",
            label=f"selected score {selected_score_band}",
            band=selected_score_band,
        ),
        _GroupSpec(
            group_key=f"replacement_probability_band:{replacement_probability_band}",
            group_type="replacement_probability_band",
            label=f"replacement probability {replacement_probability_band}",
            band=replacement_probability_band,
        ),
        _GroupSpec(
            group_key=f"replacement_odds_band:{replacement_odds_band}",
            group_type="replacement_odds_band",
            label=f"replacement odds {replacement_odds_band}",
            band=replacement_odds_band,
        ),
        _GroupSpec(
            group_key=f"replacement_model_edge_band:{replacement_edge_band}",
            group_type="replacement_model_edge_band",
            label=f"replacement model edge {replacement_edge_band}",
            band=replacement_edge_band,
        ),
        _GroupSpec(
            group_key=f"replacement_quality_band:{replacement_quality_band}",
            group_type="replacement_quality_band",
            label=f"replacement quality {replacement_quality_band}",
            band=replacement_quality_band,
        ),
        _GroupSpec(
            group_key=f"probability_delta_band:{probability_delta_band}",
            group_type="probability_delta_band",
            label=f"probability delta {probability_delta_band}",
            band=probability_delta_band,
        ),
        _GroupSpec(
            group_key=f"odds_delta_band:{odds_delta_band}",
            group_type="odds_delta_band",
            label=f"odds delta {odds_delta_band}",
            band=odds_delta_band,
        ),
        _GroupSpec(
            group_key=f"model_edge_delta_band:{edge_delta_band}",
            group_type="model_edge_delta_band",
            label=f"model edge delta {edge_delta_band}",
            band=edge_delta_band,
        ),
    ]
    if options.include_profile_groups:
        profile_key = "|".join(
            [
                item.competition_id,
                item.pass_type,
                f"selected_probability:{selected_probability_band}",
                f"selected_odds:{selected_odds_band}",
                f"selected_edge:{selected_edge_band}",
                f"replacement_probability:{replacement_probability_band}",
                f"probability_delta:{probability_delta_band}",
                f"edge_delta:{edge_delta_band}",
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


def _include_replacement(
    replacement: HistoricalCandidateReplacementSimulation,
    *,
    options: HistoricalMarginalSignalGroupOptions,
) -> bool:
    if options.min_replacement_hit_probability_delta is None:
        return True
    return (
        replacement.hit_probability_delta
        >= options.min_replacement_hit_probability_delta
    )


def _decision_for_group(
    accumulator: _GroupAccumulator,
    *,
    options: HistoricalMarginalSignalGroupOptions,
) -> tuple[HistoricalMarginalSignalDecision, list[str]]:
    reasons: list[str] = []
    improvement_rate = _ratio(
        accumulator.improvement_count,
        accumulator.model_top_replacement_count,
    )
    harm_rate = _ratio(accumulator.harm_count, accumulator.model_top_replacement_count)
    average_profit_loss_delta = _ratio(
        accumulator.profit_loss_delta_sum,
        accumulator.model_top_replacement_count,
    )
    average_hit_probability_delta = _ratio(
        accumulator.hit_probability_delta_sum,
        accumulator.model_top_replacement_count,
    )
    if accumulator.model_top_replacement_count < options.min_sample_size:
        reasons.append("sample_size_below_threshold")
    if (
        improvement_rate is None
        or improvement_rate < options.min_improvement_rate
    ):
        reasons.append("improvement_rate_below_threshold")
    if harm_rate is None or harm_rate > options.max_harm_rate:
        reasons.append("harm_rate_above_threshold")
    if (
        average_profit_loss_delta is None
        or average_profit_loss_delta < options.min_average_profit_loss_delta
    ):
        reasons.append("average_profit_loss_delta_below_threshold")
    if (
        options.min_average_hit_probability_delta is not None
        and (
            average_hit_probability_delta is None
            or average_hit_probability_delta
            < options.min_average_hit_probability_delta
        )
    ):
        reasons.append("average_hit_probability_delta_below_threshold")
    if not reasons:
        return "profile_candidate", ["candidate_thresholds_satisfied"]
    if (
        accumulator.model_top_replacement_count >= options.min_sample_size
        and average_profit_loss_delta is not None
        and average_profit_loss_delta > 0
    ):
        return "watchlist", reasons
    return "rejected", reasons


def _top_profile_candidates(
    groups: Sequence[HistoricalMarginalSignalGroup],
) -> list[HistoricalMarginalSignalGroup]:
    return sorted(
        (group for group in groups if group.decision == "profile_candidate"),
        key=lambda group: (
            group.average_profit_loss_delta
            if group.average_profit_loss_delta is not None
            else -999.0,
            group.improvement_rate if group.improvement_rate is not None else -1.0,
            -(group.harm_rate if group.harm_rate is not None else 1.0),
            group.model_top_replacement_count,
            group.group_key,
        ),
        reverse=True,
    )[:20]


def _top_watchlist_groups(
    groups: Sequence[HistoricalMarginalSignalGroup],
) -> list[HistoricalMarginalSignalGroup]:
    return sorted(
        (group for group in groups if group.decision == "watchlist"),
        key=lambda group: (
            group.average_profit_loss_delta
            if group.average_profit_loss_delta is not None
            else -999.0,
            group.improvement_rate if group.improvement_rate is not None else -1.0,
            -(group.harm_rate if group.harm_rate is not None else 1.0),
            group.model_top_replacement_count,
            group.group_key,
        ),
        reverse=True,
    )[:20]


def _top_negative_signal_groups(
    groups: Sequence[HistoricalMarginalSignalGroup],
) -> list[HistoricalMarginalSignalGroup]:
    return sorted(
        (
            group
            for group in groups
            if group.average_profit_loss_delta is not None
            and group.average_profit_loss_delta < 0
        ),
        key=lambda group: (
            group.average_profit_loss_delta
            if group.average_profit_loss_delta is not None
            else 999.0,
            -(group.harm_rate if group.harm_rate is not None else 0.0),
            -group.model_top_replacement_count,
            group.group_key,
        ),
    )[:20]


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


def _signed_band(value: float) -> str:
    if value < -0.20:
        return "large_down"
    if value < -0.05:
        return "down"
    if value < 0.05:
        return "flat"
    if value < 0.20:
        return "up"
    return "large_up"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Group marginal replacement audit results by pre-match signals."
    )
    parser.add_argument("--audit-report", required=True, type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-sample-size", type=int, default=3)
    parser.add_argument("--min-improvement-rate", type=float, default=0.55)
    parser.add_argument("--max-harm-rate", type=float, default=0.30)
    parser.add_argument("--min-average-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-average-hit-probability-delta", type=float)
    parser.add_argument("--min-replacement-hit-probability-delta", type=float)
    parser.add_argument(
        "--no-profile-groups",
        action="store_true",
        help="Disable composite profile groups and emit only single-signal groups.",
    )
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalMarginalSignalGroupOptions:
    return HistoricalMarginalSignalGroupOptions(
        min_sample_size=args.min_sample_size,
        min_improvement_rate=args.min_improvement_rate,
        max_harm_rate=args.max_harm_rate,
        min_average_profit_loss_delta=args.min_average_profit_loss_delta,
        min_average_hit_probability_delta=args.min_average_hit_probability_delta,
        min_replacement_hit_probability_delta=(
            args.min_replacement_hit_probability_delta
        ),
        include_profile_groups=not args.no_profile_groups,
    )


def _report_key(summary: dict[str, object]) -> str:
    payload = dumps(summary, sort_keys=True, default=str)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_marginal_signal_groups:{digest}"


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
