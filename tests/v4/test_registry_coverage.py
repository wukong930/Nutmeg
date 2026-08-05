"""体检 Wave2 — nutmeg-registry-coverage, the 「注册表即开关」structural vaccine.

Covers: the CRON_LEAGUES↔setup_local_pipeline.sh tripwire (the tool guards the
registries, THIS guards the tool's own league list), gap classification, and
the dict-reachability check against injected team tables.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from nutmeg.v4.cli.registry_coverage import (
    CRON_LEAGUES,
    MARKET_MODE_LEAGUES,
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


#: ⛔ 窄豁免:**中文名不存在**,不是「还没补」。
#:
#: 2026-08-05 注册荷乙时,本护栏当场逮到 17 支球队没有中文名 —— 正是它该做的。
#: 其中 13 支从皇冠线史推导出了中文名(见 `team_name_zh._V12_W8_NEW_LEAGUES` 里
#: 那段)。剩下这 4 支是**预备队**,证据说它们的中文名根本不存在:
#:
#:   `crown_close_history` 里 荷乙 105 场、19 个不同的中文队名,**一支预备队都
#:   没有** ⇒ 竞彩不上架它们 ⇒ 它们永远不会成为一条可投注的腿 ⇒ 没有可抄的
#:   中文写法。编一个是瞎猜(而错的队名会静默污染 join,比缺名字更坏)。
#:
#: ⚠️ 为什么**逐条列名**而不是写 `name.startswith("Jong ")`:那是拿「名字里有
#: 没有某串字符」代替「它是不是一支竞彩不上架的预备队」—— 同一个反复出现的
#: 错误(见 [[syntactic-proxy-for-semantic-property]])。前缀规则会顺手放行任何
#: 未来叫 Jong 开头的**一队**,而这四个名字变了就该重新报警。
#:
#: 若哪天竞彩真的上架了预备队,ingest 侧的「整联赛丢失 / 过半未映射」报警会响。
_NO_CHINESE_NAME_EXISTS: frozenset[str] = frozenset({
    "Jong Ajax", "Jong AZ", "Jong PSV U21", "Jong Utrecht",
})


class TestLiveDictCoverage:
    def test_the_exemption_stays_narrow(self):
        """⭐ 豁免自身也要被看着 —— 一张没人看的豁免表最后会吞掉真缺口。

        钉死 4 个名字。加第 5 个必须让这条红一次,逼人写清楚证据。
        """
        assert len(_NO_CHINESE_NAME_EXISTS) == 4
        assert all(n.startswith("Jong ") for n in _NO_CHINESE_NAME_EXISTS), \
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
                    and t["team"]["name"] not in _NO_CHINESE_NAME_EXISTS]
            if miss:
                problems.append(f"{lg}: {miss}")
        assert not problems, "dict-unreachable teams reappeared:\n" + "\n".join(problems)
