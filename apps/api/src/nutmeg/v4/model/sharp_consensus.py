"""V14 — sharp-book consensus + cross-check guard (read-only, research).

We benchmark 竞彩 against Pinnacle's de-vig fair P. This module adds two more
SHARP books that are ALREADY in the same API-Football /odds envelope we cache
for Pinnacle — no new data source, no extra API calls, just parse more:

  - Pinnacle (id 4)   — the sharp price-maker (our current benchmark)
  - Betfair  (id 3)   — the exchange (crowd + sharp consensus, razor-thin margin)
  - SBOBET   (id 5)   — a sharp Asian book

Goal is NOT to average soft books in (that would dilute Pinnacle with lagged,
margin-shaded followers). It is to:
  1. build a SHARP-only consensus fair P (mean of the present sharps), and
  2. surface DISAGREEMENT as a staleness/anomaly guard — if Pinnacle disagrees
     with the other sharps on the favourite by a MATERIAL margin (a "favorite
     flip"; see FLIP_MARGIN — a near-pick'em argmax split does NOT count), that
     fixture's Pinnacle line is suspect (stale, or missing news) and its EV read
     should be downgraded. Same philosophy as the Polymarket detector's
     favorite-flip guard and the Australia-vs-Switzerland anomaly we caught.

All pure functions — de-vig is the SERVING method (WPO via
``nutmeg.v4.model.devig``), so the consensus/guard compares like with like.
"""
from __future__ import annotations

from dataclasses import dataclass

from nutmeg.v4.data.odds_parser import extract_1x2_odds
from nutmeg.v4.model.devig import devig_1x2 as _wpo_devig_1x2

# API-Football bookmaker ids for the three sharp sources (verified from cache).
SHARP_BOOKS: dict[str, int] = {"pinnacle": 4, "betfair": 3, "sbobet": 5}
_OUTCOMES = ("H", "D", "A")

# V14.1 — favourite-flip minimum margin. A "flip" only counts when BOTH Pinnacle
# and the other-sharp consensus prefer their (differing) favourite by at least
# this much over the contested rival — otherwise a near-pick'em (H≈A) trips the
# bare argmax on pure rounding noise. MEASURED on 3,306 settled cached fixtures:
# τ=0 → 113 flips; τ=2pp → 34 flips (−70%, all the pick'em noise) with the
# guard's signal intact (flagged-subset Pinnacle log-loss 1.08 vs 0.95 baseline,
# same as τ=0). 2pp is the knee. Mirrors the Polymarket detector's near-even guard.
FLIP_MARGIN = 0.02


def devig_1x2(odds: dict[str, float]) -> dict[str, float]:
    """{H,D,A} decimal odds → de-vig fair probabilities, SAME method as serving
    (WPO). 体检 Wave3 (P2) — this was the codebase's THIRD independent basic
    (multiplicative) de-vig: basic overprices longshots vs WPO by enough to
    flip a cold-side EV sign, so the guard/eval was judging Pinnacle against a
    P the serving path never produces. Falls back to basic normalization only
    if WPO rejects the triple (degenerate odds — extract_1x2_odds already
    filters ≤1.0, so this is a belt-and-braces path)."""
    p = _wpo_devig_1x2(odds["H"], odds["D"], odds["A"])
    if p is not None:
        return {"H": p[0], "D": p[1], "A": p[2]}
    inv = {k: 1.0 / odds[k] for k in _OUTCOMES}
    s = sum(inv.values())
    return {k: inv[k] / s for k in _OUTCOMES}


def _argmax(p: dict[str, float]) -> str:
    return max(_OUTCOMES, key=lambda k: p[k])


@dataclass(frozen=True)
class Consensus:
    """Sharp consensus + agreement diagnostics for one fixture's 1X2."""
    consensus: dict[str, float] | None  # mean fair P over present sharps, or None
    by_book: dict[str, dict[str, float]]  # {book: {H,D,A} fair P}
    books_present: tuple[str, ...]
    n_books: int
    argmax_agree: bool   # all present sharps agree on the favourite outcome
    max_spread: float    # max over H/D/A of (max book P − min book P)
    pinnacle_flip: bool  # Pinnacle present + ≥1 other, and Pinnacle's favourite
    #                      disagrees with the other sharps' consensus favourite


def per_book_fair(
    envelope: dict, books: dict[str, int] = SHARP_BOOKS,
) -> dict[str, dict[str, float]]:
    """Extract + de-vig each sharp book present in the /odds envelope."""
    out: dict[str, dict[str, float]] = {}
    for name, bid in books.items():
        odds = extract_1x2_odds(envelope, bid)
        if odds:
            out[name] = devig_1x2(odds)
    return out


def consensus(by_book: dict[str, dict[str, float]]) -> Consensus:
    """Combine the present sharp books into a consensus fair P + diagnostics."""
    present = tuple(sorted(by_book))
    if not present:
        return Consensus(None, {}, (), 0, False, 0.0, False)

    cons = {k: sum(by_book[b][k] for b in present) / len(present) for k in _OUTCOMES}
    s = sum(cons.values())  # mean of unit-sum vectors already sums to 1; float safety
    cons = {k: cons[k] / s for k in _OUTCOMES}

    argmaxes = {_argmax(by_book[b]) for b in present}
    agree = len(argmaxes) == 1
    spread = max(
        max(by_book[b][k] for b in present) - min(by_book[b][k] for b in present)
        for k in _OUTCOMES
    )

    flip = False
    if "pinnacle" in by_book and len(present) >= 2:
        others = [b for b in present if b != "pinnacle"]
        other_cons = {k: sum(by_book[b][k] for b in others) / len(others) for k in _OUTCOMES}
        pin_fav, oth_fav = _argmax(by_book["pinnacle"]), _argmax(other_cons)
        # A favourite disagreement only counts when it is MATERIAL — both sides
        # must name their (differing) favourite by ≥ FLIP_MARGIN over the
        # contested rival. Near-pick'em matches (H≈A within ~1pp) otherwise trip
        # the bare argmax on rounding noise while all sharps price identically
        # (Ulsan-Jeonbuk: books agreed to 1.0pp yet argmax-flipped). See FLIP_MARGIN.
        if pin_fav != oth_fav:
            flip = min(
                by_book["pinnacle"][pin_fav] - by_book["pinnacle"][oth_fav],
                other_cons[oth_fav] - other_cons[pin_fav],
            ) >= FLIP_MARGIN

    return Consensus(cons, dict(by_book), present, len(present), agree, spread, flip)


def consensus_for_envelope(envelope: dict) -> Consensus:
    """Convenience: /odds envelope → Consensus (extract + de-vig + combine)."""
    return consensus(per_book_fair(envelope))


def ev_1x2(fair: dict[str, float], jc_sp: dict[str, float]) -> dict[str, float]:
    """EV per outcome = fair_P × 竞彩SP − 1, for outcomes with a 竞彩 SP > 1."""
    out: dict[str, float] = {}
    for k in _OUTCOMES:
        o = jc_sp.get(k)
        if o and o > 1.0:
            out[k] = fair[k] * o - 1.0
    return out
