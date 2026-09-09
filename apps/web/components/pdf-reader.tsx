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
  /** After double-tap word select, stay ready to drag-extend (pointerup must not clear this). */
  const extendArmedRef = useRef(false);
  const anchorRangeRef = useRef<Range | null>(null);
  const lastTapRef = useRef<{ t: number; x: number; y: number } | null>(null);
  const dragOriginRef = useRef<{ x: number; y: number } | null>(null);
  const didDragRef = useRef(false);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const highlightRef = useRef<HTMLDivElement | null>(null);
  const onTextSelectRef = useRef(onTextSelect);
  const onClearSelectRef = useRef(onClearSelect);
  onTextSelectRef.current = onTextSelect;
  onClearSelectRef.current = onClearSelect;

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
    clearSelectionHighlight();
    clearExtendMode();
    window.getSelection()?.removeAllRanges();

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
      onClearSelectRef.current?.();
      return;
    }
    onTextSelectRef.current?.({ text: sel, x: clientX, y: clientY });
  }

  function paintSelectionHighlight() {
    const layer = highlightRef.current;
    const page = stageRef.current?.querySelector(".studyPdfPage") as HTMLElement | null;
    if (!layer || !page) return;
    layer.innerHTML = "";
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
    const range = sel.getRangeAt(0);
    const pageRect = page.getBoundingClientRect();
    for (const rect of Array.from(range.getClientRects())) {
      if (rect.width < 1 || rect.height < 1) continue;
      const mark = document.createElement("div");
      mark.className = "pdfSelMark";
      mark.style.left = `${rect.left - pageRect.left}px`;
      mark.style.top = `${rect.top - pageRect.top}px`;
      mark.style.width = `${rect.width}px`;
      mark.style.height = `${rect.height}px`;
      layer.appendChild(mark);
    }
  }

  function clearSelectionHighlight() {
    if (highlightRef.current) highlightRef.current.innerHTML = "";
  }

  function applyRangeFromAnchorToPoint(clientX: number, clientY: number) {
    const anchor = anchorRangeRef.current;
    if (!anchor) return;
    const caret = caretRangeFromPoint(clientX, clientY);
    if (!caret) return;
    const selection = window.getSelection();
    if (!selection) return;
    try {
      const next = document.createRange();
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
      paintSelectionHighlight();
    } catch {
      // ignore invalid boundary combos while dragging across nodes
    }
  }

  function clearExtendMode() {
    selectingRef.current = false;
    extendArmedRef.current = false;
    anchorRangeRef.current = null;
    dragOriginRef.current = null;
    didDragRef.current = false;
    textLayerRef.current?.classList.remove("isSelecting", "isExtendArmed");
  }

  function selectWordAt(clientX: number, clientY: number): boolean {
    const caret = caretRangeFromPoint(clientX, clientY);
    if (!caret) return false;
    const word = expandRangeToWord(caret);
    if (!word.toString().trim()) return false;
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(word);
    anchorRangeRef.current = word.cloneRange();
    paintSelectionHighlight();
    return true;
  }

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      if (!(e.target as HTMLElement | null)?.closest?.(".studyPdfPage")) return;

      const now = Date.now();
      const last = lastTapRef.current;
      const isDoubleTap =
        !!last && now - last.t < 350 && Math.hypot(e.clientX - last.x, e.clientY - last.y) < 32;
      lastTapRef.current = { t: now, x: e.clientX, y: e.clientY };

      // Already armed from double-tap: this press starts the drag-extend.
      if (extendArmedRef.current && anchorRangeRef.current && !isDoubleTap) {
        e.preventDefault();
        e.stopPropagation();
        selectingRef.current = true;
        didDragRef.current = false;
        dragOriginRef.current = { x: e.clientX, y: e.clientY };
        textLayerRef.current?.classList.add("isSelecting");
        try {
          stage.setPointerCapture(e.pointerId);
        } catch {
          // ignore
        }
        applyRangeFromAnchorToPoint(e.clientX, e.clientY);
        return;
      }

      if (!isDoubleTap) {
        // Single tap clears a prior unused extend arm (tap elsewhere).
        if (extendArmedRef.current) {
          clearExtendMode();
          clearSelectionHighlight();
          window.getSelection()?.removeAllRanges();
          onClearSelectRef.current?.();
        }
        return;
      }

      // Double-tap: select the word and arm extend. Do NOT require continuous press.
      e.preventDefault();
      e.stopPropagation();
      if (!selectWordAt(e.clientX, e.clientY)) return;
      selectingRef.current = true;
      extendArmedRef.current = true;
      didDragRef.current = false;
      dragOriginRef.current = { x: e.clientX, y: e.clientY };
      textLayerRef.current?.classList.add("isSelecting", "isExtendArmed");
      try {
        stage.setPointerCapture(e.pointerId);
      } catch {
        // ignore
      }
      emitSelection(e.clientX, e.clientY);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!selectingRef.current || !anchorRangeRef.current) return;
      e.preventDefault();
      const origin = dragOriginRef.current;
      if (origin && Math.hypot(e.clientX - origin.x, e.clientY - origin.y) > 6) {
        didDragRef.current = true;
      }
      applyRangeFromAnchorToPoint(e.clientX, e.clientY);
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!selectingRef.current) return;
      e.preventDefault();

      // Double-tap lift with no drag: keep the word selected and stay armed for the next drag.
      if (extendArmedRef.current && !didDragRef.current) {
        selectingRef.current = false;
        dragOriginRef.current = null;
        textLayerRef.current?.classList.remove("isSelecting");
        textLayerRef.current?.classList.add("isExtendArmed");
        paintSelectionHighlight();
        emitSelection(e.clientX, e.clientY);
        return;
      }

      paintSelectionHighlight();
      emitSelection(e.clientX, e.clientY);
      // Keep highlight visible after drag; clear arm so a tap dismisses.
      selectingRef.current = false;
      extendArmedRef.current = true;
      dragOriginRef.current = null;
      didDragRef.current = false;
      textLayerRef.current?.classList.remove("isSelecting");
      textLayerRef.current?.classList.add("isExtendArmed");
      // Re-anchor to the full selected range so another drag continues from current selection start.
      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0) {
        const full = sel.getRangeAt(0).cloneRange();
        // Keep original word start as anchor for further extends from first double-tap word.
        // If we already have an anchor, keep its start; update end tracking via caret only.
        if (!anchorRangeRef.current) anchorRangeRef.current = full;
      }
    };

    const onContextMenu = (e: Event) => {
      e.preventDefault();
    };

    const opts: AddEventListenerOptions = { capture: true, passive: false };
    stage.addEventListener("pointerdown", onPointerDown, opts);
    stage.addEventListener("pointermove", onPointerMove, opts);
    stage.addEventListener("pointerup", onPointerUp, opts);
    stage.addEventListener("pointercancel", onPointerUp, opts);
    stage.addEventListener("contextmenu", onContextMenu, opts);
    stage.addEventListener("selectstart", onContextMenu, opts);

    return () => {
      stage.removeEventListener("pointerdown", onPointerDown, opts);
      stage.removeEventListener("pointermove", onPointerMove, opts);
      stage.removeEventListener("pointerup", onPointerUp, opts);
      stage.removeEventListener("pointercancel", onPointerUp, opts);
      stage.removeEventListener("contextmenu", onContextMenu, opts);
      stage.removeEventListener("selectstart", onContextMenu, opts);
    };
  }, []);

  if (error) {
    return (
      <div className="studyPdfError">
        Couldn’t render PDF ({error}). Try another browser, or use a text fallback in the sidebar.
      </div>
    );
  }

  return (
    <div ref={stageRef} className="studyPdfStage">
      <div className="studyPdfPage">
        {rendering ? <div className="studyPdfLoading">Rendering page…</div> : null}
        <canvas ref={canvasRef} className="studyPdfCanvas" />
        <div ref={highlightRef} className="pdfSelLayer" aria-hidden />
        <div ref={textLayerRef} className="textLayer" />
      </div>
    </div>
  );
}
