from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations import (
    final_answer_core_candidate_recovery_plan as recovery_plan,
)
from nutmeg.recommendations import quality_signal_diagnostics as diagnostics

_BUILD_REPORT = recovery_plan.build_final_answer_core_candidate_recovery_plan_report
_LOAD_REPORT = recovery_plan.load_final_answer_core_candidate_recovery_plan_report


def test_recovery_plan_prioritizes_negative_competition_segments() -> None:
    report = _BUILD_REPORT(_diagnostic_report())

    assert report.status == "plan_ready"
    assert report.candidate_group_count == 2
    assert report.searchable_candidate_group_count == 2
    assert report.searchable_plan_items[0].source_group_key == (
        "competition_odds_band:ENG_CHAMPIONSHIP:medium_price"
    )
    assert report.searchable_plan_items[0].competition_ids == ("ENG_CHAMPIONSHIP",)
    assert report.searchable_plan_items[0].min_decimal_odds == 1.8
    assert report.searchable_plan_items[0].max_decimal_odds == 2.5
    assert report.searchable_plan_items[0].strength_values == (0.08, 0.12, 0.24)
    assert report.searchable_plan_items[1].source_group_key == (
        "competition_probability_band:FRA_LIGUE_2:low"
    )
    assert report.searchable_plan_items[1].probability_min == 0.35
    assert report.searchable_plan_items[1].probability_max == 0.5
    assert (
        report.recommended_next_search_json["action"]
        == "run_final_answer_quality_signal_profile_grid"
    )


def test_recovery_plan_blocks_already_evidenced_candidate_scope() -> None:
    report = _BUILD_REPORT(
        _diagnostic_report(include_second_negative=False),
        prior_evidence_payloads=[_prior_evidence_payload()],
    )

    assert report.status == "no_searchable_candidate_groups"
    assert report.searchable_candidate_group_count == 0
    assert report.blocked_prior_evidence_count == 1
    assert report.blocked_plan_items[0].decision == "blocked_prior_evidence"
    assert report.blocked_plan_items[0].prior_evidence_keys == ["gate:test"]


def test_recovery_plan_blocks_overlapping_prior_odds_segment() -> None:
    report = _BUILD_REPORT(
        _diagnostic_report(
            groups=[
                _group(
                    "competition_odds_band:ENG_CHAMPIONSHIP:medium_price",
                    "competition_odds_band",
                    "ENG_CHAMPIONSHIP odds medium_price",
                    final_answer_count=9,
                    roi=-0.38,
                    profit_loss=-6.84,
                )
            ]
        ),
        prior_evidence_payloads=[
            {
                "gate_key": "gate:medium-price",
                "summary_json": {
                    "final_answer_quality_signal_competition_ids": [
                        "ENG_CHAMPIONSHIP"
                    ],
                    "final_answer_quality_signal_probability_min": 0.45,
                    "final_answer_quality_signal_probability_max": 0.58,
                    "final_answer_quality_signal_min_decimal_odds": 1.75,
                    "final_answer_quality_signal_max_decimal_odds": 2.20,
                    "final_answer_quality_signal_max_model_edge": -0.02,
                },
            }
        ],
    )

    assert report.status == "no_searchable_candidate_groups"
    assert report.blocked_prior_evidence_count == 1
    assert "prior_evidence_for_overlapping_candidate_scope" in (
        report.blocked_plan_items[0].block_reasons
    )


def test_recovery_plan_reads_prior_grid_candidate_scope() -> None:
    report = _BUILD_REPORT(
        _diagnostic_report(
            groups=[
                _group(
                    "competition_model_edge_band:ENG_CHAMPIONSHIP:negative",
                    "competition_model_edge_band",
                    "ENG_CHAMPIONSHIP model edge negative",
                    final_answer_count=30,
                    roi=-0.156,
                    profit_loss=-9.36,
                )
            ]
        ),
        prior_evidence_payloads=[
            {
                "report_key": "grid:test",
                "candidates": [
                    {
                        "competition_ids": ["ENG_CHAMPIONSHIP"],
                        "probability_min": 0.0,
                        "probability_max": 1.0,
                        "min_decimal_odds": 1.000001,
                        "max_decimal_odds": 20.0,
                        "max_model_edge": 0.0,
                        "strength": 0.08,
                        "roi": 0.02,
                    }
                ],
            }
        ],
    )

    assert report.status == "no_searchable_candidate_groups"
    assert report.blocked_prior_evidence_count == 1
    assert report.blocked_plan_items[0].prior_evidence_keys == ["grid:test"]


def test_recovery_plan_reads_profile_value_guard_prior_evidence() -> None:
    report = _BUILD_REPORT(
        _diagnostic_report(
            groups=[
                _group(
                    "competition_probability_band:ESP_SEGUNDA_DIVISION:low",
                    "competition_probability_band",
                    "ESP_SEGUNDA_DIVISION probability low",
                    final_answer_count=9,
                    roi=-0.075,
                    profit_loss=-4.5,
                )
            ]
        ),
        prior_evidence_payloads=[
            {
                "profile_version": "profile:test",
                "profiles": [
                    {
                        "competition_id": "ESP_SEGUNDA_DIVISION",
                        "final_answer_value_guards": [
                            {
                                "penalty_strength": 0.04,
                                "probability_min": 0.0,
                                "probability_max": 0.5,
                                "min_decimal_odds": 2.0,
                                "max_decimal_odds": 10.0,
                                "max_model_edge": -0.02,
                                "source_report_key": "gate:segunda",
                            }
                        ],
                    }
                ],
            }
        ],
    )

    assert report.status == "no_searchable_candidate_groups"
    assert report.prior_evidence_count == 1
    assert report.blocked_prior_evidence_count == 1
    assert report.blocked_plan_items[0].prior_evidence_keys == [
        "gate:segunda:profile_guard:ESP_SEGUNDA_DIVISION:1"
    ]


def test_recovery_plan_ignores_global_groups_by_default() -> None:
    report = _BUILD_REPORT(
        _diagnostic_report(
            groups=[
                _group(
                    "probability_band:low",
                    "probability_band",
                    "probability low",
                    final_answer_count=40,
                    roi=-0.20,
                    profit_loss=-20.0,
                )
            ]
        )
    )

    assert report.status == "no_searchable_candidate_groups"
    assert report.candidate_group_count == 0


def test_recovery_plan_cli_writes_report(tmp_path: Path) -> None:
    source_path = tmp_path / "quality.json"
    output_path = tmp_path / "plan.json"
    source_path.write_text(
        f"{_diagnostic_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    recovery_plan.main(
        [
            str(source_path),
            "--output-path",
            str(output_path),
            "--no-fail-process",
        ]
    )

    saved = _LOAD_REPORT(output_path)
    assert saved.status == "plan_ready"
    assert saved.searchable_candidate_group_count == 2


def _diagnostic_report(
    *,
    groups: list[diagnostics.HistoricalQualitySignalGroup] | None = None,
    include_second_negative: bool = True,
) -> diagnostics.HistoricalQualitySignalDiagnosticReport:
    resolved_groups = groups
    if resolved_groups is None:
        resolved_groups = [
            _group(
                "competition_probability_band:FRA_LIGUE_2:low",
                "competition_probability_band",
                "FRA_LIGUE_2 probability low",
                final_answer_count=5,
                roi=-0.60,
                profit_loss=-6.0,
            ),
            _group(
                "competition_probability_band:ITA_SERIE_B:medium",
                "competition_probability_band",
                "ITA_SERIE_B probability medium",
                final_answer_count=24,
                roi=0.20,
                profit_loss=25.0,
            ),
        ]
        if include_second_negative:
            resolved_groups.append(
                _group(
                    "competition_odds_band:ENG_CHAMPIONSHIP:medium_price",
                    "competition_odds_band",
                    "ENG_CHAMPIONSHIP odds medium_price",
                    final_answer_count=9,
                    roi=-0.38,
                    profit_loss=-6.84,
                )
            )
    return diagnostics.HistoricalQualitySignalDiagnosticReport(
        report_key="historical_quality_signal_diagnostics:test",
        status="generated",
        slice_count=12,
        competition_count=3,
        final_answer_count=38,
        selected_leg_count=38,
        missed_leg_count=20,
        final_answer_hit_rate=0.47,
        total_stake=100.0,
        actual_return=80.0,
        profit_loss=-20.0,
        roi=-0.2,
        groups=resolved_groups,
        top_negative_signal_groups=[
            group for group in resolved_groups if group.profit_loss < 0
        ],
        top_positive_signal_groups=[
            group for group in resolved_groups if group.profit_loss > 0
        ],
    )


def _group(
    group_key: str,
    group_type: diagnostics.HistoricalQualitySignalGroupType,
    label: str,
    *,
    final_answer_count: int,
    roi: float,
    profit_loss: float,
) -> diagnostics.HistoricalQualitySignalGroup:
    return diagnostics.HistoricalQualitySignalGroup(
        group_key=group_key,
        group_type=group_type,
        label=label,
        band=group_key.split(":")[-1],
        final_answer_count=final_answer_count,
        final_answer_hit_count=1,
        final_answer_hit_rate=0.2,
        selected_leg_count=final_answer_count,
        leg_hit_count=1,
        leg_hit_rate=0.2,
        missed_leg_count=max(final_answer_count - 1, 0),
        total_stake=float(final_answer_count * 2),
        actual_return=float(final_answer_count * 2) + profit_loss,
        profit_loss=profit_loss,
        roi=roi,
        average_probability=0.48,
        average_decimal_odds=1.96,
        average_model_edge=-0.03,
    )


def _prior_evidence_payload() -> dict[str, object]:
    return {
        "gate_key": "gate:test",
        "status": "passed",
        "passed": True,
        "suite_status": "improved",
        "summary_json": {
            "final_answer_quality_signal_competition_ids": ["FRA_LIGUE_2"],
            "final_answer_quality_signal_probability_min": 0.35,
            "final_answer_quality_signal_probability_max": 0.50,
            "final_answer_quality_signal_min_decimal_odds": 1.000001,
            "final_answer_quality_signal_max_decimal_odds": 20.0,
            "final_answer_quality_signal_max_model_edge": 0.0,
            "final_answer_quality_signal_penalty_strength": 0.08,
            "candidate_roi": 0.01,
            "aggregate_deltas": {
                "final_hit_rate_delta": 0.0,
                "roi_delta": 0.01,
                "profit_loss_delta": 2.0,
            },
        },
    }
