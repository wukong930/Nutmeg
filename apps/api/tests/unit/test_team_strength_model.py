from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.modeling.team_strength import (
    HistoricalFixtureResult,
    build_competition_historical_strength_snapshot,
    estimate_goal_lambdas_from_team_strength,
)


def test_historical_team_strength_estimates_lambdas_from_as_of_safe_results() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)

    snapshot = build_competition_historical_strength_snapshot(
        [
            _result("r1", "ars", "city", 3, 1),
            _result("r2", "whu", "ars", 0, 2),
            _result("r3", "ars", "che", 2, 0),
            _result("r4", "liv", "city", 1, 2),
            _result("r5", "whu", "liv", 2, 1),
            _result("r6", "liv", "che", 0, 1),
            _result(
                "future_leak",
                "liv",
                "ars",
                7,
                0,
                kickoff_time_utc=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
            ),
        ],
        competition_id="EPL",
        as_of_time_utc=as_of_time,
        min_team_matches=3,
    )

    estimate = estimate_goal_lambdas_from_team_strength(
        snapshot,
        fixture_id="target",
        home_team_id="ars",
        away_team_id="liv",
    )

    assert estimate is not None
    assert snapshot.match_count == 6
    assert "future_leak" not in snapshot.source_fixture_ids
    assert estimate.lambda_home > estimate.lambda_away
    assert estimate.metadata_json["lambda_source"] == "historical_team_strength"
    assert estimate.metadata_json["dixon_coles_v15_compatible"] is True
    assert estimate.metadata_json["home_sample_matches"] == 3
    assert estimate.metadata_json["away_sample_matches"] == 3


def test_historical_team_strength_requires_minimum_team_samples() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    snapshot = build_competition_historical_strength_snapshot(
        [
            _result("r1", "ars", "city", 3, 1),
            _result("r2", "liv", "che", 1, 1),
        ],
        competition_id="EPL",
        as_of_time_utc=as_of_time,
        min_team_matches=2,
    )

    estimate = estimate_goal_lambdas_from_team_strength(
        snapshot,
        fixture_id="target",
        home_team_id="ars",
        away_team_id="liv",
    )

    assert estimate is None


def test_historical_team_strength_clamps_extreme_lambdas() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    snapshot = build_competition_historical_strength_snapshot(
        [
            _result("r1", "ars", "liv", 12, 0),
            _result("r2", "ars", "city", 10, 0),
            _result("r3", "whu", "ars", 0, 9),
            _result("r4", "liv", "che", 0, 8),
            _result("r5", "city", "liv", 7, 0),
            _result("r6", "liv", "whu", 0, 6),
        ],
        competition_id="EPL",
        as_of_time_utc=as_of_time,
        min_team_matches=3,
    )

    estimate = estimate_goal_lambdas_from_team_strength(
        snapshot,
        fixture_id="target",
        home_team_id="ars",
        away_team_id="liv",
    )

    assert estimate is not None
    assert estimate.lambda_home == 3.5
    assert 0.2 <= estimate.lambda_away <= 3.5


def _result(
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    home_goals: int,
    away_goals: int,
    *,
    kickoff_time_utc: datetime | None = None,
) -> HistoricalFixtureResult:
    return HistoricalFixtureResult(
        fixture_id=fixture_id,
        competition_id="EPL",
        kickoff_time_utc=kickoff_time_utc
        or datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_goals=home_goals,
        away_goals=away_goals,
    )
