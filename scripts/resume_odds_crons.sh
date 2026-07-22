#!/usr/bin/env bash
# 恢复 3 个 Odds-API cron(daily_odds / morning_odds / closing_odds)。
#
# 何时跑:配额耗尽期暂停后、额度回来时。Odds API 按**计费周年**重置(不必然 1 号);
# 先用 `nutmeg-data-freshness` 的配额探针或面板确认 x-requests-remaining > 0 再跑。
# 换新 key 也走这条路径(2026-07-22 owner 买新额度即是)。幂等,可反复跑。
#
# ⚠ 不跑的代价:欧洲联赛赛季中,odds_snapshots / [closing] / pinnacle_close_history
#   会持续空缺 = 丢失 CLV 地基与收盘锚。
#
# 踩过的两个坑(2026-07-22 —— 我**没跑本脚本**、手动绕了一大圈才发现,本脚本
# 当时其实已经是对的):
#   ① `disable` ≠ 「没装」:`bootout` 只卸载(重装即回),`launchctl disable` 会
#      写进磁盘**持久阻断** bootstrap,而两者在 `launchctl list` 里都表现为「不在」。
#      故 enable 必须在 bootstrap 之前。
#   ② plist 可能是**无效 XML** 却看着没事:launchd 对已加载 job 宽容,但 bootstrap
#      要解析磁盘文件 → `5: Input/output error`。故下面先 plutil -lint 预检并说人话。
#      生成器侧已修(setup_local_pipeline.sh 的 `&` 转义,commit 496cec0)。
set -euo pipefail
U=$(id -u)
FAILED=0

for job in daily_odds morning_odds closing_odds; do
  label="com.nutmeg.$job"
  plist="$HOME/Library/LaunchAgents/$label.plist"

  if [[ ! -f "$plist" ]]; then
    echo "  ✗ $label — plist 不存在,先跑 scripts/setup_local_pipeline.sh"
    FAILED=1; continue
  fi
  if ! plutil -lint "$plist" >/dev/null 2>&1; then
    echo "  ✗ $label — plist 是无效 XML(bootstrap 必失败),重跑 setup 重新生成"
    FAILED=1; continue
  fi

  launchctl enable "gui/$U/$label" 2>/dev/null || true   # 解除持久 disable(坑 ①)
  # 已加载时 bootstrap 会报 EALREADY —— 那是幂等成功不是失败,故**不看它的退出码**,
  # 只认下面 launchctl list 的实际状态(旧版无条件 echo "✓ resumed" 会说谎)。
  launchctl bootstrap "gui/$U" "$plist" 2>/dev/null || true

  # 用 `launchctl list <label>` 精确查询,**别 grep 全表**:2026-07-22 我先写的
  # `launchctl list | grep -qE "[[:space:]]${label}$"` 对 3 个已加载的 job 报了
  # 2 个「装载失败」—— 假阴性,和当天另外两次(cup-market 404、cron 清单误报)同源。
  # 精确查询有独立退出码,不受输出格式/分隔符影响。
  if launchctl list "$label" >/dev/null 2>&1; then
    echo "  ✓ $label 已装载"
  else
    echo "  ✗ $label 装载失败 — 查 launchctl print-disabled gui/$U | grep $job"
    FAILED=1
  fi
done

echo "--- 当前状态 ---"
launchctl list | grep -E "daily_odds|morning_odds|closing_odds" \
  || echo "  (一个都没出现 — 检查 plist 路径 / 重新登录)"

if [[ $FAILED -ne 0 ]]; then
  echo "⚠ 有 job 未恢复(见上面的 ✗)—— 别当成功,退出码 1"
  exit 1
fi
echo "✓ 3 个 odds cron 全部就位"
