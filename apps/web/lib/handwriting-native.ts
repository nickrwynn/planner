import { Capacitor, registerPlugin } from "@capacitor/core";

export type NativeCharBox = {
  char: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

type HandwritingNativePlugin = {
  isAvailable(): Promise<{ available: boolean }>;
  recognize(options: { imageBase64: string; mode: "text" | "math" }): Promise<{
    text: string;
    lineCount: number;
  }>;
  recognizeSymbols(options: { imageBase64: string }): Promise<{
    symbols: NativeCharBox[];
    width: number;
    height: number;
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

/** Per-character boxes from Vision, for the math layout pass. */
export async function recognizeSymbolsOnDevice(imageBase64: string): Promise<NativeCharBox[]> {
  if (!canRecognizeOnDevice()) return [];
  try {
    const res = await HandwritingNative.recognizeSymbols({ imageBase64 });
    return res.symbols || [];
  } catch {
    return [];
  }
}
