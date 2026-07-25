"""联赛标签漂移哨兵(2026-07-25)。

病史:`jingcai_sp` 有两个写入者、两套联赛词汇 —— `sporttery` 官方抓取写**中文
缩写**(韩职/瑞超/挪超…),`market_mode`(面板/手填)写 **EN 代码**
(KOR_K_LEAGUE_1/SWE_ALLSVENSKAN/…)。`canonical_league` 就是为这件事建的共享
读取层,设计正确(fail-open + 「新同义词观察到就加进表」)。

但**表会落后于现实**:2026-07-25 实测 9 对同名联赛里 5 对没映射
(挪超/NOR_ELITESERIEN、欧冠/UCL、欧罗巴/UEL、巴甲、美职)。后果是同一联赛在
CLV 账本的 per-league BHY-FDR 闸里算成**两个组** —— N 减半、t 值错、FDR 家族多
一个伪成员。而这道闸是记忆里写明的「唯一 money unlock」。

⚠️ 这个漂移**以前被撞见过一次**:`scripts/backfill_closing_gap.py` 里有个本地
`_ZH_TO_CODE`,注释写着「league_labels._EN_TO_CN 只覆盖前者,这里补全后者」——
有人踩到了,在脚本里本地补,**没修共享表**。正是「修共享 sink 别逐生产者打补丁」。

本测试就是那个没人建的哨兵:实盘库里只要出现「一个 ASCII 标签 + 一个 CJK 标签
指向同一联赛」而 canonical_league 合不拢,就红。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.data.league_labels import _EN_TO_CN, canonical_league

_DB = Path("data/v4_observation.db")


class TestKnownPairsCollapse:
    """2026-07-25 实测存在于库里的对 —— 逐条钉死,防回退。"""

    @pytest.mark.parametrize(("zh", "en"), [
        ("世界杯", "WC"), ("芬超", "FIN_VEIKKAUSLIIGA"),
        ("韩职", "KOR_K_LEAGUE_1"), ("瑞超", "SWE_ALLSVENSKAN"),
        # ↓ 07-25 补的 5 对
        ("挪超", "NOR_ELITESERIEN"), ("欧冠", "UCL"), ("欧罗巴", "UEL"),
        ("巴甲", "BRA_SERIE_A"), ("美职", "USA_MLS"),
    ])
    def test_pair_maps_to_one_group(self, zh, en):
        assert canonical_league(zh) == canonical_league(en), (
            f"{zh} 与 {en} 是同一联赛却分成两组 —— per-league FDR 闸会把它当两个成员")

    def test_canonical_form_is_the_chinese_abbrev(self):
        """规范形 = 竞彩中文缩写(库里占多数、账本也这么打印)。别反过来。"""
        assert canonical_league("UEL") == "欧罗巴"
        assert canonical_league("NOR_ELITESERIEN") == "挪超"

    def test_unmapped_label_passes_through(self):
        """fail-open 不能坏:没见过的标签原样返回,自成一组,绝不静默丢。"""
        assert canonical_league("ZZZ_MADE_UP") == "ZZZ_MADE_UP"
        assert canonical_league(None) == "(未标联赛)"
        assert canonical_league("  ") == "(未标联赛)"


@pytest.mark.skipif(not _DB.exists(), reason="无实盘库(CI)")
class TestLiveDriftDetector:
    def test_no_ascii_cjk_pair_left_unmapped(self):
        """漂移检测:库里每个 EN 代码,若它映射到的中文缩写**也**作为原始标签出现,
        两者必须已经合拢。合不拢 = 表落后了,把缺的对加进 _EN_TO_CN。

        (只看已知 EN 代码 → 不会误报「两个碰巧都存在的无关联赛」。)"""
        conn = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
        try:
            raw = {r[0] for r in conn.execute(
                "SELECT DISTINCT league FROM jingcai_sp WHERE league IS NOT NULL")}
        finally:
            conn.close()
        drift = []
        for label in sorted(raw):
            if not label.isascii():
                continue                      # 中文标签本身就是规范形
            cn = _EN_TO_CN.get(label)
            if cn is None:
                drift.append(f"{label}: 未在 _EN_TO_CN 注册 → 自成一组")
            elif canonical_league(cn) != canonical_league(label):
                drift.append(f"{label} vs {cn}: 注册了却合不拢")
        assert not drift, (
            "联赛标签漂移 —— 同一联赛被劈成多组,per-league FDR 闸会算错:\n  "
            + "\n  ".join(sorted(drift))
            + "\n把缺的对加进 apps/api/src/nutmeg/v4/data/league_labels.py 的 _EN_TO_CN")
