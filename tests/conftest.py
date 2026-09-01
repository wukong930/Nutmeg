"""测试期的两道**出口闸**(2026-09-01 合并自两棵并行 worktree)。

两个病是同一天各自查出来的,症状不同、机理却是同一族:
**一条路在测试进程里悄悄通到了生产资源,而 fail-soft 让它全程零红。**
⇒ 闸都放在**唯一出口**上(不是逐文件的名单),并且都**记一笔**而不是只抛异常
——`except Exception:` 风格的调用点会把异常吞掉,只抛的话闸等于不存在。

⚠️ 合并说明:两份 conftest 原本各自新建,`tests/conftest.py` 只能有一份。
职责完全不重叠(一个管 `NUTMEG_ODDS_API_KEY`,一个管
`NUTMEG_V4_OBSERVATION_DB` + `sqlite3.connect`),所以直接并存;
顺序上**先设环境变量、后清 settings 缓存**,否则清完再设等于没清。

════════════════════════════════════════════════════════════════════
第一部分 —— 生产观测库出口闸
════════════════════════════════════════════════════════════════════

🚨 测试进程**不许**写仓库根下的生产观测库 `data/v4_observation.db`。

## 病史(2026-09-01)

症状是「同一套测试,第一次跑绿,第二次跑红」。
病因是**一个相对路径**,在三层之间传递:

1. `/Users/ninoo/Nutmeg/.env` 里写着
   `NUTMEG_V4_OBSERVATION_DB=data/v4_observation.db` —— **相对路径**。
2. `nutmeg/config.py:20` 的 `load_dotenv()` 把它塞进 `os.environ`。
   ⚠️ worktree 里**没有自己的 `.env`**,`find_dotenv()` 一路往上走,
   捡的是**主 checkout 的那份**。
3. `routes.py::_observation_db_path()` / `observation_routes.py::_db_path()`
   原样返回,消费方按**测试进程的 CWD** 解析。

于是同一个值在两个世界里指向两个东西:

| 世界 | 解析到 | 后果 |
|---|---|---|
| worktree(无实库) | `<worktree>/data/…` | 跑完留下 9 表 / 121 行 / 188KB 的**残桩** |
| 主 checkout(有实库) | 111MB 的**活生产库**(cron 正在写) | 测试直接**写生产库**,而且完全无声 |

worktree 那一侧的下游伤害:`test_kickoff_slot_normalisation` 的四个哨兵用
`@pytest.mark.skipif(not _DB.exists())` 判「本地有没有观测库」。
**第一次**跑正确地 skip 掉,并留下残桩;**第二次**跑 `exists()` 变真 ⇒ 不再 skip
⇒ 改去量那个 121 行的空壳 ⇒ 撞在反空洞断言 `tot > 1000` 上。

⚠️ `.gitignore` 里有 `*.db` ⇒ **`git status` 永远看不见残桩**,只有 `-wal`/`-shm`
会露头。这是它藏了这么久的原因。

⭐ 实测(2026-09-01):残桩还**在同一轮里**多咬了两口 ——
`test_fixture_anchored_zh_overrides`(5 条)和 `test_ucl_qualifier_zh_overrides`
(2 条)本该 skip,却因为字母序在前的测试先造出了残桩而改去量它,红了 7 条。
装上本文件之后这 7 条恢复 skip。⇒ 「12 条无关基线」里有 7 条其实是这个病。

## 三层,各修各的

**① 环境变量重定向** —— 把 `NUTMEG_V4_OBSERVATION_DB` 指到本次会话的 tmp 库。
这是**预防**,也是唯一跨进程的一层(子进程继承 `os.environ`)。

**② 连接时拦截** —— 以**可写**方式打开被守路径 ⇒ 记账 + 抛。
主 checkout 里第 ③ 层恒哑(实库本来就在),只剩这层还在守。

**③ 逐条测试后查文件** —— 残桩出现 ⇒ 点名造它的那条 + 扫掉。
第 ② 层是进程内的,拦不住 `subprocess.Popen` 起的 uvicorn
(`test_e2e_playwright` 正是这一路)。

## ⛔ 为什么不是一张文件名单

被点名的候选文件是**扫了一半**的结果,而写死名单的护栏会随新测试悄悄失效
(本仓已点名过这族:判闸钉子实测只盖 3/39,而它从没红过)。
⇒ 本文件**自己发现人口**:不问「谁会造」,只问「谁碰了它」,由 pytest 报出
**是哪条 test**。实测这套自己找出来的人口 = 2 文件 / 13 条,
和事先那份名单**没有交集**。

配套自检见 `tests/v4/test_observation_db_guard.py` —— 护栏自己也要有空包弹,
否则「一直绿」不是它在保护你的证据。

════════════════════════════════════════════════════════════════════
第二部分 —— Odds API 出口闸(💸 这一条是真金白银)
════════════════════════════════════════════════════════════════════

🚨 测试期绝不花钱:Odds API 的**出口闸**(2026-09-01)。

## 为什么要有这个文件

`odds_api._request` 的判据是 ``if cf.exists() and not refresh and fresh_enough``
—— 也就是说 **``refresh=False`` 不等于「只读缓存」**:同参数的缓存文件**不存在**
时它直接 fall through 到 live fetch,一次 = 一次真消费。

这条路 2026-09-01 才被接进收盘线采集(`observation/closing_odds.capture_books_for_sport`
与 `cli/ingest_odds._gather_rows`),而测试**恰好**踩在它的盲区上:测试普遍
monkeypatch 掉 `fetch_pinnacle_lookup` ⇒ 同参数的缓存文件**从没被写过** ⇒
紧随其后的多书商拉取必然是 cache miss ⇒ 在 `.env` 已 source 的 owner 机器上,
**每个这样的用例就是一次真实付费请求**。

🚨 **「CI 和 worktree 没钥匙所以看不见」是错的 —— worktree 有钥匙。**
`nutmeg/config.py` 顶上是裸的 `load_dotenv()`,而 `find_dotenv()` **从 CWD 逐级
向上找**:worktree → `.claude/worktrees/` → `.claude/` → `/Users/ninoo/Nutmeg/.env`
⇒ 命中。实测(2026-09-01):在一个**自身没有 `.env`、shell 里也没有那个环境变量**
的 worktree 里跑一次 `pytest`,写出了 33 个新的 `data/external/odds_api/*.json`,
内容是当天真实盘口 —— **33 次真实付费请求,全程一条红都没有**
(`capture_books_for_sport` fail-soft,花了钱也全绿)。
⇒ 「一直绿」在这条路上从来不是「没在花钱」的证据。

## ⛔ 为什么不是逐文件的 autouse fixture

逐文件 = 一份**写死的名单**,而名单会掉队:今天是 13 个文件,明天谁新写一个
`_gather_rows` 的用例就又漏一个,且**漏了不会红**(fail-soft 吞掉一切)。
本文件把闸放在**唯一的出口**(`odds_api._client` / `odds_api_history.httpx`)上,
⇒ 谁新走这条路都会被自动发现,不需要有人记得更新名单。

## 两层,各管一件事

1. **`_tests_hold_no_odds_api_key`(模块级,进程级)** —— 把 `NUTMEG_ODDS_API_KEY`
   在 os.environ 里置空。os.environ 优先级高于 `.env`(pydantic-settings 与
   `load_dotenv(override=False)` 都是这个顺序),⇒ 即使 owner 的 `.env` 就在
   CWD 也拿不到钥匙。**这一层是唯一能覆盖子进程的**(E2E 会 spawn uvicorn,
   那个进程继承 environ,面板上的「🔄 刷新盘口」同样会走到这条路)。
2. **`_no_live_odds_api`(autouse,每个用例)** —— 把出口函数换成记录器:
   ⚠️ **只抛异常是不够的** —— `capture_books_for_sport` 整体 fail-soft,
   抛出去当场就被吞掉,用例照样全绿,闸等于不存在。所以记录器**另外记一笔**,
   在 teardown 里 `pytest.fail` ⇒ 吞不掉。
   抛的仍是 `OddsApiError`(= 没钥匙时的同一条控制流)⇒ 闸本身不改变任何
   现有用例的行为,只让「本来会花钱」的那一刻变得可见。

需要**故意**验证这条路的用例(如 `test_odds_api_overlay` 的熔断器组)自己
`monkeypatch.setattr(odds_api, "_client", ...)` 即可覆盖本闸;需要**读**被拦下的
调用的用例(如本闸的自检)显式申明 `live_odds_api_calls` fixture 认领它们。
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import traceback
import urllib.parse
import warnings
from pathlib import Path

import pytest

#: 仓库根 = 本文件的上一级。worktree 里是 worktree,主 checkout 里是主 checkout。
_ROOT = Path(__file__).resolve().parents[1]

#: 唯一被守的路径。⚠️ 不是「data/ 下任何东西」—— 那会把
#: `.data_freshness_heartbeat` 这类正当产物一起误伤。
_GUARDED = (_ROOT / "data" / "v4_observation.db").resolve()

#: ⚠️ 存在性一律走**在 import 时抓住的** `os.path.exists`,不用 `Path.exists()`。
#: 2026-09-02 实测的真交叉伤:`test_artifact_identity_guard` 有一条测试
#: `monkeypatch.setattr(Path, "stat", _boom)`(它钉的是「身份判定不碰文件系统」),
#: 而 `Path.exists()` 内部走 `Path.stat` ⇒ 本护栏的 **teardown** 当场炸,
#: 报的还是**别人**的断言消息("身份判定不该碰文件系统"),排查会被指到错的地方。
#: `os.path.exists` 走 `os.stat`,和那条 patch 无关。
_real_exists = os.path.exists


def _guarded_exists(suffix: str = "") -> bool:
    return _real_exists(str(_GUARDED) + suffix)

#: SQLite 的伴生文件。扫残桩时必须一起扫,否则 `-wal` 会把它复活。
_SIDECARS = ("", "-wal", "-shm", "-journal")

#: 🚨 会话开始时它就在吗?在 ⇒ 那是**真库**(主 checkout),第 ③ 层一个字都不碰它。
#: 不在 ⇒ 之后任何时刻出现,都只可能是本次跑出来的残桩。
#:
#: ⚠️ 用「会话起点存在性」而不是 mtime/大小:主 checkout 的实库有 cron 在并发写,
#: 拿 mtime 判「被改过」会变成随机假红,而**假红比假绿更贵**。
#: 这也是为什么必须有第 ② 层 —— 主 checkout 里这个常量恒 True,③ 恒哑。
_EXISTED_AT_START = _guarded_exists()


# ---------- ① 预防:把观测库环境变量重定向到本次会话的 tmp -----------------
#
# 必须在 `nutmeg.config` 被 import 之前跑完(本文件是 conftest,pytest 在收集
# 任何测试模块之前就 import 它 ⇒ 满足)。`load_dotenv()` 默认 `override=False`,
# ⇒ 我们先占住这个键,`.env` 里那个相对值就进不来。
#
# ⭐ 为什么是「重定向」而不是「删掉」:删掉 ⇒ `snapshot_db=None` ⇒ 录制代码路径
# 整条不跑,那是**改了被测行为**。重定向保留原路径,只把落点搬到 tmp。

_SESSION_OBS_DIR = tempfile.mkdtemp(prefix="nutmeg-tests-obs-")


def _needs_redirect(value: str | None) -> bool:
    """只放行「明确指向别处的绝对路径」;未设置 / 相对 / 正是被守路径 ⇒ 重定向。

    相对路径一律重定向:它的含义取决于消费方的 CWD,而那是不可控的 ——
    本病的整条因果链就是从这一点开始的。
    """
    if not value:
        return True
    p = Path(value)
    return (not p.is_absolute()) or p.resolve() == _GUARDED


if _needs_redirect(os.environ.get("NUTMEG_V4_OBSERVATION_DB")):
    os.environ["NUTMEG_V4_OBSERVATION_DB"] = str(Path(_SESSION_OBS_DIR) / "obs.db")


# ---------- ② 连接时拦截(主 checkout 里唯一有效的一道)-------------------

_real_connect = sqlite3.connect

#: 记账本。🚨 光靠 raise 不够 —— 被守的调用点大多在 fail-soft 的
#: `except Exception:` 里(`observation_routes` 整个文件都是这个风格),
#: 异常会被吞掉 ⇒ 测试照绿,而生产库照样被打开过。
#: 记一笔在这里,吞不掉,由 teardown 统一报。
_OFFENSES: list[str] = []


def _connect_target(database: object, uri: bool) -> tuple[Path | None, bool]:
    """把 `sqlite3.connect` 的第一个参数解成 `(绝对路径, 是否只读)`。

    非文件目标(`:memory:`、文件描述符、`mode=memory`)返回 `(None, _)`。
    """
    if isinstance(database, int):          # 文件描述符
        return None, False
    try:
        raw = os.fspath(database)          # type: ignore[arg-type]
    except TypeError:
        return None, False
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if raw in (":memory:", ""):
        return None, False

    readonly = False
    if uri and raw.startswith("file:"):
        parts = urllib.parse.urlsplit(raw)
        q = urllib.parse.parse_qs(parts.query)
        mode = (q.get("mode") or [""])[0]
        if mode == "memory":
            return None, False
        readonly = mode == "ro" or (q.get("immutable") or [""])[0] in ("1", "true")
        raw = urllib.parse.unquote(parts.path)
        if not raw:
            return None, False

    # 便宜的预筛:全套件几千次 connect,`.resolve()` 是系统调用,别每次都做。
    if not raw.endswith(_GUARDED.name):
        return None, readonly
    return Path(raw).resolve(), readonly


def _guarded_connect(database, *args, **kwargs):  # type: ignore[no-untyped-def]
    uri = bool(kwargs.get("uri", False))
    if not uri and len(args) >= 7:         # 位置参数形式的 uri
        uri = bool(args[6])
    target, readonly = _connect_target(database, uri)
    if target == _GUARDED and not readonly:
        _OFFENSES.append("".join(traceback.format_stack()[:-1][-6:]))
        raise RuntimeError(
            f"🚨 测试不许以**可写**方式打开生产观测库:{_GUARDED}\n"
            f"   只读是允许的(`sqlite3.connect(f'file:{{db}}?mode=ro', uri=True)`)。\n"
            f"   修法:显式传 tmp_path,或 monkeypatch NUTMEG_V4_OBSERVATION_DB。"
        )
    return _real_connect(database, *args, **kwargs)


sqlite3.connect = _guarded_connect          # type: ignore[assignment]
sqlite3.dbapi2.connect = _guarded_connect   # type: ignore[assignment]


# ---------- ③ 逐条测试后查文件(唯一能抓到子进程的一道)-------------------

#: 🚨 残桩的体量上限。超过它的**一律不删**,不管前面的判据怎么说。
#:
#: 2026-09-02 血的教训:我为了验证「保险失效会删生产库」这发空包弹,把
#: `created = _guarded_exists() and not _EXISTED_AT_START` 改成了
#: `created = _guarded_exists()`,然后**在主仓**跑了一次 pytest ——
#: 那一轮自己的 autouse fixture 就用这份被改坏的 conftest 执行了 `_sweep()`,
#: **把 111MB 的生产观测库 unlink 了**。已从 daily_backup 恢复,丢了约 21 小时
#: 的 forward-only 采集(polymarket_gaps 1,672 行等,point-in-time,补不回来)。
#:
#: ⇒ 单靠 `_EXISTED_AT_START` 一道判据是不够的:它是**正确的**,但它可以被改坏,
#:   而改坏它的代价是不可逆的。真正的残桩实测只有 **121~127 行 / 188KB** 左右
#:   (那是几条 CLI 用例走默认 `--db` 造出来的空壳),而生产库是**万级行 / 上百 MB**。
#:   两者差三个数量级 ⇒ 一条体量闸就能把「不可逆」变成「最多留个残桩」。
#: ⚠️ 阈值取 8MB:比实测残桩大 40 倍(留足未来残桩长胖的余地),
#:   比生产库(2026-09 已 108MB)小一个数量级。⛔ 别往上调 ——
#:   往上调 = 把这道兜底的保护范围往生产库那一侧挪。
_MAX_STUB_BYTES = 8 * 1024 * 1024


def _sweep() -> list[str]:
    """扫掉本次跑出来的残桩(含伴生文件),返回扫了哪些。

    ⛔ **体量闸是纵深防御,不是主判据**。主判据仍然是 `_EXISTED_AT_START`
    (会话开始就在 = 真库,一个字都不碰)。这道闸挡的是「主判据被改坏」的那一天
    —— 而那一天已经来过一次了,见 `_MAX_STUB_BYTES` 上面那段。
    """
    gone = []
    for suffix in _SIDECARS:
        if not _guarded_exists(suffix):
            continue
        p = Path(str(_GUARDED) + suffix)
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > _MAX_STUB_BYTES:
            # 🚨 到这里说明**主判据已经失效**了 —— 大声说,别静默跳过。
            warnings.warn(
                f"🚨 拒绝删除 {p.name}:{size:,} 字节 > 残桩上限 "
                f"{_MAX_STUB_BYTES:,} —— 这不是测试造出来的残桩,像是**真库**。"
                f"\n   `_EXISTED_AT_START` 这道主判据本该拦住它却没有,"
                f"去查是不是有人动了 conftest(2026-09-02 就是这么丢掉 21 小时数据的)。",
                stacklevel=2)
            continue
        gone.append(p.name)
        p.unlink()
    return gone


@pytest.fixture(autouse=True)
def _no_stray_observation_db():
    """每条测试跑完看一眼:碰过没有?造了没有?

    扫掉残桩是**判据的一部分**,不只是打扫:不删的话,第一个造它的测试之后
    所有同病测试都看到「文件已存在」⇒ 只能抓到一个,抓不到人口。
    """
    _OFFENSES.clear()
    yield
    opened = list(_OFFENSES)
    _OFFENSES.clear()
    created = _guarded_exists() and not _EXISTED_AT_START
    if not opened and not created:
        return
    gone = _sweep() if created else []
    stacks = "".join(
        f"     | {ln}\n" for w in opened for ln in w.rstrip().splitlines()
    )
    pytest.fail(
        f"🚨 本条测试碰了仓库根下的生产观测库:{_GUARDED}\n"
        + (f"   · 以**可写**方式打开过 {len(opened)} 次,调用栈:\n{stacks}"
           if opened else "")
        + (f"   · 在工作树里留下了残桩(已自动扫除:{', '.join(gone)})\n"
           if created else "")
        + "\n"
        "   病因:某条路径解析到了仓库根下的观测库 —— 通常是\n"
        "   `NUTMEG_V4_OBSERVATION_DB` 或某个 CLI `--db` 默认值用了**相对路径**。\n"
        "   修法:显式传 tmp_path(`--db {tmp_path}/obs.db`),\n"
        "        或 monkeypatch 环境变量 NUTMEG_V4_OBSERVATION_DB。\n"
        "   ⛔ 别把本护栏关掉:残桩会让**下一轮**跑的数据驱动哨兵\n"
        "      (test_kickoff_slot_normalisation 等)改去量那个 121 行的空壳。",
        pytrace=False,
    )


@pytest.fixture
def production_observation_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """把观测库指回**真库**(仓库根下那个),给只读哨兵用。

    ⚠️ 为什么需要这个:第 ① 层把 `NUTMEG_V4_OBSERVATION_DB` 挪走之后,
    「跟着生产解析链去读真库 schema」的哨兵会在主 checkout 里从**跑**变成
    **skip** —— 实测 `test_admin_freshness` 有 4 条。那是护栏自己造成的
    静默覆盖倒退,不是本来就有的。

    ⭐ 指回去是安全的,因为第 ② 层还在:只读放行,可写照样拦 + 记账。
    ⇒ 读/写的边界在这里变成显式的,而不是靠「谁也别碰它」。

    库不在(worktree / CI)⇒ skip,不假装通过。
    """
    if not _guarded_exists():
        pytest.skip(f"没有观测库({_GUARDED})—— 这条只在有真库的机器上有意义")
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(_GUARDED))
    return _GUARDED


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """兜底 + 收摊。

    ③ 只覆盖「某条测试的 teardown 窗口」;收集期、或 module 级 fixture 的
    teardown 里造出来的,得靠这里。
    """
    try:
        if not _EXISTED_AT_START and _guarded_exists():
            warnings.warn(
                f"🚨 会话期间出现生产观测库残桩,且不在任何单条测试的 teardown "
                f"窗口内:{_GUARDED} —— 已扫除 {', '.join(_sweep())}",
                stacklevel=1,
            )
    finally:
        shutil.rmtree(_SESSION_OBS_DIR, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════
# 第二部分 —— Odds API 出口闸
# ⚠️ 放在第一部分**之后**:上面那段设 `NUTMEG_V4_OBSERVATION_DB`,
#    而下面那段会 `get_settings.cache_clear()` —— 清缓存必须是最后一步,
#    否则先清后设,下一次 get_settings() 读到的还是旧值。
# ══════════════════════════════════════════════════════════════════════════

import os

import pytest

# ── 第 1 层:进程级(含子进程)──────────────────────────────────────────────
# 必须在 `nutmeg.config` 被 import 之前跑,所以放模块级而不是 fixture:
# conftest.py 的 import 早于任何测试模块的收集。
# 置**空串**而不是 delenv —— `load_dotenv()` 与 pydantic-settings 都只在
# key **不存在**时才回落到 `.env`;空串是「存在且为假」,两边都盖得住。
os.environ["NUTMEG_ODDS_API_KEY"] = ""
# 🚨 2026-09-02 补上 API-Football —— 它**同样计价**,而原来的闸只挡了 Odds API。
#    实测:装上 Odds 闸之后的那一轮,`data/external/api_football/` 里仍新增
#    **356** 个 json,而 `api_football._request` 只在 HTTP 200 之后才 `_tmp.replace(cf)`
#    ⇒ **一个文件 = 一次真实请求**。⇒ 「测试期静默烧钱」当时只修了一半,
#    而且修完那一轮的花费主体恰恰是没修的那一半。
os.environ["NUTMEG_API_FOOTBALL_KEY"] = ""
try:  # 若已被别处 import 过,lru_cache 里可能已经缓存了真钥匙
    from nutmeg.config import get_settings as _get_settings
except Exception:  # pragma: no cover - config 还没装好时不该拖垮收集
    pass
else:
    _get_settings.cache_clear()


class _BlockedLiveCall(Exception):
    """内部信号;永远不会逃出本文件(teardown 用记录而不是异常来判定)。"""


class _Recorder:
    """记下每一次「本来会发出去」的调用。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.acknowledged = False
        self.real = None      # 打补丁前的真出口(给「被测对象就是出口」的用例装回来)

    def __len__(self) -> int:
        return len(self.calls)

    def note(self, what: str) -> None:
        self.calls.append(what)


@pytest.fixture(autouse=True)
def _no_live_odds_api(monkeypatch, request):
    """出口闸:任何用例只要走到 live fetch 就会红,且**红得看得见**。"""
    from nutmeg.v4.data.sources import odds_api, odds_api_history

    rec = _Recorder()
    request.node._live_odds_api_recorder = rec

    # 熔断器是进程级全局:上一个用例把它打开会让 `_request` 在到达出口**之前**
    # 就抛,于是本闸测不到那次「本来会花钱」⇒ 每个用例先归零,别让闸被别人的
    # 残留状态蒙住眼睛。
    odds_api.reset_quota_breaker()

    def _blocked_client():
        rec.note("odds_api._client() → sports/*/odds (live fetch, cache miss)")
        # 抛 OddsApiError = 没钥匙时的同一条控制流 ⇒ 闸不改变现有用例的行为。
        raise odds_api.OddsApiError(
            "BLOCKED by tests/conftest.py: a live Odds API request was about to "
            "leave the process."
        )

    monkeypatch.setattr(odds_api, "_client", _blocked_client)

    class _NoHttpx:  # odds_api_history 用模块级 `httpx.get`(历史端点 = 20 credits/次)
        @staticmethod
        def get(url, **kwargs):
            rec.note(f"odds_api_history: httpx.get({url})")
            raise _BlockedLiveCall(url)

    monkeypatch.setattr(odds_api_history, "httpx", _NoHttpx)

    yield rec

    if rec.calls and not rec.acknowledged:
        pytest.fail(
            "🚨 这个用例走到了 Odds API 的 live fetch —— 在 `.env` 已 source 的机器上"
            "它就是一次真实付费请求(测试期已被 tests/conftest.py 拦下):\n  "
            + "\n  ".join(rec.calls)
            + "\n\n为什么会这样:`refresh=False` 不是「只读缓存」—— `odds_api._request`"
            "\n在**缓存文件不存在**时会 fall through 到 live fetch。用例 monkeypatch 掉"
            "\n`fetch_pinnacle_lookup` 之后,同参数的缓存从没被写过 ⇒ 后面那次多书商"
            "\n拉取必然 miss。"
            "\n\n怎么修(任选其一,按优先级):"
            "\n  1. 在用例里把 `book_snapshots.capture_books_for_sport` 换成 no-op"
            "\n     —— 被测的东西不是它的时候,这是最省事的;"
            "\n  2. 把 `odds_api._request` 换掉(见 tests/v4/test_book_consensus.py),"
            "\n     用例真要覆盖采集器本身时用这个;"
            "\n  3. 真要覆盖出口行为,就自己 monkeypatch `odds_api._client`"
            "\n     (见 tests/v4/test_odds_api_overlay.py 的熔断器组)。",
            pytrace=False,
        )


@pytest.fixture(autouse=True)
def _no_live_api_football(monkeypatch, request):
    """API-Football 的出口闸 —— 和上面那道**同形**,因为病是同一个。

    `api_football._client()`(api_football.py:87)是唯一出口:`_request` 第 182 行
    `r = _client().get(...)`,而落盘在 HTTP 200 **之后**(第 229-231 行的
    `_tmp.replace(cf)`)⇒ `data/external/api_football/**.json` 的**每一个文件都对应
    一次真实请求**。实测每棵 worktree 564 个、主仓今天动过 939 个。

    ⭐ 抛的是 `ApiFootballError` —— 那正是**没有 key 时** `_client()` 自己抛的那一条
    (api_football.py:90-93)⇒ 闸不引入任何新的控制流。
    ⚠️ 同样要**另记一笔**:AF 的调用点也大量在 fail-soft 的 `except Exception` 里
    (`ingest_odds._gather_rows` 的 `log.warning("%s fixtures error: %s")` 就是),
    只抛的话花了钱照样全绿。
    """
    from nutmeg.v4.data.sources import api_football

    rec = _Recorder()
    # ⚠️ 在打补丁**之前**抓住真出口 —— `real_api_football_client` fixture 要拿它
    #    把被测对象装回来(monkeypatch 每个用例都会还原,所以这里读到的一定是真的)。
    rec.real = api_football._client
    request.node._live_api_football_recorder = rec

    def _blocked_client():
        rec.note("api_football._client() → v3.football.api-sports.io (live fetch)")
        raise api_football.ApiFootballError(
            "BLOCKED by tests/conftest.py: a live API-Football request was about "
            "to leave the process."
        )

    monkeypatch.setattr(api_football, "_client", _blocked_client)
    yield rec

    if rec.calls and not rec.acknowledged:
        pytest.fail(
            "🚨 这个用例走到了 API-Football 的 live fetch —— 在 `.env` 已 source 的"
            "机器上它就是一次真实付费请求(测试期已被 tests/conftest.py 拦下):\n  "
            + "\n  ".join(rec.calls)
            + "\n\n怎么修:给用例显式传 `cache_dir=tmp_path` 并预置缓存文件,"
            "\n或 monkeypatch 掉你调用的那个 fetch_* 函数;"
            "\n真要覆盖出口行为就自己 monkeypatch `api_football._client`。",
            pytrace=False,
        )


@pytest.fixture
def live_api_football_calls(request, _no_live_api_football):
    """**认领**本用例被拦下的 AF live 调用(只给验证闸本身的用例用)。"""
    _no_live_api_football.acknowledged = True
    return _no_live_api_football


@pytest.fixture(autouse=True)
def _no_forced_wc_fixture_fetch(monkeypatch, request):
    """🩹 **止血贴,不是设计** —— 生产侧 `/today-recommendations` 每次都强制拉 WC 赛程。

        routes.py:3416  today_recommendations → predictions_wc(...)     ← **无条件**
        routes.py:3791    fetch_fixtures_for_league_season("WC", season)
        api_football.py:502  _request("/fixtures", ..., refresh=True)   ← **写死**强制刷新

    ⇒ 任何碰这个端点的用例都是一次真实付费请求。实测被 AF 闸抓出 **12 条**,
    横跨 4 个文件(test_today_recommendations / test_recommendation_version /
    test_today_pool_and_sliders / test_serving_oa_quota),而它们此前**一条红都没有**
    —— 调用点 fail-soft,花了钱照样全绿。

    ⛔ 为什么放在 conftest 而不是逐文件加:逐文件 = 一份**写死的名单**,而名单会掉队
    —— 今天是 4 个文件,明天谁再写一条碰这个端点的用例就又漏一个,**且漏了不会红**。
    这正是本仓刚刚点名过的形状(判闸钉子实测只盖 3/39)。

    ⚠️ 这里**只挡测试**。生产那条 `refresh=True` 是另一件事(与
    [[odds-api-serving-path-overspend]] 同族:额度真凶是**服务路径**不是 cron),
    已另开任务去量。那条修好之后,本 fixture 应该连同这段注释一起删掉。

    真要测这个函数本身的用例,申明 `real_wc_fixture_fetch` 豁免。
    """
    from nutmeg.v4.data.sources import api_football
    real = api_football.fetch_fixtures_for_league_season
    request.node._real_wc_fetch = real
    monkeypatch.setattr(api_football, "fetch_fixtures_for_league_season",
                        lambda *a, **k: [])


@pytest.fixture
def real_wc_fixture_fetch(monkeypatch, request, _no_forced_wc_fixture_fetch):
    """把真的 `fetch_fixtures_for_league_season` 装回来(被测对象就是它时用)。

    ⭐ 装回来**不放行花钱**:AF 出口闸(`_no_live_api_football`)仍在,
    真要出网仍会被拦下并记账。这里放开的只是那层 no-op。
    """
    from nutmeg.v4.data.sources import api_football
    monkeypatch.setattr(api_football, "fetch_fixtures_for_league_season",
                        request.node._real_wc_fetch)
    return request.node._real_wc_fetch


@pytest.fixture
def real_api_football_client(monkeypatch, _no_live_api_football):
    """把**真的** `api_football._client` 装回来。

    ⚠️ 只给「被测对象就是 `_client` 自己」的用例用(如
    `TestClientErrorWhenNoKey::test_raises_when_key_missing` —— 它断言没 key 时
    抛的那条消息,而闸抛的是自己那条 ⇒ 不装回来就永远对不上)。
    ⭐ 装回来**不等于放行花钱**:那类用例都是在 `_client()` 真正建连**之前**
    就该抛的路径(缺 key / 配置错)。真要发请求的用例不该申明本 fixture。
    """
    from nutmeg.v4.data.sources import api_football
    monkeypatch.setattr(api_football, "_client", _no_live_api_football.real)
    return _no_live_api_football.real


@pytest.fixture
def live_odds_api_calls(request, _no_live_odds_api):
    """**认领**本用例被拦下的 live 调用 —— 申明它 = 「我就是来看这个的」。

    ⚠️ 只给「验证闸本身」的用例用。普通用例申明它就等于把闸关掉了。
    """
    _no_live_odds_api.acknowledged = True
    return _no_live_odds_api
