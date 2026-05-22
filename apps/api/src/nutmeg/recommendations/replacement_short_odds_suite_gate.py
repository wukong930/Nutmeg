from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    load_historical_candidate_marginal_audit_report,
)
from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateItem,
    HistoricalShortOddsFinalAnswerGateReport,
)

type HistoricalShortOddsSuiteGateStatus = Literal["passed", "failed"]
type HistoricalShortOddsSuiteGateCheckStatus = Literal["passed", "failed", "skipped"]


class HistoricalShortOddsSuiteGateOptions(BaseModel):
    min_final_answer_count: int = Field(default=30, ge=1)
    min_changed_final_answer_count: int = Field(default=5, ge=0)
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_harm_count_vs_original: int = Field(default=0, ge=0)
    max_final_hit_harm_count_vs_original: int | None = Field(default=None, ge=0)
    max_profit_loss_harm_count_vs_original: int | None = Field(default=None, ge=0)
    min_average_hit_probability_delta_vs_original: float = -0.02
    require_final_answer_shadow_candidate: bool = True
    max_report_changed_items: int = Field(default=80, ge=1, le=500)


class HistoricalShortOddsSuiteGateCheck(BaseModel):
    name: str
    status: HistoricalShortOddsSuiteGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalShortOddsSuiteFinalAnswer(BaseModel):
    final_answer_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    baseline_actual_hit: bool
    candidate_actual_hit: bool
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_delta: float
    baseline_hit_probability: float = Field(ge=0.0, le=1.0)
    candidate_hit_probability: float = Field(ge=0.0, le=1.0)
    hit_probability_delta: float
    stake: float = Field(ge=0.0)
    changed_by_shadow: bool
    harmed_final_hit_vs_original: bool = False
    harmed_profit_loss_vs_original: bool
    source_item_key: str | None = None
    replacement_fixture_id: str | None = None
    replacement_outcome: str | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalShortOddsSuiteGateReport(BaseModel):
    report_key: str
    status: HistoricalShortOddsSuiteGateStatus
    passed: bool
    source_audit_report_key: str
    source_final_answer_gate_report_key: str
    final_answer_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    candidate_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    baseline_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_final_answer_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_hit_rate_delta: float | None = None
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_delta: float
    baseline_roi: float | None = None
    candidate_roi: float | None = None
    roi_delta: float | None = None
    total_stake: float = Field(ge=0.0)
    harm_count_vs_original: int = Field(ge=0)
    final_hit_harm_count_vs_original: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_original: int = Field(default=0, ge=0)
    average_hit_probability_delta_vs_original: float | None = None
    production_recommendation_changed: bool = False
    checks: list[HistoricalShortOddsSuiteGateCheck] = Field(default_factory=list)
    changed_items: list[HistoricalShortOddsSuiteFinalAnswer] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _BaselineFinalAnswer(BaseModel):
    final_answer_key: str
    slice_id: str
    competition_id: str
    final_answer_scenario_key: str
    pass_type: str
    mode: str
    actual_hit: bool
    profit_loss: float
    actual_return: float
    hit_probability: float = Field(ge=0.0, le=1.0)
    roi: float
    stake: float = Field(ge=0.0)
    source_item_key: str


def build_historical_short_odds_suite_gate_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    final_answer_gate_report: HistoricalShortOddsFinalAnswerGateReport,
    *,
    options: HistoricalShortOddsSuiteGateOptions | None = None,
) -> HistoricalShortOddsSuiteGateReport:
    resolved_options = options or HistoricalShortOddsSuiteGateOptions()
    warnings = list(audit_report.warnings) + list(final_answer_gate_report.warnings)
    baseline_answers = _baseline_final_answers(audit_report, warnings=warnings)
    overrides = {
        item.final_answer_key: item for item in final_answer_gate_report.items
    }
    suite_answers = [
        _suite_answer_from_baseline(
            baseline_answer,
            override=overrides.get(baseline_answer.final_answer_key),
        )
        for baseline_answer in baseline_answers
    ]
    orphan_override_count = len(set(overrides) - {item.final_answer_key for item in suite_answers})
    if orphan_override_count:
        warnings.append(
            f"short_odds_suite_gate:orphan_override_count:{orphan_override_count}"
        )

    checks = _checks(
        suite_answers,
        final_answer_gate_report=final_answer_gate_report,
        options=resolved_options,
    )
    passed = all(check.status != "failed" for check in checks)
    status: HistoricalShortOddsSuiteGateStatus = "passed" if passed else "failed"
    changed_items = sorted(
        (item for item in suite_answers if item.changed_by_shadow),
        key=lambda item: (
            item.profit_loss_delta,
            int(item.candidate_actual_hit) - int(item.baseline_actual_hit),
            item.final_answer_key,
        ),
        reverse=True,
    )[: resolved_options.max_report_changed_items]
    summary: dict[str, object] = {
        "calculation_basis": "historical_short_odds_suite_gate_v3_1",
        "source_audit_report_key": audit_report.report_key,
        "source_final_answer_gate_report_key": final_answer_gate_report.report_key,
        "final_answer_gate_decision": final_answer_gate_report.decision,
        "production_recommendation_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, changed_items, checks)
    return HistoricalShortOddsSuiteGateReport(
        report_key=report_key,
        status=status,
        passed=passed,
        source_audit_report_key=audit_report.report_key,
        source_final_answer_gate_report_key=final_answer_gate_report.report_key,
        final_answer_count=len(suite_answers),
        changed_final_answer_count=sum(
            1 for item in suite_answers if item.changed_by_shadow
        ),
        baseline_final_answer_hit_count=sum(
            1 for item in suite_answers if item.baseline_actual_hit
        ),
        candidate_final_answer_hit_count=sum(
            1 for item in suite_answers if item.candidate_actual_hit
        ),
        final_answer_hit_delta_count=sum(
            int(item.candidate_actual_hit) - int(item.baseline_actual_hit)
            for item in suite_answers
        ),
        baseline_final_answer_hit_rate=_ratio(
            sum(1 for item in suite_answers if item.baseline_actual_hit),
            len(suite_answers),
        ),
        candidate_final_answer_hit_rate=_ratio(
            sum(1 for item in suite_answers if item.candidate_actual_hit),
            len(suite_answers),
        ),
        final_answer_hit_rate_delta=_hit_rate_delta(suite_answers),
        baseline_profit_loss=sum(item.baseline_profit_loss for item in suite_answers),
        candidate_profit_loss=sum(item.candidate_profit_loss for item in suite_answers),
        profit_loss_delta=sum(item.profit_loss_delta for item in suite_answers),
        baseline_roi=_roi(
            profit_loss=sum(item.baseline_profit_loss for item in suite_answers),
            stake=sum(item.stake for item in suite_answers),
        ),
        candidate_roi=_roi(
            profit_loss=sum(item.candidate_profit_loss for item in suite_answers),
            stake=sum(item.stake for item in suite_answers),
        ),
        roi_delta=_roi_delta(suite_answers),
        total_stake=sum(item.stake for item in suite_answers),
        harm_count_vs_original=sum(
            1 for item in suite_answers if item.harmed_profit_loss_vs_original
        ),
        final_hit_harm_count_vs_original=_final_hit_harm_count(suite_answers),
        profit_loss_harm_count_vs_original=_profit_loss_harm_count(suite_answers),
        average_hit_probability_delta_vs_original=_average(
            item.hit_probability_delta
            for item in suite_answers
            if item.changed_by_shadow
        ),
        production_recommendation_changed=False,
        checks=checks,
        changed_items=changed_items,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_short_odds_final_answer_gate_report(
    path: Path,
) -> HistoricalShortOddsFinalAnswerGateReport:
    return HistoricalShortOddsFinalAnswerGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    audit_report = load_historical_candidate_marginal_audit_report(args.audit_report)
    final_answer_gate_report = load_historical_short_odds_final_answer_gate_report(
        args.final_answer_gate_report
    )
    report = build_historical_short_odds_suite_gate_report(
        audit_report,
        final_answer_gate_report,
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


def _baseline_final_answers(
    audit_report: HistoricalCandidateMarginalAuditReport,
    *,
    warnings: list[str],
) -> list[_BaselineFinalAnswer]:
    by_key: dict[str, _BaselineFinalAnswer] = {}
    for audit_item in audit_report.items:
        final_answer_key = _final_answer_key(audit_item)
        baseline = _baseline_final_answer(audit_item, final_answer_key=final_answer_key)
        existing = by_key.get(final_answer_key)
        if existing is not None:
            if existing.model_dump(exclude={"source_item_key"}) != baseline.model_dump(
                exclude={"source_item_key"}
            ):
                warnings.append(
                    "short_odds_suite_gate:inconsistent_final_answer:"
                    f"{final_answer_key}"
                )
            continue
        by_key[final_answer_key] = baseline
    return sorted(by_key.values(), key=lambda item: item.final_answer_key)


def _baseline_final_answer(
    audit_item: HistoricalCandidateMarginalAuditItem,
    *,
    final_answer_key: str,
) -> _BaselineFinalAnswer:
    stake = _stake_from_audit_item(audit_item)
    return _BaselineFinalAnswer(
        final_answer_key=final_answer_key,
        slice_id=audit_item.slice_id,
        competition_id=audit_item.competition_id,
        final_answer_scenario_key=audit_item.final_answer_scenario_key,
        pass_type=audit_item.pass_type,
        mode=str(audit_item.mode),
        actual_hit=audit_item.final_answer_actual_hit,
        profit_loss=audit_item.original_profit_loss,
        actual_return=audit_item.original_actual_return,
        hit_probability=audit_item.original_hit_probability,
        roi=audit_item.original_roi,
        stake=stake,
        source_item_key=audit_item.item_key,
    )


def _suite_answer_from_baseline(
    baseline: _BaselineFinalAnswer,
    *,
    override: HistoricalShortOddsFinalAnswerGateItem | None,
) -> HistoricalShortOddsSuiteFinalAnswer:
    candidate_hit = baseline.actual_hit
    candidate_profit_loss = baseline.profit_loss
    candidate_hit_probability = baseline.hit_probability
    source_item_key: str | None = None
    replacement_fixture_id: str | None = None
    replacement_outcome: str | None = None
    changed = False
    if override is not None:
        candidate_hit = override.shadow_actual_hit
        candidate_profit_loss = override.shadow_profit_loss
        candidate_hit_probability = override.shadow_hit_probability
        source_item_key = override.item_key
        replacement_fixture_id = override.replacement_fixture_id
        replacement_outcome = override.replacement_outcome
        changed = True
    profit_delta = candidate_profit_loss - baseline.profit_loss
    hit_probability_delta = candidate_hit_probability - baseline.hit_probability
    final_answer_hit_delta = int(candidate_hit) - int(baseline.actual_hit)
    return HistoricalShortOddsSuiteFinalAnswer(
        final_answer_key=baseline.final_answer_key,
        slice_id=baseline.slice_id,
        competition_id=baseline.competition_id,
        final_answer_scenario_key=baseline.final_answer_scenario_key,
        pass_type=baseline.pass_type,
        mode=baseline.mode,
        baseline_actual_hit=baseline.actual_hit,
        candidate_actual_hit=candidate_hit,
        baseline_profit_loss=baseline.profit_loss,
        candidate_profit_loss=candidate_profit_loss,
        profit_loss_delta=profit_delta,
        baseline_hit_probability=baseline.hit_probability,
        candidate_hit_probability=candidate_hit_probability,
        hit_probability_delta=hit_probability_delta,
        stake=baseline.stake,
        changed_by_shadow=changed,
        harmed_final_hit_vs_original=final_answer_hit_delta < 0,
        harmed_profit_loss_vs_original=profit_delta < 0,
        source_item_key=source_item_key,
        replacement_fixture_id=replacement_fixture_id,
        replacement_outcome=replacement_outcome,
        summary_json={
            "calculation_basis": "historical_short_odds_suite_final_answer_v3_1",
            "production_recommendation_changed": False,
        },
    )


def _checks(
    items: Sequence[HistoricalShortOddsSuiteFinalAnswer],
    *,
    final_answer_gate_report: HistoricalShortOddsFinalAnswerGateReport,
    options: HistoricalShortOddsSuiteGateOptions,
) -> list[HistoricalShortOddsSuiteGateCheck]:
    checks = [
        _minimum_check(
            name="final_answer_count",
            actual=len(items),
            threshold=options.min_final_answer_count,
            detail="suite should include enough unique final answers",
        ),
        _minimum_check(
            name="changed_final_answer_count",
            actual=sum(1 for item in items if item.changed_by_shadow),
            threshold=options.min_changed_final_answer_count,
            detail="shadow candidate should affect enough final answers",
        ),
        _minimum_check(
            name="final_answer_hit_rate_delta",
            actual=_hit_rate_delta(items),
            threshold=options.min_final_answer_hit_rate_delta,
            detail="candidate final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="roi_delta",
            actual=_roi_delta(items),
            threshold=options.min_roi_delta,
            detail="candidate ROI should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=sum(item.profit_loss_delta for item in items),
            threshold=options.min_profit_loss_delta,
            detail="candidate profit/loss should not regress",
        ),
        _maximum_check(
            name="harm_count_vs_original",
            actual=_profit_loss_harm_count(items),
            threshold=options.max_harm_count_vs_original,
            detail=(
                "compatibility check: shadow candidate should not reduce "
                "historical final-answer profit/loss"
            ),
        ),
        _maximum_check(
            name="final_hit_harm_count_vs_original",
            actual=_final_hit_harm_count(items),
            threshold=_final_hit_harm_threshold(options),
            detail="shadow candidate should not turn original hits into misses",
        ),
        _maximum_check(
            name="profit_loss_harm_count_vs_original",
            actual=_profit_loss_harm_count(items),
            threshold=_profit_loss_harm_threshold(options),
            detail="shadow candidate should not reduce original final-answer profit/loss",
        ),
        _minimum_check(
            name="average_hit_probability_delta_vs_original",
            actual=_average(
                item.hit_probability_delta
                for item in items
                if item.changed_by_shadow
            ),
            threshold=options.min_average_hit_probability_delta_vs_original,
            detail="expected hit-probability tolerance should remain bounded",
        ),
    ]
    if options.require_final_answer_shadow_candidate:
        checks.append(
            HistoricalShortOddsSuiteGateCheck(
                name="final_answer_gate_decision",
                status=(
                    "passed"
                    if final_answer_gate_report.decision
                    == "final_answer_shadow_candidate"
                    else "failed"
                ),
                actual=final_answer_gate_report.decision,
                threshold="final_answer_shadow_candidate",
                detail="source final-answer gate should be a shadow candidate",
            )
        )
    return checks


def _final_hit_harm_count(items: Sequence[HistoricalShortOddsSuiteFinalAnswer]) -> int:
    return sum(1 for item in items if item.harmed_final_hit_vs_original)


def _profit_loss_harm_count(items: Sequence[HistoricalShortOddsSuiteFinalAnswer]) -> int:
    return sum(1 for item in items if item.harmed_profit_loss_vs_original)


def _final_hit_harm_threshold(options: HistoricalShortOddsSuiteGateOptions) -> int:
    return (
        options.max_final_hit_harm_count_vs_original
        if options.max_final_hit_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _profit_loss_harm_threshold(options: HistoricalShortOddsSuiteGateOptions) -> int:
    return (
        options.max_profit_loss_harm_count_vs_original
        if options.max_profit_loss_harm_count_vs_original is not None
        else options.max_harm_count_vs_original
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalShortOddsSuiteGateCheck:
    if actual is None:
        return HistoricalShortOddsSuiteGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsSuiteGateCheck(
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
) -> HistoricalShortOddsSuiteGateCheck:
    if actual is None:
        return HistoricalShortOddsSuiteGateCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalShortOddsSuiteGateCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Gate a short-odds final-answer shadow candidate over a suite."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--final-answer-gate-report", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
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
        "--no-require-final-answer-shadow-candidate",
        action="store_false",
        dest="require_final_answer_shadow_candidate",
    )
    parser.add_argument("--max-report-changed-items", type=int, default=80)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalShortOddsSuiteGateOptions:
    return HistoricalShortOddsSuiteGateOptions(
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
        require_final_answer_shadow_candidate=(
            args.require_final_answer_shadow_candidate
        ),
        max_report_changed_items=args.max_report_changed_items,
    )


def _final_answer_key(item: HistoricalCandidateMarginalAuditItem) -> str:
    return f"{item.slice_id}:{item.final_answer_scenario_key}"


def _stake_from_audit_item(item: HistoricalCandidateMarginalAuditItem) -> float:
    stake = item.original_actual_return - item.original_profit_loss
    if stake >= 0:
        return stake
    if item.original_roi != 0:
        return abs(item.original_profit_loss / item.original_roi)
    return 0.0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _hit_rate_delta(
    items: Sequence[HistoricalShortOddsSuiteFinalAnswer],
) -> float | None:
    baseline = _ratio(sum(1 for item in items if item.baseline_actual_hit), len(items))
    candidate = _ratio(sum(1 for item in items if item.candidate_actual_hit), len(items))
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _roi_delta(items: Sequence[HistoricalShortOddsSuiteFinalAnswer]) -> float | None:
    stake = sum(item.stake for item in items)
    baseline = _roi(
        profit_loss=sum(item.baseline_profit_loss for item in items),
        stake=stake,
    )
    candidate = _roi(
        profit_loss=sum(item.candidate_profit_loss for item in items),
        stake=stake,
    )
    if baseline is None or candidate is None:
        return None
    return candidate - baseline


def _roi(*, profit_loss: float, stake: float) -> float | None:
    if stake <= 0:
        return None
    return profit_loss / stake


def _average(values: Iterable[float | int | None]) -> float | None:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return None
    return sum(collected) / len(collected)


def _report_key(
    summary: dict[str, object],
    changed_items: Sequence[HistoricalShortOddsSuiteFinalAnswer],
    checks: Sequence[HistoricalShortOddsSuiteGateCheck],
) -> str:
    payload = dumps(
        {
            "summary": summary,
            "changed_items": [
                {
                    "final_answer_key": item.final_answer_key,
                    "source_item_key": item.source_item_key,
                    "replacement_fixture_id": item.replacement_fixture_id,
                    "replacement_outcome": item.replacement_outcome,
                }
                for item in changed_items
            ],
            "checks": [check.model_dump(mode="json") for check in checks],
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"historical_short_odds_suite_gate:{digest}"
