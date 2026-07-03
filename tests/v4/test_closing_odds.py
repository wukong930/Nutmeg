"""Closing-line Pinnacle capture — writes fetch_pinnacle_lookup → odds_snapshots,
applies the Odds-API→canonical alias, dedups on re-run, and (2026-07-01 fix) skips
already-kicked-off matches so LIVE odds never get recorded as a "close"."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def _fake_lookup(sport_key, refresh=True):
    return {
        ("france", "sweden", "2026-06-30"): {
            "home_team": "France", "away_team": "Sweden",
            "psc_home": 1.29, "psc_draw": 6.1, "psc_away": 12.0,
            "ou_line": 3.5, "psc_over": 2.05, "psc_under": 1.86,
            "last_update": "2026-06-30T18:43:51Z",
            "commence_time": "2026-06-30T19:00:00Z"},
        ("england", "drcongo", "2026-07-01"): {
            "home_team": "England", "away_team": "DR Congo",  # ← alias target
            "psc_home": 1.29, "psc_draw": 5.36, "psc_away": 13.11,
            "ou_line": 2.5, "psc_over": 2.06, "psc_under": 1.84,
            "last_update": "2026-06-30T18:43:51Z",
            "commence_time": "2026-07-01T19:00:00Z"},
    }


# A fixed "now" BEFORE both fixture kickoffs → both count as pre-match.
_BEFORE_KO = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_capture_writes_aliases_and_dedups(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _fake_lookup)
    db = tmp_path / "obs.db"

    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=_BEFORE_KO)
    assert r == {"WC": 2}

    rows = {(x[0], x[1], x[2]) for x in sqlite3.connect(db).execute(
        "SELECT home_team, away_team, source FROM odds_snapshots")}
    assert ("France", "Sweden", "closing") in rows
    assert ("England", "Congo DR", "closing") in rows  # 'DR Congo' → 'Congo DR'

    # the Pinnacle line + bookmaker timestamp + kickoff landed
    fr = sqlite3.connect(db).execute(
        "SELECT psc_home, ou_line, odds_update, kickoff_utc FROM odds_snapshots "
        "WHERE home_team='France'").fetchone()
    assert fr == (1.29, 3.5, "2026-06-30T18:43:51Z", "2026-06-30T19:00:00Z")

    # re-run with the SAME line = append-only dedup, no new rows
    assert closing_odds.capture_closing_pinnacle(db, ["WC"], now=_BEFORE_KO) == {"WC": 0}


def test_skips_already_started_live_matches(tmp_path, monkeypatch):
    """The core fix: a match that has kicked off serves LIVE odds — it must be
    skipped, not recorded as a close. Only the still-upcoming match is written."""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _fake_lookup)
    db = tmp_path / "obs.db"

    # now is AFTER France-Sweden (19:00 on 06-30) but BEFORE England (19:00 on 07-01)
    between = datetime(2026, 6, 30, 20, 0, tzinfo=UTC)
    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=between)
    assert r == {"WC": 1}

    teams = {(x[0], x[1]) for x in sqlite3.connect(db).execute(
        "SELECT home_team, away_team FROM odds_snapshots")}
    assert ("England", "Congo DR") in teams        # upcoming → kept
    assert ("France", "Sweden") not in teams       # already kicked off → skipped


def test_missing_kickoff_is_skipped(tmp_path, monkeypatch):
    """No parseable commence_time → can't prove pre-match → skip (conservative)."""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    def _no_ko(sport_key, refresh=True):
        return {("x", "y", "2026-07-05"): {
            "home_team": "X", "away_team": "Y",
            "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.5,
            "ou_line": 2.5, "psc_over": 2.0, "psc_under": 1.85,
            "last_update": "2026-07-05T10:00:00Z"}}  # no commence_time

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _no_ko)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 0}


def test_fetch_failure_is_failsoft(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    def _boom(sport_key, refresh=True):
        raise RuntimeError("odds api down")

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _boom)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 0}


def test_poisoned_none_lookup_entry_is_skipped(tmp_path, monkeypatch):
    """体检 2026-07-03 — fetch_pinnacle_lookup poisons ambiguous club-core keys to
    None (c5e805f). This consumer loop is OUTSIDE the per-sport try: an unguarded
    None would AttributeError and kill the WHOLE capture round. The good entry
    must still be captured."""
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    future = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    date = future[:10]

    def _mixed(sport_key, refresh=True):
        return {
            ("poisoned", "core", date): None,     # ambiguous club-core key
            ("a", "b", date): {
                "home_team": "A", "away_team": "B",
                "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.5,
                "ou_line": 2.5, "psc_over": 2.0, "psc_under": 1.85,
                "last_update": future, "commence_time": future},
        }

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _mixed)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 1}


class TestResolveAutoSports:
    """体检 Wave2 — `--sports auto`: KO-window-driven sport resolution.
    Hardcoded `--sports WC` would kill the closing chain at WC end (~7/19)."""

    def _fx(self, minutes_from_now, league_id, now):
        from datetime import timedelta
        return {"fixture": {"date": (now + timedelta(minutes=minutes_from_now)).isoformat()},
                "league": {"id": league_id}}

    def test_in_window_league_with_sport_key_resolves(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(30, 292, now)]  # K-League KO in 30min
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == ["KOR_K_LEAGUE_1"]

    def test_outside_window_and_kicked_off_excluded(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(120, 292, now),   # beyond 75min lookahead
                    self._fx(-10, 292, now)]   # already kicked off
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == []

    def test_league_without_sport_key_filtered(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(30, 119, now)]  # DNK_SUPERLIGA: AF id, no sport key
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == []

    def test_af_outage_returns_empty_not_blind_fetch(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports

        def boom(d):
            raise RuntimeError("AF down")
        assert resolve_auto_sports(now=datetime.now(UTC), fetch_fixtures=boom) == []
