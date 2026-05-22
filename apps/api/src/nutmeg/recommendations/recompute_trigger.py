from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.engine import (
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    run_recommendation_generation,
)
from nutmeg.recommendations.incidents import (
    PostgresRecommendationProviderIncidentRepository,
    RecommendationProviderIncidentEventRecord,
    RecommendationProviderIncidentQueryOptions,
)
from nutmeg.recommendations.lifecycle_replay import (
    PersistedRecommendationLifecycleReplayQueryOptions,
    PersistedRecommendationRunSnapshot,
    PostgresPersistedRecommendationLifecycleReplayRepository,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationMode,
    RecommendationStrategy,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationDatabaseExecutor,
)

type RecommendationRecomputeTriggerAction = Literal["triggered", "skipped"]
type RecommendationGenerationRunner = Callable[
    [RecommendationDatabaseExecutor],
    RecommendationGenerationResult,
]

INSERT_RECOMMENDATION_RECOMPUTE_TRIGGER_RUN_QUERY = """
INSERT INTO recommendation_recompute_trigger_runs (
  trigger_key,
  as_of_time_utc,
  window_start_utc,
  window_end_utc,
  checked_run_count,
  triggered_run_count,
  skipped_run_count,
  incident_event_keys_json,
  source_recommendation_run_ids_json,
  generated_recommendation_run_ids_json,
  result_json,
  source
) VALUES (
  %(trigger_key)s,
  %(as_of_time_utc)s,
  %(window_start_utc)s,
  %(window_end_utc)s,
  %(checked_run_count)s,
  %(triggered_run_count)s,
  %(skipped_run_count)s,
  %(incident_event_keys_json)s::jsonb,
  %(source_recommendation_run_ids_json)s::jsonb,
  %(generated_recommendation_run_ids_json)s::jsonb,
  %(result_json)s::jsonb,
  %(source)s
)
ON CONFLICT (trigger_key) DO UPDATE
SET
  checked_run_count = EXCLUDED.checked_run_count,
  triggered_run_count = EXCLUDED.triggered_run_count,
  skipped_run_count = EXCLUDED.skipped_run_count,
  incident_event_keys_json = EXCLUDED.incident_event_keys_json,
  source_recommendation_run_ids_json = EXCLUDED.source_recommendation_run_ids_json,
  generated_recommendation_run_ids_json = EXCLUDED.generated_recommendation_run_ids_json,
  result_json = EXCLUDED.result_json,
  source = EXCLUDED.source,
  updated_at = now()
RETURNING recommendation_recompute_trigger_run_id, created_at, updated_at
"""


class RecommendationRecomputeTriggerDatabaseExecutor(RecommendationDatabaseExecutor, Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation recompute trigger source rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Write recommendation recompute trigger rows."""


class RecommendationRecomputeTriggerOptions(BaseModel):
    as_of_time_utc: datetime
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy | None = None
    include_candidate_pool_incidents: bool = True
    preserve_locked_legs: bool = True
    trigger_locked_successors: bool = False
    dry_run: bool = True
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)

    @property
    def window_start_utc(self) -> datetime:
        return self.normalized_as_of_time_utc - timedelta(hours=self.lookback_hours)


class RecommendationRecomputeTriggerDecision(BaseModel):
    source_recommendation_run_id: int = Field(gt=0)
    source_run_key: str
    action: RecommendationRecomputeTriggerAction
    reason_codes: list[str] = Field(default_factory=list)
    affected_fixture_ids: list[str] = Field(default_factory=list)
    excluded_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    preserved_locked_fixture_ids: list[str] = Field(default_factory=list)
    incident_event_keys: list[str] = Field(default_factory=list)
    generation_result: RecommendationGenerationResult | None = None
    warnings: list[str] = Field(default_factory=list)


class StoredRecommendationRecomputeTriggerRun(BaseModel):
    recommendation_recompute_trigger_run_id: int = Field(gt=0)
    trigger_key: str
    created_at: datetime
    updated_at: datetime


class RecommendationRecomputeTriggerRunResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    checked_run_count: int = Field(ge=0)
    triggered_run_count: int = Field(ge=0)
    skipped_run_count: int = Field(ge=0)
    generated_recommendation_run_ids: list[int] = Field(default_factory=list)
    incident_event_keys: list[str] = Field(default_factory=list)
    decisions: list[RecommendationRecomputeTriggerDecision] = Field(default_factory=list)
    stored_trigger_run: StoredRecommendationRecomputeTriggerRun | None = None
    warnings: list[str] = Field(default_factory=list)


class PostgresRecommendationRecomputeTriggerRepository:
    def __init__(self, database: RecommendationRecomputeTriggerDatabaseExecutor) -> None:
        self.database = database

    def save_run(
        self,
        result: RecommendationRecomputeTriggerRunResult,
        *,
        source: str = "recommendation_recompute_trigger_v3_1",
    ) -> StoredRecommendationRecomputeTriggerRun:
        trigger_key = _trigger_key(result)
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_RECOMPUTE_TRIGGER_RUN_QUERY,
                {
                    "trigger_key": trigger_key,
                    "as_of_time_utc": result.as_of_time_utc,
                    "window_start_utc": result.window_start_utc,
                    "window_end_utc": result.window_end_utc,
                    "checked_run_count": result.checked_run_count,
                    "triggered_run_count": result.triggered_run_count,
                    "skipped_run_count": result.skipped_run_count,
                    "incident_event_keys_json": _json(result.incident_event_keys),
                    "source_recommendation_run_ids_json": _json(
                        [
                            decision.source_recommendation_run_id
                            for decision in result.decisions
                        ]
                    ),
                    "generated_recommendation_run_ids_json": _json(
                        result.generated_recommendation_run_ids
                    ),
                    "result_json": _json(result.model_dump(mode="json")),
                    "source": source,
                },
            )
        )
        return StoredRecommendationRecomputeTriggerRun(
            recommendation_recompute_trigger_run_id=_int(
                row["recommendation_recompute_trigger_run_id"]
            ),
            trigger_key=trigger_key,
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
        )


def run_recommendation_recompute_trigger(
    database: RecommendationRecomputeTriggerDatabaseExecutor,
    *,
    options: RecommendationRecomputeTriggerOptions,
    replay_repository: PostgresPersistedRecommendationLifecycleReplayRepository | None = None,
    incident_repository: PostgresRecommendationProviderIncidentRepository | None = None,
    recommendation_repository: PostgresRecommendationRepository | None = None,
    trigger_repository: PostgresRecommendationRecomputeTriggerRepository | None = None,
    generation_runner: Callable[
        [
            RecommendationDatabaseExecutor,
            RecommendationGenerationOptions,
            PostgresRecommendationRepository | None,
        ],
        RecommendationGenerationResult,
    ] | None = None,
) -> RecommendationRecomputeTriggerRunResult:
    as_of_time = options.normalized_as_of_time_utc
    replay_reader = replay_repository or PostgresPersistedRecommendationLifecycleReplayRepository(
        database
    )
    snapshots = replay_reader.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=options.window_start_utc,
            window_end_utc=as_of_time,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            limit=options.source_run_limit,
        )
    )
    incident_reader = incident_repository or PostgresRecommendationProviderIncidentRepository(
        database
    )
    incidents = [
        incident
        for incident in incident_reader.list_events(
            options=RecommendationProviderIncidentQueryOptions(
                window_start_utc=options.window_start_utc,
                window_end_utc=as_of_time,
                only_affecting_recommendations=True,
                limit=options.incident_limit,
            )
        )
        if incident.active_at(as_of_time)
    ]

    decisions = [
        _recompute_decision_for_snapshot(
            snapshot,
            incidents=incidents,
            options=options,
            database=database,
            recommendation_repository=(
                recommendation_repository
                or (PostgresRecommendationRepository(database) if not options.dry_run else None)
            ),
            generation_runner=generation_runner or _run_generation,
        )
        for snapshot in snapshots
    ]
    generated_run_ids = [
        decision.generation_result.stored_run.recommendation_run_id
        for decision in decisions
        if decision.generation_result is not None
        and decision.generation_result.stored_run is not None
    ]
    result = RecommendationRecomputeTriggerRunResult(
        dry_run=options.dry_run,
        as_of_time_utc=as_of_time,
        window_start_utc=options.window_start_utc,
        window_end_utc=as_of_time,
        checked_run_count=len(snapshots),
        triggered_run_count=sum(
            1 for decision in decisions if decision.action == "triggered"
        ),
        skipped_run_count=sum(1 for decision in decisions if decision.action == "skipped"),
        generated_recommendation_run_ids=generated_run_ids,
        incident_event_keys=_dedupe_strings(
            incident.provider_incident_key for incident in incidents
        ),
        decisions=decisions,
    )
    if not options.dry_run:
        writer = trigger_repository or PostgresRecommendationRecomputeTriggerRepository(
            database
        )
        stored = writer.save_run(result)
        result = result.model_copy(update={"stored_trigger_run": stored})
    return result


def _recompute_decision_for_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
    options: RecommendationRecomputeTriggerOptions,
    database: RecommendationRecomputeTriggerDatabaseExecutor,
    recommendation_repository: PostgresRecommendationRepository | None,
    generation_runner: Callable[
        [
            RecommendationDatabaseExecutor,
            RecommendationGenerationOptions,
            PostgresRecommendationRepository | None,
        ],
        RecommendationGenerationResult,
    ],
) -> RecommendationRecomputeTriggerDecision:
    affected = _affected_incidents_for_snapshot(
        snapshot,
        incidents=incidents,
        include_candidate_pool=options.include_candidate_pool_incidents,
    )
    locked_candidates, locked_warnings = _locked_candidates_for_snapshot(
        snapshot,
        preserve_locked_legs=options.preserve_locked_legs,
    )
    locked_fixture_ids = [candidate.fixture_id for candidate in locked_candidates]
    if not affected:
        if options.trigger_locked_successors and locked_candidates:
            generation_options = _generation_options_from_snapshot(
                snapshot,
                as_of_time_utc=options.normalized_as_of_time_utc,
                dry_run=options.dry_run,
                locked_candidates=tuple(locked_candidates),
                excluded_fixture_ids=(),
                incident_event_keys=[],
                successor_recompute=True,
            )
            generation_result = generation_runner(
                database,
                generation_options,
                recommendation_repository if not options.dry_run else None,
            )
            return RecommendationRecomputeTriggerDecision(
                source_recommendation_run_id=snapshot.recommendation_run_id,
                source_run_key=snapshot.run_key,
                action="triggered",
                reason_codes=[
                    "locked_successor_recompute",
                    "locked_fixtures_preserved",
                ],
                locked_fixture_ids=locked_fixture_ids,
                preserved_locked_fixture_ids=locked_fixture_ids,
                generation_result=generation_result,
                warnings=locked_warnings,
            )
        return RecommendationRecomputeTriggerDecision(
            source_recommendation_run_id=snapshot.recommendation_run_id,
            source_run_key=snapshot.run_key,
            action="skipped",
            reason_codes=["no_active_incident_affects_source_run"],
            locked_fixture_ids=locked_fixture_ids,
            preserved_locked_fixture_ids=locked_fixture_ids,
            warnings=locked_warnings,
        )

    affected_fixture_ids = _dedupe_strings(
        fixture_id for incident in affected for fixture_id in incident.affected_fixture_ids()
    )
    excluded_fixture_ids = _recompute_excluded_fixture_ids(
        affected,
        locked_fixture_ids=set(locked_fixture_ids),
    )
    generation_options = _generation_options_from_snapshot(
        snapshot,
        as_of_time_utc=options.normalized_as_of_time_utc,
        dry_run=options.dry_run,
        locked_candidates=tuple(locked_candidates),
        excluded_fixture_ids=tuple(excluded_fixture_ids),
        incident_event_keys=[incident.provider_incident_key for incident in affected],
    )
    generation_result = generation_runner(
        database,
        generation_options,
        recommendation_repository if not options.dry_run else None,
    )
    return RecommendationRecomputeTriggerDecision(
        source_recommendation_run_id=snapshot.recommendation_run_id,
        source_run_key=snapshot.run_key,
        action="triggered",
        reason_codes=_trigger_reason_codes(
            snapshot,
            affected=affected,
            affected_fixture_ids=affected_fixture_ids,
        ),
        affected_fixture_ids=affected_fixture_ids,
        excluded_fixture_ids=excluded_fixture_ids,
        locked_fixture_ids=locked_fixture_ids,
        preserved_locked_fixture_ids=locked_fixture_ids,
        incident_event_keys=[incident.provider_incident_key for incident in affected],
        generation_result=generation_result,
        warnings=locked_warnings,
    )


def _affected_incidents_for_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
    include_candidate_pool: bool,
) -> list[RecommendationProviderIncidentEventRecord]:
    selected_fixture_ids = set(_selected_fixture_ids(snapshot))
    candidate_pool_fixture_ids = {
        candidate.fixture_id for candidate in snapshot.candidate_pool_candidates
    }
    locked_fixture_ids = set(_locked_fixture_ids(snapshot))
    affected: list[RecommendationProviderIncidentEventRecord] = []
    for incident in incidents:
        incident_fixture_ids = set(incident.affected_fixture_ids())
        if incident_fixture_ids & selected_fixture_ids:
            affected.append(incident)
            continue
        if incident_fixture_ids & locked_fixture_ids:
            affected.append(incident)
            continue
        if include_candidate_pool and incident_fixture_ids & candidate_pool_fixture_ids:
            affected.append(incident)
    return affected


def _generation_options_from_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    as_of_time_utc: datetime,
    dry_run: bool,
    locked_candidates: tuple[RecommendationCandidate, ...],
    excluded_fixture_ids: tuple[str, ...],
    incident_event_keys: list[str],
    successor_recompute: bool = False,
) -> RecommendationGenerationOptions:
    query = (
        snapshot.candidate_pool_snapshot.candidate_query_json
        if snapshot.candidate_pool_snapshot
        else {}
    )
    internal_trace: dict[str, object] = {
        "recompute_trigger": {
            "source_recommendation_run_id": snapshot.recommendation_run_id,
            "source_run_key": snapshot.run_key,
            "incident_event_keys": incident_event_keys,
            "excluded_fixture_ids": list(excluded_fixture_ids),
            "locked_fixture_ids": [
                candidate.fixture_id for candidate in locked_candidates
            ],
        }
    }
    if successor_recompute:
        internal_trace["successor_recompute"] = {
            "source_recommendation_run_id": snapshot.recommendation_run_id,
            "source_run_key": snapshot.run_key,
            "source_selected_fixture_ids": _selected_fixture_ids(snapshot),
            "locked_fixture_ids": [
                candidate.fixture_id for candidate in locked_candidates
            ],
            "calculation_basis": "locked_leg_successor_recompute_v3_1",
        }
    return RecommendationGenerationOptions(
        as_of_time_utc=as_of_time_utc,
        pass_type=snapshot.pass_type,
        mode=snapshot.mode,
        strategy=_strategy(snapshot.strategy),
        unit_stake=snapshot.unit_stake,
        max_budget=snapshot.max_budget,
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
        excluded_fixture_ids=excluded_fixture_ids,
        locked_candidates=locked_candidates,
        competition_id=_optional_str(query.get("competition_id")),
        model_version=_optional_str(query.get("model_version")),
        dry_run=dry_run,
        internal_trace_json=internal_trace,
    )


def _locked_candidates_for_snapshot(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    preserve_locked_legs: bool,
) -> tuple[list[RecommendationCandidate], list[str]]:
    if not preserve_locked_legs:
        return [], []
    locked_fixture_ids = _locked_fixture_ids(snapshot)
    source_candidates = [*snapshot.selected_candidates, *snapshot.candidate_pool_candidates]
    locked_candidates: list[RecommendationCandidate] = []
    warnings: list[str] = []
    used_fixture_ids: set[str] = set()
    for locked_leg in snapshot.locked_legs:
        if locked_leg.status != "locked" or locked_leg.fixture_id in used_fixture_ids:
            continue
        candidate = _matching_candidate_for_locked_leg(
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
    for fixture_id in locked_fixture_ids:
        if fixture_id in used_fixture_ids:
            continue
        candidate = _first_candidate_for_fixture(source_candidates, fixture_id)
        if candidate is None:
            warnings.append(f"locked_candidate_unavailable:{fixture_id}")
            continue
        locked_candidates.append(candidate)
        used_fixture_ids.add(fixture_id)
    return locked_candidates, warnings


def _matching_candidate_for_locked_leg(
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


def _recompute_excluded_fixture_ids(
    incidents: Sequence[RecommendationProviderIncidentEventRecord],
    *,
    locked_fixture_ids: set[str],
) -> list[str]:
    return _dedupe_strings(
        fixture_id
        for incident in incidents
        for fixture_id in incident.excluded_fixture_ids
        if fixture_id not in locked_fixture_ids
    )


def _trigger_reason_codes(
    snapshot: PersistedRecommendationRunSnapshot,
    *,
    affected: Sequence[RecommendationProviderIncidentEventRecord],
    affected_fixture_ids: list[str],
) -> list[str]:
    selected_fixture_ids = set(_selected_fixture_ids(snapshot))
    reason_codes: list[str] = []
    if any(incident.severity == "critical" for incident in affected):
        reason_codes.append("critical_provider_incident")
    if any(incident.incident_type == "odds_probability_shift" for incident in affected):
        reason_codes.append("odds_probability_shift")
    if selected_fixture_ids.intersection(affected_fixture_ids):
        reason_codes.append("selected_fixture_incident")
    else:
        reason_codes.append("candidate_pool_incident")
    return _dedupe_strings(reason_codes)


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
                locked.fixture_id
                for locked in snapshot.locked_legs
                if locked.status == "locked"
            ),
        ]
    )


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


def _allowed_markets(value: dict[str, object]) -> tuple[RecommendationMarketType, ...]:
    raw_markets = _string_list(value.get("allowed_markets"))
    supported = {"1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"}
    markets = [market for market in raw_markets if market in supported]
    if not markets:
        return ("1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score")
    return cast(tuple[RecommendationMarketType, ...], tuple(markets))


def _strategy(value: str) -> RecommendationStrategy:
    if value not in {
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    }:
        return "accuracy_first"
    return value  # type: ignore[return-value]


def _trigger_key(result: RecommendationRecomputeTriggerRunResult) -> str:
    payload = "|".join(
        [
            result.as_of_time_utc.isoformat(),
            result.window_start_utc.isoformat(),
            result.window_end_utc.isoformat(),
            ",".join(result.incident_event_keys),
            ",".join(str(item) for item in result.generated_recommendation_run_ids),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"recompute_trigger:{digest}"


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return [str(value)]


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


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


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _int_or_default(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return _int(value)
    except ValueError:
        return default


def _float_or_default(value: object, default: float) -> float:
    parsed = _optional_float(value)
    return default if parsed is None else parsed


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _bool_or_default(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "t", "yes", "y"}
    return default
