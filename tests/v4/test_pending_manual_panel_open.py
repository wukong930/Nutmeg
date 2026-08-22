"""待开盘卡的手填 Pinnacle 面板默认展开(2026-08-22)。

## 病史

owner 问「今天 18:00 日乙 磐田喜悦 vs 德岛漩涡 为什么不在竞彩可投注列表里」。
三条链查下来:名字 ✅ 解得出、竞彩 ✅ 在售且 SP 入库、**盘面 ❌ Pinnacle 两条源
都没给价** ⇒ 落进「待开盘」区。

⭐ 而**手填入口两个月前就建好了**(`_pendPinApply` + `_pendPromote`,填完升格成真卡)。
他没找到,是因为要连穿三层:待开盘区在页面最底 → 今天 80 场 → 面板自己还是一个
**默认收起**的 `<details>`。⇒ 不是功能缺失,是可发现性。

⛔ 我在查之前已经准备动手「建」这个功能了 —— 这是本会话第二次「断言某东西不存在
之前没去看」(第一次是 `jingcai_sp_snapshots`)。

## 缺口规模(决定了「全展开会不会太长」)

2026-06-11 起竞彩上架过 602 场,**从没拿到过 Pinnacle 价的只有 15 场 = 2.5%**
(巴西杯 6/7=85.7%、日乙 2/6=33.3% 是主要来源;6月 1.0% / 7月 0.0% / 8月 4.6%)。
实测当天全页只有 **2** 张这种卡 ⇒ 默认展开不会把页面撑长。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DASH = Path(__file__).resolve().parents[2] / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _fn(name: str) -> str:
    js = DASH.read_text(encoding="utf-8")
    i = js.index(name)
    depth, j, started = 0, i, False
    while j < len(js):
        if js[j] == "{":
            depth += 1
            started = True
        elif js[j] == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:j + 1]
        elif js[j] == ";" and not started:
            return js[i:j + 1]
        j += 1
    return js[i:]


def _render(reason: str) -> str:
    """真调 `_pendingCardHtml`,返回它吐出的 HTML。⛔ 不 grep 源码。"""
    src = "\n".join(_fn(n) for n in (
        "const _PEND_JC_SELLING", "function _pendIsJcSelling", "function _pendingCardHtml"))
    body = f"""
      globalThis.t = (k) => k;
      globalThis.outcomeLabel = (o) => o;
      globalThis._expandIcons = (x) => x;
      globalThis._fmtKickoff = () => '18:00';
      globalThis.teamLogo = () => '';
      globalThis.zhTeam = (x) => x;
      const pf = {{ home_team:'Jubilo Iwata', away_team:'Tokushima Vortis',
                   league:'JPN_J2', date:'2026-08-22',
                   kickoff_utc:'2026-08-22T10:00:00+00:00',
                   jc_home:2.27, jc_draw:2.9, jc_away:2.91, jc_hc_line:-1,
                   reason: {json.dumps(reason)} }};
      console.log(_pendingCardHtml(pf, 7));"""
    r = subprocess.run(["node", "-e", src + "\n" + body],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-1500:]
    return r.stdout


def _selling_reason() -> str:
    src = _fn("const _PEND_JC_SELLING")
    return json.loads(src.split("=", 1)[1].strip().rstrip(";").replace("'", '"'))


# ── 承重 ────────────────────────────────────────────────────

def test_the_manual_panel_is_open_by_default() -> None:
    """⭐ 本次改动的全部要点:竞彩在售的待开盘卡,手填面板**一眼可见**。

    断言渲染结果里 `<details>` 带 `open`,而不是源码里出现 'open' 那个词
    (后者会被注释里的任何一个 open 命中 —— 本会话已经栽过一次:
    断言匹配到了我自己写在改动里的注释)。
    """
    html = _render(_selling_reason())
    i = html.index("<details")
    tag = html[i:html.index(">", i) + 1]
    assert " open" in tag, f"手填面板仍然默认收起:{tag}"
    assert 'id="pendman-7"' in tag, f"抓到的不是手填面板那个 details:{tag}"


def test_the_apply_button_is_reachable_without_a_click() -> None:
    """行为断言:面板展开 ⇒ 「应用」按钮和三个赔率输入框都在同一份 HTML 里,
    不需要先展开任何东西。这才是 owner 那个问题的直接答案。"""
    html = _render(_selling_reason())
    for k in ("h", "d", "a"):
        assert f'id="pendman-{k}-7"' in html, f"缺输入框 pendman-{k}-7"
    assert 'onclick="_pendPinApply(7)"' in html, "缺「应用」按钮"


def test_ordinary_pending_cards_get_no_panel_at_all() -> None:
    """⛔ 反向承重:竞彩**没**在卖的待开盘卡,一个输入框都不该有。

    这条防的是「为了让 owner 看见,把面板加到所有 80 张卡上」——
    那会把待开盘区变成一堵墙,而且给不能买的场造出一个可以下注的错觉。
    """
    html = _render("no_odds_yet")
    assert "<details" not in html and "pendman-" not in html, "普通待开盘卡长出了手填面板"
