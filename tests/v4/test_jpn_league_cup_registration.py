"""日联赛杯(JPN_LEAGUE_CUP)注册 —— 端到端钉死四层(2026-09-01)。

## 为什么要这个文件

韩国杯那次注册**动了 9 个文件、0 个测试文件**(见 `test_new_competitions_2026_08.py`
开头的自我指认),结果面板印了一阵生字符串 `KOR_FA_CUP`。注册一项赛事要碰的表分散在
6 个文件里,而其中**两处漏了会完全静默**:

  · `_CUP_MARKET_COMPETITIONS` 漏 ⇒ 端点照常返回 200 + 空名单,和「今天没有比赛」同形;
  · `CALENDAR_YEAR_LEAGUES` 漏 ⇒ AF 对年初轮次返 0 场,不报错(仓里已踩过 ≥4 次)。

⇒ 下面全是**行为断言**:调真函数看返回值,不查源码里有没有某个字符串。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

CODE = "JPN_LEAGUE_CUP"
CN = "日联赛杯"
AF_ID = 101
REPO = Path(__file__).resolve().parents[2]


def test_the_af_id_is_pinned_and_unambiguous() -> None:
    """AF id=101,且**不是**那 13 个撞名的 League Cup 之一。

    锚 = 本地缓存 fixture 1567425(2026-09-02 Vanraure Hachinohe vs Tochigi City,
    league {id:101, name:'J-League Cup', country:'Japan'})。
    ⚠️ AF 全表叫「*League Cup*」的有 14 个(英 48 / 冰 168 / 苏 185 / 阿联酋 302 /
    爱尔兰 360 / 新加坡 505 / 南非 508 / 北爱 559 / 威尔士 738 / 埃及 895 /
    泰国 898 / 芬兰 899 / 香港 1199 / 英青年 871·1156)—— **按名字匹配会 13 路撞车**。
    日本另有 102 Emperor Cup(天皇杯)、548 Super Cup,也不能混。
    """
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS
    from nutmeg.v4.data.sources.api_football import league_id

    assert CUP_COMPETITIONS[CODE].api_football_id == AF_ID
    assert league_id(CODE) == AF_ID, "派生的合并 id 表没拿到它"
    for other in (48, 168, 185, 302, 360, 505, 508, 559, 738, 895, 898, 899,
                  1199, 871, 1156, 102, 548):
        assert AF_ID != other


def test_it_is_on_the_market_board_and_never_on_the_model_board() -> None:
    """⛔ 承重且**静默**:进错盘面不会报错,只会拿 OOD 欧洲模型 P 当真值。"""
    from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS, _SP_CALC_LEAGUES

    assert CODE in _CUP_MARKET_COMPETITIONS, "漏了这行 ⇒ 端点返回健康的空名单"
    assert CODE not in _SP_CALC_LEAGUES, "杯赛进了 13 个欧洲训练联赛的模型盘"


def test_both_name_tracks_agree_and_neither_says_domestic() -> None:
    """🚨 本次注册里**唯一会静默污染数据**的一条。

    `DOMESTIC_LEAGUES_CN` 是从 `_EN_TO_CN.values()` **减去** `_NON_DOMESTIC_CN`
    推导的 ⇒ 只补 `_EN_TO_CN` 不补 `_NON_DOMESTIC_CN`,一个跨 J1/J2/J3 的淘汰杯
    会悄悄混进 δ 校准的国内联赛人口。数字会动,什么都不报错。
    """
    from nutmeg.v4.data.league_labels import (
        DOMESTIC_LEAGUES_CN,
        canonical_league,
        classify_league,
        is_domestic_club_league,
    )

    assert canonical_league(CODE) == CN
    assert classify_league(CODE) == classify_league(CN), "两轨分类不一致"
    assert not is_domestic_club_league(CODE)
    assert not is_domestic_club_league(CN), "🚨 杯赛被当成国内联赛(δ 人口被污染)"
    assert CN not in DOMESTIC_LEAGUES_CN


def test_the_calendar_year_flag_actually_changes_an_early_year_lookup() -> None:
    """⭐ 不断言「它在集合里」,而是**当场算一遍**取数用的 season。

    实测竞彩档案 123 场的月份分布 2–11 月、12/1 月为零 ⇒ 日历年制;
    而年初(2–4 月)占档案 **82%** —— 漏了这条,那 82% 会按欧洲惯例算成 season−1,
    AF 返 0 场**且不报错**。
    """
    from nutmeg.v4.data.sources import api_football as af

    season_for = getattr(af, "season_for_date", None)
    if season_for is None:                       # pragma: no cover - 结构变了
        pytest.skip("season_for_date 不在了 —— 结构变化,重新钉")
    march = dt.date(2027, 3, 15)
    assert season_for(march, CODE) == 2027, "年初轮次算成了上一季 ⇒ AF 会返 0 场"
    # 对照:欧洲联赛在同一天必须仍是 2026,否则说明我改的是全局而不是这一个
    assert season_for(march, "EPL") == 2026


def test_the_panel_has_its_own_chinese_name() -> None:
    """服务端 `league_labels.py` 和面板 `dashboard.html` 是**两份同名不同用**的表。

    只加服务端 ⇒ 面板分组标题印生字符串 `JPN_LEAGUE_CUP`(韩国杯 2026-08-18 实案)。
    """
    html = (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(encoding="utf-8")
    assert f"{CODE}: '{CN}'" in html, "面板那份 LEAGUE_ZH 没有它"


def test_it_is_excused_from_registry_coverage_rather_than_left_orphan() -> None:
    """杯赛没有固定赛季队表 ⇒ 应进 OUT_OF_SCOPE,而不是 MARKET_MODE_LEAGUES。

    进错了会拿 128 队淘汰赛去做「队表 diff」,报出几十个假硬缺口 ⇒ 体检 exit 1。
    """
    from nutmeg.v4.cli.registry_coverage import (
        CRON_LEAGUES,
        MARKET_MODE_LEAGUES,
        OUT_OF_SCOPE,
    )

    assert CODE in OUT_OF_SCOPE
    assert OUT_OF_SCOPE[CODE].strip(), "排除理由不能是空串"
    assert CODE not in MARKET_MODE_LEAGUES
    assert CODE not in CRON_LEAGUES, "进 CRON_LEAGUES 会把缺 sport_key 从警告升成硬缺口"
