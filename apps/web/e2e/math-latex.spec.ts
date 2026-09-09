import { expect, test } from "@playwright/test";
import { symbolsToLatex } from "../lib/math/latex-layout";
import { barsFromComponents } from "../lib/math/segment";
import type { MathSymbol } from "../lib/math/types";

/**
 * Layout is pure, so these run without a browser. Boxes mimic what the
 * segmenter produces: y grows downward, body symbols ~40px tall.
 */

const sym = (label: string, x: number, y: number, w: number, h: number): MathSymbol => ({
  label,
  x,
  y,
  w,
  h,
});

test.describe("math layout -> LaTeX", () => {
  test("plain sequence", () => {
    const symbols = [
      sym("2", 0, 100, 30, 40),
      sym("+", 40, 100, 30, 40),
      sym("3", 80, 100, 30, 40),
    ];
    expect(symbolsToLatex(symbols)).toBe("2 + 3");
  });

  test("superscript becomes a power", () => {
    const symbols = [
      sym("x", 0, 100, 30, 40),
      // Smaller and raised: sits above the baseline at y=140.
      sym("2", 32, 84, 18, 24),
    ];
    expect(symbolsToLatex(symbols)).toBe("x^2");
  });

  test("subscript becomes an index", () => {
    const symbols = [
      sym("a", 0, 100, 30, 40),
      sym("n", 32, 124, 18, 24),
    ];
    expect(symbolsToLatex(symbols)).toBe("a_n");
  });

  test("multi-character exponent is grouped", () => {
    const symbols = [
      sym("x", 0, 100, 30, 40),
      sym("1", 32, 84, 16, 24),
      sym("0", 50, 84, 16, 24),
    ];
    expect(symbolsToLatex(symbols)).toBe("x^{10}");
  });

  test("wide bar with content above and below is a fraction", () => {
    const symbols = [
      sym("1", 10, 60, 24, 36),
      sym("bar", 0, 108, 60, 6),
      sym("2", 10, 124, 24, 36),
    ];
    expect(symbolsToLatex(symbols)).toBe("\\frac{1}{2}");
  });

  test("narrow bar with nothing below stays a minus", () => {
    const symbols = [
      sym("5", 0, 100, 30, 40),
      sym("bar", 38, 118, 22, 5),
      sym("2", 68, 100, 30, 40),
    ];
    expect(symbolsToLatex(symbols)).toBe("5 - 2");
  });

  test("fraction keeps surrounding terms", () => {
    const symbols = [
      sym("y", 0, 100, 28, 40),
      sym("=", 34, 100, 28, 40),
      sym("1", 78, 60, 24, 36),
      sym("bar", 68, 108, 60, 6),
      sym("2", 78, 124, 24, 36),
      sym("+", 136, 100, 28, 40),
      sym("3", 172, 100, 28, 40),
    ];
    expect(symbolsToLatex(symbols)).toBe("y = \\frac{1}{2} + 3");
  });

  test("radical covers its radicand", () => {
    const symbols = [
      // The sqrt box spans the content it encloses.
      sym("sqrt", 0, 90, 90, 50),
      sym("x", 24, 100, 26, 36),
      sym("+", 54, 100, 26, 36),
    ];
    expect(symbolsToLatex(symbols)).toBe("\\sqrt{x +}");
  });

  test("operator labels map to LaTeX commands", () => {
    const symbols = [
      sym("pi", 0, 100, 30, 40),
      sym("times", 40, 100, 30, 40),
      sym("2", 80, 100, 30, 40),
    ];
    expect(symbolsToLatex(symbols)).toBe("\\pi \\times 2");
  });

  test("consecutive letters spell a function name", () => {
    const symbols = [
      sym("s", 0, 100, 24, 40),
      sym("i", 26, 100, 24, 40),
      sym("n", 52, 100, 24, 40),
      sym("x", 84, 100, 24, 40),
    ];
    expect(symbolsToLatex(symbols)).toBe("\\sin x");
  });

  test("empty input yields empty output", () => {
    expect(symbolsToLatex([])).toBe("");
  });
});

test.describe("ink segmentation -> bars", () => {
  const comp = (x: number, y: number, w: number, h: number, pixels = 400) => ({ x, y, w, h, pixels });

  test("wide flat stroke is a bar", () => {
    const bars = barsFromComponents([comp(0, 100, 60, 5)]);
    expect(bars).toHaveLength(1);
    expect(bars[0].label).toBe("bar");
    expect(bars[0].w).toBe(60);
  });

  test("tall glyph is not a bar", () => {
    expect(barsFromComponents([comp(0, 100, 30, 40)])).toHaveLength(0);
  });

  test("two stacked aligned bars merge into equals", () => {
    const bars = barsFromComponents([comp(10, 100, 40, 4), comp(10, 112, 40, 4)]);
    expect(bars).toHaveLength(1);
    expect(bars[0].label).toBe("=");
    // The merged box spans both strokes.
    expect(bars[0].y).toBe(100);
    expect(bars[0].h).toBe(16);
  });

  test("bars far apart stay separate", () => {
    const bars = barsFromComponents([comp(10, 40, 40, 4), comp(10, 300, 40, 4)]);
    expect(bars).toHaveLength(2);
    expect(bars.every((b) => b.label === "bar")).toBe(true);
  });

  test("bars that do not share an x-span stay separate", () => {
    const bars = barsFromComponents([comp(0, 100, 40, 4), comp(200, 108, 40, 4)]);
    expect(bars).toHaveLength(2);
  });

  test("a fraction bar over an equals sign is read as both", () => {
    const bars = barsFromComponents([
      comp(0, 100, 40, 4),
      comp(0, 112, 40, 4),
      comp(200, 60, 80, 5),
    ]);
    const labels = bars.map((b) => b.label).sort();
    expect(labels).toEqual(["=", "bar"]);
  });
});
