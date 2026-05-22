from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.modeling import (
    DixonColesTrainingConfig,
    DixonColesTrainingMatch,
    build_dixon_coles_training_report,
    estimate_dixon_coles_lambdas_for_match,
    fit_dixon_coles_attack_defense_parameters,
    negative_weighted_log_likelihood,
)


def test_dixon_coles_training_report_freezes_window_and_selects_rho() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    config = DixonColesTrainingConfig(
        as_of_time_utc=as_of_time,
        train_window_days=120,
        validation_window_days=30,
        rho_candidates=(-0.15, -0.05, 0.0, 0.05),
        min_training_matches=4,
    )

    report = build_dixon_coles_training_report(_training_matches(), config=config)

    assert report.model_version == "dc-v1.5-candidate"
    assert report.train_sample_size == 6
    assert report.validation_sample_size == 2
    assert report.selected_rho < 0
    assert report.score_grid_regression_passed is True
    assert report.competition_ids == ["EPL"]
    assert "validation_sample_size_below_training_minimum" in report.warnings
    assert report.metrics_json["selected_rho"] == report.selected_rho
    assert report.metrics_json["score_grid_regression_passed"] is True


def test_negative_weighted_log_likelihood_prefers_low_score_rho_for_low_score_sample() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    config = DixonColesTrainingConfig(
        as_of_time_utc=as_of_time,
        train_window_days=120,
        validation_window_days=30,
        min_training_matches=4,
    )
    train_matches = [
        match
        for match in _training_matches()
        if match.kickoff_time_utc < datetime(2026, 4, 6, 12, 0, tzinfo=UTC)
    ]
    parameters = fit_dixon_coles_attack_defense_parameters(
        train_matches,
        config=config,
    )

    negative_rho_loss = negative_weighted_log_likelihood(
        train_matches,
        parameters=parameters,
        rho=-0.10,
        as_of_time_utc=as_of_time,
        time_decay_xi=config.time_decay_xi,
    )
    positive_rho_loss = negative_weighted_log_likelihood(
        train_matches,
        parameters=parameters,
        rho=0.10,
        as_of_time_utc=as_of_time,
        time_decay_xi=config.time_decay_xi,
    )

    assert negative_rho_loss < positive_rho_loss


def test_dixon_coles_training_estimate_keeps_version_and_decay_metadata() -> None:
    as_of_time = datetime(2026, 5, 6, 12, 0, tzinfo=UTC)
    config = DixonColesTrainingConfig(
        as_of_time_utc=as_of_time,
        train_window_days=120,
        validation_window_days=30,
        min_training_matches=4,
    )
    train_matches = [
        match
        for match in _training_matches()
        if match.kickoff_time_utc < datetime(2026, 4, 6, 12, 0, tzinfo=UTC)
    ]
    parameters = fit_dixon_coles_attack_defense_parameters(
        train_matches,
        config=config,
    )

    estimate = estimate_dixon_coles_lambdas_for_match(
        train_matches[0],
        parameters=parameters,
        rho=-0.05,
        as_of_time_utc=as_of_time,
        time_decay_xi=config.time_decay_xi,
        model_version="dc-v1.5-candidate",
        feature_version="features-training",
        calibration_version="calibration-training",
    )

    assert estimate.model_family == "dixon_coles"
    assert estimate.model_version == "dc-v1.5-candidate"
    assert estimate.rho == -0.05
    assert estimate.time_decay_weight is not None
    assert estimate.metadata_json["training_method"] == (
        "weighted_attack_defense_grid_search_v1"
    )


def test_dixon_coles_training_report_rejects_missing_validation_window() -> None:
    config = DixonColesTrainingConfig(
        as_of_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        train_window_days=120,
        validation_window_days=1,
        min_training_matches=4,
    )

    with pytest.raises(ValueError, match="validation window has no matches"):
        build_dixon_coles_training_report(_training_matches(), config=config)


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
        _match("future_leak", "ars", "liv", 6, 4, datetime(2026, 5, 8, 12, tzinfo=UTC)),
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
