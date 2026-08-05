"""前端 `_zhFold` 与服务端 `_affix_core` 的**行为**差异清单(2026-08-06)。

## 为什么有这个文件

我在 `a06476a` 的注释里写了一句「前端 `_zhFold` 和服务端 `_LEGAL_FORM_TOKENS` 是
**同一套**封闭词表,改一处必须改两处」。**那句话当时就是假的** —— 两边各有 4 个
对方没有的记号(服务端 AS/CFC/SS/SSC 意系,前端 CP/RCD/SAD/SD 西葡系),是分头
长出来的,不是谁漏抄。

今天它没造成显示缺口:整本词典只有 `AS Roma` 一个键带这类记号,而它是精确键、
根本走不到折叠(实测盘面 334 支队,补上服务端那 4 个记号能多救出 **0** 支)。
但**把「它们相同」写进注释,比让它们不同更坏** —— 下一个人会据此认为改一边就够。
同族:「检查的前提没人检查」。

## 为什么不是「数正则里有几个 token」

那是**语法代理测语义属性**:token 数相等不等于折叠结果相同(前缀/后缀分组不同、
`\\d{2}` 只在后缀、`1\\.?` 带可选点),token 数不等也不等于有实际影响(上面 0 支)。
所以这里拿**真名字**(整本 `TEAM_NAME_ZH` 的键)跑两边、**逐条比结果**,把差异
钉成清单。任一边加减记号 ⇒ 清单变 ⇒ 这条红 ⇒ 人被迫说清楚是有意还是漏抄。

## 两边**不必**相同

它们服务于不同的问题:服务端 `_affix_core` 喂 `resolve_serving_name`(Elo 队名解析,
要求「池内唯一」),前端 `_zhFold` 喂 `zhTeam`(中文名显示,要求「绝不 mis-map」)。
所以本文件**不**断言二者相等 —— 它断言**差异是已知的那一份**。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from nutmeg.utils.team_canonical import _affix_core
from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

#: 已知差异 —— 两边折叠结果不同的**真实队名**,配根因。
#: 新增一条 ⇒ 有人动了某一边。删除一条 ⇒ 两边靠拢了。都得有人解释。
#:
#: ⭐ 我原本以为只有 `AS Roma` 一条(按「各有 4 个记号不同」推的)。**实测 15 条** ——
#: 因为真正的根因不是词表差 4 个,是**结构不同**:服务端 `_affix_core` 把名字切成词元、
#: 剥掉**任何位置**上的记号;前端 `_zhFold` 是锚定正则,只剥**开头或结尾**,而且首尾用的
#: 是两个**不同**的集合(SV/SK/AC/SC 只在前缀组 ⇒ `Hamburger SV` 折不动)。
#: 又一次「读出来的路径 ≠ 跑着的路径」—— 清单是跑出来的,不是推出来的。
#:
#: 全部 15 条今天都**不影响显示**:它们都是词典的精确键,`zhTeam` 第一步就命中,
#: 根本走不到折叠。折叠只在「盘面拼法 ≠ 词典键」时才上场。
_KNOWN_DIVERGENCE: dict[str, str] = {
    # (a) 记号只在服务端词表里 —— 前端加上就能对齐
    "AS Roma": "AS:服务端剥,前端无此记号",
    "Casa Pia AC": "AC:服务端剥(任意位置),前端 AC 只在前缀组",
    "Hamburger SV": "SV:同上,只在前缀组",
    "Karlsruher SC": "SC:同上",
    "Nashville SC": "SC:同上",
    "Orlando City SC": "SC:同上",
    "Tochigi SC": "SC:同上",
    "Vitoria SC": "SC:同上",
    "Vasteras SK FK": "SK:同上",
    # (b) 记号只在前端词表里 —— 反方向
    "AVS Futebol SAD": "SAD:前端后缀组有,服务端词表没有",
    # (c) 结构差:服务端剥「任何位置」,前端只剥首尾
    "Bucheon FC 1995": "FC 在中间 ⇒ 前端锚定正则够不着",
    "Seattle Reign FC W": "FC 在中间(后面还有 W)⇒ 同上",
    "Sarpsborg 08 FF": "08 是成立年份,在中间 ⇒ 前端 \\d{2} 只锚结尾",
    # (d) 归一化口径差,不是记号 —— 两边永远不会一致,别试图对齐
    "Bosnia & Herzegovina": "服务端 normalize_name 把 & 变 and,前端只去重音",
    "Chapecoense-sc": "服务端按连字符切词后剥 sc,前端不切词",
}


def _fe_fold_many(names: list[str]) -> dict[str, str]:
    """在 node 里跑**真的** `_zhFold`(从 dashboard.html 抠出来),不是重写一份。

    重写一份就又变成「我以为它这么折」——本文件要测的恰恰是这个。
    """
    js = DASH.read_text(encoding="utf-8")
    m = re.search(r"\nfunction _zhFold\(", js)
    assert m, "找不到 _zhFold —— 它被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    src = js[start:j + 1]
    out = subprocess.run(
        ["node", "-e", f"{src}\nconst ns={json.dumps(names)};"
                       "const o={};for(const n of ns)o[n]=_zhFold(n);"
                       "console.log(JSON.stringify(o));"],
        capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[:1500]
    return json.loads(out.stdout)


def _srv_fold(name: str) -> str:
    """服务端侧的可比形式:`_affix_core` 吐词元,拼回字符串好和前端比。"""
    return " ".join(_affix_core(name))


def _norm(s: str) -> str:
    """比之前先抹掉两边**本来就不同**的归一化口径(大小写/标点),只留「剥了哪些记号」。

    服务端 `normalize_name` 会小写化+去标点;前端 `_zhFold` 只去重音。不抹的话
    整本词典每一条都会「不同」,清单就变成噪声,护栏当天就会被删掉。
    """
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@pytest.fixture(scope="module")
def divergence() -> dict[str, tuple[str, str]]:
    """整本词典跑一遍,返回 {队名: (前端折出来的, 服务端折出来的)}。"""
    keys = sorted(TEAM_NAME_ZH)
    fe = _fe_fold_many(keys)
    return {
        k: (fe[k], _srv_fold(k))
        for k in keys
        if _norm(fe[k]) != _norm(_srv_fold(k))
    }


class TestFoldParity:
    def test_the_divergence_list_is_exactly_what_we_pinned(self, divergence):
        """⭐ 承重条 —— 两边的差异必须是**已知的那一份**。

        红了不代表有 bug,代表**有人动了某一边的封闭词表而没动另一边**。
        照失败信息把新条目补进 `_KNOWN_DIVERGENCE` 并写清原因,或者把两边对齐。
        """
        got, want = set(divergence), set(_KNOWN_DIVERGENCE)
        new = {k: divergence[k] for k in got - want}
        gone = sorted(want - got)
        assert not new, (
            f"两边折叠结果新增 {len(new)} 处分歧 —— 有人只改了一边的词表:\n"
            + "\n".join(f"  {k!r}: 前端→{v[0]!r}  服务端→{v[1]!r}" for k, v in sorted(new.items()))
        )
        assert not gone, f"这些已知分歧消失了(两边靠拢了?)—— 更新清单:{gone}"

    def test_no_dictionary_team_loses_its_chinese_name_to_folding(self, divergence):
        """⛔ 分歧可以有,**mis-map 不许有**。

        差异清单里的每一条,若前端折出来的结果**恰好命中词典里另一支队**,那就不是
        「两边不一样」而是「显示成了别的队」—— 和 `Sporting CP → 希洪竞技` 同一种病。
        """
        lower = {k.lower(): k for k in TEAM_NAME_ZH}
        bad = []
        for team, (fe, _srv) in divergence.items():
            hit = TEAM_NAME_ZH.get(fe) or TEAM_NAME_ZH.get(lower.get(fe.lower(), ""))
            if hit and hit != TEAM_NAME_ZH[team]:
                bad.append(f"{team!r}({TEAM_NAME_ZH[team]}) 折成 {fe!r} → {hit}")
        assert not bad, "折叠把队折到别人身上了:\n  " + "\n  ".join(bad)


def test_the_comment_no_longer_claims_the_two_sets_are_identical():
    """钉住那句被更正的话本身 —— 它误导过一次,别让它长回来。

    这一条**是**语法断言,而且我知道:它守的是一句**注释**,注释没有行为可跑。
    它只是补充,真正的护栏是上面两条。
    """
    js = DASH.read_text(encoding="utf-8")
    i = js.index("const AFFIX =")
    head = js[max(0, i - 2000):i]
    assert "同一套\n  // 封闭词表" not in head and "同一套封闭词表" not in head, \
        "那句「同一套封闭词表」又回来了 —— 它是假的,见 test_zhfold_parity 模块 docstring"
