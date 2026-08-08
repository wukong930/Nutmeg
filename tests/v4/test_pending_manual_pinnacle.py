"""竞彩在售、Pinnacle 缺席的场次 → 手填后回到「💴 竞彩可投注」(2026-08-08 · v150)。

起因:日乙(JPN_J2)两条 Pinnacle 源都不存在 —— Odds API 全表 175 个 sport 只有 J1
(`/sports?all=true` live 核过);API-Football 对 J2 逐场返回**零家博彩**,含 7 天后的
未来场(fixture 1606606 live refresh),排除了「临场才发」。⇒ 它**永远**等不到自动开盘,
而竞彩确实在卖 ⇒ 手填是唯一的路。

守的东西:
① 判据是「**竞彩在不在卖**」,不是「是不是日乙」—— 不给某个联赛写特例
② 待开盘那 10 场里竞彩只卖 2 场 —— 给 10 场都开入口 = 8 张永远算不出 EV 的空卡
③ **没手填过就不许升格** —— `_cupCardHtml` 对 `p_*_1x2 = null` 会印「公允 0.0%」,
   一个长得像真测量值的假数字(「绝不编造 +EV」的显示层版本)
④ 幂等 —— 同一场升格两次 = 页面上两张卡,第二张收得下键盘却永不响应,
   且 📌 会把**另一张**的赔率发出去(`test_bettable_first_dashboard.py:164` 是实测事故)
⑤ 升格出来的卡必须带 `odds_source='manual'` —— 台账靠它区分手打线与自动线
⑥ `_attach_jingcai_sp` 喂 pending 时不许把端点打成 500
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
_SELLING = "jingcai_selling_no_pinnacle"


def _fn(name: str) -> str:
    s = DASH.read_text(encoding="utf-8")
    m = re.search(rf"^(?:async )?function {re.escape(name)}\(", s, re.M)
    assert m, f"{name} 不在 dashboard.html 里"
    i, depth = m.start(), 0
    j = s.index("{", i)
    for k in range(j, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if not depth:
                return s[i:k + 1]
    raise AssertionError(f"{name} 花括号没配平")


def _pf(home: str, away: str, day: str, *, selling: bool, ko: str | None = None) -> dict:
    """一条待开盘行(服务端 `PendingFixture` 的 JSON 形状)。"""
    row = {"home_team": home, "away_team": away, "league": "JPN_J2", "date": day,
           "kickoff_utc": ko or f"{day}T10:00:00+00:00",
           "reason": _SELLING if selling else "pinnacle_not_open",
           "jc_home": None, "jc_draw": None, "jc_away": None, "jc_source": None,
           "jc_hc_home": None, "jc_hc_draw": None, "jc_hc_away": None, "jc_hc_line": None,
           "jc_captured_at": None,
           "jc_single_available": None, "jc_hc_single_available": None}
    if selling:
        row.update(jc_home=2.32, jc_draw=3.25, jc_away=2.56, jc_source="sporttery",
                   jc_hc_home=5.26, jc_hc_draw=4.00, jc_hc_away=1.45, jc_hc_line=-1,
                   jc_single_available=0, jc_hc_single_available=0)
    return row


def _run_promote(pending: list[dict], store: dict) -> dict:
    """跑**生产源码**的 `_pendPromote`,返回升格结果 + 幂等复跑结果。"""
    stub = f"""
      const _PEND_JC_SELLING = {json.dumps(_SELLING)};
      function _cupManKey(pr) {{
        return (pr.home_team||'') + '|' + (pr.away_team||'') + '|' + (pr.date||'');
      }}
      function _cupManStore() {{ return {json.dumps(store)}; }}
    """
    code = (stub + _fn("_pendIsJcSelling") + _fn("_pendPromote")
            + f"\nconst pending = {json.dumps(pending)}; const preds = [];"
            "\nconst first = _pendPromote(preds, pending);"
            "\nconst again = _pendPromote(preds, pending);"
            "\nconsole.log(JSON.stringify({first, again, preds}));")
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[:1500]
    return json.loads(r.stdout)


_FILLED = {"h": 2.55, "d": 3.30, "a": 2.80, "line": 2.5, "o": None, "u": None, "ts": 1,
           "P": [0.3747, 0.2856, 0.3397],
           "lo": [0.3631, 0.2744, 0.3285],
           "hc": [{"line": -1, "p_home": 0.13, "p_draw": 0.24, "p_away": 0.63}]}


def test_only_matches_jingcai_is_actually_selling_get_promoted() -> None:
    """⭐ 判据是「竞彩在不在卖」,**不是**「在不在待开盘区」。

    实测(2026-08-08):面板待开盘的 10 场日乙来自 API-Football 的**赛程**,
    而竞彩官方盘面(两份独立快照,均在当天所有日乙开赛前)只卖其中 **2 场**。
    给 10 场都开手填入口 = 8 张永远算不出 EV 的空卡。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    skip = _pf("Iwaki", "Imabari", "2026-08-09", selling=False)
    key = "Montedio Yamagata|Tochigi City|2026-08-09"
    out = _run_promote([sell, skip], {key: _FILLED,
                                      "Iwaki|Imabari|2026-08-09": _FILLED})
    assert len(out["first"]) == 1, "竞彩没卖的那场也被升格了"
    assert out["first"][0]["home_team"] == "Montedio Yamagata"


def test_a_match_never_hand_filled_stays_in_pending() -> None:
    """⛔ 没手填过 ⇒ 不许升格。

    升格一张 `p_*_1x2` 为空的卡,`_cupCardHtml` 会渲染出「公允 0.0% · @0.00」
    (实测:`null` 印 0.0%,`undefined` 印 NaN%)—— 前者最坏,它长得像一个真的
    测量值。这是「绝不编造 +EV」红线的显示层版本。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    out = _run_promote([sell], {})            # localStorage 空 = 从没填过
    assert out["first"] == [], "没手填过就升格了 —— 会印出假的「公允 0.0%」"
    assert out["preds"] == []


def test_promoting_twice_does_not_create_a_second_card() -> None:
    """⭐ 幂等。`renderCupMarket` 会被 60s 轮询 / 手填 / 🔄 / 🎯 反复调用。

    同一场两张卡是**实测过的事故**(`test_bettable_first_dashboard.py:164`):
    第二张收得下键盘却永远没反应,而且 📌 记一笔会把**另一张卡**的赔率 POST 出去。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    key = "Montedio Yamagata|Tochigi City|2026-08-09"
    out = _run_promote([sell], {key: _FILLED})
    assert len(out["first"]) == 1
    assert out["again"] == [], "第二次调用又升格了一遍 —— 页面上会出现两张卡"
    assert len(out["preds"]) == 1


def test_the_promoted_card_is_tagged_as_a_hand_typed_line() -> None:
    """⭐ 台账靠 `odds_source` 区分「自动抓的 Pinnacle」和「owner 手打的」。

    前端凭空构造的对象若不显式写,送出去是 `undefined` ⇒ 库里 NULL ⇒
    诚实但丢标记。而这条线是**唯一**能事后分辨这注 P 从哪来的信息
    (`single_predictions` / `parlay_recommendations` 两张表都没有这一列,
    只能 join 回 `recommendation_sessions.odds_source`)。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    key = "Montedio Yamagata|Tochigi City|2026-08-09"
    pr = _run_promote([sell], {key: _FILLED})["preds"][0]
    assert pr["odds_source"] == "manual"
    assert pr["market_mode"] is True
    assert pr["_manual"] is True
    # 竞彩侧原样带过来 —— 少任何一个,`_isJcBettable` 就判不出可投注
    assert (pr["jc_home"], pr["jc_draw"], pr["jc_away"]) == (2.32, 3.25, 2.56)
    assert pr["jc_hc_line"] == -1
    # 玩法级单关标记必须跟过来:这 2 场都是 0(竞彩只让串关,不开单关)
    assert pr["jc_single_available"] == 0
    # 手填线**天生没有**的东西留空是诚实的,别凭空造
    assert pr["asian_handicap_lines"] == [] and pr["margin_bands"] == []
    assert pr["sharp_flip"] is False, "没有模型就没有「模型 vs sharp 分歧」"


def test_the_promoted_card_carries_the_1x2_lower_bounds() -> None:
    """⭐ 承重:升格出来的卡必须带 `onex_lo_*`。

    缺了 ⇒ `_boardLegs` 的 `lo ?? p` 回落成 `evLo ≡ ev`,1X2 腿**零收缩**,
    而同卡让球腿照吃 `p_*_lo` ⇒ 两类腿在同一个 evLo 排序里抢 argmax ——
    v149 刚消灭的不对称在**日乙唯一的那条路上**复活。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    key = "Montedio Yamagata|Tochigi City|2026-08-09"
    pr = _run_promote([sell], {key: _FILLED})["preds"][0]
    for lo, p in ((pr["onex_lo_home"], pr["p_home_1x2"]),
                  (pr["onex_lo_draw"], pr["p_draw_1x2"]),
                  (pr["onex_lo_away"], pr["p_away_1x2"])):
        assert lo is not None, "升格的卡没带 1X2 下界 —— 前端会退回 evLo≡ev"
        assert lo < p


def test_a_legacy_store_entry_without_bounds_still_promotes() -> None:
    """向后兼容:2026-08-08 之前存的手填记录没有 `lo`。

    此时下界为 null(`_boardLegs` 回落 evLo≡ev),由紧接着的
    `_cupManRefreshDerived` 一个来回补齐 —— 但**卡不能因此不出现**,
    否则 owner 会看到自己填过的场次凭空消失。
    """
    sell = _pf("Montedio Yamagata", "Tochigi City", "2026-08-09", selling=True)
    key = "Montedio Yamagata|Tochigi City|2026-08-09"
    legacy = {k: v for k, v in _FILLED.items() if k != "lo"}
    pr = _run_promote([sell], {key: legacy})["preds"][0]
    assert pr["onex_lo_home"] is None
    assert pr["p_home_1x2"] == pytest.approx(0.3747), "点估还是要贴回来"


def test_attaching_jingcai_sp_to_pending_does_not_500() -> None:
    """🚨 `PendingFixture` 是 pydantic v2 model,未声明的属性赋值抛 ValueError;
    而 `_attach_jingcai_sp` 的 try **只包到 lookup**,写回循环原来是裸的
    ⇒ 先加调用后加字段 = 第一场命中就把 `/predictions/cup-market` 打成 HTTP 500。

    这条守两件事:字段声明齐了,且写回循环兜住了异常。
    """
    from nutmeg.v4.api.routes import _attach_jingcai_sp
    from nutmeg.v4.api.schemas import PendingFixture

    pf = PendingFixture(home_team="Montedio Yamagata", away_team="Tochigi City",
                        league="JPN_J2", date=dt.date(2026, 8, 9))
    for f in ("jc_home", "jc_hc_line", "jc_captured_at", "jc_single_available"):
        assert f in PendingFixture.model_fields, f"PendingFixture 少了 {f}"
    _attach_jingcai_sp([pf])       # 无观测库时静默 no-op;有则挂上。都不许抛

    # 写回循环必须兜住:喂一个**不接受**赋值的对象,不能炸穿出来
    class _Frozen:
        date = dt.date(2026, 8, 9)
        home_team = "A"
        away_team = "B"

        def __setattr__(self, k, v):
            raise ValueError("frozen")

    _attach_jingcai_sp([_Frozen()])   # 抛出来就是回归


def test_reason_distinguishes_waiting_from_never_coming() -> None:
    """⭐「等上游开盘」和「上游永远不会有」是两件事,别合并成一个「待开盘」。

    `pinnacle_not_open` 之前是个**只有一个取值**的装饰字段(两个构造点都不传,
    唯一消费者是一条测试)。现在它承重:前端靠它决定给不给手填入口。
    """
    from nutmeg.v4.api.schemas import PendingFixture

    assert PendingFixture.model_fields["reason"].default == "pinnacle_not_open"
    body = _fn("_pendIsJcSelling")
    assert "_PEND_JC_SELLING" in body, "前端判据没走那个常量 —— 两边会漂"
    src = DASH.read_text(encoding="utf-8")
    assert f"const _PEND_JC_SELLING = '{_SELLING}'" in src, (
        "前端常量与服务端 reason 取值对不上 —— 手填入口会一个都不出现")
