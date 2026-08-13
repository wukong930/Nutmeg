"""🈯 `ODDS_SOURCE_ALIASES` 的结构护栏(2026-08-13,受训联赛 61→92 条那批)。

## 为什么需要

这张表是 `odds_snapshots` **写入前的唯一收口**,而 `canonical_team` 在 sink 里
对**所有 source** 都跑(`observation/odds_snapshots.py:155-158`)—— 不只 closing。
⇒ 一条错的别名不是「少归一一次」,是**把两支不同的球队永久合并**,
而且**不报错、日志全绿**。本仓管这叫「沉默的错误答案」。

## ⭐ 这批的对抗验证发现的两件事,直接决定了下面钉什么

**① 碰撞检测抓不到「错目标恰好不在当前数据窗口里」的形态。**
变异检验实测:`Yokohama F Marinos → Yokohama FC`(把横滨两支队并成一支)
在**全部**碰撞判据下都是绿的 —— 因为横滨 FC 已降 J2、全库 0 行。
只有「每条别名至少修好 1 个键」这条抓得住它。
⇒ 那条是**数据侧**检查(要 DB),放在 `scripts/` + 体检里跑,不在本文件。
本文件钉的是**不需要 DB** 的结构不变量。

**② 危险不止「并队」,还有「正典被回退」。**
`Vitória SC → Guimaraes` 队没错(同一个 fixture_id 1575463、AF team id 224),
但 AF 在 2026-08-13 把 224 从 `Guimaraes` **改名成** `Vitória SC` ⇒
映射它是把正典**退回**已废弃的拼法。所以 `test_vitoria_sc_stays_out` 单独钉它。
"""
from __future__ import annotations

import collections

from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES as A
from nutmeg.v4.data.odds_source_aliases import canonical_team


def test_no_key_conflicts() -> None:
    """同一个 (联赛, closing名) 不能映射到两个不同的 gather 名。

    dict 字面量天然不会有重复键 —— 但**后写的会静默覆盖先写的**,
    所以这条真正钉的是「条数没有因为重键而缩水」。
    """
    assert len(A) == 92, (
        f"表大小 {len(A)},预期 92(旧 61 + 2026-08-13 新增 31)。"
        f"若你有意增删,改这个数并在下面 per-league 表同步。")


def test_no_target_collision() -> None:
    """⛔ 两个不同的 closing 名映射到**同一个** gather 名 = 极可能把两支队合并。

    空包弹:加一条 ('BEL_PRO_LEAGUE','Cercle Brugge KSV'): 'Club Brugge KV'
    (同城并队)⇒ 这条立刻红。
    """
    byt = collections.defaultdict(list)
    for (lg, src), tgt in A.items():
        byt[(lg, tgt)].append(src)
    bad = {k: v for k, v in byt.items() if len(v) > 1}
    assert not bad, f"多个 closing 名指向同一 gather 名 ⇒ 疑似并队:{bad}"


def test_no_transitive_rewrite() -> None:
    """⛔ A→B 且 B→C:目标名不许同时是另一条的源名(否则静默二次改写)。

    ⚠️ 大小写折叠后有 9 组「伪链」(`Mito HollyHock→Mito Hollyhock` 等),
    但本表是 **dict 精确查表、大小写敏感**,两串不相等 ⇒ 不成链。
    所以这条按**精确串**比,不折叠 —— 折叠了反而会假红。
    """
    srcs = {src for _, src in A}
    chains = {(lg, s): t for (lg, s), t in A.items() if t in srcs}
    assert not chains, f"存在传递链(目标名又是别的条目的源名):{chains}"


def test_per_league_counts() -> None:
    """逐联赛条数 —— 让「谁被动过」在 diff 里一眼可见。"""
    got = dict(collections.Counter(lg for lg, _ in A))
    assert got == {
        # ── 旧 61 条(2026-08-01) ──
        "BRA_SERIE_A": 5, "DNK_SUPERLIGA": 6, "FIN_VEIKKAUSLIIGA": 10,
        "KOR_K_LEAGUE_1": 2, "NOR_ELITESERIEN": 9, "SCO_PREMIERSHIP": 6,
        "SUI_SUPER_LEAGUE": 5, "SWE_ALLSVENSKAN": 8, "USA_MLS": 10,
        # ── 新 31 条(2026-08-13,受训联赛) ──
        "BEL_PRO_LEAGUE": 10, "GER_2_BUNDESLIGA": 1, "JPN_J1": 9,
        "NED_EREDIVISIE": 5, "PRT_PRIMEIRA_LIGA": 6,
    }, got


def test_canonical_team_is_fail_open() -> None:
    """⭐ 表里没有的名字 **原样返回**,绝不猜。

    这是有意的:缺一条别名只是少一点数据,**猜一条是把两支队合并**。
    """
    assert canonical_team("BEL_PRO_LEAGUE", "Club Brugge") == "Club Brugge KV"
    assert canonical_team("BEL_PRO_LEAGUE", "Cercle Brugge KSV") == "Cercle Brugge"
    # 没见过的 → 原样
    assert canonical_team("BEL_PRO_LEAGUE", "某支没听过的队") == "某支没听过的队"
    # 跨联赛不串:同一个串在别的联赛不该被改写
    assert canonical_team("EPL", "Club Brugge") == "Club Brugge"


def test_brugge_pair_never_merges() -> None:
    """🚨 比甲同城双雄 —— 两条 closing 名必须归到**不同**身份。

    Club Brugge 与 Cercle Brugge 同城同球场(Jan Breydel),是本表最危险的一对。

    ⚠️ **本条 2026-08-13 修过一次,原版是弱断言。** 原版比的是四个串归一后的
    **集合**:
        {canonical(x) for x in (Club Brugge, Club Brugge KV, Cercle Brugge,
                                Cercle Brugge KSV)} == {'Club Brugge KV', 'Cercle Brugge'}
    变异检验发现它**抓不到并队**:把 `Cercle Brugge KSV` 改指向 `Club Brugge KV`
    之后,`Cercle Brugge`(gather 侧名、不在表里)照样**原样穿过**,集合恰好还是
    那两个 ⇒ 断言绿,而两支队已经并了。

    ⭐ 教训:**断言「集合等于什么」在有 fail-open 穿透的场景下会被穿透项补齐。**
    要断言的是**这两条 closing 名的像不相等**,那才是「没并队」的定义。
    """
    club = canonical_team("BEL_PRO_LEAGUE", "Club Brugge")
    cercle = canonical_team("BEL_PRO_LEAGUE", "Cercle Brugge KSV")
    assert club != cercle, (
        f"布鲁日双雄被归到同一身份 {club!r} —— 两支不同的俱乐部被合并了")
    assert (club, cercle) == ("Club Brugge KV", "Cercle Brugge"), (club, cercle)
    # gather 侧的两个名字必须原样穿过(它们已经是正典)
    assert canonical_team("BEL_PRO_LEAGUE", "Club Brugge KV") == "Club Brugge KV"
    assert canonical_team("BEL_PRO_LEAGUE", "Cercle Brugge") == "Cercle Brugge"


def test_structural_guards_cannot_see_out_of_window_targets() -> None:
    """📌 **把本文件的盲区钉下来** —— 不是 bug,是边界,必须显式记住。

    变异检验(2026-08-13)实测:`('JPN_J1','Yokohama F Marinos'): 'Yokohama FC'`
    —— 把横滨两支不同的队并成一支 —— **本文件全部结构断言都是绿的**。
    原因:横滨 FC 已降 J2,`odds_snapshots` 里 0 行,于是
    「目标撞车」「传递链」「自映射」逐个都够不着它。

    ⇒ 这一族只能靠**数据侧**判据兜:`scripts/check_alias_effect.py`
    的「每条别名至少修好 1 个键」。**删掉那个脚本 = 打开这个口子。**

    本测试不做断言逻辑,只在这里留一个会被 grep 到的锚点 + 让盲区进入测试报告。
    """
    assert ("JPN_J1", "Yokohama F Marinos") in A          # 我们确实有这条
    assert A[("JPN_J1", "Yokohama F Marinos")] == "Yokohama F. Marinos"
    # ⛔ 若有人把它改成 'Yokohama FC',**本文件不会红** —— 见上面 docstring。


def test_vitoria_sc_stays_out() -> None:
    """⛔ `Vitória SC → Guimaraes` **不许加回来** —— 它会把正典退回废弃拼法。

    2026-08-13 对抗验证:队没错(同 fixture_id 1575463、AF team id 224),
    但 AF 当天把 224 从 `Guimaraes` **改名为** `Vitória SC` ⇒
    `Vitória SC` 是 gather 侧的**新**正典,不是旧拼法。映射它 = 回退。

    ⚠️ 这也是为什么「两侧都有」必须单独论证:该 closing 名在 gather 侧有 2 行,
    那 2 行不是「另一支队」,而是**同一支队的新名字**。

    📌 若将来 AF 又改回去,删掉本测试并在表里加条目时**必须**重跑
    `scripts/derive_odds_name_aliases.py` 并复核 team id 的命名时间线。
    """
    assert ("PRT_PRIMEIRA_LIGA", "Vitória SC") not in A, (
        "Vitória SC → Guimaraes 已于 2026-08-13 被否决(方向反了:那是 AF 的新正典)。"
        "加回来会把 odds_snapshots 的正典退回废弃拼法。")


def test_no_self_mapping() -> None:
    """源名 == 目标名 = 无作用条目,只会让人以为归一过了。"""
    noop = {k: v for k, v in A.items() if k[1] == v}
    assert not noop, f"自映射(无作用)条目:{noop}"
