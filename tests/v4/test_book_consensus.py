"""多书商共识参照 —— 存储 / 计算 / 前端接线(2026-09-01)。

## 它回答的问题

owner 的原始需求:竞彩**封盘后**价格冻住而外盘还在动 —— 按封盘价算的 EV 还站得住吗?
实测封盘后主胜隐含概率漂移 **|漂移|>2pp 占 29%、>5pp 占 5%**(区间 [−12.4,+9.7]pp),
量级远大于所有 δ 校正。生产 EV 用的已经是**实时** Pinnacle,所以漂移本身吃进去了;
**本层补的是另一半:那次漂移是真信息,还是 Pinnacle 一家的抖动?**

⭐ 已测:单锚会**夸大** —— 法乙那场 Pinnacle 是 13 家里最看好客胜的,
单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**(近一倍)。

⛔ 63 场重叠样本**全是世界杯 + 全是缓存未过期的**,人口偏斜 ⇒ 只证明机制存在,
**不是**影响多大的估计 ⇒ 这一层永远不判闸。下面有一条测试专门钉死这件事。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# ── 存储层 ────────────────────────────────────────────────────────────────
def _books(pin=(2.10, 3.40, 3.60), other=(2.05, 3.50, 3.70)):
    return {"pinnacle": list(pin), "betfair_ex_eu": list(other),
            "williamhill": [2.08, 3.45, 3.65], "unibet_fr": [2.12, 3.38, 3.55],
            "marathonbet": [2.09, 3.42, 3.62]}


def _write(tmp_path, books, **kw):
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    return record_book_snapshot(
        tmp_path / "obs.db", match_date="2026-09-01",
        home_team="West Ham", away_team="Wolves", books=books, **kw)


def test_a_snapshot_is_written_and_reread(tmp_path: Path) -> None:
    assert _write(tmp_path, _books()) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    n, blob = conn.execute("SELECT n_books, books FROM book_snapshots").fetchone()
    assert n == 5
    assert json.loads(blob)["pinnacle"] == [2.10, 3.40, 3.60]


def test_an_unchanged_line_state_is_not_re_written(tmp_path: Path) -> None:
    """⛔ cron 每天多窗跑,价格没动就不该在表里堆重复行(同 `odds_snapshots` 的态度)。"""
    assert _write(tmp_path, _books()) is True
    assert _write(tmp_path, _books()) is False
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 1


def test_a_moved_line_is_written_again(tmp_path: Path) -> None:
    assert _write(tmp_path, _books()) is True
    assert _write(tmp_path, _books(pin=(2.30, 3.40, 3.20))) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 2


def test_insane_odds_are_gated_out(tmp_path: Path) -> None:
    """物理闸:(1.0, 1000] 之外的不收 —— 同 `odds_snapshots._sane_odds`。"""
    b = _books()
    b["broken"] = [0.5, 1.0, -3.0]
    b["also_broken"] = ["x", "y", "z"]
    assert _write(tmp_path, b) is True
    conn = sqlite3.connect(tmp_path / "obs.db")
    n, blob = conn.execute("SELECT n_books, books FROM book_snapshots").fetchone()
    assert n == 5, f"坏赔率没被闸掉:{json.loads(blob).keys()}"


def test_a_failure_never_raises(tmp_path: Path) -> None:
    """本模块契约:采集路径上**绝不抛**。"""
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    assert record_book_snapshot(tmp_path / "nope" / "x.db", match_date="", home_team="",
                                away_team="", books={}) is False


# ── 计算层 ────────────────────────────────────────────────────────────────
def _pred(**kw):
    from nutmeg.v4.api.schemas import SinglePrediction
    base = dict(date=dt.date(2026, 9, 1), home_team="West Ham", away_team="Wolves",
                league="ENG_CHAMPIONSHIP", lambda_home=1.4, lambda_away=1.1,
                p_home_1x2=0.4, p_draw_1x2=0.3, p_away_1x2=0.3,
                jc_home=1.92, jc_draw=3.5, jc_away=3.1)
    base.update(kw)
    return SinglePrediction(**base)


def _attach(tmp_path, monkeypatch, books):
    from nutmeg.v4.api import routes
    _write(tmp_path, books)
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    return p


def test_consensus_excludes_pinnacle_itself(tmp_path, monkeypatch) -> None:
    """🚨 承重:共识**排除 Pinnacle**。

    含它的中位会被它拖着走 ⇒ 答不了「Pinnacle 是不是在自说自话」这个问题,
    而那正是这一层存在的唯一理由。
    构造:Pinnacle 是极端离群,其余 4 家一致 ⇒ 共识必须**完全不受它影响**。
    """
    tight = {"a": [3.0, 3.0, 3.0], "b": [3.0, 3.0, 3.0],
             "c": [3.0, 3.0, 3.0], "d": [3.0, 3.0, 3.0]}
    p_out = _attach(tmp_path, monkeypatch, {**tight, "pinnacle": [1.01, 100.0, 100.0]})
    assert p_out.bk_consensus is not None
    assert abs(p_out.bk_consensus[0] - 1 / 3) < 1e-9, p_out.bk_consensus
    assert p_out.bk_spread == [0.0, 0.0, 0.0], "其余 4 家完全一致,离散该是 0"
    assert p_out.bk_n == 5, "n 要算上 Pinnacle(它在场,只是不进共识)"


def test_too_few_books_gives_nothing(tmp_path, monkeypatch) -> None:
    """⛔ 2 家的「共识」不是共识 —— 少于闸值直接不给,而不是给一个弱的。"""
    p_out = _attach(tmp_path, monkeypatch, {"pinnacle": [2.1, 3.4, 3.6], "a": [2.0, 3.5, 3.7]})
    assert p_out.bk_consensus is None and p_out.bk_n is None


def test_spread_is_in_percentage_points(tmp_path, monkeypatch) -> None:
    """离散度的单位是 **pp**,不是小数 —— 前端直接按 pp 上色,单位错了阈值全废。"""
    spread = {"a": [2.0, 4.0, 4.0], "b": [2.0, 4.0, 4.0], "c": [2.5, 3.5, 3.5],
              "d": [2.5, 3.5, 3.5], "pinnacle": [2.2, 3.8, 3.8]}
    p_out = _attach(tmp_path, monkeypatch, spread)
    assert p_out.bk_spread is not None
    assert 1.0 < max(p_out.bk_spread) < 100.0, p_out.bk_spread


def test_a_missing_table_is_silent(tmp_path, monkeypatch) -> None:
    """新库还没这张表 ⇒ 静默跳过,⛔ 不许让卡片渲染失败。"""
    from nutmeg.v4.api import routes
    (tmp_path / "empty.db").touch()
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "empty.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    assert p.bk_consensus is None


# ── 前端接线 ──────────────────────────────────────────────────────────────
def _html() -> str:
    return (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(encoding="utf-8")


def _js_functions() -> dict[str, str]:
    """把 dashboard.html 的顶层函数切成 {名字: 函数体}(已剥注释)。

    ⚠️ 边界用「顶层 `}`」而不是「下一个 function」—— 后者会把函数之间那些很长的
    决策注释算进上一个函数,实测直接造出 `_hasBk` / `outcomeLabel` 两个假阳。
    """
    import re
    lines = _html().split("\n")
    starts = [(i, m.group(1)) for i, ln in enumerate(lines)
              if (m := re.match(r"function ([A-Za-z_$][\w$]*)\s*\(", ln))]
    out: dict[str, str] = {}
    for i, name in starts:
        for j in range(i + 1, len(lines)):
            if lines[j] == "}":
                body = "\n".join(lines[i:j + 1])
                body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
                out[name] = "\n".join(re.sub(r"//.*$", "", ln) for ln in body.split("\n"))
                break
    return out


def test_the_panel_never_feeds_the_gate() -> None:
    """🚨 承重:参照层**绝不进判闸 / 排序 / 串关 / 钱路**。

    支持它的 63 场样本人口偏斜(全世界杯 + 全缓存未过期)⇒ 只证明机制存在,
    **不是**影响多大的估计。改闸必须走预注册(同 δ / CLV 的规格)。

    ⚠️ 这条原本写死三个名字(`_boardLegs` / `_parlayPool` / `_sweetBoard`),
    实测只覆盖到 39 个相关函数里的 **3** 个 —— 而 `_parlayBuilderHtml`(含 argmax)
    和**钱路 `_recordBet`** 完全裸奔。写死名单的护栏会随代码增长悄悄失效,
    所以改成**自己去发现**这批函数。
    """
    fns = _js_functions()
    assert len(fns) > 150, f"函数切分坏了(只切出 {len(fns)} 个)⇒ 下面的断言会空洞为真"
    MARK = ("evLo", "argmax", "_parlay", "parlayPool", "_recordBet", "kelly", "Kelly")
    BK = ("bk_consensus", "bk_low", "bk_spread", "bk_n", "bk_captured_at")
    gate = {n: b for n, b in fns.items() if any(m in b for m in MARK)}
    # 🚨 人口非平凡:发现器要是哪天只找到 2 个,下面的 not leaked 会**空洞为真**
    assert len(gate) >= 20, f"只发现 {len(gate)} 个判闸/钱路函数 ⇒ 发现器坏了"
    leaked = [n for n, b in gate.items() if any(k in b for k in BK)]
    assert not leaked, f"参照层泄进了判闸/钱路:{leaked}"


def test_the_panel_remembers_that_you_opened_it() -> None:
    """🚨 CONFIRMED 的真 bug:bk 的 <details> 原本是**裸**的。

    这张卡是 innerHTML 整片重建的(60s 轮询 / 🔄 刷新盘口 / 🎯 刷新竞彩 都会重建)
    ⇒ owner 刚点开,下一轮自己就折回去了;外面还套一层**默认折叠**的联赛组
    ⇒ 要挖两层才看得见。仓库里已为让球区踩过同一个坑并留了注释,新面板又踩了一遍。
    """
    import re
    body = _js_functions()["_bkHtml"]
    assert "_foldAttrs('bk'" in body, "bk 的 <details> 没接 _foldAttrs ⇒ 每次重渲都折回去"
    assert "_foldKey(pr)" in body, "fold key 不是按比赛身份取的 ⇒ 换一场就串了"
    kinds = set(re.findall(r"_foldAttrs\('([a-z]+)'", _html()))
    assert {"hc", "mb", "bk"} <= kinds, f"fold kind 冲突或缺失:{kinds}"


def test_promoted_pending_cards_keep_their_consensus() -> None:
    """🚨 CONFIRMED:`_pendPromote` 的白名单原本漏掉整组 `bk_*`。

    服务端 `_attach_book_consensus(pending)` **已经**给待开盘行挂好了,前端在一个
    对象字面量里把它丢了 —— 没告警、没灰字,纯静默丢字段。
    而这批卡恰恰**最需要**第二意见:竞彩在卖、Pinnacle 永远不开盘、P 完全来自
    owner 手打的一条线 ⇒ 单锚不可信到极点。
    """
    body = _js_functions()["_pendPromote"]
    for f in ("bk_consensus", "bk_low", "bk_spread", "bk_n", "bk_captured_at",
              "bk_unavailable"):
        assert f"{f}: pf.{f}" in body, f"升格时丢了 {f}"


@pytest.mark.parametrize("sel", [".spcalc-sp", ".cupsp"])
def test_the_refresh_uses_a_selector_that_actually_exists(sel: str) -> None:
    """🚨 我 2026-09-01 在这里栽过:按对称猜了 `.cupmkt-sp`,而真名是 `.cupsp`。

    猜错的后果是**静默失效** —— `querySelector` 返回 null ⇒ EV 格永远显示 `--`,
    不报错、不变红。⇒ 断言选择器在页面里**不止出现在我自己那行**。
    """
    h = _html()
    assert h.count(sel) > 1, f"{sel} 只出现一次 ⇒ 多半是只在刷新函数里,页面上根本没有"


def test_both_recalc_paths_refresh_the_panel() -> None:
    """手填竞彩 SP 后两条重算路都要刷新参照面板。

    ⚠️ 修的是一个真 bug:`_bkHtml` 是**渲染时烘进 HTML** 的,而 recalc 只改
    `#spcalc-ev-*` ⇒ 手填后真 EV 更新了、参照面板停在旧值。
    **两个数并排而其中一个是陈的,比不显示更坏** —— 它看起来像「共识不同意」,
    其实只是没跟上。
    """
    h = _html()
    for fn in ("_spcalcRecalc", "_cupRecalc"):
        i = h.index("function " + fn)
        assert "_bkEvRefresh" in h[i:i + 2500], f"{fn} 没接刷新"


def test_the_ev_cells_are_addressable() -> None:
    """就地更新的前提:EV 格子有 id。⛔ 不重渲整块 —— 那会把 <details> 收起来。"""
    h = _html()
    # ⚠️ 断言的是**行为形状**(格子有可寻址 id + 刷新函数按同一模式取它),
    #    不是某一行的字面量 —— 后者会因为换个拼法而假红。
    assert "id=\"bk-ev-' + NS + '-' + idx + '-' + i + '-c\"" in h, "共识 EV 格没有 id"
    assert "id=\"bk-ev-' + NS + '-' + idx + '-' + i + '-l\"" in h, "保守 EV 格没有 id"
    assert "getElementById('bk-ev-' + NS + '-' + idx + '-' + i + '-' + pair[0])" in h, \
        "刷新函数没按同一模式取格子"


def test_the_two_renderers_do_not_share_an_id_namespace() -> None:
    """🚨 2026-09-01 实测的真 bug:活页面上重复 id **66 个**。

    标准模式的卡索引 `_SPCALC.preds`、杯赛/市场模式的卡索引 `_CUPMKT.preds`,
    **两套 idx 都从 0 开始**,而 EV 格的 id 原本只有 `bk-ev-{idx}-…` ⇒ 撞号。
    `getElementById` 只返回 DOM 里第一个 ⇒ 在杯赛卡片上手填竞彩 SP,更新的是
    **标准模式那张卡**(数字写到了别的比赛上),而杯赛卡自己永远停在 `--`。

    ⚠️ 这条**不能**写成「id 字符串里有 NS」——那种断言在两边都传 'sp' 时照样绿。
    判据必须是「两个挂载点传的命名空间**不同**」。
    """
    h = _html()
    import re
    calls = re.findall(r"_bkHtml\(pr, idx(?:, '([a-z]+)')?\)", h)
    # 三块板 = 三个**独立的 0 基索引空间**:_SPCALC.preds / _CUPMKT.preds /
    # _MKTPRED_CARDS。任意两个共用命名空间就会再撞一次号。
    assert len(calls) >= 3, f"_bkHtml 挂载点少于 3 个(着陆页那张卡漏挂?):{calls}"
    assert all(calls), f"有挂载点没传命名空间:{calls}"
    assert len(set(calls)) == len(calls), f"有挂载点共用命名空间 {calls} ⇒ id 还是会撞"
    # 两条重算路必须各自带上**自己那个**命名空间
    for fn, sel, ns in (("_spcalcRecalc", ".spcalc-sp", "sp"),
                        ("_cupRecalc", ".cupsp", "cup")):
        body = h[h.index("function " + fn):][:2500]
        assert sel in body, f"{fn} 里没有它自己的选择器 {sel}"
        assert f"}}), '{ns}');" in body, f"{fn} 没把命名空间 '{ns}' 传给 _bkEvRefresh"


def test_the_ev_columns_survive_a_phone_screen() -> None:
    """🚨 owner 报的「多书商参考看板没有 EV 值」的真因(实测,不是猜)。

    375px 手机宽度下量出来:面板容器 264px · 表格 392px ·
    EVₑ 格 328→394 · EVₗ 格 394→459,视口只到 375
    ⇒ **最后两列恰好就是那两列 EV,整个被挤出屏幕右侧**,而容器 overflow-x
    是 visible ⇒ 连横滑都够不到。

    ⛔ 判据是「EV 两列**不带** `bk-opt`」而不是「有 `bk-opt` 这个类」——
    后者在有人顺手给 EV 列也打上标时照样绿,而那正好把 bug 修回去。
    """
    h = _html()
    i = h.index("function _bkHtml(")
    body = h[i:h.index("function _bkEvRefresh(", i)]
    # 1. 被裁掉的必须正好是那三列可推导的
    for col in ("poly_sp", "bk_low", "bk_spread"):
        th = [ln for ln in body.splitlines() if f"t('{col}')" in ln and "<th" in ln]
        assert th and all("bk-opt" in ln for ln in th), f"{col} 表头没打 bk-opt"
    # 2. 🚨 EV 两列**绝不能**被裁
    for ln in body.splitlines():
        if "bk-ev-" in ln:
            assert "bk-opt" not in ln, f"EV 格被打上了 bk-opt(窄屏会消失):{ln.strip()}"
    # 3. 横滚兜底:表格外面有 .bk-scroll
    assert "<div class=\"bk-scroll\"><table" in body, "表格没有横滚容器"
    assert "</table></div>" in body, "横滚容器没闭合"


def test_the_narrow_screen_rule_does_not_depend_on_the_tailwind_cdn() -> None:
    """⛔ 窄屏裁列**故意用原生 @media**,不用 Tailwind 的 `hidden sm:table-cell`。

    全站 @media 数原本是 **0** —— 响应式**全靠 cdn.tailwindcss.com**。owner 在墙内,
    CDN 死掉的那天,靠 Tailwind 类做的修复会跟着一起失效,而症状和现在一模一样
    (EV 列消失),排查会从头再来一遍。
    """
    h = _html()
    style = h[h.index("<style>"):h.index("</style>")]
    assert "@media" in style and ".bk-opt" in style, "窄屏规则不在页面自带的 <style> 里"
    assert ".bk-scroll" in style, ".bk-scroll 不在原生 CSS 里"
    # 不许用 Tailwind 断点类来做这件事
    body_after_style = h[h.index("</style>"):]
    assert "sm:table-cell" not in body_after_style and "md:table-cell" not in body_after_style, \
        "用 Tailwind 断点类做窄屏裁列 ⇒ CDN 挂了就跟着失效"


def test_the_spread_is_always_shown_not_only_when_wide() -> None:
    """离散必须**常显**在 <summary> 行。

    窄屏下表里那一列被 `bk-opt` 裁掉了,若 summary 还沿用旧的「≥3pp 才显示」,
    紧盘面上这个数就彻底看不到 —— 而「共识紧不紧」正是这个面板存在的理由。
    """
    h = _html()
    i = h.index("function _bkHtml(")
    body = h[i:h.index("function _bkEvRefresh(", i)]
    # 🚨 空包弹抓到过一次假绿:我原本断言「没有 `warm ?`」——而把条件换个写法
    #    (`maxSp >= 3 ?`)就绕过去了。**断言变量名 = 语法代理测语义属性。**
    #    判据必须是行为:那一行**在拼上离散之前不能有任何条件**。
    lines = [ln.strip() for ln in body.splitlines() if "maxSp.toFixed" in ln]
    assert len(lines) == 1, f"summary 里拼离散的行应恰好 1 条,实际 {len(lines)}"
    ln = lines[0]
    before = ln.split("maxSp.toFixed")[0]
    assert "?" not in before, f"离散被条件包住了 ⇒ 紧盘面上窄屏会彻底看不到它:{ln}"
    assert ln.startswith("+ ' \\u00b7 ' + t('bk_spread')"), f"离散不是无条件拼上去的:{ln}"


# ── join 层(2026-09-01 抽出 `team_match` 后新增)──────────────────────────
def test_a_match_with_many_rows_still_resolves(tmp_path, monkeypatch) -> None:
    """🚨 回归:`book_snapshots` 是 **append-only**,同一场比赛有多行(线态变了就再写)。

    我第一版把唯一性闸写成 `len(cands) != 1` —— 数的是**行数**而不是**不同的比赛**
    ⇒ 任何被抓过两次的场次一律被拒。实测后果:**英冠 2→0、日职 5→0**,
    原本能用的两个联赛全废。

    ⭐⭐ 而**总数反而从 17 涨到 24**(别的联赛刚补进来)——**聚合量把回归盖住了**,
    是逐联赛那张表才看见的。同 memory `first-match-is-not-the-population`
    「聚合量不是指纹」。⇒ 唯一性判据必须先按队名对**折叠**,再判唯一。
    """
    from nutmeg.v4.api import routes
    _write(tmp_path, _books(), captured_at="2026-09-01T08:00:00+00:00")
    _write(tmp_path, _books(pin=(2.20, 3.35, 3.50)), captured_at="2026-09-01T12:00:00+00:00")
    conn = sqlite3.connect(tmp_path / "obs.db")
    assert conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0] == 2, "夹具没造出多行"
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred()
    routes._attach_book_consensus([p])
    assert p.bk_consensus is not None, "同一场多行就解析不出 —— 唯一性闸又数成行数了"
    assert p.bk_captured_at == "2026-09-01T12:00:00+00:00", "没取最新那行"


def test_the_join_survives_long_vs_short_names(tmp_path, monkeypatch) -> None:
    """⭐ 承重:Odds API 用**全称**、盘面用 AF **短名**,join 必须过 `team_match`。

    裸 `_norm_team` 时实测 12 场英冠只通了 1 场(West Ham 那场碰巧两侧都短)。
    """
    from nutmeg.v4.api import routes
    from nutmeg.v4.observation.book_snapshots import record_book_snapshot
    record_book_snapshot(tmp_path / "obs.db", match_date="2026-09-01",
                         home_team="Lincoln City", away_team="Blackburn Rovers",
                         books=_books())
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred(home_team="Lincoln", away_team="Blackburn", league="ENG_CHAMPIONSHIP")
    routes._attach_book_consensus([p])
    assert p.bk_consensus is not None, "全称↔短名对不上 —— join 没走 team_match"


def test_a_league_with_no_odds_api_sport_is_marked_not_silent(tmp_path, monkeypatch) -> None:
    """⚠️「这项赛事永远不会有」和「今天还没抓到」必须分开。

    不分开的话 owner 会一直等一个不会来的东西(日联赛杯/意大利杯/德国杯
    在 Odds API 上根本没有对应 sport,同 JPN_J2/荷乙缺 key)。
    """
    from nutmeg.v4.api import routes
    _write(tmp_path, _books())
    monkeypatch.setattr(routes, "_observation_db_path", lambda: str(tmp_path / "obs.db"))
    p = _pred(league="JPN_LEAGUE_CUP")
    routes._attach_book_consensus([p])
    assert p.bk_unavailable is True and p.bk_consensus is None
    q = _pred(league="ENG_CHAMPIONSHIP")
    routes._attach_book_consensus([q])
    assert q.bk_unavailable is False, "有 sport_key 的不该被标成无源"


def test_the_shared_matcher_is_used_by_both_consumers() -> None:
    """⛔ 一处定义:`polymarket_match` 与共识 join 必须用**同一套**判据。

    2026-09-01 一天之内两个消费方各踩一次同一个病(全称 vs 短名)⇒
    复制第三份就是平行入口。`polymarket_match` 按原名转发,行为不变。
    """
    from nutmeg.v4.data import polymarket_match as pm
    from nutmeg.v4.data import team_match as tm
    assert pm._core is tm._core and pm._resolve is tm._resolve
    assert pm._prefix_extra is tm._prefix_extra


# ── 「刷新盘口」接线(2026-09-01)──────────────────────────────────────────
#
# owner 的问题:「现在的多书商参考怎么保证数据源是新鲜的,用『刷新盘口』吗?」
# 此前**不是** —— 唯一写入方是 `closing_odds` cron。接上之后必须钉死两件事:
# 它是**零额外配额**的,且**不会**被 60s 轮询变成每分钟 39 次的读写。

def _event(home="West Ham", away="Wolves", when="2026-09-01T14:00:00Z"):
    def _bk(key, h, d, a):
        return {"key": key, "markets": [{"key": "h2h", "outcomes": [
            {"name": home, "price": h}, {"name": away, "price": a},
            {"name": "Draw", "price": d}]}]}
    return {
        "home_team": home, "away_team": away, "commence_time": when,
        "bookmakers": [_bk("pinnacle", 2.10, 3.40, 3.60),
                       _bk("betfair_ex_eu", 2.05, 3.50, 3.70),
                       _bk("williamhill", 2.08, 3.45, 3.65),
                       _bk("unibet_fr", 2.12, 3.38, 3.55),
                       _bk("marathonbet", 2.09, 3.42, 3.62)],
    }


def test_a_cached_request_with_no_ttl_never_goes_live(tmp_path, monkeypatch) -> None:
    """🚨 「零额外配额」这条论断的**地基**,单独钉死。

    `refresh=False` **不等于「只读缓存」**:`_request` 的判据是
    `cf.exists() and not refresh and fresh_enough`,文件不在 / TTL 过期时它会直接
    fall through 去**发真请求**。所以采集器必须用 `refresh=False + ttl_seconds=None`
    且**在一次成功拉取之后**调用 —— 三者缺一,省下来的就变成花出去的。
    见 [[odds-api-serving-path-overspend]]:额度真凶历来是服务路径,不是 cron。
    """
    from nutmeg.v4.data.sources import odds_api
    endpoint, params = "sports/soccer_epl/odds", {
        "regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"}
    cf = odds_api._cache_path(endpoint, params, tmp_path)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps([_event()]), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("发出了真请求 —— 这就是一次配额消费")
    monkeypatch.setattr(odds_api, "_client", _boom)
    body = odds_api._request(endpoint, params, cache_dir=tmp_path,
                             refresh=False, ttl_seconds=None)
    assert isinstance(body, list) and body[0]["home_team"] == "West Ham"


def test_the_capture_only_ever_asks_the_cache(tmp_path, monkeypatch) -> None:
    """采集器打到 `_request` 的那组参数,必须正好是上面那条证明过安全的组合。

    ⚠️ 断言打在 `_request` 这一层而不是 `fetch_book_lookup` 那一层 —— 变异打在哪
    一层,断言就得打在哪一层:patch 掉 `fetch_book_lookup` 的话,「有人偷偷传了
    refresh=True」这个变异照样绿。
    """
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation.book_snapshots import capture_books_for_sport
    seen: list[dict] = []

    def _fake(endpoint, params, *, cache_dir=None, refresh=False, ttl_seconds=None):
        seen.append({"refresh": refresh, "ttl": ttl_seconds, "params": dict(params)})
        return [_event()]
    monkeypatch.setattr(odds_api, "_request", _fake)

    n = capture_books_for_sport(tmp_path / "obs.db", "soccer_epl")
    assert n == 1, f"该写入 1 条,实际 {n}"
    assert seen, "根本没去问 —— 这条测试什么也没证明"
    assert all(c["refresh"] is False for c in seen), f"发了 refresh=True:{seen}"
    assert all(c["ttl"] is None for c in seen), f"带了 TTL(过期即真消费):{seen}"
    # 同一个缓存键 = 和 Pinnacle 那次拉取共用文件,零增量的另一半
    assert {c["params"]["markets"] for c in seen} == {"h2h,totals"}, seen


def test_the_capture_stores_the_original_spelling(tmp_path, monkeypatch) -> None:
    """⚠️ 存**原始拼法**,不是 lookup 的归一键。

    归一后名字丢了信息(`Lincoln City` → `lincolncity`),而消费方 join 时会自己
    再归一一次;存归一版等于把 `team_match` 的四级判据废掉一半。
    """
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation.book_snapshots import capture_books_for_sport
    monkeypatch.setattr(odds_api, "_request",
                        lambda *a, **k: [_event(home="Lincoln City", away="Wolves")])
    capture_books_for_sport(tmp_path / "obs.db", "soccer_efl_champ")
    conn = sqlite3.connect(tmp_path / "obs.db")
    home, = conn.execute("SELECT home_team FROM book_snapshots").fetchone()
    conn.close()
    assert home == "Lincoln City", f"存成了 {home!r} —— 归一键把原名弄丢了"


def test_the_capture_never_raises(tmp_path, monkeypatch) -> None:
    """⛔ 参照层坏了绝不许拖垮调用方:收盘线是 CLV 地基,盘面刷新是 owner 临场在用。"""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation.book_snapshots import capture_books_for_sport

    def _boom(*a, **k):
        raise RuntimeError("Odds API 挂了")
    monkeypatch.setattr(odds_api, "_request", _boom)
    assert capture_books_for_sport(tmp_path / "obs.db", "soccer_epl") == 0


def test_the_refresh_hook_requires_all_three_conditions() -> None:
    """🚨 接线的那个 `if` 必须同时卡三条 —— 少任何一条都是一个真损失:

      · `oa_ok`         少了它 ⇒ Pinnacle 那次失败时缓存文件可能不存在 ⇒ **真消费**;
      · `_pulled_live`  少了它 ⇒ 面板每 60s 轮询,13 联赛 × 3 天 = **39 次/分钟**
                        的重复读盘+去重写;
      · `snapshot_db`   少了它 ⇒ `record_line_history=false` 的只读调用方
                        (snapshot_board cron)会开始写库。

    🚨 **2026-09-03 第二条换了名字也换了理由**(原 `league_oa_refresh` = 「这次请求
    要求刷新」)。实测那个判据把每天 4 次**已经付过钱**的 cron 拉取全挡在门外
    (`daily_predict` 3×/天 × ~33 sport、`daily_odds` 1×/天 × 13 联赛),
    后果是面板共识的中位年龄 **43.4 小时**。新判据是「这个 sport 刚刚**真被拉过**」
    (`odds_api.was_last_odds_pull_live`),它同样挡得住被动轮询 —— 因为
    **缓存命中不记账**(那条由 `test_book_consensus_p0.py` 的
    `test_cache_hit_must_not_record` 钉住,别删)。

    ⚠️ 用 AST 而不是 grep:字符串断言在有人把 `and` 改成 `or` 时照样绿。
    """
    import ast
    src = (REPO / "apps/api/src/nutmeg/v4/cli/ingest_odds.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    def _has(n):
        return "capture_books_for_sport" in ast.dump(n)
    hooks = [n for n in ast.walk(tree)
             if isinstance(n, ast.If) and _has(n)
             # ⚠️ ast.walk 连**外层**的 `if use_odds_api:` / `if sport_key:` 一起数
             #    ⇒ 只保留最内层那个(body 里没有别的也含调用的 if)
             and not any(isinstance(st, ast.If) and _has(st) for st in n.body)]
    assert len(hooks) == 1, f"接线点应恰好 1 个,实际 {len(hooks)}"
    test = hooks[0].test
    assert isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And), \
        "闸不是 and —— 换成 or 就等于没闸"
    names = {n.id for n in ast.walk(test) if isinstance(n, ast.Name)}
    assert names == {"oa_ok", "_pulled_live", "snapshot_db"}, \
        f"三条件不全或多了别的:{names}"


def test_there_is_exactly_one_capture_entry_point() -> None:
    """⛔ cron 和盘面刷新必须走**同一个函数**。

    平行入口不会被用,只会**分裂口径** —— 两处各自演化,某天一处修了另一处没修,
    而症状是「有时有数据有时没有」。见 [[grep-the-repo-before-declaring-it-missing]]。
    """
    src = {f: (REPO / "apps/api/src/nutmeg/v4" / f).read_text(encoding="utf-8")
           for f in ("observation/closing_odds.py", "cli/ingest_odds.py")}
    for f, s in src.items():
        assert "capture_books_for_sport" in s, f"{f} 没走共享入口"
        assert "record_book_snapshot" not in s, f"{f} 仍在直接调底层写入 ⇒ 又是一份平行实现"


def test_the_landing_tab_shows_the_panel_too() -> None:
    """🚨 CONFIRMED:挂了面板的容器**全在 `tab-upcoming`(默认隐藏)里**。

    着陆 tab 是 `tab-today`,上面那张卡由 `_mktPredCardHtml` 画,吃的是**同一次**
    cup-market 回包(`renderMarketPred(body.predictions)`),服务端 bk_* 早就挂满了
    —— 只是前端没渲。⇒ owner 不切 tab 就一张也看不到。
    """
    h = _html()
    body = _js_functions()["_mktPredCardHtml"]
    assert "_bkHtml(pr, idx, 'mkt')" in body, "着陆页那张卡没挂多书商面板"
    up = h.index('id="tab-upcoming"')
    for cid in ("jc-bettable-spcalc", "today-spcalc-list", "cupmkt-list"):
        assert h.index(f'id="{cid}"') > up, f"{cid} 不在 tab-upcoming 里了,这条测试的前提变了"


# ── ⓘ 说明弹窗(2026-09-03:橙字块 → summary 行的 ⓘ)────────────────────────
def test_the_disclaimer_moved_into_an_info_popup_on_the_summary_line() -> None:
    """免责文案从表格下方的橙字块,改成 `<summary>` 行末的 ⓘ 弹窗。

    ⭐ **位置是有讲究的**:这一层是**唯一**说明「不参与判闸/排序/串关」的地方,
    而它已经在两层折叠里(联赛组 + 本 details)。若把它收进弹窗**又留在表格下方**,
    就变成三层才看得到。挂到**常显的 summary** 上,省了竖向空间(实测桌面 −36px
    / −19%)**而且更好找**。

    实测(活页面,375px):点击区 12×17 → 24×20;弹窗 343/375 装得下;无横向滚动。
    """
    js = _html()
    # ⭐ 用本文件既有的 `_js_functions()`(按顶层 `}` 切),⛔ 别自己截固定字符窗口 ——
    #    我第一版截 3000 字符,而新加的决策注释把 `</summary>` 推出了窗口,当场假红。
    body = _js_functions()["_bkHtml"]
    # ① 橙字块没了
    assert "b45309" not in body, "表格下方那块橙字还在 —— 省不出空间"
    # ② ⓘ 在 summary 里(必须在 '</summary>' 之前)
    assert "</summary>" in body, "人口非平凡:切出来的函数体必须真含 summary"
    head = body[:body.index("</summary>")]
    assert "showInfo(" in head and "\\u24d8" in head, "ⓘ 不在 summary 行里"
    # ③ 🚨 承重:必须 stopPropagation —— 否则点 ⓘ 会顺手把整个 details 折起来
    assert "stopPropagation" in head, (
        "ⓘ 没挡住冒泡 ⇒ 点它会 toggle 掉 details,面板当场折叠")
    # ④ 复用既有弹窗,⛔ 不造第二套
    assert "function showInfo(" in js


def test_the_disclaimer_still_says_it_never_gates() -> None:
    """⛔ 换了载体,那句话本身不许弄丢 —— 它是这一层唯一的红线声明。"""
    js = _html()
    # 🚨 必须钉在 **`bk_disclaimer` 的文案里**,不能只查全文有没有这几个字 ——
    #    `不参与判闸` 在本文件里还出现在两条**无关注释**中(模型/市场背离那条,
    #    以及 `_bkHtml` 自己的决策注释)。第一版查全文,空包弹「把文案里那句删掉」
    #    照样绿,因为注释把它顶住了。
    for lang, must in ((1, "不参与判闸"), (2, "never gates")):
        blocks = [ln for ln in js.splitlines() if "bk_disclaimer" in ln or must in ln]
        # 取 bk_disclaimer 定义之后、下一个键之前的那段
        i = js.index("bk_disclaimer:", 0 if lang == 1 else js.index("bk_disclaimer:") + 10)
        seg = js[i:i + 1600]
        assert must in seg, f"红线声明从 bk_disclaimer 文案里消失了({must!r})"
    # 人口非平凡:两处 bk_disclaimer(中/英)都必须存在,否则上面的切片是空的
    assert js.count("bk_disclaimer:") == 2, "bk_disclaimer 不再是两处(中/英)"
