"""δ 校准仪表的**自动存档 + 自比**(2026-08-03)。

## 为什么加

prereg v2.0 §5.1 的回滚条件是:

> ±1 任一条线的 3-way log-loss 比裸网格更差,**且连续两周如此** ⇒ 回滚到 v1.9

但仪表原来只写 `logs/delta_calibration_latest.md`,**每次运行覆盖、不留历史** ——
那个条件在产物上**根本无法判定**:没有上周的数可比。

⭐ 这是本会话第三次撞见同一族问题:**检查和它的前提不匹配**。
  · 涓流:`END` 写成常量 ⇒「零新增」在数学上必然 ⇒ 假的完成信号
  · s6 :用「今天窗口为空」证明过滤器接通 ⇒ 到日子就自动失效
  · 这条:要求「连续两周」,却配了个不留历史的工具

修法不是「记得每周手动 cp 一份」——那只是把缺陷转嫁给人的记性。
是让工具**自己存档、自己比、自己在报告里回答「连续两周了吗」**。
"""
from __future__ import annotations

import json
from pathlib import Path

from nutmeg.v4.cli.delta_calibration import load_prev, main, render, slice_key, slice_stats

REPO = Path(__file__).resolve().parents[2]


def _bucket(n: int, p_raw: float, p_c1: float, hit: int = 0):
    """n 条同样的观测:裸网格 P 三元组、C1 后三元组、命中腿。"""
    raw = (p_raw, (1 - p_raw) / 2, (1 - p_raw) / 2)
    c1 = (p_c1, (1 - p_c1) / 2, (1 - p_c1) / 2)
    return [(raw, c1, hit)] * n


def test_slice_stats_only_keeps_slices_above_min_n() -> None:
    """存档口径必须和报告口径一致 —— 否则报告说「样本太小跳过」,
    存档却记了一笔,下次自比就拿一个报告里根本没显示的数当基准。"""
    buckets = {(-1, "俱乐部"): _bucket(50, 0.4, 0.45), (+1, "大赛"): _bucket(3, 0.4, 0.45)}
    st = slice_stats(buckets, min_n=10)
    assert set(st) == {"-1·俱乐部"}, st
    assert st["-1·俱乐部"]["n"] == 50


def test_load_prev_excludes_today(tmp_path: Path) -> None:
    """⭐ 承重:同日重跑时今天的存档**已被覆盖**,若不排除今天就会拿自己当基准,
    「连续两次变差」永远成立 —— 自比工具的经典自噬。"""
    h = tmp_path / "delta_calibration_history"
    h.mkdir()
    def _put(day: str, n: int) -> None:
        (h / f"{day}.json").write_text(
            json.dumps({"+1·俱乐部": {"n": n, "raw_ll": 1.0, "c1_ll": 1.1}}))
    _put("2026-08-02", 1)
    _put("2026-08-09", 2)
    prev = load_prev(h, "2026-08-09")
    assert prev is not None and prev["_date"] == "2026-08-02", "没排除今天"
    assert prev["_gap_days"] == 7


def test_load_prev_is_none_on_first_ever_run(tmp_path: Path) -> None:
    assert load_prev(tmp_path / "nope", "2026-08-09") is None


def test_report_says_baseline_when_there_is_no_history() -> None:
    """⛔ 没有历史时**必须明说** —— 不能安静地当作「没变差」。
    「分不出没有和没去看」正是本项目反复踩的那个洞。"""
    txt = render({(-1, "俱乐部"): _bucket(50, 0.4, 0.45)}, min_n=10, prev=None)
    assert "没有上次存档" in txt and "本次是基线" in txt


def test_consecutive_worse_on_a_pm1_line_names_the_rollback() -> None:
    """两次都变差 ⇒ 报告直接点名 prereg §5.1 和回滚目标值,不留给人去查。"""
    buckets = {(+1, "俱乐部"): _bucket(60, 0.40, 0.30)}    # C1 把命中腿压低 = 变差
    prev = {"_date": "2026-07-27", "_gap_days": 7,
            slice_key(+1, "俱乐部"): {"n": 55, "raw_ll": 1.03, "c1_ll": 1.05}}
    txt = render(buckets, min_n=10, prev=prev)
    assert "连续两次变差" in txt
    assert "§5.1" in txt and "0.03220" in txt, "没写清回滚到哪个值"


def test_same_week_double_run_is_called_out() -> None:
    """⚠️ 「连续两周」不该由同一周跑两次凑出来 —— 间隔太短要显式说破。"""
    buckets = {(+1, "俱乐部"): _bucket(60, 0.40, 0.30)}
    prev = {"_date": "2026-08-01", "_gap_days": 1,
            slice_key(+1, "俱乐部"): {"n": 55, "raw_ll": 1.03, "c1_ll": 1.05}}
    txt = render(buckets, min_n=10, prev=prev)
    assert "不足一周" in txt


def test_minus_2_worse_does_not_trigger_the_pm1_rollback() -> None:
    """§5.1 只管 **±1**。−2 变差不该冒充回滚条件(它走别的路)。"""
    buckets = {(-2, "大赛"): _bucket(60, 0.40, 0.30)}
    prev = {"_date": "2026-07-27", "_gap_days": 7,
            slice_key(-2, "大赛"): {"n": 55, "raw_ll": 1.03, "c1_ll": 1.05}}
    txt = render(buckets, min_n=10, prev=prev)
    assert "连续两次变差" not in txt, "−2 触发了只该 ±1 触发的回滚条件"


def test_archive_is_written_by_default(tmp_path: Path, monkeypatch) -> None:
    """默认就存档 —— 存档是「连续两周」判定的唯一依据,不该要人记得加开关。"""
    monkeypatch.chdir(REPO)
    out = tmp_path / "latest.md"
    assert main(["--out", str(out)]) == 0
    h = tmp_path / "delta_calibration_history"
    assert h.exists(), "默认没有存档"
    assert list(h.glob("*.json")) and list(h.glob("*.md")), "md/json 缺一"


def test_no_archive_flag_opts_out(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(REPO)
    assert main(["--out", str(tmp_path / "latest.md"), "--no-archive"]) == 0
    assert not (tmp_path / "delta_calibration_history").exists()
