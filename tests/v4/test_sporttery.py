"""中国体育彩票 (竞彩) source — parse, name mapping, fail-soft."""
from __future__ import annotations

from nutmeg.v4.data.sources import sporttery


def _payload():
    return {"success": True, "value": {"matchInfoList": [
        {"subMatchList": [
            {"homeTeamAllName": "墨西哥", "awayTeamAllName": "南非",
             "matchDate": "2026-06-12", "matchTime": "07:00:00", "matchNumStr": "周四001",
             "leagueAbbName": "世界杯",
             "had": {"h": "1.26", "d": "4.45", "a": "9.00"},
             "hhad": {"h": "2.00", "d": "3.25", "a": "3.11", "goalLine": "-1"}},
            {"homeTeamAllName": "火星联队", "awayTeamAllName": "月球联队",  # unmapped
             "matchDate": "2026-06-12", "matchNumStr": "周四099",
             "had": {"h": "2.0", "d": "3.0", "a": "3.5"}, "hhad": {}},
        ]}
    ]}}


def test_parse_had_hhad_and_map(monkeypatch):
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: _payload())
    ms = sporttery.fetch_lottery_matches()
    assert len(ms) == 2
    mex = ms[0]
    assert mex["home_en"] == "Mexico"          # 墨西哥 → canonical English
    assert mex["away_en"] is not None
    assert mex["had"] == (1.26, 4.45, 9.00)
    assert mex["hhad"] == (2.00, 3.25, 3.11, -1)   # incl. goalLine as int
    assert mex["match_date"] == "2026-06-11"   # 07:00 北京 → 前一 UTC 日
    assert mex["kickoff_utc"] == "2026-06-11T23:00:00+00:00"
    # second match: unmapped team + no 让球 pool
    assert ms[1]["home_en"] is None and ms[1]["hhad"] is None


def test_beijing_to_utc_date():
    """竞彩 matchDate is the Beijing (UTC+8) date; the join keys on the UTC date,
    so an early-morning Beijing kickoff must roll back to the previous UTC day."""
    f = sporttery._utc_date_and_kickoff
    assert f("2026-06-12", "07:00:00") == ("2026-06-11", "2026-06-11T23:00:00+00:00")
    assert f("2026-06-12", "20:00:00")[0] == "2026-06-12"   # 20:00 北京 → 同 UTC 日
    assert f("2026-06-12", None) == ("2026-06-12", None)     # no time → fallback


def test_zh_to_canonical():
    assert sporttery.zh_to_canonical("墨西哥") == "Mexico"
    assert sporttery.zh_to_canonical("不存在的队名") is None
    assert sporttery.zh_to_canonical(None) is None


def test_synonym_override_to_live_name():
    """TEAM_NAME_ZH's English ('Korea Republic') is corrected to the live
    odds_snapshots/settler name ('South Korea') so 竞彩 rows actually join."""
    zh = next((z for z, en in sporttery._ZH_TO_EN.items() if en == "Korea Republic"), None)
    assert zh is not None
    assert sporttery.zh_to_canonical(zh) == "South Korea"     # overridden
    zh_mex = next(z for z, en in sporttery._ZH_TO_EN.items() if en == "Mexico")
    assert sporttery.zh_to_canonical(zh_mex) == "Mexico"      # un-overridden passthrough


def test_club_prefix_override():
    """Club gather names are RAW API-Football (with prefixes); the override maps
    TEAM_NAME_ZH's cleaned key to the live name so 竞彩 league rows join."""
    zh = next((z for z, en in sporttery._ZH_TO_EN.items() if en == "Freiburg"), None)
    assert zh is not None
    assert sporttery.zh_to_canonical(zh) == "SC Freiburg"


def test_harvest_to_db_counts(tmp_path):
    """harvest_to_db (shared by CLI + 🎯 刷新竞彩 endpoint) writes mapped matches +
    skips unmapped, returning the counts."""
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = str(tmp_path / "obs.db")
    matches = [
        {"home_en": "Mexico", "away_en": "South Africa", "league_cn": "WC",
         "match_date": "2026-06-20", "kickoff_utc": None,
         "had": (1.7, 3.4, 4.5), "hhad": (2.0, 3.2, 3.3, -1)},
        {"home_en": None, "away_en": "X", "league_cn": "WC",  # unmapped → skipped
         "match_date": "2026-06-20", "had": (2.0, 3.0, 3.5), "hhad": None},
    ]
    r = harvest_to_db(db, matches=matches)
    assert r["matches"] == 2 and r["mapped"] == 1 and r["unmapped"] == 1
    assert r["had"] == 1 and r["hhad"] == 1


def test_refresh_response_carries_unmapped_teams(tmp_path):
    """🎯 端点 schema 必须透传 unmapped_teams(WHO got dropped)。2026-07-09:字段
    在 harvest 返回里一直有,但 SportteryRefreshResponse 没声明 → pydantic 静默吞掉,
    UI 只见 unmapped=2 个数字,owner 只能从「SP 对不上官网」倒推词典缺口(UEL Q1)。"""
    from nutmeg.v4.api.schemas import SportteryRefreshResponse
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    db = str(tmp_path / "obs.db")
    matches = [
        {"home_en": None, "away_en": "Derry City", "home_cn": "索菲亚中央陆军",
         "away_cn": "德里城", "league_cn": "欧罗巴", "match_date": "2026-07-09",
         "had": (1.14, 5.95, 12.0), "hhad": None},
    ]
    resp = SportteryRefreshResponse(ok=True, **harvest_to_db(db, matches=matches))
    assert resp.unmapped == 1
    assert resp.unmapped_teams == [
        {"home_cn": "索菲亚中央陆军", "away_cn": "德里城", "league_cn": "欧罗巴"}]


def test_uel_qualifier_zh_override():
    """欧联资格赛 UEL Q1 (2026-07-09) — 主队中文名缺字典 → 2 场整场静默丢弃,面板
    SP 落在数小时前的 market_mode 旧行,与竞彩官网对不上(owner 实报)。EN 值 =
    库内 AF gather 名(jingcai_sp market_mode 行同名)。"""
    assert sporttery.zh_to_canonical("索菲亚中央陆军") == "CSKA Sofia"
    assert sporttery.zh_to_canonical("斯普利特海杜克") == "HNK Hajduk Split"


def test_nor_eliteserien_zh_override():
    """挪超 NOR_ELITESERIEN (2026-07-11) — 竞彩用传统译名,TEAM_NAME_ZH 用音译 →
    4/8 在售挪超场整对静默丢弃(owner 实报「腓特烈 vs 利勒斯特 20:00 不在可投注列表」)。
    EN 值 = TEAM_NAME_ZH 既有规范键,逐一对竞彩英文 abbr (FRD/AAE/STR/SJD/HKM) 核对。"""
    assert sporttery.zh_to_canonical("腓特烈斯塔") == "Fredrikstad"
    assert sporttery.zh_to_canonical("奥勒松") == "Aalesund"
    assert sporttery.zh_to_canonical("斯达") == "Start"
    assert sporttery.zh_to_canonical("桑纳菲尤尔") == "Sandefjord"
    assert sporttery.zh_to_canonical("汉坎") == "Ham-Kam"
    # 已映射侧未受影响(半联赛盲区的另一半)
    assert sporttery.zh_to_canonical("利勒斯特罗姆") == "Lillestrom"
    assert sporttery.zh_to_canonical("特罗姆瑟") == "Tromso"


def test_mls_zh_override():
    """美职联 USA_MLS (2026-07-14) — 竞彩保留拉丁后缀(蒙特利尔CF/多伦多FC)而字典砍了,
    外加「伐木工」vs 我们的「伐木者」→ 4 场在售丢 2 场(owner 实报)。EN 值 = live
    cup-market gather 名。补别名时没配测试(全文件唯一漏锁的联赛块),2026-07-16 补。"""
    assert sporttery.zh_to_canonical("蒙特利尔CF") == "CF Montreal"
    assert sporttery.zh_to_canonical("多伦多FC") == "Toronto FC"
    assert sporttery.zh_to_canonical("波特兰伐木工") == "Portland Timbers"


def test_bra_serie_a_zh_override():
    """巴甲 BRA_SERIE_A (2026-07-16) — MLS 那条注释预言的姊妹雷(同日注册、同样只写了
    标准媒体译名)。竞彩「布拉干蒂诺RB」≠ 字典「布拉甘蒂诺」(RB 后缀词序 + 干/甘 一字之差)
    → 20 场在售丢 1 场。EN 值 = 实盘 gather 名(odds_snapshots BRA_SERIE_A 2026-07-17
    'Fluminense' vs 'RB Bragantino',Pinnacle 线已在库)。"""
    assert sporttery.zh_to_canonical("布拉干蒂诺RB") == "RB Bragantino"
    # 已映射侧未受影响 —— 一队断即整场丢,这半边一直是好的(半坏盲区的另一半)
    assert sporttery.zh_to_canonical("弗鲁米嫩塞") == "Fluminense"
    # 字典原有拼法保持可用(竞彩若哪天改写法,两种都认)
    assert sporttery.zh_to_canonical("布拉甘蒂诺") == "RB Bragantino"


def test_finnish_zh_override():
    """芬超 (market-mode league) — 竞彩's descriptive 中文 maps to the live cup-market
    gather name so the 竞彩 SP pre-fills (was 4/6 matches blank: 体检 2026-06-13)."""
    assert sporttery.zh_to_canonical("坦佩雷山猫") == "Ilves"            # Tampere Lynx
    assert sporttery.zh_to_canonical("赫尔辛基火花") == "Gnistan"        # Helsinki Spark
    assert sporttery.zh_to_canonical("国际图尔库") == "Inter Turku"
    assert sporttery.zh_to_canonical("AC奥卢") == "AC Oulu"


def test_kleague_zh_override():
    """韩职 — 竞彩挂出 7-4/7-5 SP 但 6 个队名不在字典 → 每场恰好半边失配 → 6/6 场
    被 ingest 静默丢弃 (体检 2026-07-03)。对照 KOR_K_LEAGUE_1 gather 真实拼写补齐;
    济州SK 是俱乐部改名,API-Football 仍叫 Jeju United FC。"""
    assert sporttery.zh_to_canonical("安养FC") == "FC Anyang"
    assert sporttery.zh_to_canonical("富川FC") == "Bucheon FC 1995"
    assert sporttery.zh_to_canonical("江原FC") == "Gangwon FC"
    assert sporttery.zh_to_canonical("首尔FC") == "FC Seoul"
    assert sporttery.zh_to_canonical("光州FC") == "Gwangju FC"
    assert sporttery.zh_to_canonical("济州SK") == "Jeju United FC"
    # 之前就映射成功的一侧不受影响
    assert sporttery.zh_to_canonical("浦项制铁") == "Pohang Steelers"


def test_harvest_protect_manual_toggle(tmp_path):
    """The cron (protect_manual=True) preserves a hand-priced row; the 🎯 刷新竞彩
    endpoint (protect_manual=False) overwrites the stale market_mode capture with the
    latest official SP — otherwise the button fetches fresh data but can't show it."""
    from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
    from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup, record_jingcai_sp
    db = str(tmp_path / "obs.db")
    key = ("2026-06-20", "Mexico", "South Africa")
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.70, jc_draw=3.4, jc_away=4.5,
                      market="had", source="market_mode")        # stale hand-capture
    fresh = [{"home_en": "Mexico", "away_en": "South Africa", "league_cn": "WC",
              "match_date": "2026-06-20", "kickoff_utc": None,
              "had": (1.60, 3.5, 4.7), "hhad": None}]
    harvest_to_db(db, matches=fresh, protect_manual=True)         # cron: blocked
    assert fetch_sp_lookup(db, market="had")[key][0] == 1.70
    harvest_to_db(db, matches=fresh, protect_manual=False)        # 🎯: overwrites
    assert fetch_sp_lookup(db, market="had")[key][0] == 1.60


def test_attach_jingcai_sp_normalizes_team_names(tmp_path, monkeypatch):
    """市场模式/近期赛事 boards key on API-Football names ('Czechia'), but jingcai_sp
    stores the sporttery/Odds-API spelling ('Czech Republic'). _attach_jingcai_sp must
    normalize both sides so the SP pre-fill still joins — else the 竞彩 SP boxes stay
    empty (the bug seen on 捷克 vs 南非, 2026-06-19)."""
    import datetime

    from nutmeg.v4.api import routes
    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-18", home_team="Czech Republic",
                      away_team="South Africa", jc_home=1.66, jc_draw=3.6, jc_away=4.35,
                      market="had", source="sporttery")
    monkeypatch.setattr(routes, "_observation_db_path", lambda: db)

    class _Pred:
        date = datetime.date(2026, 6, 18)
        home_team = "Czechia"            # API-Football spelling, diverges from jingcai_sp
        away_team = "South Africa"
        jc_home = jc_draw = jc_away = jc_source = None
        jc_hc_home = jc_hc_draw = jc_hc_away = jc_hc_line = None

    p = _Pred()
    routes._attach_jingcai_sp([p])
    assert p.jc_home == 1.66 and p.jc_away == 4.35  # joined across Czechia↔Czech Republic


def test_fail_soft_returns_empty(monkeypatch):
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: None)
    assert sporttery.fetch_lottery_matches() == []


def test_incomplete_odds_dropped(monkeypatch):
    bad = {"success": True, "value": {"matchInfoList": [{"subMatchList": [
        {"homeTeamAllName": "墨西哥", "awayTeamAllName": "南非", "matchDate": "2026-06-12",
         "had": {"h": "1.26"}, "hhad": None},   # incomplete had, no hhad
    ]}]}}
    monkeypatch.setattr(sporttery, "_request", lambda *a, **k: bad)
    m = sporttery.fetch_lottery_matches()[0]
    assert m["had"] is None and m["hhad"] is None


class TestOdds3SanityGuard:
    """体检 A3 (2026-07-01) — 竞彩 SP is the ×SP term in EV; a freeze/placeholder
    artifact ('0'/'999') must not be stored as a real odds line (real SP: 1.13–13.5)."""

    def test_valid_pool_parses(self):
        assert sporttery._odds3({"h": "1.85", "d": "3.4", "a": "4.2"}) == (1.85, 3.4, 4.2)

    def test_rejects_sub_unity(self):
        assert sporttery._odds3({"h": "0", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "1.0", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "0.3", "d": "3.4", "a": "4.2"}) is None

    def test_rejects_absurd(self):
        assert sporttery._odds3({"h": "1.85", "d": "3.4", "a": "9999"}) is None

    def test_rejects_negative_and_nonnumeric(self):
        assert sporttery._odds3({"h": "-2", "d": "3.4", "a": "4.2"}) is None
        assert sporttery._odds3({"h": "x", "d": "3.4", "a": "4.2"}) is None

    def test_incomplete_pool_is_none(self):
        assert sporttery._odds3(None) is None
        assert sporttery._odds3({"h": "1.85"}) is None


class TestVotePagination:
    """体检 Wave2 — getVoteV1 pagination: the single-page-of-50 read dropped
    every match past #50 on a big autumn Saturday (forward-only loss)."""

    def _resp(self, ids, pages):
        return {"success": True,
                "value": {"matches": {"list": [{"matchId": i} for i in ids],
                                      "pages": pages, "total": None}}}

    def test_fetches_all_pages_and_dedups(self, monkeypatch):
        import httpx

        from nutmeg.v4.data.sources import sporttery
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append(params["pageNo"])
            body = self._resp([1, 2], 3) if params["pageNo"] == 1 else (
                self._resp([2, 3], 3) if params["pageNo"] == 2 else self._resp([4], 3))

            class R:
                status_code = 200   # 真 httpx.Response 必有;2026-07-20 WAF 熔断读它

                def raise_for_status(self):
                    pass

                def json(self):
                    return body
            return R()

        monkeypatch.setattr(httpx, "get", fake_get)
        rows = sporttery.fetch_vote_support("HAD", page_size=2)
        assert calls == [1, 2, 3]
        assert [r["matchId"] for r in rows] == [1, 2, 3, 4]  # dup id=2 dropped

    def test_mid_pagination_failure_returns_partial(self, monkeypatch):
        import httpx

        from nutmeg.v4.data.sources import sporttery

        def fake_get(url, params=None, headers=None, timeout=None):
            if params["pageNo"] > 1:
                raise RuntimeError("page 2 down")

            class R:
                status_code = 200   # 真 httpx.Response 必有;2026-07-20 WAF 熔断读它

                def raise_for_status(self):
                    pass

                def json(self2):
                    return self._resp([1, 2], 5)
            return R()

        monkeypatch.setattr(httpx, "get", fake_get)
        rows = sporttery.fetch_vote_support("HAD", page_size=2, retries=1)
        assert [r["matchId"] for r in rows] == [1, 2]  # partial > nothing


class TestUnmappedSentinel:
    """未映射队名主动上报 — 整场丢弃是对的(无 EN 名 join 不了 Pinnacle),但要留下
    持久、可查的痕迹。2026-07-07 欧冠资格赛 2/3 场因队名未映射被静默丢:报警其实
    在 open cron 触发了,却只进无头 launchd 的桌面推送 + 没人读的 out.log,靠人肉
    发现「近期赛事」少了场。这些测试锁死 sink 层的持久报告 + health_check 契约。"""

    def _m(self, home_en, away_en, league, home_cn, away_cn):
        return {"home_en": home_en, "away_en": away_en, "league_cn": league,
                "home_cn": home_cn, "away_cn": away_cn, "had": None, "hhad": None}

    def test_partial_majority_loss_flagged(self):
        """今日真实场景:3 场欧冠,2 场队名未映射 → 过半丢失报警(单场存活的「半坏」
        盲区不再让它静默:体检 2026-07-04 瑞超 6/7)。"""
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        s = summarize_unmapped([
            self._m("FC Copenhagen", "Drita", "欧冠", "哥本哈根", "德里塔"),
            self._m(None, None, "欧冠", "克拉克斯维克", "比森阿泰尔"),
            self._m(None, "X", "欧冠", "雷克雅未克维京人", "杰尔"),
        ])
        assert len(s["unmapped"]) == 2
        assert s["gone"] == []
        assert s["partial"] == ["欧冠 2/3"]
        assert s["alarm_bits"] == ["过半丢失: 欧冠 2/3"]

    def test_whole_league_gone_flagged(self):
        """整联赛全部未映射(韩职 6/6 类)→ gone 报警,不重复计过半。"""
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        s = summarize_unmapped(
            [self._m(None, None, "韩职", f"主{i}", f"客{i}") for i in range(3)])
        assert s["gone"] == ["韩职"]
        assert s["partial"] == []
        assert s["alarm_bits"] == ["整联赛丢失: 韩职"]

    def test_single_drop_below_threshold_recorded_not_alarmed(self):
        """1/6 未映射 < 过半阈值 → 记入 unmapped(报告里可见)但不弹桌面报警。"""
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        ms = [self._m("A", "B", "英超", "甲", "乙") for _ in range(5)]
        ms.append(self._m(None, "B", "英超", "丙", "丁"))
        s = summarize_unmapped(ms)
        assert len(s["unmapped"]) == 1
        assert s["gone"] == [] and s["partial"] == [] and s["alarm_bits"] == []

    def test_all_mapped_is_empty(self):
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        s = summarize_unmapped([self._m("A", "B", "WC", "甲", "乙")])
        assert s["unmapped"] == [] and s["alarm_bits"] == []

    def test_report_line2_is_health_check_contract(self):
        """health_check.sh §11 用 `sed -n 2p` + 正则 `未映射 (N) 场` 解析计数,并用
        `grep -E '^\\s*\\['` 抓明细行 — 锁死这两个契约,别在 render 里改坏。"""
        import re

        from nutmeg.v4.cli.ingest_sporttery import (
            render_unmapped_report,
            summarize_unmapped,
        )
        ms = [
            self._m("A", "B", "欧冠", "甲", "乙"),
            self._m(None, None, "欧冠", "丙", "丁"),
            self._m(None, None, "欧冠", "戊", "己"),
        ]
        rep = render_unmapped_report(summarize_unmapped(ms), "2026-07-07 11:05", len(ms))
        line2 = rep.splitlines()[1]
        assert re.search(r"未映射 (\d+) 场", line2).group(1) == "2"
        assert any(re.match(r"^\s*\[", ln) for ln in rep.splitlines())

    def test_report_clean_reports_zero(self):
        import re

        from nutmeg.v4.cli.ingest_sporttery import (
            render_unmapped_report,
            summarize_unmapped,
        )
        rep = render_unmapped_report(
            summarize_unmapped([self._m("A", "B", "WC", "甲", "乙")]),
            "2026-07-07 23:15", 1)
        assert re.search(r"未映射 (\d+) 场", rep.splitlines()[1]).group(1) == "0"
        assert "✅" in rep

    def test_harvest_persists_report_at_sink(self, tmp_path):
        """sink 层持久化:harvest_to_db 把未映射写到 <repo>/logs/sporttery_unmapped_latest.txt
        (repo 根由 db 路径反推 data/ 上一级)。cron 和 🎯 刷新按钮两条路都会写 —
        旧代码报警只在 CLI main(),按钮路完全无痕。"""
        from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
        (tmp_path / "data").mkdir()
        db = str(tmp_path / "data" / "obs.db")   # 嵌套 ⇒ repo 根=tmp_path, 报告落 tmp_path/logs
        matches = [
            {"home_en": "Mexico", "away_en": "South Africa", "league_cn": "欧冠",
             "match_date": "2026-07-07", "kickoff_utc": None,
             "home_cn": "墨西哥", "away_cn": "南非", "had": (1.7, 3.4, 4.5), "hhad": None},
            {"home_en": None, "away_en": None, "league_cn": "欧冠",
             "home_cn": "克拉克斯维克", "away_cn": "比森阿泰尔",
             "match_date": "2026-07-07", "had": (2.0, 3.0, 3.5), "hhad": None},
        ]
        r = harvest_to_db(db, matches=matches)
        assert r["unmapped"] == 1
        assert r["unmapped_teams"] == [
            {"home_cn": "克拉克斯维克", "away_cn": "比森阿泰尔", "league_cn": "欧冠"}]
        report = tmp_path / "logs" / "sporttery_unmapped_latest.txt"
        assert report.exists()
        text = report.read_text(encoding="utf-8")
        assert "未映射 1 场" in text.splitlines()[1]
        assert "克拉克斯维克 / 比森阿泰尔" in text

    def test_harvest_empty_fetch_keeps_prior_report(self, tmp_path):
        """抓取失败(0 场)绝不能把上次报告洗成 ✅ 假绿 — 留旧报告不动;那种漏由
        data_freshness「jingcai_sp 停长」另行报警。"""
        from nutmeg.v4.cli.ingest_sporttery import harvest_to_db
        (tmp_path / "data").mkdir()
        db = str(tmp_path / "data" / "obs.db")
        report = tmp_path / "logs" / "sporttery_unmapped_latest.txt"
        report.parent.mkdir()
        report.write_text("上次报告\n未映射 2 场\n", encoding="utf-8")
        r = harvest_to_db(db, matches=[])
        assert r["matches"] == 0
        assert report.read_text(encoding="utf-8") == "上次报告\n未映射 2 场\n"
