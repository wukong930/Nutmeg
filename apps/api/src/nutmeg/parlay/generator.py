from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.parlay import ParlayEvaluation, ParlayLegSelection
from nutmeg.parlay.expander import evaluate_parlay
from nutmeg.parlay.repository import (
    ParlayRecommendationWriteInput,
    PostgresParlayRecommendationRepository,
    StoredParlayRecommendation,
    parlay_recommendation_input_from_payload,
)

LIST_PARLAY_CANDIDATES_FROM_MARKET_PREDICTIONS_QUERY = """
WITH latest_predictions AS (
  SELECT DISTINCT ON (ps.fixture_id)
    ps.prediction_snapshot_id,
    ps.fixture_id,
    ps.prediction_time_utc,
    ps.model_version,
    ps.data_quality_score,
    f.competition_id,
    f.kickoff_time_utc
  FROM prediction_snapshots ps
  JOIN fixtures f
    ON f.fixture_id = ps.fixture_id
  WHERE ps.prediction_time_utc <= %(as_of_time_utc)s
    AND f.kickoff_time_utc >= %(as_of_time_utc)s
    AND f.status = ANY(%(fixture_statuses)s)
    AND (%(competition_id)s::text IS NULL OR f.competition_id = %(competition_id)s::text)
    AND (%(fixture_ids)s::text[] IS NULL OR ps.fixture_id = ANY(%(fixture_ids)s::text[]))
    AND (%(model_version)s::text IS NULL OR ps.model_version = %(model_version)s::text)
    AND ps.data_quality_score >= %(min_data_quality_score)s
  ORDER BY ps.fixture_id, ps.prediction_time_utc DESC, ps.prediction_snapshot_id DESC
)
SELECT
  lp.prediction_snapshot_id,
  lp.fixture_id,
  lp.prediction_time_utc,
  lp.model_version,
  lp.data_quality_score,
  lp.competition_id,
  lp.kickoff_time_utc,
  mp.market_prediction_id,
  mp.market_type,
  mp.line,
  mp.side,
  mp.outcome,
  mp.probability,
  odds.decimal_odds,
  odds.fair_probability AS market_probability,
  odds.snapshot_time_utc AS odds_snapshot_time_utc,
  (
    mp.probability - COALESCE(odds.fair_probability, 1 / odds.decimal_odds)
  ) AS model_edge
FROM latest_predictions lp
JOIN market_predictions mp
  ON mp.prediction_snapshot_id = lp.prediction_snapshot_id
JOIN LATERAL (
  SELECT
    os.decimal_odds,
    os.fair_probability,
    os.snapshot_time_utc
  FROM odds_snapshots os
  WHERE os.fixture_id = mp.fixture_id
    AND os.market_type = mp.market_type
    AND os.outcome = mp.outcome
    AND os.line IS NOT DISTINCT FROM mp.line
    AND os.side IS NOT DISTINCT FROM mp.side
    AND os.decimal_odds > 1
    AND os.snapshot_time_utc <= %(as_of_time_utc)s
  ORDER BY os.snapshot_time_utc DESC, os.odds_snapshot_id DESC
  LIMIT 1
) odds ON TRUE
WHERE mp.market_type = ANY(%(allowed_markets)s)
  AND mp.probability >= %(min_probability)s
  AND (
    mp.probability - COALESCE(odds.fair_probability, 1 / odds.decimal_odds)
  ) >= %(min_model_edge)s
ORDER BY
  lp.model_version ASC,
  model_edge DESC,
  mp.probability DESC,
  lp.fixture_id ASC,
  mp.market_prediction_id ASC
LIMIT %(candidate_limit)s
"""


class MarketPredictionParlayCandidate(BaseModel):
    prediction_snapshot_id: int = Field(gt=0)
    fixture_id: str
    prediction_time_utc: datetime
    model_version: str
    data_quality_score: float = Field(ge=0.0, le=100.0)
    competition_id: str
    kickoff_time_utc: datetime
    market_prediction_id: int = Field(gt=0)
    market_type: str
    line: float | None = None
    side: str | None = None
    outcome: str
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float = Field(gt=1.0)
    market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    odds_snapshot_time_utc: datetime
    model_edge: float

    def to_leg_selection(self) -> ParlayLegSelection:
        return ParlayLegSelection(
            fixture_id=self.fixture_id,
            market_type=self.market_type,
            outcomes=[self.outcome],
            probabilities={self.outcome: self.probability},
            odds={self.outcome: self.decimal_odds},
            line=self.line,
            side=self.side,
            model_version=self.model_version,
            prediction_snapshot_id=self.prediction_snapshot_id,
            data_quality_score=self.data_quality_score,
    )


class MarketPredictionParlayDatabase(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read stored market prediction candidates."""


class MarketPredictionParlayGenerationOptions(BaseModel):
    as_of_time_utc: datetime
    pass_type: str = "2x1"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    competition_id: str | None = Field(default=None, min_length=1)
    fixture_ids: tuple[str, ...] = Field(default_factory=tuple)
    model_version: str | None = Field(default=None, min_length=1)
    allowed_markets: tuple[str, ...] = ("1x2", "cn_handicap_1x2")
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float = Field(default=0.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=100, ge=1, le=1_000)
    fixture_statuses: tuple[str, ...] = ("scheduled", "beta")
    dry_run: bool = True

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class GeneratedParlayRecommendation(BaseModel):
    recommendation: ParlayRecommendationWriteInput
    evaluation: ParlayEvaluation
    candidates: list[MarketPredictionParlayCandidate]
    stored: StoredParlayRecommendation | None = None


class MarketPredictionParlayGenerationResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    candidate_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    stored_recommendation_ids: list[int] = Field(default_factory=list)
    recommendations: list[GeneratedParlayRecommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def list_market_prediction_parlay_candidates(
    database: MarketPredictionParlayDatabase,
    *,
    options: MarketPredictionParlayGenerationOptions,
) -> list[MarketPredictionParlayCandidate]:
    rows = database.fetch_all(
        LIST_PARLAY_CANDIDATES_FROM_MARKET_PREDICTIONS_QUERY,
        {
            "as_of_time_utc": options.normalized_as_of_time_utc,
            "fixture_statuses": list(options.fixture_statuses),
            "competition_id": options.competition_id,
            "fixture_ids": list(options.fixture_ids) or None,
            "model_version": options.model_version,
            "allowed_markets": list(options.allowed_markets),
            "min_probability": options.min_probability,
            "min_model_edge": options.min_model_edge,
            "min_data_quality_score": options.min_data_quality_score,
            "candidate_limit": options.candidate_limit,
        },
    )
    return [_candidate_from_row(row) for row in rows]


def run_market_prediction_parlay_generation(
    database: MarketPredictionParlayDatabase,
    *,
    options: MarketPredictionParlayGenerationOptions,
    repository: PostgresParlayRecommendationRepository | None = None,
) -> MarketPredictionParlayGenerationResult:
    candidates = list_market_prediction_parlay_candidates(database, options=options)
    warnings: list[str] = []
    recommendation_candidates = _select_single_recommendation_candidates(
        candidates,
        leg_count=_parse_pass_legs(options.pass_type),
    )
    if not recommendation_candidates:
        warnings.append("insufficient_distinct_fixture_candidates")
        return MarketPredictionParlayGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.normalized_as_of_time_utc,
            candidate_count=len(candidates),
            generated_count=0,
            warnings=warnings,
        )

    legs = [candidate.to_leg_selection() for candidate in recommendation_candidates]
    evaluation = evaluate_parlay(
        legs,
        pass_type=options.pass_type,
        unit_stake=options.unit_stake,
        max_budget=options.max_budget,
    )
    if not evaluation.rule_valid:
        rule_reasons = evaluation.explanation_json.get("rule_reasons", [])
        if isinstance(rule_reasons, list):
            warnings.extend(f"rule_invalid:{reason}" for reason in rule_reasons)
    recommendation = parlay_recommendation_input_from_payload(
        recommendation_key=_recommendation_key(recommendation_candidates, options=options),
        model_version=recommendation_candidates[0].model_version,
        strategy="market_prediction_value",
        pass_type=evaluation.pass_type,
        is_multiple=evaluation.is_multiple,
        unit_stake=evaluation.unit_stake,
        total_stake=evaluation.total_stake,
        hit_probability=evaluation.hit_probability,
        expected_payout=evaluation.expected_payout,
        expected_value=evaluation.expected_value,
        roi=evaluation.roi,
        risk_score=evaluation.risk_score,
        risk_level=evaluation.risk_level,
        correlation_penalty=evaluation.correlation_penalty,
        rule_valid=evaluation.rule_valid,
        explanation_json={
            **evaluation.explanation_json,
            "candidate_source": "stored_market_predictions",
            "selected_market_prediction_ids": [
                candidate.market_prediction_id for candidate in recommendation_candidates
            ],
            "selected_model_edges": {
                candidate.fixture_id: candidate.model_edge
                for candidate in recommendation_candidates
            },
        },
        atomic_bets=evaluation.atomic_bets,
        source="market_prediction_generator_v1",
    )
    stored = None
    if not options.dry_run:
        if repository is None:
            raise ValueError("repository is required for non-dry-run parlay generation")
        stored = repository.save_recommendation(recommendation)

    generated = GeneratedParlayRecommendation(
        recommendation=recommendation,
        evaluation=evaluation,
        candidates=recommendation_candidates,
        stored=stored,
    )
    return MarketPredictionParlayGenerationResult(
        dry_run=options.dry_run,
        as_of_time_utc=options.normalized_as_of_time_utc,
        candidate_count=len(candidates),
        generated_count=1,
        stored_recommendation_ids=(
            [stored.parlay_recommendation_id] if stored is not None else []
        ),
        recommendations=[generated],
        warnings=warnings,
    )


def _select_single_recommendation_candidates(
    candidates: Sequence[MarketPredictionParlayCandidate],
    *,
    leg_count: int,
) -> list[MarketPredictionParlayCandidate]:
    by_model_version: dict[str, list[MarketPredictionParlayCandidate]] = {}
    for candidate in candidates:
        by_model_version.setdefault(candidate.model_version, []).append(candidate)
    for model_candidates in by_model_version.values():
        selected: list[MarketPredictionParlayCandidate] = []
        seen_fixtures: set[str] = set()
        for candidate in model_candidates:
            if candidate.fixture_id in seen_fixtures:
                continue
            selected.append(candidate)
            seen_fixtures.add(candidate.fixture_id)
            if len(selected) == leg_count:
                return selected
    return []


def _candidate_from_row(row: DatabaseRow) -> MarketPredictionParlayCandidate:
    return MarketPredictionParlayCandidate(
        prediction_snapshot_id=_int(row["prediction_snapshot_id"]),
        fixture_id=str(row["fixture_id"]),
        prediction_time_utc=_datetime(row["prediction_time_utc"]),
        model_version=str(row["model_version"]),
        data_quality_score=_float(row["data_quality_score"]),
        competition_id=str(row["competition_id"]),
        kickoff_time_utc=_datetime(row["kickoff_time_utc"]),
        market_prediction_id=_int(row["market_prediction_id"]),
        market_type=str(row["market_type"]),
        line=_optional_float(row.get("line")),
        side=_optional_str(row.get("side")),
        outcome=str(row["outcome"]),
        probability=_float(row["probability"]),
        decimal_odds=_float(row["decimal_odds"]),
        market_probability=_optional_float(row.get("market_probability")),
        odds_snapshot_time_utc=_datetime(row["odds_snapshot_time_utc"]),
        model_edge=_float(row["model_edge"]),
    )


def _parse_pass_legs(pass_type: str) -> int:
    try:
        leg_count_text, multiplier_text = pass_type.lower().split("x", maxsplit=1)
        leg_count = int(leg_count_text)
        multiplier = int(multiplier_text)
    except ValueError as exc:
        raise ValueError(f"unsupported pass_type: {pass_type}") from exc
    if leg_count < 2 or multiplier != 1:
        raise ValueError("only Nx1 pass types with at least two legs are supported")
    return leg_count


def _recommendation_key(
    candidates: Sequence[MarketPredictionParlayCandidate],
    *,
    options: MarketPredictionParlayGenerationOptions,
) -> str:
    fixture_part = "_".join(candidate.fixture_id for candidate in candidates)
    return f"market_prediction_{options.pass_type}_{fixture_part}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
