"""closing 子流:「cron 死了」和「没东西可抓」必须分得开(2026-09-23)。

病史:09-21 起国际比赛日,SPORT_KEYS 联赛全停。`com.nutmeg.closing_odds` 每 30 分钟照跑
(launchd runs=48、exit 0、out.log 1 分钟前),每轮打印「前瞻窗内无 SPORT_KEYS 联赛开球」——
而 `odds_snapshots[closing]` 3 天没长,哨兵按纯年龄判「✗ 停更 — 捕获 cron 可能静默死了」,
health_check NOT HEALTHY。**诊断和事实相反。**

修法(`data_freshness._judge_closing`):超龄后问**权威源** —— cron 自己用来决定拉什么的
AF 赛程缓存 —— 期间有没有该抓的开球;再看 cron 心跳。两条都**证明**了才放行。
⛔ 不是放宽天数:有开球的周里判红时点不变(下面「阳性对照」那几条钉的就是这个)。

⚠️ 本文件的 AF 缓存全是 tmp 里的合成文件;conftest 的 `_no_live_api_football` 兜底 ——
   哪条路径敢联网,用例在 teardown 直接红。
"""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from nutmeg.v4.cli import data_freshness as df
from nutmeg.v4.data.sources import api_football
from nutmeg.v4.data.sources.api_football import API_FOOTBALL_LEAGUE_IDS, _cache_path
from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
from nutmeg.v4.observation import closing_odds as co

from .test_data_freshness import _all_today, _mk_db

TODAY = date(2026, 6, 17)
NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
#: 最后一轮捕获 —— 复刻 09-20 22:55 那一轮:它抓的正是 23:00 开球那场。
LAST = datetime(2026, 6, 13, 22, 55, 16, tzinfo=UTC)
CLOSING = df.CLOSING_STREAM
#: 除 --db/--today 外关掉所有与本文件无关的探针(出站的、读 cwd 的都关)。
_QUIET_FLAGS = ("--no-quota", "--no-vintage", "--no-supply", "--no-league-labels",
                "--no-season", "--no-gapcurve", "--no-trickle")


def _ids() -> tuple[int, int]:
    """(SPORT_KEYS 联赛, 非 SPORT_KEYS 联赛)的 AF id —— 前提写成断言,注册表变了就大声红。"""
    assert "USA_MLS" in SPORT_KEYS, "前提变了:MLS 不在 SPORT_KEYS"
    assert "UEFA_NATIONS_LEAGUE" not in SPORT_KEYS, (
        "前提变了:欧国联进了 SPORT_KEYS —— 本文件的「国际比赛日」夹具要换一个 cron 不管的联赛")
    return API_FOOTBALL_LEAGUE_IDS["USA_MLS"], API_FOOTBALL_LEAGUE_IDS["UEFA_NATIONS_LEAGUE"]


def _fx(ko: datetime | str, league_id: int, status: str = "NS") -> dict:
    ko = ko.isoformat() if isinstance(ko, datetime) else ko
    return {"fixture": {"date": ko, "status": {"short": status}}, "league": {"id": league_id}}


def _cache_day(root: Path, day: str, fixtures) -> None:
    """按 `fetch_fixtures_for_date(day)` 的缓存键落一份合成赛程(库目录下的 external/…)。"""
    cf = _cache_path("/fixtures", {"date": day}, root / "external" / "api_football")
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(fixtures))


def _break_week(root: Path) -> None:
    """国际比赛日:06-13 23:00 最后一场 MLS(22:55 那轮已抓),之后只有欧国联 + 注册表外的赛事。"""
    mls, unl = _ids()
    _cache_day(root, "2026-06-13", [_fx("2026-06-13T23:00:00+00:00", mls, "FT"),
                                    _fx("2026-06-13T18:45:00+00:00", unl, "FT")])
    for d in ("2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"):
        _cache_day(root, d, [_fx(f"{d}T18:45:00+00:00", unl),
                             _fx(f"{d}T16:00:00+00:00", 999_999)])   # 注册表外


def _db(tmp_path: Path, closing: list[str] | None = None) -> Path:
    rows = _all_today()
    rows[CLOSING] = closing or ["2026-06-12T19:00:00+00:00", LAST.isoformat()]
    return _mk_db(tmp_path, rows)


def _closing(db: Path, *, now: datetime = NOW) -> df.TableStatus:
    return {s.table: s for s in df.check_freshness(db, today=TODAY, now=now)}[CLOSING]


def _beat(db: Path, at: datetime) -> None:
    co.write_heartbeat(db, now=at)


# ─────────────────────────────── 核心:两种局面必须分得开 ───────────────────────────────

class TestBreakWeekVsDeadCron:

    def test_break_with_a_live_cron_is_quiet_not_stale(self, tmp_path):
        db = _db(tmp_path)
        _break_week(tmp_path)
        _beat(db, NOW - timedelta(minutes=15))
        st = _closing(db)
        assert st.aged, "夹具没造出「按年龄会红」的局面 ⇒ 下面的断言恒真"
        assert not st.stale and st.quiet, st.why
        assert "空窗" in st.why and "SPORT_KEYS 联赛 0 场开球" in st.why
        # 身后那段也不是「洞」:什么都没丢 —— 但报告里留痕,不是凭空消失
        assert st.gaps == []
        assert st.quiet_gaps == [("2026-06-14", "2026-06-17", 4)]

    def test_break_with_a_live_cron_passes_the_gate(self, tmp_path, capsys):
        db = _db(tmp_path)
        _break_week(tmp_path)
        _beat(db, datetime(2026, 6, 17, 11, 45, tzinfo=UTC))
        rc = df.main(["--db", str(db), "--today", "2026-06-17", "--porcelain", *_QUIET_FLAGS])
        out = capsys.readouterr().out
        closing_lines = [ln for ln in out.splitlines() if f"\t{CLOSING}\t" in ln]
        assert [ln.split("\t")[0] for ln in closing_lines] == ["QUIET"], out
        assert "空窗" in closing_lines[0], (
            "QUIET 行没带理由 —— health_check 只会印一个光秃秃的「空窗」")
        assert rc == 0, out

    def test_dead_cron_during_a_break_is_still_red(self, tmp_path, capsys):
        """⭐ 阳性对照 ①:同一个空窗,cron 心跳停在 4 天前 ⇒ 必须红。"""
        db = _db(tmp_path)
        _break_week(tmp_path)
        _beat(db, LAST)
        st = _closing(db)
        assert st.stale and not st.quiet
        assert "cron 本身停了" in st.why, st.why
        rc = df.main(["--db", str(db), "--today", "2026-06-17", "--porcelain", *_QUIET_FLAGS])
        out = capsys.readouterr().out
        assert f"STALE\t{CLOSING}\t" in out and rc == 1, out

    def test_no_heartbeat_cannot_prove_the_cron_alive(self, tmp_path):
        db = _db(tmp_path)
        _break_week(tmp_path)
        st = _closing(db)
        assert st.stale and "证明不了 cron 活着" in st.why, st.why

    def test_missed_kickoff_is_red_even_with_a_live_cron(self, tmp_path, capsys):
        """⭐ 阳性对照 ②:平常周 —— 期间有 SPORT_KEYS 开球而没抓到 ⇒ 红,心跳再新也没用。

        (2026-07 Odds API 额度耗尽那次就是这个形状:cron 活着、每轮都跑,一行没写进来。)"""
        db = _db(tmp_path)
        _break_week(tmp_path)
        mls, unl = _ids()
        _cache_day(tmp_path, "2026-06-15", [_fx("2026-06-15T23:30:00+00:00", mls),
                                            _fx("2026-06-15T18:45:00+00:00", unl)])
        _beat(db, NOW - timedelta(minutes=15))
        st = _closing(db)
        assert st.stale and not st.quiet
        assert "不是空窗" in st.why and "06-15 23:30Z USA_MLS" in st.why, st.why
        assert "cron 活着" in st.why, "归因丢了:心跳是新的 ⇒ 该指向抓取/额度,不是 cron"
        assert st.gaps == [("2026-06-14", "2026-06-17", 4)], "真漏了的那段仍是洞"
        rc = df.main(["--db", str(db), "--today", "2026-06-17", "--porcelain", *_QUIET_FLAGS])
        assert rc == 1, capsys.readouterr().out

    def test_a_fresh_stream_is_untouched(self, tmp_path):
        """健康的流不读缓存、不看心跳、不多说一个字。"""
        db = _db(tmp_path, closing=["2026-06-17T09:00:00+00:00"])
        st = _closing(db)
        assert not st.stale and not st.quiet and st.why is None


# ─────────────────────────── 窗口的边:前瞻窗、推迟、证据不足 ───────────────────────────

class TestWhatCountsAsProof:

    @pytest.mark.parametrize("minutes_after_last, missed", [(74, False), (76, True)])
    def test_the_last_rounds_lookahead_is_already_covered(self, tmp_path, minutes_after_last,
                                                          missed):
        """最后一轮捕获已经把 (last, last+前瞻] 里开球的场次抓进来了 ⇒ 那段不算漏;
        过了前瞻窗才是「必须再跑一轮」的。钉的是 `AUTO_LOOKAHEAD_MINUTES` 的语义。"""
        assert co.AUTO_LOOKAHEAD_MINUTES == 75, "改了前瞻窗就同步改这里的 74/76"
        db = _db(tmp_path)
        _break_week(tmp_path)
        mls, unl = _ids()
        ko = LAST + timedelta(minutes=minutes_after_last)
        _cache_day(tmp_path, "2026-06-14", [_fx(ko, mls, "FT"),
                                            _fx("2026-06-14T18:45:00+00:00", unl)])
        _beat(db, NOW - timedelta(minutes=15))
        assert _closing(db).stale is missed

    def test_postponed_or_cancelled_is_not_a_miss(self, tmp_path):
        db = _db(tmp_path)
        _break_week(tmp_path)
        mls, unl = _ids()
        _cache_day(tmp_path, "2026-06-15", [_fx("2026-06-15T23:30:00+00:00", mls, "PST"),
                                            _fx("2026-06-16T01:00:00+00:00", mls, "CANC"),
                                            _fx("2026-06-15T18:45:00+00:00", unl)])
        _beat(db, NOW - timedelta(minutes=15))
        assert _closing(db).quiet

    def test_a_missing_cache_day_cannot_prove_quiet(self, tmp_path):
        """没缓存 ≠ 没比赛。"""
        db = _db(tmp_path)
        _break_week(tmp_path)
        _cache_path("/fixtures", {"date": "2026-06-15"},
                    tmp_path / "external" / "api_football").unlink()
        _beat(db, NOW - timedelta(minutes=15))
        st = _closing(db)
        assert st.stale and "证明不了是空窗" in st.why and "06-15" in st.why, st.why

    @pytest.mark.parametrize("junk", [[], [{"weird": 1}], {"response": []}],
                             ids=["empty-success", "unrecognisable", "wrong-shape"])
    def test_a_junk_cache_day_is_not_evidence(self, tmp_path, junk):
        """全世界一天零场不合理(空的成功);一场都认不出 = 格式漂了。都不是「那天没球」。"""
        db = _db(tmp_path)
        _break_week(tmp_path)
        _cache_day(tmp_path, "2026-06-15", junk)
        _beat(db, NOW - timedelta(minutes=15))
        assert _closing(db).stale

    def test_the_judge_crashing_keeps_the_old_red(self, tmp_path, monkeypatch):
        """判定自己炸了 ⇒ 维持纯年龄判据,并且说出来 —— 不许炸成「绿」。"""
        db = _db(tmp_path)
        _break_week(tmp_path)
        _beat(db, NOW - timedelta(minutes=15))

        def boom(*a, **kw):
            raise RuntimeError("缓存格式大改")

        monkeypatch.setattr(co, "scan_uncaptured_kickoffs", boom)
        st = _closing(db)
        assert st.stale and "炸了" in st.why and "RuntimeError" in st.why


class TestInteriorGaps:
    """内部空洞同理:期间一场该抓的都没有 ⇒ 什么都没丢,不是洞。"""

    def _db_with_gap(self, tmp_path):
        # 06-07 ~ 06-09 三天没行(≥ MIN_GAP_DAYS),流本身是新鲜的
        return _db(tmp_path, closing=[
            "2026-06-05T20:00:00+00:00", "2026-06-06T20:00:00+00:00",
            "2026-06-10T01:00:00+00:00", "2026-06-11T20:00:00+00:00",
            "2026-06-12T20:00:00+00:00", "2026-06-13T20:00:00+00:00",
            "2026-06-14T20:00:00+00:00", "2026-06-15T20:00:00+00:00",
            "2026-06-16T20:00:00+00:00", "2026-06-17T09:00:00+00:00"])

    def _gap_days(self, tmp_path, *, with_kickoff: bool):
        mls, unl = _ids()
        for d in ("2026-06-06", "2026-06-07", "2026-06-08", "2026-06-09", "2026-06-10"):
            fx = [_fx(f"{d}T18:45:00+00:00", unl)]
            if with_kickoff and d == "2026-06-08":
                fx.append(_fx(f"{d}T23:30:00+00:00", mls, "FT"))
            _cache_day(tmp_path, d, fx)

    def test_quiet_gap_is_not_a_hole(self, tmp_path):
        db = self._db_with_gap(tmp_path)
        self._gap_days(tmp_path, with_kickoff=False)
        st = _closing(db)
        assert not st.stale and st.why is None
        assert st.gaps == [] and st.quiet_gaps == [("2026-06-07", "2026-06-09", 3)]

    def test_gap_with_a_kickoff_is_still_a_hole(self, tmp_path):
        db = self._db_with_gap(tmp_path)
        self._gap_days(tmp_path, with_kickoff=True)
        st = _closing(db)
        assert st.gaps == [("2026-06-07", "2026-06-09", 3)] and st.quiet_gaps == []


# ─────────────────────────── 权威源:同一份赛程、同一个筛选、永不联网 ───────────────────────────

class TestSameSourceAsTheCron:

    def test_cached_reader_reads_the_file_the_fetcher_writes(self, tmp_path):
        """孪生校验:哨兵读的必须是 `fetch_fixtures_for_date` 那份缓存。键漂了 ⇒ fetcher 缓存
        未命中去联网 ⇒ conftest 的 AF 出口闸让本用例红。"""
        rows = [_fx("2026-06-10T18:00:00+00:00", 39)]
        cf = _cache_path("/fixtures", {"date": "2026-06-10"}, tmp_path)
        cf.parent.mkdir(parents=True)
        cf.write_text(json.dumps(rows))
        assert api_football.fetch_fixtures_for_date(date(2026, 6, 10), cache_dir=tmp_path) == rows
        assert api_football.cached_fixtures_for_date(date(2026, 6, 10), cache_dir=tmp_path) == rows
        assert api_football.cached_fixtures_for_date(date(2026, 6, 11), cache_dir=tmp_path) is None

    def test_the_scan_never_goes_through_the_fetcher(self, tmp_path, monkeypatch):
        """`fetch_fixtures_for_date` 对今天及以后的日期会在 TTL 过期时强制重拉 = 花钱。
        哨兵连它都不许碰 —— 把它和 `_request` 都换成炸弹,扫描照样出结论。"""
        def boom(*a, **kw):
            raise AssertionError("哨兵走进了会联网的路径")

        monkeypatch.setattr(api_football, "fetch_fixtures_for_date", boom)
        monkeypatch.setattr(api_football, "_request", boom)
        _break_week(tmp_path)
        scan = co.scan_uncaptured_kickoffs(LAST + timedelta(minutes=75), NOW,
                                           cache_dir=tmp_path / "external" / "api_football")
        assert scan.proves_nothing_to_capture and scan.fixtures_seen == 8

    def test_cron_and_sentinel_share_one_definition_of_a_capturable_kickoff(self, tmp_path):
        """cron 据它拉 sport、哨兵据它判空窗 —— 同一批 fixture,两边认的联赛必须一样。"""
        mls, unl = _ids()
        ko = datetime(2026, 6, 15, 23, 30, tzinfo=UTC)
        fixtures = [_fx(ko, mls), _fx(ko, unl), _fx(ko, 999_999), {"junk": True}]
        cron = co.resolve_auto_sports(now=ko - timedelta(minutes=30),
                                      fetch_fixtures=lambda d: fixtures)
        _cache_day(tmp_path, "2026-06-15", fixtures)
        scan = co.scan_uncaptured_kickoffs(ko - timedelta(hours=1), ko,
                                           cache_dir=tmp_path / "external" / "api_football")
        assert cron == ["USA_MLS"]
        assert [lg for _, lg in scan.kickoffs] == cron

    def test_the_derived_cache_dir_is_the_fetchers_default(self):
        """哨兵按库路径推缓存目录;生产布局下它必须落在 `DEFAULT_CACHE_DIR` 上。"""
        assert df._fixture_cache_dir("data/v4_observation.db") == \
            api_football.DEFAULT_CACHE_DIR.resolve()


# ─────────────────────────── cron 侧:心跳 ───────────────────────────

class TestCronHeartbeat:

    def _run(self, monkeypatch, db, *argv, sports=()):
        from nutmeg.v4.cli import closing_odds as cli

        calls: list = []
        monkeypatch.setattr(co, "resolve_auto_sports", lambda **kw: list(sports))
        monkeypatch.setattr(co, "capture_closing_pinnacle",
                            lambda db_path, sk, **kw: calls.append(sk) or {s: 0 for s in sk})
        return cli.main(["--db", str(db), *argv]), calls

    def test_the_nothing_to_capture_round_still_beats(self, tmp_path, monkeypatch):
        """⭐ 就是这一支:空窗期 cron 一行都不写,心跳是它活着的唯一证据。"""
        db = tmp_path / "obs.db"
        before = datetime.now(UTC).replace(microsecond=0)
        rc, calls = self._run(monkeypatch, db)
        assert rc == 0 and calls == []
        hb = co.read_heartbeat(db)
        assert hb is not None and hb >= before

    def test_a_capture_round_beats_too(self, tmp_path, monkeypatch):
        db = tmp_path / "obs.db"
        rc, calls = self._run(monkeypatch, db, sports=["USA_MLS"])
        assert rc == 0 and calls == [["USA_MLS"]]
        assert co.read_heartbeat(db) is not None

    def test_a_manual_run_does_not_vouch_for_the_cron(self, tmp_path, monkeypatch):
        """手动 `--sports WC` 跑一次,不该替一个死掉的 cron 作证。"""
        db = tmp_path / "obs.db"
        rc, calls = self._run(monkeypatch, db, "--sports", "WC")
        assert rc == 0 and calls == [["WC"]]
        assert co.read_heartbeat(db) is None

    def test_a_heartbeat_failure_never_breaks_the_capture(self, tmp_path, monkeypatch):
        db = tmp_path / "no-such-dir" / "obs.db"          # 心跳写不进去
        rc, calls = self._run(monkeypatch, db, sports=["USA_MLS"])
        assert rc == 0 and calls == [["USA_MLS"]]
        assert co.read_heartbeat(db) is None


# ─────────────────────────── health_check.sh 真的认得 QUIET ───────────────────────────

def test_health_check_renders_quiet_as_its_own_green_line():
    """把 §9 的 case 块原样抠出来跑:QUIET 不许掉进 `*)` 兜底(那会把理由吞掉),
    也不许让体检失败。"""
    body = (Path(__file__).resolve().parents[2] / "scripts" / "health_check.sh").read_text()
    sec = body[body.index('section "9.'):]
    block = sec[sec.index('case "$st" in'):sec.index("esac") + len("esac")]
    script = (
        "EXIT_CODE=0\n"
        'ok() { echo "OK: $1"; }\nwarn() { echo "WARN: $1"; }\n'
        'fail() { echo "FAIL: $1"; EXIT_CODE=1; }\nnote() { echo "NOTE: $1"; }\n'
        "while IFS=$'\\t' read -r st tab rows last days crit note; do\n"
        + block + "\ndone <<< $'QUIET\\todds_snapshots[closing]\\t9\\t2026-09-20\\t3\\t1"
        "\\tPinnacle 收盘锚 · 空窗无可捕获:理由'\n"
        'echo "EXIT=$EXIT_CODE"\n')
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                         check=True).stdout
    assert out.startswith("OK: odds_snapshots[closing] 空窗(非停更)"), out
    assert "空窗无可捕获:理由" in out and "EXIT=0" in out, out
