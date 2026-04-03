import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

test("dashboard has no critical accessibility violations", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).analyze();
  const critical = results.violations.filter((v) => v.impact === "critical");
  expect(critical).toEqual([]);
});

test("critical pages render primary landmarks and state containers", async ({ page }) => {
  const routes = [
    "/",
    "/courses",
    "/courses/00000000-0000-0000-0000-000000000000",
    "/resources",
    "/resources/00000000-0000-0000-0000-000000000000",
    "/notebooks",
    "/notebooks/00000000-0000-0000-0000-000000000000",
    "/notes",
    "/study-lab",
    "/search",
    "/tasks"
  ];

  for (const route of routes) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    if (route === "/") {
      await expect(page.locator(".card").first()).toBeVisible();
      expect(await page.getByTestId("error-state").count()).toBeLessThanOrEqual(1);
      continue;
    }
    await expect(page.getByTestId("loading-state").or(page.getByTestId("empty-state")).or(page.getByTestId("error-state")).first()).toBeVisible();
  }
});

test("resource error surface keeps retry affordance", async ({ page }) => {
  await page.goto("/resources/00000000-0000-0000-0000-000000000000");
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByTestId("retry-button")).toBeVisible();
});

test("dashboard error state has no critical accessibility violations", async ({ page }) => {
  await page.route(`${API}/health`, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "forced health failure" }),
    });
  });
  await page.route(`${API}/tasks?limit=100&offset=0`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
  await page.route(`${API}/resources?limit=100&offset=0`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
  await page.route(`${API}/planner/next`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ task: null, reasons: [] }),
    });
  });
  await page.route(`${API}/planner/upcoming?limit=8`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tasks: [] }) });
  });
  await page.goto("/");
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByTestId("retry-button")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  const critical = results.violations.filter((v) => v.impact === "critical");
  expect(critical).toEqual([]);
});
