"""意乙 2025-26 名单的中文名 —— 以及**为什么这 7 条不是「用赛事身份钉」的**。

## 病史

`test_registry_coverage` 红了:意乙 20 队里 7 支(Arezzo / Ascoli / Avellino /
Benevento / Padova / Vicenza Virtus / Virtus Entella)在 `TEAM_NAME_ZH` 里没有
中文名。它们是 2025-26 升降级换的队,而字典是 V11 P1-FE#7 按 2024-25 名单写的。

## ⚠️ 「用赛事身份钉」在意乙**不存在**

三个带中文名的源全查过(2026-08-03):

    竞彩历史档案 12,914 场   意甲 1,353 · 意大利杯 19 · 意超杯 3 · **意乙 0**
    竞彩实盘捕获 17 联赛                                        **意乙 0**
    皇冠收盘史   58 联赛     意甲 488 · 意大利杯 · 意超杯 ·      **意乙 0**

**竞彩不卖意乙。** 没有可对的赛事,就没有身份可钉 —— 这不是数据缺口,是这个联赛
压根不在中文盘口的人口里。同一段里本来就有 9 支从没在竞彩出现过却有中文名的队
(桑普多利亚 / 南蒂罗尔 / 卡拉雷塞 / 曼托瓦 / 尤文图斯·斯塔比亚…),口径一致。

## 那为什么还敢填

⭐ **红线「绝不瞎猜队名」是为 join key 立的** —— 错映射 = 静默污染。这里不同:

  · 意乙没有竞彩盘 ⇒ 不存在可被污染的 join(反查键永远不会被意乙行命中)
  · 这是**显示名** —— 错了是卡片标签写错,肉眼可见、可改
  · 唯一真风险是**撞车**:中文名若已指向别的队,反转字典会造出错的 join key

所以填之前逐条撞车检查:7 条在 `TEAM_NAME_ZH` / `_ZH_OVERRIDES` / 竞彩档案 /
皇冠档案里**都没被占**(0 冲突)。本文件把那个检查固化下来。

## ⭐ 真正的机制风险:`setdefault` 让「一名多队」静默丢后来者

`_ZH_TO_EN` 是这么建的:

    for _en, _zh in TEAM_NAME_ZH.items():
        _ZH_TO_EN.setdefault(_zh, _en)      # ← 先到先得

字典里已有 **123 组**中文名对多个英文名 —— 绝大多数是同一支队的不同拼法
(AC Milan/Milan、Man United/Manchester United、Verona/Hellas Verona),那是有意的。
但这也意味着:**将来谁在我这 7 条之前插入一个同名条目,我的条目会被静默顶掉**,
而界面看起来一切正常(中文名照显示,只是反查指向了别人)。

所以下面钉的是**往返**而不是「存在」:`_ZH_TO_EN[中文] == 英文`。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: 2026-08-03 补的 7 条。改这里必须同步重跑撞车检查(见下面两个测试)。
SERIE_B_2025_26_ADDED = {
    "Arezzo": "阿雷佐",
    "Ascoli": "阿斯科利",
    "Avellino": "阿维利诺",
    "Benevento": "贝内文托",
    "Padova": "帕多瓦",
    "Vicenza Virtus": "维琴察",
    "Virtus Entella": "恩泰拉",
}


def test_the_seven_are_present() -> None:
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    for en, zh in SERIE_B_2025_26_ADDED.items():
        assert TEAM_NAME_ZH.get(en) == zh, f"{en} 的中文名不是 {zh}"


def test_each_one_round_trips_through_zh_to_en() -> None:
    """⭐ 承重:`_ZH_TO_EN` 用 `setdefault`(先到先得)。

    只断言「字典里有这条」是不够的 —— 若将来有人在更靠前的位置插入同一个中文名,
    我的条目会被**静默顶掉**:中文名照常显示,但反查指向别的队。往返才抓得住。
    """
    from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN
    for en, zh in SERIE_B_2025_26_ADDED.items():
        got = _ZH_TO_EN.get(zh)
        assert got is not None, f"{zh} 反查不到"
        assert _EN_OVERRIDES.get(got, got) == _EN_OVERRIDES.get(en, en), (
            f"{zh} 反查到了 {got},不是 {en} —— 有人在更前面插了同名条目,"
            f"setdefault 把我这条顶掉了")


def test_no_collision_with_the_jingcai_override_table() -> None:
    """`_ZH_OVERRIDES` 是竞彩专用补丁,和主字典撞名会让 join 指向两个方向。"""
    from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES
    clash = {zh: _ZH_OVERRIDES[zh] for zh in SERIE_B_2025_26_ADDED.values()
             if zh in _ZH_OVERRIDES}
    assert not clash, f"和竞彩 override 表撞名:{clash}"


def test_no_collision_in_the_chinese_odds_archives() -> None:
    """撞车检查的**数据侧**:这 7 个中文名在竞彩/皇冠档案里不属于别的队。

    档案不在 checkout 里就跳过 —— 但**跳过不等于通过**,所以显式 skip 而不是
    静默 return(与本项目「分不出没有和没去看的检查不算检查」同一条纪律)。
    """
    db = REPO / "data/v4_jingcai_history.db"
    if not db.exists():
        pytest.skip("竞彩历史档案不在这个 checkout 里 —— 未做数据侧撞车检查")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    problems = {}
    for en, zh in SERIE_B_2025_26_ADDED.items():
        owners: set[str] = set()
        for tbl, zh_col, en_col in (
            ("jingcai_odds_history", "home_zh", "home_team"),
            ("jingcai_odds_history", "away_zh", "away_team"),
            ("crown_close_history", "home_zh", "home_team"),
            ("crown_close_history", "away_zh", "away_team"),
        ):
            owners |= {r[0] for r in conn.execute(
                f"SELECT DISTINCT {en_col} FROM {tbl} WHERE {zh_col} = ?", (zh,)) if r[0]}
        if owners - {en}:
            problems[zh] = sorted(owners)
    assert not problems, f"中文名在档案里属于别的队:{problems}"


def test_serie_b_roster_is_fully_reachable() -> None:
    """整份 2025-26 名单可达 —— 这是 `test_registry_coverage` 那条的意乙切片,
    留在这里是为了红的时候**指名道姓**(那条只会吐一串英文名)。
    """
    from datetime import UTC, datetime

    from nutmeg.v4.data.sources.api_football import (
        ApiFootballError,
        _cache_path,
        fetch_teams_for_league_season,
        league_id,
        season_for_date,
    )
    from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN
    season = season_for_date(datetime.now(UTC).date(), "ITA_SERIE_B")
    cf = _cache_path("/teams", {"league": league_id("ITA_SERIE_B"), "season": season},
                     REPO / "data/external/api_football")
    if not cf.exists():
        pytest.skip("意乙队表未缓存 —— 未做名单可达性检查")
    try:
        teams = fetch_teams_for_league_season("ITA_SERIE_B", season)
    except ApiFootballError:
        pytest.skip("意乙队表读取失败")
    reachable = {_EN_OVERRIDES.get(en, en) for en in _ZH_TO_EN.values()}
    miss = sorted(t["team"]["name"] for t in teams
                  if t["team"]["name"] not in reachable)
    assert not miss, (
        f"意乙 {len(miss)} 支队没有中文名:{miss}\n"
        "⚠️ 竞彩不卖意乙 ⇒ 没有赛事身份可钉。按标准译名补,但**必须先跑撞车检查**"
        "(见本文件 test_no_collision_* 两条),撞车的宁可留空。")
