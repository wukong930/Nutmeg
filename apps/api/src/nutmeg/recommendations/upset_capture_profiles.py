from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    _candidates_from_fixture,
    _eligible_fixtures,
    _leg_matches_actual_outcome,
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
from nutmeg.recommendations.upset_policy import (
    RecommendationUpsetDirection,
    analyze_candidate_upset_signal,
)

type HistoricalUpsetCaptureSelectionState = Literal[
    "captured",
    "selected_wrong_fixture",
    "not_selected",
]

type HistoricalUpsetCaptureGroupType = Literal[
    "competition",
    "competition_season",
    "scenario",
    "direction",
    "selection_state",
    "probability_band",
    "odds_band",
    "model_edge_band",
    "protection_score_band",
    "favorite_fragility_band",
    "selected_favorite_fragility_band",
    "selected_favorite_context",
    "profile",
]


class HistoricalUpsetOpportunityObservation(BaseModel):
    observation_key: str
    slice_id: str
    competition_id: str
    season: str | None = None
    fixture_id: str
    final_answer_scenario_key: str | None = None
    final_answer_actual_hit: bool | None = None
    opportunity_outcome: str
    opportunity_market_type: str
    actual_1x2_outcome: str
    direction: RecommendationUpsetDirection
    protection_score: float = Field(ge=0.0, le=1.0)
    favorite_fragility_score: float = Field(ge=0.0, le=1.0)
    avoidance_penalty: float = Field(ge=0.0, le=1.0)
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float | None = Field(default=None, gt=1.0)
    model_edge: float
    market_favorite_outcome: str | None = None
    market_favorite_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    market_favorite_decimal_odds: float | None = Field(default=None, gt=1.0)
    selection_state: HistoricalUpsetCaptureSelectionState
    selected_outcomes: list[str] = Field(default_factory=list)
    selected_favorite_outcomes: list[str] = Field(default_factory=list)
    selected_market_favorite: bool = False
    selected_favorite_miss: bool = False
    selected_favorite_fragility_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    selected_favorite_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_favorite_decimal_odds: float | None = Field(default=None, gt=1.0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalUpsetCaptureProfileOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    focus_competition_ids: tuple[str, ...] = ()
    min_group_sample_size: int = Field(default=1, ge=1)
    upset_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    derive_market_context_signals: bool = False
    include_profile_groups: bool = True


class HistoricalUpsetCaptureGroup(BaseModel):
    group_key: str
    group_type: HistoricalUpsetCaptureGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    opportunity_count: int = Field(default=0, ge=0)
    capture_count: int = Field(default=0, ge=0)
    missed_count: int = Field(default=0, ge=0)
    capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_wrong_fixture_count: int = Field(default=0, ge=0)
    not_selected_count: int = Field(default=0, ge=0)
    selected_favorite_miss_count: int = Field(default=0, ge=0)
    average_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_decimal_odds: float | None = Field(default=None, gt=1.0)
    average_model_edge: float | None = None
    average_protection_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_favorite_fragility_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_selected_favorite_fragility_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    observation_keys: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalUpsetCaptureProfileReport(BaseModel):
    report_key: str
    status: str
    slice_count: int = Field(ge=0)
    competition_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    opportunity_count: int = Field(ge=0)
    capture_count: int = Field(ge=0)
    missed_count: int = Field(ge=0)
    capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_wrong_fixture_count: int = Field(default=0, ge=0)
    not_selected_count: int = Field(default=0, ge=0)
    selected_favorite_miss_count: int = Field(default=0, ge=0)
    observations: list[HistoricalUpsetOpportunityObservation] = Field(default_factory=list)
    groups: list[HistoricalUpsetCaptureGroup] = Field(default_factory=list)
    top_missed_groups: list[HistoricalUpsetCaptureGroup] = Field(default_factory=list)
    top_capture_groups: list[HistoricalUpsetCaptureGroup] = Field(default_factory=list)
    favorite_fragility_miss_groups: list[HistoricalUpsetCaptureGroup] = Field(
        default_factory=list
    )
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
    group_type: HistoricalUpsetCaptureGroupType
    label: str
    competition_id: str | None = None
    season: str | None = None
    observation_keys: set[str] | None = None
    opportunity_count: int = 0
    capture_count: int = 0
    selected_wrong_fixture_count: int = 0
    not_selected_count: int = 0
    selected_favorite_miss_count: int = 0
    probability_sum: float = 0.0
    decimal_odds_sum: float = 0.0
    decimal_odds_count: int = 0
    model_edge_sum: float = 0.0
    protection_score_sum: float = 0.0
    favorite_fragility_score_sum: float = 0.0
    selected_favorite_fragility_score_sum: float = 0.0
    selected_favorite_fragility_score_count: int = 0

    def add(self, observation: HistoricalUpsetOpportunityObservation) -> None:
        if self.observation_keys is None:
            self.observation_keys = set()
        self.observation_keys.add(observation.observation_key)
        self.opportunity_count += 1
        self.capture_count += int(observation.selection_state == "captured")
        self.selected_wrong_fixture_count += int(
            observation.selection_state == "selected_wrong_fixture"
        )
        self.not_selected_count += int(observation.selection_state == "not_selected")
        self.selected_favorite_miss_count += int(observation.selected_favorite_miss)
        self.probability_sum += observation.probability
        if observation.decimal_odds is not None:
            self.decimal_odds_sum += observation.decimal_odds
            self.decimal_odds_count += 1
        self.model_edge_sum += observation.model_edge
        self.protection_score_sum += observation.protection_score
        self.favorite_fragility_score_sum += observation.favorite_fragility_score
        if observation.selected_favorite_fragility_score is not None:
            self.selected_favorite_fragility_score_sum += (
                observation.selected_favorite_fragility_score
            )
            self.selected_favorite_fragility_score_count += 1

    def group(self) -> HistoricalUpsetCaptureGroup:
        missed_count = self.opportunity_count - self.capture_count
        return HistoricalUpsetCaptureGroup(
            group_key=self.group_key,
            group_type=self.group_type,
            label=self.label,
            competition_id=self.competition_id,
            season=self.season,
            opportunity_count=self.opportunity_count,
            capture_count=self.capture_count,
            missed_count=missed_count,
            capture_rate=_ratio(self.capture_count, self.opportunity_count),
            selected_wrong_fixture_count=self.selected_wrong_fixture_count,
            not_selected_count=self.not_selected_count,
            selected_favorite_miss_count=self.selected_favorite_miss_count,
            average_probability=_ratio(self.probability_sum, self.opportunity_count),
            average_decimal_odds=_ratio(self.decimal_odds_sum, self.decimal_odds_count),
            average_model_edge=_ratio(self.model_edge_sum, self.opportunity_count),
            average_protection_score=_ratio(
                self.protection_score_sum,
                self.opportunity_count,
            ),
            average_favorite_fragility_score=_ratio(
                self.favorite_fragility_score_sum,
                self.opportunity_count,
            ),
            average_selected_favorite_fragility_score=_ratio(
                self.selected_favorite_fragility_score_sum,
                self.selected_favorite_fragility_score_count,
            ),
            observation_keys=sorted(self.observation_keys or set()),
            summary_json={
                "miss_rate": _ratio(missed_count, self.opportunity_count),
                "selected_wrong_fixture_rate": _ratio(
                    self.selected_wrong_fixture_count,
                    self.opportunity_count,
                ),
                "selected_favorite_miss_rate": _ratio(
                    self.selected_favorite_miss_count,
                    self.opportunity_count,
                ),
                "selected_favorite_fragility_sample_size": (
                    self.selected_favorite_fragility_score_count
                ),
            },
        )


def build_historical_upset_capture_profile_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalUpsetCaptureProfileOptions | None = None,
) -> HistoricalUpsetCaptureProfileReport:
    resolved_options = options or HistoricalUpsetCaptureProfileOptions()
    backtest_options = resolved_options.backtest_options.model_copy(
        update={
            "derive_market_context_signals": (
                resolved_options.derive_market_context_signals
            ),
            "upset_threshold": resolved_options.upset_threshold,
        }
    )
    warnings: list[str] = []
    observations: list[HistoricalUpsetOpportunityObservation] = []
    final_answer_count = 0
    included_slice_ids: set[str] = set()
    included_competition_ids: set[str] = set()

    for historical_slice in historical_slices:
        if not _include_competition(historical_slice, options=resolved_options):
            continue
        backtest = run_historical_recommendation_backtest(
            historical_slice,
            options=backtest_options,
        )
        warnings.extend(backtest.warnings)
        final_answer = backtest.final_answer
        if final_answer is None:
            warnings.append(
                "upset_capture_profiles:no_final_answer:"
                f"{historical_slice.metadata.slice_id}"
            )
            continue
        final_answer_count += 1
        included_slice_ids.add(historical_slice.metadata.slice_id)
        included_competition_ids.add(historical_slice.metadata.competition_id)
        observations.extend(
            _opportunity_observations(
                historical_slice,
                final_answer=final_answer,
                options=resolved_options,
            )
        )

    groups = _profile_groups(observations, options=resolved_options)
    top_missed_groups = _top_missed_groups(groups)
    top_capture_groups = _top_capture_groups(groups)
    favorite_fragility_miss_groups = _favorite_fragility_miss_groups(groups)
    capture_count = sum(
        1 for observation in observations if observation.selection_state == "captured"
    )
    selected_wrong_fixture_count = sum(
        1
        for observation in observations
        if observation.selection_state == "selected_wrong_fixture"
    )
    not_selected_count = sum(
        1 for observation in observations if observation.selection_state == "not_selected"
    )
    selected_favorite_miss_count = sum(
        1 for observation in observations if observation.selected_favorite_miss
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_upset_capture_profiles_v3_1",
        "slice_count": len(included_slice_ids),
        "competition_count": len(included_competition_ids),
        "final_answer_count": final_answer_count,
        "opportunity_count": len(observations),
        "capture_count": capture_count,
        "missed_count": len(observations) - capture_count,
        "capture_rate": _ratio(capture_count, len(observations)),
        "selected_wrong_fixture_count": selected_wrong_fixture_count,
        "not_selected_count": not_selected_count,
        "selected_favorite_miss_count": selected_favorite_miss_count,
        "group_count": len(groups),
        "top_missed_group_keys": [group.group_key for group in top_missed_groups],
        "top_capture_group_keys": [group.group_key for group in top_capture_groups],
        "favorite_fragility_miss_group_keys": [
            group.group_key for group in favorite_fragility_miss_groups
        ],
        "focus_competition_ids": list(resolved_options.focus_competition_ids),
        "upset_threshold": resolved_options.upset_threshold,
        "min_group_sample_size": resolved_options.min_group_sample_size,
        "derive_market_context_signals": resolved_options.derive_market_context_signals,
        "include_profile_groups": resolved_options.include_profile_groups,
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    return HistoricalUpsetCaptureProfileReport(
        report_key=report_key,
        status="generated",
        slice_count=len(included_slice_ids),
        competition_count=len(included_competition_ids),
        final_answer_count=final_answer_count,
        opportunity_count=len(observations),
        capture_count=capture_count,
        missed_count=len(observations) - capture_count,
        capture_rate=_ratio(capture_count, len(observations)),
        selected_wrong_fixture_count=selected_wrong_fixture_count,
        not_selected_count=not_selected_count,
        selected_favorite_miss_count=selected_favorite_miss_count,
        observations=observations,
        groups=groups,
        top_missed_groups=top_missed_groups,
        top_capture_groups=top_capture_groups,
        favorite_fragility_miss_groups=favorite_fragility_miss_groups,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_upset_capture_profile_report(
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


def _opportunity_observations(
    historical_slice: HistoricalRecommendationSlice,
    *,
    final_answer: HistoricalRecommendationScenarioResult,
    options: HistoricalUpsetCaptureProfileOptions,
) -> list[HistoricalUpsetOpportunityObservation]:
    selected_by_fixture = _selected_candidates_by_fixture(final_answer)
    observations: list[HistoricalUpsetOpportunityObservation] = []
    for fixture in _eligible_fixtures(historical_slice):
        for candidate in _candidates_from_fixture(
            fixture,
            derive_market_context_signals=options.derive_market_context_signals,
        ):
            signal = analyze_candidate_upset_signal(candidate)
            if signal.protection_score < options.upset_threshold:
                continue
            if not _leg_matches_actual_outcome(
                fixture,
                outcome=candidate.outcome,
                market_type=candidate.market_type,
            ):
                continue
            selected_candidates = selected_by_fixture.get(fixture.fixture_id, [])
            selected_outcomes = [selected.outcome for selected in selected_candidates]
            selection_state = _selection_state(candidate, selected_candidates)
            selected_favorites = [
                selected
                for selected in selected_candidates
                if _is_market_favorite(selected)
            ]
            selected_market_favorite = bool(selected_favorites)
            selected_favorite = (
                max(selected_favorites, key=lambda selected: selected.probability)
                if selected_favorites
                else None
            )
            selected_favorite_miss = any(
                not _leg_matches_actual_outcome(
                    fixture,
                    outcome=selected.outcome,
                    market_type=selected.market_type,
                )
                for selected in selected_favorites
            )
            selected_favorite_fragility_score = _selected_favorite_fragility_score(
                selected_favorites
            )
            observations.append(
                HistoricalUpsetOpportunityObservation(
                    observation_key=_observation_key(
                        historical_slice,
                        fixture=fixture,
                        candidate=candidate,
                    ),
                    slice_id=historical_slice.metadata.slice_id,
                    competition_id=historical_slice.metadata.competition_id,
                    season=historical_slice.metadata.season,
                    fixture_id=fixture.fixture_id,
                    final_answer_scenario_key=final_answer.scenario.scenario_key,
                    final_answer_actual_hit=final_answer.actual_hit,
                    opportunity_outcome=candidate.outcome,
                    opportunity_market_type=candidate.market_type,
                    actual_1x2_outcome=fixture.actual_1x2_outcome,
                    direction=signal.direction,
                    protection_score=signal.protection_score,
                    favorite_fragility_score=signal.favorite_fragility_score,
                    avoidance_penalty=signal.avoidance_penalty,
                    probability=candidate.probability,
                    decimal_odds=candidate.decimal_odds,
                    model_edge=candidate.effective_model_edge(),
                    market_favorite_outcome=_metadata_string(
                        candidate.metadata_json,
                        "market_context_favorite_outcome",
                    ),
                    market_favorite_probability=_metadata_probability(
                        candidate.metadata_json,
                        "market_context_favorite_probability",
                    ),
                    market_favorite_decimal_odds=_metadata_decimal_odds(
                        candidate.metadata_json,
                        "market_context_favorite_decimal_odds",
                    ),
                    selection_state=selection_state,
                    selected_outcomes=selected_outcomes,
                    selected_favorite_outcomes=[
                        selected.outcome for selected in selected_favorites
                    ],
                    selected_market_favorite=selected_market_favorite,
                    selected_favorite_miss=selected_favorite_miss,
                    selected_favorite_fragility_score=selected_favorite_fragility_score,
                    selected_favorite_probability=(
                        selected_favorite.probability
                        if selected_favorite is not None
                        else None
                    ),
                    selected_favorite_decimal_odds=(
                        selected_favorite.decimal_odds
                        if selected_favorite is not None
                        else None
                    ),
                    summary_json={
                        "selected_fixture": bool(selected_candidates),
                        "selected_candidate_count": len(selected_candidates),
                        "selected_market_favorite": selected_market_favorite,
                        "selected_favorite_miss": selected_favorite_miss,
                        "selected_favorite_outcomes": [
                            selected.outcome for selected in selected_favorites
                        ],
                    },
                )
            )
    return observations


def _profile_groups(
    observations: Sequence[HistoricalUpsetOpportunityObservation],
    *,
    options: HistoricalUpsetCaptureProfileOptions,
) -> list[HistoricalUpsetCaptureGroup]:
    accumulators: dict[tuple[HistoricalUpsetCaptureGroupType, str], _GroupAccumulator] = {}
    for observation in observations:
        for group_type, group_key, label in _group_keys_for_observation(
            observation,
            include_profile_groups=options.include_profile_groups,
        ):
            accumulator = accumulators.setdefault(
                (group_type, group_key),
                _GroupAccumulator(
                    group_key=group_key,
                    group_type=group_type,
                    label=label,
                    competition_id=observation.competition_id,
                    season=observation.season
                    if group_type == "competition_season"
                    else None,
                ),
            )
            accumulator.add(observation)
    return sorted(
        (
            accumulator.group()
            for accumulator in accumulators.values()
            if accumulator.opportunity_count >= options.min_group_sample_size
        ),
        key=lambda group: (group.group_type, group.group_key),
    )


def _group_keys_for_observation(
    observation: HistoricalUpsetOpportunityObservation,
    *,
    include_profile_groups: bool,
) -> list[tuple[HistoricalUpsetCaptureGroupType, str, str]]:
    season = observation.season or "unknown"
    probability_band = _probability_band(observation.probability)
    odds_band = _odds_band(observation.decimal_odds)
    edge_band = _model_edge_band(observation.model_edge)
    protection_band = _score_band(observation.protection_score)
    fragility_band = _score_band(observation.favorite_fragility_score)
    selected_favorite_fragility_band = _optional_score_band(
        observation.selected_favorite_fragility_score
    )
    selected_favorite_context = (
        "selected_favorite_miss"
        if observation.selected_favorite_miss
        else "selected_favorite_no_miss"
        if observation.selected_market_favorite
        else "no_selected_favorite"
    )
    keys: list[tuple[HistoricalUpsetCaptureGroupType, str, str]] = [
        ("competition", observation.competition_id, observation.competition_id),
        (
            "competition_season",
            f"{observation.competition_id}:{season}",
            f"{observation.competition_id} {season}",
        ),
        (
            "scenario",
            f"{observation.competition_id}:{observation.final_answer_scenario_key}",
            f"{observation.competition_id} {observation.final_answer_scenario_key}",
        ),
        (
            "direction",
            f"direction:{observation.direction}",
            observation.direction,
        ),
        (
            "selection_state",
            f"selection_state:{observation.selection_state}",
            observation.selection_state,
        ),
        (
            "probability_band",
            f"probability:{probability_band}",
            probability_band,
        ),
        ("odds_band", f"odds:{odds_band}", odds_band),
        ("model_edge_band", f"model_edge:{edge_band}", edge_band),
        (
            "protection_score_band",
            f"protection:{protection_band}",
            protection_band,
        ),
        (
            "favorite_fragility_band",
            f"favorite_fragility:{fragility_band}",
            fragility_band,
        ),
        (
            "selected_favorite_fragility_band",
            f"selected_favorite_fragility:{selected_favorite_fragility_band}",
            selected_favorite_fragility_band,
        ),
        (
            "selected_favorite_context",
            f"selected_favorite_context:{selected_favorite_context}",
            selected_favorite_context,
        ),
    ]
    if include_profile_groups:
        profile_key = "|".join(
            [
                observation.competition_id,
                observation.direction,
                probability_band,
                odds_band,
                edge_band,
                protection_band,
                selected_favorite_fragility_band,
                observation.selection_state,
                selected_favorite_context,
            ]
        )
        keys.append(("profile", f"profile:{profile_key}", profile_key))
    return keys


def _top_missed_groups(
    groups: Sequence[HistoricalUpsetCaptureGroup],
) -> list[HistoricalUpsetCaptureGroup]:
    return sorted(
        (group for group in groups if group.missed_count > 0),
        key=lambda group: (
            group.missed_count,
            group.selected_favorite_miss_count,
            group.opportunity_count,
            -(group.capture_rate if group.capture_rate is not None else 0.0),
            group.group_key,
        ),
        reverse=True,
    )[:20]


def _top_capture_groups(
    groups: Sequence[HistoricalUpsetCaptureGroup],
) -> list[HistoricalUpsetCaptureGroup]:
    return sorted(
        (group for group in groups if group.capture_count > 0),
        key=lambda group: (
            group.capture_count,
            group.capture_rate if group.capture_rate is not None else 0.0,
            group.opportunity_count,
            group.group_key,
        ),
        reverse=True,
    )[:20]


def _favorite_fragility_miss_groups(
    groups: Sequence[HistoricalUpsetCaptureGroup],
) -> list[HistoricalUpsetCaptureGroup]:
    return sorted(
        (group for group in groups if group.selected_favorite_miss_count > 0),
        key=lambda group: (
            group.selected_favorite_miss_count,
            group.missed_count,
            _group_selected_favorite_fragility_sort_value(group),
            group.group_key,
        ),
        reverse=True,
    )[:20]


def _selected_candidates_by_fixture(
    final_answer: HistoricalRecommendationScenarioResult,
) -> dict[str, list[RecommendationCandidate]]:
    if final_answer.option is None:
        return {}
    selected: dict[str, list[RecommendationCandidate]] = {}
    for scored in final_answer.option.selection.selected_candidates:
        selected.setdefault(scored.candidate.fixture_id, []).append(scored.candidate)
    return selected


def _selection_state(
    opportunity: RecommendationCandidate,
    selected_candidates: Sequence[RecommendationCandidate],
) -> HistoricalUpsetCaptureSelectionState:
    for selected in selected_candidates:
        if (
            selected.market_type == opportunity.market_type
            and selected.outcome == opportunity.outcome
            and selected.line == opportunity.line
            and selected.side == opportunity.side
        ):
            return "captured"
    if selected_candidates:
        return "selected_wrong_fixture"
    return "not_selected"


def _is_market_favorite(candidate: RecommendationCandidate) -> bool:
    raw = candidate.metadata_json.get("is_market_favorite")
    if isinstance(raw, bool):
        return raw
    favorite_outcome = _metadata_string(
        candidate.metadata_json,
        "market_context_favorite_outcome",
    )
    return favorite_outcome == candidate.outcome


def _selected_favorite_fragility_score(
    selected_favorites: Sequence[RecommendationCandidate],
) -> float | None:
    if not selected_favorites:
        return None
    return max(_candidate_favorite_fragility_score(candidate) for candidate in selected_favorites)


def _candidate_favorite_fragility_score(candidate: RecommendationCandidate) -> float:
    signal = analyze_candidate_upset_signal(candidate)
    return max(
        signal.favorite_fragility_score,
        _metadata_unit_float(candidate.metadata_json, "favorite_fragility_score") or 0.0,
        _metadata_unit_float(
            candidate.metadata_json,
            "market_context_favorite_fragility_score",
        )
        or 0.0,
    )


def _group_selected_favorite_fragility_sort_value(
    group: HistoricalUpsetCaptureGroup,
) -> float:
    if group.average_selected_favorite_fragility_score is not None:
        return group.average_selected_favorite_fragility_score
    if group.average_favorite_fragility_score is not None:
        return group.average_favorite_fragility_score
    return 0.0


def _include_competition(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalUpsetCaptureProfileOptions,
) -> bool:
    if not options.focus_competition_ids:
        return True
    return historical_slice.metadata.competition_id in options.focus_competition_ids


def _observation_key(
    historical_slice: HistoricalRecommendationSlice,
    *,
    fixture: HistoricalFixture,
    candidate: RecommendationCandidate,
) -> str:
    payload = "|".join(
        [
            historical_slice.metadata.slice_id,
            fixture.fixture_id,
            candidate.market_type,
            candidate.outcome,
            str(candidate.line),
            str(candidate.side),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"upset_opportunity:{historical_slice.metadata.slice_id}:{digest}"


def _report_key(
    summary: dict[str, object],
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> str:
    slice_payload = ";".join(
        f"{historical_slice.metadata.slice_id}@{historical_slice.as_of_time_utc.isoformat()}"
        for historical_slice in historical_slices
    )
    payload = dumps(
        {
            "summary": summary,
            "slices": slice_payload,
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_upset_capture_profiles:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Profile missed and captured historical upset opportunities."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
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
    parser.add_argument("--focus-competitions", default="")
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument("--no-profile-groups", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalUpsetCaptureProfileOptions:
    return HistoricalUpsetCaptureProfileOptions(
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
        ),
        focus_competition_ids=tuple(_csv(args.focus_competitions)),
        min_group_sample_size=args.min_group_sample_size,
        upset_threshold=args.upset_threshold,
        derive_market_context_signals=args.derive_market_context_signals,
        include_profile_groups=not args.no_profile_groups,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    return _LoadedHistoricalSlices(
        slices=[*bundle.slices, *explicit_slices],
        resolved_slice_paths=[*bundle.resolved_slice_paths, *args.slice_paths],
        manifest_result=bundle,
        warnings=bundle.warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.manifest.slices),
        "resolved_slice_count": len(manifest_result.resolved_slice_paths),
        "warnings": manifest_result.warnings,
    }


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _probability_band(probability: float) -> str:
    if probability >= 0.65:
        return "prob_0_65_plus"
    if probability >= 0.45:
        return "prob_0_45_0_64"
    if probability >= 0.30:
        return "prob_0_30_0_44"
    return "prob_under_0_30"


def _odds_band(decimal_odds: float | None) -> str:
    if decimal_odds is None:
        return "odds_unknown"
    if decimal_odds <= 1.60:
        return "odds_1_01_1_60"
    if decimal_odds <= 2.50:
        return "odds_1_61_2_50"
    if decimal_odds <= 4.00:
        return "odds_2_51_4_00"
    return "odds_4_01_plus"


def _model_edge_band(edge: float) -> str:
    if edge >= 0.08:
        return "edge_0_08_plus"
    if edge >= 0.0:
        return "edge_0_00_0_07"
    if edge >= -0.05:
        return "edge_neg_0_00_0_05"
    return "edge_neg_0_05_plus"


def _score_band(score: float) -> str:
    if score >= 0.65:
        return "score_0_65_plus"
    if score >= 0.45:
        return "score_0_45_0_64"
    if score >= 0.28:
        return "score_0_28_0_44"
    if score > 0.0:
        return "score_0_01_0_27"
    return "score_none"


def _optional_score_band(score: float | None) -> str:
    if score is None:
        return "score_unknown"
    return _score_band(score)


def _metadata_unit_float(
    metadata_json: Mapping[str, object],
    key: str,
) -> float | None:
    raw = metadata_json.get(key)
    if isinstance(raw, int | float):
        return max(0.0, min(1.0, float(raw)))
    return None


def _metadata_probability(
    metadata_json: Mapping[str, object],
    key: str,
) -> float | None:
    return _metadata_unit_float(metadata_json, key)


def _metadata_decimal_odds(
    metadata_json: Mapping[str, object],
    key: str,
) -> float | None:
    raw = metadata_json.get(key)
    if isinstance(raw, int | float) and float(raw) > 1.0:
        return float(raw)
    return None


def _metadata_string(
    metadata_json: Mapping[str, object],
    key: str,
) -> str | None:
    raw = metadata_json.get(key)
    return raw if isinstance(raw, str) else None


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
