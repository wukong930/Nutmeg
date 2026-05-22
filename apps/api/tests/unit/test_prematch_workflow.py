from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.config import Settings
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.parlay import MarketPredictionParlayGenerationResult
from nutmeg.predictions.jobs import PredictionJobResult
from nutmeg.predictions.workflow import (
    COMPLETE_PREMATCH_WORKFLOW_RUN_QUERY,
    FAIL_PREMATCH_WORKFLOW_RUN_QUERY,
    INSERT_PREMATCH_WORKFLOW_RUN_QUERY,
    LIST_PREMATCH_WORKFLOW_RUNS_QUERY,
    PostgresPrematchWorkflowRunRepository,
    PrematchWorkflowOptions,
    run_audited_prematch_workflow,
)


class FakePrematchWorkflowDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_PREMATCH_WORKFLOW_RUN_QUERY:
            return _workflow_row(status="running", completed_at=None)
        if query == COMPLETE_PREMATCH_WORKFLOW_RUN_QUERY:
            return _workflow_row(
                status="completed",
                completed_at=datetime(2026, 5, 8, 2, 5, tzinfo=UTC),
                prediction_job_run_id=params["prediction_job_run_id"],
                prediction_job_type=params["prediction_job_type"],
                prediction_fixture_count=params["prediction_fixture_count"],
                prediction_generated_count=params["prediction_generated_count"],
                parlay_generated_count=params["parlay_generated_count"],
                parlay_recommendation_ids_json=params[
                    "parlay_recommendation_ids_json"
                ],
                warnings_json=params["warnings_json"],
                duration_ms=51,
            )
        if query == FAIL_PREMATCH_WORKFLOW_RUN_QUERY:
            return _workflow_row(
                status="failed",
                completed_at=datetime(2026, 5, 8, 2, 6, tzinfo=UTC),
                error_message=params["error_message"],
                warnings_json=params["warnings_json"],
                duration_ms=19,
            )
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PREMATCH_WORKFLOW_RUNS_QUERY:
            return [_workflow_row(status="completed")]
        raise AssertionError(f"unexpected query: {query}")


class FakePredictionAuditRepository:
    pass


def test_prematch_workflow_runs_prediction_then_parlay_and_records_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakePrematchWorkflowDatabase()
    prediction_calls: list[dict[str, object]] = []
    parlay_calls: list[dict[str, object]] = []

    def fake_prediction_job(_settings: Settings, **kwargs: object) -> PredictionJobResult:
        prediction_calls.append(kwargs)
        return _prediction_job_result(warnings=["prediction_low_quality:fix_b"])

    def fake_parlay_generation(
        *args: object,
        **kwargs: object,
    ) -> MarketPredictionParlayGenerationResult:
        parlay_calls.append({"args": args, "kwargs": kwargs})
        options = kwargs["options"]
        assert options.fixture_ids == ("fix_a", "fix_b")
        assert options.pass_type == "2x1"
        return MarketPredictionParlayGenerationResult(
            dry_run=True,
            as_of_time_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
            candidate_count=2,
            generated_count=1,
            warnings=["parlay_warning"],
        )

    monkeypatch.setattr(
        "nutmeg.predictions.workflow.run_audited_prediction_job",
        fake_prediction_job,
    )
    monkeypatch.setattr(
        "nutmeg.predictions.workflow.run_market_prediction_parlay_generation",
        fake_parlay_generation,
    )

    result = run_audited_prematch_workflow(
        Settings(parlay_repository="postgres"),
        options=PrematchWorkflowOptions(
            prediction_job_type="canonical_prematch_predictions",
            competition_id="EPL",
            dry_run=True,
        ),
        requested_by="admin_api",
        database=database,
        audit_repository=PostgresPrematchWorkflowRunRepository(database),
        prediction_audit_repository=FakePredictionAuditRepository(),  # type: ignore[arg-type]
    )

    assert result.prematch_workflow_run_id == 99
    assert result.prediction.prediction_job_run_id == 19
    assert result.parlay is not None
    assert result.parlay.generated_count == 1
    assert result.warnings == ["prediction_low_quality:fix_b", "parlay_warning"]
    assert prediction_calls[0]["competition_id"] == "EPL"
    assert prediction_calls[0]["enforce_odds_quality_gate"] is True
    assert prediction_calls[0]["requested_by"] == "admin_api"
    assert len(parlay_calls) == 1
    complete_call = database.fetch_one_calls[-1]
    assert complete_call[0] == COMPLETE_PREMATCH_WORKFLOW_RUN_QUERY
    assert complete_call[1]["prediction_job_run_id"] == 19
    assert complete_call[1]["parlay_generated_count"] == 1


def test_prematch_workflow_skips_parlay_when_prediction_has_no_fixtures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakePrematchWorkflowDatabase()

    def fake_prediction_job(_settings: Settings, **_kwargs: object) -> PredictionJobResult:
        return _prediction_job_result(data_quality_scores={})

    monkeypatch.setattr(
        "nutmeg.predictions.workflow.run_audited_prediction_job",
        fake_prediction_job,
    )

    result = run_audited_prematch_workflow(
        Settings(parlay_repository="postgres"),
        options=PrematchWorkflowOptions(dry_run=True),
        database=database,
        audit_repository=PostgresPrematchWorkflowRunRepository(database),
        prediction_audit_repository=FakePredictionAuditRepository(),  # type: ignore[arg-type]
    )

    assert result.parlay is None
    assert result.warnings == ["parlay_generation_skipped:no_prediction_fixtures"]


def test_prematch_workflow_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = FakePrematchWorkflowDatabase()

    def fake_prediction_job(_settings: Settings, **_kwargs: object) -> PredictionJobResult:
        raise ValueError("prediction source unavailable")

    monkeypatch.setattr(
        "nutmeg.predictions.workflow.run_audited_prediction_job",
        fake_prediction_job,
    )

    with pytest.raises(ValueError, match="prediction source unavailable"):
        run_audited_prematch_workflow(
            Settings(),
            options=PrematchWorkflowOptions(dry_run=True),
            database=database,
            audit_repository=PostgresPrematchWorkflowRunRepository(database),
            prediction_audit_repository=FakePredictionAuditRepository(),  # type: ignore[arg-type]
        )

    assert database.fetch_one_calls[-1][0] == FAIL_PREMATCH_WORKFLOW_RUN_QUERY
    assert database.fetch_one_calls[-1][1]["error_message"] == "prediction source unavailable"


def test_prematch_workflow_repository_lists_latest_records() -> None:
    database = FakePrematchWorkflowDatabase()
    records = PostgresPrematchWorkflowRunRepository(database).list_latest(limit=5)

    assert len(records) == 1
    assert records[0].prematch_workflow_run_id == 99
    assert records[0].prediction_job_run_id == 19
    assert records[0].parlay_recommendation_ids == [77]
    assert database.fetch_all_calls == [
        (LIST_PREMATCH_WORKFLOW_RUNS_QUERY, {"limit": 5})
    ]


def _prediction_job_result(
    *,
    warnings: list[str] | None = None,
    data_quality_scores: dict[str, float] | None = None,
) -> PredictionJobResult:
    quality_scores = data_quality_scores
    if quality_scores is None:
        quality_scores = {"fix_a": 82.0, "fix_b": 79.0}
    return PredictionJobResult(
        prediction_job_run_id=19,
        job_type="canonical_prematch_predictions",
        dry_run=True,
        requested_by="admin_api",
        prediction_time_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        fixture_count=len(quality_scores),
        generated_count=len(quality_scores),
        data_quality_scores=quality_scores,
        warnings=warnings or [],
    )


def _workflow_row(
    *,
    status: str,
    completed_at: datetime | None = datetime(2026, 5, 8, 2, 5, tzinfo=UTC),
    duration_ms: int | None = 44,
    prediction_job_run_id: object | None = 19,
    prediction_job_type: object | None = "canonical_prematch_predictions",
    prediction_fixture_count: object = 2,
    prediction_generated_count: object = 2,
    parlay_generated_count: object = 1,
    parlay_recommendation_ids_json: object = "[77]",
    warnings_json: object = '["parlay_warning"]',
    error_message: object | None = None,
) -> DatabaseRow:
    return {
        "prematch_workflow_run_id": 99,
        "status": status,
        "dry_run": True,
        "requested_by": "admin_api",
        "started_at": datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "prediction_job_run_id": prediction_job_run_id,
        "prediction_job_type": prediction_job_type,
        "prediction_fixture_count": prediction_fixture_count,
        "prediction_generated_count": prediction_generated_count,
        "parlay_generated_count": parlay_generated_count,
        "parlay_recommendation_ids_json": parlay_recommendation_ids_json,
        "warnings_json": warnings_json,
        "error_message": error_message,
        "metadata_json": '{"source":"admin_api"}',
    }
