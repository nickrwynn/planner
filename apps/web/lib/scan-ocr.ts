/** On-device OCR for scanned pages (Tesseract.js, lazy-loaded). */

export type OcrWord = {
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
};

export type OcrPageResult = {
  words: OcrWord[];
  fullText: string;
};

type TesseractWord = {
  text?: string;
  bbox?: { x0?: number; y0?: number; x1?: number; y1?: number };
};

type OcrWorker = {
  recognize: (image: Blob) => Promise<{ data: { text?: string; words?: TesseractWord[] } }>;
};

let workerPromise: Promise<OcrWorker> | null = null;

async function getWorker(): Promise<OcrWorker> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const { createWorker } = await import("tesseract.js");
      return createWorker("eng", 1, {
        logger: () => undefined,
      }) as Promise<OcrWorker>;
    })();
  }
  return workerPromise;
}

export async function ocrScanPage(
  jpeg: Uint8Array,
  onProgress?: (message: string) => void
): Promise<OcrPageResult> {
  onProgress?.("Loading OCR…");
  const worker = await getWorker();
  const blob = new Blob([jpeg], { type: "image/jpeg" });
  onProgress?.("Recognizing text…");
  const result = await worker.recognize(blob);
  const words: OcrWord[] = [];
  for (const w of (result.data.words || []) as TesseractWord[]) {
    const text = (w.text || "").trim();
    const bbox = w.bbox;
    if (!text || !bbox) continue;
    const x0 = bbox.x0 ?? 0;
    const y0 = bbox.y0 ?? 0;
    const x1 = bbox.x1 ?? x0;
    const y1 = bbox.y1 ?? y0;
    if (x1 <= x0 || y1 <= y0) continue;
    words.push({ text, x0, y0, x1, y1 });
  }
  return { words, fullText: (result.data.text || "").trim() };
}

/** Recognize handwriting/ink from a JPEG data URL or base64 (on-device, fast). */
export async function ocrInkImage(imageBase64: string): Promise<string> {
  const worker = await getWorker();
  const bin = atob(imageBase64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: "image/jpeg" });
  const result = await worker.recognize(blob);
  return (result.data.text || "").trim();
}
