"""DuckDB schema for V5 external data sources.

DuckDB acts as a thin columnar store on top of parquet files in ``data/external/``.
We don't use SQLAlchemy or migrations here — the data is append-mostly and the
"schema" is enforced at write time by the source adapters.

Layout::

    data/external/
      clubelo/<team>.parquet         # one file per team, see sources/clubelo.py
      understat/<league>_<season>.parquet     (W3+: pending xG-source unblock)
      fbref/<league>_<season>.parquet         (W3+: pending xG-source unblock)
      oddsportal/<league>_<season>.parquet    (W3+: pending opening-odds adapter)

To open the lake from anywhere::

    import duckdb
    conn = duckdb.connect(":memory:")
    conn.sql("SELECT * FROM read_parquet('data/external/clubelo/*.parquet')")

All tables share these join keys (added by the ingest adapter):
  - ``team_canonical`` : V4 canonical team name (via nutmeg.utils.team_canonical)
  - ``competition_code`` : EPL, ESP_LA_LIGA, etc. (matches V4 league codes)
  - ``date_local`` : match date in local timezone (YYYY-MM-DD)
"""
from __future__ import annotations

from pathlib import Path
from typing import Final

EXTERNAL_DATA_ROOT: Final[Path] = Path("data/external")


# Canonical schema for each source (used by adapters as a sanity check).
CLUBELO_SCHEMA: Final[tuple[str, ...]] = (
    "team_canonical",
    "clubelo_slug",
    "country",
    "elo",
    "from_date",
    "to_date",
)

UNDERSTAT_SCHEMA: Final[tuple[str, ...]] = (
    "team_canonical",
    "opponent_canonical",
    "competition_code",
    "date_local",
    "home_team_canonical",
    "away_team_canonical",
    "xg_home",
    "xg_away",
    "shots_home",
    "shots_away",
    "shots_on_target_home",
    "shots_on_target_away",
    "deep_passes_home",
    "deep_passes_away",
)

FBREF_SCHEMA: Final[tuple[str, ...]] = (
    "team_canonical",
    "competition_code",
    "date_local",
    "home_team_canonical",
    "away_team_canonical",
    "xg_home",
    "xg_away",
    "npxg_home",
    "npxg_away",
    "progressive_passes_home",
    "progressive_passes_away",
    "ppda_home",
    "ppda_away",
)

OPENING_ODDS_SCHEMA: Final[tuple[str, ...]] = (
    "competition_code",
    "date_local",
    "home_team_canonical",
    "away_team_canonical",
    "open_odds_home",
    "open_odds_draw",
    "open_odds_away",
    "open_handicap_line",
    "open_overround",
    "snapshot_minutes_before_kickoff",
)
