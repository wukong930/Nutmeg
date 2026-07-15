"""验证防覆盖闸:模拟「有好缓存 + 抓取返回空」→ 好数据必须活下来。"""
import pandas as pd, pytest
from pathlib import Path
from nutmeg.v4.data.sources import clubelo

def test_empty_fetch_does_not_clobber_good_cache(tmp_path, monkeypatch):
    p = clubelo.cache_path("Ajax", tmp_path)
    good = pd.DataFrame({"team_canonical":["Ajax"],"clubelo_slug":["Ajax"],"country":["NED"],
                         "elo":[1800.0],"from_date":["2026-05-31"],"to_date":["2026-12-31"]})
    good.to_parquet(p, index=False)
    # 模拟限流:返回空 frame
    monkeypatch.setattr(clubelo, "fetch_team_history",
                        lambda team, client=None: clubelo._empty_history_frame(team, "Ajax"))
    clubelo.ingest_teams(["Ajax"], cache_dir=tmp_path, refresh=True, throttle_seconds=0)
    after = pd.read_parquet(p)
    assert len(after) == 1 and after.iloc[0]["elo"] == 1800.0, "好数据被空结果冲掉了!"

def test_empty_fetch_still_writes_when_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(clubelo, "fetch_team_history",
                        lambda team, client=None: clubelo._empty_history_frame(team, "X"))
    clubelo.ingest_teams(["NewTeam"], cache_dir=tmp_path, refresh=True, throttle_seconds=0)
    assert clubelo.cache_path("NewTeam", tmp_path).exists()   # 首次仍要落盘(标记已试过)
