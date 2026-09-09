import { isCloudAiAvailable } from "./ai-availability";
import { canRecognizeOnDevice, recognizeOnDevice } from "./handwriting-native";
import { ocrInkImage } from "./scan-ocr";

export type HandwritingMode = "text" | "math";

export type HandwritingResult = {
  text: string;
  latex?: string | null;
  source: "device" | "local" | "cloud";
};

/**
 * Recognition order:
 *  1. Apple Vision on-device (iPad app) — instant, no network, no API key.
 *  2. Tesseract in the browser — on-device fallback for web.
 *  3. Cloud LLM — math only, and only when a key is actually configured.
 *
 * Math has no on-device LaTeX engine yet, so it falls back to the cloud. When
 * the cloud is unavailable the on-device plain text is returned rather than
 * nothing.
 */
export async function recognizeHandwriting(
  imageBase64: string,
  mode: HandwritingMode
): Promise<HandwritingResult> {
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
