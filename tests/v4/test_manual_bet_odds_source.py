"""📌「记此注」必须把赔率**出处**一路带到库里(2026-08-07 P0-6)。

## 断点在哪

前端从 `a06476a` 起就一直在送 `odds_source`(`dashboard.html` 里
`odds_source: pr.odds_source ?? null`),后半段链路也一直是通的 ——
`record_manual_bet` 把 `bet` 当 request 传给 `insert_session`,后者调
`store._request_odds_source(request)` 读的正是这个键。

**唯一的断点是 `ManualBetRequest` 没声明这个字段** ⇒ Pydantic 默认静默丢弃
未声明字段 ⇒ 它从来没到过 recorder。前端送了、后端读了,中间那一层把它吃掉了,
而且**不报错**。

## 为什么这条不能只靠「读代码看着对」

`a06476a` 的提交信息里我写了「`_recordBet` 补 `odds_source`」—— 前端确实补了,
我也确实检查了前端。但没有人端到端跑一次看**库里那一列**。
「送了」和「存下来了」是两件事,中间隔着一个会静默吞字段的 schema。

## 为什么缺省必须是 NULL 而不是 'api_football'

`store._request_odds_source` 的 docstring 写死了这条:
「全部缺失 → None(不知道),**绝不默认成 'api_football'** —— 那等于把
『没告诉我』伪装成『我查过了』」。这里有一条反向断言守它。
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api.routes import router as v4_router
from nutmeg.v4.observation.store import init_db


@pytest.fixture
def client_db(tmp_path, monkeypatch):
    db = tmp_path / "obs.db"
    init_db(db)
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app), db


def _bet(**over):
    b = {
        "league": "JPN_J1", "date": "2026-08-10",
        "home_team": "Kashima", "away_team": "Urawa",
        "market_type": "1x2", "outcome": "H",
        "odds": 2.10, "probability": 0.52, "stake": 20.0,
        "bankroll": 1000.0, "record_session": True,
    }
    b.update(over)
    return b


def _stored_source(db) -> str | None:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT odds_source FROM recommendation_sessions ORDER BY session_id DESC LIMIT 1"
        ).fetchone()[0]


@pytest.mark.parametrize("src", ["manual", "odds_api", "api_football"])
def test_odds_source_reaches_the_database(client_db, src):
    """⭐ 承重条:送什么,库里就得是什么。

    这条红 = schema 又把字段吃了(或路由没往 bet dict 里放)。
    """
    client, db = client_db
    r = client.post("/api/v4/observation/record-bet", json=_bet(odds_source=src))
    assert r.status_code == 200, r.text
    assert r.json()["recorded"] is True
    assert _stored_source(db) == src, f"送了 {src!r},库里却是 {_stored_source(db)!r}"


def test_missing_odds_source_is_stored_as_null_not_guessed(client_db):
    """⛔ 反向红线:没送 ⇒ 库里必须是 NULL。

    `store._request_odds_source` 的 docstring:「全部缺失 → None(不知道),
    **绝不默认成 'api_football'**」。把「没告诉我」写成任何一个具体来源,
    都会让秋季按来源切片时把一批身份不明的注算进某一类。
    """
    client, db = client_db
    r = client.post("/api/v4/observation/record-bet", json=_bet())
    assert r.status_code == 200, r.text
    got = _stored_source(db)
    assert got is None, f"没送出处,库里却填了 {got!r} —— 把「不知道」伪装成了「查过了」"


def test_handicap_bets_carry_it_too(client_db):
    """让球那条路走的是同一个端点,但参数形状不同 —— 单独钉一次。"""
    client, db = client_db
    r = client.post("/api/v4/observation/record-bet", json=_bet(
        market_type="handicap", handicap_home=-1, odds_source="manual"))
    assert r.status_code == 200, r.text
    assert _stored_source(db) == "manual"
