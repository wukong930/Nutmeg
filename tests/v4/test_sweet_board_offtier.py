"""2026-08-01 — 甜区 EV 榜:**先筛后排 → 先排后分区**。

## 病史

榜原来在 `_sweetLegs` 的 push 里直接 `if (_evRelTier(p) !== 'sweet') return`,
甜区外的腿在榜上**彻底不存在**。审计(13,031 场 / 38,511 腿 / fd Pinnacle 锚 +
比分硬闸门)发现:

    全库过 +5% 闸的腿 178 条,其中 **55 条(30.9%)在甜区外** —— 榜藏了三分之一。

藏它们的理由是「甜区更可信」。但那个差**没确立**:
    甜区内 123 条 ROI +8.1%±13.4% · 甜区外 55 条 −33.4%±26.0% · 差 41.5pp,**z=1.42**

⭐ 而且甜区自己也没确立:+8.1%±13.4% ⇒ **t=0.60**,与 0 一致。
用一个 z=1.42 的方向去执行「完全隐藏」,是把未确立的结论当既成事实。

榜自己的说明还写着「榜=扫描辅助,下注仍看 +5% 闸」—— 但若榜就是你扫的东西,
「仍看闸」等于挨张卡片手翻,那正是榜要替掉的活。

## 修法

甜区仍是**默认排序**(主区一行不变),甜区外的过闸腿降级成**可展开附区**。
⛔ 判闸、排序键、+5% 闸一律没动 —— 纯显示层。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _src() -> str:
    return DASH.read_text(encoding="utf-8")


def test_leg_builder_no_longer_filters_sweet_inline() -> None:
    """⭐ 核心回归:`_boardLegs` 的 push 里**不许**再有甜区早退。

    这一行就是「先筛后排」本身。它一旦回来,附区拿不到任何腿,而榜看起来
    完全正常 —— 又是一个静默失效,所以钉死在源码上。
    """
    src = _src()
    assert "function _boardLegs(" in src, "_boardLegs 不见了(重构请同步本测试)"
    body = src[src.index("function _boardLegs("):src.index("function _sweetLegs(")]
    assert "!== 'sweet') return" not in body, (
        "_boardLegs 里又出现了甜区早退 —— 甜区外的过闸腿会重新变成不可见")


def test_two_partitions_exist_and_are_disjoint_by_construction() -> None:
    """主区 = 甜区(不问过没过闸);附区 = 非甜区**且**已过闸。"""
    src = _src()
    assert "return _boardLegs(pr, idx, mode).filter(l => l.tier === 'sweet');" in src
    assert ("filter(l => l.tier !== 'sweet' && l.evLo >= 0.05)" in src), (
        "附区的条件变了 —— 它必须同时是「非甜区」和「已过闸」")


def test_off_sweet_section_is_rendered_and_collapsed_by_default() -> None:
    """降级 ≠ 隐藏:附区必须真的渲染出来,且默认折叠(不抢主区注意力)。"""
    src = _src()
    assert "offBody" in src and "${body}${offBody}" in src, "附区没接进榜的 HTML"
    m = re.search(r"const offBody = !offRows\.length \? '' : `\s*\n\s*<details([^>]*)>", src)
    assert m, "附区不是 <details>(折叠靠它)"
    assert " open" not in m.group(1), "附区默认展开了 —— 应当折叠"


def test_off_sweet_rows_carry_a_tier_chip() -> None:
    """附区每行必须自报档位,否则读者不知道自己在看非甜区的东西。"""
    src = _src()
    assert "function _tierChip(" in src
    assert "_tierChip(r.lg.tier)" in src, "附区行没贴档位徽章"
    for key in ("rel_edge", "rel_cold", "rel_chalk"):
        assert f"{key}:" in src, f"档位徽章要用的 i18n 键 {key} 不存在"


def test_icon_exists_in_the_sprite() -> None:
    """⚠️ sprite 里没有的图标 `IC()` 会渲染成**空 svg**,不报错。

    这版第一稿写的 `alert-triangle` 就不在 sprite 里 —— 页面照常渲染,只是
    图标位置空着。凡新用一个图标,先确认 symbol 在。
    """
    src = _src()
    for name in re.findall(r"IC\('([a-z-]+)'\)", src):
        assert f'<symbol id="ic-{name}"' in src, f"IC('{name}') 在 sprite 里没有对应 symbol"


def test_both_locales_have_the_new_keys() -> None:
    """新键必须中英都有 —— 缺一边会在那个语言下渲染成键名。"""
    src = _src()
    for key in ("sw_off_hdr", "sw_off_note"):
        assert src.count(f"{key}:") == 2, (
            f"{key} 出现 {src.count(f'{key}:')} 次,应当中英各 1 次")


def test_falsified_variance_claim_is_gone() -> None:
    """⭐ 旧文案断言「甜区 SP 放大最小、EV 估计最稳」—— **我们测过,是假的**。

    四档边界与 σ_EV 近乎正交(档内 1.44× / 跨界 1.02×):σ_EV 在边界上几乎不变。
    UI 不该把一个已推翻的结论当事实陈述。
    """
    src = _src()
    assert "SP 放大最小,EV 估计最稳" not in src, "已证伪的方差说法还留在 UI 上"
    assert "smallest SP amplification, most stable EV estimate" not in src
    assert "1.44" in src and "orthogonal" in src, "改后的文案没写清边界是手画的"


def test_gate_and_ranking_key_untouched() -> None:
    """⛔ 这次是**显示层**改动:判闸阈值和排序键一个都不许动。

    「+5% 闸是负筛选」只在 1X2 成立、让球盘未复现,我们明确定过不许据此改闸。
    """
    src = _src()
    assert "lg.evLo >= 0.05 ? '#059669'" in src, "绿灯阈值被改了"
    assert "legs.sort((a, b) => b.evLo - a.evLo)" in src, "排序键被改了(必须是判闸 EV)"
    assert "rows.sort((a, b) => b.best.evLo - a.best.evLo)" in src, "主区排序被改了"


def test_fe_version_bumped() -> None:
    """前端改动必须 bump,否则 service worker 端老页面不换。"""
    routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    m = re.search(r'_FE_VERSION = "([^"]+)"', routes)
    assert m and m.group(1) == "nutmeg-v118-fe-sweetboard-offtier", m and m.group(1)
