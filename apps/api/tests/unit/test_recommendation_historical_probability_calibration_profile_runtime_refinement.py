from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_refinement as refinement,
)
from nutmeg.recommendations import (
    historical_probability_calibration_profile_runtime_replay as replay,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationBucket,
    CandidateProbabilityCalibrationProfile,
)


def test_probability_calibration_runtime_refinement_adds_scope_guard(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    report = refinement.build_historical_probability_calibration_profile_runtime_refinement_report(
        profile_set_path=profile_path,
        options=refinement.HistoricalProbabilityCalibrationProfileRuntimeRefinementOptions(
            profile_keys=("profile:test",),
            min_competition_season_index_by_competition_id={"ENG_CHAMPIONSHIP": 3},
        ),
    )

    profile_json = report.refined_profile_set_json["profiles"][0]
    assert report.status == "generated"
    assert report.selected_profile_key == "profile:test"
    assert report.refined_profile_key.startswith(
        "profile:test:runtime_refinement:scope_refinement:"
    )
    assert report.changed_fields_json == {
        "min_competition_season_index_by_competition_id": {"ENG_CHAMPIONSHIP": 3}
    }
    assert report.refined_profile_set_json["runtime_profile_proposal_allowed"] is False
    assert report.refined_profile_set_json["production_recommendation_changed"] is False
    assert profile_json["min_competition_season_index_by_competition_id"] == {
        "ENG_CHAMPIONSHIP": 3
    }


def test_probability_calibration_runtime_refinement_cli_and_loader(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile_set.json"
    output_path = tmp_path / "refinement.json"
    profile_output_path = tmp_path / "refined_profile_set.json"
    profile_path.write_text(
        f"{_profile_set().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = refinement._parse_args(
        [
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_output_path),
            "--profile-keys",
            "profile:test",
            "--min-competition-season-index-by-competition",
            "ENG_CHAMPIONSHIP:3",
            "--excluded-seasons",
            "2020-2021,2021-2022",
        ]
    )
    options = refinement._options_from_args(args)

    assert options.profile_keys == ("profile:test",)
    assert options.excluded_season_ids == ("2020-2021", "2021-2022")
    assert options.min_competition_season_index_by_competition_id == {
        "ENG_CHAMPIONSHIP": 3
    }

    refinement.main(
        [
            "--profile-set",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--profile-output-path",
            str(profile_output_path),
            "--profile-keys",
            "profile:test",
            "--min-competition-season-index-by-competition",
            "ENG_CHAMPIONSHIP:3",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    profile_set = replay.load_probability_calibration_runtime_profile_set(output_path)
    direct_profile_set = replay.load_probability_calibration_runtime_profile_set(
        profile_output_path
    )

    assert payload["status"] == "generated"
    assert profile_set.profiles[0].profile_key == payload["refined_profile_key"]
    assert direct_profile_set.profiles[0].profile_key == payload["refined_profile_key"]


def _profile_set() -> replay.ProbabilityCalibrationRuntimeProfileSet:
    return replay.ProbabilityCalibrationRuntimeProfileSet(
        profile_version="profile-set:test",
        status="runtime_profile_proposal_ready",
        runtime_profile_proposal_allowed=True,
        holdout_candidate_allowed=True,
        profiles=[_profile()],
    )


def _profile() -> CandidateProbabilityCalibrationProfile:
    return CandidateProbabilityCalibrationProfile(
        profile_key="profile:test",
        source_report_key="gate:test",
        mode="active",
        segment_mode="market_odds_band",
        min_bucket_sample_size=1,
        blend_weight=0.10,
        target_competition_ids=("ENG_CHAMPIONSHIP",),
        target_market_types=("1x2",),
        target_outcomes=("draw",),
        min_decimal_odds=2.25,
        max_decimal_odds=3.45,
        buckets=[
            CandidateProbabilityCalibrationBucket(
                outcome="draw",
                segment_mode="market_odds_band",
                bucket_start=0.30,
                bucket_end=0.35,
                calibrated_probability=0.45,
                sample_size=20,
                competition_id="ENG_CHAMPIONSHIP",
                market_type="1x2",
            )
        ],
    )
