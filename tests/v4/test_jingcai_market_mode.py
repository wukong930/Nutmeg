"""V14 Part 2 — 竞彩盘口推荐 covers cup/J1 with the SHARP de-vig P, not the model.

cup/J1 are out-of-distribution for the European-trained model, so when the user
fills a 竞彩 SP on a 市场模式 card and it flows into the 竞彩盘, the 胜平负 P must be
reverse-fit from the de-vig Pinnacle line (the same source 市场模式 displays) — NOT
the model's λ. `_fixture_to_match_input` now reverse-fits λ for any league in
`_CUP_MARKET_COMPETITIONS`; the 13 trained leagues keep their model λ untouched.
"""
from __future__ import annotations

import pandas as pd

from nutmeg.v4.api.routes import _fixture_to_match_input
from nutmeg.v4.combo.selections import MatchInput, build_selections_from_match
from nutmeg.v4.model.market_handicap import devig_over, fit_lambdas


def _devig(h, d, a):
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv]


def _row(league, **over):
    base = {
        "league": league, "home_team": "Kashima", "away_team": "Vissel",
        "psc_home": 2.36, "psc_draw": 3.35, "psc_away": 3.15,
        "psc_over25": 1.943, "psc_under25": 1.925, "ou_line": 2.25,
        "odds_1x2_H": 1.88, "odds_1x2_D": 3.18, "odds_1x2_A": 3.53,
        "handicap_home": float("nan"),
    }
    base.update(over)
    return pd.Series(base)


class TestCupJ1UsesDevigLambda:
    def test_j1_overrides_model_lambda_with_devig_fit(self):
        # absurd model λ (9.9 / 0.1) to PROVE they get replaced by the de-vig fit
        mi = _fixture_to_match_input(_row("JPN_J1"), lh=9.9, la=0.1, gbm_rho=-0.10)
        assert mi is not None
        fair = _devig(2.36, 3.35, 3.15)
        exp_h, exp_a = fit_lambdas(
            fair[0], fair[1], fair[2], devig_over(1.943, 1.925), ou_line=2.25
        )
        assert mi.lambda_home == exp_h
        assert mi.lambda_away == exp_a
        assert mi.lambda_home != 9.9          # model λ was overridden

    def test_cup_also_overrides(self):
        mi = _fixture_to_match_input(_row("UCL"), lh=9.9, la=0.1, gbm_rho=-0.10)
        fair = _devig(2.36, 3.35, 3.15)
        exp_h, _ = fit_lambdas(fair[0], fair[1], fair[2], devig_over(1.943, 1.925), ou_line=2.25)
        assert mi.lambda_home == exp_h

    def test_ou_line_2_25_differs_from_2_5(self):
        # the forwarded ou_line actually changes the fit (quarter line ≠ 2.5)
        mi_225 = _fixture_to_match_input(_row("JPN_J1", ou_line=2.25), 9.9, 0.1, -0.10)
        mi_250 = _fixture_to_match_input(_row("JPN_J1", ou_line=2.5), 9.9, 0.1, -0.10)
        assert (mi_225.lambda_home + mi_225.lambda_away) != (
            mi_250.lambda_home + mi_250.lambda_away
        )

    def test_match_probs_is_devig_1x2_verbatim(self):
        # 胜平负 P override = the MULTIPLICATIVE de-vig 1X2 (what the 市场模式 card shows)
        mi = _fixture_to_match_input(_row("JPN_J1"), 9.9, 0.1, -0.10)
        fair = _devig(2.36, 3.35, 3.15)
        assert mi.match_probs == {"H": fair[0], "D": fair[1], "A": fair[2]}


class TestTrainedLeagueKeepsModelLambda:
    def test_epl_lambda_untouched(self):
        mi = _fixture_to_match_input(_row("EPL"), lh=1.7, la=1.1, gbm_rho=-0.10)
        assert mi.lambda_home == 1.7          # model λ NOT replaced for trained leagues
        assert mi.lambda_away == 1.1
        assert mi.match_probs is None         # no 1X2 override for trained leagues

    def test_la_liga_lambda_untouched(self):
        mi = _fixture_to_match_input(_row("ESP_LA_LIGA"), lh=1.3, la=1.4, gbm_rho=-0.10)
        assert mi.lambda_home == 1.3
        assert mi.lambda_away == 1.4


class TestMatchProbsVerbatim:
    """build_selections uses match_probs VERBATIM — no temperature correction
    (the de-vig line is already calibrated), mirroring handicap_probs."""

    _ODDS = {"H": 2.5, "D": 3.5, "A": 5.0}

    def test_match_probs_ignores_correction(self):
        mp = {"H": 0.50, "D": 0.30, "A": 0.20}
        mi = MatchInput(match_id="x", lambda_home=1.5, lambda_away=1.1,
                        odds_1x2=self._ODDS, match_probs=mp)
        # a T≠1 correction would shift a model-grid P — but match_probs must ignore it
        sels = build_selections_from_match(mi, correction={"T": 2.0})
        by = {s.outcome: s.probability for s in sels if s.market_type == "1x2"}
        assert by == {"H": 0.50, "D": 0.30, "A": 0.20}

    def test_without_match_probs_correction_applies(self):
        mi = MatchInput(match_id="x", lambda_home=1.5, lambda_away=1.1,
                        odds_1x2=self._ODDS)               # model grid path
        raw = build_selections_from_match(mi, correction=None)
        corr = build_selections_from_match(mi, correction={"T": 2.0})
        p_raw = {s.outcome: s.probability for s in raw if s.market_type == "1x2"}
        p_corr = {s.outcome: s.probability for s in corr if s.market_type == "1x2"}
        # T=2 DOES move the model-grid P → so the verbatim test above is meaningful
        assert p_raw != p_corr


class TestArgmaxTicketCarriesHandicapLines:
    """V14 — the 今日推荐 prediction ticket now carries the market-reverse 让球
    board so the 国际盘/市场模式 boards can show a 让球胜平负 prediction (line
    selector). Display-only — for Polymarket prep, not a 竞彩 bet."""

    def test_handicap_lines_on_prediction_ticket(self):
        from nutmeg.v4.api.routes import _argmax_prediction_tickets
        from nutmeg.v4.api.schemas import HandicapLineProb, SinglePrediction
        hl = [HandicapLineProb(line=ln, p_home=0.3, p_draw=0.3, p_away=0.4)
              for ln in range(-3, 4)]
        pred = SinglePrediction(
            home_team="A", away_team="B", league="EPL", date="2026-06-06",
            lambda_home=1.4, lambda_away=1.1,
            p_home_1x2=0.45, p_draw_1x2=0.28, p_away_1x2=0.27,
            handicap_lines=hl,
        )
        tickets = _argmax_prediction_tickets([pred])
        assert len(tickets) == 1
        assert tickets[0].outcome == "H"                 # argmax 1X2 (unchanged)
        assert len(tickets[0].handicap_lines) == 7       # full −3..+3 board carried
        assert [ln.line for ln in tickets[0].handicap_lines] == list(range(-3, 4))


class TestArgmaxTicketsAreNoEvPredictions:
    """V12 W8k REGRESSION GUARD — the 今日推荐 ①单关 board must be model-argmax
    PREDICTIONS, never +EV-vs-Pinnacle bets. The killed bug fed recommend_singles
    the Pinnacle-fallback odds (no 竞彩 SP at page-load), surfacing the model's
    biggest DISAGREEMENT with the sharp as the 'best pick' — noise sold as +EV
    (e.g. an already-relegated home side @5.21). This pins that EVERY today-single
    ticket carries ZERO EV/stake and a fair (1/P) price, so anyone re-wiring
    recommend_single back into this path trips CI. (Audit 2026-06-06 found this
    invariant guarded only by a 'single is None when no fixtures' assertion.)"""

    def _preds(self):
        from nutmeg.v4.api.schemas import SinglePrediction
        return [
            SinglePrediction(home_team="A", away_team="B", league="EPL",
                             date="2026-06-06", lambda_home=1.6, lambda_away=1.0,
                             p_home_1x2=0.55, p_draw_1x2=0.27, p_away_1x2=0.18),
            SinglePrediction(home_team="C", away_team="D", league="ESP_LA_LIGA",
                             date="2026-06-06", lambda_home=0.9, lambda_away=1.5,
                             p_home_1x2=0.25, p_draw_1x2=0.28, p_away_1x2=0.47),
        ]

    def test_every_ticket_is_zero_ev_zero_stake(self):
        from nutmeg.v4.api.routes import _argmax_prediction_tickets
        tickets = _argmax_prediction_tickets(self._preds())
        assert len(tickets) == 2
        for tk in tickets:
            assert tk.ev_per_unit == 0.0          # a PREDICTION, not a +EV bet
            assert tk.stake == 0.0 and tk.raw_kelly_stake == 0.0
            assert tk.expected_return == 0.0
            assert tk.market_type == "1x2"

    def test_price_is_model_fair_not_market(self):
        # odds = 1/P (model fair price), NOT a Pinnacle/竞彩 SP → no EV can form
        from nutmeg.v4.api.routes import _argmax_prediction_tickets
        for tk in _argmax_prediction_tickets(self._preds()):
            assert abs(tk.odds - 1.0 / tk.probability) < 1e-9

    def test_outcome_is_argmax_sorted_by_confidence(self):
        from nutmeg.v4.api.routes import _argmax_prediction_tickets
        tickets = _argmax_prediction_tickets(self._preds())
        assert [tk.outcome for tk in tickets] == ["H", "A"]     # argmax of each pred
        probs = [tk.probability for tk in tickets]
        assert probs == sorted(probs, reverse=True)             # confidence desc, not EV

    def test_schema_cannot_carry_ev_or_stake(self):
        # structural guard: SinglePrediction has no EV/stake fields at all
        from nutmeg.v4.api.schemas import SinglePrediction
        f = SinglePrediction.model_fields
        assert "ev_per_unit" not in f
        assert "stake" not in f
        assert "expected_return" not in f
