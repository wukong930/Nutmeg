"""V10 W2 Day 1 — Layer A: auto-T post-hoc calibration drift correction.

Closes the recommend → settle → learn loop. Without this, the daily
cron only reports drift (P1#19); it can't act on it.

Design (per Q3 conclusions):
  - Tiny intervention: ONLY adjust a post-hoc temperature scalar on
    1X2 probabilities. Don't retrain the GBM. T-only is a 1-param
    optimization on ~30-300 settled match pairs → near-zero overfit risk.
  - Holdout validation: split past N weeks into train/holdout, fit T
    on train, evaluate on holdout. Require:
      (a) log-loss improvement ≥ DEFAULT_MIN_LOG_LOSS_GAIN on holdout
      (b) bootstrap p-value < DEFAULT_MAX_P_VALUE
  - Audit trail: every proposal / deploy / rollback logged to a
    `calibration_journal` table in the observation DB.
  - Auto-rollback: if a deployed T produces ROI worse than previous
    week by > DEFAULT_ROI_TOLERANCE_PP, revert to identity (T=1.0)
    on next check.

Production wiring (per Q3 design, V10 W2 Day 3 plan):
  - Successful proposal writes `data/v4_model_*/live_T_correction.json`
    with {"T": 1.05, "deployed_at": "...", "lookback_weeks": 8, ...}
  - The recommend pipeline reads this file at predict time and applies
    the correction as a final pass over 1X2 probabilities.
  - Reading is cached + invalidated on file mtime, so a new deploy
    takes effect on the next request without server restart.

This module is the "propose + validate" layer. The "deploy + serve"
wiring is Day 3.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from nutmeg.v4.observation.store import open_db


log = logging.getLogger(__name__)

# Ship-gate constants. Conservative defaults — Layer A's job is to
# correct drift, not to "improve the model"; a tiny improvement
# threshold avoids chasing noise.
DEFAULT_MIN_LOG_LOSS_GAIN = 0.001    # holdout log-loss must drop by this much
DEFAULT_MAX_P_VALUE = 0.10           # bootstrap p < 0.10 to deploy
DEFAULT_LOOKBACK_WEEKS = 8           # past N weeks of live data
DEFAULT_HOLDOUT_WEEKS = 2            # of which, last K weeks are holdout
DEFAULT_MIN_SAMPLES = 30             # need at least this many train pairs
DEFAULT_BOOTSTRAP_N = 1000
DEFAULT_T_LOWER = 0.5                # temperature search bounds
DEFAULT_T_UPPER = 2.0

# Auto-rollback constants (applied at NEXT check, not this one)
DEFAULT_ROI_TOLERANCE_PP = 5.0       # revert if next-week ROI drops by > 5pp


# --------- Data containers ----------

@dataclass
class CalibrationPair:
    """One (predicted probs, actual outcome) tuple from the observation DB."""
    match_date: str
    league: str
    home_team: str
    away_team: str
    p_home: float
    p_draw: float
    p_away: float
    outcome: int  # 0=H, 1=D, 2=A


@dataclass
class DriftProposal:
    """Outcome of `propose_drift_correction`. Caller decides to deploy."""
    proposed_T: float
    current_T: float = 1.0
    log_loss_before: float = float("nan")
    log_loss_after: float = float("nan")
    log_loss_delta: float = float("nan")
    p_value: float = float("nan")
    n_train: int = 0
    n_holdout: int = 0
    train_window: tuple[str, str] = ("", "")
    holdout_window: tuple[str, str] = ("", "")
    should_apply: bool = False
    reason: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


# --------- Core math ----------

def apply_post_temperature(probs: np.ndarray, T: float, eps: float = 1e-9) -> np.ndarray:
    """Post-hoc temperature scaling on already-calibrated probabilities.

    p_new[i] = exp(log(p[i]) / T) / sum_j exp(log(p[j]) / T)

    T > 1 → flatten (less confident); T < 1 → sharpen; T = 1 → identity.
    Handles 1D (single row) or 2D (N×K) inputs. Skips rows with NaN.
    """
    probs = np.asarray(probs, dtype=float)
    if probs.ndim == 1:
        return apply_post_temperature(probs[np.newaxis, :], T, eps)[0]
    log_p = np.log(np.clip(probs, eps, 1.0))
    z = log_p / T
    # softmax via stable subtract-max
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def log_loss_1x2(probs: np.ndarray, outcomes: np.ndarray, eps: float = 1e-9) -> float:
    """Multinomial log-loss for 1X2 outcomes. NaN-safe; -1 outcomes skipped."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    mask = outcomes >= 0
    probs_m = np.clip(probs[mask], eps, 1.0 - eps)
    outc_m = outcomes[mask]
    if len(outc_m) == 0:
        return float("nan")
    return float(-np.mean(np.log(probs_m[np.arange(len(outc_m)), outc_m])))


def fit_post_temperature(
    probs: np.ndarray,
    outcomes: np.ndarray,
    *,
    lower: float = DEFAULT_T_LOWER,
    upper: float = DEFAULT_T_UPPER,
) -> float:
    """1-parameter optimization for the best post-hoc T.

    Uses scipy.optimize.minimize_scalar over the bounded T range.
    """
    from scipy.optimize import minimize_scalar

    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    mask = outcomes >= 0
    probs = probs[mask]
    outcomes = outcomes[mask]
    if len(outcomes) == 0:
        return 1.0

    def _ll(T: float) -> float:
        return log_loss_1x2(apply_post_temperature(probs, T), outcomes)

    result = minimize_scalar(_ll, bounds=(lower, upper), method="bounded")
    return float(result.x)


def bootstrap_p_value(
    probs: np.ndarray,
    outcomes: np.ndarray,
    T_old: float,
    T_new: float,
    *,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_N,
    seed: int = 12345,
) -> float:
    """One-sided bootstrap p-value: how often does T_new fail to beat T_old?

    Returns the fraction of resamples where log_loss(T_new) >= log_loss(T_old).
    Low p-value → T_new is reliably better → can deploy.
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    mask = outcomes >= 0
    probs = probs[mask]
    outcomes = outcomes[mask]
    n = len(outcomes)
    if n == 0:
        return 1.0  # no data → can't deploy

    rng = np.random.default_rng(seed)
    n_fail = 0
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        p_re = probs[idx]
        o_re = outcomes[idx]
        ll_old = log_loss_1x2(apply_post_temperature(p_re, T_old), o_re)
        ll_new = log_loss_1x2(apply_post_temperature(p_re, T_new), o_re)
        if ll_new >= ll_old:
            n_fail += 1
    return n_fail / n_bootstrap


# --------- Data loading ----------

def load_calibration_pairs(
    db_path: Path | str,
    weeks: int,
    *,
    as_of: dt.datetime | None = None,
) -> list[CalibrationPair]:
    """Pull `(p_home, p_draw, p_away, actual_outcome)` rows from the last
    ``weeks`` weeks of live data.

    JOINs single_predictions (predicted probs per match) with
    match_outcomes (actual scores). Rows without an outcome are dropped.
    """
    if as_of is None:
        as_of = dt.datetime.now(dt.UTC).replace(microsecond=0)
    cutoff = as_of - dt.timedelta(weeks=weeks)
    cutoff_iso = cutoff.isoformat()

    rows: list[CalibrationPair] = []
    with open_db(db_path) as conn:
        cur = conn.execute(
            """
            SELECT
                sp.match_date, sp.league, sp.home_team, sp.away_team,
                sp.p_home_1x2, sp.p_draw_1x2, sp.p_away_1x2,
                mo.home_goals, mo.away_goals
            FROM single_predictions sp
            JOIN recommendation_sessions rs ON sp.session_id = rs.session_id
            JOIN match_outcomes mo
              ON mo.match_date = sp.match_date
             AND mo.league = sp.league
             AND mo.home_team = sp.home_team
             AND mo.away_team = sp.away_team
            WHERE rs.created_at >= ?
            ORDER BY sp.match_date ASC
            """,
            (cutoff_iso,),
        )
        for r in cur.fetchall():
            hg, ag = r["home_goals"], r["away_goals"]
            outcome = 0 if hg > ag else (2 if hg < ag else 1)
            rows.append(CalibrationPair(
                match_date=r["match_date"],
                league=r["league"],
                home_team=r["home_team"],
                away_team=r["away_team"],
                p_home=float(r["p_home_1x2"]),
                p_draw=float(r["p_draw_1x2"]),
                p_away=float(r["p_away_1x2"]),
                outcome=outcome,
            ))
    return rows


def split_train_holdout(
    pairs: list[CalibrationPair],
    holdout_weeks: int,
    *,
    as_of: dt.datetime | None = None,
) -> tuple[list[CalibrationPair], list[CalibrationPair]]:
    """Holdout = most recent `holdout_weeks` of matches; train = earlier."""
    if as_of is None:
        as_of = dt.datetime.now(dt.UTC)
    cutoff = (as_of - dt.timedelta(weeks=holdout_weeks)).date()
    cutoff_iso = cutoff.isoformat()
    train = [p for p in pairs if p.match_date < cutoff_iso]
    holdout = [p for p in pairs if p.match_date >= cutoff_iso]
    return train, holdout


def _stack(pairs: list[CalibrationPair]) -> tuple[np.ndarray, np.ndarray]:
    if not pairs:
        return np.empty((0, 3)), np.empty(0, dtype=int)
    probs = np.array([[p.p_home, p.p_draw, p.p_away] for p in pairs])
    outc = np.array([p.outcome for p in pairs], dtype=int)
    return probs, outc


# --------- Orchestrator ----------

def propose_drift_correction(
    db_path: Path | str,
    *,
    lookback_weeks: int = DEFAULT_LOOKBACK_WEEKS,
    holdout_weeks: int = DEFAULT_HOLDOUT_WEEKS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_log_loss_gain: float = DEFAULT_MIN_LOG_LOSS_GAIN,
    max_p_value: float = DEFAULT_MAX_P_VALUE,
    current_T: float = 1.0,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_N,
    as_of: dt.datetime | None = None,
) -> DriftProposal:
    """Main entry point. Fits a candidate post-T on the train slice,
    validates on the holdout slice, returns a DriftProposal with the
    ship-gate verdict.

    Caller decides to actually deploy (writes the artifact-side
    correction file). This function is read-only against the DB.
    """
    if as_of is None:
        as_of = dt.datetime.now(dt.UTC).replace(microsecond=0)

    all_pairs = load_calibration_pairs(db_path, lookback_weeks, as_of=as_of)
    train, holdout = split_train_holdout(all_pairs, holdout_weeks, as_of=as_of)

    proposal = DriftProposal(
        proposed_T=current_T,
        current_T=current_T,
        n_train=len(train),
        n_holdout=len(holdout),
    )
    if train:
        proposal.train_window = (
            min(p.match_date for p in train),
            max(p.match_date for p in train),
        )
    if holdout:
        proposal.holdout_window = (
            min(p.match_date for p in holdout),
            max(p.match_date for p in holdout),
        )

    if len(train) < min_samples:
        proposal.reason = (
            f"insufficient train data ({len(train)} pairs < {min_samples} min); "
            f"holdout has {len(holdout)} pairs"
        )
        return proposal

    if len(holdout) == 0:
        proposal.reason = "no holdout data for validation"
        return proposal

    # Fit T on train
    probs_tr, outc_tr = _stack(train)
    T_new = fit_post_temperature(probs_tr, outc_tr)
    proposal.proposed_T = T_new

    # Evaluate on holdout
    probs_ho, outc_ho = _stack(holdout)
    ll_before = log_loss_1x2(apply_post_temperature(probs_ho, current_T), outc_ho)
    ll_after = log_loss_1x2(apply_post_temperature(probs_ho, T_new), outc_ho)
    delta = ll_before - ll_after  # positive = improvement
    proposal.log_loss_before = ll_before
    proposal.log_loss_after = ll_after
    proposal.log_loss_delta = delta

    # Bootstrap significance on holdout
    p_val = bootstrap_p_value(
        probs_ho, outc_ho, current_T, T_new, n_bootstrap=n_bootstrap,
    )
    proposal.p_value = p_val

    # Ship gate
    if delta < min_log_loss_gain:
        proposal.reason = (
            f"holdout log-loss improvement {delta:+.4f} < threshold {min_log_loss_gain}; "
            f"T_new={T_new:.3f} not deployed"
        )
        return proposal
    if p_val > max_p_value:
        proposal.reason = (
            f"bootstrap p-value {p_val:.3f} > threshold {max_p_value}; "
            f"T_new={T_new:.3f} not deployed"
        )
        return proposal

    proposal.should_apply = True
    proposal.reason = (
        f"ship gate PASSED: holdout Δ log-loss {delta:+.4f}, "
        f"p-value {p_val:.3f}, T_new={T_new:.3f}"
    )
    return proposal


# --------- Audit log ----------

CALIBRATION_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS calibration_journal (
    journal_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at  TEXT NOT NULL,
    action       TEXT NOT NULL,        -- 'propose' | 'deploy' | 'rollback'
    current_T    REAL NOT NULL,
    proposed_T   REAL NOT NULL,
    log_loss_before  REAL,
    log_loss_after   REAL,
    log_loss_delta   REAL,
    p_value      REAL,
    n_train      INTEGER,
    n_holdout    INTEGER,
    train_start  TEXT,
    train_end    TEXT,
    holdout_start TEXT,
    holdout_end   TEXT,
    decision     INTEGER NOT NULL,     -- 1 = applied, 0 = skipped
    reason       TEXT,
    extras_json  TEXT
)
"""


def ensure_calibration_journal(db_path: Path | str) -> None:
    """Create the audit-log table if missing. Idempotent."""
    with open_db(db_path) as conn:
        conn.execute(CALIBRATION_JOURNAL_SCHEMA)


def record_calibration_journal(
    db_path: Path | str,
    proposal: DriftProposal,
    action: str = "propose",
    *,
    as_of: dt.datetime | None = None,
) -> int:
    """Insert one row into calibration_journal. Returns the new row's id."""
    ensure_calibration_journal(db_path)
    if as_of is None:
        as_of = dt.datetime.now(dt.UTC).replace(microsecond=0)
    with open_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO calibration_journal (
                recorded_at, action, current_T, proposed_T,
                log_loss_before, log_loss_after, log_loss_delta, p_value,
                n_train, n_holdout,
                train_start, train_end, holdout_start, holdout_end,
                decision, reason, extras_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                as_of.isoformat(),
                action,
                proposal.current_T,
                proposal.proposed_T,
                None if np.isnan(proposal.log_loss_before) else proposal.log_loss_before,
                None if np.isnan(proposal.log_loss_after) else proposal.log_loss_after,
                None if np.isnan(proposal.log_loss_delta) else proposal.log_loss_delta,
                None if np.isnan(proposal.p_value) else proposal.p_value,
                proposal.n_train,
                proposal.n_holdout,
                proposal.train_window[0],
                proposal.train_window[1],
                proposal.holdout_window[0],
                proposal.holdout_window[1],
                1 if proposal.should_apply else 0,
                proposal.reason,
                json.dumps(proposal.extras, default=str) if proposal.extras else None,
            ),
        )
        return cur.lastrowid


def fetch_latest_journal_entry(
    db_path: Path | str,
    action: str | None = None,
) -> dict[str, Any] | None:
    """Most recent row from calibration_journal, optionally filtered by action."""
    ensure_calibration_journal(db_path)
    sql = "SELECT * FROM calibration_journal"
    params: list[Any] = []
    if action is not None:
        sql += " WHERE action = ?"
        params.append(action)
    sql += " ORDER BY recorded_at DESC LIMIT 1"
    with open_db(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


# --------- Artifact-side correction file (V10 W2 Day 3) ---------------

LIVE_T_CORRECTION_FILENAME = "live_T_correction.json"


def write_artifact_correction(
    artifact_dir: Path | str,
    proposal: DriftProposal,
    *,
    as_of: dt.datetime | None = None,
) -> Path:
    """Persist a deploy decision as `<artifact_dir>/live_T_correction.json`.

    Distinct from the static `metadata.json` — this file is rewritten
    each time auto-T deploys, while metadata.json is the immutable model
    descriptor. Serving layer reads both at request time.
    """
    art_dir = Path(artifact_dir)
    if not art_dir.is_dir():
        raise FileNotFoundError(f"artifact directory not found: {art_dir}")
    if as_of is None:
        as_of = dt.datetime.now(dt.UTC).replace(microsecond=0)
    payload = {
        "T": float(proposal.proposed_T),
        "deployed_at_utc": as_of.isoformat(),
        "train_window": list(proposal.train_window),
        "holdout_window": list(proposal.holdout_window),
        "log_loss_before": None if np.isnan(proposal.log_loss_before) else proposal.log_loss_before,
        "log_loss_after": None if np.isnan(proposal.log_loss_after) else proposal.log_loss_after,
        "log_loss_delta": None if np.isnan(proposal.log_loss_delta) else proposal.log_loss_delta,
        "p_value": None if np.isnan(proposal.p_value) else proposal.p_value,
        "n_train": proposal.n_train,
        "n_holdout": proposal.n_holdout,
        "reason": proposal.reason,
        "previous_T": float(proposal.current_T),
    }
    path = art_dir / LIVE_T_CORRECTION_FILENAME
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_artifact_correction(artifact_dir: Path | str) -> dict | None:
    """Read `live_T_correction.json` from the artifact dir.

    Returns None when the file is missing (= no live correction,
    serving uses identity T=1.0) or unparseable (logged then ignored).
    """
    art_dir = Path(artifact_dir)
    if not art_dir.is_dir():
        return None
    path = art_dir / LIVE_T_CORRECTION_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("could not parse %s: %s — treating as no correction", path, exc)
        return None


def remove_artifact_correction(artifact_dir: Path | str) -> bool:
    """Delete the correction file (auto-rollback support).

    Returns True if removed, False if it didn't exist.
    """
    path = Path(artifact_dir) / LIVE_T_CORRECTION_FILENAME
    if not path.exists():
        return False
    path.unlink()
    return True


def apply_correction_to_probs(
    probs: np.ndarray, correction: dict | None
) -> np.ndarray:
    """Apply the post-T correction (if any) to 1X2 probabilities.

    None correction (or T close to 1.0) → identity passthrough.
    """
    if correction is None:
        return np.asarray(probs)
    T = float(correction.get("T", 1.0))
    if abs(T - 1.0) < 1e-9:
        return np.asarray(probs)
    return apply_post_temperature(probs, T)


__all__ = [
    "CalibrationPair",
    "DriftProposal",
    "apply_post_temperature",
    "log_loss_1x2",
    "fit_post_temperature",
    "bootstrap_p_value",
    "load_calibration_pairs",
    "split_train_holdout",
    "propose_drift_correction",
    "ensure_calibration_journal",
    "record_calibration_journal",
    "fetch_latest_journal_entry",
    "DEFAULT_LOOKBACK_WEEKS",
    "DEFAULT_HOLDOUT_WEEKS",
    "DEFAULT_MIN_SAMPLES",
    "DEFAULT_MIN_LOG_LOSS_GAIN",
    "DEFAULT_MAX_P_VALUE",
    # V10 W2 Day 3 — serving integration
    "LIVE_T_CORRECTION_FILENAME",
    "write_artifact_correction",
    "load_artifact_correction",
    "remove_artifact_correction",
    "apply_correction_to_probs",
]
