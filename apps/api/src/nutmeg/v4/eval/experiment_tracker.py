"""Experiment tracking for V4/V5 walk-forward runs.

V5 W10 — capture every bench / multi-season run into a versioned directory
keyed by git SHA + timestamp, so weekly CI can produce an experiment
diff card showing how log-loss / ECE / hit-rate evolved across V5 sprints.

Layout::

    data/v4_model/experiments/
      <sha7>_<utc-ts>/
        metadata.json    # git sha, timestamp, cfg, model_type
        pooled.json      # the pooled section of run_walk_forward result
        card.md          # human-readable bench card (same as nutmeg-bench --output)

Design choices:
- One directory per experiment so they're easy to scan / diff
- JSON + Markdown (no parquet / sqlite) so cards stay readable in git
- Stored under data/v4_model/experiments/ which IS gitignored (per W1 plan)
  EXCEPT we commit a `latest.json` symlink-equivalent and the weekly cards
  under docs/weekly/

Use cases:
1. ``track_experiment(result, ...)`` writes a new experiment directory.
2. ``list_experiments(...)`` enumerates all experiments in chronological order.
3. ``diff_experiments(a, b)`` returns a structured comparison: log-loss /
   ECE / hit-rate delta + which leagues moved.
4. ``format_diff_card(a, b)`` produces a Markdown card from a diff.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EXPERIMENTS_DIR = Path("data/v4_model/experiments")


def current_git_sha() -> str:
    """Short git SHA for the current HEAD, or 'no-git' when not in a git repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        return out or "no-git"
    except Exception:  # noqa: BLE001 — any failure → fallback label
        return "no-git"


def current_git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5,
        ).stdout.strip()
        return out or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# --------- write -------------------------------------------------------

@dataclass
class ExperimentRecord:
    """In-memory representation of one experiment after tracking."""

    experiment_dir: Path
    sha: str
    branch: str
    timestamp_utc: str
    model_type: str
    cfg: dict[str, Any]
    pooled: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


def track_experiment(
    result: dict[str, Any],
    *,
    card_text: str | None = None,
    model_type: str = "lightgbm",
    extra_metadata: dict[str, Any] | None = None,
    experiments_dir: Path | str = DEFAULT_EXPERIMENTS_DIR,
) -> ExperimentRecord:
    """Persist a walk_forward result to a new experiment directory.

    ``result`` is the dict returned by ``nutmeg.v4.eval.walk_forward.run_walk_forward``.
    """
    experiments_dir = Path(experiments_dir)
    experiments_dir.mkdir(parents=True, exist_ok=True)

    sha = current_git_sha()
    branch = current_git_branch()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    exp_dir = experiments_dir / f"{sha}_{ts}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    cfg = result.get("cfg", {}) or {}
    pooled = result.get("pooled", {}) or {}
    metadata = {
        "sha": sha,
        "branch": branch,
        "timestamp_utc": ts,
        "model_type": model_type,
        "cfg": cfg,
        **(extra_metadata or {}),
    }

    (exp_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str)
    )
    (exp_dir / "pooled.json").write_text(
        json.dumps(pooled, indent=2, default=str)
    )
    if card_text:
        (exp_dir / "card.md").write_text(card_text)

    return ExperimentRecord(
        experiment_dir=exp_dir,
        sha=sha,
        branch=branch,
        timestamp_utc=ts,
        model_type=model_type,
        cfg=cfg,
        pooled=pooled,
        metadata=metadata,
    )


# --------- read --------------------------------------------------------

def list_experiments(
    experiments_dir: Path | str = DEFAULT_EXPERIMENTS_DIR,
) -> list[ExperimentRecord]:
    """Enumerate experiments in chronological order (earliest first).

    Directory names are ``<sha>_<YYYYmmddTHHMMSSZ>`` which sort lexically =
    chronologically.
    """
    experiments_dir = Path(experiments_dir)
    if not experiments_dir.exists():
        return []
    records: list[ExperimentRecord] = []
    for sub in sorted(experiments_dir.iterdir()):
        if not sub.is_dir():
            continue
        meta_file = sub / "metadata.json"
        pooled_file = sub / "pooled.json"
        if not (meta_file.exists() and pooled_file.exists()):
            continue
        try:
            meta = json.loads(meta_file.read_text())
            pooled = json.loads(pooled_file.read_text())
        except Exception:  # noqa: BLE001 — skip corrupt experiments
            continue
        records.append(ExperimentRecord(
            experiment_dir=sub,
            sha=meta.get("sha", "unknown"),
            branch=meta.get("branch", "unknown"),
            timestamp_utc=meta.get("timestamp_utc", ""),
            model_type=meta.get("model_type", "lightgbm"),
            cfg=meta.get("cfg", {}) or {},
            pooled=pooled,
            metadata=meta,
        ))
    return records


# --------- diff --------------------------------------------------------

def _metric(pooled: dict[str, Any], slot: str, metric: str) -> float | None:
    """Pull pooled[<slot>][<metric>] safely; return None if not present."""
    s = pooled.get(slot)
    if not isinstance(s, dict):
        return None
    v = s.get(metric)
    return float(v) if v is not None else None


# Slots we care about, in display order. Keep in sync with eval/report.py rows.
_TRACKED_SLOTS = (
    "pinnacle_gbm",
    "gbm_dc_temp",
    "gbm_dc_pl_temp",
    "xgb_dc",
    "cat_dc",
    "ensemble",
    "ensemble_temp",
)


def diff_experiments(
    a: ExperimentRecord,
    b: ExperimentRecord,
    *,
    metric: str = "log_loss",
) -> list[dict[str, Any]]:
    """Per-slot delta b − a (so positive = degradation when metric = log_loss).

    Returns a list of dicts: {slot, a_value, b_value, delta} for each slot
    present in either pooled snapshot. Slots absent in both are skipped.
    """
    rows = []
    for slot in _TRACKED_SLOTS:
        va = _metric(a.pooled, slot, metric)
        vb = _metric(b.pooled, slot, metric)
        if va is None and vb is None:
            continue
        delta = None
        if va is not None and vb is not None:
            delta = vb - va
        rows.append({"slot": slot, "a": va, "b": vb, "delta": delta})
    return rows


def format_diff_card(
    a: ExperimentRecord,
    b: ExperimentRecord,
    *,
    title: str | None = None,
) -> str:
    """Markdown comparison of two experiment records."""
    lines: list[str] = []
    lines.append(title or f"# Experiment diff: {a.sha} → {b.sha}")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append(f"- **A**: {a.sha} ({a.branch}) at {a.timestamp_utc} — model_type={a.model_type}")
    lines.append(f"  cutoff={a.cfg.get('test_cutoff','?')}, train_window={a.cfg.get('train_window_days','?')}d")
    lines.append(f"- **B**: {b.sha} ({b.branch}) at {b.timestamp_utc} — model_type={b.model_type}")
    lines.append(f"  cutoff={b.cfg.get('test_cutoff','?')}, train_window={b.cfg.get('train_window_days','?')}d")
    lines.append("")

    for metric_name in ("log_loss", "ece", "hit_rate"):
        rows = diff_experiments(a, b, metric=metric_name)
        if not rows:
            continue
        lines.append(f"## {metric_name}")
        lines.append("")
        lines.append("| Slot | A | B | Δ (B − A) |")
        lines.append("|------|--:|--:|----------:|")
        for r in rows:
            sa = "—" if r["a"] is None else f"{r['a']:.4f}"
            sb = "—" if r["b"] is None else f"{r['b']:.4f}"
            sd = "—" if r["delta"] is None else f"{r['delta']:+.4f}"
            lines.append(f"| `{r['slot']}` | {sa} | {sb} | {sd} |")
        lines.append("")

    n_full_a = a.pooled.get("test_n_full")
    n_full_b = b.pooled.get("test_n_full")
    n_gbm_a = a.pooled.get("test_n_gbm")
    n_gbm_b = b.pooled.get("test_n_gbm")
    lines.append("## Test pool sizes")
    lines.append("")
    lines.append(f"- A: full={n_full_a}, gbm-eligible={n_gbm_a}")
    lines.append(f"- B: full={n_full_b}, gbm-eligible={n_gbm_b}")
    lines.append("")

    return "\n".join(lines)


__all__ = [
    "DEFAULT_EXPERIMENTS_DIR",
    "ExperimentRecord",
    "current_git_sha",
    "current_git_branch",
    "track_experiment",
    "list_experiments",
    "diff_experiments",
    "format_diff_card",
]
