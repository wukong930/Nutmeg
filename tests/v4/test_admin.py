"""个人中心 (admin) endpoints — read-only status + triple-gated restart controls.

Pins the security contract: keys never leak in full; restart needs localhost +
NUTMEG_ADMIN_ENABLED + the X-Nutmeg-Admin header, all three.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from nutmeg.main import app
from nutmeg.v4.api import admin

_LOCAL = {"client": ("127.0.0.1", 50000)}
_REMOTE = {"client": ("8.8.8.8", 40000)}


def test_status_readonly_localhost():
    r = TestClient(app, **_LOCAL).get("/api/v4/admin/status")
    assert r.status_code == 200
    j = r.json()
    assert set(j) >= {"admin_enabled", "daemon", "cron", "data", "api_keys"}
    assert {"running_commit", "head_commit", "stale", "started_at"} <= set(j["daemon"])


def test_status_never_leaks_full_key():
    j = TestClient(app, **_LOCAL).get("/api/v4/admin/status").json()
    for src in j["api_keys"].values():
        # only presence + last-4 + length may ever appear — never the full key
        assert set(src) <= {"present", "last4", "length"}
        if src.get("last4"):
            assert len(src["last4"]) == 4


def test_status_rejects_non_localhost():
    assert TestClient(app, **_REMOTE).get("/api/v4/admin/status").status_code == 403


def test_restart_disabled_by_default(monkeypatch):
    monkeypatch.setattr(admin.settings, "admin_enabled", False)
    c = TestClient(app, **_LOCAL)
    assert c.post("/api/v4/admin/restart-api").status_code == 403  # no header
    assert c.post("/api/v4/admin/restart-api",
                  headers={"X-Nutmeg-Admin": "1"}).status_code == 403  # env flag off


def test_restart_requires_all_three_gates(monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "_spawn_detached", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(admin.settings, "admin_enabled", True)
    # localhost + enabled + header → 200, spawn invoked (mocked, NO real restart)
    r = TestClient(app, **_LOCAL).post("/api/v4/admin/restart-api",
                                       headers={"X-Nutmeg-Admin": "1"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert len(calls) == 1 and "kickstart" in calls[0]
    # missing header → still 403 even when enabled
    assert TestClient(app, **_LOCAL).post("/api/v4/admin/restart-api").status_code == 403
    # non-localhost → still 403 even with header + enabled
    assert TestClient(app, **_REMOTE).post(
        "/api/v4/admin/restart-api", headers={"X-Nutmeg-Admin": "1"}).status_code == 403


def test_restart_automation_spawns_setup(monkeypatch):
    calls = []
    monkeypatch.setattr(admin, "_spawn_detached", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(admin.settings, "admin_enabled", True)
    r = TestClient(app, **_LOCAL).post("/api/v4/admin/restart-automation",
                                       headers={"X-Nutmeg-Admin": "1"})
    assert r.status_code == 200
    assert len(calls) == 1 and "setup_local_pipeline.sh" in calls[0]


def test_cron_running_job_not_flagged_after_kill(monkeypatch):
    # Regression: api_server right after `kickstart -k` reports the SIGKILL as
    # its last exit code but is RUNNING (has a PID) — it must NOT be flagged as
    # a bad exit. A genuinely-failed one-shot (no PID, non-zero exit) MUST be.
    fake = (
        "PID\tStatus\tLabel\n"
        "4847\t-9\tcom.nutmeg.api_server\n"     # running, last exit -9 (just killed)
        "-\t1\tcom.nutmeg.daily_predict\n"      # not running, exited 1 → real failure
        "-\t0\tcom.nutmeg.daily_backup\n"       # not running, clean exit
    )

    class _R:
        stdout = fake
        returncode = 0

    monkeypatch.setattr(admin.subprocess, "run", lambda *a, **k: _R())
    c = admin._cron_status()
    assert "api_server" not in c["bad_exits"]    # running ⇒ not bad despite -9
    assert "daily_predict" in c["bad_exits"]      # failed one-shot ⇒ flagged
    assert "daily_backup" not in c["bad_exits"]


def test_expected_tracks_persisted_plists_not_hardcoded(monkeypatch, tmp_path):
    """`expected` 必须**跟着磁盘 plist 走**,不是硬编码计数。

    回归:旧版 `_EXPECTED_JOBS = 21`(07-01 定)在 07-19 加 sporttery_open、
    07-20 加 sporttery_evening 后就漂了 → 面板永久显示「23/21 有任务缺失」的
    假警告,而 missing_labels 明明是空的。「加 cron 记得同步改常量」是注定
    会忘的人肉契约(已漂两次),故让它自动推导。
    """
    plist_dir = tmp_path / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True)
    for label in ("alpha", "beta", "gamma"):        # 3 个落盘 plist
        (plist_dir / f"com.nutmeg.{label}.plist").touch()
    fake = ("PID\tStatus\tLabel\n"
            "-\t0\tcom.nutmeg.alpha\n"
            "-\t0\tcom.nutmeg.beta\n"
            "-\t0\tcom.nutmeg.gamma\n")

    class _R:
        stdout = fake
        returncode = 0

    monkeypatch.setattr(admin.subprocess, "run", lambda *a, **k: _R())
    monkeypatch.setattr(admin.Path, "home", staticmethod(lambda: tmp_path))

    c = admin._cron_status()
    assert c["expected"] == c["persisted_plists"], "expected 必须 = 落盘 plist 数"
    assert c["expected"] == 3                      # 不是任何硬编码的 21
    assert c["missing_labels"] == []
    assert c["healthy"] is True                    # 3 装 3 ⇒ 绿
