"use client";

import { useEffect, useRef, useState } from "react";
import type { HandwritingResult } from "../lib/handwriting-recognize";
import { cropInkToDataUrl, growBounds, type InkBounds } from "../lib/ink-crop";

type RecognitionSource = HandwritingResult["source"];

type InkPadProps = {
  disabled?: boolean;
  penOnly?: boolean;
  onRecognize: (
    imageBase64: string,
    mode: "text" | "math",
    session: number
  ) => Promise<RecognitionSource | null>;
};

/**
 * Which engine read the ink. Worth showing: recognition quality differs sharply
 * between them, so when a result is poor the first useful question is which one
 * produced it.
 */
const SOURCE_LABELS: Record<RecognitionSource, string> = {
  device: "Apple Vision, on device",
  cloud: "Cloud model",
  local: "Browser OCR (least accurate)",
};

/**
 * How long the pen must rest before recognition runs.
 *
 * Pauses between letters are routine, so a short delay fires mid-word and
 * recognises half a word. This waits for a real word or phrase boundary.
 */
const IDLE_MS = 700;

export function InkPad({ disabled, penOnly, onRecognize }: InkPadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recognizeSeq = useRef(0);
  const [mode, setMode] = useState<"text" | "math">("text");
  const [hasInk, setHasInk] = useState(false);
  const hasInkRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<RecognitionSource | null>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const bounds = useRef<InkBounds | null>(null);
  const dprRef = useRef(1);
  const strokeWidth = useRef(2.5);
  /** Identifies one batch of ink, so repeat passes refine instead of appending. */
  const session = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    dprRef.current = dpr;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.strokeStyle = "#111827";
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    return () => {
      if (idleTimer.current) clearTimeout(idleTimer.current);
    };
  }, []);

  function pointerPos(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  /** Grow the ink bounding box as the pen moves, so cropping stays O(1). */
  function noteInk(x: number, y: number) {
    bounds.current = growBounds(bounds.current, x, y);
  }

  function scheduleAutoRecognize() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => {
      void recognize({ auto: true });
    }, IDLE_MS);
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    if (penOnly && e.pointerType === "touch") return;
    if (idleTimer.current) clearTimeout(idleTimer.current);
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    canvas.setPointerCapture(e.pointerId);
    drawing.current = true;
    const { x, y } = pointerPos(e);
    noteInk(x, y);
    ctx.beginPath();
    ctx.moveTo(x, y);
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointerPos(e);
    noteInk(x, y);
    ctx.lineTo(x, y);
    ctx.stroke();
    hasInkRef.current = true;
    setHasInk(true);
  }

  function onPointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    drawing.current = false;
    try {
      canvasRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    scheduleAutoRecognize();
  }

  /**
   * Wipe the pad and start a new ink session, so the next result is added to
   * the field rather than replacing what this ink already produced.
   */
  function clear() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const rect = canvas.getBoundingClientRect();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    bounds.current = null;
    hasInkRef.current = false;
    setHasInk(false);
    session.current += 1;
  }

  async function recognize(opts?: { auto?: boolean }) {
    const canvas = canvasRef.current;
    if (!canvas || !hasInkRef.current || disabled) return;
    if (busy && opts?.auto) return;
    const ink = bounds.current;
    if (!ink) return;
    const seq = ++recognizeSeq.current;
    setBusy(true);
    try {
      const dataUrl = cropInkToDataUrl(canvas, ink, dprRef.current, strokeWidth.current);
      if (!dataUrl) return;
      const base64 = dataUrl.split(",")[1] || dataUrl;
      const used = await onRecognize(base64, modeRef.current, session.current);
      if (used && seq === recognizeSeq.current) setSource(used);
    } finally {
      if (seq === recognizeSeq.current) setBusy(false);
    }
  }

  /** Accept what's on the pad and clear it, ready for the next phrase. */
  async function commit() {
    await recognize();
    clear();
  }

  return (
    <div className="studyInkPad">
      <div className="studyInkToolbar">
        <span className="studySideTitle" style={{ margin: 0 }}>
          Handwriting
        </span>
        <div className="studyInkModes">
          <button
            type="button"
            className={mode === "text" ? "isActive" : ""}
            disabled={disabled}
            onClick={() => setMode("text")}
          >
            Text
          </button>
          <button
            type="button"
            className={mode === "math" ? "isActive" : ""}
            disabled={disabled}
            onClick={() => setMode("math")}
          >
            Math
          </button>
        </div>
      </div>
      <canvas
        ref={canvasRef}
        className="studyInkCanvas"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
      <div className="studySideActions">
        <button
          type="button"
          disabled={disabled || busy || !hasInk}
          onClick={() => void commit()}
          title="Keep this text and clear the pad for the next phrase"
        >
          {busy ? "Recognizing…" : "Keep & clear"}
        </button>
        <button type="button" disabled={disabled} onClick={clear}>
          Clear
        </button>
      </div>
      <div className="studySideMuted" style={{ fontSize: 12 }}>
        Recognition runs a moment after you lift the pencil, and refines the same
        text as you keep writing. Keep &amp; clear starts a new phrase.
        {source ? ` Read by: ${SOURCE_LABELS[source]}.` : ""}
      </div>
    </div>
  );
}
