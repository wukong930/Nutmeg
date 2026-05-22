from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict


class MockTeam(TypedDict):
    team_id: str
    name: str


class MockFixture(TypedDict):
    fixture_id: str
    competition_id: str
    competition: str
    kickoff_time_utc: datetime
    home_team: MockTeam
    away_team: MockTeam
    home_lambda: float
    away_lambda: float
    prediction_time_utc: datetime
    status: str
    confidence: str
    data_quality_score: float
    cn_handicap: int
    asian_handicap_line: float
    european_handicap: int
    market_1x2: dict[str, float]
    market_cn_handicap_1x2: dict[str, float]
    market_european_handicap_1x2: dict[str, float]
    key_factors: dict[str, list[str]]


_FIXTURES: list[MockFixture] = [
    {
        "fixture_id": "fix_epl_001",
        "competition_id": "EPL",
        "competition": "Premier League",
        "kickoff_time_utc": datetime(2026, 5, 6, 19, 0, tzinfo=UTC),
        "home_team": {"team_id": "ars", "name": "Arsenal"},
        "away_team": {"team_id": "liv", "name": "Liverpool"},
        "home_lambda": 1.42,
        "away_lambda": 1.11,
        "prediction_time_utc": datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        "status": "beta",
        "confidence": "medium",
        "data_quality_score": 82.0,
        "cn_handicap": -1,
        "asian_handicap_line": -0.25,
        "european_handicap": -1,
        "market_1x2": {"home_win": 0.401, "draw": 0.261, "away_win": 0.338},
        "market_cn_handicap_1x2": {
            "handicap_home_win": 0.198,
            "handicap_draw": 0.244,
            "handicap_away_win": 0.558,
        },
        "market_european_handicap_1x2": {
            "handicap_home_win": 0.198,
            "handicap_draw": 0.244,
            "handicap_away_win": 0.558,
        },
        "key_factors": {
            "model": [
                "Poisson baseline 估计主队期望进球略高。",
                "比分分布集中在一球差与平局附近。",
            ],
            "market": ["市场主胜隐含概率低于模型估计。", "平局差值为正但幅度有限。"],
            "lineup": ["阵容数据质量为 B，关键缺阵信息尚未完全确认。"],
            "schedule": ["双方赛程压力处于常规区间。"],
            "uncertainty": ["Beta 模型状态，概率需要结合后续校准结果解读。"],
        },
    },
    {
        "fixture_id": "fix_epl_002",
        "competition_id": "EPL",
        "competition": "Premier League",
        "kickoff_time_utc": datetime(2026, 5, 6, 21, 0, tzinfo=UTC),
        "home_team": {"team_id": "mci", "name": "Manchester City"},
        "away_team": {"team_id": "tot", "name": "Tottenham Hotspur"},
        "home_lambda": 1.70,
        "away_lambda": 1.05,
        "prediction_time_utc": datetime(2026, 5, 6, 12, 5, tzinfo=UTC),
        "status": "scheduled",
        "confidence": "medium",
        "data_quality_score": 88.0,
        "cn_handicap": -1,
        "asian_handicap_line": -0.75,
        "european_handicap": -1,
        "market_1x2": {"home_win": 0.547, "draw": 0.221, "away_win": 0.232},
        "market_cn_handicap_1x2": {
            "handicap_home_win": 0.328,
            "handicap_draw": 0.226,
            "handicap_away_win": 0.446,
        },
        "market_european_handicap_1x2": {
            "handicap_home_win": 0.328,
            "handicap_draw": 0.226,
            "handicap_away_win": 0.446,
        },
        "key_factors": {
            "model": ["主队胜率最高，但让球盘保护空间有限。"],
            "market": ["市场对主队方向更积极，模型差异集中在让球负。"],
            "lineup": ["核心阵容覆盖较完整，数据质量 A。"],
            "schedule": ["近期赛程可能影响强队大胜尾部。"],
            "uncertainty": ["让球盘口对单球差距敏感。"],
        },
    },
    {
        "fixture_id": "fix_j1_001",
        "competition_id": "JPN_J1",
        "competition": "J1 League",
        "kickoff_time_utc": datetime(2026, 5, 7, 10, 0, tzinfo=UTC),
        "home_team": {"team_id": "kaw", "name": "Kawasaki Frontale"},
        "away_team": {"team_id": "yfm", "name": "Yokohama F. Marinos"},
        "home_lambda": 1.28,
        "away_lambda": 1.22,
        "prediction_time_utc": datetime(2026, 5, 6, 11, 30, tzinfo=UTC),
        "status": "beta",
        "confidence": "low",
        "data_quality_score": 66.0,
        "cn_handicap": 0,
        "asian_handicap_line": 0.0,
        "european_handicap": 0,
        "market_1x2": {"home_win": 0.332, "draw": 0.268, "away_win": 0.400},
        "market_cn_handicap_1x2": {
            "handicap_home_win": 0.332,
            "handicap_draw": 0.268,
            "handicap_away_win": 0.400,
        },
        "market_european_handicap_1x2": {
            "handicap_home_win": 0.332,
            "handicap_draw": 0.268,
            "handicap_away_win": 0.400,
        },
        "key_factors": {
            "model": ["双方期望进球接近，平局和一球差结果权重较高。"],
            "market": ["市场更偏向客队，模型未给出同等幅度。"],
            "lineup": ["阵容/伤停覆盖不足，降低置信度。"],
            "schedule": ["赛程日历差异可能影响 baseline 参数稳定性。"],
            "uncertainty": ["Beta 赛事且数据质量 C，不进入自动串关候选。"],
        },
    },
]


def list_mock_fixtures() -> list[MockFixture]:
    return list(_FIXTURES)


def get_mock_fixture(fixture_id: str) -> MockFixture | None:
    return next((fixture for fixture in _FIXTURES if fixture["fixture_id"] == fixture_id), None)
