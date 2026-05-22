from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nutmeg.accuracy.postgres_repository import (
    CALIBRATION_BUCKETS_QUERY,
    EVALUATION_EVENTS_QUERY,
    MODEL_COMPARISONS_QUERY,
    DatabaseRow,
    PostgresAccuracyRepository,
    QueryParams,
)
from nutmeg.accuracy.repository import AccuracySummaryService


class FakeDatabase:
    def __init__(self, rows_by_query: Mapping[str, Sequence[DatabaseRow]]) -> None:
        self.rows_by_query = rows_by_query
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows_by_query.get(query, [])


def test_postgres_repository_maps_prediction_evaluations_to_accuracy_events() -> None:
    database = FakeDatabase({EVALUATION_EVENTS_QUERY: [_evaluation_row()]})
    repository = PostgresAccuracyRepository(database)

    events = repository.list_evaluation_events()

    assert len(events) == 1
    event = events[0]
    assert event.fixture_id == "fix_epl_001"
    assert event.competition_id == "EPL"
    assert event.competition_name == "Premier League"
    assert event.market_type == "1x2"
    assert event.model_version == "poisson-m1.0.0"
    assert event.prediction_time_utc == datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    assert event.log_loss == 0.92
    assert event.brier_score == 0.21
    assert event.error_tags == ("draw_underestimated",)
    assert [observation.outcome for observation in event.calibration_observations] == [
        "home_win",
        "draw",
        "away_win",
    ]
    assert event.calibration_observations[1].actual_occurred is True


def test_postgres_repository_maps_stored_calibration_buckets() -> None:
    database = FakeDatabase({CALIBRATION_BUCKETS_QUERY: [_calibration_bucket_row()]})
    repository = PostgresAccuracyRepository(database)

    buckets = repository.list_calibration_buckets()

    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.key.model_version == "poisson-m1.0.0"
    assert bucket.key.market_type == "1x2"
    assert bucket.key.competition_id == "EPL"
    assert bucket.sample_size == 12
    assert bucket.average_predicted_probability == pytest.approx(0.35)
    assert bucket.actual_frequency == 0.25


def test_postgres_repository_maps_model_comparison_reports() -> None:
    database = FakeDatabase({MODEL_COMPARISONS_QUERY: [_model_comparison_row()]})
    repository = PostgresAccuracyRepository(database)

    comparisons = repository.list_model_comparisons([])

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison.baseline_model_version == "poisson-m1.0.0"
    assert comparison.candidate_model_version == "dc-v1.5-candidate"
    assert comparison.baseline_metrics.log_loss == 1.02
    assert comparison.candidate_metrics.brier_score == 0.2
    assert comparison.decision_stub == "needs_review"
    assert comparison.reasons == ["candidate_sample_size_low"]


def test_accuracy_summary_service_can_use_postgres_repository_contract() -> None:
    database = FakeDatabase(
        {
            EVALUATION_EVENTS_QUERY: [_evaluation_row()],
            MODEL_COMPARISONS_QUERY: [_model_comparison_row()],
        }
    )
    repository = PostgresAccuracyRepository(database)

    summary = AccuracySummaryService(
        repository,
        active_model_version="poisson-m1.0.0",
    ).build_summary(
        model_version="active",
        competition_id="EPL",
        market="1x2",
        window="90d",
        generated_at_utc=datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
    )

    assert summary.sample_size == 1
    assert summary.by_market["1x2"].sample_size == 1
    assert summary.by_competition[0].competition_id == "EPL"
    assert summary.calibration_buckets
    assert summary.model_comparisons[0].candidate_model_version == "dc-v1.5-candidate"


def _evaluation_row() -> DatabaseRow:
    return {
        "fixture_id": "fix_epl_001",
        "competition_id": "EPL",
        "competition_name": "Premier League",
        "model_version": "poisson-m1.0.0",
        "prediction_time_utc": "2026-05-06T12:00:00+00:00",
        "log_loss_1x2": Decimal("0.92"),
        "brier_score_1x2": Decimal("0.21"),
        "actual_result_1x2": "draw",
        "p_home": Decimal("0.43"),
        "p_draw": Decimal("0.28"),
        "p_away": Decimal("0.29"),
        "error_tags_json": '["draw_underestimated"]',
    }


def _calibration_bucket_row() -> DatabaseRow:
    return {
        "model_version": "poisson-m1.0.0",
        "market_type": "1x2",
        "outcome": "home_win",
        "competition_id": "EPL",
        "bucket_start": Decimal("0.30"),
        "bucket_end": Decimal("0.40"),
        "sample_size": 12,
        "predicted_probability_sum": Decimal("4.20"),
        "actual_count": 3,
    }


def _model_comparison_row() -> DatabaseRow:
    return {
        "candidate_model_version": "dc-v1.5-candidate",
        "baseline_model_version": "poisson-m1.0.0",
        "candidate_metrics_json": {
            "sample_size": 18,
            "log_loss": 1.0,
            "brier_score": 0.2,
            "ece": 0.04,
        },
        "baseline_metrics_json": {
            "sample_size": 18,
            "log_loss": 1.02,
            "brier_score": 0.22,
            "ece": 0.05,
        },
        "decision_stub": "needs_review",
        "reasons_json": ["candidate_sample_size_low"],
    }
