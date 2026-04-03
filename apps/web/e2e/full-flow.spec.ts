import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

test("full flow: upload -> index -> search -> ai -> notes -> planner", async ({ request }) => {
  test.setTimeout(210_000);
  const courseRes = await request.post(`${API}/courses`, { data: { name: "Full Flow Course" } });
  expect(courseRes.ok()).toBeTruthy();
  const course = await courseRes.json();

  const taskRes = await request.post(`${API}/tasks`, {
    data: { course_id: course.id, title: "Prepare full-flow session", status: "todo" }
  });
  expect(taskRes.ok()).toBeTruthy();

  const token = `full_flow_token_${Date.now()}`;
  const uploadRes = await request.post(`${API}/resources/upload`, {
    multipart: {
      course_id: course.id,
      title: "Full flow resource",
      resource_type: "file",
      file: {
        name: "full-flow.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(`This content contains ${token} for retrieval.`)
      }
    }
  });
  expect(uploadRes.ok()).toBeTruthy();
  const resource = await uploadRes.json();

  const deadline = Date.now() + 90_000;
  let ready = false;
  while (Date.now() < deadline) {
    const r = await request.get(`${API}/resources/${resource.id}`);
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    if (body.index_status === "done" && body.lifecycle_state === "searchable") {
      ready = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  expect(ready).toBeTruthy();

  let found = false;
  const searchDeadline = Date.now() + 45_000;
  while (Date.now() < searchDeadline) {
    const searchRes = await request.get(`${API}/search?q=${encodeURIComponent(token)}&limit=10`);
    expect(searchRes.ok()).toBeTruthy();
    const hits = await searchRes.json();
    if (hits.some((h: { resource_id: string }) => h.resource_id === resource.id)) {
      found = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  expect(found).toBeTruthy();

  const askRes = await request.post(`${API}/ai/ask`, {
    data: { message: `What mentions ${token}`, course_id: course.id, resource_ids: [resource.id], top_k: 5 }
  });
  expect(askRes.ok()).toBeTruthy();
  const ask = await askRes.json();
  expect(Array.isArray(ask.citations)).toBeTruthy();
  expect(ask.citations.length).toBeGreaterThan(0);

  const notebookRes = await request.post(`${API}/notebooks`, {
    data: { course_id: course.id, title: "Flow Notebook" }
  });
  expect(notebookRes.ok()).toBeTruthy();
  const notebook = await notebookRes.json();

  const docRes = await request.post(`${API}/note-documents`, {
    data: { notebook_id: notebook.id, title: "Flow Notes", note_type: "typed" }
  });
  expect(docRes.ok()).toBeTruthy();
  const doc = await docRes.json();

  const pageRes = await request.post(`${API}/note-pages`, {
    data: { note_document_id: doc.id, page_index: 0, text: `Captured ${token} in notes.` }
  });
  expect(pageRes.ok()).toBeTruthy();

  const plannerRes = await request.get(`${API}/planner/next`);
  expect(plannerRes.ok()).toBeTruthy();
  const planner = await plannerRes.json();
  expect(planner.task).not.toBeNull();
});

test("courses page shows error + retry behavior", async ({ page }) => {
  await page.goto("/courses");
  await page.getByPlaceholder("Course name").fill("Bad schema course");
  await page.locator("textarea").first().fill("{");
  await page.getByRole("button", { name: "Create" }).first().click();
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "Courses" })).toBeVisible();
  await expect(page.getByTestId("error-state")).toHaveCount(0);
});

test("dashboard shows standardized error + retry and no empty-state confusion", async ({ page }) => {
  let failHealth = true;
  await page.route(`${API}/health`, async (route) => {
    if (failHealth) {
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "dashboard health failed" }),
      });
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", postgres: { ok: true }, redis: { ok: true } }),
    });
  });
  await page.route(`${API}/tasks?limit=100&offset=0`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route(`${API}/resources?limit=100&offset=0`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route(`${API}/planner/next`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ task: null, reasons: [] }),
    });
  });
  await page.route(`${API}/planner/upcoming?limit=8`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ tasks: [] }),
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByTestId("retry-button")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toHaveCount(0);

  failHealth = false;
  await page.getByTestId("retry-button").click();
  await expect(page.getByTestId("error-state")).toHaveCount(0);
  await expect(page.getByText("Stack health")).toBeVisible();
});

test("tasks page shows loading before terminal state", async ({ page }) => {
  await page.route("**/courses", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]"
    });
  });
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Tasks" })).toBeVisible();
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("critical pages expose consistent state containers", async ({ page }) => {
  const routes = [
    { path: "/", heading: "Dashboard" },
    { path: "/courses", heading: "Courses" },
    { path: "/resources", heading: "Resources" },
    { path: "/notebooks", heading: "Notebooks" },
    { path: "/notes", heading: "Notes" },
    { path: "/study-lab", heading: "Study Lab" },
    { path: "/search", heading: "Search" },
    { path: "/tasks", heading: "Tasks" }
  ];

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    if (route.path === "/") {
      await expect(page.locator(".card").first()).toBeVisible();
      expect(await page.getByTestId("error-state").count()).toBeLessThanOrEqual(1);
      continue;
    }
    await expect(page.getByTestId("loading-state").or(page.getByTestId("empty-state")).or(page.getByTestId("error-state")).first()).toBeVisible();
  }
});

test("courses first-load failure shows error without empty-state confusion", async ({ page }) => {
  await page.route(`${API}/courses`, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    });
  });
  await page.goto("/courses");
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toHaveCount(0);
});

test("study lab failure shows error without empty-state overlap", async ({ page }) => {
  await page.route(`${API}/courses`, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    });
  });
  await page.goto("/study-lab");
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toHaveCount(0);
});
