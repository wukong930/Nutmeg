"""V11 backlog #4 — Layer B: quarterly auto-retrain of the CatBoost
production artifact.

Layer A (V10 W2) adjusts a single post-hoc temperature scalar; this
module is the next layer up — it proposes / deploys / rolls back a
**fresh CatBoost artifact** trained on more recent data.

Architecture (deliberate mirror of Layer A — see Layer A's docstring
in ``observation/auto_calibration.py``):

  propose  → train on N-quarter window, walk-forward on 8-week holdout,
             ship-gate (Δlog-loss ≥ 0.002, bootstrap p ≤ 0.05),
             write a ``retrain_journal`` row regardless of verdict.
  deploy   → write the candidate artifact dir + ``live_artifact_pointer.json``
             at the production base dir; delete Layer A's
             ``live_T_correction.json`` so the new model starts with a
             clean post-hoc correction.
  rollback → delete ``live_artifact_pointer.json`` + ``live_T_correction.json``.
             Serving immediately reverts to the base ``data/v4_model/``
             via the mtime-cached resolver in ``api/routes.py``.

The propose step does NOT touch the live serving path. It's safe to
run unattended via launchd (quarterly cron) — the user reviews the
markdown report and explicitly flips the deploy switch.

Production wiring (Day 3 of the V11 backlog #4 plan):
  - ``_artifact_path()`` in routes.py honors ``live_artifact_pointer.json``
  - This module ships the WRITE side (this file); the READ side is in
    ``api/routes.py``

This module IS NOT a full reimplementation of the training pipeline —
that lives in ``nutmeg.v4.model.train`` / ``nutmeg-train`` CLI. Layer B
wraps that pipeline: choose a slice, kick off training, evaluate, ship.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from nutmeg.v4.observation.store import open_db


log = logging.getLogger(__name__)


# ---------- Ship-gate constants (tighter than Layer A) ----------

# Layer A: 0.001 log-loss gain / p ≤ 0.10. Layer B is more disruptive
# (swaps a multi-MB model file vs a 1-scalar correction), so we
# require clearer evidence.
DEFAULT_MIN_LOG_LOSS_GAIN = 0.002    # holdout log-loss must drop by ≥ this
DEFAULT_MAX_P_VALUE = 0.05           # bootstrap p ≤ this to deploy
DEFAULT_HOLDOUT_WEEKS = 8            # 4× Layer A's 2 weeks; matches quarterly cadence
DEFAULT_MIN_TRAIN_MATCHES = 5000     # hard floor for a credible refit
DEFAULT_MIN_HOLDOUT_MATCHES = 100    # below this, p-values are noise
DEFAULT_BOOTSTRAP_N = 1000

# Auto-rollback constants (Layer B is ROI-driven, not log-loss-driven)
DEFAULT_ROI_TOLERANCE_PP = 5.0       # rollback if 4-week ROI drops > this many pp
DEFAULT_ROLLBACK_LOOKBACK_WEEKS = 4


# ---------- Data containers ----------

@dataclass
class HoldoutPair:
    """One match in the Layer B holdout: predictions from both the OLD
    (production) and NEW (candidate) artifacts, plus the actual outcome."""
    match_date: str
    league: str
    home_team: str
    away_team: str
    p_old_home: float
    p_old_draw: float
    p_old_away: float
    p_new_home: float
    p_new_draw: float
    p_new_away: float
    outcome: int  # 0=H, 1=D, 2=A


@dataclass
class RetrainProposal:
    """Outcome of `propose_retrain`. Caller decides to deploy."""
    artifact_version: str                   # 'v_2026-Q3'
    artifact_path: str                      # absolute path of candidate dir
    log_loss_before: float = float("nan")   # production model on holdout
    log_loss_after: float = float("nan")    # candidate model on holdout
    log_loss_delta: float = float("nan")    # before - after; positive = candidate better
    p_value: float = float("nan")           # bootstrap p that candidate beats production
    n_train: int = 0
    n_holdout: int = 0
    train_window: tuple[str, str] = ("", "")
    holdout_window: tuple[str, str] = ("", "")
    decision: bool = False                  # ship-gate verdict
    reason: str = ""
    feature_schema_version: str = ""        # to prevent silent schema drift
    extras: dict[str, Any] = field(default_factory=dict)


# ---------- Pure metric helpers (mirror Layer A) ----------

def log_loss_1x2(probs: np.ndarray, outcomes: np.ndarray, eps: float = 1e-9) -> float:
    """Mean log-loss. probs: (N, 3), outcomes: (N,) ∈ {0, 1, 2}."""
    if len(probs) == 0:
        return float("nan")
    rows = np.arange(len(outcomes))
    selected = np.clip(probs[rows, outcomes], eps, 1.0)
    return float(-np.log(selected).mean())


def bootstrap_p_value(
    probs_a: np.ndarray,
    probs_b: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_iter: int = DEFAULT_BOOTSTRAP_N,
    seed: int = 42,
) -> float:
    """Fraction of bootstrap resamples where model B's log-loss ≥ model A's.

    Returns one-sided p — how often the "candidate is better" claim
    would fail to replicate on resampled holdouts. Lower = more
    confident the candidate (B) is genuinely better than A.
    """
    if len(outcomes) == 0:
        return 1.0
    n = len(outcomes)
    rng = np.random.default_rng(seed)
    n_b_loses = 0
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        la = log_loss_1x2(probs_a[idx], outcomes[idx])
        lb = log_loss_1x2(probs_b[idx], outcomes[idx])
        # B "loses" means B's log-loss ≥ A's (A is at least as good as B)
        if lb >= la:
            n_b_loses += 1
    return n_b_loses / n_iter


def evaluate_ship_gate(
    log_loss_before: float,
    log_loss_after: float,
    p_value: float,
    n_train: int,
    n_holdout: int,
    *,
    min_log_loss_gain: float = DEFAULT_MIN_LOG_LOSS_GAIN,
    max_p_value: float = DEFAULT_MAX_P_VALUE,
    min_train_matches: int = DEFAULT_MIN_TRAIN_MATCHES,
    min_holdout_matches: int = DEFAULT_MIN_HOLDOUT_MATCHES,
) -> tuple[bool, str]:
    """Return (ship?, human-readable reason).

    Decision rule:
      - n_train >= min_train_matches
      - n_holdout >= min_holdout_matches
      - log_loss_before - log_loss_after >= min_log_loss_gain
      - p_value <= max_p_value
    All four must hold.
    """
    if n_train < min_train_matches:
        return False, (
            f"n_train={n_train} < min_train_matches={min_train_matches} — "
            "too few training matches for a credible refit"
        )
    if n_holdout < min_holdout_matches:
        return False, (
            f"n_holdout={n_holdout} < min_holdout_matches={min_holdout_matches} — "
            "holdout too small for reliable p-value"
        )
    if np.isnan(log_loss_before) or np.isnan(log_loss_after):
        return False, "log-loss is NaN (model evaluation failed)"
    delta = log_loss_before - log_loss_after  # positive = candidate better
    if delta < min_log_loss_gain:
        return False, (
            f"delta={delta:+.4f} < min_log_loss_gain={min_log_loss_gain:+.4f} — "
            "candidate's improvement too small to justify swap"
        )
    if p_value > max_p_value:
        return False, (
            f"p_value={p_value:.3f} > max_p_value={max_p_value:.2f} — "
            "improvement not statistically significant"
        )
    return True, (
        f"ship: delta={delta:+.4f}, p={p_value:.3f}, "
        f"n_train={n_train}, n_holdout={n_holdout}"
    )


# ---------- Versioning ----------

def current_quarter_version(as_of: dt.date | None = None) -> str:
    """Return the quarter label for the current date.

    Examples:
      2026-01-15 → 'v_2026-Q1'
      2026-04-01 → 'v_2026-Q2'
      2026-12-31 → 'v_2026-Q4'
    """
    if as_of is None:
        as_of = dt.date.today()
    quarter = (as_of.month - 1) // 3 + 1
    return f"v_{as_of.year}-Q{quarter}"


# ---------- Journal schema + persistence ----------

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS retrain_journal (
    journal_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at       TEXT NOT NULL,
    action            TEXT NOT NULL,         -- 'propose' | 'deploy' | 'rollback'
    artifact_version  TEXT NOT NULL,         -- 'v_2026-Q3'
    artifact_path     TEXT NOT NULL,
    log_loss_before   REAL,
    log_loss_after    REAL,
    log_loss_delta    REAL,
    p_value           REAL,
    n_train           INTEGER,
    n_holdout         INTEGER,
    train_window      TEXT,                  -- "2023-08-01 → 2026-03-31"
    holdout_window    TEXT,                  -- "2026-04-01 → 2026-05-25"
    decision          INTEGER NOT NULL,      -- 1 = shipped, 0 = held
    reason            TEXT,
    prior_version     TEXT,                  -- version this replaces / rolls back to
    extras_json       TEXT
);
CREATE INDEX IF NOT EXISTS idx_retrain_action ON retrain_journal(action, recorded_at);
"""


def ensure_retrain_journal(db_path: Path | str) -> None:
    """Idempotent CREATE TABLE for the retrain_journal."""
    with open_db(db_path) as conn:
        conn.executescript(JOURNAL_SCHEMA)


def record_retrain_journal(
    db_path: Path | str,
    *,
    action: str,
    artifact_version: str,
    artifact_path: str,
    log_loss_before: float | None = None,
    log_loss_after: float | None = None,
    log_loss_delta: float | None = None,
    p_value: float | None = None,
    n_train: int | None = None,
    n_holdout: int | None = None,
    train_window: tuple[str, str] | None = None,
    holdout_window: tuple[str, str] | None = None,
    decision: bool = False,
    reason: str = "",
    prior_version: str | None = None,
    extras: dict[str, Any] | None = None,
) -> int:
    """Insert one retrain_journal row; returns its journal_id."""
    if action not in ("propose", "deploy", "rollback"):
        raise ValueError(f"action must be propose|deploy|rollback, got {action!r}")
    ensure_retrain_journal(db_path)

    def _safe_float(x: Any) -> Optional[float]:
        if x is None:
            return None
        try:
            f = float(x)
        except (TypeError, ValueError):
            return None
        return None if np.isnan(f) else f

    def _fmt_window(w: tuple[str, str] | None) -> Optional[str]:
        if not w:
            return None
        return f"{w[0]} → {w[1]}"

    with open_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO retrain_journal (
                recorded_at, action, artifact_version, artifact_path,
                log_loss_before, log_loss_after, log_loss_delta, p_value,
                n_train, n_holdout, train_window, holdout_window,
                decision, reason, prior_version, extras_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                action,
                artifact_version,
                str(artifact_path),
                _safe_float(log_loss_before),
                _safe_float(log_loss_after),
                _safe_float(log_loss_delta),
                _safe_float(p_value),
                n_train,
                n_holdout,
                _fmt_window(train_window),
                _fmt_window(holdout_window),
                1 if decision else 0,
                reason,
                prior_version,
                json.dumps(extras or {}, ensure_ascii=False, default=str),
            ),
        )
        return int(cur.lastrowid)


def fetch_latest_journal_entry(
    db_path: Path | str,
    *,
    action: str | None = None,
) -> Optional[sqlite3.Row]:
    """Return the most recent journal row (optionally filtered by action),
    or None if the table is empty / DB doesn't exist."""
    p = Path(db_path)
    if not p.exists():
        return None
    ensure_retrain_journal(p)
    with open_db(p) as conn:
        if action:
            cur = conn.execute(
                "SELECT * FROM retrain_journal WHERE action = ? "
                "ORDER BY journal_id DESC LIMIT 1",
                (action,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM retrain_journal ORDER BY journal_id DESC LIMIT 1"
            )
        return cur.fetchone()


# ---------- Artifact-side pointer + Layer A interop ----------

LIVE_ARTIFACT_POINTER_FILENAME = "live_artifact_pointer.json"
LAYER_A_CORRECTION_FILENAME = "live_T_correction.json"


def write_artifact_pointer(
    base_dir: Path | str,
    *,
    version: str,
    artifact_path: str,
    previous_version: str | None,
    ship_gate_log_loss_delta: float,
    ship_gate_p_value: float,
    n_train: int,
    n_holdout: int,
    train_window: tuple[str, str],
    holdout_window: tuple[str, str],
    shipped_via: str = "nutmeg-auto-retrain --action=deploy",
) -> Path:
    """Write live_artifact_pointer.json at ``base_dir`` (the production
    artifact directory). The serving layer reads this file via mtime
    cache and redirects to ``artifact_path``.

    Atomic: writes to a tempfile + os.replace().

    ⛔ 2026-08-07: `base_dir` **必须已经存在**,不再 `mkdir(parents=True)`。
    这个指针是写进**生产 artifact 目录**里的(模型文件就住在那儿),所以一个
    不存在的 base 不可能是服务在读的那个目录 —— 自动建出来的唯一效果是让部署
    **看起来成功而实际不可见**:服务侧 `redirected=False`、
    `artifact_is_expected=True`、§18 一行 OK。拼错一个目录名就足够触发,
    而且没有任何东西会响。宁可在这里抛。
    """
    import os
    base = Path(base_dir)
    if not base.is_dir():
        raise NotADirectoryError(
            f"artifact base 不存在: {base} —— 拒绝创建。指针必须写进服务真正读的"
            f"那个生产 artifact 目录;凭空建一个只会写出没人读的指针。")
    target = base / LIVE_ARTIFACT_POINTER_FILENAME
    tmp = target.with_suffix(".tmp")
    payload = {
        "version": version,
        "artifact_path": str(artifact_path),
        "deployed_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "previous_version": previous_version or "production_v5_w12",
        "shipped_via": shipped_via,
        "ship_gate_log_loss_delta": float(ship_gate_log_loss_delta),
        "ship_gate_p_value": float(ship_gate_p_value),
        "n_train": int(n_train),
        "n_holdout": int(n_holdout),
        "train_window": list(train_window),
        "holdout_window": list(holdout_window),
    }
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    os.replace(tmp, target)
    return target


def artifact_trained_at(artifact_dir: Path | str) -> Optional[str]:
    """``trained_at_utc`` out of an artifact dir's metadata.json, or None.

    None means **"could not tell"** — dir missing, no metadata.json, unparsable
    JSON, or an artifact predating `47435ce` (which had no such key). It does
    NOT mean "fresh" and it does NOT mean "stale". Callers must keep those
    three apart: this project's recurring bug is a check whose "can't tell"
    reads as "fine".

    ⛔ No mtime fallback here on purpose. `cli/data_freshness.py` has one and
    it is right there — it asks "how long since we retrained", where a rsync'd
    file date is a usable proxy. Here the question is "which of these two
    artifacts is older", and a copy date answers a different question: `cp -r`
    an ancient model into a new dir and it becomes the newest thing on disk.
    """
    meta = Path(artifact_dir) / "metadata.json"
    try:
        raw = json.loads(meta.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    # Two shapes in the wild: persist.save_artifact() nests the training
    # metadata under "metadata"; some older/hand-built dirs put it flat.
    inner = raw.get("metadata")
    value = (inner or {}).get("trained_at_utc") if isinstance(inner, dict) else None
    value = value if value is not None else raw.get("trained_at_utc")
    return str(value) if value else None


def parse_trained_at(value: Optional[str]) -> Optional[dt.datetime]:
    """ISO ``trained_at_utc`` → aware datetime, or None if unparsable.

    Naive timestamps are read as UTC (the key is named `_utc` and
    `cli/train.py` always writes an offset; this only covers hand-edited dirs).

    ⛔ Exists so nobody compares the raw strings. Lexicographic order is only
    correct while both sides carry the *same* offset — true for everything
    `cli/train.py` writes today, which is exactly the shape of guard that
    passes silently on the one case it was built for.
    """
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def load_artifact_pointer(base_dir: Path | str) -> Optional[dict]:
    """Read live_artifact_pointer.json or None if absent / malformed."""
    p = Path(base_dir) / LIVE_ARTIFACT_POINTER_FILENAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("could not parse %s: %s", p, exc)
        return None


def remove_artifact_pointer(base_dir: Path | str) -> bool:
    """Delete the pointer file. Returns True if it was removed, False
    if it was absent. Layer A's live_T_correction.json is NOT touched
    by this function — see ``remove_layer_a_correction`` below."""
    p = Path(base_dir) / LIVE_ARTIFACT_POINTER_FILENAME
    if not p.exists():
        return False
    p.unlink()
    return True


def remove_layer_a_correction(base_dir: Path | str) -> bool:
    """Delete Layer A's live_T_correction.json from the base artifact
    dir. Called as part of Layer B deploy + rollback (Layer A must
    reset to identity when the underlying model changes).

    Returns True if a file was removed.
    """
    p = Path(base_dir) / LAYER_A_CORRECTION_FILENAME
    if not p.exists():
        return False
    p.unlink()
    return True


def resolve_effective_artifact_path(base_dir: Path | str) -> str:
    """Pure-function resolver mirroring ``_artifact_path()`` logic in
    routes.py: when ``live_artifact_pointer.json`` is present and the
    target dir exists, return the redirected path; else return base.

    Lives in this module (not routes.py) so it can be unit-tested
    without spinning up FastAPI.
    """
    base = Path(base_dir)
    pointer = load_artifact_pointer(base)
    if pointer is None:
        return str(base)
    target = pointer.get("artifact_path")
    if target and Path(target).is_dir():
        return target
    log.warning(
        "pointer references missing artifact %s — falling back to %s",
        target, base,
    )
    return str(base)
