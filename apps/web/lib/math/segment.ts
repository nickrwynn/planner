/**
 * Finds horizontal bars in an ink image.
 *
 * Vision reads characters but is unreliable about fraction bars and equals
 * signs — it either drops them or reports them as punctuation with no useful
 * geometry. Those strokes are trivially detectable by shape, so we find them
 * ourselves and hand both sets to the layout pass.
 */

import { BAR_LABEL, type MathSymbol } from "./types";

/** Ink is anything darker than this on the white pad. */
const INK_THRESHOLD = 200;
/** A component this much wider than tall is a bar rather than a glyph. */
const BAR_ASPECT = 3.0;
/** Two bars stacked this closely, sharing an x-span, form an equals sign. */
const EQUALS_GAP_RATIO = 1.6;
const EQUALS_OVERLAP = 0.6;

type Component = { x: number; y: number; w: number; h: number; pixels: number };

async function toImageData(imageBase64: string): Promise<ImageData | null> {
  if (typeof document === "undefined") return null;
  const src = imageBase64.startsWith("data:")
    ? imageBase64
    : `data:image/jpeg;base64,${imageBase64}`;

  const image = await new Promise<HTMLImageElement | null>((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
  if (!image) return null;

  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(image, 0, 0);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

/** Connected components of ink pixels, 8-connected, iterative flood fill. */
function findComponents(image: ImageData): Component[] {
  const { width, height, data } = image;
  const seen = new Uint8Array(width * height);
  const isInk = (i: number) => data[i * 4] < INK_THRESHOLD && data[i * 4 + 3] > 32;
  const components: Component[] = [];
  const stack: number[] = [];

  for (let start = 0; start < width * height; start += 1) {
    if (seen[start] || !isInk(start)) continue;

    let minX = width;
    let minY = height;
    let maxX = 0;
    let maxY = 0;
    let pixels = 0;

    stack.push(start);
    seen[start] = 1;

    while (stack.length) {
      const idx = stack.pop() as number;
      const x = idx % width;
      const y = (idx - x) / width;
      pixels += 1;
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;

      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const n = ny * width + nx;
          if (seen[n] || !isInk(n)) continue;
          seen[n] = 1;
          stack.push(n);
        }
      }
    }

    components.push({ x: minX, y: minY, w: maxX - minX + 1, h: maxY - minY + 1, pixels });
  }

  return components;
}

/** Horizontal-stroke components, with stacked pairs merged into "=". */
export function barsFromComponents(components: Component[]): MathSymbol[] {
  const noise = components.length ? Math.max(2, Math.round(median(components.map((c) => c.h)) * 0.12)) : 2;
  const bars = components
    .filter((c) => c.pixels > noise && c.w >= c.h * BAR_ASPECT)
    .map((c) => ({ label: BAR_LABEL, x: c.x, y: c.y, w: c.w, h: c.h }))
    .sort((a, b) => a.y - b.y);

  const out: MathSymbol[] = [];
  const used = new Set<number>();

  for (let i = 0; i < bars.length; i += 1) {
    if (used.has(i)) continue;
    const a = bars[i];
    let paired = false;

    for (let j = i + 1; j < bars.length; j += 1) {
      if (used.has(j)) continue;
      const b = bars[j];
      const overlap =
        Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const shared = overlap / Math.min(a.w, b.w);
      const gap = b.y - (a.y + a.h);
      if (shared >= EQUALS_OVERLAP && gap >= 0 && gap <= Math.max(a.h, b.h) * EQUALS_GAP_RATIO * 2) {
        out.push({
          label: "=",
          x: Math.min(a.x, b.x),
          y: a.y,
          w: Math.max(a.x + a.w, b.x + b.w) - Math.min(a.x, b.x),
          h: b.y + b.h - a.y,
        });
        used.add(i);
        used.add(j);
        paired = true;
        break;
      }
    }

    if (!paired) {
      out.push(a);
      used.add(i);
    }
  }

  return out;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Bars and equals signs found in the ink image. Empty outside the browser. */
export async function findBars(imageBase64: string): Promise<MathSymbol[]> {
  const image = await toImageData(imageBase64);
  if (!image) return [];
  return barsFromComponents(findComponents(image));
}
