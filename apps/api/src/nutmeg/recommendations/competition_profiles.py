from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH = Path(
    "configs/recommendations/competition_recommendation_profiles.json"
)


class CompetitionFinalAnswerValueGuard(BaseModel):
    penalty_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_min: float = Field(default=0.0, ge=0.0, le=1.0)
    probability_max: float = Field(default=1.0, ge=0.0, le=1.0)
    min_decimal_odds: float = Field(default=1.0, ge=1.0)
    max_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_model_edge: float | None = None
    score_min: float = Field(default=0.0, ge=0.0, le=1.0)
    score_max: float = Field(default=1.0, ge=0.0, le=1.0)
    source_report_key: str | None = None
    notes: list[str] = Field(default_factory=list)


class CompetitionRecommendationProfile(BaseModel):
    competition_id: str = Field(min_length=1)
    final_answer_score_adjustments: dict[str, float] = Field(default_factory=dict)
    final_answer_value_guards: list[CompetitionFinalAnswerValueGuard] = Field(default_factory=list)
    min_historical_final_hit_sample_size: int = Field(default=0, ge=0)
    source_report_key: str | None = None
    notes: list[str] = Field(default_factory=list)

    def final_answer_adjustment(self, *, pass_type: str, mode: str) -> float:
        return self.final_answer_score_adjustments.get(f"{pass_type}:{mode}", 0.0)


class CompetitionRecommendationProfileSet(BaseModel):
    profile_version: str = "none"
    calculation_basis: str = "competition_recommendation_profiles_v3_1"
    profiles: list[CompetitionRecommendationProfile] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def profile_index(self) -> dict[str, CompetitionRecommendationProfile]:
        return {profile.competition_id: profile for profile in self.profiles}


def load_competition_recommendation_profile_set(
    path: Path | str,
) -> CompetitionRecommendationProfileSet:
    return CompetitionRecommendationProfileSet.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def load_default_competition_recommendation_profile_set() -> CompetitionRecommendationProfileSet:
    profile_path = _default_profile_path()
    if profile_path is None:
        return CompetitionRecommendationProfileSet(
            notes=["default_competition_recommendation_profile_file_missing"]
        )
    return load_competition_recommendation_profile_set(profile_path)


def default_competition_recommendation_profile_version() -> str:
    return load_default_competition_recommendation_profile_set().profile_version


def default_competition_recommendation_profile_index() -> dict[
    str,
    CompetitionRecommendationProfile,
]:
    return load_default_competition_recommendation_profile_set().profile_index()


def competition_recommendation_profile_index(
    profiles: Sequence[CompetitionRecommendationProfile],
) -> dict[str, CompetitionRecommendationProfile]:
    return {profile.competition_id: profile for profile in profiles}


def _default_profile_path() -> Path | None:
    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.append(cwd / DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH)
    candidates.extend(
        parent / DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH for parent in cwd.parents
    )
    source_dir = Path(__file__).resolve().parent
    candidates.append(source_dir / DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH)
    candidates.extend(
        parent / DEFAULT_COMPETITION_RECOMMENDATION_PROFILE_PATH for parent in source_dir.parents
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
