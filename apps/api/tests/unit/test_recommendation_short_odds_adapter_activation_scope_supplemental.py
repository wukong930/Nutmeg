from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.short_odds_adapter_activation_scope_search import (
    ShortOddsAdapterActivationScopeCandidate,
    ShortOddsAdapterActivationScopeSearchReport,
)
from nutmeg.recommendations.short_odds_adapter_activation_scope_supplemental import (
    build_short_odds_adapter_activation_scope_supplemental_report,
    load_short_odds_adapter_activation_scope_supplemental_report,
    main,
)


def test_scope_supplemental_validates_when_all_reports_accept_scope() -> None:
    base = _scope_report(
        report_key="scope_search:base",
        scope=_scope(status="accepted", changed=2, hit_delta=0.02, roi_delta=0.01),
    )
    supplemental = _scope_report(
        report_key="scope_search:supplemental",
        scope=_scope(
            status="accepted",
            changed=3,
            hit_delta=0.03,
            roi_delta=0.02,
            profit_loss_delta=4.2,
        ),
    )

    report = build_short_odds_adapter_activation_scope_supplemental_report(
        base,
        supplemental_reports=[supplemental],
    )

    assert report.status == "supplemental_validated"
    assert report.supplemental_validated is True
    assert report.total_changed_final_answer_count == 5
    assert report.accepted_supplemental_scope_count == 1
    assert report.blocked_supplemental_scope_count == 0
    assert report.supplemental_failure_reason_counts == {}


def test_scope_supplemental_blocks_rejected_supplemental_scope() -> None:
    base = _scope_report(
        report_key="scope_search:base",
        scope=_scope(status="accepted", changed=2, hit_delta=0.02, roi_delta=0.01),
    )
    supplemental = _scope_report(
        report_key="scope_search:supplemental",
        scope=_scope(
            status="rejected",
            changed=7,
            hit_delta=-0.02,
            roi_delta=-0.01,
            profit_loss_delta=-5.86,
            harm_count=6,
            failed_fold_count=6,
            failure_reasons={"final_answer_hit_rate_delta_below_threshold": 6},
        ),
    )

    report = build_short_odds_adapter_activation_scope_supplemental_report(
        base,
        supplemental_reports=[supplemental],
    )

    assert report.status == "supplemental_blocked"
    assert report.supplemental_validated is False
    assert report.accepted_supplemental_scope_count == 0
    assert report.blocked_supplemental_scope_count == 1
    assert report.supplemental_failure_reason_counts[
        "supplemental_scope_accepted"
    ] == 1
    assert report.supplemental_failure_reason_counts[
        "final_answer_hit_rate_delta_below_threshold"
    ] == 6


def test_scope_supplemental_cli_writes_report(tmp_path: Path) -> None:
    base_path = tmp_path / "base_scope.json"
    supplemental_path = tmp_path / "supplemental_scope.json"
    output_path = tmp_path / "scope_supplemental.json"
    base_path.write_text(
        _scope_report(
            report_key="scope_search:base",
            scope=_scope(status="accepted", changed=2, hit_delta=0.02, roi_delta=0.01),
        ).model_dump_json(),
        encoding="utf-8",
    )
    supplemental_path.write_text(
        _scope_report(
            report_key="scope_search:supplemental",
            scope=_scope(
                status="accepted",
                changed=3,
                hit_delta=0.03,
                roi_delta=0.02,
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )

    main(
        [
            "--base-scope-report",
            str(base_path),
            "--supplemental-scope-report",
            str(supplemental_path),
            "--output-path",
            str(output_path),
        ]
    )

    saved = load_short_odds_adapter_activation_scope_supplemental_report(output_path)
    assert saved.status == "supplemental_validated"
    assert saved.scope_competition_ids == ["ESP_SEGUNDA_DIVISION", "FRA_LIGUE_2"]


def _scope_report(
    *,
    report_key: str,
    scope: ShortOddsAdapterActivationScopeCandidate,
) -> ShortOddsAdapterActivationScopeSearchReport:
    return ShortOddsAdapterActivationScopeSearchReport(
        report_key=report_key,
        status="accepted_scope_found" if scope.status == "accepted" else "shadow_only_scopes",
        accepted_scope_found=scope.status == "accepted",
        shadow_allowed=scope.shadow_allowed,
        source_grid_report_key="activation_grid:test",
        source_audit_report_key="historical_candidate_marginal_audit:test",
        source_rule_profile_version="short_odds_rule_test_v1",
        selected_source_candidate_count=1,
        scope_candidate_count=1,
        accepted_scope_count=1 if scope.status == "accepted" else 0,
        shadow_only_scope_count=1 if scope.status == "shadow_only" else 0,
        rejected_scope_count=1 if scope.status == "rejected" else 0,
        best_scope_key=scope.scope_key,
        best_scope=scope,
        scopes=[scope],
    )


def _scope(
    *,
    status: str,
    changed: int,
    hit_delta: float,
    roi_delta: float,
    profit_loss_delta: float = 3.6,
    harm_count: int = 0,
    failed_fold_count: int = 0,
    failure_reasons: dict[str, int] | None = None,
) -> ShortOddsAdapterActivationScopeCandidate:
    return ShortOddsAdapterActivationScopeCandidate(
        scope_key=f"scope:{status}:{changed}",
        status=status,  # type: ignore[arg-type]
        source_candidate_key="short_odds_adapter_activation_grid_candidate:test",
        source_candidate_status="accepted",
        scope_competition_ids=["ESP_SEGUNDA_DIVISION", "FRA_LIGUE_2"],
        scope_competition_count=2,
        production_candidate_allowed=status == "accepted",
        shadow_allowed=status in {"accepted", "shadow_only"},
        min_replacement_probability=0.48,
        max_replacement_decimal_odds=2.1,
        min_candidate_hit_probability_delta_vs_model_top=-0.05,
        min_candidate_hit_probability_delta_vs_original=-0.08,
        overall_runtime_shadow_report_key="runtime:test",
        rolling_admission_report_key="rolling:test",
        rolling_admission_status=status,
        overall_final_answer_count=56,
        overall_changed_final_answer_count=changed,
        overall_final_answer_hit_rate_delta=hit_delta,
        overall_roi_delta=roi_delta,
        overall_profit_loss_delta=profit_loss_delta,
        overall_harm_count_vs_original=harm_count,
        overall_final_hit_harm_count_vs_original=harm_count,
        overall_profit_loss_harm_count_vs_original=harm_count,
        overall_average_hit_probability_delta_vs_original=-0.03,
        rolling_active_competition_fold_count=2,
        rolling_active_season_fold_count=2,
        rolling_active_rolling_fold_count=3,
        rolling_failed_fold_count=failed_fold_count,
        rolling_failed_checks=["failed_fold_count"] if failed_fold_count else [],
        rolling_failed_fold_reason_counts=failure_reasons or {},
    )
