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
from pathlib import Path

import pytest

from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES as A
from nutmeg.v4.data.odds_source_aliases import canonical_team

REPO = Path(__file__).resolve().parents[2]


def test_no_key_conflicts() -> None:
    """同一个 (联赛, closing名) 不能映射到两个不同的 gather 名。

    dict 字面量天然不会有重复键 —— 但**后写的会静默覆盖先写的**,
    所以这条真正钉的是「条数没有因为重键而缩水」。
    """
    assert len(A) == 223, (
        f"表大小 {len(A)},预期 223(210 + 08-18 的 8:`derive_odds_name_aliases.py` "
        f"推出 9 条,**采纳 8 条**;第 9 条 `Vitória SC→Guimaraes` 方向反了,"
        f"理由写在别名表里 · + 09-01 的 2:EFL_CUP 的 Coventry/Leeds,"
        f"08-25 才首次在杯赛两侧共现)。"
        f"+ 09-02 的 3:沙特联 Al-Qadsiah / Al-Shabab / Diriyah Club —— "
        f"08-16 留空的那批等到了严格 1×1 槽,理由写在别名表里。"
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
        # ── 新 31 条(2026-08-13,受训联赛)+ 08-14 残余孤儿 14 条 ──
        # GER_2_BUNDESLIGA 1→3 · NED_EREDIVISIE 5→6 · PRT_PRIMEIRA_LIGA 6→9
        # · FRA_LIGUE_2 **0→8**(该联赛此前一条别名都没有)
        "BEL_PRO_LEAGUE": 10, "GER_2_BUNDESLIGA": 3, "JPN_J1": 9,
        "NED_EREDIVISIE": 6, "PRT_PRIMEIRA_LIGA": 9, "FRA_LIGUE_2": 8,
        # ── 新 38 条(2026-08-14,**预埋**:这 8 个联赛 closing 侧当时 0 行) ──
        "EPL": 2, "ESP_LA_LIGA": 7, "ITA_SERIE_A": 1, "FRA_LIGUE_1": 4,
        # ⚠️ 英冠 5→16:08-14 预埋时 closing 侧 0 行,首个比赛日才暴露 9 个名字
        #   (其中 8 个我只建了 EFL_CUP 键)。见 test_alias_gap_when_same_name...
        "ENG_CHAMPIONSHIP": 16, "ESP_SEGUNDA_DIVISION": 15, "ITA_SERIE_B": 4,
        # ── 🩸 联赛杯 39 条:**不是预埋,是止血** ──
        # 08-14 补 37 条:closing 侧 70 个名字里 37 个叠不上;08-08 整轮双记。
        # ⚠️ 37→39(2026-09-01):`Coventry City`→`Coventry` / `Leeds United`→`Leeds`。
        #   08-14 时它们在杯赛两侧都是 0 行,当时**明确不许预埋**;08-25 第一次上盘面
        #   (closing 69 / gather 418,同比赛日两侧都有)⇒ 拿到该联赛自己的共现证据才补。
        #   🚨 抓到它的不是任何注释(第 197 行和本表段落头都写过警告),而是数据驱动的
        #   `test_alias_gap_when_same_name_plays_in_another_league` —— **同一个洞第三次**。
        "EFL_CUP": 39,
        # ── 解放者杯 3 + 沙特联 2(2026-08-14):回填后仅存的跨源劈开键 ──
        # ⚠️ 沙特联 2→10(2026-08-16):08-14 只看到 2 条,数据攒够才暴露系统性差异。
        #   ⚠️ 10→13(2026-09-02):08-16 故意留空的 Al-Shabab/Al-Qadsiah 等到了
        #   严格 1×1 槽(各 1/3 个),连同 Diriyah Club(2 个)一并解开;
        #   AF 第 5 轮缓存**完整**(9 场连号、18 队各 1 次)⇒「那分钟只有 1 场」
        #   是赛程事实不是采集缺口。⛔ Al-Ahli 证据同样够但**不在当次范围**,仍留空。
        "COPA_LIBERTADORES": 5, "SAU_PRO_LEAGUE": 13,
        # ── 土超 5 条(2026-08-15):此前 0 条,全是变音符/改名 ──
        "TUR_SUPER_LIG": 11,
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


def test_celta_league_isolation_first_team_vs_b_team() -> None:
    """🚨 塞尔塔一队(西甲)与 B 队(西乙)—— **(联赛,名) 的联赛维度在这里承重**。

    Odds API 在**西乙**盘面里把塞尔塔 B 队写成 `Celta Vigo`(一队的简称),
    而 API-Football 写 `Celta de Vigo II`。同一个串 `Celta Vigo` 在**西甲**盘面里
    指的是**一队**(AF league 140),两侧同名、不需要别名。

    ⇒ 别名 `('ESP_SEGUNDA_DIVISION','Celta Vigo') → 'Celta de Vigo II'` 必须
    **只在西乙桶里开火**。若哪天有人把查表改成不带联赛(或先 fallback 到全局表),
    西甲一队会被静默改写成 B 队 —— 两支不同的队合并,而且**日志全绿**。

    空包弹:把 `canonical_team` 里的 `(canonical_league(league) or "", name)`
    改成只用 `name` ⇒ 第二条断言立刻红。
    """
    assert canonical_team("ESP_SEGUNDA_DIVISION", "Celta Vigo") == "Celta de Vigo II"
    # 🚨 承重的那条:西甲的同名串必须**原样穿过**
    assert canonical_team("ESP_LA_LIGA", "Celta Vigo") == "Celta Vigo"
    # 别的联赛同理(比如杯赛)
    assert canonical_team("UCL", "Celta Vigo") == "Celta Vigo"


def test_efl_cup_has_its_own_verified_entries() -> None:
    """🩸 联赛杯**不是预埋,是止血** —— 08-14 补了 37 条,每条独立证伪过。

    取代原来的 `test_english_names_do_not_leak_into_efl_cup`(那条的「下一轮」到了)。

    🚨 **原测试的前提有一半是假的**:它断言 5 个队名「同时出现在 EFL_CUP 盘面」,
    但实测 `Coventry`/`Leeds` 在杯赛 closing 与 gather **两侧都是 0 行** ⇒
    对那 2 条,「未被改写」是**空转断言** —— 表里本来就没有,fail-open 必然原样返回。
    ⭐ 又一例「断言了一件不可能为假的事」,和 08-13 那个被 fail-open 穿透补齐的
    集合断言同族。

    另更正一个口径:原 docstring 写「35 个键只有 6 个叠得上」,那是 (日期,主,客)
    **键**;按**队名**数则是 closing 侧 70 个里 37 个叠不上。两个数都对,单位不同。
    """
    # ① 杯赛自己的条目生效(这三条来自同槽指纹,负对照 8/8 通过)
    assert canonical_team("EFL_CUP", "Leicester City") == "Leicester"
    assert canonical_team("EFL_CUP", "West Bromwich Albion") == "West Brom"
    assert canonical_team("EFL_CUP", "Wimbledon") == "AFC Wimbledon"

    # ② 联赛维度仍然承重:同一个串在没有条目的联赛必须原样穿透
    assert canonical_team("EPL", "Leicester City") == "Leicester City"
    assert canonical_team("ENG_CHAMPIONSHIP", "Wimbledon") == "Wimbledon"

    # ③ ⛔ 没有证据的联赛不许预埋 —— **规矩没变,变的是证据**。
    #
    # 2026-08-14 立本条时,`Coventry`/`Leeds` 在 EFL_CUP 两侧都是 **0 行**,
    # 所以当时钉的是「不许有条目」。2026-08-25 它们第一次出现在杯赛盘面
    # (直接查 `odds_snapshots`:同联赛同比赛日,closing 69 行 / gather 418 行):
    #     closing 侧 'Coventry City' / 'Leeds United'
    #     gather  侧 'Coventry'      / 'Leeds'
    # ⇒ 「该联赛自己的共现证据」已经拿到,条目于 2026-09-01 补上。
    #
    # 🚨 这条断言当初把**一个当时的结论**冻了起来,而不是把**规矩**写下来
    #    ⇒ 数据变化的那一天它必然与正确修复正面冲突(实测:补键当场撞红,
    #    而红的理由「两侧都没有行」在那一刻已经是假的)。真正守这条规矩的是下面
    #    数据驱动的 `test_alias_gap_when_same_name_plays_in_another_league`
    #    —— 它是**从库里现算**的,不会随时间腐坏。这里只留正向的解析断言。
    for nm, want in (("Coventry City", "Coventry"), ("Leeds United", "Leeds")):
        assert canonical_team("EFL_CUP", nm) == want, f"{nm!r} 的杯赛条目没生效"
        # ⭐ 联赛维度仍然承重:换个没有条目的联赛必须**原样穿透**,
        #    否则「补一条杯赛键」会顺手污染所有联赛。
        assert canonical_team("UCL", nm) == nm, f"{nm!r} 泄进了没有条目的联赛"


def test_efl_cup_sheffield_pair_never_merges() -> None:
    """🚨 谢菲尔德:全库同时存在 Sheffield United / Sheffield Utd / Sheffield Wednesday。

    ⚠️ 这三个串两两**互不为前缀也互不为子串** ⇒ 08-13 那个近邻扫描
    (`gn in n or n in gn`)**抓不到**这一对。所以单写一条。
    空包弹:把目标改成 'Sheffield Wednesday' ⇒ 本条立刻红。
    """
    assert canonical_team("EFL_CUP", "Sheffield United") == "Sheffield Utd"
    assert canonical_team("EFL_CUP", "Sheffield Wednesday") == "Sheffield Wednesday"
    assert A.get(("EFL_CUP", "Sheffield United")) != "Sheffield Wednesday"


def _alias_gaps(rows: list[tuple], aliases: dict) -> dict[str, list[str]]:
    """从 `odds_snapshots` 的行里找出「别名建在了别的联赛」的缺口。

    ⭐ 2026-09-01 从 `test_alias_gap_when_same_name_plays_in_another_league`
    里抽出来:原来这段逻辑**只有在本机有观测库时才会被执行过一次**,
    没有任何东西证明它真能抓到它声称要抓的形态。抽成纯函数之后,
    `test_alias_gap_detector_fires_on_the_2026_08_15_shape` 用合成行直接钉它,
    空包弹也才有地方打。

    `rows` = [(league, match_date, source, home_team, away_team), …]。
    """
    day: dict[tuple, list[int]] = collections.defaultdict(lambda: [0, 0])
    for lg, d, src, _h, _a in rows:
        day[(lg, d)][0 if src == "closing" else 1] += 1
    live = {k for k, v in day.items() if v[0] and v[1]}   # ← 分母守卫

    closing_names: dict[str, set[str]] = collections.defaultdict(set)
    gather_names: dict[str, set[str]] = collections.defaultdict(set)
    for lg, d, src, h, a in rows:
        if (lg, d) not in live:
            continue
        tgt = closing_names if src == "closing" else gather_names
        tgt[lg].update((h, a))

    aliased = collections.defaultdict(set)               # closing名 → 已建键的联赛集
    for lg, nm in aliases:
        aliased[nm].add(lg)

    gaps: dict[str, list[str]] = collections.defaultdict(list)
    for nm, leagues in aliased.items():
        for lg, names in closing_names.items():
            if lg in leagues or nm not in names:
                continue
            # ⛔ 2026-09-01 复核移除:这里一度多一句
            #      `if nm in gather_names.get(lg, set()): continue`
            #    (closing 名在本联赛 gather 侧原样存在就当作不缺键)。它是在一次
            #    「只修测试」的改动里顺手加进来的**收窄**,没有任何 commit 依据,
            #    而 `closing_names`/`gather_names` 本来就是**逐联赛**的,它声称要防的
            #    跨联赛误算根本不存在。实测在当前全库数据上它是 no-op(加不加同一结果)
            #    ⇒ 今天不救人,将来只会漏报:同一联赛里若一部分场次两侧都用长名、
            #    另一部分是长 closing / 短 gather,它会把后者一起吞掉。
            #    ⇒ 恢复本探测器**原本的**语义。
            # 它在本联赛真的叠不上吗?(目标名在 gather 侧就说明确实缺)
            tgt = {aliases[(x, nm)] for x in leagues}
            if tgt & gather_names.get(lg, set()):
                gaps[lg].append(f"{nm!r} → {sorted(tgt)}")
    return dict(gaps)


def test_alias_gap_detector_fires_on_the_2026_08_15_shape() -> None:
    """⭐ 探针自检:用**合成行**重演 2026-08-15 那个形态,证明 `_alias_gaps` 真会响。

    没有这条,下面那条护栏在没有观测库的环境里 skip、在有库的环境里
    「恰好全绿」—— 两种情况都不构成「它能抓到东西」的证据
    (同 [[syntactic-proxy-for-semantic-property]]:先把答案当场算一遍)。
    """
    aliases = {("EFL_CUP", "Sheffield United"): "Sheffield Utd"}
    rows = [
        # 英冠这一天两侧都有行 ⇒ 过分母守卫;closing 用 `Sheffield United`,
        # gather 用别名的目标 `Sheffield Utd` ⇒ 差的就是 (ENG_CHAMPIONSHIP, …) 那条键。
        ("ENG_CHAMPIONSHIP", "2026-08-15", "closing", "Sheffield United", "Norwich"),
        ("ENG_CHAMPIONSHIP", "2026-08-15", "gather", "Sheffield Utd", "Norwich"),
    ]
    assert _alias_gaps(rows, aliases) == {
        "ENG_CHAMPIONSHIP": ["'Sheffield United' → ['Sheffield Utd']"]}, "探针不响"

    # ① 键补上 ⇒ 不响
    assert not _alias_gaps(rows, {**aliases, ("ENG_CHAMPIONSHIP", "Sheffield United"):
                                  "Sheffield Utd"})
    # ② 分母守卫:**逐(联赛,比赛日)**要求两侧都有行。
    #    这里造的正是 2026-08-15 西乙那次误报的形状:比赛日 A 只有 closing、
    #    比赛日 B 只有 gather —— 不按天卡就会把 A 的 closing 名和 B 的 gather 名
    #    拼成一个根本不存在的「缺口」。
    #    ⚠️ 第一版这条写成 `rows[:1]`(整个输入只有一行 closing),
    #    把守卫拆掉它照样绿 —— 因为 gather 侧压根是空的,走不到判据。
    assert not _alias_gaps(
        [("ENG_CHAMPIONSHIP", "2026-08-15", "closing", "Sheffield United", "Norwich"),
         ("ENG_CHAMPIONSHIP", "2026-08-16", "gather", "Sheffield Utd", "Norwich")],
        aliases)
    # ③ ⛔ 原来这里断言「closing 名在本联赛 gather 侧原样存在 ⇒ 不算缺口」。
    #    那条断言是上面被移除的 `continue` 的镜像,一起删 —— 它把一个**没有证据的
    #    收窄**固化成了期望值。逐联赛的名字集合是**并集**,「同名也出现过」并不能
    #    证明每一场都叠得上。
    # ④ 本联赛 gather 侧**没有**那个目标名 ⇒ 只凭「同名在别处有条目」不能判缺键。
    #    ⚠️ 这一条是补上去的:第一版少了它,「拆掉 `tgt & gather_names` 判据」的
    #    空包弹**全绿** —— 前三条恰好都被更早的分支挡住了,谁都没走到那句。
    assert not _alias_gaps(
        [("ENG_CHAMPIONSHIP", "2026-08-15", "closing", "Sheffield United", "Norwich"),
         ("ENG_CHAMPIONSHIP", "2026-08-15", "gather", "Somebody Else", "Norwich")],
        aliases)


def test_alias_gap_when_same_name_plays_in_another_league() -> None:
    """🚨 **同一支队进入新赛事就得重建键** —— 这条在开赛**前**就该红。

    `ODDS_SOURCE_ALIASES` 的键是精确的 `(联赛, closing名)`。
    2026-08-15 首个英冠比赛日实测:`Sheffield United` / `Norwich City` 等 8 个名字
    我在 08-14 只建了 **EFL_CUP** 键,赛季一开它们出现在英冠盘面,
    杯赛条目**零作用** ⇒ 那一整个比赛日的 closing 行叠不上 gather。

    ⭐ 本条把「已经在别的联赛补过了」这个**假的覆盖感**变成可检测的:
    若某个 closing 名在联赛 A 有条目,而它**也出现在联赛 B 的 closing 侧**
    且联赛 B 有 gather 行(⇒ B 是活的、可判的),那 B 就缺一条键。

    ⚠️ 分母守卫:只看**两侧都有行**的 (联赛,比赛日) —— 否则
    「gather 还没采到」会被误报成缺别名(2026-08-15 踩过:西乙 08-17 的 2 键
    其实是 gather 滞后,被旧口径判成 FAIL)。
    """
    import sqlite3

    # ⚠️ 2026-09-01:原来是 `Path("data/v4_observation.db")` —— **CWD 相对**。
    # 换个目录跑 pytest 就静默 skip,正是本仓那条「把『没有』说成『没去看』」。
    # 改成仓库根锚定;同文件其余 DB 用例(`test_fixture_anchored_zh_overrides` 等)
    # 也是这个写法。
    db = REPO / "data/v4_observation.db"
    if not db.exists():
        pytest.skip("没有观测库 —— 这条断言只在本地有意义")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT league, match_date, source, home_team, away_team "
            "FROM odds_snapshots").fetchall()
    finally:
        con.close()

    gaps = _alias_gaps(rows, A)
    assert not gaps, (
        f"这些 closing 名在别的联赛已有别名,却出现在**本联赛**的 closing 侧、"
        f"而本联赛 gather 侧正好有那个目标名 ⇒ 本联赛缺键,该比赛日的行会叠不上:"
        f"{dict(gaps)}。⛔ 别以为「在杯赛补过了」就够 —— (联赛,名) 是精确键。")
