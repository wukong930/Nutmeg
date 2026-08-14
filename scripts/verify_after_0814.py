#!/usr/bin/env python
"""08-14 之后的验收断言(只读)。三态输出,**分母守卫是核心**。

为什么需要分母守卫:这 8 个联赛今天 closing=0 行 ⇒ 「劈开键 = 0」在今天
是**真空真**(vacuously true)。不带分母的断言今天就绿,明天照样绿,
分不出「修好了」和「还没数据」—— 正是记忆里「零新增 ≠ 扫完了」那一族。

⚠️ 不要用 kickoff_utc 做 join 键:closing 写 '...Z',gather 写 '...+00:00',
   字符串相等永远 0%(实测全库 521 个 closing 键 0 命中)。真索引是 match_date。

## 🚨 2026-08-15 修:分母守卫**只守了联赛级,没守比赛日级**

首批真实 closing 落盘当天,本脚本报 `FAIL=2`(英冠 7 键 / 西乙 2 键)。
逐条查下来:

  · 西乙 2 键**全在 2026-08-17**,而那天 **gather = 0 行** ⇒ 是「gather 还没跑到」
  · 英冠 7 键里只有 **2 条**是真缺别名,其余同样是 08-17 的 gather 滞后

⇒ 联赛整体有 gather 行 **不等于** 每个比赛日都有。closing(Odds API)对未来场次
**先落**,gather(API-Football)按自己的节奏跟 —— 中间那段窗口里,
「劈开键」和「还没采到」**长得一模一样**。

⭐ 这正是本仓 [[unmapped-banner-silences-not-fixes]] 那一族的又一次穿法:
   **「历史总行数=0」在窗口比对象生命周期短时,和「不存在」一模一样。**
   修法:把分母守卫下沉到**(联赛, 比赛日)**,只在**两侧都有行**的日子上判。
   其余日子进第四态 `PENDING`,⛔ 既不算过也不算不过。
"""
import sqlite3, collections, sys
DB="/Users/ninoo/Nutmeg/data/v4_observation.db"
EIGHT=["EPL","ESP_LA_LIGA","ITA_SERIE_A","GER_BUNDESLIGA","FRA_LIGUE_1",
       "ENG_CHAMPIONSHIP","ESP_SEGUNDA_DIVISION","ITA_SERIE_B"]
con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
rows=con.execute("select league,source,match_date,home_team,away_team from odds_snapshots").fetchall()

#: 🚨 **比赛日级分母守卫**:只有两侧都落了行的 (联赛,比赛日) 才有资格被判。
_day=collections.defaultdict(lambda:[0,0])
for lg,src,d,_h,_a in rows:
    _day[(lg,d)][0 if src=='closing' else 1]+=1
LIVE={k for k,v in _day.items() if v[0] and v[1]}
PENDING=collections.defaultdict(list)      # 联赛 → 只有 closing 的比赛日
for (lg,d),v in _day.items():
    if v[0] and not v[1]:
        PENDING[lg].append(d)

m=collections.defaultdict(lambda:(set(),set()))
for lg,src,d,h,a in rows:
    if (lg,d) not in LIVE:
        continue                            # ← gather 未到的日子:不参与判定
    (m[lg][0] if src=='closing' else m[lg][1]).add((d,h,a))

# 参照系:已成熟联赛的实测叠合率(2026-08-14 基线 = 全库 493 键 86.8%)
BASE_OK={"NOR_ELITESERIEN","SWE_ALLSVENSKAN","KOR_K_LEAGUE_1","JPN_J1",
         "SCO_PREMIERSHIP","SUI_SUPER_LEAGUE","DNK_SUPERLIGA"}
ref=[(lg,len(m[lg][0]),len(m[lg][0]&m[lg][1])) for lg in BASE_OK if m[lg][0]]
print("参照组(别名已成熟的联赛,应为 100%):")
for lg,n,j in ref: print(f"   {lg:22s} {j}/{n}")
assert all(j==n for _,n,j in ref), "🚨 参照组自己就掉了 ⇒ 是别的东西坏了,别看下面的数"

verdict={}
print("\n本批 8 联赛:")
for lg in EIGHT:
    cl,ga=m[lg]
    pend=sorted(PENDING.get(lg,[]))
    tail=f"  ⏳ 另有 {len(pend)} 个比赛日 gather 未到({','.join(pend)}),**不计入判定**" if pend else ""
    if not cl:
        verdict[lg]="UNMEASURABLE"          # ← 分母守卫:不是绿,是「还没数据」
        print(f"   ⏳ {lg:22s} 可判比赛日的 closing 键 0 ⇒ **测不了**(不是通过){tail}")
        continue
    j=len(cl&ga)
    verdict[lg] = "PASS" if j==len(cl) else "FAIL"
    bad=sorted(cl-ga)
    print(f"   {'✅' if j==len(cl) else '🚨'} {lg:22s} {j}/{len(cl)} 叠上"
          + ("" if j==len(cl) else f"  劈开 {len(cl)-j} 键,前 5:{bad[:5]}") + tail)
n_u=sum(1 for v in verdict.values() if v=="UNMEASURABLE")
n_p=sum(len(v) for v in PENDING.values())
print(f"\n结论:PASS={sum(1 for v in verdict.values() if v=='PASS')} "
      f"FAIL={sum(1 for v in verdict.values() if v=='FAIL')} UNMEASURABLE={n_u}"
      f" · PENDING(gather 未到的比赛日)={n_p}")
if n_u: print("⚠️ 有联赛仍无可判的 closing 行 ⇒ 本次验收**不完整**,必须重跑,不许当通过。")
if n_p: print("⏳ 有比赛日只落了 closing ⇒ 那些场次**今天判不了**,"
              "gather 跟上后须重跑。⛔ 别把它们当劈开键去补别名 —— "
              "「还没采到」和「名字对不上」在这里长得一模一样。")
sys.exit(1 if any(v=="FAIL" for v in verdict.values()) else 0)
