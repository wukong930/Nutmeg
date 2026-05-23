"""Persist/load V4 model artifacts.

An artifact bundle captures everything needed to predict on a NEW fixture
WITHOUT re-reading the historical CSV. Contents:

  <artifact_dir>/
    booster_home.txt          # lightgbm Booster.save_model()
    booster_away.txt          # lightgbm Booster.save_model()
    metadata.json             # training cutoff, feature columns, hyperparams
    temperature.json          # calibration T (1.0 if not calibrated)
    team_state.json           # per (league, team): current Elo + recent goals,
                              # shots, last_match_date for form features

Loading replays the artifact into a `LoadedModel` that exposes `predict(fixtures)`.
Fixtures DataFrame must contain: league, home_team, away_team, date, psc_home,
psc_draw, psc_away, plus optional psc_over25/psc_under25/ahch when available.
The features required by GBM are computed on-the-fly from team_state.

Important: team_state is a SNAPSHOT at training cutoff. To predict matches AFTER
the cutoff, you'd typically apply results that have happened since (via
`apply_results(state, new_matches)`). For the MVP we predict matches very close
in time to the cutoff and accept some staleness.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from json import dump, load
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from nutmeg.v4.calibration.temperature import TemperatureCalibrator
from nutmeg.v4.features import GBM_FEATURE_COLUMNS
from nutmeg.v4.features.clubelo_features import build_clubelo_features
from nutmeg.v4.features.elo import DEFAULT_HOME_ADV, DEFAULT_INITIAL, DEFAULT_K
from nutmeg.v4.features.form import WINDOW as FORM_WINDOW
from nutmeg.v4.features.market import build_market_features
from nutmeg.v4.features.market_dynamics import build_market_dynamics_features
from nutmeg.v4.features.xg_lite import build_xg_lite_features


# --------- helpers --------------------------------------------------------

def _team_form_deques():
    return {
        "goals_for":              deque(maxlen=FORM_WINDOW),
        "goals_against":          deque(maxlen=FORM_WINDOW),
        "shots":                  deque(maxlen=FORM_WINDOW),
        "shots_on_target":        deque(maxlen=FORM_WINDOW),
        "shots_against":          deque(maxlen=FORM_WINDOW),
        "sot_against":            deque(maxlen=FORM_WINDOW),
        "last_match_iso":         None,
    }


# --------- artifact dataclass --------------------------------------------

@dataclass
class TeamState:
    """Per-(league, team) state needed for feature reconstruction."""
    elo: float
    goals_for: list[float]
    goals_against: list[float]
    shots: list[float]
    shots_on_target: list[float]
    last_match_iso: str | None
    # V5 W4 additions: opponent shot counts (for xG-lite defensive proxy).
    # Backward-compat: load_artifact uses .get() with default [] for older
    # team_state.json files without these keys.
    shots_against: list[float] = field(default_factory=list)
    sot_against: list[float] = field(default_factory=list)


@dataclass
class V4Artifact:
    metadata: dict[str, Any]
    feature_columns: list[str]
    booster_home: object  # lgb.Booster OR catboost.CatBoostRegressor
    booster_away: object
    temperature_T: float | None
    team_state: dict[str, dict[str, TeamState]]  # league → team → TeamState
    elo_initial: float = DEFAULT_INITIAL
    elo_k: float = DEFAULT_K
    elo_home_adv: float = DEFAULT_HOME_ADV
    # V5 W7 multi-backend support. model_type discriminates how predict_lambdas
    # invokes the boosters and how save/load (de)serialize them. cat_features
    # lists the categorical column names CatBoost uses (e.g. ["league"]);
    # empty for lightgbm.
    model_type: str = "lightgbm"
    cat_features: list[str] = field(default_factory=list)


# --------- save / load ----------------------------------------------------

def save_artifact(artifact: V4Artifact, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if artifact.model_type == "catboost":
        # CatBoost's native binary format. Note: the .cbm extension keeps the
        # file format implicit; load_model() relies on it.
        artifact.booster_home.save_model(str(out / "booster_home.cbm"))
        artifact.booster_away.save_model(str(out / "booster_away.cbm"))
    elif artifact.model_type == "lightgbm":
        artifact.booster_home.save_model(str(out / "booster_home.txt"))
        artifact.booster_away.save_model(str(out / "booster_away.txt"))
    else:
        raise ValueError(f"unknown model_type {artifact.model_type!r}")
    with open(out / "metadata.json", "w") as f:
        dump({
            "metadata": artifact.metadata,
            "feature_columns": artifact.feature_columns,
            "elo_initial": artifact.elo_initial,
            "elo_k": artifact.elo_k,
            "elo_home_adv": artifact.elo_home_adv,
            "model_type": artifact.model_type,
            "cat_features": list(artifact.cat_features),
        }, f, indent=2, default=str)
    with open(out / "temperature.json", "w") as f:
        dump({"T": artifact.temperature_T}, f)
    # team_state: flatten nested dataclass
    state_json: dict[str, dict[str, dict[str, Any]]] = {}
    for league, teams in artifact.team_state.items():
        state_json[league] = {}
        for team, st in teams.items():
            state_json[league][team] = {
                "elo": st.elo,
                "goals_for": st.goals_for,
                "goals_against": st.goals_against,
                "shots": st.shots,
                "shots_on_target": st.shots_on_target,
                "shots_against": st.shots_against,
                "sot_against": st.sot_against,
                "last_match_iso": st.last_match_iso,
            }
    with open(out / "team_state.json", "w") as f:
        dump(state_json, f, indent=2)
    return out


def load_artifact(in_dir: str | Path) -> V4Artifact:
    in_path = Path(in_dir)
    with open(in_path / "metadata.json") as f:
        meta = load(f)
    model_type = meta.get("model_type", "lightgbm")
    cat_features = list(meta.get("cat_features", []))

    if model_type == "catboost":
        import catboost as cb  # imported lazily so lightgbm-only deploys avoid the cost
        booster_home = cb.CatBoostRegressor()
        booster_home.load_model(str(in_path / "booster_home.cbm"))
        booster_away = cb.CatBoostRegressor()
        booster_away.load_model(str(in_path / "booster_away.cbm"))
    elif model_type == "lightgbm":
        booster_home = lgb.Booster(model_file=str(in_path / "booster_home.txt"))
        booster_away = lgb.Booster(model_file=str(in_path / "booster_away.txt"))
    else:
        raise ValueError(f"unknown model_type {model_type!r} in metadata.json")

    with open(in_path / "temperature.json") as f:
        T = load(f).get("T")
    with open(in_path / "team_state.json") as f:
        state_raw = load(f)
    team_state: dict[str, dict[str, TeamState]] = {}
    for league, teams in state_raw.items():
        team_state[league] = {
            team: TeamState(
                elo=t["elo"],
                goals_for=list(t["goals_for"]),
                goals_against=list(t["goals_against"]),
                shots=list(t["shots"]),
                shots_on_target=list(t["shots_on_target"]),
                last_match_iso=t.get("last_match_iso"),
                shots_against=list(t.get("shots_against", [])),
                sot_against=list(t.get("sot_against", [])),
            )
            for team, t in teams.items()
        }
    return V4Artifact(
        metadata=meta["metadata"],
        feature_columns=meta["feature_columns"],
        booster_home=booster_home,
        booster_away=booster_away,
        temperature_T=T,
        team_state=team_state,
        elo_initial=meta.get("elo_initial", DEFAULT_INITIAL),
        elo_k=meta.get("elo_k", DEFAULT_K),
        elo_home_adv=meta.get("elo_home_adv", DEFAULT_HOME_ADV),
        model_type=model_type,
        cat_features=cat_features,
    )


# --------- build artifact from training feature frame --------------------

def build_team_state(feature_df: pd.DataFrame) -> dict[str, dict[str, TeamState]]:
    """Walk the (already-feature-built) DataFrame to capture team state at the END.

    feature_df must have elo_home, elo_away columns (filled by build_elo_features).
    """
    df = feature_df.sort_values(["league", "date"]).reset_index(drop=True)

    # State accumulators
    elo: dict[tuple[str, str], float] = defaultdict(lambda: DEFAULT_INITIAL)
    g_for: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    g_ag: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    shots: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    sot: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    shots_ag: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    sot_ag: dict[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    last: dict[tuple[str, str], pd.Timestamp] = {}

    for row in df.itertuples(index=False):
        kh = (row.league, row.home_team)
        ka = (row.league, row.away_team)
        # Update form deques after the match
        g_for[kh].append(float(row.home_goals))
        g_ag[kh].append(float(row.away_goals))
        g_for[ka].append(float(row.away_goals))
        g_ag[ka].append(float(row.home_goals))
        hs = getattr(row, "home_shots", np.nan)
        ash = getattr(row, "away_shots", np.nan)
        hst = getattr(row, "home_shots_on_target", np.nan)
        ast_ = getattr(row, "away_shots_on_target", np.nan)
        # FOR side (this team's own shots in this match)
        if not pd.isna(hs):
            shots[kh].append(float(hs))
        if not pd.isna(ash):
            shots[ka].append(float(ash))
        if not pd.isna(hst):
            sot[kh].append(float(hst))
        if not pd.isna(ast_):
            sot[ka].append(float(ast_))
        # AGAINST side (opponent's shots in this match)
        if not pd.isna(ash):
            shots_ag[kh].append(float(ash))
        if not pd.isna(hs):
            shots_ag[ka].append(float(hs))
        if not pd.isna(ast_):
            sot_ag[kh].append(float(ast_))
        if not pd.isna(hst):
            sot_ag[ka].append(float(hst))
        last[kh] = row.date
        last[ka] = row.date
        # Update Elo from post-match elo_home + delta inferable from result, but easier:
        # take the AFTER-MATCH elo by re-running update.
        # row.elo_home / row.elo_away are PRE-match; recompute post-match.
        rh = row.elo_home
        ra = row.elo_away
        ph = 1.0 / (1.0 + 10.0 ** ((ra - (rh + DEFAULT_HOME_ADV)) / 400.0))
        if row.home_goals > row.away_goals:
            actual_h = 1.0
        elif row.home_goals < row.away_goals:
            actual_h = 0.0
        else:
            actual_h = 0.5
        delta = row.home_goals - row.away_goals
        k_eff = DEFAULT_K * (1.0 + np.log(abs(delta) + 1.0))
        update = k_eff * (actual_h - ph)
        elo[kh] = rh + update
        elo[ka] = ra - update

    # Collate into team_state dict
    state: dict[str, dict[str, TeamState]] = defaultdict(dict)
    all_team_keys = set(elo.keys()) | set(last.keys())
    for league, team in all_team_keys:
        state[league][team] = TeamState(
            elo=elo.get((league, team), DEFAULT_INITIAL),
            goals_for=list(g_for.get((league, team), [])),
            goals_against=list(g_ag.get((league, team), [])),
            shots=list(shots.get((league, team), [])),
            shots_on_target=list(sot.get((league, team), [])),
            shots_against=list(shots_ag.get((league, team), [])),
            sot_against=list(sot_ag.get((league, team), [])),
            last_match_iso=last[(league, team)].isoformat() if (league, team) in last else None,
        )
    return dict(state)


# --------- predict using artifact ---------------------------------------

def _team_form_avg(values: list[float]) -> float:
    if not values:
        return float("nan")
    cleaned = [v for v in values if not pd.isna(v)]
    return float(np.mean(cleaned)) if cleaned else float("nan")


def build_features_for_fixtures(
    artifact: V4Artifact,
    fixtures: pd.DataFrame,
    *,
    clubelo_cache_dir: Path | str = Path("data/external/clubelo"),
    clubelo_history: pd.DataFrame | None = None,
    lineup_lookup: dict | None = None,
    injury_lookup: dict | None = None,
    recent_injury_lookup: dict | None = None,
) -> pd.DataFrame:
    """Given new fixtures (with odds), build the feature columns the GBM needs.

    fixtures must include: league, home_team, away_team, date, psc_home, psc_draw, psc_away,
                           and optionally psc_over25/psc_under25/ahch + handicap_home.

    ``clubelo_cache_dir``/``clubelo_history`` are passed through to
    ``build_clubelo_features``; pass an explicit history DataFrame in tests
    to skip disk I/O.

    V6 W7: pass ``lineup_lookup`` + ``recent_injury_lookup`` so lineup-aware
    artifacts can populate the `lineup_*_recent_n_injuries` columns at
    inference time. Without these the artifact will gracefully fall back
    to zero counts; lineup-trained models then see the inference-time
    rows as "no recent injuries" — biased toward conservative predictions.
    """
    out = fixtures.copy().reset_index(drop=True)

    # Ensure date column is datetime
    if not pd.api.types.is_datetime64_any_dtype(out["date"]):
        out["date"] = pd.to_datetime(out["date"])

    # Market features: pure column transform
    out = build_market_features(out)

    # V5 W5 market dynamics needs opening odds (PSH/PSD/PSA). At inference
    # the user-provided fixtures CSV typically only has closing prices, so
    # we synthesize missing opening columns as NaN; build_market_dynamics
    # will set drift=0 + available=0 for those rows and the GBM will route
    # to the static market features instead.
    for col in ("ps_home", "ps_draw", "ps_away"):
        if col not in out.columns:
            out[col] = np.nan
    out = build_market_dynamics_features(out)

    # Per-row Elo + form from team_state snapshot
    elo_h = np.full(len(out), artifact.elo_initial)
    elo_a = np.full(len(out), artifact.elo_initial)
    form_h_gf = np.full(len(out), np.nan)
    form_h_ga = np.full(len(out), np.nan)
    form_h_s = np.full(len(out), np.nan)
    form_h_sot = np.full(len(out), np.nan)
    form_h_s_ag = np.full(len(out), np.nan)
    form_h_sot_ag = np.full(len(out), np.nan)
    form_a_gf = np.full(len(out), np.nan)
    form_a_ga = np.full(len(out), np.nan)
    form_a_s = np.full(len(out), np.nan)
    form_a_sot = np.full(len(out), np.nan)
    form_a_s_ag = np.full(len(out), np.nan)
    form_a_sot_ag = np.full(len(out), np.nan)
    rest_h = np.full(len(out), np.nan)
    rest_a = np.full(len(out), np.nan)

    for i, row in enumerate(out.itertuples(index=False)):
        league = row.league
        teams = artifact.team_state.get(league, {})
        sh = teams.get(row.home_team)
        sa = teams.get(row.away_team)
        if sh is not None:
            elo_h[i] = sh.elo
            form_h_gf[i] = _team_form_avg(sh.goals_for)
            form_h_ga[i] = _team_form_avg(sh.goals_against)
            form_h_s[i] = _team_form_avg(sh.shots)
            form_h_sot[i] = _team_form_avg(sh.shots_on_target)
            form_h_s_ag[i] = _team_form_avg(sh.shots_against)
            form_h_sot_ag[i] = _team_form_avg(sh.sot_against)
            if sh.last_match_iso:
                rest_h[i] = (row.date - pd.Timestamp(sh.last_match_iso)).total_seconds() / 86400
        if sa is not None:
            elo_a[i] = sa.elo
            form_a_gf[i] = _team_form_avg(sa.goals_for)
            form_a_ga[i] = _team_form_avg(sa.goals_against)
            form_a_s[i] = _team_form_avg(sa.shots)
            form_a_sot[i] = _team_form_avg(sa.shots_on_target)
            form_a_s_ag[i] = _team_form_avg(sa.shots_against)
            form_a_sot_ag[i] = _team_form_avg(sa.sot_against)
            if sa.last_match_iso:
                rest_a[i] = (row.date - pd.Timestamp(sa.last_match_iso)).total_seconds() / 86400

    out["elo_home"] = elo_h
    out["elo_away"] = elo_a
    out["elo_diff"] = elo_h - elo_a + artifact.elo_home_adv
    out["elo_p_home"] = 1.0 / (1.0 + 10.0 ** (-(out["elo_diff"]) / 400.0))
    out["form_home_goals_for_n"] = form_h_gf
    out["form_home_goals_against_n"] = form_h_ga
    out["form_home_shots_n"] = form_h_s
    out["form_home_shots_on_target_n"] = form_h_sot
    out["form_home_shots_against_n"] = form_h_s_ag
    out["form_home_sot_against_n"] = form_h_sot_ag
    out["form_away_goals_for_n"] = form_a_gf
    out["form_away_goals_against_n"] = form_a_ga
    out["form_away_shots_n"] = form_a_s
    out["form_away_shots_on_target_n"] = form_a_sot
    out["form_away_shots_against_n"] = form_a_s_ag
    out["form_away_sot_against_n"] = form_a_sot_ag
    out["form_home_goal_diff_n"] = form_h_gf - form_h_ga
    out["form_away_goal_diff_n"] = form_a_gf - form_a_ga
    out["form_home_rest_days"] = rest_h
    out["form_away_rest_days"] = rest_a

    # V5 W4: derive xG-lite from form_*_shots* columns (pure transform)
    out = build_xg_lite_features(out)
    # V5 W4: clubelo features (loads cache from disk unless history passed in)
    out = build_clubelo_features(
        out, cache_dir=clubelo_cache_dir, history=clubelo_history
    )

    # V6 W7: lineup features for lineup-aware artifacts. When the caller
    # supplies a lookup, run the same build_lineup_features path the
    # training pipeline used. Without a lookup we set the lineup columns
    # to zeros so the lineup-aware artifact has the columns it needs;
    # zero-injury inference is a sane default (the model interprets it
    # as "no signal" rather than crashing on missing columns).
    if (artifact.metadata.get("with_lineups", False)
            or lineup_lookup is not None
            or recent_injury_lookup is not None):
        from nutmeg.v4.features.lineup_features import build_lineup_features
        out = build_lineup_features(
            out,
            lineup_lookup=lineup_lookup or {},
            injury_lookup=injury_lookup,
            recent_injury_lookup=recent_injury_lookup or {},
        )

    return out


def predict_lambdas(
    artifact: V4Artifact,
    feature_df: pd.DataFrame,
) -> np.ndarray:
    """Run the artifact's two boosters and return (N, 2) lambdas.

    Dispatches on ``artifact.model_type``:
      - "lightgbm" → numpy array path (legacy V4 default)
      - "catboost" → pandas DataFrame path with categorical columns as string
                     (CatBoost takes the dataframe directly; lighter coupling
                     than building a Pool ourselves)
    Both branches clip the lambda to [0.05, 8.0] for DC-grid safety.
    """
    if artifact.model_type == "catboost":
        X = feature_df[artifact.feature_columns].copy()
        for c in artifact.cat_features:
            if c in X.columns:
                X[c] = X[c].astype(str).fillna("UNK")
        lh = artifact.booster_home.predict(X)
        la = artifact.booster_away.predict(X)
    else:
        X = feature_df[artifact.feature_columns].astype(float).values
        lh = artifact.booster_home.predict(X)
        la = artifact.booster_away.predict(X)
    lh = np.clip(np.asarray(lh, dtype=float), 0.05, 8.0)
    la = np.clip(np.asarray(la, dtype=float), 0.05, 8.0)
    return np.column_stack([lh, la])
