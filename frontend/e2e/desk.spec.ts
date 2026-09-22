import { expect, test } from "@playwright/test";

const USER = "e2eadmin";
const PASS = "testhorse1";

test.describe.configure({ mode: "serial" });

test("local sign-in creates the first admin", async ({ page, request }) => {
  const health = await request.get("http://127.0.0.1:8810/api/v1/health");
  expect(health.ok()).toBeTruthy();
  await page.goto("/signin");
  await expect(page.getByTestId("local-username")).toBeVisible();

  await page.getByTestId("local-username").fill(USER);
  await page.getByTestId("local-password").fill(PASS);
  await page.getByTestId("local-auth-submit").click();

  await page.waitForURL((url) => url.pathname === "/" || url.pathname === "/workspace" || url.pathname === "/admin");
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();
});

test("admin can save a weekday schedule", async ({ page }) => {
  await page.goto("/signin");
  await page.getByTestId("local-username").fill(USER);
  await page.getByTestId("local-password").fill(PASS);
  await page.getByTestId("local-auth-submit").click();
  await page.waitForURL((url) => url.pathname !== "/signin");

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: /Universe|defaults/i })).toBeVisible();
  const morning = page.getByLabel("India · NSE morning");
  await morning.fill("09:30");
  await page.getByTestId("save-schedule").click();
  await expect(page.getByText(/Schedule saved|weekday clock/i).first()).toBeVisible();
});

test("run attach works in demo mode", async ({ page }) => {
  await page.goto("/signin");
  await page.getByTestId("local-username").fill(USER);
  await page.getByTestId("local-password").fill(PASS);
  await page.getByTestId("local-auth-submit").click();
  await page.waitForURL((url) => url.pathname !== "/signin");

  await page.goto("/");
  const run = page.getByTestId("run-desk");
  await expect(run).toBeVisible();
  await run.click();
  await expect(
    page.getByText(/Running desk|Desk run in progress|Run .* started|Attached to run/i).first(),
  ).toBeVisible({ timeout: 20_000 });
});
