"""个人中心 (personal center / admin) — read-only status + hard-gated controls.

Security posture (deliberate — these are privileged, secret-adjacent ops):
- API keys are NEVER returned in full: only presence + last-4 + masked length.
  Editing keys stays a local-file/CLI op; this layer only DISPLAYS status.
- The WRITE controls (restart API daemon / reinstall launchd jobs) are
  TRIPLE-gated: (1) localhost-only (request.client.host), (2) the
  NUTMEG_ADMIN_ENABLED env flag (default OFF), (3) a custom ``X-Nutmeg-Admin``
  header — a browser cannot set a custom header cross-origin without a CORS
  preflight that same-origin passes and cross-origin fails, so a drive-by
  malicious page on another site cannot trigger a restart even on localhost.
- "running code vs HEAD" is captured at IMPORT (= daemon start) so the panel can
  surface the "提交≠上线" staleness that left WPO un-served for 2 days
  (the long-running uvicorn daemon does not hot-reload — see
  [[live-cron-vs-setup-source-drift]]).

The read-only GET /status does NO outbound API calls (so loading the tab never
burns API quota); the live plan/quota probe is the separate, cached GET
/api-probe, fired on demand by a button.
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from nutmeg.config import get_settings

settings = get_settings()  # singleton; env (incl. NUTMEG_ADMIN_ENABLED) read at process start

admin_router = APIRouter(prefix="/v4/admin", tags=["admin"])

_EXPECTED_JOBS = 21  # 18 base + sporttery_vote + polymarket_gaps + closing_odds (07-01)
_LOCALHOSTS = {"127.0.0.1", "::1", "localhost"}
_PROBE_TTL_SECONDS = 600  # cache live API probes 10 min → repeated tab loads don't burn quota


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parents[6]


_REPO = _find_repo_root()


def _git(*args: str, default: str | None = None) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=_REPO, capture_output=True,
                           text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else default
    except Exception:  # noqa: BLE001 — git absent / not a repo → just report unknown
        return default


# Captured ONCE at import = the commit this daemon process is actually running.
_RUNNING_COMMIT = _git("rev-parse", "--short", "HEAD", default="unknown")
_STARTED_AT = time.time()

_probe_cache: dict = {"at": 0.0, "data": None}


def _key_masked(key: str | None) -> dict:
    """Presence + last-4 ONLY — never the full key."""
    if not key:
        return {"present": False}
    return {"present": True, "last4": key[-4:], "length": len(key)}


def _cron_status() -> dict:
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
        jobs = []
        for line in r.stdout.splitlines():
            if "com.nutmeg." not in line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            pid, exit_code, label = parts[0], parts[1], parts[2]
            jobs.append({
                "label": label.replace("com.nutmeg.", ""),
                "running": pid not in ("-", ""),
                "last_exit": exit_code,
            })
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        persisted = len(list(plist_dir.glob("com.nutmeg.*.plist"))) if plist_dir.exists() else 0
        # A job with a live PID is healthy regardless of a stale previous exit
        # code — e.g. api_server right after `kickstart -k` reports the SIGKILL
        # as its last_exit but is running fine. Only flag NOT-running jobs whose
        # last run exited non-zero (a one-shot cron that genuinely failed).
        bad = [j["label"] for j in jobs
               if not j["running"] and j["last_exit"] not in ("0", "-")]
        return {
            "loaded": len(jobs),
            "expected": _EXPECTED_JOBS,
            "persisted_plists": persisted,
            "healthy": len(jobs) >= _EXPECTED_JOBS and not bad,
            "bad_exits": bad,
            "jobs": sorted(jobs, key=lambda j: j["label"]),
        }
    except Exception as e:  # noqa: BLE001
        return {"loaded": 0, "expected": _EXPECTED_JOBS, "error": str(e)}


def _data_freshness() -> list[dict]:
    db = os.environ.get("NUTMEG_V4_OBSERVATION_DB", settings.v4_observation_db)
    rows = []
    try:
        with sqlite3.connect(db) as c:
            for table, col, label in [
                ("odds_snapshots", "captured_at", "Pinnacle 线史 (CLV 地基)"),
                ("jingcai_sp", "captured_at", "竞彩 SP 捕获 (软水)"),
                ("jingcai_vote", "captured_at", "竞彩 散户支持比例 (软水)"),
                ("league_predictions", "recorded_at", "模型盘预测日志"),
                ("wc_predictions", "recorded_at", "WC 模型预测"),
                ("polymarket_gaps", "recorded_at", "Polymarket 错价缺口 (只读测量)"),
            ]:
                try:
                    n, last = c.execute(f"SELECT COUNT(*), MAX({col}) FROM {table}").fetchone()
                    rows.append({"table": table, "label": label, "rows": n, "last": last})
                except Exception:  # noqa: BLE001 — table/col may not exist on a fresh DB
                    rows.append({"table": table, "label": label, "rows": None, "last": None})
    except Exception as e:  # noqa: BLE001
        return [{"error": str(e)}]
    return rows


def _probe_apis() -> dict:
    """Live plan/quota probe for both data sources. Cached 10 min. Read-only."""
    now = time.time()
    if _probe_cache["data"] is not None and now - _probe_cache["at"] < _PROBE_TTL_SECONDS:
        return {**_probe_cache["data"], "cached": True}

    import httpx

    result: dict = {"api_football": {}, "odds_api": {}}

    af_key = settings.api_football_key
    if af_key:
        try:
            r = httpx.get(f"{settings.api_football_base_url}/status",
                          headers={"x-apisports-key": af_key}, timeout=10)
            resp = (r.json() or {}).get("response", {})
            sub, req = resp.get("subscription", {}), resp.get("requests", {})
            result["api_football"] = {
                "ok": r.status_code == 200, "plan": sub.get("plan"),
                "active": sub.get("active"), "expires": sub.get("end"),
                "requests_today": req.get("current"), "limit_day": req.get("limit_day"),
            }
        except Exception as e:  # noqa: BLE001
            result["api_football"] = {"ok": False, "error": str(e)}
    else:
        result["api_football"] = {"ok": False, "error": "no key in .env"}

    oa_key = settings.odds_api_key
    if oa_key:
        try:
            r = httpx.get(f"{settings.odds_api_base_url}/sports",
                          params={"apiKey": oa_key}, timeout=15)
            ok = r.status_code == 200
            result["odds_api"] = {
                "ok": ok, "sports": len(r.json()) if ok else None,
                "remaining": r.headers.get("x-requests-remaining"),
                "used": r.headers.get("x-requests-used"),
            }
        except Exception as e:  # noqa: BLE001
            result["odds_api"] = {"ok": False, "error": str(e)}
    else:
        result["odds_api"] = {"ok": False, "error": "no key in .env"}

    _probe_cache["at"], _probe_cache["data"] = now, result
    return {**result, "cached": False}


def _require_localhost(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCALHOSTS:
        raise HTTPException(403, "admin endpoints are localhost-only")


def _require_admin_write(request: Request, x_nutmeg_admin: str | None) -> None:
    _require_localhost(request)
    if not settings.admin_enabled:
        raise HTTPException(
            403, "admin controls disabled — set NUTMEG_ADMIN_ENABLED=1 in .env then restart")
    if x_nutmeg_admin != "1":
        raise HTTPException(403, "missing X-Nutmeg-Admin header (anti-CSRF)")


def _spawn_detached(shell_cmd: str) -> None:
    """Run a command in a NEW session, detached — so restarting our own daemon
    doesn't kill the in-flight HTTP response (the sleep lets the 200 flush first)."""
    subprocess.Popen(["bash", "-c", shell_cmd], cwd=_REPO,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


@admin_router.get("/status")
def admin_status(request: Request) -> dict:
    """Read-only. No outbound API calls. Powers the 个人中心 tab."""
    _require_localhost(request)
    head = _git("rev-parse", "--short", "HEAD", default="unknown")
    stale = (_RUNNING_COMMIT not in ("unknown", head) and head != "unknown")
    return {
        "admin_enabled": settings.admin_enabled,
        "daemon": {
            "running_commit": _RUNNING_COMMIT,
            "head_commit": head,
            "stale": stale,  # True ⇒ committed code newer than what's serving → restart to apply
            "started_at": _dt.datetime.fromtimestamp(_STARTED_AT, _dt.UTC).isoformat(),
            "uptime_seconds": int(time.time() - _STARTED_AT),
        },
        "cron": _cron_status(),
        "data": _data_freshness(),
        "api_keys": {
            "api_football": _key_masked(settings.api_football_key),
            "odds_api": _key_masked(settings.odds_api_key),
        },
    }


@admin_router.get("/api-probe")
def admin_api_probe(request: Request) -> dict:
    """Live plan/quota for both data sources (cached 10 min). Read-only; localhost-only."""
    _require_localhost(request)
    return _probe_apis()


@admin_router.post("/restart-api")
def admin_restart_api(request: Request,
                      x_nutmeg_admin: str | None = Header(default=None)) -> dict:
    _require_admin_write(request, x_nutmeg_admin)
    uid = os.getuid()
    _spawn_detached(f"sleep 1 && launchctl kickstart -k gui/{uid}/com.nutmeg.api_server")
    return {"ok": True, "action": "restart-api",
            "note": "daemon restarting in ~1s — poll /admin/status until started_at changes"}


@admin_router.post("/restart-automation")
def admin_restart_automation(request: Request,
                             x_nutmeg_admin: str | None = Header(default=None)) -> dict:
    _require_admin_write(request, x_nutmeg_admin)
    _spawn_detached("sleep 1 && bash scripts/setup_local_pipeline.sh "
                    "> logs/launchd/setup_from_admin.log 2>&1")
    return {"ok": True, "action": "restart-automation",
            "note": "reinstalling all 18 launchd jobs (incl. API daemon) — ~10s; "
                    "log at logs/launchd/setup_from_admin.log"}
