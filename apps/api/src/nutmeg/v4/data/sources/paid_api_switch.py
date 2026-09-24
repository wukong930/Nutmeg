"""付费 API 的进程级硬开关:``NUTMEG_BLOCK_PAID_APIS``(2026-09-24)。

设了它(任何非空、且不是 ``0/false/no/off`` 的值)⇒ 本进程**不许**向付费源发任何请求。
三条出口在发请求**之前**各自问它(一条腿都不能少 —— 漏一条 = 没修):

  · ``api_football._client()``
  · ``odds_api._client()``
  · ``odds_api_history.fetch_historical``(模块级 ``httpx.get``,历史端点 20 credits/次)

## 为什么测试进程里已经有闸了还要它

``tests/conftest.py`` 的出口闸是**进程内** monkeypatch,``subprocess.Popen`` 起的
子进程继承不到 —— ``test_e2e_playwright`` 的 ``server`` fixture 起的 uvicorn 里,
``_client()`` 是真的。它至今没花钱,只因为 conftest 在模块级把两个 key 置成了空串、
子进程又恰好继承了 environ:一条**写在另一个文件里的隐式副作用**,没有记账、没有测试。

实测(2026-09-24):那条副作用一旦不在(fixture 改成干净 env、或别处 pop 掉 key),
子进程会经 ``find_dotenv()`` 向上拿到主仓 ``.env`` 的真钥匙;冷缓存下**一次** dashboard
加载 = **277 次**付费请求,两次共 313(AF ``/fixtures`` 280 + OA ``sports/*/odds`` 33;
假 key + 本地桩量的,桩回空响应 ⇒ 是下界),全程 fail-soft、零红。

⇒ 开关打在**出口**上(不是逐调用点的名单),由起子进程的一方**显式**设置。

⭐ 读的是**调用时刻**的 ``os.environ``,不走 ``get_settings()``:那个有 ``lru_cache``。
   也**不** import ``nutmeg.config`` —— 那会给 ``odds_api_history`` 平添一个
   ``load_dotenv()`` 的 import 副作用(它今天没有)。
⭐ 失败方向:值写成 ``yes`` / ``true`` / ``2`` 这类一律当作**挡**。安全开关挡多了
   只是少拉一次,放错了是真钱。
"""
from __future__ import annotations

import os

ENV_VAR = "NUTMEG_BLOCK_PAID_APIS"

_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})


def paid_apis_blocked() -> bool:
    """本进程是否禁止向付费源发请求(见模块说明)。"""
    return os.environ.get(ENV_VAR, "").strip().lower() not in _OFF_VALUES
