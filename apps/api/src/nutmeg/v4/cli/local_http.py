"""探本机 daemon 用的 HTTP 打开器 —— 目标是回环地址时**永不走代理**(2026-09-25)。

## 病

`urllib.request.urlopen` 在 macOS 上除了环境变量,还会读**系统代理**(`scutil --proxy`)。
owner 的系统代理指向本机 `127.0.0.1:1082`,例外列表里有 `localhost` 却**没有**
`127.0.0.1` ⇒ `urllib.request.proxy_bypass('127.0.0.1')` 为 False ⇒ 体检探
`http://127.0.0.1:8080/...` 的请求**绕进了代理软件**(launchd 的净环境里同样如此:
它读的是系统设置,不是环境变量)。

平时代理替它转发,所以一直是绿的。2026-09-25 21:45:19 机器从睡眠里暗唤醒(DarkWake),
launchd 在 2 秒后补跑体检,代理还没醒 ⇒ `ConnectionResetError: [Errno 54]`,第 18 项红。
**断开连接的是代理,不是 daemon**(daemon 从 16:22 一直在跑、那段日志一行都没有;
重跑即绿)。

## 修

daemon 只绑 127.0.0.1,本机探针**从来不需要代理**;走代理只是多一个会坏的环节。
⇒ 目标是回环地址时用空 `ProxyHandler` 直连;不是回环地址(有人用环境变量把 URL
   改到了别处)时照旧走默认的 `urlopen` —— 不替远端目标做「禁代理」的决定。

同族但**不同**:`data_freshness._probe_get`(httpx `trust_env=False`)管的是**外网**额度
探针,那里直连优先、代理兜底 —— 外网可能真的只有代理能出去;回环地址没有兜底的理由。
"""
from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request

#: 不带任何代理的打开器(空 ProxyHandler 会盖掉环境变量与 macOS 系统代理)。
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def is_loopback(url: str) -> bool:
    """URL 的主机是不是回环地址(127.0.0.0/8、::1、localhost)。"""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def urlopen_local(req, *, timeout: float):
    """`urllib.request.urlopen` 的替身:回环地址直连,其余原样交给默认打开器。

    抛出的异常与 `urlopen` 相同(`HTTPError` / `URLError` / …)⇒ 调用方的错误分类不变。
    """
    url = req.full_url if isinstance(req, urllib.request.Request) else str(req)
    if is_loopback(url):
        return _DIRECT.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — 非回环时保持原行为
