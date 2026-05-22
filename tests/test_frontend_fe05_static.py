from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_upset_watch_components_are_wired() -> None:
    upsets_page = (ROOT / "apps/web/app/upsets/page.tsx").read_text()
    upset_card = (ROOT / "apps/web/components/upset/upset-card.tsx").read_text()
    fragility_panel = (
        ROOT / "apps/web/components/upset/favorite-fragility-panel.tsx"
    ).read_text()
    contribution_bars = (
        ROOT / "apps/web/components/upset/risk-contribution-bars.tsx"
    ).read_text()
    explanation_drawer = (
        ROOT / "apps/web/components/upset/upset-explanation-drawer.tsx"
    ).read_text()

    assert "filterUpsets" in upsets_page
    assert "最低概率差" in upsets_page
    assert "FavoriteFragilityPanel" in upset_card
    assert "UpsetExplanationDrawer" in upset_card
    assert "热门脆弱度" in fragility_panel
    assert "RiskContributionBars" in fragility_panel
    assert "冷门风险贡献条" in contribution_bars
    assert "查看解释载荷" in explanation_drawer


def test_upset_watch_api_contract_exposes_explainability_payload() -> None:
    frontend_contract = (ROOT / "apps/web/lib/api-contract.ts").read_text()
    frontend_types = (ROOT / "apps/web/types/api.ts").read_text()
    backend_schemas = (ROOT / "apps/api/src/nutmeg/api/schemas.py").read_text()
    backend_contract = (ROOT / "apps/api/src/nutmeg/api/contract.py").read_text()

    assert "favorite_model_probability" in frontend_contract
    assert "contributions" in frontend_contract
    assert "explanation_groups" in frontend_contract
    assert "UpsetContribution" in frontend_types
    assert "UpsetContributionPayload" in backend_schemas
    assert "_upset_contributions" in backend_contract


def test_upset_watch_uses_observation_copy_not_certainty() -> None:
    source_paths = [
        ROOT / "apps/web/app/upsets/page.tsx",
        ROOT / "apps/web/components/upset/favorite-fragility-panel.tsx",
        ROOT / "apps/web/components/upset/upset-explanation-drawer.tsx",
    ]
    combined = "\n".join(path.read_text() for path in source_paths)

    assert "冷门观察表示模型识别到热门方向风险，不代表冷门一定发生。" in combined
    assert "必出冷门" not in combined
    assert "确定结果" not in combined
