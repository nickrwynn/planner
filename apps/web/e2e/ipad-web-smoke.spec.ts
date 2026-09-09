import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

test.use({
  viewport: { width: 834, height: 1194 },
  hasTouch: true,
  isMobile: true
});

test("ipad smoke: critical routes remain usable", async ({ page }) => {
  await page.route(`${API}/health`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", postgres: { ok: true }, redis: { ok: true } })
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
      body: JSON.stringify({ task: null, reasons: [] })
    });
  });
  await page.route(`${API}/planner/upcoming?limit=8`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tasks: [] }) });
  });
  await page.route(`${API}/courses`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: "c1", name: "iPad Course", user_id: "u1", created_at: "", updated_at: "" }])
    });
  });
  await page.route("**/search?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: "h1", resource_id: "r1", title: "Result", score: 0.9 }])
    });
  });

  const criticalRoutes = [
    { path: "/", heading: "Dashboard" },
    { path: "/courses", heading: "Courses" },
    { path: "/tasks", heading: "Tasks" },
    { path: "/resources", heading: "Resources" },
    { path: "/search", heading: "Search" },
    { path: "/study-lab", heading: "Study Lab" },
    { path: "/notebooks", heading: "Notebooks" },
    { path: "/notes", heading: "Notes" }
  ];

  for (const route of criticalRoutes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
  }

  await expect(page.locator(".agentPane")).toBeHidden();
  await expect(page.locator(".sidebar")).toBeVisible();
  await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Resources" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search" })).toBeVisible();
});
