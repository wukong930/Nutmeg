"""总进球校准层的护栏(2026-09-22)。

⭐ 本文件存在的理由:当前 artifact 世代数据不够,**今天拟合不出真系数**。
   那就必须独立证明「拟合器本身是好的」——否则这层是纸糊的,等数据攒够那天
   没人会回头验它。核心是 `TestTheFitterActuallyWorks`:用已知 c 造数据,看它认不认得出来。
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from nutmeg.v4.model.dixon_coles import score_grid
from nutmeg.v4.observation import goals_calibration as gc


def _pair(date: str, lh: float, la: float, total: int) -> gc.GoalsPair:
    return gc.GoalsPair(date, "EPL", "H", "A", lh, la, total)


class TestPmfShape:
    def test_pmf_sums_to_one_because_the_last_bucket_is_open(self):
        # ⚠️ 尾巴被截掉会**静默**让 log-loss 变好看 —— 所以专挑高 λ 打
        for lh, la in [(0.3, 0.2), (1.5, 1.2), (3.4, 3.1), (5.0, 4.5)]:
            pmf = gc.total_goals_pmf(lh, la)
            assert pmf.sum() == pytest.approx(1.0, abs=1e-9), f"λ=({lh},{la})"
            assert len(pmf) == gc.N_BUCKETS == 8

    def test_c_equals_one_is_the_identity(self):
        # c=1 必须和「根本没有这层」逐格相同,否则部署它本身就改了盘面
        lh, la = 1.42, 1.13
        g = score_grid(lh, la, rho=-0.10)
        direct = np.zeros(8)
        for i in range(g.shape[0]):
            for j in range(g.shape[0]):
                direct[min(i + j, 7)] += g[i, j]
        assert gc.total_goals_pmf(lh, la, c=1.0) == pytest.approx(direct / direct.sum(), abs=1e-12)

    def test_c_above_one_moves_mass_to_more_goals(self):
        lo, hi = gc.total_goals_pmf(1.4, 1.2, c=1.0), gc.total_goals_pmf(1.4, 1.2, c=1.15)
        e = lambda p: float(sum(k * v for k, v in enumerate(p)))
        assert e(hi) > e(lo)
        assert hi[0] < lo[0]          # 0 球变少

    def test_rho_cannot_move_the_over_two_five_line(self):
        """DC 的 τ 只改 (0,0)(0,1)(1,0)(1,1) 四格 ⇒ 总进球 ≥3 的质量与 rho 无关。

        ⭐ 这条是我 09-22 那份实测的**数学前提**,必须钉住 —— 否则「偏差与 rho 无关」
           这个结论哪天悄悄失效都没人知道。
        """
        base = None
        for rho in (-0.20, -0.10, 0.0, 0.10):
            over25 = float(gc.total_goals_pmf(1.5, 1.3, rho=rho)[3:].sum())
            if base is None:
                base = over25
            else:
                assert over25 == pytest.approx(base, abs=1e-12), f"rho={rho} 动了大2.5"
        # 反面:2.5 以下的线**应该**被 rho 影响,否则上面那条是因为函数根本没读 rho
        u15 = [float(gc.total_goals_pmf(1.5, 1.3, rho=r)[:2].sum()) for r in (-0.20, 0.10)]
        assert u15[0] != pytest.approx(u15[1], abs=1e-9), "rho 完全没进计算 ⇒ 上一条是假绿"


class TestTheFitterActuallyWorks:
    """⭐ 今天拟不出真系数,所以必须证明拟合器认得出**已知**的 c。"""

    def test_it_recovers_a_planted_coefficient(self):
        rng = np.random.default_rng(7)
        c_true = 1.12
        pairs = []
        for i in range(4000):
            lh = float(rng.uniform(0.7, 2.2))
            la = float(rng.uniform(0.5, 1.8))
            # 真实进球按 c_true 缩放后的 λ 生成
            tot = int(rng.poisson(lh * c_true) + rng.poisson(la * c_true))
            pairs.append(_pair("2026-09-01", lh, la, tot))
        c_hat = gc.fit_goals_scale(pairs)
        assert abs(c_hat - c_true) < 0.03, f"拟合出 {c_hat:.4f},真值 {c_true}"

    def test_it_returns_one_when_there_is_no_bias(self):
        rng = np.random.default_rng(11)
        pairs = []
        for _ in range(4000):
            lh, la = float(rng.uniform(0.7, 2.2)), float(rng.uniform(0.5, 1.8))
            pairs.append(_pair("2026-09-01", lh, la, int(rng.poisson(lh) + rng.poisson(la))))
        assert abs(gc.fit_goals_scale(pairs) - 1.0) < 0.03

    def test_log_loss_is_actually_minimised_at_the_fitted_c(self):
        rng = np.random.default_rng(13)
        pairs = [_pair("2026-09-01", lh := float(rng.uniform(0.8, 2.0)),
                       la := float(rng.uniform(0.6, 1.6)),
                       int(rng.poisson(lh * 1.10) + rng.poisson(la * 1.10)))
                 for _ in range(1500)]
        c_hat = gc.fit_goals_scale(pairs)
        best = gc.log_loss_totals(pairs, c_hat)
        for d in (-0.05, -0.02, 0.02, 0.05):
            assert gc.log_loss_totals(pairs, c_hat + d) >= best - 1e-9


class TestSplitIsByTime:
    def test_no_match_date_straddles_both_sides(self):
        pairs = [_pair(f"2026-09-{d:02d}", 1.3, 1.1, 2) for d in range(1, 29) for _ in range(3)]
        tr, ho = gc.split_train_holdout(pairs, holdout_weeks=2)
        assert tr and ho
        assert not ({p.match_date for p in tr} & {p.match_date for p in ho}), "同一比赛日横跨两边"
        assert max(p.match_date for p in tr) < min(p.match_date for p in ho)


def _seed_db(path, rows):
    """rows: (created_at, model_type, lh, la, hg, ag)"""
    from nutmeg.v4.observation.store import init_db
    init_db(path)
    c = sqlite3.connect(path)
    for i, (created, mt, lh, la, hg, ag) in enumerate(rows):
        sid = i + 1   # session_id 是 INTEGER PRIMARY KEY
        c.execute("INSERT INTO recommendation_sessions (session_id, created_at, model_type,"
                  " bankroll, n_fixtures, n_recommendations, request_json)"
                  " VALUES (?,?,?,?,?,?,?)", (sid, created, mt, 1000.0, 1, 0, "{}"))
        c.execute("INSERT INTO single_predictions (session_id, match_date, league, home_team,"
                  " away_team, lambda_home, lambda_away, p_home_1x2, p_draw_1x2, p_away_1x2)"
                  " VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (sid, "2026-09-16", "EPL", f"H{i}", f"A{i}", lh, la, .4, .3, .3))
        c.execute("INSERT INTO match_outcomes (match_date, league, home_team, away_team,"
                  " home_goals, away_goals, recorded_at) VALUES (?,?,?,?,?,?,?)",
                  ("2026-09-16", "EPL", f"H{i}", f"A{i}", hg, ag, created))
    c.commit(); c.close()


class TestPopulationIsAnAllowlist:
    ERA = "2026-09-16T00:00:00"

    def test_hand_typed_rows_are_dropped_and_they_really_are_in_the_db(self, tmp_path):
        """⚠️ 人口非平凡断言:先证明毒行**确实在库里**,再证明它被丢掉。

        (⛔ 不用 `lambda_home > 0` 当代理 —— 生产库里 `user_directional_combo`
         的手填行带着正的 λ,这条已被实测证伪。)
        """
        db = str(tmp_path / "o.db")
        _seed_db(db, [("2026-09-17T10:00:00", "catboost", 1.4, 1.1, 2, 1),
                      ("2026-09-17T10:00:00", "catboost", 1.2, 1.3, 0, 0),
                      ("2026-09-17T10:00:00", "user_directional_combo", 1.31, 1.89, 3, 2)])
        raw = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM recommendation_sessions WHERE model_type='user_directional_combo'"
        ).fetchone()[0]
        assert raw == 1, "毒行没进库 ⇒ 下面那条断言是空包弹"
        got = gc.load_goals_pairs(db, era_start=self.ERA)
        assert len(got) == 2
        assert all(round(p.lambda_home, 2) != 1.31 for p in got)

    def test_a_null_model_type_is_dropped_not_admitted(self, tmp_path):
        """⛔ 和 Layer A 的差别是**故意**的:这里不放行 NULL。

        Layer A 放行 NULL 有据(pre-P1#17 老 session),但本模块只看 09-15 之后的
        世代,实测全库 0 行 NULL ⇒ 放行它纯属 fail-OPEN。
        """
        db = str(tmp_path / "o.db")
        _seed_db(db, [("2026-09-17T10:00:00", "catboost", 1.4, 1.1, 2, 1),
                      ("2026-09-17T10:00:00", None, 1.5, 1.2, 1, 1)])
        assert sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM recommendation_sessions WHERE model_type IS NULL"
        ).fetchone()[0] == 1, "NULL 行没进库 ⇒ 空包弹"
        assert len(gc.load_goals_pairs(db, era_start=self.ERA)) == 1

    def test_rows_before_the_era_start_are_dropped(self, tmp_path):
        db = str(tmp_path / "o.db")
        _seed_db(db, [("2026-09-14T10:00:00", "catboost", 1.4, 1.1, 2, 1),
                      ("2026-09-17T10:00:00", "catboost", 1.2, 1.3, 0, 0)])
        assert len(gc.load_goals_pairs(db, era_start=self.ERA)) == 1

    def test_null_lambda_rows_are_dropped(self, tmp_path):
        """schema v3 起,市场模式/手填行的 λ 是 NULL(不是哨兵 0.0)。"""
        db = str(tmp_path / "o.db")
        _seed_db(db, [("2026-09-17T10:00:00", "catboost", 1.4, 1.1, 2, 1),
                      ("2026-09-17T10:00:00", "catboost", None, None, 1, 1)])
        assert len(gc.load_goals_pairs(db, era_start=self.ERA)) == 1


class TestTheGateRefusesToWiden:
    def test_insufficient_training_data_does_not_silently_widen_the_window(self, tmp_path):
        """⭐ 预注册第 5 条。今天(2026-09-22)生产库走的就是这条路径。"""
        db = str(tmp_path / "o.db")
        _seed_db(db, [("2026-09-17T10:00:00", "catboost", 1.4, 1.1, 2, 1)] * 5)
        p = gc.propose_goals_correction(db)
        assert p.decision == "insufficient"
        assert p.proposed_c == 1.0, "样本不足时必须退回恒等,⛔ 不做部分部署"
        assert p.n_train < gc.DEFAULT_MIN_SAMPLES


class TestEveryConstructionSiteIsWired:
    """⭐ 不写死「有 3 个构造点」—— 测试自己去源码里数([[hardcoded-guard-lists-rot]])。

    未来有人加第 5 个 `SinglePrediction(...)` 而忘了带进球分布,卡片会**静默**少一块。
    这条护栏用 AST 判,不用 grep([[skip-guard-that-cannot-skip]]:判别器要 AST)。
    """

    @staticmethod
    def _sites():
        import ast
        from pathlib import Path
        src = Path("apps/api/src/nutmeg/v4/api/routes.py")
        tree = ast.parse(src.read_text(encoding="utf-8"))
        out = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "SinglePrediction"):
                kw = {k.arg for k in node.keywords}
                has_view = any(
                    k.arg is None and isinstance(k.value, ast.BoolOp)
                    and any(isinstance(v, ast.Call) and getattr(v.func, "id", "") == "goals_view"
                            for v in ast.walk(k.value))
                    for k in node.keywords)
                # λ 是写死的 0.0 ⇒ 市场模式,本来就不该有分布
                lam = next((k.value for k in node.keywords if k.arg == "lambda_home"), None)
                zero = isinstance(lam, ast.Constant) and lam.value == 0.0
                out.append((node.lineno, has_view, zero, kw))
        return out

    def test_the_ast_probe_finds_a_nontrivial_population(self):
        sites = self._sites()
        assert len(sites) >= 3, f"只找到 {len(sites)} 个构造点 ⇒ 探针坏了,下面是空包弹"
        # 探针自检:它必须能分辨两类。两类都得有,否则它可能只是恒真/恒假。
        assert any(h for _, h, _, _ in sites), "没有任何一个点带 goals_view ⇒ 探针识别不出"
        assert any(z for _, _, z, _ in sites), "没有任何一个点是 λ=0 ⇒ 探针识别不出市场模式"

    def test_every_site_either_sends_the_distribution_or_has_no_lambda(self):
        bad = [(ln, sorted(kw)[:6]) for ln, has, zero, kw in self._sites() if not has and not zero]
        assert not bad, (
            "这些 SinglePrediction(...) 既没传 goals_view 也不是 λ=0 的市场模式 ⇒ "
            f"卡片会静默少一块进球分布: {bad}")
