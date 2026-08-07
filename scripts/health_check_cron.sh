#!/usr/bin/env bash
# 定时体检包装器 —— 2026-08-07。
#
# ## 为什么不是「直接把 health_check.sh 挂上 cron + 按 exit code 弹窗」
#
# 装的当天 `health_check.sh` 就 **exit 1**,红在两个已知且非紧急的项上
# (JPN_J2 / NED_EERSTE_DIVISIE 的 sport_key 缺失 + 4 支荷乙青年队没有中文译名 ——
# 后者受「绝不照英文猜译名」红线约束,不能随手补)。按 exit code 报警的话,
# 你从第二天起每天都会收到同一条弹窗,三天内就会把它关掉 ——
# 然后真正要紧的服务盘告警也一起没了。**噪音告警等于没有告警。**
#
# ⇒ 本脚本只报**新增的红**:把当次的红灯集合和一份**已提交、可审阅**的基线
#   (`configs/health_check_known_red.txt`)比对。
#
# ## 三种通知,各自有理由
#
# * 🔴 **新增红** —— 基线里没有的红灯。这是主信号。
# * 🟢 **红灯消失** —— 基线里有、这次没了。不报的话,基线会永远保护一个**已经
#   修好的**条目,下次同名问题复发时被静默吞掉。这是「检查的前提没人检查」的
#   反向面:**豁免清单本身也要被检查**。
# * 🚨 **§18 服务盘身份** —— **永不被基线抑制**。它是钱路:服错模型时面板一切
#   正常、所有数字都来自另一个盘。这一条哪怕在基线里也照报。
#
# ## 已知的局限(写出来,不藏着)
#
# 基线的键是「节标题 + fail 判词」。§10 的判词是通用的
# (「注册表有硬缺口 — 某切片已静默降级」),所以**换一个联赛出问题、判词不变**时
# 不会新增报警。要更细就得把 `•` 明细也纳入键,但那些明细带「(1h ago)」这类
# 时间戳,会天天变 ⇒ 天天报 ⇒ 回到噪音。取舍是有意的:宁可漏报一个同类问题,
# 也不要制造一个会被关掉的告警。§18 靠上面那条豁免单独兜住。
#
# ## 可测性
#
# 判断逻辑全在这里,plist 只负责调用一次(同 §18 的做法:bash 里嵌大段逻辑
# 就只能靠「源码里有没有某个字符串」来测 = 语法代理)。三个 env 用于测试注入:
#   NUTMEG_HC_SCRIPT    体检脚本路径(默认 scripts/health_check.sh)
#   NUTMEG_HC_BASELINE  基线文件路径
#   NUTMEG_HC_NOTIFY    通知命令(默认 osascript);测试传一个记录到文件的桩
#
# Exit: 恒为 0 —— 通知才是信号,不靠 launchd 的退出码。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HC="${NUTMEG_HC_SCRIPT:-$REPO_ROOT/scripts/health_check.sh}"
BASELINE="${NUTMEG_HC_BASELINE:-$REPO_ROOT/configs/health_check_known_red.txt}"
REPORT="${NUTMEG_HC_REPORT:-$REPO_ROOT/logs/health_check_latest.md}"

notify() {   # $1=标题 $2=正文
  if [[ -n "${NUTMEG_HC_NOTIFY:-}" ]]; then
    "$NUTMEG_HC_NOTIFY" "$1" "$2"
  else
    # 正文里的双引号会破坏 osascript 的字符串 —— 先换成单引号。
    local body="${2//\"/\'}"
    osascript -e "display notification \"${body}\" with title \"$1\"" >/dev/null 2>&1
  fi
}

#: 机器可读的判定,给面板读(`/observation/health-check-latest`)。
#: ⚠️ **不要让后端去解析上面那份中文报告** —— 那是给人看的散文,解析它就是又一个
#: 「语法代理测语义属性」:改个措辞前端就瞎,而且瞎的时候看起来一切正常。
JSON="${NUTMEG_HC_JSON:-${REPORT%.md}.json}"

emit_json() {   # $1=ok(true/false) $2=detail(可空) $3=exit_code
  # 用 python 写,不手拼 JSON:判词里有中文、引号、`|`,bash 转义迟早出错。
  NUT_OK="$1" NUT_DETAIL="$2" NUT_RC="$3" \
  NUT_REDS="${CUR:-}" NUT_NEW="${NEW:-}" NUT_GONE="${GONE:-}" \
  /usr/bin/env python3 - "$JSON" <<'PY' 2>/dev/null || true
import json, os, sys, datetime
def lines(k):
    return [x for x in (os.environ.get(k) or "").splitlines() if x.strip()]
json.dump({
    "ran_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "ok": os.environ["NUT_OK"] == "true",
    "detail": os.environ.get("NUT_DETAIL") or None,
    "exit_code": int(os.environ.get("NUT_RC") or 0),
    "reds": lines("NUT_REDS"), "new": lines("NUT_NEW"), "gone": lines("NUT_GONE"),
}, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
PY
}

mkdir -p "$(dirname "$REPORT")"
"$HC" > "$REPORT" 2>&1
HC_RC=$?

# 去 ANSI → 抽出「节标题 | fail 判词」。
# ⚠️ 只认 `fail()` 的输出格式(行首两空格 + ✗ + 空格)。正文里也会出现 ✗ 字符
# (note() 打的 `• ... ✗ ...`),那些**不是**判闸结果,混进来会让基线天天变。
CUR="$(sed 's/\x1b\[[0-9;]*m//g' "$REPORT" | awk '
  /^━━ / { sec = $0; gsub(/^━━ +| +━━$/, "", sec); next }
  /^  ✗ / { msg = $0; sub(/^  ✗ +/, "", msg); print sec " | " msg }
' | sort -u)"

# §18 必须存在。它不在输出里 = 被从体检里摘掉了(或脚本报错提前退出),
# 那么「§18 没红」这个观察就是假的 —— 分不出「没红」和「没去看」。
if ! sed 's/\x1b\[[0-9;]*m//g' "$REPORT" | grep -q "artifact identity"; then
  notify "🚨 Nutmeg 体检异常" "§18 服务盘一致性不在体检输出里 —— 被摘掉了?体检可能中途退出。看 $REPORT"
  # ⚠️ 这条早退路径**也要**写 JSON。不写的话面板会读到**上一次**那份(内容是绿的、
  # 时间戳是旧的)—— 而「上次绿」和「这次没跑完」在面板上长得一模一样。
  emit_json false "§18 服务盘一致性不在体检输出里 —— 体检可能中途退出" "$HC_RC"
  exit 0
fi

BASE="$(sort -u "$BASELINE" 2>/dev/null | grep -v '^\s*#' | grep -v '^\s*$' || true)"
NEW="$(comm -23 <(printf '%s\n' "$CUR" | grep -v '^$' || true) <(printf '%s\n' "$BASE" | grep -v '^$' || true))"
GONE="$(comm -13 <(printf '%s\n' "$CUR" | grep -v '^$' || true) <(printf '%s\n' "$BASE" | grep -v '^$' || true))"
# §18 的红永不被基线抑制。
ART="$(printf '%s\n' "$CUR" | grep "artifact identity" || true)"

{
  echo
  echo "─── 定时体检判定 ($(date '+%Y-%m-%d %H:%M')) ───"
  echo "health_check exit = $HC_RC"
  echo "本次红灯:"; printf '%s\n' "${CUR:-  (无)}" | sed 's/^/  /'
  echo "新增:"; printf '%s\n' "${NEW:-  (无)}" | sed 's/^/  /'
  echo "消失:"; printf '%s\n' "${GONE:-  (无)}" | sed 's/^/  /'
} >> "$REPORT"

if [[ -n "$ART" ]]; then
  notify "🚨 Nutmeg 服务盘不对" "$(printf '%s' "$ART" | head -1) — 面板可能一切正常但数字来自另一个模型。跑 scripts/health_check.sh 看 §18"
fi
if [[ -n "$NEW" ]]; then
  notify "🔴 Nutmeg 体检新增红灯" "$(printf '%s' "$NEW" | head -3 | tr '\n' ';') — 详见 $REPORT"
fi
emit_json true "" "$HC_RC"

if [[ -n "$GONE" ]]; then
  notify "🟢 Nutmeg 体检:旧红灯消失" "$(printf '%s' "$GONE" | head -3 | tr '\n' ';') — 请从 configs/health_check_known_red.txt 删掉,否则它会永远保护一个已修好的条目"
fi
exit 0
