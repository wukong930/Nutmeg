#!/usr/bin/env bash
# post-v9 P1#16 — local-deployment health check.
# Single command answering: "is my Nutmeg pipeline accumulating data?"
#
# Usage:  ./scripts/health_check.sh
# Exit:   0 = healthy, 1 = at least one critical check failed.
#
# Checks (printed to stdout in a friendly format):
#   1. .env present + NUTMEG_API_FOOTBALL_KEY set
#   2. launchd jobs status (loaded? last run? errors?)
#   3. Cup_odds parquet row counts (forward Path A progress)
#   4. Observation DB session/settlement counts
#   5. Lineup ROI 4-week eligibility check
#   6. Disk usage of the data tree
#
# Designed to be safe to run any time; no side effects.

set -uo pipefail

# Colors
RED=$'\033[0;31m'
YEL=$'\033[0;33m'
GRN=$'\033[0;32m'
DIM=$'\033[2m'
RST=$'\033[0m'
BOLD=$'\033[1m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_CODE=0

section() { printf "\n${BOLD}━━ %s ━━${RST}\n" "$1"; }
ok()      { printf "  ${GRN}✓${RST} %s\n" "$1"; }
warn()    { printf "  ${YEL}⚠${RST} %s\n" "$1"; }
fail()    { printf "  ${RED}✗${RST} %s\n" "$1"; EXIT_CODE=1; }
note()    { printf "  ${DIM}• %s${RST}\n" "$1"; }


# ===== 1. .env =====
section "1. API key (.env)"
if [[ -f .env ]]; then
  KEY="$(grep -E '^NUTMEG_API_FOOTBALL_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
  if [[ -n "${KEY:-}" && ${#KEY} -ge 30 ]]; then
    ok ".env present and NUTMEG_API_FOOTBALL_KEY looks valid (len=${#KEY})"
  else
    fail ".env present but NUTMEG_API_FOOTBALL_KEY missing or too short"
  fi
else
  fail ".env not found at repo root"
fi


# ===== 2. launchd jobs =====
section "2. launchd jobs"
# 体检 Wave3 (P1#14) — the job list is DERIVED from the persisted plists (the
# setup script is their only writer), never hand-copied: the old 7-name array
# silently ignored 14 of the 21 installed jobs, so a dead capture cron among
# them looked "healthy" here.
JOBS=()
for _plist in "$HOME/Library/LaunchAgents"/com.nutmeg.*.plist; do
  [[ -e "$_plist" ]] || continue
  JOBS+=("$(basename "$_plist" .plist)")
done
if [[ ${#JOBS[@]} -eq 0 ]]; then
  warn "no com.nutmeg.*.plist installed — run ./scripts/setup_local_pipeline.sh"
fi
# Snapshot launchctl list ONCE (avoid SIGPIPE issues with grep -q + pipefail
# + repeated large-output pipes that previously caused false negatives).
LIST_SNAPSHOT="$(launchctl list 2>/dev/null || true)"
ANY_LOADED=0
for job in ${JOBS[@]+"${JOBS[@]}"}; do   # ${arr[@]+...}: empty-safe under bash 3.2 set -u
  # Use grep -F (fixed-string) so the . in com.nutmeg... isn't a regex wildcard.
  line="$(printf '%s\n' "$LIST_SNAPSHOT" | grep -F "$job" || true)"
  if [[ -n "$line" ]]; then
    ANY_LOADED=1
    pid="$(printf '%s' "$line" | awk '{print $1}')"
    last_exit="$(printf '%s' "$line" | awk '{print $2}')"
    if [[ "$last_exit" == "0" || "$pid" != "-" ]]; then
      ok "$job loaded (last exit=$last_exit, pid=$pid)"
    else
      warn "$job loaded but last exit=$last_exit (non-zero, check logs)"
    fi
  else
    warn "$job not loaded (run ./scripts/setup_local_pipeline.sh)"
  fi
done
if [[ $ANY_LOADED -eq 0 ]]; then
  fail "No launchd jobs installed — data pipeline is NOT running"
fi


# ===== 3. Cup odds parquets =====
section "3. Cup odds accumulation (Path A — V10 trigger #1)"
if command -v python3 >/dev/null 2>&1 && [[ -d data/external/cup_odds ]]; then
  TOTAL_ROWS="$(.venv/bin/python -c "
import pandas as pd
from pathlib import Path
total = 0
for p in sorted(Path('data/external/cup_odds').glob('*.parquet')):
    try:
        total += len(pd.read_parquet(p))
    except Exception:
        pass
print(total)
" 2>/dev/null || echo "?")"

  N_FILES="$(find data/external/cup_odds -name '*.parquet' 2>/dev/null | wc -l | tr -d ' ')"
  note "$N_FILES parquet files in data/external/cup_odds/"
  if [[ "$TOTAL_ROWS" == "0" ]]; then
    warn "0 rows total — Path A has accumulated nothing yet"
    note "needs ≥250 rows to retry cup ablation (V10 trigger). Today: 0"
  elif [[ "$TOTAL_ROWS" -ge 250 ]]; then
    ok "$TOTAL_ROWS rows accumulated — V10 trigger #1 READY"
  else
    PCT=$(( TOTAL_ROWS * 100 / 250 ))
    note "$TOTAL_ROWS / 250 rows ($PCT% of cup-ablation trigger threshold)"
  fi
else
  warn "Could not check cup_odds (no python or directory missing)"
fi


# ===== 4. Observation DB =====
section "4. Observation DB (Lineup ROI — V10 trigger #2)"
DB="data/v4_observation.db"
if [[ -f "$DB" ]]; then
  STATS="$(.venv/bin/python -c "
import sqlite3
import sys
try:
    conn = sqlite3.connect('$DB')
    sess = conn.execute('SELECT COUNT(*) FROM recommendation_sessions').fetchone()[0]
    recs = conn.execute('SELECT COUNT(*) FROM parlay_recommendations').fetchone()[0]
    outc = conn.execute('SELECT COUNT(*) FROM match_outcomes').fetchone()[0]
    settled = conn.execute('SELECT COUNT(*) FROM settlements').fetchone()[0]
    # First + last session date for age estimation
    first_last = conn.execute(
        'SELECT MIN(created_at), MAX(created_at) FROM recommendation_sessions'
    ).fetchone()
    print(f'{sess} {recs} {outc} {settled} {first_last[0] or \"-\"} {first_last[1] or \"-\"}')
except Exception as e:
    print(f'ERROR {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)" || STATS=""

  if [[ -n "$STATS" ]]; then
    SESS="$(echo "$STATS" | awk '{print $1}')"
    RECS="$(echo "$STATS" | awk '{print $2}')"
    OUTC="$(echo "$STATS" | awk '{print $3}')"
    SETTLED="$(echo "$STATS" | awk '{print $4}')"
    FIRST="$(echo "$STATS" | awk '{print $5}')"
    LAST="$(echo "$STATS" | awk '{print $6}')"
    note "sessions: $SESS · recommendations: $RECS · outcomes: $OUTC · settled: $SETTLED"
    note "first session: $FIRST · last session: $LAST"
    if [[ "$SETTLED" -ge 60 ]]; then
      ok "$SETTLED settlements — enough to read 4-week ROI verdict"
      note "next step: PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ab_report --weeks 4 --db $DB"
    elif [[ "$SESS" -gt 0 ]]; then
      warn "$SETTLED settlements (need ≥60 for verdict; ≥30/side)"
    else
      warn "DB exists but 0 sessions — recommend step never ran"
    fi
  else
    fail "Observation DB exists but couldn't query (corrupt? schema mismatch?)"
  fi
else
  fail "$DB not found — no Lineup ROI accumulation has happened yet"
fi


# ===== 5. Disk usage =====
section "5. Disk usage"
if [[ -d data/ ]]; then
  DSIZE="$(du -sh data/ 2>/dev/null | awk '{print $1}')"
  note "data/ total: $DSIZE"
fi
if [[ -d ~/Library/Caches/ms-playwright ]]; then
  PWSIZE="$(du -sh ~/Library/Caches/ms-playwright 2>/dev/null | awk '{print $1}')"
  note "Playwright cache (~/Library/Caches/ms-playwright): $PWSIZE"
fi


# ===== 6. Name-mismatch sentinel (overlay freshness) =====
# Shows the latest AF↔Odds API team-name mismatch report. Mismatches = matches the
# fresher-line overlay silently skips → stale Pinnacle line + wrong EV on the card.
# Refresh on demand:  nutmeg-name-sentinel
section "6. Name-mismatch sentinel (Odds API overlay)"
SENTINEL_REPORT="logs/name_sentinel_latest.txt"
if [[ -f "$SENTINEL_REPORT" ]]; then
  AGE_H=$(( ( $(date +%s) - $(stat -f %m "$SENTINEL_REPORT" 2>/dev/null || echo 0) ) / 3600 ))
  SUMLINE="$(sed -n '2p' "$SENTINEL_REPORT")"
  MISS="$(printf '%s' "$SUMLINE" | sed -E 's/.*疑似错配 ([0-9]+).*/\1/')"
  if [[ "$MISS" == "0" ]]; then ok "$SUMLINE  (${AGE_H}h ago)"; else warn "$SUMLINE  (${AGE_H}h ago)"; fi
  if [[ "$MISS" != "0" ]]; then grep -E '^\s*\[' "$SENTINEL_REPORT" | head -8 | while read -r l; do note "$l"; done; fi
  [[ "$AGE_H" -ge 24 ]] && note "stale report — run: nutmeg-name-sentinel"
else
  note "no report yet — run: nutmeg-name-sentinel"
fi


# ===== 7. 竞彩 staleness map (验证 — 实战 ROI) =====
# daily_settle writes this nightly (settle + analysis). Realized 竞彩 ROI accrues
# as matches settle; the report lives in logs/ (untracked — holds personal P&L).
# Manual refresh:  nutmeg-jingcai-staleness
section "7. 竞彩 staleness map (验证)"
STALE_REPORT="logs/jingcai_staleness_latest.md"
if [[ -f "$STALE_REPORT" ]]; then
  AGE_H=$(( ( $(date +%s) - $(stat -f %m "$STALE_REPORT" 2>/dev/null || echo 0) ) / 3600 ))
  note "$(grep -m1 '已结算观测' "$STALE_REPORT" || echo '报告已生成')  (${AGE_H}h ago)"
  grep -m1 '全部候选:' "$STALE_REPORT" 2>/dev/null | sed 's/^[[:space:]]*//' | while read -r l; do note "$l"; done
else
  note "no report yet — runs nightly in daily_settle; manual: nutmeg-jingcai-staleness"
fi


# ===== 8. CLV 账本 (软水验证 — 不依赖结算) =====
# daily_settle writes this nightly. CLV (竞彩 SP vs Pinnacle 收盘) needs no result,
# so it accrues per OFFERED match (not per settled one); the 验证计数器 (selected-leg
# CLV + N toward ~15) is the soft-water edge signal. Manual:  nutmeg-clv-ledger
section "8. CLV 账本 (软水验证)"
CLV_REPORT="logs/clv_ledger_latest.md"
if [[ -f "$CLV_REPORT" ]]; then
  AGE_H=$(( ( $(date +%s) - $(stat -f %m "$CLV_REPORT" 2>/dev/null || echo 0) ) / 3600 ))
  note "$(grep -m1 '配对比赛:' "$CLV_REPORT" | sed 's/^[[:space:]]*//' || echo '报告已生成')  (${AGE_H}h ago)"
  grep -m1 '【整体】' "$CLV_REPORT" 2>/dev/null | sed 's/^[[:space:]]*//;s/  ←.*//' | while read -r l; do note "$l"; done
  grep -m1 '【验证计数器】' "$CLV_REPORT" 2>/dev/null | sed 's/^[[:space:]]*//' | while read -r l; do note "$l"; done
  grep -m1 '验证 +5%' "$CLV_REPORT" 2>/dev/null | sed 's/^[[:space:]]*//' | while read -r l; do note "$l"; done
else
  note "no report yet — runs nightly in daily_settle; manual: nutmeg-clv-ledger"
fi


# ===== 9. 捕获表漏数据哨兵 (data-freshness) =====
# 捕获型 cron (daily_odds→odds_snapshots, sporttery_ingest→jingcai_sp,
# daily_predict→league_predictions, daily_wc_predict→wc_predictions) 抓的是
# 点-in-时数据,漏一次永久没了(settle 能 --refresh 补,capture 不能)。这一节
# 对每张捕获表判"多久没长了":odds/竞彩 是 CRITICAL,停长 ⇒ ✗ fail;季节性
# (夏歇/WC 赛会) ⇒ ⚠ warn。把"几周后偶然发现 cron 死了"变成"隔天就报警"。
# 手动:  nutmeg-data-freshness   (porcelain 给脚本, 普通输出给人看)
section "9. 捕获表漏数据哨兵 (data-freshness)"
if [[ -f "$DB" ]]; then
  FRESH="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.data_freshness \
             --db "$DB" --porcelain 2>/dev/null)"
  if [[ -n "$FRESH" ]]; then
    while IFS=$'\t' read -r st tab rows last days crit note; do
      [[ -z "$tab" ]] && continue
      case "$st" in
        OK)    ok   "$tab — 最后 $last (${days}d), 共 $rows 行 · $note" ;;
        OLD)   warn "$tab 偏旧 — 最后 $last (${days}d) · $note(季节性, 非致命)" ;;
        STALE) fail "$tab 停长! 最后 $last (${days}d) · $note — 捕获 cron 可能静默死了" ;;
        # GAP 行的字段含义不同: rows=起始日 last=结束日 days=天数 (见 data_freshness
        # 的 porcelain 分支)。没有这个 case 会掉进 *) 把日期错位印出来。
        GAP)   warn "$tab 内部空洞 $rows → $last (${days} 天) — 「最后 0d」是绿的但这几天永久缺,采集补不回来" ;;
        *)     note "$tab: $st $last" ;;
      esac
    done <<< "$FRESH"
  else
    warn "data-freshness 哨兵无输出(DB query 失败? 包未安装?)"
  fi
else
  fail "$DB not found — 无捕获数据可查"
fi


# ===== 10. 注册表覆盖率 diff (registry-coverage) =====
# 体检 2026-07-03 元结论的结构性疫苗:「注册表/词典/字段清单即开关」— cron 联赛
# 在 SPORT_KEYS / AF league-id / AF 队表 / zh↔EN 字典 里缺任何一格 = 该切片
# 静默降级(韩职 sport key、德乙 14/19 队打不中 的整类)。逐格 diff LIVE AF 队表,
# 硬缺口 ⇒ ✗ fail;空队表(当季未发布)⇒ ⚠ warn。
# 手动:  nutmeg-registry-coverage [--refresh]
section "10. 注册表覆盖率 diff (registry-coverage)"
COV="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.registry_coverage --gate 2>/dev/null)"
COV_EXIT=$?
if [[ -z "$COV" ]]; then
  warn "registry-coverage 无输出(包未装? AF key 缺?)"
elif [[ $COV_EXIT -eq 0 ]]; then
  if grep -q '⚠' <<< "$COV"; then
    warn "注册表覆盖:无硬缺口,但有待发布队表 → $(grep -c '⚠' <<< "$COV") 条警告"
    grep '⚠' <<< "$COV" | while read -r l; do note "$l"; done
  else
    ok "注册表全格覆盖 (cron 联赛 × SPORT_KEYS × AF 队表 × zh 字典) 无静默降级切片"
  fi
else
  fail "注册表有硬缺口 — 某切片已静默降级:"
  grep '✗' <<< "$COV" | while read -r l; do note "$l"; done
fi


# ===== 11. 竞彩未映射队名哨兵 (sporttery zh→EN) =====
# 竞彩 SP ingest 遇到任一队名不在 zh→EN 字典就**整场丢弃**(无英文名 join 不了
# Pinnacle、算不了 EV — 丢是对的)。问题在丢得**静默**:一场从「近期赛事」消失,靠
# 人肉发现少了场(2026-07-07 欧冠资格赛 2/3 场即此)。旧代码只桌面推送(无头 launchd
# 里看不见)+ 进没人读的 out.log。现在 ingest 每次(cron 终盘/开售 + 🎯 按钮)把当日
# 未映射写到这个 latest 文件(sink 层),这里主动读出来。补别名:
# apps/api/src/nutmeg/v4/data/sources/sporttery.py 的 _ZH_OVERRIDES(对照 gather 真实拼写)。
section "11. 竞彩未映射队名哨兵 (sporttery zh→EN)"
UNMAPPED_REPORT="logs/sporttery_unmapped_latest.txt"
if [[ -f "$UNMAPPED_REPORT" ]]; then
  AGE_H=$(( ( $(date +%s) - $(stat -f %m "$UNMAPPED_REPORT" 2>/dev/null || echo 0) ) / 3600 ))
  SUMLINE="$(sed -n '2p' "$UNMAPPED_REPORT")"
  UNM="$(printf '%s' "$SUMLINE" | sed -E 's/.*未映射 ([0-9]+) 场.*/\1/')"
  if [[ "$UNM" == "0" ]]; then ok "$SUMLINE  (${AGE_H}h ago)"; else warn "$SUMLINE  (${AGE_H}h ago)"; fi
  if [[ "$UNM" != "0" ]]; then grep -E '^\s*\[' "$UNMAPPED_REPORT" | head -8 | while read -r l; do note "$l"; done; fi
  [[ "$AGE_H" -ge 26 ]] && note "报告偏旧(>26h)— 竞彩 ingest cron 可能没跑(23:15/11:05);launchctl 查它真在跑没"
else
  note "no report yet — 竞彩 ingest 跑过一次即生成: nutmeg-ingest-sporttery"
fi


# ===== 12. 新队三件套 (队名翻译 + 队徽) =====
# 一支新队要显示对,得同时命中三套互不相干的机制:① join 映射(_ZH_TO_EN)② 队名翻译
# (TEAM_NAME_ZH)③ 队徽(team_logos/<slug>.png)。2026-07-21 欧冠 Q2 奥莫尼亚一场把
# 三套全踩了一遍,花三次往返才补齐 —— 因为它们各自静默失败、且只有 ① 有哨兵。
# 本节补 ②③ 的空白;① 归第 11 节(那个哨兵早就有且是对的,别再造第二套判据)。
# 分工:第 11 节是**反应式**(竞彩已上架、场已被丢才报),本节是**预测式**(读未来赛程,
# 在竞彩上架前点名)。②③ 都不影响 EV,故只 warn 不 fail。纯离线,零 API 配额。
# 手动:  nutmeg-team-assets [--days N]
section "12. 新队三件套 (队名翻译 + 队徽)"
ASSETS="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.team_assets_check \
           --days 7 --limit 6 2>/dev/null)"
if [[ -z "$ASSETS" ]]; then
  note "team-assets 无输出(包未装?)— 手动: nutmeg-team-assets"
elif grep -q '⚠' <<< "$ASSETS"; then
  warn "$(head -1 <<< "$ASSETS")"
  grep -E '⚠|补法:' <<< "$ASSETS" | while read -r l; do note "$l"; done
  grep -E '^\s+\[' <<< "$ASSETS" | head -8 | while read -r l; do note "$l"; done
else
  ok "$(head -1 <<< "$ASSETS") — ②③ 全覆盖"
fi


# ===== 13. 配对 EV 测量 (Phase 1 — 只读研究,永不 gate) =====
# 竞彩只有 17% 的场次开单关(韩职 29%/瑞超 21%/挪超 13%;欧罗巴·芬超·欧冠·巴甲·
# 美职 0/59 全零)—— 其余 83% 必须串关,而逐腿判闸判的是一个你买不到的对象。
# 串关 EV 是乘的:两条 +3% 的腿合成 +6.09% 过闸,逐腿闸看不见。
# ⚠️ 本节**只报 N 的进度**,不是结论:预注册要求 N≥30 个投注日才看主结局
# (docs/pair_ev_prereg_2026-07-25.md §5)。它**永远不影响退出码** —— 这是研究
# 测量不是运行健康,红了也不该拦发布。手动:  nutmeg-pair-ev-ledger
section "13. 配对 EV 测量 (Phase 1 · 研究)"
PAIR="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.pair_ev_ledger \
         2>/dev/null)"
if [[ -z "$PAIR" ]]; then
  note "pair-ev 无输出(包未装?)— 手动: nutmeg-pair-ev-ledger"
else
  grep -E '^候选腿' <<< "$PAIR" | while read -r l; do note "$l"; done
  grep -E '【对照组】|【选中对】' <<< "$PAIR" | sed 's/^[[:space:]]*//' \
    | while read -r l; do note "$l"; done
  # ⚠️ 按**行首**匹配:对照组那行里也含「平均 pair_CLV」,用词匹配会把它打两遍。
  grep -E '^  (平均 pair_CLV|选中日的|两腿 CLV)' <<< "$PAIR" | sed 's/^[[:space:]]*//' \
    | while read -r l; do note "$l"; done
  # N 进度:够 30 天才提示可以读结论,否则明说还在攒
  NSEL="$(grep -oE 'N=[0-9]+ 个投注日' <<< "$PAIR" | grep -oE '[0-9]+' | head -1)"
  if [[ -n "$NSEL" && "$NSEL" -ge 30 ]]; then
    note "N=${NSEL} ≥ 30 → 可以读主结局了 (预注册 §4);确认仍需 N≥200"
  else
    note "N=${NSEL:-0}/30 投注日 — 还在攒数据,**别读结论**"
  fi
fi


# ===== 14. EV 排序力 (只读研究,永不 gate) =====
# 「EV 是排序器,还是只是排除器?」按**场**累积(每场结算的比赛都算,不管下没下注)
# ⇒ 比 ROI 尺子快一个量级:前向已 531 场 / 1,593 腿 vs 实盘 34 注。
# 主统计量 = 分档 ROI 表(model-free)。⚠️ 千万别把它拟合成一条斜率:1X2 那批实测
# 是**倒 U**(0–5% 最好、≥5% 最差),直线会把它平均成约零、报「无信号」。
# ⚠️ 它测**信息**不测**钱**:排序正确 + 12.9% vig,和「每注都亏」可以同时成立。
# 与 §13 同规矩:**永不影响退出码**。手动:  nutmeg-ev-ranking [--historical]
section "14. EV 排序力 (只读研究)"
# 不传 --out ⇒ 用默认路径写全表。本节引用了那个文件,让它总是存在;
# 只读分析写进 logs/,不碰任何库(§8 那种「cron 写、体检读」的分工在这里不适用 ——
# 接 cron 要「授权改 cron」,而这份报告本来就该随体检刷新)。
EVR="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ev_ranking \
        --db "$DB" 2>/dev/null)"
if [[ -z "$EVR" ]]; then
  note "ev-ranking 无输出(包未装?)— 手动: nutmeg-ev-ranking"
else
  # 只取「全部玩法」那一段:每玩法一张表会把体检刷屏,细节留给 logs/ 的报告
  BLOCK="$(sed -n '/^### 全部玩法/,/^### 1X2/p' <<< "$EVR")"
  grep -E '^### 全部玩法' <<< "$BLOCK" | sed 's/^### //' | while read -r l; do note "$l"; done
  grep -E '^\| (全部腿|EV )' <<< "$BLOCK" | sed 's/|/ /g;s/  */ /g;s/^ //' \
    | while read -r l; do note "$l"; done
  grep -E '^- \*\*场内对比' <<< "$BLOCK" | sed 's/^- //;s/\*\*//g' \
    | while read -r l; do note "$l"; done
  note "⚠️ 测信息不测钱;分档表别拟合斜率(1X2 是倒 U)。全表: logs/ev_ranking_latest.md"
fi


# ===== 15. 让球 δ 校准 (只读研究,永不 gate) =====
# 起因(2026-07-28):δ₋₁/δ₊₁ 上线 11 天,**没有任何东西在看着它们**,直到 owner
# 随口一问才测出 δ₊₁ 在自己的拟合人口上 log-loss 变差 −0.0111、两条被修的腿都被
# 推向错误方向。——「不被问就不会发现」正是它该变成常设仪表的理由。
# 两块:① 前向校准(裸网格 vs C1 vs 实际,按俱乐部/大赛分)② 功效(δ>2SE 需多少 N)。
# ⚠️ 与 §13/§14 同规矩:**永不影响退出码**;它也**不改任何 δ**(改预注册常数要
# owner 口令 + prereg 修订)。手动:  nutmeg-delta-calibration
section "15. 让球 δ 校准 (只读研究)"
DCAL="$(PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.delta_calibration \
         --db "$DB" 2>/dev/null)"
if [[ -z "$DCAL" ]]; then
  note "delta-calibration 无输出(包未装?)— 手动: nutmeg-delta-calibration"
else
  # log-loss 那行是「修对了吗」的一句话答案。⚠️ 配对前先剔掉「样本太小」的表头 ——
  # 它们没有 log-loss 行,留着会让 paste 把两个表头错配成一行(实测踩过)。
  grep -E '^### 让球线|^- 3-way log-loss' <<< "$DCAL" | grep -v '样本太小' \
    | sed 's/^### //;s/^- //' | paste - - 2>/dev/null | while read -r l; do note "$l"; done
  grep -E '样本太小' <<< "$DCAL" | sed 's/^### //' | while read -r l; do note "$l"; done
  # 功效表里「从未确立」的行 —— 这是要 owner 决策的清单
  grep -E '从未确立' <<< "$DCAL" | sed 's/|/ /g;s/  */ /g;s/^ //' \
    | while read -r l; do note "⚠️ $l"; done
  note "全表: logs/delta_calibration_latest.md · 本节只报不判,改 δ 须 owner + prereg"
fi


# ===== Summary =====
section "Summary"
if [[ $EXIT_CODE -eq 0 ]]; then
  printf "${GRN}${BOLD}HEALTHY${RST} — pipeline is set up and (where applicable) accumulating data.\n"
else
  printf "${RED}${BOLD}NOT HEALTHY${RST} — at least one critical check failed (see above).\n"
  printf "  ${DIM}Run ./scripts/setup_local_pipeline.sh to install the launchd jobs.${RST}\n"
fi

exit $EXIT_CODE
