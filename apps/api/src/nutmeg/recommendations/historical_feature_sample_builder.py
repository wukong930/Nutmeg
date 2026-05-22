from __future__ import annotations

from argparse import ArgumentParser, Namespace
from datetime import UTC, datetime, timedelta
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.features import (
    PrematchAvailabilityFeature,
    PrematchLineupFeature,
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    PrematchSemanticSignal,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_feature_completeness import (
    HistoricalFeatureCompletenessOptions,
    HistoricalFeatureCompletenessResult,
    evaluate_historical_feature_completeness,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
)

DEFAULT_ENRICHED_FEATURE_SLICE_ID = "nutmeg_enriched_prematch_feature_sample_v1"
DEFAULT_ENRICHED_FEATURE_MODEL_VERSION = "poisson-v3.1-enriched-feature-sample"
DEFAULT_ENRICHED_FEATURE_VERSION = "features-v3.1-prematch-structured"
DEFAULT_ENRICHED_FEATURE_CALIBRATION_VERSION = "calibration-v3.1-enriched-feature-sample"
DEFAULT_ENRICHED_FEATURE_SOURCE = "deterministic-enriched-feature-sample-v3.1"

type EnrichedFeatureLineupType = Literal["expected", "confirmed", "projected"]


class HistoricalEnrichedFeatureSampleOptions(BaseModel):
    slice_id: str = DEFAULT_ENRICHED_FEATURE_SLICE_ID
    name: str = "Nutmeg enriched pre-match feature sample"
    competition_id: str = "NUTMEG_FEATURE_LAB"
    season: str = "2026-synthetic"
    as_of_time_utc: datetime = Field(
        default_factory=lambda: datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    )
    model_version: str = DEFAULT_ENRICHED_FEATURE_MODEL_VERSION
    feature_version: str = DEFAULT_ENRICHED_FEATURE_VERSION
    calibration_version: str = DEFAULT_ENRICHED_FEATURE_CALIBRATION_VERSION


class HistoricalEnrichedFeatureSampleResult(BaseModel):
    historical_slice: HistoricalRecommendationSlice
    completeness_result: HistoricalFeatureCompletenessResult
    summary_json: dict[str, object] = Field(default_factory=dict)


class _FixtureSpec(BaseModel):
    fixture_id: str
    home_team_name: str
    away_team_name: str
    kickoff_hours_after_as_of: int
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    probabilities: dict[str, float]
    market_probabilities: dict[str, float]
    decimal_odds: dict[str, float]
    lineup_type: EnrichedFeatureLineupType
    lineup_confidence: float = Field(ge=0.0, le=1.0)
    starting_xi_strength: float = Field(ge=0.0, le=1.0)
    bench_dropoff_score: float = Field(ge=0.0, le=1.0)
    key_player_absence_score: float = Field(ge=0.0, le=1.0)
    goalkeeper_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    defender_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    striker_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    opening_home_win_probability: float = Field(ge=0.0, le=1.0)
    current_home_win_probability: float = Field(ge=0.0, le=1.0)
    opening_home_win_odds: float = Field(gt=1.0)
    current_home_win_odds: float = Field(gt=1.0)
    semantic_signal_name: str
    semantic_confidence: float = Field(ge=0.0, le=1.0)
    semantic_evidence: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


def build_enriched_historical_feature_sample(
    *,
    options: HistoricalEnrichedFeatureSampleOptions | None = None,
    completeness_options: HistoricalFeatureCompletenessOptions | None = None,
) -> HistoricalEnrichedFeatureSampleResult:
    resolved_options = options or HistoricalEnrichedFeatureSampleOptions()
    fixtures = [
        _historical_fixture(spec, options=resolved_options)
        for spec in _fixture_specs()
    ]
    historical_slice = HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=resolved_options.slice_id,
            name=resolved_options.name,
            competition_id=resolved_options.competition_id,
            season=resolved_options.season,
            result_source="Deterministic local outcomes for feature-chain smoke tests",
            odds_source="Deterministic pre-match odds movement fixtures",
            prediction_source="Deterministic Nutmeg probabilities with structured features",
            source_urls=[],
            notes=[
                "Synthetic enriched sample for feature completeness and model-input experiments.",
                "Not sourced from live providers and not user-facing recommendation copy.",
            ],
        ),
        as_of_time_utc=_aware_utc(resolved_options.as_of_time_utc),
        fixtures=fixtures,
    )
    completeness = evaluate_historical_feature_completeness(
        historical_slice,
        options=completeness_options or _strict_completeness_options(),
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_enriched_feature_sample_builder_v3_1",
        "slice_id": historical_slice.metadata.slice_id,
        "fixture_count": len(historical_slice.fixtures),
        "feature_snapshot_count": sum(
            1
            for fixture in historical_slice.fixtures
            if fixture.feature_snapshot is not None
        ),
        "completeness_passed": completeness.passed,
        "completeness_key": completeness.completeness_key,
        "warnings": completeness.warnings,
    }
    return HistoricalEnrichedFeatureSampleResult(
        historical_slice=historical_slice,
        completeness_result=completeness,
        summary_json=summary,
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    result = build_enriched_historical_feature_sample(
        options=_options_from_args(args),
        completeness_options=_completeness_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{result.historical_slice.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if args.completeness_output_path is not None:
        args.completeness_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.completeness_output_path.write_text(
            f"{result.completeness_result.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if args.suite_manifest_output_path is not None:
        if args.output_path is None:
            raise ValueError("--suite-manifest-output-path requires --output-path")
        args.suite_manifest_output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = _suite_manifest(
            result.historical_slice,
            slice_path=args.output_path,
            manifest_path=args.suite_manifest_output_path,
        )
        args.suite_manifest_output_path.write_text(
            f"{manifest.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            result.summary_json,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if not result.completeness_result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _historical_fixture(
    spec: _FixtureSpec,
    *,
    options: HistoricalEnrichedFeatureSampleOptions,
) -> HistoricalFixture:
    kickoff_time = _aware_utc(options.as_of_time_utc) + timedelta(
        hours=spec.kickoff_hours_after_as_of
    )
    prediction_time = _aware_utc(options.as_of_time_utc) - timedelta(minutes=30)
    feature_snapshot = build_structured_prematch_feature_snapshot(
        fixture_id=spec.fixture_id,
        competition_id=options.competition_id,
        kickoff_time_utc=kickoff_time,
        feature_time_utc=prediction_time,
        feature_version=options.feature_version,
        historical_stats_completeness=0.82,
        provider_consistency=0.93,
        prematch_features=_prematch_features(spec, feature_time_utc=prediction_time),
    )
    return HistoricalFixture(
        fixture_id=spec.fixture_id,
        competition_id=options.competition_id,
        kickoff_time_utc=kickoff_time,
        home_team_name=spec.home_team_name,
        away_team_name=spec.away_team_name,
        actual_home_goals=spec.actual_home_goals,
        actual_away_goals=spec.actual_away_goals,
        prediction_time_utc=prediction_time,
        model_version=options.model_version,
        feature_version=options.feature_version,
        calibration_version=options.calibration_version,
        predictions=[
            _market_prediction(outcome, spec=spec)
            for outcome in ("home_win", "draw", "away_win")
        ],
        feature_snapshot=feature_snapshot,
        metadata_json={
            "sample_source": DEFAULT_ENRICHED_FEATURE_SOURCE,
            **spec.metadata_json,
        },
    )


def _prematch_features(
    spec: _FixtureSpec,
    *,
    feature_time_utc: datetime,
) -> StructuredPrematchFeatureSet:
    return StructuredPrematchFeatureSet(
        lineup=PrematchLineupFeature(
            lineup_type=spec.lineup_type,
            snapshot_time_utc=feature_time_utc - timedelta(minutes=45),
            expected_lineup_confidence=spec.lineup_confidence,
            starting_xi_strength=spec.starting_xi_strength,
            bench_dropoff_score=spec.bench_dropoff_score,
            source=DEFAULT_ENRICHED_FEATURE_SOURCE,
            source_snapshot_ref=f"lineup:{spec.fixture_id}",
        ),
        availability=PrematchAvailabilityFeature(
            snapshot_time_utc=feature_time_utc - timedelta(hours=2),
            unavailable_key_player_count=1 if spec.key_player_absence_score >= 0.25 else 0,
            doubtful_key_player_count=1 if spec.key_player_absence_score > 0 else 0,
            key_player_absence_score=spec.key_player_absence_score,
            defender_absence_score=spec.defender_absence_score,
            goalkeeper_absence_score=spec.goalkeeper_absence_score,
            striker_absence_score=spec.striker_absence_score,
            source=DEFAULT_ENRICHED_FEATURE_SOURCE,
            source_snapshot_ref=f"availability:{spec.fixture_id}",
        ),
        odds_movements=[
            PrematchOddsMovementFeature(
                market_type="1x2",
                outcome="home_win",
                bookmaker_disagreement=0.06 + abs(
                    spec.current_home_win_probability
                    - spec.opening_home_win_probability
                ),
                market_delay_signal=0.10
                if spec.lineup_confidence < 0.75
                else 0.02,
                points=[
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc - timedelta(hours=8),
                        market_type="1x2",
                        outcome="home_win",
                        decimal_odds=spec.opening_home_win_odds,
                        fair_probability=spec.opening_home_win_probability,
                        bookmaker_count=6,
                        source=DEFAULT_ENRICHED_FEATURE_SOURCE,
                        source_snapshot_ref=f"odds:{spec.fixture_id}:opening",
                    ),
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc - timedelta(minutes=10),
                        market_type="1x2",
                        outcome="home_win",
                        decimal_odds=spec.current_home_win_odds,
                        fair_probability=spec.current_home_win_probability,
                        bookmaker_count=7,
                        source=DEFAULT_ENRICHED_FEATURE_SOURCE,
                        source_snapshot_ref=f"odds:{spec.fixture_id}:current",
                    ),
                ],
            )
        ],
        semantic_signals=[
            PrematchSemanticSignal(
                signal_name=spec.semantic_signal_name,
                source=DEFAULT_ENRICHED_FEATURE_SOURCE,
                confidence=spec.semantic_confidence,
                evidence_text_short=spec.semantic_evidence,
                extracted_at_utc=feature_time_utc - timedelta(minutes=20),
            )
        ],
        metadata_json={
            "sample_source": DEFAULT_ENRICHED_FEATURE_SOURCE,
            "fixture_id": spec.fixture_id,
        },
    )


def _market_prediction(
    outcome: str,
    *,
    spec: _FixtureSpec,
) -> HistoricalMarketPrediction:
    probability = spec.probabilities[outcome]
    market_probability = spec.market_probabilities[outcome]
    return HistoricalMarketPrediction(
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=spec.decimal_odds[outcome],
        market_probability=market_probability,
        model_edge=probability - market_probability,
        data_quality_score=90.0,
        model_confidence_score=0.78,
        calibration_score=0.76,
        upset_protection_score=(
            _metadata_float(spec, "upset_protection_score")
            if outcome != "home_win"
            else 0.0
        ),
        odds_stability_score=max(
            0.0,
            1.0
            - abs(
                spec.current_home_win_probability
                - spec.opening_home_win_probability
            )
            * 3,
        ),
        volatility_penalty=min(
            1.0,
            abs(
                spec.current_home_win_probability
                - spec.opening_home_win_probability
            )
            * 2,
        ),
        metadata_json={
            "sample_source": DEFAULT_ENRICHED_FEATURE_SOURCE,
            "feature_signal_intent": spec.metadata_json.get("feature_signal_intent", ""),
        },
    )


def _fixture_specs() -> list[_FixtureSpec]:
    return [
        _FixtureSpec(
            fixture_id="enriched_feature_001",
            home_team_name="Northbridge FC",
            away_team_name="Harbor City",
            kickoff_hours_after_as_of=7,
            actual_home_goals=2,
            actual_away_goals=0,
            probabilities={"home_win": 0.58, "draw": 0.25, "away_win": 0.17},
            market_probabilities={"home_win": 0.55, "draw": 0.26, "away_win": 0.19},
            decimal_odds={"home_win": 1.80, "draw": 3.70, "away_win": 5.40},
            lineup_type="confirmed",
            lineup_confidence=0.94,
            starting_xi_strength=0.88,
            bench_dropoff_score=0.08,
            key_player_absence_score=0.04,
            opening_home_win_probability=0.54,
            current_home_win_probability=0.57,
            opening_home_win_odds=1.88,
            current_home_win_odds=1.78,
            semantic_signal_name="title_race_pressure",
            semantic_confidence=0.62,
            semantic_evidence="Home side can secure a top-place finish with a win.",
            metadata_json={"feature_signal_intent": "stable_favorite"},
        ),
        _FixtureSpec(
            fixture_id="enriched_feature_002",
            home_team_name="Riverside Albion",
            away_team_name="Eastgate United",
            kickoff_hours_after_as_of=10,
            actual_home_goals=1,
            actual_away_goals=1,
            probabilities={"home_win": 0.42, "draw": 0.31, "away_win": 0.27},
            market_probabilities={"home_win": 0.49, "draw": 0.28, "away_win": 0.23},
            decimal_odds={"home_win": 2.15, "draw": 3.25, "away_win": 3.85},
            lineup_type="expected",
            lineup_confidence=0.66,
            starting_xi_strength=0.69,
            bench_dropoff_score=0.31,
            key_player_absence_score=0.42,
            striker_absence_score=0.48,
            opening_home_win_probability=0.51,
            current_home_win_probability=0.43,
            opening_home_win_odds=1.96,
            current_home_win_odds=2.25,
            semantic_signal_name="press_conference_injury_hint",
            semantic_confidence=0.76,
            semantic_evidence="Coach said the first-choice striker remains doubtful.",
            metadata_json={
                "feature_signal_intent": "favorite_fragility",
                "upset_protection_score": 0.62,
            },
        ),
        _FixtureSpec(
            fixture_id="enriched_feature_003",
            home_team_name="Metro Stars",
            away_team_name="Old Town AFC",
            kickoff_hours_after_as_of=31,
            actual_home_goals=0,
            actual_away_goals=1,
            probabilities={"home_win": 0.34, "draw": 0.29, "away_win": 0.37},
            market_probabilities={"home_win": 0.38, "draw": 0.30, "away_win": 0.32},
            decimal_odds={"home_win": 2.55, "draw": 3.20, "away_win": 2.85},
            lineup_type="expected",
            lineup_confidence=0.78,
            starting_xi_strength=0.74,
            bench_dropoff_score=0.24,
            key_player_absence_score=0.22,
            defender_absence_score=0.33,
            opening_home_win_probability=0.40,
            current_home_win_probability=0.35,
            opening_home_win_odds=2.45,
            current_home_win_odds=2.70,
            semantic_signal_name="rotation_hint",
            semantic_confidence=0.68,
            semantic_evidence="Local reporting expects several defensive rotations.",
            metadata_json={
                "feature_signal_intent": "away_value_shift",
                "upset_protection_score": 0.55,
            },
        ),
        _FixtureSpec(
            fixture_id="enriched_feature_004",
            home_team_name="Southport Rovers",
            away_team_name="Cedar Athletic",
            kickoff_hours_after_as_of=34,
            actual_home_goals=3,
            actual_away_goals=1,
            probabilities={"home_win": 0.61, "draw": 0.23, "away_win": 0.16},
            market_probabilities={"home_win": 0.59, "draw": 0.24, "away_win": 0.17},
            decimal_odds={"home_win": 1.70, "draw": 3.90, "away_win": 5.80},
            lineup_type="confirmed",
            lineup_confidence=0.96,
            starting_xi_strength=0.91,
            bench_dropoff_score=0.10,
            key_player_absence_score=0.08,
            goalkeeper_absence_score=0.05,
            opening_home_win_probability=0.58,
            current_home_win_probability=0.61,
            opening_home_win_odds=1.76,
            current_home_win_odds=1.68,
            semantic_signal_name="european_qualification_pressure",
            semantic_confidence=0.64,
            semantic_evidence="Home side remains in the race for continental qualification.",
            metadata_json={"feature_signal_intent": "confirmed_strength"},
        ),
        _FixtureSpec(
            fixture_id="enriched_feature_005",
            home_team_name="Lakeside Town",
            away_team_name="Forest Borough",
            kickoff_hours_after_as_of=55,
            actual_home_goals=0,
            actual_away_goals=0,
            probabilities={"home_win": 0.36, "draw": 0.34, "away_win": 0.30},
            market_probabilities={"home_win": 0.41, "draw": 0.29, "away_win": 0.30},
            decimal_odds={"home_win": 2.45, "draw": 3.05, "away_win": 3.20},
            lineup_type="projected",
            lineup_confidence=0.72,
            starting_xi_strength=0.71,
            bench_dropoff_score=0.28,
            key_player_absence_score=0.31,
            goalkeeper_absence_score=0.24,
            opening_home_win_probability=0.42,
            current_home_win_probability=0.36,
            opening_home_win_odds=2.35,
            current_home_win_odds=2.62,
            semantic_signal_name="manager_change_recently",
            semantic_confidence=0.70,
            semantic_evidence="Away side appointed an interim manager this week.",
            metadata_json={
                "feature_signal_intent": "draw_risk",
                "upset_protection_score": 0.58,
            },
        ),
        _FixtureSpec(
            fixture_id="enriched_feature_006",
            home_team_name="Westvale",
            away_team_name="Kings Park",
            kickoff_hours_after_as_of=58,
            actual_home_goals=1,
            actual_away_goals=2,
            probabilities={"home_win": 0.29, "draw": 0.28, "away_win": 0.43},
            market_probabilities={"home_win": 0.32, "draw": 0.28, "away_win": 0.40},
            decimal_odds={"home_win": 3.20, "draw": 3.35, "away_win": 2.20},
            lineup_type="expected",
            lineup_confidence=0.84,
            starting_xi_strength=0.77,
            bench_dropoff_score=0.18,
            key_player_absence_score=0.18,
            defender_absence_score=0.22,
            opening_home_win_probability=0.33,
            current_home_win_probability=0.30,
            opening_home_win_odds=3.05,
            current_home_win_odds=3.35,
            semantic_signal_name="relegation_pressure",
            semantic_confidence=0.66,
            semantic_evidence="Home side carries late-season relegation pressure.",
            metadata_json={
                "feature_signal_intent": "away_favorite_with_pressure",
                "upset_protection_score": 0.42,
            },
        ),
    ]


def _strict_completeness_options() -> HistoricalFeatureCompletenessOptions:
    return HistoricalFeatureCompletenessOptions(
        min_fixture_count=6,
        min_feature_snapshot_coverage=1.0,
        min_lineup_coverage=1.0,
        min_availability_coverage=1.0,
        min_odds_movement_coverage=1.0,
        min_semantic_signal_coverage=1.0,
        min_source_ref_coverage=1.0,
        min_average_feature_data_quality_score=85.0,
        min_feature_data_quality_score=80.0,
    )


def _metadata_float(spec: _FixtureSpec, key: str) -> float:
    value = spec.metadata_json.get(key)
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _suite_manifest(
    historical_slice: HistoricalRecommendationSlice,
    *,
    slice_path: Path,
    manifest_path: Path,
) -> HistoricalRecommendationSuiteManifest:
    return HistoricalRecommendationSuiteManifest(
        suite_id="nutmeg_enriched_prematch_feature_suite_v1",
        name="Nutmeg enriched pre-match feature sample suite",
        description=(
            "Deterministic structured feature sample for completeness-gate and "
            "model-input experiments."
        ),
        tags=["enriched-features", "prematch", "feature-completeness"],
        notes=[
            "Synthetic local sample; it does not call provider APIs.",
            "Use as a schema/completeness gate fixture before real feature history.",
        ],
        slices=[
            HistoricalRecommendationSuiteManifestSlice(
                slice_path=_relative_path(slice_path, base_dir=manifest_path.parent),
                enabled=True,
                tags=["enriched-features", "prematch", "sample"],
                notes=["Generated by nutmeg-recommendation-enriched-feature-sample."],
            )
        ],
    )


def _parse_args(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build a deterministic enriched historical pre-match feature sample."
    )
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--completeness-output-path", type=Path)
    parser.add_argument("--suite-manifest-output-path", type=Path)
    parser.add_argument("--slice-id", default=DEFAULT_ENRICHED_FEATURE_SLICE_ID)
    parser.add_argument("--name", default="Nutmeg enriched pre-match feature sample")
    parser.add_argument("--competition-id", default="NUTMEG_FEATURE_LAB")
    parser.add_argument("--season", default="2026-synthetic")
    parser.add_argument("--as-of-time-utc", default="2026-05-08T12:00:00Z")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalEnrichedFeatureSampleOptions:
    return HistoricalEnrichedFeatureSampleOptions(
        slice_id=args.slice_id,
        name=args.name,
        competition_id=args.competition_id,
        season=args.season,
        as_of_time_utc=_datetime(args.as_of_time_utc),
    )


def _completeness_options_from_args(
    _args: Namespace,
) -> HistoricalFeatureCompletenessOptions:
    return _strict_completeness_options()


def _relative_path(path: Path, *, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
