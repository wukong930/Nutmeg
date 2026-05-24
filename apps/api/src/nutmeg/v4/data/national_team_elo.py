"""National-team Elo via clubelo's per-country endpoint — V8 W7.

V6 W11 registered 4 national-team competitions (WC, EURO, COPA_AMERICA,
WC_QUAL_UEFA) but the model had no per-team signal for them — WC fixtures
fell back to V4's "unknown team" path (zero form + 1500 default Elo).

clubelo exposes a country-level Elo at
    http://api.clubelo.com/<NationCode>
returning the same CSV shape as the per-club endpoint
(`Country, Rank, From, To, Elo`). The 3-letter codes are the
clubelo internal convention (ENG / BRA / ARG / FRA / ESP / GER /
ITA / NED / POR / BEL / ...) — close to but not identical to FIFA
codes (clubelo uses ENG for England, not GBR; SCO for Scotland;
NIR for Northern Ireland; etc.).

V8 W7 ships the data layer + a CLI to backfill the histories. Wiring
the lookup into the Elo feature builder for national-team-cup matches
(via V6 W11's `lookup_cup_team_pair` extension) is a follow-up task —
it requires fixture data with national teams to actually exercise.

This module is symmetric with the existing per-club `clubelo.py`:
- `NATION_CLUBELO_CODES` registry (V4-canonical-name → clubelo URL slug)
- `fetch_nation_history(code, ...)` returns a normalized DataFrame
- `build_nation_elo_lookup(cache_dir, as_of)` returns dict[code, elo]
- `lookup_nation_elo(state, name)` resolves common nation-name aliases
  to the registry codes (precedence: exact match → name alias → None)
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential


CLUBELO_BASE_URL = "http://api.clubelo.com"
DEFAULT_TIMEOUT = 20.0

log = logging.getLogger(__name__)


# clubelo's nation codes. Curated from the country-history catalog
# (http://www.clubelo.com/Ranking) — covers the major WC/Euro/Copa
# America entrants. Add new codes when ingest reports a 404.
#
# Keyed by clubelo code (uppercase). The value is a list of common
# English / API-Football name variants the lookup should resolve to
# this code.
NATION_CLUBELO_CODES: dict[str, list[str]] = {
    # UEFA — major Euro nations
    "ENG": ["England"],
    "FRA": ["France"],
    "ESP": ["Spain"],
    "GER": ["Germany"],
    "ITA": ["Italy"],
    "NED": ["Netherlands", "Holland"],
    "POR": ["Portugal"],
    "BEL": ["Belgium"],
    "CRO": ["Croatia"],
    "SUI": ["Switzerland"],
    "AUT": ["Austria"],
    "POL": ["Poland"],
    "DEN": ["Denmark"],
    "SWE": ["Sweden"],
    "TUR": ["Turkey", "Türkiye"],
    "RUS": ["Russia"],
    "UKR": ["Ukraine"],
    "CZE": ["Czech Republic", "Czechia"],
    "ROU": ["Romania"],
    "SCO": ["Scotland"],
    "WAL": ["Wales"],
    "IRL": ["Republic of Ireland", "Ireland"],
    "NIR": ["Northern Ireland"],
    "SRB": ["Serbia"],
    "GRE": ["Greece"],
    "NOR": ["Norway"],
    "HUN": ["Hungary"],
    "SVK": ["Slovakia"],
    "SVN": ["Slovenia"],
    "ALB": ["Albania"],
    "BIH": ["Bosnia and Herzegovina", "Bosnia"],
    "BUL": ["Bulgaria"],
    "ISL": ["Iceland"],
    "FIN": ["Finland"],
    "GEO": ["Georgia"],
    "MKD": ["North Macedonia", "Macedonia"],

    # CONMEBOL
    "BRA": ["Brazil"],
    "ARG": ["Argentina"],
    "URU": ["Uruguay"],
    "COL": ["Colombia"],
    "CHI": ["Chile"],
    "PER": ["Peru"],
    "ECU": ["Ecuador"],
    "PAR": ["Paraguay"],
    "BOL": ["Bolivia"],
    "VEN": ["Venezuela"],

    # CONCACAF
    "USA": ["USA", "United States"],
    "MEX": ["Mexico"],
    "CAN": ["Canada"],
    "CRC": ["Costa Rica"],
    "JAM": ["Jamaica"],
    "HON": ["Honduras"],

    # AFC + AFC-cross (commonly in WC qualifying)
    "JPN": ["Japan"],
    "KOR": ["Korea Republic", "South Korea"],
    "AUS": ["Australia"],
    "IRN": ["Iran"],
    "SAU": ["Saudi Arabia"],
    "QAT": ["Qatar"],
    "CHN": ["China PR", "China"],

    # CAF
    "MAR": ["Morocco"],
    "SEN": ["Senegal"],
    "EGY": ["Egypt"],
    "TUN": ["Tunisia"],
    "ALG": ["Algeria"],
    "NGA": ["Nigeria"],
    "CMR": ["Cameroon"],
    "GHA": ["Ghana"],
    "CIV": ["Ivory Coast", "Côte d'Ivoire"],
}


# Build the reverse lookup: normalized name → clubelo code.
def _normalize(s: str) -> str:
    return s.lower().replace("'", "").replace("-", " ").strip()


_NAME_TO_CODE: dict[str, str] = {}
for code, names in NATION_CLUBELO_CODES.items():
    _NAME_TO_CODE[code.lower()] = code  # the code itself is a valid lookup
    for name in names:
        _NAME_TO_CODE[_normalize(name)] = code


@dataclass(frozen=True)
class NationEloRecord:
    """One row of a nation's Elo history."""
    code: str           # clubelo code (ENG / BRA / etc.)
    from_date: pd.Timestamp
    to_date: pd.Timestamp
    elo: float


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def _http_get(url: str, *, client: httpx.Client) -> httpx.Response:
    """HTTP GET wrapped with exponential backoff (3 attempts)."""
    return client.get(url)


def fetch_nation_history(
    code: str,
    *,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """Fetch full Elo history for one nation (3-letter clubelo code).

    Returns a DataFrame with columns:
        code (str), from_date (Timestamp), to_date (Timestamp), elo (float)

    Empty body / 404 → returns an empty schema-only DataFrame (so callers
    can detect missing-data without exception handling).
    """
    code_upper = code.upper()
    url = f"{CLUBELO_BASE_URL}/{code_upper}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = _http_get(url, client=client)
        if resp.status_code == 404:
            log.warning("Clubelo nation 404: %s", code_upper)
            return _empty_history_frame()
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            log.warning("Clubelo returned empty body for nation %s", code_upper)
            return _empty_history_frame()
        raw = pd.read_csv(io.StringIO(resp.text))
    finally:
        if owns_client:
            client.close()

    if raw.empty:
        return _empty_history_frame()

    raw["From"] = pd.to_datetime(raw["From"], errors="coerce")
    raw["To"] = pd.to_datetime(raw["To"], errors="coerce")
    out = pd.DataFrame({
        "code":      code_upper,
        "from_date": raw["From"],
        "to_date":   raw["To"],
        "elo":       raw["Elo"].astype(float),
    })
    return out.dropna(subset=["from_date", "to_date", "elo"]).reset_index(drop=True)


def _empty_history_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "code":      pd.Series(dtype="object"),
        "from_date": pd.Series(dtype="datetime64[ns]"),
        "to_date":   pd.Series(dtype="datetime64[ns]"),
        "elo":       pd.Series(dtype="float64"),
    })


# ---------- Cache + lookup helpers ---------------------------------------

def nation_cache_path(cache_dir: Path, code: str) -> Path:
    """Canonical filename for one nation's parquet cache."""
    return cache_dir / f"{code.upper()}.parquet"


def write_nation_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_nation_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_history_frame()
    return pd.read_parquet(path)


def build_nation_elo_lookup(
    cache_dir: Path,
    *,
    as_of: pd.Timestamp | None = None,
    codes: Iterable[str] | None = None,
) -> dict[str, float]:
    """Walk cache_dir, return dict[code, elo] valid on `as_of`.

    `as_of` defaults to today. `codes` filters to a subset of registry
    codes (default = every parquet found in cache_dir).

    Each nation's Elo at `as_of` is the row whose `from_date <= as_of
    < to_date` (clubelo's intervals don't overlap). If no row covers
    `as_of` (nation hasn't played recently or cache is stale), falls
    back to the most-recent row.
    """
    if as_of is None:
        as_of = pd.Timestamp.utcnow().tz_localize(None)
    elif as_of.tzinfo is not None:
        as_of = as_of.tz_localize(None)

    if codes is None:
        cache_dir = Path(cache_dir)
        codes = [
            p.stem for p in cache_dir.glob("*.parquet")
            if p.stem.upper() in NATION_CLUBELO_CODES
        ]

    out: dict[str, float] = {}
    for code in codes:
        df = load_nation_parquet(nation_cache_path(cache_dir, code))
        if len(df) == 0:
            continue
        df = df.sort_values("from_date").reset_index(drop=True)
        active = df[(df["from_date"] <= as_of) & (df["to_date"] > as_of)]
        if len(active) == 0:
            # Fall back to most recent
            out[code.upper()] = float(df.iloc[-1]["elo"])
        else:
            out[code.upper()] = float(active.iloc[-1]["elo"])
    return out


def lookup_nation_elo(
    nation_state: dict[str, float],
    team_name: str,
) -> tuple[Optional[str], Optional[float]]:
    """Resolve a team name to (clubelo_code, current_elo) or (None, None).

    Precedence:
      1. Exact 3-letter code match (uppercase) → state[code]
      2. Normalized name → CLUBELO code via `_NAME_TO_CODE`
      3. Return (None, None)
    """
    if not team_name:
        return None, None

    # 1. Code match
    upper = team_name.upper()
    if upper in nation_state and len(upper) == 3:
        return upper, nation_state[upper]

    # 2. Name alias
    code = _NAME_TO_CODE.get(_normalize(team_name))
    if code is not None:
        elo = nation_state.get(code)
        if elo is not None:
            return code, elo
    return None, None


__all__ = [
    "CLUBELO_BASE_URL",
    "NATION_CLUBELO_CODES",
    "NationEloRecord",
    "fetch_nation_history",
    "nation_cache_path",
    "write_nation_parquet",
    "load_nation_parquet",
    "build_nation_elo_lookup",
    "lookup_nation_elo",
]
