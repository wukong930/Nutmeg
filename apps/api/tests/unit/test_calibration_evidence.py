from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from nutmeg.accuracy import (
    PostgresCalibrationEvidenceRepository,
    build_calibration_evidence_report,
)
from nutmeg.accuracy.calibration_evidence import CALIBRATION_BUCKET_EVIDENCE_QUERY
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.accuracy import CalibrationBucket, CalibrationBucketKey


class FakeCalibrationEvidenceDatabase:
    def __init__(self, rows_by_query: Mapping[str, Sequence[DatabaseRow]]) -> None:
        self.rows_by_query = rows_by_query
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows_by_query.get(query, [])


def test_build_calibration_evidence_report_computes_bucket_weighted_ece() -> None:
    report = build_calibration_evidence_report(
        [
            _bucket("baseline", "1x2", "home_win", 0.3, 0.4, 10, 3.5, 3),
            _bucket("baseline", "1x2", "draw", 0.2, 0.3, 6, 1.5, 2),
            _bucket("other", "1x2", "home_win", 0.3, 0.4, 10, 3.5, 3),
        ],
        model_version="baseline",
        market_type="1x2",
        competition_id="EPL",
    )

    assert report is not None
    expected_ece = (10 / 16) * abs(0.35 - 0.30) + (6 / 16) * abs(0.25 - (2 / 6))
    assert report.expected_calibration_error == pytest.approx(expected_ece)
    assert report.observation_count == 16
    assert report.bucket_count == 2
    assert report.metrics_json["ece_source"] == "stored_calibration_buckets"


def test_postgres_calibration_evidence_repository_reads_filtered_buckets() -> None:
    database = FakeCalibrationEvidenceDatabase(
        {
            CALIBRATION_BUCKET_EVIDENCE_QUERY: [
                {
                    "model_version": "poisson-m1.1.0",
                    "market_type": "1x2",
                    "outcome": "home_win",
                    "competition_id": "EPL",
                    "bucket_start": Decimal("0.40"),
                    "bucket_end": Decimal("0.50"),
                    "sample_size": 10,
                    "predicted_probability_sum": Decimal("4.0"),
                    "actual_count": 5,
                }
            ]
        }
    )

    report = PostgresCalibrationEvidenceRepository(database).get_model_ece(
        model_version="poisson-m1.1.0",
        market_type="1x2",
        competition_id="EPL",
    )

    assert database.calls == [
        (
            CALIBRATION_BUCKET_EVIDENCE_QUERY,
            {
                "model_version": "poisson-m1.1.0",
                "market_type": "1x2",
                "competition_id": "EPL",
            },
        )
    ]
    assert report is not None
    assert report.expected_calibration_error == pytest.approx(0.10)
    assert report.metrics_json["ece_competition_id"] == "EPL"


def test_build_calibration_evidence_report_returns_none_without_matching_samples() -> None:
    assert (
        build_calibration_evidence_report(
            [_bucket("baseline", "1x2", "home_win", 0.3, 0.4, 0, 0.0, 0)],
            model_version="baseline",
            market_type="1x2",
        )
        is None
    )


def _bucket(
    model_version: str,
    market_type: str,
    outcome: str,
    bucket_start: float,
    bucket_end: float,
    sample_size: int,
    predicted_probability_sum: float,
    actual_count: int,
) -> CalibrationBucket:
    return CalibrationBucket(
        key=CalibrationBucketKey(
            model_version=model_version,
            market_type=market_type,
            outcome=outcome,
            competition_id="EPL",
            bucket_start=bucket_start,
            bucket_end=bucket_end,
        ),
        sample_size=sample_size,
        predicted_probability_sum=predicted_probability_sum,
        actual_count=actual_count,
    )
