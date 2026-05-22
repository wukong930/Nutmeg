from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from nutmeg.recommendations import (
    PersistedRecommendationCandidatePoolSnapshot,
    PersistedRecommendationRunSnapshot,
    RecommendationCandidate,
    RecommendationCoreReplayOptions,
    build_recommendation_core_replay_report,
    run_recommendation_core_replay,
)


def test_core_replay_report_links_lifecycle_replay_to_post_match_evaluation() -> None:
    snapshots = [
        _snapshot(
            1,
            run_key="global_opening",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "B", "C"],
            atomic_fixture_ids=["A", "B", "C"],
        ),
        _snapshot(
            2,
            run_key="global_after_incident",
            as_of_time_utc=_dt(2026, 5, 2, 10),
            selected_fixture_ids=["A", "C", "D"],
            locked_fixture_ids=["A"],
            atomic_fixture_ids=["A", "C", "D"],
            explanation_json={
                "incident_excluded_fixture_ids": ["B"],
                "incident_notes": {"B": "late lineup risk removed from final answer"},
            },
        ),
    ]

    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=[
            _result("A", 2, 0),
            _result("B", 0, 1),
            _result("C", 1, 0),
            _result("D", 3, 1),
        ],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="3x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )

    assert report.report_key.startswith("core_replay:")
    assert report.replay.summary_json["changed_stage_count"] == 1
    assert report.replay.summary_json["incident_stage_count"] == 1
    assert report.replay.final_stage is not None
    assert report.replay.final_stage.selected_fixture_ids == ["A", "C", "D"]
    assert report.evaluations[-1].recommendation_run_id == 2
    assert report.evaluations[-1].evaluation_status == "settled"
    assert report.evaluations[-1].hit is True
    assert report.summary_json["final_hit"] is True
    assert report.summary_json["core_flow_ready"] is True
    assert {check.code: check.status for check in report.checks} == {
        "recommendation_runs_available": "pass",
        "candidate_pool_snapshots_available": "pass",
        "final_recommendation_selected": "pass",
        "locked_fixtures_preserved": "pass",
        "post_match_result_coverage": "pass",
        "post_match_evaluations_settled": "pass",
    }


def test_core_replay_report_warns_when_candidate_pool_or_results_are_missing() -> None:
    snapshot = _snapshot(
        1,
        run_key="missing_pool",
        as_of_time_utc=_dt(2026, 5, 1, 10),
        selected_fixture_ids=["A", "B"],
        atomic_fixture_ids=["A", "B"],
        candidate_pool_candidates=[],
    )

    report = build_recommendation_core_replay_report(
        [snapshot],
        result_rows=[_result("A", 2, 0)],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="2x1",
            mode="single",
        ),
    )

    checks = {check.code: check for check in report.checks}
    assert checks["candidate_pool_snapshots_available"].status == "fail"
    assert checks["post_match_result_coverage"].status == "warn"
    assert checks["post_match_result_coverage"].fixture_ids == ["B"]
    assert checks["post_match_evaluations_settled"].status == "warn"
    assert report.summary_json["core_flow_ready"] is False


def test_core_replay_counts_only_effective_successor_leaf_runs() -> None:
    snapshots = [
        _snapshot(
            1,
            run_key="source_with_locked_legs",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "B", "C"],
            atomic_fixture_ids=["A", "B", "C"],
            locked_fixture_ids=["A"],
        ),
        _snapshot(
            2,
            run_key="successor_after_locked_recompute",
            as_of_time_utc=_dt(2026, 5, 2, 10),
            selected_fixture_ids=["A", "C", "D"],
            atomic_fixture_ids=["A", "C", "D"],
            locked_fixture_ids=["A"],
            explanation_json={
                "internal_trace": {
                    "successor_recompute": {
                        "source_recommendation_run_id": 1,
                        "source_run_key": "source_with_locked_legs",
                        "locked_fixture_ids": ["A"],
                        "calculation_basis": "locked_leg_successor_recompute_v3_1",
                    }
                }
            },
        ),
    ]

    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=[
            _result("A", 2, 0),
            _result("B", 0, 1),
            _result("C", 1, 0),
            _result("D", 3, 1),
        ],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="3x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )

    assert len(report.evaluations) == 2
    assert report.evaluations[0].hit is False
    assert report.evaluations[1].hit is True
    assert report.summary_json["evaluated_run_count"] == 2
    assert report.summary_json["effective_evaluated_run_count"] == 1
    assert report.summary_json["superseded_source_run_count"] == 1
    assert report.summary_json["superseded_source_recommendation_run_ids"] == [1]
    assert report.summary_json["settled_run_count"] == 1
    assert report.summary_json["hit_count"] == 1
    assert report.summary_json["profit_loss"] == report.evaluations[1].profit_loss
    assert report.summary_json["final_hit"] is True
    assert report.summary_json["core_flow_ready"] is True
    assert report.strategy_metrics[0].sample_size == 1
    assert report.strategy_metrics[0].hit_count == 1


def test_core_replay_counts_only_final_leaf_in_multihop_successor_chain() -> None:
    snapshots = [
        _snapshot(
            1,
            run_key="source",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "B", "C"],
            atomic_fixture_ids=["A", "B", "C"],
        ),
        _snapshot(
            2,
            run_key="first_successor",
            as_of_time_utc=_dt(2026, 5, 1, 11),
            selected_fixture_ids=["A", "C", "D"],
            atomic_fixture_ids=["A", "C", "D"],
            explanation_json=_successor_trace(1),
        ),
        _snapshot(
            3,
            run_key="second_successor",
            as_of_time_utc=_dt(2026, 5, 1, 12),
            selected_fixture_ids=["A", "D", "E"],
            atomic_fixture_ids=["A", "D", "E"],
            explanation_json=_successor_trace(2),
        ),
    ]

    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=[
            _result("A", 2, 0),
            _result("B", 0, 1),
            _result("C", 1, 0),
            _result("D", 3, 1),
            _result("E", 2, 0),
        ],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="3x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )

    assert report.summary_json["evaluated_run_count"] == 3
    assert report.summary_json["effective_evaluated_run_count"] == 1
    assert report.summary_json["effective_leaf_recommendation_run_ids"] == [3]
    assert report.summary_json["superseded_source_recommendation_run_ids"] == [1, 2]
    assert report.summary_json["settled_run_count"] == 1
    assert report.summary_json["hit_count"] == 1
    assert report.strategy_metrics[0].sample_size == 1
    assert report.strategy_metrics[0].hit_count == 1


def test_core_replay_ignores_invalidated_successor_for_effective_metrics() -> None:
    snapshots = [
        _snapshot(
            1,
            run_key="source_kept",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "C", "D"],
            atomic_fixture_ids=["A", "C", "D"],
        ),
        _snapshot(
            2,
            run_key="invalidated_successor",
            as_of_time_utc=_dt(2026, 5, 1, 11),
            selected_fixture_ids=["A", "B", "C"],
            atomic_fixture_ids=["A", "B", "C"],
            explanation_json=_successor_trace(1),
            status="invalidated",
        ),
    ]

    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=[
            _result("A", 2, 0),
            _result("B", 0, 1),
            _result("C", 1, 0),
            _result("D", 3, 1),
        ],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="3x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )

    assert report.summary_json["evaluated_run_count"] == 2
    assert report.summary_json["effective_evaluated_run_count"] == 1
    assert report.summary_json["effective_leaf_recommendation_run_ids"] == [1]
    assert report.summary_json["superseded_source_recommendation_run_ids"] == []
    assert report.summary_json["invalidated_successor_recommendation_run_ids"] == [2]
    assert (
        report.summary_json[
            "ignored_invalidated_successor_source_recommendation_run_ids"
        ]
        == [1]
    )
    assert report.summary_json["hit_count"] == 1
    assert report.strategy_metrics[0].sample_size == 1
    assert report.strategy_metrics[0].hit_count == 1


def test_core_replay_summary_includes_validity_window_counts() -> None:
    snapshots = [
        _snapshot(
            1,
            run_key="started_locked_source",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            selected_fixture_ids=["A", "B", "C"],
            atomic_fixture_ids=["A", "B", "C"],
            locked_fixture_ids=["A"],
            kickoff_times={
                "A": _dt(2026, 5, 1, 18),
                "B": _dt(2026, 5, 2, 18),
                "C": _dt(2026, 5, 2, 20),
            },
        ),
        _snapshot(
            2,
            run_key="future_current",
            as_of_time_utc=_dt(2026, 5, 1, 19),
            selected_fixture_ids=["A", "B", "D"],
            atomic_fixture_ids=["A", "B", "D"],
            explanation_json=_successor_trace(1),
            kickoff_times={
                "A": _dt(2026, 5, 1, 18),
                "B": _dt(2026, 5, 2, 18),
                "D": _dt(2026, 5, 2, 20),
            },
        ),
    ]

    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=[
            _result("A", 2, 0),
            _result("B", 0, 1),
            _result("C", 1, 0),
            _result("D", 3, 1),
        ],
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 1, 20),
            pass_type="3x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )

    assert report.summary_json["validity_window_status_counts"] == {
        "superseded": 1,
        "expired_kickoff": 1,
    }
    assert report.summary_json["current_answer_recommendation_run_ids"] == []
    assert report.summary_json["expired_kickoff_recommendation_run_ids"] == [2]
    assert report.summary_json["successor_recompute_required_recommendation_run_ids"] == [
        2
    ]


def test_core_replay_runner_reads_snapshots_and_result_fixture_ids() -> None:
    snapshot = _snapshot(
        7,
        run_key="runner_snapshot",
        as_of_time_utc=_dt(2026, 5, 1, 10),
        selected_fixture_ids=["A", "B"],
        atomic_fixture_ids=["A", "B"],
    )
    replay_repository = FakeReplayRepository([snapshot])
    result_repository = FakeResultRepository([_result("A", 2, 0), _result("B", 1, 0)])

    result = run_recommendation_core_replay(
        object(),  # type: ignore[arg-type]
        options=RecommendationCoreReplayOptions(
            window_start_utc=_dt(2026, 5, 1, 0),
            window_end_utc=_dt(2026, 5, 3, 0),
            pass_type="2x1",
            mode="single",
        ),
        replay_repository=replay_repository,
        result_repository=result_repository,
    )

    assert replay_repository.options is not None
    assert replay_repository.options.pass_type == "2x1"
    assert result_repository.fixture_ids == ["A", "B"]
    assert result.warnings == []
    assert result.report.summary_json["settled_run_count"] == 1


class FakeReplayRepository:
    def __init__(self, snapshots: list[PersistedRecommendationRunSnapshot]) -> None:
        self.snapshots = snapshots
        self.options: Any = None

    def list_snapshots(self, *, options: Any) -> list[PersistedRecommendationRunSnapshot]:
        self.options = options
        return list(self.snapshots)


class FakeResultRepository:
    def __init__(self, result_rows: list[dict[str, object]]) -> None:
        self.result_rows = result_rows
        self.fixture_ids: list[str] = []

    def list_results_for_fixture_ids(
        self,
        fixture_ids: Sequence[str],
    ) -> list[Mapping[str, object]]:
        self.fixture_ids = list(fixture_ids)
        return list(self.result_rows)


def _snapshot(
    recommendation_run_id: int,
    *,
    run_key: str,
    as_of_time_utc: datetime,
    selected_fixture_ids: list[str],
    atomic_fixture_ids: list[str],
    locked_fixture_ids: list[str] | None = None,
    explanation_json: dict[str, object] | None = None,
    candidate_pool_candidates: list[RecommendationCandidate] | None = None,
    status: str | None = None,
    kickoff_times: dict[str, datetime] | None = None,
) -> PersistedRecommendationRunSnapshot:
    candidates = candidate_pool_candidates
    if candidates is None:
        candidates = [_candidate(fixture_id) for fixture_id in ["A", "B", "C", "D", "E"]]
    selected_candidates = [
        _candidate(
            fixture_id,
            kickoff_time_utc=(
                kickoff_times[fixture_id]
                if kickoff_times is not None and fixture_id in kickoff_times
                else None
            ),
        )
        for fixture_id in selected_fixture_ids
    ]
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=as_of_time_utc,
        strategy="accuracy_first",
        pass_type=f"{len(selected_fixture_ids)}x1",
        mode="single",
        status=status or ("locked" if locked_fixture_ids else "current"),
        unit_stake=2.0,
        max_budget=10.0,
        candidate_count=len(candidates),
        excluded_candidate_count=0,
        selected_fixture_ids=selected_fixture_ids,
        locked_fixture_ids=locked_fixture_ids or [],
        total_score=0.72,
        parlay_evaluation_json=_parlay_evaluation(atomic_fixture_ids),
        explanation_json=explanation_json or {},
        source="recommendation_global_planner_v3_1",
        created_at=as_of_time_utc,
        selected_candidates=selected_candidates,
        candidate_pool_snapshot=(
            _pool_snapshot(recommendation_run_id, run_key, as_of_time_utc, len(candidates))
            if candidates
            else None
        ),
        candidate_pool_candidates=candidates,
    )


def _candidate(
    fixture_id: str,
    *,
    kickoff_time_utc: datetime | None = None,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome="home_win",
        probability=0.62,
        decimal_odds=1.7,
        market_probability=1 / 1.7,
        data_quality_score=88,
        model_confidence_score=0.82,
        calibration_score=0.80,
        odds_stability_score=0.76,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=101,
        prediction_time_utc=_dt(2026, 5, 1, 9),
        kickoff_time_utc=kickoff_time_utc or _dt(2026, 5, 4, 18),
    )


def _pool_snapshot(
    recommendation_run_id: int,
    run_key: str,
    as_of_time_utc: datetime,
    candidate_count: int,
) -> PersistedRecommendationCandidatePoolSnapshot:
    return PersistedRecommendationCandidatePoolSnapshot(
        recommendation_candidate_pool_snapshot_id=recommendation_run_id + 100,
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=as_of_time_utc,
        strategy="accuracy_first",
        pass_type="3x1",
        mode="single",
        candidate_count=candidate_count,
        selected_candidate_count=3,
        excluded_candidate_count=0,
        candidate_query_json={"source": "unit_test"},
        source="unit_test",
        created_at=as_of_time_utc,
    )


def _parlay_evaluation(fixture_ids: list[str]) -> dict[str, object]:
    return {
        "hit_probability": 0.24,
        "expected_value": 1.1,
        "roi": 0.12,
        "total_stake": 2.0,
        "atomic_bets": [
            {
                "stake": 2.0,
                "odds_product": 1.7 ** len(fixture_ids),
                "legs": [
                    {
                        "fixture_id": fixture_id,
                        "market_type": "1x2",
                        "outcome": "home_win",
                    }
                    for fixture_id in fixture_ids
                ],
            }
        ],
    }


def _successor_trace(source_recommendation_run_id: int) -> dict[str, object]:
    return {
        "internal_trace": {
            "successor_recompute": {
                "source_recommendation_run_id": source_recommendation_run_id,
                "calculation_basis": "locked_leg_successor_recompute_v3_1",
            }
        }
    }


def _result(fixture_id: str, home_goals: int, away_goals: int) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
