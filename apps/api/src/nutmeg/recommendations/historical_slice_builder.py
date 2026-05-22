from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.models import RecommendationMarketType

CSV_REQUIRED_COLUMNS = (
    "fixture_id",
    "kickoff_time_utc",
    "home_team_name",
    "away_team_name",
    "actual_home_goals",
    "actual_away_goals",
    "prediction_time_utc",
    "model_version",
    "outcome",
    "probability",
    "decimal_odds",
)


class HistoricalRecommendationSliceBuildOptions(BaseModel):
    slice_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    competition_id: str = Field(min_length=1)
    as_of_time_utc: datetime
    result_source: str = Field(min_length=1)
    odds_source: str = Field(min_length=1)
    prediction_source: str = Field(min_length=1)
    season: str | None = None
    source_urls: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    probability_sum_tolerance: float = Field(default=0.02, ge=0.0)


class HistoricalRecommendationSliceCsvRow(BaseModel):
    row_number: int = Field(ge=2)
    fixture_id: str = Field(min_length=1)
    competition_id: str = Field(min_length=1)
    kickoff_time_utc: datetime
    home_team_name: str = Field(min_length=1)
    away_team_name: str = Field(min_length=1)
    actual_home_goals: int = Field(ge=0)
    actual_away_goals: int = Field(ge=0)
    prediction_time_utc: datetime
    model_version: str = Field(min_length=1)
    feature_version: str | None = None
    calibration_version: str | None = None
    market_type: RecommendationMarketType = "1x2"
    outcome: str = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float = Field(gt=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    model_edge: float | None = None
    data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    model_confidence_score: float = Field(default=0.70, ge=0.0, le=1.0)
    calibration_score: float = Field(default=0.70, ge=0.0, le=1.0)
    upset_protection_score: float = Field(default=0.0, ge=0.0, le=1.0)
    odds_stability_score: float = Field(default=0.70, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    line: float | None = None
    side: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    fixture_metadata_json: dict[str, object] = Field(default_factory=dict)
    feature_snapshot_json: dict[str, object] | None = None


class HistoricalRecommendationSliceBuildResult(BaseModel):
    slice: HistoricalRecommendationSlice
    row_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_recommendation_slice_from_csv(
    input_path: Path | str,
    *,
    options: HistoricalRecommendationSliceBuildOptions,
) -> HistoricalRecommendationSliceBuildResult:
    rows = _load_csv_rows(Path(input_path), options=options)
    fixtures = _fixtures_from_rows(rows, options=options)
    historical_slice = HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=options.slice_id,
            name=options.name,
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
    warnings = _build_warnings(rows, options=options)
    summary = {
        "calculation_basis": "historical_recommendation_slice_builder_v3_1",
        "input_path": str(input_path),
        "slice_id": options.slice_id,
        "competition_id": options.competition_id,
        "row_count": len(rows),
        "fixture_count": len(fixtures),
        "prediction_count": sum(len(fixture.predictions) for fixture in fixtures),
        "feature_snapshot_fixture_count": sum(
            1 for fixture in fixtures if fixture.feature_snapshot is not None
        ),
        "warnings": warnings,
    }
    return HistoricalRecommendationSliceBuildResult(
        slice=historical_slice,
        row_count=len(rows),
        fixture_count=len(fixtures),
        prediction_count=sum(len(fixture.predictions) for fixture in fixtures),
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = build_historical_recommendation_slice_from_csv(
        args.input_csv_path,
        options=_options_from_args(args),
    )
    output_payload = dumps(
        result.slice.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        Path(args.output_path).write_text(f"{output_payload}\n", encoding="utf-8")
        print(
            dumps(
                {
                    **result.summary_json,
                    "output_path": str(args.output_path),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(output_payload)


def _load_csv_rows(
    input_path: Path,
    *,
    options: HistoricalRecommendationSliceBuildOptions,
) -> list[HistoricalRecommendationSliceCsvRow]:
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = DictReader(handle)
        _validate_csv_columns(input_path, reader.fieldnames)
        return [
            _parse_csv_row(raw_row, row_number=row_number, options=options)
            for row_number, raw_row in enumerate(reader, start=2)
        ]


def _validate_csv_columns(input_path: Path, fieldnames: Sequence[str] | None) -> None:
    if fieldnames is None:
        raise ValueError(f"historical slice input has no header: {input_path}")
    missing = [column for column in CSV_REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(
            f"historical slice input missing required columns: {','.join(missing)}"
        )


def _parse_csv_row(
    raw_row: Mapping[str, str | None],
    *,
    row_number: int,
    options: HistoricalRecommendationSliceBuildOptions,
) -> HistoricalRecommendationSliceCsvRow:
    return HistoricalRecommendationSliceCsvRow(
        row_number=row_number,
        fixture_id=_required_text(raw_row, "fixture_id", row_number=row_number),
        competition_id=(
            _optional_text(raw_row, "competition_id") or options.competition_id
        ),
        kickoff_time_utc=_datetime(
            _required_text(raw_row, "kickoff_time_utc", row_number=row_number)
        ),
        home_team_name=_required_text(raw_row, "home_team_name", row_number=row_number),
        away_team_name=_required_text(raw_row, "away_team_name", row_number=row_number),
        actual_home_goals=_int(
            _required_text(raw_row, "actual_home_goals", row_number=row_number)
        ),
        actual_away_goals=_int(
            _required_text(raw_row, "actual_away_goals", row_number=row_number)
        ),
        prediction_time_utc=_datetime(
            _required_text(raw_row, "prediction_time_utc", row_number=row_number)
        ),
        model_version=_required_text(raw_row, "model_version", row_number=row_number),
        feature_version=_optional_text(raw_row, "feature_version"),
        calibration_version=_optional_text(raw_row, "calibration_version"),
        market_type=cast(
            RecommendationMarketType,
            _optional_text(raw_row, "market_type") or "1x2",
        ),
        outcome=_required_text(raw_row, "outcome", row_number=row_number),
        probability=_float(_required_text(raw_row, "probability", row_number=row_number)),
        decimal_odds=_float(
            _required_text(raw_row, "decimal_odds", row_number=row_number)
        ),
        market_probability=_optional_float(raw_row, "market_probability"),
        model_edge=_optional_float(raw_row, "model_edge"),
        data_quality_score=_optional_float(raw_row, "data_quality_score") or 80.0,
        model_confidence_score=(
            _optional_float(raw_row, "model_confidence_score") or 0.70
        ),
        calibration_score=_optional_float(raw_row, "calibration_score") or 0.70,
        upset_protection_score=(
            _optional_float(raw_row, "upset_protection_score") or 0.0
        ),
        odds_stability_score=_optional_float(raw_row, "odds_stability_score") or 0.70,
        volatility_penalty=_optional_float(raw_row, "volatility_penalty") or 0.0,
        line=_optional_float(raw_row, "line"),
        side=_optional_text(raw_row, "side"),
        metadata_json=_json_object(_optional_text(raw_row, "metadata_json")),
        fixture_metadata_json=_json_object(
            _optional_text(raw_row, "fixture_metadata_json")
        ),
        feature_snapshot_json=_optional_json_object(
            _optional_text(raw_row, "feature_snapshot_json")
        ),
    )


def _fixtures_from_rows(
    rows: Sequence[HistoricalRecommendationSliceCsvRow],
    *,
    options: HistoricalRecommendationSliceBuildOptions,
) -> list[HistoricalFixture]:
    rows_by_fixture: OrderedDict[str, list[HistoricalRecommendationSliceCsvRow]] = (
        OrderedDict()
    )
    for row in rows:
        rows_by_fixture.setdefault(row.fixture_id, []).append(row)
    return [
        _fixture_from_rows(fixture_rows, options=options)
        for fixture_rows in rows_by_fixture.values()
    ]


def _fixture_from_rows(
    rows: Sequence[HistoricalRecommendationSliceCsvRow],
    *,
    options: HistoricalRecommendationSliceBuildOptions,
) -> HistoricalFixture:
    first = rows[0]
    _validate_fixture_rows(rows)
    return HistoricalFixture(
        fixture_id=first.fixture_id,
        competition_id=first.competition_id or options.competition_id,
        kickoff_time_utc=_aware_utc(first.kickoff_time_utc),
        home_team_name=first.home_team_name,
        away_team_name=first.away_team_name,
        actual_home_goals=first.actual_home_goals,
        actual_away_goals=first.actual_away_goals,
        prediction_time_utc=_aware_utc(first.prediction_time_utc),
        model_version=first.model_version,
        feature_version=first.feature_version,
        calibration_version=first.calibration_version,
        predictions=[
            HistoricalMarketPrediction(
                market_type=row.market_type,
                outcome=row.outcome,
                probability=row.probability,
                decimal_odds=row.decimal_odds,
                market_probability=row.market_probability,
                model_edge=row.model_edge,
                data_quality_score=row.data_quality_score,
                model_confidence_score=row.model_confidence_score,
                calibration_score=row.calibration_score,
                upset_protection_score=row.upset_protection_score,
                odds_stability_score=row.odds_stability_score,
                volatility_penalty=row.volatility_penalty,
                line=row.line,
                side=row.side,
                metadata_json=row.metadata_json,
            )
            for row in rows
        ],
        feature_snapshot=_feature_snapshot_from_json(
            first.feature_snapshot_json,
            fixture_id=first.fixture_id,
        ),
        metadata_json=first.fixture_metadata_json,
    )


def _validate_fixture_rows(rows: Sequence[HistoricalRecommendationSliceCsvRow]) -> None:
    first = rows[0]
    fixture_fields = (
        "competition_id",
        "kickoff_time_utc",
        "home_team_name",
        "away_team_name",
        "actual_home_goals",
        "actual_away_goals",
        "prediction_time_utc",
        "model_version",
        "feature_version",
        "calibration_version",
        "feature_snapshot_json",
    )
    seen_predictions: set[tuple[str, str, float | None, str | None]] = set()
    for row in rows:
        for field_name in fixture_fields:
            if getattr(row, field_name) != getattr(first, field_name):
                raise ValueError(
                    f"fixture {first.fixture_id} has inconsistent {field_name} "
                    f"at CSV row {row.row_number}"
                )
        prediction_key = (row.market_type, row.outcome, row.line, row.side)
        if prediction_key in seen_predictions:
            raise ValueError(
                f"fixture {first.fixture_id} has duplicate prediction "
                f"{prediction_key} at CSV row {row.row_number}"
            )
        seen_predictions.add(prediction_key)


def _build_warnings(
    rows: Sequence[HistoricalRecommendationSliceCsvRow],
    *,
    options: HistoricalRecommendationSliceBuildOptions,
) -> list[str]:
    warnings: list[str] = []
    rows_by_fixture_market: dict[tuple[str, str], list[HistoricalRecommendationSliceCsvRow]] = {}
    for row in rows:
        rows_by_fixture_market.setdefault((row.fixture_id, row.market_type), []).append(row)
        if _aware_utc(row.prediction_time_utc) > _aware_utc(options.as_of_time_utc):
            warnings.append(
                "historical_slice_builder:prediction_after_as_of:"
                f"{row.fixture_id}:row_{row.row_number}"
            )
        if _aware_utc(row.kickoff_time_utc) <= _aware_utc(options.as_of_time_utc):
            warnings.append(
                "historical_slice_builder:kickoff_not_after_as_of:"
                f"{row.fixture_id}:row_{row.row_number}"
            )
        feature_snapshot = _feature_snapshot_from_json(
            row.feature_snapshot_json,
            fixture_id=row.fixture_id,
        )
        if feature_snapshot is not None:
            if _aware_utc(feature_snapshot.feature_time_utc) > _aware_utc(
                options.as_of_time_utc
            ):
                warnings.append(
                    "historical_slice_builder:feature_snapshot_after_as_of:"
                    f"{row.fixture_id}:row_{row.row_number}"
                )
            if _aware_utc(feature_snapshot.feature_time_utc) >= _aware_utc(
                row.kickoff_time_utc
            ):
                warnings.append(
                    "historical_slice_builder:feature_snapshot_not_before_kickoff:"
                    f"{row.fixture_id}:row_{row.row_number}"
                )
    for (fixture_id, market_type), market_rows in rows_by_fixture_market.items():
        probability_sum = sum(row.probability for row in market_rows)
        if abs(probability_sum - 1.0) > options.probability_sum_tolerance:
            warnings.append(
                "historical_slice_builder:probability_sum_out_of_tolerance:"
                f"{fixture_id}:{market_type}:{probability_sum:.6f}"
            )
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build a frozen historical recommendation slice from CSV rows."
    )
    parser.add_argument("input_csv_path", type=Path)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--as-of-time-utc", required=True)
    parser.add_argument("--season", default=None)
    parser.add_argument("--result-source", required=True)
    parser.add_argument("--odds-source", required=True)
    parser.add_argument("--prediction-source", required=True)
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--probability-sum-tolerance", type=float, default=0.02)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalRecommendationSliceBuildOptions:
    return HistoricalRecommendationSliceBuildOptions(
        slice_id=args.slice_id,
        name=args.name,
        competition_id=args.competition_id,
        as_of_time_utc=_datetime(args.as_of_time_utc),
        season=args.season,
        result_source=args.result_source,
        odds_source=args.odds_source,
        prediction_source=args.prediction_source,
        source_urls=tuple(args.source_url),
        notes=tuple(args.note),
        probability_sum_tolerance=args.probability_sum_tolerance,
    )


def _required_text(
    row: Mapping[str, str | None],
    column: str,
    *,
    row_number: int,
) -> str:
    value = _optional_text(row, column)
    if value is None:
        raise ValueError(f"CSV row {row_number} missing required column {column}")
    return value


def _optional_text(row: Mapping[str, str | None], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_float(row: Mapping[str, str | None], column: str) -> float | None:
    value = _optional_text(row, column)
    if value is None:
        return None
    return _float(value)


def _float(value: str) -> float:
    return float(value)


def _int(value: str) -> int:
    return int(value)


def _datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return _aware_utc(datetime.fromisoformat(normalized))


def _json_object(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    parsed: Any = loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("CSV JSON metadata fields must contain JSON objects")
    return cast(dict[str, object], parsed)


def _optional_json_object(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    parsed: Any = loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("CSV JSON metadata fields must contain JSON objects")
    return cast(dict[str, object], parsed)


def _feature_snapshot_from_json(
    value: dict[str, object] | None,
    *,
    fixture_id: str,
) -> FeatureSnapshot | None:
    if value is None:
        return None
    payload = dict(value)
    payload.setdefault("fixture_id", fixture_id)
    snapshot = FeatureSnapshot.model_validate(payload)
    if snapshot.fixture_id != fixture_id:
        raise ValueError(
            "feature_snapshot_json fixture_id does not match CSV fixture_id: "
            f"{snapshot.fixture_id} != {fixture_id}"
        )
    return snapshot


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
