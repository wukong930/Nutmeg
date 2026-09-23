"""Closing-line Pinnacle capture — snapshot the Odds-API Pinnacle lookup straight
into ``odds_snapshots(source='closing')``, bypassing the cup-market gather (whose
fixture-matching drops most matches → it writes ~nothing right now). Run frequently
(cron, every ~30 min) so EVERY match gets a Pinnacle line captured close to its own
kickoff = the true CLOSE — the correct anchor for CLV + the de-noised soft-water
comparison (③ found the gather-side anchor was median ~5h stale). Forward-only,
append-only (record_row_snapshot dedups on line-state), fail-soft.

Team names: ``fetch_pinnacle_lookup`` returns Odds-API display names. Most already
match the jingcai_vote / odds_snapshots canonical (France=France, Ivory Coast=Ivory
Coast …); only a few national-team word-order/synonym diffs do not. We apply a SMALL
measured alias (``_ODDS_API_ALIAS``) aligned to the JOIN TARGET's naming — extend it
when a new mismatch surfaces (see 记忆 cross-source-team-name-mismatch). The heavier
`team_canonical` fuzzy pool is deliberately NOT used here: it needs multi-step pool
construction and a closing capture must stay light + reliable.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

#: `--sports auto` 的开球前瞻窗(分钟)。**cron 与哨兵共用这一个定义**:哨兵据它推
#: 「最后一次捕获之后,哪些开球是 cron 本该再跑一轮去抓的」—— 两边各写一个 75,
#: 改了一边,哨兵就会在错的窗口上判「漏了」或「空窗」。
AUTO_LOOKAHEAD_MINUTES = 75

#: cron 每跑完一轮 `--sports auto` 写一次,与观测库同目录(同 `.data_freshness_heartbeat`)。
#: 空窗期(国际比赛日:SPORT_KEYS 联赛全停)cron **本来就不该写库**,这是它活着的唯一证据。
#: ⛔ 别「简化」成读 launchd 日志:`rotate_logs.sh` 原地重写 `logs/launchd/*.log`(mtime 跟着
#:    变新),plist 命令尾巴是 `|| true`(launchd 的 last exit code 恒为 0)—— 两个都会替死 cron 作证。
HEARTBEAT_FILENAME = ".closing_odds_heartbeat"

#: AF 状态码:这两种 = 那场**没踢**(推迟 / 取消),没有收盘线可抓。
#: ⚠️ AF 写的是 `PST` 不是 `POSTP`(2026-09-23 扫本地 fixture 缓存 62,206 条:
#:    PST 327 / CANC 438 / POSTP **0**)。
_NOT_PLAYED = frozenset({"PST", "CANC"})


def _parse_iso(s: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (accepting a trailing 'Z') to an aware UTC
    datetime, or None if absent/malformed."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

# Odds-API team name → our canonical (the name jingcai_vote / odds_snapshots use, =
# API-Football EN via zh_to_canonical). Only the measured mismatches; identity
# otherwise. Extend as new ones appear in the closing run's "unmatched" log.
_ODDS_API_ALIAS: dict[str, str] = {
    "DR Congo": "Congo DR",
    # 体检 B3 (2026-07-01, measured): every other source (竞彩, cup_market,
    # predict_log, jingcai_sp) + the elo table spell it "Cape Verde Islands"; only
    # the Odds-API closing capture wrote the outlier "Cape Verde", so the freshest
    # anchor silently un-joined jingcai_vote (Argentina v Cape Verde Islands).
    "Cape Verde": "Cape Verde Islands",
}


def _canon(name: str | None) -> str | None:
    if not name:
        return None
    return _ODDS_API_ALIAS.get(name.strip(), name.strip())


def _kickoff_and_league(fx) -> tuple[datetime, object] | None:
    """AF fixture → ``(开球时刻, league id)``;缺任一项或形状不对 → None。"""
    try:
        ko = _parse_iso((fx.get("fixture") or {}).get("date"))
        lg_id = (fx.get("league") or {}).get("id")
    except AttributeError:
        return None
    return None if ko is None or lg_id is None else (ko, lg_id)


def _status_short(fx) -> str | None:
    try:
        return ((fx.get("fixture") or {}).get("status") or {}).get("short")
    except AttributeError:
        return None


def _sport_key_kickoffs(fixtures, id_to_canonical: dict):
    """AF fixture 列表 → ``(开球时刻, canonical, fixture)``,只留 SPORT_KEYS 联赛。

    ⭐ 「哪些开球归收盘锚管」的**唯一定义**:cron(`resolve_auto_sports`)据它决定拉
    哪些 sport,哨兵(`scan_uncaptured_kickoffs`)据它判「那几天是不是真没东西可抓」。
    两边各写一份筛选,迟早一边多认一个联赛而另一边不认 —— 哨兵就会在 cron 根本
    不管的联赛上报「漏了」,或者反过来把真漏掉的判成空窗。"""
    from nutmeg.v4.data.sources import odds_api

    for fx in fixtures:
        kl = _kickoff_and_league(fx)
        if kl is None:
            continue
        try:
            canonical = id_to_canonical.get(kl[1])
        except TypeError:          # 不可哈希的脏 id
            continue
        if canonical and canonical in odds_api.SPORT_KEYS:
            yield kl[0], canonical, fx


def resolve_auto_sports(
    *,
    lookahead_minutes: int = AUTO_LOOKAHEAD_MINUTES,
    now: datetime | None = None,
    fetch_fixtures=None,
) -> list[str]:
    """体检 Wave2 — kickoff-window sport resolution for ``--sports auto``.

    The plist used to hardcode ``--sports WC`` → the whole closing chain dies
    when the WC ends (~7/19) and every in-season league goes unanchored (the
    「注册表即开关」class). Auto mode derives, from the cached API-Football
    fixture schedule (1 cheap/cached AF read, NOT Odds-API credits), the set of
    SPORT_KEYS leagues with a kickoff inside ``(now, now+lookahead]`` — i.e.
    fetch a sport's Odds-API board ONLY when one of its matches is about to
    start, which is exactly when the capture equals the true close. A 30-min
    cron + 75-min lookahead ⇒ 1–2 pre-KO snapshots per match; quiet hours cost
    ZERO Odds-API credits (vs 48×/day flat for one sport before).

    Fail-soft: an AF outage returns [] (0 credits burned blind); a sustained
    stall is caught by the data_freshness ``odds_snapshots[closing]`` sentinel
    (Wave 1), not silence. ``fetch_fixtures`` is injectable for tests."""
    from nutmeg.v4.data.sources.api_football import (
        API_FOOTBALL_LEAGUE_IDS,
        fetch_fixtures_for_date,
    )

    now = now or datetime.now(UTC)
    fetch = fetch_fixtures or fetch_fixtures_for_date
    horizon = now + timedelta(minutes=lookahead_minutes)
    id_to_canonical = {v: k for k, v in API_FOOTBALL_LEAGUE_IDS.items()}
    keys: set[str] = set()
    # Today + tomorrow (UTC) covers a lookahead crossing midnight.
    for d in {now.date(), horizon.date()}:
        try:
            fixtures = fetch(d) or []
        except Exception:  # noqa: BLE001 — fail-soft; sentinel catches sustained stalls
            log.warning("auto-sports: fixture fetch failed for %s", d, exc_info=True)
            continue
        for ko, canonical, _fx in _sport_key_kickoffs(fixtures, id_to_canonical):
            if now < ko <= horizon:
                keys.add(canonical)
    return sorted(keys)


@dataclass
class KickoffScan:
    """`scan_uncaptured_kickoffs` 的结果。三态要分开:有开球 / 证明没有 / 证明不了。"""
    #: 窗口内的 SPORT_KEYS 开球 (时刻, 联赛),升序。扫到**第一个有开球的日子**就停 ——
    #: 结论已定(不是空窗),不为了凑个总数去翻几十天的缓存。
    kickoffs: list[tuple[datetime, str]] = field(default_factory=list)
    #: 读到了、且认得出比赛的赛程缓存日。
    days_read: list[date] = field(default_factory=list)
    #: 缺 / 读坏 / 空列表 / 一场都认不出 —— 这些日子**证明不了**「那天没球」。
    unknown_days: list[date] = field(default_factory=list)
    #: 读到的 fixture 总数(全部联赛)。让「0 场 SPORT_KEYS」可核:是翻了几百场
    #: 一场都不归我们管,还是压根没翻到东西。
    fixtures_seen: int = 0

    @property
    def proves_nothing_to_capture(self) -> bool:
        return not self.kickoffs and not self.unknown_days and bool(self.days_read)


def scan_uncaptured_kickoffs(
    start: datetime, end: datetime, *, cache_dir: str | Path,
) -> KickoffScan:
    """``(start, end]`` 内 SPORT_KEYS 联赛的开球 —— **只读 AF 缓存,永不联网**。

    哨兵用它回答「收盘锚这几天没长,是没东西可抓,还是漏了」—— 问的是 cron 自己
    用来决定拉什么的**同一份赛程**(同一个筛选 `_sport_key_kickoffs`),而不是去信
    cron 自报的「前瞻窗内无开球」:AF 抓失败时 `resolve_auto_sports` 也返回 []、
    也打印那一句,自报分不清「没有」和「没去看」。

    ⚠️ 不是证据的缓存一律记进 ``unknown_days``:文件缺失(没缓存 ≠ 没比赛)、
       读坏、``[]``(全世界一天零场不合理 = 一次「空的成功」)、一场都认不出(格式漂了)。
    ⚠️ 推迟 / 取消(`_NOT_PLAYED`)的不算:它们没有收盘线可抓。
    """
    from nutmeg.v4.data.sources.api_football import (
        API_FOOTBALL_LEAGUE_IDS,
        cached_fixtures_for_date,
    )

    id_to_canonical = {v: k for k, v in API_FOOTBALL_LEAGUE_IDS.items()}
    scan = KickoffScan()
    d = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    while start < end and d <= last:
        rows = cached_fixtures_for_date(d, cache_dir=Path(cache_dir))
        if not rows or not any(_kickoff_and_league(fx) for fx in rows):
            scan.unknown_days.append(d)
        else:
            scan.days_read.append(d)
            scan.fixtures_seen += len(rows)
            hits = sorted(
                (ko, canonical)
                for ko, canonical, fx in _sport_key_kickoffs(rows, id_to_canonical)
                if start < ko <= end and _status_short(fx) not in _NOT_PLAYED
            )
            if hits:
                scan.kickoffs = hits
                break
        d += timedelta(days=1)
    return scan


def heartbeat_path(db_path: str | Path) -> Path:
    return Path(db_path).resolve().parent / HEARTBEAT_FILENAME


def write_heartbeat(db_path: str | Path, *, now: datetime | None = None) -> None:
    """cron 跑完一轮 `--sports auto` 就写(无论这轮抓没抓到东西)。

    Fail-soft:心跳写不进去**绝不许**拖垮收盘捕获 —— 那是 CLV 地基,心跳只是旁证。
    tmp + rename:哨兵永远读不到写了一半的文件。"""
    try:
        p = heartbeat_path(db_path)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text((now or datetime.now(UTC)).isoformat(timespec="seconds") + "\n",
                       encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        log.warning("closing heartbeat write failed", exc_info=True)


def read_heartbeat(db_path: str | Path) -> datetime | None:
    """→ 心跳时刻(aware);没有 / 读不出 → None(**不**回落到文件 mtime —— 兜底要看得出来)。"""
    try:
        text = heartbeat_path(db_path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    lines = text.splitlines()
    return _parse_iso(lines[0].strip()) if lines else None


def capture_closing_pinnacle(
    db_path: str | Path,
    sport_keys,
    *,
    refresh: bool = True,
    now: datetime | None = None,
) -> dict:
    """For each sport (short key like 'WC'/'UCL' or a raw odds-api sport_key),
    fetch the current Pinnacle lookup and append each quotable *pre-kickoff* match
    as a ``source='closing'`` snapshot. Returns ``{sport_key: rows_written}``.
    Fail-soft per sport — a fetch failure just writes 0 for that sport.

    PRE-KICKOFF ONLY: once a match starts, The Odds API serves LIVE Pinnacle odds
    (a leading team → a degenerate 1.06/53.96 line). Recording those as a "close"
    poisons the CLV ledger and the soft-water scan (2026-07-01: an in-play capture
    produced a phantom +87% EV leg). We skip any match whose kickoff is at/​before
    the observation instant; a match with no parseable kickoff is skipped too
    (can't prove it's pre-match). The last snapshot before kickoff = the true close.

    🚨 **该闸的 `now` 必须逐行重取,且必须就是落库的 `captured_at`**(2026-09-01)。
    此前 `now` 只在函数入口取一次,而它到写库之间隔着:每个 sport 一次
    `fetch_pinnacle_lookup` HTTP + 一次 `capture_books_for_sport` + 逐行写库。
    实测(789 轮 closing)**写入→写入**跨度随本轮联赛数线性增长:1 个联赛 p50 0s、
    11 个联赛 p50 8s / max 9s —— 而 `now` 取在第一次 HTTP **之前**,真实窗口比这更宽。
    cron 又恰好卡在最坏相位:`StartInterval 1800` 漂到 HH:29:5x / HH:59:5x,
    而开球集中在 HH:00:00 / HH:30:00 ⇒ **每一轮都在开球点前几秒起跑**。
    2026-08-30 因此写出 2 行 `captured_at > kickoff_utc`(晚 1s / 2s),
    撞红了那条生产哨兵(它当时叫 `…gate_is_currently_a_noop…`,现已随本次
    修复改名为 `test_pre_kickoff_gate_blocks_nothing_written_after_the_race_fix`)。

    ⭐ 修法是**取一次、既判闸又落库**(`observed`),不是加安全边界:
      · 只重取 `now` 而让 sink 自己戳 `captured_at` ⇒ 闸与戳之间仍有 δ。δ 实测
        p50 0.2ms,但 `record_row_snapshot` 自带 `busy_timeout=3000` ⇒ **最坏 3s**
        ⇒ 要挡住它得上 M≥3s 的边界。
      · 而边界**恰好只砍最有价值的那批线**:实测 lead<5s 的有 6 场(0.50%)、
        lead<30s 的 19 场(1.57%),它们被挡掉后 close 全部退化到**约 30 分钟前**
        (上一 tick;0 场彻底失去 close)。本模块存在的全部理由就是「贴着自己的
        开球点取线」(修 ③ 的中位 ~5h 陈旧锚)⇒ 花 0.5–1.6% 最贵的线去换一个
        δ 本可以直接消掉的问题,是**用钱买省事**。
      · `observed` 先 `.replace(microsecond=0)` 再判闸,判闸用**同样截秒**的开球点
        ⇒ 落库字面 `captured_at < kickoff_utc` 由构造保证,零边界、零合法行损失。
    ⚠️ 显式传入的 `now` 仍然被尊重(冻结时钟 = 测试/回放),此时不重取。"""
    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.observation.book_snapshots import capture_books_for_sport
    from nutmeg.v4.observation.odds_snapshots import record_row_snapshot

    frozen_now = now          # 显式传入 = 冻结时钟(测试/回放);None = 实时,逐行重取
    out: dict[str, int] = {}
    for sk in sport_keys:
        sport_key = odds_api.SPORT_KEYS.get(sk, sk)
        try:
            lookup = odds_api.fetch_pinnacle_lookup(sport_key, refresh=refresh)
        except Exception:  # noqa: BLE001 — fail-soft; one sport's failure isn't fatal
            log.warning("closing-odds fetch failed for %s (%s)", sk, sport_key,
                        exc_info=True)
            out[sk] = 0
            continue
        # 多书商快照(2026-09-01)—— **零额外调用**:`fetch_current_odds` 是 TTL 缓存的,
        # 上面这次 `fetch_pinnacle_lookup` 刚取过同一批事件,这里只是把**本来丢掉的
        # 那 15–22 家**读出来存下。用途=给单锚做离散度参照(见 `book_snapshots` 模块头)。
        # ⛔ 整段 fail-soft 且**独立于主流程**:它坏了绝不影响 Pinnacle 收盘线的采集
        #    —— 那是 CLV 地基,不能被一个「参照层」拖累。
        # ⭐ 2026-09-01 抽成 `capture_books_for_sport` 一处定义:盘面「🔄 刷新盘口」
        #    也要落同一张表(见 ingest_odds._gather_rows),而**平行入口不会被用,
        #    只会分裂口径** —— 两边必须是同一个函数。
        capture_books_for_sport(db_path, sport_key, refresh=False)
        written = 0
        skipped_live = 0
        for key, e in (lookup or {}).items():
            # 体检 2026-07-03 — fetch_pinnacle_lookup poisons ambiguous club-core
            # secondary keys to None (c5e805f wrong-team guard). The overlay
            # consumer skips them via `if not rec`; this loop is OUTSIDE the
            # per-sport try, so an unguarded None crashes the WHOLE capture round.
            if e is None:
                continue
            # 🚨 逐行重取观测时刻 —— **不能**用函数入口那个 now(见 docstring:
            #    中间隔着 HTTP + 书商快照 + 逐行写库,实测最宽 9s,而 cron 正好在
            #    开球点前几秒起跑)。截到秒:落库的 `captured_at` 就是这个值,
            #    判闸也拿它跟**同样截秒**的开球点比 ⇒ `captured_at < kickoff_utc`
            #    由构造成立,不需要安全边界,也不损失任何合法的临开球线。
            observed = (frozen_now or datetime.now(UTC)).replace(microsecond=0)
            kickoff = _parse_iso(e.get("commence_time"))
            if kickoff is None or observed >= kickoff.replace(microsecond=0):
                skipped_live += 1  # already kicked off (live odds) or unknown KO
                continue
            date = key[2] if isinstance(key, tuple) and len(key) >= 3 else e.get("date")
            row = {
                "date": date,
                "league": sk,
                "home_team": _canon(e.get("home_team")),
                "away_team": _canon(e.get("away_team")),
                "psc_home": e.get("psc_home"),
                "psc_draw": e.get("psc_draw"),
                "psc_away": e.get("psc_away"),
                "ou_line": e.get("ou_line"),
                "psc_over25": e.get("psc_over"),
                "psc_under25": e.get("psc_under"),
                "odds_update": e.get("last_update"),
                "kickoff_utc": e.get("commence_time"),
                # 本路径 OA 独用(Pinnacle-STRICT,无 AF 兜底)→ 显式标源,
                # 否则 record_row_snapshot 的默认会把它记成 api_football。
                "odds_source": "odds_api",
            }
            if not (row["date"] and row["home_team"] and row["away_team"]):
                continue
            # ⭐ 把判过闸的那个时刻**原样**戳进 captured_at —— 不让 sink 在写库那一刻
            #    再取一次 now(那就又出现闸与戳之间的 δ)。它也比写库时刻**更接近真相**:
            #    「我们何时观测到」= 取数那一刻,不是落盘那一刻。
            written += int(record_row_snapshot(
                db_path, row, source="closing",
                captured_at=observed.isoformat(timespec="seconds")))
        if skipped_live:
            log.info("closing-odds %s: skipped %d already-started/unknown-KO match(es)",
                     sk, skipped_live)
        out[sk] = written
    return out
