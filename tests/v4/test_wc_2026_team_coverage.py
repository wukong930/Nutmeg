"""V12 W0 (2026-05-28) —守门 WC 2026 三层覆盖一致性.

Verifies that **every one of the 48 WC 2026 participants** has:

1. A `TEAM_NAME_TO_ELO_CODE` mapping (V10 W1 Track B Day 2) — required
   for the WC predictor to resolve team names to eloratings 2-letter codes.

2. Real Elo data in the eloratings snapshot — without this the prediction
   falls back to None and the WC model can't score the fixture.

3. A `TEAM_NAME_ZH` translation — required for the dashboard WC tab to
   render Chinese names instead of raw English (the bug that triggered
   this audit on 2026-05-27 was "墨西哥 vs South Africa").

The 48-team list is locked at WC 2026 group-stage start (FIFA's draw,
pulled directly from API-Football league=1 season=2026 on 2026-05-28).
If FIFA changes participants (extremely rare post-draw), update the
constant below.

The test purposely runs against the *real* eloratings parquet (not a
mock) so a stale or broken snapshot fails CI.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


# Pulled 2026-05-28 via:
#   GET https://v3.football.api-sports.io/fixtures?league=1&season=2026
# All 48 entries are exact API-Football spellings (matters for & vs and,
# Islands suffix, "Türkiye" vs "Turkey", etc).
WC_2026_TEAMS: list[str] = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia & Herzegovina", "Brazil", "Canada", "Cape Verde Islands",
    "Colombia", "Congo DR", "Croatia", "Curaçao", "Czech Republic",
    "Ecuador", "Egypt", "England", "France", "Germany", "Ghana",
    "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan",
    "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
    "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia",
    "Scotland", "Senegal", "South Africa", "South Korea", "Spain",
    "Sweden", "Switzerland", "Tunisia", "Türkiye", "USA", "Uruguay",
    "Uzbekistan",
]


REPO_ROOT = Path(__file__).resolve().parents[2]
ELORATINGS_DIR = REPO_ROOT / "data" / "external" / "eloratings"


def test_wc_2026_has_48_teams():
    """Sanity check: WC 2026 has exactly 48 teams (the new expanded format)."""
    assert len(WC_2026_TEAMS) == 48, (
        f"Expected 48 WC 2026 teams, got {len(WC_2026_TEAMS)}. "
        "If FIFA changed the format, update the constant in this test."
    )


def test_all_wc_2026_teams_have_elo_code_mapping():
    """Every WC 2026 team name must resolve to an eloratings 2-letter code."""
    from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code

    missing = [t for t in WC_2026_TEAMS if lookup_elo_code(t) is None]
    assert not missing, (
        f"{len(missing)} WC 2026 team(s) missing from TEAM_NAME_TO_ELO_CODE: "
        f"{missing}. Add to apps/api/src/nutmeg/v4/data/national_team_name_to_elo.py."
    )


def test_all_wc_2026_teams_have_zh_translation():
    """Every WC 2026 team name must have a Chinese translation.

    Triggering case (2026-05-27): the dashboard's WC tab displayed
    "墨西哥 vs South Africa" because South Africa was not in TEAM_NAME_ZH.
    Same root cause for "Cape Verde Islands" → 佛得角.
    """
    from nutmeg.v4.data.team_name_zh import lookup_zh

    # `lookup_zh` returns the input unchanged when there's no mapping,
    # so an English-only result means it's missing.
    missing = []
    for t in WC_2026_TEAMS:
        zh = lookup_zh(t)
        if zh == t:  # passthrough → no zh entry
            missing.append(t)
    assert not missing, (
        f"{len(missing)} WC 2026 team(s) missing from TEAM_NAME_ZH: "
        f"{missing}. Add to apps/api/src/nutmeg/v4/data/team_name_zh.py's "
        f"_NATIONAL_TEAMS section."
    )


def test_all_wc_2026_teams_resolve_to_real_elo_data():
    """Every WC 2026 team's elo_code must have a row in the eloratings parquet.

    Without this, the WC predictor's `_elo_for(team_name)` returns None
    and the fixture can't be scored.
    """
    from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code

    # Use the most-recent snapshot
    snapshots = sorted(ELORATINGS_DIR.glob("eloratings_*.parquet"))
    if not snapshots:
        pytest.skip(
            "No eloratings snapshot found (data/external/eloratings/*.parquet); "
            "scrape one before running this guardrail."
        )
    df = pd.read_parquet(snapshots[-1])
    available_codes = set(df["country_code"].unique())

    missing = []
    for t in WC_2026_TEAMS:
        code = lookup_elo_code(t)
        if code is None:
            # Caught by separate test; skip here to surface a focused message
            continue
        if code not in available_codes:
            missing.append((t, code))

    assert not missing, (
        f"{len(missing)} WC 2026 team(s) have a TEAM_NAME_TO_ELO_CODE "
        f"mapping but no eloratings parquet row: {missing}. "
        f"Re-scrape the eloratings snapshot or check the 2-letter codes."
    )


def test_wc_2026_elo_codes_are_all_2_letter_lowercase_uppercase_mixed():
    """Sanity: eloratings codes are 2-character country codes (e.g. ES, AR, ZA).

    Catches typos that would silently fail the parquet lookup.
    """
    from nutmeg.v4.data.national_team_name_to_elo import TEAM_NAME_TO_ELO_CODE

    for name, code in TEAM_NAME_TO_ELO_CODE.items():
        assert len(code) == 2, f"{name!r} has non-2-letter code {code!r}"
        assert code.isalpha(), f"{name!r} has non-alpha code {code!r}"
        assert code == code.upper(), (
            f"{name!r} has lowercase code {code!r}; eloratings uses uppercase."
        )
