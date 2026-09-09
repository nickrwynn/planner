import { Capacitor, registerPlugin } from "@capacitor/core";

type SpellIssue = {
  word: string;
  start: number;
  length: number;
  suggestions: string[];
};

type TextAssistNativePlugin = {
  isAvailable(): Promise<{ available: boolean }>;
  completeWord(options: { prefix: string; language?: string; limit?: number }): Promise<{
    partial: string;
    completions: string[];
  }>;
  spellSuggestions(options: { text: string; language?: string }): Promise<{ issues: SpellIssue[] }>;
};

const TextAssistNative = registerPlugin<TextAssistNativePlugin>("TextAssist");

export type { SpellIssue };

export function hasNativeTextAssist(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable("TextAssist");
}

/** On-device word completion (Apple's dictionary). Returns "" when nothing fits. */
export async function completeWordOnDevice(textBeforeCaret: string): Promise<string> {
  if (!hasNativeTextAssist()) return "";
  try {
    const res = await TextAssistNative.completeWord({ prefix: textBeforeCaret, limit: 1 });
    const partial = res.partial || "";
    const best = (res.completions || [])[0] || "";
    if (!partial || !best) return "";
    // Return only the remaining characters so the caller can render ghost text.
    if (best.toLowerCase().startsWith(partial.toLowerCase()) && best.length > partial.length) {
      return best.slice(partial.length);
    }
    return "";
  } catch {
    return "";
  }
}

/** On-device spell check (Apple's checker). Empty list when unavailable. */
export async function spellCheckOnDevice(text: string): Promise<SpellIssue[]> {
  if (!hasNativeTextAssist() || !text.trim()) return [];
  try {
    const res = await TextAssistNative.spellSuggestions({ text });
    return res.issues || [];
  } catch {
    return [];
  }
}
