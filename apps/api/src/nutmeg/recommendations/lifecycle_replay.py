from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.incidents import (
    RecommendationProviderIncidentEventRecord,
    apply_provider_incidents_to_backtest_checkpoints,
)
from nutmeg.recommendations.lifecycle_backtest import (
    PrematchRecommendationBacktestCheckpoint,
)
from nutmeg.recommendations.models import RecommendationCandidate, RecommendationMode
from nutmeg.recommendations.policy import parse_pass_type_leg_count

type PersistedRecommendationReplayStageStatus = Literal["selected", "no_selection"]

LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY = """
SELECT
  recommendation_run_id,
  run_key,
  as_of_time_utc,
  strategy,
  pass_type,
  mode,
  status,
  unit_stake,
  max_budget,
  candidate_count,
  excluded_candidate_count,
  selected_fixture_ids_json,
  locked_fixture_ids_json,
  total_score,
  parlay_evaluation_json,
  explanation_json,
  source,
  created_at
FROM recommendation_runs
WHERE as_of_time_utc >= %(window_start_utc)s
  AND as_of_time_utc <= %(window_end_utc)s
  AND (
    %(recommendation_run_id)s::bigint IS NULL
    OR recommendation_run_id = %(recommendation_run_id)s::bigint
  )
  AND (%(pass_type)s::text IS NULL OR pass_type = %(pass_type)s::text)
  AND (%(mode)s::text IS NULL OR mode = %(mode)s::text)
  AND (%(strategy)s::text IS NULL OR strategy = %(strategy)s::text)
ORDER BY as_of_time_utc ASC, recommendation_run_id ASC
LIMIT %(limit)s
"""

LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY = """
SELECT
  recommendation_candidate_id,
  recommendation_run_id,
  fixture_id,
  market_type,
  line,
  side,
  outcome,
  probability,
  decimal_odds,
  market_probability,
  model_edge,
  data_quality_score,
  model_confidence_score,
  calibration_score,
  upset_protection_score,
  odds_stability_score,
  volatility_penalty,
  model_version,
  prediction_snapshot_id,
  prediction_time_utc,
  kickoff_time_utc,
  recommendation_score,
  selected,
  locked,
  metadata_json,
  created_at
FROM recommendation_candidates
WHERE recommendation_run_id = ANY(%(recommendation_run_ids)s::bigint[])
  AND selected IS TRUE
ORDER BY recommendation_run_id ASC, recommendation_candidate_id ASC
"""

LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY = """
SELECT
  recommendation_lifecycle_event_id,
  recommendation_run_id,
  recommendation_key,
  from_status,
  to_status,
  reason_code,
  event_time_utc,
  metadata_json,
  created_at
FROM recommendation_lifecycle_events
WHERE recommendation_run_id = ANY(%(recommendation_run_ids)s::bigint[])
ORDER BY recommendation_run_id ASC, event_time_utc ASC, recommendation_lifecycle_event_id ASC
"""

LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY = """
SELECT
  recommendation_locked_leg_id,
  recommendation_run_id,
  fixture_id,
  market_type,
  outcome,
  locked_at_utc,
  status,
  metadata_json,
  created_at
FROM recommendation_locked_legs
WHERE recommendation_run_id = ANY(%(recommendation_run_ids)s::bigint[])
ORDER BY recommendation_run_id ASC, locked_at_utc ASC, recommendation_locked_leg_id ASC
"""

LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY = """
SELECT
  recommendation_candidate_pool_snapshot_id,
  recommendation_run_id,
  run_key,
  as_of_time_utc,
  strategy,
  pass_type,
  mode,
  candidate_count,
  selected_candidate_count,
  excluded_candidate_count,
  candidate_query_json,
  source,
  created_at
FROM recommendation_candidate_pool_snapshots
WHERE recommendation_run_id = ANY(%(recommendation_run_ids)s::bigint[])
ORDER BY recommendation_run_id ASC, recommendation_candidate_pool_snapshot_id ASC
"""

LIST_PERSISTED_RECOMMENDATION_POOL_ITEMS_FOR_REPLAY_QUERY = """
SELECT
  recommendation_candidate_pool_item_id,
  recommendation_candidate_pool_snapshot_id,
  fixture_id,
  market_type,
  line,
  side,
  outcome,
  probability,
  decimal_odds,
  market_probability,
  model_edge,
  data_quality_score,
  model_confidence_score,
  calibration_score,
  upset_protection_score,
  odds_stability_score,
  volatility_penalty,
  model_version,
  prediction_snapshot_id,
  prediction_time_utc,
  kickoff_time_utc,
  selected,
  locked,
  metadata_json,
  created_at
FROM recommendation_candidate_pool_items
WHERE recommendation_candidate_pool_snapshot_id =
  ANY(%(recommendation_candidate_pool_snapshot_ids)s::bigint[])
ORDER BY recommendation_candidate_pool_snapshot_id ASC,
  recommendation_candidate_pool_item_id ASC
"""


class PersistedRecommendationReplayDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read persisted recommendation lifecycle replay rows."""


class PersistedRecommendationLifecycleReplayQueryOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    recommendation_run_id: int | None = Field(default=None, gt=0)
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


class PersistedRecommendationLockedLegSnapshot(BaseModel):
    recommendation_locked_leg_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    fixture_id: str
    market_type: str
    outcome: str
    locked_at_utc: datetime
    status: str
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None


class PersistedRecommendationLifecycleEventSnapshot(BaseModel):
    recommendation_lifecycle_event_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    recommendation_key: str
    from_status: str
    to_status: str
    reason_code: str
    event_time_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime | None = None


class PersistedRecommendationCandidatePoolSnapshot(BaseModel):
    recommendation_candidate_pool_snapshot_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    as_of_time_utc: datetime
    strategy: str
    pass_type: str
    mode: RecommendationMode
    candidate_count: int = Field(ge=0)
    selected_candidate_count: int = Field(ge=0)
    excluded_candidate_count: int = Field(ge=0)
    candidate_query_json: dict[str, object] = Field(default_factory=dict)
    source: str
    created_at: datetime


class PersistedRecommendationRunSnapshot(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    as_of_time_utc: datetime
    strategy: str
    pass_type: str
    mode: RecommendationMode
    status: str
    unit_stake: float = Field(gt=0.0)
    max_budget: float | None = Field(default=None, gt=0.0)
    candidate_count: int = Field(ge=0)
    excluded_candidate_count: int = Field(ge=0)
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    total_score: float | None = None
    parlay_evaluation_json: dict[str, object] = Field(default_factory=dict)
    explanation_json: dict[str, object] = Field(default_factory=dict)
    source: str
    created_at: datetime
    selected_candidates: list[RecommendationCandidate] = Field(default_factory=list)
    lifecycle_events: list[PersistedRecommendationLifecycleEventSnapshot] = Field(
        default_factory=list
    )
    locked_legs: list[PersistedRecommendationLockedLegSnapshot] = Field(
        default_factory=list
    )
    candidate_pool_snapshot: PersistedRecommendationCandidatePoolSnapshot | None = None
    candidate_pool_candidates: list[RecommendationCandidate] = Field(default_factory=list)


class PersistedRecommendationLifecycleReplayStage(BaseModel):
    stage_id: str
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    as_of_time_utc: datetime
    status: PersistedRecommendationReplayStageStatus
    pass_type: str
    mode: RecommendationMode
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    preserved_locked_fixture_ids: list[str] = Field(default_factory=list)
    missing_locked_fixture_ids: list[str] = Field(default_factory=list)
    started_locked_fixture_ids: list[str] = Field(default_factory=list)
    continuation_fixture_ids: list[str] = Field(default_factory=list)
    remaining_open_leg_count: int = Field(default=0, ge=0)
    changed_fixture_ids: list[str] = Field(default_factory=list)
    incident_fixture_ids: list[str] = Field(default_factory=list)
    lifecycle_reason_codes: list[str] = Field(default_factory=list)
    event_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    explanation_json: dict[str, object] = Field(default_factory=dict)


class PersistedRecommendationLifecycleReplayResult(BaseModel):
    stages: list[PersistedRecommendationLifecycleReplayStage] = Field(
        default_factory=list
    )
    final_stage: PersistedRecommendationLifecycleReplayStage | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class PostgresPersistedRecommendationLifecycleReplayRepository:
    def __init__(self, database: PersistedRecommendationReplayDatabaseExecutor) -> None:
        self.database = database

    def list_snapshots(
        self,
        *,
        options: PersistedRecommendationLifecycleReplayQueryOptions,
    ) -> list[PersistedRecommendationRunSnapshot]:
        run_rows = self.database.fetch_all(
            LIST_PERSISTED_RECOMMENDATION_RUNS_FOR_REPLAY_QUERY,
            {
                "window_start_utc": options.normalized_window_start_utc,
                "window_end_utc": options.normalized_window_end_utc,
                "recommendation_run_id": options.recommendation_run_id,
                "pass_type": options.pass_type,
                "mode": options.mode,
                "strategy": options.strategy,
                "limit": options.limit,
            },
        )
        if not run_rows:
            return []

        snapshots = [_run_snapshot_from_row(row) for row in run_rows]
        run_ids = [snapshot.recommendation_run_id for snapshot in snapshots]
        candidates_by_run_id = _group_by_run_id(
            self.database.fetch_all(
                LIST_PERSISTED_RECOMMENDATION_CANDIDATES_FOR_REPLAY_QUERY,
                {"recommendation_run_ids": run_ids},
            )
        )
        events_by_run_id = _group_by_run_id(
            self.database.fetch_all(
                LIST_PERSISTED_RECOMMENDATION_EVENTS_FOR_REPLAY_QUERY,
                {"recommendation_run_ids": run_ids},
            )
        )
        locked_legs_by_run_id = _group_by_run_id(
            self.database.fetch_all(
                LIST_PERSISTED_RECOMMENDATION_LOCKED_LEGS_FOR_REPLAY_QUERY,
                {"recommendation_run_ids": run_ids},
            )
        )
        pool_snapshots = [
            _pool_snapshot_from_row(row)
            for row in self.database.fetch_all(
                LIST_PERSISTED_RECOMMENDATION_POOL_SNAPSHOTS_FOR_REPLAY_QUERY,
                {"recommendation_run_ids": run_ids},
            )
        ]
        pool_snapshot_by_run_id = {
            snapshot.recommendation_run_id: snapshot for snapshot in pool_snapshots
        }
        pool_items_by_snapshot_id: dict[int, list[DatabaseRow]] = {}
        pool_snapshot_ids = [
            snapshot.recommendation_candidate_pool_snapshot_id
            for snapshot in pool_snapshots
        ]
        if pool_snapshot_ids:
            pool_items_by_snapshot_id = _group_by_pool_snapshot_id(
                self.database.fetch_all(
                    LIST_PERSISTED_RECOMMENDATION_POOL_ITEMS_FOR_REPLAY_QUERY,
                    {
                        "recommendation_candidate_pool_snapshot_ids": (
                            pool_snapshot_ids
                        )
                    },
                )
            )

        return [
            snapshot.model_copy(
                update={
                    "selected_candidates": [
                        _candidate_from_row(row)
                        for row in candidates_by_run_id.get(
                            snapshot.recommendation_run_id, []
                        )
                    ],
                    "lifecycle_events": [
                        _event_from_row(row)
                        for row in events_by_run_id.get(
                            snapshot.recommendation_run_id, []
                        )
                    ],
                    "locked_legs": [
                        _locked_leg_from_row(row)
                        for row in locked_legs_by_run_id.get(
                            snapshot.recommendation_run_id, []
                        )
                    ],
                    "candidate_pool_snapshot": pool_snapshot_by_run_id.get(
                        snapshot.recommendation_run_id
                    ),
                    "candidate_pool_candidates": [
                        _pool_item_candidate_from_row(row)
                        for row in pool_items_by_snapshot_id.get(
                            _pool_snapshot_id_for_run(
                                pool_snapshot_by_run_id,
                                snapshot.recommendation_run_id,
                            ),
                            [],
                        )
                    ],
                }
            )
            for snapshot in snapshots
        ]


def build_persisted_recommendation_lifecycle_replay(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> PersistedRecommendationLifecycleReplayResult:
    ordered_snapshots = sorted(
        snapshots,
        key=lambda snapshot: (
            _aware_utc(snapshot.as_of_time_utc),
            snapshot.recommendation_run_id,
        ),
    )
    stages: list[PersistedRecommendationLifecycleReplayStage] = []
    previous_selected_fixture_ids: list[str] | None = None

    for snapshot in ordered_snapshots:
        selected_fixture_ids = _selected_fixture_ids(snapshot)
        locked_fixture_ids = _active_locked_fixture_ids(snapshot)
        preserved_locked_fixture_ids = [
            fixture_id for fixture_id in locked_fixture_ids if fixture_id in selected_fixture_ids
        ]
        missing_locked_fixture_ids = [
            fixture_id
            for fixture_id in locked_fixture_ids
            if fixture_id not in selected_fixture_ids
        ]
        started_locked_fixture_ids = _started_locked_fixture_ids(
            snapshot,
            locked_fixture_ids=locked_fixture_ids,
        )
        continuation_fixture_ids = _continuation_fixture_ids(
            selected_fixture_ids,
            locked_fixture_ids=locked_fixture_ids,
        )
        remaining_open_leg_count = (
            len(continuation_fixture_ids)
            if selected_fixture_ids
            else _remaining_open_leg_count(
                snapshot.pass_type,
                locked_fixture_ids=locked_fixture_ids,
            )
        )
        incident_fixture_ids = _incident_fixture_ids(snapshot)
        successor_recompute_trace = _successor_recompute_trace(snapshot)
        lifecycle_reason_codes = _dedupe_strings(
            event.reason_code for event in snapshot.lifecycle_events
        )
        changed_fixture_ids = _changed_fixture_ids(
            previous_selected_fixture_ids,
            selected_fixture_ids,
        )
        status: PersistedRecommendationReplayStageStatus = (
            "selected" if selected_fixture_ids else "no_selection"
        )
        event_codes = _stage_event_codes(
            previous_selected_fixture_ids=previous_selected_fixture_ids,
            selected_fixture_ids=selected_fixture_ids,
            changed_fixture_ids=changed_fixture_ids,
            preserved_locked_fixture_ids=preserved_locked_fixture_ids,
            missing_locked_fixture_ids=missing_locked_fixture_ids,
            started_locked_fixture_ids=started_locked_fixture_ids,
            continuation_fixture_ids=continuation_fixture_ids,
            incident_fixture_ids=incident_fixture_ids,
            successor_recompute_observed=successor_recompute_trace is not None,
            lifecycle_reason_codes=lifecycle_reason_codes,
        )
        warnings = [
            f"locked_fixture_not_preserved:{fixture_id}"
            for fixture_id in missing_locked_fixture_ids
        ]

        stage = PersistedRecommendationLifecycleReplayStage(
            stage_id=snapshot.run_key,
            recommendation_run_id=snapshot.recommendation_run_id,
            run_key=snapshot.run_key,
            as_of_time_utc=_aware_utc(snapshot.as_of_time_utc),
            status=status,
            pass_type=snapshot.pass_type,
            mode=snapshot.mode,
            selected_fixture_ids=selected_fixture_ids,
            locked_fixture_ids=locked_fixture_ids,
            preserved_locked_fixture_ids=preserved_locked_fixture_ids,
            missing_locked_fixture_ids=missing_locked_fixture_ids,
            started_locked_fixture_ids=started_locked_fixture_ids,
            continuation_fixture_ids=continuation_fixture_ids,
            remaining_open_leg_count=remaining_open_leg_count,
            changed_fixture_ids=changed_fixture_ids,
            incident_fixture_ids=incident_fixture_ids,
            lifecycle_reason_codes=lifecycle_reason_codes,
            event_codes=event_codes,
            warnings=warnings,
            explanation_json={
                "calculation_basis": "persisted_recommendation_lifecycle_replay",
                "candidate_scope": _candidate_scope(snapshot),
                "candidate_count": snapshot.candidate_count,
                "candidate_pool_count": len(snapshot.candidate_pool_candidates),
                "excluded_candidate_count": snapshot.excluded_candidate_count,
                "stored_selected_candidate_count": len(snapshot.selected_candidates),
                "incident_notes": _incident_notes(snapshot),
                "run_status": snapshot.status,
                "source": snapshot.source,
                "successor_recompute": successor_recompute_trace,
                "continuation": {
                    "pass_type": snapshot.pass_type,
                    "total_leg_count": _pass_type_leg_count_or_selected_count(
                        snapshot.pass_type,
                        selected_fixture_ids=selected_fixture_ids,
                    ),
                    "locked_fixture_ids": locked_fixture_ids,
                    "started_locked_fixture_ids": started_locked_fixture_ids,
                    "continuation_fixture_ids": continuation_fixture_ids,
                    "remaining_open_leg_count": remaining_open_leg_count,
                    "selection_basis": (
                        "persisted locked legs remain constraints while unlocked "
                        "selected fixtures continue through future prematch replay"
                    ),
                },
            },
        )
        stages.append(stage)
        previous_selected_fixture_ids = selected_fixture_ids

    final_stage = stages[-1] if stages else None
    return PersistedRecommendationLifecycleReplayResult(
        stages=stages,
        final_stage=final_stage,
        summary_json=_replay_summary(stages),
    )


def build_prematch_backtest_checkpoints_from_persisted_snapshots(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    *,
    provider_incidents: Sequence[RecommendationProviderIncidentEventRecord] = (),
) -> list[PrematchRecommendationBacktestCheckpoint]:
    checkpoints = [
        PrematchRecommendationBacktestCheckpoint(
            checkpoint_id=snapshot.run_key,
            as_of_time_utc=_aware_utc(snapshot.as_of_time_utc),
            candidates=_checkpoint_candidates(snapshot),
            locked_fixture_ids=_active_locked_fixture_ids(snapshot),
            excluded_fixture_ids=_incident_fixture_ids(snapshot),
            incident_notes=_incident_notes(snapshot),
            metadata_json={
                "recommendation_run_id": snapshot.recommendation_run_id,
                "run_key": snapshot.run_key,
                "candidate_scope": _candidate_scope(snapshot),
                "candidate_pool_snapshot_id": (
                    snapshot.candidate_pool_snapshot.recommendation_candidate_pool_snapshot_id
                    if snapshot.candidate_pool_snapshot is not None
                    else None
                ),
                "source": "recommendation_runs",
            },
        )
        for snapshot in sorted(
            snapshots,
            key=lambda item: (_aware_utc(item.as_of_time_utc), item.recommendation_run_id),
        )
    ]
    if not provider_incidents:
        return checkpoints
    return apply_provider_incidents_to_backtest_checkpoints(
        checkpoints,
        provider_incidents,
    )


def _stage_event_codes(
    *,
    previous_selected_fixture_ids: list[str] | None,
    selected_fixture_ids: list[str],
    changed_fixture_ids: list[str],
    preserved_locked_fixture_ids: list[str],
    missing_locked_fixture_ids: list[str],
    started_locked_fixture_ids: list[str],
    continuation_fixture_ids: list[str],
    incident_fixture_ids: list[str],
    successor_recompute_observed: bool,
    lifecycle_reason_codes: list[str],
) -> list[str]:
    event_codes: list[str] = []
    if not selected_fixture_ids:
        event_codes.append("no_persisted_selection_available")
    elif previous_selected_fixture_ids is None:
        event_codes.append("initial_persisted_recommendation")
    elif changed_fixture_ids:
        event_codes.append("persisted_recommendation_changed")
    else:
        event_codes.append("persisted_recommendation_unchanged")

    if preserved_locked_fixture_ids:
        event_codes.append("locked_fixtures_preserved")
    if missing_locked_fixture_ids:
        event_codes.append("locked_fixtures_missing")
    if started_locked_fixture_ids:
        event_codes.append("started_locked_fixtures_retained")
    if continuation_fixture_ids:
        event_codes.append("remaining_fixtures_continue")
    if incident_fixture_ids:
        event_codes.append("incident_exclusion_observed")
    if successor_recompute_observed:
        event_codes.append("successor_recompute_generated")
    if any("lock" in reason_code for reason_code in lifecycle_reason_codes):
        event_codes.append("user_lock_event_recorded")
    if any("release" in reason_code for reason_code in lifecycle_reason_codes):
        event_codes.append("user_release_event_recorded")
    return _dedupe_strings(event_codes)


def _replay_summary(
    stages: Sequence[PersistedRecommendationLifecycleReplayStage],
) -> dict[str, object]:
    final_stage = stages[-1] if stages else None
    return {
        "stage_count": len(stages),
        "selected_stage_count": sum(1 for stage in stages if stage.status == "selected"),
        "changed_stage_count": sum(
            1 for stage in stages if "persisted_recommendation_changed" in stage.event_codes
        ),
        "incident_stage_count": sum(
            1 for stage in stages if "incident_exclusion_observed" in stage.event_codes
        ),
        "locked_preservation_stage_count": sum(
            1 for stage in stages if "locked_fixtures_preserved" in stage.event_codes
        ),
        "started_locked_stage_count": sum(
            1 for stage in stages if stage.started_locked_fixture_ids
        ),
        "continuation_stage_count": sum(
            1 for stage in stages if stage.continuation_fixture_ids
        ),
        "successor_recompute_stage_count": sum(
            1 for stage in stages if "successor_recompute_generated" in stage.event_codes
        ),
        "warning_count": sum(len(stage.warnings) for stage in stages),
        "final_run_key": final_stage.run_key if final_stage is not None else None,
        "final_selected_fixture_ids": (
            final_stage.selected_fixture_ids if final_stage is not None else []
        ),
        "final_continuation_fixture_ids": (
            final_stage.continuation_fixture_ids if final_stage is not None else []
        ),
        "final_remaining_open_leg_count": (
            final_stage.remaining_open_leg_count if final_stage is not None else 0
        ),
        "final_successor_source_recommendation_run_id": (
            _successor_source_recommendation_run_id(final_stage)
            if final_stage is not None
            else None
        ),
        "calculation_basis": "persisted_recommendation_lifecycle_replay_summary",
    }


def _selected_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
    if snapshot.selected_fixture_ids:
        return _dedupe_strings(snapshot.selected_fixture_ids)
    return _dedupe_strings(
        candidate.fixture_id for candidate in snapshot.selected_candidates
    )


def _checkpoint_candidates(
    snapshot: PersistedRecommendationRunSnapshot,
) -> list[RecommendationCandidate]:
    if snapshot.candidate_pool_candidates:
        return snapshot.candidate_pool_candidates
    return snapshot.selected_candidates


def _candidate_scope(snapshot: PersistedRecommendationRunSnapshot) -> str:
    if snapshot.candidate_pool_candidates:
        return "persisted_candidate_pool"
    return "persisted_selected_candidates"


def _active_locked_fixture_ids(
    snapshot: PersistedRecommendationRunSnapshot,
) -> list[str]:
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


def _started_locked_fixture_ids(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    locked_fixture_ids: Sequence[str],
) -> list[str]:
    candidates_by_fixture = _candidate_by_fixture_id(snapshot)
    as_of_time_utc = _aware_utc(snapshot.as_of_time_utc)
    return [
        fixture_id
        for fixture_id in locked_fixture_ids
        if fixture_id in candidates_by_fixture
        and candidates_by_fixture[fixture_id].has_started(as_of_time_utc)
    ]


def _continuation_fixture_ids(
    selected_fixture_ids: Sequence[str],
    *,
    locked_fixture_ids: Sequence[str],
) -> list[str]:
    locked = set(locked_fixture_ids)
    return [
        fixture_id
        for fixture_id in selected_fixture_ids
        if fixture_id not in locked
    ]


def _remaining_open_leg_count(
    pass_type: str,
    *,
    locked_fixture_ids: Sequence[str],
) -> int:
    return max(_pass_type_leg_count_or_selected_count(pass_type) - len(set(locked_fixture_ids)), 0)


def _pass_type_leg_count_or_selected_count(
    pass_type: str,
    *,
    selected_fixture_ids: Sequence[str] = (),
) -> int:
    try:
        return parse_pass_type_leg_count(pass_type)
    except ValueError:
        return len(set(selected_fixture_ids))


def _candidate_by_fixture_id(
    snapshot: PersistedRecommendationRunSnapshot,
) -> dict[str, RecommendationCandidate]:
    candidates_by_fixture: dict[str, RecommendationCandidate] = {}
    for candidate in [*snapshot.candidate_pool_candidates, *snapshot.selected_candidates]:
        candidates_by_fixture.setdefault(candidate.fixture_id, candidate)
    return candidates_by_fixture


def _changed_fixture_ids(
    previous_fixture_ids: list[str] | None,
    selected_fixture_ids: list[str],
) -> list[str]:
    if previous_fixture_ids is None:
        return []
    return sorted(set(previous_fixture_ids).symmetric_difference(selected_fixture_ids))


def _incident_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
    fixture_ids: list[str] = []
    fixture_ids.extend(
        _collect_fixture_ids(
            snapshot.explanation_json,
            keys=(
                "excluded_fixture_ids",
                "incident_fixture_ids",
                "incident_excluded_fixture_ids",
                "invalidated_fixture_ids",
            ),
        )
    )
    for event in snapshot.lifecycle_events:
        fixture_ids.extend(
            _collect_fixture_ids(
                event.metadata_json,
                keys=(
                    "excluded_fixture_ids",
                    "incident_fixture_ids",
                    "incident_excluded_fixture_ids",
                    "invalidated_fixture_ids",
                ),
            )
        )
        if _reason_suggests_incident(event.reason_code):
            fixture_id = event.metadata_json.get("fixture_id")
            if fixture_id is not None:
                fixture_ids.append(str(fixture_id))
    return _dedupe_strings(fixture_ids)


def _incident_notes(snapshot: PersistedRecommendationRunSnapshot) -> dict[str, str]:
    notes: dict[str, str] = {}
    event_payloads = [event.metadata_json for event in snapshot.lifecycle_events]
    for payload in [snapshot.explanation_json, *event_payloads]:
        for note_key in ("incident_notes", "provider_incident_notes"):
            value = payload.get(note_key)
            if isinstance(value, Mapping):
                notes.update({str(key): str(item) for key, item in value.items()})
        for nested_key in ("lifecycle", "lifecycle_backtest", "incident", "provider_incidents"):
            nested = payload.get(nested_key)
            if not isinstance(nested, Mapping):
                continue
            value = nested.get("incident_notes")
            if isinstance(value, Mapping):
                notes.update({str(key): str(item) for key, item in value.items()})
    return notes


def _successor_recompute_trace(
    snapshot: PersistedRecommendationRunSnapshot,
) -> dict[str, object] | None:
    internal_trace = snapshot.explanation_json.get("internal_trace")
    if not isinstance(internal_trace, Mapping):
        return None
    successor_recompute = internal_trace.get("successor_recompute")
    if not isinstance(successor_recompute, Mapping):
        return None
    return {str(key): value for key, value in successor_recompute.items()}


def _successor_source_recommendation_run_id(
    stage: PersistedRecommendationLifecycleReplayStage,
) -> int | None:
    successor_recompute = stage.explanation_json.get("successor_recompute")
    if not isinstance(successor_recompute, Mapping):
        return None
    value = successor_recompute.get("source_recommendation_run_id")
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _collect_fixture_ids(
    payload: Mapping[str, object],
    *,
    keys: Sequence[str],
) -> list[str]:
    fixture_ids: list[str] = []
    for key in keys:
        fixture_ids.extend(_string_values(payload.get(key)))
    for nested_key in ("lifecycle", "lifecycle_backtest", "incident", "provider_incidents"):
        nested = payload.get(nested_key)
        if not isinstance(nested, Mapping):
            continue
        for key in keys:
            fixture_ids.extend(_string_values(nested.get(key)))
    return fixture_ids


def _string_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [str(item) for item in value]
    return [str(value)]


def _reason_suggests_incident(reason_code: str) -> bool:
    lowered = reason_code.lower()
    return any(
        token in lowered
        for token in ("incident", "injury", "lineup", "invalidated", "data_quality")
    )


def _run_snapshot_from_row(row: DatabaseRow) -> PersistedRecommendationRunSnapshot:
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        as_of_time_utc=_datetime(row["as_of_time_utc"]),
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=_mode(row["mode"]),
        status=str(row["status"]),
        unit_stake=_float(row["unit_stake"]),
        max_budget=_optional_float(row.get("max_budget")),
        candidate_count=_int(row["candidate_count"]),
        excluded_candidate_count=_int(row["excluded_candidate_count"]),
        selected_fixture_ids=_string_list(row.get("selected_fixture_ids_json")),
        locked_fixture_ids=_string_list(row.get("locked_fixture_ids_json")),
        total_score=_optional_float(row.get("total_score")),
        parlay_evaluation_json=_json_object(row.get("parlay_evaluation_json")),
        explanation_json=_json_object(row.get("explanation_json")),
        source=str(row["source"]),
        created_at=_datetime(row["created_at"]),
    )


def _candidate_from_row(row: DatabaseRow) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=str(row["fixture_id"]),
        market_type=_market_type(row["market_type"]),
        outcome=str(row["outcome"]),
        probability=_float(row["probability"]),
        decimal_odds=_optional_float(row.get("decimal_odds")),
        market_probability=_optional_float(row.get("market_probability")),
        model_edge=_optional_float(row.get("model_edge")),
        data_quality_score=_float(row["data_quality_score"]),
        model_confidence_score=_float(row["model_confidence_score"]),
        calibration_score=_float(row["calibration_score"]),
        upset_protection_score=_float(row["upset_protection_score"]),
        odds_stability_score=_float(row["odds_stability_score"]),
        volatility_penalty=_float(row["volatility_penalty"]),
        line=_optional_float(row.get("line")),
        side=_optional_str(row.get("side")),
        candidate_id=str(row["recommendation_candidate_id"]),
        model_version=_optional_str(row.get("model_version")),
        prediction_snapshot_id=_optional_int(row.get("prediction_snapshot_id")),
        prediction_time_utc=_optional_datetime(row.get("prediction_time_utc")),
        kickoff_time_utc=_optional_datetime(row.get("kickoff_time_utc")),
        metadata_json={
            **_json_object(row.get("metadata_json")),
            "recommendation_candidate_id": _int(row["recommendation_candidate_id"]),
            "recommendation_run_id": _int(row["recommendation_run_id"]),
            "recommendation_score": _optional_float(row.get("recommendation_score")),
            "selected": _bool(row["selected"]),
            "locked": _bool(row["locked"]),
        },
    )


def _pool_snapshot_from_row(
    row: DatabaseRow,
) -> PersistedRecommendationCandidatePoolSnapshot:
    return PersistedRecommendationCandidatePoolSnapshot(
        recommendation_candidate_pool_snapshot_id=_int(
            row["recommendation_candidate_pool_snapshot_id"]
        ),
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        as_of_time_utc=_datetime(row["as_of_time_utc"]),
        strategy=str(row["strategy"]),
        pass_type=str(row["pass_type"]),
        mode=_mode(row["mode"]),
        candidate_count=_int(row["candidate_count"]),
        selected_candidate_count=_int(row["selected_candidate_count"]),
        excluded_candidate_count=_int(row["excluded_candidate_count"]),
        candidate_query_json=_json_object(row.get("candidate_query_json")),
        source=str(row["source"]),
        created_at=_datetime(row["created_at"]),
    )


def _pool_item_candidate_from_row(row: DatabaseRow) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=str(row["fixture_id"]),
        market_type=_market_type(row["market_type"]),
        outcome=str(row["outcome"]),
        probability=_float(row["probability"]),
        decimal_odds=_optional_float(row.get("decimal_odds")),
        market_probability=_optional_float(row.get("market_probability")),
        model_edge=_optional_float(row.get("model_edge")),
        data_quality_score=_float(row["data_quality_score"]),
        model_confidence_score=_float(row["model_confidence_score"]),
        calibration_score=_float(row["calibration_score"]),
        upset_protection_score=_float(row["upset_protection_score"]),
        odds_stability_score=_float(row["odds_stability_score"]),
        volatility_penalty=_float(row["volatility_penalty"]),
        line=_optional_float(row.get("line")),
        side=_optional_str(row.get("side")),
        candidate_id=str(row["recommendation_candidate_pool_item_id"]),
        model_version=_optional_str(row.get("model_version")),
        prediction_snapshot_id=_optional_int(row.get("prediction_snapshot_id")),
        prediction_time_utc=_optional_datetime(row.get("prediction_time_utc")),
        kickoff_time_utc=_optional_datetime(row.get("kickoff_time_utc")),
        metadata_json={
            **_json_object(row.get("metadata_json")),
            "recommendation_candidate_pool_item_id": _int(
                row["recommendation_candidate_pool_item_id"]
            ),
            "recommendation_candidate_pool_snapshot_id": _int(
                row["recommendation_candidate_pool_snapshot_id"]
            ),
            "selected": _bool(row["selected"]),
            "locked": _bool(row["locked"]),
        },
    )


def _event_from_row(row: DatabaseRow) -> PersistedRecommendationLifecycleEventSnapshot:
    return PersistedRecommendationLifecycleEventSnapshot(
        recommendation_lifecycle_event_id=_int(
            row["recommendation_lifecycle_event_id"]
        ),
        recommendation_run_id=_int(row["recommendation_run_id"]),
        recommendation_key=str(row["recommendation_key"]),
        from_status=str(row["from_status"]),
        to_status=str(row["to_status"]),
        reason_code=str(row["reason_code"]),
        event_time_utc=_datetime(row["event_time_utc"]),
        metadata_json=_json_object(row.get("metadata_json")),
        created_at=_optional_datetime(row.get("created_at")),
    )


def _locked_leg_from_row(row: DatabaseRow) -> PersistedRecommendationLockedLegSnapshot:
    return PersistedRecommendationLockedLegSnapshot(
        recommendation_locked_leg_id=_int(row["recommendation_locked_leg_id"]),
        recommendation_run_id=_int(row["recommendation_run_id"]),
        fixture_id=str(row["fixture_id"]),
        market_type=str(row["market_type"]),
        outcome=str(row["outcome"]),
        locked_at_utc=_datetime(row["locked_at_utc"]),
        status=str(row["status"]),
        metadata_json=_json_object(row.get("metadata_json")),
        created_at=_optional_datetime(row.get("created_at")),
    )


def _group_by_run_id(rows: Sequence[DatabaseRow]) -> dict[int, list[DatabaseRow]]:
    grouped: dict[int, list[DatabaseRow]] = {}
    for row in rows:
        grouped.setdefault(_int(row["recommendation_run_id"]), []).append(row)
    return grouped


def _group_by_pool_snapshot_id(
    rows: Sequence[DatabaseRow],
) -> dict[int, list[DatabaseRow]]:
    grouped: dict[int, list[DatabaseRow]] = {}
    for row in rows:
        grouped.setdefault(
            _int(row["recommendation_candidate_pool_snapshot_id"]), []
        ).append(row)
    return grouped


def _pool_snapshot_id_for_run(
    pool_snapshot_by_run_id: Mapping[int, PersistedRecommendationCandidatePoolSnapshot],
    recommendation_run_id: int,
) -> int:
    snapshot = pool_snapshot_by_run_id.get(recommendation_run_id)
    if snapshot is None:
        return 0
    return snapshot.recommendation_candidate_pool_snapshot_id


def _market_type(value: object) -> Literal[
    "1x2",
    "cn_handicap_1x2",
    "european_handicap_1x2",
    "correct_score",
]:
    text = str(value)
    if text not in {"1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"}:
        raise ValueError(f"unsupported recommendation market type: {text}")
    return text  # type: ignore[return-value]


def _mode(value: object) -> RecommendationMode:
    text = str(value)
    if text not in {"single", "multiple"}:
        raise ValueError(f"unsupported recommendation mode: {text}")
    return text  # type: ignore[return-value]


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, dict):
            return dict(loaded)
        raise ValueError("expected JSON object")
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    raise ValueError(f"expected JSON object, got {type(value).__name__}")


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, list):
            return list(loaded)
        raise ValueError("expected JSON array")
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return list(value)
    raise ValueError(f"expected JSON array, got {type(value).__name__}")


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_array(value)]


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("expected numeric value")
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    raise ValueError(f"expected numeric value, got {type(value).__name__}")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "t", "yes", "y"}
    if isinstance(value, int):
        return bool(value)
    raise ValueError(f"expected boolean value, got {type(value).__name__}")
