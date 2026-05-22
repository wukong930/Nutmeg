from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_profile_proposal import (
    CompetitionProfileProposalOptions,
    _options_from_args,
    _parse_args,
    build_competition_profile_proposal_report,
    main,
)


def test_profile_proposal_keeps_accepted_evidence_shadow_only_when_admission_blocks() -> None:
    report = build_competition_profile_proposal_report(
        profile_evidence_report=_profile_evidence_report(),
        admission_gate_report=_admission_report(
            decision="shadow_only",
            production=False,
            training=False,
            shadow=True,
        ),
        options=CompetitionProfileProposalOptions(
            profile_version="proposal-v1",
            min_historical_final_hit_sample_size=30,
        ),
    )

    assert report.status == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert report.training_pool_allowed is False
    assert report.shadow_allowed is True
    assert report.proposal_count == 2
    assert report.proposals[0].production_recommendation_allowed is False
    assert report.proposals[0].shadow_allowed is True
    assert report.proposals[0].final_answer_score_adjustments == {"2x1:multiple": 0.1}
    assert "competition_profile_proposal:admission_shadow_only" in report.warnings
    proposal_profile_set = report.proposal_profile_set_json
    assert proposal_profile_set["production_recommendation_allowed"] is False
    assert len(proposal_profile_set["profiles"]) == 2


def test_profile_proposal_marks_profiles_ready_when_admission_accepts() -> None:
    report = build_competition_profile_proposal_report(
        profile_evidence_report=_profile_evidence_report(),
        admission_gate_report=_admission_report(
            decision="accepted",
            production=True,
            training=True,
            shadow=True,
        ),
    )

    assert report.status == "production_ready"
    assert report.production_recommendation_allowed is True
    assert report.training_pool_allowed is True
    assert report.warnings == []
    assert all(proposal.production_recommendation_allowed for proposal in report.proposals)
    assert all(proposal.training_pool_allowed for proposal in report.proposals)


def test_profile_proposal_records_no_candidates() -> None:
    evidence = _profile_evidence_report()
    evidence["decisions"] = []
    evidence["summary_json"]["accepted_profile_adjustments"] = {}

    report = build_competition_profile_proposal_report(
        profile_evidence_report=evidence,
        admission_gate_report=_admission_report(
            decision="accepted",
            production=True,
            training=True,
            shadow=True,
        ),
    )

    assert report.status == "no_candidates"
    assert report.proposal_count == 0
    assert "competition_profile_proposal:no_accepted_profile_candidates" in report.warnings


def test_profile_proposal_cli_writes_shadow_report(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    admission_path = tmp_path / "admission.json"
    output_path = tmp_path / "proposal.json"
    evidence_path.write_text(_json(_profile_evidence_report()), encoding="utf-8")
    admission_path.write_text(
        _json(
            _admission_report(
                decision="shadow_only",
                production=False,
                training=False,
                shadow=True,
            )
        ),
        encoding="utf-8",
    )

    main(
        [
            "--profile-evidence-report",
            str(evidence_path),
            "--admission-gate-report",
            str(admission_path),
            "--output-path",
            str(output_path),
            "--profile-version",
            "proposal-cli",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "shadow_only"
    assert payload["proposal_count"] == 2
    assert payload["proposal_profile_set_json"]["profile_version"] == "proposal-cli"


def test_profile_proposal_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--profile-evidence-report",
            "evidence.json",
            "--admission-gate-report",
            "admission.json",
            "--output-path",
            "proposal.json",
            "--profile-version",
            "custom-profile",
            "--min-historical-final-hit-sample-size",
            "42",
            "--allow-without-production-admission",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert args.profile_evidence_report == Path("evidence.json")
    assert args.admission_gate_report == Path("admission.json")
    assert args.output_path == Path("proposal.json")
    assert options.profile_version == "custom-profile"
    assert options.min_historical_final_hit_sample_size == 42
    assert options.require_production_admission is False


def _profile_evidence_report() -> dict[str, object]:
    return {
        "report_key": "historical_competition_profile_evidence:test",
        "decisions": [
            _accepted_decision(
                "ESP_SEGUNDA_DIVISION",
                hit_count_delta=4,
                roi_delta=0.065,
                profit_loss_delta=1.67,
            ),
            _accepted_decision(
                "ITA_SERIE_B",
                hit_count_delta=3,
                roi_delta=0.188,
                profit_loss_delta=16.64,
            ),
            {
                "competition_id": "ENG_CHAMPIONSHIP",
                "status": "baseline_retained",
                "recommended_scenario_key": "1x1:single",
            },
        ],
        "summary_json": {
            "report_key": "historical_competition_profile_evidence:test",
            "accepted_count": 2,
            "retained_count": 1,
            "accepted_profile_adjustments": {
                "ESP_SEGUNDA_DIVISION": {
                    "scenario_key": "2x1:multiple",
                    "suggested_score_adjustment": 0.1,
                },
                "ITA_SERIE_B": {
                    "scenario_key": "2x1:multiple",
                    "suggested_score_adjustment": 0.1,
                },
            },
        },
    }


def _accepted_decision(
    competition_id: str,
    *,
    hit_count_delta: int,
    roi_delta: float,
    profit_loss_delta: float,
) -> dict[str, object]:
    return {
        "competition_id": competition_id,
        "status": "candidate_accepted",
        "recommended_scenario_key": "2x1:multiple",
        "suggested_score_adjustment": 0.1,
        "hit_count_delta": hit_count_delta,
        "roi_delta": roi_delta,
        "profit_loss_delta": profit_loss_delta,
        "baseline_metric": {
            "scenario_key": "current_final_answer",
            "sample_size": 30,
            "hit_count": 16,
            "roi": -0.10,
        },
        "selected_metric": {
            "scenario_key": "2x1:multiple",
            "sample_size": 30,
            "hit_count": 20,
            "roi": -0.03,
        },
        "reason_codes": [
            "competition_profile_evidence:hit_count_preserved",
            "competition_profile_evidence:roi_improved",
            "competition_profile_evidence:profit_loss_improved",
        ],
    }


def _admission_report(
    *,
    decision: str,
    production: bool,
    training: bool,
    shadow: bool,
) -> dict[str, object]:
    return {
        "report_key": "competition_admission_gate:test",
        "decision": decision,
        "production_recommendation_allowed": production,
        "training_pool_allowed": training,
        "shadow_allowed": shadow,
        "summary_json": {
            "report_key": "competition_admission_gate:test",
            "decision": decision,
            "production_recommendation_allowed": production,
            "training_pool_allowed": training,
            "shadow_allowed": shadow,
        },
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
