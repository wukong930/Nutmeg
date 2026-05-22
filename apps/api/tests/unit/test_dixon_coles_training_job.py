from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.accuracy.calibration_evidence import CALIBRATION_BUCKET_EVIDENCE_QUERY
from nutmeg.accuracy.dixon_coles_job import (
    LIST_DIXON_COLES_TRAINING_MATCHES_QUERY,
    UPSERT_DIXON_COLES_JOB_BASELINE_MODEL_VERSION_QUERY,
    UPSERT_DIXON_COLES_JOB_MODEL_VERSION_QUERY,
    DixonColesTrainingBacktestJobOptions,
    list_dixon_coles_training_matches,
    run_dixon_coles_training_backtest_job,
)
from nutmeg.accuracy.postgres_write_repository import (
    INSERT_BACKTEST_RUN_QUERY,
    INSERT_MODEL_COMPARISON_REPORT_QUERY,
)
from nutmeg.accuracy.promotion_evidence import (
    HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
    PARLAY_SIMULATION_EVIDENCE_QUERY,
    UPSET_PRECISION_EVIDENCE_QUERY,
)
from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.model_governance.promotion_repository import INSERT_MODEL_PROMOTION_REVIEW_QUERY


class FakeDixonColesTrainingDatabase:
    def __init__(
        self,
        *,
        rows: Sequence[DatabaseRow],
        calibration_rows: Sequence[DatabaseRow] = (),
    ) -> None:
        self.rows = list(rows)
        self.calibration_rows = list(calibration_rows)
        self.promotion_rows_by_query: dict[str, list[DatabaseRow]] = {}
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == CALIBRATION_BUCKET_EVIDENCE_QUERY:
            return self.calibration_rows
        if query in {
            UPSET_PRECISION_EVIDENCE_QUERY,
            HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
            PARLAY_SIMULATION_EVIDENCE_QUERY,
        }:
            return self.promotion_rows_by_query.get(query, [])
        return self.rows

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == UPSERT_DIXON_COLES_JOB_MODEL_VERSION_QUERY:
            return {"model_version": params["model_version"]}
        if query == UPSERT_DIXON_COLES_JOB_BASELINE_MODEL_VERSION_QUERY:
            return {"model_version": params["model_version"]}
        if query == INSERT_BACKTEST_RUN_QUERY:
            return {
                "backtest_run_id": 71,
                "created_at": datetime(2026, 5, 6, 12, 30, tzinfo=UTC),
            }
        if query == INSERT_MODEL_COMPARISON_REPORT_QUERY:
            return {
                "comparison_report_id": 81,
                "created_at": datetime(2026, 5, 6, 12, 31, tzinfo=UTC),
            }
        if query == INSERT_MODEL_PROMOTION_REVIEW_QUERY:
            return {
                "model_promotion_review_id": 91,
                "created_at": datetime(2026, 5, 6, 12, 32, tzinfo=UTC),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_training_match_reader_uses_as_of_safe_result_query() -> None:
    database = FakeDixonColesTrainingDatabase(rows=[_row("train_001", "ars", "liv", 1, 0)])

    matches = list_dixon_coles_training_matches(
        database,
        as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
        competition_id="EPL",
        limit=50,
    )

    query, params = database.fetch_all_calls[0]
    assert query == LIST_DIXON_COLES_TRAINING_MATCHES_QUERY
    assert "COALESCE(r.settled_at, f.kickoff_time_utc) <= %(as_of_time_utc)s" in query
    assert "f.kickoff_time_utc < %(as_of_time_utc)s" in query
    assert params["competition_id"] == "EPL"
    assert params["limit"] == 50
    assert matches[0].fixture_id == "train_001"
    assert matches[0].home_goals == 1
    assert matches[0].kickoff_time_utc.tzinfo is not None


def test_dixon_coles_training_backtest_job_dry_run_does_not_persist() -> None:
    database = FakeDixonColesTrainingDatabase(rows=_training_rows())

    result = run_dixon_coles_training_backtest_job(
        database,
        options=DixonColesTrainingBacktestJobOptions(
            as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            dry_run=True,
        ),
    )

    assert database.fetch_one_calls == []
    assert result.dry_run is True
    assert result.fixture_count == 8
    assert result.backtest_run_id is None
    assert result.model_comparison_report_id is None
    assert result.model_promotion_review_id is None
    assert result.candidate_model_version == "dc-v1.5-candidate"
    assert result.train_sample_size == 6
    assert result.validation_sample_size == 2
    assert result.candidate_brier_score is not None
    assert result.candidate_ece is not None
    assert result.baseline_ece is None
    assert result.calibration_evidence_json["sample_size"] == 2
    assert result.model_comparison_decision == "needs_review"
    assert result.model_promotion_decision == "keep_experiment"
    assert result.model_promotion_next_status == "experiment"
    assert "candidate_brier_unavailable" not in result.warnings
    assert "candidate_calibration_unavailable" not in result.warnings
    assert "baseline_calibration_unavailable" in result.warnings
    assert "upset_precision_evidence_unavailable" in result.model_promotion_reasons
    assert result.rollback_should_rollback is False


def test_dixon_coles_training_backtest_job_persists_promotion_review() -> None:
    database = FakeDixonColesTrainingDatabase(rows=_training_rows())

    result = run_dixon_coles_training_backtest_job(
        database,
        options=DixonColesTrainingBacktestJobOptions(
            as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            baseline_log_loss=5.0,
            baseline_brier_score=0.25,
            baseline_ece=0.10,
            candidate_brier_score=0.20,
            candidate_ece=0.04,
            promotion_minimum_sample_size=2,
            core_market_improvement=True,
            upset_precision_at_k_delta=0.0,
            handicap_performance_delta=0.0,
            dry_run=False,
        ),
    )

    queries = [query for query, _params in database.fetch_one_calls]
    assert queries == [
        UPSERT_DIXON_COLES_JOB_MODEL_VERSION_QUERY,
        UPSERT_DIXON_COLES_JOB_BASELINE_MODEL_VERSION_QUERY,
        INSERT_BACKTEST_RUN_QUERY,
        INSERT_MODEL_COMPARISON_REPORT_QUERY,
        INSERT_MODEL_PROMOTION_REVIEW_QUERY,
    ]
    assert result.dry_run is False
    assert result.backtest_run_id == 71
    assert result.model_comparison_report_id == 81
    assert result.model_promotion_review_id == 91
    assert result.model_promotion_decision == "shadow_candidate"
    assert result.model_promotion_next_status == "shadow"
    assert result.model_promotion_reasons == ["candidate_passed_first_promotion_gate"]
    assert result.report.validation_sample_size == 2
    assert result.candidate_brier_score == 0.20
    assert result.candidate_ece == 0.04
    assert result.calibration_evidence_json["calibration_status"] == (
        "validation_evidence_only"
    )


def test_dixon_coles_training_backtest_job_uses_stored_baseline_calibration_evidence() -> None:
    database = FakeDixonColesTrainingDatabase(
        rows=_training_rows(),
        calibration_rows=[
            {
                "model_version": "poisson-m1.1.0",
                "market_type": "1x2",
                "outcome": "home_win",
                "competition_id": "EPL",
                "bucket_start": 0.4,
                "bucket_end": 0.5,
                "sample_size": 10,
                "predicted_probability_sum": 4.0,
                "actual_count": 5,
            }
        ],
    )

    result = run_dixon_coles_training_backtest_job(
        database,
        options=DixonColesTrainingBacktestJobOptions(
            as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            baseline_log_loss=5.0,
            baseline_brier_score=0.25,
            candidate_brier_score=0.20,
            candidate_ece=0.04,
            promotion_minimum_sample_size=2,
            core_market_improvement=True,
            upset_precision_at_k_delta=0.0,
            handicap_performance_delta=0.0,
            dry_run=True,
        ),
    )

    assert database.fetch_all_calls[1] == (
        CALIBRATION_BUCKET_EVIDENCE_QUERY,
        {
            "model_version": "poisson-m1.1.0",
            "market_type": "1x2",
            "competition_id": None,
        },
    )
    assert result.baseline_ece == pytest.approx(0.10)
    assert result.baseline_calibration_evidence_json["ece_source"] == (
        "stored_calibration_buckets"
    )
    assert "baseline_calibration_unavailable" not in result.warnings
    assert result.model_promotion_decision == "shadow_candidate"


def test_dixon_coles_training_backtest_job_uses_stored_promotion_evidence() -> None:
    database = FakeDixonColesTrainingDatabase(rows=_training_rows())
    database.promotion_rows_by_query = {
        UPSET_PRECISION_EVIDENCE_QUERY: [
            {
                "upset_alert_id": 1,
                "fixture_id": "valid_001",
                "upset_type": "draw_overlooked",
                "target_market_type": "1x2",
                "target_line": None,
                "target_outcome": "draw",
                "upset_score": 0.8,
                "home_goals": 0,
                "away_goals": 0,
            }
        ],
        HANDICAP_PERFORMANCE_EVIDENCE_QUERY: [
            {
                "fixture_id": "valid_001",
                "market_type": "cn_handicap_1x2",
                "line": -1,
                "side": None,
                "outcome": "handicap_away_win",
                "probability": 0.7,
                "home_goals": 0,
                "away_goals": 0,
            }
        ],
    }

    result = run_dixon_coles_training_backtest_job(
        database,
        options=DixonColesTrainingBacktestJobOptions(
            as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            baseline_log_loss=5.0,
            baseline_brier_score=0.25,
            baseline_ece=0.10,
            candidate_brier_score=0.20,
            candidate_ece=0.04,
            promotion_minimum_sample_size=2,
            core_market_improvement=True,
            dry_run=True,
        ),
    )

    assert "upset_precision_evidence_unavailable" not in result.model_promotion_reasons
    assert "handicap_performance_evidence_unavailable" not in result.model_promotion_reasons
    assert result.model_promotion_decision == "shadow_candidate"
    assert result.promotion_evidence_json["candidate_upset_precision"]["hit_count"] == 1
    assert result.promotion_evidence_json["candidate_handicap_performance"][
        "correct_count"
    ] == 1


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
    kickoff_time_utc: datetime | None = None,
) -> DatabaseRow:
    return {
        "fixture_id": fixture_id,
        "competition_id": "EPL",
        "kickoff_time_utc": kickoff_time_utc or "2026-02-01T12:00:00+00:00",
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
    }
