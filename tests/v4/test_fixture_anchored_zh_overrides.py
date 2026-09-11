"""竞彩用了另一种中文写法 → 靠**同场唯一**锚补 `_ZH_OVERRIDES`(表驱动)。

## 病史(两天两例,同一形状)

    2026-08-19  [欧罗巴] 贝尔格莱德红星 vs 比尔森      词典写「比尔森胜利」
    2026-08-20  [日职]   东京FC vs 千叶市原           词典写「千叶联」

⭐ **两例都是「只坏一侧」** —— 红星 / 东京FC 本来就通,横幅点的是**比赛**不是队。
照横幅列的两个名字各补一条会白补一半。**先逐名跑 `zh_to_canonical`,再动手。**

⭐ **两例都是「词典的中文值从来没匹配过竞彩」**(比尔森 25 场 vs 0、千叶市原 65 场 vs 0)
—— 不是「竞彩改了写法」,是**潜伏多年**的缺口:横幅只在该队被竞彩上架那天才点名。
⇒ **「横幅没响」≠「词典是全的」**(memory: `unmapped-gap-history-forward-only`)。

## 补法与红线

① 类(队在系统里、只是写法不同)⇒ 补 `_ZH_OVERRIDES`,**不动** `team_name_zh.py`。
英文值**照抄盘面真在用的拼法**(`odds_snapshots` 那条线 = join 目标本身),
配对靠**赛事身份**:同场已解析的那一侧,在该日该联赛**只有一个对手**。
⛔ 绝不照英文猜译名 —— 错映射是静默污染,比缺映射更坏。

## 加新条目时

在 `PINNED` 里加一行(中文串 → 英文值 + 锚队/方位/日期/联赛),
本文件五条断言会自动覆盖它。**锚必须是同场唯一,不是"长得像"。**
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: 竞彩中文写法 → 盘面英文名,附**赛事身份锚**(同场已解析的那一侧当日唯一对手)。
PINNED: dict[str, dict] = {
    "比尔森": {
        "en": "Plzen",
        "anchor": ("FK Crvena Zvezda", "home"),
        "date": "2026-08-20", "league": "UEL",
        "already_ok": ("贝尔格莱德红星", "FK Crvena Zvezda"),
    },
    "千叶市原": {
        "en": "JEF United Chiba",
        "anchor": ("FC Tokyo", "home"),
        "date": "2026-08-21", "league": "JPN_J1",
        "already_ok": ("东京FC", "FC Tokyo"),
    },
    # ⚠️ 这条是**同音异形**:词典写「弗罗西诺内」(罗),竞彩写「弗洛西诺内」(洛)。
    #    按竞彩写法 grep 会 0 命中而误判成「整队不在」⇒ 判类要 grep **英文键**。
    "弗洛西诺内": {
        "en": "Frosinone",
        "anchor": ("Juventus", "away"),
        "date": "2026-08-23", "league": "ITA_SERIE_A",
        "already_ok": ("尤文图斯", "Juventus"),
    },
    # ── 2026-09-01 横幅「2/17」。⭐ 被点名的 4 个名字里 **2 个本来就是好的**
    #    (普雷斯顿 / 枥木城)—— 横幅按**比赛**点名。又一次「先逐名跑再动手」。
    "布里斯托尔城": {
        "en": "Bristol City",
        "anchor": ("Preston", "home"),
        "date": "2026-09-01", "league": "ENG_CHAMPIONSHIP",
        "already_ok": ("普雷斯顿", "Preston"),
    },
    # ⚠️ 这条**锚不到 odds_snapshots**:Pinnacle 从没覆盖过日联赛杯,该场 0 行。
    #    ⇒ 用 `af_fixture` 锚(AF 赛程缓存里的那一条),见下面锚定断言的两条路。
    #    「南源」按音完全对不上 Vanraure —— 翻译法必错,只有 fixture 锚拿得到。
    # ── 2026-09-11 横幅「整个联赛的在售场次全部解不出:日乙」──
    # ⭐ 第三种变体机制:**意译 vs 音译**(词典「仙台维加塔」= Vegalta 音译;
    #    竞彩「仙台七夕」= Vega+Altair 的牛郎织女典故)。按音对不上,只有 fixture 锚拿得到。
    "仙台七夕": {
        "en": "Vegalta Sendai",
        "anchor": ("Consadole Sapporo", "away"),
        "date": "2026-09-13", "league": "JPN_J2",
        "already_ok": ("札幌冈萨多", "Consadole Sapporo"),
    },
    "秋田闪电": {          # 词典写「秋田蓝色闪电」—— 长短写法
        "en": "Blaublitz Akita",
        "anchor": ("Kataller Toyama", "away"),
        "date": "2026-08-15", "league": "JPN_J2",
        "already_ok": ("富山胜利", "Kataller Toyama"),
    },
    # ── 2026-09-10 `test_jingcai_listed_teams_are_fully_reachable` 点名的沙职缺口 ──
    # ⭐ 这条的锚**在档案同一行里**(对家英文已填),不用跨表配对。
    "哈马费萨": {          # 词典写「哈马赫费萨利」—— 竞彩用短写法
        "en": "Al-Faisaly FC",
        "anchor": ("Al-Hilal Saudi FC", "home"),
        "date": "2026-08-14", "league": "SAU_PRO_LEAGUE",
        "already_ok": ("利雅新月", "Al-Hilal Saudi FC"),
    },
    # ── 2026-09-10 横幅「整个联赛的在售场次全部解不出:巴甲」(1/19)──
    # ⭐ 横幅只点了 1 场,但**普查**发现档案里巴甲有 **8 个**写法解不出。
    #    这三条锚得到,另外 5 条锚不到 ⇒ 故意没补(理由写在 sporttery.py 那段)。
    #    判类要 grep **英文键**:三支的英文名词典**本来就有**,只是竞彩换了写法。
    "科里蒂巴": {          # 词典写「库里蒂巴」——「库/科」同音异形,眼睛最容易跳过
        "en": "Coritiba",
        "anchor": ("Atletico Paranaense", "away"),
        "date": "2026-09-12", "league": "BRA_SERIE_A",
        "already_ok": ("巴拉纳竞技", "Atletico Paranaense"),
    },
    "沙佩科": {            # 词典写「沙佩科恩斯」—— 竞彩用短写法
        "en": "Chapecoense-sc",
        "anchor": ("Flamengo", "away"),
        "date": "2026-07-23", "league": "BRA_SERIE_A",
        "already_ok": ("弗拉门戈", "Flamengo"),
    },
    "达伽马": {            # 词典写「瓦斯科达伽马」—— 同样是短写法
        "en": "Vasco DA Gama",
        "anchor": ("Santos", "away"),
        "date": "2026-08-16", "league": "BRA_SERIE_A",
        "already_ok": ("桑托斯", "Santos"),
    },
    "八户南源": {
        "en": "Vanraure Hachinohe",
        "anchor": ("Tochigi City", "away"),
        "date": "2026-09-02", "league": "JPN_LEAGUE_CUP",
        "af_fixture": 1567425,
        "already_ok": ("枥木城", "Tochigi City"),
    },
}


def _af_fixture_pair(fixture_id: int) -> tuple[str, str] | None:
    """AF 赛程缓存里 ``fixture_id`` 的 ``(home, away)``;找不到返回 None(⇒ 断言会红)。"""
    import glob
    import json
    for f in (glob.glob(str(REPO / "data/external/api_football/_fixtures/*.json"))
              + glob.glob(str(REPO / "data/external/api_football/fixtures/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for it in (d if isinstance(d, list) else d.get("response") or []):
            if not isinstance(it, dict):
                continue
            if (it.get("fixture") or {}).get("id") != fixture_id:
                continue
            t = it.get("teams") or {}
            return ((t.get("home") or {}).get("name"), (t.get("away") or {}).get("name"))
    return None


@pytest.mark.parametrize("zh", sorted(PINNED))
def test_the_name_resolves(zh: str) -> None:
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    assert zh_to_canonical(zh) == PINNED[zh]["en"]


@pytest.mark.parametrize("zh", sorted(PINNED))
def test_the_other_side_was_already_fine(zh: str) -> None:
    """⭐ 承重:证明「只有一侧坏」这个诊断是对的。

    这条红了说明另一侧也漂了 —— 那时该**重新诊断**,不是顺手再补一条。
    """
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    other_zh, other_en = PINNED[zh]["already_ok"]
    assert zh_to_canonical(other_zh) == other_en


@pytest.mark.parametrize("zh", sorted(PINNED))
def test_the_value_is_the_live_join_target(zh: str) -> None:
    """⭐ 承重:override 的值必须是 **odds_snapshots 用的那个英文名**(join 目标)。

    写成词典里的另一个同义键会让竞彩行**解析成功但 join 不上 Pinnacle** ——
    比缺映射更难查,因为界面看着正常。
    """
    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    en = PINNED[zh]["en"]
    n = conn.execute("SELECT COUNT(*) FROM odds_snapshots WHERE home_team=? OR away_team=?",
                     (en, en)).fetchone()[0]
    assert n > 0, f"{zh} → {en!r} 在 odds_snapshots 里一次都没出现过,不是 join 目标"


@pytest.mark.parametrize("zh", sorted(PINNED))
def test_the_pairing_is_pinned_by_fixture_identity(zh: str) -> None:
    """⭐ 承重:配对是**推出来的**不是猜的 —— 锚队当日对手唯一,且就是它。

    红了 = 钉的前提没了(赛程变了/库里多了一场)⇒ **重新钉一次,别硬改常数。**
    """
    p = PINNED[zh]
    if "af_fixture" in p:
        # ⭐ 第二条锚源(2026-09-01 起)。`odds_snapshots` 只覆盖 Pinnacle 开过的场次
        # —— 日联赛杯这类它从没开过,该表 0 行 ⇒ 拿它当唯一锚源会把**能锚的场次
        # 误判成锚不到**。AF 赛程缓存不依赖任何书商开盘,而且钉的是**具体 fixture id**,
        # 比「当日对手集」更硬。⛔ 但它只是换锚源,不是放宽:仍要求两侧逐字相等。
        assert _af_fixture_pair(p["af_fixture"]) == (
            (p["en"], p["anchor"][0]) if p["anchor"][1] == "away" else (p["anchor"][0], p["en"])
        ), f"AF fixture {p['af_fixture']} 的两队和钉的不一致 —— 重新钉,别改常数"
        return
    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    anchor, side = p["anchor"]
    col, other = ("home_team", "away_team") if side == "home" else ("away_team", "home_team")
    rs = {r[0] for r in conn.execute(
        f"SELECT DISTINCT {other} FROM odds_snapshots WHERE {col}=? AND match_date=? AND league=?",
        (anchor, p["date"], p["league"]))}
    assert rs == {p["en"]}, (
        f"{anchor} 在 {p['date']} {p['league']} 的对手集 = {rs},期望恰好 {{{p['en']!r}}}")


@pytest.mark.parametrize("zh", sorted(PINNED))
def test_no_collision_and_display_dict_untouched(zh: str) -> None:
    """⛔ 一名多队 = 静默 join 污染;且 ① 类不该动主字典(会多一条 setdefault 反查路径)。"""
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    en = PINNED[zh]["en"]
    clash = {e for e, z in TEAM_NAME_ZH.items() if z == zh and e != en}
    assert not clash, f"「{zh}」在 TEAM_NAME_ZH 里已属于 {clash}"
    assert zh not in TEAM_NAME_ZH.values(), f"「{zh}」被塞进了主字典,应该只在 override 里"

    db = REPO / "data/v4_jingcai_history.db"
    if not db.exists():
        pytest.skip("竞彩档案不在这个 checkout 里")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    owners: set[str] = set()
    for tbl, zc, ec in (("jingcai_odds_history", "home_zh", "home_team"),
                        ("jingcai_odds_history", "away_zh", "away_team"),
                        ("crown_close_history", "home_zh", "home_team"),
                        ("crown_close_history", "away_zh", "away_team")):
        owners |= {r[0] for r in conn.execute(
            f"SELECT DISTINCT {ec} FROM {tbl} WHERE {zc}=?", (zh,)) if r[0]}
    assert not (owners - {en}), f"「{zh}」在档案里属于别的队:{sorted(owners)}"


def test_the_two_red_stars_never_collapse_into_one() -> None:
    """⛔ 单独一条 —— 「红星」是本组里唯一的真歧义。

    竞彩档案里 `贝红星`(21 场,全欧罗巴 = 贝尔格莱德红星)与
    `圣旺红星`(22 场,全法甲/法乙 = 巴黎红星)是**不同的俱乐部**。
    `贝红星` 2026-08-19 **故意没补**(拿不到锚:自有赛程只回溯到 2026-05-31、
    皇冠同场 home_team 也是 NULL)—— 但哪天有人补了,绝不能指到巴黎红星。

    ⭐ 该断言对「补没补」不敏感,只对**补错**敏感 ⇒ 不会假红。
    """
    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    bg, paris = zh_to_canonical("贝红星"), zh_to_canonical("圣旺红星")
    assert paris == "RED Star FC 93", f"圣旺红星(巴黎)漂了:{paris!r}"
    if bg is not None:
        assert bg != paris, "贝红星被映射成了巴黎红星 —— 两支不同的俱乐部"
        assert "Zvezda" in bg or "Crvena" in bg, f"贝红星 被映射到 {bg!r}"


def test_the_unanchored_j2_teams_were_not_guessed() -> None:
    """⛔ 2026-09-11 普查:日乙 14 个写法解不出,只有 2 个锚得到。

    另外 12 个(熊本深红 ×404 · 群马温泉 ×391 · 爱媛FC ×332 · 磐城FC ×300 ·
    山口雷诺 ×300 · 枥木SC ×290 · 金泽塞维 ×232 · 琉球FC ×221 · 盛冈仙鹤 ×182 ·
    藤枝MYFC ×162 · 今治FC ×86 · 相模原SC ×12)**故意没补**:它们的档案比赛最晚停在
    2021–2025,而 `odds_snapshots` 的日乙赛程只覆盖 2026-08-07→09-13、
    AF fixture 缓存只到 2026-05-23 —— **两条锚源都够不着**。

    ⭐ 本断言对「补没补」不敏感、只对「补错」敏感(同「两颗红星」「巴甲」两条):
    哪天它们再上架、当场就有锚,补上了照样绿;但补成一个**盘面日乙名单里没有的
    英文名**就红 —— 那正是「按音猜」会产生的东西。
    ⚠️ 日乙尤其危险:`仙台七夕` 证明了竞彩会用**意译**(Vegalta→七夕),
    按音去猜必错。
    """
    import sqlite3

    from nutmeg.v4.data.sources.sporttery import zh_to_canonical

    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    board = {r[0] for r in conn.execute(
        "SELECT DISTINCT home_team FROM odds_snapshots WHERE league='JPN_J2'")}
    board |= {r[0] for r in conn.execute(
        "SELECT DISTINCT away_team FROM odds_snapshots WHERE league='JPN_J2'")}
    # 🚨 人口非平凡:盘面必须真有日乙球队,否则 `in board` 全是空洞为真
    assert len(board) >= 15, f"盘面日乙只有 {len(board)} 支 —— 断言变空洞,请先看数据"
    for zh in ("熊本深红", "群马温泉", "爱媛FC", "磐城FC", "山口雷诺", "枥木SC",
               "金泽塞维", "琉球FC", "盛冈仙鹤", "藤枝MYFC", "今治FC", "相模原SC"):
        en = zh_to_canonical(zh)
        if en is None:
            continue                      # 仍未补 —— 合规
        assert en in board, (
            f"「{zh}」被补成了 {en!r},而盘面日乙名单里没有它 —— 疑似按音猜的")


def test_the_unanchored_brazilians_were_not_guessed() -> None:
    """⛔ 2026-09-10 普查:巴甲有 8 个写法解不出,只有 3 个锚得到。

    另外 5 个(戈竞技 ×185 · 尤文图德 ×182 · 库亚巴 ×165 · 阿瓦伊 ×67 · 累体育 ×59)
    **故意没补** —— 档案英文列全空、盘面赛程只覆盖 2026-07-16→09-14 够不着它们的比赛、
    皇冠档案里一场巴西联赛都没有。⇒ **没有锚就不写**。

    ⭐ 本断言对「补没补」**不敏感**,只对「补错」敏感(同「两颗红星」那条):
    哪天有人拿到锚补上了,它照样绿;但补成一个**盘面上不存在的英文名**就会红 ——
    那正是「按音猜」会产生的东西。
    """
    import sqlite3

    from nutmeg.v4.data.sources.sporttery import zh_to_canonical

    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("观测库不在这个 checkout 里")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    board = {r[0] for r in conn.execute(
        "SELECT DISTINCT home_team FROM odds_snapshots WHERE league='BRA_SERIE_A'")}
    board |= {r[0] for r in conn.execute(
        "SELECT DISTINCT away_team FROM odds_snapshots WHERE league='BRA_SERIE_A'")}
    # 🚨 人口非平凡:盘面必须真有巴甲球队,否则下面的 `in board` 全是空洞为真
    assert len(board) >= 15, f"盘面巴甲只有 {len(board)} 支 —— 断言变空洞,请先看数据"
    for zh in ("戈竞技", "尤文图德", "库亚巴", "阿瓦伊", "累体育"):
        en = zh_to_canonical(zh)
        if en is None:
            continue                      # 仍未补 —— 合规
        assert en in board, (
            f"「{zh}」被补成了 {en!r},而盘面巴甲名单里没有它 —— 疑似按音猜的")
