/**
 * What actually happened on the last pen stroke and the last recognition.
 *
 * Recognition quality problems are almost impossible to diagnose from the
 * outside: the engine, the bitmap it received, and the pointer type the browser
 * reported are all invisible. This records them so the app can show them.
 *
 * Deliberately a plain module-level store rather than React state — the writers
 * are event handlers and library functions with no access to a provider.
 */

export type PointerSample = {
  type: string;
  pressure: number;
  /** Surface that received it, for telling the pad and the notebook apart. */
  surface: string;
  at: number;
};

export type RecognitionSample = {
  at: number;
  mode: "text" | "math";
  /** Which engine produced the text, or why none did. */
  engine: string;
  ms: number;
  text: string;
  /** The exact bitmap handed to the engine, so a bad crop is visible. */
  imageDataUrl: string | null;
  imageBytes: number;
  error?: string | null;
};

const MAX_POINTERS = 14;

let pointers: PointerSample[] = [];
let lastRecognition: RecognitionSample | null = null;
const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

export function subscribeDiagnostics(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function recordPointer(sample: Omit<PointerSample, "at">) {
  pointers = [{ ...sample, at: Date.now() }, ...pointers].slice(0, MAX_POINTERS);
  notify();
}

export function recordRecognition(sample: Omit<RecognitionSample, "at">) {
  lastRecognition = { ...sample, at: Date.now() };
  notify();
}

export function getPointerSamples(): PointerSample[] {
  return pointers;
}

export function getLastRecognition(): RecognitionSample | null {
  return lastRecognition;
}

/** Counts by pointer type, which is the question that matters for the keyboard. */
export function pointerTypeCounts(): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const sample of pointers) {
    counts[sample.type || "(empty)"] = (counts[sample.type || "(empty)"] || 0) + 1;
  }
  return counts;
}
