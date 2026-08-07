"""V11 backlog #4 — tests for Layer B auto-retrain module + CLI + serving.

Mirrors the Layer A test layout (test_auto_calibration*.py):

  - Pure helpers (log-loss, bootstrap, ship gate, version label)
  - Journal schema + persistence
  - Artifact-pointer write/read/remove
  - CLI: propose / deploy / rollback flows
  - Serving: _artifact_path() honors pointer + mtime cache
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ============ Pure helpers ============================================

class TestLogLoss:
    def test_perfect_prediction_zero(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        out = np.array([0, 1, 2])
        assert log_loss_1x2(probs, out) < 1e-6

    def test_uniform_is_log3(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.full((3, 3), 1.0 / 3.0)
        out = np.array([0, 1, 2])
        assert abs(log_loss_1x2(probs, out) - float(np.log(3.0))) < 1e-6

    def test_empty(self):
        from nutmeg.v4.observation.auto_retrain import log_loss_1x2
        probs = np.zeros((0, 3))
        out = np.array([], dtype=int)
        assert np.isnan(log_loss_1x2(probs, out))


class TestBootstrap:
    def test_b_strictly_better_low_p(self):
        """When B is uniformly better on every match, p ≈ 0."""
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        rng = np.random.default_rng(0)
        n = 100
        out = rng.integers(0, 3, size=n)
        # A predicts uniform, B always predicts the correct outcome at p=0.8
        a = np.full((n, 3), 1.0 / 3.0)
        b = np.full((n, 3), 0.1)
        b[np.arange(n), out] = 0.8
        p = bootstrap_p_value(a, b, out, n_iter=200)
        assert p < 0.05

    def test_a_strictly_better_high_p(self):
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        rng = np.random.default_rng(0)
        n = 100
        out = rng.integers(0, 3, size=n)
        # A is the better predictor here
        b = np.full((n, 3), 1.0 / 3.0)
        a = np.full((n, 3), 0.1)
        a[np.arange(n), out] = 0.8
        p = bootstrap_p_value(a, b, out, n_iter=200)
        assert p > 0.5

    def test_empty(self):
        from nutmeg.v4.observation.auto_retrain import bootstrap_p_value
        out = np.array([], dtype=int)
        empty = np.zeros((0, 3))
        # No samples → no claim — return 1.0
        assert bootstrap_p_value(empty, empty, out, n_iter=10) == 1.0


class TestShipGate:
    def test_all_thresholds_pass(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000,
            log_loss_after=0.995,
            p_value=0.02,
            n_train=10000,
            n_holdout=200,
        )
        assert ok is True
        assert "ship" in reason

    def test_too_few_train_matches(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.02, n_train=100, n_holdout=200,
        )
        assert ok is False
        assert "n_train" in reason

    def test_too_few_holdout_matches(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.02, n_train=10000, n_holdout=50,
        )
        assert ok is False
        assert "n_holdout" in reason

    def test_log_loss_delta_too_small(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.9995,  # only 0.5 milli
            p_value=0.02, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "delta" in reason

    def test_p_value_too_high(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=1.000, log_loss_after=0.995,
            p_value=0.20, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "p_value" in reason

    def test_nan_log_loss_fails(self):
        from nutmeg.v4.observation.auto_retrain import evaluate_ship_gate
        ok, reason = evaluate_ship_gate(
            log_loss_before=float("nan"), log_loss_after=0.995,
            p_value=0.02, n_train=10000, n_holdout=200,
        )
        assert ok is False
        assert "NaN" in reason


class TestVersioning:
    def test_q1_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 1, 15)) == "v_2026-Q1"
        assert current_quarter_version(dt.date(2026, 3, 31)) == "v_2026-Q1"

    def test_q2_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 4, 1)) == "v_2026-Q2"
        assert current_quarter_version(dt.date(2026, 6, 30)) == "v_2026-Q2"

    def test_q3_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 7, 1)) == "v_2026-Q3"

    def test_q4_label(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        assert current_quarter_version(dt.date(2026, 12, 31)) == "v_2026-Q4"

    def test_today_returns_string(self):
        from nutmeg.v4.observation.auto_retrain import current_quarter_version
        v = current_quarter_version()
        assert v.startswith("v_")
        assert "-Q" in v


# ============ Journal persistence =====================================

@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "obs.db")


class TestJournal:
    def test_ensure_creates_table(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import ensure_retrain_journal
        ensure_retrain_journal(temp_db)
        # Idempotent — second call works too
        ensure_retrain_journal(temp_db)

    def test_record_propose(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            fetch_latest_journal_entry,
            record_retrain_journal,
        )
        jid = record_retrain_journal(
            temp_db,
            action="propose",
            artifact_version="v_2026-Q3",
            artifact_path="/tmp/v_2026-Q3",
            log_loss_before=1.000, log_loss_after=0.995,
            log_loss_delta=0.005, p_value=0.02,
            n_train=12000, n_holdout=200,
            train_window=("2023-08-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
            decision=True,
            reason="all gates passed",
        )
        assert jid >= 1
        row = fetch_latest_journal_entry(temp_db)
        assert row is not None
        assert row["action"] == "propose"
        assert row["artifact_version"] == "v_2026-Q3"
        assert row["decision"] == 1
        assert "2023-08-01 → 2026-04-30" in row["train_window"]

    def test_action_validation(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import record_retrain_journal
        with pytest.raises(ValueError):
            record_retrain_journal(
                temp_db, action="invalid",
                artifact_version="x", artifact_path="x",
            )

    def test_fetch_filters_by_action(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            fetch_latest_journal_entry,
            record_retrain_journal,
        )
        record_retrain_journal(temp_db, action="propose",
                               artifact_version="v1", artifact_path="/x")
        record_retrain_journal(temp_db, action="deploy",
                               artifact_version="v2", artifact_path="/x")
        record_retrain_journal(temp_db, action="propose",
                               artifact_version="v3", artifact_path="/x")
        latest_propose = fetch_latest_journal_entry(temp_db, action="propose")
        assert latest_propose["artifact_version"] == "v3"
        latest_deploy = fetch_latest_journal_entry(temp_db, action="deploy")
        assert latest_deploy["artifact_version"] == "v2"

    def test_fetch_on_missing_db(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        missing = tmp_path / "does-not-exist.db"
        assert fetch_latest_journal_entry(missing) is None

    def test_nan_handled(self, temp_db):
        from nutmeg.v4.observation.auto_retrain import (
            fetch_latest_journal_entry,
            record_retrain_journal,
        )
        record_retrain_journal(
            temp_db, action="propose",
            artifact_version="x", artifact_path="x",
            log_loss_before=float("nan"),  # should land as NULL not NaN
        )
        row = fetch_latest_journal_entry(temp_db)
        assert row["log_loss_before"] is None


# ============ Artifact pointer ========================================

class TestArtifactPointer:
    def test_write_creates_atomic(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
            write_artifact_pointer,
        )
        out = write_artifact_pointer(
            tmp_path,
            version="v_2026-Q3",
            artifact_path=str(tmp_path / "v_2026-Q3"),
            previous_version="production_v5_w12",
            ship_gate_log_loss_delta=0.0024,
            ship_gate_p_value=0.018,
            n_train=12000, n_holdout=200,
            train_window=("2023-08-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
        )
        assert out.name == LIVE_ARTIFACT_POINTER_FILENAME
        assert out.exists()
        payload = json.loads(out.read_text())
        assert payload["version"] == "v_2026-Q3"
        assert payload["ship_gate_log_loss_delta"] == 0.0024
        assert payload["ship_gate_p_value"] == 0.018
        # Atomic-write artifact — no .tmp left behind
        assert not (tmp_path / "live_artifact_pointer.tmp").exists()

    def test_load_returns_none_when_missing(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import load_artifact_pointer
        assert load_artifact_pointer(tmp_path) is None

    def test_load_round_trip(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            load_artifact_pointer,
            write_artifact_pointer,
        )
        write_artifact_pointer(
            tmp_path, version="v_2026-Q3",
            artifact_path=str(tmp_path / "target"),
            previous_version=None,
            ship_gate_log_loss_delta=0.003, ship_gate_p_value=0.04,
            n_train=10000, n_holdout=150,
            train_window=("2023-01-01", "2026-04-30"),
            holdout_window=("2026-05-01", "2026-06-30"),
        )
        ptr = load_artifact_pointer(tmp_path)
        assert ptr is not None
        assert ptr["version"] == "v_2026-Q3"
        assert ptr["previous_version"] == "production_v5_w12"

    def test_remove(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            remove_artifact_pointer,
            write_artifact_pointer,
        )
        write_artifact_pointer(
            tmp_path, version="v_x", artifact_path="x",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert remove_artifact_pointer(tmp_path) is True
        assert remove_artifact_pointer(tmp_path) is False  # already gone

    def test_remove_layer_a_correction(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            LAYER_A_CORRECTION_FILENAME,
            remove_layer_a_correction,
        )
        # No file → False
        assert remove_layer_a_correction(tmp_path) is False
        # Create + remove
        (tmp_path / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')
        assert remove_layer_a_correction(tmp_path) is True
        assert not (tmp_path / LAYER_A_CORRECTION_FILENAME).exists()


# ============ Resolver ================================================

class TestResolveArtifactPath:
    def test_no_pointer_returns_base(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import resolve_effective_artifact_path
        assert resolve_effective_artifact_path(tmp_path) == str(tmp_path)

    def test_with_pointer_returns_target(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            resolve_effective_artifact_path,
            write_artifact_pointer,
        )
        target = tmp_path / "target"
        target.mkdir()
        write_artifact_pointer(
            tmp_path, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert resolve_effective_artifact_path(tmp_path) == str(target)

    def test_pointer_to_missing_dir_falls_back(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import (
            resolve_effective_artifact_path,
            write_artifact_pointer,
        )
        # Point to a non-existent target
        write_artifact_pointer(
            tmp_path, version="v_x",
            artifact_path="/does/not/exist",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert resolve_effective_artifact_path(tmp_path) == str(tmp_path)


# ============ CLI integration =========================================

#: 生产两个盘的真实训练时间,用来把「候选比 base 更老」写成一个具体的场景
#: 而不是两个随手编的时间戳。data/v4_model = 2026-05-22(退役 LightGBM),
#: data/v4_model_cat = 2026-07-15(在服的 CatBoost)。
STALE_TRAINED_AT = "2026-05-22T06:17:04+00:00"
LIVE_TRAINED_AT = "2026-07-15T06:19:12+00:00"


def _artifact_dir(path: Path, trained_at: str | None) -> Path:
    """够真实的 artifact 目录:部署路径实际会去读的那一部分。

    只写 `metadata.json` —— 走 `save_artifact()` 要拉 lightgbm 训 40 行数据,
    只为产出一个 `trained_at_utc`。形状对齐 `persist.save_artifact()`:训练
    metadata 嵌在 "metadata" 键下(实测生产两个盘都是这个形状,顶层没有)。

    `trained_at=None` → 造一个**空目录**:`is_dir()` 为真但没有 metadata,
    正是「目录在不在」这个代理放行、而服务加载会失败的那个形状。
    """
    path.mkdir(parents=True, exist_ok=True)
    if trained_at is not None:
        (path / "metadata.json").write_text(json.dumps({
            "metadata": {"trained_at_utc": trained_at,
                         "training_cutoff": trained_at[:10]},
            "feature_columns": ["f0"],
        }))
    return path


@pytest.fixture
def serving_base(tmp_path, monkeypatch):
    """一个 tmp 目录,在本用例里**就是**声明的生产服务盘。

    monkeypatch 声明值(而不是给测试开 `--override-identity`)是刻意的:
    这样用例走的是生产那条路,而不是逃生口 —— 否则护栏加上了,而所有测试都
    绕着它跑。
    """
    from nutmeg.v4.api import routes
    base = _artifact_dir(tmp_path / "base", LIVE_TRAINED_AT)
    monkeypatch.setattr(routes, "EXPECTED_SERVING_ARTIFACT", str(base))
    return base


class TestCliPropose:
    def test_dry_run_returns_2_when_gate_fails(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        db = tmp_path / "obs.db"
        rc = main([
            "--db", str(db),
            "--action", "propose",
            "--log-loss-before", "1.000",
            "--log-loss-after", "0.999",  # only 0.001 — below threshold
            "--p-value", "0.02",
            "--n-train", "10000",
            "--n-holdout", "200",
        ])
        assert rc == 2  # ship gate not passed

    def test_dry_run_returns_0_when_gate_passes(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        db = tmp_path / "obs.db"
        rc = main([
            "--db", str(db),
            "--action", "propose",
            "--log-loss-before", "1.000",
            "--log-loss-after", "0.995",  # 5 milli-pt improvement
            "--p-value", "0.02",
            "--n-train", "10000",
            "--n-holdout", "200",
        ])
        assert rc == 0

    def test_apply_writes_journal_row(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        db = tmp_path / "obs.db"
        main([
            "--db", str(db), "--action", "propose", "--apply",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        row = fetch_latest_journal_entry(str(db))
        assert row is not None
        assert row["action"] == "propose"
        assert row["decision"] == 1

    def test_writes_report_when_out_given(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        out = tmp_path / "retrain.md"
        main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "propose",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
            "--out", str(out),
        ])
        assert out.exists()
        md = out.read_text()
        assert "Layer B Quarterly Retrain" in md
        assert "🟢 **SHIP**" in md


class TestCliDeploy:
    def test_requires_candidate(self, tmp_path):
        from nutmeg.v4.cli.auto_retrain import main
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--artifact-base", str(tmp_path / "base"),
        ])
        assert rc == 1

    def test_deploy_writes_pointer_and_clears_layer_a(self, tmp_path, serving_base):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LAYER_A_CORRECTION_FILENAME,
            LIVE_ARTIFACT_POINTER_FILENAME,
        )
        base = serving_base
        candidate = _artifact_dir(tmp_path / "v_2026-Q3", "2026-10-01T00:00:00+00:00")
        # Pre-existing Layer A correction
        (base / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')

        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--candidate", str(candidate),
            "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "0.995",
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 0
        # Pointer was written
        assert (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        # Layer A correction was cleared
        assert not (base / LAYER_A_CORRECTION_FILENAME).exists()

    def test_deploy_rejected_when_gate_fails(self, tmp_path, serving_base):
        """AUDIT FIX (R4): deploy re-checks the ship gate. A candidate that does
        NOT pass (here log-loss WORSE than production) is refused with rc 2 and
        no pointer is written — propose-passing is no longer assumed at deploy."""
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
        )
        base = serving_base
        candidate = _artifact_dir(tmp_path / "v_2026-Q3", "2026-10-01T00:00:00+00:00")
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply",
            "--candidate", str(candidate), "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "1.050",  # WORSE
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 2
        assert not (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()

    def test_deploy_override_gate_forces_through(self, tmp_path, serving_base):
        """--override-gate lets an emergency manual deploy proceed despite a
        failing gate — the pointer is written (rc 0)."""
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
        )
        base = serving_base
        candidate = _artifact_dir(tmp_path / "v_2026-Q3", "2026-10-01T00:00:00+00:00")
        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "deploy", "--apply", "--override-gate",
            "--candidate", str(candidate), "--artifact-base", str(base),
            "--version", "v_2026-Q3",
            "--log-loss-before", "1.000", "--log-loss-after", "1.050",  # WORSE
            "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200",
        ])
        assert rc == 0
        assert (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()


class TestDeployTargetIdentity:
    """⭐ 指针的**目标**必须被约束 —— `artifact_is_expected()` 判 base 是刻意的,
    所以「指到哪」是它唯一豁免的那条路,而 2026-08-07 的审查就是从那条路进来的。

    这一整类都是**行为**断言:真跑 `cli/auto_retrain.main()`,看它的退出码和
    磁盘上落了什么。⛔ 没有一条查「源码里有没有某个字符串」。
    """

    _GATE_ARGS = ["--log-loss-before", "1.000", "--log-loss-after", "0.995",
                  "--p-value", "0.02", "--n-train", "10000", "--n-holdout", "200"]

    def _deploy(self, tmp_path, base, candidate, *extra):
        from nutmeg.v4.cli.auto_retrain import main
        return main(["--db", str(tmp_path / "obs.db"),
                     "--action", "deploy", "--apply",
                     "--candidate", str(candidate), "--artifact-base", str(base),
                     "--version", "v_2026-Q3", *self._GATE_ARGS, *extra])

    def test_deploy_to_a_base_serving_does_not_read_is_refused(
            self, tmp_path, serving_base, caplog):
        """⭐ 承重条 —— Layer A 的 D1 事故在 Layer B 上重演的那一版。

        `do_deploy` 原来是 `base.mkdir(parents=True, exist_ok=True)`,**不和任何
        东西比较**。部署到一个服务侧根本不读的 base ⇒ 服务继续跑原模型,而
        `redirected=False`、`artifact_is_expected=True`、§18 只有一行 OK ——
        完全不可见。ship gate 在这里是过的:这不是「候选不够好」,是「这次部署
        谁也看不见」,两件事。
        """
        wrong = tmp_path / "not_the_serving_dir"
        candidate = _artifact_dir(tmp_path / "v_2026-Q3", "2026-10-01T00:00:00+00:00")

        rc = self._deploy(tmp_path, wrong, candidate)

        assert rc == 1, "部署到一个没人读的 base 却成功返回了"
        assert not wrong.exists(), (
            "把错误的 base **建出来**了 —— 这正是 mkdir(parents=True) 那个洞:"
            "运行成功、目录也在,而服务永远不会去看它")
        assert str(serving_base) in caplog.text, "拒了却不说正确的 base 是哪个"

    def test_deploy_pointing_at_an_older_artifact_is_refused(
            self, tmp_path, serving_base):
        """⭐ 审查实测的那条路:base 是对的,**目标**是 2026-05 的退役盘。

        身份闸对此全绿(`artifact_is_expected: true` / `status: ok` /
        `detail: null` / §18 exit 0),因为它判的是 base。所以这一条必须由
        部署侧拦 —— 拦的依据是两个盘自己的 `trained_at_utc`,不是路径黑名单。
        """
        from nutmeg.v4.observation.auto_retrain import LIVE_ARTIFACT_POINTER_FILENAME
        stale = _artifact_dir(tmp_path / "retired_model", STALE_TRAINED_AT)

        rc = self._deploy(tmp_path, serving_base, stale)

        assert rc == 1
        assert not (serving_base / LIVE_ARTIFACT_POINTER_FILENAME).exists(), (
            "拒绝了却还是把指针写下去了")

    def test_a_candidate_dir_with_no_metadata_is_refused(
            self, tmp_path, serving_base):
        """`--candidate` 原来只查 `is_dir()` —— 而空目录也是目录。

        训练中途被打断 / rsync 没传完 ⇒ 目录在、metadata.json 不在。服务会照样
        重定向过去然后加载失败,`/health` 掉 degraded。「目录存在」是这个仓库
        反复栽的那两个代理之一。
        """
        from nutmeg.v4.observation.auto_retrain import LIVE_ARTIFACT_POINTER_FILENAME
        empty = _artifact_dir(tmp_path / "half_trained", None)
        assert empty.is_dir(), "前提:它确实是个目录,只是空的"

        rc = self._deploy(tmp_path, serving_base, empty)

        assert rc == 1
        assert not (serving_base / LIVE_ARTIFACT_POINTER_FILENAME).exists()

    def test_a_newer_candidate_at_the_serving_base_deploys(
            self, tmp_path, serving_base):
        """反向:正常那条路必须还能走通,而且指针内容真的指向候选盘。

        没有这一条,上面三条全绿也可能只是因为部署整个坏了 —— 「拦住了」和
        「谁也过不去」在退出码上长得一样。
        """
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
            load_artifact_pointer,
        )
        candidate = _artifact_dir(tmp_path / "v_2026-Q4", "2026-10-01T00:00:00+00:00")

        assert self._deploy(tmp_path, serving_base, candidate) == 0
        assert (serving_base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        assert load_artifact_pointer(serving_base)["artifact_path"] == \
            str(candidate.resolve())

    def test_override_identity_lets_it_through_and_says_so_in_the_journal(
            self, tmp_path, serving_base):
        """逃生口存在,但**留痕**:事后翻 journal 时,「指到一个更旧的盘」
        和一次正常部署不能长得一模一样。

        顺带钉住:这个逃生口**不是** `--override-gate`。那一个的理由(数字缺失 /
        紧急)和这里的理由(路径写错)毫不相干,合成一个开关就等于让常规的
        gate override 顺手把这条检查也关掉。
        """
        from nutmeg.v4.observation.auto_retrain import (
            LIVE_ARTIFACT_POINTER_FILENAME,
            fetch_latest_journal_entry,
        )
        stale = _artifact_dir(tmp_path / "retired_model", STALE_TRAINED_AT)

        # --override-gate 单独给不够 —— 它管的是另一件事
        assert self._deploy(tmp_path, serving_base, stale, "--override-gate") == 1

        rc = self._deploy(tmp_path, serving_base, stale, "--override-identity")
        assert rc == 0
        assert (serving_base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        row = fetch_latest_journal_entry(str(tmp_path / "obs.db"), action="deploy")
        assert "IDENTITY OVERRIDDEN" in row["reason"], (
            f"绕过了身份检查却没记进 journal:{row['reason']!r}")

    def test_rollback_against_the_wrong_base_is_refused(self, tmp_path, serving_base):
        """rollback 只删文件 ⇒ base 写错 = 一次**静默的空操作**,还打印一张
        成功的回滚卡片。而运维跑它的时候,通常已经有东西在烧了。"""
        from nutmeg.v4.cli.auto_retrain import main
        wrong = tmp_path / "not_the_serving_dir"
        rc = main(["--db", str(tmp_path / "obs.db"),
                   "--action", "rollback", "--apply",
                   "--artifact-base", str(wrong)])
        assert rc == 1
        assert not wrong.exists()

    def test_write_artifact_pointer_refuses_to_invent_a_base(self, tmp_path):
        """纵深防御:CLI 之外的调用方也不该能凭空建出一个 base。

        `write_artifact_pointer` 里还有第二次无保护的 `mkdir(parents=True)`。
        指针是写进**生产 artifact 目录**的(模型文件就住在那儿),所以一个不存在
        的 base 不可能是服务在读的那个 —— 建出来的唯一效果是一个没人读的指针。
        """
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        ghost = tmp_path / "never_existed"
        with pytest.raises(NotADirectoryError):
            write_artifact_pointer(
                ghost, version="v_x", artifact_path=str(tmp_path),
                previous_version=None, ship_gate_log_loss_delta=0.0,
                ship_gate_p_value=0.0, n_train=0, n_holdout=0,
                train_window=("", ""), holdout_window=("", ""))
        assert not ghost.exists(), "抛异常了,但目录还是被建出来了"


class TestTrainedAtReader:
    """`artifact_trained_at` 必须分得清「读到了」「读不到」——「读不到」既不是
    新也不是旧,而这个仓库反复栽在「查不了被当成没问题」上。"""

    def test_reads_the_nested_shape_that_save_artifact_writes(self, tmp_path):
        """⚠️ 生产两个盘实测都是**嵌套**形状(顶层 `trained_at_utc` = None)。
        `cli/data_freshness.py` 读的是顶层键,所以它对每个盘都静默走了 mtime
        兜底 —— 单独的一个 bug,这里不复制它。"""
        from nutmeg.v4.observation.auto_retrain import artifact_trained_at
        d = _artifact_dir(tmp_path / "a", LIVE_TRAINED_AT)
        assert artifact_trained_at(d) == LIVE_TRAINED_AT

    def test_flat_shape_also_works(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import artifact_trained_at
        d = tmp_path / "flat"
        d.mkdir()
        (d / "metadata.json").write_text(json.dumps({"trained_at_utc": LIVE_TRAINED_AT}))
        assert artifact_trained_at(d) == LIVE_TRAINED_AT

    @pytest.mark.parametrize("make", [
        lambda d: None,                                        # 目录不存在
        lambda d: d.mkdir(),                                   # 空目录
        lambda d: (d.mkdir(), (d / "metadata.json").write_text("{{{")),   # 坏 JSON
        lambda d: (d.mkdir(), (d / "metadata.json").write_text("[]")),    # 不是 dict
        lambda d: (d.mkdir(), (d / "metadata.json").write_text("{}")),    # 没这个键
    ])
    def test_unreadable_is_none_not_a_guess(self, tmp_path, make):
        from nutmeg.v4.observation.auto_retrain import artifact_trained_at
        d = tmp_path / "x"
        make(d)
        assert artifact_trained_at(d) is None

    def test_parse_does_not_rely_on_lexicographic_order(self):
        """同一时刻、不同 offset 写法 ⇒ 字符串比较会给出**错的**顺序。

        `2026-07-15T06:00:00+00:00` vs `2026-07-15T14:00:00+08:00` 是同一时刻,
        但字符串上前者更小。护栏拿它判「谁更旧」的话,换个时区写法就翻车。
        """
        from nutmeg.v4.observation.auto_retrain import parse_trained_at
        utc = "2026-07-15T06:00:00+00:00"
        same_moment_other_offset = "2026-07-15T14:00:00+08:00"
        assert utc < same_moment_other_offset          # 字符串序:假的
        assert parse_trained_at(utc) == parse_trained_at(same_moment_other_offset)

    def test_naive_timestamp_is_read_as_utc_not_dropped(self):
        from nutmeg.v4.observation.auto_retrain import parse_trained_at
        assert parse_trained_at("2026-07-15T06:00:00") == \
            parse_trained_at("2026-07-15T06:00:00+00:00")

    @pytest.mark.parametrize("empty", ["", None])
    def test_empty_nested_value_does_not_veto_a_usable_flat_one(self, tmp_path, empty):
        """⭐ 嵌套值是**空的**时候要退回顶层,不能只在键不存在时才退。

        写成 `value if value is not None else raw.get(...)` 的话,一个 `""` 会赢过
        顶层的真日期 ⇒ 返回 None ⇒ 每个调用方都读成「读不出来」并降级。对
        `cli/data_freshness.py` 那个降级是退到文件 mtime:一个陈旧盘被报成 0d、
        零告警,而**不修这个函数的旧代码在同一个盘上是会告警的**。
        空串不是日期,不能压过一个真日期。
        """
        from nutmeg.v4.observation.auto_retrain import artifact_trained_at
        d = tmp_path / "both_shapes"
        d.mkdir()
        (d / "metadata.json").write_text(json.dumps({
            "metadata": {"trained_at_utc": empty},
            "trained_at_utc": LIVE_TRAINED_AT,
        }))
        assert artifact_trained_at(d) == LIVE_TRAINED_AT


class TestSameArtifactDir:
    """`same_artifact_dir` 是「这两个路径是不是同一个目录」的**唯一**实现。

    `api/routes._same_dir` 是它的别名(serving 的 /health 走那条),
    `cli/data_freshness` 判 `redirected` 走这条。两份实现 = 读的一侧和查的一侧
    有漂的余地,而漂开的表现是**静默**的:同一份报告会同时说「生效盘超龄」和
    「base 陈旧不告警」,说的其实是同一个目录。
    """

    @pytest.mark.parametrize("other", [
        lambda p: str(p),                        # 自己
        lambda p: str(p) + "/",                  # 尾斜杠
        lambda p: str(p / "."),                  # 单点
        lambda p: str(p / "sub" / ".."),         # 绕一圈
    ])
    def test_spellings_of_the_same_dir_agree(self, tmp_path, other):
        from nutmeg.v4.observation.auto_retrain import same_artifact_dir
        d = tmp_path / "art"
        (d / "sub").mkdir(parents=True)
        assert same_artifact_dir(d, other(d))

    def test_different_dirs_disagree(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import same_artifact_dir
        assert not same_artifact_dir(tmp_path / "a", tmp_path / "b")

    def test_neither_side_has_to_exist(self, tmp_path):
        from nutmeg.v4.observation.auto_retrain import same_artifact_dir
        assert same_artifact_dir(tmp_path / "ghost", tmp_path / "ghost")

    def test_routes_alias_is_the_same_function(self, tmp_path):
        """别名不许自己长出第二套语义 —— 行为断言,不是「源码里有没有 import」。"""
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import same_artifact_dir
        d = tmp_path / "art"
        d.mkdir()
        for a, b in [(str(d), str(d) + "/"), (str(d), str(tmp_path / "other"))]:
            assert routes._same_dir(a, b) is same_artifact_dir(a, b)


class TestCliRollback:
    def test_rollback_clears_both_files(self, tmp_path, serving_base):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import (
            LAYER_A_CORRECTION_FILENAME,
            LIVE_ARTIFACT_POINTER_FILENAME,
            write_artifact_pointer,
        )
        base = serving_base
        # Pre-populate pointer + Layer A correction
        write_artifact_pointer(
            base, version="v_2026-Q3", artifact_path=str(tmp_path / "target"),
            previous_version="production_v5_w12",
            ship_gate_log_loss_delta=0.003, ship_gate_p_value=0.04,
            n_train=10000, n_holdout=200,
            train_window=("", ""), holdout_window=("", ""),
        )
        (base / LAYER_A_CORRECTION_FILENAME).write_text('{"T": 1.05}')

        rc = main([
            "--db", str(tmp_path / "obs.db"),
            "--action", "rollback", "--apply",
            "--artifact-base", str(base),
            "--reason", "ROI regressed > 5pp post-deploy",
        ])
        assert rc == 0
        assert not (base / LIVE_ARTIFACT_POINTER_FILENAME).exists()
        assert not (base / LAYER_A_CORRECTION_FILENAME).exists()

    def test_rollback_journal_row(self, tmp_path, serving_base):
        from nutmeg.v4.cli.auto_retrain import main
        from nutmeg.v4.observation.auto_retrain import fetch_latest_journal_entry
        base = serving_base
        db = tmp_path / "obs.db"
        main([
            "--db", str(db),
            "--action", "rollback", "--apply",
            "--artifact-base", str(base),
            "--reason", "test rollback",
        ])
        row = fetch_latest_journal_entry(str(db), action="rollback")
        assert row is not None
        assert "test rollback" in row["reason"]


# ============ Serving (routes._artifact_path) =========================

class TestServingResolution:
    def test_no_pointer_returns_default(self, monkeypatch, tmp_path):
        """Without a pointer file, _artifact_path falls back to env / default."""
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(tmp_path))
        # Clear cache between tests
        from nutmeg.v4.api import routes
        routes._pointer_cache.clear()
        result = routes._artifact_path()
        assert result == str(tmp_path)

    def test_pointer_redirects_to_target(self, monkeypatch, tmp_path):
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        target = tmp_path / "target"
        base.mkdir()
        target.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert routes._artifact_path() == str(target)

    def test_pointer_to_missing_dir_falls_back(self, monkeypatch, tmp_path):
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        base.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path="/does/not/exist",
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        assert routes._artifact_path() == str(base)

    def test_mtime_cache_returns_same_path(self, monkeypatch, tmp_path):
        """Two calls with no file change → same result (cache hit)."""
        from nutmeg.v4.api import routes
        from nutmeg.v4.observation.auto_retrain import write_artifact_pointer
        routes._pointer_cache.clear()
        base = tmp_path / "base"
        target = tmp_path / "target"
        base.mkdir()
        target.mkdir()
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(base))
        write_artifact_pointer(
            base, version="v_x", artifact_path=str(target),
            previous_version=None, ship_gate_log_loss_delta=0.0,
            ship_gate_p_value=0.0, n_train=0, n_holdout=0,
            train_window=("", ""), holdout_window=("", ""),
        )
        a = routes._artifact_path()
        b = routes._artifact_path()
        assert a == b == str(target)


# ============ CLI registration ========================================

class TestCliRegistered:
    def test_pyproject_lists_nutmeg_auto_retrain(self):
        proj = (REPO_ROOT / "pyproject.toml").read_text()
        assert "nutmeg-auto-retrain" in proj
        assert "nutmeg.v4.cli.auto_retrain:main" in proj

    def test_help_works(self):
        from nutmeg.v4.cli.auto_retrain import main
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
