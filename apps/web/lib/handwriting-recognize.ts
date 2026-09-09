import { ocrInkImage } from "./scan-ocr";

export type HandwritingMode = "text" | "math";

export type HandwritingResult = {
  text: string;
  latex?: string | null;
  source: "local" | "cloud";
};

/** On-device first (Tesseract), cloud fallback for math or low-confidence text. */
export async function recognizeHandwriting(
  imageBase64: string,
  mode: HandwritingMode
): Promise<HandwritingResult> {
  if (mode === "text") {
    try {
      const local = await ocrInkImage(imageBase64);
      if (local.length >= 1) {
        return { text: local, source: "local" };
      }
    } catch {
      // fall through to cloud
    }
  }

  const { apiPost } = await import("./api");
  const res = await apiPost<{ text: string; latex?: string | null }>("/ai/handwriting", {
    image_base64: imageBase64,
    mode,
  });
  const text = (mode === "math" && res.latex ? res.latex : res.text || "").trim();
  return { text, latex: res.latex, source: "cloud" };
}
