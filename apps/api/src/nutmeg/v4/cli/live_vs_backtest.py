"""nutmeg-live-vs-backtest — compare live ROI to a backtest reference.

Usage:

    nutmeg-live-vs-backtest --db data/v4_observation.db --weeks 4 \\
        --backtest-cutoff 2024-08-01 --out docs/weekly/2025-W18.md

    # post-v9 P1#19: compare production lineup-aware live ROI directly
    # against the historical ROI replay DB produced by nutmeg-roi-backtest.
    nutmeg-live-vs-backtest --db data/v4_observation.db --weeks 4 \\
        --live-model-arm lineup_aware \\
        --roi-backtest-db data/v4_observation_backtest.db \\
        --roi-backtest-arm lineup_aware

Exits:
    0  — gap within ±5 pp tolerance (or no backtest reference)
    2  — gap exceeds tolerance (cron should alert)
    1  — input / data error
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from nutmeg.v4.data.ingest import load_all_matches
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward
from nutmeg.v4.observation.live_vs_backtest import format_report
from nutmeg.v4.observation.live_vs_backtest import run as live_vs_backtest_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 W8 live vs backtest comparison")
    parser.add_argument("--db", required=True, help="Path to observation SQLite DB")
    parser.add_argument("--weeks", type=int, default=4,
                        help="How many weeks of live settlements to include (default 4)")
    parser.add_argument(
        "--backtest-cutoff",
        default=None,
        help="YYYY-MM-DD test cutoff for the backtest. If omitted, no backtest "
        "comparison is performed and only the live slice is reported.",
    )
    parser.add_argument(
        "--data",
        default="data/historical_sources/football_data_co_uk",
        help="Path to historical data tree (used only when --backtest-cutoff given)",
    )
    parser.add_argument(
        "--snapshot-phase",
        choices=("pre_close", "closing", "post_close"),
        default=None,
        help="If set, restrict live slice to sessions of this phase only.",
    )
    parser.add_argument(
        "--live-model-arm",
        choices=("all", "lineup_aware", "lineup_free"),
        default="all",
        help="Restrict the live observation slice by artifact arm. P1#19 uses lineup_aware.",
    )
    parser.add_argument(
        "--roi-backtest-db",
        default=None,
        help="Observation DB produced by nutmeg-roi-backtest. When set, this "
        "is the reference instead of a walk-forward --backtest-cutoff run.",
    )
    parser.add_argument(
        "--roi-backtest-arm",
        choices=("lineup_aware", "lineup_free", "default"),
        default="lineup_aware",
        help="Model arm to slice from --roi-backtest-db.",
    )
    parser.add_argument("--out", default=None, help="Output markdown file (default stdout)")
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"ERROR: observation DB not found: {args.db}", file=sys.stderr)
        return 1
    if args.roi_backtest_db and args.backtest_cutoff:
        print(
            "ERROR: choose exactly one backtest reference: --roi-backtest-db "
            "or --backtest-cutoff, not both",
            file=sys.stderr,
        )
        return 1
    if args.roi_backtest_db and not Path(args.roi_backtest_db).exists():
        print(f"ERROR: ROI backtest DB not found: {args.roi_backtest_db}", file=sys.stderr)
        return 1

    backtest_pooled = None
    if args.backtest_cutoff:
        try:
            df = load_all_matches(args.data)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: could not load historical data from {args.data}: {exc}",
                  file=sys.stderr)
            return 1
        import pandas as pd  # type: ignore[import-untyped]
        cfg = WalkForwardConfig(test_cutoff=pd.Timestamp(args.backtest_cutoff))
        wf = run_walk_forward(df, cfg)
        backtest_pooled = wf.get("pooled")

    report = live_vs_backtest_run(
        args.db,
        weeks=args.weeks,
        backtest_pooled=backtest_pooled,
        backtest_cutoff=args.backtest_cutoff,
        snapshot_phase=args.snapshot_phase,
        live_model_arm=args.live_model_arm,
        roi_backtest_db=args.roi_backtest_db,
        roi_backtest_arm=args.roi_backtest_arm,
    )
    as_of = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    card = format_report(report, weeks=args.weeks, as_of_iso=as_of)

    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(card)
        print(f"Wrote {out_p}", file=sys.stderr)
    else:
        print(card)

    return 2 if report.over_tolerance else 0


if __name__ == "__main__":
    sys.exit(main())
