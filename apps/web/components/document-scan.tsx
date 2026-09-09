"use client";

import { useRef, useState } from "react";
import { filesToScanPdf } from "../lib/scan-to-pdf";

type DocumentScanProps = {
  disabled?: boolean;
  onPdfReady: (file: File) => Promise<void> | void;
};

export function DocumentScan({ disabled, onPdfReady }: DocumentScanProps) {
  const cameraRef = useRef<HTMLInputElement | null>(null);
  const libraryRef = useRef<HTMLInputElement | null>(null);
  const [pages, setPages] = useState<{ url: string; file: File }[]>([]);
  const [title, setTitle] = useState("Scan");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function clearPages() {
    for (const p of pages) URL.revokeObjectURL(p.url);
    setPages([]);
  }

  async function onPick(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    const next = [...pages];
    for (const file of Array.from(files)) {
      // iOS camera often omits type or uses image/heic — still accept.
      const looksImage =
        file.type.startsWith("image/") ||
        !file.type ||
        /\.(jpe?g|png|heic|heif|webp|gif)$/i.test(file.name || "");
      if (!looksImage) continue;
      next.push({ file, url: URL.createObjectURL(file) });
    }
    if (next.length === pages.length) {
      setError("No images found in that selection.");
      return;
    }
    setPages(next);
    if (cameraRef.current) cameraRef.current.value = "";
    if (libraryRef.current) libraryRef.current.value = "";
  }

  async function makePdf() {
    if (!pages.length || busy) return;
    setBusy(true);
    setError(null);
    setProgress("Building PDF…");
    try {
      const pdf = await filesToScanPdf(
        pages.map((p) => p.file),
        title.trim() || "Scan"
      );
      setProgress("Uploading…");
      await onPdfReady(pdf);
      clearPages();
      setProgress(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build PDF");
      setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="docScan">
      <div style={{ fontWeight: 600 }}>Scan pages to PDF</div>
      <div style={{ fontSize: 13, color: "var(--muted)" }}>
        Take a photo or pick from Photos — we’ll build a PDF resource.
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          disabled={disabled || busy}
          onChange={(e) => void onPick(e.target.files)}
          style={{ display: "none" }}
        />
        <input
          ref={libraryRef}
          type="file"
          accept="image/*,.heic,.heif"
          multiple
          disabled={disabled || busy}
          onChange={(e) => void onPick(e.target.files)}
          style={{ display: "none" }}
        />
        <button type="button" disabled={disabled || busy} onClick={() => cameraRef.current?.click()}>
          Take photo
        </button>
        <button type="button" disabled={disabled || busy} onClick={() => libraryRef.current?.click()}>
          Add from Photos
        </button>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="PDF title"
          disabled={disabled || busy}
          style={{ padding: 8, minWidth: 160 }}
        />
        <button type="button" disabled={disabled || busy || pages.length === 0} onClick={() => void makePdf()}>
          {busy ? progress || "Working…" : `Create PDF (${pages.length} page${pages.length === 1 ? "" : "s"})`}
        </button>
        {pages.length > 0 ? (
          <button type="button" disabled={busy} onClick={clearPages}>
            Clear pages
          </button>
        ) : null}
      </div>
      {error ? <div style={{ color: "#f14c4c", fontSize: 13 }}>{error}</div> : null}
      {pages.length > 0 ? (
        <div className="docScanThumbs">
          {pages.map((p, idx) => (
            <div key={p.url} className="docScanThumb">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt={`Page ${idx + 1}`} />
              <span>Page {idx + 1}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
