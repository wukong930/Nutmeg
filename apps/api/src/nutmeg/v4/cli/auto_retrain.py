"""nutmeg-auto-retrain — Layer B propose / deploy / rollback CLI.

V11 backlog #4. Mirror of nutmeg-auto-calibration (Layer A).

Usage:

    # Dry-run propose (default): journal-only; no live artifact change
    nutmeg-auto-retrain --db data/v4_observation.db

    # Persist the journal entry (still doesn't ship)
    nutmeg-auto-retrain --db data/v4_observation.db --apply

    # Deploy a previously-trained candidate
    nutmeg-auto-retrain --db data/v4_observation.db \\
        --apply --action deploy \\
        --candidate data/v4_model_layer_b/v_2026-Q3 \\
        --artifact-base data/v4_model

    # Rollback (delete pointer + reset Layer A's T)
    nutmeg-auto-retrain --db data/v4_observation.db \\
        --apply --action rollback \\
        --artifact-base data/v4_model

    # Mark the verdict in a markdown report
    nutmeg-auto-retrain --out docs/quarterly/retrain_2026-Q3.md

This is the wrapper / orchestrator. The actual model retraining
happens by invoking `nutmeg-train` separately — Layer B does not
re-implement the training pipeline. The CLI surfaces the ship-gate
verdict + artifact-pointer swap; the user (or a wrapper script)
runs the training step beforehand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from nutmeg.v4.observation.auto_retrain import (
    DEFAULT_MAX_P_VALUE,
    DEFAULT_MIN_HOLDOUT_MATCHES,
    DEFAULT_MIN_LOG_LOSS_GAIN,
    DEFAULT_MIN_TRAIN_MATCHES,
    DEFAULT_ROI_TOLERANCE_PP,
    DEFAULT_ROLLBACK_LOOKBACK_WEEKS,
    LAYER_A_CORRECTION_FILENAME,
    LIVE_ARTIFACT_POINTER_FILENAME,
    RetrainProposal,
    current_quarter_version,
    ensure_retrain_journal,
    evaluate_ship_gate,
    fetch_latest_journal_entry,
    load_artifact_pointer,
    record_retrain_journal,
    remove_artifact_pointer,
    remove_layer_a_correction,
    resolve_effective_artifact_path,
    write_artifact_pointer,
)


log = logging.getLogger(__name__)


VALID_ACTIONS = ("propose", "deploy", "rollback")


# ---------- Report rendering ----------

def render_proposal_markdown(prop: RetrainProposal) -> str:
    """Produce the human-readable quarterly retrain card."""
    lines: list[str] = []
    lines.append(f"# Layer B Quarterly Retrain — {prop.artifact_version}\n")
    lines.append(
        f"_Generated {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}_\n"
    )
    lines.append("## Verdict")
    if prop.decision:
        lines.append(f"🟢 **SHIP** — {prop.reason}")
    else:
        lines.append(f"🔴 **HOLD** — {prop.reason}")
    lines.append("")
    lines.append("## Numbers\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Train window           | {prop.train_window[0]} → {prop.train_window[1]} |")
    lines.append(f"| Holdout window         | {prop.holdout_window[0]} → {prop.holdout_window[1]} |")
    lines.append(f"| n_train                | {prop.n_train:,} |")
    lines.append(f"| n_holdout              | {prop.n_holdout:,} |")
    lines.append(f"| log_loss (production)  | {prop.log_loss_before:.4f} |")
    lines.append(f"| log_loss (candidate)   | {prop.log_loss_after:.4f} |")
    lines.append(f"| Δ (before − after)     | {prop.log_loss_delta:+.4f} |")
    lines.append(f"| Bootstrap p-value      | {prop.p_value:.3f} |")
    lines.append(f"| Feature schema version | {prop.feature_schema_version or 'unknown'} |")
    lines.append("")
    lines.append("## Ship gate")
    lines.append("")
    lines.append(f"- Δlog-loss ≥ {DEFAULT_MIN_LOG_LOSS_GAIN:.4f}: "
                 f"{'✅' if prop.log_loss_delta >= DEFAULT_MIN_LOG_LOSS_GAIN else '❌'}")
    lines.append(f"- p-value ≤ {DEFAULT_MAX_P_VALUE:.2f}: "
                 f"{'✅' if prop.p_value <= DEFAULT_MAX_P_VALUE else '❌'}")
    lines.append(f"- n_train ≥ {DEFAULT_MIN_TRAIN_MATCHES:,}: "
                 f"{'✅' if prop.n_train >= DEFAULT_MIN_TRAIN_MATCHES else '❌'}")
    lines.append(f"- n_holdout ≥ {DEFAULT_MIN_HOLDOUT_MATCHES:,}: "
                 f"{'✅' if prop.n_holdout >= DEFAULT_MIN_HOLDOUT_MATCHES else '❌'}")
    lines.append("")
    if prop.decision:
        lines.append("## Next step")
        lines.append("")
        lines.append("```bash")
        lines.append(f"nutmeg-auto-retrain --action deploy --apply \\")
        lines.append(f"    --candidate {prop.artifact_path} \\")
        lines.append(f"    --artifact-base <production artifact dir>")
        lines.append("```")
    else:
        lines.append("## Next step")
        lines.append("")
        lines.append("No action. Wait for next quarterly cron + re-evaluate.")
    return "\n".join(lines) + "\n"


def render_deploy_markdown(version: str, artifact_path: str, base_dir: str,
                            previous_version: Optional[str]) -> str:
    return (
        f"# Layer B Deploy — {version}\n\n"
        f"_Generated {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
        f"- artifact_path: `{artifact_path}`\n"
        f"- base_dir: `{base_dir}`\n"
        f"- previous_version: `{previous_version or 'production_v5_w12'}`\n"
        f"- Layer A's `{LAYER_A_CORRECTION_FILENAME}` cleared (model swap → "
        f"T must re-calibrate)\n\n"
        f"Serving picks up the new artifact on next request via mtime cache.\n"
    )


def render_rollback_markdown(version_rolled_back: Optional[str], base_dir: str) -> str:
    return (
        f"# Layer B Rollback\n\n"
        f"_Generated {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
        f"- Rolled back from: `{version_rolled_back or 'unknown'}`\n"
        f"- base_dir: `{base_dir}`\n"
        f"- `{LIVE_ARTIFACT_POINTER_FILENAME}` removed → serving reverts to "
        f"base artifact\n"
        f"- `{LAYER_A_CORRECTION_FILENAME}` removed → Layer A reset to identity\n\n"
        f"Serving picks up the rollback on next request.\n"
    )


# ---------- Action implementations ----------

def do_propose(args: argparse.Namespace) -> int:
    """Build a RetrainProposal from numbers the user provides via flags,
    apply the ship gate, optionally journal + write the report.

    This wrapper deliberately does NOT run the training pipeline itself.
    The user runs `nutmeg-train` (which is slow) once; this CLI reads
    the resulting metadata and applies the ship-gate logic.
    """
    version = args.version or current_quarter_version()
    candidate_path = Path(args.candidate) if args.candidate else None

    # Layer B inputs come from the user / wrapper script after they've
    # run nutmeg-train. Read metadata.json + holdout-eval JSON from the
    # candidate dir; else use --log-loss-* flags as overrides.
    log_loss_before = float(args.log_loss_before) if args.log_loss_before is not None else float("nan")
    log_loss_after  = float(args.log_loss_after)  if args.log_loss_after  is not None else float("nan")
    p_value         = float(args.p_value)         if args.p_value         is not None else 1.0
    n_train         = int(args.n_train)           if args.n_train         is not None else 0
    n_holdout       = int(args.n_holdout)         if args.n_holdout       is not None else 0
    feature_schema  = args.feature_schema_version or ""
    train_window    = tuple(args.train_window.split(":", 1)) if args.train_window else ("", "")
    holdout_window  = tuple(args.holdout_window.split(":", 1)) if args.holdout_window else ("", "")

    delta = log_loss_before - log_loss_after if not (np.isnan(log_loss_before) or np.isnan(log_loss_after)) else float("nan")
    decision, reason = evaluate_ship_gate(
        log_loss_before=log_loss_before,
        log_loss_after=log_loss_after,
        p_value=p_value,
        n_train=n_train,
        n_holdout=n_holdout,
        min_log_loss_gain=args.min_log_loss_gain,
        max_p_value=args.max_p_value,
        min_train_matches=args.min_train_matches,
        min_holdout_matches=args.min_holdout_matches,
    )

    prop = RetrainProposal(
        artifact_version=version,
        artifact_path=str(candidate_path) if candidate_path else "",
        log_loss_before=log_loss_before,
        log_loss_after=log_loss_after,
        log_loss_delta=delta,
        p_value=p_value,
        n_train=n_train,
        n_holdout=n_holdout,
        train_window=train_window,
        holdout_window=holdout_window,
        decision=decision,
        reason=reason,
        feature_schema_version=feature_schema,
    )

    if args.apply:
        ensure_retrain_journal(args.db)
        record_retrain_journal(
            args.db,
            action="propose",
            artifact_version=version,
            artifact_path=str(candidate_path) if candidate_path else "",
            log_loss_before=log_loss_before,
            log_loss_after=log_loss_after,
            log_loss_delta=delta,
            p_value=p_value,
            n_train=n_train,
            n_holdout=n_holdout,
            train_window=train_window,
            holdout_window=holdout_window,
            decision=decision,
            reason=reason,
            extras={"feature_schema_version": feature_schema},
        )

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_proposal_markdown(prop))
        log.info("Wrote proposal card → %s", out_path)

    print(render_proposal_markdown(prop))
    return 0 if decision else 2  # 2 = "ship gate not passed"


def do_deploy(args: argparse.Namespace) -> int:
    """Atomically swap the production pointer to the candidate dir."""
    if not args.candidate:
        log.error("--candidate is required for --action deploy")
        return 1
    if not args.artifact_base:
        log.error("--artifact-base is required for --action deploy")
        return 1
    candidate = Path(args.candidate).resolve()
    base = Path(args.artifact_base).resolve()
    if not candidate.is_dir():
        log.error("candidate dir does not exist: %s", candidate)
        return 1
    base.mkdir(parents=True, exist_ok=True)

    # Read the prior pointer (if any) to record the rollback target
    prior_pointer = load_artifact_pointer(base)
    previous_version = (prior_pointer or {}).get("version")

    version = args.version or current_quarter_version()
    log_loss_delta = float(args.log_loss_after - args.log_loss_before) * -1.0 \
        if (args.log_loss_before is not None and args.log_loss_after is not None) else 0.0
    p_value = float(args.p_value) if args.p_value is not None else 0.0
    n_train = int(args.n_train) if args.n_train is not None else 0
    n_holdout = int(args.n_holdout) if args.n_holdout is not None else 0
    train_window = tuple(args.train_window.split(":", 1)) if args.train_window else ("", "")
    holdout_window = tuple(args.holdout_window.split(":", 1)) if args.holdout_window else ("", "")

    # AUDIT FIX (R4): re-evaluate the ship gate at DEPLOY time. propose and
    # deploy are separate CLI invocations, so deploy previously swapped the
    # production pointer with NO gate check (it journaled decision=True
    # unconditionally). A fat-fingered worse candidate — or one that regressed
    # since propose — would silently go live. Refuse unless the gate passes, or
    # --override-gate forces a logged emergency override.
    ll_before = float(args.log_loss_before) if args.log_loss_before is not None else float("nan")
    ll_after = float(args.log_loss_after) if args.log_loss_after is not None else float("nan")
    gate_ok, gate_reason = evaluate_ship_gate(
        log_loss_before=ll_before, log_loss_after=ll_after,
        p_value=p_value, n_train=n_train, n_holdout=n_holdout,
        min_log_loss_gain=args.min_log_loss_gain, max_p_value=args.max_p_value,
        min_train_matches=args.min_train_matches,
        min_holdout_matches=args.min_holdout_matches,
    )
    if not gate_ok and not args.override_gate:
        log.error("ship gate REJECTED deploy: %s", gate_reason)
        log.error("pass --override-gate to force an emergency manual deploy")
        return 2
    if not gate_ok:
        log.warning("ship gate FAILED (%s) — deploying anyway via --override-gate",
                    gate_reason)

    if args.apply:
        write_artifact_pointer(
            base,
            version=version,
            artifact_path=str(candidate),
            previous_version=previous_version,
            ship_gate_log_loss_delta=log_loss_delta,
            ship_gate_p_value=p_value,
            n_train=n_train,
            n_holdout=n_holdout,
            train_window=train_window,
            holdout_window=holdout_window,
        )
        layer_a_removed = remove_layer_a_correction(base)
        if layer_a_removed:
            log.info("Removed Layer A's %s (model swap → T must re-calibrate)",
                     LAYER_A_CORRECTION_FILENAME)
        ensure_retrain_journal(args.db)
        record_retrain_journal(
            args.db,
            action="deploy",
            artifact_version=version,
            artifact_path=str(candidate),
            log_loss_before=args.log_loss_before,
            log_loss_after=args.log_loss_after,
            log_loss_delta=log_loss_delta,
            p_value=p_value,
            n_train=n_train,
            n_holdout=n_holdout,
            train_window=train_window,
            holdout_window=holdout_window,
            decision=gate_ok,
            reason=("deployed via CLI — ship gate passed" if gate_ok
                    else f"deployed via CLI — ship gate OVERRIDDEN: {gate_reason}"),
            prior_version=previous_version,
        )
    else:
        log.info("(dry-run) would write pointer → %s",
                 base / LIVE_ARTIFACT_POINTER_FILENAME)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            render_deploy_markdown(version, str(candidate), str(base), previous_version)
        )

    print(render_deploy_markdown(version, str(candidate), str(base), previous_version))
    return 0


def do_rollback(args: argparse.Namespace) -> int:
    """Delete the live_artifact_pointer.json + Layer A's correction."""
    if not args.artifact_base:
        log.error("--artifact-base is required for --action rollback")
        return 1
    base = Path(args.artifact_base).resolve()
    prior = load_artifact_pointer(base)
    rolled_version = (prior or {}).get("version")
    rollback_target = (prior or {}).get("previous_version")

    if args.apply:
        removed_ptr = remove_artifact_pointer(base)
        removed_t = remove_layer_a_correction(base)
        log.info("removed: pointer=%s, layer_a_correction=%s",
                 removed_ptr, removed_t)
        ensure_retrain_journal(args.db)
        record_retrain_journal(
            args.db,
            action="rollback",
            artifact_version=rolled_version or "unknown",
            artifact_path=str(base),
            decision=True,
            reason=args.reason or "manual rollback via CLI",
            prior_version=rollback_target,
        )
    else:
        log.info("(dry-run) would remove %s + %s",
                 LIVE_ARTIFACT_POINTER_FILENAME,
                 LAYER_A_CORRECTION_FILENAME)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_rollback_markdown(rolled_version, str(base)))

    print(render_rollback_markdown(rolled_version, str(base)))
    return 0


# ---------- main ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="V11 backlog #4 — Layer B propose / deploy / rollback CLI.",
    )
    p.add_argument("--db", default="data/v4_observation.db",
                   help="Observation SQLite database path")
    p.add_argument("--action", choices=VALID_ACTIONS, default="propose",
                   help="What to do (default: propose)")
    p.add_argument("--apply", action="store_true",
                   help="Without this, the run is a dry-run (no journal write, "
                   "no file changes)")
    p.add_argument("--out", default=None,
                   help="Markdown report output path")
    p.add_argument("--quiet", action="store_true")

    # Shared metadata
    p.add_argument("--version", default=None,
                   help="Artifact version label; defaults to v_YYYY-QN of today")
    p.add_argument("--candidate", default=None,
                   help="Path to a freshly-trained artifact dir (for propose / deploy)")
    p.add_argument("--artifact-base", default=None,
                   help="Production artifact base dir where live_artifact_pointer.json "
                   "lives (e.g. data/v4_model)")

    # Numbers the wrapper passes after running training
    p.add_argument("--log-loss-before", type=float, default=None,
                   help="Production model's holdout log-loss")
    p.add_argument("--log-loss-after", type=float, default=None,
                   help="Candidate model's holdout log-loss")
    p.add_argument("--p-value", type=float, default=None,
                   help="Bootstrap p that candidate beats production")
    p.add_argument("--n-train", type=int, default=None)
    p.add_argument("--n-holdout", type=int, default=None)
    p.add_argument("--train-window", default=None,
                   help="'YYYY-MM-DD:YYYY-MM-DD'")
    p.add_argument("--holdout-window", default=None,
                   help="'YYYY-MM-DD:YYYY-MM-DD'")
    p.add_argument("--feature-schema-version", default="",
                   help="Set to current GBM_FEATURE_COLUMNS hash. Prevents "
                   "silent schema drift between retrains.")

    # Ship-gate overrides
    p.add_argument("--min-log-loss-gain", type=float, default=DEFAULT_MIN_LOG_LOSS_GAIN)
    p.add_argument("--max-p-value", type=float, default=DEFAULT_MAX_P_VALUE)
    p.add_argument("--min-train-matches", type=int, default=DEFAULT_MIN_TRAIN_MATCHES)
    p.add_argument("--min-holdout-matches", type=int, default=DEFAULT_MIN_HOLDOUT_MATCHES)
    p.add_argument("--override-gate", action="store_true",
                   help="Deploy even if the ship gate fails — emergency manual "
                   "override, recorded in the journal reason. (audit R4)")

    # Rollback bits
    p.add_argument("--reason", default="",
                   help="Human-readable reason field for journal rows")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    args = build_parser().parse_args(argv)
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    if args.action == "propose":
        return do_propose(args)
    if args.action == "deploy":
        return do_deploy(args)
    if args.action == "rollback":
        return do_rollback(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
