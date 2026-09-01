"""Closing-line Pinnacle capture — writes fetch_pinnacle_lookup → odds_snapshots,
applies the Odds-API→canonical alias, dedups on re-run, and (2026-07-01 fix) skips
already-kicked-off matches so LIVE odds never get recorded as a "close"."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest


def _fake_lookup(sport_key, refresh=True):
    return {
        ("france", "sweden", "2026-06-30"): {
            "home_team": "France", "away_team": "Sweden",
            "psc_home": 1.29, "psc_draw": 6.1, "psc_away": 12.0,
            "ou_line": 3.5, "psc_over": 2.05, "psc_under": 1.86,
            "last_update": "2026-06-30T18:43:51Z",
            "commence_time": "2026-06-30T19:00:00Z"},
        ("england", "drcongo", "2026-07-01"): {
            "home_team": "England", "away_team": "DR Congo",  # ← alias target
            "psc_home": 1.29, "psc_draw": 5.36, "psc_away": 13.11,
            "ou_line": 2.5, "psc_over": 2.06, "psc_under": 1.84,
            "last_update": "2026-06-30T18:43:51Z",
            "commence_time": "2026-07-01T19:00:00Z"},
    }


# A fixed "now" BEFORE both fixture kickoffs → both count as pre-match.
_BEFORE_KO = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_capture_writes_aliases_and_dedups(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _fake_lookup)
    db = tmp_path / "obs.db"

    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=_BEFORE_KO)
    assert r == {"WC": 2}

    rows = {(x[0], x[1], x[2]) for x in sqlite3.connect(db).execute(
        "SELECT home_team, away_team, source FROM odds_snapshots")}
    assert ("France", "Sweden", "closing") in rows
    assert ("England", "Congo DR", "closing") in rows  # 'DR Congo' → 'Congo DR'

    # the Pinnacle line + bookmaker timestamp + kickoff landed
    fr = sqlite3.connect(db).execute(
        "SELECT psc_home, ou_line, odds_update, kickoff_utc FROM odds_snapshots "
        "WHERE home_team='France'").fetchone()
    # ⚠️ 2026-08-16:`kickoff_utc` 现在由 sink 归一到正典字面 `…+00:00`。
    # 输入仍是 Odds API 原样的 `…Z`(第 17 行),**归一发生在写入侧** ——
    # 这条断言正是那条归一的端到端证据(输入 Z、落库 +00:00)。
    # 📌 `odds_update`(第 3 位)**不归一**:它是「这条线什么时候更新的」,
    #    不参与任何跨源 join,没有被两套字面咬到的路径。只归一承重的那一列。
    assert fr == (1.29, 3.5, "2026-06-30T18:43:51Z", "2026-06-30T19:00:00+00:00")

    # re-run with the SAME line = append-only dedup, no new rows
    assert closing_odds.capture_closing_pinnacle(db, ["WC"], now=_BEFORE_KO) == {"WC": 0}


def test_skips_already_started_live_matches(tmp_path, monkeypatch):
    """The core fix: a match that has kicked off serves LIVE odds — it must be
    skipped, not recorded as a close. Only the still-upcoming match is written."""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _fake_lookup)
    db = tmp_path / "obs.db"

    # now is AFTER France-Sweden (19:00 on 06-30) but BEFORE England (19:00 on 07-01)
    between = datetime(2026, 6, 30, 20, 0, tzinfo=UTC)
    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=between)
    assert r == {"WC": 1}

    teams = {(x[0], x[1]) for x in sqlite3.connect(db).execute(
        "SELECT home_team, away_team FROM odds_snapshots")}
    assert ("England", "Congo DR") in teams        # upcoming → kept
    assert ("France", "Sweden") not in teams       # already kicked off → skipped


def test_missing_kickoff_is_skipped(tmp_path, monkeypatch):
    """No parseable commence_time → can't prove pre-match → skip (conservative)."""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    def _no_ko(sport_key, refresh=True):
        return {("x", "y", "2026-07-05"): {
            "home_team": "X", "away_team": "Y",
            "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.5,
            "ou_line": 2.5, "psc_over": 2.0, "psc_under": 1.85,
            "last_update": "2026-07-05T10:00:00Z"}}  # no commence_time

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _no_ko)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 0}


def test_fetch_failure_is_failsoft(tmp_path, monkeypatch):
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    def _boom(sport_key, refresh=True):
        raise RuntimeError("odds api down")

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _boom)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 0}


def test_poisoned_none_lookup_entry_is_skipped(tmp_path, monkeypatch):
    """体检 2026-07-03 — fetch_pinnacle_lookup poisons ambiguous club-core keys to
    None (c5e805f). This consumer loop is OUTSIDE the per-sport try: an unguarded
    None would AttributeError and kill the WHOLE capture round. The good entry
    must still be captured."""
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    future = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    date = future[:10]

    def _mixed(sport_key, refresh=True):
        return {
            ("poisoned", "core", date): None,     # ambiguous club-core key
            ("a", "b", date): {
                "home_team": "A", "away_team": "B",
                "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.5,
                "ou_line": 2.5, "psc_over": 2.0, "psc_under": 1.85,
                "last_update": future, "commence_time": future},
        }

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _mixed)
    assert closing_odds.capture_closing_pinnacle(tmp_path / "x.db", ["WC"]) == {"WC": 1}


class TestResolveAutoSports:
    """体检 Wave2 — `--sports auto`: KO-window-driven sport resolution.
    Hardcoded `--sports WC` would kill the closing chain at WC end (~7/19)."""

    def _fx(self, minutes_from_now, league_id, now):
        from datetime import timedelta
        return {"fixture": {"date": (now + timedelta(minutes=minutes_from_now)).isoformat()},
                "league": {"id": league_id}}

    def test_in_window_league_with_sport_key_resolves(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(30, 292, now)]  # K-League KO in 30min
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == ["KOR_K_LEAGUE_1"]

    def test_outside_window_and_kicked_off_excluded(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(120, 292, now),   # beyond 75min lookahead
                    self._fx(-10, 292, now)]   # already kicked off
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == []

    def test_league_without_sport_key_filtered(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports
        now = datetime.now(UTC)

        def fake(d):
            return [self._fx(30, 99, now)]  # JPN_J2: AF id, no sport key (DNK got a key 2026-07-12; Odds API has no J2)
        assert resolve_auto_sports(now=now, fetch_fixtures=fake) == []

    def test_af_outage_returns_empty_not_blind_fetch(self):
        from datetime import UTC, datetime

        from nutmeg.v4.observation.closing_odds import resolve_auto_sports

        def boom(d):
            raise RuntimeError("AF down")
        assert resolve_auto_sports(now=datetime.now(UTC), fetch_fixtures=boom) == []


# ── 竞态:now 必须逐行重取,且必须就是落库的 captured_at(2026-09-01) ──────


@pytest.fixture(autouse=True)
def _no_live_book_fetch(monkeypatch):
    """💸 全模块闸:掐掉 `capture_books_for_sport` 那一路的**真实 Odds-API 请求**。

    🚨 `refresh=False` **不等于「只读缓存」**(`book_snapshots` 模块头自己写着):
    `odds_api._request` 的判据是 `cf.exists() and not refresh and fresh_enough`,
    缓存文件不存在时它 fall through 到 live fetch。本文件的测试都把
    `fetch_pinnacle_lookup` monkeypatch 掉了 ⇒ **同参数的缓存文件从来不会被写出**
    ⇒ 紧接着的书商快照必然缓存未命中。当前 worktree/CI 里没有 key,`_client()`
    先抛 `OddsApiError` 被 fail-soft 吞掉 ⇒ 看起来无害;但在 owner 那台
    **source 过 .env** 的机器上跑同一批测试,每个用例都是一次真消费。
    ⚠️ 该调用是 2026-09-01 才接进 closing 路径的,此前本文件没有这个口子。

    ⛔ 打在 `nutmeg.v4.observation.book_snapshots` 上,**不是** `closing_odds` 上 ——
    那边是**函数内 import**,打模块属性是 no-op(第一版就踩了:两行都被写下来,
    而失败信息长得像「闸没生效」)。
    """
    from nutmeg.v4.observation import book_snapshots
    monkeypatch.setattr(book_snapshots, "capture_books_for_sport", lambda *a, **k: 0)


class _FakeDatetimeModule:
    """`odds_snapshots` 里 `import datetime as dt` 的替身:`dt.datetime` 换成假时钟,
    其余(`dt.UTC` …)透传。

    🚨 不装它,`test_capture_never_writes_a_row_violating_the_pre_kickoff_invariant`
    **在夹具里没有功效**:sink 用真时钟戳 `captured_at`(今天),而夹具的开球点在
    未来几天 ⇒ `captured_at < kickoff_utc` 恒成立,连老代码都绿。空包弹实测确认过。
    ⚠️ 这条 setattr 咬死了 `odds_snapshots` 的模块内名字 `dt` —— 它被改名时
    `monkeypatch.setattr` 会**直接报错**(raising 默认 True),不会静默失效。
    """

    def __init__(self, clock):
        self.datetime = clock

    def __getattr__(self, name):
        import datetime as _dt
        return getattr(_dt, name)


class _TickingClock:
    """`datetime` 的替身:`now()` **先返回当前值再前进**,其余属性透传真 datetime。

    ⚠️ 两个都是刻意的:
    ① **后置前进** —— 这样第一次 `now()` 拿到的就是 `start`,才能忠实模拟老代码
       「入口取一次、零成本」的语义。若改成前置前进,老代码的入口读数也会被推到
       开球点之后 ⇒ 空包弹里老代码也「挡住了」,本条就证明不了任何事。
    ② **透传 `fromisoformat`** —— `closing_odds._parse_iso` 用的是**同一个模块级
       名字** `datetime`。只 stub `now` 会让解析整体崩掉,而 fail-soft 会把它
       咽下去变成「写了 0 行」,和「闸挡住了」完全同形。
    """

    def __init__(self, start, step_seconds: int):
        import datetime as _dt
        self._t = start
        self._step = _dt.timedelta(seconds=step_seconds)
        self.ticks = 0

    def now(self, tz=None):
        self.ticks += 1
        cur = self._t
        self._t = self._t + self._step
        return cur

    def __getattr__(self, name):
        import datetime as _dt
        return getattr(_dt.datetime, name)


def _lookup(*entries):
    """entries = (home, away, commence_time) …  → fetch_pinnacle_lookup 的替身。"""
    def _f(sport_key, refresh=True):
        return {
            (h.lower(), a.lower(), ko[:10]): {
                "home_team": h, "away_team": a,
                "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.5,
                "ou_line": 2.5, "psc_over": 2.0, "psc_under": 1.85,
                "last_update": ko, "commence_time": ko}
            for h, a, ko in entries}
    return _f


def test_gate_rereads_the_clock_so_a_kickoff_crossed_mid_round_is_skipped(
        tmp_path, monkeypatch):
    """🚨 回归:`now` 只在函数入口取一次 ⇒ 一轮里跨过开球点的场次被写成「收盘」。

    实测(2026-08-30 生产):`captured_at` 比 `kickoff_utc` 晚 1s / 2s 的 2 行
    正是这条路径 —— 入口 now=15:29:5x,写库 15:30:01 / 15:30:02。
    窗口不是抖动:入口 `now` 到写库之间隔着每 sport 一次 Odds-API HTTP + 一次
    书商快照 + 逐行写库,实测一轮**写入→写入**跨度随联赛数线性增长
    (1 个联赛 p50 0s → 11 个联赛 p50 8s / max 9s),而入口 now 还在第一次 HTTP
    之前 ⇒ 真实窗口比 9s 更宽。30 分钟 cron 又恰好漂到 HH:29:5x 起跑,
    开球集中在 HH:30:00 —— **每一轮都在开球点前几秒起跑**,这是最坏相位。

    ⭐ **人口非平凡断言**(否则本条空洞为真):`ko_race` 在**进入函数那一刻仍未
    开球** ⇒ 老代码必然把它写下来(空包弹实跑:老口径 3 行,本口径 2 行)。
    它现在被挡掉,只能是因为闸重取了时钟。
    """
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    start = dt.datetime(2026, 9, 5, 14, 59, 55, tzinfo=dt.UTC)
    ko_race = "2026-09-05T14:59:59Z"      # 入口 +4s 开球 —— 轮到它时已经开了
    ko_far = "2026-09-05T16:00:00Z"       # 一小时后,两种口径都该写
    assert closing_odds._parse_iso(ko_race) > start, (
        "夹具坏了:ko_race 在入口时刻就已开球 ⇒ 老代码也会挡掉它,本条证明不了任何事")

    # 每行前进 6s:第一跳(A)拿到 start,第二跳(RACE)拿到 start+6 > ko_race。
    # 6s 在实测范围内 —— 11 个联赛一轮的写入跨度 max 9s。
    clock = _TickingClock(start, step_seconds=6)
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _lookup(
        ("A", "A2", ko_far), ("RACE", "VICTIM", ko_race), ("C", "C2", ko_far)))
    monkeypatch.setattr(closing_odds, "datetime", clock)
    db = tmp_path / "race.db"
    r = closing_odds.capture_closing_pinnacle(db, ["WC"])

    # ⚠️ 先断言**结果**再断言防空洞的 ticks —— 反过来的话,老口径会先在 ticks 上
    #    炸掉,失败信息只说「时钟没重取」而不说「越界的那行被写下来了」。
    assert r == {"WC": 2}, f"跨过开球点的那场没被挡掉:{r}"
    teams = {x[0] for x in sqlite3.connect(db).execute(
        "SELECT home_team FROM odds_snapshots")}
    assert teams == {"A", "C"}, f"写下来的不是「仍未开球」的那两场:{teams}"
    assert clock.ticks >= 3, f"时钟没有被逐行重取(只走了 {clock.ticks} 步)⇒ 本条空洞"


def test_captured_at_is_the_instant_the_gate_judged_not_the_write_instant(
        tmp_path, monkeypatch):
    """⭐ 闸判的时刻 = 落库的 `captured_at`,**同一个值**。

    只重取 `now` 而让 sink 在写库那一刻自己再取一次,闸与戳之间还剩一段 δ
    (`record_row_snapshot` 自带 `busy_timeout=3000` ⇒ 最坏 3s),`captured_at`
    照样能翻到开球点之后 —— 那就得再加一道 M≥3s 的安全边界,而边界**只砍最贵的
    那批线**(实测 lead<5s 的 6 场、lead<30s 的 19 场,被挡后 close 全部退化到
    约 30 分钟前的上一 tick)。传入判过闸的那个时刻是零成本的根除。
    """
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    frozen = dt.datetime(2026, 9, 5, 14, 30, 0, tzinfo=dt.UTC)
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _lookup(
        ("A", "A2", "2026-09-05T15:00:00Z"), ("B", "B2", "2026-09-05T16:00:00Z")))
    db = tmp_path / "stamp.db"
    assert closing_odds.capture_closing_pinnacle(db, ["WC"], now=frozen) == {"WC": 2}
    caps = {x[0] for x in sqlite3.connect(db).execute(
        "SELECT captured_at FROM odds_snapshots")}
    assert caps == {"2026-09-05T14:30:00+00:00"}, (
        f"captured_at 不是闸判的那一刻:{caps} —— sink 又自己取了一次 now?")


def test_capture_never_writes_a_row_violating_the_pre_kickoff_invariant(
        tmp_path, monkeypatch):
    """🚨 **不变量**:本采集路径写下的每一行都满足 `captured_at < kickoff_utc`。

    这是那条生产哨兵
    (`test_kickoff_slot_normalisation::test_pre_kickoff_gate_…`)在夹具侧的补集:
    哨兵只能事后数库里的行(而库里那 2 行**不会被删** —— 见它的注释),
    闸的**能力**只能在这里验证。把开球点密集铺在时钟前进的路径上,
    让每一轮都有场次在环里跨过开球点。

    ⚠️ 断言写成**字面比较**(和哨兵、和 4 个消费方的 SQL 闸同口径),
    不是 datetime 比较 —— 承重的是字面,不是我们解析后的语义。
    """
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds, odds_snapshots

    db = tmp_path / "inv.db"
    for off in range(1, 12):
        start = dt.datetime(2026, 9, 5, 14, 59, 50, tzinfo=dt.UTC)
        ko = (start + dt.timedelta(seconds=off)).strftime("%Y-%m-%dT%H:%M:%SZ")
        far = (start + dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _lookup(
            (f"H{off}", f"A{off}", ko), (f"F{off}", f"G{off}", far)))
        clock = _TickingClock(start, step_seconds=off)
        monkeypatch.setattr(closing_odds, "datetime", clock)
        monkeypatch.setattr(odds_snapshots, "dt", _FakeDatetimeModule(clock))
        closing_odds.capture_closing_pinnacle(db, [f"L{off}"])

    c = sqlite3.connect(db)
    tot, bad = c.execute(
        "SELECT COUNT(*), SUM(CASE WHEN NOT (captured_at < kickoff_utc) THEN 1 ELSE 0 END)"
        " FROM odds_snapshots WHERE kickoff_utc IS NOT NULL").fetchone()
    kept_near = c.execute(
        "SELECT COUNT(*) FROM odds_snapshots WHERE home_team LIKE 'H%'").fetchone()[0]
    c.close()
    assert tot >= 11, f"人口太小({tot} 行)⇒ 断言空洞;夹具没写进去?"
    assert kept_near > 0, (
        "一条**临开球**的行都没留下 ⇒ 闸把整批都挡了,`bad == 0` 是空洞为真。"
        "本条要证的是「挡掉越界的、留下合法的」,不是「什么都别写」。")
    assert (bad or 0) == 0, f"{bad}/{tot} 行违反 captured_at < kickoff_utc"


# ── 闸的**边界**(2026-09-02 补:空包弹发现这两发变异全绿)────────────────

def test_the_gate_is_closed_at_the_exact_kickoff_second(tmp_path, monkeypatch):
    """🚨 `observed == kickoff` 必须**挡掉**,不是放行。

    空包弹实测:把判据从 `observed >= kickoff` 放宽一档改成 `>`,**全套照绿**
    —— 也就是说「恰好等于开球点」这个边界从来没有被测过。
    而它一放行,落库的就是 `captured_at == kickoff_utc`,直接违反
    `captured_at < kickoff_utc` 这条被四个文件称作承重的不变量;
    生产哨兵 `test_pre_kickoff_gate_...` 的判据 `NOT (captured_at < kickoff_utc)`
    会把它算成越界行 —— 也就是我们刚花了一整轮去根除的那个形状。

    ⭐ 人口非平凡:`ko_far` 那场必须被写下来,否则「一行都没有」也能让下面绿。
    """
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    ko = "2026-09-05T15:30:00Z"
    exact = dt.datetime(2026, 9, 5, 15, 30, 0, tzinfo=dt.UTC)   # 与开球点**逐秒相等**
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _lookup(
        ("EXACT", "VICTIM", ko), ("FAR", "FAR2", "2026-09-05T18:00:00Z")))
    db = tmp_path / "exact.db"
    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=exact)

    assert r == {"WC": 1}, f"恰好等于开球点的那场没被挡掉:{r}"
    teams = {x[0] for x in sqlite3.connect(db).execute(
        "SELECT home_team FROM odds_snapshots")}
    assert teams == {"FAR"}, f"写下来的不对:{teams} —— 应该只有 FAR"


def test_a_subsecond_kickoff_inside_the_same_second_is_skipped(tmp_path, monkeypatch):
    """🚨 亚秒开球点:`15:30:00.5` 而观测在 `15:30:00.2` ⇒ 仍然**挡掉**。

    空包弹实测:去掉判据里**开球点那一侧**的截秒(`kickoff.replace(microsecond=0)`),
    全套照绿 —— 那一侧的截秒从来没有被测过。

    ⭐ 为什么必须挡:落库的 `captured_at` 是**截到秒**的(`timespec="seconds"`),
    所以同一秒内我们**没有能力证明** `captured_at < kickoff_utc`。
    闸的全部设计意图是「由构造成立、零安全边界」,而由构造成立的前提就是
    两侧同粒度比较。⚠️ 代价是会丢掉最多 1 秒的合法线 —— 作者用实测取舍过:
    真正值钱的是 lead<30s 那 19 场(1.57%),不是 lead<1s。

    ⛔ 别把这条改成「允许写入」来省那一秒 —— 那等于把安全边界从 0 变成
    「取决于 API 返回的时间戳精度」,而那个精度不由我们控制。
    """
    import datetime as dt

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation import closing_odds

    ko_sub = "2026-09-05T15:30:00.500000+00:00"          # 亚秒精度
    observed = dt.datetime(2026, 9, 5, 15, 30, 0, 200000, tzinfo=dt.UTC)  # 同一秒内
    assert closing_odds._parse_iso(ko_sub) > observed, (
        "夹具坏了:observed 必须**真的**早于开球点,否则本条测的不是截秒而是常识")
    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _lookup(
        ("SUB", "VICTIM", ko_sub), ("FAR", "FAR2", "2026-09-05T18:00:00Z")))
    db = tmp_path / "sub.db"
    r = closing_odds.capture_closing_pinnacle(db, ["WC"], now=observed)

    assert r == {"WC": 1}, (
        f"亚秒开球点、同一秒内观测的那场被写下来了:{r}\n"
        f"⇒ 落库 captured_at 截到秒 = 15:30:00,而 kickoff 是 15:30:00.5,"
        f"我们无法在秒粒度上证明 captured_at < kickoff_utc")
    teams = {x[0] for x in sqlite3.connect(db).execute(
        "SELECT home_team FROM odds_snapshots")}
    assert teams == {"FAR"}, f"写下来的不对:{teams}"
