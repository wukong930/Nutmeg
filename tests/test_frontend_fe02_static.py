from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_match_list_mvp_components_are_wired() -> None:
    match_card = (ROOT / "apps/web/components/match/match-card.tsx").read_text()
    dashboard = (ROOT / "apps/web/app/dashboard/page.tsx").read_text()
    filters = (ROOT / "apps/web/components/match/match-list-filters.tsx").read_text()

    assert "ProbabilityTriptych" in match_card
    assert "RiskBadge" in match_card
    assert "match.asianHandicap.label" in match_card
    assert "topScore" in match_card
    assert "MatchListFilters" in dashboard
    assert "日期" in filters
    assert "赛事" in filters
    assert "数据质量" in filters
    assert "冷门风险" in filters


def test_frontend_copy_avoids_forbidden_profit_language() -> None:
    scanned_dirs = [
        ROOT / "apps/web/app",
        ROOT / "apps/web/components",
        ROOT / "apps/web/lib",
    ]
    forbidden_terms = ("稳赚", "必中", "稳胆", "包中", "guaranteed profit", "sure win")

    source_text = "\n".join(
        path.read_text()
        for directory in scanned_dirs
        for path in directory.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    ).lower()

    for term in forbidden_terms:
        assert term not in source_text
