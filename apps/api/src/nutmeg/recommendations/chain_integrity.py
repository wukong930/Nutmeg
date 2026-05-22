from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.models import RecommendationMode

type RecommendationChainIntegritySeverity = Literal["info", "warning", "critical"]

SUCCESSOR_SOURCE_JSON_PATH = (
    "{internal_trace,successor_recompute,source_recommendation_run_id}"
)

LIST_RECOMMENDATION_CHAIN_RUNS_QUERY = """
WITH scoped_runs AS (
  SELECT recommendation_run_id
  FROM recommendation_runs
  WHERE as_of_time_utc >= %(window_start_utc)s
    AND as_of_time_utc <= %(window_end_utc)s
    AND (%(pass_type)s::text IS NULL OR pass_type = %(pass_type)s::text)
    AND (%(mode)s::text IS NULL OR mode = %(mode)s::text)
    AND (%(strategy)s::text IS NULL OR strategy = %(strategy)s::text)
  ORDER BY as_of_time_utc ASC, recommendation_run_id ASC
  LIMIT %(limit)s
),
referenced_sources AS (
  SELECT DISTINCT
    (rr.explanation_json #>>
      '{internal_trace,successor_recompute,source_recommendation_run_id}')::bigint
      AS recommendation_run_id
  FROM recommendation_runs rr
  JOIN scoped_runs sr
    ON sr.recommendation_run_id = rr.recommendation_run_id
  WHERE rr.explanation_json #>>
    '{internal_trace,successor_recompute,source_recommendation_run_id}'
    ~ '^[0-9]+$'
)
SELECT
  rr.recommendation_run_id,
  rr.run_key,
  rr.as_of_time_utc,
  rr.strategy,
  rr.pass_type,
  rr.mode,
  rr.status,
  rr.selected_fixture_ids_json,
  rr.locked_fixture_ids_json,
  rr.explanation_json,
  rr.created_at
FROM recommendation_runs rr
WHERE rr.recommendation_run_id IN (
    SELECT recommendation_run_id FROM scoped_runs
  )
  OR rr.recommendation_run_id IN (
    SELECT recommendation_run_id FROM referenced_sources
  )
ORDER BY rr.as_of_time_utc ASC, rr.recommendation_run_id ASC
"""


class RecommendationChainIntegrityDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation runs for source/successor chain integrity checks."""


class RecommendationChainIntegrityOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=500, ge=1, le=5_000)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)


class RecommendationChainRunNode(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    as_of_time_utc: datetime
    strategy: str
    pass_type: str
    mode: RecommendationMode
    status: str
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    source_recommendation_run_id: int | None = Field(default=None, gt=0)
    source_run_key: str | None = None
    successor_recommendation_run_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class RecommendationChainIntegrityIssue(BaseModel):
    code: str
    severity: RecommendationChainIntegritySeverity
    message: str
    recommendation_run_id: int | None = Field(default=None, gt=0)
    run_key: str | None = None
    source_recommendation_run_id: int | None = Field(default=None, gt=0)
    successor_recommendation_run_ids: list[int] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationChainIntegrityReport(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: str | None = None
    ready: bool
    nodes: list[RecommendationChainRunNode] = Field(default_factory=list)
    issues: list[RecommendationChainIntegrityIssue] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class RecommendationChainIntegrityRepository(Protocol):
    def list_chain_runs(
        self,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> list[RecommendationChainRunNode]:
        """List recommendation run nodes for chain integrity checks."""


class PostgresRecommendationChainIntegrityRepository:
    def __init__(self, database: RecommendationChainIntegrityDatabaseExecutor) -> None:
        self.database = database

    def list_chain_runs(
        self,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> list[RecommendationChainRunNode]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_CHAIN_RUNS_QUERY,
            {
                "window_start_utc": options.normalized_window_start_utc,
                "window_end_utc": options.normalized_window_end_utc,
                "pass_type": options.pass_type,
                "mode": options.mode,
                "strategy": options.strategy,
                "limit": options.limit,
            },
        )
        return build_recommendation_chain_nodes(
            [_chain_node_from_row(row) for row in rows]
        )


def run_recommendation_chain_integrity_check(
    repository: RecommendationChainIntegrityRepository,
    *,
    options: RecommendationChainIntegrityOptions,
) -> RecommendationChainIntegrityReport:
    nodes = repository.list_chain_runs(options=options)
    return build_recommendation_chain_integrity_report(nodes, options=options)


def build_recommendation_chain_nodes(
    nodes: Sequence[RecommendationChainRunNode],
) -> list[RecommendationChainRunNode]:
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            _aware_utc(node.as_of_time_utc),
            node.recommendation_run_id,
        ),
    )
    successors_by_source: dict[int, list[int]] = {}
    for node in ordered_nodes:
        if node.status == "invalidated" or node.source_recommendation_run_id is None:
            continue
        successors_by_source.setdefault(node.source_recommendation_run_id, []).append(
            node.recommendation_run_id
        )
    return [
        node.model_copy(
            update={
                "successor_recommendation_run_ids": successors_by_source.get(
                    node.recommendation_run_id,
                    [],
                )
            }
        )
        for node in ordered_nodes
    ]


def build_recommendation_chain_integrity_report(
    nodes: Sequence[RecommendationChainRunNode],
    *,
    options: RecommendationChainIntegrityOptions,
) -> RecommendationChainIntegrityReport:
    ordered_nodes = build_recommendation_chain_nodes(nodes)
    issues = _chain_integrity_issues(ordered_nodes)
    critical_count = sum(1 for issue in issues if issue.severity == "critical")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    active_nodes = [node for node in ordered_nodes if node.status != "invalidated"]
    leaf_run_ids = _leaf_run_ids(active_nodes)
    source_run_ids = _active_source_run_ids(active_nodes)
    summary: dict[str, object] = {
        "run_count": len(ordered_nodes),
        "active_run_count": len(active_nodes),
        "edge_count": sum(1 for node in active_nodes if node.source_recommendation_run_id),
        "root_recommendation_run_ids": _root_run_ids(active_nodes),
        "leaf_recommendation_run_ids": leaf_run_ids,
        "superseded_source_recommendation_run_ids": source_run_ids,
        "issue_count": len(issues),
        "critical_issue_count": critical_count,
        "warning_issue_count": warning_count,
        "source_status_sync_required_count": sum(
            1 for issue in issues if issue.code == "source_status_not_superseded"
        ),
        "ready": critical_count == 0,
        "calculation_basis": "recommendation_chain_integrity_v3_1",
    }
    return RecommendationChainIntegrityReport(
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        ready=critical_count == 0,
        nodes=ordered_nodes,
        issues=issues,
        summary_json=summary,
    )


def _chain_integrity_issues(
    nodes: Sequence[RecommendationChainRunNode],
) -> list[RecommendationChainIntegrityIssue]:
    node_by_id = {node.recommendation_run_id: node for node in nodes}
    active_nodes = [node for node in nodes if node.status != "invalidated"]
    active_node_by_id = {node.recommendation_run_id: node for node in active_nodes}
    issues: list[RecommendationChainIntegrityIssue] = []
    active_successors_by_source = _active_successors_by_source(active_nodes)

    for node in active_nodes:
        source_id = node.source_recommendation_run_id
        if source_id is None:
            continue
        if source_id == node.recommendation_run_id:
            issues.append(
                RecommendationChainIntegrityIssue(
                    code="successor_self_reference",
                    severity="critical",
                    message="A recommendation run points to itself as its source.",
                    recommendation_run_id=node.recommendation_run_id,
                    run_key=node.run_key,
                    source_recommendation_run_id=source_id,
                )
            )
        source = node_by_id.get(source_id)
        if source is None:
            issues.append(
                RecommendationChainIntegrityIssue(
                    code="successor_source_missing",
                    severity="critical",
                    message="A successor run references a missing source run.",
                    recommendation_run_id=node.recommendation_run_id,
                    run_key=node.run_key,
                    source_recommendation_run_id=source_id,
                )
            )
            continue
        if node.as_of_time_utc < source.as_of_time_utc:
            issues.append(
                RecommendationChainIntegrityIssue(
                    code="successor_before_source",
                    severity="warning",
                    message="A successor run is earlier than its source run.",
                    recommendation_run_id=node.recommendation_run_id,
                    run_key=node.run_key,
                    source_recommendation_run_id=source_id,
                    metadata_json={
                        "source_as_of_time_utc": source.as_of_time_utc.isoformat(),
                        "successor_as_of_time_utc": node.as_of_time_utc.isoformat(),
                    },
                )
            )

    for source_id, successor_ids in sorted(active_successors_by_source.items()):
        source = active_node_by_id.get(source_id)
        if len(successor_ids) > 1:
            issues.append(
                RecommendationChainIntegrityIssue(
                    code="multiple_active_successors",
                    severity="critical",
                    message="A source run has more than one active successor.",
                    recommendation_run_id=source_id,
                    run_key=source.run_key if source is not None else None,
                    successor_recommendation_run_ids=successor_ids,
                )
            )
        if source is not None and source.status in {"candidate", "current", "locked"}:
            issues.append(
                RecommendationChainIntegrityIssue(
                    code="source_status_not_superseded",
                    severity="warning",
                    message="A source run has an active successor but is not marked superseded.",
                    recommendation_run_id=source.recommendation_run_id,
                    run_key=source.run_key,
                    successor_recommendation_run_ids=successor_ids,
                    metadata_json={
                        "current_status": source.status,
                        "recommended_status": "superseded",
                    },
                )
            )

    for cycle in _cycle_paths(active_successors_by_source):
        issues.append(
            RecommendationChainIntegrityIssue(
                code="successor_cycle_detected",
                severity="critical",
                message="The source/successor graph contains a cycle.",
                recommendation_run_id=cycle[0] if cycle else None,
                successor_recommendation_run_ids=cycle,
                metadata_json={"cycle_recommendation_run_ids": cycle},
            )
        )
    return issues


def _active_successors_by_source(
    nodes: Sequence[RecommendationChainRunNode],
) -> dict[int, list[int]]:
    successors_by_source: dict[int, list[int]] = {}
    for node in nodes:
        source_id = node.source_recommendation_run_id
        if source_id is None:
            continue
        successors_by_source.setdefault(source_id, []).append(node.recommendation_run_id)
    return {
        source_id: sorted(set(successor_ids))
        for source_id, successor_ids in successors_by_source.items()
    }


def _cycle_paths(edges: Mapping[int, Sequence[int]]) -> list[list[int]]:
    cycles: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()

    def visit(node_id: int, path: list[int]) -> None:
        if node_id in path:
            cycle = path[path.index(node_id) :] + [node_id]
            key = _canonical_cycle_key(cycle)
            if key not in seen:
                seen.add(key)
                cycles.append(cycle)
            return
        for successor_id in edges.get(node_id, []):
            visit(successor_id, [*path, node_id])

    for node_id in sorted(edges):
        visit(node_id, [])
    return cycles


def _canonical_cycle_key(cycle: Sequence[int]) -> tuple[int, ...]:
    if len(cycle) <= 1:
        return tuple(cycle)
    body = list(cycle[:-1])
    rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
    return min(rotations)


def _leaf_run_ids(nodes: Sequence[RecommendationChainRunNode]) -> list[int]:
    source_ids = set(_active_source_run_ids(nodes))
    return [
        node.recommendation_run_id
        for node in nodes
        if node.recommendation_run_id not in source_ids
    ]


def _root_run_ids(nodes: Sequence[RecommendationChainRunNode]) -> list[int]:
    return [
        node.recommendation_run_id
        for node in nodes
        if node.source_recommendation_run_id is None
    ]


def _active_source_run_ids(nodes: Sequence[RecommendationChainRunNode]) -> list[int]:
    return sorted(
        {
            node.source_recommendation_run_id
            for node in nodes
            if node.source_recommendation_run_id is not None
        }
    )


def _chain_node_from_row(row: DatabaseRow) -> RecommendationChainRunNode:
    explanation_json = _json_object(row.get("explanation_json"))
    successor_trace = _successor_recompute_trace(explanation_json)
    return RecommendationChainRunNode(
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        as_of_time_utc=_datetime(row["as_of_time_utc"]),
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=_mode(row["mode"]),
        status=str(row["status"]),
        selected_fixture_ids=_string_list(row.get("selected_fixture_ids_json")),
        locked_fixture_ids=_string_list(row.get("locked_fixture_ids_json")),
        source_recommendation_run_id=_optional_positive_int(
            successor_trace.get("source_recommendation_run_id")
        ),
        source_run_key=_optional_str(successor_trace.get("source_run_key")),
        created_at=_datetime(row["created_at"]),
    )


def _successor_recompute_trace(
    explanation_json: Mapping[str, object],
) -> dict[str, object]:
    internal_trace = explanation_json.get("internal_trace")
    if not isinstance(internal_trace, Mapping):
        return {}
    successor_recompute = internal_trace.get("successor_recompute")
    if not isinstance(successor_recompute, Mapping):
        return {}
    return {str(key): value for key, value in successor_recompute.items()}


def _mode(value: object) -> RecommendationMode:
    text = str(value)
    if text not in {"single", "multiple"}:
        raise ValueError(f"unsupported recommendation mode: {text}")
    return text  # type: ignore[return-value]


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, dict):
            return dict(loaded)
        raise ValueError("expected JSON object")
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"expected JSON object, got {type(value).__name__}")


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, list):
            return list(loaded)
        raise ValueError("expected JSON array")
    if isinstance(value, list | tuple):
        return list(value)
    raise ValueError(f"expected JSON array, got {type(value).__name__}")


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_array(value)]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


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


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _dedupe_ints(values: Iterable[int]) -> list[int]:
    result: list[int] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result
