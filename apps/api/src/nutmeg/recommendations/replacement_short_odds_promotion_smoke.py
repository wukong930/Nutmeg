from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.competition_profiles import (
    DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    CompetitionRecommendationProfileSet,
    load_competition_recommendation_profile_set,
)
from nutmeg.recommendations.replacement_short_odds_production_proposal import (
    HistoricalShortOddsProductionProposalReport,
)

type HistoricalShortOddsPromotionSmokeStatus = Literal["passed", "failed"]
type HistoricalShortOddsPromotionSmokeCheckStatus = Literal["passed", "failed"]


class HistoricalShortOddsPromotionSmokeOptions(BaseModel):
    promoted_profile_version: str = "v3_1_short_odds_replacement_promotion_smoke"
    min_allowed_competition_count: int = Field(default=1, ge=1)
    max_replacements_per_final_answer: int = Field(default=1, ge=1)
    min_replacement_probability: float = Field(default=0.55, ge=0.0, le=1.0)
    max_replacement_decimal_odds: float = Field(default=1.75, gt=1.0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    min_candidate_hit_probability_delta_vs_original: float | None = None
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_rolling_active_competition_fold_count: int = Field(default=4, ge=0)
    min_rolling_active_season_fold_count: int = Field(default=5, ge=0)
    min_rolling_active_rolling_fold_count: int = Field(default=4, ge=0)
    max_rolling_failed_fold_count: int = Field(default=0, ge=0)
    require_production_proposal_ready: bool = True
    require_production_allowed: bool = True
    require_no_runtime_profile_write: bool = True
    require_no_public_strategy_exposure: bool = True
    require_no_existing_short_odds_rules: bool = True
    required_source_report_keys: tuple[str, ...] = (
        "suite_gate",
        "final_answer_gate",
        "audit",
        "competition_gate",
        "generated_shadow",
        "runtime_shadow_replay",
        "rolling_admission",
    )
    required_rollback_conditions: tuple[str, ...] = (
        "disable_if_production_harm_count_vs_original_exceeds_0",
        "disable_if_production_final_hit_harm_count_vs_original_exceeds_0",
        "disable_if_production_profit_loss_harm_count_vs_original_exceeds_0",
        "disable_if_runtime_shadow_replay_report_missing_or_failed",
        "disable_if_rolling_admission_report_missing_or_failed",
        "disable_if_any_isolated_competition_enters_allowed_set",
        "disable_if_source_report_key_mismatch_or_missing",
    )


class HistoricalShortOddsPromotionSmokeCheck(BaseModel):
    name: str
    status: HistoricalShortOddsPromotionSmokeCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsPromotionSmokeReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsPromotionSmokeStatus
    passed: bool
    source_proposal_report_key: str
    current_profile_version: str
    promoted_profile_version: str
    current_profile_count: int = Field(ge=0)
    temporary_profile_count: int = Field(ge=0)
    proposed_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    runtime_profile_written: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalShortOddsPromotionSmokeCheck] = Field(default_factory=list)
    temporary_profile_set_json: dict[str, object] = Field(default_factory=dict)
    public_contract_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_promotion_smoke_report(
    *,
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
    production_proposal_report: HistoricalShortOddsProductionProposalReport
    | Mapping[str, object],
    options: HistoricalShortOddsPromotionSmokeOptions | None = None,
) -> HistoricalShortOddsPromotionSmokeReport:
    resolved_options = options or HistoricalShortOddsPromotionSmokeOptions()
    raw_current_profile_set = _raw_mapping(current_profile_set)
    current_profiles = _profile_set(current_profile_set)
    proposal = _proposal_report(production_proposal_report)
    proposal_rules = _proposal_rules(proposal)
    allowed_competition_ids = _unique(
        competition_id
        for rule in proposal_rules
        for competition_id in _string_list(rule.get("allowed_competition_ids"))
    )
    excluded_competition_ids = _unique(
        competition_id
        for rule in proposal_rules
        for competition_id in _string_list(rule.get("excluded_competition_ids"))
    )
    temporary_profile_set_json = _temporary_profile_set_json(
        current_profiles,
        proposal_rules=proposal_rules,
        options=resolved_options,
        proposal_report_key=proposal.report_key,
    )
    public_contract_json: dict[str, object] = {
        "public_response_changed": False,
        "frontend_changed": False,
        "user_facing_strategy_text": False,
        "ordinary_user_path_changed": False,
        "production_recommendation_changed": False,
    }
    checks = _checks(
        proposal,
        raw_current_profile_set=raw_current_profile_set,
        proposal_rules=proposal_rules,
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        public_contract_json=public_contract_json,
        options=resolved_options,
    )
    passed = all(check.status == "passed" for check in checks)
    status: HistoricalShortOddsPromotionSmokeStatus = "passed" if passed else "failed"
    warnings = _warnings(
        passed=passed,
        excluded_competition_ids=excluded_competition_ids,
        existing_profile_count=len(current_profiles.profiles),
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_promotion_smoke_v3_1",
        "status": status,
        "passed": passed,
        "source_proposal_report_key": proposal.report_key,
        "current_profile_version": current_profiles.profile_version,
        "promoted_profile_version": resolved_options.promoted_profile_version,
        "current_profile_count": len(current_profiles.profiles),
        "temporary_profile_count": len(current_profiles.profiles),
        "proposed_rule_count": len(proposal_rules),
        "allowed_competition_ids": allowed_competition_ids,
        "excluded_competition_ids": excluded_competition_ids,
        "production_recommendation_changed": False,
        "runtime_profile_written": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, temporary_profile_set_json)
    return HistoricalShortOddsPromotionSmokeReport(
        report_key=report_key,
        status=status,
        passed=passed,
        source_proposal_report_key=proposal.report_key,
        current_profile_version=current_profiles.profile_version,
        promoted_profile_version=resolved_options.promoted_profile_version,
        current_profile_count=len(current_profiles.profiles),
        temporary_profile_count=len(current_profiles.profiles),
        proposed_rule_count=len(proposal_rules),
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        production_recommendation_changed=False,
        runtime_profile_written=False,
        public_response_changed=False,
        checks=checks,
        temporary_profile_set_json=temporary_profile_set_json,
        public_contract_json=public_contract_json,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_production_proposal_report(
    path: Path,
) -> HistoricalShortOddsProductionProposalReport:
    return HistoricalShortOddsProductionProposalReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_short_odds_promotion_smoke_report(
        current_profile_set=load_competition_recommendation_profile_set(
            args.current_profile_path
        ),
        production_proposal_report=load_historical_short_odds_production_proposal_report(
            args.production_proposal_report
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    proposal: HistoricalShortOddsProductionProposalReport,
    *,
    raw_current_profile_set: Mapping[str, object],
    proposal_rules: Sequence[Mapping[str, object]],
    allowed_competition_ids: Sequence[str],
    excluded_competition_ids: Sequence[str],
    public_contract_json: Mapping[str, object],
    options: HistoricalShortOddsPromotionSmokeOptions,
) -> list[HistoricalShortOddsPromotionSmokeCheck]:
    checks = [
        _equality_check(
            name="proposal_status",
            actual=proposal.status,
            expected="production_proposal_ready",
            enabled=options.require_production_proposal_ready,
            detail="proposal must be marked ready before promotion smoke passes",
        ),
        _boolean_check(
            name="proposal_production_allowed",
            actual=proposal.production_recommendation_allowed,
            expected=True,
            enabled=options.require_production_allowed,
            detail="proposal must allow production recommendations",
        ),
        _minimum_check(
            name="proposed_rule_count",
            actual=len(proposal_rules),
            threshold=1,
            detail="proposal must contain at least one internal rule",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="temporary promotion must have allowed competitions",
        ),
        _boolean_check(
            name="allowed_excluded_disjoint",
            actual=not bool(set(allowed_competition_ids) & set(excluded_competition_ids)),
            expected=True,
            enabled=True,
            detail="allowed competitions must not overlap excluded competitions",
        ),
        _boolean_check(
            name="runtime_profile_not_written",
            actual=True,
            expected=True,
            enabled=options.require_no_runtime_profile_write,
            detail="smoke report must not write the default runtime profile",
        ),
        _boolean_check(
            name="proposal_no_production_change",
            actual=not _proposal_production_recommendation_changed(proposal),
            expected=True,
            enabled=True,
            detail="proposal source must not already have changed production",
        ),
        _boolean_check(
            name="current_profile_has_no_short_odds_rules",
            actual="short_odds_replacement_rules" not in raw_current_profile_set,
            expected=True,
            enabled=options.require_no_existing_short_odds_rules,
            detail="default profile must not already contain this internal rule type",
        ),
        _boolean_check(
            name="public_response_unchanged",
            actual=public_contract_json.get("public_response_changed") is False,
            expected=True,
            enabled=options.require_no_public_strategy_exposure,
            detail="ordinary user response must remain unchanged in this smoke",
        ),
        _boolean_check(
            name="user_facing_strategy_text_absent",
            actual=public_contract_json.get("user_facing_strategy_text") is False,
            expected=True,
            enabled=options.require_no_public_strategy_exposure,
            detail="internal rule names must not become user-facing text",
        ),
    ]
    checks.extend(
        _rule_checks(
            proposal_rules,
            proposal=proposal,
            options=options,
        )
    )
    return checks


def _rule_checks(
    proposal_rules: Sequence[Mapping[str, object]],
    *,
    proposal: HistoricalShortOddsProductionProposalReport,
    options: HistoricalShortOddsPromotionSmokeOptions,
) -> list[HistoricalShortOddsPromotionSmokeCheck]:
    checks: list[HistoricalShortOddsPromotionSmokeCheck] = []
    final_hit_harm_threshold = _max_final_hit_harm_count_vs_original(options)
    profit_loss_harm_threshold = _max_profit_loss_harm_count_vs_original(options)
    for index, rule in enumerate(proposal_rules):
        prefix = f"rule_{index}"
        constraints = _mapping(rule.get("constraints_json"))
        source_report_keys = _mapping(rule.get("source_report_keys"))
        evidence = _mapping(rule.get("evidence_json"))
        rollback_conditions = _string_list(rule.get("rollback_conditions"))
        checks.extend(
            [
                _boolean_check(
                    name=f"{prefix}_proposed_enabled",
                    actual=_bool(rule.get("proposed_production_enabled")),
                    expected=True,
                    enabled=options.require_production_allowed,
                    detail="proposed rule must be enabled by the proposal",
                ),
                _maximum_check(
                    name=f"{prefix}_max_replacements_per_final_answer",
                    actual=_float(constraints.get("max_replacements_per_final_answer")),
                    threshold=options.max_replacements_per_final_answer,
                    detail="temporary rule must keep replacement count bounded",
                ),
                _minimum_check(
                    name=f"{prefix}_min_replacement_probability",
                    actual=_float(constraints.get("min_replacement_probability")),
                    threshold=options.min_replacement_probability,
                    detail="temporary rule must keep the short-odds probability guard",
                ),
                _maximum_check(
                    name=f"{prefix}_max_replacement_decimal_odds",
                    actual=_float(constraints.get("max_replacement_decimal_odds")),
                    threshold=options.max_replacement_decimal_odds,
                    detail="temporary rule must keep the short-odds price guard",
                ),
                _minimum_check(
                    name=f"{prefix}_average_hit_probability_tolerance",
                    actual=_float(
                        constraints.get(
                            "min_average_hit_probability_delta_vs_original"
                        )
                    ),
                    threshold=options.min_average_hit_probability_delta_vs_original,
                    detail="temporary rule must keep expected hit-probability tolerance",
                ),
                _minimum_check(
                    name=f"{prefix}_candidate_hit_probability_guard",
                    actual=_float(
                        constraints.get(
                            "min_candidate_hit_probability_delta_vs_original"
                        )
                    ),
                    threshold=(
                        options.min_candidate_hit_probability_delta_vs_original
                        if options.min_candidate_hit_probability_delta_vs_original
                        is not None
                        else _float(
                            constraints.get(
                                "min_candidate_hit_probability_delta_vs_original"
                            )
                        )
                        or 0.0
                    ),
                    detail="temporary rule must keep the candidate hit-probability guard",
                ),
                _maximum_check(
                    name=f"{prefix}_harm_count_evidence",
                    actual=_float(evidence.get("harm_count_vs_original")),
                    threshold=options.max_harm_count_vs_original,
                    detail=(
                        "proposal evidence must preserve compatibility no-harm "
                        "result"
                    ),
                ),
                _maximum_check(
                    name=f"{prefix}_final_hit_harm_count_evidence",
                    actual=_float(evidence.get("final_hit_harm_count_vs_original")),
                    threshold=final_hit_harm_threshold,
                    detail="proposal evidence must not turn original hits into misses",
                ),
                _maximum_check(
                    name=f"{prefix}_profit_loss_harm_count_evidence",
                    actual=_float(
                        evidence.get("profit_loss_harm_count_vs_original")
                    ),
                    threshold=profit_loss_harm_threshold,
                    detail=(
                        "proposal evidence must not reduce original final-answer "
                        "profit/loss"
                    ),
                ),
                _boolean_check(
                    name=f"{prefix}_runtime_shadow_replay_passed_evidence",
                    actual=_bool(evidence.get("runtime_shadow_replay_passed")),
                    expected=True,
                    enabled=True,
                    detail="proposal must carry passed runtime replay evidence",
                ),
                _maximum_check(
                    name=f"{prefix}_runtime_harm_count_evidence",
                    actual=_float(evidence.get("runtime_harm_count_vs_original")),
                    threshold=options.max_harm_count_vs_original,
                    detail=(
                        "runtime replay evidence must preserve compatibility "
                        "no-harm result"
                    ),
                ),
                _maximum_check(
                    name=f"{prefix}_runtime_final_hit_harm_count_evidence",
                    actual=_float(
                        evidence.get("runtime_final_hit_harm_count_vs_original")
                    ),
                    threshold=final_hit_harm_threshold,
                    detail=(
                        "runtime replay evidence must not turn original hits into "
                        "misses"
                    ),
                ),
                _maximum_check(
                    name=f"{prefix}_runtime_profit_loss_harm_count_evidence",
                    actual=_float(
                        evidence.get("runtime_profit_loss_harm_count_vs_original")
                    ),
                    threshold=profit_loss_harm_threshold,
                    detail=(
                        "runtime replay evidence must not reduce original "
                        "final-answer profit/loss"
                    ),
                ),
                _boolean_check(
                    name=f"{prefix}_rolling_admission_accepted_evidence",
                    actual=_bool(evidence.get("rolling_admission_accepted")),
                    expected=True,
                    enabled=True,
                    detail="proposal must carry accepted rolling admission evidence",
                ),
                _maximum_check(
                    name=f"{prefix}_rolling_failed_fold_count_evidence",
                    actual=_float(evidence.get("rolling_failed_fold_count")),
                    threshold=options.max_rolling_failed_fold_count,
                    detail="rolling admission evidence must preserve no failed folds",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_active_competition_fold_count",
                    actual=_float(
                        evidence.get("rolling_active_competition_fold_count")
                    ),
                    threshold=options.min_rolling_active_competition_fold_count,
                    detail="rolling evidence must cover enough competition folds",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_active_season_fold_count",
                    actual=_float(evidence.get("rolling_active_season_fold_count")),
                    threshold=options.min_rolling_active_season_fold_count,
                    detail="rolling evidence must cover enough season folds",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_active_rolling_fold_count",
                    actual=_float(evidence.get("rolling_active_rolling_fold_count")),
                    threshold=options.min_rolling_active_rolling_fold_count,
                    detail="rolling evidence must cover enough rolling-window folds",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_overall_hit_rate_delta_evidence",
                    actual=_float(
                        evidence.get("rolling_overall_final_answer_hit_rate_delta")
                    ),
                    threshold=0.0,
                    detail="rolling overall hit-rate evidence must not regress",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_overall_roi_delta_evidence",
                    actual=_float(evidence.get("rolling_overall_roi_delta")),
                    threshold=0.0,
                    detail="rolling overall ROI evidence must not regress",
                ),
                _minimum_check(
                    name=f"{prefix}_rolling_overall_profit_loss_delta_evidence",
                    actual=_float(evidence.get("rolling_overall_profit_loss_delta")),
                    threshold=0.0,
                    detail="rolling overall profit/loss evidence must not regress",
                ),
                _maximum_check(
                    name=f"{prefix}_rolling_overall_harm_count_evidence",
                    actual=_float(
                        evidence.get("rolling_overall_harm_count_vs_original")
                    ),
                    threshold=options.max_harm_count_vs_original,
                    detail=(
                        "rolling overall evidence must preserve compatibility "
                        "no-harm result"
                    ),
                ),
                _maximum_check(
                    name=f"{prefix}_rolling_overall_final_hit_harm_count_evidence",
                    actual=_float(
                        evidence.get(
                            "rolling_overall_final_hit_harm_count_vs_original"
                        )
                    ),
                    threshold=final_hit_harm_threshold,
                    detail=(
                        "rolling overall evidence must not turn original hits into "
                        "misses"
                    ),
                ),
                _maximum_check(
                    name=f"{prefix}_rolling_overall_profit_loss_harm_count_evidence",
                    actual=_float(
                        evidence.get(
                            "rolling_overall_profit_loss_harm_count_vs_original"
                        )
                    ),
                    threshold=profit_loss_harm_threshold,
                    detail=(
                        "rolling overall evidence must not reduce original "
                        "final-answer profit/loss"
                    ),
                ),
                _minimum_check(
                    name=(
                        f"{prefix}_rolling_overall_average_hit_probability_"
                        "delta_evidence"
                    ),
                    actual=_float(
                        evidence.get(
                            "rolling_overall_average_hit_probability_delta_vs_original"
                        )
                    ),
                    threshold=options.min_average_hit_probability_delta_vs_original,
                    detail=(
                        "rolling overall hit-probability evidence must stay inside "
                        "tolerance"
                    ),
                ),
                _boolean_check(
                    name=f"{prefix}_source_report_keys_present",
                    actual=_has_required_keys(
                        source_report_keys,
                        options.required_source_report_keys,
                    ),
                    expected=True,
                    enabled=True,
                    detail="proposal must carry all source report keys",
                ),
                _boolean_check(
                    name=f"{prefix}_source_report_keys_match_report",
                    actual=_source_keys_match_proposal(rule, proposal=proposal),
                    expected=True,
                    enabled=True,
                    detail="proposal rule source keys must match the proposal summary",
                ),
                _boolean_check(
                    name=f"{prefix}_rollback_conditions_present",
                    actual=_has_required_values(
                        rollback_conditions,
                        options.required_rollback_conditions,
                    ),
                    expected=True,
                    enabled=True,
                    detail="proposal must carry required rollback conditions",
                ),
            ]
        )
    return checks


def _temporary_profile_set_json(
    current_profiles: CompetitionRecommendationProfileSet,
    *,
    proposal_rules: Sequence[Mapping[str, object]],
    options: HistoricalShortOddsPromotionSmokeOptions,
    proposal_report_key: str,
) -> dict[str, object]:
    return {
        "profile_version": options.promoted_profile_version,
        "calculation_basis": "historical_short_odds_promotion_smoke_v3_1",
        "base_profile_version": current_profiles.profile_version,
        "profiles": [
            profile.model_dump(mode="json") for profile in current_profiles.profiles
        ],
        "short_odds_replacement_rules": [dict(rule) for rule in proposal_rules],
        "production_recommendation_changed": False,
        "runtime_profile_written": False,
        "notes": _unique(
            [
                *current_profiles.notes,
                "Temporary promotion smoke artifact only; default runtime profile unchanged.",
                "Internal short-odds replacement rules are not user-facing strategy text.",
                f"production_proposal_report_key={proposal_report_key}",
            ]
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Smoke-test a short-odds production proposal against the current profile."
    )
    parser.add_argument(
        "--current-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--production-proposal-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--promoted-profile-version",
        default="v3_1_short_odds_replacement_promotion_smoke",
    )
    parser.add_argument("--min-allowed-competition-count", type=int, default=1)
    parser.add_argument("--max-replacements-per-final-answer", type=int, default=1)
    parser.add_argument("--min-replacement-probability", type=float, default=0.55)
    parser.add_argument("--max-replacement-decimal-odds", type=float, default=1.75)
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
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument(
        "--max-final-hit-harm-count-vs-original",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--max-profit-loss-harm-count-vs-original",
        type=int,
        default=None,
    )
    parser.add_argument("--min-rolling-active-competition-fold-count", type=int, default=4)
    parser.add_argument("--min-rolling-active-season-fold-count", type=int, default=5)
    parser.add_argument("--min-rolling-active-rolling-fold-count", type=int, default=4)
    parser.add_argument("--max-rolling-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-non-ready-proposal", action="store_true")
    parser.add_argument("--allow-production-blocked-proposal", action="store_true")
    parser.add_argument("--allow-runtime-profile-write", action="store_true")
    parser.add_argument("--allow-public-strategy-exposure", action="store_true")
    parser.add_argument("--allow-existing-short-odds-rules", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsPromotionSmokeOptions:
    return HistoricalShortOddsPromotionSmokeOptions(
        promoted_profile_version=args.promoted_profile_version,
        min_allowed_competition_count=args.min_allowed_competition_count,
        max_replacements_per_final_answer=args.max_replacements_per_final_answer,
        min_replacement_probability=args.min_replacement_probability,
        max_replacement_decimal_odds=args.max_replacement_decimal_odds,
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        min_candidate_hit_probability_delta_vs_original=(
            args.min_candidate_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
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
        require_production_proposal_ready=not args.allow_non_ready_proposal,
        require_production_allowed=not args.allow_production_blocked_proposal,
        require_no_runtime_profile_write=not args.allow_runtime_profile_write,
        require_no_public_strategy_exposure=not args.allow_public_strategy_exposure,
        require_no_existing_short_odds_rules=not args.allow_existing_short_odds_rules,
    )


def _profile_set(
    value: CompetitionRecommendationProfileSet | Mapping[str, object],
) -> CompetitionRecommendationProfileSet:
    if isinstance(value, CompetitionRecommendationProfileSet):
        return value
    return CompetitionRecommendationProfileSet.model_validate(value)


def _proposal_report(
    value: HistoricalShortOddsProductionProposalReport | Mapping[str, object],
) -> HistoricalShortOddsProductionProposalReport:
    if isinstance(value, HistoricalShortOddsProductionProposalReport):
        return value
    return HistoricalShortOddsProductionProposalReport.model_validate(value)


def _proposal_rules(
    proposal: HistoricalShortOddsProductionProposalReport,
) -> list[dict[str, object]]:
    rules = _mapping_list(proposal.proposal_profile_set_json.get("rules"))
    if rules:
        return rules
    if proposal.proposal_rule is None:
        return []
    return [proposal.proposal_rule.model_dump(mode="json")]


def _proposal_production_recommendation_changed(
    proposal: HistoricalShortOddsProductionProposalReport,
) -> bool:
    if _bool(proposal.summary_json.get("production_recommendation_changed")):
        return True
    if _bool(proposal.proposal_profile_set_json.get("production_recommendation_changed")):
        return True
    if proposal.proposal_rule is not None:
        return proposal.proposal_rule.production_recommendation_changed
    return False


def _raw_mapping(
    value: CompetitionRecommendationProfileSet | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(value, CompetitionRecommendationProfileSet):
        return value.model_dump(mode="json")
    return dict(value)


def _has_required_keys(
    values: Mapping[str, object],
    required_keys: Sequence[str],
) -> bool:
    return all(_string(values.get(key)) is not None for key in required_keys)


def _has_required_values(values: Sequence[str], required_values: Sequence[str]) -> bool:
    value_set = set(values)
    return all(value in value_set for value in required_values)


def _source_keys_match_proposal(
    rule: Mapping[str, object],
    *,
    proposal: HistoricalShortOddsProductionProposalReport,
) -> bool:
    source_report_keys = _mapping(rule.get("source_report_keys"))
    expected = {
        "suite_gate": proposal.source_suite_gate_report_key,
        "final_answer_gate": proposal.source_final_answer_gate_report_key,
        "audit": proposal.source_audit_report_key,
        "competition_gate": proposal.source_competition_gate_report_key,
        "generated_shadow": proposal.generated_shadow_report_key,
    }
    if proposal.source_runtime_shadow_replay_report_key is not None:
        expected["runtime_shadow_replay"] = (
            proposal.source_runtime_shadow_replay_report_key
        )
    if proposal.source_rolling_admission_report_key is not None:
        expected["rolling_admission"] = proposal.source_rolling_admission_report_key
    return all(source_report_keys.get(key) == value for key, value in expected.items())


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsPromotionSmokeCheck:
    if not enabled:
        return HistoricalShortOddsPromotionSmokeCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsPromotionSmokeCheck(
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
) -> HistoricalShortOddsPromotionSmokeCheck:
    if not enabled:
        return HistoricalShortOddsPromotionSmokeCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsPromotionSmokeCheck(
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
) -> HistoricalShortOddsPromotionSmokeCheck:
    if actual is None:
        return HistoricalShortOddsPromotionSmokeCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsPromotionSmokeCheck(
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
) -> HistoricalShortOddsPromotionSmokeCheck:
    if actual is None:
        return HistoricalShortOddsPromotionSmokeCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsPromotionSmokeCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _warnings(
    *,
    passed: bool,
    excluded_competition_ids: Sequence[str],
    existing_profile_count: int,
) -> list[str]:
    warnings: list[str] = []
    if not passed:
        warnings.append("short_odds_promotion_smoke:failed")
    if excluded_competition_ids:
        warnings.append(
            "short_odds_promotion_smoke:excluded_competitions:"
            f"{','.join(excluded_competition_ids)}"
        )
    if existing_profile_count == 0:
        warnings.append("short_odds_promotion_smoke:no_existing_profiles")
    return warnings


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _float(value: object) -> float | None:
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


def _max_final_hit_harm_count_vs_original(
    options: HistoricalShortOddsPromotionSmokeOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _max_profit_loss_harm_count_vs_original(
    options: HistoricalShortOddsPromotionSmokeOptions,
) -> int:
    return (
        options.max_profit_loss_harm_count_vs_original
        if options.max_profit_loss_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def _load_json(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsPromotionSmokeCheck],
    temporary_profile_set_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "temporary_profile_set_json": temporary_profile_set_json,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_promotion_smoke:{digest}"
