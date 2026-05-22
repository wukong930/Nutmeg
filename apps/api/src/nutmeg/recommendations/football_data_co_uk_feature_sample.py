from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime, timedelta
from json import dumps
from pathlib import Path
from re import sub
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.features import (
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations.football_data_co_uk_asian_handicap_coverage import (
    FootballDataCoUkAsianHandicapRow,
    asian_handicap_odds_movements_from_row,
    parse_football_data_co_uk_asian_handicap_row,
)
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

type FootballDataCoUkFeatureSourceKind = Literal["market_movement", "closing_only"]
type FootballDataCoUkPredictionTimePolicy = Literal["fixture_lead", "slice_start"]

FOOTBALL_DATA_CO_UK_FEATURE_SOURCE_URL = "https://www.football-data.co.uk/data.php"
FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION = (
    "football-data-co-uk-market-movement-features-v3.1"
)
FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION = (
    "football-data-co-uk-opening-market-feature-sample-v3.1"
)
FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION = (
    "no-vig-opening-market-probability-v3.1"
)
FOOTBALL_DATA_CO_UK_CLOSING_ONLY_FEATURE_VERSION = (
    "football-data-co-uk-closing-odds-features-v3.1"
)
FOOTBALL_DATA_CO_UK_CLOSING_ONLY_MODEL_VERSION = (
    "football-data-co-uk-closing-market-feature-sample-v3.1"
)
FOOTBALL_DATA_CO_UK_CLOSING_ONLY_CALIBRATION_VERSION = (
    "no-vig-closing-market-probability-v3.1"
)
FOOTBALL_DATA_CO_UK_PREMATCH_SOURCE = "football-data.co.uk historical CSV"
DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID = (
    "football_data_co_uk_epl_2024_2025_market_features_v1"
)
DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SUITE_ID = (
    "football_data_co_uk_market_feature_sample_suite_v1"
)
DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_BATCH_SUITE_ID = (
    "football_data_co_uk_market_feature_multi_season_suite_v1"
)

_OUTCOME_TO_ODDS_SUFFIX = {
    "home_win": "H",
    "draw": "D",
    "away_win": "A",
}
_ODDS_PREFIX_PAIRS = (
    ("Avg", "AvgC"),
    ("B365", "B365C"),
    ("Max", "MaxC"),
    ("PS", "PSC"),
    ("BW", "BWC"),
    ("WH", "WHC"),
)
_COMPETITION_METADATA_BY_CODE = {
    "D1": ("BUNDESLIGA", "Bundesliga"),
    "D2": ("GER_2_BUNDESLIGA", "2. Bundesliga"),
    "E0": ("EPL", "EPL"),
    "E1": ("ENG_CHAMPIONSHIP", "Championship"),
    "F2": ("FRA_LIGUE_2", "Ligue 2"),
    "F1": ("LIGUE_1", "Ligue 1"),
    "I2": ("ITA_SERIE_B", "Serie B"),
    "I1": ("SERIE_A", "Serie A"),
    "JPN": ("JPN_J1", "J1"),
    "N1": ("NED_EREDIVISIE", "Eredivisie"),
    "P1": ("PRT_PRIMEIRA_LIGA", "Primeira Liga"),
    "SP2": ("ESP_SEGUNDA_DIVISION", "Segunda Division"),
    "SP1": ("LA_LIGA", "La Liga"),
}
_CLOSING_ONLY_ODDS_PREFIXES = ("AvgC", "MaxC", "PSC", "B365C", "BFEC")


class FootballDataCoUkPrematchFeatureSampleOptions(BaseModel):
    slice_id: str = DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID
    name: str = "Football-Data.co.uk EPL 2024-2025 market feature sample"
    competition_id: str = "EPL"
    season: str = "2024-2025"
    max_rows: int = Field(default=24, ge=1)
    prediction_lead_minutes: int = Field(default=5, ge=1)
    opening_snapshot_lead_days: int = Field(default=7, ge=1)
    model_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION
    feature_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION
    calibration_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION
    feature_source_kind: FootballDataCoUkFeatureSourceKind = "market_movement"
    source_seasons: tuple[str, ...] = ()
    prediction_time_policy: FootballDataCoUkPredictionTimePolicy = "fixture_lead"
    include_asian_handicap_features: bool = False


class FootballDataCoUkPrematchFeatureSampleResult(BaseModel):
    historical_slice: HistoricalRecommendationSlice
    completeness_result: HistoricalFeatureCompletenessResult
    input_path: Path
    row_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    selected_odds_pair_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class FootballDataCoUkPrematchFeatureBatchOptions(BaseModel):
    suite_id: str = DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_BATCH_SUITE_ID
    name: str = "Football-Data.co.uk market feature multi-season suite"
    max_rows_per_slice: int = Field(default=24, ge=1)
    prediction_lead_minutes: int = Field(default=5, ge=1)
    opening_snapshot_lead_days: int = Field(default=7, ge=1)
    min_feature_data_quality_score: float = Field(default=70.0, ge=0.0, le=100.0)
    model_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION
    feature_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION
    calibration_version: str = FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION
    feature_source_kind: FootballDataCoUkFeatureSourceKind = "market_movement"
    source_seasons: tuple[str, ...] = ()
    prediction_time_policy: FootballDataCoUkPredictionTimePolicy = "fixture_lead"
    include_asian_handicap_features: bool = False


class FootballDataCoUkPrematchFeatureBatchSliceResult(BaseModel):
    input_path: Path
    output_path: Path
    completeness_output_path: Path
    slice_id: str
    competition_id: str
    season: str
    fixture_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    completeness_passed: bool
    warnings: list[str] = Field(default_factory=list)


class FootballDataCoUkPrematchFeatureBatchResult(BaseModel):
    manifest: HistoricalRecommendationSuiteManifest
    manifest_path: Path | None = None
    slice_results: list[FootballDataCoUkPrematchFeatureBatchSliceResult] = (
        Field(default_factory=list)
    )
    failed_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _ParsedMarketFeatureRow(BaseModel):
    row_number: int = Field(ge=2)
    source_division: str | None = None
    source_season: str | None = None
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    opening_odds_prefix: str
    closing_odds_prefix: str
    opening_decimal_odds: dict[str, float]
    closing_decimal_odds: dict[str, float]
    opening_probabilities: dict[str, float]
    closing_probabilities: dict[str, float]
    opening_overround: float
    closing_overround: float
    asian_handicap: FootballDataCoUkAsianHandicapRow | None = None


def build_football_data_co_uk_prematch_feature_sample(
    input_path: Path | str,
    *,
    options: FootballDataCoUkPrematchFeatureSampleOptions | None = None,
    completeness_options: HistoricalFeatureCompletenessOptions | None = None,
) -> FootballDataCoUkPrematchFeatureSampleResult:
    resolved_options = options or FootballDataCoUkPrematchFeatureSampleOptions()
    resolved_input_path = Path(input_path)
    warnings: list[str] = []
    parsed_rows, raw_row_count = _parse_rows(
        resolved_input_path,
        options=resolved_options,
        warnings=warnings,
    )
    if not parsed_rows:
        raise ValueError(
            "football-data.co.uk feature sample produced no importable fixtures: "
            f"{resolved_input_path}"
        )

    prediction_time_override = _prediction_time_override(
        parsed_rows,
        options=resolved_options,
    )
    fixture_ids_seen: set[str] = set()
    selected_pair_counts: Counter[str] = Counter()
    fixtures: list[HistoricalFixture] = []
    for row in parsed_rows:
        fixture_id = _dedupe_fixture_id(
            _fixture_id(row, options=resolved_options),
            seen_fixture_ids=fixture_ids_seen,
        )
        selected_pair = _selected_pair_label(row, options=resolved_options)
        selected_pair_counts[selected_pair] += 1
        fixtures.append(
            _historical_fixture(
                row,
                fixture_id=fixture_id,
                input_path=resolved_input_path,
                selected_odds_pair=selected_pair,
                options=resolved_options,
                prediction_time_override=prediction_time_override,
            )
        )

    as_of_time = min(fixture.prediction_time_utc for fixture in fixtures)
    historical_slice = HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=resolved_options.slice_id,
            name=resolved_options.name,
            competition_id=resolved_options.competition_id,
            season=resolved_options.season,
            result_source="football-data.co.uk CSV final score",
            odds_source=_odds_source_label(resolved_options),
            prediction_source=_prediction_source_label(resolved_options),
            source_urls=[FOOTBALL_DATA_CO_UK_FEATURE_SOURCE_URL],
            notes=_metadata_notes(resolved_options),
        ),
        as_of_time_utc=_aware_utc(as_of_time),
        fixtures=fixtures,
    )
    completeness = evaluate_historical_feature_completeness(
        historical_slice,
        options=completeness_options or _market_feature_completeness_options(
            min_fixture_count=len(fixtures),
            feature_source_kind=resolved_options.feature_source_kind,
        ),
    )
    summary: dict[str, object] = {
        "calculation_basis": "football_data_co_uk_prematch_feature_sample_v3_1",
        "input_path": str(resolved_input_path),
        "slice_id": historical_slice.metadata.slice_id,
        "competition_id": historical_slice.metadata.competition_id,
        "season": historical_slice.metadata.season,
        "row_count": raw_row_count,
        "fixture_count": len(fixtures),
        "prediction_count": sum(len(fixture.predictions) for fixture in fixtures),
        "feature_snapshot_count": sum(
            1 for fixture in fixtures if fixture.feature_snapshot is not None
        ),
        "selected_odds_pair_counts": dict(selected_pair_counts),
        "feature_source_kind": resolved_options.feature_source_kind,
        "source_seasons": list(resolved_options.source_seasons),
        "prediction_time_policy": resolved_options.prediction_time_policy,
        "include_asian_handicap_features": resolved_options.include_asian_handicap_features,
        "asian_handicap_feature_fixture_count": sum(
            1
            for fixture in fixtures
            if _fixture_has_asian_handicap_features(fixture)
        ),
        "completeness_passed": completeness.passed,
        "completeness_key": completeness.completeness_key,
        "warnings": [*warnings, *completeness.warnings],
    }
    return FootballDataCoUkPrematchFeatureSampleResult(
        historical_slice=historical_slice,
        completeness_result=completeness,
        input_path=resolved_input_path,
        row_count=raw_row_count,
        fixture_count=len(fixtures),
        selected_odds_pair_counts=dict(selected_pair_counts),
        warnings=[*warnings, *completeness.warnings],
        summary_json=summary,
    )


def build_football_data_co_uk_prematch_feature_batch(
    input_paths: Sequence[Path | str],
    *,
    output_dir: Path | str,
    completeness_output_dir: Path | str,
    suite_manifest_path: Path | str | None = None,
    options: FootballDataCoUkPrematchFeatureBatchOptions | None = None,
) -> FootballDataCoUkPrematchFeatureBatchResult:
    resolved_options = options or FootballDataCoUkPrematchFeatureBatchOptions()
    resolved_output_dir = Path(output_dir)
    resolved_completeness_output_dir = Path(completeness_output_dir)
    resolved_manifest_path = (
        Path(suite_manifest_path) if suite_manifest_path is not None else None
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_completeness_output_dir.mkdir(parents=True, exist_ok=True)
    if resolved_manifest_path is not None:
        resolved_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    slice_entries: list[HistoricalRecommendationSuiteManifestSlice] = []
    slice_results: list[FootballDataCoUkPrematchFeatureBatchSliceResult] = []
    failed_inputs: list[str] = []
    warnings: list[str] = []
    total_fixtures = 0
    total_rows = 0
    for raw_input_path in input_paths:
        input_path = Path(raw_input_path)
        sample_options_items = _batch_sample_options(input_path, options=resolved_options)
        for sample_options in sample_options_items:
            slice_result = _build_batch_slice(
                input_path,
                output_dir=resolved_output_dir,
                completeness_output_dir=resolved_completeness_output_dir,
                manifest_path=resolved_manifest_path,
                options=resolved_options,
                sample_options=sample_options,
            )
            if isinstance(slice_result, str):
                failed_inputs.append(str(input_path))
                warnings.append(slice_result)
                continue
            (
                batch_slice_result,
                manifest_entry,
                fixture_count,
                row_count,
                slice_warnings,
            ) = slice_result
            total_fixtures += fixture_count
            total_rows += row_count
            warnings.extend(slice_warnings)
            slice_results.append(batch_slice_result)
            slice_entries.append(manifest_entry)

    if not slice_entries:
        raise ValueError("football-data.co.uk feature batch produced no slices")

    manifest = HistoricalRecommendationSuiteManifest(
        suite_id=resolved_options.suite_id,
        name=resolved_options.name,
        description=_batch_manifest_description(resolved_options),
        tags=_batch_manifest_tags(resolved_options),
        notes=_batch_manifest_notes(resolved_options),
        slices=slice_entries,
    )
    if resolved_manifest_path is not None:
        resolved_manifest_path.write_text(
            f"{manifest.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    summary: dict[str, object] = {
        "calculation_basis": "football_data_co_uk_prematch_feature_batch_v3_1",
        "suite_id": resolved_options.suite_id,
        "manifest_path": (
            str(resolved_manifest_path) if resolved_manifest_path is not None else None
        ),
        "feature_source_kind": resolved_options.feature_source_kind,
        "source_seasons": list(resolved_options.source_seasons),
        "prediction_time_policy": resolved_options.prediction_time_policy,
        "include_asian_handicap_features": (
            resolved_options.include_asian_handicap_features
        ),
        "slice_count": len(slice_results),
        "fixture_count": total_fixtures,
        "row_count": total_rows,
        "failed_input_count": len(failed_inputs),
        "failed_inputs": failed_inputs,
        "completeness_passed_slice_count": sum(
            1 for item in slice_results if item.completeness_passed
        ),
        "slice_ids": [item.slice_id for item in slice_results],
        "warnings": warnings,
    }
    return FootballDataCoUkPrematchFeatureBatchResult(
        manifest=manifest,
        manifest_path=resolved_manifest_path,
        slice_results=slice_results,
        failed_inputs=failed_inputs,
        warnings=warnings,
        summary_json=summary,
    )


def _build_batch_slice(
    input_path: Path,
    *,
    output_dir: Path,
    completeness_output_dir: Path,
    manifest_path: Path | None,
    options: FootballDataCoUkPrematchFeatureBatchOptions,
    sample_options: FootballDataCoUkPrematchFeatureSampleOptions,
) -> tuple[
    FootballDataCoUkPrematchFeatureBatchSliceResult,
    HistoricalRecommendationSuiteManifestSlice,
    int,
    int,
    list[str],
] | str:
    output_path = output_dir / f"{sample_options.slice_id}.json"
    completeness_output_path = (
        completeness_output_dir
        / f"{sample_options.slice_id}_feature_completeness.json"
    )
    try:
        sample_result = build_football_data_co_uk_prematch_feature_sample(
            input_path,
            options=sample_options,
            completeness_options=HistoricalFeatureCompletenessOptions(
                min_fixture_count=1,
                min_feature_snapshot_coverage=1.0,
                min_odds_movement_coverage=(
                    1.0 if options.feature_source_kind == "market_movement" else 0.0
                ),
                min_source_ref_coverage=1.0,
                min_average_feature_data_quality_score=(
                    options.min_feature_data_quality_score
                ),
                min_feature_data_quality_score=options.min_feature_data_quality_score,
            ),
        )
    except ValueError as exc:
        return (
            "football_data_co_uk_feature_batch:skipped_input:"
            f"{input_path}:{exc}"
        )

    output_path.write_text(
        f"{sample_result.historical_slice.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    completeness_output_path.write_text(
        f"{sample_result.completeness_result.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    warnings: list[str] = []
    if not sample_result.completeness_result.passed:
        warnings.append(
            "football_data_co_uk_feature_batch:completeness_failed:"
            f"{sample_options.slice_id}"
        )
    slice_result = FootballDataCoUkPrematchFeatureBatchSliceResult(
        input_path=input_path,
        output_path=output_path,
        completeness_output_path=completeness_output_path,
        slice_id=sample_options.slice_id,
        competition_id=sample_options.competition_id,
        season=sample_options.season,
        fixture_count=sample_result.fixture_count,
        row_count=sample_result.row_count,
        completeness_passed=sample_result.completeness_result.passed,
        warnings=sample_result.warnings,
    )
    manifest_base_dir = manifest_path.parent if manifest_path is not None else Path.cwd()
    manifest_entry = HistoricalRecommendationSuiteManifestSlice(
        slice_path=_relative_path(output_path, base_dir=manifest_base_dir),
        enabled=True,
        tags=_slice_manifest_tags(sample_options),
        notes=[
            f"Generated from {input_path} by "
            "nutmeg-recommendation-football-data-co-uk-feature-batch."
        ],
    )
    return (
        slice_result,
        manifest_entry,
        sample_result.fixture_count,
        sample_result.row_count,
        warnings,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = build_football_data_co_uk_prematch_feature_sample(
        args.input_csv_path,
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


def batch_main(argv: Sequence[str] | None = None) -> None:
    args = _parse_batch_args(argv)
    result = build_football_data_co_uk_prematch_feature_batch(
        args.input_csv_paths,
        output_dir=args.output_dir,
        completeness_output_dir=args.completeness_output_dir,
        suite_manifest_path=args.suite_manifest_output_path,
        options=_batch_options_from_args(args),
    )
    print(
        dumps(
            result.summary_json,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if (
        result.summary_json["completeness_passed_slice_count"]
        != result.summary_json["slice_count"]
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _parse_rows(
    input_path: Path,
    *,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
    warnings: list[str],
) -> tuple[list[_ParsedMarketFeatureRow], int]:
    parsed_rows: list[_ParsedMarketFeatureRow] = []
    raw_row_count = 0
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = DictReader(handle)
        for row_number, raw_row in enumerate(reader, start=2):
            raw_row_count += 1
            if len(parsed_rows) >= options.max_rows:
                continue
            if options.source_seasons:
                source_season = _first_text(raw_row, ("Season",))
                if source_season not in options.source_seasons:
                    continue
            parsed = _parse_row(
                raw_row,
                input_path=input_path,
                row_number=row_number,
                options=options,
                warnings=warnings,
            )
            if parsed is not None:
                parsed_rows.append(parsed)
    return parsed_rows, raw_row_count


def _parse_row(
    raw_row: Mapping[str, str | None],
    *,
    input_path: Path,
    row_number: int,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
    warnings: list[str],
) -> _ParsedMarketFeatureRow | None:
    home_team = _first_text(raw_row, ("HomeTeam", "Home"))
    away_team = _first_text(raw_row, ("AwayTeam", "Away"))
    match_date = _first_text(raw_row, ("Date",))
    home_goals = _first_int(raw_row, ("FTHG", "HG"))
    away_goals = _first_int(raw_row, ("FTAG", "AG"))
    if home_team is None or away_team is None or match_date is None:
        warnings.append(f"football_data_co_uk_feature_sample:row_{row_number}:missing_identity")
        return None
    if home_goals is None or away_goals is None:
        warnings.append(f"football_data_co_uk_feature_sample:row_{row_number}:missing_score")
        return None
    kickoff_time = _parse_kickoff_time(
        match_date,
        raw_row.get("Time") or "12:00",
    )
    if kickoff_time is None:
        warnings.append(
            f"football_data_co_uk_feature_sample:row_{row_number}:invalid_kickoff"
        )
        return None

    selected = _select_odds_pair(raw_row, feature_source_kind=options.feature_source_kind)
    if selected is None:
        missing_reason = (
            "missing_odds_movement"
            if options.feature_source_kind == "market_movement"
            else "missing_closing_odds"
        )
        warnings.append(
            f"football_data_co_uk_feature_sample:row_{row_number}:{missing_reason}"
        )
        return None
    opening_prefix, closing_prefix, opening_odds, closing_odds = selected
    opening_probabilities, opening_overround = _no_vig_probabilities(opening_odds)
    closing_probabilities, closing_overround = _no_vig_probabilities(closing_odds)
    asian_handicap = (
        parse_football_data_co_uk_asian_handicap_row(
            raw_row,
            input_path=input_path,
            row_number=row_number,
        )
        if options.include_asian_handicap_features
        else None
    )
    return _ParsedMarketFeatureRow(
        row_number=row_number,
        source_division=_first_text(raw_row, ("Div", "League")),
        source_season=_first_text(raw_row, ("Season",)),
        kickoff_time_utc=kickoff_time,
        home_team_name=home_team,
        away_team_name=away_team,
        actual_home_goals=home_goals,
        actual_away_goals=away_goals,
        opening_odds_prefix=opening_prefix,
        closing_odds_prefix=closing_prefix,
        opening_decimal_odds=opening_odds,
        closing_decimal_odds=closing_odds,
        opening_probabilities=opening_probabilities,
        closing_probabilities=closing_probabilities,
        opening_overround=opening_overround,
        closing_overround=closing_overround,
        asian_handicap=asian_handicap,
    )


def _prediction_time_override(
    parsed_rows: Sequence[_ParsedMarketFeatureRow],
    *,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
) -> datetime | None:
    if options.prediction_time_policy != "slice_start":
        return None
    first_kickoff = min(_aware_utc(row.kickoff_time_utc) for row in parsed_rows)
    return first_kickoff - timedelta(minutes=options.prediction_lead_minutes)


def _historical_fixture(
    row: _ParsedMarketFeatureRow,
    *,
    fixture_id: str,
    input_path: Path,
    selected_odds_pair: str,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
    prediction_time_override: datetime | None = None,
) -> HistoricalFixture:
    kickoff_time = _aware_utc(row.kickoff_time_utc)
    prediction_time = (
        _aware_utc(prediction_time_override)
        if prediction_time_override is not None
        else kickoff_time - timedelta(minutes=options.prediction_lead_minutes)
    )
    feature_snapshot = build_structured_prematch_feature_snapshot(
        fixture_id=fixture_id,
        competition_id=options.competition_id,
        kickoff_time_utc=kickoff_time,
        feature_time_utc=prediction_time,
        feature_version=options.feature_version,
        historical_stats_completeness=0.75,
        provider_consistency=0.85,
        prematch_features=_prematch_market_features(
            row,
            fixture_id=fixture_id,
            feature_time_utc=prediction_time,
            opening_snapshot_time_utc=kickoff_time
            - timedelta(days=options.opening_snapshot_lead_days),
            selected_odds_pair=selected_odds_pair,
            input_path=input_path,
            feature_source_kind=options.feature_source_kind,
        ),
    )
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=options.competition_id,
        kickoff_time_utc=kickoff_time,
        home_team_name=row.home_team_name,
        away_team_name=row.away_team_name,
        actual_home_goals=row.actual_home_goals,
        actual_away_goals=row.actual_away_goals,
        prediction_time_utc=prediction_time,
        model_version=options.model_version,
        feature_version=options.feature_version,
        calibration_version=options.calibration_version,
        predictions=[
            _market_prediction(outcome, row=row, feature_source_kind=options.feature_source_kind)
            for outcome in ("home_win", "draw", "away_win")
        ],
        feature_snapshot=feature_snapshot,
        metadata_json={
            "source": "football-data.co.uk",
            "source_division": row.source_division,
            "source_season": row.source_season,
            "source_row_number": row.row_number,
            "csv_file_name": input_path.name,
            "selected_odds_pair": selected_odds_pair,
            "opening_overround": round(row.opening_overround, 6),
            "closing_overround": round(row.closing_overround, 6),
            "feature_source_kind": options.feature_source_kind,
            "asian_handicap_available": row.asian_handicap is not None,
        },
    )


def _prematch_market_features(
    row: _ParsedMarketFeatureRow,
    *,
    fixture_id: str,
    feature_time_utc: datetime,
    opening_snapshot_time_utc: datetime,
    selected_odds_pair: str,
    input_path: Path,
    feature_source_kind: FootballDataCoUkFeatureSourceKind,
) -> StructuredPrematchFeatureSet:
    asian_handicap_movements = (
        asian_handicap_odds_movements_from_row(
            row.asian_handicap,
            feature_time_utc=feature_time_utc,
            opening_snapshot_time_utc=opening_snapshot_time_utc,
        )
        if row.asian_handicap is not None
        else []
    )
    if feature_source_kind == "closing_only":
        odds_movements = [
            PrematchOddsMovementFeature(
                market_type="1x2",
                outcome=outcome,
                points=[
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc,
                        market_type="1x2",
                        outcome=outcome,
                        decimal_odds=row.closing_decimal_odds[outcome],
                        fair_probability=row.closing_probabilities[outcome],
                        source=FOOTBALL_DATA_CO_UK_PREMATCH_SOURCE,
                        source_snapshot_ref=(
                            f"{input_path.name}:row_{row.row_number}:"
                            f"{row.closing_odds_prefix}{_OUTCOME_TO_ODDS_SUFFIX[outcome]}"
                        ),
                    )
                ],
                bookmaker_disagreement=0.0,
                market_delay_signal=0.0,
                metadata_json={
                    "source_kind": "closing_only",
                    "selected_odds_pair": selected_odds_pair,
                    "exact_snapshot_times_available": False,
                    "closing_snapshot_time_policy": "prediction_time_pre_kickoff",
                    "movement_available": False,
                },
            )
            for outcome in ("home_win", "draw", "away_win")
        ]
        odds_movements.extend(asian_handicap_movements)
        return StructuredPrematchFeatureSet(
            odds_movements=odds_movements,
            metadata_json={
                "source": "football-data.co.uk",
                "fixture_id": fixture_id,
                "source_kind": "closing_only",
                "lineup_available": False,
                "availability_available": False,
                "semantic_news_available": False,
                "selected_odds_pair": selected_odds_pair,
                "movement_available": False,
                "asian_handicap_available": bool(asian_handicap_movements),
            },
        )
    return StructuredPrematchFeatureSet(
        odds_movements=[
            PrematchOddsMovementFeature(
                market_type="1x2",
                outcome=outcome,
                points=[
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=opening_snapshot_time_utc,
                        market_type="1x2",
                        outcome=outcome,
                        decimal_odds=row.opening_decimal_odds[outcome],
                        fair_probability=row.opening_probabilities[outcome],
                        source=FOOTBALL_DATA_CO_UK_PREMATCH_SOURCE,
                        source_snapshot_ref=(
                            f"{input_path.name}:row_{row.row_number}:"
                            f"{row.opening_odds_prefix}{_OUTCOME_TO_ODDS_SUFFIX[outcome]}"
                        ),
                    ),
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc,
                        market_type="1x2",
                        outcome=outcome,
                        decimal_odds=row.closing_decimal_odds[outcome],
                        fair_probability=row.closing_probabilities[outcome],
                        source=FOOTBALL_DATA_CO_UK_PREMATCH_SOURCE,
                        source_snapshot_ref=(
                            f"{input_path.name}:row_{row.row_number}:"
                            f"{row.closing_odds_prefix}{_OUTCOME_TO_ODDS_SUFFIX[outcome]}"
                        ),
                    ),
                ],
                bookmaker_disagreement=_bookmaker_disagreement_proxy(
                    row,
                    outcome=outcome,
                ),
                market_delay_signal=0.0,
                metadata_json={
                    "source_kind": "market_movement",
                    "selected_odds_pair": selected_odds_pair,
                    "exact_snapshot_times_available": False,
                    "opening_snapshot_time_policy": "kickoff_minus_configured_days",
                    "closing_snapshot_time_policy": "prediction_time_pre_kickoff",
                },
            )
            for outcome in ("home_win", "draw", "away_win")
        ]
        + asian_handicap_movements,
        metadata_json={
            "source": "football-data.co.uk",
            "fixture_id": fixture_id,
            "source_kind": "market_movement",
            "lineup_available": False,
            "availability_available": False,
            "semantic_news_available": False,
            "selected_odds_pair": selected_odds_pair,
            "asian_handicap_available": bool(asian_handicap_movements),
        },
    )


def _market_prediction(
    outcome: str,
    *,
    row: _ParsedMarketFeatureRow,
    feature_source_kind: FootballDataCoUkFeatureSourceKind,
) -> HistoricalMarketPrediction:
    probability = row.opening_probabilities[outcome]
    market_probability = 1.0 / row.opening_decimal_odds[outcome]
    closing_probability = row.closing_probabilities[outcome]
    probability_delta = closing_probability - probability
    odds_stability = max(0.0, 1.0 - abs(probability_delta) * 4.0)
    volatility = min(1.0, abs(probability_delta) * 3.0)
    return HistoricalMarketPrediction(
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=row.opening_decimal_odds[outcome],
        market_probability=market_probability,
        model_edge=None,
        data_quality_score=72.0,
        model_confidence_score=0.66,
        calibration_score=0.70,
        upset_protection_score=_upset_protection_score(
            outcome=outcome,
            probability=probability,
            decimal_odds=row.closing_decimal_odds[outcome],
        ),
        odds_stability_score=odds_stability,
        volatility_penalty=volatility,
        metadata_json={
            "source": "football-data.co.uk",
            "baseline_probability_source": (
                "opening_no_vig_probability"
                if feature_source_kind == "market_movement"
                else "closing_no_vig_probability"
            ),
            "feature_source_kind": feature_source_kind,
            "opening_probability": round(probability, 6),
            "closing_probability": round(closing_probability, 6),
            "probability_delta": round(probability_delta, 6),
            "opening_decimal_odds": row.opening_decimal_odds[outcome],
            "closing_decimal_odds": row.closing_decimal_odds[outcome],
            "opening_odds_prefix": row.opening_odds_prefix,
            "closing_odds_prefix": row.closing_odds_prefix,
        },
    )


def _fixture_has_asian_handicap_features(fixture: HistoricalFixture) -> bool:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return False
    prematch_context = snapshot.features_json.get("prematch_context")
    if not isinstance(prematch_context, dict):
        return False
    odds_movements = prematch_context.get("odds_movement")
    if not isinstance(odds_movements, list):
        return False
    return any(
        isinstance(item, dict) and item.get("market_type") == "asian_handicap"
        for item in odds_movements
    )


def _select_odds_pair(
    row: Mapping[str, str | None],
    *,
    feature_source_kind: FootballDataCoUkFeatureSourceKind,
) -> tuple[str, str, dict[str, float], dict[str, float]] | None:
    if feature_source_kind == "closing_only":
        return _select_closing_only_odds_pair(row)
    return _select_opening_closing_odds_pair(row)


def _select_opening_closing_odds_pair(
    row: Mapping[str, str | None],
) -> tuple[str, str, dict[str, float], dict[str, float]] | None:
    for opening_prefix, closing_prefix in _ODDS_PREFIX_PAIRS:
        opening_odds = _odds_triplet(row, opening_prefix)
        closing_odds = _odds_triplet(row, closing_prefix)
        if opening_odds is not None and closing_odds is not None:
            return opening_prefix, closing_prefix, opening_odds, closing_odds
    return None


def _select_closing_only_odds_pair(
    row: Mapping[str, str | None],
) -> tuple[str, str, dict[str, float], dict[str, float]] | None:
    for closing_prefix in _CLOSING_ONLY_ODDS_PREFIXES:
        closing_odds = _odds_triplet(row, closing_prefix)
        if closing_odds is not None:
            return closing_prefix, closing_prefix, closing_odds, closing_odds
    return None


def _odds_triplet(
    row: Mapping[str, str | None],
    prefix: str,
) -> dict[str, float] | None:
    odds: dict[str, float] = {}
    for outcome, suffix in _OUTCOME_TO_ODDS_SUFFIX.items():
        decimal_odds = _first_float(row, (f"{prefix}{suffix}",))
        if decimal_odds is None or decimal_odds <= 1.01:
            return None
        odds[outcome] = decimal_odds
    return odds


def _no_vig_probabilities(
    decimal_odds: Mapping[str, float],
) -> tuple[dict[str, float], float]:
    raw = {outcome: 1.0 / odds for outcome, odds in decimal_odds.items()}
    overround = sum(raw.values())
    if overround <= 0:
        raise ValueError("invalid odds overround")
    return {outcome: value / overround for outcome, value in raw.items()}, overround


def _bookmaker_disagreement_proxy(
    row: _ParsedMarketFeatureRow,
    *,
    outcome: str,
) -> float:
    opening = row.opening_probabilities[outcome]
    closing = row.closing_probabilities[outcome]
    return min(1.0, abs(closing - opening) * 2.0)


def _upset_protection_score(
    *,
    outcome: str,
    probability: float,
    decimal_odds: float,
) -> float:
    if outcome == "home_win" or decimal_odds < 2.80:
        return 0.0
    return round(min(1.0, max(0.0, probability * (decimal_odds - 1.0) / 3.0)), 4)


def _market_feature_completeness_options(
    *,
    min_fixture_count: int,
    feature_source_kind: FootballDataCoUkFeatureSourceKind,
) -> HistoricalFeatureCompletenessOptions:
    min_feature_quality = 70.0 if feature_source_kind == "market_movement" else 55.0
    return HistoricalFeatureCompletenessOptions(
        min_fixture_count=min_fixture_count,
        min_feature_snapshot_coverage=1.0,
        min_odds_movement_coverage=1.0 if feature_source_kind == "market_movement" else 0.0,
        min_source_ref_coverage=1.0,
        min_average_feature_data_quality_score=min_feature_quality,
        min_feature_data_quality_score=min_feature_quality,
    )


def _odds_source_label(options: FootballDataCoUkPrematchFeatureSampleOptions) -> str:
    if options.feature_source_kind == "closing_only":
        return "football-data.co.uk closing 1X2 odds"
    return "football-data.co.uk opening and closing 1X2 odds"


def _prediction_source_label(options: FootballDataCoUkPrematchFeatureSampleOptions) -> str:
    if options.feature_source_kind == "closing_only":
        return (
            "no-vig closing market probabilities with structured closing-only "
            "feature snapshots"
        )
    return (
        "no-vig opening market probabilities with structured opening-to-closing "
        "market movement feature snapshots"
    )


def _metadata_notes(options: FootballDataCoUkPrematchFeatureSampleOptions) -> list[str]:
    if options.feature_source_kind == "closing_only":
        notes = [
            "Frozen historical closing-only sample built from football-data.co.uk.",
            "Lineup, injury, semantic/news, and opening odds features are absent.",
            "Closing odds are the frozen baseline probabilities for shadow analysis.",
            "This sample must not be treated as opening-to-closing market movement.",
        ]
        if options.prediction_time_policy == "slice_start":
            notes.append(
                "Slice-start prediction time is used only to make frozen shadow "
                "candidate pools replayable; it is not live availability evidence."
            )
        return notes
    return [
        "Frozen historical market-movement sample built from football-data.co.uk.",
        "Lineup, injury, and semantic/news features are intentionally absent.",
        "Opening odds are the frozen baseline probabilities for shadow analysis.",
        "Closing odds are stored only inside FeatureSnapshot odds movement.",
    ]


def _suite_manifest(
    historical_slice: HistoricalRecommendationSlice,
    *,
    slice_path: Path,
    manifest_path: Path,
) -> HistoricalRecommendationSuiteManifest:
    source_kind = _slice_source_kind(historical_slice)
    return HistoricalRecommendationSuiteManifest(
        suite_id=DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SUITE_ID,
        name=f"Football-Data.co.uk {source_kind.replace('_', '-')} feature sample suite",
        description=_single_manifest_description(source_kind),
        tags=["football-data-co-uk", source_kind.replace("_", "-"), "prematch-features"],
        notes=_single_manifest_notes(source_kind),
        slices=[
            HistoricalRecommendationSuiteManifestSlice(
                slice_path=_relative_path(slice_path, base_dir=manifest_path.parent),
                enabled=True,
                tags=["football-data-co-uk", source_kind.replace("_", "-")],
                notes=[
                    f"Slice {historical_slice.metadata.slice_id} generated by "
                    "nutmeg-recommendation-football-data-co-uk-feature-sample."
                ],
            )
        ],
    )


def _single_manifest_description(source_kind: FootballDataCoUkFeatureSourceKind) -> str:
    if source_kind == "closing_only":
        return (
            "Frozen real historical closing-only sample for structured prematch "
            "feature inventory and final-answer baseline experiments."
        )
    return (
        "Frozen real historical market-movement sample for structured prematch "
        "feature completeness and shadow ablation."
    )


def _single_manifest_notes(source_kind: FootballDataCoUkFeatureSourceKind) -> list[str]:
    if source_kind == "closing_only":
        return [
            "Uses historical CSV closing odds only.",
            "Does not contain opening odds, lineup, injury, or semantic/news features.",
            "Must not be treated as opening-to-closing market movement evidence.",
        ]
    return [
        "Uses historical CSV opening and closing odds only.",
        "Does not contain real lineup, injury, or semantic/news features.",
    ]


def _slice_source_kind(
    historical_slice: HistoricalRecommendationSlice,
) -> FootballDataCoUkFeatureSourceKind:
    first_fixture = historical_slice.fixtures[0]
    raw_kind = first_fixture.metadata_json.get("feature_source_kind")
    return "closing_only" if raw_kind == "closing_only" else "market_movement"


def _batch_manifest_description(
    options: FootballDataCoUkPrematchFeatureBatchOptions,
) -> str:
    if options.feature_source_kind == "closing_only":
        return (
            "Frozen multi-season historical closing-only feature samples for "
            "structured pre-match sample coverage and final-answer baselines."
        )
    return (
        "Frozen multi-league historical market-movement feature samples for "
        "structured pre-match feature shadow evaluation."
    )


def _batch_manifest_tags(
    options: FootballDataCoUkPrematchFeatureBatchOptions,
) -> list[str]:
    return [
        "football-data-co-uk",
        options.feature_source_kind.replace("_", "-"),
        "prematch-features",
    ]


def _batch_manifest_notes(
    options: FootballDataCoUkPrematchFeatureBatchOptions,
) -> list[str]:
    if options.feature_source_kind == "closing_only":
        return [
            "Each slice uses closing no-vig 1X2 probabilities as the frozen baseline.",
            "Opening odds are unavailable; this is not market-movement evidence.",
            "Lineup, injury, and semantic/news features are not present in this source.",
        ]
    return [
        "Each slice uses opening no-vig 1X2 probabilities as the frozen baseline.",
        "Closing odds are stored as structured odds-movement features only.",
        "Lineup, injury, and semantic/news features are not present in this source.",
    ]


def _slice_manifest_tags(
    options: FootballDataCoUkPrematchFeatureSampleOptions,
) -> list[str]:
    return [
        "football-data-co-uk",
        options.feature_source_kind.replace("_", "-"),
        options.competition_id.casefold(),
        _slug(options.season),
    ]


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a football-data.co.uk historical market-movement feature sample."
        )
    )
    parser.add_argument("input_csv_path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--completeness-output-path", type=Path)
    parser.add_argument("--suite-manifest-output-path", type=Path)
    parser.add_argument("--slice-id", default=DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_SLICE_ID)
    parser.add_argument(
        "--name",
        default="Football-Data.co.uk EPL 2024-2025 market feature sample",
    )
    parser.add_argument("--competition-id", default="EPL")
    parser.add_argument("--season", default="2024-2025")
    parser.add_argument("--max-rows", type=int, default=24)
    parser.add_argument("--prediction-lead-minutes", type=int, default=5)
    parser.add_argument("--opening-snapshot-lead-days", type=int, default=7)
    parser.add_argument(
        "--feature-source-kind",
        choices=("market_movement", "closing_only"),
        default="market_movement",
    )
    parser.add_argument(
        "--prediction-time-policy",
        choices=("fixture_lead", "slice_start"),
        default="fixture_lead",
    )
    parser.add_argument("--include-asian-handicap-features", action="store_true")
    parser.add_argument("--source-season", action="append", default=[])
    parser.add_argument("--model-version", default=FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION)
    parser.add_argument(
        "--feature-version",
        default=FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION,
    )
    parser.add_argument(
        "--calibration-version",
        default=FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION,
    )
    parser.add_argument("--min-feature-data-quality-score", type=float, default=70.0)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _parse_batch_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a multi-slice football-data.co.uk historical market-movement "
            "feature suite."
        )
    )
    parser.add_argument("input_csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--completeness-output-dir", type=Path, required=True)
    parser.add_argument("--suite-manifest-output-path", type=Path, required=True)
    parser.add_argument(
        "--suite-id",
        default=DEFAULT_FOOTBALL_DATA_CO_UK_PREMATCH_BATCH_SUITE_ID,
    )
    parser.add_argument(
        "--name",
        default="Football-Data.co.uk market feature multi-season suite",
    )
    parser.add_argument("--max-rows-per-slice", type=int, default=24)
    parser.add_argument("--prediction-lead-minutes", type=int, default=5)
    parser.add_argument("--opening-snapshot-lead-days", type=int, default=7)
    parser.add_argument(
        "--feature-source-kind",
        choices=("market_movement", "closing_only"),
        default="market_movement",
    )
    parser.add_argument(
        "--prediction-time-policy",
        choices=("fixture_lead", "slice_start"),
        default="fixture_lead",
    )
    parser.add_argument("--include-asian-handicap-features", action="store_true")
    parser.add_argument("--source-season", action="append", default=[])
    parser.add_argument("--model-version", default=FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION)
    parser.add_argument(
        "--feature-version",
        default=FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION,
    )
    parser.add_argument(
        "--calibration-version",
        default=FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION,
    )
    parser.add_argument("--min-feature-data-quality-score", type=float, default=70.0)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> FootballDataCoUkPrematchFeatureSampleOptions:
    model_version, feature_version, calibration_version = _resolved_version_defaults(args)
    return FootballDataCoUkPrematchFeatureSampleOptions(
        slice_id=args.slice_id,
        name=args.name,
        competition_id=args.competition_id,
        season=args.season,
        max_rows=args.max_rows,
        prediction_lead_minutes=args.prediction_lead_minutes,
        opening_snapshot_lead_days=args.opening_snapshot_lead_days,
        model_version=model_version,
        feature_version=feature_version,
        calibration_version=calibration_version,
        feature_source_kind=args.feature_source_kind,
        source_seasons=tuple(args.source_season),
        prediction_time_policy=args.prediction_time_policy,
        include_asian_handicap_features=args.include_asian_handicap_features,
    )


def _batch_options_from_args(args: Namespace) -> FootballDataCoUkPrematchFeatureBatchOptions:
    model_version, feature_version, calibration_version = _resolved_version_defaults(args)
    return FootballDataCoUkPrematchFeatureBatchOptions(
        suite_id=args.suite_id,
        name=args.name,
        max_rows_per_slice=args.max_rows_per_slice,
        prediction_lead_minutes=args.prediction_lead_minutes,
        opening_snapshot_lead_days=args.opening_snapshot_lead_days,
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        model_version=model_version,
        feature_version=feature_version,
        calibration_version=calibration_version,
        feature_source_kind=args.feature_source_kind,
        source_seasons=tuple(args.source_season),
        prediction_time_policy=args.prediction_time_policy,
        include_asian_handicap_features=args.include_asian_handicap_features,
    )


def _resolved_version_defaults(args: Namespace) -> tuple[str, str, str]:
    if args.feature_source_kind != "closing_only":
        return args.model_version, args.feature_version, args.calibration_version
    model_version = (
        FOOTBALL_DATA_CO_UK_CLOSING_ONLY_MODEL_VERSION
        if args.model_version == FOOTBALL_DATA_CO_UK_PREMATCH_MODEL_VERSION
        else args.model_version
    )
    feature_version = (
        FOOTBALL_DATA_CO_UK_CLOSING_ONLY_FEATURE_VERSION
        if args.feature_version == FOOTBALL_DATA_CO_UK_PREMATCH_FEATURE_VERSION
        else args.feature_version
    )
    calibration_version = (
        FOOTBALL_DATA_CO_UK_CLOSING_ONLY_CALIBRATION_VERSION
        if args.calibration_version == FOOTBALL_DATA_CO_UK_PREMATCH_CALIBRATION_VERSION
        else args.calibration_version
    )
    return model_version, feature_version, calibration_version


def _completeness_options_from_args(
    args: Namespace,
) -> HistoricalFeatureCompletenessOptions:
    return HistoricalFeatureCompletenessOptions(
        min_fixture_count=args.max_rows,
        min_feature_snapshot_coverage=1.0,
        min_odds_movement_coverage=(
            1.0 if args.feature_source_kind == "market_movement" else 0.0
        ),
        min_source_ref_coverage=1.0,
        min_average_feature_data_quality_score=args.min_feature_data_quality_score,
        min_feature_data_quality_score=args.min_feature_data_quality_score,
    )


def _batch_sample_options(
    input_path: Path,
    *,
    options: FootballDataCoUkPrematchFeatureBatchOptions,
) -> list[FootballDataCoUkPrematchFeatureSampleOptions]:
    competition_id, competition_name = _competition_metadata(input_path)
    seasons = options.source_seasons or (_season_from_input_path(input_path),)
    return [
        FootballDataCoUkPrematchFeatureSampleOptions(
            slice_id=_batch_slice_id(
                competition_id=competition_id,
                season=season,
                feature_source_kind=options.feature_source_kind,
            ),
            name=(
                f"Football-Data.co.uk {competition_name} {season} "
                f"{options.feature_source_kind.replace('_', '-')} feature sample"
            ),
            competition_id=competition_id,
            season=season,
            max_rows=options.max_rows_per_slice,
            prediction_lead_minutes=options.prediction_lead_minutes,
            opening_snapshot_lead_days=options.opening_snapshot_lead_days,
            model_version=options.model_version,
            feature_version=options.feature_version,
            calibration_version=options.calibration_version,
            feature_source_kind=options.feature_source_kind,
            source_seasons=(season,) if options.source_seasons else (),
            prediction_time_policy=options.prediction_time_policy,
            include_asian_handicap_features=options.include_asian_handicap_features,
        )
        for season in seasons
    ]


def _competition_metadata(input_path: Path) -> tuple[str, str]:
    code = input_path.stem.strip().upper()
    if code in _COMPETITION_METADATA_BY_CODE:
        return _COMPETITION_METADATA_BY_CODE[code]
    fallback = "_".join(part for part in code.replace("-", "_").split("_") if part)
    competition_id = fallback or "UNKNOWN"
    return competition_id, competition_id.replace("_", " ").title()


def _season_from_input_path(input_path: Path) -> str:
    directory_name = input_path.parent.name.strip()
    if directory_name.isdigit() and len(directory_name) == 4:
        if directory_name.startswith("20"):
            end_year = int(directory_name)
            return f"{end_year - 1}-{end_year}"
        start_year = 2000 + int(directory_name[:2])
        end_year = 2000 + int(directory_name[2:])
        return f"{start_year}-{end_year}"
    return directory_name or "unknown"


def _batch_slice_id(
    *,
    competition_id: str,
    season: str,
    feature_source_kind: FootballDataCoUkFeatureSourceKind,
) -> str:
    feature_slug = (
        "market_features"
        if feature_source_kind == "market_movement"
        else "closing_only_features"
    )
    return (
        "football_data_co_uk_"
        f"{_slug(competition_id)}_{_slug(season)}_{feature_slug}_v1"
    )


def _fixture_id(
    row: _ParsedMarketFeatureRow,
    *,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
) -> str:
    return "_".join(
        [
            "fdcuk_feature",
            _slug(options.competition_id),
            _slug(options.season),
            row.kickoff_time_utc.strftime("%Y_%m_%d"),
            _slug(row.home_team_name),
            _slug(row.away_team_name),
        ]
    )


def _selected_pair_label(
    row: _ParsedMarketFeatureRow,
    *,
    options: FootballDataCoUkPrematchFeatureSampleOptions,
) -> str:
    if options.feature_source_kind == "closing_only":
        return f"{row.closing_odds_prefix}:closing_only"
    return f"{row.opening_odds_prefix}->{row.closing_odds_prefix}"


def _dedupe_fixture_id(
    fixture_id: str,
    *,
    seen_fixture_ids: set[str],
) -> str:
    if fixture_id not in seen_fixture_ids:
        seen_fixture_ids.add(fixture_id)
        return fixture_id
    suffix = 2
    while f"{fixture_id}_{suffix}" in seen_fixture_ids:
        suffix += 1
    deduped = f"{fixture_id}_{suffix}"
    seen_fixture_ids.add(deduped)
    return deduped


def _parse_kickoff_time(date_text: str, time_text: str | None) -> datetime | None:
    cleaned_date = date_text.strip()
    cleaned_time = (time_text or "12:00").strip() or "12:00"
    datetime_text = f"{cleaned_date} {cleaned_time}"
    for datetime_format in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%y %H:%M",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%d-%m-%y %H:%M",
    ):
        try:
            return datetime.strptime(datetime_text, datetime_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _first_text(
    row: Mapping[str, str | None],
    columns: Sequence[str],
) -> str | None:
    for column in columns:
        value = row.get(column)
        if value is not None and value.strip():
            return value.strip()
    return None


def _first_int(
    row: Mapping[str, str | None],
    columns: Sequence[str],
) -> int | None:
    value = _first_text(row, columns)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _first_float(
    row: Mapping[str, str | None],
    columns: Sequence[str],
) -> float | None:
    value = _first_text(row, columns)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _slug(value: str) -> str:
    slug = sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")
    return slug or "unknown"


def _relative_path(path: Path, *, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
