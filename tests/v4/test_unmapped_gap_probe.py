"""竞彩队名缺口曲线探针(2026-09-04 补上读者)。

## 病史:这份数据攒了 16 天,一个读者都没有

`logs/sporttery_unmapped_history.jsonl` 从 2026-08-20 起 append-only。当时**有意**
不写读者:阈值要先量节律,而那个文件一行都还没有 ⇒ 拍数大概率假红
(memory `measure-cadence-before-changing-a-guard`:①红得对吗 ②还要红多久 ③才谈重设计)。
2026-09-04 攒到 355 行 / 16 天,量出节律后才补。

## 阈值的依据(不是拍的)

    相邻两行间隔:中位 0.43h · p90 2.09h · p99 10.58h · **最大 11.83h**
    >12h 的间隔在 16 天里 **0 次**;完全没有行的日子 **0 天**
    仅 cron 行同样:最大 11.83h,>12h 0 次

⇒ 复用现成的 `_PROBE_BLIND_HOURS`(24h,原为配额探针失明设),**不发明第三个**:
24h ≈ 观测最大间隔的 2 倍 ⇒ 单个晚批迟到不误报,真死了一天内必响。

## 🚨 它在真实数据上**从没红过**(0/16 天)

所以「跑起来是绿的」不构成它在工作的证据(memory `hardcoded-guard-lists-rot`)。
本文件的存在理由就是**用合成 fixture 证明它会红**。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _probe(**kw):
    from nutmeg.v4.cli.data_freshness import check_unmapped_gap
    return check_unmapped_gap(**kw)


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "hist.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")
    return p


def _row(hours_ago: float, *, trigger: str = "cron",
         seen: list | None = None, names: list | None = None) -> dict:
    return {
        "t": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "trigger": trigger,
        "matches_seen": seen if seen is not None else [["英超", "2026-09-05", "周五001"]],
        "names": names or [],
        "rows_written": {"had": 3, "hhad": 3},
        "n_matches": len(seen) if seen is not None else 1,
    }


class TestStallAlarmActuallyFires:
    """🚨 这个报警在真实数据上从没红过 —— 这里用合成 fixture 逼它红。"""

    def test_fires_when_cron_rows_stop(self, tmp_path):
        p = _write(tmp_path, [_row(30), _row(40)])
        info, alarms = _probe(history_path=p, now=NOW)
        assert alarms, f"cron 停了 30h 却没报警;info={info}"
        assert "缺口曲线" in alarms[0]

    def test_quiet_just_below_the_line(self, tmp_path):
        """23h 不报 —— 否则每天早批稍晚一点就响,变成长明灯。"""
        p = _write(tmp_path, [_row(23), _row(30)])
        info, alarms = _probe(history_path=p, now=NOW)
        assert not alarms, f"23h 就报警了(红线 24h):{alarms}"
        # 🚨 防空洞:必须确认它真的跑到了年龄那一步
        assert any("最后一条" in x for x in info), f"没算年龄,上面那条是空洞的:{info}"

    def test_threshold_comes_from_the_shared_constant(self, tmp_path):
        """⭐ 红线必须**读** `_PROBE_BLIND_HOURS`,不是内联一个 24。

        常数一改,行为要跟着改;否则那是第三份手抄。
        """
        from nutmeg.v4.cli import data_freshness as df

        p = _write(tmp_path, [_row(20)])
        assert not _probe(history_path=p, now=NOW)[1], "20h 本不该报"
        old = df._PROBE_BLIND_HOURS
        try:
            df._PROBE_BLIND_HOURS = 12.0        # ← 只改常数
            assert _probe(history_path=p, now=NOW)[1], \
                "把红线调到 12h 后 20h 的行仍不报 —— 阈值不是从常数读的"
        finally:
            df._PROBE_BLIND_HOURS = old


class TestButtonRowsCannotMaskDeadCron:
    """🚨 承重。文件有两个写入源(实测 cron 220 / 手按 135)。

    cron 死掉而 owner 照常按 🎯 时,**文件仍在长** ⇒ 任何「最后一行多久前」的探针
    都会一路绿。那正是 `check_volume_cliff` 要守的「还在写但源塌了」那一类。
    """

    def test_recent_button_row_does_not_silence_a_dead_cron(self, tmp_path):
        p = _write(tmp_path, [_row(0.5, trigger="button"), _row(30, trigger="cron")])
        info, alarms = _probe(history_path=p, now=NOW)
        assert alarms, f"最新一行是 1 小时前(手按的)就不报了 —— 手按掩盖了 cron 死掉:{info}"
        assert "手按" in alarms[0] or "cron" in alarms[0]

    def test_all_button_no_cron_is_an_alarm(self, tmp_path):
        p = _write(tmp_path, [_row(1, trigger="button"), _row(2, trigger="button")])
        info, alarms = _probe(history_path=p, now=NOW)
        assert alarms, "一条 cron 行都没有却不报警"
        assert "cron" in alarms[0]


class TestDenominatorMustBeDeduped:
    """🚨 分母陷阱:`matches_seen` 是**每轮**的裸列表,跨轮求和会被在售时长加权。

    实测真实文件:去重分母 286,裸求和 11,144 ⇒ **放大 39×**。
    按它排「先补哪个联赛」会错位(90 天模拟:12 个联赛错 8.9 个)。
    """

    def test_same_match_across_rounds_counts_once(self, tmp_path):
        same = [["英超", "2026-09-05", "周五001"]]
        p = _write(tmp_path, [_row(h, seen=same) for h in (1, 2, 3, 4, 5)])
        info, _ = _probe(history_path=p, now=NOW)
        line = next(x for x in info if "去重场次" in x)
        assert "去重场次 1 " in line, f"5 轮同一场没去重:{line}"
        # ⭐ 同时必须把放大倍数印出来,否则读者会自己去裸求和
        assert "裸求和分母会是 5" in line and "放大 5×" in line, line

    def test_match_num_is_part_of_the_key(self, tmp_path):
        """⚠️ `(联赛, 日期)` **不是**唯一键 —— 实测 54.7% 的格子装不止一场。"""
        two = [["英超", "2026-09-05", "周五001"], ["英超", "2026-09-05", "周五002"]]
        p = _write(tmp_path, [_row(1, seen=two)])
        info, _ = _probe(history_path=p, now=NOW)
        line = next(x for x in info if "去重场次" in x)
        assert "去重场次 2 " in line, f"同联赛同日两场被并成一场(丢了场次号):{line}"

    def test_numerator_uses_the_same_key(self, tmp_path):
        """分子取 `names[2:5]`,和分母同一套键 —— 不同源就没法比。"""
        seen = [["沙职", "2026-09-05", "周五003"], ["英超", "2026-09-05", "周五001"]]
        nm = [["迪里耶", "胡巴", "沙职", "2026-09-05", "周五003", "h"]]
        p = _write(tmp_path, [_row(h, seen=seen, names=nm) for h in (1, 2, 3)])
        info, _ = _probe(history_path=p, now=NOW)
        line = next(x for x in info if "去重场次" in x)
        assert "去重场次 2 " in line and "未映射 1 " in line, line
        assert "50.00%" in line, f"率算错(应 1/2):{line}"

    def test_numerator_key_must_live_in_the_denominator_space(self):
        """🚨 分子必须和分母同一套键 —— 只比**个数**分辨不出换了键。

        空包弹实测:把 `m[2:5]`(联赛/日期/场次号)换成 `m[0:2]`(两个队名)后,
        计数完全相同,`未映射 1`/`50.00%` 两条断言原样通过。
        ⇒ 生产侧改成 `bad &= seen`(分子限制在分母人口里),这条测它:
        换了键 ⇒ 交集塌成 0 ⇒ 率变 0.00%,立刻可见。
        """
        from nutmeg.v4.cli.data_freshness import check_unmapped_gap
        import json as _j, tempfile
        seen = [["沙职", "2026-09-05", "周五003"], ["英超", "2026-09-05", "周五001"]]
        nm = [["迪里耶", "胡巴", "沙职", "2026-09-05", "周五003", "h"]]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            p.write_text(_j.dumps(_row(1, seen=seen, names=nm), ensure_ascii=False) + "\n",
                         encoding="utf-8")
            info, _ = check_unmapped_gap(history_path=p, now=NOW)
        line = next(x for x in info if "去重场次" in x)
        # 🚨 人口非平凡:分子必须真的非零,否则「交集非空」空洞为真
        assert "未映射 1 " in line, f"分子是 0,这条断言变空洞:{line}"
        assert "50.00%" in line, line

    def test_a_name_outside_the_seen_population_does_not_inflate_the_rate(self):
        """率不许 >100%:`names` 里出现分母没有的场次(跨窗残留)时不该计入。"""
        from nutmeg.v4.cli.data_freshness import check_unmapped_gap
        import json as _j, tempfile
        seen = [["英超", "2026-09-05", "周五001"]]
        nm = [["甲", "乙", "沙职", "2026-09-05", "周五003", "h"],
              ["丙", "丁", "日职", "2026-09-05", "周五009", "a"]]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            p.write_text(_j.dumps(_row(1, seen=seen, names=nm), ensure_ascii=False) + "\n",
                         encoding="utf-8")
            info, _ = check_unmapped_gap(history_path=p, now=NOW)
        line = next(x for x in info if "去重场次" in x)
        assert "去重场次 1 " in line and "未映射 0 " in line, \
            f"分母外的名字被计进了分子(率会 >100%):{line}"

    def test_rows_outside_the_lookback_window_are_excluded(self, tmp_path):
        """⚠️ `lookback_days` 必须真的裁窗 —— 否则「近 7 天」印的是全历史。

        空包弹实测:把窗口改成 99999 天,原有 fixture **一条都没红**(它们全在窗内)。
        这条造一个窗外的场次:它不许进分母。
        """
        recent = [["英超", "2026-09-05", "周五001"]]
        old = [["旧联赛", "2026-07-01", "周一001"], ["旧联赛", "2026-07-01", "周一002"]]
        p = _write(tmp_path, [_row(1, seen=recent), _row(24 * 30, seen=old)])
        info, alarms = _probe(history_path=p, now=NOW, lookback_days=7)
        line = next(x for x in info if "去重场次" in x)
        assert "去重场次 1 " in line, f"窗外的 2 场进了分母:{line}"
        # 🚨 人口非平凡:证明那 2 场**确实存在**,否则上面那条空洞为真
        wide = next(x for x in _probe(history_path=p, now=NOW, lookback_days=90)[0]
                    if "去重场次" in x)
        assert "去重场次 3 " in wide, f"放宽窗口也只有 1 场 —— 对照不成立:{wide}"


class TestRateIsReportedButNeverGated:
    """⛔ 率**不判闸**:它测「名字解不解得出」,不测「盘面有没有价」。

    实测 291 场「名字解出来了」里 10 场(3.4%)盘面零行 ⇒ 曲线变绿 ≠ 窟窿变小。
    而且人口太小:16 天去重后只有 5 场未映射,逐日率跳一格只要 2 场。
    """

    def test_hundred_percent_gap_still_produces_no_alarm(self, tmp_path):
        seen = [["沙职", "2026-09-05", "周五003"]]
        nm = [["迪里耶", "胡巴", "沙职", "2026-09-05", "周五003", "h"]]
        p = _write(tmp_path, [_row(1, seen=seen, names=nm)])
        info, alarms = _probe(history_path=p, now=NOW)
        # 🚨 防空洞:先证明它真的算出了 100%,否则「没报警」毫无意义
        assert any("100.00%" in x for x in info), f"没算出 100%:{info}"
        assert not alarms, f"率进了 alarms —— 用词典闸冒充盘面闸:{alarms}"

    def test_it_says_what_it_does_not_measure(self, tmp_path):
        p = _write(tmp_path, [_row(1)])
        info, _ = _probe(history_path=p, now=NOW)
        blob = " ".join(info)
        assert "jc_home is null" in blob, "没说盘面验收该看什么"
        assert "≠" in blob, "没说清「名字解出来」和「行落库」「盘面有价」不是一回事"


class TestMissingDataIsNotSilence:
    """⛔ 「没有曲线」不许读成「没有缺口」—— 同涓流探针那次 4,751 场的教训。"""

    @pytest.mark.parametrize("kind", ["missing", "empty", "garbage"])
    def test_no_usable_rows_alarms(self, tmp_path, kind):
        p = tmp_path / "hist.jsonl"
        if kind == "empty":
            p.write_text("", encoding="utf-8")
        elif kind == "garbage":
            p.write_text("not json\n{oops\n", encoding="utf-8")
        info, alarms = _probe(history_path=p, now=NOW)
        assert alarms, f"{kind}: 静默了"
        assert "别把" in alarms[0] or "空的" in alarms[0]


class TestWiredIntoTheSentinel:
    """规则对了但没接线 = 哨兵不会因为它非零退出。

    ⛔ 库必须是**真的、且全绿的**合成库 —— 复用 `test_data_freshness` 的
    `_mk_db`/`_all_today`,不另造一套。
    ⚠️ 第一版我传了一个不存在的路径,`main` 在「观测库不存在」那一步就
    `return 1` 了 ⇒ `rc == 1` **是对的但理由是错的**(经典的对照不成立)。
    所以下面每条都先断言「不动它的时候是 0」,再断言「动了它变 1」。
    """

    _ARGS = ("--today", "2026-06-17", "--no-quota", "--no-supply", "--no-trickle")

    def _green_db(self, tmp_path):
        from .test_data_freshness import _all_today, _mk_db
        return _mk_db(tmp_path, _all_today())

    def test_alarm_drives_nonzero_exit_and_names_its_kind(self, monkeypatch, capsys, tmp_path):
        """⭐ 一条测试盖住全部接线腿(调用点/报告/类别行/退出码)。"""
        from nutmeg.v4.cli import data_freshness as df

        db = self._green_db(tmp_path)
        # 🚨 对照:不动缺口曲线时必须是 0,否则下面的 1 说明不了任何事
        monkeypatch.setattr(df, "check_unmapped_gap", lambda **kw: ([], []))
        assert df.main(["--db", str(db), *self._ARGS]) == 0, \
            "对照不成立 —— 基线就不是绿的:\n" + capsys.readouterr().out[-800:]
        capsys.readouterr()

        monkeypatch.setattr(df, "check_unmapped_gap",
                            lambda **kw: ([], ["合成:缺口曲线停更"]))
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert rc == 1, "缺口曲线报警没有驱动非零退出"
        assert "合成:缺口曲线停更" in out, "报警没进报告"
        assert "缺口曲线停更" in out.split("报警类别: ")[-1], "类别行没点名它"

    def test_info_reaches_the_report_even_without_an_alarm(self, monkeypatch, capsys, tmp_path):
        """全绿那轮也要能看见它 —— 否则「它在跑吗」无从判断。"""
        from nutmeg.v4.cli import data_freshness as df

        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_unmapped_gap",
                            lambda **kw: (["合成:曲线 123 行"], []))
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert rc == 0 and "合成:曲线 123 行" in out, out[-600:]

    def test_probe_crash_becomes_an_alarm_not_silence(self, monkeypatch, capsys, tmp_path):
        """探针自己炸了必须变成报警 —— 否则「没检查」和「检查过没事」同形。"""
        from nutmeg.v4.cli import data_freshness as df

        def _boom(**kw):
            raise RuntimeError("boom")

        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_unmapped_gap", _boom)
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert rc == 1 and "探针自己炸了" in out, out[-600:]
