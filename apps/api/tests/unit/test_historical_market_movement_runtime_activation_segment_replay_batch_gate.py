from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_replay import (
    HistoricalMarketMovementRiskFilterRuntimeReplayReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_segment_expansion import (
    HistoricalMarketMovementRuntimeActivationSegmentExpansionReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_segment_replay_batch_gate import (  # noqa: E501
    HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions,
    build_historical_market_movement_runtime_activation_segment_replay_batch_gate_report,
    main,
)


def test_segment_replay_batch_gate_accepts_full_shadow_batch() -> None:
    report = (
        build_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
            _segment_expansion_report(),
            replay_reports=[
                _replay_report("rule-a", "segment:a", 120),
                _replay_report("rule-b", "segment:b", 80),
            ],
            options=HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateOptions(
                min_replay_report_count=2,
                min_passed_replay_count=2,
                min_distinct_rule_count=2,
                min_distinct_segment_count=2,
                min_covered_selected_segment_count=2,
                min_total_adjusted_fixture_count=200,
                min_total_adjusted_prediction_count=600,
            ),
        )
    )

    assert report.status == "watchlist"
    assert report.passed is True
    assert report.runtime_replay_batch_ready is True
    assert report.production_promotion_ready is False
    assert report.passed_replay_count == 2
    assert report.total_adjusted_fixture_count == 200
    assert report.total_adjusted_prediction_count == 600
    assert report.missing_selected_segment_group_keys == []
    assert report.watchlist == ["segment_expansion_production_promotion_ready"]


def test_segment_replay_batch_gate_blocks_missing_selected_segment() -> None:
    report = (
        build_historical_market_movement_runtime_activation_segment_replay_batch_gate_report(
            _segment_expansion_report(),
            replay_reports=[_replay_report("rule-a", "segment:a", 120)],
        )
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.passed is False
    assert "all_expansion_selected_segments_replayed" in failed_checks
    assert report.missing_selected_segment_group_keys == ["segment:b"]


def test_segment_replay_batch_gate_cli_writes_report(tmp_path: Path) -> None:
    expansion_path = tmp_path / "segment_expansion.json"
    replay_a_path = tmp_path / "replay_a.json"
    replay_b_path = tmp_path / "replay_b.json"
    output_path = tmp_path / "batch_gate.json"
    expansion_path.write_text(
        f"{_segment_expansion_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    replay_a_path.write_text(
        f"{_replay_report('rule-a', 'segment:a', 120).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    replay_b_path.write_text(
        f"{_replay_report('rule-b', 'segment:b', 80).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--segment-expansion-report",
            str(expansion_path),
            "--runtime-replay-report",
            str(replay_a_path),
            "--runtime-replay-report",
            str(replay_b_path),
            "--min-replay-report-count",
            "2",
            "--min-passed-replay-count",
            "2",
            "--min-total-adjusted-fixture-count",
            "200",
            "--min-total-adjusted-prediction-count",
            "600",
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "watchlist"
    assert payload["passed"] is True
    assert payload["runtime_replay_batch_ready"] is True
    assert payload["summary_json"]["replay_report_count"] == 2


def _segment_expansion_report() -> (
    HistoricalMarketMovementRuntimeActivationSegmentExpansionReport
):
    return HistoricalMarketMovementRuntimeActivationSegmentExpansionReport.model_validate(
        {
            "report_key": "historical_market_movement_segment_expansion:test",
            "status": "watchlist",
            "passed": True,
            "runtime_replay_expansion_ready": True,
            "production_promotion_ready": False,
            "expansion_id": "segment-expansion-test",
            "source_sample_expansion_report_key": "sample-expansion:test",
            "source_scope_refinement_report_key": "scope-refinement:test",
            "source_activation_report_key": "activation:test",
            "sample_expansion_status": "shadow_only",
            "sample_expansion_passed": True,
            "sample_expansion_promotion_ready": False,
            "scope_refinement_status": "guarded_scope_required",
            "stable_scope_count": 2,
            "selected_candidate_count": 2,
            "selected_segment_group_keys": ["segment:a", "segment:b"],
            "existing_segment_group_keys": [],
            "total_adjusted_fixture_count": 200,
            "total_adjusted_prediction_count": 600,
            "total_competition_count": 2,
            "total_season_count": 2,
            "combined_sample_fixture_count": 1000,
            "adjusted_to_combined_fixture_ratio": 0.2,
            "default_profile_written": False,
            "default_recommendation_path_changed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "profile_json": {
                "rules": [
                    {"rule_id": "rule-a", "segment_group_keys": ["segment:a"]},
                    {"rule_id": "rule-b", "segment_group_keys": ["segment:b"]},
                ]
            },
            "candidates": [],
            "checks": [],
            "blockers": [],
            "watchlist": ["sample_expansion_promotion_ready_for_production"],
            "warnings": [],
            "summary_json": {},
        }
    )


def _replay_report(
    rule_id: str,
    segment_group_key: str,
    adjusted_fixture_count: int,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayReport:
    return HistoricalMarketMovementRiskFilterRuntimeReplayReport.model_validate(
        {
            "report_key": f"historical_market_movement_runtime_replay:{rule_id}",
            "status": "runtime_shadow_replay_passed",
            "runtime_shadow_replay_allowed": True,
            "holdout_replay_allowed": True,
            "source_rule_profile_version": "segment-expansion-test-profile",
            "rule_count": 2,
            "selected_rule_count": 1,
            "selected_rule_id": rule_id,
            "segment_gate_report_key": "segment-gate:test",
            "selected_candidate_id": f"candidate:{rule_id}",
            "selected_segment_group_key": segment_group_key,
            "candidate_count": 1,
            "accepted_count": 1,
            "adjusted_fixture_count": adjusted_fixture_count,
            "adjusted_prediction_count": adjusted_fixture_count * 3,
            "final_hit_rate_delta": 0.0,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
            "brier_score_delta": -0.001,
            "log_loss_delta": -0.002,
            "mean_calibration_error_delta": -0.001,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "rule_set_json": {},
            "selected_rule_json": {},
            "segment_gate_report_json": {},
            "warnings": [],
            "summary_json": {},
        }
    )
