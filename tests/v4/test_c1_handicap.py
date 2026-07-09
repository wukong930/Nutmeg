"""C1 让球修正 — implied_handicap_lines(c1=True) 的不变量。

C1 仅在 −1 线把 ``_C1_DELTA`` 从让胜(DC 高估)守恒地挪给让平(DC 低估),让负不动;
其它线与默认(c1=False, eval 路径)完全不变。δ=0.019,样本外 log-loss 配对 t=+3.56。
"""
import pytest

from nutmeg.v4.model.market_handicap import _C1_DELTA, implied_handicap_lines


def _by_line(rows):
    return {ln: (ph, pd, pa) for ln, ph, pd, pa in rows}


def test_c1_shifts_line_minus1_conserving():
    args = (0.55, 0.25, 0.20)                      # 主热;−1 线让胜 ≈0.32 > δ(不 clamp)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    r, c = raw[-1], c1[-1]
    assert c[0] == pytest.approx(r[0] - _C1_DELTA)   # 让胜 −δ
    assert c[1] == pytest.approx(r[1] + _C1_DELTA)   # 让平 +δ
    assert c[2] == pytest.approx(r[2])               # 让负 不动
    assert sum(c) == pytest.approx(sum(r))           # 质量守恒


def test_c1_leaves_other_lines_and_default_untouched():
    args = (0.55, 0.25, 0.20)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    for ln in raw:
        if ln != -1:
            assert c1[ln] == pytest.approx(raw[ln])  # 只 −1 变
    assert _by_line(implied_handicap_lines(*args)) == raw  # 默认 c1=False = raw(不动 eval)


def test_c1_clamps_when_home_cover_below_delta():
    # 主队巨冷(−1 线让胜 ≈0 < δ)→ shift=min(δ, ph):让胜不为负、仍守恒
    args = (0.05, 0.20, 0.75)
    raw = _by_line(implied_handicap_lines(*args))
    c1 = _by_line(implied_handicap_lines(*args, c1=True))
    assert c1[-1][0] >= 0.0
    assert sum(c1[-1]) == pytest.approx(sum(raw[-1]))
