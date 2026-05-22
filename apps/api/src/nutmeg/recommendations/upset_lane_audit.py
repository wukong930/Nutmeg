from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.final_arbitrator import score_final_answer_option
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    _leg_matches_actual_outcome,
    _rank_historical_final_answer_options,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationMode,
    RecommendationStrategy,
)
from nutmeg.recommendations.upset_policy import analyze_candidate_upset_signal

type HistoricalUpsetLaneAuditStatus = Literal["selected", "near_miss", "failed"]
type HistoricalUpsetLaneComparisonOutcome = Literal[
    "actual_improved",
    "actual_unchanged",
    "actual_harmed",
    "no_comparison",
]
type HistoricalUpsetLaneAuditGroupType = Literal[
    "status",
    "comparison_outcome",
    "competition",
    "competition_season",
    "probability_band",
    "odds_band",
    "model_edge_band",
    "score_gap_band",
    "profile",
]
type HistoricalUpsetLaneProfileDecision = Literal[
    "profile_candidate",
    "monitor",
    "rejected",
]


class HistoricalUpsetLaneCandidateAudit(BaseModel):
    fixture_id: str
    market_type: str
    outcome: str
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float | None = Field(default=None, gt=1.0)
    model_edge: float
    data_quality_score: float = Field(ge=0.0, le=100.0)
    calibration_score: float = Field(ge=0.0, le=1.0)
    model_confidence_score: float = Field(ge=0.0, le=1.0)
    odds_stability_score: float = Field(ge=0.0, le=1.0)
    volatility_penalty: float = Field(ge=0.0, le=1.0)
    protection_score: float = Field(ge=0.0, le=1.0)
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    avoidance_penalty: float = Field(ge=0.0, le=1.0)
    direction: str
    leg_actual_hit: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)


class HistoricalUpsetLaneAuditObservation(BaseModel):
    observation_key: str
    slice_id: str
    competition_id: str
    season: str | None = None
    status: HistoricalUpsetLaneAuditStatus
    comparison_outcome: HistoricalUpsetLaneComparisonOutcome
    lane_scenario_key: str
    final_answer_scenario_key: str | None = None
    comparison_scenario_key: str | None = None
    lane_rank: int | None = Field(default=None, ge=1)
    ranked_option_count: int = Field(default=0, ge=0)
    lane_candidate_count: int = Field(default=0, ge=0)
    lane_selected_fixture_ids: list[str] = Field(default_factory=list)
    lane_selected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    comparison_selected_fixture_ids: list[str] = Field(default_factory=list)
    comparison_selected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    lane_actual_hit: bool | None = None
    comparison_actual_hit: bool | None = None
    actual_hit_delta: int | None = None
    lane_actual_return: float | None = Field(default=None, ge=0.0)
    comparison_actual_return: float | None = Field(default=None, ge=0.0)
    actual_return_delta: float | None = None
    lane_profit_loss: float | None = None
    comparison_profit_loss: float | None = None
    profit_loss_delta: float | None = None
    lane_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    comparison_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    hit_probability_delta: float | None = None
    lane_roi: float | None = None
    comparison_roi: float | None = None
    roi_delta: float | None = None
    lane_brier_score: float | None = Field(default=None, ge=0.0)
    comparison_brier_score: float | None = Field(default=None, ge=0.0)
    brier_score_delta: float | None = None
    lane_log_loss: float | None = Field(default=None, ge=0.0)
    comparison_log_loss: float | None = Field(default=None, ge=0.0)
    log_loss_delta: float | None = None
    lane_calibration_error: float | None = Field(default=None, ge=0.0)
    comparison_calibration_error: float | None = Field(default=None, ge=0.0)
    calibration_error_delta: float | None = None
    lane_final_answer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    comparison_final_answer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_score_gap: float | None = None
    average_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_model_edge: float | None = None
    average_data_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    average_calibration_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_model_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_odds_stability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_volatility_penalty: float | None = Field(default=None, ge=0.0, le=1.0)
    max_protection_score: float | None = Field(default=None, ge=0.0, le=1.0)
    candidates: list[HistoricalUpsetLaneCandidateAudit] = Field(default_factory=list)
    error_message: str | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalUpsetLaneAuditOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    focus_competition_ids: tuple[str, ...] = ()
    min_group_sample_size: int = Field(default=1, ge=1)
    top_case_limit: int = Field(default=10, ge=1, le=100)
    min_profile_candidate_sample_size: int = Field(default=3, ge=1)
    min_profile_candidate_improvement_rate: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
    )
    max_profile_candidate_harm_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    min_profile_candidate_average_profit_loss_delta: float = 0.0
    min_profile_candidate_average_hit_probability_delta: float | None = Field(
        default=-0.20,
        ge=-1.0,
        le=1.0,
    )
    max_profile_candidate_average_brier_score_delta: float | None = None
    max_profile_candidate_average_log_loss_delta: float | None = None
    max_profile_candidate_average_calibration_error_delta: float | None = None


class HistoricalUpsetLaneAuditGroup(BaseModel):
    group_key: str
    group_type: HistoricalUpsetLaneAuditGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    observation_count: int = Field(default=0, ge=0)
    selected_count: int = Field(default=0, ge=0)
    near_miss_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    actual_improvement_count: int = Field(default=0, ge=0)
    actual_harm_count: int = Field(default=0, ge=0)
    actual_unchanged_count: int = Field(default=0, ge=0)
    improvement_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    harm_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_lane_candidate_count: float | None = Field(default=None, ge=0.0)
    average_profit_loss_delta: float | None = None
    average_hit_probability_delta: float | None = None
    average_brier_score_delta: float | None = None
    average_log_loss_delta: float | None = None
    average_calibration_error_delta: float | None = None
    average_final_answer_score_gap: float | None = None
    decision: HistoricalUpsetLaneProfileDecision = "monitor"
    reason_codes: list[str] = Field(default_factory=list)
    observation_keys: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalUpsetLaneAuditReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    evaluated_slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    completed_lane_count: int = Field(default=0, ge=0)
    selected_lane_count: int = Field(default=0, ge=0)
    near_miss_count: int = Field(default=0, ge=0)
    failed_lane_count: int = Field(default=0, ge=0)
    lane_candidate_count: int = Field(default=0, ge=0)
    actual_improvement_count: int = Field(default=0, ge=0)
    actual_harm_count: int = Field(default=0, ge=0)
    actual_unchanged_count: int = Field(default=0, ge=0)
    average_profit_loss_delta: float | None = None
    average_hit_probability_delta: float | None = None
    average_final_answer_score_gap: float | None = None
    observations: list[HistoricalUpsetLaneAuditObservation] = Field(default_factory=list)
    groups: list[HistoricalUpsetLaneAuditGroup] = Field(default_factory=list)
    top_near_miss_improvement_cases: list[HistoricalUpsetLaneAuditObservation] = (
        Field(default_factory=list)
    )
    top_selected_cases: list[HistoricalUpsetLaneAuditObservation] = Field(
        default_factory=list
    )
    top_harm_cases: list[HistoricalUpsetLaneAuditObservation] = Field(default_factory=list)
    profile_candidate_count: int = Field(default=0, ge=0)
    profile_candidates: list[HistoricalUpsetLaneAuditGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass
class _GroupAccumulator:
    group_key: str
    group_type: HistoricalUpsetLaneAuditGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    observation_keys: set[str] | None = None
    observation_count: int = 0
    selected_count: int = 0
    near_miss_count: int = 0
    failed_count: int = 0
    actual_improvement_count: int = 0
    actual_harm_count: int = 0
    actual_unchanged_count: int = 0
    lane_candidate_count_sum: float = 0.0
    profit_loss_delta_sum: float = 0.0
    profit_loss_delta_count: int = 0
    hit_probability_delta_sum: float = 0.0
    hit_probability_delta_count: int = 0
    brier_score_delta_sum: float = 0.0
    brier_score_delta_count: int = 0
    log_loss_delta_sum: float = 0.0
    log_loss_delta_count: int = 0
    calibration_error_delta_sum: float = 0.0
    calibration_error_delta_count: int = 0
    final_answer_score_gap_sum: float = 0.0
    final_answer_score_gap_count: int = 0

    def add(self, observation: HistoricalUpsetLaneAuditObservation) -> None:
        if self.observation_keys is None:
            self.observation_keys = set()
        self.observation_keys.add(observation.observation_key)
        self.observation_count += 1
        self.selected_count += int(observation.status == "selected")
        self.near_miss_count += int(observation.status == "near_miss")
        self.failed_count += int(observation.status == "failed")
        self.actual_improvement_count += int(
            observation.comparison_outcome == "actual_improved"
        )
        self.actual_harm_count += int(
            observation.comparison_outcome == "actual_harmed"
        )
        self.actual_unchanged_count += int(
            observation.comparison_outcome == "actual_unchanged"
        )
        self.lane_candidate_count_sum += observation.lane_candidate_count
        if observation.profit_loss_delta is not None:
            self.profit_loss_delta_sum += observation.profit_loss_delta
            self.profit_loss_delta_count += 1
        if observation.hit_probability_delta is not None:
            self.hit_probability_delta_sum += observation.hit_probability_delta
            self.hit_probability_delta_count += 1
        if observation.brier_score_delta is not None:
            self.brier_score_delta_sum += observation.brier_score_delta
            self.brier_score_delta_count += 1
        if observation.log_loss_delta is not None:
            self.log_loss_delta_sum += observation.log_loss_delta
            self.log_loss_delta_count += 1
        if observation.calibration_error_delta is not None:
            self.calibration_error_delta_sum += observation.calibration_error_delta
            self.calibration_error_delta_count += 1
        if observation.final_answer_score_gap is not None:
            self.final_answer_score_gap_sum += observation.final_answer_score_gap
            self.final_answer_score_gap_count += 1

    def group(
        self,
        *,
        options: HistoricalUpsetLaneAuditOptions,
    ) -> HistoricalUpsetLaneAuditGroup:
        improvement_rate = _ratio(
            self.actual_improvement_count,
            self.observation_count,
        )
        harm_rate = _ratio(self.actual_harm_count, self.observation_count)
        average_profit_loss_delta = _ratio(
            self.profit_loss_delta_sum,
            self.profit_loss_delta_count,
        )
        average_hit_probability_delta = _ratio(
            self.hit_probability_delta_sum,
            self.hit_probability_delta_count,
        )
        average_brier_score_delta = _ratio(
            self.brier_score_delta_sum,
            self.brier_score_delta_count,
        )
        average_log_loss_delta = _ratio(
            self.log_loss_delta_sum,
            self.log_loss_delta_count,
        )
        average_calibration_error_delta = _ratio(
            self.calibration_error_delta_sum,
            self.calibration_error_delta_count,
        )
        decision, reason_codes = _profile_decision(
            self,
            options=options,
            improvement_rate=improvement_rate,
            harm_rate=harm_rate,
            average_profit_loss_delta=average_profit_loss_delta,
            average_hit_probability_delta=average_hit_probability_delta,
            average_brier_score_delta=average_brier_score_delta,
            average_log_loss_delta=average_log_loss_delta,
            average_calibration_error_delta=average_calibration_error_delta,
        )
        return HistoricalUpsetLaneAuditGroup(
            group_key=self.group_key,
            group_type=self.group_type,
            label=self.label,
            competition_id=self.competition_id,
            season=self.season,
            observation_count=self.observation_count,
            selected_count=self.selected_count,
            near_miss_count=self.near_miss_count,
            failed_count=self.failed_count,
            actual_improvement_count=self.actual_improvement_count,
            actual_harm_count=self.actual_harm_count,
            actual_unchanged_count=self.actual_unchanged_count,
            improvement_rate=improvement_rate,
            harm_rate=harm_rate,
            average_lane_candidate_count=_ratio(
                self.lane_candidate_count_sum,
                self.observation_count,
            ),
            average_profit_loss_delta=average_profit_loss_delta,
            average_hit_probability_delta=average_hit_probability_delta,
            average_brier_score_delta=average_brier_score_delta,
            average_log_loss_delta=average_log_loss_delta,
            average_calibration_error_delta=average_calibration_error_delta,
            average_final_answer_score_gap=_ratio(
                self.final_answer_score_gap_sum,
                self.final_answer_score_gap_count,
            ),
            decision=decision,
            reason_codes=reason_codes,
            observation_keys=sorted(self.observation_keys or set()),
            summary_json={
                "selected_rate": _ratio(self.selected_count, self.observation_count),
                "near_miss_rate": _ratio(self.near_miss_count, self.observation_count),
                "failed_rate": _ratio(self.failed_count, self.observation_count),
                "actual_improvement_rate": improvement_rate,
                "actual_harm_rate": harm_rate,
                "decision": decision,
                "reason_codes": reason_codes,
            },
        )


def build_historical_upset_lane_audit_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalUpsetLaneAuditOptions | None = None,
) -> HistoricalUpsetLaneAuditReport:
    resolved_options = options or HistoricalUpsetLaneAuditOptions()
    backtest_options = resolved_options.backtest_options
    warnings: list[str] = []
    observations: list[HistoricalUpsetLaneAuditObservation] = []
    included_competition_ids: set[str] = set()

    for historical_slice in historical_slices:
        if not _include_competition(historical_slice, options=resolved_options):
            continue
        backtest = run_historical_recommendation_backtest(
            historical_slice,
            options=backtest_options,
        )
        warnings.extend(backtest.warnings)
        included_competition_ids.add(historical_slice.metadata.competition_id)
        observations.append(
            _audit_observation_for_slice(
                historical_slice,
                scenarios=backtest.scenarios,
                final_answer=backtest.final_answer,
                options=backtest_options,
            )
        )

    groups = _audit_groups(observations, options=resolved_options)
    profile_candidates = _top_profile_candidates(
        groups,
        limit=resolved_options.top_case_limit,
    )
    completed = [
        observation
        for observation in observations
        if observation.status in {"selected", "near_miss"}
    ]
    lane_candidate_count = sum(
        observation.lane_candidate_count for observation in observations
    )
    actual_improvement_count = sum(
        1
        for observation in observations
        if observation.comparison_outcome == "actual_improved"
    )
    actual_harm_count = sum(
        1
        for observation in observations
        if observation.comparison_outcome == "actual_harmed"
    )
    actual_unchanged_count = sum(
        1
        for observation in observations
        if observation.comparison_outcome == "actual_unchanged"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_upset_lane_audit_v3_1",
        "slice_count": len(historical_slices),
        "evaluated_slice_count": len(observations),
        "competition_count": len(included_competition_ids),
        "completed_lane_count": len(completed),
        "selected_lane_count": sum(
            1 for observation in observations if observation.status == "selected"
        ),
        "near_miss_count": sum(
            1 for observation in observations if observation.status == "near_miss"
        ),
        "failed_lane_count": sum(
            1 for observation in observations if observation.status == "failed"
        ),
        "lane_candidate_count": lane_candidate_count,
        "actual_improvement_count": actual_improvement_count,
        "actual_harm_count": actual_harm_count,
        "actual_unchanged_count": actual_unchanged_count,
        "average_profit_loss_delta": _average_optional(
            observation.profit_loss_delta for observation in observations
        ),
        "average_hit_probability_delta": _average_optional(
            observation.hit_probability_delta for observation in observations
        ),
        "average_final_answer_score_gap": _average_optional(
            observation.final_answer_score_gap for observation in observations
        ),
        "profile_candidate_count": len(profile_candidates),
        "profile_candidate_group_keys": [
            group.group_key for group in profile_candidates
        ],
        "profile_candidate_thresholds": {
            "min_sample_size": resolved_options.min_profile_candidate_sample_size,
            "min_improvement_rate": (
                resolved_options.min_profile_candidate_improvement_rate
            ),
            "max_harm_rate": resolved_options.max_profile_candidate_harm_rate,
            "min_average_profit_loss_delta": (
                resolved_options.min_profile_candidate_average_profit_loss_delta
            ),
            "min_average_hit_probability_delta": (
                resolved_options.min_profile_candidate_average_hit_probability_delta
            ),
            "max_average_brier_score_delta": (
                resolved_options.max_profile_candidate_average_brier_score_delta
            ),
            "max_average_log_loss_delta": (
                resolved_options.max_profile_candidate_average_log_loss_delta
            ),
            "max_average_calibration_error_delta": (
                resolved_options.max_profile_candidate_average_calibration_error_delta
            ),
        },
        "backtest_options": backtest_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, observations)
    return HistoricalUpsetLaneAuditReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        evaluated_slice_count=len(observations),
        competition_count=len(included_competition_ids),
        completed_lane_count=cast(int, summary["completed_lane_count"]),
        selected_lane_count=cast(int, summary["selected_lane_count"]),
        near_miss_count=cast(int, summary["near_miss_count"]),
        failed_lane_count=cast(int, summary["failed_lane_count"]),
        lane_candidate_count=lane_candidate_count,
        actual_improvement_count=actual_improvement_count,
        actual_harm_count=actual_harm_count,
        actual_unchanged_count=actual_unchanged_count,
        average_profit_loss_delta=cast(float | None, summary["average_profit_loss_delta"]),
        average_hit_probability_delta=cast(
            float | None,
            summary["average_hit_probability_delta"],
        ),
        average_final_answer_score_gap=cast(
            float | None,
            summary["average_final_answer_score_gap"],
        ),
        observations=observations,
        groups=groups,
        top_near_miss_improvement_cases=_top_near_miss_improvement_cases(
            observations,
            limit=resolved_options.top_case_limit,
        ),
        top_selected_cases=_top_selected_cases(
            observations,
            limit=resolved_options.top_case_limit,
        ),
        top_harm_cases=_top_harm_cases(
            observations,
            limit=resolved_options.top_case_limit,
        ),
        profile_candidate_count=len(profile_candidates),
        profile_candidates=profile_candidates,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_upset_lane_audit_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
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


def _audit_observation_for_slice(
    historical_slice: HistoricalRecommendationSlice,
    *,
    scenarios: Sequence[HistoricalRecommendationScenarioResult],
    final_answer: HistoricalRecommendationScenarioResult | None,
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalUpsetLaneAuditObservation:
    lane_result = _lane_result(scenarios)
    lane_scenario_key = (
        lane_result.scenario.scenario_key
        if lane_result is not None
        else (
            "upset_lane:"
            f"{options.upset_final_answer_lane_pass_type}:"
            f"{options.upset_final_answer_lane_mode}"
        )
    )
    if lane_result is None or lane_result.status == "failed" or lane_result.option is None:
        return _failed_observation(
            historical_slice,
            lane_result=lane_result,
            final_answer=final_answer,
            lane_scenario_key=lane_scenario_key,
        )

    completed_options = [
        result.option
        for result in scenarios
        if result.status == "completed" and result.option is not None
    ]
    ranked_options = _rank_historical_final_answer_options(
        completed_options,
        backtest_options=options,
    )
    lane_rank = _option_rank(lane_result, ranked_options)
    status: HistoricalUpsetLaneAuditStatus = (
        "selected"
        if _same_result_option(lane_result, final_answer)
        else "near_miss"
    )
    comparison = (
        _best_non_lane_result(scenarios, ranked_options)
        if status == "selected"
        else final_answer
    )
    comparison_outcome = _comparison_outcome(lane_result, comparison)
    candidates = _candidate_audits(historical_slice, lane_result)
    lane_score = score_final_answer_option(lane_result.option).final_answer_score
    comparison_score = (
        score_final_answer_option(comparison.option).final_answer_score
        if comparison is not None and comparison.option is not None
        else None
    )
    final_answer_score_gap = (
        comparison_score - lane_score if comparison_score is not None else None
    )
    return HistoricalUpsetLaneAuditObservation(
        observation_key=_observation_key(
            historical_slice.metadata.slice_id,
            lane_scenario_key,
        ),
        slice_id=historical_slice.metadata.slice_id,
        competition_id=historical_slice.metadata.competition_id,
        season=historical_slice.metadata.season,
        status=status,
        comparison_outcome=comparison_outcome,
        lane_scenario_key=lane_scenario_key,
        final_answer_scenario_key=(
            final_answer.scenario.scenario_key if final_answer is not None else None
        ),
        comparison_scenario_key=(
            comparison.scenario.scenario_key if comparison is not None else None
        ),
        lane_rank=lane_rank,
        ranked_option_count=len(ranked_options),
        lane_candidate_count=_lane_candidate_count(lane_result),
        lane_selected_fixture_ids=lane_result.selected_fixture_ids,
        lane_selected_outcomes=lane_result.selected_outcomes,
        comparison_selected_fixture_ids=(
            comparison.selected_fixture_ids if comparison is not None else []
        ),
        comparison_selected_outcomes=(
            comparison.selected_outcomes if comparison is not None else {}
        ),
        lane_actual_hit=lane_result.actual_hit,
        comparison_actual_hit=(
            comparison.actual_hit if comparison is not None else None
        ),
        actual_hit_delta=(
            int(lane_result.actual_hit) - int(comparison.actual_hit)
            if comparison is not None
            else None
        ),
        lane_actual_return=lane_result.actual_return,
        comparison_actual_return=(
            comparison.actual_return if comparison is not None else None
        ),
        actual_return_delta=_optional_delta(
            lane_result.actual_return,
            comparison.actual_return if comparison is not None else None,
        ),
        lane_profit_loss=lane_result.profit_loss,
        comparison_profit_loss=(
            comparison.profit_loss if comparison is not None else None
        ),
        profit_loss_delta=_optional_delta(
            lane_result.profit_loss,
            comparison.profit_loss if comparison is not None else None,
        ),
        lane_hit_probability=lane_result.expected_hit_probability,
        comparison_hit_probability=(
            comparison.expected_hit_probability if comparison is not None else None
        ),
        hit_probability_delta=_optional_delta(
            lane_result.expected_hit_probability,
            comparison.expected_hit_probability if comparison is not None else None,
        ),
        lane_roi=lane_result.roi,
        comparison_roi=comparison.roi if comparison is not None else None,
        roi_delta=_optional_delta(
            lane_result.roi,
            comparison.roi if comparison is not None else None,
        ),
        lane_brier_score=lane_result.brier_score,
        comparison_brier_score=(
            comparison.brier_score if comparison is not None else None
        ),
        brier_score_delta=_optional_delta(
            lane_result.brier_score,
            comparison.brier_score if comparison is not None else None,
        ),
        lane_log_loss=lane_result.log_loss,
        comparison_log_loss=(
            comparison.log_loss if comparison is not None else None
        ),
        log_loss_delta=_optional_delta(
            lane_result.log_loss,
            comparison.log_loss if comparison is not None else None,
        ),
        lane_calibration_error=lane_result.calibration_error,
        comparison_calibration_error=(
            comparison.calibration_error if comparison is not None else None
        ),
        calibration_error_delta=_optional_delta(
            lane_result.calibration_error,
            comparison.calibration_error if comparison is not None else None,
        ),
        lane_final_answer_score=lane_score,
        comparison_final_answer_score=comparison_score,
        final_answer_score_gap=final_answer_score_gap,
        average_probability=_average(candidate.probability for candidate in candidates),
        average_decimal_odds=_average(candidate.decimal_odds for candidate in candidates),
        average_model_edge=_average(candidate.model_edge for candidate in candidates),
        average_data_quality_score=_average(
            candidate.data_quality_score for candidate in candidates
        ),
        average_calibration_score=_average(
            candidate.calibration_score for candidate in candidates
        ),
        average_model_confidence_score=_average(
            candidate.model_confidence_score for candidate in candidates
        ),
        average_odds_stability_score=_average(
            candidate.odds_stability_score for candidate in candidates
        ),
        max_volatility_penalty=max(
            (candidate.volatility_penalty for candidate in candidates),
            default=None,
        ),
        max_protection_score=max(
            (candidate.protection_score for candidate in candidates),
            default=None,
        ),
        candidates=candidates,
        summary_json={
            "lane_option_key": lane_result.option.option_key,
            "comparison_option_key": (
                comparison.option.option_key
                if comparison is not None and comparison.option is not None
                else None
            ),
            "lane_selected_as_final_answer": status == "selected",
            "lane_would_have_improved_actual_profit": (
                comparison_outcome == "actual_improved"
            ),
            "lane_would_have_harmed_actual_profit": (
                comparison_outcome == "actual_harmed"
            ),
        },
    )


def _failed_observation(
    historical_slice: HistoricalRecommendationSlice,
    *,
    lane_result: HistoricalRecommendationScenarioResult | None,
    final_answer: HistoricalRecommendationScenarioResult | None,
    lane_scenario_key: str,
) -> HistoricalUpsetLaneAuditObservation:
    return HistoricalUpsetLaneAuditObservation(
        observation_key=_observation_key(
            historical_slice.metadata.slice_id,
            lane_scenario_key,
        ),
        slice_id=historical_slice.metadata.slice_id,
        competition_id=historical_slice.metadata.competition_id,
        season=historical_slice.metadata.season,
        status="failed",
        comparison_outcome="no_comparison",
        lane_scenario_key=lane_scenario_key,
        final_answer_scenario_key=(
            final_answer.scenario.scenario_key if final_answer is not None else None
        ),
        comparison_scenario_key=(
            final_answer.scenario.scenario_key if final_answer is not None else None
        ),
        ranked_option_count=0,
        error_message=(
            lane_result.error_message
            if lane_result is not None
            else "upset_lane_not_enabled_or_not_generated"
        ),
        summary_json={
            "final_answer_selected_fixture_ids": (
                final_answer.selected_fixture_ids if final_answer is not None else []
            ),
        },
    )


def _candidate_audits(
    historical_slice: HistoricalRecommendationSlice,
    lane_result: HistoricalRecommendationScenarioResult,
) -> list[HistoricalUpsetLaneCandidateAudit]:
    if lane_result.option is None:
        return []
    fixture_by_id = {
        fixture.fixture_id: fixture for fixture in historical_slice.fixtures
    }
    audits: list[HistoricalUpsetLaneCandidateAudit] = []
    for scored in lane_result.option.selection.selected_candidates:
        candidate = scored.candidate
        signal = analyze_candidate_upset_signal(candidate)
        fixture = fixture_by_id.get(candidate.fixture_id)
        leg_actual_hit = (
            _leg_matches_actual_outcome(
                fixture,
                outcome=candidate.outcome,
                market_type=candidate.market_type,
            )
            if fixture is not None
            else None
        )
        audits.append(
            HistoricalUpsetLaneCandidateAudit(
                fixture_id=candidate.fixture_id,
                market_type=candidate.market_type,
                outcome=candidate.outcome,
                probability=candidate.probability,
                decimal_odds=candidate.decimal_odds,
                model_edge=candidate.effective_model_edge(),
                data_quality_score=candidate.data_quality_score,
                calibration_score=candidate.calibration_score,
                model_confidence_score=candidate.model_confidence_score,
                odds_stability_score=candidate.odds_stability_score,
                volatility_penalty=candidate.volatility_penalty,
                protection_score=signal.protection_score,
                favorite_fragility_score=signal.favorite_fragility_score,
                avoidance_penalty=signal.avoidance_penalty,
                direction=signal.direction,
                leg_actual_hit=leg_actual_hit,
                reason_codes=signal.reason_codes,
            )
        )
    return audits


def _audit_groups(
    observations: Sequence[HistoricalUpsetLaneAuditObservation],
    *,
    options: HistoricalUpsetLaneAuditOptions,
) -> list[HistoricalUpsetLaneAuditGroup]:
    accumulators: dict[tuple[str, str], _GroupAccumulator] = {}
    for observation in observations:
        for spec in _group_specs(observation):
            key = (spec.group_type, spec.group_key)
            accumulator = accumulators.get(key)
            if accumulator is None:
                accumulator = _GroupAccumulator(**spec.model_dump())
                accumulators[key] = accumulator
            accumulator.add(observation)
    groups = [
        accumulator.group(options=options)
        for accumulator in accumulators.values()
        if accumulator.observation_count >= options.min_group_sample_size
    ]
    return sorted(
        groups,
        key=lambda group: (
            group.decision == "profile_candidate",
            group.actual_improvement_count,
            -group.actual_harm_count,
            group.near_miss_count,
            group.selected_count,
            group.observation_count,
            group.group_key,
        ),
        reverse=True,
    )


def _profile_decision(
    accumulator: _GroupAccumulator,
    *,
    options: HistoricalUpsetLaneAuditOptions,
    improvement_rate: float | None,
    harm_rate: float | None,
    average_profit_loss_delta: float | None,
    average_hit_probability_delta: float | None,
    average_brier_score_delta: float | None,
    average_log_loss_delta: float | None,
    average_calibration_error_delta: float | None,
) -> tuple[HistoricalUpsetLaneProfileDecision, list[str]]:
    if accumulator.group_type != "profile":
        return "monitor", ["not_composite_profile_group"]

    reason_codes: list[str] = []
    if accumulator.observation_count < options.min_profile_candidate_sample_size:
        reason_codes.append("sample_size_below_threshold")
    if improvement_rate is None or (
        improvement_rate < options.min_profile_candidate_improvement_rate
    ):
        reason_codes.append("improvement_rate_below_threshold")
    if harm_rate is None or harm_rate > options.max_profile_candidate_harm_rate:
        reason_codes.append("harm_rate_above_threshold")
    if (
        average_profit_loss_delta is None
        or average_profit_loss_delta
        < options.min_profile_candidate_average_profit_loss_delta
    ):
        reason_codes.append("average_profit_loss_delta_below_threshold")
    if (
        options.min_profile_candidate_average_hit_probability_delta is not None
        and (
            average_hit_probability_delta is None
            or average_hit_probability_delta
            < options.min_profile_candidate_average_hit_probability_delta
        )
    ):
        reason_codes.append("average_hit_probability_delta_below_threshold")
    if (
        options.max_profile_candidate_average_brier_score_delta is not None
        and (
            average_brier_score_delta is None
            or average_brier_score_delta
            > options.max_profile_candidate_average_brier_score_delta
        )
    ):
        reason_codes.append("average_brier_score_delta_above_threshold")
    if (
        options.max_profile_candidate_average_log_loss_delta is not None
        and (
            average_log_loss_delta is None
            or average_log_loss_delta
            > options.max_profile_candidate_average_log_loss_delta
        )
    ):
        reason_codes.append("average_log_loss_delta_above_threshold")
    if (
        options.max_profile_candidate_average_calibration_error_delta is not None
        and (
            average_calibration_error_delta is None
            or average_calibration_error_delta
            > options.max_profile_candidate_average_calibration_error_delta
        )
    ):
        reason_codes.append("average_calibration_error_delta_above_threshold")

    if reason_codes:
        return "rejected", reason_codes
    return "profile_candidate", ["profile_candidate_thresholds_satisfied"]


class _GroupSpec(BaseModel):
    group_key: str
    group_type: HistoricalUpsetLaneAuditGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None


def _group_specs(
    observation: HistoricalUpsetLaneAuditObservation,
) -> list[_GroupSpec]:
    specs = [
        _GroupSpec(
            group_key=f"status:{observation.status}",
            group_type="status",
            label=observation.status,
        ),
        _GroupSpec(
            group_key=f"comparison_outcome:{observation.comparison_outcome}",
            group_type="comparison_outcome",
            label=observation.comparison_outcome,
        ),
        _GroupSpec(
            group_key=f"competition:{observation.competition_id}",
            group_type="competition",
            label=observation.competition_id,
            competition_id=observation.competition_id,
        ),
    ]
    if observation.season is not None:
        specs.append(
            _GroupSpec(
                group_key=(
                    f"competition_season:{observation.competition_id}:"
                    f"{observation.season}"
                ),
                group_type="competition_season",
                label=f"{observation.competition_id} {observation.season}",
                competition_id=observation.competition_id,
                season=observation.season,
            )
        )
    specs.extend(
        [
            _GroupSpec(
                group_key=(
                    "probability:"
                    f"{_probability_band(observation.average_probability)}"
                ),
                group_type="probability_band",
                label=_probability_band(observation.average_probability),
            ),
            _GroupSpec(
                group_key=f"odds:{_odds_band(observation.average_decimal_odds)}",
                group_type="odds_band",
                label=_odds_band(observation.average_decimal_odds),
            ),
            _GroupSpec(
                group_key=f"model_edge:{_model_edge_band(observation.average_model_edge)}",
                group_type="model_edge_band",
                label=_model_edge_band(observation.average_model_edge),
            ),
            _GroupSpec(
                group_key=(
                    "score_gap:"
                    f"{_score_gap_band(observation.final_answer_score_gap)}"
                ),
                group_type="score_gap_band",
                label=_score_gap_band(observation.final_answer_score_gap),
            ),
            _GroupSpec(
                group_key="profile:"
                f"{observation.status}:"
                f"{observation.comparison_outcome}:"
                f"{_model_edge_band(observation.average_model_edge)}:"
                f"{_odds_band(observation.average_decimal_odds)}",
                group_type="profile",
                label=" ".join(
                    [
                        observation.status,
                        observation.comparison_outcome,
                        _model_edge_band(observation.average_model_edge),
                        _odds_band(observation.average_decimal_odds),
                    ]
                ),
            ),
        ]
    )
    return specs


def _lane_result(
    scenarios: Sequence[HistoricalRecommendationScenarioResult],
) -> HistoricalRecommendationScenarioResult | None:
    for scenario in scenarios:
        if scenario.scenario.scenario_key.startswith("upset_lane:"):
            return scenario
    return None


def _best_non_lane_result(
    scenarios: Sequence[HistoricalRecommendationScenarioResult],
    ranked_options: Sequence[object],
) -> HistoricalRecommendationScenarioResult | None:
    for option in ranked_options:
        option_key = getattr(option, "option_key", "")
        if isinstance(option_key, str) and option_key.startswith("historical:upset_lane:"):
            continue
        for scenario in scenarios:
            if scenario.option is not None and scenario.option.option_key == option_key:
                return scenario
    return None


def _option_rank(
    lane_result: HistoricalRecommendationScenarioResult,
    ranked_options: Sequence[object],
) -> int | None:
    if lane_result.option is None:
        return None
    for index, option in enumerate(ranked_options, start=1):
        option_key = getattr(option, "option_key", None)
        if option_key == lane_result.option.option_key:
            return index
    return None


def _same_result_option(
    left: HistoricalRecommendationScenarioResult | None,
    right: HistoricalRecommendationScenarioResult | None,
) -> bool:
    if left is None or right is None:
        return False
    if left.option is None or right.option is None:
        return False
    return left.option.option_key == right.option.option_key


def _comparison_outcome(
    lane_result: HistoricalRecommendationScenarioResult,
    comparison: HistoricalRecommendationScenarioResult | None,
) -> HistoricalUpsetLaneComparisonOutcome:
    if comparison is None:
        return "no_comparison"
    delta = lane_result.profit_loss - comparison.profit_loss
    if abs(delta) <= 1e-9:
        return "actual_unchanged"
    return "actual_improved" if delta > 0 else "actual_harmed"


def _lane_candidate_count(result: HistoricalRecommendationScenarioResult) -> int:
    raw = result.selection_diagnostics_json.get("lane_candidate_count")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return 0


def _top_near_miss_improvement_cases(
    observations: Sequence[HistoricalUpsetLaneAuditObservation],
    *,
    limit: int,
) -> list[HistoricalUpsetLaneAuditObservation]:
    return sorted(
        (
            observation
            for observation in observations
            if observation.status == "near_miss"
            and observation.comparison_outcome == "actual_improved"
        ),
        key=lambda observation: (
            observation.profit_loss_delta or 0.0,
            -(observation.final_answer_score_gap or 0.0),
        ),
        reverse=True,
    )[:limit]


def _top_selected_cases(
    observations: Sequence[HistoricalUpsetLaneAuditObservation],
    *,
    limit: int,
) -> list[HistoricalUpsetLaneAuditObservation]:
    return sorted(
        (observation for observation in observations if observation.status == "selected"),
        key=lambda observation: observation.profit_loss_delta or 0.0,
        reverse=True,
    )[:limit]


def _top_harm_cases(
    observations: Sequence[HistoricalUpsetLaneAuditObservation],
    *,
    limit: int,
) -> list[HistoricalUpsetLaneAuditObservation]:
    return sorted(
        (
            observation
            for observation in observations
            if observation.comparison_outcome == "actual_harmed"
        ),
        key=lambda observation: observation.profit_loss_delta or 0.0,
    )[:limit]


def _top_profile_candidates(
    groups: Sequence[HistoricalUpsetLaneAuditGroup],
    *,
    limit: int,
) -> list[HistoricalUpsetLaneAuditGroup]:
    return sorted(
        (group for group in groups if group.decision == "profile_candidate"),
        key=lambda group: (
            group.actual_improvement_count,
            -(group.actual_harm_count),
            group.improvement_rate or 0.0,
            group.average_profit_loss_delta or 0.0,
            group.average_hit_probability_delta or -1.0,
            group.observation_count,
        ),
        reverse=True,
    )[:limit]


def _include_competition(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalUpsetLaneAuditOptions,
) -> bool:
    return (
        not options.focus_competition_ids
        or historical_slice.metadata.competition_id in set(options.focus_competition_ids)
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    resolved_slice_paths = list(args.slice_paths)
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        slices = [*manifest_result.slices, *slices]
        resolved_slice_paths = [
            *manifest_result.resolved_slice_paths,
            *resolved_slice_paths,
        ]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=slices,
        resolved_slice_paths=resolved_slice_paths,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Audit upset final-answer lane selected and near-miss cases."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default="single")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"], default="solver")
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--upset-final-answer-lane", action="store_true")
    parser.add_argument("--upset-final-answer-lane-pass-type", default="1x1")
    parser.add_argument(
        "--upset-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--upset-final-answer-lane-candidate-limit", type=int, default=24)
    parser.add_argument(
        "--upset-final-answer-lane-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-probability",
        type=float,
        default=0.15,
    )
    parser.add_argument("--upset-final-answer-lane-min-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-max-decimal-odds", type=float)
    parser.add_argument("--upset-final-answer-lane-min-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-max-model-edge", type=float)
    parser.add_argument("--upset-final-answer-lane-competitions", default="")
    parser.add_argument("--upset-final-answer-lane-excluded-competitions", default="")
    parser.add_argument(
        "--upset-final-answer-lane-min-calibration-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-model-confidence-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-odds-stability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-max-volatility-penalty", type=float)
    parser.add_argument(
        "--upset-final-answer-lane-max-hit-probability-deficit",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-max-signal-calibration-risk",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-signal-reliability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-score-boost", type=float, default=0.0)
    parser.add_argument("--focus-competitions", default="")
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument("--top-case-limit", type=int, default=10)
    parser.add_argument("--min-profile-candidate-sample-size", type=int, default=3)
    parser.add_argument("--min-profile-candidate-improvement-rate", type=float, default=0.55)
    parser.add_argument("--max-profile-candidate-harm-rate", type=float, default=0.25)
    parser.add_argument(
        "--min-profile-candidate-average-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-profile-candidate-average-hit-probability-delta",
        type=float,
        default=-0.20,
    )
    parser.add_argument("--max-profile-candidate-average-brier-score-delta", type=float)
    parser.add_argument("--max-profile-candidate-average-log-loss-delta", type=float)
    parser.add_argument(
        "--max-profile-candidate-average-calibration-error-delta",
        type=float,
    )
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalUpsetLaneAuditOptions:
    return HistoricalUpsetLaneAuditOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
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
            upset_final_answer_lane=args.upset_final_answer_lane,
            upset_final_answer_lane_pass_type=args.upset_final_answer_lane_pass_type,
            upset_final_answer_lane_mode=cast(
                RecommendationMode,
                args.upset_final_answer_lane_mode,
            ),
            upset_final_answer_lane_candidate_limit=(
                args.upset_final_answer_lane_candidate_limit
            ),
            upset_final_answer_lane_min_protection_score=(
                args.upset_final_answer_lane_min_protection_score
            ),
            upset_final_answer_lane_min_probability=(
                args.upset_final_answer_lane_min_probability
            ),
            upset_final_answer_lane_min_decimal_odds=(
                args.upset_final_answer_lane_min_decimal_odds
            ),
            upset_final_answer_lane_max_decimal_odds=(
                args.upset_final_answer_lane_max_decimal_odds
            ),
            upset_final_answer_lane_min_model_edge=(
                args.upset_final_answer_lane_min_model_edge
            ),
            upset_final_answer_lane_max_model_edge=(
                args.upset_final_answer_lane_max_model_edge
            ),
            upset_final_answer_lane_competition_ids=tuple(
                _csv(args.upset_final_answer_lane_competitions)
            ),
            upset_final_answer_lane_excluded_competition_ids=tuple(
                _csv(args.upset_final_answer_lane_excluded_competitions)
            ),
            upset_final_answer_lane_min_calibration_score=(
                args.upset_final_answer_lane_min_calibration_score
            ),
            upset_final_answer_lane_min_model_confidence_score=(
                args.upset_final_answer_lane_min_model_confidence_score
            ),
            upset_final_answer_lane_min_odds_stability_score=(
                args.upset_final_answer_lane_min_odds_stability_score
            ),
            upset_final_answer_lane_max_volatility_penalty=(
                args.upset_final_answer_lane_max_volatility_penalty
            ),
            upset_final_answer_lane_max_hit_probability_deficit=(
                args.upset_final_answer_lane_max_hit_probability_deficit
            ),
            upset_final_answer_lane_max_signal_calibration_risk=(
                args.upset_final_answer_lane_max_signal_calibration_risk
            ),
            upset_final_answer_lane_min_signal_reliability_score=(
                args.upset_final_answer_lane_min_signal_reliability_score
            ),
            upset_final_answer_lane_score_boost=args.upset_final_answer_lane_score_boost,
        ),
        focus_competition_ids=tuple(_csv(args.focus_competitions)),
        min_group_sample_size=args.min_group_sample_size,
        top_case_limit=args.top_case_limit,
        min_profile_candidate_sample_size=args.min_profile_candidate_sample_size,
        min_profile_candidate_improvement_rate=(
            args.min_profile_candidate_improvement_rate
        ),
        max_profile_candidate_harm_rate=args.max_profile_candidate_harm_rate,
        min_profile_candidate_average_profit_loss_delta=(
            args.min_profile_candidate_average_profit_loss_delta
        ),
        min_profile_candidate_average_hit_probability_delta=(
            args.min_profile_candidate_average_hit_probability_delta
        ),
        max_profile_candidate_average_brier_score_delta=(
            args.max_profile_candidate_average_brier_score_delta
        ),
        max_profile_candidate_average_log_loss_delta=(
            args.max_profile_candidate_average_log_loss_delta
        ),
        max_profile_candidate_average_calibration_error_delta=(
            args.max_profile_candidate_average_calibration_error_delta
        ),
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _observation_key(slice_id: str, scenario_key: str) -> str:
    digest = sha256(f"{slice_id}|{scenario_key}".encode()).hexdigest()[:12]
    return f"historical_upset_lane_audit:{slice_id}:{digest}"


def _report_key(
    summary: dict[str, object],
    observations: Sequence[HistoricalUpsetLaneAuditObservation],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "observation_keys": [
                    observation.observation_key for observation in observations
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_upset_lane_audit:{digest}"


def _optional_delta(
    value: float | None,
    baseline: float | None,
) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _average(values: Iterable[float | None]) -> float | None:
    collected = [value for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _average_optional(values: Iterable[float | None]) -> float | None:
    return _average(values)


def _ratio(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _probability_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.18:
        return "p_lt_0_18"
    if value < 0.20:
        return "p_0_18_0_20"
    if value < 0.24:
        return "p_0_20_0_24"
    return "p_gte_0_24"


def _odds_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 3.5:
        return "odds_lt_3_5"
    if value < 5.0:
        return "odds_3_5_5_0"
    if value < 7.0:
        return "odds_5_0_7_0"
    return "odds_gte_7_0"


def _model_edge_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < -0.02:
        return "edge_lt_neg_0_02"
    if value < -0.01:
        return "edge_neg_0_02_neg_0_01"
    if value < 0.0:
        return "edge_neg_0_01_0"
    if value < 0.02:
        return "edge_0_0_02"
    return "edge_gte_0_02"


def _score_gap_band(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0:
        return "lane_leads"
    if value < 0.02:
        return "gap_lt_0_02"
    if value < 0.05:
        return "gap_0_02_0_05"
    if value < 0.10:
        return "gap_0_05_0_10"
    return "gap_gte_0_10"
