# V13 候选: 数据质量升级 — 6 个平台 ROI 评估

_2026-05-26 · 用户决定: 维持竞彩 SP 现状 (以 Pinnacle signal 为主), 下一步看数据质量升级_

---

## 0. 现在的数据栈基线

| 来源 | 类型 | 月成本 | 用途 |
|---|---|---:|---|
| **football-data.co.uk** | 历史 CSV (含 Pinnacle PSC) | $0 | 主训练数据 (5 季 × 14 联赛) |
| **API-Football** | 实时 fixtures + lineups + injuries + odds | ~$20 | cron 每日 ingest |
| **The Odds API** | 多 book 历史 odds | $0-50 | 杯赛 odds 回填 (V11 P1#20) |
| **clubelo.com** | 俱乐部 Elo | $0 (抓取) | Elo 特征 |
| **understat.com** | xG-lite + shots | $0 (抓取) | xG 代理特征 |
| **eloratings.net** | 国家队 Elo | $0 (抓取) | WC 模型 + Path A++ |

**总月成本: ~$20-70**

---

## 1. 当前数据短板 (按对 model 影响)

| # | 短板 | 现状 | log-loss 改善期望 |
|---|---|---|---:|
| 1 | **真 xG 不存在** | 用 shots + SOT 拼凑的 xg-lite | -0.005 ~ -0.010 |
| 2 | **阵容数据浅** | API-Football 名单 + injuries 但球员质量未量化 | -0.002 ~ -0.005 |
| 3 | **开盘价没拿** | 只有 closing 价 (PSC) | V5 W5 market_dynamics ablation 负 |
| 4 | **裁判数据 0** | 无 | +0.001 (噪音内) |
| 5 | **天气数据 0** | 无 | +0.001 (噪音内) |
| 6 | **比赛战术数据** (传球网络, pressing) | 0 | 大但贵到几乎无法获取 |

**最大短板是 #1: 真 xG** — 单独这一项就能让 model 追平 Pinnacle (当前 +0.0056 log-loss 差距)。

---

## 2. 6 个候选平台 (按 ROI 排序)

### 🥇 #1 FBref / Sports Reference

**类型**: 免费 scrape (rate-limited)  
**类别**: 真 xG + advanced stats  
**月成本**: $0

**是什么**: Sports Reference 系的足球数据站, 暴露 StatsBomb 数据
- 历史 xG, npxG, xA, shots, key passes, pressures
- 14 联赛 + UCL/UEL 5+ 季覆盖
- Per-team + per-player

**为什么是头号选择**:

| 维度 | 现 xg-lite | FBref 真 xG |
|---|---|---|
| 输入 | 总射门 + 射正 | 每脚射门的 shot quality (位置, 类型, 防守压力) |
| 准确性 | ~60% 重合实际 xG | ~95% StatsBomb 同步 |
| 估计 log-loss 改善 | (现有 -0.003 已贡献) | 额外 **-0.005 ~ -0.010** |
| 额外特征 | 无 | + possession, deep completions, PPDA |

**工程量**: 3-4 天
1. 写 `nutmeg-ingest-fbref` CLI
2. 处理反爬 (rate limit, user-agent rotation, ≥3 秒/请求)
3. 重写 `xg_lite.py` 为真 `xg.py` 用 FBref 数据
4. 一次性回填 14 联赛 × 5 季 (~10,000 比赛, 5-7 天 wall clock 拉取)
5. Walk-forward 验证 + 替换决策

**风险**:
- 🟡 中: FBref 偶尔改版 / ban scraper IP (历史上稳定, 比 transfermarkt 好)
- 🟢 低: 数据本身质量高 (StatsBomb 出处)
- 🟡 中: 5-7 天拉取期, 需 robust resume + 缓存

**Ship gate**: log-loss vs current baseline 改善 ≥ -0.003 (walk-forward, multi-season).

---

### 🥈 #2 StatsBomb Open Data

**类型**: 免费官方 GitHub repo + Python SDK  
**类别**: 高质量 event data, 限国际赛 + 部分顶级联赛  
**月成本**: $0

**是什么**: StatsBomb 自己开源的数据
- 完整 360° event data (传球, 射门, 跑动, pressures)
- 覆盖范围:
  - World Cup 2018, 2022
  - Euro 2020, 2024
  - 部分 Premier League seasons
  - 部分 La Liga seasons (Messi/Barca era)
  - Champions League final 2022

**对 Nutmeg 的具体价值**:
- ⚡ **直接解决 WC 训练集 128 场太小的问题**
- WC 2018/2022 我们已有, 但 event-level 数据没用上
- 加上 WC 2014 + EURO 2020/2024 = 192 → ~250 训练样本 (+95%)
- 每场 360 events 深度数据让 NationalTeamModel 提升空间大

**工程量**: 2-3 天
1. `pip install statsbombpy` (官方 Python SDK)
2. 写 `nutmeg-ingest-statsbomb-events` 把 event data 聚合成 per-team-match aggregated stats
3. 注入 WC training frame, 重训 NationalTeamModel
4. Walk-forward 验证 WC 2018/2022 backtest

**短板**:
- ❌ 不解决日常 14 联赛覆盖问题 (它只有 WC/Euro + 极少 PL/La Liga)
- ❌ 限国际比赛 / 部分顶级联赛 — 不能替代 FBref

**Ship gate**: WC backtest log-loss 改善 ≥ -0.005 vs 当前 NationalTeamModel.

---

### 🥉 #3 Transfermarkt

**类型**: 免费 scrape (有 ToS 风险)  
**类别**: 球员市值 + 详细伤病史  
**月成本**: $0

**是什么**: 全球球员 transfer + market value + injury 数据库
- 球队总市值, 主力 vs 替补价值差
- 完整伤病史 + 严重程度 + 出场缺失场数
- 球员档案 (年龄, 位置, 当前俱乐部)

**对 Nutmeg 的价值**:
- 当前 `recent_n_injuries` 只数**人数**, 不知道**伤的球员重要性**
- 比如 EPL 某队 "3 人伤" 可能是 3 个替补 (无所谓) 或 3 个主力 (伤筋动骨)
- Transfermarkt 市值差能区分

**工程量**: 5-7 天
1. 反爬复杂 (Cloudflare + 严格 rate limit, 3-5s/req)
2. 需要写 robust scraper + 缓存 + retry logic
3. team_canonical 映射 (transfermarkt 用德语队名 — 跟我们 V8 W1 别名 dict 不同源)
4. 训练集回填会很慢 (~5,000 团队 × 5 季, 多周拉取)
5. 新 feature: `lineup_home_market_value_share` 等 2-4 列

**风险**:
- 🔴 ToS 明确禁止商业 scraping (个人自用是 grey zone)
- 🟠 反爬较激进, 维护成本 1-2 天/年
- 🟡 数据质量高但门槛比 FBref 高

**Ship gate**: lineup-aware artifact + transfermarkt 特征 log-loss 改善 ≥ -0.001.

---

### #4 Open-Meteo / Weather APIs

**类型**: 免费 API (无 key)  
**类别**: 历史 + 实时天气  
**月成本**: $0

**对 Nutmeg 的价值**:
- 雨天平均比赛减 ~0.1-0.2 进球 (literature)
- 但 **Pinnacle 已经在 closing price 里 price in 了**
- 预期 log-loss 改善 ~0.001 max, 可能负 due to noise

**工程量**: 1-2 天 (前提 stadium_features.py 死码先激活, 又是几天)

**为什么排第 4**:
- 收益薄
- 需要先激活 `stadium_features.py` (位置数据) — 那是 dead code 状态 (V11 Phase 0)
- 即便都接上, 收益低
- 但**快、免费、低风险** — V13 Phase 1 时 1 天能落

---

### #5 Betfair Exchange API

**类型**: 免费 API + 复杂 auth  
**类别**: 实时市场撮合价 + volume  
**月成本**: $0 (free tier 够个人用)

**是什么**: 全球最大博彩交易所
- 不同于 Pinnacle (单边报价), Betfair 是 P2P 撮合
- "**实际撮合到的价格**" 比 closing line 更接近真实概率
- 流动性也是信号 (大资金进场 = 强信号)

**对 Nutmeg 的价值**:
- 进一步提高市场特征质量 (替代 / 补充 Pinnacle PSC)
- "Match odds traded volume" 是 closing-line value 的强代理

**工程量**: 5-8 天
1. Betfair API 注册 (英国账号 + KYC, **中国用户难**)
2. OAuth + cert-based auth
3. 数据规模大 (need to subscribe to live stream for top leagues)
4. ToS 允许个人 analytical use

**短板**:
- 🔴 中国用户开账户难
- 🟠 工程复杂度高
- 🟡 工程量大于收益

---

### #6 Football-Data.org (注意: 不是 .co.uk!)

**类型**: 付费 API  
**类别**: fixtures + standings + 部分 stats  
**月成本**: ~$20

**为什么不推荐**:
- 跟 API-Football 大量重叠
- 覆盖比 API-Football 少
- 价格类似
- **重复投资, 不解决新问题**

⛔ 跳过。

---

## 3. 升级后预期效果

| Stage | log-loss vs Pinnacle | hit-rate vs Pinnacle | 实战 ROI 改善期望 |
|---|---:|---:|---:|
| **现在 (V11 ship)** | +0.0056 (略差) | -0.12pp | unknown (0 数据) |
| + FBref 真 xG | +0.0005 ~ -0.0001 (追平甚至略胜) | +0.0 ~ +0.5pp | +1-2pp ROI? |
| + StatsBomb WC | 仅影响 WC 准度 | WC 期间 +1-2pp | 限 WC 期 |
| + Transfermarkt 重大伤 | -0.0005 ~ -0.0010 | +0.1-0.3pp | +0.5pp ROI |

**估算极限**: 接 FBref + Transfermarkt 后 model 大致能持平 Pinnacle。**模型不会比 Pinnacle 强**, 但 vig 0% 的 Pinnacle 标尺达到了, 是质的飞跃。

但仍然: **EV 还是受限于你能拿到的市场**。Pinnacle-tier 准确性 + 竞彩 13% vig 出来的 EV, 跟 Pinnacle-tier + Pinnacle 4% vig 是两个世界。

---

## 4. 推荐执行顺序

### 🔴 P0 — 先做这个 (V13 W1 候选)

**FBref 真 xG 接入** (3-4 天, FREE)

**理由**:
1. ML 栈最大短板就是 xg-lite
2. log-loss 改善期望 -0.005 ~ -0.010 (单这一项让 model **追上 Pinnacle**)
3. 完全免费
4. 不依赖任何还没启动的工作 (cron / V12 W3 / ROI verdict 都不阻塞)
5. 同样的工程框架可以将来扩到 Transfermarkt

### 🟠 P1 — WC 期间紧前做

**StatsBomb Open Data 扩 WC 训练样本** (2-3 天, FREE)

**理由**:
1. WC 2026 还有 16 天开赛 (2026-06-11)
2. 128 → ~250 训练样本 (+95%)
3. 每场 event-level 数据让 NationalTeamModel 提升空间大

### 🟡 P2 — 中期 (V13/V14)

**Transfermarkt 球员市值** (5-7 天, FREE 但反爬+ToS 风险)

**理由**:
- 当前 `recent_n_injuries` 是 count, 不是 weight by 球员重要性
- 比 weather / referee 的预期改善大 5-10 倍
- 但反爬维护成本要 budget 进

### ⏸️ 暂不投入

| 项 | 不做的理由 |
|---|---|
| StatsBomb 商业 | €50k+/年, ROI 不够 |
| Wyscout | 同上 |
| Opta/Sportradar | 不卖给个人 |
| 天气 API | 收益太薄, 先做高 ROI 的 |
| Football-data.org | 与 API-Football 重叠 |
| Betfair Exchange | 中国账户问题 + 工程复杂 |

---

## 5. 触发条件 (什么时候启动 V13)

**不要现在就启动**。等待信号:

| 信号 | 行动 |
|---|---|
| **4 周 ROI verdict 正且 ≥ +5%** | ✅ 启动 FBref (V13 W1) → model 升级解锁更多机会 |
| **ROI 正但 < +5%** | ✅ 同上 (vig 没吃光 model edge, FBref 提高 edge) |
| **ROI 0 或负** | ❌ 不投 FBref, 先解决 model 根本问题 |
| **WC 开赛前 (< 7 天)** | ⚡ 优先 P1 StatsBomb Open, 不等 ROI |

---

## 6. Ship Gate (V13 真正 ship 的标准)

无论选哪个数据源, V13 ship gate:

1. ✅ 数据 ingest CLI 通过本地 dry-run (no API budget 超支)
2. ✅ 新 features 在 `pipeline.py` 接通 + `--with-fatigue` 风格 flag
3. ✅ Walk-forward log-loss 比 baseline 改善 ≥ ship-gate 阈值 (FBref -0.003, Transfermarkt -0.001)
4. ✅ 3-chunk in-season stability test (P1#18 同款) 没有 chunk 显示 < -10pp ROI
5. ✅ 至少 3 季历史训练数据
6. ✅ 守门测试: 数据源失效不应该 break production (graceful fallback to old features)

---

## 7. 不做的事 (明确范围)

- ❌ 不买 StatsBomb / Wyscout / Opta 商业 license — €50k+/年, ROI 不够
- ❌ 不做 Football-Data.org — 与 API-Football 重叠
- ❌ 不做 Betfair Exchange — 中国账户问题
- ❌ 不写竞彩官方爬虫 — ToS + 法律风险 (用户已明确 deferred)
- ❌ 不做单纯的 weather/referee scrape — 收益薄

---

## TL;DR

| Rank | 平台 | 类型 | 月成本 | 工程 | 预期 log-loss 改善 |
|---|---|---|---:|---:|---:|
| **#1** | **FBref** (真 xG) | 免费 scrape | $0 | 3-4 天 | **-0.005 ~ -0.010** |
| **#2** | **StatsBomb Open** (WC) | 免费 SDK | $0 | 2-3 天 | -0.005 (限 WC) |
| #3 | Transfermarkt (伤病重) | 免费 scrape | $0 | 5-7 天 | -0.001 ~ -0.002 |
| #4 | Open-Meteo (天气) | 免费 API | $0 | 1-2 天 | ~0 (噪音内) |
| #5 | Betfair Exchange | 免费 API | $0 | 5-8 天 (复杂) | -0.002 ~ -0.003 |
| ❌ | Football-Data.org | 付费 | $20 | 1-2 天 | 0 (重叠) |

**核心建议**: 当前不动；等 4 周 ROI verdict 出来再决定 V13 W1 启动哪个。如果 ROI 正, **FBref 是头号选择** (3-4 天工程 + 免费 + 让 model 追平 Pinnacle)。
