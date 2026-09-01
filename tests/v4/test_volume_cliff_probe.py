"""行量断崖探针 —— 抓「**还在写,但量掉了一个数量级**」(2026-09-01)。

## 它存在的理由(一次真事故)

`check_freshness` 问的是「最后一行多久前」。2026-08-23 起 Polymarket 抓取从
~140 行/天塌到 ~10 行/天,**但它每天都还在写** ⇒ 最后一行永远是今天 ⇒ 探针
一路报 ✓ 绿,可用赛事从 344 个掉到 22 个,**塌了 10 天没人知道**。

⇒ 这一族故障(静默降级)对「最后一行」判据是**结构上不可见**的,需要第二个判据。

## 阈值是回测定的,不是拍的

0.30:在健康表 `odds_snapshots`(49 个可回测日)上触发 **0 次**,
而 `polymarket_gaps` 的真塌方触发 5 次;0.60 会在健康表上响 7 次(太松)。
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from nutmeg.v4.cli.data_freshness import (
    _CLIFF_MIN_BASELINE,
    _CLIFF_RATIO,
    _VOLUME_CLIFF_TABLES,
    check_volume_cliff,
)

TODAY = date(2026, 9, 1)
TBL = "polymarket_gaps"
COL = _VOLUME_CLIFF_TABLES[TBL]


def _db(tmp_path: Path, recent_per_day: int, base_per_day: int) -> Path:
    """近 7 天每天 `recent_per_day` 行,前 28 天每天 `base_per_day` 行。"""
    p = tmp_path / "obs.db"
    conn = sqlite3.connect(p)
    conn.execute(f"CREATE TABLE {TBL} ({COL} TEXT)")
    rows = []
    for k in range(0, 7):
        rows += [((TODAY - timedelta(days=k)).isoformat() + "T12:00:00+00:00",)] * recent_per_day
    for k in range(7, 35):
        rows += [((TODAY - timedelta(days=k)).isoformat() + "T12:00:00+00:00",)] * base_per_day
    conn.executemany(f"INSERT INTO {TBL} VALUES (?)", rows)
    conn.commit(); conn.close()
    return p


def test_a_real_cliff_fires(tmp_path: Path) -> None:
    """还在写(每天都有行)但量塌了 20 倍 ⇒ 必须响。

    这就是 Polymarket 那次的形状:`check_freshness` 看不见它,因为最后一行是今天。
    """
    info, alarms = check_volume_cliff(_db(tmp_path, 6, 124), today=TODAY)
    assert alarms, "真断崖没响 —— 这个探针存在的唯一理由就是抓它"
    assert TBL in alarms[0] and "行量断崖" in alarms[0]
    assert info, "只报警不给读数 ⇒ 人看不出掉了多少"


def test_a_healthy_table_is_silent(tmp_path: Path) -> None:
    """⭐ 假红比假绿更贵 —— 量在涨的表绝不能响。"""
    _, alarms = check_volume_cliff(_db(tmp_path, 150, 120), today=TODAY)
    assert not alarms, alarms


def test_a_small_table_is_never_judged(tmp_path: Path) -> None:
    """基线低于 `_CLIFF_MIN_BASELINE` 不判 —— 小表的比值全是噪声。

    没有这条闸,任何一张每天几行的表都会随机响。
    """
    base = int(_CLIFF_MIN_BASELINE) - 1
    info, alarms = check_volume_cliff(_db(tmp_path, 0, base), today=TODAY)
    assert not alarms, "基线太小还判了"
    assert not info, "基线太小时连读数都不该报(会被误当成有意义)"


@pytest.mark.parametrize("ratio_target", [0.05, 0.20, 0.29])
def test_it_fires_below_the_threshold(tmp_path: Path, ratio_target: float) -> None:
    base = 200
    _, alarms = check_volume_cliff(
        _db(tmp_path, max(int(base * ratio_target), 1), base), today=TODAY)
    assert alarms, f"{ratio_target} < {_CLIFF_RATIO} 却没响"


@pytest.mark.parametrize("ratio_target", [0.35, 0.60, 1.00])
def test_it_stays_silent_above_the_threshold(tmp_path: Path, ratio_target: float) -> None:
    base = 200
    _, alarms = check_volume_cliff(
        _db(tmp_path, int(base * ratio_target), base), today=TODAY)
    assert not alarms, f"{ratio_target} ≥ {_CLIFF_RATIO} 却响了(假红)"


def test_a_missing_table_is_not_an_alarm(tmp_path: Path) -> None:
    """旧库缺表/缺列 ⇒ 跳过,**不是**报警 —— 否则升级期间全是假红。"""
    p = tmp_path / "obs.db"
    conn = sqlite3.connect(p); conn.execute("CREATE TABLE unrelated (x TEXT)")
    conn.commit(); conn.close()
    info, alarms = check_volume_cliff(p, today=TODAY)
    assert not alarms and not info


def test_the_alarm_kind_is_reported(tmp_path: Path) -> None:
    """⭐ 报警类别行必须带上它 —— 否则 owner 收到推送后不知道是哪一类。

    这正是 2026-08-24 那次的教训(推送文案指向 cron,实际是联赛标签)。
    """
    from nutmeg.v4.cli.data_freshness import alarm_kinds_line
    line = alarm_kinds_line([], [], [], [], [], ["x"])
    assert "行量断崖" in line, line
    assert alarm_kinds_line([], [], [], [], [], []) == "", "全绿时不该出类别行"
