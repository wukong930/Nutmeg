from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from csv import DictReader
from datetime import UTC, datetime, timedelta
from json import dumps
from pathlib import Path
from re import sub
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.domain.features import (
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
)

type FootballDataCoUkAsianHandicapSide = Literal["home", "away"]
type FootballDataCoUkAsianHandicapSnapshotKind = Literal["opening", "closing"]

FOOTBALL_DATA_CO_UK_ASIAN_HANDICAP_SOURCE_URL = "https://www.football-data.co.uk/data.php"
DEFAULT_FOOTBALL_DATA_CO_UK_ASIAN_HANDICAP_AUDIT_ID = (
    "football-data-co-uk-asian-handicap-coverage-v3.1"
)
DEFAULT_ASIAN_HANDICAP_PREFIX_PAIRS: tuple[tuple[str, str], ...] = (
    ("Avg", "AvgC"),
    ("B365", "B365C"),
    ("Max", "MaxC"),
    ("P", "PC"),
    ("BFE", "BFEC"),
)


class FootballDataCoUkAsianHandicapCoverageOptions(BaseModel):
    audit_id: str = DEFAULT_FOOTBALL_DATA_CO_UK_ASIAN_HANDICAP_AUDIT_ID
    prefix_pairs: tuple[tuple[str, str], ...] = DEFAULT_ASIAN_HANDICAP_PREFIX_PAIRS
    max_rows_per_file: int | None = Field(default=None, ge=1)
    opening_snapshot_lead_days: int = Field(default=7, ge=1)
    closing_snapshot_lead_minutes: int = Field(default=5, ge=1)


class FootballDataCoUkAsianHandicapSnapshot(BaseModel):
    kind: FootballDataCoUkAsianHandicapSnapshotKind
    line: float
    home_decimal_odds: float = Field(gt=1.0)
    away_decimal_odds: float = Field(gt=1.0)
    home_probability: float = Field(ge=0.0, le=1.0)
    away_probability: float = Field(ge=0.0, le=1.0)
    overround: float = Field(gt=0.0)
    odds_prefix: str


class FootballDataCoUkAsianHandicapRow(BaseModel):
    source_path: Path
    source_file_name: str
    source_division: str
    source_season: str | None = None
    row_number: int = Field(ge=2)
    kickoff_time_utc: datetime
    home_team_name: str
    away_team_name: str
    actual_home_goals: int | None = Field(default=None, ge=0)
    actual_away_goals: int | None = Field(default=None, ge=0)
    opening: FootballDataCoUkAsianHandicapSnapshot
    closing: FootballDataCoUkAsianHandicapSnapshot

    @property
    def line_changed(self) -> bool:
        return abs(self.opening.line - self.closing.line) > 1e-9

    @property
    def line_delta(self) -> float:
        return self.closing.line - self.opening.line


class FootballDataCoUkAsianHandicapFileSummary(BaseModel):
    source_path: Path
    source_file_name: str
    source_division: str
    source_season: str | None = None
    row_count: int = Field(ge=0)
    importable_row_count: int = Field(ge=0)
    skipped_row_count: int = Field(ge=0)
    selected_prefix_pair_counts: dict[str, int] = Field(default_factory=dict)
    line_changed_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @property
    def importable_row_coverage(self) -> float | None:
        if self.row_count == 0:
            return None
        return self.importable_row_count / self.row_count


class FootballDataCoUkAsianHandicapCoverageReport(BaseModel):
    audit_id: str
    source_url: str = FOOTBALL_DATA_CO_UK_ASIAN_HANDICAP_SOURCE_URL
    source_count: int = Field(ge=0)
    row_count: int = Field(ge=0)
    importable_row_count: int = Field(ge=0)
    skipped_row_count: int = Field(ge=0)
    importable_row_coverage: float | None = None
    line_changed_count: int = Field(ge=0)
    file_summaries: list[FootballDataCoUkAsianHandicapFileSummary] = (
        Field(default_factory=list)
    )
    importable_rows_sample: list[FootballDataCoUkAsianHandicapRow] = Field(
        default_factory=list
    )
    competition_row_counts: dict[str, int] = Field(default_factory=dict)
    competition_importable_row_counts: dict[str, int] = Field(default_factory=dict)
    season_importable_row_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_football_data_co_uk_asian_handicap_coverage_report(
    input_paths: Sequence[Path | str],
    *,
    options: FootballDataCoUkAsianHandicapCoverageOptions | None = None,
) -> FootballDataCoUkAsianHandicapCoverageReport:
    resolved_options = options or FootballDataCoUkAsianHandicapCoverageOptions()
    csv_paths = _csv_paths(input_paths)
    if not csv_paths:
        raise ValueError("football-data.co.uk Asian handicap coverage needs CSV inputs")

    file_summaries: list[FootballDataCoUkAsianHandicapFileSummary] = []
    row_samples: list[FootballDataCoUkAsianHandicapRow] = []
    competition_row_counts: Counter[str] = Counter()
    competition_importable_row_counts: Counter[str] = Counter()
    season_importable_row_counts: Counter[str] = Counter()
    warnings: list[str] = []

    for csv_path in csv_paths:
        file_result = _parse_file(csv_path, options=resolved_options)
        file_summaries.append(file_result.summary)
        warnings.extend(file_result.summary.warnings)
        competition_row_counts[file_result.summary.source_division] += (
            file_result.summary.row_count
        )
        competition_importable_row_counts[file_result.summary.source_division] += (
            file_result.summary.importable_row_count
        )
        if file_result.summary.source_season is not None:
            season_importable_row_counts[file_result.summary.source_season] += (
                file_result.summary.importable_row_count
            )
        for row in file_result.rows:
            if len(row_samples) < 20:
                row_samples.append(row)

    row_count = sum(summary.row_count for summary in file_summaries)
    importable_row_count = sum(
        summary.importable_row_count for summary in file_summaries
    )
    skipped_row_count = sum(summary.skipped_row_count for summary in file_summaries)
    line_changed_count = sum(summary.line_changed_count for summary in file_summaries)
    if importable_row_count == 0:
        warnings.append("football_data_co_uk_asian_handicap:no_importable_rows")
    if any(summary.source_division == "JPN" for summary in file_summaries) and (
        competition_importable_row_counts["JPN"] == 0
    ):
        warnings.append("football_data_co_uk_asian_handicap:japan_no_ah_columns")

    coverage = importable_row_count / row_count if row_count else None
    summary_json: dict[str, object] = {
        "calculation_basis": "football_data_co_uk_asian_handicap_coverage_v3_1",
        "audit_id": resolved_options.audit_id,
        "source_count": len(file_summaries),
        "row_count": row_count,
        "importable_row_count": importable_row_count,
        "skipped_row_count": skipped_row_count,
        "importable_row_coverage": coverage,
        "line_changed_count": line_changed_count,
        "competition_row_counts": dict(competition_row_counts),
        "competition_importable_row_counts": dict(competition_importable_row_counts),
        "season_importable_row_counts": dict(season_importable_row_counts),
        "warnings": warnings,
    }
    return FootballDataCoUkAsianHandicapCoverageReport(
        audit_id=resolved_options.audit_id,
        source_count=len(file_summaries),
        row_count=row_count,
        importable_row_count=importable_row_count,
        skipped_row_count=skipped_row_count,
        importable_row_coverage=coverage,
        line_changed_count=line_changed_count,
        file_summaries=file_summaries,
        importable_rows_sample=row_samples,
        competition_row_counts=dict(competition_row_counts),
        competition_importable_row_counts=dict(competition_importable_row_counts),
        season_importable_row_counts=dict(season_importable_row_counts),
        warnings=warnings,
        summary_json=summary_json,
    )


def asian_handicap_odds_movements_from_row(
    row: FootballDataCoUkAsianHandicapRow,
    *,
    feature_time_utc: datetime,
    opening_snapshot_time_utc: datetime | None = None,
) -> list[PrematchOddsMovementFeature]:
    opening_time = opening_snapshot_time_utc or (
        _aware_utc(feature_time_utc) - timedelta(days=7)
    )
    closing_time = _aware_utc(feature_time_utc)
    return [
        _movement_for_side(
            row,
            side="home",
            opening_snapshot_time_utc=opening_time,
            closing_snapshot_time_utc=closing_time,
        ),
        _movement_for_side(
            row,
            side="away",
            opening_snapshot_time_utc=opening_time,
            closing_snapshot_time_utc=closing_time,
        ),
    ]


def parse_football_data_co_uk_asian_handicap_row(
    raw_row: Mapping[str, str | None],
    *,
    input_path: Path | str,
    row_number: int,
    options: FootballDataCoUkAsianHandicapCoverageOptions | None = None,
) -> FootballDataCoUkAsianHandicapRow | None:
    return _parse_row(
        raw_row,
        input_path=Path(input_path),
        row_number=row_number,
        options=options or FootballDataCoUkAsianHandicapCoverageOptions(),
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_football_data_co_uk_asian_handicap_coverage_report(
        args.input_paths,
        options=_options_from_args(args),
    )
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)


class _ParsedFileResult(BaseModel):
    summary: FootballDataCoUkAsianHandicapFileSummary
    rows: list[FootballDataCoUkAsianHandicapRow] = Field(default_factory=list)


def _parse_file(
    input_path: Path,
    *,
    options: FootballDataCoUkAsianHandicapCoverageOptions,
) -> _ParsedFileResult:
    warnings: list[str] = []
    importable_rows: list[FootballDataCoUkAsianHandicapRow] = []
    prefix_pair_counts: Counter[str] = Counter()
    row_count = 0
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = DictReader(handle)
        if not reader.fieldnames:
            warnings.append(
                f"football_data_co_uk_asian_handicap:no_header:{input_path}"
            )
            return _ParsedFileResult(
                summary=_file_summary(
                    input_path,
                    row_count=0,
                    rows=[],
                    prefix_pair_counts=prefix_pair_counts,
                    warnings=warnings,
                )
            )
        for row_number, raw_row in enumerate(reader, start=2):
            if options.max_rows_per_file is not None and row_count >= (
                options.max_rows_per_file
            ):
                break
            row_count += 1
            parsed = _parse_row(
                raw_row,
                input_path=input_path,
                row_number=row_number,
                options=options,
            )
            if parsed is None:
                continue
            importable_rows.append(parsed)
            prefix_pair_counts[
                f"{parsed.opening.odds_prefix}->{parsed.closing.odds_prefix}"
            ] += 1
    return _ParsedFileResult(
        summary=_file_summary(
            input_path,
            row_count=row_count,
            rows=importable_rows,
            prefix_pair_counts=prefix_pair_counts,
            warnings=warnings,
        ),
        rows=importable_rows,
    )


def _parse_row(
    raw_row: Mapping[str, str | None],
    *,
    input_path: Path,
    row_number: int,
    options: FootballDataCoUkAsianHandicapCoverageOptions,
) -> FootballDataCoUkAsianHandicapRow | None:
    selected = _select_asian_handicap_pair(raw_row, options=options)
    if selected is None:
        return None
    opening, closing = selected
    kickoff_time = _kickoff_time(raw_row, input_path=input_path)
    return FootballDataCoUkAsianHandicapRow(
        source_path=input_path,
        source_file_name=input_path.name,
        source_division=_source_division(input_path),
        source_season=_source_season(input_path),
        row_number=row_number,
        kickoff_time_utc=kickoff_time,
        home_team_name=_text(raw_row, "HomeTeam") or "Home",
        away_team_name=_text(raw_row, "AwayTeam") or "Away",
        actual_home_goals=_optional_int(raw_row, "FTHG"),
        actual_away_goals=_optional_int(raw_row, "FTAG"),
        opening=opening,
        closing=closing,
    )


def _select_asian_handicap_pair(
    row: Mapping[str, str | None],
    *,
    options: FootballDataCoUkAsianHandicapCoverageOptions,
) -> tuple[FootballDataCoUkAsianHandicapSnapshot, FootballDataCoUkAsianHandicapSnapshot] | None:
    for opening_prefix, closing_prefix in options.prefix_pairs:
        opening = _snapshot(
            row,
            kind="opening",
            line_column="AHh",
            odds_prefix=opening_prefix,
        )
        closing = _snapshot(
            row,
            kind="closing",
            line_column="AHCh",
            odds_prefix=closing_prefix,
        )
        if opening is not None and closing is not None:
            return opening, closing
    return None


def _snapshot(
    row: Mapping[str, str | None],
    *,
    kind: FootballDataCoUkAsianHandicapSnapshotKind,
    line_column: str,
    odds_prefix: str,
) -> FootballDataCoUkAsianHandicapSnapshot | None:
    line = _optional_float(row, line_column)
    home_odds = _optional_float(row, f"{odds_prefix}AHH")
    away_odds = _optional_float(row, f"{odds_prefix}AHA")
    if line is None or home_odds is None or away_odds is None:
        return None
    if home_odds <= 1.01 or away_odds <= 1.01:
        return None
    raw_home = 1.0 / home_odds
    raw_away = 1.0 / away_odds
    overround = raw_home + raw_away
    if overround <= 0:
        return None
    return FootballDataCoUkAsianHandicapSnapshot(
        kind=kind,
        line=line,
        home_decimal_odds=home_odds,
        away_decimal_odds=away_odds,
        home_probability=raw_home / overround,
        away_probability=raw_away / overround,
        overround=overround,
        odds_prefix=odds_prefix,
    )


def _movement_for_side(
    row: FootballDataCoUkAsianHandicapRow,
    *,
    side: FootballDataCoUkAsianHandicapSide,
    opening_snapshot_time_utc: datetime,
    closing_snapshot_time_utc: datetime,
) -> PrematchOddsMovementFeature:
    outcome = f"{side}_cover"
    opening_odds = (
        row.opening.home_decimal_odds
        if side == "home"
        else row.opening.away_decimal_odds
    )
    closing_odds = (
        row.closing.home_decimal_odds
        if side == "home"
        else row.closing.away_decimal_odds
    )
    opening_probability = (
        row.opening.home_probability if side == "home" else row.opening.away_probability
    )
    closing_probability = (
        row.closing.home_probability if side == "home" else row.closing.away_probability
    )
    suffix = "AHH" if side == "home" else "AHA"
    return PrematchOddsMovementFeature(
        market_type="asian_handicap",
        outcome=outcome,
        points=[
            PrematchOddsMovementPoint(
                snapshot_time_utc=_aware_utc(opening_snapshot_time_utc),
                market_type="asian_handicap",
                outcome=outcome,
                decimal_odds=opening_odds,
                fair_probability=opening_probability,
                source="football-data.co.uk",
                source_snapshot_ref=(
                    f"{row.source_file_name}:row_{row.row_number}:"
                    f"AHh:{row.opening.odds_prefix}{suffix}"
                ),
            ),
            PrematchOddsMovementPoint(
                snapshot_time_utc=_aware_utc(closing_snapshot_time_utc),
                market_type="asian_handicap",
                outcome=outcome,
                decimal_odds=closing_odds,
                fair_probability=closing_probability,
                source="football-data.co.uk",
                source_snapshot_ref=(
                    f"{row.source_file_name}:row_{row.row_number}:"
                    f"AHCh:{row.closing.odds_prefix}{suffix}"
                ),
            ),
        ],
        bookmaker_disagreement=abs(closing_probability - opening_probability),
        market_delay_signal=0.0,
        metadata_json={
            "source": "football-data.co.uk",
            "source_division": row.source_division,
            "source_season": row.source_season,
            "side": side,
            "opening_line": row.opening.line,
            "closing_line": row.closing.line,
            "line_delta": row.line_delta,
            "line_changed": row.line_changed,
            "opening_overround": round(row.opening.overround, 6),
            "closing_overround": round(row.closing.overround, 6),
            "opening_odds_prefix": row.opening.odds_prefix,
            "closing_odds_prefix": row.closing.odds_prefix,
        },
    )


def _file_summary(
    input_path: Path,
    *,
    row_count: int,
    rows: Sequence[FootballDataCoUkAsianHandicapRow],
    prefix_pair_counts: Counter[str],
    warnings: list[str],
) -> FootballDataCoUkAsianHandicapFileSummary:
    return FootballDataCoUkAsianHandicapFileSummary(
        source_path=input_path,
        source_file_name=input_path.name,
        source_division=_source_division(input_path),
        source_season=_source_season(input_path),
        row_count=row_count,
        importable_row_count=len(rows),
        skipped_row_count=row_count - len(rows),
        selected_prefix_pair_counts=dict(prefix_pair_counts),
        line_changed_count=sum(1 for row in rows if row.line_changed),
        warnings=warnings,
    )


def _csv_paths(input_paths: Sequence[Path | str]) -> list[Path]:
    paths: list[Path] = []
    for input_path in input_paths:
        path = Path(input_path)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.csv")))
        else:
            paths.append(path)
    return list(dict.fromkeys(paths))


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Audit football-data.co.uk Asian handicap column coverage."
    )
    parser.add_argument("input_paths", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--audit-id", default=DEFAULT_FOOTBALL_DATA_CO_UK_ASIAN_HANDICAP_AUDIT_ID)
    parser.add_argument("--max-rows-per-file", type=int, default=None)
    parser.add_argument("--opening-snapshot-lead-days", type=int, default=7)
    parser.add_argument("--closing-snapshot-lead-minutes", type=int, default=5)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> FootballDataCoUkAsianHandicapCoverageOptions:
    return FootballDataCoUkAsianHandicapCoverageOptions(
        audit_id=args.audit_id,
        max_rows_per_file=args.max_rows_per_file,
        opening_snapshot_lead_days=args.opening_snapshot_lead_days,
        closing_snapshot_lead_minutes=args.closing_snapshot_lead_minutes,
    )


def _kickoff_time(row: Mapping[str, str | None], *, input_path: Path) -> datetime:
    raw_date = _text(row, "Date")
    if raw_date is None:
        return datetime(1970, 1, 1, 12, 0, tzinfo=UTC)
    date_format = "%d/%m/%Y" if len(raw_date.split("/")[-1]) == 4 else "%d/%m/%y"
    parsed = datetime.strptime(raw_date, date_format).replace(tzinfo=UTC)
    raw_time = _text(row, "Time")
    if raw_time is None:
        return parsed.replace(hour=12, minute=0)
    hour_text, minute_text = raw_time.split(":", maxsplit=1)
    return parsed.replace(hour=int(hour_text), minute=int(minute_text[:2]))


def _source_division(input_path: Path) -> str:
    return input_path.stem


def _source_season(input_path: Path) -> str | None:
    for part in reversed(input_path.parts):
        if part.isdigit() and len(part) == 4:
            return f"20{part[:2]}-20{part[2:]}"
        if part.isdigit() and len(part) == 2:
            return f"20{part}-20{int(part) + 1:02d}"
    return None


def _optional_float(row: Mapping[str, str | None], column: str) -> float | None:
    value = _text(row, column)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(row: Mapping[str, str | None], column: str) -> int | None:
    value = _text(row, column)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _text(row: Mapping[str, str | None], column: str) -> str | None:
    value = row.get(column)
    if value is None:
        return None
    text = value.strip()
    return text or None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _slug(value: str) -> str:
    return sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
