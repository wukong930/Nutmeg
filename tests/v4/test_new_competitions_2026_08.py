"""解放者杯 / 欧超杯 / 沙职 —— 三个新注册赛事的行为护栏(2026-08-09 owner 点名)。

守的不是「常量等于某个值」,是**接错线时会静默烂掉的四条性质**。
三个赛事**故意**分别踩不同的坑,所以放在一个文件里对照着看。

⭐ 本文件最重要的一条是 `test_saudi_counts_as_a_domestic_league`:
我第一版把沙职塞进了 `CUP_COMPETITIONS`(因为那是「加赛事」的显眼入口),
它会同时踩两个真 bug —— `is_cup_competition()` 只看「在不在字典里」、不看
`competition_type`;`classify_league()` 的 `if s in CUP_COMPETITIONS: return
"excluded"` 先命中 ⇒ 沙职被从 δ 拟合的国内联赛人口里悄悄踢出去。
两处都**不报错**,只是数字悄悄变了 —— 正是本仓一直在防的那类。
"""
from __future__ import annotations

import datetime as dt

import pytest

from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS
from nutmeg.v4.data.competitions import CUP_COMPETITIONS, is_cup_competition
from nutmeg.v4.data.league_labels import classify_league
from nutmeg.v4.data.sources.api_football import (
    API_FOOTBALL_LEAGUE_IDS,
    season_for_date,
)

# 2026-08-18 补 KOR_FA_CUP —— 注册它的提交(`38ab5ad`)改了 9 个文件、
# **测试文件 0 个**(`grep -rn KOR_FA_CUP tests/` 当时是 0 命中),而 08-10 那批
# 给自己的三个赛事都补了这里的条目。⇒ 新赛事上线时两侧都没护栏。
NEW = ("COPA_LIBERTADORES", "UEFA_SUPER_CUP", "SAU_PRO_LEAGUE", "KOR_FA_CUP")


@pytest.mark.parametrize("code", NEW)
def test_each_new_competition_resolves_to_an_api_football_id(code: str) -> None:
    """没有 id ⇒ fixtures 拉不到 ⇒ 整个联赛静默不存在(不报错,只是空)。"""
    assert API_FOOTBALL_LEAGUE_IDS.get(code), f"{code} 没有 AF league id"


@pytest.mark.parametrize("code", NEW)
def test_each_new_competition_reaches_the_market_mode_board(code: str) -> None:
    """三个都不在训练集里 ⇒ **只能**走市场模式(Pinnacle 去vig 的 P)。

    漏了这一步的后果不是报错,是这些场次在面板上**根本不出现** ——
    标准模式没有它们的模型,市场模式又不认它们。
    """
    assert code in _CUP_MARKET_COMPETITIONS, f"{code} 不在市场模式集合里"


def test_saudi_counts_as_a_domestic_league() -> None:
    """🚨 承重。沙职是**国内俱乐部联赛**,必须和荷乙同待遇。

    空包弹:把 `"SAU_PRO_LEAGUE": 307` 从 `_DOMESTIC_LEAGUE_IDS` 挪进
    `CUP_COMPETITIONS`(我的第一版)⇒ 这条立刻红。
    """
    assert classify_league("SAU_PRO_LEAGUE") == "domestic"
    assert classify_league("SAU_PRO_LEAGUE") == classify_league("NED_EERSTE_DIVISIE")
    assert not is_cup_competition("SAU_PRO_LEAGUE")
    assert "SAU_PRO_LEAGUE" not in CUP_COMPETITIONS


@pytest.mark.parametrize("code", ("COPA_LIBERTADORES", "UEFA_SUPER_CUP", "KOR_FA_CUP"))
def test_the_two_cups_are_excluded_from_the_domestic_population(code: str) -> None:
    """反向对照:杯赛必须和欧冠同待遇,别混进 δ 的拟合人口。

    ⚠️ 2026-08-18 加入 `KOR_FA_CUP`(韩国**足总杯**)。它和沙职形成对照:
    同为「新注册的非欧洲赛事」,沙职是**国内联赛**(domestic)、韩国杯是**杯赛**
    (excluded)。两条断言并排放着,分类搞反时会立刻显形。
    """
    assert classify_league(code) == "excluded" == classify_league("UCL")
    assert is_cup_competition(code)


def test_libertadores_march_resolves_to_the_current_year() -> None:
    """🚨 日历年陷阱。解放者杯 2-11 月跑完一个日历年。

    漏进 `CALENDAR_YEAR_LEAGUES` 的话,3 月的比赛会按欧洲惯例算成 season=去年,
    AF 返回 **0 场** —— 和 WC 那条注释记的「整届世界杯静默消失」同族。
    ⭐ 断言的是**跨越分界线**(3 月 vs 8 月同年),不是某个字面量。
    """
    assert season_for_date(dt.date(2026, 3, 15), "COPA_LIBERTADORES") == 2026
    assert season_for_date(dt.date(2026, 8, 15), "COPA_LIBERTADORES") == 2026


def test_saudi_march_resolves_to_the_season_that_started_last_august() -> None:
    """反向对照:沙职 8 月–5 月跨年 ⇒ 欧洲惯例本来就对,**不该**进日历年集合。

    误加进去的话 3 月会算成 2026,而那个赛季在 AF 标的是 2025 ⇒ 同样 0 场。
    """
    assert season_for_date(dt.date(2026, 3, 15), "SAU_PRO_LEAGUE") == 2025
    assert season_for_date(dt.date(2026, 8, 15), "SAU_PRO_LEAGUE") == 2026


def test_a_competition_without_an_odds_api_key_still_gets_served() -> None:
    """欧超杯在 Odds API 的 175 个 sport 里**没有** key(2026-08-09 全表核过)。

    ⛔ 这里**故意不断言「它没有 key」** —— 那会在 Odds API 哪天加了这个 sport 时
    变成假红,而假红最后会被删掉(本仓「老误报的护栏会被删」那条)。
    断言的是真正重要的性质:**缺 key 不该把它挡在盘面外**(它靠 AF 镜像,
    那场实测 13 家含 Pinnacle)。
    """
    from nutmeg.v4.data.sources.odds_api import SPORT_KEYS

    assert "UEFA_SUPER_CUP" in _CUP_MARKET_COMPETITIONS
    assert "UEFA_SUPER_CUP" in API_FOOTBALL_LEAGUE_IDS
    # 有没有 key 都行;有 key 时必须是字符串,不能是 None/空串那种半吊子
    assert SPORT_KEYS.get("UEFA_SUPER_CUP", "x") != ""


# ── 2026-08-18 · 韩国杯专条 ────────────────────────────────────────────────

def test_korea_cup_march_resolves_to_the_current_year() -> None:
    """🚨 日历年陷阱(同解放者杯)。韩国足球 2–11 月跑完一个日历年。

    漏进 `CALENDAR_YEAR_LEAGUES` ⇒ 年初的 1/128~Round of 32 按欧洲惯例算成
    season−1。⭐ 断言**跨越分界线**(3 月 vs 8 月必须同年),不是某个字面量。
    """
    import datetime as dt

    from nutmeg.v4.data.sources.api_football import season_for_date
    assert season_for_date(dt.date(2026, 3, 15), "KOR_FA_CUP") == 2026
    assert season_for_date(dt.date(2026, 8, 19), "KOR_FA_CUP") == 2026
    # 反向对照:欧洲惯例的联赛在 3 月应落到 season−1(证明上面不是恒真)
    assert season_for_date(dt.date(2026, 3, 15), "EPL") == 2025


def test_korea_cup_has_no_odds_api_key_on_purpose() -> None:
    """⛔ **故意**没有 sport key —— `/v4/sports?all=true` 175 个全表 live 核过,
    韩国只有 `soccer_korea_kleague1`。

    猜一个不存在的 key 只会让 fetch 每次 404 当空处理(同欧超杯/荷乙/JPN_J2 先例)。
    ⇒ 本条钉的是「**留空是决定,不是遗漏**」。哪天 Odds API 真上了韩国杯,
      改这条并附上核查证据。
    """
    from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
    assert SPORT_KEYS.get("KOR_FA_CUP") is None


def test_korea_cup_is_reachable_from_both_name_tracks() -> None:
    """中英双轨都要认得它 —— 只加一轨 = 同一赛事按写法落进不同层。

    (`日乙` 就是这么活着的:`JPN_J2` 判 domestic、`日乙` 判 unknown,
     直到 2026-08-17 才补上。)
    """
    from nutmeg.v4.data.league_labels import canonical_league, classify_league
    assert canonical_league("KOR_FA_CUP") == "韩国杯"
    assert canonical_league("韩国杯") == "韩国杯"
    assert classify_league("KOR_FA_CUP") == classify_league("韩国杯") == "excluded"


def test_korea_cup_has_a_panel_chinese_name() -> None:
    """面板那份表是**另一份** —— 服务端加了修不了它。

    2026-08-18 实测:注册后它曾是 `_CUP_MARKET_COMPETITIONS` 全部成员里
    **唯一**没有面板中文名的 ⇒ 分组头直接印 `KOR_FA_CUP`。
    (完整分母护栏见 `test_league_zh_coverage.py`;这里留一个具名锚。)
    """
    import pathlib
    import re
    html = (pathlib.Path(__file__).resolve().parents[2]
            / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"const LEAGUE_ZH\s*=\s*\{(.*?)\n\};", html, re.S)
    assert m, "找不到 LEAGUE_ZH —— 提取器需要更新"
    assert re.search(r"KOR_FA_CUP\s*:\s*'韩国杯'", m.group(1)), \
        "面板 `LEAGUE_ZH` 里没有韩国杯 ⇒ 分组头会印生字符串"
