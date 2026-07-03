"""中国体育彩票 (竞彩) source — parse, name mapping, fail-soft."""
from __future__ import annotations

from nutmeg.v4.data.sources import sporttery


def _payload():
    return {"success": True, "value": {"matchInfoList": [
        {"subMatchList": [
            {"homeTeamAllName": "墨西哥", "awayTeamAllName": "南非",
             "matchDate": "2026-06-12", "matchTime": "07:00:00", "matchNumStr": "周四001",
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
    assert mex["match_date"] == "2026-06-11"   # 07:00 北京 → 前一 UTC 日
    assert mex["kickoff_utc"] == "2026-06-11T23:00:00+00:00"
    # second match: unmapped team + no 让球 pool
    assert ms[1]["home_en"] is None and ms[1]["hhad"] is None


def test_beijing_to_utc_date():
    """竞彩 matchDate is the Beijing (UTC+8) date; the join keys on the UTC date,
    so an early-morning Beijing kickoff must roll back to the previous UTC day."""
    f = sporttery._utc_date_and_kickoff
    assert f("2026-06-12", "07:00:00") == ("2026-06-11", "2026-06-11T23:00:00+00:00")
    assert f("2026-06-12", "20:00:00")[0] == "2026-06-12"   # 20:00 北京 → 同 UTC 日
    assert f("2026-06-12", None) == ("2026-06-12", None)     # no time → fallback


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


def test_club_prefix_override():
    """Club gather names are RAW API-Football (with prefixes); the override maps
    TEAM_NAME_ZH's cleaned key to the live name so 竞彩 league rows join."""
    zh = next((z for z, en in sporttery._ZH_TO_EN.items() if en == "Freiburg"), None)
    assert zh is not None
    assert sporttery.zh_to_canonical(zh) == "SC Freiburg"


def test_harvest_to_db_counts(tmp_path):
    """harvest_to_db (shared by CLI + 🎯 刷新竞彩 endpoint) writes mapped matches +
    skips unmapped, returning the counts."""
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = str(tmp_path / "obs.db")
    matches = [
        {"home_en": "Mexico", "away_en": "South Africa", "league_cn": "WC",
         "match_date": "2026-06-20", "kickoff_utc": None,
         "had": (1.7, 3.4, 4.5), "hhad": (2.0, 3.2, 3.3, -1)},
        {"home_en": None, "away_en": "X", "league_cn": "WC",  # unmapped → skipped
         "match_date": "2026-06-20", "had": (2.0, 3.0, 3.5), "hhad": None},
    ]
    r = harvest_to_db(db, matches=matches)
    assert r["matches"] == 2 and r["mapped"] == 1 and r["unmapped"] == 1
    assert r["had"] == 1 and r["hhad"] == 1


def test_finnish_zh_override():
    """芬超 (market-mode league) — 竞彩's descriptive 中文 maps to the live cup-market
    gather name so the 竞彩 SP pre-fills (was 4/6 matches blank: 体检 2026-06-13)."""
    assert sporttery.zh_to_canonical("坦佩雷山猫") == "Ilves"            # Tampere Lynx
    assert sporttery.zh_to_canonical("赫尔辛基火花") == "Gnistan"        # Helsinki Spark
    assert sporttery.zh_to_canonical("国际图尔库") == "Inter Turku"
    assert sporttery.zh_to_canonical("AC奥卢") == "AC Oulu"


def test_kleague_zh_override():
    """韩职 — 竞彩挂出 7-4/7-5 SP 但 6 个队名不在字典 → 每场恰好半边失配 → 6/6 场
    被 ingest 静默丢弃 (体检 2026-07-03)。对照 KOR_K_LEAGUE_1 gather 真实拼写补齐;
    济州SK 是俱乐部改名,API-Football 仍叫 Jeju United FC。"""
    assert sporttery.zh_to_canonical("安养FC") == "FC Anyang"
    assert sporttery.zh_to_canonical("富川FC") == "Bucheon FC 1995"
    assert sporttery.zh_to_canonical("江原FC") == "Gangwon FC"
    assert sporttery.zh_to_canonical("首尔FC") == "FC Seoul"
    assert sporttery.zh_to_canonical("光州FC") == "Gwangju FC"
    assert sporttery.zh_to_canonical("济州SK") == "Jeju United FC"
    # 之前就映射成功的一侧不受影响
    assert sporttery.zh_to_canonical("浦项制铁") == "Pohang Steelers"


def test_harvest_protect_manual_toggle(tmp_path):
    """The cron (protect_manual=True) preserves a hand-priced row; the 🎯 刷新竞彩
    endpoint (protect_manual=False) overwrites the stale market_mode capture with the
    latest official SP — otherwise the button fetches fresh data but can't show it."""
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup, record_jingcai_sp
    db = str(tmp_path / "obs.db")
    key = ("2026-06-20", "Mexico", "South Africa")
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.78, jc_draw=3.4, jc_away=4.5,
                      market="had", source="market_mode")        # stale hand-capture
    fresh = [{"home_en": "Mexico", "away_en": "South Africa", "league_cn": "WC",
              "match_date": "2026-06-20", "kickoff_utc": None,
              "had": (1.71, 3.5, 4.7), "hhad": None}]
    harvest_to_db(db, matches=fresh, protect_manual=True)         # cron: blocked
    assert fetch_sp_lookup(db, market="had")[key][0] == 1.78
    harvest_to_db(db, matches=fresh, protect_manual=False)        # 🎯: overwrites
    assert fetch_sp_lookup(db, market="had")[key][0] == 1.71


def test_attach_jingcai_sp_normalizes_team_names(tmp_path, monkeypatch):
    """市场模式/近期赛事 boards key on API-Football names ('Czechia'), but jingcai_sp
    stores the sporttery/Odds-API spelling ('Czech Republic'). _attach_jingcai_sp must
    normalize both sides so the SP pre-fill still joins — else the 竞彩 SP boxes stay
    empty (the bug seen on 捷克 vs 南非, 2026-06-19)."""
    import datetime

    from nutmeg.v4.api import routes
    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-18", home_team="Czech Republic",
                      away_team="South Africa", jc_home=1.66, jc_draw=3.6, jc_away=4.35,
                      market="had", source="sporttery")
    monkeypatch.setattr(routes, "_observation_db_path", lambda: db)

    class _Pred:
        date = datetime.date(2026, 6, 18)
        home_team = "Czechia"            # API-Football spelling, diverges from jingcai_sp
        away_team = "South Africa"
        jc_home = jc_draw = jc_away = jc_source = None
        jc_hc_home = jc_hc_draw = jc_hc_away = jc_hc_line = None

    p = _Pred()
    routes._attach_jingcai_sp([p])
    assert p.jc_home == 1.66 and p.jc_away == 4.35  # joined across Czechia↔Czech Republic


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


class TestOdds3SanityGuard:
    """体检 A3 (2026-07-01) — 竞彩 SP is the ×SP term in EV; a freeze/placeholder
    artifact ('0'/'999') must not be stored as a real odds line (real SP: 1.13–13.5)."""

    def test_valid_pool_parses(self):
        assert sporttery._odds3({"h": "1.85", "d": "3.4", "a": "4.2"}) == (1.85, 3.4, 4.2)

    def test_rejects_sub_unity(self):
        assert sporttery._odds3({"h": "0", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "1.0", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "0.3", "d": "3.4", "a": "4.2"}) is None

    def test_rejects_absurd(self):
        assert sporttery._odds3({"h": "1.85", "d": "3.4", "a": "9999"}) is None

    def test_rejects_negative_and_nonnumeric(self):
        assert sporttery._odds3({"h": "-2", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "x", "d": "3.4", "a": "4.2"}) is None

    def test_incomplete_pool_is_none(self):
        assert sporttery._odds3(None) is None
        assert sporttery._odds3({"h": "1.85"}) is None
