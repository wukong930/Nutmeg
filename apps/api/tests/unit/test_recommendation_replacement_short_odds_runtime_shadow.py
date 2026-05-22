from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_runtime_shadow_replay_report,
    load_short_odds_runtime_rule_set,
    main,
)


def test_runtime_shadow_replay_is_disabled_without_feature_flag(tmp_path: Path) -> None:
    rule_path = tmp_path / "rules.json"
    rule_path.write_text(_json(_rule_profile()), encoding="utf-8")
    rule_set = load_short_odds_runtime_rule_set(rule_path)

    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report([_audit_item("item_a")]),
        rule_set=rule_set,
    )

    assert report.status == "disabled"
    assert report.passed is False
    assert report.enabled_rule_count == 1
    assert report.changed_final_answer_count == 0
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert "short_odds_runtime_shadow_replay:disabled_by_feature_flag" in report.warnings


def test_runtime_shadow_replay_applies_loaded_rule_and_keeps_excluded_league() -> None:
    rule_set = load_short_odds_runtime_rule_set_from_payload(_rule_profile())
    model_top_a = _replacement(rank=1, fixture_id="model_top_a", simulated_hp=0.62)
    candidate_a = _replacement(
        rank=2,
        fixture_id="candidate_a",
        odds=1.18,
        simulated_hp=0.611,
        simulated_hit=True,
        simulated_profit=0.2,
    )
    model_top_b = _replacement(rank=1, fixture_id="model_top_b", simulated_hp=0.62)
    candidate_b = _replacement(
        rank=2,
        fixture_id="candidate_b",
        odds=1.19,
        simulated_hp=0.615,
        simulated_hit=True,
        simulated_profit=0.4,
    )
    isolated_candidate = _replacement(
        rank=2,
        fixture_id="isolated_candidate",
        odds=1.20,
        simulated_hp=0.615,
        simulated_hit=True,
        simulated_profit=0.4,
    )
    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    model_top=model_top_a,
                    replacements=[model_top_a, candidate_a],
                ),
                _audit_item(
                    "item_b",
                    selected_fixture_id="selected_b",
                    model_top=model_top_b,
                    replacements=[model_top_b, candidate_b],
                ),
                _audit_item(
                    "item_c",
                    slice_id="slice_b",
                    final_answer_hit=True,
                    original_profit=1.0,
                    original_return=3.0,
                    original_hp=0.55,
                    model_top=model_top_a,
                    replacements=[model_top_a],
                ),
                _audit_item(
                    "item_d",
                    competition_id="ESP_LA_LIGA",
                    slice_id="slice_c",
                    model_top=model_top_a,
                    replacements=[model_top_a, isolated_candidate],
                ),
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=3,
            min_changed_final_answer_count=1,
        ),
    )

    assert report.status == "shadow_replay_passed"
    assert report.passed is True
    assert report.rule_count == 1
    assert report.enabled_rule_count == 1
    assert report.final_answer_count == 3
    assert report.changed_final_answer_count == 1
    assert report.baseline_final_answer_hit_count == 1
    assert report.shadow_final_answer_hit_count == 2
    assert report.final_answer_hit_delta_count == 1
    assert report.harm_count_vs_original == 0
    assert report.profit_loss_delta == 2.4
    assert report.changed_items[0].replacement_fixture_id == "candidate_b"
    assert report.changed_items[0].competition_id == "EPL"
    assert "ESP_LA_LIGA" in report.rule_set_json["rules"][0]["excluded_competition_ids"]


def test_runtime_shadow_replay_supports_probability_preserving_quality_score() -> None:
    rule_profile = _rule_profile()
    rule_profile["short_odds_replacement_rules"][0][
        "profile_id"
    ] = "probability_preserving_quality_score_v1"
    rule_set = load_short_odds_runtime_rule_set_from_payload(rule_profile)
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        odds=1.12,
        simulated_hp=0.62,
        quality=0.60,
        score=0.60,
    )
    edge_candidate = _replacement(
        rank=2,
        fixture_id="edge_candidate",
        odds=1.18,
        model_edge=0.08,
        simulated_hp=0.611,
        quality=0.61,
        score=0.62,
        simulated_hit=True,
        simulated_profit=0.2,
    )
    quality_candidate = _replacement(
        rank=3,
        fixture_id="quality_candidate",
        odds=1.17,
        model_edge=0.02,
        simulated_hp=0.607,
        quality=0.76,
        score=0.74,
        simulated_hit=True,
        simulated_profit=0.4,
    )

    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    model_top=model_top,
                    replacements=[model_top, edge_candidate, quality_candidate],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
        ),
    )

    assert report.status == "shadow_replay_passed"
    assert report.changed_items[0].replacement_fixture_id == "quality_candidate"


def test_runtime_shadow_replay_candidate_original_hp_guard_filters_harm() -> None:
    rule_set = load_short_odds_runtime_rule_set_from_payload(_rule_profile())
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        odds=1.12,
        simulated_hp=0.61,
        simulated_hit=True,
        simulated_profit=1.0,
    )
    safe_candidate = _replacement(
        rank=2,
        fixture_id="safe_candidate",
        odds=1.17,
        simulated_hp=0.605,
        simulated_hit=True,
        simulated_profit=1.2,
    )
    harmful_short_odds_candidate = _replacement(
        rank=3,
        fixture_id="harmful_short_odds_candidate",
        odds=1.18,
        simulated_hp=0.60,
        simulated_hit=False,
        simulated_profit=-2.0,
    )

    without_guard = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    final_answer_hit=True,
                    original_profit=1.0,
                    original_return=3.0,
                    original_hp=0.62,
                    model_top=model_top,
                    replacements=[
                        model_top,
                        safe_candidate,
                        harmful_short_odds_candidate,
                    ],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
            max_harm_count_vs_original=1,
            min_profit_loss_delta=-3.0,
            min_roi_delta=-1.5,
            min_final_answer_hit_rate_delta=-1.0,
        ),
    )
    with_guard = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    final_answer_hit=True,
                    original_profit=1.0,
                    original_return=3.0,
                    original_hp=0.62,
                    model_top=model_top,
                    replacements=[
                        model_top,
                        safe_candidate,
                        harmful_short_odds_candidate,
                    ],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
            min_candidate_hit_probability_delta_vs_original=-0.018,
        ),
    )

    assert without_guard.changed_items[0].replacement_fixture_id == (
        "harmful_short_odds_candidate"
    )
    assert without_guard.harm_count_vs_original == 1
    assert with_guard.passed is True
    assert with_guard.changed_items[0].replacement_fixture_id == "safe_candidate"
    assert with_guard.harm_count_vs_original == 0
    assert with_guard.profit_loss_delta == 0.19999999999999996
    assert with_guard.summary_json["options"][
        "min_candidate_hit_probability_delta_vs_original"
    ] == -0.018


def test_runtime_shadow_replay_rejects_final_hit_harm_even_without_profit_loss_harm() -> None:
    rule_set = load_short_odds_runtime_rule_set_from_payload(_rule_profile())
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        odds=1.12,
        simulated_hp=0.61,
        simulated_hit=True,
        simulated_profit=-2.0,
    )
    final_hit_harm_candidate = _replacement(
        rank=2,
        fixture_id="final_hit_harm_candidate",
        odds=1.18,
        simulated_hp=0.605,
        simulated_hit=False,
        simulated_profit=-1.0,
    )

    strict_report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    final_answer_hit=True,
                    original_profit=-2.0,
                    original_return=0.0,
                    original_hp=0.62,
                    model_top=model_top,
                    replacements=[model_top, final_hit_harm_candidate],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
            min_final_answer_hit_rate_delta=-1.0,
        ),
    )
    relaxed_report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    final_answer_hit=True,
                    original_profit=-2.0,
                    original_return=0.0,
                    original_hp=0.62,
                    model_top=model_top,
                    replacements=[model_top, final_hit_harm_candidate],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
            min_final_answer_hit_rate_delta=-1.0,
            max_final_hit_harm_count_vs_original=1,
        ),
    )

    failed_checks = {
        check.name for check in strict_report.checks if check.status == "failed"
    }
    assert strict_report.passed is False
    assert strict_report.final_hit_harm_count_vs_original == 1
    assert strict_report.profit_loss_harm_count_vs_original == 0
    assert strict_report.harm_count_vs_original == 0
    assert "final_hit_harm_count_vs_original" in failed_checks
    assert relaxed_report.passed is True


def test_runtime_shadow_replay_excludes_original_hit_harm_when_rule_requires_it() -> None:
    profile = _rule_profile()
    profile["short_odds_replacement_rules"][0]["constraints_json"][
        "exclude_original_hit_harm"
    ] = True
    rule_set = load_short_odds_runtime_rule_set_from_payload(profile)
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        odds=1.12,
        simulated_hp=0.61,
        simulated_hit=True,
        simulated_profit=1.0,
    )
    final_hit_harm_candidate = _replacement(
        rank=2,
        fixture_id="final_hit_harm_candidate",
        odds=1.18,
        simulated_hp=0.605,
        simulated_hit=False,
        simulated_profit=-1.0,
    )

    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    final_answer_hit=True,
                    original_profit=1.0,
                    original_return=3.0,
                    original_hp=0.62,
                    model_top=model_top,
                    replacements=[model_top, final_hit_harm_candidate],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=0,
        ),
    )

    assert report.passed is True
    assert report.changed_final_answer_count == 0
    assert report.final_hit_harm_count_vs_original == 0
    assert report.profit_loss_harm_count_vs_original == 0


def test_runtime_shadow_replay_reports_no_rules_for_disabled_rule() -> None:
    profile = _rule_profile()
    profile["short_odds_replacement_rules"][0]["proposed_production_enabled"] = False
    rule_set = load_short_odds_runtime_rule_set_from_payload(profile)

    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report([_audit_item("item_a")]),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
        ),
    )

    assert report.status == "no_rules"
    assert report.passed is False
    assert report.enabled_rule_count == 0
    assert "short_odds_runtime_shadow_replay:no_enabled_rules" in report.warnings


def test_runtime_shadow_replay_treats_no_change_average_delta_as_zero() -> None:
    rule_set = load_short_odds_runtime_rule_set_from_payload(_rule_profile())

    report = build_historical_short_odds_runtime_shadow_replay_report(
        _audit_report(
            [
                _audit_item(
                    "item_a",
                    model_top=_replacement(
                        rank=1,
                        fixture_id="model_top",
                        odds=1.12,
                        simulated_hp=0.61,
                    ),
                    replacements=[],
                )
            ]
        ),
        rule_set=rule_set,
        options=HistoricalShortOddsRuntimeShadowReplayOptions(
            enable_shadow_replay=True,
            min_final_answer_count=1,
            min_changed_final_answer_count=0,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}
    assert report.passed is True
    assert report.changed_final_answer_count == 0
    assert report.average_hit_probability_delta_vs_original == 0.0
    assert "average_hit_probability_delta_vs_original" not in failed_checks


def test_runtime_shadow_replay_cli_options_loader_and_main(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    rule_path = tmp_path / "rules.json"
    output_path = tmp_path / "runtime_shadow.json"
    audit_path.write_text(
        f"{_audit_report([_audit_item('item_a')]).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rule_path.write_text(_json(_rule_profile()), encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--rule-ids",
            "short_odds_final_answer_replacement_v1",
            "--min-final-answer-count",
            "1",
            "--min-changed-final-answer-count",
            "1",
            "--min-final-answer-hit-rate-delta",
            "0.1",
            "--min-roi-delta",
            "0.2",
            "--min-profit-loss-delta",
            "0.3",
            "--max-harm-count-vs-original",
            "1",
            "--max-final-hit-harm-count-vs-original",
            "2",
            "--max-profit-loss-harm-count-vs-original",
            "3",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-candidate-hit-probability-delta-vs-original",
            "-0.025",
            "--allow-production-change",
            "--max-report-items",
            "12",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert args.audit_report == audit_path
    assert args.rule_profile == rule_path
    assert args.output_path == output_path
    assert options.enable_shadow_replay is True
    assert options.rule_ids == ("short_odds_final_answer_replacement_v1",)
    assert options.min_final_answer_count == 1
    assert options.min_changed_final_answer_count == 1
    assert options.min_final_answer_hit_rate_delta == 0.1
    assert options.min_roi_delta == 0.2
    assert options.min_profit_loss_delta == 0.3
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.min_candidate_hit_probability_delta_vs_original == -0.025
    assert options.require_no_production_change is False
    assert options.max_report_items == 12

    main(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-replay",
            "--min-final-answer-count",
            "1",
            "--min-changed-final-answer-count",
            "1",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "shadow_replay_passed"
    assert payload["production_recommendation_changed"] is False
    assert payload["public_response_changed"] is False
    assert payload["final_hit_harm_count_vs_original"] == 0
    assert payload["profit_loss_harm_count_vs_original"] == 0


def load_short_odds_runtime_rule_set_from_payload(payload: dict[str, object]):
    path = Path("/tmp/nutmeg_short_odds_runtime_rule_test.json")
    path.write_text(_json(payload), encoding="utf-8")
    return load_short_odds_runtime_rule_set(path, enable_shadow_replay=True)


def _rule_profile() -> dict[str, object]:
    return {
        "profile_version": "runtime-shadow-test",
        "calculation_basis": "historical_short_odds_promotion_smoke_v3_1",
        "short_odds_replacement_rules": [
            {
                "rule_id": "short_odds_final_answer_replacement_v1",
                "profile_id": "max_short_odds_within_deficit_v1",
                "proposed_production_enabled": True,
                "production_recommendation_changed": False,
                "allowed_competition_ids": ["EPL", "FRA_LIGUE_1"],
                "excluded_competition_ids": ["ESP_LA_LIGA"],
                "selection_rule": "highest_candidate_hit_probability",
                "constraints_json": {
                    "max_replacements_per_final_answer": 1,
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                    "min_average_hit_probability_delta_vs_original": -0.02,
                    "max_harm_count_vs_original": 0,
                },
                "source_report_keys": {
                    "suite_gate": "suite:test",
                    "final_answer_gate": "final-answer:test",
                    "audit": "audit:test",
                    "competition_gate": "competition:test",
                    "generated_shadow": "shadow:test",
                },
                "rollback_conditions": [
                    "disable_if_production_harm_count_vs_original_exceeds_0",
                    "disable_if_any_isolated_competition_enters_allowed_set",
                    "disable_if_source_report_key_mismatch_or_missing",
                ],
            }
        ],
    }


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-candidate-replacement-audit",
        status="generated",
        slice_count=1,
        competition_count=1,
        final_answer_count=len({item.slice_id for item in items}),
        selected_leg_count=len(items),
        missed_leg_count=0,
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=0,
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _audit_item(
    item_key: str,
    *,
    competition_id: str = "EPL",
    slice_id: str = "slice_a",
    selected_fixture_id: str = "selected_a",
    final_answer_hit: bool = False,
    original_profit: float = -2.0,
    original_return: float = 0.0,
    original_hp: float = 0.62,
    model_top: HistoricalCandidateReplacementSimulation | None = None,
    replacements: list[HistoricalCandidateReplacementSimulation] | None = None,
) -> HistoricalCandidateMarginalAuditItem:
    resolved_model_top = model_top or _replacement(rank=1, fixture_id="model_top")
    resolved_replacements = replacements or [
        resolved_model_top,
        _replacement(
            rank=2,
            fixture_id="candidate",
            odds=1.18,
            simulated_hp=0.611,
            simulated_hit=True,
            simulated_profit=0.4,
        ),
    ]
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id=slice_id,
        competition_id=competition_id,
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        final_answer_actual_hit=final_answer_hit,
        selected_fixture_id=selected_fixture_id,
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.80,
        selected_decimal_odds=1.12,
        selected_model_edge=-0.03,
        selected_score=0.60,
        leg_actual_hit=final_answer_hit,
        original_actual_return=original_return,
        original_profit_loss=original_profit,
        original_hit_probability=original_hp,
        original_roi=original_profit / 2.0,
        original_risk_score=1.0 - original_hp,
        replacement_count=len(resolved_replacements),
        model_top_replacement=resolved_model_top,
        actual_best_replacement=resolved_replacements[-1],
        replacement_candidates=resolved_replacements,
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str,
    probability: float = 0.80,
    odds: float = 1.12,
    model_edge: float = -0.03,
    score: float = 0.60,
    quality: float = 0.50,
    simulated_hp: float = 0.62,
    simulated_hit: bool = False,
    simulated_profit: float = -2.0,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=probability,
        replacement_decimal_odds=odds,
        replacement_model_edge=model_edge,
        replacement_score=score,
        replacement_quality_score=quality,
        replacement_leg_actual_hit=simulated_hit,
        simulated_actual_hit=simulated_hit,
        simulated_actual_return=max(simulated_profit + 2.0, 0.0),
        simulated_profit_loss=simulated_profit,
        simulated_hit_probability=simulated_hp,
        simulated_roi=simulated_profit / 2.0,
        simulated_risk_score=1.0 - simulated_hp,
        actual_return_delta=simulated_profit,
        profit_loss_delta=simulated_profit + 2.0,
        hit_probability_delta=simulated_hp - 0.62,
        roi_delta=simulated_profit / 2.0,
        risk_score_delta=0.0,
        decision="actual_improved" if simulated_profit > -2.0 else "actual_unchanged",
    )


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
