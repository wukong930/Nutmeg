#!/usr/bin/env bash
# post-v9 P1#16 — one-shot install of the local Nutmeg data pipeline (macOS).
#
# Installs these launchd jobs into ~/Library/LaunchAgents:
#   1. com.nutmeg.api_server                  always-on daemon — FastAPI dashboard server on 127.0.0.1:8080
#   2. com.nutmeg.morning_odds                09:00 daily — V12 W0 Plan A: fetch Asian (J1) odds
#   3. com.nutmeg.morning_recommend           10:00 daily — V12 W0 Plan A: morning wave recommendations
#   4. com.nutmeg.daily_odds                  14:00 daily — V12 W0 Plan A: afternoon European wave odds
#   5. com.nutmeg.daily_recommend             15:00 daily — afternoon wave recommendations
#   6. com.nutmeg.daily_settle                02:00 daily — settle finished-match outcomes + write ROI report + rotate logs
#   7. com.nutmeg.weekly_gate                 Sunday 04:00 — P1#19 live-vs-backtest gate
#   8. com.nutmeg.weekly_calibration_check    Monday 03:00 — V10 W2 auto-T calibration drift check + rollback
#   9. com.nutmeg.daily_wc_predict            09:00 daily — V10 W4 WC predictions + record
#  10. com.nutmeg.daily_wc_settle             02:00 daily — V10 W4 WC outcome settle + report
#  11. com.nutmeg.daily_predict               15:30 daily — V12 W8j model-board prediction log + settle + accuracy report
#  12. com.nutmeg.weekly_elo_refresh          Saturday 04:30 — V14 national-team Elo snapshot refresh (eloratings.net → WC model prior)
#  13. com.nutmeg.daily_backup                03:30 daily — 体检 A2: sqlite online backup (keep 7) + WAL checkpoint
#  14. com.nutmeg.sporttery_vote              11:10/17:00/23:20 daily — 竞彩 散户支持比例 (getVoteV1 → jingcai_vote); 3 windows survive a sleeping laptop
#  15. com.nutmeg.polymarket_gaps             10:00/16:00/23:30 daily — Polymarket 错价缺口时间序列 (只读测量, record+settle); FORCES proxy (外网)
#  16. com.nutmeg.closing_odds                每 30 分 (StartInterval) — Pinnacle 收盘锚 (fetch_pinnacle_lookup → odds_snapshots source=closing); 修 ③ 锚陈旧
# (also installed, predating this header's numbering: com.nutmeg.sporttery_ingest/sporttery_open + score_ev_forward_*)
#
# All read NUTMEG_API_FOOTBALL_KEY from .env via the shell wrapper
# (no plaintext key in plists). Logs go to logs/launchd/.
#
# Usage:   ./scripts/setup_local_pipeline.sh
# Re-run:  safe to re-run **除非有 job 被有意 disable**(下方前置闸会诚实拒绝,
#          见「体检 W1 F-RERUN」注释)。
# Undo:    ./scripts/teardown_local_pipeline.sh
#
# Why launchd not crontab? macOS prefers launchd: (a) survives reboots
# automatically, (b) handles missed runs (RunAtLoad), (c) GUI-inspectable
# via Console.app, (d) per-job log files, (e) no fragile crontab format.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PLATFORM="$(uname -s)"
if [[ "$PLATFORM" != "Darwin" ]]; then
  echo "ERROR: this script only supports macOS (uname=$PLATFORM)" >&2
  echo "  For Linux: write a systemd unit or use crontab manually." >&2
  exit 1
fi

# Resolve absolute paths (launchd needs them; relative paths don't work)
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs/launchd"
DB_PATH="$REPO_ROOT/data/v4_observation.db"
PLIST_DIR="$HOME/Library/LaunchAgents"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: $VENV_PY not found or not executable" >&2
  echo "  Set up the venv first (uv pip install -e .)" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found at $REPO_ROOT/.env" >&2
  echo "  Create it with NUTMEG_API_FOOTBALL_KEY=<your-key>" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$PLIST_DIR"

# 体检 W1 2026-07-15(F-RERUN)— 「可安全重跑」在有 job 被有意 disable 时不成立:
# bootstrap 会在 disabled job 上失败中断(exit 1 卡在半程),而「先 enable 再装」
# 又会**复活被有意暂停的 cron**(odds 三件套因配额暂停,恢复只该走
# scripts/resume_odds_crons.sh + owner 口令)。所以:检测到 disabled 就诚实拒绝,
# 不猜、不硬来。
_disabled_jobs="$(launchctl print-disabled "gui/$UID" 2>/dev/null \
  | grep -E '"com\.nutmeg\.[a-z_]+" => disabled' \
  | grep -oE 'com\.nutmeg\.[a-z_]+' || true)"
if [[ -n "$_disabled_jobs" ]]; then
  echo "⛔ 以下 com.nutmeg job 处于 disabled(多半是有意暂停):" >&2
  echo "$_disabled_jobs" | sed 's/^/     /' >&2
  echo "   暂停期间禁止重跑 setup —— 会中途失败,硬修又会复活被暂停的 cron。" >&2
  echo "   恢复暂停的 odds cron:bash scripts/resume_odds_crons.sh(需 owner 口令);" >&2
  echo "   之后再跑本脚本。" >&2
  exit 1
fi

# Helper: write a single plist atomically + bootstrap it
install_job() {
  local label="$1"
  local hour="$2"
  local minute="$3"
  local weekday="$4"   # 0-6 (0=Sun); empty for "every day"
  local script="$5"
  local extra_times="${6:-}"   # optional space-separated "H:M" EXTRA daily run times.
                           # When set, StartCalendarInterval becomes an ARRAY (primary +
                           # extras) so the job has several wake-windows per day. This is
                           # what survives a sleeping laptop: launchd runs a missed
                           # calendar job once on wake, so more windows ⇒ fewer missed
                           # days. (weekday is ignored in multi-time mode.)

  local plist="$PLIST_DIR/$label.plist"
  local out_log="$LOG_DIR/$label.out.log"
  local err_log="$LOG_DIR/$label.err.log"

  # ⚠️ 命令串里的 `&&` 必须转义成 `&amp;&amp;`,否则写出的是**无效 XML**。
  # 危害不是「立刻不跑」,而是**只在下次 bootstrap 时才炸**:launchd 对已加载的
  # job 很宽容(内存里那份来自某个有效版本,照跑不误),但 `launchctl bootstrap`
  # 要解析磁盘文件 → 直接 `5: Input/output error`,job 再也装不回来。
  # 2026-07-21 恢复 3 个 odds cron 时实测撞上:23 个 plist 里 21 个无效,其中
  # 17 个还「活着」纯属侥幸。同一个坑 2026-06-23 在 sporttery_ingest 上踩过,
  # 当时只修了那一个文件、没修这个生成器 → 复发。这次修共享生成器,不逐个补文件
  # (`记忆 health-check-guardrails` 的 Altitude 条:修共享 sink,别逐生产者打补丁)。
  local script_xml="${script//&/&amp;}"

  local calendar_xml
  if [[ -n "$extra_times" ]]; then
    calendar_xml="<key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$minute</integer></dict>"
    local t h m
    for t in $extra_times; do
      h="${t%%:*}"; m="${t##*:}"
      calendar_xml="$calendar_xml
        <dict><key>Hour</key><integer>$h</integer><key>Minute</key><integer>$m</integer></dict>"
    done
    calendar_xml="$calendar_xml
    </array>"
  else
    calendar_xml="<key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$hour</integer>
        <key>Minute</key><integer>$minute</integer>"
    if [[ -n "$weekday" ]]; then
      calendar_xml="$calendar_xml
        <key>Weekday</key><integer>$weekday</integer>"
    fi
    calendar_xml="$calendar_xml
    </dict>"
  fi

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>WorkingDirectory</key>
    <string>$REPO_ROOT</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>$script_xml</string>
    </array>
    $calendar_xml
    <key>StandardOutPath</key>
    <string>$out_log</string>
    <key>StandardErrorPath</key>
    <string>$err_log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONPATH</key>
        <string>$REPO_ROOT/apps/api/src</string>
    </dict>
</dict>
</plist>
EOF

  # Bootstrap (idempotent — bootout first if loaded)
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  if launchctl bootstrap "gui/$UID" "$plist" 2>/dev/null; then
    printf "  ✓ installed %s (runs %02d:%02d%s)\n" "$label" "$hour" "$minute" \
      "$([[ -n "$weekday" ]] && echo " weekday=$weekday" || echo " daily")"
  else
    printf "  ✗ failed to bootstrap %s\n" "$label" >&2
    exit 1
  fi
}

# V12 W0 (2026-05-28) — long-running daemon variant of install_job.
# Used for the FastAPI server so the dashboard is reachable any time
# without manual `uvicorn` invocations. KeepAlive=true means launchd
# auto-restarts the process if it crashes; RunAtLoad=true means it
# starts when the user logs in (and stays up across reboots once
# bootstrap'd).
#
# Differences from install_job:
#   - No StartCalendarInterval (it's a daemon, not a cron job)
#   - KeepAlive=true (auto-restart on crash)
#   - RunAtLoad=true (start immediately + on every user login)
install_daemon() {
  local label="$1"
  local cmd="$2"

  local plist="$PLIST_DIR/$label.plist"
  local out_log="$LOG_DIR/$label.out.log"
  local err_log="$LOG_DIR/$label.err.log"
  local cmd_xml="${cmd//&/&amp;}"   # 同 install_job:`&&` 不转义 = 无效 XML

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>WorkingDirectory</key>
    <string>$REPO_ROOT</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>$cmd_xml</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$out_log</string>
    <key>StandardErrorPath</key>
    <string>$err_log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONPATH</key>
        <string>$REPO_ROOT/apps/api/src</string>
    </dict>
</dict>
</plist>
EOF

  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  if launchctl bootstrap "gui/$UID" "$plist" 2>/dev/null; then
    printf "  ✓ installed %s (daemon — RunAtLoad + KeepAlive)\n" "$label"
  else
    printf "  ✗ failed to bootstrap %s\n" "$label" >&2
    exit 1
  fi
}

# Common shell prefix for all jobs: cd + source .env so NUTMEG_API_FOOTBALL_KEY is set
ENV_PREFIX="cd $REPO_ROOT && set -a && source .env && set +a"

# V12 W0 Plan A (Option B variant) — split leagues by region so each
# wave's Pinnacle SP is captured close to that region's closing line.
#
# WHY split: morning EU SP (09:00) is ~11h pre-kickoff = early/opening line,
# far from closing. Our model was trained against closing odds, so using
# opening lines introduces systematic noise. Asian leagues (J1 weekend
# kickoffs at 12:00 CST) need a 09:00 pull to catch their closing window
# — but European leagues do NOT need to be in that pull, they're better
# served by the 14:00 cron (6h pre-kickoff = much closer to closing).
#
# Trade-off: cross-region combos (e.g., J1+EU 4-串-1) are impossible in
# any single wave under this split. User picks J1 picks in the morning,
# EU picks in the afternoon, as two separate bets. Per V12 W0 discussion
# 2026-05-28 this matches the actual user workflow.
LEAGUES_ASIAN="JPN_J1"
LEAGUES_EUROPEAN="EPL,ESP_LA_LIGA,ITA_SERIE_A,GER_BUNDESLIGA,FRA_LIGUE_1,ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,ITA_SERIE_B,GER_2_BUNDESLIGA,FRA_LIGUE_2,NED_EREDIVISIE,PRT_PRIMEIRA_LIGA,BEL_PRO_LEAGUE"

# Where Job 1 drops the daily CSV that Job 2 consumes. ``$(date +%Y-%m-%d)``
# is expanded by /bin/bash at run time (not by setup_local_pipeline.sh),
# so the plist content stays stable across days.
DAILY_DIR="$REPO_ROOT/data/daily"
mkdir -p "$DAILY_DIR"   # Job 1 / Job 2 don't bother re-creating per-run
DAILY_CSV='$REPO_ROOT/data/daily/fixtures_$(date +%Y-%m-%d).csv'   # NOT expanded here — see /bin/bash -c below
# V12 W0 Plan A — morning wave CSV (J1 + future European fixtures). The
# afternoon CSV overwrites this 4 hours later (still same day file) with
# the post-J1 European-only set.
MORNING_CSV='$REPO_ROOT/data/daily/fixtures_$(date +%Y-%m-%d)_morning.csv'
# NB: launchd plists use /bin/bash -c "<string>" so the shell will expand
# $(date ...) and $REPO_ROOT at run time. We keep DAILY_CSV single-quoted
# in setup so write_plist embeds the literal string.

echo "Installing 10 launchd jobs into $PLIST_DIR ..."

# ── V12 W0 (2026-05-28) — Always-on FastAPI server (daemon) ────────────
# Why: the dashboard needs the API server running 24/7 to load. Previously
# the server was a manually-spawned uvicorn process that died when the
# user's terminal closed / the sandbox cleaned up / the laptop slept.
# Result: "❌ 抓取盘口失败 (API 暂不可用)" because the page can't reach 8080.
#
# Now: launchd manages it. RunAtLoad=true → starts at user login.
# KeepAlive=true → auto-restart if it crashes. ThrottleInterval=10s → if
# uvicorn fails to start (e.g., port in use), launchd waits 10s before
# the next retry instead of busy-looping.
#
# Bind to 127.0.0.1:8080 (localhost only — no LAN exposure). For phone
# access, separately run: `./scripts/run_local_server.sh 8080 lan` (this
# will conflict with the daemon's port; stop the daemon first with
# `launchctl bootout gui/$UID/com.nutmeg.api_server`).
install_daemon "com.nutmeg.api_server" \
  "cd $REPO_ROOT && set -a && source .env && set +a && $VENV_PY -m uvicorn nutmeg.main:app --host 127.0.0.1 --port 8080 --app-dir $REPO_ROOT/apps/api/src"

# ── V12 W0 Plan A — Morning wave (09:00 + 10:00) ───────────────────────
# Why: J1 has weekend kickoffs at 12:00-14:00 CST. The 14:00 cron is
# already too late for those. By running the ingest at 09:00 (3+ hours
# before earliest J1 kickoff), we capture Pinnacle SP near J1's closing
# window. Job 2 (morning_recommend) at 10:00 generates Wave 1 picks.
#
# Region split (Option B — locked 2026-05-28): morning_odds pulls
# JPN_J1 ONLY, not EU. Reason: EU SP at 09:00 is ~11h pre-kickoff
# (opening line). Our model is trained against closing line, so using
# 09:00 EU SP introduces systematic noise. EU waits for the 14:00 cron
# where its SP is ~6h pre-kickoff (closer to closing).
#
# Trade-off: cross-region combos (J1+EU 4-串-1) impossible in any single
# wave. User makes J1 bets in the morning, EU bets in the afternoon.
#
# Filter: --min-kickoff-buffer-minutes 30 drops fixtures already kicked
# off OR kicking off in < 30 min. With $LEAGUES_ASIAN = "JPN_J1" the
# filter mostly catches the FT case (defensive guard if cron retries
# after kickoff).
#
# Both waves write distinct sessions to the observation DB. 推荐追溯
# surfaces both under the same date.
install_job "com.nutmeg.morning_odds" \
  9 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && mkdir -p $DAILY_DIR && $VENV_PY -m nutmeg.v4.cli.ingest_odds --leagues $LEAGUES_ASIAN --min-kickoff-buffer-minutes 30 --out $MORNING_CSV"

install_job "com.nutmeg.morning_recommend" \
  10 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && $VENV_PY -m nutmeg.v4.cli.recommend --fixtures $MORNING_CSV --record-to $DB_PATH"

# Job 1: daily odds ingest (14:00 daily) — afternoon European wave
# V12 W0 Plan A (Option B): $LEAGUES_EUROPEAN = 13 European leagues
# (top 5 + 5 second-tier + Eredivisie + Liga Portugal + Belgian Pro League).
# JPN_J1 is now handled by the 09:00 morning_odds job, NOT here.
#
# post-v9 P1#20: UCL/UEL/UECL still excluded — cup ablation closed
# negative (docs/post_v9_p1_20_cup_ablation_negative.md). Cups stay
# out of cron until / unless a separate cup model ships.
#
# CRON FIX 2026-05-26: Job 1 now writes the CSV to a dated file so
# Job 2 can find it. Previously the CSV went to stdout/log (unusable
# as input). DAILY_CSV is single-quoted at install time; /bin/bash -c
# expands $(date) + $REPO_ROOT at the 14:00 firing.
#
# V12 W0 Plan A: --min-kickoff-buffer-minutes 30 filters out fixtures
# within 30 min of kickoff (no time to act). Combined with the
# European-only league list, the 14:00 CSV is naturally clean of any
# Asian leftovers — they were already handled by the morning wave.
#
# API budget under Option B: ~22 calls/day (13 EU /fixtures + ~9 /odds).
# Plus ~1-3 calls/day for the morning J1 wave. Total still well under
# free tier's 100/day.
install_job "com.nutmeg.daily_odds" \
  14 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && mkdir -p $DAILY_DIR && $VENV_PY -m nutmeg.v4.cli.ingest_odds --leagues $LEAGUES_EUROPEAN --min-kickoff-buffer-minutes 30 --out $DAILY_CSV"

# Job 2: daily recommend + record (15:00 daily — 1h after Job 1)
# Generates recommendations using the production model (V6 W7 lineup-aware
# CatBoost since P1#18 ship), records each session into the observation
# DB. This is what populates the data we need for the 4-week lineup ROI
# verdict + Layer A T calibration.
#
# CRON FIX 2026-05-26: previously this called
#   nutmeg.v4.cli.recommend --auto-fetch --leagues ...
# which doesn't exist (recommend.py only takes --fixtures + --record-to;
# --auto-fetch lives on nutmeg-rec which itself lacks --record-to).
# Now: read the CSV Job 1 just wrote.
#
# If Job 1 failed earlier (API outage etc.), Job 2 will see "no such file"
# and exit non-zero — the err log surfaces the upstream gap clearly
# instead of producing silent bad data.
install_job "com.nutmeg.daily_recommend" \
  15 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && $VENV_PY -m nutmeg.v4.cli.recommend --fixtures $DAILY_CSV --record-to $DB_PATH"

# Job 3: daily settle (02:00 every day)
# Pulls finished-match results, settles open recommendations, refreshes the
# 4-week ROI report. (Was Sunday-only `weekly_settle`; switched to DAILY on
# 2026-05-29 for faster 推荐追溯 verification — auto_settle is cheap and only
# touches finished fixtures. Still runs at 02:00, so it lands BEFORE the Sunday
# 04:00 gate and the Monday 03:00 calibration, which read freshly-settled rows.)
#
# LOG ROTATION (2026-05-29): a trailing `; rotate_logs.sh` keeps the launchd
# logs bounded. The always-on api_server daemon logs every request, so its
# err/out log grows without limit otherwise. rotate_logs.sh copytruncates any
# log over 5000 lines down to its last 2000 (inode-preserving — safe for the
# daemon's open fd). The leading `;` (not `&&`) runs it regardless of whether
# settle/report succeeded; its own `|| true` keeps the job's exit code clean.
# --leagues auto (2026-05-30): derive the settle league set from leagues with
# unsettled recorded bets in the DB, instead of the 2-league default. Covers the
# model leagues AND 市场模式 surfaces (J1, cups) the moment a bet is recorded
# there, with zero API calls on no-pending leagues.
# --refresh-fixtures (2026-05-31): force a fresh /fixtures pull. The morning
# odds cron caches each date's fixtures while they're still NS (no result); the
# 02:00 settle would otherwise read that stale cache and see "0 finished", so a
# match settled overnight (e.g. the UCL final, decided late) stays pending. The
# extra calls are cheap (settle window is 3 days × pending leagues only).
install_job "com.nutmeg.daily_settle" \
  2 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.auto_settle --db $DB_PATH --leagues auto --refresh-fixtures && $VENV_PY -m nutmeg.v4.cli.ab_report --weeks 4 --db $DB_PATH --out $REPO_ROOT/docs/local_ab_report_latest.md || true; $VENV_PY -m nutmeg.v4.cli.jingcai_staleness --settle --db $DB_PATH > $REPO_ROOT/logs/jingcai_staleness_latest.md || true; $VENV_PY -m nutmeg.v4.cli.clv_ledger --db $DB_PATH --out '' > $REPO_ROOT/logs/clv_ledger_latest.md || true; $VENV_PY -m nutmeg.v4.cli.name_sentinel --quiet || true; $VENV_PY -m nutmeg.v4.cli.data_freshness --db $DB_PATH --out $REPO_ROOT/logs/data_freshness_latest.md >/dev/null || osascript -e 'display notification \"捕获表停长,某 cron 可能死了 — 跑 health_check\" with title \"⚠️ Nutmeg 数据漏\"' || true; $REPO_ROOT/scripts/rotate_logs.sh || true" \
  "13:00 20:00"   # 防睡眠(同 #356):02:00 睡过去 → 白天 13:00/20:00 兜底(launchd 唤醒后合并跑一次)。末尾 data_freshness 哨兵:任一 critical 捕获表停长 → 桌面弹通知(主动报警,不等你查)。

# 体检(2026-06-12)— 竞彩 SP harvest (23:15, after the ~23:00 竞彩 freeze).
# Gated on NUTMEG_SPORTTERY_ENABLED=1 (a one-line kill switch in .env). Reads the
# PUBLIC sporttery uniform endpoint (no auth/WAF) → jingcai_sp (source=sporttery,
# never clobbers a hand-priced line). --exotics also captures 比分(crs)/总进球(ttg)
# frozen SP → jingcai_exotic_sp (long-format, forward-only for the autumn soft-water
# EV test; see docs/parlay_soft_water_research.md §7). Fail-soft + low-freq (once/day).
# Pairs with the 02:00 settle to keep the 竞彩 staleness map self-populating.
install_job "com.nutmeg.sporttery_ingest" \
  23 15 "" \
  "$ENV_PREFIX && if [ \"\$NUTMEG_SPORTTERY_ENABLED\" = \"1\" ]; then $VENV_PY -m nutmeg.v4.cli.ingest_sporttery --db $DB_PATH --exotics; else echo sporttery-disabled; fi || true"

# 体检(2026-06-23)— 竞彩 开售初盘 harvest (11:05, just after the 11:00 竞彩 开售).
# Same source/gate/fail-soft as sporttery_ingest, but --phase open: stamps the 开售
# SP into jc_open_* (set-once, preserved across the 23:15 终盘 overwrite into jc_*),
# so 竞彩's own open→freeze line movement is recorded first-hand — no Okooo (which
# only re-displays the same 竞彩 SP behind anti-bot). jc_* stays the canonical 终盘.
# 2026-07-19 — extra 09:50 window: 官方 getFixedBonusV1 走势实测,竞彩每天的发布
# 都落在 09:24–09:44(北京)晨批(样本:世界杯 D−3 09:35:49 / 韩职 D−1 09:44:30 /
# 北欧 D−0 09:33:52 / WC-QF 09:24:44),而北欧等小联赛**当天早上才上架** —— 只有
# 11:05 一窗时,2026-07-18 北欧 8 场从 09:33 发布到 11:05 首捕空窗 92 分钟(owner
# 08:50 看板自然不见)。09:50 窗把同日新场的首捕/初盘拉近到发布后 ≤26 分钟;11:05
# 保留作第二遍扫尾(晚批/睡眠兜底)。phase=open 的 jc_open_* set-once ⇒ 双窗互不冲突,
# 初盘只会更贴近真开售。见 docs/jingcai_batch_opening_2026-07-18.md。
install_job "com.nutmeg.sporttery_open" \
  11 5 "" \
  "$ENV_PREFIX && if [ \"\$NUTMEG_SPORTTERY_ENABLED\" = \"1\" ]; then $VENV_PY -m nutmeg.v4.cli.ingest_sporttery --db $DB_PATH --phase open; else echo sporttery-disabled; fi || true" \
  "9:50"

# 2026-07-20 — 竞彩晚间跟盘窗(17:00–23:30 每 30 分,14 次/天)。owner 复盘发现:
# EV = P(t₁)×SP(t₂),竞彩在**临停售**最后几小时调价最凶(埃尔夫斯堡 21:51 让胜
# 1.97→1.79 急砍;库奥皮奥 20:39 后客胜才过闸),而此前 jc 价全靠 11:05/23:15 两窗
# + 手点 🎯 —— 面板拿旧价算 EV,能虚高 8pp 或整个藏掉绿灯。
# 只开晚间(白天低频窗已够),phase=close 写 jc_*(终盘口径不变,upsert-latest)。
# 封禁风险:端点公开无认证、无账号可封;涓流 cron 每小时枚举 120-170 场已数周零
# 事故,本窗只加 ~14 次/天。护栏三件:①--jitter-seconds 120 打散整点指纹
# ②sporttery.py 落盘 WAF 熔断(403/429 → 静音 6h,跨进程有效)③既有指数退避。
# 被拦时 jingcai_sp 停更 → data_freshness 哨兵响 = 响亮失败,不是静默污染。
install_job "com.nutmeg.sporttery_evening" \
  17 0 "" \
  "$ENV_PREFIX && if [ \"\$NUTMEG_SPORTTERY_ENABLED\" = \"1\" ]; then $VENV_PY -m nutmeg.v4.cli.ingest_sporttery --db $DB_PATH --phase close --refresh --jitter-seconds 120; else echo sporttery-disabled; fi || true" \
  "17:30 18:00 18:30 19:00 19:30 20:00 20:30 21:00 21:30 22:00 22:30 23:00"

# 体检(2026-06-30)— 竞彩 散户支持比例 harvest (THREE windows: 11:10 开售后 / 17:00 / 23:20 终盘后).
# Same PUBLIC uniform endpoint + same NUTMEG_SPORTTERY_ENABLED kill switch as
# sporttery_ingest, but getVoteV1 → jingcai_vote: forward-only retail 支持比例
# (h/d/a support% + 票数 + 体彩 implied/error + 竞彩 SP). FORWARD-ONLY (no history,
# current-day only) ⇒ THREE run-windows so a laptop that sleeps still lands the day —
# launchd runs a missed calendar job once on wake (same trick as daily_predict).
# Upsert-latest keyed (date,home,away,pool): each run overwrites with the freshest
# crowd snapshot, never duplicates, never clobbers a settled result. Fail-soft +
# low-freq (3×/day ≈ 6 GETs, well within polite). Feeds the autumn 散户-bias / 软水
# measurement (join supportRate → Pinnacle de-vig P + result).
install_job "com.nutmeg.sporttery_vote" \
  23 20 "" \
  "$ENV_PREFIX && if [ \"\$NUTMEG_SPORTTERY_ENABLED\" = \"1\" ]; then $VENV_PY -m nutmeg.v4.cli.ingest_jingcai_vote --db $DB_PATH; else echo sporttery-disabled; fi || true" \
  "11:10 17:0"

# 体检(2026-07-01)— Polymarket 错价缺口时间序列 (THREE windows: 10:00 / 16:00 / 23:30).
# Read-only MEASUREMENT capture — NOT betting (Polymarket is geo-blocked for CN + legal
# wall). It only banks the model/Pinnacle-vs-Polymarket gap series to cross-validate our
# own line + later study by-tier realized hit-rate. The CLI does record + settle in one
# pass; upsert-latest keyed (date,fixture,outcome), never clobbers a settled result.
# ⚠️ FOREIGN source → unreachable from CN WITHOUT the proxy (gamma/clob = 000 direct, 200
# via 127.0.0.1:1082); launchd's env is clean so the command FORCES HTTP(S)_PROXY. If the
# 科学上网 proxy is down when it fires, the CLI fail-softs to 0 rows that day. Experimental:
# off-switch = `launchctl bootout gui/<uid>/com.nutmeg.polymarket_gaps` (no .env gate).
install_job "com.nutmeg.polymarket_gaps" \
  23 30 "" \
  "$ENV_PREFIX && HTTP_PROXY=http://127.0.0.1:1082 HTTPS_PROXY=http://127.0.0.1:1082 NO_PROXY=localhost,127.0.0.1,::1 $VENV_PY -m nutmeg.v4.cli.polymarket_gaps --db $DB_PATH --days 3 || true" \
  "10:0 16:0"

# 2026-07-31 — 竞彩历史走势涓流 (getFixedBonusV1 → jingcai_odds_history)。
#
# ⚠️ **这个 job 曾经存在、被"扫完了"退休、然后静默丢了 10.5 个月数据。** 复盘:
#   · 它原本是**手装的 hourly campaign job**(StartInterval 3600),不在 setup 体系里;
#   · `jingcai_history_trickle.py` 的 END 硬编码 `dt.date(2025,7,31)` ⇒ 游标扫到那天
#     就绕回起点,**"第二轮 56 轮零新增"是必然的,不是"覆盖齐了"**;
#   · 那个假信号说服我们 2026-07-20 退休它,plist 还被移进 retired/「防重启复活」;
#   · 结果 2025-07-28→2026-06-10 的 4,751 场竞彩变盘史两边都没有,**没有任何东西会喊**
#     (日志天天绿),直到 owner 问一场具体比赛的历史 EV 才暴露。已于 2026-07-31 回填。
#
# 两处防复发:① 脚本里 END 改成 `_end_date()=今天−2`,并有测试**钉源码**禁止写回常量;
# ② 该 job 进 setup 体系(不再手装)⇒ teardown 排除表不必再收留它,setup 重跑装得回来。
#
# 从 hourly 降到**每日 2 窗**:缺口补完后它只需跟上每周新增的 7 天,而窗口就是 7 天/次
# ⇒ 一天一次即可持平,两窗是给睡眠错过留余量。中国站,ENV_PREFIX 后脚本自己清 6 个代理变量。
install_job "com.nutmeg.jingcai_history_trickle" \
  9 40 "" \
  "$ENV_PREFIX && $VENV_PY scripts/jingcai_history_trickle.py || true" \
  "21:40"

# 体检(2026-07-01)— Pinnacle 收盘锚捕获 (StartInterval 每 30 分 — 非日历,故不用 install_job).
# ③ measured the gather-side anchor was median ~5h stale (竞彩 KO in 北京深夜/凌晨);
# user now keeps the laptop 24/7-awake, so a frequent run snapshots each match's
# Pinnacle near its OWN kickoff = the true close. Bypasses the cup-market gather
# (drops most matches) by writing fetch_pinnacle_lookup straight into
# odds_snapshots(source='closing'). Odds API is CN-reachable direct (no proxy,
# unlike polymarket). The 23:20 vote backfill then co-locates the freshest line
# onto each jingcai_vote row → de-noises 软水 ②/CLV.
# 体检 Wave2 — `--sports auto`: derive the sports whose kickoff falls inside the
# next 75 min from the (cached) AF schedule and fetch ONLY those — the hardcoded
# `--sports WC` would have killed the whole closing chain when the WC ends
# (~7/19), and flat-fetching all 20+ keys 48×/day would burn Odds-API credits.
# Quiet hours = 0 credits; match windows ≈ a handful of sports per tick.
CLOSING_PLIST="$PLIST_DIR/com.nutmeg.closing_odds.plist"
# 同 install_job:命令串含 `&&`,必须转义后再插进 XML(这块是独立 heredoc,
# 不走 install_job,所以要单独转一次 —— 2026-07-21 它正是三个坏文件之一)。
CLOSING_CMD_XML="${ENV_PREFIX//&/&amp;} &amp;&amp; $VENV_PY -m nutmeg.v4.cli.closing_odds --db $DB_PATH --sports auto || true"
cat > "$CLOSING_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.nutmeg.closing_odds</string>
    <key>WorkingDirectory</key><string>$REPO_ROOT</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string><string>-c</string>
        <string>$CLOSING_CMD_XML</string>
    </array>
    <key>StartInterval</key><integer>1800</integer>
    <key>StandardOutPath</key><string>$LOG_DIR/com.nutmeg.closing_odds.out.log</string>
    <key>StandardErrorPath</key><string>$LOG_DIR/com.nutmeg.closing_odds.err.log</string>
    <key>RunAtLoad</key><false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONPATH</key><string>$REPO_ROOT/apps/api/src</string>
    </dict>
</dict>
</plist>
EOF
launchctl bootout "gui/$UID/com.nutmeg.closing_odds" 2>/dev/null || true
if launchctl bootstrap "gui/$UID" "$CLOSING_PLIST" 2>/dev/null; then
  echo "  ✓ installed com.nutmeg.closing_odds (StartInterval 每 30 分)"
else
  echo "  ✗ failed to bootstrap com.nutmeg.closing_odds" >&2
fi

# Job 4: weekly P1#19 gate (Sunday 04:00, 2h after settle)
# post-v9 P1#24: automate the P1#19 cross-source-aware gate.
# Compares live lineup-aware ROI to the P1#17 historical replay
# baseline. Uses --tolerance-pp 50 (cross-source noise floor per
# P1#22 — live cron uses API-Football odds; reference uses
# football-data.co.uk PSC; their snapshot-time differences alone
# cause 30-50pp ROI gap without any model issue).
#
# Output: docs/weekly/p1_19_gate_$(date +%G-W%V).md
# Exit code: 0 within tolerance; 2 over tolerance (logged but not
# alarmed — operator should `tail` the err log on Monday morning).
# Job 3b: 体检 A2 — nightly DB backup + WAL checkpoint (03:30, after settle).
# No .env needed (pure sqlite3). NO `|| true`: a failed backup must show as a
# nonzero exit in the err log, not vanish.
install_job "com.nutmeg.daily_backup" \
  3 30 "" \
  "$REPO_ROOT/scripts/backup_observation_db.sh"

BACKTEST_DB="$REPO_ROOT/data/v4_observation_backtest.db"
GATE_OUT_DIR="$REPO_ROOT/docs/weekly"
install_job "com.nutmeg.weekly_gate" \
  4 0 0 \
  "$ENV_PREFIX && mkdir -p $GATE_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.live_vs_backtest --db $DB_PATH --weeks 4 --live-model-arm lineup_aware --roi-backtest-db $BACKTEST_DB --roi-backtest-arm lineup_aware --tolerance-pp 50 --out $GATE_OUT_DIR/p1_19_gate_\$(date +%G-W%V).md || true"

# Job 5: V10 W2 weekly auto-T calibration check (Monday 03:00)
# Runs auto-rollback safety net FIRST: if the currently-deployed
# `live_T_correction.json` has post-deploy log-loss WORSE than identity
# by > 0.003, automatically revert (journal + delete artifact).
# Otherwise proposes a fresh T against the last 8 weeks of data and
# writes the proposal to the journal (action=propose). User reviews
# the report Monday morning and decides whether to ship via:
#   nutmeg-auto-calibration --apply --action=deploy --deploy-artifact <dir>
#
# Why Monday 03:00? Settle (Sunday 02:00) and Gate (Sunday 04:00)
# need to finish first — calibration uses the freshly-settled rows.
#
# AUDIT FIX (D1): deploy Layer A corrections to the SAME artifact dir serving
# reads — NUTMEG_V4_ARTIFACT_PATH in .env (data/v4_model_cat, the CatBoost
# model). The old value data/v4_model is the LightGBM default that serving does
# NOT load, so a correction written there was a silent no-op (it fit, gated,
# journaled, reported success — while serving applied identity T=1.0 forever).
# tests/v4/test_layer_a_deploy_path.py locks deploy-dir == serving-dir.
ARTIFACT_DIR="$REPO_ROOT/data/v4_model_cat"
CALIB_OUT_DIR="$REPO_ROOT/docs/weekly"
install_job "com.nutmeg.weekly_calibration_check" \
  3 0 1 \
  "$ENV_PREFIX && mkdir -p $CALIB_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.auto_calibration --db $DB_PATH --apply --auto-rollback --deploy-artifact $ARTIFACT_DIR --out $CALIB_OUT_DIR/auto_calibration_\$(date +%G-W%V).md || true"

# Job 6: V10 W4 WC daily predict (09:00 daily during tournament)
# Re-runs nutmeg-wc-predict for today, fetches current Pinnacle odds
# (once they open), and UPSERTS each prediction into wc_predictions
# (PK = fixture_id → idempotent on repeated runs).
# Also writes a per-day JSON report under docs/wc/.
WC_OUT_DIR="$REPO_ROOT/docs/wc"
install_job "com.nutmeg.daily_wc_predict" \
  9 0 "" \
  "$ENV_PREFIX && mkdir -p $WC_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.wc_predict --date \$(date -u +%Y-%m-%d) --fetch-current-odds --record-to $DB_PATH --out $WC_OUT_DIR/wc_\$(date -u +%Y-%m-%d).json --quiet || true"

# Job 7: V10 W4 WC daily settle (02:00 daily)
# Pulls finished WC fixtures from API-Football, fills outcome columns
# in wc_predictions. Runs BEFORE the calibration check so today's
# wc_predictions rows are settled before Layer A reads them.
# Then writes a fresh aggregate hit-rate / log-loss report.
install_job "com.nutmeg.daily_wc_settle" \
  2 0 "" \
  "$ENV_PREFIX && mkdir -p $WC_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.wc_settle --db $DB_PATH --refresh --quiet && $VENV_PY -m nutmeg.v4.cli.wc_report --db $DB_PATH --season 2026 --out $WC_OUT_DIR/wc_report_\$(date +%Y-%m-%d).md --quiet || true" \
  "13:00 20:00"   # 防睡眠(同 daily_settle/#356):单 02:00 窗口睡过去 → 白天 13:00/20:00 兜底(launchd 唤醒后合并跑一次)。--refresh 取实时结果:否则 wc_settle 读到赛前缓存(status=NS、无比分)→ 找到 0 finished → settle 0。

# Job 8: V14 weekly national-team Elo refresh (Saturday 04:30)
# The WC model's national-strength prior reads the LATEST
# data/external/eloratings/eloratings_<date>.parquet (eloratings.net, 244
# nations). Before V14 there was NO CLI/cron for this file — it was a one-off
# manual ingest that silently went stale (the only Elo CLI, ingest-national-elo,
# writes a DIFFERENT clubelo file). A weekly drop keeps the prior current through
# the tournament; load_elo_snapshot always picks the newest dated snapshot.
install_job "com.nutmeg.weekly_elo_refresh" \
  4 30 6 \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.ingest_eloratings --quiet || true"

# Job 8b: weekly CLUBELO refresh (Monday 05:00) — 2026-07-15, owner 授权改 cron
# ⚠️ 这是【俱乐部】Elo,和上面 Job 8 的【国家队】eloratings 是两套不同的源/文件:
#   · eloratings.net  → 244 国家队 → 只喂世界杯模型
#   · api.clubelo.com → ~589 欧洲俱乐部 → 喂 13 个受训联赛的生产模型
#     (40 个特征里 5 个是 clubelo_*:home/away/diff/p_home/available)
# 为什么现在才加:clubelo 从 2026-05-23 一次性手抓之后【就没有任何 cron】,两个月无人
# 更新。休赛期没比赛所以看不出来,但新赛季一开打它当天就开始烂,而且不会自愈 —— 模型
# 有 clubelo_available 标志会【静默降级】,不崩不报,所以两个月没人发现。
# 周一跑:收周末+周中的比赛结果(clubelo 只在有比赛时才变)。
# --refresh(全量重抓)敢开的前提是 clubelo.ingest_teams 里那道【防覆盖闸】:限流时
# 源返回空 body 而不报错,旧代码会把空结果写盘、冲掉好数据(335 份里 181 份变空就是
# 这么来的)。现在空结果绝不覆盖非空缓存 → 最坏只是「这周没更新」,不会毁历史。
install_job "com.nutmeg.weekly_clubelo_refresh" \
  5 0 1 \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.ingest_external --source clubelo --refresh --skip-coverage-card || true"

# Job 11: V12 W8j model-board + V14 市场模式 prediction accuracy (09:00/15:30/21:00 daily)
# Logs the 1X2 prediction for every UPCOMING match (model board for the 13 trained
# leagues + Pinnacle de-vig for cups/J1/J2/国际赛, market_mode=1), settles finished
# ones on the 90' score, then writes a hit-rate / calibration / vs-Pinnacle report.
# THREE run-times (not one): on a laptop that sleeps, launchd runs a missed calendar
# job once on wake — three windows (morning/afternoon/evening) means a sleeping Mac
# misses far fewer days. Idempotent (re-logging updates P, never clobbers an outcome).
install_job "com.nutmeg.daily_predict" \
  15 30 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.predict_log --db $DB_PATH --days 2 && mkdir -p $REPO_ROOT/docs/weekly && $VENV_PY -m nutmeg.v4.cli.predict_report --db $DB_PATH --out $REPO_ROOT/docs/weekly/predict_report_latest.md || true" \
  "9:0 21:0"

# Job 12: V12 score-EV forward test (OOS correct-score +EV validation).
# Snapshots the correct-score market + the model's +EV flags for UPCOMING
# fixtures (replacing each fixture's prior snapshot → the last pre-kickoff
# capture ≈ closing). Two record passes catch afternoon + evening kickoffs;
# settle fills the 90' result next morning. Read with: nutmeg-score-ev-forward
# --report. HONEST purpose: the backtest over-states ROI (post-match cached /
# non-closing odds + uncapturable best line); this accumulates a real OOS sample.
SEV_DB="$REPO_ROOT/data/score_ev_forward.db"
install_job "com.nutmeg.score_ev_forward_record_noon" \
  13 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.score_ev_forward --db $SEV_DB --record --max-fixtures 200 || true"
install_job "com.nutmeg.score_ev_forward_record_eve" \
  19 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.score_ev_forward --db $SEV_DB --record --max-fixtures 200 || true"
install_job "com.nutmeg.score_ev_forward_settle" \
  6 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.score_ev_forward --db $SEV_DB --settle || true"

echo ""
echo "✓ Done. Jobs are loaded. Logs:"
echo "    $LOG_DIR/com.nutmeg.api_server.{out,err}.log    ← always-on daemon"
echo "    $LOG_DIR/com.nutmeg.morning_odds.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.morning_recommend.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_odds.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_recommend.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_settle.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_gate.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_calibration_check.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_predict.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_settle.{out,err}.log"
echo ""
echo "Next:"
echo "  • Dashboard now reachable 24/7 at: http://127.0.0.1:8080/api/v4/dashboard"
echo "  • Verify with: ./scripts/health_check.sh"
echo "  • Inspect jobs: launchctl list | grep com.nutmeg"
echo "  • Stop the API server only: launchctl bootout gui/\$UID/com.nutmeg.api_server"
echo "  • Daily timeline: 02:00 settle + wc_settle → 03:00 calibration → 09:00 morning_odds + wc_predict → 10:00 morning_recommend → 14:00 daily_odds → 15:00 daily_recommend"
echo "  • Weekly gate reports land at: $GATE_OUT_DIR/p1_19_gate_<ISO-week>.md"
echo "  • Weekly calibration reports land at: $CALIB_OUT_DIR/auto_calibration_<ISO-week>.md"
echo "  • Daily WC reports land at: $WC_OUT_DIR/wc_report_<YYYY-MM-DD>.md"
echo "  • Uninstall: ./scripts/teardown_local_pipeline.sh"
