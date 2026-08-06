"""nutmeg-harvest-team-zh 的行为测试 —— 建真库、跑真函数、读真文件。

盯的是会让这个工具变危险的事:
  ① 默认不写(它改的是**源码**,比改库还险);
  ② 「词典已有这支队」必须是**语义**判断(大小写/重音/法定形式记号/别名),
     而且判定必须发生在**运行时那条路**上,不是只活在测试里;
  ③ 判成已有 ⇒ 只打印,永不自动写;
  ④ 一名多译不选赢家;
  ⑤ 「没找到」和「没去看」不能长一样 —— 这条是涓流常量 END 事故买回来的;
  ⑥ 写盘要么全成要么原样 —— 半截的 team_name_zh.py 会让整个服务起不来。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nutmeg.v4.cli import harvest_team_zh as m

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "apps" / "api" / "src"
LIVE_DICT = SRC_ROOT / "nutmeg" / "v4" / "data" / "team_name_zh.py"

# 一份最小但**结构真实**的词典文件:同样的 TEAM_NAME_ZH 组装方式 + 同样的收割块
# 标记。写侧只认标记,所以这个替身走的是和线上文件完全一样的读/改/写路径。
_FAKE_DICT = '''"""fake dict for tests."""
from __future__ import annotations

from typing import Dict

_BASE: Dict[str, str] = {
    "Arsenal": "阿森纳",
    "FC Seoul": "首尔",
}
TEAM_NAME_ZH: Dict[str, str] = {}
TEAM_NAME_ZH.update(_BASE)

# HARVEST-BEGIN
_JINGCAI_VOTE_HARVEST: Dict[str, str] = {
}
# HARVEST-END
for _en, _zh in _JINGCAI_VOTE_HARVEST.items():
    TEAM_NAME_ZH.setdefault(_en, _zh)
'''


def _dict_file(tmp_path: Path, text: str = _FAKE_DICT) -> Path:
    p = tmp_path / "team_name_zh.py"
    p.write_text(text, encoding="utf-8")
    return p


def _strays(root: Path) -> list[str]:
    """写侧临时产物的**递归**清点。

    ⚠️ 非递归 `iterdir()` 曾让这些断言变成假绿:复核用的子进程 import 那个
    `.harvest-tmp-*.py` 时,会在**下一层** `__pycache__/` 里留一个同名 `.pyc`,
    而 `_atomic_write` 的 `finally` 只 unlink 得掉 `.py`。断言的措辞
    (「留下了临时文件」)比它真正看得见的范围强 —— 同族:「检查的前提没人检查」。
    """
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if "harvest-tmp" in p.name)


def _db(tmp_path: Path, rows: list[tuple], *, table: str = "jingcai_vote") -> Path:
    """rows = (home_team, away_team, home_zh, away_zh)。列名照抄真表。"""
    import sqlite3
    p = tmp_path / "o.db"
    c = sqlite3.connect(p)
    c.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, match_date TEXT, "
              "home_zh TEXT NOT NULL, away_zh TEXT NOT NULL, "
              "home_team TEXT, away_team TEXT, pool_code TEXT)")
    c.executemany(
        f"INSERT INTO {table} (match_date, home_team, away_team, home_zh, away_zh, "
        "pool_code) VALUES ('2026-08-06',?,?,?,?,'HAD')", rows)
    c.commit()
    c.close()
    return p


# ---------- ① 默认不写 ---------------------------------------------------

class TestDryRunDefault:
    def test_default_run_does_not_touch_the_dict_file(self, tmp_path, capsys):
        """⚠️ 这个工具改的是**源码**。一个默认会改源码的工具,迟早会被人
        不带参数跑一次,然后 git diff 里冒出没人要的条目。"""
        d = _dict_file(tmp_path)
        before = d.read_text(encoding="utf-8")
        db = _db(tmp_path, [("SC Freiburg", "VfL Bochum", "弗赖堡", "波鸿")])

        assert m.main(["--db", str(db), "--dict-path", str(d)]) == 0

        assert d.read_text(encoding="utf-8") == before, "dry-run 改了词典文件"
        assert "dry-run" in capsys.readouterr().out

    def test_apply_writes_the_new_entries(self, tmp_path):
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("SC Freiburg", "VfL Bochum", "弗赖堡", "波鸿")])

        assert m.main(["--db", str(db), "--dict-path", str(d), "--apply"]) == 0

        after = m.read_dict_file(d)
        assert after["SC Freiburg"] == "弗赖堡"
        assert after["VfL Bochum"] == "波鸿"
        assert after["Arsenal"] == "阿森纳", "--apply 碰坏了别的块"

    def test_apply_twice_is_a_noop(self, tmp_path):
        """幂等:第二次跑,那些名字已经在词典里了 ⇒ 变成 agree,不再是 new。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("SC Freiburg", "VfL Bochum", "弗赖堡", "波鸿")])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        once = d.read_text(encoding="utf-8")

        assert m.main(["--db", str(db), "--dict-path", str(d), "--apply"]) == 0
        assert d.read_text(encoding="utf-8") == once, "第二次 --apply 又改了文件"

    def test_written_file_still_imports_and_is_valid_python(self, tmp_path):
        """渲染坏了会让整个 API 起不来 —— 所以写完必须还能真加载。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("1. FC Köln", "Estac Troyes", "科隆", "特鲁瓦")])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        assert m.read_dict_file(d)["1. FC Köln"] == "科隆"

    def test_a_write_that_did_not_take_is_reported_not_swallowed(self, tmp_path, capsys,
                                                                 monkeypatch):
        """⭐ 写后幂等复查:重读文件、把刚写的那批再判一次,还判为「新」就退 1。

        `test_apply_twice_is_a_noop` 比的是**文件字节**,写侧根本没动文件时它照绿
        —— 那条分支之前谁都没走到。这里让写入器**报成功但什么也没写**(下游过滤、
        权限、写到了别的路径……都是这个形状),复查必须把它喊出来,而不是让
        「✅ 已写入 2 条」成为最后一句话。
        """
        d = _dict_file(tmp_path)
        before = d.read_text(encoding="utf-8")
        db = _db(tmp_path, [("SC Freiburg", "VfL Bochum", "弗赖堡", "波鸿")])

        calls: list[int] = []

        def _lying_writer(path, new):          # noqa: ANN001 — 测试替身
            calls.append(len(new))
            return len(new)                    # 报「写了 N 条」,一个字节也没落盘

        monkeypatch.setattr(m, "apply_new_entries", _lying_writer)
        rc = m.main(["--db", str(db), "--dict-path", str(d), "--apply"])

        assert calls == [2], f"没走到写入路径,这条测的不是复查分支:{calls}"
        assert d.read_text(encoding="utf-8") == before, "替身居然真写了,前提坏了"
        out = capsys.readouterr().out
        assert "✅ 已写入" in out, "先确认它确实报了成功 —— 这正是复查要拆穿的那句"
        assert "写入不是幂等的" in out, "写了个寂寞,复查却没吭声"
        assert rc == 1, f"复查发现没落地,退出码必须非 0,实际 {rc}"


# ---------- ② 「词典已有这支队」是语义判断,且判定在运行时那条路上 -------

class TestSameTeamIsJudgedSemantically:
    """🚨 首版的病:`en not in known`(精确键)。

    竞彩侧的英文名走 `zh_to_canonical`,吐的是**盘面拼法**(`SC Freiburg` /
    `PAU` / `Fortuna Düsseldorf`),词典存的是清洗过的短名 ⇒ 精确键必然对不上 ⇒
    同一支队被当全新队写进去,报告还打「⚠️ 与词典冲突 0」。
    """

    def test_af_spelling_of_a_known_club_is_a_conflict_not_a_new_key(self, tmp_path):
        """`_EN_OVERRIDES` 反查臂:词典有 `Freiburg`,feed 给 `SC Freiburg`。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Freiburg": "弗赖堡",'))
        db = _db(tmp_path, [("SC Freiburg", "Arsenal", "弗赖堡FC", "阿森纳")])

        rep = m.harvest(db, m.read_dict_file(d))

        assert "SC Freiburg" not in rep.new, "盘面拼法被当成了一支全新的队"
        assert rep.conflicts["SC Freiburg"] == ("弗赖堡", "弗赖堡FC")
        assert "_EN_OVERRIDES" in rep.matched_how["SC Freiburg"]

    def test_accent_only_difference_is_the_same_team(self, tmp_path):
        """折叠臂 · 重音:`Fortuna Düsseldorf` vs 词典 `Fortuna Dusseldorf`。
        首版就是在这条上写出了「杜塞多夫 / 杜塞尔多夫」两个名字。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",',
            '"Arsenal": "阿森纳",\n    "Fortuna Dusseldorf": "杜塞尔多夫",'))
        db = _db(tmp_path, [("Fortuna Düsseldorf", "Arsenal", "杜塞多夫", "阿森纳")])

        rep = m.harvest(db, m.read_dict_file(d))

        assert "Fortuna Düsseldorf" not in rep.new
        assert rep.conflicts["Fortuna Düsseldorf"] == ("杜塞尔多夫", "杜塞多夫")

    def test_case_only_difference_is_the_same_team(self, tmp_path):
        """折叠臂 · 大小写:`PAU` vs 词典 `Pau`(AF 的 ALL-CAPS 异常)。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Pau": "波城",'))
        db = _db(tmp_path, [("PAU", "Arsenal", "波城FC", "阿森纳")])

        rep = m.harvest(db, m.read_dict_file(d))

        assert "PAU" not in rep.new
        assert rep.conflicts["PAU"] == ("波城", "波城FC")

    def test_legal_form_token_difference_is_the_same_team(self, tmp_path):
        """折叠臂 · 法定形式记号 + 成立年份:`FC Schalke 04` vs 词典 `Schalke`。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Schalke": "沙尔克 04",'))
        db = _db(tmp_path, [("FC Schalke 04", "Arsenal", "沙尔克04", "阿森纳")])

        rep = m.harvest(db, m.read_dict_file(d))

        assert "FC Schalke 04" not in rep.new
        assert rep.conflicts["FC Schalke 04"] == ("沙尔克 04", "沙尔克04")

    def test_same_team_same_chinese_is_an_alias_not_a_conflict(self, tmp_path):
        """中文一致的别名拼法**不是冲突** —— 把它叫冲突就是假红,而老误报的
        护栏最后会被人删掉。它进 🔗 那一栏:可手工补键,工具照样不写。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Freiburg": "弗赖堡",'))
        db = _db(tmp_path, [("SC Freiburg", "Arsenal", "弗赖堡", "阿森纳")])

        rep = m.harvest(db, m.read_dict_file(d))

        assert rep.aliases["SC Freiburg"] == ("Freiburg", "弗赖堡")
        assert "SC Freiburg" not in rep.new and "SC Freiburg" not in rep.conflicts

    def test_a_routine_en_override_addition_does_not_resurrect_the_bug(self, tmp_path):
        """⚠️ 这条是「今天不发作」的解药。

        今天新键上限恰好是 0(26 个别名已被填满),所以裸眼看不出病。可是
        `_EN_OVERRIDES` 加条目是**例行操作**(07-04 加 27 条、08-05 加 Waalwijk)——
        一加就复活。这里注入一条常规 override,判定必须仍然守得住。
        """
        d = _dict_file(tmp_path)
        kt = m.KnownTeams(m.read_dict_file(d), {"Arsenal": "Arsenal FC"})
        db = _db(tmp_path, [("Arsenal FC", "FC Seoul", "阿森纳FC", "首尔")])

        rep = m.harvest(db, m.read_dict_file(d), known_teams=kt)

        assert "Arsenal FC" not in rep.new, "新加一条 override 就又能写出同队两名"
        assert rep.conflicts["Arsenal FC"] == ("阿森纳", "阿森纳FC")

    def test_the_judgment_runs_by_default_not_only_when_a_test_injects_it(self, tmp_path):
        """⭐ 承重条 —— 首版的病根是「正确的检查存在于测试、跑着的那条还在裸比
        字符串」。所以这里**不注入任何东西**,走 CLI 默认路径,断言默认那条就是
        语义判断。用的是线上 `_EN_OVERRIDES` 里真实存在的一对。"""
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES
        assert _EN_OVERRIDES.get("Bochum") == "VfL Bochum", "样本前提变了,换一对"
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Bochum": "波鸿",'))
        db = _db(tmp_path, [("VfL Bochum", "Arsenal", "波鸿队", "阿森纳")])

        assert m.main(["--db", str(db), "--dict-path", str(d), "--apply"]) == 0

        assert "VfL Bochum" not in m.read_dict_file(d), "默认路径把同一支队又写了一遍"

    def test_the_whole_af_alias_block_would_be_refused_as_new(self):
        """⭐ 线上回归条 —— 把 `_AF_SPELLING_ALIASES_2026_08` 摘掉当 pre-change 态,
        逐条问「这是新队吗」。全部必须判成**已有**(0 条 new)。

        首版实跑:12 条被写进去,产生 11 组同队两名 + 4 个中文不同的 case-only
        碰撞键。这条按真词典逐条走,不是抽样。
        """
        from nutmeg.v4.data.team_name_zh import (
            _AF_SPELLING_ALIASES_2026_08 as AF,
        )
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        pre = {k: v for k, v in TEAM_NAME_ZH.items() if k not in AF}

        rep = m.classify([(en, zh) for en, zh in AF.items()], pre)

        assert rep.new == {}, f"这些别名键会被当成新队写进去:{sorted(rep.new)}"
        assert set(rep.aliases) | set(rep.conflicts) == set(AF)
        # 而且中文全部照抄词典 ⇒ 一条冲突都不该有。
        assert rep.conflicts == {}, (
            f"这些别名的中文和词典里同一支队不一致:{rep.conflicts}")


# ---------- ③ 冲突绝不静默覆盖 -------------------------------------------

class TestConflictsAreNeverOverwritten:
    def test_conflict_is_reported_not_applied(self, tmp_path, capsys):
        """真样本:`FC Seoul` 字典=首尔 / 竞彩=首尔FC。竞彩留 FC 后缀、我们剥掉,
        这是**编辑口径选择**,工具没资格替人选。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("FC Seoul", "Arsenal", "首尔FC", "阿森纳")])

        assert m.main(["--db", str(db), "--dict-path", str(d), "--apply"]) == 0

        assert m.read_dict_file(d)["FC Seoul"] == "首尔", "冲突条目被静默覆盖了"
        out = capsys.readouterr().out
        assert "首尔FC" in out and "首尔" in out, "冲突没打印出来给人看"

    def test_conflict_never_reaches_the_new_bucket(self, tmp_path):
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("FC Seoul", "Arsenal", "首尔FC", "阿森纳")])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.conflicts == {"FC Seoul": ("首尔", "首尔FC")}
        assert rep.new == {}
        assert rep.agree == {"Arsenal": "阿森纳"}

    def test_apply_only_writes_the_new_ones_when_mixed(self, tmp_path):
        """冲突和新名字混在一条 feed 里:新的照写,冲突的一动不动。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("FC Seoul", "SC Freiburg", "首尔FC", "弗赖堡")])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        after = m.read_dict_file(d)
        assert after["SC Freiburg"] == "弗赖堡"
        assert after["FC Seoul"] == "首尔"

    def test_hand_written_entries_in_the_block_survive_a_rewrite(self, tmp_path):
        """块是整块重写的 —— 重写必须是**并入**,不是覆盖。否则上一次收的
        条目会在下一次静默消失。"""
        seeded = _FAKE_DICT.replace(
            '_JINGCAI_VOTE_HARVEST: Dict[str, str] = {\n}',
            '_JINGCAI_VOTE_HARVEST: Dict[str, str] = {\n    "Guimaraes": "吉马良斯",\n}')
        d = _dict_file(tmp_path, seeded)
        db = _db(tmp_path, [("SC Freiburg", "Arsenal", "弗赖堡", "阿森纳")])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        after = m.read_dict_file(d)
        assert after["Guimaraes"] == "吉马良斯", "重写把块里已有条目抹了"
        assert after["SC Freiburg"] == "弗赖堡"

    def test_case_only_collision_with_a_different_chinese_is_refused(self, tmp_path):
        """同批两条只差大小写、中文却不同 ⇒ 两条都拒收。

        前端 `TEAM_ZH_LOWER` 按小写建索引(末位胜)⇒ 这种键会让显示取决于字典
        顺序,正是 `test_dict_has_no_case_only_collisions` 存在的理由。折叠臂管
        「和词典撞」,这条管「同批内部互撞」—— 那条路折叠臂够不着。
        """
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [
            ("Nutmeg Alpha", "Arsenal", "甲队", "阿森纳"),
            ("NUTMEG ALPHA", "Arsenal", "乙队", "阿森纳"),
        ])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.new == {}, f"写出了中文不同的 case-only 碰撞键:{rep.new}"
        assert set(rep.rejected) == {"Nutmeg Alpha", "NUTMEG ALPHA"}
        assert "case-only" in rep.rejected["Nutmeg Alpha"][1]

    def test_case_only_variants_with_the_same_chinese_are_still_allowed(self, tmp_path):
        """反向:中文相同的大小写变体**不该**被拦 —— 线上词典本来就有 6 组
        (`Pau`/`PAU` 等),把它们判红就是给自己造假红。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [
            ("Nutmeg Beta", "Arsenal", "丙队", "阿森纳"),
            ("NUTMEG BETA", "Arsenal", "丙队", "阿森纳"),
        ])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.rejected == {}
        # 折叠臂让第二条变成第一条的别名(同队同中文),两条都不该进 new。
        assert set(rep.new) | set(rep.aliases) == {"Nutmeg Beta", "NUTMEG BETA"}


# ---------- ④ 一名多译 = 停 ----------------------------------------------

class TestAmbiguityStops:
    def test_two_zh_for_one_en_is_refused_not_resolved(self, tmp_path):
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [
            ("Ilves", "Arsenal", "伊尔维斯", "阿森纳"),
            ("Ilves", "Arsenal", "坦佩雷山猫", "阿森纳"),
        ])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.ambiguous == {"Ilves": ["伊尔维斯", "坦佩雷山猫"]}
        assert "Ilves" not in rep.new and "Ilves" not in rep.conflicts

    def test_ambiguous_name_is_not_written_even_with_apply(self, tmp_path):
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [
            ("Ilves", "Arsenal", "伊尔维斯", "阿森纳"),
            ("Ilves", "Arsenal", "坦佩雷山猫", "阿森纳"),
        ])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        assert "Ilves" not in m.read_dict_file(d)

    def test_one_ambiguous_name_does_not_block_the_clean_ones(self, tmp_path):
        """拒收是**逐条**的,不连坐 —— 一条脏数据不该挡住其余 25 条。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [
            ("Ilves", "SC Freiburg", "伊尔维斯", "弗赖堡"),
            ("Ilves", "SC Freiburg", "坦佩雷山猫", "弗赖堡"),
        ])
        m.main(["--db", str(db), "--dict-path", str(d), "--apply"])
        after = m.read_dict_file(d)
        assert after["SC Freiburg"] == "弗赖堡"
        assert "Ilves" not in after


# ---------- ⑤ 「没找到」≠「没去看」 --------------------------------------

class TestBlindVsEmpty:
    def test_missing_db_raises_and_exits_2(self, tmp_path, capsys, caplog):
        """库不在 ⇒ 炸,**不能**报「新名字 0」。这正是涓流那次的形状:
        工具用一个必然为真的「零新增」把自己说成健康。"""
        d = _dict_file(tmp_path)
        with pytest.raises(m.HarvestBlindError):
            m.harvest(tmp_path / "nope.db", {})
        assert m.main(["--db", str(tmp_path / "nope.db"), "--dict-path", str(d)]) == 2
        assert "失明" in caplog.text
        assert "0" not in capsys.readouterr().out, "失明时还打了统计表 —— 会被读成体检通过"

    def test_missing_table_raises(self, tmp_path):
        """库文件在、表不在 —— 最像「一切正常」的失明形态。"""
        db = _db(tmp_path, [], table="some_other_table")
        with pytest.raises(m.HarvestBlindError):
            m.harvest(db, {})

    def test_a_file_that_is_not_a_database_raises(self, tmp_path):
        """⚠️ 「文件不是数据库」抛的是 `sqlite3.DatabaseError`,**不是**
        `OperationalError` —— 只捕子类会让它一路漏成未捕异常,绕过 HarvestBlindError,
        于是「没去看」又一次长得和别的东西一样。"""
        fake = tmp_path / "o.db"
        fake.write_bytes(b"this is not a sqlite file, it's a text file\n" * 40)
        with pytest.raises(m.HarvestBlindError):
            m.harvest(fake, {})

    def test_missing_markers_refuse_to_write(self, tmp_path):
        """收割块标记被人删了 ⇒ 不猜位置、不写。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace("# HARVEST-BEGIN", "# gone"))
        with pytest.raises(m.HarvestBlindError):
            m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"})

    def test_a_marker_that_appears_twice_refuses_to_write(self, tmp_path):
        """⭐ 上一条只删标记 —— 裸 `str.find` 和「恰好一次」两种实现都是 0 命中,
        它区分不出来。这条给出**判别输入**:块头注释里把 `# HARVEST-BEGIN`
        单独写成一行(散文里提一句这个标记),全文就出现 2 次。

        裸 `find` 会取**第一处**(注释里那行)当块的起点,于是切错块;
        `_marker_at` 要求「独占一行且恰好一次」,多一次就报失明、不猜位置。
        这个坑 `_marker_at` 的 docstring 说「返工时真踩到了」,却一直零覆盖。
        """
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            "# HARVEST-BEGIN\n_JINGCAI_VOTE_HARVEST",
            "# 别在下面这两行之间加东西:\n"
            "# HARVEST-BEGIN\n"
            "# 和 HARVEST-END。\n"
            "# HARVEST-BEGIN\n_JINGCAI_VOTE_HARVEST", 1))
        before = d.read_text(encoding="utf-8")
        assert before.count("\n# HARVEST-BEGIN\n") == 2, "判别输入没造出来"

        with pytest.raises(m.HarvestBlindError, match="出现 2 次"):
            m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"})
        assert d.read_text(encoding="utf-8") == before, "报了失明却还是写了"

    def test_empty_table_reports_zero_rows_and_exits_0(self, tmp_path, capsys):
        """表在但空 = 真的「feed 没有」⇒ 退 0,且报告里带得出扫描计数当证据。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [])
        assert m.main(["--db", str(db), "--dict-path", str(d)]) == 0
        out = capsys.readouterr().out
        assert "0 行" in out
        assert "不是「没去看」" in out

    def test_zero_new_report_states_the_structural_ceiling(self, tmp_path, capsys):
        """0 条新名字时,报告必须说清「上限是多少」—— 上限 0(路走到头)和
        上限 >0 却命中 0(秋天会来)是完全不同的两件事。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("Arsenal", "FC Seoul", "阿森纳", "首尔")])
        assert m.main(["--db", str(db), "--dict-path", str(d)]) == 0
        out = capsys.readouterr().out
        assert "🆕 0 条" in out
        assert "结构上限" in out
        assert "个槽位" in out, "没把「扫过多少」摆出来当证据"

    def test_ceiling_is_none_not_zero_when_it_cannot_be_computed(self, monkeypatch):
        """算不出来就说「未知」。编一个 0 出来比缺这个数更坏 —— 它会让人以为
        这个源已经榨干了。"""
        import builtins
        real_import = builtins.__import__

        def boom(name, *a, **kw):
            if name == "nutmeg.v4.data.sources.sporttery":
                raise ImportError("no sporttery")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", boom)
        assert m.new_key_ceiling({"Arsenal": "阿森纳"}) is None

    def test_blind_when_the_alias_table_is_unreachable(self, monkeypatch):
        """判不了「是不是同一支队」时必须**停**,不许降级成裸比字符串 ——
        降级正是首版那个 bug 的形状,而且降级后一样退 0、一样打「冲突 0」。"""
        import builtins
        real_import = builtins.__import__

        def boom(name, *a, **kw):
            if name == "nutmeg.v4.data.sources.sporttery":
                raise ImportError("no sporttery")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", boom)
        with pytest.raises(m.HarvestBlindError):
            m.classify([("SC Freiburg", "弗赖堡")], {"Freiburg": "弗赖堡"})


class TestCeilingIsMeasuredNotAsserted:
    """上限那个数是**算**出来的,不是写死的 —— 而「上限恰好是 0」会让任何
    `isdisjoint` 之类的断言恒真(**空洞**)。所以这里全部用「动一下、看它跟着动」
    的方式测,和上限此刻是几无关。"""

    def test_the_resolver_the_ceiling_leans_on_is_itself_not_vacuous(self):
        """上限 = 「能吐出来 ∖ 词典已有这支队」。左边是覆盖表的事,右边全靠
        `KnownTeams` —— 所以先把右边钉死:该认的认、不该认的不认。"""
        kt = m.KnownTeams({"Freiburg": "弗赖堡"}, {"Freiburg": "SC Freiburg"})
        assert kt.lookup("SC Freiburg").zhs == ("弗赖堡",)   # 别名臂
        assert kt.lookup("FREIBURG").zhs == ("弗赖堡",)      # 折叠臂(大小写)
        assert kt.lookup("Freiburg II") is None, "预备队被并进一队了"
        assert kt.lookup("Hamburg") is None, "不相干的队被认成已有 ⇒ 上限会假性归零"

    def test_dropping_a_whole_club_makes_it_reappear_in_the_ceiling(self):
        """行为级、非空洞:把某支队的**所有**键从线上词典里摘掉,上限必须多出
        它的盘面拼法。上限若「静默返回空集」,这条立刻红。"""
        from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        target = "Kyoto Sanga FC"
        assert target in _ZH_OVERRIDES.values(), "样本前提变了,换一个 _ZH_OVERRIDES 值"

        full = m.new_key_ceiling(TEAM_NAME_ZH)
        assert full is not None and target not in full, "词典里还有这支队,上限不该含它"

        pruned = {k: v for k, v in TEAM_NAME_ZH.items()
                  if m.fold_key(k) != m.fold_key(target)}
        assert len(pruned) < len(TEAM_NAME_ZH), "没摘掉任何键 —— 这条会变空洞"
        assert target in (m.new_key_ceiling(pruned) or set())

    def test_ceiling_never_contains_a_team_the_dict_already_has(self):
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        ceiling = m.new_key_ceiling(TEAM_NAME_ZH)
        assert ceiling is not None
        kt = m.KnownTeams(TEAM_NAME_ZH, {})
        assert not [en for en in ceiling if kt.lookup(en)], "上限里混进了词典已有的队"


# ---------- 收窄闸:不合法的东西不许写进源码 ------------------------------

class TestRejects:
    def test_zh_without_han_chars_is_refused(self, tmp_path):
        """词典有一条既存不变量:每个值都得有汉字(test_team_name_zh.py)。
        收割绝不能把别人的测试搞红。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [("SC Freiburg", "Arsenal", "Freiburg", "阿森纳")])
        rep = m.harvest(db, m.read_dict_file(d))
        assert "SC Freiburg" in rep.rejected
        assert "SC Freiburg" not in rep.new

    def test_quote_in_name_is_refused(self, tmp_path):
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [('Bad"Name', "Arsenal", "坏名字", "阿森纳")])
        rep = m.harvest(db, m.read_dict_file(d))
        assert 'Bad"Name' in rep.rejected

    def test_overlong_entry_is_refused(self, tmp_path):
        """渲染后超过 100 字符 ⇒ 拒收。ruff line-length=100,写进去就是自造 E501。"""
        d = _dict_file(tmp_path)
        long_en = "A" * 90
        db = _db(tmp_path, [(long_en, "Arsenal", "超长队名", "阿森纳")])
        rep = m.harvest(db, m.read_dict_file(d))
        assert long_en in rep.rejected
        assert "E501" in rep.rejected[long_en][1]

    def test_unmapped_zh_is_counted_not_dropped(self, tmp_path, capsys):
        """竞彩有中文、我们没英文名 —— 收不了(没有键),但**必须报出来**:
        秋天英乙/东欧杯赛上盘时,这一栏就是「该补哪些队」的清单。"""
        d = _dict_file(tmp_path)
        db = _db(tmp_path, [(None, "Arsenal", "巴恩斯利", "阿森纳")])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.unmapped_zh == {"巴恩斯利": 1}
        assert m.main(["--db", str(db), "--dict-path", str(d)]) == 0
        assert "巴恩斯利" in capsys.readouterr().out

    def test_every_slot_lands_in_exactly_one_bucket(self, tmp_path):
        """分桶必须是**划分**,不是筛子 —— 没有哪个名字能悄悄消失。"""
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            '"Arsenal": "阿森纳",', '"Arsenal": "阿森纳",\n    "Freiburg": "弗赖堡",'))
        db = _db(tmp_path, [
            ("Arsenal", "FC Seoul", "阿森纳", "首尔FC"),      # agree + conflict
            ("SC Freiburg", None, "弗赖堡", "巴恩斯利"),       # alias + unmapped
            ("Ilves", "VfL Bochum", "伊尔维斯", "波鸿"),       # ambiguous + new
            ("Ilves", "VfL Bochum", "坦佩雷山猫", "波鸿"),
        ])
        rep = m.harvest(db, m.read_dict_file(d))
        assert rep.n_slots == 8, "有中文名的槽位漏数了"

        buckets = [set(rep.agree), set(rep.aliases), set(rep.conflicts), set(rep.new),
                   set(rep.ambiguous), set(rep.rejected)]
        union: set[str] = set().union(*buckets)
        assert union == {"Arsenal", "FC Seoul", "SC Freiburg", "Ilves", "VfL Bochum"}, (
            "有英文名凭空消失")
        assert sum(len(b) for b in buckets) == len(union), "同一个名字进了两个桶"
        assert rep.n_distinct_en == 5
        assert sum(rep.unmapped_zh.values()) == 1

    def test_every_list_says_how_many_it_truncated(self, tmp_path, capsys):
        """无声截断 = 假装覆盖全了。四个列表都得把截掉的条数说出来,
        不能只有 new/conflicts 有。"""
        d = _dict_file(tmp_path)
        rows = []
        for i in range(4):
            rows.append((f"Nutmeg Amb {i}", None, f"歧义{i}甲", f"无英文{i}"))
            rows.append((f"Nutmeg Amb {i}", None, f"歧义{i}乙", f"无英文{i}b"))
            rows.append((f"Nutmeg Bad {i}" + "X" * 90, "Arsenal", f"超长{i}", "阿森纳"))
        db = _db(tmp_path, rows)
        assert m.main(["--db", str(db), "--dict-path", str(d), "--show", "1"]) == 0
        out = capsys.readouterr().out
        assert out.count("其余") >= 3, f"有列表在静默截断:\n{out}"


# ---------- ⑥ 写盘要么全成要么原样 ---------------------------------------

_CRASH_CHILD = """
import json, resource, signal, sys
from pathlib import Path
from nutmeg.v4.cli import harvest_team_zh as m

mode, target = sys.argv[1], Path(sys.argv[2])
if mode == "old":                      # 复原返工前的写法:就地 write_text
    def _old(p, text, expected_keys):
        p.write_text(text, encoding="utf-8")
    m._atomic_write = _old

fill = {"Nutmeg Fill %04d FC" % i: "填充队%d" % i for i in range(400)}
before = target.read_bytes()
m.read_dict_file(target)               # 先热一遍,别让别的 I/O 撞上限
soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)      # 要 EFBIG,不要被信号打死
resource.setrlimit(resource.RLIMIT_FSIZE, (len(before) + 4000, hard))
err = ""
try:
    m.apply_new_entries(target, fill)
except BaseException as exc:
    err = type(exc).__name__
resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))

raw = target.read_bytes()
try:
    m.read_dict_file(target)
    importable = True
except BaseException:
    importable = False
print(json.dumps({
    "err": err,
    "intact": raw == before,
    "importable": importable,
    "tail": raw[-60:].decode("utf-8", "replace"),
    "strays": sorted(str(p.relative_to(target.parent))
                     for p in target.parent.rglob("*") if "harvest-tmp" in p.name),
}))
"""


def _run_crash_child(mode: str, target: Path) -> dict:
    # ⚠️ 这里**故意不**设 `PYTHONDONTWRITEBYTECODE` —— 原来设了,于是上面那句
    # `strays` 永远看不见字节码残留(工具真留过一个 `.harvest-tmp-*.pyc`),
    # 检查看不见它声称检查的东西。抑制字节码是**被测代码**
    # (`_verify_importable`)自己的责任,不是测试替身该替它做的。
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    out = subprocess.run([sys.executable, "-c", _CRASH_CHILD, mode, str(target)],
                         capture_output=True, text=True, timeout=300, env=env)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


class TestWriteIsAtomic:
    """磁盘满 / Ctrl-C / OOM / 掉电都会在写到一半时把进程掐掉。

    `team_name_zh.py` 被 API / dashboard / 所有 CLI 顶层 import ⇒ 半截文件
    = 整个服务起不来,而且同目录连个 .bak 都没有。这里用 RLIMIT_FSIZE 真的把
    写入卡在中途(不是 mock 一个异常),A/B 对比返工前后。
    """

    def test_the_pre_change_writer_really_did_corrupt_the_file(self, tmp_path):
        """先证明这个复现是真的会发作的 —— 否则下面那条「现在好了」就没有参照。"""
        d = tmp_path / "team_name_zh.py"
        d.write_text(LIVE_DICT.read_text(encoding="utf-8"), encoding="utf-8")
        got = _run_crash_child("old", d)
        assert got["err"], "上限没卡住写入,这个复现失效了"
        assert not got["intact"], "就地 write_text 居然没截断?复现前提变了"
        assert not got["importable"], "半截文件竟然还能 import?复现前提变了"

    def test_a_failed_write_leaves_the_original_untouched(self, tmp_path):
        d = tmp_path / "team_name_zh.py"
        original = LIVE_DICT.read_text(encoding="utf-8")
        d.write_text(original, encoding="utf-8")

        got = _run_crash_child("new", d)

        assert got["err"], "上限没卡住写入,这条测的就不是崩溃路径了"
        assert got["intact"], f"写失败后文件被改了,尾巴是 {got['tail']!r}"
        assert got["importable"], "写失败后词典 import 不了 —— 服务会起不来"
        assert got["strays"] == [], f"留下了临时文件:{got['strays']}"
        assert d.read_text(encoding="utf-8") == original

    def test_a_failure_at_the_rename_step_also_leaves_no_trace(self, tmp_path,
                                                               monkeypatch):
        """确定性版本:替换那一步炸。原文件不动,tmp 不许留。"""
        d = _dict_file(tmp_path)
        before = d.read_text(encoding="utf-8")
        monkeypatch.setattr(m.os, "replace",
                            lambda *a, **kw: (_ for _ in ()).throw(OSError("boom")))
        with pytest.raises(OSError, match="boom"):
            m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"})
        assert d.read_text(encoding="utf-8") == before
        assert _strays(tmp_path) == []

    def test_a_successful_write_leaves_no_trace_either(self, tmp_path):
        """⭐ 上面两条盯的都是**失败**路径,而残留恰恰发生在**成功**路径上:
        复核子进程 import 完 tmp 文件,`__pycache__/` 里就多一个
        `.harvest-tmp-*.pyc`,`finally` 里那句 `tmp.unlink()` 够不着它。

        实测:修之前每跑一次 `--apply` 攒一个孤儿字节码(线上目录也真攒了一个),
        而当时的断言用非递归 `iterdir()`,看不见 —— 假绿。
        """
        d = _dict_file(tmp_path)
        assert m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"}) == 1
        assert m.read_dict_file(d)["SC Freiburg"] == "弗赖堡", "先确认这是成功路径"
        assert _strays(tmp_path) == []


class TestRewriteIsVerifiedBySemanticsNotSyntax:
    """`ast.parse` 只证明「能解析」。整块重写把块里别的语句一起删掉,写出来的
    文件照样 parse 得过,import 时才 NameError —— 语法代理测语义属性。"""

    _WITH_EXTRA = _FAKE_DICT.replace(
        "# HARVEST-BEGIN\n_JINGCAI_VOTE_HARVEST",
        '# HARVEST-BEGIN\n_HARVEST_NOTE = "块里的另一条语句"\n_JINGCAI_VOTE_HARVEST',
    ).replace("for _en, _zh in", "assert _HARVEST_NOTE\nfor _en, _zh in")

    def test_rendering_away_a_statement_yields_parseable_but_unimportable(self, tmp_path):
        """先证明危险是真的:手工走一遍「只渲染键值对」的老路子。"""
        import ast
        d = _dict_file(tmp_path, self._WITH_EXTRA)
        head, block, tail = m._split(d.read_text(encoding="utf-8"))
        rendered = head + m._render_block({"SC Freiburg": "弗赖堡"}) + tail
        ast.parse(rendered)                    # ← 老的复核在这里就放行了
        broken = tmp_path / "broken.py"
        broken.write_text(rendered, encoding="utf-8")
        with pytest.raises(m.HarvestBlindError, match="import 不了"):
            m._verify_importable(broken, set())

    def test_apply_refuses_when_the_block_holds_anything_else(self, tmp_path):
        d = _dict_file(tmp_path, self._WITH_EXTRA)
        before = d.read_text(encoding="utf-8")
        with pytest.raises(m.HarvestBlindError, match="整块重写会丢掉"):
            m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"})
        assert d.read_text(encoding="utf-8") == before

    def test_a_comment_inside_the_block_is_named_not_silently_dropped(self, tmp_path):
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            "_JINGCAI_VOTE_HARVEST: Dict[str, str] = {\n}",
            "# 人手写的一句提醒\n_JINGCAI_VOTE_HARVEST: Dict[str, str] = {\n}"))
        extras = m.block_extras(m._split(d.read_text(encoding="utf-8"))[1])
        assert any("人手写的一句提醒" in e for e in extras)

    def test_dry_run_surfaces_block_extras_without_needing_apply(self, tmp_path, capsys):
        """光靠 --apply 报错不够 —— 人跑 dry-run 时就得看见,否则这个坑要等到
        真去写的那天才现身。"""
        d = _dict_file(tmp_path, self._WITH_EXTRA)
        db = _db(tmp_path, [("Arsenal", "FC Seoul", "阿森纳", "首尔")])
        assert m.main(["--db", str(db), "--dict-path", str(d)]) == 0
        assert "整块重写丢掉" in capsys.readouterr().out

    def test_key_count_mismatch_is_caught_before_the_file_is_replaced(self, tmp_path):
        probe = tmp_path / "t.py"
        probe.write_text("TEAM_NAME_ZH = {'Arsenal': '阿森纳'}\n", encoding="utf-8")
        m._verify_importable(probe, {"Arsenal"})            # 对得上 → 静默通过
        with pytest.raises(m.HarvestBlindError, match="放弃写入"):
            m._verify_importable(probe, {"Arsenal", "Chelsea"})

    def test_apply_itself_refuses_when_the_entry_would_not_actually_land(self, tmp_path):
        """⭐ 上面两条直接调复核函数;这条盯的是**写入路径真的用了它**没有
        (「检查的前提没人检查」)。

        场景是真会发生的:有人在块**下面**的接线上加了个过滤,于是块里写进去了、
        `TEAM_NAME_ZH` 里却没有。纯语法复核照样放行,工具会打「✅ 已写入 1 条」,
        而那条名字永远不显示。
        """
        d = _dict_file(tmp_path, _FAKE_DICT.replace(
            "for _en, _zh in _JINGCAI_VOTE_HARVEST.items():\n"
            "    TEAM_NAME_ZH.setdefault(_en, _zh)",
            "for _en, _zh in _JINGCAI_VOTE_HARVEST.items():\n"
            '    if _en != "SC Freiburg":\n'
            "        TEAM_NAME_ZH.setdefault(_en, _zh)"))
        before = d.read_text(encoding="utf-8")

        with pytest.raises(m.HarvestBlindError, match="放弃写入"):
            m.apply_new_entries(d, {"SC Freiburg": "弗赖堡"})

        assert d.read_text(encoding="utf-8") == before, "复核失败后文件仍被改了"
        assert _strays(tmp_path) == []


# ---------- 线上目标文件本身可写 ------------------------------------------

class TestLiveDictFileIsWritable:
    def test_live_file_has_a_parseable_harvest_block(self):
        """写侧只认标记 —— 标记要是被谁删了,这个 CLI 就永远写不进去,而且
        只有真去 --apply 的那天才会发现。

        ⚠️ 这里**不**断言块此刻是空的:那是个瞬时状态,工具成功用一次就会红
        (典型假红,而且会把这条真正该守的不变量一起拖走)。
        """
        text = LIVE_DICT.read_text(encoding="utf-8")
        _head, block, _tail = m._split(text)
        assert isinstance(m._parse_block(block), dict), "块里的 dict 解析不了"
        assert m.block_extras(block) == [], "块里有整块重写会丢掉的东西"
        # 「块接进了 TEAM_NAME_ZH 没有」不在这里断言:原来那句
        # `assert "_JINGCAI_VOTE_HARVEST.items()" in tail` 是**拿源码字符串代替
        # 行为** —— 把接线改成等价的 `for _en in _JINGCAI_VOTE_HARVEST:` 就假红,
        # 而真把接线删掉时 `test_round_trip_on_a_copy_of_the_live_file` 本来就会红
        # (实测:删接线 ⇒ 那条红)。只产假红、不产信息 ⇒ 删。

    def test_the_machine_block_never_shadows_a_hand_written_entry(self, tmp_path):
        """🚨 机器块原来是文件**最后**一次 update ⇒ 盖住上面所有人工联赛块,
        而块头注释恰恰叫人「手工条目写进上面的块里」—— 那条订正路径是 no-op。

        行为断言:往线上文件的副本里塞一条和人工条目撞键的收割条目,import 后
        必须是**人工**那个中文。
        """
        d = tmp_path / "team_name_zh.py"
        d.write_text(LIVE_DICT.read_text(encoding="utf-8"), encoding="utf-8")
        before = m.read_dict_file(d)
        assert before["Arsenal"] == "阿森纳"

        head, block, tail = m._split(d.read_text(encoding="utf-8"))
        d.write_text(head + m._render_block({"Arsenal": "机器覆盖队"}) + tail,
                     encoding="utf-8")

        after = m.read_dict_file(d)
        assert after["Arsenal"] == "阿森纳", "机器块盖掉了人工条目"

    def test_the_machine_block_stays_last_in_insertion_order(self, tmp_path):
        """🚨 `setdefault` 要的是**两个**性质,上一条只守住了第一个(人工值赢)。

        第二个写在块头注释里、却一直没人守:机器条目必须留在 `TEAM_NAME_ZH` 的
        **插入顺序末尾**。`sporttery._ZH_TO_EN` 拿插入顺序建中文→英文反查(先到
        先得),机器条目一旦排到人工条目前面,就会抢下反查权 —— 那正是 07-04 /
        08-05 两次「别名遮蔽」事故的形状:行照写、join 永死,而且**值仍然是对的**,
        所以上一条断言全程绿。

        (这一句取代了原来的 `assert head.count("TEAM_NAME_ZH") > 0` —— 那句在
        1100 行的真词典上恒真,不存在能让它为 0 的现实改动。判别变异实测:把接线
        换成「机器条目排最前、人工值仍覆盖」,当时整个套件只有那条语法代理会红。)

        ⚠️ 断言的是「探针后面**没有人工条目**」,不是「探针在最末尾」。后者写出来
        试过,当场就是假红:块非空时整块**按键排序**重写,`Nutmeg Order FC` 排在
        `Nutmeg Smoke A FC` 前面 ⇒ 工具被正常用一次这条就红。要守的性质是
        「机器条目占据插入顺序的一个**后缀**」,和块内怎么排序无关。
        """
        d = tmp_path / "team_name_zh.py"
        d.write_text(LIVE_DICT.read_text(encoding="utf-8"), encoding="utf-8")
        assert m.apply_new_entries(d, {"Nutmeg Order FC": "顺序队"}) == 1

        keys = list(m.read_dict_file(d))
        block = set(m._parse_block(m._split(d.read_text(encoding="utf-8"))[1]))
        probe_at = keys.index("Nutmeg Order FC")
        handwritten_after = [k for k in keys[probe_at + 1:] if k not in block]
        assert handwritten_after == [], (
            "收割条目没占住插入顺序的后缀 —— 它会跟人工条目抢 `_ZH_TO_EN` 反查权"
            f"(排在机器条目后面的人工键 {len(handwritten_after)} 个,"
            f"前几个:{handwritten_after[:5]})")

    def test_live_block_is_counted_in_coverage(self):
        """既有不变量 TOTAL ≤ 各块之和 靠每个块都登记在册;漏登记会静默破坏它。"""
        from nutmeg.v4.data.team_name_zh import coverage_by_league
        assert "JINGCAI_VOTE_HARVEST" in coverage_by_league()

    def test_round_trip_on_a_copy_of_the_live_file(self, tmp_path):
        """拿线上文件的副本走一遍完整读→写→读,证明真目标(1100+ 行、
        20 个块、带重音键)也吃得下这个写法。"""
        d = tmp_path / "team_name_zh.py"
        d.write_text(LIVE_DICT.read_text(encoding="utf-8"), encoding="utf-8")
        before = m.read_dict_file(d)
        assert m.apply_new_entries(d, {"Nutmeg Test FC": "测试队"}) == 1
        after = m.read_dict_file(d)
        assert after["Nutmeg Test FC"] == "测试队"
        assert len(after) == len(before) + 1, "写入影响了别的条目"
