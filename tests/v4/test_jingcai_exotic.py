"""竞彩冷门玩法 SP — 比分(crs)/总进球(ttg) long-format capture + settle.

Covers the sporttery pool extractors, the upsert-latest capture (result preserved
on re-price), the winning-outcome helpers (incl. 其他 buckets + 7+ collapse), and
the full settle path (winner hit=1, the rest hit=0) mirroring settle_jingcai_sp.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from nutmeg.v4.data.sources.sporttery import _crs_outcomes, _ttg_outcomes
from nutmeg.v4.observation.jingcai_exotic import (
    crs_winning_outcome,
    record_exotic_sp,
    settle_exotic_sp,
    ttg_winning_outcome,
)

# ----- realistic raw pools (note the *f flag keys + metadata that must be skipped)

_CRS_POOL = {
    "s00s00": "8.50", "s00s00f": "0",
    "s02s01": "9.75", "s02s01f": "0",
    "s01s00": "6.00", "s01s00f": "0",
    "s1sh": "5.50", "s1shf": "0",   # 胜其他
    "s1sd": "11.00", "s1sdf": "0",  # 平其他
    "s1sa": "8.00", "s1saf": "0",   # 负其他
    "goalLine": "0", "goalLineValue": "0", "updateTime": "2026-06-25 22:00",
}
_TTG_POOL = {
    "s0": "7.50", "s0f": "0", "s1": "4.20", "s2": "3.50",
    "s3": "3.80", "s7": "15.00", "s7f": "0", "goalLine": "0",
}


def _rows(db, market=None):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM jingcai_exotic_sp"
    args: tuple = ()
    if market:
        q += " WHERE market=?"
        args = (market,)
    out = [dict(r) for r in con.execute(q, args).fetchall()]
    con.close()
    return out


# ----------------------------------------------------------------- extractors

def test_crs_extractor_parses_scores_and_other_buckets():
    got = _crs_outcomes(_CRS_POOL)
    assert got["0:0"] == 8.50 and got["2:1"] == 9.75 and got["1:0"] == 6.00
    assert got["胜其他"] == 5.50 and got["平其他"] == 11.00 and got["负其他"] == 8.00
    # flags + metadata never leak in as outcomes
    assert not any(k.endswith("f") for k in got)
    assert "goalLine" not in got and "updateTime" not in got
    assert len(got) == 6


def test_ttg_extractor_parses_buckets_skips_flags():
    got = _ttg_outcomes(_TTG_POOL)
    assert got == {"0": 7.50, "1": 4.20, "2": 3.50, "3": 3.80, "7": 15.00}


def test_extractors_empty_on_none_or_junk():
    assert _crs_outcomes(None) == {} and _crs_outcomes({}) == {}
    assert _ttg_outcomes(None) == {} and _ttg_outcomes({"goalLine": "0"}) == {}


# --------------------------------------------------------------- winning outcome

def test_crs_winning_exact_when_offered():
    offered = {"2:1", "1:0", "0:0"}
    assert crs_winning_outcome(2, 1, offered) == "2:1"


def test_crs_winning_falls_back_to_other_bucket():
    offered = {"2:1", "1:0"}                       # 4:0 not in the grid
    assert crs_winning_outcome(4, 0, offered) == "胜其他"
    assert crs_winning_outcome(3, 3, offered) == "平其他"
    assert crs_winning_outcome(0, 5, offered) == "负其他"


def test_ttg_winning_sums_and_collapses_seven_plus():
    assert ttg_winning_outcome(2, 1) == "3"
    assert ttg_winning_outcome(0, 0) == "0"
    assert ttg_winning_outcome(5, 4) == "7"        # 9 goals → '7' (7+)


# ------------------------------------------------------------------- capture

_M = dict(match_date="2026-06-25", home_team="Mexico", away_team="South Africa")


def test_record_writes_one_row_per_outcome(tmp_path):
    db = str(tmp_path / "e.db")
    n_crs = record_exotic_sp(db, market="crs", outcomes=_crs_outcomes(_CRS_POOL), **_M)
    n_ttg = record_exotic_sp(db, market="ttg", outcomes=_ttg_outcomes(_TTG_POOL), **_M)
    assert n_crs == 6 and n_ttg == 5
    assert len(_rows(db)) == 11
    crs = {r["outcome"]: r["jc_sp"] for r in _rows(db, "crs")}
    assert crs["2:1"] == 9.75 and crs["胜其他"] == 5.50


def test_record_noop_on_empty(tmp_path):
    db = str(tmp_path / "e.db")
    assert record_exotic_sp(db, market="crs", outcomes={}, **_M) == 0
    assert record_exotic_sp(db, market="crs", outcomes={"2:1": 9.0},
                            home_team="", away_team="B", match_date="2026-06-25") == 0


def test_recapture_updates_price_keeps_result(tmp_path):
    db = str(tmp_path / "e.db")
    record_exotic_sp(db, market="ttg", outcomes={"3": 3.8}, **_M)
    # settle it, then re-price (latest=终盘): the SP moves, the result must survive
    settle_exotic_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 2, 1)],
                     today=dt.date(2026, 6, 26))
    record_exotic_sp(db, market="ttg", outcomes={"3": 3.5}, **_M)
    r = _rows(db, "ttg")[0]
    assert r["jc_sp"] == 3.5            # re-priced
    assert r["hit"] == 1 and r["settled_at"]   # 2+1=3 goals → '3' hit, preserved


# ------------------------------------------------------------------- settle

def _fx(home, away, hg, ag):
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": {"home": hg, "away": ag},
    }


def test_settle_marks_winner_and_losers(tmp_path):
    db = str(tmp_path / "e.db")
    record_exotic_sp(db, market="crs", outcomes=_crs_outcomes(_CRS_POOL), **_M)
    record_exotic_sp(db, market="ttg", outcomes=_ttg_outcomes(_TTG_POOL), **_M)

    def fetch(d: dt.date):
        assert d == dt.date(2026, 6, 25)
        return [_fx("Mexico", "South Africa", 2, 1)]   # 比分 2:1 → 总进球 3

    n = settle_exotic_sp(db, fetch_fixtures=fetch, today=dt.date(2026, 6, 26))
    assert n == 11
    crs = {r["outcome"]: r["hit"] for r in _rows(db, "crs")}
    assert crs["2:1"] == 1 and crs["1:0"] == 0 and crs["胜其他"] == 0
    ttg = {r["outcome"]: r["hit"] for r in _rows(db, "ttg")}
    assert ttg["3"] == 1 and ttg["2"] == 0
    assert all(r["home_goals"] == 2 and r["away_goals"] == 1 for r in _rows(db))


def test_settle_uses_other_bucket_for_out_of_grid_score(tmp_path):
    db = str(tmp_path / "e.db")
    record_exotic_sp(db, market="crs", outcomes=_crs_outcomes(_CRS_POOL), **_M)
    # 5:0 is not an offered exact score → 胜其他 must be the hit
    settle_exotic_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 5, 0)],
                     today=dt.date(2026, 6, 26))
    crs = {r["outcome"]: r["hit"] for r in _rows(db, "crs")}
    assert crs["胜其他"] == 1 and sum(crs.values()) == 1   # exactly one winner


def test_settle_skips_future(tmp_path):
    db = str(tmp_path / "e.db")
    record_exotic_sp(db, market="ttg", outcomes={"3": 3.8}, **_M)
    called: list = []
    n = settle_exotic_sp(db, fetch_fixtures=lambda d: called.append(d) or [],
                         today=dt.date(2026, 6, 24))   # match 06-25 is in the future
    assert n == 0 and called == []
