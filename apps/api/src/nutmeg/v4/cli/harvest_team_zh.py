"""nutmeg-harvest-team-zh — 从 `jingcai_vote` 收割 EN→ZH 队名 → TEAM_NAME_ZH。

`jingcai_vote` 每行同时存着竞彩官方中文名(`home_zh`/`away_zh`)和我们的正典英文名
(`home_team`/`away_team`),等于一份**免费的权威 EN→ZH 对照表**;而展示词典
`data/team_name_zh.py` 一直是纯手工维护的。这个 CLI 把前者读出来、和后者对账。

    nutmeg-harvest-team-zh                  # 默认 dry-run,只报不写
    nutmeg-harvest-team-zh --apply          # 把「词典没有这支队」的那些写进收割块

## 纪律

* **默认 dry-run。** 会改源码的工具,默认值必须是「不动」。
* **绝不静默覆盖已有条目。** 竞彩保留 FC/CF 后缀(`首尔FC`)、我们剥掉(`首尔`),
  2026-08-06 实测 44 条这种冲突 —— 那是**编辑口径选择,不是 bug**。工具只打印,
  由人决定,一条都不动。
* **「词典已有这支队」是语义判断,不是字符串相等。** 见下。
* **一名多译 = 停,不选赢家。** 同一个英文名在 feed 里对上 >1 个中文名 ⇒ 那条整个
  拒收(**只拒那一条**,不连坐其它),打印出来让人看。
* **每一步收窄都打印,且「没找到」必须能和「没去看」区分开。** 库/表缺失 ⇒
  `HarvestBlindError` + exit 2,**绝不**退化成「新名字 0」。这条是被
  [[health-check-guardrails]] 的涓流常量 END 事故买回来的。

## 🚨 2026-08-06 返工:上面那条「绝不静默覆盖」曾经是**假的**

首版用 `en not in known`(精确键)判「词典已有这支队」。竞彩侧的英文名走的是
`sporttery.zh_to_canonical`,它吐的是**盘面拼法**(`SC Freiburg` / `PAU` /
`Fortuna Düsseldorf`),而词典存的是清洗过的短名(`Freiburg` / `Pau` /
`Fortuna Dusseldorf`)—— 精确键当然对不上,于是同一支队被当**全新队**写进去,
报告还打印「⚠️ 与词典冲突 0」。实跑(把 `_AF_SPELLING_ALIASES_2026_08` 摘掉当
pre-change 态、喂 `_ZH_OVERRIDES` 能产出的 12 行)⇒ 退 0、报 0 冲突、写入 12 条、
产生 11 组同队两名 + 4 个中文不同的 case-only 碰撞键。

所以「同一支队」现在由 `KnownTeams` 判,而且**判定逻辑就在运行时这一条路上**
(`classify` 调它),不是只活在某个测试里 —— 首版的病根正是「正确的检查存在于
测试、跑着的那条还在裸比字符串」。三条臂:

1. 精确键;
2. `sporttery._EN_OVERRIDES` 反查(词典短名 → 盘面拼法,双向);
3. `team_canonical._affix_core` 折叠(大小写 + 重音 + 法定形式记号 + 成立年份)。

判成「已有」的一律**只打印不写**:中文一致 ⇒ 🔗别名(可手工补键);中文不同 ⇒ ⚠️冲突。

## ⚠️ 这个源有硬上限,而且上限是能算出来的

`home_team` 不是外部真相 —— 它是 `sporttery.zh_to_canonical` 的输出,而那个函数
**就是本词典的反转**(+ `_ZH_OVERRIDES` / `_EN_OVERRIDES`)。所以:

* 中文侧是真外部信息(竞彩官方写法)⇒ **冲突**那一栏有真内容;
* 英文侧是我们自己的东西回流 ⇒ **新队只能来自 `_EN_OVERRIDES` 的值和 `_ZH_OVERRIDES`
  里指向词典外英文名的条目**,而且还得是词典**整支队都没有**的(同上,别名不算)。

所以「新名字 0」有两种完全不同的读法,`new_key_ceiling()` 把它们分开:上限=0 是
「这条路已经走到头」,上限>0 而命中 0 是「秋天联赛回来就会自动收到」。拿不到
sporttery 覆盖表时报「未知」,**不报 0** —— 编一个数比缺一个数更坏。
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tokenize
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from nutmeg.utils.team_canonical import _affix_core

log = logging.getLogger("harvest_team_zh")

#: 收割块的边界标记。写侧只认它们,不生成结构 —— 块本身由人建在
#: `team_name_zh.py` 里(空的),工具只重写 body。标记没了就报错,不猜。
_BEGIN = "# HARVEST-BEGIN"
_END = "# HARVEST-END"
_BLOCK_NAME = "_JINGCAI_VOTE_HARVEST"

#: 与 tests/v4/test_team_name_zh.py::test_values_are_chinese 同一区间 —— 收进来的
#: 条目必须过得了那条已有的不变量,否则 --apply 会把别人的测试搞红。
_HAN = re.compile(r"[一-鿿]")
#: ruff line-length = 100;渲染出来超长的条目宁可拒收,也不写一行会被 E501 咬的源码。
_MAX_LINE = 100


class HarvestBlindError(RuntimeError):
    """探测器自己失明 —— 库缺失 / 表缺失 / 收割块标记不见了 / 判不了「是不是同一支队」。

    与「看过了,没有新名字」严格区分:后者返回一份带扫描计数的报告,前者直接
    炸。一个分不清这两者的工具,迟早会用「0 条」把「我根本没去看」说成好消息。
    """


# ---------- 「词典里已经有这支队了吗」------------------------------------

def fold_key(name: str) -> str:
    """折到「同一支队」的可比形式(大小写 + 重音 + 法定形式记号 + 成立年份)。

    直接复用服务端 `team_canonical._affix_core`,**不另写一份**:`VfL Bochum` 和
    `Bochum`、`FC Schalke 04` 和 `Schalke 04`、`Fortuna Düsseldorf` 和
    `Fortuna Dusseldorf` 都折到同一串。

    ⚠️ 这把尺子**故意偏松**:`Vitoria SC` 和 `Vitoria` 会折到一起,而它们是两支
    不同的队。松的方向是安全的 —— 折到一起只会让条目进「冲突」栏由人决定,
    永远不会自动写。反过来(漏判成新队)才是会静默造出同队两名的那一侧。
    """
    return " ".join(_affix_core(name))


@dataclass(frozen=True)
class KnownTeam:
    """词典里被判成「和候选英文名同一支队」的那些条目。"""

    keys: tuple[str, ...]       # 命中的词典键
    zhs: tuple[str, ...]        # 它们的中文名(去重排序)
    how: str                    # 判定依据,原样打进报告


class KnownTeams:
    """判「词典里已经有这支队了吗」——  **运行时那一条**。

    构造成本是一次全词典扫描(~1000 键),`classify` 只建一次。
    """

    def __init__(self, known: Mapping[str, str], en_overrides: Mapping[str, str]) -> None:
        self._known = dict(known)
        self._by_fold: dict[str, list[str]] = {}
        for k in self._known:
            f = fold_key(k)
            if f:
                self._by_fold.setdefault(f, []).append(k)
        #: 盘面拼法 → 词典短名(`_EN_OVERRIDES` 的反转)。一个盘面拼法可能对多个短名。
        self._alias_back: dict[str, list[str]] = {}
        for short, live in en_overrides.items():
            self._alias_back.setdefault(live, []).append(short)
        self._alias_fwd = dict(en_overrides)

    def lookup(self, en: str) -> KnownTeam | None:
        """→ 词典里同一支队的条目;真的一支都没有才返回 None。"""
        if en in self._known:
            return KnownTeam((en,), (self._known[en],), "精确键")
        keys: list[str] = []
        hows: list[str] = []

        def _add(k: str, how: str) -> None:
            if k in self._known and k not in keys:
                keys.append(k)
                hows.append(how)

        for short in self._alias_back.get(en, ()):
            _add(short, f"_EN_OVERRIDES 别名 ← {short!r}")
        fwd = self._alias_fwd.get(en)
        if fwd:
            _add(fwd, f"_EN_OVERRIDES 别名 → {fwd!r}")
        f = fold_key(en)
        if f:
            for k in self._by_fold.get(f, ()):
                _add(k, f"折叠同名 ← {k!r}")
        if not keys:
            return None
        zhs = tuple(sorted({self._known[k] for k in keys}))
        return KnownTeam(tuple(keys), zhs, " / ".join(hows))


def load_en_overrides() -> dict[str, str]:
    """`sporttery._EN_OVERRIDES`(词典短名 → 盘面拼法)。拿不到就**停**,不降级。

    没有它就分不出 `SC Freiburg` 是不是词典里的 `Freiburg` —— 降级成裸比字符串
    正是首版那个 bug。判不了就别判,`HarvestBlindError` 让人看见。
    """
    try:
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES
    except Exception as exc:  # noqa: BLE001 — 任何导入失败都等于「判不了」
        raise HarvestBlindError(
            "拿不到 sporttery._EN_OVERRIDES —— 没有它就分不出盘面拼法和词典短名"
            f"是不是同一支队,判「新」会写出同队两名。停,不猜:{exc}") from exc
    return dict(_EN_OVERRIDES)


@dataclass(frozen=True)
class HarvestReport:
    """一次收割的全部去向。每个名字槽位都必须落进恰好一个桶里。"""

    db_path: str
    n_rows: int                                    # 扫过的 jingcai_vote 行数
    n_slots: int                                   # 有中文名的队名槽位数(每行 ≤2)
    agree: dict[str, str] = field(default_factory=dict)          # EN → ZH,精确键且一致
    aliases: dict[str, tuple[str, str]] = field(default_factory=dict)   # EN → (词典键, ZH)
    conflicts: dict[str, tuple[str, str]] = field(default_factory=dict)  # EN → (词典, 竞彩)
    new: dict[str, str] = field(default_factory=dict)            # EN → ZH,可写
    ambiguous: dict[str, list[str]] = field(default_factory=dict)  # EN → 多个 ZH,拒收
    unmapped_zh: dict[str, int] = field(default_factory=dict)    # 有中文但无 EN,收不了
    rejected: dict[str, tuple[str, str]] = field(default_factory=dict)   # EN → (ZH, 原因)
    matched_how: dict[str, str] = field(default_factory=dict)    # EN → 判成同队的依据

    @property
    def n_distinct_en(self) -> int:
        return (len(self.agree) + len(self.aliases) + len(self.conflicts) + len(self.new)
                + len(self.ambiguous) + len(self.rejected))


# ---------- 读 ----------------------------------------------------------

def read_slots(conn: sqlite3.Connection) -> tuple[int, list[tuple[str | None, str]]]:
    """→ ``(行数, [(canonical_en|None, 竞彩_zh), ...])``。只读。

    表不在(或列对不上,或这个文件压根不是 SQLite 库)⇒ `HarvestBlindError`,
    **不是**空列表。空列表会被下游读成「feed 里没名字」,而真相是「没去看」。
    ⚠️ 捕的是 `sqlite3.Error`(基类)不是 `OperationalError`:「文件不是数据库」
    抛的是 `DatabaseError`,只捕子类会让它一路漏成未捕异常。
    """
    try:
        rows = conn.execute(
            "SELECT home_team, away_team, home_zh, away_zh FROM jingcai_vote").fetchall()
    except sqlite3.Error as exc:
        raise HarvestBlindError(f"读不到 jingcai_vote:{exc}") from exc
    slots: list[tuple[str | None, str]] = []
    for home_en, away_en, home_zh, away_zh in rows:
        for en, zh in ((home_en, home_zh), (away_en, away_zh)):
            if zh and str(zh).strip():
                slots.append((str(en).strip() if en else None, str(zh).strip()))
    return len(rows), slots


def _reject_reason(en: str, zh: str) -> str | None:
    """条目**本身**不可写的原因(可写 → None)。写源码前的最后一道闸。

    只管这一条自己长得对不对;「和词典/同批其它条目撞不撞」由 `classify` 管
    (那需要词典,这里拿不到)。
    """
    if not en or not zh:
        return "名字为空"
    for s in (en, zh):
        if any(c in s for c in '"\\\n\r\t') or not s.isprintable():
            return "含引号/反斜杠/控制字符 —— 不往源码里写"
    if en == zh:
        return "中英文相同(没翻译)"
    if not _HAN.search(zh):
        return "中文名里没有汉字"
    if len(_render_entry(en, zh)) > _MAX_LINE:
        return f"渲染后 {len(_render_entry(en, zh))} 字符 > {_MAX_LINE}(会撞 E501)"
    return None


def _reject_case_collisions(rep: HarvestReport, known: Mapping[str, str]) -> None:
    """把会造成「中文不同的 case-only 碰撞键」的新条目挪进 rejected。

    前端 `TEAM_ZH_LOWER` 按小写建索引(末位胜)⇒ 两个只差大小写、中文却不同的键
    会让显示变成**取决于字典顺序**。既有不变量
    `test_dict_has_no_case_only_collisions` 守的就是这个(它只在中文**不同**时红,
    所以这里也只拦中文不同的 —— 中文相同的 case 变体词典里本来就有 6 组)。

    折叠臂通常先一步把这类判成冲突;这条是**同批内部**两条新条目互撞的兜底,
    那条路折叠臂够不着。
    """
    by_lower: dict[str, list[tuple[str, str]]] = {}
    for k, v in known.items():
        by_lower.setdefault(k.lower(), []).append((k, v))
    for en in sorted(rep.new):
        by_lower.setdefault(en.lower(), []).append((en, rep.new[en]))
    for group in by_lower.values():
        if len(group) < 2 or len({v for _k, v in group}) < 2:
            continue
        for k, v in group:
            if k in rep.new:
                others = sorted({f"{o!r}→{w}" for o, w in group if o != k})
                rep.new.pop(k)
                rep.rejected[k] = (v, f"case-only 碰撞键且中文不同:{'、'.join(others)}")


def classify(slots: list[tuple[str | None, str]], known: Mapping[str, str],
             *, db_path: str = "", n_rows: int = 0,
             known_teams: KnownTeams | None = None) -> HarvestReport:
    """把槽位分桶。纯函数,不碰库也不碰文件。

    `known_teams` 不给就用运行时那一套(`load_en_overrides()`)—— 给参数只是为了
    让测试能注入一份合成覆盖表,**默认路径必须是真的那条**。
    """
    kt = known_teams if known_teams is not None else KnownTeams(known, load_en_overrides())
    by_en: dict[str, set[str]] = {}
    unmapped: Counter[str] = Counter()
    for en, zh in slots:
        if en:
            by_en.setdefault(en, set()).add(zh)
        else:
            unmapped[zh] += 1

    rep = HarvestReport(db_path=db_path, n_rows=n_rows, n_slots=len(slots),
                        unmapped_zh=dict(unmapped.most_common()))
    for en in sorted(by_en):
        zhs = by_en[en]
        if len(zhs) > 1:
            # 一名多译:不选赢家,整条拒收。挑一个「看起来对」的正是这类工具
            # 出错的方式 —— 它会挑得很自信。
            rep.ambiguous[en] = sorted(zhs)
            continue
        zh = next(iter(zhs))
        why = _reject_reason(en, zh)
        if why:
            rep.rejected[en] = (zh, why)
            continue
        hit = kt.lookup(en)
        if hit is None:
            rep.new[en] = zh
            continue
        rep.matched_how[en] = hit.how
        if zh not in hit.zhs:
            rep.conflicts[en] = (" / ".join(hit.zhs), zh)
        elif hit.keys == (en,):
            rep.agree[en] = zh
        else:
            rep.aliases[en] = (hit.keys[0], zh)
    _reject_case_collisions(rep, known)
    return rep


def harvest(db_path: str | Path, known: Mapping[str, str],
            *, known_teams: KnownTeams | None = None) -> HarvestReport:
    """打开库 → 读 → 分桶。库文件不存在 / 打不开 ⇒ `HarvestBlindError`。"""
    p = Path(db_path)
    if not p.exists():
        raise HarvestBlindError(f"库不存在:{p} —— 这是「没去看」,不是「没有新名字」")
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise HarvestBlindError(f"打不开库 {p}:{exc}") from exc
    try:
        n_rows, slots = read_slots(conn)
    finally:
        conn.close()
    return classify(slots, known, db_path=str(p), n_rows=n_rows, known_teams=known_teams)


def new_key_ceiling(known: Mapping[str, str], *,
                    known_teams: KnownTeams | None = None) -> set[str] | None:
    """`zh_to_canonical` 能吐出、而词典**整支队都没有**的英文名 = 本源新键的硬上限。

    「整支队都没有」和 `classify` 用的是**同一把尺子**(`KnownTeams`)—— 上限若还
    按精确键算,就会把 26 个别名键算成「26 个新队」,而 classify 一个都不会写,
    报告和行为对不上。

    拿不到 sporttery 的覆盖表就返回 None(报「未知」),**绝不返回空集合** ——
    「上限 0」和「不知道上限」是两回事,前者会让人以为这条路走到头了。
    """
    try:
        from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_OVERRIDES
    except Exception:  # noqa: BLE001 — 诊断项,拿不到就诚实说不知道
        log.debug("sporttery 覆盖表导入失败", exc_info=True)
        return None
    kt = known_teams if known_teams is not None else KnownTeams(known, _EN_OVERRIDES)
    emittable = {_EN_OVERRIDES.get(en, en) for en in set(known) | set(_ZH_OVERRIDES.values())}
    return {en for en in emittable if kt.lookup(en) is None}


# ---------- 写 ----------------------------------------------------------

def _render_entry(en: str, zh: str) -> str:
    return f"    {json.dumps(en, ensure_ascii=False)}: {json.dumps(zh, ensure_ascii=False)},"


def _pad(s: str, width: int) -> str:
    """按终端显示宽度补齐(汉字占 2 列)。`str.ljust` 按码点数,中文列会全部错位。"""
    used = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    return s + " " * max(1, width - used)


def _marker_at(text: str, marker: str) -> int:
    """标记的**行首**位置。整行必须就是标记本身,而且只许出现一次。

    ⚠️ 裸 `str.find` 会被**注释里提到这个标记的散文**劫持 —— 上面那段块头注释
    只要写一句「别在 `# HARVEST-BEGIN` 和 `# HARVEST-END` 之间加东西」,整块的
    起点就跑到注释里去了,然后 `ast.parse` 拿到半句话报「收割块解析失败」。
    (返工时真踩到了。)出现多次也不猜位置,直接报失明。
    """
    hits = [mt.start() for mt in re.finditer(rf"^{re.escape(marker)}$", text, re.M)]
    if len(hits) != 1:
        raise HarvestBlindError(
            f"收割块标记 {marker} 在文件里出现 {len(hits)} 次(要求恰好 1 次,且独占一行)"
            " —— 工具不猜位置,不写。")
    return hits[0]


def _split(text: str) -> tuple[str, str, str]:
    i, j = _marker_at(text, _BEGIN), _marker_at(text, _END)
    if j < i:
        raise HarvestBlindError(f"{_END} 出现在 {_BEGIN} 之前 —— 工具不猜位置,不写。")
    return text[:i], text[i:j + len(_END)], text[j + len(_END):]


def _parse_block(block: str) -> dict[str, str]:
    """块里的字面量 dict。解析失败就炸,不当成空块 —— 当成空块就等于把人手写
    进去的东西无声抹掉。"""
    body = block[len(_BEGIN):-len(_END)]
    try:
        tree = ast.parse(body.strip())
        for node in tree.body:
            if isinstance(node, ast.AnnAssign | ast.Assign) and node.value is not None:
                targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                if any(isinstance(t, ast.Name) and t.id == _BLOCK_NAME for t in targets):
                    return dict(ast.literal_eval(node.value))
    except (SyntaxError, ValueError) as exc:
        raise HarvestBlindError(f"收割块解析失败:{exc}") from exc
    raise HarvestBlindError(f"收割块里没有 {_BLOCK_NAME} 赋值")


def block_extras(block: str) -> list[str]:
    """块里**除了那个 dict 赋值以外**的东西 —— 整块重写会把它们静默丢掉。

    `_render_block` 只吐键值对。所以块内的注释和别的语句在重写后就没了,而工具
    还会打「✅ 已写入」。返回它们,由 `apply_new_entries` 拒写、由报告打印出来 ——
    「要么保留,要么明确报告丢了什么」,不许第三种。
    """
    body = block[len(_BEGIN):-len(_END)]
    extras: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(body).readline):
            if tok.type == tokenize.COMMENT:
                extras.append(f"第 {tok.start[0]} 行注释:{tok.string.strip()}")
    except tokenize.TokenError as exc:
        raise HarvestBlindError(f"收割块 token 化失败:{exc}") from exc
    try:
        tree = ast.parse(body.strip())
    except SyntaxError as exc:
        raise HarvestBlindError(f"收割块解析失败:{exc}") from exc
    for node in tree.body:
        targets = ([node.target] if isinstance(node, ast.AnnAssign)
                   else getattr(node, "targets", []))
        if any(isinstance(t, ast.Name) and t.id == _BLOCK_NAME for t in targets):
            continue
        extras.append(f"第 {node.lineno} 行语句:{ast.unparse(node)[:60]}")
    return extras


def _render_block(entries: Mapping[str, str]) -> str:
    # `dict[str, str]` 而非 `Dict[...]`:后者是 ruff UP006,写出来等于每次 --apply
    # 都给自己的 diff 加一条新 lint。
    lines = [_BEGIN, f"{_BLOCK_NAME}: dict[str, str] = {{"]
    lines += [_render_entry(k, entries[k]) for k in sorted(entries)]
    lines += ["}", _END]
    return "\n".join(lines)


def read_dict_file(path: str | Path) -> dict[str, str]:
    """按路径加载词典模块,返回**完整的** TEAM_NAME_ZH。

    按路径而不是 import 名加载,是为了让「读到的词典」和「要写的文件」永远是
    同一个东西 —— 否则测试写临时文件、判重却查线上词典,幂等性无从谈起。
    """
    p = Path(path)
    spec = importlib.util.spec_from_file_location("_nutmeg_team_name_zh_target", p)
    if spec is None or spec.loader is None:
        raise HarvestBlindError(f"加载不了词典模块:{p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    known = getattr(mod, "TEAM_NAME_ZH", None)
    if not isinstance(known, dict):
        raise HarvestBlindError(f"{p} 里没有 TEAM_NAME_ZH dict")
    return dict(known)


_PROBE = """\
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("_probe_team_name_zh", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(json.dumps(sorted(mod.TEAM_NAME_ZH), ensure_ascii=False))
"""


def _verify_importable(path: Path, expected_keys: set[str]) -> None:
    """真在**子进程里 import 一次**,并断言键集就是预期那一套。

    `ast.parse` 只证明「能解析」。整块重写若把块里别的语句一起删掉,写出来的文件
    照样 parse 得过,import 时才 NameError —— 那正是「语法代理测语义属性」。
    子进程:失败不能污染当前进程已加载的模块,也不能让探测本身把文件跑起来的
    副作用留在这边。

    ⚠️ `PYTHONDONTWRITEBYTECODE=1`:探针 import 的是那个 `.harvest-tmp-*.py`,
    默认会顺手在同目录 `__pycache__/` 里留一个同名 `.pyc`。`_atomic_write` 的
    `finally` 只 unlink 得掉 `.py` ⇒ 每跑一次 `--apply` 攒一个孤儿字节码,而且
    它带着 tmp 文件名、永远不会再被命中。这里从源头不生成,而不是在下游追着删。
    """
    out = subprocess.run([sys.executable, "-c", _PROBE, str(path)],
                         capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if out.returncode != 0:
        raise HarvestBlindError(
            f"渲染出来的词典 import 不了,已放弃写入:{out.stderr.strip()[-800:]}")
    try:
        got = set(json.loads(out.stdout))
    except ValueError as exc:
        raise HarvestBlindError(f"探针输出读不了,已放弃写入:{exc}") from exc
    if got != expected_keys:
        missing = sorted(expected_keys - got)[:8]
        extra = sorted(got - expected_keys)[:8]
        raise HarvestBlindError(
            f"import 后 TEAM_NAME_ZH 有 {len(got)} 键,期望 {len(expected_keys)};"
            f"少了 {missing},多了 {extra} —— 已放弃写入")


def _atomic_write(p: Path, text: str, expected_keys: set[str]) -> None:
    """同目录 tmp → 子进程 import 复核 → `os.replace`。

    中途挂掉(磁盘满 / Ctrl-C / OOM / 掉电)时,`p` 要么是旧内容要么是新内容,
    **不会**停在半截字符串上。就地 `write_text` 会先截断:实测卡住写入
    (RLIMIT_FSIZE)后文件停在 `"Nutmeg Fill 0254 FC": "填` —— 字符串没闭合、
    再 import 直接 SyntaxError,而这个模块被 API/dashboard/所有 CLI 顶层 import
    ⇒ 整个服务起不来,而且同目录连个 .bak 都没有。
    """
    # 同目录(才能 `os.replace`)、点开头(不显眼)、**后缀仍是 .py**:
    # `spec_from_file_location` 认后缀,叫 `xxx.py.tmp` 会直接拿不到 loader,
    # 于是复核每次都「import 不了」—— 一个只会在写入路径上发作的假红。
    tmp = p.with_name(f".{p.stem}.harvest-tmp-{os.getpid()}{p.suffix}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _verify_importable(tmp, expected_keys)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def apply_new_entries(path: str | Path, new: Mapping[str, str]) -> int:
    """把 `new` 并进收割块并落盘,返回**实际新增**条数。

    * 渲染 → `ast.parse` → 复核块内容 → 写同目录 tmp → **子进程真 import 一次**
      → `os.replace`。宁可什么都不写,也不留一个坏掉的 `team_name_zh.py`。
    * 已在块里且值相同的条目不计新增 ⇒ 重复跑是 no-op(幂等)。
    * 已在块里但值不同的,这里**不会**出现 —— 它们在 classify 里已经是 conflict。
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    head, block, tail = _split(text)
    extras = block_extras(block)
    if extras:
        raise HarvestBlindError(
            "收割块里有整块重写会丢掉的东西,已放弃写入(请把它们移到标记之外):\n  "
            + "\n  ".join(extras))
    current = _parse_block(block)
    merged = dict(current)
    merged.update(new)
    if merged == current:
        return 0

    new_text = head + _render_block(merged) + tail
    try:
        ast.parse(new_text)
    except SyntaxError as exc:
        raise HarvestBlindError(f"渲染出来的词典解析不了,已放弃写入:{exc}") from exc
    if _parse_block(_split(new_text)[1]) != merged:
        raise HarvestBlindError("渲染复核对不上,已放弃写入")
    _atomic_write(p, new_text, set(read_dict_file(p)) | set(merged))
    return len(merged) - len(current)


# ---------- 报告 --------------------------------------------------------

def _print_list(rep_items: list[str], show: int) -> list[str]:
    """截断 + **把截掉的条数说出来**。静默截断 = 假装覆盖全了。"""
    if len(rep_items) <= show:
        return rep_items
    return [*rep_items[:show], f"     …… 其余 {len(rep_items) - show} 条(--show 调多)"]


def _print_report(rep: HarvestReport, ceiling: set[str] | None, *, show: int,
                  extras: list[str] | None = None) -> None:
    print(f"竞彩 vote-feed 队名收割 · 库 {rep.db_path}")
    print(f"已扫描:jingcai_vote {rep.n_rows} 行 → {rep.n_slots} 个队名槽位 → "
          f"{rep.n_distinct_en} 个不同英文名")
    print(f"  ✅ 与词典一致        {len(rep.agree):4d}")
    print(f"  🔗 同队别名拼法      {len(rep.aliases):4d}   ← 中文一致,只是词典键拼法不同,工具不写")
    print(f"  ⚠️ 与词典冲突        {len(rep.conflicts):4d}   ← 编辑口径选择,工具不动")
    print(f"  🆕 词典没有这支队    {len(rep.new):4d}")
    print(f"  ⛔ 一名多译(拒收)  {len(rep.ambiguous):4d}")
    print(f"  🈳 有中文但无英文名  {len(rep.unmapped_zh):4d}   ← 收不了(没有键),需人工给 EN")
    print(f"  🚫 不合法(拒收)    {len(rep.rejected):4d}")

    if extras:
        print(f"\n🛑 收割块里有 {len(extras)} 处会被整块重写丢掉的内容 —— --apply 会拒写:")
        for line in extras:
            print(f"     {line}")

    if rep.n_rows == 0:
        print("\n注:表在,但一行都没有 —— 这是「看过了,feed 是空的」,不是「没去看」"
              "(没去看会以 HarvestBlindError 退出 2)。")

    if rep.new:
        print(f"\n🆕 词典没有这支队({len(rep.new)}):")
        for line in _print_list(
                [f"     {_pad(en, 34)} → {rep.new[en]}" for en in sorted(rep.new)], show):
            print(line)
    else:
        n_ceil = "未知" if ceiling is None else str(len(ceiling))
        print(f"\n🆕 0 条 —— 已扫过上面那 {rep.n_slots} 个槽位,feed 里确实没有词典没见过的队。")
        print("   结构上限:`home_team` 来自 `zh_to_canonical`(= 本词典的反转 + "
              "_ZH_OVERRIDES/_EN_OVERRIDES),")
        print(f"   所以这个源**最多**能给出 {n_ceil} 支新队。", end="")
        if ceiling is None:
            print(" 上限算不出来(拿不到 sporttery 覆盖表),不是 0。")
        elif not ceiling:
            # ⚠️ 别读成「这工具没用了」:上限只反映**此刻**的覆盖表,`_EN_OVERRIDES` /
            # `_ZH_OVERRIDES` 一加**新队**就会重新长出来(加别名拼法不会 —— 那是
            # 同一支队);而 ⚠️冲突 / 🔗别名 / 🈳无英文名 三栏一直在盯,🈳 那栏正是
            # 秋天英乙/东欧杯赛上盘时的补录清单。
            print(" 上限为 0 = 此刻这个源给不出没见过的队(覆盖表加新队才会重新长出来);")
            print("   ⚠️冲突 / 🔗别名 / 🈳无英文名 三栏不受此限,照常盯。")
        else:
            print(f" 当前 feed 一个都没碰到,例如:{'、'.join(sorted(ceiling)[:5])} ……")
            print("   (这些是盘面真实拼法,竞彩盘面出现该联赛时才会进 feed。)")

    if rep.aliases:
        print(f"\n🔗 同队别名拼法({len(rep.aliases)})—— 中文和词典一致,只是键的拼法不同。"
              "工具不写;要让盘面这个拼法也命中词典,手工补键:")
        lines = ["  " + _pad(_render_entry(en, rep.aliases[en][1]), 58)
                 + f"# {rep.matched_how.get(en, '')}"
                 for en in sorted(rep.aliases)]
        for line in _print_list(lines, show):
            print(line)

    if rep.conflicts:
        print(f"\n⚠️ 与词典冲突({len(rep.conflicts)})—— 一条都没动。要采纳哪条,"
              "手工写进对应联赛块:")
        lines = []
        for en in sorted(rep.conflicts):
            dict_zh, feed_zh = rep.conflicts[en]
            lines.append("  " + _pad(_render_entry(en, feed_zh), 58)
                         + f"# 词典现为「{dict_zh}」({rep.matched_how.get(en, '')})")
        for line in _print_list(lines, show):
            print(line)

    if rep.ambiguous:
        print(f"\n⛔ 一名多译({len(rep.ambiguous)})—— 整条拒收,不选赢家:")
        for line in _print_list(
                [f"     {_pad(en, 34)} → {' / '.join(rep.ambiguous[en])}"
                 for en in sorted(rep.ambiguous)], show):
            print(line)

    if rep.unmapped_zh:
        print(f"\n🈳 竞彩有中文名但映不到英文名({len(rep.unmapped_zh)})—— 这个方向收不了,"
              "要人工在 sporttery._ZH_OVERRIDES 里给英文名:")
        for line in _print_list(
                [f"     {zh}  ×{n}" for zh, n in rep.unmapped_zh.items()], show):
            print(line)

    if rep.rejected:
        print(f"\n🚫 不合法({len(rep.rejected)}):")
        lines = []
        for en in sorted(rep.rejected):
            zh, why = rep.rejected[en]
            lines.append(f"     {_pad(en, 34)} → {zh!r}  ({why})")
        for line in _print_list(lines, show):
            print(line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="从 jingcai_vote 收割 EN→ZH 队名,对账 / 写入 TEAM_NAME_ZH")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--dict-path", default=None,
                    help="team_name_zh.py 路径(默认 = 线上那个)")
    ap.add_argument("--apply", action="store_true",
                    help="真写。不给就是 dry-run(默认),只报不改。")
    ap.add_argument("--show", type=int, default=20, help="每一栏最多打印几条(默认 20)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.dict_path:
        dict_path = Path(args.dict_path)
    else:
        from nutmeg.v4.data import team_name_zh
        dict_path = Path(team_name_zh.__file__)

    try:
        known = read_dict_file(dict_path)
        extras = block_extras(_split(dict_path.read_text(encoding="utf-8"))[1])
        rep = harvest(args.db, known)
    except HarvestBlindError as exc:
        # 失明必须炸得响:退 2,和「跑完了、没新名字」(退 0)彻底分开。
        log.error("❌ 收割器失明,没有产出任何结论:%s", exc)
        return 2

    _print_report(rep, new_key_ceiling(known), show=args.show, extras=extras)

    if not args.apply:
        print("\n(dry-run — 没写任何东西。确认无误后加 --apply。)")
        return 0
    if not rep.new:
        print("\n--apply:没有可写的新名字,词典原样未动。")
        return 0

    try:
        n = apply_new_entries(dict_path, rep.new)
    except HarvestBlindError as exc:
        log.error("❌ 写入失败,词典未改:%s", exc)
        return 2
    print(f"\n✅ 已写入 {dict_path}:收割块新增 {n} 条。")

    try:
        after = read_dict_file(dict_path)
        left = classify([(en, zh) for en, zh in rep.new.items()], after).new
    except HarvestBlindError as exc:
        log.error("❌ 写后复查失败:%s", exc)
        return 2
    if left:
        print(f"⚠️ 复查:仍有 {len(left)} 条判为「新」—— 写入不是幂等的,请查")
        return 1
    print("复查:0 条待写(幂等)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
