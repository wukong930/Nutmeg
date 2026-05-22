from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from json import dumps, loads
from typing import Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.providers.governance.onboarding import (
    CompetitionOnboardingAssessment,
    CompetitionOnboardingInput,
    OnboardingDecision,
    OnboardingTargetStage,
    assess_competition_onboarding,
)

INSERT_COMPETITION_ONBOARDING_ASSESSMENT_QUERY = """
INSERT INTO competition_onboarding_assessments (
  competition_id,
  competition_name,
  target_stage,
  decision,
  schedule_coverage,
  result_coverage,
  odds_coverage,
  handicap_coverage,
  lineup_injury_coverage,
  historical_stats_completeness,
  provider_consistency,
  data_freshness,
  historical_sample_size,
  complete_seasons,
  data_quality_score,
  data_quality_grade,
  market_resolver_tests_passed,
  score_grid_generation_passed,
  log_loss_delta_vs_baseline,
  brier_delta_vs_baseline,
  calibration_shift,
  reasons_json
) VALUES (
  %(competition_id)s,
  %(competition_name)s,
  %(target_stage)s,
  %(decision)s,
  %(schedule_coverage)s,
  %(result_coverage)s,
  %(odds_coverage)s,
  %(handicap_coverage)s,
  %(lineup_injury_coverage)s,
  %(historical_stats_completeness)s,
  %(provider_consistency)s,
  %(data_freshness)s,
  %(historical_sample_size)s,
  %(complete_seasons)s,
  %(data_quality_score)s,
  %(data_quality_grade)s,
  %(market_resolver_tests_passed)s,
  %(score_grid_generation_passed)s,
  %(log_loss_delta_vs_baseline)s,
  %(brier_delta_vs_baseline)s,
  %(calibration_shift)s,
  %(reasons_json)s::jsonb
)
RETURNING assessment_id, created_at
"""

LATEST_COMPETITION_ONBOARDING_ASSESSMENTS_QUERY = """
SELECT DISTINCT ON (competition_id, target_stage)
  assessment_id,
  competition_id,
  competition_name,
  target_stage,
  decision,
  schedule_coverage,
  result_coverage,
  odds_coverage,
  handicap_coverage,
  lineup_injury_coverage,
  historical_stats_completeness,
  provider_consistency,
  data_freshness,
  historical_sample_size,
  complete_seasons,
  data_quality_score,
  data_quality_grade,
  market_resolver_tests_passed,
  score_grid_generation_passed,
  log_loss_delta_vs_baseline,
  brier_delta_vs_baseline,
  calibration_shift,
  reasons_json,
  created_at
FROM competition_onboarding_assessments
WHERE (%(competition_id)s::text IS NULL OR competition_id = %(competition_id)s::text)
ORDER BY competition_id, target_stage, created_at DESC, assessment_id DESC
LIMIT %(limit)s::int
"""


class OnboardingAssessmentDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a read-only onboarding query and return mapping rows."""


class StoredCompetitionOnboardingAssessment(BaseModel):
    assessment_id: int = Field(gt=0)
    created_at_utc: datetime
    assessment: CompetitionOnboardingAssessment


class PostgresCompetitionOnboardingAssessmentRepository:
    def __init__(self, database: OnboardingAssessmentDatabaseExecutor) -> None:
        self.database = database

    def save_assessment(
        self,
        *,
        payload: CompetitionOnboardingInput,
        assessment: CompetitionOnboardingAssessment,
    ) -> StoredCompetitionOnboardingAssessment:
        row = _required_row(
            self.database.fetch_one(
                INSERT_COMPETITION_ONBOARDING_ASSESSMENT_QUERY,
                _assessment_params(payload=payload, assessment=assessment),
            )
        )
        return StoredCompetitionOnboardingAssessment(
            assessment_id=_int(row["assessment_id"]),
            created_at_utc=_datetime(row["created_at"]),
            assessment=assessment,
        )

    def list_latest(
        self,
        *,
        competition_id: str | None = None,
        limit: int = 50,
    ) -> list[StoredCompetitionOnboardingAssessment]:
        rows = self.database.fetch_all(
            LATEST_COMPETITION_ONBOARDING_ASSESSMENTS_QUERY,
            {"competition_id": competition_id, "limit": limit},
        )
        return [_stored_assessment_from_row(row) for row in rows]


def _assessment_params(
    *,
    payload: CompetitionOnboardingInput,
    assessment: CompetitionOnboardingAssessment,
) -> dict[str, object]:
    return {
        "competition_id": payload.competition_id,
        "competition_name": payload.competition_name,
        "target_stage": payload.target_stage,
        "decision": assessment.decision,
        "schedule_coverage": payload.schedule_coverage,
        "result_coverage": payload.result_coverage,
        "odds_coverage": payload.odds_coverage,
        "handicap_coverage": payload.handicap_coverage,
        "lineup_injury_coverage": payload.lineup_injury_coverage,
        "historical_stats_completeness": payload.historical_stats_completeness,
        "provider_consistency": payload.provider_consistency,
        "data_freshness": payload.data_freshness,
        "historical_sample_size": payload.historical_sample_size,
        "complete_seasons": payload.complete_seasons,
        "data_quality_score": assessment.data_quality.score,
        "data_quality_grade": assessment.data_quality.grade,
        "market_resolver_tests_passed": payload.market_resolver_tests_passed,
        "score_grid_generation_passed": payload.score_grid_generation_passed,
        "log_loss_delta_vs_baseline": payload.log_loss_delta_vs_baseline,
        "brier_delta_vs_baseline": payload.brier_delta_vs_baseline,
        "calibration_shift": payload.calibration_shift,
        "reasons_json": _json(assessment.reasons),
    }


def _stored_assessment_from_row(row: DatabaseRow) -> StoredCompetitionOnboardingAssessment:
    payload = CompetitionOnboardingInput(
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        target_stage=cast(OnboardingTargetStage, str(row["target_stage"])),
        schedule_coverage=_float(row["schedule_coverage"]),
        result_coverage=_float(row["result_coverage"]),
        odds_coverage=_float(row["odds_coverage"]),
        handicap_coverage=_float(row["handicap_coverage"]),
        lineup_injury_coverage=_float(row["lineup_injury_coverage"]),
        historical_stats_completeness=_float(row["historical_stats_completeness"]),
        provider_consistency=_float(row["provider_consistency"]),
        data_freshness=_float(row["data_freshness"]),
        historical_sample_size=_int(row["historical_sample_size"]),
        complete_seasons=_int(row["complete_seasons"]),
        market_resolver_tests_passed=bool(row["market_resolver_tests_passed"]),
        score_grid_generation_passed=bool(row["score_grid_generation_passed"]),
        log_loss_delta_vs_baseline=_optional_float(row["log_loss_delta_vs_baseline"]),
        brier_delta_vs_baseline=_optional_float(row["brier_delta_vs_baseline"]),
        calibration_shift=_optional_float(row["calibration_shift"]),
    )
    recalculated_assessment = assess_competition_onboarding(payload)
    assessment = CompetitionOnboardingAssessment(
        competition_id=payload.competition_id,
        competition_name=payload.competition_name,
        target_stage=payload.target_stage,
        decision=cast(OnboardingDecision, str(row["decision"])),
        data_quality=recalculated_assessment.data_quality,
        reasons=_string_list(row["reasons_json"]),
        beta_ready=recalculated_assessment.beta_ready,
        production_ready=str(row["decision"]) == "production_ready",
    )
    return StoredCompetitionOnboardingAssessment(
        assessment_id=_int(row["assessment_id"]),
        created_at_utc=_datetime(row["created_at"]),
        assessment=assessment,
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected competition onboarding assessment row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    return int(str(value))


def _float(value: object) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float(value)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _string_list(value: object) -> list[str]:
    parsed = loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]
