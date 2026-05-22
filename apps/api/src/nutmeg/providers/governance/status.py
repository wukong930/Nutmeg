from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from nutmeg.model_governance import (
    ModelPromotionInput,
    ModelPromotionReview,
    ModelRollbackPlan,
    ModelRollbackSignal,
    evaluate_model_promotion,
    evaluate_model_rollback,
)
from nutmeg.providers.governance.contracts import ProviderAuthorizationRecord
from nutmeg.providers.governance.onboarding import (
    CompetitionOnboardingAssessment,
    CompetitionOnboardingInput,
    assess_competition_onboarding,
)


class ProviderGovernanceSnapshot(BaseModel):
    providers: list[ProviderAuthorizationRecord]
    competition_readiness: list[CompetitionOnboardingAssessment]
    model_promotion_review: ModelPromotionReview
    rollback_plan: ModelRollbackPlan
    generated_at_utc: datetime


def build_mock_provider_governance_snapshot(
    persisted_competition_readiness: list[CompetitionOnboardingAssessment] | None = None,
    provider_authorizations: list[ProviderAuthorizationRecord] | None = None,
) -> ProviderGovernanceSnapshot:
    return ProviderGovernanceSnapshot(
        providers=provider_authorizations or _provider_authorizations(),
        competition_readiness=_merge_competition_readiness(
            _competition_readiness(),
            persisted_competition_readiness or [],
        ),
        model_promotion_review=evaluate_model_promotion(
            ModelPromotionInput(
                candidate_model_version="poisson-m1.1.0",
                baseline_model_version="poisson-m1.0.0",
                sample_size=620,
                overall_log_loss_delta=-0.012,
                overall_brier_delta=-0.006,
                calibration_error_delta=-0.004,
                core_market_improvement=True,
                upset_precision_at_k_delta=-0.005,
                handicap_performance_delta=0.003,
                parlay_simulation_delta=0.01,
                low_sample_competition_drift=False,
            )
        ),
        rollback_plan=evaluate_model_rollback(
            ModelRollbackSignal(
                active_model_version="poisson-m1.0.0",
                previous_stable_model_version="poisson-m0.9.4",
            )
        ),
        generated_at_utc=datetime(2026, 5, 6, 12, 45, tzinfo=UTC),
    )


def _merge_competition_readiness(
    baseline: list[CompetitionOnboardingAssessment],
    persisted: list[CompetitionOnboardingAssessment],
) -> list[CompetitionOnboardingAssessment]:
    if not persisted:
        return baseline
    persisted_by_key = {
        (assessment.competition_id, assessment.target_stage): assessment
        for assessment in persisted
    }
    merged: list[CompetitionOnboardingAssessment] = []
    seen: set[tuple[str, str]] = set()
    for assessment in baseline:
        key = (assessment.competition_id, assessment.target_stage)
        merged.append(persisted_by_key.get(key, assessment))
        seen.add(key)
    for assessment in persisted:
        key = (assessment.competition_id, assessment.target_stage)
        if key not in seen:
            merged.append(assessment)
            seen.add(key)
    return merged


def _provider_authorizations() -> list[ProviderAuthorizationRecord]:
    checked_at = datetime(2026, 5, 6, 0, 0, tzinfo=UTC)
    return [
        ProviderAuthorizationRecord(
            provider_name="mock-local",
            status="active",
            capabilities=(
                "competitions",
                "seasons",
                "fixtures",
                "fixture_detail",
                "results",
                "odds",
                "lineups",
                "injuries",
                "team_stats",
            ),
            terms_checked_at_utc=checked_at,
            commercial_use_allowed=True,
            retention_allowed=True,
            allowed_use="local_development_and_test",
            rate_limit="none",
            historical_data_allowed=True,
            redistribution_allowed=True,
            terms_url=None,
            last_reviewed_at=checked_at,
            next_review_due_at=checked_at + timedelta(days=365),
            owner="nutmeg-ops",
            api_key_env_var=None,
            notes="Local deterministic fixture provider for development and tests.",
        ),
        ProviderAuthorizationRecord(
            provider_name="football-data.org",
            status="pending_review",
            capabilities=("competitions", "seasons", "fixtures", "results"),
            terms_checked_at_utc=checked_at,
            commercial_use_allowed=False,
            retention_allowed=False,
            allowed_use="fixtures_results_research_dry_run",
            rate_limit="free_plan_provider_defined",
            historical_data_allowed=False,
            redistribution_allowed=False,
            terms_url="https://www.football-data.org/terms",
            last_reviewed_at=checked_at,
            next_review_due_at=checked_at + timedelta(days=180),
            owner="nutmeg-ops",
            api_key_env_var="FOOTBALL_DATA_API_KEY",
            notes=(
                "Candidate schedule/result provider; legal and retention review required "
                "before production."
            ),
        ),
        ProviderAuthorizationRecord(
            provider_name="the-odds-api",
            status="pending_review",
            capabilities=("odds",),
            terms_checked_at_utc=checked_at,
            commercial_use_allowed=False,
            retention_allowed=False,
            allowed_use="odds_snapshot_research_dry_run",
            rate_limit="free_plan_provider_defined",
            historical_data_allowed=False,
            redistribution_allowed=False,
            terms_url="https://the-odds-api.com/terms.html",
            last_reviewed_at=checked_at,
            next_review_due_at=checked_at + timedelta(days=180),
            owner="nutmeg-ops",
            api_key_env_var="THE_ODDS_API_KEY",
            notes="Candidate odds provider; verify historical snapshot retention terms.",
        ),
        ProviderAuthorizationRecord(
            provider_name="sportmonks",
            status="pending_review",
            capabilities=("fixtures", "results", "odds", "lineups", "injuries", "team_stats"),
            terms_checked_at_utc=checked_at,
            commercial_use_allowed=False,
            retention_allowed=False,
            allowed_use="broad_coverage_trial_research",
            rate_limit="trial_plan_provider_defined",
            historical_data_allowed=False,
            redistribution_allowed=False,
            terms_url="https://www.sportmonks.com/terms-of-service/",
            last_reviewed_at=checked_at,
            next_review_due_at=checked_at + timedelta(days=180),
            owner="nutmeg-ops",
            api_key_env_var="SPORTMONKS_API_KEY",
            notes=(
                "Candidate broad coverage provider; production use requires explicit plan "
                "and contract check."
            ),
        ),
        ProviderAuthorizationRecord(
            provider_name="api-football",
            status="pending_review",
            capabilities=("competitions", "seasons", "fixtures", "results"),
            terms_checked_at_utc=datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
            commercial_use_allowed=False,
            retention_allowed=False,
            allowed_use="fixture_result_fallback_research_dry_run",
            rate_limit="free_plan_provider_defined",
            historical_data_allowed=False,
            redistribution_allowed=False,
            terms_url="https://www.api-football.com/terms",
            last_reviewed_at=datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
            next_review_due_at=datetime(2026, 5, 8, 0, 0, tzinfo=UTC)
            + timedelta(days=180),
            owner="nutmeg-ops",
            api_key_env_var="API_FOOTBALL_API_KEY",
            notes=(
                "Candidate broad fixture/result fallback; free plan can be "
                "season-limited."
            ),
        ),
    ]


def _competition_readiness() -> list[CompetitionOnboardingAssessment]:
    return [
        assess_competition_onboarding(
            CompetitionOnboardingInput(
                competition_id="EPL",
                competition_name="Premier League",
                target_stage="beta",
                schedule_coverage=0.995,
                result_coverage=0.995,
                odds_coverage=0.72,
                handicap_coverage=0.75,
                lineup_injury_coverage=0.70,
                historical_stats_completeness=0.82,
                provider_consistency=0.93,
                data_freshness=0.88,
                historical_sample_size=420,
                complete_seasons=1,
                market_resolver_tests_passed=True,
                score_grid_generation_passed=True,
            )
        ),
        assess_competition_onboarding(
            CompetitionOnboardingInput(
                competition_id="JPN_J1",
                competition_name="J1 League",
                target_stage="beta",
                schedule_coverage=0.96,
                result_coverage=0.98,
                odds_coverage=0.48,
                handicap_coverage=0.42,
                lineup_injury_coverage=0.35,
                historical_stats_completeness=0.58,
                provider_consistency=0.76,
                data_freshness=0.64,
                historical_sample_size=180,
                complete_seasons=0,
                market_resolver_tests_passed=True,
                score_grid_generation_passed=True,
            )
        ),
        assess_competition_onboarding(
            CompetitionOnboardingInput(
                competition_id="EPL",
                competition_name="Premier League",
                target_stage="production",
                schedule_coverage=0.995,
                result_coverage=0.995,
                odds_coverage=0.72,
                handicap_coverage=0.75,
                lineup_injury_coverage=0.70,
                historical_stats_completeness=0.82,
                provider_consistency=0.93,
                data_freshness=0.88,
                historical_sample_size=420,
                complete_seasons=1,
                market_resolver_tests_passed=True,
                score_grid_generation_passed=True,
                log_loss_delta_vs_baseline=-0.004,
                brier_delta_vs_baseline=-0.002,
                calibration_shift=0.02,
            )
        ),
    ]
