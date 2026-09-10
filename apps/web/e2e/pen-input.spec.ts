import { expect, test } from "@playwright/test";
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
