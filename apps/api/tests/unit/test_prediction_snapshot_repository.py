from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.domain.modeling import GoalLambdaEstimate
from nutmeg.predictions import (
    FilePredictionSnapshotRepository,
    build_prediction_snapshot_from_lambda_estimate,
)


def _estimate(lambda_home: float, lambda_away: float) -> GoalLambdaEstimate:
    return GoalLambdaEstimate(
        fixture_id="repo_fixture",
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        model_family="poisson",
        model_version="poisson-m1.0.0",
        feature_version="features-m1.0.0",
        calibration_version="calibration-m1.0.0",
    )


def test_file_prediction_snapshot_repository_persists_and_loads_snapshot(tmp_path: Path) -> None:
    repository = FilePredictionSnapshotRepository(tmp_path)
    snapshot = build_prediction_snapshot_from_lambda_estimate(
        _estimate(1.40, 1.05),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    stored = repository.save(snapshot)
    loaded = repository.get(stored.snapshot_id)

    assert loaded is not None
    assert loaded.fixture_id == snapshot.fixture_id
    assert loaded.prediction_time_utc == snapshot.prediction_time_utc
    assert loaded.score_grid.grid == snapshot.score_grid.grid
    assert loaded.market_probabilities == snapshot.market_probabilities


def test_file_prediction_snapshot_repository_returns_latest_for_fixture(tmp_path: Path) -> None:
    repository = FilePredictionSnapshotRepository(tmp_path)
    earlier = build_prediction_snapshot_from_lambda_estimate(
        _estimate(1.20, 1.00),
        prediction_time_utc=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
    )
    later = build_prediction_snapshot_from_lambda_estimate(
        _estimate(1.60, 1.10),
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
    )

    repository.save(later)
    repository.save(earlier)

    snapshots = repository.list_for_fixture("repo_fixture")
    latest = repository.latest_for_fixture("repo_fixture")

    assert [snapshot.prediction_time_utc for snapshot in snapshots] == [
        earlier.prediction_time_utc,
        later.prediction_time_utc,
    ]
    assert latest is not None
    assert latest.prediction_time_utc == later.prediction_time_utc
