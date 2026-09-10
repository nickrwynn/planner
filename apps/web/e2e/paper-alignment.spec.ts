import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Verifies typed text sits exactly on the ruled lines. The rule spacing and the
 * textarea line-height must stay in lockstep; this catches a drift of even 1px
 * by measuring where each line of text lands.
 */

const CSS = fs.readFileSync(path.join(__dirname, "../app/globals.css"), "utf-8");

const HARNESS = `<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin: 0; font-family: system-ui, sans-serif; background: #e5e7eb; }
  .sheet { width: 700px; margin: 20px; padding: 28px 32px 32px 44px; background: #fff; }
${CSS}
</style></head>
<body>
  <div class="studyNotebook is-notebook">
    <div class="sheet studyNotebookEntry">
      <div class="studyPaper">
        <textarea class="studyPaperText" rows="8">Line one
Line two
Line three
Line four</textarea>
        <canvas class="studyPaperInk"></canvas>
      </div>
    </div>
  </div>
</body></html>`;

test("typed lines align to the ruled lines", async ({ page }) => {
  await page.setContent(HARNESS);
  const paper = page.locator(".studyPaper");
  await expect(paper).toBeVisible();

  const metrics = await page.evaluate(() => {
    const ta = document.querySelector(".studyPaperText") as HTMLTextAreaElement;
    const style = getComputedStyle(ta);
    return {
      lineHeight: style.lineHeight,
      paddingTop: style.paddingTop,
      borderTop: style.borderTopWidth,
      fontSize: style.fontSize,
    };
  });

  // The rules repeat every 28px, so the text must advance 28px per line with
  // no padding or border pushing it out of phase.
  expect(metrics.lineHeight).toBe("28px");
  expect(metrics.paddingTop).toBe("0px");
  expect(metrics.borderTop).toBe("0px");

  // Ink layer must never swallow taps meant for the textarea.
  const inkEvents = await page.evaluate(
    () => getComputedStyle(document.querySelector(".studyPaperInk")!).pointerEvents
  );
  expect(inkEvents).toBe("none");

  await page.locator(".sheet").screenshot({ path: "test-results/paper-alignment.png" });
});
