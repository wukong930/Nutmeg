from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.benchmark_runner import (
    PostgresRecommendationBenchmarkRunRepository,
    RecommendationBenchmarkDatabaseExecutor,
    StoredRecommendationBenchmarkRun,
)
from nutmeg.recommendations.models import RecommendationStrategy

type RecommendationBenchmarkStrategyComparisonCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type RecommendationBenchmarkStrategyComparisonStatus = Literal[
    "passed",
    "failed",
    "insufficient_history",
]
type RecommendationBenchmarkStrategyComparisonScalar = (
    bool | float | int | str | None
)

RECOMMENDATION_STRATEGY_CHOICES = (
    "accuracy_first",
    "value_first",
    "upset_protection",
    "budget_constrained",
)


class RecommendationBenchmarkStrategyComparisonRepository(Protocol):
    def list_history(
        self,
        *,
        benchmark_key: str | None = None,
        strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkRun]:
        """Read persisted benchmark runs for cross-strategy comparison."""


class RecommendationBenchmarkStrategyComparisonOptions(BaseModel):
    benchmark_key: str | None = Field(default=None, min_length=1)
    candidate_benchmark_key: str | None = Field(default=None, min_length=1)
    baseline_benchmark_key: str | None = Field(default=None, min_length=1)
    candidate_strategy: RecommendationStrategy = "value_first"
    baseline_strategy: RecommendationStrategy = "accuracy_first"
    history_limit: int = Field(default=20, ge=1, le=200)
    allow_missing_history: bool = False
    require_matrix_match: bool = True
    min_scenario_count: int = Field(default=1, ge=0)
    min_completed_ratio: float | None = Field(default=1.0, ge=0.0, le=1.0)
    max_failed_count: int | None = Field(default=0, ge=0)
    min_core_replay_ready_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    min_final_hit_sample_size: int = Field(default=0, ge=0)
    min_average_core_replay_roi_delta: float | None = 0.0
    min_final_hit_rate_delta: float | None = None


class RecommendationBenchmarkStrategyComparisonCheck(BaseModel):
    name: str
    status: RecommendationBenchmarkStrategyComparisonCheckStatus
    candidate_value: RecommendationBenchmarkStrategyComparisonScalar = None
    baseline_value: RecommendationBenchmarkStrategyComparisonScalar = None
    threshold: RecommendationBenchmarkStrategyComparisonScalar = None
    detail: str


class RecommendationBenchmarkStrategyComparisonResult(BaseModel):
    comparison_key: str
    status: RecommendationBenchmarkStrategyComparisonStatus
    passed: bool
    candidate_run: StoredRecommendationBenchmarkRun | None = None
    baseline_run: StoredRecommendationBenchmarkRun | None = None
    checks: list[RecommendationBenchmarkStrategyComparisonCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_benchmark_strategy_comparison(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkStrategyComparisonOptions,
    repository: RecommendationBenchmarkStrategyComparisonRepository | None = None,
) -> RecommendationBenchmarkStrategyComparisonResult:
    comparison_repository = repository or PostgresRecommendationBenchmarkRunRepository(
        database
    )
    candidate_key = options.candidate_benchmark_key or options.benchmark_key
    baseline_key = options.baseline_benchmark_key or options.benchmark_key
    candidate_history = comparison_repository.list_history(
        benchmark_key=candidate_key,
        strategy=options.candidate_strategy,
        limit=options.history_limit,
    )
    baseline_history = comparison_repository.list_history(
        benchmark_key=baseline_key,
        strategy=options.baseline_strategy,
        limit=options.history_limit,
    )
    if not candidate_history or not baseline_history:
        return _missing_history_result(
            options=options,
            candidate_history_count=len(candidate_history),
            baseline_history_count=len(baseline_history),
        )
    return build_recommendation_benchmark_strategy_comparison(
        candidate=candidate_history[0],
        baseline=baseline_history[0],
        options=options,
    )


def build_recommendation_benchmark_strategy_comparison(
    *,
    candidate: StoredRecommendationBenchmarkRun,
    baseline: StoredRecommendationBenchmarkRun,
    options: RecommendationBenchmarkStrategyComparisonOptions,
) -> RecommendationBenchmarkStrategyComparisonResult:
    checks = _comparison_checks(candidate, baseline, options=options)
    failed_checks = [check for check in checks if check.status == "failed"]
    passed = not failed_checks
    status: RecommendationBenchmarkStrategyComparisonStatus = (
        "passed" if passed else "failed"
    )
    warnings = [
        f"benchmark_strategy_comparison:failed_check:{check.name}"
        for check in failed_checks
    ]
    comparison_key = _comparison_key(
        candidate=candidate,
        baseline=baseline,
        options=options,
    )
    return RecommendationBenchmarkStrategyComparisonResult(
        comparison_key=comparison_key,
        status=status,
        passed=passed,
        candidate_run=candidate,
        baseline_run=baseline,
        checks=checks,
        warnings=warnings,
        summary_json=_comparison_summary(
            comparison_key=comparison_key,
            candidate=candidate,
            baseline=baseline,
            checks=checks,
            status=status,
            passed=passed,
            warnings=warnings,
        ),
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_benchmark_strategy_comparison(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _comparison_checks(
    candidate: StoredRecommendationBenchmarkRun,
    baseline: StoredRecommendationBenchmarkRun,
    *,
    options: RecommendationBenchmarkStrategyComparisonOptions,
) -> list[RecommendationBenchmarkStrategyComparisonCheck]:
    return [
        _check_matrix_match(
            candidate,
            baseline,
            required=options.require_matrix_match,
        ),
        _check_minimum(
            name="candidate_scenario_count",
            candidate_value=candidate.scenario_count,
            threshold=options.min_scenario_count,
            detail="candidate benchmark should cover enough scenarios",
        ),
        _check_optional_minimum(
            name="candidate_completed_ratio",
            candidate_value=_ratio(candidate.completed_count, candidate.scenario_count),
            threshold=options.min_completed_ratio,
            detail="candidate benchmark completed ratio should meet the configured floor",
        ),
        _check_optional_maximum(
            name="candidate_failed_count",
            candidate_value=candidate.failed_count,
            threshold=options.max_failed_count,
            detail="candidate failed scenarios should stay within the configured limit",
        ),
        _check_optional_minimum(
            name="candidate_core_replay_ready_ratio",
            candidate_value=_ratio(
                candidate.core_replay_ready_count,
                candidate.completed_count,
            ),
            threshold=options.min_core_replay_ready_ratio,
            detail="candidate core replay readiness should meet the configured floor",
        ),
        _check_minimum(
            name="candidate_final_hit_sample_size",
            candidate_value=candidate.final_hit_sample_size,
            threshold=options.min_final_hit_sample_size,
            detail="candidate settled final-hit sample should meet the configured minimum",
        ),
        _check_optional_minimum(
            name="average_core_replay_roi_delta",
            candidate_value=_optional_delta(
                candidate.average_core_replay_roi,
                baseline.average_core_replay_roi,
            ),
            threshold=options.min_average_core_replay_roi_delta,
            detail=(
                "candidate average core replay ROI should beat the baseline "
                "by the configured delta"
            ),
        ),
        _check_optional_minimum(
            name="final_hit_rate_delta",
            candidate_value=_optional_delta(
                _hit_rate(candidate),
                _hit_rate(baseline),
            ),
            threshold=options.min_final_hit_rate_delta,
            detail="candidate final hit rate should beat the baseline by the configured delta",
        ),
    ]


def _comparison_summary(
    *,
    comparison_key: str,
    candidate: StoredRecommendationBenchmarkRun,
    baseline: StoredRecommendationBenchmarkRun,
    checks: Sequence[RecommendationBenchmarkStrategyComparisonCheck],
    status: RecommendationBenchmarkStrategyComparisonStatus,
    passed: bool,
    warnings: Sequence[str],
) -> dict[str, object]:
    candidate_hit_rate = _hit_rate(candidate)
    baseline_hit_rate = _hit_rate(baseline)
    candidate_ready_ratio = _ratio(
        candidate.core_replay_ready_count,
        candidate.completed_count,
    )
    baseline_ready_ratio = _ratio(
        baseline.core_replay_ready_count,
        baseline.completed_count,
    )
    return {
        "comparison_key": comparison_key,
        "status": status,
        "passed": passed,
        "candidate_benchmark_run_id": candidate.recommendation_benchmark_run_id,
        "baseline_benchmark_run_id": baseline.recommendation_benchmark_run_id,
        "candidate_benchmark_key": candidate.benchmark_key,
        "baseline_benchmark_key": baseline.benchmark_key,
        "candidate_strategy": candidate.strategy,
        "baseline_strategy": baseline.strategy,
        "candidate_created_at": candidate.created_at.isoformat(),
        "baseline_created_at": baseline.created_at.isoformat(),
        "candidate_final_hit_rate": candidate_hit_rate,
        "baseline_final_hit_rate": baseline_hit_rate,
        "final_hit_rate_delta": _optional_delta(
            candidate_hit_rate,
            baseline_hit_rate,
        ),
        "candidate_average_core_replay_roi": candidate.average_core_replay_roi,
        "baseline_average_core_replay_roi": baseline.average_core_replay_roi,
        "average_core_replay_roi_delta": _optional_delta(
            candidate.average_core_replay_roi,
            baseline.average_core_replay_roi,
        ),
        "candidate_core_replay_ready_ratio": candidate_ready_ratio,
        "baseline_core_replay_ready_ratio": baseline_ready_ratio,
        "core_replay_ready_ratio_delta": _optional_delta(
            candidate_ready_ratio,
            baseline_ready_ratio,
        ),
        "matrix_match": _benchmark_matrix(candidate) == _benchmark_matrix(baseline),
        "candidate_matrix": _benchmark_matrix(candidate),
        "baseline_matrix": _benchmark_matrix(baseline),
        "failed_checks": [check.name for check in checks if check.status == "failed"],
        "warnings": list(warnings),
        "calculation_basis": "recommendation_benchmark_strategy_comparison_v3_1",
    }


def _missing_history_result(
    *,
    options: RecommendationBenchmarkStrategyComparisonOptions,
    candidate_history_count: int,
    baseline_history_count: int,
) -> RecommendationBenchmarkStrategyComparisonResult:
    warnings: list[str] = []
    if candidate_history_count <= 0:
        warnings.append("benchmark_strategy_comparison:no_candidate_history")
    if baseline_history_count <= 0:
        warnings.append("benchmark_strategy_comparison:no_baseline_history")
    status: RecommendationBenchmarkStrategyComparisonStatus = (
        "passed" if options.allow_missing_history else "insufficient_history"
    )
    comparison_key = _options_key(options)
    return RecommendationBenchmarkStrategyComparisonResult(
        comparison_key=comparison_key,
        status=status,
        passed=options.allow_missing_history,
        warnings=warnings,
        summary_json={
            "comparison_key": comparison_key,
            "status": status,
            "passed": options.allow_missing_history,
            "candidate_strategy": options.candidate_strategy,
            "baseline_strategy": options.baseline_strategy,
            "candidate_history_count": candidate_history_count,
            "baseline_history_count": baseline_history_count,
            "allow_missing_history": options.allow_missing_history,
            "warnings": warnings,
            "calculation_basis": "recommendation_benchmark_strategy_comparison_v3_1",
        },
    )


def _check_matrix_match(
    candidate: StoredRecommendationBenchmarkRun,
    baseline: StoredRecommendationBenchmarkRun,
    *,
    required: bool,
) -> RecommendationBenchmarkStrategyComparisonCheck:
    matched = _benchmark_matrix(candidate) == _benchmark_matrix(baseline)
    if not required:
        return RecommendationBenchmarkStrategyComparisonCheck(
            name="matrix_match",
            status="skipped",
            candidate_value=matched,
            baseline_value=True,
            detail="benchmark matrix compatibility check is disabled",
        )
    return RecommendationBenchmarkStrategyComparisonCheck(
        name="matrix_match",
        status="passed" if matched else "failed",
        candidate_value=matched,
        baseline_value=True,
        threshold=True,
        detail=(
            "candidate and baseline should use the same as-of windows, pass types, "
            "modes, budgets and dry-run setting"
        ),
    )


def _check_minimum(
    *,
    name: str,
    candidate_value: int,
    threshold: int,
    detail: str,
) -> RecommendationBenchmarkStrategyComparisonCheck:
    return RecommendationBenchmarkStrategyComparisonCheck(
        name=name,
        status="passed" if candidate_value >= threshold else "failed",
        candidate_value=candidate_value,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_minimum(
    *,
    name: str,
    candidate_value: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> RecommendationBenchmarkStrategyComparisonCheck:
    if threshold is None:
        return RecommendationBenchmarkStrategyComparisonCheck(
            name=name,
            status="skipped",
            candidate_value=candidate_value,
            detail=detail,
        )
    return RecommendationBenchmarkStrategyComparisonCheck(
        name=name,
        status=(
            "passed"
            if candidate_value is not None and candidate_value >= float(threshold)
            else "failed"
        ),
        candidate_value=candidate_value,
        threshold=threshold,
        detail=detail,
    )


def _check_optional_maximum(
    *,
    name: str,
    candidate_value: int,
    threshold: int | None,
    detail: str,
) -> RecommendationBenchmarkStrategyComparisonCheck:
    if threshold is None:
        return RecommendationBenchmarkStrategyComparisonCheck(
            name=name,
            status="skipped",
            candidate_value=candidate_value,
            detail=detail,
        )
    return RecommendationBenchmarkStrategyComparisonCheck(
        name=name,
        status="passed" if candidate_value <= threshold else "failed",
        candidate_value=candidate_value,
        threshold=threshold,
        detail=detail,
    )


def _benchmark_matrix(run: StoredRecommendationBenchmarkRun) -> dict[str, object]:
    return {
        "as_of_times": _list_summary_value(run.summary_json, "as_of_times"),
        "pass_types": _list_summary_value(run.summary_json, "pass_types"),
        "modes": _list_summary_value(run.summary_json, "modes"),
        "budgets": _list_summary_value(run.summary_json, "budgets"),
        "scenario_count": run.scenario_count,
        "dry_run": run.dry_run,
    }


def _list_summary_value(summary: dict[str, object], key: str) -> list[object]:
    value = summary.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _hit_rate(run: StoredRecommendationBenchmarkRun) -> float | None:
    return _ratio(run.final_hit_count, run.final_hit_sample_size)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _optional_delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def _comparison_key(
    *,
    candidate: StoredRecommendationBenchmarkRun,
    baseline: StoredRecommendationBenchmarkRun,
    options: RecommendationBenchmarkStrategyComparisonOptions,
) -> str:
    payload = "|".join(
        [
            str(candidate.recommendation_benchmark_run_id),
            str(baseline.recommendation_benchmark_run_id),
            options.candidate_strategy,
            options.baseline_strategy,
            str(options.require_matrix_match),
            str(options.min_average_core_replay_roi_delta),
            str(options.min_final_hit_rate_delta),
        ]
    )
    return f"recommendation_benchmark_strategy_comparison:{_digest(payload)}"


def _options_key(options: RecommendationBenchmarkStrategyComparisonOptions) -> str:
    payload = dumps(options.model_dump(mode="json"), sort_keys=True, default=str)
    return f"recommendation_benchmark_strategy_comparison:{_digest(payload)}"


def _digest(payload: str) -> str:
    return sha256(payload.encode("utf-8")).hexdigest()[:20]


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Compare persisted Nutmeg recommendation benchmark strategies."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--benchmark-key", default=None)
    parser.add_argument("--candidate-benchmark-key", default=None)
    parser.add_argument("--baseline-benchmark-key", default=None)
    parser.add_argument(
        "--candidate-strategy",
        choices=list(RECOMMENDATION_STRATEGY_CHOICES),
        default="value_first",
    )
    parser.add_argument(
        "--baseline-strategy",
        choices=list(RECOMMENDATION_STRATEGY_CHOICES),
        default="accuracy_first",
    )
    parser.add_argument("--history-limit", type=int, default=20)
    parser.add_argument("--allow-missing-history", action="store_true")
    parser.add_argument("--no-require-matrix-match", action="store_true")
    parser.add_argument("--min-scenario-count", type=int, default=1)
    parser.add_argument("--min-completed-ratio", type=float, default=1.0)
    parser.add_argument("--max-failed-count", type=int, default=0)
    parser.add_argument("--min-core-replay-ready-ratio", type=float, default=None)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--skip-roi-delta-check", action="store_true")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkStrategyComparisonOptions:
    return RecommendationBenchmarkStrategyComparisonOptions(
        benchmark_key=args.benchmark_key,
        candidate_benchmark_key=args.candidate_benchmark_key,
        baseline_benchmark_key=args.baseline_benchmark_key,
        candidate_strategy=_strategy(args.candidate_strategy),
        baseline_strategy=_strategy(args.baseline_strategy),
        history_limit=args.history_limit,
        allow_missing_history=args.allow_missing_history,
        require_matrix_match=not args.no_require_matrix_match,
        min_scenario_count=args.min_scenario_count,
        min_completed_ratio=args.min_completed_ratio,
        max_failed_count=args.max_failed_count,
        min_core_replay_ready_ratio=args.min_core_replay_ready_ratio,
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_average_core_replay_roi_delta=(
            None if args.skip_roi_delta_check else args.min_roi_delta
        ),
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
    )


def _strategy(value: str) -> RecommendationStrategy:
    if value not in RECOMMENDATION_STRATEGY_CHOICES:
        raise ValueError(f"unknown recommendation strategy: {value}")
    return cast(RecommendationStrategy, value)
