"""体检 C1 (2026-07-01) — /recommend/market-handicap must expose the WPO 1X2
fair-P (`p_1x2`) so the reverse-calc client stops recomputing it with BASIC
normalization (which inflated longshot P → false 🟢 +EV, up to ~11pp).
"""
from __future__ import annotations

from nutmeg.v4.api.routes import recommend_market_handicap
from nutmeg.v4.api.schemas import MarketHandicapRequest
from nutmeg.v4.model.devig import devig_1x2


def _req(h, d, a):
    return MarketHandicapRequest(
        league="MANUAL", date="2026-08-01", home_team="A", away_team="B",
        psc_home=h, psc_draw=d, psc_away=a, ou_line=2.5, handicap_home=-1,
        odds_handicap_H=None, odds_handicap_D=None, odds_handicap_A=None,
        record_session=False)


def test_p_1x2_is_wpo_not_basic():
    resp = recommend_market_handicap(_req(1.386, 4.7, 8.12))
    wpo = devig_1x2(1.386, 4.7, 8.12)
    assert resp.p_1x2 is not None
    assert [round(x, 6) for x in resp.p_1x2] == [round(x, 6) for x in wpo]

    # and it is NOT the basic normalization (the old client bug)
    inv = [1 / 1.386, 1 / 4.7, 1 / 8.12]
    s = sum(inv)
    basic = [x / s for x in inv]
    assert [round(x, 6) for x in resp.p_1x2] != [round(x, 6) for x in basic]
    # WPO shrinks the longshot vs basic — the whole point (prevents false +EV)
    assert resp.p_1x2[2] < basic[2]


def test_p_1x2_sums_to_one():
    resp = recommend_market_handicap(_req(2.1, 3.3, 3.6))
    assert abs(sum(resp.p_1x2) - 1.0) < 1e-9
