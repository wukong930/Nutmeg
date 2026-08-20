"""竞彩把「比尔森胜利」写作「比尔森」(2026-08-19 横幅 1/9)。

## 病史

面板报「⚠️ 竞彩队名解不出 → SP 挂不上的比赛 (1/9)」:

    [欧罗巴] 贝尔格莱德红星 vs 比尔森

⭐ **横幅点的是「比赛」不是「队」** —— 两个名字里只有一个解不出:
`贝尔格莱德红星` → `FK Crvena Zvezda` 本来就通,拖住整场的是 `比尔森`
(词典写 `比尔森胜利`)。照横幅的两个名字各补一条会白补一半。

## ① 类,而且是个**四年的老缺口**

实测竞彩自己的档案(外部来源,不是我们的词典回流):
`比尔森` 出现 **25 场**(2022-07-21..2026-02-27),`比尔森胜利` **0 场**
⇒ 词典那个中文值从来没匹配过竞彩。不是「竞彩改了写法」,是一直如此;
横幅看不见它,因为它只在该队被竞彩上架时才点名。

## 另一条链是好的

补词典只解决「竞彩 SP 挂不挂得上」。该场 Pinnacle 赔率已在 `odds_snapshots`
(2026-08-20 UEL,psc 1.72/4.16/4.18,ou_line 2.5)⇒ 补完是真能算 EV,
不是只让横幅闭嘴(见 memory `unmapped-banner-silences-not-fixes`)。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

ADDED = {"比尔森": "Plzen"}
#: 同场里已经能解析的那一侧 —— 赛事身份钉的锚。
ANCHOR = {"比尔森": ("FK Crvena Zvezda", "home")}
FIXTURE_DATE, FIXTURE_LEAGUE = "2026-08-20", "UEL"


def test_the_name_resolves() -> None:
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    for zh, en in ADDED.items():
        assert zh_to_canonical(zh) == en, f"{zh} 没解析到 {en}"


def test_the_other_side_was_already_fine() -> None:
    """⭐ 承重:证明「只有一侧坏」这个诊断是对的。

    若哪天这条红了,说明红星那一侧也漂了 —— 那时该重新诊断,**不是**顺手再补一条。
    """
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    assert zh_to_canonical("贝尔格莱德红星") == "FK Crvena Zvezda"


def test_the_value_is_the_live_join_target_not_a_dictionary_key() -> None:
    """⭐ 承重:override 的值必须是 **odds_snapshots 用的那个英文名**。"""
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
    """⭐ 承重:配对是**推出来的**不是猜的 —— 锚队当日对手唯一,且就是它。"""
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
    """⛔ 一名多队 = 静默 join 污染。主字典 / override 表 / 两个中文档案都查。"""
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
    """① 类 ⇒ 补 override 就够,`team_name_zh.py` **不该**动。"""
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    for zh in ADDED:
        assert zh not in TEAM_NAME_ZH.values(), f"「{zh}」被塞进了主字典,应该只在 override 里"


def test_the_two_red_stars_never_collapse_into_one() -> None:
    """⛔ 这次真正的污染风险,不是比尔森,是**两支「红星」**。

    竞彩档案里 `贝红星`(21 场,全欧罗巴 = 贝尔格莱德红星)与
    `圣旺红星`(22 场,全法甲/法乙 = 巴黎红星)是**不同的俱乐部**。
    `贝红星` 我**故意没补**(2026-08-19:拿不到锚,理由写在 sporttery.py 里)——
    但哪天有人补了,它**绝不能**指到巴黎红星那一支。

    ⭐ 这条断言对「补了没补」不敏感,只对**补错**敏感 ⇒ 不会假红。
    """
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    bg, paris = zh_to_canonical("贝红星"), zh_to_canonical("圣旺红星")
    assert paris == "RED Star FC 93", f"圣旺红星(巴黎)漂了:{paris!r}"
    if bg is not None:
        assert bg != paris, "贝红星被映射成了巴黎红星 —— 两支不同的俱乐部"
        assert "Zvezda" in bg or "Crvena" in bg, (
            f"贝红星 被映射到 {bg!r};若真要补,值必须是贝尔格莱德红星那条线")
