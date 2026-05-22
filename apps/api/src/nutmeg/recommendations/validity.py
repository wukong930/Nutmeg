from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

type RecommendationValidityStatus = Literal[
    "valid",
    "valid_locked",
    "superseded",
    "invalidated",
    "historical",
    "expired_kickoff",
    "stale_incident",
]


class RecommendationValidityEventNode(BaseModel):
    reason_code: str
    event_time_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationValidityRunNode(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    status: str
    as_of_time_utc: datetime
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    fixture_kickoff_times_utc: dict[str, datetime] = Field(default_factory=dict)
    source_recommendation_run_id: int | None = Field(default=None, gt=0)
    lifecycle_events: list[RecommendationValidityEventNode] = Field(default_factory=list)


class RecommendationValidityWindow(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    lifecycle_status: str
    validity_status: RecommendationValidityStatus
    valid_from_utc: datetime
    valid_until_utc: datetime | None = None
    can_show_as_current_answer: bool
    requires_successor_recompute: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    started_fixture_ids: list[str] = Field(default_factory=list)
    started_locked_fixture_ids: list[str] = Field(default_factory=list)
    remaining_open_fixture_ids: list[str] = Field(default_factory=list)
    successor_recommendation_run_ids: list[int] = Field(default_factory=list)
    incident_fixture_ids: list[str] = Field(default_factory=list)


class RecommendationValidityWindowReport(BaseModel):
    as_of_time_utc: datetime
    windows: list[RecommendationValidityWindow] = Field(default_factory=list)
    current_answer_recommendation_run_ids: list[int] = Field(default_factory=list)
    stale_recommendation_run_ids: list[int] = Field(default_factory=list)
    superseded_recommendation_run_ids: list[int] = Field(default_factory=list)
    invalidated_recommendation_run_ids: list[int] = Field(default_factory=list)
    expired_kickoff_recommendation_run_ids: list[int] = Field(default_factory=list)
    stale_incident_recommendation_run_ids: list[int] = Field(default_factory=list)
    successor_recompute_required_recommendation_run_ids: list[int] = Field(
        default_factory=list
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_recommendation_validity_window_report(
    nodes: Sequence[RecommendationValidityRunNode],
    *,
    as_of_time_utc: datetime,
) -> RecommendationValidityWindowReport:
    normalized_as_of = _aware_utc(as_of_time_utc)
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (_aware_utc(node.as_of_time_utc), node.recommendation_run_id),
    )
    successors_by_source = _active_successors_by_source(ordered_nodes)
    windows = [
        _validity_window(
            node,
            as_of_time_utc=normalized_as_of,
            successor_run_ids=successors_by_source.get(
                node.recommendation_run_id,
                [],
            ),
            successor_as_of_times=[
                _aware_utc(successor.as_of_time_utc)
                for successor in ordered_nodes
                if successor.recommendation_run_id
                in successors_by_source.get(node.recommendation_run_id, [])
            ],
        )
        for node in ordered_nodes
    ]
    current_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.can_show_as_current_answer
    ]
    stale_run_ids = [
        window.recommendation_run_id
        for window in windows
        if not window.can_show_as_current_answer
        and window.validity_status
        in {"superseded", "invalidated", "expired_kickoff", "stale_incident"}
    ]
    superseded_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.validity_status == "superseded"
    ]
    invalidated_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.validity_status == "invalidated"
    ]
    expired_kickoff_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.validity_status == "expired_kickoff"
    ]
    stale_incident_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.validity_status == "stale_incident"
    ]
    recompute_required_run_ids = [
        window.recommendation_run_id
        for window in windows
        if window.requires_successor_recompute
    ]
    status_counts = _validity_status_counts(windows)
    summary = {
        "run_count": len(windows),
        "current_answer_run_count": len(current_run_ids),
        "stale_run_count": len(stale_run_ids),
        "status_counts": status_counts,
        "current_answer_recommendation_run_ids": current_run_ids,
        "stale_recommendation_run_ids": stale_run_ids,
        "superseded_recommendation_run_ids": superseded_run_ids,
        "invalidated_recommendation_run_ids": invalidated_run_ids,
        "expired_kickoff_recommendation_run_ids": expired_kickoff_run_ids,
        "stale_incident_recommendation_run_ids": stale_incident_run_ids,
        "successor_recompute_required_recommendation_run_ids": (
            recompute_required_run_ids
        ),
        "calculation_basis": "recommendation_validity_window_v3_1",
    }
    return RecommendationValidityWindowReport(
        as_of_time_utc=normalized_as_of,
        windows=windows,
        current_answer_recommendation_run_ids=current_run_ids,
        stale_recommendation_run_ids=stale_run_ids,
        superseded_recommendation_run_ids=superseded_run_ids,
        invalidated_recommendation_run_ids=invalidated_run_ids,
        expired_kickoff_recommendation_run_ids=expired_kickoff_run_ids,
        stale_incident_recommendation_run_ids=stale_incident_run_ids,
        successor_recompute_required_recommendation_run_ids=recompute_required_run_ids,
        summary_json=summary,
    )


def _validity_window(
    node: RecommendationValidityRunNode,
    *,
    as_of_time_utc: datetime,
    successor_run_ids: Sequence[int],
    successor_as_of_times: Sequence[datetime],
) -> RecommendationValidityWindow:
    selected_fixture_ids = _dedupe_strings(node.selected_fixture_ids)
    locked_fixture_ids = _dedupe_strings(node.locked_fixture_ids)
    kickoff_times = {
        fixture_id: _aware_utc(kickoff_time)
        for fixture_id, kickoff_time in node.fixture_kickoff_times_utc.items()
        if fixture_id in selected_fixture_ids
    }
    started_fixture_ids = [
        fixture_id
        for fixture_id in selected_fixture_ids
        if kickoff_times.get(fixture_id) is not None
        and kickoff_times[fixture_id] <= as_of_time_utc
    ]
    started_locked_fixture_ids = [
        fixture_id for fixture_id in started_fixture_ids if fixture_id in locked_fixture_ids
    ]
    remaining_open_fixture_ids = [
        fixture_id for fixture_id in selected_fixture_ids if fixture_id not in started_fixture_ids
    ]
    incident = _incident_context(node)
    first_kickoff = _first_datetime(kickoff_times.values())
    first_started_kickoff = _first_datetime(
        kickoff_times[fixture_id]
        for fixture_id in started_fixture_ids
        if fixture_id in kickoff_times
    )
    first_successor_time = _first_datetime(successor_as_of_times)

    status: RecommendationValidityStatus
    reason_codes: list[str]
    valid_until_utc: datetime | None
    if node.status == "invalidated":
        status = "invalidated"
        reason_codes = ["recommendation_status_invalidated"]
        valid_until_utc = _last_invalidation_time(node) or first_kickoff
    elif successor_run_ids or node.status == "superseded":
        status = "superseded"
        reason_codes = ["successor_recommendation_generated"]
        valid_until_utc = first_successor_time or first_kickoff
    elif incident.affected:
        status = "stale_incident"
        reason_codes = ["recommendation_stale_due_to_provider_incident"]
        valid_until_utc = incident.first_event_time_utc or first_kickoff
    elif started_fixture_ids:
        status = "expired_kickoff"
        reason_codes = ["recommendation_expired_after_fixture_kickoff"]
        valid_until_utc = first_started_kickoff or first_kickoff
    elif node.status in {"confirmed_manual", "live", "settled"}:
        status = "historical"
        reason_codes = [f"recommendation_status_{node.status}"]
        valid_until_utc = first_kickoff
    elif node.status == "locked":
        status = "valid_locked"
        reason_codes = ["recommendation_valid_with_locked_legs"]
        valid_until_utc = first_kickoff
    else:
        status = "valid"
        reason_codes = ["recommendation_valid_before_kickoff"]
        valid_until_utc = first_kickoff

    requires_successor_recompute = (
        status in {"expired_kickoff", "stale_incident"}
        and bool(remaining_open_fixture_ids)
        and node.status in {"current", "locked"}
    )
    return RecommendationValidityWindow(
        recommendation_run_id=node.recommendation_run_id,
        run_key=node.run_key,
        lifecycle_status=node.status,
        validity_status=status,
        valid_from_utc=_aware_utc(node.as_of_time_utc),
        valid_until_utc=valid_until_utc,
        can_show_as_current_answer=status in {"valid", "valid_locked"},
        requires_successor_recompute=requires_successor_recompute,
        reason_codes=reason_codes,
        selected_fixture_ids=selected_fixture_ids,
        locked_fixture_ids=locked_fixture_ids,
        started_fixture_ids=started_fixture_ids,
        started_locked_fixture_ids=started_locked_fixture_ids,
        remaining_open_fixture_ids=remaining_open_fixture_ids,
        successor_recommendation_run_ids=list(successor_run_ids),
        incident_fixture_ids=incident.fixture_ids,
    )


class _IncidentContext(BaseModel):
    affected: bool
    fixture_ids: list[str] = Field(default_factory=list)
    first_event_time_utc: datetime | None = None


def _incident_context(node: RecommendationValidityRunNode) -> _IncidentContext:
    selected_fixture_ids = set(node.selected_fixture_ids)
    incident_fixture_ids: list[str] = []
    event_times: list[datetime] = []
    generic_incident_observed = False
    for event in node.lifecycle_events:
        reason_code = event.reason_code.lower()
        metadata_fixture_ids = _metadata_fixture_ids(event.metadata_json)
        if (
            "incident" not in reason_code
            and "invalidated" not in reason_code
            and not metadata_fixture_ids
        ):
            continue
        matched_fixture_ids = [
            fixture_id
            for fixture_id in metadata_fixture_ids
            if fixture_id in selected_fixture_ids
        ]
        if matched_fixture_ids:
            incident_fixture_ids.extend(matched_fixture_ids)
            event_times.append(_aware_utc(event.event_time_utc))
            continue
        if "incident" in reason_code or "invalidated" in reason_code:
            generic_incident_observed = True
            event_times.append(_aware_utc(event.event_time_utc))
    deduped_fixture_ids = _dedupe_strings(incident_fixture_ids)
    return _IncidentContext(
        affected=bool(deduped_fixture_ids) or generic_incident_observed,
        fixture_ids=deduped_fixture_ids,
        first_event_time_utc=_first_datetime(event_times),
    )


def _active_successors_by_source(
    nodes: Sequence[RecommendationValidityRunNode],
) -> dict[int, list[int]]:
    node_ids = {node.recommendation_run_id for node in nodes}
    successors_by_source: dict[int, list[int]] = {}
    for node in nodes:
        if node.status == "invalidated" or node.source_recommendation_run_id is None:
            continue
        if node.source_recommendation_run_id not in node_ids:
            continue
        successors_by_source.setdefault(node.source_recommendation_run_id, []).append(
            node.recommendation_run_id
        )
    return {
        source_id: _dedupe_ints(successor_ids)
        for source_id, successor_ids in sorted(successors_by_source.items())
    }


def _metadata_fixture_ids(metadata_json: Mapping[str, object]) -> list[str]:
    fixture_ids: list[str] = []
    for key in (
        "fixture_id",
        "canonical_fixture_id",
        "excluded_fixture_ids",
        "invalidated_fixture_ids",
        "affected_fixture_ids",
    ):
        value = metadata_json.get(key)
        if isinstance(value, str):
            fixture_ids.append(value)
        elif isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            fixture_ids.extend(str(item) for item in value if item is not None)
    for nested_key in ("incident", "provider_incidents", "lifecycle"):
        nested = metadata_json.get(nested_key)
        if isinstance(nested, Mapping):
            fixture_ids.extend(_metadata_fixture_ids(nested))
    return _dedupe_strings(fixture_ids)


def _last_invalidation_time(node: RecommendationValidityRunNode) -> datetime | None:
    invalidation_times = [
        _aware_utc(event.event_time_utc)
        for event in node.lifecycle_events
        if event.reason_code
        in {
            "recommendation_invalidated",
            "provider_incident_invalidated_fixture",
        }
        or "invalidated" in event.reason_code
    ]
    if not invalidation_times:
        return None
    return max(invalidation_times)


def _validity_status_counts(
    windows: Sequence[RecommendationValidityWindow],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for window in windows:
        counts[window.validity_status] = counts.get(window.validity_status, 0) + 1
    return counts


def _first_datetime(values: Iterable[datetime]) -> datetime | None:
    normalized = [_aware_utc(value) for value in values]
    if not normalized:
        return None
    return min(normalized)


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


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result
