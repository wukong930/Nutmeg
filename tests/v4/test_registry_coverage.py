"""体检 Wave2 — nutmeg-registry-coverage, the 「注册表即开关」structural vaccine.

Covers: the CRON_LEAGUES↔setup_local_pipeline.sh tripwire (the tool guards the
registries, THIS guards the tool's own league list), gap classification, and
the dict-reachability check against injected team tables.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from nutmeg.v4.cli.registry_coverage import CRON_LEAGUES, check_league, run

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

    def test_missing_sport_key_is_hard_gap(self):
        with patch("nutmeg.v4.data.sources.api_football.fetch_teams_for_league_season",
                   return_value=_teams()):
            rows, gaps, warns = run(["DNK_SUPERLIGA"])  # AF id ✓, sport key ✗
        assert any("sport key" in g for g in gaps)

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
        for lg in CRON_LEAGUES:
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
                    if t["team"]["name"] not in reachable]
            if miss:
                problems.append(f"{lg}: {miss}")
        assert not problems, "dict-unreachable teams reappeared:\n" + "\n".join(problems)
