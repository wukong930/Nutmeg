"""Closing-line Pinnacle capture — writes fetch_pinnacle_lookup → odds_snapshots,
applies the Odds-API→canonical alias, dedups on re-run."""
from __future__ import annotations

import sqlite3


def _fake_lookup(sport_key, refresh=True):
    return {
        ("france", "sweden", "2026-06-30"): {
            "home_team": "France", "away_team": "Sweden",
            "psc_home": 1.29, "psc_draw": 6.1, "psc_away": 12.0,
            "ou_line": 3.5, "psc_over": 2.05, "psc_under": 1.86,
            "last_update": "2026-06-30T18:43:51Z"},
        ("england", "drcongo", "2026-07-01"): {
            "home_team": "England", "away_team": "DR Congo",  # ← alias target
            "psc_home": 1.29, "psc_draw": 5.36, "psc_away": 13.11,
            "ou_line": 2.5, "psc_over": 2.06, "psc_under": 1.84,
            "last_update": "2026-06-30T18:43:51Z"},
    }


def test_capture_writes_aliases_and_dedups(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _fake_lookup)
    db = tmp_path / "obs.db"

    r = closing_odds.capture_closing_pinnacle(db, ["WC"])
    assert r == {"WC": 2}

    rows = {(x[0], x[1], x[2]) for x in sqlite3.connect(db).execute(
        "SELECT home_team, away_team, source FROM odds_snapshots")}
    assert ("France", "Sweden", "closing") in rows
    assert ("England", "Congo DR", "closing") in rows  # 'DR Congo' → 'Congo DR'

    # the Pinnacle line + bookmaker timestamp landed
    fr = sqlite3.connect(db).execute(
        "SELECT psc_home, ou_line, odds_update FROM odds_snapshots "
        "WHERE home_team='France'").fetchone()
    assert fr == (1.29, 3.5, "2026-06-30T18:43:51Z")

    # re-run with the SAME line = append-only dedup, no new rows
    assert closing_odds.capture_closing_pinnacle(db, ["WC"]) == {"WC": 0}


def test_fetch_failure_is_failsoft(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    def _boom(sport_key, refresh=True):
        raise RuntimeError("odds api down")

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _boom)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 0}
