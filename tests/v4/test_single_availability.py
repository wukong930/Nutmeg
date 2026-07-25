"""单关可得性接进面板(2026-07-25)。

病史:`single_available` 抓了很久却**一次都没被消费** —— routes/dashboard 里零引用。
后果:甜区榜可以把一条你**物理上买不了**的腿排在第一。实测竞彩只给 **17%** 的场次
开单关,且高度集中(韩职 29% / 瑞超 21% / 挪超 13%;欧罗巴·芬超·欧冠·巴甲·美职
**0/59 全零**)—— 也就是说你常看的 5 个联赛里,榜首那条腿基本都得配串才能下。

⚠️ 本列是 **PER-MARKET(玩法级)**,不是场次级(见 jingcai_sp DDL 该列注释):
竞彩可以给胜平负开单关而让球不开。两个玩法必须各带各的标记。
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup, record_jingcai_sp

_OK = (2.04, 3.03, 3.23)      # 真实竞彩终盘,booksum≈1.13 在捕获闸带内


def _seed(db, *, market="had", single=None, hc=None):
    return record_jingcai_sp(
        db, match_date="2026-08-01", home_team="A", away_team="B",
        jc_home=_OK[0], jc_draw=_OK[1], jc_away=_OK[2],
        market=market, handicap_home=hc, single_available=single,
        source="sporttery")


class TestLookupCarriesTheFlag:
    def test_flag_reaches_the_lookup_tuple(self, tmp_path):
        db = tmp_path / "o.db"
        assert _seed(db, single=1)
        (v,) = fetch_sp_lookup(db, market="had").values()
        assert len(v) == 7, "元组尾部必须多出 single_available"
        assert v[6] == 1

    def test_parlay_only_is_zero_not_none(self, tmp_path):
        """0(只能串)和 None(未知)必须分得开 —— 前端对两者的处理完全不同。"""
        db = tmp_path / "o.db"
        _seed(db, single=0)
        (v,) = fetch_sp_lookup(db, market="had").values()
        assert v[6] == 0 and v[6] is not None

    def test_unknown_stays_none(self, tmp_path):
        db = tmp_path / "o.db"
        _seed(db, single=None)
        (v,) = fetch_sp_lookup(db, market="had").values()
        assert v[6] is None, "未知就是未知,**不猜**"

    def test_per_market_not_per_match(self, tmp_path):
        """⚠️ 核心语义:同一场,胜平负可单关而让球只能串。合并成一个标记就会
        让你以为让球腿也能单买。"""
        db = tmp_path / "o.db"
        _seed(db, market="had", single=1)
        _seed(db, market="hhad", single=0, hc=-1)
        (had,) = fetch_sp_lookup(db, market="had").values()
        (hhad,) = fetch_sp_lookup(db, market="hhad").values()
        assert (had[6], hhad[6]) == (1, 0)


class TestDashboardWiring:
    def _html(self) -> str:
        from pathlib import Path
        return Path("apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text()

    def test_badge_helper_exists_and_skips_unknown(self):
        html = self._html()
        assert "function _singleBadge(v)" in html
        assert "if (v === null || v === undefined) return ''" in html, (
            "未知必须**不渲染**:画成「只能串」会让人错过真能单关的场")

    def test_board_picks_the_leg_s_own_market(self):
        """回归钉:我第一版用 leg.market==='hhad' —— 腿对象根本没有 market 字段
        (1X2 是 'H'/'D'/'A',让球是 'hcH'/…),恒 false ⇒ 让球腿会被贴上 1X2 的
        单关标记。必须按 outcome 前缀判。"""
        html = self._html()
        assert "function _legIsHc(leg)" in html
        assert "leg.o.startsWith('hc')" in html
        assert "_legIsHc(r.best)" in html
        assert "r.best.market" not in html, "别再退回那个恒 false 的判法"

    def test_both_i18n_locales_have_the_keys(self):
        html = self._html()
        for k in ("sw_single_yes", "sw_single_no",
                  "sw_single_yes_hint", "sw_single_no_hint"):
            assert html.count(f"{k}:") >= 2, f"{k} 中英两套字典都要有"


class TestSchemaEcho:
    def test_prediction_carries_both_markets(self):
        from nutmeg.v4.api.schemas import SinglePrediction
        f = SinglePrediction.model_fields
        assert "jc_single_available" in f and "jc_hc_single_available" in f
        assert f["jc_single_available"].default is None


class TestRealDbShape:
    def test_live_column_exists(self, tmp_path):
        """建表/迁移路径必须带这一列(老库走 ALTER)。"""
        db = tmp_path / "o.db"
        _seed(db, single=1)
        with sqlite3.connect(db) as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(jingcai_sp)")}
        assert "single_available" in cols
