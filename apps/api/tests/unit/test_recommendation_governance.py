from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from json import loads

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.governance import (
    GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY,
    INSERT_RECOMMENDATION_STRATEGY_REVIEW_QUERY,
    PostgresRecommendationStrategyGovernanceRepository,
    RecommendationStrategyEvidence,
    RecommendationStrategyGovernanceOverview,
    RecommendationStrategyReviewOptions,
    build_mock_recommendation_strategy_governance_overview,
    build_recommendation_strategy_review_artifact,
    evaluate_recommendation_strategy_promotion,
    evaluate_recommendation_strategy_rollback,
    run_recommendation_strategy_review,
    select_recommendation_strategy_from_governance,
)


def test_recommendation_strategy_evidence_query_excludes_superseded_source_runs() -> None:
    assert (
        "internal_trace,successor_recompute,source_recommendation_run_id"
        in GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY
    )
    assert "successor.status <> 'invalidated'" in GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY


def test_recommendation_strategy_promotion_promotes_better_settled_strategy() -> None:
    review = evaluate_recommendation_strategy_promotion(
        candidate_evidence=_evidence(
            "upset_protection",
            sample_size=80,
            roi=0.12,
            hit_rate=0.48,
            calibration_error=0.04,
            single_focus_hit_rate=0.55,
            single_focus_calibration_error=0.04,
            upset_focus_capture_rate=0.36,
            upset_focus_calibration_error=0.09,
        ),
        baseline_evidence=_evidence(
            "accuracy_first",
            sample_size=90,
            roi=0.08,
            hit_rate=0.47,
            calibration_error=0.05,
            single_focus_hit_rate=0.50,
            single_focus_calibration_error=0.06,
            upset_focus_capture_rate=0.25,
            upset_focus_calibration_error=0.12,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="upset_protection",
            minimum_sample_size=50,
            minimum_baseline_sample_size=50,
            min_roi_delta=0.02,
        ),
    )

    assert review.decision == "shadow_candidate"
    assert review.next_status == "shadow"
    assert review.reasons == ["strategy_passed_first_governance_gate"]


def test_recommendation_strategy_promotion_keeps_experiment_when_evidence_is_weak() -> None:
    review = evaluate_recommendation_strategy_promotion(
        candidate_evidence=_evidence(
            "value_first",
            sample_size=12,
            roi=-0.04,
            hit_rate=0.40,
            calibration_error=0.18,
        ),
        baseline_evidence=_evidence(
            "accuracy_first",
            sample_size=60,
            roi=0.07,
            hit_rate=0.48,
            calibration_error=0.04,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="value_first",
            minimum_sample_size=30,
            minimum_baseline_sample_size=30,
            min_roi_delta=0.0,
            min_candidate_roi=0.0,
            tolerated_hit_rate_drop=0.02,
            tolerated_calibration_error_delta=0.05,
        ),
    )

    assert review.decision == "keep_experiment"
    assert review.next_status == "experiment"
    assert "candidate_sample_size_below_minimum" in review.reasons
    assert "candidate_roi_below_minimum" in review.reasons
    assert "candidate_roi_not_better_than_baseline" in review.reasons
    assert "candidate_hit_rate_drop_too_large" in review.reasons
    assert "candidate_hit_calibration_worse" in review.reasons


def test_recommendation_strategy_rollback_plan_restores_baseline_when_candidate_degrades() -> None:
    plan = evaluate_recommendation_strategy_rollback(
        active_evidence=_evidence(
            "value_first",
            sample_size=70,
            roi=-0.16,
            hit_rate=0.41,
            calibration_error=0.31,
        ),
        previous_evidence=_evidence(
            "accuracy_first",
            sample_size=80,
            roi=0.02,
            hit_rate=0.46,
            calibration_error=0.07,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="value_first",
            minimum_sample_size=50,
            rollback_roi_floor=-0.10,
            rollback_max_roi_underperformance=0.10,
            rollback_calibration_error_ceiling=0.25,
        ),
    )

    assert plan.should_rollback is True
    assert plan.target_strategy == "accuracy_first"
    assert plan.reasons == [
        "active_strategy_roi_below_floor",
        "active_strategy_roi_underperforms_previous",
        "active_strategy_hit_calibration_drift",
    ]
    assert plan.steps == [
        "mark_candidate_strategy_experiment_only",
        "restore_baseline_strategy_as_default",
        "pause_candidate_strategy_publication",
        "generate_recommendation_strategy_review_report",
    ]


def test_recommendation_strategy_review_artifact_contains_deltas_and_thresholds() -> None:
    artifact = build_recommendation_strategy_review_artifact(
        candidate_evidence=_evidence(
            "upset_protection",
            sample_size=80,
            roi=0.12,
            hit_rate=0.48,
            calibration_error=0.04,
            single_focus_hit_rate=0.55,
            single_focus_calibration_error=0.04,
            upset_focus_capture_rate=0.36,
            upset_focus_calibration_error=0.09,
        ),
        baseline_evidence=_evidence(
            "accuracy_first",
            sample_size=90,
            roi=0.08,
            hit_rate=0.47,
            calibration_error=0.05,
            single_focus_hit_rate=0.50,
            single_focus_calibration_error=0.06,
            upset_focus_capture_rate=0.25,
            upset_focus_calibration_error=0.12,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="upset_protection",
            baseline_strategy="accuracy_first",
            pass_type="3x1",
            mode="multiple",
            minimum_sample_size=50,
            minimum_baseline_sample_size=50,
            min_roi_delta=0.02,
        ),
    )

    assert artifact.review_key.startswith(
        "v3_1_strategy_review_upset_protection_vs_accuracy_first_3x1_multiple"
    )
    assert artifact.metrics_json["deltas"] == {
        "roi_delta": 0.039999999999999994,
        "hit_rate_delta": 0.010000000000000009,
        "mean_absolute_hit_calibration_error_delta": -0.010000000000000002,
        "single_focus_hit_rate_delta": 0.050000000000000044,
        "mean_absolute_single_focus_calibration_error_delta": -0.019999999999999997,
        "upset_focus_capture_rate_delta": 0.10999999999999999,
        "mean_absolute_upset_focus_calibration_error_delta": -0.03,
        "expected_roi_delta": 0.039999999999999994,
    }
    assert artifact.metrics_json["thresholds"]["minimum_sample_size"] == 50
    assert artifact.metrics_json["thresholds"]["minimum_focus_sample_size"] == 30
    assert artifact.rollback_plan.should_rollback is False


def test_recommendation_strategy_promotion_uses_focus_policy_evidence_when_available() -> None:
    review = evaluate_recommendation_strategy_promotion(
        candidate_evidence=_evidence(
            "value_first",
            sample_size=80,
            roi=0.12,
            hit_rate=0.49,
            calibration_error=0.04,
            single_focus_hit_rate=0.43,
            single_focus_calibration_error=0.15,
            upset_focus_capture_rate=0.18,
            upset_focus_calibration_error=0.22,
        ),
        baseline_evidence=_evidence(
            "accuracy_first",
            sample_size=90,
            roi=0.08,
            hit_rate=0.48,
            calibration_error=0.05,
            single_focus_hit_rate=0.52,
            single_focus_calibration_error=0.06,
            upset_focus_capture_rate=0.30,
            upset_focus_calibration_error=0.12,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="value_first",
            minimum_sample_size=50,
            minimum_baseline_sample_size=50,
            minimum_focus_sample_size=30,
        ),
    )

    assert review.decision == "keep_experiment"
    assert "candidate_single_focus_hit_rate_drop_too_large" in review.reasons
    assert "candidate_single_focus_calibration_worse" in review.reasons
    assert "candidate_upset_focus_capture_rate_drop_too_large" in review.reasons
    assert "candidate_upset_focus_calibration_worse" in review.reasons


def test_recommendation_strategy_rollback_uses_focus_calibration_drift() -> None:
    plan = evaluate_recommendation_strategy_rollback(
        active_evidence=_evidence(
            "upset_protection",
            sample_size=80,
            roi=0.04,
            hit_rate=0.48,
            calibration_error=0.05,
            single_focus_hit_rate=0.50,
            single_focus_calibration_error=0.34,
            upset_focus_capture_rate=0.25,
            upset_focus_calibration_error=0.37,
        ),
        previous_evidence=_evidence(
            "accuracy_first",
            sample_size=90,
            roi=0.03,
            hit_rate=0.47,
            calibration_error=0.06,
            single_focus_hit_rate=0.49,
            single_focus_calibration_error=0.07,
            upset_focus_capture_rate=0.24,
            upset_focus_calibration_error=0.12,
        ),
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="upset_protection",
            minimum_sample_size=50,
            minimum_focus_sample_size=30,
            rollback_focus_calibration_error_ceiling=0.30,
        ),
    )

    assert plan.should_rollback is True
    assert plan.reasons == [
        "active_strategy_single_focus_calibration_drift",
        "active_strategy_upset_focus_calibration_drift",
    ]


def test_postgres_recommendation_strategy_governance_repository_reads_and_saves() -> None:
    database = FakeRecommendationStrategyGovernanceDatabase()
    repository = PostgresRecommendationStrategyGovernanceRepository(database)

    result = run_recommendation_strategy_review(
        repository,
        options=RecommendationStrategyReviewOptions(
            candidate_strategy="upset_protection",
            baseline_strategy="accuracy_first",
            pass_type="2x1",
            mode="single",
            minimum_sample_size=50,
            minimum_baseline_sample_size=50,
            dry_run=False,
        ),
    )

    assert result.dry_run is False
    assert result.stored_review is not None
    assert result.stored_review.recommendation_strategy_review_id == 401
    assert result.artifact.promotion_review.decision == "shadow_candidate"
    assert result.artifact.candidate_evidence.single_focus_hit_rate == 0.52
    assert result.artifact.candidate_evidence.upset_focus_capture_rate == 0.31
    assert [query for query, _params in database.fetch_one_calls] == [
        GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY,
        GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY,
        INSERT_RECOMMENDATION_STRATEGY_REVIEW_QUERY,
    ]
    save_params = database.fetch_one_calls[2][1]
    assert save_params["candidate_strategy"] == "upset_protection"
    assert save_params["baseline_strategy"] == "accuracy_first"
    assert loads(str(save_params["reasons_json"])) == ["strategy_passed_first_governance_gate"]
    assert loads(str(save_params["rollback_plan_json"]))["should_rollback"] is False
    saved_metrics = loads(str(save_params["metrics_json"]))
    assert "single_focus_hit_rate_delta" in saved_metrics["deltas"]
    assert "upset_focus_capture_rate_delta" in saved_metrics["deltas"]


def test_strategy_auto_selection_uses_best_governance_candidate() -> None:
    overview = build_mock_recommendation_strategy_governance_overview(
        candidate_strategies=[
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        baseline_strategy="accuracy_first",
        pass_type="2x1",
        mode="single",
        minimum_sample_size=30,
        minimum_baseline_sample_size=30,
    )

    selection = select_recommendation_strategy_from_governance(
        overview,
        requested_strategy="auto",
        baseline_strategy="accuracy_first",
        pass_type="2x1",
        mode="single",
    )

    assert selection.selected_strategy == "upset_protection"
    assert selection.source == "governance_overview"
    assert selection.review_key is not None
    assert "selected_by_recommendation_strategy_governance" in selection.reasons
    assert selection.metric_deltas["roi_delta"] > 0


def test_strategy_auto_selection_falls_back_to_baseline_without_evidence() -> None:
    selection = select_recommendation_strategy_from_governance(
        RecommendationStrategyGovernanceOverview(
            generated_at_utc=datetime(2026, 5, 9, tzinfo=UTC),
        ),
        requested_strategy="auto",
        baseline_strategy="accuracy_first",
        pass_type="2x1",
        mode="single",
    )

    assert selection.selected_strategy == "accuracy_first"
    assert selection.source == "baseline_fallback"
    assert selection.reasons == ["no_candidate_strategy_passed_governance_gate"]
    assert "strategy_governance_overview_empty" in selection.warnings


def _evidence(
    strategy: str,
    *,
    sample_size: int,
    roi: float | None,
    hit_rate: float | None,
    calibration_error: float | None,
    single_focus_hit_rate: float | None = None,
    single_focus_calibration_error: float | None = None,
    upset_focus_capture_rate: float | None = None,
    upset_focus_calibration_error: float | None = None,
) -> RecommendationStrategyEvidence:
    single_focus_sample_size = sample_size if single_focus_hit_rate is not None else 0
    upset_focus_sample_size = sample_size if upset_focus_capture_rate is not None else 0
    return RecommendationStrategyEvidence(
        strategy=strategy,
        pass_type="2x1",
        mode="single",
        sample_size=sample_size,
        settled_run_count=sample_size,
        hit_count=int(sample_size * (hit_rate or 0)),
        total_stake=sample_size * 2.0,
        gross_payout=sample_size * 2.0 * (1.0 + (roi or 0.0)),
        profit_loss=sample_size * 2.0 * (roi or 0.0),
        roi=roi,
        hit_rate=hit_rate,
        average_expected_roi=roi,
        average_expected_hit_probability=hit_rate,
        average_hit_calibration_error=0.0,
        mean_absolute_hit_calibration_error=calibration_error,
        single_focus_sample_size=single_focus_sample_size,
        single_focus_hit_count=int(single_focus_sample_size * (single_focus_hit_rate or 0.0)),
        single_focus_hit_rate=single_focus_hit_rate,
        average_single_focus_calibration_error=(
            0.0 if single_focus_calibration_error is not None else None
        ),
        mean_absolute_single_focus_calibration_error=single_focus_calibration_error,
        upset_focus_sample_size=upset_focus_sample_size,
        upset_focus_capture_count=int(
            upset_focus_sample_size * (upset_focus_capture_rate or 0.0)
        ),
        upset_focus_capture_rate=upset_focus_capture_rate,
        average_upset_focus_calibration_error=(
            0.0 if upset_focus_calibration_error is not None else None
        ),
        mean_absolute_upset_focus_calibration_error=upset_focus_calibration_error,
        first_evaluation_time_utc=datetime(2026, 5, 1, tzinfo=UTC),
        last_evaluation_time_utc=datetime(2026, 5, 9, tzinfo=UTC),
    )


class FakeRecommendationStrategyGovernanceDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == GET_RECOMMENDATION_STRATEGY_EVIDENCE_QUERY:
            strategy = str(params["strategy"])
            if strategy == "upset_protection":
                return _evidence_row(
                    strategy="upset_protection",
                    sample_size=80,
                    roi=0.12,
                    hit_rate=0.48,
                    calibration_error=0.04,
                )
            return _evidence_row(
                strategy="accuracy_first",
                sample_size=90,
                roi=0.08,
                hit_rate=0.47,
                calibration_error=0.05,
            )
        if query == INSERT_RECOMMENDATION_STRATEGY_REVIEW_QUERY:
            return {
                "recommendation_strategy_review_id": 401,
                "created_at": datetime(2026, 5, 10, tzinfo=UTC),
            }
        raise AssertionError(f"unexpected query: {query}")


def _evidence_row(
    *,
    strategy: str,
    sample_size: int,
    roi: float,
    hit_rate: float,
    calibration_error: float,
    single_focus_hit_rate: float = 0.52,
    single_focus_calibration_error: float = 0.05,
    upset_focus_capture_rate: float = 0.31,
    upset_focus_calibration_error: float = 0.10,
) -> Mapping[str, object]:
    return {
        "strategy": strategy,
        "pass_type": "2x1",
        "mode": "single",
        "sample_size": sample_size,
        "settled_run_count": sample_size,
        "hit_count": int(sample_size * hit_rate),
        "total_stake": sample_size * 2.0,
        "gross_payout": sample_size * 2.0 * (1.0 + roi),
        "profit_loss": sample_size * 2.0 * roi,
        "roi": roi,
        "hit_rate": hit_rate,
        "average_expected_roi": roi,
        "average_expected_hit_probability": hit_rate,
        "average_hit_calibration_error": 0.0,
        "mean_absolute_hit_calibration_error": calibration_error,
        "single_focus_sample_size": sample_size,
        "single_focus_hit_count": int(sample_size * single_focus_hit_rate),
        "single_focus_hit_rate": single_focus_hit_rate,
        "average_single_focus_calibration_error": 0.0,
        "mean_absolute_single_focus_calibration_error": single_focus_calibration_error,
        "upset_focus_sample_size": sample_size,
        "upset_focus_capture_count": int(sample_size * upset_focus_capture_rate),
        "upset_focus_capture_rate": upset_focus_capture_rate,
        "average_upset_focus_calibration_error": 0.0,
        "mean_absolute_upset_focus_calibration_error": upset_focus_calibration_error,
        "first_evaluation_time_utc": datetime(2026, 5, 1, tzinfo=UTC),
        "last_evaluation_time_utc": datetime(2026, 5, 9, tzinfo=UTC),
    }
