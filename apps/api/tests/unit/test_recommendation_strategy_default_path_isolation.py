from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.competition_profiles import (
    CompetitionRecommendationProfile,
    CompetitionRecommendationProfileSet,
)
from nutmeg.recommendations.recommendation_strategy_default_path_isolation import (
    RecommendationStrategyDefaultPathIsolationOptions,
    _options_from_args,
    _parse_args,
    build_recommendation_strategy_default_path_isolation_report,
    load_recommendation_strategy_default_path_isolation_report,
    main,
)
from nutmeg.recommendations.recommendation_strategy_staged_activation_smoke import (
    RecommendationStrategyStagedActivationSmokeReport,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    load_short_odds_runtime_rule_set,
)


def test_default_path_isolation_passes_when_staged_profile_is_opt_in_only(
    tmp_path: Path,
) -> None:
    staged_profile_path = _write_json(tmp_path / "staged_profile.json", _staged_profile())
    report = build_recommendation_strategy_default_path_isolation_report(
        _staged_smoke_report(),
        default_profile_set=_default_profile_set(),
        default_profile_json=_default_profile_json(),
        default_profile_path=tmp_path / "default_profiles.json",
        staged_profile_path=staged_profile_path,
        staged_rule_set=load_short_odds_runtime_rule_set(staged_profile_path),
    )

    assert report.status == "isolated"
    assert report.default_path_isolated is True
    assert report.default_adapter_status == "disabled"
    assert report.default_adapter_selection_changed is False
    assert report.explicit_opt_in_adapter_status == "applied"
    assert report.explicit_opt_in_selection_changed is True
    assert report.default_profile_written is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False


def test_default_path_isolation_blocks_default_profile_short_odds_rules(
    tmp_path: Path,
) -> None:
    staged_profile_path = _write_json(tmp_path / "staged_profile.json", _staged_profile())
    default_json = _default_profile_json()
    default_json["short_odds_replacement_rules"] = [_rule()]

    report = build_recommendation_strategy_default_path_isolation_report(
        _staged_smoke_report(),
        default_profile_set=_default_profile_set(),
        default_profile_json=default_json,
        default_profile_path=tmp_path / "default_profiles.json",
        staged_profile_path=staged_profile_path,
        staged_rule_set=load_short_odds_runtime_rule_set(staged_profile_path),
    )

    assert report.status == "blocked"
    assert "default_profile_without_short_odds_rules" in report.blockers


def test_default_path_isolation_watchlists_missing_explicit_opt_in_change(
    tmp_path: Path,
) -> None:
    staged_profile = _staged_profile()
    rule = dict(staged_profile["short_odds_replacement_rules"][0])  # type: ignore[index]
    constraints = dict(rule["constraints_json"])  # type: ignore[index]
    constraints["min_replacement_probability"] = 0.99
    rule["constraints_json"] = constraints
    staged_profile["short_odds_replacement_rules"] = [rule]
    staged_profile_path = _write_json(tmp_path / "staged_profile.json", staged_profile)

    report = build_recommendation_strategy_default_path_isolation_report(
        _staged_smoke_report(),
        default_profile_set=_default_profile_set(),
        default_profile_json=_default_profile_json(),
        default_profile_path=tmp_path / "default_profiles.json",
        staged_profile_path=staged_profile_path,
        staged_rule_set=load_short_odds_runtime_rule_set(staged_profile_path),
    )

    assert report.status == "watchlist"
    assert "explicit_opt_in_adapter_status" in report.blockers
    assert report.default_adapter_selection_changed is False


def test_default_path_isolation_can_relax_explicit_opt_in_change(
    tmp_path: Path,
) -> None:
    staged_profile = _staged_profile()
    rule = dict(staged_profile["short_odds_replacement_rules"][0])  # type: ignore[index]
    constraints = dict(rule["constraints_json"])  # type: ignore[index]
    constraints["min_replacement_probability"] = 0.99
    rule["constraints_json"] = constraints
    staged_profile["short_odds_replacement_rules"] = [rule]
    staged_profile_path = _write_json(tmp_path / "staged_profile.json", staged_profile)

    report = build_recommendation_strategy_default_path_isolation_report(
        _staged_smoke_report(),
        default_profile_set=_default_profile_set(),
        default_profile_json=_default_profile_json(),
        default_profile_path=tmp_path / "default_profiles.json",
        staged_profile_path=staged_profile_path,
        staged_rule_set=load_short_odds_runtime_rule_set(staged_profile_path),
        options=RecommendationStrategyDefaultPathIsolationOptions(
            require_explicit_opt_in_applies=False
        ),
    )

    assert report.status == "isolated"
    assert report.explicit_opt_in_adapter_status == "unchanged"


def test_default_path_isolation_cli_options_and_main(tmp_path: Path) -> None:
    staged_smoke_path = _write_json(
        tmp_path / "staged_smoke.json",
        _staged_smoke_report().model_dump(mode="json"),
    )
    staged_profile_path = _write_json(tmp_path / "staged_profile.json", _staged_profile())
    default_profile_path = _write_json(
        tmp_path / "default_profiles.json",
        _default_profile_json(),
    )
    report_path = tmp_path / "isolation_report.json"

    args = _parse_args(
        [
            "--staged-activation-smoke-report",
            str(staged_smoke_path),
            "--staged-profile-path",
            str(staged_profile_path),
            "--default-profile-path",
            str(default_profile_path),
            "--report-output-path",
            str(report_path),
            "--isolation-id",
            "unit-isolation",
            "--min-rule-count",
            "1",
            "--min-allowed-competition-count",
            "5",
            "--allow-missing-explicit-opt-in-change",
        ]
    )
    options = _options_from_args(args)

    assert options.isolation_id == "unit-isolation"
    assert options.min_allowed_competition_count == 5
    assert options.require_explicit_opt_in_applies is False

    main(
        [
            "--staged-activation-smoke-report",
            str(staged_smoke_path),
            "--staged-profile-path",
            str(staged_profile_path),
            "--default-profile-path",
            str(default_profile_path),
            "--report-output-path",
            str(report_path),
            "--isolation-id",
            "unit-isolation",
            "--min-rule-count",
            "1",
            "--min-allowed-competition-count",
            "5",
        ]
    )

    saved = load_recommendation_strategy_default_path_isolation_report(report_path)
    assert saved.status == "isolated"
    assert saved.isolation_id == "unit-isolation"


def _staged_smoke_report() -> RecommendationStrategyStagedActivationSmokeReport:
    return RecommendationStrategyStagedActivationSmokeReport(
        report_key="recommendation_strategy_staged_activation_smoke:test",
        status="staged_activation_ready",
        staged_activation_ready=True,
        staged_profile_version="staged-profile-v1",
        source_strategy_gate_key="recommendation_strategy_promotion_gate:test",
        source_strategy_key="probability_preserving_13change_replacement",
        source_gate_id="strategy-gate-v1",
        source_promotion_review_report_keys=[
            "historical_replacement_probability_preserving_promotion_review:test"
        ],
        source_selected_candidate_keys=[
            "replacement_probability_preserving_candidate:test"
        ],
        rule_profile_version="review-profile-v1",
        rule_count=1,
        selected_rule_count=1,
        allowed_competition_ids=[
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        excluded_competition_ids=[],
        total_final_answer_count=99,
        total_changed_final_answer_count=13,
        total_final_answer_hit_delta_count=4,
        total_profit_loss_delta=15.74,
        minimum_roi_delta=0.0403,
        total_harm_count_vs_original=0,
        total_final_hit_harm_count_vs_original=0,
        total_profit_loss_harm_count_vs_original=0,
        minimum_active_surface_count=8,
        total_failed_surface_count=0,
        minimum_active_competition_fold_count=5,
        minimum_active_season_fold_count=5,
        minimum_active_rolling_fold_count=13,
        total_failed_fold_count=0,
        default_profile_write_requested=False,
        default_profile_written=False,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=[],
        blockers=[],
        staged_profile_json=_staged_profile(),
        public_contract_json={"public_response_changed": False},
        warnings=[],
        summary_json={},
    )


def _default_profile_set() -> CompetitionRecommendationProfileSet:
    return CompetitionRecommendationProfileSet(
        profile_version="default-profile-v1",
        profiles=[
            CompetitionRecommendationProfile(
                competition_id="ENG_CHAMPIONSHIP",
                final_answer_score_adjustments={},
            )
        ],
    )


def _default_profile_json() -> dict[str, object]:
    return _default_profile_set().model_dump(mode="json")


def _staged_profile() -> dict[str, object]:
    return {
        "profile_version": "staged-profile-v1",
        "calculation_basis": "recommendation_strategy_staged_activation_smoke_v3_1",
        "staged_only": True,
        "dry_run_only": True,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "short_odds_replacement_rules": [_rule()],
    }


def _rule() -> dict[str, object]:
    return {
        "rule_id": "probability_preserving_runtime_dry_run:test",
        "profile_id": "nearest_model_top_probability",
        "proposed_profile_version": "runtime-dry-run-v1",
        "proposed_production_enabled": True,
        "production_recommendation_changed": False,
        "allowed_competition_ids": [
            "ENG_CHAMPIONSHIP",
            "ESP_SEGUNDA_DIVISION",
            "FRA_LIGUE_2",
            "GER_2_BUNDESLIGA",
            "ITA_SERIE_B",
        ],
        "excluded_competition_ids": [],
        "selection_rule": "highest_candidate_hit_probability",
        "constraints_json": {
            "selection_rule": "highest_candidate_hit_probability",
            "max_replacements_per_final_answer": 1,
            "min_replacement_probability": 0.45,
            "max_replacement_decimal_odds": 2.20,
            "min_candidate_hit_probability_delta_vs_model_top": -0.05,
            "max_candidate_hit_probability_delta_vs_model_top": 0.0,
            "min_decimal_odds_delta_vs_model_top": 0.0,
            "min_candidate_hit_probability_delta_vs_original": -0.025,
            "exclude_original_hit_harm": True,
            "max_harm_count_vs_original": 0,
            "max_final_hit_harm_count_vs_original": 0,
            "max_profit_loss_harm_count_vs_original": 0,
        },
        "evidence_json": {
            "candidate_key": "replacement_probability_preserving_candidate:test",
            "changed_final_answer_count": 13,
            "harm_count_vs_original": 0,
        },
    }


def _write_json(path: Path, payload: object) -> Path:
    import json

    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")
    return path
