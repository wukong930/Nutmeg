from __future__ import annotations

import nutmeg.accuracy.historical_prematch_feature_parameter_learning as learning_module
from nutmeg.accuracy import (
    HistoricalPrematchFeatureParameterLearningOptions,
    build_historical_prematch_feature_parameter_learning_report,
)
from nutmeg.accuracy.historical_prematch_feature_ablation import (
    HistoricalPrematchFeatureAblationComparisonGroup,
    HistoricalPrematchFeatureAblationMetricSet,
    HistoricalPrematchFeatureAblationOptions,
    HistoricalPrematchFeatureAblationReport,
)
from nutmeg.accuracy.historical_prematch_feature_parameter_learning import (
    HistoricalPrematchFeatureParameterCandidate,
    HistoricalPrematchFeatureParameterCandidateTrainingResult,
    _options_from_args,
    _parse_args,
    _select_candidate,
)
from nutmeg.recommendations import (
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    build_enriched_historical_feature_sample,
)


def test_prematch_feature_parameter_learning_selects_holdout_candidate() -> None:
    slices = [
        _season_slice("2021"),
        _season_slice("2022"),
        _season_slice("2023"),
    ]

    report = build_historical_prematch_feature_parameter_learning_report(
        slices,
        options=HistoricalPrematchFeatureParameterLearningOptions(
            holdout_season_count=1,
            min_training_season_count=2,
            min_training_sample_size=1,
            min_validation_sample_size=1,
            max_probability_shifts=(0.0, 0.08),
            odds_movement_weights=(0.0, 0.35),
            tracked_fragility_weights=(0.0,),
            lineup_strength_weights=(0.0,),
            draw_signal_weights=(0.0,),
        ),
    )

    result = report.competitions[0]

    assert report.status == "generated"
    assert report.learned_competition_count == 1
    assert report.candidate_count == 4
    assert report.validation_count == 6
    assert result.status == "learned"
    assert result.training_seasons == ["2021", "2022"]
    assert result.validation_seasons == ["2023"]
    assert result.selected_candidate is not None
    assert result.selected_training_result is not None
    assert result.selected_validation is not None
    assert result.selected_validation.validation_count == 6
    assert report.overall_validation_candidate is not None
    assert report.overall_validation_baseline is not None


def test_prematch_feature_parameter_learning_skips_without_training_seasons() -> None:
    report = build_historical_prematch_feature_parameter_learning_report(
        [_season_slice("2023")],
        options=HistoricalPrematchFeatureParameterLearningOptions(
            min_training_season_count=2,
            min_training_sample_size=1,
            min_validation_sample_size=1,
        ),
    )

    assert report.learned_competition_count == 0
    assert report.competitions[0].status == "skipped"
    assert "insufficient_training_seasons" in report.warnings[0]


def test_prematch_feature_parameter_learning_blocks_training_ece_regression() -> None:
    safe_baseline = _training_result(
        candidate_key="shift_0_0_odds_0_0_fragility_0_0_lineup_0_0_draw_0_0",
        max_probability_shift=0.0,
        brier_delta=0.0,
        expected_calibration_error_delta=0.0,
    )
    brier_better_but_uncalibrated = _training_result(
        candidate_key="shift_0_08_odds_0_35_fragility_0_0_lineup_0_0_draw_0_0",
        max_probability_shift=0.08,
        brier_delta=-0.02,
        expected_calibration_error_delta=0.01,
    )

    selected = _select_candidate(
        [brier_better_but_uncalibrated, safe_baseline],
        options=HistoricalPrematchFeatureParameterLearningOptions(
            min_training_sample_size=1,
            max_training_expected_calibration_error_delta=0.0,
        ),
    )

    assert selected == safe_baseline


def test_prematch_feature_parameter_learning_allows_tiny_ece_rounding_noise() -> None:
    nearly_zero = _training_result(
        candidate_key="shift_0_0_odds_0_0_fragility_0_0_lineup_0_0_draw_0_0",
        max_probability_shift=0.0,
        brier_delta=0.0,
        expected_calibration_error_delta=5e-13,
    )

    selected = _select_candidate(
        [nearly_zero],
        options=HistoricalPrematchFeatureParameterLearningOptions(
            min_training_sample_size=1,
            max_training_expected_calibration_error_delta=0.0,
        ),
    )

    assert selected == nearly_zero


def test_prematch_feature_parameter_learning_skips_when_all_candidates_regress_ece() -> None:
    selected = _select_candidate(
        [
            _training_result(
                candidate_key="shift_0_08_odds_0_35_fragility_0_0_lineup_0_0_draw_0_0",
                max_probability_shift=0.08,
                brier_delta=-0.02,
                expected_calibration_error_delta=0.01,
            )
        ],
        options=HistoricalPrematchFeatureParameterLearningOptions(
            min_training_sample_size=1,
            max_training_expected_calibration_error_delta=0.0,
        ),
    )

    assert selected is None


def test_prematch_feature_parameter_learning_falls_back_to_noop_on_validation_ece(
    monkeypatch,
) -> None:
    def fake_ablation_report(
        slices,
        *,
        options: HistoricalPrematchFeatureAblationOptions,
    ) -> HistoricalPrematchFeatureAblationReport:
        noop = options.max_probability_shift == 0.0
        validation = len(slices) == 1
        if noop:
            deltas = {
                "brier_score_delta": 0.0,
                "log_loss_delta": 0.0,
                "expected_calibration_error_delta": 0.0,
            }
        elif validation:
            deltas = {
                "brier_score_delta": -0.02,
                "log_loss_delta": -0.02,
                "expected_calibration_error_delta": 0.02,
            }
        else:
            deltas = {
                "brier_score_delta": -0.02,
                "log_loss_delta": -0.02,
                "expected_calibration_error_delta": -0.01,
            }
        return _ablation_report(deltas)

    monkeypatch.setattr(
        learning_module,
        "build_historical_prematch_feature_ablation_report",
        fake_ablation_report,
    )

    result = learning_module._competition_learning_result(
        "TEST_COMPETITION",
        slices=[_season_slice("2021"), _season_slice("2022"), _season_slice("2023")],
        candidates=[
            HistoricalPrematchFeatureParameterCandidate(
                candidate_key="shift_0_0_odds_0_0_fragility_0_0_lineup_0_0_draw_0_0",
                max_probability_shift=0.0,
                odds_movement_weight=0.0,
                tracked_fragility_weight=0.0,
                lineup_strength_weight=0.0,
                draw_signal_weight=0.0,
            ),
            HistoricalPrematchFeatureParameterCandidate(
                candidate_key="shift_0_08_odds_0_35_fragility_0_0_lineup_0_0_draw_0_0",
                max_probability_shift=0.08,
                odds_movement_weight=0.35,
                tracked_fragility_weight=0.0,
                lineup_strength_weight=0.0,
                draw_signal_weight=0.0,
            ),
        ],
        options=HistoricalPrematchFeatureParameterLearningOptions(
            min_training_season_count=2,
            min_training_sample_size=1,
            min_validation_sample_size=1,
            max_training_expected_calibration_error_delta=0.0,
            max_validation_expected_calibration_error_delta=0.0,
        ),
    )

    assert result.selected_candidate is not None
    assert result.selected_candidate.max_probability_shift == 0.0
    assert result.selected_validation is not None
    assert result.selected_validation.deltas_json["expected_calibration_error_delta"] == 0.0
    assert result.status == "learned_with_warnings"
    assert "validation_ece_regression_fallback_to_noop" in result.warnings[0]


def test_prematch_feature_parameter_learning_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--output-path",
            "tmp/prematch_feature_parameter_learning.json",
            "--holdout-season-count",
            "2",
            "--min-training-season-count",
            "3",
            "--min-training-sample-size",
            "40",
            "--min-validation-sample-size",
            "20",
            "--selection-metric",
            "log_loss_delta",
            "--max-training-expected-calibration-error-delta",
            "0.02",
            "--max-validation-expected-calibration-error-delta",
            "0.03",
            "--min-feature-data-quality-score",
            "82",
            "--max-probability-shifts",
            "0,0.04",
            "--odds-movement-weights",
            "0.2,0.4",
            "--tracked-fragility-weights",
            "0,0.8",
            "--lineup-strength-weights",
            "0,0.3",
            "--draw-signal-weights",
            "0,0.2",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "3",
            "--prediction-sample-limit",
            "2",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
        ]
    )

    options = _options_from_args(args)

    assert options.holdout_season_count == 2
    assert options.min_training_season_count == 3
    assert options.min_training_sample_size == 40
    assert options.min_validation_sample_size == 20
    assert options.selection_metric == "log_loss_delta"
    assert options.max_training_expected_calibration_error_delta == 0.02
    assert options.max_validation_expected_calibration_error_delta == 0.03
    assert options.min_feature_data_quality_score == 82
    assert options.max_probability_shifts == (0.0, 0.04)
    assert options.odds_movement_weights == (0.2, 0.4)
    assert options.tracked_fragility_weights == (0.0, 0.8)
    assert options.lineup_strength_weights == (0.0, 0.3)
    assert options.draw_signal_weights == (0.0, 0.2)
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 3
    assert options.prediction_sample_limit == 2
    assert options.require_feature_not_after_prediction is False
    assert options.require_feature_before_kickoff is False


def _season_slice(season: str) -> HistoricalRecommendationSlice:
    base_slice = build_enriched_historical_feature_sample().historical_slice
    metadata = HistoricalRecommendationSliceMetadata(
        slice_id=f"prematch_feature_learning_{season}",
        name=f"Prematch feature learning {season}",
        competition_id=base_slice.metadata.competition_id,
        season=season,
        result_source=base_slice.metadata.result_source,
        odds_source=base_slice.metadata.odds_source,
        prediction_source=base_slice.metadata.prediction_source,
        source_urls=base_slice.metadata.source_urls,
        notes=base_slice.metadata.notes,
    )
    return base_slice.model_copy(
        update={
            "metadata": metadata,
            "fixtures": [
                fixture.model_copy(
                    update={"fixture_id": f"{season}_{fixture.fixture_id}"}
                )
                for fixture in base_slice.fixtures
            ],
        }
    )


def _training_result(
    *,
    candidate_key: str,
    max_probability_shift: float,
    brier_delta: float,
    expected_calibration_error_delta: float,
) -> HistoricalPrematchFeatureParameterCandidateTrainingResult:
    candidate = HistoricalPrematchFeatureParameterCandidate(
        candidate_key=candidate_key,
        max_probability_shift=max_probability_shift,
        odds_movement_weight=0.0,
        tracked_fragility_weight=0.0,
        lineup_strength_weight=0.0,
        draw_signal_weight=0.0,
    )
    metric_set = HistoricalPrematchFeatureAblationMetricSet(
        sample_size=10,
        hit_count=5,
        hit_rate=0.5,
        brier_score=0.25,
        log_loss=0.70,
        expected_calibration_error=0.05,
    )
    return HistoricalPrematchFeatureParameterCandidateTrainingResult(
        candidate=candidate,
        training_report_key=f"training:{candidate_key}",
        training_sample_size=10,
        training_candidate=metric_set,
        training_baseline=metric_set,
        training_deltas_json={
            "brier_score_delta": brier_delta,
            "log_loss_delta": brier_delta,
            "expected_calibration_error_delta": expected_calibration_error_delta,
        },
        selection_metric_value=brier_delta,
    )


def _ablation_report(
    deltas_json: dict[str, object],
) -> HistoricalPrematchFeatureAblationReport:
    baseline = HistoricalPrematchFeatureAblationMetricSet(
        sample_size=10,
        hit_count=5,
        hit_rate=0.5,
        brier_score=0.25,
        log_loss=0.70,
        expected_calibration_error=0.05,
    )
    candidate = baseline.model_copy()
    group = HistoricalPrematchFeatureAblationComparisonGroup(
        group_key="overall",
        group_type="overall",
        label="Overall",
        validation_count=10,
        skipped_count=0,
        candidate=candidate,
        baseline=baseline,
        deltas_json=deltas_json,
    )
    return HistoricalPrematchFeatureAblationReport(
        report_key="prematch_feature_ablation:test",
        status="generated",
        slice_count=1,
        fixture_count=10,
        validation_count=10,
        skipped_count=0,
        overall=group,
    )
