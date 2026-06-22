"""真 EV 推荐板 (/recommend/ev-board) — EV = P(Pinnacle 去vig) × 竞彩SP − 1.

The honest board behind 单关/串关/复式: merges the two live 近期赛事 surfaces
(predictions_sp_calc + predictions_cup_market) and keeps only legs that have BOTH a
Pinnacle line (→ P) AND a 竞彩 SP on file; gated at min_ev, sorted by EV. Usually empty
— that empty state IS the 空仓 signal (the ~12% 竞彩 vig wall). See
[[soft-water-leg-finding-measured]].
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from nutmeg.v4.api import routes
from nutmeg.v4.api.schemas import HandicapLineProb, SinglePrediction, SpCalcResponse


def _pred(**kw) -> SinglePrediction:
    base = dict(
        home_team="A", away_team="B", league="WC",
        date=datetime.date(2026, 6, 25), lambda_home=1.2, lambda_away=1.0,
        p_home_1x2=0.45, p_draw_1x2=0.28, p_away_1x2=0.27,
    )
    base.update(kw)
    return SinglePrediction(**base)


def _legs(preds, *, min_ev=0.05, bankroll=1000.0, kelly_fraction=0.25):
    return routes._ev_board_legs(
        preds, min_ev=min_ev, bankroll=bankroll, kelly_fraction=kelly_fraction
    )


def _spcalc(preds):
    return SpCalcResponse(
        generated_at_utc="t", date_start="d", date_end="d", days=3,
        fixtures_fetched=len(preds), predictions=preds,
    )


def test_filters_to_positive_ev_and_sorts():
    """Only the +EV leg survives the +5% gate. EV is P(Pinnacle de-vig) × 竞彩SP − 1,
    NOT model P, NOT Pinnacle's own price. (de-vig away ≈ 24.1%; 竞彩 4.5 → +8.6%.)"""
    preds = [
        _pred(home_team="Spain", away_team="Brazil",
              psc_home=2.0, psc_draw=3.5, psc_away=4.0,
              jc_home=1.9, jc_draw=3.0, jc_away=4.5),
        _pred(home_team="X", away_team="Y",                 # no 竞彩 SP → excluded
              psc_home=1.5, psc_draw=4.0, psc_away=6.0),
    ]
    legs, n_fix, n_with, n_pos = _legs(preds)
    assert n_fix == 1 and n_with == 3 and n_pos == 1
    assert len(legs) == 1
    leg = legs[0]
    assert leg.market == "had" and leg.outcome == "away"
    assert leg.ev > 0.05 and leg.jc_sp == 4.5 and leg.kelly_stake > 0


def test_excludes_predictions_without_pinnacle():
    """A 竞彩 SP with no Pinnacle line → not priceable → not on the board."""
    preds = [_pred(jc_home=1.9, jc_draw=3.0, jc_away=4.5)]  # psc_* None
    legs, n_fix, n_with, _ = _legs(preds, min_ev=-1.0)
    assert n_fix == 0 and n_with == 0 and legs == []


def test_empty_when_no_positive_but_slider_surfaces_least_bad():
    """0 真 +EV → empty board (honest 空仓). The min_ev slider pulled negative
    surfaces the least-bad legs (still clearly −EV)."""
    preds = [_pred(psc_home=1.2, psc_draw=6.0, psc_away=12.0,   # heavy favourite
                   jc_home=1.15, jc_draw=5.0, jc_away=10.0)]    # 竞彩 tight → all −EV
    gated, _, _, n_pos = _legs(preds, min_ev=0.05)
    loose, _, _, _ = _legs(preds, min_ev=-0.30)
    assert n_pos == 0 and gated == []
    assert len(loose) >= 1 and all(leg.ev < 0.05 for leg in loose)


def test_handicap_leg_from_market_reverse_lines():
    """让球 EV uses the prediction's O/U-double-anchored handicap_lines × 竞彩 让球 SP."""
    hl = [HandicapLineProb(line=-1, p_home=0.30, p_draw=0.25, p_away=0.45)]
    preds = [_pred(psc_home=1.8, psc_draw=3.6, psc_away=4.5,
                   jc_hc_home=4.0, jc_hc_draw=3.5, jc_hc_away=2.0, jc_hc_line=-1,
                   handicap_lines=hl)]
    legs, n_fix, _, _ = _legs(preds, min_ev=0.05)
    assert n_fix == 1
    hhad = [leg for leg in legs if leg.market == "hhad"]
    assert len(hhad) == 1
    assert hhad[0].outcome == "home" and hhad[0].handicap_line == -1
    assert abs(hhad[0].ev - 0.20) < 1e-6     # 让胜 0.30 × 4.0 − 1


def test_dedup_by_match_across_gathers():
    """The same fixture surfacing from both gathers is counted once."""
    kw = dict(home_team="Spain", away_team="Brazil",
              psc_home=2.0, psc_draw=3.5, psc_away=4.0,
              jc_home=1.9, jc_draw=3.0, jc_away=4.5)
    legs, n_fix, n_with, _ = _legs([_pred(**kw), _pred(**kw)], min_ev=-1.0)
    assert n_fix == 1 and n_with == 3


def test_endpoint_merges_both_gathers():
    """The endpoint unions predictions_sp_calc + predictions_cup_market (so WC/芬超/日职
    via cup_market reach the board, not just the 13 off-season leagues)."""
    league = _spcalc([])                       # 13 leagues: off-season, empty
    cup = _spcalc([_pred(home_team="Spain", away_team="Brazil",
                         psc_home=2.0, psc_draw=3.5, psc_away=4.0,
                         jc_home=1.9, jc_draw=3.0, jc_away=4.5)])
    with patch.object(routes, "predictions_sp_calc", return_value=league), \
         patch.object(routes, "predictions_cup_market", return_value=cup):
        resp = routes.recommend_ev_board(days=3, min_ev=0.05)
    assert resp.n_fixtures == 1 and resp.n_positive == 1 and len(resp.legs) == 1
    assert resp.legs[0].home_team == "Spain"


def test_endpoint_survives_a_failing_gather():
    """One surface raising must not 500 — the board just uses the other."""
    cup = _spcalc([_pred(home_team="Spain", away_team="Brazil",
                         psc_home=2.0, psc_draw=3.5, psc_away=4.0,
                         jc_home=1.9, jc_draw=3.0, jc_away=4.5)])
    with patch.object(routes, "predictions_sp_calc", side_effect=RuntimeError("boom")), \
         patch.object(routes, "predictions_cup_market", return_value=cup):
        resp = routes.recommend_ev_board(days=3, min_ev=0.05)
    assert resp.n_positive == 1


def test_days_out_of_range_422():
    with pytest.raises(HTTPException) as ei:
        routes.recommend_ev_board(days=9)
    assert ei.value.status_code == 422


def test_validation_422():
    """bankroll / kelly_fraction / min_ev are range-checked (no garbage stakes)."""
    for kw in ({"bankroll": -1}, {"kelly_fraction": 0.0}, {"kelly_fraction": 1.5},
               {"min_ev": 2.0}):
        with pytest.raises(HTTPException) as ei:
            routes.recommend_ev_board(**kw)
        assert ei.value.status_code == 422, kw


def test_503_when_both_gathers_fail():
    """BOTH surfaces down → 503, NOT an empty 200 — so an empty board can only ever
    mean '0 +EV legs', never 'system unavailable'."""
    with patch.object(routes, "predictions_sp_calc", side_effect=RuntimeError("boom")), \
         patch.object(routes, "predictions_cup_market", side_effect=RuntimeError("boom")), \
         pytest.raises(HTTPException) as ei:
        routes.recommend_ev_board(days=3, min_ev=0.05)
    assert ei.value.status_code == 503


def test_hhad_fixture_without_matching_line_not_counted():
    """竞彩 让球 SP present but handicap_lines lacks that line (e.g. a −2 favourite line
    the model never emits / O/U missing → empty) → 0 legs, and n_fixtures must NOT count it."""
    preds = [_pred(psc_home=1.8, psc_draw=3.6, psc_away=4.5,
                   jc_hc_home=4.0, jc_hc_draw=3.5, jc_hc_away=2.0, jc_hc_line=-2,
                   handicap_lines=[HandicapLineProb(line=-1, p_home=0.3,
                                                    p_draw=0.25, p_away=0.45)])]
    legs, n_fix, n_with, _ = _legs(preds, min_ev=-1.0)
    assert n_fix == 0 and n_with == 0 and legs == []
