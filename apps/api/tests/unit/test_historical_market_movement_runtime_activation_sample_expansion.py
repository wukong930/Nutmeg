from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import (
    historical_market_movement_runtime_activation_segment_replay_batch_gate as batch_gate,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    HistoricalMarketMovementRiskFilterRuntimeActivationReport,
)
from nutmeg.recommendations.historical_market_movement_runtime_activation_sample_expansion import (
    build_historical_market_movement_runtime_activation_sample_expansion_report,
    main,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
)
from nutmeg.recommendations.historical_sample_coverage_audit import (
    HistoricalSampleCoverageAuditReport,
)


def test_activation_sample_expansion_keeps_single_segment_shadow_only() -> None:
    report = build_historical_market_movement_runtime_activation_sample_expansion_report(
        _activation_report(),
        sample_readiness_reports=[_sample_readiness_report()],
        coverage_audit_reports=[_coverage_audit_report()],
    )

    assert report.status == "shadow_only"
    assert report.passed is True
    assert report.promotion_ready is False
    assert report.ready_fixture_count == 600
    assert report.supplemental_fixture_count == 2520
    assert report.combined_fixture_count == 3120
    assert report.combined_competition_count == 12
    assert report.selected_segment_competition_ids == ["LA_LIGA"]
    assert "selected_segment_count_for_promotion" in report.watchlist
    assert "adjusted_to_combined_fixture_ratio_for_promotion" in report.watchlist


def test_activation_sample_expansion_is_ready_when_direct_evidence_broadens() -> None:
    report = build_historical_market_movement_runtime_activation_sample_expansion_report(
        _activation_report(
            selected_segments=[
                "competition_outcome:LA_LIGA:home_win",
                "competition_outcome:EPL:away_win",
            ],
            adjusted_fixture_count=240,
            adjusted_prediction_count=720,
        ),
        sample_readiness_reports=[_sample_readiness_report()],
        coverage_audit_reports=[_coverage_audit_report()],
    )

    assert report.status == "sample_expansion_ready"
    assert report.passed is True
    assert report.promotion_ready is True
    assert report.watchlist == []
    assert report.adjusted_to_combined_fixture_ratio == 240 / 3120


def test_activation_sample_expansion_uses_segment_replay_batch_as_effective_evidence() -> None:
    report = build_historical_market_movement_runtime_activation_sample_expansion_report(
        _activation_report(),
        sample_readiness_reports=[_sample_readiness_report()],
        coverage_audit_reports=[_coverage_audit_report()],
        segment_replay_batch_gate_reports=[_segment_replay_batch_gate_report()],
    )

    assert report.status == "sample_expansion_ready"
    assert report.passed is True
    assert report.promotion_ready is True
    assert report.segment_replay_batch_gate_count == 1
    assert report.segment_replay_batch_ready_count == 1
    assert report.segment_replay_batch_adjusted_fixture_count == 1323
    assert report.effective_adjusted_fixture_count == 1323
    assert report.effective_adjusted_to_combined_fixture_ratio == 1323 / 3120
    assert report.effective_segment_count == 5
    assert report.watchlist == []


def test_activation_sample_expansion_blocks_missing_ready_samples() -> None:
    report = build_historical_market_movement_runtime_activation_sample_expansion_report(
        _activation_report(staged_activation_ready=False, status="blocked"),
        sample_readiness_reports=[],
        coverage_audit_reports=[],
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.passed is False
    assert report.promotion_ready is False
    assert "activation_ready" in failed_checks
    assert "readiness_report_count" in failed_checks
    assert "ready_fixture_count" in failed_checks


def test_activation_sample_expansion_cli_writes_report(tmp_path: Path) -> None:
    activation_path = tmp_path / "activation.json"
    readiness_path = tmp_path / "readiness.json"
    coverage_path = tmp_path / "coverage.json"
    output_path = tmp_path / "sample_expansion.json"
    activation_path.write_text(
        f"{_activation_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    readiness_path.write_text(
        f"{_sample_readiness_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    coverage_path.write_text(
        f"{_coverage_audit_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--activation-report",
            str(activation_path),
            "--sample-readiness-report",
            str(readiness_path),
            "--coverage-audit-report",
            str(coverage_path),
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "shadow_only"
    assert payload["passed"] is True
    assert payload["promotion_ready"] is False
    assert payload["summary_json"]["supplemental_fixture_count"] == 2520


def test_activation_sample_expansion_cli_accepts_segment_replay_batch_gate(
    tmp_path: Path,
) -> None:
    activation_path = tmp_path / "activation.json"
    readiness_path = tmp_path / "readiness.json"
    coverage_path = tmp_path / "coverage.json"
    batch_gate_path = tmp_path / "batch_gate.json"
    output_path = tmp_path / "sample_expansion.json"
    activation_path.write_text(
        f"{_activation_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    readiness_path.write_text(
        f"{_sample_readiness_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    coverage_path.write_text(
        f"{_coverage_audit_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    batch_gate_path.write_text(
        f"{_segment_replay_batch_gate_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--activation-report",
            str(activation_path),
            "--sample-readiness-report",
            str(readiness_path),
            "--coverage-audit-report",
            str(coverage_path),
            "--segment-replay-batch-gate-report",
            str(batch_gate_path),
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "sample_expansion_ready"
    assert payload["promotion_ready"] is True
    assert payload["summary_json"]["effective_adjusted_fixture_count"] == 1323


def _activation_report(
    *,
    status: str = "staged_activation_ready",
    staged_activation_ready: bool = True,
    selected_segments: list[str] | None = None,
    adjusted_fixture_count: int = 120,
    adjusted_prediction_count: int = 360,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationReport:
    return HistoricalMarketMovementRiskFilterRuntimeActivationReport.model_validate(
        {
            "report_key": "historical_market_movement_runtime_activation:test",
            "status": status,
            "staged_activation_ready": staged_activation_ready,
            "staged_profile_version": "market-movement-staged-v1",
            "source_suite_gate_key": "historical_suite_quality_gate:test",
            "source_runtime_replay_report_key": "runtime-replay:test",
            "source_runtime_profile_version": "market-movement-runtime-v1",
            "rule_count": 1,
            "selected_rule_count": 1,
            "selected_rule_ids": [
                "market_movement_risk_filter_runtime_shadow_candidate_v1"
            ],
            "selected_segment_group_keys": selected_segments
            or ["competition_outcome:LA_LIGA:home_win"],
            "rollback_conditions": [
                "disable_if_shadow_replay_fails_no_harm_gate"
            ],
            "adjusted_fixture_count": adjusted_fixture_count,
            "adjusted_prediction_count": adjusted_prediction_count,
            "final_hit_rate_delta": 0.0,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
            "brier_score_delta": -0.001288445,
            "log_loss_delta": -0.002760848,
            "mean_calibration_error_delta": -0.001278256,
            "default_profile_write_requested": False,
            "default_profile_written": False,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": False,
            "default_recommendation_path_changed": False,
            "public_response_changed": False,
            "checks": [],
            "blockers": [] if staged_activation_ready else ["activation_ready"],
            "staged_profile_json": {"staged_only": True},
            "public_contract_json": {
                "public_response_changed": False,
                "production_recommendation_changed": False,
                "default_recommendation_path_changed": False,
                "default_profile_written": False,
            },
            "warnings": [],
            "summary_json": {},
        }
    )


HistoricalSegmentReplayBatchGateReport = (
    batch_gate.HistoricalMarketMovementRuntimeActivationSegmentReplayBatchGateReport
)


def _segment_replay_batch_gate_report() -> HistoricalSegmentReplayBatchGateReport:
    segment_group_keys = [
        "competition_direction:LA_LIGA:probability_drifted",
        "opening_probability_band:0.25:0.45",
        "outcome:home_win",
        "strongest_movement_direction:probability_shortened",
    ]
    return (
        HistoricalSegmentReplayBatchGateReport.model_validate(
            {
                "report_key": "historical_market_movement_segment_replay_batch_gate:test",
                "status": "watchlist",
                "passed": True,
                "runtime_replay_batch_ready": True,
                "production_promotion_ready": False,
                "gate_id": "market-movement-runtime-activation-segment-replay-batch-gate-v3.2",
                "source_segment_expansion_report_key": (
                    "historical_market_movement_segment_expansion:test"
                ),
                "source_segment_expansion_status": "runtime_replay_expansion_ready",
                "source_segment_expansion_passed": True,
                "source_runtime_replay_expansion_ready": True,
                "source_production_promotion_ready": False,
                "replay_report_count": 4,
                "passed_replay_count": 4,
                "failed_replay_count": 0,
                "runtime_allowed_replay_count": 4,
                "distinct_rule_count": 4,
                "distinct_segment_count": 4,
                "covered_selected_segment_count": 4,
                "total_adjusted_fixture_count": 1323,
                "total_adjusted_prediction_count": 3969,
                "weighted_final_hit_rate_delta": 0.0,
                "weighted_roi_delta": 0.0,
                "total_profit_loss_delta": 0.0,
                "weighted_brier_score_delta": -0.001158,
                "weighted_log_loss_delta": -0.002435,
                "weighted_mean_calibration_error_delta": -0.001259,
                "worst_final_hit_rate_delta": 0.0,
                "worst_roi_delta": 0.0,
                "worst_brier_score_delta": 0.0,
                "worst_log_loss_delta": 0.0,
                "worst_mean_calibration_error_delta": 0.0,
                "selected_rule_ids": [
                    "market_movement_risk_filter_runtime_shadow_candidate_v1"
                ],
                "selected_segment_group_keys": segment_group_keys,
                "replayed_rule_ids": [
                    "market_movement_risk_filter_runtime_shadow_candidate_v1"
                ],
                "replayed_segment_group_keys": segment_group_keys,
                "missing_selected_segment_group_keys": [],
                "unexpected_replayed_rule_ids": [],
                "unexpected_replayed_segment_group_keys": [],
                "default_recommendation_path_changed": False,
                "production_recommendation_changed": False,
                "public_response_changed": False,
                "replay_summaries": [],
                "checks": [],
                "blockers": [],
                "watchlist": ["segment_expansion_production_promotion_ready"],
                "warnings": [
                    "market_movement_segment_replay_batch_gate:watchlist:segment_expansion_production_promotion_ready"
                ],
                "summary_json": {},
            }
        )
    )


def _sample_readiness_report() -> HistoricalPrematchFeatureSampleReadinessReport:
    competition_ids = ["BUNDESLIGA", "EPL", "LA_LIGA", "LIGUE_1", "SERIE_A"]
    season_ids = [
        "2020-2021",
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
    ]
    competition_season_keys = [
        f"{competition_id}:{season_id}"
        for competition_id in competition_ids
        for season_id in season_ids
    ]
    return HistoricalPrematchFeatureSampleReadinessReport.model_validate(
        {
            "readiness_key": "historical_prematch_feature_sample_readiness:test",
            "status": "accepted",
            "sample_ready_allowed": True,
            "shadow_allowed": True,
            "readiness_id": "market-feature-readiness-test",
            "target_profile": "market_movement",
            "coverage_audit_key": "historical_sample_coverage_audit:core",
            "source_count": 1,
            "evaluated_source_count": 1,
            "accepted_source_count": 1,
            "shadow_only_source_count": 0,
            "rejected_source_count": 0,
            "ready_source_ids": ["core-five-leagues"],
            "ready_fixture_count": 600,
            "ready_slice_count": 25,
            "ready_competition_count": len(competition_ids),
            "ready_season_count": len(season_ids),
            "ready_competition_season_count": len(competition_season_keys),
            "checks": [],
            "sources": [
                {
                    "source_id": "core-five-leagues",
                    "status": "accepted",
                    "target_profile": "market_movement",
                    "ready_for_target": True,
                    "source_path": None,
                    "slice_count": 25,
                    "fixture_count": 600,
                    "competition_count": len(competition_ids),
                    "season_count": len(season_ids),
                    "competition_season_count": len(competition_season_keys),
                    "readiness_json": {
                        "final_answer_sample_ready": True,
                        "feature_snapshot_ready": True,
                        "market_movement_feature_ready": True,
                    },
                    "checks": [],
                    "failed_check_names": [],
                    "warnings": [],
                    "coverage_json": {"odds_time_series_coverage": 1.0},
                    "summary_json": {
                        "competition_ids": competition_ids,
                        "season_ids": season_ids,
                        "competition_season_keys": competition_season_keys,
                    },
                }
            ],
            "warnings": [],
            "summary_json": {},
        }
    )


def _coverage_audit_report() -> HistoricalSampleCoverageAuditReport:
    competition_ids = [
        "ENG_CHAMPIONSHIP",
        "ESP_SEGUNDA_DIVISION",
        "FRA_LIGUE_2",
        "GER_2_BUNDESLIGA",
        "ITA_SERIE_B",
        "NED_EREDIVISIE",
        "PRT_PRIMEIRA_LIGA",
    ]
    season_ids = [
        "2020-2021",
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
    ]
    competition_season_keys = [
        f"{competition_id}:{season_id}"
        for competition_id in competition_ids
        for season_id in season_ids
    ]
    return HistoricalSampleCoverageAuditReport.model_validate(
        {
            "audit_key": "historical_sample_coverage_audit:expanded",
            "audit_id": "expanded-a-leagues-market-feature-test",
            "status": "generated",
            "source_count": 1,
            "slice_count": 210,
            "fixture_count": 2520,
            "sources": [
                {
                    "source_id": "expanded-a-leagues",
                    "source_type": "suite_manifest",
                    "source_path": None,
                    "slice_count": 210,
                    "fixture_count": 2520,
                    "prediction_count": 7560,
                    "complete_1x2_fixture_count": 2520,
                    "feature_snapshot_count": 2520,
                    "prematch_context_count": 2520,
                    "lineup_feature_count": 0,
                    "availability_feature_count": 0,
                    "odds_movement_feature_count": 2520,
                    "odds_time_series_feature_count": 2520,
                    "semantic_signal_feature_count": 0,
                    "source_ref_count": 2520,
                    "feature_snapshot_coverage": 1.0,
                    "complete_1x2_coverage": 1.0,
                    "prematch_context_coverage": 1.0,
                    "lineup_coverage": 0.0,
                    "availability_coverage": 0.0,
                    "odds_movement_coverage": 1.0,
                    "odds_time_series_coverage": 1.0,
                    "semantic_signal_coverage": 0.0,
                    "source_ref_coverage": 1.0,
                    "competition_ids": competition_ids,
                    "season_ids": season_ids,
                    "competition_season_keys": competition_season_keys,
                    "readiness_json": {
                        "final_answer_sample_ready": True,
                        "feature_snapshot_ready": True,
                        "market_movement_feature_ready": True,
                    },
                    "warnings": [],
                    "summary_json": {},
                }
            ],
            "cross_source_gaps": [],
            "warnings": [],
            "summary_json": {},
        }
    )
