# 测试卡:冻结缺口 ∝ 冻结→开球时长(深夜欧洲场最大)

**状态:🟡 data-gated(等秋天受训联赛 + 攒够已结算腿)** · 记于 2026-06-24 · 派生自 [[sharp_money_market_microstructure]] §4/§7 + `parlay_soft_water_research.md` §6

> **一句话**:竞彩 23:00 行政冻死,Pinnacle 继续吸 sharp 钱把价磨向有效到开球。软水 EV 活在这条缝里。**可证伪假设:缝(竞彩 vs Pinnacle 收盘的 CLV)随「冻结→开球」小时数单调变大,深夜欧洲场最大。** 机器已就位,到秋天喂数据即出结论。

---

## 1. 假设(带符号,可证伪)

**H1(主):** 对受训欧洲联赛的竞彩腿,`CLV(竞彩SP vs Pinnacle收盘)` 随 **`freeze_to_ko_hours`(竞彩冻结到开球的小时数)单调改善**(越不负 / 越正)。

**H1a(强形式):** **深夜欧洲场**(北京 KO 03:00–05:00)的 CLV **显著优于**同日**下午/傍晚亚洲场**(北京 KO 16:00–22:00)。

**证伪条件:** CLV 在各 `freeze_to_ko_hours` 桶间**持平**(无单调、深夜桶不优)→ H1 假,冻结时长与缝大小无关 → 砍掉「按开球时段择时/择场」这个角度。

---

## 2. 机制(为什么该这样)

1. 竞彩 SP ~**23:00(北京)行政冻结** = 终盘(`jingcai_sp.jc_*`,close-grade)。
2. Pinnacle **不冻**,继续吸 sharp 钱 + 阵容钱把价磨向有效,**直到开球**。
3. 单场最大的**计划内**信息事件 = **开球前 ~60–75 分钟官方首发** [microstructure §3]。
4. **深夜欧洲场** KO 在北京 03:00–05:00 → 首发在 **02:00–04:00 落地**,**全在竞彩 23:00 冻结之后** → 竞彩冻在「无阵容」的旧价上,Pinnacle 把阵容信息全价进收盘 → **缝最大**。
5. **下午亚洲场** KO 离冻结近、信息已定 → 缝最小。

**实证后盾(同行评议):** Kaunitz 2017 [A1] —— **开球前 1–5h 的盘 +9.9% vs 收盘 +3.5%**:edge 在临近收盘的几小时最肥,越近收盘越被磨平。竞彩冻结点离 Pinnacle 收盘越远(=深夜场),错过的「磨平」越多。

---

## 3. 测试设计

**数据输入(全部已在库):**
| 字段 | 来源 |
|---|---|
| 竞彩终盘 SP(`jc_home/draw/away`, market∈had/hhad) | `jingcai_sp` |
| 开球时间 `kickoff_utc` | `jingcai_sp` |
| Pinnacle 收盘线(去 vig 公允) | `odds_snapshots` / Odds API 历史收盘 |
| 已结算结果 | `settle_jingcai_sp` |

**派生:**
- `freeze_to_ko_hours = kickoff_utc − 当日竞彩冻结时刻(~15:00 UTC = 北京 23:00)`。
- `CLV_腿 = 竞彩SP / (1 / Pinnacle收盘去vig公允P) − 1`(复用 §3 / `clv_ledger` 口径,让球走 `implied_handicap_lines` 反推)。

**分桶 + 指标:**
- 按 `freeze_to_ko_hours` 分桶:`<2h / 2–5h / 5–10h / >10h`;并按北京开球时段交叉(亚洲下午 / 欧洲傍晚 / 深夜欧洲)。
- 每桶报:**CLV 中位**、**+EV 腿占比**、**甜区命中**、N。
- **只用受训欧洲联赛**;**不混 WC / 杯 / 北欧 / 亚盘日职**(锐利度 regime 不同,见 `handicap-reconstruction-calibration-tested` + `soft-water-leg-finding-measured`)。控制 favorite/dog、market(had vs hhad)。

**判定:**
- **H1 支持** ⟺ CLV 随桶单调改善 **且** 深夜欧洲桶显著优于亚洲下午桶(用 bootstrap 显著性,防小 N 假阳)。
- **H1 证伪** ⟺ 各桶持平。

---

## 4. 关键纪律(别误读结论)

- **结构 ≠ 绝对 +EV。** 即便 H1 成立,只说明缝**在哪最大**;缝最大的桶**仍可能整个埋在 −11% 抽水墙里**(见 `soft-water-leg-finding-measured`)。绝对「能不能投」仍是软水数据门(`parlay_soft_water_research` §4)。本卡只测**相对结构**。
- **前向数据门:** 价格侧(竞彩让球 SP)只能向前,历史拿不到(`parlay_soft_water_research` §5)。要受训联赛复赛(~8 月)+ 攒够已结算腿才能跑。
- **样本卫生:** 小 N 易假阳;bootstrap 显著性是硬门,不看点估计。

---

## 5. 何时跑 / 机器清单

**触发(已自动化,无需盯):** `clv_ledger` 选中计数器到阈值时,受训联赛腿自然攒够即跑(同 `parlay_soft_water_research` §7/§8)。

**机器(已就位):**
- ✅ `jingcai_sp`(`jc_*` 终盘 + `jc_open_*` 初盘 + `kickoff_utc`)+ 23:15 终盘 / 11:05 初盘 cron
- ✅ `odds_snapshots` 线史 + Odds API 历史收盘
- ✅ `clv_ledger` / §3 测量脚本 / `nutmeg-handicap-triples`
- ✅ `settle_jingcai_sp` 每日结算

**唯一缺口 = 受训联赛的前向已结算腿**(6 月全休,等秋天)。

**决策:** H1 支持 → 捕获/择时偏向深夜欧洲场,作为软水搜索的优先窗口;H1 证伪 → 冻结缺口均匀,砍掉时段角度,省力。

---

*相关:[[sharp_money_market_microstructure]](实证后盾 + 引文)、`docs/parlay_soft_water_research.md` §6 盘口路径/冻结缺口 · §8 秋天重启计划。*
