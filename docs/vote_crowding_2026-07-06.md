# 竞彩 散户拥挤曲线 — 探索 #3 的 measure-first 结果:数据在被每天丢掉

_2026-07-06 · 探索方向 #3 · 只读测量 · 工具 `nutmeg-vote-crowding` + 采集加固_

## 问题

第三条想测两件事:①**散户拥挤曲线** —— 随开赛临近,散户支持怎么移动(往热门堆=跟风,
还是后期逆向/分散)?②**lead-lag** —— 散户支持是**先于**还是**后于** Pinnacle 线动
(散户带信息,还是纯跟盘)?两者都需要**日内多次快照**。

## Measure-first 抓到的事:数据在被每天丢掉

先查 `jingcai_vote` 的日内快照密度,结果:**36 场,每场只有 1 个快照**(n=1 全场),
support 位移**无法测**。根因不是 cron 没跑,是**表结构在覆盖**:

```sql
UNIQUE(match_date, home_zh, away_zh, pool_code)
... ON CONFLICT(...) DO UPDATE SET h_support=excluded.h_support, ...
```

`jingcai_vote` 是 **upsert-latest**(每场一行,每次 re-capture 覆盖成最新)。这对
「服务当前支持」是对的,但它**静默丢弃了日内轨迹**。36 行 = 36 场,铁证。而这条轨迹
是**forward-only**(无回填):vote 端点只给当天、无历史,今天覆盖掉的读数**永远回不来**。
按 forward-only-build-now 原则,**每空一天 = 数据永久损失**,所以第三条的正确交付**不是**
在 N=0 上硬跑分析,而是**先把采集堵漏**。

## 修法:附加式快照表,不动现有服务视图

新增 `jingcai_vote_snapshots`(**append-only**),坐落在 upsert 的 `jingcai_vote` **旁边** ——
完全类比 `odds_snapshots` 保留 Pinnacle 线史、坐落在当前赔率旁边的做法:

- 每次 capture **追加**一行 `(match, captured_at, 支持三路, 计数, jc 赔率, 让球线)`;
  `UNIQUE(match, captured_at)` 让同秒重跑幂等、不同拉取累积。
- 写在采集的**同一事务**里,但用**独立的 try 守卫** —— 快照写失败**绝不回滚**当前视图
  upsert(继承「丢一次观测也不能挂采集」契约)。
- 无结算列:结果留在 `jingcai_vote`,分析时按 match key 联结。
- 采集函数加可注入的 `captured_at`(默认 now),便于测试/回填;cron 不传 → 用 now。

**非破坏性**:`CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE`,无数据变更。live vote
cron(`com.nutmeg.sporttery_vote`,每日 11:10/17:00/23:20)在改动上线后的**下一次运行
起自动累积**(CLI 每次跑是新进程,取已提交代码;无需重装 plist / 重启)。

## 工具 `nutmeg-vote-crowding`(已锁,随数据累积复读)

读 `jingcai_vote_snapshots`,报:
- **支持位移** = 逐腿 (max−min) support 均值 / 单场最大:人群到底动没动。
- **跟风指数** = 早期热门腿支持「涨向开赛」的场占比:>50% 跟风堆热门,<50% 后期逆向。

今天输出 = **0 场有 ≥2 快照**(表刚建,历史 36 行是覆盖后的单快照,进不了新表)。序列从
下次 cron 起长。合成数据单测覆盖了位移/跟风/逆向/空集,工具行为已锁死。

## 裁决 + 边界

1. **第三条的「发现」暂缓**(N=0 序列),但**造成暂缓的 forward-only 漏洞已堵** —— 这是
   本轮真正的价值:再不堵,拥挤曲线永远测不了。
2. **lead-lag(散户 vs Pinnacle 谁先动)进一步推迟**:需要 vote 序列 × `odds_snapshots`
   按时间戳联结,秋季序列攒厚(每场跨 ≥2 窗口)再设计+验证。今天不在 N=0 上臆造回归。
3. 与 S2(散户逆向)的关系:S2 看**终值** support 跟结果;拥挤曲线看 support 的**过程**。
   若「早期逆向盘、后期被散户跟风推贵」成立,则**早捕获的读数**比临场读数更接近 sharp ——
   这会给「何时下手」一个时间维度。纯探索,秋季进预注册才可能影响下注。
