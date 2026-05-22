from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.recommendations.chain_integrity import (
    RecommendationChainIntegrityOptions,
    RecommendationChainRunNode,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationOptions,
    _options_from_args,
    _parse_args,
    run_recommendation_successor_chain_evaluation,
)


def test_successor_chain_evaluation_passes_clean_multihop_leaf_chain() -> None:
    result = run_recommendation_successor_chain_evaluation(
        _FakeChainRepository(
            [
                _node(1, status="superseded"),
                _node(2, status="superseded", source_recommendation_run_id=1),
                _node(3, status="current", source_recommendation_run_id=2),
            ]
        ),
        options=_options(min_active_edge_count=2),
    )

    assert result.passed is True
    assert result.effective_chain.effective_leaf_recommendation_run_ids == [3]
    assert result.summary_json["active_edge_count"] == 2
    assert result.summary_json["effective_leaf_count"] == 1
    assert result.summary_json["chain_integrity_critical_issue_count"] == 0
    assert all(check.status == "passed" for check in result.checks)


def test_successor_chain_evaluation_blocks_ambiguous_active_successors() -> None:
    result = run_recommendation_successor_chain_evaluation(
        _FakeChainRepository(
            [
                _node(1, status="superseded"),
                _node(2, status="current", source_recommendation_run_id=1),
                _node(3, status="current", source_recommendation_run_id=1),
            ]
        ),
        options=_options(),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "chain_integrity_critical_issue_count" in failed_names
    assert "ambiguous_successor_source_count" in failed_names
    assert result.summary_json["ambiguous_successor_source_recommendation_run_ids"] == [1]
    assert "successor_chain_evaluation:ambiguous_successor_sources" in result.warnings


def test_successor_chain_evaluation_ignores_invalidated_successor() -> None:
    result = run_recommendation_successor_chain_evaluation(
        _FakeChainRepository(
            [
                _node(1, status="current"),
                _node(2, status="invalidated", source_recommendation_run_id=1),
            ]
        ),
        options=_options(),
    )

    assert result.passed is True
    assert result.effective_chain.effective_leaf_recommendation_run_ids == [1]
    assert result.summary_json["invalidated_successor_count"] == 1
    assert (
        result.summary_json[
            "ignored_invalidated_successor_source_recommendation_run_ids"
        ]
        == [1]
    )
    assert "successor_chain_evaluation:invalidated_successors_ignored" in result.warnings


def test_successor_chain_evaluation_can_fail_on_unsynced_source_status() -> None:
    result = run_recommendation_successor_chain_evaluation(
        _FakeChainRepository(
            [
                _node(1, status="current"),
                _node(2, status="current", source_recommendation_run_id=1),
            ]
        ),
        options=_options(max_source_status_sync_required_count=0),
    )

    failed_names = {check.name for check in result.checks if check.status == "failed"}
    assert result.passed is False
    assert "source_status_sync_required_count" in failed_names
    assert result.summary_json["source_status_sync_required_count"] == 1


def test_successor_chain_evaluation_cli_maps_threshold_args() -> None:
    args = _parse_args(
        [
            "--window-start-utc",
            "2026-05-01T00:00:00Z",
            "--window-end-utc",
            "2026-05-03T00:00:00Z",
            "--output-path",
            "tmp/successor_chain_evaluation.json",
            "--pass-type",
            "6x1",
            "--mode",
            "single",
            "--limit",
            "42",
            "--min-effective-leaf-count",
            "2",
            "--min-active-edge-count",
            "1",
            "--max-critical-issue-count",
            "0",
            "--max-ambiguous-successor-source-count",
            "0",
            "--max-source-status-sync-required-count",
            "0",
        ]
    )
    options = _options_from_args(args)

    assert options.pass_type == "6x1"
    assert options.mode == "single"
    assert options.limit == 42
    assert options.min_effective_leaf_count == 2
    assert options.min_active_edge_count == 1
    assert options.max_source_status_sync_required_count == 0
    assert str(args.output_path) == "tmp/successor_chain_evaluation.json"


class _FakeChainRepository:
    def __init__(self, nodes: Sequence[RecommendationChainRunNode]) -> None:
        self.nodes = list(nodes)

    def list_chain_runs(
        self,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> list[RecommendationChainRunNode]:
        return self.nodes[: options.limit]


def _options(
    *,
    min_active_edge_count: int = 0,
    max_source_status_sync_required_count: int | None = None,
) -> RecommendationSuccessorChainEvaluationOptions:
    return RecommendationSuccessorChainEvaluationOptions(
        window_start_utc=_dt(2026, 5, 1, 0),
        window_end_utc=_dt(2026, 5, 3, 0),
        min_active_edge_count=min_active_edge_count,
        max_source_status_sync_required_count=max_source_status_sync_required_count,
    )


def _node(
    recommendation_run_id: int,
    *,
    status: str,
    source_recommendation_run_id: int | None = None,
) -> RecommendationChainRunNode:
    return RecommendationChainRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=f"run-{recommendation_run_id}",
        as_of_time_utc=_dt(2026, 5, recommendation_run_id, 10),
        strategy="accuracy_first",
        pass_type="6x1",
        mode="single",
        status=status,
        selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
        locked_fixture_ids=[],
        source_recommendation_run_id=source_recommendation_run_id,
        source_run_key=f"run-{source_recommendation_run_id}"
        if source_recommendation_run_id
        else None,
        created_at=_dt(2026, 5, recommendation_run_id, 10),
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
