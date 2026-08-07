"""定时体检包装器的告警判断 —— 行为断言(2026-08-07)。

## 为什么需要这个文件

`scripts/health_check_cron.sh` 是**告警路径**:它决定什么时候打断你。
这类代码最典型的坏死方式是**安静地不响** —— 而「不响」和「没事」在输出上
长得一模一样(本项目今年反复栽的形状)。所以每条分支都得真跑一遍。

## 设计前提(这些前提本身也被断言)

装它的当天 `health_check.sh` 就 exit 1(注册表硬缺口)。若按 exit code 报警,
从次日起每天一条同样的弹窗 ⇒ 三天内被关掉 ⇒ 连带服务盘告警一起失效。
所以规则是「只报新增的红」+「§18 永不被基线抑制」。

这两条各自都有可能被将来的人「简化」掉,所以都有正反两向的用例。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CRON = REPO / "scripts/health_check_cron.sh"

_S18 = "━━ 18. 服务盘一致性 (artifact identity) ━━"


def _report(*, reds: list[tuple[str, str]], include_s18: bool = True) -> str:
    """造一份体检输出。`reds` 是 (节标题, fail 判词) 对。"""
    out = []
    seen: set[str] = set()
    for sec, msg in reds:
        if sec not in seen:
            out.append(f"━━ {sec} ━━")
            seen.add(sec)
        out.append(f"  ✗ {msg}")
        # note() 行:正文里也可能出现 ✗ 字符,但它**不是**判闸结果。
        out.append("  • 细节里也有个 ✗ 但这行不该被当成红灯")
    if include_s18 and _S18 not in "\n".join(out):
        out.append(_S18)
        out.append("  ✓ 配置盘 = data/v4_model_cat")
    return "\n".join(out) + "\n"


@pytest.fixture
def env(tmp_path):
    """一套隔离的桩环境:假体检脚本 + 假通知命令 + 临时基线/报告。"""
    hc = tmp_path / "fake_health_check.sh"
    notify = tmp_path / "fake_notify.sh"
    notify.write_text('#!/usr/bin/env bash\nprintf "%s\\t%s\\n" "$1" "$2" >> "$NOTIFY_LOG"\n')
    notify.chmod(0o755)
    log = tmp_path / "notifications.txt"
    log.write_text("")

    def run(report_text: str, baseline: str, rc: int = 1) -> list[str]:
        hc.write_text("#!/usr/bin/env bash\ncat <<'EOF'\n" + report_text + f"EOF\nexit {rc}\n")
        hc.chmod(0o755)
        (tmp_path / "baseline.txt").write_text(baseline)
        log.write_text("")
        r = subprocess.run(
            ["bash", str(CRON)],
            env={**os.environ,
                 "NUTMEG_HC_SCRIPT": str(hc),
                 "NUTMEG_HC_BASELINE": str(tmp_path / "baseline.txt"),
                 "NUTMEG_HC_REPORT": str(tmp_path / "report.md"),
                 "NUTMEG_HC_NOTIFY": str(notify),
                 "NOTIFY_LOG": str(log)},
            capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, f"包装器本身不该失败:{r.stderr[:600]}"
        return [ln for ln in log.read_text().splitlines() if ln.strip()]

    return run


_KNOWN = "10. 注册表覆盖率 diff (registry-coverage) | 注册表有硬缺口 — 某切片已静默降级:"


def test_all_green_with_an_empty_baseline_is_silent(env):
    """没有红、基线也是空的 ⇒ 完全安静。

    ⚠️ 基线**非空**而这次全绿是另一回事(旧红灯消失,要响提醒你剪基线),
    见 `test_a_disappeared_red_fires_so_the_baseline_gets_pruned`。
    第一版这条把两种情形混在一起写,被脚本正确地打红了 —— 是用例的前提错了。
    """
    assert env(_report(reds=[]), "", rc=0) == []


def test_only_known_red_is_silent(env):
    """⭐ 这条是整个设计的理由:已知红不该天天打断你。"""
    got = env(_report(reds=[("10. 注册表覆盖率 diff (registry-coverage)",
                             "注册表有硬缺口 — 某切片已静默降级:")]), _KNOWN)
    assert got == [], f"已知红灯弹了通知 ⇒ 每天一条 ⇒ 三天内被你关掉:{got}"


def test_a_new_red_fires(env):
    """⭐ 主信号。基线里没有的红必须响,并且**说出是哪条**。"""
    got = env(_report(reds=[
        ("10. 注册表覆盖率 diff (registry-coverage)", "注册表有硬缺口 — 某切片已静默降级:"),
        ("9. 捕获表漏数据哨兵 (data-freshness)", "odds_snapshots 已 5 天没有新行"),
    ]), _KNOWN)
    assert len(got) == 1, got
    assert "🔴" in got[0]
    assert "odds_snapshots" in got[0], f"响了但没说是什么:{got[0]}"
    assert "注册表" not in got[0], "把已知红也塞进通知了 ⇒ 信噪比回到原点"


def test_a_disappeared_red_fires_so_the_baseline_gets_pruned(env):
    """⭐ 反向:基线里有、这次没了,也要响。

    不响的话基线会**永远**保护一个已经修好的条目 —— 同名问题复发时被静默吞掉。
    豁免清单本身也要被检查,否则就是「检查的前提没人检查」的又一个实例。
    """
    got = env(_report(reds=[]), _KNOWN, rc=0)
    assert len(got) == 1 and "🟢" in got[0], got
    assert "health_check_known_red" in got[0], "没告诉人要去哪把它删掉"


def test_artifact_identity_red_is_never_suppressed_by_the_baseline(env):
    """🚨 承重条:§18 是钱路,写进基线也照报。

    服错模型时面板一切正常、所有数字都来自另一个盘 —— 这是**唯一**不允许被
    「我知道了,别再烦我」静音的一条。
    """
    art = ("18. 服务盘一致性 (artifact identity)",
           "配置盘 = data/v4_model(来源 env),预期 data/v4_model_cat")
    baseline = _KNOWN + "\n" + f"{art[0]} | {art[1]}"      # 故意把它加进基线
    got = env(_report(reds=[art]), baseline)
    assert any("🚨" in g and "data/v4_model" in g for g in got), (
        f"§18 被基线抑制了 —— 这条豁免是整个定时体检存在的理由:{got}")


def test_missing_section_18_is_itself_an_alert(env):
    """§18 根本不在输出里 ⇒ 「§18 没红」这个观察是假的。

    体检中途退出、或有人把这一节摘掉,都会让「没红」和「没去看」长得一样。
    ⛔ 这正是本项目最贵的失败模式,所以缺席本身就要响。
    """
    got = env(_report(reds=[], include_s18=False), _KNOWN, rc=0)
    assert any("🚨" in g and "18" in g for g in got), f"§18 消失了却没人吭声:{got}"


def test_note_lines_containing_a_cross_are_not_treated_as_red(env):
    """`note()` 正文里也有 ✗ 字符,但它不是判闸结果。

    把它们算进红灯集合的话,基线会天天变 ⇒ 天天报 ⇒ 噪音。
    """
    got = env(_report(reds=[("10. 注册表覆盖率 diff (registry-coverage)",
                             "注册表有硬缺口 — 某切片已静默降级:")]), _KNOWN)
    assert got == [], f"把 note 行里的 ✗ 当成红灯了:{got}"
