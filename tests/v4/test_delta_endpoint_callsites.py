"""δ 端点前端调用点的**分母**护栏(2026-08-17)。

## 为什么有这个文件

`c7034c4` 修「手填卡漏传 league」时,我用了一条计数断言:

    grep -c 'league: pr && pr.league' dashboard.html   →  3

看起来很严谨,它甚至当场救过一次场(我以为 2 处、它说 3 处)。**但它数的是
「我修了几处」** —— 模式就是修复本身的写法。**分母(存在几处)从来没有被建立。**
真实数字是 4:`_cupManRefreshDerived` 从头到尾没进过那个 grep 的视野,因为它
根本没被修过,所以不匹配修复的写法。

后果:前三个调用点算对的让球板,**下一次页面加载就被第四个覆盖回 10 倍带宽**
(`_UNCAL_SE=0.078` 地板 vs 覆盖内 `0.0078`),而且 `_cupManSave` 会把坏板写回
localStorage ⇒ 粘住。owner 08-16 报的那张西甲卡症状会原样复发。

⭐ **计数断言只有在分母独立于修复时才有判别力。** 这个文件建立分母。

## 三层,各自能被单独打红

1. `test_callsite_set_is_pinned` —— 枚举**全部** fetch 调用点,和钉住的集合逐字比。
   新增任何形态的调用点 ⇒ 红。这是分母本身。
2. `test_every_inline_body_carries_league` —— 就地字面量 body 必须含 league。
3. `test_upstream_builders_carry_league` —— body 由上游构造器产出的,构造器必须含。

## ⭐ 为什么这里的语法断言是**直接**的,不是代理

本仓有一条纪律:「语法代理测语义属性」是反模式(`filter(` 当 EV 地板、`.slice(`
当截断)。那些例子里,语法和语义之间隔着一层推理。

**这里没有那层。** 出事的属性逐字就是「这个 fetch 的 body 对象里有没有 `league`
这个键」—— 它本身就是语法事实。但两个额外要求仍然成立:

* **提取器必须自检**(`test_extractor_actually_finds_bodies`)—— 我今天用 12 行窗口
  数 market-handicap 时得到 2 个假阴性(body 在上游 `built.body` 构造,窗口看不见)。
  一个静默返回 0 的提取器会让全部断言恒绿。
* **空包弹焊进测试**(`test_checker_rejects_a_body_with_league_removed`)—— 拿真实
  body 抠掉 league,断言检查器**拒绝**它。没有这条,以上全部可能是恒真式。
  (08-16 我就交付过一个恒真验收:`_SCOPE_STATS` 在新进程里恒为 0。)

## 边界:这里**不**断言运行时后果

「每次页面加载会重打端点」「坏板写回 localStorage」是**浏览器内**主张,本文件
不验(没有浏览器)。它只钉住「body 里有没有那个键」。运行时那半由
`test_e2e_playwright.py` 覆盖,且今天没有为此新增用例 —— 明写,不假装。
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

import pytest

_HTML = pathlib.Path(__file__).resolve().parents[2] / (
    "apps/api/src/nutmeg/v4/api/static/dashboard.html")

#: 会返回 `handicap_lines`(即穿过 δ 范围闸)的**计算型**端点。
#: ⚠️ 这是手工清单 —— `test_endpoint_list_matches_server` 拿服务端路由对账,
#:    所以新端点开始出让球线时这个清单会被打红,而不是静默漏掉。
_DELTA_ENDPOINTS = ("market-reprice", "market-handicap")

#: **分母。** {(端点, 函数名): body 形态}
#:   'inline'         —— body 是 fetch 里的就地字面量 ⇒ 查那个字面量
#:   'local'          —— body 是同函数内的局部变量 ⇒ 查该函数源码
#:   'upstream:<fn>'  —— body 由别处构造 ⇒ 查那个构造器
#:
#: 🚨 改这张表 = 你新增/删除了一个会穿过 δ 闸的前端调用点。**请说清楚为什么。**
#:
#: ⚠️ 2026-08-17 自我更正:我第一版把 `_todayRecRecord` 写成 `inline` —— 它其实是
#:    `local`(`const body = {...}` 在同函数内)。我是拿今早那个「fetch 行往下 12 行」
#:    的粗扫结果填的表,而那个窗口**看不到 body 在上游构造**。
#:    ⇒ 表填错了会让护栏假红,而假红最后会被删掉。所以有 `test_body_shape_matches_table`
#:      —— 它拿实际扫到的形态和这张表对账,**表本身也是被检查的对象**。
_CALLSITES: dict[tuple[str, str], str] = {
    ("market-reprice", "_cupManualReprice"):     "inline",
    ("market-reprice", "_spcalcManualReprice"):  "inline",
    # 2026-08-17 补:这一个是 c7034c4 漏掉的第 4 个,也是本文件存在的原因。
    ("market-reprice", "_cupManRefreshDerived"): "inline",
    ("market-reprice", "_pendPinApply"):         "inline",
    ("market-handicap", "_todayRecRecord"):      "local",
    ("market-handicap", "_cupHcRecord"):         "inline",
    # 这两个共用 `_mrevBuildBody`(手动反推计算器)。
    # ⚠️ 该构造器**故意**在「算一遍」时送 'MANUAL' 而在「记一笔」时送下拉值 ——
    #    见 `test_mrev_builder_sends_a_sentinel_not_a_real_league`,那是**已知的
    #    潜伏形状**,不是本护栏要修的东西。
    ("market-handicap", "manualReverseCalc"):    "upstream:_mrevBuildBody",
    ("market-handicap", "manualReverseRecord"):  "upstream:_mrevBuildBody",
}


def _src() -> str:
    return _HTML.read_text(encoding="utf-8")


#: 字符串/模板字面量 + 注释 —— 它们内部的括号不能参与计数。
_MASKABLE = re.compile(
    r"`[^`]*`|'[^'\n]*'|\"[^\"\n]*\"|/\*.*?\*/|//[^\n]*", re.S)


def _strip_literals(s: str) -> str:
    """把字符串/模板/注释的**内容**抹掉,只为让括号计数可靠。

    🚨 **必须保长。** 我的第一版写 `re.sub(..., '""', s)` —— 变长替换 ⇒ 后面
    所有索引错位 ⇒ `_fn_source` 把函数体从中间切断,node 拿到半截语法错误。
    (而且那个错误长得像「JS 有 bug」而不是「我的提取器有 bug」。)
    ⇒ 逐字符替换成同长度的 `_`,首尾定界符保留。

    ⚠️ 注释也必须抹:`// …(纯计算、零额度、无 DB),把贴回的旧` 这类中文注释里
    的全角括号不影响计数,但 `/* ... { ... */` 会。
    """
    def blank(m: re.Match[str]) -> str:
        t = m.group(0)
        return t[0] + "_" * (len(t) - 2) + t[-1] if len(t) >= 2 else t
    return _MASKABLE.sub(blank, s)


def _balanced_slice(text: str, start: int) -> str:
    """从 `start` 起吃一个表达式:深度回到 0 时遇 `,` 或多余的 `}`/`)` 即止。"""
    masked = _strip_literals(text)
    depth = 0
    for k in range(start, len(text)):
        ch = masked[k]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return text[start:k]
            depth -= 1
        elif ch == "," and depth == 0:
            return text[start:k]
    return text[start:]


def _enclosing_fn(lines: list[str], idx: int) -> str | None:
    """从第 idx 行往上找最近的 `function NAME` / `async function NAME`。"""
    for j in range(idx, max(-1, idx - 200), -1):
        m = re.match(r"\s*(?:async\s+)?function\s+(\w+)\s*\(", lines[j])
        if m:
            return m.group(1)
    return None


def _fetch_call_text(lines: list[str], idx: int) -> str:
    """从 fetch 那一行起,按括号平衡吃到调用结束,返回整段文本。"""
    buf, depth, started = [], 0, False
    for j in range(idx, min(len(lines), idx + 60)):
        buf.append(lines[j])
        for ch in _strip_literals(lines[j]):
            if ch in "([{":
                depth += 1
                started = True
            elif ch in ")]}":
                depth -= 1
        if started and depth <= 0:
            break
    return "\n".join(buf)


def _callsites_found() -> list[tuple[str, str, str]]:
    """扫出**实际存在**的调用点,返回 [(端点, 函数名, body 表达式), ...]。

    🚨 **必须是 list 不是 dict。** 第一版返回 dict[(端点,函数名)] —— 空包弹③
    (在 `_cupManRefreshDerived` 里塞第二个不带 league 的 fetch)**没打红**,
    因为两个调用点键相同、后者把前者覆盖掉了 ⇒ 集合没变。
    ⭐ 分母键必须**每个调用点唯一**,否则数出来的是「有几个函数」不是「有几处调用」。
      —— 同一个错误今天犯了两次:先是数「我修了几处」,再是数「有几个函数」。
    """
    lines = _src().split("\n")
    out: list[tuple[str, str, str]] = []
    for i, ln in enumerate(lines):
        if "fetch(" not in ln:
            continue
        ep = next((e for e in _DELTA_ENDPOINTS if e in ln), None)
        if ep is None:
            continue
        fn = _enclosing_fn(lines, i)
        assert fn is not None, f"L{i+1} 的 fetch 找不到外层函数名 —— 提取器需要更新"
        text = _fetch_call_text(lines, i)
        # 🚨 第一版用 `(.+?)(?:,\s*\n|\n)` —— 只吃到**第一个换行**,而这些 body
        #    全是多行对象字面量、`league` 在最后一行 ⇒ 6 个调用点全判成「没有」。
        #    假红比假绿更贵,而且这种假红会让人删掉护栏。⇒ 改成括号平衡切片。
        m = re.search(r"\bbody:\s*", text)
        assert m is not None, f"{fn} 的 fetch 里没找到 body: —— 提取器需要更新"
        out.append((ep, fn, _balanced_slice(text, m.end()).strip()))
    return out


def _by_key() -> dict[tuple[str, str], str]:
    """{(端点, 函数名): body} —— 顺带断言**每个键只出现一次**。

    一个函数里出现第二个打同端点的 fetch ⇒ 这里红,而不是静默折叠。
    """
    found = _callsites_found()
    keys = [(ep, fn) for ep, fn, _ in found]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, (
        f"🚨 这些函数里有**多于一个**打 δ 端点的 fetch:{sorted(dupes)}\n"
        f"   本文件的分母键是 (端点, 函数名),重复键会互相覆盖 ⇒ 新调用点变不可见。\n"
        f"   请把那个函数拆开,或把本文件的键改成能区分它们的形式。")
    return {(ep, fn): body for ep, fn, body in found}


def _fn_source(name: str) -> str:
    """把某个 JS 函数的源码抠出来(括号平衡),给上游构造器用。"""
    src = _src()
    m = re.search(rf"\n(?:async\s+)?function {re.escape(name)}\s*\(", src)
    assert m, f"dashboard.html 里找不到函数 {name}"
    body = src[m.start():]
    masked = _strip_literals(body)          # ⚠️ 保长,否则 end 会切错(见 _strip_literals)
    assert len(masked) == len(body), "掩码改变了长度 —— 索引会错位"
    depth, started, end = 0, False, len(body)
    for k, ch in enumerate(masked):
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                end = k + 1
                break
    assert started, f"{name} 的函数体没找到 `{{` —— 提取器需要更新"
    return body[:end]


# ────────────────────────────────────────────────────────────────────
# 0. 提取器自检 —— 没有这条,下面全部可能恒绿
# ────────────────────────────────────────────────────────────────────

def test_extractor_actually_finds_bodies():
    """⭐ 前提自检:提取器必须真的找到东西,且每个都拿到了 body 表达式。

    今天我用「fetch 行往下 12 行」的窗口数 market-handicap,得到 **2 个假阴性**
    (`manualReverseCalc`/`manualReverseRecord` 的 body 是上游的 `built.body`,
    窗口里看不到 league)。一个返回 0 的提取器和「全都合规」长得一模一样。
    """
    found = _callsites_found()
    assert len(found) == len(_CALLSITES), (
        f"扫到 {len(found)} 个调用点,表里登记了 {len(_CALLSITES)} 个 —— "
        f"提取器坏了,或有未登记的新调用点")
    for ep, fn, body in found:
        assert body, f"({ep}, {fn}) 的 body 表达式是空的 —— 提取器坏了"


def test_checker_rejects_a_body_with_league_removed():
    """⭐⭐ **空包弹焊进测试** —— 证明检查器有判别力。

    拿一条真实的就地字面量 body,抠掉 `league`,断言 `_body_has_league` 判它**不合格**。
    没有这条,`test_every_inline_body_carries_league` 可能是个恒真式 ——
    而 08-16 我确实交付过一个恒真验收(`_SCOPE_STATS` 在新进程里恒为 0)。
    """
    good = _by_key()[("market-reprice", "_cupManRefreshDerived")]
    assert _body_has_league(good), "基线就不合格 —— 空包弹失去意义,先修基线"
    mutated = re.sub(r",?\s*league:\s*[^,}]+", "", good)
    assert mutated != good, "变异没生效(没找到 league 那一段)—— 空包弹是哑弹"
    assert not _body_has_league(mutated), "🚨 检查器对『league 被删掉』无感 —— 它是恒真的"


def _body_has_league(body_expr: str) -> bool:
    """就地字面量 body 里有没有 `league` 这个**键**。"""
    return re.search(r"\bleague\s*:", body_expr) is not None


# ────────────────────────────────────────────────────────────────────
# 1. 分母
# ────────────────────────────────────────────────────────────────────

def test_callsite_set_is_pinned():
    """**这是分母。** 新增/删除任何 δ 端点调用点 ⇒ 这条红。

    ⚠️ 和 `grep -c '<修复的写法>'` 的关键差别:这里的模式是 **fetch 到那个端点**,
    与「有没有被修过」完全无关 ⇒ 一个从没被修过的调用点也会被数进来。
    """
    found = set(_by_key())
    pinned = set(_CALLSITES)
    assert found == pinned, (
        f"δ 端点调用点集合变了。\n"
        f"  新增(未审查!): {sorted(found - pinned)}\n"
        f"  消失: {sorted(pinned - found)}\n"
        f"⇒ 新调用点必须显式登记进 _CALLSITES 并说明 body 形态。")


# ────────────────────────────────────────────────────────────────────
# 2/3. 每个调用点都得把 league 送出去
# ────────────────────────────────────────────────────────────────────

def test_body_shape_matches_table():
    """⭐ **表本身也要被检查。** 实际扫到的形态 vs `_CALLSITES` 声明的形态。

    我第一版把两个 `local`/`upstream` 站点填成了 `inline` ⇒ 6 条断言假红。
    「检查的前提没人检查」是本仓的老形状 —— 这条就是检查那个前提。
    """
    mism = []
    for key, body in _by_key().items():
        declared = _CALLSITES.get(key)
        actual = "inline" if body.lstrip().startswith(("JSON.stringify({", "{")) else "indirect"
        if declared == "inline" and actual != "inline":
            mism.append(f"{key[1]}: 表说 inline,实际 body 是 `{body[:40]}`")
        if declared != "inline" and actual == "inline":
            mism.append(f"{key[1]}: 表说 {declared},实际是就地字面量")
    assert not mism, "形态表和代码对不上:\n  " + "\n  ".join(mism)


@pytest.mark.parametrize("key", sorted(_CALLSITES), ids=lambda k: k[1])
def test_every_callsite_sends_league(key):
    """每个调用点都必须把 league 送出去 —— 按各自的形态去它该在的地方查。"""
    shape = _CALLSITES[key]
    if shape == "inline":
        where, src = "fetch 里的就地字面量 body", _by_key()[key]
    elif shape == "local":
        where, src = f"{key[1]} 函数体内构造的 body", _fn_source(key[1])
    else:
        builder = shape.split(":", 1)[1]
        where, src = f"上游构造器 {builder}", _fn_source(builder)
    assert _body_has_league(src), (
        f"{key[1]} 打 /{key[0]} —— {where} 里没有 `league` 键。\n"
        f"⇒ 服务端 `_delta_in_scope(None)` = False ⇒ 让球下界吃 `_UNCAL_SE=0.078` "
        f"地板(覆盖内的 10 倍)、点估少扣 δ₋₁ 的 4.6pp。\n"
        f"实际前 200 字:{src[:200]}")


# ────────────────────────────────────────────────────────────────────
# 4. 服务端对账 —— 手工清单会过期
# ────────────────────────────────────────────────────────────────────

def test_endpoint_list_matches_server():
    """`_DELTA_ENDPOINTS` 是手工写的。这条拿**服务端路由**对账。

    判据 = handler 源码里直接出现 δ 引擎的名字。
    ⇒ 哪天有第三个端点开始出让球线,这条红,而不是本文件静默漏掉它。

    ⚠️ 我第一版用「response_model 里有没有 `handicap_lines`」—— **错的**:
    `MarketHandicapResponse` 回的是**单条**请求线的 `market_implied_p`/`ev_per_unit`,
    根本没有 `handicap_lines` 字段 ⇒ 判据把它漏掉了,而它正是会写台账的那个。
    ⭐ 又一次「拿一个看起来相关的语法特征代替真正的属性」。真正的属性是
      **handler 有没有调 δ 引擎**,那就直接查它。

    ⚠️ 边界:只查**直接**引用。经由 `_market_reverse_handicap_probs` 这类 helper
    间接到达 δ 的端点(`/recommend/single` 等)不在本文件范围 —— 它们的 league
    由 schema **必填**保证(漏传 422),是 fail-loud 的那一半,见
    `test_schema_league_optionality_is_pinned`。**明写,不假装覆盖了。**
    """
    import inspect

    from fastapi import FastAPI

    from nutmeg.v4.api.routes import router as v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    needles = ("implied_handicap_lines", "_market_handicap_lines", "c1_leg_lower_bounds")
    emitting = set()
    for r in app.routes:
        fn = getattr(r, "endpoint", None)
        if fn is None:
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if any(n in src for n in needles):
            emitting.add(r.path.rsplit("/", 1)[-1])
    assert emitting == set(_DELTA_ENDPOINTS), (
        f"直接调 δ 引擎的端点集合变了:服务端={sorted(emitting)} "
        f"本文件={sorted(_DELTA_ENDPOINTS)}")


def test_schema_league_optionality_is_pinned():
    """哪些请求模型**必填** league、哪些允许 None —— 钉住,别偷偷放松。

    ⚠️ 这两个策略今天是**不一致**的,而且是偶然不一致(没有文档说明为什么):
      · `MarketHandicapRequest.league: str`        —— 必填,漏传直接 422(fail-loud)
      · `MarketRepriceRequest.league: str | None`  —— 可选,漏传 200 + 10 倍带宽
    可选那个是 c7034c4 **故意**的:老前端(缓存的旧 tab)不传时按方案 A 保守处理,
    而不是 422 掉整张卡 —— owner 红线是「显示层降级不能 422 掉整张卡」。
    ⇒ 本条不主张统一,只主张**不许无声改变**。
    """
    from nutmeg.v4.api.schemas import MarketHandicapRequest, MarketRepriceRequest
    assert MarketHandicapRequest.model_fields["league"].is_required() is True
    assert MarketRepriceRequest.model_fields["league"].is_required() is False


# ────────────────────────────────────────────────────────────────────
# 5. 已知潜伏形状 —— 记下来,别假装它不存在
# ────────────────────────────────────────────────────────────────────

def test_mrev_builder_sends_a_sentinel_not_a_real_league():
    """🚨 手动反推计算器:「算一遍」送 `'MANUAL'`,「记一笔」才送下拉值。

        league: record ? leagueSel : 'MANUAL',

    注释写的理由是「league 只在记一笔时用于自动结算 join」—— 那在 δ 上线**之前**
    是对的。现在 `league` 多了一个身份:**判闸键**。⇒ 展示与落库用两个不同的 league。

    **今天数值差为 0**,因为 `mrev-league` 下拉的 8 个 option 无一在 δ 白名单里
    (下一条测试钉住这一点)。⇒ 这是潜伏形状,不是活 bug。
    ⛔ 所以这条测试**断言现状**而不是要求修复 —— 真正的雷在下拉表的内容,
       修法是那条测试红的时候一起处理。
    """
    src = _fn_source("_mrevBuildBody")
    assert "record ? leagueSel : 'MANUAL'" in src, (
        "`_mrevBuildBody` 的 league 表达式变了 —— 如果你修好了它,请删掉本测试;"
        "如果你换了别的写法,请确认「算一遍」和「记一笔」现在用同一个 league。")


def test_mrev_dropdown_has_no_delta_calibrated_league():
    """⭐ **真正的雷在这里。** 往 `mrev-league` 下拉里加一条白名单联赛 ⇒ 上一条的
    潜伏形状当场发作:同一张卡「算一遍」显示未校准带宽(0.156),「记一笔」按
    校准带宽(0.0156)入账,两者相差 10 倍。

    实测(2026-08-17,SP=2.45 的 −1 让负腿):MANUAL ⇒ EV +3.57% 不过闸;
    ESP_LA_LIGA ⇒ EV +38.02% 过闸并下注 ¥50。**同一副盘口。**
    """
    from nutmeg.v4.model.market_handicap import _delta_in_scope
    m = re.search(r'<select id="mrev-league".*?</select>', _src(), re.S)
    assert m, "找不到 mrev-league 下拉 —— 本测试的前提没了"
    opts = re.findall(r'<option value="([^"]+)"', m.group(0))
    assert opts, "下拉里一个 option 都没扫到 —— 提取器坏了"
    in_scope = [o for o in opts if _delta_in_scope(o)]
    assert not in_scope, (
        f"🚨 `mrev-league` 下拉里出现了 δ 覆盖内联赛 {in_scope} ——\n"
        f"   `_mrevBuildBody` 的 `record ? leagueSel : 'MANUAL'` 会让「算一遍」和\n"
        f"   「记一笔」用不同的 league(带宽差 10 倍)。**先修那一行,再加这个联赛。**")


# ────────────────────────────────────────────────────────────────────
# 6. 行为断言 —— 在 node 里跑**真的** shipped 函数
# ────────────────────────────────────────────────────────────────────

def test_cup_man_refresh_derived_actually_sends_league_over_the_wire():
    """⭐ 语法断言之外的那一层:把**真的** `_cupManRefreshDerived` 抠出来在 node 里跑,
    桩掉 fetch,看**实际发出去的 body**里有没有 league。

    为什么单独给它一条:它是 08-17 出事的那个,而且它是唯一一个会把结果
    **写回 localStorage** 的(`_cupManSave`)—— 坏值在这里会粘住,不是刷新一下就没了。
    """
    js = _fn_source("_cupManRefreshDerived")
    harness = f"""
const API = 'http://stub';
let sent = null;
globalThis.fetch = async (url, opt) => {{
  sent = {{ url, body: JSON.parse(opt.body) }};
  return {{ ok: true, json: async () => ({{ handicap_lines: [], p_home_1x2: 0.4,
            p_draw_1x2: 0.3, p_away_1x2: 0.3, onex_lo_home: 0.39,
            onex_lo_draw: 0.29, onex_lo_away: 0.29 }}) }};
}};
let saved = null;
function _cupManSave(pr, m) {{ saved = {{ pr, m }}; }}
{js}
const pr = {{ _manual: true, league: 'ESP_LA_LIGA', home_team: 'A', away_team: 'B' }};
const m  = {{ h: 2.34, d: 3.03, a: 3.64, o: 2.04, u: 1.85, line: 2.25 }};
_cupManRefreshDerived([[pr, m]], () => {{}}, true).then(() => {{
  console.log(JSON.stringify({{ body: sent && sent.body, saved: saved !== null }}));
}});
"""
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"node 跑挂了:\n{out.stderr}"
    got = json.loads(out.stdout.strip().split("\n")[-1])
    assert got["body"] is not None, "fetch 根本没被调用 —— 桩或函数体变了,断言会恒绿"
    assert got["body"].get("league") == "ESP_LA_LIGA", (
        f"🚨 实际发出去的 body 里 league={got['body'].get('league')!r} —— "
        f"服务端会按覆盖外处理。完整 body: {got['body']}")
    assert got["saved"], "没走到 `_cupManSave` —— 写回 localStorage 那条路没被覆盖到"
