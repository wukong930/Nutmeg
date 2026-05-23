"""A/B comparison of lineup-aware vs lineup-free recommendation slices.

V6 W8 — answers the question: "across the last N weeks of settled real-bet
recommendations, did the lineup-aware artifact (`with_lineups=True` in the
session metadata blob) outperform the lineup-free default?"

The W8 cron records each recommend session with its `metadata_json`, which
embeds the artifact's `model.metadata` dict. The lineup-aware artifact
(V6 W7) sets `model.with_lineups = true` there. This module groups
settlements by that marker and produces a side-by-side ROI / hit-rate /
EV-realized report.

Implementation notes:
- We always JOIN through `recommendation_sessions AS r` and reference
  session-side columns via `r.<col>`, including in the bare COUNT(*)
  session query. Single column-namespacing rule = no string juggling.
- Predicates are built with `r.metadata_json`, `r.created_at` baked in.
- We treat sqlite3.Row outputs via index access (`row["hit"]`) — caller
  must ensure `conn.row_factory = sqlite3.Row` (the `open_db()` helper
  does this).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class ArtifactSlice:
    """ROI summary for one artifact variant."""

    label: str
    n_sessions: int
    n_settled: int
    n_hit: int
    n_partial: int
    n_miss: int
    total_stake: float
    total_payout: float
    profit_loss: float
    roi: float
    avg_hit_p_predicted: float
    actual_hit_rate: float


def _slice_for_predicate(
    conn: sqlite3.Connection,
    predicate_sql: str,
    params: tuple,
    label: str,
) -> ArtifactSlice:
    """Compute one slice. `predicate_sql` MUST use the `r.` prefix for
    session-side columns (e.g. `r.metadata_json`, `r.created_at`).

    Two queries run:
      1. session count — `recommendation_sessions AS r WHERE <predicate>`
      2. settled rows  — JOIN settlements → parlay_recommendations →
         recommendation_sessions r WHERE <predicate>
    """
    sess_count = conn.execute(
        f"SELECT COUNT(*) FROM recommendation_sessions AS r WHERE {predicate_sql}",
        params,
    ).fetchone()[0]

    rows = list(conn.execute(
        f"""
        SELECT s.hit, s.stake, s.actual_payout, s.profit_loss, p.hit_probability
        FROM settlements s
        JOIN parlay_recommendations p ON s.rec_id = p.rec_id
        JOIN recommendation_sessions r ON p.session_id = r.session_id
        WHERE {predicate_sql}
        """,
        params,
    ).fetchall())

    n_settled = len(rows)
    n_hit = sum(1 for row in rows if row["hit"] == 1)
    n_partial = sum(1 for row in rows if row["hit"] == -1)
    n_miss = sum(1 for row in rows if row["hit"] == 0)
    total_stake = sum(row["stake"] for row in rows)
    total_payout = sum(row["actual_payout"] for row in rows)
    pl = total_payout - total_stake
    avg_hit_p = sum(row["hit_probability"] for row in rows) / n_settled if n_settled else 0.0
    actual_hr = (n_hit + 0.5 * n_partial) / n_settled if n_settled else 0.0
    return ArtifactSlice(
        label=label,
        n_sessions=int(sess_count),
        n_settled=n_settled,
        n_hit=n_hit,
        n_partial=n_partial,
        n_miss=n_miss,
        total_stake=float(total_stake),
        total_payout=float(total_payout),
        profit_loss=float(pl),
        roi=pl / total_stake if total_stake > 0 else 0.0,
        avg_hit_p_predicted=avg_hit_p,
        actual_hit_rate=actual_hr,
    )


def _append_time_window(where: str, params: list, start_iso: Optional[str], end_iso: Optional[str]) -> str:
    if start_iso is not None:
        where += " AND r.created_at >= ?"
        params.append(start_iso)
    if end_iso is not None:
        where += " AND r.created_at < ?"
        params.append(end_iso)
    return where


def slice_lineup_aware(
    conn: sqlite3.Connection,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
) -> ArtifactSlice:
    """Slice for sessions where the artifact's metadata flagged with_lineups=True.

    Detected via JSON1: `json_extract(r.metadata_json, '$.model.with_lineups') = 1`.
    SQLite's json1 returns 1 for JSON true.
    """
    where = "json_extract(r.metadata_json, '$.model.with_lineups') = 1"
    params: list = []
    where = _append_time_window(where, params, start_iso, end_iso)
    return _slice_for_predicate(conn, where, tuple(params), "lineup-aware")


def slice_lineup_free(
    conn: sqlite3.Connection,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
) -> ArtifactSlice:
    """Slice for sessions WITHOUT the lineup flag (V5 W12 default behavior)."""
    where = (
        "(json_extract(r.metadata_json, '$.model.with_lineups') IS NULL"
        " OR json_extract(r.metadata_json, '$.model.with_lineups') = 0)"
    )
    params: list = []
    where = _append_time_window(where, params, start_iso, end_iso)
    return _slice_for_predicate(conn, where, tuple(params), "lineup-free")


def format_ab_card(
    free: ArtifactSlice,
    aware: ArtifactSlice,
    *,
    weeks: Optional[int] = None,
) -> str:
    """Markdown comparison table."""
    lines = []
    title_suffix = f" (last {weeks} weeks)" if weeks else ""
    lines.append(f"# A/B: lineup-free vs lineup-aware{title_suffix}")
    lines.append("")
    lines.append("| Metric | lineup-free (V5 W12 default) | lineup-aware (V6 W7) | Δ (aware − free) |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Sessions | {free.n_sessions} | {aware.n_sessions} | {aware.n_sessions - free.n_sessions:+d} |")
    lines.append(f"| Settled recs | {free.n_settled} | {aware.n_settled} | {aware.n_settled - free.n_settled:+d} |")
    lines.append(f"| Hits / Partial / Miss | {free.n_hit}/{free.n_partial}/{free.n_miss} | {aware.n_hit}/{aware.n_partial}/{aware.n_miss} | — |")
    lines.append(f"| Total stake | ¥{free.total_stake:.2f} | ¥{aware.total_stake:.2f} | ¥{aware.total_stake-free.total_stake:+.2f} |")
    lines.append(f"| Total payout | ¥{free.total_payout:.2f} | ¥{aware.total_payout:.2f} | ¥{aware.total_payout-free.total_payout:+.2f} |")
    lines.append(f"| P/L | ¥{free.profit_loss:+.2f} | ¥{aware.profit_loss:+.2f} | ¥{aware.profit_loss-free.profit_loss:+.2f} |")
    lines.append(f"| **ROI** | **{free.roi*100:+.2f}%** | **{aware.roi*100:+.2f}%** | **{(aware.roi-free.roi)*100:+.2f}pp** |")
    lines.append(f"| Predicted hit-rate | {free.avg_hit_p_predicted*100:.2f}% | {aware.avg_hit_p_predicted*100:.2f}% | {(aware.avg_hit_p_predicted-free.avg_hit_p_predicted)*100:+.2f}pp |")
    lines.append(f"| Actual hit-rate | {free.actual_hit_rate*100:.2f}% | {aware.actual_hit_rate*100:.2f}% | {(aware.actual_hit_rate-free.actual_hit_rate)*100:+.2f}pp |")
    lines.append("")

    # Interpretation hint
    if free.n_settled == 0 and aware.n_settled == 0:
        lines.append("_No settled recommendations yet — pipeline is set up but waiting on real-bet data._")
    elif free.n_settled < 30 or aware.n_settled < 30:
        lines.append("_Sample size still small (< 30 settlements on at least one side) — read the diff with caution._")
    else:
        diff = aware.roi - free.roi
        if abs(diff) < 0.02:
            lines.append("_ROI diff within ±2pp — no clear winner on this window._")
        elif diff > 0:
            lines.append(f"_lineup-aware leads by {diff*100:+.2f}pp ROI — confirms V6 W6 backtest direction._")
        else:
            lines.append(f"_lineup-free leads by {-diff*100:+.2f}pp ROI — lineup artifact may need re-evaluation._")
    return "\n".join(lines)


__all__ = [
    "ArtifactSlice",
    "slice_lineup_aware",
    "slice_lineup_free",
    "format_ab_card",
]
