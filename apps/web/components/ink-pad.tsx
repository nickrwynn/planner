"use client";

import { useEffect, useRef, useState } from "react";
type InkPadProps = {
  disabled?: boolean;
  penOnly?: boolean;
  onRecognize: (imageBase64: string, mode: "text" | "math") => Promise<void>;
};

function cropInkDataUrl(canvas: HTMLCanvasElement): string {
  const ctx = canvas.getContext("2d");
  if (!ctx) return canvas.toDataURL("image/jpeg", 0.85);
  const { width, height } = canvas;
  const image = ctx.getImageData(0, 0, width, height);
  const data = image.data;
  let minX = width;
  let minY = height;
  let maxX = 0;
  let maxY = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      // Non-white ink pixels
      if (data[i] < 245 || data[i + 1] < 245 || data[i + 2] < 245) {
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
      }
    }
  }
  if (maxX < minX || maxY < minY) {
    return canvas.toDataURL("image/jpeg", 0.85);
  }
  const pad = 12;
  minX = Math.max(0, minX - pad);
  minY = Math.max(0, minY - pad);
  maxX = Math.min(width - 1, maxX + pad);
  maxY = Math.min(height - 1, maxY + pad);
  const w = maxX - minX + 1;
  const h = maxY - minY + 1;
  const out = document.createElement("canvas");
  const maxSide = 640;
  const scale = Math.min(1, maxSide / Math.max(w, h));
  out.width = Math.max(1, Math.round(w * scale));
  out.height = Math.max(1, Math.round(h * scale));
  const octx = out.getContext("2d");
  if (!octx) return canvas.toDataURL("image/jpeg", 0.85);
  octx.fillStyle = "#ffffff";
  octx.fillRect(0, 0, out.width, out.height);
  octx.drawImage(canvas, minX, minY, w, h, 0, 0, out.width, out.height);
  return out.toDataURL("image/jpeg", 0.82);
}

export function InkPad({ disabled, penOnly, onRecognize }: InkPadProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recognizeSeq = useRef(0);
  const [mode, setMode] = useState<"text" | "math">("text");
  const [hasInk, setHasInk] = useState(false);
  const hasInkRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
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

  function scheduleAutoRecognize() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => {
      void recognize({ auto: true });
    }, 120);
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
    ctx.beginPath();
    ctx.moveTo(x, y);
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointerPos(e);
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

  function clear() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const rect = canvas.getBoundingClientRect();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    hasInkRef.current = false;
    setHasInk(false);
  }

  async function recognize(opts?: { auto?: boolean }) {
    const canvas = canvasRef.current;
    if (!canvas || !hasInkRef.current || disabled) return;
    if (busy && opts?.auto) return;
    const seq = ++recognizeSeq.current;
    setBusy(true);
    try {
      const dataUrl = cropInkDataUrl(canvas);
      const base64 = dataUrl.split(",", 1)[1] || dataUrl;
      await onRecognize(base64, modeRef.current);
    } finally {
      if (seq === recognizeSeq.current) setBusy(false);
    }
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
        <button type="button" disabled={disabled || busy || !hasInk} onClick={() => void recognize()}>
          {busy ? "Recognizing…" : "Recognize"}
        </button>
        <button type="button" disabled={disabled} onClick={clear}>
          Clear
        </button>
      </div>
      <div style={{ fontSize: 12, color: "#6b7280" }}>
        Recognition runs automatically when you lift the pencil.
      </div>
    </div>
  );
}
