"""nutmeg-cup-ablation — multi-fold ablation runner for cup-data training.

V8 W3 — runs walk_forward across N (cutoff, mode) combinations to
measure whether `--with-cup-data` and/or `--with-cup-features`
actually improve log-loss on held-out league fixtures.

This is the test V6 W6 used to validate `recent_n_injuries` before
V6 W7 shipped the lineup-aware artifact. **Same ship gate**: ≥ 3/4
folds improve by ≥ −0.001 log-loss → V8 W4 ships
`data/v4_model_cat_cup/` as opt-in.

Usage:

    # Default ablation: 4 cutoffs × 3 modes (baseline / data / data+features)
    nutmeg-cup-ablation --out docs/v8_w3_cup_ablation.md

    # Tighter sweep
    nutmeg-cup-ablation --cutoffs 2024-08-01 --modes baseline,cup_data

Prerequisite:
    Run `nutmeg-ingest-cup-history` + `nutmeg-ingest-cup-odds` for the
    seasons you want in the cup pool. The ablation reads those parquets
    via `--cup-history-dir` + `--cup-odds-dir`.

Modes:
    baseline       — no cup data, no cup features (V5 W12 default)
    cup_data       — UNION cup rows into training (V8 W2); cross_league_seed
                     enabled automatically; no cup feature columns
    cup_features   — adds the 5 W11 cup feature columns; NO cup data UNION
                     (sanity check: cup cols alone on league-only training
                     should not change anything, since every league row
                     emits 0 for is_cup_match)
    cup_full       — both: cup data UNION + cup features columns
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

from nutmeg.v4.data.cup_history import load_multi_season_cup_history
from nutmeg.v4.data.cup_training import (
    build_cup_training_rows,
    union_league_and_cup,
)
from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.metrics import summary
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


log = logging.getLogger("cup_ablation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


VALID_MODES = ("baseline", "cup_data", "cup_features", "cup_full")


def _parse_cutoff(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _build_inputs_for_mode(
    league_df: pd.DataFrame,
    mode: str,
    *,
    cup_history_dir: Path,
    cup_odds_dir: Path,
    cup_leagues: list[str],
    cup_seasons: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame | None, bool]:
    """Construct (df, cup_history_df_for_features, cross_league_seed) per mode.

    Returns the inputs to feed `WalkForwardConfig(...)` for one ablation run.
    """
    if mode == "baseline":
        return league_df, None, False
    if mode == "cup_features":
        # Cup feature COLUMNS, no UNION
        cup_hist = load_multi_season_cup_history(
            cup_history_dir, cup_leagues, cup_seasons,
        )
        return league_df, cup_hist if len(cup_hist) > 0 else None, False
    # Both cup_data and cup_full need the UNION
    cup_rows = build_cup_training_rows(
        cup_history_dir, cup_odds_dir,
        leagues=cup_leagues, seasons=cup_seasons,
        league_team_df=league_df,
    )
    unioned = union_league_and_cup(league_df, cup_rows)
    if mode == "cup_data":
        return unioned, None, True
    # cup_full
    cup_hist = load_multi_season_cup_history(
        cup_history_dir, cup_leagues, cup_seasons,
    )
    return unioned, cup_hist if len(cup_hist) > 0 else None, True


def run_one_fold(
    league_df: pd.DataFrame,
    cutoff: pd.Timestamp,
    mode: str,
    *,
    cup_history_dir: Path,
    cup_odds_dir: Path,
    cup_leagues: list[str],
    cup_seasons: list[int],
) -> dict:
    """Run a single (cutoff, mode) fold; return the pooled metric summary."""
    df, cup_hist, cross_seed = _build_inputs_for_mode(
        league_df, mode,
        cup_history_dir=cup_history_dir, cup_odds_dir=cup_odds_dir,
        cup_leagues=cup_leagues, cup_seasons=cup_seasons,
    )
    cfg = WalkForwardConfig(
        test_cutoff=cutoff,
        cup_history_df=cup_hist,
        cross_league_seed=cross_seed,
    )
    result = run_walk_forward(df, cfg)
    pooled = result.get("pooled", {})
    return {
        "n_test": int(pooled.get("n_test", 0)),
        # Use the CatBoost (or LightGBM if catboost missing) GBM line — that's
        # what the production artifact ships
        "log_loss_gbm_temp": float(pooled.get("log_loss_gbm_temp", float("nan"))),
        "brier_gbm_temp":    float(pooled.get("brier_gbm_temp", float("nan"))),
        "hit_rate_gbm":      float(pooled.get("hit_rate_gbm", float("nan"))),
    }


def format_ablation_report(
    rows: list[dict],
    *,
    cup_leagues: list[str],
    cup_seasons: list[int],
) -> str:
    """Markdown card with per-(cutoff, mode) log-loss + delta vs baseline."""
    lines: list[str] = []
    lines.append("# V8 W3 — cup-data ablation\n")
    lines.append(
        f"_Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_  "
        f"_Cups: {', '.join(cup_leagues)}_  "
        f"_Seasons: {cup_seasons}_\n"
    )
    lines.append("")
    # Pivot rows by cutoff
    by_cutoff: dict[pd.Timestamp, dict[str, dict]] = {}
    for r in rows:
        by_cutoff.setdefault(r["cutoff"], {})[r["mode"]] = r["result"]

    lines.append("| cutoff | mode | n_test | log_loss | Δ vs baseline | hit-rate |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for cutoff in sorted(by_cutoff.keys()):
        baseline = by_cutoff[cutoff].get("baseline", {})
        baseline_ll = baseline.get("log_loss_gbm_temp", float("nan"))
        for mode in VALID_MODES:
            data = by_cutoff[cutoff].get(mode)
            if data is None:
                continue
            ll = data["log_loss_gbm_temp"]
            delta = (ll - baseline_ll) if not (pd.isna(ll) or pd.isna(baseline_ll)) else float("nan")
            delta_str = f"{delta:+.4f}" if not pd.isna(delta) else "—"
            lines.append(
                f"| {cutoff.date()} | {mode} | {data['n_test']:,} | "
                f"{ll:.4f} | {delta_str} | {data['hit_rate_gbm']:.4f} |"
            )
        lines.append("")

    # Ship-gate summary
    lines.append("## Ship gate")
    lines.append(
        "Per V6 W6 methodology: cup-aware artifact ships in V8 W4 only when "
        "**≥ 3/4 folds** show `cup_full` improving over `baseline` by "
        "≥ −0.001 log-loss."
    )
    lines.append("")

    n_folds = 0
    n_improved = 0
    for cutoff, modes in by_cutoff.items():
        if "baseline" not in modes or "cup_full" not in modes:
            continue
        n_folds += 1
        base_ll = modes["baseline"]["log_loss_gbm_temp"]
        full_ll = modes["cup_full"]["log_loss_gbm_temp"]
        if pd.isna(base_ll) or pd.isna(full_ll):
            continue
        if (full_ll - base_ll) <= -0.001:
            n_improved += 1
    if n_folds == 0:
        lines.append("⚠️ Couldn't compute gate — no `baseline` × `cup_full` pairs.")
    elif n_improved >= 3 and n_folds >= 4:
        lines.append(f"✅ Gate PASSED ({n_improved}/{n_folds} folds improved ≥ −0.001 log-loss).")
        lines.append("→ V8 W4 should ship `data/v4_model_cat_cup/` as opt-in artifact.")
    else:
        lines.append(f"❌ Gate NOT passed ({n_improved}/{n_folds} folds improved ≥ −0.001 log-loss).")
        lines.append("→ Do NOT ship cup-aware artifact. Document negative result in V8 W4.")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V8 W3 cup-data ablation runner (multi-fold)",
    )
    p.add_argument(
        "--data",
        default="data/historical_sources/football_data_co_uk",
        help="Football-data.co.uk tree",
    )
    p.add_argument(
        "--cup-history-dir",
        type=Path,
        default=Path("data/external/cup_history"),
    )
    p.add_argument(
        "--cup-odds-dir",
        type=Path,
        default=Path("data/external/cup_odds"),
    )
    p.add_argument(
        "--cup-leagues",
        default="UCL,UEL",
        help="Cup competitions to include in the UNION pool",
    )
    p.add_argument(
        "--cup-seasons",
        default="2021,2022,2023,2024",
    )
    p.add_argument(
        "--cutoffs",
        default="2024-01-15,2024-05-01,2024-08-01,2024-12-01",
        help="Comma-separated test cutoffs (YYYY-MM-DD)",
    )
    p.add_argument(
        "--modes",
        default="baseline,cup_data,cup_features,cup_full",
        help=f"Comma-separated ablation modes (subset of {VALID_MODES})",
    )
    p.add_argument(
        "--out",
        default="docs/v8_w3_cup_ablation.md",
        help="Output markdown card path",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    try:
        cutoffs = [_parse_cutoff(s.strip()) for s in args.cutoffs.split(",") if s.strip()]
    except Exception as exc:  # noqa: BLE001
        log.error("could not parse --cutoffs=%r: %s", args.cutoffs, exc)
        return 2
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    for m in modes:
        if m not in VALID_MODES:
            log.error("unknown mode %r; valid: %s", m, VALID_MODES)
            return 2

    cup_leagues = [s.strip() for s in args.cup_leagues.split(",") if s.strip()]
    cup_seasons = [int(s.strip()) for s in args.cup_seasons.split(",") if s.strip()]

    data_path = Path(args.data)
    if not data_path.exists():
        log.error("football-data tree not found at %s", data_path)
        return 1
    log.info("Loading league data ...")
    league_df = load_all_matches(str(data_path))
    log.info("Loaded %d league matches", len(league_df))

    rows: list[dict] = []
    for cutoff in cutoffs:
        for mode in modes:
            log.info("Fold cutoff=%s mode=%s ...", cutoff.date(), mode)
            try:
                result = run_one_fold(
                    league_df, cutoff, mode,
                    cup_history_dir=args.cup_history_dir,
                    cup_odds_dir=args.cup_odds_dir,
                    cup_leagues=cup_leagues,
                    cup_seasons=cup_seasons,
                )
            except Exception as exc:  # noqa: BLE001
                log.error("fold %s/%s failed: %s", cutoff.date(), mode, exc)
                result = {
                    "n_test": 0,
                    "log_loss_gbm_temp": float("nan"),
                    "brier_gbm_temp": float("nan"),
                    "hit_rate_gbm": float("nan"),
                }
            log.info(
                "  → n_test=%d log_loss=%.4f hit_rate=%.4f",
                result["n_test"],
                result["log_loss_gbm_temp"],
                result["hit_rate_gbm"],
            )
            rows.append({"cutoff": cutoff, "mode": mode, "result": result})

    card = format_ablation_report(
        rows, cup_leagues=cup_leagues, cup_seasons=cup_seasons,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(card, encoding="utf-8")
    log.info("Wrote ablation card → %s", out_path)
    print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
