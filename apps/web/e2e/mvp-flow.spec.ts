import { expect, test } from "@playwright/test";

test.describe("Nutmeg MVP acceptance flow", () => {
  test("opens dashboard and drills into a fixture detail", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: "今日最佳答案" }).first()).toBeVisible();
    await expect(page.getByText("当前答案").first()).toBeVisible();
    await expect(page.getByText("冷门提醒").first()).toBeVisible();
    await expect(page.getByText("调整预算/关数").first()).toBeVisible();
    await page.getByText("查看候选比赛与冷门摘要").click();
    await expect(page.getByRole("heading", { name: "候选比赛" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Arsenal vs Liverpool" })).toBeVisible();
    await expect(page.getByText("poisson-m1.0.0").first()).toBeVisible();
    await expect(page.getByText("本工具仅提供概率分析与研究参考")).toBeVisible();
    await page.getByRole("button", { name: "保留" }).first().click();
    await expect(page.getByText("已保留").first()).toBeVisible();
    await expect(page.getByText("1 场").first()).toBeVisible();
    await expect(page.getByText("取消").first()).toBeVisible();

    await page.getByRole("link", { name: "查看详情" }).first().click();

    await expect(page).toHaveURL(/\/fixtures\/fix_/);
    await expect(page.getByRole("heading", { name: /vs/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "1X2 胜平负概率" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "让球玩法" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "中国竞彩让球", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "亚洲让球", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "比分倾向 Top 5" })).toBeVisible();
    await expect(page.getByText("精确比分属于低概率事件")).toBeVisible();
    await page.getByText("Advanced matrix").click();
    await expect(page.getByText("比分概率矩阵")).toBeVisible();
    await expect(page.getByText("poisson-m1.0.0").first()).toBeVisible();
    await expect(page.getByText(/预测/).first()).toBeVisible();
  });

  test("checks parlay and accuracy acceptance markers", async ({ page }) => {
    await page.goto("/parlays");

    await expect(page.getByRole("heading", { name: "串关最佳答案" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "今日最佳答案" })).toBeVisible();
    await expect(page.getByText("冷门提醒").first()).toBeVisible();
    await expect(page.getByText("调整预算/关数").first()).toBeVisible();
    await page.getByText("查看参数与备选方案").click();
    await expect(page.getByRole("heading", { name: "备选方案" })).toBeVisible();
    await expect(page.getByText("组合评估").first()).toBeVisible();
    await expect(page.getByText("注数").first()).toBeVisible();
    await expect(page.getByText("总金额").first()).toBeVisible();
    await expect(page.getByText("命中概率").first()).toBeVisible();
    await expect(page.getByText("EV").first()).toBeVisible();
    await expect(page.getByText("ROI").first()).toBeVisible();
    await expect(page.getByText("串关会放大波动").first()).toBeVisible();
    await expect(page.getByText("不构成投注建议").first()).toBeVisible();

    await page.goto("/accuracy");

    await expect(page.getByRole("heading", { name: "Accuracy Lab" })).toBeVisible();
    await expect(page.getByLabel("CalibrationCurve")).toBeVisible();
    await expect(page.getByLabel("BrierTrend")).toBeVisible();
    await expect(page.getByLabel("LogLossTrend")).toBeVisible();
    await expect(page.getByText("Log Loss").first()).toBeVisible();
    await expect(page.getByText("Brier Score").first()).toBeVisible();
    await expect(page.getByText("按玩法拆分 Log Loss")).toBeVisible();
    await expect(page.getByText("按联赛拆分概率评分")).toBeVisible();
  });

  test("keeps upset copy and mobile layout within viewport", async ({ page }) => {
    await page.goto("/upsets");

    await expect(page.getByRole("heading", { name: "冷门观察" })).toBeVisible();
    await expect(page.getByText("不代表冷门一定发生").first()).toBeVisible();
    await expect(page.getByText("poisson-m1.0.0").first()).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });

  test("loads provider sync templates into the dry-run form", async ({ page }) => {
    await page.goto("/providers");

    await expect(page.getByRole("heading", { name: "Provider Ops", exact: true })).toBeVisible();
    await expect(page.getByLabel("Provider Ops Access")).toBeVisible();
    await expect(
      page.getByLabel("Provider Ops Access").getByText("Admin controls locked", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Operator").fill("e2e-operator");
    await page.getByLabel("Access token").fill("e2e-provider-ops-token");
    await page.getByRole("button", { name: "Unlock Provider Ops" }).click();
    await expect(page.getByText("Admin controls unlocked")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Provider Ops Runbook" })).toBeVisible();
    await expect(page.getByLabel(/Runtime keys status/)).toBeVisible();
    await expect(page.getByLabel(/Fixture mappings status/)).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Provider Sync Workflow" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Prediction Quality Gate" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Odds Coverage Gaps" })).toBeVisible();
    await expect(page.getByText("gap fixtures").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mapped Odds Sync" })).toBeVisible();
    await expect(page.getByText("Provider sync run templates").first()).toBeVisible();
    await expect(page.getByText("Provider sync dry-run approval audit")).toBeVisible();
    await expect(page.getByText("Prediction dry-run history").first()).toBeVisible();

    await page.getByText("Template payload").first().click();
    await expect(page.getByLabel("Template task review matrix")).toBeVisible();
    await expect(page.getByText("Odds sync 1")).toBeVisible();
    await expect(page.getByText("Workflow preflight summary")).toBeVisible();
    await expect(page.getByText("No task issues recorded.").first()).toBeVisible();

    await page.getByRole("button", { name: "Load template" }).last().click();

    await expect(page.getByLabel("Template name")).toHaveValue("Fallback EPL dry-run");
    await expect(page.getByLabel("Provider competition")).toHaveValue("PL");
    await expect(page.getByText("Odds task 1")).toBeVisible();
    await expect(page.getByLabel("Sport key 1")).toHaveValue("soccer_epl");
    await expect(page.locator('input[name="odds_0_canonical_fixture_id"]')).toHaveValue(
      "fd_fixture_330299",
    );
    await page.getByRole("button", { name: "Add odds task" }).click();
    await expect(page.getByText("Odds task 2")).toBeVisible();
    await page.getByRole("button", { name: "Add availability task" }).click();
    await expect(page.getByText("Availability task 2")).toBeVisible();
    await expect(page.getByRole("button", { name: "Update selected" })).toBeEnabled();
    await expect(page.getByLabel("operator approved dry-run")).not.toBeChecked();
    await expect(page.getByText("archive approved")).toBeVisible();

    await page.getByRole("button", { name: "Dry-run workflow" }).click();
    await expect(page.getByText("Dry-run 前需要勾选 operator approval。")).toBeVisible();

    await page.getByRole("button", { name: "Mapped odds dry-run" }).click();
    await expect(
      page.getByText("Mapped odds dry-run 前需要勾选映射已审核。"),
    ).toBeVisible();
    const mappedOddsCommitForm = page.locator(
      'form[aria-label="Mapped odds commit"]',
    );
    await expect(mappedOddsCommitForm).toBeVisible();
    await expect(
      mappedOddsCommitForm.getByText("Commit Mapped Odds", { exact: true }),
    ).toBeVisible();
    await expect(mappedOddsCommitForm.getByText("operator approval")).toBeVisible();
    await expect(mappedOddsCommitForm.getByLabel("Approval note")).toBeVisible();
    await expect(
      mappedOddsCommitForm.getByLabel("approve odds snapshot write"),
    ).not.toBeChecked();
    await mappedOddsCommitForm
      .getByRole("button", { name: "Commit mapped odds" })
      .click();
    await expect(
      page.getByText("Mapped odds commit 前需要确认 dry-run 和映射审核结果。"),
    ).toBeVisible();

    await page.getByRole("button", { name: "Prediction dry-run" }).click();
    await expect(
      page.getByText("Prediction dry-run 前需要勾选质量门禁确认。"),
    ).toBeVisible();
  });
});
