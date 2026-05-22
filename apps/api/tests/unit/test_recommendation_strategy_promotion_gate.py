from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.recommendation_strategy_promotion_gate import (
    RecommendationStrategyPromotionGateOptions,
    _options_from_args,
    _parse_args,
    build_recommendation_strategy_promotion_gate_report,
    load_recommendation_strategy_promotion_gate_report,
    main,
)
from nutmeg.recommendations.replacement_probability_preserving_promotion_review import (
    HistoricalReplacementProbabilityPreservingPromotionReviewReport,
)


def test_strategy_promotion_gate_is_ready_for_clean_review() -> None:
    report = build_recommendation_strategy_promotion_gate_report(
        [_promotion_review_report()]
    )

    assert report.status == "ready"
    assert report.strategy_gate_ready is True
    assert report.production_recommendation_allowed is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.evidence_count == 1
    assert report.ready_evidence_count == 1
    assert report.selected_candidate_keys == [
        "replacement_probability_preserving_candidate:test"
    ]
    assert report.total_changed_final_answer_count == 13
    assert report.total_final_answer_hit_delta_count == 4
    assert report.total_harm_count_vs_original == 0
    assert all(check.status == "passed" for check in report.checks)


def test_strategy_promotion_gate_watchlists_review_blockers() -> None:
    review = _promotion_review_report().model_copy(
        update={
            "status": "promotion_review_watchlist",
            "promotion_review_allowed": False,
            "candidate_rule_count": 0,
            "blockers": ["exclude_original_hit_harm_constraint"],
        }
    )

    report = build_recommendation_strategy_promotion_gate_report([review])

    assert report.status == "watchlist"
    assert report.strategy_gate_ready is False
    assert "all_reviews_ready" in report.blockers
    assert "promotion_review_blocker_count" in report.blockers
    assert report.production_recommendation_changed is False


def test_strategy_promotion_gate_blocks_production_change() -> None:
    review = _promotion_review_report().model_copy(
        update={
            "production_recommendation_changed": True,
            "public_response_changed": True,
        }
    )

    report = build_recommendation_strategy_promotion_gate_report([review])

    assert report.status == "blocked"
    assert "no_production_recommendation_change" in report.blockers
    assert "no_public_response_change" in report.blockers


def test_strategy_promotion_gate_options_can_relax_roi_requirement() -> None:
    review = _promotion_review_report().model_copy(update={"roi_delta": None})

    blocked = build_recommendation_strategy_promotion_gate_report([review])
    relaxed = build_recommendation_strategy_promotion_gate_report(
        [review],
        options=RecommendationStrategyPromotionGateOptions(
            min_minimum_roi_delta=None
        ),
    )

    assert blocked.status == "watchlist"
    assert "minimum_roi_delta" in blocked.blockers
    assert relaxed.status == "ready"


def test_strategy_promotion_gate_cli_options_and_main(tmp_path: Path) -> None:
    review_path = tmp_path / "promotion_review.json"
    report_path = tmp_path / "strategy_gate.json"
    review_path.write_text(
        f"{_promotion_review_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--promotion-review-report",
            str(review_path),
            "--report-output-path",
            str(report_path),
            "--gate-id",
            "unit-gate",
            "--strategy-key",
            "unit-strategy",
            "--min-total-final-answer-count",
            "99",
            "--min-total-changed-final-answer-count",
            "13",
            "--min-minimum-active-surface-count",
            "8",
            "--min-minimum-active-competition-fold-count",
            "5",
            "--min-minimum-active-season-fold-count",
            "5",
            "--min-minimum-active-rolling-fold-count",
            "13",
            "--allow-missing-roi-delta",
        ]
    )
    options = _options_from_args(args)

    assert options.gate_id == "unit-gate"
    assert options.strategy_key == "unit-strategy"
    assert options.min_total_final_answer_count == 99
    assert options.min_minimum_roi_delta is None

    main(
        [
            "--promotion-review-report",
            str(review_path),
            "--report-output-path",
            str(report_path),
            "--gate-id",
            "unit-gate",
            "--strategy-key",
            "unit-strategy",
            "--min-total-final-answer-count",
            "99",
            "--min-total-changed-final-answer-count",
            "13",
            "--min-minimum-active-surface-count",
            "8",
            "--min-minimum-active-competition-fold-count",
            "5",
            "--min-minimum-active-season-fold-count",
            "5",
            "--min-minimum-active-rolling-fold-count",
            "13",
        ]
    )

    saved = load_recommendation_strategy_promotion_gate_report(report_path)
    assert saved.status == "ready"
    assert saved.gate_id == "unit-gate"


def _promotion_review_report() -> HistoricalReplacementProbabilityPreservingPromotionReviewReport:
    return HistoricalReplacementProbabilityPreservingPromotionReviewReport(
        report_key="historical_replacement_probability_preserving_promotion_review:test",
        status="promotion_review_ready",
        promotion_review_allowed=True,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        source_runtime_dry_run_report_key=(
            "historical_replacement_probability_preserving_runtime_dry_run:test"
        ),
        source_grid_report_key="grid:test",
        source_surface_replay_report_key="surface:test",
        source_admission_report_key="admission:test",
        generated_runtime_shadow_replay_report_key="runtime-shadow:test",
        selected_candidate_key="replacement_probability_preserving_candidate:test",
        reviewed_profile_version="unit-review-profile",
        candidate_rule_count=1,
        allowed_competition_ids=[
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        final_answer_count=99,
        changed_final_answer_count=13,
        final_answer_hit_delta_count=4,
        profit_loss_delta=15.74,
        roi_delta=0.0403,
        harm_count_vs_original=0,
        final_hit_harm_count_vs_original=0,
        profit_loss_harm_count_vs_original=0,
        average_hit_probability_delta_vs_original=-0.011,
        active_surface_count=8,
        failed_surface_count=0,
        active_competition_fold_count=5,
        active_season_fold_count=5,
        active_rolling_fold_count=13,
        failed_fold_count=0,
        checks=[],
        blockers=[],
        review_profile_json={"dry_run_only": True},
        warnings=[],
        summary_json={},
    )
