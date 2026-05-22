from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_market_visualization_components_are_wired() -> None:
    fixture_page = (ROOT / "apps/web/app/fixtures/[fixtureId]/page.tsx").read_text()
    api_mapping = (ROOT / "apps/web/lib/api.ts").read_text()
    schemas = (ROOT / "apps/web/lib/schemas.ts").read_text()

    assert "MarketGapChart" in fixture_page
    assert "HandicapResolverPanel" in fixture_page
    assert "ScoreGridHeatmap" in fixture_page
    assert "MarketMovementTimeline" in fixture_page
    assert "scoreGrid:" in api_mapping
    assert "prediction.score_grid.grid" in api_mapping
    assert "scoreGrid:" in schemas


def test_market_visualization_copy_marks_missing_history() -> None:
    market_gap = (ROOT / "apps/web/components/market/market-gap-chart.tsx").read_text()
    movement = (ROOT / "apps/web/components/market/market-movement-timeline.tsx").read_text()
    heatmap = (ROOT / "apps/web/components/score/score-grid-heatmap.tsx").read_text()

    assert "市场分歧只表示模型与市场观点不同" in market_gap
    assert "历史快照待接入" in movement
    assert "避免把缺失数据解释为真实走势" in movement
    assert "比分概率是底层模型输出" in heatmap
    assert "tailMass" in heatmap
