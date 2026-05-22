"""Understat xG adapter — DEFERRED.

The understat.com website moved to JavaScript-rendered pages and no longer
exposes the ``datesData`` / ``teamsData`` JSON variables that the (now broken)
``understat`` PyPI package looked for. Our direct HTTP scrape returns only a
~18 KB shell HTML with no data.

Verified blocked options:
- ``understat`` PyPI 0.1.4 → ``re.search(pattern, None)`` because script.string is None
- Direct httpx scrape with desktop + mobile User-Agent → no datesData on page
- worldfootballR_data understat_shots/*.rds → pyreadr fails on string encoding
- Wayback Machine snapshots exist but are static and not refreshable

Path forward (decided in W12):
- Option A: ``$19/mo`` API-Football includes per-match xG → fold into this module
- Option B: Run a Playwright headless renderer (heavier, may be blocked by Cloudflare)
- Option C: Subscribe to fbref via a paid scraping proxy

Until then, V5 features fall back to V4's existing ``home_shots`` / ``away_shots``
columns and the regression-to-mean "xG-lite" approximation in
``v4/features/xg_lite.py`` (W4).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nutmeg.v4.data.external_schema import UNDERSTAT_SCHEMA


class UnderstatNotAvailableError(RuntimeError):
    """Raised when an adapter call is attempted while the source is blocked."""


def fetch_league_season(league: str, season: int) -> pd.DataFrame:  # noqa: ARG001
    raise UnderstatNotAvailableError(
        "understat scraping is currently blocked (JS-rendered site). "
        "See module docstring for paid alternatives."
    )


def ingest_league_season(  # noqa: ARG001
    league: str,
    season: int,
    *,
    cache_dir: Path = Path("data/external/understat"),
    refresh: bool = False,
) -> pd.DataFrame:
    raise UnderstatNotAvailableError(
        "understat ingest is deferred. See module docstring."
    )


__all__ = [
    "UnderstatNotAvailableError",
    "fetch_league_season",
    "ingest_league_season",
    "UNDERSTAT_SCHEMA",
]
