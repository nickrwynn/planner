"use client";

import { useEffect, useRef, useState } from "react";

export type InkStroke = {
  points: [number, number][];
  width: number;
  tool: "pen";
};

export type InkElement = {
  id: string;
  type: "ink";
  strokes: InkStroke[];
};

export function HandwritingCanvas({
  initial,
  onChange
}: {
  initial?: InkElement;
  onChange: (el: InkElement) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [element, setElement] = useState<InkElement>(
    initial ?? { id: "ink1", type: "ink", strokes: [] }
  );
  const elementRef = useRef<InkElement>(element);
  const [isDrawing, setIsDrawing] = useState(false);

  useEffect(() => {
    if (initial) setElement(initial);
  }, [initial]);

  useEffect(() => {
    elementRef.current = element;
  }, [element]);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#111";

    for (const s of element.strokes) {
      if (s.points.length < 2) continue;
      ctx.lineWidth = s.width;
      ctx.beginPath();
      ctx.moveTo(s.points[0][0], s.points[0][1]);
      for (let i = 1; i < s.points.length; i++) {
        ctx.lineTo(s.points[i][0], s.points[i][1]);
      }
      ctx.stroke();
    }
  }, [element]);

  function getPoint(e: React.PointerEvent<HTMLCanvasElement>): [number, number] {
    const rect = e.currentTarget.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  function start(e: React.PointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = getPoint(e);
    const next: InkElement = {
      ...element,
      strokes: [...element.strokes, { points: [p], width: 2, tool: "pen" }]
    };
    setElement(next);
    setIsDrawing(true);
  }

  function move(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!isDrawing) return;
    const p = getPoint(e);
    setElement((prev) => {
      const strokes = [...prev.strokes];
      const last = strokes[strokes.length - 1];
      if (!last) return prev;
      const updated = { ...last, points: [...last.points, p] };
      strokes[strokes.length - 1] = updated;
      return { ...prev, strokes };
    });
  }

  function end() {
    setIsDrawing(false);
    onChange(elementRef.current);
  }

  function clear() {
    const next = { ...element, strokes: [] };
    setElement(next);
    onChange(next);
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <canvas
        ref={canvasRef}
        width={600}
        height={360}
        style={{ border: "1px solid #e5e7eb", borderRadius: 10, background: "#fff" }}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={clear} style={{ padding: "8px 12px" }}>
          Clear
        </button>
        <div style={{ color: "#555", fontSize: 12, alignSelf: "center" }}>
          Minimal handwriting MVP: pen only.
        </div>
      </div>
    </div>
  );
}

