"""Stadium / venue features — Path 3 of V11 Branch B (skeleton).

_V11 Phase 0 — pure-function skeleton + API shape. Production data
ingest is Branch B W2 work. This module compiles and tests pass on
synthetic data, but the venue registry (`data/external/stadiums.parquet`)
is empty until Branch B W2 fills it._

## What this adds beyond the current home_adv constant

The production model currently uses a single global `home_adv = 0.20`
goal multiplier for the home team (V4 baseline). Football literature
(Pollard 1986, 2006; Pollard & Pollard 2005) shows home advantage
varies by:

  1. **Altitude** — La Paz (3640m), Quito (2850m), Mexico City (2240m)
     give an extra ~5-8% win-rate advantage when away team is from
     sea level (fatigue-driven)
  2. **Travel distance** — long-haul away trips (>3000km) reduce
     away performance ~3-5pp
  3. **Capacity / atmosphere** — stadiums with >50k capacity show
     stronger home advantage than smaller venues (less consistent
     in the literature; weaker effect)
  4. **Surface type** — teams accustomed to artificial turf are
     disadvantaged on grass and vice versa (mostly relevant for
     Scandinavian leagues / MLS visitors)

## Feature output (one match, vectorized over a DataFrame)

| Column | Type | Range | Description |
|---|---|---|---|
| `stadium_altitude_m` | float | [-50, 4000] | venue altitude in meters above sea level |
| `stadium_altitude_modifier` | float | [1.00, 1.10] | multiplicative home advantage from altitude (see `altitude_modifier()`) |
| `stadium_travel_km` | float | [0, 18000] | great-circle km from away team's prior venue (or country center) to current venue |
| `stadium_capacity` | int | [0, 100000] | venue seating capacity |
| `stadium_capacity_quantile` | float | [0, 1] | quantile within the league's venues |
| `stadium_is_artificial_turf` | int | {0, 1} | surface type flag |

## NOT in this skeleton (Branch B W2 deliverable)

- Actual `data/external/stadiums.parquet` data file
- API-Football `/venues` endpoint ingester
- Open-Elevation API integration for altitude lookup
- Travel-distance computation (uses haversine; needs lat/lon for both
  home and away team's previous venue)
- Walk-forward ablation against current production
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


log = logging.getLogger(__name__)


# ---------- Data shape -------------------------------------------------------

@dataclass(frozen=True)
class StadiumInfo:
    """Lightweight venue descriptor. Populated from the venue registry
    parquet (Branch B W2) or constructed inline for tests.

    All optional fields are None when unknown — downstream features
    must handle missing data (return NaN, don't crash)."""
    venue_id: str | int
    name: str
    city: str | None = None
    country: str | None = None
    altitude_m: float | None = None
    capacity: int | None = None
    lat: float | None = None
    lon: float | None = None
    surface: str | None = None  # 'grass' | 'artificial' | 'hybrid'


# ---------- Curated altitude lookup (skeleton placeholder) -------------------

# Top-tier high-altitude stadiums where altitude clearly matters.
# Sourced from public Wikipedia altitude data; Branch B W2 will replace
# this with a full venue registry covering all leagues we model.
KNOWN_HIGH_ALTITUDE_VENUES: dict[str, float] = {
    # South America
    "Hernando Siles": 3640.0,           # La Paz, Bolivia
    "Atahualpa": 2850.0,                # Quito, Ecuador
    "Cuscatlán": 600.0,                 # San Salvador, El Salvador
    "Azteca": 2240.0,                   # Mexico City
    "Akron": 1620.0,                    # Zapopan, Mexico
    "Hidalgo": 1869.0,                  # Pachuca, Mexico
    "Centenario de Armenia": 1480.0,    # Armenia, Colombia
    "El Campín": 2640.0,                # Bogotá, Colombia
    "Atanasio Girardot": 1495.0,        # Medellín, Colombia
    "Olímpico Atahualpa": 2850.0,       # Quito, Ecuador (alt name)
    "Monumental": 65.0,                 # Buenos Aires (sea-level reference)
    # Africa
    "FNB": 1690.0,                      # Johannesburg, South Africa
    "Loftus Versfeld": 1330.0,          # Pretoria
    # Europe (mostly sea-level; for completeness)
    "Wembley": 16.0,
    "Camp Nou": 9.0,
    "Allianz Arena": 510.0,             # Munich
    "Stadio Olimpico": 21.0,            # Rome
    "Anfield": 30.0,
    "Old Trafford": 36.0,
}


def lookup_altitude(venue_name: str) -> float | None:
    """Cheap fallback altitude lookup for the curated table.

    Returns None when the venue isn't in the curated list (most cases).
    Branch B W2 replaces this with a full registry query."""
    # Direct hit
    if venue_name in KNOWN_HIGH_ALTITUDE_VENUES:
        return KNOWN_HIGH_ALTITUDE_VENUES[venue_name]
    # Fuzzy: ignore stuff in parentheses, case-insensitive substring
    name_norm = venue_name.lower().split("(")[0].strip()
    for known_name, alt in KNOWN_HIGH_ALTITUDE_VENUES.items():
        if name_norm == known_name.lower():
            return alt
    return None


# ---------- Core feature math ------------------------------------------------

# Altitude-modifier curve: home win-rate boost as a function of altitude.
# Fit loosely from the football-analytics literature; will be re-calibrated
# at Branch B W2 against actual fixture outcomes.
#
# Below 1000m: no modifier (1.00)
# 1000-2000m: linear ramp from 1.00 → 1.05
# 2000-3000m: linear ramp from 1.05 → 1.08
# Above 3000m: flat 1.10 (cap)
def altitude_modifier(altitude_m: float | None) -> float:
    """Multiplicative home advantage from altitude.

    Returns 1.0 (no modifier) for sea-level or unknown.
    Output ∈ [1.00, 1.10].
    """
    if altitude_m is None or not np.isfinite(altitude_m) or altitude_m < 1000:
        return 1.00
    if altitude_m < 2000:
        # Linear ramp 1.00 → 1.05 over 1000m
        return 1.00 + 0.05 * (altitude_m - 1000) / 1000
    if altitude_m < 3000:
        # Linear ramp 1.05 → 1.08
        return 1.05 + 0.03 * (altitude_m - 2000) / 1000
    # Cap at 1.10 for >3000m
    return min(1.10, 1.08 + 0.02 * (altitude_m - 3000) / 1000)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km.

    Standard haversine formula. Used for travel-distance feature.
    """
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def travel_distance_km(
    home_venue: StadiumInfo | None,
    away_venue: StadiumInfo | None,
) -> float | None:
    """Distance from away team's previous venue to current venue.

    None when either venue lacks lat/lon. Branch B W2 will fall back
    to "away team's home country centroid" when prior-venue is unknown.
    """
    if home_venue is None or away_venue is None:
        return None
    if home_venue.lat is None or home_venue.lon is None:
        return None
    if away_venue.lat is None or away_venue.lon is None:
        return None
    return haversine_km(
        away_venue.lat, away_venue.lon,
        home_venue.lat, home_venue.lon,
    )


def capacity_quantile(capacity: int | None, league_caps: list[int]) -> float:
    """Quantile of `capacity` within the league's distribution.

    Returns NaN when capacity is unknown or league_caps is empty.
    Branch B W2: precomputed per-league quantile tables for efficiency.
    """
    if capacity is None or not league_caps:
        return float("nan")
    valid = sorted(c for c in league_caps if c is not None and c > 0)
    if not valid:
        return float("nan")
    # Rank position / N
    rank = sum(1 for c in valid if c <= capacity)
    return rank / len(valid)


# ---------- Vectorized feature builder ---------------------------------------

OUTPUT_COLUMNS = [
    "stadium_altitude_m",
    "stadium_altitude_modifier",
    "stadium_travel_km",
    "stadium_capacity",
    "stadium_capacity_quantile",
    "stadium_is_artificial_turf",
]


def build_stadium_features(
    df: pd.DataFrame,
    *,
    venue_registry: dict[str | int, StadiumInfo] | None = None,
    league_capacities: dict[str, list[int]] | None = None,
) -> pd.DataFrame:
    """Compute stadium features for each row of `df`.

    `df` must have at minimum:
      - `home_venue_id` (str or int) — the venue where the match is played
      - `away_team_prior_venue_id` (str or int, optional) — where away
        team played their previous match (for travel-distance). When
        absent, travel_km is NaN.
      - `league` (str) — for capacity quantile lookup

    Returns a DataFrame with the same index as `df` and OUTPUT_COLUMNS.
    NaN/0 for missing data; never raises.
    """
    if venue_registry is None:
        venue_registry = {}
    if league_capacities is None:
        league_capacities = {}

    n = len(df)
    out: dict[str, np.ndarray] = {
        "stadium_altitude_m":           np.full(n, np.nan, dtype=float),
        "stadium_altitude_modifier":    np.ones(n, dtype=float),
        "stadium_travel_km":            np.full(n, np.nan, dtype=float),
        "stadium_capacity":             np.full(n, 0, dtype=int),
        "stadium_capacity_quantile":    np.full(n, np.nan, dtype=float),
        "stadium_is_artificial_turf":   np.zeros(n, dtype=int),
    }

    for i, row in enumerate(df.itertuples(index=False)):
        home_venue_id = getattr(row, "home_venue_id", None)
        away_prior_venue_id = getattr(row, "away_team_prior_venue_id", None)
        league = getattr(row, "league", "")
        home_venue = venue_registry.get(home_venue_id) if home_venue_id is not None else None

        if home_venue is None:
            continue

        # Altitude
        alt = home_venue.altitude_m
        if alt is None:
            alt = lookup_altitude(home_venue.name)
        if alt is not None:
            out["stadium_altitude_m"][i] = alt
            out["stadium_altitude_modifier"][i] = altitude_modifier(alt)

        # Travel
        if away_prior_venue_id is not None:
            away_venue = venue_registry.get(away_prior_venue_id)
            travel = travel_distance_km(home_venue, away_venue)
            if travel is not None:
                out["stadium_travel_km"][i] = travel

        # Capacity
        if home_venue.capacity is not None:
            out["stadium_capacity"][i] = home_venue.capacity
            league_caps = league_capacities.get(league, [])
            out["stadium_capacity_quantile"][i] = capacity_quantile(
                home_venue.capacity, league_caps,
            )

        # Surface
        if home_venue.surface in {"artificial", "artificial_turf", "synthetic"}:
            out["stadium_is_artificial_turf"][i] = 1

    return pd.DataFrame(out, index=df.index)


# ---------- Stadium registry I/O (Branch B W2 will implement) ----------------

DEFAULT_REGISTRY_PATH = Path("data/external/stadiums.parquet")


def load_venue_registry(
    path: Path | str = DEFAULT_REGISTRY_PATH,
) -> dict[str | int, StadiumInfo]:
    """Load a venue registry parquet → dict keyed by venue_id.

    Schema (Branch B W2 will produce):
      - venue_id (str)
      - name, city, country (str)
      - altitude_m (float, nullable)
      - capacity (int, nullable)
      - lat, lon (float, nullable)
      - surface (str, nullable)

    Returns {} when the file is missing (Branch B W2 hasn't filled it yet);
    callers should not crash on empty registries — features fall back to
    the curated altitude table + zero defaults.
    """
    p = Path(path)
    if not p.exists():
        log.info("venue registry not present at %s — returning empty dict", p)
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse %s: %s", p, exc)
        return {}
    registry: dict[str | int, StadiumInfo] = {}
    for r in df.itertuples(index=False):
        registry[r.venue_id] = StadiumInfo(
            venue_id=r.venue_id,
            name=getattr(r, "name", ""),
            city=getattr(r, "city", None),
            country=getattr(r, "country", None),
            altitude_m=getattr(r, "altitude_m", None),
            capacity=getattr(r, "capacity", None),
            lat=getattr(r, "lat", None),
            lon=getattr(r, "lon", None),
            surface=getattr(r, "surface", None),
        )
    return registry


__all__ = [
    "StadiumInfo",
    "KNOWN_HIGH_ALTITUDE_VENUES",
    "OUTPUT_COLUMNS",
    "altitude_modifier",
    "haversine_km",
    "lookup_altitude",
    "travel_distance_km",
    "capacity_quantile",
    "build_stadium_features",
    "load_venue_registry",
]
