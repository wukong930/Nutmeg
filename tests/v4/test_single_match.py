"""Tests for V6 W9 single-match (单关) recommender + nutmeg-rec interactive CLI.

Two layers:
  1. combo.single_match.recommend_singles  — pure logic tests with hand-
     constructed MatchInputs (no artifact needed)
  2. cli.rec  — prompt helpers + main() dispatch (mocked input + mocked
     fixtures loading)
"""
from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import pytest

from nutmeg.v4.cli.rec import (
    _build_parser,
    _format_single,
    _prompt,
    _prompt_choice,
    _prompt_float,
    _prompt_int,
    main,
)
from nutmeg.v4.combo.lottery_rules import JINGCAI_DEFAULT, LotteryRules
from nutmeg.v4.combo.selections import MatchInput
from nutmeg.v4.combo.single_match import (
    SingleMatchRecommendation,
    SingleMatchTicket,
    _best_per_match,
    recommend_singles,
)


# ---------- single_match logic --------------------------------------------

class TestRecommendSingles:
    def _high_ev_match(self, mid="EPL_Arsenal_vs_Wolves"):
        # λ_h=2.5, λ_a=0.5 → strong home favorite (p_H ≈ 0.75 via DC grid)
        # Lottery odds 1.5 for H → edge = 0.75*1.5 - 1 ≈ +0.125 (passes 5% threshold)
        return MatchInput(
            match_id=mid,
            lambda_home=2.5, lambda_away=0.5, rho=-0.10,
            odds_1x2={"H": 1.50, "D": 5.00, "A": 8.00},
        )

    def _low_ev_match(self, mid="EPL_Brentford_vs_Brighton"):
        # Balanced match λ=1.3 each (DC gives p ≈ 0.355/0.29/0.355).
        # Lottery offers tight odds so every selection's edge is negative.
        # (0.355*2.50 - 1 = -0.1125 for H/A; 0.29*3.00 - 1 = -0.13 for D)
        return MatchInput(
            match_id=mid,
            lambda_home=1.3, lambda_away=1.3, rho=-0.10,
            odds_1x2={"H": 2.50, "D": 3.00, "A": 2.50},
        )

    def test_high_ev_match_yields_recommendation(self):
        rec = recommend_singles([self._high_ev_match()], bankroll=1000.0)
        assert len(rec.selected_tickets) == 1
        t = rec.selected_tickets[0]
        assert t.selection.outcome == "H"
        assert t.selection.market_type == "1x2"
        # Quantized to ¥2
        assert t.stake % 2 == 0
        assert t.stake > 0
        assert rec.total_stake > 0
        assert rec.total_expected_return > 0

    def test_low_ev_match_yields_no_recommendation(self):
        rec = recommend_singles([self._low_ev_match()], bankroll=1000.0)
        assert rec.selected_tickets == []
        assert rec.total_stake == 0.0

    def test_top_per_match_limits_per_fixture(self):
        # Construct a fixture where BOTH H and away handicap might pass thresholds
        m = MatchInput(
            match_id="EPL_Arsenal_vs_Liverpool",
            lambda_home=2.0, lambda_away=1.0, rho=-0.10,
            odds_1x2={"H": 1.80, "D": 4.00, "A": 5.00},
            handicap_home=-1,
            odds_handicap_1x2={"H": 2.50, "D": 3.40, "A": 2.80},
        )
        rec1 = recommend_singles([m], bankroll=1000.0, top_per_match=1)
        rec2 = recommend_singles([m], bankroll=1000.0, top_per_match=2)
        ids_1 = [t.selection.match_id for t in rec1.tickets]
        ids_2 = [t.selection.match_id for t in rec2.tickets]
        # Same match_id may appear 1 or 2 times in tickets depending on top_per_match
        # (only those that passed threshold). The 2-version should have >= the 1-version.
        assert len(ids_2) >= len(ids_1)
        # And in rec1, that match_id appears at most once
        assert ids_1.count("EPL_Arsenal_vs_Liverpool") <= 1

    def test_empty_match_list_returns_empty_rec(self):
        rec = recommend_singles([], bankroll=1000.0)
        assert rec.tickets == []
        assert rec.selected_tickets == []
        assert rec.total_stake == 0.0
        assert rec.total_expected_return == 0.0

    def test_apply_thresholds_false_keeps_more(self):
        m = self._low_ev_match()
        with_thresh = recommend_singles([m], bankroll=1000.0, apply_thresholds=True)
        no_thresh = recommend_singles([m], bankroll=1000.0, apply_thresholds=False)
        assert len(no_thresh.tickets) > len(with_thresh.tickets)

    def test_stake_caps_at_20k(self):
        # Extreme bankroll → Kelly raw stake would explode; ¥20k cap kicks in
        m = self._high_ev_match()
        rec = recommend_singles(
            [m], bankroll=10_000_000.0,  # 10M bankroll
            max_stake_fraction_per_ticket=1.0,  # disable Kelly safety cap
            kelly_fraction=1.0,
        )
        assert all(t.stake <= JINGCAI_DEFAULT.max_ticket_stake for t in rec.selected_tickets)

    def test_zero_bankroll_yields_zero_stakes(self):
        rec = recommend_singles([self._high_ev_match()], bankroll=0.0)
        assert all(t.stake == 0.0 for t in rec.tickets)
        assert rec.selected_tickets == []

    def test_custom_rules_min_ev_filters_differently(self):
        m = self._high_ev_match()
        # The high-EV match actually clocks ~20.6% edge on H. With a 30%
        # threshold even this strong favorite gets filtered.
        strict = LotteryRules(min_ev_per_unit=0.30)
        rec = recommend_singles([m], bankroll=1000.0, rules=strict)
        assert rec.selected_tickets == []


class TestBestPerMatch:
    def _ticket(self, match_id, ev) -> SingleMatchTicket:
        from nutmeg.v4.combo.selections import Selection
        # 1.5 odds + (ev+1)/1.5 probability satisfies edge = p*odds - 1 = ev
        odds = 1.5
        p = (ev + 1.0) / odds
        sel = Selection(match_id=match_id, market_type="1x2", outcome="H",
                        probability=p, odds=odds)
        return SingleMatchTicket(
            selection=sel,
            raw_kelly_stake=10.0, stake=10.0,
            expected_return=10.0 * ev,
        )

    def test_top_1_picks_highest_per_match(self):
        ts = [
            self._ticket("M1", 0.10),
            self._ticket("M1", 0.20),  # winner for M1
            self._ticket("M1", 0.05),
            self._ticket("M2", 0.15),
            self._ticket("M2", 0.08),  # not winner
        ]
        kept = _best_per_match(ts, top_per_match=1)
        kept_evs = [t.ev_per_unit for t in kept]
        assert pytest.approx(0.20) == kept_evs[0]  # global #1
        assert pytest.approx(0.15) == kept_evs[1]  # global #2
        assert len(kept) == 2  # 1 per match

    def test_top_2_picks_two_per_match(self):
        ts = [
            self._ticket("M1", 0.10),
            self._ticket("M1", 0.20),
            self._ticket("M1", 0.05),
            self._ticket("M2", 0.15),
            self._ticket("M2", 0.08),
        ]
        kept = _best_per_match(ts, top_per_match=2)
        # M1 keeps 0.20 + 0.10; M2 keeps 0.15 + 0.08; total 4
        assert len(kept) == 4

    def test_invalid_top_per_match_raises(self):
        with pytest.raises(ValueError):
            _best_per_match([], top_per_match=0)


# ---------- _format_single ------------------------------------------------

class TestFormatSingle:
    def test_empty_says_no_bet(self):
        rec = SingleMatchRecommendation(tickets=[], selected_tickets=[])
        card = _format_single(rec, bankroll=1000.0, n_fixtures=3)
        assert "无可下注组合" in card
        assert "单关推荐" in card

    def test_with_tickets_renders_table(self):
        from nutmeg.v4.combo.selections import Selection
        sel = Selection(
            match_id="EPL_Arsenal_vs_Liverpool",
            market_type="1x2", outcome="H",
            probability=0.55, odds=2.10,
        )
        ticket = SingleMatchTicket(
            selection=sel, raw_kelly_stake=22.5, stake=22.0,
            expected_return=22.0 * sel.edge,
        )
        rec = SingleMatchRecommendation(
            tickets=[ticket], selected_tickets=[ticket],
            total_stake=22.0, total_expected_return=22.0 * sel.edge,
        )
        card = _format_single(rec, bankroll=1000.0, n_fixtures=1)
        assert "Arsenal vs Liverpool" in card
        assert "胜平负" in card
        assert "¥22" in card


# ---------- Prompt helpers ------------------------------------------------

def _reader_from_list(answers):
    """Build a fake `input` that returns answers in order, EOFError after."""
    it = iter(answers)

    def _r(prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError("no more answers")
    return _r


class TestPrompts:
    def test_prompt_default_on_empty(self):
        r = _reader_from_list([""])
        assert _prompt("X", default="hello", reader=r) == "hello"

    def test_prompt_uses_typed_value(self):
        r = _reader_from_list(["world"])
        assert _prompt("X", default="hello", reader=r) == "world"

    def test_prompt_int_validates_range(self):
        # First answer 99 (out of range), then 5 (in)
        r = _reader_from_list(["99", "5"])
        v = _prompt_int("N", default=3, lo=1, hi=8, reader=r)
        assert v == 5

    def test_prompt_int_default_on_empty(self):
        r = _reader_from_list([""])
        v = _prompt_int("N", default=3, lo=1, hi=8, reader=r)
        assert v == 3

    def test_prompt_int_rejects_non_integer(self):
        r = _reader_from_list(["abc", "4"])
        v = _prompt_int("N", default=3, lo=1, hi=8, reader=r)
        assert v == 4

    def test_prompt_float_validates(self):
        r = _reader_from_list(["xyz", "12.5"])
        v = _prompt_float("X", default=1.0, reader=r)
        assert v == 12.5

    def test_prompt_choice_rejects_off_menu(self):
        r = _reader_from_list(["7", "y"])
        v = _prompt_choice("Q", choices=["y", "n"], default="n", reader=r)
        assert v == "y"

    def test_prompt_eof_uses_default(self):
        r = _reader_from_list([])
        v = _prompt("X", default="def", reader=r)
        assert v == "def"


# ---------- main() integration --------------------------------------------

class TestMainDispatch:
    def test_quit_via_menu_returns_0(self, capsys):
        r = _reader_from_list(["q"])
        rc = main(argv=[], reader=r)
        assert rc == 0

    def test_unknown_fixtures_file_returns_1(self, capsys):
        # --type single, but the path doesn't exist
        r = _reader_from_list([])
        rc = main(
            argv=["--type", "single", "--fixtures", "/nonexistent.csv",
                  "--bankroll", "100", "--model", "data/v4_model_cat"],
            reader=r,
        )
        assert rc == 1
        out = capsys.readouterr().err
        assert "ERROR" in out

    def test_parser_accepts_all_modes(self):
        p = _build_parser()
        for t in ("single", "parlay", "pool"):
            ns = p.parse_args(["--type", t])
            assert ns.type == t

    def test_parser_default_type_none(self):
        ns = _build_parser().parse_args([])
        assert ns.type is None


class TestHandicapProbsOverride:
    """F1 — MatchInput.handicap_probs lets the API feed the MARKET-REVERSE 让球 P
    (de-vig Pinnacle 1X2 + O/U) so the single-leg recommendation matches the
    dashboard display + the parlay record. Before this, recommend_single used
    the model grid for 让球 → the EV the user SAW (market-reverse) ≠ the EV that
    got recommended/recorded (model grid) — a divergence up to ~4pp on 让胜.
    """

    def _hc_selections(self, match):
        from nutmeg.v4.combo.selections import build_selections_from_match
        return {
            s.outcome: s.probability
            for s in build_selections_from_match(match)
            if s.market_type == "handicap_1x2"
        }

    def test_override_used_verbatim_no_correction(self):
        mkt = {"H": 0.293, "D": 0.233, "A": 0.474}
        m = MatchInput(
            match_id="t", lambda_home=1.6, lambda_away=1.1, rho=-0.10,
            handicap_home=-1, odds_handicap_1x2={"H": 2.2, "D": 3.3, "A": 2.9},
            handicap_probs=mkt,
        )
        got = self._hc_selections(m)
        # used verbatim — NOT temperature-corrected (it is a de-vig prob already)
        assert got == pytest.approx(mkt, abs=1e-12)

    def test_without_override_falls_back_to_model_grid(self):
        from nutmeg.v4.model.dixon_coles import grid_to_handicap_1x2, score_grid
        m = MatchInput(
            match_id="t", lambda_home=1.6, lambda_away=1.1, rho=-0.10,
            handicap_home=-1, odds_handicap_1x2={"H": 2.2, "D": 3.3, "A": 2.9},
        )  # no handicap_probs
        got = self._hc_selections(m)
        gh, gd, ga = grid_to_handicap_1x2(score_grid(1.6, 1.1, rho=-0.10), handicap_home=-1)
        assert got["H"] == pytest.approx(gh, abs=1e-9)
        assert got["D"] == pytest.approx(gd, abs=1e-9)
        assert got["A"] == pytest.approx(ga, abs=1e-9)

    def test_override_changes_the_recommended_pick_ev(self):
        # Same odds, two P sources → materially different edge (the bug's impact).
        odds = {"H": 3.5, "D": 3.3, "A": 2.9}
        mkt = MatchInput(
            match_id="t", lambda_home=1.6, lambda_away=1.1, rho=-0.10,
            handicap_home=-1, odds_handicap_1x2=odds,
            handicap_probs={"H": 0.293, "D": 0.233, "A": 0.474},
        )
        model = MatchInput(
            match_id="t", lambda_home=1.6, lambda_away=1.1, rho=-0.10,
            handicap_home=-1, odds_handicap_1x2=odds,
        )
        ev_mkt = self._hc_selections(mkt)["H"] * 3.5 - 1
        ev_model = self._hc_selections(model)["H"] * 3.5 - 1
        # market-reverse 让胜 EV is positive-ish; model-grid is clearly negative —
        # i.e. which P you use flips the sign of the recommendation.
        assert ev_mkt > ev_model
        assert abs(ev_mkt - ev_model) > 0.05
