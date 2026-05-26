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
    """Extract the LEAGUES env var value from setup_local_pipeline.sh.

    The fix on 2026-05-26 introduced a `LEAGUES="..."` shell variable
    that the daily_odds + daily_recommend plists consume. This parser
    reads the literal value so the test stays in sync.
    """
    script = REPO_ROOT / "scripts" / "setup_local_pipeline.sh"
    src = script.read_text()
    m = re.search(r'^LEAGUES="([^"]+)"\s*$', src, re.M)
    assert m is not None, (
        f"could not locate LEAGUES=\"...\" in {script} — has the variable "
        "name changed?"
    )
    return set(s.strip() for s in m.group(1).split(",") if s.strip())


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
