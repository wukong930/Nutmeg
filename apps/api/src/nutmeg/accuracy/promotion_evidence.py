from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from json import loads
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.settlement import AsianHandicapSettlement, HandicapOneXTwoOutcome
from nutmeg.market_resolver.settlement import (
    settle_1x2,
    settle_asian_handicap,
    settle_cn_handicap_1x2,
    settle_european_handicap_1x2,
)
from nutmeg.parlay import settle_parlay_atomic_bet

UPSET_PRECISION_EVIDENCE_QUERY = """
SELECT
  ua.upset_alert_id,
  ua.fixture_id,
  ua.upset_type,
  ua.target_market_type,
  ua.target_line,
  ua.target_outcome,
  ua.upset_score,
  r.home_goals,
  r.away_goals
FROM upset_alerts ua
JOIN prediction_snapshots ps
  ON ps.prediction_snapshot_id = ua.prediction_snapshot_id
JOIN fixtures f
  ON f.fixture_id = ua.fixture_id
JOIN results r
  ON r.fixture_id = ua.fixture_id
WHERE ps.model_version = %(model_version)s
  AND (%(competition_id)s::text IS NULL OR f.competition_id = %(competition_id)s::text)
ORDER BY ua.upset_score DESC NULLS LAST, ua.upset_alert_id ASC
LIMIT %(top_k)s
"""

HANDICAP_PERFORMANCE_EVIDENCE_QUERY = """
SELECT
  mp.fixture_id,
  mp.market_type,
  mp.line,
  mp.side,
  mp.outcome,
  mp.probability,
  r.home_goals,
  r.away_goals
FROM market_predictions mp
JOIN prediction_snapshots ps
  ON ps.prediction_snapshot_id = mp.prediction_snapshot_id
JOIN fixtures f
  ON f.fixture_id = mp.fixture_id
JOIN results r
  ON r.fixture_id = mp.fixture_id
WHERE ps.model_version = %(model_version)s
  AND mp.market_type = ANY(%(market_types)s)
  AND (%(competition_id)s::text IS NULL OR f.competition_id = %(competition_id)s::text)
ORDER BY mp.fixture_id, mp.market_type, mp.line, mp.side, mp.outcome
"""

PARLAY_SIMULATION_EVIDENCE_QUERY = """
SELECT
  pr.parlay_recommendation_id,
  pr.model_version,
  pr.strategy,
  pr.pass_type,
  pr.rule_valid,
  pab.atomic_bet_id,
  pab.outcomes_json,
  pab.stake,
  pab.odds_product,
  pab.expected_payout,
  pab.expected_value,
  pab.result_status,
  pab.gross_payout,
  pab.profit_loss,
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
FROM parlay_recommendations pr
JOIN parlay_atomic_bets pab
  ON pab.parlay_recommendation_id = pr.parlay_recommendation_id
LEFT JOIN LATERAL jsonb_array_elements(pab.outcomes_json) AS leg(value)
  ON TRUE
LEFT JOIN results r
  ON r.fixture_id = leg.value->>'fixture_id'
WHERE pr.model_version = %(model_version)s
  AND pr.rule_valid IS TRUE
  AND (
    %(competition_id)s::text IS NULL
    OR EXISTS (
      SELECT 1
      FROM jsonb_array_elements(pab.outcomes_json) AS filter_leg(value)
      JOIN fixtures f
        ON f.fixture_id = filter_leg.value->>'fixture_id'
      WHERE f.competition_id = %(competition_id)s::text
    )
  )
GROUP BY
  pr.parlay_recommendation_id,
  pr.model_version,
  pr.strategy,
  pr.pass_type,
  pr.rule_valid,
  pab.atomic_bet_id,
  pab.outcomes_json,
  pab.stake,
  pab.odds_product,
  pab.expected_payout,
  pab.expected_value,
  pab.result_status,
  pab.gross_payout,
  pab.profit_loss
ORDER BY pr.parlay_recommendation_id ASC, pab.atomic_bet_id ASC
"""


class PromotionEvidenceDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read settled evidence rows for promotion gates."""


class UpsetPrecisionEvidenceReport(BaseModel):
    model_version: str
    competition_id: str | None = None
    top_k: int = Field(ge=1)
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    unresolved_count: int = Field(default=0, ge=0)

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "upset_precision_at_k": self.precision_at_k,
            "upset_precision_top_k": self.top_k,
            "upset_precision_sample_size": self.sample_size,
            "upset_precision_hit_count": self.hit_count,
            "upset_precision_unresolved_count": self.unresolved_count,
            "upset_precision_source": "settled_upset_alerts",
        }


class HandicapPerformanceEvidenceReport(BaseModel):
    model_version: str
    competition_id: str | None = None
    market_types: list[str]
    sample_size: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    unresolved_count: int = Field(default=0, ge=0)

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "handicap_accuracy": self.accuracy,
            "handicap_brier_score": self.brier_score,
            "handicap_sample_size": self.sample_size,
            "handicap_correct_count": self.correct_count,
            "handicap_unresolved_count": self.unresolved_count,
            "handicap_market_types": self.market_types,
            "handicap_performance_source": "settled_market_predictions",
        }


class ParlaySimulationEvidenceReport(BaseModel):
    model_version: str
    competition_id: str | None = None
    status: str
    sample_size: int = Field(ge=0)
    won_atomic_bets: int = Field(default=0, ge=0)
    total_stake: float = Field(default=0.0, ge=0.0)
    gross_payout: float = Field(default=0.0, ge=0.0)
    profit_loss: float = 0.0
    roi: float | None = None
    unresolved_count: int = Field(default=0, ge=0)
    reason: str

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "parlay_simulation_status": self.status,
            "parlay_simulation_sample_size": self.sample_size,
            "parlay_simulation_won_atomic_bets": self.won_atomic_bets,
            "parlay_simulation_total_stake": self.total_stake,
            "parlay_simulation_gross_payout": self.gross_payout,
            "parlay_simulation_profit_loss": self.profit_loss,
            "parlay_simulation_roi": self.roi,
            "parlay_simulation_unresolved_count": self.unresolved_count,
            "parlay_simulation_reason": self.reason,
        }


class ModelPromotionEvidenceBundle(BaseModel):
    model_version: str
    candidate_upset_precision: UpsetPrecisionEvidenceReport | None = None
    baseline_upset_precision: UpsetPrecisionEvidenceReport | None = None
    candidate_handicap_performance: HandicapPerformanceEvidenceReport | None = None
    baseline_handicap_performance: HandicapPerformanceEvidenceReport | None = None
    candidate_parlay_simulation: ParlaySimulationEvidenceReport | None = None
    baseline_parlay_simulation: ParlaySimulationEvidenceReport | None = None

    @property
    def metrics_json(self) -> dict[str, object]:
        metrics: dict[str, object] = {}
        if self.candidate_upset_precision is not None:
            metrics["candidate_upset_precision"] = (
                self.candidate_upset_precision.metrics_json
            )
        if self.baseline_upset_precision is not None:
            metrics["baseline_upset_precision"] = (
                self.baseline_upset_precision.metrics_json
            )
        if self.candidate_handicap_performance is not None:
            metrics["candidate_handicap_performance"] = (
                self.candidate_handicap_performance.metrics_json
            )
        if self.baseline_handicap_performance is not None:
            metrics["baseline_handicap_performance"] = (
                self.baseline_handicap_performance.metrics_json
            )
        if self.candidate_parlay_simulation is not None:
            metrics["candidate_parlay_simulation"] = (
                self.candidate_parlay_simulation.metrics_json
            )
        if self.baseline_parlay_simulation is not None:
            metrics["baseline_parlay_simulation"] = (
                self.baseline_parlay_simulation.metrics_json
            )
        return metrics


class PostgresPromotionEvidenceRepository:
    def __init__(self, database: PromotionEvidenceDatabaseExecutor) -> None:
        self.database = database

    def get_upset_precision_at_k(
        self,
        *,
        model_version: str,
        top_k: int = 20,
        competition_id: str | None = None,
    ) -> UpsetPrecisionEvidenceReport | None:
        rows = self.database.fetch_all(
            UPSET_PRECISION_EVIDENCE_QUERY,
            {
                "model_version": model_version,
                "competition_id": competition_id,
                "top_k": max(1, top_k),
            },
        )
        return build_upset_precision_evidence_report(
            rows,
            model_version=model_version,
            competition_id=competition_id,
            top_k=top_k,
        )

    def get_handicap_performance(
        self,
        *,
        model_version: str,
        market_types: Sequence[str] = (
            "cn_handicap_1x2",
            "european_handicap_1x2",
            "asian_handicap",
        ),
        competition_id: str | None = None,
    ) -> HandicapPerformanceEvidenceReport | None:
        rows = self.database.fetch_all(
            HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
            {
                "model_version": model_version,
                "competition_id": competition_id,
                "market_types": list(market_types),
            },
        )
        return build_handicap_performance_evidence_report(
            rows,
            model_version=model_version,
            competition_id=competition_id,
            market_types=market_types,
        )

    def get_parlay_simulation(
        self,
        *,
        model_version: str,
        competition_id: str | None = None,
    ) -> ParlaySimulationEvidenceReport:
        rows = self.database.fetch_all(
            PARLAY_SIMULATION_EVIDENCE_QUERY,
            {
                "model_version": model_version,
                "competition_id": competition_id,
            },
        )
        return build_parlay_simulation_evidence_report(
            rows,
            model_version=model_version,
            competition_id=competition_id,
        )


def build_upset_precision_evidence_report(
    rows: Sequence[Mapping[str, object]],
    *,
    model_version: str,
    top_k: int,
    competition_id: str | None = None,
) -> UpsetPrecisionEvidenceReport | None:
    hit_count = 0
    sample_size = 0
    unresolved_count = 0
    for row in rows:
        hit = _upset_row_hit(row)
        if hit is None:
            unresolved_count += 1
            continue
        sample_size += 1
        hit_count += 1 if hit else 0
    if sample_size == 0 and unresolved_count == 0:
        return None
    return UpsetPrecisionEvidenceReport(
        model_version=model_version,
        competition_id=competition_id,
        top_k=max(1, top_k),
        sample_size=sample_size,
        hit_count=hit_count,
        precision_at_k=hit_count / sample_size if sample_size > 0 else None,
        unresolved_count=unresolved_count,
    )


def build_handicap_performance_evidence_report(
    rows: Sequence[Mapping[str, object]],
    *,
    model_version: str,
    market_types: Sequence[str],
    competition_id: str | None = None,
) -> HandicapPerformanceEvidenceReport | None:
    grouped_rows = _group_handicap_rows(rows)
    correct_count = 0
    sample_size = 0
    unresolved_count = 0
    brier_scores: list[float] = []
    for group in grouped_rows.values():
        actual_outcome = _handicap_actual_outcome(group[0])
        if actual_outcome is None:
            unresolved_count += 1
            continue
        probabilities = {
            _str(row["outcome"]): _float(row["probability"])
            for row in group
            if _float(row["probability"]) >= 0
        }
        if not probabilities:
            unresolved_count += 1
            continue
        predicted_outcome = max(probabilities, key=lambda outcome: probabilities[outcome])
        sample_size += 1
        correct_count += 1 if predicted_outcome == actual_outcome else 0
        brier_scores.append(_brier_score(probabilities, actual_outcome))
    if sample_size == 0 and unresolved_count == 0:
        return None
    return HandicapPerformanceEvidenceReport(
        model_version=model_version,
        competition_id=competition_id,
        market_types=list(market_types),
        sample_size=sample_size,
        correct_count=correct_count,
        accuracy=correct_count / sample_size if sample_size > 0 else None,
        brier_score=sum(brier_scores) / len(brier_scores) if brier_scores else None,
        unresolved_count=unresolved_count,
    )


def build_parlay_simulation_evidence_report(
    rows: Sequence[Mapping[str, object]],
    *,
    model_version: str,
    competition_id: str | None = None,
) -> ParlaySimulationEvidenceReport:
    sample_size = 0
    won_atomic_bets = 0
    total_stake = 0.0
    gross_payout = 0.0
    unresolved_count = 0
    for row in rows:
        stake = _float(row["stake"])
        settled_win = _parlay_atomic_bet_win(row)
        if settled_win is None:
            unresolved_count += 1
            continue
        sample_size += 1
        total_stake += stake
        if settled_win:
            won_atomic_bets += 1
            gross_payout += _optional_float(row.get("gross_payout")) or (
                stake * _float(row["odds_product"])
            )
        else:
            gross_payout += _optional_float(row.get("gross_payout")) or 0.0
    profit_loss = gross_payout - total_stake
    if sample_size == 0:
        return ParlaySimulationEvidenceReport(
            model_version=model_version,
            competition_id=competition_id,
            status="unavailable",
            sample_size=0,
            won_atomic_bets=0,
            total_stake=0.0,
            gross_payout=0.0,
            profit_loss=0.0,
            roi=None,
            unresolved_count=unresolved_count,
            reason="no settled model-version parlay atomic bets",
        )
    return ParlaySimulationEvidenceReport(
        model_version=model_version,
        competition_id=competition_id,
        status="available",
        sample_size=sample_size,
        won_atomic_bets=won_atomic_bets,
        total_stake=total_stake,
        gross_payout=gross_payout,
        profit_loss=profit_loss,
        roi=profit_loss / total_stake if total_stake > 0 else None,
        unresolved_count=unresolved_count,
        reason="settled_model_version_parlay_atomic_bets",
    )


def _upset_row_hit(row: Mapping[str, object]) -> bool | None:
    target_market_type = _optional_str(row.get("target_market_type"))
    target_outcome = _optional_str(row.get("target_outcome"))
    if not target_outcome:
        target_outcome = _default_outcome_for_upset_type(_optional_str(row.get("upset_type")))
    if target_outcome is None:
        return None
    home_goals = _int(row["home_goals"])
    away_goals = _int(row["away_goals"])
    if target_outcome in {"home_win", "draw", "away_win"}:
        return settle_1x2(home_goals, away_goals).value == target_outcome
    if target_outcome in {item.value for item in HandicapOneXTwoOutcome}:
        line = _optional_float(row.get("target_line"))
        if line is None:
            return None
        handicap = int(round(line))
        if target_market_type == "european_handicap_1x2":
            return (
                settle_european_handicap_1x2(
                    home_goals,
                    away_goals,
                    handicap=handicap,
                ).value
                == target_outcome
            )
        return (
            settle_cn_handicap_1x2(home_goals, away_goals, handicap=handicap).value
            == target_outcome
        )
    if target_outcome in {item.value for item in AsianHandicapSettlement}:
        line = _optional_float(row.get("target_line"))
        if line is None:
            return None
        return (
            settle_asian_handicap(home_goals, away_goals, line=line, side="home").value
            == target_outcome
        )
    return None


def _default_outcome_for_upset_type(upset_type: str | None) -> str | None:
    if upset_type == "draw_overlooked":
        return "draw"
    return None


def _group_handicap_rows(
    rows: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str, float | None, str | None], list[Mapping[str, object]]]:
    groups: dict[tuple[str, str, float | None, str | None], list[Mapping[str, object]]] = {}
    for row in rows:
        key = (
            _str(row["fixture_id"]),
            _str(row["market_type"]),
            _optional_float(row.get("line")),
            _optional_str(row.get("side")),
        )
        groups.setdefault(key, []).append(row)
    return groups


def _handicap_actual_outcome(row: Mapping[str, object]) -> str | None:
    market_type = _str(row["market_type"])
    home_goals = _int(row["home_goals"])
    away_goals = _int(row["away_goals"])
    line = _optional_float(row.get("line"))
    if market_type in {"cn_handicap_1x2", "european_handicap_1x2"}:
        if line is None:
            return None
        handicap = int(round(line))
        if market_type == "european_handicap_1x2":
            return settle_european_handicap_1x2(
                home_goals,
                away_goals,
                handicap=handicap,
            ).value
        return settle_cn_handicap_1x2(home_goals, away_goals, handicap=handicap).value
    if market_type == "asian_handicap":
        if line is None:
            return None
        return settle_asian_handicap(
            home_goals,
            away_goals,
            line=line,
            side=_optional_str(row.get("side")) or "home",
        ).value
    return None


def _brier_score(probabilities: Mapping[str, float], actual_outcome: str) -> float:
    outcomes = set(probabilities) | {actual_outcome}
    return sum(
        (probabilities.get(outcome, 0.0) - (1.0 if outcome == actual_outcome else 0.0))
        ** 2
        for outcome in outcomes
    )


def _parlay_atomic_bet_win(row: Mapping[str, object]) -> bool | None:
    status = _optional_str(row.get("result_status"))
    if status is not None:
        normalized_status = status.lower()
        if normalized_status in {"won", "win", "hit"}:
            return True
        if normalized_status in {"lost", "loss", "missed", "miss"}:
            return False
        if normalized_status in {"void", "push"}:
            return False

    outcomes = _json_array(row.get("outcomes_json"))
    if not outcomes:
        return None
    result_rows = _json_array(row.get("result_rows_json"))
    settlement = settle_parlay_atomic_bet(
        [outcome for outcome in outcomes if isinstance(outcome, Mapping)],
        [result_row for result_row in result_rows if isinstance(result_row, Mapping)],
        stake=_float(row["stake"]),
        odds_product=_float(row["odds_product"]),
    )
    if not settlement.is_settled:
        return None
    return settlement.result_status == "won"


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = loads(value)
        if isinstance(parsed, list):
            return parsed
        raise ValueError("expected JSON array")
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise ValueError(f"expected JSON array value, got {type(value).__name__}")


def _str(value: object) -> str:
    if value is None:
        raise ValueError("expected non-null string value")
    return str(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


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
