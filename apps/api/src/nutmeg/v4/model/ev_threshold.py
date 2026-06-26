"""B2 — the +EV bar as a FUNCTION of the outcome's fair P (variance-adjusted),
not a flat +5% constant.

Motivation (measured, docs/ev_threshold_variance_2026-06-26.md): EV = P·SP − 1
⇒ σ_EV = SP·σ_P. The de-vig fair-P estimate has σ_P ≈ const (~1–1.5pp at 竞彩's
freeze gap), so a longshot's +EV carries ~1/P× (= SP×) the uncertainty of a
sweet-spot pick. To hold "true EV > 0" confidence CONSTANT across the
probability range, the bar must rise for low P (high SP):

    threshold(P) = base + z · σ_P · league_factor · SP      (SP defaults to 1/P)

Measured calibration (28k Pinnacle 1X2 open→close + odds_snapshots line history):
  - σ_P ≈ 1.2pp at 竞彩's 12–24h freeze gap (range 0.4pp near-close … 2.5pp open).
  - league_factor spread only 1.39× (soft/lower leagues noisier, ~2.3pp vs ~1.7pp).
  - ⇒ sweet (SP~2.5) bar ~8%, deep longshot (SP~12.5) bar ~20% at z=1.

STATUS: pure spec only — NOT wired into the live +EV gate (that is a deliberate
betting-rule change). The dashboard shows this side-by-side with the flat 5% so
the cost of the flat bar on longshots is visible.
"""
from __future__ import annotations

# Measured defaults — see the doc above. Override per call as data sharpens.
BASE_THRESHOLD = 0.05      # the legacy flat +5% bar
SIGMA_P = 0.012            # σ of the de-vig fair-P estimate at 竞彩 freeze (~1.2pp)
Z_CONFIDENCE = 1.0         # one-sided multiplier (1.0≈84%, 1.65≈95%) for true-EV>0


def variance_adjusted_threshold(
    p: float,
    sp: float | None = None,
    *,
    base: float = BASE_THRESHOLD,
    sigma_p: float = SIGMA_P,
    z: float = Z_CONFIDENCE,
    league_factor: float = 1.0,
) -> float:
    """EV threshold for an outcome with fair probability ``p`` (and optional
    actual 竞彩 ``sp`` — defaults to the fair odds 1/p). Returns an EV fraction
    (e.g. 0.08 = +8%). Rises for longshots because σ_EV = σ_P·SP.

    A non-probability ``p`` (≤0 or ≥1) falls back to the flat ``base`` — no SP to
    amplify. ``league_factor`` is the per-league σ_P multiplier (~0.85–1.2)."""
    if not (0.0 < p < 1.0):
        return base
    if sp is None:
        sp = 1.0 / p
    return base + z * sigma_p * league_factor * sp
