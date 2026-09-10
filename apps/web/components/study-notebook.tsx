"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { cropInkToDataUrl, growBounds, type InkBounds } from "../lib/ink-crop";
import type { StudyExcerpt } from "../lib/studyflow-actions";

export type PaperStyle = "notebook" | "printer";

/** Distance between ruled lines, in px. Text line-height matches this. */
const RULE = 28;
/**
 * Pause after the pencil lifts before ink is recognized. Long enough to clear
 * the natural gaps between letters, so recognition sees whole words.
 */
const RECOGNIZE_IDLE_MS = 700;
const MIN_ROWS = 10;

type StudyNotebookProps = {
  excerpts: StudyExcerpt[];
  activeExcerptId: string | null;
  paperStyle: PaperStyle;
  onPaperStyleChange: (style: PaperStyle) => void;
  onSelectExcerpt: (id: string) => void;
  onRecognizeInk: (imageBase64: string, mode: "text" | "math") => Promise<string>;
  inkDisabled?: boolean;
  commentDraft?: string;
  onCommentDraftChange?: (text: string) => void;
  onSaveComment?: () => void;
  saveBusy?: boolean;
};

/**
 * One sheet of ruled paper per excerpt.
 *
 * There is no separate input box and no separate ink pad: the paper *is* the
 * field. Apple Pencil draws on the lines and the ink is recognized into text;
 * a finger or mouse lands on the textarea underneath, so the keyboard opens
 * and typing appears on the same lines.
 */
export function StudyNotebook({
  excerpts,
  activeExcerptId,
  paperStyle,
  onPaperStyleChange,
  onSelectExcerpt,
  onRecognizeInk,
  inkDisabled,
  commentDraft,
  onCommentDraftChange,
  onSaveComment,
  saveBusy,
}: StudyNotebookProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const surfaceRef = useRef<HTMLDivElement | null>(null);
  const drawing = useRef(false);
  const hasInkRef = useRef(false);
  const inkBounds = useRef<InkBounds | null>(null);
  const dprRef = useRef(1);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mode, setMode] = useState<"text" | "math">("text");
  const [writing, setWriting] = useState(false);
  const [busy, setBusy] = useState(false);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  const text = commentDraft ?? "";

  /** Match the backing store to the CSS box so ink is not blurry or offset. */
  const sizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const surface = surfaceRef.current;
    if (!canvas || !surface) return;
    const rect = surface.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return;
    const dpr = window.devicePixelRatio || 1;
    dprRef.current = dpr;
    canvas.width = Math.floor(rect.width * dpr);
    canvas.height = Math.floor(rect.height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.strokeStyle = "#1e3a8a";
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  }, []);

  useEffect(() => {
    sizeCanvas();
    const surface = surfaceRef.current;
    if (!surface || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => sizeCanvas());
    observer.observe(surface);
    return () => observer.disconnect();
  }, [sizeCanvas, activeExcerptId]);

  useEffect(() => {
    return () => {
      if (idleTimer.current) clearTimeout(idleTimer.current);
    };
  }, []);

  function clearInk() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    hasInkRef.current = false;
    inkBounds.current = null;
  }

  /** Insert recognized text at the caret so writing continues where you were. */
  function insertAtCaret(value: string) {
    const el = textRef.current;
    const current = text;
    if (!el) {
      onCommentDraftChange?.(current + value);
      return;
    }
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? current.length;
    const needsSpace = start > 0 && !/\s$/.test(current.slice(0, start));
    const addition = `${needsSpace ? " " : ""}${value}`;
    const next = `${current.slice(0, start)}${addition}${current.slice(end)}`;
    onCommentDraftChange?.(next);
    const caret = start + addition.length;
    requestAnimationFrame(() => {
      try {
        el.setSelectionRange(caret, caret);
      } catch {
        // ignore
      }
    });
  }

  async function recognize() {
    const canvas = canvasRef.current;
    if (!canvas || !hasInkRef.current || inkDisabled || busy) return;
    setBusy(true);
    try {
      const ink = inkBounds.current;
      if (!ink) return;
      // Crop to the writing and flatten onto white: recognition expects dark
      // ink on a light page, and a word alone on a full page reads poorly.
      const dataUrl = cropInkToDataUrl(canvas, ink, dprRef.current, 2);
      if (!dataUrl) return;
      const base64 = dataUrl.split(",")[1] || dataUrl;
      const recognized = await onRecognizeInk(base64, modeRef.current);
      if (recognized?.trim()) {
        insertAtCaret(recognized.trim());
        clearInk();
      }
    } finally {
      setBusy(false);
    }
  }

  function scheduleRecognize() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => void recognize(), RECOGNIZE_IDLE_MS);
  }

  function pointAt(e: React.PointerEvent) {
    const surface = surfaceRef.current!;
    const rect = surface.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    // Finger and mouse fall through to the textarea so the keyboard opens.
    if (e.pointerType !== "pen" || inkDisabled) return;
    // Stop the pen from focusing the field or opening the global ink sheet.
    e.preventDefault();
    e.stopPropagation();
    if (idleTimer.current) clearTimeout(idleTimer.current);

    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    drawing.current = true;
    setWriting(true);
    const { x, y } = pointAt(e);
    inkBounds.current = growBounds(inkBounds.current, x, y);
    ctx.beginPath();
    ctx.moveTo(x, y);
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }

  function onPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = canvasRef.current?.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointAt(e);
    inkBounds.current = growBounds(inkBounds.current, x, y);
    ctx.lineTo(x, y);
    ctx.stroke();
    hasInkRef.current = true;
  }

  function onPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (!drawing.current) return;
    drawing.current = false;
    setWriting(false);
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
    scheduleRecognize();
  }

  const rows = Math.max(MIN_ROWS, text.split("\n").length + 1);

  return (
    <div className={`studyNotebook is-${paperStyle}`}>
      <div className="studyNotebookToolbar">
        <span className="studySideTitle" style={{ margin: 0 }}>
          Study notebook
        </span>
        <div className="studyNotebookTools">
          <div className="studyInkModes">
            <button
              type="button"
              className={mode === "text" ? "isActive" : ""}
              onClick={() => setMode("text")}
            >
              Text
            </button>
            <button
              type="button"
              className={mode === "math" ? "isActive" : ""}
              onClick={() => setMode("math")}
            >
              Math
            </button>
          </div>
          <div className="studyInkModes">
            <button
              type="button"
              className={paperStyle === "notebook" ? "isActive" : ""}
              onClick={() => onPaperStyleChange("notebook")}
            >
              Ruled
            </button>
            <button
              type="button"
              className={paperStyle === "printer" ? "isActive" : ""}
              onClick={() => onPaperStyleChange("printer")}
            >
              Blank
            </button>
          </div>
        </div>
      </div>

      <div className="studyNotebookScroll">
        {excerpts.length === 0 ? (
          <div className="studyNotebookEmpty">
            Highlight text in the resource, then switch here to write notes on paper.
          </div>
        ) : (
          excerpts.map((ex) => {
            const isActive = ex.id === activeExcerptId;
            return (
              <article
                key={ex.id}
                className={`studyNotebookEntry${isActive ? " isActive" : ""}`}
                onClick={() => onSelectExcerpt(ex.id)}
              >
                <div className="studyNotebookHighlight">
                  <span className="studyNotebookPage">p{ex.page}</span>
                  {ex.text}
                </div>

                {isActive && onCommentDraftChange ? (
                  <>
                    <div
                      ref={surfaceRef}
                      className={`studyPaper${writing ? " isWriting" : ""}`}
                      onPointerDownCapture={onPointerDown}
                      onPointerMove={onPointerMove}
                      onPointerUp={onPointerUp}
                      onPointerCancel={onPointerUp}
                    >
                      <textarea
                        ref={textRef}
                        className="studyPaperText"
                        value={text}
                        onChange={(e) => onCommentDraftChange(e.target.value)}
                        rows={rows}
                        placeholder="Write with your pencil or type with a finger…"
                        spellCheck
                        autoCorrect="on"
                        autoCapitalize="sentences"
                      />
                      <canvas ref={canvasRef} className="studyPaperInk" />
                    </div>
                    <div className="studyPaperFooter">
                      <span className="studySideMuted">
                        {busy
                          ? "Reading your writing…"
                          : `Pencil writes · finger types · ${mode === "math" ? "math → LaTeX" : "text"}`}
                      </span>
                      {onSaveComment ? (
                        <button
                          type="button"
                          className="studyPaperSave"
                          disabled={saveBusy || !text.trim()}
                          onClick={onSaveComment}
                        >
                          {saveBusy ? "Saving…" : "Save to notes"}
                        </button>
                      ) : null}
                    </div>
                  </>
                ) : (
                  <div className="studyNotebookCommentText">
                    {ex.comment?.trim() || ex.summary?.trim() || (
                      <span className="studySideMuted">Tap to write here…</span>
                    )}
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

export { RULE };
