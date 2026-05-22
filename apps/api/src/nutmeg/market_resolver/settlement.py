from __future__ import annotations

from math import isclose

from nutmeg.domain.settlement import (
    AsianHandicapSettlement,
    HandicapOneXTwoOutcome,
    OneXTwoOutcome,
)

ListedScoreOptions = set[tuple[int, int]]


def _validate_goals(home_goals: int, away_goals: int) -> None:
    if home_goals < 0 or away_goals < 0:
        raise ValueError("goals must be non-negative")


def settle_1x2(home_goals: int, away_goals: int) -> OneXTwoOutcome:
    _validate_goals(home_goals, away_goals)
    if home_goals > away_goals:
        return OneXTwoOutcome.HOME_WIN
    if home_goals == away_goals:
        return OneXTwoOutcome.DRAW
    return OneXTwoOutcome.AWAY_WIN


def settle_asian_1x2(home_goals: int, away_goals: int) -> OneXTwoOutcome:
    """Settle a provider-normalized Asian three-way 1X2 market.

    Some providers label the ordinary three-way result market by region. After
    normalization, its settlement is identical to standard 1X2.
    """

    return settle_1x2(home_goals, away_goals)


def settle_handicap_1x2(
    home_goals: int,
    away_goals: int,
    *,
    handicap: int,
) -> HandicapOneXTwoOutcome:
    _validate_goals(home_goals, away_goals)
    adjusted_home_goals = home_goals + handicap
    if adjusted_home_goals > away_goals:
        return HandicapOneXTwoOutcome.HANDICAP_HOME_WIN
    if adjusted_home_goals == away_goals:
        return HandicapOneXTwoOutcome.HANDICAP_DRAW
    return HandicapOneXTwoOutcome.HANDICAP_AWAY_WIN


def settle_cn_handicap_1x2(
    home_goals: int,
    away_goals: int,
    *,
    handicap: int,
) -> HandicapOneXTwoOutcome:
    return settle_handicap_1x2(home_goals, away_goals, handicap=handicap)


def settle_european_handicap_1x2(
    home_goals: int,
    away_goals: int,
    *,
    handicap: int,
) -> HandicapOneXTwoOutcome:
    return settle_handicap_1x2(home_goals, away_goals, handicap=handicap)


def split_asian_handicap_line(line: float) -> tuple[float, ...]:
    quarter_units = line * 4
    if not isclose(quarter_units, round(quarter_units), abs_tol=1e-9):
        raise ValueError("Asian handicap line must be a multiple of 0.25")
    units = int(round(quarter_units))
    if units % 2 == 0:
        return (units / 4,)
    return ((units - 1) / 4, (units + 1) / 4)


def _settle_single_asian_line(margin: int, line: float) -> AsianHandicapSettlement:
    adjusted_margin = margin + line
    if adjusted_margin > 0:
        return AsianHandicapSettlement.FULL_WIN
    if adjusted_margin < 0:
        return AsianHandicapSettlement.FULL_LOSS
    return AsianHandicapSettlement.PUSH


def combine_asian_handicap_split_settlement(
    settlements: tuple[AsianHandicapSettlement, ...],
) -> AsianHandicapSettlement:
    if len(settlements) == 1:
        return settlements[0]
    wins = sum(1 for settlement in settlements if settlement is AsianHandicapSettlement.FULL_WIN)
    pushes = sum(1 for settlement in settlements if settlement is AsianHandicapSettlement.PUSH)
    losses = sum(1 for settlement in settlements if settlement is AsianHandicapSettlement.FULL_LOSS)
    if wins == 2:
        return AsianHandicapSettlement.FULL_WIN
    if wins == 1 and pushes == 1:
        return AsianHandicapSettlement.HALF_WIN
    if pushes == 2:
        return AsianHandicapSettlement.PUSH
    if pushes == 1 and losses == 1:
        return AsianHandicapSettlement.HALF_LOSS
    if losses == 2:
        return AsianHandicapSettlement.FULL_LOSS
    raise ValueError(f"unsupported Asian handicap settlement combination: {settlements}")


def settle_asian_handicap(
    home_goals: int,
    away_goals: int,
    *,
    line: float,
    side: str = "home",
) -> AsianHandicapSettlement:
    _validate_goals(home_goals, away_goals)
    if side not in {"home", "away"}:
        raise ValueError("side must be 'home' or 'away'")
    margin = home_goals - away_goals if side == "home" else away_goals - home_goals
    settlements = tuple(
        _settle_single_asian_line(margin, split_line)
        for split_line in split_asian_handicap_line(line)
    )
    return combine_asian_handicap_split_settlement(settlements)


def settle_correct_score(
    home_goals: int,
    away_goals: int,
    *,
    selected_home_goals: int,
    selected_away_goals: int,
) -> bool:
    _validate_goals(home_goals, away_goals)
    _validate_goals(selected_home_goals, selected_away_goals)
    return home_goals == selected_home_goals and away_goals == selected_away_goals


def correct_score_option_key(
    home_goals: int,
    away_goals: int,
    *,
    listed_options: ListedScoreOptions,
) -> str:
    _validate_goals(home_goals, away_goals)
    if (home_goals, away_goals) in listed_options:
        return f"{home_goals}-{away_goals}"
    if home_goals > away_goals:
        return "home_other"
    if home_goals == away_goals:
        return "draw_other"
    return "away_other"
