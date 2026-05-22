from __future__ import annotations

from datetime import UTC, datetime
from json import dumps
from pathlib import Path

from nutmeg.domain.features import (
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations import (
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSliceBuildOptions,
    build_historical_recommendation_slice_from_csv,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_slice_builder import _options_from_args, _parse_args


def test_historical_slice_builder_builds_deterministic_slice_from_csv() -> None:
    result = build_historical_recommendation_slice_from_csv(
        Path("configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv"),
        options=_sample_build_options(),
    )

    assert result.row_count == 6
    assert result.fixture_count == 2
    assert result.prediction_count == 6
    assert result.warnings == []
    assert result.slice.metadata.slice_id == "euro_2024_builder_sample_v1"
    assert result.slice.metadata.competition_id == "UEFA_EURO"
    assert result.slice.as_of_time_utc == datetime(2024, 6, 29, 12, tzinfo=UTC)
    assert result.slice.fixtures[0].fixture_id == "euro2024_r16_sui_ita"
    assert result.slice.fixtures[0].predictions[0].metadata_json == {
        "target_outcome": "home_win",
        "upset_score": 0.76,
        "upset_direction": "underdog_protection",
    }
    assert sum(prediction.probability for prediction in result.slice.fixtures[0].predictions) == 1


def test_historical_slice_builder_output_is_backtest_compatible() -> None:
    build_result = build_historical_recommendation_slice_from_csv(
        Path("configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv"),
        options=_sample_build_options(),
    )

    backtest = run_historical_recommendation_backtest(
        build_result.slice,
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            max_budget=4.0,
        ),
    )

    assert backtest.fixture_count == 2
    assert backtest.candidate_count == 6
    assert backtest.completed_count == 1
    assert backtest.final_answer is not None
    assert backtest.final_hit_sample_size == 1


def test_historical_slice_builder_accepts_fixture_feature_snapshot_json(
    tmp_path: Path,
) -> None:
    feature_snapshot = build_structured_prematch_feature_snapshot(
        fixture_id="hist_feature_001",
        competition_id="EPL",
        kickoff_time_utc=datetime(2026, 5, 8, 19, 0, tzinfo=UTC),
        feature_time_utc=datetime(2026, 5, 8, 17, 45, tzinfo=UTC),
        prematch_features=StructuredPrematchFeatureSet(
            odds_movements=[
                PrematchOddsMovementFeature(
                    market_type="1x2",
                    outcome="home_win",
                    points=[
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=2.20,
                            fair_probability=0.45,
                        ),
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=datetime(2026, 5, 8, 17, 30, tzinfo=UTC),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=1.95,
                            fair_probability=0.52,
                        ),
                    ],
                )
            ]
        ),
    )
    feature_payload = dumps(
        feature_snapshot.model_dump(mode="json"),
        separators=(",", ":"),
        sort_keys=True,
    ).replace('"', '""')
    input_csv = tmp_path / "historical_feature_snapshot.csv"
    input_csv.write_text(
        "\n".join(
            [
                "fixture_id,kickoff_time_utc,home_team_name,away_team_name,"
                "actual_home_goals,actual_away_goals,prediction_time_utc,"
                "model_version,outcome,probability,decimal_odds,feature_snapshot_json",
                'hist_feature_001,2026-05-08T19:00:00Z,Alpha,Bravo,2,1,'
                '2026-05-08T17:45:00Z,model-v1,home_win,0.52,1.95,'
                f'"{feature_payload}"',
                'hist_feature_001,2026-05-08T19:00:00Z,Alpha,Bravo,2,1,'
                '2026-05-08T17:45:00Z,model-v1,draw,0.25,3.40,'
                f'"{feature_payload}"',
                'hist_feature_001,2026-05-08T19:00:00Z,Alpha,Bravo,2,1,'
                '2026-05-08T17:45:00Z,model-v1,away_win,0.23,4.10,'
                f'"{feature_payload}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_historical_recommendation_slice_from_csv(
        input_csv,
        options=HistoricalRecommendationSliceBuildOptions(
            slice_id="feature_snapshot_slice",
            name="Feature snapshot slice",
            competition_id="EPL",
            as_of_time_utc=datetime(2026, 5, 8, 18, 0, tzinfo=UTC),
            season="2025-2026",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
    )

    fixture = result.slice.fixtures[0]
    assert result.summary_json["feature_snapshot_fixture_count"] == 1
    assert result.warnings == []
    assert fixture.feature_snapshot is not None
    assert fixture.feature_snapshot.fixture_id == "hist_feature_001"
    assert fixture.feature_snapshot.features_json["prematch_context"]["odds_movement"][
        0
    ]["current_prob"] == 0.52


def test_historical_slice_builder_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv",
            "--output-path",
            "tmp/generated_slice.json",
            "--slice-id",
            "builder_cli_slice",
            "--name",
            "Builder CLI Slice",
            "--competition-id",
            "UEFA_EURO",
            "--as-of-time-utc",
            "2024-06-29T12:00:00Z",
            "--season",
            "2024",
            "--result-source",
            "unit test results",
            "--odds-source",
            "unit test odds",
            "--prediction-source",
            "unit test predictions",
            "--source-url",
            "https://example.test/results",
            "--note",
            "deterministic builder test",
            "--probability-sum-tolerance",
            "0.01",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/generated_slice.json")
    assert options.slice_id == "builder_cli_slice"
    assert options.name == "Builder CLI Slice"
    assert options.competition_id == "UEFA_EURO"
    assert options.as_of_time_utc == datetime(2024, 6, 29, 12, tzinfo=UTC)
    assert options.season == "2024"
    assert options.source_urls == ("https://example.test/results",)
    assert options.notes == ("deterministic builder test",)
    assert options.probability_sum_tolerance == 0.01


def _sample_build_options() -> HistoricalRecommendationSliceBuildOptions:
    return HistoricalRecommendationSliceBuildOptions(
        slice_id="euro_2024_builder_sample_v1",
        name="Euro 2024 builder sample",
        competition_id="UEFA_EURO",
        as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
        season="2024",
        result_source="UEFA Euro 2024 public match records, builder sample",
        odds_source="Frozen consensus-style decimal odds CSV sample",
        prediction_source="Frozen Nutmeg-style pre-match probabilities CSV sample",
        source_urls=("https://www.uefa.com/euro2024/fixtures-results/",),
        notes=("Generated from canonical CSV input for builder tests.",),
    )
