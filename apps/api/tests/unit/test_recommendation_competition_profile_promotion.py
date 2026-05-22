from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.competition_profile_promotion import (
    CompetitionProfilePromotionOptions,
    _options_from_args,
    _parse_args,
    build_competition_profile_promotion_report,
    main,
)
from nutmeg.recommendations.competition_profiles import (
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
)


def test_profile_promotion_merges_production_ready_proposal() -> None:
    report = build_competition_profile_promotion_report(
        current_profile_set=_current_profile_set(),
        proposal_report=_proposal_report(),
        options=CompetitionProfilePromotionOptions(
            promoted_profile_version="promoted-v1",
        ),
    )

    promoted_profiles = {
        profile["competition_id"]: profile
        for profile in report.promoted_profile_set_json["profiles"]
    }

    assert report.status == "promoted"
    assert report.promoted_profile_version == "promoted-v1"
    assert report.promoted_competition_ids == [
        "ESP_SEGUNDA_DIVISION",
        "ITA_SERIE_B",
    ]
    assert report.promoted_profile_count == 2
    assert report.profile_count == 3
    assert promoted_profiles["EPL"]["final_answer_score_adjustments"] == {
        "5x1:single": 0.1
    }
    assert promoted_profiles["ESP_SEGUNDA_DIVISION"][
        "final_answer_score_adjustments"
    ] == {"2x1:multiple": 0.1}
    assert promoted_profiles["ITA_SERIE_B"]["min_historical_final_hit_sample_size"] == 30


def test_profile_promotion_blocks_shadow_only_proposal() -> None:
    proposal = _proposal_report(status="shadow_only", production=False, training=False)

    report = build_competition_profile_promotion_report(
        current_profile_set=_current_profile_set(),
        proposal_report=proposal,
    )

    assert report.status == "blocked"
    assert "profile_proposal_not_production_ready" in report.blockers
    assert "profile_proposal_production_not_allowed" in report.blockers
    assert "profile_proposal_training_pool_not_allowed" in report.blockers


def test_profile_promotion_blocks_existing_adjustment_conflict() -> None:
    current = CompetitionRecommendationProfileSet(
        profile_version="current-v1",
        profiles=[
            CompetitionRecommendationProfile(
                competition_id="ESP_SEGUNDA_DIVISION",
                final_answer_score_adjustments={"2x1:multiple": 0.03},
            )
        ],
    )

    report = build_competition_profile_promotion_report(
        current_profile_set=current,
        proposal_report=_proposal_report(),
    )

    assert report.status == "blocked"
    assert (
        "profile_adjustment_conflict:ESP_SEGUNDA_DIVISION:2x1:multiple"
        in report.blockers
    )


def test_profile_promotion_cli_writes_profile_and_report(tmp_path: Path) -> None:
    current_path = tmp_path / "current_profiles.json"
    proposal_path = tmp_path / "proposal.json"
    profile_output_path = tmp_path / "promoted_profiles.json"
    report_output_path = tmp_path / "promotion_report.json"
    current_path.write_text(
        _json(_current_profile_set().model_dump(mode="json")),
        encoding="utf-8",
    )
    proposal_path.write_text(_json(_proposal_report()), encoding="utf-8")

    main(
        [
            "--current-profile-path",
            str(current_path),
            "--profile-proposal-report",
            str(proposal_path),
            "--profile-output-path",
            str(profile_output_path),
            "--report-output-path",
            str(report_output_path),
            "--promoted-profile-version",
            "cli-promoted-v1",
        ]
    )

    promoted_profile = loads(profile_output_path.read_text(encoding="utf-8"))
    promotion_report = loads(report_output_path.read_text(encoding="utf-8"))

    assert promoted_profile["profile_version"] == "cli-promoted-v1"
    assert promotion_report["status"] == "promoted"
    assert promotion_report["promoted_profile_count"] == 2


def test_profile_promotion_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--current-profile-path",
            "current.json",
            "--profile-proposal-report",
            "proposal.json",
            "--profile-output-path",
            "promoted.json",
            "--report-output-path",
            "report.json",
            "--promoted-profile-version",
            "custom-promoted",
            "--allow-overwrite-existing",
            "--allow-without-training-pool",
            "--allow-non-production-ready",
            "--dry-run",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert args.current_profile_path == Path("current.json")
    assert args.profile_proposal_report == Path("proposal.json")
    assert args.profile_output_path == Path("promoted.json")
    assert args.report_output_path == Path("report.json")
    assert options.promoted_profile_version == "custom-promoted"
    assert options.allow_overwrite_existing is True
    assert options.require_training_pool_allowed is False
    assert options.require_production_ready is False
    assert options.dry_run is True


def _current_profile_set() -> CompetitionRecommendationProfileSet:
    return CompetitionRecommendationProfileSet(
        profile_version="current-v1",
        calculation_basis="competition_recommendation_profiles_v3_1",
        profiles=[
            CompetitionRecommendationProfile(
                competition_id="EPL",
                final_answer_score_adjustments={"5x1:single": 0.1},
                min_historical_final_hit_sample_size=5,
                source_report_key="historical_recommendation_diagnostic:test",
            )
        ],
        notes=["existing note"],
    )


def _proposal_report(
    *,
    status: str = "production_ready",
    production: bool = True,
    training: bool = True,
) -> dict[str, object]:
    return {
        "report_key": "competition_profile_proposal:test",
        "status": status,
        "production_recommendation_allowed": production,
        "training_pool_allowed": training,
        "shadow_allowed": True,
        "admission_report_key": "competition_admission_gate:test",
        "proposals": [
            _proposal_item("ESP_SEGUNDA_DIVISION"),
            _proposal_item("ITA_SERIE_B"),
        ],
        "summary_json": {
            "report_key": "competition_profile_proposal:test",
            "status": status,
            "admission_report_key": "competition_admission_gate:test",
            "production_recommendation_allowed": production,
            "training_pool_allowed": training,
        },
    }


def _proposal_item(competition_id: str) -> dict[str, object]:
    return {
        "competition_id": competition_id,
        "scenario_key": "2x1:multiple",
        "final_answer_score_adjustments": {"2x1:multiple": 0.1},
        "min_historical_final_hit_sample_size": 30,
        "source_report_key": "historical_competition_profile_evidence:test",
        "admission_report_key": "competition_admission_gate:test",
        "production_recommendation_allowed": True,
        "training_pool_allowed": True,
        "shadow_allowed": True,
    }


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
