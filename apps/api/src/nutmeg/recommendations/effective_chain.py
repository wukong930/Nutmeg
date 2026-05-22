from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class RecommendationEffectiveChainNode(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str | None = None
    status: str
    source_recommendation_run_id: int | None = Field(default=None, gt=0)
    as_of_time_utc: datetime | None = None


class RecommendationEffectiveChainReport(BaseModel):
    nodes: list[RecommendationEffectiveChainNode] = Field(default_factory=list)
    root_recommendation_run_ids: list[int] = Field(default_factory=list)
    leaf_recommendation_run_ids: list[int] = Field(default_factory=list)
    effective_leaf_recommendation_run_ids: list[int] = Field(default_factory=list)
    superseded_source_recommendation_run_ids: list[int] = Field(default_factory=list)
    invalidated_successor_recommendation_run_ids: list[int] = Field(
        default_factory=list
    )
    ignored_invalidated_successor_source_recommendation_run_ids: list[int] = Field(
        default_factory=list
    )
    ambiguous_successor_source_recommendation_run_ids: list[int] = Field(
        default_factory=list
    )
    active_edge_count: int = Field(ge=0)
    chain_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_effective_recommendation_chain(
    nodes: Sequence[RecommendationEffectiveChainNode],
) -> RecommendationEffectiveChainReport:
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            _optional_aware_utc(node.as_of_time_utc),
            node.recommendation_run_id,
        ),
    )
    active_nodes = [node for node in ordered_nodes if node.status != "invalidated"]
    active_node_ids = {node.recommendation_run_id for node in active_nodes}
    successors_by_source = _active_successors_by_source(active_nodes, active_node_ids)
    active_source_ids = set(successors_by_source)
    superseded_source_run_ids = [
        node.recommendation_run_id
        for node in active_nodes
        if node.recommendation_run_id in active_source_ids
    ]
    root_run_ids = [
        node.recommendation_run_id
        for node in active_nodes
        if node.source_recommendation_run_id not in active_node_ids
    ]
    leaf_run_ids = [
        node.recommendation_run_id
        for node in active_nodes
        if node.recommendation_run_id not in active_source_ids
    ]
    effective_leaf_run_ids = [
        node.recommendation_run_id
        for node in active_nodes
        if node.recommendation_run_id in leaf_run_ids
        and node.status != "superseded"
    ]
    invalidated_successor_run_ids = [
        node.recommendation_run_id
        for node in ordered_nodes
        if node.status == "invalidated"
        and node.source_recommendation_run_id is not None
    ]
    ignored_invalidated_source_ids = _dedupe_ints(
        node.source_recommendation_run_id
        for node in ordered_nodes
        if node.status == "invalidated"
        and node.source_recommendation_run_id in active_node_ids
    )
    ambiguous_source_ids = [
        source_id
        for source_id, successor_ids in sorted(successors_by_source.items())
        if len(successor_ids) > 1
    ]
    active_edge_count = sum(len(successor_ids) for successor_ids in successors_by_source.values())
    summary = {
        "run_count": len(ordered_nodes),
        "active_run_count": len(active_nodes),
        "active_edge_count": active_edge_count,
        "chain_count": len(root_run_ids),
        "root_recommendation_run_ids": root_run_ids,
        "leaf_recommendation_run_ids": leaf_run_ids,
        "effective_leaf_recommendation_run_ids": effective_leaf_run_ids,
        "superseded_source_recommendation_run_ids": superseded_source_run_ids,
        "invalidated_successor_recommendation_run_ids": invalidated_successor_run_ids,
        "ignored_invalidated_successor_source_recommendation_run_ids": (
            ignored_invalidated_source_ids
        ),
        "ambiguous_successor_source_recommendation_run_ids": ambiguous_source_ids,
        "calculation_basis": "effective_recommendation_chain_v3_1",
    }
    return RecommendationEffectiveChainReport(
        nodes=ordered_nodes,
        root_recommendation_run_ids=root_run_ids,
        leaf_recommendation_run_ids=leaf_run_ids,
        effective_leaf_recommendation_run_ids=effective_leaf_run_ids,
        superseded_source_recommendation_run_ids=superseded_source_run_ids,
        invalidated_successor_recommendation_run_ids=invalidated_successor_run_ids,
        ignored_invalidated_successor_source_recommendation_run_ids=(
            ignored_invalidated_source_ids
        ),
        ambiguous_successor_source_recommendation_run_ids=ambiguous_source_ids,
        active_edge_count=active_edge_count,
        chain_count=len(root_run_ids),
        summary_json=summary,
    )


def successor_source_recommendation_run_id_from_explanation(
    explanation_json: Mapping[str, object],
) -> int | None:
    internal_trace = explanation_json.get("internal_trace")
    if not isinstance(internal_trace, Mapping):
        return None
    successor_recompute = internal_trace.get("successor_recompute")
    if not isinstance(successor_recompute, Mapping):
        return None
    return _optional_positive_int(successor_recompute.get("source_recommendation_run_id"))


def _active_successors_by_source(
    nodes: Sequence[RecommendationEffectiveChainNode],
    active_node_ids: set[int],
) -> dict[int, list[int]]:
    successors_by_source: dict[int, list[int]] = {}
    for node in nodes:
        source_id = node.source_recommendation_run_id
        if source_id is None or source_id not in active_node_ids:
            continue
        successors_by_source.setdefault(source_id, []).append(
            node.recommendation_run_id
        )
    return {
        source_id: _dedupe_ints(successor_ids)
        for source_id, successor_ids in sorted(successors_by_source.items())
    }


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value) if isinstance(value, int | float | Decimal | str) else None
    except (TypeError, ValueError):
        return None
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _optional_aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _dedupe_ints(values: Iterable[int | None]) -> list[int]:
    result: list[int] = []
    for value in values:
        if value is None or value in result:
            continue
        result.append(value)
    return result
