#!/usr/bin/env bash
# post-v9 P1#16 — uninstall the launchd jobs installed by setup_local_pipeline.sh
# V10 W2 Day 4 — added com.nutmeg.weekly_calibration_check
#
# Usage:  ./scripts/teardown_local_pipeline.sh
#
# Safe to run if jobs were never installed (bootout errors silently swallowed).
# Does NOT delete logs/launchd/ — preserves history for forensics.

set -euo pipefail

PLIST_DIR="$HOME/Library/LaunchAgents"
# 体检 Wave3 (P1#14) — the job list is DERIVED from the persisted plists, never
# hand-copied: the old 11-name array had drifted from the 21 installed jobs.
# ⚠️ 体检 W1 2026-07-15 — 「setup 是 com.nutmeg.* 唯一 writer」已失真:存在
# 手工装的短期 campaign job(下方排除表)。glob = 安装集 − 排除集。
#
# 排除表:游离于 setup/teardown 体系的 job。teardown 删了它们 setup 装不回
# (= 回填永久中断);campaign 抓完自会 bootout。往这里加名字,别改 glob。
# ⚠️ 2026-07-31 更正 —— 上面那条 2026-07-20 的「已退休」结论是**错的,而且是被
# 一个 bug 制造出来的**。原文写的是「第二轮 56 轮零新增 = 枚举出的每场都已入库
# 8,163 场」。真相:`jingcai_history_trickle.py` 的 END 硬编码 `dt.date(2025,7,31)`,
# 游标扫到那天就绕回起点 ⇒ **"零新增"是数学上必然的**,它永远不会去看那天之后的
# 日期。我们据此关掉了它,还把 plist 移进 retired/「防重启复活」。
# 代价:2025-07-28→2026-06-10 的 **4,751 场 / 47,229 行**竞彩变盘史两边都没有,
# 而且没有任何东西会喊(日志天天绿),直到 owner 问一场具体比赛的历史 EV 才暴露。
#
# ⭐ 教训:**「零新增」只能证明"扫描范围内没有新东西",不能证明"范围是对的"。**
# 一个自称扫完了的任务,先查它的边界是不是常量。
#
# 现状:已回填;涓流改为**日历 job 进 setup 体系**(不再手装 campaign job),
# END 动态跟今天、联赛取全部;`tests/v4/test_jingcai_history_trickle.py` 钉源码。
# ⇒ 它现在归 setup/teardown 管,**不在排除表里**,teardown 删了 setup 装得回来。
#
# 排除表机制保留 —— 下个真·短期 campaign job 往这里加名字即可。
TEARDOWN_EXCLUDE=()
JOBS=()
for _plist in "$PLIST_DIR"/com.nutmeg.*.plist; do
  [[ -e "$_plist" ]] || continue
  _label="$(basename "$_plist" .plist)"
  for _ex in "${TEARDOWN_EXCLUDE[@]}"; do
    if [[ "$_label" == "$_ex" ]]; then
      echo "  ⏭  跳过 campaign job $_label(不属 setup 体系,teardown 不碰)"
      _label=""
      break
    fi
  done
  [[ -n "$_label" ]] && JOBS+=("$_label")
done
# Legacy label that may be loaded WITHOUT a persisted plist (renamed →
# daily_settle 2026-05-29); boot out the leftover if present.
JOBS+=("com.nutmeg.weekly_settle")

echo "Uninstalling launchd jobs ..."
for job in "${JOBS[@]}"; do
  if launchctl bootout "gui/$UID/$job" 2>/dev/null; then
    echo "  ✓ booted out $job"
  else
    echo "  • $job not currently loaded (skipping bootout)"
  fi
  plist="$PLIST_DIR/$job.plist"
  if [[ -f "$plist" ]]; then
    rm "$plist"
    echo "  ✓ removed $plist"
  fi
done

echo ""
echo "Done. Logs preserved at logs/launchd/ (delete manually if you don't need them)."
echo "Re-install: ./scripts/setup_local_pipeline.sh"
