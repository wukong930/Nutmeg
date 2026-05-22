from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.chain_integrity import (
    PostgresRecommendationChainIntegrityRepository,
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationChainIntegrityRepository,
    RecommendationChainRunNode,
    run_recommendation_chain_integrity_check,
)
from nutmeg.recommendations.effective_chain import (
    RecommendationEffectiveChainNode,
    RecommendationEffectiveChainReport,
    build_effective_recommendation_chain,
)
from nutmeg.recommendations.models import RecommendationMode

type RecommendationSuccessorChainEvaluationCheckStatus = Literal["passed", "failed"]


class RecommendationSuccessorChainEvaluationOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=500, ge=1, le=5_000)
    min_effective_leaf_count: int = Field(default=1, ge=0)
    min_active_edge_count: int = Field(default=0, ge=0)
    max_critical_issue_count: int | None = Field(default=0, ge=0)
    max_ambiguous_successor_source_count: int | None = Field(default=0, ge=0)
    max_source_status_sync_required_count: int | None = Field(default=None, ge=0)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)


class RecommendationSuccessorChainEvaluationCheck(BaseModel):
    name: str
    status: RecommendationSuccessorChainEvaluationCheckStatus
    detail: str
    observed_value: int | float | None = None
    threshold: int | float | None = None
    recommendation_run_ids: list[int] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationSuccessorChainEvaluationResult(BaseModel):
    passed: bool
    chain_integrity: RecommendationChainIntegrityReport
    effective_chain: RecommendationEffectiveChainReport
    checks: list[RecommendationSuccessorChainEvaluationCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_successor_chain_evaluation(
    repository: RecommendationChainIntegrityRepository,
    *,
    options: RecommendationSuccessorChainEvaluationOptions,
) -> RecommendationSuccessorChainEvaluationResult:
    chain_integrity = run_recommendation_chain_integrity_check(
        repository,
        options=RecommendationChainIntegrityOptions(
            window_start_utc=options.normalized_window_start_utc,
            window_end_utc=options.normalized_window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            limit=options.limit,
        ),
    )
    return build_recommendation_successor_chain_evaluation_result(
        chain_integrity,
        options=options,
    )


def build_recommendation_successor_chain_evaluation_result(
    chain_integrity: RecommendationChainIntegrityReport,
    *,
    options: RecommendationSuccessorChainEvaluationOptions,
) -> RecommendationSuccessorChainEvaluationResult:
    effective_chain = build_effective_recommendation_chain(
        [_effective_node_from_chain_node(node) for node in chain_integrity.nodes]
    )
    checks = _successor_chain_checks(
        chain_integrity,
        effective_chain=effective_chain,
        options=options,
    )
    passed = all(check.status == "passed" for check in checks)
    warnings = _successor_chain_warnings(chain_integrity, effective_chain=effective_chain)
    return RecommendationSuccessorChainEvaluationResult(
        passed=passed,
        chain_integrity=chain_integrity,
        effective_chain=effective_chain,
        checks=checks,
        warnings=warnings,
        summary_json=_summary_json(
            chain_integrity,
            effective_chain=effective_chain,
            checks=checks,
            passed=passed,
            options=options,
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
    result = run_recommendation_successor_chain_evaluation(
        PostgresRecommendationChainIntegrityRepository(database),
        options=_options_from_args(args),
    )
    output = result.model_dump_json(indent=2)
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Evaluate Nutmeg source/successor recommendation chains.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--window-start-utc", required=True)
    parser.add_argument("--window-end-utc", required=True)
    parser.add_argument("--pass-type", default=None)
    parser.add_argument("--mode", choices=["single", "multiple"], default=None)
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default=None,
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--min-effective-leaf-count", type=int, default=1)
    parser.add_argument("--min-active-edge-count", type=int, default=0)
    parser.add_argument("--max-critical-issue-count", type=int, default=0)
    parser.add_argument("--max-ambiguous-successor-source-count", type=int, default=0)
    parser.add_argument("--max-source-status-sync-required-count", type=int, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationSuccessorChainEvaluationOptions:
    return RecommendationSuccessorChainEvaluationOptions(
        window_start_utc=_datetime(args.window_start_utc),
        window_end_utc=_datetime(args.window_end_utc),
        pass_type=args.pass_type,
        mode=args.mode,
        strategy=args.strategy,
        limit=args.limit,
        min_effective_leaf_count=args.min_effective_leaf_count,
        min_active_edge_count=args.min_active_edge_count,
        max_critical_issue_count=args.max_critical_issue_count,
        max_ambiguous_successor_source_count=(
            args.max_ambiguous_successor_source_count
        ),
        max_source_status_sync_required_count=(
            args.max_source_status_sync_required_count
        ),
    )


def _effective_node_from_chain_node(
    node: RecommendationChainRunNode,
) -> RecommendationEffectiveChainNode:
    return RecommendationEffectiveChainNode(
        recommendation_run_id=node.recommendation_run_id,
        run_key=node.run_key,
        status=node.status,
        source_recommendation_run_id=node.source_recommendation_run_id,
        as_of_time_utc=node.as_of_time_utc,
    )


def _successor_chain_checks(
    chain_integrity: RecommendationChainIntegrityReport,
    *,
    effective_chain: RecommendationEffectiveChainReport,
    options: RecommendationSuccessorChainEvaluationOptions,
) -> list[RecommendationSuccessorChainEvaluationCheck]:
    checks = [
        _minimum_check(
            name="effective_leaf_count",
            observed=len(effective_chain.effective_leaf_recommendation_run_ids),
            threshold=options.min_effective_leaf_count,
            detail="successor chains should contribute enough final effective leaf runs",
            recommendation_run_ids=effective_chain.effective_leaf_recommendation_run_ids,
        ),
        _minimum_check(
            name="active_successor_edge_count",
            observed=effective_chain.active_edge_count,
            threshold=options.min_active_edge_count,
            detail="successor evaluation should observe enough active source->successor edges",
        ),
    ]
    if options.max_critical_issue_count is not None:
        checks.append(
            _maximum_check(
                name="chain_integrity_critical_issue_count",
                observed=_summary_int(chain_integrity.summary_json, "critical_issue_count"),
                threshold=options.max_critical_issue_count,
                detail="critical chain integrity issues should stay within the configured limit",
                recommendation_run_ids=_issue_run_ids(chain_integrity, severity="critical"),
            )
        )
    if options.max_ambiguous_successor_source_count is not None:
        checks.append(
            _maximum_check(
                name="ambiguous_successor_source_count",
                observed=len(
                    effective_chain.ambiguous_successor_source_recommendation_run_ids
                ),
                threshold=options.max_ambiguous_successor_source_count,
                detail=(
                    "sources with multiple active successors should stay within "
                    "the configured limit"
                ),
                recommendation_run_ids=(
                    effective_chain.ambiguous_successor_source_recommendation_run_ids
                ),
            )
        )
    if options.max_source_status_sync_required_count is not None:
        checks.append(
            _maximum_check(
                name="source_status_sync_required_count",
                observed=_summary_int(
                    chain_integrity.summary_json,
                    "source_status_sync_required_count",
                ),
                threshold=options.max_source_status_sync_required_count,
                detail=(
                    "source runs requiring superseded status sync should stay within "
                    "the configured limit"
                ),
                recommendation_run_ids=[
                    issue.recommendation_run_id
                    for issue in chain_integrity.issues
                    if issue.code == "source_status_not_superseded"
                    and issue.recommendation_run_id is not None
                ],
            )
        )
    return checks


def _successor_chain_warnings(
    chain_integrity: RecommendationChainIntegrityReport,
    *,
    effective_chain: RecommendationEffectiveChainReport,
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(
        f"successor_chain_integrity:{issue.severity}:{issue.code}"
        for issue in chain_integrity.issues
    )
    if effective_chain.invalidated_successor_recommendation_run_ids:
        warnings.append("successor_chain_evaluation:invalidated_successors_ignored")
    if effective_chain.ambiguous_successor_source_recommendation_run_ids:
        warnings.append("successor_chain_evaluation:ambiguous_successor_sources")
    return warnings


def _summary_json(
    chain_integrity: RecommendationChainIntegrityReport,
    *,
    effective_chain: RecommendationEffectiveChainReport,
    checks: Sequence[RecommendationSuccessorChainEvaluationCheck],
    passed: bool,
    options: RecommendationSuccessorChainEvaluationOptions,
) -> dict[str, object]:
    return {
        "passed": passed,
        "window_start_utc": options.normalized_window_start_utc.isoformat(),
        "window_end_utc": options.normalized_window_end_utc.isoformat(),
        "pass_type": options.pass_type,
        "mode": options.mode,
        "strategy": options.strategy,
        "run_count": _summary_int(chain_integrity.summary_json, "run_count"),
        "active_run_count": _summary_int(
            chain_integrity.summary_json,
            "active_run_count",
        ),
        "active_edge_count": effective_chain.active_edge_count,
        "effective_chain_count": effective_chain.chain_count,
        "effective_leaf_count": len(
            effective_chain.effective_leaf_recommendation_run_ids
        ),
        "effective_leaf_recommendation_run_ids": list(
            effective_chain.effective_leaf_recommendation_run_ids
        ),
        "superseded_source_run_count": len(
            effective_chain.superseded_source_recommendation_run_ids
        ),
        "superseded_source_recommendation_run_ids": list(
            effective_chain.superseded_source_recommendation_run_ids
        ),
        "invalidated_successor_count": len(
            effective_chain.invalidated_successor_recommendation_run_ids
        ),
        "ignored_invalidated_successor_source_recommendation_run_ids": list(
            effective_chain.ignored_invalidated_successor_source_recommendation_run_ids
        ),
        "ambiguous_successor_source_count": len(
            effective_chain.ambiguous_successor_source_recommendation_run_ids
        ),
        "ambiguous_successor_source_recommendation_run_ids": list(
            effective_chain.ambiguous_successor_source_recommendation_run_ids
        ),
        "chain_integrity_ready": chain_integrity.ready,
        "chain_integrity_issue_count": _summary_int(
            chain_integrity.summary_json,
            "issue_count",
        ),
        "chain_integrity_critical_issue_count": _summary_int(
            chain_integrity.summary_json,
            "critical_issue_count",
        ),
        "source_status_sync_required_count": _summary_int(
            chain_integrity.summary_json,
            "source_status_sync_required_count",
        ),
        "failed_check_count": sum(1 for check in checks if check.status == "failed"),
        "calculation_basis": "successor_chain_evaluation_v3_1",
    }


def _minimum_check(
    *,
    name: str,
    observed: int,
    threshold: int,
    detail: str,
    recommendation_run_ids: Sequence[int] = (),
) -> RecommendationSuccessorChainEvaluationCheck:
    return RecommendationSuccessorChainEvaluationCheck(
        name=name,
        status="passed" if observed >= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
        recommendation_run_ids=list(recommendation_run_ids),
    )


def _maximum_check(
    *,
    name: str,
    observed: int,
    threshold: int,
    detail: str,
    recommendation_run_ids: Sequence[int] = (),
) -> RecommendationSuccessorChainEvaluationCheck:
    return RecommendationSuccessorChainEvaluationCheck(
        name=name,
        status="passed" if observed <= threshold else "failed",
        detail=detail,
        observed_value=observed,
        threshold=threshold,
        recommendation_run_ids=list(recommendation_run_ids),
    )


def _issue_run_ids(
    chain_integrity: RecommendationChainIntegrityReport,
    *,
    severity: str,
) -> list[int]:
    run_ids: list[int] = []
    for issue in chain_integrity.issues:
        if issue.severity != severity or issue.recommendation_run_id is None:
            continue
        if issue.recommendation_run_id not in run_ids:
            run_ids.append(issue.recommendation_run_id)
    return run_ids


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _summary_int(summary_json: dict[str, object], key: str) -> int:
    value = summary_json.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
