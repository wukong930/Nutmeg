"""双 EV + 判闸改用市场 EV + 模型 P 陈旧标(owner 2026-08-06)。

## 三个问题引出的三件事

owner 问:①手填时模型 P 是不是跟不上 ②能不能显示纯市场 EV ③有没有更好的方案。

实测下来:

* 模型 P **会**随 Pinnacle 盘口变(`market_p_*` 是模型的输入特征;同一场只改赔率,
  主胜从 43.8% 走到 32.2%),**但不跟着手填变** —— 而手填恰恰发生在临场、线动得
  最多的时候。同一张卡上「市」是新的、模型 P 是旧的,**判闸却用旧的那个**。
* ⛔ 没走「让手填也重算模型 P」:40 个特征里只有 5 个(收盘 1X2 去vig)手填能改,
  其余 35 个(Elo/form/开盘漂移)是冻结快照。硬刷那 5 个会把模型推出训练分布,
  而且**给不新鲜的东西刷层新鲜的漆,比让它显示自己不新鲜更危险**。

## 为什么判闸改用市场 EV

不是「市场更准」—— 那也没测过。是:

* 模型至今没有一次被证明赢过 Pinnacle;自检看板 N 太小读不了(要等秋季 N≥100);
* `team_state` 冻在 2026-06-01,上赛季后半程一场没进;
* 实测结论「**EV 是排除器不是排序器**」⇒ 模型当否决器安全,当发现器是在赌一个
  未验证的组件;
* 市场模式的**所有**比赛早就是市场 P 判闸,改完全系统口径统一。

## 本文件为什么在 node 里真跑

「显示了两个 EV」和「判闸真的换了」是两件事。前者 grep 得到,后者不行 ——
少写一个 `evGate`、或 `best` 里回填成 `evModel`,grep 全过、钱照错。所以这里
把 `_spcalcRecalc` 从源码抠出来,配 DOM 桩真跑,断言**过闸与否**和**注额**。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(name: str) -> str:
    js = _js()
    m = re.search(rf"\n(async )?function {re.escape(name)}\(", js)
    assert m, f"找不到 {name}"
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
    m = re.search(rf"const {re.escape(name)} = [^;]+;", _js())
    assert m, f"找不到常量 {name}"
    return m.group(0)


def _run(pr: dict, sp: dict, min_ev: float = 0.05) -> dict:
    """真跑 `_spcalcRecalc`,回收它写进 DOM 的结论。

    桩只替换 DOM 与**周边**helper(带宽/可靠性标/Kelly);被测的判闸逻辑、
    `_mktP`、`_modelPStale`、`_PMKT_DIVERGE_PP` 全部从源码抠。
    """
    src = f"""
const _out = {{ ev: {{}}, cls: {{}}, color: {{}}, verdict: null, btnDisabled: null }};
const _inputs = {json.dumps(sp)};
function _mkEl(id) {{
  return {{ _id: id, textContent: '', innerHTML: '', className: '', disabled: null,
    style: {{ cssText: '', get color() {{ return this._c || ''; }},
              set color(v) {{ this._c = v; _out.color[id] = v; }},
              fontWeight: '' }},
    removeAttribute() {{ this.style._c = ''; }},
    set _ih(v) {{}} }};
}}
const _els = {{}};
function _get(id) {{
  if (!_els[id]) _els[id] = _mkEl(id);
  return _els[id];
}}
const document = {{
  querySelector(sel) {{
    const m = sel.match(/data-idx="(\\d+)"\\]\\[data-outcome="([HDA])"/);
    if (m && sel.includes('spcalc-sp')) {{
      const v = _inputs[m[2]];
      return v == null ? null : {{ value: String(v) }};
    }}
    return null;
  }},
  getElementById: _get,
}};
const $ = (s) => _get(s.replace('#', ''));
const t = (k) => k;
const outcomeLabel = (o) => o;
const fmtMoney = (x) => 'CNY' + Number(x).toFixed(2);
const _frzBandHtml = () => '';
const _frzHalfEv = () => 0;
const _evRelTag = () => '';
const _isWideBook = () => false;
const _spcalcStake = (p, sp, bankroll, kelly) => p * 1000;   // 可辨认:注额 = P×1000
const _parlayRender = undefined;
const _jcStaleCapture = () => {{}};
const _sweetBoardScheduleRefresh = () => {{}};

{_const('_PMKT_DIVERGE_PP')}
{_fn('_mktP')}
{_fn('_modelPStale')}

const _SPCALC = {{ preds: [{json.dumps(pr)}], minEv: {min_ev}, bankroll: 10000, kelly: 0.5 }};
{_fn('_spcalcRecalc')}
_spcalcRecalc(0);

['H','D','A'].forEach(o => {{
  const e = _els['spcalc-ev-0-' + o];
  if (e) {{ _out.ev[o] = e.innerHTML; _out.cls[o] = e.className; }}
}});
const v = _els['spcalc-verdict-0'];
_out.verdict = v ? v.textContent : null;
// 2026-08-06 — 卡级「已下单」按钮已删,过闸信号改读 verdict:
//   过闸 ⇒ `spcalc_pick: …`   不过闸 ⇒ `spcalc_nobet` / `spcalc_enter_sp` / `spcalc_nojc`
_out.passed = !!(v && String(v.textContent).includes('spcalc_pick'));
console.log(JSON.stringify(_out));
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[:2000]
    return json.loads(r.stdout)


def _pred(*, pm, pk, **kw) -> dict:
    """pm = 模型 P 三元组;pk = 市场 P 三元组(None ⇒ 没有 Pinnacle 线)。"""
    d = {"p_home_1x2": pm[0], "p_draw_1x2": pm[1], "p_away_1x2": pm[2],
         "jc_home": None, "jc_draw": None, "jc_away": None}
    if pk is not None:
        d.update(p_home_market=pk[0], p_draw_market=pk[1], p_away_market=pk[2])
    d.update(kw)
    return d


class TestGateFollowsTheMarket:
    def test_model_rosy_market_thin_does_not_pass(self):
        """⭐⭐ 本次改动的**核心行为**,用这张德乙卡的真实数字。

        模型 47% / 市场 42%,SP=2.40:
            EV模型 = .47×2.40−1 = +12.8%   ← 旧行为:远超 +5% 闸,绿灯
            EV市场 = .42×2.40−1 =  +0.8%   ← 新行为:不过闸
        这条红了 = 判闸又滑回模型 P 了。
        """
        out = _run(_pred(pm=(0.47, 0.25, 0.28), pk=(0.42, 0.26, 0.32)), {"H": 2.40})
        assert out["passed"] is False, out["verdict"]
        assert "spcalc_nobet" in (out["verdict"] or "")
        # 两个 EV 都得显示出来,不是把模型 EV 藏了
        assert "+0.8%" in out["ev"]["H"] and "+12.8%" in out["ev"]["H"], out["ev"]["H"]

    def test_model_negative_market_positive_does_pass(self):
        """反向:模型看空、市场看多 ⇒ 现在**过闸**。

        没有这条,上一条可能只是「什么都不过闸」。
        模型 30% → EV −28%;市场 50% → EV +20%(SP=2.40)。
        """
        out = _run(_pred(pm=(0.30, 0.30, 0.40), pk=(0.50, 0.25, 0.25)), {"H": 2.40})
        assert out["passed"] is True, out["verdict"]
        assert "+20.0%" in out["ev"]["H"] and "-28.0%" in out["ev"]["H"], out["ev"]["H"]

    def test_stake_uses_the_gating_probability(self):
        """注额跟判闸同源 —— 用模型 P 下注、用市场 P 判闸会得到两边都不自洽的仓位。

        桩里 `_spcalcStake = P × 1000`,所以注额直接读出用的是哪个 P。
        """
        out = _run(_pred(pm=(0.30, 0.30, 0.40), pk=(0.50, 0.25, 0.25)), {"H": 2.40})
        assert "CNY500.00" in (out["verdict"] or ""), out["verdict"]   # .50×1000,不是 .30


class TestNoMarketLineMeansNoGate:
    def test_missing_market_p_never_greens(self):
        """⛔ 没有 Pinnacle 线 ⇒ **不判闸**,而不是回退到模型 EV。

        回退等于把刚移出判闸的东西从后门放回来,而且是静默的。
        这里模型 EV 高达 +88%,仍然不许过。
        """
        out = _run(_pred(pm=(0.78, 0.12, 0.10), pk=None), {"H": 2.40})
        assert out["passed"] is False, out["verdict"]
        assert "spcalc_ev_nomkt" in out["ev"]["H"], out["ev"]["H"]

    def test_partial_market_p_is_treated_as_missing(self):
        """三个只给两个 = 不完整 ⇒ 当没有。别拿半份数据算 EV。"""
        pr = _pred(pm=(0.47, 0.25, 0.28), pk=None)
        pr["p_home_market"] = 0.42          # 只有主胜
        out = _run(pr, {"H": 2.40})
        assert out["passed"] is False
        assert "spcalc_ev_nomkt" in out["ev"]["H"]


class TestDivergenceFlag:
    def test_flags_when_model_and_market_disagree(self):
        """模型 47% vs 市场 42% = 5pp ⇒ 到阈值,标出来。"""
        out = _run(_pred(pm=(0.47, 0.25, 0.28), pk=(0.42, 0.26, 0.32)), {"H": 2.40})
        assert "⚠︎" in out["ev"]["H"] and "+5pp" in out["ev"]["H"], out["ev"]["H"]

    def test_quiet_when_they_agree(self):
        """差 1pp 不标 —— 老误报的护栏最后会被删掉。"""
        out = _run(_pred(pm=(0.43, 0.26, 0.31), pk=(0.42, 0.26, 0.32)), {"H": 2.40})
        assert "⚠︎" not in out["ev"]["H"], out["ev"]["H"]


class TestStaleBadge:
    def test_manual_fill_marks_model_p_stale(self):
        """手填过 ⇒ 模型 P 打 ⏳(它不跟着手填变,这是结构事实不是估计)。"""
        src = f"{_fn('_modelPStale')}\nconsole.log(JSON.stringify([" \
              "_modelPStale({_manual: true}), _modelPStale({}), _modelPStale(null)]));"
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout) == [True, False, False]

    def test_card_renders_the_badge(self):
        """⚠️ 语法断言,只当补充 —— 承重的是上面真跑的那些。"""
        js = _js()
        assert "_modelPStale(pr) ?" in js, "卡片没挂陈旧标"
        assert "spcalc_p_stale" in js


class TestMarketPComesFromTheServer:
    def test_no_client_side_devig_fallback(self):
        """⭐ `_mktP` **故意不做**客户端 basic 兜底。

        兜底会让「服务端字段缺失」静默退化成另一种去vig 方法 —— 而这正是本次
        要消灭的劈叉:显示用 basic(42.0%)、EV/分析路用 WPO(42.5%)。判闸真的
        用市场 EV 之后,这 0.5pp 就不再是显示瑕疵而是钱。
        """
        body = _fn("_mktP")
        assert "psc" not in body, f"_mktP 里出现了 psc —— 疑似又在客户端自己去vig:\n{body}"
        assert "p_home_market" in body

    def test_server_sends_the_field(self):
        from nutmeg.v4.api.schemas import SinglePrediction
        for f in ("p_home_market", "p_draw_market", "p_away_market"):
            assert f in SinglePrediction.model_fields, f

    def test_server_uses_wpo_not_basic(self):
        """服务端那三个字段必须来自 WPO(和手填 reprice 端点同一个函数)。"""
        from nutmeg.v4.model.devig import devig_1x2
        wpo = devig_1x2(2.25, 3.57, 2.99, method="wpo")
        basic = devig_1x2(2.25, 3.57, 2.99, method="basic")
        assert abs(wpo[0] - basic[0]) > 0.004, "两法差太小,这条测试失去区分力"
        routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert "mkt = _pinnacle_devig_1x2(f.psc_home, f.psc_draw, f.psc_away)" in routes


@pytest.mark.parametrize("key", [
    "spcalc_ev_model", "spcalc_ev_mkt", "spcalc_ev_nomkt",
    "spcalc_diverge_tip", "spcalc_p_stale", "spcalc_p_stale_tip",
])
def test_i18n_keys_exist_in_both_locales(key):
    """漏一个语言 ⇒ 面板上直接显示 key 名。"""
    js = _js()
    assert js.count(f"{key}:") >= 2, f"{key} 只有 {js.count(f'{key}:')} 处(中英各需 1)"
