"""δ「连续变差」追踪(2026-08-23)—— 把一个天天在印却没人看得见的数印出来。

## 病史

2026-08-22 owner 顺口问「§15 里 −1 俱乐部变差这条怎么处理」,查下来
`+1·俱乐部` 已经**连续 22 个读数**比裸网格差(2026-08-02 起),
而 prereg v2.0 §5.1 的回滚条件早在 **08-16** 就满足了 —— **没有任何人被通知**。

根因不是「没有归档」(归档 08-02 起就在写),是**每份产物只显示当天那一帧**,
「连了多久」这个数在任何现有输出里都不存在。本模块就是把它算出来并接进体检。

## 🚨 它是可见性装置,不是判据

- 日读数之间共享几乎全部数据(N 从 63 涨到 112 用了三周)
  ⇒ **22 个读数不是 22 个证据,是 1 个证据印了 22 遍**。
- 判「变差」只看符号、**没有幅度阈值**:2026-08-22 的对抗审查实测,零效应下
  连续两月切片都变差的概率 ≈ **24.6%**,且与 `n_delta` **无关**(30→200 不变);
  九个月赛季至少一次假触发 ≈ **82%**。
⇒ 看到 ⚠️ **不等于该回滚**。回滚判据在 prereg v2.0 §5.1,要 owner 口令。
（替换它的 v2.1 §4 已被同一次对抗审查否掉:承重证据跨了两把尺子做减法。)
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _hist(tmp_path: Path, rows: list[tuple[str, float, int | None]]) -> Path:
    """造归档。rows = [(日期, +1俱乐部的 diff, n_delta)],diff<0 = 变差。"""
    h = tmp_path / "delta_calibration_history"
    h.mkdir(parents=True, exist_ok=True)
    for date, diff, nd in rows:
        cell = {"raw_ll": 1.0, "c1_ll": 1.0 - diff, "n": 100}
        if nd is not None:
            cell["n_delta"] = nd
        (h / f"{date}.json").write_text(
            json.dumps({"+1·俱乐部": cell, "-1·俱乐部": cell}, ensure_ascii=False),
            encoding="utf-8")
    return h


def test_it_counts_consecutive_worse_readings(tmp_path) -> None:
    """⭐ 承重:这就是那个「任何现有输出里都不存在」的数。"""
    from nutmeg.v4.cli.delta_calibration import worse_streaks
    h = _hist(tmp_path, [("2026-08-01", +0.01, 20), ("2026-08-02", -0.01, 20),
                         ("2026-08-03", -0.02, 20), ("2026-08-04", -0.03, 20)])
    st = worse_streaks(h)["+1·俱乐部"]
    assert st["streak"] == 3, "没数对连续变差的读数"
    assert st["n_readings"] == 4
    assert st["latest"]["date"] == "2026-08-04"


def test_an_improving_reading_breaks_the_streak(tmp_path) -> None:
    """改善就断 —— 否则它会变成一个永远只涨不跌的数字,失去信息。"""
    from nutmeg.v4.cli.delta_calibration import worse_streaks
    h = _hist(tmp_path, [("2026-08-01", -0.01, 20), ("2026-08-02", +0.01, 20),
                         ("2026-08-03", -0.01, 20)])
    assert worse_streaks(h)["+1·俱乐部"]["streak"] == 1


def test_untested_readings_break_the_streak_and_are_named(tmp_path) -> None:
    """🚨 承重:`n_delta == 0` 是「**没测**」不是「没变差」。

    这是 `00fdb53` 修掉的那个病(差值恒 0 被印成 ✅ 改善)在连续计数上的复现。

    ⚠️ **夹具用 diff<0 而不是 diff==0**:现实里 `n_delta==0` ⇒ `c1_ll ≡ raw_ll`
    ⇒ diff 恒 0,而 `0 < 0` 为假 ⇒ 连续**本来就会断**。用 diff==0 造夹具时,
    把 `break` 删掉测试照样绿(空包弹第 ① 发实测)—— 那样这条断言就没在守
    任何东西。用 diff<0 才让那个 `break` 承重:它守的是「哪天 c1 口径变了、
    没测的行也可能带非零差」时,连续**仍然**必须断。
    """
    from nutmeg.v4.cli.delta_calibration import worse_streaks
    h = _hist(tmp_path, [("2026-08-01", -0.01, 20), ("2026-08-02", -0.05, 0),
                         ("2026-08-03", -0.01, 20)])
    st = worse_streaks(h)["+1·俱乐部"]
    assert st["streak"] == 1, "「没测」那份被算进了连续变差"
    assert st["n_untested"] == 1, "「没测」没有被单独计数 ⇒ 它会静默消失"


def test_legacy_archives_are_flagged(tmp_path) -> None:
    """2026-08-16 之前的归档没有 `n_delta` 字段 ⇒ 分不出「没测」和「没变差」,
    必须标出来,别假装那段历史和现在同质。"""
    from nutmeg.v4.cli.delta_calibration import worse_streaks
    h = _hist(tmp_path, [("2026-08-01", -0.01, None), ("2026-08-02", -0.01, 20)])
    assert worse_streaks(h)["+1·俱乐部"]["has_legacy"] is True


def test_no_archive_is_not_a_zero_streak(tmp_path) -> None:
    """⛔ 没有归档 ⇒ `latest is None`,渲染成「无归档读数」——
    **不能**渲染成「连续 0 个」,那和「一切正常」同形。"""
    from nutmeg.v4.cli.delta_calibration import render_streaks, worse_streaks
    st = worse_streaks(tmp_path / "nope")
    assert st["+1·俱乐部"]["latest"] is None
    assert "无归档读数" in render_streaks(st)


def test_the_threshold_constant_is_pinned() -> None:
    """⛔ 先把常数钉死,再谈行为。

    ⚠️ 本条的第一版把阈值当参数造夹具(`range(1, _STREAK_WARN)`)⇒ 常数被改成 1
    时测试**跟着适应、照样绿** —— 那是拿常数验证常数。空包弹第 ④ 发抓到的。
    14 ≈ 两周日读数,对齐 prereg v2.0 §5.1「连续两周」的精神;改它要改这里。
    """
    from nutmeg.v4.cli.delta_calibration import _STREAK_WARN
    assert _STREAK_WARN == 14


def test_the_warning_marker_only_appears_past_the_threshold(tmp_path) -> None:
    """⭐ 行为断言:体检靠 `⚠️` 把它路由成黄灯(`warn`)而不是灰字(`note`)。

    用**字面量** 13 / 15 跨过阈值,不引用常数。
    """
    from nutmeg.v4.cli.delta_calibration import render_streaks, worse_streaks

    def marker(n: int) -> str:
        h = _hist(tmp_path / f"n{n}", [(f"2026-08-{i:02d}", -0.01, 20)
                                       for i in range(1, n + 1)])
        line = [l for l in render_streaks(worse_streaks(h)).splitlines()
                if l.startswith("- 连续变差")][0]
        return line

    assert "⚠️" not in marker(13), "13 个读数就亮黄 —— 阈值比 14 松了"
    assert "⚠️" in marker(15), "15 个读数还不亮黄 —— 阈值比 14 紧了"


def test_the_render_always_carries_the_not_a_gate_caveat() -> None:
    """⛔ 承重:这段警告是这个装置能存在的前提。

    没有它,一个只判符号、假阳性 24.6%/窗的数字会被当成回滚信号 ——
    那正是本仓「绿灯 + 口头禁令」的镜像(黄灯 + 没人说清它不算数)。
    """
    from nutmeg.v4.cli.delta_calibration import render_streaks, worse_streaks
    out = render_streaks(worse_streaks(REPO / "logs/delta_calibration_history"))
    assert "不是回滚判据" in out and "24.6%" in out
    assert "prereg v2.0 §5.1" in out, "没指明真正的判据在哪"
