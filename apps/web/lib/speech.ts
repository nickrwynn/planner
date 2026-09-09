let voicesReady: Promise<SpeechSynthesisVoice[]> | null = null;

const VOICE_URI_KEY = "tts_voice_uri";
const RATE_KEY = "tts_rate";

function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    return Promise.resolve([]);
  }
  if (!voicesReady) {
    voicesReady = new Promise((resolve) => {
      const existing = window.speechSynthesis.getVoices();
      if (existing.length) {
        resolve(existing);
        return;
      }
      const onChange = () => {
        const list = window.speechSynthesis.getVoices();
        if (list.length) {
          window.speechSynthesis.removeEventListener("voiceschanged", onChange);
          resolve(list);
        }
      };
      window.speechSynthesis.addEventListener("voiceschanged", onChange);
      window.setTimeout(() => resolve(window.speechSynthesis.getVoices()), 500);
    });
  }
  return voicesReady;
}

export async function listVoices(): Promise<SpeechSynthesisVoice[]> {
  const voices = await loadVoices();
  return [...voices].sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name));
}

export function getPreferredVoiceUri(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(VOICE_URI_KEY);
}

export function setPreferredVoiceUri(uri: string | null): void {
  if (typeof window === "undefined") return;
  if (!uri) localStorage.removeItem(VOICE_URI_KEY);
  else localStorage.setItem(VOICE_URI_KEY, uri);
}

export function getSpeechRate(): number {
  if (typeof window === "undefined") return 1;
  const raw = Number(localStorage.getItem(RATE_KEY));
  if (!Number.isFinite(raw) || raw < 0.6 || raw > 1.6) return 1;
  return raw;
}

export function setSpeechRate(rate: number): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(RATE_KEY, String(rate));
}

export async function speakText(
  text: string,
  opts?: { onEnd?: () => void; onError?: (msg: string) => void; voiceUri?: string | null }
): Promise<void> {
  const cleaned = text.trim();
  if (!cleaned) {
    opts?.onError?.("Nothing to read.");
    return;
  }
  if (typeof window === "undefined" || !window.speechSynthesis) {
    opts?.onError?.("Read aloud is not supported in this browser.");
    return;
  }
  window.speechSynthesis.cancel();
  const voices = await loadVoices();
  const utterance = new SpeechSynthesisUtterance(cleaned);
  const preferred = opts?.voiceUri ?? getPreferredVoiceUri();
  const chosen =
    (preferred ? voices.find((v) => v.voiceURI === preferred) : null) ||
    voices.find((v) => /en(-|_|$)/i.test(v.lang)) ||
    voices[0];
  if (chosen) utterance.voice = chosen;
  utterance.rate = getSpeechRate();
  utterance.onend = () => opts?.onEnd?.();
  utterance.onerror = () => {
    opts?.onError?.("Read aloud failed.");
    opts?.onEnd?.();
  };
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (typeof window !== "undefined") window.speechSynthesis?.cancel();
}

export function isSpeechSupported(): boolean {
  return typeof window !== "undefined" && !!window.speechSynthesis;
}
