from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenario,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_selection_value_signal_search_generates_specs_from_bucket_report(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "bucket_search.json"
    report_path.write_text(dumps(_bucket_report(), indent=2), encoding="utf-8")

    specs = value_search._candidate_specs(
        value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions(
            bucket_search_report_path=report_path,
            strength_values=(0.02, 0.04),
            max_hit_probability_deficit_values=(None, 0.05),
        )
    )

    assert len(specs) == 4
    assert {spec.strength for spec in specs} == {0.02, 0.04}
    assert {spec.max_hit_probability_deficit for spec in specs} == {None, 0.05}
    assert all(spec.competition_ids == ("ENG_CHAMPIONSHIP",) for spec in specs)
    assert all(spec.outcomes == ("draw",) for spec in specs)
    assert specs[0].min_decimal_odds == pytest.approx(2.5)
    assert specs[0].max_decimal_odds == pytest.approx(3.3333333333333335)
    assert specs[0].source_bucket_key == "ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000"


def test_selection_value_signal_search_generates_movement_conditioned_specs(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "movement_diagnostics.json"
    report_path.write_text(dumps(_movement_report(), indent=2), encoding="utf-8")

    specs = value_search._candidate_specs(
        value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions(
            movement_diagnostics_report_path=report_path,
            movement_score_band=0.002,
        )
    )

    assert len(specs) == 1
    spec = specs[0]
    assert spec.strength == 0.32
    assert spec.outcomes == ("draw",)
    assert spec.score_min == pytest.approx(0.503)
    assert spec.score_max == pytest.approx(0.507)
    assert "movement_clean_positive" in spec.spec_key


def test_selection_value_signal_search_can_probe_configured_movement_classes(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "movement_diagnostics.json"
    movement_report = _movement_report()
    movement_report["candidates"][0]["movement_diagnostics_json"]["records"].append(
        {
            "slice_id": "slice_probability_harm",
            "movement_class": "positive_with_probability_harm",
            "candidate": {
                "selected_candidates": [
                    {
                        "fixture_id": "fixture_probability_harm",
                        "outcome": "draw",
                        "decimal_odds": 3.2,
                        "probability": 0.31,
                        "model_edge": -0.01,
                        "score": 0.512,
                    }
                ]
            },
        }
    )
    report_path.write_text(dumps(movement_report, indent=2), encoding="utf-8")

    specs = value_search._candidate_specs(
        value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions(
            movement_diagnostics_report_path=report_path,
            movement_score_band=0.002,
            movement_conditioned_classes=(
                "clean_positive",
                "positive_with_probability_harm",
            ),
        )
    )

    assert len(specs) == 2
    assert any("slice_probability_harm" in spec.spec_key for spec in specs)
    assert sorted(spec.score_min for spec in specs) == pytest.approx([0.503, 0.51])


def test_selection_value_signal_search_accepts_no_harm_value_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "bucket_search.json"
    report_path.write_text(dumps(_bucket_report(), indent=2), encoding="utf-8")
    monkeypatch.setattr(
        value_search,
        "run_historical_recommendation_backtest_suite",
        _fake_backtest_suite,
    )

    report = value_search.build_historical_final_answer_selection_value_signal_search_report(
        [_slice()],
        options=value_search.HistoricalFinalAnswerSelectionValueSignalSearchOptions(
            bucket_search_report_path=report_path,
            strength_values=(0.02, 0.04, 0.08),
            min_final_answer_count=1,
            include_movement_diagnostics=True,
            movement_diagnostics_limit=2,
        ),
    )

    assert report.status == "generated"
    assert report.candidate_count == 3
    assert report.accepted_count == 1
    assert report.rejected_count == 2
    assert report.best_candidate is not None
    assert report.best_candidate.spec.strength == 0.04
    assert report.best_candidate.affected_leg_count == 1
    assert report.best_candidate.guard_blocked_option_count == 0
    assert report.best_candidate.movement_count == 1
    assert report.best_candidate.positive_movement_count == 1
    assert report.best_candidate.harmful_movement_count == 0
    assert report.best_candidate.probability_quality_harm_movement_count == 0
    assert report.best_candidate.movement_diagnostics_json["record_count"] == 1
    records = report.best_candidate.movement_diagnostics_json["records"]
    assert isinstance(records, list)
    assert records[0]["movement_class"] == "clean_positive"
    assert records[0]["candidate"]["selected_candidates"] == []
    assert report.best_candidate.final_answer_hit_delta_count == 1
    assert report.best_candidate.brier_score_delta == pytest.approx(-0.01)
    rejected_reasons = {
        reason
        for candidate in report.candidates
        if candidate.decision == "rejected"
        for reason in candidate.decision_reasons
    }
    assert "changed_final_answer_count:below_threshold" in rejected_reasons
    assert "brier_score_delta:above_threshold" in rejected_reasons


def test_selection_value_signal_search_cli_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "bucket_search.json"
    slice_path = tmp_path / "slice.json"
    output_path = tmp_path / "selection_value_search.json"
    report_path.write_text(dumps(_bucket_report(), indent=2), encoding="utf-8")
    slice_path.write_text(f"{_slice().model_dump_json(indent=2)}\n", encoding="utf-8")
    monkeypatch.setattr(
        value_search,
        "run_historical_recommendation_backtest_suite",
        _fake_backtest_suite,
    )

    args = value_search._parse_args(
        [
            str(slice_path),
            "--bucket-search-report",
            str(report_path),
            "--movement-diagnostics-report",
            str(report_path),
            "--output-path",
            str(output_path),
            "--strength-values",
            "0.04",
            "--pass-types",
            "1x1,3x1",
            "--modes",
            "single",
            "--unit-stake",
            "2",
            "--max-budget",
            "20",
            "--min-probability",
            "0.15",
            "--max-candidates-per-fixture",
            "3",
            "--final-answer-scenario-variant-count",
            "3",
            "--derive-market-context-signals",
            "--max-hit-probability-deficit-values",
            "0.02,0.05",
            "--min-option-roi-values",
            "none,0.0",
            "--max-option-risk-score-values",
            "0.8",
            "--include-movement-diagnostics",
            "--movement-diagnostics-limit",
            "5",
            "--movement-score-band",
            "0.002",
            "--max-movement-conditioned-specs",
            "3",
            "--movement-conditioned-classes",
            "clean_positive,positive_with_probability_harm",
            "--min-final-answer-count",
            "1",
            "--no-fail-process",
        ]
    )
    options = value_search._options_from_args(args)

    assert options.strength_values == (0.04,)
    assert options.backtest_options.pass_types == ("1x1", "3x1")
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.max_hit_probability_deficit_values == (0.02, 0.05)
    assert options.min_option_roi_values == (None, 0.0)
    assert options.max_option_risk_score_values == (0.8,)
    assert options.include_movement_diagnostics is True
    assert options.movement_diagnostics_limit == 5
    assert options.movement_diagnostics_report_path == report_path
    assert options.movement_score_band == pytest.approx(0.002)
    assert options.max_movement_conditioned_specs == 3
    assert options.movement_conditioned_classes == (
        "clean_positive",
        "positive_with_probability_harm",
    )

    value_search.main(
        [
            str(slice_path),
            "--bucket-search-report",
            str(report_path),
            "--output-path",
            str(output_path),
            "--strength-values",
            "0.04",
            "--include-movement-diagnostics",
            "--min-final-answer-count",
            "1",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "generated"
    assert payload["accepted_count"] == 1
    assert payload["best_candidate"]["spec"]["strength"] == 0.04
    assert payload["best_candidate"]["movement_count"] == 1
    assert payload["best_candidate"]["movement_diagnostics_json"]["record_count"] == 1


def _fake_backtest_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalRecommendationBacktestOptions | None = None,
    baseline_optimizer_profile: str = "heuristic",
    candidate_optimizer_profile: str = "solver",
) -> HistoricalRecommendationBacktestSuiteResult:
    del historical_slices
    resolved_options = options or HistoricalRecommendationBacktestOptions()
    baseline_result = _result(
        backtest_key="backtest:baseline",
        fixture_id="fixture_a",
        outcome="home_win",
        hit=False,
        profit_loss=-2.0,
        brier=0.20,
        log_loss=0.60,
        calibration_error=0.30,
    )
    if not resolved_options.final_answer_selection_value_signal:
        candidate_result = baseline_result
    elif resolved_options.final_answer_selection_value_signal_strength == 0.04:
        candidate_result = _result(
            backtest_key="backtest:candidate:accepted",
            fixture_id="fixture_a",
            outcome="draw",
            hit=True,
            profit_loss=4.0,
            brier=0.19,
            log_loss=0.58,
            calibration_error=0.28,
        )
    elif resolved_options.final_answer_selection_value_signal_strength == 0.08:
        candidate_result = _result(
            backtest_key="backtest:candidate:quality_regression",
            fixture_id="fixture_a",
            outcome="draw",
            hit=True,
            profit_loss=4.0,
            brier=0.22,
            log_loss=0.65,
            calibration_error=0.35,
        )
    else:
        candidate_result = baseline_result
    is_candidate = resolved_options.final_answer_selection_value_signal
    summary = {
        "candidate_final_hit_sample_size": 1,
        "candidate_final_hit_count": int(candidate_result.final_hit_count),
        "candidate_final_hit_rate": candidate_result.final_hit_rate,
        "candidate_roi": candidate_result.roi,
        "candidate_profit_loss": candidate_result.profit_loss,
        "candidate_brier_score": candidate_result.brier_score,
        "candidate_log_loss": candidate_result.log_loss,
        "candidate_mean_calibration_error": candidate_result.mean_calibration_error,
        "candidate_final_answer_selection_value_signal_affected_leg_count": (
            1 if is_candidate else 0
        ),
    }
    comparison = HistoricalRecommendationBacktestComparisonResult(
        comparison_key=f"comparison:{candidate_result.backtest_key}",
        slice_id="slice_test",
        baseline_optimizer_profile="heuristic",
        candidate_optimizer_profile="solver",
        status="improved" if candidate_result.final_hit_count else "unchanged",
        baseline=baseline_result,
        candidate=candidate_result,
    )
    return HistoricalRecommendationBacktestSuiteResult(
        suite_key=f"suite:{candidate_result.backtest_key}",
        status="improved" if candidate_result.final_hit_count else "unchanged",
        slice_count=1,
        comparison_count=1,
        baseline_optimizer_profile=baseline_optimizer_profile,  # type: ignore[arg-type]
        candidate_optimizer_profile=candidate_optimizer_profile,  # type: ignore[arg-type]
        comparisons=[comparison],
        summary_json=summary,
    )


def _result(
    *,
    backtest_key: str,
    fixture_id: str,
    outcome: str,
    hit: bool,
    profit_loss: float,
    brier: float,
    log_loss: float,
    calibration_error: float,
) -> HistoricalRecommendationBacktestResult:
    actual_return = max(0.0, profit_loss + 2.0)
    roi = profit_loss / 2.0
    final_answer = HistoricalRecommendationScenarioResult(
        scenario=HistoricalRecommendationScenario(
            scenario_key="1x1:single",
            pass_type="1x1",
            mode="single",
        ),
        status="completed",
        selected_fixture_ids=[fixture_id],
        selected_outcomes={fixture_id: [outcome]},
        total_stake=2.0,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=roi,
        expected_hit_probability=0.4,
        actual_hit=hit,
        brier_score=brier,
        log_loss=log_loss,
        calibration_error=calibration_error,
    )
    return HistoricalRecommendationBacktestResult(
        backtest_key=backtest_key,
        slice_id="slice_test",
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixture_count=1,
        candidate_count=3,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=final_answer,
        scenarios=[final_answer],
        final_hit_sample_size=1,
        final_hit_count=int(hit),
        final_hit_rate=1.0 if hit else 0.0,
        total_stake=2.0,
        actual_return=actual_return,
        profit_loss=profit_loss,
        roi=roi,
        mean_calibration_error=calibration_error,
        brier_score=brier,
        log_loss=log_loss,
        upset_opportunity_count=0,
        upset_capture_count=0,
        upset_capture_rate=None,
    )


def _bucket_report() -> dict[str, object]:
    return {
        "report_key": "bucket-search:test",
        "candidates": [
            {
                "candidate_key": "bucket-candidate:positive",
                "rank": 1,
                "final_answer_hit_delta_count": 1,
                "profit_loss_delta": 6.0,
                "spec": {
                    "bucket_keys": [
                        "ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000",
                    ]
                },
            },
            {
                "candidate_key": "bucket-candidate:no_movement",
                "rank": 2,
                "final_answer_hit_delta_count": 0,
                "profit_loss_delta": 0.0,
                "spec": {
                    "bucket_keys": [
                        "ENG_CHAMPIONSHIP:1x2:draw:0.2000-0.3000",
                    ]
                },
            },
        ],
    }


def _movement_report() -> dict[str, object]:
    return {
        "report_key": "movement-diagnostics:test",
        "candidates": [
            {
                "candidate_key": "candidate:movement",
                "spec": {
                    "spec_key": "base:movement",
                    "competition_ids": ["ENG_CHAMPIONSHIP"],
                    "outcomes": ["draw"],
                    "probability_min": 0.0,
                    "probability_max": 1.0,
                    "min_decimal_odds": 2.5,
                    "max_decimal_odds": 3.3333333333333335,
                    "max_model_edge": None,
                    "score_min": 0.0,
                    "score_max": 1.0,
                    "max_hit_probability_deficit": 0.02,
                    "min_option_roi": None,
                    "max_option_risk_score": None,
                    "strength": 0.32,
                    "source_bucket_key": (
                        "ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000"
                    ),
                    "source_bucket_search_candidate_key": "source:candidate",
                },
                "movement_diagnostics_json": {
                    "records": [
                        {
                            "movement_class": "harmful",
                            "slice_id": "slice_harm",
                            "candidate": {
                                "selected_candidates": [
                                    {
                                        "fixture_id": "fixture_harm",
                                        "outcome": "draw",
                                        "probability": 0.29,
                                        "decimal_odds": 3.20,
                                        "model_edge": -0.02,
                                        "score": 0.500,
                                    }
                                ]
                            },
                        },
                        {
                            "movement_class": "clean_positive",
                            "slice_id": "slice_clean",
                            "candidate": {
                                "selected_candidates": [
                                    {
                                        "fixture_id": "fixture_clean",
                                        "outcome": "draw",
                                        "probability": 0.28,
                                        "decimal_odds": 3.30,
                                        "model_edge": -0.01,
                                        "score": 0.505,
                                    },
                                    {
                                        "fixture_id": "fixture_outside",
                                        "outcome": "draw",
                                        "probability": 0.28,
                                        "decimal_odds": 3.50,
                                        "model_edge": -0.01,
                                        "score": 0.506,
                                    },
                                ]
                            },
                        },
                    ]
                },
            }
        ],
    }


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="slice_test",
            name="Selection value signal search test slice",
            competition_id="ENG_CHAMPIONSHIP",
            season="2021-2022",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=datetime(2025, 5, 1, 12, tzinfo=UTC),
        fixtures=[
            HistoricalFixture(
                fixture_id="fixture_a",
                competition_id="ENG_CHAMPIONSHIP",
                kickoff_time_utc=datetime(2025, 5, 2, 18, tzinfo=UTC),
                home_team_name="Alpha",
                away_team_name="Bravo",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=datetime(2025, 5, 1, 10, tzinfo=UTC),
                model_version="poisson-v3.1-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.45,
                        decimal_odds=2.10,
                        market_probability=1 / 2.10,
                    ),
                    HistoricalMarketPrediction(
                        outcome="draw",
                        probability=0.30,
                        decimal_odds=3.20,
                        market_probability=1 / 3.20,
                    ),
                    HistoricalMarketPrediction(
                        outcome="away_win",
                        probability=0.25,
                        decimal_odds=3.80,
                        market_probability=1 / 3.80,
                    ),
                ],
            )
        ],
    )
