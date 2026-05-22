from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.recommendations.chain_integrity import (
    RecommendationChainIntegrityOptions,
    RecommendationChainRunNode,
)
from nutmeg.recommendations.lifecycle import RecommendationLifecycleStatus
from nutmeg.recommendations.repository import (
    RecommendationLifecycleEventRecord,
    RecommendationLifecycleMutationResult,
    RecommendationRunLifecycleRecord,
)
from nutmeg.recommendations.source_status_sync import (
    RecommendationSourceStatusSyncOptions,
    _options_from_args,
    _parse_args,
    run_recommendation_source_status_sync,
)


def test_source_status_sync_dry_run_lists_candidates_without_mutation() -> None:
    chain_repository = FakeChainRepository(
        [
            _node(1, run_key="source", status="current"),
            _node(2, run_key="successor", source_recommendation_run_id=1),
        ]
    )
    status_repository = FakeStatusRepository()

    result = run_recommendation_source_status_sync(
        FakeDatabase(),
        options=_options(dry_run=True),
        chain_repository=chain_repository,
        status_repository=status_repository,
    )

    assert result.dry_run is True
    assert result.blocked is False
    assert [candidate.recommendation_run_id for candidate in result.candidates] == [1]
    assert result.candidates[0].successor_recommendation_run_ids == [2]
    assert result.summary_json["candidate_count"] == 1
    assert result.summary_json["synced_source_count"] == 0
    assert status_repository.transitions == []


def test_source_status_sync_commit_marks_current_or_locked_sources_superseded() -> None:
    event_time = _dt(2026, 5, 12, 8)
    chain_repository = FakeChainRepository(
        [
            _node(1, run_key="source-a", status="current"),
            _node(2, run_key="successor-a", source_recommendation_run_id=1),
            _node(3, run_key="source-b", status="locked"),
            _node(4, run_key="successor-b", source_recommendation_run_id=3),
        ]
    )
    status_repository = FakeStatusRepository()

    result = run_recommendation_source_status_sync(
        FakeDatabase(),
        options=_options(dry_run=False, event_time_utc=event_time),
        chain_repository=chain_repository,
        status_repository=status_repository,
    )

    assert result.dry_run is False
    assert result.blocked is False
    assert result.synced_source_recommendation_run_ids == [1, 3]
    assert [mutation.run.status for mutation in result.mutations] == [
        "superseded",
        "superseded",
    ]
    assert status_repository.transitions == [
        {
            "recommendation_run_id": 1,
            "to_status": "superseded",
            "event_time_utc": event_time,
            "reason_code": "successor_source_status_sync",
            "metadata_json": {
                "successor_recommendation_run_ids": [2],
                "previous_status": "current",
                "source": "recommendation_source_status_sync_v3_1",
            },
        },
        {
            "recommendation_run_id": 3,
            "to_status": "superseded",
            "event_time_utc": event_time,
            "reason_code": "successor_source_status_sync",
            "metadata_json": {
                "successor_recommendation_run_ids": [4],
                "previous_status": "locked",
                "source": "recommendation_source_status_sync_v3_1",
            },
        },
    ]
    assert result.summary_json["chain_integrity_ready"] is True


def test_source_status_sync_blocks_commit_when_chain_has_critical_issues() -> None:
    chain_repository = FakeChainRepository(
        [
            _node(1, run_key="source", status="locked"),
            _node(2, run_key="successor-a", source_recommendation_run_id=1),
            _node(3, run_key="successor-b", source_recommendation_run_id=1),
        ]
    )
    status_repository = FakeStatusRepository()

    result = run_recommendation_source_status_sync(
        FakeDatabase(),
        options=_options(dry_run=False),
        chain_repository=chain_repository,
        status_repository=status_repository,
    )

    assert result.blocked is True
    assert result.block_reason == "chain_integrity_critical_issues"
    assert result.synced_source_recommendation_run_ids == []
    assert result.skipped_source_recommendation_run_ids == [1]
    assert result.summary_json["chain_integrity_critical_issue_count"] == 1
    assert any(
        warning == "source_status_sync_blocked_by_chain_integrity:multiple_active_successors"
        for warning in result.warnings
    )
    assert status_repository.transitions == []


def test_source_status_sync_skips_candidate_status_sources_by_default() -> None:
    chain_repository = FakeChainRepository(
        [
            _node(1, run_key="source", status="candidate"),
            _node(2, run_key="successor", source_recommendation_run_id=1),
        ]
    )
    status_repository = FakeStatusRepository()

    result = run_recommendation_source_status_sync(
        FakeDatabase(),
        options=_options(dry_run=False),
        chain_repository=chain_repository,
        status_repository=status_repository,
    )

    assert result.blocked is False
    assert result.candidates == []
    assert result.warnings == ["source_status_sync_unsupported_status:1:candidate"]
    assert result.summary_json["candidate_count"] == 0
    assert status_repository.transitions == []


def test_source_status_sync_cli_maps_args_to_safe_dry_run_options() -> None:
    args = _parse_args(
        [
            "--window-start-utc",
            "2026-05-01T00:00:00Z",
            "--window-end-utc",
            "2026-05-03T00:00:00Z",
            "--pass-type",
            "6x1",
            "--mode",
            "multiple",
            "--strategy",
            "accuracy_first",
            "--limit",
            "90",
            "--event-time-utc",
            "2026-05-12T08:00:00Z",
            "--allowed-source-statuses",
            "current, locked",
            "--reason-code",
            "unit_test_sync",
        ]
    )

    options = _options_from_args(args)

    assert options.window_start_utc == _dt(2026, 5, 1, 0)
    assert options.window_end_utc == _dt(2026, 5, 3, 0)
    assert options.pass_type == "6x1"
    assert options.mode == "multiple"
    assert options.strategy == "accuracy_first"
    assert options.limit == 90
    assert options.event_time_utc == _dt(2026, 5, 12, 8)
    assert options.dry_run is True
    assert options.allowed_source_statuses == ("current", "locked")
    assert options.reason_code == "unit_test_sync"


def test_source_status_sync_cli_commit_maps_to_non_dry_run() -> None:
    args = _parse_args(
        [
            "--window-start-utc",
            "2026-05-01T00:00:00Z",
            "--window-end-utc",
            "2026-05-03T00:00:00Z",
            "--commit",
        ]
    )

    assert _options_from_args(args).dry_run is False


class FakeDatabase:
    pass


class FakeChainRepository:
    def __init__(self, nodes: Sequence[RecommendationChainRunNode]) -> None:
        self.nodes = list(nodes)
        self.options: list[RecommendationChainIntegrityOptions] = []

    def list_chain_runs(
        self,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> list[RecommendationChainRunNode]:
        self.options.append(options)
        return list(self.nodes)


class FakeStatusRepository:
    def __init__(self) -> None:
        self.transitions: list[dict[str, object]] = []

    def transition_run_status(
        self,
        recommendation_run_id: int,
        *,
        to_status: RecommendationLifecycleStatus,
        event_time_utc: datetime,
        reason_code: str,
        metadata_json: dict[str, object] | None = None,
    ) -> RecommendationLifecycleMutationResult:
        self.transitions.append(
            {
                "recommendation_run_id": recommendation_run_id,
                "to_status": to_status,
                "event_time_utc": event_time_utc,
                "reason_code": reason_code,
                "metadata_json": metadata_json or {},
            }
        )
        return _mutation(
            recommendation_run_id,
            to_status=to_status,
            event_time_utc=event_time_utc,
            reason_code=reason_code,
            metadata_json=metadata_json or {},
        )


def _options(
    *,
    dry_run: bool,
    event_time_utc: datetime | None = None,
) -> RecommendationSourceStatusSyncOptions:
    return RecommendationSourceStatusSyncOptions(
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 3, 0),
        pass_type="6x1",
        mode="single",
        strategy="accuracy_first",
        dry_run=dry_run,
        event_time_utc=event_time_utc,
    )


def _node(
    recommendation_run_id: int,
    *,
    run_key: str,
    status: str = "current",
    source_recommendation_run_id: int | None = None,
) -> RecommendationChainRunNode:
    return RecommendationChainRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=_dt(2026, 5, recommendation_run_id, 10),
        strategy="accuracy_first",
        pass_type="6x1",
        mode="single",
        status=status,
        selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
        locked_fixture_ids=["A", "B"] if status == "locked" else [],
        source_recommendation_run_id=source_recommendation_run_id,
        source_run_key="source" if source_recommendation_run_id else None,
        created_at=_dt(2026, 5, recommendation_run_id, 10),
    )


def _mutation(
    recommendation_run_id: int,
    *,
    to_status: RecommendationLifecycleStatus,
    event_time_utc: datetime,
    reason_code: str,
    metadata_json: dict[str, object],
) -> RecommendationLifecycleMutationResult:
    return RecommendationLifecycleMutationResult(
        run=RecommendationRunLifecycleRecord(
            recommendation_run_id=recommendation_run_id,
            run_key=f"run-{recommendation_run_id}",
            status=to_status,
            selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
            locked_fixture_ids=[],
            created_at=_dt(2026, 5, recommendation_run_id, 10),
        ),
        event=RecommendationLifecycleEventRecord(
            recommendation_lifecycle_event_id=900 + recommendation_run_id,
            recommendation_run_id=recommendation_run_id,
            recommendation_key=f"run-{recommendation_run_id}",
            from_status="locked",
            to_status=to_status,
            reason_code=reason_code,
            event_time_utc=event_time_utc,
            metadata_json=metadata_json,
        ),
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
