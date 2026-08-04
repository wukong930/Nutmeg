"""欧冠资格赛两支队的竞彩中文写法(2026-08-04)。

## 病史

面板报「⚠️ 竞彩在售、但没进盘面的比赛 (2/7)」:

    [欧冠] 米亚尔比 vs 布拉迪斯拉发
    [欧冠] 圣吉尔联合 vs 博德闪耀

⚠️ **先分清是词典缺口还是 Pinnacle 覆盖缺口** —— 面板提示自己警告过:
资格赛常常是 Pinnacle 根本没开盘,那种情况补词典没用。查了:两场的 psc 都在
`odds_snapshots` 里(2026-08-04 03:24Z 抓,2.08/3.62/3.18 与 2.07/3.8/3.08)
⇒ **纯词典缺口,补了会生效。**

## 属于 ① 类:队在词典里,只是竞彩换了写法

    Slovan Bratislava  词典「布拉迪斯拉发斯洛万」  竞彩「布拉迪斯拉发」
    Union St. Gilloise 词典「圣吉罗斯联」          竞彩「圣吉尔联合」

所以补 `_ZH_OVERRIDES`,**不动** `team_name_zh.py`(那里没缺东西)。

## ⭐ 配对靠赛事身份,不是音译

红线是「绝不瞎猜队名」——错映射是静默污染,比缺映射更坏。这两条不是猜的:
两场里**已解析的那一侧**(米亚尔比=Mjallby AIF / 博德闪耀=Bodo/Glimt)在
2026-08-04 UCL 各只有**唯一**一个对手,对手就是这两个名字。
撞车检查:两个中文名在 TEAM_NAME_ZH / _ZH_OVERRIDES / 竞彩档案 / 皇冠档案里
**都没被别的队占用**(0 冲突)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: 2026-08-04 补的两条。⭐ 值必须是 **odds_snapshots 里那条线的英文名**(join 目标),
#: 不是 TEAM_NAME_ZH 的键 —— 注意 `Union St. Gilloise`(带点)而非 `Union Saint-Gilloise`,
#: 两种写法词典里都有,但实盘线用的是前者。
ADDED = {
    "布拉迪斯拉发": "Slovan Bratislava",
    "圣吉尔联合": "Union St. Gilloise",
}
#: 同场里已经能解析的那一侧 —— 赛事身份钉的锚。
ANCHOR = {"布拉迪斯拉发": ("Mjallby AIF", "home"),
          "圣吉尔联合": ("Bodo/Glimt", "away")}
FIXTURE_DATE, FIXTURE_LEAGUE = "2026-08-04", "UCL"


def test_both_names_resolve() -> None:
    from nutmeg.v4.data.sources.sporttery import _ZH_TO_EN
    for zh, en in ADDED.items():
        assert _ZH_TO_EN.get(zh) == en, f"{zh} 没解析到 {en}"


def test_the_value_is_the_live_join_target_not_a_dictionary_key() -> None:
    """⭐ 承重:override 的值必须是 **odds_snapshots 用的那个英文名**。

    写成 TEAM_NAME_ZH 的另一个同义键(`Union Saint-Gilloise`)会让竞彩行
    **解析成功但 join 不上 Pinnacle** —— 比缺映射更难查,因为界面看着正常。
    """
    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里 —— 未做 join 目标核对")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for zh, en in ADDED.items():
        n = conn.execute(
            "SELECT COUNT(*) FROM odds_snapshots WHERE home_team=? OR away_team=?",
            (en, en)).fetchone()[0]
        assert n > 0, f"{zh} → {en!r} 在 odds_snapshots 里一次都没出现过,不是 join 目标"


def test_the_pairing_is_pinned_by_fixture_identity() -> None:
    """⭐ 承重:配对是**推出来的**不是猜的 —— 锚队当日对手必须唯一,且就是它。

    这条红了意味着钉的前提没了(赛程变了/库里多了一场),那时**不该**直接改常数,
    该重新钉一次。
    """
    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里 —— 未做赛事身份钉")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for zh, (anchor, side) in ANCHOR.items():
        col, other = ("home_team", "away_team") if side == "home" else ("away_team", "home_team")
        rs = {r[0] for r in conn.execute(
            f"SELECT DISTINCT {other} FROM odds_snapshots "
            f"WHERE {col}=? AND match_date=? AND league=?",
            (anchor, FIXTURE_DATE, FIXTURE_LEAGUE))}
        assert rs == {ADDED[zh]}, (
            f"{anchor} 在 {FIXTURE_DATE} {FIXTURE_LEAGUE} 的对手集 = {rs},"
            f"期望恰好 {{{ADDED[zh]!r}}} —— 身份钉的前提变了,重新钉,别硬改常数")


def test_no_collision_anywhere() -> None:
    """⛔ 一名多队 = 静默 join 污染。三处都查:主字典 / override 表 / 中文档案。"""
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    for zh, en in ADDED.items():
        clash = {e for e, z in TEAM_NAME_ZH.items() if z == zh and e != en}
        assert not clash, f"「{zh}」在 TEAM_NAME_ZH 里已属于 {clash}"
    db = REPO / "data/v4_jingcai_history.db"
    if not db.exists():
        pytest.skip("竞彩档案不在这个 checkout 里 —— 未做数据侧撞车检查")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for zh, en in ADDED.items():
        owners: set[str] = set()
        for tbl, zc, ec in (("jingcai_odds_history", "home_zh", "home_team"),
                            ("jingcai_odds_history", "away_zh", "away_team"),
                            ("crown_close_history", "home_zh", "home_team"),
                            ("crown_close_history", "away_zh", "away_team")):
            owners |= {r[0] for r in conn.execute(
                f"SELECT DISTINCT {ec} FROM {tbl} WHERE {zc}=?", (zh,)) if r[0]}
        assert not (owners - {en}), f"「{zh}」在档案里属于别的队:{sorted(owners)}"


def test_we_did_not_touch_the_display_dictionary() -> None:
    """这是 ① 类(只是写法不同)⇒ 补 override 就够,`team_name_zh.py` **不该**动。

    往主字典塞一个竞彩专用写法会让**反查**多一条 `setdefault` 先到先得的路径,
    可能顶掉别人 —— 见 test_serie_b_zh_names 里那条往返断言的病史。
    """
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    for zh in ADDED:
        assert zh not in TEAM_NAME_ZH.values(), f"「{zh}」被塞进了主字典,应该只在 override 里"
