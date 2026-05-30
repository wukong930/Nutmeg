"""V12 audit (post-V11) — league coverage guardrail.

Failure mode this prevents
--------------------------
On 2026-05-26 the user noticed two 竞彩 fixtures (法甲 + 德乙) that fell
inside our 14-league production training set, but the daily cron only
captured 1 of them. Root cause: ``BEL_PRO_LEAGUE`` was in:

  - ``data/historical_sources/football_data_co_uk/europe/<YY>YY/B1.csv``
    (5 seasons; model trained on it) ✓
  - ``scripts/setup_local_pipeline.sh`` LEAGUES list ✓
  - ``docs/PROJECT_OVERVIEW.md`` "14 trained leagues" section ✓

…but NOT in:

  - ``apps/api/src/nutmeg/v4/data/sources/api_football.py``
    ``_DOMESTIC_LEAGUE_IDS`` ✗

So the cron crashed silently on Belgian matches:
::

    [WARNING] BEL_PRO_LEAGUE fixtures error:
              no API-Football league ID for 'BEL_PRO_LEAGUE'

This violated the user's explicit ask ("能识别的没识别 不可接受").

Guardrail
---------
Two coupled assertions:

1. **setup-script ↔ registry parity** — every league listed in the
   production launchd plist must have an API-Football ID. Catches the
   exact bug above.

2. **registry → 14 expected** — the production set should be these 14
   European/Japan league codes. Stops anyone from silently removing
   a league.

These run on every PR + on every developer's local pytest. The cost is
two file reads and two set comparisons (microseconds).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS


REPO_ROOT = Path(__file__).resolve().parents[2]


# The 14 leagues our V5+ production model was trained on (per
# docs/PROJECT_OVERVIEW.md §3). Mostly European + Japan J1.
PRODUCTION_LEAGUES_14 = frozenset({
    # Top 5 European
    "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
    # 5 second-tier European
    "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
    "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
    # 3 other European
    "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA", "BEL_PRO_LEAGUE",
    # 1 Asian
    "JPN_J1",
})


def _parse_setup_script_leagues() -> set[str]:
    """Union every ``LEAGUES*="..."`` list declared in setup_local_pipeline.sh.

    Originally there was a single ``LEAGUES="..."`` variable. V12 W0's
    Option B region-split replaced it with ``LEAGUES_ASIAN="..."`` (J1,
    09:00 morning wave) + ``LEAGUES_EUROPEAN="..."`` (13 EU leagues, 14:00
    afternoon wave) so J1's noon kickoffs aren't missed. This parser unions
    all ``LEAGUES*=`` assignments so the guardrail keeps covering the full
    production set regardless of how the cron waves are partitioned.
    """
    script = REPO_ROOT / "scripts" / "setup_local_pipeline.sh"
    src = script.read_text()
    matches = re.findall(r'^LEAGUES\w*="([^"]+)"\s*$', src, re.M)
    assert matches, (
        f"could not locate any LEAGUES*=\"...\" in {script} — has the "
        "variable naming changed?"
    )
    leagues: set[str] = set()
    for group in matches:
        leagues.update(s.strip() for s in group.split(",") if s.strip())
    return leagues


class TestProductionLeagueCoverage:
    """The 14 production leagues must be registered everywhere they're
    referenced. A single missing entry breaks the daily cron silently."""

    def test_setup_script_lists_all_14_production_leagues(self):
        """scripts/setup_local_pipeline.sh's LEAGUES var = the 14 we trained on."""
        listed = _parse_setup_script_leagues()
        missing = PRODUCTION_LEAGUES_14 - listed
        extra = listed - PRODUCTION_LEAGUES_14
        assert not missing, (
            f"setup_local_pipeline.sh dropped production leagues: {missing}. "
            f"Re-add them or update PRODUCTION_LEAGUES_14 if scope changed."
        )
        assert not extra, (
            f"setup_local_pipeline.sh includes leagues NOT in production "
            f"training set: {extra}. Either train on them or remove from cron."
        )

    def test_dashboard_today_default_leagues_are_the_13_model_leagues(self):
        """V12 W3 — the dashboard's TODAY_DEFAULT_LEAGUES (the 今日推荐 MODEL
        board) must cover the model-scored set, not a 2-league subset.

        V12 W7 — that set is now the 13 European leagues; JPN_J1 is EXCLUDED
        because it's out-of-distribution for the European-trained model (it
        diverges ~13pp from the sharp J1 line). J1 is served via 市场模式
        (Pinnacle de-vig) instead. The cron still fetches J1 to warm the cache."""
        dash = REPO_ROOT / "apps" / "api" / "src" / "nutmeg" / "v4" / "api" / "static" / "dashboard.html"
        src = dash.read_text(encoding="utf-8")
        m = re.search(r"const TODAY_DEFAULT_LEAGUES\s*=\s*\[(.*?)\]", src, re.S)
        assert m is not None, "TODAY_DEFAULT_LEAGUES array not found in dashboard.html"
        listed = set(re.findall(r"'([A-Z0-9_]+)'", m.group(1)))
        model_13 = PRODUCTION_LEAGUES_14 - {"JPN_J1"}
        missing = model_13 - listed
        assert not missing, (
            f"dashboard 今日推荐 missing model leagues: {sorted(missing)}"
        )
        assert "JPN_J1" not in listed, (
            "JPN_J1 must NOT be in the MODEL board — it's OOD → 市场模式"
        )

    def test_j1_routed_to_market_mode_not_model(self):
        """V12 W7 — J1 is in the market-mode set and OUT of every model-scored
        league list (国际盘口 + 近期赛事). Same treatment as cups."""
        from nutmeg.v4.api.routes import (
            _CUP_MARKET_COMPETITIONS,
            _SP_CALC_LEAGUES,
        )
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        assert "JPN_J1" in _CUP_MARKET_COMPETITIONS, "J1 must be market-mode"
        assert "JPN_J1" not in _SP_CALC_LEAGUES, "J1 must be out of model 近期赛事"
        assert "JPN_J1" not in TodayRecommendationsRequest().leagues, (
            "J1 must be out of the model 今日推荐 default"
        )

    def test_every_setup_league_has_api_football_id(self):
        """The actual failure mode: production cron's --leagues list must
        be 100% resolvable via API-Football. Missing IDs cause silent
        per-league skip + WARNING log — exact bug surfaced 2026-05-26."""
        listed = _parse_setup_script_leagues()
        missing = sorted(
            league for league in listed
            if league not in API_FOOTBALL_LEAGUE_IDS
        )
        assert not missing, (
            f"{len(missing)} cron-listed leagues lack API-Football IDs: "
            f"{missing}. Open "
            f"apps/api/src/nutmeg/v4/data/sources/api_football.py and add "
            f"to _DOMESTIC_LEAGUE_IDS. This is the exact regression that "
            f"silently dropped Belgian matches on 2026-05-26."
        )

    def test_every_production_league_has_api_football_id(self):
        """Belt-and-suspenders: production set ⊆ API-Football registry."""
        missing = sorted(
            league for league in PRODUCTION_LEAGUES_14
            if league not in API_FOOTBALL_LEAGUE_IDS
        )
        assert not missing, (
            f"Production training leagues missing API-Football IDs: {missing}"
        )

    def test_api_football_ids_are_positive_ints(self):
        """Sanity: catches typos like None / 0 / negative."""
        for league, lid in API_FOOTBALL_LEAGUE_IDS.items():
            assert isinstance(lid, int), (
                f"{league} → {lid!r} is not int"
            )
            assert lid > 0, f"{league} → {lid} must be positive"

    def test_belgian_pro_league_specifically(self):
        """Regression: BEL_PRO_LEAGUE was silently missing pre-2026-05-26."""
        assert "BEL_PRO_LEAGUE" in API_FOOTBALL_LEAGUE_IDS
        # API-Football's id for Jupiler Pro League is 144 — pinning so a
        # future "let's renumber" can't silently break Belgian coverage.
        assert API_FOOTBALL_LEAGUE_IDS["BEL_PRO_LEAGUE"] == 144


class TestMarketModeExpansion:
    """V12 W8 — 10 竞彩-common leagues added to market mode (no model). Each
    needs an API-Football ID (to fetch fixtures+odds) AND a place in
    _CUP_MARKET_COMPETITIONS (to be served). Nordic/K-League/J2 are
    calendar-year; the rest run the European Aug–May calendar."""

    NEW = (
        "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "DNK_SUPERLIGA", "FIN_VEIKKAUSLIIGA",
        "KOR_K_LEAGUE_1", "JPN_J2", "AUS_A_LEAGUE", "SCO_PREMIERSHIP",
        "TUR_SUPER_LIG", "SUI_SUPER_LEAGUE",
    )

    def test_all_have_api_football_ids(self):
        for lg in self.NEW:
            assert lg in API_FOOTBALL_LEAGUE_IDS, f"{lg} missing API-Football ID"
            assert API_FOOTBALL_LEAGUE_IDS[lg] > 0

    def test_ids_pinned(self):
        """Pin the /leagues-verified IDs — a silent API renumber would
        otherwise fetch the wrong league with no error."""
        expect = {
            "NOR_ELITESERIEN": 103, "SWE_ALLSVENSKAN": 113, "DNK_SUPERLIGA": 119,
            "FIN_VEIKKAUSLIIGA": 244, "KOR_K_LEAGUE_1": 292, "JPN_J2": 99,
            "AUS_A_LEAGUE": 188, "SCO_PREMIERSHIP": 179, "TUR_SUPER_LIG": 203,
            "SUI_SUPER_LEAGUE": 207,
        }
        for lg, lid in expect.items():
            assert API_FOOTBALL_LEAGUE_IDS[lg] == lid

    def test_all_in_market_mode_list(self):
        from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS
        for lg in self.NEW:
            assert lg in _CUP_MARKET_COMPETITIONS

    def test_not_in_model_board(self):
        """They're market-mode only — must NOT enter the model-scored set."""
        from nutmeg.v4.api.routes import _SP_CALC_LEAGUES
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        for lg in self.NEW:
            assert lg not in _SP_CALC_LEAGUES
            assert lg not in TodayRecommendationsRequest().leagues
            assert lg not in PRODUCTION_LEAGUES_14

    def test_season_convention(self):
        import datetime as dt

        from nutmeg.v4.data.sources.api_football import season_for_date
        # Nordic / K-League / J2: a June date is mid-season of THAT calendar year
        for lg in ("NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "FIN_VEIKKAUSLIIGA",
                   "KOR_K_LEAGUE_1", "JPN_J2"):
            assert season_for_date(dt.date(2025, 6, 1), lg) == 2025
        # European new leagues: June belongs to the season that began prior August
        for lg in ("SCO_PREMIERSHIP", "TUR_SUPER_LIG", "SUI_SUPER_LEAGUE",
                   "DNK_SUPERLIGA", "AUS_A_LEAGUE"):
            assert season_for_date(dt.date(2025, 6, 1), lg) == 2024
