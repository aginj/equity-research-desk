import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const backend = path.join(__dirname, "..", "backend");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3810",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8810",
      cwd: backend,
      url: "http://127.0.0.1:8810/api/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        SMP_FORCE_DEMO_DATA: "true",
        SMP_DATABASE_URL: "sqlite:///./data/e2e.db",
        SMP_RATE_LIMIT_ENABLED: "false",
        SMP_AUTH_JWT_SECRET: "",
        SMP_API_KEY: "",
        OPENAI_API_KEY: "",
        ANTHROPIC_API_KEY: "",
        CURSOR_API_KEY: "",
        FINNHUB_API_KEY: "",
        NEWSAPI_KEY: "",
      },
    },
    {
      command: "npm run dev -- --port 3810",
      url: "http://127.0.0.1:3810",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8810",
        AUTH_SECRET: "e2e-auth-secret-e2e-auth-secret-e2e-auth",
        AUTH_URL: "http://127.0.0.1:3810",
        AUTH_TRUST_HOST: "true",
      },
    },
  ],
});
