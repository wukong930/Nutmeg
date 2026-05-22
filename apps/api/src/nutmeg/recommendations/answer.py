from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.parlay.risk import clamp_probability, risk_level_from_score
from nutmeg.recommendations.engine import RecommendationGenerationResult
from nutmeg.recommendations.models import RecommendationMode, ScoredRecommendationCandidate

type RecommendationAnswerStatus = Literal["ready", "unavailable"]


class RecommendationAnswerLeg(BaseModel):
    fixture_id: str
    market_type: str
    outcomes: list[str] = Field(min_length=1)
    probability: float = Field(ge=0.0, le=1.0)
    decimal_odds: float | None = Field(default=None, gt=1.0)
    line: float | None = None
    side: str | None = None
    data_quality_score: float = Field(ge=0.0, le=100.0)
    model_version: str | None = None
    prediction_snapshot_id: int | None = Field(default=None, gt=0)
    prediction_time_utc: datetime | None = None
    kickoff_time_utc: datetime | None = None
    recommendation_score: float = Field(ge=0.0, le=1.0)


class RecommendationBudgetSummary(BaseModel):
    unit_stake: float = Field(gt=0.0)
    total_stake: float = Field(ge=0.0)
    max_budget: float | None = Field(default=None, gt=0.0)
    within_budget: bool


class RecommendationAnswer(BaseModel):
    status: RecommendationAnswerStatus
    generated_at_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    is_multiple: bool = False
    fixture_count: int = Field(default=0, ge=0)
    legs: list[RecommendationAnswerLeg] = Field(default_factory=list)
    budget: RecommendationBudgetSummary | None = None
    atomic_bet_count: int = Field(default=0, ge=0)
    hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_payout: float | None = None
    expected_value: float | None = None
    roi: float | None = None
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: str | None = None
    rule_valid: bool = False
    average_data_quality_score: float | None = Field(default=None, ge=0.0, le=100.0)
    data_quality_grade: Literal["A", "B", "C", "D"] | None = None
    warnings: list[str] = Field(default_factory=list)


class RecommendationAnswerSet(BaseModel):
    primary_answer: RecommendationAnswer
    backup_answers: list[RecommendationAnswer] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_recommendation_answer(
    result: RecommendationGenerationResult,
    *,
    max_budget: float | None = None,
) -> RecommendationAnswer:
    selection = result.selection
    if selection is None:
        return RecommendationAnswer(
            status="unavailable",
            generated_at_utc=result.as_of_time_utc,
            warnings=result.warnings,
        )

    evaluation = selection.evaluation
    resolved_max_budget = _budget_limit(evaluation.explanation_json, max_budget=max_budget)
    legs = [
        RecommendationAnswerLeg(
            fixture_id=item.candidate.fixture_id,
            market_type=item.candidate.market_type,
            outcomes=[item.candidate.outcome],
            probability=item.candidate.probability,
            decimal_odds=item.candidate.decimal_odds,
            line=item.candidate.line,
            side=item.candidate.side,
            data_quality_score=item.candidate.data_quality_score,
            model_version=item.candidate.model_version,
            prediction_snapshot_id=item.candidate.prediction_snapshot_id,
            prediction_time_utc=item.candidate.prediction_time_utc,
            kickoff_time_utc=item.candidate.kickoff_time_utc,
            recommendation_score=item.score,
        )
        for item in selection.selected_candidates
    ]
    average_data_quality = _average(
        item.candidate.data_quality_score for item in selection.selected_candidates
    )
    return RecommendationAnswer(
        status="ready",
        generated_at_utc=result.as_of_time_utc,
        pass_type=selection.pass_type,
        mode=selection.mode,
        is_multiple=evaluation.is_multiple,
        fixture_count=len(selection.fixture_ids),
        legs=legs,
        budget=RecommendationBudgetSummary(
            unit_stake=evaluation.unit_stake,
            total_stake=evaluation.total_stake,
            max_budget=resolved_max_budget,
            within_budget=resolved_max_budget is None
            or evaluation.total_stake <= resolved_max_budget,
        ),
        atomic_bet_count=evaluation.total_atomic_bets,
        hit_probability=evaluation.hit_probability,
        expected_payout=evaluation.expected_payout,
        expected_value=evaluation.expected_value,
        roi=evaluation.roi,
        risk_score=evaluation.risk_score,
        risk_level=evaluation.risk_level,
        rule_valid=evaluation.rule_valid,
        average_data_quality_score=average_data_quality,
        data_quality_grade=(
            _data_quality_grade(average_data_quality) if average_data_quality is not None else None
        ),
        warnings=result.warnings,
    )


def build_public_recommendation_answer_set(
    primary_answer: RecommendationAnswer,
    candidate_backup_answers: Sequence[RecommendationAnswer],
    *,
    max_backup_answers: int = 2,
) -> RecommendationAnswerSet:
    primary_signature = _answer_signature(primary_answer)
    seen_signatures = {primary_signature}
    backup_answers: list[RecommendationAnswer] = []
    for answer in candidate_backup_answers:
        if not _eligible_backup_answer(answer):
            continue
        signature = _answer_signature(answer)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        backup_answers.append(answer)
        if len(backup_answers) >= max(0, max_backup_answers):
            break
    return RecommendationAnswerSet(
        primary_answer=primary_answer,
        backup_answers=backup_answers,
        summary_json={
            "calculation_basis": "public_final_answer_envelope_v3_1",
            "primary_status": primary_answer.status,
            "primary_pass_type": primary_answer.pass_type,
            "primary_mode": primary_answer.mode,
            "primary_fixture_count": primary_answer.fixture_count,
            "candidate_backup_count": len(candidate_backup_answers),
            "backup_count": len(backup_answers),
            "max_backup_count": max(0, max_backup_answers),
            "public_scope": "single_best_answer_with_necessary_backups",
        },
    )


def build_candidate_recommendation_answer(
    scored_candidate: ScoredRecommendationCandidate | None,
    *,
    generated_at_utc: datetime,
    pass_type: str,
    mode: RecommendationMode = "single",
    unit_stake: float = 2.0,
    max_budget: float | None = None,
    unavailable_warning: str,
) -> RecommendationAnswer:
    if scored_candidate is None:
        return RecommendationAnswer(
            status="unavailable",
            generated_at_utc=generated_at_utc,
            pass_type=pass_type,
            mode=mode,
            warnings=[unavailable_warning],
        )

    candidate = scored_candidate.candidate
    expected_payout = (
        unit_stake * candidate.probability * candidate.decimal_odds
        if candidate.decimal_odds is not None
        else None
    )
    expected_value = expected_payout - unit_stake if expected_payout is not None else None
    roi = expected_value / unit_stake if expected_value is not None else None
    risk_score = clamp_probability(1.0 - candidate.probability + candidate.volatility_penalty)
    return RecommendationAnswer(
        status="ready",
        generated_at_utc=generated_at_utc,
        pass_type=pass_type,
        mode=mode,
        is_multiple=False,
        fixture_count=1,
        legs=[
            RecommendationAnswerLeg(
                fixture_id=candidate.fixture_id,
                market_type=candidate.market_type,
                outcomes=[candidate.outcome],
                probability=candidate.probability,
                decimal_odds=candidate.decimal_odds,
                line=candidate.line,
                side=candidate.side,
                data_quality_score=candidate.data_quality_score,
                model_version=candidate.model_version,
                prediction_snapshot_id=candidate.prediction_snapshot_id,
                prediction_time_utc=candidate.prediction_time_utc,
                kickoff_time_utc=candidate.kickoff_time_utc,
                recommendation_score=scored_candidate.score,
            )
        ],
        budget=RecommendationBudgetSummary(
            unit_stake=unit_stake,
            total_stake=unit_stake,
            max_budget=max_budget,
            within_budget=max_budget is None or unit_stake <= max_budget,
        ),
        atomic_bet_count=1,
        hit_probability=candidate.probability,
        expected_payout=expected_payout,
        expected_value=expected_value,
        roi=roi,
        risk_score=risk_score,
        risk_level=risk_level_from_score(risk_score),
        rule_valid=max_budget is None or unit_stake <= max_budget,
        average_data_quality_score=candidate.data_quality_score,
        data_quality_grade=_data_quality_grade(candidate.data_quality_score),
    )


def _budget_limit(
    explanation_json: dict[str, object],
    *,
    max_budget: float | None,
) -> float | None:
    if max_budget is not None:
        return max_budget
    budget_payload = explanation_json.get("budget")
    if not isinstance(budget_payload, dict):
        return None
    raw_budget = budget_payload.get("max_budget")
    if isinstance(raw_budget, int | float) and raw_budget > 0:
        return float(raw_budget)
    return None


def _eligible_backup_answer(answer: RecommendationAnswer) -> bool:
    if answer.status != "ready":
        return False
    if not answer.rule_valid:
        return False
    return answer.budget is None or answer.budget.within_budget


def _answer_signature(answer: RecommendationAnswer) -> tuple[
    str | None,
    RecommendationMode | None,
    tuple[tuple[str, str, tuple[str, ...], float | None, str | None], ...],
]:
    return (
        answer.pass_type,
        answer.mode,
        tuple(
            (
                leg.fixture_id,
                leg.market_type,
                tuple(leg.outcomes),
                leg.line,
                leg.side,
            )
            for leg in answer.legs
        ),
    )


def _average(values: Iterable[float]) -> float | None:
    collected = [float(value) for value in values]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _data_quality_grade(score: float) -> Literal["A", "B", "C", "D"]:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"
