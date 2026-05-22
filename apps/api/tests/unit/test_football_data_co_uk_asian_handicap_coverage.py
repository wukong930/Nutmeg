from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations.football_data_co_uk_asian_handicap_coverage import (
    FootballDataCoUkAsianHandicapCoverageOptions,
    _options_from_args,
    _parse_args,
    asian_handicap_odds_movements_from_row,
    build_football_data_co_uk_asian_handicap_coverage_report,
    main,
)


def test_football_data_co_uk_asian_handicap_coverage_parses_opening_and_closing(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(tmp_path / "E0.csv")

    report = build_football_data_co_uk_asian_handicap_coverage_report(
        [csv_path],
        options=FootballDataCoUkAsianHandicapCoverageOptions(),
    )

    assert report.source_count == 1
    assert report.row_count == 2
    assert report.importable_row_count == 1
    assert report.skipped_row_count == 1
    assert report.importable_row_coverage == 0.5
    assert report.line_changed_count == 1
    assert report.competition_importable_row_counts == {"E0": 1}
    row = report.importable_rows_sample[0]
    assert row.source_division == "E0"
    assert row.home_team_name == "Arsenal"
    assert row.opening.line == -0.5
    assert row.closing.line == -0.75
    assert row.opening.odds_prefix == "Avg"
    assert row.closing.odds_prefix == "AvgC"
    assert row.line_delta == -0.25


def test_football_data_co_uk_asian_handicap_row_builds_odds_movements(
    tmp_path: Path,
) -> None:
    report = build_football_data_co_uk_asian_handicap_coverage_report(
        [_write_csv(tmp_path / "E0.csv")]
    )
    row = report.importable_rows_sample[0]

    movements = asian_handicap_odds_movements_from_row(
        row,
        feature_time_utc=datetime(2026, 5, 8, 18, 55, tzinfo=UTC),
        opening_snapshot_time_utc=datetime(2026, 5, 1, 18, 55, tzinfo=UTC),
    )

    assert [movement.outcome for movement in movements] == ["home_cover", "away_cover"]
    assert movements[0].market_type == "asian_handicap"
    assert movements[0].points[0].decimal_odds == 1.95
    assert movements[0].points[1].decimal_odds == 1.88
    assert movements[0].metadata_json["opening_line"] == -0.5
    assert movements[0].metadata_json["closing_line"] == -0.75
    assert movements[0].metadata_json["line_changed"] is True


def test_football_data_co_uk_asian_handicap_coverage_cli_writes_report(
    tmp_path: Path,
) -> None:
    csv_path = _write_csv(tmp_path / "E0.csv")
    output_path = tmp_path / "report.json"

    args = _parse_args(
        [
            str(csv_path),
            "--output-path",
            str(output_path),
            "--audit-id",
            "unit-ah-audit",
            "--max-rows-per-file",
            "5",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == output_path
    assert options.audit_id == "unit-ah-audit"
    assert options.max_rows_per_file == 5

    main(
        [
            str(csv_path),
            "--output-path",
            str(output_path),
            "--audit-id",
            "unit-ah-audit",
        ]
    )

    assert output_path.exists()
    payload = output_path.read_text(encoding="utf-8")
    assert '"audit_id": "unit-ah-audit"' in payload
    assert '"importable_row_count": 1' in payload


def _write_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,AHh,AvgAHH,AvgAHA,"
                "AHCh,AvgCAHH,AvgCAHA",
                "E0,08/05/2026,19:00,Arsenal,Liverpool,2,1,-0.5,1.95,1.90,"
                "-0.75,1.88,2.02",
                "E0,09/05/2026,19:00,Chelsea,Everton,1,1,,,,,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path
