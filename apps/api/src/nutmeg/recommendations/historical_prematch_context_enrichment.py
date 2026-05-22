from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

from nutmeg.domain.features import (
    PrematchAvailabilityFeature,
    PrematchLineupFeature,
    PrematchLineupType,
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    PrematchSemanticSignal,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
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

LINEUP_REQUIRED_COLUMNS = (
    "fixture_id",
    "snapshot_time_utc",
    "lineup_type",
    "source",
)
AVAILABILITY_REQUIRED_COLUMNS = (
    "fixture_id",
    "snapshot_time_utc",
    "source",
)
SEMANTIC_REQUIRED_COLUMNS = (
    "fixture_id",
    "signal_name",
    "source",
    "confidence",
    "evidence_text_short",
    "extracted_at_utc",
)

DEFAULT_PREMATCH_CONTEXT_ENRICHMENT_FEATURE_VERSION = (
    "features-v3.1-frozen-prematch-context"
)


class HistoricalPrematchContextEnrichmentOptions(BaseModel):
    slice_id: str | None = None
    name: str | None = None
    feature_version: str = DEFAULT_PREMATCH_CONTEXT_ENRICHMENT_FEATURE_VERSION
    fixture_reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    historical_stats_completeness: float = Field(default=0.65, ge=0.0, le=1.0)
    provider_consistency: float = Field(default=0.75, ge=0.0, le=1.0)
    preserve_existing_lineup: bool = True
    preserve_existing_availability: bool = True
    preserve_existing_odds_movement: bool = True
    preserve_existing_semantic_signals: bool = True
    append_note: str = (
        "Frozen structured prematch context was merged from reviewed CSV inputs."
    )


class HistoricalPrematchLineupCsvRow(BaseModel):
    row_number: int = Field(ge=2)
    fixture_id: str = Field(min_length=1)
    snapshot_time_utc: datetime
    lineup_type: PrematchLineupType = "unknown"
    expected_lineup_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    starting_xi_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    bench_dropoff_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    source_snapshot_ref: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchAvailabilityCsvRow(BaseModel):
    row_number: int = Field(ge=2)
    fixture_id: str = Field(min_length=1)
    snapshot_time_utc: datetime
    unavailable_key_player_count: int = Field(default=0, ge=0)
    doubtful_key_player_count: int = Field(default=0, ge=0)
    key_player_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    defender_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    goalkeeper_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    striker_absence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    source_snapshot_ref: str | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchSemanticCsvRow(BaseModel):
    row_number: int = Field(ge=2)
    fixture_id: str = Field(min_length=1)
    signal_name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_text_short: str = Field(min_length=1, max_length=280)
    extracted_at_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchContextEnrichmentResult(BaseModel):
    historical_slice: HistoricalRecommendationSlice
    completeness_result: HistoricalFeatureCompletenessResult
    lineup_row_count: int = Field(ge=0)
    availability_row_count: int = Field(ge=0)
    semantic_row_count: int = Field(ge=0)
    enriched_fixture_count: int = Field(ge=0)
    feature_snapshot_fixture_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def enrich_historical_slice_with_frozen_prematch_context(
    historical_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalPrematchContextEnrichmentOptions | None = None,
    lineup_rows: Sequence[HistoricalPrematchLineupCsvRow] = (),
    availability_rows: Sequence[HistoricalPrematchAvailabilityCsvRow] = (),
    semantic_rows: Sequence[HistoricalPrematchSemanticCsvRow] = (),
    completeness_options: HistoricalFeatureCompletenessOptions | None = None,
) -> HistoricalPrematchContextEnrichmentResult:
    resolved_options = options or HistoricalPrematchContextEnrichmentOptions()
    if not lineup_rows and not availability_rows and not semantic_rows:
        raise ValueError("provide at least one frozen prematch context CSV row")

    fixture_ids = {fixture.fixture_id for fixture in historical_slice.fixtures}
    lineup_by_fixture, lineup_warnings = _latest_lineups(lineup_rows, fixture_ids)
    availability_by_fixture, availability_warnings = _latest_availability(
        availability_rows,
        fixture_ids,
    )
    semantic_by_fixture, semantic_warnings = _semantic_by_fixture(
        semantic_rows,
        fixture_ids,
    )
    enriched_fixtures = [
        _enriched_fixture(
            fixture,
            options=resolved_options,
            lineup=lineup_by_fixture.get(fixture.fixture_id),
            availability=availability_by_fixture.get(fixture.fixture_id),
            semantic_signals=semantic_by_fixture.get(fixture.fixture_id, ()),
        )
        for fixture in historical_slice.fixtures
    ]
    enriched_fixture_ids = [
        fixture.fixture_id
        for fixture in historical_slice.fixtures
        if fixture.fixture_id in lineup_by_fixture
        or fixture.fixture_id in availability_by_fixture
        or fixture.fixture_id in semantic_by_fixture
    ]
    output_slice = historical_slice.model_copy(
        update={
            "metadata": historical_slice.metadata.model_copy(
                update={
                    "slice_id": (
                        resolved_options.slice_id or historical_slice.metadata.slice_id
                    ),
                    "name": resolved_options.name or historical_slice.metadata.name,
                    "notes": _merged_notes(
                        historical_slice.metadata.notes,
                        resolved_options.append_note,
                    ),
                }
            ),
            "fixtures": enriched_fixtures,
        }
    )
    completeness = evaluate_historical_feature_completeness(
        output_slice,
        options=completeness_options or HistoricalFeatureCompletenessOptions(),
    )
    warnings = [
        *lineup_warnings,
        *availability_warnings,
        *semantic_warnings,
        *_source_time_warnings(output_slice),
        *completeness.warnings,
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_context_enrichment_v3_1",
        "slice_id": output_slice.metadata.slice_id,
        "source_slice_id": historical_slice.metadata.slice_id,
        "fixture_count": len(output_slice.fixtures),
        "lineup_row_count": len(lineup_rows),
        "availability_row_count": len(availability_rows),
        "semantic_row_count": len(semantic_rows),
        "enriched_fixture_count": len(enriched_fixture_ids),
        "enriched_fixture_ids": enriched_fixture_ids,
        "feature_snapshot_fixture_count": sum(
            1 for fixture in output_slice.fixtures if fixture.feature_snapshot is not None
        ),
        "completeness_passed": completeness.passed,
        "completeness_key": completeness.completeness_key,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    return HistoricalPrematchContextEnrichmentResult(
        historical_slice=output_slice,
        completeness_result=completeness,
        lineup_row_count=len(lineup_rows),
        availability_row_count=len(availability_rows),
        semantic_row_count=len(semantic_rows),
        enriched_fixture_count=len(enriched_fixture_ids),
        feature_snapshot_fixture_count=cast(int, summary["feature_snapshot_fixture_count"]),
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    historical_slice = load_historical_recommendation_slice(args.input_slice_path)
    result = enrich_historical_slice_with_frozen_prematch_context(
        historical_slice,
        options=_options_from_args(args),
        lineup_rows=_load_lineup_csv(args.lineup_csv),
        availability_rows=_load_availability_csv(args.availability_csv),
        semantic_rows=_load_semantic_csv(args.semantic_csv),
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


def _enriched_fixture(
    fixture: HistoricalFixture,
    *,
    options: HistoricalPrematchContextEnrichmentOptions,
    lineup: HistoricalPrematchLineupCsvRow | None,
    availability: HistoricalPrematchAvailabilityCsvRow | None,
    semantic_signals: Sequence[HistoricalPrematchSemanticCsvRow],
) -> HistoricalFixture:
    existing = _existing_prematch_features(fixture)
    prematch_features = StructuredPrematchFeatureSet(
        lineup=(
            _lineup_feature(lineup)
            or (existing.lineup if options.preserve_existing_lineup else None)
        ),
        availability=(
            _availability_feature(availability)
            or (
                existing.availability
                if options.preserve_existing_availability
                else None
            )
        ),
        odds_movements=(
            existing.odds_movements if options.preserve_existing_odds_movement else []
        ),
        semantic_signals=_merged_semantic_signals(
            (
                existing.semantic_signals
                if options.preserve_existing_semantic_signals
                else []
            ),
            [_semantic_signal(row) for row in semantic_signals],
        ),
        metadata_json={
            **existing.metadata_json,
            "frozen_prematch_context_enrichment": True,
        },
    )
    feature_snapshot = build_structured_prematch_feature_snapshot(
        fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        kickoff_time_utc=fixture.kickoff_time_utc,
        feature_time_utc=fixture.prediction_time_utc,
        feature_version=options.feature_version,
        fixture_reliability=options.fixture_reliability,
        historical_stats_completeness=options.historical_stats_completeness,
        provider_consistency=options.provider_consistency,
        prematch_features=prematch_features,
    )
    return fixture.model_copy(
        update={
            "feature_version": options.feature_version,
            "feature_snapshot": feature_snapshot,
            "metadata_json": {
                **fixture.metadata_json,
                "frozen_prematch_context_enriched": True,
            },
        }
    )


def _existing_prematch_features(
    fixture: HistoricalFixture,
) -> StructuredPrematchFeatureSet:
    snapshot = fixture.feature_snapshot
    if snapshot is None:
        return StructuredPrematchFeatureSet()
    raw_context = snapshot.features_json.get("prematch_context")
    if not isinstance(raw_context, dict):
        return StructuredPrematchFeatureSet()
    lineup = _optional_model(PrematchLineupFeature, raw_context.get("lineup"))
    availability = _optional_model(
        PrematchAvailabilityFeature,
        raw_context.get("availability"),
    )
    return StructuredPrematchFeatureSet(
        lineup=lineup,
        availability=availability,
        odds_movements=_existing_odds_movements(raw_context.get("odds_movement")),
        semantic_signals=_existing_semantic_signals(
            raw_context.get("semantic_signals")
        ),
        metadata_json=_json_dict(raw_context.get("metadata_json")),
    )


def _existing_odds_movements(value: object) -> list[PrematchOddsMovementFeature]:
    if not isinstance(value, list):
        return []
    movements: list[PrematchOddsMovementFeature] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        raw_points = raw_item.get("points")
        points = [
            PrematchOddsMovementPoint.model_validate(point)
            for point in raw_points
            if isinstance(point, dict)
        ] if isinstance(raw_points, list) else []
        market_type = raw_item.get("market_type")
        outcome = raw_item.get("outcome")
        if not isinstance(market_type, str) or not isinstance(outcome, str):
            continue
        movements.append(
            PrematchOddsMovementFeature(
                market_type=market_type,
                outcome=outcome,
                points=points,
                bookmaker_disagreement=_optional_number(
                    raw_item.get("bookmaker_disagreement")
                ),
                exchange_liquidity=_optional_number(
                    raw_item.get("exchange_liquidity")
                ),
                market_delay_signal=_number(raw_item.get("market_delay_signal")),
                metadata_json=_json_dict(raw_item.get("metadata_json")),
            )
        )
    return movements


def _existing_semantic_signals(value: object) -> list[PrematchSemanticSignal]:
    if not isinstance(value, list):
        return []
    return [
        PrematchSemanticSignal.model_validate(item)
        for item in value
        if isinstance(item, dict)
    ]


def _lineup_feature(
    row: HistoricalPrematchLineupCsvRow | None,
) -> PrematchLineupFeature | None:
    if row is None:
        return None
    return PrematchLineupFeature(
        lineup_type=row.lineup_type,
        snapshot_time_utc=row.snapshot_time_utc,
        expected_lineup_confidence=row.expected_lineup_confidence,
        starting_xi_strength=row.starting_xi_strength,
        bench_dropoff_score=row.bench_dropoff_score,
        source=row.source,
        source_snapshot_ref=row.source_snapshot_ref,
        metadata_json=row.metadata_json,
    )


def _availability_feature(
    row: HistoricalPrematchAvailabilityCsvRow | None,
) -> PrematchAvailabilityFeature | None:
    if row is None:
        return None
    return PrematchAvailabilityFeature(
        snapshot_time_utc=row.snapshot_time_utc,
        unavailable_key_player_count=row.unavailable_key_player_count,
        doubtful_key_player_count=row.doubtful_key_player_count,
        key_player_absence_score=row.key_player_absence_score,
        defender_absence_score=row.defender_absence_score,
        goalkeeper_absence_score=row.goalkeeper_absence_score,
        striker_absence_score=row.striker_absence_score,
        source=row.source,
        source_snapshot_ref=row.source_snapshot_ref,
        metadata_json=row.metadata_json,
    )


def _semantic_signal(row: HistoricalPrematchSemanticCsvRow) -> PrematchSemanticSignal:
    return PrematchSemanticSignal(
        signal_name=row.signal_name,
        source=row.source,
        confidence=row.confidence,
        evidence_text_short=row.evidence_text_short,
        extracted_at_utc=row.extracted_at_utc,
        metadata_json=row.metadata_json,
    )


def _merged_semantic_signals(
    existing: Sequence[PrematchSemanticSignal],
    incoming: Sequence[PrematchSemanticSignal],
) -> list[PrematchSemanticSignal]:
    deduped: list[PrematchSemanticSignal] = []
    seen: set[tuple[str, str, str]] = set()
    for signal in [*existing, *incoming]:
        key = (
            signal.signal_name,
            signal.source,
            _aware_utc(signal.extracted_at_utc).isoformat(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    return deduped


def _latest_lineups(
    rows: Sequence[HistoricalPrematchLineupCsvRow],
    fixture_ids: set[str],
) -> tuple[dict[str, HistoricalPrematchLineupCsvRow], list[str]]:
    by_fixture: dict[str, list[HistoricalPrematchLineupCsvRow]] = {}
    warnings: list[str] = []
    for row in rows:
        if row.fixture_id not in fixture_ids:
            warnings.append(
                f"prematch_context_enrichment:unknown_lineup_fixture:{row.fixture_id}:row_{row.row_number}"
            )
            continue
        by_fixture.setdefault(row.fixture_id, []).append(row)
    return _latest_rows(by_fixture, warning_prefix="duplicate_lineup_fixture", warnings=warnings)


def _latest_availability(
    rows: Sequence[HistoricalPrematchAvailabilityCsvRow],
    fixture_ids: set[str],
) -> tuple[dict[str, HistoricalPrematchAvailabilityCsvRow], list[str]]:
    by_fixture: dict[str, list[HistoricalPrematchAvailabilityCsvRow]] = {}
    warnings: list[str] = []
    for row in rows:
        if row.fixture_id not in fixture_ids:
            warnings.append(
                f"prematch_context_enrichment:unknown_availability_fixture:{row.fixture_id}:row_{row.row_number}"
            )
            continue
        by_fixture.setdefault(row.fixture_id, []).append(row)
    return _latest_rows(
        by_fixture,
        warning_prefix="duplicate_availability_fixture",
        warnings=warnings,
    )


def _latest_rows(
    rows_by_fixture: dict[str, list[Any]],
    *,
    warning_prefix: str,
    warnings: list[str],
) -> tuple[dict[str, Any], list[str]]:
    latest: dict[str, Any] = {}
    for fixture_id, rows in rows_by_fixture.items():
        if len(rows) > 1:
            warnings.append(f"prematch_context_enrichment:{warning_prefix}:{fixture_id}")
        latest[fixture_id] = max(
            rows,
            key=lambda row: (_aware_utc(row.snapshot_time_utc), row.row_number),
        )
    return latest, warnings


def _semantic_by_fixture(
    rows: Sequence[HistoricalPrematchSemanticCsvRow],
    fixture_ids: set[str],
) -> tuple[dict[str, list[HistoricalPrematchSemanticCsvRow]], list[str]]:
    by_fixture: dict[str, list[HistoricalPrematchSemanticCsvRow]] = {}
    warnings: list[str] = []
    for row in rows:
        if row.fixture_id not in fixture_ids:
            warnings.append(
                f"prematch_context_enrichment:unknown_semantic_fixture:{row.fixture_id}:row_{row.row_number}"
            )
            continue
        by_fixture.setdefault(row.fixture_id, []).append(row)
    for fixture_rows in by_fixture.values():
        fixture_rows.sort(key=lambda row: (_aware_utc(row.extracted_at_utc), row.row_number))
    return by_fixture, warnings


def _source_time_warnings(
    historical_slice: HistoricalRecommendationSlice,
) -> list[str]:
    warnings: list[str] = []
    for fixture in historical_slice.fixtures:
        context = _existing_prematch_features(fixture)
        source_times = [
            *(
                [context.lineup.snapshot_time_utc]
                if context.lineup is not None
                else []
            ),
            *(
                [context.availability.snapshot_time_utc]
                if context.availability is not None
                else []
            ),
            *(signal.extracted_at_utc for signal in context.semantic_signals),
        ]
        for source_time in source_times:
            if source_time is None:
                continue
            if _aware_utc(source_time) > _aware_utc(fixture.prediction_time_utc):
                warnings.append(
                    "prematch_context_enrichment:source_after_prediction:"
                    f"{fixture.fixture_id}"
                )
            if _aware_utc(source_time) >= _aware_utc(fixture.kickoff_time_utc):
                warnings.append(
                    "prematch_context_enrichment:source_not_before_kickoff:"
                    f"{fixture.fixture_id}"
                )
    return _dedupe_strings(warnings)


def _load_lineup_csv(path: Path | None) -> list[HistoricalPrematchLineupCsvRow]:
    if path is None:
        return []
    return [
        HistoricalPrematchLineupCsvRow(
            row_number=row_number,
            fixture_id=_required_text(row, "fixture_id", row_number=row_number),
            snapshot_time_utc=_datetime(
                _required_text(row, "snapshot_time_utc", row_number=row_number)
            ),
            lineup_type=cast(
                PrematchLineupType,
                _required_text(row, "lineup_type", row_number=row_number),
            ),
            expected_lineup_confidence=_optional_float(
                row,
                "expected_lineup_confidence",
            ),
            starting_xi_strength=_optional_float(row, "starting_xi_strength"),
            bench_dropoff_score=_optional_float(row, "bench_dropoff_score") or 0.0,
            source=_required_text(row, "source", row_number=row_number),
            source_snapshot_ref=_optional_text(row, "source_snapshot_ref"),
            metadata_json=_json_object(_optional_text(row, "metadata_json")),
        )
        for row_number, row in _csv_rows(path, required_columns=LINEUP_REQUIRED_COLUMNS)
    ]


def _load_availability_csv(
    path: Path | None,
) -> list[HistoricalPrematchAvailabilityCsvRow]:
    if path is None:
        return []
    return [
        HistoricalPrematchAvailabilityCsvRow(
            row_number=row_number,
            fixture_id=_required_text(row, "fixture_id", row_number=row_number),
            snapshot_time_utc=_datetime(
                _required_text(row, "snapshot_time_utc", row_number=row_number)
            ),
            unavailable_key_player_count=_optional_int(
                row,
                "unavailable_key_player_count",
            )
            or 0,
            doubtful_key_player_count=_optional_int(row, "doubtful_key_player_count")
            or 0,
            key_player_absence_score=_optional_float(
                row,
                "key_player_absence_score",
            )
            or 0.0,
            defender_absence_score=_optional_float(row, "defender_absence_score")
            or 0.0,
            goalkeeper_absence_score=_optional_float(row, "goalkeeper_absence_score")
            or 0.0,
            striker_absence_score=_optional_float(row, "striker_absence_score")
            or 0.0,
            source=_required_text(row, "source", row_number=row_number),
            source_snapshot_ref=_optional_text(row, "source_snapshot_ref"),
            metadata_json=_json_object(_optional_text(row, "metadata_json")),
        )
        for row_number, row in _csv_rows(
            path,
            required_columns=AVAILABILITY_REQUIRED_COLUMNS,
        )
    ]


def _load_semantic_csv(path: Path | None) -> list[HistoricalPrematchSemanticCsvRow]:
    if path is None:
        return []
    return [
        HistoricalPrematchSemanticCsvRow(
            row_number=row_number,
            fixture_id=_required_text(row, "fixture_id", row_number=row_number),
            signal_name=_required_text(row, "signal_name", row_number=row_number),
            source=_required_text(row, "source", row_number=row_number),
            confidence=_float(_required_text(row, "confidence", row_number=row_number)),
            evidence_text_short=_required_text(
                row,
                "evidence_text_short",
                row_number=row_number,
            ),
            extracted_at_utc=_datetime(
                _required_text(row, "extracted_at_utc", row_number=row_number)
            ),
            metadata_json=_json_object(_optional_text(row, "metadata_json")),
        )
        for row_number, row in _csv_rows(
            path,
            required_columns=SEMANTIC_REQUIRED_COLUMNS,
        )
    ]


def _csv_rows(
    path: Path,
    *,
    required_columns: Sequence[str],
) -> list[tuple[int, Mapping[str, str | None]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = DictReader(handle)
        _validate_csv_columns(path, reader.fieldnames, required_columns)
        return [
            (row_number, row)
            for row_number, row in enumerate(reader, start=2)
        ]


def _validate_csv_columns(
    input_path: Path,
    fieldnames: Sequence[str] | None,
    required_columns: Sequence[str],
) -> None:
    if fieldnames is None:
        raise ValueError(f"frozen prematch context CSV has no header: {input_path}")
    missing = [column for column in required_columns if column not in fieldnames]
    if missing:
        raise ValueError(
            f"frozen prematch context CSV missing required columns: {','.join(missing)}"
        )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Merge reviewed frozen lineup, availability, and semantic/news CSV "
            "features into an existing historical recommendation slice."
        )
    )
    parser.add_argument("input_slice_path", type=Path)
    parser.add_argument("--lineup-csv", type=Path)
    parser.add_argument("--availability-csv", type=Path)
    parser.add_argument("--semantic-csv", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--completeness-output-path", type=Path)
    parser.add_argument("--suite-manifest-output-path", type=Path)
    parser.add_argument("--slice-id", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument(
        "--feature-version",
        default=DEFAULT_PREMATCH_CONTEXT_ENRICHMENT_FEATURE_VERSION,
    )
    parser.add_argument("--fixture-reliability", type=float, default=1.0)
    parser.add_argument("--historical-stats-completeness", type=float, default=0.65)
    parser.add_argument("--provider-consistency", type=float, default=0.75)
    parser.add_argument("--drop-existing-lineup", action="store_true")
    parser.add_argument("--drop-existing-availability", action="store_true")
    parser.add_argument("--drop-existing-odds-movement", action="store_true")
    parser.add_argument("--drop-existing-semantic-signals", action="store_true")
    parser.add_argument("--note", default=None)
    parser.add_argument("--min-fixture-count", type=int, default=1)
    parser.add_argument("--min-feature-snapshot-coverage", type=float, default=1.0)
    parser.add_argument("--min-lineup-coverage", type=float, default=0.0)
    parser.add_argument("--min-availability-coverage", type=float, default=0.0)
    parser.add_argument("--min-odds-movement-coverage", type=float, default=0.0)
    parser.add_argument("--min-semantic-signal-coverage", type=float, default=0.0)
    parser.add_argument("--min-source-ref-coverage", type=float, default=0.0)
    parser.add_argument("--min-average-feature-data-quality-score", type=float)
    parser.add_argument("--min-feature-data-quality-score", type=float)
    parser.add_argument("--allow-missing-prematch-context", action="store_true")
    parser.add_argument("--allow-feature-after-prediction", action="store_true")
    parser.add_argument("--allow-feature-not-before-kickoff", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if args.lineup_csv is None and args.availability_csv is None and args.semantic_csv is None:
        parser.error("provide at least one of --lineup-csv, --availability-csv, --semantic-csv")
    return args


def _options_from_args(args: Namespace) -> HistoricalPrematchContextEnrichmentOptions:
    return HistoricalPrematchContextEnrichmentOptions(
        slice_id=args.slice_id,
        name=args.name,
        feature_version=args.feature_version,
        fixture_reliability=args.fixture_reliability,
        historical_stats_completeness=args.historical_stats_completeness,
        provider_consistency=args.provider_consistency,
        preserve_existing_lineup=not args.drop_existing_lineup,
        preserve_existing_availability=not args.drop_existing_availability,
        preserve_existing_odds_movement=not args.drop_existing_odds_movement,
        preserve_existing_semantic_signals=not args.drop_existing_semantic_signals,
        append_note=args.note
        or HistoricalPrematchContextEnrichmentOptions().append_note,
    )


def _completeness_options_from_args(
    args: Namespace,
) -> HistoricalFeatureCompletenessOptions:
    return HistoricalFeatureCompletenessOptions(
        min_fixture_count=args.min_fixture_count,
        min_feature_snapshot_coverage=args.min_feature_snapshot_coverage,
        min_lineup_coverage=args.min_lineup_coverage,
        min_availability_coverage=args.min_availability_coverage,
        min_odds_movement_coverage=args.min_odds_movement_coverage,
        min_semantic_signal_coverage=args.min_semantic_signal_coverage,
        min_source_ref_coverage=args.min_source_ref_coverage,
        min_average_feature_data_quality_score=(
            args.min_average_feature_data_quality_score
        ),
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        require_prematch_context=not args.allow_missing_prematch_context,
        require_feature_not_after_prediction=not args.allow_feature_after_prediction,
        require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
    )


def _suite_manifest(
    historical_slice: HistoricalRecommendationSlice,
    *,
    slice_path: Path,
    manifest_path: Path,
) -> HistoricalRecommendationSuiteManifest:
    return HistoricalRecommendationSuiteManifest(
        suite_id=f"{historical_slice.metadata.slice_id}_suite_v1",
        name=f"{historical_slice.metadata.name} suite",
        description="Frozen structured prematch context enrichment suite.",
        tags=["prematch-context", "frozen-features", "feature-completeness"],
        notes=[
            "Generated from reviewed local CSV inputs.",
            "No provider API calls are performed by this enrichment command.",
        ],
        slices=[
            HistoricalRecommendationSuiteManifestSlice(
                slice_path=_relative_path(slice_path, base_dir=manifest_path.parent),
                enabled=True,
                tags=["prematch-context", "enriched"],
                notes=["Generated by historical prematch context enrichment."],
            )
        ],
    )


def _merged_notes(existing_notes: Sequence[str], note: str) -> list[str]:
    notes = list(existing_notes)
    if note not in notes:
        notes.append(note)
    return notes


def _optional_model(model_type: type[Any], value: object) -> Any | None:
    if not isinstance(value, dict):
        return None
    return model_type.model_validate(value)


def _json_dict(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _json_object(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    parsed: Any = loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("CSV metadata_json fields must contain JSON objects")
    return cast(dict[str, object], parsed)


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


def _optional_int(row: Mapping[str, str | None], column: str) -> int | None:
    value = _optional_text(row, column)
    if value is None:
        return None
    return int(value)


def _number(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _float(value: str) -> float:
    return float(value)


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _relative_path(path: Path, *, base_dir: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
