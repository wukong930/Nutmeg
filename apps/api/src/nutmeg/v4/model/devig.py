"""Single source of truth for de-vigging bookmaker odds → fair probabilities.

Default = **WPO** (margin-weights-proportional-to-odds, Buchdahl): it corrects the
favourite-longshot bias (basic normalization over-states longshots) and, per
Buchdahl's 136,876-game Pinnacle closing-1X2 test, is tied-best by realized yield
with a **closed-form, zero-iteration** formula. Falls back to basic proportional
normalization if WPO ever produces an out-of-[0,1] value (extreme longshot × fat
margin — measured 0/5,234 times on real Pinnacle 1X2, so the guard is belt-and-
suspenders). See ``docs/devig_method_comparison.md``.

WPO:  p_i = (n − M·O_i) / (n·O_i),  where M = Σ(1/O_j) − 1 (the book margin), n = #outcomes.
basic: p_i = (1/O_i) / Σ(1/O_j).

SCOPE NOTE: this is for **fair-P-for-EV / analysis** (soft-water EV measurement,
dashboard EV, CLV). The MODEL-FEATURE de-vigs in ``features/market.py`` and
``features/market_dynamics.py`` deliberately STAY on basic normalization — changing
them shifts the trained model's input distribution and would require a full retrain
+ walk-forward re-validation. Don't route those through here without that.
"""
from __future__ import annotations

_VALID_METHODS = ("wpo", "basic")


def _basic(odds: list[float]) -> list[float]:
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def _wpo(odds: list[float]) -> list[float]:
    n = len(odds)
    margin = sum(1.0 / o for o in odds) - 1.0
    return [(n - margin * o) / (n * o) for o in odds]


def devig(odds, *, method: str = "wpo") -> list[float] | None:
    """Fair (de-vig) probabilities from decimal odds. ``method`` ∈ {'wpo','basic'}.
    Returns None if any odd is missing/NaN/≤1.0. WPO falls back to basic if it would
    emit an out-of-[0,1] probability."""
    try:
        odds = [float(o) for o in odds]
    except (TypeError, ValueError):
        return None
    # reject NaN (o != o) and non-decimal odds (≤ 1.0)
    if any(o != o or o <= 1.0 for o in odds):
        return None
    if method == "basic":
        return _basic(odds)
    p = _wpo(odds)
    if any(x <= 0.0 or x >= 1.0 for x in p):  # extreme longshot × fat margin
        return _basic(odds)
    return p


def devig_1x2(h, d, a, *, method: str = "wpo") -> tuple[float, float, float] | None:
    """3-way convenience wrapper → (p_home, p_draw, p_away) or None."""
    if h is None or d is None or a is None:
        return None
    p = devig([h, d, a], method=method)
    return (p[0], p[1], p[2]) if p else None
