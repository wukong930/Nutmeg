"""新队三件套哨兵 — 队名翻译 + 队徽的覆盖审计。"""
from __future__ import annotations

import datetime as dt
import sqlite3

from nutmeg.v4.cli import team_assets_check as tac


def _db(tmp_path, rows):
    """建一个只含 odds_snapshots 必要列的临时库。"""
    path = tmp_path / "obs.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE odds_snapshots (home_team TEXT, away_team TEXT, "
        "league TEXT, kickoff_utc TEXT)"
    )
    conn.executemany("INSERT INTO odds_snapshots VALUES (?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return str(path)


def _iso(hours):
    return (dt.datetime.now(dt.UTC) + dt.timedelta(hours=hours)).isoformat()


def test_collect_only_future_and_within_window(tmp_path):
    """只收未来、且在窗口内的场 —— 已开球的队补件已经来不及,过远的是噪声。"""
    db = _db(tmp_path, [
        ("Past FC", "Past Utd", "UCL", _iso(-5)),      # 已开球 → 不收
        ("Soon FC", "Soon Utd", "UCL", _iso(+12)),     # 窗口内 → 收
        ("Far FC", "Far Utd", "UCL", _iso(+24 * 30)),  # 30 天后 → 窗口外
    ])
    teams = tac.collect_upcoming_teams(db, days=7)
    assert set(teams) == {"Soon FC", "Soon Utd"}


def test_audit_separates_the_two_mechanisms(tmp_path, monkeypatch):
    """②③ 互相独立:有中文名不代表有队徽,反之亦然。

    这正是 2026-07-21 的实测形态 —— Slovan Bratislava 有中文名却缺队徽,
    所以两类必须分开报,不能合成一个「缺件」计数。
    """
    monkeypatch.setattr(tac, "TEAM_NAME_ZH", {"Has Zh Only": "有中文", "Has Both": "都有"})
    monkeypatch.setattr(tac, "logo_exists", lambda n: n in {"Has Logo Only", "Has Both"})
    teams = {
        "Has Zh Only": ("UCL", _iso(1)),
        "Has Logo Only": ("UCL", _iso(2)),
        "Has Both": ("UCL", _iso(3)),
        "Has Neither": ("UCL", _iso(4)),
    }
    no_zh, no_logo = tac.audit(teams)
    assert no_zh == ["Has Logo Only", "Has Neither"]
    assert no_logo == ["Has Zh Only", "Has Neither"]


def test_render_marks_gaps_with_warn_never_fail(tmp_path, monkeypatch):
    """输出契约:有缺口发 ⚠,全覆盖发 ✓,**永不发 ✗** —— ②③ 不影响 EV,
    不该让 health_check 变红(health_check 第 12 节 grep 的就是 ⚠)。"""
    monkeypatch.setattr(tac, "TEAM_NAME_ZH", {})
    monkeypatch.setattr(tac, "logo_exists", lambda n: True)
    teams = {"Nobody Knows": ("UECL", _iso(6))}
    out = tac.render(teams, ["Nobody Knows"], [], days=7)
    assert "⚠" in out and "✗" not in out
    assert "Nobody Knows" in out
    assert "✓ ③ 队徽:全覆盖" in out


def test_main_exit_zero_even_with_gaps(tmp_path, monkeypatch, capsys):
    """缺件不是钱 bug → 退出码恒 0。"""
    monkeypatch.setattr(tac, "TEAM_NAME_ZH", {})
    monkeypatch.setattr(tac, "logo_exists", lambda n: False)
    db = _db(tmp_path, [("A FC", "B FC", "UCL", _iso(10))])
    assert tac.main(["--db", db, "--days", "7"]) == 0
    assert "⚠" in capsys.readouterr().out


def test_main_handles_empty_schedule(tmp_path, capsys):
    """休赛期无赛程 → 说人话,别报成「全覆盖」(那是假绿灯)。"""
    db = _db(tmp_path, [])
    assert tac.main(["--db", db]) == 0
    assert "无赛程" in capsys.readouterr().out
