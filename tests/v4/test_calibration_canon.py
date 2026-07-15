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


class TestPolymarketOffsetCap:
    """Wave 0 回归:Polymarket 弃用深 offset 分页(offset≥2100 → 422 keyset)。

    修前:422 穿透整个 run → 已抓的页作废、零写入、exit 0 → cron 绿灯空转 4 天。
    修后:撞墙 = 视为到底(events 按 startDate 升序,深页全是远期比赛),接受已抓页。
    """

    def _events(self, pm, n):
        # 过滤器打真:这些谓词另有单测,这里只测翻页逻辑。
        return [{"id": i} for i in range(n)]

    def test_offset_cap_accepts_partial(self, monkeypatch):
        import nutmeg.v4.data.sources.polymarket as pm
        def fake_fetch(*, limit, offset, refresh):
            if offset >= 100:
                raise pm.PolymarketError(
                    '/events HTTP 422: {"error":"offset too large, use /events/keyset"}')
            return self._events(pm, limit)          # 满页 → 逼出下一页
        monkeypatch.setattr(pm, "fetch_events", fake_fetch)
        monkeypatch.setattr(pm, "_is_game_event", lambda e: True)
        monkeypatch.setattr(pm, "_in_window", lambda e, s, en: True)
        out = pm.fetch_soccer_game_events(start_date_min="2026-01-01", page_size=100)
        assert len(out) == 100, "撞 offset 墙必须接受已抓的近期页,而不是全部作废"

    def test_other_errors_still_raise(self, monkeypatch):
        import nutmeg.v4.data.sources.polymarket as pm
        def fake_fetch(*, limit, offset, refresh):
            raise pm.PolymarketError("/events HTTP 500: upstream down")
        monkeypatch.setattr(pm, "fetch_events", fake_fetch)
        with pytest.raises(pm.PolymarketError):
            pm.fetch_soccer_game_events(start_date_min="2026-01-01")
