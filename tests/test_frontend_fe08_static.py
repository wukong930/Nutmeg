from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "apps/web"
SCAN_DIRS = [
    WEB_ROOT / "app",
    WEB_ROOT / "components",
    WEB_ROOT / "lib",
    WEB_ROOT / "types",
]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def frontend_sources() -> list[Path]:
    sources: list[Path] = []
    for directory in SCAN_DIRS:
        sources.extend(
            path
            for path in directory.rglob("*")
            if path.suffix in {".ts", ".tsx", ".css"}
            and "node_modules" not in path.parts
            and ".next" not in path.parts
        )
    return sources


def test_global_compliance_notice_is_wired() -> None:
    app_shell = read("apps/web/components/layout/app-shell.tsx")
    notice = read("apps/web/components/layout/compliance-notice.tsx")
    globals_css = read("apps/web/app/globals.css")
    layout = read("apps/web/app/layout.tsx")

    assert "ComplianceNotice" in app_shell
    assert "app-footer" in app_shell
    assert "本工具仅提供概率分析与研究参考，不保证结果，不构成投注建议" in notice
    assert "预测时间、模型版本和数据质量需一并阅读" in notice
    assert "合规与风险提示" in notice
    assert ".compliance-notice" in globals_css
    assert "仅供概率分析与研究参考" in layout


def test_required_fe08_risk_copy_exists() -> None:
    parlay_page = read("apps/web/app/parlays/page.tsx")
    parlay_panel = read("apps/web/components/parlay/parlay-evaluation-panel.tsx")
    parlay_builder = read("apps/web/components/parlay/parlay-builder.tsx")
    upset_page = read("apps/web/app/upsets/page.tsx")
    upset_panel = read("apps/web/components/upset/favorite-fragility-panel.tsx")
    score_top = read("apps/web/components/score/score-top-list.tsx")
    score_grid = read("apps/web/components/score/score-grid-heatmap.tsx")

    assert "串关会放大波动。组合命中概率通常显著低于单场概率。" in (
        parlay_page + parlay_panel
    )
    assert "不构成投注建议" in parlay_page
    assert "低质量、过期或规则无效的选项需要降权或排除" in parlay_builder
    assert "冷门观察表示模型识别到热门方向风险，不代表冷门一定发生。" in (
        upset_page + upset_panel
    )
    assert "精确比分属于低概率事件，Top 5 比分也不代表确定结果。" in score_top
    assert "比分概率矩阵：行表示主队进球，列表示客队进球" in score_grid


def test_probability_diagnostics_have_accessible_captions() -> None:
    accuracy_page = read("apps/web/app/accuracy/page.tsx")
    accuracy_css = read("apps/web/components/accuracy/accuracy.css")
    score_grid = read("apps/web/components/score/score-grid-heatmap.tsx")
    score_css = read("apps/web/components/score/score.css")

    assert "<caption>按玩法拆分 Log Loss、Brier、ECE 和样本量。</caption>" in accuracy_page
    assert "<caption>按联赛拆分概率评分和低样本漂移风险。</caption>" in accuracy_page
    assert ".accuracy-table caption" in accuracy_css
    assert "<caption>" in score_grid
    assert ".score-grid-table caption" in score_css


def test_forbidden_frontend_guarantee_language_is_absent() -> None:
    forbidden_terms = [
        "稳赚",
        "必中",
        "稳胆",
        "包红",
        "锁定",
        "神单",
        "无脑上",
        "必出冷门",
        "保证盈利",
        "guaranteed profit",
        "sure win",
        "must bet",
    ]

    violations: list[str] = []
    for path in frontend_sources():
        text = path.read_text()
        for term in forbidden_terms:
            if term in text:
                violations.append(f"{path.relative_to(ROOT)}: {term}")

    assert violations == []


def test_fe08_readme_status_is_recorded() -> None:
    readme = read("README.md")

    assert "Frontend FE-08 copy and compliance pass" in readme
    assert "global research-only risk notice" in readme
    assert "static checks against forbidden guarantee language" in readme


def test_v31_minimal_answer_page_consumes_public_answer_set() -> None:
    api_contract = read("apps/web/lib/api-contract.ts")
    api_client = read("apps/web/lib/api.ts")
    api_types = read("apps/web/types/api.ts")
    final_panel = read("apps/web/components/recommendation/final-answer-panel.tsx")
    dashboard = read("apps/web/app/dashboard/page.tsx")
    parlays = read("apps/web/app/parlays/page.tsx")

    assert "answer_set: recommendationAnswerSetResponseSchema" in api_contract
    assert "primary_answer: recommendationAnswerResponseSchema" in api_contract
    assert "backup_answers: z.array(recommendationAnswerResponseSchema)" in api_contract
    assert "RecommendationAnswerSet" in api_types
    assert "answerSet?.primaryAnswer" in api_client
    assert "answerSet?.backupAnswers" in api_client

    assert "今日最佳答案" in final_panel
    assert "必要备选" in final_panel
    assert "冷门提醒" in final_panel
    assert "调整预算/关数" in final_panel
    assert "Global Best" not in final_panel

    assert "answerSet={answerSet}" in dashboard
    assert "answerSet={answerSet}" in parlays
    assert "查看候选比赛与冷门摘要" in dashboard
    assert "查看参数与备选方案" in parlays


def test_v31_mock_path_requires_explicit_dev_fallback_flag() -> None:
    api_client = read("apps/web/lib/api.ts")
    playwright_config = read("apps/web/playwright.config.ts")
    upgrade_doc = read("Nutmeg_docs_v2/11_Nutmeg_V3_1_Recommendation_Upgrade.md")

    assert "NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS" in api_client
    assert "FRONTEND_DEV_FALLBACKS_ENABLED" in api_client
    assert "parseBooleanEnv" in api_client
    assert "未启用开发兜底" in api_client
    assert "recommendationBundleFromFallbackTickets" in api_client
    assert "NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS" in playwright_config
    assert 'process.env.NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS ?? "true"' in (
        playwright_config
    )
    assert "V3.1-70 当前落地能力" in upgrade_doc
