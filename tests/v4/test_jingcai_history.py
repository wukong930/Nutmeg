"""2026-07-09 — 竞彩 历史赔率走势回填(getFixedBonusV1)parse + store 单测.

Pure-logic tests on an inline fixture (no network). Cross-checks the parse against
the real 2032775 values (欧冠 萨尔茨堡-布兰 2025-07-29, verified live vs the sporttery
site screenshot). Network wrappers (fetch_fixed_bonus / fetch_match_list) are
live-verified, not unit-tested here. `记忆 jingcai-fixedbonus-history-endpoint`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nutmeg.v4.data.sources.sporttery_history import (
    parse_fixed_bonus,
    parse_match_list,
)
from nutmeg.v4.observation.jingcai_history import record_history_match

# inline getFixedBonusV1 `value` (real 2032775 numbers, trimmed to 2 rows/market)
FB = {
    "sectionsNo999": "1:1",
    "oddsHistory": {
        "matchId": 2032775, "leagueId": 69,
        "leagueAbbName": "欧冠", "leagueAllName": "欧洲冠军联赛",
        "homeTeamAbbName": "萨尔茨堡", "awayTeamAbbName": "布兰",
        "hadList": [
            {"h": "1.34", "d": "4.68", "a": "5.90", "updateDate": "2025-07-29",
             "updateTime": "09:26:30", "goalLine": ""},
            {"h": "1.30", "d": "4.95", "a": "6.35", "updateDate": "2025-07-30",
             "updateTime": "21:25:16", "goalLine": ""},
        ],
        "hhadList": [
            {"h": "2.05", "d": "3.62", "a": "2.74", "updateDate": "2025-07-29",
             "updateTime": "09:26:30", "goalLine": "-1"},
            {"h": "1.93", "d": "3.75", "a": "2.90", "updateDate": "2025-07-30",
             "updateTime": "21:25:08", "goalLine": "-1"},
        ],
        "singleList": [{"poolCode": "HAD", "single": 0}, {"poolCode": "HHAD", "single": 0}],
    },
}


def test_parse_fixed_bonus_matches_known_values() -> None:
    p = parse_fixed_bonus(FB)
    assert p["match_id"] == 2032775
    assert p["league_cn"] == "欧冠"
    assert p["close_date"] == "2025-07-30" and p["open_date"] == "2025-07-29"
    assert (p["home_goals"], p["away_goals"]) == (1, 1)
    assert p["single"] == {"had": 0, "hhad": 0}
    had, hhad = p["series"]["had"], p["series"]["hhad"]
    assert (had[0]["h"], had[0]["d"], had[0]["a"]) == (1.34, 4.68, 5.90)   # 初盘
    assert (had[-1]["h"], had[-1]["d"], had[-1]["a"]) == (1.30, 4.95, 6.35)  # 终盘
    assert hhad[0]["goal_line"] == -1


def test_parse_returns_none_on_empty() -> None:
    assert parse_fixed_bonus({}) is None
    assert parse_fixed_bonus({"oddsHistory": {"hadList": [], "hhadList": []}}) is None


def test_series_drops_implausible_triple() -> None:
    fb = {"oddsHistory": {"matchId": 1, "hadList": [
        {"h": "1.00", "d": "3", "a": "5"},        # h≤1.0 → whole row dropped
        {"h": "1.5", "d": "3", "a": "5", "updateDate": "2025-01-01", "updateTime": "00:00:00"},
    ]}}
    p = parse_fixed_bonus(fb)
    assert len(p["series"]["had"]) == 1 and p["series"]["had"][0]["h"] == 1.5


def test_record_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    p = parse_fixed_bonus(FB)
    n1 = record_history_match(db, p)
    assert n1 == 4  # 2 had + 2 hhad
    record_history_match(db, p)  # re-ingest (delete-then-insert)
    with sqlite3.connect(db) as c:
        total = c.execute("SELECT COUNT(*) FROM jingcai_odds_history").fetchone()[0]
        close = c.execute("SELECT d, home_goals, single_available FROM jingcai_odds_history "
                          "WHERE market='had' ORDER BY seq DESC LIMIT 1").fetchone()
    assert total == 4                      # no dupes
    assert close == (4.95, 1, 0)           # 终盘 draw odds + result + single flag


def test_date_chunks() -> None:
    from nutmeg.v4.cli.ingest_jingcai_history import _date_chunks
    assert list(_date_chunks("2025-05-01", "2025-05-14", 14)) == [("2025-05-01", "2025-05-14")]
    assert list(_date_chunks("2025-05-01", "2025-05-20", 14)) == [
        ("2025-05-01", "2025-05-14"), ("2025-05-15", "2025-05-20")]
    assert list(_date_chunks("2025-05-01", "2025-05-01", 14)) == [("2025-05-01", "2025-05-01")]


def test_parse_match_list_enumeration() -> None:
    val = {"matchResult": [
        {"matchId": 2032770, "leagueId": 69, "leagueNameAbbr": "欧冠",
         "leagueName": "欧洲冠军联赛", "matchDate": "2025-07-30"},
        {"noMatchId": 1},  # skipped
    ]}
    got = parse_match_list(val)
    assert got == [{"match_id": 2032770, "league_id": 69, "league_cn": "欧冠",
                    "match_date": "2025-07-30"}]
    assert parse_match_list({}) == []
