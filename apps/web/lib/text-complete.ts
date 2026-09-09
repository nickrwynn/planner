/**
 * Text completion: on-device first, cloud only as a backup.
 *
 * Order of attempts:
 *  1. Apple's on-device dictionary (finishes the word you are typing).
 *  2. A phrase model learned from your own notes (continues the sentence).
 *  3. Cursor cloud — only when both come up empty, and only after a pause,
 *     with a hard timeout so a slow network never blocks typing.
 */

import { isCloudAiAvailable } from "./ai-availability";
import { completeWordOnDevice } from "./text-assist-native";
import { predictContinuation } from "./text-predict";

export type CompletionSource = "device" | "phrases" | "cloud" | "none";

export type Completion = {
  /** Text to append at the caret. Empty when there is no suggestion. */
  text: string;
  source: CompletionSource;
};

const CLOUD_TIMEOUT_MS = 1200;

const EMPTY: Completion = { text: "", source: "none" };

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), ms);
    promise
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch(() => {
        clearTimeout(timer);
        resolve(null);
      });
  });
}

/**
 * Instant, on-device only. Safe to call on every keystroke.
 */
export async function suggestOnDevice(textBeforeCaret: string): Promise<Completion> {
  if (!textBeforeCaret.trim()) return EMPTY;

  const word = await completeWordOnDevice(textBeforeCaret);
  if (word) return { text: word, source: "device" };

  const phrase = predictContinuation(textBeforeCaret);
  if (phrase) {
    const needsSpace = /\S$/.test(textBeforeCaret);
    return { text: `${needsSpace ? " " : ""}${phrase}`, source: "phrases" };
  }

  return EMPTY;
}

/**
 * Cloud backup. Call this only after `suggestOnDevice` returned nothing and the
 * user has paused typing.
 */
export async function suggestFromCloud(
  textBeforeCaret: string,
  opts?: { courseId?: string; signal?: AbortSignal }
): Promise<Completion> {
  if (textBeforeCaret.trim().length < 12) return EMPTY;
  if (!(await isCloudAiAvailable())) return EMPTY;

  const { apiPost } = await import("./api");
  const req = apiPost<{ completion: string }>("/ai/complete", {
    text: textBeforeCaret.slice(-1200),
    course_id: opts?.courseId || null,
  });

  const res = await withTimeout(req, CLOUD_TIMEOUT_MS);
  const text = (res?.completion || "").trim();
  if (!text) return EMPTY;

  const needsSpace = /\S$/.test(textBeforeCaret) && !/^[\s.,;:!?]/.test(text);
  return { text: `${needsSpace ? " " : ""}${text}`, source: "cloud" };
}
