#!/usr/bin/env python
"""08-14 之后的验收断言(只读)。三态输出,**分母守卫是核心**。

为什么需要分母守卫:这 8 个联赛今天 closing=0 行 ⇒ 「劈开键 = 0」在今天
是**真空真**(vacuously true)。不带分母的断言今天就绿,明天照样绿,
分不出「修好了」和「还没数据」—— 正是记忆里「零新增 ≠ 扫完了」那一族。

⚠️ 不要用 kickoff_utc 做 join 键:closing 写 '...Z',gather 写 '...+00:00',
   字符串相等永远 0%(实测全库 521 个 closing 键 0 命中)。真索引是 match_date。
"""
import sqlite3, collections, sys
DB="/Users/ninoo/Nutmeg/data/v4_observation.db"
EIGHT=["EPL","ESP_LA_LIGA","ITA_SERIE_A","GER_BUNDESLIGA","FRA_LIGUE_1",
       "ENG_CHAMPIONSHIP","ESP_SEGUNDA_DIVISION","ITA_SERIE_B"]
con=sqlite3.connect(f"file:{DB}?mode=ro",uri=True)
rows=con.execute("select league,source,match_date,home_team,away_team from odds_snapshots").fetchall()
m=collections.defaultdict(lambda:(set(),set()))
for lg,src,d,h,a in rows:
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
    if not cl:
        verdict[lg]="UNMEASURABLE"          # ← 分母守卫:不是绿,是「还没数据」
        print(f"   ⏳ {lg:22s} closing 键 0 ⇒ **测不了**(不是通过)")
        continue
    j=len(cl&ga)
    verdict[lg] = "PASS" if j==len(cl) else "FAIL"
    bad=sorted(cl-ga)
    print(f"   {'✅' if j==len(cl) else '🚨'} {lg:22s} {j}/{len(cl)} 叠上"
          + ("" if j==len(cl) else f"  劈开 {len(cl)-j} 键,前 5:{bad[:5]}"))
n_u=sum(1 for v in verdict.values() if v=="UNMEASURABLE")
print(f"\n结论:PASS={sum(1 for v in verdict.values() if v=='PASS')} "
      f"FAIL={sum(1 for v in verdict.values() if v=='FAIL')} UNMEASURABLE={n_u}")
if n_u: print("⚠️ 有联赛仍无 closing 行 ⇒ 本次验收**不完整**,必须重跑,不许当通过。")
sys.exit(1 if any(v=="FAIL" for v in verdict.values()) else 0)
