from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_slice_windowing import (
    HistoricalSliceWindowingOptions,
    build_windowed_historical_recommendation_slices,
    write_windowed_historical_recommendation_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    load_historical_recommendation_suite_manifest,
)


def test_windowing_builds_pre_kickoff_fixture_windows() -> None:
    source_slice = _source_slice(fixture_count=9)

    windows = build_windowed_historical_recommendation_slices(
        source_slice,
        options=HistoricalSliceWindowingOptions(
            window_fixture_count=4,
            stride_fixture_count=4,
            min_fixture_count=3,
            as_of_offset_minutes=10,
        ),
    )

    assert [len(window.fixtures) for window in windows] == [4, 4]
    assert windows[0].metadata.slice_id == "source_slice_rolling_window_v1_001"
    assert windows[1].metadata.slice_id == "source_slice_rolling_window_v1_002"
    assert windows[0].as_of_time_utc == datetime(2026, 1, 1, 11, 50, tzinfo=UTC)
    assert all(
        fixture.prediction_time_utc == windows[0].as_of_time_utc
        for fixture in windows[0].fixtures
    )
    assert all(
        fixture.kickoff_time_utc > windows[0].as_of_time_utc
        for fixture in windows[0].fixtures
    )
    assert (
        windows[0].fixtures[0].metadata_json["original_prediction_time_utc"]
        == "2026-01-01T11:55:00+00:00"
    )


def test_windowing_updates_feature_snapshot_as_of_guard() -> None:
    source_slice = _source_slice(fixture_count=4, include_feature_snapshot=True)

    window = build_windowed_historical_recommendation_slices(
        source_slice,
        options=HistoricalSliceWindowingOptions(
            window_fixture_count=4,
            stride_fixture_count=4,
            min_fixture_count=4,
            as_of_offset_minutes=15,
        ),
    )[0]

    snapshot = window.fixtures[0].feature_snapshot

    assert snapshot is not None
    assert snapshot.feature_time_utc == window.as_of_time_utc
    assert snapshot.features_json["as_of_time_guard"] == {
        "feature_time_utc": "2026-01-01T11:45:00+00:00",
        "feature_before_kickoff": True,
        "feature_time_normalized_by_windowing": True,
    }
    assert snapshot.features_json["historical_windowing"] == {
        "source_slice_id": "source_slice",
        "output_slice_id": "source_slice_rolling_window_v1_001",
        "original_feature_time_utc": "2026-01-01T11:55:00+00:00",
        "window_as_of_time_utc": "2026-01-01T11:45:00+00:00",
        "feature_time_policy": "window_as_of_time",
    }


def test_write_windowed_suite_outputs_slices_manifest_and_report(tmp_path) -> None:
    source_slice = _source_slice(fixture_count=9)
    output_dir = tmp_path / "slices"
    manifest_path = tmp_path / "suites" / "window_suite.json"

    report = write_windowed_historical_recommendation_suite(
        [source_slice],
        output_dir=output_dir,
        suite_manifest_output_path=manifest_path,
        suite_id="test_window_suite",
        suite_name="Test window suite",
        suite_description="Synthetic test window suite",
        options=HistoricalSliceWindowingOptions(
            window_fixture_count=4,
            stride_fixture_count=4,
            min_fixture_count=3,
        ),
    )

    manifest = load_historical_recommendation_suite_manifest(manifest_path)
    first_slice = load_historical_recommendation_slice(
        manifest_path.parent / manifest.slices[0].slice_path
    )

    assert report.generated_slice_count == 2
    assert report.skipped_window_count == 1
    assert report.summary_json["competition_slice_counts"] == {"TEST_COMP": 2}
    assert manifest.suite_id == "test_window_suite"
    assert len(manifest.slices) == 2
    assert first_slice.metadata.slice_id == report.records[0].output_slice_id
    assert first_slice.fixtures[0].prediction_time_utc == first_slice.as_of_time_utc


def _source_slice(
    *,
    fixture_count: int,
    include_feature_snapshot: bool = False,
) -> HistoricalRecommendationSlice:
    kickoff_start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="source_slice",
            name="Source slice",
            competition_id="TEST_COMP",
            season="2025-2026",
            result_source="test_results",
            odds_source="test_odds",
            prediction_source="test_predictions",
            notes=["source note"],
        ),
        as_of_time_utc=kickoff_start - timedelta(minutes=5),
        fixtures=[
            _fixture(
                index=index,
                kickoff_time=kickoff_start + timedelta(hours=index),
                include_feature_snapshot=include_feature_snapshot,
            )
            for index in range(fixture_count)
        ],
    )


def _fixture(
    *,
    index: int,
    kickoff_time: datetime,
    include_feature_snapshot: bool,
) -> HistoricalFixture:
    prediction_time = kickoff_time - timedelta(minutes=5)
    fixture_id = f"fixture_{index}"
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST_COMP",
        kickoff_time_utc=kickoff_time,
        home_team_name=f"Home {index}",
        away_team_name=f"Away {index}",
        actual_home_goals=2,
        actual_away_goals=1,
        prediction_time_utc=prediction_time,
        model_version="test-model",
        feature_version="test-feature",
        calibration_version="test-calibration",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.60,
                decimal_odds=1.90,
                market_probability=1 / 1.90,
                data_quality_score=90.0,
            )
        ],
        feature_snapshot=(
            FeatureSnapshot(
                fixture_id=fixture_id,
                feature_time_utc=prediction_time,
                feature_version="test-feature",
                features_json={
                    "as_of_time_guard": {
                        "feature_time_utc": prediction_time.isoformat(),
                        "feature_before_kickoff": True,
                    }
                },
                source_snapshot_refs={"source": "test"},
                data_quality_score=90.0,
            )
            if include_feature_snapshot
            else None
        ),
    )
