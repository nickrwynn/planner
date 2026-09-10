/**
 * Cropping ink for recognition.
 *
 * Recognisers read a bitmap, and accuracy depends heavily on what that bitmap
 * contains. A word floating in a mostly-empty page recognises far worse than
 * the same word filling the frame, so ink is cropped to its own bounds and
 * scaled to a legible size before being handed over.
 */

export type InkBounds = { minX: number; minY: number; maxX: number; maxY: number };

export type CropRect = {
  /** Source rectangle in device pixels. */
  sx: number;
  sy: number;
  sw: number;
  sh: number;
  /** Destination size in device pixels. */
  dw: number;
  dh: number;
};

/** Widest edge handed to a recogniser; beyond this costs time for no accuracy. */
const MAX_SIDE = 1024;
/** Ink shorter than this is scaled up, since small glyphs recognise badly. */
const TARGET_HEIGHT = 240;

/**
 * Grow ink bounds to include a new point. Accumulating bounds while drawing
 * avoids scanning every pixel of the canvas to find the ink afterwards.
 */
export function growBounds(bounds: InkBounds | null, x: number, y: number): InkBounds {
  if (!bounds) return { minX: x, minY: y, maxX: x, maxY: y };
  return {
    minX: Math.min(bounds.minX, x),
    minY: Math.min(bounds.minY, y),
    maxX: Math.max(bounds.maxX, x),
    maxY: Math.max(bounds.maxY, y),
  };
}

/**
 * Source and destination rectangles for the crop.
 *
 * `bounds` are in CSS pixels (as reported by pointer events) while the canvas
 * backing store is in device pixels, hence the `dpr` conversion.
 */
export function cropRect(
  bounds: InkBounds,
  canvasWidth: number,
  canvasHeight: number,
  dpr: number,
  strokeWidth: number
): CropRect | null {
  // Pad past the stroke centre-line so round caps aren't sliced off.
  const pad = 12 + strokeWidth;
  const sx = Math.max(0, Math.floor((bounds.minX - pad) * dpr));
  const sy = Math.max(0, Math.floor((bounds.minY - pad) * dpr));
  const right = Math.min(canvasWidth, Math.ceil((bounds.maxX + pad) * dpr));
  const bottom = Math.min(canvasHeight, Math.ceil((bounds.maxY + pad) * dpr));
  const sw = right - sx;
  const sh = bottom - sy;
  if (sw < 2 || sh < 2) return null;

  const scale = Math.min(MAX_SIDE / Math.max(sw, sh), Math.max(1, TARGET_HEIGHT / sh));
  return {
    sx,
    sy,
    sw,
    sh,
    dw: Math.max(1, Math.round(sw * scale)),
    dh: Math.max(1, Math.round(sh * scale)),
  };
}

/**
 * Ink cropped onto a white background, as a PNG data URL.
 *
 * PNG rather than JPEG: strokes are a couple of pixels wide, and JPEG ringing
 * around them measurably hurts recognition while saving nothing on line art.
 */
export function cropInkToDataUrl(
  canvas: HTMLCanvasElement,
  bounds: InkBounds,
  dpr: number,
  strokeWidth: number
): string | null {
  const rect = cropRect(bounds, canvas.width, canvas.height, dpr, strokeWidth);
  if (!rect) return null;
  const out = document.createElement("canvas");
  out.width = rect.dw;
  out.height = rect.dh;
  const ctx = out.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, rect.dw, rect.dh);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(canvas, rect.sx, rect.sy, rect.sw, rect.sh, 0, 0, rect.dw, rect.dh);
  return out.toDataURL("image/png");
}
