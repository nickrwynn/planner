import { isCloudAiAvailable } from "./ai-availability";
import { canRecognizeOnDevice, recognizeOnDevice } from "./handwriting-native";
import { recordRecognition } from "./ink-diagnostics";
import { recognizeMathOnDevice } from "./math/recognize-math";
import { ocrInkImage } from "./scan-ocr";

export type HandwritingMode = "text" | "math";

export type HandwritingResult = {
  text: string;
  latex?: string | null;
  source: "device" | "local" | "cloud";
};

/**
 * Accept either raw base64 or a full `data:` URL.
 *
 * Callers hand over whatever `toDataURL` gave them. The native plugin and the
 * cloud endpoint both tolerate the prefix, but `atob` does not, so leaving it
 * on made the browser OCR path throw and every recognition fall through to the
 * network.
 */
function toRawBase64(image: string): string {
  const trimmed = image.trim();
  if (!trimmed.startsWith("data:")) return trimmed;
  const comma = trimmed.indexOf(",");
  return comma === -1 ? trimmed : trimmed.slice(comma + 1);
}

/**
 * Recognition order:
 *  1. Apple Vision on-device (iPad app) — instant, no network, no API key, and
 *     trained on handwriting. Math additionally runs our own layout engine.
 *  2. Cloud vision model — the accurate option in a plain browser.
 *  3. Tesseract in the browser — offline last resort.
 *
 * Tesseract sits last on purpose. It is a printed-text engine trained on
 * typeset fonts, so on handwriting it returns confident nonsense; it is only
 * worth using when there is no better option available at all.
 */
export async function recognizeHandwriting(
  rawImage: string,
  mode: HandwritingMode
): Promise<HandwritingResult> {
  const started = Date.now();
  const imageBase64 = toRawBase64(rawImage);
  const record = (engine: string, text: string, error?: string) =>
    recordRecognition({
      mode,
      engine,
      ms: Date.now() - started,
      text,
      imageDataUrl: `data:image/png;base64,${imageBase64}`,
      imageBytes: Math.round((imageBase64.length * 3) / 4),
      error: error ?? null,
    });

  try {
    const result = await recognizeWith(imageBase64, mode);
    record(result.source, result.text);
    return result;
  } catch (err) {
    record("failed", "", err instanceof Error ? err.message : String(err));
    throw err;
  }
}

async function recognizeWith(
  imageBase64: string,
  mode: HandwritingMode
): Promise<HandwritingResult> {
  if (mode === "math") {
    const latex = await recognizeMathOnDevice(imageBase64);
    if (latex) return { text: latex, latex, source: "device" };
  }

  const device = await recognizeOnDevice(imageBase64, mode);
  if (device && mode === "text") {
    return { text: device, source: "device" };
  }

  let cloudError: unknown = null;
  if (await isCloudAiAvailable()) {
    try {
      const { apiPost } = await import("./api");
      const res = await apiPost<{ text: string; latex?: string | null }>("/ai/handwriting", {
        image_base64: imageBase64,
        mode,
      });
      const text = (mode === "math" && res.latex ? res.latex : res.text || "").trim();
      if (text) return { text, latex: res.latex, source: "cloud" };
    } catch (err) {
      cloudError = err;
    }
  }

  let local = "";
  if (mode === "text" && !canRecognizeOnDevice()) {
    try {
      local = await ocrInkImage(imageBase64);
      if (local) return { text: local, source: "local" };
    } catch {
      // Nothing left to try.
    }
  }

  if (!device && !local && cloudError) throw cloudError;
  return { text: device || local || "", source: device ? "device" : "local" };
}
