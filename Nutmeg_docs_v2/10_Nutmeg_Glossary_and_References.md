# Nutmeg 术语表与参考资料 v2

## 1. 核心术语

### Nutmeg

项目名。足球术语中表示“穿裆过人”。本项目中表示一个清晰、有趣、专业的足球预测系统。

### Score Probability Grid

比分概率矩阵。

```text
P[home_goals][away_goals]
```

Nutmeg 的所有玩法概率都从这个矩阵派生。

### 1X2

胜平负：

```text
1 = 主胜
X = 平局
2 = 客胜
```

### CN Handicap 1X2

中国竞彩让球胜平负。三结果玩法：

```text
让球胜
让球平
让球负
```

### Asian Handicap

亚洲让球。常见结果：

```text
全赢
半赢
走水
半输
全输
```

### Correct Score

精确比分玩法。

### Parlay / Accumulator / 串关

多个单场选项组合。任一 atomic bet 中所有腿都命中才返还。

### Multiple / 复式

同一场选择多个结果，自动展开为多注 atomic bets。

### Atomic Bet

复式串关展开后的单个具体组合。

### EV

Expected Value，期望值。

```text
EV = Expected Payout - Stake
```

### ROI

Return on Investment。

```text
ROI = EV / Stake
```

### Log Loss

概率预测评估指标。对过度自信的错误惩罚很重。

### Brier Score

概率预测评估指标，用于衡量概率分布与实际结果的平方误差。

### Calibration

概率校准。若模型说某类事件概率 60%，长期实际发生率应接近 60%。

### Dixon-Coles Model

足球比分建模经典方法，在 Poisson 框架上加入时间衰减和低比分相关性修正。

### Accuracy Learning Loop

Nutmeg 的学习闭环：

```text
预测 → 记录 → 赛后评估 → 错误归因 → 再训练 → 回测 → 校准 → 晋级/回滚
```

---

## 2. 玩法术语

### 让球胜平负示例

主队 -1：

```text
2-0 → 让胜
1-0 → 让平
2-1 → 让平
0-0 → 让负
```

### 亚洲让球 -0.75 示例

```text
赢 2 球或以上 → 全赢
赢 1 球 → 半赢
平或输 → 全输
```

### 四串一复式示例

```text
A: 负/平
B: 负
C: 平/负
D: 胜
```

注数：

```text
2 × 1 × 2 × 1 = 4 注
```

---

## 3. 参考资料

> 这些资料用于产品和技术设计参考。开发前必须重新核对授权、调用限制、商业使用限制和最新文档。

### 3.1 数据源与 Provider

1. football-data.org Coverage  
   https://www.football-data.org/coverage

2. football-data.org API Reference  
   https://www.football-data.org/documentation/api

3. API-Football Coverage  
   https://www.api-football.com/coverage

4. SportMonks Football API Coverage  
   https://www.sportmonks.com/football-api/coverage/

5. SportMonks Football API  
   https://www.sportmonks.com/football-api/

6. SportMonks Expected Lineups  
   https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/premium-expected-lineups

7. SportMonks Injuries and Suspensions  
   https://www.sportmonks.com/glossary/injuries-and-suspensions/

8. The Odds API Documentation v4  
   https://the-odds-api.com/liveapi/guides/v4/

9. Betfair Historical Data Services API  
   https://developer.betfair.com/historical-data-services-api/

10. Betfair Exchange API  
    https://developer.betfair.com/exchange-api/

11. Polymarket API Reference  
    https://docs.polymarket.com/api-reference/introduction

12. Polymarket Market Data: Fetching Markets  
    https://docs.polymarket.com/market-data/fetching-markets

13. StatsBomb Open Data  
    https://github.com/statsbomb/open-data

14. OpenFootball / football.json  
    https://github.com/openfootball/football.json

### 3.2 竞彩与过关规则

1. 中国竞彩网：自由过关详解  
   https://www.sporttery.cn/help/249715.html?gid=2

2. 中国体彩网/彩票.gov：混合过关详解  
   https://www.lottery.gov.cn/bzzx/yxgz/20191119/1040217.html

3. 湖南红网：混合过关及自由过关详解  
   https://sports.rednet.cn/c/2018/07/06/4672898.htm

> 注意：具体玩法、关数、规则可能随地区和时间变化。系统应做规则配置化，并在上线前以官方最新规则为准。

### 3.3 足球建模与评估

1. Dixon, M. J. and Coles, S. G. (1997). Modelling Association Football Scores and Inefficiencies in the Football Betting Market.  
   https://academic.oup.com/jrsssc/article/46/2/265/6990546

2. Dixon-Coles paper alternative PDF mirror  
   https://www.ajbuckeconbikesail.net/wkpapers/Airports/MVPoisson/soccer_betting.pdf

3. Dixon-Coles and Time Weighting tutorial  
   https://dashee87.github.io/football/python/predicting-football-results-with-statistical-modelling-dixon-coles-and-time-weighting/

4. scikit-learn  
   https://scikit-learn.org/

5. MLflow  
   https://mlflow.org/

6. Databricks MLflow documentation  
   https://docs.databricks.com/aws/en/mlflow/

---

## 4. 关键设计备忘

### 4.1 不要混淆概率和建议

```text
概率 = 模型估计
建议 = 产品表达
下注 = 不属于 Nutmeg MVP 范围
```

### 4.2 不要混淆赔率高和价值高

赔率高不代表有价值。价值取决于：

```text
model_probability > market_implied_probability
```

### 4.3 不要混淆命中率和准确性

准确性要看：

```text
Log Loss
Brier Score
Calibration
```

### 4.4 不要声称能稳定预测极端比分

7:1 这类比分赛前通常是低概率长尾事件。系统应识别长尾风险，而不是声称能稳定预测精确极端比分。

### 4.5 不要让 LLM 直接做概率预测

LLM 可以解释、抽取、总结，但最终概率必须来自可回测、可校准的模型。

