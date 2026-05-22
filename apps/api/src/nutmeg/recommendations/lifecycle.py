from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

type RecommendationLifecycleStatus = Literal[
    "candidate",
    "current",
    "superseded",
    "locked",
    "confirmed_manual",
    "live",
    "settled",
    "invalidated",
]

_ALLOWED_TRANSITIONS: dict[RecommendationLifecycleStatus, set[RecommendationLifecycleStatus]] = {
    "candidate": {"current", "invalidated"},
    "current": {"superseded", "locked", "confirmed_manual", "invalidated"},
    "superseded": {"settled"},
    "locked": {"current", "confirmed_manual", "superseded", "invalidated"},
    "confirmed_manual": {"live", "settled"},
    "live": {"settled"},
    "settled": set(),
    "invalidated": set(),
}


class RecommendationLifecycleState(BaseModel):
    recommendation_key: str
    revision_id: str
    status: RecommendationLifecycleStatus
    created_at_utc: datetime
    updated_at_utc: datetime
    locked_fixture_ids: list[str] = Field(default_factory=list)
    confirmed_fixture_ids: list[str] = Field(default_factory=list)
    supersedes_revision_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationLifecycleEvent(BaseModel):
    recommendation_key: str
    from_status: RecommendationLifecycleStatus
    to_status: RecommendationLifecycleStatus
    event_time_utc: datetime
    reason_code: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


def transition_recommendation_status(
    state: RecommendationLifecycleState,
    *,
    to_status: RecommendationLifecycleStatus,
    event_time_utc: datetime,
    reason_code: str,
    metadata_json: dict[str, object] | None = None,
) -> tuple[RecommendationLifecycleState, RecommendationLifecycleEvent]:
    if to_status not in _ALLOWED_TRANSITIONS[state.status]:
        transition = f"{state.status}->{to_status}"
        raise ValueError(f"invalid recommendation lifecycle transition: {transition}")
    event = RecommendationLifecycleEvent(
        recommendation_key=state.recommendation_key,
        from_status=state.status,
        to_status=to_status,
        event_time_utc=event_time_utc,
        reason_code=reason_code,
        metadata_json=metadata_json or {},
    )
    next_state = state.model_copy(
        deep=True,
        update={
            "status": to_status,
            "updated_at_utc": event_time_utc,
            "reason_codes": [*state.reason_codes, reason_code],
        },
    )
    return next_state, event
