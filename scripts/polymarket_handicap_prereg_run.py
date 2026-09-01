"""跑 `docs/polymarket_handicap_prereg_v1.0_2026-07-30.md`(含 §6.1 更正)。

⚠️ 一次性测量,**不进 cron**,**不改任何线上常数**(prereg §5 红线 1)。
只读打开所有数据库。

顺序严格照协议:
  §3 结构映射验证(吻合率 <99% ⇒ **停,不出结论**)
  §2 人口 + 丢弃计数(丢弃率 >20% ⇒ 告警)
  §4 主检验(唯一确认性):配对 Δlog-loss,按场聚类,双侧 t
  §4 次级(**仅描述**):判闸翻转腿数 + 按真实竞彩 SP 的 ROI
"""
from __future__ import annotations

import math
import sqlite3
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps/api/src"))

from nutmeg.v4.model.market_handicap import implied_handicap_lines  # noqa: E402

OBS = REPO / "data/v4_observation.db"
EPS = 1e-6


def _ro(p: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


# ── §3 结构映射 ────────────────────────────────────────────────────────────
def _yes_expected(spec: str, line: float, hg: int, ag: int) -> bool | None:
    """按**声明的语义**独立重算 YES —— ⛔ 故意不复用生产的 `_yes_resolves`,
    那样是循环论证(拿它自己验它自己)。半盘无 push。"""
    if spec == "HANDICAP_HOME":
        return (hg + line) > ag
    if spec == "HANDICAP_AWAY":
        return (ag + line) > hg
    return None


def verify_mapping(conn) -> tuple[int, int, list]:
    rows = conn.execute(
        "SELECT outcome_spec, line, home_goals, away_goals, outcome_hit "
        "FROM polymarket_gaps WHERE outcome_spec LIKE 'HANDICAP%' "
        "AND settled_at IS NOT NULL AND home_goals IS NOT NULL "
        "AND away_goals IS NOT NULL AND outcome_hit IS NOT NULL").fetchall()
    ok = 0
    bad = []
    for r in rows:
        exp = _yes_expected(r["outcome_spec"], float(r["line"]),
                            int(r["home_goals"]), int(r["away_goals"]))
        if exp is None:
            continue
        if int(exp) == int(r["outcome_hit"]):
            ok += 1
        else:
            bad.append(dict(r))
    return ok, len(rows), bad


# ── §2 人口 ────────────────────────────────────────────────────────────────
#: Poly 半盘 → 竞彩整数线上的**那一条腿**。索引对齐 implied_handicap_lines 的
#: (让胜, 让平, 让负)。见 prereg §3。
LEG_MAP = {
    ("HANDICAP_HOME", -1.5): (-1, 0),   # 主队净胜≥2  ≡ 竞彩 −1 线「让胜」
    ("HANDICAP_AWAY", -1.5): (1, 2),    # 客队净胜≥2  ≡ 竞彩 +1 线「让负」
}


def build_population(conn):
    jc = {}
    for r in conn.execute(
            "SELECT match_date, home_team, away_team, league, handicap_home, "
            "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, "
            "ou_line, psc_over, home_goals, away_goals "
            "FROM jingcai_sp WHERE market='hhad'"):
        jc[(r["match_date"], r["home_team"], r["away_team"])] = dict(r)

    paired, drop = [], {"no_jc": 0, "no_pinnacle": 0, "line_mismatch": 0,
                        "no_result": 0, "no_mid": 0, "fit_failed": 0}
    for r in conn.execute(
            "SELECT match_date, home_team, away_team, league, outcome_spec, line, "
            "poly_mid, home_goals, away_goals, outcome_hit, freshness_hours, depth_usd "
            "FROM polymarket_gaps WHERE outcome_spec LIKE 'HANDICAP%' "
            "AND settled_at IS NOT NULL"):
        key = (r["outcome_spec"], float(r["line"]))
        if key not in LEG_MAP:
            continue                       # 只测 ±1.5 那两个可映射的 spec
        want_line, leg_idx = LEG_MAP[key]
        j = jc.get((r["match_date"], r["home_team"], r["away_team"]))
        if j is None:
            drop["no_jc"] += 1; continue
        if j["handicap_home"] != want_line:
            drop["line_mismatch"] += 1; continue
        if not all(j[c] for c in ("psc_home", "psc_draw", "psc_away")):
            drop["no_pinnacle"] += 1; continue
        if r["poly_mid"] is None or r["outcome_hit"] is None:
            drop["no_mid"] += 1; continue
        if j["home_goals"] is None or j["away_goals"] is None:
            drop["no_result"] += 1; continue
        try:
            lines = implied_handicap_lines(
                1.0 / float(j["psc_home"]), 1.0 / float(j["psc_draw"]),
                1.0 / float(j["psc_away"]),
                (1.0 / float(j["psc_over"])) if j["psc_over"] else None,
                ou_line=float(j["ou_line"] or 2.5),
                c1=True, league=j["league"])
        except (ValueError, ZeroDivisionError, TypeError):
            drop["fit_failed"] += 1; continue
        ours = next((t for t in lines if t[0] == want_line), None)
        if ours is None:
            drop["fit_failed"] += 1; continue
        paired.append({
            "match": (r["match_date"], r["home_team"], r["away_team"]),
            "league": j["league"], "line": want_line, "leg": leg_idx,
            "p_ours": float(ours[1 + leg_idx]), "p_poly": float(r["poly_mid"]),
            "y": int(r["outcome_hit"]),
            "jc_sp": [j["jc_home"], j["jc_draw"], j["jc_away"]][leg_idx],
            "fresh_h": r["freshness_hours"], "depth": r["depth_usd"],
        })
    return paired, drop


def logloss(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -(math.log(p) if y else math.log(1 - p))


def main() -> int:
    conn = _ro(OBS)
    print("=" * 68)
    print("Polymarket 让球切片 —— prereg v1.0 + §6.1 更正 · 一次性测量")
    print("=" * 68)

    print("\n【§3】结构映射验证(吻合率 <99% ⇒ 停)")
    ok, tot, bad = verify_mapping(conn)
    rate = ok / tot if tot else 0.0
    print(f"  独立重算 vs outcome_hit:{ok}/{tot} = {rate*100:.2f}%")
    if tot == 0 or rate < 0.99:
        print("  ❌ 吻合率不足 ⇒ **停,不出结论**(prereg §3)。先查符号约定。")
        for b in bad[:5]:
            print(f"     不符样例:{b}")
        return 2
    print("  ✅ 映射成立,继续。")

    print("\n【§2】人口与丢弃")
    paired, drop = build_population(conn)
    n_drop = sum(drop.values())
    dr = n_drop / max(len(paired) + n_drop, 1)
    print(f"  配对腿 {len(paired)} · 丢弃 {n_drop} ({dr*100:.1f}%) · 明细 {drop}")
    matches = {p["match"] for p in paired}
    print(f"  去重场次 {len(matches)}")
    if dr > 0.20:
        print("  ⚠️ 丢弃率 >20%(prereg §5-4)—— 结论要打折读,先怀疑别名层")
    if not paired:
        print("  ❌ 无配对样本 ⇒ 停。")
        return 2

    print("\n【§4 主检验】配对 Δlog-loss = 我们的 P(C1,含 δ) − Poly mid")
    per_match = {}
    for p in paired:
        d = logloss(p["p_ours"], p["y"]) - logloss(p["p_poly"], p["y"])
        per_match.setdefault(p["match"], []).append(d)
    diffs = [st.mean(v) for v in per_match.values()]      # 按**场**聚类
    n = len(diffs)
    mean = st.mean(diffs)
    se = st.stdev(diffs) / math.sqrt(n) if n > 1 else float("nan")
    t = mean / se if se else float("nan")
    print(f"  N = {n} 场(聚类单位=比赛)")
    print(f"  Δ = {mean:+.4f} ± {se:.4f}  ⇒  t = {t:+.2f}")
    print(f"  (>0 = Poly 更准;判据 |t| ≥ 1.96)")
    if t >= 1.96:
        verdict = "有信号:Poly 显著更准 ⇒ ⚠️ 仍不改任何常数,走 v1.1 查混淆"
    elif t <= -1.96:
        verdict = "反向发现:我们显著更准 ⇒ 记一笔,同样不改常数"
    else:
        verdict = "测不出(= §1 的事前预期)⇒ 诚实停,⛔不再换切法"
    print(f"  ⇒ 判定:**{verdict}**")
    dmin = 2.8 * st.stdev(diffs) / math.sqrt(n) if n > 1 else float("nan")
    print(f"  §6.1 功效:本次可判定 Δ ≥ {dmin:.3f}(1X2 实测效应量 0.023)")

    print("\n【§4 次级 —— ⛔ 仅描述,不判闸、不进 FDR】")
    flip = [p for p in paired if (p["p_ours"] >= 0.5) != (p["p_poly"] >= 0.5)]
    print(f"  两侧对该腿的多空判断分歧:{len(flip)}/{len(paired)} 腿")
    for tag, key in (("我们的 P", "p_ours"), ("Poly mid", "p_poly")):
        bets = [p for p in paired if p["jc_sp"] and p[key] * float(p["jc_sp"]) - 1 >= 0.05]
        if bets:
            roi = st.mean([(float(b["jc_sp"]) - 1) if b["y"] else -1.0 for b in bets])
            print(f"  用 {tag:8s} 过 +5% 闸:{len(bets):3d} 腿 · ROI {roi*100:+.1f}%")
        else:
            print(f"  用 {tag:8s} 过 +5% 闸:0 腿")
    print("  ⚠️ prereg §4:这个量级的数字永远只能当描述,不能当证据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
