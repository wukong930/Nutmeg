"""供应链探针必须量**服务真的加载的那个盘** —— Layer B 指针要跟。

姊妹文件 `test_artifact_age_probe.py` 钉的是**哪个日期**;这里钉的是**哪个目录**。
两条是同一次审查里翻出来的两个独立的洞,缺一个红线就是瞎的。

## 起因(2026-08-07 审查)

`check_model_supply_chain` 解析目标时只到 base 就停了::

    art = Path(artifact_dir or os.environ.get("NUTMEG_V4_ARTIFACT_PATH")
               or "data/v4_model_cat")

而 serving 走 `routes._resolve_artifact()`,**会**跟 `live_artifact_pointer.json`。
Layer B 一部署,两边量的就是两个目录。用真实生产函数实测复现出双向失效:

  · **假红** — base metadata `trained_at=2025-06-01`、指针目标 `2026-08-01`。
    服务侧正确重定向到 6 天新的盘,探针却喊「已 432 天未重训」。
  · **假绿(更坏的那半)** — base `2026-08-01`、指针目标 `2025-06-01`。
    服务侧正在喂那个 432 天的旧盘,探针报「6d」并返回**零告警**。

⇒ 724 天冻结事故(`production-artifact-frozen-724d`)的疫苗,恰恰在 Layer B
生效时整个失灵。而且失灵的方向里有一个是**静默**的。

## 本文件钉的是什么

**两个方向都钉**,而且都是行为断言 —— 指针用真实的 `write_artifact_pointer()`
写(手搓 JSON 就是在测我们自己对格式的想象,不是测生产写出来的东西)。

只钉假红那半是不够的:把解析改回只看 base,假红用例会红、假绿用例**也**必须红。
一条只在「不该响时不响」上做文章的测试,挡不住「该响时不响」。

⭐ 还钉一条**等价性**:探针的解析结果必须与 `routes._resolve_artifact()` 指向
同一个目录。探针复用 `resolve_effective_artifact_path()` 而 serving 自己带 mtime
缓存地写了一遍 —— 两个实现,就有漂的余地。这条是「探针量的是服务加载的盘」这句话
唯一的地基;它一红,上面所有用例的意义都要重估。

⚠️ **本文件不按告警文案过滤。** 见 `_about()` —— 老写法 `"未重训" in a` 在
「只改措辞」的变异下让**该恒红的那条恒绿**(它断言的就是空集)。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from nutmeg.v4.api import routes
from nutmeg.v4.cli.data_freshness import (
    ARTIFACT_MAX_AGE_DAYS,
    UNABSORBED_MATCHES_ALARM,
    _artifact_age_reading,
    _serving_artifact,
    check_model_supply_chain,
)
from nutmeg.v4.observation.auto_retrain import (
    same_artifact_dir,
    write_artifact_pointer,
)

TODAY = dt.date(2026, 8, 7)

#: 审查里实测出来的两个日期。老盘 = 432 天(> 120 红线),新盘 = 6 天。
OLD = "2025-06-01"
NEW = "2026-08-01"

assert (TODAY - dt.date.fromisoformat(OLD)).days > ARTIFACT_MAX_AGE_DAYS
assert (TODAY - dt.date.fromisoformat(NEW)).days <= ARTIFACT_MAX_AGE_DAYS

#: 目录名故意互不为子串 —— `_about()` 按路径过滤,名字撞了会串。
BASE_NAME = "prod_base"
TARGET_NAME = "v_2026-Q3"


@pytest.fixture(autouse=True)
def _isolate_serving_state():
    """serving 的指针解析带进程级 mtime 缓存,不清就会串用例。"""
    routes._pointer_cache.clear()
    yield
    routes._pointer_cache.clear()


def _artifact(path: Path, trained: str | None, cutoff: str | None = None) -> Path:
    """造一个最小 artifact 目录。``trained`` 进**嵌套**的 ``trained_at_utc``
    —— 那是 `persist.save_artifact()` 写出来的真实形状(扁平形状由姊妹文件覆盖)。
    ``trained=None`` = 有目录、没 metadata.json(半途失败的部署)。"""
    path.mkdir(parents=True, exist_ok=True)
    if trained is None:
        return path
    inner: dict = {"trained_at_utc": f"{trained}T07:00:00+00:00"}
    if cutoff is not None:
        inner["training_cutoff"] = cutoff
    (path / "metadata.json").write_text(
        json.dumps({"model_type": "catboost", "metadata": inner}))
    return path


def _base(tmp_path: Path, trained: str | None, cutoff: str | None = None) -> Path:
    return _artifact(tmp_path / BASE_NAME, trained, cutoff)


def _target(tmp_path: Path, trained: str | None, cutoff: str | None = None) -> Path:
    return _artifact(tmp_path / "layer_b" / TARGET_NAME, trained, cutoff)


def _point(base: Path, target: Path | str) -> None:
    """用**生产的写入函数**下指针 —— 不手搓 JSON。"""
    write_artifact_pointer(
        base,
        version="v_2026-Q3",
        artifact_path=str(target),
        previous_version=None,
        ship_gate_log_loss_delta=0.0024,
        ship_gate_p_value=0.018,
        n_train=12000,
        n_holdout=200,
        train_window=("2023-08-01", "2026-04-30"),
        holdout_window=("2026-05-01", "2026-06-30"),
    )


def _run(base: Path, tmp_path: Path):
    return check_model_supply_chain(
        TODAY, artifact_dir=base,
        sources_dir=tmp_path / "no_sources", external_dir=tmp_path / "no_external")


def _about(alarms: list[str], art: Path) -> list[str]:
    """挑出「关于**这个盘**」的告警 —— 按**路径**过滤,不按文案。

    ⛔ 老写法是 `[a for a in alarms if "未重训" in a]`。实测把措辞改一改(纯变异,
    行为不动):三条该红的确实红了,而 `test_false_red_*` 那条**恒绿** —— 它断言
    过滤结果是空集,而过滤器在措辞不匹配时本来就返回空集。一个在措辞变化下永远
    绿的用例挡不住任何东西,却会让人以为这个方向有人守。

    路径是**用例自己造的数据**,不是被测代码的措辞;探针的契约是「每条关于某个
    artifact 的告警都带那个盘的路径」,这条契约写在 `check_model_supply_chain`
    的 docstring 里。
    """
    return [a for a in alarms if str(art) in a]


# --------------------------------------------------------------- 两个方向

class TestFollowsThePointerBothWays:
    def test_false_red_stale_base_but_pointer_to_a_fresh_artifact(self, tmp_path):
        """假红:base 旧 + 指针指向新盘 ⇒ **生效盘**不该被喊超龄。

        Layer B 部署后 base 停在旧盘是设计如此(它是 rollback 的落点)。
        对着**生效盘**告警 = 又在量 base。

        ⚠️ 这里不能断言 `alarms == []` —— base 陈旧会另外触发一条「出注 cron 仍在
        加载 base」的告警(见 `TestBaseAgeNoteAndTheBettingPathAlarm`),那条是对的。
        断言要精确到「关于哪个盘」。
        """
        base = _base(tmp_path, OLD)
        target = _target(tmp_path, NEW)
        _point(base, target)

        info, alarms = _run(base, tmp_path)

        assert _about(alarms, target) == [], (
            f"服务侧已重定向到 6 天新的盘,探针却在喊它超龄 —— 又在量 base:{alarms}")
        assert any("6d" in i and TARGET_NAME in i for i in info), info

    def test_false_green_fresh_base_but_pointer_to_a_stale_artifact(self, tmp_path):
        """⭐⭐ 承重条,假绿(更坏的那半):base 新 + 指针指向旧盘 ⇒ **必须**告警。

        服务侧此刻正在喂那个 432 天的旧盘。量 base 的探针会报「6d · 零告警」——
        724 天冻结事故的疫苗在这里静默失效,而静默失效没有任何外部症状。
        """
        base = _base(tmp_path, NEW)
        target = _target(tmp_path, OLD)
        _point(base, target)

        info, alarms = _run(base, tmp_path)

        hit = _about(alarms, target)
        assert hit, (
            "服务正在加载一个 432 天的盘而探针零告警 —— 这正是 724 天冻结的形状,"
            f"info={info} alarms={alarms}")

    def test_no_pointer_still_measures_the_base(self, tmp_path):
        """没有 Layer B 时行为不变 —— 修完不能只在有指针时才对。"""
        base = _base(tmp_path, OLD)
        info, alarms = _run(base, tmp_path)
        assert _about(alarms, base), f"裸 base 超龄照样得响:{info}"
        assert not [i for i in info if i.startswith("NOTE base")], (
            f"没重定向就没有「base vs 生效盘」之分,别凭空多一行:{info}")

    def test_pointer_to_a_missing_dir_falls_back_like_serving_does(self, tmp_path):
        """指针目标不存在 ⇒ serving 回落到 base,探针也必须回落到 base。

        否则会出现「探针量一个根本没人加载的路径」的第三种错法。
        """
        base = _base(tmp_path, OLD)
        _point(base, tmp_path / "gone")

        assert _serving_artifact(base)[1] == base
        assert _about(_run(base, tmp_path)[1], base), (
            "指针悬空时服务吃的是 base(旧盘),探针必须跟着量 base")

    def test_half_deployed_pointer_target_alarms_instead_of_going_quiet(self, tmp_path):
        """⭐ 指针目标**是个存在的目录**但里面没有 metadata.json ⇒ 必须告警。

        `resolve_effective_artifact_path` 只在 `is_dir()` 为真时才重定向,所以这个
        形状是真实可达的:训练目录建好、盘还没落全就写了指针(半途失败的部署)。

        修之前:年龄读不出 ⇒ 走「artifact 不存在 — 跳过」那条 info,base 又被降级成
        NOTE ⇒ **整体零告警**。而**同样这个场景没有指针时是会告警的** —— 也就是说
        下一个指针反而让红线闭嘴了。第三种静默失效。
        """
        base = _base(tmp_path, NEW)
        target = _target(tmp_path, None)          # 目录在,metadata.json 没有
        _point(base, target)

        info, alarms = _run(base, tmp_path)

        assert _about(alarms, target), (
            f"服务正在加载一个量不了年龄的盘,探针却零告警:info={info} alarms={alarms}")
        assert not any("不存在" in i and str(target) in i for i in info), (
            f"这个目录是**存在**的,别对它说「不存在」——会把人指向错误的排查方向:{info}")


# ------------------------------------------------ base:NOTE + 出注路径那条告警

class TestBaseAgeNoteAndTheBettingPathAlarm:
    """决定(2026-08-07,owner 拍板;理由写在 `check_model_supply_chain` 里):
    base 的**陈旧本身**只进 info;告警的判据是「**出注那条路仍在加载 base**」。"""

    def test_stale_base_is_reported_as_a_note(self, tmp_path):
        base = _base(tmp_path, OLD)
        _point(base, _target(tmp_path, NEW))

        info, _ = _run(base, tmp_path)
        note = [i for i in info if i.startswith("NOTE base")]
        assert note, f"回滚落点的年龄被藏起来了: {info}"
        assert OLD in note[0], note

    def test_stale_base_also_alarms_because_recommend_still_loads_it(self, tmp_path):
        """⭐ 面板/health 吃生效盘,而**注单吃 base**,且 `do_deploy` 从不刷新 base。

        ⇒ 第一次 Layer B deploy 之后,base 就是一个没人重训、却仍在生成注单的盘。
        只报 NOTE 不告警,等于把钱那条路上的陈旧模型静音。前提见
        `TestTheBettingPathPremise` —— 前提一旦不成立,这条告警就该删。
        """
        base = _base(tmp_path, OLD)
        _point(base, _target(tmp_path, NEW))

        _, alarms = _run(base, tmp_path)
        assert _about(alarms, base), f"出注路径吃着一个 432 天的盘,零告警:{alarms}"

    def test_fresh_base_under_a_pointer_does_not_alarm(self, tmp_path):
        """base 还新 ⇒ 只有 NOTE,没有告警。判据是**陈旧**,不是「有指针」——
        否则这条会退化成「部署过 Layer B 就每天一条红」,老误报最后会被删掉。"""
        base = _base(tmp_path, NEW)
        _point(base, _target(tmp_path, NEW))

        info, alarms = _run(base, tmp_path)
        assert [i for i in info if i.startswith("NOTE base")], info
        assert alarms == [], f"base 还新,不该有任何告警:{alarms}"

    def test_the_redirect_itself_is_visible(self, tmp_path):
        """报告要说清「以下年龄量的是哪个目录」,否则读的人会以为在读 base。"""
        base = _base(tmp_path, OLD)
        target = _target(tmp_path, NEW)
        _point(base, target)

        info, _ = _run(base, tmp_path)
        assert any("Layer B 指针生效" in i and str(target) in i for i in info), info


class TestTheBettingPathPremise:
    """⭐ 上面那条 base 告警的**前提**要有人查 —— 本仓反复栽在「检查的前提没人检查」。

    前提:出注 cron(`com.nutmeg.{morning,daily}_recommend`)不传 `--model`,吃
    `cli/recommend.py` 的 argparse 默认值,既不读 `NUTMEG_V4_ARTIFACT_PATH` 也不跟
    Layer B 指针。⇒ 它加载的就是 base。

    这条测试红了 = 前提不再成立 = **那条告警该删了**,而不是「测试坏了」。
    """

    def test_recommend_cli_loads_the_base_ignoring_env_and_pointer(
            self, monkeypatch, tmp_path):
        """按 cron 的调用形状跑 `recommend.main()`(不传 `--model`),看它把哪个
        路径交给 `load_artifact` —— 行为断言,不是「源码里有没有某个字符串」。"""
        from nutmeg.v4.cli import recommend

        base = _base(tmp_path, NEW)
        _point(base, _target(tmp_path, OLD))
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))

        class _Stop(Exception):
            pass

        seen: dict[str, str] = {}

        def _capture(path):
            seen["model"] = path
            raise _Stop

        monkeypatch.setattr(recommend, "_read_fixtures", lambda p: [])
        monkeypatch.setattr(recommend, "load_artifact", _capture)

        with pytest.raises(_Stop):
            recommend.main(["--fixtures", str(tmp_path / "fixtures.csv")])

        assert seen["model"] == "data/v4_model_cat", (
            "出注 CLI 现在解析到了别的东西 —— 如果它已经会跟 Layer B 指针/env 了,"
            "`check_model_supply_chain` 里那条「出注 cron 仍在加载 base」的告警"
            f"就该删掉。拿到:{seen['model']}")


# --------------------------------------- 同一个目录的两种拼法 ≠ 重定向

class TestSpellingIsNotARedirect:
    """⭐ `redirected` 不许用字符串比较。

    `.env` 写相对路径而 `run_local_server.sh` 导出绝对路径 —— 两者是同一个目录,
    字符串却不相等。`routes.py` 早就为这个理由留了 `_same_dir`(见 /health 里
    `artifact_redirected` 那段注释),探针这边却写成 `str(art) != str(base)`。

    实跑后果:同一份报告里同时出现「432d 告警(生效盘)」和「NOTE base:陈旧不
    告警」两行**自相矛盾**的话,说的其实是同一个目录。
    """

    @pytest.mark.parametrize("spell", ["absolute", "dotdot"])
    def test_same_dir_spelled_differently_is_not_a_redirect(
            self, monkeypatch, tmp_path, spell):
        monkeypatch.chdir(tmp_path)
        _base(tmp_path, OLD)
        base_rel = Path(BASE_NAME)                     # 相对写法(`.env` 的形状)
        other = (str(tmp_path / BASE_NAME) if spell == "absolute"
                 else str(tmp_path / "layer_b" / ".." / BASE_NAME))
        (tmp_path / "layer_b").mkdir(exist_ok=True)
        _point(base_rel, other)

        info, alarms = _run(base_rel, tmp_path)

        assert not [i for i in info if i.startswith("NOTE base")], (
            f"同一个目录被当成 base + 生效盘两个东西了({spell}):{info}")
        assert not any("Layer B 指针生效" in i for i in info), info
        assert len(alarms) == 1, (
            f"一个陈旧目录应该只产生一条告警,不是「超龄告警 + base 告警」两条:{alarms}")


# ------------------------------------------ 未吸收比赛探针也必须读生效盘

class TestUnabsorbedProbeAlsoFollowsThePointer:
    def test_cutoff_comes_from_the_serving_artifact(self, tmp_path):
        """同一个洞的第二个出口:`training_cutoff` 读错盘 ⇒ 积压被藏。

        base 的 cutoff 很新(积压=0),生效盘的 cutoff 很旧(积压一大批)。
        量 base 的探针会安静;量生效盘的必须喊。
        """
        pd = pytest.importorskip("pandas")

        base = _base(tmp_path, NEW, cutoff="2026-06-01")
        target = _target(tmp_path, NEW, cutoff="2020-01-01")
        _point(base, target)

        src = tmp_path / "src" / "europe" / "2526"
        src.mkdir(parents=True)
        n = UNABSORBED_MATCHES_ALARM + 50
        start = pd.Timestamp("2021-01-01")
        rows = [((start + pd.Timedelta(days=i)).strftime("%d/%m/%Y"),
                 f"H{i}", f"A{i}", 2, 1) for i in range(n)]
        frame = pd.DataFrame(rows, columns=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        frame["FTR"] = "H"
        frame.insert(0, "Div", "E0")
        frame.to_csv(src / "E0.csv", index=False)

        info, alarms = check_model_supply_chain(
            TODAY, artifact_dir=base, sources_dir=tmp_path / "src",
            external_dir=tmp_path / "no_external")

        assert [a for a in alarms if "从没见过" in a], (
            f"cutoff 读的是 base(2026-06-01)⇒ 积压被藏。info={info}")


# ------------------------------------------------- 与 serving 的解析必须等价

class TestResolutionMatchesServing:
    """探针复用 `resolve_effective_artifact_path()`,serving 自己带缓存地写了
    一遍同样的规则。两个实现 = 有漂的余地,这条把它们焊在一起。"""

    @pytest.mark.parametrize("with_pointer", [False, True])
    def test_probe_resolves_to_exactly_what_serving_loads(
            self, monkeypatch, tmp_path, with_pointer):
        base = _base(tmp_path, NEW)
        if with_pointer:
            _point(base, _target(tmp_path, OLD))

        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        routes._pointer_cache.clear()

        serving = routes._resolve_artifact()
        probe_base, probe_effective = _serving_artifact()

        # ⚠️ 比目录不比字符串 —— 尾斜杠/相对写法会让字面比较假红。
        assert same_artifact_dir(probe_effective, serving.path), (
            "探针和 serving 解析到了不同的目录 —— 「探针量的是服务加载的盘」不成立了")
        assert same_artifact_dir(probe_base, serving.base)
        assert (not same_artifact_dir(probe_effective, probe_base)) is bool(
            with_pointer)

    def test_trailing_slash_in_the_env_var_is_the_same_dir(self, monkeypatch, tmp_path):
        """`.env` 里多一个尾斜杠不该改变任何判断(字面比较会在这里假红)。"""
        base = _base(tmp_path, NEW)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base) + "/")
        routes._pointer_cache.clear()

        probe_base, probe_effective = _serving_artifact()
        assert same_artifact_dir(probe_base, base)
        assert same_artifact_dir(probe_effective, routes._resolve_artifact().path)

    def test_probe_honors_the_env_var_serving_reads(self, monkeypatch, tmp_path):
        """base 侧不 import routes(不把 FastAPI 拖进 cron 哨兵),所以「读的是
        同一个环境变量」要单独钉一次。"""
        base = _artifact(tmp_path / "elsewhere", NEW)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        assert _serving_artifact()[0] == base

    def test_explicit_argument_beats_the_env_var(self, monkeypatch, tmp_path):
        """体检/测试传进来的目录优先 —— 否则用例会被机器上的 `.env` 污染。"""
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_path / "env_one"))
        explicit = _artifact(tmp_path / "explicit", NEW)
        assert _serving_artifact(explicit)[0] == explicit

    def test_bare_call_follows_the_pointer_too(self, monkeypatch, tmp_path):
        """⭐ 生产那一行是 `check_model_supply_chain(today)` —— **不传** artifact_dir。
        上面的用例全都显式传了目录;默认那条分支才是每天真的在跑的那条。"""
        base = _base(tmp_path, NEW)
        target = _target(tmp_path, OLD)
        _point(base, target)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        monkeypatch.chdir(tmp_path)

        info, alarms = check_model_supply_chain(TODAY)
        assert _about(alarms, target), (
            f"不传参数时没跟指针 —— 生产跑的正是这条:info={info} alarms={alarms}")


# ------------------------------------------------------- 三态:没有 / 读不出 / 读到了

class TestAgeReadingIsThreeStates:
    def test_missing_metadata_is_none_not_a_guess(self, tmp_path):
        """None = 「这里没有盘」。既不是新也不是旧。"""
        assert _artifact_age_reading(tmp_path / "nope") is None

    def test_old_format_artifact_falls_back_to_mtime_and_says_which(self, tmp_path):
        """`47435ce` 之前的 artifact 没有 `trained_at_utc`,但它们**存在** ——
        读不出日期不能折成「这里没有盘」(又一次「分不出没有和没去看」)。
        退到 mtime 时第二格必须是 `mtime`,调用方才能在报告里说出口径。"""
        import os

        art = tmp_path / "old"
        art.mkdir()
        meta = art / "metadata.json"
        meta.write_text(json.dumps({"model_type": "lightgbm"}))
        stamp = dt.datetime(2024, 8, 1, tzinfo=dt.UTC).timestamp()
        os.utime(meta, (stamp, stamp))

        reading = _artifact_age_reading(art)
        assert reading is not None
        assert reading[0] == dt.date(2024, 8, 1)
        assert reading[1] == "mtime", f"退到文件日期时口径必须能被调用方看见:{reading}"

    def test_readable_artifact_reports_trained(self, tmp_path):
        reading = _artifact_age_reading(_artifact(tmp_path / "good", NEW))
        assert reading == (dt.date.fromisoformat(NEW), "trained")
