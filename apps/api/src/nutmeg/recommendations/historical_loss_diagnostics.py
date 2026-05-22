from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalFixture,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationStrategy,
)

type HistoricalFinalAnswerLossGroupUnit = Literal[
    "final_answer",
    "selected_leg",
    "missed_leg",
]
type HistoricalFinalAnswerLossGroupType = Literal[
    "competition",
    "competition_season",
    "scenario",
    "correlation_exposure",
    "odds_band",
    "probability_band",
    "model_edge_band",
    "favorite_fragility_band",
    "favorite_flag",
    "correlation_key",
    "kickoff_month",
    "miss_reason",
]


class HistoricalFinalAnswerLossDiagnosticOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    focus_competition_ids: tuple[str, ...] = ()
    min_group_sample_size: int = Field(default=1, ge=1)
    include_positive_roi_competitions: bool = True
    derive_market_context_signals: bool = False
    fragile_favorite_threshold: float = Field(default=0.28, ge=0.0, le=1.0)
    short_price_odds_threshold: float = Field(default=1.60, gt=1.0)
    high_probability_threshold: float = Field(default=0.65, ge=0.0, le=1.0)


class HistoricalFinalAnswerLossDiagnosticGroup(BaseModel):
    group_key: str
    group_type: HistoricalFinalAnswerLossGroupType
    unit: HistoricalFinalAnswerLossGroupUnit
    label: str
    competition_id: str | None = None
    season: str | None = None
    final_answer_sample_size: int = Field(default=0, ge=0)
    final_answer_hit_count: int = Field(default=0, ge=0)
    final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_leg_count: int = Field(default=0, ge=0)
    leg_hit_count: int = Field(default=0, ge=0)
    leg_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    missed_leg_count: int = Field(default=0, ge=0)
    total_stake: float = Field(default=0.0, ge=0.0)
    actual_return: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float | None = None
    average_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_model_edge: float | None = None
    average_favorite_fragility_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    max_correlation_exposure: int = Field(default=0, ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerLossDiagnosticReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    selected_leg_count: int = Field(ge=0)
    missed_leg_count: int = Field(ge=0)
    negative_roi_competitions: list[str] = Field(default_factory=list)
    groups: list[HistoricalFinalAnswerLossDiagnosticGroup] = Field(default_factory=list)
    top_loss_groups: list[HistoricalFinalAnswerLossDiagnosticGroup] = Field(
        default_factory=list
    )
    top_missed_leg_groups: list[HistoricalFinalAnswerLossDiagnosticGroup] = Field(
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


@dataclass(frozen=True)
class _FinalAnswerObservation:
    competition_id: str
    season: str | None
    slice_id: str
    scenario_key: str
    final_answer: HistoricalRecommendationScenarioResult
    max_correlation_exposure: int


@dataclass(frozen=True)
class _LegObservation:
    competition_id: str
    season: str | None
    slice_id: str
    fixture_id: str
    kickoff_time_utc: datetime | None
    scenario_key: str
    candidate: RecommendationCandidate
    actual_1x2_outcome: str | None
    actual_hit: bool


@dataclass
class _GroupAccumulator:
    group_key: str
    group_type: HistoricalFinalAnswerLossGroupType
    unit: HistoricalFinalAnswerLossGroupUnit
    label: str
    competition_id: str | None = None
    season: str | None = None
    final_answer_sample_size: int = 0
    final_answer_hit_count: int = 0
    selected_leg_count: int = 0
    leg_hit_count: int = 0
    missed_leg_count: int = 0
    total_stake: float = 0.0
    actual_return: float = 0.0
    probability_sum: float = 0.0
    probability_count: int = 0
    decimal_odds_sum: float = 0.0
    decimal_odds_count: int = 0
    model_edge_sum: float = 0.0
    model_edge_count: int = 0
    fragility_sum: float = 0.0
    fragility_count: int = 0
    max_correlation_exposure: int = 0

    def add_final_answer(self, observation: _FinalAnswerObservation) -> None:
        self.final_answer_sample_size += 1
        self.final_answer_hit_count += int(observation.final_answer.actual_hit)
        self.total_stake += observation.final_answer.total_stake
        self.actual_return += observation.final_answer.actual_return
        self.max_correlation_exposure = max(
            self.max_correlation_exposure,
            observation.max_correlation_exposure,
        )

    def add_leg(self, observation: _LegObservation) -> None:
        self.selected_leg_count += 1
        self.leg_hit_count += int(observation.actual_hit)
        self.missed_leg_count += int(not observation.actual_hit)
        self.probability_sum += observation.candidate.probability
        self.probability_count += 1
        if observation.candidate.decimal_odds is not None:
            self.decimal_odds_sum += observation.candidate.decimal_odds
            self.decimal_odds_count += 1
        self.model_edge_sum += observation.candidate.effective_model_edge()
        self.model_edge_count += 1
        fragility_score = _favorite_fragility_score(observation.candidate)
        self.fragility_sum += fragility_score
        self.fragility_count += 1

    def group(self) -> HistoricalFinalAnswerLossDiagnosticGroup:
        profit_loss = self.actual_return - self.total_stake
        return HistoricalFinalAnswerLossDiagnosticGroup(
            group_key=self.group_key,
            group_type=self.group_type,
            unit=self.unit,
            label=self.label,
            competition_id=self.competition_id,
            season=self.season,
            final_answer_sample_size=self.final_answer_sample_size,
            final_answer_hit_count=self.final_answer_hit_count,
            final_answer_hit_rate=_ratio(
                self.final_answer_hit_count,
                self.final_answer_sample_size,
            ),
            selected_leg_count=self.selected_leg_count,
            leg_hit_count=self.leg_hit_count,
            leg_hit_rate=_ratio(self.leg_hit_count, self.selected_leg_count),
            missed_leg_count=self.missed_leg_count,
            total_stake=self.total_stake,
            actual_return=self.actual_return,
            profit_loss=profit_loss,
            roi=profit_loss / self.total_stake if self.total_stake > 0 else None,
            average_probability=_ratio(self.probability_sum, self.probability_count),
            average_decimal_odds=_ratio(self.decimal_odds_sum, self.decimal_odds_count),
            average_model_edge=_ratio(self.model_edge_sum, self.model_edge_count),
            average_favorite_fragility_score=_ratio(
                self.fragility_sum,
                self.fragility_count,
            ),
            max_correlation_exposure=self.max_correlation_exposure,
            summary_json={
                "missed_leg_rate": _ratio(
                    self.missed_leg_count,
                    self.selected_leg_count,
                ),
                "loss_per_final_answer": _ratio(
                    -profit_loss if profit_loss < 0 else 0.0,
                    self.final_answer_sample_size,
                ),
            },
        )


def build_historical_final_answer_loss_diagnostic_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerLossDiagnosticOptions | None = None,
) -> HistoricalFinalAnswerLossDiagnosticReport:
    resolved_options = options or HistoricalFinalAnswerLossDiagnosticOptions()
    backtest_options = resolved_options.backtest_options.model_copy(
        update={
            "derive_market_context_signals": resolved_options.derive_market_context_signals,
        }
    )
    final_answer_observations: list[_FinalAnswerObservation] = []
    leg_observations: list[_LegObservation] = []
    warnings: list[str] = []

    for historical_slice in historical_slices:
        if not _include_competition(
            historical_slice.metadata.competition_id,
            options=resolved_options,
        ):
            continue
        backtest = run_historical_recommendation_backtest(
            historical_slice,
            options=backtest_options,
        )
        warnings.extend(backtest.warnings)
        if backtest.final_answer is None:
            warnings.append(
                f"historical_loss_diagnostics:no_final_answer:{historical_slice.metadata.slice_id}"
            )
            continue
        fixture_by_id = {
            fixture.fixture_id: fixture for fixture in historical_slice.fixtures
        }
        final_answer_observations.append(
            _final_answer_observation(
                historical_slice,
                final_answer=backtest.final_answer,
            )
        )
        leg_observations.extend(
            _leg_observations(
                historical_slice,
                final_answer=backtest.final_answer,
                fixture_by_id=fixture_by_id,
            )
        )

    groups = _diagnostic_groups(
        final_answer_observations,
        leg_observations=leg_observations,
        options=resolved_options,
    )
    negative_roi_competitions = _negative_roi_competitions(groups)
    visible_final_answer_observations = _filter_final_answer_observations(
        final_answer_observations,
        negative_roi_competitions=negative_roi_competitions,
        options=resolved_options,
    )
    visible_leg_observations = _filter_leg_observations(
        leg_observations,
        negative_roi_competitions=negative_roi_competitions,
        options=resolved_options,
    )
    visible_groups = _filter_groups(
        groups,
        negative_roi_competitions=negative_roi_competitions,
        options=resolved_options,
    )
    top_loss_groups = _top_loss_groups(visible_groups)
    top_missed_leg_groups = _top_missed_leg_groups(visible_groups)
    summary = _report_summary(
        historical_slices,
        final_answer_observations=visible_final_answer_observations,
        leg_observations=visible_leg_observations,
        groups=visible_groups,
        negative_roi_competitions=negative_roi_competitions,
        warnings=warnings,
        options=resolved_options,
    )
    report_key = _report_key(summary, historical_slices)
    return HistoricalFinalAnswerLossDiagnosticReport(
        report_key=report_key,
        status="generated",
        slice_count=len(
            {
                observation.slice_id
                for observation in visible_final_answer_observations
            }
        ),
        competition_count=len(
            {
                observation.competition_id
                for observation in visible_final_answer_observations
            }
        ),
        final_answer_count=len(visible_final_answer_observations),
        selected_leg_count=len(visible_leg_observations),
        missed_leg_count=sum(
            1
            for observation in visible_leg_observations
            if not observation.actual_hit
        ),
        negative_roi_competitions=negative_roi_competitions,
        groups=visible_groups,
        top_loss_groups=top_loss_groups,
        top_missed_leg_groups=top_missed_leg_groups,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_final_answer_loss_diagnostic_report(
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


def _final_answer_observation(
    historical_slice: HistoricalRecommendationSlice,
    *,
    final_answer: HistoricalRecommendationScenarioResult,
) -> _FinalAnswerObservation:
    return _FinalAnswerObservation(
        competition_id=historical_slice.metadata.competition_id,
        season=historical_slice.metadata.season,
        slice_id=historical_slice.metadata.slice_id,
        scenario_key=final_answer.scenario.scenario_key,
        final_answer=final_answer,
        max_correlation_exposure=_max_correlation_exposure(final_answer),
    )


def _leg_observations(
    historical_slice: HistoricalRecommendationSlice,
    *,
    final_answer: HistoricalRecommendationScenarioResult,
    fixture_by_id: Mapping[str, HistoricalFixture],
) -> list[_LegObservation]:
    if final_answer.option is None:
        return []
    observations: list[_LegObservation] = []
    for scored in final_answer.option.selection.selected_candidates:
        candidate = scored.candidate
        fixture = fixture_by_id.get(candidate.fixture_id)
        observations.append(
            _LegObservation(
                competition_id=historical_slice.metadata.competition_id,
                season=historical_slice.metadata.season,
                slice_id=historical_slice.metadata.slice_id,
                fixture_id=candidate.fixture_id,
                kickoff_time_utc=candidate.kickoff_time_utc,
                scenario_key=final_answer.scenario.scenario_key,
                candidate=candidate,
                actual_1x2_outcome=fixture.actual_1x2_outcome
                if fixture is not None
                else _metadata_string(candidate.metadata_json, "actual_1x2_outcome"),
                actual_hit=_candidate_matches_actual(candidate, fixture=fixture),
            )
        )
    return observations


def _diagnostic_groups(
    final_answer_observations: Sequence[_FinalAnswerObservation],
    *,
    leg_observations: Sequence[_LegObservation],
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> list[HistoricalFinalAnswerLossDiagnosticGroup]:
    accumulators: dict[
        tuple[HistoricalFinalAnswerLossGroupType, HistoricalFinalAnswerLossGroupUnit, str],
        _GroupAccumulator,
    ] = {}
    for final_observation in final_answer_observations:
        for group_type, group_key, label in _final_answer_group_keys(final_observation):
            accumulator = accumulators.setdefault(
                (group_type, "final_answer", group_key),
                _GroupAccumulator(
                    group_key=group_key,
                    group_type=group_type,
                    unit="final_answer",
                    label=label,
                    competition_id=final_observation.competition_id,
                    season=final_observation.season
                    if group_type == "competition_season"
                    else None,
                ),
            )
            accumulator.add_final_answer(final_observation)
    for leg_observation in leg_observations:
        for group_type, group_key, label in _selected_leg_group_keys(leg_observation):
            accumulator = accumulators.setdefault(
                (group_type, "selected_leg", group_key),
                _GroupAccumulator(
                    group_key=group_key,
                    group_type=group_type,
                    unit="selected_leg",
                    label=label,
                    competition_id=leg_observation.competition_id,
                ),
            )
            accumulator.add_leg(leg_observation)
        if not leg_observation.actual_hit:
            for reason in _miss_reason_codes(leg_observation, options=options):
                group_key = f"{leg_observation.competition_id}:{reason}"
                accumulator = accumulators.setdefault(
                    ("miss_reason", "missed_leg", group_key),
                    _GroupAccumulator(
                        group_key=group_key,
                        group_type="miss_reason",
                        unit="missed_leg",
                        label=f"{leg_observation.competition_id} {reason}",
                        competition_id=leg_observation.competition_id,
                    ),
                )
                accumulator.add_leg(leg_observation)
    return sorted(
        (
            accumulator.group()
            for accumulator in accumulators.values()
            if _group_sample_size(accumulator.group()) >= options.min_group_sample_size
        ),
        key=lambda group: (group.group_type, group.unit, group.group_key),
    )


def _final_answer_group_keys(
    observation: _FinalAnswerObservation,
) -> list[tuple[HistoricalFinalAnswerLossGroupType, str, str]]:
    competition_id = observation.competition_id
    season = observation.season or "unknown"
    return [
        ("competition", competition_id, competition_id),
        (
            "competition_season",
            f"{competition_id}:{season}",
            f"{competition_id} {season}",
        ),
        (
            "scenario",
            f"{competition_id}:{observation.scenario_key}",
            f"{competition_id} {observation.scenario_key}",
        ),
        (
            "correlation_exposure",
            f"{competition_id}:{_correlation_exposure_band(observation.max_correlation_exposure)}",
            (
                f"{competition_id} "
                f"{_correlation_exposure_band(observation.max_correlation_exposure)}"
            ),
        ),
    ]


def _selected_leg_group_keys(
    observation: _LegObservation,
) -> list[tuple[HistoricalFinalAnswerLossGroupType, str, str]]:
    competition_id = observation.competition_id
    odds_band = _odds_band(observation.candidate.decimal_odds)
    probability_band = _probability_band(observation.candidate.probability)
    edge_band = _model_edge_band(observation.candidate.effective_model_edge())
    fragility_band = _fragility_band(_favorite_fragility_score(observation.candidate))
    favorite_flag = _favorite_flag(observation.candidate)
    correlation_key = observation.candidate.correlation_key or "uncorrelated"
    kickoff_month = (
        observation.kickoff_time_utc.strftime("%Y-%m")
        if observation.kickoff_time_utc is not None
        else "unknown"
    )
    return [
        ("odds_band", f"{competition_id}:{odds_band}", f"{competition_id} {odds_band}"),
        (
            "probability_band",
            f"{competition_id}:{probability_band}",
            f"{competition_id} {probability_band}",
        ),
        (
            "model_edge_band",
            f"{competition_id}:{edge_band}",
            f"{competition_id} {edge_band}",
        ),
        (
            "favorite_fragility_band",
            f"{competition_id}:{fragility_band}",
            f"{competition_id} {fragility_band}",
        ),
        (
            "favorite_flag",
            f"{competition_id}:{favorite_flag}",
            f"{competition_id} {favorite_flag}",
        ),
        (
            "correlation_key",
            f"{competition_id}:{correlation_key}",
            f"{competition_id} {correlation_key}",
        ),
        (
            "kickoff_month",
            f"{competition_id}:{kickoff_month}",
            f"{competition_id} {kickoff_month}",
        ),
    ]


def _miss_reason_codes(
    observation: _LegObservation,
    *,
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> list[str]:
    candidate = observation.candidate
    reasons: list[str] = ["selected_leg_missed"]
    if _favorite_flag(candidate) == "market_favorite":
        reasons.append("market_favorite_missed")
        if observation.actual_1x2_outcome == "draw":
            reasons.append("favorite_draw_failure")
        elif observation.actual_1x2_outcome in {"home_win", "away_win"}:
            reasons.append("favorite_lost_failure")
    if candidate.probability >= options.high_probability_threshold:
        reasons.append("high_probability_miss")
    if (
        candidate.decimal_odds is not None
        and candidate.decimal_odds <= options.short_price_odds_threshold
    ):
        reasons.append("short_price_miss")
    if _favorite_fragility_score(candidate) >= options.fragile_favorite_threshold:
        reasons.append("fragile_favorite_miss")
    if observation.actual_1x2_outcome == "draw":
        reasons.append("draw_underestimated_miss")
    return reasons


def _negative_roi_competitions(
    groups: Sequence[HistoricalFinalAnswerLossDiagnosticGroup],
) -> list[str]:
    return sorted(
        group.competition_id
        for group in groups
        if group.group_type == "competition"
        and group.unit == "final_answer"
        and group.competition_id is not None
        and group.roi is not None
        and group.roi < 0
    )


def _filter_groups(
    groups: Sequence[HistoricalFinalAnswerLossDiagnosticGroup],
    *,
    negative_roi_competitions: Sequence[str],
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> list[HistoricalFinalAnswerLossDiagnosticGroup]:
    if options.include_positive_roi_competitions:
        return list(groups)
    negative_set = set(negative_roi_competitions)
    return [
        group
        for group in groups
        if group.competition_id is None or group.competition_id in negative_set
    ]


def _filter_final_answer_observations(
    observations: Sequence[_FinalAnswerObservation],
    *,
    negative_roi_competitions: Sequence[str],
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> list[_FinalAnswerObservation]:
    if options.include_positive_roi_competitions:
        return list(observations)
    negative_set = set(negative_roi_competitions)
    return [
        observation
        for observation in observations
        if observation.competition_id in negative_set
    ]


def _filter_leg_observations(
    observations: Sequence[_LegObservation],
    *,
    negative_roi_competitions: Sequence[str],
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> list[_LegObservation]:
    if options.include_positive_roi_competitions:
        return list(observations)
    negative_set = set(negative_roi_competitions)
    return [
        observation
        for observation in observations
        if observation.competition_id in negative_set
    ]


def _top_loss_groups(
    groups: Sequence[HistoricalFinalAnswerLossDiagnosticGroup],
) -> list[HistoricalFinalAnswerLossDiagnosticGroup]:
    candidates = [
        group
        for group in groups
        if group.unit == "final_answer" and group.profit_loss < 0
    ]
    return sorted(
        candidates,
        key=lambda group: (group.profit_loss, group.roi or 0.0, group.group_key),
    )[:10]


def _top_missed_leg_groups(
    groups: Sequence[HistoricalFinalAnswerLossDiagnosticGroup],
) -> list[HistoricalFinalAnswerLossDiagnosticGroup]:
    candidates = [
        group
        for group in groups
        if group.unit in {"selected_leg", "missed_leg"} and group.missed_leg_count > 0
    ]
    return sorted(
        candidates,
        key=lambda group: (
            -group.missed_leg_count,
            group.leg_hit_rate if group.leg_hit_rate is not None else 1.0,
            group.group_key,
        ),
    )[:15]


def _include_competition(
    competition_id: str,
    *,
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> bool:
    return not options.focus_competition_ids or competition_id in options.focus_competition_ids


def _candidate_matches_actual(
    candidate: RecommendationCandidate,
    *,
    fixture: HistoricalFixture | None,
) -> bool:
    if fixture is None:
        actual_outcome = _metadata_string(candidate.metadata_json, "actual_1x2_outcome")
        if candidate.market_type == "1x2":
            return candidate.outcome == actual_outcome
        return False
    if candidate.market_type == "1x2":
        return candidate.outcome == fixture.actual_1x2_outcome
    if candidate.market_type == "correct_score":
        return candidate.outcome == f"{fixture.actual_home_goals}-{fixture.actual_away_goals}"
    return False


def _max_correlation_exposure(
    final_answer: HistoricalRecommendationScenarioResult,
) -> int:
    if final_answer.option is None:
        return 0
    counts = Counter(
        scored.candidate.correlation_key
        for scored in final_answer.option.selection.selected_candidates
        if scored.candidate.correlation_key is not None
    )
    return max(counts.values(), default=0)


def _favorite_fragility_score(candidate: RecommendationCandidate) -> float:
    return max(
        _metadata_float(candidate.metadata_json, "favorite_fragility_score"),
        _metadata_float(candidate.metadata_json, "market_context_favorite_fragility_score"),
    )


def _favorite_flag(candidate: RecommendationCandidate) -> str:
    raw = candidate.metadata_json.get("is_market_favorite")
    if raw is True:
        return "market_favorite"
    if raw is False:
        return "non_favorite"
    return "unknown_favorite_context"


def _odds_band(decimal_odds: float | None) -> str:
    if decimal_odds is None:
        return "odds_unknown"
    if decimal_odds <= 1.35:
        return "odds_1_01_1_35"
    if decimal_odds <= 1.60:
        return "odds_1_36_1_60"
    if decimal_odds <= 2.00:
        return "odds_1_61_2_00"
    if decimal_odds <= 3.00:
        return "odds_2_01_3_00"
    return "odds_3_01_plus"


def _probability_band(probability: float) -> str:
    if probability >= 0.75:
        return "prob_0_75_plus"
    if probability >= 0.65:
        return "prob_0_65_0_74"
    if probability >= 0.55:
        return "prob_0_55_0_64"
    if probability >= 0.45:
        return "prob_0_45_0_54"
    return "prob_under_0_45"


def _model_edge_band(edge: float) -> str:
    if edge >= 0.15:
        return "edge_0_15_plus"
    if edge >= 0.08:
        return "edge_0_08_0_14"
    if edge >= 0.00:
        return "edge_0_00_0_07"
    return "edge_negative"


def _fragility_band(score: float) -> str:
    if score >= 0.45:
        return "fragility_0_45_plus"
    if score >= 0.28:
        return "fragility_0_28_0_44"
    if score > 0.0:
        return "fragility_0_01_0_27"
    return "fragility_none"


def _correlation_exposure_band(max_exposure: int) -> str:
    if max_exposure >= 4:
        return "correlation_exposure_4_plus"
    if max_exposure >= 2:
        return f"correlation_exposure_{max_exposure}"
    return "correlation_exposure_0_1"


def _metadata_float(metadata_json: Mapping[str, object], key: str) -> float:
    raw = metadata_json.get(key)
    if isinstance(raw, int | float):
        return max(0.0, min(1.0, float(raw)))
    return 0.0


def _metadata_string(metadata_json: Mapping[str, object], key: str) -> str | None:
    raw = metadata_json.get(key)
    return raw if isinstance(raw, str) else None


def _group_sample_size(group: HistoricalFinalAnswerLossDiagnosticGroup) -> int:
    if group.unit == "final_answer":
        return group.final_answer_sample_size
    return group.selected_leg_count


def _report_summary(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    final_answer_observations: Sequence[_FinalAnswerObservation],
    leg_observations: Sequence[_LegObservation],
    groups: Sequence[HistoricalFinalAnswerLossDiagnosticGroup],
    negative_roi_competitions: Sequence[str],
    warnings: Sequence[str],
    options: HistoricalFinalAnswerLossDiagnosticOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_final_answer_loss_diagnostics_v3_1",
        "slice_count": len({observation.slice_id for observation in final_answer_observations}),
        "input_slice_count": len(historical_slices),
        "competition_count": len(
            {observation.competition_id for observation in final_answer_observations}
        ),
        "final_answer_count": len(final_answer_observations),
        "selected_leg_count": len(leg_observations),
        "missed_leg_count": sum(
            1 for observation in leg_observations if not observation.actual_hit
        ),
        "negative_roi_competitions": list(negative_roi_competitions),
        "group_count": len(groups),
        "pass_types": list(options.backtest_options.pass_types),
        "modes": list(options.backtest_options.modes),
        "strategy": options.backtest_options.strategy,
        "optimizer_profile": options.backtest_options.optimizer_profile,
        "unit_stake": options.backtest_options.unit_stake,
        "max_budget": options.backtest_options.max_budget,
        "min_probability": options.backtest_options.min_probability,
        "min_data_quality_score": options.backtest_options.min_data_quality_score,
        "max_outcomes_per_fixture": options.backtest_options.max_outcomes_per_fixture,
        "upset_threshold": options.backtest_options.upset_threshold,
        "candidate_fixture_limit": options.backtest_options.candidate_fixture_limit,
        "max_candidates_per_fixture": (
            options.backtest_options.max_candidates_per_fixture
        ),
        "scenario_candidate_fixture_buffer": (
            options.backtest_options.scenario_candidate_fixture_buffer
        ),
        "short_price_negative_edge_guardrail": (
            options.backtest_options.short_price_negative_edge_guardrail
        ),
        "short_price_negative_edge_max_decimal_odds": (
            options.backtest_options.short_price_negative_edge_max_decimal_odds
        ),
        "short_price_negative_edge_min_probability": (
            options.backtest_options.short_price_negative_edge_min_probability
        ),
        "short_price_negative_edge_max_model_edge": (
            options.backtest_options.short_price_negative_edge_max_model_edge
        ),
        "short_price_negative_edge_soft_penalty": (
            options.backtest_options.short_price_negative_edge_soft_penalty
        ),
        "short_price_negative_edge_soft_penalty_strength": (
            options.backtest_options.short_price_negative_edge_soft_penalty_strength
        ),
        "short_price_negative_edge_soft_penalty_competition_ids": list(
            options.backtest_options.short_price_negative_edge_soft_penalty_competition_ids
        ),
        "focus_competition_ids": list(options.focus_competition_ids),
        "include_positive_roi_competitions": options.include_positive_roi_competitions,
        "derive_market_context_signals": options.derive_market_context_signals,
        "fragile_favorite_threshold": options.fragile_favorite_threshold,
        "short_price_odds_threshold": options.short_price_odds_threshold,
        "high_probability_threshold": options.high_probability_threshold,
        "warnings": list(warnings),
    }


def _report_key(
    summary: Mapping[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "slice_ids": [
                    historical_slice.metadata.slice_id
                    for historical_slice in historical_slices
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_loss_diagnostics:{digest}"


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Stratify final-answer misses and losses in historical recommendation slices."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--output-path", type=Path)
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
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
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
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--short-price-negative-edge-guardrail", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-max-decimal-odds",
        type=float,
        default=1.35,
    )
    parser.add_argument(
        "--short-price-negative-edge-min-probability",
        type=float,
        default=0.70,
    )
    parser.add_argument(
        "--short-price-negative-edge-max-model-edge",
        type=float,
        default=0.0,
    )
    parser.add_argument("--short-price-negative-edge-soft-penalty", action="store_true")
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-strength",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--short-price-negative-edge-soft-penalty-competitions",
        default="",
    )
    parser.add_argument("--focus-competitions", default="")
    parser.add_argument("--negative-roi-only", action="store_true")
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument("--fragile-favorite-threshold", type=float, default=0.28)
    parser.add_argument("--short-price-odds-threshold", type=float, default=1.60)
    parser.add_argument("--high-probability-threshold", type=float, default=0.65)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalFinalAnswerLossDiagnosticOptions:
    return HistoricalFinalAnswerLossDiagnosticOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=_csv_tuple(args.pass_types),
            modes=tuple(
                cast(RecommendationMode, mode)
                for mode in _csv_tuple(args.modes)
            ),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            optimizer_profile=cast(
                HistoricalOptimizerProfile,
                args.optimizer_profile,
            ),
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
            short_price_negative_edge_guardrail=(
                args.short_price_negative_edge_guardrail
            ),
            short_price_negative_edge_max_decimal_odds=(
                args.short_price_negative_edge_max_decimal_odds
            ),
            short_price_negative_edge_min_probability=(
                args.short_price_negative_edge_min_probability
            ),
            short_price_negative_edge_max_model_edge=(
                args.short_price_negative_edge_max_model_edge
            ),
            short_price_negative_edge_soft_penalty=(
                args.short_price_negative_edge_soft_penalty
            ),
            short_price_negative_edge_soft_penalty_strength=(
                args.short_price_negative_edge_soft_penalty_strength
            ),
            short_price_negative_edge_soft_penalty_competition_ids=_csv_tuple(
                args.short_price_negative_edge_soft_penalty_competitions
            ),
        ),
        focus_competition_ids=_csv_tuple(args.focus_competitions),
        min_group_sample_size=args.min_group_sample_size,
        include_positive_roi_competitions=not args.negative_roi_only,
        derive_market_context_signals=args.derive_market_context_signals,
        fragile_favorite_threshold=args.fragile_favorite_threshold,
        short_price_odds_threshold=args.short_price_odds_threshold,
        high_probability_threshold=args.high_probability_threshold,
    )


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            resolved_slice_paths=list(args.slice_paths),
            slices=explicit_slices,
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
    resolved_slice_paths = [
        slice_path
        for bundle in bundles
        for slice_path in bundle.resolved_slice_paths
    ]
    warnings = [warning for bundle in bundles for warning in bundle.warnings]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *explicit_slices],
        resolved_slice_paths=[*resolved_slice_paths, *args.slice_paths],
        manifest_result=bundles[0] if len(bundles) == 1 else None,
        manifest_results=bundles,
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
