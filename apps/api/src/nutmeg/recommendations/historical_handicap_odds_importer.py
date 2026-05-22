from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.models import RecommendationMarketType

type HistoricalHandicapOddsProbabilitySource = Literal[
    "explicit_probability",
    "no_vig_market_probability",
]

HANDICAP_IMPORT_MARKETS: tuple[RecommendationMarketType, ...] = (
    "cn_handicap_1x2",
    "european_handicap_1x2",
)
HANDICAP_IMPORT_OUTCOMES = (
    "handicap_home_win",
    "handicap_draw",
    "handicap_away_win",
)

CSV_REQUIRED_COLUMNS = (
    "fixture_id",
    "market_type",
    "line",
    "outcome",
    "decimal_odds",
)


class HistoricalHandicapOddsImportOptions(BaseModel):
    source_label: str = "historical-handicap-odds-csv"
    allowed_market_types: tuple[RecommendationMarketType, ...] = HANDICAP_IMPORT_MARKETS
    require_complete_lines: bool = True
    require_integer_lines: bool = True
    replace_existing_lines: bool = True
    data_quality_score: float = Field(default=80.0, ge=0.0, le=100.0)
    model_confidence_score: float = Field(default=0.64, ge=0.0, le=1.0)
    calibration_score: float = Field(default=0.68, ge=0.0, le=1.0)
    odds_stability_score: float = Field(default=0.70, ge=0.0, le=1.0)
    volatility_penalty: float = Field(default=0.08, ge=0.0, le=1.0)


class HistoricalHandicapOddsCsvRow(BaseModel):
    row_number: int = Field(ge=2)
    fixture_id: str = Field(min_length=1)
    market_type: RecommendationMarketType
    line: float
    outcome: str = Field(min_length=1)
    decimal_odds: float = Field(gt=1.0)
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    data_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    model_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    calibration_score: float | None = Field(default=None, ge=0.0, le=1.0)
    odds_stability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    volatility_penalty: float | None = Field(default=None, ge=0.0, le=1.0)
    provider: str | None = None
    bookmaker: str | None = None
    snapshot_time_utc: datetime | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalHandicapOddsImportedLine(BaseModel):
    fixture_id: str
    market_type: RecommendationMarketType
    line: float
    prediction_count: int = Field(ge=0)
    probability_source: HistoricalHandicapOddsProbabilitySource
    overround: float | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalHandicapOddsImportResult(BaseModel):
    slice: HistoricalRecommendationSlice
    input_path: Path
    row_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    imported_line_count: int = Field(ge=0)
    imported_prediction_count: int = Field(ge=0)
    skipped_row_count: int = Field(ge=0)
    skipped_line_count: int = Field(ge=0)
    imported_lines: list[HistoricalHandicapOddsImportedLine] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def enrich_historical_slice_with_handicap_odds_csv(
    historical_slice: HistoricalRecommendationSlice,
    input_path: Path | str,
    *,
    options: HistoricalHandicapOddsImportOptions | None = None,
) -> HistoricalHandicapOddsImportResult:
    resolved_options = options or HistoricalHandicapOddsImportOptions()
    resolved_input_path = Path(input_path)
    warnings: list[str] = []
    parsed_rows = _load_csv_rows(
        resolved_input_path,
        options=resolved_options,
        warnings=warnings,
    )
    fixture_ids = {fixture.fixture_id for fixture in historical_slice.fixtures}
    rows_for_existing_fixtures = [
        row
        for row in parsed_rows
        if _row_fixture_exists(row, fixture_ids=fixture_ids, warnings=warnings)
    ]
    predictions_by_line, imported_lines, skipped_line_count = _predictions_by_line(
        rows_for_existing_fixtures,
        options=resolved_options,
        warnings=warnings,
    )
    enriched_fixtures = [
        _enriched_fixture(
            fixture,
            predictions_by_line=predictions_by_line,
            replace_existing_lines=resolved_options.replace_existing_lines,
        )
        for fixture in historical_slice.fixtures
    ]
    enriched_slice = historical_slice.model_copy(update={"fixtures": enriched_fixtures})
    imported_prediction_count = sum(
        len(predictions) for predictions in predictions_by_line.values()
    )
    skipped_row_count = len(parsed_rows) - len(rows_for_existing_fixtures)
    summary: dict[str, object] = {
        "calculation_basis": "historical_handicap_odds_import_v3_1",
        "input_path": str(resolved_input_path),
        "slice_id": historical_slice.metadata.slice_id,
        "source_label": resolved_options.source_label,
        "row_count": len(parsed_rows),
        "fixture_count": len(historical_slice.fixtures),
        "imported_line_count": len(imported_lines),
        "imported_prediction_count": imported_prediction_count,
        "skipped_row_count": skipped_row_count,
        "skipped_line_count": skipped_line_count,
        "warnings": warnings,
    }
    return HistoricalHandicapOddsImportResult(
        slice=enriched_slice,
        input_path=resolved_input_path,
        row_count=len(parsed_rows),
        fixture_count=len(historical_slice.fixtures),
        imported_line_count=len(imported_lines),
        imported_prediction_count=imported_prediction_count,
        skipped_row_count=skipped_row_count,
        skipped_line_count=skipped_line_count,
        imported_lines=imported_lines,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = enrich_historical_slice_with_handicap_odds_csv(
        load_historical_recommendation_slice(args.base_slice_path),
        args.input_csv_path,
        options=_options_from_args(args),
    )
    output_payload = result.slice.model_dump_json(indent=2)
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output_payload}\n", encoding="utf-8")
    print(dumps(_cli_summary(result, output_path=args.output_path), ensure_ascii=False, indent=2))


def _load_csv_rows(
    input_path: Path,
    *,
    options: HistoricalHandicapOddsImportOptions,
    warnings: list[str],
) -> list[HistoricalHandicapOddsCsvRow]:
    rows: list[HistoricalHandicapOddsCsvRow] = []
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = DictReader(handle)
        _validate_csv_columns(input_path, reader.fieldnames)
        for row_number, raw_row in enumerate(reader, start=2):
            parsed = _parse_csv_row(
                raw_row,
                row_number=row_number,
                options=options,
                warnings=warnings,
            )
            if parsed is not None:
                rows.append(parsed)
    return rows


def _validate_csv_columns(input_path: Path, fieldnames: Sequence[str] | None) -> None:
    if fieldnames is None:
        raise ValueError(f"historical handicap odds input has no header: {input_path}")
    missing = [column for column in CSV_REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(
            "historical handicap odds input missing required columns: "
            f"{','.join(missing)}"
        )


def _parse_csv_row(
    raw_row: Mapping[str, str | None],
    *,
    row_number: int,
    options: HistoricalHandicapOddsImportOptions,
    warnings: list[str],
) -> HistoricalHandicapOddsCsvRow | None:
    market_type = _market_type(_required_text(raw_row, "market_type", row_number=row_number))
    if market_type not in options.allowed_market_types:
        warnings.append(f"handicap_odds_import:row_{row_number}:unsupported_market")
        return None
    line = _float(_required_text(raw_row, "line", row_number=row_number))
    if options.require_integer_lines and not _is_integer_line(line):
        warnings.append(f"handicap_odds_import:row_{row_number}:non_integer_line")
        return None
    outcome = _handicap_outcome(
        _required_text(raw_row, "outcome", row_number=row_number)
    )
    if outcome is None:
        warnings.append(f"handicap_odds_import:row_{row_number}:unsupported_outcome")
        return None
    return HistoricalHandicapOddsCsvRow(
        row_number=row_number,
        fixture_id=_required_text(raw_row, "fixture_id", row_number=row_number),
        market_type=market_type,
        line=line,
        outcome=outcome,
        decimal_odds=_float(_required_text(raw_row, "decimal_odds", row_number=row_number)),
        probability=_optional_float(raw_row, "probability"),
        market_probability=_optional_float(raw_row, "market_probability"),
        data_quality_score=_optional_float(raw_row, "data_quality_score"),
        model_confidence_score=_optional_float(raw_row, "model_confidence_score"),
        calibration_score=_optional_float(raw_row, "calibration_score"),
        odds_stability_score=_optional_float(raw_row, "odds_stability_score"),
        volatility_penalty=_optional_float(raw_row, "volatility_penalty"),
        provider=_optional_text(raw_row, "provider"),
        bookmaker=_optional_text(raw_row, "bookmaker"),
        snapshot_time_utc=_optional_datetime(_optional_text(raw_row, "snapshot_time_utc")),
        metadata_json=_metadata_json(_optional_text(raw_row, "metadata_json")),
    )


def _row_fixture_exists(
    row: HistoricalHandicapOddsCsvRow,
    *,
    fixture_ids: set[str],
    warnings: list[str],
) -> bool:
    if row.fixture_id in fixture_ids:
        return True
    warnings.append(
        f"handicap_odds_import:row_{row.row_number}:unknown_fixture:{row.fixture_id}"
    )
    return False


def _predictions_by_line(
    rows: Sequence[HistoricalHandicapOddsCsvRow],
    *,
    options: HistoricalHandicapOddsImportOptions,
    warnings: list[str],
) -> tuple[
    dict[tuple[str, RecommendationMarketType, float], list[HistoricalMarketPrediction]],
    list[HistoricalHandicapOddsImportedLine],
    int,
]:
    grouped: OrderedDict[
        tuple[str, RecommendationMarketType, float],
        list[HistoricalHandicapOddsCsvRow],
    ] = OrderedDict()
    for row in rows:
        grouped.setdefault((row.fixture_id, row.market_type, row.line), []).append(row)

    imported: dict[
        tuple[str, RecommendationMarketType, float],
        list[HistoricalMarketPrediction],
    ] = {}
    imported_lines: list[HistoricalHandicapOddsImportedLine] = []
    skipped_line_count = 0
    for key, line_rows in grouped.items():
        deduped_rows = _dedupe_line_rows(line_rows, warnings=warnings)
        fixture_id, market_type, line = key
        missing_outcomes = [
            outcome
            for outcome in HANDICAP_IMPORT_OUTCOMES
            if outcome not in {row.outcome for row in deduped_rows}
        ]
        line_warnings: list[str] = []
        if missing_outcomes:
            line_warnings.append(
                "missing_outcomes:" + ",".join(sorted(missing_outcomes))
            )
        if missing_outcomes and options.require_complete_lines:
            skipped_line_count += 1
            warnings.append(
                "handicap_odds_import:skipped_incomplete_line:"
                f"{fixture_id}:{market_type}:{line:g}"
            )
            continue
        predictions, probability_source, overround = _line_predictions(
            deduped_rows,
            options=options,
        )
        imported[key] = predictions
        imported_lines.append(
            HistoricalHandicapOddsImportedLine(
                fixture_id=fixture_id,
                market_type=market_type,
                line=line,
                prediction_count=len(predictions),
                probability_source=probability_source,
                overround=overround,
                warnings=line_warnings,
            )
        )
    return imported, imported_lines, skipped_line_count


def _dedupe_line_rows(
    rows: Sequence[HistoricalHandicapOddsCsvRow],
    *,
    warnings: list[str],
) -> list[HistoricalHandicapOddsCsvRow]:
    by_outcome: OrderedDict[str, HistoricalHandicapOddsCsvRow] = OrderedDict()
    for row in rows:
        if row.outcome in by_outcome:
            warnings.append(
                f"handicap_odds_import:row_{row.row_number}:duplicate_outcome:{row.outcome}"
            )
            continue
        by_outcome[row.outcome] = row
    return list(by_outcome.values())


def _line_predictions(
    rows: Sequence[HistoricalHandicapOddsCsvRow],
    *,
    options: HistoricalHandicapOddsImportOptions,
) -> tuple[list[HistoricalMarketPrediction], HistoricalHandicapOddsProbabilitySource, float]:
    raw_probabilities = {row.outcome: 1.0 / row.decimal_odds for row in rows}
    implied_sum = sum(raw_probabilities.values())
    overround = implied_sum - 1.0
    fair_probabilities = {
        outcome: raw_probability / implied_sum
        for outcome, raw_probability in raw_probabilities.items()
    }
    probability_source: HistoricalHandicapOddsProbabilitySource = (
        "explicit_probability"
        if all(row.probability is not None for row in rows)
        else "no_vig_market_probability"
    )
    return [
        _prediction_from_row(
            row,
            probability=(
                row.probability
                if row.probability is not None
                else fair_probabilities[row.outcome]
            ),
            market_probability=(
                row.market_probability
                if row.market_probability is not None
                else raw_probabilities[row.outcome]
            ),
            fair_probability=fair_probabilities[row.outcome],
            raw_probability=raw_probabilities[row.outcome],
            overround=overround,
            probability_source=probability_source,
            options=options,
        )
        for row in rows
    ], probability_source, overround


def _prediction_from_row(
    row: HistoricalHandicapOddsCsvRow,
    *,
    probability: float,
    market_probability: float,
    fair_probability: float,
    raw_probability: float,
    overround: float,
    probability_source: HistoricalHandicapOddsProbabilitySource,
    options: HistoricalHandicapOddsImportOptions,
) -> HistoricalMarketPrediction:
    model_edge = probability - market_probability
    metadata = {
        **row.metadata_json,
        "source": options.source_label,
        "provider": row.provider,
        "bookmaker": row.bookmaker,
        "snapshot_time_utc": (
            row.snapshot_time_utc.isoformat() if row.snapshot_time_utc is not None else None
        ),
        "row_number": row.row_number,
        "probability_source": probability_source,
        "raw_implied_probability": round(raw_probability, 6),
        "no_vig_probability": round(fair_probability, 6),
        "odds_overround": round(overround, 6),
    }
    return HistoricalMarketPrediction(
        market_type=row.market_type,
        outcome=row.outcome,
        probability=probability,
        decimal_odds=row.decimal_odds,
        market_probability=market_probability,
        model_edge=model_edge,
        data_quality_score=row.data_quality_score
        if row.data_quality_score is not None
        else options.data_quality_score,
        model_confidence_score=row.model_confidence_score
        if row.model_confidence_score is not None
        else options.model_confidence_score,
        calibration_score=row.calibration_score
        if row.calibration_score is not None
        else options.calibration_score,
        odds_stability_score=row.odds_stability_score
        if row.odds_stability_score is not None
        else options.odds_stability_score,
        volatility_penalty=row.volatility_penalty
        if row.volatility_penalty is not None
        else options.volatility_penalty,
        line=row.line,
        side=None,
        metadata_json=metadata,
    )


def _enriched_fixture(
    fixture: HistoricalFixture,
    *,
    predictions_by_line: Mapping[
        tuple[str, RecommendationMarketType, float],
        Sequence[HistoricalMarketPrediction],
    ],
    replace_existing_lines: bool,
) -> HistoricalFixture:
    fixture_line_keys = {
        key for key in predictions_by_line if key[0] == fixture.fixture_id
    }
    if not fixture_line_keys:
        return fixture
    existing_predictions = fixture.predictions
    if replace_existing_lines:
        existing_predictions = [
            prediction
            for prediction in fixture.predictions
            if (
                fixture.fixture_id,
                prediction.market_type,
                prediction.line if prediction.line is not None else 0.0,
            )
            not in fixture_line_keys
        ]
    imported_predictions = [
        prediction
        for key in fixture_line_keys
        for prediction in predictions_by_line[key]
    ]
    return fixture.model_copy(
        update={"predictions": [*existing_predictions, *imported_predictions]}
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Enrich a historical recommendation slice with complete integer-line "
            "Chinese/European handicap 1X2 odds."
        )
    )
    parser.add_argument("base_slice_path", type=Path)
    parser.add_argument("input_csv_path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--source-label", default="historical-handicap-odds-csv")
    parser.add_argument(
        "--allowed-market-types",
        default="cn_handicap_1x2,european_handicap_1x2",
    )
    parser.add_argument("--allow-incomplete-lines", action="store_true")
    parser.add_argument("--allow-non-integer-lines", action="store_true")
    parser.add_argument("--append-existing-lines", action="store_true")
    parser.add_argument("--data-quality-score", type=float, default=80.0)
    parser.add_argument("--model-confidence-score", type=float, default=0.64)
    parser.add_argument("--calibration-score", type=float, default=0.68)
    parser.add_argument("--odds-stability-score", type=float, default=0.70)
    parser.add_argument("--volatility-penalty", type=float, default=0.08)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalHandicapOddsImportOptions:
    return HistoricalHandicapOddsImportOptions(
        source_label=args.source_label,
        allowed_market_types=_market_tuple(args.allowed_market_types),
        require_complete_lines=not args.allow_incomplete_lines,
        require_integer_lines=not args.allow_non_integer_lines,
        replace_existing_lines=not args.append_existing_lines,
        data_quality_score=args.data_quality_score,
        model_confidence_score=args.model_confidence_score,
        calibration_score=args.calibration_score,
        odds_stability_score=args.odds_stability_score,
        volatility_penalty=args.volatility_penalty,
    )


def _cli_summary(
    result: HistoricalHandicapOddsImportResult,
    *,
    output_path: Path | None,
) -> dict[str, object]:
    return {
        **result.summary_json,
        "output_path": str(output_path) if output_path is not None else None,
        "imported_lines": [
            item.model_dump(mode="json") for item in result.imported_lines
        ],
    }


def _market_tuple(value: str) -> tuple[RecommendationMarketType, ...]:
    markets: list[RecommendationMarketType] = []
    valid = set(HANDICAP_IMPORT_MARKETS)
    for item in [part.strip() for part in value.split(",") if part.strip()]:
        if item not in valid:
            raise ValueError(f"unsupported handicap import market type: {item}")
        markets.append(item)
    return tuple(markets)


def _market_type(value: str) -> RecommendationMarketType:
    normalized = value.strip().lower()
    aliases = {
        "chinese_handicap_1x2": "cn_handicap_1x2",
        "cn_handicap": "cn_handicap_1x2",
        "sporttery_handicap_1x2": "cn_handicap_1x2",
        "euro_handicap_1x2": "european_handicap_1x2",
        "european_handicap": "european_handicap_1x2",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized == "cn_handicap_1x2":
        return "cn_handicap_1x2"
    if normalized == "european_handicap_1x2":
        return "european_handicap_1x2"
    return "1x2"


def _handicap_outcome(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized in {"home", "home_win", "handicap_home_win", "h", "1"}:
        return "handicap_home_win"
    if normalized in {"draw", "handicap_draw", "x", "d"}:
        return "handicap_draw"
    if normalized in {"away", "away_win", "handicap_away_win", "a", "2"}:
        return "handicap_away_win"
    return None


def _required_text(
    row: Mapping[str, str | None],
    column: str,
    *,
    row_number: int,
) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise ValueError(f"missing required column {column} on row {row_number}")
    return value.strip()


def _optional_text(row: Mapping[str, str | None], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    text = value.strip()
    return text or None


def _optional_float(row: Mapping[str, str | None], column: str) -> float | None:
    value = _optional_text(row, column)
    if value is None:
        return None
    return _float(value)


def _float(value: str) -> float:
    return float(value)


def _optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _metadata_json(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    payload = loads(value)
    if not isinstance(payload, dict):
        raise ValueError("metadata_json must be a JSON object")
    return dict(payload)


def _is_integer_line(line: float) -> bool:
    return abs(line - round(line)) <= 1e-9
