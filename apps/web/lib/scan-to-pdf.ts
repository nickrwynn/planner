/** Build a multi-page PDF from JPEG page images (no external PDF deps). */

function enc(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

export type ScanPage = {
  jpeg: Uint8Array;
  width: number;
  height: number;
};

export async function imageFileToScanPage(file: Blob, maxSide = 1600): Promise<ScanPage> {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas unavailable");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(bitmap, 0, 0, width, height);
    const img = ctx.getImageData(0, 0, width, height);
    const d = img.data;
    const contrast = 1.12;
    const intercept = 128 * (1 - contrast);
    for (let i = 0; i < d.length; i += 4) {
      d[i] = Math.min(255, Math.max(0, d[i] * contrast + intercept));
      d[i + 1] = Math.min(255, Math.max(0, d[i + 1] * contrast + intercept));
      d[i + 2] = Math.min(255, Math.max(0, d[i + 2] * contrast + intercept));
    }
    ctx.putImageData(img, 0, 0);
    const blob: Blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("JPEG encode failed"))), "image/jpeg", 0.88);
    });
    return { jpeg: new Uint8Array(await blob.arrayBuffer()), width, height };
  } finally {
    bitmap.close();
  }
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

export async function filesToScanPdf(files: Blob[], title = "Scan"): Promise<File> {
  const pages: ScanPage[] = [];
  for (const file of files) {
    pages.push(await imageFileToScanPage(file));
  }
  const pdf = buildPdfFromScanPages(pages);
  const safe = title.replace(/[^\w\- ]+/g, "").trim() || "Scan";
  return new File([pdf], `${safe}.pdf`, { type: "application/pdf" });
}
