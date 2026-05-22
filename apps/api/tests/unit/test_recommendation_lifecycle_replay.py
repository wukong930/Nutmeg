from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PersistedRecommendationLifecycleEventSnapshot,
    PersistedRecommendationLifecycleReplayQueryOptions,
    PersistedRecommendationLockedLegSnapshot,
    PersistedRecommendationRunSnapshot,
    PostgresPersistedRecommendationLifecycleReplayRepository,
    RecommendationCandidate,
    build_persisted_recommendation_lifecycle_replay,
    build_prematch_backtest_checkpoints_from_persisted_snapshots,
)
from nutmeg.recommendations.incidents import RecommendationProviderIncidentEventRecord
from nutmeg.recommendations.lifecycle_replay import (
    LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_POOL_ITEMS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
    LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
)


class FakePersistedLifecycleDatabase:
    def __init__(
        self,
        *,
        run_rows: Sequence[DatabaseRow],
        candidate_rows: Sequence[DatabaseRow],
        event_rows: Sequence[DatabaseRow],
        locked_leg_rows: Sequence[DatabaseRow],
        pool_snapshot_rows: Sequence[DatabaseRow] = (),
        pool_item_rows: Sequence[DatabaseRow] = (),
    ) -> None:
        self.run_rows = list(run_rows)
        self.candidate_rows = list(candidate_rows)
        self.event_rows = list(event_rows)
        self.locked_leg_rows = list(locked_leg_rows)
        self.pool_snapshot_rows = list(pool_snapshot_rows)
        self.pool_item_rows = list(pool_item_rows)
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY:
            return self.run_rows
        if query == LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY:
            return self.candidate_rows
        if query == LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY:
            return self.event_rows
        if query == LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY:
            return self.locked_leg_rows
        if query == LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY:
            return self.pool_snapshot_rows
        if query == LIST_PERSISTED_RECOMMENDATION_POOL_ITEMS_FOR_REPLAY_QUERY:
            return self.pool_item_rows
        raise AssertionError(f"unexpected query: {query}")


def test_persisted_lifecycle_replay_tracks_changes_locks_and_incidents() -> None:
    snapshots = [
        _snapshot(
            1,
            "run-1",
            _dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
            events=[
                _event(101, 1, "recommendation_generated", _dt(2026, 5, 1, 10))
            ],
        ),
        _snapshot(
            2,
            "run-2",
            _dt(2026, 5, 1, 16),
            selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
            locked_fixture_ids=["A", "B"],
            locked_legs=[_locked_leg(201, 2, "A"), _locked_leg(202, 2, "B")],
            events=[_event(102, 2, "user_locked_leg", _dt(2026, 5, 1, 16))],
            selected_candidates=[
                _candidate("A", kickoff_time_utc=_dt(2026, 5, 1, 14)),
                _candidate("B", kickoff_time_utc=_dt(2026, 5, 1, 15)),
                _candidate("C", kickoff_time_utc=_dt(2026, 5, 2, 18)),
                _candidate("D", kickoff_time_utc=_dt(2026, 5, 2, 20)),
                _candidate("E", kickoff_time_utc=_dt(2026, 5, 3, 18)),
                _candidate("F", kickoff_time_utc=_dt(2026, 5, 3, 20)),
            ],
        ),
        _snapshot(
            3,
            "run-3",
            _dt(2026, 5, 1, 19),
            selected_fixture_ids=["A", "B", "C", "D", "G", "H"],
            locked_fixture_ids=["A", "B"],
            locked_legs=[_locked_leg(203, 3, "A"), _locked_leg(204, 3, "B")],
            events=[
                _event(
                    103,
                    3,
                    "provider_incident_invalidated_fixture",
                    _dt(2026, 5, 1, 18),
                    metadata_json={
                        "excluded_fixture_ids": ["E", "F"],
                        "incident_notes": {"E": "late_lineup_risk"},
                    },
                )
            ],
        ),
    ]

    result = build_persisted_recommendation_lifecycle_replay(snapshots)

    assert result.stages[0].event_codes == [
        "initial_persisted_recommendation",
        "remaining_fixtures_continue",
    ]
    assert result.stages[1].event_codes == [
        "persisted_recommendation_unchanged",
        "locked_fixtures_preserved",
        "started_locked_fixtures_retained",
        "remaining_fixtures_continue",
        "user_lock_event_recorded",
    ]
    assert result.stages[1].started_locked_fixture_ids == ["A", "B"]
    assert result.stages[1].continuation_fixture_ids == ["C", "D", "E", "F"]
    assert result.stages[1].remaining_open_leg_count == 4
    assert result.stages[2].changed_fixture_ids == ["E", "F", "G", "H"]
    assert result.stages[2].incident_fixture_ids == ["E", "F"]
    assert result.stages[2].continuation_fixture_ids == ["C", "D", "G", "H"]
    assert "incident_exclusion_observed" in result.stages[2].event_codes
    assert result.stages[2].explanation_json["incident_notes"] == {
        "E": "late_lineup_risk"
    }
    assert result.summary_json["changed_stage_count"] == 1
    assert result.summary_json["locked_preservation_stage_count"] == 2
    assert result.summary_json["started_locked_stage_count"] == 1
    assert result.summary_json["continuation_stage_count"] == 3
    assert result.summary_json["final_selected_fixture_ids"] == [
        "A",
        "B",
        "C",
        "D",
        "G",
        "H",
    ]
    assert result.summary_json["final_continuation_fixture_ids"] == [
        "C",
        "D",
        "G",
        "H",
    ]
    assert result.summary_json["final_remaining_open_leg_count"] == 4


def test_persisted_lifecycle_replay_warns_when_locked_leg_is_not_preserved() -> None:
    snapshot = _snapshot(
        1,
        "run-1",
        _dt(2026, 5, 1, 10),
        selected_fixture_ids=["B", "C"],
        locked_fixture_ids=["A"],
        locked_legs=[_locked_leg(201, 1, "A")],
    )

    result = build_persisted_recommendation_lifecycle_replay([snapshot])

    assert result.stages[0].missing_locked_fixture_ids == ["A"]
    assert result.stages[0].warnings == ["locked_fixture_not_preserved:A"]
    assert "locked_fixtures_missing" in result.stages[0].event_codes
    assert result.summary_json["warning_count"] == 1


def test_persisted_lifecycle_replay_exposes_successor_source_evidence() -> None:
    snapshot = _snapshot(
        2,
        "run-2",
        _dt(2026, 5, 1, 12),
        selected_fixture_ids=["A", "B", "C", "D"],
        locked_fixture_ids=["A"],
        explanation_json={
            "internal_trace": {
                "successor_recompute": {
                    "source_recommendation_run_id": 1,
                    "source_run_key": "run-1",
                    "source_selected_fixture_ids": ["A", "B", "OLD_C", "OLD_D"],
                    "locked_fixture_ids": ["A"],
                    "calculation_basis": "locked_leg_successor_recompute_v3_1",
                }
            }
        },
    )

    result = build_persisted_recommendation_lifecycle_replay([snapshot])

    assert "successor_recompute_generated" in result.stages[0].event_codes
    assert result.stages[0].explanation_json["successor_recompute"] == {
        "source_recommendation_run_id": 1,
        "source_run_key": "run-1",
        "source_selected_fixture_ids": ["A", "B", "OLD_C", "OLD_D"],
        "locked_fixture_ids": ["A"],
        "calculation_basis": "locked_leg_successor_recompute_v3_1",
    }
    assert result.summary_json["successor_recompute_stage_count"] == 1
    assert result.summary_json["final_successor_source_recommendation_run_id"] == 1


def test_persisted_lifecycle_repository_groups_runs_children_and_builds_checkpoints() -> None:
    database = FakePersistedLifecycleDatabase(
        run_rows=[
            _run_row(11, "run-11", _dt(2026, 5, 1, 10), ["A", "B"], ["A"]),
            _run_row(12, "run-12", _dt(2026, 5, 1, 12), ["A", "C"], ["A"]),
        ],
        candidate_rows=[
            _candidate_row(301, 11, "A", "home_win", locked=True),
            _candidate_row(302, 11, "B", "draw"),
            _candidate_row(303, 12, "A", "home_win", locked=True),
            _candidate_row(304, 12, "C", "away_win"),
        ],
        event_rows=[
            _event_row(401, 11, "recommendation_generated"),
            _event_row(
                402,
                12,
                "provider_incident_invalidated_fixture",
                metadata_json={"excluded_fixture_ids": ["B"]},
            ),
        ],
        locked_leg_rows=[_locked_leg_row(501, 11, "A"), _locked_leg_row(502, 12, "A")],
    )
    repository = PostgresPersistedRecommendationLifecycleReplayRepository(database)

    snapshots = repository.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 2, 0),
            pass_type="2x1",
            mode="single",
            strategy="accuracy_first",
            limit=50,
        )
    )
    checkpoints = build_prematch_backtest_checkpoints_from_persisted_snapshots(snapshots)

    assert [snapshot.recommendation_run_id for snapshot in snapshots] == [11, 12]
    assert [candidate.fixture_id for candidate in snapshots[0].selected_candidates] == [
        "A",
        "B",
    ]
    assert snapshots[1].lifecycle_events[0].reason_code == (
        "provider_incident_invalidated_fixture"
    )
    assert snapshots[1].locked_legs[0].fixture_id == "A"
    assert checkpoints[1].checkpoint_id == "run-12"
    assert checkpoints[1].locked_fixture_ids == ["A"]
    assert checkpoints[1].excluded_fixture_ids == ["B"]
    assert [query for query, _params in database.fetch_all_calls] == [
        LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
    ]
    run_params = database.fetch_all_calls[0][1]
    assert run_params["pass_type"] == "2x1"
    assert run_params["mode"] == "single"
    assert run_params["strategy"] == "accuracy_first"
    assert run_params["limit"] == 50


def test_persisted_checkpoints_use_candidate_pool_and_provider_incidents() -> None:
    database = FakePersistedLifecycleDatabase(
        run_rows=[_run_row(11, "run-11", _dt(2026, 5, 1, 10), ["A", "B"], [])],
        candidate_rows=[
            _candidate_row(301, 11, "A", "home_win"),
            _candidate_row(302, 11, "B", "draw"),
        ],
        event_rows=[],
        locked_leg_rows=[],
        pool_snapshot_rows=[_pool_snapshot_row(701, 11, "run-11")],
        pool_item_rows=[
            _pool_item_row(801, 701, "A", "home_win", selected=True),
            _pool_item_row(802, 701, "B", "draw", selected=True),
            _pool_item_row(803, 701, "C", "away_win"),
        ],
    )
    repository = PostgresPersistedRecommendationLifecycleReplayRepository(database)
    snapshots = repository.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 2, 0),
        )
    )
    incident = _provider_incident(
        "incident-1",
        event_time_utc=_dt(2026, 5, 1, 9),
        fixture_id="C",
        summary="late_lineup_risk",
    )

    checkpoints = build_prematch_backtest_checkpoints_from_persisted_snapshots(
        snapshots,
        provider_incidents=[incident],
    )

    assert [candidate.fixture_id for candidate in checkpoints[0].candidates] == [
        "A",
        "B",
        "C",
    ]
    assert checkpoints[0].excluded_fixture_ids == ["C"]
    assert checkpoints[0].incident_notes == {"C": "late_lineup_risk"}
    assert checkpoints[0].metadata_json["candidate_scope"] == "persisted_candidate_pool"
    assert checkpoints[0].metadata_json["candidate_pool_snapshot_id"] == 701
    assert checkpoints[0].metadata_json["provider_incident_event_keys"] == ["incident-1"]
    assert [query for query, _params in database.fetch_all_calls] == [
        LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
        LIST_PERSISTED_RECOMMENDATION_POOL_ITEMS_FOR_REPLAY_QUERY,
    ]


def _snapshot(
    recommendation_run_id: int,
    run_key: str,
    as_of_time_utc: datetime,
    *,
    selected_fixture_ids: list[str],
    locked_fixture_ids: list[str] | None = None,
    events: list[PersistedRecommendationLifecycleEventSnapshot] | None = None,
    locked_legs: list[PersistedRecommendationLockedLegSnapshot] | None = None,
    selected_candidates: list[RecommendationCandidate] | None = None,
    explanation_json: dict[str, object] | None = None,
) -> PersistedRecommendationRunSnapshot:
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=as_of_time_utc,
        strategy="accuracy_first",
        pass_type="6x1",
        mode="single",
        status="current",
        unit_stake=2.0,
        max_budget=20.0,
        candidate_count=len(selected_fixture_ids),
        excluded_candidate_count=0,
        selected_fixture_ids=selected_fixture_ids,
        locked_fixture_ids=locked_fixture_ids or [],
        total_score=0.82,
        explanation_json=explanation_json or {},
        source="recommendation_engine_v3_1",
        created_at=as_of_time_utc,
        selected_candidates=selected_candidates or [],
        lifecycle_events=events or [],
        locked_legs=locked_legs or [],
    )


def _candidate(
    fixture_id: str,
    *,
    kickoff_time_utc: datetime,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome="home_win",
        probability=0.62,
        decimal_odds=1.85,
        market_probability=0.54,
        data_quality_score=88.0,
        model_confidence_score=0.82,
        calibration_score=0.80,
        odds_stability_score=0.74,
        prediction_time_utc=_dt(2026, 5, 1, 9),
        kickoff_time_utc=kickoff_time_utc,
    )


def _event(
    event_id: int,
    recommendation_run_id: int,
    reason_code: str,
    event_time_utc: datetime,
    *,
    metadata_json: dict[str, object] | None = None,
) -> PersistedRecommendationLifecycleEventSnapshot:
    return PersistedRecommendationLifecycleEventSnapshot(
        recommendation_lifecycle_event_id=event_id,
        recommendation_run_id=recommendation_run_id,
        recommendation_key=f"run-{recommendation_run_id}",
        from_status="current",
        to_status="current",
        reason_code=reason_code,
        event_time_utc=event_time_utc,
        metadata_json=metadata_json or {},
        created_at=event_time_utc,
    )


def _locked_leg(
    locked_leg_id: int,
    recommendation_run_id: int,
    fixture_id: str,
) -> PersistedRecommendationLockedLegSnapshot:
    locked_at = _dt(2026, 5, 1, 11)
    return PersistedRecommendationLockedLegSnapshot(
        recommendation_locked_leg_id=locked_leg_id,
        recommendation_run_id=recommendation_run_id,
        fixture_id=fixture_id,
        market_type="1x2",
        outcome="home_win",
        locked_at_utc=locked_at,
        status="locked",
        created_at=locked_at,
    )


def _run_row(
    recommendation_run_id: int,
    run_key: str,
    as_of_time_utc: datetime,
    selected_fixture_ids: list[str],
    locked_fixture_ids: list[str],
) -> DatabaseRow:
    return {
        "recommendation_run_id": recommendation_run_id,
        "run_key": run_key,
        "as_of_time_utc": as_of_time_utc,
        "strategy": "accuracy_first",
        "pass_type": "2x1",
        "mode": "single",
        "status": "current",
        "unit_stake": 2,
        "max_budget": 20,
        "candidate_count": len(selected_fixture_ids),
        "excluded_candidate_count": 0,
        "selected_fixture_ids_json": selected_fixture_ids,
        "locked_fixture_ids_json": locked_fixture_ids,
        "total_score": 0.82,
        "parlay_evaluation_json": {"total_stake": 2},
        "explanation_json": {},
        "source": "recommendation_engine_v3_1",
        "created_at": as_of_time_utc,
    }


def _candidate_row(
    candidate_id: int,
    recommendation_run_id: int,
    fixture_id: str,
    outcome: str,
    *,
    locked: bool = False,
) -> DatabaseRow:
    return {
        "recommendation_candidate_id": candidate_id,
        "recommendation_run_id": recommendation_run_id,
        "fixture_id": fixture_id,
        "market_type": "1x2",
        "line": None,
        "side": None,
        "outcome": outcome,
        "probability": 0.62,
        "decimal_odds": 1.85,
        "market_probability": 0.54,
        "model_edge": 0.08,
        "data_quality_score": 88,
        "model_confidence_score": 0.82,
        "calibration_score": 0.80,
        "upset_protection_score": 0.12,
        "odds_stability_score": 0.74,
        "volatility_penalty": 0.04,
        "model_version": "poisson-m1.0.0",
        "prediction_snapshot_id": 901,
        "prediction_time_utc": _dt(2026, 5, 1, 9),
        "kickoff_time_utc": _dt(2026, 5, 2, 18),
        "recommendation_score": 0.81,
        "selected": True,
        "locked": locked,
        "metadata_json": {"component_scores": {"probability": 0.62}},
        "created_at": _dt(2026, 5, 1, 10),
    }


def _pool_snapshot_row(
    pool_snapshot_id: int,
    recommendation_run_id: int,
    run_key: str,
) -> DatabaseRow:
    return {
        "recommendation_candidate_pool_snapshot_id": pool_snapshot_id,
        "recommendation_run_id": recommendation_run_id,
        "run_key": run_key,
        "as_of_time_utc": _dt(2026, 5, 1, 10),
        "strategy": "accuracy_first",
        "pass_type": "2x1",
        "mode": "single",
        "candidate_count": 3,
        "selected_candidate_count": 2,
        "excluded_candidate_count": 0,
        "candidate_query_json": {"candidate_limit": 200},
        "source": "recommendation_engine_v3_1",
        "created_at": _dt(2026, 5, 1, 10),
    }


def _pool_item_row(
    pool_item_id: int,
    pool_snapshot_id: int,
    fixture_id: str,
    outcome: str,
    *,
    selected: bool = False,
    locked: bool = False,
) -> DatabaseRow:
    return {
        "recommendation_candidate_pool_item_id": pool_item_id,
        "recommendation_candidate_pool_snapshot_id": pool_snapshot_id,
        "fixture_id": fixture_id,
        "market_type": "1x2",
        "line": None,
        "side": None,
        "outcome": outcome,
        "probability": 0.61,
        "decimal_odds": 1.9,
        "market_probability": 0.53,
        "model_edge": 0.08,
        "data_quality_score": 87,
        "model_confidence_score": 0.81,
        "calibration_score": 0.79,
        "upset_protection_score": 0.10,
        "odds_stability_score": 0.72,
        "volatility_penalty": 0.05,
        "model_version": "poisson-m1.0.0",
        "prediction_snapshot_id": 901,
        "prediction_time_utc": _dt(2026, 5, 1, 9),
        "kickoff_time_utc": _dt(2026, 5, 2, 18),
        "selected": selected,
        "locked": locked,
        "metadata_json": {"source": "unit-test-pool"},
        "created_at": _dt(2026, 5, 1, 10),
    }


def _provider_incident(
    provider_incident_key: str,
    *,
    event_time_utc: datetime,
    fixture_id: str,
    summary: str,
) -> RecommendationProviderIncidentEventRecord:
    return RecommendationProviderIncidentEventRecord(
        recommendation_provider_incident_event_id=601,
        provider_incident_key=provider_incident_key,
        provider_name="fixture-feed",
        fixture_id=fixture_id,
        competition_id="EPL",
        incident_type="lineup_update",
        severity="warning",
        event_time_utc=event_time_utc,
        observed_at_utc=event_time_utc,
        status="open",
        affects_recommendations=True,
        excluded_fixture_ids=[],
        summary=summary,
        created_at=event_time_utc,
        updated_at=event_time_utc,
    )


def _event_row(
    event_id: int,
    recommendation_run_id: int,
    reason_code: str,
    *,
    metadata_json: dict[str, object] | None = None,
) -> DatabaseRow:
    event_time = _dt(2026, 5, 1, 11)
    return {
        "recommendation_lifecycle_event_id": event_id,
        "recommendation_run_id": recommendation_run_id,
        "recommendation_key": f"run-{recommendation_run_id}",
        "from_status": "current",
        "to_status": "current",
        "reason_code": reason_code,
        "event_time_utc": event_time,
        "metadata_json": metadata_json or {},
        "created_at": event_time,
    }


def _locked_leg_row(
    locked_leg_id: int,
    recommendation_run_id: int,
    fixture_id: str,
) -> DatabaseRow:
    locked_at = _dt(2026, 5, 1, 11)
    return {
        "recommendation_locked_leg_id": locked_leg_id,
        "recommendation_run_id": recommendation_run_id,
        "fixture_id": fixture_id,
        "market_type": "1x2",
        "outcome": "home_win",
        "locked_at_utc": locked_at,
        "status": "locked",
        "metadata_json": {"operator": "unit-test"},
        "created_at": locked_at,
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
