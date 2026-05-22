from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.accuracy.mock_repository import ACTIVE_MODEL_VERSION, MockAccuracyEventRepository
from nutmeg.accuracy.summary import build_accuracy_summary
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.predictions import build_mock_prediction_snapshot
from nutmeg.providers.mock import list_mock_fixtures


def test_accuracy_summary_aggregates_mock_evaluation_events() -> None:
    repository = MockAccuracyEventRepository(_mock_snapshots())
    events = repository.list_evaluation_events()

    summary = build_accuracy_summary(
        events,
        model_version="active",
        competition_id="all",
        market="all",
        window="90d",
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
        active_model_version=ACTIVE_MODEL_VERSION,
        model_comparisons=repository.list_model_comparisons(events),
    )

    assert summary.sample_size == 9
    assert summary.log_loss is not None
    assert summary.brier_score is not None
    assert summary.ece is not None
    assert set(summary.by_market) == {"1x2", "asian_handicap", "cn_handicap_1x2"}
    assert summary.by_market["1x2"].sample_size == 3
    assert [row.competition_id for row in summary.by_competition] == ["EPL", "JPN_J1"]
    assert sum(bucket.sample_size for bucket in summary.calibration_buckets) == 33
    assert summary.error_types
    assert summary.model_comparisons[0].decision == "needs_review"


def test_accuracy_summary_honors_competition_and_market_filters() -> None:
    repository = MockAccuracyEventRepository(_mock_snapshots())
    events = repository.list_evaluation_events()

    summary = build_accuracy_summary(
        events,
        model_version="active",
        competition_id="EPL",
        market="1x2",
        window="90d",
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
        active_model_version=ACTIVE_MODEL_VERSION,
        model_comparisons=[],
    )

    assert summary.sample_size == 2
    assert list(summary.by_market) == ["1x2"]
    assert len(summary.by_competition) == 1
    assert summary.by_competition[0].competition_id == "EPL"
    assert summary.by_competition[0].sample_size == 2
    assert summary.filters.competition_id == "EPL"
    assert summary.filters.market == "1x2"


def test_accuracy_summary_returns_empty_metrics_for_out_of_window_filter() -> None:
    repository = MockAccuracyEventRepository(_mock_snapshots())

    summary = build_accuracy_summary(
        repository.list_evaluation_events(),
        model_version="active",
        competition_id="all",
        market="all",
        window="30d",
        generated_at_utc=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        active_model_version=ACTIVE_MODEL_VERSION,
        model_comparisons=[],
    )

    assert summary.sample_size == 0
    assert summary.log_loss is None
    assert summary.brier_score is None
    assert summary.ece is None
    assert summary.by_market == {}
    assert summary.calibration_buckets == []


def test_accuracy_summary_rejects_unknown_model_version_without_active_mapping() -> None:
    repository = MockAccuracyEventRepository(_mock_snapshots())

    summary = build_accuracy_summary(
        repository.list_evaluation_events(),
        model_version="dc-v1.5-candidate",
        competition_id="all",
        market="all",
        window="90d",
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
        active_model_version=ACTIVE_MODEL_VERSION,
        model_comparisons=[],
    )

    assert summary.sample_size == 0


def _mock_snapshots() -> dict[str, PredictionSnapshot]:
    snapshots: dict[str, PredictionSnapshot] = {}
    for fixture in list_mock_fixtures():
        snapshot = build_mock_prediction_snapshot(fixture["fixture_id"])
        assert snapshot is not None
        snapshots[fixture["fixture_id"]] = snapshot
    return snapshots
