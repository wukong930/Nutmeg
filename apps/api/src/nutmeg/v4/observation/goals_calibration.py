"""总进球校准层 —— Layer A 的镜像,作用在**进球分布**而不是 1X2(2026-09-22)。

## 为什么需要它(实测,不是推测)

模型是两个 CatBoost **Poisson** 回归器,直接对 `home_goals`/`away_goals` 训练,
所以 λ 是真正的期望进球、进球分布是一等输出。但**从来没人给它装过修正**:
`fit_temperature_1x2` 只作用在 1X2 / 让球上,不碰比分网格。

2026-09-22 在 790 场(`model_type='catboost'` ∩ 有赛果)上实测:

    E[总进球]  模型 2.731  ·  实际 2.932   ⇒ 每场低约 0.2 球
    大 2.5     预测 0.510  ·  实际 0.576   z=+3.74
    大 3.5     预测 0.293  ·  实际 0.361   z=+3.97
    0–2 球区间 预测 0.490  ·  实际 0.424   z=-3.74

两道稳健性检查都过:① **rho 无关** —— DC 的 τ 只改总进球 ≤2 的四格,
所以 2.5 及以上的线在数学上完全不受 rho 影响(实测四个 rho 值给出同一个数);
② 不是混世代的假象 —— 09-15 换过 artifact,切开看两边同向同幅。

## ⛔ 预注册(2026-09-22 写定,**在拟合任何系数之前**)

1. **参数**:单一乘性标量 `c`,同时作用于 λ_home 与 λ_away,搜索区间 [0.80, 1.30]。
   ⛔ **只用于总进球**。1X2 / 让球那条路一个字不动 —— 它上面已经压着一个拟合好的
      温度 T,改 λ 或 rho 等于**改掉别人的输入**,那条 T 立刻失配。
2. **目标函数**:总进球分桶 {0,1,…,7+} 上的多分类 log-loss。
   (8 档不是随便挑的 —— 它正是竞彩 ttg 盘的分桶。)
3. **人口**:`model_type IN ('catboost','lightgbm')` 且 λ 非空 且有赛果。
   ⛔ **不用 `lambda_home > 0` 这个代理** —— 它已被实际证伪:库里有 `user_directional_combo`
      的手填行带着正的 λ(1.31 / 1.89,两位小数是指纹)。
4. **窗口**:`created_at >= CURRENT_ARTIFACT_ERA_START`(照抄 Layer A)。
   ⭐ 理由:**校准一个模型的输出必须用那个模型的数据**,混世代 = 校准两个模型的平均。
   训练/holdout 按时间切,holdout 取最后 `DEFAULT_HOLDOUT_WEEKS` 周。
5. **接受条件**(两条都要):holdout log-loss 改善 ≥ `DEFAULT_MIN_LOG_LOSS_GAIN`
   **且** bootstrap p < `DEFAULT_MAX_P_VALUE`。样本不足(训练 < `DEFAULT_MIN_SAMPLES`)
   一律 `insufficient`,**不放宽窗口**。
6. **失败处方 = 回到 c = 1.0**(恒等),不做部分部署。
7. **回滚触发器 = holdout 校准质量退化**,⛔ **不是 ROI**。
   ⭐ 这一条和 Layer A **故意不同**:进球分布不用于下注决策,拿 ROI 判它是**拿错尺子**。

⚠️ 一条**看了数据之后**才成立、因此**不拿来当理由**的观察:那个偏差在 09-15 前后
   两个世代里同向同幅,这是「或许可以跨世代拟合」的线索。**记成待验假设**,
   不作为放宽第 4 条的依据 —— 否则就是后验自由度。

## ⚠️ 今天(2026-09-22)的现实

当前世代只有 **130 场**、全挤在 09-16→09-20 五天内 ⇒ 按第 4 条切,训练集是 **0**。
所以本模块今天会诚实地返回 `insufficient`,和 Layer A 09-20 那条 journal 一样。
**机制先在,数据到了自己生效。**
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from nutmeg.v4.model.dixon_coles import score_grid

#: 分桶数:0,1,…,6,7+ —— 与竞彩 ttg 盘一致
N_BUCKETS = 8

DEFAULT_C_LOWER = 0.80
DEFAULT_C_UPPER = 1.30
DEFAULT_MIN_LOG_LOSS_GAIN = 0.002    # 8 类 log-loss 绝对值比 3 类大,阈值相应提高
DEFAULT_MAX_P_VALUE = 0.10
DEFAULT_HOLDOUT_WEEKS = 2
DEFAULT_MIN_SAMPLES = 30
DEFAULT_BOOTSTRAP_N = 1000
DEFAULT_ROLLBACK_LOG_LOSS_THRESHOLD = 0.004


@dataclass(frozen=True)
class GoalsPair:
    """一场已结算比赛:模型的 (λh, λa) + 真实总进球。"""
    match_date: str
    league: str
    home_team: str
    away_team: str
    lambda_home: float
    lambda_away: float
    total_goals: int


@dataclass(frozen=True)
class GoalsProposal:
    """一次提案的完整记录 —— 每个字段都进 journal,别只记结论。"""
    decision: str                 # 'deploy' | 'hold' | 'insufficient'
    reason: str
    current_c: float
    proposed_c: float
    n_train: int
    n_holdout: int
    log_loss_before: float | None
    log_loss_after: float | None
    log_loss_delta: float | None   # >0 = 改善
    p_value: float | None
    train_start: str = ""
    train_end: str = ""
    holdout_start: str = ""
    holdout_end: str = ""


def total_goals_pmf(lambda_home: float, lambda_away: float, *,
                    c: float = 1.0, rho: float = -0.10,
                    n_buckets: int = N_BUCKETS) -> np.ndarray:
    """总进球分桶概率 {0,1,…,n-2,(n-1)+}。

    ⚠️ 最后一桶是**开口的**(7+),所以 pmf 必然和为 1 —— 这条由测试钉住,
       因为「尾巴被截掉」是个会静默让 log-loss 变好看的坑。
    """
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("lambdas must be positive")
    g = score_grid(lambda_home * c, lambda_away * c, rho=rho)
    n = g.shape[0]
    out = np.zeros(n_buckets, dtype=float)
    for i in range(n):
        for j in range(n):
            out[min(i + j, n_buckets - 1)] += g[i, j]
    s = out.sum()
    return out / s if s > 0 else out


def log_loss_totals(pairs: Sequence[GoalsPair], c: float, *,
                    rho: float = -0.10, eps: float = 1e-9) -> float:
    """分桶 log-loss(越小越好)。"""
    if not pairs:
        return float("nan")
    tot = 0.0
    for p in pairs:
        pmf = total_goals_pmf(p.lambda_home, p.lambda_away, c=c, rho=rho)
        k = min(int(p.total_goals), N_BUCKETS - 1)
        tot -= math.log(max(float(pmf[k]), eps))
    return tot / len(pairs)


def fit_goals_scale(pairs: Sequence[GoalsPair], *,
                    lower: float = DEFAULT_C_LOWER,
                    upper: float = DEFAULT_C_UPPER,
                    rho: float = -0.10) -> float:
    """一维搜索最优 c。区间固定(见预注册第 1 条),⛔ 不按结果调区间。"""
    from scipy.optimize import minimize_scalar
    if not pairs:
        return 1.0
    r = minimize_scalar(lambda c: log_loss_totals(pairs, float(c), rho=rho),
                        bounds=(lower, upper), method="bounded")
    return float(r.x)


def bootstrap_p_value(pairs: Sequence[GoalsPair], c_new: float, *,
                      c_old: float = 1.0, n: int = DEFAULT_BOOTSTRAP_N,
                      rho: float = -0.10, seed: int = 42) -> float:
    """H0:新 c 不比旧 c 好。重采样 holdout,数「没改善」的比例。"""
    if not pairs:
        return 1.0
    rng = np.random.default_rng(seed)
    idx = np.arange(len(pairs))
    worse = 0
    for _ in range(n):
        s = [pairs[i] for i in rng.choice(idx, size=len(idx), replace=True)]
        if log_loss_totals(s, c_new, rho=rho) >= log_loss_totals(s, c_old, rho=rho):
            worse += 1
    return worse / n


def load_goals_pairs(db_path: str | Path, *, era_start: str | None = None) -> list[GoalsPair]:
    """按预注册第 3/4 条取人口。

    ⛔ 允许清单(不是排除清单):未来出现新的非模型 `model_type` 会 **fail SAFE**
       (被丢掉)而不是污染校准 —— 照抄 Layer A 那条注释的理由。
    """
    if era_start is None:
        from nutmeg.v4.observation.prediction_log import CURRENT_ARTIFACT_ERA_START
        era_start = CURRENT_ARTIFACT_ERA_START
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT s.match_date, s.league, s.home_team, s.away_team,
                   s.lambda_home, s.lambda_away, o.home_goals, o.away_goals
            FROM single_predictions s
            JOIN recommendation_sessions r ON r.session_id = s.session_id
            JOIN match_outcomes o
              ON o.match_date = s.match_date AND o.league = s.league
             AND o.home_team = s.home_team AND o.away_team = s.away_team
            WHERE r.created_at >= ?
              -- ⛔ 故意**不**带 Layer A 那条 `model_type IS NULL OR ...`:
              -- 它在 Layer A 里有据(NULL = pre-P1#17 的老 session),但本模块
              -- 只看 2026-09-15 之后的世代,**实测全库 0 行 NULL model_type**
              -- ⇒ 那个分支对这里是死代码,却是个 fail-OPEN 的口子。
              AND r.model_type IN ('catboost', 'lightgbm')
              AND s.lambda_home IS NOT NULL AND s.lambda_away IS NOT NULL
              AND s.lambda_home > 0 AND s.lambda_away > 0
              AND o.home_goals IS NOT NULL AND o.away_goals IS NOT NULL
            ORDER BY s.match_date ASC
            """,
            (era_start,),
        )
        return [
            GoalsPair(r["match_date"], r["league"], r["home_team"], r["away_team"],
                      float(r["lambda_home"]), float(r["lambda_away"]),
                      int(r["home_goals"]) + int(r["away_goals"]))
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def split_train_holdout(pairs: Sequence[GoalsPair], *,
                        holdout_weeks: int = DEFAULT_HOLDOUT_WEEKS,
                        ) -> tuple[list[GoalsPair], list[GoalsPair]]:
    """按**时间**切,不是随机切 —— 随机切会让同一比赛日横跨两边。"""
    import datetime as dt
    if not pairs:
        return [], []
    last = max(dt.date.fromisoformat(p.match_date) for p in pairs)
    cut = (last - dt.timedelta(weeks=holdout_weeks)).isoformat()
    return ([p for p in pairs if p.match_date < cut],
            [p for p in pairs if p.match_date >= cut])


def propose_goals_correction(db_path: str | Path, *, current_c: float = 1.0,
                             holdout_weeks: int = DEFAULT_HOLDOUT_WEEKS,
                             min_samples: int = DEFAULT_MIN_SAMPLES,
                             min_gain: float = DEFAULT_MIN_LOG_LOSS_GAIN,
                             max_p: float = DEFAULT_MAX_P_VALUE,
                             rho: float = -0.10) -> GoalsProposal:
    """走完预注册的全流程,返回一条可直接进 journal 的记录。"""
    pairs = load_goals_pairs(db_path)
    train, hold = split_train_holdout(pairs, holdout_weeks=holdout_weeks)
    span = lambda ps: (ps[0].match_date, ps[-1].match_date) if ps else ("", "")
    tr_s, tr_e = span(train)
    ho_s, ho_e = span(hold)
    if len(train) < min_samples:
        return GoalsProposal(
            "insufficient",
            f"训练集 {len(train)} 场 < 下限 {min_samples};holdout {len(hold)} 场。"
            f"⛔ 按预注册第 5 条**不放宽窗口** —— 等当前 artifact 世代攒够数据。",
            current_c, current_c, len(train), len(hold),
            None, None, None, None, tr_s, tr_e, ho_s, ho_e)
    c_new = fit_goals_scale(train, rho=rho)
    ll_before = log_loss_totals(hold, current_c, rho=rho)
    ll_after = log_loss_totals(hold, c_new, rho=rho)
    gain = ll_before - ll_after
    p = bootstrap_p_value(hold, c_new, c_old=current_c, rho=rho)
    if gain < min_gain:
        d, why = "hold", f"holdout 改善 {gain:+.4f} < 阈值 {min_gain};c_new={c_new:.4f} 不部署"
    elif p >= max_p:
        d, why = "hold", f"bootstrap p={p:.3f} ≥ {max_p};c_new={c_new:.4f} 不部署"
    else:
        d, why = "deploy", f"holdout 改善 {gain:+.4f} · p={p:.3f} ⇒ 部署 c={c_new:.4f}"
    return GoalsProposal(d, why, current_c, c_new, len(train), len(hold),
                         ll_before, ll_after, gain, p, tr_s, tr_e, ho_s, ho_e)


# ── 卡片展示层 ────────────────────────────────────────────────────────────
#: 区间边界(闭区间,含端点)。0-1 / 2-3 / 4+
#: ⭐ 为什么是这三档而不是 owner 举例的 0-2 / 3-5:2026-09-22 在 793 场真 λ 上实测,
#:    0-2/3-5/6+ 的第三档只有 6.3% 的质量(等于一档废掉),而 0-1/2-3/4+ 是 24/47/29。
GOALS_BANDS: tuple[tuple[int, int], ...] = ((0, 1), (2, 3), (4, 99))
GOALS_BAND_LABELS: tuple[str, ...] = ("0-1 球", "2-3 球", "4+ 球")
#: 大球线 1.5 / 2.5 / 3.5 ⇒ 总进球 ≥ 2 / 3 / 4
GOALS_OVER_LINES: tuple[float, ...] = (1.5, 2.5, 3.5)


def goals_view(grid, *, lambda_home: float, lambda_away: float,
               rho: float, c: float = 1.0) -> dict | None:
    """把模型**已经算好的**比分网格变成卡片要的几个数。

    ⭐ 传 `grid` 而不是自己重算,是为了躲开
       [[reusing-the-function-is-not-reusing-the-calibration]]:`score_grid` 的默认
       rho 是 **0.0**,生产口径是 `art.metadata['gbm_rho']`。复用调用方手里那张网格
       ⇒ rho / max_goals / 归一化三样全都不可能和模型分家。
       只有 c ≠ 1 时才必须重算(因为 c 缩放的是 λ 本身)。

    ⚠️ 返回 None = 这场没有模型 λ(市场模式 / 手填)⇒ **前端什么都别画**。
       编一个出来比不画坏得多。
    """
    import numpy as _np
    if not (lambda_home > 0 and lambda_away > 0):
        return None
    g = _np.asarray(grid if c == 1.0 else
                    score_grid(lambda_home * c, lambda_away * c, rho=rho))
    n = g.shape[0]
    tot = _np.zeros(2 * n - 1)
    for i in range(n):
        for j in range(n):
            tot[i + j] += g[i, j]
    s = float(tot.sum())
    if s <= 0:
        return None
    tot /= s
    bands = [float(tot[lo:hi + 1].sum()) for lo, hi in GOALS_BANDS]
    order = sorted(bands, reverse=True)
    return {
        "goals_bands": [round(b, 4) for b in bands],
        "goals_over": [round(float(tot[int(x + 0.5):].sum()), 4) for x in GOALS_OVER_LINES],
        "goals_gap": round(order[0] - order[1], 4),
        "goals_c": c,
    }


def active_c() -> float:
    """当前生效的校准系数。没有部署文件 ⇒ 1.0(恒等,即「未校准」)。

    ⭐ 照 Layer A 的 `live_T_correction.json` 那套:按 mtime 缓存,改文件不用重启。
    """
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[4] / "data" / "live_goals_correction.json"
    try:
        st = p.stat()
    except OSError:
        return 1.0
    cached = getattr(active_c, "_cache", None)
    if cached and cached[0] == st.st_mtime_ns:
        return cached[1]
    try:
        c = float(json.loads(p.read_text())["c"])
    except Exception:
        return 1.0
    if not (DEFAULT_C_LOWER <= c <= DEFAULT_C_UPPER):
        return 1.0          # ⛔ 区间外一律当没有,别让一个坏文件改掉盘面
    active_c._cache = (st.st_mtime_ns, c)
    return c
