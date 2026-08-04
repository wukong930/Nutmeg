"""nutmeg-backfill-odds-names — 存量行补归一(2026-08-04)。

别名表修的是写入侧;表是 append-only 的,补一条别名之后**之前落下的行还是分开的**。
这个 CLI 补那个存量。危险点全在「写数据库」上,所以测试盯的是:默认不写、
撞车不静默、改完幂等。
"""
from __future__ import annotations

import sqlite3

import pytest

from nutmeg.v4.cli import backfill_odds_names as m

# 用真别名表里的一条:('SUI_SUPER_LEAGUE', 'Servette') → 'Servette FC'
_LG, _OLD, _NEW = "SUI_SUPER_LEAGUE", "Servette", "Servette FC"
_OLD2, _NEW2 = "FC Basel", "FC Basel 1893"


def _db(tmp_path, rows):
    p = tmp_path / "o.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE odds_snapshots (id INTEGER PRIMARY KEY, league TEXT, "
              "match_date TEXT, home_team TEXT, away_team TEXT, captured_at TEXT)")
    c.executemany("INSERT INTO odds_snapshots (league, match_date, home_team, away_team, "
                  "captured_at) VALUES (?,?,?,?,?)", rows)
    c.commit()
    c.close()
    return p


def _dump(p):
    c = sqlite3.connect(p)
    out = c.execute(
        "SELECT league, home_team, away_team FROM odds_snapshots ORDER BY id").fetchall()
    c.close()
    return out


class TestBackfill:
    def test_dry_run_is_the_default_and_writes_nothing(self, tmp_path):
        """⚠️ 数据迁移的默认值必须是「不动」。

        这条守的不是某个 bug,是**默认值本身** —— 一个默认会改库的工具,
        迟早会被人不带参数地跑一次。
        """
        p = _db(tmp_path, [(_LG, "2026-07-22", _OLD, "FC Zurich", "t1")])
        assert m.main(["--db", str(p)]) == 0
        assert _dump(p) == [(_LG, _OLD, "FC Zurich")], "dry-run 改了库"

    def test_apply_rewrites_both_sides(self, tmp_path):
        """同一场两边都在别名表里 —— 实测真库 87 个槽位分布在 78 行,
        差的 9 行正是这种。只改一边就会漏。"""
        p = _db(tmp_path, [(_LG, "2026-07-22", _OLD, _OLD2, "t1")])
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == [(_LG, _NEW, _NEW2)]

    def test_league_column_normalised_too(self, tmp_path):
        """`canonical_team` 按 (联赛, 队名) 查表 ⇒ league 还写着 sport_key 时
        队名归一整个落空。两列必须一起处理,且 league 在先。"""
        p = _db(tmp_path, [("soccer_switzerland_superleague", "2026-07-22", _OLD, "FC Sion", "t1")])
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == [(_LG, _NEW, "FC Sion")]

    def test_collision_is_skipped_not_merged(self, tmp_path):
        """⚠️ 表上**没有 UNIQUE 索引** ⇒ 撞车的 UPDATE 不会报错,会静默多一行重复。

        遇到就原样留着 + 打印,不合并不删除 —— 删数据不是这个工具该干的。
        """
        p = _db(tmp_path, [
            (_LG, "2026-07-22", _NEW, "FC Sion", "t1"),   # 已经是正典的行
            (_LG, "2026-07-22", _OLD, "FC Sion", "t1"),   # 改完会和上一行完全同键
        ])
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == [(_LG, _NEW, "FC Sion"), (_LG, _OLD, "FC Sion")], \
            "撞车行被改了 ⇒ 库里多了一条静默重复"

    def test_near_miss_is_not_a_collision(self, tmp_path):
        """只有**全键**相同才算撞车。captured_at 不同 = 两次快照,都该改。

        (不加这条,「撞车判据」写宽一档就会静默少改一批,而且看不出来。)
        """
        p = _db(tmp_path, [
            (_LG, "2026-07-22", _NEW, "FC Sion", "t1"),
            (_LG, "2026-07-22", _OLD, "FC Sion", "t2"),   # 同场不同时刻
        ])
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == [(_LG, _NEW, "FC Sion"), (_LG, _NEW, "FC Sion")]

    def test_idempotent(self, tmp_path):
        """跑第二遍必须 0 行待改 —— CLI 自己也会复查,这里从外面再钉一次。"""
        p = _db(tmp_path, [(_LG, "2026-07-22", _OLD, "FC Sion", "t1")])
        m.main(["--db", str(p), "--apply", "--no-backup"])
        before = _dump(p)
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == before

    def test_unknown_names_untouched(self, tmp_path):
        """表里没有的名字**原样留着,绝不猜** —— 同 canonical_team 的红线。"""
        p = _db(tmp_path, [(_LG, "2026-07-22", "Some New Club", "FC Sion", "t1")])
        assert m.main(["--db", str(p), "--apply", "--no-backup"]) == 0
        assert _dump(p) == [(_LG, "Some New Club", "FC Sion")]

    def test_apply_takes_a_backup(self, tmp_path):
        """--apply 自己备份,别指望人记得。备份必须是**改之前**的内容。"""
        p = _db(tmp_path, [(_LG, "2026-07-22", _OLD, "FC Sion", "t1")])
        assert m.main(["--db", str(p), "--apply"]) == 0
        baks = list(tmp_path.glob("o.db.bak-*-pre-name-backfill"))
        assert len(baks) == 1, f"没备份或备了多份:{baks}"
        assert _dump(baks[0]) == [(_LG, _OLD, "FC Sion")], "备份里是改**之后**的内容"
        assert _dump(p) == [(_LG, _NEW, "FC Sion")]

    def test_missing_db_is_an_error_not_a_silent_zero(self, tmp_path):
        """路径写错必须非零退出。返回 0 + 「改了 0 行」= 又一个「抓了空集也叫成功」。"""
        assert m.main(["--db", str(tmp_path / "nope.db")]) == 1

    def test_registered_in_pyproject(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        assert "nutmeg-backfill-odds-names" in (root / "pyproject.toml").read_text()

    def test_help_works(self):
        with pytest.raises(SystemExit) as exc:
            m.main(["--help"])
        assert exc.value.code == 0
