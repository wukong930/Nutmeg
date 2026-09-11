"""📚 训练源树**有没有当前赛季** —— mtime 探针结构上看不见的维度(2026-09-11)。

## 病史

源树停在 `2526`,**整个 `2627` 目录不存在**;上游 13/13 个 div 都有数据、共 503 场。
而体检当时报「训练源树: 最新 CSV 2026-07-15 · 58d(红线 120d)」⇒ **绿的**。

⭐ mtime 量的是「**多久没进新文件**」,不是「**最新赛季在不在**」——
换季时这两件事分家:上赛季的补录还在写(mtime 新鲜),新赛季一个文件都没拉过。
⛔ 而 `ingest_football_data` **没有 cron**(当时),没人碰就永远停在上赛季。

## 🚨 判据里没有拍出来的常数

第一版想用「源树最新比赛日落后今天 N 天」。实测:近 3 年最大空窗 **68 天**(今夏),
而这次缺口是 **103 天** —— 只差 35 天,没有安全边际;且 `japan/JPN.csv` 已停更 9 个月、
不再填夏窗 ⇒ 往后空窗只会更长。**放弃。**

⇒ 改成**直接问上游**(用生产的 `fetch_one`):本地缺哪个 div 就确认上游有没有。
休赛期上游 404 ⇒ **天然不误报**,不需要任何日期闸。

⭐ 且**健康时零网络开销** —— 13 个 div 都在就一个请求都不发。本文件钉死这条。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from nutmeg.v4.cli import data_freshness as df

NOW = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.UTC)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """造一棵源树;`calls` 记录所有向上游发的请求(用来钉「零网络开销」)。"""
    from nutmeg.v4.cli import ingest_football_data as ifd

    calls: list[tuple[str, str]] = []
    root = tmp_path / "football_data_co_uk"
    (root / "europe" / "2627").mkdir(parents=True)

    def write(div: str, rows: int) -> None:
        body = "Div,Date,HomeTeam,AwayTeam\n" + "".join(
            f"{div},01/01/2027,A,B\n" for _ in range(rows))
        (root / "europe" / "2627" / f"{div}.csv").write_text(body, encoding="utf-8")

    for d in ifd.TRAINED_DIVS:
        write(d, 30)

    def fake_fetch(season, div, *, timeout=30.0):
        calls.append((season, div))
        return (b"Div,Date\nE0,01/01/2027\n" * 1, "ok")

    monkeypatch.setattr(ifd, "fetch_one", fake_fetch)
    return type("T", (), {"root": root, "calls": calls, "write": staticmethod(write),
                          "divs": ifd.TRAINED_DIVS})()


class TestHealthyCostsNothing:
    def test_all_divs_present_no_alarm(self, tree):
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert not alarms, alarms
        assert any("13/13" in x for x in info), info

    def test_zero_upstream_requests_when_healthy(self, tree):
        """⭐ 承重:健康时**一个请求都不发**。

        这是本探针能进 2×/天 哨兵的全部理由。没有这条,下一个人「顺手」改成
        每次都问上游,就变成每天 26 次外部请求而没人注意。
        """
        df.check_training_source_season(tree.root, now=NOW)
        assert tree.calls == [], f"健康时发了 {len(tree.calls)} 个上游请求:{tree.calls}"


class TestTheGapIsCaught:
    def test_missing_div_that_upstream_has_alarms(self, tree, monkeypatch):
        (tree.root / "europe" / "2627" / "E0.csv").unlink()
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert alarms, f"缺了 E0 而上游有,却没报警;info={info}"
        assert "E0" in alarms[0] and "2627" in alarms[0]
        assert tree.calls == [("2627", "E0")], f"只该为缺的那个 div 问上游:{tree.calls}"

    def test_whole_season_missing_alarms(self, tree):
        for f in (tree.root / "europe" / "2627").glob("*.csv"):
            f.unlink()
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert alarms and "13" in alarms[0], alarms
        assert len(tree.calls) == 13

    def test_season_dir_absent_entirely(self, tree):
        """🚨 这才是 2026-09-11 的真实形态:**目录压根不存在**(不是文件空)。"""
        import shutil
        shutil.rmtree(tree.root / "europe" / "2627")
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert alarms, f"整个赛季目录没了却不报警;info={info}"

    def test_europe_root_missing_is_an_alarm_not_silence(self, tree):
        import shutil
        shutil.rmtree(tree.root / "europe")
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert alarms and "别读成" in alarms[0], alarms


class TestOffSeasonDoesNotCryWolf:
    """⛔ 休赛期上游本来就 404 —— 那不是缺口。没有这条,每年 7 月都会假红。"""

    def test_upstream_404_is_not_a_gap(self, tree, monkeypatch):
        from nutmeg.v4.cli import ingest_football_data as ifd

        monkeypatch.setattr(ifd, "fetch_one",
                            lambda s, d, **k: (tree.calls.append((s, d)), (None, "· 尚未发布(404)"))[1])
        for f in (tree.root / "europe" / "2627").glob("*.csv"):
            f.unlink()
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        # 🚨 人口非平凡:先证明它**确实**去问了上游,否则「没报警」空洞为真
        assert len(tree.calls) == 13, f"没问上游就断言不报警:{tree.calls}"
        assert not alarms, f"上游 404 却报警了:{alarms}"
        assert any("上游也还没发布" in x for x in info), info

    def test_network_failure_says_unchecked_not_zero(self, tree, monkeypatch):
        """⚠️「查不了」和「没缺口」必须分开 —— 同涓流探针传错库那条。"""
        from nutmeg.v4.cli import ingest_football_data as ifd

        monkeypatch.setattr(ifd, "fetch_one",
                            lambda s, d, **k: (_ for _ in ()).throw(OSError("boom")))
        (tree.root / "europe" / "2627" / "E0.csv").unlink()
        info, alarms = df.check_training_source_season(tree.root, now=NOW)
        assert not alarms, "网络失败不该报成缺口"
        assert any("未查" in x for x in info), f"没说清是「未查」:{info}"


class TestWiredIntoTheSentinel:
    _ARGS = ("--today", "2026-06-17", "--no-quota", "--no-supply", "--no-trickle", "--no-gapcurve")

    def _green_db(self, tmp_path):
        from .test_data_freshness import _all_today, _mk_db
        return _mk_db(tmp_path, _all_today())

    def test_alarm_drives_nonzero_exit_and_names_its_kind(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_training_source_season", lambda **k: ([], []))
        assert df.main(["--db", str(db), *self._ARGS]) == 0, \
            "对照不成立 —— 基线就不是绿的:\n" + capsys.readouterr().out[-800:]
        capsys.readouterr()
        monkeypatch.setattr(df, "check_training_source_season",
                            lambda **k: ([], ["合成:训练源树缺赛季"]))
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert rc == 1, "没有驱动非零退出"
        assert "合成:训练源树缺赛季" in out
        assert "训练源树缺赛季" in out.split("报警类别: ")[-1], "类别行没点名它"

    def test_probe_crash_becomes_an_alarm(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)

        def boom(**k):
            raise RuntimeError("boom")

        monkeypatch.setattr(df, "check_training_source_season", boom)
        rc = df.main(["--db", str(db), *self._ARGS])
        assert rc == 1 and "探针自己炸了" in capsys.readouterr().out

    def test_no_season_flag_skips_it(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_training_source_season",
                            lambda **k: ([], ["合成:不该出现"]))
        rc = df.main(["--db", str(db), *self._ARGS, "--no-season"])
        assert rc == 0 and "合成:不该出现" not in capsys.readouterr().out
