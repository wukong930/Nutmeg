from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.accuracy import CalibrationBucket, CalibrationBucketKey

CALIBRATION_BUCKET_EVIDENCE_QUERY = """
SELECT
  model_version,
  market_type,
  outcome,
  competition_id,
  bucket_start,
  bucket_end,
  sample_size,
  predicted_probability_sum,
  actual_count
FROM calibration_buckets
WHERE model_version = %(model_version)s
  AND market_type = %(market_type)s
  AND (%(competition_id)s::text IS NULL OR competition_id = %(competition_id)s::text)
ORDER BY outcome, competition_id, bucket_start, bucket_end
"""


class CalibrationEvidenceDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read aggregate calibration buckets."""


class CalibrationEvidenceReport(BaseModel):
    model_version: str
    market_type: str
    competition_id: str | None = None
    bucket_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    expected_calibration_error: float = Field(ge=0.0)
    buckets: list[CalibrationBucket]

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "ece": self.expected_calibration_error,
            "ece_source": "stored_calibration_buckets",
            "ece_market_type": self.market_type,
            "ece_competition_id": self.competition_id,
            "ece_observation_count": self.observation_count,
            "ece_bucket_count": self.bucket_count,
        }


class PostgresCalibrationEvidenceRepository:
    def __init__(self, database: CalibrationEvidenceDatabaseExecutor) -> None:
        self.database = database

    def get_model_ece(
        self,
        *,
        model_version: str,
        market_type: str,
        competition_id: str | None = None,
    ) -> CalibrationEvidenceReport | None:
        rows = self.database.fetch_all(
            CALIBRATION_BUCKET_EVIDENCE_QUERY,
            {
                "model_version": model_version,
                "market_type": market_type,
                "competition_id": competition_id,
            },
        )
        buckets = [_calibration_bucket_from_row(row) for row in rows]
        return build_calibration_evidence_report(
            buckets,
            model_version=model_version,
            market_type=market_type,
            competition_id=competition_id,
        )


def build_calibration_evidence_report(
    buckets: Sequence[CalibrationBucket],
    *,
    model_version: str,
    market_type: str,
    competition_id: str | None = None,
) -> CalibrationEvidenceReport | None:
    matching_buckets = [
        bucket
        for bucket in buckets
        if bucket.key.model_version == model_version
        and bucket.key.market_type == market_type
        and (competition_id is None or bucket.key.competition_id == competition_id)
        and bucket.sample_size > 0
    ]
    observation_count = sum(bucket.sample_size for bucket in matching_buckets)
    if observation_count == 0:
        return None
    expected_calibration_error = sum(
        (bucket.sample_size / observation_count)
        * abs(bucket.average_predicted_probability - bucket.actual_frequency)
        for bucket in matching_buckets
    )
    return CalibrationEvidenceReport(
        model_version=model_version,
        market_type=market_type,
        competition_id=competition_id,
        bucket_count=len(matching_buckets),
        observation_count=observation_count,
        expected_calibration_error=expected_calibration_error,
        buckets=sorted(matching_buckets, key=lambda bucket: bucket.key.stable_id),
    )


def _calibration_bucket_from_row(row: Mapping[str, object]) -> CalibrationBucket:
    return CalibrationBucket(
        key=CalibrationBucketKey(
            model_version=_str(row["model_version"]),
            market_type=_str(row["market_type"]),
            outcome=_str(row["outcome"]),
            competition_id=_optional_str(row["competition_id"]),
            bucket_start=_float(row["bucket_start"]),
            bucket_end=_float(row["bucket_end"]),
        ),
        sample_size=_int(row["sample_size"]),
        predicted_probability_sum=_float(row["predicted_probability_sum"]),
        actual_count=_int(row["actual_count"]),
    )


def _str(value: object) -> str:
    if value is None:
        raise ValueError("expected non-null string value")
    return str(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")
