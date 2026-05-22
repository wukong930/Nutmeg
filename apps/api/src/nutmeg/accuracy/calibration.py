from __future__ import annotations

from math import floor
from pathlib import Path

from nutmeg.domain.accuracy import CalibrationBucket, CalibrationBucketKey


def calibration_bucket_key_for_probability(
    *,
    predicted_probability: float,
    model_version: str,
    market_type: str,
    outcome: str,
    bucket_size: float = 0.10,
    competition_id: str | None = None,
) -> CalibrationBucketKey:
    if not 0.0 <= predicted_probability <= 1.0:
        raise ValueError("predicted_probability must be between 0 and 1")
    if not 0.0 < bucket_size <= 1.0:
        raise ValueError("bucket_size must be in (0, 1]")
    if predicted_probability == 1.0:
        bucket_start = max(0.0, 1.0 - bucket_size)
    else:
        bucket_start = floor(predicted_probability / bucket_size) * bucket_size
    bucket_end = min(1.0, bucket_start + bucket_size)
    return CalibrationBucketKey(
        model_version=model_version,
        market_type=market_type,
        outcome=outcome,
        bucket_start=round(bucket_start, 10),
        bucket_end=round(bucket_end, 10),
        competition_id=competition_id,
    )


class FileCalibrationBucketStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def update(
        self,
        *,
        predicted_probability: float,
        actual_occurred: bool,
        model_version: str,
        market_type: str,
        outcome: str,
        bucket_size: float = 0.10,
        competition_id: str | None = None,
    ) -> CalibrationBucket:
        key = calibration_bucket_key_for_probability(
            predicted_probability=predicted_probability,
            model_version=model_version,
            market_type=market_type,
            outcome=outcome,
            bucket_size=bucket_size,
            competition_id=competition_id,
        )
        bucket = self.get(key) or CalibrationBucket(key=key)
        updated = bucket.model_copy(
            update={
                "sample_size": bucket.sample_size + 1,
                "predicted_probability_sum": (
                    bucket.predicted_probability_sum + predicted_probability
                ),
                "actual_count": bucket.actual_count + (1 if actual_occurred else 0),
            }
        )
        self._write(updated)
        return updated

    def get(self, key: CalibrationBucketKey) -> CalibrationBucket | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        return CalibrationBucket.model_validate_json(path.read_text(encoding="utf-8"))

    def list_buckets(self) -> list[CalibrationBucket]:
        buckets = [
            CalibrationBucket.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.root_dir.glob("*.json"))
        ]
        return sorted(buckets, key=lambda bucket: bucket.key.stable_id)

    def _write(self, bucket: CalibrationBucket) -> None:
        self._path_for(bucket.key).write_text(bucket.model_dump_json(indent=2), encoding="utf-8")

    def _path_for(self, key: CalibrationBucketKey) -> Path:
        safe_name = key.stable_id.replace("|", "__")
        return self.root_dir / f"{safe_name}.json"
