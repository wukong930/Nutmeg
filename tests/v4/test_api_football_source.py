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
