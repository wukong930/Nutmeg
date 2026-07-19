"""CLV ledger — settlement-independent soft-water measurement."""
from __future__ import annotations

import sqlite3

from nutmeg.v4.cli.clv_ledger import _hhad_cover_p, _tier, compute_ledger
from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp


def _seed_close(db, date, h, a, psc):
    from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots
    with sqlite3.connect(db) as c:
        ensure_odds_snapshots(c)   # canonical schema (avoids partial-DDL drift)
        c.execute("INSERT INTO odds_snapshots (source, league, captured_at, match_date, "
                  "home_team, away_team, psc_home, psc_draw, psc_away, psc_over, "
                  "psc_under, ou_line) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("closing", "WC", "2026-01-01T00:00:00+00:00", date, h, a,
                   psc[0], psc[1], psc[2], 1.9, 1.9, 2.5))


def test_tier_boundaries():
    assert _tier(0.10).startswith("cold")
    assert _tier(0.17).startswith("边缘")   # '高估区' retired (n=323 phantom) → 边缘 (15–25%)
    assert _tier(0.22).startswith("边缘")
    assert _tier(0.45).startswith("甜区")
    assert _tier(0.72).startswith("边缘")
    assert _tier(0.90).startswith("chalk")


def test_hhad_cover_p_partitions():
    # close = (psc_home, psc_draw, psc_away, psc_over, psc_under, ou_line)
    p = _hhad_cover_p((1.8, 3.6, 4.8, 1.9, 1.9, 2.5), -1)
    assert p is not None and abs(sum(p) - 1.0) < 0.05  # 让胜/让平/让负 exhaust the space


def test_settlement_independent_and_selected(tmp_path):
    """A row that NEVER settles still produces 3 legs; the capture-+EV leg becomes
    a selected observation whose CLV is measured vs the CLOSE (no look-ahead)."""
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=2.0, jc_draw=3.3, jc_away=3.3,
                      psc_home=1.8, psc_draw=3.6, psc_away=4.8, market="had")
    _seed_close(db, "2026-06-20", "A", "B", (1.85, 3.5, 4.6))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3 and rep["no_close"] == 0 and rep["n_matches"] == 1
    # capture home EV = devig(1.8,3.6,4.8)[0]*2.0 − 1 ≈ +8.3% (WPO) ≥ 5% → selected, 主胜
    assert len(rep["selected"]) == 1
    s = rep["selected"][0]
    assert s["pos"] == "主胜"
    p_close_home = devig_1x2(1.85, 3.5, 4.6)[0]   # WPO, production de-vig (single source)
    assert abs(s["clv"] - (p_close_home * 2.0 - 1)) < 1e-6  # CLV vs CLOSE, not capture


def test_no_close_skipped(tmp_path):
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-21", home_team="C", away_team="D",
                      jc_home=2.0, jc_draw=3.3, jc_away=3.3, market="had")
    rep = compute_ledger(db)
    assert rep["legs"] == [] and rep["no_close"] == 1


def test_below_threshold_not_selected(tmp_path):
    db = str(tmp_path / "obs.db")  # 竞彩 == Pinnacle → every leg is just −vig, none +EV
    record_jingcai_sp(db, match_date="2026-06-22", home_team="E", away_team="F",
                      jc_home=1.9, jc_draw=3.2, jc_away=3.55,
                      psc_home=1.9, psc_draw=3.2, psc_away=3.55, market="had")
    _seed_close(db, "2026-06-22", "E", "F", (1.9, 3.2, 3.55))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3 and rep["selected"] == []


def test_name_join_tripwire_splits_miss_reason(tmp_path):
    """A join miss where Pinnacle HAS the fixture same-day under a different spelling
    is flagged name-suspect (alias gap); a genuinely-absent day is plain no_quote.
    Uses a CLUB spelling split — national-team synonyms now auto-resolve via the elo
    alias (see test_jingcai_staleness), but club aliases stay autumn-gated → surface."""
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-08-01", home_team="Manchester City",
                      away_team="Arsenal", jc_home=2.0, jc_draw=3.3, jc_away=3.3,
                      psc_home=1.8, psc_draw=3.6, psc_away=4.8, market="had")
    _seed_close(db, "2026-08-01", "Man City", "Arsenal", (1.85, 3.5, 4.6))
    # genuinely no Pinnacle quote that day
    record_jingcai_sp(db, match_date="2026-08-09", home_team="Foo", away_team="Bar",
                      jc_home=2.0, jc_draw=3.3, jc_away=3.3, market="had")
    rep = compute_ledger(db, min_ev=0.05)
    assert rep["legs"] == [] and rep["no_close"] == 2
    assert rep["miss_quote"] == 1                                   # Foo v Bar
    assert [m["home"] for m in rep["miss_name"]] == ["Manchester City"]  # name-suspect


def test_league_labels_canonicalized_into_one_gate_group(tmp_path):
    """体检 2026-07-02: sporttery writes CN abbrevs (芬超) while the 记一笔 path
    writes EN codes (FIN_VEIKKAUSLIIGA) — the SAME league. Selected legs must
    land in ONE canonical group, or the per-league gate dilutes N and the
    BHY-FDR family gains a spurious member."""
    db = str(tmp_path / "obs.db")
    # same +EV setup as the selected-leg test; two matches, two label vocabularies
    record_jingcai_sp(db, match_date="2026-08-15", home_team="A", away_team="B",
                      jc_home=2.0, jc_draw=3.3, jc_away=3.3,
                      psc_home=1.8, psc_draw=3.6, psc_away=4.8,
                      market="had", league="芬超")
    _seed_close(db, "2026-08-15", "A", "B", (1.85, 3.5, 4.6))
    record_jingcai_sp(db, match_date="2026-08-16", home_team="C", away_team="D",
                      jc_home=2.0, jc_draw=3.3, jc_away=3.3,
                      psc_home=1.8, psc_draw=3.6, psc_away=4.8,
                      market="had", league="FIN_VEIKKAUSLIIGA")
    _seed_close(db, "2026-08-16", "C", "D", (1.85, 3.5, 4.6))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["selected"]) == 2
    assert {s["league"] for s in rep["selected"]} == {"芬超"}   # ONE group, not two


def test_canonical_league_failopen_and_trained_set():
    from nutmeg.v4.data.league_labels import TRAINED_LEAGUES_CN, canonical_league

    assert canonical_league("EPL") == "英超"
    assert canonical_league("WC") == "世界杯"
    assert canonical_league("瑞典超级联赛") == "瑞超"    # vote-table full-name synonym
    assert canonical_league("芬超") == "芬超"            # already canonical → identity
    assert canonical_league("KOR_K1_SOMETHING") == "KOR_K1_SOMETHING"  # fail-open
    assert canonical_league(None) == "(未标联赛)" and canonical_league(" ") == "(未标联赛)"
    assert len(TRAINED_LEAGUES_CN) == 13 and "日职" in TRAINED_LEAGUES_CN


def test_hhad_selected_reverse_fits_capture_ou(tmp_path):
    """让球选中腿: capture-time cover-P is reverse-fit from the stored 1X2 + O/U
    (psc_over/under), so an hhad +EV pick enters the validation counter."""
    db = str(tmp_path / "obs.db")
    # 软腿构造(2026-07-19 捕获闸后不能再用 5.0/5.0/5.0 的离带假盘):用生产同款
    # _hhad_cover_p 反推 −1 线三路 P,让平腿定价 1.12/p(EV≈+12% → 被选),其余两腿
    # k/p 定价(EV≈−17%),booksum≈1.13 落在闸带内。
    p3 = _hhad_cover_p((1.5, 4.0, 7.0, 1.9, 1.9, 2.5), -1)
    jc_d = round(1.12 / p3[1], 2)
    k = (p3[0] + p3[2]) / (1.13 - 1.0 / jc_d)
    record_jingcai_sp(db, match_date="2026-06-23", home_team="G", away_team="H",
                      jc_home=round(k / p3[0], 2), jc_draw=jc_d,
                      jc_away=round(k / p3[2], 2),
                      psc_home=1.5, psc_draw=4.0, psc_away=7.0,
                      psc_over=1.9, psc_under=1.9, ou_line=2.5,
                      market="hhad", handicap_home=-1)
    _seed_close(db, "2026-06-23", "G", "H", (1.55, 3.9, 6.5))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3
    assert len(rep["selected"]) == 1 and rep["selected"][0]["market"] == "hhad"
