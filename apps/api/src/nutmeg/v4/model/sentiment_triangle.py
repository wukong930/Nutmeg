"""竞彩 情绪三角 — model / sharp / retail as three independent vertices.

Exploration direction #4 (2026-07-06). We hold THREE views of the same match:

  * **model** — Nutmeg CatBoost+DC fundamental P (league_predictions).
  * **sharp** — Pinnacle WPO de-vig P. The truth anchor (EV is always sharp × 竞彩SP).
  * **retail** — 竞彩 支持比例 (ticket-share sentiment). NOT a calibrated P — the crowd
    over-concentrates — so it is used for DIRECTION (over/under-weighting vs sharp),
    not as a probability.

#2 showed 竞彩 shades its price toward the crowd (lengthening the legs the crowd
AVOIDS → the soft, potentially-+EV spots). The triangle adds the MODEL as an
independent second vote on that signal: on the leg the crowd avoids (where 竞彩 is
soft), does the model AGREE it's under-valued (model_P ≥ sharp_P → confirm) or
DISAGREE (model_P < sharp_P → caution — the crowd may be right and sharp generous
for a reason)? The question this answers that sharp-alone can't: is a soft leg
double-confirmed, or is the model siding with the crowd against sharp?

PURE module; the CLI feeds three de-vigged/normalized triples + the outcome.
EXPLORATORY, read-only; a triangulation pattern is an autumn hypothesis, not a bet.
"""
from __future__ import annotations

from dataclasses import dataclass

_POS = ("主", "平", "客")


def _tv(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Total variation (½ L1) between two distributions — 0=identical, 1=disjoint."""
    return 0.5 * sum(abs(a[i] - b[i]) for i in range(3))


@dataclass(frozen=True)
class TriangleSample:
    match_date: str
    home: str
    away: str
    model_p: tuple[float, float, float]   # model P (主,平,客)
    sharp_p: tuple[float, float, float]   # Pinnacle WPO de-vig (truth)
    retail_p: tuple[float, float, float]  # support/100 — sentiment share, not P
    outcome: int | None = None            # 0=主,1=平,2=客, or None if unsettled

    @property
    def d_model_sharp(self) -> float:
        return _tv(self.model_p, self.sharp_p)

    @property
    def d_sharp_retail(self) -> float:
        return _tv(self.sharp_p, self.retail_p)

    @property
    def d_model_retail(self) -> float:
        return _tv(self.model_p, self.retail_p)

    @property
    def crowd_is_outlier(self) -> bool:
        """model & sharp agree more with each other than either does with the crowd
        → the crowd is the odd one out (竞彩, priced on it, likely soft)."""
        return (self.d_model_sharp < self.d_sharp_retail
                and self.d_model_sharp < self.d_model_retail)

    @property
    def crowd_avoided_leg(self) -> int:
        """Leg the crowd UNDER-weights most vs sharp (retail − sharp minimal) —
        where 竞彩 lengthens the price = the #2 soft spot."""
        return min(range(3), key=lambda i: self.retail_p[i] - self.sharp_p[i])

    @property
    def model_confirms_avoided(self) -> bool:
        """On the crowd-avoided leg, does the model rate it ≥ sharp (confirm soft)?"""
        i = self.crowd_avoided_leg
        return self.model_p[i] >= self.sharp_p[i]


@dataclass(frozen=True)
class TriangleResult:
    n: int
    n_settled: int
    mean_d_model_sharp: float      # is the model closer to sharp…
    mean_d_sharp_retail: float
    mean_d_model_retail: float     # …or to the crowd?
    crowd_outlier_frac: float      # share of matches where the crowd is the outlier
    # settled: crowd-avoided leg — did it win, split by the model's verdict?
    confirm_n: int
    confirm_wins: int
    confirm_sharp_base: float      # mean sharp_P on those legs (expected win rate)
    contra_n: int
    contra_wins: int
    contra_sharp_base: float


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def analyze(samples: list[TriangleSample]) -> TriangleResult:
    n = len(samples)
    settled = [s for s in samples if s.outcome is not None]
    confirm = [s for s in settled if s.model_confirms_avoided]
    contra = [s for s in settled if not s.model_confirms_avoided]

    def _wins(group: list[TriangleSample]) -> int:
        return sum(1 for s in group if s.outcome == s.crowd_avoided_leg)

    def _base(group: list[TriangleSample]) -> float:
        return _mean([s.sharp_p[s.crowd_avoided_leg] for s in group])

    return TriangleResult(
        n=n,
        n_settled=len(settled),
        mean_d_model_sharp=_mean([s.d_model_sharp for s in samples]),
        mean_d_sharp_retail=_mean([s.d_sharp_retail for s in samples]),
        mean_d_model_retail=_mean([s.d_model_retail for s in samples]),
        crowd_outlier_frac=_mean([1.0 if s.crowd_is_outlier else 0.0 for s in samples]),
        confirm_n=len(confirm), confirm_wins=_wins(confirm), confirm_sharp_base=_base(confirm),
        contra_n=len(contra), contra_wins=_wins(contra), contra_sharp_base=_base(contra),
    )


__all__ = ["TriangleSample", "TriangleResult", "analyze", "_POS"]
