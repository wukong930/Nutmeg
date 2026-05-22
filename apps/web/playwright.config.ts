import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.NUTMEG_E2E_PORT ?? 3100);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;
const skipWebServer = Boolean(process.env.PLAYWRIGHT_BASE_URL);

export default defineConfig({
  testDir: "./e2e",
  timeout: 35_000,
  expect: {
    timeout: 10_000,
  },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: skipWebServer
    ? undefined
    : {
        command: `npm run start -- --hostname 127.0.0.1 --port ${port}`,
        env: {
          NUTMEG_API_BASE_URL:
            process.env.NUTMEG_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1",
          NUTMEG_API_TIMEOUT_MS: process.env.NUTMEG_API_TIMEOUT_MS ?? "800",
          NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS:
            process.env.NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS ?? "true",
          NUTMEG_PROVIDER_OPS_UI_TOKEN:
            process.env.NUTMEG_PROVIDER_OPS_UI_TOKEN ?? "e2e-provider-ops-token",
        },
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
        url: baseURL,
      },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 5"] },
    },
  ],
});
