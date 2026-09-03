"""多书商共识层 P0 三条(2026-09-03,深度评估落地)。

来源:4 条独立测线 + 4 名对抗复算。⭐ owner 问的「要不要筛掉交易量小的书商」被
**实测反证**(出现率越高的书商离共识越远,r=+0.484;剔最吵 5 家共识中位只动
0.055pp、结论翻转 0/945),所以这里**一条书商名单都没有** —— 三条修的分别是
读路径范围、采集触发判据、和逐报价的有效性。
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from nutmeg.v4.data.sources import odds_api as OA
from v4.test_book_consensus import _attach, _pred


def _q(h, d, a):
    return [h, d, a]


class TestDegenerateQuoteDoesNotSkewSpread:
    """P0-3:自身抽水 >30% 的退化报价只污染 min/spread,不污染中位。

    实测:388 场 / 7,060 条报价里 67 条退化(典型 `[1.08,1.08,1.08]`,全来自交易所
    无流动性时段),把显示离散度打歪最坏 **45.98pp**(60/388 场虚高 >5pp);
    落地后实测 max 51.74pp → 10.96pp、亮红 21.6% → 5.9%、零场因此消失。

    🚨 **本类必须调生产的 `_attach_book_consensus`,不许自己复刻那段算法。**
       第一版我复刻了 → 空包弹「把退化闸整个拿掉」照样**绿**,因为测试根本没碰
       生产代码。(同 [[reusing-the-function-is-not-reusing-the-calibration]] 的
       镜像面:那次是复用函数丢了口径,这次是不复用函数丢了覆盖。)
    """

    #: 重度热门。⚠️ 退化报价去vig 恒为 [1/3,1/3,1/3],它离共识多远取决于共识本身有多偏
    #: —— 势均力敌的样本只能造出 9.9pp 的污染,测不出这条修复(我第一版就这么写,
    #: 被「人口非平凡」断言当场抓住)。真实的 45.98pp 就出在热门场。
    _FAV = {f"bk{i}": [1.28 + i * 0.005, 6.0, 11.0] for i in range(6)}
    _DEGENERATE = [1.08, 1.08, 1.08]      # 抽水 178%

    def test_a_degenerate_quote_no_longer_blows_up_the_spread(self, tmp_path, monkeypatch):
        second = tmp_path / "b"
        second.mkdir()
        clean = _attach(tmp_path, monkeypatch, dict(self._FAV))
        poisoned = _attach(second, monkeypatch,
                           dict(self._FAV, exchange_dead=list(self._DEGENERATE)))

        assert clean.bk_spread and poisoned.bk_spread, "人口非平凡:两边都必须真算出来"
        # 🚨 承重:同一条退化报价,对 spread 是灾难、对中位只是噪声
        assert max(poisoned.bk_spread) < 10.0, (
            f"退化报价仍在污染 spread:{poisoned.bk_spread}")
        moved = max(abs(a - b) for a, b in
                    zip(clean.bk_consensus, poisoned.bk_consensus, strict=True)) * 100
        assert moved < 1.2, f"共识中位被推了 {moved:.2f}pp,超出实测上限 1.12pp"

    def test_the_sample_really_is_poisonous(self, tmp_path, monkeypatch):
        """⚠️ 人口非平凡:先证明**不修的话**这个样本真的会炸,否则上一条空洞为真。"""
        from nutmeg.v4.api import routes
        monkeypatch.setattr(routes, "_BK_MAX_OVERROUND", 99.0)   # 等于没闸
        p = _attach(tmp_path, monkeypatch,
                    dict(self._FAV, exchange_dead=list(self._DEGENERATE)))
        assert max(p.bk_spread) > 30.0, (
            f"样本不够毒({max(p.bk_spread):.1f}pp)—— 上一条测不出任何东西")

    def test_the_degenerate_quote_still_counts_toward_n_books(self, tmp_path, monkeypatch):
        """⚠️ 退化报价必须**仍进 devigged**(参与家数),否则会把整块面板挤掉门槛。

        实测:若在去vig 循环里 `continue`,1 场(2026-09-12 Heerenveen vs SC Telstar)
        整块共识面板会消失 —— `_BK_MIN_BOOKS` 闸在循环之后才判。
        """
        from nutmeg.v4.api.routes import _BK_MIN_BOOKS
        books = {f"bk{i}": [1.28, 6.0, 11.0] for i in range(_BK_MIN_BOOKS - 1)}
        books["exchange_dead"] = list(self._DEGENERATE)
        assert len(books) == _BK_MIN_BOOKS
        p = _attach(tmp_path, monkeypatch, books)
        assert p.bk_consensus is not None, "退化报价被踢出计数 ⇒ 整块面板消失了"
        assert p.bk_n == _BK_MIN_BOOKS

    def test_threshold_sits_in_the_empty_band(self):
        """阈值必须落在实测的空隙里(正常报价抽水 p99=0.189,退化簇最小 0.453)。"""
        from nutmeg.v4.api.routes import _BK_MAX_OVERROUND
        assert 0.28 <= _BK_MAX_OVERROUND <= 0.45, (
            f"{_BK_MAX_OVERROUND} 掉出了实测空隙 —— 会误伤正常报价或放过退化报价")


class TestLivePullLedger:
    """P0-2 的判据:只有**本进程刚真花过钱**才为真。"""

    def setup_method(self):
        OA._LAST_LIVE.clear()

    def test_cold_process_is_false(self):
        assert OA.was_last_odds_pull_live("soccer_epl") is False

    def test_is_per_sport_not_a_global_switch(self):
        OA._LAST_LIVE[OA._odds_endpoint("soccer_epl")] = time.time()
        assert OA.was_last_odds_pull_live("soccer_epl") is True
        assert OA.was_last_odds_pull_live("soccer_italy_serie_a") is False

    def test_expires(self):
        OA._LAST_LIVE[OA._odds_endpoint("soccer_epl")] = time.time() - 301
        assert OA.was_last_odds_pull_live("soccer_epl") is False

    def test_cache_hit_must_not_record(self, monkeypatch):
        """🚨 承重:缓存命中不记账 —— 否则面板 60s 被动轮询会开始写库
        (13 联赛 × 3 天 = 39 次/分钟的重复读盘+去重写)。"""
        d = Path(tempfile.mkdtemp())
        cf = OA._cache_path(OA._odds_endpoint("soccer_t"),
                            {"regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}, d)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([]))

        def _boom(*a, **k):
            raise AssertionError("🚨 发了真请求")
        monkeypatch.setattr(OA, "_client", _boom)

        OA.fetch_current_odds("soccer_t", regions="eu", markets="h2h", cache_dir=d)
        assert OA._LAST_LIVE == {}, "缓存命中却记了账 ⇒ 被动轮询会开始写库"

    def test_endpoint_is_built_in_exactly_one_place(self):
        """⛔ 调用方不许手抄 `f"sports/{sk}/odds"` —— 两份字面量会悄悄漂开,
        而漂开的后果是判据**静默常闭**,长得和「今天没比赛」一样。"""
        import re
        pkg = Path("apps/api/src/nutmeg")
        assert pkg.is_dir(), "人口非平凡:包路径必须存在"
        files = list(pkg.rglob("*.py"))
        assert len(files) > 50, f"人口非平凡:只扫到 {len(files)} 个文件"
        pat = re.compile(r'f"sports/\{[a-z_]+\}/odds"')
        hits = [str(f) for f in files if pat.search(f.read_text(encoding="utf-8"))]
        assert len(hits) == 1 and hits[0].endswith("odds_api.py"), (
            f"endpoint 字面量出现在多处:{hits}")


class TestSameRulerAsTheMainEv:
    """P1-①:共识必须和它要对照的那个 EV 用**同一把尺子**(WPO)。

    实测(388 场 / 21,180 条报价):比例归一 vs WPO 逐条 |ΔP| 中位 0.669pp、
    p90 2.01pp;逐场共识中位位移 中位 1.169pp,换算 EV(×SP≈3)≈ 3.5pp,
    而面板绿灯线是 5% —— 两把不同刻度的尺子并排、还共用同一套上色阈值。
    """

    def test_consensus_matches_the_production_wpo_devig(self, tmp_path, monkeypatch):
        """⭐ 行为断言:拿生产的 `devig(method='wpo')` 独立算一遍,必须逐位相同。

        ⛔ 不写「源码里有没有 `method="wpo"`」那种语法断言 —— 换个等价写法就假红,
        而真正换回比例归一时它可能照样绿。
        """
        from nutmeg.v4.model.devig import devig
        import statistics as st
        books = {f"bk{i}": [1.90 + i * 0.05, 3.50, 4.20 - i * 0.05] for i in range(6)}
        p = _attach(tmp_path, monkeypatch, books)
        assert p.bk_consensus, "人口非平凡:必须真算出共识"

        want = [st.median([devig(o, method="wpo")[i] for o in books.values()])
                for i in range(3)]
        for got, exp in zip(p.bk_consensus, want, strict=True):
            assert abs(got - exp) < 1e-9, (
                f"共识不是 WPO 口径:{p.bk_consensus} vs {want}")

    def test_it_differs_from_the_old_proportional_ruler(self, tmp_path, monkeypatch):
        """🚨 人口非平凡:样本必须真能分开两把尺子,否则上一条空洞为真。"""
        import statistics as st
        books = {f"bk{i}": [1.90 + i * 0.05, 3.50, 4.20 - i * 0.05] for i in range(6)}
        p = _attach(tmp_path, monkeypatch, books)
        prop = [st.median([(1 / o[i]) / sum(1 / x for x in o) for o in books.values()])
                for i in range(3)]
        moved = max(abs(a - b) for a, b in zip(p.bk_consensus, prop, strict=True)) * 100
        assert moved > 0.3, f"样本分不开两把尺子(只差 {moved:.3f}pp)—— 上一条测不出东西"


class TestThreeStatesAreDistinguishable:
    """P1-③:「没接入」/「有快照但没连上」/「今天还没抓到」是**三**件事。

    原来后两者都渲染成空白 ⇒ owner 无从知道该去补词典。实测一次 79 场的 sp-calc
    里 3 场落在第二态,其中 `PSG vs Monaco` 是**竞彩当天在售**的。
    """

    def test_name_mismatch_is_flagged_not_blank(self, tmp_path, monkeypatch):
        from nutmeg.v4.api import routes
        # 库里有这一天的快照,但队名是另一场
        _attach(tmp_path, monkeypatch, {f"bk{i}": [2.0, 3.4, 3.6] for i in range(6)})
        p = _pred(home_team="Nowhere United", away_team="Elsewhere FC")
        routes._attach_book_consensus([p])
        assert p.bk_consensus is None
        assert p.bk_no_match is True, "队名没连上却没标记 ⇒ 渲染成空白,和『今天没抓到』分不开"
        assert p.bk_unavailable is False, "这不是『没接入』"

    def test_no_snapshot_that_day_is_not_flagged(self, tmp_path, monkeypatch):
        """⚠️ 对照组:今天真没抓到**不该**标 —— 否则会把 cron 没跑误报成词典问题。"""
        from nutmeg.v4.api import routes
        import datetime as dt
        _attach(tmp_path, monkeypatch, {f"bk{i}": [2.0, 3.4, 3.6] for i in range(6)})
        p = _pred(date=dt.date(2030, 1, 1))          # 那天库里一行都没有
        routes._attach_book_consensus([p])
        assert p.bk_no_match is False, "把『今天没抓到』误标成了词典问题"

    def test_unavailable_still_wins(self, tmp_path, monkeypatch):
        """没接入的赛事优先标『没接入』,不落到第二态。"""
        from nutmeg.v4.api import routes
        _attach(tmp_path, monkeypatch, {f"bk{i}": [2.0, 3.4, 3.6] for i in range(6)})
        p = _pred(league="JPN_LEAGUE_CUP")           # 不在 SPORT_KEYS
        routes._attach_book_consensus([p])
        assert p.bk_unavailable is True and p.bk_no_match is False
