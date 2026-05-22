"""Clubelo ELO history adapter (http://clubelo.com).

API: ``GET http://api.clubelo.com/<TeamName>`` returns CSV with columns
``Rank, Club, Country, Level, Elo, From, To`` — one row per ELO change.

V5 uses this as an INDEPENDENT ELO baseline (the existing V4 Elo is computed
internally and is per-league; clubelo is cross-country and uses its own K-factor),
providing a second view of team strength that the GBM can blend with.

Team-name expectations: clubelo uses URL-friendly names without spaces
(``ManCity``, ``ManUnited``, ``RealMadrid``, ``Atletico``). We maintain a
clubelo-specific alias dict because our team_canonical primarily targets
understat/fbref-style spellings.

The full per-team history is small (~30 KB / ~1k rows back to 1946) so we
fetch once and cache to ``data/external/clubelo/<team>.parquet``.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import httpx
import pandas as pd


log = logging.getLogger(__name__)

CLUBELO_BASE_URL = "http://api.clubelo.com"
DEFAULT_CACHE_DIR = Path("data/external/clubelo")
DEFAULT_TIMEOUT = 8.0
THROTTLE_SECONDS = 0.1  # clubelo doesn't rate-limit on the public endpoint


# V4 canonical name → clubelo URL slug. Only entries that differ from canonical.
# Clubelo URL convention: PascalCase, no spaces, ASCII.
CLUBELO_SLUGS: dict[str, str] = {
    "Man United": "ManUnited",
    "Man City": "ManCity",
    "Nott'm Forest": "Forest",
    "West Ham": "WestHam",
    "Aston Villa": "AstonVilla",
    "West Brom": "WestBrom",
    "Sheffield United": "SheffieldUnited",
    "Crystal Palace": "CrystalPalace",
    "Ath Bilbao": "Bilbao",
    "Ath Madrid": "Atletico",
    "Real Madrid": "RealMadrid",
    "Sociedad": "Sociedad",
    "Las Palmas": "LasPalmas",
    "Espanol": "Espanyol",
    "Valladolid": "Valladolid",
    "Bayern Munich": "Bayern",
    "Dortmund": "Dortmund",
    "RB Leipzig": "RBLeipzig",
    "Leverkusen": "Leverkusen",
    "Ein Frankfurt": "Frankfurt",
    "M'gladbach": "Gladbach",
    "FC Koln": "Koeln",
    "Werder Bremen": "Bremen",
    "Union Berlin": "UnionBerlin",
    "Schalke 04": "Schalke",
    "Hertha": "Hertha",
    "Holstein Kiel": "Kiel",
    "St Pauli": "StPauli",
    "Paris SG": "PSG",
    "St Etienne": "SaintEtienne",
    "Le Havre": "LeHavre",
    "PSV Eindhoven": "PSV",
    "AZ Alkmaar": "AZ",
    "NEC Nijmegen": "Nijmegen",
    "Sparta Rotterdam": "SpartaRotterdam",
    "Go Ahead Eagles": "GoAheadEagles",
    "For Sittard": "Sittard",
    "Sp Braga": "Braga",
}


def _slug_for(team: str) -> str:
    """Convert a V4 canonical team name to the clubelo URL slug."""
    return CLUBELO_SLUGS.get(team, team.replace(" ", "").replace("'", ""))


def fetch_team_history(team: str, *, client: httpx.Client | None = None) -> pd.DataFrame:
    """Fetch full ELO history for a single team (V4 canonical name).

    Returns a DataFrame with normalized columns:
        team_canonical (str), clubelo_slug (str), country (str),
        elo (float), from_date (date), to_date (date)
    Raises httpx.HTTPStatusError on non-2xx after retries.
    """
    slug = _slug_for(team)
    url = f"{CLUBELO_BASE_URL}/{slug}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.text.strip():
            log.warning("Clubelo returned empty body for %s (slug=%s)", team, slug)
            return _empty_history_frame(team, slug)
        raw = pd.read_csv(io.StringIO(resp.text))
    finally:
        if owns_client:
            client.close()

    if raw.empty:
        return _empty_history_frame(team, slug)

    raw["From"] = pd.to_datetime(raw["From"], errors="coerce").dt.date
    raw["To"] = pd.to_datetime(raw["To"], errors="coerce").dt.date
    out = pd.DataFrame(
        {
            "team_canonical": team,
            "clubelo_slug": slug,
            "country": raw["Country"],
            "elo": raw["Elo"].astype(float),
            "from_date": raw["From"],
            "to_date": raw["To"],
        }
    )
    return out.dropna(subset=["from_date", "to_date", "elo"]).reset_index(drop=True)


def _empty_history_frame(team: str, slug: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_canonical": pd.Series(dtype="object"),
            "clubelo_slug": pd.Series(dtype="object"),
            "country": pd.Series(dtype="object"),
            "elo": pd.Series(dtype="float64"),
            "from_date": pd.Series(dtype="object"),
            "to_date": pd.Series(dtype="object"),
        }
    )


def cache_path(team: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Where the per-team parquet lives."""
    safe = team.replace(" ", "_").replace("'", "").replace("/", "_")
    return cache_dir / f"{safe}.parquet"


def ingest_teams(
    teams: list[str],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    throttle_seconds: float = THROTTLE_SECONDS,
) -> pd.DataFrame:
    """Fetch (and cache) ELO history for every team in `teams`.

    Returns a long-format DataFrame with one row per (team, ELO change interval).
    If a per-team parquet already exists and `refresh=False`, it is loaded from
    disk; otherwise it's re-fetched.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        for team in teams:
            p = cache_path(team, cache_dir)
            if p.exists() and not refresh:
                frames.append(pd.read_parquet(p))
                continue
            try:
                df = fetch_team_history(team, client=client)
            except Exception as exc:  # noqa: BLE001 — log and continue with empty
                log.warning("Clubelo fetch failed for %s: %s", team, exc)
                df = _empty_history_frame(team, _slug_for(team))
            df.to_parquet(p, index=False)
            frames.append(df)
            time.sleep(throttle_seconds)
    if not frames:
        return _empty_history_frame("", "")
    return pd.concat(frames, ignore_index=True)


def elo_on_date(history: pd.DataFrame, team: str, match_date: pd.Timestamp | str) -> float | None:
    """Look up a team's clubelo ELO on a specific date.

    Returns the ELO value from the row where ``from_date <= match_date <= to_date``,
    or None if the team has no history covering that date (e.g., team didn't
    exist or was lower-division and dropped off clubelo's tracked level).
    """
    if isinstance(match_date, str):
        match_date = pd.to_datetime(match_date).date()
    elif isinstance(match_date, pd.Timestamp):
        match_date = match_date.date()
    h = history[history["team_canonical"] == team]
    if h.empty:
        return None
    mask = (h["from_date"] <= match_date) & (h["to_date"] >= match_date)
    rows = h[mask]
    if rows.empty:
        return None
    return float(rows["elo"].iloc[0])
