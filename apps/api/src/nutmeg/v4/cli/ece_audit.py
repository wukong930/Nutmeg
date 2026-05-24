"""nutmeg-ece-audit — per-bucket Brier + log-loss decomposition.

V9 W5 — investigates the V5 W12 mystery: CatBoost ECE (0.0120) is
slightly BETTER than Pinnacle (0.0123), yet log-loss is 0.0056 worse.
Three retrospectives mentioned this; none investigated. W5 did the
audit + writes the verdict.

**post-v9 P1#9**: added `--cutoffs A,B,C` for multi-cutoff verdict.
The V9 retrospective self-criticized W5's single-cutoff verdict as
over-promising — the (0.6, 0.8] bucket pattern was non-stationary
across seasons. The multi-cutoff path requires the same bucket to
dominate on ≥ 2/3 cutoffs before flagging as fixable.

Runs walk_forward (with_ensemble=True so CatBoost predictions land in
the pooled arrays), pulls Pinnacle vs CatBoost vs labels, runs the
appropriate audit card (single or multi-cutoff), writes markdown.

Usage:

    # Multi-cutoff (recommended)
    nutmeg-ece-audit --cutoffs 2022-08-01,2023-08-01,2024-08-01 \\
        --out docs/ece_audit_multi.md

    # Single cutoff (V9 W5 mode; emits a "consider multi-cutoff" hint)
    nutmeg-ece-audit --cutoff 2024-08-01 --out docs/v9_w5_ece_audit.md

The verdict reports either:
  - 🎯 stable concentrated bucket → calibration ablation candidate
  - 🟡 same bin recurs but Δ too small → low-priority structural
  - ❌ non-stationary OR uniform → structural; close investigation
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.bucket_decomp import (
    format_audit_card,
    format_multi_cutoff_audit_card,
)
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


log = logging.getLogger("ece_audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _run_one(df, cutoff: str) -> dict | None:
    cfg = WalkForwardConfig(
        test_cutoff=pd.Timestamp(cutoff),
        with_ensemble=True,
    )
    result = run_walk_forward(df, cfg)
    arrays = result.get("pooled_arrays")
    if not arrays:
        log.error("pooled_arrays missing for cutoff=%s", cutoff)
        return None
    y = arrays["y_gbm"]
    pin = arrays["pinnacle_gbm"]
    cat = arrays["cat_dc"]
    if len(y) == 0:
        log.error("0 GBM-aligned rows for cutoff=%s", cutoff)
        return None
    if len(cat) == 0:
        log.error("CatBoost predictions empty for cutoff=%s", cutoff)
        return None
    return {"cutoff": cutoff, "probs_a": pin, "probs_b": cat, "y": y}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V9 W5 + P1#9 ECE-vs-log-loss audit")
    p.add_argument(
        "--data", default="data/historical_sources/football_data_co_uk",
        help="Football-data.co.uk tree",
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--cutoff",
        help="Single test cutoff (YYYY-MM-DD). V9 W5 default 2024-08-01. "
             "Single-cutoff verdicts can mislead — prefer --cutoffs.",
    )
    grp.add_argument(
        "--cutoffs",
        help="Comma-separated list of cutoffs for multi-cutoff verdict "
             "(post-v9 P1#9). Recommended for investigations.",
    )
    p.add_argument(
        "--out", default="docs/ece_audit.md",
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

    log.info("Loading league data...")
    df = load_all_matches(str(data_path))

    # Determine mode
    if args.cutoffs:
        cutoffs = [c.strip() for c in args.cutoffs.split(",") if c.strip()]
        if len(cutoffs) < 2:
            log.error("--cutoffs requires ≥ 2 dates; use --cutoff for single")
            return 1
        log.info("Multi-cutoff mode: %d cutoffs", len(cutoffs))
        per_cutoff: list[dict] = []
        for cutoff in cutoffs:
            log.info("Running walk_forward for cutoff=%s...", cutoff)
            entry = _run_one(df, cutoff)
            if entry is None:
                return 1
            per_cutoff.append(entry)
        card = format_multi_cutoff_audit_card("Pinnacle", "CatBoost", per_cutoff)
    else:
        # Single-cutoff (default 2024-08-01 to preserve V9 W5 behavior)
        cutoff = args.cutoff or "2024-08-01"
        log.info("Single-cutoff mode: %s "
                 "(post-v9 P1#9 recommends --cutoffs for investigations)", cutoff)
        entry = _run_one(df, cutoff)
        if entry is None:
            return 1
        card = format_audit_card(
            "Pinnacle", entry["probs_a"],
            "CatBoost", entry["probs_b"],
            entry["y"],
            test_label=f"cutoff={cutoff} (n={len(entry['y'])})",
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(card)
    log.info("Wrote audit card → %s", out_path)
    print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
