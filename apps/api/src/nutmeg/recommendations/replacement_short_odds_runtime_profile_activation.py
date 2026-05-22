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
)
from nutmeg.recommendations.replacement_short_odds_runtime_profile_promotion import (
    HistoricalShortOddsRuntimeProfilePromotionReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

type HistoricalShortOddsRuntimeProfileActivationStatus = Literal[
    "activation_ready",
    "dry_run",
    "blocked",
]
type HistoricalShortOddsRuntimeProfileActivationCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalShortOddsRuntimeProfileActivationOptions(BaseModel):
    activated_profile_version: str = (
        "v3_1_competition_profiles_short_odds_runtime_enabled_candidate"
    )
    min_rule_count: int = Field(default=1, ge=1)
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
    require_promotion_ready: bool = True
    require_candidate_profile_ready: bool = True
    require_candidate_runtime_shadow_replay_passed: bool = True
    require_no_current_short_odds_rules: bool = True
    require_no_public_response_change: bool = True
    require_no_production_change: bool = True
    dry_run: bool = False


class HistoricalShortOddsRuntimeProfileActivationCheck(BaseModel):
    name: str
    status: HistoricalShortOddsRuntimeProfileActivationCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsRuntimeProfileActivationReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsRuntimeProfileActivationStatus
    activation_ready: bool
    activated_profile_version: str
    current_profile_version: str
    candidate_profile_version: str
    source_runtime_profile_promotion_report_key: str
    source_candidate_runtime_shadow_replay_report_key: str
    candidate_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    default_profile_written: bool = False
    checks: list[HistoricalShortOddsRuntimeProfileActivationCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    activated_profile_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_runtime_profile_activation_report(
    *,
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
    candidate_runtime_profile: Mapping[str, object],
    runtime_profile_promotion_report: HistoricalShortOddsRuntimeProfilePromotionReport
    | Mapping[str, object],
    candidate_runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | Mapping[str, object],
    options: HistoricalShortOddsRuntimeProfileActivationOptions | None = None,
) -> HistoricalShortOddsRuntimeProfileActivationReport:
    resolved_options = options or HistoricalShortOddsRuntimeProfileActivationOptions()
    raw_current_profile_set = _raw_profile_set(current_profile_set)
    raw_candidate_profile = dict(candidate_runtime_profile)
    promotion = _promotion_report(runtime_profile_promotion_report)
    candidate_replay = _runtime_shadow_replay_report(
        candidate_runtime_shadow_replay_report
    )
    current_profile_version = _string(raw_current_profile_set.get("profile_version")) or (
        "unknown"
    )
    candidate_profile_version = _string(raw_candidate_profile.get("profile_version")) or (
        "unknown"
    )
    candidate_rules = _mapping_list(
        raw_candidate_profile.get("short_odds_replacement_rules")
    )
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
        raw_candidate_profile=raw_candidate_profile,
        candidate_profile_version=candidate_profile_version,
        promotion=promotion,
        candidate_replay=candidate_replay,
        candidate_rules=candidate_rules,
        allowed_competition_ids=allowed_competition_ids,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    activation_ready = not blockers
    status: HistoricalShortOddsRuntimeProfileActivationStatus
    if blockers:
        status = "blocked"
    elif resolved_options.dry_run:
        status = "dry_run"
    else:
        status = "activation_ready"
    activated_profile = _activated_profile_json(
        raw_current_profile_set=raw_current_profile_set,
        raw_candidate_profile=raw_candidate_profile,
        candidate_rules=candidate_rules if activation_ready else [],
        promotion=promotion,
        candidate_replay=candidate_replay,
        options=resolved_options,
        status=status,
        activation_ready=activation_ready,
    )
    warnings = _warnings(status=status, blockers=blockers)
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_runtime_profile_activation_v3_1",
        "status": status,
        "activation_ready": activation_ready,
        "activated_profile_version": resolved_options.activated_profile_version,
        "current_profile_version": current_profile_version,
        "candidate_profile_version": candidate_profile_version,
        "source_runtime_profile_promotion_report_key": promotion.report_key,
        "source_candidate_runtime_shadow_replay_report_key": candidate_replay.report_key,
        "candidate_runtime_final_hit_harm_count_vs_original": (
            candidate_replay.final_hit_harm_count_vs_original
        ),
        "candidate_runtime_profit_loss_harm_count_vs_original": (
            candidate_replay.profit_loss_harm_count_vs_original
        ),
        "candidate_rule_count": len(candidate_rules),
        "allowed_competition_ids": allowed_competition_ids,
        "excluded_competition_ids": excluded_competition_ids,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "default_profile_written": False,
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, activated_profile)
    return HistoricalShortOddsRuntimeProfileActivationReport(
        report_key=report_key,
        status=status,
        activation_ready=activation_ready,
        activated_profile_version=resolved_options.activated_profile_version,
        current_profile_version=current_profile_version,
        candidate_profile_version=candidate_profile_version,
        source_runtime_profile_promotion_report_key=promotion.report_key,
        source_candidate_runtime_shadow_replay_report_key=candidate_replay.report_key,
        candidate_rule_count=len(candidate_rules),
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        production_recommendation_changed=False,
        public_response_changed=False,
        default_profile_written=False,
        checks=checks,
        blockers=blockers,
        activated_profile_json=activated_profile,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_runtime_profile_promotion_report(
    path: Path,
) -> HistoricalShortOddsRuntimeProfilePromotionReport:
    return HistoricalShortOddsRuntimeProfilePromotionReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def load_historical_short_odds_runtime_shadow_replay_report(
    path: Path,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_short_odds_runtime_profile_activation_report(
        current_profile_set=_load_json(args.current_profile_path),
        candidate_runtime_profile=_load_json(args.candidate_runtime_profile),
        runtime_profile_promotion_report=(
            load_historical_short_odds_runtime_profile_promotion_report(
                args.runtime_profile_promotion_report
            )
        ),
        candidate_runtime_shadow_replay_report=(
            load_historical_short_odds_runtime_shadow_replay_report(
                args.candidate_runtime_shadow_replay_report
            )
        ),
        options=_options_from_args(args),
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    if report.activation_ready and args.activated_profile_output_path is not None:
        args.activated_profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.activated_profile_output_path.write_text(
            f"{dumps(report.activated_profile_json, indent=2)}\n",
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
    raw_candidate_profile: Mapping[str, object],
    candidate_profile_version: str,
    promotion: HistoricalShortOddsRuntimeProfilePromotionReport,
    candidate_replay: HistoricalShortOddsRuntimeShadowReplayReport,
    candidate_rules: Sequence[Mapping[str, object]],
    allowed_competition_ids: Sequence[str],
    options: HistoricalShortOddsRuntimeProfileActivationOptions,
) -> list[HistoricalShortOddsRuntimeProfileActivationCheck]:
    candidate_source_keys = _mapping(raw_candidate_profile.get("source_report_keys"))
    final_hit_harm_threshold = _max_final_hit_harm_count_vs_original(options)
    profit_loss_harm_threshold = _max_profit_loss_harm_count_vs_original(options)
    return [
        _equality_check(
            name="promotion_status",
            actual=promotion.status,
            expected="promotion_ready",
            enabled=options.require_promotion_ready,
            detail="runtime profile promotion gate must be ready",
        ),
        _boolean_check(
            name="promotion_ready",
            actual=promotion.promotion_ready,
            expected=True,
            enabled=options.require_promotion_ready,
            detail="runtime profile promotion report must be promotion-ready",
        ),
        _boolean_check(
            name="candidate_profile_promotion_ready",
            actual=_bool(raw_candidate_profile.get("promotion_ready")),
            expected=True,
            enabled=options.require_candidate_profile_ready,
            detail="candidate runtime profile must be marked promotion-ready",
        ),
        _equality_check(
            name="candidate_profile_version_matches_promotion",
            actual=candidate_profile_version,
            expected=promotion.promoted_profile_version,
            enabled=True,
            detail="candidate runtime profile version must match promotion report",
        ),
        _equality_check(
            name="candidate_source_production_proposal_key",
            actual=_string(candidate_source_keys.get("production_proposal")),
            expected=promotion.source_production_proposal_report_key,
            enabled=True,
            detail="candidate profile must link the governed production proposal",
        ),
        _equality_check(
            name="candidate_source_promotion_smoke_key",
            actual=_string(candidate_source_keys.get("promotion_smoke")),
            expected=promotion.source_promotion_smoke_report_key,
            enabled=True,
            detail="candidate profile must link the promotion smoke report",
        ),
        _equality_check(
            name="candidate_source_runtime_shadow_replay_key",
            actual=_string(candidate_source_keys.get("runtime_shadow_replay")),
            expected=promotion.source_runtime_shadow_replay_report_key,
            enabled=True,
            detail="candidate profile must link the source runtime replay report",
        ),
        _equality_check(
            name="candidate_source_post_promotion_runtime_shadow_replay_key",
            actual=_string(
                candidate_source_keys.get("post_promotion_runtime_shadow_replay")
            ),
            expected=promotion.source_post_promotion_runtime_shadow_replay_report_key,
            enabled=promotion.source_post_promotion_runtime_shadow_replay_report_key
            is not None,
            detail="candidate profile must link the post-promotion runtime replay",
        ),
        _equality_check(
            name="candidate_source_rolling_admission_key",
            actual=_string(candidate_source_keys.get("rolling_admission")),
            expected=promotion.source_rolling_admission_report_key,
            enabled=True,
            detail="candidate profile must link the rolling admission report",
        ),
        _minimum_check(
            name="candidate_rule_count",
            actual=len(candidate_rules),
            threshold=options.min_rule_count,
            detail="candidate profile must carry enough short-odds rules",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="candidate short-odds rules must cover enough competitions",
        ),
        _boolean_check(
            name="current_profile_has_no_short_odds_rules",
            actual=not _mapping_list(
                raw_current_profile_set.get("short_odds_replacement_rules")
            ),
            expected=True,
            enabled=options.require_no_current_short_odds_rules,
            detail="default current profile must not already contain short-odds rules",
        ),
        _boolean_check(
            name="candidate_runtime_shadow_replay_passed",
            actual=candidate_replay.passed,
            expected=True,
            enabled=options.require_candidate_runtime_shadow_replay_passed,
            detail="candidate profile runtime shadow replay must pass",
        ),
        _equality_check(
            name="candidate_runtime_shadow_replay_status",
            actual=candidate_replay.status,
            expected="shadow_replay_passed",
            enabled=options.require_candidate_runtime_shadow_replay_passed,
            detail="candidate profile runtime shadow replay status must be passed",
        ),
        _equality_check(
            name="candidate_runtime_shadow_replay_source_profile_version",
            actual=candidate_replay.source_rule_profile_version,
            expected=candidate_profile_version,
            enabled=True,
            detail="candidate replay must use the candidate runtime profile",
        ),
        _minimum_check(
            name="candidate_runtime_final_answer_count",
            actual=candidate_replay.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="candidate replay must cover enough final answers",
        ),
        _minimum_check(
            name="candidate_runtime_changed_final_answer_count",
            actual=candidate_replay.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="candidate replay must affect enough final answers",
        ),
        _minimum_check(
            name="candidate_runtime_final_answer_hit_rate_delta",
            actual=candidate_replay.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="candidate replay final-answer hit rate must not regress",
        ),
        _minimum_check(
            name="candidate_runtime_roi_delta",
            actual=candidate_replay.roi_delta,
            threshold=options.min_roi_delta,
            detail="candidate replay ROI must not regress",
        ),
        _minimum_check(
            name="candidate_runtime_profit_loss_delta",
            actual=candidate_replay.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="candidate replay profit/loss must not regress",
        ),
        _maximum_check(
            name="candidate_runtime_harm_count_vs_original",
            actual=candidate_replay.harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail="candidate replay must pass compatibility no-harm",
        ),
        _maximum_check(
            name="candidate_runtime_final_hit_harm_count_vs_original",
            actual=candidate_replay.final_hit_harm_count_vs_original,
            threshold=final_hit_harm_threshold,
            detail="candidate replay must not turn original hits into misses",
        ),
        _maximum_check(
            name="candidate_runtime_profit_loss_harm_count_vs_original",
            actual=candidate_replay.profit_loss_harm_count_vs_original,
            threshold=profit_loss_harm_threshold,
            detail="candidate replay must not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="candidate_runtime_average_hit_probability_delta_vs_original",
            actual=candidate_replay.average_hit_probability_delta_vs_original,
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="candidate replay hit-probability loss must stay inside tolerance",
        ),
        _boolean_check(
            name="candidate_profile_public_response_unchanged",
            actual=not _bool(raw_candidate_profile.get("public_response_changed")),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="candidate profile must not change public response shape",
        ),
        _boolean_check(
            name="candidate_replay_public_response_unchanged",
            actual=not candidate_replay.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="candidate replay must not change public responses",
        ),
        _boolean_check(
            name="promotion_public_response_unchanged",
            actual=not promotion.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="promotion gate must not change public responses",
        ),
        _boolean_check(
            name="candidate_profile_production_unchanged",
            actual=not _bool(raw_candidate_profile.get("production_recommendation_changed")),
            expected=True,
            enabled=options.require_no_production_change,
            detail="candidate profile must not change production recommendations",
        ),
        _boolean_check(
            name="candidate_replay_production_unchanged",
            actual=not candidate_replay.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="candidate replay must not change production recommendations",
        ),
        _boolean_check(
            name="promotion_production_unchanged",
            actual=not promotion.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="promotion gate must not change production recommendations",
        ),
    ]


def _activated_profile_json(
    *,
    raw_current_profile_set: Mapping[str, object],
    raw_candidate_profile: Mapping[str, object],
    candidate_rules: Sequence[Mapping[str, object]],
    promotion: HistoricalShortOddsRuntimeProfilePromotionReport,
    candidate_replay: HistoricalShortOddsRuntimeShadowReplayReport,
    options: HistoricalShortOddsRuntimeProfileActivationOptions,
    status: HistoricalShortOddsRuntimeProfileActivationStatus,
    activation_ready: bool,
) -> dict[str, object]:
    activated_profile = dict(raw_current_profile_set)
    candidate_source_keys = _mapping(raw_candidate_profile.get("source_report_keys"))
    source_report_keys: dict[str, object] = {
        **candidate_source_keys,
        "runtime_profile_promotion": promotion.report_key,
        "candidate_runtime_shadow_replay": candidate_replay.report_key,
    }
    current_notes = _string_list(raw_current_profile_set.get("notes"))
    candidate_notes = _string_list(raw_candidate_profile.get("notes"))
    activated_profile.update(
        {
            "profile_version": options.activated_profile_version,
            "calculation_basis": (
                "historical_short_odds_runtime_profile_activation_v3_1"
            ),
            "status": status,
            "activation_ready": activation_ready,
            "base_profile_version": (
                _string(raw_current_profile_set.get("profile_version")) or "unknown"
            ),
            "candidate_profile_version": (
                _string(raw_candidate_profile.get("profile_version")) or "unknown"
            ),
            "profiles": _mapping_list(raw_current_profile_set.get("profiles")),
            "short_odds_replacement_rules": [dict(rule) for rule in candidate_rules],
            "source_report_keys": source_report_keys,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "default_profile_written": False,
            "notes": _unique(
                [
                    *current_notes,
                    *candidate_notes,
                    "Activated profile artifact only; default profile unchanged.",
                    "Short-odds replacement rules remain internal and not user-facing text.",
                    (
                        "No automated betting, wallet, payment, or guaranteed-outcome "
                        "behavior is introduced."
                    ),
                    f"runtime_profile_promotion_report_key={promotion.report_key}",
                    (
                        "candidate_runtime_shadow_replay_report_key="
                        f"{candidate_replay.report_key}"
                    ),
                ]
            ),
        }
    )
    return activated_profile


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build a gated activated short-odds runtime profile artifact."
    )
    parser.add_argument(
        "--current-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--candidate-runtime-profile", type=Path, required=True)
    parser.add_argument("--runtime-profile-promotion-report", type=Path, required=True)
    parser.add_argument(
        "--candidate-runtime-shadow-replay-report",
        type=Path,
        required=True,
    )
    parser.add_argument("--activated-profile-output-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--activated-profile-version",
        default="v3_1_competition_profiles_short_odds_runtime_enabled_candidate",
    )
    parser.add_argument("--min-rule-count", type=int, default=1)
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
    parser.add_argument("--allow-non-ready-promotion", action="store_true")
    parser.add_argument("--allow-failed-candidate-replay", action="store_true")
    parser.add_argument("--allow-existing-short-odds-rules", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalShortOddsRuntimeProfileActivationOptions:
    return HistoricalShortOddsRuntimeProfileActivationOptions(
        activated_profile_version=args.activated_profile_version,
        min_rule_count=args.min_rule_count,
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
        require_promotion_ready=not args.allow_non_ready_promotion,
        require_candidate_profile_ready=not args.allow_non_ready_promotion,
        require_candidate_runtime_shadow_replay_passed=(
            not args.allow_failed_candidate_replay
        ),
        require_no_current_short_odds_rules=not args.allow_existing_short_odds_rules,
        require_no_public_response_change=not args.allow_public_response_change,
        require_no_production_change=not args.allow_production_change,
        dry_run=args.dry_run,
    )


def _promotion_report(
    value: HistoricalShortOddsRuntimeProfilePromotionReport | Mapping[str, object],
) -> HistoricalShortOddsRuntimeProfilePromotionReport:
    if isinstance(value, HistoricalShortOddsRuntimeProfilePromotionReport):
        return value
    return HistoricalShortOddsRuntimeProfilePromotionReport.model_validate(value)


def _runtime_shadow_replay_report(
    value: HistoricalShortOddsRuntimeShadowReplayReport | Mapping[str, object],
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    if isinstance(value, HistoricalShortOddsRuntimeShadowReplayReport):
        return value
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(value)


def _raw_profile_set(
    value: CompetitionRecommendationProfileSet | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(value, CompetitionRecommendationProfileSet):
        return value.model_dump(mode="json")
    return dict(value)


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    enabled: bool,
    detail: str,
) -> HistoricalShortOddsRuntimeProfileActivationCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfileActivationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileActivationCheck(
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
) -> HistoricalShortOddsRuntimeProfileActivationCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfileActivationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileActivationCheck(
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
) -> HistoricalShortOddsRuntimeProfileActivationCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfileActivationCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileActivationCheck(
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
) -> HistoricalShortOddsRuntimeProfileActivationCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfileActivationCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileActivationCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _warnings(
    *,
    status: HistoricalShortOddsRuntimeProfileActivationStatus,
    blockers: Sequence[str],
) -> list[str]:
    warnings: list[str] = []
    if status == "blocked":
        warnings.append("short_odds_runtime_profile_activation:blocked")
    if blockers:
        warnings.extend(
            f"short_odds_runtime_profile_activation:blocker:{blocker}"
            for blocker in blockers
        )
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


def _max_final_hit_harm_count_vs_original(
    options: HistoricalShortOddsRuntimeProfileActivationOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _max_profit_loss_harm_count_vs_original(
    options: HistoricalShortOddsRuntimeProfileActivationOptions,
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
    return dict(payload) if isinstance(payload, Mapping) else {}


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsRuntimeProfileActivationCheck],
    activated_profile_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "activated_profile_json": activated_profile_json,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_runtime_profile_activation:{digest}"
