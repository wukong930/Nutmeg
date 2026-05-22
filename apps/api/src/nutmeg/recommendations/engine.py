from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
    RecommendationMode,
    RecommendationSelection,
    RecommendationStrategy,
)
from nutmeg.recommendations.optimizer import (
    select_budget_constrained_multiple_parlay,
    select_budget_constrained_single_parlay,
)
from nutmeg.recommendations.policy import (
    build_recommendation_policy_config,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationCandidateQueryOptions,
    RecommendationDatabaseExecutor,
    StoredRecommendationRun,
)


class RecommendationGenerationOptions(BaseModel):
    as_of_time_utc: datetime
    pass_type: str = "2x1"
    mode: RecommendationMode = "single"
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    allowed_markets: tuple[RecommendationMarketType, ...] = (
        "1x2",
        "cn_handicap_1x2",
        "european_handicap_1x2",
        "correct_score",
    )
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_model_edge: float | None = None
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=200, ge=1, le=2_000)
    require_odds: bool = True
    max_outcomes_per_fixture: int = Field(default=2, ge=1, le=3)
    min_marginal_quality_gain: float = 0.0
    fixture_ids: tuple[str, ...] = ()
    excluded_fixture_ids: tuple[str, ...] = ()
    locked_candidates: tuple[RecommendationCandidate, ...] = ()
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    dry_run: bool = True
    internal_trace_json: dict[str, object] = Field(default_factory=dict)


class RecommendationGenerationResult(BaseModel):
    dry_run: bool
    as_of_time_utc: datetime
    candidate_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    selection: RecommendationSelection | None = None
    stored_run: StoredRecommendationRun | None = None
    warnings: list[str] = Field(default_factory=list)


def run_recommendation_generation(
    database: RecommendationDatabaseExecutor,
    *,
    options: RecommendationGenerationOptions,
    repository: PostgresRecommendationRepository | None = None,
) -> RecommendationGenerationResult:
    reader = PostgresRecommendationRepository(database)
    candidates = reader.list_candidates(
        options=RecommendationCandidateQueryOptions(
            as_of_time_utc=options.as_of_time_utc,
            allowed_markets=options.allowed_markets,
            min_probability=options.min_probability,
            min_model_edge=options.min_model_edge,
            min_data_quality_score=options.min_data_quality_score,
            require_odds=options.require_odds,
            candidate_limit=options.candidate_limit,
            fixture_ids=options.fixture_ids,
            competition_id=options.competition_id,
            model_version=options.model_version,
        )
    )
    if options.excluded_fixture_ids:
        excluded_fixture_ids = set(options.excluded_fixture_ids)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.fixture_id not in excluded_fixture_ids
        ]
    warnings: list[str] = []
    policy_config = build_recommendation_policy_config(
        strategy=options.strategy,
        allowed_markets=options.allowed_markets,
        min_probability=options.min_probability,
        min_model_edge=options.min_model_edge,
        min_data_quality_score=options.min_data_quality_score,
        require_odds=options.require_odds,
    )
    try:
        if options.mode == "multiple":
            selection = select_budget_constrained_multiple_parlay(
                candidates,
                pass_type=options.pass_type,
                unit_stake=options.unit_stake,
                max_budget=options.max_budget,
                config=policy_config,
                as_of_time_utc=options.as_of_time_utc,
                locked_candidates=options.locked_candidates,
                max_outcomes_per_fixture=options.max_outcomes_per_fixture,
                min_marginal_quality_gain=options.min_marginal_quality_gain,
            )
        else:
            selection = select_budget_constrained_single_parlay(
                candidates,
                pass_type=options.pass_type,
                unit_stake=options.unit_stake,
                max_budget=options.max_budget,
                config=policy_config,
                as_of_time_utc=options.as_of_time_utc,
                locked_candidates=options.locked_candidates,
                min_quality_gain=options.min_marginal_quality_gain,
            )
    except ValueError as exc:
        warnings.append(str(exc))
        return RecommendationGenerationResult(
            dry_run=options.dry_run,
            as_of_time_utc=options.as_of_time_utc,
            candidate_count=len(candidates),
            generated_count=0,
            warnings=warnings,
        )

    stored_run = None
    if not options.dry_run:
        if repository is None:
            raise ValueError("repository is required for non-dry-run recommendation generation")
        stored_run = repository.save_selection(
            selection,
            as_of_time_utc=options.as_of_time_utc,
            run_key=_recommendation_run_key(selection, options=options),
            internal_trace_json=options.internal_trace_json,
            candidate_pool=candidates,
            candidate_query_json=_candidate_query_json(options),
        )

    return RecommendationGenerationResult(
        dry_run=options.dry_run,
        as_of_time_utc=options.as_of_time_utc,
        candidate_count=len(candidates),
        generated_count=1,
        selection=selection,
        stored_run=stored_run,
        warnings=warnings,
    )


def _recommendation_run_key(
    selection: RecommendationSelection,
    *,
    options: RecommendationGenerationOptions,
) -> str:
    fixture_part = "_".join(selection.fixture_ids)
    timestamp_part = options.as_of_time_utc.isoformat().replace("+00:00", "Z")
    return f"v3_1_{options.strategy}_{options.pass_type}_{fixture_part}_{timestamp_part}"


def _candidate_query_json(options: RecommendationGenerationOptions) -> dict[str, object]:
    return {
        "as_of_time_utc": options.as_of_time_utc.isoformat(),
        "allowed_markets": list(options.allowed_markets),
        "min_probability": options.min_probability,
        "min_model_edge": options.min_model_edge,
        "min_data_quality_score": options.min_data_quality_score,
        "candidate_limit": options.candidate_limit,
        "require_odds": options.require_odds,
        "fixture_ids": list(options.fixture_ids),
        "excluded_fixture_ids": list(options.excluded_fixture_ids),
        "locked_fixture_ids": [
            candidate.fixture_id for candidate in options.locked_candidates
        ],
        "competition_id": options.competition_id,
        "model_version": options.model_version,
        "source": "recommendation_generation_options",
    }
