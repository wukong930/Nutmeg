from __future__ import annotations

from datetime import UTC, datetime
from json import loads
from pathlib import Path

from nutmeg.recommendations import build_enriched_historical_feature_sample
from nutmeg.recommendations.historical_backtest import load_historical_recommendation_slice
from nutmeg.recommendations.historical_feature_completeness import (
    HistoricalFeatureCompletenessResult,
)
from nutmeg.recommendations.historical_feature_sample_builder import (
    DEFAULT_ENRICHED_FEATURE_SLICE_ID,
    _options_from_args,
    _parse_args,
    main,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest_bundle,
)


def test_enriched_feature_sample_builder_returns_gate_passing_slice() -> None:
    result = build_enriched_historical_feature_sample()
    historical_slice = result.historical_slice

    assert historical_slice.metadata.slice_id == DEFAULT_ENRICHED_FEATURE_SLICE_ID
    assert len(historical_slice.fixtures) == 6
    assert all(fixture.feature_snapshot is not None for fixture in historical_slice.fixtures)
    assert result.completeness_result.passed is True
    assert result.completeness_result.summary_json["feature_snapshot_coverage"] == 1.0
    assert result.completeness_result.summary_json["odds_movement_coverage"] == 1.0
    assert result.summary_json["completeness_passed"] is True

    fragile_favorite = historical_slice.fixtures[1]
    assert fragile_favorite.actual_1x2_outcome == "draw"
    assert fragile_favorite.feature_snapshot is not None
    prematch_context = fragile_favorite.feature_snapshot.features_json["prematch_context"]
    assert prematch_context["odds_movement"][0]["movement_direction"] == (
        "probability_drifted"
    )
    assert prematch_context["risk_signals"]["lineup_schedule_risk"] > 0.30


def test_enriched_feature_sample_cli_writes_slice_report_and_manifest(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "enriched_feature_sample.json"
    completeness_path = tmp_path / "enriched_feature_completeness.json"
    manifest_path = tmp_path / "enriched_feature_suite.json"

    main(
        [
            "--output-path",
            str(output_path),
            "--completeness-output-path",
            str(completeness_path),
            "--suite-manifest-output-path",
            str(manifest_path),
        ]
    )

    historical_slice = load_historical_recommendation_slice(output_path)
    completeness = HistoricalFeatureCompletenessResult.model_validate_json(
        completeness_path.read_text(encoding="utf-8")
    )
    bundle = load_historical_recommendation_suite_manifest_bundle(manifest_path)

    assert historical_slice.metadata.slice_id == DEFAULT_ENRICHED_FEATURE_SLICE_ID
    assert completeness.passed is True
    assert bundle.manifest.suite_id == "nutmeg_enriched_prematch_feature_suite_v1"
    assert bundle.slices[0].metadata.slice_id == DEFAULT_ENRICHED_FEATURE_SLICE_ID
    assert loads(manifest_path.read_text(encoding="utf-8"))["slices"][0][
        "slice_path"
    ] == "enriched_feature_sample.json"


def test_enriched_feature_sample_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--output-path",
            "tmp/sample.json",
            "--slice-id",
            "custom_feature_slice",
            "--name",
            "Custom Feature Slice",
            "--competition-id",
            "CUSTOM_FEATURE",
            "--season",
            "2027",
            "--as-of-time-utc",
            "2026-05-09T12:00:00Z",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/sample.json")
    assert options.slice_id == "custom_feature_slice"
    assert options.name == "Custom Feature Slice"
    assert options.competition_id == "CUSTOM_FEATURE"
    assert options.season == "2027"
    assert options.as_of_time_utc == datetime(2026, 5, 9, 12, tzinfo=UTC)
