"""Mispricing gap engine: Polymarket ask vs our Pinnacle de-vig fair P.

For a matched game we de-vig Pinnacle's 1X2 → fair ``q`` per outcome, read the
Polymarket ASK ``p`` for the YES share of that outcome, and report
``ev = q/p − 1`` (buying the YES is +EV iff q > p). EV is labelled HONESTLY:
**+EV carries risk; it is NOT risk-free arbitrage**, and ``q`` is only as good
as the (possibly stale) Pinnacle line behind it.

The confidence TIER is the soul of this module — a big gap is usually a data
artifact, not an edge:
- ``excluded``  favorite-flip: Pinnacle and Polymarket disagree on which TEAM is
                more likely to win → almost always one side's data is wrong
                (the friendly "favorite flip" anomaly). Dropped, never surfaced
                as actionable.
- capped to ``low``     stale Pinnacle line, thin Polymarket book, or an
                        unverifiable flip (missing opposite-side price).
- capped to ``medium``  wide ask-vs-mid spread (illiquid → inflated apparent edge).
- ``high``      survives all of the above.

Tier reflects DATA QUALITY, independent of EV magnitude; callers filter/sort by
EV separately. Network (odds + orderbooks) is injected so the core is pure and
unit-tested with literals (including the mandatory favorite-flip case).
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nutmeg.v4.data.odds_parser import extract_1x2_odds, extract_over_under_25
from nutmeg.v4.data.polymarket_match import (
    AWAY_WIN,
    DRAW,
    HANDICAP_AWAY,
    HANDICAP_HOME,
    HOME_WIN,
    OVER,
    UNDER,
    MatchedGame,
)
from nutmeg.v4.data.sources.polymarket import ask_depth_usd, best_ask, mid_price
from nutmeg.v4.model.dixon_coles import score_grid
from nutmeg.v4.model.market_handicap import (
    DEFAULT_MAX_GOALS,
    DEFAULT_RHO,
    asian_total_over_prob,
    dc_home_cover_prob,
    devig_over,
    fit_lambdas,
)

log = logging.getLogger(__name__)

# Confidence thresholds (data-quality, not EV magnitude).
FRESH_MAX_HOURS = 12.0       # Pinnacle line older than this → cap at low
# ⛔ 2026-09-03 实测:**别收紧这个常数,没有数据支持。**
# 人口 = 干净集(已结算 且 recorded_at < kickoff)5,584 行 / 499 场;决策集
# (tier=high & ev≥5%)270 行 / 166 场。
#  · 校准偏差按 freshness 分档**非单调**(+0.08/+1.29/+1.01/−0.00/+0.77 pp)。
#    🚨 而且这把尺子在本表上**结构性退化**:88.4%(4,935/5,584)的行落在互补组里
#    (1X2 三腿 / O/U 双腿的 q 与 y 各恒和 =1)⇒ 组内 Σ(y−q)≡0,聚类后偏差被
#    **机械地**压成 0(8-16h 档 bias = −2.7e−18,机器零)。⇒ 只能看 Brier。
#  · Brier 确实随陈旧变差,但**那是比赛难度不是锚陈旧**:同一批行上、同一时刻的
#    Polymarket mid(它不随 Pinnacle 变旧)Brier 涨得**更多**,难度解释 116%;
#    难度受控的配对技能差 = −0.0026 ± 0.0017(t=−1.49),方向还反着。
#  · tier=high 内部(实测跨 0.95–10.18h)全 null,且最新鲜的 <2h 档是第二差的。
#  · 功效:收紧提案真正会用到的 8h 切点上 MDE = 0.0371,**连 0.02 都测不出**;
#    而配对尺子 MDE 只有 0.0048 ⇒ 「陈旧使 q 的 Brier 技能损失 >0.005」**被排除**。
#  · 代价是实的:12→6h 会把 45% 的 high 行(决策集 55%)降级。
# ⭐ 另:「high 的锚最旧 10.2h」不是窟窿,是**这个闸生效的结果** —— 916 行
#    (干净人口的 16.4%)带 `stale_pinnacle` 已被 12h 闸压到 low。
MIN_DEPTH_USD = 200.0        # USD resting at the ask below this → cap at low (thin)
WIDE_SPREAD_FRAC = 0.10      # (ask − mid)/mid above this → cap at medium
FAVORITE_TOL = 0.03          # |P_home − P_away| (or ask gap) below this = "too close
                             # to call" → never flagged as a flip
LONGSHOT_FLOOR = 0.15        # min(q, ask) below this → the "+EV" is a favourite-
                             # longshot / penny-tick ARTIFACT, not an edge: Polymarket
                             # prices in $0.01 ticks (a 1¢ tick is 25% of a 4¢ price),
                             # and the de-vig of an extreme Pinnacle line (17-to-1,
                             # 25-to-1) systematically overestimates tiny probabilities.
                             # Both manufacture fake +EV on deep underdogs/draws → cap low.
POLY_TICK = 0.01             # Polymarket's price granularity. An EV smaller than one
                             # tick's relative value (TICK/ask) is inside the rounding
                             # noise — it can flip sign on the next tick → cap low.
#: 并发拉 CLOB 盘口的线程数。⚠️ Polymarket 没有公开限流文档 ⇒ **取保守值**;
#: 真被限流会由 `_request` 的重试/退避兜住,但那会比串行还慢 —— 调高前先实测。
_BOOK_WORKERS = 8
Q_BAND = (0.12, 0.88)        # only PRICE (fetch a CLOB orderbook for) a 让球/大小球 line
                             # whose fair q sits in this informative band. Polymarket
                             # lists a deep ladder (±5.5 spreads, O/U 8.5) that is all
                             # longshot noise the LONGSHOT_FLOOR would cap anyway — and
                             # each priced leg costs one orderbook call. Moneyline is
                             # always priced (needed for the favorite-flip guard).

_TIER_RANK = {"excluded": 0, "low": 1, "medium": 2, "high": 3}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}


@dataclass(frozen=True)
class Gap:
    fixture_id: int
    league: str
    home_team: str
    away_team: str
    match_date: str
    kickoff_utc: str | None
    outcome_spec: str           # HOME_WIN|AWAY_WIN|DRAW|HANDICAP_HOME|HANDICAP_AWAY|OVER|UNDER
    line: float | None          # 让球 / 大小球 line (None for moneyline)
    q_fair: float               # our Pinnacle de-vig fair probability
    poly_ask: float             # actionable cost to buy the YES share
    poly_mid: float | None
    ev: float                   # q/p − 1 (+EV iff > 0; carries RISK, not arb)
    edge_direction: str         # "buy_yes" | "no_edge"
    confidence_tier: str        # excluded | low | medium | high
    reasons: list[str] = field(default_factory=list)
    depth_usd: float = 0.0
    freshness_hours: float | None = None
    yes_token: str = ""
    series_slug: str = ""
    event_slug: str = ""
    match_method: str = ""
    match_confidence: float = 0.0


def _devig_1x2(h: Any, d: Any, a: Any) -> tuple[float, float, float] | None:
    """WPO de-vig of Pinnacle 1X2 → fair (P_H, P_D, P_A) — the SAME method the 竞彩
    board uses (routes._pinnacle_devig_1x2 → nutmeg.v4.model.devig), so BOTH boards
    share one fair P. None on junk / any ≤1.0 leg (devig_1x2 guards internally)."""
    from nutmeg.v4.model.devig import devig_1x2
    p = devig_1x2(h, d, a)
    return (p[0], p[1], p[2]) if p else None


def _build_grid(p_h: float, p_d: float, p_a: float, p_over: float | None):
    """DC score grid fit to the de-vig 1X2 (+ O/U) — the market-reverse anchor the
    竞彩 让球 board uses, so 让球/大小球 price off the SAME Pinnacle line as 1X2."""
    lh, la = fit_lambdas(p_h, p_d, p_a, p_over, ou_line=2.5)
    return score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)


def _q_for(spec: str, line: float | None, p_h: float, p_d: float, p_a: float,
           grid) -> float | None:
    """Fair q for any outcome_spec. Moneyline off the WPO 1X2; 让球/大小球 off the DC
    grid (home covers `line` / total over `line`); away/under = complement (half-
    line ⇒ no push). None for an unknown spec or a prop without a line/grid."""
    if spec == HOME_WIN:
        return p_h
    if spec == DRAW:
        return p_d
    if spec == AWAY_WIN:
        return p_a
    if line is None or grid is None:
        return None
    if spec in (HANDICAP_HOME, HANDICAP_AWAY):
        # 体检 Wave3 (P2) — dc_home_cover_prob is half-line-only (integer
        # lines push). Polymarket handicap lines are external input: a
        # non-half line is skipped honestly (None → market excluded) rather
        # than mispriced via the no-push complement.
        if abs(line * 2 - round(line * 2)) > 1e-9 or int(round(line * 2)) % 2 == 0:
            return None
        if spec == HANDICAP_HOME:
            return dc_home_cover_prob(grid, line)
        return 1.0 - dc_home_cover_prob(grid, -line)
    if spec == OVER:
        return asian_total_over_prob(grid, line)
    if spec == UNDER:
        return 1.0 - asian_total_over_prob(grid, line)
    return None


def _cap(tier: str, ceiling: str) -> str:
    return _RANK_TIER[min(_TIER_RANK[tier], _TIER_RANK[ceiling])]


def _age_hours(iso_update: str | None, now: dt.datetime) -> float | None:
    if not iso_update:
        return None
    s = str(iso_update).replace("Z", "+00:00")
    try:
        then = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=dt.UTC)
    return (now - then).total_seconds() / 3600.0


def _favorite_flip(
    p_home: float, p_away: float, home_ask: float | None, away_ask: float | None
) -> bool | None:
    """True if Pinnacle and Polymarket disagree on the more-likely TEAM, None if
    not checkable (missing a side), False otherwise. A near-even matchup on
    EITHER source (within FAVORITE_TOL) is treated as no-flip (too close to call)."""
    if home_ask is None or away_ask is None:
        return None
    if abs(p_home - p_away) < FAVORITE_TOL or abs(home_ask - away_ask) < FAVORITE_TOL:
        return False
    # higher de-vig P / higher ask price ⇒ that source's favourite
    return (p_home > p_away) != (home_ask > away_ask)


def compute_gaps(
    game: MatchedGame,
    devig: tuple[float, float, float],
    books_by_token: dict[str, dict | None],
    odds_update: str | None,
    *,
    p_over: float | None = None,
    grid=None,
    now: dt.datetime | None = None,
) -> list[Gap]:
    """PURE core: gaps for one game from its de-vig 1X2 (+ O/U-anchored DC grid for
    让球/大小球) + Polymarket orderbooks. Only markets present in ``books_by_token``
    with a live ask form a gap (caller prices the informative subset)."""
    now = now or dt.datetime.now(dt.UTC)
    p_h, p_d, p_a = devig
    if grid is None:
        grid = _build_grid(p_h, p_d, p_a, p_over)

    # game-level favorite-flip (needs both team asks)
    ask_of: dict[str, float | None] = {}
    for mk in game.markets:
        ba = best_ask(books_by_token.get(mk.yes_token))
        ask_of[mk.outcome_spec] = ba[0] if ba else None
    flip = _favorite_flip(p_h, p_a, ask_of.get(HOME_WIN), ask_of.get(AWAY_WIN))
    fresh_h = _age_hours(odds_update, now)

    gaps: list[Gap] = []
    for mk in game.markets:
        q = _q_for(mk.outcome_spec, mk.line, p_h, p_d, p_a, grid)
        book = books_by_token.get(mk.yes_token)
        ba = best_ask(book)
        if q is None or ba is None:
            continue  # no price / unknown outcome → can't form a gap
        p = ba[0]
        mid = mid_price(book)
        depth = ask_depth_usd(book)
        ev = q / p - 1.0

        reasons: list[str] = []
        tier = "high"
        if flip is True:
            tier = "excluded"
            reasons.append("favorite_flip")
        elif flip is None:
            tier = _cap(tier, "low")
            reasons.append("flip_uncheckable")
        if fresh_h is None:
            tier = _cap(tier, "low")
            reasons.append("pinnacle_age_unknown")
        elif fresh_h > FRESH_MAX_HOURS:
            tier = _cap(tier, "low")
            reasons.append(f"stale_pinnacle:{fresh_h:.0f}h")
        if depth < MIN_DEPTH_USD:
            tier = _cap(tier, "low")
            reasons.append(f"thin:{depth:.0f}usd")
        if mid and mid > 0 and (p - mid) / mid > WIDE_SPREAD_FRAC:
            tier = _cap(tier, "medium")
            reasons.append("wide_spread")
        if min(q, p) < LONGSHOT_FLOOR:
            tier = _cap(tier, "low")
            reasons.append(f"longshot:{min(q, p) * 100:.0f}pp")
        if 0.0 < ev < POLY_TICK / p:  # edge smaller than one price tick → noise
            tier = _cap(tier, "low")
            reasons.append("within_tick")

        gaps.append(Gap(
            fixture_id=game.fixture_id, league=game.league,
            home_team=game.home_team, away_team=game.away_team,
            match_date=game.match_date, kickoff_utc=game.kickoff_utc,
            outcome_spec=mk.outcome_spec, line=mk.line, q_fair=q, poly_ask=p, poly_mid=mid,
            ev=ev, edge_direction="buy_yes" if q > p else "no_edge",
            confidence_tier=tier, reasons=reasons, depth_usd=depth,
            freshness_hours=fresh_h, yes_token=mk.yes_token,
            series_slug=game.series_slug, event_slug=game.event_slug,
            match_method=game.match_method, match_confidence=game.match_confidence,
        ))
    return gaps


def gaps_for_game(
    game: MatchedGame,
    *,
    fetch_odds: Callable[[int], list[dict]],
    fetch_book: Callable[[str], dict | None],
    now: dt.datetime | None = None,
) -> list[Gap]:
    """Orchestrator: fetch the fixture's Pinnacle odds + each YES token's book,
    de-vig, and compute gaps. Returns [] when no Pinnacle 1X2 line exists
    (skip — we have no fair P to compare against)."""
    try:
        envs = fetch_odds(game.fixture_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("polymarket-gap: odds fetch failed for fixture %s: %s", game.fixture_id, exc)
        return []
    env = envs[0] if envs else None
    if env is None:
        return []
    o1 = extract_1x2_odds(env)
    if not o1:
        return []
    devig = _devig_1x2(o1.get("H"), o1.get("D"), o1.get("A"))
    if devig is None:
        return []
    ou = extract_over_under_25(env)
    p_over = devig_over(ou[0], ou[1]) if ou else None
    grid = _build_grid(devig[0], devig[1], devig[2], p_over)

    # Price only the INFORMATIVE subset (one CLOB orderbook call per priced leg):
    # moneyline always (feeds the favorite-flip guard) + 让球/大小球 with fair q in
    # Q_BAND. Skips the deep-longshot ladder Polymarket lists (±5.5 spreads, O/U 8.5).
    def _informative(mk) -> bool:
        if mk.outcome_spec in (HOME_WIN, DRAW, AWAY_WIN):
            return True
        q = _q_for(mk.outcome_spec, mk.line, devig[0], devig[1], devig[2], grid)
        return q is not None and Q_BAND[0] <= q <= Q_BAND[1]

    # 盘口并发拉取(2026-09-01)。⚠️ **只改快慢,不改任何数据** ——
    # 取哪些腿、算什么、存什么全不变,只是别再一个一个等来回。
    #
    # 起因:英冠匹配修好后 `gaps computed` 从 841 涨到 1,687,一轮 CLOB 调用
    # **1,659 次**串行 ≈ 10 分钟。⭐ 实测这一轮里 AF `/odds` 只有 **26 次**、
    # AF `/fixtures` **0 次**(全缓存)—— 我先前从**代码顺序**推断「AF 配额才是
    # 真代价」是错的(`fetch_odds` 写在前面,但绝大多数在 `return []` 前就退了)。
    # 又一次「读出来的路径 ≠ 跑着的路径」⇒ 先数调用,再优化。
    #
    # 线程安全的两个前提都核过:`polymarket._client()` **每次新建** httpx.Client
    # (不共享),且 book 调用 `ttl_seconds=0` ⇒ **不写缓存文件**,没有写竞争。
    # 异常语义与串行版一致(`ex.map` 在取结果时抛,和逐个调一样)。
    toks = list(dict.fromkeys(          # 去重:同一 token 别拉两次
        mk.yes_token for mk in game.markets if _informative(mk)))
    if len(toks) <= 1:
        books = {t: fetch_book(t) for t in toks}
    else:
        with ThreadPoolExecutor(max_workers=min(_BOOK_WORKERS, len(toks))) as ex:
            books = dict(zip(toks, ex.map(fetch_book, toks), strict=True))
    return compute_gaps(game, devig, books, env.get("update"),
                        p_over=p_over, grid=grid, now=now)


def sort_gaps(gaps: list[Gap]) -> list[Gap]:
    """Excluded sink to the bottom; otherwise EV descending."""
    return sorted(gaps, key=lambda g: (g.confidence_tier == "excluded", -g.ev))


__all__ = [
    "Gap", "compute_gaps", "gaps_for_game", "sort_gaps",
    "FRESH_MAX_HOURS", "MIN_DEPTH_USD", "WIDE_SPREAD_FRAC", "FAVORITE_TOL",
    "LONGSHOT_FLOOR", "POLY_TICK",
]
