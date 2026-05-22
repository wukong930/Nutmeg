from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.evaluation import (
    LIST_RECOMMENDATION_RUN_EVALUATIONS_QUERY,
    LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY,
    LIST_RESULTS_FOR_RECOMMENDATION_FIXTURES_QUERY,
    UPSERT_RECOMMENDATION_RUN_EVALUATION_QUERY,
    PostgresRecommendationEvaluationRepository,
    RecommendationEvaluationOptions,
    RecommendationRunForEvaluation,
    evaluate_recommendation_run,
    run_recommendation_evaluation,
    summarize_recommendation_strategy_evaluations,
)


def test_recommendation_evaluation_settles_atomic_bets_and_computes_roi() -> None:
    evaluation = evaluate_recommendation_run(
        _run_for_evaluation(),
        result_rows=[
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
        ],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )

    assert evaluation.evaluation_status == "settled"
    assert evaluation.total_atomic_bets == 2
    assert evaluation.won_atomic_bets == 1
    assert evaluation.lost_atomic_bets == 1
    assert evaluation.unresolved_atomic_bets == 0
    assert evaluation.gross_payout == 7.2
    assert evaluation.profit_loss == 3.2
    assert evaluation.roi == 0.8
    assert evaluation.hit is True
    assert evaluation.hit_rate == 0.5
    assert evaluation.expected_hit_probability_at_recommendation == 0.43
    assert evaluation.hit_calibration_error == 0.5700000000000001
    assert evaluation.expected_roi_at_recommendation == 0.35
    assert evaluation.locked_fixture_count == 1
    assert evaluation.selected_fixture_count == 2
    assert (
        evaluation.settlement_detail_json["calculation_basis"]
        == "stored_recommendation_parlay_evaluation_atomic_bets_settled_against_results"
    )


def test_recommendation_evaluation_marks_missing_results_unresolved() -> None:
    evaluation = evaluate_recommendation_run(
        _run_for_evaluation(),
        result_rows=[{"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0}],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )

    assert evaluation.evaluation_status == "unresolved"
    assert evaluation.unresolved_atomic_bets == 2
    assert evaluation.hit is None
    assert evaluation.hit_rate is None


def test_recommendation_evaluation_summary_groups_strategy_performance() -> None:
    settled = evaluate_recommendation_run(
        _run_for_evaluation(),
        result_rows=[
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
        ],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )
    unresolved = evaluate_recommendation_run(
        _run_for_evaluation(recommendation_run_id=78),
        result_rows=[{"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0}],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )

    metrics = summarize_recommendation_strategy_evaluations([settled, unresolved])

    assert len(metrics) == 1
    assert metrics[0].strategy == "accuracy_first"
    assert metrics[0].sample_size == 2
    assert metrics[0].settled_run_count == 1
    assert metrics[0].hit_count == 1
    assert metrics[0].total_stake == 4.0
    assert metrics[0].roi == 0.8
    assert metrics[0].average_expected_hit_probability == 0.43
    assert metrics[0].average_hit_calibration_error == 0.5700000000000001
    assert metrics[0].average_expected_roi == 0.35


def test_recommendation_evaluation_settles_focus_policy_answers() -> None:
    evaluation = evaluate_recommendation_run(
        _run_for_evaluation(explanation_json=_focus_explanation_json()),
        result_rows=[
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
            {"fixture_id": "fix_focus_upset", "home_goals": 0, "away_goals": 1},
        ],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )

    assert evaluation.single_focus_hit is True
    assert evaluation.single_focus_expected_probability == 0.78
    assert evaluation.single_focus_calibration_error == 0.21999999999999997
    assert evaluation.upset_focus_triggered is True
    assert evaluation.upset_focus_captured is True
    assert evaluation.upset_focus_expected_probability == 0.31
    assert evaluation.upset_focus_calibration_error == 0.69
    focus_detail = evaluation.settlement_detail_json["focus_policy_evaluation"]
    assert isinstance(focus_detail, dict)
    single_detail = focus_detail["single"]
    upset_detail = focus_detail["upset"]
    assert isinstance(single_detail, dict)
    assert isinstance(upset_detail, dict)
    assert single_detail["result_status"] == "won"
    assert upset_detail["actual_outcome"] == "away_win"


def test_recommendation_evaluation_summary_includes_focus_policy_metrics() -> None:
    settled = evaluate_recommendation_run(
        _run_for_evaluation(explanation_json=_focus_explanation_json()),
        result_rows=[
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
            {"fixture_id": "fix_focus_upset", "home_goals": 0, "away_goals": 1},
        ],
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )

    metrics = summarize_recommendation_strategy_evaluations([settled])

    assert metrics[0].single_focus_sample_size == 1
    assert metrics[0].single_focus_hit_count == 1
    assert metrics[0].single_focus_hit_rate == 1.0
    assert metrics[0].average_single_focus_calibration_error == 0.21999999999999997
    assert metrics[0].upset_focus_sample_size == 1
    assert metrics[0].upset_focus_capture_count == 1
    assert metrics[0].upset_focus_capture_rate == 1.0
    assert metrics[0].average_upset_focus_calibration_error == 0.69


def test_postgres_recommendation_evaluation_repository_reads_and_saves() -> None:
    database = FakeRecommendationEvaluationDatabase()
    repository = PostgresRecommendationEvaluationRepository(database)

    runs = repository.list_pending_runs(limit=3, eligible_statuses=("confirmed_manual",))
    results = repository.list_results_for_fixture_ids(runs[0].selected_fixture_ids)
    evaluation = evaluate_recommendation_run(
        runs[0],
        result_rows=results,
        evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
    )
    stored = repository.save_run_evaluation(evaluation)

    assert runs[0].selected_fixture_ids == ["fix_a", "fix_b"]
    assert runs[0].expected_hit_probability_at_recommendation == 0.43
    assert runs[0].expected_value_at_recommendation == 1.4
    assert stored.recommendation_run_evaluation_id == 901
    assert [query for query, _params in database.fetch_all_calls] == [
        LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY,
        LIST_RESULTS_FOR_RECOMMENDATION_FIXTURES_QUERY,
    ]
    save_query, save_params = database.fetch_one_calls[0]
    assert save_query == UPSERT_RECOMMENDATION_RUN_EVALUATION_QUERY
    assert save_params["recommendation_run_id"] == 77
    assert save_params["evaluation_status"] == "settled"
    assert save_params["won_atomic_bets"] == 1


def test_recommendation_evaluation_runner_fetches_focus_answer_results() -> None:
    database = FakeRecommendationEvaluationDatabase(
        expected_fixture_ids=["fix_a", "fix_b", "fix_focus_upset"],
        explanation_json=_focus_explanation_json(),
        result_rows=[
            {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
            {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
            {"fixture_id": "fix_focus_upset", "home_goals": 0, "away_goals": 1},
        ],
    )
    repository = PostgresRecommendationEvaluationRepository(database)

    result = run_recommendation_evaluation(
        repository,
        options=RecommendationEvaluationOptions(
            evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
            limit=10,
        ),
    )

    assert result.evaluated_runs == 1
    assert result.evaluations[0].upset_focus_captured is True
    _query, params = database.fetch_all_calls[1]
    assert params["fixture_ids"] == ["fix_a", "fix_b", "fix_focus_upset"]


def test_recommendation_evaluation_runner_skips_unresolved_by_default() -> None:
    database = FakeRecommendationEvaluationDatabase(result_rows=[])
    repository = PostgresRecommendationEvaluationRepository(database)

    result = run_recommendation_evaluation(
        repository,
        options=RecommendationEvaluationOptions(
            evaluation_time_utc=datetime(2026, 5, 11, 1, tzinfo=UTC),
            limit=10,
        ),
    )

    assert result.checked_runs == 1
    assert result.evaluated_runs == 0
    assert result.skipped_unresolved_runs == 1
    assert result.stored_evaluation_ids == []
    assert result.warnings == ["recommendation_run_unresolved:77"]
    assert database.fetch_one_calls == []


def test_recommendation_evaluation_queries_exclude_superseded_source_runs() -> None:
    successor_path = (
        "internal_trace,successor_recompute,source_recommendation_run_id"
    )

    assert successor_path in LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY
    assert successor_path in LIST_RECOMMENDATION_RUN_EVALUATIONS_QUERY
    assert "successor.status <> 'invalidated'" in (
        LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY
    )
    assert "successor.status <> 'invalidated'" in LIST_RECOMMENDATION_RUN_EVALUATIONS_QUERY


def _run_for_evaluation(
    recommendation_run_id: int = 77,
    *,
    explanation_json: dict[str, object] | None = None,
) -> RecommendationRunForEvaluation:
    return RecommendationRunForEvaluation(
        recommendation_run_id=recommendation_run_id,
        run_key=f"rec-{recommendation_run_id}",
        strategy="accuracy_first",
        pass_type="2x1",
        mode="multiple",
        recommendation_status="confirmed_manual",
        unit_stake=2.0,
        total_stake=4.0,
        selected_fixture_ids=["fix_a", "fix_b"],
        locked_fixture_ids=["fix_a"],
        parlay_evaluation_json=_parlay_evaluation_json(),
        explanation_json=explanation_json or {},
        expected_hit_probability_at_recommendation=0.43,
        expected_value_at_recommendation=1.4,
        expected_roi_at_recommendation=0.35,
        created_at=datetime(2026, 5, 9, 10, tzinfo=UTC),
    )


def _parlay_evaluation_json() -> dict[str, object]:
    return {
        "pass_type": "2x1",
        "is_multiple": True,
        "unit_stake": 2.0,
        "total_atomic_bets": 2,
        "total_stake": 4.0,
        "hit_probability": 0.43,
        "expected_value": 1.4,
        "roi": 0.35,
        "atomic_bets": [
            {
                "legs": [
                    _atomic_leg("fix_a", "home_win", 0.64, 1.8),
                    _atomic_leg("fix_b", "away_win", 0.55, 2.0),
                ],
                "stake": 2.0,
                "probability": 0.352,
                "odds_product": 3.6,
                "expected_payout": 2.5344,
                "expected_value": 0.5344,
                "roi": 0.2672,
            },
            {
                "legs": [
                    _atomic_leg("fix_a", "draw", 0.22, 3.0),
                    _atomic_leg("fix_b", "away_win", 0.55, 2.0),
                ],
                "stake": 2.0,
                "probability": 0.121,
                "odds_product": 6.0,
                "expected_payout": 1.452,
                "expected_value": -0.548,
                "roi": -0.274,
            },
        ],
    }


def _atomic_leg(
    fixture_id: str,
    outcome: str,
    probability: float,
    odds: float,
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "market_type": "1x2",
        "outcome": outcome,
        "probability": probability,
        "odds": odds,
    }


def _focus_explanation_json() -> dict[str, object]:
    return {
        "internal_trace": {
            "focus_policy_answers": {
                "single": {
                    "fixture_id": "fix_a",
                    "market_type": "1x2",
                    "outcome": "home_win",
                    "probability": 0.78,
                    "decimal_odds": 1.42,
                    "recommendation_score": 0.86,
                    "upset_protection_score": 0.05,
                    "model_version": "poisson-m1.0.0",
                    "prediction_snapshot_id": 41,
                },
                "upset": {
                    "fixture_id": "fix_focus_upset",
                    "market_type": "1x2",
                    "outcome": "away_win",
                    "probability": 0.31,
                    "decimal_odds": 3.2,
                    "recommendation_score": 0.61,
                    "upset_protection_score": 0.93,
                    "model_version": "poisson-m1.0.0",
                    "prediction_snapshot_id": 42,
                },
            }
        }
    }


class FakeRecommendationEvaluationDatabase:
    def __init__(
        self,
        result_rows: Sequence[DatabaseRow] | None = None,
        *,
        expected_fixture_ids: Sequence[str] | None = None,
        explanation_json: dict[str, object] | None = None,
    ) -> None:
        self.result_rows = list(
            result_rows
            if result_rows is not None
            else [
                {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
                {"fixture_id": "fix_b", "home_goals": 0, "away_goals": 1},
            ]
        )
        self.expected_fixture_ids = list(expected_fixture_ids or ["fix_a", "fix_b"])
        self.explanation_json = explanation_json or {}
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_RECOMMENDATION_RUNS_PENDING_EVALUATION_QUERY:
            return [
                {
                    "recommendation_run_id": 77,
                    "run_key": "rec-77",
                    "strategy": "accuracy_first",
                    "pass_type": "2x1",
                    "mode": "multiple",
                    "recommendation_status": "confirmed_manual",
                    "unit_stake": 2.0,
                    "total_stake": 4.0,
                    "selected_fixture_ids_json": dumps(["fix_a", "fix_b"]),
                    "locked_fixture_ids_json": dumps(["fix_a"]),
                    "parlay_evaluation_json": dumps(_parlay_evaluation_json()),
                    "explanation_json": dumps(self.explanation_json),
                    "created_at": datetime(2026, 5, 9, 10, tzinfo=UTC),
                }
            ]
        if query == LIST_RESULTS_FOR_RECOMMENDATION_FIXTURES_QUERY:
            assert params["fixture_ids"] == self.expected_fixture_ids
            return self.result_rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == UPSERT_RECOMMENDATION_RUN_EVALUATION_QUERY:
            return {
                "recommendation_run_evaluation_id": 901,
                "created_at": datetime(2026, 5, 11, 1, tzinfo=UTC),
            }
        raise AssertionError(f"unexpected query: {query}")
