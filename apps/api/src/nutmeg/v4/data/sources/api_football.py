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
API_FOOTBALL_LEAGUE_IDS: dict[str, int] = {
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
    "JPN_J1": 98,
}


def league_id(canonical: str) -> int:
    if canonical not in API_FOOTBALL_LEAGUE_IDS:
        raise ApiFootballError(f"no API-Football league ID for {canonical!r}")
    return API_FOOTBALL_LEAGUE_IDS[canonical]


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
        # season heuristic: a fixture in Aug-Dec uses calendar year as start;
        # Jan-Jul uses previous calendar year. API-Football's `season` param
        # is the year the season started in. 2024-08-01 → season=2024.
        season = on_date.year if on_date.month >= 7 else on_date.year - 1
        params["season"] = season
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


__all__ = [
    "API_FOOTBALL_LEAGUE_IDS",
    "ApiFootballError",
    "fetch_fixtures_for_date",
    "fetch_lineups",
    "fetch_injuries",
    "fetch_odds",
    "fetch_status",
    "league_id",
]
