"""artifact 年龄探针量的是**训练日期**,不是 metadata.json 的文件日期(2026-08-07)。

姊妹文件 `test_supply_chain_follows_layer_b.py` 钉的是**哪个目录**;这里钉的是
**哪个日期**。两条是同一次审查里翻出来的两个独立的洞,合在一起才是完整的红线:
量错目录 = 看的不是服务加载的盘,量错日期 = 看的不是训练时间。

## 病

`check_model_supply_chain` 的 `ARTIFACT_MAX_AGE_DAYS`(120d)红线是「生产 artifact
曾冻 724 天」那次事故留下的守卫。它这样取年龄:

    raw = (json.loads(meta.read_text()) or {}).get("trained_at_utc")   # 顶层
    ...
    if trained is None:
        trained = datetime.fromtimestamp(meta.stat().st_mtime, UTC).date()   # 兜底

但 `model/persist.py::save_artifact()` 写出的 `metadata.json` 是**嵌套**的 ——
训练 metadata 在 `"metadata"` 键下面,顶层只有 feature_columns / elo_* /
model_type / cat_features。实测 2026-08-07:

  · `data/v4_model_cat`  顶层 None,嵌套 `2026-07-15T06:19:12+00:00`
  · `data/v4_model`      顶层 None,嵌套 `2026-05-22T06:17:04+00:00`

⇒ `raw` 恒为 None ⇒ **每次都走那条本来只为旧格式盘(47435ce 之前)准备的兜底**。
红线量的一直是文件修改时间。同一个文件里的 `_training_cutoff()` 读对了(它的
docstring 甚至专门警告过这个坑),偏偏年龄这条没有。

## 为什么它不会自己暴露

它**不报错**,只把年龄报得**偏乐观**,而且报告里两种年龄显示成同一句「训练于 X」。
盘上就有现成的例子(2026-08-07 实测):

    v4_model_cat.bak-20260715T135746-pre-clubelo-retrain
        trained_at_utc = 2026-05-23 (76d)   mtime = 2026-07-15 (23d)   少算 53 天

`cp -r` 出来的备份盘就这样。rsync / 备份还原同理 —— 任何一次搬运都能把一个陈旧
盘刷成「刚训好」,而这正是这条红线要守的东西。守卫本身失效了,且是静默的。

## 本文件钉住的性质

**把 metadata.json 的 mtime 刷新到今天,不能让超龄报警闭嘴。**
反向同样钉住:mtime 很旧但训练日期很新,不许假报警。

另外两条是**修这个 bug 的过程中差点自己引入的**,所以一起钉死(两条都实跑复现过,
两条的共同形状都是「本来会响的场景,修完变成零告警」):

  · 嵌套值是空串时,不许挡住顶层那个能用的日期(falsy ≠ 缺失)。
  · 训练日期在未来时,不许夹成 0d —— 夹一次就是**永远** 0d、永远零告警。

⛔ 断言一律打在探针**跑出来的 info/alarms** 上,不查源码里有没有某个字符串
(cf. [[syntactic-proxy-for-semantic-property]]:语法代理测语义属性,假红比假绿更贵)。
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from nutmeg.v4.cli.data_freshness import (
    ARTIFACT_MAX_AGE_DAYS,
    check_model_supply_chain,
)

TODAY = dt.date(2026, 8, 7)


def _set_mtime(path: Path, day: dt.date) -> None:
    """把文件 mtime 钉到某个日历日(用绝对时间戳,不依赖跑测试那台机器的钟)。"""
    ts = dt.datetime.combine(day, dt.time(12, 0), tzinfo=dt.UTC).timestamp()
    os.utime(path, (ts, ts))


def _artifact(
    tmp_path: Path,
    *,
    trained_at: str | None,
    mtime_day: dt.date,
    nested: bool = True,
    flat_too: str | None = None,
    name: str = "artifact",
) -> Path:
    """造一个 artifact 目录:训练日期与文件日期**可以不一致**(这正是被测的事)。

    ``flat_too`` 额外写一个顶层 ``trained_at_utc``,用来测两种形状同时存在时谁赢。
    """
    art = tmp_path / name
    art.mkdir(parents=True, exist_ok=True)
    meta: dict = {
        "model_type": "catboost",
        "elo_initial": 1500.0,
        "feature_columns": ["elo_diff"],
    }
    if trained_at is not None:
        if nested:
            # 真实形状 —— persist.save_artifact() 把训练 metadata 塞进子字典
            meta["metadata"] = {"trained_at_utc": trained_at, "training_cutoff": "2024-06-01"}
        else:
            # 手搓/旧盘的扁平形状(test_hc_wave1 的两个用例就是这个)
            meta["trained_at_utc"] = trained_at
    if flat_too is not None:
        meta["trained_at_utc"] = flat_too
    mp = art / "metadata.json"
    mp.write_text(json.dumps(meta))
    _set_mtime(mp, mtime_day)
    return art


def _probe(art: Path, tmp_path: Path, today: dt.date = TODAY):
    """只跑 artifact 那一支 —— 源树/外部 parquet 指向不存在的目录,自动跳过。"""
    return check_model_supply_chain(
        today,
        artifact_dir=art,
        sources_dir=tmp_path / "no-sources",
        external_dir=tmp_path / "no-external",
    )


def _artifact_line(info: list[str]) -> str:
    hits = [ln for ln in info if ln.startswith("artifact ")]
    assert len(hits) == 1, f"期望恰好一行 artifact 报告,拿到 {info}"
    return hits[0]


# ---------------------------------------------------------------- 核心:mtime 骗不了它

class TestTrainedDateBeatsFileDate:
    def test_stale_training_date_alarms_even_when_file_is_brand_new(self, tmp_path):
        """训练于 2024-08-01,但 metadata.json 今天刚被 cp/rsync 碰过 ⇒ 必须报**旧**的那个年龄。

        这就是 bug 的原形:`cp -r` 一个陈旧盘,mtime=今天 ⇒ 老代码算出 0d,红线闭嘴。
        """
        trained_day = dt.date(2024, 8, 1)
        art = _artifact(
            tmp_path,
            trained_at="2024-08-01T00:00:00+00:00",
            mtime_day=TODAY,          # 文件「刚刚」被动过
        )
        info, alarms = _probe(art, tmp_path)

        expected_age = (TODAY - trained_day).days
        assert expected_age > ARTIFACT_MAX_AGE_DAYS, "前提:这个训练日期本就该超龄"

        line = _artifact_line(info)
        assert f"{expected_age}d" in line, f"年龄应取训练日期({expected_age}d),拿到:{line}"
        assert str(trained_day) in line, f"应显示训练日 {trained_day},拿到:{line}"
        assert "· 0d" not in line, f"0d = 又在用文件日期:{line}"
        # 老代码在这里 alarms == [] —— 这一条就是「守卫失效」本身
        assert alarms, "陈旧 artifact 必须报警,哪怕文件是今天刚落的"
        assert str(expected_age) in alarms[0]

    def test_fresh_training_date_stays_quiet_even_when_file_is_ancient(self, tmp_path):
        """反向:训练于 5 天前,但文件 mtime 是两年前 ⇒ 不许假报警。

        两个方向一起钉,才能证明它真在读 JSON 而不是碰巧和 mtime 一致
        (线上 `data/v4_model_cat` 两者恰好都是 2026-07-15,单看一个方向分不出来)。
        """
        art = _artifact(
            tmp_path,
            trained_at="2026-08-02T06:19:12+00:00",
            mtime_day=dt.date(2024, 8, 1),   # 文件很旧(解包/还原出来的)
        )
        info, alarms = _probe(art, tmp_path)

        line = _artifact_line(info)
        assert "· 5d" in line, f"年龄应是 5d,拿到:{line}"
        assert alarms == [], f"刚训好的盘不该报警,拿到:{alarms}"

    def test_flat_shape_still_honoured(self, tmp_path):
        """手搓/旧盘的扁平 `trained_at_utc` 仍然要认(test_hc_wave1 的两个用例就是这形状)。"""
        art = _artifact(
            tmp_path,
            trained_at="2024-08-01T00:00:00",
            mtime_day=TODAY,
            nested=False,
        )
        info, alarms = _probe(art, tmp_path)

        expected_age = (TODAY - dt.date(2024, 8, 1)).days
        assert f"{expected_age}d" in _artifact_line(info)
        assert alarms, "扁平形状也要能触发超龄报警"

    def test_offset_timestamp_folds_to_utc_day(self, tmp_path):
        """带偏移的时间戳按 UTC 折日,不是裸切 `[:10]`。

        `2026-08-03T02:00:00+08:00` 的 UTC 日是 08-02(切片会读成 08-03,差一天)。
        """
        art = _artifact(
            tmp_path,
            trained_at="2026-08-03T02:00:00+08:00",
            mtime_day=TODAY,
        )
        info, _ = _probe(art, tmp_path)
        line = _artifact_line(info)
        assert "2026-08-02" in line and "· 5d" in line, f"应折成 UTC 日 08-02 / 5d:{line}"

    def test_empty_nested_value_does_not_veto_a_usable_flat_one(self, tmp_path):
        """⭐ 嵌套值是**空串**时,不许挡住顶层那个能用的日期。

        「嵌套优先」若写成 `if value is None:` 才回退,一个 `""` 就会赢过顶层的真
        日期 ⇒ 读成 None ⇒ 退到 mtime ⇒ **0d 零告警**,而**修之前的基线在同一个
        盘上是会喊 736d 的**。也就是说:修 bug 的那一版会在这个形状上比原版更瞎。
        空串不是日期,不能压过一个真日期。
        """
        art = _artifact(
            tmp_path,
            trained_at="",                              # 嵌套:空
            flat_too="2024-08-01T00:00:00+00:00",       # 顶层:能用
            mtime_day=TODAY,
        )
        info, alarms = _probe(art, tmp_path)

        expected_age = (TODAY - dt.date(2024, 8, 1)).days
        line = _artifact_line(info)
        assert f"训练于 2024-08-01 · {expected_age}d" in line, (
            f"空的嵌套值把顶层的真日期挡掉了,退到 mtime 了:{line}")
        assert alarms, "顶层有可用日期且超龄 ⇒ 必须响"


# ---------------------------------------------------------------- 未来日期:不许夹成 0

class TestFutureDateIsAFaultNotZero:
    def test_trained_in_the_future_alarms_instead_of_clamping_to_zero(self, tmp_path):
        """⭐ 训练日期在未来 ⇒ **告警**,不是 `max(0, …)` 夹成 0d。

        夹的后果不是「显示成 0d」,是年龄**永远** 0d、**永远**零告警:一个坏时钟、
        一次手改 metadata、一次时区写反,就能把这条红线彻底关掉,而基线在同一个盘上
        (没有 trained_at 时退 mtime)是会喊 949d 的。⇒ 夹一下,红线就此消失且无人知晓。
        """
        future = TODAY + dt.timedelta(days=3)
        art = _artifact(
            tmp_path,
            trained_at=f"{future.isoformat()}T00:00:00+00:00",
            mtime_day=dt.date(2024, 1, 1),
        )
        info, alarms = _probe(art, tmp_path)

        assert alarms, f"未来日期必须响 —— 夹成 0d 就是把红线关掉:info={info}"
        assert "未来" in alarms[0], f"要说清是什么故障:{alarms[0]}"
        line = _artifact_line(info)
        assert "· 0d" not in line, f"年龄不该被夹成 0d:{line}"

    def test_same_day_is_zero_and_quiet(self, tmp_path):
        """边界另一侧:今天训练的 = 0d,正常,不许被上一条误伤成告警。"""
        art = _artifact(
            tmp_path,
            trained_at=f"{TODAY.isoformat()}T00:00:00+00:00",
            mtime_day=dt.date(2024, 1, 1),
        )
        info, alarms = _probe(art, tmp_path)
        assert alarms == [], f"今天刚训的盘不该响:{alarms}"
        assert "· 0d" in _artifact_line(info)


# ---------------------------------------------------------------- 兜底:走了要说出来

class TestMtimeFallbackIsLabelled:
    def test_no_trained_at_falls_back_but_says_so(self, tmp_path):
        """完全没有 trained_at_utc(真·旧格式盘)⇒ 允许走 mtime,但输出必须自认。"""
        art = _artifact(tmp_path, trained_at=None, mtime_day=dt.date(2026, 8, 2))
        info, alarms = _probe(art, tmp_path)

        line = _artifact_line(info)
        assert "· 5d" in line, f"兜底年龄应来自 mtime(5d):{line}"
        assert alarms == []
        assert "文件" in line and "不是训练日期" in line, (
            f"走 mtime 时必须讲明这是文件日期:{line}")
        assert "训练于" not in line, (
            "这一行不能既说「训练于 X」又说「不是训练日期」—— 自相矛盾的报告行比"
            f"没有那句警告更坏,读的人会挑自己想信的那半:{line}")

    def test_fallback_alarm_carries_the_caveat(self, tmp_path):
        """兜底 + 超龄 ⇒ 报警本身也要带上「这是文件日期」,别让人照着它下结论。"""
        art = _artifact(tmp_path, trained_at=None, mtime_day=dt.date(2024, 8, 1))
        _, alarms = _probe(art, tmp_path)

        assert alarms, "兜底路径下超龄照样要响"
        assert "文件日期" in alarms[0], f"报警要自曝口径:{alarms[0]}"

    def test_trained_and_fallback_lines_are_distinguishable(self, tmp_path):
        """两种口径不许长成同一句话 —— 修之前它们就是同一句「训练于 X」。"""
        good = _artifact(
            tmp_path, trained_at="2026-08-02T00:00:00+00:00",
            mtime_day=dt.date(2026, 8, 2), name="with-key")
        bad = _artifact(
            tmp_path, trained_at=None, mtime_day=dt.date(2026, 8, 2), name="no-key")

        good_line = _artifact_line(_probe(good, tmp_path)[0])
        bad_line = _artifact_line(_probe(bad, tmp_path)[0])

        # 同一个年龄、同一个日期,只有口径不同 ⇒ 差异必须落在措辞上
        assert "· 5d" in good_line and "· 5d" in bad_line
        strip = lambda s: s.split(":", 1)[1]            # noqa: E731 — 去掉目录名
        assert strip(good_line) != strip(bad_line), (
            "「读到了训练日期」和「读不到、退到文件日期」在报告里必须能分辨,"
            f"现在两句一样:{good_line}")

    def test_corrupt_metadata_falls_back_not_crashes(self, tmp_path):
        """坏 JSON ⇒ 走兜底并标注,不炸掉整个体检(它是别人调用链上的一环)。"""
        art = tmp_path / "corrupt"
        art.mkdir()
        mp = art / "metadata.json"
        mp.write_text("{not json at all")
        _set_mtime(mp, dt.date(2026, 8, 2))

        info, alarms = _probe(art, tmp_path)
        line = _artifact_line(info)
        assert "· 5d" in line and "不是训练日期" in line
        assert alarms == []


# ------------------------------------------------- 跑着的调用点:**不传** artifact_dir

class TestTheCallShapeProductionActuallyUses:
    """⭐ 上面每一条都显式传了 `artifact_dir=`,而生产里那一行是::

        supply_info, supply_alarms = check_model_supply_chain(today)

    —— **不传**。测参数路径而生产走默认路径,又是一次「读出来的路径 ≠ 跑着的
    路径」(cf. [[two-modes-coverage-and-p-source]])。默认那条分支才是每天真的
    在跑的那条,它必须自己有用例。
    """

    def test_bare_call_resolves_the_hardcoded_default_dir(self, monkeypatch, tmp_path):
        """没有 env 时走字面量 `data/v4_model_cat`(相对 cwd),陈旧照样响。

        顺带钉住:裸调用不会因为拿不到目录就静默 —— 它得真的去看。
        """
        monkeypatch.delenv("NUTMEG_V4_ARTIFACT_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        _artifact(
            tmp_path / "data", trained_at="2024-08-01T00:00:00+00:00",
            mtime_day=TODAY, name="v4_model_cat")

        # 真·生产调用形状:除了 today 什么都不传。源树/外部目录在 tmp 下不存在 ⇒ 自动跳过。
        info, alarms = check_model_supply_chain(TODAY)

        expected_age = (TODAY - dt.date(2024, 8, 1)).days
        assert alarms, f"默认路径下的陈旧盘零告警 —— 生产跑的就是这条:{info}"
        assert str(expected_age) in alarms[0], alarms

    def test_bare_call_honours_the_env_var_serving_reads(self, monkeypatch, tmp_path):
        """有 env 时跟 env —— serving 读的是同一个变量。"""
        art = _artifact(
            tmp_path, trained_at="2024-08-01T00:00:00+00:00", mtime_day=TODAY)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(art))
        monkeypatch.chdir(tmp_path)

        _, alarms = check_model_supply_chain(TODAY)
        assert alarms and str(art) in alarms[0], alarms
