"""Clubelo ELO features — independent cross-country ELO from clubelo.com.

V5 W4 addition. V4 already has a per-league internal ELO; clubelo provides a
SECOND, cross-country ELO computed with a different K-factor and methodology.
Blending the two (as separate columns) gives the GBM two views of team
strength that are correlated but not identical, especially for teams that
recently changed leagues / European positions.

Source: per-team parquet files written by
``nutmeg.v4.data.sources.clubelo.ingest_teams`` under data/external/clubelo/.
Each parquet has columns (team_canonical, clubelo_slug, country, elo,
from_date, to_date) — one row per ELO change interval since 1946.

Features (per match):
  clubelo_home / clubelo_away      — ELO on match date (or NaN if not tracked)
  clubelo_diff                     — clubelo_home − clubelo_away
  clubelo_p_home                   — sigmoid((diff + home_advantage) / scale),
                                     a clubelo-derived 1X2-style home win prob
  clubelo_available                — 1 if both teams have ELO that date, else 0

Missing handling: if a team is not in clubelo (e.g., J1 teams, lower-division
that fell out of clubelo's tracked level), both clubelo_home and clubelo_away
land as NaN. The GBM gets the ``clubelo_available`` flag and can route to
market+internal-elo features for those rows.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd


log = logging.getLogger(__name__)

# Sensible defaults for the sigmoid-based win-probability proxy.
# Home advantage in clubelo terms (~70 elo points is typical for home matches).
CLUBELO_HOME_ADVANTAGE = 70.0
# Scale constant: 400 in the standard ELO formula P = 1 / (1 + 10^(−Δ/400))
CLUBELO_SCALE = 400.0
# Placeholder ELO when clubelo doesn't track a team. The GBM also gets the
# ``clubelo_available`` flag and can learn to discount these placeholder
# rows; using a value (instead of NaN) lets rows survive the GBM dropna.
CLUBELO_PLACEHOLDER = 1500.0


CLUBELO_FEATURE_COLUMNS = [
    "clubelo_home",
    "clubelo_away",
    "clubelo_diff",
    "clubelo_p_home",
    "clubelo_available",
]


def load_clubelo_history(
    cache_dir: Path | str = Path("data/external/clubelo"),
) -> pd.DataFrame:
    """Load every cached clubelo team-history parquet into one long DataFrame.

    Empty/non-existent caches are silently skipped. Returns an empty frame with
    the right columns if no caches exist.
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        log.warning("clubelo cache dir %s does not exist", cache_dir)
        return _empty_history()
    frames: list[pd.DataFrame] = []
    for p in sorted(cache_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping unreadable parquet %s: %s", p, exc)
            continue
        if not df.empty:
            frames.append(df)
    if not frames:
        return _empty_history()
    return pd.concat(frames, ignore_index=True)


def _empty_history() -> pd.DataFrame:
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


def _build_team_lookup(history: pd.DataFrame) -> dict[str, list[tuple]]:
    """Group history by team_canonical → list of (from_date, to_date, elo) sorted.

    This is much faster than a pandas mask per row when we're looking up ~25k
    matches × 2 teams.
    """
    lookup: dict[str, list[tuple]] = {}
    if history.empty:
        return lookup
    for team, group in history.groupby("team_canonical"):
        rows = [
            (r.from_date, r.to_date, float(r.elo))
            for r in group.itertuples(index=False)
        ]
        rows.sort(key=lambda x: x[0])
        lookup[str(team)] = rows
    return lookup


def _elo_for(lookup: dict[str, list[tuple]], team: str, match_date) -> float:
    """Linear scan over the team's intervals; returns NaN if no interval covers the date.

    Acceptable performance because each team has ~1k intervals (since 1946)
    and we early-return on first hit.
    """
    if team not in lookup or pd.isna(match_date):
        return float("nan")
    # match_date is a pandas Timestamp; clubelo from/to are datetime.date
    if isinstance(match_date, pd.Timestamp):
        match_date = match_date.date()
    for from_d, to_d, elo in lookup[team]:
        if from_d <= match_date <= to_d:
            return elo
    return float("nan")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def build_clubelo_features(
    df: pd.DataFrame,
    *,
    cache_dir: Path | str = Path("data/external/clubelo"),
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Augment df with clubelo features (5 columns).

    Pass ``history`` to avoid re-loading from disk in tests; otherwise loads
    from ``cache_dir``.
    """
    out = df.copy()

    if history is None:
        history = load_clubelo_history(cache_dir)
    lookup = _build_team_lookup(history)

    home_elo = np.full(len(out), np.nan)
    away_elo = np.full(len(out), np.nan)
    for i, row in enumerate(out.itertuples(index=False)):
        home_elo[i] = _elo_for(lookup, row.home_team, row.date)
        away_elo[i] = _elo_for(lookup, row.away_team, row.date)

    # available flag based on raw ELO values BEFORE we fill placeholders
    available = (
        pd.Series(home_elo).notna() & pd.Series(away_elo).notna()
    ).astype(int).values

    # Fill missing with placeholder so rows survive GBM dropna. The flag tells
    # the model when these are real vs imputed.
    home_filled = np.where(np.isnan(home_elo), CLUBELO_PLACEHOLDER, home_elo)
    away_filled = np.where(np.isnan(away_elo), CLUBELO_PLACEHOLDER, away_elo)

    out["clubelo_home"] = home_filled
    out["clubelo_away"] = away_filled
    out["clubelo_diff"] = home_filled - away_filled

    diff_with_ha = (out["clubelo_diff"] + CLUBELO_HOME_ADVANTAGE) / CLUBELO_SCALE
    # 10^x / (1 + 10^x) — standard ELO win-prob formula
    out["clubelo_p_home"] = 1.0 / (1.0 + np.power(10.0, -diff_with_ha))

    out["clubelo_available"] = available

    return out
