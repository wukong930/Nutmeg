from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_accuracy_lab_components_are_wired() -> None:
    page = (ROOT / "apps/web/app/accuracy/page.tsx").read_text()
    selector = (
        ROOT / "apps/web/components/accuracy/model-version-selector.tsx"
    ).read_text()
    window_display = (
        ROOT / "apps/web/components/accuracy/evaluation-window-display.tsx"
    ).read_text()
    calibration_curve = (
        ROOT / "apps/web/components/accuracy/calibration-curve.tsx"
    ).read_text()
    brier_trend = (ROOT / "apps/web/components/accuracy/brier-trend.tsx").read_text()
    log_loss_trend = (
        ROOT / "apps/web/components/accuracy/log-loss-trend.tsx"
    ).read_text()

    assert "ModelVersionSelector" in page
    assert "EvaluationWindowDisplay" in page
    assert "CalibrationCurve" in page
    assert "BrierTrend" in page
    assert "LogLossTrend" in page
    assert "Model version selector" in selector
    assert "Evaluation window display" in window_display
    assert "aria-label=\"CalibrationCurve\"" in calibration_curve
    assert "aria-label=\"BrierTrend\"" in brier_trend
    assert "aria-label=\"LogLossTrend\"" in log_loss_trend


def test_accuracy_lab_query_params_drive_api_summary() -> None:
    page = (ROOT / "apps/web/app/accuracy/page.tsx").read_text()
    api = (ROOT / "apps/web/lib/api.ts").read_text()

    assert "accuracyOptionsFromParams" in page
    assert "model_version" in page
    assert "competition_id" in page
    assert "AccuracySummaryRequestOptions" in api
    assert "URLSearchParams" in api
    assert "/accuracy/summary?" in api


def test_accuracy_lab_keeps_probability_quality_copy() -> None:
    page = (ROOT / "apps/web/app/accuracy/page.tsx").read_text()
    window_display = (
        ROOT / "apps/web/components/accuracy/evaluation-window-display.tsx"
    ).read_text()
    trend_copy = (
        ROOT / "apps/web/components/accuracy/log-loss-trend.tsx"
    ).read_text()

    combined = "\n".join([page, window_display, trend_copy])

    assert "不把单场结果作为唯一判断依据" in combined
    assert "不只展示命中率" in combined
    assert "正式回测" in combined
