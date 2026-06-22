"""nutmeg-handicap-triples — 让球三元组报告.

Assembles 〈竞彩让球 SP × Pinnacle 收盘重构 P × 让球结算〉 from the forward-captured
observation DB and prints the EV-vs-realized + reconstruction-calibration report.
Read-only; computes on demand, writes nothing.

    nutmeg-handicap-triples [--db data/v4_observation.db] [--min-ev 0.05] [--limit N]
"""
from __future__ import annotations

import argparse

from nutmeg.v4.observation.handicap_triples import (
    assemble_handicap_triples,
    format_report,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="nutmeg-handicap-triples",
        description="让球三元组(竞彩让球 SP × Pinnacle 收盘重构 P × 让球结算)报告",
    )
    ap.add_argument("--db", default="data/v4_observation.db", help="观测库路径")
    ap.add_argument(
        "--min-ev", type=float, default=0.05, help="+EV 选择门槛(默认 +5%%)"
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="逐场只显示前 N 条(默认全部)"
    )
    args = ap.parse_args(argv)

    triples = assemble_handicap_triples(args.db)
    print(format_report(triples, min_ev=args.min_ev, limit=args.limit))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
