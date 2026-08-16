"""🚨 `kickoff_utc` 三种字面 —— 守住**唯一两处**真跨格式等值配对的地方。

## 为什么有这个文件

`odds_snapshots.kickoff_utc` 同一时刻有三种写法:

| | 字面 | 产地 | 当前行数 |
|---|---|---|---|
| A | `2026-07-01T16:00:00Z` | `closing_odds.py:167`(Odds API `commence_time` 直抄) | 4,856 |
| B | `2026-06-13T12:00:00+00:00` | 其余 5 个生产者(API-Football) | 其余 |
| C | `2026-06-30 21:00:00+00` | `polymarket_gaps`(空格分隔) | 本表 0 |

⇒ **`a.kickoff_utc = b.kickoff_utc` 永不成立。** 实测(2026-08-14):
`closing × cup_market` 按 `(home_team, match_date)` join = **144,686 行**;
同一 join 加上 `a.kickoff_utc = b.kickoff_utc` = **0 行**。抹平 100%。

⭐ 但**全仓爆炸半径 = 0** —— 因为没有任何消费方拿它当 join 键。
安全来自**两次互相独立的运气**:
  ① 所有 pre-kickoff 闸用的是 `<` 而不是 `=`,而 A/B 共享前 19 位
     `YYYY-MM-DDTHH:MM:SS` ⇒ 字典序即时序(实测 28,405 行分歧 **0**);
  ② 唯一两处真做等值配对的脚本,**恰好**把截断落在那段不变区间里。

**第二条随时会被一次无辜的重构打掉,而打掉之后是静默的。** 本文件守它。

## ⛔ 为什么不用语法断言

「源码里必须出现 `[:16]`」这种会:
  · 把截断重构进 helper 的正当改动 ⇒ **假红**
  · 换成 `[:20]` 这种**已实测会归零**的写法 ⇒ 照样绿(串还在)
本仓已点名过这族(误伤 `cur.slice()` 那次):**假红比假绿更贵,老误报的护栏最后会被删掉。**
⇒ 这里全部是**行为断言**:塞夹具、跑真函数、数结果。

## 正负对照缺一不可

只断言「≥1 条别名」的话,一个**恒返回非空**的 bug 照样过。
所以每条都配一个负对照:两侧本来同名 ⇒ 必须 **0 条**。
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

#: 全库允许的三种字面。ELSE 兜底分支是关键 —— 没有它就分不出
#: 「没有第四种」和「我没去看」。
_FORMATS = ("A: …Z", "B: …+00:00", "C: 空格分隔 +00")


def _load(name: str):
    """按路径加载 scripts/ 下的脚本(它们不是包的一部分)。"""
    p = _ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, p)
    assert spec and spec.loader, p
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixture_db(tmp_path: Path, rows: list[tuple]) -> str:
    """最小 odds_snapshots 夹具。rows = (league, source, kickoff_utc, home, away)。"""
    db = tmp_path / "fx.db"
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE odds_snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, league TEXT, source TEXT,
        kickoff_utc TEXT, home_team TEXT, away_team TEXT, match_date TEXT)""")
    c.executemany(
        "INSERT INTO odds_snapshots(league,source,kickoff_utc,home_team,away_team,match_date)"
        " VALUES(?,?,?,?,?,?)",
        [(lg, s, k, h, a, (k or "")[:10]) for lg, s, k, h, a in rows])
    c.commit()
    c.close()
    return str(db)


# ── G1 · 跨格式配对(最重要) ──────────────────────────────────────────

def test_derive_pairs_across_Z_and_offset_literals(tmp_path: Path) -> None:
    """🚨 closing 写 `…Z`、gather 写 `…+00:00`,同一场必须**配得上**。

    这是 `derive_odds_name_aliases` 存在的全部理由 —— 它靠开球槽位把两个源的
    同一场对上,再从「恰好一侧不同名」推出别名。

    空包弹(已在 2026-08-14 实跑,此处以注释留证,勿删):
        `_slot` 退化成裸 `ko`  ⇒ 别名 **0 条**
        `_slot` 改成 `ko[:20]` ⇒ 别名 **0 条**(悬崖精确落在第 20 位)
    两种退化都**不报错**,输出与「两个源本来就同名」完全同形。
    """
    d = _load("derive_odds_name_aliases")
    db = _fixture_db(tmp_path, [
        # 同一场:closing 侧是 Z 字面且主队写法不同;客队两侧一致 ⇒ 恰好一侧劈开
        ("TEST_LG", "closing", "2026-07-01T16:00:00Z", "Leicester City", "Arsenal"),
        ("TEST_LG", "cup_market", "2026-07-01T16:00:00+00:00", "Leicester", "Arsenal"),
    ])
    aliases, conflicts, _pending, _one = d.derive(db)
    assert aliases, (
        "跨 Z↔+00:00 的同场没配上 ⇒ 槽位归一坏了。"
        "⚠️ 这不会报错,只会静默输出「别名 0 条」—— 和「两个源本来同名」同形。")
    assert aliases.get(("TEST_LG", "Leicester City"), (None,))[0] == "Leicester", aliases
    assert not conflicts, conflicts


def test_derive_negative_control_same_names_yield_nothing(tmp_path: Path) -> None:
    """⭐ 负对照:两侧本来就同名 ⇒ 必须 **0 条**。

    没有这条,一个「恒返回非空」的 bug 会让上面那条永远绿。
    """
    d = _load("derive_odds_name_aliases")
    db = _fixture_db(tmp_path, [
        ("TEST_LG", "closing", "2026-07-01T16:00:00Z", "Leicester", "Arsenal"),
        ("TEST_LG", "cup_market", "2026-07-01T16:00:00+00:00", "Leicester", "Arsenal"),
    ])
    aliases, _c, _p, _o = d.derive(db)
    assert not aliases, f"两侧同名却推出了别名 ⇒ 判据在无中生有:{aliases}"


def test_slot_key_is_stable_across_all_three_literals() -> None:
    """三种字面的同一时刻 ⇒ **同一个槽位键**。C 型(空格分隔)也要归一。

    ⚠️ C 型当前不在 `odds_snapshots` 里(只在 `polymarket_gaps`),
    但 `polymarket_match.py:334` 是它的产地,哪天并表就会进来。
    先归一,不等它咬。
    """
    d = _load("derive_odds_name_aliases")
    keys = {d._slot(x) for x in (
        "2026-07-01T16:00:00Z",
        "2026-07-01T16:00:00+00:00",
        "2026-07-01 16:00:00+00",
    )}
    assert keys == {"2026-07-01T16:00"}, f"三种字面没归到同一槽:{keys}"


def test_slot_key_still_separates_different_kickoffs() -> None:
    """负对照:不同开球时刻**不许**被归一化撞在一起(分钟精度)。"""
    d = _load("derive_odds_name_aliases")
    assert d._slot("2026-07-01T16:00:00Z") != d._slot("2026-07-01T16:30:00Z")
    assert d._slot("2026-07-01T16:00:00Z") != d._slot("2026-07-02T16:00:00Z")


# ── G3 · 无偏移哨兵(唯一会「吞掉能买的腿」的方向) ────────────────────

_DB = _ROOT / "data" / "v4_observation.db"


@pytest.mark.skipif(not _DB.exists(), reason="没有观测库 —— 本断言只在本地有意义")
def test_no_kickoff_value_lacks_a_timezone_offset() -> None:
    """🚨 第四种格式 `2026-08-14T16:30:00`(**无偏移**)= 唯一会吞腿的方向。

    JS `new Date()` 对它按**本地时区**解释:本机 TZ=Asia/Shanghai 时
    `2026-08-14T16:30:00` → **08:30Z**,早 8 小时 ⇒ 未开赛被判成已开赛
    ⇒ 前端 `_isJcBettable` **静默把这条腿从可投注列表里剔掉**。

    ⚠️ 它**不是 NaN** ⇒ `Number.isFinite` 挡不住(源码注释已说明它不承重)。
    基线:9 张带该列的表,无偏移值 **全部为 0**。这是**待防的下一个格式**,
    不是现存 bug —— 所以这条护栏天生绿,红了就是真的出事了。
    """
    c = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        tabs = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
            if any(x[1] == "kickoff_utc" for x in c.execute(f"PRAGMA table_info({r[0]})"))]
        assert tabs, "一张带 kickoff_utc 的表都没找到 ⇒ 本护栏是空洞的"
        bad = {}
        for t in tabs:
            n = c.execute(
                f"SELECT COUNT(*) FROM {t} WHERE kickoff_utc IS NOT NULL "
                "AND kickoff_utc <> '' AND kickoff_utc NOT LIKE '%Z' "
                "AND kickoff_utc NOT LIKE '%+%' AND kickoff_utc NOT LIKE '%-__:__'"
            ).fetchone()[0]
            if n:
                bad[t] = n
    finally:
        c.close()
    assert not bad, (
        f"这些表有**无时区偏移**的 kickoff_utc:{bad}。"
        f"JS 会按本地时区解释它 ⇒ 早 8 小时 ⇒ 未开赛的场被静默剔出可投注列表。"
        f"修法:去写入侧补偏移,⛔ 不要在消费方猜时区。")


@pytest.mark.skipif(not _DB.exists(), reason="没有观测库")
def test_kickoff_literal_shapes_stay_within_the_known_whitelist() -> None:
    """G4 · 形状白名单 + **兜底分支**。

    ⭐ 兜底(ELSE)是关键 —— 没有它,这条断言就分不出
    「没有第四种格式」和「我没去看」。同族:「零新增 ≠ 扫完了」。
    预期红频:~1 次/年(14 个月出了 3 种),每次都可行动。
    """
    c = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        rows = c.execute("""
            SELECT CASE
              WHEN kickoff_utc LIKE '%Z'      THEN 'A'
              WHEN kickoff_utc LIKE '%+00:00' THEN 'B'
              WHEN kickoff_utc LIKE '% %+00'  THEN 'C'
              ELSE 'OTHER' END AS shape, COUNT(*)
            FROM odds_snapshots WHERE kickoff_utc IS NOT NULL AND kickoff_utc <> ''
            GROUP BY shape""").fetchall()
    finally:
        c.close()
    seen = dict(rows)
    assert sum(seen.values()) > 0, "odds_snapshots 里一行 kickoff_utc 都没有 ⇒ 断言是空洞的"
    assert seen.get("OTHER", 0) == 0, (
        f"出现了白名单外的 kickoff_utc 字面(共 {seen.get('OTHER')} 行)。"
        f"已知三种:{_FORMATS}。先去查它长什么样,⛔ 不要直接把它加进白名单 —— "
        f"新格式可能正是「无偏移」那种会吞腿的。")


# ── G5 · pre-kickoff 闸的夹具(被迫的:它在生产数据上是 no-op) ────────

@pytest.mark.skipif(not _DB.exists(), reason="没有观测库")
def test_pre_kickoff_gate_is_currently_a_noop_and_can_only_be_guarded_by_fixtures() -> None:
    """🚨 四个文件称作「承重」的 `captured_at < kickoff_utc` 闸,**一行都没挡住**。

    实测(2026-08-14):`kickoff_utc` 非空 28,405 行里被排除 **0 行(0.00%)**;
    `_pinn_close` 的 base 与「整个把闸拿掉」的变体,861 条腿**逐条相同**。

    后果不是「它没用」,而是 —— **它无法自证**。
    哪天格式漂移让这个比较恒为真,production 的读数和现在**一模一样**(还是 0)。
    ⇒ 生产数据永远喂不到它 ⇒ 只能靠夹具守。

    本条断言的是**这个事实本身**:一旦它开始挡住行,说明数据形态变了,
    值得去看一眼(而不是继续假设它在保护什么)。
    """
    c = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        tot, blocked = c.execute("""
            SELECT COUNT(*), SUM(CASE WHEN NOT (captured_at < kickoff_utc) THEN 1 ELSE 0 END)
            FROM odds_snapshots WHERE kickoff_utc IS NOT NULL AND captured_at IS NOT NULL
        """).fetchone()
    finally:
        c.close()
    assert tot > 1000, f"样本太小({tot}),这条会变空洞"
    assert (blocked or 0) == 0, (
        f"pre-kickoff 闸开始挡住行了({blocked}/{tot})—— 这**不一定是坏事**,"
        f"但它此前一直是 no-op,形态变了值得看一眼:是真有盘中行进来了,"
        f"还是 kickoff_utc/captured_at 的字面漂了导致字典序失效?"
        f"⛔ 别直接改这个断言的期望值,先去数。")


def test_pre_kickoff_gate_actually_excludes_a_post_kickoff_row(tmp_path: Path) -> None:
    """G5 夹具:喂一条**混格式**的盘中行,断言字典序比较仍然把它排除。

    这是上一条(生产数据恒 0)的补集 —— 闸的**能力**只能在这里验证。
    `captured_at` 全库单一 `+00:00`,而 closing 行的 `kickoff_utc` 是 `Z`
    ⇒ 那道闸对 closing 行是**行内跨格式比较**,不是同格式。
    """
    db = tmp_path / "gate.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t(captured_at TEXT, kickoff_utc TEXT)")
    c.executemany("INSERT INTO t VALUES(?,?)", [
        ("2026-07-01T15:00:00+00:00", "2026-07-01T16:00:00Z"),        # 赛前 ⇒ 留
        ("2026-07-01T17:00:00+00:00", "2026-07-01T16:00:00Z"),        # 盘中 ⇒ 排除
        ("2026-07-01T15:00:00+00:00", "2026-07-01T16:00:00+00:00"),   # 同格式赛前 ⇒ 留
        ("2026-07-01T17:00:00+00:00", "2026-07-01T16:00:00+00:00"),   # 同格式盘中 ⇒ 排除
    ])
    kept = c.execute(
        "SELECT COUNT(*) FROM t WHERE kickoff_utc IS NULL OR captured_at < kickoff_utc"
    ).fetchone()[0]
    c.close()
    assert kept == 2, (
        f"混格式下 pre-kickoff 闸留下了 {kept} 行,应为 2。"
        f"字典序失效了 —— 检查两侧字面的前 19 位布局是否还相同。")


# ── 写入侧归一(2026-08-16 上线,共享 sink) ──────────────────────────

def test_sink_normalises_all_three_literals_to_one_canonical_form() -> None:
    """三种字面 + 非 UTC 偏移 → **单一正典**;幂等。"""
    from nutmeg.v4.observation.odds_snapshots import _norm_kickoff as N

    assert N("2026-07-01T16:00:00Z") == "2026-07-01T16:00:00+00:00"        # A
    assert N("2026-06-13T12:00:00+00:00") == "2026-06-13T12:00:00+00:00"   # B(幂等)
    assert N("2026-06-30 21:00:00+00") == "2026-06-30T21:00:00+00:00"      # C
    assert N("2026-07-01T16:00:00+08:00") == "2026-07-01T08:00:00+00:00"   # 换算
    assert N(N("2026-07-01T16:00:00Z")) == N("2026-07-01T16:00:00Z")       # 幂等


def test_sink_never_guesses_a_timezone() -> None:
    """⛔ 无偏移 / 看不懂 ⇒ **原样返回**,绝不编一个看起来正常的时刻。

    🚨 无偏移是**唯一会吞腿**的形态(JS 按本地时区解释 ⇒ 早 8 小时 ⇒
    未开赛被判成已开赛 ⇒ 静默剔出可投注列表)。
    正确处理是**让它保持怪样子**,由 `test_no_kickoff_value_lacks_a_timezone_offset`
    喊出来 —— 而不是在 sink 里补一个我们没有根据的 `+00:00`。
    ⭐ 同 `canonical_team` 的 fail-open:缺归一只是难看,**猜一个是造假数据**。
    """
    from nutmeg.v4.observation.odds_snapshots import _norm_kickoff as N

    assert N("2026-08-14T16:30:00") == "2026-08-14T16:30:00"   # 无偏移 → 原样
    assert N("乱七八糟") == "乱七八糟"                             # 看不懂 → 原样
    assert N(None) is None and N("") is None


@pytest.mark.skipif(not _DB.exists(), reason="没有观测库")
def test_rows_written_after_the_sink_fix_use_the_canonical_literal() -> None:
    """G2 · **新行**必须是正典字面。⚠️ 必须**时间窗口化**。

    🚨 不带窗口的话:库里有 4,856 行历史 `…Z`,而**回填 odds_snapshots 是红线**
    ⇒ 这条会**天生红且永远红** ⇒ 按「老误报的护栏最后会被删掉」,它必然被删。

    ⇒ 只看部署时刻之后写入的行。部署当天窗口为空 ⇒ **天生绿**,
      一天内被真实 cron 填满(closing 实测 12–774 行/日)。
    """
    import sqlite3

    c = sqlite3.connect(f"file:{_DB}?mode=ro", uri=True)
    try:
        bad = c.execute(
            "SELECT COUNT(*) FROM odds_snapshots "
            "WHERE captured_at > ? AND kickoff_utc IS NOT NULL AND kickoff_utc <> '' "
            "AND kickoff_utc NOT LIKE '%+00:00'",
            (_SINK_FIX_DEPLOYED_AT,)).fetchone()[0]
    finally:
        c.close()
    assert bad == 0, (
        f"{_SINK_FIX_DEPLOYED_AT} 之后写入的行里有 {bad} 行不是正典字面。"
        f"写入侧归一没生效 —— 查 `odds_snapshots._norm_kickoff` 是否还挂在 sink 上,"
        f"以及服务/cron 是否重启过(词典与 sink 都在进程启动时载入)。")


#: 写入侧归一上线时刻(UTC)。⚠️ 之前的行**不回填**(共享表回填是红线),
#: 所以上面那条断言只对之后的行生效。
_SINK_FIX_DEPLOYED_AT = "2026-08-16T02:50:00+00:00"
