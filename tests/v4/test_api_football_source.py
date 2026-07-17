"""体检 Wave2 — api_football source-layer cache semantics."""
from __future__ import annotations


class TestEmptyTeamsCacheTTL:
    """体检 Wave2 — an empty [] /teams cache for a current season is "not
    published yet", not truth (TUR/AUS 2026 cached as [] forever → the autumn
    dict-coverage diff would get a fake green light)."""

    def _setup_cache(self, tmp_path, content, age_hours):
        import json as _json
        import os
        import time
        from datetime import UTC, datetime

        import nutmeg.v4.data.sources.api_football as af
        season = af.season_for_date(datetime.now(UTC).date(), "EPL")
        params = {"league": af.league_id("EPL"), "season": season}
        cf = af._cache_path("/teams", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(_json.dumps(content))
        old = time.time() - age_hours * 3600
        os.utime(cf, (old, old))
        return af, season

    def test_stale_empty_cache_refetches(self, tmp_path, monkeypatch):
        af, season = self._setup_cache(tmp_path, [], age_hours=8)
        calls = []

        def fake_request(endpoint, params, *, cache_dir, refresh=False):
            calls.append(refresh)
            return [{"team": {"name": "X"}}]
        monkeypatch.setattr(af, "_request", fake_request)
        out = af.fetch_teams_for_league_season("EPL", season, cache_dir=tmp_path)
        assert calls == [True], "stale EMPTY current-season cache must force-refresh"
        assert out and out[0]["team"]["name"] == "X"

    def test_stale_nonempty_cache_stays_permanent(self, tmp_path, monkeypatch):
        af, season = self._setup_cache(
            tmp_path, [{"team": {"name": "Cached"}}], age_hours=8)
        calls = []

        def fake_request(endpoint, params, *, cache_dir, refresh=False):
            calls.append(refresh)
            import json as _json
            cf = af._cache_path(endpoint, params, tmp_path)
            return _json.loads(cf.read_text())
        monkeypatch.setattr(af, "_request", fake_request)
        out = af.fetch_teams_for_league_season("EPL", season, cache_dir=tmp_path)
        assert calls == [False], "a POPULATED roster cache is truth — no refetch"
        assert out[0]["team"]["name"] == "Cached"

    def test_past_season_empty_cache_stays_permanent(self, tmp_path, monkeypatch):
        import json as _json

        import nutmeg.v4.data.sources.api_football as af
        params = {"league": af.league_id("EPL"), "season": 2019}
        cf = af._cache_path("/teams", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(_json.dumps([]))
        import os
        import time
        old = time.time() - 8 * 3600
        os.utime(cf, (old, old))
        calls = []

        def fake_request(endpoint, params, *, cache_dir, refresh=False):
            calls.append(refresh)
            return []
        monkeypatch.setattr(af, "_request", fake_request)
        af.fetch_teams_for_league_season("EPL", 2019, cache_dir=tmp_path)
        assert calls == [False], "historical seasons never auto-refresh"


class TestOddsEmptyRefetchGuard:
    """体检 2026-07-17(挪超 Bodo/Glimt 消失案)— 「空的成功也是失败」。

    AF 临近开赛下架赛前赔率;到龄重拉(体检 F1 的 2h 防陈旧)恰好落进下架窗口
    时拿回 [],旧实现把它写缓存 ⇒ 好线被静默冲掉 → fixture 掉待开盘 → 竞彩 SP
    不 join → 可投注区在**下注窗口**抹掉场次。实锤:_odds/f314942788e0.json
    (fixture 1494700)21:10:11 被覆盖成 2 字节 `[]`。守卫 = 重拉无价且旧缓存
    有价 ⇒ 恢复旧缓存照常返回。同族:clubelo 空 body 闸、上面的空队表 TTL。
    """

    _GOOD = [{"fixture": {"id": 1494700},
              "bookmakers": [{"name": "Pinnacle", "bets": []}]}]

    def _seed(self, tmp_path, content, age_hours=3.0):
        import json as _json
        import os
        import time

        import nutmeg.v4.data.sources.api_football as af
        cf = af._cache_path("/odds", {"fixture": 1494700}, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(_json.dumps(content))
        old = time.time() - age_hours * 3600
        os.utime(cf, (old, old))
        return af, cf

    def _fake_request(self, af, tmp_path, returns):
        # 复刻真实 _request 的关键副作用:refresh=True 会把响应写进缓存 ——
        # 守卫必须在这之后把好内容**恢复**回来,测试才证明了恢复而非「没写」。
        import json as _json
        calls = []

        def fake(endpoint, params, *, cache_dir, refresh=False):
            calls.append(refresh)
            cf = af._cache_path(endpoint, params, tmp_path)
            if refresh:
                cf.write_text(_json.dumps(returns))
                return returns
            return _json.loads(cf.read_text())
        return fake, calls

    def test_stale_refetch_empty_keeps_prior_cache(self, tmp_path, monkeypatch):
        import json as _json
        af, cf = self._seed(tmp_path, self._GOOD)
        fake, calls = self._fake_request(af, tmp_path, returns=[])
        monkeypatch.setattr(af, "_request", fake)
        out = af.fetch_odds(1494700, cache_dir=tmp_path, max_age_seconds=3600)
        assert calls == [True], "到龄必须重拉"
        assert out == self._GOOD, "空响应 → 返回旧的好线"
        assert _json.loads(cf.read_text()) == self._GOOD, "缓存文件必须被恢复"

    def test_explicit_refresh_empty_also_guarded(self, tmp_path, monkeypatch):
        import json as _json
        af, cf = self._seed(tmp_path, self._GOOD, age_hours=0.1)
        fake, _ = self._fake_request(af, tmp_path, returns=[])
        monkeypatch.setattr(af, "_request", fake)
        out = af.fetch_odds(1494700, cache_dir=tmp_path, refresh=True)
        assert out == self._GOOD, "🔄 撞上下架窗口同样不该把好线丢掉"
        assert _json.loads(cf.read_text()) == self._GOOD

    def test_bookmakerless_husk_counts_as_empty(self, tmp_path, monkeypatch):
        af, cf = self._seed(tmp_path, self._GOOD)
        husk = [{"fixture": {"id": 1494700}, "bookmakers": []}]
        fake, _ = self._fake_request(af, tmp_path, returns=husk)
        monkeypatch.setattr(af, "_request", fake)
        out = af.fetch_odds(1494700, cache_dir=tmp_path, max_age_seconds=3600)
        assert out == self._GOOD, "有壳无价 = 零价,同样触发守卫"

    def test_fresh_nonempty_overwrites_normally(self, tmp_path, monkeypatch):
        import json as _json
        af, cf = self._seed(tmp_path, self._GOOD)
        newer = [{"fixture": {"id": 1494700},
                  "bookmakers": [{"name": "Pinnacle", "bets": [{"name": "Match Winner"}]}]}]
        fake, _ = self._fake_request(af, tmp_path, returns=newer)
        monkeypatch.setattr(af, "_request", fake)
        out = af.fetch_odds(1494700, cache_dir=tmp_path, max_age_seconds=3600)
        assert out == newer, "有价的新响应照常生效"
        assert _json.loads(cf.read_text()) == newer, "守卫不许妨碍正常刷新"

    def test_no_prior_prices_empty_passes_through(self, tmp_path, monkeypatch):
        af, cf = self._seed(tmp_path, [])   # 旧缓存本来就空 → 无可保护
        fake, _ = self._fake_request(af, tmp_path, returns=[])
        monkeypatch.setattr(af, "_request", fake)
        out = af.fetch_odds(1494700, cache_dir=tmp_path, max_age_seconds=3600)
        assert out == []
