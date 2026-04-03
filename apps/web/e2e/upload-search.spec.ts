import { expect, test } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

test("upload pseudo-pdf and find it in search", async ({ request }) => {
  test.setTimeout(210_000);
  const courseRes = await request.post(`${API}/courses`, {
    data: { name: "E2E Course" }
  });
  expect(courseRes.ok()).toBeTruthy();
  const course = await courseRes.json();

  const token = `e2e_pdf_token_${Date.now()}`;
  const pdfBytes = Buffer.from(
    `%PDF-1.1
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 69 >>stream
BT /F1 12 Tf 72 100 Td (${token}) Tj ET
endstream endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000060 00000 n 
0000000117 00000 n 
0000000268 00000 n 
0000000388 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
458
%%EOF`
  );

  const uploadRes = await request.post(`${API}/resources/upload`, {
    multipart: {
      course_id: course.id,
      title: "E2E PDF",
      resource_type: "pdf",
      file: {
        name: "e2e.pdf",
        mimeType: "application/pdf",
        buffer: pdfBytes
      }
    }
  });
  expect(uploadRes.ok()).toBeTruthy();
  const resource = await uploadRes.json();

  const deadline = Date.now() + 90_000;
  let done = false;
  while (Date.now() < deadline) {
    const r = await request.get(`${API}/resources/${resource.id}`);
    expect(r.ok()).toBeTruthy();
    const body = await r.json();
    if (body.index_status === "done") {
      done = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  expect(done).toBeTruthy();

  let found = false;
  const searchDeadline = Date.now() + 45_000;
  while (Date.now() < searchDeadline) {
    const searchRes = await request.get(`${API}/search?q=${encodeURIComponent(token)}&limit=10`);
    expect(searchRes.ok()).toBeTruthy();
    const hits = await searchRes.json();
    expect(Array.isArray(hits)).toBeTruthy();
    if (hits.some((h: { resource_id: string }) => h.resource_id === resource.id)) {
      found = true;
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  expect(found).toBeTruthy();
});

test("resource detail shows loading and stable states", async ({ page }) => {
  const resourceId = "11111111-1111-1111-1111-111111111111";
  await page.route(`${API}/resources/${resourceId}`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: resourceId,
        title: "Detail Resource",
        resource_type: "file",
        parse_status: "done",
        ocr_status: "done",
        index_status: "done",
        storage_path: "/tmp/detail.txt",
        metadata_json: {},
      }),
    });
  });
  await page.route(`${API}/resources/${resourceId}/jobs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    });
  });
  await page.route(`${API}/resources/${resourceId}/chunks`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: "c1", chunk_index: 0, page_number: 1, text_preview: "preview text" }]),
    });
  });

  await page.goto("/resources/00000000-0000-0000-0000-000000000000");
  await expect(page.getByTestId("error-state")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.goto(`/resources/${resourceId}`);
  await expect(page.getByRole("heading", { name: "Resource" })).toBeVisible();
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await expect(page.getByText("Background jobs")).toBeVisible();
  await expect(page.getByTestId("error-state")).toHaveCount(0);
});

test("search page shows loading and empty states", async ({ page }) => {
  await page.route("**/search?**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    });
  });
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Search" })).toBeVisible();
  await expect(page.getByTestId("empty-state")).toBeVisible();
  await page.getByPlaceholder("Search your indexed resources…").fill("no_results_token_123456");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("resources page shows loading before empty state", async ({ page }) => {
  await page.route("**/courses", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]"
    });
  });
  await page.goto("/resources");
  await expect(page.getByRole("heading", { name: "Resources" })).toBeVisible();
  await expect(page.getByTestId("loading-state")).toBeVisible();
  await expect(page.getByTestId("empty-state")).toBeVisible();
});
