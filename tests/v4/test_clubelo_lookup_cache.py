"""clubelo team-lookup 的进程内缓存(2026-08-09)。

## 为什么加它

`/predictions/sp-calc` 实测 3.0s,其中 **76%(4.04s/5.34s)** 花在
`_build_team_lookup` —— 102.8 万行 / 316 队 ⇒ **618 万次** Arrow 逐元素迭代,
单次 1.20s;`load_clubelo_history` 再读 369 个 parquet 花 0.31s。
而这两步**每次请求都从头做一遍**,且 sp-calc 对窗口里**每个有比赛的日子**各做一次。

⭐ 为什么以前没人发现:夏休期 13 个训练联赛一场比赛都没有(实测 7 月初 / 7 月下的
3 天窗口都是 `[0,0,0]`)⇒ 这条路径**根本不执行**。8 月欧洲联赛复赛(窗口 32+2 场)
才把它叫醒。**「变慢」是季节性的,慢的东西一直在那** —— 不是退化,也不是竞彩那条链。

## 这些测试守什么

① **纯性能**:缓存前后特征逐位相同(上线时用 6 行 × 5 列真数据比过,0 个不一致)
② **失效判据必须逐文件**,不能用聚合量 —— 见 `test_stale_cache_is_not_served`
③ 显式传 `history=` 的调用方(全部既有测试)行为不变,不被缓存污染
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from nutmeg.v4.features.clubelo_features import (
    _LOOKUP_CACHE,
    _cache_stamp,
    build_clubelo_features,
    load_clubelo_history_cached,
)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """两个队各一个 parquet —— 真文件,因为指纹判据读的就是文件系统。"""
    for team, elo in (("Alpha", 1600.0), ("Beta", 1400.0)):
        pd.DataFrame({
            "team_canonical": [team], "clubelo_slug": [team.lower()],
            "country": ["XX"], "elo": [elo],
            "from_date": [pd.Timestamp("2026-01-01").date()],
            "to_date": [pd.Timestamp("2026-12-31").date()],
        }).to_parquet(tmp_path / f"{team}.parquet")
    _LOOKUP_CACHE.clear()
    yield tmp_path
    _LOOKUP_CACHE.clear()


def test_second_call_returns_the_very_same_objects(cache_dir: Path) -> None:
    """⭐ 命中判据用**对象同一性**,不用耗时 —— 计时断言在 CI 上是薛定谔的。

    `is` 为真 ⇒ 没重建。这是「缓存真的生效了」唯一不含噪声的证据。
    """
    h1, l1 = load_clubelo_history_cached(cache_dir)
    h2, l2 = load_clubelo_history_cached(cache_dir)
    assert h1 is h2, "history 被重建了 —— 缓存没命中"
    assert l1 is l2, "lookup 被重建了 —— 缓存没命中"


def test_stale_cache_is_not_served(cache_dir: Path) -> None:
    """🚨 承重:动了目录里**任何一个**文件都必须重建。

    ⛔ 第一版指纹是 `(文件数, max(mtime), 总字节)`,**被这条测试当场证伪**:
    把**最旧**那个文件的 mtime 往前拨,它仍低于 max ⇒ 指纹不变 ⇒ 吃陈旧缓存。
    真实 cron 写入把 mtime 设成「现在」所以能被发现,但**原地改一个旧文件**
    (回填、修某支队的历史)会漏。
    ⭐ 通用教训:**用聚合量当指纹,就会漏掉不改变聚合量的那类变化。**

    这里刻意改**较旧**的那个文件 —— 正是当初漏掉的那一类。
    """
    _, l0 = load_clubelo_history_cached(cache_dir)
    files = sorted(cache_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime_ns)
    oldest = files[0]
    st = os.stat(oldest)
    os.utime(oldest, ns=(st.st_atime_ns, st.st_mtime_ns - 10**9))   # 往**回**拨,max 不受影响

    _, l1 = load_clubelo_history_cached(cache_dir)
    assert l1 is not l0, (
        f"改了 {oldest.name} 的 mtime 却没重建 —— cron 更新后面板会一直读旧 Elo")


def test_adding_and_removing_a_file_both_invalidate(cache_dir: Path) -> None:
    """新增/删除也必须被发现 —— clubelo 会随赛季增删球队。"""
    _, l0 = load_clubelo_history_cached(cache_dir)
    pd.DataFrame({
        "team_canonical": ["Gamma"], "clubelo_slug": ["gamma"], "country": ["XX"],
        "elo": [1500.0], "from_date": [pd.Timestamp("2026-01-01").date()],
        "to_date": [pd.Timestamp("2026-12-31").date()],
    }).to_parquet(cache_dir / "Gamma.parquet")
    _, l1 = load_clubelo_history_cached(cache_dir)
    assert l1 is not l0 and "Gamma" in l1, "新增球队没被发现"

    (cache_dir / "Gamma.parquet").unlink()
    _, l2 = load_clubelo_history_cached(cache_dir)
    assert l2 is not l1 and "Gamma" not in l2, "删除球队没被发现"


def test_explicit_history_still_bypasses_the_cache(cache_dir: Path) -> None:
    """⛔ 显式传 `history=` 的调用方**不许**走缓存。

    全部既有 clubelo 测试都是那么调的(`test_clubelo_features.py` 7 处)——
    给它们套上共享缓存会让测试之间互相污染,那是比慢更坏的东西。
    """
    fixt = pd.DataFrame({"home_team": ["Alpha"], "away_team": ["Beta"],
                         "date": pd.to_datetime(["2026-06-01"])})
    # 喂一份**和磁盘不同**的历史;若被缓存劫持,拿到的会是磁盘那份
    fake = pd.DataFrame({
        "team_canonical": ["Alpha", "Beta"], "clubelo_slug": ["a", "b"],
        "country": ["XX", "XX"], "elo": [1900.0, 1100.0],
        "from_date": [pd.Timestamp("2026-01-01").date()] * 2,
        "to_date": [pd.Timestamp("2026-12-31").date()] * 2,
    })
    load_clubelo_history_cached(cache_dir)          # 先把磁盘那份灌进缓存
    out = build_clubelo_features(fixt, cache_dir=cache_dir, history=fake)
    assert out["clubelo_home"].iloc[0] == pytest.approx(1900.0), "显式 history 被缓存劫持了"
    assert out["clubelo_away"].iloc[0] == pytest.approx(1100.0)


def test_cached_and_uncached_agree_bit_for_bit(cache_dir: Path) -> None:
    """⭐ 这是「纯性能改动」的定义:同样的输入,输出**逐位**相同。

    上线时另跑过一次真数据版(6 行 × 5 列 = 30 个数,0 个不一致),
    这里用夹具把它固化成回归护栏。
    """
    fixt = pd.DataFrame({
        "home_team": ["Alpha", "Beta", "NoSuchTeam"],
        "away_team": ["Beta", "NoSuchTeam", "Alpha"],
        "date": pd.to_datetime(["2026-06-01", "2026-06-02", "2020-01-01"]),
    })
    hist, _ = load_clubelo_history_cached(cache_dir)
    uncached = build_clubelo_features(fixt.copy(), history=hist)   # 绕开缓存
    _LOOKUP_CACHE.clear()
    cached = build_clubelo_features(fixt.copy(), cache_dir=cache_dir)   # 走缓存
    cols = [c for c in cached.columns if c.startswith("clubelo_")]
    assert cols, "clubelo 列没生成"
    for c in cols:
        pd.testing.assert_series_equal(cached[c], uncached[c], check_exact=True)


def test_missing_dir_degrades_instead_of_crashing(tmp_path: Path) -> None:
    """目录不存在 ⇒ 空 lookup,不炸(与 `load_clubelo_history` 同惯例)。

    ⚠️ 我第一版断言 `_cache_stamp(gone) == ()`,**红了** —— `Path.glob` 对不存在的
    目录不抛 `OSError`,只是不产出,所以指纹是 `(0, hash(()))`。
    断言改成真正重要的两条性质,而不是我以为的返回值:
      ① 不炸、给空结果;② 指纹**稳定**(否则每次都判失效,缓存等于没加)。
    """
    gone = tmp_path / "nope"
    hist, lookup = load_clubelo_history_cached(gone)
    assert hist.empty and lookup == {}
    assert _cache_stamp(gone) == _cache_stamp(gone), "空目录指纹不稳定 ⇒ 会无限重建"
    _, lookup2 = load_clubelo_history_cached(gone)
    assert lookup2 is lookup, "空目录没走缓存 ⇒ 每次请求都白跑一遍"
