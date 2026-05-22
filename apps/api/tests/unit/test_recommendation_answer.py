from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations.answer import (
    RecommendationAnswer,
    RecommendationAnswerLeg,
    RecommendationBudgetSummary,
    build_public_recommendation_answer_set,
    build_recommendation_answer,
)
from nutmeg.recommendations.engine import RecommendationGenerationResult
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)


def test_recommendation_answer_contains_final_ticket_without_strategy_payload() -> None:
    result = RecommendationGenerationResult(
        dry_run=True,
        as_of_time_utc=datetime(2026, 5, 9, 10, tzinfo=UTC),
        candidate_count=2,
        generated_count=1,
        selection=RecommendationSelection(
            pass_type="2x1",
            mode="single",
            selected_candidates=[
                ScoredRecommendationCandidate(
                    candidate=RecommendationCandidate(
                        fixture_id="fix_a",
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.64,
                        decimal_odds=1.8,
                        data_quality_score=88,
                        model_version="poisson-m1.0.0",
                        prediction_snapshot_id=31,
                        prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                        kickoff_time_utc=datetime(2026, 5, 10, 12, tzinfo=UTC),
                    ),
                    score=0.71,
                ),
                ScoredRecommendationCandidate(
                    candidate=RecommendationCandidate(
                        fixture_id="fix_b",
                        market_type="cn_handicap_1x2",
                        outcome="handicap_away_win",
                        probability=0.58,
                        decimal_odds=1.9,
                        data_quality_score=82,
                        model_version="poisson-m1.0.0",
                        prediction_snapshot_id=32,
                        prediction_time_utc=datetime(2026, 5, 9, 9, tzinfo=UTC),
                        kickoff_time_utc=datetime(2026, 5, 10, 14, tzinfo=UTC),
                    ),
                    score=0.68,
                ),
            ],
            evaluation=ParlayEvaluation(
                pass_type="2x1",
                unit_stake=2,
                total_atomic_bets=1,
                total_stake=2,
                hit_probability=0.3712,
                expected_payout=6.84,
                expected_value=0.54,
                roi=0.27,
                risk_score=0.42,
                risk_level="medium",
                explanation_json={"budget": {"max_budget": 20}},
            ),
            total_score=0.695,
            candidate_count=2,
            excluded_candidate_count=0,
            explanation_json={"strategy": "upset_protection"},
        ),
    )

    answer = build_recommendation_answer(result)

    assert answer.status == "ready"
    assert answer.pass_type == "2x1"
    assert answer.fixture_count == 2
    assert answer.budget is not None
    assert answer.budget.within_budget is True
    assert answer.data_quality_grade == "A"
    assert "strategy" not in answer.model_dump(mode="json")


def test_public_answer_set_keeps_only_distinct_budget_safe_backups() -> None:
    primary = _answer("2x1", ["fix_a", "fix_b"])
    duplicate = _answer("2x1", ["fix_a", "fix_b"])
    over_budget = _answer("4x1", ["fix_c", "fix_d"], within_budget=False)
    backup = _answer("6x1", ["fix_e", "fix_f", "fix_g"])
    second_backup = _answer("multiple", ["fix_h", "fix_i"], mode="multiple")

    answer_set = build_public_recommendation_answer_set(
        primary,
        [duplicate, over_budget, backup, second_backup],
    )

    assert answer_set.primary_answer == primary
    assert answer_set.backup_answers == [backup, second_backup]
    assert answer_set.summary_json == {
        "calculation_basis": "public_final_answer_envelope_v3_1",
        "primary_status": "ready",
        "primary_pass_type": "2x1",
        "primary_mode": "single",
        "primary_fixture_count": 2,
        "candidate_backup_count": 4,
        "backup_count": 2,
        "max_backup_count": 2,
        "public_scope": "single_best_answer_with_necessary_backups",
    }
    assert "strategy" not in answer_set.model_dump_json()


def _answer(
    pass_type: str,
    fixture_ids: list[str],
    *,
    mode: str = "single",
    within_budget: bool = True,
) -> RecommendationAnswer:
    return RecommendationAnswer(
        status="ready",
        generated_at_utc=datetime(2026, 5, 9, 10, tzinfo=UTC),
        pass_type=pass_type,
        mode=cast(RecommendationMode, mode),
        fixture_count=len(fixture_ids),
        legs=[
            RecommendationAnswerLeg(
                fixture_id=fixture_id,
                market_type="1x2",
                outcomes=["home_win"],
                probability=0.60,
                decimal_odds=1.80,
                data_quality_score=88,
                recommendation_score=0.72,
            )
            for fixture_id in fixture_ids
        ],
        budget=RecommendationBudgetSummary(
            unit_stake=2.0,
            total_stake=2.0,
            max_budget=20.0,
            within_budget=within_budget,
        ),
        atomic_bet_count=1,
        hit_probability=0.36,
        expected_payout=3.4,
        expected_value=0.4,
        roi=0.2,
        risk_score=0.42,
        risk_level="medium",
        rule_valid=within_budget,
        average_data_quality_score=88,
        data_quality_grade="A",
    )
