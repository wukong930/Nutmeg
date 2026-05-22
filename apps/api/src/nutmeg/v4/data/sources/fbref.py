"""fbref.com adapter — DEFERRED.

fbref.com (sports-reference) blocks all HTTP UA we tested (desktop Chrome,
mobile Safari, default httpx) with a 403 inside a few KB stub page. Their TOS
explicitly forbids automated scraping; the only "free" path is the
``worldfootballR`` R-package wrapper that uses Cloudflare-friendly request
patterns — and even that has rate caps.

Path forward (W12 decision, same as understat):
- Option A: API-Football $19/mo (xG inline; covers ~95% of our 5+1 leagues)
- Option B: ScrapingBee / ScrapFly residential proxy ($30+/mo)
- Option C: subscribe to ``soccerdata`` package which centralizes these adapters
  behind their own throttling
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nutmeg.v4.data.external_schema import FBREF_SCHEMA


class FbrefNotAvailableError(RuntimeError):
    pass


def fetch_match_summary(league: str, season: int) -> pd.DataFrame:  # noqa: ARG001
    raise FbrefNotAvailableError("fbref scraping is blocked (HTTP 403). See module docstring.")


def ingest_match_summary(  # noqa: ARG001
    league: str,
    season: int,
    *,
    cache_dir: Path = Path("data/external/fbref"),
    refresh: bool = False,
) -> pd.DataFrame:
    raise FbrefNotAvailableError("fbref ingest is deferred. See module docstring.")


__all__ = [
    "FbrefNotAvailableError",
    "fetch_match_summary",
    "ingest_match_summary",
    "FBREF_SCHEMA",
]
