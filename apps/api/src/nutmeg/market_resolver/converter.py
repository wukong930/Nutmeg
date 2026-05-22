from __future__ import annotations

from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver.asian_handicap import resolve_asian_handicap
from nutmeg.market_resolver.cn_handicap import resolve_cn_handicap_1x2
from nutmeg.market_resolver.correct_score import resolve_correct_score
from nutmeg.market_resolver.european_handicap import resolve_european_handicap_1x2
from nutmeg.market_resolver.one_x_two import resolve_1x2

type MarketProbabilityValue = dict[str, float] | list[dict[str, float | int | str]]
type MarketProbabilityPayload = dict[str, MarketProbabilityValue]


def score_grid_to_market_probabilities(
    score_grid: ScoreProbabilityGrid,
    *,
    cn_handicaps: tuple[int, ...] = (),
    asian_handicap_lines: tuple[float, ...] = (),
    european_handicaps: tuple[int, ...] = (),
    asian_side: str = "home",
    correct_score_top_n: int | None = None,
) -> MarketProbabilityPayload:
    payload: MarketProbabilityPayload = {}
    one_x_two = resolve_1x2(score_grid)
    payload["1x2"] = one_x_two.as_market_map()

    for handicap in cn_handicaps:
        cn_probabilities = resolve_cn_handicap_1x2(score_grid, handicap=handicap)
        payload[f"cn_handicap_1x2:{handicap}"] = {
            "handicap_home_win": cn_probabilities.handicap_home_win,
            "handicap_draw": cn_probabilities.handicap_draw,
            "handicap_away_win": cn_probabilities.handicap_away_win,
        }

    for line in asian_handicap_lines:
        asian_probabilities = resolve_asian_handicap(score_grid, line=line, side=asian_side)
        payload[f"asian_handicap:{asian_side}:{line:g}"] = {
            "full_win": asian_probabilities.full_win_prob,
            "half_win": asian_probabilities.half_win_prob,
            "push": asian_probabilities.push_prob,
            "half_loss": asian_probabilities.half_loss_prob,
            "full_loss": asian_probabilities.full_loss_prob,
            "expected_return": asian_probabilities.expected_return_prob,
        }

    for handicap in european_handicaps:
        european_probabilities = resolve_european_handicap_1x2(score_grid, handicap=handicap)
        payload[f"european_handicap_1x2:{handicap}"] = {
            "handicap_home_win": european_probabilities.handicap_home_win,
            "handicap_draw": european_probabilities.handicap_draw,
            "handicap_away_win": european_probabilities.handicap_away_win,
        }

    if correct_score_top_n is not None:
        payload["correct_score_top_n"] = [
            {
                "home_goals": score.home_goals,
                "away_goals": score.away_goals,
                "probability": score.probability,
                "option_key": score.option_key,
            }
            for score in resolve_correct_score(score_grid, top_n=correct_score_top_n)
        ]

    return payload
