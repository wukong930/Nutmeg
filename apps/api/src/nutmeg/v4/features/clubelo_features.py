"""Clubelo ELO features — independent cross-country ELO from clubelo.com.

V5 W4 addition. V4 already has a per-league internal ELO; clubelo provides a
SECOND, cross-country ELO computed with a different K-factor and methodology.
Blending the two (as separate columns) gives the GBM two views of team
strength that are correlated but not identical, especially for teams that
recently changed leagues / European positions.

Source: per-team parquet files written by
``nutmeg.v4.data.sources.clubelo.ingest_teams`` under data/external/clubelo/.
Each parquet has columns (team_canonical, clubelo_slug, country, elo,
from_date, to_date) — one row per ELO change interval since 1946.

Features (per match):
  clubelo_home / clubelo_away      — ELO on match date (or NaN if not tracked)
  clubelo_diff                     — clubelo_home − clubelo_away
  clubelo_p_home                   — sigmoid((diff + home_advantage) / scale),
                                     a clubelo-derived 1X2-style home win prob
  clubelo_available                — 1 if both teams have ELO that date, else 0

Missing handling: if a team is not in clubelo (e.g., J1 teams, lower-division
that fell out of clubelo's tracked level), both clubelo_home and clubelo_away
land as NaN. The GBM gets the ``clubelo_available`` flag and can route to
market+internal-elo features for those rows.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd


log = logging.getLogger(__name__)

# Sensible defaults for the sigmoid-based win-probability proxy.
# Home advantage in clubelo terms (~70 elo points is typical for home matches).
CLUBELO_HOME_ADVANTAGE = 70.0
# Scale constant: 400 in the standard ELO formula P = 1 / (1 + 10^(−Δ/400))
CLUBELO_SCALE = 400.0
# Placeholder ELO when clubelo doesn't track a team. The GBM also gets the
# ``clubelo_available`` flag and can learn to discount these placeholder
# rows; using a value (instead of NaN) lets rows survive the GBM dropna.
CLUBELO_PLACEHOLDER = 1500.0


CLUBELO_FEATURE_COLUMNS = [
    "clubelo_home",
    "clubelo_away",
    "clubelo_diff",
    "clubelo_p_home",
    "clubelo_available",
]


def load_clubelo_history(
    cache_dir: Path | str = Path("data/external/clubelo"),
) -> pd.DataFrame:
    """Load every cached clubelo team-history parquet into one long DataFrame.

    Empty/non-existent caches are silently skipped. Returns an empty frame with
    the right columns if no caches exist.
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        log.warning("clubelo cache dir %s does not exist", cache_dir)
        return _empty_history()
    frames: list[pd.DataFrame] = []
    for p in sorted(cache_dir.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping unreadable parquet %s: %s", p, exc)
            continue
        if not df.empty:
            frames.append(df)
    if not frames:
        return _empty_history()
    return pd.concat(frames, ignore_index=True)


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_canonical": pd.Series(dtype="object"),
            "clubelo_slug": pd.Series(dtype="object"),
            "country": pd.Series(dtype="object"),
            "elo": pd.Series(dtype="float64"),
            "from_date": pd.Series(dtype="object"),
            "to_date": pd.Series(dtype="object"),
        }
    )


def _cache_stamp(cache_dir: Path) -> tuple:
    """clubelo 缓存目录的指纹 —— **每个文件**的 (名字, mtime_ns, 大小) 的哈希。

    ⛔ 第一版我写的是 `(文件数, max(mtime), 总字节)`,**被自己的失效测试当场证伪**:
    把最旧的 `Arsenal.parquet`(7-27)mtime 往前拨 1 秒,它仍远低于 max(8-3)
    ⇒ 指纹不变 ⇒ 吃了陈旧缓存。真实 cron 写入把 mtime 设成「现在」所以能被发现,
    但**原地改一个旧文件**会漏 —— 而「回填/修一支队的历史」正是会那样做的操作。
    ⭐ 教训同族:**用聚合量当指纹,就会漏掉不改变聚合量的那类变化。**

    现在逐文件取哈希:新增/删除/改名/改内容/改 mtime 全盖得住,
    成本仍是同一次 `stat` 遍历(369 个文件 ≈ 1ms,相对 1.5s 的重建可忽略)。

    ⚠️ 判据必须是**目录状态**,不是「进程启动时读一次」:clubelo 是周更/月更的 cron,
    抓完之后面板必须当场认新数据,不能等重启(本仓「daemon 不热载」踩过的坑)。
    """
    try:
        items = sorted(
            (p.name, p.stat().st_mtime_ns, p.stat().st_size)
            for p in cache_dir.glob("*.parquet")
        )
    except OSError:
        return ()
    return (len(items), hash(tuple(items)))


#: 进程内缓存 —— `{cache_dir: (stamp, history_df, lookup)}`。
#:
#: 动机(2026-08-09 实测):`_build_team_lookup` 要跑 **618 万次** Arrow 逐元素迭代
#: (102.8 万行 / 316 队),单次 **1.20s**;`load_clubelo_history` 再读 369 个 parquet
#: 花 0.31s。而这两步**每次请求都从头做一遍**,`/predictions/sp-calc` 对窗口里
#: **每个有比赛的日子**各做一次 ⇒ 3 天窗口最多 4.5s,占该端点总耗时的 76%。
#:
#: ⭐ 为什么以前没人发现:夏休期 13 个训练联赛**一场比赛都没有**
#: (实测 7 月初/7 月下的 3 天窗口都是 `[0,0,0]`)⇒ 这条路径根本不执行,端点秒回。
#: 8 月欧洲联赛复赛(今天窗口 32+2 场)才把它叫醒 ——
#: **「变慢」是季节性的,慢的东西一直在那。**
#:
#: 线程安全:两个线程并发未命中时会各建一次(浪费,不出错),最后一个赋值胜出。
#: 故意不加锁 —— 锁的失败模式(构建抛异常时死锁)比多建一次贵。
_LOOKUP_CACHE: dict[str, tuple] = {}


def load_clubelo_history_cached(
    cache_dir: Path | str = Path("data/external/clubelo"),
) -> tuple[pd.DataFrame, dict[str, list[tuple]]]:
    """`(history, lookup)`,按目录指纹缓存。指纹变了就重建。

    ⛔ 返回的 `history` / `lookup` 是**共享对象**,调用方不许原地改
    (现有唯一消费者 `build_clubelo_features` 只读它们)。
    """
    cache_dir = Path(cache_dir)
    key = str(cache_dir.resolve())
    stamp = _cache_stamp(cache_dir)
    hit = _LOOKUP_CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1], hit[2]
    history = load_clubelo_history(cache_dir)
    lookup = _build_team_lookup(history)
    _LOOKUP_CACHE[key] = (stamp, history, lookup)
    return history, lookup


def _build_team_lookup(history: pd.DataFrame) -> dict[str, list[tuple]]:
    """Group history by team_canonical → list of (from_date, to_date, elo) sorted.

    This is much faster than a pandas mask per row when we're looking up ~25k
    matches × 2 teams.
    """
    lookup: dict[str, list[tuple]] = {}
    if history.empty:
        return lookup
    for team, group in history.groupby("team_canonical"):
        rows = [
            (r.from_date, r.to_date, float(r.elo))
            for r in group.itertuples(index=False)
        ]
        rows.sort(key=lambda x: x[0])
        lookup[str(team)] = rows
    return lookup


def _elo_for(lookup: dict[str, list[tuple]], team: str, match_date) -> float:
    """Linear scan over the team's intervals; returns NaN if no interval covers the date.

    Acceptable performance because each team has ~1k intervals (since 1946)
    and we early-return on first hit.
    """
    if team not in lookup or pd.isna(match_date):
        return float("nan")
    # match_date is a pandas Timestamp; clubelo from/to are datetime.date
    if isinstance(match_date, pd.Timestamp):
        match_date = match_date.date()
    for from_d, to_d, elo in lookup[team]:
        if from_d <= match_date <= to_d:
            return elo
    return float("nan")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def build_clubelo_features(
    df: pd.DataFrame,
    *,
    cache_dir: Path | str = Path("data/external/clubelo"),
    history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Augment df with clubelo features (5 columns).

    Pass ``history`` to avoid re-loading from disk in tests; otherwise loads
    from ``cache_dir``.
    """
    out = df.copy()

    # ⭐ 2026-08-09 —— 走缓存那条路。显式传 `history` 的调用方(测试)行为**不变**:
    # 它们本来就自带数据、不碰磁盘,给它们套缓存只会让测试之间互相污染。
    if history is None:
        history, lookup = load_clubelo_history_cached(cache_dir)
    else:
        lookup = _build_team_lookup(history)

    home_elo = np.full(len(out), np.nan)
    away_elo = np.full(len(out), np.nan)
    for i, row in enumerate(out.itertuples(index=False)):
        home_elo[i] = _elo_for(lookup, row.home_team, row.date)
        away_elo[i] = _elo_for(lookup, row.away_team, row.date)

    # available flag based on raw ELO values BEFORE we fill placeholders
    available = (
        pd.Series(home_elo).notna() & pd.Series(away_elo).notna()
    ).astype(int).values

    # Fill missing with placeholder so rows survive GBM dropna. The flag tells
    # the model when these are real vs imputed.
    home_filled = np.where(np.isnan(home_elo), CLUBELO_PLACEHOLDER, home_elo)
    away_filled = np.where(np.isnan(away_elo), CLUBELO_PLACEHOLDER, away_elo)

    out["clubelo_home"] = home_filled
    out["clubelo_away"] = away_filled
    out["clubelo_diff"] = home_filled - away_filled

    diff_with_ha = (out["clubelo_diff"] + CLUBELO_HOME_ADVANTAGE) / CLUBELO_SCALE
    # 10^x / (1 + 10^x) — standard ELO win-prob formula
    out["clubelo_p_home"] = 1.0 / (1.0 + np.power(10.0, -diff_with_ha))

    out["clubelo_available"] = available

    return out
