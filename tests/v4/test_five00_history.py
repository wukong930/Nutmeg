"""500 hisdata 解析 + Crown 提取的核心不变量。"""
import xml.etree.ElementTree as ET

import pytest

from nutmeg.v4.data.sources.five00_history import _ou, _triple, parse_hisdata

_MATCH = """<xml><head><updatetime>2024-11-11</updatetime></head>
<matches><matchdate date="2024-11-09">
  <match id="1" league="西甲" homename="皇马" awayname="奥萨苏纳" score="4:0"
         rangqiu="-2" matchnumdate="2024-11-09" plspf=""/>
  <match id="2" league="X" homename="A" awayname="B" score=""
         rangqiu="-1" matchnumdate="2024-11-09"/>
</matchdate></matches></xml>"""

_ODDS = """<xml><head/><matches>
  <match id="1"><europe hg="1.27,6.50,10.00" avg="1.25,6.31,11.13"/>
    <rq avg="2.50,4.00,2.09"/><dxq bet365="0.95,3/3.5,0.95"/></match>
  <match id="3"><europe avg="2.0,3.0,4.0"/></match>
</matches></xml>"""


def test_triple():
    assert _triple("1.27,6.50,10.00") == (1.27, 6.5, 10.0)
    assert _triple("1.00,2,3") is None       # 任一赔 ≤ 1 = junk
    assert _triple(None) is None


def test_ou_quarter_line():
    assert _ou("0.95,3/3.5,0.95") == pytest.approx((1.95, 3.25, 1.95))   # HK→decimal · 分盘取均
    assert _ou("0.90,2.5,0.98") == pytest.approx((1.90, 2.5, 1.98))
    assert _ou("x") is None


def test_parse_only_crown_scored():
    recs = parse_hisdata(ET.fromstring(_MATCH), ET.fromstring(_ODDS))
    assert len(recs) == 1                    # id=2 无比分跳过;id=1 有 Crown+score
    r = recs[0]
    assert r["match_id"] == "1"
    assert r["home_zh"] == "皇马" and r["league_cn"] == "西甲"
    assert (r["home_goals"], r["away_goals"]) == (4, 0)
    assert r["rangqiu"] == -2
    assert r["crown_1x2"] == (1.27, 6.5, 10.0)
    assert r["crown_ou"] == pytest.approx((1.95, 3.25, 1.95))   # HK 0.95 → decimal 1.95
    assert r["rq_avg"] == (2.5, 4.0, 2.09)


def test_parse_none_roots():
    assert parse_hisdata(None, None) == []
