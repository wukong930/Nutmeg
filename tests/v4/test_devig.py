"""Shared de-vig helper — WPO default (FLB-aware) + basic toggle + guard.

WPO: p_i = (n − M·O_i)/(n·O_i), M = Σ(1/O)−1. Corrects the favourite-longshot bias
(raises favourites, shrinks longshots) vs basic proportional normalization.
"""
from __future__ import annotations

import math

from nutmeg.v4.model.devig import devig, devig_1x2


def test_wpo_exact_values():
    # odds [2.0, 3.5, 4.0]: M = 0.5 + 1/3.5 + 0.25 − 1 = 0.0357142857
    p = devig([2.0, 3.5, 4.0])  # wpo default
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)
    assert math.isclose(p[0], 0.488095238, abs_tol=1e-6)
    assert math.isclose(p[1], 0.273809524, abs_tol=1e-6)
    assert math.isclose(p[2], 0.238095238, abs_tol=1e-6)


def test_basic_normalization():
    p = devig([2.0, 3.5, 4.0], method="basic")
    s = 1 / 2.0 + 1 / 3.5 + 1 / 4.0
    assert math.isclose(p[0], (1 / 2.0) / s, abs_tol=1e-12)
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)


def test_wpo_corrects_favourite_longshot_bias():
    # vs basic, WPO must RAISE the favourite (lowest odds) and SHRINK the longshot.
    odds = [1.8, 3.6, 5.0]  # home favourite, away longshot
    w = devig(odds)
    b = devig(odds, method="basic")
    assert w[0] > b[0]   # favourite raised
    assert w[2] < b[2]   # longshot shrunk  ← the cold-trap-tightening direction
    assert math.isclose(sum(w), 1.0, abs_tol=1e-12)


def test_near_even_market_wpo_close_to_basic():
    # no clear favourite → FLB correction tiny → methods nearly equal.
    odds = [2.9, 3.1, 2.95]
    w, b = devig(odds), devig(odds, method="basic")
    assert all(abs(x - y) < 0.01 for x, y in zip(w, b, strict=True))


def test_out_of_bounds_falls_back_to_basic():
    # [1.05, 6, 50]: WPO gives a negative longshot prob → must fall back to basic.
    odds = [1.05, 6.0, 50.0]
    w = devig(odds)
    b = devig(odds, method="basic")
    assert all(0.0 < x < 1.0 for x in w)        # no negative / >1 leaked out
    assert w == b                                # fell back to basic
    assert math.isclose(sum(w), 1.0, abs_tol=1e-12)


def test_closed_form_inverse_roundtrip():
    # WPO fair odds Of_i = n·O_i/(n − M·O_i); 1/Of_i must equal p_i.
    odds = [2.2, 3.4, 3.3]
    p = devig(odds)
    n, M = 3, sum(1 / o for o in odds) - 1.0
    for o, pi in zip(odds, p, strict=True):
        of = n * o / (n - M * o)
        assert math.isclose(1.0 / of, pi, abs_tol=1e-12)


def test_invalid_inputs_return_none():
    assert devig([2.0, 3.0, None]) is None
    assert devig([2.0, 3.0, float("nan")]) is None
    assert devig([1.0, 3.0, 4.0]) is None        # ≤ 1.0 decimal odds
    assert devig_1x2(None, 3.0, 4.0) is None
    assert devig_1x2("x", 3.0, 4.0) is None


def test_devig_1x2_returns_tuple():
    p = devig_1x2(2.0, 3.5, 4.0)
    assert isinstance(p, tuple) and len(p) == 3
    assert math.isclose(sum(p), 1.0, abs_tol=1e-12)
