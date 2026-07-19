"""竞彩 SP 初/终双快照 — jc_open_* (set-once) coexists with jc_* (canonical 终盘).

The 11:00 开售 初盘 is captured via ``phase='open'`` and preserved across the
latest=终盘 overwrites, so 竞彩's own open→freeze line movement is recorded —
first-hand from sporttery (no Okooo, which only re-displays the same 竞彩 SP).
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.jingcai_sp import (
    ensure_jingcai_sp_table,
    record_jingcai_sp,
)

_M = dict(match_date="2026-06-25", home_team="A", away_team="B",
          market="hhad", handicap_home=-1)


def _row(db, market="hhad"):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM jingcai_sp WHERE market=?", (market,)).fetchone()
    con.close()
    return dict(r) if r else None


def test_open_phase_stamps_jc_open(tmp_path):
    db = str(tmp_path / "o.db")
    record_jingcai_sp(db, jc_home=2.0, jc_draw=3.2, jc_away=3.3,
                      source="sporttery", phase="open", **_M)
    r = _row(db)
    assert (r["jc_open_home"], r["jc_open_draw"], r["jc_open_away"]) == (2.0, 3.2, 3.3)
    assert r["opened_at"] is not None
    assert r["jc_home"] == 2.0  # first capture also seeds the canonical line


def test_close_after_open_keeps_open_updates_canonical(tmp_path):
    db = str(tmp_path / "o.db")
    record_jingcai_sp(db, jc_home=2.0, jc_draw=3.2, jc_away=3.3,
                      source="sporttery", phase="open", **_M)
    record_jingcai_sp(db, jc_home=2.5, jc_draw=3.2, jc_away=2.55,  # 终盘 moved
                      source="sporttery", phase="close", **_M)
    r = _row(db)
    assert r["jc_open_home"] == 2.0 and r["jc_open_away"] == 3.3   # 初盘 preserved
    assert r["jc_home"] == 2.5 and r["jc_away"] == 2.55             # 终盘 = canonical


def test_close_only_leaves_open_null(tmp_path):
    db = str(tmp_path / "o.db")
    record_jingcai_sp(db, jc_home=2.5, jc_draw=3.2, jc_away=2.55,
                      source="sporttery", phase="close", **_M)
    r = _row(db)
    assert r["jc_open_home"] is None and r["opened_at"] is None
    assert r["jc_home"] == 2.5


def test_open_after_close_backfills_open(tmp_path):
    db = str(tmp_path / "o.db")
    record_jingcai_sp(db, jc_home=2.5, jc_draw=3.2, jc_away=2.55,
                      source="sporttery", phase="close", **_M)
    record_jingcai_sp(db, jc_home=2.0, jc_draw=3.2, jc_away=3.3,
                      source="sporttery", phase="open", **_M)
    r = _row(db)
    assert r["jc_open_home"] == 2.0   # open backfilled
    assert r["jc_home"] == 2.0        # this open was also the latest → canonical


def test_open_is_set_once(tmp_path):
    db = str(tmp_path / "o.db")
    record_jingcai_sp(db, jc_home=2.0, jc_draw=3.2, jc_away=3.3,
                      source="sporttery", phase="open", **_M)
    record_jingcai_sp(db, jc_home=2.05, jc_draw=3.15, jc_away=3.25,  # cron ran twice
                      source="sporttery", phase="open", **_M)
    r = _row(db)
    assert r["jc_open_home"] == 2.0   # first 开售 line kept (set-once)


def test_migration_adds_open_columns(tmp_path):
    # An OLD table (pre open-columns) must gain them on the next ensure_ call.
    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE jingcai_sp (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "captured_at TEXT NOT NULL, source TEXT NOT NULL, match_date TEXT NOT NULL, "
        "home_team TEXT NOT NULL, away_team TEXT NOT NULL, "
        "market TEXT NOT NULL DEFAULT 'had', jc_home REAL, jc_draw REAL, jc_away REAL, "
        "settled_at TEXT, UNIQUE(match_date, home_team, away_team, market));"
    )
    con.commit()
    ensure_jingcai_sp_table(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(jingcai_sp)")}
    con.close()
    assert {"jc_open_home", "jc_open_draw", "jc_open_away", "opened_at"} <= cols
