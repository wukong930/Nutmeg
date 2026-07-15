"""验证窗空掉必须【硬失败】,不许静默出一个没校准的 artifact(2026-07-15)。

真实剧本(非假想):football-data 的 Pinnacle 已於 **2026-01-14** 断供,而 `train.py`
的训练/验证行都要求 `psc_home.notna()`。cutoff 一旦前移过 01-14,默认 90 天的验证窗
就整个落进无 Pinnacle 区 → `val=0`。

修之前的行为:打印「Fitting temperature calibrator on validation pool ...」→ 然后
**一声不吭**(那句 `fitted T = ...` 在 `if` 里面)→ `temperature_T=None` 的 artifact
照常出厂,**看着像成功**。而 cron 用 `--quiet` 跑(成功时不写 stdout)⇒ 光加警告是
隐形的,只能硬失败。
"""
from __future__ import annotations

import numpy as np
import pytest

from nutmeg.v4.cli.train import _MIN_VAL_FOR_TEMPERATURE, main


class TestValFloorConstant:
    def test_floor_is_the_documented_100(self):
        # 这个常数是闸门的量级;改它要连带改 train.py 里那段解释 + 本测试。
        assert _MIN_VAL_FOR_TEMPERATURE == 100


class TestEmptyValFailsLoudly:
    """用真数据跑,把 cutoff 推到 Pinnacle 断供之后 → 复现秋季那个剧本。"""

    _DATA = "data/historical_sources/football_data_co_uk"

    def _has_data(self) -> bool:
        from pathlib import Path
        return (Path(self._DATA) / "europe").is_dir()

    def test_val_window_in_the_pinnacle_dead_zone_errors(self, tmp_path, capsys):
        if not self._has_data():
            pytest.skip("需要 football-data 源树")
        # cutoff=2026-05-31 + 默认 90 天 → 验证窗 [2026-03-02, 2026-05-31) 全在
        # Pinnacle 断供区(最后一天 2026-01-14)→ val 必为 0。
        rc = main(["--data", self._DATA, "--cutoff", "2026-05-31",
                   "--validation-days", "90", "--out", str(tmp_path / "art"), "--quiet"])
        assert rc == 1, "验证窗空掉必须返回 1,不许静默成功"
        err = capsys.readouterr().err
        assert "验证集" in err and "温度无法校准" in err, "错误必须说清是【验证窗】空了"
        assert "--validation-days" in err, "错误必须给出可操作的修法"
        assert "2026-01-14" in err, "错误必须点名 Pinnacle 断供日(不然下个人还得重查一遍)"
        assert not (tmp_path / "art").exists(), "失败时不许留下半成品 artifact"

    def test_widened_val_window_succeeds(self, tmp_path):
        if not self._has_data():
            pytest.skip("需要 football-data 源树")
        # 227 天 → 窗口跨回 2025-10-16,吃到断供前的 Pinnacle → 应当成功
        rc = main(["--data", self._DATA, "--cutoff", "2026-05-31",
                   "--validation-days", "227", "--out", str(tmp_path / "ok"), "--quiet"])
        assert rc == 0
        import json
        m = json.loads((tmp_path / "ok" / "metadata.json").read_text())["metadata"]
        assert m["temperature_fitted"] is True, "窗口够宽 → 温度必须真的校准了"
        assert m["n_val"] >= _MIN_VAL_FOR_TEMPERATURE

    def test_escape_hatch_is_explicit_and_recorded(self, tmp_path):
        """--allow-uncalibrated 仍可出 artifact,但 metadata 必须如实标 False。"""
        if not self._has_data():
            pytest.skip("需要 football-data 源树")
        rc = main(["--data", self._DATA, "--cutoff", "2026-05-31",
                   "--validation-days", "90", "--allow-uncalibrated",
                   "--out", str(tmp_path / "unc"), "--quiet"])
        assert rc == 0, "显式授权时应当放行"
        import json
        m = json.loads((tmp_path / "unc" / "metadata.json").read_text())["metadata"]
        assert m["temperature_fitted"] is False, "没校准就得如实写 False,别让后人翻日志猜"


class TestTemperatureFittedFlagIsHonest:
    def test_flag_mirrors_reality_not_intent(self):
        """`temperature_fitted` 记的是【是否真的拟合了】,不是【是否想拟合】。
        纯逻辑守卫:防止后人把它接到 args 上而不是接到 temperature_T 上。"""
        import inspect

        from nutmeg.v4.cli import train
        src = inspect.getsource(train.main)
        assert '"temperature_fitted": temperature_T is not None' in src, (
            "该字段必须由 temperature_T 的真实取值决定"
        )


class TestNoRegressionInHappyPath:
    def test_probs_val_length_is_what_gates(self):
        """闸门看的是【验证预测行数】,不是 val 的原始行数(NaN 清洗后可能更少)。"""
        import inspect

        from nutmeg.v4.cli import train
        src = inspect.getsource(train.main)
        assert "len(probs_val) >= _MIN_VAL_FOR_TEMPERATURE" in src
        assert isinstance(_MIN_VAL_FOR_TEMPERATURE, int)
        assert np.isfinite(_MIN_VAL_FOR_TEMPERATURE)
