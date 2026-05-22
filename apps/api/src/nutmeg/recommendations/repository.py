from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from json import dumps, loads
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.lifecycle import RecommendationLifecycleStatus
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationProbabilitySource,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)

LIST_RECOMMENDATION_CANDIDATES_QUERY = """
WITH latest_predictions AS (
  SELECT DISTINCT ON (ps.fixture_id)
    ps.prediction_snapshot_id,
    ps.fixture_id,
    ps.prediction_time_utc,
    ps.model_version,
    ps.data_quality_score,
    f.competition_id,
    f.kickoff_time_utc
  FROM prediction_snapshots ps
  JOIN fixtures f
    ON f.fixture_id = ps.fixture_id
  WHERE ps.prediction_time_utc <= %(as_of_time_utc)s
    AND f.kickoff_time_utc >= %(as_of_time_utc)s
    AND f.status = ANY(%(fixture_statuses)s)
    AND (%(competition_id)s::text IS NULL OR f.competition_id = %(competition_id)s::text)
    AND (%(fixture_ids)s::text[] IS NULL OR ps.fixture_id = ANY(%(fixture_ids)s::text[]))
    AND (%(model_version)s::text IS NULL OR ps.model_version = %(model_version)s::text)
    AND ps.data_quality_score >= %(min_data_quality_score)s
  ORDER BY ps.fixture_id, ps.prediction_time_utc DESC, ps.prediction_snapshot_id DESC
)
SELECT
  lp.prediction_snapshot_id,
  lp.fixture_id,
  lp.prediction_time_utc,
  lp.model_version,
  lp.data_quality_score,
  lp.competition_id,
  lp.kickoff_time_utc,
  mp.market_prediction_id,
  mp.market_type,
  mp.line,
  mp.side,
  mp.outcome,
  mp.probability,
  odds.decimal_odds,
  COALESCE(
    odds.fair_probability,
    CASE WHEN odds.decimal_odds > 1 THEN 1 / odds.decimal_odds ELSE NULL END,
    CASE WHEN mp.fair_odds > 1 THEN 1 / mp.fair_odds ELSE NULL END
  ) AS market_probability,
  (
    mp.probability - COALESCE(
      odds.fair_probability,
      CASE WHEN odds.decimal_odds > 1 THEN 1 / odds.decimal_odds ELSE NULL END,
      CASE WHEN mp.fair_odds > 1 THEN 1 / mp.fair_odds ELSE NULL END,
      mp.probability
    )
  ) AS model_edge,
  COALESCE(upset.upset_score, 0) AS upset_score,
  COALESCE(upset.favorite_fragility_score, 0) AS favorite_fragility_score
FROM latest_predictions lp
JOIN market_predictions mp
  ON mp.prediction_snapshot_id = lp.prediction_snapshot_id
LEFT JOIN LATERAL (
  SELECT
    os.decimal_odds,
    os.fair_probability,
    os.snapshot_time_utc
  FROM odds_snapshots os
  WHERE os.fixture_id = mp.fixture_id
    AND os.market_type = mp.market_type
    AND os.outcome = mp.outcome
    AND os.line IS NOT DISTINCT FROM mp.line
    AND os.side IS NOT DISTINCT FROM mp.side
    AND os.decimal_odds > 1
    AND os.snapshot_time_utc <= %(as_of_time_utc)s
  ORDER BY os.snapshot_time_utc DESC, os.odds_snapshot_id DESC
  LIMIT 1
) odds ON TRUE
LEFT JOIN LATERAL (
  SELECT
    ua.upset_score,
    ua.favorite_fragility_score
  FROM upset_alerts ua
  WHERE ua.fixture_id = mp.fixture_id
    AND ua.target_market_type = mp.market_type
    AND ua.target_outcome = mp.outcome
    AND ua.target_line IS NOT DISTINCT FROM mp.line
  ORDER BY ua.created_at DESC, ua.upset_alert_id DESC
  LIMIT 1
) upset ON TRUE
WHERE mp.market_type = ANY(%(allowed_markets)s)
  AND mp.probability >= %(min_probability)s
  AND (%(require_odds)s = false OR odds.decimal_odds IS NOT NULL)
  AND (
    %(min_model_edge)s::numeric IS NULL
    OR (
      mp.probability - COALESCE(
        odds.fair_probability,
        CASE WHEN odds.decimal_odds > 1 THEN 1 / odds.decimal_odds ELSE NULL END,
        CASE WHEN mp.fair_odds > 1 THEN 1 / mp.fair_odds ELSE NULL END,
        mp.probability
      )
    ) >= %(min_model_edge)s
  )
ORDER BY
  lp.model_version ASC,
  model_edge DESC,
  mp.probability DESC,
  lp.fixture_id ASC,
  mp.market_prediction_id ASC
LIMIT %(candidate_limit)s
"""

INSERT_RECOMMENDATION_RUN_QUERY = """
INSERT INTO recommendation_runs (
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
  source
) VALUES (
  %(run_key)s,
  %(as_of_time_utc)s,
  %(strategy)s,
  %(pass_type)s,
  %(mode)s,
  %(status)s,
  %(unit_stake)s,
  %(max_budget)s,
  %(candidate_count)s,
  %(excluded_candidate_count)s,
  %(selected_fixture_ids_json)s::jsonb,
  %(locked_fixture_ids_json)s::jsonb,
  %(total_score)s,
  %(parlay_evaluation_json)s::jsonb,
  %(explanation_json)s::jsonb,
  %(source)s
)
RETURNING recommendation_run_id, created_at
"""

INSERT_RECOMMENDATION_CANDIDATE_QUERY = """
INSERT INTO recommendation_candidates (
  recommendation_run_id,
  fixture_id,
  market_type,
  line,
  side,
  outcome,
  probability,
  model_probability,
  calibrated_probability,
  probability_source,
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
  metadata_json
) VALUES (
  %(recommendation_run_id)s,
  %(fixture_id)s,
  %(market_type)s,
  %(line)s,
  %(side)s,
  %(outcome)s,
  %(probability)s,
  %(model_probability)s,
  %(calibrated_probability)s,
  %(probability_source)s,
  %(decimal_odds)s,
  %(market_probability)s,
  %(model_edge)s,
  %(data_quality_score)s,
  %(model_confidence_score)s,
  %(calibration_score)s,
  %(upset_protection_score)s,
  %(odds_stability_score)s,
  %(volatility_penalty)s,
  %(model_version)s,
  %(prediction_snapshot_id)s,
  %(prediction_time_utc)s,
  %(kickoff_time_utc)s,
  %(recommendation_score)s,
  %(selected)s,
  %(locked)s,
  %(metadata_json)s::jsonb
)
RETURNING recommendation_candidate_id
"""

INSERT_RECOMMENDATION_CANDIDATE_POOL_SNAPSHOT_QUERY = """
INSERT INTO recommendation_candidate_pool_snapshots (
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
  source
) VALUES (
  %(recommendation_run_id)s,
  %(run_key)s,
  %(as_of_time_utc)s,
  %(strategy)s,
  %(pass_type)s,
  %(mode)s,
  %(candidate_count)s,
  %(selected_candidate_count)s,
  %(excluded_candidate_count)s,
  %(candidate_query_json)s::jsonb,
  %(source)s
)
RETURNING recommendation_candidate_pool_snapshot_id
"""

INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY = """
INSERT INTO recommendation_candidate_pool_items (
  recommendation_candidate_pool_snapshot_id,
  fixture_id,
  market_type,
  line,
  side,
  outcome,
  probability,
  model_probability,
  calibrated_probability,
  probability_source,
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
  metadata_json
) VALUES (
  %(recommendation_candidate_pool_snapshot_id)s,
  %(fixture_id)s,
  %(market_type)s,
  %(line)s,
  %(side)s,
  %(outcome)s,
  %(probability)s,
  %(model_probability)s,
  %(calibrated_probability)s,
  %(probability_source)s,
  %(decimal_odds)s,
  %(market_probability)s,
  %(model_edge)s,
  %(data_quality_score)s,
  %(model_confidence_score)s,
  %(calibration_score)s,
  %(upset_protection_score)s,
  %(odds_stability_score)s,
  %(volatility_penalty)s,
  %(model_version)s,
  %(prediction_snapshot_id)s,
  %(prediction_time_utc)s,
  %(kickoff_time_utc)s,
  %(selected)s,
  %(locked)s,
  %(metadata_json)s::jsonb
)
RETURNING recommendation_candidate_pool_item_id
"""

INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY = """
INSERT INTO recommendation_lifecycle_events (
  recommendation_run_id,
  recommendation_key,
  from_status,
  to_status,
  reason_code,
  event_time_utc,
  metadata_json
) VALUES (
  %(recommendation_run_id)s,
  %(recommendation_key)s,
  %(from_status)s,
  %(to_status)s,
  %(reason_code)s,
  %(event_time_utc)s,
  %(metadata_json)s::jsonb
)
RETURNING recommendation_lifecycle_event_id
"""

GET_RECOMMENDATION_RUN_QUERY = """
SELECT
  recommendation_run_id,
  run_key,
  status,
  selected_fixture_ids_json,
  locked_fixture_ids_json,
  created_at
FROM recommendation_runs
WHERE recommendation_run_id = %(recommendation_run_id)s
"""

UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY = """
UPDATE recommendation_runs
SET
  status = %(status)s,
  locked_fixture_ids_json = %(locked_fixture_ids_json)s::jsonb,
  explanation_json = explanation_json || %(explanation_patch_json)s::jsonb
WHERE recommendation_run_id = %(recommendation_run_id)s
RETURNING
  recommendation_run_id,
  run_key,
  status,
  selected_fixture_ids_json,
  locked_fixture_ids_json,
  created_at
"""

INSERT_RECOMMENDATION_LOCKED_LEG_QUERY = """
INSERT INTO recommendation_locked_legs (
  recommendation_run_id,
  fixture_id,
  market_type,
  outcome,
  locked_at_utc,
  status,
  metadata_json
) VALUES (
  %(recommendation_run_id)s,
  %(fixture_id)s,
  %(market_type)s,
  %(outcome)s,
  %(locked_at_utc)s,
  %(status)s,
  %(metadata_json)s::jsonb
)
RETURNING recommendation_locked_leg_id
"""

UPDATE_RECOMMENDATION_LOCKED_LEG_STATUS_QUERY = """
UPDATE recommendation_locked_legs
SET
  status = %(status)s,
  metadata_json = metadata_json || %(metadata_json)s::jsonb
WHERE recommendation_run_id = %(recommendation_run_id)s
  AND fixture_id = %(fixture_id)s
  AND market_type = %(market_type)s
  AND outcome = %(outcome)s
  AND status = 'locked'
RETURNING
  recommendation_locked_leg_id,
  recommendation_run_id,
  fixture_id,
  market_type,
  outcome,
  locked_at_utc,
  status,
  metadata_json
"""

LIST_RECOMMENDATION_LOCKED_LEGS_QUERY = """
SELECT
  recommendation_locked_leg_id,
  recommendation_run_id,
  fixture_id,
  market_type,
  outcome,
  locked_at_utc,
  status,
  metadata_json
FROM recommendation_locked_legs
WHERE recommendation_run_id = %(recommendation_run_id)s
ORDER BY locked_at_utc ASC, recommendation_locked_leg_id ASC
"""

LIST_RECOMMENDATION_LIFECYCLE_EVENTS_QUERY = """
SELECT
  recommendation_lifecycle_event_id,
  recommendation_run_id,
  recommendation_key,
  from_status,
  to_status,
  reason_code,
  event_time_utc,
  metadata_json
FROM recommendation_lifecycle_events
WHERE recommendation_run_id = %(recommendation_run_id)s
ORDER BY event_time_utc ASC, recommendation_lifecycle_event_id ASC
LIMIT %(limit)s
"""


class RecommendationDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation candidate rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one row."""


class RecommendationCandidateQueryOptions(BaseModel):
    as_of_time_utc: datetime
    allowed_markets: tuple[RecommendationMarketType, ...] = (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
        "correct_score",
    )
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    require_odds: bool = True
    candidate_limit: int = Field(default=200, ge=1, le=2_000)
    fixture_statuses: tuple[str, ...] = ("scheduled", "beta")
    fixture_ids: tuple[str, ...] = ()
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class StoredRecommendationRun(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    recommendation_candidate_ids: list[int] = Field(default_factory=list)
    recommendation_candidate_pool_snapshot_id: int | None = None
    recommendation_candidate_pool_item_ids: list[int] = Field(default_factory=list)
    recommendation_lifecycle_event_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class RecommendationRunLifecycleRecord(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str
    status: RecommendationLifecycleStatus
    selected_fixture_ids: list[str] = Field(default_factory=list)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class RecommendationLockedLegRecord(BaseModel):
    recommendation_locked_leg_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    fixture_id: str
    market_type: str
    outcome: str
    locked_at_utc: datetime
    status: str
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationLifecycleEventRecord(BaseModel):
    recommendation_lifecycle_event_id: int = Field(gt=0)
    recommendation_run_id: int = Field(gt=0)
    recommendation_key: str
    from_status: RecommendationLifecycleStatus
    to_status: RecommendationLifecycleStatus
    reason_code: str
    event_time_utc: datetime
    metadata_json: dict[str, object] = Field(default_factory=dict)


class RecommendationLifecycleMutationResult(BaseModel):
    run: RecommendationRunLifecycleRecord
    event: RecommendationLifecycleEventRecord
    locked_leg: RecommendationLockedLegRecord | None = None


class RecommendationLifecycleDetail(BaseModel):
    run: RecommendationRunLifecycleRecord
    locked_legs: list[RecommendationLockedLegRecord] = Field(default_factory=list)
    events: list[RecommendationLifecycleEventRecord] = Field(default_factory=list)


class PostgresRecommendationRepository:
    def __init__(self, database: RecommendationDatabaseExecutor) -> None:
        self.database = database

    def list_candidates(
        self,
        *,
        options: RecommendationCandidateQueryOptions,
    ) -> list[RecommendationCandidate]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_CANDIDATES_QUERY,
            {
                "as_of_time_utc": options.normalized_as_of_time_utc,
                "allowed_markets": list(options.allowed_markets),
                "min_probability": options.min_probability,
                "min_model_edge": options.min_model_edge,
                "min_data_quality_score": options.min_data_quality_score,
                "require_odds": options.require_odds,
                "candidate_limit": options.candidate_limit,
                "fixture_statuses": list(options.fixture_statuses),
                "fixture_ids": list(options.fixture_ids) or None,
                "competition_id": options.competition_id,
                "model_version": options.model_version,
            },
        )
        return [_candidate_from_row(row) for row in rows]

    def save_selection(
        self,
        selection: RecommendationSelection,
        *,
        as_of_time_utc: datetime,
        run_key: str,
        source: str = "recommendation_engine_v3_1",
        internal_trace_json: dict[str, object] | None = None,
        candidate_pool: Sequence[RecommendationCandidate] = (),
        candidate_query_json: dict[str, object] | None = None,
    ) -> StoredRecommendationRun:
        normalized_as_of_time_utc = _aware_utc(as_of_time_utc)
        run_row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_RUN_QUERY,
                _run_params(
                    selection,
                    as_of_time_utc=normalized_as_of_time_utc,
                    run_key=run_key,
                    source=source,
                    internal_trace_json=internal_trace_json or {},
                ),
            )
        )
        recommendation_run_id = _int(run_row["recommendation_run_id"])
        candidate_ids = [
            self._insert_selected_candidate(recommendation_run_id, selection, index)
            for index in range(len(selection.selected_candidates))
        ]
        candidate_pool_snapshot_id: int | None = None
        candidate_pool_item_ids: list[int] = []
        if candidate_pool:
            candidate_pool_snapshot_id = self._insert_candidate_pool_snapshot(
                recommendation_run_id,
                selection=selection,
                as_of_time_utc=normalized_as_of_time_utc,
                run_key=run_key,
                source=source,
                candidate_count=len(candidate_pool),
                candidate_query_json=candidate_query_json or {},
            )
            candidate_pool_item_ids = [
                self._insert_candidate_pool_item(
                    candidate_pool_snapshot_id,
                    candidate,
                    selection=selection,
                )
                for candidate in candidate_pool
            ]
        lifecycle_event_id = self._insert_lifecycle_event(
            recommendation_run_id,
            run_key=run_key,
            event_time_utc=normalized_as_of_time_utc,
        )
        return StoredRecommendationRun(
            recommendation_run_id=recommendation_run_id,
            recommendation_candidate_ids=candidate_ids,
            recommendation_candidate_pool_snapshot_id=candidate_pool_snapshot_id,
            recommendation_candidate_pool_item_ids=candidate_pool_item_ids,
            recommendation_lifecycle_event_ids=[lifecycle_event_id],
            created_at=_datetime(run_row["created_at"]),
        )

    def get_lifecycle_detail(
        self,
        recommendation_run_id: int,
        *,
        event_limit: int = 100,
    ) -> RecommendationLifecycleDetail:
        run = self._get_run_lifecycle(recommendation_run_id)
        locked_legs = [
            _locked_leg_from_row(row)
            for row in self.database.fetch_all(
                LIST_RECOMMENDATION_LOCKED_LEGS_QUERY,
                {"recommendation_run_id": recommendation_run_id},
            )
        ]
        events = [
            _event_from_row(row)
            for row in self.database.fetch_all(
                LIST_RECOMMENDATION_LIFECYCLE_EVENTS_QUERY,
                {
                    "recommendation_run_id": recommendation_run_id,
                    "limit": max(1, event_limit),
                },
            )
        ]
        return RecommendationLifecycleDetail(run=run, locked_legs=locked_legs, events=events)

    def lock_leg(
        self,
        recommendation_run_id: int,
        *,
        fixture_id: str,
        market_type: str,
        outcome: str,
        locked_at_utc: datetime,
        reason_code: str = "user_locked_leg",
        metadata_json: dict[str, object] | None = None,
    ) -> RecommendationLifecycleMutationResult:
        run = self._get_run_lifecycle(recommendation_run_id)
        locked_at = _aware_utc(locked_at_utc)
        locked_leg_row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_LOCKED_LEG_QUERY,
                {
                    "recommendation_run_id": recommendation_run_id,
                    "fixture_id": fixture_id,
                    "market_type": market_type,
                    "outcome": outcome,
                    "locked_at_utc": locked_at,
                    "status": "locked",
                    "metadata_json": _json(metadata_json or {}),
                },
            )
        )
        next_locked_fixture_ids = _append_unique(run.locked_fixture_ids, fixture_id)
        next_run = self._update_run_lifecycle(
            run,
            to_status="locked",
            locked_fixture_ids=next_locked_fixture_ids,
            explanation_patch={
                "lifecycle": {
                    "last_event": reason_code,
                    "last_event_time_utc": locked_at.isoformat(),
                }
            },
        )
        event = self._record_lifecycle_event(
            next_run.recommendation_run_id,
            recommendation_key=next_run.run_key,
            from_status=run.status,
            to_status="locked",
            reason_code=reason_code,
            event_time_utc=locked_at,
            metadata_json={
                "fixture_id": fixture_id,
                "market_type": market_type,
                "outcome": outcome,
                **(metadata_json or {}),
            },
        )
        locked_leg = RecommendationLockedLegRecord(
            recommendation_locked_leg_id=_int(
                locked_leg_row["recommendation_locked_leg_id"]
            ),
            recommendation_run_id=recommendation_run_id,
            fixture_id=fixture_id,
            market_type=market_type,
            outcome=outcome,
            locked_at_utc=locked_at,
            status="locked",
            metadata_json=metadata_json or {},
        )
        return RecommendationLifecycleMutationResult(
            run=next_run,
            event=event,
            locked_leg=locked_leg,
        )

    def release_leg(
        self,
        recommendation_run_id: int,
        *,
        fixture_id: str,
        market_type: str,
        outcome: str,
        released_at_utc: datetime,
        reason_code: str = "user_released_leg",
        metadata_json: dict[str, object] | None = None,
    ) -> RecommendationLifecycleMutationResult:
        run = self._get_run_lifecycle(recommendation_run_id)
        released_at = _aware_utc(released_at_utc)
        release_metadata = {
            "released_at_utc": released_at.isoformat(),
            **(metadata_json or {}),
        }
        locked_leg = _locked_leg_from_row(
            _required_row(
                self.database.fetch_one(
                    UPDATE_RECOMMENDATION_LOCKED_LEG_STATUS_QUERY,
                    {
                        "recommendation_run_id": recommendation_run_id,
                        "fixture_id": fixture_id,
                        "market_type": market_type,
                        "outcome": outcome,
                        "status": "released",
                        "metadata_json": _json(release_metadata),
                    },
                )
            )
        )
        active_locked_legs = [
            _locked_leg_from_row(row)
            for row in self.database.fetch_all(
                LIST_RECOMMENDATION_LOCKED_LEGS_QUERY,
                {"recommendation_run_id": recommendation_run_id},
            )
            if str(row.get("status")) == "locked"
        ]
        next_locked_fixture_ids = _unique(
            locked_leg.fixture_id for locked_leg in active_locked_legs
        )
        next_status: RecommendationLifecycleStatus = (
            "locked" if next_locked_fixture_ids else "current"
        )
        next_run = self._update_run_lifecycle(
            run,
            to_status=next_status,
            locked_fixture_ids=next_locked_fixture_ids,
            explanation_patch={
                "lifecycle": {
                    "last_event": reason_code,
                    "last_event_time_utc": released_at.isoformat(),
                }
            },
        )
        event = self._record_lifecycle_event(
            next_run.recommendation_run_id,
            recommendation_key=next_run.run_key,
            from_status=run.status,
            to_status=next_status,
            reason_code=reason_code,
            event_time_utc=released_at,
            metadata_json={
                "fixture_id": fixture_id,
                "market_type": market_type,
                "outcome": outcome,
                **(metadata_json or {}),
            },
        )
        return RecommendationLifecycleMutationResult(
            run=next_run,
            event=event,
            locked_leg=locked_leg,
        )

    def transition_run_status(
        self,
        recommendation_run_id: int,
        *,
        to_status: RecommendationLifecycleStatus,
        event_time_utc: datetime,
        reason_code: str,
        metadata_json: dict[str, object] | None = None,
    ) -> RecommendationLifecycleMutationResult:
        run = self._get_run_lifecycle(recommendation_run_id)
        event_time = _aware_utc(event_time_utc)
        next_run = self._update_run_lifecycle(
            run,
            to_status=to_status,
            locked_fixture_ids=run.locked_fixture_ids,
            explanation_patch={
                "lifecycle": {
                    "last_event": reason_code,
                    "last_event_time_utc": event_time.isoformat(),
                }
            },
        )
        event = self._record_lifecycle_event(
            next_run.recommendation_run_id,
            recommendation_key=next_run.run_key,
            from_status=run.status,
            to_status=to_status,
            reason_code=reason_code,
            event_time_utc=event_time,
            metadata_json=metadata_json or {},
        )
        return RecommendationLifecycleMutationResult(run=next_run, event=event)

    def _get_run_lifecycle(
        self,
        recommendation_run_id: int,
    ) -> RecommendationRunLifecycleRecord:
        row = _required_row(
            self.database.fetch_one(
                GET_RECOMMENDATION_RUN_QUERY,
                {"recommendation_run_id": recommendation_run_id},
            )
        )
        return _run_lifecycle_from_row(row)

    def _update_run_lifecycle(
        self,
        run: RecommendationRunLifecycleRecord,
        *,
        to_status: RecommendationLifecycleStatus,
        locked_fixture_ids: list[str],
        explanation_patch: dict[str, object],
    ) -> RecommendationRunLifecycleRecord:
        row = _required_row(
            self.database.fetch_one(
                UPDATE_RECOMMENDATION_RUN_LIFECYCLE_QUERY,
                {
                    "recommendation_run_id": run.recommendation_run_id,
                    "status": to_status,
                    "locked_fixture_ids_json": _json(locked_fixture_ids),
                    "explanation_patch_json": _json(explanation_patch),
                },
            )
        )
        return _run_lifecycle_from_row(row)

    def _record_lifecycle_event(
        self,
        recommendation_run_id: int,
        *,
        recommendation_key: str,
        from_status: RecommendationLifecycleStatus,
        to_status: RecommendationLifecycleStatus,
        reason_code: str,
        event_time_utc: datetime,
        metadata_json: dict[str, object],
    ) -> RecommendationLifecycleEventRecord:
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
                {
                    "recommendation_run_id": recommendation_run_id,
                    "recommendation_key": recommendation_key,
                    "from_status": from_status,
                    "to_status": to_status,
                    "reason_code": reason_code,
                    "event_time_utc": event_time_utc,
                    "metadata_json": _json(metadata_json),
                },
            )
        )
        return RecommendationLifecycleEventRecord(
            recommendation_lifecycle_event_id=_int(
                row["recommendation_lifecycle_event_id"]
            ),
            recommendation_run_id=recommendation_run_id,
            recommendation_key=recommendation_key,
            from_status=from_status,
            to_status=to_status,
            reason_code=reason_code,
            event_time_utc=event_time_utc,
            metadata_json=metadata_json,
        )

    def _insert_selected_candidate(
        self,
        recommendation_run_id: int,
        selection: RecommendationSelection,
        index: int,
    ) -> int:
        scored = selection.selected_candidates[index]
        locked_fixture_ids = set(selection.locked_fixture_ids)
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_CANDIDATE_QUERY,
                _selected_candidate_params(
                    scored,
                    recommendation_run_id=recommendation_run_id,
                    locked=scored.candidate.fixture_id in locked_fixture_ids,
                ),
            )
        )
        return _int(row["recommendation_candidate_id"])

    def _insert_candidate_pool_snapshot(
        self,
        recommendation_run_id: int,
        *,
        selection: RecommendationSelection,
        as_of_time_utc: datetime,
        run_key: str,
        source: str,
        candidate_count: int,
        candidate_query_json: dict[str, object],
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_CANDIDATE_POOL_SNAPSHOT_QUERY,
                {
                    "recommendation_run_id": recommendation_run_id,
                    "run_key": run_key,
                    "as_of_time_utc": as_of_time_utc,
                    "strategy": str(
                        selection.explanation_json.get("strategy", "accuracy_first")
                    ),
                    "pass_type": selection.pass_type,
                    "mode": selection.mode,
                    "candidate_count": candidate_count,
                    "selected_candidate_count": len(selection.selected_candidates),
                    "excluded_candidate_count": selection.excluded_candidate_count,
                    "candidate_query_json": _json(candidate_query_json),
                    "source": source,
                },
            )
        )
        return _int(row["recommendation_candidate_pool_snapshot_id"])

    def _insert_candidate_pool_item(
        self,
        recommendation_candidate_pool_snapshot_id: int,
        candidate: RecommendationCandidate,
        *,
        selection: RecommendationSelection,
    ) -> int:
        selected_identities = {
            _candidate_identity(scored.candidate)
            for scored in selection.selected_candidates
        }
        locked_fixture_ids = set(selection.locked_fixture_ids)
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_CANDIDATE_POOL_ITEM_QUERY,
                _candidate_pool_item_params(
                    candidate,
                    recommendation_candidate_pool_snapshot_id=(
                        recommendation_candidate_pool_snapshot_id
                    ),
                    selected=_candidate_identity(candidate) in selected_identities,
                    locked=candidate.fixture_id in locked_fixture_ids,
                ),
            )
        )
        return _int(row["recommendation_candidate_pool_item_id"])

    def _insert_lifecycle_event(
        self,
        recommendation_run_id: int,
        *,
        run_key: str,
        event_time_utc: datetime,
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_LIFECYCLE_EVENT_QUERY,
                {
                    "recommendation_run_id": recommendation_run_id,
                    "recommendation_key": run_key,
                    "from_status": "candidate",
                    "to_status": "current",
                    "reason_code": "recommendation_generated",
                    "event_time_utc": event_time_utc,
                    "metadata_json": _json({"source": "recommendation_engine_v3_1"}),
                },
            )
        )
        return _int(row["recommendation_lifecycle_event_id"])


def _candidate_from_row(row: DatabaseRow) -> RecommendationCandidate:
    upset_score = _optional_float(row.get("upset_score")) or 0.0
    fragility_score = _optional_float(row.get("favorite_fragility_score")) or 0.0
    return RecommendationCandidate(
        fixture_id=str(row["fixture_id"]),
        market_type=_market_type(row["market_type"]),
        outcome=str(row["outcome"]),
        probability=_float(row["probability"]),
        model_probability=_optional_float(row.get("model_probability")),
        calibrated_probability=_optional_float(row.get("calibrated_probability")),
        probability_source=_probability_source(row.get("probability_source")),
        decimal_odds=_optional_float(row.get("decimal_odds")),
        market_probability=_optional_float(row.get("market_probability")),
        model_edge=_optional_float(row.get("model_edge")),
        data_quality_score=_float(row["data_quality_score"]),
        upset_protection_score=max(upset_score, fragility_score),
        line=_optional_float(row.get("line")),
        side=_optional_str(row.get("side")),
        candidate_id=str(row.get("market_prediction_id")),
        model_version=str(row["model_version"]),
        prediction_snapshot_id=_int(row["prediction_snapshot_id"]),
        prediction_time_utc=_datetime(row["prediction_time_utc"]),
        kickoff_time_utc=_datetime(row["kickoff_time_utc"]),
        metadata_json={
            "source": "stored_market_predictions",
            "competition_id": str(row["competition_id"]),
            "market_prediction_id": _int(row["market_prediction_id"]),
            "upset_score": upset_score,
            "favorite_fragility_score": fragility_score,
        },
    )


def _run_lifecycle_from_row(row: DatabaseRow) -> RecommendationRunLifecycleRecord:
    return RecommendationRunLifecycleRecord(
        recommendation_run_id=_int(row["recommendation_run_id"]),
        run_key=str(row["run_key"]),
        status=_lifecycle_status(row["status"]),
        selected_fixture_ids=_string_list(row["selected_fixture_ids_json"]),
        locked_fixture_ids=_string_list(row["locked_fixture_ids_json"]),
        created_at=_datetime(row["created_at"]),
    )


def _locked_leg_from_row(row: DatabaseRow) -> RecommendationLockedLegRecord:
    return RecommendationLockedLegRecord(
        recommendation_locked_leg_id=_int(row["recommendation_locked_leg_id"]),
        recommendation_run_id=_int(row["recommendation_run_id"]),
        fixture_id=str(row["fixture_id"]),
        market_type=str(row["market_type"]),
        outcome=str(row["outcome"]),
        locked_at_utc=_datetime(row["locked_at_utc"]),
        status=str(row["status"]),
        metadata_json=_json_object(row.get("metadata_json")),
    )


def _event_from_row(row: DatabaseRow) -> RecommendationLifecycleEventRecord:
    return RecommendationLifecycleEventRecord(
        recommendation_lifecycle_event_id=_int(
            row["recommendation_lifecycle_event_id"]
        ),
        recommendation_run_id=_int(row["recommendation_run_id"]),
        recommendation_key=str(row["recommendation_key"]),
        from_status=_lifecycle_status(row["from_status"]),
        to_status=_lifecycle_status(row["to_status"]),
        reason_code=str(row["reason_code"]),
        event_time_utc=_datetime(row["event_time_utc"]),
        metadata_json=_json_object(row.get("metadata_json")),
    )


def _run_params(
    selection: RecommendationSelection,
    *,
    as_of_time_utc: datetime,
    run_key: str,
    source: str,
    internal_trace_json: dict[str, object],
) -> QueryParams:
    budget_payload = selection.evaluation.explanation_json.get("budget")
    max_budget = None
    if isinstance(budget_payload, dict):
        max_budget = budget_payload.get("max_budget")
    explanation_json: dict[str, object] = dict(selection.explanation_json)
    if internal_trace_json:
        explanation_json["internal_trace"] = internal_trace_json
    return {
        "run_key": run_key,
        "as_of_time_utc": as_of_time_utc,
        "strategy": str(selection.explanation_json.get("strategy", "accuracy_first")),
        "pass_type": selection.pass_type,
        "mode": selection.mode,
        "status": "current",
        "unit_stake": selection.evaluation.unit_stake,
        "max_budget": max_budget,
        "candidate_count": selection.candidate_count,
        "excluded_candidate_count": selection.excluded_candidate_count,
        "selected_fixture_ids_json": _json(selection.fixture_ids),
        "locked_fixture_ids_json": _json(selection.locked_fixture_ids),
        "total_score": selection.total_score,
        "parlay_evaluation_json": _json(selection.evaluation.model_dump(mode="json")),
        "explanation_json": _json(explanation_json),
        "source": source,
    }


def _selected_candidate_params(
    scored_candidate: ScoredRecommendationCandidate,
    *,
    recommendation_run_id: int,
    locked: bool,
) -> QueryParams:
    candidate = scored_candidate.candidate
    return {
        "recommendation_run_id": recommendation_run_id,
        "fixture_id": candidate.fixture_id,
        "market_type": candidate.market_type,
        "line": candidate.line,
        "side": candidate.side,
        "outcome": candidate.outcome,
        "probability": candidate.probability,
        "model_probability": candidate.raw_model_probability(),
        "calibrated_probability": candidate.calibrated_probability,
        "probability_source": candidate.probability_source,
        "decimal_odds": candidate.decimal_odds,
        "market_probability": candidate.effective_market_probability(),
        "model_edge": candidate.effective_model_edge(),
        "data_quality_score": candidate.data_quality_score,
        "model_confidence_score": candidate.model_confidence_score,
        "calibration_score": candidate.calibration_score,
        "upset_protection_score": candidate.upset_protection_score,
        "odds_stability_score": candidate.odds_stability_score,
        "volatility_penalty": candidate.volatility_penalty,
        "model_version": candidate.model_version,
        "prediction_snapshot_id": candidate.prediction_snapshot_id,
        "prediction_time_utc": candidate.prediction_time_utc,
        "kickoff_time_utc": candidate.kickoff_time_utc,
        "recommendation_score": scored_candidate.score,
        "selected": True,
        "locked": locked,
        "metadata_json": _json(
            {
                **candidate.metadata_json,
                "component_scores": scored_candidate.component_scores,
                "reason_codes": scored_candidate.reason_codes,
            }
        ),
    }


def _candidate_pool_item_params(
    candidate: RecommendationCandidate,
    *,
    recommendation_candidate_pool_snapshot_id: int,
    selected: bool,
    locked: bool,
) -> QueryParams:
    return {
        "recommendation_candidate_pool_snapshot_id": (
            recommendation_candidate_pool_snapshot_id
        ),
        "fixture_id": candidate.fixture_id,
        "market_type": candidate.market_type,
        "line": candidate.line,
        "side": candidate.side,
        "outcome": candidate.outcome,
        "probability": candidate.probability,
        "model_probability": candidate.raw_model_probability(),
        "calibrated_probability": candidate.calibrated_probability,
        "probability_source": candidate.probability_source,
        "decimal_odds": candidate.decimal_odds,
        "market_probability": candidate.effective_market_probability(),
        "model_edge": candidate.effective_model_edge(),
        "data_quality_score": candidate.data_quality_score,
        "model_confidence_score": candidate.model_confidence_score,
        "calibration_score": candidate.calibration_score,
        "upset_protection_score": candidate.upset_protection_score,
        "odds_stability_score": candidate.odds_stability_score,
        "volatility_penalty": candidate.volatility_penalty,
        "model_version": candidate.model_version,
        "prediction_snapshot_id": candidate.prediction_snapshot_id,
        "prediction_time_utc": candidate.prediction_time_utc,
        "kickoff_time_utc": candidate.kickoff_time_utc,
        "selected": selected,
        "locked": locked,
        "metadata_json": _json(candidate.metadata_json),
    }


def _candidate_identity(candidate: RecommendationCandidate) -> tuple[
    str,
    str,
    str,
    float | None,
    str | None,
]:
    return (
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
        candidate.line,
        candidate.side,
    )


def _market_type(value: object) -> RecommendationMarketType:
    text = str(value)
    if text not in {"1x2", "cn_handicap_1x2", "european_handicap_1x2", "correct_score"}:
        raise ValueError(f"unsupported recommendation market type: {text}")
    return text  # type: ignore[return-value]


def _probability_source(value: object) -> RecommendationProbabilitySource:
    text = str(value or "model")
    if text not in {"model", "calibrated"}:
        return "model"
    return text  # type: ignore[return-value]


def _lifecycle_status(value: object) -> RecommendationLifecycleStatus:
    text = str(value)
    if text not in {
        "candidate",
        "current",
        "superseded",
        "locked",
        "confirmed_manual",
        "live",
        "settled",
        "invalidated",
    }:
        raise ValueError(f"unsupported recommendation lifecycle status: {text}")
    return text  # type: ignore[return-value]


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, dict):
            return dict(loaded)
        raise ValueError("expected JSON object")
    if isinstance(value, dict):
        return dict(value)
    raise ValueError(f"expected JSON object, got {type(value).__name__}")


def _json_array(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, str):
        loaded = loads(value)
        if isinstance(loaded, list):
            return list(loaded)
        raise ValueError("expected JSON array")
    if isinstance(value, list | tuple):
        return list(value)
    raise ValueError(f"expected JSON array, got {type(value).__name__}")


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _json_array(value)]


def _append_unique(values: Sequence[str], value: str) -> list[str]:
    result = list(values)
    if value not in result:
        result.append(value)
    return result


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
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
