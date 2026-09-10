import { isCloudAiAvailable } from "./ai-availability";
import { canRecognizeOnDevice, recognizeOnDevice } from "./handwriting-native";
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
 *  1. Apple Vision on-device (iPad app) — instant, no network, no API key.
 *     Math additionally runs our own layout engine to produce LaTeX.
 *  2. Tesseract in the browser — on-device fallback for web.
 *  3. Cloud LLM — only when on-device came up empty and a key is configured.
 */
export async function recognizeHandwriting(
  rawImage: string,
  mode: HandwritingMode
): Promise<HandwritingResult> {
  const imageBase64 = toRawBase64(rawImage);
  if (mode === "math") {
    const latex = await recognizeMathOnDevice(imageBase64);
    if (latex) return { text: latex, latex, source: "device" };
  }

  const device = await recognizeOnDevice(imageBase64, mode);
  if (device && mode === "text") {
    return { text: device, source: "device" };
  }

  let local = "";
  if (mode === "text" && !canRecognizeOnDevice()) {
    try {
      local = await ocrInkImage(imageBase64);
      if (local.length >= 1) {
        return { text: local, source: "local" };
      }
    } catch {
      // fall through to cloud
    }
  }

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
      if (!device && !local) throw err;
    }
  }

  return { text: device || local || "", source: device ? "device" : "local" };
}
