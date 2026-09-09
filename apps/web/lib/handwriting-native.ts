import { Capacitor, registerPlugin } from "@capacitor/core";

type HandwritingNativePlugin = {
  isAvailable(): Promise<{ available: boolean }>;
  recognize(options: { imageBase64: string; mode: "text" | "math" }): Promise<{
    text: string;
    lineCount: number;
  }>;
};

const HandwritingNative = registerPlugin<HandwritingNativePlugin>("Handwriting");

/** Apple Vision recognition is available in the native iPad app only. */
export function canRecognizeOnDevice(): boolean {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable("Handwriting");
}

/**
 * On-device (Apple Vision) recognition. No network, no API key.
 * Returns null when the native plugin is unavailable or found no text.
 */
export async function recognizeOnDevice(
  imageBase64: string,
  mode: "text" | "math"
): Promise<string | null> {
  if (!canRecognizeOnDevice()) return null;
  try {
    const res = await HandwritingNative.recognize({ imageBase64, mode });
    const text = (res.text || "").trim();
    return text || null;
  } catch {
    return null;
  }
}
