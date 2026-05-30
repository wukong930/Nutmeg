"""V12 W8 — auto-settle `--leagues auto`: derive the settle set from the DB.

The daily settle cron used a 2-league default (EPL, ESP_LA_LIGA), so 市场模式
bets (J1, cups) never got their results fetched → they sat unsettled. `auto`
fixes that by fetching results only for leagues that actually have an
unresolved recorded bet — covering J1/cups automatically, wasting no API calls.
"""
from __future__ import annotations

from datetime import date

from nutmeg.v4.cli.auto_settle import main as auto_main
from nutmeg.v4.cli.auto_settle import pending_leagues
from nutmeg.v4.observation.recorder import record_market_handicap_session
from nutmeg.v4.observation.store import init_db, open_db, upsert_outcome


def _db(tmp_path):
    db = tmp_path / "obs.db"
    init_db(db)
    return db


def _record_j1(db):
    record_market_handicap_session(
        db, league="JPN_J1", match_date="2026-05-30",
        home_team="Vissel Kobe", away_team="Kashima", handicap_home=-1,
        p_handicap=(0.18, 0.22, 0.60), p_1x2=(0.40, 0.32, 0.28),
        pick_outcome="H", pick_odds=5.50, pick_ev=-0.01,
        pick_stake=2.0, pick_expected_return=-0.02, bankroll=1000.0,
    )


class TestPendingLeagues:
    def test_unresolved_bet_league_is_pending(self, tmp_path):
        db = _db(tmp_path)
        _record_j1(db)
        lgs = pending_leagues(db, date(2026, 5, 28), date(2026, 5, 31))
        assert "JPN_J1" in lgs

    def test_resolved_bet_league_drops_out(self, tmp_path):
        db = _db(tmp_path)
        _record_j1(db)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=5, away_goals=0,
            )
        lgs = pending_leagues(db, date(2026, 5, 28), date(2026, 5, 31))
        assert "JPN_J1" not in lgs

    def test_out_of_window_excluded(self, tmp_path):
        db = _db(tmp_path)
        _record_j1(db)  # match_date 2026-05-30
        lgs = pending_leagues(db, date(2026, 1, 1), date(2026, 1, 3))
        assert "JPN_J1" not in lgs

    def test_missing_db_returns_empty(self, tmp_path):
        assert pending_leagues(tmp_path / "nope.db", date(2026, 5, 1), date(2026, 5, 3)) == []


class TestAutoMain:
    def test_auto_empty_db_returns_zero_no_api(self, tmp_path):
        """With nothing pending, `auto` short-circuits to 0 before any fetch."""
        db = _db(tmp_path)
        rc = auto_main(["--leagues", "auto", "--db", str(db),
                        "--days", "3", "--end-date", "2026-05-30", "--quiet"])
        assert rc == 0
