"""体检 Wave2 — nutmeg-registry-coverage, the 「注册表即开关」structural vaccine.

Covers: the CRON_LEAGUES↔setup_local_pipeline.sh tripwire (the tool guards the
registries, THIS guards the tool's own league list), gap classification, and
the dict-reachability check against injected team tables.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from nutmeg.v4.cli.registry_coverage import (
    CRON_LEAGUES,
    MARKET_MODE_LEAGUES,
    NO_CHINESE_NAME_EXISTS,
    NO_JINGCAI_ANCHOR,
    check_league,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCronLeagueTripwire:
    def test_cron_leagues_match_setup_script(self):
        """CRON_LEAGUES must equal LEAGUES_EUROPEAN + LEAGUES_ASIAN in
        setup_local_pipeline.sh — a cron-league edit that forgets the coverage
        tool would silently shrink the vaccine's own scope."""
        body = (REPO_ROOT / "scripts" / "setup_local_pipeline.sh").read_text()
        eur = re.search(r'^LEAGUES_EUROPEAN="([^"]+)"', body, re.M)
        asi = re.search(r'^LEAGUES_ASIAN="([^"]+)"', body, re.M)
        assert eur and asi, "setup_local_pipeline.sh league vars not found"
        script_set = {s.strip() for s in (eur.group(1) + "," + asi.group(1)).split(",")
                      if s.strip()}
        assert set(CRON_LEAGUES) == script_set, (
            f"CRON_LEAGUES drifted from setup_local_pipeline.sh: "
            f"only-in-tool={set(CRON_LEAGUES) - script_set} "
            f"only-in-script={script_set - set(CRON_LEAGUES)}"
        )

    def test_every_cron_league_has_sport_key(self):
        """体检 Wave2 W2-1 regression — 8/13 cron leagues had NO Odds-API sport
        key, so the fresher-line overlay + closing anchor never ran for them."""
        from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
        missing = [lg for lg in CRON_LEAGUES if lg not in SPORT_KEYS]
        assert not missing, f"cron leagues without a sport key: {missing}"

    def test_every_cron_league_has_af_id(self):
        from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS
        missing = [lg for lg in CRON_LEAGUES if lg not in API_FOOTBALL_LEAGUE_IDS]
        assert not missing, f"cron leagues without an AF league id: {missing}"


def _teams(*names):
    return [{"team": {"name": n}} for n in names]


class TestCheckLeague:
    def test_reachable_and_unreachable_split(self):
        # PSV Eindhoven reachable via the Wave2 override; a fake club is not.
        with patch("nutmeg.v4.data.sources.api_football.fetch_teams_for_league_season",
                   return_value=_teams("PSV Eindhoven", "FC Nonexistium")):
            r = check_league("NED_EREDIVISIE")
        assert r["af_id"] and r["sport_key"]
        assert r["n_teams"] == 2
        assert r["unreachable"] == ["FC Nonexistium"]

    def test_missing_sport_key_gap_only_for_cron_leagues(self):
        # 2026-07-04 — market-mode leagues price off the AF mirror by design:
        # a missing sport key is a WARN (设计内), never a hard gap. A cron league
        # without a key would still gate (guarded separately by
        # test_every_cron_league_has_sport_key). NB 2026-07-12: DNK/SCO/SUI/AUS/
        # TUR got real keys (/sports?all=true live-verified); JPN_J2 is now the
        # sole keyless market-mode league (Odds API has no J2, only J1).
        with patch("nutmeg.v4.data.sources.api_football.fetch_teams_for_league_season",
                   return_value=_teams()):
            rows, gaps, warns = run(["JPN_J2"])  # AF id ✓, sport key ✗ (no J2 key)
        assert not any("sport key" in g for g in gaps)
        assert any("设计内" in w for w in warns)

    def test_empty_table_is_warning_not_gap(self):
        with patch("nutmeg.v4.data.sources.api_football.fetch_teams_for_league_season",
                   return_value=_teams()):
            rows, gaps, warns = run(["EPL"])
        assert not gaps
        assert any("队表为空" in w for w in warns)

    def test_unknown_league_is_hard_gap(self):
        rows, gaps, warns = run(["MARS_SUPER_LEAGUE"])
        assert any("AF league-id" in g for g in gaps)




class TestLiveDictCoverage:
    def test_the_exemption_stays_narrow(self):
        """⭐ 豁免自身也要被看着 —— 一张没人看的豁免表最后会吞掉真缺口。

        钉死 4 个名字。加第 5 个必须让这条红一次,逼人写清楚证据。
        """
        assert len(NO_CHINESE_NAME_EXISTS) == 4
        assert all(n.startswith("Jong ") for n in NO_CHINESE_NAME_EXISTS), \
            "豁免只为荷乙预备队而设 —— 进来别的东西说明范围漂了"

    def test_the_derived_eerste_divisie_names_are_present(self):
        """13 条推导名必须真的在字典里 —— 否则豁免之外的部分是空的,
        本护栏就变成「荷乙整个联赛被跳过」而不是「4 支预备队被跳过」。"""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        for en, zh in [("De Graafschap", "格拉夫"), ("Roda", "罗达JC"),
                       ("Waalwijk", "瓦尔韦克"), ("FC Eindhoven", "埃因FC"),
                       ("Vitesse", "维迪斯")]:
            assert TEAM_NAME_ZH.get(en) == zh, en

    def test_cached_team_tables_fully_reachable(self):
        """The Wave2 dict fill's acceptance bar, as a permanent regression:
        every team in the CACHED AF tables must stay dict-reachable. Runs off
        the cache only (no network); a league with no cached table is skipped
        (the live tool warns on those instead)."""
        from datetime import UTC, datetime

        from nutmeg.v4.data.sources.api_football import (
            ApiFootballError,
            _cache_path,
            fetch_teams_for_league_season,
            league_id,
            season_for_date,
        )
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN

        reachable = {_EN_OVERRIDES.get(en, en) for en in _ZH_TO_EN.values()}
        today = datetime.now(UTC).date()
        problems = []
        # 2026-07-04 瑞超事件 — market-mode leagues joined the regression line
        # (their dict gaps drop 竞彩 SP just the same).
        for lg in CRON_LEAGUES + MARKET_MODE_LEAGUES:
            season = season_for_date(today, lg)
            cf = _cache_path("/teams", {"league": league_id(lg), "season": season},
                             Path("data/external/api_football"))
            if not cf.exists():
                continue  # never fetched — the live tool covers this case
            try:
                teams = fetch_teams_for_league_season(lg, season)
            except ApiFootballError:
                continue
            miss = [t["team"]["name"] for t in teams
                    if t["team"]["name"] not in reachable
                    and t["team"]["name"] not in NO_CHINESE_NAME_EXISTS
                    and t["team"]["name"] not in NO_JINGCAI_ANCHOR.get(lg, ())]
            if miss:
                problems.append(f"{lg}: {miss}")
        assert not problems, "dict-unreachable teams reappeared:\n" + "\n".join(problems)


def test_every_served_competition_is_either_checked_or_excused() -> None:
    """🚨 覆盖率工具的**作用域**本身也得有人看着。

    ⭐ 起因(2026-08-09):给解放者杯/欧超杯/沙职接完全部注册表,跑这个工具 ——
    **全绿,三个联赛一个字没提**。因为它从手写元组 `MARKET_MODE_LEAGUES` 迭代,
    新赛事它压根**没去看**。`CRON_LEAGUES` 有 tripwire(解析 setup 脚本比对),
    这条一直没有。

    ⚠️ 这正是本仓最贵的那一族:**「没有缺口」和「没去看那一格」长得一模一样**,
    而且是往**安全**的方向说谎 —— 体检绿灯 ⇒ 没人会去查。
    (同族:涓流 END 写成常量 ⇒「零新增」数学上必然;s6 空窗口;δ 无历史。)

    规矩:市场模式会服务、且有 AF id 的赛事,要么进 `MARKET_MODE_LEAGUES`
    (被真的检查),要么进 `OUT_OF_SCOPE` 并写明**为什么这套单元格对它没意义**。
    二选一,不许有第三种状态 —— 逼下次加赛事的人做个有意识的选择。

    ⛔ 故意**不**断言「作用域恰好等于某个集合」:那会在任何合理扩容时假红,
    而假红的护栏最后会被删掉。这里只断言「没有无人认领的」。
    """
    from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS
    from nutmeg.v4.cli.registry_coverage import (
        CRON_LEAGUES,
        MARKET_MODE_LEAGUES,
        OUT_OF_SCOPE,
    )
    from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS

    scope = set(CRON_LEAGUES) | set(MARKET_MODE_LEAGUES) | set(OUT_OF_SCOPE)
    served = {c for c in _CUP_MARKET_COMPETITIONS if API_FOOTBALL_LEAGUE_IDS.get(c)}
    orphans = sorted(served - scope)
    assert not orphans, (
        f"这些赛事会被市场模式服务,但覆盖率工具既不查、也没写明为什么不查:{orphans}。"
        f"进 MARKET_MODE_LEAGUES,或进 OUT_OF_SCOPE 并写理由。")

    # 理由不许是空串 —— 「写了一个占位符」等于没写
    blank = sorted(k for k, v in OUT_OF_SCOPE.items() if not str(v).strip())
    assert not blank, f"OUT_OF_SCOPE 里这些条目没写理由:{blank}"




def test_jingcai_listed_teams_are_fully_reachable() -> None:
    """🚨 真正会花钱的那条闸:**竞彩上架过的队**必须 100% 可解析。

    `_NO_JINGCAI_ANCHOR` 放行的是 AF 队表里竞彩从没卖过的队 —— 它们解析不出
    不会掉任何一条腿。但只要竞彩上架过,解析不出就等于**那场比赛的竞彩 SP 挂不上**,
    进而这场既进不了可投注列表、也不会有人发现(这正是 2026-07-04 瑞超 6 场
    静默消失的形状)。

    ⭐ 所以这条断言的人口是**会下注的人口**,不是 AF 的花名册 —— 与本仓
    「统计量必须在会下注的人口上算」「校准必须在真实竞彩线上测」同一条纪律。

    没有竞彩档案库时跳过(CI 上没有这个文件)。
    """
    import sqlite3

    from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES, _ZH_TO_EN

    db = Path("data/v4_jingcai_history.db")
    if not db.exists():
        pytest.skip("没有竞彩档案库 —— 这条断言只在本地有意义")

    resolvable = set(_ZH_TO_EN) | set(_ZH_OVERRIDES)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """SELECT league_cn, home_zh FROM jingcai_odds_history
                WHERE home_zh <> ''
                UNION
               SELECT league_cn, away_zh FROM jingcai_odds_history
                WHERE away_zh <> ''""").fetchall()
    finally:
        con.close()

    by_league: dict[str, set[str]] = {}
    for lg, zh in rows:
        by_league.setdefault(str(lg or "?"), set()).add(zh)

    # 只守本次新上的三个 —— 全库范围是另一件事(存量联赛有历史缺口,
    # 一次性拉齐会变成一条永远红的护栏,那种最后会被删掉)。
    watched = {"解放者杯", "沙职", "欧超杯"}
    gaps = {lg: sorted(t - resolvable)
            for lg, t in by_league.items()
            if lg in watched and (t - resolvable)}
    assert not gaps, (
        f"这些队竞彩**上架过**却解析不出 ⇒ 它们的竞彩 SP 挂不上、场次静默掉出"
        f"可投注列表:{gaps}。修法是跑 scripts/anchor_team_names_by_score.py,"
        f"⛔ 不是往 _NO_JINGCAI_ANCHOR 里加一行。")


def test_mapped_english_names_exist_in_real_fixture_data() -> None:
    """🚨 上一条能被**假修**:随便编一个英文名,横幅和体检立刻双绿,而 join 照样死。

    ⭐ 这是本仓 2026-08-06 记下的形态 ——「补显示别名会让护栏闭嘴而 join 照样死」。
    上一条只问「这个中文名解不解得出」,从不问「解出来的那串英文**存不存在**」。
    两条合起来才是完整的:能解析 **且** 解出来的东西在真实数据里出现过。

    这里的「真实数据」取 AF fixture 缓存 —— 因为这批是杯赛历史队,
    `odds_snapshots` 里未必有(采集窗口比它们的生命周期短,
    而「历史总行数=0」在那种情况下和「不存在」一模一样,不能当证据)。

    空包弹:把词典里任一条改成 `"Millonarioss"`(多一个 s)⇒ 上一条仍绿,这条红。
    """
    import json

    cache = Path("data/external/api_football/_fixtures")
    if not cache.exists():
        pytest.skip("没有 AF fixture 缓存 —— 这条只在本地有意义")

    from nutmeg.v4.data.sources.sporttery import zh_to_canonical
    from nutmeg.v4.data.team_name_zh import _LIBERTADORES_SAUDI_2026_08

    real: set[str] = set()
    for f in cache.glob("*.json"):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                 # noqa: BLE001, S112
            continue
        for r in (doc if isinstance(doc, list) else doc.get("response") or []):
            if not isinstance(r, dict):
                continue
            for side in ("home", "away"):
                n = ((r.get("teams") or {}).get(side) or {}).get("name")
                if n:
                    real.add(n)
    if not real:
        pytest.skip("缓存里没解析出任何队名 —— 这条断言此刻没有分母")

    # 🚨 断言的是 `zh_to_canonical()` 的**输出**,不是词典的 key。
    # ⭐ 08-12 审查抓到:第一版断言 key 存在,而 **join 用的是输出** ——
    #    别名遮蔽(另一条映射把同一个中文名劫走)和「两个真名张冠李戴」
    #    这两种形态都能让「查 key」全绿而 join 照样连错队。
    #    ⇒ 走真正跑着的那个函数,别查它的原料。
    resolved = {zh: zh_to_canonical(zh)
                for en, zh in _LIBERTADORES_SAUDI_2026_08.items()}
    ghosts = sorted(f"{zh}→{out!r}" for zh, out in resolved.items()
                    if out is None or out not in real)
    assert not ghosts, (
        f"这些中文名解出来的英文在 AF 真实赛程里查无此队:{ghosts}。"
        f"⇒ 横幅/体检会变绿(名字解析得出)但 join 会静默失败。"
        f"⛔ 修法是重新锚定,不是把它加进豁免名单。")

    # 别名遮蔽:词典里写 en→zh,但 zh 解回去必须是**同一个** en。
    # 不一致 = 有另一条映射把这个中文名劫走了,而「查 key」永远看不见。
    hijacked = sorted(f"{zh}: 词典说 {en!r} 但解析成 {resolved[zh]!r}"
                      for en, zh in _LIBERTADORES_SAUDI_2026_08.items()
                      if resolved[zh] != en)
    assert not hijacked, f"中文名被另一条映射劫走:{hijacked}"


def test_community_shield_is_registered_end_to_end() -> None:
    """🏆 社区盾(2026-08-16 注册)—— **注册 ≠ 生效**,四层都要通。

    竞彩 08-16 上架 `英社区盾 阿森纳 vs 曼彻斯特城`,而注册表里没有它。
    补一个 `Competition` 条目只是第一层;本条钉住它**一路通到采集器**。

    ⚠️ `api_football_id=528` 是从缓存**实证**的,不是查表猜的:
    AF 缓存里含 "Shield" 的联赛有 **3 个**(528 England / 534 CONCACAF /
    971 Kenya)⇒ **按名字匹配会撞车**。钉死它的是那场比赛本身
    (`2026-08-16T14:00Z Arsenal vs Manchester City · round=Final`)。

    ⚠️ 中文名 `英社区盾` 是**双源实证**:竞彩 `leagueAbbName` + 档案库
    `jingcai_odds_history.league_cn` 已有 66 行(往年同赛事)。
    ⛔ 不是意译 —— 意译得到「英格兰社区盾杯」,和两个源都对不上。
    """
    from nutmeg.v4.data.competitions import (
        CUP_COMPETITIONS,
        api_football_id_for_cup,
        cup_codes,
        is_club_cup_competition,
    )
    from nutmeg.v4.data.league_labels import (
        TRAINED_LEAGUES_CN,
        canonical_league,
        classify_league,
    )
    from nutmeg.v4.data.sources.api_football import (
        API_FOOTBALL_LEAGUE_IDS,
        CALENDAR_YEAR_LEAGUES,
    )

    CODE, CN = "COMMUNITY_SHIELD", "英社区盾"

    # ① 注册表
    assert CODE in CUP_COMPETITIONS
    assert api_football_id_for_cup(CODE) == 528
    assert is_club_cup_competition(CODE), "社区盾是俱乐部杯赛"
    assert CODE in cup_codes()

    # ② 标签双向归一(竞彩写中文,盘面写英文键 —— 两条都得通)
    assert canonical_league(CODE) == CN
    assert canonical_league(CN) == CN

    # ③ 🚨 **采集器**真的认得它 —— 这一层是「注册 ≠ 生效」的分界:
    #    `API_FOOTBALL_LEAGUE_IDS` 由 `_merged_league_ids()` 合并杯赛注册表得来,
    #    若哪天有人把它改回硬编码,注册表加条目就**不再传导**,而没有任何东西会喊。
    assert API_FOOTBALL_LEAGUE_IDS.get(CODE) == 528, (
        "社区盾没进 API_FOOTBALL_LEAGUE_IDS ⇒ 采集器不会去拉它,"
        "而注册表看起来是好的 —— 典型的「注册了但不生效」")

    # ④ 季口径:**不**进 CALENDAR_YEAR_LEAGUES(8 月 = 英格兰赛季揭幕)
    #    实测 season_for_date(2026-08-16) = 2026 = AF 缓存标的 season。
    #    ⛔ 进了会按日历年拉 ⇒ 拉错季 ⇒ **静默返回 0 场**。
    assert CODE not in CALENDAR_YEAR_LEAGUES

    # ⑤ ⛔ 国内俱乐部杯赛 ⇒ 不进 δ 的拟合人口(δ 拟合在各国**联赛** CSV 上)
    #
    # 🚨 **本条 2026-08-16 修过一次,原版是空转断言。**
    # 原版写的是 `CN not in TRAINED_LEAGUES_CN` —— 但 `英社区盾` **本来就不在**
    # 那个集合里,所以把它从 `_NON_DOMESTIC_CN`(我真正加的那个集合)删掉之后,
    # 断言照样绿。空包弹 `into_delta_pop` 当场抓住。
    # ⭐ 同族:Coventry/Leeds 那条「断言了一件不可能为假的事」。
    # ⇒ 改成断言**行为出口** `classify_league`:它才是 P3 计数真正读的东西。
    #   `excluded` = 已知大赛/杯赛,静默排除;`unknown` = 没见过,**必须被报出来**。
    assert classify_league(CN) == "excluded", (
        f"{CN} 应被判为 excluded(国内俱乐部杯赛,不进 δ 拟合人口),"
        f"实际 {classify_league(CN)!r}。若是 'unknown' 说明标签没注册;"
        f"若是 'domestic' 说明它被当成国内**联赛**混进了 δ 的人口。")
    assert classify_league(CODE) == "excluded", "EN 轨同样要排除"
    assert CN not in TRAINED_LEAGUES_CN   # 顺带(本来就不在,留作可读性)
