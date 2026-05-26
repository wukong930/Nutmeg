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
from nutmeg.v4.features.pipeline import feature_columns_with_cup
from nutmeg.v4.features.lineup_features import _fixture_key
from nutmeg.v4.features.pipeline import (
    LINEUP_VALIDATED_COLUMNS,
    feature_columns_with_fatigue,
    feature_columns_with_lineups,
)
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
        default="cat",
        help="Booster backend. 'cat' = CatBoost (V5 W12 default — uses `league` "
        "as a categorical feature; multi-season tests show -0.0033 log-loss "
        "improvement vs lgb across 3 seasons). 'lgb' = lightgbm (V4 legacy "
        "fallback; available for A/B comparison).",
    )
    parser.add_argument(
        "--with-lineups",
        action="store_true",
        help="Include V6 W6 validated lineup features (recent_n_injuries 30-day "
        "unique). Requires API-Football lineup cache; populated by "
        "`nutmeg-ingest-lineups`. Cache dir defaults to data/external/api_football.",
    )
    parser.add_argument(
        "--lineup-leagues",
        default="EPL,ESP_LA_LIGA",
        help="Comma-separated V4 league codes to pull lineup data for (only used "
        "with --with-lineups). Default: EPL,ESP_LA_LIGA (the leagues validated "
        "in V6 W6).",
    )
    parser.add_argument(
        "--lineup-seasons",
        default="2023,2024",
        help="Comma-separated season-start years for lineup ingest (only used "
        "with --with-lineups). Default: 2023,2024.",
    )
    parser.add_argument(
        "--with-cup-features",
        action="store_true",
        help="V7 W7 — include the 5 V6 W11 cup side-channel feature columns "
        "(is_cup_match / is_knockout / is_two_legged / "
        "is_national_team_match / competition_type_id). Loads cup-history "
        "parquets (V7 W6) and merges round-label info onto the training "
        "frame. Domestic-league rows emit 0 for every cup column; only "
        "cup-match rows contribute signal. **NOTE**: V7 W7 ships the "
        "wiring only; actual cup-data training value depends on cup "
        "fixtures being present in the training frame, which requires "
        "odds backfill (V7 W8+ work).",
    )
    parser.add_argument(
        "--cup-history-dir",
        default="data/external/cup_history",
        help="Where the V7 W6 cup-history parquets live "
        "(default data/external/cup_history). Only used with "
        "--with-cup-features.",
    )
    parser.add_argument(
        "--cup-leagues",
        default="UCL,UEL",
        help="Comma-separated cup codes to load from the cup-history dir "
        "(default UCL,UEL). Only used with --with-cup-features.",
    )
    parser.add_argument(
        "--cup-seasons",
        default="2021,2022,2023,2024",
        help="Comma-separated cup season-start years to load "
        "(default 2021,2022,2023,2024). Used with --with-cup-features "
        "and/or --with-cup-data.",
    )
    parser.add_argument(
        "--with-cup-data",
        action="store_true",
        help="V8 W2 — UNION cup training rows into the V4 training frame. "
        "Reads V7 W6 cup-history + V7 W8 cup-odds parquets, applies "
        "to_v4_canonical_global to map team names, pads V4 schema cols "
        "the parquets don't carry (shots/corners/cards → NaN; alt-book "
        "odds → psc_* proxy). Different from --with-cup-features (which "
        "only ADDS the 5 cup feature COLUMNS without adding any rows). "
        "Combine both flags for the full cup-data + cup-features run.",
    )
    parser.add_argument(
        "--cup-odds-dir",
        default="data/external/cup_odds",
        help="V8 W2 — where V7 W8 cup-odds parquets live "
        "(default data/external/cup_odds). Only used with --with-cup-data.",
    )
    parser.add_argument(
        "--cup-canonical-fuzzy",
        type=float, default=0.86,
        help="V8 W1 fuzzy-match cutoff for cup team-name resolution "
        "(default 0.86). Lower = more permissive but riskier silent "
        "wrong joins. Only used with --with-cup-data.",
    )
    parser.add_argument(
        "--nation-elo-cache-dir",
        default=None,
        help="Post-V8 P1#4 — when set (e.g. data/external/clubelo_national), "
        "load per-nation Elo histories via build_nation_elo_lookup and pass "
        "to build_elo_features. National-team-cup rows (WC, EURO, COPA_AMERICA, "
        "WC_QUAL_UEFA) get seeded from the real clubelo nation Elo instead "
        "of the default 1500. Requires --with-cup-data to be effective (cross-"
        "league seeding only fires when that flag is set). Run `nutmeg-ingest-"
        "national-elo` first to populate the cache.",
    )
    parser.add_argument(
        "--with-fatigue",
        action="store_true",
        help="V12 Day 2 (post-V11 audit) — include the 12 fatigue / "
        "fixture-congestion features (short-rest flags 3/5 day, long-rest "
        "rust 14-day, euro-midweek-4day, third-match-in-8day, "
        "matches-in-30day; × home/away). Zero new data dependency — uses "
        "the existing date/home/away/league columns. Day 1 audit "
        "(docs/v12_stadium_fatigue_day1_audit.md) verified 10/12 features "
        "fire on real EPL 24/25 with sensible distributions; euro-midweek "
        "stays 0 on single-league data (gate enabled only when training "
        "frame includes UCL/UEL via --with-cup-data).",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    t0 = time.time()
    _info(f"Loading matches from {args.data} ...", args.quiet)
    df = load_all_matches(args.data)
    _info(f"  loaded {len(df):,} matches", args.quiet)

    # V8 W2: optional cup-data UNION. When --with-cup-data, load
    # V7 W6 + V7 W8 cup parquets, canonicalize team names, pad V4
    # schema cols, and concat into the training frame. Different
    # from --with-cup-features (which only adds COLUMNS); --with-
    # cup-data adds ROWS.
    if args.with_cup_data:
        from pathlib import Path as _Path
        from nutmeg.v4.data.cup_training import (
            build_cup_training_rows,
            union_league_and_cup,
        )
        cup_leagues = [s.strip() for s in args.cup_leagues.split(",") if s.strip()]
        cup_seasons = [int(s.strip()) for s in args.cup_seasons.split(",") if s.strip()]
        cup_rows = build_cup_training_rows(
            _Path(args.cup_history_dir),
            _Path(args.cup_odds_dir),
            leagues=cup_leagues,
            seasons=cup_seasons,
            league_team_df=df,
            fuzzy_threshold=args.cup_canonical_fuzzy,
        )
        _info(
            f"  cup data: {len(cup_rows)} resolved cup rows "
            f"({len(cup_leagues)} cups × {len(cup_seasons)} seasons)",
            args.quiet,
        )
        df = union_league_and_cup(df, cup_rows)
        _info(f"  after cup UNION: {len(df):,} matches total", args.quiet)

    cutoff = pd.Timestamp(args.cutoff) if args.cutoff else df["date"].max() + pd.Timedelta(days=1)
    _info(f"Training cutoff: {cutoff.date()}", args.quiet)

    # V6 W6: optional lineup feature integration. When --with-lineups, build
    # the recent_injury_lookup from the API-Football cache and feed it through
    # build_feature_frame so the validated 2-column subset is emitted.
    lineup_lookup = None
    injury_lookup = None
    recent_injury_lookup = None
    if args.with_lineups:
        from nutmeg.v4.data.lineup_lookup import (
            build_lineup_lookup_from_cache,
            build_recent_injury_lookup,
        )
        lineups: dict = {}
        recent: dict = {}
        leagues_to_pull = [s.strip() for s in args.lineup_leagues.split(",") if s.strip()]
        seasons_to_pull = [int(s.strip()) for s in args.lineup_seasons.split(",") if s.strip()]
        for league in leagues_to_pull:
            teams = sorted(
                set(df.loc[df["league"] == league, "home_team"].dropna().unique())
            )
            for season in seasons_to_pull:
                lin, _, _ = build_lineup_lookup_from_cache(league, season, teams)
                lineups.update(lin)
                ri = build_recent_injury_lookup(league, season, teams)
                recent.update(ri)
        lineup_lookup = lineups
        recent_injury_lookup = recent
        _info(
            f"  lineup cache: {len(lineups)} fixtures, {len(recent)} with recent-injury counts",
            args.quiet,
        )

    # V7 W7: optional cup-history merge. When --with-cup-features, load
    # per-(league, season) parquets from --cup-history-dir into a single
    # DataFrame and pass through build_feature_frame so the 5 V6 W11 cup
    # side-channel cols get appended. Domestic-league rows emit 0; cup
    # rows (when present in `df`) pick up the structural flags.
    cup_history_df = None
    if args.with_cup_features:
        from pathlib import Path as _Path
        from nutmeg.v4.data.cup_history import load_multi_season_cup_history
        cup_leagues = [s.strip() for s in args.cup_leagues.split(",") if s.strip()]
        cup_seasons = [int(s.strip()) for s in args.cup_seasons.split(",") if s.strip()]
        cup_history_df = load_multi_season_cup_history(
            _Path(args.cup_history_dir),
            leagues=cup_leagues,
            seasons=cup_seasons,
        )
        _info(
            f"  cup history: {len(cup_history_df)} fixtures across "
            f"{len(cup_leagues)} cups × {len(cup_seasons)} seasons",
            args.quiet,
        )

    # Post-V8 P1#4: optional nation-state Elo for national-team-cup rows
    nation_state = None
    if args.nation_elo_cache_dir:
        from pathlib import Path as _Path
        from nutmeg.v4.data.national_team_elo import build_nation_elo_lookup
        nation_state = build_nation_elo_lookup(_Path(args.nation_elo_cache_dir))
        _info(
            f"  nation Elo: {len(nation_state)} countries loaded from "
            f"{args.nation_elo_cache_dir}",
            args.quiet,
        )

    _info("Building features ...", args.quiet)
    # V8 W3: auto-enable cross-league seeding when --with-cup-data is set —
    # cup-row Elo/form needs to draw on the team's domestic-league history.
    feats = build_feature_frame(
        df,
        lineup_lookup=lineup_lookup,
        injury_lookup=injury_lookup,
        recent_injury_lookup=recent_injury_lookup,
        cup_history_df=cup_history_df,
        cross_league_seed=args.with_cup_data,
        nation_state=nation_state,
        with_fatigue=args.with_fatigue,
    )

    # Time split
    val_start = cutoff - pd.Timedelta(days=args.validation_days)
    train = feats[(feats.date < val_start) & feats.psc_home.notna()].copy()
    val = feats[(feats.date >= val_start) & (feats.date < cutoff) & feats.psc_home.notna()].copy()
    _info(f"  Train: {len(train):,} matches    Val: {len(val):,} matches", args.quiet)

    if len(train) < 500:
        print(f"ERROR: not enough training matches ({len(train)})", file=sys.stderr)
        return 1

    # Compose feature column list. Each flag is INDEPENDENT — the GBM
    # input is the union of whichever transforms were actually run:
    #   --with-lineups        → +2 lineup validated cols (V6 W6)
    #   --with-cup-features   → +5 cup side-channel cols (V6 W11 + V7 W6)
    #   --with-fatigue        → +12 fatigue cols (V12 Day 2 post-V11 audit)
    #   any combination       → union of the above on top of GBM_FEATURE_COLUMNS
    # Conflating any flag into another would break callers that only
    # have one data source ingested.
    if args.with_fatigue:
        # The 12 fatigue cols stack on top of whatever lineup/cup combo
        # is in use. feature_columns_with_fatigue handles the matrix.
        base_numeric_cols = feature_columns_with_fatigue(
            include_lineups=args.with_lineups,
            include_cup=args.with_cup_features,
        )
    elif args.with_cup_features and args.with_lineups:
        base_numeric_cols = feature_columns_with_cup(include_lineups=True)
    elif args.with_cup_features:
        base_numeric_cols = feature_columns_with_cup(include_lineups=False)
    elif args.with_lineups:
        base_numeric_cols = feature_columns_with_lineups()
    else:
        base_numeric_cols = list(GBM_FEATURE_COLUMNS)

    # Booster training — backend depends on --model
    if args.model == "cat":
        _info(
            f"Training CatBoost-λ (Poisson × 2; league as categorical; "
            f"{'with' if args.with_lineups else 'without'} lineup features) ...",
            args.quiet,
        )
        cat_feature_cols = list(base_numeric_cols) + ["league"]
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
        _info(
            f"Training GBM-λ (Poisson lightgbm × 2; "
            f"{'with' if args.with_lineups else 'without'} lineup features) ...",
            args.quiet,
        )
        booster = fit_gbm_lambda(train, val, feature_cols=base_numeric_cols)
        feature_columns_used = list(base_numeric_cols)
        cat_features_used = []
        model_type = "lightgbm"
        booster_home_obj = booster.model_home
        booster_away_obj = booster.model_away
        best_iter_home = booster.best_iter_home
        best_iter_away = booster.best_iter_away

        val_clean = val.dropna(subset=base_numeric_cols).copy()
        X_val = val_clean[base_numeric_cols].astype(float).values
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
            # V6 W7 marker
            "with_lineups": bool(args.with_lineups),
            "lineup_leagues": (
                args.lineup_leagues.split(",") if args.with_lineups else []
            ),
            "lineup_seasons": (
                [int(s) for s in args.lineup_seasons.split(",")] if args.with_lineups else []
            ),
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
