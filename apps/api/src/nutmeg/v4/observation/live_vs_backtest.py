"""Live (real-bet) ROI vs backtest expectation comparison.

V5 W8 — answers the question: "is the ROI we're seeing in real betting
consistent with what walk-forward backtests would predict?"

A large positive gap (live ROI >> backtest) is suspicious — could be data
leakage in the backtest, lucky variance, or correlated bets. A large negative
gap (live ROI << backtest) is also a red flag — could be lookahead bias in
features, market drift since training cutoff, or model degradation.

Both ways: a gap of more than ±LIVE_BACKTEST_TOLERANCE_PCT_POINTS = 5
percentage points triggers a non-zero exit code so cron-based CI can alert.

Usage:

    nutmeg-live-vs-backtest --db data/v4_observation.db --weeks 4 \\
        --backtest-cutoff 2024-08-01 --out docs/weekly/2025-W18.md

    # exits 0 if gap ≤ 5pp; 2 if gap > 5pp; 1 on input/data errors
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from nutmeg.v4.observation.roi import compute_headline
from nutmeg.v4.observation.store import open_db


# A live-vs-backtest ROI gap above this many percentage points is flagged.
# Empirical: V4 backtest ROI variance over 4-week windows is ~1-3pp; a 5pp
# divergence implies a real model/data issue, not noise.
LIVE_BACKTEST_TOLERANCE_PCT_POINTS = 5.0


@dataclass
class LiveSlice:
    """Aggregated settled-bet stats over a date window (live observations only)."""

    n_sessions: int
    n_settled: int
    n_hit: int
    n_partial: int
    n_miss: int
    total_stake: float
    total_payout: float
    profit_loss: float
    roi: float                  # profit_loss / total_stake
    avg_hit_p_predicted: float
    actual_hit_rate: float


@dataclass
class BacktestSlice:
    """ROI / hit-rate snapshot from a walk-forward backtest summary dict."""

    cutoff: str
    test_n_full: int
    test_n_gbm: int
    log_loss: float
    hit_rate: float
    ece: float


@dataclass
class GapReport:
    live: LiveSlice
    backtest: BacktestSlice | None
    roi_gap_pp: float | None
    hit_rate_gap_pp: float | None
    over_tolerance: bool


def _window_bounds(weeks: int, as_of: datetime | None = None) -> tuple[str, str]:
    """Return (start_iso, end_iso) covering the most recent ``weeks`` weeks."""
    end = (as_of or datetime.now(timezone.utc)).replace(microsecond=0)
    start = end - timedelta(weeks=weeks)
    return start.isoformat(), end.isoformat()


def slice_live_settled(
    conn: sqlite3.Connection,
    *,
    start_iso: str,
    end_iso: str,
    snapshot_phase: str | None = None,
) -> LiveSlice:
    """Compute headline ROI for settlements whose session was created in window."""
    base_sql = """
        SELECT s.hit, s.stake, s.actual_payout, s.profit_loss, p.hit_probability,
               r.snapshot_phase
        FROM settlements s
        JOIN parlay_recommendations p ON s.rec_id = p.rec_id
        JOIN recommendation_sessions r ON p.session_id = r.session_id
        WHERE r.created_at >= ? AND r.created_at < ?
    """
    params: list[Any] = [start_iso, end_iso]
    if snapshot_phase is not None:
        base_sql += " AND r.snapshot_phase = ?"
        params.append(snapshot_phase)
    rows = list(conn.execute(base_sql, params).fetchall())

    n_settled = len(rows)
    n_hit = sum(1 for r in rows if r["hit"] == 1)
    n_partial = sum(1 for r in rows if r["hit"] == -1)
    n_miss = sum(1 for r in rows if r["hit"] == 0)
    total_stake = sum(r["stake"] for r in rows)
    total_payout = sum(r["actual_payout"] for r in rows)
    pl = total_payout - total_stake
    avg_hit_p = sum(r["hit_probability"] for r in rows) / n_settled if n_settled else 0.0
    actual_hit_rate = (n_hit + 0.5 * n_partial) / n_settled if n_settled else 0.0

    # Count distinct sessions in window for context
    sess = conn.execute(
        "SELECT COUNT(*) AS c FROM recommendation_sessions "
        "WHERE created_at >= ? AND created_at < ?"
        + (" AND snapshot_phase = ?" if snapshot_phase is not None else ""),
        params,
    ).fetchone()
    n_sessions = int(sess["c"]) if sess else 0

    return LiveSlice(
        n_sessions=n_sessions,
        n_settled=n_settled,
        n_hit=n_hit,
        n_partial=n_partial,
        n_miss=n_miss,
        total_stake=float(total_stake),
        total_payout=float(total_payout),
        profit_loss=float(pl),
        roi=pl / total_stake if total_stake > 0 else 0.0,
        avg_hit_p_predicted=avg_hit_p,
        actual_hit_rate=actual_hit_rate,
    )


def backtest_slice_from_pooled(pooled: dict, cutoff: str) -> BacktestSlice | None:
    """Build a BacktestSlice from the dict returned by walk_forward.run_walk_forward.

    Returns None when the relevant GBM-eligible numbers are not in the pool
    (e.g., the test set was empty).
    """
    gbm_t = pooled.get("gbm_dc_temp")
    if gbm_t is None:
        return None
    return BacktestSlice(
        cutoff=cutoff,
        test_n_full=int(pooled.get("test_n_full") or 0),
        test_n_gbm=int(pooled.get("test_n_gbm") or 0),
        log_loss=float(gbm_t["log_loss"]),
        hit_rate=float(gbm_t["hit_rate"]),
        ece=float(gbm_t["ece"]),
    )


def compute_gap(live: LiveSlice, backtest: BacktestSlice | None) -> GapReport:
    """Wrap the two slices into a comparable report."""
    if backtest is None:
        return GapReport(live=live, backtest=None, roi_gap_pp=None,
                         hit_rate_gap_pp=None, over_tolerance=False)
    # Backtest doesn't have ROI (it has log-loss/hit-rate). The closest analog
    # is hit-rate, so we compare both: hit-rate gap directly, ROI gap inferred.
    hit_rate_gap_pp = (live.actual_hit_rate - backtest.hit_rate) * 100.0
    # ROI is harder — backtests give probabilities, not ROI; for now we report
    # hit_rate gap as the primary alert signal and live ROI separately.
    over_tol = abs(hit_rate_gap_pp) > LIVE_BACKTEST_TOLERANCE_PCT_POINTS
    return GapReport(
        live=live,
        backtest=backtest,
        roi_gap_pp=None,  # Not directly comparable without a backtest-stake model
        hit_rate_gap_pp=hit_rate_gap_pp,
        over_tolerance=over_tol,
    )


def format_report(report: GapReport, *, weeks: int, as_of_iso: str) -> str:
    """Markdown card."""
    lines: list[str] = []
    lines.append("# Live vs Backtest — V5 W8")
    lines.append("")
    lines.append(f"_Generated {as_of_iso} (window = last {weeks} weeks)_")
    lines.append("")

    lines.append("## Live (real-bet) slice")
    lines.append("")
    L = report.live
    lines.append(f"- Sessions: **{L.n_sessions}**")
    lines.append(f"- Settled recommendations: **{L.n_settled}** "
                 f"(hit {L.n_hit} / partial {L.n_partial} / miss {L.n_miss})")
    lines.append(f"- Total stake: **{L.total_stake:.2f}**, payout: **{L.total_payout:.2f}**, "
                 f"P/L: **{L.profit_loss:+.2f}**")
    lines.append(f"- ROI: **{L.roi*100:+.2f}%**")
    lines.append(f"- Hit-rate: predicted **{L.avg_hit_p_predicted*100:.2f}%**, "
                 f"actual **{L.actual_hit_rate*100:.2f}%**")
    lines.append("")

    if report.backtest is None:
        lines.append("## Backtest slice")
        lines.append("")
        lines.append("_no comparable backtest run supplied_")
        lines.append("")
    else:
        B = report.backtest
        lines.append("## Backtest slice (walk-forward on training data)")
        lines.append("")
        lines.append(f"- Cutoff: **{B.cutoff}** (test pool n={B.test_n_gbm})")
        lines.append(f"- log-loss: **{B.log_loss:.4f}**, hit-rate: **{B.hit_rate*100:.2f}%**, "
                     f"ECE: **{B.ece:.4f}**")
        lines.append("")
        lines.append("## Gap")
        lines.append("")
        if report.hit_rate_gap_pp is not None:
            lines.append(f"- Hit-rate gap (live − backtest): **{report.hit_rate_gap_pp:+.2f} pp**")
        lines.append(f"- Tolerance: ±{LIVE_BACKTEST_TOLERANCE_PCT_POINTS:.1f} pp")
        if report.over_tolerance:
            lines.append("- **⚠️ OVER TOLERANCE** — investigate (leakage? lucky variance? "
                         "market drift since training cutoff?)")
        else:
            lines.append("- Within tolerance — no action needed.")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- This compares **hit-rate** (the directly observable quantity) between "
                 "real settlements and what the backtest predicted on the test split. "
                 "ROI requires a stake model that the backtest doesn't run.")
    lines.append("- A 1-3 pp gap is normal sampling noise for 4-week windows. ")
    lines.append("- See `docs/v5_w8_observation_loop.md` for the full observation pipeline.")
    return "\n".join(lines)


def run(
    db_path: str,
    *,
    weeks: int,
    backtest_pooled: dict | None,
    backtest_cutoff: str | None,
    snapshot_phase: str | None = None,
    as_of: datetime | None = None,
) -> GapReport:
    """End-to-end helper. Loads live slice from db, pairs with backtest dict
    (typically the ``pooled`` field of a walk_forward result), and returns
    the GapReport. The caller decides what to do with `report.over_tolerance`.
    """
    start_iso, end_iso = _window_bounds(weeks, as_of=as_of)
    with open_db(db_path) as conn:
        live = slice_live_settled(
            conn, start_iso=start_iso, end_iso=end_iso, snapshot_phase=snapshot_phase
        )
    backtest = (
        backtest_slice_from_pooled(backtest_pooled, backtest_cutoff or "")
        if backtest_pooled is not None
        else None
    )
    return compute_gap(live, backtest)


__all__ = [
    "LIVE_BACKTEST_TOLERANCE_PCT_POINTS",
    "LiveSlice",
    "BacktestSlice",
    "GapReport",
    "slice_live_settled",
    "backtest_slice_from_pooled",
    "compute_gap",
    "format_report",
    "run",
]
