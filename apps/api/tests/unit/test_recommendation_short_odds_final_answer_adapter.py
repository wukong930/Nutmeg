from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.parlay import evaluate_parlay
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.short_odds_final_answer_adapter import (
    ShortOddsFinalAnswerAdapterOptions,
    apply_short_odds_final_answer_adapter,
    main,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)


def test_short_odds_final_answer_adapter_is_disabled_by_default(
    tmp_path: Path,
) -> None:
    selection, candidate_pool = _selection_and_candidate_pool()
    result = apply_short_odds_final_answer_adapter(
        selection,
        candidate_pool=candidate_pool,
        rule_set=_rule_set(tmp_path),
    )

    assert result.status == "disabled"
    assert result.adapter_selection_changed is False
    assert result.adapted_selection == selection
    assert result.public_response_changed is False
    assert "short_odds_final_answer_adapter:disabled_by_feature_flag" in result.warnings


def test_short_odds_final_answer_adapter_applies_opt_in_replacement(
    tmp_path: Path,
) -> None:
    selection, candidate_pool = _selection_and_candidate_pool()
    result = apply_short_odds_final_answer_adapter(
        selection,
        candidate_pool=candidate_pool,
        rule_set=_rule_set(tmp_path),
        options=ShortOddsFinalAnswerAdapterOptions(enable_adapter=True),
    )

    assert result.status == "applied"
    assert result.adapter_selection_changed is True
    assert result.default_path_changed is False
    assert result.public_response_changed is False
    assert result.selected_action is not None
    assert result.selected_action.removed_fixture_id == "selected_a"
    assert result.selected_action.replacement_fixture_id == "replacement_c"
    assert result.selected_action.hit_probability_delta < 0
    assert result.selected_action.hit_probability_delta >= -0.025
    assert result.selected_action.roi_delta > 0
    assert result.adapted_selection.fixture_ids == ["replacement_c", "selected_b"]
    trace = result.adapted_selection.explanation_json["short_odds_final_answer_adapter"]
    assert isinstance(trace, dict)
    assert trace["applied"] is True
    assert trace["public_response_changed"] is False


def test_short_odds_final_answer_adapter_preserves_locked_fixture(
    tmp_path: Path,
) -> None:
    selection, candidate_pool = _selection_and_candidate_pool()
    locked = selection.model_copy(update={"locked_fixture_ids": ["selected_a"]})
    result = apply_short_odds_final_answer_adapter(
        locked,
        candidate_pool=candidate_pool,
        rule_set=_rule_set(tmp_path),
        options=ShortOddsFinalAnswerAdapterOptions(enable_adapter=True),
    )

    assert result.status == "unchanged"
    assert result.adapter_selection_changed is False
    assert result.rejection_reason_counts["removed_fixture_locked"] == 1


def test_short_odds_final_answer_adapter_cli_writes_smoke_report(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "rule_profile.json"
    output_path = tmp_path / "adapter_smoke.json"
    profile_path.write_text(_json(_rule_profile()), encoding="utf-8")

    main(
        [
            "--rule-profile",
            str(profile_path),
            "--output-path",
            str(output_path),
            "--enable-adapter",
            "--competition-id",
            "EPL",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "applied"
    assert payload["adapter_selection_changed"] is True
    assert payload["summary_json"]["public_response_changed"] is False


def _rule_set(tmp_path: Path) -> ShortOddsRuntimeRuleSet:
    path = tmp_path / "rule_profile.json"
    path.write_text(_json(_rule_profile()), encoding="utf-8")
    return load_short_odds_runtime_rule_set(path)


def _rule_profile() -> dict[str, object]:
    return {
        "profile_version": "short-odds-adapter-test",
        "short_odds_replacement_rules": [
            {
                "rule_id": "short_odds_final_answer_replacement_v1",
                "profile_id": "max_short_odds_within_deficit_v1",
                "proposed_production_enabled": True,
                "production_recommendation_changed": False,
                "allowed_competition_ids": ["EPL"],
                "excluded_competition_ids": ["ESP_LA_LIGA"],
                "selection_rule": "highest_candidate_hit_probability",
                "constraints_json": {
                    "selection_rule": "highest_candidate_hit_probability",
                    "max_replacements_per_final_answer": 1,
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                    "min_average_hit_probability_delta_vs_original": -0.02,
                    "min_candidate_hit_probability_delta_vs_original": -0.025,
                    "max_harm_count_vs_original": 0,
                    "max_final_hit_harm_count_vs_original": 0,
                    "max_profit_loss_harm_count_vs_original": 0,
                },
            }
        ],
    }


def _selection_and_candidate_pool() -> (
    tuple[RecommendationSelection, list[ScoredRecommendationCandidate]]
):
    selected_a = _scored_candidate(
        fixture_id="selected_a",
        outcome="home_win",
        probability=0.62,
        decimal_odds=1.12,
        score=0.78,
    )
    selected_b = _scored_candidate(
        fixture_id="selected_b",
        outcome="away_win",
        probability=0.72,
        decimal_odds=1.40,
        score=0.76,
    )
    replacement = _scored_candidate(
        fixture_id="replacement_c",
        outcome="home_win",
        probability=0.611,
        decimal_odds=1.18,
        score=0.77,
    )
    blocked = _scored_candidate(
        fixture_id="blocked_d",
        outcome="draw",
        probability=0.50,
        decimal_odds=2.80,
        score=0.60,
    )
    selected = [selected_a, selected_b]
    evaluation = evaluate_parlay(
        [item.candidate.to_leg_selection() for item in selected],
        pass_type="2x1",
        unit_stake=2.0,
        max_budget=20.0,
    )
    selection = RecommendationSelection(
        pass_type="2x1",
        mode="single",
        selected_candidates=selected,
        evaluation=evaluation,
        total_score=0.77,
        candidate_count=4,
        excluded_candidate_count=0,
    )
    return selection, [selected_a, selected_b, replacement, blocked]


def _scored_candidate(
    *,
    fixture_id: str,
    outcome: str,
    probability: float,
    decimal_odds: float,
    score: float,
) -> ScoredRecommendationCandidate:
    candidate = RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=decimal_odds,
        market_probability=1.0 / decimal_odds,
        model_edge=probability - 1.0 / decimal_odds,
        data_quality_score=88.0,
        model_confidence_score=0.82,
        calibration_score=0.80,
        metadata_json={"competition_id": "EPL"},
    )
    return ScoredRecommendationCandidate(candidate=candidate, score=score)


def _json(value: object) -> str:
    return f"{dumps(value, indent=2)}\n"
