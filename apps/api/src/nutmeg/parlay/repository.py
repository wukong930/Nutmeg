from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps, loads
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.parlay import AtomicBet
from nutmeg.parlay.settlement import ParlayAtomicSettlement, settle_parlay_atomic_bet

UPSERT_PARLAY_MODEL_VERSION_QUERY = """
INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  metrics_json,
  params_json
) VALUES (
  %(model_version)s,
  %(model_family)s,
  %(status)s,
  %(metrics_json)s::jsonb,
  %(params_json)s::jsonb
)
ON CONFLICT (model_version) DO UPDATE SET
  metrics_json = model_versions.metrics_json || EXCLUDED.metrics_json,
  params_json = model_versions.params_json || EXCLUDED.params_json
RETURNING model_version
"""

INSERT_PARLAY_RECOMMENDATION_QUERY = """
INSERT INTO parlay_recommendations (
  model_version,
  strategy,
  pass_type,
  is_multiple,
  unit_stake,
  multiplier,
  total_atomic_bets,
  total_stake,
  hit_probability,
  expected_payout,
  expected_value,
  roi,
  risk_score,
  risk_level,
  correlation_penalty,
  recommendation_score,
  rule_valid,
  explanation_json,
  prediction_snapshot_ids_json,
  source
) VALUES (
  %(model_version)s,
  %(strategy)s,
  %(pass_type)s,
  %(is_multiple)s,
  %(unit_stake)s,
  %(multiplier)s,
  %(total_atomic_bets)s,
  %(total_stake)s,
  %(hit_probability)s,
  %(expected_payout)s,
  %(expected_value)s,
  %(roi)s,
  %(risk_score)s,
  %(risk_level)s,
  %(correlation_penalty)s,
  %(recommendation_score)s,
  %(rule_valid)s,
  %(explanation_json)s::jsonb,
  %(prediction_snapshot_ids_json)s::jsonb,
  %(source)s
)
RETURNING parlay_recommendation_id, created_at
"""

INSERT_PARLAY_LEG_QUERY = """
INSERT INTO parlay_legs (
  parlay_recommendation_id,
  leg_index,
  fixture_id,
  market_type,
  line,
  side,
  selected_outcomes_json,
  probabilities_json,
  odds_json,
  prediction_snapshot_id,
  model_version
) VALUES (
  %(parlay_recommendation_id)s,
  %(leg_index)s,
  %(fixture_id)s,
  %(market_type)s,
  %(line)s,
  %(side)s,
  %(selected_outcomes_json)s::jsonb,
  %(probabilities_json)s::jsonb,
  %(odds_json)s::jsonb,
  %(prediction_snapshot_id)s,
  %(model_version)s
)
RETURNING parlay_leg_id
"""

INSERT_PARLAY_ATOMIC_BET_QUERY = """
INSERT INTO parlay_atomic_bets (
  parlay_recommendation_id,
  outcomes_json,
  stake,
  probability,
  odds_product,
  expected_payout,
  expected_value,
  result_status,
  gross_payout,
  profit_loss,
  settlement_detail_json
) VALUES (
  %(parlay_recommendation_id)s,
  %(outcomes_json)s::jsonb,
  %(stake)s,
  %(probability)s,
  %(odds_product)s,
  %(expected_payout)s,
  %(expected_value)s,
  NULL,
  NULL,
  NULL,
  '{}'::jsonb
)
RETURNING atomic_bet_id
"""

LIST_UNSETTLED_PARLAY_ATOMIC_BETS_QUERY = """
SELECT
  pab.atomic_bet_id,
  pab.parlay_recommendation_id,
  pr.model_version,
  pab.outcomes_json,
  pab.stake,
  pab.odds_product,
  COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'fixture_id', r.fixture_id,
        'home_goals', r.home_goals,
        'away_goals', r.away_goals
      )
    ) FILTER (WHERE r.fixture_id IS NOT NULL),
    '[]'::jsonb
  ) AS result_rows_json
FROM parlay_atomic_bets pab
JOIN parlay_recommendations pr
  ON pr.parlay_recommendation_id = pab.parlay_recommendation_id
LEFT JOIN LATERAL jsonb_array_elements(pab.outcomes_json) AS leg(value)
  ON TRUE
LEFT JOIN results r
  ON r.fixture_id = leg.value->>'fixture_id'
WHERE pab.result_status IS NULL
  AND (%(model_version)s::text IS NULL OR pr.model_version = %(model_version)s::text)
GROUP BY
  pab.atomic_bet_id,
  pab.parlay_recommendation_id,
  pr.model_version,
  pab.outcomes_json,
  pab.stake,
  pab.odds_product
ORDER BY pab.atomic_bet_id ASC
LIMIT %(limit)s
"""

UPDATE_PARLAY_ATOMIC_BET_SETTLEMENT_QUERY = """
UPDATE parlay_atomic_bets
SET
  result_status = %(result_status)s,
  settled_at = %(settled_at)s,
  gross_payout = %(gross_payout)s,
  profit_loss = %(profit_loss)s,
  settlement_detail_json = %(settlement_detail_json)s::jsonb
WHERE atomic_bet_id = %(atomic_bet_id)s
RETURNING atomic_bet_id
"""

UPDATE_PARLAY_RECOMMENDATION_SETTLEMENT_SUMMARY_QUERY = """
UPDATE parlay_recommendations pr
SET settlement_summary_json = (
  SELECT jsonb_build_object(
    'settled_atomic_bets', COUNT(*),
    'won_atomic_bets', COUNT(*) FILTER (WHERE result_status = 'won'),
    'lost_atomic_bets', COUNT(*) FILTER (WHERE result_status = 'lost'),
    'gross_payout', COALESCE(SUM(gross_payout), 0),
    'profit_loss', COALESCE(SUM(profit_loss), 0),
    'settled_at_utc', %(settled_at)s
  )
  FROM parlay_atomic_bets pab
  WHERE pab.parlay_recommendation_id = pr.parlay_recommendation_id
    AND pab.result_status IS NOT NULL
)
WHERE pr.parlay_recommendation_id = %(parlay_recommendation_id)s
RETURNING parlay_recommendation_id
"""


class ParlayWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read unsettled atomic bets for settlement."""


class ParlayRecommendationWriteInput(BaseModel):
    recommendation_key: str | None = None
    model_version: str | None = None
    strategy: str
    pass_type: str
    is_multiple: bool
    unit_stake: float = Field(gt=0.0)
    multiplier: int = Field(default=1, ge=1)
    total_atomic_bets: int = Field(ge=0)
    total_stake: float = Field(ge=0.0)
    hit_probability: float = Field(ge=0.0, le=1.0)
    expected_payout: float
    expected_value: float
    roi: float
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: str
    correlation_penalty: float = Field(ge=0.0, le=1.0)
    rule_valid: bool
    explanation_json: dict[str, object] = Field(default_factory=dict)
    atomic_bets: list[AtomicBet] = Field(default_factory=list)
    recommendation_score: float | None = None
    source: str = "api_parlay_recommend"


class StoredParlayRecommendation(BaseModel):
    parlay_recommendation_id: int = Field(gt=0)
    parlay_leg_ids: list[int] = Field(default_factory=list)
    atomic_bet_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class SettledParlayAtomicBet(BaseModel):
    atomic_bet_id: int = Field(gt=0)
    parlay_recommendation_id: int = Field(gt=0)
    settlement: ParlayAtomicSettlement


class ParlaySettlementRun(BaseModel):
    checked_atomic_bets: int = Field(ge=0)
    settled_atomic_bets: int = Field(ge=0)
    unresolved_atomic_bets: int = Field(ge=0)
    settled: list[SettledParlayAtomicBet] = Field(default_factory=list)


class PostgresParlayRecommendationRepository:
    def __init__(self, database: ParlayWriteDatabaseExecutor) -> None:
        self.database = database

    def save_recommendation(
        self,
        recommendation: ParlayRecommendationWriteInput,
        *,
        ensure_model_version: bool = True,
    ) -> StoredParlayRecommendation:
        if ensure_model_version and recommendation.model_version is not None:
            self._upsert_model_version(recommendation.model_version)
        row = _required_row(
            self.database.fetch_one(
                INSERT_PARLAY_RECOMMENDATION_QUERY,
                _recommendation_params(recommendation),
            )
        )
        parlay_recommendation_id = _int(row["parlay_recommendation_id"])
        leg_ids = [
            self._insert_leg(parlay_recommendation_id, leg)
            for leg in _leg_inputs_from_atomic_bets(recommendation.atomic_bets)
        ]
        atomic_bet_ids = [
            self._insert_atomic_bet(parlay_recommendation_id, atomic_bet)
            for atomic_bet in recommendation.atomic_bets
        ]
        return StoredParlayRecommendation(
            parlay_recommendation_id=parlay_recommendation_id,
            parlay_leg_ids=leg_ids,
            atomic_bet_ids=atomic_bet_ids,
            created_at=_datetime(row["created_at"]),
        )

    def settle_unsettled_atomic_bets(
        self,
        *,
        limit: int = 100,
        model_version: str | None = None,
        settled_at: datetime | None = None,
    ) -> ParlaySettlementRun:
        checked_rows = self.database.fetch_all(
            LIST_UNSETTLED_PARLAY_ATOMIC_BETS_QUERY,
            {
                "model_version": model_version,
                "limit": max(1, limit),
            },
        )
        settled_at_utc = _aware_utc(settled_at or datetime.now(tz=UTC))
        settled_items: list[SettledParlayAtomicBet] = []
        unresolved_count = 0
        touched_recommendation_ids: set[int] = set()
        for row in checked_rows:
            settlement = settle_parlay_atomic_bet(
                _json_array(row["outcomes_json"]),
                _json_array(row["result_rows_json"]),
                stake=_float(row["stake"]),
                odds_product=_float(row["odds_product"]),
            )
            if not settlement.is_settled:
                unresolved_count += 1
                continue
            atomic_bet_id = _int(row["atomic_bet_id"])
            parlay_recommendation_id = _int(row["parlay_recommendation_id"])
            _required_row(
                self.database.fetch_one(
                    UPDATE_PARLAY_ATOMIC_BET_SETTLEMENT_QUERY,
                    {
                        "atomic_bet_id": atomic_bet_id,
                        "result_status": settlement.result_status,
                        "settled_at": settled_at_utc,
                        "gross_payout": settlement.gross_payout,
                        "profit_loss": settlement.profit_loss,
                        "settlement_detail_json": _json(settlement.detail_json),
                    },
                )
            )
            touched_recommendation_ids.add(parlay_recommendation_id)
            settled_items.append(
                SettledParlayAtomicBet(
                    atomic_bet_id=atomic_bet_id,
                    parlay_recommendation_id=parlay_recommendation_id,
                    settlement=settlement,
                )
            )
        for parlay_recommendation_id in sorted(touched_recommendation_ids):
            _required_row(
                self.database.fetch_one(
                    UPDATE_PARLAY_RECOMMENDATION_SETTLEMENT_SUMMARY_QUERY,
                    {
                        "parlay_recommendation_id": parlay_recommendation_id,
                        "settled_at": settled_at_utc.isoformat(),
                    },
                )
            )
        return ParlaySettlementRun(
            checked_atomic_bets=len(checked_rows),
            settled_atomic_bets=len(settled_items),
            unresolved_atomic_bets=unresolved_count,
            settled=settled_items,
        )

    def _upsert_model_version(self, model_version: str) -> None:
        _required_row(
            self.database.fetch_one(
                UPSERT_PARLAY_MODEL_VERSION_QUERY,
                {
                    "model_version": model_version,
                    "model_family": _model_family(model_version),
                    "status": "active",
                    "metrics_json": _json({"source": "parlay_recommendation"}),
                    "params_json": _json({"source": "parlay_repository"}),
                },
            )
        )

    def _insert_leg(
        self,
        parlay_recommendation_id: int,
        leg: _ParlayLegWriteInput,
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PARLAY_LEG_QUERY,
                {
                    "parlay_recommendation_id": parlay_recommendation_id,
                    "leg_index": leg.leg_index,
                    "fixture_id": leg.fixture_id,
                    "market_type": leg.market_type,
                    "line": leg.line,
                    "side": leg.side,
                    "selected_outcomes_json": _json(leg.selected_outcomes),
                    "probabilities_json": _json(leg.probabilities),
                    "odds_json": _json(leg.odds),
                    "prediction_snapshot_id": leg.prediction_snapshot_id,
                    "model_version": leg.model_version,
                },
            )
        )
        return _int(row["parlay_leg_id"])

    def _insert_atomic_bet(
        self,
        parlay_recommendation_id: int,
        atomic_bet: AtomicBet,
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                INSERT_PARLAY_ATOMIC_BET_QUERY,
                {
                    "parlay_recommendation_id": parlay_recommendation_id,
                    "outcomes_json": _json(
                        [leg.model_dump(mode="json") for leg in atomic_bet.legs]
                    ),
                    "stake": atomic_bet.stake,
                    "probability": atomic_bet.probability,
                    "odds_product": atomic_bet.odds_product,
                    "expected_payout": atomic_bet.expected_payout,
                    "expected_value": atomic_bet.expected_value,
                },
            )
        )
        return _int(row["atomic_bet_id"])


class _ParlayLegWriteInput(BaseModel):
    leg_index: int = Field(ge=0)
    fixture_id: str
    market_type: str
    line: float | None = None
    side: str | None = None
    selected_outcomes: list[str] = Field(min_length=1)
    probabilities: dict[str, float]
    odds: dict[str, float]
    prediction_snapshot_id: int | None = Field(default=None, gt=0)
    model_version: str | None = None


def parlay_recommendation_input_from_payload(
    *,
    recommendation_key: str | None,
    model_version: str | None,
    strategy: str,
    pass_type: str,
    is_multiple: bool,
    unit_stake: float,
    total_stake: float,
    hit_probability: float,
    expected_payout: float,
    expected_value: float,
    roi: float,
    risk_score: float,
    risk_level: str,
    correlation_penalty: float,
    rule_valid: bool,
    explanation_json: Mapping[str, object],
    atomic_bets: Sequence[AtomicBet],
    source: str = "api_parlay_recommend",
) -> ParlayRecommendationWriteInput:
    return ParlayRecommendationWriteInput(
        recommendation_key=recommendation_key,
        model_version=model_version,
        strategy=strategy,
        pass_type=pass_type,
        is_multiple=is_multiple,
        unit_stake=unit_stake,
        multiplier=1,
        total_atomic_bets=len(atomic_bets),
        total_stake=total_stake,
        hit_probability=hit_probability,
        expected_payout=expected_payout,
        expected_value=expected_value,
        roi=roi,
        risk_score=risk_score,
        risk_level=risk_level,
        correlation_penalty=correlation_penalty,
        rule_valid=rule_valid,
        explanation_json=dict(explanation_json),
        atomic_bets=list(atomic_bets),
        source=source,
    )


def _recommendation_params(
    recommendation: ParlayRecommendationWriteInput,
) -> QueryParams:
    prediction_snapshot_ids = _prediction_snapshot_ids(recommendation.atomic_bets)
    explanation_json = {
        **recommendation.explanation_json,
        "recommendation_key": recommendation.recommendation_key,
    }
    return {
        "model_version": recommendation.model_version,
        "strategy": recommendation.strategy,
        "pass_type": recommendation.pass_type,
        "is_multiple": recommendation.is_multiple,
        "unit_stake": recommendation.unit_stake,
        "multiplier": recommendation.multiplier,
        "total_atomic_bets": recommendation.total_atomic_bets,
        "total_stake": recommendation.total_stake,
        "hit_probability": recommendation.hit_probability,
        "expected_payout": recommendation.expected_payout,
        "expected_value": recommendation.expected_value,
        "roi": recommendation.roi,
        "risk_score": recommendation.risk_score,
        "risk_level": recommendation.risk_level,
        "correlation_penalty": recommendation.correlation_penalty,
        "recommendation_score": recommendation.recommendation_score,
        "rule_valid": recommendation.rule_valid,
        "explanation_json": _json(explanation_json),
        "prediction_snapshot_ids_json": _json(prediction_snapshot_ids),
        "source": recommendation.source,
    }


def _leg_inputs_from_atomic_bets(
    atomic_bets: Sequence[AtomicBet],
) -> list[_ParlayLegWriteInput]:
    if not atomic_bets:
        return []
    leg_count = len(atomic_bets[0].legs)
    leg_inputs: list[_ParlayLegWriteInput] = []
    for leg_index in range(leg_count):
        legs_at_index = [
            atomic_bet.legs[leg_index]
            for atomic_bet in atomic_bets
            if len(atomic_bet.legs) > leg_index
        ]
        first = legs_at_index[0]
        probabilities = {leg.outcome: leg.probability for leg in legs_at_index}
        odds = {leg.outcome: leg.odds for leg in legs_at_index}
        selected_outcomes = sorted(probabilities)
        leg_inputs.append(
            _ParlayLegWriteInput(
                leg_index=leg_index,
                fixture_id=first.fixture_id,
                market_type=first.market_type,
                line=first.line,
                side=first.side,
                selected_outcomes=selected_outcomes,
                probabilities=probabilities,
                odds=odds,
                prediction_snapshot_id=first.prediction_snapshot_id,
                model_version=first.model_version,
            )
        )
    return leg_inputs


def _prediction_snapshot_ids(atomic_bets: Sequence[AtomicBet]) -> list[int]:
    ids = sorted(
        {
            leg.prediction_snapshot_id
            for atomic_bet in atomic_bets
            for leg in atomic_bet.legs
            if leg.prediction_snapshot_id is not None
        }
    )
    return ids


def _model_family(model_version: str) -> str:
    if model_version.startswith("poisson"):
        return "poisson"
    if model_version.startswith("dc") or "dixon" in model_version:
        return "dixon_coles"
    return model_version.split("-", maxsplit=1)[0] or "unknown"


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_array(value: object) -> list[Mapping[str, object]]:
    parsed = loads(value) if isinstance(value, str) else value
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, Mapping)]
    raise ValueError("expected JSON array")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
