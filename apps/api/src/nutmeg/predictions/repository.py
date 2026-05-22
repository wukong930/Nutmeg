from __future__ import annotations

from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.domain.prediction import PredictionSnapshot

UPSERT_MODEL_VERSION_FOR_PREDICTION_QUERY = """
INSERT INTO model_versions (
  model_version,
  model_family,
  status,
  feature_version,
  calibration_version,
  metrics_json,
  params_json,
  activated_at
) VALUES (
  %(model_version)s,
  %(model_family)s,
  %(status)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(metrics_json)s::jsonb,
  %(params_json)s::jsonb,
  %(activated_at)s
)
ON CONFLICT (model_version) DO UPDATE SET
  model_family = EXCLUDED.model_family,
  feature_version = EXCLUDED.feature_version,
  calibration_version = EXCLUDED.calibration_version,
  metrics_json = model_versions.metrics_json || EXCLUDED.metrics_json,
  params_json = model_versions.params_json || EXCLUDED.params_json
RETURNING model_version
"""

INSERT_SCORE_GRID_QUERY = """
INSERT INTO score_probability_grids (
  fixture_id,
  prediction_time_utc,
  model_version,
  calibration_version,
  max_goals,
  grid_json,
  tail_mass,
  lambda_home,
  lambda_away
) VALUES (
  %(fixture_id)s,
  %(prediction_time_utc)s,
  %(model_version)s,
  %(calibration_version)s,
  %(max_goals)s,
  %(grid_json)s::jsonb,
  %(tail_mass)s,
  %(lambda_home)s,
  %(lambda_away)s
)
RETURNING score_grid_id
"""

INSERT_POSTGRES_PREDICTION_SNAPSHOT_QUERY = """
INSERT INTO prediction_snapshots (
  fixture_id,
  prediction_time_utc,
  model_version,
  feature_version,
  calibration_version,
  feature_snapshot_id,
  score_grid_id,
  p_home,
  p_draw,
  p_away,
  market_probabilities_json,
  uncertainty,
  data_quality_score,
  explanation_json
) VALUES (
  %(fixture_id)s,
  %(prediction_time_utc)s,
  %(model_version)s,
  %(feature_version)s,
  %(calibration_version)s,
  %(feature_snapshot_id)s,
  %(score_grid_id)s,
  %(p_home)s,
  %(p_draw)s,
  %(p_away)s,
  %(market_probabilities_json)s::jsonb,
  %(uncertainty)s,
  %(data_quality_score)s,
  %(explanation_json)s::jsonb
)
RETURNING prediction_snapshot_id
"""

INSERT_MARKET_PREDICTION_QUERY = """
INSERT INTO market_predictions (
  prediction_snapshot_id,
  fixture_id,
  market_type,
  line,
  side,
  outcome,
  probability,
  fair_odds,
  settlement_rule_json
) VALUES (
  %(prediction_snapshot_id)s,
  %(fixture_id)s,
  %(market_type)s,
  %(line)s,
  %(side)s,
  %(outcome)s,
  %(probability)s,
  %(fair_odds)s,
  %(settlement_rule_json)s::jsonb
)
RETURNING market_prediction_id
"""


class StoredPredictionSnapshot(BaseModel):
    snapshot_id: str
    path: str
    snapshot: PredictionSnapshot


class StoredPostgresPredictionSnapshot(BaseModel):
    prediction_snapshot_id: int = Field(gt=0)
    score_grid_id: int = Field(gt=0)
    snapshot: PredictionSnapshot


class PredictionSnapshotRepository(Protocol):
    def save(self, snapshot: PredictionSnapshot) -> StoredPredictionSnapshot: ...

    def get(self, snapshot_id: str) -> PredictionSnapshot | None: ...

    def list_for_fixture(self, fixture_id: str) -> list[PredictionSnapshot]: ...

    def latest_for_fixture(self, fixture_id: str) -> PredictionSnapshot | None: ...


class PredictionSnapshotWriteDatabaseExecutor(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a write statement with RETURNING and return one mapping row."""


def prediction_snapshot_id(snapshot: PredictionSnapshot) -> str:
    raw_key = "|".join(
        [
            snapshot.fixture_id,
            snapshot.prediction_time_utc.isoformat(),
            snapshot.model_version,
            snapshot.feature_version,
            snapshot.calibration_version,
        ]
    )
    return sha256(raw_key.encode("utf-8")).hexdigest()[:24]


class FilePredictionSnapshotRepository:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: PredictionSnapshot) -> StoredPredictionSnapshot:
        snapshot_id = prediction_snapshot_id(snapshot)
        path = self._path_for(snapshot_id)
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        return StoredPredictionSnapshot(
            snapshot_id=snapshot_id,
            path=str(path),
            snapshot=snapshot,
        )

    def get(self, snapshot_id: str) -> PredictionSnapshot | None:
        path = self._path_for(snapshot_id)
        if not path.exists():
            return None
        return PredictionSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def list_for_fixture(self, fixture_id: str) -> list[PredictionSnapshot]:
        snapshots = [
            snapshot
            for snapshot in (self.get(path.stem) for path in sorted(self.root_dir.glob("*.json")))
            if snapshot is not None and snapshot.fixture_id == fixture_id
        ]
        return sorted(snapshots, key=lambda snapshot: snapshot.prediction_time_utc)

    def latest_for_fixture(self, fixture_id: str) -> PredictionSnapshot | None:
        snapshots = self.list_for_fixture(fixture_id)
        if not snapshots:
            return None
        return snapshots[-1]

    def _path_for(self, snapshot_id: str) -> Path:
        if not snapshot_id or "/" in snapshot_id:
            raise ValueError("snapshot_id must be a non-empty file-safe id")
        return self.root_dir / f"{snapshot_id}.json"


class PostgresPredictionSnapshotRepository:
    def __init__(
        self,
        database: PredictionSnapshotWriteDatabaseExecutor,
        *,
        ensure_model_version: bool = True,
    ) -> None:
        self.database = database
        self.ensure_model_version = ensure_model_version

    def save(self, snapshot: PredictionSnapshot) -> StoredPostgresPredictionSnapshot:
        if self.ensure_model_version:
            self._upsert_model_version(snapshot)
        score_grid_id = self._insert_score_grid(snapshot)
        prediction_snapshot_id = self._insert_prediction_snapshot(
            snapshot,
            score_grid_id=score_grid_id,
        )
        self._insert_market_predictions(
            snapshot,
            prediction_snapshot_id=prediction_snapshot_id,
        )
        return StoredPostgresPredictionSnapshot(
            prediction_snapshot_id=prediction_snapshot_id,
            score_grid_id=score_grid_id,
            snapshot=snapshot,
        )

    def _upsert_model_version(self, snapshot: PredictionSnapshot) -> None:
        model_notes = snapshot.explanation_json.get("model_notes", {})
        _required_row(
            self.database.fetch_one(
                UPSERT_MODEL_VERSION_FOR_PREDICTION_QUERY,
                {
                    "model_version": snapshot.model_version,
                    "model_family": _model_family(snapshot),
                    "status": "active",
                    "feature_version": snapshot.feature_version,
                    "calibration_version": snapshot.calibration_version,
                    "metrics_json": _json({"source": "prematch_prediction_pipeline"}),
                    "params_json": _json(
                        {
                            "source": "prediction_snapshot_writer",
                            "model_notes": model_notes
                            if isinstance(model_notes, dict)
                            else {},
                        }
                    ),
                    "activated_at": snapshot.prediction_time_utc,
                },
            )
        )

    def _insert_score_grid(self, snapshot: PredictionSnapshot) -> int:
        score_grid = snapshot.score_grid
        row = _required_row(
            self.database.fetch_one(
                INSERT_SCORE_GRID_QUERY,
                {
                    "fixture_id": snapshot.fixture_id,
                    "prediction_time_utc": snapshot.prediction_time_utc,
                    "model_version": snapshot.model_version,
                    "calibration_version": snapshot.calibration_version,
                    "max_goals": score_grid.max_goals,
                    "grid_json": _json(score_grid.grid),
                    "tail_mass": score_grid.tail_mass,
                    "lambda_home": score_grid.lambda_home,
                    "lambda_away": score_grid.lambda_away,
                },
            )
        )
        return _int(row["score_grid_id"])

    def _insert_prediction_snapshot(
        self,
        snapshot: PredictionSnapshot,
        *,
        score_grid_id: int,
    ) -> int:
        row = _required_row(
            self.database.fetch_one(
                INSERT_POSTGRES_PREDICTION_SNAPSHOT_QUERY,
                {
                    "fixture_id": snapshot.fixture_id,
                    "prediction_time_utc": snapshot.prediction_time_utc,
                    "model_version": snapshot.model_version,
                    "feature_version": snapshot.feature_version,
                    "calibration_version": snapshot.calibration_version,
                    "feature_snapshot_id": snapshot.feature_snapshot_id,
                    "score_grid_id": score_grid_id,
                    "p_home": snapshot.p_home,
                    "p_draw": snapshot.p_draw,
                    "p_away": snapshot.p_away,
                    "market_probabilities_json": _json(snapshot.market_probabilities),
                    "uncertainty": snapshot.uncertainty,
                    "data_quality_score": snapshot.data_quality_score,
                    "explanation_json": _json(snapshot.explanation_json),
                },
            )
        )
        return _int(row["prediction_snapshot_id"])

    def _insert_market_predictions(
        self,
        snapshot: PredictionSnapshot,
        *,
        prediction_snapshot_id: int,
    ) -> None:
        for market_prediction in _market_prediction_rows(
            snapshot,
            prediction_snapshot_id=prediction_snapshot_id,
        ):
            _required_row(
                self.database.fetch_one(
                    INSERT_MARKET_PREDICTION_QUERY,
                    market_prediction,
                )
            )


def _model_family(snapshot: PredictionSnapshot) -> str:
    model_family = snapshot.explanation_json.get("model_family")
    if isinstance(model_family, str) and model_family:
        return model_family
    return snapshot.model_version.split("-", maxsplit=1)[0] or "unknown"


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise ValueError("expected database RETURNING row")
    return row


def _json(value: object) -> str:
    return dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    return int(str(value))


def _market_prediction_rows(
    snapshot: PredictionSnapshot,
    *,
    prediction_snapshot_id: int,
) -> list[QueryParams]:
    rows: list[QueryParams] = []
    for market_key, probability_payload in snapshot.market_probabilities.items():
        market_type, side, line = _parse_market_probability_key(market_key)
        if isinstance(probability_payload, dict):
            for outcome, probability in probability_payload.items():
                if outcome == "expected_return":
                    continue
                rows.append(
                    _market_prediction_row(
                        snapshot,
                        prediction_snapshot_id=prediction_snapshot_id,
                        market_key=market_key,
                        market_type=market_type,
                        side=side,
                        line=line,
                        outcome=outcome,
                        probability=float(probability),
                    )
                )
        elif isinstance(probability_payload, list):
            for item in probability_payload:
                option_key = item.get("option_key")
                item_probability = item.get("probability")
                if option_key is None or item_probability is None:
                    continue
                rows.append(
                    _market_prediction_row(
                        snapshot,
                        prediction_snapshot_id=prediction_snapshot_id,
                        market_key=market_key,
                        market_type=market_type,
                        side=side,
                        line=line,
                        outcome=str(option_key),
                        probability=float(item_probability),
                    )
                )
    return rows


def _market_prediction_row(
    snapshot: PredictionSnapshot,
    *,
    prediction_snapshot_id: int,
    market_key: str,
    market_type: str,
    side: str | None,
    line: float | None,
    outcome: str,
    probability: float,
) -> QueryParams:
    return {
        "prediction_snapshot_id": prediction_snapshot_id,
        "fixture_id": snapshot.fixture_id,
        "market_type": market_type,
        "line": line,
        "side": side,
        "outcome": outcome,
        "probability": probability,
        "fair_odds": (1.0 / probability if probability > 0 else None),
        "settlement_rule_json": _json(
            {
                "source_market_key": market_key,
                "probability_basis": "score_probability_grid",
                "model_version": snapshot.model_version,
                "prediction_time_utc": snapshot.prediction_time_utc.isoformat(),
            }
        ),
    }


def _parse_market_probability_key(
    market_key: str,
) -> tuple[str, str | None, float | None]:
    parts = market_key.split(":")
    market_type = parts[0]
    if market_type == "asian_handicap" and len(parts) >= 3:
        return market_type, parts[1] or None, float(parts[2])
    if market_type in {"cn_handicap_1x2", "european_handicap_1x2"} and len(parts) >= 2:
        return market_type, None, float(parts[1])
    if market_type == "correct_score_top_n":
        return "correct_score", None, None
    return market_type, None, None
