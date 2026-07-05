"""Tests for 线源残差分解 (exploration #2) — band-based irreducible-domestic split."""
from __future__ import annotations

from nutmeg.v4.model.line_origin import LineOriginSample, analyze


def _s(jc, open_p, close_p, band_lo=None, band_hi=None, support=None):
    # default band = per-leg [min, max] of open & close (jc between them = inside)
    if band_lo is None:
        band_lo = tuple(min(open_p[i], close_p[i]) for i in range(3))
    if band_hi is None:
        band_hi = tuple(max(open_p[i], close_p[i]) for i in range(3))
    return LineOriginSample("2026-08-10", "H", "A", jc, open_p, close_p,
                            band_lo, band_hi, support)


def test_irreducible_zero_when_inside_band():
    # 竞彩 lands inside the sharp-line's traversed range on every leg → some stale
    # anchor could have produced it → irreducible domestic is zero.
    s = _s(jc=(0.47, 0.29, 0.24), open_p=(0.45, 0.30, 0.25), close_p=(0.50, 0.28, 0.22))
    assert all(abs(x) < 1e-12 for x in s.irreducible)
    res = analyze([s])
    assert res.mean_abs_irreducible < 1e-12
    assert res.domestic_share < 1e-9
    assert res.frac_legs_outside_band < 1e-9


def test_staleness_credited_when_jc_mirrors_close():
    # THE regression test for the flaw the band fixes: a 竞彩 line that perfectly
    # mirrors the CLOSING sharp line has NO domestic bias. A naïve 竞彩−open split
    # would wrongly tag it; the band credits staleness → irreducible must be zero.
    open_p, close_p = (0.45, 0.30, 0.25), (0.52, 0.27, 0.21)
    s = _s(jc=close_p, open_p=open_p, close_p=close_p)
    assert all(abs(x) < 1e-12 for x in s.irreducible)


def test_irreducible_outside_band_signed_distance():
    # jc above the band on home, below on away → signed distance to nearest edge.
    s = _s(jc=(0.60, 0.28, 0.12), open_p=(0.45, 0.30, 0.25), close_p=(0.50, 0.28, 0.22))
    # bands: home [0.45,0.50] → 0.60−0.50=+0.10 ; draw [0.28,0.30] inside → 0 ;
    #        away [0.22,0.25] → 0.12−0.22=−0.10
    assert abs(s.irreducible[0] - 0.10) < 1e-12
    assert abs(s.irreducible[1]) < 1e-12
    assert abs(s.irreducible[2] - (-0.10)) < 1e-12
    res = analyze([s])
    assert abs(res.frac_legs_outside_band - 2 / 3) < 1e-9  # 2 of 3 legs outside


def test_by_position_irreducible_sign():
    # Pinnacle never moved (open==close → point band); 竞彩 shades home UP, away DOWN.
    s = _s(jc=(0.60, 0.30, 0.10), open_p=(0.50, 0.30, 0.20), close_p=(0.50, 0.30, 0.20))
    res = analyze([s])
    assert res.by_position_irreducible["主"] > 0
    assert res.by_position_irreducible["客"] < 0
    assert abs(res.by_position_irreducible["平"]) < 1e-12


def test_support_terciles_track_irreducible():
    # Point band (open==close) so irreducible == 竞彩 − sharp directly. 竞彩 pushes
    # implied P toward the crowd: hot (home) leg positive, cold (away) leg negative.
    pin = (0.40, 0.30, 0.30)
    samples = []
    for j in range(6):
        support = (55.0 + j, 25.0, 20.0 - j)  # home hot, away cold
        jc = (0.45, 0.30, 0.25)               # +0.05 home / 0 draw / −0.05 away
        samples.append(_s(jc=jc, open_p=pin, close_p=pin, support=support))
    res = analyze(samples)
    assert len(res.support_terciles) == 3
    low_sup, high_sup = res.support_terciles[0][2], res.support_terciles[2][2]
    assert high_sup > low_sup                 # terciles ordered by support
    low_dom, high_dom = res.support_terciles[0][3], res.support_terciles[2][3]
    assert high_dom > low_dom                 # irreducible residual rises with support
    assert low_dom < 0 < high_dom             # cold leg −, hot leg +


def test_empty_and_small_samples_safe():
    res = analyze([])
    assert res.n == 0
    assert res.domestic_share == 0.0
    assert res.support_terciles == []
    res2 = analyze([_s(jc=(0.4, 0.3, 0.3), open_p=(0.4, 0.3, 0.3),
                       close_p=(0.4, 0.3, 0.3), support=(33.0, 33.0, 34.0))])
    assert res2.support_terciles == []
