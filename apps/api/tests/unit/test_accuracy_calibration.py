from __future__ import annotations

from math import isclose
from pathlib import Path

from nutmeg.accuracy import FileCalibrationBucketStore, calibration_bucket_key_for_probability


def test_calibration_bucket_key_handles_closed_upper_bound() -> None:
    key = calibration_bucket_key_for_probability(
        predicted_probability=1.0,
        model_version="model-a",
        market_type="1x2",
        outcome="home_win",
    )

    assert key.bucket_start == 0.90
    assert key.bucket_end == 1.0


def test_file_calibration_bucket_store_updates_and_persists_bucket(tmp_path: Path) -> None:
    store = FileCalibrationBucketStore(tmp_path)
    first = store.update(
        predicted_probability=0.64,
        actual_occurred=True,
        model_version="model-a",
        market_type="1x2",
        outcome="home_win",
    )
    second = store.update(
        predicted_probability=0.66,
        actual_occurred=False,
        model_version="model-a",
        market_type="1x2",
        outcome="home_win",
    )

    loaded = store.get(first.key)
    buckets = store.list_buckets()

    assert second.sample_size == 2
    assert second.actual_count == 1
    assert isclose(second.average_predicted_probability, 0.65)
    assert second.actual_frequency == 0.5
    assert loaded == second
    assert buckets == [second]
