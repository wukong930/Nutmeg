# δ 联赛范围闸 —— 实施方案(2026-08-14 起草,**当日回滚待重做**)

**状态** 🟡 方案已定、发现已完成、**代码已回滚**。等别名批次验收后重做。
**授权** owner 口令「做1」+ 设计选择「**方案 A**」(2026-08-14)
**延后原因** owner 口令「B」—— 见 §6

---

## §0 一句话

`market_handicap.py:262` 的注释从一开始就写着「范围:football-data 覆盖的欧洲联赛;
日职/杯赛/北欧/韩职 **0 覆盖**」,但 `grep -n league` 在该文件与
`onex_calibration.py` **零命中** ⇒ **警告写在注释里,闸没写在代码里**。
本方案就是把那句注释变成可执行的闸。

---

## §1 为什么做(不是新提案,是**预定动作**)

锚迁移桥接检验(`docs/autumn_anchor_migration_prereg_v1.0_2026-08-13.md` §2)
判定落在**第三种结果「① 不过」**:Pinnacle 与 Betfair 两锚在让胜腿系统性不同
(+0.4070pp,t=17.0;−2 线达 ±0.010 界的 **178%**)。

§2.4 的预定动作逐字是:

> **① 不过(两锚系统性不同)** → ⛔ **不换,且现行 δ 值的适用性存疑**。
> 此时正确动作是**收紧**:覆盖外一律不施加点估 δ。

配套的事实(2026-08-13 审计):当日可投注人口里只有 **102/2,352 = 4.3%** 的腿
落在覆盖内,而**过闸的 8 条腿 0/8 在覆盖内** ——
全系统最大的单常数杠杆,正被全额施加在一个它从未被测量过的人口上。

---

## §2 ⭐ 白名单 = 这 10 个(**跑尺子自己的加载器取的,不是猜的**)

```python
_DELTA_CALIBRATED_LEAGUES = frozenset({
    "EPL", "ITA_SERIE_A", "ESP_LA_LIGA", "FRA_LIGUE_1", "GER_BUNDESLIGA",
    "ENG_CHAMPIONSHIP", "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
    "FRA_LIGUE_2", "GER_2_BUNDESLIGA",
})
```

取法(可复现):

```python
import importlib.util, collections, sys; sys.path.insert(0,'apps/api/src')
spec = importlib.util.spec_from_file_location("hdh","scripts/handicap_delta_homogeneity.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
fd, pool = M.load_football_data()
sample, diag = M.build_sample("data/v4_jingcai_history.db", fd, pool)
collections.Counter(s["league"] for s in sample)
```

实测分布(6,095 场合格样本):

| 联赛 | 场次 | 占比 |
|---|---:|---:|
| 英超 EPL | 1171 | 19.2% |
| 意甲 ITA_SERIE_A | 1041 | 17.1% |
| 西甲 ESP_LA_LIGA | 1009 | 16.6% |
| 法甲 FRA_LIGUE_1 | 646 | 10.6% |
| 德甲 GER_BUNDESLIGA | 602 | 9.9% |
| 英冠 ENG_CHAMPIONSHIP | 523 | 8.6% |
| 荷甲 NED_EREDIVISIE | 412 | 6.8% |
| 葡超 PRT_PRIMEIRA_LIGA | 378 | 6.2% |
| 法乙 FRA_LIGUE_2 | 284 | 4.7% |
| 德乙 GER_2_BUNDESLIGA | **29** | 0.5% |

### 两条必须记住的更正

1. 🚨 **不是 9 个。** 我(以及记忆文件)一直写「9 个欧洲联赛」——**错的**,是 10 个。
2. 🚨 **文件数 ≠ 联赛数。** football-data 有 **13** 个文件带 Pinnacle 收盘
   (25,941 行),但 **B1/N1/SP2 三个从未 join 上竞彩让球** ⇒ 校准人口只有 10 个联赛。

### ⚠️ 德乙只有 29 场,为什么还进白名单

δ 是**池化**估计(同源性检验 z=1.40,拒绝不了同源)⇒ 白名单 = δ 的实测人口,
**不另发明「每联赛最小样本量」** —— 那是事后加判据。
若日后要加逐联赛门槛,须单独预注册。

---

## §3 设计:方案 A(owner 选定)

`league=None`(调用方没传)⇒ **按未校准处理**(不施加点估 δ)。

- **方向**:保守 —— 判闸更严、注更少。不确定时该走的方向。
- **代价**:哪个调用点漏传,δ 就**静默关掉**。
- **对策**:三态计数器,让「静默」变可观测:

```python
_SCOPE_STATS = {
    "applied": 0,            # 覆盖内,点估已施加
    "suppressed_league": 0,  # 联赛在覆盖外 ⇒ 不施加(预期形态)
    "suppressed_none": 0,    # 没传 league ⇒ 不施加(**可能是漏传,要查**)
}
```

`suppressed_none` 不为 0 就是有调用点漏传。⛔ 别把这个计数删成 no-op ——
它是方案 A 唯一的可观测性。

### 两个函数各改什么

**`implied_handicap_lines(..., c1=True, league=None)`**
`_c1 = bool(c1) and _delta_in_scope(league)`,后面三个分支用 `_c1`。
⚠️ `c1=False`(eval/measurement)**完全不受影响** —— 尺子不该被闸改口径。

**`c1_leg_lower_bounds(line, ..., league=None)`**
覆盖外 + `line != 0` ⇒ 用 `_UNCAL_SE` 地板(与 +2/±3 未校准线同一处理)。
理由:既然没施加点估 δ,就不能用「在测过的联赛上 δ 有多准」的那批 SE ——
那等于把**别人的精度**借给一个未知偏差。

---

## §4 调用点全图(**比开工时估的大**)

### 判闸路径(`c1=True`,必须传 league)

| # | file:line | 函数 | league 从哪来 |
|---|---|---|---|
| ① | `api/routes.py:863` | `_market_reverse_handicap_probs(row, line)` | `row.get("league")` |
| ② | `api/routes.py:2064` | `_model_board_handicap_lines(f, ...)` | `getattr(f,"league",None)` |
| ③ | `api/routes.py:2487` | `_market_handicap_lines(fair, r)` | `r["league"]` ✅ 已存在 |
| ④ | `api/routes.py:2821` | `recommend_market_handicap(req)` | `req.league` ✅ schema 已有 |
| ⑤ | `api/routes.py:2840` | 同上的 `c1_leg_lower_bounds(...)` | `req.league` |
| ⑥ | `cli/delta_calibration.py:142` | **每日漂移监控** | `r["league"]`(SELECT * from jingcai_sp) |

🚨 **⑥ 最容易漏**:它用 `c1=True` 但它是**监控 δ 的东西**。不传 league ⇒
监控静默失去监控对象。

### 🚨 还有一层我第一版漏了(靠断言挡住的)

`_hc_line_prob(line, ph, pd_, pa, bounds_fn)`(`routes.py:2457`)
**内部调 `bounds_fn(...)`** ⇒ 它的签名也得接 `league` 并透传。
①②③ 都经过它。

### 不受影响(`c1=False`,尺子/eval —— ⛔ 别动)

`scripts/handicap_delta_homogeneity.py:168` · `cli/ev_ranking.py`(注释明写走 raw)
· `cli/clv_ledger.py:97` · `cli/jingcai_staleness.py:136`
· `observation/handicap_triples.py:126`(默认 c1=False)

---

## §5 测试

### 既有 4 条会红,**要按新语义重写**(不是删)

```
test_c1_handicap.py::test_lower_bounds_are_not_a_distribution
test_handicap_delta2.py::test_minus2_shift_direction_and_sum
test_handicap_delta2.py::test_minus2_bounds_use_per_leg_se
test_handicap_delta2.py::test_uncalibrated_band_is_wider_than_calibrated
```

它们钉的是「δ 施加了」,新语义是「**在覆盖内**施加、**覆盖外**不施加」
⇒ 每条加 `league="EPL"`,并**各配一条覆盖外的对照**。

### 空包弹(至少 3 发,先跑不变异的基线)

1. 白名单清空 ⇒ 覆盖内的断言必须红
2. `_delta_in_scope` 恒返回 True ⇒ 覆盖外的断言必须红
3. `_SCOPE_STATS` 改成 no-op ⇒ 可观测性断言必须红

⚠️ 插入变异要注意:dict/frozenset 字面量**后写覆盖先写**,变异必须插在
**定义之后**才生效。08-13 踩过一次:变异被合法条目静默擦掉,空包弹显示绿,
我差点报「护栏没漏」。**空包弹本身也要验证它真的装填了。**

---

## §6 为什么 08-14 当天回滚

**不是技术风险,是可归因性。**

当天已上线别名批次(92→130 条,写入侧收口),而今晚正是英冠/西乙首批 closing
落盘 —— 别名那批**一次真实验证都还没经过**(`verify_after_0814.py` 当天报的是
**UNMEASURABLE**,不是 PASS)。

同一天动两处核心路径(写入侧 + 判闸侧),盘面一旦异常,两者纠缠在一起分不开。
而**本闸没有截止日**:它不需要任何新数据,明天做代价为零。

### 回滚时的实际状态(供重做时对照)

- `market_handicap.py` 引擎侧**已改完并验证可用**
  (`_delta_in_scope` 对 `EPL`/`英超` 都返回 True、对 `JPN_J1`/`日职`/`WC`/`None` 返回 False)
- `routes.py` **一个字没动** —— 批量替换在第一处断言失败,脚本先断言后写 ⇒ 原子性保住
- ⚠️ 那个半成品状态的后果值得记:**引擎加闸 + 无人传 league = δ 在所有联赛
  (含那 10 个)上全被抑制**,4 条既有测试当场红。
  ⇒ **这个改动不存在「改一半也能上线」的中间态**,必须一次做完。

---

## §7 重做时的顺序

1. 先跑 `scripts/verify_after_0814.py`,确认别名批次 **PASS**(不是 UNMEASURABLE)
2. 引擎:白名单 + `_delta_in_scope` + `_SCOPE_STATS` + 两个函数(§3)
3. `_hc_line_prob` 签名(§4 那一层)
4. 六个调用点(§4 表)
5. 重写 4 条测试 + 加覆盖外对照(§5)
6. 空包弹 3 发,**先跑基线**
7. 全套 + lint + `/health`
8. ⚠️ **重启服务需要单独口令**;重启后查 `_SCOPE_STATS`,
   `suppressed_none` 应为 **0**(不为 0 = 有调用点漏传)

---

## §8 2026-08-15 第二次尝试 —— 又回滚,但**捞到一个会静默生效的 bug**

### 🚨 最值钱的发现:白名单用英文键,而 `canonical_league` 归一到**中文**

```python
canonical_league("EPL")  # → '英超'   ← 不是 'EPL'
```

⇒ `_DELTA_CALIBRATED_LEAGUES`(英文键)拿去和它比,**永远不匹配**
⇒ 闸会把 **所有** 联赛判成覆盖外,δ 被**全局静默关掉** —— 包括那 10 个校准过的。

**这个 bug 不会报错、不会红任何测试、面板照常出数**,只是每一条让球腿都少了 δ。
⭐ 它唯一被抓住的原因是我把 `_delta_in_scope` 的返回值**打出来看了一眼**:

```
'EPL'  → False      ← 一眼就不对
```

⇒ **修法**:`_canon()` 两侧都过归一,白名单缓存成正典形。
   ⛔ 别改成「白名单直接写中文」—— 英文键是尺子加载器的输出形态,
      写中文会让「白名单从哪来」这条线索断掉。

### 本次做完了什么(全部已回滚,但值得照抄)

· 引擎:`_DELTA_CALIBRATED_LEAGUES` / `_canon` / `_canonical_scope` /
  `_delta_in_scope` / `_SCOPE_STATS` 三态计数器
· `implied_handicap_lines(..., league=None)` + `_c1 = bool(c1) and _delta_in_scope(league)`
· `c1_leg_lower_bounds(..., league=None)`:覆盖外 + `line != 0` ⇒ 吃 `_UNCAL_SE` 地板
· `_hc_line_prob(..., *, league=None)` 透传给 `bounds_fn`
· 6 个调用点(routes.py ×5 + delta_calibration.py ×1)全部接上
· **行为自检通过**:
    EPL 让胜 0.2700 · 日职/None/c1=False 三者同为 0.3163
    ⇒ δ 只在覆盖内施加,且尺子(c1=False)不受影响

### ⛔ 为什么还是回滚:**12 条测试红**

按旧语义写的断言(「δ 施加了」)在新语义下必然红:
`test_c1_handicap` 5 · `test_handicap_delta2` 3 · `test_market_handicap_tracking` 4。

前 8 条只需逐个补 `league="EPL"` 并**各配一条覆盖外对照**;
🚨 后 4 条要单独想:它们的夹具用 `league="JPN_J1"` —— 覆盖外,
   所以 δ 被抑制、EV 变了、「恰好一条正 EV 腿」这类断言不再成立。
   **那是新语义下的正确行为**,断言要重写而不是把夹具改成 EPL
   (改夹具 = 把「日职不该吃 δ」这个新事实从测试里抹掉)。

⚠️ 我这次用**正则**批量改测试文件,改坏了(`NameError`),已 `git checkout` 回滚。
   ⇒ 下次:测试改判据用**逐条 Edit**,别在源码上跑正则。

### §9 下次重做的顺序(在 §7 基础上更新)

1. 引擎侧照抄 §8(含 `_canon` 双侧归一 —— **这是新增的必要步骤**)
2. **先改测试再接调用点**:把 8 条补 `league` + 4 条重写判据,
   跑一遍确认「只有范围闸相关的红」
3. 再接 6 个调用点 + `_hc_line_prob`
4. 空包弹 3 发(白名单清空 / `_delta_in_scope` 恒 True / `_SCOPE_STATS` no-op)
5. 全套 + lint + `/health`;重启后查 `_SCOPE_STATS["suppressed_none"]` 应为 **0**
