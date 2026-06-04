"""Integration test for nutmeg-score-ev-forward (record → settle → report).

Network-free: API-Football (fetch_fixtures_for_date / fetch_odds) is monkeypatched,
so the full record→settle→report flow runs against an in-memory fake + a tmp DB.
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.cli import score_ev_forward as fwd

_FID = 9001


def _odds_blob():
    return [{"bookmakers": [
        {"name": "BookA", "bets": [
            {"name": "Match Winner", "values": [
                {"value": "Home", "odd": "1.20"},
                {"value": "Draw", "odd": "6.00"},
                {"value": "Away", "odd": "12.00"}]},
            {"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": "1.90"},
                {"value": "Under 2.5", "odd": "1.90"}]},
            {"name": "Correct Score", "values": [
                {"value": "1:0", "odd": "7.0"},
                {"value": "2:1", "odd": "50.0"}]},   # generous → +EV flag
        ]},
    ]}]


def _fixture(status, gh=None, ga=None):
    return {
        "fixture": {"id": _FID, "status": {"short": status},
                    "date": "2026-06-10T18:00:00+00:00"},
        "teams": {"home": {"name": "Alpha"}, "away": {"name": "Beta"}},
        "league": {"name": "Friendlies"},
        "goals": {"home": gh, "away": ga},
    }


def test_record_settle_report(tmp_path, monkeypatch):
    import nutmeg.v4.data.sources.api_football as af
    db = str(tmp_path / "fwd.db")

    # --- record: fixture upcoming (NS) ---
    monkeypatch.setattr(af, "fetch_fixtures_for_date", lambda d, **k: [_fixture("NS")])
    monkeypatch.setattr(af, "fetch_odds", lambda fid, **k: _odds_blob())
    assert fwd.main(["--db", db, "--record", "--date", "2026-06-10"]) == 0

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM score_ev_flags").fetchall()
    assert rows, "record should store at least one +EV flag"
    assert all(r["won"] is None for r in rows)                 # unsettled
    preds = {(r["pred_home"], r["pred_away"]) for r in rows}
    assert (2, 1) in preds                                      # the generous 2:1

    # --- record idempotency: a second snapshot replaces, not duplicates ---
    assert fwd.main(["--db", db, "--record", "--date", "2026-06-10"]) == 0
    n2 = conn.execute("SELECT COUNT(*) FROM score_ev_flags").fetchone()[0]
    assert n2 == len(rows)                                      # replaced in place

    # --- settle: fixture now FT 2-1 → the 2:1 flag wins ---
    monkeypatch.setattr(af, "fetch_fixtures_for_date",
                        lambda d, **k: [_fixture("FT", 2, 1)])
    assert fwd.main(["--db", db, "--settle"]) == 0
    settled = conn.execute(
        "SELECT pred_home, pred_away, won FROM score_ev_flags WHERE won IS NOT NULL"
    ).fetchall()
    assert settled, "settle should fill results"
    won_map = {(r["pred_home"], r["pred_away"]): r["won"] for r in settled}
    assert won_map[(2, 1)] == 1                                 # 2-1 hit
    assert all(v == 0 for k, v in won_map.items() if k != (2, 1))

    # --- report runs cleanly over settled rows ---
    assert fwd.main(["--db", db, "--report"]) == 0
    conn.close()


def test_report_empty_db(tmp_path):
    assert fwd.main(["--db", str(tmp_path / "empty.db"), "--report"]) == 0
