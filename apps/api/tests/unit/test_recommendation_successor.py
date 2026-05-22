from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations import (
    PersistedRecommendationCandidatePoolSnapshot,
    PersistedRecommendationLockedLegSnapshot,
    PersistedRecommendationRunSnapshot,
    RecommendationCandidate,
    RecommendationGenerationOptions,
    RecommendationGenerationResult,
    RecommendationSuccessorRecomputeOptions,
    ScoredRecommendationCandidate,
    StoredRecommendationRun,
    run_recommendation_successor_recompute,
)
from nutmeg.recommendations.models import RecommendationSelection


class FakeSuccessorReplayRepository:
    def __init__(self, snapshots: Sequence[PersistedRecommendationRunSnapshot]) -> None:
        self.snapshots = list(snapshots)
        self.options: object | None = None

    def list_snapshots(self, *, options: object) -> list[PersistedRecommendationRunSnapshot]:
        self.options = options
        return self.snapshots


class FakeSuccessorDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected query: {query}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected query: {query}")


def test_successor_recompute_preserves_exact_locked_leg_and_generates_continuation() -> None:
    snapshot = _snapshot(
        selected_fixture_ids=["A", "B", "C", "D"],
        locked_fixture_ids=["A"],
        candidate_pool=[
            _candidate("A", "home_win", probability=0.55),
            _candidate("A", "away_win", probability=0.61),
            _candidate("B", "home_win", probability=0.62),
            _candidate("C", "home_win", probability=0.63),
            _candidate("D", "home_win", probability=0.64),
            _candidate("E", "home_win", probability=0.65),
        ],
        locked_legs=[
            PersistedRecommendationLockedLegSnapshot(
                recommendation_locked_leg_id=401,
                recommendation_run_id=77,
                fixture_id="A",
                market_type="1x2",
                outcome="away_win",
                locked_at_utc=_dt(2026, 5, 1, 11),
                status="locked",
                metadata_json={},
            )
        ],
    )
    generation_calls: list[RecommendationGenerationOptions] = []

    def fake_generation_runner(
        database: object,
        options: RecommendationGenerationOptions,
        repository: object | None,
    ) -> RecommendationGenerationResult:
        generation_calls.append(options)
        assert repository is not None
        selected = [
            ScoredRecommendationCandidate(candidate=options.locked_candidates[0], score=0.80),
            ScoredRecommendationCandidate(candidate=_candidate("C", "home_win"), score=0.79),
            ScoredRecommendationCandidate(candidate=_candidate("D", "home_win"), score=0.78),
            ScoredRecommendationCandidate(candidate=_candidate("E", "home_win"), score=0.77),
        ]
        return RecommendationGenerationResult(
            dry_run=False,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=6,
            generated_count=1,
            selection=_selection(selected, pass_type=options.pass_type),
            stored_run=StoredRecommendationRun(
                recommendation_run_id=88,
                created_at=options.as_of_time_utc,
            ),
        )

    result = run_recommendation_successor_recompute(
        FakeSuccessorDatabase(),
        options=RecommendationSuccessorRecomputeOptions(
            source_recommendation_run_id=77,
            as_of_time_utc=_dt(2026, 5, 2, 9),
            pass_type="4x1",
            max_budget=12,
            excluded_fixture_ids=("B",),
            dry_run=False,
        ),
        replay_repository=FakeSuccessorReplayRepository([snapshot]),  # type: ignore[arg-type]
        recommendation_repository=object(),  # type: ignore[arg-type]
        generation_runner=fake_generation_runner,  # type: ignore[arg-type]
    )

    assert result.generated_recommendation_run_id == 88
    assert result.locked_fixture_ids == ["A"]
    assert result.continuation_fixture_ids == ["C", "D", "E"]
    assert result.source_selected_fixture_ids == ["A", "B", "C", "D"]
    assert generation_calls[0].pass_type == "4x1"
    assert generation_calls[0].max_budget == 12
    assert generation_calls[0].excluded_fixture_ids == ("B",)
    assert generation_calls[0].locked_candidates[0].fixture_id == "A"
    assert generation_calls[0].locked_candidates[0].outcome == "away_win"
    assert generation_calls[0].internal_trace_json["successor_recompute"] == {
        "source_recommendation_run_id": 77,
        "source_run_key": "run-77",
        "source_selected_fixture_ids": ["A", "B", "C", "D"],
        "locked_fixture_ids": ["A"],
        "excluded_fixture_ids": ["B"],
        "calculation_basis": "locked_leg_successor_recompute_v3_1",
    }


def test_successor_recompute_returns_warning_when_source_run_missing() -> None:
    result = run_recommendation_successor_recompute(
        FakeSuccessorDatabase(),
        options=RecommendationSuccessorRecomputeOptions(
            source_recommendation_run_id=77,
            as_of_time_utc=_dt(2026, 5, 2, 9),
        ),
        replay_repository=FakeSuccessorReplayRepository([]),  # type: ignore[arg-type]
    )

    assert result.generation_result is None
    assert result.warnings == ["source_recommendation_run_not_found"]


def _snapshot(
    *,
    selected_fixture_ids: list[str],
    locked_fixture_ids: list[str],
    candidate_pool: list[RecommendationCandidate],
    locked_legs: list[PersistedRecommendationLockedLegSnapshot],
) -> PersistedRecommendationRunSnapshot:
    return PersistedRecommendationRunSnapshot(
        recommendation_run_id=77,
        run_key="run-77",
        as_of_time_utc=_dt(2026, 5, 1, 10),
        strategy="accuracy_first",
        pass_type="6x1",
        mode="single",
        status="locked",
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
        locked_legs=locked_legs,
        candidate_pool_snapshot=PersistedRecommendationCandidatePoolSnapshot(
            recommendation_candidate_pool_snapshot_id=701,
            recommendation_run_id=77,
            run_key="run-77",
            as_of_time_utc=_dt(2026, 5, 1, 10),
            strategy="accuracy_first",
            pass_type="6x1",
            mode="single",
            candidate_count=len(candidate_pool),
            selected_candidate_count=len(selected_fixture_ids),
            excluded_candidate_count=0,
            candidate_query_json={
                "allowed_markets": ["1x2"],
                "min_probability": 0.20,
                "min_data_quality_score": 50,
                "require_odds": True,
                "competition_id": "BENCH_V3",
                "model_version": "poisson-v3.1-baseline",
            },
            source="unit-test",
            created_at=_dt(2026, 5, 1, 10),
        ),
        candidate_pool_candidates=candidate_pool,
    )


def _selection(
    selected_candidates: list[ScoredRecommendationCandidate],
    *,
    pass_type: str,
) -> RecommendationSelection:
    return RecommendationSelection(
        pass_type=pass_type,
        mode="single",
        selected_candidates=selected_candidates,
        evaluation=ParlayEvaluation(
            pass_type=pass_type,
            unit_stake=2,
            total_atomic_bets=1,
            total_stake=2,
            hit_probability=0.22,
            expected_payout=28.0,
            expected_value=4.0,
            roi=2.0,
            risk_score=0.55,
            risk_level="medium",
            explanation_json={"budget": {"max_budget": 12, "within_budget": True}},
        ),
        total_score=0.78,
        locked_fixture_ids=["A"],
        candidate_count=6,
        excluded_candidate_count=1,
        explanation_json={"strategy": "accuracy_first"},
    )


def _candidate(
    fixture_id: str,
    outcome: str,
    *,
    probability: float = 0.62,
) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome=outcome,
        probability=probability,
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


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
