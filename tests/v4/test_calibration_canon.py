"""口径正典锁 + Wave 0 回归(2026-07-15 第三次体检,owner 拍板 D2/D3)。

D3【温度口径】:artifact 的温度 T 只在【评估】(walk_forward/bench 卡)应用以保
跨模型可比;**服务端吐裸 DC 网格 P**,唯一运行时校准 = Layer A 的
live_T_correction.json。谁要改这个口径,先来改本文件 + train.py 的正典注释。

D2【默认 artifact】:recommend 家族 CLI 默认 = 生产盘 data/v4_model_cat。
lineups 盘冻结在 cutoff 2024-08-01(未随 07-15 解冻重训)且服务时 lineup 特征
恒 0(lookup 从不传入)→ 它不是真·lineup 臂;roi_backtest 是显式 A/B 工具,豁免。
关键:morning/daily_recommend 两个 cron 不传 --model,吃的就是这些默认值 ——
改默认 = 改 cron 行为(这正是本修复的目的,也是本锁存在的原因)。
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest


class TestD3TemperatureCanon:
    def test_routes_only_echoes_temperature(self):
        """routes 里 temperature_T 的每次出现都必须是 ModelInfo 回显。

        机械锁:出现次数 == 回显模式次数 × 2(kwarg 行 `temperature_T=art.temperature_T`
        左右各含一次)。谁在服务端把 T 乘进概率,等式立刻破 → 强迫先改正典再改代码。
        """
        import nutmeg.v4.api.routes as routes
        src = inspect.getsource(routes)
        total = src.count("temperature_T")
        echoes = src.count("temperature_T=art.temperature_T")
        assert echoes >= 4, "ModelInfo 回显至少 4 处(现状基线)"
        assert total == echoes * 2, (
            f"routes 出现 {total} 次 temperature_T,回显只解释 {echoes * 2} 次 —— "
            "有人在服务端应用了温度?改口径请先改本测试 + train.py 正典注释"
        )

    def test_eval_applies_temperature_serving_does_not(self):
        import nutmeg.v4.eval.walk_forward as wf
        import nutmeg.v4.model.persist as persist
        assert "fit_temperature_1x2" in inspect.getsource(wf), "评估侧应用 T(跨模型可比)"
        psrc = inspect.getsource(persist.predict_lambdas)
        assert "temperature" not in psrc.lower(), "预测路径不许掺温度(正典=裸 grid P)"


class TestD2RecommendDefaults:
    def test_recommend_family_defaults_to_production_artifact(self):
        import nutmeg.v4.cli.rec as rec
        import nutmeg.v4.cli.recommend as recommend
        import nutmeg.v4.cli.recommend_pool as pool
        for mod in (recommend, rec, pool):
            src = inspect.getsource(mod)
            assert "data/v4_model_cat_lineups" not in src, (
                f"{mod.__name__} 不许再默认冻结的 lineups 盘(体检 D2)"
            )
            assert "data/v4_model_cat" in src

    def test_roi_backtest_keeps_explicit_lineup_arm(self):
        # 显式 A/B 工具豁免:两臂对比正是它的用途,别被 D2 顺手「修」掉。
        import nutmeg.v4.cli.roi_backtest as rb
        assert "data/v4_model_cat_lineups" in inspect.getsource(rb)

    def test_run_local_server_fallback_is_production(self):
        sh = Path("scripts/run_local_server.sh").read_text()
        assert "data/v4_model_cat_lineups" not in sh
        assert "data/v4_model_cat}" in sh, "兜底必须指生产盘"


class TestPolymarketPaginationCanon:
    """Polymarket 分页正典 —— **2026-09-01 推翻了 Wave 0 的结论,连同它的测试**。

    ## 病史两层

    **Wave 0(2026-07-15)**:offset≥2100 → 422 穿透整个 run ⇒ 已抓页作废、零写入、
    exit 0 ⇒ cron 绿灯空转 4 天。当时的修法是**接住 422、接受已抓到的页**,
    理由写作「events 按 startDate 升序,深页全是远期比赛 ⇒ 撞墙=到底了」。

    **2026-09-01**:那句理由是**假的**。升序 + `closed=false` ⇒ **浅页是最老的、
    还没关闭的市场**,它们只增不减;实测墙内 **95.6% 是已开球的比赛**(889 个开球在
    30 天前以上),今天的比赛被挤到墙**后面**。⇒ 每轮只捞 ~20 个赛事(峰值 344),
    抓取量塌 10 倍,而 Wave 0 的修法恰好**把唯一的告警也拿掉了** ⇒ 塌了 10 天没人知道。

    ⭐ 通用教训:**把「炸给你看」改成「安静少给你」之前,先问谁来告诉我它降级了。**
    (配套新增了 `data_freshness.check_volume_cliff` 这条独立判据。)

    ⇒ 正典现在是 **/events/keyset + after_cursor + start_time_min/max**,
    ⛔ **不许再出现 offset 分页**。分页细节的测试在
    `test_polymarket_keyset_pagination.py`;本类只钉「正典是什么」。
    """

    def test_offset_pagination_is_gone(self, monkeypatch):
        """⛔ 承重:发出去的 HTTP query 里**不许有 offset**,端点必须是 keyset。

        退回 offset 就是退回那堵墙 —— 而墙后面正是我们要的数据。
        """
        import nutmeg.v4.data.sources.polymarket as pm
        seen = {}

        def _req(base, endpoint, params=None, **kw):
            seen["endpoint"] = endpoint
            seen["params"] = dict(params or {})
            return {"events": [], "next_cursor": None}

        monkeypatch.setattr(pm, "_request", _req)
        pm.fetch_soccer_game_events(start_date_min="2026-01-01", end_date="2026-01-03")
        assert seen["endpoint"] == "/events/keyset", seen["endpoint"]
        assert "offset" not in seen["params"], seen["params"]
        assert "start_time_min" in seen["params"], seen["params"]

    def test_other_errors_still_raise(self, monkeypatch):
        """上游 500 仍须穿透 —— ⛔ 别再把异常吞成「安静少给你」。"""
        import nutmeg.v4.data.sources.polymarket as pm

        def _boom(**kw):
            raise pm.PolymarketError("/events/keyset HTTP 500: upstream down")

        monkeypatch.setattr(pm, "fetch_events_keyset", _boom)
        with pytest.raises(pm.PolymarketError):
            pm.fetch_soccer_game_events(start_date_min="2026-01-01")
