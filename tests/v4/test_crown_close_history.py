"""crown_close_history record 的核心不变量。"""
import sqlite3

from nutmeg.v4.observation.crown_close_history import record_match


def _rec():
    return {"match_id": "156951", "date": "2024-11-09", "league_cn": "西甲",
            "home_zh": "皇马", "away_zh": "奥萨苏纳", "home_goals": 4, "away_goals": 0,
            "rangqiu": -2, "crown_1x2": (1.27, 6.5, 10.0),
            "crown_ou": (1.95, 3.25, 1.95), "rq_avg": (2.5, 4.0, 2.09)}


def test_record_and_idempotent(tmp_path):
    db = tmp_path / "t.db"
    assert record_match(db, _rec()) == 1
    # 重录(同 match_id,幂等)→ 仍 1 写、仍 1 行、字段更新
    assert record_match(db, {**_rec(), "home_goals": 9}) == 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT match_id, home_goals, c_home, rangqiu, ou_line, rq_draw "
        "FROM crown_close_history").fetchall()
    assert len(rows) == 1
    mid, hg, ch, rq, ol, rqd = rows[0]
    assert mid == "156951"
    assert hg == 9 and ch == 1.27 and rq == -2 and ol == 3.25 and rqd == 4.0


def test_record_skips_no_crown(tmp_path):
    db = tmp_path / "t.db"
    assert record_match(db, {**_rec(), "crown_1x2": None}) == 0
