from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.short_odds_adapter_activation_scope_search import (
    ShortOddsAdapterActivationScopeCandidate,
    ShortOddsAdapterActivationScopeSearchReport,
    load_short_odds_adapter_activation_scope_search_report,
)

type ShortOddsAdapterActivationScopeSupplementalStatus = Literal[
    "supplemental_validated",
    "supplemental_blocked",
    "no_base_scope",
    "no_supplemental_reports",
]
type ShortOddsAdapterActivationScopeSupplementalCheckStatus = Literal[
    "passed",
    "failed",
]


class ShortOddsAdapterActivationScopeSupplementalOptions(BaseModel):
    scope_competition_ids: tuple[str, ...] = ()
    min_supplemental_report_count: int = Field(default=1, ge=0)
    min_supplemental_changed_final_answer_count: int = Field(default=2, ge=0)
    min_total_changed_final_answer_count: int = Field(default=4, ge=0)
    min_supplemental_final_answer_hit_rate_delta: float = 0.0
    min_supplemental_roi_delta: float = 0.0
    min_supplemental_profit_loss_delta: float = 0.0
    max_supplemental_failed_fold_count: int = Field(default=0, ge=0)
    max_supplemental_harm_count_vs_original: int = Field(default=0, ge=0)
    require_supplemental_accepted: bool = True


class ShortOddsAdapterActivationScopeSupplementalCheck(BaseModel):
    name: str
    status: ShortOddsAdapterActivationScopeSupplementalCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class ShortOddsAdapterActivationScopeSupplementalItem(BaseModel):
    source_report_key: str
    matched: bool
    status: str | None = None
    scope_key: str | None = None
    scope_competition_ids: list[str] = Field(default_factory=list)
    overall_final_answer_count: int = Field(default=0, ge=0)
    overall_changed_final_answer_count: int = Field(default=0, ge=0)
    overall_final_answer_hit_rate_delta: float | None = None
    overall_roi_delta: float | None = None
    overall_profit_loss_delta: float = 0.0
    overall_average_hit_probability_delta_vs_original: float | None = None
    overall_harm_count_vs_original: int = Field(default=0, ge=0)
    overall_final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    overall_profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    rolling_failed_fold_count: int = Field(default=0, ge=0)
    rolling_failed_fold_reason_counts: dict[str, int] = Field(default_factory=dict)
    checks: list[ShortOddsAdapterActivationScopeSupplementalCheck] = Field(
        default_factory=list
    )
    failed_checks: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class ShortOddsAdapterActivationScopeSupplementalReport(BaseModel):
    report_key: str
    status: ShortOddsAdapterActivationScopeSupplementalStatus
    supplemental_validated: bool
    source_base_scope_report_key: str
    source_supplemental_report_keys: list[str] = Field(default_factory=list)
    scope_competition_ids: list[str] = Field(default_factory=list)
    base_scope_key: str | None = None
    base_scope_status: str | None = None
    base_changed_final_answer_count: int = Field(default=0, ge=0)
    base_final_answer_hit_rate_delta: float | None = None
    base_roi_delta: float | None = None
    base_profit_loss_delta: float = 0.0
    base_failed_fold_count: int = Field(default=0, ge=0)
    supplemental_report_count: int = Field(ge=0)
    matched_supplemental_report_count: int = Field(ge=0)
    accepted_supplemental_scope_count: int = Field(ge=0)
    blocked_supplemental_scope_count: int = Field(ge=0)
    total_changed_final_answer_count: int = Field(ge=0)
    weighted_supplemental_final_answer_hit_rate_delta: float | None = None
    weighted_supplemental_roi_delta: float | None = None
    supplemental_profit_loss_delta: float = 0.0
    supplemental_failure_reason_counts: dict[str, int] = Field(default_factory=dict)
    checks: list[ShortOddsAdapterActivationScopeSupplementalCheck] = Field(
        default_factory=list
    )
    supplemental_items: list[ShortOddsAdapterActivationScopeSupplementalItem] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_short_odds_adapter_activation_scope_supplemental_report(
    base_scope_report: ShortOddsAdapterActivationScopeSearchReport,
    *,
    supplemental_reports: Sequence[ShortOddsAdapterActivationScopeSearchReport],
    options: ShortOddsAdapterActivationScopeSupplementalOptions | None = None,
) -> ShortOddsAdapterActivationScopeSupplementalReport:
    resolved_options = options or ShortOddsAdapterActivationScopeSupplementalOptions()
    base_scope = _selected_base_scope(base_scope_report, options=resolved_options)
    warnings = [*base_scope_report.warnings]
    warnings.extend(
        warning
        for report in supplemental_reports
        for warning in report.warnings
    )
    if base_scope is None:
        warnings.append("short_odds_scope_supplemental:no_base_scope")
        return _report(
            status="no_base_scope",
            base_scope_report=base_scope_report,
            base_scope=None,
            supplemental_reports=supplemental_reports,
            supplemental_items=[],
            checks=[],
            warnings=warnings,
            options=resolved_options,
        )
    if not supplemental_reports:
        warnings.append("short_odds_scope_supplemental:no_supplemental_reports")
        return _report(
            status="no_supplemental_reports",
            base_scope_report=base_scope_report,
            base_scope=base_scope,
            supplemental_reports=supplemental_reports,
            supplemental_items=[],
            checks=[],
            warnings=warnings,
            options=resolved_options,
        )
    supplemental_items = [
        _supplemental_item(
            report,
            scope_competition_ids=base_scope.scope_competition_ids,
            options=resolved_options,
        )
        for report in supplemental_reports
    ]
    checks = _checks(
        base_scope,
        supplemental_items=supplemental_items,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    status: ShortOddsAdapterActivationScopeSupplementalStatus = (
        "supplemental_blocked" if failed_checks else "supplemental_validated"
    )
    return _report(
        status=status,
        base_scope_report=base_scope_report,
        base_scope=base_scope,
        supplemental_reports=supplemental_reports,
        supplemental_items=supplemental_items,
        checks=checks,
        warnings=warnings,
        options=resolved_options,
    )


def load_short_odds_adapter_activation_scope_supplemental_report(
    path: Path | str,
) -> ShortOddsAdapterActivationScopeSupplementalReport:
    return ShortOddsAdapterActivationScopeSupplementalReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_short_odds_adapter_activation_scope_supplemental_report(
        load_short_odds_adapter_activation_scope_search_report(args.base_scope_report),
        supplemental_reports=[
            load_short_odds_adapter_activation_scope_search_report(path)
            for path in args.supplemental_scope_report
        ],
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
    if (
        args.require_supplemental_validated
        and not report.supplemental_validated
        and not args.no_fail_process
    ):
        raise SystemExit(1)


def _selected_base_scope(
    report: ShortOddsAdapterActivationScopeSearchReport,
    *,
    options: ShortOddsAdapterActivationScopeSupplementalOptions,
) -> ShortOddsAdapterActivationScopeCandidate | None:
    scope_competition_ids = _scope_competition_ids(options.scope_competition_ids)
    if scope_competition_ids:
        return _matching_scope(report, scope_competition_ids)
    if report.best_scope is not None and report.best_scope.status == "accepted":
        return report.best_scope
    for scope in report.scopes:
        if scope.status == "accepted":
            return scope
    return None


def _supplemental_item(
    report: ShortOddsAdapterActivationScopeSearchReport,
    *,
    scope_competition_ids: Sequence[str],
    options: ShortOddsAdapterActivationScopeSupplementalOptions,
) -> ShortOddsAdapterActivationScopeSupplementalItem:
    matched_scope = _matching_scope(report, scope_competition_ids)
    if matched_scope is None:
        checks = [
            ShortOddsAdapterActivationScopeSupplementalCheck(
                name="supplemental_scope_present",
                status="failed",
                actual=False,
                threshold=True,
                detail="supplemental scope report must contain the selected scope",
            )
        ]
        return ShortOddsAdapterActivationScopeSupplementalItem(
            source_report_key=report.report_key,
            matched=False,
            scope_competition_ids=list(scope_competition_ids),
            checks=checks,
            failed_checks=[check.name for check in checks],
            summary_json={
                "source_report_key": report.report_key,
                "matched": False,
                "failed_checks": [check.name for check in checks],
            },
        )
    checks = _supplemental_item_checks(matched_scope, options=options)
    failed_checks = [check.name for check in checks if check.status == "failed"]
    return ShortOddsAdapterActivationScopeSupplementalItem(
        source_report_key=report.report_key,
        matched=True,
        status=matched_scope.status,
        scope_key=matched_scope.scope_key,
        scope_competition_ids=list(matched_scope.scope_competition_ids),
        overall_final_answer_count=matched_scope.overall_final_answer_count,
        overall_changed_final_answer_count=(
            matched_scope.overall_changed_final_answer_count
        ),
        overall_final_answer_hit_rate_delta=(
            matched_scope.overall_final_answer_hit_rate_delta
        ),
        overall_roi_delta=matched_scope.overall_roi_delta,
        overall_profit_loss_delta=matched_scope.overall_profit_loss_delta,
        overall_average_hit_probability_delta_vs_original=(
            matched_scope.overall_average_hit_probability_delta_vs_original
        ),
        overall_harm_count_vs_original=matched_scope.overall_harm_count_vs_original,
        overall_final_hit_harm_count_vs_original=(
            matched_scope.overall_final_hit_harm_count_vs_original
        ),
        overall_profit_loss_harm_count_vs_original=(
            matched_scope.overall_profit_loss_harm_count_vs_original
        ),
        rolling_failed_fold_count=matched_scope.rolling_failed_fold_count,
        rolling_failed_fold_reason_counts=dict(
            matched_scope.rolling_failed_fold_reason_counts
        ),
        checks=checks,
        failed_checks=failed_checks,
        summary_json={
            "source_report_key": report.report_key,
            "matched": True,
            "status": matched_scope.status,
            "scope_key": matched_scope.scope_key,
            "scope_competition_ids": list(matched_scope.scope_competition_ids),
            "overall_changed_final_answer_count": (
                matched_scope.overall_changed_final_answer_count
            ),
            "overall_final_answer_hit_rate_delta": (
                matched_scope.overall_final_answer_hit_rate_delta
            ),
            "overall_roi_delta": matched_scope.overall_roi_delta,
            "overall_profit_loss_delta": matched_scope.overall_profit_loss_delta,
            "rolling_failed_fold_count": matched_scope.rolling_failed_fold_count,
            "failed_checks": failed_checks,
        },
    )


def _matching_scope(
    report: ShortOddsAdapterActivationScopeSearchReport,
    scope_competition_ids: Sequence[str],
) -> ShortOddsAdapterActivationScopeCandidate | None:
    expected = tuple(sorted(scope_competition_ids))
    candidates = [
        scope for scope in [report.best_scope, *report.scopes] if scope is not None
    ]
    for scope in candidates:
        if tuple(sorted(scope.scope_competition_ids)) == expected:
            return scope
    return None


def _supplemental_item_checks(
    scope: ShortOddsAdapterActivationScopeCandidate,
    *,
    options: ShortOddsAdapterActivationScopeSupplementalOptions,
) -> list[ShortOddsAdapterActivationScopeSupplementalCheck]:
    checks = [
        _status_check(
            name="supplemental_scope_accepted",
            actual=scope.status,
            expected="accepted",
            enabled=options.require_supplemental_accepted,
            detail="supplemental scope should pass rolling admission",
        ),
        _minimum_check(
            name="supplemental_changed_final_answer_count",
            actual=scope.overall_changed_final_answer_count,
            threshold=options.min_supplemental_changed_final_answer_count,
            detail="supplemental scope should activate enough final answers",
        ),
        _optional_minimum_check(
            name="supplemental_final_answer_hit_rate_delta",
            actual=scope.overall_final_answer_hit_rate_delta,
            threshold=options.min_supplemental_final_answer_hit_rate_delta,
            detail="supplemental final-answer hit rate should not regress",
        ),
        _optional_minimum_check(
            name="supplemental_roi_delta",
            actual=scope.overall_roi_delta,
            threshold=options.min_supplemental_roi_delta,
            detail="supplemental ROI should not regress",
        ),
        _minimum_check(
            name="supplemental_profit_loss_delta",
            actual=scope.overall_profit_loss_delta,
            threshold=options.min_supplemental_profit_loss_delta,
            detail="supplemental profit/loss should not regress",
        ),
        _maximum_check(
            name="supplemental_failed_fold_count",
            actual=scope.rolling_failed_fold_count,
            threshold=options.max_supplemental_failed_fold_count,
            detail="supplemental rolling folds should not fail",
        ),
        _maximum_check(
            name="supplemental_harm_count_vs_original",
            actual=scope.overall_harm_count_vs_original,
            threshold=options.max_supplemental_harm_count_vs_original,
            detail="supplemental scope should not harm original final answers",
        ),
    ]
    return checks


def _checks(
    base_scope: ShortOddsAdapterActivationScopeCandidate,
    *,
    supplemental_items: Sequence[ShortOddsAdapterActivationScopeSupplementalItem],
    options: ShortOddsAdapterActivationScopeSupplementalOptions,
) -> list[ShortOddsAdapterActivationScopeSupplementalCheck]:
    matched_items = [item for item in supplemental_items if item.matched]
    accepted_items = [item for item in matched_items if item.status == "accepted"]
    failed_item_checks = [
        check.name
        for item in supplemental_items
        for check in item.checks
        if check.status == "failed"
    ]
    return [
        _status_check(
            name="base_scope_accepted",
            actual=base_scope.status,
            expected="accepted",
            enabled=True,
            detail="base scope must be an accepted discovery scope",
        ),
        _minimum_check(
            name="supplemental_report_count",
            actual=len(supplemental_items),
            threshold=options.min_supplemental_report_count,
            detail="supplemental validation should include enough reports",
        ),
        _minimum_check(
            name="matched_supplemental_report_count",
            actual=len(matched_items),
            threshold=options.min_supplemental_report_count,
            detail="selected scope must be present in supplemental reports",
        ),
        _minimum_check(
            name="accepted_supplemental_scope_count",
            actual=len(accepted_items),
            threshold=(
                options.min_supplemental_report_count
                if options.require_supplemental_accepted
                else 0
            ),
            detail="supplemental reports should accept the selected scope",
        ),
        _maximum_check(
            name="supplemental_failed_check_count",
            actual=len(failed_item_checks),
            threshold=0,
            detail="supplemental scope item checks should pass",
        ),
        _minimum_check(
            name="total_changed_final_answer_count",
            actual=(
                base_scope.overall_changed_final_answer_count
                + sum(
                    item.overall_changed_final_answer_count
                    for item in supplemental_items
                )
            ),
            threshold=options.min_total_changed_final_answer_count,
            detail="base plus supplemental scopes should affect enough final answers",
        ),
    ]


def _report(
    *,
    status: ShortOddsAdapterActivationScopeSupplementalStatus,
    base_scope_report: ShortOddsAdapterActivationScopeSearchReport,
    base_scope: ShortOddsAdapterActivationScopeCandidate | None,
    supplemental_reports: Sequence[ShortOddsAdapterActivationScopeSearchReport],
    supplemental_items: Sequence[ShortOddsAdapterActivationScopeSupplementalItem],
    checks: Sequence[ShortOddsAdapterActivationScopeSupplementalCheck],
    warnings: Sequence[str],
    options: ShortOddsAdapterActivationScopeSupplementalOptions,
) -> ShortOddsAdapterActivationScopeSupplementalReport:
    matched_items = [item for item in supplemental_items if item.matched]
    accepted_items = [item for item in matched_items if item.status == "accepted"]
    blocked_items = [
        item
        for item in supplemental_items
        if not item.matched or item.failed_checks or item.status != "accepted"
    ]
    scope_competition_ids = (
        list(base_scope.scope_competition_ids) if base_scope is not None else []
    )
    total_changed = (
        (base_scope.overall_changed_final_answer_count if base_scope is not None else 0)
        + sum(item.overall_changed_final_answer_count for item in supplemental_items)
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "short_odds_adapter_activation_scope_supplemental_v3_1"
        ),
        "status": status,
        "supplemental_validated": status == "supplemental_validated",
        "source_base_scope_report_key": base_scope_report.report_key,
        "source_supplemental_report_keys": [
            report.report_key for report in supplemental_reports
        ],
        "scope_competition_ids": scope_competition_ids,
        "base_scope_key": base_scope.scope_key if base_scope is not None else None,
        "supplemental_report_count": len(supplemental_reports),
        "matched_supplemental_report_count": len(matched_items),
        "accepted_supplemental_scope_count": len(accepted_items),
        "blocked_supplemental_scope_count": len(blocked_items),
        "total_changed_final_answer_count": total_changed,
        "weighted_supplemental_final_answer_hit_rate_delta": (
            _weighted_delta(matched_items, "hit_rate")
        ),
        "weighted_supplemental_roi_delta": _weighted_delta(matched_items, "roi"),
        "supplemental_profit_loss_delta": sum(
            item.overall_profit_loss_delta for item in supplemental_items
        ),
        "supplemental_failure_reason_counts": _failure_reason_counts(
            supplemental_items
        ),
        "failed_checks": [check.name for check in checks if check.status == "failed"],
        "options": options.model_dump(mode="json"),
        "warnings": list(warnings),
    }
    report_key = _digest_key(
        "short_odds_adapter_activation_scope_supplemental",
        {
            **summary,
            "checks": [check.model_dump(mode="json") for check in checks],
            "supplemental_items": [
                item.model_dump(mode="json") for item in supplemental_items
            ],
        },
    )
    return ShortOddsAdapterActivationScopeSupplementalReport(
        report_key=report_key,
        status=status,
        supplemental_validated=status == "supplemental_validated",
        source_base_scope_report_key=base_scope_report.report_key,
        source_supplemental_report_keys=[
            report.report_key for report in supplemental_reports
        ],
        scope_competition_ids=scope_competition_ids,
        base_scope_key=base_scope.scope_key if base_scope is not None else None,
        base_scope_status=base_scope.status if base_scope is not None else None,
        base_changed_final_answer_count=(
            base_scope.overall_changed_final_answer_count
            if base_scope is not None
            else 0
        ),
        base_final_answer_hit_rate_delta=(
            base_scope.overall_final_answer_hit_rate_delta
            if base_scope is not None
            else None
        ),
        base_roi_delta=base_scope.overall_roi_delta if base_scope is not None else None,
        base_profit_loss_delta=(
            base_scope.overall_profit_loss_delta if base_scope is not None else 0.0
        ),
        base_failed_fold_count=(
            base_scope.rolling_failed_fold_count if base_scope is not None else 0
        ),
        supplemental_report_count=len(supplemental_reports),
        matched_supplemental_report_count=len(matched_items),
        accepted_supplemental_scope_count=len(accepted_items),
        blocked_supplemental_scope_count=len(blocked_items),
        total_changed_final_answer_count=total_changed,
        weighted_supplemental_final_answer_hit_rate_delta=_weighted_delta(
            matched_items,
            "hit_rate",
        ),
        weighted_supplemental_roi_delta=_weighted_delta(matched_items, "roi"),
        supplemental_profit_loss_delta=sum(
            item.overall_profit_loss_delta for item in supplemental_items
        ),
        supplemental_failure_reason_counts=_failure_reason_counts(supplemental_items),
        checks=list(checks),
        supplemental_items=list(supplemental_items),
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _scope_competition_ids(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(value for value in values if value))


def _weighted_delta(
    items: Sequence[ShortOddsAdapterActivationScopeSupplementalItem],
    metric: Literal["hit_rate", "roi"],
) -> float | None:
    numerator = 0.0
    denominator = 0
    for item in items:
        value = (
            item.overall_final_answer_hit_rate_delta
            if metric == "hit_rate"
            else item.overall_roi_delta
        )
        if value is None:
            continue
        numerator += value * item.overall_final_answer_count
        denominator += item.overall_final_answer_count
    if denominator <= 0:
        return None
    return numerator / denominator


def _failure_reason_counts(
    items: Sequence[ShortOddsAdapterActivationScopeSupplementalItem],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        counts.update(item.failed_checks)
        counts.update(item.rolling_failed_fold_reason_counts)
    return {
        key: value
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    }


def _status_check(
    *,
    name: str,
    actual: str | None,
    expected: str,
    enabled: bool,
    detail: str,
) -> ShortOddsAdapterActivationScopeSupplementalCheck:
    if not enabled:
        return ShortOddsAdapterActivationScopeSupplementalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold="not_required",
            detail=detail,
        )
    return ShortOddsAdapterActivationScopeSupplementalCheck(
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
) -> ShortOddsAdapterActivationScopeSupplementalCheck:
    if actual is None:
        return ShortOddsAdapterActivationScopeSupplementalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return ShortOddsAdapterActivationScopeSupplementalCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> ShortOddsAdapterActivationScopeSupplementalCheck:
    return _minimum_check(
        name=name,
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
) -> ShortOddsAdapterActivationScopeSupplementalCheck:
    if actual is None:
        return ShortOddsAdapterActivationScopeSupplementalCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return ShortOddsAdapterActivationScopeSupplementalCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _digest_key(prefix: str, payload: Mapping[str, object]) -> str:
    body = dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Validate accepted short-odds activation scopes against supplemental "
            "scope-search reports."
        )
    )
    parser.add_argument("--base-scope-report", type=Path, required=True)
    parser.add_argument(
        "--supplemental-scope-report",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--scope-competition-ids", default="")
    parser.add_argument("--min-supplemental-report-count", type=int, default=1)
    parser.add_argument("--min-supplemental-changed-final-answer-count", type=int, default=2)
    parser.add_argument("--min-total-changed-final-answer-count", type=int, default=4)
    parser.add_argument(
        "--min-supplemental-final-answer-hit-rate-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-supplemental-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-supplemental-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-supplemental-failed-fold-count", type=int, default=0)
    parser.add_argument("--max-supplemental-harm-count-vs-original", type=int, default=0)
    parser.add_argument("--allow-supplemental-shadow-only", action="store_true")
    parser.add_argument("--require-supplemental-validated", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> ShortOddsAdapterActivationScopeSupplementalOptions:
    return ShortOddsAdapterActivationScopeSupplementalOptions(
        scope_competition_ids=tuple(_csv(args.scope_competition_ids)),
        min_supplemental_report_count=args.min_supplemental_report_count,
        min_supplemental_changed_final_answer_count=(
            args.min_supplemental_changed_final_answer_count
        ),
        min_total_changed_final_answer_count=args.min_total_changed_final_answer_count,
        min_supplemental_final_answer_hit_rate_delta=(
            args.min_supplemental_final_answer_hit_rate_delta
        ),
        min_supplemental_roi_delta=args.min_supplemental_roi_delta,
        min_supplemental_profit_loss_delta=args.min_supplemental_profit_loss_delta,
        max_supplemental_failed_fold_count=args.max_supplemental_failed_fold_count,
        max_supplemental_harm_count_vs_original=(
            args.max_supplemental_harm_count_vs_original
        ),
        require_supplemental_accepted=not args.allow_supplemental_shadow_only,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
