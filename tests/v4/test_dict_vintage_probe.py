"""🔁 活 API 的队名词典**是不是源码那一代** —— 「改了没重启」的结构约束。

## 病史(同一个坑第二次)

2026-09-15 横幅点名 3 场竞彩比赛「队名解不出」,而其中 **2 场的映射前一天就已提交**
(`叻武里`/`北京国安`)。源码解得出、**活进程解不出** —— 那批只走了「提交 / 推送」,
没走「重启」,而 `_ZH_TO_EN` 是 **import 时建表**、uvicorn 无 `--reload`。

🚨 症状是「横幅在点已经修好的名字」,而它和「真的还没修」**长得一模一样** ——
照着横幅去补,只会往词典里加已经存在的条目。

⭐ 这条纪律已经写在**两处注释**里(横幅端点的 docstring、横幅正文的 ⚠️),仍然复发。
   ⇒ 按 `discipline-belongs-in-the-tool`:**口头说第二遍的纪律该变成代码里的拒绝**。

## 判据:同缓存 · 同纯函数 · 两个进程(零代理)

  · 源码侧:本进程 `fetch_lottery_matches(refresh=False, ttl_seconds=10**9)`
    —— **只认缓存、绝不发请求** —— 再过 `summarize_unmapped`
  · daemon 侧:`GET /observation/jingcai-unmapped`,它读**同一个缓存文件**、
    调**同一个纯函数**

`home_en` 由 `fetch_lottery_matches` 在**读取时**用进程内词典填 ⇒ 同输入同代码,
两边不同**只可能**是词典代次不同。⛔ 不是「数条目数」那种语法代理。

## 两条判据,严重程度不同

① daemon 解不出而源码解得出 ⇒ **报警**(会被看见的缺陷)
② 条目数不等但在售场次不受影响 ⇒ 只报 info(已提交未生效,今天没人看得见)——
   同 `statistics-on-the-bettable-population`:统计量要算在会被看见的人口上。
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from nutmeg.v4.cli import data_freshness as df

from .test_data_freshness import OUTBOUND, offline


def _m(h, a, lg="日职", ok=True):
    """一条竞彩场次;`ok=False` = 本进程解不出(home_en/away_en 为空)。"""
    return {"home_cn": h, "away_cn": a, "league_cn": lg,
            "home_en": (h + "-EN") if ok else None,
            "away_en": (a + "-EN") if ok else None}


@pytest.fixture
def wire(monkeypatch):
    """打桩两侧:`src` = 本进程看到的场次;`live` = daemon 端点返回的 JSON。"""
    state = {"src": [], "live": {}, "dict": {}, "calls": [], "boom": None}

    def fake_fetch(**kw):
        # ⭐ 钉住「只认缓存」:端点和探针都必须传极大 ttl、refresh=False
        state["calls"].append(kw)
        return state["src"]

    from nutmeg.v4.data.sources import sporttery as sp
    monkeypatch.setattr(sp, "fetch_lottery_matches", fake_fetch)
    monkeypatch.setattr(df, "_API_BASE", "http://stub")

    class _Resp:
        def __init__(self, payload): self._p = json.dumps(payload).encode()
        def read(self): return self._p
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        if state["boom"]:
            raise state["boom"]
        url = req.full_url if hasattr(req, "full_url") else str(req)
        state["calls"].append(url)
        return _Resp(state["live"] if "jingcai-unmapped" in url else state["dict"])

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    return state


def _live(unmapped, ok=True):
    return {"ok": ok, "n_matches": 99,
            "unmapped": [{"home_cn": h, "away_cn": a, "league_cn": "日职"}
                         for h, a in unmapped]}


class TestTheActualBug:
    def test_daemon_behind_source_alarms_and_prescribes_restart(self, wire):
        """🚨 2026-09-15 那次的形状:源码全解得出,daemon 还在点两场。"""
        wire["src"] = [_m("叻武里", "上海海港"), _m("北京国安", "浦项制铁"),
                       _m("科莫", "帕尔马")]
        wire["live"] = _live([("叻武里", "上海海港"), ("北京国安", "浦项制铁")])
        wire["dict"] = {f"T{i}": f"队{i}" for i in range(1085)}
        info, alarms = df.check_dict_vintage()
        assert alarms, f"daemon 比源码旧却不报警;info={info}"
        a = alarms[0]
        assert "比源码旧" in a and "2 场" in a
        assert "叻武里vs上海海港" in a, "报警必须点名是哪几场(否则人不知道去查什么)"
        assert "重启" in a and "kickstart" in a, "处方没给可执行的重启命令"

    def test_green_when_both_sides_agree(self, wire):
        wire["src"] = [_m("科莫", "帕尔马")]
        wire["live"] = _live([])
        wire["dict"] = {f"T{i}": f"队{i}" for i in range(10)}
        info, alarms = df.check_dict_vintage()
        assert not alarms, alarms
        # 人口非平凡:确认它**确实**两边都问过了
        assert any("在售 1 场" in x for x in info), info

    def test_reverse_direction_says_do_not_restart(self, wire):
        """⛔ 源码解不出而 daemon 解得出 = 映射被删/改坏,**重启只会让情况更糟**。

        没有这条,处方会把一次源码回归误导成一次重启。
        """
        wire["src"] = [_m("张三", "李四", ok=False)]
        wire["live"] = _live([])
        wire["dict"] = {}
        info, alarms = df.check_dict_vintage()
        assert alarms and "别重启" in alarms[0], alarms
        assert "git log" in alarms[0]


class TestSeverityIsGraded:
    def test_size_mismatch_without_visible_impact_is_info_only(self, wire):
        """已提交未生效、但当前在售场次不受影响 ⇒ 提醒,不报警。"""
        wire["src"] = [_m("科莫", "帕尔马")]
        wire["live"] = _live([])
        wire["dict"] = {f"T{i}": f"队{i}" for i in range(3)}
        monkey = pytest.MonkeyPatch()
        monkey.setattr(df, "_API_BASE", "http://stub")
        info, alarms = df.check_dict_vintage()
        monkey.undo()
        assert not alarms, "条目数不等但没人看得见,不该报警"
        assert any("条目数不等" in x and "只提醒不报警" in x for x in info), info


class TestFailSoftSaysUncheckedNotClean:
    """⚠️「查不了」和「没漂移」必须分开 —— 本仓反复踩过的那一类。"""

    def test_api_unreachable_is_unchecked(self, wire):
        wire["src"] = [_m("科莫", "帕尔马")]
        wire["boom"] = urllib.error.URLError("refused")
        info, alarms = df.check_dict_vintage()
        assert not alarms, "取不到 API 不该报成漂移"
        assert any("未查" in x for x in info), info
        assert any("不等于「没漂移」" in x for x in info), "没说清「查不了≠没问题」"
        # 人口非平凡:证明它**确实**试过了,否则「不报警」空洞为真
        assert wire["calls"], "根本没去请求就断言 fail-soft"

    def test_no_cache_is_unchecked(self, wire):
        wire["src"] = []
        info, alarms = df.check_dict_vintage()
        assert not alarms and any("未查" in x for x in info), (info, alarms)

    def test_endpoint_not_ok_is_unchecked(self, wire):
        wire["src"] = [_m("科莫", "帕尔马")]
        wire["live"] = {"ok": False, "reason": "读取竞彩缓存失败"}
        info, alarms = df.check_dict_vintage()
        assert not alarms and any("未查" in x for x in info), (info, alarms)


class TestItOnlyReadsTheCache:
    def test_never_issues_a_live_sporttery_request(self, wire):
        """⭐ 探针跑在 2×/天 的哨兵里。它**绝不能**去打竞彩官网 ——
        那既不礼貌,也会让体检的行为依赖外网。"""
        wire["src"] = [_m("科莫", "帕尔马")]
        wire["live"] = _live([])
        wire["dict"] = {}
        df.check_dict_vintage()
        kw = [c for c in wire["calls"] if isinstance(c, dict)]
        assert kw, "根本没调 fetch_lottery_matches"
        assert kw[0].get("refresh") is False, f"refresh 不是 False:{kw[0]}"
        assert kw[0].get("ttl_seconds", 0) >= 10**8, f"ttl 太小会触发真抓取:{kw[0]}"


class TestWiredIntoTheSentinel:
    _ARGS = ("--today", "2026-06-17", *offline("--no-vintage"))

    def _green_db(self, tmp_path):
        from .test_data_freshness import _all_today, _mk_db
        return _mk_db(tmp_path, _all_today())

    def test_alarm_drives_nonzero_exit_and_names_its_kind(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_dict_vintage", lambda *a, **k: ([], []))
        assert df.main(["--db", str(db), *self._ARGS]) == 0, \
            "对照不成立 —— 基线就不是绿的:\n" + capsys.readouterr().out[-800:]
        capsys.readouterr()
        monkeypatch.setattr(df, "check_dict_vintage", lambda *a, **k: ([], ["合成:词典未生效"]))
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert rc == 1, "没有驱动非零退出"
        assert "合成:词典未生效" in out
        assert "词典未生效" in out.split("报警类别: ")[-1], "类别行没点名它"

    def test_probe_crash_becomes_an_alarm(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)

        def boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(df, "check_dict_vintage", boom)
        rc = df.main(["--db", str(db), *self._ARGS])
        assert rc == 1 and "词典代次探针自己炸了" in capsys.readouterr().out

    def test_no_vintage_flag_skips_it(self, monkeypatch, capsys, tmp_path):
        db = self._green_db(tmp_path)
        monkeypatch.setattr(df, "check_dict_vintage", lambda *a, **k: ([], ["合成:不该出现"]))
        rc = df.main(["--db", str(db), *self._ARGS, "--no-vintage"])
        assert rc == 0 and "合成:不该出现" not in capsys.readouterr().out


class TestTheSentinelStaysHermeticUnderTestFlags:
    """🚨 2026-09-16 —— 我接这个探针时漏了第 12 条腿:**既有测试的参数表**。

    ## 病史

    `check_dict_vintage` 是哨兵里**第一个默认就往进程外发请求**的探针
    (其余探针读合成 DB / 本地文件,天然 hermetic;`--no-quota` 那个也出站,
     但既有测试早就关掉了它)。

    接线当天全绿 —— 因为当时活 daemon 恰好和源码同代。两天后我改了词典还没重启,
    探针**正确地**报警,于是 **10 条与它无关的体检测试一起红**,报错指向
    「存档没写」「健康轮造不出来」这类**错误的地方**。

    ⇒ 不是探针的错,是我漏了那条腿。但「下次别忘」不是修法 ——
      按 [[discipline-belongs-in-the-tool]],做成一条**中心化的守卫**。

    ## 不变量

    哨兵在**测试参数**下跑一轮,**一个出站请求都不该发**。
    任何未来的出站探针(或某条测试忘了关它)都会在这里一次性被抓住,
    而不是散落成十条指向别处的假红。

    ## 2026-09-23 —— 它抓到了第三个出站探针,而主树里一直看不见

    赛季探针(09-11)本地缺当季源树就去问 football-data。主树里 `2627/` 在
    ⇒ 零请求 ⇒ 这条一直绿 —— **又是运气**(同上:活 daemon 恰好同代)。
    从 worktree 跑(源树只到 `2526/`)它就红了:13 次出站。
    ⇒ 修的是**参数表**:`--no-season` 进 `OUTBOUND`,全仓的调用方一起拿到;
      断言一字未动,其余探针仍全开着跑,谁出站照样红在这里。
    ⚠️ 这条的检出力**取决于跑在什么树上**:条件出站(缺数据才问上游)的探针,
       只在数据缺的环境里现形 —— 「主树里绿」不是「没出站路径」的证据。
    """

    _ARGS = ("--today", "2026-06-17", *OUTBOUND)

    def test_a_sentinel_round_issues_no_outbound_request(self, monkeypatch, tmp_path, capsys):
        from .test_data_freshness import _all_today, _mk_db

        calls: list[str] = []

        def boom(req, *a, **k):
            url = getattr(req, "full_url", str(req))
            calls.append(url)
            raise AssertionError(f"哨兵在测试参数下发了出站请求:{url}")

        monkeypatch.setattr("urllib.request.urlopen", boom)
        # httpx / requests 走别的栈 —— 一并堵上,别只堵一个就以为覆盖了
        for mod, attr in (("httpx", "get"), ("httpx", "post")):
            try:
                m = __import__(mod)
                monkeypatch.setattr(m, attr, boom, raising=False)
            except Exception:  # noqa: BLE001
                pass

        db = _mk_db(tmp_path, _all_today())
        rc = df.main(["--db", str(db), *self._ARGS])
        out = capsys.readouterr().out
        assert not calls, f"发了 {len(calls)} 个出站请求:{calls[:3]}"
        # 人口非平凡:确认它**真的跑了一整轮**,不是提前退出让断言空洞为真
        assert "判定" in out or "报警类别" in out, f"没跑完一轮,这条测不出东西:\n{out[-600:]}"
        assert rc in (0, 1)

    def test_the_flag_actually_exists_and_is_spelled_as_used(self):
        """⭐ 上面那条靠传 `OUTBOUND` 才 hermetic。拼错了会被 argparse 拒绝 ——
        但如果将来改名而这里没跟着改,上面那条会**报参数错**而不是漏测,
        所以这里单独钉住名字。"""
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            with pytest.raises(SystemExit):
                df.main(["--help"])
        for flag in OUTBOUND:
            assert flag in buf.getvalue(), flag
