"""盘面反事实快照 —— 记事实不记规则(2026-08-11,08-12 审查后重写)。

## 这些测试守什么

owner 问「串关构造器能不能自我学习」。查账:真串关票 **1 张**,结算 4 行 ⇒
从自己的票学 = 从 n=1 学。而每场比赛三条腿都会结算,**没买的那两条结果一样白送**
⇒ 学习信号在盘面,不在票。快照层就是把盘面留下来。

它是 **forward-only**:今天不记,这一天就永远补不回来。

## 🚨 第一版这批测试是怎么全绿还漏掉两个 blocker 的

**① 夹具喂了生产不存在的字段。** `_pred()` 里写了 `match_date`,而端点下发的是
`date` —— 于是被测的是**生产永远走不到的分支**。⇒ 现在夹具**逐字照抄真实 payload**
的键名,并有一条测试专门钉死这件事。

**② 全部夹具都是 `market_mode=True`。** 那种模式下 `p_*_1x2` 恰好等于市场 P,
所以「模型 P 配市场 P 的下界」这个 blocker 在夏季数据上**测不出来**。
⇒ 现在标准模式(`market_mode=False`)有自己的夹具。

**③ 「八个 δ 常数一个不能漏」把清单抄了第二份** —— 代码一份、测试一份,
结构上不可能发现漏项,而当时**已经漏了 6 个上线中的常数**。
⇒ 现在从模块自己的命名空间**推导**期望集合,不再手抄。

**④ join 断言恒真** —— LEFT JOIN 打在空表上,`joined == 6` 只是左表行数,
`ON 1=0` 也能过。⇒ 现在右表先塞一行真数据。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.observation.board_snapshot import (
    _CONST_SPECS,
    _legs_from_prediction,
    live_constants,
    snapshot_board,
)

_NOW = dt.datetime(2026, 8, 11, 12, 0, tzinfo=dt.UTC)


def _pred(**over) -> dict:
    """一条盘面记录。

    🚨 键名**逐字抄自 2026-08-12 的真实 `/predictions/cup-market` 响应**
    (`date`,不是 `match_date`)。见 `test_fixture_keys_exist_in_the_real_payload`
    —— 夹具和生产分家过一次,代价是两个 blocker 从测试底下溜过去。
    """
    base = {
        "date": "2026-08-12", "league": "UEFA_SUPER_CUP",
        "home_team": "Paris Saint Germain", "away_team": "Aston Villa",
        "kickoff_utc": "2026-08-12T19:00:00+00:00", "market_mode": True,
        # 市场模式:p_*_1x2 与 p_*_market 同源(都是 Pinnacle 去vig)
        "p_home_1x2": 0.5563, "p_draw_1x2": 0.2381, "p_away_1x2": 0.2055,
        "p_home_market": 0.5563, "p_draw_market": 0.2381, "p_away_market": 0.2055,
        "onex_lo_home": 0.5447, "onex_lo_draw": 0.2269, "onex_lo_away": 0.1943,
        "jc_home": 1.60, "jc_draw": 3.58, "jc_away": 4.45,
        "psc_home": 1.76, "psc_draw": 4.00, "psc_away": 4.60,
        "psc_over25": 1.90, "psc_under25": 1.95, "ou_line": 2.5,
        "jc_captured_at": "2026-08-11T17:22:22+00:00",
        "odds_update": "2026-08-11T16:02:14+00:00",
        "jc_single_available": 1, "jc_hc_single_available": 1,
        "jc_hc_line": -1, "jc_hc_home": 2.88, "jc_hc_draw": 3.45, "jc_hc_away": 2.03,
        "handicap_lines": [
            {"line": -2, "p_home": .13, "p_draw": .15, "p_away": .72,
             "p_home_lo": .11, "p_draw_lo": .13, "p_away_lo": .70},
            {"line": -1, "p_home": .2722, "p_draw": .2796, "p_away": .4483,
             "p_home_lo": .2566, "p_draw_lo": .2640, "p_away_lo": .4329},
            {"line": 0, "p_home": .55, "p_draw": .24, "p_away": .21,
             "p_home_lo": .53, "p_draw_lo": .22, "p_away_lo": .19},
            {"line": 1, "p_home": .79, "p_draw": .10, "p_away": .11,
             "p_home_lo": .77, "p_draw_lo": .08, "p_away_lo": .09},
        ],
    }
    base.update(over)
    return base


def _pred_standard(**over) -> dict:
    """**标准模式**的盘面记录 —— 两个概率族真正分家的那一半。

    ⭐ 关键差异:`p_*_1x2` 是**模型 P**,`p_*_market` 是 Pinnacle 去vig,
    而 `onex_lo_*` 是**后者**的下界。这里故意让模型 P 低于市场 P,
    复现实测中 27.5% 的腿会出现「下界 > 点估」的那个形状。
    """
    return _pred(market_mode=False, league="EPL",
                 p_home_1x2=0.48, p_draw_1x2=0.26, p_away_1x2=0.26,
                 p_home_market=0.5563, p_draw_market=0.2381, p_away_market=0.2055,
                 **over)


class TestFixtureMatchesProduction:
    """🚨 第一版最贵的一条:夹具喂了端点根本不下发的键。"""

    def test_fixture_keys_exist_in_the_real_payload(self) -> None:
        """夹具用的每个键,都必须是端点真的会下发的。

        ⭐ 这条是**行为断言**:它拿真实端点的响应当权威,而不是查源码里
        有没有某个字符串。端点不通就 skip —— 但绝不因为不通而假装通过。

        空包弹:把 `_pred()` 里的 `date` 改回 `match_date` ⇒ 这条立刻红。
        """
        import httpx
        try:
            r = httpx.get("http://127.0.0.1:8080/api/v4/predictions/cup-market",
                          params={"days": 3}, timeout=180)
            r.raise_for_status()
            preds = r.json().get("predictions") or []
        except Exception:                                 # noqa: BLE001
            pytest.skip("服务没起 —— 这条只在本地有意义")
        if not preds:
            pytest.skip("盘面为空 —— 此刻没有分母")

        real = set(preds[0])
        ours = set(_pred())
        ghosts = sorted(ours - real)
        assert not ghosts, (
            f"夹具喂了端点**不下发**的键:{ghosts} ⇒ 被测的是生产走不到的分支。"
            f"(第一版就是这么让两个 blocker 溜过去的)")

    def test_date_key_is_read_not_match_date(self) -> None:
        """身份日期必须从 `date` 读出来,不能只靠 kickoff_utc 兜底。

        空包弹:把 `_match_date` 里的 `("date", "match_date")` 改成
        `("match_date",)` ⇒ 下面第二条断言红(退化成开球日)。
        """
        legs = _legs_from_prediction(_pred(), _NOW)
        assert legs[0]["match_date"] == "2026-08-12"
        # 没有 kickoff_utc 时,date 仍必须能单独撑起身份
        only_date = _legs_from_prediction(_pred(kickoff_utc=None), _NOW)
        assert only_date and only_date[0]["match_date"] == "2026-08-12"


class TestTwoProbabilityFamilies:
    """🚨 blocker ①:1X2 腿的点估和下界来自**两个不同的概率族**。"""

    def test_standard_mode_keeps_model_and_market_apart(self) -> None:
        """标准模式下 `p_model` != `p_market`,两个都得留,且 `p_lo` 明标是谁的。

        ⭐ 这条在**市场模式夹具上恒绿**(那时两者同源)—— 所以它必须用
        标准模式的夹具。第一版 17 条测试全是市场模式,这就是漏掉的原因。

        空包弹:把 `_legs_from_prediction` 改回只存一个 `p` ⇒ 整个类红。
        """
        legs = [x for x in _legs_from_prediction(_pred_standard(), _NOW)
                if x["market"] == "had"]
        assert len(legs) == 3
        assert legs[0]["p_model"] == pytest.approx(0.48), "模型 P 必须原样留下"
        assert legs[0]["p_market"] == pytest.approx(0.5563), "市场 P 必须**另存一列**"
        assert legs[0]["p_model"] != legs[0]["p_market"], "标准模式两族不该相等"
        assert legs[0]["p_lo_of"] == "p_market", "下界是市场 P 的下界,必须明标"

    def test_the_bound_is_consistent_with_the_column_it_names(self) -> None:
        """`p_lo` 必须小于 `p_lo_of` 指向的那一列 —— 而不是小于「随便哪个 p」。

        ⭐ 这才是第一版 `assert p_lo < p` 想守的性质。在标准模式下,
        `p_lo (0.5447) > p_model (0.48)` 是**正常的**(不同族),
        旧断言会在这里假红;而它真正该守的 `p_lo < p_market` 才是不变量。
        """
        for pred in (_pred(), _pred_standard()):
            for leg in _legs_from_prediction(pred, _NOW):
                ref = leg[leg["p_lo_of"]]
                assert leg["p_lo"] is not None and ref is not None
                assert leg["p_lo"] < ref, (
                    f"{leg['market']} 腿{leg['leg']}:下界({leg['p_lo']})不小于"
                    f"它自称的点估 {leg['p_lo_of']}({ref})")

    def test_handicap_legs_declare_their_own_family(self) -> None:
        """让球网格两模式一律 Pinnacle 反推 ⇒ 点估与下界同族,标 `p_model`。"""
        hc = [x for x in _legs_from_prediction(_pred(), _NOW) if x["market"] == "hhad"]
        assert hc and all(x["p_lo_of"] == "p_model" for x in hc)
        assert all(x["p_market"] is None for x in hc), "让球没有独立的市场 1X2 点估"


class TestEmptyBoardIsNotSilence:
    """⭐ 本仓最贵的错误家族:「没有」和「没去看」长得一模一样。

    涓流 END 写成常量 ⇒ 「零新增」数学上必然 ⇒ 我们被自己造的假信号说服
    主动关掉它,静默丢了 10.5 个月。快照层不许重演 —— 而第一版**重演了**。
    """

    def test_zero_predictions_still_writes_provenance(self, tmp_path: Path) -> None:
        """夏休期 `sp-calc` 真的返回 0 场。那天必须留下「跑过且是空的」的证据。"""
        db = tmp_path / "obs.db"
        res = snapshot_board([], str(db), fe_version="v151", now=_NOW)
        assert res["legs"] == 0
        with sqlite3.connect(db) as c:
            rows = c.execute(
                "SELECT created_at, fe_version FROM snapshot_provenance").fetchall()
        assert len(rows) == 1, "空盘面也必须留下一行 —— 否则和『没跑』无法区分"
        assert rows[0][1] == "v151"

    def test_broken_feed_is_distinguishable_from_an_empty_board(
        self, tmp_path: Path,
    ) -> None:
        """🚨 blocker ②:两者都是 0 条腿,但**库里必须分得开**。

        审查用桩服务证实第一版做不到:喂料断(抓到 20 场、全部 pending)
        和真空盘(抓到 0 场)输出**逐字相同**、落库**完全不可区分**,
        而 CLI 还打印「证明盘面本来就是空的」—— 那句话是假的。

        空包弹:把 `snapshot_board` 的 `feed` 参数丢掉不落库 ⇒ 这条红。
        """
        broken = {"/predictions/sp-calc":
                  {"predictions": 0, "fixtures_fetched": 20, "pending": 20}}
        truly_empty = {"/predictions/sp-calc":
                       {"predictions": 0, "fixtures_fetched": 0, "pending": 0}}

        db_a, db_b = tmp_path / "a.db", tmp_path / "b.db"
        snapshot_board([], str(db_a), feed=broken, now=_NOW)
        snapshot_board([], str(db_b), feed=truly_empty, now=_NOW)

        def _feed(p: Path) -> dict:
            with sqlite3.connect(p) as c:
                return json.loads(
                    c.execute("SELECT feed_json FROM snapshot_provenance").fetchone()[0])

        fa, fb = _feed(db_a), _feed(db_b)
        assert fa != fb, "喂料断和真空盘在库里必须分得开"
        assert fa["/predictions/sp-calc"]["fixtures_fetched"] == 20
        assert fb["/predictions/sp-calc"]["fixtures_fetched"] == 0

    def test_two_empty_runs_are_two_rows(self, tmp_path: Path) -> None:
        """连续两次空跑 = 两行 —— 「连续两周都空」要能数出来。"""
        db = tmp_path / "obs.db"
        snapshot_board([], str(db), now=_NOW)
        snapshot_board([], str(db), now=_NOW + dt.timedelta(days=1))
        with sqlite3.connect(db) as c:
            n = c.execute("SELECT COUNT(*) FROM snapshot_provenance").fetchone()[0]
        assert n == 2


class TestProvenanceIsLoadBearing:
    """没有「当时哪套 δ 在跑」,半年后「换个 δ 回放」是没有意义的。"""

    def test_constants_are_read_from_the_live_module_not_copied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """变异检验:改掉模块里的 δ,快照必须**跟着变**。"""
        from nutmeg.v4.model import market_handicap as MH
        monkeypatch.setattr(MH, "_C1_DELTA", 0.9999, raising=False)
        db = tmp_path / "obs.db"
        snapshot_board([], str(db), now=_NOW)
        with sqlite3.connect(db) as c:
            got = json.loads(c.execute(
                "SELECT constants_json FROM snapshot_provenance").fetchone()[0])
        assert got["market_handicap._C1_DELTA"] == 0.9999, (
            "常数是抄的不是读的 —— provenance 会撒谎,整批快照的回放价值归零")

    def test_missing_constant_records_null_not_omission(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """「这一版没这个常数」和「我忘了记」是两件事。"""
        from nutmeg.v4.model import market_handicap as MH
        monkeypatch.delattr(MH, "_UNCAL_SE", raising=False)
        got = live_constants()
        assert "market_handicap._UNCAL_SE" in got, "键必须在"
        assert got["market_handicap._UNCAL_SE"] is None, "值该是 None,不是省略"

    def test_import_failure_still_fills_every_key(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """🚨 第一版的 except 分支**违反了自己的 docstring** —— import 一失败
        就把 8 个键全省略、只留一个 `__error__`,而快照照常写完 exit 0。

        空包弹:把 `live_constants` 的 except 改回 `out[...__error__] = ...; continue`
        ⇒ 这条红。
        """
        import builtins
        real = builtins.__import__

        def boom(name, *a, **kw):
            if "market_handicap" in name:
                raise ImportError("boom")
            return real(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", boom)
        got = live_constants()
        assert got.get("market_handicap.__error__"), "该记下错误"
        assert got["market_handicap._C1_DELTA"] is None, "键必须在且为 None,不是省略"

    def test_every_calibration_constant_in_the_module_is_registered(self) -> None:
        """🚨 第一版把常数清单**抄了第二份**(代码一份、测试一份)⇒ 结构上
        不可能发现漏项,而当时**已经漏了 δ₋₂ 的 6 个上线常数**。

        ⭐ 修法:期望集合从**模块自己的命名空间推导**,不再手抄。
        以后谁加一个 `_C3_DELTA_*` 而忘了注册,这条立刻红。

        空包弹:把 `_CONST_SPECS` 里的 `_C2_DELTA_H` 删掉 ⇒ 这条红。
        """
        prefixes = ("_C1_", "_C2_", "_C3_", "_UNCAL_", "ONEX_")
        missing: list[str] = []
        for prefix, module_path, names in _CONST_SPECS:
            mod = __import__(module_path, fromlist=["_"])
            live = {n for n in vars(mod)
                    if n.startswith(prefixes) and not callable(getattr(mod, n))}
            missing += [f"{prefix}.{n}" for n in sorted(live - set(names))]
        assert not missing, (
            f"模块里有这些校准常数,但 `_CONST_SPECS` 没登记 ⇒ 回放不出当时的下界:"
            f"{missing}")

    def test_daemon_divergence_is_at_least_visible(self, tmp_path: Path) -> None:
        """常数是 CLI 读的、P 是 daemon 算的,而 daemon 不热载代码。

        修不掉(要改进程边界),但**必须可见** —— 落 `constants_mtime`,
        回放者能自己判断「模块比 fe_version 新 ⇒ 这批存疑」。
        """
        db = tmp_path / "obs.db"
        snapshot_board([], str(db), now=_NOW)
        with sqlite3.connect(db) as c:
            src, mtime = c.execute(
                "SELECT constants_source, constants_mtime FROM snapshot_provenance"
            ).fetchone()
        assert src == "cli-process", "必须诚实标注常数是谁读的"
        assert mtime, "必须留下模块的磁盘时刻,否则劈叉不可见"


class TestWhatGetsRecorded:
    def test_1x2_plus_every_line_we_care_about(self) -> None:
        """1X2 三条 + (−1/0/+1 ∪ 竞彩线) × 三条。本例竞彩卖 −1,已在三线内。"""
        legs = _legs_from_prediction(_pred(), _NOW)
        had = [x for x in legs if x["market"] == "had"]
        hhad = [x for x in legs if x["market"] == "hhad"]
        assert len(had) == 3
        assert sorted({x["handicap_home"] for x in hhad}) == [-1, 0, 1]
        assert len(hhad) == 9

    def test_line_source_marks_the_one_jingcai_actually_sells(self) -> None:
        """⭐ 「会下注的人口」这条纪律由**列**表达,不是由「少记几行」表达。

        第一版只记竞彩那条线,导致 hhad 的**未上架人口结构性为 0** ——
        于是「竞彩的选择函数在让球盘上有没有效应」永远只能得到
        「没有效应」这个假答案(分母是空的)。

        空包弹:把 `_HC_LINES_ALWAYS` 改成 `()` ⇒ 未上架人口重新归零,这条红。
        """
        hhad = [x for x in _legs_from_prediction(_pred(), _NOW)
                if x["market"] == "hhad"]
        jc = [x for x in hhad if x["line_source"] == "jingcai"]
        model = [x for x in hhad if x["line_source"] == "model"]
        assert {x["handicap_home"] for x in jc} == {-1}, "竞彩卖的是 −1"
        assert all(x["jc_sp"] is not None for x in jc), "竞彩那条线必须有 SP"
        assert all(x["jc_sp"] is None for x in model), "非竞彩线不能编 SP"
        assert len(model) == 6, "未上架人口的分母不能是 0"

    def test_unlisted_match_still_yields_a_handicap_population(self) -> None:
        """竞彩完全没开让球的场次,照样留下 −1/0/+1 —— 那是选择函数的对照组。"""
        hhad = [x for x in _legs_from_prediction(_pred(jc_hc_line=None), _NOW)
                if x["market"] == "hhad"]
        assert len(hhad) == 9
        assert all(x["line_source"] == "model" for x in hhad)
        assert all(x["jc_sp"] is None for x in hhad)

    def test_jingcai_line_missing_from_grid_is_loud(self, caplog) -> None:
        """⚠️ 第一版 `if row:` 会**静默**丢掉三条腿。现在必须留下日志。"""
        import logging
        with caplog.at_level(logging.WARNING):
            _legs_from_prediction(_pred(jc_hc_line=7), _NOW)
        assert any("网格里没有这条线" in r.getMessage() for r in caplog.records), \
            "竞彩线不在网格里,必须响亮一次而不是静默丢腿"

    def test_freshness_stamps_are_recorded(self) -> None:
        """⭐ forward-only:「当时那个价多旧」事后重建不出来。

        面板 6688 行的注释原话:旧竞彩价会**静默美化/隐藏 EV**。
        """
        leg = _legs_from_prediction(_pred(), _NOW)[0]
        assert leg["jc_captured_at"] == "2026-08-11T17:22:22+00:00"
        assert leg["odds_update"] == "2026-08-11T16:02:14+00:00"

    def test_ou_anchor_is_recorded(self) -> None:
        """让球网格的另一半锚:`ou_line` + Pinnacle 大小球。

        实测 `ou_line` 只有 40% 是 2.5,靠 psc 三元组回 odds_snapshots 模糊 join
        有 7.3% 对应不止一个 O/U ⇒ 必须行内自带。
        """
        leg = _legs_from_prediction(_pred(), _NOW)[0]
        assert leg["ou_line"] == 2.5
        assert leg["psc_over"] == 1.90 and leg["psc_under"] == 1.95

    def test_unlisted_legs_are_kept_with_null_sp(self) -> None:
        """竞彩没上架的场次照记 —— 「竞彩只上架厚水场」的对照组就是它们。"""
        legs = _legs_from_prediction(
            _pred(jc_home=None, jc_draw=None, jc_away=None, jc_hc_line=None), _NOW)
        had = [x for x in legs if x["market"] == "had"]
        assert len(had) == 3
        assert all(x["jc_sp"] is None for x in had)
        assert all(x["p_model"] is not None for x in had), "没上架不代表没有 P"

    def test_hours_to_ko_is_signed_and_survives_a_naive_timestamp(self) -> None:
        """距开球是 freeze-gap 的自变量。

        ⚠️ 无时区的时间串减 aware 抛 **TypeError**;第一版只捕 ValueError ⇒
        那一下会穿出整个 snapshot_board,**当天快照全丢**。
        """
        legs = _legs_from_prediction(_pred(), _NOW)
        assert legs[0]["hours_to_ko"] == pytest.approx(31.0, abs=0.01)
        past = _legs_from_prediction(_pred(), _NOW + dt.timedelta(hours=40))
        assert past[0]["hours_to_ko"] < 0, "开球后该是负数"
        naive = _legs_from_prediction(_pred(kickoff_utc="2026-08-12T19:00:00"), _NOW)
        assert naive[0]["hours_to_ko"] == pytest.approx(31.0, abs=0.01), \
            "无时区时间串不许把整次快照带崩"

    def test_rows_without_identity_are_dropped_not_written_blank(self) -> None:
        """缺队名/日期 ⇒ 整场丢掉(且有日志)。"""
        assert _legs_from_prediction(_pred(home_team=None), _NOW) == []
        assert _legs_from_prediction(_pred(date=None, kickoff_utc=None), _NOW) == []


class TestItStaysReplayable:
    """⛔ 快照里**只能有事实**。规则(闸门/名次/选腿)会变,事实不会。"""

    def test_schema_carries_no_rule_output(self, tmp_path: Path) -> None:
        """名次已实测不预测 ROI;闸门可由 `p_lo`+`jc_sp` 事后重算。"""
        db = tmp_path / "obs.db"
        snapshot_board([_pred()], str(db), now=_NOW)
        with sqlite3.connect(db) as c:
            cols = {r[1] for r in c.execute("PRAGMA table_info(board_leg_snapshot)")}
        forbidden = {"rank", "passed_gate", "selected", "ev", "ev_lo", "recommended"}
        assert not (cols & forbidden), f"规则输出混进了 schema:{cols & forbidden}"

    def test_a_future_rule_can_recompute_ev_from_what_was_stored(
        self, tmp_path: Path,
    ) -> None:
        """⭐ 真正的验收:拿库里的行,能不能算出当时屏幕上的 EV?"""
        db = tmp_path / "obs.db"
        snapshot_board([_pred()], str(db), now=_NOW)
        with sqlite3.connect(db) as c:
            c.row_factory = sqlite3.Row
            row = c.execute("SELECT p_model, p_market, p_lo, p_lo_of, jc_sp"
                            " FROM board_leg_snapshot"
                            " WHERE market='had' AND leg=0").fetchone()
        assert row["p_model"] * row["jc_sp"] - 1 == pytest.approx(0.5563 * 1.60 - 1)
        ref = row[row["p_lo_of"]]
        assert row["p_lo"] * row["jc_sp"] - 1 < ref * row["jc_sp"] - 1, \
            "判闸必须比显示更保守"


class TestAppendOnly:
    def test_same_instant_is_idempotent_and_says_so(self, tmp_path: Path) -> None:
        """同一秒重跑不该翻倍 —— 且 `inserted` 必须诚实报 0。

        ⚠️ 只报「尝试了 N 条腿」会让重跑看起来像有新数据。
        """
        db = tmp_path / "obs.db"
        a = snapshot_board([_pred()], str(db), now=_NOW)
        b = snapshot_board([_pred()], str(db), now=_NOW)
        assert a["inserted"] == a["legs"] > 0
        assert b["legs"] == a["legs"] and b["inserted"] == 0, \
            "重跑该报 inserted=0,不该假装有新数据"
        with sqlite3.connect(db) as c:
            n = c.execute("SELECT COUNT(*) FROM board_leg_snapshot").fetchone()[0]
        assert n == a["legs"]

    def test_later_instant_appends_a_new_generation(self, tmp_path: Path) -> None:
        """⭐ 不同时刻 = 新一代,**不是** UPSERT 覆盖 —— 线史就是全部内容。"""
        db = tmp_path / "obs.db"
        snapshot_board([_pred()], str(db), now=_NOW)
        snapshot_board([_pred(jc_home=1.75)], str(db), now=_NOW + dt.timedelta(hours=3))
        with sqlite3.connect(db) as c:
            sps = [r[0] for r in c.execute(
                "SELECT jc_sp FROM board_leg_snapshot"
                " WHERE market='had' AND leg=0 ORDER BY captured_at")]
        assert sps == [1.60, 1.75], "盘口移动必须两代都在"

    def test_migration_adds_columns_to_a_preexisting_table(self, tmp_path: Path) -> None:
        """🚨 `CREATE TABLE IF NOT EXISTS` 对已存在的表是空操作 ⇒ 没有迁移路径的话,
        加一列会让 cron 在生产库上直接 `no such column` 猝死。

        空包弹:把 `ensure_tables` 里的 ALTER 循环删掉 ⇒ 这条红。
        """
        from nutmeg.v4.observation.board_snapshot import ensure_tables
        db = tmp_path / "obs.db"
        with sqlite3.connect(db) as c:   # 先造一张**旧版**表(缺新列)
            c.execute("CREATE TABLE board_leg_snapshot ("
                      " snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,"
                      " provenance_id INTEGER NOT NULL, captured_at TEXT NOT NULL,"
                      " match_date TEXT NOT NULL, league TEXT, home_team TEXT NOT NULL,"
                      " away_team TEXT NOT NULL, kickoff_utc TEXT, market TEXT NOT NULL,"
                      " handicap_home INTEGER, leg INTEGER NOT NULL, p_lo REAL,"
                      " jc_sp REAL, psc REAL, market_mode INTEGER,"
                      " single_available INTEGER, hours_to_ko REAL,"
                      " UNIQUE(captured_at, match_date, home_team, away_team,"
                      "        market, handicap_home, leg))")
            ensure_tables(c)
            cols = {r[1] for r in c.execute("PRAGMA table_info(board_leg_snapshot)")}
        for need in ("p_model", "p_market", "p_lo_of", "line_source",
                     "ou_line", "jc_captured_at", "odds_update"):
            assert need in cols, f"迁移没补上 {need} ⇒ 生产库上 INSERT 会炸"
        # 补完之后必须真能写进去
        res = snapshot_board([_pred()], str(db), now=_NOW)
        assert res["inserted"] == res["legs"] > 0

    def test_joins_to_jingcai_sp_with_real_rows_on_both_sides(
        self, tmp_path: Path,
    ) -> None:
        """🚨 第一版这条是**恒真**的:LEFT JOIN 打在**空的** jingcai_sp 上,
        `joined == 6` 只是左表行数 —— `ON 1=0` 也能过。典型的语法代理测语义。

        ⭐ 修法:右表先塞一行**真的对得上**的数据,再断言 join 出了非空右侧。

        空包弹:把 join 条件里的 `b.home_team=s.home_team` 改成 `b.league=s.league`
        ⇒ 这条红。
        """
        from nutmeg.v4.observation.jingcai_sp import ensure_jingcai_sp_table
        db = tmp_path / "obs.db"
        with sqlite3.connect(db) as c:
            ensure_jingcai_sp_table(c)
            c.execute(
                "INSERT INTO jingcai_sp (source, match_date, home_team, away_team,"
                " market, handicap_home, captured_at, hc_outcome)"
                " VALUES ('test','2026-08-12','Paris Saint Germain','Aston Villa',"
                "         'hhad',-1,'x',1)")
        snapshot_board([_pred()], str(db), now=_NOW)
        with sqlite3.connect(db) as c:
            hit = c.execute(
                "SELECT COUNT(*) FROM board_leg_snapshot b JOIN jingcai_sp s"
                "  ON b.match_date=s.match_date AND b.home_team=s.home_team"
                " AND b.away_team=s.away_team AND b.market=s.market"
                " AND b.handicap_home=s.handicap_home"
                " WHERE s.hc_outcome IS NOT NULL").fetchone()[0]
        assert hit == 3, (
            f"竞彩 −1 那条线的三条腿必须 join 上赛果,实际 {hit} —— "
            f"join 不上就没法结算,而这是快照唯一的学习出口")


class TestItDoesNotContaminateSigmaP:
    """🚨 本 cron 每天 5 个固定时刻打 serving 端点,而 serving 会往
    `odds_snapshots` 追加行。`sigma_p_fit` 要求「最靠近开球的点 ≤1.5h」否则整条
    轨迹丢弃 ⇒ 混进来就等于**给一个进行中的预注册测量换了抽样人口**
    (入选闸从「owner 恰好那时看了」变成「开球时刻是否贴着 cron 槽」)。

    ✅ **隔离机制 = 纯读者**:CLI 传 `record_line_history=false`,serving 把
    `snapshot_db` 传成 `None` ⇒ **一行都不写**。

    ⛔ 试过但不成立的两版,都记在这里免得有人绕回去:
    1. 「给 cron 自己的 source 标签」—— 去重键**不带 source**,标签只会把同一条
       线史拆给两个标签、把 `cup_market` 的轨迹打出洞。
    2. 「靠 σ_P 按 source 分组自动隔离」—— 那个分组轴本身 2026-08-13 被证伪
       并已改掉(prereg v2.3)。**把隔离建在一个错的前提上,前提一修隔离就没了。**

    ⚠️ 下面两条是**语法代理**(`inspect.getsource` + 字符串匹配),不是行为断言。
    它们钉的是「开关有没有被接上」;真正的行为证据是生产库里 cron 那 5 个时刻
    的写入行数 —— 见 §「上线后核对」,那个只能在真库上看。
    """

    def test_serving_writes_no_line_history_when_told_not_to(self) -> None:
        """⭐ 行为断言:`record_line_history=False` 时,serving 必须把
        `snapshot_db` 传成 None ⇒ `_gather_rows` 一行都不往 odds_snapshots 写。

        ⛔ 上一版我试过「给 cron 一个自己的 source 标签让 σ_P 分组自动隔离」——
        **不成立**:去重查的是 (fixture_id) 或 (date,league,home,away),
        **不带 source**,谁先跑到谁认领,标签只会把同一条线史拆给两个标签、
        把 cup_market 的轨迹打出洞。所以正解是**根本不写**。

        空包弹:把 routes 里的 `if record_line_history else None` 去掉 ⇒ 这条红。
        """
        import inspect

        from nutmeg.v4.api import routes as R
        for fn in (R.predictions_cup_market, R.predictions_sp_calc):
            src = inspect.getsource(fn)
            assert "record_line_history" in src, f"{fn.__name__} 没有这个开关"
            assert "if record_line_history else None" in src, (
                f"{fn.__name__} 拿到开关却没用它关掉 snapshot_db ⇒ 纯读者照样在写")

    def test_cli_declares_itself_a_reader(self) -> None:
        """CLI 必须传 `record_line_history=false`。

        空包弹:把 CLI 里那个 param 去掉 ⇒ 这条红。
        """
        import inspect

        from nutmeg.v4.cli import snapshot_board as M
        assert '"record_line_history": "false"' in inspect.getsource(M.main), (
            "CLI 没声明自己是纯读者 ⇒ 它的 5 个固定时刻会改掉 σ_P 的抽样人口")

    def test_sigma_p_pools_sources_into_one_trajectory_per_match(self, tmp_path) -> None:
        """⚠️ **本条 2026-08-13 反转了**:σ_P 现在按**比赛**池化,不再按 source 切。

        旧版断言 `len(trajs) == 2`(两个 source 两条轨迹),理由是「隔离赖以成立的
        前提就是分组带 source」。**那个理由已经不成立**:隔离靠的是上面两条 ——
        CLI 声明自己是纯读者、serving 把 `snapshot_db` 传成 None,**一行都不写**。
        写都不写,按什么分组就与污染无关了。

        而按 source 切本身是**错的**(prereg v2.3):线的走势是市场的属性,不是
        观测者的属性;实测 1544/1544 组各 source 记的价格完全相同,切开只会把
        同一条市场轨迹打成互相看不见的碎片、把锚推离收盘。

        📌 **留下这条(而不是删掉)是有意的** —— 它现在钉的是新轴,
        并且把「旧断言为什么被推翻」写在原地,免得日后有人照着旧理由改回去。

        空包弹:把 `sigma_p_fit` 的分组键 `k` 加回 `r["source"]`
        ⇒ 变回两条,`len(trajs) == 2`,这条红。
        """
        import sqlite3 as _s

        from nutmeg.v4.cli.sigma_p_fit import load_trajectories

        db = tmp_path / "obs.db"
        con = _s.connect(db)
        con.execute(
            "CREATE TABLE odds_snapshots (captured_at TEXT, source TEXT,"
            " home_team TEXT, away_team TEXT, match_date TEXT, league TEXT,"
            " kickoff_utc TEXT, psc_home REAL, psc_draw REAL, psc_away REAL)")
        ko = "2026-09-01T19:00:00+00:00"
        for src_lbl, (h, d, a) in (("cup_market", (2.00, 3.40, 3.80)),
                                   ("board_snapshot", (2.05, 3.35, 3.75))):
            for hrs, bump in ((6.0, 0.0), (1.0, 0.02)):   # 含 ≤1.5h 的近收盘锚
                ca = (dt.datetime.fromisoformat(ko) - dt.timedelta(hours=hrs))
                con.execute(
                    "INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (ca.isoformat(), src_lbl, "Alpha FC", "Beta FC", "2026-09-01",
                     "EPL", ko, h + bump, d, a))
        con.commit()
        con.close()

        trajs = load_trajectories(db)
        assert len(trajs) == 1, (
            f"同一场比赛被切成了 {len(trajs)} 条轨迹 ⇒ 分组轴还带着 source,"
            f"锚会被系统性推离收盘、低估国内层 σ_P 约 19%(prereg v2.3 §2③)")
        assert len(trajs[0]["points"]) == 4, (
            "池化后应当把两个 source 的 4 个观测点合成一条轨迹,"
            f"实际 {len(trajs[0]['points'])} 个")

    def test_multiple_kickoffs_take_the_latest_not_the_mode(self, tmp_path) -> None:
        """prereg v2.3 §3① —— 同一场多个 `kickoff_utc` 取 **max**,不是众数。

        实测 41/41 单调后移:Odds API `commence_time` 会更新成**实际**开球,
        API-Football `fixture.date` 是**排定**开球、从不更新。
        ⇒ **众数会系统性选中陈旧的排定时刻**(它出现次数更多)。

        本例:3 行排定 20:00、1 行更新为 20:30。众数 = 20:00(错),max = 20:30(对)。
        锚那条抓于 20:15 —— 按 20:00 算 h 为负会被丢弃,按 20:30 算 h=0.25 才留下。

        空包弹:把 `max(ks)` 改成 `statistics.mode(ks)` ⇒ 锚被丢,这条红。
        """
        import sqlite3 as _s

        from nutmeg.v4.cli.sigma_p_fit import load_trajectories

        db = tmp_path / "obs.db"
        con = _s.connect(db)
        con.execute(
            "CREATE TABLE odds_snapshots (captured_at TEXT, source TEXT,"
            " home_team TEXT, away_team TEXT, match_date TEXT, league TEXT,"
            " kickoff_utc TEXT, psc_home REAL, psc_draw REAL, psc_away REAL)")
        sched, actual = "2026-09-01T20:00:00+00:00", "2026-09-01T20:30:00+00:00"
        rows = [("2026-09-01T14:00:00+00:00", sched), ("2026-09-01T17:00:00+00:00", sched),
                ("2026-09-01T19:00:00+00:00", sched), ("2026-09-01T20:15:00+00:00", actual)]
        for i, (ca, ko) in enumerate(rows):
            con.execute("INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (ca, "closing", "Alpha FC", "Beta FC", "2026-09-01", "EPL", ko,
                         2.00 + i * 0.01, 3.40, 3.80))
        con.commit()
        con.close()

        trajs = load_trajectories(db)
        assert len(trajs) == 1, f"这一场应当产出一条轨迹,实际 {len(trajs)}"
        assert abs(trajs[0]["points"][0][0] - 0.25) < 1e-6, (
            "锚的 h 必须按**实际**开球(20:30)算出 0.25h;"
            f"实际 {trajs[0]['points'][0][0]:.3f}h ⇒ 用的是陈旧的排定时刻")

    def test_a_wild_kickoff_drops_the_trajectory_and_is_counted(self, tmp_path) -> None:
        """prereg v2.3 §3① 护栏:开球跨度 >3h ⇒ 整条丢弃,**且计数上仪表**。

        没有这条,上游哪天把某场的时刻写飞,整条轨迹的 h 轴会被静默平移。
        计数必须可见 —— 静默护栏 = 又一个「零告警所以没问题」的假信号。

        空包弹:删掉 `_KO_SPREAD_MAX_H` 那个 if ⇒ 轨迹留下,这条红。
        """
        import sqlite3 as _s

        from nutmeg.v4.cli import sigma_p_fit as M

        db = tmp_path / "obs.db"
        con = _s.connect(db)
        con.execute(
            "CREATE TABLE odds_snapshots (captured_at TEXT, source TEXT,"
            " home_team TEXT, away_team TEXT, match_date TEXT, league TEXT,"
            " kickoff_utc TEXT, psc_home REAL, psc_draw REAL, psc_away REAL)")
        for ca, ko in (("2026-09-01T14:00:00+00:00", "2026-09-01T20:00:00+00:00"),
                       ("2026-09-01T19:00:00+00:00", "2026-09-02T09:00:00+00:00")):
            con.execute("INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (ca, "closing", "Alpha FC", "Beta FC", "2026-09-01", "EPL", ko,
                         2.00, 3.40, 3.80))
        con.commit()
        con.close()

        assert M.load_trajectories(db) == [], "开球时刻写飞了却没丢弃"
        assert M._LOAD_STATS["ko_spread_dropped"] == 1, (
            f"丢弃了却没计数 ⇒ 仪表上看不见,实际 {M._LOAD_STATS['ko_spread_dropped']}")
