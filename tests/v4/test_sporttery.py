"""中国体育彩票 (竞彩) source — parse, name mapping, fail-soft."""
from __future__ import annotations

from nutmeg.v4.data.sources import sporttery


def _payload():
    return {"success": True, "value": {"matchInfoList": [
        {"subMatchList": [
            {"homeTeamAllName": "墨西哥", "awayTeamAllName": "南非",
             "matchDate": "2026-06-12", "matchNumStr": "周四001",
             "leagueAbbName": "世界杯",
             "had": {"h": "1.26", "d": "4.45", "a": "9.00"},
             "hhad": {"h": "2.00", "d": "3.25", "a": "3.11", "goalLine": "-1"}},
            {"homeTeamAllName": "火星联队", "awayTeamAllName": "月球联队",  # unmapped
             "matchDate": "2026-06-12", "matchNumStr": "周四099",
             "had": {"h": "2.0", "d": "3.0", "a": "3.5"}, "hhad": {}},
        ]}
    ]}}


def test_parse_had_hhad_and_map(monkeypatch):
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: _payload())
    ms = sporttery.fetch_lottery_matches()
    assert len(ms) == 2
    mex = ms[0]
    assert mex["home_en"] == "Mexico"          # 墨西哥 → canonical English
    assert mex["away_en"] is not None
    assert mex["had"] == (1.26, 4.45, 9.00)
    assert mex["hhad"] == (2.00, 3.25, 3.11, -1)   # incl. goalLine as int
    assert mex["match_date"] == "2026-06-12"
    # second match: unmapped team + no 让球 pool
    assert ms[1]["home_en"] is None and ms[1]["hhad"] is None


def test_zh_to_canonical():
    assert sporttery.zh_to_canonical("墨西哥") == "Mexico"
    assert sporttery.zh_to_canonical("不存在的队名") is None
    assert sporttery.zh_to_canonical(None) is None


def test_synonym_override_to_live_name():
    """TEAM_NAME_ZH's English ('Korea Republic') is corrected to the live
    odds_snapshots/settler name ('South Korea') so 竞彩 rows actually join."""
    zh = next((z for z, en in sporttery._ZH_TO_EN.items() if en == "Korea Republic"), None)
    assert zh is not None
    assert sporttery.zh_to_canonical(zh) == "South Korea"     # overridden
    zh_mex = next(z for z, en in sporttery._ZH_TO_EN.items() if en == "Mexico")
    assert sporttery.zh_to_canonical(zh_mex) == "Mexico"      # un-overridden passthrough


def test_fail_soft_returns_empty(monkeypatch):
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: None)
    assert sporttery.fetch_lottery_matches() == []


def test_incomplete_odds_dropped(monkeypatch):
    bad = {"success": True, "value": {"matchInfoList": [{"subMatchList": [
        {"homeTeamAllName": "墨西哥", "awayTeamAllName": "南非", "matchDate": "2026-06-12",
         "had": {"h": "1.26"}, "hhad": None},   # incomplete had, no hhad
    ]}]}}
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: bad)
    m = sporttery.fetch_lottery_matches()[0]
    assert m["had"] is None and m["hhad"] is None
