"""δ 范围闸三态 `delta_scope` —— 服务端产出 + 前端渲染的双向护栏(2026-08-17)。

## 为什么要有这个字段

方案 A(联赛在 δ 覆盖外 ⇒ 不施加点估修正 + 下界改吃 `_UNCAL_SE` 地板)的代价是
**完全静默**:数字悄悄变了,没有任何东西喊。08-16 和 08-17 各因此漏了一个调用点,
两次症状都是「让球 ± 带宽 10 倍」,而**两次都是 owner 看着卡片报出来的**。

原本唯一的可观测性是 `_SCOPE_STATS` —— 进程内计数器、重启归零、全仓零生产读者,
而且它数的是**调用次数**不是场次。⇒ 它不是可观测性。
(更糟:方案文档写的验收步骤「重启后查 `suppressed_none == 0`」在**新进程**里恒为 0
 ⇒ 那步验收**永远通过**。我 08-16 就是这么"验"的。)

## 三态,不是两态

`missing` 和 `out_of_scope` 数值后果完全一样,但**成因相反**:

* `out_of_scope` = 日职/杯赛/北欧 —— δ 在那些人口上没测过。**预期形态。**
* `missing`      = 某个调用点忘了传 league。**是 bug。**

合并成一个 bool 就等于把 bug 伪装成形态 —— 而这正是两次事故都没被自动发现的原因。

## ⛔ 为什么不是「漏传直接 422」

owner 红线:**显示层降级不能 422 掉整张卡**。缓存的老 tab 会打过来。
⇒ 选「可见但不失败」。代价老实说:每个消费方多一个**必须被渲染**的字段,
漏渲染 = 又一个静默 —— 所以本文件断言前端确实画了它。
"""
from __future__ import annotations

import pathlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api.routes import router as v4_router

_HTML = pathlib.Path(__file__).resolve().parents[2] / (
    "apps/api/src/nutmeg/v4/api/static/dashboard.html")

_IN, _OUT = "ESP_LA_LIGA", "JPN_J1"

_REPRICE = {
    "psc_home": 2.34, "psc_draw": 3.03, "psc_away": 3.64,
    "psc_over25": 2.04, "psc_under25": 1.85, "ou_line": 2.25,
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _src() -> str:
    return _HTML.read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────
# 1. 服务端:三态必须真的出现,且 missing ≠ out_of_scope
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("league", "want"), [
    (_IN, "applied"),
    (_OUT, "out_of_scope"),
    (None, "missing"),
    ("", "missing"),
    ("   ", "missing"),          # 🚨 空白串:原实现只判 `== ""`,于是「传了但传的是
    ("\t", "missing"),           #    空白」被记成正常的覆盖外 —— 把漏传警报静音。
])
def test_market_reprice_reports_the_scope(league, want):
    body = dict(_REPRICE) if league is None else {**_REPRICE, "league": league}
    r = _client().post("/api/v4/recommend/market-reprice", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["delta_scope"] == want


def test_missing_and_out_of_scope_are_numerically_identical_but_distinguishable():
    """⭐ 本文件存在的理由,一条测试说完。

    两者的**数字**必须一样(都不施加 δ、都吃地板)——
    但**标签**必须不同,否则 bug 和形态分不开。
    """
    c = _client()
    miss = c.post("/api/v4/recommend/market-reprice", json=_REPRICE).json()
    oos = c.post("/api/v4/recommend/market-reprice",
                 json={**_REPRICE, "league": _OUT}).json()
    def band(d):
        x = next(v for v in d["handicap_lines"] if v["line"] == -1)
        return round(x["p_home"] - x["p_home_lo"], 12), round(x["p_home"], 12)
    assert band(miss) == band(oos), "数值应当一样 —— 不一样说明两条分支实现漂开了"
    assert miss["delta_scope"] == "missing"
    assert oos["delta_scope"] == "out_of_scope"
    assert miss["delta_scope"] != oos["delta_scope"], "🚨 两者同标签 ⇒ bug 被伪装成形态"


def test_scope_and_the_gate_come_from_one_function():
    """判闸(`_delta_in_scope`)和显示(`delta_scope`)必须同源。

    两个名字指同一个量、各算一份 —— 本仓在 WPO 去vig 上踩过(server 一份 JS 一份,
    漂了 11pp)。这里逐个联赛对账,不是读代码看长得像不像。
    """
    from nutmeg.v4.model.market_handicap import _delta_in_scope, delta_scope
    for lg in (_IN, _OUT, "英超", "MANUAL", None, "", "  ", "soccer_epl", "epl"):
        assert _delta_in_scope(lg) == (delta_scope(lg) == "applied"), lg


def test_market_handicap_reports_the_scope():
    """⚠️ 这个端点**会写台账** ⇒ 「这注的 δ 施加了没有」必须能被事后看见。"""
    c = _client()
    base = {**_REPRICE, "date": "2026-08-17", "home_team": "A", "away_team": "B",
            "handicap_home": -1, "odds_handicap_H": 2.6, "odds_handicap_D": 3.4,
            "odds_handicap_A": 2.45, "record_session": False}
    for lg, want in ((_IN, "applied"), (_OUT, "out_of_scope")):
        r = c.post("/api/v4/recommend/market-handicap", json={**base, "league": lg})
        assert r.status_code == 200, r.text
        assert r.json()["delta_scope"] == want


@pytest.mark.parametrize("ep", ["/api/v4/predictions/sp-calc",
                                "/api/v4/predictions/cup-market"])
def test_auto_boards_never_report_missing(ep):
    """🚨 **自动卡也吃这个闸。** 任何一场报 `missing` = 构造点漏填 league。

    ⭐ 这条替代了 08-16 那个恒真验收(「重启后查 `suppressed_none == 0`」——
    新进程里计数器恒为 0,永远通过)。**它问的是逐场的事实,不是进程内的计数。**
    """
    r = _client().get(ep)
    assert r.status_code == 200, r.text
    preds = (r.json() or {}).get("predictions") or []
    bad = [(p.get("home_team"), p.get("league")) for p in preds
           if p.get("delta_scope") == "missing"]
    assert not bad, f"{len(bad)} 场没带 league 到 δ 闸:{bad[:5]}"
    # ⚠️ 休赛期可能一场都没有 —— 那时本条**没有判别力**,明写而不是假装通过。
    if not preds:
        pytest.skip("盘面为空(休赛期/采集窗口)—— 本条本次无判别力")


# ────────────────────────────────────────────────────────────────
# 2. 前端:必须真的渲染,且不许自己判范围
# ────────────────────────────────────────────────────────────────

def test_frontend_renders_the_badge():
    s = _src()
    assert "function _dscopeHtml(pr)" in s
    assert "_dscopeHtml(pr)" in s.split("function _hcEvHtml")[1][:600], \
        "`_hcEvHtml` 没调 `_dscopeHtml` ⇒ 字段回来了但没人画 = 又一个静默"


def test_frontend_does_not_reimplement_the_whitelist():
    """⛔ 白名单和 `canonical_league` 都在服务端。前端只渲染回包。

    同「δ 常数不许挪进 JS」的理由:两份实现必然漂开,而漂开的那天没人会发现。
    """
    from nutmeg.v4.model.market_handicap import _DELTA_CALIBRATED_LEAGUES
    s = _src()
    m = re.search(r"function _dscopeHtml\(pr\)\s*\{.*?\n\}", s, re.S)
    assert m, "找不到 _dscopeHtml —— 本条的前提没了"
    leaked = [lg for lg in _DELTA_CALIBRATED_LEAGUES if lg in m.group(0)]
    assert not leaked, f"🚨 前端里出现了白名单联赛名 {leaked} —— 它在自己判范围"


def test_applied_draws_nothing():
    """正常态**不画** —— 80% 的卡挂同一个图标 = 噪声,最后谁都不看。稀有才有信息量。"""
    m = re.search(r"function _dscopeHtml\(pr\)\s*\{.*?\n\}", _src(), re.S)
    assert "sc === 'applied'" in m.group(0) and "return ''" in m.group(0)


def test_every_board_replacement_syncs_the_scope():
    """⭐ **分母护栏。** 每个替换 `pr.handicap_lines` 的地方都必须同步 `delta_scope`。

    不同步 ⇒ 板已按「未校准」重算、徽章还显示上一次的 `applied`
    ⇒ **徽章朝最危险的方向撒谎**(看起来正常,实际 10 倍带)。
    同步之后,徽章本身就是「这次重算漏没漏传 league」的探测器 ——
    08-17 那个 bug 会当场自曝。
    """
    s = _src()
    n_board = s.count("pr.handicap_lines = data.handicap_lines;")
    n_scope = s.count("pr.delta_scope = data.delta_scope;")
    assert n_board >= 3, f"只找到 {n_board} 处换板 —— 提取器坏了,不是代码变干净了"
    assert n_board == n_scope, (
        f"🚨 换板 {n_board} 处,同步 scope 只有 {n_scope} 处 —— "
        f"少的那处会让徽章停在旧值。")


def test_out_of_scope_marker_is_readable_text_not_a_bare_symbol():
    """⭐ 这条是 **owner 的提问**逼出来的,不是我想出来的。

    第一版用一个上标 `°` 做覆盖外标记。owner 看着带 `°` 的芬超卡**还是来问了**
    「为什么市场模式的 ± 这么高」—— 那就是它没做到工作的直接证据:
    在 ±72.4% 这么大的数字旁边,一个点看不见。

    ⇒ 标记必须是**能读出来的文字**(走 i18n),不是裸符号。
    ⚠️ 但仍必须**淡色 + 单行**:覆盖外占了盘面约 80%,做成醒目色就是满屏噪声,
       最后和 `°` 一样没人看 —— 只是换了个方式失效。
    """
    m = re.search(r"function _dscopeHtml\(pr\)\s*\{.*?\n\}", _src(), re.S)
    assert m, "找不到 _dscopeHtml"
    body = m.group(0)
    assert "t('dscope_out_tag')" in body, "覆盖外标记不是走 i18n 的文字"
    assert ">°<" not in body, "🚨 覆盖外标记退回成了裸符号 `°`"
    assert "text-muted" in body, "覆盖外标记必须是淡色 —— 它占盘面 80%"


def test_i18n_keys_in_both_locales():
    s = _src()
    for k in ("dscope_out_tag", "dscope_out_tip", "dscope_miss_tip"):
        assert s.count(k + ":") >= 2, f"i18n 键 {k!r} 缺了一个语种"


# ────────────────────────────────────────────────────────────────
# 3. 快照层:白名单必须进 provenance,scope 必须逐腿落列
# ────────────────────────────────────────────────────────────────

def test_whitelist_is_recorded_in_provenance():
    """🚨 白名单从 08-16 起是 `p_lo` 的**一等决定项**(0.0078 还是 0.078)。

    不记它,闸上线前后两批快照的 `constants_json` **逐字节相同、语义已变**,
    而这是 forward-only,补不回来。
    """
    from nutmeg.v4.observation.board_snapshot import live_constants
    v = live_constants().get("market_handicap._DELTA_CALIBRATED_LEAGUES")
    assert isinstance(v, list) and v, "白名单没进 provenance"
    assert v == sorted(v), "必须排序 —— 否则 PYTHONHASHSEED 让同一份名单写出不同 JSON"
    from nutmeg.v4.model.market_handicap import _DELTA_CALIBRATED_LEAGUES
    assert set(v) == set(_DELTA_CALIBRATED_LEAGUES)


def test_snapshot_carries_delta_scope_per_leg():
    from nutmeg.v4.observation.board_snapshot import _COLS, _legs_from_prediction
    assert "delta_scope" in _COLS
    import datetime as dt
    pred = {"home_team": "A", "away_team": "B", "league": _IN, "date": "2026-08-17",
            "delta_scope": "applied", "p_home_1x2": 0.4, "p_draw_1x2": 0.3,
            "p_away_1x2": 0.3, "handicap_lines": []}
    rows = _legs_from_prediction(pred, dt.datetime.now(dt.UTC))
    assert rows, "夹具没造出腿 —— 本条无判别力"
    assert all(r["delta_scope"] == "applied" for r in rows), \
        "腿没带上 scope ⇒ 秋季回放时「哪些腿真吃到 δ」仍得靠带宽指纹反推"
