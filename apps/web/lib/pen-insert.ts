/**
 * Text splicing for pen-to-field insertion.
 *
 * Recognition runs repeatedly while ink sits on the pad, and each pass reads
 * *all* the ink, not just the newest stroke. Appending every pass turns "cat"
 * into "c ca cat", so a pass has to replace what the previous pass wrote
 * rather than add to it. These helpers own that bookkeeping.
 */

/** The region a previous recognition pass wrote into a field. */
export type InsertionSpan = {
  /** Ink session the span belongs to; a new session appends instead. */
  session: number;
  start: number;
  end: number;
};

export type SplicePlan = {
  /** Range to overwrite. */
  from: number;
  to: number;
};

/**
 * Where the next recognition result should go.
 *
 * Same ink session as the last pass means the pass is a refinement of the same
 * handwriting, so it overwrites. Anything else lands at the caret.
 */
export function planInsertion(
  previous: InsertionSpan | null,
  session: number,
  caret: { start: number; end: number }
): SplicePlan {
  if (previous && previous.session === session) {
    return { from: previous.start, to: previous.end };
  }
  return { from: caret.start, to: caret.end };
}

export function spliceText(
  value: string,
  plan: SplicePlan,
  text: string
): { value: string; span: { start: number; end: number } } {
  const from = Math.max(0, Math.min(plan.from, value.length));
  const to = Math.max(from, Math.min(plan.to, value.length));
  return {
    value: `${value.slice(0, from)}${text}${value.slice(to)}`,
    span: { start: from, end: from + text.length },
  };
}
