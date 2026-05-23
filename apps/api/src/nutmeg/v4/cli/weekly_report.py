"""nutmeg-weekly-report — bundle three observation-driven reports per week.

V7 W3. Closes V7 Track C: with W1 (odds in) + W2 (outcomes in) + this
W3 (reports out), the daily user flow is fully automated and the
V6 W8 lineup-aware ROI verdict can finally close on automated data.

Bundles three CLIs into one call:

  1. `nutmeg-roi-report`           → docs/weekly/<YYYY-Www>-roi.md
  2. `nutmeg-ab-report --weeks N`  → docs/weekly/<YYYY-Www>-ab.md
  3. `nutmeg-live-vs-backtest`     → docs/weekly/<YYYY-Www>-gap.md
       (skipped when --backtest-cutoff is not provided)

Same exit-code convention as `nutmeg-live-vs-backtest`:
  0 — all reports ran, gap within tolerance (or no gap check)
  1 — input/setup error (missing DB etc.)
  2 — gap exceeds tolerance — cron should alert

Designed for the user's local crontab (the observation DB is local).
See `docs/v7_w3_weekly_report.md` for a sample weekly crontab entry.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Optional

from nutmeg.v4.cli import ab_report as ab_report_cli
from nutmeg.v4.cli import live_vs_backtest as live_vs_backtest_cli
from nutmeg.v4.cli import roi_report as roi_report_cli


log = logging.getLogger("weekly_report")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _week_tag(d: dt.date | None = None) -> str:
    """ISO week tag: 'YYYY-Www' (matches V5 W10 weekly-bench card naming)."""
    if d is None:
        d = dt.date.today()
    iso = d.isocalendar()  # (year, week, weekday)
    return f"{iso[0]}-W{iso[1]:02d}"


def run_weekly_report(
    *,
    db: str,
    out_dir: Path,
    weeks: int,
    backtest_cutoff: Optional[str],
    backtest_data: Optional[str],
    snapshot_phase: Optional[str],
    week_tag: Optional[str] = None,
) -> tuple[int, dict[str, Path | None]]:
    """Run all three reports; return (exit_code, file_paths_by_kind).

    Exit code follows the live-vs-backtest convention so a single
    cron alert hook works for both this wrapper and the underlying
    CLI. If `backtest_cutoff` is None, the gap report is skipped
    (returns None in the paths dict).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = week_tag or _week_tag()

    roi_path = out_dir / f"{tag}-roi.md"
    ab_path = out_dir / f"{tag}-ab.md"
    gap_path = out_dir / f"{tag}-gap.md" if backtest_cutoff else None

    # ROI report — exit 1 only when DB missing (filesystem-level error)
    roi_args = ["--db", db, "--out", str(roi_path), "--quiet"]
    rc_roi = roi_report_cli.main(roi_args)
    if rc_roi != 0:
        log.error("nutmeg-roi-report failed with exit code %d", rc_roi)
        return rc_roi, {"roi": None, "ab": None, "gap": None}
    log.info("Wrote ROI report → %s", roi_path)

    # A/B report — same exit-code semantics (1 = DB missing; otherwise 0)
    ab_args = ["--db", db, "--weeks", str(weeks), "--out", str(ab_path)]
    rc_ab = ab_report_cli.main(ab_args)
    if rc_ab != 0:
        log.error("nutmeg-ab-report failed with exit code %d", rc_ab)
        return rc_ab, {"roi": roi_path, "ab": None, "gap": None}
    log.info("Wrote A/B report → %s", ab_path)

    # Gap report (optional) — exit 2 when over tolerance; we propagate
    rc_gap = 0
    if gap_path is not None:
        gap_args = ["--db", db, "--weeks", str(weeks),
                    "--backtest-cutoff", backtest_cutoff, "--out", str(gap_path)]
        if backtest_data:
            gap_args.extend(["--data", backtest_data])
        if snapshot_phase:
            gap_args.extend(["--snapshot-phase", snapshot_phase])
        rc_gap = live_vs_backtest_cli.main(gap_args)
        if rc_gap == 2:
            log.warning("Live vs backtest gap EXCEEDS tolerance — alert!")
        elif rc_gap != 0:
            log.error("nutmeg-live-vs-backtest failed with exit code %d", rc_gap)
            return rc_gap, {"roi": roi_path, "ab": ab_path, "gap": None}
        else:
            log.info("Wrote gap report → %s", gap_path)

    return rc_gap, {"roi": roi_path, "ab": ab_path, "gap": gap_path}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V7 W3 — bundled weekly observation reports"
    )
    p.add_argument("--db", required=True, help="Local observation DB path")
    p.add_argument(
        "--out-dir", type=Path, default=Path("docs/weekly"),
        help="Where to drop the three markdown cards (default docs/weekly/)",
    )
    p.add_argument(
        "--weeks", type=int, default=4,
        help="A/B + live-vs-backtest window (weeks). Default 4 matches V6 W8 cadence.",
    )
    p.add_argument(
        "--backtest-cutoff", default=None,
        help="YYYY-MM-DD; when present, gap report runs. When absent, gap step is skipped.",
    )
    p.add_argument(
        "--backtest-data",
        default=None,
        help="Path to historical data tree for the gap report (default lives in live_vs_backtest CLI).",
    )
    p.add_argument(
        "--snapshot-phase",
        choices=("pre_close", "closing", "post_close"),
        default=None,
        help="Restrict live slice to one snapshot phase (passed through to live-vs-backtest).",
    )
    p.add_argument(
        "--week-tag", default=None,
        help="Override the YYYY-Www tag (default = ISO week of today's UTC date).",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    if not Path(args.db).exists():
        log.error("observation DB not found: %s", args.db)
        return 1

    exit_code, paths = run_weekly_report(
        db=args.db,
        out_dir=args.out_dir,
        weeks=args.weeks,
        backtest_cutoff=args.backtest_cutoff,
        backtest_data=args.backtest_data,
        snapshot_phase=args.snapshot_phase,
        week_tag=args.week_tag,
    )

    # Final one-line summary even in --quiet mode (the cron log truncates,
    # this is the most important line)
    wrote = [str(v) for v in paths.values() if v is not None]
    print(
        f"weekly-report: wrote {len(wrote)} cards "
        f"({', '.join(Path(p).name for p in wrote)}); exit={exit_code}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
