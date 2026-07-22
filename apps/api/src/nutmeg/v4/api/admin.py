"""个人中心 (personal center / admin) — read-only status + hard-gated controls.

Security posture (deliberate — these are privileged, secret-adjacent ops):
- API keys are NEVER returned in full: only presence + last-4 + masked length.
  2026-07-20 — key ROTATION added (POST /rotate-key), but the read direction is
  unchanged and non-negotiable: **write-only**. No endpoint ever returns a key,
  and the new value is never logged (only its last-4 lands in the log line), so
  the panel can never become an exfiltration surface. See ``_write_env_key``.
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
import logging
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Body, Header, HTTPException, Request

from nutmeg.config import get_settings

settings = get_settings()  # singleton; env (incl. NUTMEG_ADMIN_ENABLED) read at process start

admin_router = APIRouter(prefix="/v4/admin", tags=["admin"])

# NB 期望值**自动推导** = 落盘的 plist 数(setup_local_pipeline.sh 恰好写这些),
# 不再硬编码。旧版 `_EXPECTED_JOBS = 21`(07-01 定)在 07-19 加 sporttery_open、
# 07-20 加 sporttery_evening 后就漂了 → 面板永久显示「23/21 有任务缺失」的**假警告**,
# 而 missing_labels 明明是空的。加 cron 要记得同步改常量 = 注定会忘的人肉契约
# (这已是第二次漂),所以直接让它跟着磁盘走。
# ⚠️ 这不是循环论证:真正的健康判据是下面的 `missing = persisted_labels -
# loaded_labels`(W3-4 的 label 集比对),`expected` 只是给人看的分母。
log = logging.getLogger(__name__)
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
        persisted_labels = (
            {p.stem.replace("com.nutmeg.", "") for p in plist_dir.glob("com.nutmeg.*.plist")}
            if plist_dir.exists() else set()
        )
        # A job with a live PID is healthy regardless of a stale previous exit
        # code — e.g. api_server right after `kickstart -k` reports the SIGKILL
        # as its last_exit but is running fine. Only flag NOT-running jobs whose
        # last run exited non-zero (a one-shot cron that genuinely failed).
        bad = [j["label"] for j in jobs
               if not j["running"] and j["last_exit"] not in ("0", "-")]
        # 体检 Wave3 (P2) — healthy by LABEL SET, not by count: "loaded ≥ 21"
        # stays green when job A silently unloads while a stray job B is
        # loaded. The persisted plists ARE the installed set (setup writes
        # exactly those), so every persisted label must be loaded.
        loaded_labels = {j["label"] for j in jobs}
        missing = sorted(persisted_labels - loaded_labels)
        return {
            "loaded": len(jobs),
            "expected": len(persisted_labels),   # 自动推导,见文件头注释
            "persisted_plists": len(persisted_labels),
            "missing_labels": missing,
            "healthy": bool(persisted_labels) and not missing and not bad,
            "bad_exits": bad,
            "jobs": sorted(jobs, key=lambda j: j["label"]),
        }
    except Exception as e:  # noqa: BLE001
        # 读不到 launchctl/plist 时 expected 也未知 —— 报 0 而不是编个数字,
        # 免得「0/21」看着像「21 个全丢了」(实际是探测本身失败,见 error 字段)。
        return {"loaded": 0, "expected": 0, "error": str(e)}


def _data_freshness() -> list[dict]:
    db = os.environ.get("NUTMEG_V4_OBSERVATION_DB", settings.v4_observation_db)
    rows = []
    try:
        # 体检 Wave1 — READ-ONLY open. A plain connect() on a mistyped/moved path
        # silently CREATES an empty DB file, turning "DB missing" (loud) into
        # "DB fine but 0 rows" (masked misconfig). mode=ro raises instead —
        # same posture as the score_ev_forward probe below.
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
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
    # 体检 E1 — score_ev_forward.db is a SEPARATE forward-only DB (3 crons write
    # score_ev_flags). It was absent from this panel, so a silent stall of those
    # crons would show all-green while forward-only data bled. Read-only URI so a
    # missing file never creates a spurious DB.
    sef = Path(str(db)).with_name("score_ev_forward.db")
    label = "外盘 EV 前向记录 (score_ev_forward.db)"
    try:
        with sqlite3.connect(f"file:{sef}?mode=ro", uri=True) as c2:
            n, last = c2.execute(
                "SELECT COUNT(*), MAX(captured_at) FROM score_ev_flags").fetchone()
            rows.append({"table": "score_ev_flags", "label": label, "rows": n, "last": last})
    except Exception:  # noqa: BLE001 — missing DB/table on a fresh setup
        rows.append({"table": "score_ev_flags", "label": label, "rows": None, "last": None})
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


# 2026-07-20 — 密钥轮换比重启更重,要求**本机浏览器**,把手机排除掉。
# 背景:`tailscale serve` 是反向代理 —— 手机来的请求最终以 127.0.0.1 抵达,
# 所以 `_require_localhost` 那道闸对手机是**放行**的(重启按钮本来就想让手机能用)。
# 判据三合一(任一不满足即拒):① client.host 是回环 ② Host 头是 localhost
# (手机走 ts.net 域名)③ 没有任何代理转发头。三条都是「代理必然留下痕迹」的
# 正面特征,而不是猜某个代理的实现细节。
_PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-proto", "x-forwarded-host",
                  "x-real-ip", "forwarded", "tailscale-user-login",
                  "tailscale-user-name", "tailscale-user-profile-pic")


def _require_same_machine(request: Request) -> None:
    """本机浏览器专用闸(严于 _require_localhost)——密钥轮换用。"""
    _require_localhost(request)
    seen = [h for h in _PROXY_HEADERS if h in request.headers]
    if seen:
        raise HTTPException(
            403, f"密钥轮换仅限本机浏览器:检测到代理转发头 {seen} —— "
                 "手机/远程(tailscale serve)请在这台电脑上操作")
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host not in _LOCALHOSTS:
        raise HTTPException(
            403, f"密钥轮换仅限本机浏览器:Host={host!r} 不是 localhost —— "
                 "请用 http://127.0.0.1:8080 打开面板")


def _require_admin_write(request: Request, x_nutmeg_admin: str | None) -> None:
    _require_localhost(request)
    if not settings.admin_enabled:
        raise HTTPException(
            403, "admin controls disabled — set NUTMEG_ADMIN_ENABLED=1 in .env then restart")
    if x_nutmeg_admin != "1":
        raise HTTPException(403, "missing X-Nutmeg-Admin header (anti-CSRF)")


# ── 密钥轮换(2026-07-20)────────────────────────────────────────────────
# owner 需求:个人中心手动替换 API-Football / Odds API 密钥。设计三条铁律:
#   ① **write-only** —— 没有任何端点回传 key(读方向仍只有 `_key_masked`);
#   ② **永不入日志** —— 只记 which + last4,值本身不进 log/异常/响应;
#   ③ 写 .env 前先备份 + 原子替换 + chmod 600,且**只动目标那一行**(其余行
#      逐字保留,含注释/空行/顺序)—— .env 是唯一真相,毁了它比丢 key 更糟。
# 生效需重启:`get_settings` 是 @lru_cache,且各模块在 import 时就绑了 settings
# 对象 —— 清缓存救不了已绑定的引用,所以老实返回 restart_required=True。
_ROTATABLE = {
    "api_football": "NUTMEG_API_FOOTBALL_KEY",
    "odds_api": "NUTMEG_ODDS_API_KEY",
}
_KEY_MIN_LEN, _KEY_MAX_LEN = 8, 200


def _validate_key(raw: str) -> str:
    """形状校验(不校验有效性 —— 那是 /api-probe 的事)。异常信息**不含 key**。"""
    key = (raw or "").strip()
    if not key:
        raise HTTPException(400, "key 为空")
    if len(key) < _KEY_MIN_LEN or len(key) > _KEY_MAX_LEN:
        raise HTTPException(400, f"key 长度须在 {_KEY_MIN_LEN}-{_KEY_MAX_LEN} 之间")
    if any(c in key for c in "\n\r\0"):
        raise HTTPException(400, "key 含换行/空字节 —— 会破坏 .env 结构")
    if not all(32 <= ord(c) < 127 for c in key):
        raise HTTPException(400, "key 含非 ASCII 可见字符 —— 多半是粘贴带了格式")
    return key


def _write_env_key(env_var: str, key: str) -> None:
    """把 ``env_var=key`` 写进 .env:备份 → 逐行重建(只换目标行)→ 原子 rename。

    ⚠️ key 只在本函数内存活,不返回、不记日志、不进异常文本。"""
    env = _REPO / ".env"
    if not env.exists():
        raise HTTPException(500, f".env 不存在({env})—— 拒绝凭空创建")
    original = env.read_text(encoding="utf-8")
    backup = env.with_name(f".env.bak-{_dt.datetime.now().strftime('%Y%m%dT%H%M%S')}")
    backup.write_text(original, encoding="utf-8")
    backup.chmod(0o600)

    lines = original.splitlines()
    new_line = f"{env_var}={key}"
    replaced = False
    out = []
    for line in lines:
        if line.lstrip().startswith(f"{env_var}=") and not line.lstrip().startswith("#"):
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:            # 首次设置:追加到末尾
        out.append(new_line)
    body = "\n".join(out) + "\n"

    tmp = env.with_name(f".env.{os.getpid()}.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(env)            # 原子;权限随 tmp 带过去


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


@admin_router.post("/rotate-key")
def admin_rotate_key(request: Request,
                     which: str = Body(..., embed=True),
                     key: str = Body(..., embed=True),
                     x_nutmeg_admin: str | None = Header(default=None)) -> dict:
    """替换 API-Football / Odds API 密钥(写 .env)。

    与两个 restart 端点同一道三重闸(localhost + NUTMEG_ADMIN_ENABLED + 自定义头)。
    **write-only**:响应只回掩码,日志只记 which+last4 —— 本端点永不成为泄露面。
    生效需重启 daemon(settings 是 lru_cache + import 期绑定)。"""
    _require_admin_write(request, x_nutmeg_admin)
    _require_same_machine(request)      # 手机/远程排除 —— 见函数注释
    env_var = _ROTATABLE.get(which)
    if not env_var:
        raise HTTPException(400, f"which 须是 {sorted(_ROTATABLE)} 之一")
    validated = _validate_key(key)
    _write_env_key(env_var, validated)
    log.warning("admin: 轮换 %s 密钥(…%s)— 需重启 daemon 生效",
                which, validated[-4:])
    return {"ok": True, "action": "rotate-key", "which": which,
            "masked": _key_masked(validated), "restart_required": True,
            "note": "已写入 .env(旧值已备份为 .env.bak-<时间戳>);"
                    "点「♻️ 重启 API 服务」后生效"}
