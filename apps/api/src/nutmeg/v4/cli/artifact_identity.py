"""服务盘身份闸的**判断逻辑** —— `scripts/health_check.sh` §18 的大脑。

## 为什么是一个模块而不是内嵌在 bash 里

第一版把这段判断写成 §18 里的 python heredoc。问题不是它跑不对,而是
**它没法被行为测试** —— 唯一能测的只剩「脚本源码里有没有某个字符串」,
而那正是本项目栽过三次的「语法代理测语义属性」。审查(2026-08-07)实测出
它双向失效:改个措辞就假红(且红的文案指控闸没生效,是假话)、改个段号抛
`ValueError` 而不是断言失败、多打一个空格也假红;同时**没有任何测试真的执行过
那段 bash**。

抽成模块后:判断在 Python 里被逐条行为断言(`tests/v4/test_artifact_identity_guard.py`),
bash 只剩「判词 → 严重性」的映射,那一层才用(贴着具体写法的)语法断言守。

## 两问独立,都要问

* **A. 磁盘上的配置对不对** —— 不需要 server 在跑。
* **B. 跑着的 daemon 服的对不对** —— daemon **不热载** `.env`,改完不
  `launchctl kickstart -k` 就还是旧的。「配置对」推不出「跑着的对」。

## ⛔ 判据不许退化成这两个代理

「目录存在」和 `artifact_loaded == True` —— 陈旧盘**两样都满足**,它只是错的盘。
这正是那个洞能潜伏的原因。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import NamedTuple

#: `/health` 的地址。可用 `NUTMEG_HEALTH_URL` 覆盖(测试与非默认端口用)。
DEFAULT_HEALTH_URL = "http://127.0.0.1:8080/api/v4/health"

#: 严重性。bash 侧按这四个词分派到 ok/warn/fail/note。
OK, WARN, FAIL, NOTE = "OK", "WARN", "FAIL", "NOTE"


class Row(NamedTuple):
    severity: str
    message: str


def _health_url() -> str:
    return os.environ.get("NUTMEG_HEALTH_URL") or DEFAULT_HEALTH_URL


# ------------------------------------------------------------------ A. 磁盘

def disk_rows() -> list[Row]:
    """只看磁盘配置解析成什么,不碰网络。"""
    from nutmeg.v4.api.routes import (
        EXPECTED_SERVING_ARTIFACT,
        _resolve_artifact,
        artifact_is_expected,
    )

    rows: list[Row] = []
    res = _resolve_artifact()
    if not artifact_is_expected():
        rows.append(Row(FAIL, f"配置盘 = {res.base}(来源 {res.source}),"
                              f"预期 {EXPECTED_SERVING_ARTIFACT} — 服务会喂错模型"))
    elif res.source != "env":
        rows.append(Row(WARN, f"配置盘 = {res.base} — 盘对,但 NUTMEG_V4_ARTIFACT_PATH "
                              f"没设,吃的是代码兜底值(.env 没生效?)"))
    else:
        rows.append(Row(OK, f"配置盘 = {res.base}(来源 .env,与预期一致)"))
    if res.redirected:
        rows.extend(_redirect_rows(res.base, res.path))
    return rows


def _redirect_rows(base: str, path: str) -> list[Row]:
    """Layer B 指针生效时,说清**指到哪**和**那个盘多新**。

    ⚠️ 这是身份闸唯一豁免的那条路,而 2026-08-07 的审查从这条路走了进来:
    用出厂 CLI 把 `data/v4_model_cat/live_artifact_pointer.json` 写成指向
    `data/v4_model`(2026-05-22 的旧盘),`/health` 回的是
    `artifact_is_expected: true` / `status: ok` / `detail: null`,§18 exit 0。
    `artifact_is_expected()` 判 base 是**刻意**的(指针文件就住在 base 里,
    base 对了才是指针可信的理由),所以补的不是判据而是**目标的可见性**:
    重定向到哪、目标盘的 `trained_at_utc` 是什么。

    ⭐ 目标比 base 更老 ⇒ **WARN 而不是 NOTE**。⚠️ 两者在 bash 侧**都不改退出码**
    (只有 `fail()` 设 EXIT_CODE=1),差的是**看得见的程度**:`note()` 是灰色暗字,
    整段体检里那是背景噪音;`warn()` 是黄色 ⚠。「指针把服务指回一个更旧的模型」
    不该长得像背景噪音。

    ⛔ 也不判红:部署侧现在会直接拒(`cli/auto_retrain._deploy_target_problems`),
    所以能走到这里的只剩两种人 —— 显式 `--override-identity` 的(那是**故意**的,
    判红就是假红)和手搓 JSON 的。这里是事后发现的那一半,拦截在 deploy 侧。
    """
    from nutmeg.v4.observation.auto_retrain import (
        artifact_trained_at,
        parse_trained_at,
    )

    base_raw, target_raw = artifact_trained_at(base), artifact_trained_at(path)
    shown = target_raw or "读不到 trained_at_utc(metadata.json 缺失/损坏?)"
    line = f"Layer B 指针生效: {base} -> {path}(目标 trained_at={shown})"

    base_at, target_at = parse_trained_at(base_raw), parse_trained_at(target_raw)
    if target_at is None:
        return [Row(WARN, line + " — 目标盘看不出是什么,服务可能加载失败")]
    if base_at is not None and target_at < base_at:
        return [Row(WARN, line + f" — ⚠️ 比 base 自己的 {base_raw} 更旧:"
                                 f"指针把服务指回了一个更老的模型")]
    return [Row(NOTE, line)]


# ---------------------------------------------------------------- B. daemon

def daemon_rows(url: str | None = None, timeout: float = 5.0) -> list[Row]:
    """问跑着的进程。

    ⭐ 三种失败必须**分开**报,这是 2026-08-07 审查逮到的 P0:

    * **连不上**(`URLError`:进程没起 / 端口没监听)⇒ `NOTE`。这是**真的
      「查不了」**,daemon 不在本来就没什么可判的,不该把整脚本判红。
    * **连上了但答不了**(`HTTPError` 5xx / 非 JSON / 缺字段)⇒ **`FAIL`**。
      daemon **响应了**,只是坏的 —— 比如服务目录在但 artifact 半成品,
      `/health` 直接 500。第一版把这一类也吞成 `NOTE daemon 未响应`:既**判错了**
      (它响应了),又让「跑着的 daemon 服的对不对」这半边**恰好在服务坏掉时静默跳过**,
      而 §1–§17 里没有任何一节探 daemon ⇒ 一个答不了 /health 的 daemon 全绿。
      同一条规矩在磁盘侧写的是「查不了必须红」,两边不能各一套。
    """
    from nutmeg.v4.api.routes import EXPECTED_SERVING_ARTIFACT

    target = url or _health_url()
    try:
        with urllib.request.urlopen(target, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        # 连上了、答了,但答的是错误码 ⇒ daemon 活着且坏着。必须红。
        return [Row(FAIL, f"daemon 响应了但 /health 返回 HTTP {e.code} — "
                          f"服务坏了(artifact 半成品?),身份未验证")]
    except urllib.error.URLError as e:
        # 连不上 ⇒ 真的没法判。不红,但要说清只验了磁盘。
        return [Row(NOTE, f"daemon 未监听 {target}({e.reason})— "
                          f"只验了磁盘配置,**没验跑着的进程**")]
    except Exception as e:                                   # noqa: BLE001
        return [Row(FAIL, f"探 daemon 时出乎意料地失败:{type(e).__name__}: {e}")]

    try:
        h = json.loads(body)
    except Exception:                                        # noqa: BLE001
        return [Row(FAIL, f"daemon /health 返回的不是 JSON({body[:80]!r})")]

    if "artifact_is_expected" not in h:
        return [Row(FAIL, "daemon /health 无 artifact_is_expected 字段 — 跑的是"
                          "本次改动前的旧代码,须重启 daemon 才生效")]
    if not h["artifact_is_expected"]:
        return [Row(FAIL, f"daemon 正在服 {h.get('artifact_base_path')},"
                          f"预期 {EXPECTED_SERVING_ARTIFACT} — .env 改了但 daemon 没热载? "
                          f"修: launchctl kickstart -k gui/$(id -u)/com.nutmeg.api_server")]
    rows = [Row(OK, f"daemon 正在服 {h.get('artifact_path')}"
                    f"(trained_at={h.get('trained_at_utc')}, {h.get('model_type')})")]
    # 磁盘侧的重定向注记量的是**磁盘**;daemon 有自己的 mtime 缓存,可能还没
    # 跟上。所以这条问的是跑着的进程自己怎么说 —— 用 `artifact_redirected`
    # 字段而不是拿 base/path 做字符串比较(相对 vs 绝对路径会假阳)。
    # `is True` 而不是真值判断:旧后端没这个字段,「没告诉我」不等于「重定向了」。
    if h.get("artifact_redirected") is True:
        rows.append(Row(NOTE, f"daemon 侧 Layer B 指针生效: "
                              f"{h.get('artifact_base_path')} -> {h.get('artifact_path')}"))
    return rows


# -------------------------------------------------------------------- 出口

def all_rows(url: str | None = None, timeout: float = 5.0) -> list[Row]:
    return disk_rows() + daemon_rows(url, timeout)


def main(argv: list[str] | None = None) -> int:
    """打印 `严重性\\tmessage`,每行一条;有 FAIL 则 exit 1。

    ⚠️ **先全部算完再打印**。边算边打印的话,中途抛异常会留下**半截输出**,
    而 bash 侧只看「输出是不是空」⇒ 半截会被当成完整结果,错误被 `2>/dev/null`
    吞掉 —— 又一个「分不出『没有』和『没去看』」。
    """
    # import 副作用 = load_dotenv()。按 daemon 入口(nutmeg.main)的方式先加载,
    # 否则健康的机器上也会把 source 读成 "default" —— 那量的是**我们自己的
    # import 顺序**,不是部署。
    from nutmeg.config import get_settings  # noqa: F401

    try:
        rows = all_rows()
    except Exception as e:                                   # noqa: BLE001
        rows = [Row(FAIL, f"身份闸自身抛异常,未验证:{type(e).__name__}: {e}")]

    out = "\n".join(f"{r.severity}\t{r.message}" for r in rows)
    print(out)
    return 1 if any(r.severity == FAIL for r in rows) else 0


if __name__ == "__main__":                                   # pragma: no cover
    sys.exit(main())
