from __future__ import annotations

from pathlib import Path


def test_core_migration_contains_required_milestone_one_tables_and_fields() -> None:
    sql = Path("db/migrations/0001_core_schema.sql").read_text(encoding="utf-8")

    for table_name in [
        "competitions",
        "fixtures",
        "odds_snapshots",
        "feature_snapshots",
        "score_probability_grids",
        "prediction_snapshots",
        "market_predictions",
        "parlay_atomic_bets",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for field_name in [
        "prediction_time_utc",
        "model_version",
        "feature_version",
        "calibration_version",
        "score_grid_id",
        "market_probabilities_json",
    ]:
        assert field_name in sql


def test_accuracy_loop_migration_contains_calibration_and_backtest_storage() -> None:
    sql = Path("db/migrations/0002_accuracy_loop.sql").read_text(encoding="utf-8")

    for table_name in [
        "calibration_buckets",
        "model_backtest_runs",
        "model_comparison_reports",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for field_name in [
        "bucket_start",
        "bucket_end",
        "sample_size",
        "actual_count",
        "mode",
        "as_of_time",
        "decision_stub",
    ]:
        assert field_name in sql


def test_accuracy_write_migration_handles_nullable_calibration_competition() -> None:
    sql = Path("db/migrations/0003_accuracy_write_contract.sql").read_text(encoding="utf-8")

    assert "idx_calibration_buckets_unique_nullable" in sql
    assert "NULLS NOT DISTINCT" in sql


def test_accuracy_job_runs_migration_contains_governed_job_audit_table() -> None:
    sql = Path("db/migrations/0004_accuracy_job_runs.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS accuracy_job_runs" in sql
    for field_name in [
        "accuracy_job_run_id",
        "job_type",
        "status",
        "reset_requested",
        "requested_by",
        "started_at",
        "completed_at",
        "duration_ms",
        "fixture_count",
        "evaluation_count",
        "calibration_observation_count",
        "model_comparison_report_id",
        "prediction_snapshot_ids_json",
        "evaluation_ids_json",
        "error_message",
        "metadata_json",
    ]:
        assert field_name in sql


def test_provider_governance_migration_contains_authorization_and_gate_tables() -> None:
    sql = Path("db/migrations/0005_provider_governance.sql").read_text(encoding="utf-8")

    for table_name in [
        "provider_authorizations",
        "provider_sync_runs",
        "competition_onboarding_assessments",
        "model_promotion_reviews",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for field_name in [
        "terms_checked_at_utc",
        "commercial_use_allowed",
        "retention_allowed",
        "api_key_env_var",
        "data_quality_score",
        "historical_sample_size",
        "market_resolver_tests_passed",
        "score_grid_generation_passed",
        "rollback_plan_json",
    ]:
        assert field_name in sql


def test_provider_authorization_seed_contains_runtime_provider_names() -> None:
    sql = Path("db/migrations/0024_provider_authorization_seed.sql").read_text(encoding="utf-8")

    for provider_name in [
        "mock-local",
        "football-data.org",
        "the-odds-api",
        "sportmonks",
    ]:
        assert provider_name in sql

    assert "ON CONFLICT (provider_name)" in sql
    assert "FOOTBALL_DATA_API_KEY" in sql
    assert "THE_ODDS_API_KEY" in sql
    assert "SPORTMONKS_API_KEY" in sql


def test_provider_authorization_metadata_migration_matches_provider_registry_spec() -> None:
    sql = Path("db/migrations/0026_provider_authorization_metadata.sql").read_text(encoding="utf-8")

    for field_name in [
        "allowed_use",
        "rate_limit",
        "historical_data_allowed",
        "redistribution_allowed",
        "terms_url",
        "owner",
    ]:
        assert field_name in sql

    assert "api-football" in sql
    assert "API_FOOTBALL_API_KEY" in sql
    assert "ON CONFLICT (provider_name)" in sql


def test_provider_authorization_reviews_migration_adds_terms_review_audit_chain() -> None:
    sql = Path("db/migrations/0027_provider_authorization_reviews.sql").read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS last_reviewed_at" in sql
    assert "ADD COLUMN IF NOT EXISTS next_review_due_at" in sql
    assert "CREATE TABLE IF NOT EXISTS provider_authorization_reviews" in sql
    assert "UNIQUE(provider_name, review_reference)" in sql
    for field_name in [
        "review_status",
        "reviewed_by",
        "terms_version_hash",
        "commercial_use_allowed",
        "retention_allowed",
        "historical_data_allowed",
        "redistribution_allowed",
        "evidence_json",
    ]:
        assert field_name in sql


def test_provider_ops_audit_migration_adds_unified_operator_event_log() -> None:
    sql = Path("db/migrations/0028_provider_ops_audit_events.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_ops_audit_events" in sql
    for field_name in [
        "provider_ops_audit_event_id",
        "event_type",
        "operator_name",
        "action_surface",
        "target_type",
        "target_id",
        "outcome",
        "request_path",
        "request_method",
        "metadata_json",
        "created_at",
    ]:
        assert field_name in sql
    assert "idx_provider_ops_audit_events_created" in sql
    assert "idx_provider_ops_audit_events_operator_created" in sql


def test_provider_ops_run_history_migration_adds_helper_run_log() -> None:
    sql = Path("db/migrations/0032_provider_ops_run_history.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_ops_run_history" in sql
    for field_name in [
        "provider_ops_run_id",
        "run_name",
        "run_type",
        "source",
        "status",
        "operator_name",
        "started_at",
        "completed_at",
        "duration_ms",
        "exit_code",
        "summary_json",
        "output_excerpt",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "provider_ops_run_history_status_check" in sql
    assert "idx_provider_ops_run_history_created" in sql
    assert "idx_provider_ops_run_history_name_created" in sql


def test_recommendation_engine_migration_adds_v3_1_decision_tables() -> None:
    sql = Path("db/migrations/0033_recommendation_engine.sql").read_text(encoding="utf-8")

    for table_name in [
        "recommendation_policy_configs",
        "recommendation_runs",
        "recommendation_candidates",
        "recommendation_versions",
        "recommendation_lifecycle_events",
        "recommendation_locked_legs",
        "recommendation_budget_adjustments",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for field_name in [
        "as_of_time_utc",
        "strategy",
        "pass_type",
        "selected_fixture_ids_json",
        "locked_fixture_ids_json",
        "parlay_evaluation_json",
        "upset_protection_score",
        "recommendation_score",
        "event_time_utc",
    ]:
        assert field_name in sql


def test_recommendation_lifecycle_api_migration_adds_lock_and_event_indexes() -> None:
    sql = Path("db/migrations/0034_recommendation_lifecycle_api_contract.sql").read_text(
        encoding="utf-8"
    )

    for index_name in [
        "idx_recommendation_runs_status_created",
        "idx_recommendation_locked_legs_run_status",
        "idx_recommendation_locked_legs_unique_active",
        "idx_recommendation_lifecycle_events_key_time",
    ]:
        assert index_name in sql

    assert "WHERE status = 'locked'" in sql


def test_recommendation_strategy_evaluation_migration_adds_accuracy_loop_tables() -> None:
    sql = Path("db/migrations/0035_recommendation_strategy_evaluation.sql").read_text(
        encoding="utf-8"
    )

    for table_name in [
        "recommendation_run_evaluations",
        "recommendation_strategy_metrics",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    for field_name in [
        "recommendation_run_id",
        "strategy",
        "pass_type",
        "mode",
        "evaluation_status",
        "won_atomic_bets",
        "lost_atomic_bets",
        "unresolved_atomic_bets",
        "expected_hit_probability_at_recommendation",
        "hit_calibration_error",
        "expected_roi_at_recommendation",
        "settlement_detail_json",
        "average_expected_hit_probability",
        "average_hit_calibration_error",
        "average_expected_roi",
    ]:
        assert field_name in sql

    assert "idx_recommendation_run_evaluations_strategy_time" in sql
    assert "idx_recommendation_strategy_metrics_window" in sql


def test_recommendation_strategy_governance_migration_adds_review_storage() -> None:
    sql = Path("db/migrations/0036_recommendation_strategy_governance.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS recommendation_strategy_reviews" in sql
    for field_name in [
        "review_key",
        "candidate_strategy",
        "baseline_strategy",
        "decision",
        "next_status",
        "candidate_roi",
        "baseline_roi",
        "candidate_hit_rate",
        "baseline_hit_rate",
        "candidate_calibration_error",
        "baseline_calibration_error",
        "metrics_json",
        "reasons_json",
        "rollback_plan_json",
    ]:
        assert field_name in sql

    assert "idx_recommendation_strategy_reviews_candidate_scope" in sql
    assert "idx_recommendation_strategy_reviews_decision" in sql


def test_provider_runtime_monitoring_migration_adds_snapshot_storage() -> None:
    sql = Path("db/migrations/0029_provider_runtime_monitoring.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_runtime_snapshots" in sql
    for field_name in [
        "provider_runtime_snapshot_id",
        "provider_name",
        "capability",
        "probe_status",
        "key_configured",
        "live_probe",
        "safe_to_call_real_provider",
        "latency_ms",
        "error_rate",
        "rate_limit_remaining",
        "fallback_used",
        "next_action",
        "metadata_json",
        "observed_at",
    ]:
        assert field_name in sql
    assert "idx_provider_runtime_snapshots_provider_observed" in sql
    assert "idx_provider_runtime_snapshots_status_observed" in sql


def test_provider_runtime_incident_migration_adds_report_storage() -> None:
    sql = Path("db/migrations/0030_provider_runtime_incident_reports.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS provider_runtime_incident_reports" in sql
    for field_name in [
        "provider_runtime_incident_report_id",
        "alert_level",
        "alert_count",
        "snapshot_count",
        "summary_json",
        "alerts_json",
        "thresholds_json",
        "source",
        "created_by",
        "metadata_json",
        "created_at",
    ]:
        assert field_name in sql
    assert "idx_provider_runtime_incidents_created" in sql
    assert "idx_provider_runtime_incidents_level_created" in sql


def test_provider_runtime_incident_lifecycle_migration_adds_status_fields() -> None:
    sql = Path("db/migrations/0031_provider_runtime_incident_lifecycle.sql").read_text(
        encoding="utf-8"
    )

    for field_name in [
        "incident_status",
        "acknowledged_by",
        "acknowledged_at",
        "resolved_by",
        "resolved_at",
        "resolution_note",
        "notification_status",
        "notification_payload_json",
        "updated_at",
    ]:
        assert field_name in sql
    assert "provider_runtime_incident_status_check" in sql
    assert "provider_runtime_incident_notification_status_check" in sql
    assert "'not_configured', 'queued', 'sent', 'skipped', 'failed'" in sql
    assert "idx_provider_runtime_incidents_status_created" in sql
    assert "idx_provider_runtime_incidents_updated" in sql


def test_recommendation_candidate_pool_and_incident_migration_adds_replay_storage() -> None:
    sql = Path(
        "db/migrations/0037_recommendation_candidate_pool_and_incidents.sql"
    ).read_text(encoding="utf-8")

    for table_name in [
        "recommendation_candidate_pool_snapshots",
        "recommendation_candidate_pool_items",
        "recommendation_provider_incident_events",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql
    for field_name in [
        "recommendation_candidate_pool_snapshot_id",
        "recommendation_candidate_pool_item_id",
        "provider_incident_key",
        "excluded_fixture_ids_json",
        "affects_recommendations",
        "candidate_query_json",
        "selected_candidate_count",
    ]:
        assert field_name in sql
    assert "recommendation_provider_incident_status_check" in sql
    assert "idx_recommendation_candidate_pool_items_fixture" in sql
    assert "idx_recommendation_provider_incidents_status_time" in sql


def test_recommendation_prematch_change_report_migration_adds_report_storage() -> None:
    sql = Path("db/migrations/0038_recommendation_prematch_change_reports.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS recommendation_prematch_change_reports" in sql
    for field_name in [
        "recommendation_prematch_change_report_id",
        "report_key",
        "window_start_utc",
        "window_end_utc",
        "stage_count",
        "changed_stage_count",
        "incident_count",
        "critical_incident_count",
        "locked_preservation_stage_count",
        "report_json",
    ]:
        assert field_name in sql
    assert "idx_recommendation_prematch_reports_window" in sql
    assert "idx_recommendation_prematch_reports_incidents" in sql


def test_recommendation_recompute_trigger_migration_adds_audit_storage() -> None:
    sql = Path("db/migrations/0039_recommendation_recompute_triggers.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS recommendation_recompute_trigger_runs" in sql
    for field_name in [
        "recommendation_recompute_trigger_run_id",
        "trigger_key",
        "as_of_time_utc",
        "checked_run_count",
        "triggered_run_count",
        "incident_event_keys_json",
        "source_recommendation_run_ids_json",
        "generated_recommendation_run_ids_json",
        "result_json",
    ]:
        assert field_name in sql
    assert "idx_recommendation_recompute_triggers_time" in sql
    assert "idx_recommendation_recompute_triggers_counts" in sql


def test_recommendation_prematch_pipeline_migration_adds_workflow_audit() -> None:
    sql = Path("db/migrations/0040_recommendation_prematch_pipeline_runs.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS recommendation_prematch_pipeline_runs" in sql
    for field_name in [
        "recommendation_prematch_pipeline_run_id",
        "run_key",
        "status",
        "dry_run",
        "as_of_time_utc",
        "window_start_utc",
        "window_end_utc",
        "mapped_incident_count",
        "stored_incident_count",
        "checked_run_count",
        "triggered_run_count",
        "generated_recommendation_run_ids_json",
        "prematch_report_key",
        "result_json",
    ]:
        assert field_name in sql
    assert "recommendation_prematch_pipeline_status_check" in sql
    assert "idx_recommendation_prematch_pipeline_runs_status_started" in sql
    assert "idx_recommendation_prematch_pipeline_runs_triggered" in sql


def test_recommendation_benchmark_migration_adds_report_history_storage() -> None:
    sql = Path("db/migrations/0041_recommendation_benchmark_runs.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS recommendation_benchmark_runs" in sql
    for field_name in [
        "recommendation_benchmark_run_id",
        "benchmark_key",
        "scenario_count",
        "completed_count",
        "failed_count",
        "as_of_times_json",
        "pass_types_json",
        "modes_json",
        "budgets_json",
        "global_best_selected_count",
        "core_replay_ready_count",
        "core_replay_total_run_count",
        "core_replay_total_settled_run_count",
        "final_hit_sample_size",
        "final_hit_count",
        "average_core_replay_roi",
        "history_comparison_json",
        "summary_json",
        "result_json",
    ]:
        assert field_name in sql
    assert "recommendation_benchmark_strategy_check" in sql
    assert "idx_recommendation_benchmark_runs_key_created" in sql
    assert "idx_recommendation_benchmark_runs_roi" in sql


def test_recommendation_successor_effective_index_migration_supports_leaf_metrics() -> None:
    sql = Path(
        "db/migrations/0042_recommendation_successor_effective_indexes.sql"
    ).read_text(encoding="utf-8")

    assert "idx_recommendation_runs_successor_source" in sql
    assert "internal_trace,successor_recompute,source_recommendation_run_id" in sql
    assert "status <> 'invalidated'" in sql


def test_recommendation_benchmark_strategy_pair_migration_adds_history_storage() -> None:
    sql = Path(
        "db/migrations/0043_recommendation_benchmark_strategy_pair_runs.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS recommendation_benchmark_strategy_pair_runs" in sql
    for field_name in [
        "recommendation_benchmark_strategy_pair_run_id",
        "pair_key",
        "baseline_strategy",
        "candidate_strategy",
        "baseline_benchmark_key",
        "candidate_benchmark_key",
        "baseline_benchmark_run_id",
        "candidate_benchmark_run_id",
        "comparison_key",
        "comparison_status",
        "average_core_replay_roi_delta",
        "final_hit_rate_delta",
        "core_replay_ready_ratio_delta",
        "matrix_match",
        "failed_checks_json",
        "summary_json",
        "result_json",
    ]:
        assert field_name in sql
    assert "recommendation_benchmark_strategy_pair_status_check" in sql
    assert "idx_recommendation_benchmark_strategy_pair_key_created" in sql
    assert "idx_recommendation_benchmark_strategy_pair_roi_delta" in sql


def test_recommendation_candidate_probability_basis_migration_adds_calibration_fields() -> None:
    sql = Path(
        "db/migrations/0045_recommendation_candidate_probability_basis.sql"
    ).read_text(encoding="utf-8")

    for field_name in [
        "model_probability",
        "calibrated_probability",
        "probability_source",
    ]:
        assert field_name in sql
    assert "recommendation_candidates_probability_source_check" in sql
    assert "recommendation_candidate_pool_items_probability_source_check" in sql
    assert "idx_recommendation_candidates_probability_source" in sql


def test_provider_sync_index_migration_contains_raw_payload_lookup_indexes() -> None:
    sql = Path("db/migrations/0006_provider_sync_indexes.sql").read_text(encoding="utf-8")

    assert "idx_raw_payload_entity_time" in sql
    assert "idx_raw_payload_request_hash" in sql
    assert "idx_provider_sync_runs_status_started" in sql


def test_provider_canonical_sync_index_migration_contains_mapping_lookup_indexes() -> None:
    sql = Path("db/migrations/0007_provider_canonical_sync_indexes.sql").read_text(encoding="utf-8")

    assert "idx_provider_entity_mappings_canonical" in sql
    assert "idx_fixtures_status_kickoff" in sql
    assert "idx_results_source" in sql


def test_odds_snapshot_provider_index_migration_contains_odds_lookup_indexes() -> None:
    sql = Path("db/migrations/0008_odds_snapshot_provider_indexes.sql").read_text(encoding="utf-8")

    assert "idx_odds_snapshots_provider_bookmaker_time" in sql
    assert "idx_odds_snapshots_payload" in sql


def test_odds_snapshot_idempotency_migration_dedupes_and_adds_unique_tick_index() -> None:
    sql = Path("db/migrations/0025_odds_snapshot_idempotency.sql").read_text(encoding="utf-8")

    assert "ranked_odds_snapshots" in sql
    assert "duplicate_rank > 1" in sql
    assert "idx_odds_snapshots_unique_market_tick" in sql
    assert "NULLS NOT DISTINCT" in sql
    for field_name in [
        "fixture_id",
        "provider",
        "bookmaker",
        "market_type",
        "line",
        "side",
        "outcome",
        "snapshot_time_utc",
    ]:
        assert field_name in sql


def test_availability_snapshot_migrations_contain_snapshot_tables_and_indexes() -> None:
    table_sql = Path("db/migrations/0009_fixture_availability_snapshots.sql").read_text(
        encoding="utf-8"
    )
    index_sql = Path("db/migrations/0010_availability_snapshot_provider_indexes.sql").read_text(
        encoding="utf-8"
    )

    for table_name in ["player_availability_snapshots", "lineup_snapshots"]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in table_sql

    for field_name in [
        "snapshot_time_utc",
        "payload_id",
        "source_confidence",
        "probability_start",
    ]:
        assert field_name in table_sql

    assert "idx_player_availability_payload" in index_sql
    assert "idx_lineup_snapshots_payload" in index_sql


def test_feature_snapshot_lookup_index_migration_contains_version_and_quality_indexes() -> None:
    sql = Path("db/migrations/0011_feature_snapshot_lookup_indexes.sql").read_text(encoding="utf-8")

    assert "idx_feature_snapshots_version_time" in sql
    assert "idx_feature_snapshots_quality" in sql


def test_prediction_job_runs_migration_contains_prematch_job_audit_table() -> None:
    sql = Path("db/migrations/0012_prediction_job_runs.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS prediction_job_runs" in sql
    for field_name in [
        "prediction_job_run_id",
        "job_type",
        "status",
        "dry_run",
        "fixture_count",
        "generated_count",
        "feature_snapshot_ids_json",
        "prediction_snapshot_ids_json",
        "score_grid_ids_json",
        "data_quality_scores_json",
        "skipped_fixture_ids_json",
        "warnings_json",
        "metadata_json",
    ]:
        assert field_name in sql


def test_parlay_lineage_migration_contains_model_and_settlement_fields() -> None:
    sql = Path("db/migrations/0013_parlay_model_lineage.sql").read_text(encoding="utf-8")

    for field_name in [
        "model_version",
        "prediction_snapshot_ids_json",
        "prediction_snapshot_id",
        "side",
        "gross_payout",
        "profit_loss",
        "settlement_detail_json",
    ]:
        assert field_name in sql

    assert "idx_parlay_recommendations_model_created" in sql
    assert "idx_parlay_atomic_bets_settlement" in sql


def test_market_prediction_parlay_index_migration_contains_candidate_indexes() -> None:
    sql = Path("db/migrations/0014_market_prediction_parlay_indexes.sql").read_text(
        encoding="utf-8"
    )

    assert "idx_market_predictions_snapshot_market" in sql
    assert "idx_market_predictions_fixture_outcome" in sql
    assert "idx_prediction_snapshots_model_time" in sql


def test_prematch_workflow_run_migration_contains_top_level_audit_table() -> None:
    sql = Path("db/migrations/0015_prematch_workflow_runs.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS prematch_workflow_runs" in sql
    for field_name in [
        "prematch_workflow_run_id",
        "prediction_job_run_id",
        "prediction_job_type",
        "prediction_fixture_count",
        "prediction_generated_count",
        "parlay_generated_count",
        "parlay_recommendation_ids_json",
        "warnings_json",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_prematch_workflow_runs_status_started" in sql


def test_provider_sync_workflow_migration_contains_orchestration_audit_table() -> None:
    sql = Path("db/migrations/0016_provider_sync_workflow_runs.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_sync_workflow_runs" in sql
    for field_name in [
        "provider_sync_workflow_run_id",
        "fixture_sync_run_id",
        "odds_sync_run_ids_json",
        "availability_sync_run_ids_json",
        "fixture_count",
        "odds_snapshot_count",
        "availability_snapshot_count",
        "raw_payload_ids_json",
        "canonical_fixture_ids_json",
        "prematch_workflow_run_id",
        "warnings_json",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_provider_sync_workflow_runs_status_started" in sql


def test_provider_sync_workflow_template_migration_contains_template_store() -> None:
    sql = Path("db/migrations/0021_provider_sync_workflow_templates.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS provider_sync_workflow_templates" in sql
    for field_name in [
        "provider_sync_workflow_template_id",
        "template_name",
        "fixture_sync_json",
        "odds_syncs_json",
        "availability_syncs_json",
        "run_conflict_detection",
        "conflict_observation_lookback_hours",
        "conflict_limit",
        "created_by",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_provider_sync_workflow_templates_updated" in sql


def test_provider_sync_template_ops_migration_contains_archive_and_approval_audit() -> None:
    sql = Path("db/migrations/0022_provider_sync_template_ops_and_approvals.sql").read_text(
        encoding="utf-8"
    )

    for field_name in [
        "archived_at",
        "archived_by",
        "archive_reason",
    ]:
        assert field_name in sql
    assert "CREATE TABLE IF NOT EXISTS provider_sync_workflow_operator_approvals" in sql
    for field_name in [
        "provider_sync_workflow_approval_id",
        "approval_type",
        "approval_status",
        "provider_sync_workflow_template_id",
        "provider_sync_workflow_run_id",
        "approved_by",
        "approved_at",
        "approval_note",
        "request_payload_json",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_provider_sync_workflow_approvals_approved" in sql


def test_provider_mapping_ops_index_migration_contains_review_indexes() -> None:
    sql = Path("db/migrations/0017_provider_mapping_ops_indexes.sql").read_text(encoding="utf-8")

    assert "idx_provider_entity_mappings_provider_type_updated" in sql
    assert "idx_provider_entity_mappings_canonical_updated" in sql


def test_provider_mapping_review_run_migration_contains_audit_table() -> None:
    sql = Path("db/migrations/0018_provider_mapping_review_runs.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_mapping_review_runs" in sql
    for field_name in [
        "provider_mapping_review_run_id",
        "low_confidence_threshold",
        "stale_after_days",
        "checked_mapping_count",
        "issue_count",
        "critical_count",
        "warning_count",
        "info_count",
        "issues_json",
        "requested_by",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_provider_mapping_review_runs_created" in sql
    assert "idx_provider_mapping_review_runs_scope" in sql


def test_provider_conflict_event_migration_contains_governance_tables() -> None:
    sql = Path("db/migrations/0019_provider_conflict_events.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_conflict_events" in sql
    for field_name in [
        "provider_conflict_event_id",
        "source_review_run_id",
        "conflict_type",
        "severity",
        "provider_names_json",
        "trusted_provider",
        "resolution_status",
        "data_quality_score_delta",
        "evidence_json",
    ]:
        assert field_name in sql
    assert "CREATE TABLE IF NOT EXISTS provider_trusted_priorities" in sql
    assert "idx_provider_conflict_events_status_created" in sql
    assert "idx_provider_trusted_priorities_capability_rank" in sql


def test_provider_observation_migration_contains_normalized_observation_table() -> None:
    sql = Path("db/migrations/0020_provider_observations.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS provider_observations" in sql
    for field_name in [
        "provider_observation_id",
        "provider_name",
        "capability",
        "canonical_entity_id",
        "field_name",
        "observed_value",
        "observed_at_utc",
        "payload_id",
        "metadata_json",
    ]:
        assert field_name in sql
    assert "idx_provider_observations_entity_field_time" in sql
    assert "idx_provider_observations_provider_capability_time" in sql
