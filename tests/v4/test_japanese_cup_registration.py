"""日本两个杯赛的注册 —— 端到端钉死每一层(表驱动)。

    JPN_LEAGUE_CUP   日联赛杯   AF 101   2026-09-01 注册
    JPN_EMPEROR_CUP  日天皇杯   AF 102   2026-09-01 注册

## 为什么要这个文件

韩国杯那次注册**动了 9 个文件、0 个测试文件**(见 `test_new_competitions_2026_08.py`
开头的自我指认),结果面板印了一阵生字符串 `KOR_FA_CUP`。注册一项赛事要碰的表分散在
6 个文件里,其中**两处漏了会完全静默**:

  · `_CUP_MARKET_COMPETITIONS` 漏 ⇒ 端点照常返回 200 + 空名单,和「今天没有比赛」同形;
  · `CALENDAR_YEAR_LEAGUES` 漏 ⇒ AF 对年初轮次返 0 场,不报错(仓里已踩过 ≥4 次)。

⇒ 下面全是**行为断言**:调真函数看返回值,不查源码里有没有某个字符串。

## 加新杯赛时

往 `CUPS` 里加一行,六条断言自动覆盖。AF id **必须**有本地锚(fixture 或 leagues
catalog),⛔ 不许按名字搜 —— 「*League Cup*」在 AF 全表有 14 个。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: code → 注册事实。`rivals` = 必须区分开的**同名/邻近** AF id。
CUPS: dict[str, dict] = {
    "JPN_LEAGUE_CUP": {
        "cn": "日联赛杯",
        "af_id": 101,
        # AF 全表叫「*League Cup*」的 14 个 + 日本另两个杯赛
        "rivals": (48, 168, 185, 302, 360, 505, 508, 559, 738, 895, 898, 899,
                   1199, 871, 1156, 102, 548),
        "early_month": dt.date(2027, 3, 15),   # 档案 82% 在 2–4 月
        "synonym": ("日本联赛杯", "日联赛杯"),   # jingcai_vote 全称,2 行
    },
    "JPN_EMPEROR_CUP": {
        "cn": "日天皇杯",
        "af_id": 102,
        "rivals": (101, 548, 98, 99, 100),      # 日联赛杯 / 超级杯 / J1 / J2 / J3
        "early_month": dt.date(2027, 5, 20),   # 档案最早在 5 月
        "synonym": ("天皇杯", "日天皇杯"),      # crown_close_history 短名,7 场
    },
}


@pytest.mark.parametrize("code", sorted(CUPS))
def test_the_af_id_is_pinned_and_unambiguous(code: str) -> None:
    """AF id 有本地锚,且和每个易混 id 都不同。

    ⛔ 按名字搜必错:AF 全表叫「*League Cup*」的有 14 个(英 48 / 冰 168 / 苏 185 /
    阿联酋 302 / 埃及 895 / 泰国 898 …)。日本自己就有 101 J-League Cup、
    102 Emperor Cup、548 Super Cup 三个杯赛。
    """
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS
    from nutmeg.v4.data.sources.api_football import league_id

    want = CUPS[code]["af_id"]
    assert CUP_COMPETITIONS[code].api_football_id == want
    assert league_id(code) == want, "派生的合并 id 表没拿到它"
    assert want not in CUPS[code]["rivals"]


@pytest.mark.parametrize("code", sorted(CUPS))
def test_it_is_on_the_market_board_and_never_on_the_model_board(code: str) -> None:
    """⛔ 承重且**静默**:进错盘面不报错,只会拿 OOD 欧洲模型 P 当真值。"""
    from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS, _SP_CALC_LEAGUES

    assert code in _CUP_MARKET_COMPETITIONS, "漏了这行 ⇒ 端点返回健康的空名单"
    assert code not in _SP_CALC_LEAGUES, "杯赛进了 13 个欧洲训练联赛的模型盘"


@pytest.mark.parametrize("code", sorted(CUPS))
def test_both_name_tracks_agree_and_neither_says_domestic(code: str) -> None:
    """🚨 注册里**唯一会静默污染数据**的一条。

    `DOMESTIC_LEAGUES_CN` 是从 `_EN_TO_CN.values()` **减去** `_NON_DOMESTIC_CN`
    推导的 ⇒ 只补前者不补后者,杯赛会悄悄混进 δ 校准的国内联赛人口。
    数字会动,什么都不报错。
    """
    from nutmeg.v4.data.league_labels import (
        DOMESTIC_LEAGUES_CN,
        canonical_league,
        classify_league,
        is_domestic_club_league,
    )

    cn = CUPS[code]["cn"]
    assert canonical_league(code) == cn
    assert classify_league(code) == classify_league(cn), "两轨分类不一致"
    assert not is_domestic_club_league(code)
    assert not is_domestic_club_league(cn), "🚨 杯赛被当成国内联赛(δ 人口被污染)"
    assert cn not in DOMESTIC_LEAGUES_CN
    alias, canon = CUPS[code]["synonym"]
    assert canonical_league(alias) == canon, f"另一个源的写法 {alias!r} 归不到规范形"


@pytest.mark.parametrize("code", sorted(CUPS))
def test_the_calendar_year_flag_actually_changes_an_early_year_lookup(code: str) -> None:
    """⭐ 不断言「它在集合里」,而是**当场算一遍**取数用的 season。

    两个杯赛都在一个日历年内跑完(日联赛杯 2–11 月、天皇杯 5–12 月),而欧洲惯例
    会把年内早期的日期算成 season−1 ⇒ AF 返 0 场**且不报错**。
    """
    from nutmeg.v4.data.sources import api_football as af

    season_for = getattr(af, "season_for_date", None)
    if season_for is None:                       # pragma: no cover - 结构变了
        pytest.skip("season_for_date 不在了 —— 结构变化,重新钉")
    d = CUPS[code]["early_month"]
    assert season_for(d, code) == d.year, "年内早期轮次算成了上一季 ⇒ AF 会返 0 场"


def test_the_european_heuristic_is_not_globally_broken() -> None:
    """对照:上面那条改的必须是**这几个杯赛**,不是全局。"""
    from nutmeg.v4.data.sources.api_football import season_for_date

    assert season_for_date(dt.date(2027, 3, 15), "EPL") == 2026


@pytest.mark.parametrize("code", sorted(CUPS))
def test_the_panel_has_its_own_chinese_name(code: str) -> None:
    """服务端 `league_labels.py` 和面板 `dashboard.html` 是**两份同名不同用**的表。

    只加服务端 ⇒ 面板分组标题印生字符串(韩国杯 2026-08-18 实案)。
    """
    html = (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(encoding="utf-8")
    assert f"{code}: '{CUPS[code]['cn']}'" in html, "面板那份 LEAGUE_ZH 没有它"


@pytest.mark.parametrize("code", sorted(CUPS))
def test_it_is_excused_from_registry_coverage_rather_than_left_orphan(code: str) -> None:
    """杯赛没有固定赛季队表 ⇒ 进 OUT_OF_SCOPE,而不是 MARKET_MODE_LEAGUES。

    进错了会拿淘汰赛去做「队表 diff」,报出几十个假硬缺口 ⇒ 体检 exit 1。
    """
    from nutmeg.v4.cli.registry_coverage import (
        CRON_LEAGUES,
        MARKET_MODE_LEAGUES,
        OUT_OF_SCOPE,
    )

    assert code in OUT_OF_SCOPE
    assert OUT_OF_SCOPE[code].strip(), "排除理由不能是空串"
    assert code not in MARKET_MODE_LEAGUES
    assert code not in CRON_LEAGUES, "进 CRON_LEAGUES 会把缺 sport_key 从警告升成硬缺口"


def test_the_two_cups_are_never_collapsed_into_one() -> None:
    """⛔ 101 与 102 是**两项不同赛事**,任何一层都不能混。

    它们同国家、同类型、同为「杯」,中文只差一个字 —— 正是最容易被眼睛跳过的形状。
    """
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS
    from nutmeg.v4.data.league_labels import canonical_league

    a, b = CUP_COMPETITIONS["JPN_LEAGUE_CUP"], CUP_COMPETITIONS["JPN_EMPEROR_CUP"]
    assert a.api_football_id != b.api_football_id
    assert canonical_league("JPN_LEAGUE_CUP") != canonical_league("JPN_EMPEROR_CUP")
    # 赛制实测有别:日联赛杯有两回合(29 组赛季内重复),天皇杯纯单场淘汰(0 组)
    assert a.has_two_legged_ties is True
    assert b.has_two_legged_ties is False
