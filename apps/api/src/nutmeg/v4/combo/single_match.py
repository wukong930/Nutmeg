"""Single-match (单关) recommender — V6 W9.

The simplest 竞彩 product: pick one match, pick one outcome, place one
ticket. No parlay, no compound pool — just a single-leg bet sized by
fractional Kelly under the lottery's ¥2 / ¥20k / 31.5%-vig rules.

The hard part isn't the math (single-leg Kelly is the textbook case),
it's the SELECTION step: each match offers up to 6 outcomes
(1X2 × {H, D, A} + handicap_1x2 × {H, D, A}). We score them all, keep
only the candidates that pass `passes_recommendation_thresholds`, and
limit to at most `top_per_match` recommendations per match (default 1 —
don't suggest betting both home AND away on the same fixture).

Outputs are ranked by EV descending, ¥2-quantized, ¥20k-capped.

This mirrors the M-select-N pool's stake-sizing pipeline so users see
consistent stake behaviour across 单关 / 串关 / 复式.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nutmeg.v4.combo.compound_pool import quantize_stake
from nutmeg.v4.combo.kelly import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_FRACTION,
    fractional_kelly_stake,
)
from nutmeg.v4.combo.lottery_rules import (
    JINGCAI_DEFAULT,
    LotteryRules,
    cap_ticket_stake,
    passes_recommendation_thresholds,
)
from nutmeg.v4.combo.selections import (
    MatchInput,
    Selection,
    build_selections_from_match,
)


@dataclass(frozen=True)
class SingleMatchTicket:
    """One single-leg ticket: the chosen selection + sizing."""

    selection: Selection
    raw_kelly_stake: float        # pre-quantization
    stake: float                  # ¥2-quantized
    expected_return: float        # stake * (odds*p - 1)

    @property
    def hit_probability(self) -> float:
        return self.selection.probability

    @property
    def ev_per_unit(self) -> float:
        return self.selection.edge


@dataclass
class SingleMatchRecommendation:
    """Aggregated single-leg recommendation output."""

    tickets: list[SingleMatchTicket]                  # all candidates, EV desc
    selected_tickets: list[SingleMatchTicket] = field(default_factory=list)  # stake > 0
    total_stake: float = 0.0
    total_expected_return: float = 0.0


def _best_per_match(
    candidates: list[SingleMatchTicket],
    top_per_match: int,
) -> list[SingleMatchTicket]:
    """Keep at most `top_per_match` selections per fixture.

    Sorts each match's selections by EV desc and slices to top_per_match.
    Order across matches is then re-applied (EV desc globally).
    """
    if top_per_match <= 0:
        raise ValueError(f"top_per_match must be ≥ 1, got {top_per_match}")
    by_match: dict[str, list[SingleMatchTicket]] = {}
    for t in candidates:
        by_match.setdefault(t.selection.match_id, []).append(t)
    kept: list[SingleMatchTicket] = []
    for _, ts in by_match.items():
        ts_sorted = sorted(ts, key=lambda x: x.ev_per_unit, reverse=True)
        kept.extend(ts_sorted[:top_per_match])
    kept.sort(key=lambda t: t.ev_per_unit, reverse=True)
    return kept


def recommend_singles(
    matches: list[MatchInput],
    *,
    bankroll: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_fraction_per_ticket: float = DEFAULT_MAX_STAKE_FRACTION,
    rules: LotteryRules = JINGCAI_DEFAULT,
    top_per_match: int = 1,
    apply_thresholds: bool = True,
) -> SingleMatchRecommendation:
    """Recommend single-leg tickets across the supplied matches.

    Pipeline (per match):
      1. `build_selections_from_match` → up to 6 candidate Selections
      2. (if apply_thresholds) filter by `passes_recommendation_thresholds`
         — drops sub-min-EV or sub-min-hit-p
      3. Per-selection Kelly stake → ¥20k cap → ¥2 quantization
      4. Keep at most `top_per_match` per match (default 1)
      5. Global EV-descending sort

    Tickets that survived thresholds but quantize to ¥0 still appear in
    `tickets` (diagnostic) but are excluded from `selected_tickets`.
    """
    candidates: list[SingleMatchTicket] = []
    for match in matches:
        sels = build_selections_from_match(match)
        for sel in sels:
            if apply_thresholds and not passes_recommendation_thresholds(
                hit_probability=sel.probability,
                ev_per_unit=sel.edge,
                rules=rules,
            ):
                continue
            kr = fractional_kelly_stake(
                hit_probability=sel.probability,
                ev_per_unit=sel.edge,
                bankroll=bankroll,
                kelly_fraction=kelly_fraction,
                max_stake_fraction=max_stake_fraction_per_ticket,
            )
            capped = cap_ticket_stake(kr.recommended_stake, rules)
            quantized = quantize_stake(capped, rules.stake_unit)
            expected_return = quantized * sel.edge
            candidates.append(SingleMatchTicket(
                selection=sel,
                raw_kelly_stake=kr.recommended_stake,
                stake=quantized,
                expected_return=expected_return,
            ))

    kept = _best_per_match(candidates, top_per_match)
    selected = [t for t in kept if t.stake > 0]
    return SingleMatchRecommendation(
        tickets=kept,
        selected_tickets=selected,
        total_stake=sum(t.stake for t in selected),
        total_expected_return=sum(t.expected_return for t in selected),
    )


__all__ = [
    "SingleMatchTicket",
    "SingleMatchRecommendation",
    "recommend_singles",
]
