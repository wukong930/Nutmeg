"""体检 B1/B2 (2026-07-01) — the CLOSE readers (backfill_vote_pinnacle + the
clv/staleness _pinn_close) must skip an IN-PLAY snapshot (captured at/after
kickoff), so a leading team's live line (1.06/…/53.96) never becomes the pinned
close / CLV anchor. Producer guards exist too; this is the durable reader defense.
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots

_KO = "2026-08-01T18:00:00+00:00"


def _snap(conn, *, home, away, psc_home, psc_away, captured_at, kickoff_utc=_KO):
    conn.execute(
        "INSERT INTO odds_snapshots (captured_at, source, league, match_date, "
        "home_team, away_team, kickoff_utc, psc_home, psc_draw, psc_away) "
        "VALUES (?, 'closing', 'WC', '2026-08-01', ?, ?, ?, ?, 5.0, ?)",
        (captured_at, home, away, kickoff_utc, psc_home, psc_away))


def _seed_both(conn, home, away):
    # healthy PRE-KO close (older) + IN-PLAY line (newer, degenerate)
    _snap(conn, home=home, away=away, psc_home=2.2, psc_away=4.5,
          captured_at="2026-08-01T17:30:00+00:00")
    _snap(conn, home=home, away=away, psc_home=1.06, psc_away=53.96,
          captured_at="2026-08-01T19:00:00+00:00")   # captured AFTER kickoff


def test_backfill_skips_in_play_snapshot(tmp_path):
    from nutmeg.v4.observation.jingcai_vote import (
        backfill_vote_pinnacle,
        ensure_jingcai_vote_table,
    )
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        ensure_jingcai_vote_table(conn)
        _seed_both(conn, "Mexico", "Ecuador")
        conn.execute(
            "INSERT INTO jingcai_vote (captured_at, source, match_date, home_zh, "
            "away_zh, pool_code, home_team, away_team) VALUES "
            "('2026-08-01T00:00:00+00:00','sporttery','2026-08-01','墨西哥','厄瓜多尔',"
            "'HAD','Mexico','Ecuador')")
        conn.commit()

    backfill_vote_pinnacle(db)
    with sqlite3.connect(db) as conn:
        psc = conn.execute(
            "SELECT psc_home FROM jingcai_vote WHERE home_team='Mexico'").fetchone()[0]
    assert psc == 2.2   # the pre-KO close, NOT the 1.06 in-play line


def test_pinn_close_skips_in_play(tmp_path):
    from nutmeg.v4.cli.jingcai_staleness import _pinn_close
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        _seed_both(conn, "A", "B")
        conn.commit()
        close = _pinn_close(
            conn, {"match_date": "2026-08-01", "home_team": "A", "away_team": "B"})
    assert close is not None
    assert close[0] == 2.2   # pre-KO close, not the in-play 1.06


def test_null_kickoff_still_pinnable(tmp_path):
    # historical rows (kickoff_utc NULL, pre-2026-07-01) can't be judged → kept
    from nutmeg.v4.cli.jingcai_staleness import _pinn_close
    db = tmp_path / "obs.db"
    with sqlite3.connect(db) as conn:
        ensure_odds_snapshots(conn)
        _snap(conn, home="C", away="D", psc_home=1.9, psc_away=4.0,
              captured_at="2026-05-01T12:00:00+00:00", kickoff_utc=None)
        conn.commit()
        close = _pinn_close(
            conn, {"match_date": "2026-08-01", "home_team": "C", "away_team": "D"})
    assert close is not None and close[0] == 1.9
