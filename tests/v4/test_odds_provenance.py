"""盘口来源溯源(2026-07-23)—— 手打的 Pinnacle 不能在台账里冒充抓来的。

病史:owner 在 OA 没覆盖的赛事上手填 Pinnacle(欧战资格战等)。手填值会随
📌 记一笔原样落账,而台账**没有任何字段**能把它和抓来的价区分开 —— 手填若
是陈旧价或手滑打错,记下的就是一个虚构价,事后谁也查不出来。

修在 `insert_session` 这个共享 sink(五个 recorder 全过它),不逐 recorder 传参。
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.store import _request_odds_source, insert_session, open_db


class TestRequestOddsSource:
    def test_flat_request_market_handicap(self):
        """/recommend/market-handicap 是扁平形状 —— 手填走的就是这条路。"""
        assert _request_odds_source({"psc_home": 2.1, "odds_source": "manual"}) == "manual"

    def test_fixture_list_request(self):
        """/recommend、/recommend/single 是 fixtures 列表形状。"""
        assert _request_odds_source(
            {"fixtures": [{"odds_source": "odds_api"}, {"odds_source": "odds_api"}]}
        ) == "odds_api"

    def test_mixed_sources_are_labelled_mixed_not_guessed(self):
        """批量 gather:OA 覆盖的场次叠了 overlay、其余留 AF。硬挑一个当代表会让
        后续切片悄悄算错 —— 必须显式 'mixed'。"""
        assert _request_odds_source(
            {"fixtures": [{"odds_source": "odds_api"}, {"odds_source": "api_football"}]}
        ) == "mixed"

    def test_absent_is_none_never_defaulted(self):
        """⚠️ 本列的立身之本:没告诉我 → None,**绝不**默认成 'api_football'。
        那等于把「没告诉我」伪装成「我查过了」,正是这一列想防的事。"""
        assert _request_odds_source({"fixtures": [{"psc_home": 2.0}]}) is None
        assert _request_odds_source({"psc_home": 2.0}) is None
        assert _request_odds_source({}) is None
        assert _request_odds_source(None) is None      # type: ignore[arg-type]


class TestSessionColumn:
    def _sess(self, tmp_path, request: dict) -> str | None:
        db = tmp_path / "obs.db"
        with open_db(db) as conn:
            sid = insert_session(
                conn, bankroll=1000.0, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request=request)
        with sqlite3.connect(db) as c:
            return c.execute(
                "SELECT odds_source FROM recommendation_sessions WHERE session_id=?",
                (sid,)).fetchone()[0]

    def test_manual_bet_lands_labelled(self, tmp_path):
        assert self._sess(tmp_path, {"odds_source": "manual"}) == "manual"

    def test_unlabelled_bet_stays_null(self, tmp_path):
        """老客户端(没 bump 到 v112)不传该字段 → NULL,而不是被猜成某个源。"""
        assert self._sess(tmp_path, {"psc_home": 2.0}) is None

    def test_legacy_db_migrates_without_backfilling_a_guess(self, tmp_path):
        """老库补列走 PRAGMA + ALTER(照抄 snapshot_phase/model_type 的写法)。

        ⚠️ 但与那两条**不同**:这一列不做任何 UPDATE 回填。snapshot_phase/
        model_type 有可推断的历史默认值('closing'/'lightgbm');odds_source 没有
        —— 已记的注确实无从追溯,给它填个 'api_football' 就是在造假。

        这里手工造一张没有该列的老表(而不是 DROP COLUMN:这张表 DDL 里带 `--`
        注释,SQLite 重建时会语法失败 —— 改动前就如此,非本次引入)。"""
        db = tmp_path / "obs.db"
        with sqlite3.connect(db) as c:
            c.execute("""CREATE TABLE recommendation_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL, bankroll REAL NOT NULL,
                model_cutoff TEXT, model_trained_at TEXT,
                n_fixtures INTEGER NOT NULL, n_recommendations INTEGER NOT NULL,
                request_json TEXT NOT NULL, metadata_json TEXT)""")
            c.execute("INSERT INTO recommendation_sessions (created_at, bankroll, "
                      "n_fixtures, n_recommendations, request_json) "
                      "VALUES ('2026-01-01T00:00:00', 1000.0, 1, 1, '{}')")
        with open_db(db) as conn:           # 打开即迁移
            cols = {r["name"] for r in conn.execute(
                "PRAGMA table_info(recommendation_sessions)")}
            assert "odds_source" in cols, "老库没补上列"
            old = conn.execute(
                "SELECT odds_source FROM recommendation_sessions").fetchone()[0]
            assert old is None, "老行必须留 NULL —— 不知道就是不知道,不许回填猜测值"
        with open_db(db):                   # 再开一次:幂等,不该炸
            pass
