"""OddsPortal opening-odds adapter — DEFERRED.

OddsPortal serves the entire match list via JavaScript (Vue.js single-page app)
behind Cloudflare. Pure HTTP scrape returns an empty SPA shell; full extraction
requires Playwright with a session that bypasses Cloudflare interactive challenge.

Path forward (W5 decision):
- Option A: keep using football-data.co.uk's ``B365H/D/A`` opening odds (already
  in our DataFrame; we just haven't used them as ``open_odds_*`` yet) — this is
  the lowest-effort win because the data is *already on disk*.
- Option B: Playwright headless against OddsPortal with stealth plugin (heavy
  + brittle; failure mode is silent IP ban).
- Option C: pay for ``the-odds-api.com`` historical odds endpoint.

For W5 "市场动态" features we recommend Option A — football-data.co.uk's Bet365
opening line is widely accepted as a reasonable opening-market signal.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from nutmeg.v4.data.external_schema import OPENING_ODDS_SCHEMA


class OddsPortalNotAvailableError(RuntimeError):
    pass


def fetch_opening_odds(league: str, season: int) -> pd.DataFrame:  # noqa: ARG001
    raise OddsPortalNotAvailableError("OddsPortal scraping is deferred. See module docstring.")


def ingest_opening_odds(  # noqa: ARG001
    league: str,
    season: int,
    *,
    cache_dir: Path = Path("data/external/oddsportal"),
    refresh: bool = False,
) -> pd.DataFrame:
    raise OddsPortalNotAvailableError(
        "OddsPortal ingest is deferred. Use football-data.co.uk B365H/D/A opening "
        "odds (already on disk) for W5 'market dynamics' features."
    )


__all__ = [
    "OddsPortalNotAvailableError",
    "fetch_opening_odds",
    "ingest_opening_odds",
    "OPENING_ODDS_SCHEMA",
]
