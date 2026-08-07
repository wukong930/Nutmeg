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
    """抠出一个顶层函数体(行首锚定 —— 注释里出现同名串不算)。"""
    s = DASH.read_text(encoding="utf-8")
    m = re.search(rf"^function {re.escape(name)}\(", s, re.M)
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
