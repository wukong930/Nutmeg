"""V4 FastAPI routes.

Endpoints:
  GET  /v4/health    — artifact load status, model metadata
  POST /v4/recommend — fixtures (JSON) → predictions + recommendations

Artifact loading is LAZY (first request triggers load) so the app starts
fast even when artifact is on slow disk; subsequent requests reuse the
cached LoadedModel.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import NamedTuple, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, Response

from nutmeg.v4.api.schemas import (
    FixtureOddsInput,
    HealthResponse,
    JingcaiRecommendRequest,
    JingcaiSpRequest,
    HealthCheckLatestResponse,
    JingcaiUnmappedResponse,
    JingcaiSpResponse,
    LegResponse,
    LotteryRulesResponse,
    ManualBetRequest,
    ManualBetResponse,
    MarketHandicapRequest,
    MarketHandicapResponse,
    MarketRepriceRequest,
    MarketRepriceResponse,
    MarginBand,
    ScoreCell,
    ModelInfo,
    ParlayLegEcho,
    ParlayRecordRequest,
    ParlayRecordResponse,
    PoolFixturePick,
    PoolLegResponse,
    PlayoffWarning,
    PoolRecommendRequest,
    PoolRecommendResponse,
    PoolTicketResponse,
    RecommendRequest,
    RecommendResponse,
    RecommendationResponse,
    SelectionResponse,
    SingleRecommendRequest,
    SingleRecommendResponse,
    AsianHandicapLineProb,
    HandicapLineProb,
    PendingFixture,
    SinglePrediction,
    EvBoardResponse,
    EvLeg,
    SpCalcResponse,
    SingleTicketResponse,
    SportteryRefreshResponse,
    TodayRecommendationsDiff,
    TodayRecommendationsRequest,
    TodayRecommendationsResponse,
    TodaySummary,
    WcFixtureRecInput,
    WcRecommendationOutcome,
    WcSingleRecMatch,
    WcSingleRecRequest,
    WcSingleRecResponse,
    WcUpcomingPick,
    WcUpcomingResponse,
    UpcomingPredictionsRequest,
    UpcomingPredictionsResponse,
    WcMatchPrediction,
    WcPredictionsResponse,
)
from nutmeg.v4.combo import MatchInput, recommend_combinations
from nutmeg.v4.combo.compound_pool import recommend_pool
from nutmeg.v4.combo.lottery_rules import JINGCAI_DEFAULT
from nutmeg.v4.combo.selections import Selection
from nutmeg.v4.combo.single_match import recommend_singles
from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    grid_to_margin_bands,
    score_grid,
)
from nutmeg.v4.model.persist import (
    V4Artifact,
    build_features_for_fixtures,
    load_artifact,
    predict_lambdas,
)
from nutmeg.v4.observation.auto_calibration import (
    LIVE_T_CORRECTION_FILENAME,
    apply_correction_to_probs,
    load_artifact_correction,
)


router = APIRouter(prefix="/v4", tags=["v4"])


# ---------- Artifact loader (lazy + thread-safe) ------------------------

# The ONE declared production artifact. This is a *declaration*, not a knob:
# `.env`'s NUTMEG_V4_ARTIFACT_PATH is what actually gets served, and this is
# what we expect that to be. Disagreement is the alarm
# (`/health.artifact_is_expected=False`, health_check.sh §18 red).
#
# 2026-08-07: this replaces a bare `DEFAULT_ARTIFACT_PATH = "data/v4_model"`
# that was 4,871 fixtures behind production. Two mechanisms (launchd's explicit
# `source .env` + `load_dotenv()` walking up the tree) kept it from firing, so
# nothing was ever mis-served — but had `.env` gone missing, serving would have
# silently dropped to the 2025-06 LightGBM baseline with `artifact_loaded=True`,
# `status="ok"` and every health signal still green. Same family as the
# 涓流-END-is-a-constant bug: the check's premise was never itself checked.
#
# 🚨 换盘不是「改这一行 + `.env`」两处。审查实测(2026-08-07):这个常量只管
# **读的那条路**(面板 / `/health` / 所有预测端点)。**真正生成注单的那条路不读它,
# 也不读环境变量** —— 已安装的 `com.nutmeg.morning_recommend` /
# `com.nutmeg.daily_recommend` 跑 `python -m nutmeg.v4.cli.recommend` 且**不传
# `--model`**,吃的是各 CLI 自己的 argparse 默认值;`load_artifact()` 只接 `in_dir`,
# 不读 env、不读 config、不看 Layer B 指针。只改这里 + `.env` 的结果是:
# **闸全绿,而 owner 实际下注依据的注单出自退役模型**。绿灯成了错误的背书。
#
# ⇒ 换盘的完整清单(`tests/v4/test_artifact_identity_guard.py::TestArtifactLiteralsAgree`
#    会把它们逐个钉死,漏一处就红):
#      1. 这一行 `EXPECTED_SERVING_ARTIFACT`
#      2. `.env` 的 NUTMEG_V4_ARTIFACT_PATH   ← 未提交,须手改
#      3. `.env.example`                       (装机模板)
#      4. `cli/recommend.py`  `--model` 默认   ← 💰 出注 cron 吃这个
#      5. `cli/recommend_pool.py` `--model` 默认
#      6. `cli/rec.py` 三处交互默认(单关/串关/复式)
#      7. `cli/data_freshness.py` 供应链探针兜底
#      8. `scripts/run_local_server.sh` 兜底
#      9. `scripts/setup_local_pipeline.sh` ARTIFACT_DIR
#     10. `cli/auto_retrain.py` 的 `--artifact-base` 用法示例 + help(Layer B 部署
#         的落点。⚠️ 这一条 AST 断言逮不到 —— 它在**文档字符串里**,
#         `ast.Constant` 的值是整段 docstring 而不是那个路径,`startswith` 直接
#         漏过。另有一条正则断言专门盯它。判闸本身走
#         `is_expected_serving_base()`,不吃这个字面量。)
#   豁免:`cli/roi_backtest.py` 的 LINEUP_ARTIFACT 是显式 A/B 的另一臂,故意不同。
EXPECTED_SERVING_ARTIFACT = "data/v4_model_cat"

# Fallback when NUTMEG_V4_ARTIFACT_PATH is unset. Bound to the *same symbol* on
# purpose — a second literal here is exactly what went stale last time, and one
# literal cannot drift from itself.
DEFAULT_ARTIFACT_PATH = EXPECTED_SERVING_ARTIFACT

_artifact_cache: dict[str, V4Artifact] = {}
#: path → 上次加载失败的原因。让 /health 能区分「盘没配」和「盘配了但坏了」——
#: 两者都表现为 artifact_loaded=False,但要做的事完全不同。
_load_errors: dict[str, str] = {}
_load_lock = Lock()


# V11 backlog #4 — Layer B: live_artifact_pointer.json redirect cache.
# When present at the base artifact dir, serving redirects to the
# Layer-B-deployed candidate dir without server restart. Mtime cache
# mirrors _load_correction(): re-reads when the pointer file changes.
_pointer_cache: dict[str, tuple[float, str | None]] = {}


class ArtifactResolution(NamedTuple):
    """How serving arrived at the directory it is about to load.

    ``path`` is what actually gets loaded; ``base`` is the pre-Layer-B dir;
    ``source`` says whether a human configured it (``"env"``) or we fell back
    to the compiled-in default (``"default"``). Keeping ``source`` is the
    point: "which artifact" and "who chose it" are different questions, and
    only the second one distinguishes a healthy deploy from a `.env` that
    quietly went missing.
    """

    path: str
    base: str
    source: str          # "env" | "default"
    redirected: bool     # Layer B pointer took effect


def _artifact_base() -> tuple[str, str]:
    """(base, source) —— **纯环境变量读取,零文件系统访问**。

    单独拆出来是因为 `artifact_is_expected()` 只需要 base。原来它绕道
    `_resolve_artifact()` 拿,而后者必然要 `stat()` 一次指针文件 ⇒ 一个纯粹
    「配置写的是哪个盘」的问题被绑上了 I/O 失败模式。见下面 `except OSError`
    的注记:那正是身份闸自己被噎死的路径。

    空串按缺失处理(`.env` 里写 `NUTMEG_V4_ARTIFACT_PATH=` 是缺失不是「空路径」)。
    """
    env_base = os.environ.get("NUTMEG_V4_ARTIFACT_PATH")
    if env_base:
        return env_base, "env"
    return DEFAULT_ARTIFACT_PATH, "default"


def _resolve_artifact() -> ArtifactResolution:
    """Resolve the effective artifact directory, keeping its provenance.

    Precedence:
      1. ``NUTMEG_V4_ARTIFACT_PATH`` env var → that path (existing V5 W11 behavior)
      2. ``live_artifact_pointer.json`` at the base dir → its target path
         (V11 backlog #4 Layer B)
      3. ``DEFAULT_ARTIFACT_PATH`` → fallback

    Layer B's pointer can redirect to ``data/v4_model_layer_b/v_2026-Q3/``;
    the redirect is mtime-cached so the next request post-deploy
    serves the new artifact without restart.
    """
    base, source = _artifact_base()

    def _res(path: str) -> ArtifactResolution:
        return ArtifactResolution(path, base, source, path != base)

    from nutmeg.v4.observation.auto_retrain import (
        LIVE_ARTIFACT_POINTER_FILENAME,
        load_artifact_pointer,
    )
    pointer_path = Path(base) / LIVE_ARTIFACT_POINTER_FILENAME
    try:
        mtime = pointer_path.stat().st_mtime
    except OSError:
        # ⚠️ 2026-08-07:原来只捕 FileNotFoundError。NotADirectoryError 和
        # PermissionError 是 OSError 的**兄弟**不是子类 ⇒ base 指到一个文件
        # (`.env` 打错成 `…/metadata.json`)或目录丢了读权限时,异常会一路穿出
        # `artifact_is_expected()` 把 /health 打成 500,而 §18 会把 500 误诊成
        # 「包未装 / import 失败」。这恰恰是身份闸本该**大声说清楚**的那类配置错误,
        # 它却在这里把自己噎死。没有指针 = 不重定向,这是唯一正确的降级。
        _pointer_cache.pop(base, None)
        return _res(base)
    cached = _pointer_cache.get(base)
    if cached and cached[0] == mtime:
        return _res(cached[1] or base)
    pointer = load_artifact_pointer(base)
    if pointer is None:
        _pointer_cache[base] = (mtime, None)
        return _res(base)
    target = pointer.get("artifact_path")
    if target and Path(target).is_dir():
        _pointer_cache[base] = (mtime, target)
        return _res(target)
    _pointer_cache[base] = (mtime, None)
    return _res(base)


def _artifact_path() -> str:
    """The directory serving will actually load. Thin view of _resolve_artifact()."""
    return _resolve_artifact().path


def _same_dir(a: str, b: str) -> bool:
    """Compare two directory paths by normalized absolute form.

    Deliberately tolerant of the relative/absolute split we actually ship with:
    `.env` carries ``data/v4_model_cat`` while ``run_local_server.sh`` exports
    ``$REPO_ROOT/data/v4_model_cat``. Both name the same directory and both are
    correct. Does NOT require either path to exist — see artifact_is_expected().

    ⭐ 2026-08-07: the body moved to ``observation.auto_retrain`` so the launchd
    sentinel (`cli/data_freshness.py`) can ask the same question without
    importing FastAPI. This name stays as the alias serving already calls.
    Imported lazily like the pointer helpers below it — routes.py deliberately
    keeps `observation.auto_retrain` (which pulls numpy) off the import path
    that FastAPI startup walks.
    """
    from nutmeg.v4.observation.auto_retrain import same_artifact_dir
    return same_artifact_dir(a, b)


def is_expected_serving_base(path: str) -> bool:
    """Would serving actually *read* a Layer B pointer written at ``path``?

    Same judgment `artifact_is_expected()` makes, but about an arbitrary
    directory rather than about the configured one — the **write** side needs
    it too. `cli/auto_retrain.do_deploy` writes `live_artifact_pointer.json`
    into whatever `--artifact-base` says and used to compare it against
    nothing; a base serving does not read makes the deploy invisible by
    construction (`redirected=False`, `artifact_is_expected=True`,
    health_check.sh §18 a single OK line). That is Layer A's D1 incident
    (`docs/v12_deep_audit.md`, `tests/v4/test_layer_a_deploy_path.py`)
    replayed one layer up.

    One function on purpose: two copies of "is this the serving dir" is how
    read and write drift into disagreeing, and the disagreement is silent.
    """
    return _same_dir(path, EXPECTED_SERVING_ARTIFACT)


def artifact_is_expected() -> bool:
    """Is serving pointed at the declared production artifact?

    Judged on the BASE dir, not the effective one: a Layer B
    ``live_artifact_pointer.json`` legitimately redirects away from the base,
    and that pointer file lives *inside* the base — so an expected base is
    precisely what makes the redirect trustworthy.

    ⚠️ That exemption is exactly one hole wide: this says nothing about what
    the pointer *targets*. Constraining the target is the deploy side's job
    (`cli/auto_retrain.do_deploy`) plus §18's job of making the target and its
    age visible (`cli/artifact_identity.disk_rows`) — not this function's.

    ⛔ Deliberately does NOT consult whether the directory exists, nor whether
    an artifact loaded. Those are the two proxies that let the stale-default
    hole survive undetected: `data/v4_model` exists and loads perfectly, it is
    just the wrong model. "It loaded" and "it is the one we meant" are
    different propositions and only the second one is worth checking.

    走 `_artifact_base()` 而不是 `_resolve_artifact()`:这是个纯配置问题,
    不该为了回答它去碰磁盘(原来会,而磁盘一出错它就抛异常而不是给判词)。
    """
    return is_expected_serving_base(_artifact_base()[0])


def _observation_db_path() -> Optional[str]:
    """Post-V8 P1#5 — env-var that turns on session recording capability.

    Set NUTMEG_V4_OBSERVATION_DB=data/v4_observation.db to ALLOW the
    /recommend* endpoints to record sessions. V9 W3: this is now the
    server-side enable gate; the request must ALSO have
    `record_session=True` for an actual write to happen. Unset → no
    recording regardless of request flag (existing V4 W8 + V8 W6
    behavior).
    """
    return os.environ.get("NUTMEG_V4_OBSERVATION_DB")


# ---------- Live T-correction loader (V10 W2 Day 3) ---------------------
# Per-request load with mtime cache invalidation. The file ships from
# `nutmeg-auto-calibration --apply --deploy-artifact <art_dir>`; serving
# applies it as a final post-hoc temperature pass on 1X2 / handicap probs.
# Missing file → None → identity passthrough (existing V4-V9 behavior).
_correction_cache: dict[str, tuple[float, dict | None]] = {}


def _load_correction() -> dict | None:
    """Return the cached `live_T_correction.json` content (or None).

    Re-reads from disk when the file mtime changes (so a fresh
    `--deploy-artifact` takes effect on the next request without a
    server restart). Returns None when the file is missing, empty,
    or unparseable.
    """
    art_dir = _artifact_path()
    path = Path(art_dir) / LIVE_T_CORRECTION_FILENAME
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _correction_cache.pop(art_dir, None)
        return None
    cached = _correction_cache.get(art_dir)
    if cached and cached[0] == mtime:
        return cached[1]
    correction = load_artifact_correction(art_dir)
    _correction_cache[art_dir] = (mtime, correction)
    return correction


def _should_record_session(req_record_flag: bool) -> Optional[str]:
    """V9 W3 — return the observation DB path iff both gates are satisfied.

    Both gates required:
      1. Server: NUTMEG_V4_OBSERVATION_DB is set
      2. Request: record_session=True

    Returns the DB path string when both hold, None otherwise. Callers
    use the result as a truthiness check + the path to pass into the
    recorder.
    """
    if not req_record_flag:
        return None
    return _observation_db_path()


def _attach_jingcai_sp(preds: list) -> None:
    """Pre-fill each prediction's 竞彩 SP (1X2 + 让球) from jingcai_sp so the 市场模式
    / 近期赛事 cards SHOW the line on file (your hand-price, else the sporttery
    auto-harvest) + compute EV without re-typing. Best-effort + env-gated: no
    observation DB → silent no-op; a lookup failure never breaks a card render."""
    db = _observation_db_path()
    if not db or not preds:
        return
    try:
        from nutmeg.v4.data.sources.odds_api import _norm_team
        from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup
        had = fetch_sp_lookup(db, market="had")
        hhad = fetch_sp_lookup(db, market="hhad")
    except Exception:  # noqa: BLE001
        return
    if not had and not hhad:
        return
    # Re-key by the cross-source normalized team name so a board ↔ jingcai_sp
    # spelling divergence (AF 'Czechia' vs 竞彩/OA 'Czech Republic') still joins —
    # else the SP boxes stay empty, mirroring the fresher-line overlay miss.
    had = {(d, _norm_team(h), _norm_team(a)): v for (d, h, a), v in had.items()}
    hhad = {(d, _norm_team(h), _norm_team(a)): v for (d, h, a), v in hhad.items()}
    # 🚨 2026-08-08 —— 写回循环原来是**裸的**,而 docstring 写着「a lookup failure
    # never breaks a card render」。那句话只对 lookup 成立,对写回不成立:喂一个
    # 没声明 `jc_*` 的 pydantic model(如加字段前的 `PendingFixture`)⇒ 第一场命中
    # 就抛 ValueError ⇒ 穿出 `predictions_cup_market` ⇒ 整个面板 HTTP 500。
    # 现在逐场兜住,并**记一次 warning** —— 静默吞掉会让 schema 回归变成
    # 「竞彩 SP 莫名其妙都没了」,那正是这个项目最难查的一类故障。
    _failed = 0
    for p in preds:
      try:
        d = p.date.isoformat() if hasattr(p.date, "isoformat") else str(p.date)
        key = (d, _norm_team(p.home_team), _norm_team(p.away_team))
        r = had.get(key)
        if r:
            p.jc_home, p.jc_draw, p.jc_away, p.jc_source = r[0], r[1], r[2], r[3]
        h = hhad.get(key)
        if h:
            p.jc_hc_home, p.jc_hc_draw, p.jc_hc_away, p.jc_hc_line = h[0], h[1], h[2], h[4]
        # 竞彩价年龄标(2026-07-20):had/hhad 取**较旧**的捕获时刻——两块几乎总是
        # 同批 upsert,若真分叉,旧的那侧才是风险所在(保守报龄)。
        stamps = [x[5] for x in (r, h) if x and len(x) > 5 and x[5]]
        if stamps:
            p.jc_captured_at = min(stamps)
        # 单关可得性(2026-07-25)—— 抓了很久却一直没人消费。
        # ⚠️ 它是 **PER-MARKET(玩法级)**,不是场次级(见 jingcai_sp DDL 该列注释):
        # 竞彩可以给胜平负开单关、让球不开。所以两个玩法各带各的,别合并成一个 ——
        # 合并会让你以为让球腿能单关。None = 未知 → 前端不渲染徽章,**不猜**:
        # 把未知画成「只能串」会让人错过真能单关的场。
        if r and len(r) > 6 and r[6] is not None:
            p.jc_single_available = int(r[6])
        if h and len(h) > 6 and h[6] is not None:
            p.jc_hc_single_available = int(h[6])
      except Exception:  # noqa: BLE001, PERF203 — 一场坏行不该拖垮整块面板
        _failed += 1
    if _failed:
        import logging
        logging.getLogger(__name__).warning(
            "_attach_jingcai_sp: %d/%d 场写回失败(多半是消费方 schema 少声明了 jc_* 字段)"
            " —— 这些卡上不会有竞彩 SP,也就进不了「竞彩可投注」", _failed, len(preds))


def get_artifact(path: str | None = None) -> Optional[V4Artifact]:
    """Returns the loaded artifact, or None if path doesn't exist.

    ``path`` 可由调用方传入**已经解析好的**目录,避免同一个请求里重复解析。
    ⚠️ 2026-08-07:`/health` 原来一次请求解析 **3 次**(自己一次、
    `artifact_is_expected()` 一次、这里一次)。三次之间 Layer B 的
    `live_artifact_pointer.json` 可能被写入 ⇒ **回包里报的 path 不是它真正
    加载的那个 artifact** —— 「读出来的路径 ≠ 跑着的路径」出现在专门报告路径的
    端点里。实测在部署写指针的并发下 1500 次请求有 162 次错位。
    """
    path = path if path is not None else _artifact_path()
    if path in _artifact_cache:
        return _artifact_cache[path]
    if not Path(path).exists():
        _load_errors[path] = "目录不存在"
        return None
    with _load_lock:
        if path not in _artifact_cache:
            try:
                _artifact_cache[path] = load_artifact(path)
            except Exception as e:                           # noqa: BLE001
                # ⚠️ 2026-08-07:原来只挡「目录不存在」,`load_artifact` 自己抛的
                # 异常一路穿出 ⇒ **/health 500**。而 §18 的 daemon 探针会把 500
                # 正确判红但只能说「服务坏了」,说不出坏在哪。真实触发路径:
                # `nutmeg-train` 中途被打断 / rsync 没传完 ⇒ 目录在、metadata.json
                # 不在;或 `.env` 把路径打成一个文件;或目录丢了读权限。
                #
                # 所有调用方本来就把 None 处理成 503 + 说明,所以降级成 None 是
                # **和既有契约一致**的,而且把不透明的 500 traceback 换成能读的 503。
                # ⛔ 但不许变成静默吞:原因记进 `_load_errors` 并由 /health 透出,
                # 否则「盘坏了」和「盘没配」在输出上又分不出来。
                _load_errors[path] = f"{type(e).__name__}: {e}"
                logging.getLogger(__name__).exception(
                    "artifact 加载失败 path=%s", path)
                return None
            _load_errors.pop(path, None)
        return _artifact_cache[path]


def clear_artifact_cache() -> None:
    """Used by tests to force reload."""
    _artifact_cache.clear()
    _load_errors.clear()


# ---------- /v4/health ---------------------------------------------------

@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    res = _resolve_artifact()
    path = res.path
    expected = artifact_is_expected()
    # `status` stays a LIVENESS verdict ("can I serve?"). Identity is reported
    # alongside it rather than folded into it: they fail independently and for
    # different reasons, and a config that serves the wrong-but-loadable model
    # is precisely the case where collapsing them loses the signal.
    # scripts/health_check.sh §18 is what turns artifact_is_expected=False red.
    identity = dict(
        artifact_is_expected=expected,
        expected_artifact_path=EXPECTED_SERVING_ARTIFACT,
        artifact_base_path=res.base,
        artifact_path_source=res.source,
        # 「指到哪」必须是个字段,不能让消费方拿 base 和 path 做字符串比较:
        # `.env` 写相对路径而 run_local_server.sh 导出绝对路径,两者相等时
        # 字符串也不相等(`_same_dir` 存在就是为了这个)⇒ 字符串比较会把
        # 「没重定向」读成「重定向了」。
        artifact_redirected=res.redirected,
    )
    mismatch = None if expected else (
        f"serving artifact base {res.base!r} (source={res.source}) is not the "
        f"declared production artifact {EXPECTED_SERVING_ARTIFACT!r}"
    )
    # 用**这次**解析出来的路径去加载,而不是让 get_artifact() 自己再解析一遍 ——
    # 否则回包里的 artifact_path 可能不是它真正加载的那个(见 get_artifact 注记)。
    art = get_artifact(path)
    if art is None:
        return HealthResponse(
            status="degraded",
            artifact_loaded=False,
            artifact_path=path,
            detail=(f"artifact 无法加载 at {path}"
                    + (f" —— {_load_errors[path]}" if path in _load_errors
                       else "; run `python -m nutmeg.v4.cli.train`")
                    + (f" · {mismatch}" if mismatch else "")),
            **identity,
        )
    n_teams = sum(len(teams) for teams in art.team_state.values())
    return HealthResponse(
        status="ok",
        artifact_loaded=True,
        artifact_path=path,
        trained_at_utc=art.metadata.get("trained_at_utc"),
        training_cutoff=art.metadata.get("training_cutoff"),
        n_teams=n_teams,
        n_leagues=len(art.team_state),
        model_type=art.model_type,
        detail=mismatch,
        **identity,
    )




# ---------- /v4/dashboard (web UI) ---------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Serve the single-file vanilla-JS dashboard.

    ``Cache-Control: no-cache`` forces the browser (and the service worker's
    network-first ``fetch``) to REVALIDATE the HTML on every load. Without it the
    HTML was served from the HTTP disk cache with a heuristic freshness window, so
    code changes silently failed to reach the client even after a hard reload —
    the SW's network-first fetch just returned the stale cached copy.
    """
    html_path = _STATIC_DIR / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail="dashboard.html not bundled with package")
    return HTMLResponse(
        content=html_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# ---------- /v4/manifest.json + /v4/sw.js + /v4/icon.svg (P1#14 PWA) ----

@router.get("/manifest.json", include_in_schema=False)
def manifest() -> Response:
    """post-v9 P1#14: PWA manifest so the dashboard can be installed
    as a standalone web app on mobile (Android Chrome / iOS Safari
    "Add to Home Screen"). Minimal: name, icons, theme color,
    display mode, start URL."""
    import json as _json
    body = {
        "name": "Nutmeg Football Betting Helper",
        "short_name": "Nutmeg",
        "description": "China sports lottery football betting recommendations",
        "start_url": "/api/v4/dashboard",
        "scope": "/api/v4/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#0d1119",
        "theme_color": "#131826",
        "icons": [
            {"src": "/api/v4/icon.svg",
             "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
        ],
        "lang": "zh-CN",
        "categories": ["sports", "finance"],
    }
    return Response(
        content=_json.dumps(body, ensure_ascii=False, indent=2),
        media_type="application/manifest+json",
    )


@router.get("/icon.svg", include_in_schema=False)
def app_icon() -> Response:
    """SVG app icon (works at any size, low byte count, no PNG generation)."""
    # E (靶心足球): gold target + ball center on dark navy — matches the
    # dashboard's gold-on-dark theme. Full-bleed bg → safe as a maskable icon.
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">'
        '<rect width="192" height="192" fill="#131826"/>'
        '<g fill="none" stroke="#d4a574" stroke-width="9" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="96" cy="96" r="52"/>'
        '<circle cx="96" cy="96" r="29"/>'
        '<path d="M96 30 V46 M96 146 V162 M30 96 H46 M146 96 H162"/>'
        '</g>'
        '<circle cx="96" cy="96" r="13" fill="#ef4444"/>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


# Single source of truth for the frontend/SW version. Bump on ANY frontend
# change → the /version endpoint + the new-version banner trigger a reload so an
# open tab never silently runs stale code (the recurring "refreshed but didn't
# update" trap was an old tab running pre-fix JS).
_FE_VERSION = "nutmeg-v159-fe-closing-zone"


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    """post-v9 P1#14 + V12 W4: minimal service worker.

    Strategy: NETWORK-first for the dashboard + all API data (always fresh
    when online; the dashboard falls back to cache for offline launch).
    Cache-first only for the truly-static manifest + icon.

    V12 W4 flipped the dashboard from cache-first → network-first: cache-first
    meant a shipped dashboard.html update kept serving the stale cached page
    until a manual hard-refresh / two reloads. Network-first shows the new
    page on the next normal reload, while the precache + catch-fallback keep
    offline launch working.

    Versioned cache name + activate-purge still force a clean slate; bump
    CACHE_VERSION when the static shell (manifest/icon) changes.
    """
    sw_js = """
// V12 W4 — dashboard is now NETWORK-first (was cache-first), so a shipped
// dashboard.html update shows on the next normal reload instead of needing a
// hard-refresh / two reloads. The dashboard is still precached + used as an
// offline fallback. Only manifest + icon stay cache-first (truly static).
// The activate handler deletes any cache != this constant, so a CACHE_VERSION
// bump still auto-purges old caches on the next load.
const CACHE_VERSION = '__FE_VERSION__';
const SHELL_URLS = [
  '/api/v4/dashboard',
  '/api/v4/manifest.json',
  '/api/v4/icon.svg',
];
const STATIC_SHELL = [
  '/api/v4/manifest.json',
  '/api/v4/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // 2026-07-08 — Only GET is cacheable / safe to intercept. Non-GET
  // (POST/PUT/… — e.g. the 手填盘口 /recommend/market-reprice, 记一笔 writes)
  // MUST bypass the SW: re-fetching a Request that carries a body is fraught,
  // and the network-first catch below falls to caches.match — which is
  // undefined for a POST — so respondWith(undefined) throws
  // "FetchEvent.respondWith received an error: Returned response is null"
  // (hit on phone / Tailscale where the re-fetch is likelier to fail).
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // Cache-first for the truly-static shell (manifest + icon).
  if (STATIC_SHELL.some((u) => url.pathname === u || url.pathname.endsWith(u))) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request).then((resp) => {
        const respClone = resp.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, respClone));
        return resp;
      }))
    );
    return;
  }
  // Network-first for the dashboard: always fresh online; cache it so an
  // offline launch still works. A never-cached miss → Response.error() (a real
  // failed fetch the page can handle), NEVER undefined.
  if (url.pathname === '/api/v4/dashboard' || url.pathname.endsWith('/api/v4/dashboard')) {
    event.respondWith(
      fetch(event.request).then((resp) => {
        const respClone = resp.clone();
        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, respClone));
        return resp;
      }).catch(() => caches.match(event.request).then((c) => c || Response.error()))
    );
    return;
  }
  // Network-first, no cache, for everything else (GET API data must be fresh).
  // catch → cache fallback, but a never-cached GET returns undefined, so coerce
  // to Response.error() — respondWith must never receive null.
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request).then((c) => c || Response.error()))
  );
});
""".lstrip().replace("__FE_VERSION__", _FE_VERSION)
    return Response(content=sw_js, media_type="application/javascript")


@router.get("/version", include_in_schema=False)
def version() -> dict:
    """Current frontend/SW version. The dashboard captures this at load, polls it
    on tab-focus, and shows a 'new version ready → reload' banner when it differs
    — so an open tab never silently keeps running stale code."""
    return {"version": _FE_VERSION}


# ---------- /v4/rules (V6 W10) -------------------------------------------

@router.get("/rules", response_model=LotteryRulesResponse)
def rules() -> LotteryRulesResponse:
    """Return the currently active 竞彩 LotteryRules constants.

    The dashboard fetches this on load so rule-display text (¥2 起投,
    ¥20k 上限, 派奖率 68.5%, EV 门槛 5%) stays in lockstep with the
    server's actual enforcement logic. Single source of truth lives in
    `nutmeg.v4.combo.lottery_rules.JINGCAI_DEFAULT`.
    """
    r = JINGCAI_DEFAULT
    return LotteryRulesResponse(
        stake_unit=r.stake_unit,
        max_ticket_stake=r.max_ticket_stake,
        max_period_stake=r.max_period_stake,
        min_parlay_legs=r.min_parlay_legs,
        max_legs_per_ticket=r.max_legs_per_ticket,
        payout_ratio=r.payout_ratio,
        vig=r.vig,
        min_ev_per_unit=r.min_ev_per_unit,
        min_hit_probability=r.min_hit_probability,
    )


# ---------- /v4/team-logo/{slug} (V11 P1-FE#2 Day 2) -------------------

_TEAM_LOGOS_DIR = Path("data/external/team_logos")


@router.get("/team-logo/{slug}", include_in_schema=False)
def team_logo_endpoint(slug: str) -> Response:
    """Serve a cached team logo PNG.

    404 when the logo hasn't been ingested yet — the dashboard's
    ``<img onerror=...>`` then falls back to the 2-letter initials
    circle so a missing logo is never a user-visible defect.

    Slug format: lowercase + underscore (produced by ``team_slug()`` in
    ``nutmeg.v4.data.team_logos``).
    """
    # Defensive: only allow simple lowercase + underscore + digits to
    # prevent path traversal. Anything else → 404.
    import re as _re
    if not slug or not _re.fullmatch(r"[a-z0-9_]+", slug):
        raise HTTPException(status_code=404, detail="invalid slug")
    candidate = _TEAM_LOGOS_DIR / f"{slug}.png"
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="logo not cached")
    return Response(
        content=candidate.read_bytes(),
        media_type="image/png",
        # Logos rarely change — cache aggressively
        headers={"Cache-Control": "public, max-age=604800"},  # 7 days
    )


# ---------- /v4/team-name-zh (V11 P1-FE#2) ------------------------------

@router.get("/team-name-zh", include_in_schema=False)
def team_name_zh_endpoint() -> Response:
    """Return the full Chinese team-name dict (~150 teams across every
    served league).

    Dashboard fetches this at init (with ``cache: 'no-cache'``) and stores it
    as ``TEAM_ZH_DICT``. When ``locale == 'zh'`` the frontend calls
    ``zhTeam(name)`` to swap English → Chinese in match cards. Unknown teams
    fall through unchanged.

    NOT static: the dict grows whenever a league/team is registered (MLS/巴甲
    …), so a long cache would pin a stale copy and the new names would show
    English for hours. Short max-age + must-revalidate so any consumer
    self-heals; the dashboard's no-cache fetch makes its own load always fresh.
    """
    import json as _json
    from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
    return Response(
        content=_json.dumps(TEAM_NAME_ZH, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=600, must-revalidate"},
    )


# ---------- /v4/recommend -----------------------------------------------

def _fixtures_to_dataframe(fixtures: list[FixtureOddsInput]) -> pd.DataFrame:
    """Convert API input to the DataFrame shape the model expects."""
    rows = []
    for f in fixtures:
        rows.append({
            "date": pd.Timestamp(f.date),
            "league": f.league,
            "home_team": f.home_team,
            "away_team": f.away_team,
            "psc_home": f.psc_home,
            "psc_draw": f.psc_draw,
            "psc_away": f.psc_away,
            "psc_over25": f.psc_over25,
            "psc_under25": f.psc_under25,
            "ou_line": f.ou_line,   # 体检 Wave1 — real total line, was silently dropped
            "odds_update": f.odds_update,   # 体检 P1#10 — snapshot age (echo, not a feature)
            "ahch": f.ahch,
            "handicap_home": f.handicap_home,
            "odds_1x2_H": f.odds_1x2_H,
            "odds_1x2_D": f.odds_1x2_D,
            "odds_1x2_A": f.odds_1x2_A,
            "odds_handicap_H": f.odds_handicap_H,
            "odds_handicap_D": f.odds_handicap_D,
            "odds_handicap_A": f.odds_handicap_A,
        })
    return pd.DataFrame(rows)


def _market_reverse_handicap_probs(row: pd.Series, line: int) -> dict[str, float] | None:
    """F1 — market-reverse 让球 P for ONE integer line, identical to what the
    dashboard board displays (``_model_board_handicap_lines``): de-vig Pinnacle
    1X2 (+ O/U) → Dixon-Coles grid → cover probs. Returns ``{"H","D","A"}`` or
    None when Pinnacle 1X2 is absent / the fit fails, so the single-leg engine
    falls back to the model grid. Keeps recommend_single's 让球 P consistent with
    the displayed EV + the parlay record (one source of truth, V12 W8)."""
    fair = _pinnacle_devig_1x2(row.get("psc_home"), row.get("psc_draw"), row.get("psc_away"))
    if fair is None:
        return None
    try:
        from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
        p_over = devig_over(row.get("psc_over25"), row.get("psc_under25"))
        ou_line = float(row.get("ou_line") or 2.5)
        for ln, ph, pd_, pa in implied_handicap_lines(
            fair[0], fair[1], fair[2], p_over, ou_line=ou_line, c1=True,
            league=row.get("league"),          # 🚨 δ 范围闸:必须传
        ):
            if ln == int(line):
                return {"H": float(ph), "D": float(pd_), "A": float(pa)}
    except Exception:  # noqa: BLE001
        # 体检 W0 2026-07-15 — 以前零 log:反推失败时让球腿 P 静默降级回模型 grid,
        # 与「Pinnacle 缺席」走同一条不可见的路。行为不变,只让降级可见。
        logging.getLogger(__name__).warning(
            "market-reverse handicap P failed for %s vs %s (line=%s) — "
            "falling back to model grid",
            row.get("home_team"), row.get("away_team"), line, exc_info=True)
        return None
    return None


def _fixture_to_match_input(row: pd.Series, lh: float, la: float, gbm_rho: float) -> Optional[MatchInput]:
    """Build a MatchInput from a fixture's 竞彩 (lottery) odds — or None.

    A 竞彩 recommendation is only meaningful against a real 竞彩 SP: the line you
    actually bet. We deliberately do NOT substitute Pinnacle (psc_*) when the
    lottery line is missing — Pinnacle is the sharp BENCHMARK, not a betting
    venue, so EV = model_P × Pinnacle_odds − 1 measures the model's divergence
    from the sharp (noise), not a real edge. Feeding that fallback into the
    recommenders was the "EV-vs-Pinnacle" bug; removing it here stops the same
    pattern from resurfacing through /recommend or /recommend/single.

    Returns None when neither the 竞彩 1X2 nor the 竞彩 handicap line is present
    (no rankable ticket). Callers still emit a model PREDICTION for the fixture;
    only the bet recommendation is withheld until a real 竞彩 SP arrives.
    """
    # 1X2 market — require a real 竞彩 line; NO Pinnacle fallback.
    o_h = row.get("odds_1x2_H")
    o_d = row.get("odds_1x2_D")
    o_a = row.get("odds_1x2_A")
    odds_1x2 = None
    if not (pd.isna(o_h) or pd.isna(o_d) or pd.isna(o_a)):
        odds_1x2 = {"H": float(o_h), "D": float(o_d), "A": float(o_a)}

    # Handicap market (only when both handicap_home and 竞彩 odds_handicap_* present)
    odds_hc = None
    handicap = None
    if not pd.isna(row.get("handicap_home")):
        handicap = int(row["handicap_home"])
        ho_h = row.get("odds_handicap_H")
        ho_d = row.get("odds_handicap_D")
        ho_a = row.get("odds_handicap_A")
        if not (pd.isna(ho_h) or pd.isna(ho_d) or pd.isna(ho_a)):
            odds_hc = {"H": float(ho_h), "D": float(ho_d), "A": float(ho_a)}

    # No real 竞彩 line on either market → no rankable 竞彩 ticket.
    if odds_1x2 is None and odds_hc is None:
        return None

    # V14 — cup/J1 are OUT-OF-DISTRIBUTION for the model; the 竞彩盘 must price
    # their 胜平负 off the SHARP de-vig Pinnacle line, NOT the OOD model. Reverse-
    # fit λ from the de-vig 1X2 (+ O/U anchor) so the grid reproduces de-vig 1X2
    # AND market-reverse 让球 — the SAME source the 市场模式 card displays. The 13
    # trained leagues keep their model λ untouched.
    lam_h, lam_a = float(lh), float(la)
    m_probs: dict[str, float] | None = None
    if row.get("league") in _CUP_MARKET_COMPETITIONS:
        fair = _pinnacle_devig_1x2(
            row.get("psc_home"), row.get("psc_draw"), row.get("psc_away")
        )
        if fair is not None:
            # 胜平负 P = de-vig Pinnacle VERBATIM (match_probs → no model temperature
            # correction, matches the 市场模式 card exactly). Also reverse-fit λ so the
            # grid backing any non-overridden outcome stays de-vig-consistent.
            m_probs = {"H": fair[0], "D": fair[1], "A": fair[2]}
            from nutmeg.v4.model.market_handicap import devig_over, fit_lambdas
            p_over = devig_over(row.get("psc_over25"), row.get("psc_under25"))
            ou_line = float(row.get("ou_line") or 2.5)
            try:
                lam_h, lam_a = fit_lambdas(
                    fair[0], fair[1], fair[2], p_over, ou_line=ou_line
                )
            except Exception:  # noqa: BLE001 — keep model λ if the fit fails
                # 体检 W0 2026-07-15 — 以前零 log:fit 失败后 1X2 用 de-vig fair、
                # grid 留在模型 λ = 同一张 rec 内概率源静默劈叉。行为不变,仅曝光。
                logging.getLogger(__name__).warning(
                    "market λ fit failed for %s vs %s — grid stays on model λ "
                    "while 1X2 uses de-vig fair",
                    row.get("home_team"), row.get("away_team"), exc_info=True)

    # F1 — when a 让球 bet is present, use the MARKET-REVERSE P (de-vig Pinnacle
    # 1X2 + O/U), the SAME source the dashboard shows + the parlay path records,
    # so the single-leg recommendation matches the displayed EV. None when
    # Pinnacle is absent → the engine falls back to the model grid.
    hc_probs = (
        _market_reverse_handicap_probs(row, handicap)
        if (odds_hc is not None and handicap is not None)
        else None
    )

    return MatchInput(
        match_id=f"{row['league']}_{row['home_team']}_vs_{row['away_team']}",
        lambda_home=lam_h,
        lambda_away=lam_a,
        rho=gbm_rho,
        handicap_home=handicap if odds_hc else None,
        odds_1x2=odds_1x2,
        odds_handicap_1x2=odds_hc,
        handicap_probs=hc_probs,
        match_probs=m_probs,
    )


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    if req.k_max < req.k_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="k_max must be >= k_min",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    # Per-fixture predictions
    single_preds = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
        pred = SinglePrediction(
            home_team=f.home_team,
            away_team=f.away_team,
            league=f.league,
            date=f.date,
            lambda_home=float(lh),
            lambda_away=float(la),
            p_home_1x2=float(ph),
            p_draw_1x2=float(pd_),
            p_away_1x2=float(pa),
        )
        if f.handicap_home is not None:
            hph, hpd, hpa = tuple(
                apply_correction_to_probs(
                    np.array(grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)),
                    correction,
                )
            )
            pred.handicap_home = f.handicap_home
            pred.p_home_handicap = float(hph)
            pred.p_draw_handicap = float(hpd)
            pred.p_away_handicap = float(hpa)
        single_preds.append(pred)

    # Combo recommendations
    inputs: list[MatchInput] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        mi = _fixture_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            inputs.append(mi)

    recs = recommend_combinations(
        inputs,
        bankroll=req.bankroll,
        k_min=req.k_min,
        k_max=req.k_max,
        top_n_recommendations=req.top_n,
        min_hit_probability=req.min_hit_probability,
        min_kelly_stake=req.min_kelly_stake,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction=req.max_stake_fraction,
        include_compound=req.include_compound,
        correction=correction,
    )

    recommendations_out = []
    for r in recs:
        p = r.parlay
        legs_out = []
        for leg in p.legs:
            legs_out.append(LegResponse(
                match_id=leg.match_id,
                market_type=leg.market_type,
                selections=[
                    SelectionResponse(
                        outcome=s.outcome,
                        odds=float(s.odds),
                        probability=float(s.probability),
                        edge=float(s.edge),
                    )
                    for s in leg.selections
                ],
            ))
        # V11 P1-FE#5 — per-rec fingerprint over its pick set
        from nutmeg.v4.observation.recommendation_version import (
            parlay_recommendation_fingerprint,
        )
        rec_resp = RecommendationResponse(
            rank=r.rank,
            k_legs=p.k,
            is_compound=p.is_compound,
            stake_units=r.stake_units,
            kelly_recommended_stake=float(r.kelly.recommended_stake),
            kelly_capped_fraction=float(r.kelly.capped_kelly),
            expected_return=float(r.kelly.expected_return),
            hit_probability=float(p.hit_probability),
            ev_per_unit=float(p.ev_per_unit),
            log_growth=float(r.kelly_log_growth),
            legs=legs_out,
        )
        rec_resp.selection_fingerprint = parlay_recommendation_fingerprint(rec_resp)
        recommendations_out.append(rec_resp)

    # V11 P1-FE#5 — parlay top-level version_hash
    from nutmeg.v4.observation.recommendation_version import (
        version_hash as _vh,
        fixtures_odds_digest,
    )
    _parlay_top_hash = _vh(
        parlay_fingerprints=[r.selection_fingerprint for r in recommendations_out if r.selection_fingerprint],
        odds_digest=fixtures_odds_digest(req.fixtures),
    )
    response = RecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=ModelInfo(
            trained_at_utc=art.metadata.get("trained_at_utc"),
            training_cutoff=art.metadata.get("training_cutoff"),
            n_train=art.metadata.get("n_train"),
            gbm_rho=gbm_rho,
            temperature_T=art.temperature_T,
            model_type=art.model_type,
            cat_features=art.cat_features,
        ),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=len(recommendations_out),
        single_match_predictions=single_preds,
        recommendations=recommendations_out,
        version_hash=_parlay_top_hash,
    )

    # V9 W3: 串关 (parlay) auto-record path — both env AND request flag required.
    # Previously this endpoint never recorded (the dashboard's checkbox was
    # a no-op since V5 W11). The CLI's `--record-to` (V5 W8) still works
    # independently for command-line workflows.
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation import record_session as _record
        try:
            _record(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
                snapshot_phase=req.snapshot_phase,
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
            # 体检 A3 — surface the failure (≠ gate-off) so the UI can go red.
            response.record_failed = True
    return response


# ---------- /v4/predictions/upcoming (V5 W11) ----------

@router.post("/predictions/upcoming", response_model=UpcomingPredictionsResponse)
def predictions_upcoming(req: UpcomingPredictionsRequest) -> UpcomingPredictionsResponse:
    """Lightweight prediction-only endpoint.

    Same input shape as /recommend, but returns ONLY per-fixture lambdas +
    1X2 + (optional) handicap probabilities — no Kelly, no parlay
    enumeration. Suitable for cheap "show me tomorrow's predictions" calls
    from the dashboard or external integrations.
    """
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    if not req.fixtures:
        # Empty input is semantically valid for this endpoint — return empty
        # predictions list with the same model_info envelope.
        return UpcomingPredictionsResponse(
            generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            model=ModelInfo(
                trained_at_utc=art.metadata.get("trained_at_utc"),
                training_cutoff=art.metadata.get("training_cutoff"),
                n_train=art.metadata.get("n_train"),
                gbm_rho=float(art.metadata.get("gbm_rho", -0.10)),
                temperature_T=art.temperature_T,
                model_type=art.model_type,
                cat_features=art.cat_features,
            ),
            n_fixtures=0,
            predictions=[],
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    predictions = []
    for i, f in enumerate(req.fixtures):
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
        pred = SinglePrediction(
            home_team=f.home_team,
            away_team=f.away_team,
            league=f.league,
            date=f.date,
            lambda_home=float(lh),
            lambda_away=float(la),
            p_home_1x2=float(ph),
            p_draw_1x2=float(pd_),
            p_away_1x2=float(pa),
        )
        if f.handicap_home is not None:
            hph, hpd, hpa = tuple(
                apply_correction_to_probs(
                    np.array(grid_to_handicap_1x2(grid, handicap_home=f.handicap_home)),
                    correction,
                )
            )
            pred.handicap_home = f.handicap_home
            pred.p_home_handicap = float(hph)
            pred.p_draw_handicap = float(hpd)
            pred.p_away_handicap = float(hpa)
        predictions.append(pred)

    return UpcomingPredictionsResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=ModelInfo(
            trained_at_utc=art.metadata.get("trained_at_utc"),
            training_cutoff=art.metadata.get("training_cutoff"),
            n_train=art.metadata.get("n_train"),
            gbm_rho=gbm_rho,
            temperature_T=art.temperature_T,
            model_type=art.model_type,
            cat_features=art.cat_features,
        ),
        n_fixtures=len(req.fixtures),
        predictions=predictions,
    )


# ---------- /v4/recommend/single (V8 W6) ----------

def _model_info_from_artifact(art) -> ModelInfo:
    return ModelInfo(
        trained_at_utc=art.metadata.get("trained_at_utc"),
        training_cutoff=art.metadata.get("training_cutoff"),
        n_train=art.metadata.get("n_train"),
        gbm_rho=float(art.metadata.get("gbm_rho", -0.10)),
        temperature_T=art.temperature_T,
        model_type=art.model_type,
        cat_features=art.cat_features,
    )


@router.post("/recommend/single", response_model=SingleRecommendResponse)
def recommend_single(req: SingleRecommendRequest) -> SingleRecommendResponse:
    """V8 W6 — 单关 (single-leg) recommendations via the V6 W9 engine."""
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    matches: list[MatchInput] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        mi = _fixture_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            matches.append(mi)

    rec = recommend_singles(
        matches,
        bankroll=req.bankroll,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction_per_ticket=req.max_stake_fraction,
        top_per_match=req.top_per_match,
        correction=correction,
    )

    # V11 P1-FE#5 — stamp each ticket with its selection_fingerprint
    # so the frontend can diff against its prior view.
    from nutmeg.v4.observation.recommendation_version import (
        single_ticket_fingerprint,
        version_hash as _vh,
        fixtures_odds_digest,
    )
    # V12 W7 — match_id → fixture, so each ticket carries its team/league/date.
    # The 今日推荐 single board renders these directly; without them the card
    # showed "VS · undefined · undefined" (match_id alone isn't parsed there).
    _fx_by_match = {
        f"{fx.league}_{fx.home_team}_vs_{fx.away_team}": fx for fx in req.fixtures
    }
    tickets_out: list[SingleTicketResponse] = []
    for t in rec.selected_tickets:
        _fx = _fx_by_match.get(t.selection.match_id)
        tk = SingleTicketResponse(
            match_id=t.selection.match_id,
            league=(_fx.league if _fx else None),
            date=(str(_fx.date) if _fx else None),
            home_team=(_fx.home_team if _fx else None),
            away_team=(_fx.away_team if _fx else None),
            market_type=t.selection.market_type,
            outcome=t.selection.outcome,
            odds=float(t.selection.odds),
            probability=float(t.selection.probability),
            ev_per_unit=float(t.ev_per_unit),
            stake=float(t.stake),
            raw_kelly_stake=float(t.raw_kelly_stake),
            expected_return=float(t.expected_return),
            # V12 W8i — echo the source fixture's Pinnacle inputs so the 今日推荐
            # card can record THIS pick at the user's 竞彩 SP (the record
            # endpoints recompute model P from these; never trust a client P).
            psc_home=(float(_fx.psc_home) if _fx else None),
            psc_draw=(float(_fx.psc_draw) if _fx else None),
            psc_away=(float(_fx.psc_away) if _fx else None),
            psc_over25=(float(_fx.psc_over25) if _fx and _fx.psc_over25 else None),
            psc_under25=(float(_fx.psc_under25) if _fx and _fx.psc_under25 else None),
            # 体检 Wave1 — real total line; without it the record path refit at 2.5
            ou_line=(float(_fx.ou_line) if _fx and _fx.ou_line is not None else None),
            # 体检 P1#10 — snapshot age so the card can badge stale Pinnacle echoes
            odds_update=(_fx.odds_update if _fx else None),
            handicap_home=(
                int(_fx.handicap_home)
                if _fx and _fx.handicap_home is not None
                else None
            ),
        )
        tk.selection_fingerprint = single_ticket_fingerprint(tk)
        tickets_out.append(tk)
    _single_top_hash = _vh(
        single_fingerprints=[tk.selection_fingerprint for tk in tickets_out if tk.selection_fingerprint],
        odds_digest=fixtures_odds_digest(req.fixtures),
    )

    response = SingleRecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=len(tickets_out),
        tickets=tickets_out,
        total_stake=float(rec.total_stake),
        total_expected_return=float(rec.total_expected_return),
        version_hash=_single_top_hash,
    )

    # V9 W3: record when both gates pass (server env + request flag).
    # Post-V8 P1#5 originally auto-recorded on env alone; V9 W3 adds the
    # request-side opt-in so the dashboard's per-session checkbox controls
    # whether a given response lands in the DB.
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation.recorder import record_single_session
        try:
            record_single_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_single_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
            # 体检 A3 — surface the failure (≠ gate-off) so the UI can go red.
            response.record_failed = True
    return response


# ---------- /v4/observation/record-bet (Post-V13 — 记此注) ----------

@router.post("/observation/record-bet", response_model=ManualBetResponse)
def record_bet(req: ManualBetRequest) -> ManualBetResponse:
    """记此注: record the EXACT outcome + real stake the user placed (NOT the
    model's best pick), INCLUDING −EV, so the observation DB tracks the user's
    real betting history and ROI is honest. Settlement-compatible (see
    ``record_manual_bet``). Dual-gated like every recorder (server env +
    request flag); the response always returns the computed EV either way."""
    ev = float(req.probability) * float(req.odds) - 1.0
    db_path = _should_record_session(req.record_session)
    session_id: int | None = None
    recorded = False
    if db_path:
        from nutmeg.v4.observation import record_manual_bet
        try:
            session_id = record_manual_bet(db_path, bet={
                "league": req.league, "match_date": req.date,
                "home_team": req.home_team, "away_team": req.away_team,
                "market_type": req.market_type, "handicap_home": req.handicap_home,
                "outcome": req.outcome, "odds": req.odds,
                "probability": req.probability, "stake": req.stake,
                "bankroll": req.bankroll,
                # 溯源:共享 sink `store._request_odds_source` 从这个键读。
                # 漏了它,手打价和镜像价在台账里就永远分不出来(且不可回溯)。
                "odds_source": req.odds_source,
            })
            recorded = True
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_manual_bet failed (db=%s)", db_path)
            # 体检 A3 — recording IS this endpoint's whole job. A swallowed DB
            # failure used to surface as recorded=False, which the 📌 button
            # renders as "记录开关未开" — the user walks away believing the bet
            # is tracked. Fail loudly; the button's catch shows it red.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="记录失败(数据库写入异常)— 本注未入库,请重试",
            ) from None
    return ManualBetResponse(
        recorded=recorded, ev=ev, outcome=req.outcome,
        stake=req.stake, session_id=session_id)


@router.post("/observation/jingcai-sp", response_model=JingcaiSpResponse)
def record_jingcai_sp_endpoint(req: JingcaiSpRequest) -> JingcaiSpResponse:
    """体检 — SILENT capture of the 竞彩 SP the user is pricing against, for the
    softness/staleness map (竞彩's frozen line vs Pinnacle's drift to kickoff).

    Fire-and-forget: gated ONLY on the observation-DB env (no record flag — this
    is passive measurement the user already enters, NOT a bet). Upsert-latest
    dedups repeated pre-kickoff re-pricing; never raises (a lost observation must
    not break the live EV view), so the frontend can ignore the response."""
    db_path = _observation_db_path()
    if not db_path:
        return JingcaiSpResponse(recorded=False)
    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
    recorded = record_jingcai_sp(
        db_path,
        match_date=req.match_date, home_team=req.home_team, away_team=req.away_team,
        jc_home=req.jc_home, jc_draw=req.jc_draw, jc_away=req.jc_away,
        psc_home=req.psc_home, psc_draw=req.psc_draw, psc_away=req.psc_away,
        ou_line=req.ou_line, psc_over=req.psc_over, psc_under=req.psc_under,
        fixture_id=req.fixture_id, league=req.league,
        kickoff_utc=req.kickoff_utc, market=req.market,
        handicap_home=req.handicap_home, source="market_mode")
    return JingcaiSpResponse(recorded=recorded)


@router.post("/observation/sporttery-refresh", response_model=SportteryRefreshResponse)
def sporttery_refresh_endpoint() -> SportteryRefreshResponse:
    """🎯 刷新竞彩 — on-demand 竞彩 SP harvest from sporttery → jingcai_sp, so the
    cards pick up the latest frozen line WITHOUT waiting for the 23:15 cron or the
    CLI. Read-only vs sporttery (public odds). protect_manual=False ON PURPOSE:
    an explicit 🎯 click means "give me the latest OFFICIAL SP", which outranks a
    stale hand-typed line (the unattended cron keeps protect_manual=True — only
    the explicit button overwrites). 体检 Wave3 — docstring was still claiming
    the opposite. Env-gated (observation DB) + fail-soft."""
    db_path = _observation_db_path()
    if not db_path:
        return SportteryRefreshResponse(ok=False, reason="未配置观测库 (NUTMEG_V4_OBSERVATION_DB)")
    try:
        from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
        # protect_manual=False: an explicit 🎯 refresh OVERWRITES the stale
        # market_mode capture with the latest official SP (that IS the button's job).
        # trigger="button" —— `phase` 分不出触发源(close 覆盖 13 轮晚间 + exotics +
        # 每一次点击)。实测 jingcai_sp 自 07-20 起 104 个 captured_at 里 39 个
        # (37.5%)落在 cron 槽位 ±5min 之外 ⇒ 靠时间戳反推不可靠。
        r = harvest_to_db(db_path, refresh=True, protect_manual=False,
                          trigger="button")
    except Exception:  # noqa: BLE001 — fail-soft; the button surfaces the reason
        return SportteryRefreshResponse(ok=False, reason="竞彩抓取失败(网络/端点)")
    return SportteryRefreshResponse(ok=True, **r)


@router.get("/observation/jingcai-unmapped", response_model=JingcaiUnmappedResponse)
def jingcai_unmapped_endpoint() -> JingcaiUnmappedResponse:
    """竞彩中文队名映射不到英文规范名的场次 — 近期赛事页横幅用(有缺口才显示)。

    ⛔ **它测的只有一件事:名字解没解出来。** 判据是纯函数 ``summarize_unmapped``,
    只看每场自己的 home_en/away_en,**从不碰赔率**。所以:

    * 解不出的后果是**竞彩 SP 挂不上**,不是「整场丢弃」—— 盘面行来自
      API-Football 的**英文**数据,和中文词典是两条独立的链。2026-08-07 实测:
      横幅点名 2 场日乙,而 ``/predictions/cup-market`` 里 10 场日乙**全在**
      「待开盘」。原 docstring 写「整场丢弃」是错的,已改。
    * 反过来,「横幅不响」也**不**代表比赛都能算 EV:Pinnacle/AF 缺价导致的
      少场对这条判据完全隐形。⇒ 「(N/M)」不能读成「另外 M−N 场都在盘面上」。
    * 补完词典**必须重启 API**:``_ZH_TO_EN`` 在 import 时建好,uvicorn 无 --reload。

    为什么存在:检测早就有、而且工作正常 —— 2026-07-15 竞彩上架 4 场美职联而面板只
    显示 2 场时,``summarize_unmapped`` 11:43 就精确点名了那 2 场、那 3 个错名字,并
    写进了 logs/sporttery_unmapped_latest.txt(比 owner 人肉发现早几小时)。缺的从来
    不是检测能力,是**可见性**:告警只走易逝的桌面推送(无头 launchd 里根本看不见)
    加一个只有 health_check.sh 才主动读的文件,面板上一个字都没有 → owner 只能靠比对
    竞彩 App 才发现少了场。本端点把同一份结论搬到他真正会看的那块屏幕上。

    只读 cron 已写好的缓存(ttl 给极大值 = 只认缓存、绝不发请求):被动横幅在每次开页
    都去打一次竞彩官网既不礼貌也没必要 —— 主动抓取是 🎯 刷新竞彩 的活。判据复用同一个
    纯函数 ``summarize_unmapped``,不另立第二套口径。Fail-soft:读不到就 ok=False,
    横幅缺席好过整页崩。
    """
    from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
    from nutmeg.v4.data.sources.sporttery import (
        fetch_lottery_matches,
        lottery_cache_age_seconds,
    )
    try:
        matches = fetch_lottery_matches(refresh=False, ttl_seconds=10**9)
    except Exception:  # noqa: BLE001 — fail-soft; 横幅缺席好过整页崩
        return JingcaiUnmappedResponse(ok=False, reason="读取竞彩缓存失败")
    if not matches:
        return JingcaiUnmappedResponse(ok=False, reason="暂无竞彩缓存(等下次抓取)")
    s = summarize_unmapped(matches)
    age = lottery_cache_age_seconds()
    return JingcaiUnmappedResponse(
        ok=True,
        n_matches=len(matches),
        unmapped=s["unmapped"],
        gone=s["gone"],
        partial=s["partial"],
        age_seconds=int(age) if age is not None else None,
    )


#: 报告多旧算「cron 可能死了」。job 每天 09:45 + 21:00 两次;笔记本睡眠时 launchd
#: 唤醒后补跑一次 ⇒ 30h 容得下一整轮 miss + 一次睡眠,又不至于把真死拖上两天。
_HC_STALE_SECONDS = 30 * 3600


@router.get("/observation/health-check-latest",
            response_model=HealthCheckLatestResponse)
def health_check_latest_endpoint() -> HealthCheckLatestResponse:
    """定时体检上一次的判定。读 `health_check_cron.sh` 写的 **JSON 边车**。

    ⛔ **不读那份 .md** —— 那是给人看的中文报告,解析它就是「语法代理测语义属性」:
    改个措辞面板就瞎,而且瞎的时候看起来一切正常(见 `health_check_cron.sh` 顶部)。

    Fail-soft 但**不 fail-silent**:读不到 ⇒ `ok=False` + 原因,前端显示成红。
    「没红灯」和「没读到」在这里必须是两个不同的回答。
    """
    import json as _json

    p = Path(os.environ.get("NUTMEG_HC_JSON")
             or "logs/health_check_latest.json")
    try:
        raw = _json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HealthCheckLatestResponse(
            ok=False, detail=f"体检还没跑过(没有 {p})—— 装了 cron 吗?")
    except Exception as e:                                   # noqa: BLE001
        return HealthCheckLatestResponse(
            ok=False, detail=f"体检判定读不出来:{type(e).__name__}")

    age: int | None = None
    with contextlib.suppress(Exception):
        age = int((datetime.now(timezone.utc)
                   - datetime.fromisoformat(raw["ran_at"])).total_seconds())
    # 算不出年龄 ⇒ 当成 stale。「不知道多旧」不能当「很新」——
    # 那正是让一个死掉的 cron 看起来健在的那一步。
    stale = age is None or age > _HC_STALE_SECONDS
    return HealthCheckLatestResponse(
        ok=bool(raw.get("ok")),
        detail=raw.get("detail"),
        ran_at=raw.get("ran_at"),
        age_seconds=age,
        stale=stale,
        exit_code=raw.get("exit_code"),
        reds=list(raw.get("reds") or []),
        new=list(raw.get("new") or []),
        gone=list(raw.get("gone") or []),
    )


# ---------- /v4/recommend/parlay (V12 W5 — hand-picked 串关) ----------

def _leg_model_p(pred: SinglePrediction, market_type: str, outcome: str,
                 handicap_home: int | None) -> float | None:
    """Pull the model P for one parlay leg's pick from a SinglePrediction.

    1x2 → p_{home,draw,away}_1x2; handicap → the matching handicap_lines row.
    Returns None if the pick can't be scored (e.g. handicap line not computed).
    """
    if market_type == "handicap":
        if handicap_home is None:
            return None
        for hl in pred.handicap_lines:
            if hl.line == handicap_home:
                return {"H": hl.p_home, "D": hl.p_draw, "A": hl.p_away}.get(outcome)
        return None
    return {"H": pred.p_home_1x2, "D": pred.p_draw_1x2,
            "A": pred.p_away_1x2}.get(outcome)


@router.post("/recommend/parlay", response_model=ParlayRecordResponse)
def recommend_parlay(req: ParlayRecordRequest) -> ParlayRecordResponse:
    """V12 W5 — score + (optionally) record a HAND-PICKED 竞彩 串关.

    Server recomputes each leg's model P (authoritative), products them into
    the parlay hit probability, products the entered 竞彩 SPs into the parlay
    odds, then sizes the stake with the SAME kelly.py + lottery_rules pipeline
    as 单关/复式. Records (when double-gated) as one settlement-compatible
    单式 parlay row.
    """
    import datetime as _dt

    from nutmeg.v4.combo.compound_pool import quantize_stake
    from nutmeg.v4.combo.kelly import fractional_kelly_stake
    from nutmeg.v4.combo.lottery_rules import (
        cap_ticket_stake,
        passes_recommendation_thresholds,
    )

    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    # A parlay must combine DISTINCT matches (can't parlay two picks of one game).
    keys = [(leg.home_team, leg.away_team, str(leg.date)) for leg in req.legs]
    if len(set(keys)) != len(keys):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="parlay legs must be distinct matches",
        )

    fixtures = [
        FixtureOddsInput(
            date=leg.date, league=leg.league,
            home_team=leg.home_team, away_team=leg.away_team,
            kickoff_utc=leg.kickoff_utc,
            psc_home=leg.psc_home or leg.sp,
            psc_draw=leg.psc_draw or leg.sp,
            psc_away=leg.psc_away or leg.sp,
        )
        for leg in req.legs
    ]
    preds = _calc_predictions(get_artifact(), fixtures)
    if len(preds) != len(req.legs):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not score all parlay legs",
        )

    legs_echo: list[ParlayLegEcho] = []
    hit_p = 1.0
    odds = 1.0
    for leg, pred in zip(req.legs, preds, strict=True):
        p = _leg_model_p(pred, leg.market_type, leg.outcome, leg.handicap_home)
        if p is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"leg {leg.home_team} vs {leg.away_team}: no model P for "
                    f"{leg.market_type}/{leg.outcome} (handicap_home={leg.handicap_home})"
                ),
            )
        hit_p *= float(p)
        odds *= float(leg.sp)
        # Stamp the per-match prediction with THIS leg's chosen handicap line so
        # the recorded single_prediction lets V4 settlement resolve the handicap
        # leg (settlement reads handicap_home off single_predictions).
        if leg.market_type == "handicap":
            pred.handicap_home = leg.handicap_home
        legs_echo.append(ParlayLegEcho(
            match_id=f"{leg.league}_{leg.home_team}_vs_{leg.away_team}",
            league=leg.league, market_type=leg.market_type, outcome=leg.outcome,
            handicap_home=leg.handicap_home, sp=float(leg.sp), model_p=float(p),
        ))

    ev = hit_p * odds - 1.0
    kr = fractional_kelly_stake(
        hit_probability=hit_p, ev_per_unit=ev, bankroll=req.bankroll,
        kelly_fraction=req.kelly_fraction, max_stake_fraction=req.max_stake_fraction,
    )
    raw = float(kr.recommended_stake)
    stake = float(quantize_stake(cap_ticket_stake(raw)))
    passes = passes_recommendation_thresholds(hit_probability=hit_p, ev_per_unit=ev)

    response = ParlayRecordResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        legs=legs_echo,
        k_legs=len(req.legs),
        hit_probability=hit_p,
        odds=odds,
        ev_per_unit=ev,
        raw_kelly_stake=raw,
        stake=stake,
        passes_gate=passes,
        recorded=False,
        single_match_predictions=preds,
    )

    # V9 W3 double-gate: server env + request flag. Records the EXACT
    # hand-picked combo (not an engine pick) as one 单式 parlay row.
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation.recorder import record_parlay_session
        try:
            record_parlay_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
            response.recorded = True
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_parlay_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
            # 体检 A3 — surface the failure (≠ gate-off) so the UI can go red.
            response.record_failed = True
    return response


# ---------- /v4/recommend/pool (V8 W6) ----------

# Map the PoolFixturePick `pick` field to a (market_type, outcome) tuple
_POOL_PICK_MAP: dict[str, tuple[str, str]] = {
    "1x2_H": ("1x2", "H"),
    "1x2_D": ("1x2", "D"),
    "1x2_A": ("1x2", "A"),
    "hc_H":  ("handicap_1x2", "H"),
    "hc_D":  ("handicap_1x2", "D"),
    "hc_A":  ("handicap_1x2", "A"),
}


def _pick_to_selection(
    row: pd.Series,
    lh: float,
    la: float,
    gbm_rho: float,
    pick: str,
    *,
    correction: dict | None = None,
) -> Optional[Selection]:
    """Convert one (fixture row, pick) → one Selection for the compound pool.

    Mirrors the CLI's `_row_to_selection` in cli/recommend_pool.py but
    consumes a typed `pick` string instead of a CSV cell.

    V10 W2 Day 3 — applies the live post-T correction (if any) to the
    1X2 / handicap_1x2 probability tuple before extracting the chosen
    outcome's probability.
    """
    grid = score_grid(float(lh), float(la), rho=gbm_rho)
    match_id = f"{row['league']}_{row['home_team']}_vs_{row['away_team']}"
    market_type, outcome = _POOL_PICK_MAP[pick]

    if market_type == "1x2":
        ph, pd_, pa = tuple(
            apply_correction_to_probs(np.array(grid_to_1x2(grid)), correction)
        )
        prob = {"H": ph, "D": pd_, "A": pa}[outcome]
        odds_col = f"odds_1x2_{outcome}"
        odds = row.get(odds_col)
        if odds is None or pd.isna(odds):
            # AUDIT FIX (B2): a 竞彩 recommendation requires a real 竞彩 SP. Do
            # NOT fall back to psc_* (raw vigged Pinnacle) — that makes
            # edge = model_P × Pinnacle_odds − 1 = model-vs-sharp noise (the
            # EV-vs-Pinnacle bug). The 让球 branch below already raises; this
            # parallel 复式(pool) path was missed by the 53a7dc8 single/parlay fix.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{match_id}: 1X2 {outcome} has no SP (no Pinnacle fallback)",
            )
        return Selection(
            match_id=match_id, market_type="1x2", outcome=outcome,
            probability=float(prob), odds=float(odds),
        )

    # handicap_1x2
    if pd.isna(row.get("handicap_home")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"row {match_id}: pick={pick} requires handicap_home to be set",
        )
    handicap_home = int(row["handicap_home"])
    hp_h, hp_d, hp_a = tuple(
        apply_correction_to_probs(
            np.array(grid_to_handicap_1x2(grid, handicap_home=handicap_home)),
            correction,
        )
    )
    prob = {"H": hp_h, "D": hp_d, "A": hp_a}[outcome]
    odds_col = f"odds_handicap_{outcome}"
    odds = row.get(odds_col)
    if odds is None or pd.isna(odds):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"row {match_id}: pick={pick} but odds_handicap_{outcome} missing",
        )
    return Selection(
        match_id=match_id, market_type="handicap_1x2", outcome=outcome,
        probability=float(prob), odds=float(odds),
    )


@router.post("/recommend/pool", response_model=PoolRecommendResponse)
def recommend_pool_endpoint(req: PoolRecommendRequest) -> PoolRecommendResponse:
    """V8 W6 — 复式 (M-select-N compound parlay) via the V6 W3 engine."""
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )
    m = len(req.fixtures)
    if req.n > m:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"n={req.n} but only {m} fixtures in pool",
        )

    fixtures_df = _fixtures_to_dataframe(req.fixtures)
    feats = build_features_for_fixtures(art, fixtures_df)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))
    correction = _load_correction()

    selections: list[Selection] = []
    for i in range(len(fixtures_df)):
        row = fixtures_df.iloc[i]
        sel = _pick_to_selection(
            row, lambdas[i, 0], lambdas[i, 1], gbm_rho,
            req.fixtures[i].pick,
            correction=correction,
        )
        if sel is not None:
            selections.append(sel)

    rec = recommend_pool(
        selections, n=req.n,
        bankroll=req.bankroll,
        max_total_budget=req.max_total_budget,
        kelly_fraction=req.kelly_fraction,
        max_stake_fraction_per_ticket=req.max_stake_fraction_per_ticket,
    )

    # V11 P1-FE#5 — pool tickets get per-ticket fingerprints
    from nutmeg.v4.observation.recommendation_version import (
        pool_ticket_fingerprint,
        version_hash as _vh,
        fixtures_odds_digest,
    )
    tickets_out: list[PoolTicketResponse] = []
    for t in rec.tickets:
        tk = PoolTicketResponse(
            legs=[
                PoolLegResponse(
                    match_id=leg.match_id,
                    market_type=leg.market_type,
                    outcome=leg.outcome,
                    odds=float(leg.odds),
                    probability=float(leg.probability),
                    edge=float(leg.edge),
                )
                for leg in t.legs
            ],
            hit_probability=float(t.hit_probability),
            combined_odds=float(t.combined_odds),
            ev_per_unit=float(t.ev_per_unit),
            stake=float(t.stake),
            raw_kelly_stake=float(t.raw_kelly_stake),
            expected_return=float(t.expected_return),
        )
        tk.selection_fingerprint = pool_ticket_fingerprint(tk)
        tickets_out.append(tk)

    response = PoolRecommendResponse(
        generated_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model=_model_info_from_artifact(art),
        bankroll=req.bankroll,
        m=rec.m,
        n=rec.n,
        n_combinations=rec.n_combinations,
        n_selected=len(rec.selected_tickets),
        total_stake=float(rec.total_stake),
        total_expected_return=float(rec.total_expected_return),
        tickets=tickets_out,
        version_hash=_vh(
            pool_fingerprints=[tk.selection_fingerprint for tk in tickets_out if tk.selection_fingerprint and tk.stake > 0],
            odds_digest=fixtures_odds_digest(req.fixtures),
        ),
    )

    # V9 W3: record when both gates pass (server env + request flag).
    db_path = _should_record_session(req.record_session)
    if db_path:
        from nutmeg.v4.observation.recorder import record_pool_session
        try:
            record_pool_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_pool_session failed (db=%s); recommendation returned anyway",
                db_path,
            )
            # 体检 A3 — surface the failure (≠ gate-off) so the UI can go red.
            response.record_failed = True
    return response


# ---------- /today-recommendations (V10 W1 Track A) ----------

def _fixture_rows_to_inputs(rows: list[dict]) -> list[FixtureOddsInput]:
    """Convert ingest_odds CSV-row dicts to FixtureOddsInput pydantic objects.

    Drops rows missing required psc_* (closing odds) — those can't be
    scored. Logs the drop count for observability.
    """
    out: list[FixtureOddsInput] = []
    for r in rows:
        try:
            # ingest_odds returns numeric fields as either floats or ""
            # (when bookmaker didn't quote that market). FixtureOddsInput
            # validates `> 1.0`; empty string fails. So we coerce + skip.
            def _f(key: str, default=None):
                v = r.get(key)
                if v is None or v == "":
                    return default
                return float(v)

            psc_h = _f("psc_home")
            psc_d = _f("psc_draw")
            psc_a = _f("psc_away")
            if psc_h is None or psc_d is None or psc_a is None:
                continue

            out.append(FixtureOddsInput(
                date=r["date"],
                league=r["league"],
                home_team=r["home_team"],
                away_team=r["away_team"],
                kickoff_utc=(r.get("kickoff_utc") or None),
                psc_home=psc_h,
                psc_draw=psc_d,
                psc_away=psc_a,
                odds_1x2_H=_f("odds_1x2_H"),
                odds_1x2_D=_f("odds_1x2_D"),
                odds_1x2_A=_f("odds_1x2_A"),
                handicap_home=int(r["handicap_home"]) if r.get("handicap_home") not in (None, "") else None,
                odds_handicap_H=_f("odds_handicap_H"),
                odds_handicap_D=_f("odds_handicap_D"),
                odds_handicap_A=_f("odds_handicap_A"),
                psc_over25=_f("psc_over25"),
                psc_under25=_f("psc_under25"),
                ou_line=_f("ou_line"),   # 体检 Wave1 — was dropped → downstream anchored 2.5
                asian_handicap=(r.get("asian_handicap") or None),
                odds_update=(r.get("odds_update") or None),   # 体检 P1#10 — snapshot age
            ))
        except Exception:  # noqa: BLE001
            # Tolerate per-row failures — better to return partial recs
            # than to 500 the whole endpoint
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: dropped fixture row %r",
                {k: r.get(k) for k in ("date", "league", "home_team", "away_team")},
            )
    return out


# 💸 Odds API 服务侧配额(2026-07-17)— how stale a cached Pinnacle pull may be
# before a PASSIVE serving load pays a credit to refresh it. The three endpoints
# the dashboard polls (today_rec / sp-calc / cup-market) share one on-disk cache
# keyed by sport_key, spanning a 30-key union; at the CLI default an open
# dashboard re-armed that meter 48×/day ⇒ 1,440 credits/day against a 20K/month
# ≈ 667/day plan (2.2×), which is what drained the quota to 401 while the odds
# crons sat paused since 07-12.
#
# That default (1800s) was never arbitrary: it is closing_odds' StartInterval,
# i.e. serving was tuned to RIDE that cron's 30-min cache. But the TTL is a
# refresh TRIGGER (odds_api._request), not a cache-only gate — so with the cron
# paused, the same code silently promoted the dashboard from cache READER to
# cache REFRESHER, spending on all 30 keys where closing_odds spends only on
# sports kicking off inside 75min. Do NOT "restore" this to 1800 to re-couple
# them; passive serving should never be a refresher at any cron cadence.
#
# 6h ⇒ ≤120/day (0.2× plan). Near-KO freshness is closing_odds' job, so what
# ages here is mostly fixtures far from kickoff, and a stale line still surfaces
# to the user via the card's odds_update badge (>2h → ⚠️ 陈旧) rather than
# passing itself off as fresh. 🔄 is untouched (refresh=True bypasses the TTL).
#: 观测口:调用方可以声明「我只是来读盘面的,别把我记进线史」。
#:
#: 🚨 为什么需要它(2026-08-13):`_gather_rows` 会把每次取到的 Pinnacle 线
#: 追加进 `odds_snapshots`,而 `sigma_p_fit` 按 **(比赛, source)** 分组成轨迹、
#: 要求「最靠近开球的点 ≤1.5h」否则整条丢弃。2026-08-12 上线的 `snapshot_board`
#: cron 每天 5 个固定时刻打这两个端点 ⇒ 它会**改掉那份进行中的预注册测量的
#: 抽样人口**(入选闸从「owner 恰好那时候看了」变成「开球时刻是否贴着 cron 槽」)。
#: 实测节奏确实变了:08-11 之前 11–36 个不规则写入时刻/天,08-13 起
#: 我的 5 个槽 02/08/11/14/15:30 UTC 全部到齐。
#:
#: ⛔ 第一版我想「给 cron 一个自己的 source 标签」让 σ_P 的分组自动隔离 ——
#: **不成立**:`record_row_snapshot` 的去重查的是 `(fixture_id)` 或
#: `(date, league, home, away)`,**不带 source**(odds_snapshots.py:198-208)。
#: 谁先跑到谁「认领」这次线变化,另一个被去重掉 ⇒ 标签只会把同一条线史
#: **拆给两个标签**,把 cup_market 的轨迹打出洞,而不是另开一条。
#:
#: ⭐ 正解更简单:快照层**根本不需要**写共享线史表 —— 它自己的
#: `board_leg_snapshot` 已经存了每条腿的 `psc`。让它当纯读者,
#: σ_P 的人口就精确地回到 08-12 之前,零波及面、随时可逆。
#:
#: 📌 顺带发现(**我没引入、也没修**):跨 source 去重意味着
#: `cup_market`/`sp_calc`/`predict_log` 本来就在互相抢同一次线变化,
#: 而 σ_P 却按 source 分组 —— 那份数据地基和分析口径本就不一致。
#: 改它要动共享表的语义(CLV/freeze-gap/δ 全吃这张表),该由 owner 定。
_SERVING_OA_TTL_SECONDS = 6 * 3600

# ── V12 W3 — 竞彩 SP calculator data (近期赛事 tab) ─────────────────────
# The full 14-league production set (matches TodayRecommendationsRequest's
# default + the dashboard TODAY_DEFAULT_LEAGUES). Kept here so the sp-calc
# endpoint covers every league the user bets.
_SP_CALC_LEAGUES = [
    "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
    "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B", "GER_2_BUNDESLIGA",
    "FRA_LIGUE_2", "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA", "BEL_PRO_LEAGUE",
    # V12 W7 — JPN_J1 moved OUT of the model-scored set: the production model
    # was trained on European leagues only, and on J1 it disagrees with the
    # sharp Pinnacle line by up to 13pp (systematically making home favorites
    # underdogs) → out-of-distribution. J1 now goes through the market-mode
    # path (Pinnacle de-vig) in _CUP_MARKET_COMPETITIONS, like cups.
]
# Playoff/barrage: how much to keep the model's own 1X2 P vs the Pinnacle
# de-vig P. <1 leans on the market (which prices the high-stakes context the
# model never learned). 0.3 = mostly market, a little model.
_PLAYOFF_BLEND_ALPHA = 0.3


def _onex_lo(fair) -> tuple[float | None, float | None, float | None]:
    """1X2 三腿判闸下界(δ₁ₓ₂)。`fair` 为 None(无 Pinnacle 线)时全 None。

    ⭐ 和 `_pinnacle_devig_1x2` 贴在一起是**故意**的:凡是拿到那个三元组的路径,
    都在同一屏里看得见它的下界该怎么算 —— 两个模式各写一份是这个项目反复踩过的坑。
    """
    if not fair:
        return (None, None, None)
    from nutmeg.v4.model.onex_calibration import onex_leg_lower_bounds
    return onex_leg_lower_bounds(fair[0], fair[1], fair[2])


def _pinnacle_devig_1x2(h, d, a):
    """De-vig Pinnacle 1X2 → fair [P_home, P_draw, P_away] via WPO (corrects the
    favourite-longshot bias; single source = ``nutmeg.v4.model.devig``). Returns
    None on missing/NaN/≤1.0 input (so the API returns 422, not a 500). The
    model-feature de-vigs stay on basic normalization — this is the EV/analysis path."""
    from nutmeg.v4.model.devig import devig_1x2
    p = devig_1x2(h, d, a)
    return list(p) if p else None


def _model_board_handicap_lines(f, model_grid, corr) -> list[HandicapLineProb]:
    """V12 W8 — 让球 lines for the 13-league model board.

    Switched from the model's own DC grid to MARKET-REVERSE (a Dixon-Coles grid
    fit to the de-vig Pinnacle 1X2 + O/U). A leakage-free walk-forward on 4330
    EU matches (24/25) showed the reverse sits on Pinnacle's own Asian-Handicap
    ceiling (cover Brier 0.2045) while the model grid is +2.4e-3 worse — the
    model's total goals isn't anchored to the O/U, the reverse's is. The model
    still drives the 1X2; only 让球 changes. Falls back to the model grid when
    the Pinnacle 1X2 is absent or the fit raises."""
    fair = _pinnacle_devig_1x2(
        getattr(f, "psc_home", None), getattr(f, "psc_draw", None), getattr(f, "psc_away", None)
    )
    if fair is not None:
        try:
            from nutmeg.v4.model.market_handicap import (
                c1_leg_lower_bounds,
                devig_over,
                implied_handicap_lines,
            )
            p_over = devig_over(getattr(f, "psc_over25", None), getattr(f, "psc_under25", None))
            ou_line = float(getattr(f, "ou_line", None) or 2.5)
            _lg = getattr(f, "league", None)   # 🚨 δ 范围闸:必须传
            return [
                _hc_line_prob(ln, ph, pd_, pa, c1_leg_lower_bounds, league=_lg)
                for ln, ph, pd_, pa in implied_handicap_lines(
                    fair[0], fair[1], fair[2], p_over, ou_line=ou_line, c1=True,
                    league=_lg,
                )
            ]
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "market-reverse handicap failed (%s vs %s); model-grid fallback",
                getattr(f, "home_team", "?"), getattr(f, "away_team", "?"),
            )
    # 模型网格兜底(Pinnacle 缺席时)—— **不吃 C1**:C1 修的是「市场 1X2 反推出的
    # DC 网格」的净胜切分偏差,而这里的 grid 来自 CatBoost 自己的 λ,来源不同、偏差
    # 未测。既然没上 δ,就没有 δ 的估计误差 → 下界留空(None),前端 `?? 点估` 兜住。
    out: list[HandicapLineProb] = []
    for line in range(-3, 4):
        hh, hd, ha = tuple(apply_correction_to_probs(
            np.array(grid_to_handicap_1x2(model_grid, handicap_home=line)), corr))
        out.append(HandicapLineProb(
            line=line, p_home=float(hh), p_draw=float(hd), p_away=float(ha)))
    return out


def _calc_predictions(art, fixtures) -> list[SinglePrediction]:
    """V12 W3 — per-fixture model output for the 竞彩 SP calculator: 1X2 P,
    Pinnacle-odds echo, and handicap P across integer lines −3..+3 (all from
    one Dixon-Coles grid → instant client-side EV).

    Playoff/barrage adjustment: the model's learned feature→λ map is
    unreliable for these rare high-stakes matches, but Pinnacle prices the
    context — so for flagged fixtures we blend the served 1X2 P toward the
    Pinnacle de-vig P (lean on market). Handicap P stays grid-based.

    Defensive: returns [] on missing artifact / any failure so the dashboard
    degrades gracefully instead of 500-ing.
    """
    if art is None or not fixtures:
        return []
    import logging

    from nutmeg.v4.data.playoff_context import detect_playoff
    try:
        rho = float(art.metadata.get("gbm_rho", -0.10))
        corr = _load_correction()
        lambdas = predict_lambdas(
            art, build_features_for_fixtures(art, _fixtures_to_dataframe(fixtures))
        )
    except Exception:  # noqa: BLE001 — batch feature/λ stage: nothing salvageable
        logging.getLogger(__name__).exception("_calc_predictions failed (batch stage)")
        return []
    preds: list[SinglePrediction] = []
    for i, f in enumerate(fixtures):
        # 体检 Wave2 — per-fixture degradation. One poisoned fixture (bad λ,
        # unfittable grid, weird odds) used to abort the WHOLE board via the
        # single batch try → the dashboard showed "今天没比赛" while 20 healthy
        # matches existed. Skip the bad one loudly, keep the rest.
        try:
            lh, la = lambdas[i]
            grid = score_grid(lh, la, rho=rho)
            ph, pd_, pa = tuple(apply_correction_to_probs(np.array(grid_to_1x2(grid)), corr))
            if detect_playoff(f.league, f.date) is not None:
                pin = _pinnacle_devig_1x2(f.psc_home, f.psc_draw, f.psc_away)
                if pin is not None:
                    a = _PLAYOFF_BLEND_ALPHA
                    ph, pd_, pa = (
                        a * ph + (1 - a) * pin[0],
                        a * pd_ + (1 - a) * pin[1],
                        a * pa + (1 - a) * pin[2],
                    )
            hc_lines = _model_board_handicap_lines(f, grid, corr)
            # 2026-08-06 — 纯市场公允 P,和模型 P 并列下发。**同一个 WPO 函数**
            # 供:这里的显示、前端的市场 EV、手填后的 reprice 端点 ⇒ 三处不可能
            # 漂开。前端原来自己 basic 去vig 画「市」列,和 EV 路的 WPO 差 0.5pp。
            mkt = _pinnacle_devig_1x2(f.psc_home, f.psc_draw, f.psc_away)
            preds.append(SinglePrediction(
                home_team=f.home_team, away_team=f.away_team,
                league=f.league, date=f.date,
                kickoff_utc=getattr(f, "kickoff_utc", None),
                lambda_home=float(lh), lambda_away=float(la),
                p_home_1x2=float(ph), p_draw_1x2=float(pd_), p_away_1x2=float(pa),
                p_home_market=(float(mkt[0]) if mkt else None),
                p_draw_market=(float(mkt[1]) if mkt else None),
                p_away_market=(float(mkt[2]) if mkt else None),
                # δ₁ₓ₂ 下界 —— 与 mkt 同源同一次去vig,不可能漂开
                **dict(zip(("onex_lo_home", "onex_lo_draw", "onex_lo_away"),
                           _onex_lo(mkt), strict=True)),
                psc_home=f.psc_home, psc_draw=f.psc_draw, psc_away=f.psc_away,
                psc_over25=getattr(f, "psc_over25", None),
                psc_under25=getattr(f, "psc_under25", None),
                ou_line=getattr(f, "ou_line", None),   # 体检 Wave1 — echo real line
                odds_update=getattr(f, "odds_update", None),   # 体检 P1#10 — snapshot age
                handicap_lines=hc_lines,
                # 🚨 用 `f.league`(同行 2142),**不是** `_model_board_handicap_lines`
                # 里那个 `_lg` —— 那是另一个函数的局部名。我第一版写了 `_lg` ⇒
                # `NameError`,而它被下面那个 `except Exception` 吞成
                # 「fixture poisoned, skipped」⇒ **标准板返回 0 场 + HTTP 200**。
                # ⭐ 又一次「HTTP 200 ≠ 成功」:面板会显示空,而不是显示错误。
                delta_scope=_delta_scope(f.league),
                asian_handicap_lines=_model_board_asian_handicap(f, grid),
                margin_bands=_mk_margin_bands(grid_to_margin_bands(grid)),
            ))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "_calc_predictions: fixture poisoned, skipped (%s vs %s, %s %s)",
                getattr(f, "home_team", "?"), getattr(f, "away_team", "?"),
                getattr(f, "league", "?"), getattr(f, "date", "?"),
            )
    return preds


def _utc_today():
    """UTC "today" for fixture-date windows — NEVER the process-local date.

    API-Football match dates are UTC. A window anchored on the local date
    (Asia/Shanghai) rolls forward at Beijing midnight (16:00 UTC) and silently
    drops every fixture kicking off 16:00–23:59 UTC that night (= Beijing
    00:00–07:59, the late-night EU slate — the exact freeze-gap targets) HOURS
    before kickoff. Caught live 2026-07-03 00:13 Beijing: Spain (KO −2h47m) and
    Portugal (KO −6h47m) had vanished from 近期赛事. A UTC anchor can never
    exclude a pre-kickoff fixture (kickoff ≥ now ⇒ UTC-date(kickoff) ≥
    UTC-date(now)); already-kicked-off same-day rows are handled by the
    _gather_rows kickoff-buffer guard where wired."""
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).date()


@router.get(
    "/predictions/sp-calc",
    response_model=SpCalcResponse,
    summary="V12 W3 — N-day fixtures + model P for the 竞彩 SP calculator",
)
def predictions_sp_calc(
    days: int = 3, refresh_odds: bool = False, bettable_only: bool = True,
    record_line_history: bool = True,
) -> SpCalcResponse:
    import datetime as _dt
    from pathlib import Path as _Path

    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
        _odds_api_available,
    )

    if not 1 <= days <= 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be in [1, 7]",
        )
    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )
    today = _utc_today()   # UTC anchor (local date drops the late-night EU slate)
    all_preds: list[SinglePrediction] = []
    pending: list[PendingFixture] = []
    # 体检 Wave1 → 2026-07-09 hotfix: the OA feed is DATE-INDEPENDENT, so one 🔄
    # should pull each sport at most ONCE. The old `d == 0` gate broke the
    # bettable filter (a league whose 竞彩 match is tomorrow never refreshed);
    # now _gather_rows dedups per sport via this shared set, firing on the
    # FIRST day the league has a (bettable) fixture.
    _oa_refreshed: set[str] = set()
    for d in range(days):
        on_date = today + _dt.timedelta(days=d)
        try:
            # V12 W6 — require_odds=False keeps fixtures whose Pinnacle line
            # isn't open yet (psc_* = None) so we can list them as 待开盘.
            rows, _n, _s = _gather_rows(
                _SP_CALC_LEAGUES, on_date,
                cache_dir=_Path("data/external/api_football"),
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=refresh_odds,
                require_odds=False,
                min_kickoff_buffer_minutes=5,
                # ⭐ `record_line_history=false` 的调用方(snapshot_board cron)
                # 只读不写 —— 见 `_SERVING_OA_TTL_SECONDS` 上方那段。
                snapshot_db=(_observation_db_path() if record_line_history else None),
                snapshot_source="sp_calc",
                use_odds_api=_odds_api_available(),
                odds_api_refresh=refresh_odds,
                # 2026-07-09 — only spend that refresh on 竞彩-bettable leagues/fixtures.
                bettable_refresh_only=bettable_only,
                oa_refreshed=_oa_refreshed,
                oa_ttl_seconds=_SERVING_OA_TTL_SECONDS,
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("sp-calc fetch failed for %s", on_date)
            rows = []
        # Split: a Pinnacle 1X2 quote → scored (model P reliable); no quote →
        # 待开盘 (psc is a strong feature, so a psc-free P would mislead).
        scored_rows = [r for r in rows if r.get("psc_home") is not None]
        pending_rows = [r for r in rows if r.get("psc_home") is None]
        all_preds.extend(_calc_predictions(art, _fixture_rows_to_inputs(scored_rows)))
        for r in pending_rows:
            if not r.get("home_team") or not r.get("away_team"):
                continue
            pending.append(PendingFixture(
                home_team=r["home_team"],
                away_team=r["away_team"],
                league=r["league"],
                date=r["date"],
                kickoff_utc=(r.get("kickoff_utc") or None),
            ))
    _attach_jingcai_sp(all_preds)
    return SpCalcResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date_start=today.isoformat(),
        date_end=(today + _dt.timedelta(days=days - 1)).isoformat(),
        days=days,
        fixtures_fetched=len(all_preds) + len(pending),
        predictions=all_preds,
        pending_fixtures=pending,
    )


def _ev_board_legs(predictions, *, min_ev, bankroll, kelly_fraction):
    """Pure core of the 真 EV 板: a SinglePrediction list → (legs, n_fixtures,
    n_legs_with_sp, n_positive). EV = P(Pinnacle de-vig) × 竞彩SP − 1 per leg. 'had' legs
    price the 竞彩 1X2 SP (jc_*) off the de-vig Pinnacle 1X2; 'hhad' legs price the 竞彩
    让球 SP (jc_hc_*) off the prediction's O/U-double-anchored ``handicap_lines`` at
    ``jc_hc_line`` (validated vs Pinnacle's own AH ~1pp). Only predictions carrying BOTH a
    Pinnacle line AND a 竞彩 SP qualify. Dedup by (date, home, away). Injectable for testing."""
    seen: set = set()
    legs: list[EvLeg] = []

    def _push(pred, diso, market, outcome, line, prob, odds):
        if prob is None or not odds or float(odds) <= 1.0:
            return
        o = float(odds)
        ev = prob * o - 1.0
        b = o - 1.0
        frac = max(0.0, ev / b) if b > 0 else 0.0
        legs.append(EvLeg(
            date=diso, home_team=pred.home_team, away_team=pred.away_team,
            league=pred.league, kickoff_utc=pred.kickoff_utc, market=market,
            outcome=outcome, handicap_line=line, p_pinnacle=round(float(prob), 4),
            jc_sp=o, ev=ev,
            kelly_stake=round(bankroll * kelly_fraction * frac, 2),
        ))

    for p in predictions:
        diso = p.date.isoformat() if hasattr(p.date, "isoformat") else str(p.date)
        key = (diso, p.home_team, p.away_team)
        if key in seen:
            continue
        dv = _pinnacle_devig_1x2(p.psc_home, p.psc_draw, p.psc_away)
        if dv is None:
            continue
        has_had = bool(p.jc_home and p.jc_draw and p.jc_away)
        has_hhad = bool(
            p.jc_hc_home and p.jc_hc_draw and p.jc_hc_away and p.jc_hc_line is not None
        )
        if not (has_had or has_hhad):
            continue
        seen.add(key)
        if has_had:
            for oc, prob, odds in zip(
                ("home", "draw", "away"), dv,
                (p.jc_home, p.jc_draw, p.jc_away), strict=True,
            ):
                _push(p, diso, "had", oc, None, prob, odds)
        if has_hhad:
            line = int(p.jc_hc_line)
            hl = next((x for x in p.handicap_lines if x.line == line), None)
            if hl is not None:
                for oc, prob, odds in zip(
                    ("home", "draw", "away"),
                    (hl.p_home, hl.p_draw, hl.p_away),
                    (p.jc_hc_home, p.jc_hc_draw, p.jc_hc_away), strict=True,
                ):
                    _push(p, diso, "hhad", oc, line, prob, odds)

    # n_fixtures = fixtures that actually produced ≥1 priceable leg (a fixture with
    # 竞彩 SP but no matching handicap_line yields 0 legs and must NOT inflate the count).
    n_fixtures = len({(leg.date, leg.home_team, leg.away_team) for leg in legs})
    n_positive = sum(1 for leg in legs if leg.ev >= 0.05)
    kept = sorted((leg for leg in legs if leg.ev >= min_ev),
                  key=lambda leg: leg.ev, reverse=True)
    return kept, n_fixtures, len(legs), n_positive


@router.get(
    "/recommend/ev-board",
    response_model=EvBoardResponse,
    summary="真 EV 推荐板 — P(Pinnacle 去vig)×竞彩SP−1, 仅有竞彩 SP 的腿, 按 EV 排",
)
def recommend_ev_board(
    days: int = 3,
    min_ev: float = 0.05,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
    refresh_odds: bool = False,
) -> EvBoardResponse:
    """The honest EV board behind 单关/串关/复式. Gathers the SAME live surfaces the
    近期赛事 tab shows — ``predictions_sp_calc`` (13 受训联赛) + ``predictions_cup_market``
    (WC/EURO/杯赛 + 芬超/日职, market-mode) — both carrying FRESH Pinnacle (→ de-vig fair
    P) + the 竞彩 SP on file (``_attach_jingcai_sp``). For every fixture with BOTH, EV =
    P_pinnacle_devig × 竞彩SP − 1 per leg (NOT model-vs-market, NOT Pinnacle's own price).
    Gated at ``min_ev``, sorted by EV desc, fractional-Kelly staked. Returns SINGLES; the
    frontend forms 串/复 from them. Usually empty (the ~12% 竞彩 vig wall) — that empty
    state IS the honest 空仓 signal. See [[soft-water-leg-finding-measured]]."""
    import datetime as _dt
    import logging as _logging

    if not 1 <= days <= 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be in [1, 7]",
        )
    if bankroll <= 0 or not 0.0 < kelly_fraction <= 1.0 or not -1.0 <= min_ev <= 1.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="bankroll>0, kelly_fraction∈(0,1], min_ev∈[-1,1] required",
        )
    preds: list = []
    gathered_ok = 0
    for gather in (predictions_sp_calc, predictions_cup_market):
        try:
            preds.extend(gather(days=days, refresh_odds=refresh_odds).predictions)
            gathered_ok += 1
        except Exception:  # noqa: BLE001 — one surface failing must not 500 the board
            _logging.getLogger(__name__).warning(
                "ev-board gather %s failed",
                getattr(gather, "__name__", "gather"), exc_info=True,
            )
    # Both surfaces down → a real outage, NOT an honest 空仓. Surface it as 503 so an
    # empty board can only ever mean "no +EV legs", never "system unavailable".
    if gathered_ok == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ev-board prediction surfaces unavailable; try again shortly",
        )
    legs, n_fixtures, n_with_sp, n_positive = _ev_board_legs(
        preds, min_ev=min_ev, bankroll=bankroll, kelly_fraction=kelly_fraction,
    )
    return EvBoardResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        days=days,
        min_ev=min_ev,
        bankroll=bankroll,
        n_fixtures=n_fixtures,
        n_legs_with_sp=n_with_sp,
        n_positive=n_positive,
        legs=legs,
    )


# ── V12 W7 — 杯赛市场模式 (Tier 1: UCL/UEL/UECL + 五大联赛国内杯 + WC/EURO) ──────
# The model is out-of-distribution for cups: the cup ablation was NEGATIVE, and
# neutral-venue finals break its home-advantage assumption. Cups are also the
# sharpest, most-liquid markets in football. So we DON'T model them — we serve
# Pinnacle's de-vig fair 1X2 as the probability and let the user price 竞彩 SP
# against it (市场模式). Cups never enter the model-driven 国际盘口 auto board;
# this is a manual, market-anchored surface only.
_CUP_MARKET_COMPETITIONS = [
    "UCL", "UEL", "UECL",
    "FAC", "COPA_DEL_REY", "COPPA_ITALIA", "DFB_POKAL", "COUPE_DE_FRANCE",
    "WC", "EURO", "WC_QUAL_UEFA",
    # V12 W7 — JPN_J1: not a cup, but out-of-distribution for the model
    # (European-trained; diverges ~13pp from the sharp J1 line). Priced off
    # Pinnacle de-vig here instead of model-scored — same treatment as cups.
    "JPN_J1",
    # V12 W8 — market-mode expansion: 竞彩-common leagues Pinnacle prices that
    # we never trained on. Served via the SAME de-vig 1X2 + reverse 让球 engine
    # (handicap validated to sit on Pinnacle's AH ceiling). User-confirmed set:
    # Nordic + APAC + 4 European. No model, no training — pure market.
    "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "DNK_SUPERLIGA", "FIN_VEIKKAUSLIIGA",
    "KOR_K_LEAGUE_1", "JPN_J2", "AUS_A_LEAGUE",
    "SCO_PREMIERSHIP", "TUR_SUPER_LIG", "SUI_SUPER_LEAGUE",
    "USA_MLS", "BRA_SERIE_A",   # 补(2026-07-14)美洲市场模式
    # 补荷乙 + 英联赛杯(2026-08-05 owner)。两者都**不在**训练集里 ⇒ 只能走市场
    # 模式。赔率来源实测有别,记在这里免得以后误判「荷乙怎么线这么旧」:
    #   · EFL_CUP  → Odds API 有 `soccer_england_efl_cup`(active=True)+ AF 镜像,
    #                双覆盖,鲜线叠加正常工作;
    #   · 荷乙     → Odds API **根本没有**这个 sport(只有 eredivisie),只走 AF 的
    #                Pinnacle 镜像(实测 fixture 1551741 有 Pinnacle;2026-08-08 复核
    #                当日 3/3 全上了可定价区),线会比有 sport key 的联赛旧一些 ——
    #                这是数据现实,不是 bug。
    #                ⚠️ 原文写的是「同 JPN_J2 先例」,2026-08-08 已删 —— 但删的理由
    #                我当天写错过一次(说「J2 的 AF 镜像也是空的」),当晚就被证伪:
    #                AF 对 J2 是**稀疏且晚**(那轮 10 场只 1 场有线,临场 ~23h 才发),
    #                不是「没有」。详见 odds_api.SPORT_KEYS 那条(记着错法)。
    #                ⇒ 「缺 sport key ⇒ 有 AF 镜像兜底」不是规则,是**逐联赛**的事实,
    #                   每加一个没 key 的联赛都得自己数一遍行,不能靠先例外推。
    # 补三个(2026-08-09 owner)。三个都**不在**训练集 ⇒ 只能走市场模式。
    # 覆盖各不相同(全部 2026-08-09 实测,别外推):
    #   · 解放者杯 → Odds API active=True + AF 镜像 14 家含 Pinnacle,双覆盖;
    #   · 欧超杯   → Odds API **无 key**,只走 AF 镜像(那场实测 13 家含 Pinnacle);
    #                ⚠️ 一年只有一场,别对样本量有幻想;
    #   · 沙职     → AF **不给赔率**(上赛季已打完的 5 场也 0/5),Odds API 是唯一源;
    #                key 休赛期 active=False,自激活前会走「竞彩在售+手填」那条路。
    "COPA_LIBERTADORES", "UEFA_SUPER_CUP", "SAU_PRO_LEAGUE",
    "NED_EERSTE_DIVISIE", "EFL_CUP",
    # 补韩国杯(2026-08-18 owner)。线源实测(⛔ 别外推,逐条数过):
    #   · Odds API → 175/175 sport 全表核过,韩国只有 `soccer_korea_kleague1`,
    #                **没有** cup 这个 sport ⇒ 这条路对 294 永远空;
    #   · AF /odds → **稀疏**,不是没有:2026-08-19 那轮 8 场 R16 里**只有 1 场**
    #                (Anyang×Jeju,fid 1607203)有线 —— 12 家含 Pinnacle
    #                (H2.87/D3.09/A2.31);其余 7 场 0 家。同 JPN_J2「稀疏且晚」那条
    #                先例(⚠️ 我第一版只探了 4 场小队对阵、全 0,就误写成「AF 真不给
    #                韩国杯挂线」——当天被同轮的 Anyang×Jeju 证伪。记着这个错法:
    #                探赔率覆盖必须把**那一轮全扫一遍**,marquee 场和小队场结论相反)。
    # ⇒ 两类腿都要:marquee 对阵 AF 自动挂 Pinnacle(psc 自动填、直接可投);其余
    #    场次 psc=None,走**「竞彩在售 + 手填 Pinnacle」**(同沙职休赛期那条路)。
    # 把它放进本表**正是为了让这两条都通**:①gather `require_odds=False` ⇒ 无赔率的
    # 赛程也会作为 psc_*=None 的卡片冒出来(否则 gather 迭代本表,压根不拉 294);
    # ②`_fixture_to_match_input` 的 925 行闸命中 ⇒ 胜平负按 **de-vig Pinnacle(AF 自动
    # 或手填,同一条)逐字定价**,而不是喂给对韩国杯 OOD 的欧洲模型(那会出垃圾 P)。
    # 队表那一格仍在 `registry_coverage.OUT_OF_SCOPE` 豁免(全表 64 队跨 K1~业余,
    # 52 支无 zh 证据,⛔ 不猜)⇒ `--gate` 不查它、不假红,同 FAC/EFL_CUP。
    # ⚠️ 2026-08-18:「无 zh 证据」措辞已在 `registry_coverage.py` 更正 ——
    #   中文串在 `v4_jingcai_history.db` 里**是有的**(大邱FC 922 行等),
    #   缺的是**同行的英文侧** ⇒ 该走比分锚,不是「没证据」。
    # exit 条件:哪天 Odds API 上了 korea cup(叠鲜线),或 AF 把覆盖从 marquee 扩到
    # 全轮 —— 都自动叠上来,这里不用再动。
    "KOR_FA_CUP",
]


def _delta_scope(league: str | None) -> str:
    """δ 范围闸三态(`applied`/`out_of_scope`/`missing`)—— 薄封装。

    ⛔ **别在这里重新实现判据。** 它和 `_delta_in_scope`(判闸用的那个)必须
    走同一个 `market_handicap.delta_scope`,否则就会出现「判闸按 A、徽章按 B」——
    本仓在 WPO 去vig 上踩过一次(server 一份、JS 一份,漂了 11pp)。
    """
    from nutmeg.v4.model.market_handicap import delta_scope
    return delta_scope(league)


def _hc_line_prob(line, ph, pd_, pa, bounds_fn, *, league=None) -> HandicapLineProb:
    """A′(2026-07-17)— 把点估 + δ 的逐腿下界一起打包给前端。

    点估用于**显示 EV**;下界用于**判闸**(绿灯/候选)。两者同源同一次拟合,
    所以面板上「+7.3% [−1.1%, +15.7%] · 下界未过闸」三者自洽 —— 这正是
    B 方案做不到的(它会让绿灯和禁令打架)。
    """
    # 🚨 δ 范围闸:`league` 必须一路透传到下界函数 —— 否则覆盖内的联赛会被
    #    当成未校准、吃 `_UNCAL_SE` 地板(判闸过严,方向相反的错)。
    lo_h, lo_d, lo_a = bounds_fn(
        int(line), float(ph), float(pd_), float(pa), league=league)
    return HandicapLineProb(
        line=int(line), p_home=float(ph), p_draw=float(pd_), p_away=float(pa),
        p_home_lo=lo_h, p_draw_lo=lo_d, p_away_lo=lo_a,
    )


def _market_handicap_lines(fair, r: dict) -> list[HandicapLineProb]:
    """V12 W8 — market-implied 让球 for a market-mode fixture: reverse-map the
    de-vig 1X2 + Pinnacle O/U 2.5 to a Dixon-Coles goal grid, then read off the
    integer handicap lines. Pure market (no model) — validated against
    Pinnacle's own Asian Handicap within ~1pp. Degrades to a 1X2-only fit when
    the O/U is absent, and to [] (1X2-only card) if the fit raises."""
    try:
        from nutmeg.v4.model.market_handicap import (
            c1_leg_lower_bounds,
            devig_over,
            implied_handicap_lines,
        )
        p_over = devig_over(r.get("psc_over25"), r.get("psc_under25"))
        ou_line = float(r.get("ou_line") or 2.5)
        _lg = r.get("league")                 # 🚨 δ 范围闸:必须传
        return [
            _hc_line_prob(line, ph, pd_, pa, c1_leg_lower_bounds, league=_lg)
            for line, ph, pd_, pa in implied_handicap_lines(
                float(fair[0]), float(fair[1]), float(fair[2]), p_over,
                ou_line=ou_line, c1=True, league=_lg,
            )
        ]
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "market handicap fit failed for %s vs %s",
            r.get("home_team"), r.get("away_team"),
        )
        return []


def _mk_margin_bands(band_dicts: list, top: int = 4) -> list[MarginBand]:
    """``grid_to_margin_bands`` dicts → MarginBand schema (scores capped at ``top``)."""
    return [
        MarginBand(
            margin=int(b["margin"]), is_tail=bool(b["is_tail"]), p=float(b["p"]),
            scores=[ScoreCell(home=int(i), away=int(j), p=float(p))
                    for i, j, p in b["scores"][:top]],
        )
        for b in band_dicts
    ]


def _market_margin_bands(fair, r: dict) -> list[MarginBand]:
    """净胜球分组 for a market-mode fixture — same reverse-fit grid as
    ``_market_handicap_lines``. READ tool, not a signal. [] on any failure."""
    try:
        from nutmeg.v4.model.market_handicap import devig_over, implied_margin_bands
        p_over = devig_over(r.get("psc_over25"), r.get("psc_under25"))
        ou_line = float(r.get("ou_line") or 2.5)
        return _mk_margin_bands(implied_margin_bands(
            float(fair[0]), float(fair[1]), float(fair[2]), p_over, ou_line=ou_line,
        ))
    except Exception:  # noqa: BLE001
        return []


def _real_ah_board(raw):
    """Parse the ``asian_handicap`` JSON ({line: {home, away}}) → {float: {...}}."""
    if not raw:
        return None
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
        return {float(k): v for k, v in d.items()} or None
    except Exception:  # noqa: BLE001
        return None


def _asian_handicap_lines(fair, p_over, ou_line, real_raw) -> list[AsianHandicapLineProb]:
    """INTERNATIONAL Asian Handicap (HALF-line, 2-way: cover/not, NO push) board
    for the 让球胜平负 PREDICTION — real Pinnacle de-vig where that line is quoted,
    DC-grid cover-prob fallback otherwise. ``fair`` = de-vig 1X2 triple. This is
    the NON-竞彩 international handicap rule (≠ the 竞彩 integer ``handicap_lines``)."""
    try:
        from nutmeg.v4.model.market_handicap import asian_handicap_board
        return [
            AsianHandicapLineProb(line=ln, p_home=ph, p_away=pa, source=src)
            for ln, ph, pa, src in asian_handicap_board(
                float(fair[0]), float(fair[1]), float(fair[2]), p_over,
                real_board=_real_ah_board(real_raw), ou_line=ou_line,
            )
        ]
    except Exception:  # noqa: BLE001
        return []


def _model_board_asian_handicap(f, model_grid) -> list[AsianHandicapLineProb]:
    """国际盘 AH board. Fit to the de-vig Pinnacle 1X2 (+ O/U) when present (same
    market anchor as the 让球 integer board); else read cover-P off the model
    grid. Real Pinnacle AH de-vig overlays either, per line."""
    fair = _pinnacle_devig_1x2(
        getattr(f, "psc_home", None), getattr(f, "psc_draw", None), getattr(f, "psc_away", None)
    )
    real_raw = getattr(f, "asian_handicap", None)
    if fair is not None:
        from nutmeg.v4.model.market_handicap import devig_over
        p_over = devig_over(getattr(f, "psc_over25", None), getattr(f, "psc_under25", None))
        ou_line = float(getattr(f, "ou_line", None) or 2.5)
        return _asian_handicap_lines(fair, p_over, ou_line, real_raw)
    try:
        from nutmeg.v4.model.market_handicap import (
            DEFAULT_AH_LINES,
            dc_home_cover_prob,
            devig_asian_handicap_line,
        )
        real = _real_ah_board(real_raw)
        out: list[AsianHandicapLineProb] = []
        for ln in DEFAULT_AH_LINES:
            dv = (
                devig_asian_handicap_line(real[float(ln)].get("home"), real[float(ln)].get("away"))
                if real and float(ln) in real else None
            )
            if dv is not None:
                ph, pa, src = dv[0], dv[1], "mkt"
            else:
                ph, pa, src = dc_home_cover_prob(model_grid, float(ln)), 0.0, "dc"
                pa = 1.0 - ph
            out.append(AsianHandicapLineProb(line=float(ln), p_home=ph, p_away=pa, source=src))
        return out
    except Exception:  # noqa: BLE001
        return []


def _market_asian_handicap_lines(fair, r: dict) -> list[AsianHandicapLineProb]:
    """市场模式 AH board (non-竞彩): real Pinnacle de-vig where quoted, DC fallback
    fit to the de-vig 1X2 + O/U otherwise."""
    from nutmeg.v4.model.market_handicap import devig_over
    return _asian_handicap_lines(
        fair, devig_over(r.get("psc_over25"), r.get("psc_under25")),
        float(r.get("ou_line") or 2.5), r.get("asian_handicap"),
    )


def _row_to_market_prediction(r: dict) -> SinglePrediction | None:
    """Build a market-mode SinglePrediction: 1X2 P = Pinnacle de-vig (NOT
    model). Returns None when the row has no Pinnacle 1X2 quote (caller routes
    those to pending_fixtures / 待开盘).

    V12 W8 — also carries market-implied 让球 lines (DC fit to 1X2 + O/U) so the
    market-mode card prices 竞彩 让球 SP live, not just 胜平负."""
    fair = _pinnacle_devig_1x2(r.get("psc_home"), r.get("psc_draw"), r.get("psc_away"))
    if fair is None:
        return None
    return SinglePrediction(
        home_team=r["home_team"], away_team=r["away_team"],
        league=r["league"], date=r["date"],
        kickoff_utc=(r.get("kickoff_utc") or None),
        lambda_home=0.0, lambda_away=0.0,
        p_home_1x2=float(fair[0]), p_draw_1x2=float(fair[1]), p_away_1x2=float(fair[2]),
        # δ₁ₓ₂ 下界 —— 市场模式的 1X2 点估就在 p_*_1x2(这里 p_*_market 一律 null)
        **dict(zip(("onex_lo_home", "onex_lo_draw", "onex_lo_away"),
                   _onex_lo(fair), strict=True)),
        psc_home=r.get("psc_home"), psc_draw=r.get("psc_draw"), psc_away=r.get("psc_away"),
        psc_over25=r.get("psc_over25"), psc_under25=r.get("psc_under25"),
        # V14 — the ACTUAL total line those prices are quoted at (2.75 for the
        # Sirius overlay line); without it the card labels every O/U "2.5"
        # (体检 2026-07-03). Server-side 让球反推 already used it (line above).
        ou_line=r.get("ou_line"),
        handicap_lines=_market_handicap_lines(fair, r),
        delta_scope=_delta_scope(r.get("league")),
        asian_handicap_lines=_market_asian_handicap_lines(fair, r),
        odds_update=r.get("odds_update"),
        # 2026-07-23 — 出处回显。_apply_odds_api_overlay 打过标的是 'odds_api',
        # 没打过 = 走 AF 镜像。前端记账时原样送回(手填会改成 'manual')。
        odds_source=r.get("odds_source") or "api_football",
        market_mode=True,
        sharp_flip=bool(r.get("sharp_flip", False)),
        margin_bands=_market_margin_bands(fair, r),
    )


@router.get(
    "/predictions/cup-market",
    response_model=SpCalcResponse,
    summary="V12 W7 — Tier-1 cup fixtures priced off Pinnacle de-vig (市场模式)",
)
def predictions_cup_market(
    days: int = 3, refresh_odds: bool = False, bettable_only: bool = True,
    record_line_history: bool = True,
) -> SpCalcResponse:
    """市场模式: Tier-1 cups (UCL/UEL/UECL + big domestic cups + WC/EURO) over an
    N-day window, each carrying Pinnacle de-vig fair 1X2 as its probability — NO
    model (it's OOD for cups). Fixtures with no Pinnacle line yet → 待开盘.

    Reuses _gather_rows(require_odds=False). No artifact needed (pure market).

    V14 — called PASSIVELY by the dashboard: 市场模式 lives on the 今日推荐 landing
    tab (loadCupMarket → renderMarketPred → #mktpred-section), so this fires on
    page load, on tab switch, and on the 60s poll — NOT user-triggered. Cost is
    bounded by the TTL, not by call frequency: those passive calls leave
    refresh_odds=False, so _gather_rows's odds_api.fetch_pinnacle_lookup serves
    cache until ``_SERVING_OA_TTL_SECONDS`` (6h) lapses — only a call landing
    after that window spends credit. Cup competitions are sparse (most days
    discovery returns 0 fixtures), which is what keeps the auto-load affordable.
    Owner decision 2026-07-17: keep the passive load and gate cost at that TTL
    (same day the TTL itself moved 1800s→6h — see the constant's rationale).
    """
    import datetime as _dt
    from pathlib import Path as _Path

    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
        _odds_api_available,
    )

    if not 1 <= days <= 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be in [1, 7]",
        )
    today = _utc_today()   # UTC anchor (local date drops the late-night EU slate)
    preds: list[SinglePrediction] = []
    pending: list[PendingFixture] = []
    # 2026-07-09 hotfix — same one-pull-per-sport dedup as sp-calc (see there).
    _oa_refreshed: set[str] = set()
    for d in range(days):
        on_date = today + _dt.timedelta(days=d)
        try:
            rows, _n, _s = _gather_rows(
                _CUP_MARKET_COMPETITIONS, on_date,
                cache_dir=_Path("data/external/api_football"),
                bookmaker_id=PINNACLE_BOOKMAKER_ID,
                refresh_fixtures=False, refresh_odds=refresh_odds,
                require_odds=False,
                min_kickoff_buffer_minutes=5,
                # 体检 A1 — the 市场模式 board (incl. 🔄 refresh) feeds the
                # odds_snapshots line history; near-KO refreshes are exactly
                # the closing-line evidence CLV needs.
                # ⭐ `record_line_history=false` 的调用方(snapshot_board cron)
                # 只读不写 —— 见 `_SERVING_OA_TTL_SECONDS` 上方那段。
                snapshot_db=(_observation_db_path() if record_line_history else None),
                snapshot_source="cup_market",
                use_odds_api=_odds_api_available(),
                odds_api_refresh=refresh_odds,
                # 2026-07-09 — refresh only 竞彩-bettable leagues/fixtures.
                bettable_refresh_only=bettable_only,
                oa_refreshed=_oa_refreshed,
                oa_ttl_seconds=_SERVING_OA_TTL_SECONDS,
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("cup-market fetch failed for %s", on_date)
            rows = []
        for r in rows:
            mp = _row_to_market_prediction(r)
            if mp is not None:
                preds.append(mp)
            elif r.get("home_team") and r.get("away_team"):
                pending.append(PendingFixture(
                    home_team=r["home_team"], away_team=r["away_team"],
                    league=r["league"], date=r["date"],
                    kickoff_utc=(r.get("kickoff_utc") or None),
                ))
    _attach_jingcai_sp(preds)
    # ⭐ 2026-08-08 —— 待开盘行也挂竞彩 SP,并把「竞彩已经在卖」这件事标出来。
    #
    # 为什么以前不挂:待开盘 = 「等 Pinnacle 开盘」,而开盘后它自然会变成 pred
    # 并在那时拿到 SP ⇒ 挂了也没人用。这个前提对**绝大多数**联赛成立,
    # 但日乙(JPN_J2)证伪了它:两条 Pinnacle 源都不存在,它**永远**等不到,
    # 而竞彩确实在卖 ⇒ 「等着」= 永远看不见一场买得到的比赛。
    #
    # ⚠️ 判据是「**竞彩在不在卖**」,不是「是不是日乙」——
    #    对任何联赛都一样,不给 J2 写特例。今天实测:52 场竞彩在售里
    #    只有日乙 2 场缺 Pinnacle,其余 11 个联赛 0 场。
    # ⚠️ 也**不是**「待开盘里所有场次」:面板待开盘的 10 场日乙来自 AF **赛程**,
    #    竞彩只卖其中 2 场 —— 给 10 场都开手填入口 = 8 张永远算不出 EV 的空卡。
    _attach_jingcai_sp(pending)
    for pf in pending:
        # 与前端 `_isJcBettable` 同口径:胜平负三条齐 **或** 让球三条齐。
        # 单独抽出来是为了两边只有一份定义(前端那份是显示层,这份是数据层)。
        _had = pf.jc_home is not None and pf.jc_draw is not None and pf.jc_away is not None
        _hhad = (pf.jc_hc_home is not None and pf.jc_hc_draw is not None
                 and pf.jc_hc_away is not None)
        if _had or _hhad:
            pf.reason = "jingcai_selling_no_pinnacle"
    return SpCalcResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date_start=today.isoformat(),
        date_end=(today + _dt.timedelta(days=days - 1)).isoformat(),
        days=days,
        fixtures_fetched=len(preds) + len(pending),
        predictions=preds,
        pending_fixtures=pending,
    )


@router.post(
    "/recommend/market-reprice",
    response_model=MarketRepriceResponse,
    summary="V14 — re-price a 市场模式 card from hand-typed live Pinnacle odds",
)
def recommend_market_reprice(req: MarketRepriceRequest) -> MarketRepriceResponse:
    """Pure compute: de-vig the typed 1X2 + reverse-fit the 让球 board (the SAME
    validated path the auto card uses) so the dashboard can swap a LIVE Pinnacle
    line into ONE market-mode card when API-Football's feed is stale. No
    recording, no DB — recording still goes through /recommend/market-handicap."""
    fair = _pinnacle_devig_1x2(req.psc_home, req.psc_draw, req.psc_away)
    if fair is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="missing/invalid Pinnacle 1X2",
        )
    r = {
        "psc_over25": req.psc_over25,
        "psc_under25": req.psc_under25,
        "ou_line": req.ou_line,
        # 🚨 δ 范围闸:`_market_handicap_lines` 读 `r["league"]`。
        # 这个 dict 是**就地字面量**,不是 DB 行 —— 少一个键不会有任何东西喊,
        # 而后果是手填卡的让球带宽 10 倍(2026-08-16 线上实测,截图复现)。
        "league": req.league,
    }
    lines = _market_handicap_lines(fair, r)
    overround = (1.0 / req.psc_home + 1.0 / req.psc_draw + 1.0 / req.psc_away) - 1.0
    # ⭐ 2026-08-08 —— 逐字复用 `_row_to_market_prediction:2569` 的那一行。
    # 手填卡和自动卡的 1X2 下界必须是**同一个函数的同一次调用形态**,不是
    # 「两边各算一份 k·SE」—— 后者正是 WPO 那次 server↔JS 漂移的形状。
    lo_h, lo_d, lo_a = _onex_lo(fair)
    from nutmeg.v4.model.devig import is_impossible_book
    from nutmeg.v4.model.market_handicap import delta_scope
    return MarketRepriceResponse(
        p_home_1x2=float(fair[0]),
        p_draw_1x2=float(fair[1]),
        p_away_1x2=float(fair[2]),
        onex_lo_home=lo_h,
        onex_lo_draw=lo_d,
        onex_lo_away=lo_a,
        handicap_lines=lines,
        overround=float(overround),
        impossible_book=is_impossible_book(req.psc_home, req.psc_draw, req.psc_away),
        # 🚨 和判闸**同源**(都走 `delta_scope`)—— 不许在这里重算一遍口径。
        delta_scope=delta_scope(req.league),
    )


@router.post(
    "/recommend/market-handicap",
    response_model=MarketHandicapResponse,
    summary="V12 W8 — record a 市场模式 让球 pick (market-implied P; J1/cups)",
)
def recommend_market_handicap(req: MarketHandicapRequest) -> MarketHandicapResponse:
    """Recompute the market-implied 让球 P (Dixon-Coles fit to de-vig Pinnacle
    1X2 + O/U 2.5) for the requested line, score each 竞彩 SP, and — when
    record_session + the server DB gate are both on — record the highest-EV leg
    to the observation DB (model_type=market_handicap) so the existing
    settle/ROI pipeline tracks it. NO model is used (OOD for these comps)."""
    fair = _pinnacle_devig_1x2(req.psc_home, req.psc_draw, req.psc_away)
    if fair is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="missing/invalid Pinnacle 1X2",
        )
    from nutmeg.v4.combo.lottery_rules import DEFAULT_MIN_EV_PER_UNIT
    from nutmeg.v4.model.market_handicap import (
        c1_leg_lower_bounds,
        delta_scope,
        devig_over,
        implied_handicap_lines,
    )
    p_over = devig_over(req.psc_over25, req.psc_under25)
    lines = implied_handicap_lines(
        fair[0], fair[1], fair[2], p_over, ou_line=req.ou_line, c1=True,
        league=getattr(req, "league", None),   # 🚨 δ 范围闸:必须传
    )
    row = next((ln for ln in lines if ln[0] == req.handicap_home), None)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"handicap line {req.handicap_home} out of range [-3, 3]",
        )
    _, p_h, p_d, p_a = row
    # 🚨 P0-5(2026-08-07)—— 判闸/选腿/注额一律走 **δ 逐腿下界**,不是点估。
    #
    # 2026-08-06 钱路审查实测:这个端点会记录的 64 注里 **90.6% 被看板自己拒绝**,
    # 22% 选中的是**另一条腿** —— 因为看板(`_spcalcHcRecalc`/`_cupHcRecalc`)判的是
    # `PB.lo[o] * sp - 1 >= 0.05`,而这里判的是点估 `ev > 0`。同一注两套口径,
    # 而这个端点**没有前置判闸**:按钮就在每张市场模式让球卡上,点了直接进台账。
    #
    # ⚠️ 下界**不是概率分布**(三腿和 < 1),按 `c1_leg_lower_bounds` 的契约只许判闸,
    #    不许展示/归一化/喂模型 —— 所以 `p_handicap` 落库和回包仍送点估三元组。
    lo_h, lo_d, lo_a = c1_leg_lower_bounds(
        req.handicap_home, p_h, p_d, p_a, league=getattr(req, "league", None))
    PLO = {"H": lo_h, "D": lo_d, "A": lo_a}
    odds = {"H": req.odds_handicap_H, "D": req.odds_handicap_D, "A": req.odds_handicap_A}
    ev = {
        o: (PLO[o] * odds[o] - 1.0) if (odds[o] and odds[o] > 1.0) else None
        for o in ("H", "D", "A")
    }
    # 选腿也走下界 —— 用点估选、用下界判会选中「点估最高但下界不是最高」的那条,
    # 审查实测 22% 的注就是这么选错的。
    filled = [o for o in ("H", "D", "A") if ev[o] is not None]
    best = max(filled, key=lambda o: ev[o]) if filled else None

    best_stake = None
    recorded = False
    record_failed = False
    session_id = None
    # AUDIT FIX (R1): a leg is a recommendation only when it is genuinely +EV.
    # Under 竞彩's ~31.5% vig the market default is that ALL THREE outcomes are
    # −EV; the old code took the least-negative leg and floored it to the ¥2
    # minimum (Kelly returns 0 for EV ≤ 0), manufacturing a phantom "推荐" with a
    # NEGATIVE expected_return that then polluted the unfiltered ROI / settle /
    # calibration population. No +EV leg → 空仓: stake 0, record nothing. Mirrors
    # the WC-handicap endpoint (test_wc_handicap_recording: "Sub-EV → not recorded").
    # ⛔ 闸从 `> 0` 收紧成 `>= DEFAULT_MIN_EV_PER_UNIT`(0.05)—— 和看板、和项目 DNA
    #    「只投 EV≥+5%」同一个数,而且**引常量不抄字面量**(抄一个 0.05 进来,
    #    以后调闸就会漏掉这一处)。`> 0` 会放行一大批 0~5% 的腿进台账,而看板
    #    从不推荐它们 ⇒ 台账人口 ≠ 决策人口,秋季算 ROI 算的是另一群注。
    if best is not None and ev[best] is not None and ev[best] >= DEFAULT_MIN_EV_PER_UNIT:
        from nutmeg.v4.combo.kelly import fractional_kelly_stake
        k = fractional_kelly_stake(
            hit_probability=PLO[best], ev_per_unit=ev[best],
            bankroll=req.bankroll, kelly_fraction=req.kelly_fraction,
        )
        best_stake = max(float(k.recommended_stake), 2.0)
        db_path = _should_record_session(req.record_session)
        if db_path:
            from nutmeg.v4.observation.recorder import record_market_handicap_session
            try:
                session_id = record_market_handicap_session(
                    db_path,
                    league=req.league, match_date=str(req.date),
                    home_team=req.home_team, away_team=req.away_team,
                    handicap_home=req.handicap_home,
                    p_handicap=(p_h, p_d, p_a),
                    p_1x2=(fair[0], fair[1], fair[2]),
                    pick_outcome=best, pick_odds=float(odds[best]),
                    pick_ev=float(ev[best]),
                    pick_stake=best_stake,
                    pick_expected_return=best_stake * float(ev[best]),
                    bankroll=req.bankroll,
                    psc_1x2=(req.psc_home, req.psc_draw, req.psc_away),
                    request=req.model_dump(mode="json"),
                )
                recorded = True
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception(
                    "record_market_handicap_session failed (db=%s)", db_path,
                )
                # 体检 A3 — surface the failure (≠ gate-off); UI goes red.
                record_failed = True
    elif best is not None:
        # 没过闸的腿仍然回包(best_outcome / best_ev 给上下文),但**不是注**:
        # stake 0、不落库。⚠️ 2026-08-07 起「没过闸」包含 0~5% 这一段,不再只是负 EV。
        best_stake = 0.0

    def _fair(p):
        return (1.0 / p) if p > 0 else 0.0

    try:
        from nutmeg.v4.model.market_handicap import implied_margin_bands
        margin_bands = _mk_margin_bands(implied_margin_bands(
            fair[0], fair[1], fair[2], p_over, ou_line=req.ou_line,
        ))
    except Exception:  # noqa: BLE001
        margin_bands = []

    return MarketHandicapResponse(
        league=req.league, date=req.date,
        home_team=req.home_team, away_team=req.away_team,
        handicap_home=req.handicap_home,
        market_implied_p=[p_h, p_d, p_a],
        # 体检 C1 — expose the WPO 1X2 fair-P so the reverse-calc client stops
        # recomputing it with basic normalization (which faked longshot +EV).
        p_1x2=[float(fair[0]), float(fair[1]), float(fair[2])],
        fair_odds=[_fair(p_h), _fair(p_d), _fair(p_a)],
        ev_per_unit=[ev["H"], ev["D"], ev["A"]],
        best_outcome=best,
        best_ev=(ev[best] if best is not None else None),
        best_stake=best_stake, recorded=recorded, record_failed=record_failed,
        session_id=session_id, margin_bands=margin_bands,
        # 🚨 和 L2834/L2853 判闸时用的是同一个函数 —— 这个端点会**写台账**,
        #    所以「这注的 δ 到底施加了没有」必须能被事后看见,不能只活在进程内计数器里。
        delta_scope=delta_scope(req.league),
    )


def _argmax_prediction_tickets(
    preds: list[SinglePrediction],
) -> list[SingleTicketResponse]:
    """V12 W8k — BUGFIX. Build the 今日推荐 single board as model PREDICTIONS,
    not EV-vs-Pinnacle recommendations.

    The old board fed recommend_singles the Pinnacle-fallback odds (no 竞彩 SP
    at page-load), so its "EV" was actually model_P × Pinnacle_odds − 1 = the
    model's DIVERGENCE from the sharp (noise), and it surfaced the model's
    biggest disagreement with the sharp as the "best pick" (e.g. recommending
    an already-relegated home side at 5.21). That mislabels noise as a bet.

    A prediction board instead shows, per match, the model's single MOST-LIKELY
    1X2 outcome (argmax of model P) + its probability. No bet, no EV. The actual
    bet decision (real EV) happens only when the user types a 竞彩 SP into the
    per-card input. Sorted by model confidence (argmax P) desc.
    """
    from nutmeg.v4.observation.recommendation_version import (
        single_ticket_fingerprint,
    )

    tickets: list[SingleTicketResponse] = []
    for p in preds:
        probs = {"H": p.p_home_1x2, "D": p.p_draw_1x2, "A": p.p_away_1x2}
        outcome = max(probs, key=lambda k: probs[k])
        prob = float(probs[outcome])
        tk = SingleTicketResponse(
            match_id=f"{p.league}_{p.home_team}_vs_{p.away_team}",
            league=p.league, date=str(p.date),
            home_team=p.home_team, away_team=p.away_team,
            market_type="1x2", outcome=outcome,
            odds=float(1.0 / prob) if prob > 0 else 99.0,  # model fair price
            probability=prob,
            ev_per_unit=0.0,           # a prediction is NOT a bet — no EV here
            stake=0.0, raw_kelly_stake=0.0, expected_return=0.0,
            psc_home=p.psc_home, psc_draw=p.psc_draw, psc_away=p.psc_away,
            psc_over25=p.psc_over25, psc_under25=p.psc_under25,
            ou_line=p.ou_line,   # 体检 Wave1 — real total line for the record path
            odds_update=p.odds_update,   # 体检 P1#10 — snapshot age for the card badge
            handicap_lines=p.handicap_lines,   # V14 — market-reverse 让球 board
            delta_scope=p.delta_scope,
            asian_handicap_lines=p.asian_handicap_lines,  # V14 — international AH (half-line)
        )
        tk.selection_fingerprint = single_ticket_fingerprint(tk)
        tickets.append(tk)
    tickets.sort(key=lambda t: -t.probability)
    return tickets


@router.post(
    "/today-recommendations",
    response_model=TodayRecommendationsResponse,
    summary="Unified daily recommendation flow: auto-fetch fixtures + run single + parlay",
)
def today_recommendations(req: TodayRecommendationsRequest) -> TodayRecommendationsResponse:
    """V10 W1 Track A — the user-facing "land on the page" endpoint.

    Reuses existing endpoint functions (`recommend`, `recommend_single`)
    internally; no new ML logic. Server-side fetches fixtures via
    `nutmeg.v4.cli.ingest_odds._gather_rows` (V7 W1).

    Returns None for any included game type that produced 0 recommendations
    or whose pipeline raised — UI renders "no recommendations today" rather
    than throwing a 500.

    V11 P1-FE#4 — pool option is now included by default. Strategy B
    (locked 2026-05-25 in docs/v11_p1_fe_design.md): for each fixture
    that passes the EV gate, pick the max-EV market; then build C(M, N)
    pool of size N=req.pool_n. min_ev gate + risk_preference→Kelly map
    are applied to all three pipelines (single/parlay/pool).
    """
    import datetime as _dt
    from pathlib import Path as _Path

    from nutmeg.v4.cli.ingest_odds import (
        PINNACLE_BOOKMAKER_ID,
        _gather_rows,
        _odds_api_available,
    )

    # V11 P1-FE#4 — risk dial → Kelly fraction. The explicit
    # `kelly_fraction` field acts as an override: when the caller leaves
    # it at the default 0.25 we map from risk_preference; if it's been
    # set to anything else (e.g. via the engineer CLI) we honor that.
    _RISK_TO_KELLY = {
        "conservative": 0.15,
        "balanced": 0.25,
        "aggressive": 0.40,
    }
    if abs(req.kelly_fraction - 0.25) < 1e-9:
        effective_kelly = _RISK_TO_KELLY[req.risk_preference]
    else:
        effective_kelly = req.kelly_fraction

    # Resolve date
    if req.date is None:
        on_date = _utc_today()   # UTC anchor (see _utc_today)
    else:
        try:
            on_date = _dt.date.fromisoformat(req.date)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"date must be ISO YYYY-MM-DD: {exc}",
            )

    # Fetch fixtures (uses API-Football; will use cache if available).
    # V12 W0 (2026-05-28) — auto-filter fixtures that have already kicked
    # off (or are about to in next 5 min). This is what makes the morning
    # + afternoon cron waves produce different optimal sets, AND what
    # keeps the dashboard showing the *current* state (e.g., at 16:00
    # J1 matches are filtered out because they're done).
    try:
        rows, _n_calls, _n_skipped = _gather_rows(
            req.leagues,
            on_date,
            cache_dir=_Path("data/external/api_football"),
            bookmaker_id=PINNACLE_BOOKMAKER_ID,
            refresh_fixtures=False,
            # V12 W3 — 🔄 刷新盘口 sets req.refresh_odds=True to pull live
            # near-kickoff Pinnacle (fixtures stay cached; only odds drift).
            refresh_odds=req.refresh_odds,
            min_kickoff_buffer_minutes=5,
            snapshot_db=_observation_db_path(),
            snapshot_source="today_rec",
            use_odds_api=_odds_api_available(),
            odds_api_refresh=req.refresh_odds,
            # 2026-07-09 — refresh only 竞彩-bettable leagues/fixtures (§quota).
            bettable_refresh_only=req.bettable_only,
            oa_ttl_seconds=_SERVING_OA_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        # API-Football errors (rate limit, network, missing key) → return
        # empty response with clear summary, not 500. Caller sees
        # fixtures_fetched=0 and can show "no data today / API issue".
        import logging
        logging.getLogger(__name__).warning(
            "today-recommendations fixture fetch failed: %s", exc,
        )
        rows = []

    fixtures = _fixture_rows_to_inputs(rows)
    fixtures_fetched = len(fixtures)

    # V12 W3 — per-fixture model output for the 竞彩 SP calculator, via the
    # shared _calc_predictions helper (1X2 P + Pinnacle echo + handicap-line
    # P + playoff→market blend). The 近期赛事 tab uses the SAME helper via
    # /predictions/sp-calc across a 3-day window.
    single_match_predictions = _calc_predictions(get_artifact(), fixtures)

    # V12 W0 (2026-05-27) — flag fixtures in known playoff/barrage windows.
    # Model has no playoff feature; dashboard renders these as ⚠️ banner.
    # See apps/api/src/nutmeg/v4/data/playoff_context.py
    from nutmeg.v4.data.playoff_context import detect_playoff

    playoff_warnings: list[PlayoffWarning] = []
    for f in fixtures:
        w = detect_playoff(f.league, f.date)
        if w is None:
            continue
        # f.date may be a datetime.date (Pydantic-parsed from ISO string);
        # coerce to ISO string for the response model.
        _date_str = f.date.isoformat() if hasattr(f.date, "isoformat") else str(f.date)
        playoff_warnings.append(PlayoffWarning(
            league=f.league,
            home_team=f.home_team,
            away_team=f.away_team,
            date=_date_str,
            context=w.context,
            model_bias_note=w.model_bias_note,
        ))

    single_resp: SingleRecommendResponse | None = None
    parlay_resp: RecommendResponse | None = None
    pool_resp: PoolRecommendResponse | None = None
    total_recs = 0
    total_stake = 0.0
    stake_weighted_ev_sum = 0.0

    if fixtures_fetched > 0 and "single" in req.include:
        try:
            # V12 W8k — BUGFIX: the single board is now the model's PREDICTIONS
            # (argmax per match), NOT the EV-vs-Pinnacle max-pick. At page-load
            # there is no 竞彩 SP, so the old recommend_single fell back to
            # Pinnacle odds and ranked by model-minus-sharp divergence (noise) —
            # surfacing the model's biggest disagreement with the sharp as the
            # "best bet". The real bet decision (EV) happens when the user types
            # a 竞彩 SP into the per-card input.
            _art = get_artifact()
            # fetch-perf D — reuse single_match_predictions computed above on the
            # SAME fixtures + artifact. _calc_predictions runs
            # build_features_for_fixtures (~880ms clubelo/ratings disk load,
            # measured) and was being paid a 2nd time here for identical output.
            _preds = single_match_predictions
            pred_tickets = _argmax_prediction_tickets(_preds)
            if pred_tickets:
                single_resp = SingleRecommendResponse(
                    generated_at_utc=datetime.now(timezone.utc).isoformat(
                        timespec="seconds"),
                    model=_model_info_from_artifact(_art),
                    bankroll=req.bankroll,
                    n_fixtures=len(fixtures),
                    n_recommendations=len(pred_tickets),
                    tickets=pred_tickets,
                    total_stake=0.0,            # predictions, not bets
                    total_expected_return=0.0,
                )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: prediction board failed",
            )
            single_resp = None

    # V12 W8k — parlay/pool boards are SUPPRESSED on 今日推荐: they were the same
    # bug as the single board — auto-generated +EV-vs-Pinnacle combos with no
    # real 竞彩 SP = model-vs-sharp noise sold as bet recommendations. A 串关/复式
    # recommendation needs a real 竞彩 SP per leg, which this predictions view
    # doesn't have.
    #
    # This stays OFF by design — NOT "to be built later". The real-EV 串关 already
    # exists: the 近期赛事 串关篮子 (tick 「串」 across legs → POST /recommend/parlay,
    # which server-recomputes each leg's model P and returns ∏P × ∏SP − 1, gated
    # + Kelly-staked). 今日推荐 stays a pure predictions board and routes users
    # there (see the in-card hint). Re-enabling an auto-parlay here would only
    # reintroduce the noise, since this view carries no entered 竞彩 SP.
    _today_allow_parlay_pool = False
    if _today_allow_parlay_pool and fixtures_fetched >= 2 and "parlay" in req.include:
        try:
            parlay_req = RecommendRequest(
                fixtures=fixtures,
                bankroll=req.bankroll,
                top_n=10,
                k_min=2,
                k_max=min(8, fixtures_fetched),
                min_hit_probability=req.min_hit_probability,
                min_kelly_stake=req.min_kelly_stake,
                kelly_fraction=effective_kelly,
                include_compound=False,
                record_session=req.record_session,
            )
            parlay_resp = recommend(parlay_req)
            # V11 P1-FE#4 — min_ev gate (parlay)
            if parlay_resp.n_recommendations > 0 and req.min_ev > 0:
                kept = [r for r in parlay_resp.recommendations if r.ev_per_unit >= req.min_ev]
                parlay_resp.recommendations = kept
                parlay_resp.n_recommendations = len(kept)
            if parlay_resp.n_recommendations > 0:
                total_recs += parlay_resp.n_recommendations
                # RecommendResponse has no total_stake field — sum per-ticket
                # kelly_recommended_stake (real ¥). (Pre-V12-W5 this assigned a
                # nonexistent attribute → raised → the 串关 board was silently
                # dropped whenever min_ev>0. Now it shows.)
                total_stake += float(sum(
                    r.kelly_recommended_stake for r in parlay_resp.recommendations))
                for r in parlay_resp.recommendations:
                    stake_weighted_ev_sum += r.kelly_recommended_stake * r.ev_per_unit
            else:
                parlay_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: parlay pipeline failed",
            )
            parlay_resp = None

    # V11 P1-FE#4 — pool (Strategy B: auto-pick max-EV market per fixture)
    # V12 W8k — suppressed on 今日推荐 (see _today_allow_parlay_pool note above).
    if _today_allow_parlay_pool and fixtures_fetched >= req.pool_n and "pool" in req.include:
        try:
            pool_resp = _build_today_pool(
                fixtures=fixtures,
                bankroll=req.bankroll,
                kelly_fraction=effective_kelly,
                min_ev=req.min_ev,
                pool_n=req.pool_n,
                record_session=req.record_session,
            )
            if pool_resp is not None and pool_resp.n_selected > 0:
                total_recs += pool_resp.n_selected
                total_stake += pool_resp.total_stake
                for t in pool_resp.tickets:
                    if t.stake > 0:
                        stake_weighted_ev_sum += t.stake * t.ev_per_unit
            else:
                pool_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: pool pipeline failed",
            )
            pool_resp = None

    # V11 post-ship — WC 1X2 informational block.
    # Reuses /predictions/wc internally; surfaces today's WC fixtures so
    # the user doesn't need to switch tabs to see what's on. The user
    # still goes to the 🏆 WC tab to enter handicap SP for actual
    # recommendations (which then post to /recommend/wc/single). WC is
    # purely informational here — doesn't count toward total_recs / stake.
    wc_resp: WcPredictionsResponse | None = None
    if "wc" in req.include:
        try:
            wc_resp = predictions_wc(
                date=on_date.isoformat(),
                fetch_current_odds=False,  # don't burn Odds API quota in today loop
                alpha=0.4,
            )
            if not wc_resp or wc_resp.n_fixtures == 0:
                wc_resp = None
        except HTTPException as exc:
            # 503 when WC training data / eloratings missing — degrade
            # gracefully (today endpoint shouldn't fail because WC infra
            # is incomplete; the rest still works).
            import logging
            logging.getLogger(__name__).info(
                "today-recommendations: WC block unavailable (%s)", exc.detail,
            )
            wc_resp = None
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "today-recommendations: WC block failed",
            )
            wc_resp = None

    weighted_ev = (stake_weighted_ev_sum / total_stake) if total_stake > 0 else None

    # V11 P1-FE#5 — top-level version_hash + optional diff vs prev_version.
    # Combines fingerprints from all three pipelines + the odds digest.
    from nutmeg.v4.observation.recommendation_version import (
        version_hash as _vh,
        fixtures_odds_digest,
    )
    _single_fps  = [t.selection_fingerprint for t in (single_resp.tickets if single_resp else []) if t.selection_fingerprint]
    _parlay_fps  = [r.selection_fingerprint for r in (parlay_resp.recommendations if parlay_resp else []) if r.selection_fingerprint]
    _pool_fps    = [t.selection_fingerprint for t in (pool_resp.tickets if pool_resp else []) if t.selection_fingerprint and t.stake > 0]
    _odds_digest = fixtures_odds_digest(fixtures)
    _top_hash = _vh(
        single_fingerprints=_single_fps,
        parlay_fingerprints=_parlay_fps,
        pool_fingerprints=_pool_fps,
        odds_digest=_odds_digest,
    )

    # If the client sent a prev_version and it differs, surface a diff
    # block. We can't compute added/removed server-side because the
    # client's prior fingerprint set isn't echoed back — the frontend
    # owns the per-rec diff (it has the prior set in localStorage and
    # compares against the new selection_fingerprints inline).
    # Server's role: confirm "yes, version moved" + a one-line summary.
    diff_block: TodayRecommendationsDiff | None = None
    if req.prev_version and req.prev_version != _top_hash:
        cur_set = set(_single_fps + _parlay_fps + _pool_fps)
        diff_block = TodayRecommendationsDiff(
            prev_version=req.prev_version,
            current_version=_top_hash,
            odds_changed=False,  # frontend infers from rec-level fp comparison
            added_fingerprints=sorted(cur_set),
            removed_fingerprints=[],
            summary="推荐已更新",
        )

    return TodayRecommendationsResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date=on_date.isoformat(),
        leagues=req.leagues,
        bankroll=req.bankroll,
        fixtures_fetched=fixtures_fetched,
        single=single_resp,
        parlay=parlay_resp,
        pool=pool_resp,
        wc=wc_resp,
        summary=TodaySummary(
            total_recs=total_recs,
            total_stake=total_stake,
            weighted_ev=weighted_ev,
        ),
        version_hash=_top_hash,
        diff=diff_block,
        playoff_warnings=playoff_warnings,
        single_match_predictions=single_match_predictions,
    )


@router.post("/recommend/jingcai", response_model=TodayRecommendationsResponse)
def recommend_jingcai(req: JingcaiRecommendRequest) -> TodayRecommendationsResponse:
    """V12 W5 — 💴 竞彩盘口推荐: single + parlay + pool over the fixtures the user
    filled with 竞彩 SP (+ 让球) in 近期赛事.

    Same engine + same three pipelines as /today-recommendations (国际盘口,
    odds=Pinnacle), but here each fixture's ``odds_1x2`` / handicap odds (= the
    竞彩 SP) drive the EV, so this is the 竞彩 frame. Model P still uses psc as a
    feature. Kept as its own endpoint (rather than refactoring the auto-fetch
    Pinnacle path) so the working today flow is untouched.
    """
    import datetime as _dt

    art = get_artifact()
    if art is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"V4 model artifact not loaded; expected at {_artifact_path()}",
        )

    _RISK_TO_KELLY = {"conservative": 0.15, "balanced": 0.25, "aggressive": 0.40}
    effective_kelly = (
        _RISK_TO_KELLY[req.risk_preference]
        if abs(req.kelly_fraction - 0.25) < 1e-9 else req.kelly_fraction
    )

    fixtures = req.fixtures
    n = len(fixtures)
    single_match_predictions = _calc_predictions(art, fixtures)

    single_resp: SingleRecommendResponse | None = None
    parlay_resp: RecommendResponse | None = None
    pool_resp: PoolRecommendResponse | None = None
    total_recs = 0
    total_stake = 0.0
    stake_weighted_ev_sum = 0.0

    if n > 0 and "single" in req.include:
        try:
            sr = recommend_single(SingleRecommendRequest(
                fixtures=fixtures, bankroll=req.bankroll,
                kelly_fraction=effective_kelly, record_session=req.record_session,
            ))
            if sr.n_recommendations > 0 and req.min_ev > 0:
                kept = [t for t in sr.tickets if t.ev_per_unit >= req.min_ev]
                sr.tickets = kept
                sr.n_recommendations = len(kept)
                sr.total_stake = float(sum(t.stake for t in kept))
                sr.total_expected_return = float(sum(t.expected_return for t in kept))
            if sr.n_recommendations > 0:
                single_resp = sr
                total_recs += sr.n_recommendations
                total_stake += sr.total_stake
                for t in sr.tickets:
                    stake_weighted_ev_sum += t.stake * t.ev_per_unit
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("jingcai: single pipeline failed")

    if n >= 2 and "parlay" in req.include:
        try:
            pr = recommend(RecommendRequest(
                fixtures=fixtures, bankroll=req.bankroll, top_n=10, k_min=2,
                k_max=min(8, n), min_hit_probability=req.min_hit_probability,
                min_kelly_stake=req.min_kelly_stake, kelly_fraction=effective_kelly,
                include_compound=False, record_session=req.record_session,
            ))
            if pr.n_recommendations > 0 and req.min_ev > 0:
                kept = [r for r in pr.recommendations if r.ev_per_unit >= req.min_ev]
                pr.recommendations = kept
                pr.n_recommendations = len(kept)
            if pr.n_recommendations > 0:
                parlay_resp = pr
                total_recs += pr.n_recommendations
                # RecommendResponse has no total_stake field; sum the per-ticket
                # kelly_recommended_stake (real ¥) for the board total.
                _p_stake = float(sum(r.kelly_recommended_stake for r in pr.recommendations))
                total_stake += _p_stake
                for r in pr.recommendations:
                    stake_weighted_ev_sum += r.kelly_recommended_stake * r.ev_per_unit
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("jingcai: parlay pipeline failed")

    if n >= req.pool_n and "pool" in req.include:
        try:
            po = _build_today_pool(
                fixtures=fixtures, bankroll=req.bankroll,
                kelly_fraction=effective_kelly, min_ev=req.min_ev,
                pool_n=req.pool_n, record_session=req.record_session,
            )
            if po is not None and po.n_selected > 0:
                pool_resp = po
                total_recs += po.n_selected
                total_stake += po.total_stake
                for t in po.tickets:
                    if t.stake > 0:
                        stake_weighted_ev_sum += t.stake * t.ev_per_unit
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("jingcai: pool pipeline failed")

    weighted_ev = (stake_weighted_ev_sum / total_stake) if total_stake > 0 else None
    return TodayRecommendationsResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        date=_utc_today().isoformat(),
        leagues=sorted({f.league for f in fixtures}),
        bankroll=req.bankroll,
        fixtures_fetched=n,
        single=single_resp,
        parlay=parlay_resp,
        pool=pool_resp,
        wc=None,
        summary=TodaySummary(
            total_recs=total_recs, total_stake=total_stake, weighted_ev=weighted_ev,
        ),
        version_hash=None,
        diff=None,
        playoff_warnings=[],
        single_match_predictions=single_match_predictions,
    )


# ---------- helper: today-recommendations pool builder ------------------

# V11 P1-FE#4 Strategy B (locked 2026-05-25):
#   1. Run /recommend/single on all fixtures with top_per_match=1 so each
#      fixture yields its single max-EV pick.
#   2. Filter to ev_per_unit ≥ min_ev. If fewer than pool_n remain, return None.
#   3. Convert each surviving pick → PoolFixturePick (with the pick field
#      derived from market_type + outcome).
#   4. Call recommend_pool_endpoint with N=pool_n. The pool ticket set
#      is fully enumerated (C(M, N)) inside that engine.
_OUTCOME_TO_POOL_PICK: dict[tuple[str, str], str] = {
    ("1x2", "H"):          "1x2_H",
    ("1x2", "D"):          "1x2_D",
    ("1x2", "A"):          "1x2_A",
    ("handicap_1x2", "H"): "hc_H",
    ("handicap_1x2", "D"): "hc_D",
    ("handicap_1x2", "A"): "hc_A",
}


def _build_today_pool(
    *,
    fixtures: list[FixtureOddsInput],
    bankroll: float,
    kelly_fraction: float,
    min_ev: float,
    pool_n: int,
    record_session: bool,
) -> PoolRecommendResponse | None:
    """Run Strategy B and return a PoolRecommendResponse, or None if there
    aren't enough +EV fixtures to form an N-leg pool."""
    if len(fixtures) < pool_n:
        return None

    # 1+2. Get one max-EV pick per fixture (top_per_match=1) then filter
    single_resp = recommend_single(SingleRecommendRequest(
        fixtures=fixtures,
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        top_per_match=1,
        record_session=False,  # don't double-record; today endpoint records its own intent
    ))
    if single_resp.n_recommendations < pool_n:
        return None
    picks = [t for t in single_resp.tickets if t.ev_per_unit >= min_ev]
    if len(picks) < pool_n:
        return None

    # 3. Build PoolFixturePick rows from the surviving picks.
    by_match: dict[str, FixtureOddsInput] = {
        f"{f.league}_{f.home_team}_vs_{f.away_team}": f for f in fixtures
    }
    pool_fixtures: list[PoolFixturePick] = []
    for t in picks:
        f = by_match.get(t.match_id)
        if f is None:
            continue
        pick_str = _OUTCOME_TO_POOL_PICK.get((t.market_type, t.outcome))
        if pick_str is None:
            continue
        pool_fixtures.append(PoolFixturePick(
            **f.model_dump(),
            pick=pick_str,
        ))
    if len(pool_fixtures) < pool_n:
        return None

    # 4. Pool engine — N legs across the M picks
    pool_req = PoolRecommendRequest(
        fixtures=pool_fixtures,
        n=pool_n,
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        record_session=record_session,
    )
    return recommend_pool_endpoint(pool_req)


# ---------- /predictions/wc (V10 W1 Track B Day 5) ----------

@router.get(
    "/predictions/wc",
    response_model=WcPredictionsResponse,
    summary="Daily WC 1X2 predictions (LightGBM + Pinnacle blend per Day 3 verdict)",
)
def predictions_wc(
    date: str | None = None,
    fetch_current_odds: bool = False,
    alpha: float = 0.4,
    season: int | None = None,
) -> WcPredictionsResponse:
    """V10 W1 Track B Day 5 — HTTP wrapper around the `nutmeg-wc-predict`
    CLI logic. Used by the dashboard "🏆 WC 2026" tab.

    Parameters
    ----------
    date : YYYY-MM-DD. Default today (UTC).
    fetch_current_odds : if True, pulls Pinnacle from The Odds API
        (costs ~10 quota per request); if False, model-only output.
    alpha : blend weight LightGBM × Pinnacle (default 0.4 per Day 3
        walk-forward).
    season : WC season year (default derived from date.year).

    Graceful degradation
    --------------------
    - Missing training data → 503
    - No fixtures on date → 200 with predictions=[] and n_fixtures=0
    - API-Football error → 200 with empty predictions (logged)
    - Odds API error → 200, fall back to lightgbm_only
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    if date is None:
        on_date = _utc_today()   # UTC anchor (see _utc_today)
    else:
        try:
            on_date = _dt.date.fromisoformat(date)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"date must be ISO YYYY-MM-DD: {exc}",
            )

    season_resolved = season or on_date.year

    # Local imports (avoid top-level cost in tests / other endpoints)
    try:
        from nutmeg.v4.cli.wc_predict import (
            HOST_COUNTRIES,
            _build_pinnacle_lookup_for_date,
            _pinnacle_lookup_with_aliases,
            _predict_one_fixture,
            _train_combined_model,
        )
        from nutmeg.v4.data.sources.api_football import (
            fetch_fixtures_for_league_season,
        )
        from nutmeg.v4.data.wc_training_frame import load_elo_snapshot
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC prediction module not loadable: {exc}",
        )

    snapshots = sorted(_Path("data/external/eloratings").glob("eloratings_*.parquet"))
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eloratings snapshot found at data/external/eloratings/. "
                   "Run the eloratings scraper first (see v10_w1_day2_*.md).",
        )

    # Training data needed
    try:
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}. "
                   "Run nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022",
        )

    elo = load_elo_snapshot(snapshots[-1])

    try:
        all_fx = fetch_fixtures_for_league_season("WC", season_resolved)
    except Exception as exc:  # noqa: BLE001
        _log.warning("WC fixture fetch failed: %s", exc)
        all_fx = []

    on_iso = on_date.isoformat()
    today_fx = [f for f in all_fx if f.get("fixture", {}).get("date", "").startswith(on_iso)]

    pinnacle_lookup = {}
    if fetch_current_odds and today_fx:
        try:
            pinnacle_lookup = _build_pinnacle_lookup_for_date(on_date)
        except Exception as exc:  # noqa: BLE001
            _log.warning("WC pinnacle fetch failed: %s", exc)

    season_hosts = HOST_COUNTRIES.get(season_resolved, {})
    preds: list[WcMatchPrediction] = []
    for fx in today_fx:
        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        pin = _pinnacle_lookup_with_aliases(home, away, pinnacle_lookup)
        raw = _predict_one_fixture(
            fx, model, elo, season_hosts, pinnacle_h2h=pin, alpha=alpha,
        )
        preds.append(WcMatchPrediction(**raw))

    return WcPredictionsResponse(
        date=on_iso,
        season=season_resolved,
        n_fixtures=len(preds),
        blend_alpha=alpha,
        elo_snapshot=snapshots[-1].name,
        host_country_hint=season_hosts,
        predictions=preds,
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
    )


# ---------- /predictions/wc-upcoming (V12 W0 — 2026-05-28) --------------

@router.get(
    "/predictions/wc-upcoming",
    response_model=WcUpcomingResponse,
    summary="V12 W0 — top-N WC single-leg picks across the next N days, sorted by hit rate",
)
def predictions_wc_upcoming(
    days: int = 5,
    top_n: int = 5,
    fetch_current_odds: bool = True,
    min_ev: float = 0.05,
    bankroll: float = 1000.0,
    kelly_fraction: float = 0.25,
    alpha: float = 0.4,
) -> WcUpcomingResponse:
    """V12 W0 (2026-05-28) — lookahead WC picker.

    User feedback: a single day of WC has 4-6 matches, often not enough
    for combo enumeration. But across a 5-day window we have ~20-30
    matches, plenty of single-leg candidates.

    For each fixture in `[today, today + days - 1]`:
      1. Train/load NationalTeamModel
      2. Predict 1X2 probabilities (Elo + Pinnacle blend if available)
      3. Compute EV per outcome: ``model_P × SP - 1``
      4. Keep outcomes with ``ev_per_unit >= min_ev``
      5. Compute Kelly stake: ``bankroll × kelly_fraction × edge / (SP - 1)``

    Sort all surviving picks by ``hit_probability`` descending,
    return ``top_n``.

    Parameters
    ----------
    days : Look-ahead window in days (1-14, default 5). >=14 raises 422
        — anything longer is pre-tournament wishful thinking.
    top_n : Number of picks to return (1-20, default 5).
    fetch_current_odds : Pull live Pinnacle WC odds from The Odds API
        (~10 quota per request). Default True because EV needs SP.
    min_ev : EV per unit gate (default +5%, same as JINGCAI_DEFAULT).
    bankroll : Budget for Kelly sizing.
    kelly_fraction : Kelly fraction (0.15 / 0.25 / 0.40 standard).
    alpha : Blend weight (default 0.4 per V10 W1 Track B Day 3 verdict).

    Phase 1 scope (this endpoint):
      - 1X2 outcomes only (H / D / A)
      - No handicap (let user use the existing per-match Path A++ form)
      - No parlay / pool (V8 W4 cup ablation NEGATIVE — multi-leg in WC
        compounds errors; user previously locked "WC 单关 only")
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    # Validate
    if not 1 <= days <= 14:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="days must be in [1, 14]",
        )
    if not 1 <= top_n <= 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="top_n must be in [1, 20]",
        )

    today = _utc_today()   # UTC anchor (local date drops the late-night EU slate)
    date_end = today + _dt.timedelta(days=days - 1)

    # Local imports (avoid top-level cost)
    try:
        from nutmeg.v4.cli.wc_predict import (
            HOST_COUNTRIES,
            _build_pinnacle_lookup_for_date,
            _pinnacle_lookup_with_aliases,
            _predict_one_fixture,
            _train_combined_model,
        )
        from nutmeg.v4.data.sources.api_football import (
            fetch_fixtures_for_league_season,
        )
        from nutmeg.v4.data.wc_training_frame import load_elo_snapshot
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC prediction module not loadable: {exc}",
        )

    snapshots = sorted(_Path("data/external/eloratings").glob("eloratings_*.parquet"))
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eloratings snapshot found.",
        )

    # Train model once (covers all fixtures in window)
    try:
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}",
        )

    elo = load_elo_snapshot(snapshots[-1])
    season_resolved = today.year  # assume WC is in current year (2026)
    season_hosts = HOST_COUNTRIES.get(season_resolved, {})

    # Fetch all WC fixtures for the season once, then filter by date
    try:
        all_fx = fetch_fixtures_for_league_season("WC", season_resolved)
    except Exception as exc:  # noqa: BLE001
        _log.warning("WC fixture fetch failed: %s", exc)
        all_fx = []

    # Filter to date window
    window_iso_prefixes = [
        (today + _dt.timedelta(days=i)).isoformat()
        for i in range(days)
    ]
    in_window_fx = [
        f for f in all_fx
        if any(
            f.get("fixture", {}).get("date", "").startswith(p)
            for p in window_iso_prefixes
        )
    ]

    # Build Pinnacle lookup per-day if requested (each day = 1 Odds API call)
    pinnacle_lookups_by_day: dict[str, dict] = {}
    if fetch_current_odds and in_window_fx:
        for i in range(days):
            d = today + _dt.timedelta(days=i)
            try:
                pinnacle_lookups_by_day[d.isoformat()] = (
                    _build_pinnacle_lookup_for_date(d)
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("Pinnacle fetch failed for %s: %s", d, exc)
                pinnacle_lookups_by_day[d.isoformat()] = {}

    # Iterate fixtures, compute single-leg picks
    picks: list[WcUpcomingPick] = []
    for fx in in_window_fx:
        iso_date = fx.get("fixture", {}).get("date", "")
        if not iso_date:
            continue
        day_key = iso_date[:10]
        day_lookup = pinnacle_lookups_by_day.get(day_key, {})

        home = fx["teams"]["home"]["name"]
        away = fx["teams"]["away"]["name"]
        pin = _pinnacle_lookup_with_aliases(home, away, day_lookup) if day_lookup else None

        try:
            raw = _predict_one_fixture(
                fx, model, elo, season_hosts, pinnacle_h2h=pin, alpha=alpha,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("predict failed for fixture %s: %s", fx.get("fixture", {}).get("id"), exc)
            continue

        # Compute days_until_kickoff
        try:
            kickoff_dt = _dt.datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            days_until = (kickoff_dt.date() - today).days
        except Exception:  # noqa: BLE001
            days_until = 0

        # Only score outcomes where Pinnacle SP exists (need SP for EV)
        if not raw.get("has_pinnacle"):
            continue

        # Build picks for each of H / D / A
        for outcome, p_key, sp_key in [
            ("H", "p_home", "psc_home"),
            ("D", "p_draw", "psc_draw"),
            ("A", "p_away", "psc_away"),
        ]:
            p = float(raw[p_key])
            sp = float(raw[sp_key])
            ev = p * sp - 1.0  # ev IS the edge here (p·SP − 1)
            if ev < min_ev:
                continue
            # Kelly fractional stake. The ev>=min_ev gate above already
            # implies ev>0; the sp<=1.0 guard covers degenerate odds.
            if sp <= 1.0 or ev <= 0:
                stake = 0.0
            else:
                kelly_full = ev / (sp - 1.0)
                stake = round(bankroll * kelly_fraction * kelly_full, 2)
            picks.append(WcUpcomingPick(
                fixture_id=raw["fixture_id"],
                kickoff_utc=raw["kickoff_utc"],
                days_until_kickoff=days_until,
                home_team=home,
                away_team=away,
                outcome=outcome,
                hit_probability=p,
                odds=sp,
                ev_per_unit=ev,
                stake=stake,
                source=raw["source"],
            ))

    # Sort by hit_probability descending, take top_n
    picks.sort(key=lambda p: p.hit_probability, reverse=True)
    top_picks = picks[:top_n]

    return WcUpcomingResponse(
        date_start=today.isoformat(),
        date_end=date_end.isoformat(),
        days=days,
        n_fixtures_scanned=len(in_window_fx),
        n_picks_after_ev_gate=len(picks),
        picks=top_picks,
        blend_alpha=alpha,
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
    )


# ---------- /recommend/wc/single (V11 post-ship — Path A++ hybrid) -------
#
# DEPRECATED (V12 W8 — WC unification). Superseded by 市场模式
# (``_market_handicap_lines`` / POST ``/recommend/market-handicap``), which
# fits λ to de-vigged Pinnacle 1X2 + O/U(2.5) and reads the integer let-line
# directly. The walk-forward showdown (4330 EU matches, 24/25, leakage-free)
# measured market-reverse at 0.20452 AH-cover Brier vs the fair model's
# 0.20690 — reverse beats model by 2.4e-3 because it anchors the goal total
# to the O/U line instead of a 2.6 prior + 128-match model blend. Path A++
# also blends TOWARD the 竞彩 SP, which shrinks any real edge. WC/EURO/
# WC_QUAL_UEFA are in ``_CUP_MARKET_COMPETITIONS`` so they already serve
# market-reverse 让球 via 市场模式. The dashboard WC tab (and its
# ``renderWcHandicapSection`` 让球 redirect) was since removed entirely in the
# V14 真-EV-board cleanup. This endpoint is kept only so any cached client
# mid-session keeps working; do not extend it.

@router.post(
    "/recommend/wc/single",
    response_model=WcSingleRecResponse,
    summary="[DEPRECATED V12 W8 → 市场模式] WC integer-handicap (Path A++)",
)
def recommend_wc_single(req: WcSingleRecRequest) -> WcSingleRecResponse:
    """DEPRECATED (V12 W8). Use 市场模式 (``/recommend/market-handicap``) — it
    de-vigs Pinnacle 1X2 + O/U and reads the let-line directly, measured 2.4e-3
    Brier better than this Path A++ blend on a leakage-free walk-forward. Kept
    only for mid-session cached clients; the dashboard no longer calls it.

    V11 post-ship — bridges NationalTeamModel (1X2) to the 竞彩 整数让球
    market via Path A++ hybrid:

      1. NationalTeamModel.predict_proba → 1X2 model probs
      2. Blend with user-provided Pinnacle 1X2 (α = req.blend_alpha)
      3. Reverse-map blended 1X2 → (λ_h, λ_a) under WC mean λ_total prior
      4. DC score grid → model handicap probs (让胜 / 让平 / 让负)
      5. Dewedge user 竞彩 SP → market handicap probs
      6. Bayesian blend model HC + market HC at α = req.blend_alpha
      7. Per-outcome EV + Kelly → ¥2-quantized stake, gated by req.min_ev

    The 1X2 blend and the handicap blend reuse the same α; this is
    intentional — both are model-vs-Pinnacle and the WC convention is 0.4.

    Returns one ``WcSingleRecMatch`` per fixture, each carrying 3 outcomes
    (H/D/A on the let-line) with diagnostics + stake. Outcomes whose EV is
    below ``req.min_ev`` are surfaced with stake=0 (kept for transparency
    on the dashboard).

    Graceful degradation
    --------------------
    - eloratings snapshot missing      → 503
    - WC training data missing         → 503
    - NationalTeamModel fit fails      → 503
    - Per-fixture errors (e.g. unknown team) → matches[].outcomes is empty
      with diagnostic fields zeroed; the rest of the request continues.
    """
    import datetime as _dt
    import logging
    from pathlib import Path as _Path

    _log = logging.getLogger(__name__)

    # Local imports — avoid top-level cost on cold start / non-WC routes.
    try:
        from nutmeg.v4.cli.wc_predict import (
            HOST_COUNTRIES,
            _train_combined_model,
        )
        from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
        from nutmeg.v4.data.wc_training_frame import load_elo_snapshot
        from nutmeg.v4.model.national_team_handicap import (
            DEFAULT_WC_LAMBDA_TOTAL,
            evaluate_handicap_market,
        )
        from nutmeg.v4.model.national_team_predict import (
            bayesian_blend,
            market_implied_probs,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC recommendation module not loadable: {exc}",
        )

    # Lottery rules — for stake quantization + cap.
    from nutmeg.v4.combo.compound_pool import quantize_stake
    from nutmeg.v4.combo.kelly import fractional_kelly_stake
    from nutmeg.v4.combo.lottery_rules import (
        JINGCAI_DEFAULT,
        cap_ticket_stake,
    )

    snapshots = sorted(
        _Path("data/external/eloratings").glob("eloratings_*.parquet")
    )
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No eloratings snapshot found at data/external/eloratings/. "
                   "Run the eloratings scraper first (see v10_w1_day2_*.md).",
        )

    try:
        # Use 2018 hosts as default training-time hint (matches predictions_wc).
        host_hint = HOST_COUNTRIES.get(2018)
        model = _train_combined_model([2018, 2022], host_countries=host_hint)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"WC training data missing: {exc}. "
                   "Run nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022",
        )

    elo = load_elo_snapshot(snapshots[-1])
    rules = JINGCAI_DEFAULT

    # Optional host-country override (e.g. 'USA' for WC 2026).
    user_hosts: dict[str, float] = {}
    if req.host_country:
        user_hosts[req.host_country] = req.host_advantage

    matches: list[WcSingleRecMatch] = []
    total_stake = 0.0
    total_expected_return = 0.0
    n_recs = 0

    for fx in req.fixtures:
        # ----- Per-fixture model 1X2 -----
        h_code = lookup_elo_code(fx.home_team)
        a_code = lookup_elo_code(fx.away_team)
        h_elo = float(elo.get(h_code, {}).get("elo", 1500.0)) if h_code else 1500.0
        a_elo = float(elo.get(a_code, {}).get("elo", 1500.0)) if a_code else 1500.0

        # Per-row host hint: if user named a host, treat fixture's home team
        # as host when its name matches the user_hosts key OR fall back to
        # season-hint convention (use_hosts lookup only if home matches).
        is_host = fx.home_team in user_hosts
        home_adv = user_hosts.get(fx.home_team, 0.0) if is_host else 0.0

        df = pd.DataFrame([{
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "home_elo": h_elo,
            "away_elo": a_elo,
            "psc_home": fx.psc_home,
            "psc_draw": fx.psc_draw,
            "psc_away": fx.psc_away,
        }])

        try:
            lgb_probs = model.predict_proba(
                df,
                host_country=fx.home_team if is_host else None,
                host_advantage=home_adv if is_host else 0.0,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "WC recommend: predict_proba failed for %s vs %s: %s",
                fx.home_team, fx.away_team, exc,
            )
            matches.append(WcSingleRecMatch(
                fixture_id=fx.fixture_id,
                home_team=fx.home_team,
                away_team=fx.away_team,
                kickoff_utc=fx.kickoff_utc,
                handicap_home=fx.handicap_home,
                p_1x2_blended=[0.0, 0.0, 0.0],
                inferred_lambda_home=0.0,
                inferred_lambda_away=0.0,
                outcomes=[],
            ))
            continue

        # ----- Blend with user-provided Pinnacle 1X2 -----
        pin_probs = market_implied_probs(
            pd.Series([fx.psc_home]),
            pd.Series([fx.psc_draw]),
            pd.Series([fx.psc_away]),
        )
        blended_1x2 = bayesian_blend(lgb_probs, pin_probs, alpha=req.blend_alpha)[0]
        p_h, p_d, p_a = float(blended_1x2[0]), float(blended_1x2[1]), float(blended_1x2[2])

        # ----- Path A++ handicap evaluation -----
        try:
            rec = evaluate_handicap_market(
                p_h, p_d, p_a,
                fx.handicap_home,
                fx.odds_handicap_H, fx.odds_handicap_D, fx.odds_handicap_A,
                blend_alpha=req.blend_alpha,
                lambda_total_prior=DEFAULT_WC_LAMBDA_TOTAL,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "WC recommend: handicap evaluation failed for %s vs %s @ HC %+d: %s",
                fx.home_team, fx.away_team, fx.handicap_home, exc,
            )
            matches.append(WcSingleRecMatch(
                fixture_id=fx.fixture_id,
                home_team=fx.home_team,
                away_team=fx.away_team,
                kickoff_utc=fx.kickoff_utc,
                handicap_home=fx.handicap_home,
                p_1x2_blended=[p_h, p_d, p_a],
                inferred_lambda_home=0.0,
                inferred_lambda_away=0.0,
                outcomes=[],
            ))
            continue

        # ----- EV gate + Kelly per outcome -----
        outcomes_out: list[WcRecommendationOutcome] = []
        labels = ("H", "D", "A")
        # Market p_market is NaN-tuple when no SP — surface as None.
        p_market_tuple: tuple[Optional[float], Optional[float], Optional[float]] = (
            None if np.isnan(rec.p_market_hc[0]) else float(rec.p_market_hc[0]),
            None if np.isnan(rec.p_market_hc[1]) else float(rec.p_market_hc[1]),
            None if np.isnan(rec.p_market_hc[2]) else float(rec.p_market_hc[2]),
        )
        for i, label in enumerate(labels):
            p_final_i = float(rec.p_final_hc[i])
            p_model_i = float(rec.p_model_hc[i])
            ev_i = float(rec.ev_per_unit[i])
            odds_i = float(rec.odds_hc[i])
            full_kelly_i = float(rec.kelly_fraction[i])

            if ev_i < req.min_ev:
                # Below EV gate — surface diagnostics, no stake.
                stake_i = 0.0
                er_i = 0.0
            else:
                kr = fractional_kelly_stake(
                    hit_probability=p_final_i,
                    ev_per_unit=ev_i,
                    bankroll=req.bankroll,
                    kelly_fraction=req.kelly_fraction,
                    max_stake_fraction=req.max_stake_fraction,
                )
                capped = cap_ticket_stake(kr.recommended_stake, rules)
                stake_i = float(quantize_stake(capped, rules.stake_unit))
                er_i = stake_i * ev_i

            if stake_i > 0:
                n_recs += 1
                total_stake += stake_i
                total_expected_return += er_i

            outcomes_out.append(WcRecommendationOutcome(
                outcome=label,
                p_final=p_final_i,
                p_model=p_model_i,
                p_market=p_market_tuple[i],
                odds=odds_i,
                ev_per_unit=ev_i,
                kelly_fraction=full_kelly_i,
                stake=stake_i,
                expected_return=er_i,
            ))

        matches.append(WcSingleRecMatch(
            fixture_id=fx.fixture_id,
            home_team=fx.home_team,
            away_team=fx.away_team,
            kickoff_utc=fx.kickoff_utc,
            handicap_home=fx.handicap_home,
            p_1x2_blended=[p_h, p_d, p_a],
            inferred_lambda_home=float(rec.inferred_lambda_home),
            inferred_lambda_away=float(rec.inferred_lambda_away),
            outcomes=outcomes_out,
        ))

    response = WcSingleRecResponse(
        generated_at_utc=_dt.datetime.now(_dt.UTC).isoformat(),
        bankroll=req.bankroll,
        n_fixtures=len(req.fixtures),
        n_recommendations=n_recs,
        matches=matches,
        total_stake=total_stake,
        total_expected_return=total_expected_return,
        blend_alpha=req.blend_alpha,
        lambda_total_prior=DEFAULT_WC_LAMBDA_TOTAL,
    )

    # V11 post-ship — A/B observation hook. Both gates required:
    # server env NUTMEG_V4_OBSERVATION_DB set + request record_session=True.
    # Only fixtures with at least one stake>0 outcome land in the DB.
    db_path = _should_record_session(req.record_session)
    if db_path and n_recs > 0:
        from nutmeg.v4.observation.recorder import record_wc_handicap_session
        try:
            record_wc_handicap_session(
                db_path,
                request=req.model_dump(mode="json"),
                response=response.model_dump(mode="json"),
            )
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "record_wc_handicap_session failed (db=%s); rec returned anyway",
                db_path,
            )
    return response
