from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.replacement_probability_preserving_runtime_dry_run import (
    HistoricalReplacementProbabilityPreservingRuntimeDryRunReport,
    load_historical_replacement_probability_preserving_runtime_dry_run_report,
)

type HistoricalReplacementProbabilityPreservingPromotionReviewStatus = Literal[
    "promotion_review_ready",
    "promotion_review_watchlist",
    "blocked",
]
type HistoricalReplacementProbabilityPreservingPromotionReviewCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalReplacementProbabilityPreservingPromotionReviewOptions(BaseModel):
    review_id: str = "probability_preserving_replacement_runtime_review_v1"
    reviewed_profile_version: str = (
        "v3_1_probability_preserving_replacement_runtime_review"
    )
    min_rule_count: int = Field(default=1, ge=1)
    min_allowed_competition_count: int = Field(default=5, ge=0)
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=13, ge=0)
    min_final_answer_hit_delta_count: int = 0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    min_average_hit_probability_delta_vs_original: float = -0.02
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    min_active_surface_count: int = Field(default=8, ge=0)
    max_failed_surface_count: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=5, ge=0)
    min_active_season_fold_count: int = Field(default=5, ge=0)
    min_active_rolling_fold_count: int = Field(default=13, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    require_runtime_dry_run_passed: bool = True
    require_shadow_runtime_allowed: bool = True
    require_dry_run_only_profile: bool = True
    require_exclude_original_hit_harm: bool = True
    require_no_production_allowed: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalReplacementProbabilityPreservingPromotionReviewCheck(BaseModel):
    name: str
    status: HistoricalReplacementProbabilityPreservingPromotionReviewCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalReplacementProbabilityPreservingPromotionReviewReport(BaseModel):
    report_key: str
    status: HistoricalReplacementProbabilityPreservingPromotionReviewStatus
    promotion_review_allowed: bool
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    source_runtime_dry_run_report_key: str
    source_grid_report_key: str | None = None
    source_surface_replay_report_key: str | None = None
    source_admission_report_key: str | None = None
    generated_runtime_shadow_replay_report_key: str | None = None
    selected_candidate_key: str | None = None
    reviewed_profile_version: str
    candidate_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    profit_loss_delta: float
    roi_delta: float | None = None
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(ge=0)
    profit_loss_harm_count_vs_original: int = Field(ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    active_surface_count: int = Field(ge=0)
    failed_surface_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    checks: list[HistoricalReplacementProbabilityPreservingPromotionReviewCheck] = (
        Field(default_factory=list)
    )
    blockers: list[str] = Field(default_factory=list)
    review_profile_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_replacement_probability_preserving_promotion_review_report(
    runtime_dry_run_report: HistoricalReplacementProbabilityPreservingRuntimeDryRunReport,
    *,
    options: HistoricalReplacementProbabilityPreservingPromotionReviewOptions | None = None,
) -> HistoricalReplacementProbabilityPreservingPromotionReviewReport:
    resolved_options = (
        options or HistoricalReplacementProbabilityPreservingPromotionReviewOptions()
    )
    profile = dict(runtime_dry_run_report.runtime_proposal_profile_set_json)
    rules = _rules(profile)
    allowed_competition_ids = _unique(
        competition_id
        for rule in rules
        for competition_id in _string_list(rule.get("allowed_competition_ids"))
    )
    first_rule = rules[0] if rules else {}
    constraints = _mapping(first_rule.get("constraints_json"))
    checks = _checks(
        runtime_dry_run_report,
        rules=rules,
        allowed_competition_ids=allowed_competition_ids,
        constraints=constraints,
        profile=profile,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    dry_run_failed = (
        runtime_dry_run_report.status != "runtime_dry_run_passed"
        and resolved_options.require_runtime_dry_run_passed
    )
    if dry_run_failed:
        status: HistoricalReplacementProbabilityPreservingPromotionReviewStatus = (
            "blocked"
        )
    elif blockers:
        status = "promotion_review_watchlist"
    else:
        status = "promotion_review_ready"
    promotion_review_allowed = status == "promotion_review_ready"
    review_profile = _review_profile_json(
        profile,
        rules=rules if promotion_review_allowed else [],
        status=status,
        options=resolved_options,
        promotion_review_allowed=promotion_review_allowed,
    )
    warnings = [
        *runtime_dry_run_report.warnings,
        *[f"probability_preserving_promotion_review:failed_check:{name}" for name in blockers],
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_replacement_probability_preserving_promotion_review_v3_1"
        ),
        "status": status,
        "promotion_review_allowed": promotion_review_allowed,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "review_id": resolved_options.review_id,
        "reviewed_profile_version": resolved_options.reviewed_profile_version,
        "source_runtime_dry_run_report_key": runtime_dry_run_report.report_key,
        "source_grid_report_key": runtime_dry_run_report.source_grid_report_key,
        "source_surface_replay_report_key": (
            runtime_dry_run_report.source_surface_replay_report_key
        ),
        "source_admission_report_key": (
            runtime_dry_run_report.source_admission_report_key
        ),
        "generated_runtime_shadow_replay_report_key": (
            runtime_dry_run_report.generated_runtime_shadow_replay_report_key
        ),
        "selected_candidate_key": runtime_dry_run_report.selected_candidate_key,
        "candidate_rule_count": len(rules) if promotion_review_allowed else 0,
        "allowed_competition_ids": (
            allowed_competition_ids if promotion_review_allowed else []
        ),
        "final_answer_count": runtime_dry_run_report.final_answer_count,
        "changed_final_answer_count": runtime_dry_run_report.changed_final_answer_count,
        "final_answer_hit_delta_count": (
            runtime_dry_run_report.final_answer_hit_delta_count
        ),
        "profit_loss_delta": runtime_dry_run_report.profit_loss_delta,
        "roi_delta": runtime_dry_run_report.roi_delta,
        "harm_count_vs_original": runtime_dry_run_report.harm_count_vs_original,
        "final_hit_harm_count_vs_original": (
            runtime_dry_run_report.final_hit_harm_count_vs_original
        ),
        "profit_loss_harm_count_vs_original": (
            runtime_dry_run_report.profit_loss_harm_count_vs_original
        ),
        "average_hit_probability_delta_vs_original": (
            runtime_dry_run_report.average_hit_probability_delta_vs_original
        ),
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, review_profile)
    return HistoricalReplacementProbabilityPreservingPromotionReviewReport(
        report_key=report_key,
        status=status,
        promotion_review_allowed=promotion_review_allowed,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        source_runtime_dry_run_report_key=runtime_dry_run_report.report_key,
        source_grid_report_key=runtime_dry_run_report.source_grid_report_key,
        source_surface_replay_report_key=(
            runtime_dry_run_report.source_surface_replay_report_key
        ),
        source_admission_report_key=runtime_dry_run_report.source_admission_report_key,
        generated_runtime_shadow_replay_report_key=(
            runtime_dry_run_report.generated_runtime_shadow_replay_report_key
        ),
        selected_candidate_key=runtime_dry_run_report.selected_candidate_key,
        reviewed_profile_version=resolved_options.reviewed_profile_version,
        candidate_rule_count=len(rules) if promotion_review_allowed else 0,
        allowed_competition_ids=(
            allowed_competition_ids if promotion_review_allowed else []
        ),
        final_answer_count=runtime_dry_run_report.final_answer_count,
        changed_final_answer_count=runtime_dry_run_report.changed_final_answer_count,
        final_answer_hit_delta_count=(
            runtime_dry_run_report.final_answer_hit_delta_count
        ),
        profit_loss_delta=runtime_dry_run_report.profit_loss_delta,
        roi_delta=runtime_dry_run_report.roi_delta,
        harm_count_vs_original=runtime_dry_run_report.harm_count_vs_original,
        final_hit_harm_count_vs_original=(
            runtime_dry_run_report.final_hit_harm_count_vs_original
        ),
        profit_loss_harm_count_vs_original=(
            runtime_dry_run_report.profit_loss_harm_count_vs_original
        ),
        average_hit_probability_delta_vs_original=(
            runtime_dry_run_report.average_hit_probability_delta_vs_original
        ),
        active_surface_count=runtime_dry_run_report.active_surface_count,
        failed_surface_count=runtime_dry_run_report.failed_surface_count,
        active_competition_fold_count=(
            runtime_dry_run_report.active_competition_fold_count
        ),
        active_season_fold_count=runtime_dry_run_report.active_season_fold_count,
        active_rolling_fold_count=runtime_dry_run_report.active_rolling_fold_count,
        failed_fold_count=runtime_dry_run_report.failed_fold_count,
        checks=checks,
        blockers=blockers,
        review_profile_json=review_profile,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_replacement_probability_preserving_promotion_review_report(
    path: Path | str,
) -> HistoricalReplacementProbabilityPreservingPromotionReviewReport:
    return (
        HistoricalReplacementProbabilityPreservingPromotionReviewReport
        .model_validate_json(Path(path).read_text(encoding="utf-8"))
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_replacement_probability_preserving_promotion_review_report(
        load_historical_replacement_probability_preserving_runtime_dry_run_report(
            args.runtime_dry_run_report
        ),
        options=_options_from_args(args),
    )
    if args.profile_output_path is not None and report.promotion_review_allowed:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.review_profile_json, indent=2)}\n",
            encoding="utf-8",
        )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    runtime_dry_run_report: HistoricalReplacementProbabilityPreservingRuntimeDryRunReport,
    *,
    rules: Sequence[Mapping[str, object]],
    allowed_competition_ids: Sequence[str],
    constraints: Mapping[str, object],
    profile: Mapping[str, object],
    options: HistoricalReplacementProbabilityPreservingPromotionReviewOptions,
) -> list[HistoricalReplacementProbabilityPreservingPromotionReviewCheck]:
    return [
        _equality_check(
            name="runtime_dry_run_status",
            actual=runtime_dry_run_report.status,
            expected="runtime_dry_run_passed",
            enabled=options.require_runtime_dry_run_passed,
            detail="runtime dry run must pass before review is allowed",
        ),
        _boolean_check(
            name="shadow_runtime_candidate_allowed",
            actual=runtime_dry_run_report.shadow_runtime_candidate_allowed,
            expected=True,
            enabled=options.require_shadow_runtime_allowed,
            detail="dry run must mark the candidate as shadow-runtime allowed",
        ),
        _boolean_check(
            name="dry_run_only_profile",
            actual=bool(profile.get("dry_run_only")),
            expected=True,
            enabled=options.require_dry_run_only_profile,
            detail="review profile must remain dry-run only",
        ),
        _boolean_check(
            name="production_recommendation_allowed_false",
            actual=runtime_dry_run_report.production_recommendation_allowed,
            expected=False,
            enabled=options.require_no_production_allowed,
            detail="promotion review must not allow production recommendations",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not runtime_dry_run_report.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="dry run must not change production recommendations",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=not runtime_dry_run_report.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="dry run must not change public responses",
        ),
        _minimum_check(
            name="candidate_rule_count",
            actual=len(rules),
            threshold=options.min_rule_count,
            detail="review profile must include enough candidate rules",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="review profile must cover enough allowed competitions",
        ),
        _minimum_check(
            name="final_answer_count",
            actual=runtime_dry_run_report.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="review evidence should cover enough final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=runtime_dry_run_report.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="review evidence should affect enough final answers",
        ),
        _minimum_check(
            name="final_answer_hit_delta_count",
            actual=runtime_dry_run_report.final_answer_hit_delta_count,
            threshold=options.min_final_answer_hit_delta_count,
            detail="final-answer hit count should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=runtime_dry_run_report.roi_delta,
            threshold=options.min_roi_delta,
            detail="ROI should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=runtime_dry_run_report.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="profit/loss should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_original",
            actual=runtime_dry_run_report.harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail="candidate should not harm original final answers",
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_original",
            actual=runtime_dry_run_report.final_hit_harm_count_vs_original,
            threshold=options.max_final_hit_harm_count_vs_original,
            detail="candidate should not turn original hits into misses",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_original",
            actual=runtime_dry_run_report.profit_loss_harm_count_vs_original,
            threshold=options.max_profit_loss_harm_count_vs_original,
            detail="candidate should not reduce original final-answer P/L",
        ),
        _minimum_check(
            name="average_hit_probability_delta_vs_original",
            actual=runtime_dry_run_report.average_hit_probability_delta_vs_original,
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="probability loss should remain bounded",
        ),
        _minimum_check(
            name="active_surface_count",
            actual=runtime_dry_run_report.active_surface_count,
            threshold=options.min_active_surface_count,
            detail="review should cover enough active surfaces",
        ),
        _maximum_check(
            name="failed_surface_count",
            actual=runtime_dry_run_report.failed_surface_count,
            threshold=options.max_failed_surface_count,
            detail="review should not carry failed surfaces",
        ),
        _minimum_check(
            name="active_competition_fold_count",
            actual=runtime_dry_run_report.active_competition_fold_count,
            threshold=options.min_active_competition_fold_count,
            detail="review should cover enough competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=runtime_dry_run_report.active_season_fold_count,
            threshold=options.min_active_season_fold_count,
            detail="review should cover enough season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=runtime_dry_run_report.active_rolling_fold_count,
            threshold=options.min_active_rolling_fold_count,
            detail="review should cover enough rolling folds",
        ),
        _maximum_check(
            name="failed_fold_count",
            actual=runtime_dry_run_report.failed_fold_count,
            threshold=options.max_failed_fold_count,
            detail="review should not carry failed folds",
        ),
        _boolean_check(
            name="exclude_original_hit_harm_constraint",
            actual=bool(constraints.get("exclude_original_hit_harm")),
            expected=True,
            enabled=options.require_exclude_original_hit_harm,
            detail="runtime rule must keep original-hit harm exclusion",
        ),
        _maximum_check(
            name="rule_max_harm_count_vs_original",
            actual=_optional_int(constraints.get("max_harm_count_vs_original")),
            threshold=options.max_harm_count_vs_original,
            detail="runtime rule should carry the no-harm constraint",
        ),
        _maximum_check(
            name="rule_max_final_hit_harm_count_vs_original",
            actual=_optional_int(
                constraints.get("max_final_hit_harm_count_vs_original")
            ),
            threshold=options.max_final_hit_harm_count_vs_original,
            detail="runtime rule should carry final-hit no-harm constraint",
        ),
        _maximum_check(
            name="rule_max_profit_loss_harm_count_vs_original",
            actual=_optional_int(
                constraints.get("max_profit_loss_harm_count_vs_original")
            ),
            threshold=options.max_profit_loss_harm_count_vs_original,
            detail="runtime rule should carry P/L no-harm constraint",
        ),
        _boolean_check(
            name="source_chain_complete",
            actual=all(
                [
                    runtime_dry_run_report.source_grid_report_key,
                    runtime_dry_run_report.source_surface_replay_report_key,
                    runtime_dry_run_report.source_admission_report_key,
                    runtime_dry_run_report.generated_runtime_shadow_replay_report_key,
                ]
            ),
            expected=True,
            detail="review must preserve the grid/surface/admission/runtime chain",
        ),
    ]


def _review_profile_json(
    profile: Mapping[str, object],
    *,
    rules: Sequence[Mapping[str, object]],
    status: HistoricalReplacementProbabilityPreservingPromotionReviewStatus,
    options: HistoricalReplacementProbabilityPreservingPromotionReviewOptions,
    promotion_review_allowed: bool,
) -> dict[str, object]:
    payload = dict(profile)
    payload.update(
        {
            "profile_version": options.reviewed_profile_version,
            "review_id": options.review_id,
            "review_status": status,
            "promotion_review_allowed": promotion_review_allowed,
            "production_recommendation_allowed": False,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "dry_run_only": True,
            "rules": [dict(rule) for rule in rules],
            "notes": [
                *(_string_list(profile.get("notes"))),
                "promotion_review_only",
                "no_default_profile_write",
            ],
        }
    )
    return payload


def _rules(profile: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw_rules = profile.get("rules")
    if not isinstance(raw_rules, list):
        raw_rules = profile.get("short_odds_replacement_rules")
    if not isinstance(raw_rules, list):
        return []
    return [dict(rule) for rule in raw_rules if isinstance(rule, Mapping)]


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str)})


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalReplacementProbabilityPreservingPromotionReviewCheck:
    if not enabled:
        return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _equality_check(
    *,
    name: str,
    actual: str,
    expected: str,
    detail: str,
    enabled: bool = True,
) -> HistoricalReplacementProbabilityPreservingPromotionReviewCheck:
    if not enabled:
        return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
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
) -> HistoricalReplacementProbabilityPreservingPromotionReviewCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
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
) -> HistoricalReplacementProbabilityPreservingPromotionReviewCheck:
    if actual is None:
        return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalReplacementProbabilityPreservingPromotionReviewCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Review a probability-preserving replacement runtime dry-run report "
            "without writing production profiles."
        )
    )
    parser.add_argument("--runtime-dry-run-report", type=Path, required=True)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--review-id",
        default="probability_preserving_replacement_runtime_review_v1",
    )
    parser.add_argument(
        "--reviewed-profile-version",
        default="v3_1_probability_preserving_replacement_runtime_review",
    )
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-allowed-competition-count", type=int, default=5)
    parser.add_argument("--min-final-answer-count", type=int, default=30)
    parser.add_argument("--min-changed-final-answer-count", type=int, default=13)
    parser.add_argument("--min-final-answer-hit-delta-count", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--min-average-hit-probability-delta-vs-original",
        type=float,
        default=-0.02,
    )
    parser.add_argument("--max-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-final-hit-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--min-active-surface-count", type=int, default=8)
    parser.add_argument("--max-failed-surface-count", type=int, default=0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=5)
    parser.add_argument("--min-active-season-fold-count", type=int, default=5)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=13)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--allow-failed-runtime-dry-run", action="store_true")
    parser.add_argument("--allow-shadow-runtime-disallowed", action="store_true")
    parser.add_argument("--allow-non-dry-run-profile", action="store_true")
    parser.add_argument("--allow-missing-original-hit-harm-guard", action="store_true")
    parser.add_argument("--allow-production-recommendation", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalReplacementProbabilityPreservingPromotionReviewOptions:
    return HistoricalReplacementProbabilityPreservingPromotionReviewOptions(
        review_id=args.review_id,
        reviewed_profile_version=args.reviewed_profile_version,
        min_rule_count=args.min_rule_count,
        min_allowed_competition_count=args.min_allowed_competition_count,
        min_final_answer_count=args.min_final_answer_count,
        min_changed_final_answer_count=args.min_changed_final_answer_count,
        min_final_answer_hit_delta_count=args.min_final_answer_hit_delta_count,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        min_average_hit_probability_delta_vs_original=(
            args.min_average_hit_probability_delta_vs_original
        ),
        max_harm_count_vs_original=args.max_harm_count_vs_original,
        max_final_hit_harm_count_vs_original=(
            args.max_final_hit_harm_count_vs_original
        ),
        max_profit_loss_harm_count_vs_original=(
            args.max_profit_loss_harm_count_vs_original
        ),
        min_active_surface_count=args.min_active_surface_count,
        max_failed_surface_count=args.max_failed_surface_count,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        max_failed_fold_count=args.max_failed_fold_count,
        require_runtime_dry_run_passed=not args.allow_failed_runtime_dry_run,
        require_shadow_runtime_allowed=not args.allow_shadow_runtime_disallowed,
        require_dry_run_only_profile=not args.allow_non_dry_run_profile,
        require_exclude_original_hit_harm=(
            not args.allow_missing_original_hit_harm_guard
        ),
        require_no_production_allowed=not args.allow_production_recommendation,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalReplacementProbabilityPreservingPromotionReviewCheck],
    review_profile: Mapping[str, object],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "review_profile": review_profile,
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_replacement_probability_preserving_promotion_review:{digest}"
