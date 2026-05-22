from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_market_movement_risk_filter_scope_refinement import (
    HistoricalMarketMovementRiskFilterScopeRefinementReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_sample_expansion import (
    HistoricalMarketMovementRuntimeActivationSampleExpansionReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_segment_expansion import (
    build_historical_market_movement_runtime_activation_segment_expansion_report,
    main,
)


def test_segment_expansion_builds_shadow_replay_candidate_profile() -> None:
    report = build_historical_market_movement_runtime_activation_segment_expansion_report(
        _sample_expansion_report(),
        scope_refinement=_scope_refinement_report(),
    )

    assert report.status == "watchlist"
    assert report.passed is True
    assert report.runtime_replay_expansion_ready is True
    assert report.production_promotion_ready is False
    assert report.selected_segment_group_keys == [
        "strongest_movement_direction:probability_shortened",
        "opening_probability_band:0.25:0.45",
    ]
    assert report.total_adjusted_fixture_count == 694
    assert report.total_competition_count == 5
    assert report.profile_json["default_profile_written"] is False
    rules = report.profile_json["rules"]
    assert isinstance(rules, list)
    assert [rule["segment_group_keys"] for rule in rules] == [
        ["strongest_movement_direction:probability_shortened"],
        ["opening_probability_band:0.25:0.45"],
    ]
    assert report.watchlist == ["sample_expansion_promotion_ready_for_production"]


def test_segment_expansion_blocks_without_selected_candidates() -> None:
    report = build_historical_market_movement_runtime_activation_segment_expansion_report(
        _sample_expansion_report(),
        scope_refinement=_scope_refinement_report(only_existing=True),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.passed is False
    assert report.runtime_replay_expansion_ready is False
    assert "selected_candidate_count" in failed_checks
    assert "total_adjusted_fixture_count" in failed_checks


def test_segment_expansion_cli_writes_report_and_profile(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample_expansion.json"
    scope_path = tmp_path / "scope_refinement.json"
    output_path = tmp_path / "segment_expansion.json"
    profile_path = tmp_path / "segment_expansion_profile.json"
    sample_path.write_text(
        f"{_sample_expansion_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    scope_path.write_text(
        f"{_scope_refinement_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--sample-expansion-report",
            str(sample_path),
            "--scope-refinement-report",
            str(scope_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile = loads(profile_path.read_text(encoding="utf-8"))
    assert payload["runtime_replay_expansion_ready"] is True
    assert payload["production_promotion_ready"] is False
    assert len(profile["rules"]) == 2
    assert profile["production_recommendation_allowed"] is False


def _sample_expansion_report() -> (
    HistoricalMarketMovementRuntimeActivationSampleExpansionReport
):
    return HistoricalMarketMovementRuntimeActivationSampleExpansionReport.model_validate(
        {
            "report_key": (
                "historical_market_movement_runtime_activation_sample_expansion:test"
            ),
            "status": "shadow_only",
            "passed": True,
            "promotion_ready": False,
            "expansion_id": "sample-expansion-test",
            "source_activation_report_key": (
                "historical_market_movement_runtime_activation:test"
            ),
            "activation_status": "staged_activation_ready",
            "activation_ready": True,
            "selected_segment_group_keys": ["competition_outcome:LA_LIGA:home_win"],
            "selected_segment_competition_ids": ["LA_LIGA"],
            "selected_segment_competition_count": 1,
            "selected_segment_competition_season_count": 5,
            "readiness_report_count": 1,
            "coverage_audit_report_count": 1,
            "ready_source_count": 1,
            "supplemental_source_count": 1,
            "ready_fixture_count": 600,
            "ready_slice_count": 25,
            "ready_competition_count": 5,
            "ready_season_count": 5,
            "ready_competition_season_count": 25,
            "supplemental_fixture_count": 2520,
            "supplemental_slice_count": 210,
            "combined_fixture_count": 3120,
            "combined_slice_count": 235,
            "combined_competition_count": 12,
            "combined_season_count": 5,
            "combined_competition_season_count": 60,
            "adjusted_fixture_count": 120,
            "adjusted_prediction_count": 360,
            "adjusted_to_combined_fixture_ratio": 120 / 3120,
            "default_profile_written": False,
            "default_recommendation_path_changed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "sources": [],
            "blockers": [],
            "watchlist": ["selected_segment_count_for_promotion"],
            "warnings": [],
            "summary_json": {},
        }
    )


def _scope_refinement_report(
    *,
    only_existing: bool = False,
) -> HistoricalMarketMovementRiskFilterScopeRefinementReport:
    scopes = (
        [_scope("competition_outcome:LA_LIGA:home_win", adjusted_fixture_count=432)]
        if only_existing
        else [
            _scope(
                "strongest_movement_direction:probability_shortened",
                adjusted_fixture_count=550,
                competition_ids=["BUNDESLIGA", "EPL", "LA_LIGA", "LIGUE_1", "SERIE_A"],
                brier_delta=-0.002,
                log_loss_delta=-0.005,
            ),
            _scope(
                "opening_probability_band:0.25:0.45",
                adjusted_fixture_count=144,
                competition_ids=["LA_LIGA", "SERIE_A"],
                brier_delta=-0.012,
                log_loss_delta=-0.027,
            ),
            _scope("competition_outcome:LA_LIGA:home_win", adjusted_fixture_count=432),
        ]
    )
    return HistoricalMarketMovementRiskFilterScopeRefinementReport.model_validate(
        {
            "report_key": "historical_market_movement_scope_refinement:test",
            "status": "guarded_scope_required",
            "refinement_id": "scope-refinement-test",
            "rolling_admission_report_key": "rolling-admission:test",
            "rolling_admission_status": "shadow_only",
            "rolling_risk_filter_allowed": False,
            "rolling_shadow_allowed": True,
            "source_failed_fold_count": 0,
            "analyzed_fold_count": 5,
            "scope_candidate_count": len(scopes),
            "stable_scope_count": len(scopes),
            "guarded_scope_count": 0,
            "blocked_scope_count": 0,
            "insufficient_scope_count": 0,
            "blocked_guard_count": 0,
            "best_scope_key": scopes[0]["segment_group_key"],
            "best_scope": scopes[0],
            "scopes": scopes,
            "evaluations": [],
            "blocked_scopes": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _scope(
    segment_group_key: str,
    *,
    adjusted_fixture_count: int,
    competition_ids: list[str] | None = None,
    brier_delta: float = -0.001,
    log_loss_delta: float = -0.002,
) -> dict[str, object]:
    resolved_competition_ids = competition_ids or ["LA_LIGA"]
    return {
        "segment_group_key": segment_group_key,
        "segment_group_type": segment_group_key.split(":", 1)[0],
        "segment_label": segment_group_key,
        "status": "stable_shadow_candidate",
        "recommended_action": "keep_shadow",
        "evaluated_fold_count": 5,
        "accepted_fold_count": 5,
        "rejected_fold_count": 0,
        "failed_scope_count": 0,
        "failed_quality_count": 0,
        "passing_fold_ids": ["overall"],
        "rejected_fold_ids": [],
        "failed_scope_fold_ids": [],
        "source_competition_ids": resolved_competition_ids,
        "source_season_ids": [
            "2020-2021",
            "2021-2022",
            "2022-2023",
            "2023-2024",
            "2024-2025",
        ],
        "total_adjusted_fixture_count": adjusted_fixture_count,
        "total_adjusted_prediction_count": adjusted_fixture_count * 3,
        "best_candidate_id": f"candidate:{segment_group_key}",
        "best_final_hit_rate_delta": 0.0,
        "best_brier_score_delta": brier_delta,
        "best_log_loss_delta": log_loss_delta,
        "best_mean_calibration_error_delta": -0.001,
        "average_brier_score_delta": brier_delta,
        "average_log_loss_delta": log_loss_delta,
        "average_final_hit_rate_delta": 0.0,
        "summary_json": {},
    }
