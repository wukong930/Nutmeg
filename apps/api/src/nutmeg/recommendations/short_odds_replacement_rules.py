from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type ShortOddsReplacementRuleManifestStatus = Literal["ready", "blocked", "empty"]
type ShortOddsReplacementRuleManifestCheckStatus = Literal["passed", "failed"]

DEFAULT_REQUIRED_SOURCE_REPORT_KEYS = (
    "suite_gate",
    "final_answer_gate",
    "audit",
    "competition_gate",
    "generated_shadow",
    "runtime_shadow_replay",
    "rolling_admission",
)


class ShortOddsReplacementRuleConstraints(BaseModel):
    selection_rule: str | None = None
    max_replacements_per_final_answer: int = Field(default=1, ge=1)
    min_replacement_probability: float = Field(default=0.55, ge=0.0, le=1.0)
    max_replacement_decimal_odds: float = Field(default=1.75, gt=1.0)
    min_candidate_hit_probability_delta_vs_model_top: float = -0.015
    max_candidate_hit_probability_delta_vs_model_top: float = 0.0
    min_decimal_odds_delta_vs_model_top: float = 0.0
    min_average_hit_probability_delta_vs_original: float = -0.02
    min_candidate_hit_probability_delta_vs_original: float | None = None
    max_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)


class ShortOddsRuntimeReplacementRule(BaseModel):
    rule_id: str
    profile_id: str
    proposed_profile_version: str | None = None
    proposed_production_enabled: bool = False
    production_recommendation_changed: bool = False
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    selection_rule: str | None = None
    constraints_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def constraints(self) -> ShortOddsReplacementRuleConstraints:
        return ShortOddsReplacementRuleConstraints.model_validate(self.constraints_json)

    def allows_competition(self, competition_id: str) -> bool:
        if competition_id in self.excluded_competition_ids:
            return False
        return (
            not self.allowed_competition_ids
            or competition_id in self.allowed_competition_ids
        )


class ShortOddsRuntimeRuleSet(BaseModel):
    profile_version: str = "unknown"
    calculation_basis: str = "short_odds_runtime_rule_loader_v3_1"
    shadow_replay_enabled: bool = False
    rules: list[ShortOddsRuntimeReplacementRule] = Field(default_factory=list)
    source_json_path: str | None = None
    notes: list[str] = Field(default_factory=list)

    def selected_rules(
        self,
        *,
        rule_ids: Sequence[str] = (),
        require_proposed_production_enabled: bool = True,
        require_no_production_change: bool = True,
    ) -> list[ShortOddsRuntimeReplacementRule]:
        selected_rule_ids = set(rule_ids)
        return [
            rule
            for rule in self.rules
            if (not selected_rule_ids or rule.rule_id in selected_rule_ids)
            and (
                not require_proposed_production_enabled
                or rule.proposed_production_enabled
            )
            and (
                not require_no_production_change
                or not rule.production_recommendation_changed
            )
        ]


class ShortOddsReplacementRuleManifestOptions(BaseModel):
    rule_ids: tuple[str, ...] = ()
    enabled_rules_only: bool = True
    min_rule_count: int = Field(default=1, ge=1)
    min_allowed_competition_count: int = Field(default=1, ge=0)
    require_no_allowed_excluded_overlap: bool = True
    require_proposed_production_enabled: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True
    require_runtime_shadow_replay_passed: bool = True
    require_rolling_admission_accepted: bool = True
    require_rolling_admission_production_allowed: bool = True
    require_no_harm_constraints: bool = True
    required_source_report_keys: tuple[str, ...] = DEFAULT_REQUIRED_SOURCE_REPORT_KEYS


class ShortOddsReplacementRuleManifestCheck(BaseModel):
    name: str
    status: ShortOddsReplacementRuleManifestCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class ShortOddsReplacementRuleManifestReport(BaseModel):
    report_key: str
    status: ShortOddsReplacementRuleManifestStatus
    ready: bool
    profile_version: str
    calculation_basis: str
    source_json_path: str | None = None
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    enabled_rule_count: int = Field(ge=0)
    allowed_competition_ids: list[str] = Field(default_factory=list)
    excluded_competition_ids: list[str] = Field(default_factory=list)
    selection_rules: list[str] = Field(default_factory=list)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[ShortOddsReplacementRuleManifestCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    rule_set_json: dict[str, object] = Field(default_factory=dict)
    selected_rules_json: list[dict[str, object]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_short_odds_runtime_rule_set(
    path: Path,
    *,
    enable_shadow_replay: bool = False,
) -> ShortOddsRuntimeRuleSet:
    payload = _load_json(path)
    profile_json = extract_short_odds_runtime_rule_profile_json(payload)
    rules = [
        ShortOddsRuntimeReplacementRule.model_validate(rule)
        for rule in _mapping_list(profile_json.get("short_odds_replacement_rules"))
    ]
    if not rules:
        rules = [
            ShortOddsRuntimeReplacementRule.model_validate(rule)
            for rule in _mapping_list(profile_json.get("rules"))
        ]
    return ShortOddsRuntimeRuleSet(
        profile_version=_string(profile_json.get("profile_version")) or "unknown",
        calculation_basis=(
            _string(profile_json.get("calculation_basis"))
            or "short_odds_runtime_rule_loader_v3_1"
        ),
        shadow_replay_enabled=enable_shadow_replay,
        rules=rules,
        source_json_path=str(path),
        notes=_string_list(profile_json.get("notes")),
    )


def extract_short_odds_runtime_rule_profile_json(
    payload: Mapping[str, object],
) -> dict[str, object]:
    for key in (
        "staged_profile_json",
        "activated_profile_json",
        "temporary_profile_set_json",
        "proposal_profile_set_json",
        "candidate_profile_json",
    ):
        profile = payload.get(key)
        if isinstance(profile, Mapping):
            return dict(profile)
    return dict(payload)


def build_short_odds_replacement_rule_manifest_report(
    rule_set: ShortOddsRuntimeRuleSet,
    *,
    options: ShortOddsReplacementRuleManifestOptions | None = None,
) -> ShortOddsReplacementRuleManifestReport:
    resolved_options = options or ShortOddsReplacementRuleManifestOptions()
    selected_rules = rule_set.selected_rules(
        rule_ids=resolved_options.rule_ids,
        require_proposed_production_enabled=resolved_options.enabled_rules_only,
        require_no_production_change=resolved_options.enabled_rules_only,
    )
    if not resolved_options.enabled_rules_only:
        selected_rule_ids = set(resolved_options.rule_ids)
        selected_rules = [
            rule
            for rule in rule_set.rules
            if not selected_rule_ids or rule.rule_id in selected_rule_ids
        ]
    allowed_competition_ids = _unique(
        competition_id
        for rule in selected_rules
        for competition_id in rule.allowed_competition_ids
    )
    excluded_competition_ids = _unique(
        competition_id
        for rule in selected_rules
        for competition_id in rule.excluded_competition_ids
    )
    checks = _manifest_checks(
        selected_rules,
        rule_set=rule_set,
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    ready = not blockers and bool(selected_rules)
    status: ShortOddsReplacementRuleManifestStatus
    if not selected_rules:
        status = "empty"
    elif blockers:
        status = "blocked"
    else:
        status = "ready"
    warnings = [f"short_odds_rule_manifest:failed_check:{name}" for name in blockers]
    enabled_rule_count = len(
        [
            rule
            for rule in rule_set.rules
            if rule.proposed_production_enabled
            and not rule.production_recommendation_changed
        ]
    )
    selection_rules = _unique(
        rule.selection_rule or rule.constraints().selection_rule or "unknown"
        for rule in selected_rules
    )
    summary: dict[str, object] = {
        "calculation_basis": "short_odds_replacement_rule_manifest_v3_1",
        "status": status,
        "ready": ready,
        "profile_version": rule_set.profile_version,
        "source_json_path": rule_set.source_json_path,
        "rule_count": len(rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "enabled_rule_count": enabled_rule_count,
        "allowed_competition_ids": allowed_competition_ids,
        "excluded_competition_ids": excluded_competition_ids,
        "selection_rules": selection_rules,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, selected_rules)
    return ShortOddsReplacementRuleManifestReport(
        report_key=report_key,
        status=status,
        ready=ready,
        profile_version=rule_set.profile_version,
        calculation_basis=rule_set.calculation_basis,
        source_json_path=rule_set.source_json_path,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        enabled_rule_count=enabled_rule_count,
        allowed_competition_ids=allowed_competition_ids,
        excluded_competition_ids=excluded_competition_ids,
        selection_rules=selection_rules,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        blockers=blockers,
        rule_set_json=rule_set.model_dump(mode="json"),
        selected_rules_json=[rule.model_dump(mode="json") for rule in selected_rules],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    options = _options_from_args(args)
    report = build_short_odds_replacement_rule_manifest_report(
        load_short_odds_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=args.enable_shadow_replay,
        ),
        options=options,
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
    if not report.ready and not args.no_fail_process:
        raise SystemExit(1)


def _manifest_checks(
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    *,
    rule_set: ShortOddsRuntimeRuleSet,
    allowed_competition_ids: Sequence[str],
    excluded_competition_ids: Sequence[str],
    options: ShortOddsReplacementRuleManifestOptions,
) -> list[ShortOddsReplacementRuleManifestCheck]:
    overlap = sorted(set(allowed_competition_ids) & set(excluded_competition_ids))
    checks = [
        _minimum_check(
            name="selected_rule_count",
            actual=len(selected_rules),
            threshold=options.min_rule_count,
            detail="at least one selected short-odds replacement rule is required",
        ),
        _minimum_check(
            name="allowed_competition_count",
            actual=len(allowed_competition_ids),
            threshold=options.min_allowed_competition_count,
            detail="selected rules should name enough scoped competitions",
        ),
    ]
    if options.require_no_allowed_excluded_overlap:
        checks.append(
            _boolean_check(
                name="allowed_excluded_competition_disjoint",
                actual=not overlap,
                expected=True,
                detail="a competition cannot be both allowed and excluded",
            )
        )
    if options.require_proposed_production_enabled:
        checks.append(
            _boolean_check(
                name="all_selected_rules_enabled",
                actual=all(rule.proposed_production_enabled for rule in selected_rules),
                expected=True,
                detail="manifest can only carry explicitly enabled staged rules",
            )
        )
    if options.require_no_production_change:
        checks.append(
            _boolean_check(
                name="no_production_recommendation_change",
                actual=not any(
                    rule.production_recommendation_changed for rule in selected_rules
                ),
                expected=True,
                detail="rule manifest must not change production recommendations",
            )
        )
    if options.require_no_public_response_change:
        checks.append(
            _boolean_check(
                name="no_public_response_change",
                actual=True,
                expected=True,
                detail="rule manifest is internal and must not change public responses",
            )
        )
    if options.require_runtime_shadow_replay_passed:
        checks.append(
            _boolean_check(
                name="runtime_shadow_replay_passed",
                actual=all(
                    _bool(rule.evidence_json.get("runtime_shadow_replay_passed"))
                    for rule in selected_rules
                ),
                expected=True,
                detail="every selected rule should carry passed runtime shadow evidence",
            )
        )
    if options.require_rolling_admission_accepted:
        checks.append(
            _boolean_check(
                name="rolling_admission_accepted",
                actual=all(
                    _bool(rule.evidence_json.get("rolling_admission_accepted"))
                    for rule in selected_rules
                ),
                expected=True,
                detail="every selected rule should carry accepted rolling admission evidence",
            )
        )
    if options.require_rolling_admission_production_allowed:
        checks.append(
            _boolean_check(
                name="rolling_admission_production_allowed",
                actual=all(
                    _bool(rule.evidence_json.get("rolling_admission_production_allowed"))
                    for rule in selected_rules
                ),
                expected=True,
                detail="rolling admission must allow the staged production candidate",
            )
        )
    if options.require_no_harm_constraints:
        checks.extend(_no_harm_constraint_checks(selected_rules))
    if options.required_source_report_keys:
        missing_source_keys = _missing_source_report_keys(
            selected_rules,
            required_keys=options.required_source_report_keys,
        )
        checks.append(
            ShortOddsReplacementRuleManifestCheck(
                name="source_report_keys_present",
                status="passed" if not missing_source_keys else "failed",
                actual=missing_source_keys,
                threshold=list(options.required_source_report_keys),
                detail="selected rules must retain their upstream evidence report keys",
            )
        )
    if rule_set.source_json_path is None:
        checks.append(
            _boolean_check(
                name="source_json_path_present",
                actual=False,
                expected=True,
                detail="manifest should be traceable to a local source JSON artifact",
            )
        )
    return checks


def _no_harm_constraint_checks(
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
) -> list[ShortOddsReplacementRuleManifestCheck]:
    constraints = [rule.constraints() for rule in selected_rules]
    return [
        _boolean_check(
            name="max_harm_count_vs_original_zero",
            actual=all(item.max_harm_count_vs_original == 0 for item in constraints),
            expected=True,
            detail="selected rules must keep compatibility harm at zero",
        ),
        _boolean_check(
            name="max_final_hit_harm_count_vs_original_zero",
            actual=all(
                item.max_final_hit_harm_count_vs_original == 0 for item in constraints
            ),
            expected=True,
            detail="selected rules must not turn historical final hits into misses",
        ),
        _boolean_check(
            name="max_profit_loss_harm_count_vs_original_zero",
            actual=all(
                item.max_profit_loss_harm_count_vs_original == 0
                for item in constraints
            ),
            expected=True,
            detail="selected rules must not reduce historical final-answer profit/loss",
        ),
    ]


def _missing_source_report_keys(
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
    *,
    required_keys: Sequence[str],
) -> list[str]:
    missing: list[str] = []
    for rule in selected_rules:
        for key in required_keys:
            if not rule.source_report_keys.get(key):
                missing.append(f"{rule.rule_id}:{key}")
    return missing


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Build an internal manifest for staged short-odds replacement rules."
    )
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-shadow-replay", action="store_true")
    parser.add_argument(
        "--rule-ids",
        default="",
        help="Comma-separated rule ids. Empty means all selected rules.",
    )
    parser.add_argument("--include-disabled-rules", action="store_true")
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-allowed-competition-count", type=int, default=1)
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--allow-missing-runtime-shadow-replay", action="store_true")
    parser.add_argument("--allow-missing-rolling-admission", action="store_true")
    parser.add_argument("--allow-harm-constraints", action="store_true")
    parser.add_argument(
        "--required-source-report-keys",
        default=",".join(DEFAULT_REQUIRED_SOURCE_REPORT_KEYS),
        help="Comma-separated evidence keys that must be present on every rule.",
    )
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> ShortOddsReplacementRuleManifestOptions:
    return ShortOddsReplacementRuleManifestOptions(
        rule_ids=_csv_values(args.rule_ids),
        enabled_rules_only=not args.include_disabled_rules,
        min_rule_count=args.min_rule_count,
        min_allowed_competition_count=args.min_allowed_competition_count,
        require_proposed_production_enabled=not args.include_disabled_rules,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
        require_runtime_shadow_replay_passed=not args.allow_missing_runtime_shadow_replay,
        require_rolling_admission_accepted=not args.allow_missing_rolling_admission,
        require_rolling_admission_production_allowed=(
            not args.allow_missing_rolling_admission
        ),
        require_no_harm_constraints=not args.allow_harm_constraints,
        required_source_report_keys=_csv_values(args.required_source_report_keys),
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> ShortOddsReplacementRuleManifestCheck:
    return ShortOddsReplacementRuleManifestCheck(
        name=name,
        status="passed" if actual is expected else "failed",
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
) -> ShortOddsReplacementRuleManifestCheck:
    return ShortOddsReplacementRuleManifestCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _load_json(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


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


def _csv_values(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _bool(value: object) -> bool:
    return value is True


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[ShortOddsReplacementRuleManifestCheck],
    selected_rules: Sequence[ShortOddsRuntimeReplacementRule],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "selected_rules": [
                    {
                        "rule_id": rule.rule_id,
                        "profile_id": rule.profile_id,
                        "allowed_competition_ids": rule.allowed_competition_ids,
                        "excluded_competition_ids": rule.excluded_competition_ids,
                    }
                    for rule in selected_rules
                ],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"short_odds_replacement_rule_manifest:{digest}"
