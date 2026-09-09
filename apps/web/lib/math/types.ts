/** Shared types for the on-device math recognizer. */

/**
 * A recognized symbol and where it sits on the page.
 * Coordinates are pixels with y increasing downward.
 */
export type MathSymbol = {
  /** Canonical label, e.g. "2", "x", "+", "sqrt", "bar", "int". */
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** Symbols that draw as a single horizontal stroke. */
export const BAR_LABEL = "bar";

/** Labels that never take a superscript/subscript directly. */
export const OPERATOR_LABELS = new Set([
  "+",
  "-",
  "=",
  "<",
  ">",
  "times",
  "div",
  "pm",
  "leq",
  "geq",
  "neq",
  "approx",
  "cdot",
]);

/** Multi-letter names that should render as LaTeX operators. */
export const FUNCTION_NAMES = new Set([
  "sin",
  "cos",
  "tan",
  "sec",
  "csc",
  "cot",
  "log",
  "ln",
  "exp",
  "lim",
  "max",
  "min",
  "det",
  "gcd",
]);

/** Canonical label -> LaTeX fragment. Anything unlisted renders as itself. */
export const LATEX_TOKENS: Record<string, string> = {
  times: "\\times",
  div: "\\div",
  pm: "\\pm",
  leq: "\\leq",
  geq: "\\geq",
  neq: "\\neq",
  approx: "\\approx",
  cdot: "\\cdot",
  infty: "\\infty",
  int: "\\int",
  sum: "\\sum",
  prod: "\\prod",
  alpha: "\\alpha",
  beta: "\\beta",
  gamma: "\\gamma",
  delta: "\\delta",
  theta: "\\theta",
  lambda: "\\lambda",
  mu: "\\mu",
  pi: "\\pi",
  sigma: "\\sigma",
  phi: "\\phi",
  omega: "\\omega",
  rightarrow: "\\rightarrow",
  "{": "\\{",
  "}": "\\}",
};
