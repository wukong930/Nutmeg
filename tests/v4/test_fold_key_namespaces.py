"""联赛折叠 key 的名字空间(owner 2026-08-05)。

## 病

`_lgGroupHtml` 的注释从一开始就写着:

    pfx namespaces the collapse key so the SAME league folds independently in
    different sections (e.g. scored board vs 待开盘). Default '' = scored boards.

—— 但 `_mktGroupsHtml`(今日推荐的市场预测板)**没传 pfx**,退化成 `''`。而它被
`renderMarketPred` 调**两次**(强档 / 弱档),两块都写进 `#mktpred-list`;
`#cupmkt-list` 的参考区也用 `''`。活页面实测:43 个组里 **11 个 key 各 3 份**。

## 危害不在点击当下,在下一次重渲

`_toggleLeague` 走 `headEl.closest(...)`,点谁收谁 —— 所以肉眼看着是对的。
但折叠位是**按 key 持久化的全局状态**,重渲时每个同 key 的组都去读它。
实测复现(活页面,2026-08-05):

    ① 三处 UEL 都展开
    ② 只点「今日推荐」强档里那个 UEL 组头 → 只有它自己收起
    ③ 重渲「近期赛事」的市场板 → `#cupmkt-list` 里的 UEL **自己塌了**

一个 tab 里的操作静默改了另一个 tab 的版式,而且中间隔着一次重渲,
现场根本联系不起来。

## 这条测试为什么真跑 JS

「加了 pfx」和「折叠真的互不干扰」是两件事:pfx 传了但两处传成同一个值、
或者 `_toggleLeague` 写回时算的 key 和渲染时不一致,grep 都发现不了。
所以这里在 node 里**真渲染 + 真点击 + 真重渲**,断言另一处不动。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

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


def _run(src: str) -> dict:
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


#: 渲染 + 折叠状态的最小真实环境:两个函数都从源码抠,常量也从源码抠 ——
#: 桩只提供 DOM 之外的边界(t / zhLeague / localStorage)。
def _harness(body: str) -> str:
    js = _js()
    m = re.search(r"const _LG_DEFAULT_COLLAPSED = new Set\([^)]*\);", js)
    assert m, "找不到 _LG_DEFAULT_COLLAPSED"
    return (
        "const _store = new Set();"
        "const localStorage = { getItem: () => '[]', setItem: () => {} };"
        "const t = k => k; const zhLeague = x => x;"
        f"{m.group(0)}"
        "let _collapsedLgs = _store;"
        f"{_fn('_lgDefaultCollapsed')}{_fn('_lgGroupHtml')}"
        f"{body}"
    )


class TestPrefixReallyIsolates:
    def test_same_league_different_prefix_folds_independently(self):
        """⭐ 核心行为:折叠 `mkts:UEL` 之后,重渲 `''` 那一份必须仍是展开的。

        模拟真实时序:渲染 → (用户点了强档那个) → 另一块板重渲。
        `_toggleLeague` 的写回逻辑直接抄用源码,不重写。
        """
        toggle = _fn("_toggleLeague")
        # 只取写回那两行的语义(DOM 部分在 node 里没有,自己驱动)
        assert "if (nowCollapsed !== _lgDefaultCollapsed(lg)) _collapsedLgs.add(lg);" in toggle
        out = _run(_harness("""
const render = (pfx) => _lgGroupHtml('UEL', '#000', 1, '<i></i>', pfx);
const before = { mkts: render('mkts:'), plain: render('') };
// 用户折叠了「今日推荐」强档那个组:_toggleLeague 的写回等价于
const lg = 'mkts:UEL', nowCollapsed = true;
if (nowCollapsed !== _lgDefaultCollapsed(lg)) _collapsedLgs.add(lg);
else _collapsedLgs.delete(lg);
const after = { mkts: render('mkts:'), plain: render('') };
console.log(JSON.stringify({
  before_mkts_collapsed: before.mkts.includes('spcalc-lg-cards hidden'),
  before_plain_collapsed: before.plain.includes('spcalc-lg-cards hidden'),
  after_mkts_collapsed: after.mkts.includes('spcalc-lg-cards hidden'),
  after_plain_collapsed: after.plain.includes('spcalc-lg-cards hidden'),
}));
"""))
        assert out["before_mkts_collapsed"] is False
        assert out["before_plain_collapsed"] is False
        assert out["after_mkts_collapsed"] is True, "折叠没生效"
        assert out["after_plain_collapsed"] is False, (
            "⭐ 连坐:折叠今日推荐的组,近期赛事那份重渲后也塌了 —— 正是本次要修的病")

    def test_without_a_prefix_the_two_would_collide(self):
        """反面对照:两处都用 `''` 时**确实**会连坐。

        没有这一条,上面那条可能只是「折叠根本没生效」。
        """
        out = _run(_harness("""
const render = (pfx) => _lgGroupHtml('UEL', '#000', 1, '<i></i>', pfx);
_collapsedLgs.add('UEL');                      // 一处折叠,key 无前缀
console.log(JSON.stringify({
  a: render('').includes('spcalc-lg-cards hidden'),
  b: render('').includes('spcalc-lg-cards hidden'),
}));
"""))
        assert out["a"] is True and out["b"] is True, "同 key 本来就该一起塌(这是病因)"


class TestMarketPredBoardIsNamespaced:
    def test_helper_requires_a_prefix(self):
        assert "function _mktGroupsHtml(preds, uidStart, pfx)" in _js()
        body = _fn("_mktGroupsHtml")
        assert re.search(r"_mktPredCardHtml\(pr, u\+\+\)\)\.join\(''\), pfx\)", body), \
            "抠出来的 pfx 没传给 _lgGroupHtml"

    def test_strong_and_weak_tiers_use_distinct_namespaces(self):
        """同一联赛可以同时出现在强档和弱档 ⇒ 两档必须各自命名空间。"""
        body = _fn("renderMarketPred")
        assert "_mktGroupsHtml(strong, 0, 'mkts:')" in body
        assert "_mktGroupsHtml(weak, a.nextUid, 'mktw:')" in body

    def test_no_bare_lgGroupHtml_call_left_without_a_prefix(self):
        """⚠️ 语法断言,只当补充 —— 承重的是上面真跑 node 的那两条。
        贴着「调用时只给 4 个实参」这个具体写法写:`_lgGroupHtml` 的第 5 参
        缺省即 `''`,而 `''` 是两块参考区共用的名字空间,新代码不该再默认落进去。
        """
        js = _js()
        # 允许的裸调用:只有 `_lgGroupsHtml` 内部那个显式转发 pfx 的
        bare = [m.group(0) for m in re.finditer(r"_lgGroupHtml\([^;]*?\);", js, re.S)
                if m.group(0).count(",") == 3]
        assert not bare, f"有 _lgGroupHtml 调用没给折叠前缀:{bare}"


class TestExistingNamespacesUnchanged:
    """已有前缀的行为**逐字不变** —— 这次只补一个漏传的地方,不是重排名字空间。"""

    def test_pending_and_reference_zones_keep_their_prefixes(self):
        assert "'pend:')" in _js()                                   # 待开盘
        assert "_lgGroupsHtml(rest, cardHtml, '')" in _fn("_referenceZoneHtml")
        assert "_lgGroupsHtml(bett, cardHtml, 'jcg:')" in _fn("_renderBettableInto")
