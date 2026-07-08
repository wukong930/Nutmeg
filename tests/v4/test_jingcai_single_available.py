"""2026-07-08 — 竞彩 单关/过关 (single-bet availability) capture → jingcai_sp.

竞彩 marks each match's markets as 单关-bettable (single) or 过关-only (parlay) —
its own confidence signal + a free covariate for every 竞彩 analysis. PROBED
2026-07-08 against the live feed: the flag is PER-POOL (``poolList[].bettingSingle``);
the sub-match-level ``bettingSingle`` is ALWAYS 0 (useless). The same match can be
单关 on 胜平负 but 过关-only on 让球 → it maps to jingcai_sp's per-market row.
Forward-only (live feed carries no history) → captured on every harvest.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nutmeg.v4.data.sources.sporttery import _single_by_pool
from nutmeg.v4.observation.jingcai_sp import (
    ensure_jingcai_sp_table,
    record_jingcai_sp,
)


def test_single_by_pool_is_per_pool_not_match_level() -> None:
    # match-level bettingSingle is always 0 and MUST be ignored; pool-level wins.
    g = {
        "bettingSingle": 0, "bettingAllUp": 0,   # decoy match-level fields
        "poolList": [
            {"poolCode": "HAD", "bettingSingle": 1, "bettingAllup": 1},
            {"poolCode": "HHAD", "bettingSingle": 0, "bettingAllup": 1},
        ],
    }
    assert _single_by_pool(g) == {"had": 1, "hhad": 0}


def test_single_by_pool_handles_missing_and_garbage() -> None:
    assert _single_by_pool({}) == {}
    assert _single_by_pool({"poolList": []}) == {}
    assert _single_by_pool({"poolList": [{"poolCode": "HAD"}]}) == {}            # no flag
    assert _single_by_pool({"poolList": [{"bettingSingle": 1}]}) == {}           # no code
    assert _single_by_pool(
        {"poolList": [{"poolCode": "HAD", "bettingSingle": "x"}]}) == {}         # non-int


def test_record_stores_single_available(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    assert record_jingcai_sp(
        db, match_date="2026-07-10", home_team="A", away_team="B",
        jc_home=2.0, jc_draw=3.0, jc_away=4.0, market="had", single_available=1)
    with sqlite3.connect(db) as c:
        row = c.execute(
            "SELECT single_available FROM jingcai_sp WHERE market='had'").fetchone()
    assert row[0] == 1


def test_recapture_without_flag_preserves_stored(tmp_path: Path) -> None:
    # a manual re-pin carries no single flag → must NOT null out the last-known value
    # (mirrors the psc_* COALESCE-preserve rule).
    db = tmp_path / "t.db"
    record_jingcai_sp(db, match_date="2026-07-10", home_team="A", away_team="B",
                      jc_home=2.0, jc_draw=3.0, jc_away=4.0, market="had",
                      single_available=1)
    record_jingcai_sp(db, match_date="2026-07-10", home_team="A", away_team="B",
                      jc_home=2.1, jc_draw=3.1, jc_away=4.1, market="had",
                      single_available=None)
    with sqlite3.connect(db) as c:
        row = c.execute(
            "SELECT single_available, jc_home FROM jingcai_sp WHERE market='had'").fetchone()
    assert row[0] == 1     # flag preserved
    assert row[1] == 2.1   # line still updated to latest


def test_migration_adds_column_to_legacy_table(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as c:
        # a realistic pre-single_available table: has settled_at (the DDL's
        # idx_jingcai_sp_unsettled index needs it) but lacks single_available.
        c.execute("CREATE TABLE jingcai_sp (id INTEGER PRIMARY KEY, match_date TEXT, "
                  "home_team TEXT, away_team TEXT, market TEXT, jc_home REAL, jc_draw REAL, "
                  "jc_away REAL, settled_at TEXT, "
                  "UNIQUE(match_date, home_team, away_team, market))")
        ensure_jingcai_sp_table(c)
        cols = {r[1] for r in c.execute("PRAGMA table_info(jingcai_sp)")}
    assert "single_available" in cols


def test_harvest_wires_single_per_market(tmp_path: Path, monkeypatch) -> None:
    # end-to-end wiring: a match dict's per-market `single` reaches the DB row.
    monkeypatch.chdir(tmp_path)   # isolate the logs/ unmapped-report side effect
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = tmp_path / "t.db"
    match = {
        "match_date": "2026-07-10", "kickoff_utc": None, "match_num": "周四097",
        "league_cn": "世界杯", "home_cn": "法国", "away_cn": "摩洛哥",
        "home_en": "France", "away_en": "Morocco",
        "had": (1.5, 3.8, 5.4), "hhad": (2.55, 3.05, 2.51, -1),
        "crs": {}, "ttg": {}, "single": {"had": 1, "hhad": 0},
    }
    r = harvest_to_db(db, matches=[match], protect_manual=False)
    assert r["had"] == 1 and r["hhad"] == 1
    with sqlite3.connect(db) as c:
        rows = dict(c.execute(
            "SELECT market, single_available FROM jingcai_sp").fetchall())
    assert rows == {"had": 1, "hhad": 0}
