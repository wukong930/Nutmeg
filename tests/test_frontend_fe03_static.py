from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_match_detail_mvp_components_are_wired() -> None:
    fixture_page = (ROOT / "apps/web/app/fixtures/[fixtureId]/page.tsx").read_text()
    match_header = (ROOT / "apps/web/components/match/match-header.tsx").read_text()
    prediction_trace = (ROOT / "apps/web/components/prediction/prediction-trace.tsx").read_text()
    model_fingerprint = (ROOT / "apps/web/components/model/model-fingerprint.tsx").read_text()
    top_scores = (ROOT / "apps/web/components/score/score-top-list.tsx").read_text()

    assert "MatchHeader" in fixture_page
    assert "ProbabilityTriptych" in fixture_page
    assert "PredictionTrace" in fixture_page
    assert "TopScoresPanel" in fixture_page
    assert "ModelFingerprint" in fixture_page
    assert "不代表确定赛果" in match_header
    assert "Data Snapshot" in prediction_trace
    assert "Market Resolver" in prediction_trace
    assert "Calibration" in model_fingerprint
    assert "比分概率是底层模型输出" in top_scores


def test_match_detail_keeps_probability_first_copy() -> None:
    source_paths = [
        ROOT / "apps/web/app/fixtures/[fixtureId]/page.tsx",
        ROOT / "apps/web/components/match/match-header.tsx",
        ROOT / "apps/web/components/prediction/prediction-trace.tsx",
        ROOT / "apps/web/components/model/model-fingerprint.tsx",
        ROOT / "apps/web/components/score/score-top-list.tsx",
    ]
    combined = "\n".join(path.read_text() for path in source_paths)

    assert "ProbabilityTriptych" in combined
    assert "Prediction Trace" in combined
    assert "Model Fingerprint" in combined
    assert "确定赛果" in combined
