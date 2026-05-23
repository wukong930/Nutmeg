"""V4 train CLI.

Usage:
    python -m nutmeg.v4.cli.train [--data DIR] [--cutoff YYYY-MM-DD] [--out DIR]

Trains:
  - GBM-λ (lightgbm Poisson regression × 2 for home/away)
  - Temperature calibrator (single-parameter softmax scaling on validation pool)
Saves the artifact to `--out` directory.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from nutmeg.v4.calibration.temperature import fit_temperature_1x2
from nutmeg.v4.data import load_all_matches
from nutmeg.v4.features import GBM_FEATURE_COLUMNS, build_feature_frame
from nutmeg.v4.model.cat_lambda import fit_cat_lambda
from nutmeg.v4.model.dixon_coles import lambdas_to_1x2_array
from nutmeg.v4.model.gbm_lambda import fit_gbm_lambda
from nutmeg.v4.model.persist import V4Artifact, build_team_state, save_artifact


DEFAULT_VALIDATION_DAYS = 90
DEFAULT_OUTPUT_DIR = "data/v4_model"
DEFAULT_GBM_RHO = -0.10


def _info(msg: str, quiet: bool):
    if not quiet:
        print(msg, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V4 train CLI")
    parser.add_argument("--data", default="data/historical_sources/football_data_co_uk",
                        help="Source CSV tree")
    parser.add_argument("--cutoff", default=None,
                        help="Training cutoff date YYYY-MM-DD (default = max date in data)")
    parser.add_argument("--validation-days", type=int, default=DEFAULT_VALIDATION_DAYS,
                        help="Days before cutoff used as validation for temperature fit")
    parser.add_argument("--out", default=DEFAULT_OUTPUT_DIR, help="Artifact output dir")
    parser.add_argument("--gbm-rho", type=float, default=DEFAULT_GBM_RHO,
                        help="DC tau correction parameter for lambda → score grid")
    parser.add_argument(
        "--model",
        choices=("lgb", "cat"),
        default="lgb",
        help="Booster backend. 'lgb' = lightgbm (V4 default). 'cat' = CatBoost "
        "(V5 W7 — uses `league` as a categorical feature; multi-season "
        "tests show -0.0033 log-loss improvement vs lgb).",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    t0 = time.time()
    _info(f"Loading matches from {args.data} ...", args.quiet)
    df = load_all_matches(args.data)
    _info(f"  loaded {len(df):,} matches", args.quiet)

    cutoff = pd.Timestamp(args.cutoff) if args.cutoff else df["date"].max() + pd.Timedelta(days=1)
    _info(f"Training cutoff: {cutoff.date()}", args.quiet)

    _info("Building features ...", args.quiet)
    feats = build_feature_frame(df)

    # Time split
    val_start = cutoff - pd.Timedelta(days=args.validation_days)
    train = feats[(feats.date < val_start) & feats.psc_home.notna()].copy()
    val = feats[(feats.date >= val_start) & (feats.date < cutoff) & feats.psc_home.notna()].copy()
    _info(f"  Train: {len(train):,} matches    Val: {len(val):,} matches", args.quiet)

    if len(train) < 500:
        print(f"ERROR: not enough training matches ({len(train)})", file=sys.stderr)
        return 1

    # Booster training — backend depends on --model
    if args.model == "cat":
        _info("Training CatBoost-λ (Poisson × 2; league as categorical) ...", args.quiet)
        cat_feature_cols = list(GBM_FEATURE_COLUMNS) + ["league"]
        booster = fit_cat_lambda(
            train, val, feature_cols=cat_feature_cols, cat_features=["league"]
        )
        feature_columns_used = cat_feature_cols
        cat_features_used = ["league"]
        model_type = "catboost"
        booster_home_obj = booster.model_home
        booster_away_obj = booster.model_away
        best_iter_home = booster.best_iter_home
        best_iter_away = booster.best_iter_away

        # Val predictions for temperature
        val_clean = val.dropna(subset=["home_goals", "away_goals"]).copy()
        lam_val = booster.predict(val_clean)
        lh_val, la_val = lam_val[:, 0], lam_val[:, 1]
    else:
        _info("Training GBM-λ (Poisson lightgbm × 2) ...", args.quiet)
        booster = fit_gbm_lambda(train, val, feature_cols=GBM_FEATURE_COLUMNS)
        feature_columns_used = list(GBM_FEATURE_COLUMNS)
        cat_features_used = []
        model_type = "lightgbm"
        booster_home_obj = booster.model_home
        booster_away_obj = booster.model_away
        best_iter_home = booster.best_iter_home
        best_iter_away = booster.best_iter_away

        val_clean = val.dropna(subset=GBM_FEATURE_COLUMNS).copy()
        X_val = val_clean[GBM_FEATURE_COLUMNS].astype(float).values
        lh_val = booster.model_home.predict(X_val)
        la_val = booster.model_away.predict(X_val)
        lh_val = np.clip(lh_val, 0.05, 8.0)
        la_val = np.clip(la_val, 0.05, 8.0)

    _info(f"  best_iter home={best_iter_home}, away={best_iter_away}", args.quiet)

    # Temperature calibration on validation predictions
    _info("Fitting temperature calibrator on validation pool ...", args.quiet)
    probs_val = lambdas_to_1x2_array(np.column_stack([lh_val, la_val]), rho=args.gbm_rho)
    temperature_T = None
    if len(probs_val) >= 100:
        cal = fit_temperature_1x2(probs_val, val_clean.result_1x2.values)
        temperature_T = cal.T
        _info(f"  fitted T = {temperature_T:.3f} (nll: {cal.nll_before:.4f} → {cal.nll_after:.4f})",
              args.quiet)

    # Team state snapshot at cutoff
    _info("Capturing team state at cutoff ...", args.quiet)
    pre_cutoff = feats[feats.date < cutoff].copy()
    team_state = build_team_state(pre_cutoff)
    n_pairs = sum(len(t) for t in team_state.values())
    _info(f"  {n_pairs} (league, team) pairs across {len(team_state)} leagues", args.quiet)

    # Build artifact
    artifact = V4Artifact(
        metadata={
            "training_cutoff": str(cutoff.date()),
            "validation_days": args.validation_days,
            "n_train": int(len(train)),
            "n_val": int(len(val)),
            "gbm_rho": args.gbm_rho,
            "gbm_best_iter_home": int(best_iter_home),
            "gbm_best_iter_away": int(best_iter_away),
            "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        feature_columns=feature_columns_used,
        booster_home=booster_home_obj,
        booster_away=booster_away_obj,
        temperature_T=temperature_T,
        team_state=team_state,
        model_type=model_type,
        cat_features=cat_features_used,
    )

    out_path = Path(args.out)
    save_artifact(artifact, out_path)
    _info(f"\nArtifact saved to: {out_path}", args.quiet)
    _info(f"Total elapsed: {time.time() - t0:.1f}s", args.quiet)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
