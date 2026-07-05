"""Tests for 情绪三角 (exploration #4) — model/sharp/retail triangulation."""
from __future__ import annotations

from nutmeg.v4.model.sentiment_triangle import TriangleSample, _tv, analyze


def _s(model, sharp, retail, outcome=None):
    return TriangleSample("2026-08-10", "H", "A", model, sharp, retail, outcome)


def test_tv_bounds():
    assert _tv((0.5, 0.3, 0.2), (0.5, 0.3, 0.2)) == 0.0
    assert abs(_tv((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)) - 1.0) < 1e-12


def test_crowd_avoided_leg_is_most_underweighted():
    # crowd piles home (+0.1 vs sharp), avoids away (−0.1) → avoided leg = away(2)
    s = _s(model=(0.4, 0.3, 0.3), sharp=(0.5, 0.3, 0.2), retail=(0.6, 0.3, 0.1))
    assert s.crowd_avoided_leg == 2


def test_model_confirms_vs_contradicts_avoided():
    # avoided leg = away(2), sharp_p[2]=0.2
    confirm = _s(model=(0.4, 0.3, 0.3), sharp=(0.5, 0.3, 0.2), retail=(0.6, 0.3, 0.1))
    assert confirm.model_confirms_avoided is True   # model 0.3 ≥ sharp 0.2
    contra = _s(model=(0.6, 0.3, 0.1), sharp=(0.5, 0.3, 0.2), retail=(0.6, 0.3, 0.1))
    assert contra.model_confirms_avoided is False   # model 0.1 < sharp 0.2


def test_crowd_is_outlier_only_when_model_sides_with_sharp():
    # model == sharp, crowd apart → crowd is the outlier
    s1 = _s(model=(0.5, 0.3, 0.2), sharp=(0.5, 0.3, 0.2), retail=(0.7, 0.2, 0.1))
    assert s1.crowd_is_outlier is True
    # model shares the crowd, both off sharp → NOT crowd-outlier (model has crowd bias)
    s2 = _s(model=(0.7, 0.2, 0.1), sharp=(0.5, 0.3, 0.2), retail=(0.7, 0.2, 0.1))
    assert s2.crowd_is_outlier is False


def test_analyze_splits_avoided_leg_by_model_verdict():
    # avoided leg = away(2) in all three; sharp_p[2]=0.2
    confirm_win = _s((0.4, 0.3, 0.3), (0.5, 0.3, 0.2), (0.6, 0.3, 0.1), outcome=2)
    confirm_loss = _s((0.4, 0.3, 0.3), (0.5, 0.3, 0.2), (0.6, 0.3, 0.1), outcome=0)
    contra_loss = _s((0.6, 0.3, 0.1), (0.5, 0.3, 0.2), (0.6, 0.3, 0.1), outcome=0)
    unsettled = _s((0.4, 0.3, 0.3), (0.5, 0.3, 0.2), (0.6, 0.3, 0.1), outcome=None)
    res = analyze([confirm_win, confirm_loss, contra_loss, unsettled])
    assert res.n == 4 and res.n_settled == 3        # unsettled excluded
    assert res.confirm_n == 2 and res.confirm_wins == 1
    assert res.contra_n == 1 and res.contra_wins == 0
    assert abs(res.confirm_sharp_base - 0.2) < 1e-9  # mean sharp_P on avoided leg


def test_model_closer_to_sharp_than_crowd_flag():
    # model hugs sharp, crowd far → mean model↔sharp < model↔retail
    samples = [
        _s((0.5, 0.3, 0.2), (0.5, 0.3, 0.2), (0.75, 0.15, 0.1)),
        _s((0.4, 0.35, 0.25), (0.42, 0.33, 0.25), (0.7, 0.2, 0.1)),
    ]
    res = analyze(samples)
    assert res.mean_d_model_sharp < res.mean_d_model_retail


def test_empty_safe():
    res = analyze([])
    assert res.n == 0 and res.n_settled == 0
    assert res.confirm_n == 0 and res.contra_n == 0
