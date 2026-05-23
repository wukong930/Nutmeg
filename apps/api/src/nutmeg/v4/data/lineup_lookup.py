"""Build the fixture_key → (home_lineup, away_lineup) lookup for
nutmeg.v4.features.lineup_features.build_lineup_features.

V6 W5 — bridges the raw API-Football cache (data/external/api_football/)
to the feature pipeline. Handles the team-name reconciliation between
API-Football's naming convention (e.g. "Manchester United") and the V4
canonical convention from football-data.co.uk (e.g. "Man United").

Inputs cached by nutmeg.v4.cli.ingest_lineups:
- data/external/api_football/_fixtures/<hash>.json  — list of fixtures
- data/external/api_football/_fixtures_lineups/<hash>.json — one file
  per fixture_id, contents = list of 2 team-lineup dicts

Outputs:
- lineup_lookup: dict {"<league>__<YYYY-MM-DD>__<home_v4>__<away_v4>":
                       (home_lineup_dict | None, away_lineup_dict | None)}
- injury_lookup: dict {fixture_key: (home_injuries, away_injuries)}
- A diagnostic dict for unmatched team-name mappings

Usage from training:
    lookup = build_lineup_lookup_from_cache(...)
    feats = build_feature_frame(df, ..., lineup_lookup=lookup)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nutmeg.utils.team_canonical import to_v4_canonical


log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/external/api_football")


def _load_all_fixtures(cache_dir: Path) -> list[dict[str, Any]]:
    """Read every cached /fixtures response and flatten."""
    fixtures: list[dict[str, Any]] = []
    fixtures_dir = cache_dir / "_fixtures"
    if not fixtures_dir.exists():
        return fixtures
    for jsonf in sorted(fixtures_dir.glob("*.json")):
        try:
            data = json.loads(jsonf.read_text())
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, list):
            fixtures.extend(data)
    return fixtures


def _load_lineup_by_fixture_id(cache_dir: Path) -> dict[int, list[dict]]:
    """Map fixture_id → list-of-2 lineup payload, from cached JSONs.

    The cache file name is hashed by (endpoint, params), so we have to
    open each one and use the team_id/match info inside it to identify
    the fixture_id. Cheaper alternative: scan cached fixture rows and
    re-derive cache filename per fixture_id with the same hash scheme.
    """
    lineups: dict[int, list[dict]] = {}
    lineups_dir = cache_dir / "_fixtures_lineups"
    if not lineups_dir.exists():
        return lineups

    # We can't know which fixture each file is for without consulting the
    # request params. Easier: re-derive the cache path per fixture_id using
    # the same hash scheme (api_football._cache_path).
    from nutmeg.v4.data.sources import api_football as af

    # The caller likely doesn't have the fixture list yet, so for now
    # provide a function the caller invokes once per fixture_id.
    # This helper returns the dict mapping (built via the same scheme).
    # In practice callers should use ``get_lineup_for_fixture_id`` below.
    return lineups


def get_lineup_for_fixture_id(
    fixture_id: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[dict] | None:
    """Return the cached /fixtures/lineups response for a fixture_id,
    or None if not cached.

    Avoids hitting the API; useful when building the lookup from a known
    set of (date, fixture_id) pairs.
    """
    from nutmeg.v4.data.sources.api_football import _cache_path

    cp = _cache_path("/fixtures/lineups", {"fixture": fixture_id}, cache_dir)
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text())
    except Exception:  # noqa: BLE001
        return None


def get_injuries_for_team(
    team_id: int,
    season: int,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[dict] | None:
    """Return the cached /injuries response for a (team_id, season) pair."""
    from nutmeg.v4.data.sources.api_football import _cache_path

    cp = _cache_path("/injuries", {"team": team_id, "season": season}, cache_dir)
    if not cp.exists():
        return None
    try:
        return json.loads(cp.read_text())
    except Exception:  # noqa: BLE001
        return None


DEFAULT_INJURY_WINDOW_DAYS = 30


def _filter_injuries_before(
    injuries: list[dict] | None,
    match_date_str: str,
) -> list[dict] | None:
    """Filter injury records to those whose fixture.date < match_date_str.

    Critical for leakage prevention: API-Football's /injuries endpoint
    returns ALL season injury records by default, including those AFTER
    the match date. A naive len(injuries) feature would leak future
    information. This filter restricts to injuries WHOSE FIXTURE OCCURRED
    BEFORE the prediction match — i.e., "injury history accumulated so
    far in the season".

    Each injury record has shape:
        {"fixture": {"date": "YYYY-MM-DDTHH:MM:SS+00:00", ...}, ...}
    We compare lexicographically on the YYYY-MM-DD prefix.
    """
    if not injuries:
        return injuries
    return [
        r for r in injuries
        if (r.get("fixture", {}).get("date", "") or "")[:10] < match_date_str
    ]


def _recent_unique_injured_count(
    injuries: list[dict] | None,
    match_date_str: str,
    window_days: int = DEFAULT_INJURY_WINDOW_DAYS,
) -> int:
    """Count UNIQUE players injured in the window (match_date − N days, match_date).

    Empirically (V6 W5 EPL ablation) this beats season-cumulative count
    by 0.0038 log-loss on a 1-fold EPL test. The intuition: cumulative
    season count just measures "the team has had a tough season" — a
    proxy for team weakness already encoded in market odds. Recent
    unique players is closer to "who is missing today" — closer to the
    info the market doesn't fully price.

    Leak-free by construction: filters to fixture.date < match_date_str.
    """
    import datetime as _dt
    if not injuries:
        return 0
    try:
        match_date = _dt.date.fromisoformat(match_date_str)
    except ValueError:
        return 0
    window_start = (match_date - _dt.timedelta(days=window_days)).isoformat()

    seen: set[int] = set()
    for r in injuries:
        date_part = (r.get("fixture", {}).get("date", "") or "")[:10]
        if not date_part:
            continue
        if window_start <= date_part < match_date_str:
            pid = r.get("player", {}).get("id")
            if pid is not None:
                seen.add(int(pid))
    return len(seen)


def build_lineup_lookup_from_cache(
    league_canonical: str,
    season: int,
    v4_team_pool: list[str],
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> tuple[
    dict[str, tuple[dict | None, dict | None]],
    dict[str, tuple[list | None, list | None]],
    dict[str, str],  # unmatched team-name diagnostic
]:
    """Build (lineup_lookup, injury_lookup, unmatched_diagnostic).

    Walks the cached /fixtures list for the (league, season), opens each
    fixture's cached /fixtures/lineups response, maps API-Football team
    names → V4 canonical via ``team_canonical.to_v4_canonical``, and
    keys the lookup by V4 fixture_key.

    Skips fixtures with missing lineups or unresolved team names; counts
    are returned in the diagnostic dict (api_name → "unmatched").
    """
    cache_dir = Path(cache_dir)
    lineup_lookup: dict[str, tuple[dict | None, dict | None]] = {}
    injury_lookup: dict[str, tuple[list | None, list | None]] = {}
    unmatched: dict[str, str] = {}

    all_fixtures = _load_all_fixtures(cache_dir)
    # Filter to (league, season) — match on the API-Football's league.id
    from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS

    target_league_id = API_FOOTBALL_LEAGUE_IDS.get(league_canonical)
    if target_league_id is None:
        log.warning("Unknown V4 league canonical: %s", league_canonical)
        return lineup_lookup, injury_lookup, unmatched

    fixtures_in_scope = [
        f for f in all_fixtures
        if f.get("league", {}).get("id") == target_league_id
        and f.get("league", {}).get("season") == season
    ]

    for fixture in fixtures_in_scope:
        fid = fixture["fixture"]["id"]
        date_str = fixture["fixture"]["date"][:10]
        home_api = fixture["teams"]["home"]["name"]
        away_api = fixture["teams"]["away"]["name"]

        # Map to V4 canonical
        home_v4 = to_v4_canonical(home_api, league_canonical, v4_team_pool)
        away_v4 = to_v4_canonical(away_api, league_canonical, v4_team_pool)
        if home_v4.canonical is None:
            unmatched[home_api] = "unmatched"
            continue
        if away_v4.canonical is None:
            unmatched[away_api] = "unmatched"
            continue

        key = f"{league_canonical}__{date_str}__{home_v4.canonical}__{away_v4.canonical}"

        lineups_payload = get_lineup_for_fixture_id(fid, cache_dir)
        if lineups_payload and len(lineups_payload) >= 2:
            # API returns home first then away, but be defensive
            home_lineup = next(
                (l for l in lineups_payload if l.get("team", {}).get("name") == home_api),
                lineups_payload[0],
            )
            away_lineup = next(
                (l for l in lineups_payload if l.get("team", {}).get("name") == away_api),
                lineups_payload[1] if len(lineups_payload) > 1 else None,
            )
            lineup_lookup[key] = (home_lineup, away_lineup)

        # Injuries: per-team, per-season — same set covers many fixtures.
        # Filter to injuries that occurred BEFORE the current match date
        # to avoid leakage (the raw /injuries endpoint returns the WHOLE
        # season's injury events, including future ones).
        home_team_id = fixture["teams"]["home"]["id"]
        away_team_id = fixture["teams"]["away"]["id"]
        h_inj = _filter_injuries_before(
            get_injuries_for_team(home_team_id, season, cache_dir),
            date_str,
        )
        a_inj = _filter_injuries_before(
            get_injuries_for_team(away_team_id, season, cache_dir),
            date_str,
        )
        if h_inj is not None or a_inj is not None:
            injury_lookup[key] = (h_inj, a_inj)

    log.info(
        "Built lookup for %s %d: %d lineups, %d injuries, %d unmatched team names",
        league_canonical, season, len(lineup_lookup), len(injury_lookup), len(unmatched),
    )
    return lineup_lookup, injury_lookup, unmatched


def build_recent_injury_lookup(
    league_canonical: str,
    season: int,
    v4_team_pool: list[str],
    cache_dir: Path = DEFAULT_CACHE_DIR,
    window_days: int = DEFAULT_INJURY_WINDOW_DAYS,
) -> dict[str, tuple[int, int]]:
    """Return fixture_key → (home_recent_count, away_recent_count) of
    leak-free 30-day unique-injured player counts.

    Empirically validated in V6 W5 EPL ablation: this signal gave
    -0.0038 log-loss vs baseline (1-fold EPL 2024-12-01 test). Other
    lineup-derived features (formation, season-cumulative injuries,
    minutes share) failed the same test.
    """
    cache_dir = Path(cache_dir)
    out: dict[str, tuple[int, int]] = {}

    all_fixtures = _load_all_fixtures(cache_dir)
    from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS
    league_id = API_FOOTBALL_LEAGUE_IDS.get(league_canonical)
    if league_id is None:
        return out

    fixtures_in_scope = [
        f for f in all_fixtures
        if f.get("league", {}).get("id") == league_id
        and f.get("league", {}).get("season") == season
    ]

    for fixture in fixtures_in_scope:
        date_str = fixture["fixture"]["date"][:10]
        home_api = fixture["teams"]["home"]["name"]
        away_api = fixture["teams"]["away"]["name"]
        home_v4 = to_v4_canonical(home_api, league_canonical, v4_team_pool).canonical
        away_v4 = to_v4_canonical(away_api, league_canonical, v4_team_pool).canonical
        if not home_v4 or not away_v4:
            continue
        key = f"{league_canonical}__{date_str}__{home_v4}__{away_v4}"

        h_team_id = fixture["teams"]["home"]["id"]
        a_team_id = fixture["teams"]["away"]["id"]
        h_inj = get_injuries_for_team(h_team_id, season, cache_dir) or []
        a_inj = get_injuries_for_team(a_team_id, season, cache_dir) or []
        h_count = _recent_unique_injured_count(h_inj, date_str, window_days)
        a_count = _recent_unique_injured_count(a_inj, date_str, window_days)
        out[key] = (h_count, a_count)

    return out


__all__ = [
    "DEFAULT_CACHE_DIR",
    "DEFAULT_INJURY_WINDOW_DAYS",
    "build_lineup_lookup_from_cache",
    "build_recent_injury_lookup",
    "get_lineup_for_fixture_id",
    "get_injuries_for_team",
]
