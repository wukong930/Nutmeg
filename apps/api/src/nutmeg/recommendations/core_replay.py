from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.effective_chain import (
    RecommendationEffectiveChainNode,
    RecommendationEffectiveChainReport,
    build_effective_recommendation_chain,
    successor_source_recommendation_run_id_from_explanation,
)
from nutmeg.recommendations.evaluation import (
    PostgresRecommendationEvaluationRepository,
    RecommendationRunEvaluation,
    RecommendationRunForEvaluation,
    RecommendationStrategyMetrics,
    evaluate_recommendation_run,
    summarize_recommendation_strategy_evaluations,
)
from nutmeg.recommendations.lifecycle_replay import (
    PersistedRecommendationLifecycleReplayQueryOptions,
    PersistedRecommendationLifecycleReplayResult,
    PersistedRecommendationRunSnapshot,
    PostgresPersistedRecommendationLifecycleReplayRepository,
    build_persisted_recommendation_lifecycle_replay,
)
from nutmeg.recommendations.models import RecommendationMode
from nutmeg.recommendations.validity import (
    RecommendationValidityEventNode,
    RecommendationValidityRunNode,
    RecommendationValidityWindowReport,
    build_recommendation_validity_window_report,
)

type RecommendationCoreReplayCheckStatus = Literal["pass", "warn", "fail"]


class RecommendationCoreReplayDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation replay and result rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Compatibility hook for repositories that expose writes."""


class RecommendationCoreReplaySnapshotRepository(Protocol):
    def list_snapshots(
        self,
        *,
        options: PersistedRecommendationLifecycleReplayQueryOptions,
    ) -> list[PersistedRecommendationRunSnapshot]:
        """List persisted recommendation snapshots for the replay window."""


class RecommendationCoreReplayResultRepository(Protocol):
    def list_results_for_fixture_ids(
        self,
        fixture_ids: Sequence[str],
    ) -> list[Mapping[str, object]]:
        """List final results for fixtures involved in the replay."""


class RecommendationCoreReplayOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=200, ge=1, le=2_000)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)


class RecommendationCoreReplayCheck(BaseModel):
    code: str
    status: RecommendationCoreReplayCheckStatus
    message: str
    fixture_ids: list[str] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationCoreReplayReport(BaseModel):
    report_key: str
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: str | None = None
    replay: PersistedRecommendationLifecycleReplayResult
    evaluations: list[RecommendationRunEvaluation] = Field(default_factory=list)
    strategy_metrics: list[RecommendationStrategyMetrics] = Field(default_factory=list)
    checks: list[RecommendationCoreReplayCheck] = Field(default_factory=list)
    result_fixture_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class RecommendationCoreReplayRunResult(BaseModel):
    report: RecommendationCoreReplayReport
    warnings: list[str] = Field(default_factory=list)


def run_recommendation_core_replay(
    database: RecommendationCoreReplayDatabaseExecutor,
    *,
    options: RecommendationCoreReplayOptions,
    replay_repository: RecommendationCoreReplaySnapshotRepository | None = None,
    result_repository: RecommendationCoreReplayResultRepository | None = None,
) -> RecommendationCoreReplayRunResult:
    replay_reader = replay_repository or PostgresPersistedRecommendationLifecycleReplayRepository(
        database
    )
    snapshots = replay_reader.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=options.normalized_window_start_utc,
            window_end_utc=options.normalized_window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            limit=options.limit,
        )
    )
    fixture_ids = _result_fixture_ids(snapshots)
    result_reader = result_repository or PostgresRecommendationEvaluationRepository(database)
    result_rows = result_reader.list_results_for_fixture_ids(fixture_ids)
    report = build_recommendation_core_replay_report(
        snapshots,
        result_rows=result_rows,
        options=options,
    )
    return RecommendationCoreReplayRunResult(
        report=report,
        warnings=_run_warnings(
            snapshots=snapshots,
            fixture_ids=fixture_ids,
            result_rows=result_rows,
        ),
    )


def build_recommendation_core_replay_report(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    *,
    result_rows: Sequence[Mapping[str, object]],
    options: RecommendationCoreReplayOptions,
) -> RecommendationCoreReplayReport:
    ordered_snapshots = sorted(
        snapshots,
        key=lambda snapshot: (
            _aware_utc(snapshot.as_of_time_utc),
            snapshot.recommendation_run_id,
        ),
    )
    replay = build_persisted_recommendation_lifecycle_replay(ordered_snapshots)
    evaluations = [
        evaluate_recommendation_run(
            _run_for_evaluation(snapshot),
            result_rows=result_rows,
            evaluation_time_utc=options.normalized_window_end_utc,
        )
        for snapshot in ordered_snapshots
    ]
    effective_chain = _effective_chain(ordered_snapshots)
    validity_report = _validity_report(
        ordered_snapshots,
        as_of_time_utc=options.normalized_window_end_utc,
    )
    effective_leaf_run_ids = set(effective_chain.effective_leaf_recommendation_run_ids)
    effective_evaluations = [
        evaluation
        for evaluation in evaluations
        if evaluation.recommendation_run_id in effective_leaf_run_ids
    ]
    result_fixture_count = len(_result_fixture_ids_from_rows(result_rows))
    checks = _core_replay_checks(
        ordered_snapshots,
        replay=replay,
        evaluations=effective_evaluations,
        result_rows=result_rows,
    )
    summary = _core_replay_summary(
        replay,
        snapshots=ordered_snapshots,
        evaluations=effective_evaluations,
        all_evaluation_count=len(evaluations),
        effective_chain=effective_chain,
        validity_report=validity_report,
        checks=checks,
        result_fixture_count=result_fixture_count,
    )
    return RecommendationCoreReplayReport(
        report_key=_report_key(options, summary=summary),
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        replay=replay,
        evaluations=evaluations,
        strategy_metrics=summarize_recommendation_strategy_evaluations(
            effective_evaluations
        ),
        checks=checks,
        result_fixture_count=result_fixture_count,
        summary_json=summary,
    )


def _run_for_evaluation(
    snapshot: PersistedRecommendationRunSnapshot,
) -> RecommendationRunForEvaluation:
    parlay_evaluation_json = dict(snapshot.parlay_evaluation_json)
    return RecommendationRunForEvaluation(
        recommendation_run_id=snapshot.recommendation_run_id,
        run_key=snapshot.run_key,
        strategy=snapshot.strategy,
        pass_type=snapshot.pass_type,
        mode=snapshot.mode,
        recommendation_status=snapshot.status,
        unit_stake=snapshot.unit_stake,
        total_stake=_optional_float(parlay_evaluation_json.get("total_stake"))
        or snapshot.unit_stake,
        selected_fixture_ids=_selected_fixture_ids(snapshot),
        locked_fixture_ids=_active_locked_fixture_ids(snapshot),
        parlay_evaluation_json=parlay_evaluation_json,
        explanation_json=dict(snapshot.explanation_json),
        expected_hit_probability_at_recommendation=_optional_float(
            parlay_evaluation_json.get("hit_probability")
        ),
        expected_value_at_recommendation=_optional_float(
            parlay_evaluation_json.get("expected_value")
        ),
        expected_roi_at_recommendation=_optional_float(parlay_evaluation_json.get("roi")),
        created_at=snapshot.created_at,
    )


def _core_replay_checks(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    *,
    replay: PersistedRecommendationLifecycleReplayResult,
    evaluations: Sequence[RecommendationRunEvaluation],
    result_rows: Sequence[Mapping[str, object]],
) -> list[RecommendationCoreReplayCheck]:
    return [
        _snapshot_availability_check(snapshots),
        _candidate_pool_check(snapshots),
        _final_selection_check(replay),
        _locked_preservation_check(replay),
        _result_coverage_check(replay, result_rows=result_rows),
        _post_match_evaluation_check(evaluations),
    ]


def _snapshot_availability_check(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> RecommendationCoreReplayCheck:
    if snapshots:
        return RecommendationCoreReplayCheck(
            code="recommendation_runs_available",
            status="pass",
            message=f"{len(snapshots)} persisted recommendation run(s) loaded.",
        )
    return RecommendationCoreReplayCheck(
        code="recommendation_runs_available",
        status="fail",
        message="No persisted recommendation runs were available for this replay window.",
    )


def _candidate_pool_check(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> RecommendationCoreReplayCheck:
    if not snapshots:
        return RecommendationCoreReplayCheck(
            code="candidate_pool_snapshots_available",
            status="fail",
            message="No recommendation runs were available, so candidate pool coverage is zero.",
        )
    missing_run_keys = [
        snapshot.run_key
        for snapshot in snapshots
        if not snapshot.candidate_pool_candidates
    ]
    if not missing_run_keys:
        return RecommendationCoreReplayCheck(
            code="candidate_pool_snapshots_available",
            status="pass",
            message="Every replayed recommendation run includes a persisted candidate pool.",
        )
    status: RecommendationCoreReplayCheckStatus = (
        "fail" if len(missing_run_keys) == len(snapshots) else "warn"
    )
    return RecommendationCoreReplayCheck(
        code="candidate_pool_snapshots_available",
        status=status,
        message=(
            f"{len(missing_run_keys)} replayed run(s) are missing full candidate pools."
        ),
        metadata_json={"missing_run_keys": missing_run_keys},
    )


def _final_selection_check(
    replay: PersistedRecommendationLifecycleReplayResult,
) -> RecommendationCoreReplayCheck:
    final_stage = replay.final_stage
    if final_stage is not None and final_stage.status == "selected":
        return RecommendationCoreReplayCheck(
            code="final_recommendation_selected",
            status="pass",
            message="The replay has a final selected recommendation.",
            fixture_ids=final_stage.selected_fixture_ids,
        )
    return RecommendationCoreReplayCheck(
        code="final_recommendation_selected",
        status="fail",
        message="The replay did not produce a final selected recommendation.",
    )


def _locked_preservation_check(
    replay: PersistedRecommendationLifecycleReplayResult,
) -> RecommendationCoreReplayCheck:
    missing_fixture_ids = _dedupe_strings(
        fixture_id
        for stage in replay.stages
        for fixture_id in stage.missing_locked_fixture_ids
    )
    if missing_fixture_ids:
        return RecommendationCoreReplayCheck(
            code="locked_fixtures_preserved",
            status="fail",
            message="At least one locked fixture was not preserved in a later recommendation.",
            fixture_ids=missing_fixture_ids,
        )
    preserved_fixture_ids = _dedupe_strings(
        fixture_id
        for stage in replay.stages
        for fixture_id in stage.preserved_locked_fixture_ids
    )
    return RecommendationCoreReplayCheck(
        code="locked_fixtures_preserved",
        status="pass",
        message="Locked fixtures were preserved where lock constraints existed.",
        fixture_ids=preserved_fixture_ids,
    )


def _result_coverage_check(
    replay: PersistedRecommendationLifecycleReplayResult,
    *,
    result_rows: Sequence[Mapping[str, object]],
) -> RecommendationCoreReplayCheck:
    final_fixture_ids = replay.final_stage.selected_fixture_ids if replay.final_stage else []
    result_fixture_ids = set(_result_fixture_ids_from_rows(result_rows))
    missing_fixture_ids = [
        fixture_id for fixture_id in final_fixture_ids if fixture_id not in result_fixture_ids
    ]
    if not final_fixture_ids:
        return RecommendationCoreReplayCheck(
            code="post_match_result_coverage",
            status="warn",
            message="No final selected fixtures were available for result coverage checks.",
        )
    if missing_fixture_ids:
        return RecommendationCoreReplayCheck(
            code="post_match_result_coverage",
            status="warn",
            message="Some final selected fixtures do not have final results yet.",
            fixture_ids=missing_fixture_ids,
        )
    return RecommendationCoreReplayCheck(
        code="post_match_result_coverage",
        status="pass",
        message="Final selected fixtures have result rows for settlement.",
        fixture_ids=final_fixture_ids,
    )


def _post_match_evaluation_check(
    evaluations: Sequence[RecommendationRunEvaluation],
) -> RecommendationCoreReplayCheck:
    if not evaluations:
        return RecommendationCoreReplayCheck(
            code="post_match_evaluations_settled",
            status="fail",
            message="No recommendation evaluations were produced.",
        )
    unresolved = [
        evaluation.run_key
        for evaluation in evaluations
        if evaluation.evaluation_status != "settled"
    ]
    if unresolved:
        return RecommendationCoreReplayCheck(
            code="post_match_evaluations_settled",
            status="warn",
            message=f"{len(unresolved)} evaluation(s) are not fully settled.",
            metadata_json={"unsettled_run_keys": unresolved},
        )
    return RecommendationCoreReplayCheck(
        code="post_match_evaluations_settled",
        status="pass",
        message="All replayed recommendation runs settled against final results.",
    )


def _core_replay_summary(
    replay: PersistedRecommendationLifecycleReplayResult,
    *,
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    evaluations: Sequence[RecommendationRunEvaluation],
    all_evaluation_count: int,
    effective_chain: RecommendationEffectiveChainReport,
    validity_report: RecommendationValidityWindowReport,
    checks: Sequence[RecommendationCoreReplayCheck],
    result_fixture_count: int,
) -> dict[str, object]:
    replay_summary = replay.summary_json
    evaluation_counts = _evaluation_status_counts(evaluations)
    settled_evaluations = [
        evaluation for evaluation in evaluations if evaluation.evaluation_status == "settled"
    ]
    total_stake = sum(evaluation.total_stake for evaluation in settled_evaluations)
    profit_loss = sum(evaluation.profit_loss for evaluation in settled_evaluations)
    final_evaluation = _final_evaluation(replay, evaluations)
    return {
        "run_count": len(snapshots),
        "stage_count": _summary_int(replay_summary, "stage_count"),
        "selected_stage_count": _summary_int(replay_summary, "selected_stage_count"),
        "changed_stage_count": _summary_int(replay_summary, "changed_stage_count"),
        "incident_stage_count": _summary_int(replay_summary, "incident_stage_count"),
        "locked_preservation_stage_count": _summary_int(
            replay_summary,
            "locked_preservation_stage_count",
        ),
        "candidate_pool_snapshot_count": sum(
            1 for snapshot in snapshots if snapshot.candidate_pool_candidates
        ),
        "result_fixture_count": result_fixture_count,
        "evaluated_run_count": all_evaluation_count,
        "effective_evaluated_run_count": len(evaluations),
        "effective_chain_count": effective_chain.chain_count,
        "effective_chain_active_edge_count": effective_chain.active_edge_count,
        "effective_leaf_recommendation_run_ids": list(
            effective_chain.effective_leaf_recommendation_run_ids
        ),
        "superseded_source_run_count": len(
            effective_chain.superseded_source_recommendation_run_ids
        ),
        "superseded_source_recommendation_run_ids": list(
            effective_chain.superseded_source_recommendation_run_ids
        ),
        "invalidated_successor_recommendation_run_ids": list(
            effective_chain.invalidated_successor_recommendation_run_ids
        ),
        "ignored_invalidated_successor_source_recommendation_run_ids": list(
            effective_chain.ignored_invalidated_successor_source_recommendation_run_ids
        ),
        "ambiguous_successor_source_recommendation_run_ids": list(
            effective_chain.ambiguous_successor_source_recommendation_run_ids
        ),
        "validity_window_status_counts": _summary_mapping(
            validity_report.summary_json,
            "status_counts",
        ),
        "current_answer_recommendation_run_ids": list(
            validity_report.current_answer_recommendation_run_ids
        ),
        "stale_recommendation_run_ids": list(
            validity_report.stale_recommendation_run_ids
        ),
        "expired_kickoff_recommendation_run_ids": list(
            validity_report.expired_kickoff_recommendation_run_ids
        ),
        "stale_incident_recommendation_run_ids": list(
            validity_report.stale_incident_recommendation_run_ids
        ),
        "successor_recompute_required_recommendation_run_ids": list(
            validity_report.successor_recompute_required_recommendation_run_ids
        ),
        "evaluation_status_counts": evaluation_counts,
        "settled_run_count": evaluation_counts.get("settled", 0),
        "hit_count": sum(1 for evaluation in settled_evaluations if evaluation.hit is True),
        "total_stake": total_stake,
        "profit_loss": profit_loss,
        "roi": profit_loss / total_stake if total_stake > 0 else 0.0,
        "final_run_key": replay_summary.get("final_run_key"),
        "final_selected_fixture_ids": replay_summary.get("final_selected_fixture_ids", []),
        "final_evaluation_status": (
            final_evaluation.evaluation_status if final_evaluation is not None else None
        ),
        "final_hit": final_evaluation.hit if final_evaluation is not None else None,
        "check_fail_count": sum(1 for check in checks if check.status == "fail"),
        "check_warn_count": sum(1 for check in checks if check.status == "warn"),
        "core_flow_ready": all(check.status == "pass" for check in checks),
        "calculation_basis": "effective_leaf_recommendation_core_replay_v3_1",
    }


def _final_evaluation(
    replay: PersistedRecommendationLifecycleReplayResult,
    evaluations: Sequence[RecommendationRunEvaluation],
) -> RecommendationRunEvaluation | None:
    if replay.final_stage is None:
        return None
    for evaluation in evaluations:
        if evaluation.recommendation_run_id == replay.final_stage.recommendation_run_id:
            return evaluation
    return None


def _evaluation_status_counts(
    evaluations: Sequence[RecommendationRunEvaluation],
) -> dict[str, int]:
    counts = {"settled": 0, "partial": 0, "unresolved": 0}
    for evaluation in evaluations:
        counts[evaluation.evaluation_status] = counts.get(evaluation.evaluation_status, 0) + 1
    return counts


def _effective_chain(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> RecommendationEffectiveChainReport:
    return build_effective_recommendation_chain(
        [
            RecommendationEffectiveChainNode(
                recommendation_run_id=snapshot.recommendation_run_id,
                run_key=snapshot.run_key,
                status=snapshot.status,
                source_recommendation_run_id=(
                    successor_source_recommendation_run_id_from_explanation(
                        snapshot.explanation_json
                    )
                ),
                as_of_time_utc=snapshot.as_of_time_utc,
            )
            for snapshot in snapshots
        ]
    )


def _validity_report(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    *,
    as_of_time_utc: datetime,
) -> RecommendationValidityWindowReport:
    return build_recommendation_validity_window_report(
        [
            RecommendationValidityRunNode(
                recommendation_run_id=snapshot.recommendation_run_id,
                run_key=snapshot.run_key,
                status=snapshot.status,
                as_of_time_utc=snapshot.as_of_time_utc,
                selected_fixture_ids=_selected_fixture_ids(snapshot),
                locked_fixture_ids=_active_locked_fixture_ids(snapshot),
                fixture_kickoff_times_utc=_fixture_kickoff_times(snapshot),
                source_recommendation_run_id=(
                    successor_source_recommendation_run_id_from_explanation(
                        snapshot.explanation_json
                    )
                ),
                lifecycle_events=[
                    RecommendationValidityEventNode(
                        reason_code=event.reason_code,
                        event_time_utc=event.event_time_utc,
                        metadata_json=dict(event.metadata_json),
                    )
                    for event in snapshot.lifecycle_events
                ],
            )
            for snapshot in snapshots
        ],
        as_of_time_utc=as_of_time_utc,
    )


def _fixture_kickoff_times(
    snapshot: PersistedRecommendationRunSnapshot,
) -> dict[str, datetime]:
    kickoff_times: dict[str, datetime] = {}
    selected_fixture_ids = set(_selected_fixture_ids(snapshot))
    for candidate in [*snapshot.selected_candidates, *snapshot.candidate_pool_candidates]:
        if candidate.fixture_id not in selected_fixture_ids:
            continue
        kickoff_time = candidate.normalized_kickoff_time_utc()
        if kickoff_time is None:
            continue
        kickoff_times.setdefault(candidate.fixture_id, kickoff_time)
    return kickoff_times


def _result_fixture_ids(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> list[str]:
    fixture_ids: list[str] = []
    for snapshot in snapshots:
        fixture_ids.extend(_selected_fixture_ids(snapshot))
        fixture_ids.extend(_active_locked_fixture_ids(snapshot))
        fixture_ids.extend(candidate.fixture_id for candidate in snapshot.selected_candidates)
        fixture_ids.extend(
            _atomic_bet_fixture_ids(snapshot.parlay_evaluation_json.get("atomic_bets"))
        )
        fixture_ids.extend(_focus_answer_fixture_ids(snapshot.explanation_json))
    return _dedupe_strings(fixture_ids)


def _result_fixture_ids_from_rows(result_rows: Sequence[Mapping[str, object]]) -> list[str]:
    return _dedupe_strings(
        str(row["fixture_id"]) for row in result_rows if row.get("fixture_id") is not None
    )


def _atomic_bet_fixture_ids(value: object) -> list[str]:
    fixture_ids: list[str] = []
    for atomic_bet in _mapping_array(value):
        for leg in _mapping_array(atomic_bet.get("legs")):
            fixture_id = leg.get("fixture_id")
            if fixture_id is not None:
                fixture_ids.append(str(fixture_id))
    return fixture_ids


def _focus_answer_fixture_ids(explanation_json: Mapping[str, object]) -> list[str]:
    fixture_ids: list[str] = []
    focus_payload = explanation_json.get("focus_policy_answers")
    if not isinstance(focus_payload, Mapping):
        internal_trace = explanation_json.get("internal_trace")
        if isinstance(internal_trace, Mapping):
            focus_payload = internal_trace.get("focus_policy_answers")
    if not isinstance(focus_payload, Mapping):
        return []
    for key in ("single", "upset"):
        answer = focus_payload.get(key)
        if not isinstance(answer, Mapping):
            continue
        fixture_id = answer.get("fixture_id")
        if fixture_id is not None:
            fixture_ids.append(str(fixture_id))
    return fixture_ids


def _selected_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
    if snapshot.selected_fixture_ids:
        return _dedupe_strings(snapshot.selected_fixture_ids)
    return _dedupe_strings(candidate.fixture_id for candidate in snapshot.selected_candidates)


def _active_locked_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
    return _dedupe_strings(
        [
            *snapshot.locked_fixture_ids,
            *(
                locked_leg.fixture_id
                for locked_leg in snapshot.locked_legs
                if locked_leg.status == "locked"
            ),
        ]
    )


def _run_warnings(
    *,
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    fixture_ids: Sequence[str],
    result_rows: Sequence[Mapping[str, object]],
) -> list[str]:
    warnings: list[str] = []
    if not snapshots:
        warnings.append("no_recommendation_runs_for_core_replay_window")
    if fixture_ids and not result_rows:
        warnings.append("no_result_rows_for_replayed_recommendation_fixtures")
    return warnings


def _report_key(
    options: RecommendationCoreReplayOptions,
    *,
    summary: Mapping[str, object],
) -> str:
    payload = "|".join(
        [
            options.normalized_window_start_utc.isoformat(),
            options.normalized_window_end_utc.isoformat(),
            options.pass_type or "all_pass_types",
            options.mode or "all_modes",
            options.strategy or "all_strategies",
            str(summary.get("run_count", 0)),
            str(summary.get("final_run_key")),
            str(summary.get("settled_run_count", 0)),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"core_replay:{digest}"


def _mapping_array(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | Decimal | str):
        return int(value)
    return 0


def _summary_mapping(summary: Mapping[str, object], key: str) -> dict[str, object]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
