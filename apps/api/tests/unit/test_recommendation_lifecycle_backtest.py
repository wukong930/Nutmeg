from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.recommendations import (
    PrematchRecommendationBacktestCheckpoint,
    RecommendationCandidate,
    run_prematch_recommendation_lifecycle_backtest,
)


def test_lifecycle_backtest_preserves_locked_started_legs_and_refills_future_matches() -> None:
    initial_candidates = [
        _candidate("A", "home_win", probability=0.70, kickoff_time_utc=_dt(2026, 5, 1, 18)),
        _candidate("B", "home_win", probability=0.68, kickoff_time_utc=_dt(2026, 5, 1, 20)),
        _candidate("C", "home_win", probability=0.66, kickoff_time_utc=_dt(2026, 5, 2, 18)),
        _candidate("D", "home_win", probability=0.64, kickoff_time_utc=_dt(2026, 5, 2, 20)),
        _candidate("E", "home_win", probability=0.62, kickoff_time_utc=_dt(2026, 5, 3, 18)),
        _candidate("F", "home_win", probability=0.60, kickoff_time_utc=_dt(2026, 5, 3, 20)),
        _candidate("G", "home_win", probability=0.58, kickoff_time_utc=_dt(2026, 5, 3, 21)),
        _candidate("H", "home_win", probability=0.57, kickoff_time_utc=_dt(2026, 5, 4, 20)),
    ]

    result = run_prematch_recommendation_lifecycle_backtest(
        [
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="t_minus_24h",
                as_of_time_utc=_dt(2026, 5, 1, 10),
                candidates=initial_candidates,
            ),
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="after_day_one_locks",
                as_of_time_utc=_dt(2026, 5, 2, 10),
                candidates=initial_candidates,
                locked_fixture_ids=["A", "B"],
            ),
        ],
        pass_type="6x1",
        mode="single",
        unit_stake=2.0,
        max_budget=10.0,
    )

    assert result.stages[0].selected_fixture_ids == ["A", "B", "C", "D", "E", "F"]
    assert result.stages[1].selected_fixture_ids == ["A", "B", "C", "D", "E", "F"]
    assert result.stages[1].locked_fixture_ids == ["A", "B"]
    assert result.stages[1].preserved_locked_fixture_ids == ["A", "B"]
    assert result.stages[1].started_locked_fixture_ids == ["A", "B"]
    assert result.stages[1].continuation_fixture_ids == ["C", "D", "E", "F"]
    assert result.stages[1].remaining_open_leg_count == 4
    assert "started_locked_fixtures_retained" in result.stages[1].event_codes
    assert "locked_fixtures_preserved" in result.stages[1].event_codes
    assert "remaining_fixtures_continue" in result.stages[1].event_codes
    assert result.summary_json["locked_preservation_stage_count"] == 1
    assert result.summary_json["started_locked_stage_count"] == 1
    assert result.summary_json["final_continuation_fixture_ids"] == [
        "C",
        "D",
        "E",
        "F",
    ]
    assert result.summary_json["final_remaining_open_leg_count"] == 4


def test_lifecycle_backtest_excludes_incident_fixtures_before_user_locks_them() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.72, kickoff_time_utc=_dt(2026, 5, 2, 20)),
        _candidate("B", "home_win", probability=0.70, kickoff_time_utc=_dt(2026, 5, 2, 21)),
        _candidate("C", "home_win", probability=0.66, kickoff_time_utc=_dt(2026, 5, 3, 18)),
        _candidate("D", "home_win", probability=0.64, kickoff_time_utc=_dt(2026, 5, 3, 20)),
        _candidate("E", "home_win", probability=0.62, kickoff_time_utc=_dt(2026, 5, 4, 18)),
        _candidate("F", "home_win", probability=0.60, kickoff_time_utc=_dt(2026, 5, 4, 20)),
        _candidate("G", "home_win", probability=0.58, kickoff_time_utc=_dt(2026, 5, 4, 21)),
        _candidate("H", "home_win", probability=0.56, kickoff_time_utc=_dt(2026, 5, 5, 20)),
    ]

    result = run_prematch_recommendation_lifecycle_backtest(
        [
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="opening",
                as_of_time_utc=_dt(2026, 5, 1, 10),
                candidates=candidates,
            ),
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="injury_update",
                as_of_time_utc=_dt(2026, 5, 2, 10),
                candidates=candidates,
                excluded_fixture_ids=["A", "B"],
                incident_notes={
                    "A": "late_lineup_risk_removed_fixture",
                    "B": "data_quality_dropped_below_threshold",
                },
            ),
        ],
        pass_type="6x1",
        mode="single",
        unit_stake=2.0,
        max_budget=10.0,
    )

    assert result.stages[1].selected_fixture_ids == ["C", "D", "E", "F", "G", "H"]
    assert result.stages[1].continuation_fixture_ids == ["C", "D", "E", "F", "G", "H"]
    assert result.stages[1].remaining_open_leg_count == 6
    assert result.stages[1].excluded_fixture_ids == ["A", "B"]
    assert result.stages[1].changed_fixture_ids == ["A", "B", "G", "H"]
    assert "incident_exclusion_applied" in result.stages[1].event_codes
    assert "recommendation_changed" in result.stages[1].event_codes
    assert result.summary_json["incident_stage_count"] == 1


def test_lifecycle_backtest_keeps_locked_fixture_even_if_later_incident_flags_it() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.70, kickoff_time_utc=_dt(2026, 5, 1, 18)),
        _candidate("B", "home_win", probability=0.66, kickoff_time_utc=_dt(2026, 5, 2, 18)),
        _candidate("C", "home_win", probability=0.64, kickoff_time_utc=_dt(2026, 5, 2, 20)),
        _candidate("D", "home_win", probability=0.62, kickoff_time_utc=_dt(2026, 5, 3, 20)),
    ]

    result = run_prematch_recommendation_lifecycle_backtest(
        [
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="opening",
                as_of_time_utc=_dt(2026, 5, 1, 10),
                candidates=candidates,
            ),
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="after_user_lock",
                as_of_time_utc=_dt(2026, 5, 1, 19),
                candidates=candidates,
                locked_fixture_ids=["A"],
                excluded_fixture_ids=["A"],
            ),
        ],
        pass_type="3x1",
        mode="single",
        unit_stake=2.0,
        max_budget=6.0,
    )

    assert result.stages[1].selected_fixture_ids == ["A", "B", "C"]
    assert result.stages[1].preserved_locked_fixture_ids == ["A"]
    assert result.stages[1].started_locked_fixture_ids == ["A"]
    assert result.stages[1].continuation_fixture_ids == ["B", "C"]
    assert result.stages[1].remaining_open_leg_count == 2
    assert result.stages[1].warnings == ["locked_fixture_has_incident_exclusion:A"]
    assert "locked_fixtures_preserved" in result.stages[1].event_codes


def test_lifecycle_backtest_supports_multiple_mode_under_budget() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.68, kickoff_time_utc=_dt(2026, 5, 2, 18)),
        _candidate(
            "A",
            "draw",
            probability=0.24,
            decimal_odds=3.40,
            kickoff_time_utc=_dt(2026, 5, 2, 18),
        ),
        _candidate("B", "home_win", probability=0.66, kickoff_time_utc=_dt(2026, 5, 2, 20)),
        _candidate("C", "home_win", probability=0.60, kickoff_time_utc=_dt(2026, 5, 3, 20)),
    ]

    result = run_prematch_recommendation_lifecycle_backtest(
        [
            PrematchRecommendationBacktestCheckpoint(
                checkpoint_id="multiple_budget_check",
                as_of_time_utc=_dt(2026, 5, 1, 10),
                candidates=candidates,
            )
        ],
        pass_type="2x1",
        mode="multiple",
        unit_stake=2.0,
        max_budget=4.0,
        max_outcomes_per_fixture=2,
    )

    assert result.final_selection is not None
    assert result.final_selection.mode == "multiple"
    assert result.final_selection.evaluation.total_stake <= 4.0


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float,
    decimal_odds: float = 1.80,
    kickoff_time_utc: datetime,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        data_quality_score=90.0,
        model_confidence_score=0.88,
        calibration_score=0.86,
        upset_protection_score=0.20 if outcome == "draw" else 0.0,
        odds_stability_score=0.75,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=101,
        prediction_time_utc=datetime(2026, 5, 1, 9, tzinfo=UTC),
        kickoff_time_utc=kickoff_time_utc,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
