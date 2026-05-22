from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.predictions.job_repository import PredictionJobRunRecord
from nutmeg.predictions.jobs import run_audited_prediction_job, run_prediction_job
from nutmeg.predictions.pipeline import PreMatchPredictionPipelineResult


class FakePredictionDatabase:
    pass


class FakePredictionAuditRepository:
    def __init__(self) -> None:
        self.started: list[tuple[str, bool, str | None, dict[str, object] | None]] = []
        self.completed: list[
            tuple[
                int,
                int,
                int,
                dict[str, int],
                dict[str, int],
                dict[str, int],
                dict[str, float],
                list[str],
                list[str],
            ]
        ] = []
        self.failed: list[tuple[int, str]] = []

    def start_job(
        self,
        *,
        job_type: str,
        dry_run: bool,
        requested_by: str | None,
        metadata_json: dict[str, object] | None = None,
    ) -> PredictionJobRunRecord:
        self.started.append((job_type, dry_run, requested_by, metadata_json))
        return _job_run_record(status="running", completed_at=None)

    def complete_job(
        self,
        *,
        prediction_job_run_id: int,
        fixture_count: int,
        generated_count: int,
        feature_snapshot_ids: dict[str, int],
        prediction_snapshot_ids: dict[str, int],
        score_grid_ids: dict[str, int],
        data_quality_scores: dict[str, float],
        skipped_fixture_ids: list[str],
        warnings: list[str],
    ) -> PredictionJobRunRecord:
        self.completed.append(
            (
                prediction_job_run_id,
                fixture_count,
                generated_count,
                feature_snapshot_ids,
                prediction_snapshot_ids,
                score_grid_ids,
                data_quality_scores,
                skipped_fixture_ids,
                warnings,
            )
        )
        return _job_run_record(
            status="completed",
            completed_at=datetime(2026, 5, 8, 2, 5, tzinfo=UTC),
            duration_ms=44,
            fixture_count=fixture_count,
            generated_count=generated_count,
            feature_snapshot_ids=feature_snapshot_ids,
            prediction_snapshot_ids=prediction_snapshot_ids,
            score_grid_ids=score_grid_ids,
            data_quality_scores=data_quality_scores,
            skipped_fixture_ids=skipped_fixture_ids,
            warnings=warnings,
        )

    def fail_job(
        self,
        *,
        prediction_job_run_id: int,
        error_message: str,
    ) -> PredictionJobRunRecord:
        self.failed.append((prediction_job_run_id, error_message))
        return _job_run_record(
            status="failed",
            completed_at=datetime(2026, 5, 8, 2, 6, tzinfo=UTC),
            error_message=error_message,
        )


def test_run_prediction_job_dispatches_canonical_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakePredictionDatabase()
    calls: list[dict[str, object]] = []

    def fake_canonical_runner(**kwargs: object) -> PreMatchPredictionPipelineResult:
        calls.append(kwargs)
        return _pipeline_result()

    monkeypatch.setattr(
        "nutmeg.predictions.jobs.run_postgres_canonical_prematch_prediction_pipeline",
        fake_canonical_runner,
    )

    result = run_prediction_job(
        Settings(provider_governance_repository="postgres"),
        job_type="canonical_prematch_predictions",
        fixture_ids=["canonical_fix_001"],
        competition_id="EPL",
        dry_run=True,
        as_of_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        window_hours=48,
        max_snapshot_lag_hours=12,
        limit=25,
        database=database,
    )

    assert calls == [
        {
            "database": database,
            "fixture_ids": ["canonical_fix_001"],
            "competition_id": "EPL",
            "as_of_time_utc": datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            "window_hours": 48,
            "max_snapshot_lag_hours": 12,
            "limit": 25,
            "enforce_odds_quality_gate": True,
            "dry_run": True,
        }
    ]
    assert result.job_type == "canonical_prematch_predictions"
    assert result.fixture_count == 1
    assert result.generated_count == 1
    assert result.data_quality_scores == {"canonical_fix_001": 95.7}


def test_run_audited_prediction_job_records_canonical_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakePredictionDatabase()
    audit_repository = FakePredictionAuditRepository()

    def fake_canonical_runner(**kwargs: object) -> PreMatchPredictionPipelineResult:
        assert kwargs["database"] is database
        return _pipeline_result(dry_run=False)

    monkeypatch.setattr(
        "nutmeg.predictions.jobs.run_postgres_canonical_prematch_prediction_pipeline",
        fake_canonical_runner,
    )

    result = run_audited_prediction_job(
        Settings(provider_governance_repository="postgres"),
        job_type="canonical_prematch_predictions",
        fixture_ids=["canonical_fix_001"],
        competition_id="EPL",
        dry_run=False,
        window_hours=48,
        max_snapshot_lag_hours=12,
        limit=25,
        requested_by="admin_api",
        database=database,
        audit_repository=audit_repository,
    )

    assert audit_repository.started == [
        (
            "canonical_prematch_predictions",
            False,
            "admin_api",
            {
                "source": "api",
                "fixture_ids": ["canonical_fix_001"],
                "competition_id": "EPL",
                "window_hours": 48,
                "max_snapshot_lag_hours": 12,
                "limit": 25,
                "enforce_odds_quality_gate": True,
                "provider_governance_repository": "postgres",
            },
        )
    ]
    assert audit_repository.completed == [
        (
            19,
            1,
            1,
            {"canonical_fix_001": 501},
            {"canonical_fix_001": 801},
            {"canonical_fix_001": 701},
            {"canonical_fix_001": 95.7},
            [],
            [],
        )
    ]
    assert audit_repository.failed == []
    assert result.prediction_job_run_id == 19
    assert result.duration_ms == 44


def _pipeline_result(*, dry_run: bool = True) -> PreMatchPredictionPipelineResult:
    return PreMatchPredictionPipelineResult(
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        fixture_count=1,
        generated_count=1,
        dry_run=dry_run,
        feature_snapshot_ids={} if dry_run else {"canonical_fix_001": 501},
        prediction_snapshot_ids={} if dry_run else {"canonical_fix_001": 801},
        score_grid_ids={} if dry_run else {"canonical_fix_001": 701},
        data_quality_scores={"canonical_fix_001": 95.7},
    )


def _job_run_record(
    *,
    status: str,
    completed_at: datetime | None,
    duration_ms: int | None = None,
    fixture_count: int = 0,
    generated_count: int = 0,
    feature_snapshot_ids: dict[str, int] | None = None,
    prediction_snapshot_ids: dict[str, int] | None = None,
    score_grid_ids: dict[str, int] | None = None,
    data_quality_scores: dict[str, float] | None = None,
    skipped_fixture_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    error_message: str | None = None,
) -> PredictionJobRunRecord:
    return PredictionJobRunRecord(
        prediction_job_run_id=19,
        job_type="canonical_prematch_predictions",
        status=status,
        dry_run=True,
        requested_by="admin_api",
        started_at=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        completed_at=completed_at,
        duration_ms=duration_ms,
        fixture_count=fixture_count,
        generated_count=generated_count,
        feature_snapshot_ids=feature_snapshot_ids or {},
        prediction_snapshot_ids=prediction_snapshot_ids or {},
        score_grid_ids=score_grid_ids or {},
        data_quality_scores=data_quality_scores or {},
        skipped_fixture_ids=skipped_fixture_ids or [],
        warnings=warnings or [],
        error_message=error_message,
    )
