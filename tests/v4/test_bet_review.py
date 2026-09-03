"""`nutmeg-bet-review` —— 手工投注复盘的承重契约。

这个工具的价值在于**它印什么、拒绝印什么**,所以测试钉的是那几条:
读表不吞行 · 腿型映射对 · 口径同源 · 小切片不给 ROI · 头条是期望vs实得。
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.cli import bet_review as R

SRC = Path("apps/api/src/nutmeg/v4/cli/bet_review.py")


def _sheet(tmp_path: Path, rows: list[str]) -> Path:
    p = tmp_path / "b.csv"
    p.write_text("日期,联赛,赛事,投注,结果\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def _db(tmp_path: Path, *, line=None, ft=0, hco=None) -> str:
    db = str(tmp_path / "obs.db")
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE jingcai_sp (match_date TEXT, market TEXT, home_team TEXT,
        away_team TEXT, jc_home REAL, jc_draw REAL, jc_away REAL, handicap_home INT,
        ft_outcome INT, hc_outcome INT, psc_home REAL, psc_draw REAL, psc_away REAL,
        ou_line REAL, psc_over REAL, psc_under REAL)""")
    c.execute("""CREATE TABLE jingcai_vote (match_date TEXT, home_zh TEXT, away_zh TEXT,
        home_team TEXT, away_team TEXT, jc_home REAL, jc_draw REAL, jc_away REAL,
        handicap_home INT, ft_outcome INT)""")
    c.execute("INSERT INTO jingcai_sp VALUES ('2026-08-22','had','Burnley','Boro',"
              "2.0,3.4,3.6,NULL,?,NULL,1.95,3.5,3.7,2.5,1.9,1.9)", (ft,))
    c.execute("INSERT INTO jingcai_sp VALUES ('2026-08-22','hhad','Burnley','Boro',"
              "1.5,4.0,5.0,-1,?,?,1.95,3.5,3.7,2.5,1.9,1.9)", (ft, hco))
    c.execute("INSERT INTO jingcai_vote VALUES ('2026-08-22','伯恩利','米德尔斯堡',"
              "'Burnley','Boro',2.0,3.4,3.6,NULL,?)", (ft,))
    c.execute("INSERT INTO jingcai_vote VALUES ('2026-08-22','伯恩利','米德尔斯堡',"
              "'Burnley','Boro',1.5,4.0,5.0,-1,?)", (ft,))
    c.commit(); c.close()
    return db


class TestReadingNeverSwallowsRows:
    """🚨 读不了的行必须**出现在输出里**,不能静默消失 —— 一注就是一笔钱。"""

    def test_unknown_bet_label_is_reported_not_dropped(self, tmp_path, capsys):
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯堡,大小球,对"])
        recs, gripes = R._parse(R._read(s))
        assert recs == []
        assert gripes and "认不出" in gripes[0], "认不出的标签被静默丢了"

    def test_missing_separator_is_reported(self, tmp_path):
        s = _sheet(tmp_path, ["2026-08-22,西甲,甲队乙队,主胜,错"])
        recs, gripes = R._parse(R._read(s))
        assert recs == [] and any("分隔符" in g for g in gripes)

    def test_date_is_forward_filled(self, tmp_path):
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯堡,主胜,对",
                              ",英冠,甲-乙,客胜,错"])
        recs, _ = R._parse(R._read(s))
        assert len(recs) == 2
        assert recs[1]["date"] == dt.date(2026, 8, 22), "日期没有向下填充"


class TestLegMapping:
    @pytest.mark.parametrize("bet,market,leg", [
        ("主胜", "had", 0), ("平", "had", 1), ("客胜", "had", 2),
        ("主让胜", "hhad", 0), ("让胜", "hhad", 0),
        ("主让负", "hhad", 2), ("让负", "hhad", 2),
    ])
    def test_labels(self, bet, market, leg):
        assert R._BET_LEG[bet] == (market, leg)

    def test_every_label_has_a_display_name(self):
        """⚠️ 反向表必须覆盖正向表 —— 否则对账那行会 KeyError 崩在最需要它的时候。"""
        for mk, lg in R._BET_LEG.values():
            assert (mk, lg) in R._LEG_NAME


class TestCalibrationIsNotReimplemented:
    """⛔ 概率一律 import 生产模块。复刻会在生产改口径时静默分叉。"""

    def test_no_local_probability_math(self):
        body = re.sub(r'""".*?"""', "", SRC.read_text(encoding="utf-8"), flags=re.S)
        # ⚠️ 只列**概率算法**的痕迹。第一版把 `median(` 也列进来了,而那是赔率对照
        #    用的显示统计 —— 断言写错了对象,当场假红。
        for tok in ("1.0 / float(", "def devig", "def _devig", "def implied_handicap"):
            assert tok not in body, f"自己实现了 {tok!r} ⇒ 口径会分叉"
        # 人口非平凡:这几个生产符号必须真的被 import,否则上面全是空洞为真
        for must in ("from nutmeg.v4.model.devig import devig_1x2",
                     "implied_handicap_lines", "onex_leg_lower_bounds"):
            assert must in body, f"没 import {must!r} ⇒ 这条断言在测一个空文件"

    def test_handicap_uses_the_serving_calibration(self):
        """🚨 让球必须 `c1=True` **且传 league** —— 只传一半会静默降级成未校准。"""
        body = SRC.read_text(encoding="utf-8")
        # ⚠️ 非贪婪正则会停在第一个 `)`(`A[5] or 2.5` 那里),抓不到后面的 c1
        #    —— 第一版就这么假红。改成取调用起点后的一个窗口。
        i = body.find("implied_handicap_lines(")
        assert i > 0, "没调生产的让球网格"
        call = body[i:i + 300]
        assert "c1=True" in call and "league=" in call, (
            f"让球用的不是服务口径(只传一半会静默降级成未校准):{call[:160]}")


class TestReportDiscipline:
    def test_small_slices_get_no_roi(self, tmp_path, capsys):
        """⛔ 相邻档符号相反、量级相同,是噪声的指纹 —— 小切片不许给 ROI。"""
        db = _db(tmp_path)
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯堡,主胜,对"])
        R.main([str(s), "--db", db])
        out = capsys.readouterr().out
        assert "N 太小不给 ROI" in out
        assert R._MIN_SLICE >= 20

    def test_headline_is_expected_vs_realised(self, tmp_path, capsys):
        db = _db(tmp_path)
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯堡,主胜,对"])
        R.main([str(s), "--db", db])
        out = capsys.readouterr().out
        assert "期望 vs 实得" in out and "运气那一部分" in out
        assert "自举 CI" in out, "实得必须带 CI —— 没有 CI 的 ROI 会被当成结论"
        assert "evLo(生产真正用的)" in out

    def test_record_vs_db_disagreement_is_surfaced(self, tmp_path, capsys):
        """记录说赢、库里说输 ⇒ 必须**列出来让人判**,不替人选一边。"""
        db = _db(tmp_path, ft=2)          # 库里:客胜
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯堡,主胜,对"])
        R.main([str(s), "--db", db])
        out = capsys.readouterr().out
        assert "不一致 1" in out and "没替你判" in out
        # ⚠️ 光断言计数不够 —— 空包弹「把逐条列表清空」照样绿(实测溜过一次)。
        #    必须断言那一注**真的被印出来**,连同两边的说法。
        assert "伯恩利-米德尔斯堡" in out.split("【对账】")[1], "不一致的注没被列出来"
        assert "客胜" in out.split("【对账】")[1], "没印出库里的说法,人无从判"

    def test_fuzzy_joins_are_always_printed(self, tmp_path, capsys):
        """「长得像」是零证据 ⇒ 每一条模糊连都要人眼核对。"""
        db = _db(tmp_path)
        s = _sheet(tmp_path, ["2026-08-22,英冠,伯恩利-米德尔斯保,主胜,对"])  # 末字不同
        R.main([str(s), "--db", db])
        out = capsys.readouterr().out
        assert "请人眼核对" in out and "伯恩利-米德尔斯保" in out
