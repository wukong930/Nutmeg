"""nutmeg-margin-bands — 比分网格 → 净胜球分组(读法工具,配让球线用)。

A READOUT over the Dixon-Coles grid: feed Pinnacle 1X2 (+ O/U) and it prints the
goal-margin distribution with the top scorelines in each band — and, if you pass
a 让球数, the 让胜/让平/让负 split with the score CLUSTER behind each.

NOT a new signal: a 1500-fixture eval showed feeding the handicap line into the λ
fit adds ~0 info (the 1X2+O/U grid already reproduces the AH curve to ~1.5pp).
This just SYSTEMATISES the read "让球线 → 预期净胜球档 → 一簇比分".

    nutmeg-margin-bands 1.952 3.31 4.21 --ou 2.25 1.813 2.04 --handicap -1
"""
from __future__ import annotations

import argparse

from nutmeg.v4.api.routes import _pinnacle_devig_1x2
from nutmeg.v4.model.dixon_coles import (
    grid_to_handicap_1x2,
    grid_to_margin_bands,
    score_grid,
)
from nutmeg.v4.model.market_handicap import (
    DEFAULT_MAX_GOALS,
    DEFAULT_RHO,
    devig_over,
    fit_lambdas,
)


def _label(margin: int, is_tail: bool) -> str:
    if margin == 0:
        return "平局"
    return f"{'主胜' if margin > 0 else '客胜'}{abs(margin)}{'+' if is_tail else ''}球"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="比分网格 → 净胜球分组(读法工具)")
    p.add_argument("h", type=float, help="Pinnacle 主胜赔率")
    p.add_argument("d", type=float, help="Pinnacle 平赔率")
    p.add_argument("a", type=float, help="Pinnacle 客胜赔率")
    p.add_argument("--ou", nargs=3, type=float, metavar=("LINE", "OVER", "UNDER"),
                   help="Pinnacle 大小球: 盘口线 大 小(省略则仅用 1X2 拟合)")
    p.add_argument("--handicap", type=int, help="主队让球数(整数,-1 = 主让1球)")
    p.add_argument("--tail", type=int, default=3, help="净胜球折叠尾(默认 3 = 3+ 合并)")
    p.add_argument("--top", type=int, default=3, help="每档显示前几个比分(默认 3)")
    args = p.parse_args(argv)

    fair = _pinnacle_devig_1x2(args.h, args.d, args.a)
    if fair is None:
        p.error("无效的 1X2 赔率(每个都需 > 1.0)")
    ou_line, p_over = 2.5, None
    if args.ou:
        ou_line, p_over = args.ou[0], devig_over(args.ou[1], args.ou[2])
    lh, la = fit_lambdas(fair[0], fair[1], fair[2], p_over, ou_line=ou_line)
    grid = score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)

    print(f"去vig 主 {fair[0]*100:.0f}% / 平 {fair[1]*100:.0f}% / 客 {fair[2]*100:.0f}%"
          f"   λ 主 {lh:.2f} / 客 {la:.2f}")
    print(f"\n{'净胜球档':<8}{'概率':>6}   top 比分")
    print("-" * 48)
    for b in grid_to_margin_bands(grid, tail=args.tail):
        if b["p"] < 0.005:
            continue
        tops = "  ".join(f"{i}:{j} {p*100:.0f}%" for i, j, p in b["scores"][:args.top])
        print(f"  {_label(b['margin'], b['is_tail']):<8}{b['p']*100:5.0f}%   {tops}")

    if args.handicap is not None:
        L = args.handicap
        ph, pd, pa = grid_to_handicap_1x2(grid, handicap_home=L)
        cluster: dict[str, list[tuple[float, int, int]]] = {"让胜": [], "让平": [], "让负": []}
        n = grid.shape[0]
        for i in range(n):
            for j in range(n):
                diff = (i + L) - j
                key = "让胜" if diff > 0 else "让平" if diff == 0 else "让负"
                cluster[key].append((float(grid[i, j]), i, j))
        print(f"\n竞彩让球 主队 {L:+d}:  让胜 {ph*100:.0f}%  ·  让平 {pd*100:.0f}%  ·  让负 {pa*100:.0f}%")  # noqa: E501
        for key, prob in (("让胜", ph), ("让平", pd), ("让负", pa)):
            cells = sorted(cluster[key], reverse=True)[:args.top]
            tops = "  ".join(f"{i}:{j} {p*100:.0f}%" for p, i, j in cells)
            print(f"  {key} {prob*100:4.0f}%  比分簇: {tops}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
