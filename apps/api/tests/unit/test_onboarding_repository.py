from __future__ import annotations

from datetime import UTC, datetime
from json import loads

from nutmeg.providers.governance.onboarding import (
    CompetitionOnboardingInput,
    assess_competition_onboarding,
)
from nutmeg.providers.governance.onboarding_repository import (
    INSERT_COMPETITION_ONBOARDING_ASSESSMENT_QUERY,
    PostgresCompetitionOnboardingAssessmentRepository,
)


class FakeOnboardingDatabase:
    def __init__(self) -> None:
        self.last_query: str | None = None
        self.last_params: dict[str, object] | None = None

    def fetch_one(self, query: str, params: dict[str, object]) -> dict[str, object]:
        self.last_query = query
        self.last_params = params
        return {
            "assessment_id": 42,
            "created_at": datetime(2026, 5, 8, 9, 30, tzinfo=UTC),
        }

    def fetch_all(self, query: str, params: dict[str, object]) -> list[dict[str, object]]:
        return []


def test_postgres_onboarding_repository_persists_assessment_components() -> None:
    database = FakeOnboardingDatabase()
    repository = PostgresCompetitionOnboardingAssessmentRepository(database)
    payload = CompetitionOnboardingInput(
        competition_id="EPL",
        competition_name="Premier League",
        target_stage="production",
        schedule_coverage=0.995,
        result_coverage=0.995,
        odds_coverage=0.84,
        handicap_coverage=0.69,
        lineup_injury_coverage=0.70,
        historical_stats_completeness=0.82,
        provider_consistency=0.93,
        data_freshness=0.80,
        historical_sample_size=620,
        complete_seasons=2,
        market_resolver_tests_passed=True,
        score_grid_generation_passed=True,
        log_loss_delta_vs_baseline=-0.01,
        brier_delta_vs_baseline=-0.01,
        calibration_shift=0.02,
    )
    assessment = assess_competition_onboarding(payload)

    stored = repository.save_assessment(payload=payload, assessment=assessment)

    assert database.last_query == INSERT_COMPETITION_ONBOARDING_ASSESSMENT_QUERY
    assert database.last_params is not None
    assert database.last_params["competition_id"] == "EPL"
    assert database.last_params["target_stage"] == "production"
    assert database.last_params["odds_coverage"] == 0.84
    assert database.last_params["handicap_coverage"] == 0.69
    assert database.last_params["data_quality_score"] == assessment.data_quality.score
    assert loads(str(database.last_params["reasons_json"])) == [
        "odds_coverage_below_85",
        "handicap_coverage_below_70",
    ]
    assert stored.assessment_id == 42
    assert stored.created_at_utc == datetime(2026, 5, 8, 9, 30, tzinfo=UTC)
    assert stored.assessment.decision == "not_ready"
