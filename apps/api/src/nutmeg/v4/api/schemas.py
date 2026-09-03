"""Pydantic schemas for v4 API request/response.

These are the EXTERNAL contract — any change here is a breaking API change.
Internal data classes (MatchInput, Selection, Parlay) are separate and
can evolve freely.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- Request body ----------

class FixtureOddsInput(BaseModel):
    """One match in a daily recommendation request."""
    date: date
    league: str = Field(..., description="Canonical league code, e.g. 'EPL', 'ESP_LA_LIGA'")
    home_team: str = Field(..., description="Must match training-set team spelling")
    away_team: str
    # V12 W4 — ISO kickoff time (with tz) from the odds cache, threaded through
    # to SinglePrediction so the 近期赛事 cards can show + sort by time.
    kickoff_utc: str | None = None

    # Required: model needs these to construct market features
    psc_home: float = Field(..., gt=1.0, description="Pinnacle (or sharp) closing 1X2 home odds")
    psc_draw: float = Field(..., gt=1.0)
    psc_away: float = Field(..., gt=1.0)

    # 竞彩 lottery odds (what the player actually bets at). If absent, the
    # outcome is NOT bettable — do NOT substitute Pinnacle (psc_*). Pinnacle is
    # the sharp benchmark, not a betting venue; EV against it is model-vs-sharp
    # noise (the EV-vs-Pinnacle bug). Selection builders raise when these are
    # missing (audit B2/D3; was previously "Default to Pinnacle if absent").
    odds_1x2_H: Optional[float] = Field(None, gt=1.0)
    odds_1x2_D: Optional[float] = Field(None, gt=1.0)
    odds_1x2_A: Optional[float] = Field(None, gt=1.0)

    # China integer handicap
    handicap_home: Optional[int] = Field(None, ge=-5, le=5, description="China integer handicap")
    odds_handicap_H: Optional[float] = Field(None, gt=1.0)
    odds_handicap_D: Optional[float] = Field(None, gt=1.0)
    odds_handicap_A: Optional[float] = Field(None, gt=1.0)

    # Optional extra market signals (features only, never bet)
    psc_over25: Optional[float] = Field(None, gt=1.0)
    psc_under25: Optional[float] = Field(None, gt=1.0)
    # V14 — Asian total line the psc_over25/under25 are quoted AT (often 2.25 for
    # J1, not 2.5). Lets the 竞彩盘 anchor the market-reverse λ for cup/J1 to the
    # real line instead of assuming 2.5. None → server defaults 2.5.
    ou_line: Optional[float] = Field(None, gt=0.0)
    ahch: Optional[float] = Field(None, description="European Asian handicap closing line")
    # V14 — real Pinnacle Asian Handicap board as a JSON string ({line: {home,
    # away}}); the server de-vigs it for the 让球胜平负 prediction (DC fallback
    # when absent). JSON-encoded so it survives the pandas/pydantic round-trip.
    asian_handicap: Optional[str] = None
    # 体检 P1#10 — when API-Football last refreshed this fixture's Pinnacle
    # snapshot (ISO). Display echo only (never a model feature): threads to
    # SinglePrediction / SingleTicketResponse so the 今日推荐 ticket shows the
    # same odds-age badge the 市场模式 card already has.
    odds_update: str | None = None
    # 2026-07-23 — 这些 psc_* 的出处('odds_api'/'api_football'/'manual')。
    # **不是模型特征**,纯溯源:record_session 时 store._request_odds_source 读它,
    # 落到 recommendation_sessions.odds_source。None = 不知道,**不猜**。
    odds_source: str | None = None


class RecommendRequest(BaseModel):
    """POST /v4/recommend body."""
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1, max_length=50)
    bankroll: float = Field(1000.0, gt=0)
    top_n: int = Field(10, ge=1, le=50)
    k_min: int = Field(2, ge=2, le=8)
    k_max: int = Field(8, ge=2, le=8)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0)
    include_compound: bool = Field(False, description="Enumerate 复式 legs")
    # V5 W11: optional snapshot_phase carried through to observation recorder
    # when --record-to / X-Record-DB is set on the server. Values come from
    # SNAPSHOT_PHASES in nutmeg.v4.observation.store; defaults to "closing"
    # (legacy V4 behavior).
    snapshot_phase: Literal["pre_close", "closing", "post_close"] = "closing"
    # V9 W3: per-request opt-in for observation recording. Both this AND
    # the server's NUTMEG_V4_OBSERVATION_DB env var must be set for a
    # session to actually land in the DB. Defaults to False so existing
    # callers don't accidentally start recording.
    record_session: bool = False


# ---------- Response body ----------

class HandicapLineProb(BaseModel):
    """V12 W3 — model P(让胜/让平/让负) for one integer handicap line,
    derived from the same Dixon-Coles score grid. The 竞彩 SP calculator
    looks up the line matching the user's 竞彩 让球线 and computes live EV
    client-side (no server round-trip)."""
    line: int  # handicap_home: −1 = 主队让1球, +1 = 主队受让1球
    p_home: float
    p_draw: float
    p_away: float
    # A′(2026-07-17)— ±1 线的 P 里含 C1 修正,而 C1 的 δ 是**估计值**,其误差
    # 1:1 传进被修正的腿、再乘 竞彩SP 放大成 EV 误差。这三个是**逐腿下界**
    # (δ ∓ 2SE 中让该腿自己 P 更小的那侧);未被 C1 碰的腿 = 点估。
    # 前端:EV 点估用 p_*,**判闸(绿灯/候选)用 p_*_lo**,显示区间
    # [lo, 2×点估−lo](带宽对称)。⚠️ lo 三元组**不是分布**(和<1),别归一化。
    # 计算在服务端(model.market_handicap.c1_leg_lower_bounds)—— 别把 C1 结构
    # 抄进 JS(参照 devig-js-server-mismatch 的教训:客户端并行算法必然漂移)。
    p_home_lo: float | None = None
    p_draw_lo: float | None = None
    p_away_lo: float | None = None


class AsianHandicapLineProb(BaseModel):
    """V14 — INTERNATIONAL Asian Handicap (half-line, 2-way: cover / not, NO
    push). Distinct from HandicapLineProb (竞彩 integer 3-way). ``line`` is the
    home handicap (−0.5 = 主队让半球 ⇒ home must win; +1.5 = 主受让1.5 …).
    ``source`` = ``"mkt"`` when de-vigged from a real Pinnacle AH quote, ``"dc"``
    when read off the Dixon-Coles grid (fallback). For the 让球胜平负 prediction
    display (国际盘 + 市场模式), for future Polymarket comparison."""
    line: float
    p_home: float   # P(home covers)
    p_away: float   # P(away covers) = 1 − p_home (half-line, no push)
    source: str = "dc"


class ScoreCell(BaseModel):
    """One exact scoreline (home:away) with its probability."""
    home: int
    away: int
    p: float


class MarginBand(BaseModel):
    """V14 — one goal-margin (home−away) band for the 净胜球分组 READ tool.

    A readout of the same Dixon-Coles grid — NOT a new signal (a 1500-fixture
    eval showed feeding the Asian Handicap INTO the λ fit adds ~0 info: the grid
    already reproduces the AH curve to ~1.5pp). It helps pick a coherent CLUSTER
    of scorelines given the 让球 line. ``margin`` is signed home−away; ``is_tail``
    flags the folded ±N+ buckets; ``scores`` are the top exact scorelines in it."""
    margin: int
    is_tail: bool
    p: float
    scores: list[ScoreCell] = Field(default_factory=list)


class SinglePrediction(BaseModel):
    home_team: str
    away_team: str
    league: str
    date: date
    # V12 W4 — ISO kickoff time (with tz) when known, so the 近期赛事 cards can
    # show date+time and sort chronologically within a league. Optional: the
    # odds cache row may omit it; the client falls back to `date`.
    kickoff_utc: str | None = None
    lambda_home: float
    lambda_away: float
    p_home_1x2: float
    p_draw_1x2: float
    p_away_1x2: float
    # 2026-08-06 owner — **纯市场**公允 P(Pinnacle WPO 去vig),和模型 P 并列下发。
    #
    # 为什么必须由服务端算、而不是前端就地除:前端原来用 basic(按比例)去vig 画
    # 「市」那一列,而 EV/分析路(`_pinnacle_devig_1x2`、手填 reprice 端点)一律走
    # **WPO**。两者对这场德乙差 0.5pp(42.0 vs 42.5)—— 只要 EV 用一个、显示用
    # 另一个,面板上就会出现「市 42%」却按 42.5% 算 EV 的静默劈叉。
    # 见 [[devig-js-server-mismatch]]:结论是 **EV 路 server-first**,别把 WPO
    # 移植进 JS。这三个字段就是那条结论的落地。
    #
    # None = 该场没有 Pinnacle 线(市场 EV 无从算起,前端据此退回只显示模型 EV)。
    p_home_market: float | None = None
    p_draw_market: float | None = None
    p_away_market: float | None = None
    # 2026-08-08 — 1X2 三条腿的**判闸下界**(δ₁ₓ₂,model.onex_calibration)。
    #
    # ⚠️ 名字刻意不叫 `p_*_market_lo`:它的**点估在哪个字段取决于模式** ——
    #   标准模式 → `p_*_market`;市场模式 → `p_*_1x2`(那里 `p_*_market` 一律 null,
    #   见上面那段注释)。两者是**同一个 Pinnacle WPO 三元组**,所以下界只有一份。
    #   叫 `p_*_market_lo` 会在市场模式下变成一个撒谎的名字。
    #
    # 为什么必须服务端下发而不是前端就地减:常数要和让球侧的 `_C1_SE_K` 同源,
    # 放进 JS 就会重演 WPO 那次的 server↔JS 漂移([[devig-js-server-mismatch]])。
    #
    # None = 该场没有 Pinnacle 线 ⇒ 点估也是 None ⇒ 前端那三条腿本来就不进榜。
    onex_lo_home: float | None = None
    onex_lo_draw: float | None = None
    onex_lo_away: float | None = None
    # V12 W3 — Pinnacle closing odds echoed back so the dashboard's 竞彩 SP
    # calculator can pre-fill inputs and show the 竞彩-vs-Pinnacle soft-line
    # gap. Optional: not every prediction path carries them (e.g. WC).
    psc_home: float | None = None
    psc_draw: float | None = None
    psc_away: float | None = None
    # V12 W8 — Pinnacle over/under 2.5 echo, present in 市场模式. The dashboard
    # sends these back to /recommend/market-handicap so the server recomputes
    # the market-implied 让球 P (double-anchored on 1X2 + O/U) authoritatively
    # before recording — no trusting a client-sent probability.
    psc_over25: float | None = None
    psc_under25: float | None = None
    # 体检 2026-07-03 — the ACTUAL total line those prices are quoted at (the
    # Odds-API overlay moves it, e.g. Sirius 2.5→2.75). Without it the card
    # labels every O/U "2.5" while showing another line's prices. The server's
    # own 让球反推 already used the row value; this is the display echo.
    ou_line: float | None = None
    # 体检 — the 竞彩 SP (1X2) on file for this match from jingcai_sp (your manual
    # market_mode entry, else the sporttery auto-harvest). Lets the card PRE-FILL
    # its SP boxes + compute EV without re-typing. None when no 竞彩 line on file.
    jc_home: float | None = None
    jc_draw: float | None = None
    jc_away: float | None = None
    jc_source: str | None = None
    # 体检 — 竞彩 让球 (hhad) SP + its line, so the card's 让球 section pre-fills too.
    jc_hc_home: float | None = None
    jc_hc_draw: float | None = None
    jc_hc_away: float | None = None
    jc_hc_line: int | None = None
    # 2026-07-20 — 竞彩价的捕获时刻(had/hhad 较旧者,ISO)。前端年龄标用:
    # EV = P(t₁)×SP(t₂),Pinnacle 有 odds_update 年龄,竞彩侧此前不可见 —— 旧价
    # 会静默美化/隐藏 EV(埃尔夫斯堡 +8pp / 库奥皮奥藏绿灯 两案)。
    jc_captured_at: str | None = None
    # 2026-07-25 — 竞彩单关可投标记。⚠️ **PER-MARKET**(见 jingcai_sp DDL):竞彩
    # 可以给胜平负开单关而让球不开,所以两个玩法各一列,别合并。
    # 实测只有 17% 场次可单关且高度集中(韩职 29%/瑞超 21%/挪超 13%,
    # 欧罗巴·芬超·欧冠·巴甲·美职 0/59)。None=未知 → 前端不渲染徽章,不猜。
    # ── 多书商离散度参照(2026-09-01)—— ⛔ **只显示,不判闸** ────────────────
    #: 回答的问题是 owner 提的那个:竞彩**封盘后**价格冻住而外盘还在动,
    #: 按封盘价算的 EV 还站不站得住?实测封盘后主胜隐含概率漂移
    #: **|漂移|>2pp 占 29%、>5pp 占 5%,区间 [−12.4,+9.7]pp** —— 量级远大于所有 δ 校正。
    #:
    #: ⭐ 单锚(只看 Pinnacle)会**夸大**:法乙那场它是 13 家里最看好客胜的 ⇒
    #: 单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**(近一倍)。
    #: 63 场重叠上「Pinnacle 过 +5% 闸而共识不过」的腿有 5 条。
    #: ⛔ 但那 63 场人口偏斜(全世界杯 + 全缓存未过期)⇒ 只证明**机制存在**,
    #: **不是**影响多大的估计 ⇒ 绝不进 `_boardLegs` 的 evLo / argmax / 串关。
    #:
    #: ⚠️ **共识刻意排除 Pinnacle 自己** —— 含它的中位会被它拖着走,答不了
    #: 「Pinnacle 是不是在自说自话」这个问题。
    #: ⚠️ `bk_n` **必须和数值一起显示**:2 家的「共识」不是共识。
    #: 三元组顺序 = (主胜, 平局, 客胜),与 `jc_home/draw/away` 对齐。
    bk_consensus: list[float] | None = None   # 非-Pinnacle 书商去vig 后的**中位**
    bk_low: list[float] | None = None         # 最保守(最小)的那一家
    bk_spread: list[float] | None = None      # 离散度(max−min,**百分点**)
    bk_n: int | None = None                   # 家数(含 Pinnacle)
    bk_captured_at: str | None = None         # 这批报价抓于何时
    #: True = **本项目未接入该赛事的多书商源**(该赛事不在 `SPORT_KEYS` 里)。
    #: ⚠️ 2026-09-03 订正措辞:原文写「Odds API 根本没有对应 sport」并点名德国杯,
    #: 而我们自己 2026-06-11 的 `/sports` 缓存里**就有** `soccer_germany_dfb_pokal`
    #: —— 那是**我们没接**,不是人家没有(日联赛杯等则确实是人家没有)。
    #: 把两者都说成后者,正是本仓反复犯的「把『没有』说成『没去看』」的反向版。
    #: ⇒ 多书商共识**永远不会有**,不是「今天没抓到」。
    #: ⚠️ 必须和「有 key 但今天没数据」区分开 —— 否则 owner 会一直等一个不会来的东西。
    bk_unavailable: bool = False
    #: 第三态(2026-09-03):这一天**有**多书商快照,只是这一场**没连上**(队名对不上)。
    #: ⚠️ 和 `bk_unavailable`(Odds API 结构性没有该赛事)、和「今天一行都没抓到」
    #: 三者互斥。原来后两者都渲染成空白 ⇒ owner 看不出「该去补词典」。
    #: 实测:一次 79 场的 sp-calc 里 3 场落在这一态,其中一场是竞彩当天在售的。
    bk_no_match: bool = False
    jc_single_available: int | None = None
    jc_hc_single_available: int | None = None
    # V14 — when API-Football last refreshed this Pinnacle snapshot (ISO). The
    # 市场模式 card shows the age so a stale de-vig prior isn't trusted near
    # kickoff (API-Football mirrors Pinnacle only every few hours).
    odds_update: str | None = None
    # 2026-07-23 — 这条 Pinnacle 价的**出处**:'odds_api'(OA 直连)/
    # 'api_football'(AF 镜像)/'manual'(owner 手填)。回显给前端,前端记账时原样
    # 送回 ⇒ 台账能分清「抓来的」和「手打的」。见 store._request_odds_source。
    odds_source: str | None = None
    # Optional handicap probs (present only when handicap_home was provided)
    handicap_home: Optional[int] = None
    p_home_handicap: Optional[float] = None
    p_draw_handicap: Optional[float] = None
    p_away_handicap: Optional[float] = None
    # V12 W3 — model handicap P across integer lines (−3..+3) so the 竞彩 SP
    # calculator computes live 让球 EV for any 竞彩 让球线 without a round-trip.
    # Empty when not computed (e.g. WC predictions).
    handicap_lines: list[HandicapLineProb] = Field(default_factory=list)
    # 🚨 δ 联赛范围闸三态 —— **自动卡也吃这个闸**,不是只有手填卡。
    # 标准板(`_model_board_handicap_lines`)与市场板(`_market_handicap_lines`)
    # 各自按行的 league 判,所以这个字段是**逐场**的,不是全局常量。
    # 默认 `missing` 是**故意**的:构造点漏填 ⇒ 面板显示⚠️,而不是显示「一切正常」。
    delta_scope: Literal["applied", "out_of_scope", "missing"] = "missing"
    # V14 — INTERNATIONAL Asian Handicap (half-line, 2-way) for the 让球胜平负
    # PREDICTION: real Pinnacle AH de-vig where quoted, DC-grid cover-prob
    # fallback otherwise. NOT the 竞彩 integer market (that's handicap_lines).
    asian_handicap_lines: list[AsianHandicapLineProb] = Field(default_factory=list)
    # V12 W7 — 杯赛市场模式: when True, p_*_1x2 are NOT model output — they are
    # the Pinnacle de-vig fair probabilities (the model is out-of-distribution
    # for cups, so we lean 100% on the sharp market). lambda_* are 0. The UI
    # labels these "市场模式·Pinnacle 公允价".
    # V12 W8 — handicap_lines ARE now populated for market mode too: a
    # Dixon-Coles goal grid reverse-fitted to the de-vig 1X2 + Pinnacle O/U
    # gives market-implied 让球 P (validated vs Pinnacle's own AH ~1pp). So the
    # market-mode card prices 竞彩 让球 SP live, not just 胜平负.
    market_mode: bool = False
    # V14 — sharp-flip guard: True when Pinnacle's de-vig favourite DISAGREES
    # with the other sharp books (Betfair + SBOBET) in the SAME /odds envelope.
    # Empirically Pinnacle's line is much worse on these (~10pp hit-rate drop,
    # log-loss 1.07 vs 0.97), so the card downgrades the EV reliability tag to
    # ⚠️ "sharp 分歧" — our Pinnacle-based EV is built on a suspect line there.
    sharp_flip: bool = False
    # V14 — 净胜球分组 (goal-margin bands): same DC grid, grouped by margin with
    # the top scorelines per band, so the card can show a coherent score CLUSTER
    # for the chosen 让球 line. READOUT, not a +EV signal (AH-into-fit was a wash).
    margin_bands: list[MarginBand] = Field(default_factory=list)


class PendingFixture(BaseModel):
    """V12 W6 — an upcoming fixture whose Pinnacle 1X2 line has NOT opened yet.

    The model treats Pinnacle (psc) as a STRONG feature — empirically, without
    it the served λ/P shifts materially (the favorite can flip), so a psc-free
    probability would be unreliable. Rather than surface a misleading P/EV, the
    近期赛事 tab lists these as '待开盘' cards so the user still sees the full
    slate; each is auto-promoted into `predictions` (full calc) once Pinnacle
    opens that line.

    ⚠️ 「once Pinnacle opens」这句对**大多数**联赛成立,但不是全部。2026-08-08 实测:
    日乙(JPN_J2)两条 Pinnacle 源都不存在(Odds API 无 sport key + AF 逐场零家博彩,
    含 7 天后的未来场)⇒ 它的场次**永远**等不到自动开盘,而竞彩确实在卖。
    所以 `reason` 从「只有一个取值的装饰字段」变成了真的判据 —— 见下。
    """
    #: True = **已开赛**(不是「Pinnacle 未开盘」)。两者都 `psc_home is None`,
    #: 但意思相反:前者永远不会再有线,后者随时可能开。
    #: 🚨 病情(owner 2026-09-03 实报):一场比赛开球前 5 分钟还在卡片上,
    #: **一按 🔄 就整张消失** —— 后端 `min_kickoff_buffer_minutes=5` 那个
    #: `continue` 既跳过了 /odds 调用(声明的目的)**也删掉了行**(未声明的副作用),
    #: 而前端的同款闸只是把它移出「可投注」分组、卡片还在。同一条规则,
    #: 一边降级一边删除。⇒ 服务路径改成 `keep_started=True`:不拉赔率(零额外配额)
    #: 但照样出行,并由本字段区分状态。
    started: bool = False
    home_team: str
    away_team: str
    league: str
    date: date
    kickoff_utc: str | None = None
    #: 为什么这场没有 P。**两个取值语义完全不同,别合并**:
    #:   · `pinnacle_not_open` —— 上游还没开盘,等就行(绝大多数);
    #:   · `jingcai_selling_no_pinnacle` —— 竞彩**已经在卖**、而 Pinnacle 这条线
    #:     可能永远不会有(日乙)⇒ 只有手填 Pinnacle 这一条路。
    #: 2026-08-08 之前这个字段恒等于默认值(两个构造点都不传),
    #: 唯一消费者是一条测试 —— 一个**长得像能区分原因、实际不能**的字段。
    reason: str = "pinnacle_not_open"
    #: 竞彩侧的 SP(由 `_attach_jingcai_sp` 填)。
    #:
    #: 🚨 为什么必须先声明再调用:`PendingFixture` 是 pydantic v2 model,未声明的
    #: 属性赋值会抛 `ValueError`;而 `_attach_jingcai_sp` 的 try 只包到 lookup,
    #: **写回循环是裸的** ⇒ 先加调用后加字段 = 第一场命中的 pending 就把
    #: `/predictions/cup-market` 打成 HTTP 500(agent 实跑证明,不是推测)。
    jc_home: float | None = None
    jc_draw: float | None = None
    jc_away: float | None = None
    jc_source: str | None = None
    jc_hc_home: float | None = None
    jc_hc_draw: float | None = None
    jc_hc_away: float | None = None
    jc_hc_line: float | None = None
    jc_captured_at: str | None = None
    #: PER-MARKET(玩法级)单关可得性 —— 竞彩可以给胜平负开单关、让球不开。
    #: 日乙这 2 场两个玩法都是 0(竞彩原始 feed 独立核过:`"single":0, "allUp":1`)
    #: ⇒ 即便手填出 +EV **也只能进串关,买不了单关**。
    jc_single_available: int | None = None
    jc_hc_single_available: int | None = None
    # ── 多书商离散度参照(2026-09-01)—— ⛔ **只显示,不判闸** ────────────────
    #: 回答的问题是 owner 提的那个:竞彩**封盘后**价格冻住而外盘还在动,
    #: 按封盘价算的 EV 还站不站得住?实测封盘后主胜隐含概率漂移
    #: **|漂移|>2pp 占 29%、>5pp 占 5%,区间 [−12.4,+9.7]pp** —— 量级远大于所有 δ 校正。
    #:
    #: ⭐ 单锚(只看 Pinnacle)会**夸大**:法乙那场它是 13 家里最看好客胜的 ⇒
    #: 单锚 EV **+16.7%** vs 13 家中位 **+8.8%** vs 最保守 **−0.6%**(近一倍)。
    #: 63 场重叠上「Pinnacle 过 +5% 闸而共识不过」的腿有 5 条。
    #: ⛔ 但那 63 场人口偏斜(全世界杯 + 全缓存未过期)⇒ 只证明**机制存在**,
    #: **不是**影响多大的估计 ⇒ 绝不进 `_boardLegs` 的 evLo / argmax / 串关。
    #:
    #: ⚠️ **共识刻意排除 Pinnacle 自己** —— 含它的中位会被它拖着走,答不了
    #: 「Pinnacle 是不是在自说自话」这个问题。
    #: ⚠️ `bk_n` **必须和数值一起显示**:2 家的「共识」不是共识。
    #: 三元组顺序 = (主胜, 平局, 客胜),与 `jc_home/draw/away` 对齐。
    bk_consensus: list[float] | None = None   # 非-Pinnacle 书商去vig 后的**中位**
    bk_low: list[float] | None = None         # 最保守(最小)的那一家
    bk_spread: list[float] | None = None      # 离散度(max−min,**百分点**)
    bk_n: int | None = None                   # 家数(含 Pinnacle)
    bk_captured_at: str | None = None         # 这批报价抓于何时
    #: True = **本项目未接入该赛事的多书商源**(该赛事不在 `SPORT_KEYS` 里)。
    #: ⚠️ 2026-09-03 订正措辞:原文写「Odds API 根本没有对应 sport」并点名德国杯,
    #: 而我们自己 2026-06-11 的 `/sports` 缓存里**就有** `soccer_germany_dfb_pokal`
    #: —— 那是**我们没接**,不是人家没有(日联赛杯等则确实是人家没有)。
    #: 把两者都说成后者,正是本仓反复犯的「把『没有』说成『没去看』」的反向版。
    #: ⇒ 多书商共识**永远不会有**,不是「今天没抓到」。
    #: ⚠️ 必须和「有 key 但今天没数据」区分开 —— 否则 owner 会一直等一个不会来的东西。
    bk_unavailable: bool = False
    #: 第三态(2026-09-03):这一天**有**多书商快照,只是这一场**没连上**(队名对不上)。
    #: ⚠️ 和 `bk_unavailable`(Odds API 结构性没有该赛事)、和「今天一行都没抓到」
    #: 三者互斥。原来后两者都渲染成空白 ⇒ owner 看不出「该去补词典」。
    #: 实测:一次 79 场的 sp-calc 里 3 场落在这一态,其中一场是竞彩当天在售的。
    bk_no_match: bool = False


class SpCalcResponse(BaseModel):
    """V12 W3 — data for the 近期赛事 tab's 竞彩 SP calculator: model output
    for every fixture across a multi-day window (default 3 days). Each
    prediction carries 1X2 P + Pinnacle odds + handicap-line P so the client
    computes live 竞彩 EV. Separate from /today-recommendations (the auto
    'best recommendation' surface), to avoid mixing the two."""
    generated_at_utc: str
    date_start: str
    date_end: str
    days: int
    fixtures_fetched: int
    predictions: list[SinglePrediction] = Field(default_factory=list)
    # V12 W6 — upcoming fixtures with no Pinnacle line yet (model P would be
    # unreliable without its psc feature). Listed as 待开盘 in the UI, NOT
    # scored. Auto-promoted to `predictions` once Pinnacle opens that line.
    pending_fixtures: list[PendingFixture] = Field(default_factory=list)


class EvLeg(BaseModel):
    """V14 — one bettable leg on the 真 EV 板. EV = P(Pinnacle de-vig) × 竞彩SP − 1 —
    the ONLY honest edge: a sharp fair probability priced against the actual 竞彩 SP
    you bet at (NOT the model, NOT Pinnacle's own price). Only legs carrying BOTH a
    Pinnacle line (→ P) AND a 竞彩 SP on file qualify."""
    date: str
    home_team: str
    away_team: str
    league: str
    kickoff_utc: str | None = None
    market: Literal["had", "hhad"]
    outcome: Literal["home", "draw", "away"]
    handicap_line: int | None = None  # 竞彩 让球线 (hhad only)
    p_pinnacle: float                 # de-vig fair P for this outcome
    jc_sp: float                      # 竞彩 SP you'd actually bet at
    ev: float                         # p_pinnacle × jc_sp − 1
    kelly_stake: float                # fractional-Kelly stake on the bankroll


class EvBoardResponse(BaseModel):
    """V14 — the 真 EV 推荐板 feeding 单关/串关/复式 (replaces the old
    'best by hit-rate vs Pinnacle' boards). ``legs`` are gated at ``min_ev`` and
    sorted by EV desc; ``n_positive`` counts genuine +EV (≥+5%) legs regardless of
    the slider, so the UI can honestly say '0 条真 +EV → 空仓'. Usually empty (the
    ~12% 竞彩 vig wall) — that empty state IS the signal."""
    generated_at_utc: str
    days: int
    min_ev: float
    bankroll: float
    n_fixtures: int       # fixtures with a Pinnacle line + at least one 竞彩 SP
    n_legs_with_sp: int   # eligible legs (had + hhad) carrying both P and 竞彩 SP
    n_positive: int       # of those, how many are genuinely +EV (≥ +5%)
    legs: list[EvLeg] = Field(default_factory=list)


class SelectionResponse(BaseModel):
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    edge: float


class LegResponse(BaseModel):
    match_id: str
    market_type: Literal["1x2", "handicap_1x2"]
    selections: list[SelectionResponse]


class RecommendationResponse(BaseModel):
    rank: int
    k_legs: int = Field(..., ge=2, le=8)
    is_compound: bool
    stake_units: int
    kelly_recommended_stake: float
    kelly_capped_fraction: float
    expected_return: float
    hit_probability: float
    ev_per_unit: float
    log_growth: float
    legs: list[LegResponse]
    # V11 P1-FE#5 — deterministic fingerprint of the picks (sorted
    # match_id+market+outcome tuples). Frontend uses this to detect
    # "this specific recommendation's picks changed" so it can render
    # an "已更新" badge next to it. Computed server-side.
    selection_fingerprint: str | None = Field(None, description=
        "12-char SHA1 prefix of sorted (match_id, market_type, outcome) tuples")


class ModelInfo(BaseModel):
    trained_at_utc: Optional[str] = None
    training_cutoff: Optional[str] = None
    n_train: Optional[int] = None
    gbm_rho: Optional[float] = None
    temperature_T: Optional[float] = None
    # V5 W7 + W11: backend identity so callers (dashboard, observation recorder)
    # can label data with which artifact produced it.
    model_type: Optional[str] = "lightgbm"
    cat_features: Optional[list[str]] = None


class RecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    single_match_predictions: list[SinglePrediction]
    recommendations: list[RecommendationResponse]
    # V11 P1-FE#5 — top-level version hash for parlay output.
    version_hash: str | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


# ---------- /v4/recommend/parlay (V12 W5 — hand-picked 串关) ----------

class ParlayLegInput(BaseModel):
    """One hand-picked leg of a 竞彩 parlay, from the 近期赛事 calculator.

    Carries the fixture identity (so the server can recompute the model P and
    the leg is settleable) + the user's pick + the 竞彩 SP for this leg.
    """
    date: date
    league: str
    home_team: str
    away_team: str
    kickoff_utc: str | None = None
    market_type: Literal["1x2", "handicap"] = "1x2"
    outcome: Literal["H", "D", "A"]
    # Required when market_type == "handicap" (China integer handicap line).
    handicap_home: int | None = Field(None, ge=-5, le=5)
    # The 竞彩 SP the user is betting this leg into.
    sp: float = Field(..., gt=1.0, description="竞彩 SP for this leg")
    # Pinnacle closing odds (a model feature; the 近期赛事 cards carry these).
    # Fall back to `sp` server-side if absent so the leg can still be scored.
    psc_home: float | None = Field(None, gt=1.0)
    psc_draw: float | None = Field(None, gt=1.0)
    psc_away: float | None = Field(None, gt=1.0)


class ParlayLegEcho(BaseModel):
    """Server-recomputed view of one leg (model P is authoritative)."""
    match_id: str
    league: str
    market_type: str
    outcome: str
    handicap_home: int | None = None
    sp: float
    model_p: float


class ParlayRecordRequest(BaseModel):
    """V12 W5 — compute (and optionally record) a HAND-PICKED 竞彩 串关.

    Unlike /recommend (engine auto-generates combos), this scores the exact
    legs the user selected: server recomputes each leg's model P → parlay hit
    P = ∏P, parlay odds = ∏ 竞彩 SP, EV, fractional Kelly stake (same kelly.py
    + lottery_rules pipeline as 单关/复式 so stakes are consistent). Distinct
    matches only; 2–8 legs (混合过关).
    """
    legs: list[ParlayLegInput] = Field(..., min_length=2, max_length=8)
    bankroll: float = Field(..., gt=0)
    kelly_fraction: float = Field(0.25, ge=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0)
    record_session: bool = False


class ParlayRecordResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    legs: list[ParlayLegEcho]
    k_legs: int
    hit_probability: float       # ∏ model_p
    odds: float                  # ∏ sp (竞彩 parlay payout multiplier)
    ev_per_unit: float           # hit_probability * odds - 1
    raw_kelly_stake: float       # pre-quantization
    stake: float                 # ¥2-quantized, ticket-capped
    passes_gate: bool            # meets JINGCAI thresholds (hit% + EV)
    recorded: bool
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False
    # Per-leg full predictions (match identity + 1X2 P + handicap_home for the
    # picked line). Recorded into single_predictions so V4 settlement can
    # bridge each leg's match_id → match_outcome (it keys off this table).
    single_match_predictions: list[SinglePrediction] = Field(default_factory=list)


class ManualBetRequest(BaseModel):
    """Post-V13 — record ONE user-chosen bet ("记此注").

    Records EXACTLY the outcome + real stake the user placed (NOT the model's
    best pick), INCLUDING −EV — the observation DB is the user's real betting
    history so ROI is honest. Settlement-compatible (see record_manual_bet).
    """
    league: str
    date: str
    home_team: str
    away_team: str
    market_type: Literal["1x2", "handicap"] = "1x2"
    handicap_home: int | None = None
    outcome: Literal["H", "D", "A"]
    odds: float = Field(..., gt=1.0)             # the 竞彩 SP for the picked outcome
    probability: float = Field(0.0, ge=0.0, le=1.0)  # model P (for EV display)
    stake: float = Field(..., gt=0.0)            # real money the user bet
    bankroll: float = Field(1000.0, gt=0)
    #: 这次下注所依据的 Pinnacle 价的**出处**('manual' / 'odds_api' / 'api_football')。
    #:
    #: 🚨 P0-6(2026-08-07)—— 前端从 `a06476a` 起就一直在送这个字段,但本模型没声明它,
    #: Pydantic 默认**静默丢弃**未声明字段 ⇒ 它从来没到过 recorder。链路后半段其实是通的:
    #: `record_manual_bet` 把 `bet` 当 request 传给 `insert_session`,后者调
    #: `store._request_odds_source(request)` 读的就是这个键。**断点只在这一行的缺席。**
    #:
    #: ⚠️ 缺省 None = 「不知道」,`_request_odds_source` 会如实写 NULL ——
    #: **绝不默认成 'api_football'**(那等于把「没告诉我」伪装成「我查过了」)。
    odds_source: str | None = None
    record_session: bool = False


class ManualBetResponse(BaseModel):
    recorded: bool
    ev: float
    outcome: str
    stake: float
    session_id: int | None = None


class JingcaiSpRequest(BaseModel):
    """体检 — one silent 竞彩 SP capture for the softness/staleness map. 竞彩
    freezes its SP (~23:00 daily) while Pinnacle keeps drifting to kickoff; the
    gap is the only place edge can live. Passive measurement — NOT a bet, no
    record flag. The user re-prices a match many times to verify, so the table
    upsert-latest keeps the canonical (nearest-kickoff) line per (match, market)."""
    match_date: str
    home_team: str
    away_team: str
    jc_home: float | None = None
    jc_draw: float | None = None
    jc_away: float | None = None
    psc_home: float | None = None
    psc_draw: float | None = None
    psc_away: float | None = None
    ou_line: float | None = None
    psc_over: float | None = None       # capture-time O/U — lets the CLV ledger reverse-fit
    psc_under: float | None = None      # the hhad cover-P at bet time (no look-ahead)
    fixture_id: int | None = None
    league: str | None = None
    kickoff_utc: str | None = None
    market: str = "had"
    handicap_home: int | None = None   # 竞彩 让球线 (market='hhad'); DC sign −1=主队让1球


class JingcaiSpResponse(BaseModel):
    recorded: bool = False


class SportteryRefreshResponse(BaseModel):
    """Result of the 🎯 刷新竞彩 on-demand sporttery harvest."""
    ok: bool = False
    reason: Optional[str] = None
    matches: int = 0
    mapped: int = 0
    unmapped: int = 0
    had: int = 0
    hhad: int = 0
    # 2026-07-09 — WHO got dropped, not just how many. harvest_to_db already
    # returns [{home_cn, away_cn, league_cn}] (sink report had it); the schema
    # silently swallowed it, so the UI could only show a count and the owner had
    # to reverse-engineer "SP 对不上" back to a dictionary gap (UEL Q1 case).
    unmapped_teams: list[dict] = []


class HealthCheckLatestResponse(BaseModel):
    """定时体检(`com.nutmeg.daily_health_check`)上一次的判定 —— 给面板读。

    ## 为什么要有这个端点(2026-08-07)

    体检的告警原本只走 `osascript` 桌面通知。实测**通知没送到** —— `osascript`
    退出码 0 但 macOS 静默丢弃(权限库 TCC 保护,连查都查不了)。
    ⇒ 一个上线当天就死掉、而且**死的时候看起来正常**的告警通道。

    面板是 owner 每天都看的表面,且不依赖任何系统权限。这里把判定送到那儿。

    ## ⛔ 契约:分不出「没红灯」和「没读到」

    * `ok=False` = **读不到/没跑完**,不是「没问题」。前端必须把它显示成**红**。
    * `stale` **只在 `ok=True` 时有意义** —— 读不到报告时它是 False,那不代表「新鲜」。
      前端的判据必须是 `!ok || stale`,不能只看其中一个。
    * `stale=True` = 报告太旧 ⇒ **cron 可能死了**。这是本端点存在的第二个理由:
      通道自己的失效必须可见。job 每天跑两次(09:45 / 21:00),笔记本睡眠时
      launchd 唤醒后补跑一次 ⇒ 阈值取 30h(容得下一整轮 miss + 一次睡眠)。
    * `reds` 是**全部**红灯,`new` 是基线里没有的那些。面板该突出的是 `new` ——
      已知红天天报就是噪音,三天内会被关掉(见 `configs/health_check_known_red.txt`)。
    """
    ok: bool = False
    detail: str | None = None       # ok=False 时的原因;或体检自己报的异常
    ran_at: str | None = None       # 体检跑完的本地时间(ISO)
    age_seconds: int | None = None
    stale: bool = False             # age 超阈值 ⇒ cron 可能死了
    exit_code: int | None = None
    reds: list[str] = []            # 本次全部红灯「节标题 | 判词」
    new: list[str] = []             # 不在基线里的(主信号)
    gone: list[str] = []            # 基线里有、这次没了(提醒剪基线)


class JingcaiUnmappedResponse(BaseModel):
    """上次竞彩抓取里因队名映射不到英文规范名而被【整场丢弃】的场次 — 被动可见性。

    和 ``SportteryRefreshResponse.unmapped_teams`` 同一份结论,区别只在触发方式:
    那个要 owner 主动点 🎯 刷新竞彩 才看得到,这个在开页时自己说出来。
    """
    # NB 邻居用 Optional[...],本模型用 `X | None`:同义,但 ruff(UP045)判 Optional
    # 为陈旧写法,而本仓要求「不新增 lint」→ 新代码走新写法,旧的留给统一迁移。
    ok: bool = False
    reason: str | None = None
    n_matches: int = 0            # 上次抓取到的在售总场次
    unmapped: list[dict] = []     # [{home_cn, away_cn, league_cn}] — 每个被丢的场
    gone: list[str] = []          # 整联赛 0 场入库的联赛
    partial: list[str] = []       # ["美职 2/4"] — 该联赛≥半数被丢
    age_seconds: int | None = None   # 这份结论的新鲜度(缓存距今)


class JingcaiRecommendRequest(BaseModel):
    """V12 W5 — 竞彩盘口推荐: run single + parlay + pool over the fixtures the
    user filled with 竞彩 SP (+ 让球) in 近期赛事.

    Same engine as /today-recommendations, but each fixture's ``odds_1x2`` /
    ``odds_handicap_*`` (= the 竞彩 SP the user typed) drive the EV instead of
    Pinnacle. Model P still uses psc (Pinnacle) as a feature. The caller should
    only include fixtures it actually filled 竞彩 odds for — fixtures missing
    ``odds_1x2`` would fall back to Pinnacle inside the engine, which is NOT the
    竞彩 frame. Returns a TodayRecommendationsResponse (the 💴 竞彩 board)."""
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1)
    bankroll: float = Field(1000.0, gt=0)
    include: list[Literal["single", "parlay", "pool"]] = Field(
        default_factory=lambda: ["single", "parlay", "pool"])
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    min_ev: float = Field(0.05, ge=-0.20, le=0.50)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    pool_n: int = Field(3, ge=2, le=8)
    record_session: bool = False


# ---------- Health ----------

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    artifact_loaded: bool
    artifact_path: Optional[str] = None

    # 2026-08-07 — "did an artifact load?" and "is it the one we meant?" are
    # different questions. `status`/`artifact_loaded` answer the first (can I
    # serve at all); these four answer the second (am I serving the right
    # model). The stale-default hole survived because only the first was ever
    # asked, and the wrong artifact answers it in the affirmative.
    #
    # `artifact_is_expected` has NO default on purpose: every construction site
    # must state a verdict, so a future branch cannot forget it into None and
    # have a falsy reading pass for "fine".
    artifact_is_expected: bool
    expected_artifact_path: Optional[str] = None
    artifact_base_path: Optional[str] = None      # pre-Layer-B dir
    artifact_path_source: Optional[str] = None    # "env" | "default"

    # 2026-08-07 (follow-up) — `artifact_is_expected` judges the BASE, and a
    # Layer B pointer legitimately redirects away from it. That exemption says
    # nothing about the *target*: a pointer at the right base aimed at the
    # 2025-06 LightGBM reads `artifact_is_expected=True`, `status="ok"`.
    # This field is what makes "a redirect is in effect" reportable at all;
    # `artifact_path` + `trained_at_utc` then say where to and how fresh.
    # Required, same reason as above: a branch that forgets it would report
    # falsy = "no redirect", which is the reassuring answer.
    artifact_redirected: bool

    trained_at_utc: Optional[str] = None
    training_cutoff: Optional[str] = None
    n_teams: Optional[int] = None
    n_leagues: Optional[int] = None
    # V5 W11: surface the active backend in health so dashboards can show
    # whether the running server is on `lightgbm` (V4 default) or `catboost`
    # (W7 opt-in).
    model_type: Optional[str] = "lightgbm"
    detail: Optional[str] = None


# ---------- /predictions/upcoming (V5 W11) ----------

class UpcomingPredictionsRequest(BaseModel):
    """Lightweight body for the predictions/upcoming endpoint.

    Same shape as RecommendRequest but without bankroll / Kelly knobs —
    callers (dashboard, scheduled cron, mobile app) just want the model's
    probability output, not parlay recommendations.
    """

    fixtures: list[FixtureOddsInput]


class UpcomingPredictionsResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    n_fixtures: int
    predictions: list[SinglePrediction]


# ---------- /recommend/single (V8 W6) ----------

class SingleRecommendRequest(BaseModel):
    """POST /v4/recommend/single body — 单关 (single-leg) flow.

    Same fixture shape as /v4/recommend (one row per match). The server
    runs `recommend_singles` (V6 W9) against the V5 W12 default artifact
    + lottery rules, returns at most `top_per_match` recommendations per
    fixture sorted by EV desc.
    """
    fixtures: list[FixtureOddsInput] = Field(..., min_length=1, max_length=50)
    bankroll: float = Field(1000.0, gt=0)
    top_per_match: int = Field(1, ge=1, le=3,
                                description="Max recommendations per fixture (default 1, max 3)")
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0,
                                       description="Per-ticket cap as fraction of bankroll")
    # V9 W3: see RecommendRequest.record_session
    record_session: bool = Field(False, description=
        "Opt-in observation recording. Requires NUTMEG_V4_OBSERVATION_DB "
        "env var on the server to actually persist.")


class SingleTicketResponse(BaseModel):
    match_id: str
    # V12 W7 — match identity so the 今日推荐 single board renders
    # "home vs away · league · date" directly (it reads these fields, unlike
    # the parlay/history renderers which parse match_id). Without them the
    # card showed "VS · undefined · undefined". Optional for back-compat.
    league: str | None = None
    date: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    market_type: Literal["1x2", "handicap_1x2"]
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    ev_per_unit: float
    stake: float                  # ¥2-quantized
    raw_kelly_stake: float        # pre-quantization (diagnostic)
    expected_return: float
    # V12 W8i — Pinnacle inputs echoed so the 今日推荐 card can record THIS pick
    # at the user's 竞彩 SP. The record endpoints recompute model P from these
    # (server never trusts a client-sent P); psc_over/under + handicap_home let
    # a 让球 pick re-derive its grid via /recommend/market-handicap. All optional
    # for back-compat (None when the source fixture lacked them).
    psc_home: float | None = None
    psc_draw: float | None = None
    psc_away: float | None = None
    psc_over25: float | None = None
    psc_under25: float | None = None
    # 体检 2026-07-03 Wave1 — the ACTUAL total line psc_over25/under25 are quoted
    # at. Without it the 今日推荐 record path hardcoded 2.5 → the server's
    # "authoritative" 让球 refit anchored on the wrong line → the RECORDED
    # P/EV/stake themselves were wrong (15/22 WC matches had non-2.5 lines).
    ou_line: float | None = None
    # 体检 P1#10 — Pinnacle snapshot timestamp (ISO) echoed from the source
    # fixture. The psc_* echoes above drive the card's 市场同意 chip + the 📌
    # record refit, so the 今日推荐 card shows their age (>2h → amber), same as
    # the 市场模式 card's freshness badge.
    odds_update: str | None = None
    handicap_home: int | None = None
    # V14 — market-reverse 让球 board (−3..+3) carried onto the prediction ticket
    # so the 今日推荐 boards can show a 让球胜平负 prediction with a line selector
    # (non-竞彩 / Pinnacle-de-vig handicap rule). Same shape the cup-market preds use.
    handicap_lines: list[HandicapLineProb] = Field(default_factory=list)
    # δ 范围闸三态 —— 与来源 `SinglePrediction.delta_scope` 逐字同值(直接抄,不重算)。
    delta_scope: Literal["applied", "out_of_scope", "missing"] = "missing"
    # V14 — international Asian Handicap (half-line, 2-way) board for the 让球
    # PREDICTION display. Real Pinnacle de-vig where quoted, DC fallback else.
    asian_handicap_lines: list[AsianHandicapLineProb] = Field(default_factory=list)
    # V11 P1-FE#5 — per-ticket fingerprint (12 chars). One single
    # ticket = a single (match_id, market, outcome) triple, so the
    # fingerprint identifies exactly that pick.
    selection_fingerprint: str | None = None


class SingleRecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    n_fixtures: int
    n_recommendations: int
    tickets: list[SingleTicketResponse]
    total_stake: float
    total_expected_return: float
    # V11 P1-FE#5 — same versioning treatment as parlays/pool.
    version_hash: str | None = Field(None, description=
        "12-char SHA1 prefix covering this response's picks. Frontend compares "
        "to its last-seen hash to detect when recs need a refresh.")
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


# ---------- /recommend/market-handicap (V12 W8 — 市场模式让球追踪) ----------

class MarketHandicapRequest(BaseModel):
    """POST /v4/recommend/market-handicap — record one 市场模式 让球 pick (J1 /
    cup) for tracking.

    The server RECOMPUTES the market-implied 让球 P from the Pinnacle inputs
    (de-vig 1X2 + O/U at ``ou_line``) — it never trusts a client-sent
    probability. For each outcome carrying a 竞彩 SP it computes EV, picks the
    highest-EV leg, and (when record_session=True AND the server DB gate is on)
    records it tagged model_type=market_handicap so AB/ROI reports slice it
    apart from model bets."""
    league: str
    date: date
    home_team: str
    away_team: str
    psc_home: float
    psc_draw: float
    psc_away: float
    # 2026-07-23 — 这三个 psc_* 的出处。手填 Pinnacle 的场景就走这个端点,所以这
    # 一条是整条溯源链最要紧的一环:没有它,手打的价和抓来的价在台账里长得一模一样。
    odds_source: str | None = None
    psc_over25: float | None = None
    psc_under25: float | None = None
    # Asian total line the over/under prices are quoted AT. Pinnacle's main J1
    # total is often a quarter line (2.25 / 2.75), not 2.5; the server anchors
    # λ_total to THIS line (push counted as half). Treating a 2.25 line as 2.5
    # biases λ_total ~+0.22 goals. Default 2.5 keeps existing callers unchanged;
    # the over/under value is simply the price at ou_line.
    ou_line: float = Field(2.5, gt=0.0)
    handicap_home: int
    odds_handicap_H: float | None = None
    odds_handicap_D: float | None = None
    odds_handicap_A: float | None = None
    bankroll: float = 1000.0
    kelly_fraction: float = 0.25
    record_session: bool = False


class MarketHandicapResponse(BaseModel):
    league: str
    date: date
    home_team: str
    away_team: str
    handicap_home: int
    # market-implied P(让胜/让平/让负) for this line, order [H, D, A]
    market_implied_p: list[float]
    # 体检 C1 (2026-07-01) — the WPO-de-vig 1X2 fair-P [H, D, A] (NOT 让球). The
    # reverse-calculator client used to recompute the 1X2 fair-P with BASIC
    # normalization, inflating longshot P and flipping −EV legs into false 🟢 +EV
    # (up to ~11pp). Exposing the server's WPO P lets the client use the same
    # de-vig the whole betting path uses.
    p_1x2: list[float] | None = None
    fair_odds: list[float]
    # EV/unit vs the supplied 竞彩 SP; None for outcomes with no SP given
    ev_per_unit: list[float | None]
    best_outcome: str | None = None  # "H"|"D"|"A" — highest-EV leg with a SP
    best_ev: float | None = None
    best_stake: float | None = None
    recorded: bool = False
    session_id: int | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False
    # V14 — 净胜球分组 for the reverse-calc card (same grid, READ tool not signal)
    margin_bands: list[MarginBand] = Field(default_factory=list)
    # 🚨 δ 联赛范围闸的**三态**,2026-08-17 上线。`applied` / `out_of_scope` / `missing`。
    #
    # ## 为什么把它放进回包
    #
    # 方案 A(覆盖外 ⇒ 不施加点估 δ + 吃 `_UNCAL_SE` 地板)的代价是**静默**:
    # 数字悄悄变了,没有任何东西喊。08-16 和 08-17 各因此漏了一个调用点,
    # 症状都是「让球 ± 带宽 10 倍」,而两次都是 owner 看着卡片报出来的。
    #
    # 唯一的可观测性曾是 `_SCOPE_STATS` —— **进程内计数器、重启归零、全仓零生产读者**,
    # 而且它数的是调用次数不是场次。⇒ 它不是可观测性,是自我安慰。
    #
    # ⛔ **为什么不改成漏传直接 422**:owner 红线「显示层降级不能 422 掉整张卡」。
    #    缓存的老 tab 打过来会拿 422 ⇒ 卡显示报错。⇒ 选「可见但不失败」。
    # ⚠️ 代价老实说:每个消费方多一个**必须被渲染**的字段,漏渲染 = 又一个静默。
    #    所以护栏 `test_delta_scope_badge.py` 断言前端确实画了它。
    delta_scope: Literal["applied", "out_of_scope", "missing"] = "missing"


class MarketRepriceRequest(BaseModel):
    """V14 — POST /v4/recommend/market-reprice. Re-price ONE 市场模式 card from
    a LIVE Pinnacle line the user typed by hand (API-Football mirrors Pinnacle
    only every few hours, so the auto-fed line can trail Pinnacle.com near
    kickoff). Pure compute: de-vig the 1X2 + reverse-fit the 让球 board exactly
    as the auto card does — NO recording, NO DB. The dashboard then swaps these
    P's into the card so display / 让球线 selector / EV / 📌 all use the live
    line. Reuses the validated implied_handicap_lines path (not a JS re-impl)."""
    psc_home: float
    psc_draw: float
    psc_away: float
    psc_over25: float | None = None
    psc_under25: float | None = None
    ou_line: float = Field(2.5, gt=0.0)
    # 🚨 2026-08-16 —— δ 联赛范围闸**必需**。缺了它 `_market_handicap_lines` 里
    # `r.get("league")` 得 None ⇒ 按未校准处理 ⇒ ±1/−2 线改吃 `_UNCAL_SE` 地板
    # (2×0.078 = 0.156,是覆盖内的 **10 倍**)⇒ 手填卡的让球 ± 带宽 10 倍、
    # 点估也少扣了 δ。**不报错、不红测试**,只是数字悄悄变了。
    # ⚠️ 可选(None)是**故意**的:老前端/老脚本不传时仍按方案 A 保守处理
    #    (不施加点估 δ + 宽带),而不是 422 掉整张卡。
    league: str | None = None


class MarketRepriceResponse(BaseModel):
    # de-vig fair 1X2 (multiplicative), order [home, draw, away]
    p_home_1x2: float
    p_draw_1x2: float
    p_away_1x2: float
    # δ₁ₓ₂ 逐腿判闸下界 —— 与 `SinglePrediction.onex_lo_*` **同名同源**(都由
    # `routes._onex_lo(fair)` 算),故意不另起名字:两个名字指同一个量是这个仓库
    # 反复踩过的坑。
    #
    # ⭐ 2026-08-08 补 —— 在此之前这个回包**没有**下界,后果不是「少个字段」:
    #   · 全新的手填卡(日乙唯一的路)⇒ `_boardLegs` 的 `lo ?? p` 回落成
    #     `evLo ≡ ev`,1X2 腿**零收缩**,而同一张卡的让球腿照吃 `p_*_lo`
    #     ⇒ 两类腿在同一个 evLo 排序里抢 argmax,v149 刚消灭的偏置原样复活;
    #   · 已有的自动卡手填后 ⇒ `p_*_1x2` 换成新盘口、`onex_lo_*` 停在旧盘口
    #     ⇒ 手填把 P 调低超过 2·SE 时 **evLo > ev**,下界变上界、判闸反而**变松**。
    #     同 `market_handicap.py` 那条「越不可信越容易变绿」的形状。
    # 同族病史:`_cupManRefreshDerived` 就是 2026-07-18 为「让球侧 p_*_lo 缺失」
    # 专门加的重算路径 —— 同一个洞换一条腿又犯了一次。
    onex_lo_home: float | None = None
    onex_lo_draw: float | None = None
    onex_lo_away: float | None = None
    # market-implied 让球 board across integer lines (same shape the card holds).
    # 元素 `HandicapLineProb` 自带 `p_*_lo` ⇒ 让球腿的下界一直是通的;
    # 上面那三个 `onex_lo_*` 补的正是同一个回包里**缺掉的另一半**。
    handicap_lines: list[HandicapLineProb]
    # 1X2 overround the user's typed odds imply — a sanity check the dashboard
    # surfaces so a fat-finger (e.g. swapped 主/客) shows an off vig.
    #
    # ⚠️ 只有**上**界有人看(`WIDE_BOOK_VIG=0.08`)。下界没人看,而下界才是手滑的
    # 指纹:`1.9/33.5/3.3`(小数点丢一位)⇒ overround −14.08%,一本负抽水的「盘」
    # 物理上不存在 —— 见 `impossible_book` 与 dashboard 的 `_isImpossibleBook`。
    overround: float
    # True ⇔ overround 落在物理上不可能的区间(见 `devig.is_impossible_book`)。
    # 服务端算,免得前端自己写一份阈值(同 δ 常数不许挪进 JS 的理由)。
    impossible_book: bool = False
    # 🚨 δ 联赛范围闸的**三态**,2026-08-17 上线。`applied` / `out_of_scope` / `missing`。
    #
    # ## 为什么把它放进回包
    #
    # 方案 A(覆盖外 ⇒ 不施加点估 δ + 吃 `_UNCAL_SE` 地板)的代价是**静默**:
    # 数字悄悄变了,没有任何东西喊。08-16 和 08-17 各因此漏了一个调用点,
    # 症状都是「让球 ± 带宽 10 倍」,而两次都是 owner 看着卡片报出来的。
    #
    # 唯一的可观测性曾是 `_SCOPE_STATS` —— **进程内计数器、重启归零、全仓零生产读者**,
    # 而且它数的是调用次数不是场次。⇒ 它不是可观测性,是自我安慰。
    #
    # ⛔ **为什么不改成漏传直接 422**:owner 红线「显示层降级不能 422 掉整张卡」。
    #    缓存的老 tab 打过来会拿 422 ⇒ 卡显示报错。⇒ 选「可见但不失败」。
    # ⚠️ 代价老实说:每个消费方多一个**必须被渲染**的字段,漏渲染 = 又一个静默。
    #    所以护栏 `test_delta_scope_badge.py` 断言前端确实画了它。
    delta_scope: Literal["applied", "out_of_scope", "missing"] = "missing"


# ---------- /recommend/pool (V8 W6) ----------

class PoolFixturePick(FixtureOddsInput):
    """Pool fixture row — same FixtureOddsInput shape plus a `pick` field.

    `pick` is the user's pre-decided outcome for that match, one of:
        "1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"
    Compound parlay then enumerates every C(M, N) ticket across those
    M picks.
    """
    pick: Literal["1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"]


class PoolRecommendRequest(BaseModel):
    """POST /v4/recommend/pool body — 复式 (M-select-N compound parlay)."""

    fixtures: list[PoolFixturePick] = Field(..., min_length=1, max_length=20)
    n: int = Field(..., ge=1, le=8,
                    description="Legs per ticket (1..8 per 竞彩 rules)")
    bankroll: float = Field(1000.0, gt=0)
    max_total_budget: Optional[float] = Field(None, gt=0,
                                               description="Optional pool-wide stake cap")
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction_per_ticket: float = Field(0.05, gt=0.0, le=1.0)
    # V9 W3: see RecommendRequest.record_session
    record_session: bool = Field(False, description=
        "Opt-in observation recording. Requires NUTMEG_V4_OBSERVATION_DB "
        "env var on the server to actually persist.")


class PoolLegResponse(BaseModel):
    """One leg of a pool ticket — like SelectionResponse but with the
    match_id + market_type baked in so the row is settleable.

    Post-V8 P1#5: previously PoolTicketResponse.legs used SelectionResponse
    which dropped match_id/market_type — the observation recorder couldn't
    write these rows in a settleable shape. PoolLegResponse closes that gap.
    """
    match_id: str
    market_type: Literal["1x2", "handicap_1x2"]
    outcome: Literal["H", "D", "A"]
    odds: float
    probability: float
    edge: float


class PoolTicketResponse(BaseModel):
    legs: list[PoolLegResponse]
    hit_probability: float
    combined_odds: float
    ev_per_unit: float
    stake: float                  # ¥2-quantized
    raw_kelly_stake: float
    expected_return: float
    # V11 P1-FE#5 — per-ticket fingerprint over its leg set.
    selection_fingerprint: str | None = None


class PoolRecommendResponse(BaseModel):
    generated_at_utc: str
    model: ModelInfo
    bankroll: float
    m: int                            # input pool size
    n: int                            # legs per ticket
    n_combinations: int               # = C(m, n)
    n_selected: int                   # tickets with stake > 0
    total_stake: float
    total_expected_return: float
    tickets: list[PoolTicketResponse]  # all enumerated, sorted by EV desc
    # V11 P1-FE#5 — top-level pool version hash.
    version_hash: str | None = None
    # 体检 A3 — gate was ON but the DB write THREW (≠ gate-off). UI shows red.
    record_failed: bool = False


# ---------- /today-recommendations (V10 W1 Track A) ----------

class TodayRecommendationsRequest(BaseModel):
    """POST /v4/today-recommendations body.

    V10 W1 Track A — the user-facing "land on the page and see
    recommendations" endpoint. Replaces the old engineer-facing flow
    that required the user to paste fixtures JSON.

    Server-side: fetches today's fixtures via api_football, runs the
    single + parlay recommend pipelines, returns a unified response.
    """

    date: Optional[str] = Field(None, description=
        "ISO YYYY-MM-DD; defaults to today (UTC).")
    leagues: list[str] = Field(
        default_factory=lambda: [
            # Top 5 European
            "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
            # Second-tier European
            "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
            "GER_2_BUNDESLIGA", "FRA_LIGUE_2",
            # Other major European
            "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA", "BEL_PRO_LEAGUE",
            # V12 W7 — JPN_J1 removed from the MODEL-scored board: it's
            # out-of-distribution (European-trained model; ~13pp off the sharp
            # J1 line). J1 is now served via market mode (Pinnacle de-vig).
        ],
        description=(
            "V4 canonical league codes (default: all 13 trained leagues). "
            "post-V11 audit (2026-05-25): expanded from EPL+La Liga to "
            "match the production model's full training coverage."
        ),
    )
    bankroll: float = Field(1000.0, gt=0,
        description="Total bankroll. Default ¥1000.")
    include: list[Literal["single", "parlay", "pool", "wc"]] = Field(
        default_factory=lambda: ["single", "parlay", "pool", "wc"],
        description=(
            "Which game types to include. V11 P1-FE#4: pool added; "
            "V11 post-ship: 'wc' added — when on a date with WC fixtures, "
            "surfaces today's WC 1X2 predictions as a side block "
            "(no auto-handicap; user enters SP in the WC tab to get 让球 "
            "recommendations). 'wc' is informational only — it doesn't "
            "contribute to total_recs / total_stake / weighted_ev."
        ),
    )
    # V11 P1-FE#4 — UI-facing risk + EV sliders. risk_preference is the
    # high-level dial; it maps to a kelly_fraction (0.15 / 0.25 / 0.40).
    # min_ev is the EV gate; recommendations below this are dropped.
    risk_preference: Literal["conservative", "balanced", "aggressive"] = Field(
        "balanced",
        description=(
            "User-facing risk dial. Maps to internal Kelly fraction: "
            "保守=0.15, 中=0.25, 激进=0.40. Explicit `kelly_fraction` "
            "overrides this when set non-default."
        ),
    )
    min_ev: float = Field(
        0.05,
        ge=-0.20,
        le=0.50,
        description=(
            "Minimum EV-per-unit threshold; recommendations with "
            "ev < min_ev are dropped. Default +5% matches the original "
            "JINGCAI_DEFAULT.min_ev_per_unit. UI offers -5% / 0% / +5% / +10%."
        ),
    )
    # carry-over from RecommendRequest for advanced overrides
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    min_hit_probability: float = Field(0.05, ge=0.0, le=1.0)
    min_kelly_stake: float = Field(2.0, ge=0.0)
    record_session: bool = Field(False, description=
        "Opt-in observation recording (see RecommendRequest.record_session).")
    # V12 W3 — on-demand fresh-odds pull. Normal polls read the cron-cached
    # Pinnacle odds (cheap). When the 竞彩 SP calculator's 🔄 刷新盘口 button
    # is pressed, the client sets this True so the server re-fetches odds
    # live (refresh_odds=True in _gather_rows) — capturing near-kickoff
    # Pinnacle for the model's market feature. A handful of calls per press;
    # well within the daily budget. Fixtures stay cached (only odds drift).
    refresh_odds: bool = Field(False, description=
        "Bypass the odds cache and pull live Pinnacle odds for this request.")
    # 2026-07-09 — when a 🔄 refresh runs, spend API quota ONLY on matches 竞彩
    # lists as bettable (full HAD SP on file). Skips whole non-竞彩 leagues (Odds
    # API credit) + non-竞彩 fixtures (API-Football /odds). Default True (the 「只投
    # 竞彩」 DNA); the 全刷 escape hatch sets it False. No effect unless refresh_odds.
    bettable_only: bool = Field(True, description=
        "On a refresh, only pull odds for 竞彩-bettable matches (skip non-竞彩 to save quota).")
    # V11 P1-FE#4 — pool sizing (when "pool" in include)
    pool_n: int = Field(
        3,
        ge=2,
        le=8,
        description=(
            "N legs per pool ticket (M-select-N). Default 3 (most popular). "
            "Pool generation only runs when at least N matches pass the EV gate."
        ),
    )
    # V11 P1-FE#5 — when set, the server compares the new response's
    # version_hash against this one; if different, it includes a `diff`
    # field describing which picks changed. The frontend supplies its
    # last-known hash via this param.
    prev_version: str | None = Field(
        None,
        description=(
            "Caller's last-known version_hash. When provided and the new "
            "hash differs, the response carries a `diff` block (added "
            "fingerprints / removed fingerprints / odds_changed flag)."
        ),
        min_length=8,
        max_length=64,
    )


class TodaySummary(BaseModel):
    """Aggregated stats across all recommendation types."""
    total_recs: int
    total_stake: float
    weighted_ev: Optional[float] = Field(None, description=
        "Stake-weighted average EV. None if total_stake == 0.")


class PlayoffWarning(BaseModel):
    """V12 W0 — one fixture flagged as likely playoff/barrage context.

    The model has no playoff feature; SP buyers (Pinnacle sharps) do
    price-adjust but we can't decompose vig. Dashboard renders these as
    a ⚠️ banner so the user knows model output is uncalibrated for
    end-of-season high-stakes fixtures.
    """
    league: str = Field(..., description="V4 canonical league code, e.g. FRA_LIGUE_1")
    home_team: str
    away_team: str
    date: str = Field(..., description="ISO YYYY-MM-DD")
    context: str = Field(..., description=(
        "Short human-readable label, e.g. 'Ligue 1 barrage de relegation'."
    ))
    model_bias_note: str = Field(..., description=(
        "Why the model is wrong-for-this-context — surfaced in banner tooltip."
    ))


class TodayRecommendationsDiff(BaseModel):
    """V11 P1-FE#5 — describes what changed vs the caller's prev_version.

    The frontend uses this to:
      - Show "推荐已更新" banner with a short summary
      - Add a 已更新 badge next to each rec whose selection_fingerprint
        is in `added_fingerprints` but not in the caller's prior set

    All lists are sorted for stable diffs.
    """
    prev_version: str = Field(..., description="echoed from the request")
    current_version: str
    odds_changed: bool = Field(False, description=
        "True when the fixture odds digest differs even though picks are stable.")
    # Selection fingerprints present in the current response but NOT in
    # the caller's previous one (i.e. newly recommended picks).
    added_fingerprints: list[str] = Field(default_factory=list)
    # Fingerprints that were in prev but no longer present (picks dropped).
    removed_fingerprints: list[str] = Field(default_factory=list)
    # Human-readable summary for the banner — server-generated so zh/en
    # is consistent regardless of locale toggle state.
    summary: str = Field(..., description=
        "One-line summary, e.g. '2 picks changed' / 'odds moved on 1 leg'")


class TodayRecommendationsResponse(BaseModel):
    """Unified response for the V10 landing flow.

    Each game-type field is None when:
      (a) excluded via request.include, OR
      (b) the underlying engine returned 0 recommendations.

    `fixtures_fetched` reports how many fixtures the server pulled
    for the date+leagues (regardless of whether they passed the EV gate).
    """
    generated_at_utc: str
    date: str
    leagues: list[str]
    bankroll: float
    fixtures_fetched: int
    single: Optional[SingleRecommendResponse] = None
    parlay: Optional[RecommendResponse] = None
    # V11 P1-FE#4 — third option in the today landing tab.
    # Strategy B (locked 2026-05-25): filter fixtures to ev_per_unit ≥ min_ev,
    # pick max-EV market per match, generate C(M, N) pool of N-selections.
    pool: Optional[PoolRecommendResponse] = None
    # V11 post-ship — WC 1X2 model predictions for the same date.
    # Surfaced informationally; doesn't contribute to total_recs/stake/ev
    # (no handicap → no EV computation possible until user enters SP in the
    # WC tab). Frontend renders this as a "🏆 WC 板块" with a CTA that
    # deep-links to the WC tab. None when no WC fixtures or "wc" excluded.
    wc: Optional[WcPredictionsResponse] = None
    summary: TodaySummary
    # V11 P1-FE#5 — top-level version hash covering single + parlay + pool
    # picks + the fixture odds digest. Frontend polls every 30s and shows
    # a "推荐已更新" banner when this changes.
    version_hash: str | None = Field(None, description=
        "12-char SHA1 prefix. Stable as long as picks and odds don't change.")
    # When the client passes `prev_version` and the hash differs, the
    # server fills in a diff describing what changed (per-rec changed
    # selection_fingerprints + odds_changed flag).
    diff: Optional["TodayRecommendationsDiff"] = None
    # V12 W0 (2026-05-27) — fixtures detected as falling within a known
    # playoff / barrage / end-of-season high-stakes window. Model has no
    # feature for this; banner alerts the user. See data/playoff_context.py.
    # Empty list when no fixtures hit a window — banner stays hidden.
    playoff_warnings: list[PlayoffWarning] = Field(
        default_factory=list,
        description=(
            "Fixtures in a known playoff/barrage date window. Coarse "
            "hard-coded heuristic — V13 P1 will replace with a real "
            "training feature."
        ),
    )
    # V12 W3 — model P(H/D/A) + Pinnacle odds for EVERY fetched fixture
    # (not just the gate-passing ones in `single`), so the dashboard's
    # 竞彩 SP calculator can compute live EV against user-entered 竞彩 SP.
    # Probabilities are market-agnostic (Pinnacle-informed); the client
    # multiplies P by the user's 竞彩 SP for EV. Empty when no fixtures.
    single_match_predictions: list[SinglePrediction] = Field(default_factory=list)


# ---------- /predictions/wc (V10 W1 Track B Day 5) ----------

class WcMatchPrediction(BaseModel):
    """One WC fixture's predicted 1X2 probabilities + diagnostics.

    Mirrors the JSON shape that `nutmeg-wc-predict` CLI outputs per
    fixture. `source` is "blend(α=0.4)" when Pinnacle was available,
    "lightgbm_only" when only the model contributed.
    """
    fixture_id: int
    kickoff_utc: str
    round: Optional[str] = None
    home_team: str
    away_team: str
    home_elo: float
    away_elo: float
    elo_diff: float
    home_adv: float
    has_pinnacle: bool
    psc_home: Optional[float] = None
    psc_draw: Optional[float] = None
    psc_away: Optional[float] = None
    p_home: float
    p_draw: float
    p_away: float
    # Pure-Elo baseline for transparency (always populated)
    p_home_elo_only: float
    p_draw_elo_only: float
    p_away_elo_only: float
    source: str


class WcPredictionsResponse(BaseModel):
    """Wraps `nutmeg-wc-predict` output for the dashboard."""
    date: str
    season: int
    n_fixtures: int
    blend_alpha: float
    elo_snapshot: Optional[str] = None
    host_country_hint: dict[str, float] = Field(default_factory=dict)
    predictions: list[WcMatchPrediction]
    generated_at_utc: str


# ---------- /predictions/wc-upcoming (V12 W0 — 2026-05-28) ------------

class WcUpcomingPick(BaseModel):
    """One single-leg pick across the lookahead date window.

    Format intentionally mirrors `SingleTicketResponse` for league
    matches so the dashboard render helpers can be reused — but the
    underlying model is the WC-specific Elo+Pinnacle blend
    (NationalTeamModel α=0.4), not CatBoost.

    Only 1X2 outcomes here; the existing Path A++ handicap form
    handles 让球 on a per-match basis (the lookahead is a "show me
    the best NEXT few days" feature, not an enumeration of every
    market).
    """
    fixture_id: int
    kickoff_utc: str        # ISO with timezone
    days_until_kickoff: int  # 0 = today, 1 = tomorrow, etc.
    home_team: str
    away_team: str
    outcome: str = Field(..., description="'H' / 'D' / 'A' — 1X2 selection")
    hit_probability: float
    odds: float = Field(..., description="Pinnacle decimal odds")
    ev_per_unit: float
    stake: float = Field(..., description="Kelly-sized recommended stake (¥)")
    source: str = Field(..., description="'blend(α=0.4)' or 'lightgbm_only'")


class WcUpcomingResponse(BaseModel):
    """Top-N WC single-leg picks across the next N days, sorted by
    hit_probability descending. See `predictions_wc_upcoming` endpoint."""
    date_start: str        # ISO YYYY-MM-DD (today)
    date_end: str          # ISO YYYY-MM-DD (today + days - 1)
    days: int
    n_fixtures_scanned: int
    n_picks_after_ev_gate: int
    picks: list[WcUpcomingPick]
    blend_alpha: float
    generated_at_utc: str


# ---------- /recommend/wc/single (V11 post-ship — Path A++ hybrid) ----

class WcFixtureRecInput(BaseModel):
    """One WC fixture for the multi-market recommendation endpoint.

    Inputs the user provides per fixture:
    - Identity + Pinnacle 1X2 (for NationalTeamModel reverse-mapping)
    - 让球 line + 竞彩 SP odds (the actual bet market)

    All three handicap odds fields must be present together; if any
    is missing, the endpoint falls back to pure-model handicap probs
    (no Bayesian blend).
    """
    fixture_id: int
    home_team: str = Field(..., min_length=1)
    away_team: str = Field(..., min_length=1)
    kickoff_utc: str
    # Pinnacle 1X2 — model reverse-map input (REQUIRED for path A++)
    psc_home: float = Field(..., gt=1.0)
    psc_draw: float = Field(..., gt=1.0)
    psc_away: float = Field(..., gt=1.0)
    # 竞彩 整数让球 line + SP odds — the actual bet market
    handicap_home: int = Field(..., ge=-5, le=5,
        description="主队 让球数 (正 = 主队 受让, 负 = 主队 让球)")
    odds_handicap_H: float = Field(..., gt=1.0)
    odds_handicap_D: float = Field(..., gt=1.0)
    odds_handicap_A: float = Field(..., gt=1.0)


class WcSingleRecRequest(BaseModel):
    """POST /v4/recommend/wc/single body.

    Path A++ hybrid: runs NationalTeamModel for 1X2, reverse-maps to
    (λ_h, λ_a) under a WC-mean total-goals prior, computes model-side
    handicap probs via DC grid, blends with market-implied (dewedged)
    handicap probs at alpha=0.4 (matching the 1X2 blend convention).

    Returns one recommendation per fixture per market: 让球胜 / 让球平 /
    让球负 are scored independently; the server filters to outcomes with
    EV ≥ ``min_ev``.
    """
    fixtures: list[WcFixtureRecInput] = Field(..., min_length=1, max_length=20)
    bankroll: float = Field(1000.0, gt=0)
    kelly_fraction: float = Field(0.25, gt=0.0, le=1.0)
    max_stake_fraction: float = Field(0.05, gt=0.0, le=1.0,
        description="Per-ticket cap as fraction of bankroll")
    min_ev: float = Field(0.05, ge=-0.20, le=0.50,
        description="EV-per-unit floor; outcomes below this are dropped")
    blend_alpha: float = Field(0.4, ge=0.0, le=1.0,
        description="Model weight in the model+market handicap blend "
        "(0=pure market, 1=pure model; default 0.4 matches WC 1X2 blend)")
    host_country: Optional[str] = Field(None,
        description="Optional 3-letter code (e.g. 'USA' for WC 2026 host) "
        "passed to NationalTeamModel for host-advantage")
    host_advantage: float = Field(50.0,
        description="Elo points added for host country")
    # V11 post-ship — A/B observation hook (mirrors single/parlay/pool).
    # Two gates required for a real write: server NUTMEG_V4_OBSERVATION_DB
    # env var + this request flag. Recorded outcomes settle via the regular
    # auto-settle pipeline once a WC match outcome lands in match_outcomes.
    record_session: bool = Field(False,
        description="Opt-in observation recording for A/B / ROI tracking. "
        "Server-side recording also requires NUTMEG_V4_OBSERVATION_DB env.")


class WcRecommendationOutcome(BaseModel):
    """One row in WcSingleRecResponse.recommendations — the engine
    surfaces up to 3 outcomes per fixture (让胜, 让平, 让负); only the
    ones passing min_ev get a non-zero stake."""
    outcome: Literal["H", "D", "A"]
    p_final: float = Field(..., description="Final blended probability")
    p_model: float = Field(..., description="Model-only (DC reverse-mapped)")
    p_market: Optional[float] = Field(None,
        description="Market-implied (dewedged from SP). None if SP missing.")
    odds: float
    ev_per_unit: float
    kelly_fraction: float = Field(..., description="Full Kelly fraction "
        "(server applies kelly_fraction × kelly_fraction_param × bankroll)")
    stake: float = Field(..., description="¥2-quantized recommended stake")
    expected_return: float


class WcSingleRecMatch(BaseModel):
    """One fixture in the WC recommendation output."""
    fixture_id: int
    home_team: str
    away_team: str
    kickoff_utc: str
    handicap_home: int
    # Surfaced for transparency / diagnostics
    p_1x2_blended: list[float] = Field(..., description="The blended 1X2 from "
        "wc_predict (model + Pinnacle); the reverse-map input")
    inferred_lambda_home: float = Field(..., description="λ̂_h from 1X2 reverse-map")
    inferred_lambda_away: float = Field(..., description="λ̂_a from 1X2 reverse-map")
    # The 3 让球 outcomes — those with stake > 0 are the recommendations
    outcomes: list[WcRecommendationOutcome]


class WcSingleRecResponse(BaseModel):
    generated_at_utc: str
    bankroll: float
    n_fixtures: int
    n_recommendations: int = Field(..., description=
        "Outcomes with stake > 0 across all fixtures")
    matches: list[WcSingleRecMatch]
    total_stake: float
    total_expected_return: float
    blend_alpha: float
    lambda_total_prior: float = Field(..., description=
        "Total-goals prior used for the 1X2 → λ reverse-map (WC mean ~2.6)")


# ---------- /rules (V6 W10) ----------

class LotteryRulesResponse(BaseModel):
    """Snapshot of the currently active LotteryRules.

    Returned by GET /api/v4/rules so the dashboard / external tools can
    surface accurate, in-sync rule constants (¥2 unit, ¥20k cap, 31.5%
    vig, 5% EV threshold) without hard-coding them client-side. Changes
    in `combo.lottery_rules.JINGCAI_DEFAULT` propagate automatically.
    """

    stake_unit: float = Field(..., description="最小投注单位 (¥)")
    max_ticket_stake: float = Field(..., description="单注最高金额 (¥)")
    max_period_stake: float = Field(..., description="单期累计上限 (¥)")
    min_parlay_legs: int = Field(..., description="混合过关最少串关数")
    max_legs_per_ticket: int = Field(..., description="混合过关最多串关数")
    payout_ratio: float = Field(..., description="平均派奖率 (e.g. 0.685)")
    vig: float = Field(..., description="庄家抽水率 = 1 - payout_ratio")
    min_ev_per_unit: float = Field(..., description="推荐门槛: 单位投注最小 EV")
    min_hit_probability: float = Field(..., description="推荐门槛: 最小命中率")
    label: str = Field(default="中国体彩 · 竞彩足球",
                       description="规则集名称 (供 UI 展示)")
