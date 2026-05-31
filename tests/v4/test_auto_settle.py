"""Tests for V7 W2 nutmeg-auto-settle.

Three layers:
  1. `_extract_outcome_rows` — pure fixture-payload parser (no IO)
  2. `gather_finished_outcomes` — walks leagues × dates via mocked
     api_football.fetch_fixtures_for_date
  3. `apply_outcomes` — end-to-end: seed a parlay rec, hand it an
     outcome, verify settlements land in the DB (no API calls — uses
     pure observation layer)
"""
from __future__ import annotations

import datetime as dt
import json
from unittest.mock import patch

import pytest

from nutmeg.v4.cli import auto_settle as auto_settle_mod
from nutmeg.v4.cli.auto_settle import (
    FINISHED_STATUSES,
    _date_range,
    _extract_outcome_rows,
    apply_outcomes,
    gather_finished_outcomes,
)
from nutmeg.v4.observation import open_db, record_session


# ---------- Fixture builders --------------------------------------------

def _fixture(
    *,
    fid: int = 100,
    status: str = "FT",
    iso_date: str = "2025-08-17T15:00:00+00:00",
    home: str = "Arsenal",
    away: str = "Liverpool",
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    ft_home: int | None = None,
    ft_away: int | None = None,
) -> dict:
    """``home_goals``/``away_goals`` populate fixture["goals"] (= 120' score
    for AET/PEN). ``ft_home``/``ft_away`` populate score.fulltime (the 90'
    score) — set them to model a knockout decided in extra time."""
    fx = {
        "fixture": {
            "id": fid,
            "date": iso_date,
            "status": {"short": status, "long": status},
        },
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"id": 39},
    }
    if ft_home is not None or ft_away is not None:
        fx["score"] = {"fulltime": {"home": ft_home, "away": ft_away}}
    return fx


# ---------- _date_range ----------------------------------------------

class TestDateRange:
    def test_single_day(self):
        d = dt.date(2025, 8, 17)
        assert _date_range(d, d) == [d]

    def test_three_day_inclusive(self):
        out = _date_range(dt.date(2025, 8, 15), dt.date(2025, 8, 17))
        assert out == [
            dt.date(2025, 8, 15),
            dt.date(2025, 8, 16),
            dt.date(2025, 8, 17),
        ]

    def test_end_before_start_returns_empty(self):
        assert _date_range(dt.date(2025, 8, 18), dt.date(2025, 8, 17)) == []


# ---------- _extract_outcome_rows ------------------------------------

class TestExtractOutcomeRows:
    def test_full_match_extracts(self):
        rows = _extract_outcome_rows([_fixture()], "EPL")
        assert rows == [{
            "match_date": "2025-08-17",
            "league": "EPL",
            "home_team": "Arsenal",
            "away_team": "Liverpool",
            "home_goals": 2,
            "away_goals": 1,
        }]

    def test_aet_status_extracts(self):
        rows = _extract_outcome_rows(
            [_fixture(status="AET", home_goals=2, away_goals=2)],
            "EPL",
        )
        assert len(rows) == 1
        assert rows[0]["home_goals"] == 2
        assert rows[0]["away_goals"] == 2

    def test_pen_status_extracts(self):
        rows = _extract_outcome_rows([_fixture(status="PEN")], "EPL")
        assert len(rows) == 1

    def test_cup_knockout_settles_on_90_minute_score(self):
        """竞彩 settles 胜平负/让球 on the 90' result. A knockout that goes to
        extra time must use score.fulltime (90'), NOT goals (incl. ET).

        Regression: the UCL final (2026-05-30) settled fine only because ET was
        scoreless. A 1-1-at-90' / 2-1-after-ET match would otherwise settle as
        an away-cover when 竞彩 scores it a draw."""
        rows = _extract_outcome_rows(
            [_fixture(status="AET", home_goals=2, away_goals=1,  # 120' score
                      ft_home=1, ft_away=1)],                    # 90' score
            "UCL",
        )
        assert len(rows) == 1
        assert (rows[0]["home_goals"], rows[0]["away_goals"]) == (1, 1)

    def test_fulltime_absent_falls_back_to_goals(self):
        """Normal FT matches (no score.fulltime in the payload) keep using
        goals — back-compat, unchanged behaviour."""
        rows = _extract_outcome_rows([_fixture(status="FT")], "EPL")
        assert (rows[0]["home_goals"], rows[0]["away_goals"]) == (2, 1)

    @pytest.mark.parametrize("status", [
        "NS",    # Not started
        "1H",    # First half live
        "HT",    # Half time
        "2H",    # Second half live
        "ET",    # Extra time live
        "LIVE",
        "PST",   # Postponed
        "CANC",  # Cancelled
        "ABD",   # Abandoned
        "AWD",   # Technical loss
        "WO",    # Walkover
    ])
    def test_non_finished_status_skipped(self, status):
        rows = _extract_outcome_rows([_fixture(status=status)], "EPL")
        assert rows == []

    def test_missing_goals_skipped(self):
        rows = _extract_outcome_rows(
            [_fixture(home_goals=None, away_goals=None)], "EPL",
        )
        assert rows == []

    def test_partial_goals_skipped(self):
        rows = _extract_outcome_rows(
            [_fixture(home_goals=2, away_goals=None)], "EPL",
        )
        assert rows == []

    def test_missing_team_names_skipped(self):
        fx = _fixture()
        fx["teams"] = {"home": {}, "away": {"name": "Liverpool"}}
        assert _extract_outcome_rows([fx], "EPL") == []

    def test_iso_date_truncated_to_yyyy_mm_dd(self):
        rows = _extract_outcome_rows(
            [_fixture(iso_date="2025-08-17T22:30:00+09:00")], "EPL",
        )
        assert rows[0]["match_date"] == "2025-08-17"

    def test_finished_statuses_constant_shape(self):
        assert FINISHED_STATUSES == {"FT", "AET", "PEN"}

    def test_multiple_fixtures_mixed_statuses(self):
        rows = _extract_outcome_rows(
            [
                _fixture(fid=1, status="FT", home="A", away="B"),
                _fixture(fid=2, status="NS", home="C", away="D"),
                _fixture(fid=3, status="FT", home="E", away="F"),
                _fixture(fid=4, status="PST", home="G", away="H"),
            ],
            "EPL",
        )
        teams = {(r["home_team"], r["away_team"]) for r in rows}
        assert teams == {("A", "B"), ("E", "F")}


# ---------- gather_finished_outcomes (mocked API) --------------------

class TestGatherFinishedOutcomes:
    def _patch(self, fn):
        return patch.object(
            auto_settle_mod.api_football,
            "fetch_fixtures_for_date",
            side_effect=fn,
        )

    def test_walks_leagues_and_days(self, tmp_path):
        calls = []

        def fake(on_date, league_canonical=None, **kw):
            calls.append((on_date, league_canonical))
            if league_canonical == "EPL" and on_date.day == 17:
                return [_fixture(home="Arsenal", away="Liverpool")]
            return []

        with self._patch(fake):
            rows, n_calls, per_league = gather_finished_outcomes(
                ["EPL", "ESP_LA_LIGA"],
                dt.date(2025, 8, 15),
                dt.date(2025, 8, 17),
                cache_dir=tmp_path,
            )
        # 2 leagues × 3 days = 6 API calls
        assert n_calls == 6
        # Only the EPL-on-17 hit produced a row
        assert len(rows) == 1
        assert rows[0]["home_team"] == "Arsenal"
        assert per_league == {"EPL": 1, "ESP_LA_LIGA": 0}

    def test_api_error_skips_that_day_continues_others(self, tmp_path):
        def fake(on_date, league_canonical=None, **kw):
            # Fail one specific day, return a finished match the other
            if on_date.day == 16:
                raise auto_settle_mod.api_football.ApiFootballError("simulated 503")
            return [_fixture(home=f"Day{on_date.day}", away="Other")]

        with self._patch(fake):
            rows, n_calls, _ = gather_finished_outcomes(
                ["EPL"],
                dt.date(2025, 8, 15),
                dt.date(2025, 8, 17),
                cache_dir=tmp_path,
            )
        # 3 days = 3 calls attempted; 1 failed → 2 rows
        assert n_calls == 2  # successful calls counted; failing one bails early
        assert len(rows) == 2
        assert {r["home_team"] for r in rows} == {"Day15", "Day17"}


# ---------- apply_outcomes (end-to-end DB) ---------------------------

class TestApplyOutcomes:
    def _seed_parlay(self, db_path, *, home_team="Arsenal", away_team="Liverpool"):
        """Insert a 2-leg parlay session (H + H) so we can settle it."""
        response = {
            "generated_at_utc": "2025-08-17T10:00:00+00:00",
            "model": {"training_cutoff": "2025-06-01",
                      "trained_at_utc": "2025-08-17T09:00:00+00:00"},
            "bankroll": 1000.0, "n_fixtures": 2, "n_recommendations": 1,
            "single_match_predictions": [
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": home_team, "away_team": away_team,
                 "lambda_home": 1.5, "lambda_away": 1.0,
                 "p_home_1x2": 0.5, "p_draw_1x2": 0.25, "p_away_1x2": 0.25},
                {"date": "2025-08-17", "league": "ESP_LA_LIGA",
                 "home_team": "Real Madrid", "away_team": "Getafe",
                 "lambda_home": 1.4, "lambda_away": 1.1,
                 "p_home_1x2": 0.45, "p_draw_1x2": 0.28, "p_away_1x2": 0.27},
            ],
            "recommendations": [{
                "rank": 1, "k_legs": 2, "is_compound": False, "stake_units": 1,
                "kelly_recommended_stake": 10.0, "expected_return": 5.0,
                "hit_probability": 0.16, "ev_per_unit": 0.5, "log_growth": 0.02,
                "legs": [
                    {"match_id": f"EPL_{home_team}_vs_{away_team}",
                     "market_type": "1x2",
                     "selections": [{"outcome": "H", "odds": 2.5,
                                     "probability": 0.5, "edge": 0.1}]},
                    {"match_id": "ESP_LA_LIGA_Real Madrid_vs_Getafe",
                     "market_type": "1x2",
                     "selections": [{"outcome": "H", "odds": 3.0,
                                     "probability": 0.4, "edge": 0.1}]},
                ],
            }],
        }
        record_session(db_path, request={}, response=response)

    def test_writes_outcomes_and_settles(self, tmp_path):
        db = tmp_path / "obs.db"
        self._seed_parlay(db)
        rows = [
            {"match_date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 2, "away_goals": 0},
            {"match_date": "2025-08-17", "league": "ESP_LA_LIGA",
             "home_team": "Real Madrid", "away_team": "Getafe",
             "home_goals": 3, "away_goals": 1},
        ]
        summary = apply_outcomes(db, rows, dry_run=False)
        assert summary["n_outcome_rows"] == 2
        assert summary["settled"] == 1
        assert summary["dry_run"] is False
        # Verify it's actually in the DB
        with open_db(db) as conn:
            n_outcomes = conn.execute(
                "SELECT COUNT(*) FROM match_outcomes"
            ).fetchone()[0]
            n_settlements = conn.execute(
                "SELECT COUNT(*) FROM settlements"
            ).fetchone()[0]
        assert n_outcomes == 2
        assert n_settlements == 1

    def test_dry_run_writes_nothing(self, tmp_path):
        db = tmp_path / "obs.db"
        self._seed_parlay(db)
        rows = [{"match_date": "2025-08-17", "league": "EPL",
                 "home_team": "Arsenal", "away_team": "Liverpool",
                 "home_goals": 2, "away_goals": 0}]
        summary = apply_outcomes(db, rows, dry_run=True)
        assert summary["n_outcome_rows"] == 1
        assert summary["dry_run"] is True
        # Settle counts are NOT populated in dry-run
        assert summary["settled"] == 0
        with open_db(db) as conn:
            n_outcomes = conn.execute(
                "SELECT COUNT(*) FROM match_outcomes"
            ).fetchone()[0]
            n_settlements = conn.execute(
                "SELECT COUNT(*) FROM settlements"
            ).fetchone()[0]
        assert n_outcomes == 0
        assert n_settlements == 0

    def test_empty_rows_returns_zero_summary(self, tmp_path):
        db = tmp_path / "obs.db"
        summary = apply_outcomes(db, [], dry_run=False)
        assert summary["n_outcome_rows"] == 0
        assert summary["settled"] == 0
        assert summary["still_unknown"] == 0

    def test_idempotent_second_run(self, tmp_path):
        """Re-running with same data should add no new settlements."""
        db = tmp_path / "obs.db"
        self._seed_parlay(db)
        rows = [
            {"match_date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 2, "away_goals": 0},
            {"match_date": "2025-08-17", "league": "ESP_LA_LIGA",
             "home_team": "Real Madrid", "away_team": "Getafe",
             "home_goals": 3, "away_goals": 1},
        ]
        apply_outcomes(db, rows, dry_run=False)
        # Second call: outcomes upserted (no-op effect on values), settle finds
        # no new unsettled recs
        summary2 = apply_outcomes(db, rows, dry_run=False)
        assert summary2["settled"] == 0
        with open_db(db) as conn:
            n_settlements = conn.execute(
                "SELECT COUNT(*) FROM settlements"
            ).fetchone()[0]
        assert n_settlements == 1  # still 1, no duplicate

    def test_outcome_partial_one_known_one_unknown(self, tmp_path):
        """Parlay leg with no recorded outcome → stays unsettled."""
        db = tmp_path / "obs.db"
        self._seed_parlay(db)
        rows = [
            # Only record the EPL leg's outcome; Real Madrid stays unknown
            {"match_date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 2, "away_goals": 0},
        ]
        summary = apply_outcomes(db, rows, dry_run=False)
        assert summary["settled"] == 0
        assert summary["still_unknown"] == 1
