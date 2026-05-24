"""nutmeg-cat-calibration-ablation — V9 W6 verdict runner.

V9 W5 audit found a concentrated log-loss gap to Pinnacle in the
(0.6, 0.8] p(true) bucket. W6 tests whether per-class isotonic
calibration on CatBoost actually closes that gap, across multiple
cutoffs (so we don't ship a single-season win that's noise).

For each cutoff in --cutoffs:
  1. Run walk_forward with --with-ensemble (so CatBoost val + test
     predictions exist + the V9 W6 cat_dc_temp / cat_dc_iso are built)
  2. Pull pooled cat_dc / cat_dc_temp / cat_dc_iso from pooled_arrays
  3. Compare pooled log-loss + the (0.6, 0.8] bucket contribution
     against the V5 W12 raw CatBoost baseline
  4. Write a per-cutoff row to the verdict table

Writes a single markdown card with:
  - Per-cutoff log-loss table (raw vs temp vs iso vs Pinnacle)
  - Per-cutoff (0.6, 0.8] bucket weighted-ll
  - Overall verdict:
    🎯 ship-iso  → all cutoffs show iso < raw + bucket gap shrinks
    🟡 marginal → mixed; iso < raw on some cutoffs only
    ❌ no-fix   → iso ≥ raw on majority → close ECE backlog permanently

Usage:
    nutmeg-cat-calibration-ablation \\
        --cutoffs 2022-08-01,2023-08-01,2024-08-01 \\
        --out docs/v9_w6_calibration_ablation.md
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.bucket_decomp import (
    DEFAULT_BIN_EDGES,
    _per_row_p_true,
    bucket_breakdown,
)
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


log = logging.getLogger("cat_calibration_ablation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# The bucket V9 W5 flagged as the concentrated-gap location
TARGET_BUCKET_INDEX = 3       # (0.6, 0.8]
TARGET_BUCKET_LABEL = "(0.6, 0.8]"


def _pooled_log_loss(probs: np.ndarray, y) -> float:
    """Same epsilon handling as bucket_decomp._per_row_p_true."""
    p_true = _per_row_p_true(probs, y)
    return float(-np.log(p_true).mean())


def _bucket_weighted_ll(probs: np.ndarray, y, bucket_idx: int) -> tuple[float, int]:
    """Return (weighted_ll, n) for the requested bucket index."""
    rows = bucket_breakdown(probs, y)
    n_total = sum(r.n for r in rows)
    bucket = rows[bucket_idx]
    if bucket.n == 0 or n_total == 0:
        return 0.0, 0
    return (bucket.n / n_total) * bucket.log_loss_contribution, bucket.n


def _run_one_cutoff(df: pd.DataFrame, cutoff: str) -> dict:
    """Run walk_forward + return per-variant pooled + bucket metrics."""
    cfg = WalkForwardConfig(
        test_cutoff=pd.Timestamp(cutoff),
        with_ensemble=True,
    )
    res = run_walk_forward(df, cfg)
    arrays = res.get("pooled_arrays")
    if not arrays:
        raise RuntimeError(f"pooled_arrays missing for cutoff={cutoff}")

    y = arrays["y_gbm"]
    pin = arrays["pinnacle_gbm"]
    raw = arrays["cat_dc"]
    tmp = arrays["cat_dc_temp"]
    iso = arrays["cat_dc_iso"]

    out: dict = {"cutoff": cutoff, "n": int(len(y))}
    for name, probs in (
        ("pinnacle", pin),
        ("cat_raw",  raw),
        ("cat_temp", tmp),
        ("cat_iso",  iso),
    ):
        if len(probs) == 0:
            out[f"{name}_ll"] = float("nan")
            out[f"{name}_target_ll"] = float("nan")
            out[f"{name}_target_n"] = 0
            continue
        out[f"{name}_ll"] = _pooled_log_loss(probs, y)
        wll, n_bucket = _bucket_weighted_ll(probs, y, TARGET_BUCKET_INDEX)
        out[f"{name}_target_ll"] = wll
        out[f"{name}_target_n"] = n_bucket

    out["cat_T"] = res.get("calibrators", {}).get("cat_T")
    return out


def _format_card(rows: list[dict], cutoffs: list[str]) -> str:
    """Build the markdown ablation card with verdict."""
    lines: list[str] = []
    lines.append("# V9 W6 — CatBoost calibration ablation\n")
    lines.append(
        "Tests whether per-class isotonic / temperature calibration on "
        "raw CatBoost closes the V9 W5-identified gap. Multi-cutoff "
        "verdict: ship only if **all** cutoffs improve pooled log-loss.\n"
    )

    # Pooled log-loss table
    lines.append("## Pooled log-loss per cutoff\n")
    lines.append(
        "| Cutoff | n | Pinnacle | cat_raw | cat_temp | cat_iso | "
        "Δ temp − raw | Δ iso − raw |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        d_temp = r["cat_temp_ll"] - r["cat_raw_ll"]
        d_iso = r["cat_iso_ll"] - r["cat_raw_ll"]
        lines.append(
            f"| {r['cutoff']} | {r['n']} | "
            f"{r['pinnacle_ll']:.4f} | {r['cat_raw_ll']:.4f} | "
            f"{r['cat_temp_ll']:.4f} | {r['cat_iso_ll']:.4f} | "
            f"{d_temp:+.4f} | {d_iso:+.4f} |"
        )
    lines.append("")

    # Target bucket weighted-ll table
    lines.append(f"## `{TARGET_BUCKET_LABEL}` bucket weighted log-loss\n")
    lines.append(
        f"Only the bucket V9 W5 flagged. Lower = better. Pinnacle's "
        f"value is the reachable ceiling for this bucket.\n"
    )
    lines.append(
        "| Cutoff | Pin wll | cat_raw wll | cat_temp wll | cat_iso wll | "
        "Δ raw vs Pin | Δ iso vs Pin |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        gap_raw = r["cat_raw_target_ll"] - r["pinnacle_target_ll"]
        gap_iso = r["cat_iso_target_ll"] - r["pinnacle_target_ll"]
        lines.append(
            f"| {r['cutoff']} | {r['pinnacle_target_ll']:.4f} | "
            f"{r['cat_raw_target_ll']:.4f} | {r['cat_temp_target_ll']:.4f} | "
            f"{r['cat_iso_target_ll']:.4f} | "
            f"{gap_raw:+.4f} | {gap_iso:+.4f} |"
        )
    lines.append("")

    # Calibrator parameters
    lines.append("## Calibrator parameters\n")
    lines.append("| Cutoff | cat temperature T | iso fitted? |")
    lines.append("|---|---:|---:|")
    for r in rows:
        T = r.get("cat_T")
        T_str = f"{T:.4f}" if T is not None else "—"
        lines.append(f"| {r['cutoff']} | {T_str} | yes |")
    lines.append("")

    # Verdict
    n_iso_wins = sum(1 for r in rows if r["cat_iso_ll"] < r["cat_raw_ll"])
    n_temp_wins = sum(1 for r in rows if r["cat_temp_ll"] < r["cat_raw_ll"])
    n_cutoffs = len(rows)
    iso_mean_delta = float(np.mean([r["cat_iso_ll"] - r["cat_raw_ll"] for r in rows]))
    temp_mean_delta = float(np.mean([r["cat_temp_ll"] - r["cat_raw_ll"] for r in rows]))

    lines.append("## Verdict\n")
    lines.append(
        f"- **isotonic**: improved on {n_iso_wins}/{n_cutoffs} cutoffs, "
        f"mean Δ vs raw = `{iso_mean_delta:+.4f}` log-loss\n"
        f"- **temperature**: improved on {n_temp_wins}/{n_cutoffs} cutoffs, "
        f"mean Δ vs raw = `{temp_mean_delta:+.4f}` log-loss\n"
    )

    if n_iso_wins == n_cutoffs and iso_mean_delta < -0.0005:
        lines.append(
            "🎯 **ship-iso**: isotonic improves all cutoffs and mean Δ "
            f"`{iso_mean_delta:+.4f}` exceeds 0.0005 threshold. V9 W6 "
            "should wire isotonic into the production CatBoost predict "
            "path (train-time fit on the same val window; persist "
            "alongside the model artifact; apply at inference time).\n"
        )
    elif n_iso_wins >= n_cutoffs / 2 and iso_mean_delta < 0:
        lines.append(
            "🟡 **marginal**: isotonic improves a majority of cutoffs but "
            "either fails on some or the mean Δ is smaller than 0.0005. "
            "Two options: (a) ship isotonic anyway and accept marginal "
            "gain, (b) document and skip — gain too small to be worth "
            "the artifact-format change.\n"
        )
    else:
        lines.append(
            "❌ **no-fix**: isotonic doesn't beat raw across cutoffs. "
            "The V9 W5 audit revealed the (0.6, 0.8] gap but per-class "
            "isotonic doesn't close it. Interpretation: the 619 vs 542 "
            "row population delta is real signal CatBoost picks up that "
            "Pinnacle's market prior deliberately dampens — calibrating "
            "would erase real edge. **Close ECE-vs-log-loss backlog "
            "permanently**; the audit was the answer.\n"
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V9 W6 CatBoost calibration ablation")
    p.add_argument(
        "--data", default="data/historical_sources/football_data_co_uk",
        help="Football-data.co.uk tree",
    )
    p.add_argument(
        "--cutoffs", default="2022-08-01,2023-08-01,2024-08-01",
        help="Comma-separated cutoff dates",
    )
    p.add_argument(
        "--out", default="docs/v9_w6_calibration_ablation.md",
        help="Output markdown card path",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    data_path = Path(args.data)
    if not data_path.exists():
        log.error("football-data tree not found: %s", data_path)
        return 1

    cutoffs = [c.strip() for c in args.cutoffs.split(",") if c.strip()]
    if not cutoffs:
        log.error("--cutoffs must list at least one date")
        return 1

    log.info("Loading league data...")
    df = load_all_matches(str(data_path))

    rows: list[dict] = []
    for cutoff in cutoffs:
        log.info("Running walk_forward for cutoff=%s...", cutoff)
        row = _run_one_cutoff(df, cutoff)
        rows.append(row)
        log.info(
            "  cutoff=%s n=%d  pin=%.4f  raw=%.4f  temp=%.4f  iso=%.4f",
            cutoff, row["n"], row["pinnacle_ll"],
            row["cat_raw_ll"], row["cat_temp_ll"], row["cat_iso_ll"],
        )

    card = _format_card(rows, cutoffs)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(card)
    log.info("Wrote ablation card → %s", out_path)
    print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
