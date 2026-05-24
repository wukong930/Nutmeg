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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
    """Reference snapshot from either walk-forward or ROI replay backtests."""

    cutoff: str
    test_n_full: int
    test_n_gbm: int
    log_loss: float | None
    hit_rate: float
    ece: float | None
    source: str = "walk_forward"
    label: str = "walk-forward"
    n_sessions: int = 0
    n_settled: int = 0
    roi: float | None = None
    avg_hit_p_predicted: float | None = None


@dataclass
class GapReport:
    live: LiveSlice
    backtest: BacktestSlice | None
    roi_gap_pp: float | None
    hit_rate_gap_pp: float | None
    over_tolerance: bool


def _window_bounds(weeks: int, as_of: datetime | None = None) -> tuple[str, str]:
    """Return (start_iso, end_iso) covering the most recent ``weeks`` weeks."""
    end = (as_of or datetime.now(UTC)).replace(microsecond=0)
    start = end - timedelta(weeks=weeks)
    return start.isoformat(), end.isoformat()


def slice_live_settled(
    conn: sqlite3.Connection,
    *,
    start_iso: str,
    end_iso: str,
    snapshot_phase: str | None = None,
    model_arm: str | None = None,
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
    if model_arm in (None, "all"):
        pass
    elif model_arm == "lineup_aware":
        base_sql += " AND json_extract(r.metadata_json, '$.model.with_lineups') = 1"
    elif model_arm == "lineup_free":
        base_sql += (
            " AND (json_extract(r.metadata_json, '$.model.with_lineups') IS NULL"
            " OR json_extract(r.metadata_json, '$.model.with_lineups') = 0)"
        )
    else:
        raise ValueError(
            "model_arm must be one of None, 'all', 'lineup_aware', 'lineup_free'"
        )
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
        + (" AND snapshot_phase = ?" if snapshot_phase is not None else "")
        + (
            " AND json_extract(metadata_json, '$.model.with_lineups') = 1"
            if model_arm == "lineup_aware" else ""
        )
        + (
            " AND (json_extract(metadata_json, '$.model.with_lineups') IS NULL"
            " OR json_extract(metadata_json, '$.model.with_lineups') = 0)"
            if model_arm == "lineup_free" else ""
        ),
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


def backtest_slice_from_pooled(pooled: dict[str, Any], cutoff: str) -> BacktestSlice | None:
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
        source="walk_forward",
        label="walk-forward",
    )


def roi_backtest_slice_from_db(db_path: str | Path, *, arm: str = "lineup_aware") -> BacktestSlice:
    """Build a reference slice from a DB produced by ``nutmeg-roi-backtest``.

    P1#19: after P1#18 flipped production to lineup-aware, the most useful
    reference is no longer only walk-forward hit-rate. We need the historical
    recommendation replay's ROI + hit-rate, sliced to the same model arm.
    """
    from nutmeg.v4.observation.ab_report import slice_lineup_aware, slice_lineup_free

    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"ROI backtest DB not found: {p}")

    with open_db(p) as conn:
        if arm == "lineup_aware":
            ref = slice_lineup_aware(conn)
            label = "lineup-aware ROI backtest"
        elif arm in ("lineup_free", "default"):
            ref = slice_lineup_free(conn)
            label = "lineup-free ROI backtest"
        else:
            raise ValueError("arm must be one of 'lineup_aware', 'lineup_free', 'default'")

    return BacktestSlice(
        cutoff="roi-backtest",
        test_n_full=ref.n_settled,
        test_n_gbm=ref.n_settled,
        log_loss=None,
        hit_rate=ref.actual_hit_rate,
        ece=None,
        source="roi_backtest",
        label=label,
        n_sessions=ref.n_sessions,
        n_settled=ref.n_settled,
        roi=ref.roi,
        avg_hit_p_predicted=ref.avg_hit_p_predicted,
    )


def compute_gap(
    live: LiveSlice,
    backtest: BacktestSlice | None,
    *,
    tolerance_pp: float = LIVE_BACKTEST_TOLERANCE_PCT_POINTS,
) -> GapReport:
    """Wrap the two slices into a comparable report.

    ``tolerance_pp`` is the pp threshold at which `over_tolerance` flips
    to True. Defaults to LIVE_BACKTEST_TOLERANCE_PCT_POINTS (5.0pp), which
    is right for same-source comparisons (live + reference both sourced
    from the same bookmaker / snapshot timing).

    For cross-source comparisons (e.g., live API-Football vs reference
    football-data PSC), set tolerance_pp higher (~50pp). See P1#22 doc
    for triage rationale; the cross-source price-level gap alone can
    push ROI gap past 30pp without any model issue.
    """
    if backtest is None:
        return GapReport(live=live, backtest=None, roi_gap_pp=None,
                         hit_rate_gap_pp=None, over_tolerance=False)
    if live.n_settled == 0 or (backtest.source == "roi_backtest" and backtest.n_settled == 0):
        return GapReport(live=live, backtest=backtest, roi_gap_pp=None,
                         hit_rate_gap_pp=None, over_tolerance=False)
    # Backtest doesn't have ROI (it has log-loss/hit-rate). The closest analog
    # is hit-rate, so we compare both: hit-rate gap directly, ROI gap inferred.
    hit_rate_gap_pp = (live.actual_hit_rate - backtest.hit_rate) * 100.0
    roi_gap_pp = (
        (live.roi - backtest.roi) * 100.0
        if backtest.roi is not None
        else None
    )
    over_tol = abs(hit_rate_gap_pp) > tolerance_pp
    if roi_gap_pp is not None:
        over_tol = over_tol or abs(roi_gap_pp) > tolerance_pp
    return GapReport(
        live=live,
        backtest=backtest,
        roi_gap_pp=roi_gap_pp,
        hit_rate_gap_pp=hit_rate_gap_pp,
        over_tolerance=over_tol,
    )


def format_report(
    report: GapReport,
    *,
    weeks: int,
    as_of_iso: str,
    tolerance_pp: float = LIVE_BACKTEST_TOLERANCE_PCT_POINTS,
) -> str:
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
        if B.source == "roi_backtest":
            lines.append("## Backtest slice (historical ROI replay)")
        else:
            lines.append("## Backtest slice (walk-forward on training data)")
        lines.append("")
        lines.append(f"- Reference: **{B.label}**")
        if B.source == "roi_backtest":
            lines.append(
                f"- Sessions: **{B.n_sessions}**, "
                f"settled recommendations: **{B.n_settled}**"
            )
            if B.roi is not None:
                lines.append(f"- ROI: **{B.roi*100:+.2f}%**")
            if B.avg_hit_p_predicted is not None:
                lines.append(
                    f"- Hit-rate: predicted **{B.avg_hit_p_predicted*100:.2f}%**, "
                    f"actual **{B.hit_rate*100:.2f}%**"
                )
            else:
                lines.append(f"- Hit-rate: **{B.hit_rate*100:.2f}%**")
        else:
            lines.append(f"- Cutoff: **{B.cutoff}** (test pool n={B.test_n_gbm})")
            log_loss = "n/a" if B.log_loss is None else f"{B.log_loss:.4f}"
            ece = "n/a" if B.ece is None else f"{B.ece:.4f}"
            lines.append(
                f"- log-loss: **{log_loss}**, hit-rate: **{B.hit_rate*100:.2f}%**, "
                f"ECE: **{ece}**"
            )
        lines.append("")
        lines.append("## Gap")
        lines.append("")
        if report.roi_gap_pp is not None:
            lines.append(f"- ROI gap (live - backtest): **{report.roi_gap_pp:+.2f} pp**")
        if report.hit_rate_gap_pp is not None:
            lines.append(f"- Hit-rate gap (live - backtest): **{report.hit_rate_gap_pp:+.2f} pp**")
        lines.append(f"- Tolerance: ±{tolerance_pp:.1f} pp")
        if report.over_tolerance:
            lines.append("- **⚠️ OVER TOLERANCE** — investigate (leakage? lucky variance? "
                         "market drift since training cutoff?)")
        else:
            lines.append("- Within tolerance — no action needed.")
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Walk-forward references compare hit-rate only; ROI-replay references "
                 "compare both ROI and hit-rate because they run the recommendation "
                 "stake model end-to-end.")
    lines.append("- A 1-3 pp gap is normal sampling noise for 4-week windows. ")
    lines.append("- See `docs/v5_w8_observation_loop.md` for the full observation pipeline.")
    return "\n".join(lines)


def run(
    db_path: str,
    *,
    weeks: int,
    backtest_pooled: dict[str, Any] | None,
    backtest_cutoff: str | None,
    snapshot_phase: str | None = None,
    as_of: datetime | None = None,
    live_model_arm: str | None = None,
    roi_backtest_db: str | Path | None = None,
    roi_backtest_arm: str = "lineup_aware",
    tolerance_pp: float = LIVE_BACKTEST_TOLERANCE_PCT_POINTS,
) -> GapReport:
    """End-to-end helper. Loads live slice from db, pairs with backtest dict
    (typically the ``pooled`` field of a walk_forward result), and returns
    the GapReport. The caller decides what to do with `report.over_tolerance`.
    """
    start_iso, end_iso = _window_bounds(weeks, as_of=as_of)
    with open_db(db_path) as conn:
        live = slice_live_settled(
            conn,
            start_iso=start_iso,
            end_iso=end_iso,
            snapshot_phase=snapshot_phase,
            model_arm=live_model_arm,
        )
    backtest: BacktestSlice | None
    if roi_backtest_db is not None:
        backtest = roi_backtest_slice_from_db(roi_backtest_db, arm=roi_backtest_arm)
    elif backtest_pooled is not None:
        backtest = backtest_slice_from_pooled(backtest_pooled, backtest_cutoff or "")
    else:
        backtest = None
    return compute_gap(live, backtest, tolerance_pp=tolerance_pp)


__all__ = [
    "LIVE_BACKTEST_TOLERANCE_PCT_POINTS",
    "LiveSlice",
    "BacktestSlice",
    "GapReport",
    "slice_live_settled",
    "backtest_slice_from_pooled",
    "roi_backtest_slice_from_db",
    "compute_gap",
    "format_report",
    "run",
]
