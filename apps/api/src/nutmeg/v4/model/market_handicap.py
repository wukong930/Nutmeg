"""V12 W8 — market-implied 让球 (handicap) from Pinnacle 1X2 + over/under.

Fits a Dixon-Coles goal grid to BOTH the de-vigged Pinnacle 1X2 AND the
Pinnacle over/under line, then reads off any integer handicap line's
让胜/让平/让负 probabilities. Pure market — no model.

Why this exists
---------------
竞彩 让球 is a 3-way European handicap on an integer line (−1 = 主队让1球).
Computing it needs a goal-margin distribution. The production CatBoost model
is out-of-distribution for J1 + cups (the cup ablation was negative; J1
diverges ~13pp from the sharp line). So for those surfaces we DON'T use the
model — we reverse-engineer the goal distribution from two sharp Pinnacle
markets:

  - de-vig 1X2          → pins λ_diff = λ_home − λ_away (the supremacy)
  - de-vig over/under   → pins λ_total = λ_home + λ_away (the goal level)

Two anchors uniquely determine (λ_home, λ_away); the DC grid then gives every
handicap line. When the O/U is missing we fall back to a 1X2-only fit (the
draw rate weakly constrains the total — empirically within ~1pp on the
handicap, slightly optimistic on the favourite's 让胜).

Distinct from ``national_team_handicap.lambdas_from_1x2``, which FIXES
λ_total at a constant prior (WC had no reliable O/U). Anchoring λ_total to
the actual O/U is what makes this accurate.

Validation
----------
Fit only to 1X2 + O/U, the resulting grid reproduces Pinnacle's OWN Asian
Handicap cover probability within ~1pp across a full J1 matchday (the AH line
was held out, never fitted) — i.e. Pinnacle's own money agrees with the
reverse-mapped goal distribution. See tests/v4/test_market_handicap.py.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    grid_to_margin_bands,
    score_grid,
)

# Production DC low-score correction (matches gbm_rho default).
DEFAULT_RHO = -0.10
# Score-grid truncation. Goals >9 are vanishingly rare; 10 is ample headroom
# for blowouts (the 让胜 tail) while keeping the fit fast.
DEFAULT_MAX_GOALS = 10
# Integer handicap lines 竞彩 offers (主队 −3..+3). −1 = 主队让1球.
DEFAULT_LINES = tuple(range(-3, 4))

# Loss weights. The 1X2 is the sharper, lower-vig market, so weight matching
# it above the O/U. These reproduce the ~1pp AH cross-check (see module docstring).
_W_1X2 = 4.0
_W_OU = 2.0

# Fit search domain. λ outside [0.2, 3.4] is unphysical for a single team's
# expected goals; the bounds keep score_grid's λ>0 precondition satisfied.
_LAMBDA_BOUNDS = (0.2, 3.4)
_LAMBDA_X0 = (1.20, 1.05)


def devig_over(odds_over, odds_under) -> float | None:
    """2-way de-vig of an over/under pair → P(over). None if either leg is
    missing or non-positive (caller then fits 1X2-only).

    DELIBERATELY basic normalization (the 1X2 de-vig is WPO; this stays basic) —
    don't "fix" the inconsistency. MEASURED 2026-06-26 on 23,840 football-data
    Pinnacle-closing matches: routing this through WPO shifts the reconstructed
    让球 P by ~0.05pp median (p99 0.22pp, max 0.71pp on the most lopsided totals)
    with ZERO calibration change (3-way logloss Δ=−6e-6, paired-bootstrap 95% CI
    [−2e-5,+1e-5] straddles 0). 0.05pp P ≈ 0.1pp EV vs the +5% bar → ~50× too
    small to flip any pick. The O/U leg only nudges λ_total (2nd-order for
    integer-line cover); the already-WPO 1X2 split dominates. See
    docs/devig_method_comparison.md §5."""
    try:
        o = float(odds_over)
        u = float(odds_under)
    except (TypeError, ValueError):
        return None
    if not (o > 1.0 and u > 1.0):
        return None
    inv_o, inv_u = 1.0 / o, 1.0 / u
    return inv_o / (inv_o + inv_u)


def asian_total_over_prob(grid: np.ndarray, line: float) -> float:
    """P(over) at any Asian total ``line`` from a Dixon-Coles score grid,
    counting a push (stake refunded) as half a win.

    Handles the three Asian-line families 竞彩/Pinnacle actually quote:

      - half line  (…, 2.5, 3.5): no push — ``P(total > line)``.
      - whole line (…, 2.0, 3.0): pushes when ``total == line`` — adds
        ``0.5·P(==line)``.
      - quarter line (…, 2.25, 2.75): the stake splits 50/50 across the two
        neighbouring lines (2.25 = ½·2.0 + ½·2.5), so the over prob is the mean
        of those two single-line values.

    Why this matters: :func:`fit_lambdas` anchors λ_total to this number.
    Treating a 2.25 line as a 2.5 line (the old hard-coded assumption) biases
    λ_total high — on a typical J1 total by ~+0.22 goals, shifting the 让球 P by
    ~1pp. The push-as-half convention makes ``over + under == 1`` at every line,
    consistent with the 2-way de-vig in :func:`devig_over`.

    Reduces EXACTLY to ``grid_to_over_under(grid, line)[0]`` at half lines, so
    the default-2.5 serving path is unchanged.
    """
    tot: dict[int, float] = {}
    n = grid.shape[0]
    for i in range(n):
        for j in range(n):
            tot[i + j] = tot.get(i + j, 0.0) + float(grid[i, j])

    def _single(ell: float) -> float:
        # A push (total == ell, only possible at whole lines) counts as half.
        return sum(
            p * (1.0 if k > ell else 0.5 if k == ell else 0.0)
            for k, p in tot.items()
        )

    frac = line - math.floor(line)
    if abs(frac - 0.25) < 1e-9 or abs(frac - 0.75) < 1e-9:
        return 0.5 * _single(line - 0.25) + 0.5 * _single(line + 0.25)
    return _single(line)


def fit_lambdas(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> tuple[float, float]:
    """Fit (λ_home, λ_away) so the DC grid reproduces the de-vig 1X2 — and the
    de-vig P(over) at ``ou_line`` when provided.

    Returns a positive (λ_home, λ_away) pair. ``p_over`` None → 1X2-only fit.
    """
    th = np.array([p_home, p_draw, p_away], dtype=float)
    s = th.sum()
    if s <= 0:
        raise ValueError("1X2 probabilities sum to zero")
    th = th / s

    def loss(x: np.ndarray) -> float:
        lh, la = float(x[0]), float(x[1])
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        ph, pd_, pa = grid_to_1x2(grid)
        err = _W_1X2 * ((ph - th[0]) ** 2 + (pd_ - th[1]) ** 2 + (pa - th[2]) ** 2)
        if p_over is not None:
            over = asian_total_over_prob(grid, ou_line)
            err += _W_OU * (over - p_over) ** 2
        return float(err)

    res = minimize(
        loss,
        x0=np.array(_LAMBDA_X0, dtype=float),
        method="L-BFGS-B",
        bounds=[_LAMBDA_BOUNDS, _LAMBDA_BOUNDS],
    )
    return float(res.x[0]), float(res.x[1])


def implied_handicap_lines(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    lines=DEFAULT_LINES,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> list[tuple[int, float, float, float]]:
    """Fit the goal grid once, then return ``(line, P让胜, P让平, P让负)`` for
    each integer handicap line.

    ``line`` is ``handicap_home`` in DC convention (added to home's score):
    −1 = 主队让1球, +1 = 主队受让1球. The triple is
    (P(home covers), P(push), P(away covers)).
    """
    lh, la = fit_lambdas(
        p_home, p_draw, p_away, p_over,
        ou_line=ou_line, rho=rho, max_goals=max_goals,
    )
    grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
    out: list[tuple[int, float, float, float]] = []
    for line in lines:
        ph, pd_, pa = grid_to_handicap_1x2(grid, handicap_home=int(line))
        out.append((int(line), float(ph), float(pd_), float(pa)))
    return out


def implied_margin_bands(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
    tail: int = 4,
    top: int = 4,
) -> list[dict]:
    """净胜球分组 (goal-margin bands) from the SAME fit as ``implied_handicap_lines``
    (de-vig 1X2 + O/U → Dixon-Coles grid). Returns ``grid_to_margin_bands`` with
    each band's ``scores`` capped at ``top``.

    READOUT only — a 1500-fixture eval showed feeding the Asian Handicap INTO the
    fit adds ~0 info (the grid already reproduces the AH curve to ~1.5pp). ``tail=4``
    so every 竞彩 让球 line (−3..+3) classifies exactly into 让胜/让平/让负."""
    lh, la = fit_lambdas(
        p_home, p_draw, p_away, p_over, ou_line=ou_line, rho=rho, max_goals=max_goals,
    )
    bands = grid_to_margin_bands(score_grid(lh, la, rho=rho, max_goals=max_goals), tail=tail)
    for b in bands:
        b["scores"] = b["scores"][:top]
    return bands


# ── International Asian Handicap (HALF-line, 2-way: cover / not, NO push) ──────
# 竞彩 让球 (implied_handicap_lines above) is a 3-way INTEGER market (主胜/平/负
# after the line). The INTERNATIONAL / Pinnacle handicap is a 2-way HALF-line
# (主 -0.5 / -1.5 …): home covers OR away covers, no 让平. This is the line
# Polymarket-style "win by N+" markets map to. We price it two ways:
#   - REAL: de-vig the actual Pinnacle Asian-Handicap 2-way quote (most accurate)
#   - FALLBACK: read P(home covers) straight off the DC grid (when not quoted)

DEFAULT_AH_LINES = (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)


def devig_asian_handicap_line(home_odd, away_odd) -> tuple[float, float] | None:
    """De-vig ONE 2-way Asian-handicap line → (P(home covers), P(away covers)).

    The pair sums to 1 (a half-line has no push). Returns None for junk odds
    (≤ 1.0 or non-numeric) so callers fall back to the DC grid.
    """
    try:
        h, a = float(home_odd), float(away_odd)
    except (TypeError, ValueError):
        return None
    if h <= 1.0 or a <= 1.0:
        return None
    ih, ia = 1.0 / h, 1.0 / a
    s = ih + ia
    if s <= 0:
        return None
    return ih / s, ia / s


def dc_home_cover_prob(grid: np.ndarray, line: float) -> float:
    """P(home covers) at home-handicap ``line`` from a DC grid (half-line, no push).

    Home covers iff ``(home_goals − away_goals) + line > 0``. ``line`` is the
    home handicap: −0.5 ⇒ home must win; +0.5 ⇒ home win-or-draw; −1.5 ⇒ home
    wins by ≥ 2. For a half-line the margin can never tie the line, so there is
    no push and ``P(away covers) = 1 − P(home covers)``.
    """
    n = grid.shape[0]
    idx = np.arange(n)
    margin = idx[:, None] - idx[None, :]          # margin[i, j] = i − j
    return float(grid[(margin + line) > 0.0].sum())


def asian_handicap_board(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over: float | None = None,
    *,
    real_board: dict[float, dict[str, float]] | None = None,
    deep_lines=(-2.5, -1.5, 1.5, 2.5),
    ou_line: float = 2.5,
    rho: float = DEFAULT_RHO,
    max_goals: int = DEFAULT_MAX_GOALS,
) -> list[tuple[float, float, float, str]]:
    """International AH board: ``(line, P(home covers), P(away covers), source)``.

    Mirrors what Pinnacle actually shows. EVERY line Pinnacle quotes — level 0,
    quarter ±0.25/±0.75, half ±0.5, integer ±1, … — is de-vigged straight off
    its odds (``source="mkt"``), so the board lines up 1:1 with the Pinnacle page
    (which headlines 0 / ±0.25 for even matches, not just half-lines). The deep
    half-lines ``deep_lines`` (±1.5/±2.5, for Polymarket "win by N+") are filled
    off the DC grid (``"dc"``) when Pinnacle doesn't quote them. With NO real AH
    at all, the whole board falls back to the DC half-line ladder.

    ``real_board`` shape: ``{line: {"home": odd, "away": odd}}`` (line = home
    handicap; e.g. from ``odds_parser.extract_asian_handicap``). The DC grid is
    fitted to the de-vig 1X2 (+ O/U) — the SAME anchor as the 1X2 board.
    """
    out: dict[float, tuple[float, float, str]] = {}
    if real_board:
        for ln, q in real_board.items():
            dv = devig_asian_handicap_line(q.get("home"), q.get("away"))
            if dv is not None:
                out[float(ln)] = (dv[0], dv[1], "mkt")
    # DC fill: just the deep Polymarket lines when Pinnacle quoted SOMETHING;
    # the whole half-line ladder when it quoted nothing.
    fill = (
        [float(x) for x in deep_lines if float(x) not in out]
        if out else list(DEFAULT_AH_LINES)
    )
    if fill:
        lh, la = fit_lambdas(
            p_home, p_draw, p_away, p_over,
            ou_line=ou_line, rho=rho, max_goals=max_goals,
        )
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        for line in fill:
            ph = dc_home_cover_prob(grid, line)
            out[line] = (ph, 1.0 - ph, "dc")
    return [(ln, float(out[ln][0]), float(out[ln][1]), out[ln][2]) for ln in sorted(out)]


__all__ = [
    "DEFAULT_RHO",
    "DEFAULT_MAX_GOALS",
    "DEFAULT_LINES",
    "DEFAULT_AH_LINES",
    "devig_over",
    "asian_total_over_prob",
    "fit_lambdas",
    "implied_handicap_lines",
    "devig_asian_handicap_line",
    "dc_home_cover_prob",
    "asian_handicap_board",
]
