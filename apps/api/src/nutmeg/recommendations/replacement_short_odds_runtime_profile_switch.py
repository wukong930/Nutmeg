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
from nutmeg.recommendations.replacement_short_odds_runtime_profile_activation import (
    HistoricalShortOddsRuntimeProfileActivationReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)

type HistoricalShortOddsRuntimeProfileSwitchStatus = Literal[
    "switch_ready",
    "applied",
    "dry_run",
    "blocked",
]
type HistoricalShortOddsRuntimeProfileSwitchCheckStatus = Literal[
    "passed",
    "failed",
]


class HistoricalShortOddsRuntimeProfileSwitchOptions(BaseModel):
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
    require_activation_ready: bool = True
    require_activated_runtime_shadow_replay_passed: bool = True
    require_current_profile_matches_activation_base: bool = True
    require_no_current_short_odds_rules: bool = True
    require_no_public_response_change: bool = True
    require_no_production_change: bool = True
    write_default_profile: bool = False
    confirm_default_profile_write: bool = False
    default_profile_written: bool = False
    dry_run: bool = False


class HistoricalShortOddsRuntimeProfileSwitchCheck(BaseModel):
    name: str
    status: HistoricalShortOddsRuntimeProfileSwitchCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsRuntimeProfileSwitchReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsRuntimeProfileSwitchStatus
    switch_ready: bool
    activated_profile_version: str
    current_profile_version: str
    source_runtime_profile_activation_report_key: str
    source_activated_runtime_shadow_replay_report_key: str
    candidate_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    default_profile_write_requested: bool = False
    default_profile_written: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalShortOddsRuntimeProfileSwitchCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    staged_profile_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_short_odds_runtime_profile_switch_report(
    *,
    current_profile_set: CompetitionRecommendationProfileSet | Mapping[str, object],
    activated_profile: Mapping[str, object],
    activation_report: HistoricalShortOddsRuntimeProfileActivationReport
    | Mapping[str, object],
    activated_runtime_shadow_replay_report: HistoricalShortOddsRuntimeShadowReplayReport
    | Mapping[str, object],
    options: HistoricalShortOddsRuntimeProfileSwitchOptions | None = None,
) -> HistoricalShortOddsRuntimeProfileSwitchReport:
    resolved_options = options or HistoricalShortOddsRuntimeProfileSwitchOptions()
    raw_current_profile_set = _raw_profile_set(current_profile_set)
    raw_activated_profile = dict(activated_profile)
    activation = _activation_report(activation_report)
    activated_replay = _runtime_shadow_replay_report(
        activated_runtime_shadow_replay_report
    )
    current_profile_version = _string(raw_current_profile_set.get("profile_version")) or (
        "unknown"
    )
    activated_profile_version = (
        _string(raw_activated_profile.get("profile_version")) or "unknown"
    )
    rules = _mapping_list(raw_activated_profile.get("short_odds_replacement_rules"))
    allowed_competition_ids = _unique(
        competition_id
        for rule in rules
        for competition_id in _string_list(rule.get("allowed_competition_ids"))
    )
    excluded_competition_ids = _unique(
        competition_id
        for rule in rules
        for competition_id in _string_list(rule.get("excluded_competition_ids"))
    )
    checks = _checks(
        raw_current_profile_set=raw_current_profile_set,
        raw_activated_profile=raw_activated_profile,
        activated_profile_version=activated_profile_version,
        activation=activation,
        activated_replay=activated_replay,
        rules=rules,
        allowed_competition_ids=allowed_competition_ids,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    switch_ready = not blockers
    status: HistoricalShortOddsRuntimeProfileSwitchStatus
    if blockers:
        status = "blocked"
    elif resolved_options.dry_run:
        status = "dry_run"
    elif resolved_options.default_profile_written:
        status = "applied"
    else:
        status = "switch_ready"
    staged_profile = _staged_profile_json(
        raw_activated_profile=raw_activated_profile,
        activation=activation,
        activated_replay=activated_replay,
        rules=rules if switch_ready else [],
        options=resolved_options,
        status=status,
        switch_ready=switch_ready,
    )
    warnings = _warnings(
        status=status,
        blockers=blockers,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_runtime_profile_switch_v3_1",
        "status": status,
        "switch_ready": switch_ready,
        "activated_profile_version": activated_profile_version,
        "current_profile_version": current_profile_version,
        "source_runtime_profile_activation_report_key": activation.report_key,
        "source_activated_runtime_shadow_replay_report_key": activated_replay.report_key,
        "activated_runtime_final_hit_harm_count_vs_original": (
            activated_replay.final_hit_harm_count_vs_original
        ),
        "activated_runtime_profit_loss_harm_count_vs_original": (
            activated_replay.profit_loss_harm_count_vs_original
        ),
        "candidate_rule_count": len(rules),
        "allowed_competition_ids": allowed_competition_ids,
        "excluded_competition_ids": excluded_competition_ids,
        "default_profile_write_requested": resolved_options.write_default_profile,
        "default_profile_written": resolved_options.default_profile_written,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "blockers": blockers,
        "options": _options_json(resolved_options),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, staged_profile)
    return HistoricalShortOddsRuntimeProfileSwitchReport(
        report_key=report_key,
        status=status,
        switch_ready=switch_ready,
        activated_profile_version=activated_profile_version,
        current_profile_version=current_profile_version,
        source_runtime_profile_activation_report_key=activation.report_key,
        source_activated_runtime_shadow_replay_report_key=activated_replay.report_key,
        candidate_rule_count=len(rules),
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        default_profile_write_requested=resolved_options.write_default_profile,
        default_profile_written=resolved_options.default_profile_written,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        blockers=blockers,
        staged_profile_json=staged_profile,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_runtime_profile_activation_report(
    path: Path,
) -> HistoricalShortOddsRuntimeProfileActivationReport:
    return HistoricalShortOddsRuntimeProfileActivationReport.model_validate_json(
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
    options = _options_from_args(args)
    current_profile = _load_json(args.current_profile_path)
    activated_profile = _load_json(args.activated_profile)
    activation = load_historical_short_odds_runtime_profile_activation_report(
        args.activation_report
    )
    activated_replay = load_historical_short_odds_runtime_shadow_replay_report(
        args.activated_runtime_shadow_replay_report
    )
    report = build_historical_short_odds_runtime_profile_switch_report(
        current_profile_set=current_profile,
        activated_profile=activated_profile,
        activation_report=activation,
        activated_runtime_shadow_replay_report=activated_replay,
        options=options,
    )
    if (
        report.switch_ready
        and options.write_default_profile
        and options.confirm_default_profile_write
        and not options.dry_run
    ):
        report = build_historical_short_odds_runtime_profile_switch_report(
            current_profile_set=current_profile,
            activated_profile=activated_profile,
            activation_report=activation,
            activated_runtime_shadow_replay_report=activated_replay,
            options=options.model_copy(update={"default_profile_written": True}),
        )
        args.current_profile_path.parent.mkdir(parents=True, exist_ok=True)
        args.current_profile_path.write_text(
            f"{dumps(report.staged_profile_json, indent=2)}\n",
            encoding="utf-8",
        )
    if report.switch_ready and args.staged_profile_output_path is not None:
        args.staged_profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.staged_profile_output_path.write_text(
            f"{dumps(report.staged_profile_json, indent=2)}\n",
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
    *,
    raw_current_profile_set: Mapping[str, object],
    raw_activated_profile: Mapping[str, object],
    activated_profile_version: str,
    activation: HistoricalShortOddsRuntimeProfileActivationReport,
    activated_replay: HistoricalShortOddsRuntimeShadowReplayReport,
    rules: Sequence[Mapping[str, object]],
    allowed_competition_ids: Sequence[str],
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
) -> list[HistoricalShortOddsRuntimeProfileSwitchCheck]:
    activated_source_keys = _mapping(raw_activated_profile.get("source_report_keys"))
    current_profile_version = _string(raw_current_profile_set.get("profile_version"))
    final_hit_harm_threshold = _max_final_hit_harm_count_vs_original(options)
    profit_loss_harm_threshold = _max_profit_loss_harm_count_vs_original(options)
    return [
        _equality_check(
            name="activation_status",
            actual=activation.status,
            expected="activation_ready",
            enabled=options.require_activation_ready,
            detail="runtime profile activation report must be ready",
        ),
        _boolean_check(
            name="activation_ready",
            actual=activation.activation_ready,
            expected=True,
            enabled=options.require_activation_ready,
            detail="activation report must mark the profile as ready",
        ),
        _boolean_check(
            name="activated_profile_activation_ready",
            actual=_bool(raw_activated_profile.get("activation_ready")),
            expected=True,
            enabled=options.require_activation_ready,
            detail="activated profile must carry activation_ready=true",
        ),
        _equality_check(
            name="activated_profile_version_matches_activation",
            actual=activated_profile_version,
            expected=activation.activated_profile_version,
            enabled=True,
            detail="activated profile version must match the activation report",
        ),
        _equality_check(
            name="activated_profile_base_matches_activation_current",
            actual=_string(raw_activated_profile.get("base_profile_version")),
            expected=activation.current_profile_version,
            enabled=True,
            detail="activated profile base version must match activation evidence",
        ),
        _equality_check(
            name="current_profile_matches_activation_current",
            actual=current_profile_version,
            expected=activation.current_profile_version,
            enabled=options.require_current_profile_matches_activation_base,
            detail="current default profile must still match the activation base",
        ),
        _boolean_check(
            name="current_profile_has_no_short_odds_rules",
            actual=not _mapping_list(
                raw_current_profile_set.get("short_odds_replacement_rules")
            ),
            expected=True,
            enabled=options.require_no_current_short_odds_rules,
            detail="current default profile must not already contain short-odds rules",
        ),
        _equality_check(
            name="activated_source_runtime_profile_promotion_key",
            actual=_string(activated_source_keys.get("runtime_profile_promotion")),
            expected=activation.source_runtime_profile_promotion_report_key,
            enabled=True,
            detail="activated profile must link the promotion report",
        ),
        _equality_check(
            name="activated_source_candidate_runtime_shadow_replay_key",
            actual=_string(activated_source_keys.get("candidate_runtime_shadow_replay")),
            expected=activation.source_candidate_runtime_shadow_replay_report_key,
            enabled=True,
            detail="activated profile must link the candidate replay report",
        ),
        _minimum_check(
            name="candidate_rule_count",
            actual=len(rules),
            threshold=options.min_rule_count,
            detail="activated profile must carry enough short-odds rules",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="activated short-odds rules must cover enough competitions",
        ),
        _boolean_check(
            name="activated_runtime_shadow_replay_passed",
            actual=activated_replay.passed,
            expected=True,
            enabled=options.require_activated_runtime_shadow_replay_passed,
            detail="activated profile runtime shadow replay must pass",
        ),
        _equality_check(
            name="activated_runtime_shadow_replay_status",
            actual=activated_replay.status,
            expected="shadow_replay_passed",
            enabled=options.require_activated_runtime_shadow_replay_passed,
            detail="activated profile runtime replay status must be passed",
        ),
        _equality_check(
            name="activated_runtime_shadow_replay_source_profile_version",
            actual=activated_replay.source_rule_profile_version,
            expected=activated_profile_version,
            enabled=True,
            detail="activated replay must use the activated profile version",
        ),
        _minimum_check(
            name="activated_runtime_final_answer_count",
            actual=activated_replay.final_answer_count,
            threshold=options.min_final_answer_count,
            detail="activated replay must cover enough final answers",
        ),
        _minimum_check(
            name="activated_runtime_changed_final_answer_count",
            actual=activated_replay.changed_final_answer_count,
            threshold=options.min_changed_final_answer_count,
            detail="activated replay must affect enough final answers",
        ),
        _minimum_check(
            name="activated_runtime_final_answer_hit_rate_delta",
            actual=activated_replay.final_answer_hit_rate_delta,
            threshold=options.min_final_answer_hit_rate_delta,
            detail="activated replay final-answer hit rate must not regress",
        ),
        _minimum_check(
            name="activated_runtime_roi_delta",
            actual=activated_replay.roi_delta,
            threshold=options.min_roi_delta,
            detail="activated replay ROI must not regress",
        ),
        _minimum_check(
            name="activated_runtime_profit_loss_delta",
            actual=activated_replay.profit_loss_delta,
            threshold=options.min_profit_loss_delta,
            detail="activated replay profit/loss must not regress",
        ),
        _maximum_check(
            name="activated_runtime_harm_count_vs_original",
            actual=activated_replay.harm_count_vs_original,
            threshold=options.max_harm_count_vs_original,
            detail="activated replay must pass compatibility no-harm",
        ),
        _maximum_check(
            name="activated_runtime_final_hit_harm_count_vs_original",
            actual=activated_replay.final_hit_harm_count_vs_original,
            threshold=final_hit_harm_threshold,
            detail="activated replay must not turn original hits into misses",
        ),
        _maximum_check(
            name="activated_runtime_profit_loss_harm_count_vs_original",
            actual=activated_replay.profit_loss_harm_count_vs_original,
            threshold=profit_loss_harm_threshold,
            detail="activated replay must not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="activated_runtime_average_hit_probability_delta_vs_original",
            actual=activated_replay.average_hit_probability_delta_vs_original,
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="activated replay hit-probability loss must stay inside tolerance",
        ),
        _boolean_check(
            name="activation_public_response_unchanged",
            actual=not activation.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="activation gate must not change public responses",
        ),
        _boolean_check(
            name="activated_replay_public_response_unchanged",
            actual=not activated_replay.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="activated replay must not change public responses",
        ),
        _boolean_check(
            name="activation_production_unchanged",
            actual=not activation.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="activation gate must not change production recommendations",
        ),
        _boolean_check(
            name="activated_replay_production_unchanged",
            actual=not activated_replay.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="activated replay must not change production recommendations",
        ),
        _boolean_check(
            name="default_profile_write_confirmation",
            actual=options.confirm_default_profile_write,
            expected=True,
            enabled=options.write_default_profile,
            detail="default profile writes require an explicit confirmation flag",
        ),
    ]


def _staged_profile_json(
    *,
    raw_activated_profile: Mapping[str, object],
    activation: HistoricalShortOddsRuntimeProfileActivationReport,
    activated_replay: HistoricalShortOddsRuntimeShadowReplayReport,
    rules: Sequence[Mapping[str, object]],
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
    status: HistoricalShortOddsRuntimeProfileSwitchStatus,
    switch_ready: bool,
) -> dict[str, object]:
    staged_profile = dict(raw_activated_profile)
    source_report_keys = {
        **_mapping(raw_activated_profile.get("source_report_keys")),
        "runtime_profile_activation": activation.report_key,
        "activated_runtime_shadow_replay": activated_replay.report_key,
    }
    staged_profile.update(
        {
            "calculation_basis": "historical_short_odds_runtime_profile_switch_v3_1",
            "status": status,
            "switch_ready": switch_ready,
            "short_odds_replacement_rules": [dict(rule) for rule in rules],
            "source_report_keys": source_report_keys,
            "default_profile_write_requested": options.write_default_profile,
            "default_profile_written": options.default_profile_written,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "notes": _unique(
                [
                    *_string_list(raw_activated_profile.get("notes")),
                    (
                        "Switch gate staged profile; default profile is only "
                        "written with explicit confirmation."
                    ),
                    "Short-odds replacement rules remain internal and not user-facing text.",
                    (
                        "No automated betting, wallet, payment, or guaranteed-outcome "
                        "behavior is introduced."
                    ),
                    f"runtime_profile_activation_report_key={activation.report_key}",
                    (
                        "activated_runtime_shadow_replay_report_key="
                        f"{activated_replay.report_key}"
                    ),
                ]
            ),
        }
    )
    return staged_profile


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build or explicitly apply a gated short-odds runtime profile."
    )
    parser.add_argument(
        "--current-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--activated-profile", type=Path, required=True)
    parser.add_argument("--activation-report", type=Path, required=True)
    parser.add_argument(
        "--activated-runtime-shadow-replay-report",
        type=Path,
        required=True,
    )
    parser.add_argument("--staged-profile-output-path", type=Path)
    parser.add_argument("--report-output-path", type=Path)
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
    parser.add_argument("--allow-non-ready-activation", action="store_true")
    parser.add_argument("--allow-failed-activated-replay", action="store_true")
    parser.add_argument("--allow-stale-current-profile", action="store_true")
    parser.add_argument("--allow-existing-short-odds-rules", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--write-default-profile", action="store_true")
    parser.add_argument("--confirm-default-profile-write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsRuntimeProfileSwitchOptions:
    return HistoricalShortOddsRuntimeProfileSwitchOptions(
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
        require_activation_ready=not args.allow_non_ready_activation,
        require_activated_runtime_shadow_replay_passed=(
            not args.allow_failed_activated_replay
        ),
        require_current_profile_matches_activation_base=(
            not args.allow_stale_current_profile
        ),
        require_no_current_short_odds_rules=not args.allow_existing_short_odds_rules,
        require_no_public_response_change=not args.allow_public_response_change,
        require_no_production_change=not args.allow_production_change,
        write_default_profile=args.write_default_profile,
        confirm_default_profile_write=args.confirm_default_profile_write,
        dry_run=args.dry_run,
    )


def _activation_report(
    value: HistoricalShortOddsRuntimeProfileActivationReport | Mapping[str, object],
) -> HistoricalShortOddsRuntimeProfileActivationReport:
    if isinstance(value, HistoricalShortOddsRuntimeProfileActivationReport):
        return value
    return HistoricalShortOddsRuntimeProfileActivationReport.model_validate(value)


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
) -> HistoricalShortOddsRuntimeProfileSwitchCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfileSwitchCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileSwitchCheck(
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
) -> HistoricalShortOddsRuntimeProfileSwitchCheck:
    if not enabled:
        return HistoricalShortOddsRuntimeProfileSwitchCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileSwitchCheck(
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
) -> HistoricalShortOddsRuntimeProfileSwitchCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfileSwitchCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileSwitchCheck(
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
) -> HistoricalShortOddsRuntimeProfileSwitchCheck:
    if actual is None:
        return HistoricalShortOddsRuntimeProfileSwitchCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsRuntimeProfileSwitchCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _warnings(
    *,
    status: HistoricalShortOddsRuntimeProfileSwitchStatus,
    blockers: Sequence[str],
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
) -> list[str]:
    warnings: list[str] = []
    if status == "blocked":
        warnings.append("short_odds_runtime_profile_switch:blocked")
    if blockers:
        warnings.extend(
            f"short_odds_runtime_profile_switch:blocker:{blocker}"
            for blocker in blockers
        )
    if options.write_default_profile and not options.confirm_default_profile_write:
        warnings.append("short_odds_runtime_profile_switch:write_requires_confirmation")
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
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _max_profit_loss_harm_count_vs_original(
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
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


def _options_json(
    options: HistoricalShortOddsRuntimeProfileSwitchOptions,
) -> dict[str, object]:
    return options.model_dump(
        mode="json",
        exclude={"default_profile_written"},
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalShortOddsRuntimeProfileSwitchCheck],
    staged_profile_json: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "staged_profile_json": staged_profile_json,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_short_odds_runtime_profile_switch:{digest}"
