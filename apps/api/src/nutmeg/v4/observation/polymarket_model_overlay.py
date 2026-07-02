"""Our model as an independent THIRD opinion on a Polymarket board match.

The board's core is Pinnacle-de-vig fair P vs Polymarket price. For a match in a
MODELLED competition (World Cup / the 13 trained leagues) we ALSO surface our own
CatBoost/Elo model's 1X2 — NOT as an EV input (the model doesn't beat the close;
V12 pivot), but as a low-weight third vote that TRIANGULATES the two markets:

  - model + Pinnacle agree on the favourite but Polymarket DISAGREES → Polymarket
    is the likely-mispriced side (highest research value).
  - model + Polymarket agree but Pinnacle disagrees → Pinnacle is likely
    stale/flipped (we're catching our OWN data's error).

It also breaks the favorite-flip tie the gap engine flags: when Pinnacle and
Polymarket disagree on the favourite, whom does the independent model back?

The model 1X2 is JOINED from already-logged predictions — we never re-run the
model here:
  - ``wc_predictions`` by fixture_id (the Elo+model blend; the real WC model).
  - ``league_predictions`` by (match_date, teams) but ONLY ``market_mode = 0``
    rows — a market_mode=1 row's ``p_*`` is just the Pinnacle de-vig, i.e. NOT an
    independent model, so it would be a fake third opinion (WC lands here as
    market_mode=1 → excluded; use wc_predictions for it instead).

None is returned when no real-model prediction exists (the common case for the
obscure long-tail Polymarket lists) → the card then shows only Pinnacle vs
Polymarket, exactly like the 竞彩 board's market mode.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_OUTCOME = ("H", "D", "A")


def _argmax3(p_h: float, p_d: float, p_a: float) -> str:
    trip = (p_h, p_d, p_a)
    return _OUTCOME[max(range(3), key=lambda i: trip[i])]


def fetch_model_1x2(
    db_path: str | Path,
    *,
    fixture_id: int | None = None,
    match_date: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> tuple[float, float, float] | None:
    """(p_home, p_draw, p_away) from a logged REAL-model prediction for this match,
    or None. wc_predictions (fixture_id) first, then league_predictions
    (market_mode=0). Read-only; never raises (a missing table/DB → None)."""
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            if fixture_id is not None:
                r = conn.execute(
                    "SELECT p_home, p_draw, p_away FROM wc_predictions "
                    "WHERE fixture_id=? AND p_home IS NOT NULL "
                    "ORDER BY recorded_at DESC LIMIT 1", (fixture_id,)).fetchone()
                if r is not None:
                    return (float(r["p_home"]), float(r["p_draw"]), float(r["p_away"]))
            if match_date and home_team and away_team:
                r = conn.execute(
                    "SELECT p_home, p_draw, p_away FROM league_predictions "
                    "WHERE match_date=? AND home_team=? AND away_team=? "
                    "AND market_mode=0 AND p_home IS NOT NULL "
                    "ORDER BY recorded_at DESC LIMIT 1",
                    (match_date, home_team, away_team)).fetchone()
                if r is not None:
                    return (float(r["p_home"]), float(r["p_draw"]), float(r["p_away"]))
    except Exception:  # noqa: BLE001 — overlay is optional; a bad read must not break the board
        log.debug("model-overlay lookup failed for fixture=%s", fixture_id, exc_info=True)
    return None


@dataclass(frozen=True)
class Triangulation:
    model_1x2: tuple[float, float, float] | None
    model_argmax: str | None         # H|D|A|None
    pinnacle_argmax: str             # H|D|A
    polymarket_argmax: str | None    # H|D|A|None (needs all three moneyline asks)
    consensus_vs_poly_diverge: bool  # model & Pinnacle agree, Polymarket disagrees
    flip_backer: str | None          # on a Pinnacle↔Polymarket flip: "pinnacle"|"polymarket"|None
    all_three_agree: bool


def triangulate(
    pinnacle_1x2: tuple[float, float, float],
    poly_moneyline_asks: dict[str, float | None],
    model_1x2: tuple[float, float, float] | None,
) -> Triangulation:
    """Three-way favourite agreement. ``poly_moneyline_asks`` = {"H":ask,"D":ask,
    "A":ask} (a Polymarket YES price ≈ implied prob, so the highest ask = its
    favourite). Model absent → the model-derived flags are False/None (card shows
    Pinnacle vs Polymarket only)."""
    pinn_am = _argmax3(*pinnacle_1x2)
    poly_am: str | None = None
    if poly_moneyline_asks and all(
        poly_moneyline_asks.get(k) is not None for k in ("H", "D", "A")
    ):
        poly_am = _argmax3(
            poly_moneyline_asks["H"], poly_moneyline_asks["D"], poly_moneyline_asks["A"])
    model_am = _argmax3(*model_1x2) if model_1x2 else None

    diverge = bool(model_am and poly_am and model_am == pinn_am and poly_am != pinn_am)
    flip_backer: str | None = None
    if model_am and poly_am and poly_am != pinn_am:  # Pinnacle ↔ Polymarket flip
        if model_am == pinn_am:
            flip_backer = "pinnacle"
        elif model_am == poly_am:
            flip_backer = "polymarket"
    all_agree = bool(model_am and poly_am and model_am == pinn_am == poly_am)
    return Triangulation(
        model_1x2=model_1x2, model_argmax=model_am, pinnacle_argmax=pinn_am,
        polymarket_argmax=poly_am, consensus_vs_poly_diverge=diverge,
        flip_backer=flip_backer, all_three_agree=all_agree,
    )


__all__ = ["Triangulation", "fetch_model_1x2", "triangulate"]
