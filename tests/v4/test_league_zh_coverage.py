"""面板联赛中文名的**分母**护栏(2026-08-18)。

## 为什么

`38ab5ad` 注册韩国杯时,把 `KOR_FA_CUP → 韩国杯` 加进了**服务端**
`data/league_labels.py`。那份表是给 δ 人口分类 / 中文轨 join 用的。

**面板读的是另一份表** —— `dashboard.html` 里的 `LEAGUE_ZH`。
两份同名不同用,加一处 ⇒ **服务端绿、面板直接印生字符串 `KOR_FA_CUP`**。

实测:出事时它是 `_CUP_MARKET_COMPETITIONS` 全部 30 个成员里**唯一**没有中文名的。
`_lgGroupHtml`(分组头)和甜区榜行都走 `zhLeague(lg)`,所以 owner 在
「竞彩可投注」分组头上会直接看到 `KOR_FA_CUP`。

## ⭐ 分母

和 `test_league_label_tracks.TestEveryServedLeagueHasBothTracks` 同一个教训:
护栏的分母必须是「**我们实际会服务的全部联赛**」= 两块板的并集,
不是任一块。本会话已经在分母上栽过三次(计数断言数「我修了几处」、
调用点键把同函数第二个 fetch 折叠、老护栏只看标准板)。

## ⛔ 颜色不在本护栏范围

`leagueColor` 有显式回落 `|| '#64748b'`,而市场板 30 个里有 4 个本来就没颜色
(灰色是**既定状态**,不是缺陷)。⇒ 只钉中文名,不钉颜色。
"""
from __future__ import annotations

import pathlib
import re

_HTML = pathlib.Path(__file__).resolve().parents[2] / (
    "apps/api/src/nutmeg/v4/api/static/dashboard.html")


def _league_zh() -> dict[str, str]:
    s = _HTML.read_text(encoding="utf-8")
    m = re.search(r"const LEAGUE_ZH\s*=\s*\{(.*?)\n\};", s, re.S)
    assert m, "找不到 LEAGUE_ZH —— 提取器需要更新(不是代码变干净了)"
    return dict(re.findall(r"([A-Z_0-9]+)\s*:\s*'([^']+)'", m.group(1)))


def _served() -> list[str]:
    from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS, _SP_CALC_LEAGUES
    return sorted(set(_SP_CALC_LEAGUES) | set(_CUP_MARKET_COMPETITIONS))


def test_extractor_actually_finds_entries():
    """前提自检 —— 一个返回空表的提取器会让下面全部恒绿。"""
    d = _league_zh()
    assert len(d) >= 40, f"只扫到 {len(d)} 条 LEAGUE_ZH —— 提取器坏了"
    assert d.get("KOR_K_LEAGUE_1"), "抽样键取不到值 —— 正则没匹配到值那一半"


def test_every_served_league_has_a_panel_chinese_name():
    """🚨 每个会上盘面的赛事都必须有面板中文名。

    没有 ⇒ 分组头和甜区榜行直接印英文代码,owner 一眼就看见。
    """
    d = _league_zh()
    missing = [lg for lg in _served() if lg not in d]
    assert not missing, (
        f"🚨 这些赛事会上盘面,但 `LEAGUE_ZH` 里没有中文名:{missing}\n"
        f"   ⇒ `_lgGroupHtml` / 甜区榜会直接印生字符串。\n"
        f"   ⚠️ 服务端 `league_labels.py` 加了**修不了这个** —— 面板读的是另一份表。")


def test_korea_cup_specifically():
    """2026-08-18 的活例 —— 留个具名锚,回归时一眼认出。"""
    assert _league_zh().get("KOR_FA_CUP") == "韩国杯"


# ⛔ 这里原本还有一条 `test_panel_table_and_server_table_do_not_contradict`
# ——「两份表的中文名不许互相矛盾」。**写完一跑就被证伪,已删。**
#
# 实测差异(4 条,全部是**合理的显示变体**,不是矛盾):
#     SWE_ALLSVENSKAN 面板『瑞典超』· 服务端『瑞超』
#     JPN_J2          面板『日职乙』· 服务端『日乙』
#     USA_MLS         面板『美职联』· 服务端『美职』
#     UEL             面板『欧联』  · 服务端『欧罗巴』
# 面板那份是**给人看的显示名**,服务端那份是**竞彩缩写**(join 用)。两者本来就该
# 各自最优,没有任何 join 依赖面板表。
#
# ⭐ 删而不是加豁免:5 条豁免的清单会让这条测试退化成一张名单,而
#    「陈旧的豁免名单会掩护真缺口」是本仓当天刚记下的教训
#    (`DNK_SUPERLIGA` 靠老护栏的分母盲区活了三个月)。
#    **前提被证伪的测试该删掉,不是关小。**
