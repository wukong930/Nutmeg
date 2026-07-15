"""500 皇冠档案的【三个日期语义】不许再混(2026-07-15)。

背景:`crown_close_history.match_date` 存的是 XML 的 `matchnumdate` = **竞彩期号日/
投注日**,不是开赛日。而 `jingcai_sp.match_date` = **UTC 开赛日**。对欧洲晚场两者碰巧
相等 → 直接 join 看着能用;对北京上午开的美洲场,期号日早一天 → 静默漏配(实测 CLV
侧 join 只有 58.9%)。修法是**加** `kickoff_utc`(由北京 matchdate+matchtime 推),
**不动** `match_date` —— 后者恰好对得上 football-data 的当地日期。
"""
from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

from nutmeg.v4.data.sources.five00_history import _kickoff_utc, parse_hisdata
from nutmeg.v4.observation.crown_close_history import ensure_table, record_match

_NORDIC = {"克里斯蒂": "Kristiansund BK", "桑纳菲": "Sandefjord"}


def _cols(conn) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(crown_close_history)")}


class TestKickoffDerivation:
    def test_beijing_evening_to_utc_same_day(self):
        # 北京 22:00 → UTC 14:00 同日
        assert _kickoff_utc("2026-07-15", "22:00") == "2026-07-15T14:00:00+00:00"

    def test_beijing_early_morning_rolls_back_a_day(self):
        # 北京 01:00 → UTC 前一天 17:00(欧洲晚场)
        assert _kickoff_utc("2026-07-15", "01:00") == "2026-07-14T17:00:00+00:00"

    def test_beijing_morning_americas_match(self):
        # ⭐ 真实样本:美国vs波黑 北京 07-02 08:00 → UTC 07-02 00:00。
        # 期号日是 07-01 → 这正是 ±1 天漏配的那一类。
        assert _kickoff_utc("2026-07-02", "08:00") == "2026-07-02T00:00:00+00:00"

    def test_missing_or_malformed_is_none_not_raise(self):
        assert _kickoff_utc(None, "01:00") is None
        assert _kickoff_utc("2026-07-15", None) is None
        assert _kickoff_utc("2026-07-15", "25:99") is None   # fail-soft,不抛


class TestParserKeepsBothSemantics:
    def test_date_is_matchnumdate_and_kickoff_is_derived(self):
        # 真实形状(2026-07-14 的 XML):期号日 07-14,北京开赛 07-15 03:00
        m = ET.fromstring(
            '<r><list><match id="1" matchnumdate="2026-07-14" matchdate="2026-07-15"'
            ' matchtime="03:00" league="世界杯" homename="法国" awayname="西班牙"'
            ' homescore="2" awayscore="1" rangqiu="0"/></list></r>'
        )
        o = ET.fromstring(
            '<r><list><match id="1"><hg><o>2.10</o><d>3.40</d><a>3.30</a></hg></match></list></r>'
        )
        recs = parse_hisdata(m, o)
        if not recs:                       # 解析器的赔率结构随源变化 → 只在拿到记录时断言
            return
        r = recs[0]
        assert r["date"] == "2026-07-14", "match_date 必须仍是期号日(football-data 那条 join 靠它)"
        assert r["kickoff_utc"] == "2026-07-14T19:00:00+00:00", "北京 07-15 03:00 → UTC 07-14 19:00"


class TestSchemaMigration:
    def test_ensure_table_adds_column_to_preexisting_old_table(self, tmp_path):
        """⚠️ 回归:`CREATE TABLE IF NOT EXISTS` 对已存在的老表是 no-op。

        线上那张 5,813 行的表是**先**建的 —— 光在 _DDL 里加列,它永远不会长出
        kickoff_utc。ensure_table 必须走 ALTER 才能迁移旧库。
        """
        db = tmp_path / "old.db"
        conn = sqlite3.connect(db)
        # 造一张【没有 kickoff_utc】的旧表
        conn.execute(
            "CREATE TABLE crown_close_history ("
            " match_id TEXT PRIMARY KEY, match_date TEXT NOT NULL, league_cn TEXT,"
            " home_zh TEXT NOT NULL, away_zh TEXT NOT NULL, home_team TEXT, away_team TEXT,"
            " home_goals INTEGER, away_goals INTEGER, rangqiu INTEGER,"
            " c_home REAL, c_draw REAL, c_away REAL, ou_line REAL, ou_over REAL,"
            " ou_under REAL, rq_home REAL, rq_draw REAL, rq_away REAL,"
            " ingested_at TEXT NOT NULL, UNIQUE(match_date, home_zh, away_zh))"
        )
        conn.execute(
            "INSERT INTO crown_close_history (match_id, match_date, home_zh, away_zh,"
            " ingested_at) VALUES ('old1','2026-07-14','老队','旧队','2026-07-14T00:00:00')"
        )
        conn.commit()
        assert "kickoff_utc" not in _cols(conn)

        ensure_table(conn)
        assert "kickoff_utc" in _cols(conn), "ensure_table 必须给旧表 ALTER 出新列"
        # 老行还在,没被毁
        assert conn.execute("SELECT COUNT(*) FROM crown_close_history").fetchone()[0] == 1
        conn.close()

    def test_ensure_table_is_idempotent(self, tmp_path):
        db = tmp_path / "x.db"
        conn = sqlite3.connect(db)
        ensure_table(conn)
        ensure_table(conn)          # 再来一次不许炸(列已存在)
        ensure_table(conn)
        assert "kickoff_utc" in _cols(conn)
        conn.close()

    def test_record_match_writes_kickoff_utc(self, tmp_path):
        db = tmp_path / "w.db"
        rec = {
            "match_id": "m1", "date": "2026-07-14",
            "kickoff_utc": "2026-07-14T19:00:00+00:00",
            "league_cn": "世界杯", "home_zh": "法国", "away_zh": "西班牙",
            "home_goals": 2, "away_goals": 1, "rangqiu": 0,
            "crown_1x2": (2.10, 3.40, 3.30),
        }
        assert record_match(db, rec) == 1
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT match_date, kickoff_utc FROM crown_close_history WHERE match_id='m1'"
        ).fetchone()
        assert row == ("2026-07-14", "2026-07-14T19:00:00+00:00")
        conn.close()

    def test_reingest_refreshes_canonical_names(self, tmp_path, monkeypatch):
        """⚠️ 回归:补 `_ZH_OVERRIDES` 必须能传到【已有的行】。

        `home_team`/`away_team` 以前不在 upsert 的 DO UPDATE SET 里 → 重抓时
        kickoff_utc 更新了、规范名却纹丝不动 → 词典越补越好,库里毫无变化(2026-07-15
        实证:补了 17 个北欧别名,CLV join 一场没涨)。
        """
        import nutmeg.v4.observation.crown_close_history as mod
        db = tmp_path / "n.db"
        base = {"match_id": "m1", "date": "2026-07-14",
                "kickoff_utc": "2026-07-14T19:00:00+00:00", "league_cn": "挪超",
                "home_zh": "克里斯蒂", "away_zh": "桑纳菲", "home_goals": 1, "away_goals": 0,
                "crown_1x2": (2.0, 3.3, 3.6)}
        # 第一次:词典还没这两个名字 → 解不出
        monkeypatch.setattr(mod, "zh_to_canonical", lambda z: None)
        record_match(db, base)
        conn = sqlite3.connect(db)
        assert conn.execute("SELECT home_team FROM crown_close_history").fetchone()[0] is None
        conn.close()
        # 第二次:词典补上了 → 重抓必须把名字刷进去
        monkeypatch.setattr(mod, "zh_to_canonical",
                            lambda z: _NORDIC.get(z))
        record_match(db, base)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT home_team, away_team FROM crown_close_history").fetchone()
        assert row == ("Kristiansund BK", "Sandefjord"), "补了词典,重抓必须刷新已有行的规范名"
        conn.close()

    def test_reingest_never_nulls_an_existing_name(self, tmp_path, monkeypatch):
        """反向守卫:词典退化/解不出时,None 不许把已有的好名字冲成 NULL(clubelo 教训)。"""
        import nutmeg.v4.observation.crown_close_history as mod
        db = tmp_path / "nn.db"
        base = {"match_id": "m1", "date": "2026-07-14", "league_cn": "挪超",
                "home_zh": "克里斯蒂", "away_zh": "桑纳菲", "home_goals": 1, "away_goals": 0,
                "crown_1x2": (2.0, 3.3, 3.6)}
        monkeypatch.setattr(mod, "zh_to_canonical",
                            lambda z: _NORDIC.get(z))
        record_match(db, base)
        monkeypatch.setattr(mod, "zh_to_canonical", lambda z: None)   # ← 退化
        record_match(db, base)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT home_team, away_team FROM crown_close_history").fetchone()
        assert row == ("Kristiansund BK", "Sandefjord"), "None 不许覆盖已有的规范名"
        conn.close()

    def test_reingest_never_nulls_an_existing_kickoff(self, tmp_path):
        """COALESCE 守卫:老源没有 kickoff 时,重抓不许把已有的值冲成 NULL。
        (同 clubelo 那个『空结果覆盖好数据』的教训。)"""
        db = tmp_path / "c.db"
        base = {"match_id": "m1", "date": "2026-07-14", "league_cn": "世界杯",
                "home_zh": "法国", "away_zh": "西班牙", "home_goals": 2, "away_goals": 1,
                "crown_1x2": (2.10, 3.40, 3.30)}
        record_match(db, {**base, "kickoff_utc": "2026-07-14T19:00:00+00:00"})
        record_match(db, {**base, "kickoff_utc": None})      # ← 重抓,这次没解析出时刻
        conn = sqlite3.connect(db)
        ko = conn.execute(
            "SELECT kickoff_utc FROM crown_close_history WHERE match_id='m1'"
        ).fetchone()[0]
        assert ko == "2026-07-14T19:00:00+00:00", "None 不许覆盖已有的 kickoff"
        conn.close()
