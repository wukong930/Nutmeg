from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseReadError, DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationBenchmarkPreflightOptions,
    run_recommendation_benchmark_preflight,
)
from nutmeg.recommendations.benchmark_preflight import (
    BENCHMARK_HISTORY_COUNT_QUERY,
    DATABASE_CONNECTIVITY_QUERY,
    TABLE_EXISTS_QUERY,
    _options_from_args,
    _parse_args,
)


def test_benchmark_preflight_passes_when_database_tables_and_history_exist() -> None:
    database = FakePreflightDatabase(
        existing_tables={"recommendation_benchmark_runs", "recommendation_runs"},
        history_count=3,
    )

    result = run_recommendation_benchmark_preflight(
        database,
        options=RecommendationBenchmarkPreflightOptions(
            required_tables=("recommendation_benchmark_runs", "recommendation_runs"),
            min_benchmark_history_count=1,
        ),
    )

    assert result.ready is True
    assert result.status == "ready"
    assert result.warnings == []
    assert result.summary_json["failed_check_count"] == 0
    assert result.summary_json["warning_check_count"] == 0
    assert [call[0] for call in database.fetch_all_calls] == [
        DATABASE_CONNECTIVITY_QUERY
    ]
    assert [call[0] for call in database.fetch_one_calls] == [
        TABLE_EXISTS_QUERY,
        TABLE_EXISTS_QUERY,
        BENCHMARK_HISTORY_COUNT_QUERY,
    ]


def test_benchmark_preflight_warns_when_history_is_empty_for_first_baseline() -> None:
    result = run_recommendation_benchmark_preflight(
        FakePreflightDatabase(
            existing_tables={"recommendation_benchmark_runs"},
            history_count=0,
        ),
        options=RecommendationBenchmarkPreflightOptions(
            required_tables=("recommendation_benchmark_runs",),
            min_benchmark_history_count=0,
        ),
    )

    assert result.ready is True
    assert result.status == "warning"
    assert result.summary_json["warning_checks"] == ["benchmark_history"]
    assert result.warnings == ["benchmark_preflight:warning:benchmark_history"]


def test_benchmark_preflight_blocks_when_required_table_is_missing() -> None:
    result = run_recommendation_benchmark_preflight(
        FakePreflightDatabase(
            existing_tables={"recommendation_benchmark_runs"},
            history_count=1,
        ),
        options=RecommendationBenchmarkPreflightOptions(
            required_tables=("recommendation_benchmark_runs", "recommendation_runs"),
        ),
    )

    assert result.ready is False
    assert result.status == "blocked"
    assert result.summary_json["failed_checks"] == ["required_table:recommendation_runs"]
    assert result.warnings == [
        "benchmark_preflight:failed:required_table:recommendation_runs"
    ]


def test_benchmark_preflight_blocks_cleanly_when_database_connection_fails() -> None:
    result = run_recommendation_benchmark_preflight(
        FailingPreflightDatabase(),
        options=RecommendationBenchmarkPreflightOptions(),
    )

    assert result.ready is False
    assert result.status == "blocked"
    assert result.checks[0].name == "database_connectivity"
    assert result.checks[0].status == "failed"
    assert "role nutmeg does not exist" in result.checks[0].metadata_json["error"]


def test_benchmark_preflight_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--required-tables",
            "recommendation_benchmark_runs,recommendation_runs",
            "--min-benchmark-history-count",
            "2",
            "--no-empty-history-warning",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.required_tables == (
        "recommendation_benchmark_runs",
        "recommendation_runs",
    )
    assert options.min_benchmark_history_count == 2
    assert options.warn_on_empty_history is False


class FakePreflightDatabase:
    def __init__(self, *, existing_tables: set[str], history_count: int) -> None:
        self.existing_tables = existing_tables
        self.history_count = history_count
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        assert query == DATABASE_CONNECTIVITY_QUERY
        return [{"ok": 1}]

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == TABLE_EXISTS_QUERY:
            relation_name = str(params["relation_name"])
            table_name = relation_name.removeprefix("public.")
            return {"relation_name": relation_name if table_name in self.existing_tables else None}
        if query == BENCHMARK_HISTORY_COUNT_QUERY:
            return {
                "run_count": self.history_count,
                "latest_created_at": (
                    datetime(2026, 5, 12, 0, tzinfo=UTC)
                    if self.history_count
                    else None
                ),
            }
        raise AssertionError(f"unexpected query: {query}")


class FailingPreflightDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise DatabaseReadError("database read failed") from RuntimeError(
            "role nutmeg does not exist"
        )

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")
