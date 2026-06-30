"""竞彩 散户支持比例 capture — parse + upsert + fail-soft + settle-preserve."""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.jingcai_vote import (
    fetch_jingcai_vote,
    parse_vote_row,
    record_jingcai_vote,
)


def _raw(**over):
    base = {
        "matchDate": "2026-07-01 03:00",
        "matchNum": "周二001",
        "leagueAllName": "世界杯",
        "homeTeamAllName": "法国",
        "awayTeamAllName": "火星联队",  # deliberately unmappable
        "hsupportRate": "77%", "dsupportRate": "15%", "asupportRate": "8%",
        "win": "2589843", "draw": "491465", "lose": "273300",
        "hprobability": "77%", "dprobability": "15%", "aprobability": "8%",
        "herror": "0%", "derror": "0%", "aerror": "0%",
        "h": "1.16", "d": "5.80", "a": "10.50",
        "goalLine": "-1",
    }
    base.update(over)
    return base


def test_parse_maps_support_counts_and_keeps_unmapped_row():
    kw = parse_vote_row(_raw(), "had")
    assert kw is not None
    assert kw["match_date"] == "2026-07-01"  # time suffix trimmed
    assert kw["pool_code"] == "HAD"  # uppercased
    assert (kw["h_support"], kw["d_support"], kw["a_support"]) == (77.0, 15.0, 8.0)
    assert (kw["h_count"], kw["d_count"], kw["a_count"]) == (2589843, 491465, 273300)
    assert kw["handicap_home"] == -1
    assert (kw["jc_home"], kw["jc_draw"], kw["jc_away"]) == (1.16, 5.80, 10.50)
    # mappable home → canonical EN; unmappable away → None but the ROW IS KEPT
    assert kw["home_team"] and isinstance(kw["home_team"], str)
    assert kw["away_team"] is None


def test_parse_drops_row_missing_teams_or_support():
    assert parse_vote_row(_raw(homeTeamAllName=""), "had") is None
    assert parse_vote_row(
        _raw(hsupportRate="", dsupportRate="", asupportRate=""), "had") is None


def test_record_upserts_latest_and_preserves_settlement(tmp_path):
    db = tmp_path / "obs.db"
    kw = parse_vote_row(_raw(), "had")
    assert record_jingcai_vote(db, **kw) is True

    rows = fetch_jingcai_vote(db)
    assert len(rows) == 1 and rows[0]["h_support"] == 77.0

    # simulate the settler having filled the result
    with sqlite3.connect(db) as c:
        c.execute("UPDATE jingcai_vote SET home_goals=2, away_goals=0, "
                  "ft_outcome=0, settled_at='2026-07-01T22:00:00'")

    # a later same-day re-capture (crowd shifted 77→81) must UPDATE support but
    # NEVER clobber the settled result
    kw2 = parse_vote_row(_raw(hsupportRate="81%"), "had")
    assert record_jingcai_vote(db, **kw2) is True
    rows = fetch_jingcai_vote(db)
    assert len(rows) == 1  # upsert, not a duplicate
    assert rows[0]["h_support"] == 81.0  # latest crowd
    assert rows[0]["ft_outcome"] == 0 and rows[0]["home_goals"] == 2  # preserved


def test_record_failsoft_on_missing_keys(tmp_path):
    db = tmp_path / "obs.db"
    # missing match_date → no-op False, no raise
    assert record_jingcai_vote(
        db, match_date="", home_zh="A", away_zh="B", pool_code="HAD",
        h_support=50.0) is False
    # no support triple → no-op False
    assert record_jingcai_vote(
        db, match_date="2026-07-01", home_zh="A", away_zh="B",
        pool_code="HAD") is False


def test_had_and_hhad_are_separate_rows(tmp_path):
    db = tmp_path / "obs.db"
    record_jingcai_vote(db, **parse_vote_row(_raw(), "had"))
    record_jingcai_vote(db, **parse_vote_row(_raw(hsupportRate="40%"), "hhad"))
    rows = fetch_jingcai_vote(db)
    assert len(rows) == 2  # same match, two pools → two rows
    assert {r["pool_code"] for r in rows} == {"HAD", "HHAD"}
