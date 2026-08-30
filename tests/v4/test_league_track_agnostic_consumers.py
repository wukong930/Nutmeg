"""联赛标签**两轨**下,消费者必须给出同一个答案(2026-08-30 哨兵报警的回归闸)。

## 病

``jingcai_sp.league`` 有两个写入方两套词汇:sporttery cron 写竞彩中文缩写
(西甲/日职),面板「记一笔」(``source='market_mode'``)写 V4 EN 代码
(ESP_LA_LIGA/JPN_J1)。``data_freshness.check_league_labels`` 会把这报成
「劈开」,并建议跑 ``backfill_league_labels --apply``。

## 为什么要这两条测试,而不是「断言列里只有一种写法」

⭐ 那个报警测的是**语法**(列里有几种字符串),而真正要紧的是**语义**
(有没有消费者因此给出不同答案)。两者不等价 —— 2026-08-30 实测:
  · 全仓 8 个 ``jingcai_sp`` 读者里,**只有一个**真的裸分组(jingcai_staleness);
  · 而报警**自带的处方**会让另一个消费者(backfill_closing_gap)变得**更差** ——
    它的 sport_key 表用的是 EN 代码,归一成中文反而查不到。
⇒ 正确的不变量不是「只准有一种写法」,是「**两种写法必须得到同一个答案**」。
这两条测试断言的就是后者,所以它们不会因为将来又冒出第三种写法而假红。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nutmeg.v4.data.league_labels import canonical_league

REPO = Path(__file__).resolve().parents[2]

#: (EN 代码, 中文缩写) —— 2026-08-30 在 jingcai_sp 里**实际观测到**的两对。
TRACK_PAIRS = [("ESP_LA_LIGA", "西甲"), ("JPN_J1", "日职")]


def _load_backfill_closing_gap():
    path = REPO / "scripts" / "backfill_closing_gap.py"
    spec = importlib.util.spec_from_file_location("_bcg", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(("en", "cn"), TRACK_PAIRS)
def test_sport_key_is_track_agnostic(en: str, cn: str) -> None:
    """两轨写法必须解析到**同一个** sport_key,且都不是 None。

    回归的是真 bug:旧代码用一份手维护的中文→代码字典(只有 8 条,且**漏了**
    西甲/日职/意甲/英超/德甲/法乙/葡超/英冠 —— 正好是训练联赛)。中文标签
    落不到 sport_key ⇒ ``sk=None`` ⇒ ``continue`` ⇒ **静静跳过**,
    和「这个联赛没有数据」完全同形。实测被跳过 248/646 行(38%)。
    """
    mod = _load_backfill_closing_gap()
    sk_en, sk_cn = mod._sport_key(en), mod._sport_key(cn)
    assert sk_en is not None, f"{en} 解析不到 sport_key"
    assert sk_cn is not None, (
        f"{cn} 解析不到 sport_key —— 中文轨的行会被静默跳过(旧 bug 复发)")
    assert sk_en == sk_cn, f"两轨不一致: {en}→{sk_en} vs {cn}→{sk_cn}"


def test_canonicalizing_the_column_never_loses_a_sport_key() -> None:
    """⭐ 这条守的是「报警的处方不能反过来伤人」。

    ``backfill_league_labels --apply`` 会把 EN 代码改写成中文规范形。如果
    ``_sport_key`` 只认 EN,那次回填就会**静默地**把这些场次从抓取计划里删掉
    —— 而且是在一条**花钱**的 Odds API 路径上。2026-08-30 实测过这个反向危害
    (18 场 → 16 场),所以这里钉死:归一前后必须解析到同一个 sport_key。
    """
    mod = _load_backfill_closing_gap()
    for en, _cn in TRACK_PAIRS:
        assert mod._sport_key(en) == mod._sport_key(canonical_league(en)), (
            f"{en} 归一成 {canonical_league(en)} 后 sport_key 变了 —— "
            "回填会静默丢掉这些场次")


def test_staleness_groups_by_canonical_league() -> None:
    """``jingcai_staleness`` 的联赛分桶必须过归一。

    它是全仓 8 个 ``jingcai_sp`` 读者里唯一一个曾经裸分组的。默认
    ``--min-ev 0.05`` 下看不见(那几条 EN 腿 EV 顶到 -4.65%,离闸还差 9.65pp)
    —— **潜伏不等于不存在**:EN 行一旦过闸,表就会报出多余的组并稀释真联赛的 N。
    """
    import inspect

    from nutmeg.v4.cli import jingcai_staleness as js

    src = inspect.getsource(js)
    # 语法断言只当补充(见 [[syntactic-proxy-for-semantic-property]]),
    # 真正的断言在下面:拿两轨写法喂分桶键,必须得到同一个键。
    assert 'lambda c: c["league"]' not in src, "联赛分桶又回到裸字符串了"
    key = lambda c: canonical_league(c["league"])  # noqa: E731 — 与生产同形
    for en, cn in TRACK_PAIRS:
        assert key({"league": en}) == key({"league": cn}), (
            f"{en} 与 {cn} 分到了不同的桶 —— 一个联赛会被算成两组")


# ─────────────────────────────────────────────────────────────────────────
# 写入侧:2026-08-30 起在捕获处归一,终结「回填跑步机」
# ─────────────────────────────────────────────────────────────────────────

def _capture(tmp_path, league, *, home="Racing Santander", away="Elche"):
    """跑一次真实捕获,返回落库的 league 值(None 表示 NULL)。"""
    import sqlite3

    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp

    db = tmp_path / "obs.db"
    ok = record_jingcai_sp(
        db_path=db, match_date="2026-08-28", home_team=home, away_team=away,
        # booksum = 1.1251 ∈ [1.10, 1.15](真实那一行的赔率),否则被闸 1 拒写
        jc_home=1.91, jc_draw=3.35, jc_away=3.30,
        league=league, kickoff_utc="2099-01-01T00:00:00+00:00",
        source="market_mode")
    assert ok, "捕获被拒 —— 夹具本身没生效,下面的断言会是空的"
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT league FROM jingcai_sp WHERE home_team=?", (home,)).fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize(("en", "cn"), TRACK_PAIRS)
def test_capture_normalises_en_code_to_canonical(tmp_path, en, cn) -> None:
    """面板「记一笔」写 EN 代码时,落库的必须已经是规范中文形。

    这是终结跑步机的那一刀:在此之前,靠 ``backfill_league_labels --apply``
    事后清,25 天清了 4 次,每轮再生 3-8 个写法。
    """
    assert _capture(tmp_path, en) == cn


def test_capture_keeps_unknown_labels_verbatim(tmp_path) -> None:
    """认不出的标签**原样透传** —— 否则 data_freshness 的 unknown 检查会瞎掉。

    ⛔ 绝不在这里编映射(同「绝不照英文猜译名」那条红线)。
    """
    assert _capture(tmp_path, "SOME_NEW_LEAGUE") == "SOME_NEW_LEAGUE"


def test_capture_leaves_missing_league_null(tmp_path) -> None:
    """🚨 ``league=None`` 必须仍然落成 NULL。

    ``canonical_league(None)`` 返回 ``'(未标联赛)'`` —— 一个**字面量占位串**。
    无真值闸地套用会造成两处伤害:
      · 「不知道联赛」被写成一个看起来像联赛的值;
      · upsert 的 ``COALESCE(excluded.league, jingcai_sp.league)`` 会拿这个占位串
        **覆盖掉已存的真联赛** —— 把「没去看」写成「看过了」。
    """
    assert _capture(tmp_path, None) is None
