"""逐场【赛前】Elo 回填的解析契约(nutmeg-ingest-eloratings-history)。

这些测试守的是一个**沉默型**错误:源文件给的是【赛后】Elo,谁要是直接拿来当特征,
walk-forward 就会泄漏本场结果 —— 而且不会报错、不会崩,只会让模型看起来变强。
所以下面用真实数据行钉死 `pre = post − change` 这条还原公式。

真实样本取自 https://www.eloratings.net/2018_results.tsv(2026-07-15 实抓)。
"""
from __future__ import annotations

import pandas as pd
import pytest

from nutmeg.v4.cli.ingest_eloratings_history import parse_results_tsv

# 真实行。法国 2018 首场:3/23 主场 2:3 负哥伦比亚,本场 −14,主队列(赛后)= 1974。
# 独立锚点:2018_start.tsv 里 FR = 1988(= 2017 年末)→ 1974 − (−14) = 1988 ✅
_FR_FIRST = "2018\t03\t23\tFR\tCO\t2\t3\tF\tFR\t−14\t1974\t1940\t0\t+3\t7\t13"
# 2018 决赛:法国 4:2 克罗地亚 @ 俄罗斯,本场 +30,赛后 2125/1942 → 赛前 2095/1972
_FR_FINAL = "2018\t07\t15\tFR\tHR\t4\t2\tWC\tRU\t30\t2125\t1942\t+1\t−2\t1\t7"
_GULF = "2018\t01\t02\tIQ\tAE\t0\t0\tGLF\tKW\t-1\t1571\t1564\t0\t+2\t67\t69"


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return parse_results_tsv("\n".join([_GULF, _FR_FIRST, _FR_FINAL]), 2018)


class TestPreMatchEloRecovery:
    def test_recovers_pre_match_elo_not_post(self, df: pd.DataFrame):
        """核心契约:落盘的 elo_*_pre 必须是【赛前】值,不是源文件里的赛后值。"""
        final = df[df.date == "2018-07-15"].iloc[0]
        assert final.home_elo_post == 2125          # 源给的(赛后 = 含夺冠涨幅)
        assert final.home_elo_pre == 2095           # 2125 − 30 = 赛前 ✅ 零泄漏
        assert final.away_elo_pre == 1972           # 1942 + 30(Elo 零和 → 客队取反)

    def test_first_match_anchors_to_independent_year_start(self, df: pd.DataFrame):
        """定性依据:法国 2018 首场的赛前值必须等于 2018_start.tsv 的 FR=1988。

        这是唯一能区分「赛前 vs 赛后」的独立证据 —— 1974(源里的值)不等于 1988,
        而 1974−(−14)=1988 等于。别把这条删了,它是整条还原链的锚。
        """
        first = df[df.date == "2018-03-23"].iloc[0]
        assert first.home_elo_post == 1974
        assert first.home_elo_pre == 1988

    def test_handles_unicode_minus(self, df: pd.DataFrame):
        """eloratings 用 U+2212(−)而不是 ASCII '-';float() 直接吃会炸整行。"""
        first = df[df.date == "2018-03-23"].iloc[0]
        assert first.elo_change == -14.0            # 源里写的是 '−14'
        gulf = df[df.date == "2018-01-02"].iloc[0]
        assert gulf.elo_change == -1.0              # 这行用的是 ASCII '-',两种都得吃


class TestSchemaContract:
    def test_parses_all_real_rows(self, df: pd.DataFrame):
        """3 行真实数据必须全解析出来 —— 0 行是这个模块最危险的失败模式。

        `ingest_eloratings.parse_world_tsv` 喂年份档案就会【静默返回 0 行】(年份文件
        多一个前导涨跌列),0 行不报错、只是数据凭空消失。这条守住列位没搞错。
        """
        assert len(df) == 3

    def test_fields_match_known_history(self, df: pd.DataFrame):
        final = df[df.date == "2018-07-15"].iloc[0]
        assert (final.home_code, final.away_code) == ("FR", "HR")
        assert (final.home_goals, final.away_goals) == (4, 2)   # 史实比分
        assert final.tournament == "WC"
        assert final.venue_code == "RU"                          # 2018 世界杯在俄罗斯
        assert final.season == 2018

    def test_skips_junk_rows_without_raising(self):
        """源档案偶有空行/残行 → 整行跳过,绝不抛异常(抓一年炸一年)。"""
        out = parse_results_tsv("\n".join(["", "垃圾行", "a\tb\tc", _FR_FINAL]), 2018)
        assert len(out) == 1
