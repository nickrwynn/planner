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
  onTextSelect?: (payload: { text: string; x: number; y: number; showMenu?: boolean }) => void;
  onClearSelect?: () => void;
};

const HOLD_TO_START_MS = 350;
const HOLD_FOR_MENU_MS = 400;
const MOVE_CANCEL_PX = 28;

function nativeCaretRange(x: number, y: number): Range | null {
  const doc = document as Document & {
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
    caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
  };
  if (typeof doc.caretRangeFromPoint === "function") {
    const range = doc.caretRangeFromPoint(x, y);
    if (!range) return null;
    if (range.startContainer.nodeType === Node.TEXT_NODE) return range;
    // PDF spans sometimes return the element — walk into its text.
    const el = range.startContainer as Element;
    const text = el.nodeType === Node.ELEMENT_NODE ? el.childNodes[0] : null;
    if (text && text.nodeType === Node.TEXT_NODE) {
      const next = document.createRange();
      const len = text.textContent?.length ?? 0;
      next.setStart(text, Math.min(range.startOffset, len));
      next.collapse(true);
      return next;
    }
    return null;
  }
  const pos = doc.caretPositionFromPoint?.(x, y);
  if (!pos || pos.offsetNode.nodeType !== Node.TEXT_NODE) return null;
  const range = document.createRange();
  range.setStart(pos.offsetNode, pos.offset);
  range.collapse(true);
  return range;
}

/** Binary-search character offset inside a text node for an x position on one line. */
function offsetForXInTextNode(textNode: Node, x: number, y: number): number {
  const text = textNode.textContent || "";
  if (!text.length) return 0;
  let lo = 0;
  let hi = text.length;
  const probe = document.createRange();
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    probe.setStart(textNode, mid);
    probe.setEnd(textNode, Math.min(mid + 1, text.length));
    const rect = probe.getBoundingClientRect();
    if (!rect.width && !rect.height) {
      hi = mid;
      continue;
    }
    // Prefer the glyph whose vertical band contains y when possible.
    const midX = rect.left + rect.width / 2;
    if (x > midX) lo = mid + 1;
    else hi = mid;
  }
  // Nudge: if we're past the last glyph center, clamp to end.
  if (lo >= text.length) return text.length;
  probe.setStart(textNode, lo);
  probe.setEnd(textNode, Math.min(lo + 1, text.length));
  const r = probe.getBoundingClientRect();
  if (r.width && x > r.left + r.width * 0.65) {
    return Math.min(lo + 1, text.length);
  }
  void y;
  return lo;
}

/**
 * Robust caret for pdf.js text layers: native caret, then nearby probes,
 * then nearest span by geometry (gaps between glyphs kill caretRangeFromPoint).
 */
function caretInTextLayer(x: number, y: number, root: HTMLElement | null): Range | null {
  const probes: Array<[number, number]> = [
    [x, y],
    [x, y - 6],
    [x, y + 6],
    [x - 8, y],
    [x + 8, y],
    [x - 14, y],
    [x + 14, y],
    [x, y - 14],
    [x, y + 14],
  ];
  for (const [px, py] of probes) {
    const hit = nativeCaretRange(px, py);
    if (!hit) continue;
    if (root && !root.contains(hit.startContainer)) continue;
    return hit;
  }
  if (!root) return null;

  let best: { dist: number; range: Range } | null = null;
  const spans = root.querySelectorAll("span");
  for (const span of spans) {
    if (!span.firstChild || span.firstChild.nodeType !== Node.TEXT_NODE) continue;
    const textNode = span.firstChild;
    for (const rect of Array.from(span.getClientRects())) {
      if (rect.width < 1 && rect.height < 1) continue;
      const dx = x < rect.left ? rect.left - x : x > rect.right ? x - rect.right : 0;
      const dy = y < rect.top ? rect.top - y : y > rect.bottom ? y - rect.bottom : 0;
      const dist = Math.hypot(dx, dy);
      if (dist > 64) continue;
      const clampedX = Math.min(Math.max(x, rect.left), rect.right);
      const offset = offsetForXInTextNode(textNode, clampedX, y);
      const range = document.createRange();
      range.setStart(textNode, offset);
      range.collapse(true);
      if (!best || dist < best.dist) best = { dist, range };
    }
  }
  return best?.range ?? null;
}

function pointInClientRects(x: number, y: number, rects: DOMRectList | DOMRect[]): boolean {
  for (const rect of Array.from(rects)) {
    if (x >= rect.left - 6 && x <= rect.right + 6 && y >= rect.top - 6 && y <= rect.bottom + 6) {
      return true;
    }
  }
  return false;
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

  const stageRef = useRef<HTMLDivElement | null>(null);
  const highlightRef = useRef<HTMLDivElement | null>(null);
  const caretRef = useRef<HTMLDivElement | null>(null);

  /** idle | press | selecting | selected | menu_press */
  const modeRef = useRef<"idle" | "press" | "selecting" | "selected" | "menu_press">("idle");
  const anchorRangeRef = useRef<Range | null>(null);
  const selectedRangeRef = useRef<Range | null>(null);
  const pressOriginRef = useRef<{ x: number; y: number } | null>(null);
  const holdTimerRef = useRef<number | null>(null);
  const activePointerRef = useRef<number | null>(null);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);
  const rafRef = useRef<number | null>(null);

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

  function clearHoldTimer() {
    if (holdTimerRef.current != null) {
      window.clearTimeout(holdTimerRef.current);
      holdTimerRef.current = null;
    }
  }

  function hideCaret() {
    if (caretRef.current) caretRef.current.style.display = "none";
  }

  function showCaretAt(clientX: number, clientY: number) {
    const caret = caretRef.current;
    const pageEl = stageRef.current?.querySelector(".studyPdfPage") as HTMLElement | null;
    if (!caret || !pageEl) return;
    const pageRect = pageEl.getBoundingClientRect();
    caret.style.display = "block";
    caret.style.left = `${clientX - pageRect.left}px`;
    caret.style.top = `${clientY - pageRect.top - 12}px`;
    caret.style.height = "24px";
  }

  function clearSelectionHighlight() {
    if (highlightRef.current) highlightRef.current.innerHTML = "";
  }

  function paintSelectionHighlight(range?: Range | null) {
    const layer = highlightRef.current;
    const pageEl = stageRef.current?.querySelector(".studyPdfPage") as HTMLElement | null;
    if (!layer || !pageEl) return;
    layer.innerHTML = "";
    const active =
      range ||
      selectedRangeRef.current ||
      (window.getSelection() && window.getSelection()!.rangeCount
        ? window.getSelection()!.getRangeAt(0)
        : null);
    if (!active || active.collapsed) return;
    const pageRect = pageEl.getBoundingClientRect();
    for (const rect of Array.from(active.getClientRects())) {
      if (rect.width < 0.5 || rect.height < 0.5) continue;
      const mark = document.createElement("div");
      mark.className = "pdfSelMark";
      mark.style.left = `${rect.left - pageRect.left}px`;
      mark.style.top = `${rect.top - pageRect.top}px`;
      mark.style.width = `${rect.width}px`;
      mark.style.height = `${rect.height}px`;
      layer.appendChild(mark);
    }
  }

  function resetSelectionUi() {
    clearHoldTimer();
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    modeRef.current = "idle";
    anchorRangeRef.current = null;
    selectedRangeRef.current = null;
    pressOriginRef.current = null;
    activePointerRef.current = null;
    lastPointRef.current = null;
    hideCaret();
    clearSelectionHighlight();
    textLayerRef.current?.classList.remove("isSelecting", "hasSelection");
    window.getSelection()?.removeAllRanges();
  }

  useEffect(() => {
    if (!doc || !canvasRef.current || !textLayerRef.current) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    let textLayer: TextLayer | null = null;
    resetSelectionUi();
    onClearSelectRef.current?.();

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  function beginSelectAt(clientX: number, clientY: number, pointerId: number) {
    const caret = caretInTextLayer(clientX, clientY, textLayerRef.current);
    if (!caret) return false;
    const anchor = caret.cloneRange();
    anchor.collapse(true);
    anchorRangeRef.current = anchor;
    selectedRangeRef.current = null;
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(anchor);
    modeRef.current = "selecting";
    textLayerRef.current?.classList.add("isSelecting");
    textLayerRef.current?.classList.remove("hasSelection");
    showCaretAt(clientX, clientY);
    clearSelectionHighlight();
    try {
      stageRef.current?.setPointerCapture(pointerId);
    } catch {
      // ignore
    }
    return true;
  }

  function applyRangeFromAnchorToPoint(clientX: number, clientY: number) {
    const anchor = anchorRangeRef.current;
    if (!anchor) return;
    const caret = caretInTextLayer(clientX, clientY, textLayerRef.current);
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
        next.setEnd(anchor.startContainer, anchor.startOffset);
      }
      selection.removeAllRanges();
      selection.addRange(next);
      selectedRangeRef.current = next.cloneRange();
      paintSelectionHighlight(next);
      if (!next.collapsed) hideCaret();
    } catch {
      // ignore invalid boundary combos while dragging across nodes
    }
  }

  function scheduleSelectUpdate(clientX: number, clientY: number) {
    lastPointRef.current = { x: clientX, y: clientY };
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const pt = lastPointRef.current;
      if (!pt || modeRef.current !== "selecting") return;
      applyRangeFromAnchorToPoint(pt.x, pt.y);
    });
  }

  function finalizeSelection(clientX: number, clientY: number) {
    applyRangeFromAnchorToPoint(clientX, clientY);
    const sel = window.getSelection();
    const text = (selectedRangeRef.current?.toString() || sel?.toString() || "").trim();
    hideCaret();
    textLayerRef.current?.classList.remove("isSelecting");
    if (!text) {
      resetSelectionUi();
      onClearSelectRef.current?.();
      return;
    }
    if (selectedRangeRef.current) {
      sel?.removeAllRanges();
      sel?.addRange(selectedRangeRef.current);
    }
    modeRef.current = "selected";
    textLayerRef.current?.classList.add("hasSelection");
    paintSelectionHighlight(selectedRangeRef.current);
    onTextSelectRef.current?.({ text, x: clientX, y: clientY, showMenu: false });
  }

  function openMenuAt(clientX: number, clientY: number) {
    const text = (selectedRangeRef.current?.toString() || window.getSelection()?.toString() || "").trim();
    if (!text) return;
    modeRef.current = "selected";
    onTextSelectRef.current?.({ text, x: clientX, y: clientY, showMenu: true });
  }

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const onPointerDown = (e: PointerEvent) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      if (!(e.target as HTMLElement | null)?.closest?.(".studyPdfPage")) return;

      e.preventDefault();
      e.stopPropagation();
      activePointerRef.current = e.pointerId;
      pressOriginRef.current = { x: e.clientX, y: e.clientY };
      lastPointRef.current = { x: e.clientX, y: e.clientY };
      clearHoldTimer();

      if (modeRef.current === "selected" && selectedRangeRef.current) {
        const rects = selectedRangeRef.current.getClientRects();
        if (pointInClientRects(e.clientX, e.clientY, rects)) {
          modeRef.current = "menu_press";
          holdTimerRef.current = window.setTimeout(() => {
            holdTimerRef.current = null;
            openMenuAt(e.clientX, e.clientY);
            modeRef.current = "selected";
          }, HOLD_FOR_MENU_MS);
          return;
        }
        resetSelectionUi();
        onClearSelectRef.current?.();
      }

      modeRef.current = "press";
      holdTimerRef.current = window.setTimeout(() => {
        holdTimerRef.current = null;
        const origin = pressOriginRef.current;
        if (!origin || activePointerRef.current !== e.pointerId) return;
        if (!beginSelectAt(origin.x, origin.y, e.pointerId)) {
          // Retry at latest finger position (may have drifted slightly during hold).
          const latest = lastPointRef.current || origin;
          beginSelectAt(latest.x, latest.y, e.pointerId);
        }
      }, HOLD_TO_START_MS);
    };

    const onPointerMove = (e: PointerEvent) => {
      if (activePointerRef.current !== e.pointerId) return;
      lastPointRef.current = { x: e.clientX, y: e.clientY };
      const origin = pressOriginRef.current;
      const dist = origin ? Math.hypot(e.clientX - origin.x, e.clientY - origin.y) : 0;

      if (modeRef.current === "press") {
        // Only cancel hold if this looks like a scroll, not a tiny tremor.
        if (dist > MOVE_CANCEL_PX) {
          clearHoldTimer();
          modeRef.current = "idle";
          activePointerRef.current = null;
        }
        return;
      }

      if (modeRef.current === "menu_press") {
        if (dist > MOVE_CANCEL_PX) {
          clearHoldTimer();
          modeRef.current = "selected";
        }
        return;
      }

      if (modeRef.current === "selecting") {
        e.preventDefault();
        scheduleSelectUpdate(e.clientX, e.clientY);
      }
    };

    const onPointerUp = (e: PointerEvent) => {
      if (activePointerRef.current !== null && activePointerRef.current !== e.pointerId) return;
      clearHoldTimer();

      if (modeRef.current === "selecting") {
        e.preventDefault();
        finalizeSelection(e.clientX, e.clientY);
        activePointerRef.current = null;
        pressOriginRef.current = null;
        try {
          stage.releasePointerCapture(e.pointerId);
        } catch {
          // ignore
        }
        return;
      }

      if (modeRef.current === "menu_press") {
        modeRef.current = "selected";
        activePointerRef.current = null;
        pressOriginRef.current = null;
        return;
      }

      if (modeRef.current === "press") {
        modeRef.current = "idle";
        activePointerRef.current = null;
        pressOriginRef.current = null;
        return;
      }

      activePointerRef.current = null;
      pressOriginRef.current = null;
    };

    const block = (ev: Event) => ev.preventDefault();
    const opts: AddEventListenerOptions = { capture: true, passive: false };
    stage.addEventListener("pointerdown", onPointerDown, opts);
    stage.addEventListener("pointermove", onPointerMove, opts);
    stage.addEventListener("pointerup", onPointerUp, opts);
    stage.addEventListener("pointercancel", onPointerUp, opts);
    stage.addEventListener("contextmenu", block, opts);
    stage.addEventListener("selectstart", block, opts);

    return () => {
      clearHoldTimer();
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      stage.removeEventListener("pointerdown", onPointerDown, opts);
      stage.removeEventListener("pointermove", onPointerMove, opts);
      stage.removeEventListener("pointerup", onPointerUp, opts);
      stage.removeEventListener("pointercancel", onPointerUp, opts);
      stage.removeEventListener("contextmenu", block, opts);
      stage.removeEventListener("selectstart", block, opts);
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
        <div ref={caretRef} className="pdfCaret" aria-hidden />
        <div ref={textLayerRef} className="textLayer" />
      </div>
      <div className="pdfSelectHint">
        Hold to place start · drag across text · hold the highlight for actions
      </div>
    </div>
  );
}
