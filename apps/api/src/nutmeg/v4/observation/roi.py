"""ROI / performance aggregation from the observation DB.

Computes:
  - Headline: total stake, total payout, profit/loss, ROI, hit rate
  - By k_legs: how does 2-串-1 perform vs 8-串-1?
  - By league: where is the model finding alpha vs losing?
  - Calibration: hit_probability bin → actual hit rate
  - Time series: weekly cumulative P/L

All read-only; no mutation of the DB.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class HeadlineStats:
    n_settled: int
    n_hit: int          # hit == 1 (full hit)
    n_partial: int      # hit == -1 (复式 partial hit)
    n_miss: int
    total_stake: float
    total_payout: float
    profit_loss: float
    roi: float          # profit_loss / total_stake
    avg_hit_p_predicted: float
    actual_hit_rate: float


def _safe_div(a: float, b: float) -> float:
    return a / b if b > 0 else 0.0


def compute_headline(conn: sqlite3.Connection) -> HeadlineStats:
    cur = conn.execute(
        """SELECT s.hit, s.stake, s.actual_payout, s.profit_loss, p.hit_probability
           FROM settlements s JOIN parlay_recommendations p ON s.rec_id = p.rec_id"""
    )
    rows = cur.fetchall()
    n_settled = len(rows)
    n_hit = sum(1 for r in rows if r["hit"] == 1)
    n_partial = sum(1 for r in rows if r["hit"] == -1)
    n_miss = sum(1 for r in rows if r["hit"] == 0)
    total_stake = sum(r["stake"] for r in rows)
    total_payout = sum(r["actual_payout"] for r in rows)
    profit_loss = total_payout - total_stake
    avg_hit_p = sum(r["hit_probability"] for r in rows) / n_settled if n_settled else 0
    actual_hit_rate = (n_hit + 0.5 * n_partial) / n_settled if n_settled else 0
    return HeadlineStats(
        n_settled=n_settled,
        n_hit=n_hit,
        n_partial=n_partial,
        n_miss=n_miss,
        total_stake=total_stake,
        total_payout=total_payout,
        profit_loss=profit_loss,
        roi=_safe_div(profit_loss, total_stake),
        avg_hit_p_predicted=avg_hit_p,
        actual_hit_rate=actual_hit_rate,
    )


def group_by_k_legs(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        """SELECT p.k_legs,
                  COUNT(*)        AS n,
                  SUM(s.hit = 1)  AS n_hit,
                  SUM(s.stake)    AS stake,
                  SUM(s.actual_payout) AS payout,
                  SUM(s.profit_loss)   AS pl,
                  AVG(p.hit_probability) AS avg_hit_p
           FROM settlements s
           JOIN parlay_recommendations p ON s.rec_id = p.rec_id
           GROUP BY p.k_legs
           ORDER BY p.k_legs"""
    )
    return [dict(r) for r in cur.fetchall()]


def group_by_league(conn: sqlite3.Connection) -> list[dict]:
    """Attribute settlements to leagues via the leg with the LARGEST contribution.

    Heuristic: a parlay's "primary league" is the league of its first leg.
    For more nuanced attribution we'd need per-leg accounting.
    """
    # Pull all settled parlays + their legs; derive league per parlay
    cur = conn.execute(
        """SELECT p.rec_id, p.legs_json, s.hit, s.stake, s.actual_payout, s.profit_loss
           FROM settlements s JOIN parlay_recommendations p ON s.rec_id = p.rec_id"""
    )
    by_league: dict[str, dict] = defaultdict(lambda: {"n": 0, "n_hit": 0, "stake": 0.0,
                                                        "payout": 0.0, "pl": 0.0})
    for r in cur.fetchall():
        legs = json.loads(r["legs_json"])
        if not legs:
            continue
        # First leg's match_id starts with "{league}_"; parse it
        first_mid = legs[0]["match_id"]
        # league = the part before "_{home_team}_vs_{away_team}"
        league = first_mid.split("_vs_")[0].rsplit("_", 1)[0] if "_vs_" in first_mid else "UNKNOWN"
        by_league[league]["n"] += 1
        by_league[league]["n_hit"] += (1 if r["hit"] == 1 else 0)
        by_league[league]["stake"] += r["stake"]
        by_league[league]["payout"] += r["actual_payout"]
        by_league[league]["pl"] += r["profit_loss"]
    out = []
    for lg, v in sorted(by_league.items(), key=lambda kv: -kv[1]["pl"]):
        out.append({
            "league": lg,
            "n": v["n"],
            "n_hit": v["n_hit"],
            "hit_rate": _safe_div(v["n_hit"], v["n"]),
            "stake": v["stake"],
            "payout": v["payout"],
            "pl": v["pl"],
            "roi": _safe_div(v["pl"], v["stake"]),
        })
    return out


def calibration_buckets(conn: sqlite3.Connection, n_bins: int = 5) -> list[dict]:
    """Compare predicted hit_probability vs actual outcome."""
    cur = conn.execute(
        """SELECT p.hit_probability, s.hit
           FROM settlements s JOIN parlay_recommendations p ON s.rec_id = p.rec_id"""
    )
    rows = cur.fetchall()
    # Equal-width bins on hit_probability
    width = 1.0 / n_bins
    bins: list[dict[str, Any]] = [
        {"lo": i * width, "hi": (i + 1) * width, "n": 0, "n_hit": 0, "sum_pred": 0.0}
        for i in range(n_bins)
    ]
    for r in rows:
        hp = float(r["hit_probability"])
        idx = min(int(hp / width), n_bins - 1)
        bins[idx]["n"] += 1
        bins[idx]["n_hit"] += (1 if r["hit"] == 1 else 0)
        bins[idx]["sum_pred"] += hp
    out = []
    for b in bins:
        if b["n"] == 0:
            continue
        out.append({
            "bin_lo": b["lo"],
            "bin_hi": b["hi"],
            "n": b["n"],
            "avg_predicted": b["sum_pred"] / b["n"],
            "actual_hit_rate": b["n_hit"] / b["n"],
        })
    return out


def weekly_pl(conn: sqlite3.Connection) -> list[dict]:
    """Group settlements by ISO week → cumulative P/L."""
    cur = conn.execute(
        """SELECT sess.created_at AS session_at, s.profit_loss, s.stake
           FROM settlements s
           JOIN parlay_recommendations p ON s.rec_id = p.rec_id
           JOIN recommendation_sessions sess ON p.session_id = sess.session_id
           ORDER BY sess.created_at"""
    )
    weekly: dict[str, dict] = defaultdict(lambda: {"n": 0, "stake": 0.0, "pl": 0.0})
    for r in cur.fetchall():
        try:
            dt = datetime.fromisoformat(r["session_at"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        year, week, _ = dt.isocalendar()
        key = f"{year}-W{week:02d}"
        weekly[key]["n"] += 1
        weekly[key]["stake"] += r["stake"]
        weekly[key]["pl"] += r["profit_loss"]
    out = []
    cum_pl = 0.0
    for week in sorted(weekly):
        v = weekly[week]
        cum_pl += v["pl"]
        out.append({
            "week": week,
            "n": v["n"],
            "stake": v["stake"],
            "pl": v["pl"],
            "cumulative_pl": cum_pl,
            "roi": _safe_div(v["pl"], v["stake"]),
        })
    return out
