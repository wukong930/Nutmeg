"""⭐ 最优腿徽章 —— 行为断言(2026-09-03)。

## 为什么非要有这个文件

owner 说「我读判断计算结果的能力不行」。真因不是他,是**屏幕上印的数不是判闸的数**:
腿行印**点估** `ev`,绿灯由**下界** `evLo` 决定。当天真实盘面 8 张有腿的卡,
**6/8 = 75%** 两者指向不同的腿。徽章要修的就是这个。

⇒ 于是徽章有三条**只要错一条就变成误导**的性质,全部在这里钉死:

1. 它跟的是**下界**排序(= `_boardLegs`,和串关池同源),不是点估;
2. 它印出来的那个数**就是判闸那个数**,不是点估;
3. 它**必须带过闸状态** —— 当天 0/8 过闸,不带状态就等于给 8 场发了 8 个推荐,
   把「最不差」读成「推荐」。这是本改动唯一真正危险的失败模式。

## 这里怎么写才不是语法代理

抠生产函数原文在 node 里真跑(harness 抄 `test_gate_p_source_behavioral.py`),
喂一份**故意让点估最优腿 ≠ 下界最优腿**的 fixture,断言**徽章文本里出现的腿名和数字**。
⛔ 不 grep 源码里有没有 `_boardLegs` 这串字符 —— 那种断言换个等价写法就失效。

🚨 `_bestLegRefresh` 整体包着 `try/catch`(显示层不许拖垮主 EV 计算),
   ⇒ **harness 里任何异常都会被静默吞掉,测试全绿而一行都没跑到**。
   所以每条断言之前先断言「徽章确实被写过」(`_ASSERT_RAN`),
   否则这整个文件就是一堆空洞为真的断言。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _fn(name: str) -> str:
    """抠出生产函数原文(花括号配平)—— 不重写一份,重写就测不到真代码。"""
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\n(async )?function {re.escape(name)}\s*\(", js)
    assert m, f"找不到 {name} —— 它被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)


def _const(name: str) -> str:
    """把 `const _X = <字面量>;` **原文**取过来 —— ⛔ 不在测试里照抄一个门槛数字。"""
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"^const {re.escape(name)} = [0-9.]+;", js, re.M)
    assert m, f"找不到常数 {name} —— 本 harness 失效"
    return m.group(0)


#: 一场**故意让两种排序打架**的比赛(数字取得夸张,好让「用错了哪个」一眼可见):
#:
#:   腿        点估 p   下界 lo   SP     点估 EV    下界 EV
#:   胜(H)     0.50    0.49    2.20    +10.0%    **+7.8%**   ← 下界最优
#:   -1让胜    0.60    0.45    2.00   **+20.0%**   −10.0%    ← 点估最优
#:
#: ⇒ 徽章若说「-1让胜」或印出 20.0%,就是滑回点估了。
_PR = {
    "p_home_market": 0.50, "p_draw_market": 0.25, "p_away_market": 0.25,
    "onex_lo_home": 0.49, "onex_lo_draw": 0.24, "onex_lo_away": 0.24,
    "jc_home": 2.20, "jc_draw": 3.50, "jc_away": 3.60,
    "jc_hc_line": -1, "jc_hc_home": 2.00, "jc_hc_draw": 3.30, "jc_hc_away": 3.80,
    "handicap_lines": [{
        "line": -1,
        "p_home": 0.60, "p_draw": 0.25, "p_away": 0.15,
        "p_home_lo": 0.45, "p_draw_lo": 0.20, "p_away_lo": 0.12,
    }],
}

#: 市场模式的 `p_*_1x2` **本身就是** Pinnacle 去vig(服务端不下发 `p_*_market`)。
_PR_CUP = {**_PR, "p_home_1x2": 0.50, "p_draw_1x2": 0.25, "p_away_1x2": 0.25}


def _run(mode: str, pr: dict, *, sp_override: dict | None = None,
         min_ev: float | None = None, second_pr: dict | None = None,
         hcline_value: int | None = None) -> dict:
    """在 node 里真跑 `_bestLegRefresh`,回收徽章文本 + ⭐ 落在哪一行。

    ⭐ `_sweetEffSp` 用**生产原文**(不是桩):它就是「手填 SP → 重算」那条真路径,
    而 owner 的需求原话是「最优腿能够根据最新计算结果变化而变化」。桩掉它,
    这条需求就一行都没测到。

    `second_pr` 不为空时跑**两遍**(中间换盘),用来验 ⭐ 搬家后不留幽灵。
    """
    hc = "cuphcsp" if mode == "cup" else "spcalc-hcsp"
    one = "cupsp" if mode == "cup" else "spcalc-sp"
    src = f"""
const _created = [], _roots = {{}}, _inputs = {json.dumps(sp_override or {})};
function mkEl(id) {{
  const e = {{ id: id, title: '', textContent: '', innerHTML: '', value: '',
    style: {{ cssText: '', display: '' }}, _kids: [], _parent: null,
    insertBefore(n, ref) {{
      if (n._parent) n._parent._kids = n._parent._kids.filter(x => x !== n);
      n._parent = this;
      const i = ref ? this._kids.indexOf(ref) : -1;
      if (i >= 0) this._kids.splice(i, 0, n); else this._kids.unshift(n);
      return n;
    }},
    remove() {{ if (this._parent) this._parent._kids =
      this._parent._kids.filter(x => x !== this); this._parent = null; }},
  }};
  Object.defineProperty(e, 'firstChild', {{ get() {{ return this._kids[0] || null; }} }});
  return e;
}}
const R = (id) => (_roots[id] = _roots[id] || mkEl(id));
// 预建:徽章行 + 六个 EV 格(两套寻址各三个)
R('bestleg-{mode}-0');
['H','D','A'].forEach(o => {{ R('spcalc-ev-0-'+o); R('spcalc-hcev-0-'+o);
                             R('cupev-0-'+o); R('cuphcev-0-'+o); }});
const document = {{
  createElement: (tag) => {{ const e = mkEl(''); _created.push(e); return e; }},
  getElementById: (id) => {{
    const k = String(id);
    if (_roots[k]) return _roots[k];
    // 让球线选择器。⚠️ `_boardLegs` 里有个 `onSale` 闸:**只有当展示的线 == 竞彩
    // 在售线时,手填的让球 SP 才生效**(看的不是在售线,就不该把竞彩 SP 套上去)。
    // 早先这里返回 null ⇒ onSale 恒 false ⇒ 手填那条路径被 harness 自己关掉了,
    // 于是「手填后 ⭐ 换腿」这条测试红得像 bug,其实是**桩的前提错了**。
    if (k.includes('hcline')) {{
      const store = k.indexOf('cuphcline') === 0 ? _CUPMKT : _SPCALC;
      const cur = (store.preds || [])[0] || {{}};
      // 默认「展示的线 == 在售线」(onSale=true)。测试可用 hcline_value 拨开,
      // 才能真正踩到 onSale 那条分支 —— 靠改 jc_hc_line 是拨不开的:那样
      // `handicap_lines.find` 直接落空,让球腿整段不进池,测试**空洞通过**。
      const forced = {json.dumps(hcline_value)};
      if (forced != null) return {{ value: String(forced) }};
      return cur.jc_hc_line != null ? {{ value: String(cur.jc_hc_line) }} : null;
    }}
    const n = _created.find(x => x.id === k && x._parent);
    return n || null;
  }},
  querySelector: (sel) => {{
    const s = String(sel);
    const m = s.match(/^\\.([\\w-]+)\\[data-idx="(\\d+)"\\]\\[data-outcome="([HDA])"\\]$/);
    // ⛔ 认不出的选择器**直接炸**,绝不 return null —— 生产代码碰到 null 会静悄悄
    //    走空分支,而测试全绿(假绿)。见 test_gate_p_source_behavioral 同款处理。
    if (!m) throw new Error('harness 不认识的选择器: ' + s);
    const cls = m[1], o = m[3];
    if (cls === 'cupev' || cls === 'cuphcev') return R(cls + '-0-' + o);
    const e = R('input-' + cls + '-' + o);
    e.value = (_inputs[cls + ':' + o] != null) ? String(_inputs[cls + ':' + o]) : '';
    return e;
  }},
}};
const t = (k) => k;                        // 断言直接打 i18n key,和文案解耦
const _evRelTier = () => 'sweet';          // 把 tier 这个变量控住,让六条腿全进池
const _frzHalfEv = () => 0;                // 冻结带按定义不判闸
const _hcLineLabel = () => '-1', _hcOutcomeLabel = (o) => 'HC' + o;
const showInfo = () => {{}};
let _SPCALC = {{ preds: [{json.dumps(pr)}], minEv: {json.dumps(min_ev)} }};
let _CUPMKT = {{ preds: [{json.dumps(pr)}] }};
{_const('_TODAY_REC_GATE')}
{_fn('_sweetEffSp')}
{_fn('_mktP')}
{_fn('_hcLineP')}
{_fn('_boardLegs')}
{_fn('_bestLegGate')}
{_fn('_bestLegEvEl')}
{_fn('_bestLegRefresh')}
_bestLegRefresh(0, {json.dumps(mode)});
const SECOND = {json.dumps(second_pr)};
if (SECOND) {{ _SPCALC.preds[0] = SECOND; _CUPMKT.preds[0] = SECOND;
               _bestLegRefresh(0, {json.dumps(mode)}); }}
const badge = _roots['bestleg-{mode}-0'];
const spans = Object.keys(_roots).filter(k => k.includes('ev-0-'));
const starAt = spans.filter(k => _roots[k]._kids.some(c => c.id.startsWith('beststar-')));
console.log(JSON.stringify({{
  badge: badge.innerHTML, display: badge.style.display,
  starAt: starAt,
  starTotal: spans.reduce((n, k) =>
    n + _roots[k]._kids.filter(c => c.id.startsWith('beststar-')).length, 0),
}}));
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2500]
    out = json.loads(r.stdout)
    return out


def _assert_ran(out: dict) -> None:
    """🚨 防空洞:`_bestLegRefresh` 整体 try/catch,harness 出错会被**静默吞掉**。

    没有这一条,下面每一条 `assert 'x' not in badge` 都空洞为真。
    """
    assert out["badge"], f"徽章是空的 —— 说明 _bestLegRefresh 中途抛了(被 try 吞掉):{out}"
    assert out["display"] != "none", f"徽章被隐藏了:{out}"


class TestBadgeFollowsTheGatingNumber:
    """承重①② —— 徽章跟的是**下界**,印的也是**下界**。"""

    def test_names_the_lower_bound_winner_not_the_point_estimate_winner(self):
        """⭐ 最承重的一条。

        fixture 里点估最优是 **-1让胜(+20.0%)**、下界最优是 **胜(+7.8%)**。
        徽章若说让球腿,就是滑回点估排序了 —— 而实测 75% 的卡两者不同,
        这一滑就等于把系统自己不认的那条腿推给 owner。
        """
        out = _run("spcalc", _PR)
        _assert_ran(out)
        assert "sw_1x2_h" in out["badge"], f"徽章没点名「胜」:{out['badge']}"
        assert "HC" not in out["badge"], f"徽章点名了让球腿 = 按点估排序了:{out['badge']}"
        assert out["starAt"] == ["spcalc-ev-0-H"], f"⭐ 落错行:{out['starAt']}"

    def test_prints_the_lower_bound_value_not_the_point_estimate(self):
        """承重②:印出来的数必须是 **+7.8%**(判闸值),不是 **+10.0%**(点估)。

        少了这一条,徽章看起来会像在和屏幕上的数字打架,而 owner 无从分辨
        「它算错了」还是「它用的是另一把尺」。
        """
        out = _run("spcalc", _PR)
        _assert_ran(out)
        assert "+7.8%" in out["badge"], f"没印判闸值:{out['badge']}"
        assert "+10.0%" not in out["badge"], f"印的是点估:{out['badge']}"
        assert "+20.0%" not in out["badge"], f"印的是让球点估:{out['badge']}"


class TestBadgeAlwaysCarriesGateState:
    """🚨 承重③ —— 本改动**唯一真正危险**的失败模式。

    当天真实盘面 **0/8 过闸**。徽章不带过闸状态 ⇒ 八张卡看起来就是八条推荐,
    「最不差」被读成「该下这一注」。这比不做这个功能更坏。
    """

    def test_below_gate_says_below_gate_and_never_says_pass(self):
        """evLo=+7.8% ≥ 门槛 5% 会过闸 ⇒ 把门槛抬到 10% 制造未过闸。"""
        out = _run("spcalc", _PR, min_ev=0.10)
        _assert_ran(out)
        assert "best_leg_fail" in out["badge"], f"未过闸却没说:{out['badge']}"
        assert "best_leg_pass" not in out["badge"], f"未过闸却说过闸:{out['badge']}"

    def test_above_gate_says_pass(self):
        out = _run("spcalc", _PR, min_ev=0.05)
        _assert_ran(out)
        assert "best_leg_pass" in out["badge"], f"过闸却没说:{out['badge']}"
        assert "best_leg_fail" not in out["badge"], out["badge"]

    def test_gate_is_taken_per_mode_not_hardcoded(self):
        """⚠️ 标准模式门槛可调(`_SPCALC.minEv`),市场模式固定(`_TODAY_REC_GATE`)。

        写死一个会造出「徽章说过闸、同一张卡的行却是红的」—— 两把尺子并排。
        这里把 `_SPCALC.minEv` 抬到 10%:标准模式必须翻成未过闸,
        市场模式**必须不受影响**(它根本不该读那个字段)。
        """
        sp = _run("spcalc", _PR, min_ev=0.10)
        cup = _run("cup", _PR_CUP, min_ev=0.10)
        _assert_ran(sp); _assert_ran(cup)
        assert "best_leg_fail" in sp["badge"], sp["badge"]
        assert "best_leg_pass" in cup["badge"], \
            f"市场模式跟着 _SPCALC.minEv 走了 = 门槛写串了:{cup['badge']}"


class TestBadgeTracksLatestNumbers:
    """owner 的原话:「最优腿能够**根据最新计算结果变化而变化**」。"""

    def test_manual_sp_entry_moves_the_star(self):
        """手填让球 SP 2.00 → 2.60:让球腿 evLo = 0.45×2.60−1 = **+17.0%**,
        超过 1X2 的 +7.8% ⇒ 徽章和 ⭐ 都必须换到让球腿。

        ⭐ 这条走的是**生产 `_sweetEffSp` 原文**,不是桩 —— 它就是手填那条真路径。
        """
        base = _run("spcalc", _PR)
        moved = _run("spcalc", _PR, sp_override={"spcalc-hcsp:H": 2.60})
        _assert_ran(base); _assert_ran(moved)
        assert base["starAt"] == ["spcalc-ev-0-H"], base["starAt"]
        assert moved["starAt"] == ["spcalc-hcev-0-H"], \
            f"手填后 ⭐ 没跟着换腿(_sweetEffSp 那条路径断了):{moved}"
        assert "+17.0%" in moved["badge"], moved["badge"]

    def test_exactly_one_star_after_the_winner_changes(self):
        """⭐ 换腿后**不许留幽灵**:屏幕上出现两个「最优腿」是最难自查的错。

        实现上 ⭐ 是每卡唯一一个带 id 的节点、靠 `insertBefore` 搬家(搬家自带
        从旧父节点摘除)⇒ 结构上不可能有两颗。这条钉住那个结构。
        """
        hc_wins = {**_PR, "handicap_lines": [{**_PR["handicap_lines"][0], "p_home_lo": 0.60}]}
        out = _run("spcalc", _PR, second_pr=hc_wins)
        _assert_ran(out)
        assert out["starTotal"] == 1, f"换腿后 ⭐ 数量 = {out['starTotal']}(幽灵):{out}"
        assert out["starAt"] == ["spcalc-hcev-0-H"], out["starAt"]

    def test_no_legs_hides_the_badge_instead_of_showing_a_stale_one(self):
        """⛔ 没有市场 P ⇒ 1X2 腿整条不进池(生产规则),也没让球线 ⇒ 池空。

        池空时徽章必须**隐藏**,不是留着上一次的内容。
        """
        empty = {k: v for k, v in _PR.items()
                 if k not in ("handicap_lines", "jc_hc_line")}
        empty.update(p_home_market=None, p_draw_market=None, p_away_market=None)
        out = _run("spcalc", empty)
        assert out["display"] == "none", f"池空却仍显示徽章:{out}"
        assert out["starTotal"] == 0, f"池空却留着 ⭐:{out}"

    def test_manual_hc_sp_is_ignored_when_a_different_line_is_displayed(self):
        """⚠️ 生产语义:展示的让球线 ≠ 竞彩在售线时,手填的让球 SP **不该**生效。

        看的不是在售那条线,把竞彩 SP 套上去就是拿 A 线的赔率配 B 线的概率。
        这条钉住 `_boardLegs` 里的 `onSale` 闸 —— 它一旦被「简化」掉,
        徽章会在错误的线上算出一个很好看的 evLo。
        """
        # ⚠️ 早先这条写成 `jc_hc_line=-2`,那是**空洞通过**:`handicap_lines` 里
        #    没有 -2 ⇒ `find` 落空 ⇒ 让球腿整段不进池,`onSale` 一次都没跑到。
        #    空包弹(拆掉 onSale)因此没被抓住。真正要拨的是**下拉框显示的线**。
        out = _run("spcalc", _PR, sp_override={"spcalc-hcsp:H": 2.60}, hcline_value=-2)
        _assert_ran(out)
        assert "+17.0%" not in out["badge"], \
            f"非在售线上套用了手填 SP:{out['badge']}"
        assert out["starAt"] == ["spcalc-ev-0-H"], out["starAt"]

    def test_cup_mode_star_lands_on_the_class_addressed_row(self):
        """🚨 市场模式的 EV 格**没有 id,只有 class**(`.cupev` / `.cuphcev`)。

        我第一版把两种模式都当成 id 寻址 —— 那样 `_bestLegEvEl` 在市场模式恒返回
        null,⭐ **静默不出现**(徽章行照常显示,所以肉眼看不出少了什么)。
        没有这条,那个 bug 可以一直绿着。
        """
        out = _run("cup", _PR_CUP)
        _assert_ran(out)
        assert out["starAt"] == ["cupev-0-H"], f"市场模式 ⭐ 没落到腿行:{out}"
        assert out["starTotal"] == 1, out


class TestWiringPopulationIsComplete:
    """⭐ 人口**自己发现**,不写死名单(写死的名单会掉队,已四次)。"""

    def _src(self) -> str:
        return DASH.read_text(encoding="utf-8")

    def test_every_declared_mode_is_fully_wired(self):
        js = self._src()
        m = re.search(r"const _BEST_LEG_MODES = \[([^\]]+)\];", js)
        assert m, "找不到 _BEST_LEG_MODES —— 人口发现器失效"
        modes = re.findall(r"'([a-z]+)'", m.group(1))
        # 🚨 人口非平凡断言:漏了它,下面的 for 循环空转也能全绿
        assert len(modes) >= 2, f"模式人口退化到 {modes} —— 断言变空洞"
        for mode in modes:
            assert f'id="bestleg-{mode}-${{idx}}"' in js, f"{mode} 卡片模板里没有徽章行"
            assert f"_bestLegRefresh(idx, '{mode}')" in js, f"{mode} 没有任何刷新调用点"

    def test_both_recalc_families_refresh_the_badge(self):
        """1X2 段和让球段是**两个独立的 recalc**,只挂一边 ⇒ 改让球 SP 徽章不动。"""
        js = self._src()
        for fn in ("_spcalcRecalc", "_spcalcHcRecalc", "_cupRecalc", "_cupHcRecalc"):
            body = _fn(fn)
            assert "_bestLegRefresh(" in body, f"{fn} 没有刷新徽章 —— 那一段改了 SP 徽章会陈"

    def test_i18n_keys_exist_in_both_dictionaries(self):
        """徽章文案缺一条,`t()` 会静默回落成 key,屏幕上出现 `best_leg_fail` 这种字样。"""
        js = self._src()
        keys = ["best_leg_label", "best_leg_gate", "best_leg_pass",
                "best_leg_fail", "best_leg_info_t", "best_leg_info_b"]
        for k in keys:
            n = len(re.findall(rf"^    {k}:", js, re.M))
            assert n == 2, f"{k} 在 i18n 里出现 {n} 次(应为中英各一)"
