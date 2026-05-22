from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationBenchmarkOptions,
    RecommendationBenchmarkRunResult,
    RecommendationBenchmarkScheduleOptions,
    build_scheduled_benchmark_as_of_times,
    run_recommendation_benchmark_schedule,
)
from nutmeg.recommendations.benchmark_schedule import _options_from_args, _parse_args


def test_schedule_builds_daily_windows_oldest_to_newest() -> None:
    options = RecommendationBenchmarkScheduleOptions(
        schedule_name="daily-core",
        cadence="daily",
        run_at_utc=_dt(2026, 5, 10, 0),
        window_count=3,
    )

    as_of_times = build_scheduled_benchmark_as_of_times(options)

    assert as_of_times == (
        _dt(2026, 5, 8, 0),
        _dt(2026, 5, 9, 0),
        _dt(2026, 5, 10, 0),
    )


def test_schedule_builds_weekly_windows_oldest_to_newest() -> None:
    options = RecommendationBenchmarkScheduleOptions(
        cadence="weekly",
        run_at_utc=_dt(2026, 5, 10, 0),
        window_count=3,
    )

    as_of_times = build_scheduled_benchmark_as_of_times(options)

    assert as_of_times == (
        _dt(2026, 4, 26, 0),
        _dt(2026, 5, 3, 0),
        _dt(2026, 5, 10, 0),
    )


def test_schedule_once_uses_only_run_at_time() -> None:
    options = RecommendationBenchmarkScheduleOptions(
        cadence="once",
        run_at_utc=_dt(2026, 5, 10, 18),
        window_count=10,
    )

    assert build_scheduled_benchmark_as_of_times(options) == (_dt(2026, 5, 10, 18),)


def test_schedule_runner_passes_generated_windows_to_benchmark_runner() -> None:
    calls: list[RecommendationBenchmarkOptions] = []

    def benchmark_runner(
        database: object,
        *,
        options: RecommendationBenchmarkOptions,
    ) -> RecommendationBenchmarkRunResult:
        calls.append(options)
        return RecommendationBenchmarkRunResult(
            benchmark_key="recommendation_benchmark:scheduled",
            dry_run=options.dry_run,
            strategy=options.strategy,
            scenario_count=4,
            completed_count=3,
            failed_count=1,
            warnings=["core_replay:no_settled_runs"],
            summary_json={
                "history_status": "baseline",
                "scenario_count": 4,
                "completed_count": 3,
                "failed_count": 1,
            },
        )

    result = run_recommendation_benchmark_schedule(
        FakeDatabase(),
        options=RecommendationBenchmarkScheduleOptions(
            schedule_name="daily-core",
            cadence="daily",
            run_at_utc=_dt(2026, 5, 10, 0),
            window_count=2,
            lookback_hours=48,
            pass_types=("2x1", "6x1"),
            modes=("single", "multiple"),
            max_budgets=(10.0, 30.0),
            run_prematch_pipeline=True,
            run_core_replay=False,
            dry_run=False,
            save_report=True,
            save_pipeline_audit=True,
            continue_on_error=False,
        ),
        benchmark_runner=benchmark_runner,
    )

    assert len(calls) == 1
    benchmark_options = calls[0]
    assert benchmark_options.as_of_times_utc == (
        _dt(2026, 5, 9, 0),
        _dt(2026, 5, 10, 0),
    )
    assert benchmark_options.lookback_hours == 48
    assert benchmark_options.pass_types == ("2x1", "6x1")
    assert benchmark_options.modes == ("single", "multiple")
    assert benchmark_options.max_budgets == (10.0, 30.0)
    assert benchmark_options.run_prematch_pipeline is True
    assert benchmark_options.run_core_replay is False
    assert benchmark_options.run_successor_chain_evaluation is True
    assert benchmark_options.dry_run is False
    assert benchmark_options.save_report is True
    assert benchmark_options.save_pipeline_audit is True
    assert benchmark_options.continue_on_error is False
    assert result.schedule_key == "recommendation_benchmark_schedule:daily-core:daily"
    assert result.summary_json["benchmark_key"] == "recommendation_benchmark:scheduled"
    assert result.summary_json["benchmark_scenario_count"] == 4
    assert result.summary_json["benchmark_failed_count"] == 1
    assert result.summary_json["history_status"] == "baseline"
    assert result.warnings == ["core_replay:no_settled_runs"]


def test_schedule_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--schedule-name",
            "weekly-core",
            "--cadence",
            "weekly",
            "--run-at-utc",
            "2026-05-10T00:00:00Z",
            "--window-count",
            "4",
            "--lookback-hours",
            "72",
            "--pass-types",
            "2x1,8x1",
            "--modes",
            "single,multiple",
            "--budgets",
            "10,50",
            "--include-prematch-pipeline",
            "--skip-core-replay",
            "--skip-chain-integrity",
            "--commit",
            "--save-report",
            "--save-audit",
            "--stop-on-error",
            "--no-require-odds",
        ]
    )

    options = _options_from_args(args)

    assert options.schedule_name == "weekly-core"
    assert options.cadence == "weekly"
    assert options.run_at_utc == _dt(2026, 5, 10, 0)
    assert options.window_count == 4
    assert options.lookback_hours == 72
    assert options.pass_types == ("2x1", "8x1")
    assert options.modes == ("single", "multiple")
    assert options.max_budgets == (10.0, 50.0)
    assert options.run_prematch_pipeline is True
    assert options.run_core_replay is False
    assert options.run_chain_integrity is False
    assert options.run_successor_chain_evaluation is False
    assert options.dry_run is False
    assert options.save_report is True
    assert options.save_pipeline_audit is True
    assert options.continue_on_error is False
    assert options.require_odds is False


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
