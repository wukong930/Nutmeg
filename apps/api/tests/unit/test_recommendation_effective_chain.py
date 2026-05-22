from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.recommendations import (
    RecommendationEffectiveChainNode,
    build_effective_recommendation_chain,
    successor_source_recommendation_run_id_from_explanation,
)


def test_effective_chain_counts_only_multihop_leaf_runs() -> None:
    report = build_effective_recommendation_chain(
        [
            _node(1, "current", as_of_hour=10),
            _node(2, "current", source_id=1, as_of_hour=11),
            _node(3, "current", source_id=2, as_of_hour=12),
        ]
    )

    assert report.root_recommendation_run_ids == [1]
    assert report.leaf_recommendation_run_ids == [3]
    assert report.effective_leaf_recommendation_run_ids == [3]
    assert report.superseded_source_recommendation_run_ids == [1, 2]
    assert report.active_edge_count == 2
    assert report.chain_count == 1
    assert (
        report.summary_json["calculation_basis"]
        == "effective_recommendation_chain_v3_1"
    )


def test_effective_chain_ignores_invalidated_successor_edges() -> None:
    report = build_effective_recommendation_chain(
        [
            _node(1, "current", as_of_hour=10),
            _node(2, "invalidated", source_id=1, as_of_hour=11),
        ]
    )

    assert report.root_recommendation_run_ids == [1]
    assert report.leaf_recommendation_run_ids == [1]
    assert report.effective_leaf_recommendation_run_ids == [1]
    assert report.superseded_source_recommendation_run_ids == []
    assert report.invalidated_successor_recommendation_run_ids == [2]
    assert report.ignored_invalidated_successor_source_recommendation_run_ids == [1]
    assert report.active_edge_count == 0


def test_effective_chain_marks_ambiguous_sources_without_selecting_strategy() -> None:
    report = build_effective_recommendation_chain(
        [
            _node(1, "current", as_of_hour=10),
            _node(2, "current", source_id=1, as_of_hour=11),
            _node(3, "current", source_id=1, as_of_hour=12),
        ]
    )

    assert report.superseded_source_recommendation_run_ids == [1]
    assert report.leaf_recommendation_run_ids == [2, 3]
    assert report.effective_leaf_recommendation_run_ids == [2, 3]
    assert report.ambiguous_successor_source_recommendation_run_ids == [1]


def test_successor_source_parser_accepts_numeric_strings_and_rejects_bool() -> None:
    assert (
        successor_source_recommendation_run_id_from_explanation(
            {
                "internal_trace": {
                    "successor_recompute": {
                        "source_recommendation_run_id": "41",
                    }
                }
            }
        )
        == 41
    )
    assert (
        successor_source_recommendation_run_id_from_explanation(
            {
                "internal_trace": {
                    "successor_recompute": {
                        "source_recommendation_run_id": True,
                    }
                }
            }
        )
        is None
    )


def _node(
    recommendation_run_id: int,
    status: str,
    *,
    source_id: int | None = None,
    as_of_hour: int,
) -> RecommendationEffectiveChainNode:
    return RecommendationEffectiveChainNode(
        recommendation_run_id=recommendation_run_id,
        run_key=f"run-{recommendation_run_id}",
        status=status,
        source_recommendation_run_id=source_id,
        as_of_time_utc=datetime(2026, 5, 1, as_of_hour, tzinfo=UTC),
    )
