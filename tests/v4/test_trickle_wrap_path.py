"""涓流的**绕回自愈路径** —— 直接驱动它,不再「等它自己跑到头看看」(2026-09-04)。

## 为什么不能靠等

架构靠「游标走到终点 → 绕回起点 → `skip_existing` 让上一遍失败的重来」自愈。
但 `wrapped=True` 的轮次:2026-08-24 时 **0/236**,2026-09-04 仍是 **0/258** ——
**那条路径从没在生产被观测到跑过。**

⭐ 原计划是「⏰ 约 2026-09-13 跑到头时去看它变没变 True」。那个计划本身是坏的:

1. **如果自愈是坏的,发现方式是「它静默地没自愈」** —— 而那和「还没轮到」
   长得一模一样(本仓栽过很多次的同形陷阱)。
2. **日志不一定能回答。** 2026-09-04 复查时我一度以为「2026-08-04 绕回了但标志没记上」
   —— 查下去发现 `_write_status` 是 **08-08**(`73c365e`)才引入的,而状态文件最早一行是
   **07-31**:那一段是**事后重建的**,`end` 恒为一个常量、`wrapped` 一律 false。
   ⇒ **那段日志不是观测,不能当证据。** 等下去只会再攒一堆同样说不清的行。
3. 等到那天,`end` 还在往前跑(`today − LAG_DAYS`),窗口是个移动靶。

⇒ 改成**在测试里构造 `cursor > end` 直接驱动那条分支**,今天就能答,而且以后每次改都守住。

⛔ `backfill` 必须打桩:它打真实的 sporttery(中国站),测试里绝不联网。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "scripts/jingcai_history_trickle.py"


def _load():
    spec = importlib.util.spec_from_file_location("_trickle_wrap", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def trickle(tmp_path, monkeypatch):
    """把脚本的三个外部依赖(游标 / 状态 / backfill)全部引到 tmp,并断网。"""
    mod = _load()
    monkeypatch.setattr(mod, "CURSOR", tmp_path / "cursor.txt")
    monkeypatch.setattr(mod, "STATUS", tmp_path / "status.jsonl")
    calls: list[tuple[str, str, bool]] = []

    def _fake_backfill(db, start, end, **kw):
        # ⭐ 记下**它被要求扫的窗口**和 skip_existing —— 自愈的全部内容就是这两样
        calls.append((start, end, bool(kw.get("skip_existing"))))
        return {"enumerated": 3, "in_scope": 3, "fetched": 0,
                "stored_rows": 0, "skipped": 3, "failed": 0, "failed_ids": []}

    monkeypatch.setattr(mod, "backfill", _fake_backfill)
    monkeypatch.setattr(mod, "_should_skip", lambda *a, **k: (False, "测试:不跳过"))
    mod._calls = calls
    return mod


def _rows(mod) -> list[dict]:
    p = Path(mod.STATUS)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


class TestWrapPathActuallyFires:
    """🚨 本文件的全部理由:这条路径从没在生产被观测到跑过。"""

    def test_cursor_past_end_wraps_to_begin_and_records_it(self, trickle):
        mod = trickle
        end = mod._end_date()
        # 游标越过终点 —— 这正是生产里迟早会到达、但至今没被观测到的状态
        Path(mod.CURSOR).write_text((end + dt.timedelta(days=1)).isoformat())

        assert mod.main() == 0
        rows = _rows(mod)
        assert len(rows) == 1, f"没写状态行:{rows}"
        r = rows[0]
        # ① 标志必须落盘为 True —— 「0/258 从没 True 过」就是这条在守的东西
        assert r["wrapped"] is True, f"绕回了却记成 {r['wrapped']!r} —— 探针永远看不见它"
        # ② 真的回到起点
        assert r["window_start"] == mod.BEGIN.isoformat(), r
        assert mod._calls[0][0] == mod.BEGIN.isoformat(), mod._calls
        # ③ 游标写回 BEGIN + 一个窗口
        nxt = mod.BEGIN + dt.timedelta(days=mod.WINDOW_DAYS)
        assert Path(mod.CURSOR).read_text().strip() == nxt.isoformat()

    def test_resweep_keeps_skip_existing_on(self, trickle):
        """⭐ 自愈的**便宜**全靠它:已入库的跳过,只有上一遍失败的会重来。

        关掉它 ⇒ 每次绕回都全量重抓 ⇒ 触发 sporttery 的 403 IP 封(建这个脚本的初衷)。
        """
        mod = trickle
        Path(mod.CURSOR).write_text((mod._end_date() + dt.timedelta(days=1)).isoformat())
        mod.main()
        assert mod._calls and mod._calls[0][2] is True, \
            f"re-sweep 没开 skip_existing:{mod._calls}"

    def test_a_normal_run_does_not_claim_to_have_wrapped(self, trickle):
        """⚠️ 对照:不越界时必须 False。

        没有这条,上面那条可以靠「`wrapped` 恒 True」通过 —— 那是把探针钉死在另一边。
        """
        mod = trickle
        Path(mod.CURSOR).write_text(mod.BEGIN.isoformat())
        mod.main()
        r = _rows(mod)[0]
        assert r["wrapped"] is False, r
        assert r["window_start"] == mod.BEGIN.isoformat()


class TestTheBoundaryWhereProductionWillActuallyLand:
    """⚠️ 生产不会「跳过」终点,它会**正好落在或越过**终点 —— 两种都要走通。"""

    def test_cursor_exactly_on_end_does_not_wrap_but_advances_past(self, trickle):
        """游标 == 终点:`cur > end` 为假 ⇒ 不绕回,扫一个单日窗口,然后越过终点。

        ⭐ 这一步是生产真正会走的路。若它把游标停在原地,就**永远绕不回去** ——
        而外部症状是「一直没 wrapped」,和「自愈坏了」同形。
        """
        mod = trickle
        end = mod._end_date()
        Path(mod.CURSOR).write_text(end.isoformat())
        mod.main()
        r = _rows(mod)[0]
        assert r["wrapped"] is False, r
        assert r["window_start"] == end.isoformat() and r["window_end"] == end.isoformat(), r
        nxt = dt.date.fromisoformat(Path(mod.CURSOR).read_text().strip())
        assert nxt > end, f"游标停在 {nxt},没有越过终点 ⇒ 永远绕不回去"

    def test_two_runs_from_the_boundary_reach_the_wrap(self, trickle):
        """⭐ 端到端:从「正好落在终点」出发,**第二轮**必须真的绕回。

        这是把上面两条串起来的那一步 —— 生产里 09-13 前后要发生的正是这个序列。
        """
        mod = trickle
        Path(mod.CURSOR).write_text(mod._end_date().isoformat())
        mod.main()
        mod.main()
        rows = _rows(mod)
        assert len(rows) == 2, rows
        assert [r["wrapped"] for r in rows] == [False, True], \
            f"两轮的 wrapped 序列是 {[r['wrapped'] for r in rows]},应为 [False, True]"
        assert rows[1]["window_start"] == mod.BEGIN.isoformat(), rows[1]


class TestStatusRowInvariants:
    """🚨 这些不变式在**重建出来的**那段日志里被破坏过 —— 钉住,别再让它含糊。"""

    @pytest.mark.parametrize("offset", [-30, -7, -1, 0, 1, 8])
    def test_window_end_never_exceeds_end(self, trickle, offset):
        """`window_end ≤ end`。重建的那段里出现过 `window_end 2026-08-01` / `end 2026-08-06`,
        自相矛盾 ⇒ 我无法从日志判断那次到底绕没绕回。"""
        mod = trickle
        Path(mod.CURSOR).write_text(
            (mod._end_date() + dt.timedelta(days=offset)).isoformat())
        mod.main()
        r = _rows(mod)[0]
        assert r["window_end"] <= r["end"], f"窗口越过终点:{r}"
        assert r["window_start"] <= r["window_end"], r
        assert r["begin"] <= r["window_start"], r

    @pytest.mark.parametrize("offset", [-30, -1, 0, 1])
    def test_days_remaining_matches_cursor_and_end(self, trickle, offset):
        """`days_remaining` 必须能从同一行的 `cursor_next` / `end` 推出来 ——
        它是探针算 ETA 的输入,漂了 ETA 就是编的。"""
        mod = trickle
        Path(mod.CURSOR).write_text(
            (mod._end_date() + dt.timedelta(days=offset)).isoformat())
        mod.main()
        r = _rows(mod)[0]
        want = max((dt.date.fromisoformat(r["end"])
                    - dt.date.fromisoformat(r["cursor_next"])).days, 0)
        assert r["days_remaining"] == want, r

    def test_end_in_the_status_row_is_todays_end(self, trickle):
        """⚠️ 重建的那段里 `end` 在 4 轮 / 2 天内**恒为同一个值**,而 `_end_date()`
        是 `today − LAG_DAYS` ⇒ 那不可能是当场写的。这条钉住「状态行里的 end
        就是这次运行算出来的 end」。"""
        mod = trickle
        Path(mod.CURSOR).write_text(mod.BEGIN.isoformat())
        mod.main()
        assert _rows(mod)[0]["end"] == mod._end_date().isoformat()


class TestItNeverTouchesTheNetwork:
    """⛔ 这个脚本打的是中国站 sporttery;测试里必须一次都不出网。"""

    def test_backfill_is_the_only_io_and_it_is_stubbed(self, trickle):
        mod = trickle
        Path(mod.CURSOR).write_text(mod.BEGIN.isoformat())
        mod.main()
        # 🚨 人口非平凡:先证明它**确实**调了 backfill,否则「没联网」空洞为真
        assert len(mod._calls) == 1, f"根本没调 backfill:{mod._calls}"
