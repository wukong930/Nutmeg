from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMarketType,
)

type CandidateProbabilityCalibrationStatus = Literal["applied", "not_applicable"]
type CandidateProbabilityCalibrationMode = Literal["active", "shadow"]
type CandidateProbabilityCalibrationSegmentMode = Literal[
    "probability_bucket",
    "market_odds_band",
]

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
type _CandidateIdentity = tuple[str, str, str, float | None, str | None]
type _BucketIndex = dict[
    tuple[str | None, RecommendationMarketType, str],
    list[CandidateProbabilityCalibrationBucket],
]


class CandidateProbabilityCalibrationBucket(BaseModel):
    outcome: str
    segment_mode: CandidateProbabilityCalibrationSegmentMode = "probability_bucket"
    bucket_start: float = Field(ge=0.0, le=1.0)
    bucket_end: float = Field(ge=0.0, le=1.0)
    calibrated_probability: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(default=0, ge=0)
    competition_id: str | None = None
    market_type: RecommendationMarketType = "1x2"

    @property
    def bucket_key(self) -> str:
        competition_part = self.competition_id or "global"
        return (
            f"{competition_part}:{self.market_type}:{self.outcome}:"
            f"{self.bucket_start:.4f}-{self.bucket_end:.4f}"
        )

    def contains(self, probability: float) -> bool:
        if probability < self.bucket_start:
            return False
        if self.bucket_end >= 1.0:
            return probability <= self.bucket_end
        return probability < self.bucket_end


class CandidateProbabilityCalibrationProfile(BaseModel):
    profile_key: str
    buckets: list[CandidateProbabilityCalibrationBucket] = Field(default_factory=list)
    source_report_key: str | None = None
    mode: CandidateProbabilityCalibrationMode = "active"
    segment_mode: CandidateProbabilityCalibrationSegmentMode = "probability_bucket"
    min_bucket_sample_size: int = Field(default=1, ge=1)
    blend_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    target_competition_ids: tuple[str, ...] = ()
    target_market_types: tuple[RecommendationMarketType, ...] = ("1x2",)
    target_outcomes: tuple[str, ...] = ()
    min_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    max_probability: float = Field(default=1.0, ge=0.0, le=1.0)
    min_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_decimal_odds: float | None = Field(default=None, gt=1.0)
    target_season_ids: tuple[str, ...] = ()
    excluded_season_ids: tuple[str, ...] = ()
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    min_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )
    max_competition_season_index_by_competition_id: dict[str, int] = Field(
        default_factory=dict
    )


class CandidateProbabilityCalibrationResult(BaseModel):
    status: CandidateProbabilityCalibrationStatus
    candidates: list[RecommendationCandidate]
    adjusted_candidate_count: int = Field(ge=0)
    adjusted_fixture_count: int = Field(ge=0)
    skipped_group_count: int = Field(ge=0)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _CalibrationProjection(BaseModel):
    probabilities: dict[str, float]
    adjusted_outcomes: set[str]
    bucket_keys_by_outcome: dict[str, str | None]


def apply_candidate_probability_calibration_profile(
    candidates: Sequence[RecommendationCandidate],
    *,
    profile: CandidateProbabilityCalibrationProfile,
) -> CandidateProbabilityCalibrationResult:
    if not candidates or not profile.buckets:
        return CandidateProbabilityCalibrationResult(
            status="not_applicable",
            candidates=list(candidates),
            adjusted_candidate_count=0,
            adjusted_fixture_count=0,
            skipped_group_count=0,
            warning_codes=["candidate_probability_calibration:no_input"],
            summary_json=_summary(
                profile,
                adjusted_candidate_count=0,
                adjusted_fixture_count=0,
                skipped_group_count=0,
            ),
        )

    bucket_index = _bucket_index(profile.buckets)
    grouped = _candidate_groups(candidates)
    adjusted_by_identity: dict[_CandidateIdentity, RecommendationCandidate] = {}
    skipped_group_count = 0

    for _group_key, group_candidates in grouped.items():
        projection = _calibration_projection(
            group_candidates,
            profile=profile,
            bucket_index=bucket_index,
        )
        if projection is None:
            skipped_group_count += 1
            continue
        for candidate in group_candidates:
            identity = _candidate_identity(candidate)
            adjusted_by_identity[identity] = _candidate_with_calibrated_probability(
                candidate,
                calibrated_probability=projection.probabilities[candidate.outcome],
                adjusted_outcomes=projection.adjusted_outcomes,
                bucket_key=projection.bucket_keys_by_outcome.get(candidate.outcome),
                profile=profile,
            )

    calibrated_candidates = [
        adjusted_by_identity.get(_candidate_identity(candidate), candidate)
        for candidate in candidates
    ]
    adjusted_candidate_count = len(adjusted_by_identity)
    adjusted_fixture_count = len(
        {
            fixture_id
            for fixture_id, _market_type in grouped
            if any(
                _candidate_identity(candidate) in adjusted_by_identity
                for candidate in grouped[(fixture_id, _market_type)]
            )
        }
    )
    status: CandidateProbabilityCalibrationStatus = (
        "applied" if adjusted_candidate_count else "not_applicable"
    )
    return CandidateProbabilityCalibrationResult(
        status=status,
        candidates=calibrated_candidates,
        adjusted_candidate_count=adjusted_candidate_count,
        adjusted_fixture_count=adjusted_fixture_count,
        skipped_group_count=skipped_group_count,
        summary_json=_summary(
            profile,
            adjusted_candidate_count=adjusted_candidate_count,
            adjusted_fixture_count=adjusted_fixture_count,
            skipped_group_count=skipped_group_count,
        ),
    )


def _calibration_projection(
    candidates: Sequence[RecommendationCandidate],
    *,
    profile: CandidateProbabilityCalibrationProfile,
    bucket_index: Mapping[
        tuple[str | None, RecommendationMarketType, str],
        list[CandidateProbabilityCalibrationBucket],
    ],
) -> _CalibrationProjection | None:
    if len(candidates) != len(ONE_X_TWO_OUTCOMES):
        return None
    by_outcome = {candidate.outcome: candidate for candidate in candidates}
    if set(by_outcome) != set(ONE_X_TWO_OUTCOMES):
        return None
    first = candidates[0]
    if first.market_type not in set(profile.target_market_types):
        return None
    competition_id = _competition_id(first)
    if (
        profile.target_competition_ids
        and competition_id not in set(profile.target_competition_ids)
    ):
        return None

    next_probabilities = {
        outcome: by_outcome[outcome].raw_model_probability()
        for outcome in ONE_X_TWO_OUTCOMES
    }
    adjusted_outcomes: set[str] = set()
    bucket_keys_by_outcome: dict[str, str | None] = {}
    for outcome in ONE_X_TWO_OUTCOMES:
        candidate = by_outcome[outcome]
        if not _candidate_matches_profile(candidate, profile):
            continue
        bucket = _matching_bucket(
            candidate,
            competition_id=competition_id,
            bucket_index=bucket_index,
            profile=profile,
        )
        if bucket is None:
            continue
        raw_probability = candidate.raw_model_probability()
        next_probabilities[outcome] = _clamp_probability(
            (1.0 - profile.blend_weight) * raw_probability
            + profile.blend_weight * bucket.calibrated_probability
        )
        adjusted_outcomes.add(outcome)
        bucket_keys_by_outcome[outcome] = bucket.bucket_key

    if not adjusted_outcomes:
        return None
    normalized = _normalize_probabilities(next_probabilities)
    if normalized is None:
        return None
    return _CalibrationProjection(
        probabilities=normalized,
        adjusted_outcomes=adjusted_outcomes,
        bucket_keys_by_outcome=bucket_keys_by_outcome,
    )


def _candidate_with_calibrated_probability(
    candidate: RecommendationCandidate,
    *,
    calibrated_probability: float,
    adjusted_outcomes: set[str],
    bucket_key: str | None,
    profile: CandidateProbabilityCalibrationProfile,
) -> RecommendationCandidate:
    raw_model_probability = candidate.raw_model_probability()
    market_probability = candidate.effective_market_probability()
    next_probability = (
        calibrated_probability if profile.mode == "active" else candidate.probability
    )
    next_model_edge = (
        next_probability - market_probability if market_probability is not None else None
    )
    return candidate.model_copy(
        update={
            "probability": next_probability,
            "model_probability": raw_model_probability,
            "calibrated_probability": calibrated_probability,
            "probability_source": (
                "calibrated" if profile.mode == "active" else candidate.probability_source
            ),
            "model_edge": next_model_edge,
            "metadata_json": {
                **candidate.metadata_json,
                "candidate_probability_calibration_profile_key": profile.profile_key,
                "candidate_probability_calibration_source_report_key": (
                    profile.source_report_key
                ),
                "candidate_probability_calibration_mode": profile.mode,
                "candidate_probability_calibration_segment_mode": profile.segment_mode,
                "model_probability": raw_model_probability,
                "calibrated_probability": calibrated_probability,
                "calibration_bucket_key": bucket_key,
                "calibration_directly_adjusted": candidate.outcome in adjusted_outcomes,
                "calibration_adjusted_outcomes": sorted(adjusted_outcomes),
            },
        }
    )


def _candidate_matches_profile(
    candidate: RecommendationCandidate,
    profile: CandidateProbabilityCalibrationProfile,
) -> bool:
    if candidate.market_type not in set(profile.target_market_types):
        return False
    if profile.target_outcomes and candidate.outcome not in set(profile.target_outcomes):
        return False
    if not _candidate_matches_season_scope(candidate, profile):
        return False
    raw_probability = candidate.raw_model_probability()
    if raw_probability < profile.min_probability or raw_probability > profile.max_probability:
        return False
    if (
        profile.min_decimal_odds is not None
        and (candidate.decimal_odds is None or candidate.decimal_odds < profile.min_decimal_odds)
    ):
        return False
    return not (
        profile.max_decimal_odds is not None
        and (candidate.decimal_odds is None or candidate.decimal_odds > profile.max_decimal_odds)
    )


def _candidate_matches_season_scope(
    candidate: RecommendationCandidate,
    profile: CandidateProbabilityCalibrationProfile,
) -> bool:
    season_id = _season_id(candidate)
    if profile.target_season_ids and season_id not in set(profile.target_season_ids):
        return False
    if profile.excluded_season_ids and season_id in set(profile.excluded_season_ids):
        return False
    min_index = profile.min_competition_season_index
    max_index = profile.max_competition_season_index
    competition_id = _competition_id(candidate)
    if competition_id is not None:
        min_index = profile.min_competition_season_index_by_competition_id.get(
            competition_id,
            min_index,
        )
        max_index = profile.max_competition_season_index_by_competition_id.get(
            competition_id,
            max_index,
        )
    if min_index is None and max_index is None:
        return True
    season_index = _competition_season_index(candidate)
    if season_index is None:
        return False
    if min_index is not None and season_index < min_index:
        return False
    return not (max_index is not None and season_index > max_index)


def _matching_bucket(
    candidate: RecommendationCandidate,
    *,
    competition_id: str | None,
    bucket_index: Mapping[
        tuple[str | None, RecommendationMarketType, str],
        list[CandidateProbabilityCalibrationBucket],
    ],
    profile: CandidateProbabilityCalibrationProfile,
) -> CandidateProbabilityCalibrationBucket | None:
    for scoped_competition_id in (competition_id, None):
        for bucket in bucket_index.get(
            (scoped_competition_id, candidate.market_type, candidate.outcome),
            [],
        ):
            if bucket.sample_size < profile.min_bucket_sample_size:
                continue
            if bucket.segment_mode != profile.segment_mode:
                continue
            if bucket.contains(_candidate_bucket_basis_probability(candidate, profile)):
                return bucket
    return None


def _bucket_index(
    buckets: Sequence[CandidateProbabilityCalibrationBucket],
) -> _BucketIndex:
    index: _BucketIndex = defaultdict(list)
    for bucket in buckets:
        index[(bucket.competition_id, bucket.market_type, bucket.outcome)].append(bucket)
    return dict(index)


def _candidate_groups(
    candidates: Sequence[RecommendationCandidate],
) -> dict[tuple[str, RecommendationMarketType], list[RecommendationCandidate]]:
    grouped: dict[tuple[str, RecommendationMarketType], list[RecommendationCandidate]] = (
        defaultdict(list)
    )
    for candidate in candidates:
        if candidate.market_type != "1x2":
            continue
        grouped[(candidate.fixture_id, candidate.market_type)].append(candidate)
    return dict(grouped)


def _normalize_probabilities(probabilities: Mapping[str, float]) -> dict[str, float] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {
        outcome: _clamp_probability(probability / total)
        for outcome, probability in probabilities.items()
    }


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def _candidate_bucket_basis_probability(
    candidate: RecommendationCandidate,
    profile: CandidateProbabilityCalibrationProfile,
) -> float:
    if profile.segment_mode == "market_odds_band":
        market_probability = candidate.effective_market_probability()
        if market_probability is not None:
            return _clamp_probability(market_probability)
    return candidate.raw_model_probability()


def _competition_id(candidate: RecommendationCandidate) -> str | None:
    raw_competition_id = candidate.metadata_json.get("competition_id")
    return raw_competition_id if isinstance(raw_competition_id, str) else None


def _season_id(candidate: RecommendationCandidate) -> str | None:
    for key in ("season_id", "season", "source_season"):
        raw = candidate.metadata_json.get(key)
        if isinstance(raw, str) and raw:
            return raw
    return None


def _competition_season_index(candidate: RecommendationCandidate) -> int | None:
    raw = candidate.metadata_json.get("competition_season_index")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _candidate_identity(
    candidate: RecommendationCandidate,
) -> tuple[str, str, str, float | None, str | None]:
    return (
        candidate.fixture_id,
        candidate.market_type,
        candidate.outcome,
        candidate.line,
        candidate.side,
    )


def _summary(
    profile: CandidateProbabilityCalibrationProfile,
    *,
    adjusted_candidate_count: int,
    adjusted_fixture_count: int,
    skipped_group_count: int,
) -> dict[str, object]:
    return {
        "calculation_basis": "candidate_probability_calibration_profile_v3_1",
        "profile_key": profile.profile_key,
        "source_report_key": profile.source_report_key,
        "mode": profile.mode,
        "segment_mode": profile.segment_mode,
        "bucket_count": len(profile.buckets),
        "min_bucket_sample_size": profile.min_bucket_sample_size,
        "blend_weight": profile.blend_weight,
        "target_competition_ids": list(profile.target_competition_ids),
        "target_market_types": list(profile.target_market_types),
        "target_outcomes": list(profile.target_outcomes),
        "target_season_ids": list(profile.target_season_ids),
        "excluded_season_ids": list(profile.excluded_season_ids),
        "min_competition_season_index": profile.min_competition_season_index,
        "max_competition_season_index": profile.max_competition_season_index,
        "min_competition_season_index_by_competition_id": (
            dict(sorted(profile.min_competition_season_index_by_competition_id.items()))
        ),
        "max_competition_season_index_by_competition_id": (
            dict(sorted(profile.max_competition_season_index_by_competition_id.items()))
        ),
        "adjusted_candidate_count": adjusted_candidate_count,
        "adjusted_fixture_count": adjusted_fixture_count,
        "skipped_group_count": skipped_group_count,
    }
