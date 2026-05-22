from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.recommendations import (
    RecommendationLifecycleState,
    transition_recommendation_status,
)


def test_recommendation_lifecycle_allows_current_to_locked_transition() -> None:
    state = RecommendationLifecycleState(
        recommendation_key="rec-6x1-2026-05-02",
        revision_id="rev-001",
        status="current",
        created_at_utc=datetime(2026, 5, 2, 10, tzinfo=UTC),
        updated_at_utc=datetime(2026, 5, 2, 10, tzinfo=UTC),
        locked_fixture_ids=["A", "B"],
    )

    next_state, event = transition_recommendation_status(
        state,
        to_status="locked",
        event_time_utc=datetime(2026, 5, 2, 11, tzinfo=UTC),
        reason_code="user_locked_early_legs",
    )

    assert next_state.status == "locked"
    assert next_state.reason_codes == ["user_locked_early_legs"]
    assert event.from_status == "current"
    assert event.to_status == "locked"


def test_recommendation_lifecycle_rejects_settled_to_current_transition() -> None:
    state = RecommendationLifecycleState(
        recommendation_key="rec-2x1-2026-05-02",
        revision_id="rev-002",
        status="settled",
        created_at_utc=datetime(2026, 5, 2, 10, tzinfo=UTC),
        updated_at_utc=datetime(2026, 5, 3, 10, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="invalid recommendation lifecycle transition"):
        transition_recommendation_status(
            state,
            to_status="current",
            event_time_utc=datetime(2026, 5, 3, 11, tzinfo=UTC),
            reason_code="cannot_reopen_settled_recommendation",
        )
