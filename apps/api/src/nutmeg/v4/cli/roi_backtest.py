"""nutmeg-roi-backtest — replay historical fixtures through both default
+ lineup-aware artifacts and write A/B sessions into a fresh observation
DB so `nutmeg-ab-report` gives an immediate ROI verdict.

post-v9 P1#17. Closes the 4-6 week wait for real-data lineup ROI
accumulation. Uses football-data.co.uk historical CSVs (already
present locally with EPL + La Liga + ... through 24/25). Each
fixture in the date range is processed:

  1. Synthesize a 'today' moment for that date
  2. Run the recommend pipeline twice — once with the default artifact
     (data/v4_model_cat), once with lineup-aware (data/v4_model_cat_lineups)
  3. Record both sessions to the backtest DB
  4. After all dates: upsert actual outcomes (already known from CSV)
  5. settle_unsettled fires; settlements row is populated

Then the user runs `nutmeg-ab-report --weeks N --db <backtest-db>`
to see the lineup-aware vs default verdict.

This is NOT cheating: model training cutoff is enforced (we skip
fixtures before the artifact's training_cutoff date so no lookahead
bias). Same walk-forward principle as `nutmeg-bench`.

Usage:

    # Default: replay 2024-09 → 2024-12 EPL + La Liga, write to backtest DB
    nutmeg-roi-backtest

    # Custom range + leagues + output DB
    nutmeg-roi-backtest \\
        --start 2024-09-01 --end 2025-05-31 \\
        --leagues EPL,ESP_LA_LIGA,ITA_SERIE_A \\
        --out-db data/v4_observation_backtest.db

The backtest DB is intentionally separate from your real
data/v4_observation.db so it doesn't pollute the real ROI data
the daily cron is collecting.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


log = logging.getLogger("roi_backtest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# Default model artifact paths
DEFAULT_ARTIFACT = "data/v4_model_cat"
LINEUP_ARTIFACT = "data/v4_model_cat_lineups"


def _row_to_fixture(row: pd.Series) -> dict | None:
    """Convert one historical-CSV row into a fixtures-frame row the
    recommend pipeline can consume. Returns None if missing required
    odds (psc_*)."""
    psh = row.get("psc_home")
    psd = row.get("psc_draw")
    psa = row.get("psc_away")
    if pd.isna(psh) or pd.isna(psd) or pd.isna(psa):
        return None
    # Forward every non-NaN column from the historical CSV. The recommend
    # pipeline (build_market_features + build_market_dynamics_features etc.)
    # needs psc_over25 / psc_under25 / ps_home / ps_draw / ps_away / ahch
    # which all exist in football-data CSVs but only some have the strict
    # psc_home/draw/away check above.
    fixture = {}
    for col in row.index:
        v = row[col]
        if pd.notna(v):
            fixture[col] = v
    # Normalize date to string
    fixture["date"] = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
    # Synthesize odds_1x2_H/D/A from Pinnacle closing (psc_*) so the
    # production recommend filter (_row_to_match_input) accepts the row.
    # Production cron has `odds_1x2_*` from API-Football's /odds endpoint;
    # backtest substitutes Pinnacle closing as "the price we'd bet at" —
    # this is the same model V5 uses for ROI backtest reasoning.
    fixture["odds_1x2_H"] = float(psh)
    fixture["odds_1x2_D"] = float(psd)
    fixture["odds_1x2_A"] = float(psa)
    return fixture


def _build_response_dict(
    fixtures_df: pd.DataFrame,
    lambdas: np.ndarray,
    recs,
    bankroll: float,
    artifact_meta: dict,
    model_type: str,
) -> dict:
    """Mirror the shape of RecommendResponse so record_session can
    persist it. Minimum fields the recorder reads."""
    from nutmeg.v4.model.dixon_coles import score_grid, grid_to_1x2

    rho = artifact_meta.get("gbm_rho", -0.10)
    single_preds = []
    for i, row in fixtures_df.iterrows():
        lh, la = lambdas[i]
        grid = score_grid(float(lh), float(la), rho=rho)
        ph, pd_, pa = grid_to_1x2(grid)
        single_preds.append({
            "date": row["date"] if isinstance(row["date"], str) else pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            "league": row["league"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "lambda_home": float(lh),
            "lambda_away": float(la),
            "p_home_1x2": float(ph),
            "p_draw_1x2": float(pd_),
            "p_away_1x2": float(pa),
        })

    rec_dicts = []
    for r in recs:
        # Recommendation has .parlay (Parlay) + .kelly (KellyResult) +
        # .kelly_log_growth + .rank + .stake_units. Hit probability and
        # ev_per_unit are @property forwarded from parlay.
        rec_dicts.append({
            "rank": r.rank,
            "k_legs": r.k_legs,
            "is_compound": r.parlay.is_compound,
            "stake_units": r.stake_units,
            "kelly_recommended_stake": float(r.kelly.recommended_stake),
            "expected_return": float(r.kelly.expected_return),
            "hit_probability": float(r.hit_probability),
            "ev_per_unit": float(r.ev_per_unit),
            "log_growth": float(r.kelly_log_growth),
            "legs": [
                {
                    "match_id": leg.match_id,
                    "market_type": leg.market_type,
                    "selections": [
                        {
                            "outcome": s.outcome,
                            "odds": float(s.odds),
                            "probability": float(s.probability),
                            "edge": float(s.edge),
                        } for s in leg.selections
                    ],
                } for leg in r.parlay.legs
            ],
        })

    # Propagate with_lineups so ab_report can slice arms via
    # json_extract(metadata_json, '$.model.with_lineups')
    model_block = {
        "training_cutoff": artifact_meta.get("training_cutoff", ""),
        "trained_at_utc": artifact_meta.get("trained_at_utc", ""),
        "model_type": model_type,
        "with_lineups": bool(artifact_meta.get("with_lineups", False)),
    }
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": model_block,
        "bankroll": bankroll,
        "n_fixtures": len(fixtures_df),
        "n_recommendations": len(rec_dicts),
        "single_match_predictions": single_preds,
        "recommendations": rec_dicts,
    }


def _replay_one_day(
    db_path: Path,
    day: pd.Timestamp,
    day_matches: pd.DataFrame,
    artifact,
    artifact_name: str,
    bankroll: float,
) -> int:
    """Replay one date through one model. Records 1 session into the DB.

    Returns the number of recommendations generated (0 if no eligible fixtures)."""
    from nutmeg.v4.combo.recommend import recommend_combinations
    from nutmeg.v4.combo.selections import MatchInput
    from nutmeg.v4.model.persist import build_features_for_fixtures, predict_lambdas
    from nutmeg.v4.cli.recommend import _row_to_match_input
    from nutmeg.v4.observation import record_session

    # Build fixtures frame
    fixture_rows = []
    for _, row in day_matches.iterrows():
        fx = _row_to_fixture(row)
        if fx:
            fixture_rows.append(fx)
    if not fixture_rows:
        return 0
    fixtures = pd.DataFrame(fixture_rows)

    # Build features + predict
    feats = build_features_for_fixtures(artifact, fixtures)
    lambdas = predict_lambdas(artifact, feats)

    # Recommendations
    gbm_rho = artifact.metadata.get("gbm_rho", -0.10)
    inputs = []
    for i, row in fixtures.iterrows():
        mi = _row_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            inputs.append(mi)
    if not inputs:
        return 0

    recs = recommend_combinations(
        inputs,
        bankroll=bankroll,
        k_min=2, k_max=8,
        top_n_recommendations=10,
        min_hit_probability=0.05,
        min_kelly_stake=2.0,
        kelly_fraction=0.25,
        max_stake_fraction=0.05,
        include_compound=False,
    )

    response = _build_response_dict(
        fixtures, lambdas, recs, bankroll, artifact.metadata, artifact_name,
    )
    request_dict: dict[str, Any] = {
        "fixtures": fixture_rows,
        "bankroll": bankroll,
        "backtest_date": day.strftime("%Y-%m-%d"),
        "backtest_model": artifact_name,
    }
    # NOTE: recorder reads model_type from response["model"]["model_type"]
    # which _build_response_dict already populates. No extra kwarg needed.
    record_session(db_path, request=request_dict, response=response)
    return len(recs)


def _settle_outcomes(db_path: Path, all_matches: pd.DataFrame) -> dict:
    """Upsert known outcomes from the historical CSVs and run settle."""
    from nutmeg.v4.observation import open_db, upsert_outcome, settle_unsettled
    n_outcomes = 0
    with open_db(db_path) as conn:
        for _, row in all_matches.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue
            upsert_outcome(
                conn,
                match_date=pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                league=row["league"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                home_goals=int(row["home_goals"]),
                away_goals=int(row["away_goals"]),
            )
            n_outcomes += 1
        counts = settle_unsettled(conn)
    counts["n_outcomes_upserted"] = n_outcomes
    return counts


def _detect_lineup_artifact_exists() -> bool:
    """The lineup-aware artifact may not have been trained on this machine.
    If it doesn't exist, we run default-only and emit a clear warning."""
    return Path(LINEUP_ARTIFACT).is_dir()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="P1#17 ROI backtest — accelerate lineup-ROI verdict via historical replay")
    p.add_argument(
        "--data", default="data/historical_sources/football_data_co_uk",
        help="football-data.co.uk tree (already in repo)",
    )
    p.add_argument(
        "--start", default="2024-09-01",
        help="First date to replay (YYYY-MM-DD). Must be ≥ artifact training_cutoff",
    )
    p.add_argument(
        "--end", default="2024-12-31",
        help="Last date to replay (YYYY-MM-DD). Default 4 months ≈ 250+ fixtures across 2 leagues",
    )
    p.add_argument(
        "--leagues", default="EPL,ESP_LA_LIGA",
        help="Comma-separated league codes. More leagues → more sessions → tighter verdict",
    )
    p.add_argument(
        "--out-db", default="data/v4_observation_backtest.db",
        help="Output observation DB. SEPARATE from data/v4_observation.db by default to avoid polluting your real ROI data",
    )
    p.add_argument(
        "--default-artifact", default=DEFAULT_ARTIFACT,
        help="Path to the default-arm artifact (V5 W12 CatBoost)",
    )
    p.add_argument(
        "--lineup-artifact", default=LINEUP_ARTIFACT,
        help="Path to the lineup-aware arm artifact (V6 W7)",
    )
    p.add_argument(
        "--bankroll", type=float, default=1000.0,
        help="Simulated bankroll per session (¥)",
    )
    p.add_argument(
        "--lineup-only", action="store_true",
        help="Skip the default arm (useful if lineup artifact missing — falls back to default-only)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    from nutmeg.v4.data.ingest import load_all_matches
    from nutmeg.v4.model.persist import load_artifact

    out_db = Path(args.out_db)
    if out_db.exists():
        log.warning(
            "Output DB %s already exists. Rows will be APPENDED (not cleared). "
            "Delete it first if you want a clean run.", out_db,
        )

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    if end < start:
        log.error("--end must be ≥ --start")
        return 1

    # Load default artifact + check cutoff
    log.info("Loading default artifact %s ...", args.default_artifact)
    default_art = load_artifact(args.default_artifact)
    default_cutoff = default_art.metadata.get("training_cutoff", "1970-01-01")
    log.info("  default cutoff: %s", default_cutoff)
    if start < pd.Timestamp(default_cutoff):
        log.error(
            "--start %s is BEFORE default model cutoff %s — that would leak "
            "training data into the backtest. Pick --start ≥ %s",
            start.date(), default_cutoff, default_cutoff,
        )
        return 1

    # Optional: lineup artifact
    use_lineup = False
    lineup_art = None
    if not args.lineup_only or args.lineup_artifact != LINEUP_ARTIFACT:
        lineup_dir = Path(args.lineup_artifact)
        if lineup_dir.is_dir():
            log.info("Loading lineup-aware artifact %s ...", args.lineup_artifact)
            try:
                lineup_art = load_artifact(args.lineup_artifact)
                lineup_cutoff = lineup_art.metadata.get("training_cutoff", default_cutoff)
                log.info("  lineup cutoff: %s", lineup_cutoff)
                if start >= pd.Timestamp(lineup_cutoff):
                    use_lineup = True
                else:
                    log.warning(
                        "lineup cutoff %s > --start %s; running default-only "
                        "for the lineup arm to avoid leakage",
                        lineup_cutoff, start.date(),
                    )
            except Exception as e:
                log.warning("could not load lineup artifact: %s — running default-only", e)
        else:
            log.warning(
                "lineup artifact %s not present locally — running default-only. "
                "Train it with `nutmeg-train --with-lineups` to enable the A/B arm.",
                args.lineup_artifact,
            )

    # Load historical matches
    log.info("Loading historical matches from %s ...", args.data)
    all_df = load_all_matches(args.data)
    # Filter by league + date range
    mask = (
        all_df["league"].isin(leagues)
        & (all_df["date"] >= start)
        & (all_df["date"] <= end)
    )
    sub = all_df[mask].copy()
    sub = sub.sort_values("date").reset_index(drop=True)
    log.info(
        "Filtered: %d matches across %d leagues in %s → %s",
        len(sub), len(leagues), start.date(), end.date(),
    )
    if len(sub) == 0:
        log.error("No matches in date range; nothing to replay")
        return 1

    # Group by date and replay
    sub["date_str"] = sub["date"].dt.strftime("%Y-%m-%d")
    n_sessions = {"default": 0, "lineup_aware": 0}
    n_recs = {"default": 0, "lineup_aware": 0}
    for day_str, day_matches in sub.groupby("date_str", sort=True):
        day = pd.Timestamp(day_str)
        # Default arm
        try:
            n = _replay_one_day(out_db, day, day_matches, default_art, "default", args.bankroll)
            n_sessions["default"] += 1
            n_recs["default"] += n
        except Exception as e:
            log.error("  default arm failed for %s: %s", day_str, e)
        # Lineup arm (if available)
        if use_lineup and lineup_art is not None:
            try:
                n = _replay_one_day(out_db, day, day_matches, lineup_art, "lineup_aware", args.bankroll)
                n_sessions["lineup_aware"] += 1
                n_recs["lineup_aware"] += n
            except Exception as e:
                log.error("  lineup arm failed for %s: %s", day_str, e)
        if (n_sessions["default"]) % 10 == 0:
            log.info(
                "  progress: %s, %d days, default=%d recs, lineup=%d recs",
                day_str, n_sessions["default"], n_recs["default"], n_recs["lineup_aware"],
            )

    log.info(
        "Done replay: %d days, default %d sessions (%d recs), lineup %d sessions (%d recs)",
        len(sub.date_str.unique()),
        n_sessions["default"], n_recs["default"],
        n_sessions["lineup_aware"], n_recs["lineup_aware"],
    )

    # Settle
    log.info("Settling against known outcomes ...")
    settle_stats = _settle_outcomes(out_db, sub)
    log.info("Settle stats: %s", settle_stats)

    log.info("✓ Backtest complete. DB: %s", out_db)
    log.info(
        "Next: PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ab_report "
        "--weeks %d --db %s",
        max(1, (end - start).days // 7),
        out_db,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
