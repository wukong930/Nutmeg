from __future__ import annotations

from enum import StrEnum


class OneXTwoOutcome(StrEnum):
    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"


class HandicapOneXTwoOutcome(StrEnum):
    HANDICAP_HOME_WIN = "handicap_home_win"
    HANDICAP_DRAW = "handicap_draw"
    HANDICAP_AWAY_WIN = "handicap_away_win"


class AsianHandicapSettlement(StrEnum):
    FULL_WIN = "full_win"
    HALF_WIN = "half_win"
    PUSH = "push"
    HALF_LOSS = "half_loss"
    FULL_LOSS = "full_loss"
