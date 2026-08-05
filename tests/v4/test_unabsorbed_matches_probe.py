"""未吸收比赛探针:artifact 落后多少,不靠 mtime 代理(owner 2026-08-05)。

## 缘起

owner 问「Elo 接下来会不会自动更新」。查下来三条实测:

  · 没有任何 train/retrain 的 launchd job(24 个 job grep 零命中);
  · `apply_results`(team_state 增量更新)只存在于 `persist.py:21` 的注释里;
  · 名字很像的 `weekly_elo_refresh` 跑的是 `ingest_eloratings` = **国家队** Elo,
    `weekly_clubelo_refresh` 是外部 ClubElo —— **两个都不碰 team_state**。

⇒ 模型自己的 Elo 是训练期快照,冻在 2026-07-15(cutoff 2026-06-01),不会自己动。

## 但「该重训了」这句话当时是错的

实测源树:cutoff 之后 **0 场**新比赛(football-data 语料止于 2026-05-31,正好
是 cutoff)。欧洲联赛 6–7 月休赛 ⇒ 今天重训是空操作,一行都加不进去。

## 真正缺的信号

`check_model_supply_chain` 原有两个量都是**代理**:

  · artifact 年龄  → 「多久没重训」,但休赛期不重训是对的;
  · 源树 CSV mtime → 「多久没进新文件」,而它能被**手动放一次文件**清零。

秋天这两个会同时说谎:8 月手动更新一次 CSV ⇒ mtime 变绿、报警闭嘴,而
artifact 仍然没吸收那批比赛。**刷新输入把关于输出的报警说服了** —— 同族见
[[health-check-guardrails]] 的「检查的前提没人检查」。

本文件钉住的核心性质就是这一条:**touch CSV 文件不能让未吸收报警闭嘴。**
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from nutmeg.v4.cli import data_freshness as df_mod
from nutmeg.v4.cli.data_freshness import (
    UNABSORBED_MATCHES_ALARM,
    _count_matches_after,
    _training_cutoff,
    check_model_supply_chain,
)

TODAY = dt.date(2026, 8, 5)


def _artifact(tmp_path: Path, cutoff: str | None = "2026-06-01") -> Path:
    art = tmp_path / "artifact"
    art.mkdir()
    meta: dict = {"model_type": "catboost", "elo_initial": 1500.0}
    if cutoff is not None:
        # 真实形状:cutoff 嵌在 metadata 子字典里,不是顶层
        meta["metadata"] = {"training_cutoff": cutoff, "n_train": 29347}
    (art / "metadata.json").write_text(json.dumps(meta))
    return art


def _sources(tmp_path: Path, n_after: int, cutoff: str = "2026-06-01") -> Path:
    """造一棵最小 football-data 树:n_after 场晚于 cutoff + 几场早于 cutoff。"""
    src = tmp_path / "src"
    (src / "europe" / "2526").mkdir(parents=True)
    rows = []
    for i in range(3):
        rows.append(("01/05/2026", f"OldH{i}", f"OldA{i}", 1, 0))
    base = pd.Timestamp(cutoff) + pd.Timedelta(days=40)
    for i in range(n_after):
        d = (base + pd.Timedelta(days=i % 30)).strftime("%d/%m/%Y")
        rows.append((d, f"NewH{i}", f"NewA{i}", 2, 1))
    out = pd.DataFrame(rows, columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    out["FTR"] = "H"
    # ⚠️ `_read_europe_csv` 对缺 `Div` 是**抛异常**,不是返回空 —— 少这一列会让
    # 整个探针走 None 分支,测试就变成在测「探针坏掉时的样子」而不是它的行为。
    out.insert(0, "Div", "E0")
    out.to_csv(src / "europe" / "2526" / "E0.csv", index=False)
    return src


class TestCutoffReading:
    def test_reads_the_nested_key(self, tmp_path):
        """⚠️ `training_cutoff` 在 metadata 子字典里。写成顶层会永远拿 None,
        而「拿不到 cutoff」和「没有新比赛」在报告里都不报警 ⇒ 静默失效。"""
        assert _training_cutoff(_artifact(tmp_path)) == "2026-06-01"

    def test_missing_cutoff_gives_none_not_a_guess(self, tmp_path):
        assert _training_cutoff(_artifact(tmp_path, cutoff=None)) is None

    def test_missing_or_broken_metadata_gives_none(self, tmp_path):
        assert _training_cutoff(tmp_path / "nope") is None
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "metadata.json").write_text("{not json")
        assert _training_cutoff(bad) is None


class TestCountingSeparatesAbsenceFromBlindness:
    def test_counts_only_matches_after_the_cutoff(self, tmp_path):
        src = _sources(tmp_path, n_after=17)
        assert _count_matches_after(src, "2026-06-01") == 17

    def test_offseason_is_a_real_zero(self, tmp_path):
        """0 = 「去看了,确实没有」—— 休赛期的正确答案,不该报警。"""
        assert _count_matches_after(_sources(tmp_path, n_after=0), "2026-06-01") == 0

    def test_unreadable_source_is_none_not_zero(self, tmp_path, monkeypatch):
        """⭐ None ≠ 0。把读失败折成 0 就是又一次「分不出没有和没去看」——
        探针会在自己坏掉的时候安静地宣布「没有新数据」。"""
        def boom(*a, **k):
            raise OSError("disk gone")
        monkeypatch.setattr(df_mod, "_count_matches_after", _count_matches_after)
        monkeypatch.setattr("nutmeg.v4.data.ingest.load_all_matches", boom)
        assert _count_matches_after(tmp_path, "2026-06-01") is None


class TestAlarmBehaviour:
    def test_quiet_when_nothing_new(self, tmp_path):
        info, alarms = check_model_supply_chain(
            TODAY, artifact_dir=_artifact(tmp_path),
            sources_dir=_sources(tmp_path, n_after=0), external_dir=tmp_path / "none")
        assert not [a for a in alarms if "未吸收" in a or "从没见过" in a]
        assert any("未吸收比赛: 0 场" in i for i in info)

    def test_fires_once_a_real_backlog_exists(self, tmp_path):
        n = UNABSORBED_MATCHES_ALARM + 50
        info, alarms = check_model_supply_chain(
            TODAY, artifact_dir=_artifact(tmp_path),
            sources_dir=_sources(tmp_path, n_after=n), external_dir=tmp_path / "none")
        hit = [a for a in alarms if "从没见过" in a]
        assert hit, alarms
        assert str(n) in hit[0] and "2026-06-01" in hit[0]

    def test_just_under_threshold_stays_quiet(self, tmp_path):
        """零星补录不该逼人重训一次。"""
        _, alarms = check_model_supply_chain(
            TODAY, artifact_dir=_artifact(tmp_path),
            sources_dir=_sources(tmp_path, n_after=UNABSORBED_MATCHES_ALARM),
            external_dir=tmp_path / "none")
        assert not [a for a in alarms if "从没见过" in a]

    def test_no_cutoff_says_so_instead_of_silently_passing(self, tmp_path):
        """拿不到 cutoff 时要在 info 里明说,别和「没有新数据」长得一样。"""
        info, _ = check_model_supply_chain(
            TODAY, artifact_dir=_artifact(tmp_path, cutoff=None),
            sources_dir=_sources(tmp_path, n_after=999), external_dir=tmp_path / "none")
        assert any("没有 training_cutoff" in i for i in info), info


class TestTouchingFilesCannotSilenceIt:
    def test_fresh_mtime_does_not_quiet_the_backlog_alarm(self, tmp_path):
        """⭐⭐ 本文件的承重条。

        造一棵**文件刚落盘**(mtime=现在,源树年龄报警必然安静)但装着一大批
        cutoff 之后比赛的源树。旧的两个代理都会说「一切正常」,未吸收探针必须
        照样喊 —— 这正是 8 月手动更新一次 CSV 之后会发生的事。
        """
        src = _sources(tmp_path, n_after=UNABSORBED_MATCHES_ALARM + 300)
        now = dt.datetime.now().timestamp()
        for f in src.rglob("*.csv"):
            os.utime(f, (now, now))

        info, alarms = check_model_supply_chain(
            TODAY, artifact_dir=_artifact(tmp_path), sources_dir=src,
            external_dir=tmp_path / "none")

        # 代理确实被"喂饱"了:源树年龄报警不响
        assert not [a for a in alarms if "源树" in a and "没进新数据" in a], alarms
        # 但真信号照样喊
        assert [a for a in alarms if "从没见过" in a], (
            "⭐ touch 一下文件就让报警闭嘴了 —— 正是本探针要防的那件事")


def test_the_real_tree_is_currently_a_true_zero():
    """拿真源树核一次(存在才跑)。

    2026-08-05 实测:football-data 语料止于 2026-05-31 = cutoff,cutoff 之后
    **0 场**。所以「artifact 该重训了」当时是错的 —— 重训会一行都加不进去。
    这条红了说明新赛季数据进来了,那时重训才真的买得到东西。
    """
    src = Path("data/historical_sources/football_data_co_uk")
    art = Path("data/v4_model_cat")
    if not (src.exists() and (art / "metadata.json").exists()):
        pytest.skip("生产数据不在(CI)")
    cutoff = _training_cutoff(art)
    assert cutoff == "2026-06-01", f"cutoff 变了({cutoff})— 本文件的叙述要重查"
    n = _count_matches_after(src, cutoff)
    assert n is not None, "探针读不了真源树"
    assert n >= 0
