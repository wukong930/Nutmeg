from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_parlay_lab_components_are_wired() -> None:
    page = (ROOT / "apps/web/app/parlays/page.tsx").read_text()
    builder = (ROOT / "apps/web/components/parlay/parlay-builder.tsx").read_text()
    leg_selector = (
        ROOT / "apps/web/components/parlay/parlay-leg-selector.tsx"
    ).read_text()
    expansion_tree = (
        ROOT / "apps/web/components/parlay/parlay-expansion-tree.tsx"
    ).read_text()
    evaluation_panel = (
        ROOT / "apps/web/components/parlay/parlay-evaluation-panel.tsx"
    ).read_text()
    ticket_card = (ROOT / "apps/web/components/parlay/parlay-ticket-card.tsx").read_text()

    assert "ParlayBuilder" in page
    assert "parlayOptionsFromParams" in page
    assert "MultiSelectionLegPreview" in builder
    assert "Multi-selection leg UI" in leg_selector
    assert "ParlayExpansionTree" in expansion_tree
    assert "ParlayEvaluationPanel" in evaluation_panel
    assert "ParlayEvaluationPanel" in ticket_card
    assert "ParlayExpansionTree" in ticket_card


def test_parlay_lab_contract_exposes_atomic_bets_and_explanations() -> None:
    frontend_contract = (ROOT / "apps/web/lib/api-contract.ts").read_text()
    frontend_types = (ROOT / "apps/web/types/api.ts").read_text()
    frontend_api = (ROOT / "apps/web/lib/api.ts").read_text()
    backend_schemas = (ROOT / "apps/api/src/nutmeg/api/schemas.py").read_text()
    backend_contract = (ROOT / "apps/api/src/nutmeg/api/contract.py").read_text()

    assert "atomic_bets" in frontend_contract
    assert "explanation_json" in frontend_contract
    assert "AtomicParlayBet" in frontend_types
    assert "correlationPenalty" in frontend_api
    assert "atomicBets" in frontend_api
    assert "AtomicBet" in backend_schemas
    assert "atomic_bets=evaluation.atomic_bets" in backend_contract


def test_parlay_lab_displays_required_metrics_and_risk_copy() -> None:
    page = (ROOT / "apps/web/app/parlays/page.tsx").read_text()
    evaluation_panel = (
        ROOT / "apps/web/components/parlay/parlay-evaluation-panel.tsx"
    ).read_text()

    combined = page + "\n" + evaluation_panel
    for text in ["注数", "单注", "总金额", "命中概率", "预期返还", "EV", "ROI"]:
        assert text in combined
    assert "串关会放大波动。组合命中概率通常显著低于单场概率。" in combined
    assert "不构成投注建议" in combined
