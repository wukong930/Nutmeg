from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps
from pathlib import Path
from typing import cast

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationCandidate,
    RecommendationGlobalPlannerOptions,
    StoredRecommendationRun,
    run_recommendation_global_planner,
)
from nutmeg.recommendations.models import RecommendationMarketType
from nutmeg.recommendations.repository import LIST_RECOMMENDATION_CANDIDATES_QUERY


class FakeGlobalPlannerDatabase:
    def __init__(self, candidates: Sequence[RecommendationCandidate]) -> None:
        self.rows = [
            _candidate_row(index, candidate)
            for index, candidate in enumerate(candidates, 1)
        ]
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_RECOMMENDATION_CANDIDATES_QUERY:
            return self.rows
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected query: {query}")


class FakeRecommendationRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[object, dict[str, object]]] = []

    def save_selection(self, selection: object, **kwargs: object) -> StoredRecommendationRun:
        self.saved.append((selection, dict(kwargs)))
        return StoredRecommendationRun(
            recommendation_run_id=901,
            created_at=_dt(2026, 5, 1, 12),
        )


def test_global_planner_compares_single_and_parlay_options() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.70, decimal_odds=1.72),
        _candidate("B", "home_win", probability=0.63, decimal_odds=1.82),
        _candidate("C", "away_win", probability=0.58, decimal_odds=1.95),
        _candidate("D", "draw", probability=0.31, decimal_odds=3.60, upset=0.70),
    ]

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            pass_types=("all",),
            modes=("single", "multiple"),
            unit_stake=2.0,
            max_budget=4.0,
            min_probability=0.20,
            dry_run=True,
        ),
    )

    assert result.candidate_count == 4
    assert result.evaluated_option_count >= 3
    assert result.best_option is not None
    assert result.best_option.within_budget is True
    assert result.best_option.selection.evaluation.rule_valid is True
    assert result.final_answer_decision_json["calculation_basis"] == (
        "final_answer_arbitrator_v3_1"
    )
    arbitration_payload = cast(
        dict[str, object],
        result.best_option.explanation_json["final_answer_arbitration"],
    )
    assert arbitration_payload["rank"] == 1
    assert result.best_option.pass_type in {"1x1", "2x1", "3x1", "4x1"}
    assert result.alternatives
    assert {
        option.option_type for option in [result.best_option, *result.alternatives]
    } >= {"standalone_single", "single_parlay"}


def test_global_planner_records_unified_candidate_pool_and_can_skip_2x1() -> None:
    candidates = [
        _candidate(
            "A",
            "1-0",
            market_type="correct_score",
            probability=0.82,
            decimal_odds=2.25,
        ),
        _candidate("B", "home_win", probability=0.21, decimal_odds=1.80),
        _candidate(
            "C",
            "handicap_away_win",
            market_type="cn_handicap_1x2",
            probability=0.25,
            decimal_odds=1.85,
            line=-1.0,
        ),
    ]

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            allowed_markets=("1x2", "cn_handicap_1x2", "correct_score"),
            pass_types=("1x1", "2x1"),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            min_probability=0.20,
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    assert result.best_option.pass_type == "1x1"
    assert result.best_option.option_type == "standalone_single"
    pool = cast(dict[str, object], result.final_answer_decision_json["unified_candidate_pool"])
    assert pool["calculation_basis"] == "unified_final_answer_candidate_pool_v3_2"
    assert pool["candidate_count"] == result.generated_option_count
    assert pool["valid_candidate_count"] == result.generated_option_count
    assert pool["selected_family_key"] == "standalone_single:1x1:single"
    assert pool["selected_pass_type"] == "1x1"
    assert pool["two_x_one_is_candidate_family"] is True
    assert pool["correct_score_candidate_present"] is True
    assert pool["handicap_candidate_present"] is True
    assert {
        "standalone_single:1x1:single",
        "single_parlay:2x1:single",
    }.issubset(set(cast(list[str], pool["candidate_family_keys"])))


def test_global_planner_can_select_handicap_final_answer_candidates() -> None:
    candidates = [
        _candidate(
            "A",
            "home_win",
            probability=0.52,
            decimal_odds=1.95,
        ),
        _candidate(
            "A",
            "handicap_away_win",
            market_type="cn_handicap_1x2",
            probability=0.72,
            decimal_odds=1.70,
            line=-1.0,
        ),
        _candidate(
            "B",
            "away_win",
            probability=0.51,
            decimal_odds=2.05,
        ),
        _candidate(
            "B",
            "handicap_home_win",
            market_type="european_handicap_1x2",
            probability=0.69,
            decimal_odds=1.75,
            line=1.0,
        ),
    ]

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            allowed_markets=("cn_handicap_1x2", "european_handicap_1x2"),
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            min_probability=0.20,
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    selected = result.best_option.selection.selected_candidates
    assert {item.candidate.market_type for item in selected} == {
        "cn_handicap_1x2",
        "european_handicap_1x2",
    }
    assert {item.candidate.line for item in selected} == {-1.0, 1.0}
    assert result.best_option.selection.evaluation.rule_valid is True
    rule_reasons = cast(
        list[str],
        result.best_option.selection.evaluation.explanation_json["rule_reasons"],
    )
    assert "unsupported_market_type" not in rule_reasons


def test_global_planner_keeps_dynamic_mixed_market_path_for_2x1_to_8x1() -> None:
    candidates = _dynamic_mixed_market_candidates()

    for leg_count in range(2, 9):
        result = run_recommendation_global_planner(
            FakeGlobalPlannerDatabase(candidates),
            options=RecommendationGlobalPlannerOptions(
                as_of_time_utc=_dt(2026, 5, 1, 12),
                pass_types=(f"{leg_count}x1",),
                modes=("single", "multiple"),
                unit_stake=2.0,
                max_budget=128.0,
                min_probability=0.20,
                max_outcomes_per_fixture=2,
                dry_run=True,
            ),
        )

        assert result.best_option is not None
        assert result.best_option.pass_type == f"{leg_count}x1"
        assert result.best_option.selection.evaluation.rule_valid is True
        assert result.best_option.within_budget is True
        assert len(result.best_option.selection.fixture_ids) == leg_count
        selected_markets = {
            item.candidate.market_type
            for item in result.best_option.selection.selected_candidates
        }
        assert "1x2" in selected_markets
        assert selected_markets & {"cn_handicap_1x2", "european_handicap_1x2"}
        assert len(selected_markets) >= 2
        arbitration_payload = cast(
            dict[str, object],
            result.best_option.explanation_json["final_answer_arbitration"],
        )
        assert arbitration_payload["dynamic_mixed_market_answer"] is True
        assert arbitration_payload["market_count"] == len(selected_markets)
        assert result.final_answer_decision_json["dynamic_mixed_market_answer"] is True
        assert set(
            cast(
                list[str],
                result.final_answer_decision_json["selected_market_types"],
            )
        ) == selected_markets
        assert "mixed_market_answer" in result.best_option.reason_codes
        assert "includes_handicap_market" in result.best_option.reason_codes


def test_global_planner_falls_back_when_requested_pass_type_has_too_few_fixtures() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.66, decimal_odds=1.65),
        _candidate("B", "home_win", probability=0.64, decimal_odds=1.75),
        _candidate("C", "away_win", probability=0.62, decimal_odds=1.80),
    ]

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            pass_types=("6x1", "2x1"),
            modes=("multiple",),
            unit_stake=2.0,
            max_budget=4.0,
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    assert result.best_option.pass_type == "2x1"
    assert result.best_option.mode == "multiple"
    assert any("6x1:multiple" in warning for warning in result.warnings)


def test_global_planner_records_multiple_value_admission_in_candidate_pool() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.62, decimal_odds=1.70),
        _candidate("A", "draw", probability=0.26, decimal_odds=3.40),
        _candidate("B", "home_win", probability=0.60, decimal_odds=1.80),
        _candidate("C", "away_win", probability=0.59, decimal_odds=1.80),
    ]

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            pass_types=("3x1",),
            modes=("multiple",),
            unit_stake=2.0,
            max_budget=4.0,
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    admission = cast(
        dict[str, object],
        result.best_option.explanation_json["multiple_value_admission"],
    )
    assert admission["status"] == "admitted"
    assert admission["extra_option_count"] == 1
    pool = cast(dict[str, object], result.final_answer_decision_json["unified_candidate_pool"])
    assert pool["multiple_value_candidate_count"] == 1
    assert pool["multiple_value_admitted_candidate_count"] == 1
    assert pool["multiple_value_rejected_candidate_count"] == 0
    assert pool["multiple_value_extra_option_count"] == 1
    assert pool["selected_multiple_value_status"] == "admitted"
    assert pool["selected_multiple_value_admitted"] is True
    assert pool["selected_multiple_extra_option_count"] == 1


def test_global_planner_preserves_locked_fixture_and_persists_best_selection() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.42, decimal_odds=2.40),
        _candidate("B", "home_win", probability=0.72, decimal_odds=1.50),
        _candidate("C", "away_win", probability=0.69, decimal_odds=1.55),
    ]
    repository = FakeRecommendationRepository()

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            locked_candidates=(candidates[0],),
            dry_run=False,
        ),
        repository=repository,  # type: ignore[arg-type]
    )

    assert result.best_option is not None
    assert result.best_option.selection.fixture_ids == ["A", "B"]
    assert result.best_option.selection.locked_fixture_ids == ["A"]
    assert result.stored_run is not None
    assert result.stored_run.recommendation_run_id == 901
    assert repository.saved
    _selection, kwargs = repository.saved[0]
    assert kwargs["source"] == "recommendation_global_planner_v3_1"
    assert kwargs["candidate_pool"]


def test_global_planner_value_first_avoids_adverse_odds_favorites() -> None:
    candidates = [
        _candidate("A", "home_win", probability=0.70, decimal_odds=1.25),
        _candidate("A", "draw", probability=0.31, decimal_odds=4.00),
        _candidate("B", "away_win", probability=0.68, decimal_odds=1.30),
        _candidate("B", "draw", probability=0.30, decimal_odds=4.20),
    ]

    accuracy_result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            strategy="accuracy_first",
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            dry_run=True,
        ),
    )
    value_result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            strategy="value_first",
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            dry_run=True,
        ),
    )

    assert accuracy_result.best_option is not None
    assert value_result.best_option is not None
    assert [
        item.candidate.outcome
        for item in accuracy_result.best_option.selection.selected_candidates
    ] == ["home_win", "away_win"]
    assert [
        item.candidate.outcome
        for item in value_result.best_option.selection.selected_candidates
    ] == ["draw", "draw"]
    assert all(
        item.candidate.effective_model_edge() >= 0.0
        for item in value_result.best_option.selection.selected_candidates
    )
    assert value_result.best_option.selection.excluded_candidate_count == 2


def test_global_planner_short_odds_adapter_shadow_records_internal_summary(
    tmp_path: Path,
) -> None:
    candidates = _short_odds_adapter_candidates()

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            strategy="accuracy_first",
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=20.0,
            min_probability=0.20,
            short_odds_adapter_enabled=True,
            short_odds_adapter_shadow_only=True,
            short_odds_adapter_rule_profile_path=_short_odds_rule_profile_path(tmp_path),
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    assert set(result.best_option.selection.fixture_ids) == {"A", "B"}
    summary = cast(
        dict[str, object],
        result.final_answer_decision_json["short_odds_final_answer_adapter"],
    )
    assert summary["status"] == "applied"
    assert summary["shadow_only"] is True
    assert summary["planner_option_changed"] is False
    assert summary["default_path_changed"] is False
    assert result.best_option.selection.explanation_json[
        "short_odds_final_answer_adapter"
    ] == summary


def test_global_planner_short_odds_adapter_explicit_opt_in_changes_best_option(
    tmp_path: Path,
) -> None:
    candidates = _short_odds_adapter_candidates()

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            strategy="accuracy_first",
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=20.0,
            min_probability=0.20,
            short_odds_adapter_enabled=True,
            short_odds_adapter_shadow_only=False,
            short_odds_adapter_rule_profile_path=_short_odds_rule_profile_path(tmp_path),
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    assert set(result.best_option.selection.fixture_ids) == {"B", "C"}
    assert "short_odds_final_answer_adapter_applied" in result.best_option.reason_codes
    summary = cast(
        dict[str, object],
        result.best_option.explanation_json["short_odds_final_answer_adapter"],
    )
    selected_action = cast(dict[str, object], summary["selected_action"])
    assert summary["status"] == "applied"
    assert summary["shadow_only"] is False
    assert summary["planner_option_changed"] is True
    assert summary["default_path_changed"] is True
    assert selected_action["removed_fixture_id"] == "A"
    assert selected_action["replacement_fixture_id"] == "C"


def test_global_planner_short_odds_adapter_preserves_locked_fixture(
    tmp_path: Path,
) -> None:
    candidates = _short_odds_adapter_candidates()

    result = run_recommendation_global_planner(
        FakeGlobalPlannerDatabase(candidates),
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=_dt(2026, 5, 1, 12),
            strategy="accuracy_first",
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=20.0,
            min_probability=0.20,
            locked_candidates=(candidates[0],),
            short_odds_adapter_enabled=True,
            short_odds_adapter_shadow_only=False,
            short_odds_adapter_rule_profile_path=_short_odds_rule_profile_path(tmp_path),
            dry_run=True,
        ),
    )

    assert result.best_option is not None
    assert "A" in result.best_option.selection.fixture_ids
    summary = cast(
        dict[str, object],
        result.best_option.explanation_json["short_odds_final_answer_adapter"],
    )
    assert summary["status"] == "unchanged"
    assert summary["planner_option_changed"] is False


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    market_type: RecommendationMarketType = "1x2",
    probability: float,
    decimal_odds: float,
    line: float | None = None,
    side: str | None = None,
    upset: float = 0.0,
    data_quality_score: float = 90.0,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type=market_type,
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        data_quality_score=data_quality_score,
        model_confidence_score=0.88,
        calibration_score=0.84,
        upset_protection_score=upset,
        odds_stability_score=0.80,
        line=line,
        side=side,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=100 + ord(fixture_id[0]),
        prediction_time_utc=_dt(2026, 5, 1, 10),
        kickoff_time_utc=_dt(2026, 5, 2, 20),
        metadata_json={"competition_id": "EPL"},
    )


def _short_odds_adapter_candidates() -> list[RecommendationCandidate]:
    return [
        _candidate(
            "A",
            "home_win",
            probability=0.62,
            decimal_odds=1.12,
            data_quality_score=100.0,
        ),
        _candidate("B", "away_win", probability=0.72, decimal_odds=1.40),
        _candidate(
            "C",
            "home_win",
            probability=0.611,
            decimal_odds=1.18,
            data_quality_score=50.0,
        ),
        _candidate("D", "draw", probability=0.30, decimal_odds=3.20),
    ]


def _dynamic_mixed_market_candidates() -> list[RecommendationCandidate]:
    return [
        _candidate(
            "A",
            "home_win",
            probability=0.66,
            decimal_odds=1.80,
            data_quality_score=98.0,
        ),
        _candidate(
            "A",
            "draw",
            probability=0.24,
            decimal_odds=4.20,
            data_quality_score=98.0,
        ),
        _candidate(
            "B",
            "handicap_home_win",
            market_type="cn_handicap_1x2",
            probability=0.65,
            decimal_odds=1.82,
            line=-1.0,
            data_quality_score=98.0,
        ),
        _candidate(
            "B",
            "handicap_draw",
            market_type="cn_handicap_1x2",
            probability=0.20,
            decimal_odds=4.80,
            line=-1.0,
            data_quality_score=98.0,
        ),
        _candidate(
            "C",
            "away_win",
            probability=0.64,
            decimal_odds=1.85,
            data_quality_score=98.0,
        ),
        _candidate(
            "D",
            "handicap_away_win",
            market_type="european_handicap_1x2",
            probability=0.63,
            decimal_odds=1.88,
            line=1.0,
            data_quality_score=98.0,
        ),
        _candidate(
            "E",
            "home_win",
            probability=0.62,
            decimal_odds=1.90,
            data_quality_score=98.0,
        ),
        _candidate(
            "F",
            "handicap_home_win",
            market_type="cn_handicap_1x2",
            probability=0.61,
            decimal_odds=1.92,
            line=1.0,
            data_quality_score=98.0,
        ),
        _candidate(
            "G",
            "away_win",
            probability=0.60,
            decimal_odds=1.95,
            data_quality_score=98.0,
        ),
        _candidate(
            "H",
            "handicap_draw",
            market_type="european_handicap_1x2",
            probability=0.59,
            decimal_odds=2.00,
            line=0.0,
            data_quality_score=98.0,
        ),
        _candidate(
            "I",
            "1-0",
            market_type="correct_score",
            probability=0.32,
            decimal_odds=4.00,
            data_quality_score=98.0,
        ),
    ]


def _short_odds_rule_profile_path(tmp_path: Path) -> Path:
    path = tmp_path / "short_odds_rule_profile.json"
    path.write_text(
        f"{dumps(_short_odds_rule_profile(), indent=2)}\n",
        encoding="utf-8",
    )
    return path


def _short_odds_rule_profile() -> dict[str, object]:
    return {
        "profile_version": "global-planner-short-odds-adapter-test",
        "short_odds_replacement_rules": [
            {
                "rule_id": "short_odds_final_answer_replacement_v1",
                "profile_id": "max_short_odds_within_deficit_v1",
                "proposed_production_enabled": True,
                "production_recommendation_changed": False,
                "allowed_competition_ids": ["EPL"],
                "excluded_competition_ids": ["ESP_LA_LIGA"],
                "selection_rule": "highest_candidate_hit_probability",
                "constraints_json": {
                    "selection_rule": "highest_candidate_hit_probability",
                    "max_replacements_per_final_answer": 1,
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                    "min_average_hit_probability_delta_vs_original": -0.02,
                    "min_candidate_hit_probability_delta_vs_original": -0.025,
                    "max_harm_count_vs_original": 0,
                    "max_final_hit_harm_count_vs_original": 0,
                    "max_profit_loss_harm_count_vs_original": 0,
                },
            }
        ],
    }


def _candidate_row(index: int, candidate: RecommendationCandidate) -> DatabaseRow:
    return {
        "prediction_snapshot_id": candidate.prediction_snapshot_id,
        "fixture_id": candidate.fixture_id,
        "prediction_time_utc": candidate.prediction_time_utc,
        "model_version": candidate.model_version,
        "data_quality_score": candidate.data_quality_score,
        "competition_id": "EPL",
        "kickoff_time_utc": candidate.kickoff_time_utc,
        "market_prediction_id": index,
        "market_type": candidate.market_type,
        "line": candidate.line,
        "side": candidate.side,
        "outcome": candidate.outcome,
        "probability": candidate.probability,
        "decimal_odds": candidate.decimal_odds,
        "market_probability": candidate.market_probability,
        "model_edge": candidate.effective_model_edge(),
        "upset_score": candidate.upset_protection_score,
        "favorite_fragility_score": 0.0,
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
