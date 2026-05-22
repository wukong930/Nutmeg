from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from numbers import Real
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.providers.the_odds_api.normalizer import (
    NormalizedOddsSnapshot,
    OddsMarketType,
)

LineupType = Literal["expected", "confirmed", "unknown"]
AvailabilityStatus = Literal["injured", "suspended", "doubtful", "available", "unknown"]


class NormalizedLineupSnapshot(BaseModel):
    provider: str = "sportmonks"
    provider_fixture_id: str
    provider_team_id: str
    provider_player_id: str | None = None
    player_name: str | None = None
    lineup_type: LineupType
    position: str | None = None
    probability_start: float | None = Field(default=None, ge=0.0, le=1.0)
    is_starter: bool | None = None
    source: str = "sportmonks"
    snapshot_time_utc: datetime


class NormalizedPlayerAvailabilitySnapshot(BaseModel):
    provider: str = "sportmonks"
    provider_fixture_id: str | None = None
    provider_team_id: str
    provider_player_id: str | None = None
    player_name: str | None = None
    status: AvailabilityStatus
    reason: str | None = None
    expected_return_date: date | None = None
    source: str = "sportmonks"
    source_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    snapshot_time_utc: datetime


def normalize_lineups(
    payload: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    provider_fixture_id: str,
    snapshot_time_utc: datetime | None = None,
) -> list[NormalizedLineupSnapshot]:
    fallback_snapshot_time = _aware_utc(snapshot_time_utc or datetime.now(UTC))
    rows: list[NormalizedLineupSnapshot] = []
    for item in _records(payload):
        team = _dict(item.get("team")) or _dict(item.get("participant"))
        player = _dict(item.get("player"))
        provider_team_id = _first_text(
            item,
            ("team_id", "participant_id", "participantId"),
            fallback=_first_text(team, ("id", "team_id")),
        )
        if provider_team_id is None:
            continue
        rows.append(
            NormalizedLineupSnapshot(
                provider_fixture_id=_first_text(item, ("fixture_id", "fixtureId"))
                or provider_fixture_id,
                provider_team_id=provider_team_id,
                provider_player_id=_first_text(
                    item,
                    ("player_id", "playerId"),
                    fallback=_first_text(player, ("id", "player_id")),
                ),
                player_name=_first_text(
                    item,
                    ("player_name", "playerName", "display_name", "name"),
                    fallback=_first_text(player, ("display_name", "name", "common_name")),
                ),
                lineup_type=_lineup_type(item),
                position=_position(item),
                probability_start=_probability(item),
                is_starter=_starter(item),
                snapshot_time_utc=_timestamp(item, fallback_snapshot_time),
            )
        )
    return rows


def normalize_injuries(
    payload: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    provider_team_id: str,
    provider_fixture_id: str | None = None,
    snapshot_time_utc: datetime | None = None,
) -> list[NormalizedPlayerAvailabilitySnapshot]:
    fallback_snapshot_time = _aware_utc(snapshot_time_utc or datetime.now(UTC))
    rows: list[NormalizedPlayerAvailabilitySnapshot] = []
    for item in _records(payload):
        team = _dict(item.get("team")) or _dict(item.get("participant"))
        player = _dict(item.get("player"))
        row_team_id = _first_text(
            item,
            ("team_id", "participant_id", "participantId"),
            fallback=_first_text(team, ("id", "team_id")) or provider_team_id,
        )
        if row_team_id is None:
            continue
        rows.append(
            NormalizedPlayerAvailabilitySnapshot(
                provider_fixture_id=_first_text(item, ("fixture_id", "fixtureId"))
                or provider_fixture_id,
                provider_team_id=row_team_id,
                provider_player_id=_first_text(
                    item,
                    ("player_id", "playerId"),
                    fallback=_first_text(player, ("id", "player_id")),
                ),
                player_name=_first_text(
                    item,
                    ("player_name", "playerName", "display_name", "name"),
                    fallback=_first_text(player, ("display_name", "name", "common_name")),
                ),
                status=_availability_status(item),
                reason=_reason(item),
                expected_return_date=_optional_date(
                    _first_text(
                        item,
                        (
                            "expected_return_date",
                            "expectedReturnDate",
                            "return_date",
                            "returnDate",
                        ),
                    )
                ),
                source_confidence=_probability_like(item, ("confidence", "source_confidence")),
                snapshot_time_utc=_timestamp(item, fallback_snapshot_time),
            )
        )
    return rows


def normalize_odds(
    payload: Mapping[str, object] | Sequence[Mapping[str, object]],
    *,
    provider_fixture_id: str,
    snapshot_time_utc: datetime | None = None,
) -> list[NormalizedOddsSnapshot]:
    fallback_snapshot_time = _aware_utc(snapshot_time_utc or datetime.now(UTC))
    rows: list[NormalizedOddsSnapshot] = []
    for item in _records(payload):
        bookmaker = _bookmaker_key(item)
        market_key, market_type = _odds_market(item)
        if market_type == "unsupported":
            continue
        decimal_odds = _decimal_odds(item)
        if decimal_odds is None:
            continue
        outcome, side = _odds_outcome(item, market_type=market_type)
        if outcome is None:
            continue
        rows.append(
            NormalizedOddsSnapshot(
                provider="sportmonks",
                provider_event_id=_first_text(item, ("fixture_id", "fixtureId"))
                or provider_fixture_id,
                sport_key="football",
                bookmaker=bookmaker,
                market_type=market_type,
                market_key=market_key,
                side=side,
                outcome=outcome,
                line=_odds_line(item),
                decimal_odds=decimal_odds,
                raw_implied_probability=1.0 / decimal_odds,
                snapshot_time_utc=_timestamp(item, fallback_snapshot_time),
            )
        )
    return _with_fair_probabilities(rows)


def _records(
    payload: Mapping[str, object] | Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, Mapping)]
        if isinstance(data, Mapping):
            nested = data.get("data")
            if isinstance(nested, list):
                return [dict(item) for item in nested if isinstance(item, Mapping)]
            for key in ("lineups", "injuries", "sidelined"):
                value = data.get(key)
                if isinstance(value, Mapping):
                    nested_data = value.get("data")
                    if isinstance(nested_data, list):
                        return [
                            dict(item)
                            for item in nested_data
                            if isinstance(item, Mapping)
                        ]
                if isinstance(value, list):
                    return [dict(item) for item in value if isinstance(item, Mapping)]
            odds = data.get("odds")
            if isinstance(odds, Mapping):
                nested_data = odds.get("data")
                if isinstance(nested_data, list):
                    return [dict(item) for item in nested_data if isinstance(item, Mapping)]
            if isinstance(odds, list):
                return [dict(item) for item in odds if isinstance(item, Mapping)]
            return [dict(data)]
        return []
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def _dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_text(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
    *,
    fallback: str | None = None,
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return fallback


def _lineup_type(item: Mapping[str, object]) -> LineupType:
    raw_text = " ".join(
        text
        for text in [
            _first_text(item, ("lineup_type", "lineupType", "type", "name")),
            _first_text(_dict(item.get("type")), ("name", "code")),
        ]
        if text is not None
    ).lower()
    if "expected" in raw_text or "probable" in raw_text:
        return "expected"
    if "confirmed" in raw_text or "starting" in raw_text or "official" in raw_text:
        return "confirmed"
    return "unknown"


def _availability_status(item: Mapping[str, object]) -> AvailabilityStatus:
    raw_text = " ".join(
        text
        for text in [
            _first_text(item, ("status", "type", "category")),
            _first_text(_dict(item.get("type")), ("name", "code")),
            _first_text(_dict(item.get("reason")), ("name", "code")),
        ]
        if text is not None
    ).lower()
    if "suspend" in raw_text or "ban" in raw_text:
        return "suspended"
    if "doubt" in raw_text or "question" in raw_text:
        return "doubtful"
    if "available" in raw_text or "fit" in raw_text:
        return "available"
    if "injur" in raw_text or "out" in raw_text or "sidelined" in raw_text:
        return "injured"
    return "unknown"


def _bookmaker_key(item: Mapping[str, object]) -> str:
    bookmaker = _dict(item.get("bookmaker"))
    return (
        _first_text(
            item,
            (
                "bookmaker",
                "bookmaker_name",
                "bookmakerName",
                "bookmaker_id",
                "bookmakerId",
            ),
            fallback=_first_text(bookmaker, ("name", "code", "id")),
        )
        or "unknown"
    )


def _odds_market(item: Mapping[str, object]) -> tuple[str, OddsMarketType]:
    market = _dict(item.get("market"))
    raw = (
        _first_text(
            item,
            (
                "market_key",
                "marketKey",
                "market_name",
                "marketName",
                "market",
            ),
            fallback=_first_text(market, ("key", "code", "name")),
        )
        or "unknown"
    )
    normalized = raw.strip().lower()
    if normalized in {"1x2", "h2h", "match winner", "fulltime result", "3way result"}:
        return raw, "1x2"
    if "1x2" in normalized or "match winner" in normalized or "3way" in normalized:
        return raw, "1x2"
    if "asian handicap" in normalized or normalized in {"spreads", "handicap"}:
        return raw, "asian_handicap"
    if "over/under" in normalized or normalized in {"totals", "total goals"}:
        return raw, "totals"
    return raw, "unsupported"


def _odds_outcome(
    item: Mapping[str, object],
    *,
    market_type: OddsMarketType,
) -> tuple[str | None, str | None]:
    label = (
        _first_text(
            item,
            (
                "outcome",
                "outcome_name",
                "outcomeName",
                "label",
                "name",
                "selection",
                "type",
            ),
            fallback=_first_text(_dict(item.get("outcome")), ("name", "label", "code")),
        )
        or ""
    )
    normalized = label.strip().lower()
    if market_type == "1x2":
        if normalized in {"home", "home win", "1", "team1", "team 1"}:
            return "home_win", None
        if normalized in {"draw", "x"}:
            return "draw", None
        if normalized in {"away", "away win", "2", "team2", "team 2"}:
            return "away_win", None
        return None, None
    if market_type == "asian_handicap":
        if normalized in {"home", "home win", "1", "team1", "team 1"}:
            return "cover", "home"
        if normalized in {"away", "away win", "2", "team2", "team 2"}:
            return "cover", "away"
        return None, None
    if market_type == "totals":
        if normalized in {"over", "under"}:
            return normalized, normalized
        return None, None
    return None, None


def _decimal_odds(item: Mapping[str, object]) -> float | None:
    value = _first_value(
        item,
        (
            "decimal_odds",
            "decimalOdds",
            "decimal",
            "odds",
            "price",
            "value",
        ),
    )
    if isinstance(value, Mapping):
        value = _first_value(value, ("decimal", "odds", "value"))
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (Real, str)):
        return None
    number = float(value)
    return number if number > 1.0 else None


def _odds_line(item: Mapping[str, object]) -> float | None:
    value = _first_value(
        item,
        ("line", "point", "handicap", "handicap_value", "handicapValue", "total"),
    )
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (Real, str)):
        return None
    return float(value)


def _with_fair_probabilities(
    rows: list[NormalizedOddsSnapshot],
) -> list[NormalizedOddsSnapshot]:
    groups: dict[tuple[str, str, str, str, float | None], list[NormalizedOddsSnapshot]] = {}
    for row in rows:
        line = (
            abs(row.line)
            if row.market_type == "asian_handicap" and row.line is not None
            else row.line
        )
        key = (row.provider_event_id, row.bookmaker, row.market_type, row.market_key, line)
        groups.setdefault(key, []).append(row)

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


def _first_value(mapping: Mapping[str, object], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _position(item: Mapping[str, object]) -> str | None:
    position = _dict(item.get("position"))
    return _first_text(
        item,
        ("position", "formation_position", "formationPosition"),
        fallback=_first_text(position, ("name", "code", "display_name")),
    )


def _reason(item: Mapping[str, object]) -> str | None:
    reason = _dict(item.get("reason"))
    type_value = _dict(item.get("type"))
    return _first_text(
        item,
        ("reason", "details", "comment", "note"),
        fallback=_first_text(reason, ("name", "code"))
        or _first_text(type_value, ("name", "code")),
    )


def _starter(item: Mapping[str, object]) -> bool | None:
    for key in ("is_starter", "isStarter", "starter", "starting"):
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "starter", "starting"}:
                return True
            if normalized in {"false", "0", "no", "bench", "substitute"}:
                return False
    lineup_type = _lineup_type(item)
    if lineup_type == "confirmed":
        type_text = _first_text(item, ("type", "lineup_type", "lineupType"))
        return not (type_text is not None and "bench" in type_text.lower())
    return None


def _probability(item: Mapping[str, object]) -> float | None:
    return _probability_like(
        item,
        (
            "probability_start",
            "probabilityStart",
            "probability",
            "start_probability",
            "startProbability",
        ),
    )


def _probability_like(item: Mapping[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None or isinstance(value, bool):
            continue
        if not isinstance(value, (Real, str)):
            continue
        number = float(value)
        if number > 1.0:
            number = number / 100.0
        return max(0.0, min(1.0, number))
    return None


def _timestamp(item: Mapping[str, object], fallback: datetime) -> datetime:
    value = _first_text(
        item,
        (
            "snapshot_time_utc",
            "snapshotTimeUtc",
            "updated_at",
            "updatedAt",
            "last_update",
            "lastUpdate",
            "created_at",
            "createdAt",
        ),
    )
    if value is None:
        return fallback
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value[:10])


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
