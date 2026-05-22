from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from numbers import Real
from typing import Literal

from pydantic import BaseModel, Field

OddsMarketType = Literal["1x2", "asian_handicap", "totals", "unsupported"]


class NormalizedOddsSnapshot(BaseModel):
    provider: str = "the-odds-api"
    provider_event_id: str
    sport_key: str
    bookmaker: str
    market_type: OddsMarketType
    market_key: str
    side: str | None = None
    outcome: str
    line: float | None = None
    decimal_odds: float = Field(gt=1.0)
    raw_implied_probability: float = Field(gt=0.0)
    fair_probability: float | None = Field(default=None, gt=0.0, le=1.0)
    overround: float | None = None
    snapshot_time_utc: datetime


def normalize_event_odds(
    payload: dict[str, object],
    *,
    snapshot_time_utc: datetime | None = None,
) -> list[NormalizedOddsSnapshot]:
    provider_event_id = _required_text(payload.get("id"), "event.id")
    sport_key = _required_text(payload.get("sport_key"), "event.sport_key")
    home_team = _optional_text(payload.get("home_team"))
    away_team = _optional_text(payload.get("away_team"))
    fallback_time = snapshot_time_utc or _datetime_or_now(payload.get("commence_time"))

    rows: list[NormalizedOddsSnapshot] = []
    for bookmaker in _list(payload.get("bookmakers")):
        bookmaker_key = _required_text(bookmaker.get("key"), "bookmaker.key")
        bookmaker_time = _optional_datetime(bookmaker.get("last_update")) or fallback_time
        for market in _list(bookmaker.get("markets")):
            market_key = _required_text(market.get("key"), "market.key")
            market_time = _optional_datetime(market.get("last_update")) or bookmaker_time
            for outcome in _list(market.get("outcomes")):
                normalized = _normalize_outcome(
                    outcome,
                    provider_event_id=provider_event_id,
                    sport_key=sport_key,
                    bookmaker=bookmaker_key,
                    market_key=market_key,
                    home_team=home_team,
                    away_team=away_team,
                    snapshot_time_utc=market_time,
                )
                if normalized is not None:
                    rows.append(normalized)

    return _with_fair_probabilities(rows)


def _normalize_outcome(
    payload: dict[str, object],
    *,
    provider_event_id: str,
    sport_key: str,
    bookmaker: str,
    market_key: str,
    home_team: str | None,
    away_team: str | None,
    snapshot_time_utc: datetime,
) -> NormalizedOddsSnapshot | None:
    name = _required_text(payload.get("name"), "outcome.name")
    price = _float(payload.get("price"), "outcome.price")
    line = _optional_float(payload.get("point"))
    market_type = _market_type(market_key)
    if market_type == "unsupported":
        return None

    outcome_key, side = _outcome_and_side(
        name,
        market_type=market_type,
        home_team=home_team,
        away_team=away_team,
    )
    if outcome_key is None:
        return None

    return NormalizedOddsSnapshot(
        provider_event_id=provider_event_id,
        sport_key=sport_key,
        bookmaker=bookmaker,
        market_type=market_type,
        market_key=market_key,
        side=side,
        outcome=outcome_key,
        line=line,
        decimal_odds=price,
        raw_implied_probability=1.0 / price,
        snapshot_time_utc=snapshot_time_utc,
    )


def _with_fair_probabilities(
    rows: list[NormalizedOddsSnapshot],
) -> list[NormalizedOddsSnapshot]:
    groups: dict[tuple[str, str, str, str, float | None], list[NormalizedOddsSnapshot]] = (
        defaultdict(list)
    )
    for row in rows:
        groups[
            (
                row.provider_event_id,
                row.bookmaker,
                row.market_type,
                row.market_key,
                _group_line(row),
            )
        ].append(row)

    normalized_rows: list[NormalizedOddsSnapshot] = []
    for group in groups.values():
        implied_sum = sum(row.raw_implied_probability for row in group)
        overround = implied_sum - 1.0 if implied_sum > 0 else None
        for row in group:
            normalized_rows.append(
                row.model_copy(
                    update={
                        "fair_probability": row.raw_implied_probability / implied_sum
                        if implied_sum > 0
                        else None,
                        "overround": overround,
                    }
                )
            )
    return normalized_rows


def _group_line(row: NormalizedOddsSnapshot) -> float | None:
    if row.market_type == "asian_handicap" and row.line is not None:
        return abs(row.line)
    return row.line


def _market_type(market_key: str) -> OddsMarketType:
    if market_key == "h2h":
        return "1x2"
    if market_key == "spreads":
        return "asian_handicap"
    if market_key == "totals":
        return "totals"
    return "unsupported"


def _outcome_and_side(
    name: str,
    *,
    market_type: OddsMarketType,
    home_team: str | None,
    away_team: str | None,
) -> tuple[str | None, str | None]:
    normalized_name = name.strip().lower()
    if market_type == "1x2":
        if home_team and name == home_team:
            return "home_win", None
        if away_team and name == away_team:
            return "away_win", None
        if normalized_name == "draw":
            return "draw", None
        return None, None
    if market_type == "asian_handicap":
        if home_team and name == home_team:
            return "cover", "home"
        if away_team and name == away_team:
            return "cover", "away"
        return None, None
    if market_type == "totals":
        if normalized_name in {"over", "under"}:
            return normalized_name, normalized_name
        return None, None
    return None, None


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"missing required The Odds API field: {field_name}")
    return str(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"expected numeric The Odds API field: {field_name}")
    if not isinstance(value, (Real, str)):
        raise ValueError(f"expected numeric The Odds API field: {field_name}")
    number = float(value)
    if number <= 1.0:
        raise ValueError(f"expected decimal odds > 1.0 for {field_name}")
    return number


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected numeric line")
    if not isinstance(value, (Real, str)):
        raise ValueError("expected numeric line")
    return float(value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _datetime_or_now(value: object) -> datetime:
    parsed = _optional_datetime(value)
    if parsed is not None:
        return parsed
    return datetime.now(UTC)
