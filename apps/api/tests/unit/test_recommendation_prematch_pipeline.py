from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PersistedRecommendationLifecycleReplayResult,
    RecommendationPrematchChangeReport,
    RecommendationPrematchChangeReportRunResult,
    RecommendationPrematchPipelineOptions,
    RecommendationPrematchPipelineRunRecord,
    RecommendationPrematchPipelineRunResult,
    RecommendationProviderIncidentMappingResult,
    RecommendationRecomputeTriggerRunResult,
    run_recommendation_prematch_pipeline,
)
from nutmeg.recommendations.prematch_pipeline import (
    COMPLETE_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
    FAIL_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
    INSERT_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
    PostgresRecommendationPrematchPipelineRunRepository,
)
from nutmeg.recommendations.prematch_report import (
    RecommendationPrematchChangeReportOptions,
)
from nutmeg.recommendations.provider_incident_mapping import (
    RecommendationProviderIncidentMappingOptions,
)
from nutmeg.recommendations.recompute_trigger import RecommendationRecomputeTriggerOptions


class FakePipelineDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY:
            return _run_row(status="running")
        if query == COMPLETE_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY:
            return _run_row(
                status="completed",
                mapped_incident_count=params["mapped_incident_count"],
                stored_incident_count=params["stored_incident_count"],
                checked_run_count=params["checked_run_count"],
                triggered_run_count=params["triggered_run_count"],
                skipped_run_count=params["skipped_run_count"],
                generated_recommendation_run_ids_json=[88],
                prematch_report_key=params["prematch_report_key"],
                warnings_json=["dry_run_provider_incidents_not_persisted_before_recompute"],
                completed_at=_dt(2026, 5, 1, 12, 1),
                duration_ms=100,
            )
        if query == FAIL_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY:
            return _run_row(
                status="failed",
                warnings_json=[],
                error_message=params["error_message"],
                completed_at=_dt(2026, 5, 1, 12, 1),
                duration_ms=100,
            )
        raise AssertionError(f"unexpected query: {query}")


class FakeAuditRepository:
    def __init__(self) -> None:
        self.started: list[RecommendationPrematchPipelineOptions] = []
        self.completed: list[RecommendationPrematchPipelineRunResult] = []
        self.failed: list[str] = []

    def start_run(
        self,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None,
        source: str,
    ) -> RecommendationPrematchPipelineRunRecord:
        self.started.append(options)
        return _record(status="running", requested_by=requested_by)

    def complete_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        result: RecommendationPrematchPipelineRunResult,
    ) -> RecommendationPrematchPipelineRunRecord:
        self.completed.append(result)
        return _record(status="completed", requested_by=result.requested_by)

    def fail_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> RecommendationPrematchPipelineRunRecord:
        self.failed.append(error_message)
        return _record(status="failed", error_message=error_message)


def test_prematch_pipeline_runs_mapping_recompute_report_and_audit() -> None:
    calls: list[str] = []
    audit = FakeAuditRepository()

    def mapping_runner(
        database: object,
        *,
        options: RecommendationProviderIncidentMappingOptions,
    ) -> RecommendationProviderIncidentMappingResult:
        calls.append("mapping")
        assert options.lookback_hours == 12
        assert options.provider_name == "sportmonks"
        assert options.canonical_fixture_id == "fix-a"
        assert options.dry_run is True
        return RecommendationProviderIncidentMappingResult(
            dry_run=True,
            as_of_time_utc=options.as_of_time_utc,
            observation_count=3,
            mapped_incident_count=1,
            stored_incident_count=0,
        )

    def recompute_runner(
        database: object,
        *,
        options: RecommendationRecomputeTriggerOptions,
    ) -> RecommendationRecomputeTriggerRunResult:
        calls.append("recompute")
        assert options.pass_type == "6x1"
        assert options.mode == "multiple"
        assert options.strategy == "accuracy_first"
        assert options.preserve_locked_legs is True
        assert options.trigger_locked_successors is True
        return RecommendationRecomputeTriggerRunResult(
            dry_run=True,
            as_of_time_utc=options.as_of_time_utc,
            window_start_utc=options.window_start_utc,
            window_end_utc=options.as_of_time_utc,
            checked_run_count=2,
            triggered_run_count=1,
            skipped_run_count=1,
            generated_recommendation_run_ids=[88],
            incident_event_keys=["incident-a"],
        )

    def report_runner(
        database: object,
        *,
        options: RecommendationPrematchChangeReportOptions,
    ) -> RecommendationPrematchChangeReportRunResult:
        calls.append("report")
        assert options.window_start_utc == _dt(2026, 5, 1, 0)
        assert options.window_end_utc == _dt(2026, 5, 1, 12)
        return RecommendationPrematchChangeReportRunResult(
            dry_run=True,
            report=RecommendationPrematchChangeReport(
                report_key="prematch_change:test",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                replay=PersistedRecommendationLifecycleReplayResult(
                    summary_json={"stage_count": 2}
                ),
                checkpoint_count=2,
                summary_json={"stage_count": 2},
            ),
        )

    result = run_recommendation_prematch_pipeline(
        FakePipelineDatabase(),
        options=RecommendationPrematchPipelineOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            lookback_hours=12,
            pass_type="6x1",
            mode="multiple",
            strategy="accuracy_first",
            provider_name="sportmonks",
            canonical_fixture_id="fix-a",
            dry_run=True,
        ),
        requested_by="unit-test",
        audit_repository=audit,
        provider_incident_mapping_runner=mapping_runner,
        recompute_trigger_runner=recompute_runner,
        prematch_change_report_runner=report_runner,
    )

    assert calls == ["mapping", "recompute", "report"]
    assert result.mapped_incident_count == 1
    assert result.stored_incident_count == 0
    assert result.checked_run_count == 2
    assert result.triggered_run_count == 1
    assert result.skipped_run_count == 1
    assert result.generated_recommendation_run_ids == [88]
    assert result.prematch_report_key == "prematch_change:test"
    assert result.warnings == ["dry_run_provider_incidents_not_persisted_before_recompute"]
    assert result.stored_run is not None
    assert audit.completed[0].triggered_run_count == 1


def test_prematch_pipeline_failure_marks_audit_failed() -> None:
    audit = FakeAuditRepository()

    def failing_mapping_runner(
        database: object,
        *,
        options: RecommendationProviderIncidentMappingOptions,
    ) -> RecommendationProviderIncidentMappingResult:
        raise RuntimeError("provider observations unavailable")

    with pytest.raises(RuntimeError, match="provider observations unavailable"):
        run_recommendation_prematch_pipeline(
            FakePipelineDatabase(),
            options=RecommendationPrematchPipelineOptions(
                as_of_time_utc=_dt(2026, 5, 1, 12),
            ),
            audit_repository=audit,
            provider_incident_mapping_runner=failing_mapping_runner,
        )

    assert audit.failed == ["provider observations unavailable"]
    assert audit.completed == []


def test_postgres_prematch_pipeline_repository_writes_audit_rows() -> None:
    database = FakePipelineDatabase()
    repository = PostgresRecommendationPrematchPipelineRunRepository(database)
    options = RecommendationPrematchPipelineOptions(
        as_of_time_utc=_dt(2026, 5, 1, 12),
        lookback_hours=12,
        pass_type="2x1",
        mode="single",
        strategy="accuracy_first",
        dry_run=False,
    )

    started = repository.start_run(
        options=options,
        requested_by="unit-test",
        source="unit-test-source",
    )
    completed = repository.complete_run(
        recommendation_prematch_pipeline_run_id=started.recommendation_prematch_pipeline_run_id,
        result=RecommendationPrematchPipelineRunResult(
            dry_run=False,
            as_of_time_utc=options.normalized_as_of_time_utc,
            window_start_utc=options.window_start_utc,
            window_end_utc=options.normalized_as_of_time_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            mapped_incident_count=1,
            stored_incident_count=1,
            checked_run_count=2,
            triggered_run_count=1,
            skipped_run_count=1,
            generated_recommendation_run_ids=[88],
            prematch_report_key="prematch_change:test",
        ),
    )

    assert started.status == "running"
    assert completed.status == "completed"
    start_query, start_params = database.fetch_one_calls[0]
    complete_query, complete_params = database.fetch_one_calls[1]
    assert start_query == INSERT_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY
    assert start_params["requested_by"] == "unit-test"
    assert start_params["pass_type"] == "2x1"
    assert complete_query == COMPLETE_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY
    assert complete_params["triggered_run_count"] == 1
    assert complete_params["generated_recommendation_run_ids_json"] == "[88]"
    assert complete_params["prematch_report_key"] == "prematch_change:test"


def _record(
    *,
    status: str,
    requested_by: str | None = None,
    error_message: str | None = None,
) -> RecommendationPrematchPipelineRunRecord:
    return RecommendationPrematchPipelineRunRecord(
        recommendation_prematch_pipeline_run_id=301,
        run_key="prematch_pipeline:test",
        status=status,  # type: ignore[arg-type]
        dry_run=True,
        as_of_time_utc=_dt(2026, 5, 1, 12),
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 1, 12),
        requested_by=requested_by,
        error_message=error_message,
        source="unit-test",
        started_at=_dt(2026, 5, 1, 12),
        created_at=_dt(2026, 5, 1, 12),
        updated_at=_dt(2026, 5, 1, 12),
    )


def _run_row(
    *,
    status: str,
    mapped_incident_count: object = 0,
    stored_incident_count: object = 0,
    checked_run_count: object = 0,
    triggered_run_count: object = 0,
    skipped_run_count: object = 0,
    generated_recommendation_run_ids_json: object | None = None,
    prematch_report_key: object | None = None,
    warnings_json: object | None = None,
    error_message: object | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
) -> DatabaseRow:
    return {
        "recommendation_prematch_pipeline_run_id": 301,
        "run_key": "prematch_pipeline:test",
        "status": status,
        "dry_run": True,
        "as_of_time_utc": _dt(2026, 5, 1, 12),
        "window_start_utc": _dt(2026, 5, 1, 0),
        "window_end_utc": _dt(2026, 5, 1, 12),
        "pass_type": "2x1",
        "mode": "single",
        "strategy": "accuracy_first",
        "requested_by": "unit-test",
        "mapped_incident_count": mapped_incident_count,
        "stored_incident_count": stored_incident_count,
        "checked_run_count": checked_run_count,
        "triggered_run_count": triggered_run_count,
        "skipped_run_count": skipped_run_count,
        "generated_recommendation_run_ids_json": (
            generated_recommendation_run_ids_json or []
        ),
        "prematch_report_key": prematch_report_key,
        "warnings_json": warnings_json or [],
        "error_message": error_message,
        "source": "unit-test",
        "started_at": _dt(2026, 5, 1, 12),
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "created_at": _dt(2026, 5, 1, 12),
        "updated_at": _dt(2026, 5, 1, 12),
    }


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)
