from __future__ import annotations

from nutmeg.domain.market import CorrectScoreProbability
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver.settlement import correct_score_option_key

DEFAULT_LISTED_SCORE_OPTIONS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 0),
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
        (3, 2),
        (4, 0),
        (4, 1),
        (4, 2),
        (5, 0),
        (5, 1),
        (5, 2),
        (0, 0),
        (1, 1),
        (2, 2),
        (3, 3),
        (0, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (2, 3),
        (0, 4),
        (1, 4),
        (2, 4),
        (0, 5),
        (1, 5),
        (2, 5),
    }
)


def resolve_correct_score(
    score_grid: ScoreProbabilityGrid,
    *,
    top_n: int = 5,
    listed_options: set[tuple[int, int]] | None = None,
) -> list[CorrectScoreProbability]:
    options = listed_options or set(DEFAULT_LISTED_SCORE_OPTIONS)
    scores = [
        CorrectScoreProbability(
            home_goals=score.home_goals,
            away_goals=score.away_goals,
            probability=score.probability,
            option_key=correct_score_option_key(
                score.home_goals,
                score.away_goals,
                listed_options=options,
            ),
        )
        for score in score_grid.iter_scores()
    ]
    return sorted(scores, key=lambda score: score.probability, reverse=True)[:top_n]
