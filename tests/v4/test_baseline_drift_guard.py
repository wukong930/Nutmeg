"""AUDIT FIX (R2) — pooled-metric drift guard on the real backtest holdout.

The V12 audit found the golden pooled log-loss was NOT pinned by ANY test, while
bench.py overwrites the baseline card with no threshold — so a model regression
would be silently baked into the card (the card was in fact dirty in the tree at
audit time, having dropped rows). That makes "the model still works" an unchecked
assumption.

This pins the production model's pooled 1X2 log-loss on the committed backtest
holdout: data/v4_observation_backtest.db, where single_predictions (the model's
stored 1X2 probabilities) are scored against match_outcomes (actual 90' goals).
A model swap or feature-pipeline change that regenerates the backtest worse than
the ship threshold trips this test instead of slipping silently into the card.

Skips (never fails) when the backtest DB is absent — it is a local data artifact,
so the guard runs wherever the DB exists (the user's local verification suite).
"""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

_DB = Path(__file__).resolve().parents[2] / "data" / "v4_observation_backtest.db"

# Golden pooled 1X2 log-loss on this holdout, measured 2026-06-03 (V12 audit R2).
# Two-sided pin: a regenerated backtest must stay within ±5 milli-pt — the same
# order as the Layer B ship gate's min_log_loss_gain — else re-pin deliberately
# after reviewing why it moved.
_GOLDEN_LOG_LOSS = 0.9670
_TOL = 0.005

# The baseline card (bench.py rewrites it with NO threshold). Pin the production
# model's pooled log-loss row so a silent regeneration that drops or degrades it
# fails CI — at audit time the working-tree card had in fact dropped this row.
# Unlike the backtest-DB guard above, the card is tracked, so this runs in CI.
_CARD = Path(__file__).resolve().parents[2] / "docs" / "v4_baseline_card.md"
_CARD_GOLDEN = {
    "Pinnacle closing (baseline)": 0.9942,  # the sharp benchmark
    "V5 CatBoost + DC": 0.9960,             # PRODUCTION model (data/v4_model_cat)
}
_CARD_TOL = 0.001


def _card_pooled_log_loss(card: str, label: str) -> float | None:
    for line in card.splitlines():
        if label in line and line.lstrip().startswith("|"):
            cells = [c.strip().strip("*") for c in line.split("|") if c.strip()]
            if len(cells) >= 2:
                try:
                    return float(cells[1])
                except ValueError:
                    continue
    return None


def _pooled_log_loss(db: Path) -> tuple[float, int]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT sp.p_home_1x2 ph, sp.p_draw_1x2 pd, sp.p_away_1x2 pa,
                   mo.home_goals hg, mo.away_goals ag
            FROM single_predictions sp
            JOIN match_outcomes mo
              ON mo.match_date = sp.match_date AND mo.league = sp.league
             AND mo.home_team = sp.home_team AND mo.away_team = sp.away_team
            WHERE mo.home_goals IS NOT NULL AND mo.away_goals IS NOT NULL
              AND sp.p_home_1x2 IS NOT NULL
            """
        ).fetchall()
    finally:
        con.close()
    eps = 1e-9
    tot, n = 0.0, 0
    for r in rows:
        p = [r["ph"], r["pd"], r["pa"]]
        s = sum(p)
        if not s or abs(s - 1.0) > 0.05:  # skip malformed / non-normalised rows
            continue
        o = 0 if r["hg"] > r["ag"] else (1 if r["hg"] == r["ag"] else 2)
        tot += -math.log(max(eps, min(1 - eps, p[o])))
        n += 1
    return (tot / n if n else float("nan")), n


@pytest.mark.skipif(not _DB.exists(), reason="backtest holdout DB not present")
def test_backtest_pooled_log_loss_within_golden():
    ll, n = _pooled_log_loss(_DB)
    assert n >= 1000, f"holdout too small ({n}) to be a credible drift guard"
    assert ll < math.log(3), f"model log-loss {ll:.4f} >= uniform ln(3) — no signal"
    assert abs(ll - _GOLDEN_LOG_LOSS) <= _TOL, (
        f"pooled log-loss {ll:.4f} drifted from golden {_GOLDEN_LOG_LOSS:.4f} "
        f"(+/-{_TOL}). A model/pipeline change regenerated the backtest beyond the "
        f"ship threshold — review the baseline card, then re-pin _GOLDEN_LOG_LOSS "
        f"deliberately."
    )


def test_baseline_card_pins_production_golden():
    card = _CARD.read_text(encoding="utf-8")
    for label, golden in _CARD_GOLDEN.items():
        got = _card_pooled_log_loss(card, label)
        assert got is not None, (
            f"baseline card lost the '{label}' row — a bench.py regeneration "
            f"silently dropped the production golden (audit R2)"
        )
        assert abs(got - golden) <= _CARD_TOL, (
            f"'{label}' card log-loss {got} drifted from golden {golden} "
            f"(+/-{_CARD_TOL}) — review, then re-pin deliberately"
        )
