/** Build a multi-page PDF from JPEG page images (no external PDF deps). */

function enc(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

export type ScanPage = {
  jpeg: Uint8Array;
  width: number;
  height: number;
};

function canvasToJpegBlob(canvas: HTMLCanvasElement, quality = 0.82): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const fromDataUrl = () => {
      try {
        const dataUrl = canvas.toDataURL("image/jpeg", quality);
        const bin = atob(dataUrl.split(",")[1] || "");
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
        resolve(new Blob([bytes], { type: "image/jpeg" }));
      } catch (e) {
        reject(e instanceof Error ? e : new Error("JPEG encode failed"));
      }
    };

    if (typeof canvas.toBlob === "function") {
      try {
        canvas.toBlob((b) => (b ? resolve(b) : fromDataUrl()), "image/jpeg", quality);
        return;
      } catch {
        fromDataUrl();
        return;
      }
    }
    fromDataUrl();
  });
}

async function loadImageElement(file: Blob): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.decoding = "async";
    // Helps iOS decode camera/HEIC photos into something canvas can draw.
    (img as HTMLImageElement & { playsInline?: boolean }).playsInline = true;
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () =>
        reject(new Error("Could not read that photo. Try Retake, or pick a JPG/PNG from Photos."));
      img.src = url;
    });
    if (!(img.naturalWidth || img.width) || !(img.naturalHeight || img.height)) {
      throw new Error("Photo has no dimensions");
    }
    return img;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Decode via <img> (best HEIC/camera support on iPad), draw scaled to canvas.
 * Never uses getImageData() — that allocates full RGBA and crashes WKWebView on phone photos.
 */
export async function imageFileToScanPage(file: Blob, maxSide = 1280): Promise<ScanPage> {
  const img = await loadImageElement(file);
  const srcW = img.naturalWidth || img.width;
  const srcH = img.naturalHeight || img.height;
  const scale = Math.min(1, maxSide / Math.max(srcW, srcH));
  const width = Math.max(1, Math.round(srcW * scale));
  const height = Math.max(1, Math.round(srcH * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) throw new Error("Canvas unavailable");

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  try {
    ctx.filter = "contrast(1.08) brightness(1.02)";
  } catch {
    // ignore unsupported filter
  }
  ctx.drawImage(img, 0, 0, width, height);
  try {
    ctx.filter = "none";
  } catch {
    // ignore
  }

  // Detach image src to help GC on iOS.
  img.src = "";

  const blob = await canvasToJpegBlob(canvas, 0.8);
  canvas.width = 0;
  canvas.height = 0;

  return { jpeg: new Uint8Array(await blob.arrayBuffer()), width, height };
}

export function buildPdfFromScanPages(pages: ScanPage[]): Blob {
  if (!pages.length) throw new Error("Add at least one page");

  const chunks: (string | Uint8Array)[] = [];
  let offset = 0;
  const offsets: number[] = [0];

  const write = (part: string | Uint8Array) => {
    chunks.push(part);
    offset += typeof part === "string" ? enc(part).length : part.length;
  };

  const addObject = (id: number, body: (string | Uint8Array)[]) => {
    offsets[id] = offset;
    write(`${id} 0 obj\n`);
    for (const b of body) write(b);
    write(`\nendobj\n`);
  };

  write("%PDF-1.4\n%\xFF\xFF\xFF\xFF\n");

  const pageCount = pages.length;
  const pageIds: number[] = [];
  let nextId = 3;
  const meta: { pageId: number; contentId: number; imageId: number }[] = [];
  for (let i = 0; i < pageCount; i += 1) {
    const pageId = nextId++;
    const contentId = nextId++;
    const imageId = nextId++;
    pageIds.push(pageId);
    meta.push({ pageId, contentId, imageId });
  }

  addObject(1, ["<< /Type /Catalog /Pages 2 0 R >>"]);
  addObject(2, [
    `<< /Type /Pages /Count ${pageCount} /Kids [${pageIds.map((id) => `${id} 0 R`).join(" ")}] >>`,
  ]);

  for (let i = 0; i < pageCount; i += 1) {
    const page = pages[i];
    const { pageId, contentId, imageId } = meta[i];
    const w = page.width;
    const h = page.height;
    const content = `q\n${w} 0 0 ${h} 0 0 cm\n/Im${i} Do\nQ\n`;

    addObject(pageId, [
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im${i} ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>`,
    ]);
    addObject(contentId, [`<< /Length ${content.length} >>\nstream\n`, content, `endstream`]);
    addObject(imageId, [
      `<< /Type /XObject /Subtype /Image /Width ${w} /Height ${h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpeg.length} >>\nstream\n`,
      page.jpeg,
      `\nendstream`,
    ]);
  }

  const xrefStart = offset;
  const size = nextId;
  write(`xref\n0 ${size}\n`);
  write("0000000000 65535 f \n");
  for (let id = 1; id < size; id += 1) {
    write(`${String(offsets[id] ?? 0).padStart(10, "0")} 00000 n \n`);
  }
  write(`trailer\n<< /Size ${size} /Root 1 0 R >>\nstartxref\n${xrefStart}\n%%EOF\n`);

  const bytes = chunks.map((c) => (typeof c === "string" ? enc(c) : c));
  return new Blob(bytes, { type: "application/pdf" });
}

function yieldFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => resolve());
    else setTimeout(resolve, 0);
  });
}

export async function filesToScanPdf(files: Blob[], title = "Scan"): Promise<File> {
  if (!files.length) throw new Error("Add at least one page");
  const pages: ScanPage[] = [];
  for (let i = 0; i < files.length; i += 1) {
    try {
      pages.push(await imageFileToScanPage(files[i]));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to process photo";
      throw new Error(`Page ${i + 1}: ${msg}`);
    }
    await yieldFrame();
  }
  const pdf = buildPdfFromScanPages(pages);
  const safe = title.replace(/[^\w\- ]+/g, "").trim() || "Scan";
  const filename = `${safe}.pdf`;
  if (typeof File !== "undefined") {
    try {
      return new File([pdf], filename, { type: "application/pdf", lastModified: Date.now() });
    } catch {
      // fall through
    }
  }
  const named = new Blob([pdf], { type: "application/pdf" }) as Blob & { name: string };
  named.name = filename;
  return named as File;
}
