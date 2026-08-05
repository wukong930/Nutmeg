"""标准模式的 ✏️ 手填实时 Pinnacle(owner 2026-08-05,D 项)。

市场模式 V14 就有这个控件,标准模式一直没有。v131 把 `_pinRawHtml` 搬上标准卡
之后,它的水位警告 tooltip 里那句「下面的 ✏️ 手填实时 Pinnacle 可以用真盘口重算」
在这张卡上**指着一个不存在的控件** —— 先有的假承诺,这次是兑现。

## ⭐ 本文件真正守的那条线:标准模式手填**不许**改 1X2 的 P

两个模式的手填语义不同:
  市场模式 —— 1X2 的 P **就是** Pinnacle 去vig ⇒ 手填改一切,包括 p_*_1x2。
  标准模式 —— 1X2 的 P 是**模型**的 ⇒ 手填只重算让球(服务端本来就是 Pinnacle
              市场反推)+「市场 %」对照列 + 原盘行/水位闸。

把模型 P 换成去vig P,等于这张卡静默变成市场模式,而**卡面上看不出来**:P 那列
只是数字变了,没有任何标记说「你现在读的不是模型」。这正是
[[two-modes-coverage-and-p-source]] 里 "never auto-pick the rosier one" 的反面。

顺带收口一个**潜伏** bug:`_cupApplyStoredManual` 一直写着
`pr.p_home_1x2 = m.P[0]`,而 loadSpCalc 从 2026-07-30 起就在调它。它没出过事
只是因为标准模式**没有手填控件** ⇒ localStorage 里不可能有受训联赛的记录
(两块板的联赛集由 `_SP_CALC_LEAGUES` / `_CUP_MARKET_COMPETITIONS` 互补切开)。
控件一加,这条路当场可达:一次页面刷新就把模型 P 换成市场 P。

## 断言方式

一律**真跑 JS**,不 grep 源码。本会话已经栽过六次「子串存在 ≠ 行为成立」
(见 [[syntactic-proxy-for-semantic-property]]):变异把代码挪进死变量、把
判据写死、桩把被测的东西替换掉 —— 每一次源码里的字符串都还在,测试照样绿。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

#: market-reprice 的返回(去vig P + 让球盘)。P 与下面 `_PR` 的模型 P 刻意**不同**,
#: 否则「有没有被覆盖」根本测不出来 —— 夹具必须能区分两种结局。
_REPRICE = {
    "p_home_1x2": 0.55, "p_draw_1x2": 0.25, "p_away_1x2": 0.20,
    "handicap_lines": [{"line": -1, "p_home": 0.33, "p_draw": 0.22, "p_away": 0.45}],
    "overround": 0.031,
}
#: 一张标准模式卡的最小 pr:模型 P(≠ _REPRICE 的)+ 旧 Pinnacle 线 + 旧让球盘。
_PR = {
    "home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-08-15",
    "p_home_1x2": 0.41, "p_draw_1x2": 0.27, "p_away_1x2": 0.32,
    "psc_home": 2.10, "psc_draw": 3.40, "psc_away": 3.60,
    "psc_over25": 1.90, "psc_under25": 1.95, "ou_line": 2.5,
    "handicap_lines": [{"line": 0, "p_home": 0.41, "p_draw": 0.27, "p_away": 0.32}],
    "odds_update": "2026-08-15T06:00:00Z", "odds_source": "api_football",
}
#: 用户敲进 ✏️ 面板的新盘口(每个值都和 `_PR` 里的不同)。
_TYPED = {"h": 1.95, "d": 3.55, "a": 4.10, "line": 3.0, "o": 1.75, "u": 2.10}


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """按**配对括号**抠出一个顶层函数(含 `async function`)。

    ⚠️ 不用正则贪婪匹配 —— 上一个文件里 `.*?` 一口吞掉 74k 字符,于是「有没有
    渲染 X」全部假阳性。范围抠错的断言比没有断言更坏。
    """
    js = _js()
    m = re.search(rf"\n(async )?function {re.escape(name)}\(", js)
    assert m, f"找不到函数 {name}"
    start = m.start() + 1
    j = js.index("{", m.end())
    depth = 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                out = js[start:j + 1]
                assert out.rstrip().endswith("}"), name
                return out
        j += 1
    raise AssertionError(f"{name} 括号不配对")


def _node(src: str) -> dict:
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _run_spcalc_apply(pr: dict, typed: dict = _TYPED) -> dict:
    """真跑 `_spcalcManualReprice(0)`。

    桩只打在**边界**上(fetch / DOM / 存储 / 重渲),被测的那件事 —— 哪些 pr
    字段被写 —— 一律走真实代码。
    """
    inputs = {f"spman-{k}-0": v for k, v in
              {"h": typed["h"], "d": typed["d"], "a": typed["a"],
               "line": typed["line"], "o": typed["o"], "u": typed["u"]}.items()}
    harness = f"""
const t = k => k;
const API = '';
let saved = null, rerendered = 0;
function _cupManSave(pr, m) {{ saved = m; }}
function _spcalcRerender() {{ rerendered += 1; }}
const _inputs = {json.dumps(inputs)};
const document = {{ getElementById: (id) =>
  (id in _inputs ? {{ value: String(_inputs[id]), style: {{}} }} : null) }};
const fetch = async () => ({{ ok: true, json: async () => ({json.dumps(_REPRICE)}) }});
const _SPCALC = {{ preds: [{json.dumps(pr)}] }};
{_fn('_spcalcManualReprice')}
_spcalcManualReprice(0).then(() => console.log(JSON.stringify(
  {{ pr: _SPCALC.preds[0], saved, rerendered }})));
"""
    return _node(harness)


def _run_cup_apply(pr: dict) -> dict:
    """同样的输入喂**市场模式**的手填 —— 对照组。

    只测一边「没写 P」证不了什么:也可能是这条路整个没跑通。两边并排跑,同一份
    输入给出两种结局,差异才是被测的属性。
    """
    inputs = {f"cupman-{k}-0": v for k, v in
              {"h": _TYPED["h"], "d": _TYPED["d"], "a": _TYPED["a"],
               "line": _TYPED["line"], "o": _TYPED["o"], "u": _TYPED["u"]}.items()}
    harness = f"""
const t = k => k;
const API = '';
function _cupManSave() {{}}
function renderCupMarket() {{}}
const _inputs = {json.dumps(inputs)};
const document = {{ getElementById: (id) =>
  (id in _inputs ? {{ value: String(_inputs[id]), style: {{}} }} : null) }};
const fetch = async () => ({{ ok: true, json: async () => ({json.dumps(_REPRICE)}) }});
const _CUPMKT = {{ preds: [{json.dumps(pr)}], pending: [] }};
{_fn('_cupManualReprice')}
_cupManualReprice(0).then(() => console.log(JSON.stringify({{ pr: _CUPMKT.preds[0] }})));
"""
    return _node(harness)


def _run_stored_apply(keep_model_p: bool) -> dict:
    """真跑 `_cupApplyStoredManual`,`_cupManRefreshDerived` 打桩记参。"""
    stored = {"Arsenal|Chelsea|2026-08-15": {
        "h": _TYPED["h"], "d": _TYPED["d"], "a": _TYPED["a"],
        "line": _TYPED["line"], "o": _TYPED["o"], "u": _TYPED["u"], "ts": 1,
        "P": [_REPRICE["p_home_1x2"], _REPRICE["p_draw_1x2"], _REPRICE["p_away_1x2"]],
        "hc": _REPRICE["handicap_lines"]}}
    harness = f"""
let fwd = null;
function _cupManStore() {{ return {json.dumps(stored)}; }}
function _cupManKey(pr) {{ return pr.home_team + '|' + pr.away_team + '|' + pr.date; }}
function _cupManRefreshDerived(pairs, rerender, keepModelP) {{
  fwd = {{ n: pairs.length, keepModelP: keepModelP === true }};
}}
const preds = [{json.dumps(_PR)}];
{_fn('_cupApplyStoredManual')}
_cupApplyStoredManual(preds, null, {str(keep_model_p).lower()});
console.log(JSON.stringify({{ pr: preds[0], fwd }}));
"""
    return _node(harness)


def _run_refresh_derived(keep_model_p: bool) -> dict:
    """真跑 `_cupManRefreshDerived`,fetch/存储打桩。"""
    m = {"h": _TYPED["h"], "d": _TYPED["d"], "a": _TYPED["a"],
         "line": _TYPED["line"], "o": _TYPED["o"], "u": _TYPED["u"], "ts": 1}
    pr = dict(_PR, _manual=True)
    harness = f"""
const API = '';
let saved = null, rerendered = 0;
function _cupManSave(pr, mm) {{ saved = mm; }}
const fetch = async () => ({{ ok: true, json: async () => ({json.dumps(_REPRICE)}) }});
const pr = {json.dumps(pr)};
{_fn('_cupManRefreshDerived')}
_cupManRefreshDerived([[pr, {json.dumps(m)}]], () => {{ rerendered += 1; }},
                      {str(keep_model_p).lower()})
  .then(() => console.log(JSON.stringify({{ pr, saved, rerendered }})));
"""
    return _node(harness)


class TestManualDoesNotOverwriteTheModelP:
    """⭐ 本次改动的全部风险都在这一个类里。"""

    def test_handicap_and_pinnacle_echo_are_repriced(self):
        """先证这条路**真的跑通了** —— 否则「P 没变」可能只是什么都没发生。"""
        out = _run_spcalc_apply(_PR)
        pr = out["pr"]
        assert pr["handicap_lines"] == _REPRICE["handicap_lines"], "让球盘没被重算"
        assert (pr["psc_home"], pr["psc_draw"], pr["psc_away"]) == (
            _TYPED["h"], _TYPED["d"], _TYPED["a"]), "Pinnacle 原盘没换成手填值"
        assert (pr["psc_over25"], pr["psc_under25"], pr["ou_line"]) == (
            _TYPED["o"], _TYPED["u"], _TYPED["line"]), "大小球没换成手填值"
        assert pr["_manual"] is True and pr["odds_source"] == "manual"
        assert pr["odds_update"] is None, "手填后还挂着自动线的时间戳 = 年龄标会撒谎"
        assert out["rerendered"] == 1, "没重渲 ⇒ 卡面还是旧数字"

    def test_the_model_1x2_p_survives_untouched(self):
        """⭐ 这条红了 = 标准模式卡静默变成了市场模式卡。"""
        pr = _run_spcalc_apply(_PR)["pr"]
        assert (pr["p_home_1x2"], pr["p_draw_1x2"], pr["p_away_1x2"]) == (
            _PR["p_home_1x2"], _PR["p_draw_1x2"], _PR["p_away_1x2"]), (
            "标准模式手填改掉了 1X2 的 P —— 那是模型的,不是 Pinnacle 去vig 的")

    def test_market_mode_by_contrast_does_replace_it(self):
        """对照组:同一份输入,市场模式**应该**换 P(它的 P 本来就是去vig)。

        没有这一条,上面那条测的可能只是「这段代码根本没跑」。
        """
        pr = _run_cup_apply(_PR)["pr"]
        assert (pr["p_home_1x2"], pr["p_draw_1x2"], pr["p_away_1x2"]) == (
            _REPRICE["p_home_1x2"], _REPRICE["p_draw_1x2"], _REPRICE["p_away_1x2"]), (
            "市场模式没把 P 换成手填去vig —— 那才是它的正确行为")

    def test_the_stored_record_still_carries_the_devig_p(self):
        """存的记录是**板无关**的:同一场比赛哪天出现在市场模式板上,那边要用 P。
        用不用由**读的一方**决定(keepModelP),不该由写的一方阉割数据。"""
        saved = _run_spcalc_apply(_PR)["saved"]
        assert saved["P"] == [_REPRICE["p_home_1x2"], _REPRICE["p_draw_1x2"],
                              _REPRICE["p_away_1x2"]], "记录里没存去vig P"
        assert saved["hc"] == _REPRICE["handicap_lines"]
        assert (saved["h"], saved["d"], saved["a"]) == (
            _TYPED["h"], _TYPED["d"], _TYPED["a"]), "记录里没存用户敲的输入"

    def test_revert_snapshot_is_taken_before_the_write(self):
        """↩︎ 复原要回到**手填前**的自动线,不是手填后的值。"""
        pr = _run_spcalc_apply(_PR)["pr"]
        snap = pr["_apiSnapshot"]
        assert snap["psc_home"] == _PR["psc_home"], "快照里是手填后的值 ⇒ ↩︎ 复原不回去"
        assert snap["odds_source"] == "api_football", "快照没存出处 ⇒ 撤销后台账仍记 manual"
        assert snap["handicap_lines"] == _PR["handicap_lines"]


class TestStoredManualRestoreIsModeAware:
    """潜伏 bug:贴回路径也会写 p_*_1x2。控件一加它就可达。"""

    def test_spcalc_restore_keeps_the_model_p(self):
        pr = _run_stored_apply(True)["pr"]
        assert pr["p_home_1x2"] == _PR["p_home_1x2"], (
            "刷新一次就把标准卡的模型 P 换成了 Pinnacle 去vig")
        assert pr["handicap_lines"] == _REPRICE["handicap_lines"], "让球盘该贴回来"
        assert pr["psc_home"] == _TYPED["h"] and pr["_manual"] is True
        assert pr["odds_source"] == "manual", "贴回的是手填价,台账不能记成 api_football"

    def test_cup_restore_still_replaces_it(self):
        pr = _run_stored_apply(False)["pr"]
        assert pr["p_home_1x2"] == _REPRICE["p_home_1x2"], (
            "市场模式贴回没换 P —— 默认(不传第三参)必须保持旧行为")

    def test_the_flag_reaches_the_background_refit(self):
        """贴回只是第一步:后台 `_cupManRefreshDerived` 会拿存的输入再算一次并
        **再写一次** p_*_1x2。旗子漏在这一步 = 前脚守住后脚放进来。"""
        assert _run_stored_apply(True)["fwd"] == {"n": 1, "keepModelP": True}
        assert _run_stored_apply(False)["fwd"] == {"n": 1, "keepModelP": False}

    def test_background_refit_honours_the_flag(self):
        keep = _run_refresh_derived(True)
        drop = _run_refresh_derived(False)
        assert keep["pr"]["p_home_1x2"] == _PR["p_home_1x2"], "后台重算把模型 P 覆盖了"
        assert drop["pr"]["p_home_1x2"] == _REPRICE["p_home_1x2"], "市场模式行为变了"
        for out in (keep, drop):
            assert out["pr"]["handicap_lines"] == _REPRICE["handicap_lines"]
            assert out["rerendered"] == 1
            assert out["saved"]["P"] == [
                _REPRICE["p_home_1x2"], _REPRICE["p_draw_1x2"], _REPRICE["p_away_1x2"]], (
                "keepModelP 时连存都不存 P ⇒ 这条记录以后在市场模式板上贴不出 P")

    def test_loadspcalc_passes_the_flag(self):
        """调用点。这三个函数守得再好,调用方不传 true 也白搭。"""
        js = _js()
        i = js.index("async function loadSpCalc(")
        body = js[i:js.index("\n}", i)]
        assert re.search(r"_cupApplyStoredManual\(\s*body\.predictions\s*,\s*_spRerender\s*,"
                         r"\s*true\s*\)", body), "loadSpCalc 没传 keepModelP=true"


#: 面板 2026-08-06 起把提示文案收进 `<details>`,summary 里带一个 `IC('info')` 图标。
#: 本文件测的是 **id 前缀**和**预填值**,图标只需存在;不桩掉它整个 harness 会 ReferenceError。
_IC_STUB = "const IC=n=>'<i data-ic=\\''+n+'\\'></i>';"


class TestPanelIsWiredIntoTheCard:
    def test_card_renders_the_panel(self):
        js = _js()
        i = js.index("const cardHtml = (pr, idx) => {")
        depth, j, started = 0, i, False
        while j < len(js):
            if js[j] == "{":
                depth += 1
                started = True
            elif js[j] == "}":
                depth -= 1
                if started and depth == 0:
                    break
            j += 1
        assert "_spcalcManualHtml(pr, idx)" in js[i:j + 1], "标准模式卡没挂 ✏️ 面板"

    def test_panel_ids_cannot_collide_with_the_market_card(self):
        """⚠️ 两块板在**同一个 tab** 上下叠着,各自用自己的 board-global idx ⇒
        直接复用 `cupman-h-0` 会让 `getElementById` 撞到另一块板的输入框,
        安静地拿错值重算另一张卡。"""
        out = subprocess.run(
            ["node", "-e", f"const t=k=>k;const outcomeLabel=o=>o;{_IC_STUB}"
                           f"{_fn('_spcalcManualHtml')}"
                           f"console.log(_spcalcManualHtml({json.dumps(_PR)}, 0));"],
            capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        ids = re.findall(r'id="([^"]+)"', out.stdout)
        assert ids, "面板一个 id 都没有"
        assert all(i.startswith("spman-") for i in ids), ids
        assert "cupman-" not in out.stdout, "标准模式面板用了市场模式的 id 前缀"

    def test_panel_prefills_from_the_cards_current_line(self):
        out = subprocess.run(
            ["node", "-e", f"const t=k=>k;const outcomeLabel=o=>o;{_IC_STUB}"
                           f"{_fn('_spcalcManualHtml')}"
                           f"console.log(_spcalcManualHtml({json.dumps(_PR)}, 0));"],
            capture_output=True, text=True, timeout=30)
        for want in ("2.1", "3.4", "3.6", "1.9", "1.95", "2.5"):
            assert f'value="{want}"' in out.stdout, f"预填缺 {want}\n{out.stdout}"

    def test_rerender_keeps_the_pending_section(self):
        """`_spcalcRerender` 必须把 `_pendingByBoard.spcalc` 传回去 —— 传 `[]`
        的话,每按一次「应用」下方「待开盘」里本板那批就被抹掉一次。"""
        got = _node(f"""
let args = null;
function renderTodaySpCalc(...a) {{ args = a; }}
const _pendingByBoard = {{ spcalc: ['MINE'], cupmkt: ['THEIRS'] }};
const _SPCALC = {{ preds: ['P'], bankroll: 777, kelly: 0.25, minEv: 0.05 }};
{_fn('_spcalcRerender')}
_spcalcRerender();
console.log(JSON.stringify(args));
""")
        assert got[0] == ["P"] and got[1] == 777
        assert got[4] == ["MINE"], f"待开盘传错了:{got[4]!r}"


class TestCopy:
    """文案也是承诺。v131 之后 `pin_wide_hint` 就在标准卡上指着一个不存在的控件。"""

    def test_spman_hint_exists_in_both_locales(self):
        hits = re.findall(r"spman_hint:\s*'((?:[^'\\]|\\.)*)'", _js())
        assert len(hits) == 2, f"中英双语没齐(找到 {len(hits)} 条)"

    def test_spman_hint_says_the_1x2_p_does_not_move(self):
        """用户会预期手填改一切 —— 不说清楚,他会以为 1X2 的 EV 已经跟着更新了。"""
        hits = re.findall(r"spman_hint:\s*'((?:[^'\\]|\\.)*)'", _js())
        zh = next(h for h in hits if "模型" in h)
        en = next(h for h in hits if "model" in h.lower())
        assert "让球" in zh and "模型" in zh, zh
        assert "handicap" in en.lower() and "model" in en.lower(), en

    def test_no_string_still_claims_the_spcalc_card_has_no_such_control(self):
        js = _js()
        for stale in ("SP 计算器卡没有这个控件",
                      "the SP-calculator card has no such control",
                      "本页和「今日推荐」没有这个控件",
                      "This page and the Today board have no such control"):
            assert stale not in js, f"文案仍说标准模式没有手填控件:{stale!r}"
