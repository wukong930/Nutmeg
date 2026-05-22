from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DataQualityGrade = Literal["A", "B", "C", "D"]


class DataQualityInputs(BaseModel):
    fixture_reliability: float = Field(ge=0.0, le=1.0)
    odds_coverage: float = Field(ge=0.0, le=1.0)
    lineup_injury_coverage: float = Field(ge=0.0, le=1.0)
    historical_stats_completeness: float = Field(ge=0.0, le=1.0)
    provider_consistency: float = Field(ge=0.0, le=1.0)
    data_freshness: float = Field(ge=0.0, le=1.0)


class DataQualityBreakdown(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    grade: DataQualityGrade
    parlay_eligible: bool
    components: DataQualityInputs
    messages: list[str]


def data_quality_grade(score: float) -> DataQualityGrade:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def score_data_quality(inputs: DataQualityInputs) -> DataQualityBreakdown:
    score = round(
        100
        * (
            0.20 * inputs.fixture_reliability
            + 0.20 * inputs.odds_coverage
            + 0.20 * inputs.lineup_injury_coverage
            + 0.20 * inputs.historical_stats_completeness
            + 0.10 * inputs.provider_consistency
            + 0.10 * inputs.data_freshness
        ),
        2,
    )
    grade = data_quality_grade(score)
    messages = _messages_for_grade(grade)
    return DataQualityBreakdown(
        score=score,
        grade=grade,
        parlay_eligible=score >= 50,
        components=inputs,
        messages=messages,
    )


def _messages_for_grade(grade: DataQualityGrade) -> list[str]:
    if grade == "A":
        return ["数据质量 A：预测基础较完整。"]
    if grade == "B":
        return ["数据质量 B：主要赛程、赔率和历史数据可用，仍需跟踪阵容更新。"]
    if grade == "C":
        return ["数据质量 C：阵容/赔率数据不足，谨慎解读。"]
    return ["数据质量 D：不生成串关推荐。"]
