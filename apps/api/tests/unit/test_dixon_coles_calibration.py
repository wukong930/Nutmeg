from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.accuracy import build_dixon_coles_validation_calibration_report
from nutmeg.domain.settlement import OneXTwoOutcome
from nutmeg.modeling import (
    DixonColesTrainingConfig,
    DixonColesTrainingMatch,
    build_dixon_coles_training_report,
)


def test_dixon_coles_validation_calibration_report_scores_1x2_validation_set() -> None:
    training_report = build_dixon_coles_training_report(
        _training_matches(),
        config=DixonColesTrainingConfig(
            as_of_time_utc=datetime(2026, 5, 6, 12, tzinfo=UTC),
            train_window_days=120,
            validation_window_days=30,
            rho_candidates=(-0.15, -0.05, 0.0, 0.05),
            min_training_matches=4,
        ),
    )

    calibration_report = build_dixon_coles_validation_calibration_report(
        _training_matches(),
        report=training_report,
        max_goals=8,
        bucket_size=0.10,
    )

    assert calibration_report.model_version == "dc-v1.5-candidate"
    assert calibration_report.market_type == "1x2"
    assert calibration_report.sample_size == 2
    assert calibration_report.observation_count == 6
    assert 0.0 <= calibration_report.brier_score <= 2.0
    assert 0.0 <= calibration_report.expected_calibration_error <= 1.0
    assert sum(bucket.sample_size for bucket in calibration_report.buckets) == 6
    assert {metric.actual_outcome for metric in calibration_report.match_metrics} == {
        OneXTwoOutcome.DRAW,
    }
    assert calibration_report.metrics_json["candidate_brier_score"] == (
        calibration_report.brier_score
    )
    assert calibration_report.calibration_json["calibration_status"] == (
        "validation_evidence_only"
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
