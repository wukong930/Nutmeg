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


class TestPendingMatchPairs:
    """体检(2026-06-10)— orphan rescue: the 3-day window must be a floor for
    freshness, NOT a ceiling for ever settling (the 克罗地亚/斯洛文尼亚 case)."""

    def test_orphan_older_than_window_is_found(self, tmp_path):
        from nutmeg.v4.cli.auto_settle import pending_match_pairs
        db = _db(tmp_path)
        _record_j1(db)  # match_date 2026-05-30
        pairs = pending_match_pairs(db, before=date(2026, 6, 7))
        assert ("JPN_J1", date(2026, 5, 30)) in pairs

    def test_resolved_orphan_drops_out(self, tmp_path):
        from nutmeg.v4.cli.auto_settle import pending_match_pairs
        db = _db(tmp_path)
        _record_j1(db)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=5, away_goals=0,
            )
        assert pending_match_pairs(db, before=date(2026, 6, 7)) == []

    def test_inside_window_not_an_orphan(self, tmp_path):
        # The normal window pass owns anything >= before; no double fetch.
        from nutmeg.v4.cli.auto_settle import pending_match_pairs
        db = _db(tmp_path)
        _record_j1(db)
        assert pending_match_pairs(db, before=date(2026, 5, 29)) == []

    def test_max_age_bounds_the_scan(self, tmp_path):
        from nutmeg.v4.cli.auto_settle import pending_match_pairs
        db = _db(tmp_path)
        _record_j1(db)  # 2026-05-30
        pairs = pending_match_pairs(db, before=date(2026, 9, 30), max_age_days=30)
        assert pairs == []  # older than 30d before `before` → out of scope

    def test_missing_db_returns_empty(self, tmp_path):
        from nutmeg.v4.cli.auto_settle import pending_match_pairs
        assert pending_match_pairs(tmp_path / "nope.db", before=date(2026, 6, 1)) == []


class TestAutoMain:
    def test_auto_empty_db_returns_zero_no_api(self, tmp_path):
        """With nothing pending, `auto` short-circuits to 0 before any fetch."""
        db = _db(tmp_path)
        rc = auto_main(["--leagues", "auto", "--db", str(db),
                        "--days", "3", "--end-date", "2026-05-30", "--quiet"])
        assert rc == 0

    def test_auto_orphan_only_run_settles_old_bet(self, tmp_path, monkeypatch):
        """Pending bet OLDER than the window: pre-fix `auto` returned 0 without
        looking; now the orphan scan fetches exactly that (league, date) pair
        and the bet settles."""
        import nutmeg.v4.cli.auto_settle as mod
        db = _db(tmp_path)
        _record_j1(db)  # match_date 2026-05-30, pick H @5.50

        def fake_gather(leagues, start, end, **kw):
            assert leagues == ["JPN_J1"] and start == end == date(2026, 5, 30)
            row = {"match_date": "2026-05-30", "league": "JPN_J1",
                   "home_team": "Vissel Kobe", "away_team": "Kashima",
                   "home_goals": 5, "away_goals": 0}
            return [row], 1, {"JPN_J1": 1}

        monkeypatch.setattr(mod, "gather_finished_outcomes", fake_gather)
        # Window 6/05–6/08 → 5/30 is outside; only the orphan scan can reach it.
        rc = auto_main(["--leagues", "auto", "--db", str(db),
                        "--days", "3", "--end-date", "2026-06-08", "--quiet"])
        assert rc == 0
        with open_db(db) as conn:
            n, = conn.execute("SELECT COUNT(*) FROM settlements").fetchone()
        assert n == 1

    def test_no_orphan_scan_flag_restores_old_behaviour(self, tmp_path, monkeypatch):
        import nutmeg.v4.cli.auto_settle as mod
        db = _db(tmp_path)
        _record_j1(db)

        def explode(*a, **k):  # pragma: no cover - must not be called
            raise AssertionError("gather must not run with --no-orphan-scan")

        monkeypatch.setattr(mod, "gather_finished_outcomes", explode)
        rc = auto_main(["--leagues", "auto", "--db", str(db), "--no-orphan-scan",
                        "--days", "3", "--end-date", "2026-06-08", "--quiet"])
        assert rc == 0  # nothing in window + scan disabled → early return
