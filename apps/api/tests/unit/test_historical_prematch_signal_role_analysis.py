from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_prematch_signal_role_analysis import (
    HistoricalPrematchSignalRoleAnalysisOptions,
    _options_from_args,
    _parse_args,
    build_historical_prematch_signal_role_analysis_report,
    main,
)


def test_prematch_signal_role_analysis_prefers_risk_filter_when_lambda_harms() -> None:
    report = build_historical_prematch_signal_role_analysis_report(
        sample_readiness_report=_sample_readiness_report(),
        lambda_admission_report=_blocked_lambda_report(),
        final_answer_gate_report=_failed_final_answer_gate_with_local_gain(),
        market_segment_gate_report=_accepted_market_segment_gate(),
    )
    decisions = {decision.role: decision for decision in report.decisions}

    assert report.primary_recommended_role == "risk_filter"
    assert decisions["lambda_adjustment"].decision == "blocked"
    assert decisions["probability_adjustment"].decision == "blocked"
    assert decisions["final_answer_filter"].decision == "shadow_candidate"
    assert decisions["risk_filter"].decision == "shadow_candidate"
    assert decisions["risk_filter"].brier_score_delta == -0.001
    assert "Build market-movement risk-filter rolling admission" in (
        report.next_core_work_items[0]
    )


def test_prematch_signal_role_analysis_accepts_lambda_only_when_gate_allows() -> None:
    report = build_historical_prematch_signal_role_analysis_report(
        sample_readiness_report=_sample_readiness_report(),
        lambda_admission_report={
            **_blocked_lambda_report(),
            "status": "accepted",
            "candidate_model_allowed": True,
            "checks": [],
            "failed_competition_no_harm_count": 0,
            "hit_rate_delta": 0.01,
            "brier_score_delta": -0.01,
            "log_loss_delta": -0.02,
            "expected_calibration_error_delta": -0.01,
        },
    )
    decisions = {decision.role: decision for decision in report.decisions}

    assert report.primary_recommended_role == "lambda_adjustment"
    assert decisions["lambda_adjustment"].decision == "accepted"
    assert report.production_allowed_role_count == 1


def test_prematch_signal_role_analysis_requires_sample_readiness_for_shadow() -> None:
    report = build_historical_prematch_signal_role_analysis_report(
        sample_readiness_report={
            **_sample_readiness_report(),
            "sample_ready_allowed": False,
            "ready_fixture_count": 20,
        },
        market_segment_gate_report=_accepted_market_segment_gate(),
        options=HistoricalPrematchSignalRoleAnalysisOptions(
            min_sample_ready_fixture_count=100,
        ),
    )
    decisions = {decision.role: decision for decision in report.decisions}

    assert decisions["risk_filter"].decision == "blocked"
    assert "sample_readiness_below_shadow_floor" in decisions["risk_filter"].reasons
    assert "prematch_signal_role_analysis:sample_not_ready" in report.warnings


def test_prematch_signal_role_analysis_cli_writes_report(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.json"
    lambda_path = tmp_path / "lambda.json"
    final_answer_path = tmp_path / "final_answer.json"
    segment_path = tmp_path / "segment.json"
    output_path = tmp_path / "role_analysis.json"
    sample_path.write_text(f"{loads_dumps(_sample_readiness_report())}\n", encoding="utf-8")
    lambda_path.write_text(f"{loads_dumps(_blocked_lambda_report())}\n", encoding="utf-8")
    final_answer_path.write_text(
        f"{loads_dumps(_failed_final_answer_gate_with_local_gain())}\n",
        encoding="utf-8",
    )
    segment_path.write_text(f"{loads_dumps(_accepted_market_segment_gate())}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--sample-readiness-report",
            str(sample_path),
            "--lambda-admission-report",
            str(lambda_path),
            "--final-answer-gate-report",
            str(final_answer_path),
            "--market-segment-gate-report",
            str(segment_path),
            "--output-path",
            str(output_path),
            "--analysis-id",
            "role-analysis-test",
            "--min-sample-ready-fixture-count",
            "200",
            "--min-sample-ready-competition-count",
            "2",
            "--min-market-segment-accepted-count",
            "2",
            "--allow-market-segment-without-final-answer-gate",
            "--require-probability-rolling-admission",
            "--allow-shadow-without-sample-readiness",
        ]
    )
    options = _options_from_args(args)

    assert options.analysis_id == "role-analysis-test"
    assert options.min_sample_ready_fixture_count == 200
    assert options.min_sample_ready_competition_count == 2
    assert options.min_market_segment_accepted_count == 2
    assert options.require_market_segment_final_answer_gate is False
    assert options.require_probability_rolling_admission is True
    assert options.require_sample_readiness_for_shadow is False

    main(
        [
            "--sample-readiness-report",
            str(sample_path),
            "--lambda-admission-report",
            str(lambda_path),
            "--final-answer-gate-report",
            str(final_answer_path),
            "--market-segment-gate-report",
            str(segment_path),
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["primary_recommended_role"] == "risk_filter"
    assert payload["shadow_candidate_role_count"] >= 1


def _sample_readiness_report() -> dict[str, object]:
    return {
        "readiness_key": "historical_prematch_feature_sample_readiness:test",
        "status": "accepted",
        "sample_ready_allowed": True,
        "shadow_allowed": True,
        "ready_fixture_count": 600,
        "ready_competition_count": 5,
        "ready_season_count": 5,
        "ready_competition_season_count": 25,
    }


def _blocked_lambda_report() -> dict[str, object]:
    return {
        "report_key": "historical_poisson_prematch_lambda_admission:test",
        "status": "shadow_only",
        "candidate_model_allowed": False,
        "shadow_allowed": True,
        "failed_competition_no_harm_count": 5,
        "hit_rate_delta": -0.07,
        "brier_score_delta": 0.08,
        "log_loss_delta": 0.13,
        "expected_calibration_error_delta": None,
        "checks": [
            {"name": "hit_rate_delta", "status": "failed"},
            {"name": "brier_score_delta", "status": "failed"},
            {"name": "log_loss_delta", "status": "failed"},
        ],
    }


def _failed_final_answer_gate_with_local_gain() -> dict[str, object]:
    return {
        "report_key": "historical_prematch_feature_final_answer_gate:test",
        "status": "generated",
        "passing_candidate_count": 0,
        "best_evaluation": {
            "deltas_json": {
                "final_hit_rate_delta": 0.04,
                "roi_delta": 0.10,
                "profit_loss_delta": 5.0,
                "brier_score_delta": 0.01,
                "log_loss_delta": 0.02,
                "mean_calibration_error_delta": 0.01,
            },
            "quality_gate": {
                "checks": [
                    {"name": "suite_status", "status": "failed"},
                    {"name": "brier_score_delta", "status": "failed"},
                ]
            },
        },
    }


def _accepted_market_segment_gate() -> dict[str, object]:
    return {
        "report_key": "historical_market_movement_segment_gate:test",
        "status": "generated",
        "accepted_count": 3,
        "best_candidate": {
            "passed_final_answer_gate": True,
            "decision_reasons": ["segment_gate:accepted"],
            "final_answer_deltas_json": {
                "final_hit_rate_delta": 0.0,
                "roi_delta": 0.0,
                "profit_loss_delta": 0.0,
                "brier_score_delta": -0.001,
                "log_loss_delta": -0.002,
                "mean_calibration_error_delta": -0.001,
            },
        },
    }


def loads_dumps(payload: dict[str, object]) -> str:
    from json import dumps

    return dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
