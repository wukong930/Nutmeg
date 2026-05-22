from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime
from json import dumps
from pathlib import Path
from re import sub
from typing import cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestRefreshOptions,
    HistoricalRecommendationSuiteManifestRefreshResult,
    refresh_historical_recommendation_suite_manifest,
)

FOOTBALL_DATA_CO_UK_SOURCE_URL = "https://www.football-data.co.uk/data.php"
FOOTBALL_DATA_CO_UK_DEFAULT_MODEL_VERSION = (
    "football-data-co-uk-market-implied-baseline-v3.1"
)
FOOTBALL_DATA_CO_UK_DEFAULT_FEATURE_VERSION = "football-data-co-uk-csv-v3.1"
FOOTBALL_DATA_CO_UK_DEFAULT_CALIBRATION_VERSION = "no-vig-implied-probability-v3.1"
FOOTBALL_DATA_CO_UK_DEFAULT_ODDS_PREFIX_PRIORITY = (
    "AvgC",
    "Avg",
    "MaxC",
    "Max",
    "B365C",
    "B365",
    "PSC",
    "PS",
    "BWC",
    "BW",
    "WHC",
    "WH",
    "IWC",
    "IW",
    "LBC",
    "LB",
)

_OUTCOME_TO_ODDS_SUFFIX = {
    "home_win": "H",
    "draw": "D",
    "away_win": "A",
}
_OUTCOME_TO_RESULT_CODE = {
    "home_win": "H",
    "draw": "D",
    "away_win": "A",
}


class FootballDataCoUkImportOptions(BaseModel):
    competition_id: str = Field(min_length=1)
    as_of_time_utc: datetime
    season: str | None = None
    slice_id: str | None = None
    slice_id_prefix: str = "football_data_co_uk"
    name: str | None = None
    name_prefix: str = "Football-Data.co.uk"
    result_source: str = "football-data.co.uk CSV final score"
    odds_source: str = "football-data.co.uk CSV 1X2 odds"
    prediction_source: str = "no-vig market-implied baseline from football-data.co.uk odds"
    source_urls: tuple[str, ...] = (FOOTBALL_DATA_CO_UK_SOURCE_URL,)
    notes: tuple[str, ...] = (
        "Generated from football-data.co.uk historical CSV files.",
        "CSV odds are treated as market-implied baseline inputs for backtesting.",
    )
    model_version: str = FOOTBALL_DATA_CO_UK_DEFAULT_MODEL_VERSION
    feature_version: str | None = FOOTBALL_DATA_CO_UK_DEFAULT_FEATURE_VERSION
    calibration_version: str | None = FOOTBALL_DATA_CO_UK_DEFAULT_CALIBRATION_VERSION
    odds_prefix_priority: tuple[str, ...] = FOOTBALL_DATA_CO_UK_DEFAULT_ODDS_PREFIX_PRIORITY
    data_quality_score: float = Field(default=82.0, ge=0.0, le=100.0)
    model_confidence_score: float = Field(default=0.66, ge=0.0, le=1.0)
    calibration_score: float = Field(default=0.70, ge=0.0, le=1.0)
    odds_stability_score: float = Field(default=0.72, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.08, ge=0.0, le=1.0)
    default_kickoff_time: str = "12:00"
    max_rows: int | None = Field(default=None, ge=1)
    min_decimal_odds: float = Field(default=1.01, gt=1.0)
    source_seasons: tuple[str, ...] = ()


class FootballDataCoUkImportResult(BaseModel):
    input_path: Path
    slice: HistoricalRecommendationSlice
    row_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    skipped_row_count: int = Field(ge=0)
    selected_odds_prefix_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class FootballDataCoUkBatchImportResult(BaseModel):
    import_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    skipped_row_count: int = Field(ge=0)
    output_slice_paths: list[Path] = Field(default_factory=list)
    imports: list[FootballDataCoUkImportResult] = Field(default_factory=list)
    manifest_refresh_result: HistoricalRecommendationSuiteManifestRefreshResult | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _FootballDataCoUkParsedRow(BaseModel):
    row_number: int
    source_division: str | None = None
    source_season: str | None = None
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    actual_result_code: str
    selected_odds_prefix: str
    decimal_odds: dict[str, float]
    raw_implied_probabilities: dict[str, float]
    no_vig_probabilities: dict[str, float]
    odds_overround: float


def build_historical_recommendation_slice_from_football_data_co_uk_csv(
    input_path: Path | str,
    *,
    options: FootballDataCoUkImportOptions,
) -> FootballDataCoUkImportResult:
    resolved_input_path = Path(input_path)
    warnings: list[str] = []
    parsed_rows = _parse_football_data_co_uk_rows(
        resolved_input_path,
        options=options,
        warnings=warnings,
    )
    if not parsed_rows:
        raise ValueError(
            f"football-data.co.uk CSV produced no importable fixtures: {resolved_input_path}"
        )

    fixture_ids_seen: set[str] = set()
    fixtures: list[HistoricalFixture] = []
    selected_prefix_counts: Counter[str] = Counter()
    for row in parsed_rows:
        fixture_id = _dedupe_fixture_id(
            _fixture_id(row, options=options),
            seen_fixture_ids=fixture_ids_seen,
        )
        selected_prefix_counts[row.selected_odds_prefix] += 1
        fixtures.append(
            HistoricalFixture(
                fixture_id=fixture_id,
                competition_id=options.competition_id,
                kickoff_time_utc=_aware_utc(row.kickoff_time_utc),
                home_team_name=row.home_team_name,
                away_team_name=row.away_team_name,
                actual_home_goals=row.actual_home_goals,
                actual_away_goals=row.actual_away_goals,
                prediction_time_utc=_aware_utc(options.as_of_time_utc),
                model_version=options.model_version,
                feature_version=options.feature_version,
                calibration_version=options.calibration_version,
                predictions=_predictions_from_row(row, options=options),
                metadata_json={
                    "source": "football-data.co.uk",
                    "source_division": row.source_division,
                    "source_season": row.source_season,
                    "source_row_number": row.row_number,
                    "actual_result_code": row.actual_result_code,
                    "selected_odds_prefix": row.selected_odds_prefix,
                    "odds_overround": round(row.odds_overround, 6),
                    "csv_file_name": resolved_input_path.name,
                },
            )
        )

    slice_id = options.slice_id or _slice_id_from_input_path(
        resolved_input_path,
        options=options,
    )
    name = options.name or _slice_name_from_input_path(resolved_input_path, options=options)
    historical_slice = HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=name,
            competition_id=options.competition_id,
            season=options.season,
            result_source=options.result_source,
            odds_source=options.odds_source,
            prediction_source=options.prediction_source,
            source_urls=list(options.source_urls),
            notes=list(options.notes),
        ),
        as_of_time_utc=_aware_utc(options.as_of_time_utc),
        fixtures=fixtures,
    )
    row_count = _csv_row_count(resolved_input_path, max_rows=options.max_rows)
    prediction_count = sum(len(fixture.predictions) for fixture in fixtures)
    summary: dict[str, object] = {
        "calculation_basis": "football_data_co_uk_csv_import_v3_1",
        "input_path": str(resolved_input_path),
        "slice_id": historical_slice.metadata.slice_id,
        "competition_id": historical_slice.metadata.competition_id,
        "season": historical_slice.metadata.season,
        "row_count": row_count,
        "fixture_count": len(fixtures),
        "prediction_count": prediction_count,
        "skipped_row_count": row_count - len(fixtures),
        "selected_odds_prefix_counts": dict(selected_prefix_counts),
        "warnings": warnings,
    }
    return FootballDataCoUkImportResult(
        input_path=resolved_input_path,
        slice=historical_slice,
        row_count=row_count,
        fixture_count=len(fixtures),
        prediction_count=prediction_count,
        skipped_row_count=row_count - len(fixtures),
        selected_odds_prefix_counts=dict(selected_prefix_counts),
        warnings=warnings,
        summary_json=summary,
    )


def run_football_data_co_uk_batch_import(
    input_paths: Sequence[Path | str],
    *,
    options: FootballDataCoUkImportOptions,
    output_dir: Path | str | None = None,
    output_path: Path | str | None = None,
    manifest_path: Path | str | None = None,
    manifest_refresh_options: HistoricalRecommendationSuiteManifestRefreshOptions | None = None,
) -> FootballDataCoUkBatchImportResult:
    if not input_paths:
        raise ValueError("At least one football-data.co.uk CSV path is required")
    if output_path is not None and len(input_paths) != 1:
        raise ValueError("--output-path can only be used with one input CSV")
    if output_dir is None and output_path is None and manifest_path is not None:
        raise ValueError("Manifest refresh requires --output-dir or --output-path")

    imports: list[FootballDataCoUkImportResult] = []
    output_slice_paths: list[Path] = []
    for input_path in input_paths:
        import_result = build_historical_recommendation_slice_from_football_data_co_uk_csv(
            input_path,
            options=options,
        )
        imports.append(import_result)
        write_path = _output_path_for_import(
            import_result,
            output_dir=Path(output_dir) if output_dir is not None else None,
            output_path=Path(output_path) if output_path is not None else None,
        )
        if write_path is not None:
            write_path.parent.mkdir(parents=True, exist_ok=True)
            write_path.write_text(
                f"{import_result.slice.model_dump_json(indent=2)}\n",
                encoding="utf-8",
            )
            output_slice_paths.append(write_path)

    manifest_result: HistoricalRecommendationSuiteManifestRefreshResult | None = None
    if manifest_path is not None:
        refresh_options = (
            manifest_refresh_options or HistoricalRecommendationSuiteManifestRefreshOptions()
        )
        manifest_result = refresh_historical_recommendation_suite_manifest(
            manifest_path,
            slice_paths=output_slice_paths,
            options=refresh_options,
        )

    warnings = [warning for import_result in imports for warning in import_result.warnings]
    if manifest_result is not None:
        warnings = [*warnings, *manifest_result.warnings]
    summary: dict[str, object] = {
        "calculation_basis": "football_data_co_uk_batch_import_v3_1",
        "import_count": len(imports),
        "fixture_count": sum(import_result.fixture_count for import_result in imports),
        "prediction_count": sum(import_result.prediction_count for import_result in imports),
        "skipped_row_count": sum(import_result.skipped_row_count for import_result in imports),
        "output_slice_paths": [str(path) for path in output_slice_paths],
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "manifest_refreshed": manifest_result is not None,
        "warnings": warnings,
    }
    return FootballDataCoUkBatchImportResult(
        import_count=len(imports),
        fixture_count=cast(int, summary["fixture_count"]),
        prediction_count=cast(int, summary["prediction_count"]),
        skipped_row_count=cast(int, summary["skipped_row_count"]),
        output_slice_paths=output_slice_paths,
        imports=imports,
        manifest_refresh_result=manifest_result,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = run_football_data_co_uk_batch_import(
        args.input_csv_paths,
        options=_options_from_args(args),
        output_dir=args.output_dir,
        output_path=args.output_path,
        manifest_path=args.manifest_path,
        manifest_refresh_options=_manifest_options_from_args(args),
    )
    print(
        dumps(
            _cli_output(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def _parse_football_data_co_uk_rows(
    input_path: Path,
    *,
    options: FootballDataCoUkImportOptions,
    warnings: list[str],
) -> list[_FootballDataCoUkParsedRow]:
    parsed_rows: list[_FootballDataCoUkParsedRow] = []
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = DictReader(handle)
        for row_index, raw_row in enumerate(reader, start=2):
            if options.max_rows is not None and len(parsed_rows) >= options.max_rows:
                break
            parsed_row = _parse_football_data_co_uk_row(
                raw_row,
                row_number=row_index,
                options=options,
                warnings=warnings,
            )
            if parsed_row is not None:
                parsed_rows.append(parsed_row)
    return parsed_rows


def _parse_football_data_co_uk_row(
    raw_row: Mapping[str, str | None],
    *,
    row_number: int,
    options: FootballDataCoUkImportOptions,
    warnings: list[str],
) -> _FootballDataCoUkParsedRow | None:
    source_season = _optional_text(raw_row.get("Season"))
    if options.source_seasons and source_season not in set(options.source_seasons):
        return None

    home_team = _first_text(raw_row, ("HomeTeam", "Home"))
    away_team = _first_text(raw_row, ("AwayTeam", "Away"))
    match_date = _first_text(raw_row, ("Date",))
    actual_home_goals = _first_int(raw_row, ("FTHG", "HG"))
    actual_away_goals = _first_int(raw_row, ("FTAG", "AG"))
    if home_team is None or away_team is None or match_date is None:
        warnings.append(f"football_data_co_uk_import:row_{row_number}:missing_match_identity")
        return None
    if actual_home_goals is None or actual_away_goals is None:
        warnings.append(f"football_data_co_uk_import:row_{row_number}:missing_final_score")
        return None

    kickoff_time = _parse_kickoff_time(
        match_date,
        raw_row.get("Time") or options.default_kickoff_time,
    )
    if kickoff_time is None:
        warnings.append(f"football_data_co_uk_import:row_{row_number}:invalid_kickoff_time")
        return None

    selected_prefix, decimal_odds = _select_odds_triplet(
        raw_row,
        options=options,
    )
    if selected_prefix is None or decimal_odds is None:
        warnings.append(f"football_data_co_uk_import:row_{row_number}:missing_1x2_odds")
        return None

    raw_implied = {
        outcome: 1.0 / odds
        for outcome, odds in decimal_odds.items()
    }
    overround = sum(raw_implied.values())
    if overround <= 0:
        warnings.append(f"football_data_co_uk_import:row_{row_number}:invalid_overround")
        return None

    no_vig_probabilities = {
        outcome: raw_probability / overround
        for outcome, raw_probability in raw_implied.items()
    }
    return _FootballDataCoUkParsedRow(
        row_number=row_number,
        source_division=_first_text(raw_row, ("Div", "League")),
        source_season=source_season,
        kickoff_time_utc=kickoff_time,
        home_team_name=home_team,
        away_team_name=away_team,
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        actual_result_code=_actual_result_code(
            actual_home_goals,
            actual_away_goals,
            _first_text(raw_row, ("FTR", "Res")),
        ),
        selected_odds_prefix=selected_prefix,
        decimal_odds=decimal_odds,
        raw_implied_probabilities=raw_implied,
        no_vig_probabilities=no_vig_probabilities,
        odds_overround=overround,
    )


def _predictions_from_row(
    row: _FootballDataCoUkParsedRow,
    *,
    options: FootballDataCoUkImportOptions,
) -> list[HistoricalMarketPrediction]:
    predictions: list[HistoricalMarketPrediction] = []
    for outcome in ("home_win", "draw", "away_win"):
        decimal_odds = row.decimal_odds[outcome]
        raw_probability = row.raw_implied_probabilities[outcome]
        no_vig_probability = row.no_vig_probabilities[outcome]
        upset_score = _upset_protection_score(
            outcome=outcome,
            decimal_odds=decimal_odds,
            probability=no_vig_probability,
        )
        predictions.append(
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome=outcome,
                probability=no_vig_probability,
                decimal_odds=decimal_odds,
                market_probability=raw_probability,
                model_edge=None,
                data_quality_score=options.data_quality_score,
                model_confidence_score=options.model_confidence_score,
                calibration_score=options.calibration_score,
                upset_protection_score=upset_score,
                odds_stability_score=options.odds_stability_score,
                volatility_penalty=options.volatility_penalty,
                metadata_json=_prediction_metadata(
                    row,
                    outcome=outcome,
                    raw_probability=raw_probability,
                    no_vig_probability=no_vig_probability,
                    upset_score=upset_score,
                ),
            )
        )
    return predictions


def _prediction_metadata(
    row: _FootballDataCoUkParsedRow,
    *,
    outcome: str,
    raw_probability: float,
    no_vig_probability: float,
    upset_score: float,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "source": "football-data.co.uk",
        "selected_odds_prefix": row.selected_odds_prefix,
        "raw_implied_probability": round(raw_probability, 6),
        "no_vig_probability": round(no_vig_probability, 6),
        "odds_overround": round(row.odds_overround, 6),
    }
    if upset_score >= 0.35:
        metadata["target_outcome"] = outcome
        metadata["upset_score"] = round(upset_score, 4)
        metadata["upset_direction"] = (
            "draw_protection" if outcome == "draw" else "underdog_protection"
        )
    return metadata


def _select_odds_triplet(
    row: Mapping[str, str | None],
    *,
    options: FootballDataCoUkImportOptions,
) -> tuple[str | None, dict[str, float] | None]:
    for prefix in options.odds_prefix_priority:
        odds: dict[str, float] = {}
        for outcome, suffix in _OUTCOME_TO_ODDS_SUFFIX.items():
            decimal_odds = _first_float(row, _odds_column_candidates(prefix, suffix))
            if decimal_odds is None or decimal_odds < options.min_decimal_odds:
                odds = {}
                break
            odds[outcome] = decimal_odds
        if odds:
            return prefix, odds
    return None, None


def _fixture_id(
    row: _FootballDataCoUkParsedRow,
    *,
    options: FootballDataCoUkImportOptions,
) -> str:
    season_segment = _slug(options.season or "season")
    return "_".join(
        [
            "fdcuk",
            _slug(options.competition_id),
            season_segment,
            row.kickoff_time_utc.strftime("%Y_%m_%d"),
            _slug(row.home_team_name),
            _slug(row.away_team_name),
        ]
    )


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


def _slice_id_from_input_path(
    input_path: Path,
    *,
    options: FootballDataCoUkImportOptions,
) -> str:
    parts = [
        options.slice_id_prefix,
        options.competition_id,
    ]
    if options.season is not None:
        parts.append(options.season)
    parts.append(input_path.stem)
    return "_".join(_slug(part) for part in parts if part)


def _slice_name_from_input_path(
    input_path: Path,
    *,
    options: FootballDataCoUkImportOptions,
) -> str:
    season = f" {options.season}" if options.season is not None else ""
    return f"{options.name_prefix} {options.competition_id}{season} {input_path.stem}"


def _output_path_for_import(
    import_result: FootballDataCoUkImportResult,
    *,
    output_dir: Path | None,
    output_path: Path | None,
) -> Path | None:
    if output_path is not None:
        return output_path
    if output_dir is not None:
        return output_dir / f"{import_result.slice.metadata.slice_id}.json"
    return None


def _csv_row_count(
    input_path: Path,
    *,
    max_rows: int | None,
) -> int:
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        row_count = sum(1 for _ in DictReader(handle))
    return min(row_count, max_rows) if max_rows is not None else row_count


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


def _actual_result_code(
    actual_home_goals: int,
    actual_away_goals: int,
    result_code: str | None,
) -> str:
    cleaned_result_code = _optional_text(result_code)
    if cleaned_result_code in {"H", "D", "A"}:
        return cleaned_result_code
    if actual_home_goals > actual_away_goals:
        return "H"
    if actual_home_goals < actual_away_goals:
        return "A"
    return "D"


def _upset_protection_score(
    *,
    outcome: str,
    decimal_odds: float,
    probability: float,
) -> float:
    if outcome == "draw":
        score = 0.14 + _clamp((decimal_odds - 3.0) / 3.5) * 0.34
    elif decimal_odds >= 3.0:
        score = 0.22 + _clamp((decimal_odds - 3.0) / 5.0) * 0.45
    else:
        score = 0.0
    if probability <= 0.25 and decimal_odds >= 3.0:
        score += 0.08
    return round(_clamp(score), 4)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _first_text(row: Mapping[str, str | None], columns: Sequence[str]) -> str | None:
    for column in columns:
        text = _optional_text(row.get(column))
        if text is not None:
            return text
    return None


def _first_int(row: Mapping[str, str | None], columns: Sequence[str]) -> int | None:
    for column in columns:
        value = _optional_int(row.get(column))
        if value is not None:
            return value
    return None


def _first_float(row: Mapping[str, str | None], columns: Sequence[str]) -> float | None:
    for column in columns:
        value = _optional_float(row.get(column))
        if value is not None:
            return value
    return None


def _odds_column_candidates(prefix: str, suffix: str) -> tuple[str, ...]:
    candidates = [f"{prefix}{suffix}"]
    if prefix == "B365C" and suffix == "A":
        candidates.append("B36CA")
    return tuple(candidates)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _optional_int(value: str | None) -> int | None:
    cleaned = _optional_text(value)
    if cleaned is None:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _optional_float(value: str | None) -> float | None:
    cleaned = _optional_text(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _slug(value: str) -> str:
    cleaned = sub(r"[^a-z0-9]+", "_", value.strip().casefold())
    return cleaned.strip("_") or "unknown"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Import football-data.co.uk CSV files as Nutmeg historical slices."
    )
    parser.add_argument("input_csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--manifest-tag", action="append", default=[])
    parser.add_argument("--manifest-note", action="append", default=[])
    parser.add_argument("--manifest-disabled", action="store_true")
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--as-of-time-utc", required=True)
    parser.add_argument("--season")
    parser.add_argument("--slice-id")
    parser.add_argument("--slice-id-prefix", default="football_data_co_uk")
    parser.add_argument("--name")
    parser.add_argument("--name-prefix", default="Football-Data.co.uk")
    parser.add_argument("--result-source", default="football-data.co.uk CSV final score")
    parser.add_argument("--odds-source", default="football-data.co.uk CSV 1X2 odds")
    parser.add_argument(
        "--prediction-source",
        default="no-vig market-implied baseline from football-data.co.uk odds",
    )
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--model-version", default=FOOTBALL_DATA_CO_UK_DEFAULT_MODEL_VERSION)
    parser.add_argument("--feature-version", default=FOOTBALL_DATA_CO_UK_DEFAULT_FEATURE_VERSION)
    parser.add_argument(
        "--calibration-version",
        default=FOOTBALL_DATA_CO_UK_DEFAULT_CALIBRATION_VERSION,
    )
    parser.add_argument("--odds-prefix", action="append", default=[])
    parser.add_argument("--data-quality-score", type=float, default=82.0)
    parser.add_argument("--model-confidence-score", type=float, default=0.66)
    parser.add_argument("--calibration-score", type=float, default=0.70)
    parser.add_argument("--odds-stability-score", type=float, default=0.72)
    parser.add_argument("--volatility-penalty", type=float, default=0.08)
    parser.add_argument("--default-kickoff-time", default="12:00")
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--min-decimal-odds", type=float, default=1.01)
    parser.add_argument("--source-season", action="append", default=[])
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> FootballDataCoUkImportOptions:
    source_urls = tuple(args.source_url) or (FOOTBALL_DATA_CO_UK_SOURCE_URL,)
    notes = tuple(args.note) or FootballDataCoUkImportOptions.model_fields["notes"].default
    odds_prefix_priority = (
        tuple(args.odds_prefix)
        if args.odds_prefix
        else FOOTBALL_DATA_CO_UK_DEFAULT_ODDS_PREFIX_PRIORITY
    )
    return FootballDataCoUkImportOptions(
        competition_id=args.competition_id,
        as_of_time_utc=_parse_iso_datetime(args.as_of_time_utc),
        season=args.season,
        slice_id=args.slice_id,
        slice_id_prefix=args.slice_id_prefix,
        name=args.name,
        name_prefix=args.name_prefix,
        result_source=args.result_source,
        odds_source=args.odds_source,
        prediction_source=args.prediction_source,
        source_urls=source_urls,
        notes=cast(tuple[str, ...], notes),
        model_version=args.model_version,
        feature_version=args.feature_version,
        calibration_version=args.calibration_version,
        odds_prefix_priority=odds_prefix_priority,
        data_quality_score=args.data_quality_score,
        model_confidence_score=args.model_confidence_score,
        calibration_score=args.calibration_score,
        odds_stability_score=args.odds_stability_score,
        volatility_penalty=args.volatility_penalty,
        default_kickoff_time=args.default_kickoff_time,
        max_rows=args.max_rows,
        min_decimal_odds=args.min_decimal_odds,
        source_seasons=tuple(args.source_season),
    )


def _manifest_options_from_args(
    args: Namespace,
) -> HistoricalRecommendationSuiteManifestRefreshOptions:
    return HistoricalRecommendationSuiteManifestRefreshOptions(
        enabled=not args.manifest_disabled,
        tags=tuple(args.manifest_tag),
        notes=tuple(args.manifest_note),
        write=args.write_manifest,
    )


def _parse_iso_datetime(value: str) -> datetime:
    cleaned = value.replace("Z", "+00:00")
    return _aware_utc(datetime.fromisoformat(cleaned))


def _cli_output(result: FootballDataCoUkBatchImportResult) -> dict[str, object]:
    output: dict[str, object] = {
        **result.summary_json,
        "imports": [import_result.summary_json for import_result in result.imports],
    }
    if result.import_count == 1 and not result.output_slice_paths:
        output["slice"] = result.imports[0].slice.model_dump(mode="json")
    if result.manifest_refresh_result is not None:
        output["manifest_refresh"] = result.manifest_refresh_result.summary_json
    return output
