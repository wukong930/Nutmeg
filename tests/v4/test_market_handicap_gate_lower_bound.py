"""`/recommend/market-handicap` 判闸/选腿/注额一律走 δ 下界(2026-08-07 P0-5)。

## 为什么

2026-08-06 钱路审查实测:这个端点**会记录的 64 注里 90.6% 被看板自己拒绝**,
22% 选中的是**另一条腿**。原因是两套口径:

* 看板(`_spcalcHcRecalc` / `_cupHcRecalc`):`PB.lo[o] × sp − 1 >= 0.05`
* 这个端点:点估 `P[o] × sp − 1 > 0`

而这个端点**没有前置判闸** —— 按钮就在每张市场模式让球卡上,点了直接进台账。
⇒ 台账人口 ≠ 决策人口,秋季算 ROI 时算的是另一群注,而且**不可回溯**
(库里不存当时的下界)。

## 四处必须同时对,且各自能被单独打红

1. EV 用下界(不是点估)
2. argmax 用下界(用点估选、用下界判 ⇒ 选中「点估最高但下界不是最高」的腿)
3. 闸用 `DEFAULT_MIN_EV_PER_UNIT`(0.05),不是 `> 0`
4. Kelly 的 `hit_probability` 用下界(和判闸同源)

⛔ 展示侧(`market_implied_p`)和落库的 `p_handicap` **仍必须是点估** ——
`c1_leg_lower_bounds` 的契约写明下界不是概率分布(三腿和 < 1),只许判闸。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api.routes import router as v4_router
from nutmeg.v4.combo.lottery_rules import DEFAULT_MIN_EV_PER_UNIT
from nutmeg.v4.model.market_handicap import c1_leg_lower_bounds, implied_handicap_lines

#: −1 让球线:C1 碰 让胜 + 让平 ⇒ 这两条腿的下界严格低于点估,让负是锚(下界 = 点估)。
#: 选 −1 是因为它同时能测「下界 < 点估」和「第三腿下界 = 点估」两种情形。
_LINE = -1


def _client():
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


#: δ **覆盖内**(白名单 10 联赛之一)—— 走「δ 已施加」那条分支。
#: 🚨 2026-08-17 之前本文件只用 `JPN_J1`,而 `truth` 夹具又不传 league ⇒
#:    被测端点和对照组**同被抑制**、断言恒成立。变异实测:白名单清空 → 全套红 18 条,
#:    闸改 no-op → 红 6 条,**本文件两种变异下 0 红** —— 它守的是会写台账的钱路端点。
#:    ⇒ 现在两条分支都跑,且 `test_the_two_parametrisations_actually_differ` 钉住二者不同。
_IN_SCOPE = "ESP_LA_LIGA"
#: δ 覆盖外 —— 也是这个端点的**典型人口**(市场模式 = J1/杯赛),所以必须保留。
_OUT_SCOPE = "JPN_J1"


def _body(league: str = _OUT_SCOPE, **over):
    b = {
        "league": league, "date": "2026-08-10",
        "home_team": "Kashima", "away_team": "Urawa",
        "handicap_home": _LINE,
        "psc_home": 2.10, "psc_draw": 3.40, "psc_away": 3.60,
        "psc_over25": 1.95, "psc_under25": 1.90, "ou_line": 2.5,
        "odds_handicap_H": 1.80, "odds_handicap_D": 3.30, "odds_handicap_A": 4.20,
        "bankroll": 10000.0, "kelly_fraction": 0.25,
        "record_session": False,
    }
    b.update(over)
    return b


@pytest.fixture(scope="module", params=[_IN_SCOPE, _OUT_SCOPE],
                ids=["δ覆盖内", "δ覆盖外"])
def truth(request):
    """独立复算点估与下界 —— 不从被测端点取,否则是自证。

    🚨 **必须把 league 传下去。** 原版不传 ⇒ 对照组永远算「覆盖外」的数,
    而端点用 `req.league`;`_body()` 又恰好用覆盖外的 `JPN_J1` ⇒ 两边同被抑制、
    每条断言恒成立。**对照组和被测对象必须在同一个分支上。**
    """
    from nutmeg.v4.api.routes import _pinnacle_devig_1x2
    from nutmeg.v4.model.market_handicap import devig_over
    lg = request.param
    b = _body(lg)
    fair = _pinnacle_devig_1x2(b["psc_home"], b["psc_draw"], b["psc_away"])
    p_over = devig_over(b["psc_over25"], b["psc_under25"])
    lines = implied_handicap_lines(fair[0], fair[1], fair[2], p_over,
                                   ou_line=b["ou_line"], c1=True, league=lg)
    _, ph, pd_, pa = next(ln for ln in lines if ln[0] == _LINE)
    lo = c1_leg_lower_bounds(_LINE, ph, pd_, pa, league=lg)
    return {"league": lg, "point": (ph, pd_, pa), "lo": lo}


def test_fixture_actually_separates_point_and_lower_bound(truth):
    """⭐ 前提自检:下界必须**严格低于**点估,否则下面全部测试都是空洞的。

    「测试的前提没人检查」是本项目栽过的形状 —— 如果 C1 哪天不碰这条线了,
    点估 == 下界,那么所有「用了哪个」的断言都恒真,而它们看起来还是绿的。
    """
    ph, pd_, pa = truth["point"]
    lo_h, lo_d, lo_a = truth["lo"]
    assert lo_h < ph - 1e-6, f"让胜下界没低于点估({lo_h} vs {ph})—— fixture 失效"
    assert lo_d < pd_ - 1e-6, f"让平下界没低于点估({lo_d} vs {pd_})"
    # ⭐ 2026-08-08 改:原来断言「让负是 −1 线的锚,下界应 = 点估」。
    # 那句话描述的是**当时的实现**,而本测试的**目的**是「fixture 要能区分点估和下界」——
    # 三条腿都分离了,对这个目的是严格变好。锚腿现在吃自己的 SE(δ 测不出、但 SE≠0),
    # 见 `_C1_THIRD_SE_M1`。⇒ 断言改成和两个兄弟同形。
    assert lo_a < pa - 1e-6, f"让负下界没低于点估({lo_a} vs {pa})—— 第三腿又退回零收缩了"


def test_the_two_parametrisations_actually_differ():
    """⭐⭐ **前提自检:双参数化不能是装饰。**

    覆盖内和覆盖外必须给出**不同**的点估和下界,否则「跑了两遍」等于跑了一遍两次,
    而本文件从 08-16 到 08-17 正是这个状态(两边同被抑制)。

    两处差异都必须在:
      · 点估 —— δ₋₁ 只在覆盖内扣掉 4.6pp
      · 带宽 —— 覆盖内 2×0.0078,覆盖外吃 `_UNCAL_SE` 地板 2×0.078(**10 倍**)
    ⚠️ 只查带宽会漏掉「δ 点估修正被撤销」那一半 —— 而那一半的方向是**更容易下注**
       (让胜 P 变高 ⇒ EV 变高),不是保守。
    """
    from nutmeg.v4.api.routes import _pinnacle_devig_1x2
    from nutmeg.v4.model.market_handicap import devig_over
    b = _body()
    fair = _pinnacle_devig_1x2(b["psc_home"], b["psc_draw"], b["psc_away"])
    p_over = devig_over(b["psc_over25"], b["psc_under25"])

    def leg(lg):
        lines = implied_handicap_lines(fair[0], fair[1], fair[2], p_over,
                                       ou_line=b["ou_line"], c1=True, league=lg)
        _, ph, pd_, pa = next(ln for ln in lines if ln[0] == _LINE)
        return ph, ph - c1_leg_lower_bounds(_LINE, ph, pd_, pa, league=lg)[0]

    p_in, band_in = leg(_IN_SCOPE)
    p_out, band_out = leg(_OUT_SCOPE)
    assert p_in < p_out - 1e-4, (
        f"覆盖内外的**点估**一样({p_in} vs {p_out})—— δ₋₁ 没被施加,"
        f"或 `_IN_SCOPE={_IN_SCOPE}` 已不在白名单里 ⇒ 本文件退回恒真")
    assert band_out > band_in * 5, (
        f"覆盖内外的**带宽**没拉开(内 {band_in:.4f} / 外 {band_out:.4f})—— "
        f"`_UNCAL_SE` 地板没生效 ⇒ 本文件退回恒真")


def test_in_scope_constant_is_really_in_scope():
    """`_IN_SCOPE` 是个字面量,白名单是另一个字面量 —— 它们会漂。

    上一条依赖 `_IN_SCOPE` 真在覆盖内;这条直接问闸本身,失败信息才指得准。
    """
    from nutmeg.v4.model.market_handicap import _delta_in_scope
    assert _delta_in_scope(_IN_SCOPE), f"{_IN_SCOPE} 不在 δ 白名单里了"
    assert not _delta_in_scope(_OUT_SCOPE), f"{_OUT_SCOPE} 进白名单了 —— 本文件失去对照组"


class TestGateUsesLowerBound:
    def test_reported_ev_comes_from_the_lower_bound(self, truth):
        """EV 必须由下界算出。点估算的 EV 更高,差值就是被修掉的那部分乐观。"""
        r = _client().post("/api/v4/recommend/market-handicap", json=_body(truth["league"]))
        assert r.status_code == 200, r.text
        d = r.json()
        sp = _body(truth["league"])["odds_handicap_H"]
        want_lo = truth["lo"][0] * sp - 1.0
        want_pt = truth["point"][0] * sp - 1.0
        got = d["ev_per_unit"][0]
        assert got == pytest.approx(want_lo, abs=1e-9), (
            f"让胜 EV={got};下界应为 {want_lo:.6f},点估为 {want_pt:.6f} —— 疑似用了点估")

    def test_display_p_stays_the_point_estimate(self, truth):
        """⛔ 反向红线:回包的 `market_implied_p` **必须**还是点估。

        下界不是概率分布(三腿和 < 1),`c1_leg_lower_bounds` 的 docstring 明令
        不许展示/归一化。把下界回包会让前端画出一个不存在的统计量。
        """
        d = _client().post("/api/v4/recommend/market-handicap", json=_body(truth["league"])).json()
        assert d["market_implied_p"] == pytest.approx(list(truth["point"]), abs=1e-9), \
            "展示侧被换成了下界 —— 违反 c1_leg_lower_bounds 契约"

    def test_a_leg_between_zero_and_five_percent_is_not_recorded(self, truth):
        """⭐ 承重条:0~5% 这一段**不该**是注。

        改之前闸是 `ev > 0` ⇒ 这一段全部进台账,而看板从不推荐它们。
        构造一个让下界 EV 恰好落在 (0, 0.05) 的 SP。
        """
        lo_h = truth["lo"][0]
        sp = 1.03 / lo_h                       # 下界 EV ≈ +3%,在闸下
        d = _client().post("/api/v4/recommend/market-handicap",
                           json=_body(truth["league"], odds_handicap_H=round(sp, 4),
                                      odds_handicap_D=1.01, odds_handicap_A=1.01)).json()
        ev_h = d["ev_per_unit"][0]
        assert 0 < ev_h < DEFAULT_MIN_EV_PER_UNIT, f"fixture 没落进 (0, 5%):{ev_h}"
        assert (d.get("best_stake") or 0) == 0, "0~5% 的腿给出了非零注额 ⇒ 闸还是 `> 0`"
        assert not d.get("recorded"), "0~5% 的腿被记进台账了"

    def test_a_leg_clearing_five_percent_on_the_lower_bound_is_a_bet(self, truth):
        """反向 —— 别把闸焊死。下界 EV ≥ 5% 就该给注额。"""
        lo_h = truth["lo"][0]
        sp = 1.20 / lo_h                       # 下界 EV ≈ +20%
        d = _client().post("/api/v4/recommend/market-handicap",
                           json=_body(truth["league"], odds_handicap_H=round(sp, 4),
                                      odds_handicap_D=1.01, odds_handicap_A=1.01)).json()
        assert d["best_outcome"] == "H", d
        assert (d.get("best_stake") or 0) > 0, "下界 +20% 的腿没给注额 —— 闸被焊死了?"

    def test_stake_is_kelly_on_the_lower_bound_not_the_point_estimate(self, truth):
        """⭐ 注额也必须和判闸同源。

        ⚠️ 这条是**变异检验逼出来的**:头一版护栏只断言了 EV / 闸 / argmax,
        把 `hit_probability=PLO[best]` 换回点估 **6 条测试全绿** —— 注额那条路当时是裸的。
        「四处都改对了」和「四处都被守住了」是两回事,不跑变异就分不出来。

        Kelly 注额随 hit_probability 单调增 ⇒ 用点估会**系统性下大**。
        这里独立复算一遍 Kelly,逐分对比。
        """
        from nutmeg.v4.combo.kelly import fractional_kelly_stake
        b = _body(truth["league"])
        lo_h = truth["lo"][0]
        sp = round(1.20 / lo_h, 4)
        d = _client().post("/api/v4/recommend/market-handicap",
                           json=_body(truth["league"], odds_handicap_H=sp,
                                      odds_handicap_D=1.01, odds_handicap_A=1.01)).json()
        ev = lo_h * sp - 1.0
        want = max(float(fractional_kelly_stake(
            hit_probability=lo_h, ev_per_unit=ev,
            bankroll=b["bankroll"], kelly_fraction=b["kelly_fraction"],
        ).recommended_stake), 2.0)
        pt = max(float(fractional_kelly_stake(
            hit_probability=truth["point"][0], ev_per_unit=ev,
            bankroll=b["bankroll"], kelly_fraction=b["kelly_fraction"],
        ).recommended_stake), 2.0)
        assert want != pytest.approx(pt), "fixture 没造出差异 —— 两个 P 给出同样注额,本条空洞"
        assert d["best_stake"] == pytest.approx(want, abs=1e-6), (
            f"注额={d['best_stake']};下界应给 {want:.2f},点估会给 {pt:.2f} —— 疑似用了点估")

    def test_argmax_follows_the_lower_bound_not_the_point_estimate(self, truth):
        """⭐ 选腿也必须走下界。

        构造:让胜和让负的**点估 EV** 让胜更高,但**下界 EV** 让负更高
        (让负是 −1 线的锚、下界 = 点估,让胜被 δ 误差压低)。
        用点估选会选 H,用下界选会选 A —— 审查实测 22% 的注就是这么选错的。
        """
        ph, _, pa = truth["point"]
        lo_h, _, lo_a = truth["lo"]
        # 让两条腿的点估 EV 相等 ⇒ 差异只来自下界
        sp_h, sp_a = 1.30 / ph, 1.30 / pa
        d = _client().post("/api/v4/recommend/market-handicap",
                           json=_body(truth["league"], odds_handicap_H=round(sp_h, 4),
                                      odds_handicap_D=1.01,
                                      odds_handicap_A=round(sp_a, 4))).json()
        ev_lo_h, ev_lo_a = lo_h * sp_h - 1, lo_a * sp_a - 1
        assert ev_lo_a > ev_lo_h, f"fixture 没造出分歧:{ev_lo_h:.4f} vs {ev_lo_a:.4f}"
        assert d["best_outcome"] == "A", (
            f"选了 {d['best_outcome']} —— 点估 EV 两腿相等,选 H 说明 argmax 还在看点估")
