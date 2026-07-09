"""§H Pinnacle-close 历史机器 + EPL join 别名的核心不变量。"""
import sqlite3

from nutmeg.v4.data.sources.odds_api import _norm_team
from nutmeg.v4.data.sources.odds_api_history import parse_pinnacle_close
from nutmeg.v4.observation.pinnacle_close_history import record_close


def _snapshot():
    """最小 Odds API 历史快照:一场有 Pinnacle(h2h+totals),一场无 Pinnacle(应跳过)。"""
    return {
        "timestamp": "2024-11-09T17:55:38Z",
        "data": [
            {"commence_time": "2024-11-09T18:00:00Z", "home_team": "Ajax", "away_team": "PSV",
             "bookmakers": [{"key": "pinnacle", "markets": [
                 {"key": "h2h", "outcomes": [{"name": "Ajax", "price": 2.1},
                                             {"name": "PSV", "price": 3.2},
                                             {"name": "Draw", "price": 3.5}]},
                 {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5},
                                                {"name": "Under", "price": 1.95}]},
             ]}]},
            {"commence_time": "2024-11-09T20:00:00Z", "home_team": "X", "away_team": "Y",
             "bookmakers": [{"key": "betfair", "markets": []}]},  # 无 pinnacle → 跳过
        ],
    }


def test_parse_pinnacle_close_only_pinnacle():
    rows = parse_pinnacle_close(_snapshot())
    assert len(rows) == 1
    r = rows[0]
    assert r["home_team"] == "Ajax"
    assert (r["p_home"], r["p_draw"], r["p_away"]) == (2.1, 3.5, 3.2)
    assert (r["ou_line"], r["over"], r["under"]) == (2.5, 1.9, 1.95)


def test_record_close_keeps_tightest(tmp_path):
    db = tmp_path / "t.db"
    row = {"commence_time": "2024-11-09T18:00:00Z", "home_team": "Ajax", "away_team": "PSV",
           "p_home": 2.1, "p_draw": 3.5, "p_away": 3.2, "ou_line": 2.5, "over": 1.9, "under": 1.95}
    record_close(db, row, snapshot_utc="2024-11-09T00:00:00Z")               # stale 先
    record_close(db, {**row, "p_home": 2.05}, snapshot_utc="2024-11-09T17:55:00Z")  # 更紧→覆盖
    record_close(db, {**row, "p_home": 9.99}, snapshot_utc="2024-11-09T12:00:00Z")  # 更早→不覆盖
    conn = sqlite3.connect(str(db))
    snap, ph = conn.execute("SELECT snapshot_utc, p_home FROM pinnacle_close_history").fetchone()
    assert snap == "2024-11-09T17:55:00Z"
    assert ph == 2.05


def test_epl_join_aliases_converge():
    """竞彩短名 canonical ↔ Odds API 长官方名,_norm_team 必须收敛到同一 key。"""
    pairs = [("Wolves", "Wolverhampton Wanderers"), ("Tottenham", "Tottenham Hotspur"),
             ("Leicester", "Leicester City"), ("Ipswich", "Ipswich Town"),
             ("Newcastle", "Newcastle United"), ("West Ham", "West Ham United"),
             ("Brighton", "Brighton and Hove Albion")]
    for short, long in pairs:
        assert _norm_team(short) == _norm_team(long), f"{short} != {long}"
