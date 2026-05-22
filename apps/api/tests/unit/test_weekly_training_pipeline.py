from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.accuracy.calibration_evidence import CALIBRATION_BUCKET_EVIDENCE_QUERY
from nutmeg.accuracy.dixon_coles_job import DixonColesTrainingBacktestJobOptions
from nutmeg.accuracy.promotion_evidence import (
    HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
    PARLAY_SIMULATION_EVIDENCE_QUERY,
    UPSET_PRECISION_EVIDENCE_QUERY,
)
from nutmeg.accuracy.weekly_training import (
    WeeklyDixonColesTrainingPipelineOptions,
    build_weekly_training_pipeline_plan,
    run_weekly_dixon_coles_training_pipeline,
    weekly_training_plan_metadata,
)
from nutmeg.database import DatabaseRow


def test_weekly_training_pipeline_plan_freezes_windows_and_safety_notes() -> None:
    options = _weekly_options()

    plan = build_weekly_training_pipeline_plan(options)

    assert plan.cadence == "weekly"
    assert plan.scheduler_status == "operator_controlled_stub"
    assert plan.run_label == "weekly-epl-dc"
    assert plan.scheduled_for_utc == datetime(2026, 5, 8, 2, 0, tzinfo=UTC)
    assert plan.freeze_as_of_time_utc == datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    assert plan.train_start_utc.isoformat() == "2026-01-06T12:00:00+00:00"
    assert plan.validation_start_utc.isoformat() == "2026-04-06T12:00:00+00:00"
    assert plan.candidate_model_version == "dc-v1.5-candidate"
    assert "no_system_cron_installed_by_this_plan" in plan.safety_notes
    assert "promotion_review_artifact" in plan.stages


def test_weekly_training_metadata_is_audit_ready() -> None:
    metadata = weekly_training_plan_metadata(_weekly_options())

    assert metadata["pipeline"] == "weekly_dixon_coles_training"
    plan = metadata["weekly_training_plan"]
    assert isinstance(plan, dict)
    assert plan["run_label"] == "weekly-epl-dc"
    assert plan["dry_run"] is True
    assert plan["scheduler_status"] == "operator_controlled_stub"


def test_weekly_training_pipeline_runs_existing_dixon_coles_job() -> None:
    database = FakeWeeklyTrainingDatabase(rows=_training_rows())

    result = run_weekly_dixon_coles_training_pipeline(
        database,
        options=_weekly_options(),
    )

    assert result.status == "completed_with_review_artifacts"
    assert result.plan.run_label == "weekly-epl-dc"
    assert result.training_result.dry_run is True
    assert result.training_result.fixture_count == 8
    assert result.training_result.backtest_run_id is None
    assert len(database.fetch_all_calls) == 8
    assert database.fetch_all_calls[1][0] == CALIBRATION_BUCKET_EVIDENCE_QUERY
    assert database.fetch_all_calls[2][0] == UPSET_PRECISION_EVIDENCE_QUERY
    assert database.fetch_all_calls[4][0] == HANDICAP_PERFORMANCE_EVIDENCE_QUERY
    assert database.fetch_all_calls[6][0] == PARLAY_SIMULATION_EVIDENCE_QUERY
    assert database.fetch_one_calls == []


class FakeWeeklyTrainingDatabase:
    def __init__(self, *, rows: list[DatabaseRow]) -> None:
        self.rows = rows
        self.fetch_all_calls: list[tuple[str, object]] = []
        self.fetch_one_calls: list[tuple[str, object]] = []

    def fetch_all(self, query: str, params: object) -> list[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == CALIBRATION_BUCKET_EVIDENCE_QUERY:
            return []
        if query in {
            UPSET_PRECISION_EVIDENCE_QUERY,
            HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
            PARLAY_SIMULATION_EVIDENCE_QUERY,
        }:
            return []
        return self.rows

    def fetch_one(self, query: str, params: object) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return None


def _weekly_options() -> WeeklyDixonColesTrainingPipelineOptions:
    return WeeklyDixonColesTrainingPipelineOptions(
        training_options=DixonColesTrainingBacktestJobOptions(
            as_of_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            dry_run=True,
        ),
        scheduled_for_utc=datetime(2026, 5, 8, 2, 0, tzinfo=UTC),
        run_label="weekly-epl-dc",
    )


def _training_rows() -> list[DatabaseRow]:
    return [
        _row("train_001", "ars", "liv", 0, 0, datetime(2026, 2, 1, 12, tzinfo=UTC)),
        _row("train_002", "city", "che", 1, 1, datetime(2026, 2, 8, 12, tzinfo=UTC)),
        _row("train_003", "ars", "city", 1, 0, datetime(2026, 2, 15, 12, tzinfo=UTC)),
        _row("train_004", "liv", "che", 0, 1, datetime(2026, 2, 22, 12, tzinfo=UTC)),
        _row("train_005", "ars", "che", 1, 1, datetime(2026, 3, 1, 12, tzinfo=UTC)),
        _row("train_006", "city", "liv", 0, 0, datetime(2026, 3, 8, 12, tzinfo=UTC)),
        _row("valid_001", "ars", "liv", 0, 0, datetime(2026, 4, 20, 12, tzinfo=UTC)),
        _row("valid_002", "city", "che", 1, 1, datetime(2026, 4, 27, 12, tzinfo=UTC)),
    ]


def _row(
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    home_goals: int,
    away_goals: int,
    kickoff_time_utc: datetime,
) -> DatabaseRow:
    return {
        "fixture_id": fixture_id,
        "competition_id": "EPL",
        "kickoff_time_utc": kickoff_time_utc,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
    }
