/**
 * On-device phrase prediction learned from the user's own writing.
 *
 * A small n-gram model kept in localStorage: no network, no model download,
 * and lookups are a plain object access so suggestions appear instantly.
 */

const STORE_KEY = "studyflows_phrase_model_v1";
const MAX_CONTEXTS = 4000;
const MAX_NEXT_PER_CONTEXT = 6;

type NextCounts = Record<string, number>;
type PhraseModel = Record<string, NextCounts>;

let cache: PhraseModel | null = null;

function load(): PhraseModel {
  if (cache) return cache;
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(STORE_KEY);
    cache = raw ? (JSON.parse(raw) as PhraseModel) : {};
  } catch {
    cache = {};
  }
  return cache;
}

function persist(model: PhraseModel) {
  cache = model;
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(model));
  } catch {
    // Storage full or unavailable — predictions just stop improving.
  }
}

function tokenize(text: string): string[] {
  return text
    .replace(/\s+/g, " ")
    .split(" ")
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Trim the model so localStorage stays small: keep the most-used contexts. */
function prune(model: PhraseModel): PhraseModel {
  const keys = Object.keys(model);
  if (keys.length <= MAX_CONTEXTS) return model;
  const scored = keys.map((k) => {
    const total = Object.values(model[k]).reduce((a, b) => a + b, 0);
    return { k, total };
  });
  scored.sort((a, b) => b.total - a.total);
  const kept: PhraseModel = {};
  for (const { k } of scored.slice(0, MAX_CONTEXTS)) kept[k] = model[k];
  return kept;
}

function contextKeys(tokens: string[]): string[] {
  // Trigram context first (more specific), then bigram, then unigram.
  const lower = tokens.map((t) => t.toLowerCase());
  const keys: string[] = [];
  if (lower.length >= 2) keys.push(lower.slice(-2).join(" "));
  if (lower.length >= 1) keys.push(lower.slice(-1).join(" "));
  return keys;
}

/** Learn from a block of the user's text. Safe to call repeatedly. */
export function learnFromText(text: string) {
  const tokens = tokenize(text);
  if (tokens.length < 3) return;
  const model = { ...load() };

  for (let i = 0; i < tokens.length - 1; i += 1) {
    const next = tokens[i + 1];
    if (!next) continue;
    const ctxs = contextKeys(tokens.slice(Math.max(0, i - 1), i + 1));
    for (const ctx of ctxs) {
      const bucket = model[ctx] ? { ...model[ctx] } : {};
      bucket[next] = (bucket[next] || 0) + 1;
      const entries = Object.entries(bucket)
        .sort((a, b) => b[1] - a[1])
        .slice(0, MAX_NEXT_PER_CONTEXT);
      model[ctx] = Object.fromEntries(entries);
    }
  }

  persist(prune(model));
}

/**
 * Predict up to `maxWords` continuation words for the text before the caret.
 * Returns "" when the model has nothing confident.
 */
export function predictContinuation(textBeforeCaret: string, maxWords = 4): string {
  const model = load();
  const endsMidWord = /[A-Za-z']$/.test(textBeforeCaret);
  if (endsMidWord) return "";

  let tokens = tokenize(textBeforeCaret);
  if (tokens.length === 0) return "";

  const out: string[] = [];
  for (let step = 0; step < maxWords; step += 1) {
    let picked: string | null = null;
    for (const ctx of contextKeys(tokens)) {
      const bucket = model[ctx];
      if (!bucket) continue;
      const best = Object.entries(bucket).sort((a, b) => b[1] - a[1])[0];
      // Require the context to have been seen more than once before suggesting.
      if (best && best[1] >= 2) {
        picked = best[0];
        break;
      }
    }
    if (!picked) break;
    out.push(picked);
    tokens = [...tokens, picked];
    if (/[.!?]$/.test(picked)) break;
  }

  return out.join(" ");
}

export function clearPhraseModel() {
  cache = {};
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORE_KEY);
  } catch {
    // ignore
  }
}
