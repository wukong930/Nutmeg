from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.chain_integrity import (
    LIST_RECOMMENDATION_CHAIN_RUNS_QUERY,
    PostgresRecommendationChainIntegrityRepository,
    RecommendationChainIntegrityOptions,
    RecommendationChainRunNode,
    build_recommendation_chain_integrity_report,
    run_recommendation_chain_integrity_check,
)


def test_chain_integrity_counts_successor_leaf_and_flags_source_status_sync() -> None:
    report = build_recommendation_chain_integrity_report(
        [
            _node(1, run_key="source", status="locked"),
            _node(2, run_key="successor", source_recommendation_run_id=1),
        ],
        options=_options(),
    )

    assert report.ready is True
    assert report.summary_json["run_count"] == 2
    assert report.summary_json["edge_count"] == 1
    assert report.summary_json["leaf_recommendation_run_ids"] == [2]
    assert report.summary_json["superseded_source_recommendation_run_ids"] == [1]
    assert report.summary_json["source_status_sync_required_count"] == 1
    assert [issue.code for issue in report.issues] == ["source_status_not_superseded"]
    assert report.issues[0].metadata_json["recommended_status"] == "superseded"


def test_chain_integrity_detects_duplicate_active_successors() -> None:
    report = build_recommendation_chain_integrity_report(
        [
            _node(1, run_key="source", status="superseded"),
            _node(2, run_key="successor_a", source_recommendation_run_id=1),
            _node(3, run_key="successor_b", source_recommendation_run_id=1),
        ],
        options=_options(),
    )

    duplicate_issue = next(
        issue for issue in report.issues if issue.code == "multiple_active_successors"
    )
    assert report.ready is False
    assert duplicate_issue.severity == "critical"
    assert duplicate_issue.recommendation_run_id == 1
    assert duplicate_issue.successor_recommendation_run_ids == [2, 3]


def test_chain_integrity_detects_missing_source_and_cycles() -> None:
    missing_report = build_recommendation_chain_integrity_report(
        [_node(2, run_key="orphan_successor", source_recommendation_run_id=99)],
        options=_options(),
    )
    cycle_report = build_recommendation_chain_integrity_report(
        [
            _node(1, run_key="cycle_a", source_recommendation_run_id=2),
            _node(2, run_key="cycle_b", source_recommendation_run_id=1),
        ],
        options=_options(),
    )

    assert missing_report.ready is False
    assert any(issue.code == "successor_source_missing" for issue in missing_report.issues)
    assert cycle_report.ready is False
    assert any(issue.code == "successor_cycle_detected" for issue in cycle_report.issues)


def test_postgres_chain_integrity_repository_reads_trace_links() -> None:
    database = FakeRecommendationChainIntegrityDatabase()
    repository = PostgresRecommendationChainIntegrityRepository(database)

    report = run_recommendation_chain_integrity_check(repository, options=_options())

    assert report.summary_json["leaf_recommendation_run_ids"] == [2]
    assert report.issues[0].code == "source_status_not_superseded"
    query, params = database.fetch_all_calls[0]
    assert query == LIST_RECOMMENDATION_CHAIN_RUNS_QUERY
    assert params["limit"] == 500
    assert params["pass_type"] is None


class FakeRecommendationChainIntegrityDatabase:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query != LIST_RECOMMENDATION_CHAIN_RUNS_QUERY:
            raise AssertionError(f"unexpected query: {query}")
        return [
            _row(1, run_key="source", status="locked"),
            _row(2, run_key="successor", source_recommendation_run_id=1),
        ]


def _options() -> RecommendationChainIntegrityOptions:
    return RecommendationChainIntegrityOptions(
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 3, 0),
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
        locked_fixture_ids=["A", "B"],
        source_recommendation_run_id=source_recommendation_run_id,
        source_run_key="source" if source_recommendation_run_id else None,
        created_at=_dt(2026, 5, recommendation_run_id, 10),
    )


def _row(
    recommendation_run_id: int,
    *,
    run_key: str,
    status: str = "current",
    source_recommendation_run_id: int | None = None,
) -> DatabaseRow:
    return {
        "recommendation_run_id": recommendation_run_id,
        "run_key": run_key,
        "as_of_time_utc": _dt(2026, 5, recommendation_run_id, 10),
        "strategy": "accuracy_first",
        "pass_type": "6x1",
        "mode": "single",
        "status": status,
        "selected_fixture_ids_json": dumps(["A", "B", "C", "D", "E", "F"]),
        "locked_fixture_ids_json": dumps(["A", "B"]),
        "explanation_json": dumps(_explanation(source_recommendation_run_id)),
        "created_at": _dt(2026, 5, recommendation_run_id, 10),
    }


def _explanation(source_recommendation_run_id: int | None) -> dict[str, object]:
    if source_recommendation_run_id is None:
        return {}
    return {
        "internal_trace": {
            "successor_recompute": {
                "source_recommendation_run_id": source_recommendation_run_id,
                "source_run_key": "source",
                "calculation_basis": "locked_leg_successor_recompute_v3_1",
            }
        }
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
