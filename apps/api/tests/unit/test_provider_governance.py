from __future__ import annotations

from datetime import UTC, datetime

import pytest

from nutmeg.providers.governance import (
    CompetitionOnboardingInput,
    DataQualityInputs,
    ProviderAuthorizationRecord,
    ProviderRegistry,
    assess_competition_onboarding,
    score_data_quality,
)


def test_data_quality_score_uses_documented_weights_and_grades() -> None:
    breakdown = score_data_quality(
        DataQualityInputs(
            fixture_reliability=0.98,
            odds_coverage=0.60,
            lineup_injury_coverage=0.40,
            historical_stats_completeness=0.80,
            provider_consistency=0.90,
            data_freshness=0.70,
        )
    )

    assert breakdown.score == 71.6
    assert breakdown.grade == "B"
    assert breakdown.parlay_eligible is True
    assert "数据质量 B" in breakdown.messages[0]


def test_data_quality_d_blocks_parlay_eligibility() -> None:
    breakdown = score_data_quality(
        DataQualityInputs(
            fixture_reliability=0.40,
            odds_coverage=0.20,
            lineup_injury_coverage=0.10,
            historical_stats_completeness=0.40,
            provider_consistency=0.50,
            data_freshness=0.40,
        )
    )

    assert breakdown.grade == "D"
    assert breakdown.parlay_eligible is False
    assert breakdown.messages == ["数据质量 D：不生成串关推荐。"]


def test_provider_authorization_uses_env_var_name_not_secret_value() -> None:
    record = ProviderAuthorizationRecord(
        provider_name="football-data.org",
        status="active",
        capabilities=("fixtures", "results"),
        terms_checked_at_utc=datetime(2026, 5, 6, tzinfo=UTC),
        commercial_use_allowed=True,
        retention_allowed=True,
        allowed_use="fixtures_results_research_dry_run",
        rate_limit="free_plan_provider_defined",
        historical_data_allowed=True,
        redistribution_allowed=False,
        terms_url="https://www.football-data.org/terms",
        last_reviewed_at=datetime(2026, 5, 8, tzinfo=UTC),
        next_review_due_at=datetime(2026, 11, 4, tzinfo=UTC),
        owner="nutmeg-ops",
        api_key_env_var="FOOTBALL_DATA_API_KEY",
    )

    assert record.is_usable_for_production is True
    assert record.supports("fixtures")
    assert record.allowed_use == "fixtures_results_research_dry_run"
    assert record.rate_limit == "free_plan_provider_defined"
    assert record.terms_url == "https://www.football-data.org/terms"
    assert record.last_reviewed_at == datetime(2026, 5, 8, tzinfo=UTC)
    assert record.next_review_due_at == datetime(2026, 11, 4, tzinfo=UTC)

    with pytest.raises(ValueError, match="uppercase environment variable"):
        ProviderAuthorizationRecord(
            provider_name="bad",
            status="active",
            api_key_env_var="plain-secret-value",
        )


def test_provider_registry_blocks_unreviewed_or_unsupported_providers() -> None:
    registry = ProviderRegistry(
        [
            ProviderAuthorizationRecord(
                provider_name="candidate",
                status="pending_review",
                capabilities=("odds",),
            )
        ]
    )

    with pytest.raises(ValueError, match="not production-authorized"):
        registry.adapter_for("candidate", required_capability="odds")

    with pytest.raises(ValueError, match="authorization missing"):
        registry.adapter_for("missing", required_capability="fixtures")


def test_competition_beta_and_production_readiness_rules() -> None:
    beta_assessment = assess_competition_onboarding(
        CompetitionOnboardingInput(
            competition_id="EPL",
            competition_name="Premier League",
            target_stage="beta",
            schedule_coverage=0.99,
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
    )
    assert beta_assessment.decision == "beta_ready"
    assert beta_assessment.beta_ready is True
    assert beta_assessment.production_ready is False

    production_assessment = assess_competition_onboarding(
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
            log_loss_delta_vs_baseline=-0.01,
            brier_delta_vs_baseline=-0.01,
            calibration_shift=0.02,
        )
    )
    assert production_assessment.decision == "not_ready"
    assert "production_needs_500_matches_or_2_complete_seasons" in (
        production_assessment.reasons
    )
    assert "odds_coverage_below_85" in production_assessment.reasons
