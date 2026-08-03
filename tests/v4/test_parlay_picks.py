"""构造器每档只出**两张**票,而且第二张不是「第二名」(2026-08-03)。

## 为什么砍

owner 问「一天出这么多推荐有必要吗」。量了一下,**那 5 行根本不是 5 个选项**:

    组合按 ∏(1+evLo) 排序,而这个乘积对候选池单调 ⇒ top-k 从池顶堆起
      2串  5 行 10 个腿位 → 只有 4.3 条不同的腿,第 1 条腿在 81% 的行里
      3串                 → 5.1 条,94%
      4串  5 行 20 个腿位 → **6.0 条,97%** ← 第一条腿倒了,5 行一起死

**而且名次不预测 ROI**(#1 在任何一档都不是最好的):

    2串  #1 −12.5 / #2 −4.7 / #3 −10.6 / #4 −22.6 / #5 −17.0
    3串  #1 −25.2 / #2 −13.9 / #3 −38.9 / #4 **+17.0** / #5 −25.6

误差 ±10~65pp ⇒ 这些差全不显著。**而「不显著」正是重点**:排成 1..5 传达了一个
测量上不具备的精度。同「EV 是排除器不是排序器」,只是这次显形在票的层面。

⇒ 改成「**主选 + 与主选零重叠的备选**」:两行都是真的不同的注,且不共命。

## ⚠️ 备选**不是更好的票**

实测 2串 −22.8%±10.1 / 3串 −4.3%±25.0 / 4串 +25.3%±65.9 —— 和主选分不出好坏。
它唯一的价值是**不跟主选一起死**。本文件的断言只钉「零重叠」这个结构性质,
**不钉任何「它更好」的性能声明** —— 那个我测不出来。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

#: 经验随机腿基线(2026-08-03 实测,取代旧的解析值)。
#: ⚠️ SE 按**比赛日**聚类,不是按重抽次数 —— 200 次重抽共享同一天的赛果,
#: 当独立样本会把 SE 缩小 1.5-1.7 倍(0.34→0.58pp)。
EMPIRICAL_RANDOM = {1: -0.127, 2: -0.252, 3: -0.319, 4: -0.447}
#: 旧的解析值 (1/1.1294)^k−1 —— 假设抽水在三腿均摊,而实测不是(热门腿吃 60%)。
RETIRED_ANALYTIC = {1: -0.115, 2: -0.216, 3: -0.306, 4: -0.385}


def _js() -> str:
    return DASH.read_text(encoding="utf-8")


def _fn(name: str, src: str | None = None) -> str:
    """抠一个顶层函数/常量声明的源码(配对花括号)。"""
    js = src or _js()
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


def _run(body: str) -> str:
    src = "\n".join(_fn(a) for a in ("function _parlayCombos", "function _parlayPicks"))
    r = subprocess.run(["node", "-e", src + "\n" + body],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


_MK = ("const mk=(i,ev)=>({key:'L'+i,label:'L'+i,sp:2.0,ev,evLo:ev,pr:{league:'LG'+i}});"
       "const pool=[8,7,6,5,4,3].map((v,i)=>mk(i+1,v/100));")


# ------------------------------------------------------------ 结构


def test_never_returns_more_than_two_rows() -> None:
    """行数是**结构**不是参数 —— 断言真实行为,不断言常量。

    ⚠️ 本条写过一版是 `_PARLAY_SHOW == 2`。全面审查时发现改成 main+alt 之后
    那个常量**一处都没被引用** —— 于是那条断言在钉一个不影响行为的数字,
    删掉常量代码照跑、测试却会红。「检查和它的前提对不上」的又一个变体:
    这次前提(常量在起作用)在我写断言的当下就已经不成立了。
    常量已删,改成从池子实际跑一遍看返回几行。
    """
    for k in (2, 3, 4):
        out = _run(_MK + f"console.log(_parlayPicks(pool, {k}).length);")
        assert int(out) <= 2, f"{k} 串返回了 {out} 行"
    assert "_PARLAY_SHOW = " not in _js(), "假旋钮又回来了(行数是结构不是参数)"


def test_the_alt_shares_no_leg_with_main() -> None:
    """⭐ 承重:备选的**全部**价值就是零重叠。共用一条腿它就没有存在意义。"""
    for k in (2, 3):
        out = _run(_MK + f"""
        const p = _parlayPicks(pool, {k});
        const a = new Set(p[0].legs.map(l => l.key));
        console.log(p.length + '|' + p.map(c => c.role).join(',') + '|'
          + (p[1] ? p[1].legs.filter(l => a.has(l.key)).length : -1));""")
        n, roles, shared = out.split("|")
        assert n == "2" and roles == "main,alt", out
        assert shared == "0", f"{k} 串备选和主选共用了 {shared} 条腿"


def test_no_disjoint_alt_means_one_row_not_a_filler() -> None:
    """⛔ 承重:凑不出零重叠的备选时**只出主选**,不拿第 2 名充数。

    拿第 2 名充数正是这次要去掉的东西 —— 它 81-97% 和主选共用腿,
    看起来像第二个选项,实际是同一注。「宁可少一行,不要一行假的」。
    """
    out = _run(_MK + """
      const tiny = [8,7,6,5].map((v,i) => mk(i+1, v/100));
      console.log(_parlayPicks(tiny, 3).length + ',' + _parlayPicks(pool, 4).length);""")
    assert out == "1,1", f"池不够时没有降到 1 行,得到 {out}"


def test_main_is_still_the_argmax() -> None:
    """砍行数不该动选票规则 —— 主选仍是 ∏(1+evLo) 最大的那张。"""
    out = _run(_MK + """
      const p = _parlayPicks(pool, 2);
      console.log(p[0].legs.map(l => l.key).sort().join('+'));""")
    assert out == "L1+L2", out


def test_combos_still_returns_the_full_ranked_list() -> None:
    """`_parlayCombos` 保持「返回全部、已排序」—— 截断的责任在 `_parlayPicks`。

    两件事分开:枚举+排序是一个纯函数,挑哪两张是展示策略。
    合在一起会让「改展示策略」不得不动枚举逻辑。

    ⚠️ 语法断言写过两版都太宽:先是 `"slice(0, _PARLAY_SHOW)" not in body`
    (焊死字面量,换个写法就瞎),再是 `".slice(" not in body`(**误伤
    `cur.slice()` 那个数组拷贝** —— 那是枚举本身要用的)。
    ⭐ 本会话第三次用**语法代理**去测**语义属性**(前两次:`filter(` 当 EV 地板、
    「恰好三档」正则当常数值)。教训一致:**先写行为断言,语法断言只当补充,
    而且要贴着那个具体写法**。截断的写法是 `.slice(0` / `.slice(N`,拷贝是 `.slice()`。
    """
    body = _fn("function _parlayCombos")
    assert ".slice()" in body, "本测试假设枚举器用 cur.slice() 拷贝;写法变了请更新"
    import re as _re
    trunc = _re.findall(r"\.slice\(\s*[^)\s]", body)
    assert not trunc, f"枚举器里塞回了截断 {trunc} —— 截断的责任在 _parlayPicks"
    # ⭐ 承重的是这条:行为上必须返回**全部** C(6,2)=15 个组合
    out = _run(_MK + "console.log(_parlayCombos(pool, 2).length);")
    assert int(out) == 15, f"C(6,2)=15,得到 {out}"


# ------------------------------------------------------------ 基线常数


def test_random_baseline_is_the_measured_one_not_the_analytic() -> None:
    """⭐ 承重:随机腿基线必须是**实测**的。

    旧值 (1/1.1294)^k−1 假设抽水在三条腿上均摊 —— 而我们实测过它不是
    (热门腿吃 60% 抽水)。真跑一遍,随机比解析线**更差** 1.2-6.2pp
    ⇒ 旧尺子**低估**了构造器自己的净提升。
    """
    m = re.search(r"const _PARLAY_RANDOM +ic?= *\{([^}]*)\}", _js()) or \
        re.search(r"const _PARLAY_RANDOM +\= *\{([^}]*)\}", _js())
    assert m, "_PARLAY_RANDOM 不见了"
    got = {int(k): float(v) for k, v in re.findall(r"(\d+): *(-?[\d.]+)", m.group(1))}
    assert got == EMPIRICAL_RANDOM, f"随机基线不是实测值:{got}"
    for k, v in RETIRED_ANALYTIC.items():
        assert got[k] != v, f"{k} 串又退回了解析值 {v}"


def test_random_baseline_carries_its_own_error_bar() -> None:
    """基线是估计量不是常数 —— 不显示 SE 会让人以为它是精确的。"""
    js = _js()
    assert "_PARLAY_RANDOM_SE" in js, "随机基线没有 SE"
    m = re.search(r"const _PARLAY_RANDOM_SE *= *\{([^}]*)\}", js)
    se = {int(k): float(v) for k, v in re.findall(r"(\d+): *([\d.]+)", m.group(1))}
    assert set(se) == {1, 2, 3, 4} and all(v > 0 for v in se.values()), se
    assert "_PARLAY_RANDOM_SE[k]" in js, "SE 没渲染到小节标题"


# ------------------------------------------------------------ 文案


def test_the_ui_explains_why_there_is_no_ranking() -> None:
    """⛔ 少显示了东西必须说破。而且要说的是**为什么** ——
    「5 行不是 5 个选项」和「名次不预测 ROI」是两个独立的理由,缺一个都不完整。"""
    js = _js()
    for key in ("pb_main", "pb_alt", "pb_rank_hdr", "pb_rank_note"):
        assert f"{key}:" in js, f"i18n 缺 {key}"
    zh = js[js.index("pb_rank_note:"):][:3000]
    assert "97%" in zh, "没写 4 串 5 行共用第一条腿的比例"
    assert "名次不预测" in zh, "没写名次不携带信息"
    assert "不是更好的票" in zh, "没声明备选并不更优 —— 会被读成推荐"
    assert "不显著" in zh, "没说破那些 ROI 差都在噪声里"


def test_roles_are_rendered_as_labels_not_numbers() -> None:
    js = _js()
    assert "pb_main' : 'pb_alt'" in js or "pb_main':'pb_alt'" in js, "行没有角色标签"
    assert "c.role === 'main'" in js


def test_fe_version_format_intact() -> None:
    routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    assert re.search(r'_FE_VERSION = "(nutmeg-v\d+-[a-z0-9-]+)"', routes)


def test_every_leg_count_has_its_i18n_key_in_both_languages() -> None:
    """⚠️ 小节标题用的是**动态键** `t('pb_' + k + 'x')` —— 静态搜索看不见它。

    `t()` 的回落是 `本地 || 中文 || 键名本身`,所以缺键不会崩,会在界面上
    渲染出裸的 `pb_5x` 字样。不崩 ≠ 没坏:将来加 5 串时忘了补键,
    只有肉眼能发现。这条替代肉眼。
    """
    js = _js()
    assert "t('pb_' + k + 'x')" in js, "动态键的构造方式变了,本测试的前提失效"
    cut = js.index("pb_1x:            'single (reference)'")   # 英文块起点锚
    zh, en = js[:cut], js[cut - 400:]
    for k in (1, 2, 3, 4):
        assert f"pb_{k}x:" in zh, f"中文缺 pb_{k}x"
        assert f"pb_{k}x:" in en, f"英文缺 pb_{k}x"


# ------------------------------------------------------- 档位标(纯显示)


def test_parlay_legs_show_their_tier_but_selection_ignores_it() -> None:
    """⭐ 承重:档位在串关腿行上**可见**,但在选池/排序里**不可读**。

    这两件事必须同时成立,少一半都错:
    · 只可见不可读 = 现状(对的):甜区与边缘 σ_EV 实测相等(4.6% vs 4.6%,
      CI 重叠,逐桶符号 3:4:1)⇒ 没有理由给边缘腿加门槛,见
      test_parlay_tier_weighting 的那批实测(24 条规则 0 条过闸)。
    · 只可读不可见 = 把「档位加权」从后门放回来。
    · 都不可见 = owner 2026-08-03 问的那个知情缺口:边缘腿占池 20.3%,
      但票面上看不出这张 3 串里装了几条。
    """
    js = _js()
    assert "_tierChip(l.tier)" in js, "串关腿行没挂档位标"
    assert "_tierChip(b1.tier)" in js, "1 串参考行没挂档位标(同一份信息不该只给串关)"
    for fn in ("function _parlayPool", "function _parlayPicks", "function _parlayCombos"):
        assert "tier" not in _fn(fn), f"{fn} 读了 tier —— 选择/排序不许看档位"


def test_tier_badge_and_colour_have_a_single_source() -> None:
    """徽章与配色只许有一份 —— 两处各存一份,改了一处另一处会**静默保持旧色**。"""
    js = _js()
    assert js.count("sweet: '🟢'") == 1, "🟢 映射出现多次(_evRelTag 与 _tierChip 该共用)"
    assert js.count("_TIER_BADGE[") >= 2 and js.count("_TIER_COLOR[") >= 2, (
        "共享常量没被两处同时使用")


def test_unknown_tier_renders_nothing_rather_than_garbage() -> None:
    """`tier` 可能是 null(P 不在 (0,1))。回落必须是**空**,不是 `undefined甜区`。"""
    src = "\n".join(_fn(a) for a in (
        "const _TIER_BADGE", "const _TIER_COLOR", "function _tierChip"))
    stub = "function t(k){return {rel_edge:'边缘',rel_edge_hint:'h'}[k]||k;}"
    r = subprocess.run(
        ["node", "-e", src + "\n" + stub +
         "\nconsole.log([null, undefined, 'bogus', 'edge']"
         ".map(x => JSON.stringify(_tierChip(x) === '' ? '' : 'CHIP')).join(','));"],
        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '"","","","CHIP"', r.stdout
