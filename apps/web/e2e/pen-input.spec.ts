import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { planInsertion, spliceText, type InsertionSpan } from "../lib/pen-insert";
import { cropRect, growBounds } from "../lib/ink-crop";

/** Pure pen-input logic — no browser needed. */

test.describe("pen insertion", () => {
  /** Feed a sequence of recognition results the way the ink pad does. */
  function run(passes: { text: string; session: number }[], initial = "") {
    let value = initial;
    let caret = initial.length;
    let span: InsertionSpan | null = null;
    for (const pass of passes) {
      const plan = planInsertion(span, pass.session, { start: caret, end: caret });
      const result = spliceText(value, plan, pass.text);
      value = result.value;
      caret = result.span.end;
      span = { session: pass.session, ...result.span };
    }
    return value;
  }

  test("repeat passes over the same ink refine instead of piling up", () => {
    // Every pass re-reads the whole pad, so this is what writing "cat" one
    // stroke at a time produces. Appending gave "c ca cat ".
    expect(run([
      { text: "c ", session: 1 },
      { text: "ca ", session: 1 },
      { text: "cat ", session: 1 },
    ])).toBe("cat ");
  });

  test("a new ink session adds to what the last one left", () => {
    expect(run([
      { text: "hello ", session: 1 },
      { text: "world ", session: 2 },
    ])).toBe("hello world ");
  });

  test("refinement within a session survives across sessions", () => {
    expect(run([
      { text: "he ", session: 1 },
      { text: "hello ", session: 1 },
      { text: "wor ", session: 2 },
      { text: "world ", session: 2 },
    ])).toBe("hello world ");
  });

  test("the first pass respects existing text and the caret", () => {
    const plan = planInsertion(null, 1, { start: 5, end: 5 });
    expect(spliceText("Notes here", plan, "X").value).toBe("NotesX here");
  });

  test("a selection is replaced by the first pass", () => {
    const plan = planInsertion(null, 1, { start: 0, end: 5 });
    expect(spliceText("Notes here", plan, "Ideas").value).toBe("Ideas here");
  });

  test("a stale span past the end of the value cannot corrupt it", () => {
    // The field can be edited by hand between passes.
    const plan = planInsertion({ session: 1, start: 40, end: 60 }, 1, { start: 2, end: 2 });
    expect(spliceText("short", plan, "X").value).toBe("shortX");
  });

  test("an inverted span is treated as an insertion point", () => {
    const plan = planInsertion({ session: 1, start: 4, end: 2 }, 1, { start: 0, end: 0 });
    expect(spliceText("abcdef", plan, "-").value).toBe("abcd-ef");
  });
});

test.describe("ink bounds", () => {
  test("bounds grow to cover every point", () => {
    let b = growBounds(null, 10, 20);
    b = growBounds(b, 5, 40);
    b = growBounds(b, 30, 15);
    expect(b).toEqual({ minX: 5, minY: 15, maxX: 30, maxY: 40 });
  });

  test("a single point still yields bounds", () => {
    expect(growBounds(null, 7, 7)).toEqual({ minX: 7, minY: 7, maxX: 7, maxY: 7 });
  });
});

test.describe("ink crop", () => {
  const bounds = { minX: 100, minY: 100, maxX: 300, maxY: 160 };

  test("crops around the ink rather than the whole canvas", () => {
    const rect = cropRect(bounds, 2000, 1200, 1, 2);
    expect(rect).not.toBeNull();
    // Padding of 12 + stroke width, applied on both sides.
    expect(rect!.sx).toBe(86);
    expect(rect!.sy).toBe(86);
    expect(rect!.sw).toBeLessThan(2000);
    expect(rect!.sh).toBeLessThan(1200);
  });

  test("device pixel ratio scales the source rectangle", () => {
    const at1 = cropRect(bounds, 2000, 1200, 1, 2)!;
    const at2 = cropRect(bounds, 4000, 2400, 2, 2)!;
    expect(at2.sx).toBe(at1.sx * 2);
    expect(at2.sw).toBe(at1.sw * 2);
  });

  test("the crop never reaches outside the canvas", () => {
    const rect = cropRect({ minX: 0, minY: 0, maxX: 50, maxY: 50 }, 60, 60, 1, 2)!;
    expect(rect.sx).toBe(0);
    expect(rect.sy).toBe(0);
    expect(rect.sx + rect.sw).toBeLessThanOrEqual(60);
    expect(rect.sy + rect.sh).toBeLessThanOrEqual(60);
  });

  test("small writing is scaled up so glyphs are legible", () => {
    // One short word: recognisers do badly on glyphs only a few pixels tall.
    const rect = cropRect({ minX: 0, minY: 0, maxX: 80, maxY: 20 }, 400, 200, 1, 2)!;
    expect(rect.dh).toBeGreaterThan(rect.sh);
  });

  test("large writing is capped rather than sent at full size", () => {
    const rect = cropRect({ minX: 0, minY: 0, maxX: 3000, maxY: 1500 }, 4000, 2000, 1, 2)!;
    expect(Math.max(rect.dw, rect.dh)).toBeLessThanOrEqual(1024);
  });

  test("an empty area yields no crop", () => {
    expect(cropRect({ minX: 5, minY: 5, maxX: 5, maxY: 5 }, 1, 1, 1, 2)).toBeNull();
  });
});

const CSS = fs.readFileSync(path.join(__dirname, "../app/globals.css"), "utf-8");

const SHEET_HARNESS = `<!doctype html>
<html><head><meta charset="utf-8"><style>${CSS}</style></head>
<body style="margin:0;height:2000px">
  <div class="inputModeBar" role="toolbar">
    <button type="button" class="isActive">Auto</button>
    <button type="button">Pen</button>
    <button type="button">Type</button>
    <button type="button">Ink</button>
  </div>
  <div class="penBridgeSheet">
    <div class="penBridgeSheetHeader"><strong>Write with Apple Pencil</strong><button>Done</button></div>
    <p class="penBridgeHint">Auto mode hint</p>
    <div class="studyInkPad"><canvas class="studyInkCanvas"></canvas></div>
  </div>
</body></html>`;

/**
 * The sheet and mode bar had no CSS at all, so they rendered as plain blocks at
 * the end of the page instead of floating over it.
 */
test.describe("pen sheet layout", () => {
  test("the sheet and mode bar float above the page", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.setContent(SHEET_HARNESS);

    const positions = await page.evaluate(() => {
      const bar = getComputedStyle(document.querySelector(".inputModeBar")!);
      const sheet = getComputedStyle(document.querySelector(".penBridgeSheet")!);
      return {
        barPosition: bar.position,
        sheetPosition: sheet.position,
        barZ: Number(bar.zIndex),
        sheetZ: Number(sheet.zIndex),
        sheetBg: sheet.backgroundColor,
      };
    });

    expect(positions.barPosition).toBe("fixed");
    expect(positions.sheetPosition).toBe("fixed");
    // The sheet has to sit above the bar or its Done button is unreachable.
    expect(positions.sheetZ).toBeGreaterThan(positions.barZ);
    // An opaque background: content behind must not show through the ink pad.
    expect(positions.sheetBg).not.toBe("rgba(0, 0, 0, 0)");

    // Both stay on screen even though the page is far taller than the viewport.
    await page.evaluate(() => window.scrollTo(0, 1200));
    for (const selector of [".inputModeBar", ".penBridgeSheet"]) {
      const box = await page.locator(selector).boundingBox();
      expect(box).not.toBeNull();
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y).toBeLessThan(768);
    }

    // The sheet must not overlap the mode bar it sits above.
    const sheet = (await page.locator(".penBridgeSheet").boundingBox())!;
    const bar = (await page.locator(".inputModeBar").boundingBox())!;
    expect(sheet.y + sheet.height).toBeLessThanOrEqual(bar.y + 1);

    await page.screenshot({ path: "test-results/pen-sheet.png" });
  });

  test("the ink canvas blocks touch scrolling", async ({ page }) => {
    await page.setContent(SHEET_HARNESS);
    const touchAction = await page.evaluate(
      () => getComputedStyle(document.querySelector(".studyInkCanvas")!).touchAction
    );
    expect(touchAction).toBe("none");
  });
});

/**
 * The keyboard guard makes the field readonly while the pencil is in use, since
 * iPadOS ignores preventDefault when deciding to raise the keyboard. These pin
 * down the two browser behaviours that approach depends on.
 */
test.describe("keyboard guard", () => {
  test("a readonly field still accepts recognised text and caret moves", async ({ page }) => {
    await page.setContent(`<textarea id="t" readonly>hello world</textarea>`);

    const result = await page.evaluate(() => {
      const el = document.querySelector<HTMLTextAreaElement>("#t")!;
      el.value = "hello there world";
      el.setSelectionRange(6, 11);
      return { value: el.value, start: el.selectionStart, end: el.selectionEnd };
    });

    expect(result.value).toBe("hello there world");
    expect(result.start).toBe(6);
    expect(result.end).toBe(11);
  });

  test("a readonly field refuses typed input but an unguarded one takes it", async ({ page }) => {
    await page.setContent(`<textarea id="guarded" readonly></textarea><textarea id="open"></textarea>`);

    await page.locator("#guarded").click();
    await page.keyboard.type("pencil");
    expect(await page.locator("#guarded").inputValue()).toBe("");

    await page.locator("#open").click();
    await page.keyboard.type("finger");
    expect(await page.locator("#open").inputValue()).toBe("finger");
  });

  test("clearing the guard during the tap lets a finger type immediately", async ({ page }) => {
    // The release has to land in pointerdown: by focus time the browser has
    // already decided whether to offer a keyboard for this tap.
    await page.setContent(`
      <textarea id="t" readonly></textarea>
      <script>
        const el = document.getElementById("t");
        el.addEventListener("pointerdown", (e) => {
          if (e.pointerType !== "pen") el.readOnly = false;
        }, true);
      </script>
    `);

    await page.locator("#t").click();
    await page.keyboard.type("typed");

    expect(await page.locator("#t").inputValue()).toBe("typed");
    expect(await page.locator("#t").evaluate((el: HTMLTextAreaElement) => el.readOnly)).toBe(false);
  });
});
