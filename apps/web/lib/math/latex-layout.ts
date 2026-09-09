/**
 * Turns positioned symbols into LaTeX.
 *
 * This is the structural half of the recognizer and is deliberately pure: no
 * DOM, no model, no async. Given boxes and labels it decides what is a
 * fraction, what is a superscript, and what belongs under a radical.
 */

import {
  BAR_LABEL,
  FUNCTION_NAMES,
  LATEX_TOKENS,
  OPERATOR_LABELS,
  type MathSymbol,
} from "./types";

/** A bar this much wider than the median symbol is structural, not a minus. */
const FRACTION_BAR_RATIO = 1.35;
/** Anything at least this tall relative to the tallest symbol is running text. */
const BODY_HEIGHT_RATIO = 0.7;
/** A script's centre must sit this far off the body centre, relative to body height. */
const SCRIPT_OFFSET = 0.22;
/** A script is also visibly smaller than the running text. */
const SCRIPT_MAX_SIZE = 0.85;

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

const centerY = (s: MathSymbol) => s.y + s.h / 2;
const right = (s: MathSymbol) => s.x + s.w;
const bottom = (s: MathSymbol) => s.y + s.h;

/**
 * The widest bar that has symbols both above and below it is a fraction.
 * Returns null when no bar qualifies, which makes a lone bar a minus sign.
 */
function findFractionBar(symbols: MathSymbol[]): MathSymbol | null {
  const medianWidth = median(symbols.map((s) => s.w));
  const bars = symbols
    .filter((s) => s.label === BAR_LABEL && s.w >= medianWidth * FRACTION_BAR_RATIO)
    .sort((a, b) => b.w - a.w);

  for (const bar of bars) {
    const spanned = symbols.filter((s) => s !== bar && right(s) > bar.x && s.x < right(bar));
    const above = spanned.some((s) => centerY(s) < bar.y);
    const below = spanned.some((s) => centerY(s) > bottom(bar));
    if (above && below) return bar;
  }
  return null;
}

type Body = { height: number; center: number };

/**
 * Size and vertical centre of the running text, ignoring bars and anything
 * small enough to be a script. Scripts are measured against this.
 */
function measureBody(symbols: MathSymbol[]): Body {
  const candidates = symbols.filter((s) => s.label !== BAR_LABEL);
  const source = candidates.length ? candidates : symbols;
  const tallest = Math.max(...source.map((s) => s.h));
  const body = source.filter((s) => s.h >= tallest * BODY_HEIGHT_RATIO);
  return {
    height: median(body.map((s) => s.h)) || 1,
    center: median(body.map((s) => centerY(s))),
  };
}

type ScriptRole = "base" | "sup" | "sub";

function scriptRole(s: MathSymbol, body: Body): ScriptRole {
  if (s.h > body.height * SCRIPT_MAX_SIZE) return "base";
  const rise = body.center - centerY(s);
  if (rise > body.height * SCRIPT_OFFSET) return "sup";
  if (-rise > body.height * SCRIPT_OFFSET) return "sub";
  return "base";
}

function tokenToLatex(s: MathSymbol): string {
  if (s.label === BAR_LABEL) return "-";
  return LATEX_TOKENS[s.label] ?? s.label;
}

/** Bars render as minus, so they space like an operator. */
function spacesAsOperator(label: string): boolean {
  return label === BAR_LABEL || OPERATOR_LABELS.has(label);
}

/** Wrap in braces only when LaTeX needs it. */
function group(latex: string): string {
  const trimmed = latex.trim();
  if (trimmed.length <= 1) return trimmed;
  // A single command like \pi is already a unit.
  if (/^\\[a-zA-Z]+$/.test(trimmed)) return trimmed;
  return `{${trimmed}}`;
}

/** Longest function name at the start of `word`, or null. */
function functionPrefix(word: string): string | null {
  const lower = word.toLowerCase();
  let best: string | null = null;
  for (const name of FUNCTION_NAMES) {
    if (lower.startsWith(name) && (!best || name.length > best.length)) best = name;
  }
  return best;
}

/** Render a run of adjacent letters, pulling out function names like sin/log. */
function lettersToLatex(word: string): string {
  let rest = word;
  let out = "";
  while (rest) {
    const fn = functionPrefix(rest);
    if (fn) {
      out += `\\${fn} `;
      rest = rest.slice(fn.length);
    } else {
      out += rest[0];
      rest = rest.slice(1);
    }
  }
  return out;
}

/**
 * Convert a set of symbols into LaTeX.
 * Symbols may be in any order; they are sorted internally.
 */
export function symbolsToLatex(symbols: MathSymbol[]): string {
  if (!symbols.length) return "";
  const sorted = [...symbols].sort((a, b) => a.x - b.x);

  const bar = findFractionBar(sorted);
  if (bar) {
    const inSpan = (s: MathSymbol) => right(s) > bar.x && s.x < right(bar);
    const numerator = sorted.filter((s) => s !== bar && inSpan(s) && centerY(s) < bar.y);
    const denominator = sorted.filter((s) => s !== bar && inSpan(s) && centerY(s) > bottom(bar));
    const before = sorted.filter((s) => right(s) <= bar.x);
    const after = sorted.filter((s) => s.x >= right(bar));

    const frac = `\\frac{${symbolsToLatex(numerator)}}{${symbolsToLatex(denominator)}}`;
    return [symbolsToLatex(before), frac, symbolsToLatex(after)]
      .filter(Boolean)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
  }

  const body = measureBody(sorted);
  let out = "";
  let emittedBase = false;
  let i = 0;

  while (i < sorted.length) {
    const s = sorted[i];

    if (s.label === "sqrt") {
      // The radical's box covers what it contains.
      const radicand = sorted.filter(
        (o) => o !== s && o.x >= s.x && right(o) <= right(s) + s.w * 0.15
      );
      out += `\\sqrt{${symbolsToLatex(radicand)}}`;
      const consumed = new Set<MathSymbol>([s, ...radicand]);
      i += 1;
      while (i < sorted.length && consumed.has(sorted[i])) i += 1;
      emittedBase = true;
      continue;
    }

    // Scripts only attach to something already written.
    const role = emittedBase ? scriptRole(s, body) : "base";
    if (role !== "base") {
      const run: MathSymbol[] = [];
      while (i < sorted.length && scriptRole(sorted[i], body) === role) {
        run.push(sorted[i]);
        i += 1;
      }
      out += `${role === "sup" ? "^" : "_"}${group(symbolsToLatex(run))}`;
      continue;
    }

    // Consecutive letters may spell a function name like sin or log.
    if (/^[a-zA-Z]$/.test(s.label)) {
      const letters: MathSymbol[] = [];
      while (
        i < sorted.length &&
        /^[a-zA-Z]$/.test(sorted[i].label) &&
        scriptRole(sorted[i], body) === "base"
      ) {
        letters.push(sorted[i]);
        i += 1;
      }
      out += lettersToLatex(letters.map((l) => l.label).join(""));
      emittedBase = true;
      continue;
    }

    const token = tokenToLatex(s);
    // Spaces around relations and binary operators keep the LaTeX readable.
    out += spacesAsOperator(s.label) ? ` ${token} ` : token;
    emittedBase = true;
    i += 1;
  }

  return out.replace(/\s+/g, " ").trim();
}
