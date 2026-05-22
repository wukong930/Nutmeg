from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.market_resolver.settlement import (
    settle_1x2,
    settle_asian_handicap,
    settle_cn_handicap_1x2,
    settle_european_handicap_1x2,
)

ParlayAtomicResultStatus = Literal["won", "lost", "unresolved"]


class ParlayLegSettlement(BaseModel):
    fixture_id: str
    market_type: str
    selected_outcome: str
    actual_outcome: str | None = None
    hit: bool | None = None
    reason: str | None = None


class ParlayAtomicSettlement(BaseModel):
    result_status: ParlayAtomicResultStatus
    gross_payout: float = Field(ge=0.0)
    profit_loss: float
    leg_results: list[ParlayLegSettlement] = Field(default_factory=list)
    unresolved_reasons: list[str] = Field(default_factory=list)

    @property
    def is_settled(self) -> bool:
        return self.result_status in {"won", "lost"}

    @property
    def detail_json(self) -> dict[str, object]:
        return {
            "result_status": self.result_status,
            "gross_payout": self.gross_payout,
            "profit_loss": self.profit_loss,
            "leg_results": [
                leg_result.model_dump(mode="json") for leg_result in self.leg_results
            ],
            "unresolved_reasons": self.unresolved_reasons,
            "calculation_basis": "all_atomic_legs_must_match_actual_settlement",
        }


def settle_parlay_atomic_bet(
    outcomes: Sequence[Mapping[str, object]],
    result_rows: Sequence[Mapping[str, object]],
    *,
    stake: float,
    odds_product: float,
) -> ParlayAtomicSettlement:
    if stake <= 0:
        raise ValueError("stake must be positive")
    if odds_product <= 1:
        raise ValueError("odds_product must be greater than 1")
    if not outcomes:
        return _unresolved(stake=stake, reason="empty_atomic_bet_outcomes")

    results_by_fixture = {
        str(row["fixture_id"]): row
        for row in result_rows
        if row.get("fixture_id") is not None
    }
    leg_results: list[ParlayLegSettlement] = []
    unresolved_reasons: list[str] = []
    for leg in outcomes:
        fixture_id = _optional_str(leg.get("fixture_id"))
        market_type = _optional_str(leg.get("market_type"))
        selected_outcome = _optional_str(leg.get("outcome"))
        if fixture_id is None or market_type is None or selected_outcome is None:
            unresolved_reasons.append("atomic_leg_missing_required_fields")
            continue
        result = results_by_fixture.get(fixture_id)
        if result is None:
            unresolved_reasons.append(f"result_missing:{fixture_id}")
            leg_results.append(
                ParlayLegSettlement(
                    fixture_id=fixture_id,
                    market_type=market_type,
                    selected_outcome=selected_outcome,
                    reason="result_missing",
                )
            )
            continue
        actual_outcome = actual_outcome_for_parlay_leg(leg, result)
        if actual_outcome is None:
            unresolved_reasons.append(f"unsupported_or_incomplete_market:{fixture_id}")
            leg_results.append(
                ParlayLegSettlement(
                    fixture_id=fixture_id,
                    market_type=market_type,
                    selected_outcome=selected_outcome,
                    reason="unsupported_or_incomplete_market",
                )
            )
            continue
        leg_results.append(
            ParlayLegSettlement(
                fixture_id=fixture_id,
                market_type=market_type,
                selected_outcome=selected_outcome,
                actual_outcome=actual_outcome,
                hit=actual_outcome == selected_outcome,
            )
        )

    if unresolved_reasons:
        return ParlayAtomicSettlement(
            result_status="unresolved",
            gross_payout=0.0,
            profit_loss=0.0,
            leg_results=leg_results,
            unresolved_reasons=unresolved_reasons,
        )

    won = all(leg.hit is True for leg in leg_results)
    gross_payout = stake * odds_product if won else 0.0
    return ParlayAtomicSettlement(
        result_status="won" if won else "lost",
        gross_payout=gross_payout,
        profit_loss=gross_payout - stake,
        leg_results=leg_results,
    )


def actual_outcome_for_parlay_leg(
    leg: Mapping[str, object],
    result: Mapping[str, object],
) -> str | None:
    market_type = (_optional_str(leg.get("market_type")) or "").lower()
    home_goals = _int(result["home_goals"])
    away_goals = _int(result["away_goals"])
    if market_type in {"1x2", "asian_1x2"}:
        return settle_1x2(home_goals, away_goals).value
    if market_type in {"cn_handicap_1x2", "european_handicap_1x2"}:
        line = _optional_float(leg.get("line"))
        if line is None:
            return None
        handicap = int(round(line))
        if market_type == "european_handicap_1x2":
            return settle_european_handicap_1x2(
                home_goals,
                away_goals,
                handicap=handicap,
            ).value
        return settle_cn_handicap_1x2(
            home_goals,
            away_goals,
            handicap=handicap,
        ).value
    if market_type == "asian_handicap":
        line = _optional_float(leg.get("line"))
        if line is None:
            return None
        return settle_asian_handicap(
            home_goals,
            away_goals,
            line=line,
            side=_optional_str(leg.get("side")) or "home",
        ).value
    if market_type == "correct_score":
        return f"{home_goals}-{away_goals}"
    return None


def _unresolved(*, stake: float, reason: str) -> ParlayAtomicSettlement:
    return ParlayAtomicSettlement(
        result_status="unresolved",
        gross_payout=0.0,
        profit_loss=0.0,
        unresolved_reasons=[reason],
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    return float(str(value))
