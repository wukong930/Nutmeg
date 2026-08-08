"""δ₁ₓ₂ —— 1X2 腿判闸下界(2026-08-08 上线)。

预注册 `docs/onex_delta_prereg_v1.0_2026-08-08.md`(先于测量提交,`e26a7a1`)
测量   `docs/onex_delta_measurement_2026-08-08.md`
复现   `scripts/onex_delta_calibration.py` · `scripts/onex_argmax_flip.py`

守的东西:
① 常数是**实测值**,不许被谁顺手改掉
② `ONEX_SE_K` 必须等于让球侧的 `_C1_SE_K` —— 两类腿在同一个 evLo 排序里竞争,
   k 不同 = 偷偷给一边加权
③ **行为**:1X2 腿在前端真的拿到了收缩(evLo < ev),不是只在服务端算了没人用
④ 无 Pinnacle 线时优雅退化(lo=null ⇒ evLo≡ev),不炸
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from nutmeg.v4.model.market_handicap import _C1_SE_K
from nutmeg.v4.model.onex_calibration import (
    ONEX_SE,
    ONEX_SE_K,
    onex_leg_lower_bounds,
)

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _fn(name: str) -> str:
    """抠出一个顶层函数体(行首锚定 —— 注释里出现同名串不算)。

    `async?` 是 2026-08-08 补的:三个 reprice 调用点都是 `async function`,
    原来的 `^function` 锚一个都抠不出来 —— 而它抛的是 AssertionError
    「不在 dashboard.html 里」,长得像「函数被删了」而不是「正则没盖住」。
    """
    s = DASH.read_text(encoding="utf-8")
    m = re.search(rf"^(?:async )?function {re.escape(name)}\(", s, re.M)
    assert m, f"{name} 不在 dashboard.html 里"
    i = m.start()
    d, j = 0, s.index("{", i)
    for k in range(j, len(s)):
        if s[k] == "{":
            d += 1
        elif s[k] == "}":
            d -= 1
            if not d:
                return s[i:k + 1]
    raise AssertionError(f"{name} 花括号没配平")


def test_constants_are_the_measured_ones() -> None:
    """⛔ 这三个数来自 6,516 场 / 871 个比赛日的比赛日聚类 SE。

    改它们 = 改判闸。要改就得连 `docs/onex_delta_measurement_2026-08-08.md`
    一起改,并说明新测量是什么。
    """
    assert ONEX_SE == (0.0058, 0.0056, 0.0056), (
        "δ₁ₓ₂ 的 SE 变了 —— 它是 1X2 腿下界的**唯一**来源")
    doc = (REPO / "docs/onex_delta_measurement_2026-08-08.md").read_text(encoding="utf-8")
    assert "0.0058, 0.0056, 0.0056" in doc, "常数和测量文档对不上了"


def test_k_matches_the_handicap_side() -> None:
    """⭐ 承重:两类腿在**同一个 evLo 排序**里抢每场的 argmax。

    k 不同 = 给其中一类腿一个纯粹来自「保守倍数选得不一样」的优势 ——
    那正是本次修复要消灭的东西(1X2 侧原本 k·SE ≡ 0)。
    """
    assert ONEX_SE_K == _C1_SE_K, (
        f"1X2 侧 k={ONEX_SE_K} 而让球侧 k={_C1_SE_K} —— 排序天平又歪了")


def test_lower_bounds_shrink_each_leg_and_clamp_at_zero() -> None:
    lo = onex_leg_lower_bounds(0.45, 0.28, 0.27)
    assert lo == pytest.approx((0.45 - 2 * 0.0058, 0.28 - 2 * 0.0056,
                                0.27 - 2 * 0.0056))
    assert onex_leg_lower_bounds(0.005, 0.5, 0.495)[0] == 0.0, "没钳到 0,会出负概率"
    # 契约与让球侧一致:返回的**不是**分布
    assert sum(onex_leg_lower_bounds(1 / 3, 1 / 3, 1 / 3)) < 1.0


def _run_boardlegs(pr: dict) -> list[dict]:
    """跑**生产源码**里的 `_boardLegs`,只喂 1X2 分支(jc_hc_line=null)。

    ⭐ 为什么必须跑真源码:上一次同族的教训是「断言 markup 而不是断言机制」——
    把 `_openFolds.add` 改成 no-op 测试照样绿。这里要证明的是
    「下界**真的进了 evLo**」,只有执行能证明。
    """
    src = _fn("_boardLegs")
    stub = """
      function _evRelTier(p) { return p > 0 && p < 1 ? 'edge' : null; }
      function _sweetEffSp(mode, idx, mkt, o, fb) { return fb; }
      function _frzHalfEv() { return 0; }
      function t(k) { return k; }
      function _mktP(pr) { return null; }
      const document = { getElementById: () => null };
    """
    r = subprocess.run(
        ["node", "-e", stub + "\n" + src +
         f"\nconst pr = {json.dumps(pr)};"
         "\nconsole.log(JSON.stringify(_boardLegs(pr, 0, 'cup')));"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[:1500]
    return json.loads(r.stdout)


_PR = {
    "p_home_1x2": 0.50, "p_draw_1x2": 0.26, "p_away_1x2": 0.24,
    "jc_home": 2.20, "jc_draw": 3.60, "jc_away": 3.90,
    "jc_hc_line": None, "handicap_lines": None,
}


def test_1x2_legs_actually_receive_the_shrink_end_to_end() -> None:
    """⭐ 行为断言:前端算出来的 `evLo` 必须**严格小于** `ev`,差值 = k·SE × SP。

    2026-08-08 之前这里传的是字面量 `null` ⇒ `evLo ≡ ev` ⇒ 1X2 腿零收缩。
    """
    lo = onex_leg_lower_bounds(_PR["p_home_1x2"], _PR["p_draw_1x2"], _PR["p_away_1x2"])
    legs = _run_boardlegs({**_PR,
                           "onex_lo_home": lo[0], "onex_lo_draw": lo[1],
                           "onex_lo_away": lo[2]})
    assert len(legs) == 3, f"1X2 三条腿没都出来:{legs}"
    got = {lg["o"]: lg for lg in legs}
    for o, i, sp in (("H", 0, 2.20), ("D", 1, 3.60), ("A", 2, 3.90)):
        lg = got[o]
        assert lg["evLo"] < lg["ev"], f"{o} 腿没被收缩 —— 下界没进 evLo"
        assert lg["ev"] - lg["evLo"] == pytest.approx(
            ONEX_SE_K * ONEX_SE[i] * sp, abs=1e-9), (
            f"{o} 腿的收缩量不是 k·SE×SP —— 中间有人改了口径")


def test_missing_pinnacle_line_degrades_instead_of_crashing() -> None:
    """无 Pinnacle 线 ⇒ 服务端下发 null ⇒ 回到 `evLo ≡ ev`,不能炸也不能出 NaN。

    (这条腿本来也进不了榜,但 `_boardLegs` 不该因为字段缺失就整场失败。)
    """
    legs = _run_boardlegs(dict(_PR))          # 三个 onex_lo_* 全缺
    assert len(legs) == 3
    for lg in legs:
        assert lg["evLo"] == pytest.approx(lg["ev"]), "缺字段时不该凭空收缩"
        assert lg["evLo"] == lg["evLo"], "出了 NaN"


def test_handicap_share_is_display_only() -> None:
    """⚠️ 让球腿占比是**纯显示**:不许出现在选池/排序/判闸里。

    它没有阈值(没人测过多少算多),所以任何拿它和一个数比大小的写法都是越界。
    """
    src = DASH.read_text(encoding="utf-8")
    assert "pb_hcshare" in src, "让球腿占比没了 —— 集中度就又不可见了"
    for fname in ("_parlayPool", "_parlayCombos", "_parlayPicks", "_boardLegs"):
        body = _fn(fname)
        assert "hcshare" not in body and "hcShare" not in body, (
            f"{fname} 里出现了让球腿占比 —— 它进了选择路径")


def test_market_mode_row_carries_the_bound_server_side() -> None:
    """市场模式:服务端**真的**把下界装进了 `SinglePrediction`。

    `_row_to_market_prediction` 吃一个普通 dict,所以这条能跑真函数。
    ⚠️ 标准模式那条发射点在 `predictions_sp_calc` 体内(要 artifact + fixtures),
       单测跑不动 —— 它由**重启后打活服务**验证,不是由这里验证。别假装它被覆盖了。
    """
    from nutmeg.v4.api.routes import _onex_lo, _row_to_market_prediction

    assert _onex_lo(None) == (None, None, None), "没线时该全 None,不是 0"
    row = {"home_team": "A", "away_team": "B", "league": "L", "date": "2026-08-08",
           "psc_home": 2.10, "psc_draw": 3.50, "psc_away": 3.80}
    mp = _row_to_market_prediction(row)
    assert mp is not None
    for lo_v, p_v in ((mp.onex_lo_home, mp.p_home_1x2),
                      (mp.onex_lo_draw, mp.p_draw_1x2),
                      (mp.onex_lo_away, mp.p_away_1x2)):
        assert lo_v is not None, "市场模式没下发下界 —— 前端会退回 evLo≡ev"
        assert lo_v < p_v, "下发的下界没有比点估小"
    assert mp.p_home_1x2 - mp.onex_lo_home == pytest.approx(ONEX_SE_K * ONEX_SE[0])


# ---------------------------------------------------------------------------
# 手填 Pinnacle 那条路(2026-08-08 · v150)
#
# 为什么必须单独守:上面那条只覆盖 `_row_to_market_prediction`,而**手填走的是
# `/recommend/market-reprice`,完全另一条路**。日乙(JPN_J2)两条 Pinnacle 源都
# 拿不到(Odds API 无 sport key + AF 逐场零家博彩),手填是它**唯一**的路 ⇒
# 这条路上缺下界 = δ₁ₓ₂ 对日乙形同没上线。
# ---------------------------------------------------------------------------

def test_reprice_carries_the_same_bound_as_the_auto_card() -> None:
    """⭐ 判据是「两条路对同一个 Pinnacle 报价给出**逐位相同**的下界」。

    ⛔ 不是「reprice 回包里有三个 onex_lo_* 字段」—— 那个断言被「前端/服务端各写
    一份 k·SE」的实现照样满足,而那正是 WPO 那次 server↔JS 漂移的形状。
    """
    from nutmeg.v4.api.routes import _row_to_market_prediction, recommend_market_reprice
    from nutmeg.v4.api.schemas import MarketRepriceRequest

    H, D, A = 2.10, 3.50, 3.80
    auto = _row_to_market_prediction(
        {"home_team": "A", "away_team": "B", "league": "JPN_J2",
         "date": "2026-08-08", "psc_home": H, "psc_draw": D, "psc_away": A})
    man = recommend_market_reprice(MarketRepriceRequest(psc_home=H, psc_draw=D, psc_away=A))

    for got, want in ((man.onex_lo_home, auto.onex_lo_home),
                      (man.onex_lo_draw, auto.onex_lo_draw),
                      (man.onex_lo_away, auto.onex_lo_away)):
        assert got is not None, "手填路径没下发下界 —— 前端会退回 evLo≡ev(零收缩)"
        assert got == pytest.approx(want, abs=1e-12), "两条路的下界漂开了"

    # 更有牙的不变量:收缩量恒等于 k·SE。一个「照旧盘口算的陈旧下界」也满足
    # `lo < p`,却过不了这一条 —— 而陈旧下界正是本次修的两种形态之一。
    for lo, p, se in ((man.onex_lo_home, man.p_home_1x2, ONEX_SE[0]),
                      (man.onex_lo_draw, man.p_draw_1x2, ONEX_SE[1]),
                      (man.onex_lo_away, man.p_away_1x2, ONEX_SE[2])):
        assert p - lo == pytest.approx(ONEX_SE_K * se, abs=1e-12)


def test_all_three_reprice_call_sites_write_the_bound_onto_the_card() -> None:
    """⭐ 服务端送了 ≠ 卡上用了。

    病史同 `test_manual_bet_odds_source.py`:前端送了、后端读了,中间那层静默吞掉。
    ⛔ 这是**语法**断言,只能证明「三处都往卡上写了下界」,证明不了写的值对 ——
       值的正确性由上面那条(两条路逐位相同)和下面那条(钳位)行为断言守。
       之所以还要它:三个调用点里**最容易漏的是 `_cupManRefreshDerived`**,
       而那个函数正是 2026-07-18 为「让球侧 p_*_lo 缺失」专门加的重算路径 ——
       同一个洞换一条腿又犯了一次,漏掉它等于修复不覆盖「刷新后贴回」。

    ⚠️ 断言必须贴着**赋值**写(`pr.onex_lo_home =`),不能只查 `onex_lo_home`
       在不在函数体里 —— 我第一版就是那么写的,空包弹当场证伪:删掉赋值之后
       函数体里仍有 `lo: [data.onex_lo_home, …]`(存 localStorage 那一行),
       测试照样绿。**假绿比没有护栏更坏**,因为它让人以为查过了。
    """
    for fname in ("_cupManualReprice", "_spcalcManualReprice", "_cupManRefreshDerived"):
        body = _fn(fname)
        assert re.search(r"pr\.onex_lo_home\s*=", body), (
            f"{fname} 没有把 1X2 下界写回卡上 —— 手填后点估换了、下界还停在旧盘口")


def test_a_stale_bound_can_no_longer_loosen_the_gate() -> None:
    """⭐ 行为断言:下界**永远不许大于点估**。

    实测的坏形状(2026-08-08):自动线 P=0.42 ⇒ 下界 0.4084;owner 手填真 Pinnacle
    得 P=0.39。竞彩 SP=2.60 时点估 EV=+1.4% 过不了 +5% 闸,而**陈旧**下界给出
    +6.2% —— **下界过闸而点估过不了**,下界变成了上界。同
    `market_handicap.py` 那条「越不可信越容易变绿」的形状。
    """
    pr = {"p_home_1x2": 0.39, "p_draw_1x2": 0.31, "p_away_1x2": 0.30,
          "jc_home": 2.60, "jc_draw": 3.40, "jc_away": 3.50,
          # 故意喂一个来自**另一条线**的下界(比点估还大)
          "onex_lo_home": 0.4084, "onex_lo_draw": 0.2988, "onex_lo_away": 0.2888,
          "jc_hc_line": None, "handicap_lines": None}
    got = {lg["o"]: lg for lg in _run_boardlegs(pr)}
    h = got["H"]
    assert h["evLo"] <= h["ev"] + 1e-12, (
        f"下界({h['evLo']:.4%})反超点估({h['ev']:.4%}) —— 判闸被放松了")
    # 钳位前这条腿会是 +6.18%(过 +5% 闸);钳位后必须回到点估
    assert h["evLo"] == pytest.approx(0.39 * 2.60 - 1, abs=1e-12)
    assert h["evLo"] < 0.05, "这条腿本不该过 +5% 闸"


def test_an_impossible_book_is_rejected_and_a_real_one_is_not() -> None:
    """⛔ 手滑闸:抽水 ≤0 的「盘口」物理上不存在。

    实测(2026-08-08)的真实手滑:`1.9 / 33.5 / 3.3`(本该 `1.9 / 3.35 / 3.3`)
    ⇒ booksum 0.8592、抽水 **−14.08%**。当时**没有任何一道闸会响**,而面板用
    **绿色**显示「✓ 已应用 · 水位 −14.1%」;打**对**了反而标黄 ⇒ 提示方向是反的。
    钱的量级:主胜公允 P 0.4837 → 0.5733(+8.96pp),竞彩 SP 2.00 时
    EV 从 −3.3% 变成 **+14.7%**,穿过 +5% 闸。

    ⚠️ 判据必须**零误报**:booksum>1 对任何真盘口恒成立,所以它不是经验阈值、
    不会随联赛/季节漂移 —— 这也是它不需要预注册的原因。
    """
    from nutmeg.v4.model.devig import is_impossible_book, is_wide_book

    assert is_impossible_book(1.9, 33.5, 3.3), "小数点丢一位没被拦下"
    assert not is_impossible_book(1.9, 3.35, 3.3), "正常的 12.8% 抽水被冤枉了"
    # ⭐ 两道闸必须是**两个**函数:`is_wide_book` 判「配不配当 sharp 锚」,有 6 个
    # 调用点靠它降级;把下界塞进同一个布尔会让那 6 处一起改变行为。
    assert not is_wide_book(1.9, 33.5, 3.3), (
        "水位闸不该管这件事 —— 它只有上界,这正是当初漏掉手滑的原因")
    assert is_wide_book(1.9, 3.35, 3.3), "12.8% > 8% 仍该被判为宽水位"
    # 算不出水位时两边都不冤枉(与 book_vig 的 None 惯例一致)
    assert not is_impossible_book(1.9, None, 3.3)


def test_hand_typed_pinnacle_never_reaches_the_jingcai_sp_table() -> None:
    """🚨 `jingcai_sp.psc_*` 的语义是「采集那一刻**观测到的** Pinnacle 线」。

    手填是 owner 自己打的数,不是观测。而表里**没有任何一列**分得出来
    (`source` 标的是「哪块屏幕」= market_mode,自动线和手填线一模一样)。
    读它的有 6 个 CLI,其中 **`delta_calibration`** 算的是让球腿的判闸下界常数
    ⇒ 手填值进去 = owner 的手输值参与决定判闸门槛,自我指涉。

    判据是**行为**:跑真的 `_jcCapturePsc`,`_manual` 卡必须整组送 null。
    """
    import json
    import subprocess

    src = _fn("_jcCapturePsc")
    probe = (src + "\n"
             "const auto = _jcCapturePsc({psc_home:2.1, psc_draw:3.5, psc_away:3.8,"
             " psc_over25:1.9, psc_under25:1.95, ou_line:2.5});\n"
             "const man  = _jcCapturePsc({psc_home:2.1, psc_draw:3.5, psc_away:3.8,"
             " psc_over25:1.9, psc_under25:1.95, ou_line:2.5, _manual:true});\n"
             "console.log(JSON.stringify({auto, man}));")
    r = subprocess.run(["node", "-e", probe], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[:1500]
    out = json.loads(r.stdout)
    assert out["auto"]["psc_home"] == 2.1, "自动线不该被误伤 —— 那是真观测,要写库"
    assert out["auto"]["psc_over"] == 1.9
    assert all(v is None for v in out["man"].values()), (
        f"手填卡把 Pinnacle 送进观测库了:{out['man']}")
