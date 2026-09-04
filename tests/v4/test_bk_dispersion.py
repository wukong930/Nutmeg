"""⚖️ 离散度:`max−min` → `p90−p10` + 重标切点(2026-09-04,预注册)。

## 为什么换

`max−min` 是**两个单点顺序统计量**之差,家数越多机械地越大。决定性实验
(同一场 · 同一时刻 · 同一批报价,只随机抽 k 家 ⇒ 联赛/热度/时间/真实分歧全被钉死):

    max−min  切点 3.0pp:k=5 18.4% → k=22 60.8%   跨度 +42.4pp
    p90−p10  切点 2.0pp:k=5 30.1% → k=22 51.4%   跨度 **+21.3pp**(砍一半)

⇒ 换尺子的**预注册通过条件**就是「跨度必须变小」,已达成。
⛔ 若没变窄,处方是回滚,不是靠调切点掩盖。

## 🚨 切点是**规则算出来的**,不是挑出来的

规则(量数据**之前**declare):**保持旧切点各自的百分位位置不变。**
实测 `max−min` 逐卡分布上 3pp = 第 31.0 百分位、6pp = 第 95.9 ⇒
`p90−p10` 上同样两个百分位 = **2.0 / 4.6pp**。
实测点亮率几乎不动(灰 31.0→32.1% · 琥珀 64.9→63.3% · 红 4.1→4.6%),
正是这条规则预期的结果 —— ⛔ 故意**不**顺手让琥珀变稀有。

## 本文件最承重的一条

**切点和统计量必须同源。** 2.0/4.6 只在「`p90−p10` + 这一把线性插值分位数尺子」
下才落在它们该在的百分位上。分位数有七八种定义,换一种这两个数就静默错位 ——
错了没人看得出来,因为屏幕上照样是三种颜色。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


class TestPercentileRuler:
    """⭐ 定切点用的那把尺子,必须就是生产在用的那把。"""

    @pytest.mark.parametrize(
        "xs,q,want",
        [
            ([1, 2, 3, 4, 5], 0.1, 1.4),      # 线性插值(numpy 默认口径)
            ([1, 2, 3, 4, 5], 0.5, 3.0),
            ([1, 2, 3, 4, 5], 0.9, 4.6),
            ([0.0, 1.0], 0.1, 0.1),           # 两点:band 的下限
            ([0.0, 1.0], 0.9, 0.9),
            ([7.0], 0.9, 7.0),                # 单点不炸
            ([], 0.5, 0.0),                   # 空不炸
        ],
    )
    def test_known_answers(self, xs, q, want):
        from nutmeg.v4.api.routes import _pctl
        assert _pctl(xs, q) == pytest.approx(want, abs=1e-9)

    def test_it_is_not_the_nearest_rank_variant(self):
        """🚨 最容易误换成的那一种(取最近秩)会给 2.0 而不是 1.4。

        换成它,2.0/4.6 这两个切点就不再落在第 31.0 / 95.9 百分位上 ——
        而屏幕上照样是三种颜色,错了看不出来。
        """
        from nutmeg.v4.api.routes import _pctl
        assert _pctl([1, 2, 3, 4, 5], 0.1) != 2.0, "退化成了取最近秩"

    def test_pctl_is_monotone_and_bounded(self):
        from nutmeg.v4.api.routes import _pctl
        xs = [0.11, 0.42, 0.19, 0.37, 0.28, 0.51]
        vals = [_pctl(xs, q / 10) for q in range(11)]
        assert vals == sorted(vals), f"分位数不单调:{vals}"
        assert min(xs) <= vals[0] and vals[-1] <= max(xs)


def _band_spread(band: list[list[float]]) -> list[float]:
    """按生产口径算三条腿的离散度。"""
    from nutmeg.v4.api.routes import _pctl
    return [(_pctl([v[i] for v in band], 0.9) - _pctl([v[i] for v in band], 0.1)) * 100.0
            for i in range(3)]


class TestStatisticIsRobustNotRange:
    """🚨 承重:一个离群家不许再主宰这个数。"""

    #: 10 家紧密一致 + 1 家离谱。极差会被那 1 家拉到 ~20pp;p90−p10 不该。
    _TIGHT = [[0.50 + i * 0.002, 0.28, 0.22 - i * 0.002] for i in range(10)]
    _OUT = [0.70, 0.20, 0.10]

    def test_one_outlier_does_not_drive_the_number(self):
        from nutmeg.v4.api.routes import _pctl
        base = _band_spread(self._TIGHT)[0]
        withx = _band_spread([*self._TIGHT, self._OUT])[0]
        rng = (max(v[0] for v in [*self._TIGHT, self._OUT])
               - min(v[0] for v in [*self._TIGHT, self._OUT])) * 100.0
        # 🚨 人口非平凡:先证明那个离群家**确实**能把极差顶起来,否则下面空洞为真
        assert rng > 15.0, f"离群家没造成大极差({rng:.1f}pp),这个 fixture 失效了"
        assert withx - base < 3.0, \
            f"加一个离群家把 p90−p10 抬了 {withx - base:.1f}pp —— 它没有抗离群"
        assert withx < rng / 2, f"p90−p10 {withx:.1f}pp 接近极差 {rng:.1f}pp"

    def test_it_is_not_max_minus_min(self):
        """⛔ 直接钉死:同一批数据上两者必须不同,否则换了个名字没换东西。"""
        band = [*self._TIGHT, self._OUT]
        mm = (max(v[0] for v in band) - min(v[0] for v in band)) * 100.0
        assert _band_spread(band)[0] != pytest.approx(mm, abs=0.01), "还是极差"


class TestCutPointsAndStatisticStayInSync:
    """🚨 **本文件最承重的一条** —— 切点只在它被校准的那个统计量下才成立。"""

    def _consts(self) -> tuple[float, float]:
        js = DASH.read_text(encoding="utf-8")
        a = re.search(r"^const _BK_DISP_AMBER = ([0-9.]+);", js, re.M)
        r = re.search(r"^const _BK_DISP_RED = ([0-9.]+);", js, re.M)
        assert a and r, "取不到切点常数 —— 本护栏失效"
        return float(a.group(1)), float(r.group(1))

    def test_constants_are_the_calibrated_values(self):
        """⛔ 这两个数由预注册规则唯一确定。改它们必须重跑那条规则,不是凭感觉挪。"""
        assert self._consts() == (2.0, 4.6), \
            "切点被改了 —— 若是重标过的,请同时更新 routes.py 那段出处注释和本断言"

    def test_the_server_no_longer_ships_a_range(self):
        """服务端若滑回 `max−min`,切点就整体偏低 ⇒ 屏幕全变红,而常数看不出问题。"""
        src = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
        i = src.index("pr.bk_spread = [")
        blk = src[i:i + 260]
        assert "_pctl(" in blk, f"bk_spread 不是用 _pctl 算的:{blk[:160]}"
        assert "max(" not in blk and "min(" not in blk, f"bk_spread 里还有 max/min:{blk[:160]}"

    def test_amber_is_below_red(self):
        a, r = self._consts()
        assert 0 < a < r, (a, r)


class TestColourHasASingleDefinition:
    """⭐ 表格那一列和 <summary> 上那个数必须共用一个配色来源。"""

    def _colour(self, d: float) -> str:
        src = _fn("_bkDispCol")
        out = subprocess.run(
            ["node", "-e", f"const _BK_DISP_AMBER=2.0,_BK_DISP_RED=4.6;\n{src}\n"
                           f"console.log(_bkDispCol({d}));"],
            capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr[:800]
        return out.stdout.strip()

    def test_three_bands(self):
        assert self._colour(1.9) == "#64748b"
        assert self._colour(2.0) == "#d97706"
        assert self._colour(4.5) == "#d97706"
        assert self._colour(4.6) == "#dc2626"

    def test_table_column_uses_the_same_definition(self):
        """🚨 表格那一列也必须走 `_bkDispCol` —— 空包弹实测:把它换回内联的
        `d >= 6 ? … : (d >= 3 ? …)`,整个文件**一条都没红**。

        那正是本次要防的分裂:summary 用新刻度、表格用旧刻度,而两个数字来自
        **同一个** `bk_spread` ⇒ 同一张卡上两处颜色互相矛盾,谁也说不清哪个对。
        """
        js = DASH.read_text(encoding="utf-8")
        m = re.search(r"const dCol = ([^;]+);", js)
        assert m, "找不到表格列的配色赋值"
        assert m.group(1).strip() == "_bkDispCol(d)", \
            f"表格列没走唯一定义点,而是:{m.group(1).strip()}"
        # 🚨 人口非平凡 + 防内联:整个文件里不许再出现写死的三档表达式
        inline = re.findall(r"\?\s*'#dc2626'\s*:", js)
        assert len(inline) <= 1, \
            f"出现了 {len(inline)} 处写死的三档配色 —— 唯一定义点被绕过了"

    def test_dcol_definition_is_the_only_place_thresholds_appear(self):
        """⛔ 旧刻度 6/3 不许以任何形式留在配色路径上。"""
        body = _fn("_bkDispCol")
        assert "_BK_DISP_RED" in body and "_BK_DISP_AMBER" in body, body
        assert "6" not in body.replace("#64748b", "").replace("#d97706", "").replace("#dc2626", ""), \
            f"_bkDispCol 里还有写死的数:{body}"

    def test_summary_number_is_coloured(self):
        """🚨 这条是「手机上看得见」的全部内容。

        窄屏 `@media (max-width:640px){.bk-opt{display:none}}` 把离散**整列**裁掉,
        而三档配色此前只写在那一列的 style 上 ⇒ **窄屏下三色刻度根本不存在**。
        owner 就是在手机上看盘的。
        ⛔ 修法不是删那条 @media(它是量 rect 修出来的,删掉等于复原旧 bug),
        而是把颜色带到已经常显的 summary 数字上。
        """
        js = DASH.read_text(encoding="utf-8")
        i = js.index("+ ' \\u00b7 ' + t('bk_spread')")
        seg = js[i:i + 300]
        assert "_bkDispCol(maxSp)" in seg, f"summary 上那个数没带颜色:{seg[:200]}"

    def test_the_narrow_screen_rule_is_still_there(self):
        """⚠️ 对照:那条 @media 必须**仍然在**。

        没有它,上一条就变成「反正列也没被裁,颜色在哪都行」—— 断言的前提消失了。
        """
        js = DASH.read_text(encoding="utf-8")
        assert "@media (max-width:640px){ .bk-opt{display:none} }" in js, \
            "窄屏裁列规则不见了 —— summary 带色那条的理由随之失效,请重新评估"

    def test_hot_flag_reads_the_constant(self):
        """⛔ summary 的 ⚠️ 不许写字面量 —— 否则会出现「表格新刻度、⚠️ 旧刻度」。"""
        js = DASH.read_text(encoding="utf-8")
        m = re.search(r"const hot = maxSp >= ([^;]+);", js)
        assert m and m.group(1).strip() == "_BK_DISP_RED", f"hot 读的是 {m and m.group(1)}"


class TestDescriptionsFollowTheStatistic:
    """描述漂了比数字错更难发现 —— 屏幕上照样有三种颜色。"""

    def test_no_surface_still_calls_it_a_range(self):
        for path, label in ((DASH, "dashboard"),
                            (REPO / "apps/api/src/nutmeg/v4/api/schemas.py", "schemas")):
            txt = path.read_text(encoding="utf-8")
            for bad in ("离散度(max−min", "= 最大 − 最小(pp)", "<b>Spread</b> = max − min"):
                assert bad not in txt, f"{label} 里还写着「{bad}」"

    def test_both_languages_name_the_new_statistic(self):
        js = DASH.read_text(encoding="utf-8")
        assert js.count("<b>p90 − p10</b>(pp,抗离群)") == 1, "中文 ⓘ 没说新统计量"
        assert js.count("<b>p90 − p10</b> (pp, outlier-robust)") == 1, "英文 ⓘ 没说新统计量"

    def test_the_cut_points_are_explained_where_they_live(self):
        """⭐ 常数旁边必须有出处,否则下一个人只能凭感觉挪。"""
        js = DASH.read_text(encoding="utf-8")
        i = js.index("const _BK_DISP_AMBER")
        head = js[max(0, i - 900):i]
        assert "百分位" in head and "预注册" in head.replace("declare", "预注册"), \
            "切点常数上方没写清它们是怎么来的"


def _fn(name: str) -> str:
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\nfunction {re.escape(name)}\s*\(", js)
    assert m, f"找不到 {name}"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)
