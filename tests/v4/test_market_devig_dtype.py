"""🚨 缺列 → `pd.NA` → object dtype → `np.log` 崩掉整条训练(2026-09-11)。

## 病史

拉完赛季 `2627` 后 `test_e2e` 全红:

    TypeError: loop of ufunc does not support argument 0 of type float
                which has no callable log method

挪开 `2627/` 就绿,放回就红 —— 归因是**数据**不是代码改动。

根因链(三段,每段自己都合理):
1. football-data.co.uk 自 **2627 起把 Pinnacle(`PS*`/`PSC*`)整组列删了** —— 13/13 个 div
   全没有(2526 还全有)。⚠️ 新增的 `PP*` **不是** Pinnacle 改名:PPC 抽水中位 **6.93%**
   是全场最差,而 2526 真 PSC 是 **2.87%**。(⛔ 没按缩写猜,是量出来的。)
2. `ingest._read_europe_csv` 缺列时填 `pd.NA` ⇒ 那些帧的 `psc_*` 是 **object dtype**;
   `pd.concat` 一沾,**整列** 33k 行全变 object。
3. `_safe_devig` 直接 `1.0 / home` —— NaN-safe,但不是 dtype-safe。

⭐ 而同文件下面十行的 `_safe_devig_two_way` **一直**是 `pd.to_numeric(errors="coerce")`。
   两个孪生函数,只有没做强制的那个崩了 —— 修法是把它们对齐,不是加特例。

## 这些行值不值钱

`train.py` 的训练/验证行要求 `psc_home.notna()` ⇒ 这 503 场**一行都进不了训练**。
所以修好之后它们安静地流过去再被丢掉 —— 崩溃发生在那道过滤**之前**。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.features.market import _safe_devig, build_market_features

_COLS = ["psc_home", "psc_draw", "psc_away", "psc_over25", "psc_under25", "ahch"]


def _frame(psc: list) -> pd.DataFrame:
    n = len(psc)
    return pd.DataFrame({
        "psc_home": psc, "psc_draw": psc, "psc_away": psc,
        "psc_over25": [2.0] * n, "psc_under25": [2.0] * n, "ahch": [0.0] * n,
    })


class TestObjectDtypeDoesNotCrash:
    def test_concat_of_present_and_missing_season_is_object(self):
        """🚨 先证明**前提成立**:缺列帧 concat 之后整列真的是 object。

        没有这条,下面的断言可能在一个 float 列上空洞地通过。
        """
        have = pd.DataFrame({"psc_home": [1.9, 2.1]})
        lack = pd.DataFrame({"psc_home": [pd.NA, pd.NA]})
        assert lack["psc_home"].dtype == object
        assert pd.concat([have, lack], ignore_index=True)["psc_home"].dtype == object

    def test_build_market_features_survives_object_dtype(self):
        df = _frame([2.0, 2.0, pd.NA, pd.NA])
        assert df["psc_home"].dtype == object, "前提没成立,这条测不到东西"
        out = build_market_features(df)          # ← 修复前:TypeError
        assert out["market_logit_home"].notna().sum() == 2
        assert out["market_logit_home"].isna().sum() == 2

    def test_devig_coerces_and_keeps_the_good_rows_exact(self):
        """⭐ 强制转换不许悄悄改**好行**的数 —— 否则这是一次静默的口径变更。"""
        p_h, p_d, p_a, total = _safe_devig(*(pd.Series([2.0, 4.0]),) * 3)
        assert np.allclose(p_h, [1 / 3, 1 / 3]) and np.allclose(total, [1.5, 0.75])

    def test_garbage_string_becomes_nan_not_an_exception(self):
        p_h, *_ = _safe_devig(pd.Series(["N/A", 2.0]), pd.Series([3.0, 3.0]),
                              pd.Series([4.0, 4.0]))
        assert pd.isna(p_h.iloc[0]) and not pd.isna(p_h.iloc[1])


class TestTheRealTreeStillBuilds:
    """⚠️ 语法代理不够 —— 在**真源树**上跑一遍(它就是崩的那个输入)。"""

    def test_full_historical_tree_builds_market_features(self):
        from nutmeg.v4.cli.ingest_external import HISTORICAL_ROOT
        from nutmeg.v4.data.ingest import load_all_matches

        root = __import__("pathlib").Path(HISTORICAL_ROOT)
        if not (root / "europe").is_dir():
            pytest.skip("worktree 没有 data/ 源树")
        df = load_all_matches(root)
        # 人口非平凡:必须真的含 object 列,否则这条恒绿
        assert len(df) > 10_000, f"源树只有 {len(df)} 行,测不出 concat 效应"
        out = build_market_features(df)
        assert out["market_logit_home"].notna().sum() > 10_000

    def test_seasons_without_pinnacle_contribute_zero_train_rows(self):
        """这 503 场的**真实价值 = 0** —— 别被体检的「未吸收比赛」处方骗去重训。"""
        from nutmeg.v4.cli.ingest_external import HISTORICAL_ROOT
        from nutmeg.v4.data.ingest import load_all_matches

        root = __import__("pathlib").Path(HISTORICAL_ROOT)
        if not (root / "europe" / "2627").is_dir():
            pytest.skip("源树里没有 2627")
        df = load_all_matches(root)
        s = df[df.season == "2627"]
        assert len(s) > 0, "人口非平凡:2627 一行都没读进来"
        assert pd.to_numeric(s["psc_home"], errors="coerce").notna().sum() == 0, \
            "2627 居然有 Pinnacle 了 —— 上游改回来了?去重读这条测试的结论"
