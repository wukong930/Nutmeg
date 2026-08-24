"""哨兵非零退出的「报警类别」行(2026-08-24)。

## 病史

桌面推送:「⚠️ Nutmeg 数据漏 —— 捕获表停长,**某 cron 可能死了** — 跑 health_check」。
查下来**没有任何 cron 死**:26 个 job 退出码全 0、所有捕获表 0–2 天新鲜。
真凶是 `data_freshness` 的 **label_alarms**(联赛标签双轨:`日职` 被劈成
['JPN_J1','日职']、`韩国杯` 劈成 ['KOR_FA_CUP','韩国杯']、['德国杯','德超杯'] 未识别)。

⭐ **一个退出码承载五种原因**(捕获表停更 / 额度 / 模型供应链 / 联赛标签 / 涓流),
而文案只说了其中一种 ⇒ **信号为真,但它证明的不是文案声称的那个命题**,
把 owner 指向了错的地方(同 memory `first-match-is-not-the-population` 第四类)。

## 修法两半

① 报告末尾加「报警类别」行(本模块测的就是它);
② 推送文案改成**类别中立**,指向报告(`setup_local_pipeline.sh`)。
⛔ 不把类别硬编进推送 —— 那要在 plist 的一行 shell 里做命令替换,而本仓的 plist
引号转义踩过大坑(`&&` 必须写 `&amp;&amp;`,21/23 个文件曾因此是无效 XML)。
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _f(*a):
    from nutmeg.v4.cli.data_freshness import alarm_kinds_line
    return alarm_kinds_line(*a)


def test_green_emits_nothing() -> None:
    """⛔ 全绿时**一个字都不能加** —— 否则每天的报告都带一行假报警。"""
    assert _f([], [], [], [], []) == ""


def test_each_source_names_itself() -> None:
    """⭐ 承重:五个驱动源各自被点名。这就是那条推送本该说的话。"""
    want = {0: "捕获表停更", 1: "额度", 2: "模型供应链", 3: "联赛标签", 4: "涓流"}
    for i, label in want.items():
        args = [[], [], [], [], []]
        args[i] = ["x"]
        out = _f(*args)
        assert label in out, f"第 {i} 个源没被点名:{out!r}"
        others = [v for k, v in want.items() if k != i]
        assert not [o for o in others if o in out], f"点名了不该点的:{out!r}"


def test_multiple_sources_are_all_listed() -> None:
    """两个源同时响时不能只说一个 —— 那正是原推送的病。"""
    out = _f([], [], [], ["a"], ["b"])
    assert "联赛标签" in out and "涓流" in out


def test_it_says_do_not_assume_a_dead_cron() -> None:
    """⭐ 承重:这句话是本次改动的**全部要点**。

    原推送让 owner 去查 cron,而 26 个 job 全是好的。没有这句,
    下次响的时候还是会从错的地方开始查。
    """
    out = _f([], [], [], ["x"], [])
    assert "别默认是 cron 死了" in out


def test_the_push_text_no_longer_claims_a_dead_cron() -> None:
    """⛔ 承重(跨文件):推送文案必须**类别中立**。

    这条是语法断言,但它守的是一个**没有别的地方能守**的东西 ——
    plist 里那行 shell 不可能在测试里执行。它贴着具体写法,不用宽泛子串。
    """
    sh = (REPO / "scripts/setup_local_pipeline.sh").read_text(encoding="utf-8")
    assert "某 cron 可能死了" not in sh, "推送文案仍在断言 cron 死了"
    assert "data_freshness_latest.md" in sh, "推送没指向报告文件"


def test_the_two_german_cups_are_registered() -> None:
    """同批修的那两个「标签表不认识」—— 它们是这次非零退出的实际成因之一。

    ⚠️ 断言写成**行为**(classify 的返回值),不是 grep 源码里有没有那两个字符串。
    """
    from nutmeg.v4.data.league_labels import audit_label_tracks, classify_league
    for cn in ("德国杯", "德超杯"):
        assert classify_league(cn) == "excluded", f"{cn} 仍未被认识"
    a = audit_label_tracks(["德国杯", "德超杯", "日职", "韩国杯", "荷甲"])
    assert a["unknown"] == [] and a["split"] == [], f"审计仍有问题:{a}"
