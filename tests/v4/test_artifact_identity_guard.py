"""服务盘身份闸 —— 「加载成功了」≠「加载的是我们指定的那个」。

起因(2026-08-07):`routes.DEFAULT_ARTIFACT_PATH` 是 `data/v4_model`(落后生产
4,871 场的 2025-06 LightGBM 老盘),生产靠 `.env` 的 `NUTMEG_V4_ARTIFACT_PATH`
顶着。当时没有活跃敞口(launchd 显式 `source .env` + `load_dotenv()` 向上查找,
两道机制挡着),但 `.env` 一丢就是**静默降级**:老盘存在、能 load、
`artifact_loaded=True`、`status="ok"`、`model_type` 有值 —— 没有任何东西会响。

⭐ 本文件的**唯一价值**是能分辨「回退了」和「没回退」。所以断言全部写成行为
断言(把 resolver 抠出来真跑一遍、把 /health 真请求一遍),不写「源码里有没有
某个字符串」那种语法代理 —— 本项目在那上面栽过三次(见
`tests/v4/test_market_handicap_gate_lower_bound.py` 的同类注记)。唯一一条文本
断言在文件末尾,并明确标注为**补充**。

⛔ 判据不许用「目录存在」也不许用 `artifact_loaded` —— 老盘两样都满足。
"""
from __future__ import annotations

import ast
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api import routes
from nutmeg.v4.cli import artifact_identity as ai
from nutmeg.v4.observation.auto_retrain import LIVE_ARTIFACT_POINTER_FILENAME

REPO_ROOT = Path(__file__).resolve().parents[2]

# 出事那天的错误答案。钉住这个**具体的值**,而不是「不等于 EXPECTED」——
# 后者在 EXPECTED 自己被改坏时会一起变绿。
STALE_ARTIFACT = "data/v4_model"


@pytest.fixture(autouse=True)
def _isolate_serving_state():
    """每个用例前后清 artifact / pointer 缓存。

    resolver 带两层进程级缓存,不清的话第二个用例会读到第一个用例的答案 ——
    那正是「测试替身抹掉守卫」的同族坑。
    """
    routes.clear_artifact_cache()
    routes._pointer_cache.clear()
    yield
    routes.clear_artifact_cache()
    routes._pointer_cache.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v4-test")
    return TestClient(app)


# ---------------------------------------------------------------- 兜底值本身

def test_unset_env_no_longer_falls_back_to_the_stale_artifact(monkeypatch):
    """变量缺失 ⇒ **不是**静默加载 `data/v4_model`。

    这是原始 bug 的直接复现口:删掉 `.env` 就是这个状态。
    """
    monkeypatch.delenv("NUTMEG_V4_ARTIFACT_PATH", raising=False)
    res = routes._resolve_artifact()

    assert res.source == "default", "没设变量却报成 env,provenance 是假的"
    assert not routes._same_dir(res.base, STALE_ARTIFACT), (
        f"兜底值又回到 {STALE_ARTIFACT} —— .env 一丢就静默服老 LightGBM 盘")
    assert routes.artifact_is_expected(), (
        "兜底值必须**就是**预期服务盘:两个字面量迟早会漂,"
        "DEFAULT_ARTIFACT_PATH 必须绑在 EXPECTED_SERVING_ARTIFACT 上")


def test_env_and_default_are_the_same_single_value(monkeypatch):
    """兜底 = 预期,而且只有**一个**字面量。

    上次出事的机制就是「两个地方各写一份、只改了一份」。同一个符号无法自己
    和自己漂移。
    """
    assert routes.DEFAULT_ARTIFACT_PATH == routes.EXPECTED_SERVING_ARTIFACT


def test_the_declared_artifact_is_pinned_by_value():
    """⭐ 钉住**这个具体的值**,不是「不等于老盘」。

    ⚠️ 审查(2026-08-07)逮到的洞:上面那两条一条禁 `data/v4_model`、一条比较
    两个符号,合起来**挡不住把 EXPECTED 改成第三个值**。把它改成
    `data/v4_model_cat_lineups`(生产里真实存在的兄弟目录,而且是**冻结在
    2024-08 的**那个)⇒ 全套绿、`.env` 一丢就服它,而 `artifact_is_expected=True`
    —— 因为常量在**跟自己比**。护栏反过来给错的模型背书。

    同 P0-3 修 δ 常数时的做法:恒真断言换成字面量 + 出处。
    改这个值 = 换生产盘,请照 `routes.py` 里那张清单**逐条**改完再改这里。
    """
    assert routes.EXPECTED_SERVING_ARTIFACT == "data/v4_model_cat", (
        "生产服务盘 = data/v4_model_cat(CatBoost,2026-07-15 重训解冻,"
        "见记忆 production-artifact-frozen-724d)。改这条前先读 routes.py 的换盘清单。")


# ------------------------------------------------------------ 指错盘会被逮到

def test_env_pointing_at_an_unexpected_dir_is_flagged(monkeypatch, tmp_path):
    other = tmp_path / "some_other_model"
    other.mkdir()
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(other))

    assert routes._resolve_artifact().source == "env"
    assert routes.artifact_is_expected() is False


def test_env_pointing_at_a_nonexistent_dir_is_still_judged(monkeypatch, tmp_path):
    """判据不依赖目录存在。

    「不存在」和「存在但不是那个」都必须判 False,而且**理由不同**:前者
    `artifact_loaded` 也会 False(旧信号够用),后者旧信号全绿 —— 身份闸要
    在两种情况下都给出同一个答案,否则它其实是在测存在性。
    """
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_path / "never_created"))
    assert routes.artifact_is_expected() is False


@pytest.mark.parametrize("form", ["relative", "absolute"])
def test_expected_path_passes_in_both_shipped_forms(monkeypatch, form):
    """`.env` 写相对路径、`run_local_server.sh` 导出绝对路径 —— 两种都是对的。

    没有这条,身份闸会把 `run_local_server.sh` 起的 server 判成红。
    """
    expected = routes.EXPECTED_SERVING_ARTIFACT
    value = expected if form == "relative" else str(Path(os.getcwd()) / expected)
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", value)
    assert routes.artifact_is_expected() is True


# --------------------------------------------------- Layer B 重定向不算跑偏

def test_layer_b_redirect_from_expected_base_stays_expected(monkeypatch, tmp_path):
    """指针把服务指向别处是**合法**的 —— 只要它躺在预期 base 里。

    判据必须落在 base 上而不是生效路径上:指针文件本身就存在预期 base 目录内,
    base 对了才是指针可信的理由。
    """
    base = tmp_path / "expected_base"
    base.mkdir()
    target = tmp_path / "layer_b" / "v_2026-Q3"
    target.mkdir(parents=True)
    (base / LIVE_ARTIFACT_POINTER_FILENAME).write_text(
        json.dumps({"version": "v_2026-Q3", "artifact_path": str(target)}))

    monkeypatch.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(base))
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
    routes._pointer_cache.clear()

    res = routes._resolve_artifact()
    assert res.base == str(base)
    assert res.path == str(target)
    assert res.redirected is True
    assert routes.artifact_is_expected() is True, (
        "把判据算在生效路径上了 —— Layer B 一部署就会误报红")


def _artifact_meta(path: Path, trained_at: str) -> Path:
    """给一个目录装上 `metadata.json`,形状对齐 `persist.save_artifact()`。

    Layer B 的目标盘是否「更旧」全靠这个文件回答,所以测试里也必须真写文件 ——
    这些用例问的正是「磁盘上那个盘是什么」。
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / "metadata.json").write_text(json.dumps(
        {"metadata": {"trained_at_utc": trained_at}, "feature_columns": ["f0"]}))
    return path


class TestRedirectTargetIsVisible:
    """⭐ 身份闸判 base 是**刻意**的(指针文件就住在 base 里,base 对了才是指针
    可信的理由)—— 但那条豁免此前对**目标**零约束。

    审查实测(2026-08-07):用出厂 CLI 把 `data/v4_model_cat` 的指针写成指向
    `data/v4_model`(2026-05-22 的退役 LightGBM),`/health` 回
    `artifact_is_expected: true` / `status: ok` / `detail: null`,§18 exit 0 并
    打印一行 OK **点名那个陈旧盘**。判据不改(改了 Layer B 每次部署都误报红,
    而误报的护栏最后会被删掉),补的是**目标的可见性**。
    """

    STALE, LIVE = "2026-05-22T06:17:04+00:00", "2026-07-15T06:19:12+00:00"

    def _redirect(self, monkeypatch, tmp_path, target_trained_at):
        base = _artifact_meta(tmp_path / "serving_base", self.LIVE)
        target = _artifact_meta(tmp_path / "elsewhere" / "target",
                                target_trained_at) \
            if target_trained_at else (tmp_path / "elsewhere" / "target")
        target.mkdir(parents=True, exist_ok=True)
        (base / LIVE_ARTIFACT_POINTER_FILENAME).write_text(
            json.dumps({"version": "v_x", "artifact_path": str(target)}))
        monkeypatch.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(base))
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        routes._pointer_cache.clear()
        return base, target

    def test_a_pointer_at_an_older_artifact_is_warned_not_noted(
            self, monkeypatch, tmp_path):
        """⭐ 承重条。WARN 而不是 NOTE —— 两者在 bash 侧都不改退出码(只有
        `fail()` 设 EXIT_CODE=1),差的是看得见的程度:`note()` 是灰色暗字,
        在整段体检里就是背景噪音。也不判红:显式 `--override-identity` 的人是
        故意的,判红就是假红。拦截在部署侧,这里只负责看得见。
        """
        base, target = self._redirect(monkeypatch, tmp_path, self.STALE)
        rows = ai.disk_rows()

        assert [r.severity for r in rows] == [ai.OK, ai.WARN], rows
        assert str(target) in rows[1].message, "没说指到哪"
        assert self.STALE in rows[1].message, "没说目标盘多新 —— 「指到哪」还差一半"

    def test_a_pointer_at_a_newer_artifact_stays_a_note(self, monkeypatch, tmp_path):
        """反向,防假红:Layer B 正常部署(候选更新)不该让体检变吵。

        没有这一条,上面那条也可能只是因为**一重定向就 WARN** —— 「逮到了」和
        「见谁咬谁」在单个断言上分不出来。
        """
        base, target = self._redirect(monkeypatch, tmp_path, "2026-10-01T00:00:00+00:00")
        rows = ai.disk_rows()

        assert [r.severity for r in rows] == [ai.OK, ai.NOTE], rows
        assert str(target) in rows[1].message
        assert "2026-10-01" in rows[1].message

    def test_a_pointer_at_a_dir_with_no_metadata_is_warned(self, monkeypatch, tmp_path):
        """目标目录存在但没有 metadata ⇒ 服务会重定向过去然后加载失败。
        「读不到」既不是新也不是旧,必须说出来,不能沉默成 NOTE。"""
        base, target = self._redirect(monkeypatch, tmp_path, None)
        rows = ai.disk_rows()

        assert [r.severity for r in rows] == [ai.OK, ai.WARN], rows
        assert str(target) in rows[1].message

    def test_health_reports_the_redirect_as_a_field(self, monkeypatch, tmp_path):
        """`/health` 必须把「重定向了没有」当成**字段**给出来。

        消费方拿 base 和 path 做字符串比较是错的:`.env` 写相对路径而
        `run_local_server.sh` 导出绝对路径,两者指同一个目录时字符串并不相等
        (`_same_dir` 存在就是为了这个)⇒ 字符串比较会把「没重定向」读成
        「重定向了」。
        """
        base, target = self._redirect(monkeypatch, tmp_path, self.STALE)
        body = _client().get("/api/v4-test/v4/health").json()

        assert body["artifact_is_expected"] is True, "判据被改成生效路径了 —— 会假红"
        assert body["artifact_redirected"] is True
        assert body["artifact_base_path"] == str(base)
        assert body["artifact_path"] == str(target)

    def test_health_says_not_redirected_when_there_is_no_pointer(
            self, monkeypatch, tmp_path):
        base = _artifact_meta(tmp_path / "serving_base", self.LIVE)
        monkeypatch.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(base))
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        routes._pointer_cache.clear()

        body = _client().get("/api/v4-test/v4/health").json()
        assert body["artifact_redirected"] is False

    def test_health_response_refuses_to_be_built_without_a_redirect_verdict(self):
        """`artifact_redirected` 没有默认值 —— 同 `artifact_is_expected` 的理由:
        漏填会**静默**落成 falsy,而 falsy 读作「没有重定向」,恰好是让人放心的
        那个答案。"""
        from pydantic import ValidationError

        from nutmeg.v4.api.schemas import HealthResponse

        with pytest.raises(ValidationError):
            HealthResponse(status="ok", artifact_loaded=True,
                           artifact_path="x", artifact_is_expected=True)


def test_layer_b_redirect_from_an_unexpected_base_is_still_flagged(
        monkeypatch, tmp_path):
    """反向:base 不对时,指针不能把它「洗白」。"""
    base = tmp_path / "wrong_base"
    base.mkdir()
    target = tmp_path / "layer_b" / "v_2026-Q3"
    target.mkdir(parents=True)
    (base / LIVE_ARTIFACT_POINTER_FILENAME).write_text(
        json.dumps({"version": "v_2026-Q3", "artifact_path": str(target)}))

    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
    routes._pointer_cache.clear()

    assert routes._resolve_artifact().redirected is True
    assert routes.artifact_is_expected() is False


# ------------------------------------------------------------------- /health

@pytest.fixture(scope="module")
def a_loadable_but_wrong_artifact(tmp_path_factory):
    """现造一个**真能 load** 的 artifact —— 不依赖仓库里任何已提交目录。

    ⚠️ 这条 fixture 的存在本身是审查(2026-08-07)的产物。原来核心用例挂着
    `@pytest.mark.skipif(not (REPO_ROOT / "data/v4_model").exists())` ——
    而 `data/v4_model` 正是这次修复**最自然的后续动作要删掉的那个目录**。
    实测的 2×2 是决定性的:

        护栏完好 + fixture 在 → 34 passed
        护栏完好 + fixture 不在 → 14 passed, 20 skipped
        护栏打坏 + fixture 在 → 1 failed          ← 逮到
        护栏打坏 + fixture 不在 → 14 passed, 20 skipped, 0 failed  ← 没逮到

    第 2、4 格的汇总**逐字节相同**。也就是说删掉那个目录之后,护栏坏没坏
    在输出上分不出来 —— 又一个「分不出『没有』和『没去看』」。

    ⇒ 不要把测试的核心断言 gate 在一个可能被合理删除的数据目录上。自己造。
    """
    import lightgbm as lgb
    import numpy as np

    from nutmeg.v4.model.persist import TeamState, V4Artifact, save_artifact

    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 1))
    y = 1.3 + 0.2 * X[:, 0]
    booster = lgb.train(
        {"objective": "regression", "verbose": -1,
         "min_data_in_leaf": 1, "min_data_in_bin": 1, "num_leaves": 2},
        lgb.Dataset(X, label=y), num_boost_round=2,
    )
    art = V4Artifact(
        metadata={"trained_at_utc": "2025-06-01T00:00:00+00:00",
                  "training_cutoff": "2025-06-01"},
        feature_columns=["f0"],
        booster_home=booster, booster_away=booster,
        temperature_T=1.0,
        team_state={"ENG_PL": {"Arsenal": TeamState(
            elo=1500.0, goals_for=[], goals_against=[], shots=[],
            shots_on_target=[], last_match_iso=None)}},
        model_type="lightgbm",
    )
    out = tmp_path_factory.mktemp("wrong") / "some_other_artifact"
    save_artifact(art, out)
    return out


def test_a_loadable_artifact_can_still_be_the_wrong_one(
        monkeypatch, a_loadable_but_wrong_artifact):
    """⭐ 核心用例:盘**加载得好好的**,身份闸照样说不对。

    `status == "ok"` + `artifact_loaded is True` + `artifact_is_expected is False`
    三者同时成立 —— 这正是为什么前两个不能当代理,也是这个洞能潜伏的原因。
    (老盘 `data/v4_model` 就是这个形状的一个实例;这里用现造的等价物,
    好处是**不会因为将来删掉那个目录而静默跳过**。)
    """
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(a_loadable_but_wrong_artifact))
    body = _client().get("/api/v4-test/v4/health").json()

    assert body["status"] == "ok"
    assert body["artifact_loaded"] is True          # 旧信号:全绿
    assert body["artifact_is_expected"] is False    # 新信号:逮到了
    assert body["expected_artifact_path"] == routes.EXPECTED_SERVING_ARTIFACT
    assert body["artifact_path_source"] == "env"
    assert body["detail"], "判红了却不说为什么,运维看不懂"


def test_health_response_refuses_to_be_built_without_a_verdict():
    """schema 层:`artifact_is_expected` 没有默认值。

    有默认值的话,将来新加的分支漏填会**悄悄**变成那个默认值 —— 而不管默认成
    True 还是 False,读的人都拿不到「这个分支根本没判」这个事实。这里直接试着
    造一个不带该字段的响应,断言它造不出来。
    """
    from pydantic import ValidationError

    from nutmeg.v4.api.schemas import HealthResponse

    with pytest.raises(ValidationError):
        HealthResponse(status="ok", artifact_loaded=True, artifact_path="x")


def test_health_reports_identity_even_when_artifact_is_missing(
        monkeypatch, tmp_path):
    """degraded 分支必须带**全部四个**身份字段,不只是那个必填的。

    ⚠️ 原来这条只查 `artifact_is_expected`。另外三个是 `Optional[...] = None`,
    所以将来有人动 degraded 分支、把 `**identity` 拆散或漏掉,它们会**静默**
    落回 None 而 pydantic 照收 —— 正是 schema 注释说要避免的那个 falsy 默认洞。
    后果具体:§18 判红那行拼的是 `daemon 正在服 {artifact_base_path}`,于是在
    「既 degraded 又指错盘」这个**最该说清楚**的时刻,运维读到的是
    「daemon 正在服 None」。§18 磁盘侧的 provenance 判断也整个建在
    `artifact_path_source` 上。
    """
    missing = tmp_path / "does_not_exist"
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(missing))
    body = _client().get("/api/v4-test/v4/health").json()

    assert body["status"] == "degraded"
    assert body["artifact_loaded"] is False
    assert body["artifact_is_expected"] is False
    assert body["expected_artifact_path"] == routes.EXPECTED_SERVING_ARTIFACT
    assert body["artifact_base_path"] == str(missing), "base 丢了 ⇒ §18 会打印 None"
    assert body["artifact_path_source"] == "env"


# ------------------------------------------- 身份判定不该被 I/O 噎死 / 不该重复解析

class TestVerdictSurvivesBadPaths:
    """⚠️ 身份闸必须在**它本该报告的那种配置错误**下still给出判词,而不是自己炸掉。

    原来 `artifact_is_expected()` 绕道 `_resolve_artifact()` 拿 base,后者必然
    `stat()` 一次指针文件,而那个 `try` 只捕 `FileNotFoundError`。
    `NotADirectoryError` / `PermissionError` 是 `OSError` 的**兄弟不是子类** ⇒
    异常一路穿出 ⇒ `/health` 500 ⇒ §18 把 500 误诊成「包未装 / import 失败」。
    """

    def test_base_pointing_at_a_file_still_gets_a_verdict(self, monkeypatch, tmp_path):
        """`.env` 打错成 `…/metadata.json` 这种。"""
        f = tmp_path / "metadata.json"
        f.write_text("{}")
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(f))
        assert routes.artifact_is_expected() is False       # 不抛异常
        r = _client().get("/api/v4-test/v4/health")
        assert r.status_code == 200, "配置写错不该让 /health 500"
        body = r.json()
        assert body["artifact_is_expected"] is False
        assert body["artifact_base_path"] == str(f)

    def test_unreadable_base_still_gets_a_verdict(self, monkeypatch, tmp_path):
        """目录在 restore/chown 后丢了读权限。"""
        d = tmp_path / "locked"
        d.mkdir()
        d.chmod(0o000)
        try:
            monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(d))
            assert routes.artifact_is_expected() is False
            assert _client().get("/api/v4-test/v4/health").status_code == 200
        finally:
            d.chmod(0o755)                                   # 让 tmp_path 能被清掉

    def test_a_half_written_artifact_degrades_loudly_not_a_500(
            self, monkeypatch, tmp_path):
        """⭐ `nutmeg-train` 被打断 / rsync 没传完:目录在,metadata.json 不在。

        原来 `load_artifact` 抛的异常穿出 ⇒ /health **500**。§18 的 daemon 探针
        会正确判红,但只说得出「服务坏了」,说不出坏在哪。
        现在:200 + degraded + **原因写在 detail 里** ——「盘没配」和「盘配了但坏了」
        必须能分开,否则又是一个「分不出没有和没去看」。
        """
        half = tmp_path / "half_written"
        half.mkdir()
        (half / "booster_home.txt").write_text("partial")     # metadata.json 缺失
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(half))
        r = _client().get("/api/v4-test/v4/health")
        assert r.status_code == 200, "半成品 artifact 把 /health 打成了 500"
        body = r.json()
        assert body["status"] == "degraded"
        assert body["artifact_loaded"] is False
        assert "FileNotFoundError" in (body["detail"] or ""), (
            f"没说清为什么加载不了,只说了『没找到』:{body['detail']!r}")

    def test_a_missing_dir_and_a_broken_dir_say_different_things(
            self, monkeypatch, tmp_path):
        """反向:两种 degraded 的 detail 必须**不同**,否则区分是假的。"""
        missing = tmp_path / "never_created"
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(missing))
        d_missing = _client().get("/api/v4-test/v4/health").json()["detail"]

        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / "booster_home.txt").write_text("x")
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(broken))
        d_broken = _client().get("/api/v4-test/v4/health").json()["detail"]

        assert d_missing != d_broken, "两种失败给出同一句话 ⇒ 区分是装的"

    def test_the_verdict_needs_no_filesystem_at_all(self, monkeypatch):
        """⭐ 更强的形式:把 `Path.stat` 整个打掉,判词照样出得来。

        这条钉的是**依赖**而不是症状:只要 `artifact_is_expected()` 还在走
        指针解析,它就还会被磁盘的失败模式牵连,以后换个 errno 又炸一次。
        """
        def _boom(*a, **k):
            raise AssertionError("身份判定不该碰文件系统")
        monkeypatch.setattr(Path, "stat", _boom)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", routes.EXPECTED_SERVING_ARTIFACT)
        assert routes.artifact_is_expected() is True


def test_health_resolves_the_artifact_exactly_once(monkeypatch):
    """⭐ 一次请求只解析一次,否则报的路径可能不是加载的那个。

    原来是 3 次:`health()` 自己一次、`artifact_is_expected()` 一次、
    `get_artifact()` 一次。三次之间 Layer B 的指针可能被写入 ⇒
    **回包里的 artifact_path ≠ 它真正加载的 artifact** —— 「读出来的路径 ≠
    跑着的路径」出现在专门报告路径的端点里。审查实测:部署写指针并发下
    1500 次请求有 162 次错位。
    """
    calls = []
    real = routes._resolve_artifact
    monkeypatch.setattr(routes, "_resolve_artifact",
                        lambda: (calls.append(1), real())[1])
    _client().get("/api/v4-test/v4/health")
    assert len(calls) == 1, f"/health 解析了 {len(calls)} 次 —— 中间可被指针写入插入"


# ============================================ §18 的判断逻辑(行为断言,主断言)
#
# ⚠️ 这一整段是审查(2026-08-07)的产物。原来这里只有**一条语法断言**
# (「§18 源码里有没有 `FAIL) fail `」),实测它双向失效:
#   * 把 §18 的错误措辞从「跑不起来」改成「无法执行」—— 行为逐字节相同,
#     测试却红,且红的文案指控「闸没判红」,**是假话**。
#   * 段号从 18 变 19 —— `sh.index(...)` 抛 `ValueError`(是 error 不是 failure),
#     且没有任何说明。
#   * `FAIL)  fail`(多一个空格)—— bash 语义不变,测试红。
#   * 反方向:三个被断言的字符串全留着、把分支改成永不可达 —— 测试绿。
# 而当时**没有任何测试真的执行过 §18 的 bash**(唯一会跑整脚本的
# `test_local_pipeline_scripts.py::test_health_check_runs_without_crash`
# 在改动前后都因 15s 超时而红)。
#
# 修法:判断搬进 `nutmeg.v4.cli.artifact_identity`,在这里逐条**跑**;
# bash 只剩映射,那一层的语法断言放在最后并明确标为补充。

class TestDiskVerdict:
    """A. 磁盘配置对不对 —— 不需要 server 在跑。"""

    def test_correct_env_is_ok(self, monkeypatch):
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", routes.EXPECTED_SERVING_ARTIFACT)
        rows = ai.disk_rows()
        assert [r.severity for r in rows] == [ai.OK], rows

    def test_unset_env_is_warn_not_fail_and_not_ok(self, monkeypatch):
        """兜底值是对的盘 ⇒ 不该判红;但「.env 没生效」本身要说出来 ⇒ 也不该 OK。"""
        monkeypatch.delenv("NUTMEG_V4_ARTIFACT_PATH", raising=False)
        rows = ai.disk_rows()
        assert [r.severity for r in rows] == [ai.WARN], rows
        assert "NUTMEG_V4_ARTIFACT_PATH" in rows[0].message

    def test_wrong_dir_is_fail(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_path / "nope"))
        rows = ai.disk_rows()
        assert rows[0].severity == ai.FAIL, rows
        assert routes.EXPECTED_SERVING_ARTIFACT in rows[0].message

    def test_layer_b_redirect_adds_a_note(self, monkeypatch, tmp_path):
        # 两个盘都得有 metadata:2026-08-07 起「目标盘读不到 trained_at_utc」
        # 自己就是一条 WARN(服务会重定向过去然后加载失败)。这条用例问的是
        # **健康的重定向**不该吵,所以场景要造完整 —— 见 TestRedirectTargetIsVisible。
        base = _artifact_meta(tmp_path / "base", "2026-07-15T06:19:12+00:00")
        target = _artifact_meta(tmp_path / "lb", "2026-10-01T00:00:00+00:00")
        (base / LIVE_ARTIFACT_POINTER_FILENAME).write_text(
            json.dumps({"version": "v", "artifact_path": str(target)}))
        monkeypatch.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(base))
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        routes._pointer_cache.clear()
        sevs = [r.severity for r in ai.disk_rows()]
        assert sevs == [ai.OK, ai.NOTE], sevs


class TestDaemonVerdict:
    """B. 跑着的 daemon 服的对不对 —— 三种失败必须分开。"""

    @staticmethod
    def _serve(handler_body):
        """起一个一次性 HTTP stub,返回 URL 和关停函数。"""
        class H(BaseHTTPRequestHandler):
            def do_GET(self):                      # noqa: N802
                handler_body(self)

            def log_message(self, *a):             # 静音
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return f"http://127.0.0.1:{srv.server_port}/health", srv.shutdown

    def _json(self, payload, code=200):
        def body(h):
            raw = json.dumps(payload).encode()
            h.send_response(code)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(raw)))
            h.end_headers()
            h.wfile.write(raw)
        return self._serve(body)

    def test_daemon_not_listening_is_note_not_fail(self):
        """⭐ 连不上 = **真的**查不了。daemon 没起本来就没什么可判,不该判红。"""
        # 端口 1 上不会有东西监听。
        rows = ai.daemon_rows("http://127.0.0.1:1/health", timeout=2.0)
        assert [r.severity for r in rows] == [ai.NOTE], rows
        assert "没验跑着的进程" in rows[0].message

    def test_http_500_is_fail_not_note(self):
        """⭐⭐ 本次审查逮到的 P0。

        daemon **响应了**,只是坏的(比如服务目录在但 artifact 半成品,
        `/health` 直接 500)。原来 `except Exception` 把它和「连不上」吞成同一条
        灰色 NOTE,`note` 不动 EXIT_CODE ⇒ 整脚本 exit 0,而 §1–§17 里
        **没有任何一节探 daemon** ⇒ 一个答不了 /health 的 daemon 全绿。
        并且那句 NOTE 说的是「daemon 未响应」—— 它响应了,判词本身是假的。
        """
        url, stop = self._json({"detail": "boom"}, code=500)
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.FAIL], rows
        assert "500" in rows[0].message

    def test_non_json_body_is_fail(self):
        def body(h):
            raw = b"<html>proxy error</html>"
            h.send_response(200)
            h.send_header("Content-Length", str(len(raw)))
            h.end_headers()
            h.wfile.write(raw)
        url, stop = self._serve(body)
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.FAIL], rows

    def test_old_code_without_the_field_is_fail(self):
        """改动上线但 daemon 没重启 —— 必须红,否则「改了」和「生效了」分不出。"""
        url, stop = self._json({"status": "ok", "artifact_loaded": True})
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.FAIL], rows
        assert "重启" in rows[0].message

    def test_daemon_mismatch_is_fail_and_names_the_base(self):
        url, stop = self._json({
            "status": "ok", "artifact_loaded": True,
            "artifact_is_expected": False,
            "artifact_base_path": "data/v4_model",
            "artifact_path": "data/v4_model"})
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.FAIL], rows
        assert "data/v4_model" in rows[0].message
        assert "kickstart" in rows[0].message, "判红了不告诉人怎么修"

    def test_healthy_daemon_is_ok(self):
        url, stop = self._json({
            "status": "ok", "artifact_loaded": True,
            "artifact_is_expected": True,
            "artifact_path": "data/v4_model_cat",
            "trained_at_utc": "2026-07-15T06:19:12+00:00",
            "model_type": "catboost"})
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.OK], rows

    def test_a_live_redirect_gets_its_own_row(self):
        """daemon 侧也要说清「指到哪」—— 它有自己的 mtime 缓存,磁盘侧的注记
        量的是磁盘,推不出跑着的进程已经跟上了。"""
        url, stop = self._json({
            "status": "ok", "artifact_loaded": True,
            "artifact_is_expected": True,
            "artifact_base_path": "data/v4_model_cat",
            "artifact_path": "data/v4_model_layer_b/v_2026-Q4",
            "artifact_redirected": True,
            "trained_at_utc": "2026-10-01T00:00:00+00:00",
            "model_type": "catboost"})
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.OK, ai.NOTE], rows
        assert "data/v4_model_layer_b/v_2026-Q4" in rows[1].message
        assert "data/v4_model_cat" in rows[1].message

    def test_an_older_backend_without_the_field_does_not_claim_a_redirect(self):
        """`is True` 而不是真值判断:旧后端没这个字段,「没告诉我」不等于
        「重定向了」—— 同 dashboard 那条 `!== false` 的理由,方向相反。"""
        url, stop = self._json({
            "status": "ok", "artifact_loaded": True,
            "artifact_is_expected": True,
            "artifact_path": "data/v4_model_cat",
            "trained_at_utc": "2026-07-15T06:19:12+00:00",
            "model_type": "catboost"})
        try:
            rows = ai.daemon_rows(url, timeout=2.0)
        finally:
            stop()
        assert [r.severity for r in rows] == [ai.OK], rows


class TestModuleEntryPoint:
    def test_exit_code_is_one_when_anything_failed(self, monkeypatch, capsys):
        monkeypatch.setattr(ai, "all_rows", lambda *a, **k: [ai.Row(ai.FAIL, "x")])
        assert ai.main() == 1
        assert capsys.readouterr().out.startswith("FAIL\tx")

    def test_exit_code_is_zero_when_only_warn_and_note(self, monkeypatch, capsys):
        monkeypatch.setattr(ai, "all_rows",
                            lambda *a, **k: [ai.Row(ai.WARN, "w"), ai.Row(ai.NOTE, "n")])
        assert ai.main() == 0

    def test_an_internal_crash_becomes_a_fail_row_not_silence(self, monkeypatch, capsys):
        """⭐ 自身炸了也必须**说话**。

        边算边打印的话,中途抛异常会留下半截输出,而 bash 只看「输出空不空」
        ⇒ 半截被当成完整结果,错误被 `2>/dev/null` 吞掉 —— 「分不出没有和没去看」。
        """
        def boom(*a, **k):
            raise RuntimeError("kaboom")
        monkeypatch.setattr(ai, "all_rows", boom)
        assert ai.main() == 1
        out = capsys.readouterr().out
        assert out.startswith("FAIL\t") and "kaboom" in out


# ------------------------------------------ 换盘清单:所有字面量必须彼此一致

class TestArtifactLiteralsAgree:
    """⭐ 审查逮到的最重一条:`EXPECTED_SERVING_ARTIFACT` **只管读的那条路**。

    真正生成注单的 cron(`com.nutmeg.morning_recommend` / `daily_recommend`)
    跑 `cli/recommend.py` 且**不传 `--model`**,吃的是它自己的 argparse 默认值;
    `load_artifact()` 不读 env、不读 config、不看 Layer B 指针。所以照
    `routes.py` 原来那句「改这一行和 `.env`」操作,结果是**闸全绿、而下注依据的
    注单出自退役模型**。绿灯成了错误的背书。

    这个类把全部字面量钉在同一个值上:漏改一处就红。
    """

    #: 显式豁免:A/B 工具的另一臂,故意不同(见 test_calibration_canon D2)。
    _ALLOWED_OTHERS = {"data/v4_model_cat_lineups"}

    _PY_SITES = [
        "nutmeg/config.py",
        "nutmeg/v4/api/routes.py",
        "nutmeg/v4/cli/recommend.py",
        "nutmeg/v4/cli/recommend_pool.py",
        "nutmeg/v4/cli/rec.py",
        "nutmeg/v4/cli/data_freshness.py",
    ]

    def test_every_python_artifact_literal_equals_the_declaration(self):
        """比的是**值**,不是子串。

        既有的 `test_calibration_canon.py::TestD2RecommendDefaults` 用的是
        `"data/v4_model_cat" in src` —— 那是子串,`data/v4_model_cat_v2` 也能过。
        这里用 AST 把每个 `data/v4_model*` 字面量抠出来逐个比值。
        """
        src_root = REPO_ROOT / "apps/api/src"
        offenders: list[str] = []
        for rel in self._PY_SITES:
            tree = ast.parse((src_root / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                v = node.value
                if not v.startswith("data/v4_model"):
                    continue
                if v == routes.EXPECTED_SERVING_ARTIFACT or v in self._ALLOWED_OTHERS:
                    continue
                offenders.append(f"{rel}:{node.lineno} = {v!r}")
        assert not offenders, (
            "这些字面量和声明的生产盘不一致 —— 换盘漏改了:\n  "
            + "\n  ".join(offenders)
            + f"\n(声明值 = {routes.EXPECTED_SERVING_ARTIFACT!r};"
              " 换盘清单见 routes.py 的 EXPECTED_SERVING_ARTIFACT 注释)")

    @pytest.mark.parametrize("rel", [
        ".env.example",
        "scripts/run_local_server.sh",
        "scripts/setup_local_pipeline.sh",
    ])
    def test_shell_and_env_literals_equal_the_declaration(self, rel):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        # 只看**非注释行**里出现的路径 —— 注释里提旧盘是讲历史,不是配置。
        code = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith("#"))
        bad = [m for m in re.findall(r"data/v4_model[A-Za-z0-9_/-]*", code)
               if m != routes.EXPECTED_SERVING_ARTIFACT and m not in self._ALLOWED_OTHERS]
        assert not bad, f"{rel} 里的 {sorted(set(bad))} 与声明的生产盘不一致"

    def test_layer_b_usage_examples_name_the_serving_base(self):
        """换盘清单第 10 条 —— **补充性**的文本断言,承重的是
        `test_auto_retrain.py::TestDeployTargetIdentity`(真跑 CLI 看退出码)。

        为什么需要它:上面那条 AST 断言**逮不到**这里。用法示例在模块的文档
        字符串里,`ast.Constant` 的值是整段 docstring,`startswith("data/v4_model")`
        直接漏过 —— 把这个文件加进 `_PY_SITES` 只会给出虚假的覆盖。

        2026-08-07 之前这两行写的是 `--artifact-base data/v4_model`:照抄就把
        Layer B 的指针写进一个服务不读的 base,部署静默不可见。
        """
        rel = "apps/api/src/nutmeg/v4/cli/auto_retrain.py"
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        bad = [m for m in re.findall(r"--artifact-base\s+(data/[A-Za-z0-9_/-]+)", text)
               if m != routes.EXPECTED_SERVING_ARTIFACT]
        assert not bad, (
            f"{rel} 的 --artifact-base 用法示例指向 {sorted(set(bad))},"
            f"而服务读的是 {routes.EXPECTED_SERVING_ARTIFACT!r}")

    def test_the_deploy_path_asks_the_same_question_serving_asks(self):
        """⭐ 行为断言:`do_deploy` 判「这是不是服务读的那个 base」时,用的必须是
        `routes` 里那个**同一个**判断,而不是自己抄一份。

        两份拷贝的后果不是「代码重复」,是**读写两侧静默地各判各的** —— 而写侧
        判错的表现形式恰好是「一切正常」。这里把声明值 monkeypatch 走,再看
        `_deploy_target_problems` 的判词有没有跟着变:抄了一份的实现不会跟。
        """
        from nutmeg.v4.cli.auto_retrain import _deploy_target_problems

        real = Path(routes.EXPECTED_SERVING_ARTIFACT).resolve()
        assert not any("不是服务读的那个盘" in p
                       for p in _deploy_target_problems(real, candidate=None))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(REPO_ROOT / "data/nope"))
            assert any("不是服务读的那个盘" in p
                       for p in _deploy_target_problems(real, candidate=None)), (
                "改了声明值,部署侧的判词没变 —— 它没在读 routes 的声明")

    def test_the_bet_generating_cli_actually_loads_the_expected_artifact(
            self, monkeypatch, tmp_path):
        """⭐ 承重条,而且是**行为**断言:真跑 `cli/recommend.main()`,
        把它交给 `load_artifact()` 的那个路径截下来看。

        为什么单独给这一条上行为断言:出注的两个 cron 走的就是它。上面的 AST
        断言看的是源码里的字面量,这一条看的是**运行时真的用了哪个**。
        """
        import nutmeg.v4.cli.recommend as rec_cli

        seen: dict[str, str] = {}

        class _Trapped(Exception):
            pass

        def _trap(path):
            seen["path"] = str(path)
            raise _Trapped

        monkeypatch.setattr(rec_cli, "load_artifact", _trap)
        csv = tmp_path / "fixtures.csv"
        csv.write_text(
            "date,league,home_team,away_team,psc_home,psc_draw,psc_away\n"
            "2026-08-10,ENG_PL,Arsenal,Chelsea,2.10,3.40,3.60\n",
            encoding="utf-8")

        with pytest.raises(_Trapped):
            rec_cli.main(["--fixtures", str(csv)])

        assert seen["path"] == routes.EXPECTED_SERVING_ARTIFACT, (
            f"出注 CLI 默认加载 {seen['path']!r},而服务侧声明的是 "
            f"{routes.EXPECTED_SERVING_ARTIFACT!r} —— 面板和注单会来自不同模型")


# ------------------------------------------------ 面板健康点必须读身份字段(行为)

DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _js_fn(name: str) -> str:
    """抠出生产函数**原文**(花括号配平),不重写一份 —— 重写就测不到真代码。

    与 `test_gate_p_source_behavioral.py` 同一手法。
    """
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\n(async )?function {re.escape(name)}\s*\(", js)
    assert m, f"找不到 {name} —— 被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)


def _render_health_dot(core: dict) -> str:
    """喂一份 /health 回包,拿到健康点真正渲染出的 HTML。"""
    import subprocess

    src = f"""
{_js_fn('_healthDot')}
{_js_fn('loadHealth')}
const API = '/api/v4';
const t = k => k;
let captured = '';
const $ = () => ({{ set innerHTML(v) {{ captured = v; }} }});
const CORE = {json.dumps(core)};
const OBS = {{ status: 'ok', n_settled: 1, n_recommendations: 2 }};
global.fetch = (u) => Promise.resolve(
  {{ json: () => (u.includes('observation') ? OBS : CORE) }});
loadHealth().then(() => console.log(captured));
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2000]
    return r.stdout


_HEALTHY = {"status": "ok", "n_teams": 445, "artifact_is_expected": True,
            "artifact_base_path": "data/v4_model_cat",
            "expected_artifact_path": "data/v4_model_cat"}


def test_dashboard_dot_is_green_when_identity_is_fine():
    html = _render_health_dot(_HEALTHY)
    assert "--accent-green" in html, html[:300]
    assert "health_wrong_artifact" not in html


def test_dashboard_dot_goes_red_when_serving_the_wrong_artifact():
    """⭐ 承重条:唯一**常开**的界面必须能看见身份闸。

    后端**刻意**让 `status` 在服错盘时仍是 'ok'(存活与身份独立失败)。
    所以只看 status 的后果是:服着另一个模型、所有数字都来自它,而这个点还是绿的。
    而唯一会判红的 `health_check.sh` **不在任何 cron 上**(24 个 plist 里 0 个)
    ⇒ 闸到人的延迟 = 「你什么时候想起来跑」。

    红而不是黄:黄是「有点降级还能用」,这个是「所有数字都来自另一个模型」——
    比后端起不来更危险,因为它看起来完全正常。
    """
    html = _render_health_dot({**_HEALTHY, "artifact_is_expected": False,
                               "artifact_base_path": "data/v4_model"})
    assert "--accent-rose" in html, f"服错盘却没变红:{html[:300]}"
    assert "health_wrong_artifact" in html
    assert "data/v4_model" in html, "没说清在服哪个盘,运维不知道要改什么"


def test_dashboard_dot_does_not_false_red_on_an_older_backend():
    """反向:后端还没升级(回包里没这个字段)时不该误报红。

    `!== false` 而不是 `=== true` —— 「没告诉我」不等于「不对」。
    """
    old = {k: v for k, v in _HEALTHY.items() if k != "artifact_is_expected"}
    html = _render_health_dot(old)
    assert "--accent-rose" not in html, "旧后端被误判成服错盘 —— 假红"


# ------------------------------------------------- health_check.sh 的严重性映射

def _identity_section() -> str:
    """定位 §18。

    ⚠️ 按**语义锚点**(调用了身份闸模块)定位,不按段号 —— 原来写的是
    `sh.index("# ===== 18. ")`,插一节新的把它变成 §19 就抛 `ValueError`,
    是 error 不是 failure,而且不告诉人为什么。
    """
    sh = (REPO_ROOT / "scripts" / "health_check.sh").read_text(encoding="utf-8")
    idx = sh.find("nutmeg.v4.cli.artifact_identity")
    assert idx != -1, (
        "health_check.sh 不再调用 nutmeg.v4.cli.artifact_identity —— "
        "身份闸被从体检里摘掉了?(判断逻辑本身另有行为测试,这条只管接线)")
    start = sh.rfind("\n# ===== ", 0, idx)
    end = sh.find("\n# ===== ", idx)
    return sh[start if start != -1 else 0: end if end != -1 else len(sh)]


def test_health_check_maps_the_fail_verdict_to_fail():
    """补充断言(**不是**主断言):bash 侧把 FAIL 判词接到 `fail` 而不是 `warn`/`note`。

    判断逻辑由上面 TestDiskVerdict / TestDaemonVerdict / TestModuleEntryPoint
    逐条跑过;bash 这一层只剩「判词 → 严重性」的映射,而映射一旦退化成 `warn`,
    整个闸就只是打印文字(`warn` 不动 EXIT_CODE)。

    ⚠️ 只断言**结构**,不断言任何提示文案 —— 措辞是给人看的,改措辞不该变红。
    正则容忍空白,`fail` 后要求词边界。
    """
    section = _identity_section()
    assert re.search(r"FAIL\)\s+fail\b", section), "§18 的 FAIL 判词没接到 fail(),闸失效"
    assert re.search(r"WARN\)\s+warn\b", section), "§18 的 WARN 判词没接到 warn()"


def test_health_check_treats_its_own_failure_as_red():
    """「查不了」必须红 —— 静默通过是这一族 bug 的本体。

    只看结构:`if [[ -z "$ART_OUT" ]]; then` 到 `else` **之间**必须调 `fail`。

    ⚠️ 这条的第一版写成 `-z "\\$ART_OUT"[\\s\\S]{0,600}?\\bfail\\s+"` —— 非贪婪
    匹配会越过分支边界,一路找到后面 case 语句里的 `FAIL) fail "$msg"`。
    变异检验实测:把这个分支从 `fail` 改成 `note`(= 跑不起来时静默通过,
    正是本条要防的那件事)**测试照样全绿**。假绿。
    ⇒ 断言必须**框住分支体**,不能只说「附近有 fail 这个词」。
    """
    section = _identity_section()
    m = re.search(r'-z\s+"\$ART_OUT"\s*\]\]\s*;\s*then([\s\S]*?)^else\b',
                  section, re.M)
    assert m, "§18 的「输出为空」分支结构变了 —— 重新确认它还判不判红"
    assert re.search(r'^\s*fail\s+"', m.group(1), re.M), (
        "§18 在自己跑不起来(模块 import 失败 / 无输出)时没有判红,"
        "又是一个「检查的前提没人检查」")
