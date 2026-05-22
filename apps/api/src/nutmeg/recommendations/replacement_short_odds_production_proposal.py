from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateReport,
)
from nutmeg.recommendations.replacement_short_odds_rolling_admission import (
    HistoricalShortOddsRollingAdmissionReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)
from nutmeg.recommendations.replacement_short_odds_suite_gate import (
    HistoricalShortOddsSuiteGateReport,
)

type HistoricalShortOddsProductionProposalStatus = Literal[
    "production_proposal_ready",
    "shadow_only",
    "blocked",
]
type HistoricalShortOddsProductionProposalCheckStatus = Literal["passed", "failed"]


class HistoricalShortOddsProductionProposalOptions(BaseModel):
    proposal_id: str = "short_odds_final_answer_replacement_v1"
    proposed_profile_version: str = "v3_1_short_odds_replacement_production_proposal"
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=5, ge=0)
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    min_candidate_hit_probability_delta_vs_original: float | None = None
    require_suite_gate_passed: bool = True
    require_final_answer_shadow_candidate: bool = True
    require_runtime_shadow_replay_passed: bool = False
    require_rolling_admission_accepted: bool = False
    min_rolling_active_competition_fold_count: int = Field(default=4, ge=0)
    min_rolling_active_season_fold_count: int = Field(default=5, ge=0)
    min_rolling_active_rolling_fold_count: int = Field(default=4, ge=0)
    max_rolling_failed_fold_count: int = Field(default=0, ge=0)
    require_no_source_production_change: bool = True
    require_isolated_competitions_excluded: bool = True


class HistoricalShortOddsProductionProposalCheck(BaseModel):
    name: str
    status: HistoricalShortOddsProductionProposalCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsProductionRuleProposal(BaseModel):
    rule_id: str
    profile_id: str
    proposed_profile_version: str
    proposed_production_enabled: bool
    production_recommendation_changed: bool = False
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    selection_rule: str | None = None
    constraints_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalShortOddsProductionProposalReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsProductionProposalStatus
    production_recommendation_allowed: bool
    shadow_allowed: bool
    proposal_count: int = Field(ge=0)
    source_suite_gate_report_key: str
    source_final_answer_gate_report_key: str
    source_runtime_shadow_replay_report_key: str | None = None
    source_rolling_admission_report_key: str | None = None
    source_audit_report_key: str | None = None
    source_competition_gate_report_key: str | None = None
    generated_shadow_report_key: str | None = None
    profile_id: str
    ready_competition_ids: list[str] = Field(default_factory=list)
    isolated_competition_ids: list[str] = Field(default_factory=list)
    checks: list[HistoricalShortOddsProductionProposalCheck] = Field(
        default_factory=list
    )
    proposal_rule: HistoricalShortOddsProductionRuleProposal | None = None
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_production_proposal_report(
    suite_gate_report: HistoricalShortOddsSuiteGateReport,
    final_answer_gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | None = None,
    rolling_admission_report: HistoricalShortOddsRollingAdmissionReport | None = None,
    options: HistoricalShortOddsProductionProposalOptions | None = None,
) -> HistoricalShortOddsProductionProposalReport:
    resolved_options = options or HistoricalShortOddsProductionProposalOptions()
    ready_competition_ids = sorted(set(final_answer_gate_report.ready_competition_ids))
    isolated_competition_ids = sorted(set(final_answer_gate_report.isolated_competition_ids))
    checks = _checks(
        suite_gate_report,
        final_answer_gate_report,
        ready_competition_ids=ready_competition_ids,
        isolated_competition_ids=isolated_competition_ids,
        runtime_shadow_replay_report=runtime_shadow_replay_report,
        rolling_admission_report=rolling_admission_report,
        options=resolved_options,
    )
    production_allowed = all(check.status == "passed" for check in checks)
    shadow_allowed = suite_gate_report.passed and (
        final_answer_gate_report.decision == "final_answer_shadow_candidate"
    )
    status = _status(
        production_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
    )
    proposal_rule = _proposal_rule(
        suite_gate_report,
        final_answer_gate_report,
        ready_competition_ids=ready_competition_ids,
        isolated_competition_ids=isolated_competition_ids,
        runtime_shadow_replay_report=runtime_shadow_replay_report,
        rolling_admission_report=rolling_admission_report,
        production_allowed=production_allowed,
        options=resolved_options,
    )
    proposal_profile_set_json = _proposal_profile_set_json(
        proposal_rule,
        status=status,
        production_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
        options=resolved_options,
    )
    warnings = _warnings(
        production_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
        ready_competition_ids=ready_competition_ids,
        isolated_competition_ids=isolated_competition_ids,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_production_proposal_v3_1",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "shadow_allowed": shadow_allowed,
        "proposal_id": resolved_options.proposal_id,
        "proposed_profile_version": resolved_options.proposed_profile_version,
        "source_suite_gate_report_key": suite_gate_report.report_key,
        "source_final_answer_gate_report_key": final_answer_gate_report.report_key,
        "source_runtime_shadow_replay_report_key": (
            runtime_shadow_replay_report.report_key
            if runtime_shadow_replay_report is not None
            else None
        ),
        "source_rolling_admission_report_key": (
            rolling_admission_report.report_key
            if rolling_admission_report is not None
            else None
        ),
        "source_audit_report_key": suite_gate_report.source_audit_report_key,
        "source_competition_gate_report_key": (
            final_answer_gate_report.source_competition_gate_report_key
        ),
        "generated_shadow_report_key": final_answer_gate_report.generated_shadow_report_key,
        "profile_id": final_answer_gate_report.profile_id,
        "ready_competition_ids": ready_competition_ids,
        "isolated_competition_ids": isolated_competition_ids,
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, proposal_rule)
    return HistoricalShortOddsProductionProposalReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=production_allowed,
        shadow_allowed=shadow_allowed,
        proposal_count=1 if proposal_rule is not None else 0,
        source_suite_gate_report_key=suite_gate_report.report_key,
        source_final_answer_gate_report_key=final_answer_gate_report.report_key,
        source_runtime_shadow_replay_report_key=(
            runtime_shadow_replay_report.report_key
            if runtime_shadow_replay_report is not None
            else None
        ),
        source_rolling_admission_report_key=(
            rolling_admission_report.report_key
            if rolling_admission_report is not None
            else None
        ),
        source_audit_report_key=suite_gate_report.source_audit_report_key,
        source_competition_gate_report_key=(
            final_answer_gate_report.source_competition_gate_report_key
        ),
        generated_shadow_report_key=final_answer_gate_report.generated_shadow_report_key,
        profile_id=final_answer_gate_report.profile_id,
        ready_competition_ids=ready_competition_ids,
        isolated_competition_ids=isolated_competition_ids,
        checks=checks,
        proposal_rule=proposal_rule,
        proposal_profile_set_json=proposal_profile_set_json,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_suite_gate_report(
    path: Path,
) -> HistoricalShortOddsSuiteGateReport:
    return HistoricalShortOddsSuiteGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_historical_short_odds_final_answer_gate_report(
    path: Path,
) -> HistoricalShortOddsFinalAnswerGateReport:
    return HistoricalShortOddsFinalAnswerGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_historical_short_odds_runtime_shadow_replay_report(
    path: Path,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_historical_short_odds_rolling_admission_report(
    path: Path,
) -> HistoricalShortOddsRollingAdmissionReport:
    return HistoricalShortOddsRollingAdmissionReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_short_odds_production_proposal_report(
        load_historical_short_odds_suite_gate_report(args.suite_gate_report),
        load_historical_short_odds_final_answer_gate_report(
            args.final_answer_gate_report
        ),
        runtime_shadow_replay_report=(
            load_historical_short_odds_runtime_shadow_replay_report(
                args.runtime_shadow_replay_report
            )
            if args.runtime_shadow_replay_report is not None
            else None
        ),
        rolling_admission_report=(
            load_historical_short_odds_rolling_admission_report(
                args.rolling_admission_report
            )
            if args.rolling_admission_report is not None
            else None
        ),
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if report.status != "production_proposal_ready" and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    suite_gate_report: HistoricalShortOddsSuiteGateReport,
    final_answer_gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    ready_competition_ids: Sequence[str],
    isolated_competition_ids: Sequence[str],
    runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | None,
    rolling_admission_report: HistoricalShortOddsRollingAdmissionReport | None,
    options: HistoricalShortOddsProductionProposalOptions,
) -> list[HistoricalShortOddsProductionProposalCheck]:
    checks = [
        _boolean_check(
            name="suite_gate_passed",
            actual=suite_gate_report.passed,
            expected=True,
            enabled=options.require_suite_gate_passed,
            detail="source suite gate must pass before a production proposal is ready",
        ),
        _equality_check(
            name="final_answer_gate_decision",
            actual=final_answer_gate_report.decision,
            expected="final_answer_shadow_candidate",
            enabled=options.require_final_answer_shadow_candidate,
            detail="source final-answer gate must remain a shadow candidate",
        ),
        _equality_check(
            name="source_final_answer_gate_report_key",
            actual=suite_gate_report.source_final_answer_gate_report_key,
            expected=final_answer_gate_report.report_key,
            enabled=True,
            detail="suite gate must be linked to the supplied final-answer gate",
        ),
        _minimum_check(
            name="final_answer_count",
            actual=suite_gate_report.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="proposal should be backed by enough final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=suite_gate_report.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="proposal should affect enough final answers to be meaningful",
        ),
        _minimum_check(
            name="final_answer_hit_rate_delta",
            actual=suite_gate_report.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="candidate final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=suite_gate_report.roi_delta,
            threshold=options.min_roi_delta,
            detail="candidate realized ROI should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=suite_gate_report.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="candidate realized profit/loss should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_original",
            actual=suite_gate_report.harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail=(
                "compatibility check: candidate should not reduce historical "
                "final-answer profit/loss"
            ),
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_original",
            actual=suite_gate_report.final_hit_harm_count_vs_original,
            threshold=_final_hit_harm_threshold(options),
            detail="candidate should not turn original hits into misses",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_original",
            actual=suite_gate_report.profit_loss_harm_count_vs_original,
            threshold=_profit_loss_harm_threshold(options),
            detail="candidate should not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="average_hit_probability_delta_vs_original",
            actual=suite_gate_report.average_hit_probability_delta_vs_original,
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="expected hit-probability regression must stay inside tolerance",
        ),
        _boolean_check(
            name="runtime_shadow_replay_present",
            actual=runtime_shadow_replay_report is not None,
            expected=True,
            enabled=options.require_runtime_shadow_replay_passed,
            detail="runtime shadow replay evidence is required for guarded proposals",
        ),
        _boolean_check(
            name="rolling_admission_present",
            actual=rolling_admission_report is not None,
            expected=True,
            enabled=options.require_rolling_admission_accepted,
            detail="rolling admission evidence is required for governed promotion",
        ),
        _minimum_check(
            name="ready_competition_count",
            actual=len(ready_competition_ids),
            threshold=1,
            detail="proposal must have at least one allowed competition",
        ),
        _boolean_check(
            name="isolated_competitions_excluded",
            actual=not bool(set(ready_competition_ids) & set(isolated_competition_ids)),
            expected=True,
            enabled=options.require_isolated_competitions_excluded,
            detail="isolated competitions must not be included in allowed competitions",
        ),
    ]
    if runtime_shadow_replay_report is not None:
        runtime_candidate_guard = _runtime_candidate_guard(runtime_shadow_replay_report)
        required_candidate_guard = (
            options.min_candidate_hit_probability_delta_vs_original
            if options.min_candidate_hit_probability_delta_vs_original is not None
            else runtime_candidate_guard
        )
        checks.extend(
            [
                _boolean_check(
                    name="runtime_shadow_replay_passed",
                    actual=runtime_shadow_replay_report.passed,
                    expected=True,
                    enabled=options.require_runtime_shadow_replay_passed,
                    detail="runtime-style shadow replay must pass before promotion",
                ),
                _equality_check(
                    name="runtime_shadow_source_audit_report_key",
                    actual=runtime_shadow_replay_report.source_audit_report_key,
                    expected=suite_gate_report.source_audit_report_key,
                    enabled=True,
                    detail="runtime replay must use the same marginal audit source",
                ),
                _minimum_check(
                    name="runtime_shadow_final_answer_count",
                    actual=runtime_shadow_replay_report.final_answer_count,
                    threshold=options.min_final_answer_count,
                    detail="runtime replay should cover enough final answers",
                ),
                _minimum_check(
                    name="runtime_shadow_changed_final_answer_count",
                    actual=runtime_shadow_replay_report.changed_final_answer_count,
                    threshold=options.min_changed_final_answer_count,
                    detail="runtime replay should affect enough final answers",
                ),
                _minimum_check(
                    name="runtime_shadow_final_answer_hit_rate_delta",
                    actual=runtime_shadow_replay_report.final_answer_hit_rate_delta,
                    threshold=options.min_final_answer_hit_rate_delta,
                    detail="runtime replay final-answer hit rate should not regress",
                ),
                _minimum_check(
                    name="runtime_shadow_roi_delta",
                    actual=runtime_shadow_replay_report.roi_delta,
                    threshold=options.min_roi_delta,
                    detail="runtime replay ROI should not regress",
                ),
                _minimum_check(
                    name="runtime_shadow_profit_loss_delta",
                    actual=runtime_shadow_replay_report.profit_loss_delta,
                    threshold=options.min_profit_loss_delta,
                    detail="runtime replay profit/loss should not regress",
                ),
                _maximum_check(
                    name="runtime_shadow_harm_count_vs_original",
                    actual=runtime_shadow_replay_report.harm_count_vs_original,
                    threshold=options.max_harm_count_vs_original,
                    detail=(
                        "compatibility check: runtime replay should not reduce "
                        "historical final-answer profit/loss"
                    ),
                ),
                _maximum_check(
                    name="runtime_shadow_final_hit_harm_count_vs_original",
                    actual=(
                        runtime_shadow_replay_report
                        .final_hit_harm_count_vs_original
                    ),
                    threshold=_final_hit_harm_threshold(options),
                    detail="runtime replay should not turn original hits into misses",
                ),
                _maximum_check(
                    name="runtime_shadow_profit_loss_harm_count_vs_original",
                    actual=(
                        runtime_shadow_replay_report
                        .profit_loss_harm_count_vs_original
                    ),
                    threshold=_profit_loss_harm_threshold(options),
                    detail=(
                        "runtime replay should not reduce original final-answer "
                        "profit/loss"
                    ),
                ),
                _minimum_check(
                    name="runtime_shadow_average_hit_probability_delta_vs_original",
                    actual=(
                        runtime_shadow_replay_report
                        .average_hit_probability_delta_vs_original
                    ),
                    threshold=options.min_average_hit_probability_delta_vs_original,
                    detail="runtime replay expected hit-probability must be bounded",
                ),
                _minimum_check(
                    name="runtime_shadow_candidate_hit_probability_guard",
                    actual=runtime_candidate_guard,
                    threshold=required_candidate_guard
                    if required_candidate_guard is not None
                    else 0.0,
                    detail="runtime replay must carry the candidate-level guard",
                ),
                _boolean_check(
                    name="runtime_shadow_no_production_change",
                    actual=(
                        not runtime_shadow_replay_report
                        .production_recommendation_changed
                    ),
                    expected=True,
                    enabled=options.require_no_source_production_change,
                    detail="runtime replay must not change production recommendations",
                ),
                _boolean_check(
                    name="runtime_shadow_no_public_change",
                    actual=not runtime_shadow_replay_report.public_response_changed,
                    expected=True,
                    enabled=True,
                    detail="runtime replay must not change public response payloads",
                ),
            ]
        )
    if rolling_admission_report is not None:
        rolling_summary = _mapping(rolling_admission_report.summary_json)
        checks.extend(
            [
                _equality_check(
                    name="rolling_admission_status",
                    actual=rolling_admission_report.status,
                    expected="accepted",
                    enabled=options.require_rolling_admission_accepted,
                    detail="rolling admission must be accepted before promotion",
                ),
                _boolean_check(
                    name="rolling_admission_production_allowed",
                    actual=rolling_admission_report.production_recommendation_allowed,
                    expected=True,
                    enabled=options.require_rolling_admission_accepted,
                    detail="rolling admission must allow production recommendation",
                ),
                _equality_check(
                    name="rolling_admission_source_audit_report_key",
                    actual=rolling_admission_report.source_audit_report_key,
                    expected=suite_gate_report.source_audit_report_key,
                    enabled=True,
                    detail="rolling admission must use the same marginal audit source",
                ),
                _equality_check(
                    name="rolling_admission_overall_runtime_shadow_report_key",
                    actual=rolling_admission_report.overall_runtime_shadow_report_key,
                    expected=(
                        runtime_shadow_replay_report.report_key
                        if runtime_shadow_replay_report is not None
                        else rolling_admission_report.overall_runtime_shadow_report_key
                    ),
                    enabled=runtime_shadow_replay_report is not None,
                    detail=(
                        "rolling admission must be linked to the supplied runtime "
                        "shadow replay"
                    ),
                ),
                _maximum_check(
                    name="rolling_admission_failed_fold_count",
                    actual=rolling_admission_report.failed_fold_count,
                    threshold=options.max_rolling_failed_fold_count,
                    detail="rolling admission must not have failing active folds",
                ),
                _minimum_check(
                    name="rolling_admission_active_competition_fold_count",
                    actual=rolling_admission_report.active_competition_fold_count,
                    threshold=options.min_rolling_active_competition_fold_count,
                    detail="rolling admission must cover enough competition folds",
                ),
                _minimum_check(
                    name="rolling_admission_active_season_fold_count",
                    actual=rolling_admission_report.active_season_fold_count,
                    threshold=options.min_rolling_active_season_fold_count,
                    detail="rolling admission must cover enough season folds",
                ),
                _minimum_check(
                    name="rolling_admission_active_rolling_fold_count",
                    actual=rolling_admission_report.active_rolling_fold_count,
                    threshold=options.min_rolling_active_rolling_fold_count,
                    detail="rolling admission must cover enough rolling-window folds",
                ),
                _minimum_check(
                    name="rolling_admission_overall_final_answer_hit_rate_delta",
                    actual=_optional_float(
                        rolling_summary.get("overall_final_answer_hit_rate_delta")
                    ),
                    threshold=options.min_final_answer_hit_rate_delta,
                    detail="rolling admission overall hit rate should not regress",
                ),
                _minimum_check(
                    name="rolling_admission_overall_roi_delta",
                    actual=_optional_float(rolling_summary.get("overall_roi_delta")),
                    threshold=options.min_roi_delta,
                    detail="rolling admission overall ROI should not regress",
                ),
                _minimum_check(
                    name="rolling_admission_overall_profit_loss_delta",
                    actual=_optional_float(
                        rolling_summary.get("overall_profit_loss_delta")
                    ),
                    threshold=options.min_profit_loss_delta,
                    detail="rolling admission overall profit/loss should not regress",
                ),
                _maximum_check(
                    name="rolling_admission_overall_harm_count_vs_original",
                    actual=_optional_float(
                        rolling_summary.get("overall_harm_count_vs_original")
                    ),
                    threshold=options.max_harm_count_vs_original,
                    detail=(
                        "compatibility check: rolling admission overall replay "
                        "should not reduce final-answer profit/loss"
                    ),
                ),
                _maximum_check(
                    name=(
                        "rolling_admission_overall_final_hit_harm_count_vs_original"
                    ),
                    actual=_optional_float(
                        rolling_summary.get(
                            "overall_final_hit_harm_count_vs_original"
                        )
                    ),
                    threshold=_final_hit_harm_threshold(options),
                    detail=(
                        "rolling admission overall replay should not turn original "
                        "hits into misses"
                    ),
                ),
                _maximum_check(
                    name=(
                        "rolling_admission_overall_profit_loss_harm_count_vs_original"
                    ),
                    actual=_optional_float(
                        rolling_summary.get(
                            "overall_profit_loss_harm_count_vs_original"
                        )
                    ),
                    threshold=_profit_loss_harm_threshold(options),
                    detail=(
                        "rolling admission overall replay should not reduce "
                        "original final-answer profit/loss"
                    ),
                ),
                _minimum_check(
                    name=(
                        "rolling_admission_overall_average_hit_probability_delta_"
                        "vs_original"
                    ),
                    actual=_optional_float(
                        rolling_summary.get(
                            "overall_average_hit_probability_delta_vs_original"
                        )
                    ),
                    threshold=options.min_average_hit_probability_delta_vs_original,
                    detail=(
                        "rolling admission overall expected hit-probability must "
                        "stay inside tolerance"
                    ),
                ),
            ]
        )
    if options.require_no_source_production_change:
        checks.extend(
            [
                _boolean_check(
                    name="suite_gate_no_production_change",
                    actual=not suite_gate_report.production_recommendation_changed,
                    expected=True,
                    enabled=True,
                    detail="suite gate source must not already have changed production",
                ),
                _boolean_check(
                    name="final_answer_gate_no_production_change",
                    actual=not final_answer_gate_report.production_recommendation_changed,
                    expected=True,
                    enabled=True,
                    detail=(
                        "final-answer gate source must not already have changed "
                        "production"
                    ),
                ),
            ]
        )
    return checks


def _proposal_rule(
    suite_gate_report: HistoricalShortOddsSuiteGateReport,
    final_answer_gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    ready_competition_ids: Sequence[str],
    isolated_competition_ids: Sequence[str],
    runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | None,
    rolling_admission_report: HistoricalShortOddsRollingAdmissionReport | None,
    production_allowed: bool,
    options: HistoricalShortOddsProductionProposalOptions,
) -> HistoricalShortOddsProductionRuleProposal | None:
    if not ready_competition_ids:
        return None
    final_options = _mapping(final_answer_gate_report.summary_json.get("options"))
    suite_options = _mapping(suite_gate_report.summary_json.get("options"))
    runtime_candidate_guard = (
        _runtime_candidate_guard(runtime_shadow_replay_report)
        if runtime_shadow_replay_report is not None
        else None
    )
    candidate_guard = (
        options.min_candidate_hit_probability_delta_vs_original
        if options.min_candidate_hit_probability_delta_vs_original is not None
        else runtime_candidate_guard
    )
    constraints = {
        "selection_rule": _string(
            final_answer_gate_report.summary_json.get("selection_rule")
        ),
        "max_replacements_per_final_answer": final_options.get(
            "max_replacements_per_final_answer"
        ),
        "min_replacement_probability": final_options.get(
            "min_replacement_probability"
        ),
        "max_replacement_decimal_odds": final_options.get(
            "max_replacement_decimal_odds"
        ),
        "min_candidate_hit_probability_delta_vs_model_top": final_options.get(
            "min_candidate_hit_probability_delta_vs_model_top"
        ),
        "max_candidate_hit_probability_delta_vs_model_top": final_options.get(
            "max_candidate_hit_probability_delta_vs_model_top"
        ),
        "min_decimal_odds_delta_vs_model_top": final_options.get(
            "min_decimal_odds_delta_vs_model_top"
        ),
        "min_average_hit_probability_delta_vs_original": suite_options.get(
            "min_average_hit_probability_delta_vs_original",
            options.min_average_hit_probability_delta_vs_original,
        ),
        "min_candidate_hit_probability_delta_vs_original": candidate_guard,
        "max_harm_count_vs_original": suite_options.get(
            "max_harm_count_vs_original",
            options.max_harm_count_vs_original,
        ),
        "max_final_hit_harm_count_vs_original": suite_options.get(
            "max_final_hit_harm_count_vs_original",
            _final_hit_harm_threshold(options),
        ),
        "max_profit_loss_harm_count_vs_original": suite_options.get(
            "max_profit_loss_harm_count_vs_original",
            _profit_loss_harm_threshold(options),
        ),
    }
    source_report_keys = {
        "suite_gate": suite_gate_report.report_key,
        "final_answer_gate": final_answer_gate_report.report_key,
        "audit": suite_gate_report.source_audit_report_key,
        "competition_gate": final_answer_gate_report.source_competition_gate_report_key,
        "generated_shadow": final_answer_gate_report.generated_shadow_report_key,
    }
    if runtime_shadow_replay_report is not None:
        source_report_keys["runtime_shadow_replay"] = (
            runtime_shadow_replay_report.report_key
        )
    if rolling_admission_report is not None:
        source_report_keys["rolling_admission"] = rolling_admission_report.report_key
    rolling_summary = (
        _mapping(rolling_admission_report.summary_json)
        if rolling_admission_report is not None
        else {}
    )
    return HistoricalShortOddsProductionRuleProposal(
        rule_id=options.proposal_id,
        profile_id=final_answer_gate_report.profile_id,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=production_allowed,
        production_recommendation_changed=False,
        allowed_competition_ids=list(ready_competition_ids),
        excluded_competition_ids=list(isolated_competition_ids),
        selection_rule=_string(final_answer_gate_report.summary_json.get("selection_rule")),
        constraints_json={key: value for key, value in constraints.items() if value is not None},
        source_report_keys=source_report_keys,
        evidence_json={
            "final_answer_count": suite_gate_report.final_answer_count,
            "changed_final_answer_count": suite_gate_report.changed_final_answer_count,
            "baseline_final_answer_hit_count": (
                suite_gate_report.baseline_final_answer_hit_count
            ),
            "candidate_final_answer_hit_count": (
                suite_gate_report.candidate_final_answer_hit_count
            ),
            "final_answer_hit_rate_delta": (
                suite_gate_report.final_answer_hit_rate_delta
            ),
            "baseline_roi": suite_gate_report.baseline_roi,
            "candidate_roi": suite_gate_report.candidate_roi,
            "roi_delta": suite_gate_report.roi_delta,
            "profit_loss_delta": suite_gate_report.profit_loss_delta,
            "harm_count_vs_original": suite_gate_report.harm_count_vs_original,
            "final_hit_harm_count_vs_original": (
                suite_gate_report.final_hit_harm_count_vs_original
            ),
            "profit_loss_harm_count_vs_original": (
                suite_gate_report.profit_loss_harm_count_vs_original
            ),
            "average_hit_probability_delta_vs_original": (
                suite_gate_report.average_hit_probability_delta_vs_original
            ),
            "runtime_shadow_replay_passed": (
                runtime_shadow_replay_report.passed
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_final_answer_hit_rate_delta": (
                runtime_shadow_replay_report.final_answer_hit_rate_delta
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_roi_delta": (
                runtime_shadow_replay_report.roi_delta
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_profit_loss_delta": (
                runtime_shadow_replay_report.profit_loss_delta
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_harm_count_vs_original": (
                runtime_shadow_replay_report.harm_count_vs_original
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_final_hit_harm_count_vs_original": (
                runtime_shadow_replay_report.final_hit_harm_count_vs_original
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_profit_loss_harm_count_vs_original": (
                runtime_shadow_replay_report.profit_loss_harm_count_vs_original
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_average_hit_probability_delta_vs_original": (
                runtime_shadow_replay_report.average_hit_probability_delta_vs_original
                if runtime_shadow_replay_report is not None
                else None
            ),
            "runtime_candidate_hit_probability_delta_vs_original": candidate_guard,
            "rolling_admission_accepted": (
                rolling_admission_report.status == "accepted"
                if rolling_admission_report is not None
                else None
            ),
            "rolling_admission_production_allowed": (
                rolling_admission_report.production_recommendation_allowed
                if rolling_admission_report is not None
                else None
            ),
            "rolling_overall_runtime_shadow_report_key": (
                rolling_admission_report.overall_runtime_shadow_report_key
                if rolling_admission_report is not None
                else None
            ),
            "rolling_failed_fold_count": (
                rolling_admission_report.failed_fold_count
                if rolling_admission_report is not None
                else None
            ),
            "rolling_active_competition_fold_count": (
                rolling_admission_report.active_competition_fold_count
                if rolling_admission_report is not None
                else None
            ),
            "rolling_active_season_fold_count": (
                rolling_admission_report.active_season_fold_count
                if rolling_admission_report is not None
                else None
            ),
            "rolling_active_rolling_fold_count": (
                rolling_admission_report.active_rolling_fold_count
                if rolling_admission_report is not None
                else None
            ),
            "rolling_overall_final_answer_hit_rate_delta": _optional_float(
                rolling_summary.get("overall_final_answer_hit_rate_delta")
            ),
            "rolling_overall_roi_delta": _optional_float(
                rolling_summary.get("overall_roi_delta")
            ),
            "rolling_overall_profit_loss_delta": _optional_float(
                rolling_summary.get("overall_profit_loss_delta")
            ),
            "rolling_overall_harm_count_vs_original": _optional_float(
                rolling_summary.get("overall_harm_count_vs_original")
            ),
            "rolling_overall_final_hit_harm_count_vs_original": _optional_float(
                rolling_summary.get("overall_final_hit_harm_count_vs_original")
            ),
            "rolling_overall_profit_loss_harm_count_vs_original": _optional_float(
                rolling_summary.get("overall_profit_loss_harm_count_vs_original")
            ),
            "rolling_overall_average_hit_probability_delta_vs_original": (
                _optional_float(
                    rolling_summary.get(
                        "overall_average_hit_probability_delta_vs_original"
                    )
                )
            ),
        },
        rollback_conditions=_rollback_conditions(
            options,
            candidate_guard=candidate_guard,
        ),
        notes=[
            "Governed production proposal artifact only; it does not modify default profiles.",
            "Rule remains internal and must not be exposed as user-facing strategy text.",
            "No automated betting, wallet, payment, or guaranteed-outcome behavior is introduced.",
        ],
    )


def _proposal_profile_set_json(
    proposal_rule: HistoricalShortOddsProductionRuleProposal | None,
    *,
    status: HistoricalShortOddsProductionProposalStatus,
    production_allowed: bool,
    shadow_allowed: bool,
    options: HistoricalShortOddsProductionProposalOptions,
) -> dict[str, object]:
    return {
        "profile_version": options.proposed_profile_version,
        "calculation_basis": "historical_short_odds_production_proposal_v3_1",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "shadow_allowed": shadow_allowed,
        "production_recommendation_changed": False,
        "rules": [
            proposal_rule.model_dump(mode="json")
            for proposal_rule in [proposal_rule]
            if proposal_rule is not None
        ],
        "notes": [
            "Copying this artifact into runtime config requires a separate promotion step.",
            "Isolated competitions must stay excluded until their own gate passes.",
        ],
    }


def _rollback_conditions(
    options: HistoricalShortOddsProductionProposalOptions,
    *,
    candidate_guard: float | None = None,
) -> list[str]:
    resolved_candidate_guard = (
        options.min_candidate_hit_probability_delta_vs_original
        if options.min_candidate_hit_probability_delta_vs_original is not None
        else candidate_guard
    )
    return [
        "disable_if_production_harm_count_vs_original_exceeds_0",
        "disable_if_production_final_hit_harm_count_vs_original_exceeds_0",
        "disable_if_production_profit_loss_harm_count_vs_original_exceeds_0",
        "disable_if_runtime_shadow_replay_report_missing_or_failed",
        "disable_if_rolling_admission_report_missing_or_failed",
        (
            "disable_if_rolling_admission_failed_fold_count_above_"
            f"{options.max_rolling_failed_fold_count}"
        ),
        (
            "disable_if_final_answer_hit_rate_delta_below_"
            f"{options.min_final_answer_hit_rate_delta}"
        ),
        f"disable_if_roi_delta_below_{options.min_roi_delta}",
        f"disable_if_profit_loss_delta_below_{options.min_profit_loss_delta}",
        (
            "disable_if_average_hit_probability_delta_below_"
            f"{options.min_average_hit_probability_delta_vs_original}"
        ),
        *(
            [
                "disable_if_candidate_hit_probability_delta_below_"
                f"{resolved_candidate_guard}"
            ]
            if resolved_candidate_guard is not None
            else []
        ),
        "disable_if_any_isolated_competition_enters_allowed_set",
        "disable_if_source_report_key_mismatch_or_missing",
    ]


def _status(
    *,
    production_allowed: bool,
    shadow_allowed: bool,
) -> HistoricalShortOddsProductionProposalStatus:
    if production_allowed:
        return "production_proposal_ready"
    if shadow_allowed:
        return "shadow_only"
    return "blocked"


def _warnings(
    *,
    production_allowed: bool,
    shadow_allowed: bool,
    ready_competition_ids: Sequence[str],
    isolated_competition_ids: Sequence[str],
) -> list[str]:
    warnings: list[str] = []
    if not production_allowed and shadow_allowed:
        warnings.append("short_odds_production_proposal:shadow_only")
    elif not production_allowed:
        warnings.append("short_odds_production_proposal:blocked")
    if not ready_competition_ids:
        warnings.append("short_odds_production_proposal:no_ready_competitions")
    if isolated_competition_ids:
        warnings.append(
            "short_odds_production_proposal:isolated_competitions_excluded:"
            f"{','.join(isolated_competition_ids)}"
        )
    return warnings


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsProductionProposalCheck:
    if not enabled:
        return HistoricalShortOddsProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsProductionProposalCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _equality_check(
    *,
    name: str,
    actual: str | None,
    expected: str,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsProductionProposalCheck:
    if not enabled:
        return HistoricalShortOddsProductionProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsProductionProposalCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsProductionProposalCheck:
    if actual is None:
        return HistoricalShortOddsProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsProductionProposalCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsProductionProposalCheck:
    if actual is None:
        return HistoricalShortOddsProductionProposalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsProductionProposalCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Build a governed short-odds production proposal from passed shadow gates."
        )
    )
    parser.add_argument("--suite-gate-report", type=Path, required=True)
    parser.add_argument("--final-answer-gate-report", type=Path, required=True)
    parser.add_argument("--runtime-shadow-replay-report", type=Path)
    parser.add_argument("--rolling-admission-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--proposal-id",
        default="short_odds_final_answer_replacement_v1",
    )
    parser.add_argument(
        "--proposed-profile-version",
        default="v3_1_short_odds_replacement_production_proposal",
    )
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=5)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument(
        "--min-candidate-hit-probability-delta-vs-original",
        type=float,
        default=None,
    )
    parser.add_argument("--min-rolling-active-competition-fold-count", type=int, default=4)
    parser.add_argument("--min-rolling-active-season-fold-count", type=int, default=5)
    parser.add_argument("--min-rolling-active-rolling-fold-count", type=int, default=4)
    parser.add_argument("--max-rolling-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-unpassed-suite-gate", action="store_true")
    parser.add_argument("--allow-non-shadow-final-answer-gate", action="store_true")
    parser.add_argument("--allow-unpassed-runtime-shadow-replay", action="store_true")
    parser.add_argument("--allow-unaccepted-rolling-admission", action="store_true")
    parser.add_argument("--allow-source-production-change", action="store_true")
    parser.add_argument("--allow-isolated-competition-overlap", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsProductionProposalOptions:
    return HistoricalShortOddsProductionProposalOptions(
        proposal_id=args.proposal_id,
        proposed_profile_version=args.proposed_profile_version,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        min_candidate_hit_probability_delta_vs_original=(
            args.min_candidate_hit_probability_delta_vs_original
        ),
        require_suite_gate_passed=not args.allow_unpassed_suite_gate,
        require_final_answer_shadow_candidate=not args.allow_non_shadow_final_answer_gate,
        require_runtime_shadow_replay_passed=(
            args.runtime_shadow_replay_report is not None
            and not args.allow_unpassed_runtime_shadow_replay
        ),
        require_rolling_admission_accepted=(
            args.rolling_admission_report is not None
            and not args.allow_unaccepted_rolling_admission
        ),
        min_rolling_active_competition_fold_count=(
            args.min_rolling_active_competition_fold_count
        ),
        min_rolling_active_season_fold_count=(
            args.min_rolling_active_season_fold_count
        ),
        min_rolling_active_rolling_fold_count=(
            args.min_rolling_active_rolling_fold_count
        ),
        max_rolling_failed_fold_count=args.max_rolling_failed_fold_count,
        require_no_source_production_change=not args.allow_source_production_change,
        require_isolated_competitions_excluded=(
            not args.allow_isolated_competition_overlap
        ),
    )


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _final_hit_harm_threshold(
    options: HistoricalShortOddsProductionProposalOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _profit_loss_harm_threshold(
    options: HistoricalShortOddsProductionProposalOptions,
) -> int:
    return (
        options.max_profit_loss_harm_count_vs_original
        if options.max_profit_loss_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _runtime_candidate_guard(
    report: HistoricalShortOddsRuntimeShadowReplayReport,
) -> float | None:
    runtime_options = _mapping(report.summary_json.get("options"))
    option_guard = _optional_float(
        runtime_options.get("min_candidate_hit_probability_delta_vs_original")
    )
    if option_guard is not None:
        return option_guard
    rule_set = _mapping(report.rule_set_json)
    rules = rule_set.get("rules")
    if not isinstance(rules, list):
        return None
    rule_guards: list[float] = []
    for raw_rule in rules:
        rule = _mapping(raw_rule)
        constraints = _mapping(rule.get("constraints_json"))
        rule_guard = _optional_float(
            constraints.get("min_candidate_hit_probability_delta_vs_original")
        )
        if rule_guard is not None:
            rule_guards.append(rule_guard)
    return min(rule_guards) if rule_guards else None


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsProductionProposalCheck],
    proposal_rule: HistoricalShortOddsProductionRuleProposal | None,
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "proposal_rule": (
                    proposal_rule.model_dump(mode="json")
                    if proposal_rule is not None
                    else None
                ),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_production_proposal:{digest}"
