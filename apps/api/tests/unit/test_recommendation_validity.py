from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.recommendations import (
    RecommendationValidityEventNode,
    RecommendationValidityRunNode,
    build_recommendation_validity_window_report,
)


def test_validity_window_keeps_future_current_run_valid_until_first_kickoff() -> None:
    report = build_recommendation_validity_window_report(
        [
            _node(
                1,
                "current",
                selected_fixture_ids=["A", "B"],
                kickoff_times={"A": _dt(2026, 5, 2, 18), "B": _dt(2026, 5, 3, 18)},
            )
        ],
        as_of_time_utc=_dt(2026, 5, 1, 12),
    )

    window = report.windows[0]
    assert window.validity_status == "valid"
    assert window.can_show_as_current_answer is True
    assert window.valid_until_utc == _dt(2026, 5, 2, 18)
    assert report.current_answer_recommendation_run_ids == [1]
    assert report.summary_json["status_counts"] == {"valid": 1}


def test_validity_window_marks_source_superseded_by_active_successor() -> None:
    report = build_recommendation_validity_window_report(
        [
            _node(
                1,
                "current",
                selected_fixture_ids=["A", "B"],
                kickoff_times={"A": _dt(2026, 5, 3, 18), "B": _dt(2026, 5, 3, 20)},
            ),
            _node(
                2,
                "current",
                as_of_time_utc=_dt(2026, 5, 1, 14),
                selected_fixture_ids=["A", "C"],
                kickoff_times={"A": _dt(2026, 5, 3, 18), "C": _dt(2026, 5, 4, 20)},
                source_id=1,
            ),
        ],
        as_of_time_utc=_dt(2026, 5, 1, 15),
    )

    source_window = report.windows[0]
    successor_window = report.windows[1]
    assert source_window.validity_status == "superseded"
    assert source_window.valid_until_utc == _dt(2026, 5, 1, 14)
    assert source_window.successor_recommendation_run_ids == [2]
    assert source_window.can_show_as_current_answer is False
    assert successor_window.validity_status == "valid"
    assert report.superseded_recommendation_run_ids == [1]
    assert report.current_answer_recommendation_run_ids == [2]


def test_validity_window_ignores_invalidated_successor_when_selecting_current_answer() -> None:
    report = build_recommendation_validity_window_report(
        [
            _node(
                1,
                "current",
                selected_fixture_ids=["A", "B"],
                kickoff_times={"A": _dt(2026, 5, 3, 18), "B": _dt(2026, 5, 3, 20)},
            ),
            _node(
                2,
                "invalidated",
                as_of_time_utc=_dt(2026, 5, 1, 14),
                selected_fixture_ids=["A", "C"],
                kickoff_times={"A": _dt(2026, 5, 3, 18), "C": _dt(2026, 5, 4, 20)},
                source_id=1,
            ),
        ],
        as_of_time_utc=_dt(2026, 5, 1, 15),
    )

    assert report.windows[0].validity_status == "valid"
    assert report.windows[1].validity_status == "invalidated"
    assert report.current_answer_recommendation_run_ids == [1]
    assert report.invalidated_recommendation_run_ids == [2]


def test_validity_window_marks_started_locked_run_as_recompute_required() -> None:
    report = build_recommendation_validity_window_report(
        [
            _node(
                1,
                "locked",
                selected_fixture_ids=["A", "B", "C", "D"],
                locked_fixture_ids=["A", "B"],
                kickoff_times={
                    "A": _dt(2026, 5, 1, 18),
                    "B": _dt(2026, 5, 1, 19),
                    "C": _dt(2026, 5, 2, 18),
                    "D": _dt(2026, 5, 2, 20),
                },
            )
        ],
        as_of_time_utc=_dt(2026, 5, 1, 20),
    )

    window = report.windows[0]
    assert window.validity_status == "expired_kickoff"
    assert window.can_show_as_current_answer is False
    assert window.started_locked_fixture_ids == ["A", "B"]
    assert window.remaining_open_fixture_ids == ["C", "D"]
    assert window.requires_successor_recompute is True
    assert report.expired_kickoff_recommendation_run_ids == [1]
    assert report.successor_recompute_required_recommendation_run_ids == [1]


def test_validity_window_marks_selected_fixture_incident_as_stale() -> None:
    report = build_recommendation_validity_window_report(
        [
            _node(
                1,
                "current",
                selected_fixture_ids=["A", "B", "C"],
                kickoff_times={
                    "A": _dt(2026, 5, 3, 18),
                    "B": _dt(2026, 5, 3, 20),
                    "C": _dt(2026, 5, 4, 20),
                },
                events=[
                    RecommendationValidityEventNode(
                        reason_code="provider_incident_invalidated_fixture",
                        event_time_utc=_dt(2026, 5, 1, 16),
                        metadata_json={
                            "excluded_fixture_ids": ["B"],
                            "incident_notes": {"B": "late lineup risk"},
                        },
                    )
                ],
            )
        ],
        as_of_time_utc=_dt(2026, 5, 1, 17),
    )

    window = report.windows[0]
    assert window.validity_status == "stale_incident"
    assert window.valid_until_utc == _dt(2026, 5, 1, 16)
    assert window.incident_fixture_ids == ["B"]
    assert window.requires_successor_recompute is True
    assert report.stale_incident_recommendation_run_ids == [1]
    assert report.current_answer_recommendation_run_ids == []


def _node(
    recommendation_run_id: int,
    status: str,
    *,
    as_of_time_utc: datetime | None = None,
    selected_fixture_ids: list[str],
    locked_fixture_ids: list[str] | None = None,
    kickoff_times: dict[str, datetime],
    source_id: int | None = None,
    events: list[RecommendationValidityEventNode] | None = None,
) -> RecommendationValidityRunNode:
    return RecommendationValidityRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=f"run-{recommendation_run_id}",
        status=status,
        as_of_time_utc=as_of_time_utc or _dt(2026, 5, 1, 12),
        selected_fixture_ids=selected_fixture_ids,
        locked_fixture_ids=locked_fixture_ids or [],
        fixture_kickoff_times_utc=kickoff_times,
        source_recommendation_run_id=source_id,
        lifecycle_events=events or [],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
