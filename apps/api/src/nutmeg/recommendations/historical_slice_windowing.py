from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from json import dumps
from os.path import relpath
from pathlib import Path

from pydantic import BaseModel, Field

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifest,
    HistoricalRecommendationSuiteManifestSlice,
    load_historical_recommendation_suite_manifest_bundle,
)


class HistoricalSliceWindowingOptions(BaseModel):
    window_fixture_count: int = Field(default=12, ge=1)
    stride_fixture_count: int = Field(default=12, ge=1)
    min_fixture_count: int = Field(default=8, ge=1)
    as_of_offset_minutes: int = Field(default=5, ge=1)
    normalize_fixture_prediction_time: bool = True
    slice_id_suffix: str = "rolling_window_v1"


class HistoricalWindowedSliceRecord(BaseModel):
    source_slice_id: str
    output_slice_id: str
    output_slice_path: Path
    competition_id: str
    season: str | None = None
    window_index: int = Field(ge=1)
    source_start_index: int = Field(ge=0)
    source_end_index: int = Field(ge=0)
    fixture_count: int = Field(ge=1)
    as_of_time_utc: datetime
    first_kickoff_time_utc: datetime
    last_kickoff_time_utc: datetime


class HistoricalSliceWindowingReport(BaseModel):
    report_key: str
    source_slice_count: int = Field(ge=0)
    generated_slice_count: int = Field(ge=0)
    skipped_window_count: int = Field(ge=0)
    output_dir: Path
    suite_manifest_output_path: Path | None = None
    generated_fixture_count: int = Field(ge=0)
    records: list[HistoricalWindowedSliceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_windowed_historical_recommendation_slices(
    source_slice: HistoricalRecommendationSlice,
    *,
    options: HistoricalSliceWindowingOptions | None = None,
) -> list[HistoricalRecommendationSlice]:
    resolved_options = options or HistoricalSliceWindowingOptions()
    sorted_fixtures = sorted(
        source_slice.fixtures,
        key=lambda fixture: (
            _aware_utc(fixture.kickoff_time_utc),
            fixture.fixture_id,
        ),
    )
    windowed_slices: list[HistoricalRecommendationSlice] = []
    window_index = 0
    for start_index in range(
        0,
        len(sorted_fixtures),
        resolved_options.stride_fixture_count,
    ):
        window_fixtures = sorted_fixtures[
            start_index : start_index + resolved_options.window_fixture_count
        ]
        if len(window_fixtures) < resolved_options.min_fixture_count:
            continue
        window_index += 1
        first_kickoff = _aware_utc(window_fixtures[0].kickoff_time_utc)
        as_of_time = first_kickoff - timedelta(
            minutes=resolved_options.as_of_offset_minutes
        )
        output_slice_id = (
            f"{source_slice.metadata.slice_id}_"
            f"{resolved_options.slice_id_suffix}_{window_index:03d}"
        )
        cloned_fixtures = [
            _window_fixture(
                fixture,
                as_of_time=as_of_time,
                source_slice_id=source_slice.metadata.slice_id,
                output_slice_id=output_slice_id,
                normalize_prediction_time=(
                    resolved_options.normalize_fixture_prediction_time
                ),
            )
            for fixture in window_fixtures
        ]
        windowed_slices.append(
            HistoricalRecommendationSlice(
                metadata=source_slice.metadata.model_copy(
                    deep=True,
                    update={
                        "slice_id": output_slice_id,
                        "name": (
                            f"{source_slice.metadata.name} rolling window "
                            f"{window_index:03d}"
                        ),
                        "notes": [
                            *source_slice.metadata.notes,
                            (
                                "Generated from source slice "
                                f"{source_slice.metadata.slice_id} by "
                                "historical_slice_windowing."
                            ),
                            (
                                "Fixture prediction times are normalized to the "
                                "window as-of time for recommendation backtest "
                                "eligibility; this is a shadow evaluation sample, "
                                "not a production data feed."
                            ),
                        ],
                    },
                ),
                as_of_time_utc=as_of_time,
                fixtures=cloned_fixtures,
            )
        )
    return windowed_slices


def write_windowed_historical_recommendation_suite(
    source_slices: Sequence[HistoricalRecommendationSlice],
    *,
    output_dir: Path,
    suite_manifest_output_path: Path | None = None,
    suite_id: str,
    suite_name: str,
    suite_description: str | None = None,
    options: HistoricalSliceWindowingOptions | None = None,
) -> HistoricalSliceWindowingReport:
    resolved_options = options or HistoricalSliceWindowingOptions()
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[HistoricalWindowedSliceRecord] = []
    warnings: list[str] = []
    manifest_slices: list[HistoricalRecommendationSuiteManifestSlice] = []
    skipped_window_count = 0

    for source_slice in source_slices:
        source_window_count = 0
        sorted_fixtures = sorted(
            source_slice.fixtures,
            key=lambda fixture: (
                _aware_utc(fixture.kickoff_time_utc),
                fixture.fixture_id,
            ),
        )
        for start_index in range(
            0,
            len(sorted_fixtures),
            resolved_options.stride_fixture_count,
        ):
            window_fixtures = sorted_fixtures[
                start_index : start_index + resolved_options.window_fixture_count
            ]
            if len(window_fixtures) < resolved_options.min_fixture_count:
                skipped_window_count += 1
                continue
            source_window_count += 1
        if source_window_count == 0:
            warnings.append(
                "historical_slice_windowing:no_windows_generated:"
                f"{source_slice.metadata.slice_id}"
            )

        for windowed_slice in build_windowed_historical_recommendation_slices(
            source_slice,
            options=resolved_options,
        ):
            output_path = output_dir / f"{windowed_slice.metadata.slice_id}.json"
            output_path.write_text(
                f"{windowed_slice.model_dump_json(indent=2)}\n",
                encoding="utf-8",
            )
            first_kickoff = min(
                _aware_utc(fixture.kickoff_time_utc)
                for fixture in windowed_slice.fixtures
            )
            last_kickoff = max(
                _aware_utc(fixture.kickoff_time_utc)
                for fixture in windowed_slice.fixtures
            )
            window_index = len(
                [
                    record
                    for record in records
                    if record.source_slice_id == source_slice.metadata.slice_id
                ]
            ) + 1
            source_start_index = (window_index - 1) * resolved_options.stride_fixture_count
            source_end_index = source_start_index + len(windowed_slice.fixtures) - 1
            records.append(
                HistoricalWindowedSliceRecord(
                    source_slice_id=source_slice.metadata.slice_id,
                    output_slice_id=windowed_slice.metadata.slice_id,
                    output_slice_path=output_path,
                    competition_id=windowed_slice.metadata.competition_id,
                    season=windowed_slice.metadata.season,
                    window_index=window_index,
                    source_start_index=source_start_index,
                    source_end_index=source_end_index,
                    fixture_count=len(windowed_slice.fixtures),
                    as_of_time_utc=_aware_utc(windowed_slice.as_of_time_utc),
                    first_kickoff_time_utc=first_kickoff,
                    last_kickoff_time_utc=last_kickoff,
                )
            )
            if suite_manifest_output_path is not None:
                manifest_slices.append(
                    HistoricalRecommendationSuiteManifestSlice(
                        slice_path=_relative_path(
                            output_path,
                            base_dir=suite_manifest_output_path.parent,
                        ),
                        enabled=True,
                        tags=[
                            "historical-window",
                            "rolling-window",
                            windowed_slice.metadata.competition_id.lower(),
                            _season_tag(windowed_slice.metadata.season),
                        ],
                        notes=[
                            (
                                "Generated from "
                                f"{source_slice.metadata.slice_id} by "
                                "nutmeg-recommendation-historical-slice-window."
                            )
                        ],
                    )
                )

    if suite_manifest_output_path is not None:
        suite_manifest_output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = HistoricalRecommendationSuiteManifest(
            suite_id=suite_id,
            name=suite_name,
            description=suite_description,
            slices=manifest_slices,
            tags=["historical-window", "rolling-window", "shadow-evaluation"],
            notes=[
                (
                    "Generated by nutmeg-recommendation-historical-slice-window "
                    "from existing frozen historical recommendation slices."
                ),
                (
                    "Windowed slices normalize fixture prediction_time_utc to "
                    "the slice as_of_time_utc so final-answer backtests have "
                    "enough pre-kickoff fixture candidates."
                ),
            ],
        )
        suite_manifest_output_path.write_text(
            f"{manifest.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    elif not records:
        warnings.append("historical_slice_windowing:no_records_generated")

    summary = _summary(
        source_slices,
        records=records,
        skipped_window_count=skipped_window_count,
        output_dir=output_dir,
        suite_manifest_output_path=suite_manifest_output_path,
        options=resolved_options,
        warnings=warnings,
    )
    report_key = _report_key(summary)
    return HistoricalSliceWindowingReport(
        report_key=report_key,
        source_slice_count=len(source_slices),
        generated_slice_count=len(records),
        skipped_window_count=skipped_window_count,
        output_dir=output_dir,
        suite_manifest_output_path=suite_manifest_output_path,
        generated_fixture_count=sum(record.fixture_count for record in records),
        records=records,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    source_slices = _source_slices_from_args(args)
    report = write_windowed_historical_recommendation_suite(
        source_slices,
        output_dir=args.output_dir,
        suite_manifest_output_path=args.suite_manifest_output_path,
        suite_id=args.suite_id,
        suite_name=args.suite_name,
        suite_description=args.suite_description,
        options=_options_from_args(args),
    )
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)


def _window_fixture(
    fixture: HistoricalFixture,
    *,
    as_of_time: datetime,
    source_slice_id: str,
    output_slice_id: str,
    normalize_prediction_time: bool,
) -> HistoricalFixture:
    original_prediction_time = _aware_utc(fixture.prediction_time_utc)
    prediction_time = as_of_time if normalize_prediction_time else original_prediction_time
    metadata = {
        **fixture.metadata_json,
        "windowed_source_slice_id": source_slice_id,
        "windowed_output_slice_id": output_slice_id,
        "original_prediction_time_utc": original_prediction_time.isoformat(),
        "window_as_of_time_utc": as_of_time.isoformat(),
        "prediction_time_policy": (
            "window_as_of_time" if normalize_prediction_time else "source_fixture_time"
        ),
    }
    return fixture.model_copy(
        deep=True,
        update={
            "prediction_time_utc": prediction_time,
            "feature_snapshot": _window_feature_snapshot(
                fixture.feature_snapshot,
                as_of_time=as_of_time,
                source_slice_id=source_slice_id,
                output_slice_id=output_slice_id,
                normalize_prediction_time=normalize_prediction_time,
            ),
            "metadata_json": metadata,
        },
    )


def _window_feature_snapshot(
    feature_snapshot: FeatureSnapshot | None,
    *,
    as_of_time: datetime,
    source_slice_id: str,
    output_slice_id: str,
    normalize_prediction_time: bool,
) -> FeatureSnapshot | None:
    if feature_snapshot is None:
        return None
    original_feature_time = _aware_utc(feature_snapshot.feature_time_utc)
    feature_time = as_of_time if normalize_prediction_time else original_feature_time
    features_json = _window_features_json(
        feature_snapshot.features_json,
        as_of_time=as_of_time,
        source_slice_id=source_slice_id,
        output_slice_id=output_slice_id,
        original_feature_time=original_feature_time,
        normalize_prediction_time=normalize_prediction_time,
    )
    return feature_snapshot.model_copy(
        deep=True,
        update={
            "feature_time_utc": feature_time,
            "features_json": features_json,
            "source_snapshot_refs": {
                **feature_snapshot.source_snapshot_refs,
                "historical_windowing": {
                    "source_slice_id": source_slice_id,
                    "output_slice_id": output_slice_id,
                    "original_feature_time_utc": original_feature_time.isoformat(),
                    "window_as_of_time_utc": as_of_time.isoformat(),
                    "feature_time_policy": (
                        "window_as_of_time"
                        if normalize_prediction_time
                        else "source_fixture_time"
                    ),
                },
            },
        },
    )


def _window_features_json(
    features_json: dict[str, object],
    *,
    as_of_time: datetime,
    source_slice_id: str,
    output_slice_id: str,
    original_feature_time: datetime,
    normalize_prediction_time: bool,
) -> dict[str, object]:
    copied = dict(features_json)
    as_of_guard = copied.get("as_of_time_guard")
    if isinstance(as_of_guard, dict):
        copied["as_of_time_guard"] = {
            **as_of_guard,
            "feature_time_utc": as_of_time.isoformat(),
            "feature_time_normalized_by_windowing": normalize_prediction_time,
        }
    copied["historical_windowing"] = {
        "source_slice_id": source_slice_id,
        "output_slice_id": output_slice_id,
        "original_feature_time_utc": original_feature_time.isoformat(),
        "window_as_of_time_utc": as_of_time.isoformat(),
        "feature_time_policy": (
            "window_as_of_time" if normalize_prediction_time else "source_fixture_time"
        ),
    }
    return copied


def _source_slices_from_args(args: Namespace) -> list[HistoricalRecommendationSlice]:
    slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    if args.input_suite_manifest is not None:
        bundle = load_historical_recommendation_suite_manifest_bundle(
            args.input_suite_manifest
        )
        slices = [*bundle.slices, *slices]
    if not slices:
        raise ValueError("Provide --input-suite-manifest or one or more slice paths")
    return slices


def _summary(
    source_slices: Sequence[HistoricalRecommendationSlice],
    *,
    records: Sequence[HistoricalWindowedSliceRecord],
    skipped_window_count: int,
    output_dir: Path,
    suite_manifest_output_path: Path | None,
    options: HistoricalSliceWindowingOptions,
    warnings: Sequence[str],
) -> dict[str, object]:
    competition_counts = Counter(record.competition_id for record in records)
    season_counts = Counter(
        f"{record.competition_id}:{record.season or 'unknown'}"
        for record in records
    )
    fixture_counts = [record.fixture_count for record in records]
    return {
        "calculation_basis": "historical_slice_windowing_v3_1",
        "source_slice_count": len(source_slices),
        "generated_slice_count": len(records),
        "skipped_window_count": skipped_window_count,
        "generated_fixture_count": sum(fixture_counts),
        "min_window_fixture_count": min(fixture_counts) if fixture_counts else 0,
        "max_window_fixture_count": max(fixture_counts) if fixture_counts else 0,
        "output_dir": str(output_dir),
        "suite_manifest_output_path": (
            str(suite_manifest_output_path)
            if suite_manifest_output_path is not None
            else None
        ),
        "window_fixture_count": options.window_fixture_count,
        "stride_fixture_count": options.stride_fixture_count,
        "min_fixture_count": options.min_fixture_count,
        "as_of_offset_minutes": options.as_of_offset_minutes,
        "normalize_fixture_prediction_time": (
            options.normalize_fixture_prediction_time
        ),
        "slice_id_suffix": options.slice_id_suffix,
        "competition_slice_counts": dict(sorted(competition_counts.items())),
        "competition_season_slice_counts": dict(sorted(season_counts.items())),
        "warnings": list(warnings),
    }


def _report_key(summary: dict[str, object]) -> str:
    from hashlib import sha256

    digest = sha256(
        dumps(summary, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_slice_windowing:{digest}"


def _relative_path(path: Path, *, base_dir: Path) -> str:
    return Path(relpath(path, base_dir)).as_posix()


def _season_tag(season: str | None) -> str:
    return (season or "unknown_season").replace("-", "_").lower()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Split historical recommendation slices into rolling windows."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--input-suite-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite-manifest-output-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--suite-name", required=True)
    parser.add_argument("--suite-description")
    parser.add_argument("--window-fixture-count", type=int, default=12)
    parser.add_argument("--stride-fixture-count", type=int, default=12)
    parser.add_argument("--min-fixture-count", type=int, default=8)
    parser.add_argument("--as-of-offset-minutes", type=int, default=5)
    parser.add_argument(
        "--keep-source-fixture-prediction-time",
        action="store_true",
    )
    parser.add_argument("--slice-id-suffix", default="rolling_window_v1")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalSliceWindowingOptions:
    return HistoricalSliceWindowingOptions(
        window_fixture_count=args.window_fixture_count,
        stride_fixture_count=args.stride_fixture_count,
        min_fixture_count=args.min_fixture_count,
        as_of_offset_minutes=args.as_of_offset_minutes,
        normalize_fixture_prediction_time=not args.keep_source_fixture_prediction_time,
        slice_id_suffix=args.slice_id_suffix,
    )
