from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.parlay import ParlayLegSelection
from nutmeg.parlay import (
    PostgresParlayRecommendationRepository,
    evaluate_parlay,
    parlay_recommendation_input_from_payload,
)
from nutmeg.parlay.repository import (
    INSERT_PARLAY_ATOMIC_BET_QUERY,
    INSERT_PARLAY_LEG_QUERY,
    INSERT_PARLAY_RECOMMENDATION_QUERY,
    LIST_UNSETTLED_PARLAY_ATOMIC_BETS_QUERY,
    UPDATE_PARLAY_ATOMIC_BET_SETTLEMENT_QUERY,
    UPDATE_PARLAY_RECOMMENDATION_SETTLEMENT_SUMMARY_QUERY,
    UPSERT_PARLAY_MODEL_VERSION_QUERY,
)


class FakeParlayDatabase:
    def __init__(self, settlement_rows: Sequence[DatabaseRow] = ()) -> None:
        self.settlement_rows = list(settlement_rows)
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.next_leg_id = 501
        self.next_atomic_bet_id = 701

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        if query == UPSERT_PARLAY_MODEL_VERSION_QUERY:
            return {"model_version": params["model_version"]}
        if query == INSERT_PARLAY_RECOMMENDATION_QUERY:
            return {
                "parlay_recommendation_id": 301,
                "created_at": datetime(2026, 5, 6, 12, tzinfo=UTC),
            }
        if query == INSERT_PARLAY_LEG_QUERY:
            row = {"parlay_leg_id": self.next_leg_id}
            self.next_leg_id += 1
            return row
        if query == INSERT_PARLAY_ATOMIC_BET_QUERY:
            row = {"atomic_bet_id": self.next_atomic_bet_id}
            self.next_atomic_bet_id += 1
            return row
        if query == UPDATE_PARLAY_ATOMIC_BET_SETTLEMENT_QUERY:
            return {"atomic_bet_id": params["atomic_bet_id"]}
        if query == UPDATE_PARLAY_RECOMMENDATION_SETTLEMENT_SUMMARY_QUERY:
            return {"parlay_recommendation_id": params["parlay_recommendation_id"]}
        raise AssertionError(f"unexpected query: {query}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        if query == LIST_UNSETTLED_PARLAY_ATOMIC_BETS_QUERY:
            return self.settlement_rows
        raise AssertionError(f"unexpected query: {query}")


def test_postgres_parlay_repository_persists_recommendation_legs_and_atomic_bets() -> None:
    database = FakeParlayDatabase()
    evaluation = evaluate_parlay(
        [
            ParlayLegSelection(
                fixture_id="fix_a",
                market_type="1x2",
                outcomes=["home_win", "draw"],
                probabilities={"home_win": 0.6, "draw": 0.25},
                odds={"home_win": 2.0, "draw": 3.1},
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=101,
            ),
            ParlayLegSelection(
                fixture_id="fix_b",
                market_type="1x2",
                outcomes=["away_win"],
                probabilities={"away_win": 0.5},
                odds={"away_win": 1.8},
                model_version="poisson-m1.0.0",
                prediction_snapshot_id=102,
            ),
        ],
        pass_type="2x1",
        unit_stake=2,
    )

    stored = PostgresParlayRecommendationRepository(database).save_recommendation(
        parlay_recommendation_input_from_payload(
            recommendation_key="parlay-test",
            model_version="poisson-m1.0.0",
            strategy="balanced",
            pass_type=evaluation.pass_type,
            is_multiple=evaluation.is_multiple,
            unit_stake=evaluation.unit_stake,
            total_stake=evaluation.total_stake,
            hit_probability=evaluation.hit_probability,
            expected_payout=evaluation.expected_payout,
            expected_value=evaluation.expected_value,
            roi=evaluation.roi,
            risk_score=evaluation.risk_score,
            risk_level=evaluation.risk_level,
            correlation_penalty=evaluation.correlation_penalty,
            rule_valid=evaluation.rule_valid,
            explanation_json=evaluation.explanation_json,
            atomic_bets=evaluation.atomic_bets,
        )
    )

    queries = [query for query, _params in database.fetch_one_calls]
    assert queries.count(UPSERT_PARLAY_MODEL_VERSION_QUERY) == 1
    assert queries.count(INSERT_PARLAY_RECOMMENDATION_QUERY) == 1
    assert queries.count(INSERT_PARLAY_LEG_QUERY) == 2
    assert queries.count(INSERT_PARLAY_ATOMIC_BET_QUERY) == 2
    assert stored.parlay_recommendation_id == 301
    assert stored.parlay_leg_ids == [501, 502]
    assert stored.atomic_bet_ids == [701, 702]
    recommendation_params = database.fetch_one_calls[1][1]
    assert recommendation_params["model_version"] == "poisson-m1.0.0"
    assert recommendation_params["prediction_snapshot_ids_json"] == "[101,102]"


def test_postgres_parlay_repository_settles_unsettled_atomic_bets() -> None:
    database = FakeParlayDatabase(
        settlement_rows=[
            {
                "atomic_bet_id": 701,
                "parlay_recommendation_id": 301,
                "model_version": "poisson-m1.0.0",
                "outcomes_json": [
                    {
                        "fixture_id": "fix_a",
                        "market_type": "1x2",
                        "outcome": "home_win",
                    }
                ],
                "stake": 2,
                "odds_product": 2,
                "result_rows_json": [
                    {"fixture_id": "fix_a", "home_goals": 2, "away_goals": 0}
                ],
            },
            {
                "atomic_bet_id": 702,
                "parlay_recommendation_id": 301,
                "model_version": "poisson-m1.0.0",
                "outcomes_json": [
                    {
                        "fixture_id": "fix_b",
                        "market_type": "1x2",
                        "outcome": "away_win",
                    }
                ],
                "stake": 2,
                "odds_product": 2,
                "result_rows_json": [],
            },
        ]
    )

    run = PostgresParlayRecommendationRepository(database).settle_unsettled_atomic_bets(
        model_version="poisson-m1.0.0",
        settled_at=datetime(2026, 5, 7, 12, tzinfo=UTC),
    )

    assert database.fetch_all_calls == [
        (
            LIST_UNSETTLED_PARLAY_ATOMIC_BETS_QUERY,
            {"model_version": "poisson-m1.0.0", "limit": 100},
        )
    ]
    assert run.checked_atomic_bets == 2
    assert run.settled_atomic_bets == 1
    assert run.unresolved_atomic_bets == 1
    update_params = [
        params
        for query, params in database.fetch_one_calls
        if query == UPDATE_PARLAY_ATOMIC_BET_SETTLEMENT_QUERY
    ][0]
    assert update_params["atomic_bet_id"] == 701
    assert update_params["result_status"] == "won"
    assert update_params["gross_payout"] == 4
    assert update_params["profit_loss"] == 2
