from __future__ import annotations

from nutmeg.accuracy.metrics import expected_total_goals
from nutmeg.domain.accuracy import ActualMatchResult
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.settlement import OneXTwoOutcome


def classify_prediction_error(
    snapshot: PredictionSnapshot,
    actual_result: ActualMatchResult,
    *,
    predicted_outcome: OneXTwoOutcome,
    actual_outcome_probability: float,
    actual_score_probability: float,
) -> list[str]:
    tags: list[str] = []
    actual_outcome = actual_result.result_1x2
    actual_total_goals = actual_result.home_goals + actual_result.away_goals
    predicted_total_goals = expected_total_goals(snapshot.score_grid)

    if predicted_outcome is not actual_outcome:
        if predicted_outcome is OneXTwoOutcome.HOME_WIN and snapshot.p_home >= 0.50:
            tags.append("favorite_overestimated")
        if actual_outcome is OneXTwoOutcome.DRAW and snapshot.p_draw <= 0.25:
            tags.append("draw_underestimated")
        if actual_outcome_probability <= 0.25 and actual_outcome is not OneXTwoOutcome.DRAW:
            tags.append("underdog_underestimated")
        if actual_outcome is OneXTwoOutcome.AWAY_WIN and snapshot.p_home > snapshot.p_away + 0.15:
            tags.append("home_advantage_overestimated")

    if predicted_total_goals >= actual_total_goals + 1.25:
        tags.append("goals_overestimated")
    elif predicted_total_goals + 1.25 <= actual_total_goals:
        tags.append("goals_underestimated")

    if actual_total_goals <= 2 and actual_score_probability <= 0.08:
        tags.append("low_score_correlation_miss")

    is_blowout = abs(actual_result.home_goals - actual_result.away_goals) >= 3
    if is_blowout and actual_score_probability <= 0.03:
        tags.append("blowout_tail_underestimated")

    return tags
