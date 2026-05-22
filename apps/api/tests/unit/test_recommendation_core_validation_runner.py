from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PersistedRecommendationLifecycleReplayResult,
    RecommendationChainIntegrityIssue,
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationChainRunNode,
    RecommendationCoreReplayReport,
    RecommendationCoreReplayRunResult,
    RecommendationCoreValidationOptions,
    RecommendationGlobalPlannerResult,
    RecommendationPrematchPipelineRunResult,
    build_recommendation_chain_integrity_report,
    run_recommendation_core_validation,
)
from nutmeg.recommendations.core_validation_runner import (
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations.global_planner import RecommendationGlobalPlannerOptions
from nutmeg.recommendations.prematch_pipeline import RecommendationPrematchPipelineOptions


def test_core_validation_runner_orchestrates_global_pipeline_and_replay() -> None:
    calls: list[str] = []

    def global_runner(
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
    ) -> RecommendationGlobalPlannerResult:
        calls.append("global")
        assert database is not None
        assert options.pass_types == ("6x1",)
        assert options.modes == ("multiple",)
        assert options.dry_run is True
        assert options.internal_trace_json["source"] == (
            "recommendation_core_validation_runner_v3_1"
        )
        return RecommendationGlobalPlannerResult(
            dry_run=True,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=12,
            evaluated_option_count=1,
            generated_option_count=1,
            final_answer_decision_json={
                "unified_candidate_pool": {
                    "candidate_count": 3,
                    "valid_candidate_count": 3,
                    "family_count": 2,
                    "candidate_family_keys": [
                        "standalone_single:1x1:single",
                        "single_parlay:2x1:single",
                    ],
                    "selected_family_key": "single_parlay:2x1:single",
                    "selected_pass_type": "2x1",
                    "selected_mode": "single",
                    "two_x_one_is_candidate_family": True,
                    "correct_score_candidate_present": True,
                    "handicap_candidate_present": True,
                    "multiple_value_candidate_count": 2,
                    "multiple_value_admitted_candidate_count": 1,
                    "multiple_value_rejected_candidate_count": 1,
                    "multiple_value_extra_option_count": 3,
                    "selected_multiple_value_status": "admitted",
                    "selected_multiple_value_admitted": True,
                    "selected_multiple_extra_option_count": 2,
                    "multiple_value_rejection_reason_counts": {
                        "marginal_quality_gain_negative": 1
                    },
                }
            },
            warnings=["candidate_pool_small"],
        )

    def pipeline_runner(
        database: object,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None = None,
        audit_repository: object | None = None,
    ) -> RecommendationPrematchPipelineRunResult:
        calls.append("pipeline")
        assert database is not None
        assert requested_by == "unit-test"
        assert audit_repository is not None
        assert options.as_of_time_utc == _dt(2026, 5, 4, 12)
        assert options.lookback_hours == 12
        assert options.pass_type == "6x1"
        assert options.mode == "multiple"
        assert options.strategy == "accuracy_first"
        return RecommendationPrematchPipelineRunResult(
            dry_run=True,
            as_of_time_utc=options.normalized_as_of_time_utc,
            window_start_utc=options.window_start_utc,
            window_end_utc=options.normalized_as_of_time_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            requested_by=requested_by,
            checked_run_count=3,
            triggered_run_count=1,
            skipped_run_count=2,
            generated_recommendation_run_ids=[77],
            prematch_report_key="prematch_change:test",
            warnings=["dry_run_provider_incidents_not_persisted_before_recompute"],
        )

    def replay_runner(
        database: object,
        *,
        options: object,
    ) -> RecommendationCoreReplayRunResult:
        calls.append("replay")
        assert database is not None
        assert options.window_start_utc == _dt(2026, 5, 4, 0)
        assert options.window_end_utc == _dt(2026, 5, 4, 12)
        assert options.pass_type == "6x1"
        assert options.mode == "multiple"
        assert options.strategy == "accuracy_first"
        return RecommendationCoreReplayRunResult(
            report=RecommendationCoreReplayReport(
                report_key="core_replay:test",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                replay=PersistedRecommendationLifecycleReplayResult(
                    summary_json={"stage_count": 2}
                ),
                evaluations=[],
                strategy_metrics=[],
                checks=[],
                result_fixture_count=2,
                summary_json={
                    "core_flow_ready": True,
                    "run_count": 2,
                    "settled_run_count": 1,
                    "effective_evaluated_run_count": 1,
                    "effective_chain_count": 1,
                    "effective_chain_active_edge_count": 1,
                    "effective_leaf_recommendation_run_ids": [22],
                    "superseded_source_run_count": 1,
                    "ambiguous_successor_source_recommendation_run_ids": [10],
                    "validity_window_status_counts": {
                        "superseded": 1,
                        "stale_incident": 1,
                    },
                    "current_answer_recommendation_run_ids": [22],
                    "stale_recommendation_run_ids": [10],
                    "expired_kickoff_recommendation_run_ids": [],
                    "stale_incident_recommendation_run_ids": [10],
                    "successor_recompute_required_recommendation_run_ids": [10],
                    "final_hit": True,
                    "roi": 0.18,
                },
            ),
            warnings=["no_result_rows_for_replayed_recommendation_fixtures"],
        )

    def chain_runner(
        repository: object,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> RecommendationChainIntegrityReport:
        calls.append("chain")
        assert repository is not None
        assert options.window_start_utc == _dt(2026, 5, 4, 0)
        assert options.window_end_utc == _dt(2026, 5, 4, 12)
        assert options.pass_type == "6x1"
        assert options.mode == "multiple"
        assert options.strategy == "accuracy_first"
        return build_recommendation_chain_integrity_report(
            [
                _chain_node(10, status="current"),
                _chain_node(22, status="current", source_recommendation_run_id=10),
            ],
            options=options,
        )

    result = run_recommendation_core_validation(
        FakeDatabase(),
        options=RecommendationCoreValidationOptions(
            as_of_time_utc=_dt(2026, 5, 4, 12),
            lookback_hours=12,
            pass_type="6x1",
            mode="multiple",
            strategy="accuracy_first",
            requested_by="unit-test",
        ),
        global_planner_runner=global_runner,
        prematch_pipeline_runner=pipeline_runner,
        core_replay_runner=replay_runner,
        chain_integrity_runner=chain_runner,
    )

    assert calls == ["global", "pipeline", "replay", "chain"]
    assert result.run_key.startswith("core_validation:")
    assert result.window_start_utc == _dt(2026, 5, 4, 0)
    assert result.prematch_pipeline is not None
    assert result.prematch_pipeline.stored_run is None
    assert result.summary_json["global_best_candidate_count"] == 12
    assert result.summary_json["unified_candidate_pool_present"] is True
    assert result.summary_json["unified_candidate_pool_candidate_count"] == 3
    assert result.summary_json["unified_candidate_pool_valid_candidate_count"] == 3
    assert result.summary_json["unified_candidate_pool_family_count"] == 2
    assert result.summary_json["unified_candidate_pool_selected_pass_type"] == "2x1"
    assert result.summary_json["unified_candidate_pool_selected_2x1"] is True
    assert result.summary_json["unified_candidate_pool_selection_mismatch"] is False
    assert result.summary_json["unified_candidate_pool_correct_score_candidate_present"] is True
    assert result.summary_json["unified_candidate_pool_handicap_candidate_present"] is True
    assert result.summary_json["unified_candidate_pool_multiple_value_candidate_count"] == 2
    assert (
        result.summary_json[
            "unified_candidate_pool_multiple_value_admitted_candidate_count"
        ]
        == 1
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_multiple_value_rejected_candidate_count"
        ]
        == 1
    )
    assert (
        result.summary_json["unified_candidate_pool_multiple_value_extra_option_count"]
        == 3
    )
    assert (
        result.summary_json["unified_candidate_pool_selected_multiple_value_status"]
        == "admitted"
    )
    assert (
        result.summary_json["unified_candidate_pool_selected_multiple_value_admitted"]
        is True
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_extra_option_count"
        ]
        == 2
    )
    assert result.summary_json[
        "unified_candidate_pool_multiple_value_rejection_reason_counts"
    ] == {"marginal_quality_gain_negative": 1}
    assert result.summary_json["prematch_triggered_run_count"] == 1
    assert result.summary_json["core_replay_ready"] is True
    assert result.summary_json["core_replay_final_hit"] is True
    assert result.summary_json["core_replay_effective_evaluated_run_count"] == 1
    assert result.summary_json["effective_chain_count"] == 1
    assert result.summary_json["effective_chain_active_edge_count"] == 1
    assert result.summary_json["effective_leaf_run_count"] == 1
    assert result.summary_json["superseded_source_run_count"] == 1
    assert result.summary_json["ambiguous_successor_source_count"] == 1
    assert result.summary_json["stale_recommendation_count"] == 1
    assert result.summary_json["stale_incident_recommendation_count"] == 1
    assert result.summary_json["successor_recompute_required_count"] == 1
    assert result.summary_json["chain_integrity_ready"] is True
    assert result.summary_json["chain_integrity_source_status_sync_required_count"] == 1
    assert result.summary_json["successor_chain_evaluation_passed"] is True
    assert result.summary_json["successor_chain_effective_leaf_count"] == 1
    assert result.summary_json["successor_chain_active_edge_count"] == 1
    assert result.warnings == [
        "global_best:candidate_pool_small",
        (
            "prematch_pipeline:"
            "dry_run_provider_incidents_not_persisted_before_recompute"
        ),
        "core_replay:no_result_rows_for_replayed_recommendation_fixtures",
    ]


def test_core_validation_runner_can_run_replay_only_in_commit_mode() -> None:
    calls: list[str] = []

    def replay_runner(
        database: object,
        *,
        options: object,
    ) -> RecommendationCoreReplayRunResult:
        calls.append("replay")
        return RecommendationCoreReplayRunResult(
            report=RecommendationCoreReplayReport(
                report_key="core_replay:replay_only",
                window_start_utc=options.window_start_utc,
                window_end_utc=options.window_end_utc,
                replay=PersistedRecommendationLifecycleReplayResult(),
                evaluations=[],
                strategy_metrics=[],
                checks=[],
                result_fixture_count=0,
                summary_json={"core_flow_ready": False, "run_count": 0},
            )
        )

    result = run_recommendation_core_validation(
        FakeDatabase(),
        options=RecommendationCoreValidationOptions(
            as_of_time_utc=_dt(2026, 5, 4, 12),
            replay_window_start_utc=_dt(2026, 5, 1, 0),
            replay_window_end_utc=_dt(2026, 5, 3, 0),
            run_global_best=False,
            run_prematch_pipeline=False,
            dry_run=False,
            run_chain_integrity=False,
        ),
        core_replay_runner=replay_runner,
    )

    assert calls == ["replay"]
    assert result.dry_run is False
    assert result.global_best is None
    assert result.prematch_pipeline is None
    assert result.replay_window_start_utc == _dt(2026, 5, 1, 0)
    assert result.replay_window_end_utc == _dt(2026, 5, 3, 0)
    assert result.summary_json["core_replay_run_count"] == 0


def test_core_validation_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--as-of-time-utc",
            "2026-05-04T12:00:00Z",
            "--replay-window-start-utc",
            "2026-05-01T00:00:00Z",
            "--replay-window-end-utc",
            "2026-05-03T00:00:00Z",
            "--pass-type",
            "8x1",
            "--mode",
            "single",
            "--commit",
            "--save-audit",
            "--no-require-odds",
            "--no-max-budget",
            "--skip-prematch-pipeline",
            "--skip-chain-integrity",
        ]
    )

    options = _options_from_args(args)

    assert options.as_of_time_utc == _dt(2026, 5, 4, 12)
    assert options.replay_window_start_utc == _dt(2026, 5, 1, 0)
    assert options.replay_window_end_utc == _dt(2026, 5, 3, 0)
    assert options.pass_type == "8x1"
    assert options.mode == "single"
    assert options.dry_run is False
    assert options.save_pipeline_audit is True
    assert options.require_odds is False
    assert options.max_budget is None
    assert options.run_prematch_pipeline is False
    assert options.run_chain_integrity is False
    assert options.run_successor_chain_evaluation is False


def test_core_validation_runner_marks_chain_integrity_critical_issue() -> None:
    def chain_runner(
        repository: object,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> RecommendationChainIntegrityReport:
        return RecommendationChainIntegrityReport(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.window_end_utc,
            ready=False,
            issues=[
                RecommendationChainIntegrityIssue(
                    code="multiple_active_successors",
                    severity="critical",
                    message="duplicate successor",
                    recommendation_run_id=1,
                    successor_recommendation_run_ids=[2, 3],
                )
            ],
            summary_json={
                "issue_count": 1,
                "critical_issue_count": 1,
                "warning_issue_count": 0,
                "source_status_sync_required_count": 0,
            },
        )

    result = run_recommendation_core_validation(
        FakeDatabase(),
        options=RecommendationCoreValidationOptions(
            as_of_time_utc=_dt(2026, 5, 4, 12),
            run_global_best=False,
            run_prematch_pipeline=False,
            run_core_replay=False,
        ),
        chain_integrity_runner=chain_runner,
    )

    assert result.summary_json["chain_integrity_ready"] is False
    assert result.summary_json["chain_integrity_critical_issue_count"] == 1
    assert result.warnings == [
        "chain_integrity:critical:multiple_active_successors",
        "successor_chain_evaluation:failed_check:chain_integrity_critical_issue_count",
    ]


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _chain_node(
    recommendation_run_id: int,
    *,
    status: str,
    source_recommendation_run_id: int | None = None,
) -> RecommendationChainRunNode:
    return RecommendationChainRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=f"run-{recommendation_run_id}",
        as_of_time_utc=_dt(2026, 5, 4, 10),
        strategy="accuracy_first",
        pass_type="6x1",
        mode="multiple",
        status=status,
        selected_fixture_ids=["A", "B", "C", "D", "E", "F"],
        locked_fixture_ids=["A", "B"],
        source_recommendation_run_id=source_recommendation_run_id,
        created_at=_dt(2026, 5, 4, 10),
    )
