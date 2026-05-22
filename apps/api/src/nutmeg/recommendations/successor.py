from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from nutmeg.recommendations.engine import (
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    run_recommendation_generation,
)
from nutmeg.recommendations.lifecycle_replay import (
    PersistedRecommendationLifecycleReplayQueryOptions,
    PersistedRecommendationRunSnapshot,
    PostgresPersistedRecommendationLifecycleReplayRepository,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationStrategy,
)
from nutmeg.recommendations.recompute_trigger import (
    _allowed_markets,
    _bool_or_default,
    _float_or_default,
    _int_or_default,
    _optional_float,
    _optional_str,
    _strategy,
    _string_list,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationDatabaseExecutor,
)


class RecommendationSuccessorRecomputeOptions(BaseModel):
    source_recommendation_run_id: int = Field(gt=0)
    as_of_time_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy | None = None
    unit_stake: float | None = Field(default=None, gt=0.0)
    max_budget: float | None = Field(default=None, gt=0.0)
    preserve_locked_legs: bool = True
    excluded_fixture_ids: tuple[str, ...] = ()
    dry_run: bool = True

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class RecommendationSuccessorRecomputeRunResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    source_recommendation_run_id: int = Field(gt=0)
    source_run_key: str | None = None
    source_selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    continuation_fixture_ids: list[str] = Field(default_factory=list)
    generated_recommendation_run_id: int | None = Field(default=None, gt=0)
    generation_result: RecommendationGenerationResult | None = None
    warnings: list[str] = Field(default_factory=list)


def run_recommendation_successor_recompute(
    database: RecommendationDatabaseExecutor,
    *,
    options: RecommendationSuccessorRecomputeOptions,
    replay_repository: PostgresPersistedRecommendationLifecycleReplayRepository | None = None,
    recommendation_repository: PostgresRecommendationRepository | None = None,
    generation_runner: Callable[
        [
            RecommendationDatabaseExecutor,
            RecommendationGenerationOptions,
            PostgresRecommendationRepository | None,
        ],
        RecommendationGenerationResult,
    ]
    | None = None,
) -> RecommendationSuccessorRecomputeRunResult:
    as_of_time = options.normalized_as_of_time_utc
    replay_reader = replay_repository or PostgresPersistedRecommendationLifecycleReplayRepository(
        database
    )
    snapshots = replay_reader.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=datetime(1970, 1, 1, tzinfo=UTC),
            window_end_utc=datetime(9999, 12, 31, tzinfo=UTC),
            recommendation_run_id=options.source_recommendation_run_id,
            limit=1,
        )
    )
    if not snapshots:
        return RecommendationSuccessorRecomputeRunResult(
            dry_run=options.dry_run,
            as_of_time_utc=as_of_time,
            source_recommendation_run_id=options.source_recommendation_run_id,
            warnings=["source_recommendation_run_not_found"],
        )

    snapshot = snapshots[0]
    locked_candidates, locked_warnings = _locked_candidates_for_snapshot(
        snapshot,
        preserve_locked_legs=options.preserve_locked_legs,
    )
    generation_options = _generation_options_from_snapshot(
        snapshot,
        options=options,
        as_of_time_utc=as_of_time,
        locked_candidates=tuple(locked_candidates),
    )
    runner = generation_runner or _run_generation
    generation_result = runner(
        database,
        generation_options,
        recommendation_repository if not options.dry_run else None,
    )
    locked_fixture_ids = [candidate.fixture_id for candidate in locked_candidates]
    continuation_fixture_ids = (
        _continuation_fixture_ids(
            generation_result.selection.fixture_ids,
            locked_fixture_ids=locked_fixture_ids,
        )
        if generation_result.selection is not None
        else []
    )
    stored_run = generation_result.stored_run
    return RecommendationSuccessorRecomputeRunResult(
        dry_run=options.dry_run,
        as_of_time_utc=as_of_time,
        source_recommendation_run_id=snapshot.recommendation_run_id,
        source_run_key=snapshot.run_key,
        source_selected_fixture_ids=_selected_fixture_ids(snapshot),
        locked_fixture_ids=locked_fixture_ids,
        continuation_fixture_ids=continuation_fixture_ids,
        generated_recommendation_run_id=(
            stored_run.recommendation_run_id if stored_run is not None else None
        ),
        generation_result=generation_result,
        warnings=[*locked_warnings, *generation_result.warnings],
    )


def _generation_options_from_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    options: RecommendationSuccessorRecomputeOptions,
    as_of_time_utc: datetime,
    locked_candidates: tuple[RecommendationCandidate, ...],
) -> RecommendationGenerationOptions:
    query = (
        snapshot.candidate_pool_snapshot.candidate_query_json
        if snapshot.candidate_pool_snapshot
        else {}
    )
    excluded_fixture_ids = _dedupe_strings(
        [*_string_list(query.get("excluded_fixture_ids")), *options.excluded_fixture_ids]
    )
    return RecommendationGenerationOptions(
        as_of_time_utc=as_of_time_utc,
        pass_type=options.pass_type or snapshot.pass_type,
        mode=options.mode or snapshot.mode,
        strategy=options.strategy or _strategy(snapshot.strategy),
        unit_stake=options.unit_stake or snapshot.unit_stake,
        max_budget=options.max_budget if options.max_budget is not None else snapshot.max_budget,
        allowed_markets=_allowed_markets(query),
        min_probability=_float_or_default(query.get("min_probability"), 0.20),
        min_model_edge=_optional_float(query.get("min_model_edge")),
        min_data_quality_score=_float_or_default(
            query.get("min_data_quality_score"),
            50.0,
        ),
        candidate_limit=_int_or_default(query.get("candidate_limit"), 200),
        require_odds=_bool_or_default(query.get("require_odds"), True),
        fixture_ids=tuple(_string_list(query.get("fixture_ids"))),
        excluded_fixture_ids=tuple(excluded_fixture_ids),
        locked_candidates=locked_candidates,
        competition_id=_optional_str(query.get("competition_id")),
        model_version=_optional_str(query.get("model_version")),
        dry_run=options.dry_run,
        internal_trace_json={
            "successor_recompute": {
                "source_recommendation_run_id": snapshot.recommendation_run_id,
                "source_run_key": snapshot.run_key,
                "source_selected_fixture_ids": _selected_fixture_ids(snapshot),
                "locked_fixture_ids": [
                    candidate.fixture_id for candidate in locked_candidates
                ],
                "excluded_fixture_ids": excluded_fixture_ids,
                "calculation_basis": "locked_leg_successor_recompute_v3_1",
            }
        },
    )


def _locked_candidates_for_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    preserve_locked_legs: bool,
) -> tuple[list[RecommendationCandidate], list[str]]:
    if not preserve_locked_legs:
        return [], []
    source_candidates = [*snapshot.selected_candidates, *snapshot.candidate_pool_candidates]
    locked_candidates: list[RecommendationCandidate] = []
    warnings: list[str] = []
    used_fixture_ids: set[str] = set()
    for locked_leg in snapshot.locked_legs:
        if locked_leg.status != "locked" or locked_leg.fixture_id in used_fixture_ids:
            continue
        candidate = _matching_candidate(
            source_candidates,
            fixture_id=locked_leg.fixture_id,
            market_type=locked_leg.market_type,
            outcome=locked_leg.outcome,
        )
        if candidate is None:
            warnings.append(f"locked_candidate_unavailable:{locked_leg.fixture_id}")
            continue
        locked_candidates.append(candidate)
        used_fixture_ids.add(locked_leg.fixture_id)

    for fixture_id in _locked_fixture_ids(snapshot):
        if fixture_id in used_fixture_ids:
            continue
        candidate = _first_candidate_for_fixture(source_candidates, fixture_id)
        if candidate is None:
            warnings.append(f"locked_candidate_unavailable:{fixture_id}")
            continue
        locked_candidates.append(candidate)
        used_fixture_ids.add(fixture_id)
    return locked_candidates, warnings


def _matching_candidate(
    candidates: Sequence[RecommendationCandidate],
    *,
    fixture_id: str,
    market_type: str,
    outcome: str,
) -> RecommendationCandidate | None:
    for candidate in candidates:
        if (
            candidate.fixture_id == fixture_id
            and candidate.market_type == market_type
            and candidate.outcome == outcome
        ):
            return candidate
    return None


def _first_candidate_for_fixture(
    candidates: Sequence[RecommendationCandidate],
    fixture_id: str,
) -> RecommendationCandidate | None:
    for candidate in candidates:
        if candidate.fixture_id == fixture_id:
            return candidate
    return None


def _selected_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
    if snapshot.selected_fixture_ids:
        return _dedupe_strings(snapshot.selected_fixture_ids)
    return _dedupe_strings(
        candidate.fixture_id for candidate in snapshot.selected_candidates
    )


def _locked_fixture_ids(snapshot: PersistedRecommendationRunSnapshot) -> list[str]:
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


def _continuation_fixture_ids(
    fixture_ids: Sequence[str],
    *,
    locked_fixture_ids: Sequence[str],
) -> list[str]:
    locked = set(locked_fixture_ids)
    return [fixture_id for fixture_id in fixture_ids if fixture_id not in locked]


def _run_generation(
    database: RecommendationDatabaseExecutor,
    options: RecommendationGenerationOptions,
    repository: PostgresRecommendationRepository | None,
) -> RecommendationGenerationResult:
    return run_recommendation_generation(
        database,
        options=options,
        repository=repository,
    )


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
