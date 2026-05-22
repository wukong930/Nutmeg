from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.parlay import ParlayEvaluation
from nutmeg.recommendations.baseline_seed import RecommendationBaselineSeedResult
from nutmeg.recommendations.chain_integrity import (
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationChainRunNode,
    build_recommendation_chain_integrity_report,
)
from nutmeg.recommendations.global_planner import (
    RecommendationGlobalPlannerOptions,
    RecommendationGlobalPlannerResult,
    RecommendationGlobalPlanOption,
)
from nutmeg.recommendations.lifecycle import RecommendationLifecycleStatus
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationSelection,
    ScoredRecommendationCandidate,
)
from nutmeg.recommendations.persisted_lifecycle_smoke import (
    RecommendationPersistedLifecycleSmokeOptions,
    _options_from_args,
    _parse_args,
    run_recommendation_persisted_lifecycle_smoke,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationLifecycleEventRecord,
    RecommendationLifecycleMutationResult,
    RecommendationLockedLegRecord,
    RecommendationRunLifecycleRecord,
    StoredRecommendationRun,
)
from nutmeg.recommendations.source_status_sync import (
    RecommendationSourceStatusSyncOptions,
    RecommendationSourceStatusSyncRunResult,
)
from nutmeg.recommendations.successor import (
    RecommendationSuccessorRecomputeOptions,
    RecommendationSuccessorRecomputeRunResult,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationOptions,
    RecommendationSuccessorChainEvaluationResult,
    build_recommendation_successor_chain_evaluation_result,
)


def test_persisted_lifecycle_smoke_safe_default_requires_commit() -> None:
    result = run_recommendation_persisted_lifecycle_smoke(
        FakeDatabase(),
        options=RecommendationPersistedLifecycleSmokeOptions(
            as_of_time_utc=_dt(2026, 5, 12, 0),
        ),
    )

    assert result.dry_run is True
    assert result.executed is False
    assert result.passed is False
    assert result.warnings == ["persisted_lifecycle_smoke_requires_commit"]
    assert result.summary_json["calculation_basis"] == (
        "recommendation_persisted_lifecycle_smoke_v3_1"
    )


def test_persisted_lifecycle_smoke_commit_runs_real_lifecycle_steps() -> None:
    database = FakeDatabase()
    repository = FakeRecommendationRepository()
    seed_runner = FakeSeedRunner()
    global_runner = FakeGlobalPlannerRunner()
    successor_runner = FakeSuccessorRunner()
    source_sync_runner = FakeSourceSyncRunner()
    chain_runner = FakeSuccessorChainRunner()

    result = run_recommendation_persisted_lifecycle_smoke(
        database,
        options=RecommendationPersistedLifecycleSmokeOptions(
            as_of_time_utc=_dt(2026, 5, 12, 0),
            pass_type="4x1",
            mode="single",
            dry_run=False,
        ),
        seed_runner=seed_runner,
        global_planner_runner=global_runner,
        successor_runner=successor_runner,
        source_sync_runner=source_sync_runner,
        successor_chain_runner=chain_runner,
        repository=cast(PostgresRecommendationRepository, repository),
    )

    assert result.passed is True
    assert result.executed is True
    assert result.source_recommendation_run_id == 101
    assert result.successor_recommendation_run_id == 102
    assert result.locked_fixture_ids == ["bench_v3_001"]
    assert result.continuation_fixture_ids == [
        "bench_v3_003",
        "bench_v3_004",
        "bench_v3_005",
    ]
    assert result.summary_json["source_status_synced"] is True
    assert seed_runner.called is True
    assert global_runner.options is not None
    assert global_runner.options.dry_run is False
    assert global_runner.options.pass_types == ("4x1",)
    assert successor_runner.options is not None
    assert successor_runner.options.source_recommendation_run_id == 101
    assert successor_runner.options.dry_run is False
    assert source_sync_runner.options is not None
    assert source_sync_runner.options.dry_run is False
    assert chain_runner.options is not None
    assert chain_runner.options.max_source_status_sync_required_count == 0
    assert repository.lock_calls == [
        {
            "recommendation_run_id": 101,
            "fixture_id": "bench_v3_001",
            "market_type": "1x2",
            "outcome": "home_win",
            "locked_at_utc": _dt(2026, 5, 12, 12),
            "reason_code": "persisted_lifecycle_smoke_locked_leg",
        }
    ]


def test_persisted_lifecycle_smoke_cli_maps_commit_options() -> None:
    args = _parse_args(
        [
            "--as-of-time-utc",
            "2026-05-12T00:00:00Z",
            "--profile",
            "mixed_outcomes",
            "--pass-type",
            "6x1",
            "--mode",
            "multiple",
            "--strategy",
            "value_first",
            "--unit-stake",
            "3",
            "--no-max-budget",
            "--min-probability",
            "0.25",
            "--min-data-quality-score",
            "70",
            "--candidate-limit",
            "120",
            "--no-require-odds",
            "--competition-id",
            "BENCH_ALT",
            "--model-version",
            "poisson-alt",
            "--lock-offset-hours",
            "10",
            "--successor-offset-hours",
            "22",
            "--window-padding-hours",
            "2",
            "--no-seed-reset",
            "--commit",
            "--output-path",
            "tmp/persisted_lifecycle.json",
        ]
    )

    options = _options_from_args(args)

    assert options.as_of_time_utc == _dt(2026, 5, 12, 0)
    assert options.profile == "mixed_outcomes"
    assert options.pass_type == "6x1"
    assert options.mode == "multiple"
    assert options.strategy == "value_first"
    assert options.unit_stake == 3
    assert options.max_budget is None
    assert options.min_probability == 0.25
    assert options.min_data_quality_score == 70
    assert options.candidate_limit == 120
    assert options.require_odds is False
    assert options.competition_id == "BENCH_ALT"
    assert options.model_version == "poisson-alt"
    assert options.lock_offset_hours == 10
    assert options.successor_offset_hours == 22
    assert options.window_padding_hours == 2
    assert options.reset_seed is False
    assert options.dry_run is False
    assert str(args.output_path) == "tmp/persisted_lifecycle.json"


class FakeDatabase:
    def execute(self, query: str, params: QueryParams) -> None:
        raise AssertionError(f"unexpected query: {query}, {params}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected query: {query}, {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected query: {query}, {params}")


class FakeSeedRunner:
    def __init__(self) -> None:
        self.called = False

    def __call__(
        self,
        database: object,
        *,
        options: object | None = None,
    ) -> RecommendationBaselineSeedResult:
        self.called = True
        return RecommendationBaselineSeedResult(
            as_of_time_utc=_dt(2026, 5, 12, 0),
            reset=True,
            profile="happy_path",
            competition_id="BENCH_V3",
            fixture_count=8,
            fixture_ids=[f"bench_v3_00{index}" for index in range(1, 9)],
            odds_snapshot_count=24,
            result_count=8,
        )


class FakeGlobalPlannerRunner:
    def __init__(self) -> None:
        self.options: RecommendationGlobalPlannerOptions | None = None

    def __call__(
        self,
        database: object,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: PostgresRecommendationRepository | None = None,
    ) -> RecommendationGlobalPlannerResult:
        self.options = options
        selection = _selection()
        option = RecommendationGlobalPlanOption(
            option_key="single_parlay:4x1:single",
            option_type="single_parlay",
            pass_type="4x1",
            mode="single",
            planner_score=0.84,
            within_budget=True,
            selection=selection,
        )
        return RecommendationGlobalPlannerResult(
            dry_run=False,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=8,
            evaluated_option_count=1,
            generated_option_count=1,
            best_option=option,
            stored_run=StoredRecommendationRun(
                recommendation_run_id=101,
                created_at=options.as_of_time_utc,
            ),
        )


class FakeRecommendationRepository:
    def __init__(self) -> None:
        self.lock_calls: list[dict[str, object]] = []

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
        self.lock_calls.append(
            {
                "recommendation_run_id": recommendation_run_id,
                "fixture_id": fixture_id,
                "market_type": market_type,
                "outcome": outcome,
                "locked_at_utc": locked_at_utc,
                "reason_code": reason_code,
            }
        )
        return _mutation(
            recommendation_run_id,
            status="locked",
            reason_code=reason_code,
            event_time_utc=locked_at_utc,
        )


class FakeSuccessorRunner:
    def __init__(self) -> None:
        self.options: RecommendationSuccessorRecomputeOptions | None = None

    def __call__(
        self,
        database: object,
        *,
        options: RecommendationSuccessorRecomputeOptions,
        recommendation_repository: PostgresRecommendationRepository | None = None,
    ) -> RecommendationSuccessorRecomputeRunResult:
        self.options = options
        return RecommendationSuccessorRecomputeRunResult(
            dry_run=False,
            as_of_time_utc=options.as_of_time_utc,
            source_recommendation_run_id=options.source_recommendation_run_id,
            source_run_key="source-101",
            source_selected_fixture_ids=[
                "bench_v3_001",
                "bench_v3_002",
                "bench_v3_003",
                "bench_v3_004",
            ],
            locked_fixture_ids=["bench_v3_001"],
            continuation_fixture_ids=[
                "bench_v3_003",
                "bench_v3_004",
                "bench_v3_005",
            ],
            generated_recommendation_run_id=102,
        )


class FakeSourceSyncRunner:
    def __init__(self) -> None:
        self.options: RecommendationSourceStatusSyncOptions | None = None

    def __call__(
        self,
        database: object,
        *,
        options: RecommendationSourceStatusSyncOptions,
    ) -> RecommendationSourceStatusSyncRunResult:
        self.options = options
        return RecommendationSourceStatusSyncRunResult(
            dry_run=False,
            blocked=False,
            report=_chain_report(source_status="locked"),
            synced_source_recommendation_run_ids=[101],
            summary_json={"synced_source_count": 1},
        )


class FakeSuccessorChainRunner:
    def __init__(self) -> None:
        self.options: RecommendationSuccessorChainEvaluationOptions | None = None

    def __call__(
        self,
        repository: object,
        *,
        options: RecommendationSuccessorChainEvaluationOptions,
    ) -> RecommendationSuccessorChainEvaluationResult:
        self.options = options
        return build_recommendation_successor_chain_evaluation_result(
            _chain_report(source_status="superseded"),
            options=options,
        )


def _selection() -> RecommendationSelection:
    selected = [
        ScoredRecommendationCandidate(
            candidate=_candidate(f"bench_v3_00{index}"),
            score=0.90 - index / 100,
        )
        for index in range(1, 5)
    ]
    return RecommendationSelection(
        pass_type="4x1",
        mode="single",
        selected_candidates=selected,
        evaluation=ParlayEvaluation(
            pass_type="4x1",
            unit_stake=2,
            total_atomic_bets=1,
            total_stake=2,
            hit_probability=0.26,
            expected_payout=24,
            expected_value=3,
            roi=1.5,
            risk_score=0.48,
            risk_level="medium",
            explanation_json={"budget": {"max_budget": 20, "within_budget": True}},
        ),
        total_score=0.82,
        candidate_count=8,
        excluded_candidate_count=0,
        explanation_json={"strategy": "accuracy_first"},
    )


def _candidate(fixture_id: str) -> RecommendationCandidate:
    return RecommendationCandidate(
        fixture_id=fixture_id,
        market_type="1x2",
        outcome="home_win",
        probability=0.62,
        decimal_odds=1.90,
        market_probability=0.52,
        data_quality_score=90,
        model_confidence_score=0.85,
        calibration_score=0.82,
        model_version="poisson-v3.1-baseline",
        prediction_snapshot_id=100,
        prediction_time_utc=_dt(2026, 5, 12, 0),
        kickoff_time_utc=_dt(2026, 5, 12, 18),
    )


def _mutation(
    recommendation_run_id: int,
    *,
    status: str,
    reason_code: str,
    event_time_utc: datetime,
) -> RecommendationLifecycleMutationResult:
    return RecommendationLifecycleMutationResult(
        run=RecommendationRunLifecycleRecord(
            recommendation_run_id=recommendation_run_id,
            run_key=f"run-{recommendation_run_id}",
            status=cast(RecommendationLifecycleStatus, status),
            selected_fixture_ids=["bench_v3_001", "bench_v3_002"],
            locked_fixture_ids=["bench_v3_001"],
            created_at=_dt(2026, 5, 12, 0),
        ),
        event=RecommendationLifecycleEventRecord(
            recommendation_lifecycle_event_id=501,
            recommendation_run_id=recommendation_run_id,
            recommendation_key=f"run-{recommendation_run_id}",
            from_status="current",
            to_status=cast(RecommendationLifecycleStatus, status),
            reason_code=reason_code,
            event_time_utc=event_time_utc,
        ),
        locked_leg=RecommendationLockedLegRecord(
            recommendation_locked_leg_id=601,
            recommendation_run_id=recommendation_run_id,
            fixture_id="bench_v3_001",
            market_type="1x2",
            outcome="home_win",
            locked_at_utc=event_time_utc,
            status="locked",
        ),
    )


def _chain_report(*, source_status: str) -> RecommendationChainIntegrityReport:
    return build_recommendation_chain_integrity_report(
        [
            _node(101, run_key="source-101", status=source_status),
            _node(102, run_key="successor-102", source_recommendation_run_id=101),
        ],
        options=RecommendationChainIntegrityOptions(
            window_start_utc=_dt(2026, 5, 11, 23),
            window_end_utc=_dt(2026, 5, 12, 20),
            pass_type="4x1",
            mode="single",
            strategy="accuracy_first",
        ),
    )


def _node(
    recommendation_run_id: int,
    *,
    run_key: str,
    status: str = "current",
    source_recommendation_run_id: int | None = None,
) -> RecommendationChainRunNode:
    return RecommendationChainRunNode(
        recommendation_run_id=recommendation_run_id,
        run_key=run_key,
        as_of_time_utc=(
            _dt(2026, 5, 12, 0)
            if source_recommendation_run_id is None
            else _dt(2026, 5, 12, 19)
        ),
        strategy="accuracy_first",
        pass_type="4x1",
        mode="single",
        status=status,
        selected_fixture_ids=[
            "bench_v3_001",
            "bench_v3_003",
            "bench_v3_004",
            "bench_v3_005",
        ],
        locked_fixture_ids=["bench_v3_001"],
        source_recommendation_run_id=source_recommendation_run_id,
        source_run_key="source-101" if source_recommendation_run_id else None,
        created_at=_dt(2026, 5, 12, 0),
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
