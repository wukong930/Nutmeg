"""Shared helpers for the recommendation CLIs.

Extracted V12 (post-V11 audit). ``cli/recommend.py`` (``_read_fixtures``)
and ``cli/recommend_pool.py`` (``_read_pool_fixtures``) both did the same
read-CSV + required-column-check + date-parse skeleton. Centralizing it
keeps the fixtures-CSV column contract in one place; the pool reader still
adds its own ``pick``-value validation on top.

(``cli/rec.py`` already imports the two reader functions rather than
re-implementing them, so there is no third copy.)
"""
from __future__ import annotations

import pandas as pd

# The minimal columns every recommendation fixtures CSV must carry.
BASE_REQUIRED_COLUMNS = [
    "date", "league", "home_team", "away_team",
    "psc_home", "psc_draw", "psc_away",
]


def read_fixtures_csv(
    path: str,
    *,
    extra_required: list[str] | None = None,
    label: str = "input CSV",
) -> pd.DataFrame:
    """Read a fixtures CSV, validate required columns, parse ``date``.

    Parameters
    ----------
    path : CSV path.
    extra_required : columns required beyond ``BASE_REQUIRED_COLUMNS``
        (e.g. ``["pick"]`` for the compound-pool CSV).
    label : prefix used in the missing-column error so callers keep
        distinguishable messages ("input CSV" vs "pool CSV").

    Raises
    ------
    ValueError : if any required column is absent.
    """
    df = pd.read_csv(path)
    required = list(BASE_REQUIRED_COLUMNS) + list(extra_required or [])
    for c in required:
        if c not in df.columns:
            raise ValueError(f"{label} missing required column: {c}")
    df["date"] = pd.to_datetime(df["date"])
    return df
