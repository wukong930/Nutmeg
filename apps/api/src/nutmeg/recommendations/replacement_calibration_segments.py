from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
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
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)

type HistoricalReplacementCalibrationGroupType = Literal[
    "competition",
    "replacement_probability_band",
    "replacement_odds_band",
    "replacement_model_edge_band",
    "hit_probability_delta_band",
    "replacement_rank_band",
    "competition_odds_band",
    "competition_hit_probability_delta_band",
    "profile",
]

type HistoricalReplacementCalibrationDecision = Literal[
    "calibration_candidate",
    "watchlist",
    "rejected",
]

type HistoricalReplacementCalibrationSearchPlanStatus = Literal[
    "search_ready",
    "watchlist",
]


class HistoricalReplacementCalibrationSegmentOptions(BaseModel):
    min_actual_best_profit_loss_delta: float = 0.0
    min_profit_loss_delta_vs_model_top: float = 0.0
    min_group_sample_size: int = Field(default=3, ge=1)
    min_average_profit_loss_delta_vs_model_top: float = 0.0
    max_average_hit_probability_delta_vs_model_top: float = 0.0
    min_simulated_actual_hit_delta_count_vs_model_top: int = 0
    min_replacement_leg_hit_delta_count_vs_model_top: int = 0
    include_profile_groups: bool = True
    max_report_groups: int = Field(default=120, ge=1, le=500)
    max_report_observations: int = Field(default=80, ge=1, le=500)
    max_search_plans: int = Field(default=12, ge=1, le=100)


class HistoricalReplacementCalibrationObservation(BaseModel):
    observation_key: str
    item_key: str
    competition_id: str
    slice_id: str
    selected_fixture_id: str
    selected_outcome: str
    replacement_fixture_id: str
    replacement_outcome: str
    replacement_rank: int = Field(ge=1)
    replacement_probability: float = Field(ge=0.0, le=1.0)
    replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    replacement_model_edge: float
    replacement_score: float = Field(ge=0.0, le=1.0)
    replacement_quality_score: float = Field(ge=0.0, le=1.0)
    replacement_leg_actual_hit: bool
    model_top_replacement_leg_actual_hit: bool
    simulated_actual_hit: bool
    model_top_simulated_actual_hit: bool
    profit_loss_delta: float
    model_top_profit_loss_delta: float
    profit_loss_delta_vs_model_top: float
    hit_probability_delta_vs_model_top: float
    probability_delta_vs_model_top: float
    decimal_odds_delta_vs_model_top: float | None = None
    model_edge_delta_vs_model_top: float
    score_delta_vs_model_top: float
    quality_score_delta_vs_model_top: float
    risk_score_delta_vs_model_top: float
    replacement_probability_band: str
    replacement_odds_band: str
    replacement_model_edge_band: str
    hit_probability_delta_band: str
    replacement_rank_band: str
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementCalibrationGroup(BaseModel):
    group_key: str
    group_type: HistoricalReplacementCalibrationGroupType
    label: str
    band: str | None = None
    decision: HistoricalReplacementCalibrationDecision
    decision_reasons: list[str] = Field(default_factory=list)
    observation_count: int = Field(ge=0)
    simulated_actual_hit_count: int = Field(ge=0)
    model_top_simulated_actual_hit_count: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_count: int = Field(ge=0)
    model_top_replacement_leg_hit_count: int = Field(ge=0)
    replacement_leg_hit_delta_count_vs_model_top: int
    replacement_leg_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    model_top_replacement_leg_hit_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    simulated_actual_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    model_top_simulated_actual_hit_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    average_profit_loss_delta: float | None = None
    average_model_top_profit_loss_delta: float | None = None
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_probability_delta_vs_model_top: float | None = None
    average_decimal_odds_delta_vs_model_top: float | None = None
    average_model_edge_delta_vs_model_top: float | None = None
    average_score_delta_vs_model_top: float | None = None
    average_quality_score_delta_vs_model_top: float | None = None
    average_risk_score_delta_vs_model_top: float | None = None
    average_replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_replacement_model_edge: float | None = None
    observation_keys: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementCalibrationSearchPlan(BaseModel):
    plan_key: str
    status: HistoricalReplacementCalibrationSearchPlanStatus
    source_group_key: str
    source_group_type: HistoricalReplacementCalibrationGroupType
    source_decision: HistoricalReplacementCalibrationDecision
    source_surface_kind: str
    source_surface_missed_legs_only: bool
    runtime_candidate_surface_allowed: bool
    competition_ids: list[str] = Field(default_factory=list)
    replacement_odds_band: str
    hit_probability_delta_band: str
    min_replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    max_replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    min_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    min_candidate_hit_probability_delta_vs_model_top: float | None = None
    max_candidate_hit_probability_delta_vs_model_top: float | None = None
    observation_count: int = Field(ge=0)
    simulated_actual_hit_delta_count_vs_model_top: int
    replacement_leg_hit_delta_count_vs_model_top: int
    average_profit_loss_delta_vs_model_top: float | None = None
    average_hit_probability_delta_vs_model_top: float | None = None
    average_replacement_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_replacement_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_replacement_model_edge: float | None = None
    required_next_gates: list[str] = Field(default_factory=list)
    search_args_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalReplacementCalibrationSegmentReport(BaseModel):
    report_key: str
    status: str
    source_audit_report_key: str
    source_surface_kind: str = "unknown_replacement_surface"
    source_surface_missed_legs_only: bool = False
    runtime_candidate_surface_allowed: bool = False
    observation_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    calibration_candidate_count: int = Field(ge=0)
    watchlist_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    search_plan_count: int = Field(default=0, ge=0)
    groups: list[HistoricalReplacementCalibrationGroup] = Field(default_factory=list)
    calibration_candidates: list[HistoricalReplacementCalibrationGroup] = Field(
        default_factory=list
    )
    watchlist_groups: list[HistoricalReplacementCalibrationGroup] = Field(
        default_factory=list
    )
    search_plans: list[HistoricalReplacementCalibrationSearchPlan] = Field(
        default_factory=list
    )
    top_observations: list[HistoricalReplacementCalibrationObservation] = Field(
        default_factory=list
    )
    recommended_next_action_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _GroupSpec:
    group_key: str
    group_type: HistoricalReplacementCalibrationGroupType
    label: str
    band: str | None = None


@dataclass
class _GroupAccumulator:
    spec: _GroupSpec
    observation_keys: set[str] = field(default_factory=set)
    observations: list[HistoricalReplacementCalibrationObservation] = field(
        default_factory=list
    )

    def add(self, observation: HistoricalReplacementCalibrationObservation) -> None:
        self.observation_keys.add(observation.observation_key)
        self.observations.append(observation)

    def group(
        self,
        *,
        options: HistoricalReplacementCalibrationSegmentOptions,
    ) -> HistoricalReplacementCalibrationGroup:
        decision, reasons = _decision_for_group(self.observations, options=options)
        simulated_actual_hit_count = sum(
            1 for observation in self.observations if observation.simulated_actual_hit
        )
        model_top_simulated_actual_hit_count = sum(
            1
            for observation in self.observations
            if observation.model_top_simulated_actual_hit
        )
        replacement_leg_hit_count = sum(
            1
            for observation in self.observations
            if observation.replacement_leg_actual_hit
        )
        model_top_replacement_leg_hit_count = sum(
            1
            for observation in self.observations
            if observation.model_top_replacement_leg_actual_hit
        )
        observation_count = len(self.observations)
        return HistoricalReplacementCalibrationGroup(
            group_key=self.spec.group_key,
            group_type=self.spec.group_type,
            label=self.spec.label,
            band=self.spec.band,
            decision=decision,
            decision_reasons=reasons,
            observation_count=observation_count,
            simulated_actual_hit_count=simulated_actual_hit_count,
            model_top_simulated_actual_hit_count=model_top_simulated_actual_hit_count,
            simulated_actual_hit_delta_count_vs_model_top=(
                simulated_actual_hit_count - model_top_simulated_actual_hit_count
            ),
            replacement_leg_hit_count=replacement_leg_hit_count,
            model_top_replacement_leg_hit_count=model_top_replacement_leg_hit_count,
            replacement_leg_hit_delta_count_vs_model_top=(
                replacement_leg_hit_count - model_top_replacement_leg_hit_count
            ),
            replacement_leg_hit_rate=_ratio(replacement_leg_hit_count, observation_count),
            model_top_replacement_leg_hit_rate=_ratio(
                model_top_replacement_leg_hit_count,
                observation_count,
            ),
            simulated_actual_hit_rate=_ratio(
                simulated_actual_hit_count,
                observation_count,
            ),
            model_top_simulated_actual_hit_rate=_ratio(
                model_top_simulated_actual_hit_count,
                observation_count,
            ),
            average_profit_loss_delta=_average(
                observation.profit_loss_delta for observation in self.observations
            ),
            average_model_top_profit_loss_delta=_average(
                observation.model_top_profit_loss_delta
                for observation in self.observations
            ),
            average_profit_loss_delta_vs_model_top=_average(
                observation.profit_loss_delta_vs_model_top
                for observation in self.observations
            ),
            average_hit_probability_delta_vs_model_top=_average(
                observation.hit_probability_delta_vs_model_top
                for observation in self.observations
            ),
            average_probability_delta_vs_model_top=_average(
                observation.probability_delta_vs_model_top
                for observation in self.observations
            ),
            average_decimal_odds_delta_vs_model_top=_average(
                observation.decimal_odds_delta_vs_model_top
                for observation in self.observations
            ),
            average_model_edge_delta_vs_model_top=_average(
                observation.model_edge_delta_vs_model_top
                for observation in self.observations
            ),
            average_score_delta_vs_model_top=_average(
                observation.score_delta_vs_model_top
                for observation in self.observations
            ),
            average_quality_score_delta_vs_model_top=_average(
                observation.quality_score_delta_vs_model_top
                for observation in self.observations
            ),
            average_risk_score_delta_vs_model_top=_average(
                observation.risk_score_delta_vs_model_top
                for observation in self.observations
            ),
            average_replacement_probability=_average(
                observation.replacement_probability for observation in self.observations
            ),
            average_replacement_decimal_odds=_average(
                observation.replacement_decimal_odds for observation in self.observations
            ),
            average_replacement_model_edge=_average(
                observation.replacement_model_edge for observation in self.observations
            ),
            observation_keys=sorted(self.observation_keys),
            summary_json={
                "calculation_basis": "historical_replacement_calibration_group_v3_1",
                "group_type": self.spec.group_type,
                "group_key": self.spec.group_key,
            },
        )


def build_historical_replacement_calibration_segment_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    options: HistoricalReplacementCalibrationSegmentOptions | None = None,
) -> HistoricalReplacementCalibrationSegmentReport:
    resolved_options = options or HistoricalReplacementCalibrationSegmentOptions()
    warnings = list(audit_report.warnings)
    source_surface = _source_surface_summary(audit_report)
    observations = [
        observation
        for item in audit_report.items
        if (
            observation := _observation_for_item(
                item,
                options=resolved_options,
            )
        )
        is not None
    ]
    if not observations:
        warnings.append("no_replacement_calibration_observations")

    groups = _groups_from_observations(observations, options=resolved_options)
    sorted_groups = sorted(
        groups,
        key=lambda group: (
            _decision_rank(group.decision),
            group.simulated_actual_hit_delta_count_vs_model_top,
            group.replacement_leg_hit_delta_count_vs_model_top,
            group.average_profit_loss_delta_vs_model_top or 0.0,
            -abs(group.average_hit_probability_delta_vs_model_top or 0.0),
            group.observation_count,
            group.group_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_groups]
    calibration_candidates = [
        group
        for group in sorted_groups
        if group.decision == "calibration_candidate"
    ]
    watchlist_groups = [
        group for group in sorted_groups if group.decision == "watchlist"
    ]
    top_observations = sorted(
        observations,
        key=lambda observation: (
            observation.profit_loss_delta_vs_model_top,
            -abs(observation.hit_probability_delta_vs_model_top),
            observation.observation_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_observations]
    search_plans = _search_plans_from_groups(
        sorted_groups,
        source_surface_kind=source_surface["source_surface_kind"],
        source_surface_missed_legs_only=bool(source_surface["missed_legs_only"]),
        runtime_candidate_surface_allowed=bool(
            source_surface["runtime_candidate_surface_allowed"]
        ),
        options=resolved_options,
    )
    recommended_next_action = _recommended_next_action(
        search_plans,
        source_surface_kind=source_surface["source_surface_kind"],
        runtime_candidate_surface_allowed=bool(
            source_surface["runtime_candidate_surface_allowed"]
        ),
    )
    report_summary: dict[str, object] = {
        "calculation_basis": "historical_replacement_calibration_segments_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "source_surface_kind": source_surface["source_surface_kind"],
        "source_surface_missed_legs_only": source_surface["missed_legs_only"],
        "runtime_candidate_surface_allowed": source_surface[
            "runtime_candidate_surface_allowed"
        ],
        "source_item_count": len(audit_report.items),
        "observation_count": len(observations),
        "group_count": len(groups),
        "calibration_candidate_count": len(calibration_candidates),
        "watchlist_count": len(watchlist_groups),
        "search_plan_count": len(search_plans),
        "recommended_next_action": recommended_next_action,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(report_summary, sorted_groups, top_observations)
    return HistoricalReplacementCalibrationSegmentReport(
        report_key=report_key,
        status="generated",
        source_audit_report_key=audit_report.report_key,
        source_surface_kind=str(source_surface["source_surface_kind"]),
        source_surface_missed_legs_only=bool(source_surface["missed_legs_only"]),
        runtime_candidate_surface_allowed=bool(
            source_surface["runtime_candidate_surface_allowed"]
        ),
        observation_count=len(observations),
        group_count=len(groups),
        calibration_candidate_count=len(calibration_candidates),
        watchlist_count=len(watchlist_groups),
        rejected_count=sum(1 for group in groups if group.decision == "rejected"),
        search_plan_count=len(search_plans),
        groups=sorted_groups,
        calibration_candidates=calibration_candidates,
        watchlist_groups=watchlist_groups,
        search_plans=search_plans,
        top_observations=top_observations,
        recommended_next_action_json=recommended_next_action,
        warnings=warnings,
        summary_json={**report_summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    report = build_historical_replacement_calibration_segment_report(
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


def _observation_for_item(
    item: HistoricalCandidateMarginalAuditItem,
    *,
    options: HistoricalReplacementCalibrationSegmentOptions,
) -> HistoricalReplacementCalibrationObservation | None:
    model_top = item.model_top_replacement
    actual_best = item.actual_best_replacement
    if model_top is None or actual_best is None:
        return None
    if actual_best.profit_loss_delta <= options.min_actual_best_profit_loss_delta:
        return None
    profit_loss_delta_vs_model_top = (
        actual_best.profit_loss_delta - model_top.profit_loss_delta
    )
    if profit_loss_delta_vs_model_top <= options.min_profit_loss_delta_vs_model_top:
        return None
    decimal_odds_delta = _decimal_odds_delta(actual_best, model_top)
    hit_probability_delta = (
        actual_best.simulated_hit_probability - model_top.simulated_hit_probability
    )
    return HistoricalReplacementCalibrationObservation(
        observation_key=f"{item.item_key}:actual_best",
        item_key=item.item_key,
        competition_id=item.competition_id,
        slice_id=item.slice_id,
        selected_fixture_id=item.selected_fixture_id,
        selected_outcome=item.selected_outcome,
        replacement_fixture_id=actual_best.replacement_fixture_id,
        replacement_outcome=actual_best.replacement_outcome,
        replacement_rank=actual_best.replacement_rank,
        replacement_probability=actual_best.replacement_probability,
        replacement_decimal_odds=actual_best.replacement_decimal_odds,
        replacement_model_edge=actual_best.replacement_model_edge,
        replacement_score=actual_best.replacement_score,
        replacement_quality_score=actual_best.replacement_quality_score,
        replacement_leg_actual_hit=actual_best.replacement_leg_actual_hit,
        model_top_replacement_leg_actual_hit=model_top.replacement_leg_actual_hit,
        simulated_actual_hit=actual_best.simulated_actual_hit,
        model_top_simulated_actual_hit=model_top.simulated_actual_hit,
        profit_loss_delta=actual_best.profit_loss_delta,
        model_top_profit_loss_delta=model_top.profit_loss_delta,
        profit_loss_delta_vs_model_top=profit_loss_delta_vs_model_top,
        hit_probability_delta_vs_model_top=hit_probability_delta,
        probability_delta_vs_model_top=(
            actual_best.replacement_probability - model_top.replacement_probability
        ),
        decimal_odds_delta_vs_model_top=decimal_odds_delta,
        model_edge_delta_vs_model_top=(
            actual_best.replacement_model_edge - model_top.replacement_model_edge
        ),
        score_delta_vs_model_top=(
            actual_best.replacement_score - model_top.replacement_score
        ),
        quality_score_delta_vs_model_top=(
            actual_best.replacement_quality_score
            - model_top.replacement_quality_score
        ),
        risk_score_delta_vs_model_top=(
            actual_best.simulated_risk_score - model_top.simulated_risk_score
        ),
        replacement_probability_band=_probability_band(
            actual_best.replacement_probability
        ),
        replacement_odds_band=_odds_band(actual_best.replacement_decimal_odds),
        replacement_model_edge_band=_model_edge_band(
            actual_best.replacement_model_edge
        ),
        hit_probability_delta_band=_hit_probability_delta_band(hit_probability_delta),
        replacement_rank_band=_rank_band(actual_best.replacement_rank),
        summary_json={
            "model_top_replacement_fixture_id": model_top.replacement_fixture_id,
            "model_top_replacement_outcome": model_top.replacement_outcome,
            "model_top_replacement_rank": model_top.replacement_rank,
            "selected_probability": item.selected_probability,
            "selected_decimal_odds": item.selected_decimal_odds,
            "selected_model_edge": item.selected_model_edge,
        },
    )


def _groups_from_observations(
    observations: Sequence[HistoricalReplacementCalibrationObservation],
    *,
    options: HistoricalReplacementCalibrationSegmentOptions,
) -> list[HistoricalReplacementCalibrationGroup]:
    accumulators: dict[str, _GroupAccumulator] = {}
    for observation in observations:
        for spec in _group_specs(observation, include_profile=options.include_profile_groups):
            accumulator = accumulators.setdefault(
                spec.group_key,
                _GroupAccumulator(spec=spec),
            )
            accumulator.add(observation)
    return [
        accumulator.group(options=options)
        for accumulator in accumulators.values()
    ]


def _group_specs(
    observation: HistoricalReplacementCalibrationObservation,
    *,
    include_profile: bool,
) -> list[_GroupSpec]:
    specs = [
        _GroupSpec(
            group_key=f"competition:{observation.competition_id}",
            group_type="competition",
            label=observation.competition_id,
        ),
        _GroupSpec(
            group_key=f"replacement_probability_band:{observation.replacement_probability_band}",
            group_type="replacement_probability_band",
            label=observation.replacement_probability_band,
            band=observation.replacement_probability_band,
        ),
        _GroupSpec(
            group_key=f"replacement_odds_band:{observation.replacement_odds_band}",
            group_type="replacement_odds_band",
            label=observation.replacement_odds_band,
            band=observation.replacement_odds_band,
        ),
        _GroupSpec(
            group_key=f"replacement_model_edge_band:{observation.replacement_model_edge_band}",
            group_type="replacement_model_edge_band",
            label=observation.replacement_model_edge_band,
            band=observation.replacement_model_edge_band,
        ),
        _GroupSpec(
            group_key=f"hit_probability_delta_band:{observation.hit_probability_delta_band}",
            group_type="hit_probability_delta_band",
            label=observation.hit_probability_delta_band,
            band=observation.hit_probability_delta_band,
        ),
        _GroupSpec(
            group_key=f"replacement_rank_band:{observation.replacement_rank_band}",
            group_type="replacement_rank_band",
            label=observation.replacement_rank_band,
            band=observation.replacement_rank_band,
        ),
        _GroupSpec(
            group_key=(
                f"competition_odds_band:{observation.competition_id}|"
                f"{observation.replacement_odds_band}"
            ),
            group_type="competition_odds_band",
            label=(
                f"{observation.competition_id} / "
                f"{observation.replacement_odds_band}"
            ),
            band=observation.replacement_odds_band,
        ),
        _GroupSpec(
            group_key=(
                f"competition_hit_probability_delta_band:{observation.competition_id}|"
                f"{observation.hit_probability_delta_band}"
            ),
            group_type="competition_hit_probability_delta_band",
            label=(
                f"{observation.competition_id} / "
                f"{observation.hit_probability_delta_band}"
            ),
            band=observation.hit_probability_delta_band,
        ),
    ]
    if include_profile:
        specs.append(
            _GroupSpec(
                group_key=(
                    f"profile:{observation.competition_id}|"
                    f"{observation.replacement_odds_band}|"
                    f"{observation.hit_probability_delta_band}"
                ),
                group_type="profile",
                label=(
                    f"{observation.competition_id} / "
                    f"{observation.replacement_odds_band} / "
                    f"{observation.hit_probability_delta_band}"
                ),
            )
        )
    return specs


def _decision_for_group(
    observations: Sequence[HistoricalReplacementCalibrationObservation],
    *,
    options: HistoricalReplacementCalibrationSegmentOptions,
) -> tuple[HistoricalReplacementCalibrationDecision, list[str]]:
    observation_count = len(observations)
    simulated_actual_hit_delta = sum(
        int(observation.simulated_actual_hit)
        - int(observation.model_top_simulated_actual_hit)
        for observation in observations
    )
    replacement_leg_hit_delta = sum(
        int(observation.replacement_leg_actual_hit)
        - int(observation.model_top_replacement_leg_actual_hit)
        for observation in observations
    )
    average_profit_delta = _average(
        observation.profit_loss_delta_vs_model_top for observation in observations
    )
    average_hit_probability_delta = _average(
        observation.hit_probability_delta_vs_model_top for observation in observations
    )
    reasons: list[str] = []
    if observation_count < options.min_group_sample_size:
        reasons.append("sample_size_below_threshold")
    if (
        average_profit_delta is None
        or average_profit_delta
        <= options.min_average_profit_loss_delta_vs_model_top
    ):
        reasons.append("average_profit_loss_delta_vs_model_top_below_threshold")
    if (
        average_hit_probability_delta is None
        or average_hit_probability_delta
        > options.max_average_hit_probability_delta_vs_model_top
    ):
        reasons.append("average_hit_probability_delta_vs_model_top_above_threshold")
    if (
        simulated_actual_hit_delta
        < options.min_simulated_actual_hit_delta_count_vs_model_top
    ):
        reasons.append("simulated_actual_hit_delta_below_threshold")
    if (
        replacement_leg_hit_delta
        < options.min_replacement_leg_hit_delta_count_vs_model_top
    ):
        reasons.append("replacement_leg_hit_delta_below_threshold")
    if not reasons:
        return "calibration_candidate", []
    if (
        average_profit_delta is not None
        and average_profit_delta > 0
        and simulated_actual_hit_delta >= 0
        and replacement_leg_hit_delta >= 0
    ):
        return "watchlist", reasons
    return "rejected", reasons


def _source_surface_summary(
    audit_report: HistoricalCandidateMarginalAuditReport,
) -> dict[str, object]:
    target_filter = audit_report.summary_json.get("target_filter")
    missed_from_filter: bool | None = None
    if isinstance(target_filter, dict):
        missed_value = target_filter.get("missed_legs_only")
        if isinstance(missed_value, bool):
            missed_from_filter = missed_value
    missed_legs_only = (
        missed_from_filter
        if missed_from_filter is not None
        else audit_report.selected_leg_count > 0
        and audit_report.selected_leg_count == audit_report.missed_leg_count
    )
    if missed_legs_only:
        source_surface_kind = "missed_leg_loss_driver_surface"
    elif isinstance(target_filter, dict):
        source_surface_kind = "prematch_replacement_surface"
    else:
        source_surface_kind = "unknown_replacement_surface"
    return {
        "source_surface_kind": source_surface_kind,
        "missed_legs_only": missed_legs_only,
        "runtime_candidate_surface_allowed": source_surface_kind
        == "prematch_replacement_surface"
        and not missed_legs_only,
    }


def _search_plans_from_groups(
    groups: Sequence[HistoricalReplacementCalibrationGroup],
    *,
    source_surface_kind: object,
    source_surface_missed_legs_only: bool,
    runtime_candidate_surface_allowed: bool,
    options: HistoricalReplacementCalibrationSegmentOptions,
) -> list[HistoricalReplacementCalibrationSearchPlan]:
    plans: list[HistoricalReplacementCalibrationSearchPlan] = []
    for group in groups:
        if len(plans) >= options.max_search_plans:
            break
        parsed = _parse_profile_group_key(group.group_key)
        if parsed is None:
            continue
        if group.decision not in {"calibration_candidate", "watchlist"}:
            continue
        competition_id, odds_band, hit_probability_delta_band = parsed
        odds_constraints = _odds_band_constraints(odds_band)
        hit_probability_constraints = _hit_probability_delta_constraints(
            hit_probability_delta_band
        )
        required_next_gates = [
            "replacement_shadow_rerank",
            "competition_gate",
            "final_answer_gate",
            "suite_gate",
            "runtime_shadow_replay",
            "rolling_admission",
        ]
        if source_surface_missed_legs_only:
            required_next_gates.insert(0, "full_prematch_surface_audit")
        search_args = _clean_search_args(
            {
                "focus_competition_ids": [competition_id],
                "min_replacement_probability": odds_constraints.get(
                    "min_replacement_probability"
                ),
                "max_replacement_probability": odds_constraints.get(
                    "max_replacement_probability"
                ),
                "min_replacement_decimal_odds": odds_constraints.get(
                    "min_replacement_decimal_odds"
                ),
                "max_replacement_decimal_odds": odds_constraints.get(
                    "max_replacement_decimal_odds"
                ),
                "min_candidate_hit_probability_delta_vs_model_top": (
                    hit_probability_constraints.get(
                        "min_candidate_hit_probability_delta_vs_model_top"
                    )
                ),
                "max_candidate_hit_probability_delta_vs_model_top": (
                    hit_probability_constraints.get(
                        "max_candidate_hit_probability_delta_vs_model_top"
                    )
                ),
                "min_decimal_odds_delta_vs_model_top": 0.0,
                "min_actual_best_profit_loss_delta": 0.0,
                "min_profit_loss_gap": 0.0,
            }
        )
        summary = {
            "calculation_basis": "historical_replacement_calibration_search_plan_v3_1",
            "source_group_key": group.group_key,
            "source_decision": group.decision,
            "source_surface_kind": source_surface_kind,
            "runtime_candidate_surface_allowed": runtime_candidate_surface_allowed,
            "search_args": search_args,
        }
        plan_key = _digest_key("historical_replacement_calibration_search_plan", summary)
        plans.append(
            HistoricalReplacementCalibrationSearchPlan(
                plan_key=plan_key,
                status=(
                    "search_ready"
                    if group.decision == "calibration_candidate"
                    else "watchlist"
                ),
                source_group_key=group.group_key,
                source_group_type=group.group_type,
                source_decision=group.decision,
                source_surface_kind=str(source_surface_kind),
                source_surface_missed_legs_only=source_surface_missed_legs_only,
                runtime_candidate_surface_allowed=runtime_candidate_surface_allowed,
                competition_ids=[competition_id],
                replacement_odds_band=odds_band,
                hit_probability_delta_band=hit_probability_delta_band,
                min_replacement_probability=_optional_float(
                    odds_constraints.get("min_replacement_probability")
                ),
                max_replacement_probability=_optional_float(
                    odds_constraints.get("max_replacement_probability")
                ),
                min_replacement_decimal_odds=_optional_float(
                    odds_constraints.get("min_replacement_decimal_odds")
                ),
                max_replacement_decimal_odds=_optional_float(
                    odds_constraints.get("max_replacement_decimal_odds")
                ),
                min_candidate_hit_probability_delta_vs_model_top=_optional_float(
                    hit_probability_constraints.get(
                        "min_candidate_hit_probability_delta_vs_model_top"
                    )
                ),
                max_candidate_hit_probability_delta_vs_model_top=_optional_float(
                    hit_probability_constraints.get(
                        "max_candidate_hit_probability_delta_vs_model_top"
                    )
                ),
                observation_count=group.observation_count,
                simulated_actual_hit_delta_count_vs_model_top=(
                    group.simulated_actual_hit_delta_count_vs_model_top
                ),
                replacement_leg_hit_delta_count_vs_model_top=(
                    group.replacement_leg_hit_delta_count_vs_model_top
                ),
                average_profit_loss_delta_vs_model_top=(
                    group.average_profit_loss_delta_vs_model_top
                ),
                average_hit_probability_delta_vs_model_top=(
                    group.average_hit_probability_delta_vs_model_top
                ),
                average_replacement_probability=group.average_replacement_probability,
                average_replacement_decimal_odds=group.average_replacement_decimal_odds,
                average_replacement_model_edge=group.average_replacement_model_edge,
                required_next_gates=required_next_gates,
                search_args_json=search_args,
                summary_json={**summary, "plan_key": plan_key},
            )
        )
    return plans


def _recommended_next_action(
    search_plans: Sequence[HistoricalReplacementCalibrationSearchPlan],
    *,
    source_surface_kind: object,
    runtime_candidate_surface_allowed: bool,
) -> dict[str, object]:
    if not search_plans:
        return {
            "action": "review_replacement_candidate_surface",
            "source_surface_kind": source_surface_kind,
        }
    best_plan = search_plans[0]
    if not runtime_candidate_surface_allowed:
        return {
            "action": "rerun_on_full_prematch_surface_before_runtime_gate",
            "source_surface_kind": source_surface_kind,
            "next_plan_key": best_plan.plan_key,
            "next_source_group_key": best_plan.source_group_key,
            "required_next_gates": best_plan.required_next_gates,
        }
    return {
        "action": "run_replacement_shadow_rerank_from_search_plan",
        "source_surface_kind": source_surface_kind,
        "next_plan_key": best_plan.plan_key,
        "next_source_group_key": best_plan.source_group_key,
        "search_args": best_plan.search_args_json,
        "required_next_gates": best_plan.required_next_gates,
    }


def _parse_profile_group_key(group_key: str) -> tuple[str, str, str] | None:
    prefix = "profile:"
    if not group_key.startswith(prefix):
        return None
    parts = group_key[len(prefix) :].split("|")
    if len(parts) != 3:
        return None
    competition_id, odds_band, hit_probability_delta_band = parts
    if not competition_id or not odds_band or not hit_probability_delta_band:
        return None
    return competition_id, odds_band, hit_probability_delta_band


def _odds_band_constraints(odds_band: str) -> dict[str, float | None]:
    if odds_band == "short":
        return {
            "min_replacement_probability": 0.55,
            "max_replacement_decimal_odds": 1.75,
        }
    if odds_band == "medium":
        return {
            "min_replacement_probability": 0.35,
            "min_replacement_decimal_odds": 1.75,
            "max_replacement_decimal_odds": 2.30,
        }
    if odds_band == "value":
        return {
            "min_replacement_probability": 0.25,
            "min_replacement_decimal_odds": 2.30,
            "max_replacement_decimal_odds": 3.20,
        }
    if odds_band == "long":
        return {
            "min_replacement_decimal_odds": 3.20,
        }
    return {}


def _hit_probability_delta_constraints(
    hit_probability_delta_band: str,
) -> dict[str, float | None]:
    if hit_probability_delta_band == "non_regressing":
        return {
            "min_candidate_hit_probability_delta_vs_model_top": 0.0,
            "max_candidate_hit_probability_delta_vs_model_top": 0.10,
        }
    if hit_probability_delta_band == "tiny_deficit":
        return {
            "min_candidate_hit_probability_delta_vs_model_top": -0.005,
            "max_candidate_hit_probability_delta_vs_model_top": 0.0,
        }
    if hit_probability_delta_band == "small_deficit":
        return {
            "min_candidate_hit_probability_delta_vs_model_top": -0.01,
            "max_candidate_hit_probability_delta_vs_model_top": -0.005,
        }
    if hit_probability_delta_band == "medium_deficit":
        return {
            "min_candidate_hit_probability_delta_vs_model_top": -0.02,
            "max_candidate_hit_probability_delta_vs_model_top": -0.01,
        }
    if hit_probability_delta_band == "large_deficit":
        return {
            "min_candidate_hit_probability_delta_vs_model_top": -1.0,
            "max_candidate_hit_probability_delta_vs_model_top": -0.02,
        }
    return {}


def _clean_search_args(values: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Diagnose replacement calibration segments from marginal audits."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-actual-best-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-group-sample-size", type=int, default=3)
    parser.add_argument("--min-average-profit-loss-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--max-average-hit-probability-delta-vs-model-top", type=float, default=0.0)
    parser.add_argument("--min-simulated-actual-hit-delta-count-vs-model-top", type=int, default=0)
    parser.add_argument("--min-replacement-leg-hit-delta-count-vs-model-top", type=int, default=0)
    parser.add_argument("--include-profile-groups", action="store_true", default=True)
    parser.add_argument(
        "--no-include-profile-groups",
        action="store_false",
        dest="include_profile_groups",
    )
    parser.add_argument("--max-report-groups", type=int, default=120)
    parser.add_argument("--max-report-observations", type=int, default=80)
    parser.add_argument("--max-search-plans", type=int, default=12)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementCalibrationSegmentOptions:
    return HistoricalReplacementCalibrationSegmentOptions(
        min_actual_best_profit_loss_delta=args.min_actual_best_profit_loss_delta,
        min_profit_loss_delta_vs_model_top=args.min_profit_loss_delta_vs_model_top,
        min_group_sample_size=args.min_group_sample_size,
        min_average_profit_loss_delta_vs_model_top=(
            args.min_average_profit_loss_delta_vs_model_top
        ),
        max_average_hit_probability_delta_vs_model_top=(
            args.max_average_hit_probability_delta_vs_model_top
        ),
        min_simulated_actual_hit_delta_count_vs_model_top=(
            args.min_simulated_actual_hit_delta_count_vs_model_top
        ),
        min_replacement_leg_hit_delta_count_vs_model_top=(
            args.min_replacement_leg_hit_delta_count_vs_model_top
        ),
        include_profile_groups=args.include_profile_groups,
        max_report_groups=args.max_report_groups,
        max_report_observations=args.max_report_observations,
        max_search_plans=args.max_search_plans,
    )


def _probability_band(value: float) -> str:
    if value < 0.25:
        return "very_low"
    if value < 0.35:
        return "low"
    if value < 0.45:
        return "medium_low"
    if value < 0.55:
        return "medium"
    return "high"


def _odds_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 1.75:
        return "short"
    if value < 2.30:
        return "medium"
    if value < 3.20:
        return "value"
    return "long"


def _model_edge_band(value: float) -> str:
    if value < -0.03:
        return "negative_high"
    if value < -0.01:
        return "negative"
    if value <= 0.01:
        return "neutral"
    if value <= 0.03:
        return "positive"
    return "positive_high"


def _hit_probability_delta_band(value: float) -> str:
    if value >= 0:
        return "non_regressing"
    if value >= -0.005:
        return "tiny_deficit"
    if value >= -0.01:
        return "small_deficit"
    if value >= -0.02:
        return "medium_deficit"
    return "large_deficit"


def _rank_band(rank: int) -> str:
    if rank <= 2:
        return "top_2"
    if rank <= 5:
        return "rank_3_to_5"
    return "rank_6_plus"


def _decimal_odds_delta(
    left: HistoricalCandidateReplacementSimulation,
    right: HistoricalCandidateReplacementSimulation,
) -> float | None:
    if left.replacement_decimal_odds is None or right.replacement_decimal_odds is None:
        return None
    return left.replacement_decimal_odds - right.replacement_decimal_odds


def _decision_rank(decision: str) -> int:
    return {
        "calibration_candidate": 3,
        "watchlist": 2,
        "rejected": 1,
    }.get(decision, 0)


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _report_key(
    summary: dict[str, object],
    groups: Sequence[HistoricalReplacementCalibrationGroup],
    observations: Sequence[HistoricalReplacementCalibrationObservation],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "groups": [
                {
                    "group_key": group.group_key,
                    "decision": group.decision,
                    "observation_count": group.observation_count,
                }
                for group in groups
            ],
            "observations": [
                {
                    "observation_key": observation.observation_key,
                    "profit_loss_delta_vs_model_top": (
                        observation.profit_loss_delta_vs_model_top
                    ),
                }
                for observation in observations
            ],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_calibration_segments:{digest}"


def _digest_key(prefix: str, payload: dict[str, object]) -> str:
    body = dumps(payload, sort_keys=True, default=str)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
