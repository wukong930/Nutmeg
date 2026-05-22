from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.accuracy import (
    backtest_run_from_dixon_coles_training_report,
    calibration_json_from_dixon_coles_training_report,
    compare_dixon_coles_training_report_to_baseline,
    metrics_json_from_dixon_coles_training_report,
    model_metrics_from_dixon_coles_training_report,
    persist_dixon_coles_training_backtest,
)
from nutmeg.domain.accuracy import (
    BacktestRunSchema,
    ModelComparisonStub,
    ModelVersionMetrics,
    StoredBacktestRun,
    StoredModelComparisonReport,
)
from nutmeg.modeling import (
    DixonColesTrainingConfig,
    DixonColesTrainingMatch,
    build_dixon_coles_training_report,
)


class FakeBacktestWriteRepository:
    def __init__(self) -> None:
        self.saved_backtests: list[
            tuple[BacktestRunSchema, dict[str, object], dict[str, object], str | None]
        ] = []
        self.saved_comparisons: list[ModelComparisonStub] = []

    def save_backtest_run(
        self,
        backtest_run: BacktestRunSchema,
        *,
        metrics_json: dict[str, object],
        calibration_json: dict[str, object] | None = None,
        report_uri: str | None = None,
    ) -> StoredBacktestRun:
        calibration = dict(calibration_json or {})
        self.saved_backtests.append((backtest_run, metrics_json, calibration, report_uri))
        return StoredBacktestRun(
            backtest_run_id=101,
            backtest_run=backtest_run,
            metrics_json=metrics_json,
            calibration_json=calibration,
            report_uri=report_uri,
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )

    def save_model_comparison_report(
        self,
        comparison: ModelComparisonStub,
    ) -> StoredModelComparisonReport:
        self.saved_comparisons.append(comparison)
        return StoredModelComparisonReport(
            comparison_report_id=202,
            comparison=comparison,
            created_at=datetime(2026, 5, 7, 12, 5, tzinfo=UTC),
        )


def test_dixon_coles_training_report_maps_to_walk_forward_backtest_schema() -> None:
    report = _training_report()

    backtest_run = backtest_run_from_dixon_coles_training_report(report)

    assert backtest_run.mode == "walk_forward"
    assert backtest_run.model_version == "dc-v1.5-candidate"
    assert backtest_run.train_window is not None
    assert backtest_run.train_window.start_date.isoformat() == "2026-01-06"
    assert backtest_run.train_window.end_date.isoformat() == "2026-04-05"
    assert backtest_run.validation_window is not None
    assert backtest_run.validation_window.start_date.isoformat() == "2026-04-06"
    assert backtest_run.test_window == backtest_run.validation_window
    assert backtest_run.competitions == ["EPL"]
    assert backtest_run.notes_json["validation_used_as_test_window"] is True
    assert backtest_run.notes_json["selected_rho"] == report.selected_rho


def test_dixon_coles_training_report_builds_persistable_metrics_payloads() -> None:
    report = _training_report()

    metrics_json = metrics_json_from_dixon_coles_training_report(report)
    calibration_json = calibration_json_from_dixon_coles_training_report(report)
    model_metrics = model_metrics_from_dixon_coles_training_report(
        report,
        brier_score=0.22,
        ece=0.04,
    )

    assert metrics_json["model_family"] == "dixon_coles"
    assert metrics_json["metric_basis"] == (
        "score_probability_negative_weighted_log_likelihood"
    )
    assert "fitted_parameters" in metrics_json
    assert calibration_json["calibration_status"] == "not_fitted"
    assert model_metrics.model_version == "dc-v1.5-candidate"
    assert model_metrics.sample_size == report.validation_sample_size
    assert model_metrics.log_loss == report.validation_negative_weighted_log_likelihood
    assert model_metrics.brier_score == 0.22
    assert model_metrics.metrics_json["brier_score_available"] is True


def test_dixon_coles_comparison_requires_review_until_brier_and_calibration_exist() -> None:
    report = _training_report()

    comparison = compare_dixon_coles_training_report_to_baseline(
        report,
        baseline_metrics=ModelVersionMetrics(
            model_version="poisson-m1.1.0",
            sample_size=report.validation_sample_size,
            log_loss=report.validation_negative_weighted_log_likelihood + 0.2,
            brier_score=0.25,
        ),
    )

    assert comparison.decision_stub == "needs_review"
    assert "candidate_log_loss_not_worse" in comparison.reasons
    assert "candidate_brier_unavailable" in comparison.reasons
    assert "candidate_calibration_unavailable" in comparison.reasons


def test_persist_dixon_coles_training_backtest_saves_backtest_and_comparison() -> None:
    repository = FakeBacktestWriteRepository()
    report = _training_report()

    stored = persist_dixon_coles_training_backtest(
        repository,
        report=report,
        baseline_metrics=ModelVersionMetrics(
            model_version="poisson-m1.1.0",
            sample_size=report.validation_sample_size,
            log_loss=report.validation_negative_weighted_log_likelihood + 0.1,
            brier_score=0.24,
        ),
        candidate_brier_score=0.23,
        candidate_ece=0.05,
        report_uri="reports/backtests/dc-v1.5-candidate.json",
    )

    assert stored.backtest_run.backtest_run_id == 101
    assert stored.model_comparison_report.comparison_report_id == 202
    assert repository.saved_backtests[0][0].model_version == "dc-v1.5-candidate"
    assert repository.saved_backtests[0][1]["selected_rho"] == report.selected_rho
    assert repository.saved_backtests[0][2]["calibration_required_before_promotion"] is True
    assert repository.saved_backtests[0][3] == "reports/backtests/dc-v1.5-candidate.json"
    assert repository.saved_comparisons[0].candidate_model_version == "dc-v1.5-candidate"


def test_persist_dixon_coles_training_backtest_accepts_calibration_evidence() -> None:
    repository = FakeBacktestWriteRepository()
    report = _training_report()

    persist_dixon_coles_training_backtest(
        repository,
        report=report,
        baseline_metrics=ModelVersionMetrics(
            model_version="poisson-m1.1.0",
            sample_size=report.validation_sample_size,
            log_loss=report.validation_negative_weighted_log_likelihood + 0.1,
            brier_score=0.24,
        ),
        candidate_brier_score=0.23,
        candidate_ece=0.05,
        extra_metrics_json={"candidate_brier_score_source": "validation_fixture"},
        calibration_json={
            "calibration_status": "validation_evidence_only",
            "sample_size": report.validation_sample_size,
        },
    )

    assert repository.saved_backtests[0][1]["candidate_brier_score_source"] == (
        "validation_fixture"
    )
    assert repository.saved_backtests[0][2]["calibration_status"] == (
        "validation_evidence_only"
    )


def _training_report():
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    return build_dixon_coles_training_report(
        _training_matches(),
        config=DixonColesTrainingConfig(
            as_of_time_utc=as_of_time,
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            min_training_matches=4,
        ),
    )


def _training_matches() -> list[DixonColesTrainingMatch]:
    return [
        _match("train_001", "ars", "liv", 0, 0, datetime(2026, 2, 1, 12, tzinfo=UTC)),
        _match("train_002", "city", "che", 1, 1, datetime(2026, 2, 8, 12, tzinfo=UTC)),
        _match("train_003", "ars", "city", 1, 0, datetime(2026, 2, 15, 12, tzinfo=UTC)),
        _match("train_004", "liv", "che", 0, 1, datetime(2026, 2, 22, 12, tzinfo=UTC)),
        _match("train_005", "ars", "che", 1, 1, datetime(2026, 3, 1, 12, tzinfo=UTC)),
        _match("train_006", "city", "liv", 0, 0, datetime(2026, 3, 8, 12, tzinfo=UTC)),
        _match("valid_001", "ars", "liv", 0, 0, datetime(2026, 4, 20, 12, tzinfo=UTC)),
        _match("valid_002", "city", "che", 1, 1, datetime(2026, 4, 27, 12, tzinfo=UTC)),
    ]


def _match(
    fixture_id: str,
    home_team_id: str,
    away_team_id: str,
    home_goals: int,
    away_goals: int,
    kickoff_time_utc: datetime,
) -> DixonColesTrainingMatch:
    return DixonColesTrainingMatch(
        fixture_id=fixture_id,
        competition_id="EPL",
        kickoff_time_utc=kickoff_time_utc,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_goals=home_goals,
        away_goals=away_goals,
    )
