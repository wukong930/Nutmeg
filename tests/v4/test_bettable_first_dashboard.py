"""竞彩可投注:2026-07-07 置顶区 → 2026-08-05 **独立成全局列表**。

## 原设计(2026-07-07,保留原文)

「近期赛事 pins matches 竞彩 lists for betting to a top zone (still league-grouped),
then the model/Pinnacle reference rump. Applies to BOTH 标准模式 (renderTodaySpCalc)
and 市场模式 (loadCupMarket) via one shared helper.」

守的性质:**能买的排在前面、两种模式同一套排序、折叠 key 分名字空间**。

## 2026-08-05 owner:「独立出来成一个列表,排版放到甜区EV榜上面」

置顶区从两块模式板里搬出来,合并成 `#jc-bettable-global`,置于 `#sweet-board-global`
之上。原来的 `_bettableFirstHtml(preds, cardHtml, mode)` 收**单个** cardHtml,
而合并列表要装两模式的卡(标准是 renderTodaySpCalc 里的局部箭头函数、市场是顶层
`_cupCardHtml`)⇒ 该签名不可能原样存活,拆成 `_bettableSplit` + `_renderBettableInto`。

⚠️ 上面那三条性质**一条没变**,变的只是容器。所以本文件按新结构重写断言,
docstring 原文留着 —— 断言可以过时,它当初想守的东西不会。

## ⭐ 为什么是「两个按模式独占的子容器」而不是一个合并 innerHTML

三条都是**在真实页面上跑出来的**(多 agent 对抗验证,2026-08-05),不是设计洁癖:

1. **卡片只能搬不能复制。** 同一 `data-idx` 出现两次时,页面上每一处
   `document.querySelector` 都取文档序第一个 ⇒ 第二张卡收得下键盘、永远没有反应
   (连 EV 都不出,判词停在「竞彩未开盘」);更贵的是 `_recordBet` 会在你点的那张卡上
   开注额框,却把**另一张卡的赔率** POST 出去 —— 无 alert 无提示。CSS 隐藏救不了:
   隐藏元素照样赢选择器。
2. **不能交给 `_sweetBoardRefresh` 渲染。** 它挂 350ms 防抖、且完全从 preds 重建
   (零 DOM 读回),而 `_spcalcRecalc` 每次 oninput 都重排这个防抖 ⇒ 每敲一个数字,
   350ms 后卡片被重建,输入值和焦点一起没。
3. **两个 renderer 不能共写同一块 innerHTML。** 后跑的那个把先跑的卡片整片抹掉,
   而对方的后处理循环早已跑完,不会再补。

⇒ 每块子容器由**它自己那个 renderer** 在后处理循环**之前同步**写入。
本文件的 `TestOwnershipInvariants` 就是守这三条。
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


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(html: str, name: str) -> str:
    """按配对括号抠出一个顶层函数体。"""
    m = re.search(rf"\n(async )?function {re.escape(name)}\(", html)
    assert m, f"找不到 {name}"
    start, j, depth = m.start() + 1, html.index("{", m.end()), 0
    while j < len(html):
        if html[j] == "{":
            depth += 1
        elif html[j] == "}":
            depth -= 1
            if depth == 0:
                return html[start:j + 1]
        j += 1
    raise AssertionError(name)


def _decl(html: str, head: str) -> str:
    """抠出一个顶层 `function …{}` 或 `const …;` 声明(同 test_jc_closing_zone.py)。"""
    i = html.index(head)
    depth, started = 0, False
    for j in range(i, len(html)):
        c = html[j]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return html[i:j + 1]
        elif c == ";" and not started:
            return html[i:j + 1]
    raise AssertionError(f"括号不平衡:{head}")


def _ko(minutes: float) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes)).isoformat()


#: 六张卡,横跨 `_bettableSplit` 的全部三个去向。⚠️ 本文件**不**断言 2/3/4/5 各自
#: 落进哪个桶(那是 `test_jc_closing_zone.py` 的活),只断言 0/1 不许出现在板里。
_SPLIT_FIXTURE = [
    {"jc_home": 2, "jc_draw": 3, "jc_away": 4, "kickoff_utc": _ko(600)},   # 0 可投注
    {"jc_home": 2, "jc_draw": 3, "jc_away": 4},                           # 1 可投注(无开球时刻)
    {"jc_home": 2, "jc_draw": 3, "jc_away": 4, "kickoff_utc": _ko(3)},    # 2 即将截止
    {"jc_home": 2, "jc_draw": 3, "jc_away": 4, "kickoff_utc": _ko(-10)},  # 3 已开赛
    {},                                                                    # 4 竞彩没上架
    {"jc_home": 2},                                                        # 5 SP 不全
]


def _run_split_wiring(html: str, renderer: str) -> dict:
    """把某个 renderer 里「切分 → 写顶部 → 写板」那三行**原样**抠出来跑一遍。

    ⭐ 为什么不逐字匹配那三行:调用点每加一个实参就会误报一次,而误报的是
    「性质破了」这个结论 —— 代价比漏报更贵(见调用方 docstring)。
    ⭐ 为什么不整跑 `renderTodaySpCalc`:它要一整个 DOM,而**这三行**就是本条要守的
    全部接线。桩掉两个渲染器只记「谁收到了哪些卡」,其余原样执行。
    """
    body = _fn(html, renderer)
    m = re.search(r"const \{[^}]*\} = _bettableSplit\(preds\);.*?_referenceZoneHtml\([^;]*;",
                  body, re.S)
    assert m, f"{renderer} 里找不到「_bettableSplit → _referenceZoneHtml」那段接线"
    src = "\n".join(_decl(html, h) for h in (
        "const _JC_KO_BUFFER_MIN", "function _hasJcSp", "function _jcKoState",
        "function _isJcBettable", "function _bettableSplit"))
    harness = """
__SRC__
let _up = null;
// 顶部那块全局子容器收到了什么
function _renderBettableInto(mode, bett, cardHtml) { _up = (bett || []).map(o => o.idx); }
// 板收到了什么。真的 `_referenceZoneHtml` 把**它收到的每一个桶**都 join 进返回值
// (clo / kck / rest 三段,见源码)⇒ 桩按「所有数组实参都会被画进板里」建模。
// `bett.length` 是个数字,`Array.isArray` 自然滤掉 ⇒ 传计数不算把卡传进板里。
function _referenceZoneHtml(...args) {
  return args.filter(Array.isArray).flatMap(a => a.map(o => `[#${o.idx}]`)).join('');
}
const cardHtml = () => '';
const _cupCardHtml = () => '';
const list = {};
const preds = __PREDS__;
__WIRING__
// ⚠️ 板的落点是 `scoredHtml`(标准)还是 `list.innerHTML`(市场)由抠出来的那段
//    自己决定;两个都取不到就让它炸,别静默返回空(空 = 下面的断言全恒真)。
const board = (typeof scoredHtml !== 'undefined') ? scoredHtml : list.innerHTML;
if (typeof board !== 'string') throw new Error('取不到板的 innerHTML —— 落点变了');
console.log(JSON.stringify({
  up: _up,
  board: [...board.matchAll(/\\[#(\\d+)\\]/g)].map(x => +x[1]),
}));
"""
    r = subprocess.run(
        ["node", "-e", harness.replace("__SRC__", src)
                              .replace("__PREDS__", json.dumps(_SPLIT_FIXTURE))
                              .replace("__WIRING__", m.group(0))],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"node 跑挂了:\n{r.stderr[-2000:]}"
    out = json.loads(r.stdout.strip().split("\n")[-1])
    assert out["up"] is not None, "`_renderBettableInto` 压根没被调用 —— 接线断了"
    return out


class TestBettableFirst:
    def test_helpers_defined(self, html: str) -> None:
        assert "function _isJcBettable(pr)" in html
        assert "function _lgGroupsHtml(items, cardHtml, pfx)" in html
        # 2026-08-05:`_bettableFirstHtml` 拆成「纯切分」+「写 DOM」两半
        assert "function _bettableSplit(preds)" in html
        assert "function _renderBettableInto(mode, bett, cardHtml)" in html

    def test_bettable_signal_is_full_had_sp(self, html: str) -> None:
        # A match is bettable iff it has a full HAD 竞彩 SP on file (all 3 legs).
        assert "pr.jc_home != null && pr.jc_draw != null && pr.jc_away != null" in html

    def test_standard_mode_wired(self, html: str) -> None:
        # 标准模式 renders through the shared helper (not the old raw byLeague loop).
        body = _fn(html, "renderTodaySpCalc")
        assert "_bettableSplit(preds)" in body
        assert "_renderBettableInto('spcalc', bett, cardHtml)" in body

    def test_market_mode_wired(self, html: str) -> None:
        # 市场模式 renders through the SAME helpers so both modes order identically.
        body = _fn(html, "renderCupMarket")
        assert "_bettableSplit(preds)" in body
        assert "_renderBettableInto('cup', _cBett, _cupCardHtml)" in body

    def test_zones_use_distinct_collapse_pfx(self, html: str) -> None:
        # Bettable zone namespaces its collapse keys so the SAME league folds
        # independently from its reference-zone copy. 2026-08-05:'jc:' → 'jcg:'
        # (新容器 = 新名字空间,且它在默认折叠集里)。
        assert "_lgGroupsHtml(bett, cardHtml, 'jcg:')" in _fn(html, "_renderBettableInto")
        assert "_lgGroupsHtml(rest, cardHtml, '')" in _fn(html, "_referenceZoneHtml")

    def test_degrades_when_nothing_bettable(self, html: str) -> None:
        """没有可投注场次 → 顶部列表不占位,模式板恢复朴素联赛分组(老样子)。"""
        assert "box.innerHTML = bett.length ? _lgGroupsHtml(bett, cardHtml, 'jcg:') : ''" \
            in _fn(html, "_renderBettableInto")
        # 参考区没有可投注头,和改动前一致
        ref = _fn(html, "_referenceZoneHtml")
        assert "jc_bettable_hdr" not in ref

    def test_reference_zone_says_so_when_everything_moved_up(self, html: str) -> None:
        """⚠️ 某模式**每一场**都可投注时,板里的列表会空 —— 只留一块空白读起来
        像「板坏了」。必须有一句话说明它去哪了。同「分不出没有和没去看」。"""
        ref = _fn(html, "_referenceZoneHtml")
        assert "jc_all_moved_up" in ref
        hits = re.findall(r"jc_all_moved_up:\s*'((?:[^'\\]|\\.)*)'", html)
        assert len(hits) == 2, f"中英没齐({len(hits)})"

    def test_i18n_keys_present_both_locales(self, html: str) -> None:
        """⚠️ 不再断言 `count(...) >= 3` —— 那种计数式断言零余量,一改就假红。
        钉的是「两个 locale 各有一条定义」这个**性质**。"""
        for key in ("h_jc_bettable", "jc_bettable_note", "jc_all_moved_up", "jc_ref_hdr"):
            hits = re.findall(rf"{key}:\s*'((?:[^'\\]|\\.)*)'", html)
            assert len(hits) == 2, f"{key} 中英没齐(找到 {len(hits)} 条)"

    def test_headers_rendered_via_i18n(self, html: str) -> None:
        assert 'data-i18n="h_jc_bettable"' in html      # 容器头(同 h_spcalc/h_cupmkt 写法)
        assert "t('jc_ref_hdr')" in html                # 参考区头(JS 渲染)

    def test_no_orphan_pin_header_key_left_behind(self, html: str) -> None:
        """置顶区的 pin 头随搬迁消失 ⇒ `jc_bettable_hdr` 成了孤儿键,已删。
        留着孤儿键会让下一个人以为还有个地方在用它。"""
        assert "jc_bettable_hdr" not in html


class TestOwnershipInvariants:
    """⭐ 三条实测出来的硬约束 —— 见文件 docstring。"""

    def test_container_has_one_subcontainer_per_mode(self, html: str) -> None:
        assert 'id="jc-bettable-spcalc"' in html
        assert 'id="jc-bettable-cupmkt"' in html

    def test_each_renderer_writes_only_its_own_subcontainer(self, html: str) -> None:
        """两个 renderer 共写一块 innerHTML ⇒ 后跑的抹掉先跑的卡片。"""
        body = _fn(html, "_renderBettableInto")
        assert "mode === 'cup' ? 'jc-bettable-cupmkt' : 'jc-bettable-spcalc'" in body
        # 顶层容器本身不许被任何人整块 innerHTML 覆盖
        assert not re.search(r"getElementById\('jc-bettable-global'\)[^\n]*\n?[^\n]*innerHTML\s*=",
                             html), "有人在整块覆盖外壳,会连子容器一起抹掉"

    def test_sweet_board_does_not_own_the_cards(self, html: str) -> None:
        """`_sweetBoardRefresh` 挂 350ms 防抖 + 零 DOM 读回 ⇒ 它若渲染卡片,
        每敲一个数字 350ms 后输入值和焦点一起没。"""
        body = _fn(html, "_sweetBoardRefresh")
        assert "jc-bettable" not in body

    def test_cards_are_written_before_the_post_processing_loop(self, html: str) -> None:
        """⭐ 顺序是硬约束:`_spcalcRecalc` 在后处理循环里逐卡跑,卡片此刻不在 DOM
        就会抛(它现在有守卫了,但顺序错了照样什么都不恢复)。"""
        body = _fn(html, "renderTodaySpCalc")
        i_render = body.index("_renderBettableInto('spcalc'")
        i_loop = body.index("preds.forEach((pr, idx) => {\n   try {")
        assert i_render < i_loop, "可投注卡在后处理循环之后才渲染 ⇒ 恢复/重算全落空"

    def test_boards_never_render_the_bettable_cards_themselves(self, html: str) -> None:
        """⭐⭐ 本文件最要紧的一条 —— 而它第一版**漏了**(变异 M1 全绿,2026-08-05)。

        「搬」和「复制」在源码上只差一个 `+`,在行为上差一个静默的错单:
        复制之后第二张卡收得下键盘却毫无反应,`_recordBet` 还会把另一张卡的赔率
        POST 出去。所以必须钉死:**两个 renderer 的板内容里不许出现可投注那批**。

        ## 2026-09-01 —— 后两条从「逐字匹配调用点」改成**真跑那三行**

        原来钉的是 `"const scoredHtml = _referenceZoneHtml(rest, cardHtml, bett.length);"`。
        a95888b(开赛前后三分区)给 `_referenceZoneHtml` 加了第 4 个实参 `closing`
        ⇒ 逐字匹配红,而它守的性质**一点没破**(`closing` 里装的是有竞彩 SP 但已过
        T−5 的场,与 `bett` 互斥)。⇒ 断言过时,不是代码退化。

        改法不是把新拼法抄进来 —— 那只是把同一根线往后挪一格(本仓已经绊过两次,
        见 `test_cup_manual_persist_dashboard.py::test_restore_triggers_background_reprice`)。
        现在把调用点那三行**原样抠出来在 node 里执行**,桩掉两个渲染器只记「谁收到了
        哪些卡」,断言:可投注那批**只**去了顶部子容器,板里一张都没有,且两边加起来
        不多不少就是全部。加第 5 个实参、换参数顺序都不会误报;把 `bett` 传进板里
        才会红 —— 那正是「搬」变成「复制」的那一个 `+`。
        """
        for fn, bett in (("renderTodaySpCalc", "bett"), ("renderCupMarket", "_cBett")):
            body = _fn(html, fn)
            assert f"_lgGroupsHtml({bett}" not in body, (
                f"{fn} 自己又渲染了一遍可投注卡 ⇒ 同一场比赛在页面上有两张卡")

        for fn in ("renderTodaySpCalc", "renderCupMarket"):
            r = _run_split_wiring(html, fn)
            up, board = set(r["up"]), set(r["board"])
            assert up == {0, 1}, (
                f"{fn}:夹具没造出可投注卡(顶部收到 {sorted(up)},应为 [0, 1])"
                f" ⇒ 下面两条恒真")
            assert not (up & board), (
                f"{fn}:{sorted(up & board)} 号场**同时**出现在顶部列表和模式板里。"
                f"\n⇒ 同一 `data-idx` 两张卡:每处 querySelector 都取文档序第一张,"
                f"第二张收得下键盘却毫无反应,而 `_recordBet` 会把**另一张卡的赔率**"
                f" POST 出去(无 alert 无提示)。CSS 隐藏救不了 —— 隐藏元素照样赢选择器。")
            assert up | board == set(range(6)), (
                f"{fn}:有卡片凭空消失了 —— 顶部 {sorted(up)} + 板 {sorted(board)}"
                f" 不等于全部 6 张")

    def test_bettable_groups_default_to_collapsed(self, html: str) -> None:
        """owner 2026-08-05 选的是「完整卡片,但联赛分组默认折叠」。

        ⚠️ 真跑 `_lgGroupHtml`,不 grep `_LG_DEFAULT_COLLAPSED` 的字面量 ——
        第一版只 grep 了集合内容,把常量清空的变异照样绿(默认值和渲染是两件事)。
        """
        import json
        import subprocess
        m = re.search(r"const _LG_DEFAULT_COLLAPSED = new Set\([^)]*\);", html)
        assert m, "找不到 _LG_DEFAULT_COLLAPSED 的声明"
        # ⚠️ 常量从**源码里抠**,不在桩里重写一遍 —— 第一版就是自己写了一份
        # `new Set(['jcg:'])`,于是「把真常量清空」的变异照样绿(2026-08-05 实测)。
        # 桩把被测的东西替换掉,同 [[syntactic-proxy-for-semantic-property]]。
        src = (m.group(0) + _fn(html, "_lgDefaultCollapsed") + _fn(html, "_lgGroupHtml")
               + "const _collapsedLgs = new Set();"
               + "const t = k => k; const zhLeague = x => x;"
               + "console.log(JSON.stringify({"
               + "  jcg: _lgGroupHtml('EPL', '#000', 1, '<i></i>', 'jcg:'),"
               + "  plain: _lgGroupHtml('EPL', '#000', 1, '<i></i>', ''),"
               + "}));")
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout)
        assert 'class="spcalc-lg-cards hidden"' in out["jcg"], "可投注组默认没收起"
        assert 'aria-expanded="false"' in out["jcg"] and "▸" in out["jcg"]
        # 既有前缀行为**逐字不变**:XOR 的另一半
        assert 'class="spcalc-lg-cards"' in out["plain"], "普通组被连坐折叠了"
        assert 'aria-expanded="true"' in out["plain"] and "▾" in out["plain"]
        assert "'jcg:'" in _fn(html, "_renderBettableInto"), "渲染时没用默认折叠的那个前缀"

    def test_empty_paths_clear_the_subcontainer_too(self, html: str) -> None:
        """空态早退若不清子容器,顶部会留下一批**已不在 preds 里**的幽灵卡,
        而它们的 data-idx 还会被 querySelector 抢走。"""
        assert "_renderBettableInto('spcalc', [], null)" in _fn(html, "renderTodaySpCalc")
        assert "_renderBettableInto('cup', [], null)" in _fn(html, "renderCupMarket")


class TestRecalcGuards:
    """搬动卡片把「卡片不在 DOM」变成了可达状态 ⇒ 补齐守卫。

    实测:`_spcalcRecalc` 原来 `parseFloat(inp.value)` 无守卫会抛,而
    `_cupRecalc` 一直是全守卫的 —— **两模式不对称**。抛出去的后果不是少算一张卡:
    它之后**所有**场次的 SP 恢复 / 让球线回填全不跑、`_parlayRestore` 永远不执行,
    最后还显示成「抓取盘口失败(API 暂不可用)」—— DOM 问题伪装成网络问题。
    """

    def test_spcalc_recalc_guards_missing_card(self, html: str) -> None:
        assert "if (!inp || !evSpan) return;" in _fn(html, "_spcalcRecalc")

    def test_spcalc_hc_recalc_guards_missing_card(self, html: str) -> None:
        assert "if (!inp || !evSpan) return;" in _fn(html, "_spcalcHcRecalc")

    def test_post_loop_isolates_one_bad_card(self, html: str) -> None:
        """同后端 `_calc_predictions` 的「一场中毒不许拖垮整块板」(体检 Wave2)。"""
        body = _fn(html, "renderTodaySpCalc")
        i_try = body.index("preds.forEach((pr, idx) => {\n   try {")
        i_catch = body.index("} catch (e) {", i_try)
        i_parlay = body.index("_parlayRestore();", i_try)
        assert i_try < i_catch < i_parlay, "try/catch 没把整圈后处理包住"
