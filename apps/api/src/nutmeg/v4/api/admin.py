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


# ⚠️ 选表的判据是「**这个 cron 停了,面板会不会红**」,不是「这张表大不大」。
# 2026-07-29 审计:23 个 cron、面板只覆盖 7 张表 —— 下面 6 行是补上的
# **静默失速盲区**,每一行对应一个此前无人代表的 cron。
#
# ⛔ 有意**不**加的:
#   · jingcai_exotic_sp(6,981 行,量最大)—— 与 jingcai_sp **同一个 cron**、
#     captured_at 逐秒相同,停了会一起停 ⇒ 零额外告警价值,不占一行。
#     ⚠️ **但它留下一个未修的口径问题**:面板「竞彩 SP 捕获 551 条」而同一批
#     实际还落了 6,981 条异型盘(比分/总进球/半全场)= **捕获量低报 13×**。
#     修法(把两数并进同一行)是显示改动,owner 定,尚未做。
#   · pinnacle_close_history / crown_close_history —— 由 scripts/backfill_*.py
#     写、**没有 cron**。静态档案,进「新鲜度」= 永久假红。
#   · settlements / single_predictions / parlay_recommendations —— 实盘台账,
#     陈旧是**因为空仓**不是故障。混进本节会被读成告警。
#   · data/external/* 的 parquet(clubelo_national / cup_* 停在 05-25)——
#     要加必须先带「预期更新频率」,否则休赛期全变红、人就学会忽略本节
#     (`clubelo-selfdestruct-and-authoritative-endpoint`:休赛期不动≠陈旧)。
_FRESHNESS_ROWS: tuple[tuple[str, str, str], ...] = (
    ("odds_snapshots", "captured_at", "Pinnacle 线史 (CLV 地基)"),
    ("jingcai_sp", "captured_at", "竞彩 SP 捕获 (软水)"),
    ("jingcai_vote", "captured_at", "竞彩 散户支持比例 (软水)"),
    ("league_predictions", "recorded_at", "模型盘预测日志"),
    ("wc_predictions", "recorded_at", "WC 模型预测"),
    ("polymarket_gaps", "recorded_at", "Polymarket 错价缺口 (只读测量)"),
    # ── P0:停了下游全部静默中毒 ──────────────────────────────
    # match_outcomes 是**唯一的赛果入口**(daily_settle)。它停了,上面所有
    # 捕获行照常绿,但 CLV 账本 / EV 排序 / δ 校准 / 抽水分解全部冻在旧结果
    # 上 —— 而且**不报错,只是 N 不涨**。与 score_ev_flags 同一种失效形状。
    ("match_outcomes", "recorded_at", "赛果结算 (下游所有测量的地基)"),
    # ⚠️ 同表第二行、**不同列**:daily_wc_settle 此前完全没有代表 ——
    # recorded_at 只在「有新预测」时动,WC 停办后它必然陈旧,于是结算 cron
    # 是死是活看不出来。实测 settled_at=今天 而 recorded_at=07-19。
    ("wc_predictions", "settled_at", "WC 结算 (daily_wc_settle)"),
    # ── P1:独立 cron,主表遮不住 ─────────────────────────────
    # 晚间跟盘窗(17:00-23:00,sporttery_evening)与晨批是**两个 cron**。
    # 实测 jingcai_sp=15:15 而 jingcai_sp_snapshots=14:02 —— 晚间窗停了,
    # 上面「竞彩 SP 捕获」照样今天。而那个窗存在的理由是
    # 「临停售调价才是 EV 杀手」(`jingcai-batch-opening-morning-release`)。
    ("jingcai_sp_snapshots", "captured_at", "竞彩 SP 晚间跟盘 (freeze-gap)"),
    ("jingcai_vote_snapshots", "captured_at", "竞彩 支持率晚间跟盘"),
    # 周任务、量小(9 行),但它是 **artifact 校正路径的唯一心跳**。
    ("calibration_journal", "recorded_at", "周度校准日志 (artifact 校正)"),
    ("recommendation_sessions", "created_at", "推荐会话 (每日/晨间)"),
    # 2026-08-12 — 盘面反事实快照(snapshot_board cron,5 窗/天)。
    # ⭐ 与上面 jingcai_sp_snapshots 完全同构的理由:独立 cron、point-in-time、
    # forward-only,**主表遮不住** —— 它死了,jingcai_sp / odds_snapshots
    # 照常今天,而没买的那两条腿的盘面就永久没了。
    # 用 provenance 当心跳(空盘面的日子 leg 表本来就该是 0 行,拿它会假红)。
    ("snapshot_provenance", "created_at", "盘面快照心跳 (反事实层)"),
)

#: 「同 cron 的姊妹表」—— 只并进主行的计数说明,**不单独占一行**。
#: key 是 (主表, 主列) 而不是光主表:wc_predictions 出现两次,只按表名会撞。
#:
#: ⚠️ 为什么是 note 不是新行:jingcai_exotic_sp 与 jingcai_sp 由**同一个 cron**
#: 写、captured_at 逐秒相同 ⇒ 停了会一起停,单独一行零告警价值、只是噪声。
#: 但不显示它,面板就把这个 cron 的捕获量**低报 13 倍**(551 vs 551+6,981)。
#: 所以:计数并进来,行数不增。
_FRESHNESS_COMPANIONS: dict[tuple[str, str], tuple[str, str, str]] = {
    # 主表/主列          → (姊妹表,             姊妹列,        后缀词)
    ("jingcai_sp", "captured_at"): ("jingcai_exotic_sp", "captured_at", "异型"),
}

#: 「长得像连接键、实际可能恒 NULL」的列 —— 100% 空时**必须喊出来**。
#:
#: ⚠️ 病史(2026-07-30):按 `jingcai_sp.fixture_id` 连 `polymarket_gaps`,得到
#: 「0 场重叠」,差点写成「Polymarket 和竞彩完全不重合」的结论。真相是该列
#: **0/576 非空**,而且**填不了、不是忘了填**:
#:   · 主力写入方 sporttery(502 行 = 87%)源头就没有 API-Football id;
#:   · 服务路径整条没有这个字段(FixtureOddsInput / SinglePrediction 都按
#:     (date, league, home_team, away_team) 走)。
#: ⇒ 恒 NULL 的连接键会把任何经过它的 join **静默清零**,长得和「真的没数据」
#: 一模一样 —— 与「404 伪装成空结果」「别名层漏掉丢 59%」同一族失败。
#: 这里**不造数据**(硬填一个猜来的 id 比 NULL 坏得多,见「绝不瞎猜队名」红线),
#: 只让「空」在面板上可见,并把正典键写在旁边。
_JOIN_KEY_COLUMNS: dict[str, tuple[str, str]] = {
    # 表          → (可疑连接列,   该表真正的正典键 = 它自己的 UNIQUE)
    "jingcai_sp": ("fixture_id", "match_date+home_team+away_team+market"),
}


def _data_freshness() -> list[dict]:
    db = os.environ.get("NUTMEG_V4_OBSERVATION_DB", settings.v4_observation_db)
    rows = []
    try:
        # 体检 Wave1 — READ-ONLY open. A plain connect() on a mistyped/moved path
        # silently CREATES an empty DB file, turning "DB missing" (loud) into
        # "DB fine but 0 rows" (masked misconfig). mode=ro raises instead —
        # same posture as the score_ev_forward probe below.
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            for table, col, label in _FRESHNESS_ROWS:
                try:
                    # ⚠️ `COUNT(col)` 不是 `COUNT(*)` —— 数的是**该列非空**的行。
                    # 对 wc_predictions/settled_at 这种「同表不同列」的行是承重的:
                    # COUNT(*) 会把**未结算**的比赛也算进「WC 结算」,虚报进度。
                    # 现有各表的时间列都在 insert 时写入 ⇒ 换了之后**当下零变化**
                    # (实测 12 行全部 COUNT(*)==COUNT(col)),只在将来有空值时才分岔。
                    n, last = c.execute(
                        f"SELECT COUNT({col}), MAX({col}) FROM {table}").fetchone()
                    row = {"table": table, "label": label, "rows": n, "last": last}
                    comp = _FRESHNESS_COMPANIONS.get((table, col))
                    if comp:
                        ct, ccol, word = comp
                        try:
                            cn = c.execute(f"SELECT COUNT({ccol}) FROM {ct}").fetchone()[0]
                            # 姊妹表为 0 行时**不加 note** —— 「+ 0 异型」比不写更糟,
                            # 它把「这个市场今天没上架」渲染成一个看着像故障的零。
                            if cn:
                                row["note"] = f"+ {cn:,} {word}"
                        except Exception:  # noqa: BLE001 — 姊妹表可能还不存在
                            pass
                    jk = _JOIN_KEY_COLUMNS.get(table)
                    if jk:
                        kcol, canon = jk
                        try:
                            total, filled = c.execute(
                                f"SELECT COUNT(*), COUNT({kcol}) FROM {table}").fetchone()
                            # 只在**表非空且该列全空**时喊 —— 空表的 0/0 不是发现,
                            # 和「+ 0 异型」同一条戒律:别把非故障渲染成故障。
                            if total and not filled:
                                warn = (f"⚠️ {kcol} 恒 NULL({total:,} 行 0 非空)"
                                        f" — 别拿它连表,正典键 = {canon}")
                                row["note"] = (f"{row['note']} · {warn}"
                                               if row.get("note") else warn)
                        except Exception:  # noqa: BLE001 — 列/表可能不存在
                            pass
                    rows.append(row)
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
