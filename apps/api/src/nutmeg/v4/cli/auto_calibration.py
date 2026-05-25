"""nutmeg-auto-calibration — V10 W2 Day 2.

Run Layer A's drift-correction proposal against the observation DB.
Emits a markdown verdict card + (unless --dry-run) records to the
calibration_journal table.

Designed to be cron-driven from launchd (V10 W2 Day 4 ships the job),
but also runs interactively.

Exit codes:
  0  success: proposal generated (regardless of ship-gate verdict)
  1  setup/input error (DB missing, journal write failed)
  2  ship-gate PASSED → real T change recommended; caller can choose
     to deploy via --apply on the next run

Examples:

    # Dry-run (just print verdict; default — no journal write):
    nutmeg-auto-calibration --db data/v4_observation.db

    # Record this proposal in the journal:
    nutmeg-auto-calibration --db data/v4_observation.db --apply

    # Custom windows (longer lookback for stable models, smaller holdout):
    nutmeg-auto-calibration --db data/v4_observation.db \\
        --lookback-weeks 12 --holdout-weeks 2 --min-samples 50

    # Write a report alongside the journal entry:
    nutmeg-auto-calibration --db data/v4_observation.db --apply \\
        --out docs/weekly/auto_calibration_2026-W22.md

Notes on production wiring (per V10 W2 Day 3 plan):
  - This CLI only PROPOSES + RECORDS. The artifact-side deploy file
    (`data/v4_model_*/live_T_correction.json`) is written by a
    separate `--deploy-artifact` flag that ships on Day 3.
  - The serving layer (`predict_lambdas`) reads the artifact file at
    request time; this CLI never restarts the server.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from nutmeg.v4.observation.auto_calibration import (
    DEFAULT_BOOTSTRAP_N,
    DEFAULT_HOLDOUT_WEEKS,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_MAX_P_VALUE,
    DEFAULT_MIN_LOG_LOSS_GAIN,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD,
    CorrectionEvaluation,
    DriftProposal,
    evaluate_active_correction,
    propose_drift_correction,
    record_calibration_journal,
    remove_artifact_correction,
    write_artifact_correction,
)


log = logging.getLogger("nutmeg-auto-calibration")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def render_markdown(proposal: DriftProposal, db_path: str) -> str:
    """Format a DriftProposal as a markdown verdict card."""
    verdict = "✅ SHIP" if proposal.should_apply else "🛑 HOLD"
    lines = [
        f"# Auto-T Calibration Drift Report",
        "",
        f"_Generated {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}_",
        "",
        f"**Source DB**: `{db_path}`",
        "",
        f"## Verdict: {verdict}",
        "",
        f"- **Current T**: `{proposal.current_T:.4f}`",
        f"- **Proposed T**: `{proposal.proposed_T:.4f}`",
        f"- **Reason**: {proposal.reason}",
        "",
        "## Sample sizes",
        "",
        f"- Train: **{proposal.n_train}** pairs · "
        f"window `{proposal.train_window[0]}` → `{proposal.train_window[1]}`",
        f"- Holdout: **{proposal.n_holdout}** pairs · "
        f"window `{proposal.holdout_window[0]}` → `{proposal.holdout_window[1]}`",
        "",
        "## Validation metrics",
        "",
    ]
    if proposal.n_holdout > 0 and proposal.log_loss_after == proposal.log_loss_after:  # not NaN
        lines.extend([
            f"| Metric | Value |",
            f"|---|---:|",
            f"| log-loss before (T={proposal.current_T:.3f}) | {proposal.log_loss_before:.4f} |",
            f"| log-loss after  (T={proposal.proposed_T:.3f}) | {proposal.log_loss_after:.4f} |",
            f"| **Δ log-loss** (positive = improvement) | **{proposal.log_loss_delta:+.4f}** |",
            f"| bootstrap p-value | {proposal.p_value:.4f} |",
            "",
        ])
    else:
        lines.append("_No holdout evaluation — see reason above._\n")

    lines.extend([
        "## Ship gate (both must pass)",
        "",
        f"| Check | Threshold | Actual | Pass |",
        f"|---|---:|---:|:---:|",
    ])
    delta_ok = (
        proposal.log_loss_delta == proposal.log_loss_delta  # not NaN
        and proposal.log_loss_delta >= DEFAULT_MIN_LOG_LOSS_GAIN
    )
    p_ok = proposal.p_value == proposal.p_value and proposal.p_value <= DEFAULT_MAX_P_VALUE
    delta_str = "n/a" if proposal.log_loss_delta != proposal.log_loss_delta else f"{proposal.log_loss_delta:+.4f}"
    p_str = "n/a" if proposal.p_value != proposal.p_value else f"{proposal.p_value:.4f}"
    lines.extend([
        f"| log-loss Δ ≥ {DEFAULT_MIN_LOG_LOSS_GAIN} | ≥ {DEFAULT_MIN_LOG_LOSS_GAIN} | {delta_str} | {'✓' if delta_ok else '✗'} |",
        f"| bootstrap p ≤ {DEFAULT_MAX_P_VALUE} | ≤ {DEFAULT_MAX_P_VALUE} | {p_str} | {'✓' if p_ok else '✗'} |",
        "",
        "## Next steps",
        "",
    ])
    if proposal.should_apply:
        lines.extend([
            "Run with `--apply` to record this as a deploy decision in the journal.",
            "Day 3 will wire the artifact-side `live_T_correction.json` writer.",
        ])
    else:
        lines.extend([
            "No change. Re-check next week when more live data has accumulated.",
            "The journal entry (if --apply was passed) preserves the audit trail.",
        ])
    lines.append("")
    return "\n".join(lines)


def render_rollback_markdown(
    eval_: CorrectionEvaluation,
    db_path: str,
    *,
    rollback_executed: bool,
) -> str:
    """V10 W2 Day 4 — markdown card for auto-rollback verdicts."""
    verdict = "🔄 AUTO-ROLLBACK" if rollback_executed else "✅ KEPT"
    lines = [
        "# Auto-T Calibration Rollback Check",
        "",
        f"_Generated {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}_",
        "",
        f"**Source DB**: `{db_path}`",
        "",
        f"## Verdict: {verdict}",
        "",
        f"- **Deployed T**: `{eval_.deployed_T:.4f}`",
        f"- **Eval window**: `{eval_.eval_window[0]}` → `{eval_.eval_window[1]}`",
        f"- **Pairs evaluated**: **{eval_.n_pairs}**",
        f"- **Reason**: {eval_.reason}",
        "",
        "## Post-deploy log-loss",
        "",
    ]
    if eval_.n_pairs > 0 and eval_.log_loss_deployed == eval_.log_loss_deployed:
        lines.extend([
            "| Strategy | Log-loss |",
            "|---|---:|",
            f"| Deployed T = {eval_.deployed_T:.3f} | {eval_.log_loss_deployed:.4f} |",
            f"| Identity (T = 1.000) | {eval_.log_loss_identity:.4f} |",
            f"| **Δ (deployed − identity)** | **{eval_.delta:+.4f}** |",
            "",
            "Positive Δ → identity beats deployed → correction was hurting.",
            "",
        ])
    else:
        lines.append("_No post-deploy data available — keeping current state._\n")

    lines.append("## Action")
    lines.append("")
    if rollback_executed:
        lines.extend([
            "Deployed correction REMOVED (`live_T_correction.json` deleted). "
            "Serving layer reverts to identity (T=1.0) on next request.",
            "",
            "Next: weekly cron will re-propose a new T if drift persists.",
        ])
    else:
        lines.extend([
            "Deployed correction RETAINED. No change to serving layer.",
            "",
            "Next: the propose flow runs to potentially recommend a NEW T.",
        ])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V10 W2 — propose post-hoc T calibration drift correction"
    )
    p.add_argument(
        "--db",
        default="data/v4_observation.db",
        help="Observation DB path (default data/v4_observation.db)",
    )
    p.add_argument(
        "--lookback-weeks", type=int, default=DEFAULT_LOOKBACK_WEEKS,
        help=f"Past N weeks of live data (default {DEFAULT_LOOKBACK_WEEKS})",
    )
    p.add_argument(
        "--holdout-weeks", type=int, default=DEFAULT_HOLDOUT_WEEKS,
        help=f"Most recent K weeks held out for validation (default {DEFAULT_HOLDOUT_WEEKS})",
    )
    p.add_argument(
        "--min-samples", type=int, default=DEFAULT_MIN_SAMPLES,
        help=f"Minimum train pairs to attempt proposal (default {DEFAULT_MIN_SAMPLES})",
    )
    p.add_argument(
        "--min-log-loss-gain", type=float, default=DEFAULT_MIN_LOG_LOSS_GAIN,
        help=f"Holdout log-loss improvement threshold (default {DEFAULT_MIN_LOG_LOSS_GAIN})",
    )
    p.add_argument(
        "--max-p-value", type=float, default=DEFAULT_MAX_P_VALUE,
        help=f"Bootstrap p-value threshold (default {DEFAULT_MAX_P_VALUE})",
    )
    p.add_argument(
        "--current-T", type=float, default=1.0,
        help="Current post-hoc T (default 1.0 = identity)",
    )
    p.add_argument(
        "--n-bootstrap", type=int, default=DEFAULT_BOOTSTRAP_N,
        help=f"Bootstrap resamples (default {DEFAULT_BOOTSTRAP_N})",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="Record this proposal in calibration_journal (default: dry-run, "
             "no journal write).",
    )
    p.add_argument(
        "--action", default="propose",
        choices=("propose", "deploy", "rollback"),
        help="Journal action tag (only used when --apply is set). "
             "Default 'propose'. Pass --deploy-artifact to also write the "
             "artifact-side `live_T_correction.json` (only effective when "
             "--apply is set, --action=deploy, and ship gate passes).",
    )
    p.add_argument(
        "--deploy-artifact", default=None,
        help="V10 W2 Day 3 — when ship gate passes, write "
             "`<dir>/live_T_correction.json` so the serving layer picks "
             "up the new T on the next request. Requires --apply. "
             "When --action=rollback (gate not required), DELETES the "
             "existing correction file (auto-rollback).",
    )
    p.add_argument(
        "--auto-rollback", action="store_true",
        help="V10 W2 Day 4 — before proposing, validate the currently-"
             "deployed correction (if any). If post-deploy data shows "
             "identity (T=1.0) beats deployed T by more than "
             "--rollback-threshold log-loss, automatically rollback "
             "(journal + delete artifact file) and SHORT-CIRCUIT the "
             "propose flow. Requires --apply + --deploy-artifact.",
    )
    p.add_argument(
        "--rollback-threshold", type=float,
        default=DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD,
        help=f"Rollback if deployed log-loss > identity by this much "
             f"on post-deploy data (default "
             f"{DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD}).",
    )
    p.add_argument(
        "--rollback-lookback-weeks", type=int, default=2,
        help="How far back to look for post-deploy validation data "
             "(default 2). The effective cutoff is "
             "max(deploy_time, now - lookback).",
    )
    p.add_argument(
        "--out", default="-",
        help="Markdown report path; '-' for stdout (default).",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("observation DB not found: %s", db_path)
        return 1

    # V10 W2 Day 4 — pre-flight auto-rollback check.
    # When --auto-rollback is set and there's an active correction whose
    # post-deploy log-loss is materially worse than identity, we revert
    # FIRST + short-circuit the propose flow. This is the safety net
    # that prevents one bad deploy from compounding across weeks.
    if args.auto_rollback:
        if not args.apply or not args.deploy_artifact:
            log.warning(
                "--auto-rollback requires --apply + --deploy-artifact; "
                "skipping rollback check.",
            )
        else:
            eval_ = evaluate_active_correction(
                db_path, args.deploy_artifact,
                lookback_weeks=args.rollback_lookback_weeks,
                rollback_threshold=args.rollback_threshold,
            )
            log.info("auto-rollback check: %s", eval_.reason)
            if eval_.should_rollback:
                # Synthesize a DriftProposal that captures the rollback
                # context, then journal + delete artifact.
                rollback_prop = DriftProposal(
                    proposed_T=1.0,  # rollback target
                    current_T=eval_.deployed_T,
                    log_loss_before=eval_.log_loss_deployed,
                    log_loss_after=eval_.log_loss_identity,
                    log_loss_delta=eval_.delta,
                    p_value=float("nan"),  # no bootstrap on rollback path
                    n_train=0,
                    n_holdout=eval_.n_pairs,
                    holdout_window=eval_.eval_window,
                    should_apply=True,
                    reason=eval_.reason,
                )
                try:
                    row_id = record_calibration_journal(
                        db_path, rollback_prop, action="rollback",
                    )
                    log.info("Recorded auto-rollback journal row #%d", row_id)
                except Exception as exc:  # noqa: BLE001
                    log.error("rollback journal write failed: %s", exc)
                    return 1
                removed = remove_artifact_correction(args.deploy_artifact)
                if removed:
                    log.warning(
                        "AUTO-ROLLBACK: removed live_T_correction.json from %s",
                        args.deploy_artifact,
                    )
                else:
                    log.info(
                        "rollback no-op: no live_T_correction.json in %s",
                        args.deploy_artifact,
                    )
                # Write the rollback report + short-circuit
                report = render_rollback_markdown(
                    eval_, str(db_path), rollback_executed=True,
                )
                if args.out == "-":
                    print(report)
                else:
                    out_path = Path(args.out)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(report)
                    log.info("wrote %d bytes → %s", len(report), out_path)
                return 0
            # Not triggered → fall through to normal propose flow.
            # Use the deployed T as baseline for propose's bootstrap
            # p-value (otherwise we'd compare against T=1.0 even though
            # serving applies the deployed T). Only override when the
            # user kept --current-T at its default 1.0.
            if eval_.correction is not None and args.current_T == 1.0:
                args.current_T = eval_.deployed_T
                log.info(
                    "auto-rollback retained: using deployed T=%.4f as "
                    "baseline for propose", args.current_T,
                )

    log.info(
        "Proposing drift correction: lookback=%dw, holdout=%dw, min_samples=%d, current_T=%.3f",
        args.lookback_weeks, args.holdout_weeks, args.min_samples, args.current_T,
    )
    proposal = propose_drift_correction(
        db_path,
        lookback_weeks=args.lookback_weeks,
        holdout_weeks=args.holdout_weeks,
        min_samples=args.min_samples,
        min_log_loss_gain=args.min_log_loss_gain,
        max_p_value=args.max_p_value,
        current_T=args.current_T,
        n_bootstrap=args.n_bootstrap,
    )

    if args.apply:
        try:
            row_id = record_calibration_journal(db_path, proposal, action=args.action)
            log.info(
                "Recorded calibration_journal row #%d (action=%s, decision=%d)",
                row_id, args.action, 1 if proposal.should_apply else 0,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("journal write failed: %s", exc)
            return 1
    else:
        log.info("[dry-run] not writing to calibration_journal (pass --apply to record)")

    # V10 W2 Day 3 — artifact-side deploy / rollback
    if args.deploy_artifact:
        if not args.apply:
            log.warning(
                "--deploy-artifact without --apply is a no-op (won't write); "
                "pass --apply to actually deploy.",
            )
        elif args.action == "rollback":
            # Rollback: delete the correction file regardless of gate verdict.
            removed = remove_artifact_correction(args.deploy_artifact)
            if removed:
                log.info("rolled back: removed live_T_correction.json from %s",
                         args.deploy_artifact)
            else:
                log.info("rollback no-op: no live_T_correction.json in %s",
                         args.deploy_artifact)
        elif args.action == "deploy":
            if not proposal.should_apply:
                log.warning(
                    "--deploy-artifact ignored: ship gate did NOT pass "
                    "(reason: %s)", proposal.reason,
                )
            else:
                try:
                    path = write_artifact_correction(args.deploy_artifact, proposal)
                    log.info("deployed: wrote %s (T=%.4f)", path, proposal.proposed_T)
                except Exception as exc:  # noqa: BLE001
                    log.error("artifact write failed: %s", exc)
                    return 1
        else:
            # action == 'propose'
            log.warning(
                "--deploy-artifact ignored: --action=%s requires "
                "--action=deploy or --action=rollback", args.action,
            )

    report = render_markdown(proposal, str(db_path))
    if args.out == "-":
        print(report)
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        log.info("wrote %d bytes → %s", len(report), out_path)

    # Exit code 2 if ship gate PASSED but not yet deployed (caller can
    # use this to know "run --apply --action=deploy next").
    if proposal.should_apply and args.action != "deploy":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
