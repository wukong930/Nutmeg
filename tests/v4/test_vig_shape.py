"""竞彩 逐路 vig 分解(探索 #1)— pure-math + shading-detection regression."""
from __future__ import annotations

from nutmeg.v4.model.vig_shape import (
    VigSample,
    analyze,
    overround,
    per_leg_vig,
)


class TestVigMath:
    def test_per_leg_vig_is_minus_ev(self):
        # vig_i = 1 − P_i·SP_i (the bettor's per-leg −EV)
        v = per_leg_vig((2.0, 3.0, 4.0), (0.5, 0.3, 0.2))
        assert abs(v[0] - (1 - 0.5 * 2.0)) < 1e-9   # 0.0 — fair
        assert abs(v[1] - (1 - 0.3 * 3.0)) < 1e-9   # +0.1
        assert abs(v[2] - (1 - 0.2 * 4.0)) < 1e-9   # +0.2

    def test_overround(self):
        assert abs(overround((2.0, 2.0, 2.0)) - 0.5) < 1e-9   # 3×0.5 − 1

    def test_proportional_pricing_gives_equal_vig(self):
        """The null: SP_i = 1/(P_i·(1+OR)) ⇒ every leg's vig = OR/(1+OR).
        A zero within-match spread is the signature of unshaded (proportional)
        pricing — the whole measurement hinges on this invariant."""
        p = (0.55, 0.25, 0.20)
        OR = 0.13
        sp = tuple(1.0 / (pi * (1 + OR)) for pi in p)
        v = per_leg_vig(sp, p)
        assert max(v) - min(v) < 1e-9                 # perfectly equal
        assert abs(v[0] - OR / (1 + OR)) < 1e-9


def _sample(p, sp, support, date="2026-07-06"):
    return VigSample(date, "H", "A", per_leg_vig(sp, p), p, sp, support)


class TestAnalyze:
    def test_spread_zero_under_proportional(self):
        p = (0.5, 0.3, 0.2)
        sp = tuple(1.0 / (pi * 1.13) for pi in p)
        res = analyze([_sample(p, sp, (50, 30, 20)) for _ in range(4)])
        assert res.mean_spread < 1e-6

    def test_razor_detects_support_shading(self):
        """Construct matches where the HIGH-support leg is priced with thicker
        vig → the support terciles must rise low→high."""
        samples = []
        # home is always the crowd leg (support 70) and always over-vigged
        for _ in range(6):
            p = (0.45, 0.25, 0.30)          # away is the SHARP favourite (0.30<0.45? no)
            # make home the fair-favourite AND crowd leg; thick vig on home
            p = (0.50, 0.25, 0.25)
            sp = (1.0 / (p[0] * 1.30),        # home: heavy vig (OR-ish 30%)
                  1.0 / (p[1] * 1.05),        # draw: thin
                  1.0 / (p[2] * 1.05))        # away: thin
            samples.append(_sample(p, sp, (70, 15, 15)))
        res = analyze(samples)
        assert res.support_terciles
        vigs = [t[3] for t in res.support_terciles]   # low, mid, high
        assert vigs[-1] > vigs[0]            # high-support leg carries more vig
        assert res.fav_vig > res.dog_vig     # fav (=home=crowd) leg vig heavier

    def test_dog_control_present_with_enough_legs(self):
        samples = [_sample((0.5, 0.25, 0.25),
                           (1/(0.5*1.3), 1/(0.25*1.05), 1/(0.25*1.05)),
                           (70, 15, 15)) for _ in range(8)]
        res = analyze(samples)
        assert res.dog_support_terciles      # non-favourite razor computed
