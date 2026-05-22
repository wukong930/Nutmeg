# Nutmeg 文档包 v2

> 项目名：**Nutmeg**  
> 定位：长期可迭代的足球单场概率预测与组合分析平台  
> 核心目标：**让预测更准确，而不是让推荐更刺激。**

本文档包是 Nutmeg 的全新重构版设计文档，面向 Codex / 工程团队直接执行开发。它把前面讨论过的世界杯、五大联赛、未来赛事扩展、胜平负、让球、比分、冷门、二串一/三串一/四串一、复式串关、Dixon-Coles、系统记忆、错误学习、前端表达规范统一到一个可落地的工程方案中。

---

## 1. 文档目录

| 文件 | 用途 |
|---|---|
| `00_Nutmeg_README.md` | 文档索引、目标、关键原则 |
| `01_Nutmeg_PRD.md` | 产品需求文档：用户、功能、页面、验收 |
| `02_Nutmeg_System_Architecture.md` | 系统架构设计：服务、模块、数据流、部署 |
| `03_Nutmeg_Data_and_Competition_Onboarding.md` | 数据源、赛事扩展、联赛/杯赛接入流程 |
| `04_Nutmeg_Modeling_and_Accuracy_Loop.md` | 模型方案、Dixon-Coles、比分矩阵、系统记忆、越用越强闭环 |
| `05_Nutmeg_Markets_Handicap_Parlay_Rules.md` | 胜平负、竞彩让球、亚洲盘、比分、串关、复式、规则引擎 |
| `06_Nutmeg_Database_and_API_Spec.md` | 数据库 schema、API 合约、任务表、事件表 |
| `07_Nutmeg_Frontend_Design_Spec.md` | 前端信息架构、组件规范、页面设计、概率表达规范 |
| `Nutmeg_Frontend_Design_Spec.md` | 前端 v2.1 详细设计规范：Quant Sports Lab 视觉方向、FE-01 至 FE-08 实施里程碑、MVP 前端验收清单 |
| `08_Nutmeg_Execution_Plan_for_Codex.md` | 项目执行计划、里程碑、Codex 任务拆分、验收清单 |
| `09_Nutmeg_Ops_Compliance_and_Governance.md` | 运维、监控、模型治理、合规边界、安全策略 |
| `10_Nutmeg_Glossary_and_References.md` | 术语表、参考资料、规则来源、研究资料 |
| `11_Nutmeg_V3_1_Recommendation_Upgrade.md` | V3.1 推荐核心升级：最佳答案引擎、预算优化、动态推荐生命周期 |

---

## 2. Nutmeg 的核心判断

Nutmeg 不应该是一个“猜比分机器人”，也不应该是一个“自动下注机器人”。它应该是一个：

```text
赛前概率预测引擎
+ 比分分布模型
+ 玩法规则解析器
+ 冷门风险识别器
+ 串关组合优化器
+ 模型学习闭环
+ 可解释前端工作台
```

最终能力不是输出一句“主胜”，而是输出一张完整概率地图：

```text
主胜 / 平 / 客胜概率
中国竞彩让球胜平负概率
亚洲让球全赢/半赢/走水/半输/全输概率
比分 Top N 与竞彩比分选项概率
大小球、双方进球、热门脆弱度
冷门类型与方向
二串一、三串一、四串一、复式串关组合质量
模型与市场差异
历史回测和校准表现
```

---

## 3. 最高优先级原则

### 3.1 底层统一：所有玩法来自比分概率矩阵

不能让不同模型分别预测胜平负、让球、比分，否则会出现互相矛盾的结论。Nutmeg 的底层必须先生成：

```text
score_probability_grid[home_goals][away_goals]
```

然后从矩阵派生全部玩法。

### 3.2 准确性优先：不以“命中率宣传”为目标

预测准确性的核心指标是：

```text
Log Loss
Brier Score
Calibration Error
Closing Odds Comparison
Score Distribution Quality
Handicap Settlement Calibration
Upset Precision@K
Parlay Portfolio Performance
```

单场“猜中/猜错”只能作为辅助指标。

### 3.3 系统要有记忆，但不能盲目自我更新

Nutmeg 必须记录每次预测时的完整上下文：

```text
当时模型版本
当时特征版本
当时赔率快照
当时伤停/阵容信息
当时预测概率
最终赛果
错误类型
回测指标
```

但模型不能每错一场就立刻乱改。正确方式是：

```text
赛后记录 → 错误归因 → 周期性训练 → Walk-forward 回测 → 校准 → 模型晋级/回滚
```

### 3.4 LLM 只做辅助，不直接给概率

LLM 可以做：

```text
新闻/发布会/伤停文本抽取
德比、轮换、战意、压力等语义特征提取
错误分析摘要
前端解释文本生成
用户问答
```

LLM 不应该直接做：

```text
给出主胜/平/客胜概率
直接预测比分
直接决定串关推荐
```

### 3.5 串关是组合优化，不是简单拼单

二串一、三串一、四串一、复式串关必须计算：

```text
注数
总金额
组合命中概率
组合赔率/理论返还
期望值 EV
ROI
风险等级
相关性惩罚
规则合法性
边际收益
```

系统要判断“是否值得多选”，而不是一律多选或一律单选。

---

## 4. MVP 范围

### 4.1 首发赛事

第一阶段建议：

```text
英超 Premier League
西甲 La Liga
德甲 Bundesliga
意甲 Serie A
法甲 Ligue 1
世界杯 / 欧洲杯等国家队赛事先以 Beta 接入
```

但架构必须支持未来新增：

```text
荷甲
葡超
英冠
日职 J1 / J2
韩职 K League
欧冠
欧罗巴杯
欧协联
欧洲杯
亚洲杯
美洲杯
国内杯赛
```

### 4.2 首发玩法

```text
1X2 胜平负
中国竞彩让球胜平负
亚洲让球主盘口
比分 Top 5
竞彩比分选项聚合
热门脆弱度
冷门提示
二串一 / 三串一 / 四串一
复式串关展开与评估
```

### 4.3 暂不做

```text
自动下注
代客投注
保证收益表达
滚球实时下注建议
未成年人导向内容
高频交易/套利机器人
```

---

## 5. 推荐仓库结构

```text
nutmeg/
  apps/
    web/                       # Next.js 前端
    api/                       # FastAPI 后端
  packages/
    shared/                    # TypeScript shared types
  services/
    ingestion/                 # 数据接入
    features/                  # 特征工程
    modeling/                  # 模型训练与预测
    market_resolver/           # 玩法概率解析
    parlay_optimizer/          # 串关组合优化
    accuracy_loop/             # 赛后评估与学习闭环
    llm_context/               # LLM 文本抽取与解释
  db/
    migrations/
    seeds/
  jobs/
    daily_ingestion.py
    pre_match_predictions.py
    post_match_evaluation.py
    weekly_training.py
  docs/
  tests/
    unit/
    integration/
    regression/
  docker-compose.yml
  README.md
```

---

## 6. Codex 执行总提示

交给 Codex 时，可以使用如下总提示：

```text
你正在实现 Nutmeg，一个足球比赛概率预测平台。请严格按照 docs/ 目录下的 Markdown 文档开发。核心原则：所有玩法概率必须从 score_probability_grid 派生；预测必须保存快照；串关必须通过规则引擎和组合展开计算；不要实现自动下注；模型必须有版本、回测、校准、晋级/回滚机制。优先完成 MVP：数据模型、模拟 provider、Poisson/Dixon-Coles baseline、market resolver、parlay optimizer、API、Next.js 前端页面和测试。
```

---

## 7. 版本说明

| 版本 | 说明 |
|---|---|
| v1 | 初步架构、PRD、技术文档、执行文档、前端规范 |
| v2 | 全面重构，加入赛事扩展、复式串关、系统记忆、Dixon-Coles v1.5、Accuracy Learning Loop、模型治理、合规运维 |
