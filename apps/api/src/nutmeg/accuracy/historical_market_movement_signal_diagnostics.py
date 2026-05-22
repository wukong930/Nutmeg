from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from math import log
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalMarketMovementSignalDiagnosticStatus = Literal["generated"]
type HistoricalMarketMovementSignalGroupType = Literal[
    "overall",
    "outcome",
    "movement_direction",
    "delta_band",
    "opening_probability_band",
    "strongest_movement_direction",
    "competition",
    "competition_outcome",
    "competition_direction",
]

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
DEFAULT_LOG_LOSS_EPSILON = 1e-12


class HistoricalMarketMovementSignalDiagnosticOptions(BaseModel):
    min_abs_probability_delta: float = Field(default=0.0, ge=0.0, le=1.0)
    movement_direction_epsilon: float = Field(default=0.001, ge=0.0, le=1.0)
    delta_bands: tuple[str, ...] = ("0.00:0.01", "0.01:0.03", "0.03:0.06", "0.06:")
    opening_probability_bands: tuple[str, ...] = (
        "0.00:0.25",
        "0.25:0.45",
        "0.45:0.65",
        "0.65:1.00",
    )
    min_group_sample_size: int = Field(default=1, ge=1)
    include_competition_groups: bool = True
    observation_sample_limit: int = Field(default=20, ge=0)


class HistoricalMarketMovementSignalObservation(BaseModel):
    fixture_id: str
    slice_id: str
    competition_id: str
    season: str | None = None
    outcome: str
    actual_outcome: str
    actual_occurred: bool
    opening_probability: float = Field(ge=0.0, le=1.0)
    closing_probability: float = Field(ge=0.0, le=1.0)
    probability_delta: float
    abs_probability_delta: float = Field(ge=0.0, le=1.0)
    movement_direction: str
    opening_decimal_odds: float | None = Field(default=None, gt=1.0)
    closing_decimal_odds: float | None = Field(default=None, gt=1.0)
    decimal_odds_delta: float | None = None
    opening_binary_brier_score: float = Field(ge=0.0)
    closing_binary_brier_score: float = Field(ge=0.0)
    opening_log_loss: float = Field(ge=0.0)
    closing_log_loss: float = Field(ge=0.0)
    closing_improved: bool
    is_strongest_fixture_movement: bool = False
    source_snapshot_refs: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementSignalGroup(BaseModel):
    group_key: str
    group_type: HistoricalMarketMovementSignalGroupType
    label: str
    competition_id: str | None = None
    outcome: str | None = None
    movement_direction: str | None = None
    band: str | None = None
    sample_count: int = Field(ge=0)
    actual_count: int = Field(ge=0)
    actual_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    closing_improved_count: int = Field(ge=0)
    closing_improved_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    average_opening_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_closing_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    average_probability_delta: float | None = None
    average_abs_probability_delta: float | None = Field(default=None, ge=0.0, le=1.0)
    opening_brier_score: float | None = Field(default=None, ge=0.0)
    closing_brier_score: float | None = Field(default=None, ge=0.0)
    brier_score_delta: float | None = None
    opening_log_loss: float | None = Field(default=None, ge=0.0)
    closing_log_loss: float | None = Field(default=None, ge=0.0)
    log_loss_delta: float | None = None
    opening_calibration_error: float | None = Field(default=None, ge=0.0)
    closing_calibration_error: float | None = Field(default=None, ge=0.0)
    calibration_error_delta: float | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementSignalDiagnosticReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementSignalDiagnosticStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    strongest_observation_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    overall: HistoricalMarketMovementSignalGroup
    groups: list[HistoricalMarketMovementSignalGroup] = Field(default_factory=list)
    top_positive_signal_groups: list[HistoricalMarketMovementSignalGroup] = (
        Field(default_factory=list)
    )
    top_negative_signal_groups: list[HistoricalMarketMovementSignalGroup] = (
        Field(default_factory=list)
    )
    sampled_observations: list[HistoricalMarketMovementSignalObservation] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _FixtureContext:
    slice_id: str
    season: str | None
    fixture: HistoricalFixture


@dataclass(frozen=True)
class _SkippedFixture:
    fixture_id: str
    competition_id: str
    season: str | None
    reason: str


@dataclass(frozen=True)
class _GroupSpec:
    group_key: str
    group_type: HistoricalMarketMovementSignalGroupType
    label: str
    competition_id: str | None = None
    outcome: str | None = None
    movement_direction: str | None = None
    band: str | None = None


@dataclass
class _GroupAccumulator:
    spec: _GroupSpec
    sample_count: int = 0
    actual_count: int = 0
    closing_improved_count: int = 0
    opening_probability_sum: float = 0.0
    closing_probability_sum: float = 0.0
    probability_delta_sum: float = 0.0
    abs_probability_delta_sum: float = 0.0
    opening_brier_score_sum: float = 0.0
    closing_brier_score_sum: float = 0.0
    opening_log_loss_sum: float = 0.0
    closing_log_loss_sum: float = 0.0

    def observe(self, observation: HistoricalMarketMovementSignalObservation) -> None:
        self.sample_count += 1
        self.actual_count += int(observation.actual_occurred)
        self.closing_improved_count += int(observation.closing_improved)
        self.opening_probability_sum += observation.opening_probability
        self.closing_probability_sum += observation.closing_probability
        self.probability_delta_sum += observation.probability_delta
        self.abs_probability_delta_sum += observation.abs_probability_delta
        self.opening_brier_score_sum += observation.opening_binary_brier_score
        self.closing_brier_score_sum += observation.closing_binary_brier_score
        self.opening_log_loss_sum += observation.opening_log_loss
        self.closing_log_loss_sum += observation.closing_log_loss

    def group(self) -> HistoricalMarketMovementSignalGroup:
        actual_rate = _ratio(self.actual_count, self.sample_count)
        opening_probability = _ratio(self.opening_probability_sum, self.sample_count)
        closing_probability = _ratio(self.closing_probability_sum, self.sample_count)
        opening_brier = _ratio(self.opening_brier_score_sum, self.sample_count)
        closing_brier = _ratio(self.closing_brier_score_sum, self.sample_count)
        opening_log_loss = _ratio(self.opening_log_loss_sum, self.sample_count)
        closing_log_loss = _ratio(self.closing_log_loss_sum, self.sample_count)
        opening_calibration_error = (
            abs(actual_rate - opening_probability)
            if actual_rate is not None and opening_probability is not None
            else None
        )
        closing_calibration_error = (
            abs(actual_rate - closing_probability)
            if actual_rate is not None and closing_probability is not None
            else None
        )
        return HistoricalMarketMovementSignalGroup(
            group_key=self.spec.group_key,
            group_type=self.spec.group_type,
            label=self.spec.label,
            competition_id=self.spec.competition_id,
            outcome=self.spec.outcome,
            movement_direction=self.spec.movement_direction,
            band=self.spec.band,
            sample_count=self.sample_count,
            actual_count=self.actual_count,
            actual_rate=actual_rate,
            closing_improved_count=self.closing_improved_count,
            closing_improved_rate=_ratio(
                self.closing_improved_count,
                self.sample_count,
            ),
            average_opening_probability=opening_probability,
            average_closing_probability=closing_probability,
            average_probability_delta=_ratio(
                self.probability_delta_sum,
                self.sample_count,
            ),
            average_abs_probability_delta=_ratio(
                self.abs_probability_delta_sum,
                self.sample_count,
            ),
            opening_brier_score=opening_brier,
            closing_brier_score=closing_brier,
            brier_score_delta=_optional_delta(closing_brier, opening_brier),
            opening_log_loss=opening_log_loss,
            closing_log_loss=closing_log_loss,
            log_loss_delta=_optional_delta(closing_log_loss, opening_log_loss),
            opening_calibration_error=opening_calibration_error,
            closing_calibration_error=closing_calibration_error,
            calibration_error_delta=_optional_delta(
                closing_calibration_error,
                opening_calibration_error,
            ),
            summary_json={
                "closing_probability_more_aligned_with_result": (
                    _ratio(self.closing_improved_count, self.sample_count)
                ),
            },
        )


def build_historical_market_movement_signal_diagnostic_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions | None = None,
) -> HistoricalMarketMovementSignalDiagnosticReport:
    resolved_options = options or HistoricalMarketMovementSignalDiagnosticOptions()
    observations, skipped = _movement_observations(
        historical_slices,
        options=resolved_options,
    )
    groups = _groups_from_observations(observations, options=resolved_options)
    overall = _overall_group(observations)
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    warnings = _report_warnings(observations, skipped)
    top_positive = _top_signal_groups(groups, reverse=False, options=resolved_options)
    top_negative = _top_signal_groups(groups, reverse=True, options=resolved_options)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    strongest_count = sum(
        1 for observation in observations if observation.is_strongest_fixture_movement
    )
    report_key = _report_key(
        historical_slices,
        options=resolved_options,
        observation_count=len(observations),
        skipped_reason_counts=skipped_reason_counts,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_market_movement_signal_diagnostics_v3_1",
        "report_key": report_key,
        "shadow_only": True,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "observation_count": len(observations),
        "strongest_observation_count": strongest_count,
        "skipped_fixture_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "overall_actual_rate": overall.actual_rate,
        "overall_closing_improved_rate": overall.closing_improved_rate,
        "overall_brier_score_delta": overall.brier_score_delta,
        "overall_log_loss_delta": overall.log_loss_delta,
        "overall_calibration_error_delta": overall.calibration_error_delta,
        "top_positive_group_keys": [
            group.group_key for group in top_positive
        ],
        "top_negative_group_keys": [
            group.group_key for group in top_negative
        ],
        "warnings": warnings,
    }
    return HistoricalMarketMovementSignalDiagnosticReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        observation_count=len(observations),
        strongest_observation_count=strongest_count,
        skipped_fixture_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        overall=overall,
        groups=groups,
        top_positive_signal_groups=top_positive,
        top_negative_signal_groups=top_negative,
        sampled_observations=observations[: resolved_options.observation_sample_limit],
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_market_movement_signal_diagnostic_report(
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
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)


def _movement_observations(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> tuple[list[HistoricalMarketMovementSignalObservation], list[_SkippedFixture]]:
    observations: list[HistoricalMarketMovementSignalObservation] = []
    skipped: list[_SkippedFixture] = []
    for historical_slice in historical_slices:
        for fixture in historical_slice.fixtures:
            context = _FixtureContext(
                slice_id=historical_slice.metadata.slice_id,
                season=historical_slice.metadata.season,
                fixture=fixture,
            )
            fixture_observations, skip_reason = _fixture_observations(
                context,
                options=options,
            )
            if skip_reason is not None:
                skipped.append(_skipped(context, skip_reason))
                continue
            observations.extend(fixture_observations)
    return observations, skipped


def _fixture_observations(
    context: _FixtureContext,
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> tuple[list[HistoricalMarketMovementSignalObservation], str | None]:
    fixture = context.fixture
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return [], "missing_feature_snapshot"
    prematch_context = _mapping(snapshot.features_json.get("prematch_context"))
    if prematch_context is None:
        return [], "missing_prematch_context"
    movements = _list_of_mappings(prematch_context.get("odds_movement"))
    if not movements:
        return [], "missing_odds_movement"
    observations = [
        observation
        for movement in movements
        if (
            observation := _observation_from_movement(
                context,
                movement=movement,
                options=options,
            )
        )
        is not None
    ]
    if not observations:
        return [], "missing_valid_odds_movement"
    strongest_abs_delta = max(item.abs_probability_delta for item in observations)
    return [
        observation.model_copy(
            update={
                "is_strongest_fixture_movement": (
                    observation.abs_probability_delta == strongest_abs_delta
                )
            }
        )
        for observation in observations
    ], None


def _observation_from_movement(
    context: _FixtureContext,
    *,
    movement: Mapping[str, object],
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> HistoricalMarketMovementSignalObservation | None:
    if movement.get("market_type") != "1x2":
        return None
    outcome = str(movement.get("outcome") or "")
    if outcome not in ONE_X_TWO_OUTCOMES:
        return None
    opening_probability = _first_float(
        movement,
        ("opening_prob", "opening_probability"),
    )
    closing_probability = _first_float(
        movement,
        ("current_prob", "closing_prob", "closing_probability", "current_probability"),
    )
    if opening_probability is None or closing_probability is None:
        return None
    probability_delta = closing_probability - opening_probability
    abs_delta = abs(probability_delta)
    if abs_delta < options.min_abs_probability_delta:
        return None
    actual_outcome = context.fixture.actual_1x2_outcome
    actual_occurred = outcome == actual_outcome
    opening_binary_brier = _binary_brier_score(
        opening_probability,
        actual_occurred=actual_occurred,
    )
    closing_binary_brier = _binary_brier_score(
        closing_probability,
        actual_occurred=actual_occurred,
    )
    opening_log_loss = _binary_log_loss(
        opening_probability,
        actual_occurred=actual_occurred,
    )
    closing_log_loss = _binary_log_loss(
        closing_probability,
        actual_occurred=actual_occurred,
    )
    closing_improved = _closing_improved(
        opening_probability,
        closing_probability,
        actual_occurred=actual_occurred,
    )
    opening_decimal_odds = _first_float(
        movement,
        ("opening_decimal_odds", "opening_odds"),
    )
    closing_decimal_odds = _first_float(
        movement,
        ("current_decimal_odds", "closing_decimal_odds", "closing_odds"),
    )
    decimal_odds_delta = (
        closing_decimal_odds - opening_decimal_odds
        if opening_decimal_odds is not None and closing_decimal_odds is not None
        else None
    )
    direction = _movement_direction(
        probability_delta,
        epsilon=options.movement_direction_epsilon,
    )
    source_refs = _movement_source_refs(movement)
    return HistoricalMarketMovementSignalObservation(
        fixture_id=context.fixture.fixture_id,
        slice_id=context.slice_id,
        competition_id=context.fixture.competition_id,
        season=context.season,
        outcome=outcome,
        actual_outcome=actual_outcome,
        actual_occurred=actual_occurred,
        opening_probability=opening_probability,
        closing_probability=closing_probability,
        probability_delta=probability_delta,
        abs_probability_delta=abs_delta,
        movement_direction=direction,
        opening_decimal_odds=opening_decimal_odds,
        closing_decimal_odds=closing_decimal_odds,
        decimal_odds_delta=decimal_odds_delta,
        opening_binary_brier_score=opening_binary_brier,
        closing_binary_brier_score=closing_binary_brier,
        opening_log_loss=opening_log_loss,
        closing_log_loss=closing_log_loss,
        closing_improved=closing_improved,
        source_snapshot_refs=source_refs,
        summary_json={
            "raw_movement_direction": movement.get("movement_direction"),
            "closing_probability_better_than_opening": closing_improved,
        },
    )


def _groups_from_observations(
    observations: Sequence[HistoricalMarketMovementSignalObservation],
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> list[HistoricalMarketMovementSignalGroup]:
    accumulators: dict[str, _GroupAccumulator] = {}
    for observation in observations:
        for spec in _group_specs(observation, options=options):
            accumulator = accumulators.setdefault(
                spec.group_key,
                _GroupAccumulator(spec=spec),
            )
            accumulator.observe(observation)
    return sorted(
        [
            accumulator.group()
            for accumulator in accumulators.values()
            if accumulator.sample_count >= options.min_group_sample_size
        ],
        key=lambda group: (group.group_type, group.group_key),
    )


def _overall_group(
    observations: Sequence[HistoricalMarketMovementSignalObservation],
) -> HistoricalMarketMovementSignalGroup:
    accumulator = _GroupAccumulator(
        _GroupSpec("overall", "overall", "Overall market movement observations")
    )
    for observation in observations:
        accumulator.observe(observation)
    return accumulator.group()


def _group_specs(
    observation: HistoricalMarketMovementSignalObservation,
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> list[_GroupSpec]:
    direction = observation.movement_direction
    delta_band = _band_for_value(observation.abs_probability_delta, options.delta_bands)
    opening_band = _band_for_value(
        observation.opening_probability,
        options.opening_probability_bands,
    )
    specs = [
        _GroupSpec(
            f"outcome:{observation.outcome}",
            "outcome",
            f"Outcome {observation.outcome}",
            outcome=observation.outcome,
        ),
        _GroupSpec(
            f"movement_direction:{direction}",
            "movement_direction",
            f"Movement direction {direction}",
            movement_direction=direction,
        ),
        _GroupSpec(
            f"delta_band:{delta_band}",
            "delta_band",
            f"Abs probability delta {delta_band}",
            band=delta_band,
        ),
        _GroupSpec(
            f"opening_probability_band:{opening_band}",
            "opening_probability_band",
            f"Opening probability {opening_band}",
            band=opening_band,
        ),
    ]
    if observation.is_strongest_fixture_movement:
        specs.append(
            _GroupSpec(
                f"strongest_movement_direction:{direction}",
                "strongest_movement_direction",
                f"Strongest fixture movement {direction}",
                movement_direction=direction,
            )
        )
    if options.include_competition_groups:
        specs.extend(
            [
                _GroupSpec(
                    f"competition:{observation.competition_id}",
                    "competition",
                    f"Competition {observation.competition_id}",
                    competition_id=observation.competition_id,
                ),
                _GroupSpec(
                    f"competition_outcome:{observation.competition_id}:{observation.outcome}",
                    "competition_outcome",
                    f"{observation.competition_id} {observation.outcome}",
                    competition_id=observation.competition_id,
                    outcome=observation.outcome,
                ),
                _GroupSpec(
                    (
                        "competition_direction:"
                        f"{observation.competition_id}:{direction}"
                    ),
                    "competition_direction",
                    f"{observation.competition_id} {direction}",
                    competition_id=observation.competition_id,
                    movement_direction=direction,
                ),
            ]
        )
    return specs


def _top_signal_groups(
    groups: Sequence[HistoricalMarketMovementSignalGroup],
    *,
    reverse: bool,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
) -> list[HistoricalMarketMovementSignalGroup]:
    eligible = [
        group
        for group in groups
        if group.sample_count >= options.min_group_sample_size
        and group.brier_score_delta is not None
        and group.group_type != "overall"
    ]
    return sorted(
        eligible,
        key=lambda group: (
            group.brier_score_delta or 0.0,
            group.log_loss_delta or 0.0,
            group.calibration_error_delta or 0.0,
        ),
        reverse=reverse,
    )[:10]


def _report_warnings(
    observations: Sequence[HistoricalMarketMovementSignalObservation],
    skipped: Sequence[_SkippedFixture],
) -> list[str]:
    warnings: list[str] = []
    if not observations:
        warnings.append("historical_market_movement_signal_diagnostics:no_observations")
    if skipped:
        warnings.append("historical_market_movement_signal_diagnostics:skipped_fixtures")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Diagnose whether opening-to-closing 1X2 market movement improves "
            "historical outcome probabilities."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-abs-probability-delta", type=float, default=0.0)
    parser.add_argument("--movement-direction-epsilon", type=float, default=0.001)
    parser.add_argument(
        "--delta-bands",
        default="0.00:0.01,0.01:0.03,0.03:0.06,0.06:",
    )
    parser.add_argument(
        "--opening-probability-bands",
        default="0.00:0.25,0.25:0.45,0.45:0.65,0.65:1.00",
    )
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument(
        "--include-competition-groups",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--observation-sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementSignalDiagnosticOptions:
    return HistoricalMarketMovementSignalDiagnosticOptions(
        min_abs_probability_delta=args.min_abs_probability_delta,
        movement_direction_epsilon=args.movement_direction_epsilon,
        delta_bands=_split_csv(args.delta_bands),
        opening_probability_bands=_split_csv(args.opening_probability_bands),
        min_group_sample_size=args.min_group_sample_size,
        include_competition_groups=args.include_competition_groups,
        observation_sample_limit=args.observation_sample_limit,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
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


def _skipped(context: _FixtureContext, reason: str) -> _SkippedFixture:
    return _SkippedFixture(
        fixture_id=context.fixture.fixture_id,
        competition_id=context.fixture.competition_id,
        season=context.season,
        reason=reason,
    )


def _movement_direction(probability_delta: float, *, epsilon: float) -> str:
    if probability_delta > epsilon:
        return "probability_shortened"
    if probability_delta < -epsilon:
        return "probability_drifted"
    return "stable"


def _closing_improved(
    opening_probability: float,
    closing_probability: float,
    *,
    actual_occurred: bool,
) -> bool:
    if actual_occurred:
        return closing_probability > opening_probability
    return closing_probability < opening_probability


def _binary_brier_score(probability: float, *, actual_occurred: bool) -> float:
    actual = 1.0 if actual_occurred else 0.0
    return (probability - actual) ** 2


def _binary_log_loss(probability: float, *, actual_occurred: bool) -> float:
    clipped = min(max(probability, DEFAULT_LOG_LOSS_EPSILON), 1.0 - DEFAULT_LOG_LOSS_EPSILON)
    return -log(clipped if actual_occurred else 1.0 - clipped)


def _movement_source_refs(movement: Mapping[str, object]) -> list[str]:
    refs: list[str] = []
    for point in _list_of_mappings(movement.get("points")):
        ref = point.get("source_snapshot_ref")
        if isinstance(ref, str) and ref:
            refs.append(ref)
    return refs


def _band_for_value(value: float, bands: Sequence[str]) -> str:
    for band in bands:
        lower, upper = _parse_band(band)
        if value >= lower and (upper is None or value < upper or value == upper == 1.0):
            return band
    return "unbucketed"


def _parse_band(value: str) -> tuple[float, float | None]:
    parts = value.split(":", maxsplit=1)
    if len(parts) != 2 or not parts[0]:
        raise ValueError("bands must use min:max")
    lower = float(parts[0])
    upper = float(parts[1]) if parts[1] else None
    if upper is not None and lower > upper:
        raise ValueError("band lower bound cannot exceed upper bound")
    return lower, upper


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _list_of_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _first_float(
    mapping: Mapping[str, object],
    keys: Sequence[str],
) -> float | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float):
            return float(value)
    return None


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _optional_delta(
    candidate: float | None,
    baseline: float | None,
) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementSignalDiagnosticOptions,
    observation_count: int,
    skipped_reason_counts: Mapping[str, int],
) -> str:
    payload = {
        "slice_ids": [item.metadata.slice_id for item in historical_slices],
        "as_of_times": [item.as_of_time_utc.isoformat() for item in historical_slices],
        "options": options.model_dump(mode="json"),
        "observation_count": observation_count,
        "skipped_reason_counts": dict(sorted(skipped_reason_counts.items())),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_signal_diagnostics:{digest}"
