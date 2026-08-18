"""体检 cron 必须跑在**它监视的那批 cron 之后**(2026-08-18,owner 授权改 cron)。

## 出事的形状

`daily_health_check` 原来在 **09:45**,而早晨批次是:

    09:00  morning_odds · daily_predict · daily_wc_predict
    09:45  daily_health_check          ← 看门狗
    09:50  sporttery_open
    10:00  snapshot_board · morning_recommend · polymarket_gaps
    11:05  sporttery_open(二档)
    11:10  sporttery_vote

⇒ **看门狗结构性地跑在被看的 cron 之前**,它看到的永远是「昨天的最新数据」。

这是 `jingcai_sp[open]` 每周二假红的**三个成因之一**(另两个:哨兵口径量错了东西、
阈值贴着噪声边缘 —— 都在 `af1c961` 修掉了)。单修哨兵不修排期,
下一个「按天算陈旧」的指标还会踩同一个坑。

⇒ 挪到 **11:30**(早晨最后一个作业 11:10 之后 20 分钟;实测这些作业各 5-8 秒跑完)。
⚠️ **21:00 那档不动** —— 它落在傍晚批次(17:00–23:00 每 30 分)中段,
   看到的是当天早+午的完整数据,没有倒序问题。

## ⭐ 为什么要有这条测试

本仓记过 [[live-cron-vs-setup-source-drift]]:**改 setup 脚本 ≠ 改已装的 launchd**,
而且 `kickstart -k` **不重读 plist**(排期变更必须 `bootout` + `bootstrap`)。
所以「排期」这件事有三份真相:setup 脚本 / 磁盘 plist / launchd 内存。
本测试守**第一份**(能进版本库的那份),另两份靠交付时的三方比对
(见本次提交信息里的实测输出)。
"""
from __future__ import annotations

import pathlib
import re

_SETUP = pathlib.Path(__file__).resolve().parents[2] / "scripts/setup_local_pipeline.sh"


#: 一个 shell 双引号串,**允许内部转义引号**(`\"`)。
#: 🚨 第一版写的是 `"[^"]*"` —— 命令串里有 `\"$NUTMEG_SPORTTERY_ENABLED\"` 这类转义,
#:    匹配在第一个 `\"` 处就断了 ⇒ 后面的 extra_times 参数**没匹配上** ⇒
#:    `sporttery_vote` 只解析出 23:20(丢了 **11:10**)、`sporttery_open` 只剩 11:05
#:    (丢了 **09:50**)—— 而这两个正是排序断言最该看的。
#:    空包弹②(把体检挪到 11:08)因此**没打红**。
_QSTR = r'"(?:[^"\\]|\\.)*"'


def _blocks() -> list[tuple[str, str]]:
    """把每个 `install_job` 调用切成 (label, 整段原文),供解析与自检共用。"""
    s = _SETUP.read_text(encoding="utf-8")
    hits = [(m.start(), m.group(1)) for m in re.finditer(r'install_job\s+"([\w.]+)"', s)]
    out = []
    for i, (pos, label) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(s)
        out.append((label, s[pos:end]))
    return out


def _jobs() -> dict[str, list[tuple[int, int]]]:
    """从 setup 脚本解析 {label: [(hour, minute), ...]}。"""
    out: dict[str, list[tuple[int, int]]] = {}
    for label, blk in _blocks():
        m = re.search(
            # weekday 那一格既可能是引号串 `""`,也可能是**裸数字**(weekly 作业写
            # `4 0 0 \\`)⇒ 两种都要认。第一版只认引号串,静默漏掉 3 个 weekly 作业,
            # 而那是被上面的完整性自检抓出来的(不是我想到的)。
            rf'install_job\s+"[\w.]+"\s*\\\s*\n\s*(\d+)\s+(\d+)\s+(?:{_QSTR}|\S+)\s*\\\s*\n'
            rf'\s*{_QSTR}(?:\s*\\?\s*\n?\s*"([^"]*)")?',
            blk,
        )
        if not m:
            continue
        times = [(int(m.group(1)), int(m.group(2)))]
        for t in (m.group(3) or "").split():
            if ":" in t:
                hh, mm = t.split(":")
                times.append((int(hh), int(mm)))
        out[label] = times
    return out


def test_parser_finds_every_install_job_invocation():
    """前提自检① —— 文件里有几个 `install_job`,就必须解析出几个。"""
    blocks = {lbl for lbl, _ in _blocks()}
    parsed = set(_jobs())
    missed = sorted(blocks - parsed)
    assert not missed, f"这些 `install_job` 调用没被解析出来:{missed} —— 正则需要更新"
    assert len(parsed) >= 15, f"只解析到 {len(parsed)} 个 —— 提取器坏了"


def test_parser_does_not_silently_drop_extra_times():
    """🚨 前提自检② —— **这条是空包弹逼出来的**。

    第一版的正则在命令串的转义引号 `\"` 处断掉 ⇒ **extra_times 被静默丢弃**:
    `sporttery_vote` 只剩 23:20(丢 11:10)、`sporttery_open` 只剩 11:05(丢 09:50)。
    而当时的自检只查「找到几个标签」,**没查时间完不完整** ⇒ 它是绿的,
    而空包弹「把体检挪到 11:08」没打红。

    ⭐ 判据从**文件自身**推导:凡是调用里带了 extras 参数(末尾那个含 `:` 的引号串)的,
    解析出的时间必须 > 1 个。不硬编码任何期望时刻。
    """
    j = _jobs()
    bad = []
    for label, blk in _blocks():
        # extras = 独占一行的「时刻列表引号串」,形如 `  "11:10 17:0"`。
        # 🚨 第一版用 `...\s*$` 锚定**块尾** —— 而块一直延伸到下一个 `install_job`,
        #    尾部是注释 ⇒ **永远匹配不上** ⇒ 这条检查是**空的**(它绿是因为什么都没查)。
        #    空包弹④(把 `_QSTR` 退回丢 extras 的老正则)因此没打红。
        # ⇒ 改成 MULTILINE 逐行找,不依赖块的边界。
        has_extras = re.search(
            r'^\s*"(\d{1,2}:\d{1,2}(?:\s+\d{1,2}:\d{1,2})*)"\s*\\?\s*$', blk, re.M)
        n = len(j.get(label, []))
        if has_extras and n <= 1:
            bad.append(f"{label}: 脚本里有 extras {has_extras.group(1)!r},却只解析出 {n} 个时刻")
    assert not bad, "🚨 解析器静默丢了 extra_times:\n  " + "\n  ".join(bad)


def test_morning_health_check_runs_after_every_morning_capture_job():
    """🚨 承重:早晨那趟体检必须晚于**所有**早晨采集作业。

    ⚠️ 分母是「早晨(≤12:00)跑的采集作业」,从脚本**推导**,不是手写名单 ——
    加一条新的早晨 cron 时这条会自动把它算进来。
    """
    j = _jobs()
    hc = [t for t in j["com.nutmeg.daily_health_check"] if t[0] < 12]
    assert len(hc) == 1, f"早晨体检不止一档:{hc} —— 本条的前提变了"
    hc_min = hc[0][0] * 60 + hc[0][1]

    late = []
    for label, times in j.items():
        if label == "com.nutmeg.daily_health_check":
            continue
        for h, mi in times:
            if h < 12 and h * 60 + mi > hc_min:
                late.append(f"{label} {h:02d}:{mi:02d}")
    assert not late, (
        f"🚨 这些早晨作业跑在体检({hc[0][0]:02d}:{hc[0][1]:02d})**之后**:{sorted(late)}\n"
        f"   ⇒ 看门狗看不到它们当天的产出,按天算陈旧的指标会假红。")


def test_evening_slot_is_untouched():
    """21:00 那档**故意保留** —— 它在傍晚批次中段,看得到当天早+午的完整数据。

    (钉住它,免得将来有人「顺手统一」把两档一起挪走。)
    """
    assert (21, 0) in _jobs()["com.nutmeg.daily_health_check"]


def test_the_reordering_is_not_vacuous():
    """⭐ 反向自检:必须真的存在「早晨采集作业」,否则上面那条恒真。

    (若哪天早晨批次全被挪走,上面那条会静默变成空断言。)
    """
    j = _jobs()
    morning = [lbl for lbl, ts in j.items()
               if lbl != "com.nutmeg.daily_health_check" and any(h < 12 for h, _ in ts)]
    assert len(morning) >= 4, (
        f"只有 {len(morning)} 个早晨作业({morning})—— 排序断言失去判别力")
