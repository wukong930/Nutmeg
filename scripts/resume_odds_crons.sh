#!/usr/bin/env bash
# Resume the 3 Odds-API crons paused during a monthly quota exhaustion.
#
# Paused 2026-07-12 (owner 授权): daily_odds / morning_odds / closing_odds were
# bootout+disabled because the Odds API monthly quota ran out — they'd only spew
# fail-soft "OUT_OF_USAGE_CREDITS" warnings until the quota resets (401 doesn't
# consume, so pausing is pure noise-reduction, not a functional need).
#
# RUN THIS when the quota resets (Odds API 按月计费周年重置,非必然 1 号;
# 用 `nutmeg-data-freshness` 的配额探针或面板确认额度回来了再跑)。Idempotent.
#
# ⚠ 不跑的代价:秋天受训欧洲联赛复赛后,odds_snapshots / [closing] /
#   pinnacle_close_history 会持续空缺 = 丢失 CLV 地基与收盘锚。别忘。
set -euo pipefail
U=$(id -u)
for job in daily_odds morning_odds closing_odds; do
  label="com.nutmeg.$job"
  plist="$HOME/Library/LaunchAgents/$label.plist"
  launchctl enable "gui/$U/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$U" "$plist" 2>/dev/null || true
  echo "  ✓ resumed $label"
done
echo "--- 当前状态(应重新出现这 3 个)---"
launchctl list | grep -E "daily_odds|morning_odds|closing_odds" || echo "  (未出现 — 检查 plist 路径 / 重新登录)"
