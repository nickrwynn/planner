/**
 * On-device handwritten math -> LaTeX.
 *
 * Two cheap passes instead of a language model: Vision reads the characters
 * and tells us where each one sits, a connected-component scan finds the
 * horizontal strokes Vision is unreliable about, and the layout engine turns
 * the combined boxes into LaTeX. Everything runs locally in well under a
 * second, which is what "instant" requires.
 */

import { recognizeSymbolsOnDevice, canRecognizeOnDevice, type NativeCharBox } from "../handwriting-native";
import { symbolsToLatex } from "./latex-layout";
import { findBars } from "./segment";
import { BAR_LABEL, type MathSymbol } from "./types";

/** Unicode Vision may emit -> canonical label understood by the layout pass. */
const CHAR_LABELS: Record<string, string> = {
  "×": "times",
  "✕": "times",
  "·": "cdot",
  "÷": "div",
  "±": "pm",
  "≤": "leq",
  "≥": "geq",
  "≠": "neq",
  "≈": "approx",
  "∞": "infty",
  "∫": "int",
  "∑": "sum",
  "∏": "prod",
  "√": "sqrt",
  "→": "rightarrow",
  "α": "alpha",
  "β": "beta",
  "γ": "gamma",
  "δ": "delta",
  "θ": "theta",
  "λ": "lambda",
  "μ": "mu",
  "π": "pi",
  "σ": "sigma",
  "φ": "phi",
  "ω": "omega",
  "−": "-",
  "–": "-",
  "—": "-",
  "⋅": "cdot",
};

/** Characters Vision reports that the bar scan handles better. */
const BAR_LIKE = new Set(["-", "_", "=", "—", "–", "−", "~"]);

function toLabel(char: string): string {
  return CHAR_LABELS[char] ?? char;
}

function overlaps(a: MathSymbol, b: MathSymbol): boolean {
  const xOverlap = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const yOverlap = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  if (xOverlap <= 0 || yOverlap <= 0) return false;
  const area = xOverlap * yOverlap;
  return area > Math.min(a.w * a.h, b.w * b.h) * 0.4;
}

function charToSymbol(c: NativeCharBox): MathSymbol {
  return { label: toLabel(c.char), x: c.x, y: c.y, w: c.w, h: c.h };
}

/**
 * Recognize math from an ink image. Returns null when on-device recognition
 * is unavailable or found nothing, so the caller can fall back.
 */
export async function recognizeMathOnDevice(imageBase64: string): Promise<string | null> {
  if (!canRecognizeOnDevice()) return null;

  const [chars, bars] = await Promise.all([
    recognizeSymbolsOnDevice(imageBase64),
    findBars(imageBase64).catch(() => [] as MathSymbol[]),
  ]);

  if (!chars.length && !bars.length) return null;

  // Prefer the geometric bars: Vision reports dashes without dependable size,
  // and the layout pass needs width to tell a fraction from a minus.
  const glyphs = chars
    .map(charToSymbol)
    .filter((s) => !(BAR_LIKE.has(s.label) && bars.some((bar) => overlaps(s, bar))));

  const symbols = [...glyphs, ...bars];
  if (!symbols.length) return null;

  const latex = symbolsToLatex(symbols);
  return latex || null;
}

export { BAR_LABEL };
