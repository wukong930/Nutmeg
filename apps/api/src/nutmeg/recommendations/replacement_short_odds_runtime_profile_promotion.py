from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
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
from nutmeg.recommendations.replacement_short_odds_promotion_smoke import (
    HistoricalShortOddsPromotionSmokeReport,
)
from nutmeg.recommendations.replacement_short_odds_rolling_admission import (
    HistoricalShortOddsRollingAdmissionReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

type HistoricalShortOddsRuntimeProfilePromotionStatus = Literal[
    "promotion_ready",
    "dry_run",
    "blocked",
]
type HistoricalShortOddsRuntimeProfilePromotionCheckStatus = Literal["passed", "failed"]


class HistoricalShortOddsRuntimeProfilePromotionOptions(BaseModel):
    promoted_profile_version: str = (
        "v3_1_short_odds_replacement_runtime_profile_candidate"
    )
    min_allowed_competition_count: int = Field(default=4, ge=1)
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=5, ge=0)
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    min_rolling_active_competition_fold_count: int = Field(default=4, ge=0)
    min_rolling_active_season_fold_count: int = Field(default=5, ge=0)
    min_rolling_active_rolling_fold_count: int = Field(default=4, ge=0)
    max_rolling_failed_fold_count: int = Field(default=0, ge=0)
    require_production_proposal_ready: bool = True
    require_promotion_smoke_passed: bool = True
    require_runtime_shadow_replay_passed: bool = True
    require_post_promotion_runtime_shadow_replay_passed: bool = False
    require_rolling_admission_accepted: bool = True
    require_no_current_short_odds_rules: bool = True
    require_no_runtime_profile_write: bool = True
    require_no_public_response_change: bool = True
    require_no_production_change: bool = True
    dry_run: bool = False


class HistoricalShortOddsRuntimeProfilePromotionCheck(BaseModel):
    name: str
    status: HistoricalShortOddsRuntimeProfilePromotionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsRuntimeProfilePromotionReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsRuntimeProfilePromotionStatus
    promotion_ready: bool
    promoted_profile_version: str
    current_profile_version: str
    source_production_proposal_report_key: str
    source_promotion_smoke_report_key: str
    source_runtime_shadow_replay_report_key: str
    source_post_promotion_runtime_shadow_replay_report_key: str | None = None
    source_rolling_admission_report_key: str
    candidate_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    runtime_profile_written: bool = False
    checks: list[HistoricalShortOddsRuntimeProfilePromotionCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    candidate_runtime_profile_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_runtime_profile_promotion_report(
    *,
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
    production_proposal_report: HistoricalShortOddsProductionProposalReport
    | Mapping[str, object],
    promotion_smoke_report: HistoricalShortOddsPromotionSmokeReport | Mapping[str, object],
    runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | Mapping[str, object],
    rolling_admission_report: HistoricalShortOddsRollingAdmissionReport
    | Mapping[str, object],
    post_promotion_runtime_shadow_replay_report: (
        HistoricalShortOddsRuntimeShadowReplayReport | Mapping[str, object] | None
    ) = None,
    options: HistoricalShortOddsRuntimeProfilePromotionOptions | None = None,
) -> HistoricalShortOddsRuntimeProfilePromotionReport:
    resolved_options = options or HistoricalShortOddsRuntimeProfilePromotionOptions()
    raw_current_profile_set = _raw_mapping(current_profile_set)
    current_profiles = _profile_set(current_profile_set)
    proposal = _proposal_report(production_proposal_report)
    smoke = _smoke_report(promotion_smoke_report)
    runtime = _runtime_report(runtime_shadow_replay_report)
    post_runtime = (
        _runtime_report(post_promotion_runtime_shadow_replay_report)
        if post_promotion_runtime_shadow_replay_report is not None
        else None
    )
    rolling = _rolling_report(rolling_admission_report)
    candidate_rules = _candidate_rules(smoke)
    allowed_competition_ids = _unique(
        competition_id
        for rule in candidate_rules
        for competition_id in _string_list(rule.get("allowed_competition_ids"))
    )
    excluded_competition_ids = _unique(
        competition_id
        for rule in candidate_rules
        for competition_id in _string_list(rule.get("excluded_competition_ids"))
    )
    checks = _checks(
        raw_current_profile_set=raw_current_profile_set,
        proposal=proposal,
        smoke=smoke,
        runtime=runtime,
        post_runtime=post_runtime,
        rolling=rolling,
        candidate_rules=candidate_rules,
        allowed_competition_ids=allowed_competition_ids,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    promotion_ready = not blockers
    status: HistoricalShortOddsRuntimeProfilePromotionStatus
    if blockers:
        status = "blocked"
    elif resolved_options.dry_run:
        status = "dry_run"
    else:
        status = "promotion_ready"
    candidate_profile = _candidate_runtime_profile_json(
        current_profiles,
        candidate_rules=candidate_rules if promotion_ready else [],
        proposal=proposal,
        smoke=smoke,
        runtime=runtime,
        post_runtime=post_runtime,
        rolling=rolling,
        options=resolved_options,
        status=status,
        promotion_ready=promotion_ready,
    )
    warnings = _warnings(
        status=status,
        blockers=blockers,
        excluded_competition_ids=excluded_competition_ids,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_runtime_profile_promotion_v3_1",
        "status": status,
        "promotion_ready": promotion_ready,
        "promoted_profile_version": resolved_options.promoted_profile_version,
        "current_profile_version": current_profiles.profile_version,
        "source_production_proposal_report_key": proposal.report_key,
        "source_promotion_smoke_report_key": smoke.report_key,
        "source_runtime_shadow_replay_report_key": runtime.report_key,
        "source_post_promotion_runtime_shadow_replay_report_key": (
            post_runtime.report_key if post_runtime is not None else None
        ),
        "source_rolling_admission_report_key": rolling.report_key,
        "runtime_final_hit_harm_count_vs_original": (
            runtime.final_hit_harm_count_vs_original
        ),
        "runtime_profit_loss_harm_count_vs_original": (
            runtime.profit_loss_harm_count_vs_original
        ),
        "rolling_overall_final_hit_harm_count_vs_original": _optional_float(
            _mapping(rolling.summary_json).get(
                "overall_final_hit_harm_count_vs_original"
            )
        ),
        "rolling_overall_profit_loss_harm_count_vs_original": _optional_float(
            _mapping(rolling.summary_json).get(
                "overall_profit_loss_harm_count_vs_original"
            )
        ),
        "post_promotion_runtime_final_hit_harm_count_vs_original": (
            post_runtime.final_hit_harm_count_vs_original
            if post_runtime is not None
            else None
        ),
        "post_promotion_runtime_profit_loss_harm_count_vs_original": (
            post_runtime.profit_loss_harm_count_vs_original
            if post_runtime is not None
            else None
        ),
        "candidate_rule_count": len(candidate_rules) if promotion_ready else 0,
        "allowed_competition_ids": allowed_competition_ids if promotion_ready else [],
        "excluded_competition_ids": excluded_competition_ids if promotion_ready else [],
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "runtime_profile_written": False,
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, candidate_profile)
    return HistoricalShortOddsRuntimeProfilePromotionReport(
        report_key=report_key,
        status=status,
        promotion_ready=promotion_ready,
        promoted_profile_version=resolved_options.promoted_profile_version,
        current_profile_version=current_profiles.profile_version,
        source_production_proposal_report_key=proposal.report_key,
        source_promotion_smoke_report_key=smoke.report_key,
        source_runtime_shadow_replay_report_key=runtime.report_key,
        source_post_promotion_runtime_shadow_replay_report_key=(
            post_runtime.report_key if post_runtime is not None else None
        ),
        source_rolling_admission_report_key=rolling.report_key,
        candidate_rule_count=len(candidate_rules) if promotion_ready else 0,
        allowed_competition_ids=allowed_competition_ids if promotion_ready else [],
        excluded_competition_ids=excluded_competition_ids if promotion_ready else [],
        production_recommendation_changed=False,
        public_response_changed=False,
        runtime_profile_written=False,
        checks=checks,
        blockers=blockers,
        candidate_runtime_profile_json=candidate_profile,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_production_proposal_report(
    path: Path,
) -> HistoricalShortOddsProductionProposalReport:
    return HistoricalShortOddsProductionProposalReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_historical_short_odds_promotion_smoke_report(
    path: Path,
) -> HistoricalShortOddsPromotionSmokeReport:
    return HistoricalShortOddsPromotionSmokeReport.model_validate_json(
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
    report = build_historical_short_odds_runtime_profile_promotion_report(
        current_profile_set=load_competition_recommendation_profile_set(
            args.current_profile_path
        ),
        production_proposal_report=load_historical_short_odds_production_proposal_report(
            args.production_proposal_report
        ),
        promotion_smoke_report=load_historical_short_odds_promotion_smoke_report(
            args.promotion_smoke_report
        ),
        runtime_shadow_replay_report=(
            load_historical_short_odds_runtime_shadow_replay_report(
                args.runtime_shadow_replay_report
            )
        ),
        post_promotion_runtime_shadow_replay_report=(
            load_historical_short_odds_runtime_shadow_replay_report(
                args.post_promotion_runtime_shadow_replay_report
            )
            if args.post_promotion_runtime_shadow_replay_report is not None
            else None
        ),
        rolling_admission_report=load_historical_short_odds_rolling_admission_report(
            args.rolling_admission_report
        ),
        options=_options_from_args(args),
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if report.promotion_ready and args.profile_output_path is not None:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.candidate_runtime_profile_json, indent=2)}\n",
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    *,
    raw_current_profile_set: Mapping[str, object],
    proposal: HistoricalShortOddsProductionProposalReport,
    smoke: HistoricalShortOddsPromotionSmokeReport,
    runtime: HistoricalShortOddsRuntimeShadowReplayReport,
    post_runtime: HistoricalShortOddsRuntimeShadowReplayReport | None,
    rolling: HistoricalShortOddsRollingAdmissionReport,
    candidate_rules: Sequence[Mapping[str, object]],
    allowed_competition_ids: Sequence[str],
    options: HistoricalShortOddsRuntimeProfilePromotionOptions,
) -> list[HistoricalShortOddsRuntimeProfilePromotionCheck]:
    rolling_summary = _mapping(rolling.summary_json)
    final_hit_harm_threshold = _max_final_hit_harm_count_vs_original(options)
    profit_loss_harm_threshold = _max_profit_loss_harm_count_vs_original(options)
    return [
        _equality_check(
            name="production_proposal_status",
            actual=proposal.status,
            expected="production_proposal_ready",
            enabled=options.require_production_proposal_ready,
            detail="production proposal must be ready",
        ),
        _boolean_check(
            name="production_proposal_allowed",
            actual=proposal.production_recommendation_allowed,
            expected=True,
            enabled=options.require_production_proposal_ready,
            detail="production proposal must allow recommendations",
        ),
        _boolean_check(
            name="promotion_smoke_passed",
            actual=smoke.passed,
            expected=True,
            enabled=options.require_promotion_smoke_passed,
            detail="promotion smoke must pass",
        ),
        _equality_check(
            name="promotion_smoke_source_proposal_key",
            actual=smoke.source_proposal_report_key,
            expected=proposal.report_key,
            enabled=True,
            detail="promotion smoke must reference the supplied proposal",
        ),
        _boolean_check(
            name="runtime_shadow_replay_passed",
            actual=runtime.passed,
            expected=True,
            enabled=options.require_runtime_shadow_replay_passed,
            detail="runtime shadow replay must pass",
        ),
        _equality_check(
            name="runtime_shadow_replay_status",
            actual=runtime.status,
            expected="shadow_replay_passed",
            enabled=options.require_runtime_shadow_replay_passed,
            detail="runtime shadow replay status must be passed",
        ),
        _equality_check(
            name="runtime_source_audit_report_key",
            actual=runtime.source_audit_report_key,
            expected=rolling.source_audit_report_key,
            enabled=True,
            detail="linked runtime replay must use the same audit as rolling admission",
        ),
        _equality_check(
            name="proposal_runtime_shadow_key",
            actual=proposal.source_runtime_shadow_replay_report_key,
            expected=runtime.report_key,
            enabled=True,
            detail="proposal must reference the supplied runtime replay",
        ),
        _equality_check(
            name="proposal_rolling_admission_key",
            actual=proposal.source_rolling_admission_report_key,
            expected=rolling.report_key,
            enabled=True,
            detail="proposal must reference the supplied rolling admission",
        ),
        _equality_check(
            name="rolling_overall_runtime_shadow_key",
            actual=rolling.overall_runtime_shadow_report_key,
            expected=runtime.report_key,
            enabled=True,
            detail="rolling admission must share the runtime replay key",
        ),
        _boolean_check(
            name="rolling_admission_accepted",
            actual=rolling.status == "accepted",
            expected=True,
            enabled=options.require_rolling_admission_accepted,
            detail="rolling admission must be accepted",
        ),
        _boolean_check(
            name="rolling_admission_production_allowed",
            actual=rolling.production_recommendation_allowed,
            expected=True,
            enabled=options.require_rolling_admission_accepted,
            detail="rolling admission must allow production recommendations",
        ),
        _maximum_check(
            name="rolling_failed_fold_count",
            actual=rolling.failed_fold_count,
            threshold=options.max_rolling_failed_fold_count,
            detail="rolling admission must not have failing active folds",
        ),
        _minimum_check(
            name="rolling_active_competition_fold_count",
            actual=rolling.active_competition_fold_count,
            threshold=options.min_rolling_active_competition_fold_count,
            detail="rolling admission must cover enough competition folds",
        ),
        _minimum_check(
            name="rolling_active_season_fold_count",
            actual=rolling.active_season_fold_count,
            threshold=options.min_rolling_active_season_fold_count,
            detail="rolling admission must cover enough season folds",
        ),
        _minimum_check(
            name="rolling_active_rolling_fold_count",
            actual=rolling.active_rolling_fold_count,
            threshold=options.min_rolling_active_rolling_fold_count,
            detail="rolling admission must cover enough rolling-window folds",
        ),
        _minimum_check(
            name="runtime_final_answer_count",
            actual=runtime.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="runtime replay must cover enough final answers",
        ),
        _minimum_check(
            name="runtime_changed_final_answer_count",
            actual=runtime.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="runtime replay must affect enough final answers",
        ),
        _minimum_check(
            name="runtime_final_answer_hit_rate_delta",
            actual=runtime.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="runtime replay final-answer hit rate must not regress",
        ),
        _minimum_check(
            name="runtime_roi_delta",
            actual=runtime.roi_delta,
            threshold=options.min_roi_delta,
            detail="runtime replay ROI must not regress",
        ),
        _minimum_check(
            name="runtime_profit_loss_delta",
            actual=runtime.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="runtime replay profit/loss must not regress",
        ),
        _maximum_check(
            name="runtime_harm_count_vs_original",
            actual=runtime.harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail="runtime replay must pass compatibility no-harm",
        ),
        _maximum_check(
            name="runtime_final_hit_harm_count_vs_original",
            actual=runtime.final_hit_harm_count_vs_original,
            threshold=final_hit_harm_threshold,
            detail="runtime replay must not turn original hits into misses",
        ),
        _maximum_check(
            name="runtime_profit_loss_harm_count_vs_original",
            actual=runtime.profit_loss_harm_count_vs_original,
            threshold=profit_loss_harm_threshold,
            detail="runtime replay must not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="runtime_average_hit_probability_delta_vs_original",
            actual=runtime.average_hit_probability_delta_vs_original,
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="runtime replay hit-probability loss must stay inside tolerance",
        ),
        _minimum_check(
            name="rolling_overall_final_answer_hit_rate_delta",
            actual=_optional_float(
                rolling_summary.get("overall_final_answer_hit_rate_delta")
            ),
            threshold=options.min_final_answer_hit_rate_delta,
            detail="rolling overall hit rate must not regress",
        ),
        _minimum_check(
            name="rolling_overall_roi_delta",
            actual=_optional_float(rolling_summary.get("overall_roi_delta")),
            threshold=options.min_roi_delta,
            detail="rolling overall ROI must not regress",
        ),
        _minimum_check(
            name="rolling_overall_profit_loss_delta",
            actual=_optional_float(rolling_summary.get("overall_profit_loss_delta")),
            threshold=options.min_profit_loss_delta,
            detail="rolling overall profit/loss must not regress",
        ),
        _maximum_check(
            name="rolling_overall_harm_count_vs_original",
            actual=_optional_float(rolling_summary.get("overall_harm_count_vs_original")),
            threshold=options.max_harm_count_vs_original,
            detail="rolling overall replay must pass compatibility no-harm",
        ),
        _maximum_check(
            name="rolling_overall_final_hit_harm_count_vs_original",
            actual=_optional_float(
                rolling_summary.get("overall_final_hit_harm_count_vs_original")
            ),
            threshold=final_hit_harm_threshold,
            detail="rolling overall replay must not turn original hits into misses",
        ),
        _maximum_check(
            name="rolling_overall_profit_loss_harm_count_vs_original",
            actual=_optional_float(
                rolling_summary.get("overall_profit_loss_harm_count_vs_original")
            ),
            threshold=profit_loss_harm_threshold,
            detail=(
                "rolling overall replay must not reduce original final-answer "
                "profit/loss"
            ),
        ),
        _boolean_check(
            name="post_promotion_runtime_shadow_replay_present",
            actual=post_runtime is not None,
            expected=True,
            enabled=options.require_post_promotion_runtime_shadow_replay_passed,
            detail="post-promotion runtime replay evidence is required when requested",
        ),
        _boolean_check(
            name="post_promotion_runtime_shadow_replay_passed",
            actual=post_runtime.passed if post_runtime is not None else False,
            expected=True,
            enabled=options.require_post_promotion_runtime_shadow_replay_passed,
            detail="post-promotion runtime replay must pass",
        ),
        _equality_check(
            name="post_promotion_runtime_source_profile_version",
            actual=(
                post_runtime.source_rule_profile_version
                if post_runtime is not None
                else None
            ),
            expected=smoke.promoted_profile_version,
            enabled=post_runtime is not None,
            detail="post-promotion runtime replay must use the smoke temporary profile",
        ),
        _minimum_check(
            name="post_promotion_runtime_final_answer_hit_rate_delta",
            actual=(
                post_runtime.final_answer_hit_rate_delta
                if post_runtime is not None
                else options.min_final_answer_hit_rate_delta
            ),
            threshold=options.min_final_answer_hit_rate_delta,
            detail="post-promotion runtime hit rate must not regress",
        ),
        _minimum_check(
            name="post_promotion_runtime_roi_delta",
            actual=(
                post_runtime.roi_delta
                if post_runtime is not None
                else options.min_roi_delta
            ),
            threshold=options.min_roi_delta,
            detail="post-promotion runtime ROI must not regress",
        ),
        _minimum_check(
            name="post_promotion_runtime_profit_loss_delta",
            actual=(
                post_runtime.profit_loss_delta if post_runtime is not None else None
            )
            if post_runtime is not None
            else options.min_profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="post-promotion runtime profit/loss must not regress",
        ),
        _maximum_check(
            name="post_promotion_runtime_harm_count_vs_original",
            actual=(
                post_runtime.harm_count_vs_original if post_runtime is not None else None
            )
            if post_runtime is not None
            else options.max_harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail="post-promotion runtime replay must pass compatibility no-harm",
        ),
        _maximum_check(
            name="post_promotion_runtime_final_hit_harm_count_vs_original",
            actual=(
                post_runtime.final_hit_harm_count_vs_original
                if post_runtime is not None
                else final_hit_harm_threshold
            ),
            threshold=final_hit_harm_threshold,
            detail=(
                "post-promotion runtime replay must not turn original hits into "
                "misses"
            ),
        ),
        _maximum_check(
            name="post_promotion_runtime_profit_loss_harm_count_vs_original",
            actual=(
                post_runtime.profit_loss_harm_count_vs_original
                if post_runtime is not None
                else profit_loss_harm_threshold
            ),
            threshold=profit_loss_harm_threshold,
            detail=(
                "post-promotion runtime replay must not reduce original "
                "final-answer profit/loss"
            ),
        ),
        _boolean_check(
            name="post_promotion_runtime_public_response_unchanged",
            actual=(
                not post_runtime.public_response_changed
                if post_runtime is not None
                else False
            ),
            expected=True,
            enabled=post_runtime is not None
            and options.require_no_public_response_change,
            detail="post-promotion runtime replay must not change public responses",
        ),
        _boolean_check(
            name="post_promotion_runtime_production_unchanged",
            actual=(
                not post_runtime.production_recommendation_changed
                if post_runtime is not None
                else False
            ),
            expected=True,
            enabled=post_runtime is not None and options.require_no_production_change,
            detail="post-promotion runtime replay must not change production",
        ),
        _boolean_check(
            name="promotion_smoke_runtime_profile_not_written",
            actual=not smoke.runtime_profile_written,
            expected=True,
            enabled=options.require_no_runtime_profile_write,
            detail="promotion smoke must not have written the runtime profile",
        ),
        _boolean_check(
            name="promotion_smoke_public_response_unchanged",
            actual=not smoke.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="promotion smoke must not change public responses",
        ),
        _boolean_check(
            name="runtime_public_response_unchanged",
            actual=not runtime.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="runtime replay must not change public responses",
        ),
        _boolean_check(
            name="proposal_production_unchanged",
            actual=not _proposal_production_recommendation_changed(proposal),
            expected=True,
            enabled=options.require_no_production_change,
            detail="proposal must not already have changed production",
        ),
        _boolean_check(
            name="smoke_production_unchanged",
            actual=not smoke.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="promotion smoke must not change production",
        ),
        _boolean_check(
            name="runtime_production_unchanged",
            actual=not runtime.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="runtime replay must not change production",
        ),
        _boolean_check(
            name="current_profile_has_no_short_odds_rules",
            actual="short_odds_replacement_rules" not in raw_current_profile_set,
            expected=True,
            enabled=options.require_no_current_short_odds_rules,
            detail="default current profile must not already contain short-odds rules",
        ),
        _minimum_check(
            name="candidate_rule_count",
            actual=len(candidate_rules),
            threshold=1,
            detail="candidate runtime profile must contain at least one rule",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="candidate rule must cover enough allowed competitions",
        ),
    ]


def _candidate_runtime_profile_json(
    current_profiles: CompetitionRecommendationProfileSet,
    *,
    candidate_rules: Sequence[Mapping[str, object]],
    proposal: HistoricalShortOddsProductionProposalReport,
    smoke: HistoricalShortOddsPromotionSmokeReport,
    runtime: HistoricalShortOddsRuntimeShadowReplayReport,
    post_runtime: HistoricalShortOddsRuntimeShadowReplayReport | None,
    rolling: HistoricalShortOddsRollingAdmissionReport,
    options: HistoricalShortOddsRuntimeProfilePromotionOptions,
    status: HistoricalShortOddsRuntimeProfilePromotionStatus,
    promotion_ready: bool,
) -> dict[str, object]:
    return {
        "profile_version": options.promoted_profile_version,
        "calculation_basis": "historical_short_odds_runtime_profile_promotion_v3_1",
        "status": status,
        "promotion_ready": promotion_ready,
        "base_profile_version": current_profiles.profile_version,
        "profiles": [
            profile.model_dump(mode="json") for profile in current_profiles.profiles
        ],
        "short_odds_replacement_rules": [dict(rule) for rule in candidate_rules],
        "source_report_keys": {
            "production_proposal": proposal.report_key,
            "promotion_smoke": smoke.report_key,
            "runtime_shadow_replay": runtime.report_key,
            "post_promotion_runtime_shadow_replay": (
                post_runtime.report_key if post_runtime is not None else None
            ),
            "rolling_admission": rolling.report_key,
            "suite_gate": proposal.source_suite_gate_report_key,
            "final_answer_gate": proposal.source_final_answer_gate_report_key,
            "audit": proposal.source_audit_report_key,
            "competition_gate": proposal.source_competition_gate_report_key,
            "generated_shadow": proposal.generated_shadow_report_key,
        },
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "runtime_profile_written": False,
        "notes": _unique(
            [
                *current_profiles.notes,
                "Candidate runtime profile artifact only; default profile unchanged.",
                "Short-odds replacement rules remain internal and not user-facing text.",
                (
                    "No automated betting, wallet, payment, or guaranteed-outcome "
                    "behavior is introduced."
                ),
                f"production_proposal_report_key={proposal.report_key}",
                f"promotion_smoke_report_key={smoke.report_key}",
                f"runtime_shadow_replay_report_key={runtime.report_key}",
                *(
                    [
                        "post_promotion_runtime_shadow_replay_report_key="
                        f"{post_runtime.report_key}"
                    ]
                    if post_runtime is not None
                    else []
                ),
                f"rolling_admission_report_key={rolling.report_key}",
            ]
        ),
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build a final-gated short-odds runtime profile candidate."
    )
    parser.add_argument(
        "--current-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--production-proposal-report", type=Path, required=True)
    parser.add_argument("--promotion-smoke-report", type=Path, required=True)
    parser.add_argument("--runtime-shadow-replay-report", type=Path, required=True)
    parser.add_argument("--post-promotion-runtime-shadow-replay-report", type=Path)
    parser.add_argument("--rolling-admission-report", type=Path, required=True)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--promoted-profile-version",
        default="v3_1_short_odds_replacement_runtime_profile_candidate",
    )
    parser.add_argument("--min-allowed-competition-count", type=int, default=4)
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=5)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
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
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--min-rolling-active-competition-fold-count", type=int, default=4)
    parser.add_argument("--min-rolling-active-season-fold-count", type=int, default=5)
    parser.add_argument("--min-rolling-active-rolling-fold-count", type=int, default=4)
    parser.add_argument("--max-rolling-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-non-ready-proposal", action="store_true")
    parser.add_argument("--allow-failed-promotion-smoke", action="store_true")
    parser.add_argument("--allow-failed-runtime-shadow-replay", action="store_true")
    parser.add_argument(
        "--allow-failed-post-promotion-runtime-shadow-replay",
        action="store_true",
    )
    parser.add_argument("--allow-unaccepted-rolling-admission", action="store_true")
    parser.add_argument("--allow-existing-short-odds-rules", action="store_true")
    parser.add_argument("--allow-runtime-profile-write", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalShortOddsRuntimeProfilePromotionOptions:
    return HistoricalShortOddsRuntimeProfilePromotionOptions(
        promoted_profile_version=args.promoted_profile_version,
        min_allowed_competition_count=args.min_allowed_competition_count,
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
        require_promotion_smoke_passed=not args.allow_failed_promotion_smoke,
        require_runtime_shadow_replay_passed=not args.allow_failed_runtime_shadow_replay,
        require_post_promotion_runtime_shadow_replay_passed=(
            args.post_promotion_runtime_shadow_replay_report is not None
            and not args.allow_failed_post_promotion_runtime_shadow_replay
        ),
        require_rolling_admission_accepted=not args.allow_unaccepted_rolling_admission,
        require_no_current_short_odds_rules=not args.allow_existing_short_odds_rules,
        require_no_runtime_profile_write=not args.allow_runtime_profile_write,
        require_no_public_response_change=not args.allow_public_response_change,
        require_no_production_change=not args.allow_production_change,
        dry_run=args.dry_run,
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


def _smoke_report(
    value: HistoricalShortOddsPromotionSmokeReport | Mapping[str, object],
) -> HistoricalShortOddsPromotionSmokeReport:
    if isinstance(value, HistoricalShortOddsPromotionSmokeReport):
        return value
    return HistoricalShortOddsPromotionSmokeReport.model_validate(value)


def _runtime_report(
    value: HistoricalShortOddsRuntimeShadowReplayReport | Mapping[str, object],
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    if isinstance(value, HistoricalShortOddsRuntimeShadowReplayReport):
        return value
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(value)


def _rolling_report(
    value: HistoricalShortOddsRollingAdmissionReport | Mapping[str, object],
) -> HistoricalShortOddsRollingAdmissionReport:
    if isinstance(value, HistoricalShortOddsRollingAdmissionReport):
        return value
    return HistoricalShortOddsRollingAdmissionReport.model_validate(value)


def _raw_mapping(
    value: CompetitionRecommendationProfileSet | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(value, CompetitionRecommendationProfileSet):
        return value.model_dump(mode="json")
    return dict(value)


def _candidate_rules(
    smoke: HistoricalShortOddsPromotionSmokeReport,
) -> list[dict[str, object]]:
    return _mapping_list(
        smoke.temporary_profile_set_json.get("short_odds_replacement_rules")
    )


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


def _warnings(
    *,
    status: HistoricalShortOddsRuntimeProfilePromotionStatus,
    blockers: Sequence[str],
    excluded_competition_ids: Sequence[str],
) -> list[str]:
    warnings: list[str] = []
    if status == "blocked":
        warnings.append("short_odds_runtime_profile_promotion:blocked")
    if blockers:
        warnings.extend(
            f"short_odds_runtime_profile_promotion:blocker:{blocker}"
            for blocker in blockers
        )
    if excluded_competition_ids:
        warnings.append(
            "short_odds_runtime_profile_promotion:excluded_competitions:"
            f"{','.join(excluded_competition_ids)}"
        )
    return warnings


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsRuntimeProfilePromotionCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfilePromotionCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfilePromotionCheck(
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
    expected: str | None,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsRuntimeProfilePromotionCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfilePromotionCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfilePromotionCheck(
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
) -> HistoricalShortOddsRuntimeProfilePromotionCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfilePromotionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfilePromotionCheck(
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
) -> HistoricalShortOddsRuntimeProfilePromotionCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfilePromotionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfilePromotionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


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


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _max_final_hit_harm_count_vs_original(
    options: HistoricalShortOddsRuntimeProfilePromotionOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _max_profit_loss_harm_count_vs_original(
    options: HistoricalShortOddsRuntimeProfilePromotionOptions,
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


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsRuntimeProfilePromotionCheck],
    candidate_runtime_profile_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "candidate_runtime_profile_json": candidate_runtime_profile_json,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_runtime_profile_promotion:{digest}"
