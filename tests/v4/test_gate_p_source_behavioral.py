"""判闸用的 P **到底是哪个数** —— 行为断言,不是语法断言(2026-08-07 P0-1/P0-2)。

## 为什么非要有这个文件

2026-08-06 的钱路审查做了变异检验(在隔离 worktree 里),结论是这两条判闸线**完全裸奔**:

* 把两个让球面的 `evLo = PB.lo[o] * sp - 1` 改成 `P[o] * sp - 1`(下界→点估,闸变松)
  ⇒ 全量 **3,182 个测试零新增红**。
* 号称守它的 `test_gate_pick_kelly_do_not_see_freeze_band` 只断言比较行上的**变量名**
  (`"const pass = evLo >= minEv;"`),没有任何东西把 `evLo` 绑回 `PB.lo` ——
  **语法代理测语义属性**,本项目最贵的失败模式。

而 2026-08-06 当天,一个审查 agent 的变异**真的**把 `_cupHcRecalc` 那行改成了点估、
撞额度死在还原之前,线上跑了 50 分钟松闸。**没有任何测试红过。**

同一次审查还查出 `d2b3950`(判闸改用市场 P)只落到比赛卡一处:甜区榜、腿行绿灯、
排序键、串关构造器、「1串参考」、今日推荐 📌、记账落库 —— 七个面还在用模型 P。
实测线上 84 条 1X2 腿里 **81 条**存在「榜说过闸、同页卡片说不过闸」的 SP 窗口,
**46/84 是榜更绿**(方向不保守)。

## 这里怎么写才不是语法代理

把生产函数**原文抠出来在 node 里真跑**,喂**故意让点估和下界分开**的 fixture,
断言**输出的 EV 数值**。改坏任何一处取 P 的地方,这里的数值就对不上 ⇒ 红。
不 grep 源码里有没有 `PB.lo` 这串字符 —— 那种断言换个等价写法就失效,
而真改坏了反而可能不红。
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
    """抠出生产函数原文(带花括号配平),不重写一份 —— 重写就测不到真代码。"""
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


def _consts(*names: str) -> str:
    """把生产源码里那几行 `const _X = <字面量>;` **原文**取过来。

    ⛔ 不在测试里照抄一个数 —— 那样测试和生产各拿一个门槛,
       门槛改了测试照样绿(2026-08-07 那次 `_TODAY_REC_GATE` 就是这么处理的)。
    """
    js = DASH.read_text(encoding="utf-8")
    out = []
    for n in names:
        m = re.search(rf"^const {re.escape(n)} = [0-9.]+;", js, re.M)
        assert m, f"找不到常数 {n} —— 它被改名或删了,本 harness 失效"
        out.append(m.group(0))
    return "\n".join(out)


def _node(src: str) -> dict:
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2500]
    return json.loads(r.stdout)


#: 一场**故意让三个 P 两两分开**的比赛:
#:   模型 P(主) 0.70  ≫  市场 P(主) 0.50   ⇒ 用错就差 20pp
#:   让球点估 0.60     ≫  让球下界 0.45     ⇒ 用错就差 15pp
#: 数字取得夸张是有意的 —— 让「用错了哪个」在输出里一眼可见,而不是差 0.3pp 靠眼力。
_PR = {
    "p_home_1x2": 0.70, "p_draw_1x2": 0.20, "p_away_1x2": 0.10,
    "p_home_market": 0.50, "p_draw_market": 0.25, "p_away_market": 0.25,
    "jc_home": 2.00, "jc_draw": 3.50, "jc_away": 6.00,
    "jc_hc_line": -1, "jc_hc_home": 2.00, "jc_hc_draw": 3.30, "jc_hc_away": 3.80,
    "handicap_lines": [{
        "line": -1,
        "p_home": 0.60, "p_draw": 0.25, "p_away": 0.15,
        "p_home_lo": 0.45, "p_draw_lo": 0.20, "p_away_lo": 0.12,
    }],
}


class TestBoardUsesMarketP:
    """P0-1 —— 甜区榜/串关构造器共用的 `_boardLegs`,1X2 腿必须用市场 P。"""

    def _legs(self, mode: str, pr: dict) -> list:
        return _node(f"""
const t = (k) => k;
const _evRelTier = () => 'sweet';                 // 让所有腿都进榜,把 tier 这个变量控住
const _frzHalfEv = () => 0;                       // 冻结带按定义不判闸,置 0 便于读数
const _sweetEffSp = (mode, idx, mkt, o, fb) => fb; // SP 直接用预填,不走 DOM
const _hcLineLabel = () => 'L', _hcOutcomeLabel = (o) => o;
const document = {{ getElementById: () => null }};  // 让球那段的 onSale 走 false 分支
{_fn('_mktP')}
{_fn('_hcLineP')}
{_fn('_boardLegs')}
console.log(JSON.stringify(_boardLegs({json.dumps(pr)}, 0, {json.dumps(mode)})));
""")

    def test_standard_mode_1x2_uses_market_p_not_model_p(self):
        """⭐ 承重条。市场 P=0.50 × SP=2.00 − 1 = **0.00**;
        若回到模型 P=0.70 则是 **+0.40** —— 差 40pp,不可能看错。

        这条红 = 甜区榜/腿行绿灯/排序键/串关构造器/「1串参考」又滑回模型 P 了。
        """
        h = [x for x in self._legs("spcalc", _PR) if x["o"] == "H"]
        assert h, "主胜腿没进榜 —— 市场 P 齐全时不该被跳过"
        assert h[0]["ev"] == pytest.approx(0.00, abs=1e-9), \
            f"主胜 EV={h[0]['ev']:.4f};+0.40 = 用了模型 P"

    def test_cup_mode_keeps_p_1x2_because_that_IS_the_market_p(self):
        """⚠️ 市场模式的 `p_*_1x2` **本身就是** Pinnacle 去vig(服务端不下发 `p_*_market`)。

        所以那边保持原样才是同源 —— 一刀切改成 `_mktP` 会把整个市场模式的榜清空。
        这条钉住「按模式取」这个结构,防止有人「统一一下」。
        """
        pr = {**_PR, "p_home_market": None, "p_draw_market": None, "p_away_market": None}
        h = [x for x in self._legs("cup", pr) if x["o"] == "H"]
        assert h, "市场模式主胜腿不该消失"
        assert h[0]["ev"] == pytest.approx(0.40, abs=1e-9), h[0]["ev"]

    def test_missing_market_p_drops_the_leg_instead_of_falling_back(self):
        """⛔ 没有市场 P ⇒ 整条 1X2 腿**不进榜**,绝不回退模型 P。

        回退 = 把刚移出判闸的东西从后门放回来,而且是静默的。
        让球腿不受影响 —— 它有自己的 P,不依赖 1X2。
        """
        pr = {**_PR, "p_home_market": None, "p_draw_market": None, "p_away_market": None}
        legs = self._legs("spcalc", pr)
        assert not [x for x in legs if x["o"] in ("H", "D", "A")], \
            f"缺市场 P 时 1X2 腿仍进榜(疑似回退模型 P):{legs}"
        assert [x for x in legs if x["o"].startswith("hc")], "让球腿被误伤"


class TestHandicapGateUsesLowerBound:
    """P0-2 —— 两个让球判闸面必须用 δ **下界**,不是点估。"""

    def _gate(self, fn: str, pr: dict) -> dict:
        """真跑判闸函数,回收它写进 DOM 的 verdict/EV。

        harness 里每一个名字要么是 `_fn()` 抠来的生产原文,要么是**纯显示**的桩。
        分界线只有一条:返回值会不会流进 `evLo` / `pass` / 注额。会 ⇒ 抠真的。
        """
        pfx = "cuphc" if "cup" in fn.lower() else "spcalc-hc"
        return _node(f"""
const _out = {{ ev: {{}}, green: [], verdict: null }};
const _mk = (id) => ({{ _id: id, textContent: '', innerHTML: '', className: '',
  style: {{ cssText: '', color: '', fontWeight: '' }}, removeAttribute() {{}} }});
const _els = {{}};
const _PRED = {json.dumps(pr)};
// 让球线选择器:无论走 `$` 还是 `getElementById` 都得给出选中的线,否则被测函数
// 在「还没选线」分支就 return 了 —— 那样测试会**假绿**(什么都没跑到)。
const _get = (id) => {{
  const k = String(id);
  if (k.includes('hcline')) return {{ value: '-1' }};
  return _els[k] || (_els[k] = _mk(k));
}};
const $ = (s) => _get(String(s).replace('#', ''));
const document = {{
  getElementById: _get,
  querySelector: (sel) => {{
    const s = String(sel);
    const m = s.match(/^\\.([\\w-]+)\\[data-idx="(\\d+)"\\]\\[data-outcome="([HDA])"\\]$/);
    // 认不出的选择器**直接炸**,绝不 return null:生产代码对 null 的反应是
    // `if (!inp || !evSpan) return;` —— 判闸一行没跑,而测试全绿(假绿)。
    if (!m) throw new Error('harness 不认识的选择器: ' + s);
    const cls = m[1], o = m[3], key = cls + '-' + m[2] + '-' + o;
    // 同一个选择器每次必须拿到**同一个**对象,否则生产代码写下的 innerHTML/颜色
    // 落在临时对象上,收不回来 —— 又是一种假绿。
    const el = _els[key] || (_els[key] = _mk(key));
    // `.spcalc-hcsp` / `.cuphcsp` = 竞彩 SP 输入框;`.cuphcev` = 市场模式让球行的
    // EV 格(那一格没有 id,只能按 class 选)。两者必须分开:都当成输入框的话,
    // EV 格永远进不了 `_els`,判闸结果就无从观测。
    if (cls.endsWith('sp')) el.value = String(_PRED['jc_hc_' + {{H:'home',D:'draw',A:'away'}}[o]]);
    return el;
  }},
}};
const t = (k) => k, _hcOutcomeLabel = (o) => o, fmtMoney = (x) => 'CNY' + Number(x).toFixed(2);
const _frzBandHtml = () => '', _frzHalfEv = () => 0, _evRelTag = () => '';
const _isWideBook = () => false, _jcStaleCaptureHc = () => {{}};
const _sweetBoardScheduleRefresh = () => {{}}, _parlayRender = undefined;
// `_bestLegRefresh` 桩 —— ⭐ 最优腿徽章(2026-09-03)。按本 harness 自己的分界线:
// 它无返回值、只写徽章那一格,**不流进 evLo / pass / 注额** ⇒ 纯显示,可以桩。
const _bestLegRefresh = () => {{}};
// `_hcEvHtml` 桩 —— 读过源码才敢桩:它把入参拼成一段 HTML 就 return,没有任何
// 返回值回流到 evLo / pass / 注额(frzHalf、_evRelTag、± 带全部只影响这一格长什么样)
// ⇒ 纯显示,可以桩。桩**只印下界**(判闸真正用的那个数),不印点估:真函数印的是
// 点估,而本 fixture 的点估 EV 恰好 = +20.0%,照搬会让「输出里不许有 20.0%」永远红。
// 这样「输出里出现 20.0%」⇔「evLo 取到了点估」—— 正是那条断言要抓的东西。
const _hcEvHtml = (ev, evLo) => 'EV≥' + (evLo >= 0 ? '+' : '') + (evLo * 100).toFixed(1) + '%';
const _CUPMKT = {{ preds: [_PRED], minEv: 0.05, bankroll: 10000, kelly: 0.25 }};
const _SPCALC = _CUPMKT;
// `_TODAY_REC_GATE` 是 const 不是 function,`_fn()` 抠不到 —— 但市场模式的
// `pass = evLo >= _TODAY_REC_GATE` 直接吃它。照抄一个 0.05 进来 = 测试和生产各拿
// 一个门槛,所以把生产源码那一行原文取过来。
{re.search(r'^const _TODAY_REC_GATE = [0-9.]+;', DASH.read_text(encoding='utf-8'), re.M).group(0)}
{_fn('_hcLineP')}
{_fn('_spcalcHcPB' if 'spcalc' in fn else '_cupHcPB')}
{_fn('_spcalcStake')}
{_fn(fn)}
{fn}(0);
['H','D','A'].forEach((o) => {{
  const e = _els['{pfx}ev-0-' + o];
  if (!e) return;
  _out.ev[o] = e.innerHTML;
  // 判闸结果在两个面长成同一对副作用:pass 分支把这一格涂绿 + 加粗。这两个字面量
  // 抄自生产 pass 分支;万一配色改了,读不到绿 —— 那时反向那条会红(它就是为了防
  // 「什么都不过闸」的假绿而存在的)。
  if (e.style.color === '#059669' && e.style.fontWeight === '600') _out.green.push(o);
}});
const v = _els['{pfx}verdict-0'];
_out.verdict = v ? v.textContent : null;
// 市场模式的让球行**没有结论行**(`_cupHcRecalc` 从不写 verdict),判闸只以上面那格的
// 绿+粗出现 ⇒ 归一成标准盘同一个 token,四条断言才能对两个面用同一套词。
if (!_out.verdict && _out.green.length)
  _out.verdict = t('spcalc_pick') + ': ' + _out.green.join(',');
console.log(JSON.stringify(_out));
""")

    @pytest.mark.parametrize("fn", ["_spcalcHcRecalc", "_cupHcRecalc"])
    def test_gate_reads_the_lower_bound_not_the_point_estimate(self, fn):
        """⭐ 承重条。下界 0.45 × SP 2.00 − 1 = **−10.0%** ⇒ 不过闸;
        点估 0.60 × 2.00 − 1 = **+20.0%** ⇒ 会过闸。

        这条红 = 有人把 `PB.lo[o]` 换成了 `P[o]`,闸变松。
        2026-08-06 线上真发生过这件事,当时 3,182 个测试一个没红。
        """
        out = self._gate(fn, _PR)
        blob = json.dumps(out, ensure_ascii=False)
        assert "spcalc_pick" not in blob, (
            f"{fn} 让下界 −10% 的腿过闸了 ⇒ 判闸疑似改用点估。输出:{blob[:400]}")
        assert "20.0%" not in blob, f"{fn} 输出里出现点估 EV(+20.0%):{blob[:400]}"

    @pytest.mark.parametrize("fn", ["_spcalcHcRecalc", "_cupHcRecalc"])
    def test_a_leg_whose_lower_bound_clears_the_gate_still_passes(self, fn):
        """反向 —— 别把闸焊死。下界 0.60 × 2.00 − 1 = +20% ⇒ **应该**过。

        没有这条,上一条可能只是「什么都不过闸」。
        """
        pr = {**_PR}
        pr["handicap_lines"] = [{**_PR["handicap_lines"][0], "p_home_lo": 0.60, "p_home": 0.75}]
        out = self._gate(fn, pr)
        assert "spcalc_pick" in json.dumps(out, ensure_ascii=False), \
            f"{fn} 下界 +20% 的腿没过闸 —— 闸被焊死了?{json.dumps(out, ensure_ascii=False)[:400]}"


# ─────────────────────────────────────────────────────────────────────────────
# 1X2 判闸的第三次收口(2026-08-16)—— 上面那两条盯的是**让球**面,
# 这一节盯 **1X2** 面。改之前它有**三个**互不相同的口径:
#     甜区榜  `_boardLegs`     → `onex_lo_*`(下界)      ✅
#     卡片·标准 `_spcalcRecalc` → `p_*_market`(点估)     ❌ 更宽松
#     卡片·市场 `_cupRecalc`    → `p_*_1x2`(点估)        ❌ 更宽松
# 实测差(2026-08-16 在售 28 场 × 3 腿):**中位 3.49pp、最大 11.42pp**,
# 而 +5% 闸的分辨率就在这个量级 ⇒ 同一条腿榜上不绿、点进卡片却绿。
#
# ⭐ 统一的时机是**今天 0 条腿会变**(39 条可判腿两口径下都不过闸):
#    零行为变化时改口径,而不是等某天它真的放行一条不该放的腿。
# ─────────────────────────────────────────────────────────────────────────────

class TestOnexLoPIsTheSingleGateSource:
    """`_onexLoP` 是三处 1X2 判闸的**唯一** P 源。抠真函数用 node 跑。"""

    def _call(self, pr: dict, point=None) -> dict:
        src = _fn("_onexLoP") + f"""
const pr = {json.dumps(pr)};
const point = {json.dumps(point)};
console.log(JSON.stringify({{ out: _onexLoP(pr, point) }}));
"""
        return _node(src)["out"]

    def test_returns_the_lower_bound_not_any_point_estimate(self) -> None:
        """基本形:三腿下界原样返回(不传点估时不钳位)。"""
        out = self._call({"onex_lo_home": 0.30, "onex_lo_draw": 0.25, "onex_lo_away": 0.40})
        assert out == {"H": 0.30, "D": 0.25, "A": 0.40}

    def test_clamps_a_lower_bound_that_exceeds_the_point_estimate(self) -> None:
        """🚨 承重条:下界**永远不许大于点估**。

        手填把 P 调低超过 k·SE ⇒ 旧下界反超新点估 ⇒ **下界变上界、判闸反而变松**。
        这条红 = 钳位没了,而它的失效方向是「越不可信越容易变绿」。
        """
        out = self._call(
            {"onex_lo_home": 0.55, "onex_lo_draw": 0.25, "onex_lo_away": 0.40},
            {"H": 0.30, "D": 0.25, "A": 0.40})   # 点估 H 比下界低
        assert out["H"] == 0.30, f"下界 0.55 没被钳到点估 0.30:{out}"
        assert out["D"] == 0.25 and out["A"] == 0.40, out

    def test_missing_lower_bound_returns_null_so_the_gate_cannot_fire(self) -> None:
        """⛔ 缺下界 ⇒ **null ⇒ 不判闸**,而不是回退到点估。

        回退等于把刚移出判闸的东西从后门放回来,而且是静默的
        —— 这正是 `d2b3950` 那次「改完全系统口径统一」外推失败的形状。
        """
        assert self._call({"onex_lo_home": 0.30, "onex_lo_draw": 0.25}) is None
        assert self._call({}) is None
        # 🚨 空包弹补的:**同时传点估**时也必须 null。
        #    2026-08-16 变异 `if (!ok) return pointP || null;` 一开始**没被抓住**,
        #    因为原用例都没传点估 ⇒ `pointP || null` 恰好也是 null。
        #    ⇒ 「缺下界」的用例必须把最诱人的回退目标摆在桌上。
        assert self._call({"onex_lo_home": 0.30}, {"H": 0.9, "D": 0.9, "A": 0.9}) is None
        assert self._call({}, {"H": 0.9, "D": 0.9, "A": 0.9}) is None
        assert self._call({"onex_lo_home": 0, "onex_lo_draw": 0.25,
                           "onex_lo_away": 0.40}) is None      # 0 不是合法 P
        assert self._call({"onex_lo_home": 1.0, "onex_lo_draw": 0.25,
                           "onex_lo_away": 0.40}) is None      # 1.0 也不是

    def test_market_mode_shape_still_works(self) -> None:
        """市场模式:`p_*_market` 为 null、点估在 `p_*_1x2`,但下界照样在。

        ⚠️ 这是三处能统一的**原因** —— 两种模式的 `onex_lo_*` 都是
        **市场 P** 的下界(服务端 `routes.py` 三处都是 `_onex_lo(fair)`
        紧跟同一次 `_pinnacle_devig_1x2`)。
        """
        out = self._call(
            {"p_home_market": None, "p_draw_market": None, "p_away_market": None,
             "onex_lo_home": 0.5479, "onex_lo_draw": 0.25, "onex_lo_away": 0.20},
            {"H": 0.5595, "D": 0.25, "A": 0.20})   # 点估来自 p_*_1x2
        assert out["H"] == 0.5479, out


class TestOneX2CardGatesReadTheLowerBound:
    """🚨 **判闸点**本身,不只是 helper。

    2026-08-16 空包弹发现:只测 `_onexLoP` 抓不到「把判闸行改回点估」——
    而那正是 2026-08-06 线上**真发生过**的变异(当时 3,182 个测试一个没红)。
    ⇒ 这一节真跑 `_spcalcRecalc` / `_cupRecalc`,断言它们写进 DOM 的绿灯。

    夹具刻意造成「点估过闸、下界不过」:
        点估 0.60 × SP 2.00 − 1 = **+20%** ⇒ 若判闸用点估就会变绿
        下界 0.45 × SP 2.00 − 1 = **−10%** ⇒ 正确行为是不绿
    """

    _PR_1X2 = {
        "p_home_1x2": 0.60, "p_draw_1x2": 0.25, "p_away_1x2": 0.15,
        "p_home_market": 0.60, "p_draw_market": 0.25, "p_away_market": 0.15,
        "onex_lo_home": 0.45, "onex_lo_draw": 0.20, "onex_lo_away": 0.10,
        "jc_home": 2.00, "jc_draw": 2.00, "jc_away": 2.00,
    }

    def _run(self, fn: str, pr: dict) -> dict:
        # ⚠️ 不按函数名分支选择器 —— harness 的 querySelector 是**通配**的
        #    (按 class 名后缀 'sp' 判输入框),两个面共用同一套。
        return _node(f"""
const _out = {{ green: [] }};
const _mk = (id) => ({{ _id: id, textContent: '', innerHTML: '', className: '',
  value: '', style: {{ color: '', fontWeight: '' }}, removeAttribute() {{}},
  setAttribute() {{}} }});
const _els = {{}};
const _PRED = {json.dumps(pr)};
const _KEY = {{ H: 'home', D: 'draw', A: 'away' }};
const _get = (id) => _els[String(id)] || (_els[String(id)] = _mk(String(id)));
const $ = (s) => _get(String(s).replace('#', ''));
const document = {{
  getElementById: _get,
  querySelector: (sel) => {{
    const s = String(sel);
    const m = s.match(/^\.([\w-]+)\[data-idx="(\d+)"\]\[data-outcome="([HDA])"\]$/);
    // ⛔ 认不出的选择器直接炸,绝不 return null —— 生产代码对 null 的反应是
    //    `if (!inp) return;`,判闸一行没跑而测试全绿(假绿)。
    if (!m) throw new Error('harness 不认识的选择器: ' + s);
    const cls = m[1], o = m[3], key = cls + '-' + m[2] + '-' + o;
    const el = _els[key] || (_els[key] = _mk(key));
    if (cls.endsWith('sp')) el.value = String(_PRED['jc_' + _KEY[o]]);
    return el;
  }},
}};
const t = (k) => k, outcomeLabel = (o) => o, fmtMoney = (x) => 'CNY' + Number(x).toFixed(2);
// 纯显示桩(读过源码:返回值不回流到 evGate / pass / 注额)
const _frzBandHtml = () => '', _frzHalfEv = () => 0, _evRelTag = () => '';
const _isWideBook = () => false, _modelPStale = () => false;
const _jcStaleCapture = () => '', _sweetBoardScheduleRefresh = () => {{}};
// `_bestLegRefresh` 桩 —— ⭐ 最优腿徽章(2026-09-03)。按本 harness 自己的分界线:
// 它无返回值、只写徽章那一格,**不流进 evLo / pass / 注额** ⇒ 纯显示,可以桩。
const _bestLegRefresh = () => {{}};
const _parlayRender = undefined, _spcalcSaveManual = () => {{}};
{_consts('_TODAY_REC_GATE', '_PMKT_DIVERGE_PP')}
{_fn('_mktP')}
{_fn('_onexLoP')}
{_fn('_spcalcStake')}
const _CUPMKT = {{ preds: [_PRED], minEv: 0.05, bankroll: 10000, kelly: 0.25 }};
const _SPCALC = _CUPMKT;
{_fn(fn)}
{fn}(0);
Object.keys(_els).forEach((k) => {{
  const e = _els[k];
  if (e.style && e.style.color === '#059669') _out.green.push(k);
}});
console.log(JSON.stringify(_out));
""")

    @pytest.mark.parametrize("fn", ["_spcalcRecalc", "_cupRecalc"])
    def test_gate_does_not_fire_when_only_the_point_estimate_clears(self, fn) -> None:
        """⭐ 承重条:点估 +20% / 下界 −10% ⇒ **不许变绿**。

        这条红 = 有人把判闸行换回了点估(`evMkt` 或 `P[o]`)。
        """
        out = self._run(fn, self._PR_1X2)
        assert not out["green"], (
            f"{fn} 让下界 −10% 的腿变绿了 ⇒ 判闸疑似改回点估。绿的格:{out['green']}")

    @pytest.mark.parametrize("fn", ["_spcalcRecalc", "_cupRecalc"])
    def test_gate_still_fires_when_the_lower_bound_clears(self, fn) -> None:
        """反向对照 —— 别把闸焊死。下界 0.60 × 2.00 − 1 = +20% ⇒ **应该**绿。

        没有这条,上一条可能只是「什么都不过闸」。
        """
        pr = {**self._PR_1X2, "onex_lo_home": 0.60}
        out = self._run(fn, pr)
        assert out["green"], f"{fn} 下界 +20% 的腿没变绿 —— 闸被焊死了?{out}"
