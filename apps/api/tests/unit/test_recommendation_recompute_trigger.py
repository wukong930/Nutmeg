from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PersistedRecommendationCandidatePoolSnapshot,
    PersistedRecommendationRunSnapshot,
    RecommendationCandidate,
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    RecommendationProviderIncidentEventRecord,
    RecommendationRecomputeTriggerOptions,
    StoredRecommendationRun,
    run_recommendation_recompute_trigger,
)
from nutmeg.recommendations.recompute_trigger import (
    INSERT_RECOMMENDATION_RECOMPUTE_TRIGGER_RUN_QUERY,
)


class FakeReplayRepository:
    def __init__(self, snapshots: Sequence[PersistedRecommendationRunSnapshot]) -> None:
        self.snapshots = list(snapshots)

    def list_snapshots(self, *, options: object) -> list[PersistedRecommendationRunSnapshot]:
        return self.snapshots


class FakeIncidentRepository:
    def __init__(self, incidents: Sequence[RecommendationProviderIncidentEventRecord]) -> None:
        self.incidents = list(incidents)

    def list_events(self, *, options: object) -> list[RecommendationProviderIncidentEventRecord]:
        return self.incidents


class FakeRecomputeDatabase:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == INSERT_RECOMMENDATION_RECOMPUTE_TRIGGER_RUN_QUERY:
            return {
                "recommendation_recompute_trigger_run_id": 901,
                "created_at": _dt(2026, 5, 1, 13),
                "updated_at": _dt(2026, 5, 1, 13),
            }
        raise AssertionError(f"unexpected query: {query}")


def test_recompute_trigger_preserves_locked_leg_and_excludes_incident_fixture() -> None:
    snapshot = _snapshot(
        selected_fixture_ids=["A", "B"],
        locked_fixture_ids=["A"],
        candidate_pool=[
            _candidate("A", "home_win"),
            _candidate("B", "home_win"),
            _candidate("C", "away_win"),
        ],
    )
    incident = _incident(
        "incident-B",
        fixture_id="B",
        severity="critical",
        excluded_fixture_ids=["B"],
    )
    generation_calls: list[RecommendationGenerationOptions] = []

    def fake_generation_runner(
        database: object,
        options: RecommendationGenerationOptions,
        repository: object | None,
    ) -> RecommendationGenerationResult:
        generation_calls.append(options)
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=3,
            generated_count=1,
        )

    result = run_recommendation_recompute_trigger(
        FakeRecomputeDatabase(),
        options=_options(),
        replay_repository=FakeReplayRepository([snapshot]),  # type: ignore[arg-type]
        incident_repository=FakeIncidentRepository([incident]),  # type: ignore[arg-type]
        generation_runner=fake_generation_runner,  # type: ignore[arg-type]
    )

    assert result.checked_run_count == 1
    assert result.triggered_run_count == 1
    assert result.skipped_run_count == 0
    assert result.decisions[0].action == "triggered"
    assert result.decisions[0].affected_fixture_ids == ["B"]
    assert result.decisions[0].excluded_fixture_ids == ["B"]
    assert result.decisions[0].locked_fixture_ids == ["A"]
    assert "critical_provider_incident" in result.decisions[0].reason_codes
    assert generation_calls[0].locked_candidates[0].fixture_id == "A"
    assert generation_calls[0].excluded_fixture_ids == ("B",)
    assert generation_calls[0].internal_trace_json["recompute_trigger"] == {
        "source_recommendation_run_id": 77,
        "source_run_key": "run-77",
        "incident_event_keys": ["incident-B"],
        "excluded_fixture_ids": ["B"],
        "locked_fixture_ids": ["A"],
    }


def test_recompute_trigger_skips_when_incident_does_not_affect_run() -> None:
    snapshot = _snapshot(
        selected_fixture_ids=["A", "B"],
        locked_fixture_ids=[],
        candidate_pool=[_candidate("A", "home_win"), _candidate("B", "home_win")],
    )
    incident = _incident(
        "incident-Z",
        fixture_id="Z",
        severity="critical",
        excluded_fixture_ids=["Z"],
    )
    generation_called = False

    def fake_generation_runner(
        database: object,
        options: RecommendationGenerationOptions,
        repository: object | None,
    ) -> RecommendationGenerationResult:
        nonlocal generation_called
        generation_called = True
        return RecommendationGenerationResult(
            dry_run=True,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=0,
            generated_count=0,
        )

    result = run_recommendation_recompute_trigger(
        FakeRecomputeDatabase(),
        options=_options(),
        replay_repository=FakeReplayRepository([snapshot]),  # type: ignore[arg-type]
        incident_repository=FakeIncidentRepository([incident]),  # type: ignore[arg-type]
        generation_runner=fake_generation_runner,  # type: ignore[arg-type]
    )

    assert generation_called is False
    assert result.triggered_run_count == 0
    assert result.skipped_run_count == 1
    assert result.decisions[0].reason_codes == ["no_active_incident_affects_source_run"]


def test_recompute_trigger_generates_locked_successor_without_incident_when_enabled() -> None:
    snapshot = _snapshot(
        selected_fixture_ids=["A", "B"],
        locked_fixture_ids=["A"],
        candidate_pool=[_candidate("A", "home_win"), _candidate("B", "home_win")],
    )
    generation_calls: list[RecommendationGenerationOptions] = []

    def fake_generation_runner(
        database: object,
        options: RecommendationGenerationOptions,
        repository: object | None,
    ) -> RecommendationGenerationResult:
        generation_calls.append(options)
        assert repository is not None
        return RecommendationGenerationResult(
            dry_run=False,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=2,
            generated_count=1,
            stored_run=StoredRecommendationRun(
                recommendation_run_id=89,
                created_at=options.as_of_time_utc,
            ),
        )

    result = run_recommendation_recompute_trigger(
        FakeRecomputeDatabase(),
        options=_options(dry_run=False, trigger_locked_successors=True),
        replay_repository=FakeReplayRepository([snapshot]),  # type: ignore[arg-type]
        incident_repository=FakeIncidentRepository([]),  # type: ignore[arg-type]
        recommendation_repository=object(),  # type: ignore[arg-type]
        generation_runner=fake_generation_runner,  # type: ignore[arg-type]
    )

    assert result.checked_run_count == 1
    assert result.triggered_run_count == 1
    assert result.skipped_run_count == 0
    assert result.generated_recommendation_run_ids == [89]
    assert result.decisions[0].reason_codes == [
        "locked_successor_recompute",
        "locked_fixtures_preserved",
    ]
    assert result.decisions[0].incident_event_keys == []
    assert generation_calls[0].locked_candidates[0].fixture_id == "A"
    assert generation_calls[0].internal_trace_json["successor_recompute"] == {
        "source_recommendation_run_id": 77,
        "source_run_key": "run-77",
        "source_selected_fixture_ids": ["A", "B"],
        "locked_fixture_ids": ["A"],
        "calculation_basis": "locked_leg_successor_recompute_v3_1",
    }


def test_recompute_trigger_persists_audit_when_not_dry_run() -> None:
    database = FakeRecomputeDatabase()
    snapshot = _snapshot(
        selected_fixture_ids=["A", "B"],
        locked_fixture_ids=[],
        candidate_pool=[_candidate("A", "home_win"), _candidate("B", "home_win")],
    )
    incident = _incident(
        "incident-A",
        fixture_id="A",
        severity="critical",
        excluded_fixture_ids=["A"],
    )

    def fake_generation_runner(
        database: object,
        options: RecommendationGenerationOptions,
        repository: object | None,
    ) -> RecommendationGenerationResult:
        return RecommendationGenerationResult(
            dry_run=False,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=3,
            generated_count=1,
            stored_run=StoredRecommendationRun(
                recommendation_run_id=88,
                created_at=options.as_of_time_utc,
            ),
        )

    result = run_recommendation_recompute_trigger(
        database,
        options=_options(dry_run=False),
        replay_repository=FakeReplayRepository([snapshot]),  # type: ignore[arg-type]
        incident_repository=FakeIncidentRepository([incident]),  # type: ignore[arg-type]
        recommendation_repository=object(),  # type: ignore[arg-type]
        generation_runner=fake_generation_runner,  # type: ignore[arg-type]
    )

    assert result.generated_recommendation_run_ids == [88]
    assert result.stored_trigger_run is not None
    assert result.stored_trigger_run.recommendation_recompute_trigger_run_id == 901
    query, params = database.fetch_one_calls[0]
    assert query == INSERT_RECOMMENDATION_RECOMPUTE_TRIGGER_RUN_QUERY
    assert params["triggered_run_count"] == 1
    assert params["generated_recommendation_run_ids_json"] == "[88]"
    assert "incident-A" in str(params["incident_event_keys_json"])


def _options(
    *,
    dry_run: bool = True,
    trigger_locked_successors: bool = False,
) -> RecommendationRecomputeTriggerOptions:
    return RecommendationRecomputeTriggerOptions(
        as_of_time_utc=_dt(2026, 5, 1, 12),
        lookback_hours=24,
        dry_run=dry_run,
        trigger_locked_successors=trigger_locked_successors,
    )


def _snapshot(
    *,
    selected_fixture_ids: list[str],
    locked_fixture_ids: list[str],
    candidate_pool: list[RecommendationCandidate],
) -> PersistedRecommendationRunSnapshot:
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=77,
        run_key="run-77",
        as_of_time_utc=_dt(2026, 5, 1, 10),
        strategy="accuracy_first",
        pass_type="2x1",
        mode="single",
        status="current",
        unit_stake=2.0,
        max_budget=20.0,
        candidate_count=len(candidate_pool),
        excluded_candidate_count=0,
        selected_fixture_ids=selected_fixture_ids,
        locked_fixture_ids=locked_fixture_ids,
        source="unit-test",
        created_at=_dt(2026, 5, 1, 10),
        selected_candidates=[
            candidate
            for candidate in candidate_pool
            if candidate.fixture_id in selected_fixture_ids
        ],
        candidate_pool_snapshot=PersistedRecommendationCandidatePoolSnapshot(
            recommendation_candidate_pool_snapshot_id=701,
            recommendation_run_id=77,
            run_key="run-77",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            strategy="accuracy_first",
            pass_type="2x1",
            mode="single",
            candidate_count=len(candidate_pool),
            selected_candidate_count=len(selected_fixture_ids),
            excluded_candidate_count=0,
            candidate_query_json={
                "allowed_markets": ["1x2"],
                "min_probability": 0.20,
                "min_data_quality_score": 50,
                "require_odds": True,
            },
            source="unit-test",
            created_at=_dt(2026, 5, 1, 10),
        ),
        candidate_pool_candidates=candidate_pool,
    )


def _candidate(fixture_id: str, outcome: str) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=0.62,
        decimal_odds=1.85,
        market_probability=0.54,
        data_quality_score=88,
        model_confidence_score=0.82,
        calibration_score=0.80,
        model_version="poisson-m1.0.0",
        prediction_snapshot_id=901,
        prediction_time_utc=_dt(2026, 5, 1, 9),
        kickoff_time_utc=_dt(2026, 5, 2, 18),
    )


def _incident(
    key: str,
    *,
    fixture_id: str,
    severity: str,
    excluded_fixture_ids: list[str],
) -> RecommendationProviderIncidentEventRecord:
    return RecommendationProviderIncidentEventRecord(
        recommendation_provider_incident_event_id=601,
        provider_incident_key=key,
        provider_name="sportmonks",
        fixture_id=fixture_id,
        competition_id="EPL",
        incident_type="player_availability_injured",
        severity=severity,  # type: ignore[arg-type]
        event_time_utc=_dt(2026, 5, 1, 11),
        observed_at_utc=_dt(2026, 5, 1, 11),
        status="open",
        affects_recommendations=True,
        excluded_fixture_ids=excluded_fixture_ids,
        summary="player injured",
        created_at=_dt(2026, 5, 1, 11),
        updated_at=_dt(2026, 5, 1, 11),
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
