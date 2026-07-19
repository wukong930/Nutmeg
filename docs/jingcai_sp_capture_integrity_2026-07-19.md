# 竞彩 SP 捕获完整性 RCA + 横扫 — 2026-07-19

**病例**:周六212 塞伊奈约基(SJK) vs 库奥皮奥(KuPS),`jingcai_sp` hhad 行存
1.40/4.45/**7.25**(+1),官方走势档案(matchId 2040557,9 次变盘)终盘为
1.40/4.45/**5.25**,7.25 从未在该场任何池出现。面板让球块因此显示让负 EV
**假 +71%**(真 +24%)。

## TL;DR

- **根因 = (c) 写库路径的旁门:市场模式面板的「静默捕获」端点**
  (`POST /v4/observation/jingcai-sp`,source=`market_mode`)把用户 SP 输入框的
  任意值当「终盘」upsert,零校验;`protect_manual=True` 又让 market_mode 行免疫
  后续 cron 覆盖,配合 upsert-latest = **一次手滑,永久定格**。
  (a) 解析串值、(b) 上游脏值均被排除:同一秒(13:08:52Z,🎯 手动刷新)的官方
  采集把 had 行写得逐腿全对;横扫中官方 sporttery 通道 **0 损坏**。
- **横扫**(match_date ≥ 2026-07-01 已结算 219 行 vs getFixedBonusV1 官方终盘):
  可比 164 行,损坏 5 行(3.0%),**全部 source=market_mode、全部 hhad**;
  sporttery 源 131 行全部干净。
- **修复 = 捕获端两道 sanity 闸**(server + 前端),已实现+测试;
  6 行损坏数据(横扫 5 + 闸门在 6 月数据上追加标记 1)的修复 SQL 见下,**未执行**。

## 病例根因链(全部时间 UTC;北京 = +8h)

| 时刻 | 事件 |
|---|---|
| 07-18 01:33 | 官方开盘 1.50/4.10/4.60(+1);03:05 我们 open cron 记初盘 ✓ |
| 09:33→13:07 | 官方全天 9 次变盘,a 腿 4.60→5.25 |
| 13:08:52 | 手动触发的官方采集(21:08 北京无任何 cron → 🎯 刷新竞彩或手跑 CLI):had 行 2.32/3.35/2.50 逐腿=官方终盘 ✓,hhad 行同批被正确写入(h/d 与官终一致可证) |
| **15:02:15** | **开球(14:00)62 分钟后**,前端静默捕获把 hhad 框值 1.40/4.45/**7.25** POST 成「终盘」(source=market_mode)。h/d=官终不变 ⇒ 只有 a 框被人为改动过;7.25 与官方任何变盘、任何池都对不上 = 人为输入(手滑/what-if) |
| 之后 | 比赛已从 calculator 下架 + `protect_manual` 保护 market_mode 行 ⇒ 无任何机制能再覆盖,7.25 定格为「终盘」 |

前端机制放大器:市场模式卡的「会话恢复」会在每次 60s 轮询重渲后把≠预填的框值
复原并**重新触发捕获**(`_cupHcLine → _cupHcRecalc → _jcStaleCaptureHc`),
所以一次输入会被反复重写直至关页 —— 15:02:15 只是最后一次。

## 横扫结果(2026-07-01..18 已结算 219 行,官方枚举 122 场)

| 分类 | sporttery | market_mode | 说明 |
|---|---|---|---|
| OK_FINAL(=官方终盘) | 104 | 27 | |
| OK_AT_CAPTURE | 27 | 1 | = captured_at 时刻官方在售值,之后官方又变盘 → **采集时点缺口,非损坏**(23:15 终盘 cron 之后、次日晨开球前的变盘;09:50 补捕窗已在收) |
| **FABRICATED**(某腿值从未在官方走势出现) | **0** | **4** | 真损坏 |
| **MIXED_PHASE**(各腿都出现过但拼不成官方任何一行) | **0** | **1** | 跨变盘手抄 |
| NO_OFFICIAL(官方侧队名未映射/枚举缺口,无法比对) | 46 | 9 | 官方档案用缩写中文名,29 场映射不出 EN(巴甲/美职联等,与生产采集无关) |

**损坏率:官方通道 0/131;手填通道 5/33(15%)。** 损坏全是 hhad(让球框
=手动输入最重的路径:线下拉 + 3 框全手填)。

## 损坏清单 + 修复 SQL(待 owner 口令执行;官方终盘来源 getFixedBonusV1)

| id | 场次 | market | 我们存的 | 官方终盘 | 备注 |
|---|---|---|---|---|---|
| 7767 | 07-18 SJK vs KuPS | hhad +1 | 1.40/4.45/**7.25** | 1.40/4.45/**5.25** | 病例;EV 假 +71% |
| 4908 | 07-04 大田 vs 富川 | hhad −1 | **3.50**/2.82/**2.19** | 3.35/2.88/2.07 | booksum 1.097 |
| 4969 | 07-04 VPS vs 玛丽港 | hhad −1 | **1.60**/3.85/3.80 | 1.65/3.85/3.80 | 小滑笔 |
| 5053 | 07-05 哥德堡 vs AIK | hhad −1 | **3.96**/3.85/**1.60** | 3.80/3.85/1.65 | 小滑笔 |
| 6896 | 07-15 英格兰 vs 阿根廷 | hhad −1 | **5.65**/3.75/1.45 | 5.76/3.75/1.45 | h=更早变盘值(跨盘手抄) |
| 260 | 06-14 澳大利亚 vs 土耳其 | had | 5.25/3.73/**1.40** | 5.55/3.78/1.46 | 闸门在 6 月数据上追加标记(横扫范围外);h/d=初盘值,a 从未存在 |

```sql
-- 全行统一重写为官方终盘,source 标 'fixedbonus_repair'(自证来源;非 market_mode
-- ⇒ 不再吃 protect_manual 保护,均已结算无实际影响)。jc_open_*/结算列不动。
UPDATE jingcai_sp SET jc_home=5.55, jc_draw=3.78, jc_away=1.46, source='fixedbonus_repair' WHERE id=260;
UPDATE jingcai_sp SET jc_home=3.35, jc_draw=2.88, jc_away=2.07, source='fixedbonus_repair' WHERE id=4908;
UPDATE jingcai_sp SET jc_home=1.65, jc_draw=3.85, jc_away=3.80, source='fixedbonus_repair' WHERE id=4969;
UPDATE jingcai_sp SET jc_home=3.80, jc_draw=3.85, jc_away=1.65, source='fixedbonus_repair' WHERE id=5053;
UPDATE jingcai_sp SET jc_home=5.76, jc_draw=3.75, jc_away=1.45, source='fixedbonus_repair' WHERE id=6896;
UPDATE jingcai_sp SET jc_home=1.40, jc_draw=4.45, jc_away=5.25, source='fixedbonus_repair' WHERE id=7767;
```

执行后建议:凡引用 6-7 月 jingcai_sp hhad 的统计(让球深尾/软水、freeze-gap 相关
口径)重跑一遍 —— 5/6 行是 hhad,且两行(SJK/大田)的腿值偏差足以翻转 EV 分级。

## 修复:捕获端两道 sanity 闸(`record_jingcai_sp`,全调用方生效)

**闸 1 · booksum(Σ1/odds)带 [1.10, 1.15],所有源。**
测量依据:竞彩管理员 vig 是铁桶 —— 2024-25 官方档案 15,959 场终盘 booksum ∈
[1.125, 1.140],2026-07 现值 373 行 ∈ [1.127, 1.130],初盘 317 行同带。官方变盘
前后 booksum 恒定,而单腿脏值/跨盘混拼必然把它拉出去。该带对全部官方数据
**零误报**,并抓住 6 行损坏中的 3 行(SJK 1.077、大田 1.097、澳土 1.173)——
恰好是 EV 扭曲最大的三行。若竞彩未来真把 vig 挪出带,捕获集体拒写 →
jingcai_sp 停更 → data_freshness 哨兵响 = 响亮失败而非静默污染。

**为什么不是「与前值突变」闸**(任务原提议):实测否决 —— 合法 open→终盘单腿
漂移最大 **2.04×**(>40% 的有 41/16k 场),幅度上与手滑不可分;booksum 才是
判别不变量。已在代码注释中钉死,防止将来被「优化」回突变闸。

**闸 2 · 开球 15 分钟后 market_mode 拒写。**
冻结 SP 开球后不可能再变;开球后的手填只会是 what-if/误触(SJK 案 +62 min)。
kickoff 取请求值,缺省回读行内已存值;两处皆无 → fail-open(手填新场仍可行)。
官方 sporttery 源不受此闸(calculator 本就只列在售场次)。

**前端**:`_jcStaleCapture` / `_jcStaleCaptureHc` 开球 15 min 后直接不再发捕获
POST(也切断 60s 轮询的重写循环);服务端同闸兜底(手机等其他客户端)。

**残余风险(诚实边界)**:开球前、band 内的单腿小滑笔(±0.05~0.11,如 VPS
1.60↔1.65)服务端无从判别 —— 它们本身就是合法赔率空间的点。量级上界 ≈ 单腿
±6% ⇒ EV 偏差 ±几 pp,不会再出现 +47pp 级假信号。彻底消除需捕获时对照官方
在售值,但那会反转「手填=用户比缓存新」的信任方向,不做。

## 验证

- 全套 pytest 通过;新增 5 个闸门测试(SJK 真值三元组直接做 fixture);既有
  测试中越带的合成三元组已改为带内真形状(测试意图不变)。
- ruff(E,F,I,B,UP,SIM,line-length 100)对 HEAD 零新增。
- 横扫工具收编为 `scripts/audit_jingcai_sp_vs_fixedbonus.py`(逐场 1s 限速 +
  本地缓存,可随时重跑);本次结果 JSON 在会话 scratchpad。

## 上线备忘(提交推送≠上线)

改动在 worktree;合入主树后需 `launchctl kickstart -k` 重启 API 服务
(`jingcai_sp.py` 是 server 端模块,daemon 不热载;dashboard.html 刷新页面即新)。
