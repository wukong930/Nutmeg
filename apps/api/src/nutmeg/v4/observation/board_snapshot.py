"""盘面反事实快照 —— 记**事实**,不记**选择**(2026-08-11)。

## 为什么建它

owner 问「串关构造器能不能有记录 + 自我学习」。查了一下账本:

```
parlay_recommendations   4 行   ← 其中 3 行 k_legs=1(单关)⇒ 真串关票 1 张
settlements              4 行
```

⇒ **从自己的票学 = 从 n=1 学。** 而 4 串 1 的实测是 −30.4% ±33.5pp(n=550),
在这个 SE 量级上闭环只会拟合噪声,并且大概率会重新「发现」已被**正面测死**的
档位加权(甜区/边缘 σ_EV 实测 4.6% vs 4.6%,24 次 ROI 规则 0 条过闸)。

但每场比赛**三条腿都会结算** —— 你没买的那两条,结果一样白送。
盘面 ~400 条腿/周,票 ~1 张/累计。**学习信号该来自盘面,不是票。**

## 为什么记盘面而不是记「被选中的腿」

⭐ 选腿逻辑(`_boardLegs`)跑在**浏览器里**(dashboard.html 11 处,routes.py 0 处)。
服务端要记「哪条腿被选中」就得在后端重写一遍选腿规则 —— 那就是 2026-08-10 刚治好的
「一条规则三份拷贝、谁都不拥有它」。

⇒ 记**事实**(每条腿的 P / 下界 / 竞彩 SP / Pinnacle),选择留给事后回放。
**规则会变,事实不会。**

## 🚨 上线前审查改掉的三件事(2026-08-12,49 个 agent / 37 条存活发现)

第一版写完自测全绿、真跑也出了 129 条腿 —— 然后审查把它拆了。三条都属于
「**看起来在工作**」的那类,所以自测抓不到:

**① 两个概率族被配成一对(blocker)。** 1X2 腿我存 `p = p_*_1x2`、`p_lo = onex_lo_*`,
但 `onex_lo_*` 是 **Pinnacle 去vig 市场 P** 的下界(routes.py `_onex_lo(mkt)`),
而标准模式下 `p_*_1x2` 是**模型 P**。拿 `league_predictions` 的真实行复算:
153 条腿里 **42 条(27.5%)会出现 `p_lo > p`** —— 区间直接翻过来;剩下 72.5% 更坏,
因为它看着完全正常。夏季只有市场模式出腿(那时两者恰好同源)⇒ **今天测不出来,
秋天才发作**。修法:`p_model` / `p_market` **两列都存**,再加一列 `p_lo_of`
明写下界是谁的下界 —— 让「配错族」在 schema 层就不可能。

**② 「喂料断了」被记成「盘面本来就是空的」(blocker)。** 两个端点在内部抓取失败时
`except Exception -> rows = []`,照样返回 **HTTP 200**。而我只取 `predictions`,
把响应里仅有的两个鉴别器 `fixtures_fetched` / `pending_fixtures` **当场丢掉**,
然后打印「证明这次真的跑过且盘面是空的」—— **那句话是假的**。
审查用桩服务跑出来:喂料断 vs 真空盘,两次输出**逐字相同**、落库**完全不可区分**。
⭐ 这正是本模块头注里写着要防的那个家族,被我在同一个文件里犯了一次。
修法:`feed_json` 落库 + 那句断言改成陈述。

**③ `match_date` 这个字段端点根本不下发**(真实键是 `date`)⇒ 主路径是死代码,
一切靠 `kickoff_utc[:10]` 兜底,而**测试夹具喂的正是那个不存在的键** ——
护栏守的是生产永远走不到的分支。同族:「检查的前提没人检查」。

## ⛔ 刻意不记的东西

· **rank / 名次** —— 实测名次不预测 ROI(#1 在任何一档都不是最好的,SE ±10~65pp)。
· **「这条腿过没过闸」** —— 那是规则。`p_lo` 和 `jc_sp` 都在,任何闸都能事后重算;
  存「当时过没过」反而把快照锁死在今天这套规则上。

## 用法

    nutmeg-snapshot-board                    # 打本地端点,写一次快照
    nutmeg-snapshot-board --dry-run          # 不写库(⚠️ 端点照打,见 CLI 文件头)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: 三条腿的下标 —— 与 `implied_handicap_lines` / 1X2 的 (主,平,客) 顺序一致
LEG_LABELS = ("home", "draw", "away")

#: 竞彩没上架时,记哪几条让球线。
#: ⭐ 审查发现:只记「竞彩在卖那条线」会让 hhad 的**未上架人口结构性为 0**,
#: 于是「竞彩的选择函数在让球盘上有没有效应」这个问题永远只能得到
#: 「没有效应」这个**假答案**(分母是空的)。而竞彩实际只卖 −1/0/+1 三条线。
#: ⇒ 三条线一律记,再用 `line_source` 标出哪条是竞彩真在卖的。
#: ⚠️ 「会下注的人口」这条纪律**没有放松**,它现在由列来表达:
#:     WHERE line_source='jingcai' AND jc_sp IS NOT NULL
_HC_LINES_ALWAYS = (-1, 0, 1)

_PROVENANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot_provenance (
    provenance_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    fe_version     TEXT,              -- 服务端自报的版本(**daemon 内存里那份**)
    git_sha        TEXT,              -- CLI 这棵树的 HEAD;取不到就 NULL,不猜
    -- ⭐ 承重:当时**活着**的校准常数,从模块读出来的,不是抄的。
    constants_json TEXT NOT NULL,
    -- 🚨 诚实标注:常数是 **CLI 进程**新 import 的,而 P 是 **daemon** 算的,
    -- 且 daemon 不热载代码 ⇒ 改了常数没重启时两者会**静默劈叉**。
    -- `constants_mtime` 给回放者一个能自己判断的钩子(模块比 fe_version 新 ⇒ 存疑)。
    constants_source TEXT,
    constants_mtime  TEXT,
    -- 🚨 喂料健康度:没有它,「盘面空」和「上游挂了」在库里长得一模一样。
    feed_json      TEXT,
    note           TEXT
);
"""

_LEG_SCHEMA = """
CREATE TABLE IF NOT EXISTS board_leg_snapshot (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    provenance_id  INTEGER NOT NULL,
    captured_at    TEXT NOT NULL,
    -- 身份(与 jingcai_sp 同一把键,便于 join 结算)
    match_date     TEXT NOT NULL,
    league         TEXT,
    home_team      TEXT NOT NULL,
    away_team      TEXT NOT NULL,
    kickoff_utc    TEXT,
    market         TEXT NOT NULL,     -- 'had' | 'hhad'
    handicap_home  INTEGER,
    line_source    TEXT,              -- 'jingcai'=竞彩真在卖 | 'model'=只有我们的网格
    leg            INTEGER NOT NULL,  -- 0 主/让胜 · 1 平/让平 · 2 客/让负
    -- 概率:**两个族分开存**(见文件头 ①)
    p_model        REAL,   -- 1X2: p_*_1x2(标准模式=模型,市场模式=Pinnacle);hhad: 网格值
    p_market       REAL,   -- 1X2: p_*_market(Pinnacle 去vig);hhad: NULL(网格本就市场反推)
    p_lo           REAL,   -- 判闸下界
    p_lo_of        TEXT,   -- ⭐ 下界是**谁**的下界:'p_market' | 'p_model'
    -- 盘口
    jc_sp          REAL,              -- 竞彩 SP;没上架就 NULL
    psc            REAL,              -- Pinnacle 1X2 原盘赔率(含 vig)
    psc_over       REAL,
    psc_under      REAL,
    ou_line        REAL,              -- 大小球主盘线 —— 回放让球网格的另一半锚
    -- 新鲜度(forward-only:「当时那个价多旧」事后重建不出来)
    jc_captured_at TEXT,
    odds_update    TEXT,
    hours_to_ko    REAL,
    market_mode    INTEGER,
    single_available INTEGER,
    UNIQUE(captured_at, match_date, home_team, away_team, market, handicap_home, leg)
);
-- 🚨 上面那条 UNIQUE 对 1X2 腿**不起作用**:它们的 handicap_home 是 NULL,
-- 而 SQLite 把 NULL 视为**互不相等** ⇒ 同秒重跑时三条 1X2 腿会重复插入
-- (实测:第二次跑 inserted=3 而不是 0)。这条是写幂等性测试时抓到的真 bug,
-- 不是测试写错 —— 没有它,cron 重试/手动补跑会静默把 1X2 腿灌成两份,
-- 而事后按 captured_at 分组统计时那批重复长得和「盘面真的有两代」一模一样。
-- ⇒ 用 COALESCE 表达式索引兜住 NULL 这一侧。
CREATE UNIQUE INDEX IF NOT EXISTS uq_board_leg_snap
    ON board_leg_snapshot (captured_at, match_date, home_team, away_team,
                           market, COALESCE(handicap_home, 99), leg);
CREATE INDEX IF NOT EXISTS idx_board_leg_snap_match
    ON board_leg_snapshot (match_date, home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_board_leg_snap_ko
    ON board_leg_snapshot (kickoff_utc);
"""

#: 前向迁移 —— `CREATE TABLE IF NOT EXISTS` 对**已存在**的表是空操作,
#: 所以新增列必须自己 ALTER,否则 INSERT 直接 `no such column` 把 cron 打死。
#: 本仓惯例(`jingcai_sp` 同款):加列同步补 SET,双写 DDL + 迁移。
_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "snapshot_provenance": [
        ("constants_source", "TEXT"), ("constants_mtime", "TEXT"), ("feed_json", "TEXT"),
    ],
    "board_leg_snapshot": [
        ("line_source", "TEXT"), ("p_model", "REAL"), ("p_market", "REAL"),
        ("p_lo_of", "TEXT"), ("psc_over", "REAL"), ("psc_under", "REAL"),
        ("ou_line", "REAL"), ("jc_captured_at", "TEXT"), ("odds_update", "TEXT"),
    ],
}


def ensure_tables(conn: sqlite3.Connection) -> None:
    """幂等 DDL + 前向迁移 —— 每次写之前调。"""
    conn.executescript(_PROVENANCE_SCHEMA)
    conn.executescript(_LEG_SCHEMA)
    for table, cols in _MIGRATIONS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


#: 回放一条腿的 P 与下界所需的**全部**常数。
#: ⚠️ 审查抓到第一版漏了 δ₋₂ 的 6 个(已上线 2026-07-27)和网格的 2 个。
#: 漏一个,事后就回放不出当时的下界 —— 而这是 forward-only,补不回来。
_CONST_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("market_handicap", "nutmeg.v4.model.market_handicap", (
        # δ₋₁ / δ₊₁ 与其 SE
        "_C1_DELTA", "_C1_DELTA_P1", "_C1_DELTA_SE", "_C1_DELTA_P1_SE",
        "_C1_SE_K", "_UNCAL_SE", "_C1_THIRD_SE_M1", "_C1_THIRD_SE_P1",
        # δ₋₂(2026-07-27 上线)—— 第一版漏了这 6 个
        "_C2_DELTA_H", "_C2_DELTA_D", "_C2_DELTA_A",
        "_C2_SE_H", "_C2_SE_D", "_C2_SE_A",
        # 网格参数 —— 不记就重算不出 handicap_lines
        "DEFAULT_RHO", "DEFAULT_MAX_GOALS",
    )),
    ("onex_calibration", "nutmeg.v4.model.onex_calibration", ("ONEX_SE", "ONEX_SE_K")),
)


def live_constants() -> dict[str, Any]:
    """把**当前进程里活着的**校准常数读出来。

    ⚠️ 必须 import 后读属性,**不许**在这里抄一份字面量 —— 抄的那份会随时间
    和真实值分家,而 provenance 一旦撒谎,整批快照的回放价值归零。

    取不到的键写 `None` 而不是省略:「这一版没有这个常数」和「我忘了记」
    是两件事,后者不该看起来像前者。
    ⭐ 审查抓到第一版的 except 分支**违反了自己这句话** —— import 一失败就把
    8 个键全省略、只留一个 `__error__`。现在无论成败都把键补齐。
    """
    out: dict[str, Any] = {}
    for prefix, module_path, names in _CONST_SPECS:
        mod = None
        err = None
        try:
            mod = __import__(module_path, fromlist=["_"])
        except Exception as exc:                          # noqa: BLE001
            err = repr(exc)
        for name in names:
            v = getattr(mod, name, None) if mod is not None else None
            out[f"{prefix}.{name}"] = list(v) if isinstance(v, tuple) else v
        if err:
            out[f"{prefix}.__error__"] = err
    return out


def _constants_mtime() -> str | None:
    """常数模块在磁盘上的最新改动时刻。

    ⭐ 它存在的唯一理由:`p`/`p_lo` 是 **daemon** 算的,常数是 **CLI** 读的,
    而 daemon **不热载代码**。改了 δ 没重启 ⇒ 两者静默劈叉、快照记的是磁盘上
    那份而不是真正算出这些数的那份。留下这个时刻,回放者至少能自己发现
    「模块比 fe_version 新 ⇒ 这批 provenance 存疑」。
    """
    stamps = []
    for _prefix, module_path, _names in _CONST_SPECS:
        try:
            mod = __import__(module_path, fromlist=["_"])
            f = getattr(mod, "__file__", None)
            if f and Path(f).exists():
                stamps.append(Path(f).stat().st_mtime)
        except Exception:                                 # noqa: BLE001, S112
            continue
    if not stamps:
        return None
    return dt.datetime.fromtimestamp(max(stamps), dt.UTC).isoformat(timespec="seconds")


def _git_sha() -> str | None:
    """CLI 这棵树的 HEAD。

    ⚠️ 它描述的是**磁盘**,不是算出这些 P 的那个 daemon 进程,也忽略未提交改动。
    和 `fe_version`(daemon 自报)一起看才有意义。
    """
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5, check=False)
        return r.stdout.strip() or None
    except Exception:                                     # noqa: BLE001
        return None


def _hours_to_ko(kickoff_utc: str | None, now: dt.datetime) -> float | None:
    """距开球小时数(可为负)。

    ⚠️ 时间串没有时区偏移时,`aware - naive` 抛的是 **TypeError** 不是 ValueError;
    第一版只捕 ValueError ⇒ 那一下会穿出整个 snapshot_board,**当天快照全丢**。
    """
    if not kickoff_utc:
        return None
    try:
        ko = dt.datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
        if ko.tzinfo is None:
            ko = ko.replace(tzinfo=dt.UTC)
        return round((ko - now).total_seconds() / 3600.0, 3)
    except (ValueError, TypeError):
        return None


def _match_date(pred: dict) -> str | None:
    """比赛日期。

    🚨 端点下发的键是 **`date`**,不是 `match_date` —— 第一版读错了键,主路径
    是死代码、全靠 `kickoff_utc[:10]` 兜底,而测试夹具恰好喂了那个不存在的键,
    所以护栏守的是生产永远走不到的分支。两个键都试,再退到开球日。
    """
    for key in ("date", "match_date"):
        v = pred.get(key)
        if v:
            return str(v)[:10]
    ko = pred.get("kickoff_utc")
    return str(ko)[:10] if ko else None


def _legs_from_prediction(pred: dict, now: dt.datetime) -> list[dict]:
    """一条盘面记录 → 1X2 三条 + 每条让球线三条。

    让球线取 `_HC_LINES_ALWAYS`(−1/0/+1,竞彩实际只卖这三条)∪ 竞彩在卖那条,
    并用 `line_source` 标注 —— 见 `_HC_LINES_ALWAYS` 的注释。
    """
    rows: list[dict] = []
    md = _match_date(pred)
    base = {
        "match_date": md,
        "league": pred.get("league"),
        "home_team": pred.get("home_team"),
        "away_team": pred.get("away_team"),
        "kickoff_utc": pred.get("kickoff_utc"),
        "market_mode": 1 if pred.get("market_mode") else 0,
        "hours_to_ko": _hours_to_ko(pred.get("kickoff_utc"), now),
        "ou_line": pred.get("ou_line"),
        "psc_over": pred.get("psc_over25"),
        "psc_under": pred.get("psc_under25"),
        "jc_captured_at": pred.get("jc_captured_at"),
        "odds_update": pred.get("odds_update"),
    }
    if not (base["home_team"] and base["away_team"] and md):
        log.warning("身份不全,整场丢弃:%s vs %s @ %s",
                    pred.get("home_team"), pred.get("away_team"), md)
        return rows

    # ── 1X2 ──────────────────────────────────────────────────────────
    # ⭐ 两个族分开存。`onex_lo_*` 是 **p_*_market** 的下界(routes 里 _onex_lo(mkt)),
    #   标准模式下 p_*_1x2 是模型 P —— 把它俩配成一对是第一版的 blocker。
    pm = [pred.get("p_home_1x2"), pred.get("p_draw_1x2"), pred.get("p_away_1x2")]
    pk = [pred.get("p_home_market"), pred.get("p_draw_market"), pred.get("p_away_market")]
    lo = [pred.get("onex_lo_home"), pred.get("onex_lo_draw"), pred.get("onex_lo_away")]
    jc = [pred.get("jc_home"), pred.get("jc_draw"), pred.get("jc_away")]
    psc = [pred.get("psc_home"), pred.get("psc_draw"), pred.get("psc_away")]
    if any(x is not None for x in pm) or any(x is not None for x in pk):
        for i in range(3):
            rows.append({**base, "market": "had", "handicap_home": None,
                         "line_source": None, "leg": i,
                         "p_model": pm[i], "p_market": pk[i],
                         "p_lo": lo[i], "p_lo_of": "p_market",
                         "jc_sp": jc[i], "psc": psc[i],
                         "single_available": pred.get("jc_single_available")})

    # ── 让球 ─────────────────────────────────────────────────────────
    grid = {int(r["line"]): r for r in (pred.get("handicap_lines") or [])
            if isinstance(r, dict) and r.get("line") is not None}
    raw_line = pred.get("jc_hc_line")
    jc_line = int(raw_line) if raw_line is not None else None
    jc_hc = [pred.get("jc_hc_home"), pred.get("jc_hc_draw"), pred.get("jc_hc_away")]

    wanted = sorted(set(_HC_LINES_ALWAYS) | ({jc_line} if jc_line is not None else set()))
    if jc_line is not None and jc_line not in grid:
        # ⚠️ 静默丢三条腿是第一版的病(`if row:` 直接跳过)。响亮一次。
        log.warning("竞彩在卖 %+d 但网格里没有这条线 ⇒ 该线三条腿缺失:%s vs %s",
                    jc_line, base["home_team"], base["away_team"])
    for line in wanted:
        row = grid.get(line)
        if not row:
            continue
        is_jc = (line == jc_line)
        ps = [row.get("p_home"), row.get("p_draw"), row.get("p_away")]
        los = [row.get("p_home_lo"), row.get("p_draw_lo"), row.get("p_away_lo")]
        for i in range(3):
            rows.append({**base, "market": "hhad", "handicap_home": line,
                         "line_source": "jingcai" if is_jc else "model", "leg": i,
                         # 让球网格两模式一律 Pinnacle 反推 ⇒ 点估与下界同族
                         "p_model": ps[i], "p_market": None,
                         "p_lo": los[i], "p_lo_of": "p_model",
                         "jc_sp": (jc_hc[i] if is_jc else None),
                         "psc": None,      # 让球没有直接的 Pinnacle 原盘赔率
                         "single_available": (pred.get("jc_hc_single_available")
                                              if is_jc else None)})
    return rows


_COLS = (
    "provenance_id", "captured_at", "match_date", "league", "home_team", "away_team",
    "kickoff_utc", "market", "handicap_home", "line_source", "leg",
    "p_model", "p_market", "p_lo", "p_lo_of",
    "jc_sp", "psc", "psc_over", "psc_under", "ou_line",
    "jc_captured_at", "odds_update", "hours_to_ko", "market_mode", "single_available",
)


def snapshot_board(
    predictions: list[dict],
    db_path: str,
    *,
    fe_version: str | None = None,
    feed: dict[str, Any] | None = None,
    note: str | None = None,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """把一批盘面记录落成快照。返回 `{provenance_id, matches, legs, inserted}`。

    ⭐ **空盘面也要写 provenance 行** —— 「那天什么都没有」和「那天没跑」
    必须分得开。但**光有行不够**:上游挂掉时端点照样 200 + 空 predictions,
    所以 `feed` 里的 `fixtures_fetched` / `pending` 必须一起落库,
    否则「盘面空」和「喂料断」在库里仍然同形(审查用桩服务证实过)。

    `legs` = 尝试写入的行数,`inserted` = **真正落库**的行数(同秒重跑会被
    UNIQUE 挡掉)。两个都报 —— 只报前者会让「重跑」看起来像「有新数据」。
    """
    now = now or dt.datetime.now(dt.UTC)
    ts = now.isoformat(timespec="seconds")
    all_rows: list[dict] = []
    for p in predictions:
        all_rows.extend(_legs_from_prediction(p, now))

    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        # 别的进程在 WAL 下写同一个库;没有 busy_timeout 时锁竞争 >5s 就整次丢失,
        # 而「整次丢失」落地成的状态恰好就是「没跑过」—— 又一个假的「没有」。
        conn.execute("PRAGMA busy_timeout=30000")
        ensure_tables(conn)
        cur = conn.execute(
            "INSERT INTO snapshot_provenance (created_at, fe_version, git_sha,"
            " constants_json, constants_source, constants_mtime, feed_json, note)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (ts, fe_version, _git_sha(), json.dumps(live_constants(), sort_keys=True),
             "cli-process", _constants_mtime(),
             json.dumps(feed or {}, sort_keys=True), note))
        pid = int(cur.lastrowid or 0)
        before = conn.total_changes
        placeholders = ",".join("?" * len(_COLS))
        sql = (f"INSERT OR IGNORE INTO board_leg_snapshot ({','.join(_COLS)})"
               f" VALUES ({placeholders})")
        for r in all_rows:
            conn.execute(sql, tuple(
                pid if c == "provenance_id"
                else ts if c == "captured_at"
                else r.get(c)
                for c in _COLS))
        inserted = conn.total_changes - before
        conn.commit()
    finally:
        conn.close()
    return {"provenance_id": pid,
            "matches": len({(r["match_date"], r["home_team"], r["away_team"])
                            for r in all_rows}),
            "legs": len(all_rows),
            "inserted": inserted}
