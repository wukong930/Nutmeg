from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest

from nutmeg.accuracy import (
    build_handicap_performance_evidence_report,
    build_parlay_simulation_evidence_report,
    build_upset_precision_evidence_report,
)
from nutmeg.accuracy.promotion_evidence import (
    HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
    PARLAY_SIMULATION_EVIDENCE_QUERY,
    UPSET_PRECISION_EVIDENCE_QUERY,
    PostgresPromotionEvidenceRepository,
)
from nutmeg.database import DatabaseRow, QueryParams


class FakePromotionEvidenceDatabase:
    def __init__(self, rows_by_query: Mapping[str, Sequence[DatabaseRow]]) -> None:
        self.rows_by_query = rows_by_query
        self.calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.calls.append((query, params))
        return self.rows_by_query.get(query, [])


def test_upset_precision_evidence_scores_settled_target_outcomes() -> None:
    report = build_upset_precision_evidence_report(
        [
            _upset_row(
                "draw_overlooked",
                target_market_type="1x2",
                target_line=None,
                target_outcome="draw",
                home_goals=1,
                away_goals=1,
            ),
            _upset_row(
                "favorite_fail_to_cover",
                target_market_type="cn_handicap_1x2",
                target_line=-1,
                target_outcome="handicap_away_win",
                home_goals=1,
                away_goals=1,
            ),
            _upset_row(
                "favorite_loss",
                target_market_type=None,
                target_line=None,
                target_outcome=None,
                home_goals=2,
                away_goals=0,
            ),
        ],
        model_version="candidate",
        top_k=20,
    )

    assert report is not None
    assert report.sample_size == 2
    assert report.hit_count == 2
    assert report.precision_at_k == 1.0
    assert report.unresolved_count == 1
    assert report.metrics_json["upset_precision_source"] == "settled_upset_alerts"


def test_handicap_performance_evidence_scores_top_probability_against_settlement() -> None:
    report = build_handicap_performance_evidence_report(
        [
            _market_row(
                "fix_a",
                "cn_handicap_1x2",
                -1,
                None,
                "handicap_home_win",
                0.20,
                2,
                0,
            ),
            _market_row(
                "fix_a",
                "cn_handicap_1x2",
                -1,
                None,
                "handicap_draw",
                0.30,
                2,
                0,
            ),
            _market_row(
                "fix_a",
                "cn_handicap_1x2",
                -1,
                None,
                "handicap_away_win",
                0.50,
                2,
                0,
            ),
            _market_row(
                "fix_b",
                "asian_handicap",
                -0.75,
                "home",
                "half_win",
                0.60,
                1,
                0,
            ),
            _market_row(
                "fix_b",
                "asian_handicap",
                -0.75,
                "home",
                "full_loss",
                0.40,
                1,
                0,
            ),
        ],
        model_version="candidate",
        market_types=("cn_handicap_1x2", "asian_handicap"),
    )

    assert report is not None
    assert report.sample_size == 2
    assert report.correct_count == 1
    assert report.accuracy == 0.5
    assert report.brier_score is not None
    assert report.metrics_json["handicap_performance_source"] == (
        "settled_market_predictions"
    )


def test_parlay_simulation_evidence_settles_atomic_bets_from_results() -> None:
    report = build_parlay_simulation_evidence_report(
        [
            _parlay_row(
                [
                    {
                        "fixture_id": "fix_a",
                        "market_type": "1x2",
                        "outcome": "home_win",
                    },
                    {
                        "fixture_id": "fix_b",
                        "market_type": "cn_handicap_1x2",
                        "line": -1,
                        "outcome": "handicap_away_win",
                    },
                ],
                [
                    {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0},
                    {"fixture_id": "fix_b", "home_goals": 1, "away_goals": 1},
                ],
                stake=2,
                odds_product=3,
            ),
            _parlay_row(
                [
                    {
                        "fixture_id": "fix_c",
                        "market_type": "1x2",
                        "outcome": "away_win",
                    }
                ],
                [{"fixture_id": "fix_c", "home_goals": 1, "away_goals": 0}],
                stake=2,
                odds_product=2.5,
            ),
            _parlay_row(
                [
                    {
                        "fixture_id": "fix_d",
                        "market_type": "asian_handicap",
                        "line": -0.75,
                        "side": "home",
                        "outcome": "half_win",
                    }
                ],
                [],
                stake=2,
                odds_product=1.8,
            ),
        ],
        model_version="candidate",
    )

    assert report.status == "available"
    assert report.sample_size == 2
    assert report.won_atomic_bets == 1
    assert report.unresolved_count == 1
    assert report.total_stake == 4
    assert report.gross_payout == 6
    assert report.profit_loss == 2
    assert report.roi == pytest.approx(0.5)
    assert report.metrics_json["parlay_simulation_reason"] == (
        "settled_model_version_parlay_atomic_bets"
    )


def test_postgres_promotion_evidence_repository_uses_expected_queries() -> None:
    database = FakePromotionEvidenceDatabase(
        {
            UPSET_PRECISION_EVIDENCE_QUERY: [
                _upset_row(
                    "draw_overlooked",
                    target_market_type="1x2",
                    target_line=None,
                    target_outcome="draw",
                    home_goals=1,
                    away_goals=1,
                )
            ],
            HANDICAP_PERFORMANCE_EVIDENCE_QUERY: [
                _market_row(
                    "fix_a",
                    "cn_handicap_1x2",
                    -1,
                    None,
                    "handicap_home_win",
                    0.70,
                    2,
                    0,
                )
            ],
            PARLAY_SIMULATION_EVIDENCE_QUERY: [
                _parlay_row(
                    [
                        {
                            "fixture_id": "fix_a",
                            "market_type": "1x2",
                            "outcome": "home_win",
                        }
                    ],
                    [{"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0}],
                    stake=2,
                    odds_product=2,
                )
            ],
        }
    )
    repository = PostgresPromotionEvidenceRepository(database)

    upset = repository.get_upset_precision_at_k(
        model_version="candidate",
        top_k=5,
        competition_id="EPL",
    )
    handicap = repository.get_handicap_performance(
        model_version="candidate",
        market_types=("cn_handicap_1x2",),
        competition_id="EPL",
    )
    parlay = repository.get_parlay_simulation(
        model_version="candidate",
        competition_id="EPL",
    )

    assert upset is not None
    assert handicap is not None
    assert parlay.status == "available"
    assert database.calls[0] == (
        UPSET_PRECISION_EVIDENCE_QUERY,
        {"model_version": "candidate", "competition_id": "EPL", "top_k": 5},
    )
    assert database.calls[1] == (
        HANDICAP_PERFORMANCE_EVIDENCE_QUERY,
        {
            "model_version": "candidate",
            "competition_id": "EPL",
            "market_types": ["cn_handicap_1x2"],
        },
    )
    assert database.calls[2] == (
        PARLAY_SIMULATION_EVIDENCE_QUERY,
        {"model_version": "candidate", "competition_id": "EPL"},
    )
    assert handicap.accuracy == pytest.approx(1.0)
    assert parlay.roi == pytest.approx(1.0)


def _upset_row(
    upset_type: str,
    *,
    target_market_type: str | None,
    target_line: float | None,
    target_outcome: str | None,
    home_goals: int,
    away_goals: int,
) -> DatabaseRow:
    return {
        "upset_alert_id": 1,
        "fixture_id": "fix_a",
        "upset_type": upset_type,
        "target_market_type": target_market_type,
        "target_line": Decimal(str(target_line)) if target_line is not None else None,
        "target_outcome": target_outcome,
        "upset_score": Decimal("0.75"),
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def _market_row(
    fixture_id: str,
    market_type: str,
    line: float,
    side: str | None,
    outcome: str,
    probability: float,
    home_goals: int,
    away_goals: int,
) -> DatabaseRow:
    return {
        "fixture_id": fixture_id,
        "market_type": market_type,
        "line": Decimal(str(line)),
        "side": side,
        "outcome": outcome,
        "probability": Decimal(str(probability)),
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


def _parlay_row(
    outcomes_json: list[dict[str, object]],
    result_rows_json: list[dict[str, object]],
    *,
    stake: float,
    odds_product: float,
) -> DatabaseRow:
    return {
        "parlay_recommendation_id": 1,
        "model_version": "candidate",
        "strategy": "balanced",
        "pass_type": "2x1",
        "rule_valid": True,
        "atomic_bet_id": 10,
        "outcomes_json": outcomes_json,
        "stake": Decimal(str(stake)),
        "odds_product": Decimal(str(odds_product)),
        "expected_payout": Decimal("0"),
        "expected_value": Decimal("0"),
        "result_status": None,
        "gross_payout": None,
        "profit_loss": None,
        "result_rows_json": result_rows_json,
    }
