"""API-Football adapter — V6 W1.

Paid subscription ($19/mo Pro plan, 7.5k requests/day). Provides:
- fixtures (with status, score, half-time score)
- lineups (starting XI + substitutes; available ~1 hour pre-kickoff)
- injuries (current squad injury list)
- odds (multi-book pre-match 1X2 / handicap / O/U; NOT 中国竞彩 SP)

The credential lives in `.env` (gitignored) at `NUTMEG_API_FOOTBALL_KEY`.
All requests carry it as the `x-apisports-key` header.

Rate budget at Pro plan:
    7,500 calls/day = ~5 calls/min sustained.
    Daily workload: 13 leagues × 10 fixtures × {fixtures, odds, lineups,
    injuries} = ~500 calls/day. Headroom 15x.

Cache strategy:
    Each fetch_* writes a per-call JSON to
    data/external/api_football/<endpoint>/<params-hash>.json
    so repeated debugging hits don't burn quota. `refresh=True` bypasses
    cache (used by the daily cron).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from nutmeg.config import get_settings


log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/external/api_football")


class ApiFootballError(RuntimeError):
    """Raised when the API returns a non-2xx, an error payload, or no key is set."""


def _client() -> httpx.Client:
    settings = get_settings()
    if not settings.api_football_key:
        raise ApiFootballError(
            "NUTMEG_API_FOOTBALL_KEY is not set. Add it to .env or env vars."
        )
    return httpx.Client(
        base_url=settings.api_football_base_url,
        headers={"x-apisports-key": settings.api_football_key},
        timeout=settings.api_football_timeout_seconds,
    )


def _cache_path(endpoint: str, params: dict[str, Any], cache_dir: Path) -> Path:
    """One JSON per (endpoint, params)."""
    payload = json.dumps(params, sort_keys=True, default=str).encode()
    h = hashlib.sha1(payload).hexdigest()[:12]
    safe_endpoint = endpoint.replace("/", "_")
    return cache_dir / safe_endpoint / f"{h}.json"


def _request(
    endpoint: str,
    params: dict[str, Any],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Make one API-Football request; cache by (endpoint, params).

    The API returns a JSON envelope with shape:
        { "get": ..., "parameters": ..., "errors": ..., "results": N,
          "response": [...] }

    We return ``response`` (the array of records) and raise if ``errors``
    is non-empty.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = _cache_path(endpoint, params, cache_dir)
    cf.parent.mkdir(parents=True, exist_ok=True)
    if cf.exists() and not refresh:
        return json.loads(cf.read_text())

    with _client() as c:
        r = c.get(endpoint, params=params)
    if r.status_code != 200:
        raise ApiFootballError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    errs = body.get("errors")
    if errs:
        # api-sports puts errors in either {} (empty) or {key: msg}
        if isinstance(errs, dict) and errs:
            raise ApiFootballError(f"{endpoint} errors: {errs}")
        if isinstance(errs, list) and errs:
            raise ApiFootballError(f"{endpoint} errors: {errs}")

    response = body.get("response", [])
    cf.write_text(json.dumps(response, indent=2, ensure_ascii=False))
    return response


# ----- league + season ID resolution ------------------------------------

# Mapping from our canonical league codes → API-Football league IDs.
# Acquired by calling /leagues with a name query and recording the IDs once.
# Reference: https://www.api-football.com/documentation-v3#tag/Leagues
_DOMESTIC_LEAGUE_IDS: dict[str, int] = {
    "EPL": 39,
    "ESP_LA_LIGA": 140,
    "ITA_SERIE_A": 135,
    "GER_BUNDESLIGA": 78,
    "FRA_LIGUE_1": 61,
    "ENG_CHAMPIONSHIP": 40,
    "ESP_SEGUNDA_DIVISION": 141,
    "ITA_SERIE_B": 136,
    "GER_2_BUNDESLIGA": 79,
    "FRA_LIGUE_2": 62,
    "NED_EREDIVISIE": 88,
    "PRT_PRIMEIRA_LIGA": 94,
    # post-V12 audit (2026-05-26): BEL_PRO_LEAGUE was missing here despite
    # being in our 14-league production training set (data/historical_sources
    # /football_data_co_uk/europe/<YY>YY/B1.csv covers 5 seasons of Belgian
    # Jupiler Pro League). The daily cron would silently skip every Belgian
    # match with "no API-Football league ID for 'BEL_PRO_LEAGUE'" — see
    # tests/v4/test_league_coverage.py for the guardrail.
    "BEL_PRO_LEAGUE": 144,   # Jupiler Pro League (Belgium)
    "JPN_J1": 98,
    # V12 W8 — 市场模式 expansion (2026-05-30). Not trained on; served via
    # market mode (Pinnacle de-vig 1X2 + reverse 让球). IDs verified against
    # API-Football /leagues?current=true. 竞彩-common + Pinnacle-priced.
    "NOR_ELITESERIEN": 103,     # Norway   (calendar-year)
    "SWE_ALLSVENSKAN": 113,     # Sweden   (calendar-year)
    "DNK_SUPERLIGA": 119,       # Denmark  (Jul–May, European)
    "FIN_VEIKKAUSLIIGA": 244,   # Finland  (calendar-year)
    "KOR_K_LEAGUE_1": 292,      # S. Korea (calendar-year)
    "JPN_J2": 99,               # Japan J2 (calendar-year)
    "AUS_A_LEAGUE": 188,        # Australia (Oct–May, European)
    "SCO_PREMIERSHIP": 179,     # Scotland (Aug–May, European)
    "TUR_SUPER_LIG": 203,       # Turkey   (Aug–May, European)
    "SUI_SUPER_LEAGUE": 207,    # Switzerland (Jul–May, European)
}

# Cup + national-team competition IDs (V6 W11). Merged into the public
# API_FOOTBALL_LEAGUE_IDS dict below so existing callers using
# `league_id("UCL")` work without code changes.
def _merged_league_ids() -> dict[str, int]:
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS
    merged = dict(_DOMESTIC_LEAGUE_IDS)
    for code, comp in CUP_COMPETITIONS.items():
        if comp.api_football_id is not None:
            merged[code] = comp.api_football_id
    return merged


API_FOOTBALL_LEAGUE_IDS: dict[str, int] = _merged_league_ids()


def league_id(canonical: str) -> int:
    if canonical not in API_FOOTBALL_LEAGUE_IDS:
        raise ApiFootballError(f"no API-Football league ID for {canonical!r}")
    return API_FOOTBALL_LEAGUE_IDS[canonical]


# Calendar-year leagues run within ONE calendar year (≈Feb–Dec), so the
# API-Football ``season`` param is the date's calendar year — NOT the European
# Aug–Jul "year the season started" convention. Add codes here as more
# calendar-year leagues (other Asian / Nordic / Americas) enter the set.
CALENDAR_YEAR_LEAGUES: frozenset[str] = frozenset({
    "JPN_J1",
    # V12 W8 — Nordic + K-League + J2 run ≈Feb–Nov (one calendar year). The
    # other new market-mode leagues (Denmark/Scotland/Turkey/Switzerland/
    # Australia) run Aug/Oct–May → the European heuristic is correct for them.
    "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "FIN_VEIKKAUSLIIGA",
    "KOR_K_LEAGUE_1", "JPN_J2",
})


def season_for_date(on_date: date, league_canonical: str | None = None) -> int:
    """API-Football ``season`` (the year a season started) for a date.

    European leagues run Aug–May, so a Jan–Jul date belongs to the *previous*
    year's season (2026-05 → 2025). Calendar-year leagues (J-League etc.) run
    within one calendar year, so the season is simply the date's year
    (2026-05 → 2026).

    Getting this wrong silently returns 0 fixtures: querying a J1 spring date
    under the European heuristic asks for the prior, already-finished season —
    which is exactly why next-day J1 fixtures went undetected (V12 W4 bug).
    """
    if league_canonical in CALENDAR_YEAR_LEAGUES:
        return on_date.year
    return on_date.year if on_date.month >= 7 else on_date.year - 1


# ----- fetchers ---------------------------------------------------------

def fetch_fixtures_for_date(
    on_date: date,
    league_canonical: str | None = None,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Pull all fixtures on the given UTC date, optionally filtered to one league."""
    params: dict[str, Any] = {"date": on_date.isoformat()}
    if league_canonical:
        params["league"] = league_id(league_canonical)
        # Season is league-aware: European leagues use the Aug–Jul heuristic,
        # calendar-year leagues (J1 etc.) use the date's year. See
        # season_for_date — getting this wrong returns 0 fixtures.
        params["season"] = season_for_date(on_date, league_canonical)
    return _request("/fixtures", params, cache_dir=cache_dir, refresh=refresh)


def fetch_fixtures_for_league_season(
    league_canonical: str,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """V10 W1 Track B Day 4 — pull ALL fixtures for one (league, season).

    Returns both NS (upcoming) and FT (finished) fixtures. Used by the
    WC predict CLI which needs the full tournament schedule, not just
    one day. The season-based query is also more cache-friendly for
    repeated calls within a tournament window.
    """
    params = {
        "league": league_id(league_canonical),
        "season": season,
    }
    return _request("/fixtures", params, cache_dir=cache_dir, refresh=refresh)


def fetch_lineups(
    fixture_id: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Two-element list: home team + away team lineup (starting XI + subs).

    Available roughly 1 hour pre-kickoff. Returns empty when not yet published.
    """
    return _request("/fixtures/lineups", {"fixture": fixture_id},
                    cache_dir=cache_dir, refresh=refresh)


def fetch_injuries(
    team_id: int,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Current injury list for a team in a season."""
    return _request("/injuries", {"team": team_id, "season": season},
                    cache_dir=cache_dir, refresh=refresh)


def fetch_odds(
    fixture_id: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Pre-match odds across all books carried by API-Football for one fixture."""
    return _request("/odds", {"fixture": fixture_id},
                    cache_dir=cache_dir, refresh=refresh)


def fetch_status() -> dict[str, Any]:
    """Subscription status; useful for cron health checks."""
    return _request("/status", {})  # singleton response, len=1


def fetch_teams_for_league_season(
    league_canonical: str,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """All teams in a league + season — used to harvest logo URLs.

    Each record contains ``team`` (id/name/logo) + ``venue``. V11 P1-FE#2
    uses this to ingest team logos for the dashboard.
    """
    return _request(
        "/teams",
        {"league": league_id(league_canonical), "season": season},
        cache_dir=cache_dir,
        refresh=refresh,
    )


def fetch_team_squad_stats(
    team_id: int,
    season: int,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """Per-player season stats for a team's full squad.

    Used by V6 W2 lineup features to compute `xi_minutes_share`: of the
    11 players starting today, how much of this season's starting-XI
    workload are they collectively responsible for? Sub-1.0 indicates
    rotation / rest / injury-driven changes (less reliable XI), 1.0
    means today's XI mirrors the season's most-trusted XI.

    The endpoint returns one record per (player, league) — we filter
    to the requested league and aggregate by player_id outside.
    """
    return _request("/players", {"team": team_id, "season": season},
                    cache_dir=cache_dir, refresh=refresh)


def compute_xi_minutes_share(
    starting_xi_player_ids: list[int],
    squad_stats: list[dict[str, Any]],
) -> float:
    """Given today's starting XI (player IDs) and the season squad stats,
    compute the fraction of total season-starting minutes those 11 players
    contributed.

    Returns 1.0 when starting_xi is empty (no XI to evaluate yet) — caller
    should pair with the lineup_present_flag to interpret.
    Returns 0.5 (safe placeholder) when squad_stats is empty.
    """
    if not starting_xi_player_ids:
        return 1.0
    if not squad_stats:
        return 0.5

    total_starts = 0
    xi_starts = 0
    xi_set = set(starting_xi_player_ids)
    for record in squad_stats:
        player_id = record.get("player", {}).get("id")
        stats_list = record.get("statistics", [])
        # API-Football returns multiple stats blobs per player (one per
        # competition). Sum starts across all of them.
        player_starts = sum(
            (s.get("games", {}).get("lineups") or 0) for s in stats_list
        )
        total_starts += player_starts
        if player_id in xi_set:
            xi_starts += player_starts

    if total_starts <= 0:
        return 0.5
    # Normalize: max is 11 * (total_starts / 11) = total_starts when the
    # team's 11 most-used players are starting; ratio is xi_starts / max_possible
    return min(1.0, max(0.0, xi_starts / total_starts))


__all__ = [
    "API_FOOTBALL_LEAGUE_IDS",
    "ApiFootballError",
    "fetch_fixtures_for_date",
    "fetch_lineups",
    "fetch_injuries",
    "fetch_odds",
    "fetch_status",
    "fetch_team_squad_stats",
    "compute_xi_minutes_share",
    "league_id",
]
