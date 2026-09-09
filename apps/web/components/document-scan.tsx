"use client";

import { useRef, useState } from "react";
import { filesToScanPdf } from "../lib/scan-to-pdf";

type DocumentScanProps = {
  disabled?: boolean;
  onPdfReady: (file: File) => Promise<void> | void;
};

export function DocumentScan({ disabled, onPdfReady }: DocumentScanProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [pages, setPages] = useState<{ url: string; file: File }[]>([]);
  const [title, setTitle] = useState("Scan");
  const [busy, setBusy] = useState(false);
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
      if (!file.type.startsWith("image/")) continue;
      next.push({ file, url: URL.createObjectURL(file) });
    }
    setPages(next);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function makePdf() {
    if (!pages.length || busy) return;
    setBusy(true);
    setError(null);
    try {
      const pdf = await filesToScanPdf(
        pages.map((p) => p.file),
        title.trim() || "Scan"
      );
      await onPdfReady(pdf);
      clearPages();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build PDF");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="docScan">
      <div style={{ fontWeight: 600 }}>Scan pages to PDF</div>
      <div style={{ fontSize: 13, color: "var(--muted)" }}>
        Take photos of worksheets, notes, or textbooks — we’ll build a PDF resource (Adobe Scan style).
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          disabled={disabled || busy}
          onChange={(e) => void onPick(e.target.files)}
        />
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="PDF title"
          disabled={disabled || busy}
          style={{ padding: 8, minWidth: 160 }}
        />
        <button type="button" disabled={disabled || busy || pages.length === 0} onClick={() => void makePdf()}>
          {busy ? "Building PDF…" : `Create PDF (${pages.length} page${pages.length === 1 ? "" : "s"})`}
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
