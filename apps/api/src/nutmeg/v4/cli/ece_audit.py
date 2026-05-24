"""nutmeg-ece-audit — per-bucket Brier + log-loss decomposition.

V9 W5 — investigates the V5 W12 mystery: CatBoost ECE (0.0120) is
slightly BETTER than Pinnacle (0.0123), yet log-loss is 0.0056 worse.
Three retrospectives mentioned this; none investigated. W5 does the
audit + writes the verdict.

Runs walk_forward (with_ensemble=True so CatBoost predictions land in
the pooled arrays), pulls Pinnacle vs CatBoost vs the labels, runs
`bucket_decomp.format_audit_card`, writes a markdown card.

Usage:

    nutmeg-ece-audit --cutoff 2024-08-01 --out docs/v9_w5_ece_audit.md

The audit reports either:
  - 🎯 a concentrated bucket → V9 W6 candidate fix
  - ❌ uniform spread → structural gap; remove from backlog
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.bucket_decomp import format_audit_card
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


log = logging.getLogger("ece_audit")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V9 W5 ECE-vs-log-loss audit")
    p.add_argument(
        "--data", default="data/historical_sources/football_data_co_uk",
        help="Football-data.co.uk tree",
    )
    p.add_argument(
        "--cutoff", default="2024-08-01",
        help="Test cutoff (YYYY-MM-DD); the V5 W12 default V4 baseline cutoff",
    )
    p.add_argument(
        "--out", default="docs/v9_w5_ece_audit.md",
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

    log.info("Loading league data + running walk_forward (this takes ~30-60s)...")
    df = load_all_matches(str(data_path))
    cfg = WalkForwardConfig(
        test_cutoff=pd.Timestamp(args.cutoff),
        with_ensemble=True,  # need CatBoost predictions in the pool
    )
    result = run_walk_forward(df, cfg)

    arrays = result.get("pooled_arrays")
    if not arrays:
        log.error("pooled_arrays missing; walk_forward didn't return them")
        return 1

    pin = arrays["pinnacle_gbm"]
    cat = arrays["cat_dc"]
    y = arrays["y_gbm"]

    if len(y) == 0:
        log.error("0 GBM-aligned rows in test horizon; check cutoff")
        return 1
    if len(cat) == 0:
        log.error("CatBoost predictions empty; --with-ensemble required?")
        return 1

    log.info(
        "Computing per-bucket decomposition on %d GBM-aligned test rows...",
        len(y),
    )
    card = format_audit_card(
        "Pinnacle", pin,
        "CatBoost", cat,
        y,
        test_label=f"cutoff={args.cutoff} (n={len(y)})",
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(card)
    log.info("Wrote ECE audit card → %s", out_path)
    print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
