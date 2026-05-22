from __future__ import annotations

from json import loads
from pathlib import Path
from typing import Literal

from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_production_proposal as proposal,
)
from nutmeg.recommendations import (
    historical_final_answer_selection_value_signal_search as value_search,
)


def test_selection_value_signal_production_proposal_ready() -> None:
    report = proposal.build_historical_final_answer_selection_value_signal_proposal_report(
        _search_report()
    )

    assert report.status == "runtime_profile_proposal_ready"
    assert report.runtime_profile_proposal_allowed is True
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert all(check.status == "passed" for check in report.checks)
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is True
    assert report.proposal_rule.holdout_candidate_enabled is True
    assert report.proposal_rule.production_recommendation_changed is False
    assert report.proposal_rule.competition_ids == ["ENG_CHAMPIONSHIP"]
    assert report.proposal_rule.outcomes == ["draw"]
    assert report.proposal_rule.score_min == 0.503
    assert report.proposal_rule.source_report_keys[
        "selection_value_signal_search"
    ] == "selection-value-search:test"
    assert report.proposal_rule.evidence_json["changed_final_answer_count"] == 1
    assert report.proposal_profile_set_json["final_answer_selection_value_signal_rules"]
    assert report.proposal_profile_set_json["default_recommendation_path_changed"] is False


def test_selection_value_signal_production_proposal_holdout_when_coverage_fails() -> None:
    report = proposal.build_historical_final_answer_selection_value_signal_proposal_report(
        _search_report(),
        options=proposal.HistoricalFinalAnswerSelectionValueSignalProposalOptions(
            min_final_answer_count=999
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "holdout_only"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is True
    assert report.proposal_count == 1
    assert failed_checks == {"final_answer_count"}
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is False
    assert report.proposal_rule.holdout_candidate_enabled is True


def test_selection_value_signal_production_proposal_blocks_harmful_movement() -> None:
    report = proposal.build_historical_final_answer_selection_value_signal_proposal_report(
        _search_report(harmful_movement_count=1)
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.runtime_profile_proposal_allowed is False
    assert report.holdout_candidate_allowed is False
    assert report.proposal_count == 0
    assert report.proposal_rule is None
    assert report.proposal_profile_set_json["final_answer_selection_value_signal_rules"] == []
    assert "harmful_movement_count" in failed_checks


def test_selection_value_signal_production_proposal_blocks_rejected_source() -> None:
    report = proposal.build_historical_final_answer_selection_value_signal_proposal_report(
        _search_report(decision="rejected", decision_reasons=("roi_delta:below_threshold",))
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.proposal_count == 0
    assert "source_search_has_accepted_candidate" in failed_checks
    assert "source_candidate_accepted" in failed_checks
    assert "source_candidate_has_no_decision_reasons" in failed_checks


def test_selection_value_signal_production_proposal_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "selection_value_search.json"
    output_path = tmp_path / "proposal.json"
    profile_path = tmp_path / "profile.json"
    source_path.write_text(
        f"{_search_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = proposal._parse_args(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--proposal-id",
            "custom-selection-rule",
            "--proposed-profile-version",
            "custom-selection-profile",
            "--source-candidate-key",
            "selection-value-candidate:test",
            "--min-final-answer-count",
            "20",
            "--min-affected-leg-count",
            "1",
            "--min-changed-final-answer-count",
            "1",
            "--min-positive-movement-count",
            "1",
            "--max-harmful-movement-count",
            "0",
            "--max-probability-quality-harm-movement-count",
            "0",
            "--min-final-answer-hit-delta-count",
            "0",
            "--min-roi-delta",
            "0.001",
            "--min-profit-loss-delta",
            "1.0",
            "--min-candidate-roi",
            "-0.5",
            "--max-brier-score-delta",
            "0.0",
            "--max-log-loss-delta",
            "0.0",
            "--max-mean-calibration-error-delta",
            "0.0",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "0",
            "--allow-non-accepted-source-candidate",
            "--allow-decision-reasons",
            "--allow-probability-grid-change",
            "--allow-non-movement-conditioned-spec",
            "--allow-probability-quality-harm-movements",
            "--no-fail-process",
        ]
    )
    options = proposal._options_from_args(args)

    assert options.proposal_id == "custom-selection-rule"
    assert options.proposed_profile_version == "custom-selection-profile"
    assert options.source_candidate_key == "selection-value-candidate:test"
    assert options.min_final_answer_count == 20
    assert options.min_roi_delta == 0.001
    assert options.min_profit_loss_delta == 1.0
    assert options.min_candidate_roi == -0.5
    assert options.require_search_candidate_accepted is False
    assert options.require_no_decision_reasons is False
    assert options.require_probability_grid_unchanged is False
    assert options.require_movement_conditioned_spec is False
    assert options.require_clean_movement_only is False
    assert proposal.load_historical_final_answer_selection_value_signal_search_report(
        source_path
    ).report_key == "selection-value-search:test"

    proposal.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_path),
            "--min-final-answer-count",
            "20",
            "--min-profit-loss-delta",
            "1.0",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile = loads(profile_path.read_text(encoding="utf-8"))
    assert payload["status"] == "runtime_profile_proposal_ready"
    assert payload["proposal_count"] == 1
    assert profile["final_answer_selection_value_signal_rules"][0]["rule_id"] == (
        "final_answer_selection_value_signal_candidate_v1"
    )


def _search_report(
    *,
    decision: Literal["accepted", "rejected"] = "accepted",
    decision_reasons: tuple[str, ...] = (),
    harmful_movement_count: int = 0,
) -> value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport:
    candidate = value_search.HistoricalFinalAnswerSelectionValueSignalSearchCandidate(
        candidate_key="selection-value-candidate:test",
        rank=1,
        decision=decision,
        decision_reasons=list(decision_reasons),
        spec=value_search.HistoricalFinalAnswerSelectionValueSignalSearchSpec(
            spec_key=(
                "bucket_value_signal:ENG_CHAMPIONSHIP:draw:"
                "movement_clean_positive:fixture:test:draw:score:0.5030-0.5060"
            ),
            competition_ids=("ENG_CHAMPIONSHIP",),
            outcomes=("draw",),
            probability_min=0.0,
            probability_max=1.0,
            min_decimal_odds=2.5,
            max_decimal_odds=3.3333333333333335,
            max_model_edge=None,
            score_min=0.503,
            score_max=0.506,
            max_hit_probability_deficit=0.02,
            strength=0.32,
            source_bucket_key="ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000",
            source_bucket_search_candidate_key="bucket-candidate:test",
        ),
        suite_key="suite:test",
        suite_status="completed",
        affected_leg_count=1,
        guard_blocked_option_count=7,
        final_answer_count=40,
        changed_final_answer_count=1,
        final_answer_hit_delta_count=0,
        final_answer_hit_rate_delta=0.0,
        roi_delta=0.01,
        profit_loss_delta=2.0,
        candidate_roi=-0.04,
        brier_score_delta=-0.001,
        log_loss_delta=-0.002,
        mean_calibration_error_delta=-0.003,
        final_hit_harm_count_vs_baseline=0,
        profit_loss_harm_count_vs_baseline=0,
        movement_count=1,
        positive_movement_count=1,
        harmful_movement_count=harmful_movement_count,
        probability_quality_harm_movement_count=0,
        summary_json={"probability_grid_unchanged": True},
    )
    accepted = decision == "accepted"
    return value_search.HistoricalFinalAnswerSelectionValueSignalSearchReport(
        report_key="selection-value-search:test",
        status="generated",
        baseline_suite_key="suite:baseline",
        baseline_suite_status="completed",
        candidate_count=1,
        accepted_count=1 if accepted else 0,
        rejected_count=0 if accepted else 1,
        best_candidate=candidate if accepted else None,
        accepted_candidates=[candidate] if accepted else [],
        candidates=[candidate],
        summary_json={"probability_grid_unchanged": True},
    )
