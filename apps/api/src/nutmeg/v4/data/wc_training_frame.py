"""V10 W1 Track B — Build the unified training frame for WC modeling.

Joins:
  - WC fixtures (data/external/cup_history/WC_{season}.parquet)
  - WC closing odds (data/external/cup_odds/WC_{season}.parquet)
  - National-team Elo snapshot (data/external/eloratings/eloratings_{date}.parquet)

Output: one row per match with home/away teams, scores, closing odds, and
Elo for both sides + Elo diff. Ready for model training (Day 3).

Why a dedicated frame builder (not the V8 W2 cup_training UNION path):
  - V8 W2's UNION was the basis for P1#20 cup ablation → NEGATIVE
  - We're explicitly using a SEPARATE model architecture for national teams
    (per Q3 discussion conclusions): not retraining domestic CatBoost
  - This frame feeds a lightweight Elo+market model in Day 3
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code


def load_elo_snapshot(snapshot_path: Path | str) -> dict[str, dict[str, float]]:
    """Read eloratings parquet → {country_code: {elo: 1900, rank: 1, ...}}."""
    df = pd.read_parquet(snapshot_path)
    return {row["country_code"]: dict(row) for _, row in df.iterrows()}


def build_wc_training_frame(
    season: int,
    cup_history_dir: Path | str = "data/external/cup_history",
    cup_odds_dir: Path | str = "data/external/cup_odds",
    elo_snapshot_path: Optional[Path | str] = None,
) -> pd.DataFrame:
    """Build a flat per-match frame for one WC season.

    Args:
        season: start year (2018 / 2022 / 2026 ...).
        cup_history_dir: source of WC_{season}.parquet fixtures.
        cup_odds_dir:    source of WC_{season}.parquet odds.
        elo_snapshot_path: parquet from eloratings.net. If None, looks for
            the most recent `data/external/eloratings/eloratings_*.parquet`.

    Returns:
        DataFrame with columns:
          date, league, season,
          home_team, away_team,
          home_goals, away_goals,    (NaN for not-yet-played)
          home_elo, away_elo, elo_diff,
          home_elo_rank, away_elo_rank,
          psc_home, psc_draw, psc_away,  (NaN if pre-tournament)
          api_football_id,
          status_short, round_label,
    """
    cup_history_dir = Path(cup_history_dir)
    cup_odds_dir = Path(cup_odds_dir)

    fixtures_path = cup_history_dir / f"WC_{season}.parquet"
    if not fixtures_path.exists():
        raise FileNotFoundError(
            f"WC {season} fixtures not found at {fixtures_path}. "
            f"Run: nutmeg-ingest-cup-history --leagues WC --seasons {season}"
        )
    fixtures = pd.read_parquet(fixtures_path)
    fixtures["season"] = season

    # Optional odds join (NaN for pre-tournament or pre-2020 seasons)
    odds_path = cup_odds_dir / f"WC_{season}.parquet"
    if odds_path.exists():
        odds = pd.read_parquet(odds_path)
        # Odds parquet keys by api_football_id; fixtures has it too
        odds_cols = ["psc_home", "psc_draw", "psc_away"]
        # Some odds parquets may not include all cols; use what's there
        odds_join_cols = ["api_football_id"] + [c for c in odds_cols if c in odds.columns]
        # Avoid pulling duplicate league/season from odds parquet
        merged = fixtures.merge(
            odds[odds_join_cols].drop_duplicates(subset=["api_football_id"]),
            on="api_football_id",
            how="left",
        )
    else:
        merged = fixtures.copy()
        merged["psc_home"] = pd.NA
        merged["psc_draw"] = pd.NA
        merged["psc_away"] = pd.NA

    # Elo snapshot join
    if elo_snapshot_path is None:
        snapshots = sorted(Path("data/external/eloratings").glob("eloratings_*.parquet"))
        if not snapshots:
            raise FileNotFoundError(
                "No eloratings snapshot found under data/external/eloratings/. "
                "Run the eloratings scraper (see docs/v10_w1_day2_*.md)."
            )
        elo_snapshot_path = snapshots[-1]

    elo = load_elo_snapshot(elo_snapshot_path)

    def _elo_for(team_name: str) -> tuple[float | None, int | None]:
        code = lookup_elo_code(team_name)
        if code and code in elo:
            return float(elo[code]["elo"]), int(elo[code]["rank"])
        return None, None

    home_elos, away_elos = [], []
    home_ranks, away_ranks = [], []
    for _, row in merged.iterrows():
        he, hr = _elo_for(row["home_team"])
        ae, ar = _elo_for(row["away_team"])
        home_elos.append(he)
        away_elos.append(ae)
        home_ranks.append(hr)
        away_ranks.append(ar)

    merged["home_elo"] = home_elos
    merged["away_elo"] = away_elos
    merged["home_elo_rank"] = home_ranks
    merged["away_elo_rank"] = away_ranks
    merged["elo_diff"] = [
        (h - a) if h is not None and a is not None else None
        for h, a in zip(home_elos, away_elos)
    ]

    # Column ordering for readability
    ordered = [
        "date", "league", "season",
        "home_team", "away_team",
        "home_goals", "away_goals",
        "home_elo", "away_elo", "elo_diff",
        "home_elo_rank", "away_elo_rank",
        "psc_home", "psc_draw", "psc_away",
        "api_football_id",
        "status_short", "round_label",
    ]
    keep = [c for c in ordered if c in merged.columns]
    return merged[keep].copy()


__all__ = ["build_wc_training_frame", "load_elo_snapshot"]
