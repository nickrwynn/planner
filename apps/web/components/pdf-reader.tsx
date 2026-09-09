"use client";

import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, TextLayer } from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

if (typeof window !== "undefined") {
  GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
}

type PdfReaderProps = {
  /** Raw PDF bytes. Prefer this over blob URLs — pdf.js workers often fail on blob: fetches. */
  data: ArrayBuffer;
  page: number;
  scale: number;
  highlightQuery?: string;
  onPageCount?: (n: number) => void;
  onTextSelect?: (payload: { text: string; x: number; y: number }) => void;
  onClearSelect?: () => void;
};

function caretRangeFromPoint(x: number, y: number): Range | null {
  const doc = document as Document & {
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
    caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
  };
  if (typeof doc.caretRangeFromPoint === "function") {
    return doc.caretRangeFromPoint(x, y);
  }
  const pos = doc.caretPositionFromPoint?.(x, y);
  if (!pos) return null;
  const range = document.createRange();
  range.setStart(pos.offsetNode, pos.offset);
  range.collapse(true);
  return range;
}

function expandRangeToWord(range: Range): Range {
  const node = range.startContainer;
  if (node.nodeType !== Node.TEXT_NODE || !node.textContent) return range;
  const text = node.textContent;
  let start = range.startOffset;
  let end = range.startOffset;
  while (start > 0 && /[\w’']/.test(text[start - 1] || "")) start -= 1;
  while (end < text.length && /[\w’']/.test(text[end] || "")) end += 1;
  const next = document.createRange();
  next.setStart(node, start);
  next.setEnd(node, end);
  return next;
}

export function PdfReader({
  data,
  page,
  scale,
  highlightQuery,
  onPageCount,
  onTextSelect,
  onClearSelect,
}: PdfReaderProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textLayerRef = useRef<HTMLDivElement | null>(null);
  const onPageCountRef = useRef(onPageCount);
  onPageCountRef.current = onPageCount;
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);

  const selectingRef = useRef(false);
  const anchorRangeRef = useRef<Range | null>(null);
  const lastTapRef = useRef<{ t: number; x: number; y: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setDoc(null);
    setError(null);
    async function load() {
      try {
        const copy = data.slice(0);
        const loadingTask = getDocument({ data: copy });
        loaded = await loadingTask.promise;
        if (cancelled) {
          await loaded.destroy();
          return;
        }
        setDoc(loaded);
        onPageCountRef.current?.(loaded.numPages);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load PDF");
      }
    }
    void load();
    return () => {
      cancelled = true;
      void loaded?.destroy();
    };
  }, [data]);

  useEffect(() => {
    if (!doc || !canvasRef.current || !textLayerRef.current) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    let textLayer: TextLayer | null = null;

    async function renderPage() {
      setRendering(true);
      try {
        const pdfPage = await doc!.getPage(page);
        if (cancelled) return;
        const viewport = pdfPage.getViewport({ scale });
        const canvas = canvasRef.current!;
        const textLayerDiv = textLayerRef.current!;
        const context = canvas.getContext("2d");
        if (!context) return;

        const outputScale = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        textLayerDiv.style.width = `${Math.floor(viewport.width)}px`;
        textLayerDiv.style.height = `${Math.floor(viewport.height)}px`;
        textLayerDiv.innerHTML = "";

        const transform = outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;
        renderTask = pdfPage.render({
          canvasContext: context,
          viewport,
          transform,
        });
        await renderTask.promise;
        if (cancelled) return;

        const textContent = await pdfPage.getTextContent();
        if (cancelled) return;
        textLayer = new TextLayer({
          textContentSource: textContent,
          container: textLayerDiv,
          viewport,
        });
        await textLayer.render();
      } catch (e) {
        const name = e instanceof Error ? e.name : "";
        if (!cancelled && name !== "RenderingCancelledException") {
          setError(e instanceof Error ? e.message : "Failed to render page");
        }
      } finally {
        if (!cancelled) setRendering(false);
      }
    }

    void renderPage();
    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [doc, page, scale]);

  useEffect(() => {
    const root = textLayerRef.current;
    if (!root) return;
    const q = (highlightQuery || "").trim().toLowerCase();
    root.querySelectorAll("span").forEach((span) => {
      const text = (span.textContent || "").toLowerCase();
      if (q && text.includes(q)) span.classList.add("pdfFindMatch");
      else span.classList.remove("pdfFindMatch");
    });
  }, [highlightQuery, page, rendering]);

  function emitSelection(clientX: number, clientY: number) {
    const sel = window.getSelection()?.toString().trim() || "";
    if (!sel) {
      onClearSelect?.();
      return;
    }
    onTextSelect?.({ text: sel, x: clientX, y: clientY });
  }

  function onPointerDown(e: React.PointerEvent) {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const now = Date.now();
    const last = lastTapRef.current;
    const isDoubleTap =
      !!last && now - last.t < 320 && Math.hypot(e.clientX - last.x, e.clientY - last.y) < 28;

    lastTapRef.current = { t: now, x: e.clientX, y: e.clientY };

    if (!isDoubleTap) return;

    e.preventDefault();
    const caret = caretRangeFromPoint(e.clientX, e.clientY);
    if (!caret) return;
    const word = expandRangeToWord(caret);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(word);
    anchorRangeRef.current = word.cloneRange();
    selectingRef.current = true;
    textLayerRef.current?.classList.add("isSelecting");
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!selectingRef.current || !anchorRangeRef.current) return;
    const caret = caretRangeFromPoint(e.clientX, e.clientY);
    if (!caret) return;
    const selection = window.getSelection();
    if (!selection) return;
    try {
      const next = document.createRange();
      const anchor = anchorRangeRef.current;
      const cmp = anchor.compareBoundaryPoints(Range.START_TO_START, caret);
      if (cmp <= 0) {
        next.setStart(anchor.startContainer, anchor.startOffset);
        next.setEnd(caret.startContainer, caret.startOffset);
      } else {
        next.setStart(caret.startContainer, caret.startOffset);
        next.setEnd(anchor.endContainer, anchor.endOffset);
      }
      selection.removeAllRanges();
      selection.addRange(next);
    } catch {
      // ignore invalid boundary combos while dragging across nodes
    }
  }

  function endSelect(e: React.PointerEvent) {
    if (selectingRef.current) {
      selectingRef.current = false;
      anchorRangeRef.current = null;
      textLayerRef.current?.classList.remove("isSelecting");
      emitSelection(e.clientX, e.clientY);
      return;
    }
    // Mouse drag / native selection fallback
    if (e.pointerType === "mouse") {
      emitSelection(e.clientX, e.clientY);
    }
  }

  if (error) {
    return (
      <div className="studyPdfError">
        Couldn’t render PDF ({error}). Try another browser, or use a text fallback in the sidebar.
      </div>
    );
  }

  return (
    <div
      className="studyPdfStage"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endSelect}
      onPointerCancel={endSelect}
    >
      <div className="studyPdfPage">
        {rendering ? <div className="studyPdfLoading">Rendering page…</div> : null}
        <canvas ref={canvasRef} className="studyPdfCanvas" />
        <div ref={textLayerRef} className="textLayer" />
      </div>
    </div>
  );
}
