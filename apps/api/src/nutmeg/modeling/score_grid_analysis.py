from __future__ import annotations

from nutmeg.domain.score_grid import ScoreGridTailMetrics, ScoreProbability, ScoreProbabilityGrid


def top_score_probabilities(
    score_grid: ScoreProbabilityGrid,
    *,
    top_n: int = 5,
) -> list[ScoreProbability]:
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    return sorted(score_grid.iter_scores(), key=lambda score: score.probability, reverse=True)[
        :top_n
    ]


def score_grid_tail_metrics(score_grid: ScoreProbabilityGrid) -> ScoreGridTailMetrics:
    home_win_by_3plus = 0.0
    away_win_by_3plus = 0.0
    any_team_4plus_goals = 0.0
    total_goals_5plus = 0.0
    for score in score_grid.iter_scores():
        margin = score.home_goals - score.away_goals
        if margin >= 3:
            home_win_by_3plus += score.probability
        if margin <= -3:
            away_win_by_3plus += score.probability
        if score.home_goals >= 4 or score.away_goals >= 4:
            any_team_4plus_goals += score.probability
        if score.home_goals + score.away_goals >= 5:
            total_goals_5plus += score.probability

    blowout_signal = max(
        home_win_by_3plus,
        away_win_by_3plus,
        any_team_4plus_goals,
        score_grid.tail_mass,
    )
    if blowout_signal >= 0.18:
        blowout_tail_risk = "high"
    elif blowout_signal >= 0.08:
        blowout_tail_risk = "medium"
    else:
        blowout_tail_risk = "low"

    return ScoreGridTailMetrics(
        truncated_tail_mass=score_grid.tail_mass,
        home_win_by_3plus=home_win_by_3plus,
        away_win_by_3plus=away_win_by_3plus,
        any_team_4plus_goals=any_team_4plus_goals,
        total_goals_5plus=total_goals_5plus,
        blowout_tail_risk=blowout_tail_risk,
    )
