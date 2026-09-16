"""亚冠精英 + 亚运女足注册(2026-09-14 横幅:「整个联赛的在售场次全部解不出」)。

## 为什么单独一个文件

`test_fixture_anchored_zh_overrides.py` 的 `PINNED` 是给**情况①**(队在系统里、
只是竞彩换了写法)设计的,每条要填 `already_ok`(同场已解出的那一侧)。
本批是**情况②:整队不在词典** ⇒ 补 `team_name_zh.py`,而且亚运女足那场
**两侧都是新的**,`already_ok` 无从填起。形状不同,别硬塞进那张表。

## 三条的锚强度**不一样** —— 这个文件的主要工作就是把差别钉住

① `Pakhtakor` ← 棉农:第①档锚(当前在售那场本身)。开球时刻 / 赛事 /
   **已解出的主队**三者同时对上,且该时刻该赛事主队唯一。
   ⭐ 顺带印证「意译 vs 音译」:Paxtakor 在乌兹别克语里就是「棉农」——
   按音猜(帕赫塔科尔)必错,而按音猜正是最容易顺手做的那件事。

② `China W` / `Hong Kong W`:**队实体锚住了,赛事没锚住**。AF 名册里两个实体带稳定
   id,但 fixture 缓存里**没有亚运女足这个赛事**(`Asian Games` 只有男足 U23)。
   ⇒ 名字是对的,但 join 不到东西。这条限制**必须写成断言**,不能只写在注释里 ——
   哪天 AF 开始发女足亚运,这条会红,提醒人回来重新判。

## ⚠️ 补完不等于能下注

odds_snapshots 的 39 个联赛里**既无亚冠精英也无亚运女足** ⇒ 这两场算不出 EV。
横幅看不见这条链,所以这里替它看着。
(🚨 查这件事时我用 `league LIKE '%ELITE%'` 命中了 NOR_ELITE**SERIEN** —— 又一次
 语法代理测语义属性。本文件的断言按**精确集合**判,不用 LIKE。)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES, zh_to_canonical
from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH, lookup_zh

REPO = Path(__file__).resolve().parents[2]
_AF_FIXTURES = REPO / "data/external/api_football/_fixtures"

#: 竞彩中文(全称 + 简称)→ 英文规范名。本文件所有断言从这张表自动展开。
REGISTERED: dict[str, str] = {
    "棉农": "Pakhtakor",
    "中国女足": "China W",
    "中国女": "China W",
    "中国香港女足": "Hong Kong W",
    "中国港女": "Hong Kong W",
}
#: 进 `team_name_zh`(情况②,一处同时修 join 和显示)的那三条。
DISPLAY: dict[str, str] = {
    "Pakhtakor": "棉农",
    "China W": "中国女足",
    "Hong Kong W": "中国香港女足",
}


def _af_rows():
    """AF fixture 缓存里的 (kickoff, 赛事名, 主, 客, id)。worktree 没 data/ ⇒ skip。"""
    if not _AF_FIXTURES.is_dir():
        pytest.skip("没有 AF fixture 缓存(worktree)")
    out = []
    for f in _AF_FIXTURES.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        for fx in (d.get("response") if isinstance(d, dict) else d) or []:
            if not isinstance(fx, dict):
                continue
            fi, tm, lg = fx.get("fixture") or {}, fx.get("teams") or {}, fx.get("league") or {}
            out.append((str(fi.get("date") or "")[:19], lg.get("name"),
                        (tm.get("home") or {}).get("name"), (tm.get("away") or {}).get("name"),
                        fi.get("id"), (tm.get("home") or {}).get("id"),
                        (tm.get("away") or {}).get("id")))
    # 🚨 人口非平凡:缓存空了的话下面每条断言都空洞为真
    assert len(out) > 10_000, f"AF 缓存只有 {len(out)} 条,测不出东西"
    return out


@pytest.mark.parametrize("zh", sorted(REGISTERED))
def test_every_registered_name_resolves(zh: str) -> None:
    assert zh_to_canonical(zh) == REGISTERED[zh]


@pytest.mark.parametrize("en", sorted(DISPLAY))
def test_display_side_too(en: str) -> None:
    """情况②补在 `team_name_zh` 的理由就是**一处同时修 join 和显示**。

    只补 `_ZH_OVERRIDES` 会变成「join 通了、卡片仍显示英文名」。
    """
    assert lookup_zh(en) == DISPLAY[en]


@pytest.mark.parametrize("zh", sorted(REGISTERED))
def test_no_collision_in_either_direction(zh: str) -> None:
    en = REGISTERED[zh]
    owners = [k for k, v in TEAM_NAME_ZH.items() if v == zh]
    assert owners in ([], [en]), f"中文名 {zh} 被别的队占了:{owners}"
    # 男足那三条必须原样不动(`China`/`China PR`→中国、`Hong Kong`→香港)
    assert TEAM_NAME_ZH.get("China") == "中国"
    assert TEAM_NAME_ZH.get("China PR") == "中国"
    assert TEAM_NAME_ZH.get("Hong Kong") == "香港"


def test_the_two_abbreviations_went_to_the_override_table() -> None:
    """简称属于「竞彩换了种写法」⇒ `_ZH_OVERRIDES`;全称属于情况② ⇒ `team_name_zh`。

    放错地方不会立刻坏,但会让下一个人读不出这批是怎么判的类。
    """
    assert _ZH_OVERRIDES.get("中国女") == "China W"
    assert _ZH_OVERRIDES.get("中国港女") == "Hong Kong W"
    assert "中国女足" not in _ZH_OVERRIDES, "全称该走 team_name_zh(它还要负责显示)"


class TestTheAnchorsAreRealNotStories:
    """⭐ 注释里的锚必须能被数据证实 —— 否则它只是一段我写的说辞。"""

    def test_pakhtakor_is_pinned_by_the_on_sale_fixture_itself(self) -> None:
        rows = _af_rows()
        ko, comp = "2026-09-14T18:15:00", "AFC Champions League Elite"
        same_slot = [r for r in rows if r[0] == ko and r[1] == comp]
        assert same_slot, f"缓存里没有 {comp} {ko} 的场次 —— 锚不成立"
        # 竞彩那场主队 = 吉达国民,词典里本来就解得出
        assert zh_to_canonical("吉达国民") == "Al-Ahli Jeddah"
        # ⚠️ 按 **fixture id** 去重:同一场比赛在缓存里可能有多份(2026-09-14 回填
        #    历史赛程后就是,同一 id 落在两个缓存文件里)。锚要求的是「**比赛**唯一」,
        #    不是「缓存行唯一」—— 原来写成数行数,回填当场把它打红了。
        mine = list({r[4]: r for r in same_slot if r[2] == "Al-Ahli Jeddah"}.values())
        assert len(mine) == 1, (
            f"该时刻该赛事以 Al-Ahli Jeddah 为主的场次有 {len(mine)} 场 —— "
            "锚要求**唯一**,不唯一就不能据此断定对手")
        # ⭐ 断言要和**被测对象**挂钩:不是「缓存里写着 Pakhtakor」(那是缓存的事实),
        #    而是「我们把棉农映射成了 fixture 说的那个名字」。
        #    实测:原来写死成 `== "Pakhtakor"` 时,把词典改成别的球队**这条照样绿** ——
        #    它验的是 AF,不是我们。(判据:改了被测对象,这条断言会不会变。)
        assert zh_to_canonical("棉农") == mine[0][3], (
            f"词典把棉农映射成 {zh_to_canonical('棉农')!r},而同场唯一的对手是 {mine[0][3]!r}")

    def test_the_two_women_entities_exist_with_stable_ids(self) -> None:
        rows = _af_rows()
        ids = {}
        for _, _, h, a, _, hid, aid in rows:
            for nm, tid in ((h, hid), (a, aid)):
                if nm in ("China W", "Hong Kong W"):
                    ids.setdefault(nm, set()).add(tid)
        # 同上:断言挂在**我们的映射**上,不是挂在缓存的字面值上。
        for zh, want_id in (("中国女足", 1723), ("中国香港女足", 17896)):
            en = zh_to_canonical(zh)
            assert ids.get(en) == {want_id}, (
                f"{zh} → {en!r},但该名字在 AF 缓存里的 id 是 {ids.get(en)}(应为 {{{want_id}}})"
                " —— 要么映射错了,要么 AF 改了实体")

    def test_af_distinguishes_age_grades_so_the_senior_name_is_unambiguous(self) -> None:
        """`China PR U20 W` 单独存在 ⇒ 不带后缀的 `China W` 就是成年队,没有歧义。

        没有这条,「China W 是成年国家队」只是我的断言。
        """
        names = {r[2] for r in _af_rows()} | {r[3] for r in _af_rows()}
        assert "China PR U20 W" in names, "AF 不区分年龄组的话,China W 的语义就不确定了"


class TestTheHonestLimits:
    """🚨 把「补完能买到什么」写成断言 —— 免得下一个人以为横幅闭嘴=能下注了。"""

    def test_the_womens_asian_games_is_now_in_the_cache_and_confirms_the_entity(self) -> None:
        """🚨 2026-09-16 订正:**这条测试的作用域原来写窄了。**

        它原名 `..._is_not_in_the_fixture_cache`,断言「`Asian Games` 里全是 U23」,
        docstring 写着「这条红了 = AF 开始发女足亚运了 ⇒ 回来重新判」。
        两天后 AF **确实**开始发了 —— 而它**没红**,因为女足在 AF 里是**另一个赛事名**
        `Asian Games Women`,而我把过滤器写成了精确的 `== "Asian Games"`。
        ⇒ 我给自己留的叫醒服务,被自己的过滤器挡掉了。
          同 [[syntactic-proxy-for-semantic-property]]:**判据写在一个我猜的常量上**。

        ## 重判的结论:09-14 那两条是对的,而且锚升级了

        当时写的是「队实体锚住了,**赛事没锚住**」。现在 `Asian Games Women` 有 18 场,
        其中 **fixture 1639548 = `China W` vs `Hong Kong W` @2026-09-14T10:00**
        —— **正是我当时注册的那一场** ⇒ 从「实体锚」升级成**第①档赛事锚**。

        ⭐ 还确认了一个当时没法确认的点:亚运**女**足用**成年队**(`China W`,无年龄后缀),
           而**男**足是 **U23** —— 两边年龄组不同,不是笔误。
        """
        rows = _af_rows()
        men = {(r[2], r[3]) for r in rows if r[1] == "Asian Games"}
        women = {(r[2], r[3], r[4]) for r in rows if r[1] == "Asian Games Women"}
        assert men, "人口非平凡:缓存里连男足亚运都没有"
        assert all(h.endswith(" U23") and a.endswith(" U23") for h, a in men), (
            f"`Asian Games`(男足)出现了非 U23 条目:{men}")
        assert women, (
            "`Asian Games Women` 又没了 —— 缓存被裁了?本条的叙述要重查")
        # ⭐ 女足是**成年队**:一个 U 后缀都不该有
        assert not any("U2" in h or "U2" in a or "U1" in h or "U1" in a
                       for h, a, _ in women), f"女足亚运出现了年龄组队伍:{women}"
        # 🚨 断言挂在**被测对象**上:我们的映射必须等于那场 fixture 说的两个名字
        slot = [w for w in women if w[2] == 1639548]
        assert len(slot) == 1, "09-14T10:00 那场(1639548)不在缓存里了 —— 叙述要重查"
        h, a, _ = slot[0]
        assert zh_to_canonical("中国女足") == h, f"主队锚到 {h!r}"
        assert zh_to_canonical("中国香港女足") == a, f"客队锚到 {a!r}"

    def test_afc_is_now_harvested_and_the_asian_games_still_is_not(self) -> None:
        """🚨 两次订正,方向相反,记在一起:

        ① 这条原来叫「没有赔率覆盖」,docstring 写着「⇒ 这两场算不出 EV」。**推论是错的。**

        `odds_snapshots` 没有这两个赛事 = **我们没去采**,不等于**源里没有**。
        实测 AF 的 Pinnacle 镜像对亚冠精英**有线**(见下一条断言)。
        真正的堵点是**市场模式注册表没登记这个赛事**,是我们这边的开关,不是数据源。

        ⇒ 判据:说「没有 X」之前,分清「库里没有」和「源里没有」。
           (同 `football-data-anchor-exhausted`:把「没有」说成「没去看」的反向版本。)

        ⚠️ 用**精确集合**判,不用 LIKE:我查这件事时用 `league LIKE '%ELITE%'`
        命中了 NOR_ELITE**SERIEN** 4024 行,差点报成「亚冠精英有覆盖」。
        """
        db = REPO / "data/v4_observation.db"
        if not db.exists():
            pytest.skip("没有观测库")
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            lgs = {r[0] for r in c.execute("select distinct league from odds_snapshots") if r[0]}
        assert len(lgs) > 20, f"人口非平凡:只有 {len(lgs)} 个联赛"
        # ⭐ 2026-09-14 翻面:注册生效后系统**真的开始采集**亚冠了 ——
        #   这条原本断言「AFC_CL_ELITE 不在库里」并据此说「算不出 EV」。
        #   护栏按它自己写的处方红了(「回来重判」),而重判的结论是**注册成功**:
        #   实测 12 行 `cup_market` 快照,例如 Beijing Guoan vs Pohang Steelers
        #   psc 1.95/3.79/3.42。这是整条链跑通的端到端证据,比原来那条强。
        assert "AFC_CL_ELITE" in lgs, (
            "注册后仍然没采到亚冠的赔率 —— 六条腿里有一条没生效,或 API 没重启")
        # 亚运女足**没有**跟着一起来:它连 AF fixture 都没有(见上一类)。
        for bad in ("ASIAN_GAMES", "ASIAD"):
            assert bad not in lgs
        assert not any(x.endswith("_W") or x.startswith("W_") for x in lgs), \
            f"出现了女足联赛 —— 覆盖变了,回来重判:{lgs}"


class TestAfcClEliteIsFullyWired:
    """🌏 2026-09-14 owner 授权:把亚冠精英加进市场模式注册表。

    ## 为什么之前不在 —— **不是数据源没给**

    AF 的 Pinnacle 镜像一直有线(2026-09-14/15 那 6 场里 **5 场**有 Pinnacle;
    fixture 1629915 = 9 家含 Pinnacle,1.22/6.70/10.04)。
    缺的是**注册表上的一行**:不在名单上,定价引擎根本不会去取。
    ⇒ 判据:说「没有 X」之前分清「**库里没有**」和「**源里没有**」。
       我一度拿「odds_snapshots 的 39 个联赛没有它」推出「算不出 EV」—— 推错了。

    ## 加一个联赛要接 5 条腿(这个类逐条钉住)

    ⚠️ 少接任何一条都不会立刻报错,只会**静默地少一块**:
      · AF id 缺 → fetch 拿不到赛程;
      · `_EN_TO_CN` 缺 → 中文轨/EN 轨劈成两组(同「日乙」那条病史);
      · `CUP_COMPETITIONS` 缺 → `classify_league` 把洲际杯赛算成 `domestic`,
        **悄悄混进 δ 校准的国内联赛人口**(韩国杯/日联赛杯那两条注释记着这个坑);
      · registry-coverage 缺 → 覆盖率检查扫不到它(2026-07-04 瑞超事件);
      · SPORT_KEYS **故意留空** —— Odds API 无此 sport,猜一个只会每次 404。
    """

    CODE = "AFC_CL_ELITE"

    def test_leg1_af_league_id_is_the_one_in_the_cache(self) -> None:
        from nutmeg.v4.data.sources.api_football import league_id
        rows = _af_rows()
        # 从**缓存**读出该赛事的 league id,而不是把 17 抄两遍
        got = {r[4] for r in rows if r[1] == "AFC Champions League Elite"}
        assert got, "人口非平凡:缓存里没有亚冠精英"
        assert league_id(self.CODE) == 17, f"league_id 给的是 {league_id(self.CODE)}"

    def test_leg2_it_is_in_the_market_mode_registry(self) -> None:
        src = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert f'"{self.CODE}"' in src
        # 人口非平凡:确认读的是**那张表**
        assert '"JPN_J2"' in src and '"NOR_ELITESERIEN"' in src

    def test_leg3_both_language_tracks_agree(self) -> None:
        from nutmeg.v4.data.league_labels import canonical_league
        assert canonical_league(self.CODE) == "亚冠精英", "EN 轨没归一到中文"

    def test_leg4a_membership_keeps_it_out_of_the_delta_population(self) -> None:
        """两条轨都必须判 `excluded` —— 否则跨国洲际杯赛混进 δ 校准的国内联赛人口。

        ⭐ 承重的是**在不在字典里**,不是 `competition_type` 的值:
           `classify_league` 的 EN 轨第一句就是 `if s in CUP_COMPETITIONS: return "excluded"`,
           中文轨靠 `亚冠精英 ∈ _NON_DOMESTIC_CN`(2026-08-17 就在了)。
        """
        from nutmeg.v4.data.competitions import is_cup_competition
        from nutmeg.v4.data.league_labels import classify_league
        assert is_cup_competition(self.CODE)
        for label in (self.CODE, "亚冠精英"):
            assert classify_league(label) == "excluded", (
                f"{label} 被判成 {classify_league(label)} —— 会混进 δ 的国内人口")

    def test_leg4b_the_competition_type_drives_a_model_feature(self) -> None:
        """🚨 变异检验的更正:我原来只写了 4a,并在 docstring 里说
        「`competition_type` 漏了会污染 δ 人口」。**那是错的** ——
        把它从 `club_cup` 改成 `league`,4a **照样全绿**(分类只看字典成员)。

        真正吃这个字段的是别处:`features/cup_features.py` 的 **`competition_type_id`
        是一个模型特征**,以及 `is_club_cup()`。所以断言要接到那条路上。

        ⭐ 用**同类赛事**对照而不是写死一个数字:亚冠精英与欧冠/解放者杯同属
           洲际俱乐部杯赛,特征值必须一致。写死数字的话,枚举一改这条就假红。
        """
        from nutmeg.v4.data.competitions import competition_type_id, is_club_cup_competition
        assert is_club_cup_competition(self.CODE), "不是 club_cup ⇒ 该判据的消费者会判错"
        # 用**同类赛事**当基准,并先证明基准本身非平凡(不是全 0)
        peer = competition_type_id("UCL")
        assert peer != competition_type_id("EPL"), "对照不成立:杯赛与联赛的特征值居然相同"
        assert competition_type_id(self.CODE) == peer == competition_type_id("COPA_LIBERTADORES"), (
            f"{self.CODE} 的 competition_type_id 与同类洲际杯赛不一致 —— 模型特征会歪")

    def test_leg5_registry_coverage_scans_it(self) -> None:
        from nutmeg.v4.cli.registry_coverage import MARKET_MODE_LEAGUES
        assert self.CODE in MARKET_MODE_LEAGUES
        assert len(MARKET_MODE_LEAGUES) > 10, "人口非平凡"

    def test_the_sport_key_is_deliberately_absent(self) -> None:
        """⛔ Odds API 没有亚冠 sport。留空是**决定**不是遗漏 ——

        猜一个不存在的 key 只会让 fetch 每次 404 当空处理(同荷乙/欧超杯/韩国杯)。
        这条红了 = 有人「补全」了它 ⇒ 先去核 `/sports?all=true` 确认真有这个 key。
        """
        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        assert self.CODE not in SPORT_KEYS
        assert "NED_EERSTE_DIVISIE" not in SPORT_KEYS, "先例变了,本条叙述要重查"

    def test_it_is_not_calendar_year(self) -> None:
        """赛季历**实证**:111 个比赛日 2021-09→2026-08,**1/6/7 月全空**、8 月→次年 5 月

        ⇒ 秋春制,欧洲惯例(season=开赛那年)正确。
        ⚠️ 解放者杯那条注释里的坑(日历年制不进表 ⇒ 3 月的比赛 AF 返回 0 场)
           在这里**不适用** —— 但判据必须是月份分布,不是「亚洲赛事大概是…」。
        """
        from nutmeg.v4.data.sources.api_football import CALENDAR_YEAR_LEAGUES
        assert self.CODE not in CALENDAR_YEAR_LEAGUES
        db = REPO / "data/v4_jingcai_history.db"
        if not db.exists():
            pytest.skip("没有竞彩历史库")
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            months = {r[0][5:7] for r in c.execute(
                "select distinct close_date from jingcai_odds_history "
                "where league_cn='亚冠精英' and close_date is not null")}
        assert len(months) >= 6, f"人口非平凡:只看到 {months}"
        assert {"06", "07"} & months == set(), f"6/7 月有比赛 ⇒ 不是秋春制了:{months}"


class TestTheBlockerIsOursNotTheSource:
    """⭐ 亚冠精英不出现在盘面上,**不是因为数据源没给**。

    三层原因,只有一层跟源有关,而那层不是堵点:
      ① 市场模式注册表(`routes.py` 的联赛白名单)**没有** AFC Champions League Elite
         ⇒ 我们从来没去要 —— 这是**我们的开关**。
      ② Odds API 确实没有亚冠的 sport key。但这不致命:荷乙同样没 sport key,
         照样走 AF 的 Pinnacle 镜像(见 `odds_api.SPORT_KEYS` 那条注释)。
      ③ 竞彩这场只开了**让球**、没开 1X2,且让球**不可单关**。

    这个类钉住 ①+② —— 免得下次有人凭「odds_snapshots 里没有」就断言「亚冠没法定价」。
    """

    def test_af_mirror_does_have_pinnacle_for_afc_cl_elite(self) -> None:
        odds_dir = REPO / "data/external/api_football/_odds"
        if not odds_dir.is_dir():
            pytest.skip("没有 AF 赔率缓存(worktree)")
        rows = _af_rows()
        afc = {r[4] for r in rows if r[1] == "AFC Champions League Elite"}
        assert afc, "人口非平凡:缓存里没有亚冠精英的场次,这条测不出东西"
        withpin = 0
        for f in odds_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                continue
            for o in (d if isinstance(d, list) else (d.get("response") or [])):
                if not isinstance(o, dict) or (o.get("fixture") or {}).get("id") not in afc:
                    continue
                if any("innacle" in (b.get("name") or "") for b in (o.get("bookmakers") or [])):
                    withpin += 1
        assert withpin > 0, (
            "AF 镜像里亚冠精英一场 Pinnacle 都没有 —— 那「源里没有」才成立,"
            "本类的叙述要重写")

    def test_the_asian_games_is_still_not_registered(self) -> None:
        """亚运女足**没有**跟着一起注册 —— 它连 AF fixture 都没有(见上一类)。

        这条红了 = 有人也把亚运加进去了 ⇒ 回来重判(那需要先有赛程和赔率)。
        """
        src = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        for key in ("ASIAN_GAMES", "ASIAD"):
            assert f'"{key}"' not in src
        assert '"JPN_J2"' in src, "人口非平凡:确认读的是那张表"


def test_the_archive_english_column_is_our_own_dictionary_flowing_back() -> None:
    """🚨 注册亚冠后覆盖率工具报硬缺口:**19/36 队 zh 字典打不中**。

    最顺手的修法是「档案里有中英文两列,配对就行」—— 那条路是**死的**。
    实测:`jingcai_odds_history` 里亚冠精英带英文的 24 支,**24/24 的英文都恰好
    等于我们词典现在解出来的值**,零条独立。⇒ 那一列是我们自己的词典回流,
    对**解不出的那些队**永远零证据(能解出的才会被写上英文)。

    (同 [[jingcai-vote-en-side-is-our-own-dict]]:数行数之前先查**那列是谁写的**。)

    ⇒ 这 19 支只能走 fixture 身份锚(同「棉农」那条),按竞彩上架逐个补。
    这条测试的作用是**挡住那条死路**,不是护栏 —— 它红了说明档案里出现了独立英文,
    那时这条路才重新可走。
    """
    db = REPO / "data/v4_jingcai_history.db"
    if not db.exists():
        pytest.skip("没有竞彩历史库")
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
        rows = c.execute(
            "select distinct home_zh, home_team from jingcai_odds_history "
            "where league_cn='亚冠精英' and home_team is not null "
            "union select distinct away_zh, away_team from jingcai_odds_history "
            "where league_cn='亚冠精英' and away_team is not null").fetchall()
    assert len(rows) >= 10, f"人口非平凡:只有 {len(rows)} 行"
    independent = [(z, e) for z, e in rows if zh_to_canonical(z) != e]
    assert not independent, (
        f"档案里出现了**独立**于我们词典的英文 {independent[:5]} —— "
        "那条配对路重新可走了,回来重判这 19 支")


class TestAsianGamesMenAnchored:
    """🏟️ 亚运**男**足(2026-09-15 横幅「整个联赛的在售场次全部解不出」)。

    ## 和亚运女足的关键差别

    女足那边 AF fixture 缓存**根本没有**这个赛事 ⇒ 只能锚队实体、join 不到东西。
    男足有:`Asian Games` 里是 14 场 **U23**(见 `TestTheHonestLimits`)。
    ⇒ 这批是**第①档锚**(当前在售那场本身),最强的一种。

    ## 锚

        竞彩  2026-09-15 10:30Z · 卡塔尔亚足 vs 韩国亚运男足(在售**仅此 1 场**)
        AF    `Asian Games` 同日 3 场(06:30/10:00/**10:30**),10:30 那格**唯一**:
              fixture 1639451 `Qatar U23` vs `Korea Republic U23`

    开球时刻 + 赛事 + **主客顺序**三者同时对上 ⇒ 名字对应由**位置**确定,
    不是按 Qatar=卡塔尔 翻的。

    ⚠️ 补完仍**算不出 EV**:`ASIAN_GAMES` 不在市场模式注册表、也不在 odds 覆盖里。
    """

    PAIRS = {"卡塔尔亚足": "Qatar U23", "卡塔尔亚": "Qatar U23",
             "韩国亚运男足": "Korea Republic U23", "韩国亚": "Korea Republic U23"}

    @pytest.mark.parametrize("zh", sorted(PAIRS))
    def test_both_spellings_resolve(self, zh: str) -> None:
        assert zh_to_canonical(zh) == self.PAIRS[zh]

    def test_the_senior_national_teams_are_untouched(self) -> None:
        """🚨 U23 和成年队是 AF 里**不同的实体**。补 U23 不许动成年队那两条。"""
        assert TEAM_NAME_ZH.get("Qatar") == "卡塔尔"
        assert TEAM_NAME_ZH.get("Korea Republic") == "韩国"
        assert zh_to_canonical("卡塔尔") == "Qatar"

    def test_the_anchor_is_a_unique_fixture_at_that_kickoff(self) -> None:
        """⭐ 断言挂在**被测对象**上:我们的映射必须等于 fixture 说的那两个名字。

        (不是「缓存里写着 Qatar U23」—— 那是缓存的事实,改了词典它照样绿。)
        """
        rows = _af_rows()
        slot = {r[4]: r for r in rows
                if r[0] == "2026-09-15T10:30:00" and r[1] == "Asian Games"}
        assert len(slot) == 1, f"该时刻该赛事不唯一({len(slot)} 场)⇒ 锚不成立"
        _, _, home, away, *_ = next(iter(slot.values()))
        assert zh_to_canonical("卡塔尔亚足") == home, f"主队锚到 {home!r}"
        assert zh_to_canonical("韩国亚运男足") == away, f"客队锚到 {away!r}"

    def test_the_abbreviations_went_to_the_override_table(self) -> None:
        assert _ZH_OVERRIDES.get("卡塔尔亚") == "Qatar U23"
        assert _ZH_OVERRIDES.get("韩国亚") == "Korea Republic U23"
        assert "卡塔尔亚足" not in _ZH_OVERRIDES, "全称该走 team_name_zh(它还负责显示)"


class TestNationalVariantsGetFlagsNotInitials:
    """🏳️ 国家队的**年龄组 / 女足**变体原本掉进「队徽/字母缩写」那条路。

    `_NATION_FLAG` 是**精确名**映射,`Qatar U23` 查不到 ⇒ 卡片上显示 "Qa"。

    ⭐ 为什么用 4 条精确映射而不是「剥掉后缀再查」的通用规则:
       实测全词典里剥后恰好等于国家名的**只有这 4 条、且 4 条全是真国家队**(零误判)。
       但通用规则会给**俱乐部青年队**发国旗(AF 命名成 `<俱乐部> U19/U21`),
       只要进来一支名字恰好等于国名的俱乐部青年队就静默错。
       省 4 行不值这个风险 —— 同 [[guard-remedy-is-not-neutral]] 的「处方不是中立的」。
    """

    def _flags(self) -> dict:
        import json
        import subprocess
        js = (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text()
        i = js.index("const _NATION_FLAG = {"); j = js.index("function teamLogo(name)")
        src = js[i:j] + "\nconsole.log(JSON.stringify(_NATION_FLAG));"
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:1500]
        return json.loads(r.stdout)

    def test_every_national_variant_in_the_dict_has_a_flag(self) -> None:
        """🚨 2026-09-16 改成**自己发现人口** —— 原来写死了 4 个名字。

        后果实测:同批又补了 5 个变体(China PR U23 / Korea DPR U23 / Japan U23 /
        Hong Kong U23 / Uzbekistan W),而变异「把 U23 国旗删掉」**照样全绿** ——
        写死名单的护栏只保护它当初列的那几个。
        ⇒ 同 [[hardcoded-guard-lists-rot]]:修法是让测试**自己发现人口**。

        不变量:词典里任何 `<国家名> <后缀>` 形式的键,只要 `<国家名>` 本身在
        国旗表里,**那个带后缀的键也必须在** —— 否则卡片退回字母缩写("Qa"/"Ch")。
        """
        import re
        f = self._flags()
        assert len(f) > 100, f"人口非平凡:只解析到 {len(f)} 个国家"
        variants = {}
        for key in TEAM_NAME_ZH:
            m = re.match(r"^(.*?)\s+(U\d\d|W|U\d\d W)$", key)
            if m and m.group(1) in f:
                variants[key] = m.group(1)
        assert len(variants) >= 9, (
            f"人口非平凡:只发现 {len(variants)} 个国家队变体,发现器可能坏了:{variants}")
        missing = {k: base for k, base in variants.items() if k not in f}
        assert not missing, (
            f"这些国家队变体没有国旗,卡片会退回字母缩写:{missing}\n"
            f"   ⇒ 在 `_NATION_FLAG` 里补上(底名的旗照抄)")
        # 旗必须和底名一致 —— 否则是抄错了国家
        wrong = {k: (f[k], f[b]) for k, b in variants.items() if f[k] != f[b]}
        assert not wrong, f"变体的旗和底名不一致(抄错国家?):{wrong}"

    def test_club_youth_teams_do_not_get_a_flag(self) -> None:
        """🚨 这条是上面那个设计决定的**承重面**:通用剥后缀会把这些染上国旗。"""
        f = self._flags()
        for club in ("Roma U20", "Swansea City U21", "Jong PSV U21", "Bayern Munich W"):
            assert club not in f, f"{club} 拿到了国旗 —— 俱乐部被当成国家了"

    def test_the_senior_entries_still_there(self) -> None:
        f = self._flags()
        for n in ("Qatar", "Korea Republic", "China", "Hong Kong"):
            assert f.get(n), f"{n} 的国旗掉了"


class TestBanner20260916:
    """📋 2026-09-16 横幅(5/27)· 亚运男足 + 亚运女足 + 欧罗巴。

    ⭐ **先逐名跑再动手**:横幅点 5 场,而 **3 个名字本来就是好的**
       (中国女足 / 霍芬海姆 / 利勒斯特罗姆)—— 横幅按**比赛**点名,不是按队。
       源码与 daemon 结果一致(都 5 场)⇒ 排除「改了没重启」(体检第 10 类)。

    四条锚全部**第①档**,且逐条验过唯一性;⭐ 其中两条靠「同场已解出的另一侧」
    把多候选缩到 1 —— 那正是这个锚源最不可替代的用法。
    """

    #: 竞彩中文(全称+简称)→ 英文规范名
    PAIRS = {
        "中国亚运男足": "China PR U23", "中国亚": "China PR U23",
        "朝鲜亚运男足": "Korea DPR U23", "朝鲜亚": "Korea DPR U23",
        "日本亚足": "Japan U23", "日本亚": "Japan U23",
        "中国香港亚运男足": "Hong Kong U23", "中国港亚": "Hong Kong U23",
        "乌兹别克斯坦女足": "Uzbekistan W", "乌兹别女": "Uzbekistan W",
        "克里特": "OFI",
        "托林斯": "Torreense",
    }
    #: (竞彩主, 竞彩客, 开球, AF 赛事, 哪一侧本来就解得出)
    ANCHORS = [
        ("中国亚运男足", "朝鲜亚运男足", "2026-09-16T10:00:00", "Asian Games", None),
        ("日本亚足", "中国香港亚运男足", "2026-09-16T10:30:00", "Asian Games", None),
        ("克里特", "霍芬海姆", "2026-09-17T16:45:00", "UEFA Europa League", "away"),
        ("利勒斯特罗姆", "托林斯", "2026-09-17T19:00:00", "UEFA Europa League", "home"),
        ("乌兹别克斯坦女足", "中国女足", "2026-09-17T05:00:00", "Asian Games Women", "away"),
    ]

    @pytest.mark.parametrize("zh", sorted(PAIRS))
    def test_every_spelling_resolves(self, zh: str) -> None:
        assert zh_to_canonical(zh) == self.PAIRS[zh]

    @pytest.mark.parametrize("case", ANCHORS, ids=lambda c: c[0])
    def test_each_anchor_is_unique_and_matches_our_mapping(self, case) -> None:
        """⭐ 断言挂在**被测对象**上:我们的映射必须等于 fixture 说的那两个名字。

        ⚠️ 唯一性**先于**取值:候选不唯一就不能据此断定对手,那时应当**留空**
           而不是挑一个(同 `score-anchored-name-mapping` 的「长得像是零证据」)。
        """
        hz, az, ko, comp, known = case
        rows = [r for r in _af_rows() if r[0] == ko and r[1] == comp]
        assert rows, f"缓存里没有 {comp} @{ko} —— 锚不成立"
        if known == "away":
            en = zh_to_canonical(az)
            assert en, f"声称已解出的那侧({az})其实解不出 —— 对照不成立"
            rows = [r for r in rows if r[3] == en]
        elif known == "home":
            en = zh_to_canonical(hz)
            assert en, f"声称已解出的那侧({hz})其实解不出 —— 对照不成立"
            rows = [r for r in rows if r[2] == en]
        uniq = list({r[4]: r for r in rows}.values())     # 按 fixture id 去重
        assert len(uniq) == 1, (
            f"{hz} vs {az}:候选 {len(uniq)} 场,**不唯一** ⇒ 不能据此断定对手")
        _, _, home, away, *_ = uniq[0]
        assert zh_to_canonical(hz) == home, f"主队:我们给 {zh_to_canonical(hz)!r},fixture 说 {home!r}"
        assert zh_to_canonical(az) == away, f"客队:我们给 {zh_to_canonical(az)!r},fixture 说 {away!r}"

    def test_the_two_multi_candidate_slots_really_needed_the_known_side(self) -> None:
        """🚨 承重:那两条 UEL 锚**不靠开球时刻单独成立** —— 同刻有多场。

        没有这条,「同场已解出的另一侧」这个机制看起来是多余的装饰。
        """
        rows = _af_rows()
        for ko, n_min in (("2026-09-17T16:45:00", 2), ("2026-09-17T19:00:00", 2)):
            slot = {r[4] for r in rows if r[0] == ko and r[1] == "UEFA Europa League"}
            assert len(slot) >= n_min, (
                f"{ko} 只有 {len(slot)} 场 —— 那这条锚不需要「已解出的另一侧」,"
                f"本类的叙述要重查")

    def test_seniors_and_other_age_grades_are_untouched(self) -> None:
        """🚨 U23 / W 和成年队在 AF 里是**不同实体**。补前者不许动后者。"""
        for en, zh in (("China PR", "中国"), ("Japan", "日本"), ("Hong Kong", "香港"),
                       ("Uzbekistan", "乌兹别克斯坦"), ("Korea Republic", "韩国")):
            assert TEAM_NAME_ZH.get(en) == zh, f"{en} 的中文被动了:{TEAM_NAME_ZH.get(en)!r}"

    def test_torreense_is_a_spelling_variant_not_a_new_team(self) -> None:
        """⭐ `托林斯` 是**情况①**:英文键早在词典里,只是竞彩换了写法。

        词典写「托雷恩塞」、竞彩写「托林斯」—— 按音猜不出来,只有 fixture 锚拿得到。
        ⇒ 它该进 `_ZH_OVERRIDES`,**不该**在 team_name_zh 里再造一个英文键。
        """
        assert TEAM_NAME_ZH.get("Torreense") == "托雷恩塞", "显示名被改了"
        assert _ZH_OVERRIDES.get("托林斯") == "Torreense"
        assert zh_to_canonical("托雷恩塞") == "Torreense", "原写法不该失效"
