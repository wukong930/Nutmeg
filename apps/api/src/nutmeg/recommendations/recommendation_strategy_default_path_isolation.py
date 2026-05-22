from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
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
from nutmeg.recommendations.recommendation_strategy_staged_activation_smoke import (
    RecommendationStrategyStagedActivationSmokeReport,
    load_recommendation_strategy_staged_activation_smoke_report,
)
from nutmeg.recommendations.short_odds_final_answer_adapter import (
    ShortOddsFinalAnswerAdapterOptions,
    ShortOddsFinalAnswerAdapterResult,
    build_short_odds_final_answer_adapter_smoke_report,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeRuleSet,
    load_short_odds_runtime_rule_set,
)

type RecommendationStrategyDefaultPathIsolationStatus = Literal[
    "isolated",
    "watchlist",
    "blocked",
]
type RecommendationStrategyDefaultPathIsolationCheckStatus = Literal[
    "passed",
    "failed",
]


class RecommendationStrategyDefaultPathIsolationOptions(BaseModel):
    isolation_id: str = "v3_1_recommendation_strategy_default_path_isolation"
    min_rule_count: int = Field(default=1, ge=1)
    min_allowed_competition_count: int = Field(default=1, ge=0)
    require_staged_activation_ready: bool = True
    require_staged_only_profile: bool = True
    require_dry_run_only_profile: bool = True
    require_no_default_profile_write: bool = True
    require_no_production_allowed: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_default_profile_distinct_from_staged: bool = True
    require_default_profile_without_short_odds_rules: bool = True
    require_default_adapter_disabled: bool = True
    require_default_adapter_selection_unchanged: bool = True
    require_explicit_opt_in_applies: bool = True
    require_explicit_opt_in_public_unchanged: bool = True


class RecommendationStrategyDefaultPathIsolationCheck(BaseModel):
    name: str
    status: RecommendationStrategyDefaultPathIsolationCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class RecommendationStrategyDefaultPathIsolationReport(BaseModel):
    report_key: str
    status: RecommendationStrategyDefaultPathIsolationStatus
    default_path_isolated: bool
    isolation_id: str
    source_staged_activation_smoke_report_key: str
    source_strategy_gate_key: str
    default_profile_path: str
    default_profile_version: str
    staged_profile_path: str
    staged_profile_version: str
    staged_profile_rule_count: int = Field(ge=0)
    staged_selected_rule_count: int = Field(ge=0)
    staged_allowed_competition_ids: list[str] = Field(default_factory=list)
    default_adapter_status: str
    default_adapter_selection_changed: bool
    default_adapter_default_path_changed: bool
    default_adapter_public_response_changed: bool
    explicit_opt_in_adapter_status: str
    explicit_opt_in_selection_changed: bool
    explicit_opt_in_default_path_changed: bool
    explicit_opt_in_public_response_changed: bool
    default_profile_written: bool = False
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[RecommendationStrategyDefaultPathIsolationCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    default_adapter_result_json: dict[str, object] = Field(default_factory=dict)
    explicit_opt_in_adapter_result_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_recommendation_strategy_default_path_isolation_report(
    staged_activation_smoke_report: RecommendationStrategyStagedActivationSmokeReport,
    *,
    default_profile_set: CompetitionRecommendationProfileSet,
    default_profile_json: Mapping[str, object],
    default_profile_path: Path | str,
    staged_profile_path: Path | str,
    staged_rule_set: ShortOddsRuntimeRuleSet,
    options: RecommendationStrategyDefaultPathIsolationOptions | None = None,
) -> RecommendationStrategyDefaultPathIsolationReport:
    resolved_options = options or RecommendationStrategyDefaultPathIsolationOptions()
    default_adapter_result = build_short_odds_final_answer_adapter_smoke_report(
        staged_rule_set,
        options=ShortOddsFinalAnswerAdapterOptions(enable_adapter=False),
        competition_id=_first_allowed_competition(staged_rule_set),
    )
    explicit_opt_in_result = build_short_odds_final_answer_adapter_smoke_report(
        staged_rule_set,
        options=ShortOddsFinalAnswerAdapterOptions(enable_adapter=True),
        competition_id=_first_allowed_competition(staged_rule_set),
    )
    staged_profile_json = staged_activation_smoke_report.staged_profile_json
    selected_rules = staged_rule_set.selected_rules(
        require_proposed_production_enabled=True,
        require_no_production_change=True,
    )
    allowed_competition_ids = sorted(
        {
            competition_id
            for rule in selected_rules
            for competition_id in rule.allowed_competition_ids
        }
    )
    checks = _checks(
        staged_activation_smoke_report,
        default_profile_set=default_profile_set,
        default_profile_json=default_profile_json,
        default_profile_path=Path(default_profile_path),
        staged_profile_path=Path(staged_profile_path),
        staged_rule_set=staged_rule_set,
        selected_rule_count=len(selected_rules),
        allowed_competition_count=len(allowed_competition_ids),
        default_adapter_result=default_adapter_result,
        explicit_opt_in_result=explicit_opt_in_result,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    status = _status(blockers)
    default_path_isolated = status == "isolated"
    warnings = [
        *staged_activation_smoke_report.warnings,
        *default_adapter_result.warnings,
        *explicit_opt_in_result.warnings,
        *[
            f"recommendation_strategy_default_path_isolation:failed_check:{name}"
            for name in blockers
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": "recommendation_strategy_default_path_isolation_v3_1",
        "status": status,
        "default_path_isolated": default_path_isolated,
        "isolation_id": resolved_options.isolation_id,
        "source_staged_activation_smoke_report_key": (
            staged_activation_smoke_report.report_key
        ),
        "source_strategy_gate_key": (
            staged_activation_smoke_report.source_strategy_gate_key
        ),
        "default_profile_path": str(default_profile_path),
        "default_profile_version": default_profile_set.profile_version,
        "staged_profile_path": str(staged_profile_path),
        "staged_profile_version": staged_rule_set.profile_version,
        "staged_profile_rule_count": len(staged_rule_set.rules),
        "staged_selected_rule_count": len(selected_rules),
        "staged_allowed_competition_ids": allowed_competition_ids,
        "default_adapter_status": default_adapter_result.status,
        "default_adapter_selection_changed": (
            default_adapter_result.adapter_selection_changed
        ),
        "default_adapter_default_path_changed": (
            default_adapter_result.default_path_changed
        ),
        "default_adapter_public_response_changed": (
            default_adapter_result.public_response_changed
        ),
        "explicit_opt_in_adapter_status": explicit_opt_in_result.status,
        "explicit_opt_in_selection_changed": (
            explicit_opt_in_result.adapter_selection_changed
        ),
        "explicit_opt_in_default_path_changed": (
            explicit_opt_in_result.default_path_changed
        ),
        "explicit_opt_in_public_response_changed": (
            explicit_opt_in_result.public_response_changed
        ),
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(
        summary,
        checks,
        default_adapter_result,
        explicit_opt_in_result,
        staged_profile_json,
    )
    return RecommendationStrategyDefaultPathIsolationReport(
        report_key=report_key,
        status=status,
        default_path_isolated=default_path_isolated,
        isolation_id=resolved_options.isolation_id,
        source_staged_activation_smoke_report_key=(
            staged_activation_smoke_report.report_key
        ),
        source_strategy_gate_key=staged_activation_smoke_report.source_strategy_gate_key,
        default_profile_path=str(default_profile_path),
        default_profile_version=default_profile_set.profile_version,
        staged_profile_path=str(staged_profile_path),
        staged_profile_version=staged_rule_set.profile_version,
        staged_profile_rule_count=len(staged_rule_set.rules),
        staged_selected_rule_count=len(selected_rules),
        staged_allowed_competition_ids=allowed_competition_ids,
        default_adapter_status=default_adapter_result.status,
        default_adapter_selection_changed=(
            default_adapter_result.adapter_selection_changed
        ),
        default_adapter_default_path_changed=default_adapter_result.default_path_changed,
        default_adapter_public_response_changed=(
            default_adapter_result.public_response_changed
        ),
        explicit_opt_in_adapter_status=explicit_opt_in_result.status,
        explicit_opt_in_selection_changed=(
            explicit_opt_in_result.adapter_selection_changed
        ),
        explicit_opt_in_default_path_changed=explicit_opt_in_result.default_path_changed,
        explicit_opt_in_public_response_changed=(
            explicit_opt_in_result.public_response_changed
        ),
        default_profile_written=False,
        production_recommendation_allowed=False,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        blockers=blockers,
        default_adapter_result_json=default_adapter_result.model_dump(mode="json"),
        explicit_opt_in_adapter_result_json=explicit_opt_in_result.model_dump(
            mode="json"
        ),
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_recommendation_strategy_default_path_isolation_report(
    path: Path | str,
) -> RecommendationStrategyDefaultPathIsolationReport:
    return RecommendationStrategyDefaultPathIsolationReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_recommendation_strategy_default_path_isolation_report(
        load_recommendation_strategy_staged_activation_smoke_report(
            args.staged_activation_smoke_report
        ),
        default_profile_set=load_competition_recommendation_profile_set(
            args.default_profile_path
        ),
        default_profile_json=_load_json(args.default_profile_path),
        default_profile_path=args.default_profile_path,
        staged_profile_path=args.staged_profile_path,
        staged_rule_set=load_short_odds_runtime_rule_set(
            args.staged_profile_path,
            enable_shadow_replay=True,
        ),
        options=_options_from_args(args),
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
    staged_smoke: RecommendationStrategyStagedActivationSmokeReport,
    *,
    default_profile_set: CompetitionRecommendationProfileSet,
    default_profile_json: Mapping[str, object],
    default_profile_path: Path,
    staged_profile_path: Path,
    staged_rule_set: ShortOddsRuntimeRuleSet,
    selected_rule_count: int,
    allowed_competition_count: int,
    default_adapter_result: ShortOddsFinalAnswerAdapterResult,
    explicit_opt_in_result: ShortOddsFinalAnswerAdapterResult,
    options: RecommendationStrategyDefaultPathIsolationOptions,
) -> list[RecommendationStrategyDefaultPathIsolationCheck]:
    staged_profile_json = staged_smoke.staged_profile_json
    return [
        _equality_check(
            name="staged_activation_smoke_status",
            actual=staged_smoke.status,
            expected="staged_activation_ready",
            enabled=options.require_staged_activation_ready,
            detail="source staged activation smoke must be ready",
        ),
        _boolean_check(
            name="staged_activation_ready",
            actual=staged_smoke.staged_activation_ready,
            expected=True,
            enabled=options.require_staged_activation_ready,
            detail="source staged activation ready flag must be true",
        ),
        _boolean_check(
            name="staged_profile_staged_only",
            actual=bool(staged_profile_json.get("staged_only")),
            expected=True,
            enabled=options.require_staged_only_profile,
            detail="staged profile must remain staged-only",
        ),
        _boolean_check(
            name="staged_profile_dry_run_only",
            actual=bool(staged_profile_json.get("dry_run_only")),
            expected=True,
            enabled=options.require_dry_run_only_profile,
            detail="staged profile must remain dry-run-only",
        ),
        _boolean_check(
            name="staged_profile_default_not_written",
            actual=not bool(staged_profile_json.get("default_profile_written"))
            and not staged_smoke.default_profile_written,
            expected=True,
            enabled=options.require_no_default_profile_write,
            detail="staged profile must not be written as the default profile",
        ),
        _boolean_check(
            name="staged_profile_production_disallowed",
            actual=not bool(staged_profile_json.get("production_recommendation_allowed"))
            and not staged_smoke.production_recommendation_allowed,
            expected=True,
            enabled=options.require_no_production_allowed,
            detail="staged profile must not allow production recommendations",
        ),
        _boolean_check(
            name="staged_profile_no_production_change",
            actual=not bool(staged_profile_json.get("production_recommendation_changed"))
            and not staged_smoke.production_recommendation_changed,
            expected=True,
            enabled=options.require_no_production_change,
            detail="staged profile must not change production recommendations",
        ),
        _boolean_check(
            name="staged_profile_no_public_response_change",
            actual=not bool(staged_profile_json.get("public_response_changed"))
            and not staged_smoke.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="staged profile must not change public responses",
        ),
        _boolean_check(
            name="default_profile_path_distinct",
            actual=default_profile_path.resolve() != staged_profile_path.resolve(),
            expected=True,
            enabled=options.require_default_profile_distinct_from_staged,
            detail="default profile path should be distinct from staged profile path",
        ),
        _boolean_check(
            name="default_profile_version_distinct_from_staged",
            actual=default_profile_set.profile_version != staged_rule_set.profile_version,
            expected=True,
            enabled=options.require_default_profile_distinct_from_staged,
            detail="default profile version should not equal staged profile version",
        ),
        _boolean_check(
            name="default_profile_without_short_odds_rules",
            actual=not _default_profile_has_short_odds_rules(default_profile_json),
            expected=True,
            enabled=options.require_default_profile_without_short_odds_rules,
            detail="ordinary default profile should not include staged short-odds rules",
        ),
        _minimum_check(
            name="staged_rule_count",
            actual=len(staged_rule_set.rules),
            threshold=options.min_rule_count,
            detail="staged profile should carry enough rules for opt-in testing",
        ),
        _minimum_check(
            name="staged_selected_rule_count",
            actual=selected_rule_count,
            threshold=options.min_rule_count,
            detail="staged profile should expose enough selected rules",
        ),
        _minimum_check(
            name="staged_allowed_competition_count",
            actual=allowed_competition_count,
            threshold=options.min_allowed_competition_count,
            detail="staged profile should retain enough competition scope",
        ),
        _equality_check(
            name="default_adapter_status",
            actual=default_adapter_result.status,
            expected="disabled",
            enabled=options.require_default_adapter_disabled,
            detail="default adapter path must stay disabled without explicit opt-in",
        ),
        _boolean_check(
            name="default_adapter_selection_unchanged",
            actual=not default_adapter_result.adapter_selection_changed,
            expected=True,
            enabled=options.require_default_adapter_selection_unchanged,
            detail="default adapter path must not change the selection",
        ),
        _boolean_check(
            name="default_adapter_default_path_unchanged",
            actual=not default_adapter_result.default_path_changed,
            expected=True,
            enabled=options.require_default_adapter_selection_unchanged,
            detail="default adapter result must not mark the default path changed",
        ),
        _boolean_check(
            name="default_adapter_public_response_unchanged",
            actual=not default_adapter_result.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="default adapter result must not change public response",
        ),
        _equality_check(
            name="explicit_opt_in_adapter_status",
            actual=explicit_opt_in_result.status,
            expected="applied",
            enabled=options.require_explicit_opt_in_applies,
            detail="explicit internal opt-in should exercise the staged rule",
        ),
        _boolean_check(
            name="explicit_opt_in_selection_changed",
            actual=explicit_opt_in_result.adapter_selection_changed,
            expected=True,
            enabled=options.require_explicit_opt_in_applies,
            detail="explicit internal opt-in should change the smoke selection",
        ),
        _boolean_check(
            name="explicit_opt_in_public_response_unchanged",
            actual=not explicit_opt_in_result.public_response_changed,
            expected=True,
            enabled=options.require_explicit_opt_in_public_unchanged,
            detail="explicit opt-in adapter smoke should remain internal",
        ),
    ]


def _status(
    blockers: Sequence[str],
) -> RecommendationStrategyDefaultPathIsolationStatus:
    hard_blockers = {
        "staged_activation_smoke_status",
        "staged_activation_ready",
        "staged_profile_default_not_written",
        "staged_profile_production_disallowed",
        "staged_profile_no_production_change",
        "staged_profile_no_public_response_change",
        "default_profile_path_distinct",
        "default_profile_without_short_odds_rules",
        "default_adapter_status",
        "default_adapter_selection_unchanged",
        "default_adapter_default_path_unchanged",
        "default_adapter_public_response_unchanged",
    }
    if any(name in hard_blockers for name in blockers):
        return "blocked"
    if blockers:
        return "watchlist"
    return "isolated"


def _default_profile_has_short_odds_rules(payload: Mapping[str, object]) -> bool:
    return bool(payload.get("short_odds_replacement_rules")) or bool(
        payload.get("rules")
    )


def _first_allowed_competition(rule_set: ShortOddsRuntimeRuleSet) -> str | None:
    for rule in rule_set.rules:
        if rule.allowed_competition_ids:
            return rule.allowed_competition_ids[0]
    return None


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> RecommendationStrategyDefaultPathIsolationCheck:
    if not enabled:
        return RecommendationStrategyDefaultPathIsolationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyDefaultPathIsolationCheck(
        name=name,
        status="passed" if actual == expected else "failed",
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
) -> RecommendationStrategyDefaultPathIsolationCheck:
    if not enabled:
        return RecommendationStrategyDefaultPathIsolationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return RecommendationStrategyDefaultPathIsolationCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> RecommendationStrategyDefaultPathIsolationCheck:
    return RecommendationStrategyDefaultPathIsolationCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _load_json(path: Path | str) -> dict[str, object]:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Verify a staged recommendation strategy profile is isolated from "
            "the ordinary default recommendation path."
        )
    )
    parser.add_argument("--staged-activation-smoke-report", type=Path, required=True)
    parser.add_argument("--staged-profile-path", type=Path, required=True)
    parser.add_argument(
        "--default-profile-path",
        type=Path,
        default=DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH,
    )
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--isolation-id",
        default="v3_1_recommendation_strategy_default_path_isolation",
    )
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-allowed-competition-count", type=int, default=1)
    parser.add_argument("--allow-non-ready-staged-smoke", action="store_true")
    parser.add_argument("--allow-non-staged-profile", action="store_true")
    parser.add_argument("--allow-non-dry-run-profile", action="store_true")
    parser.add_argument("--allow-default-profile-write", action="store_true")
    parser.add_argument("--allow-production-recommendation", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-default-profile-same-as-staged", action="store_true")
    parser.add_argument("--allow-default-short-odds-rules", action="store_true")
    parser.add_argument("--allow-default-adapter-enabled", action="store_true")
    parser.add_argument("--allow-default-selection-change", action="store_true")
    parser.add_argument("--allow-missing-explicit-opt-in-change", action="store_true")
    parser.add_argument("--allow-explicit-opt-in-public-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> RecommendationStrategyDefaultPathIsolationOptions:
    return RecommendationStrategyDefaultPathIsolationOptions(
        isolation_id=args.isolation_id,
        min_rule_count=args.min_rule_count,
        min_allowed_competition_count=args.min_allowed_competition_count,
        require_staged_activation_ready=not args.allow_non_ready_staged_smoke,
        require_staged_only_profile=not args.allow_non_staged_profile,
        require_dry_run_only_profile=not args.allow_non_dry_run_profile,
        require_no_default_profile_write=not args.allow_default_profile_write,
        require_no_production_allowed=not args.allow_production_recommendation,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        require_default_profile_distinct_from_staged=(
            not args.allow_default_profile_same_as_staged
        ),
        require_default_profile_without_short_odds_rules=(
            not args.allow_default_short_odds_rules
        ),
        require_default_adapter_disabled=not args.allow_default_adapter_enabled,
        require_default_adapter_selection_unchanged=(
            not args.allow_default_selection_change
        ),
        require_explicit_opt_in_applies=(
            not args.allow_missing_explicit_opt_in_change
        ),
        require_explicit_opt_in_public_unchanged=(
            not args.allow_explicit_opt_in_public_change
        ),
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[RecommendationStrategyDefaultPathIsolationCheck],
    default_adapter_result: ShortOddsFinalAnswerAdapterResult,
    explicit_opt_in_result: ShortOddsFinalAnswerAdapterResult,
    staged_profile: Mapping[str, object],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "default_adapter_result": default_adapter_result.model_dump(mode="json"),
            "explicit_opt_in_result": explicit_opt_in_result.model_dump(mode="json"),
            "staged_profile": staged_profile,
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"recommendation_strategy_default_path_isolation:{digest}"
