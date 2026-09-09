"use client";

import { useEffect, useRef, useState } from "react";
import type { StudyExcerpt } from "../lib/studyflow-actions";

export type PaperStyle = "notebook" | "printer";

type StudyNotebookProps = {
  excerpts: StudyExcerpt[];
  activeExcerptId: string | null;
  paperStyle: PaperStyle;
  onPaperStyleChange: (style: PaperStyle) => void;
  onSelectExcerpt: (id: string) => void;
  onRecognizeInk: (imageBase64: string, mode: "text" | "math") => Promise<void>;
  inkDisabled?: boolean;
  commentDraft?: string;
  onCommentDraftChange?: (text: string) => void;
  onSaveComment?: () => void;
  saveBusy?: boolean;
};

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
  const drawing = useRef(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasInkRef = useRef(false);
  const [hasInk, setHasInk] = useState(false);
  const [busy, setBusy] = useState(false);

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
    ctx.lineWidth = 2.2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    return () => {
      if (idleTimer.current) clearTimeout(idleTimer.current);
    };
  }, [activeExcerptId]);

  function pointerPos(e: React.PointerEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function scheduleRecognize() {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => void recognizeInk(), 120);
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (inkDisabled) return;
    if (e.pointerType === "touch") return;
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
    scheduleRecognize();
  }

  async function recognizeInk() {
    const canvas = canvasRef.current;
    if (!canvas || !hasInkRef.current || inkDisabled || busy) return;
    setBusy(true);
    try {
      const dataUrl = canvas.toDataURL("image/jpeg", 0.82);
      const base64 = dataUrl.split(",", 1)[1] || dataUrl;
      await onRecognizeInk(base64, "text");
    } finally {
      setBusy(false);
    }
  }

  function clearInk() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const rect = canvas.getBoundingClientRect();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    hasInkRef.current = false;
    setHasInk(false);
  }

  return (
    <div className={`studyNotebook is-${paperStyle}`}>
      <div className="studyNotebookToolbar">
        <span className="studySideTitle" style={{ margin: 0 }}>
          Study notebook
        </span>
        <div className="studyInkModes">
          <button
            type="button"
            className={paperStyle === "notebook" ? "isActive" : ""}
            onClick={() => onPaperStyleChange("notebook")}
          >
            Notebook
          </button>
          <button
            type="button"
            className={paperStyle === "printer" ? "isActive" : ""}
            onClick={() => onPaperStyleChange("printer")}
          >
            Printer
          </button>
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
                <div className="studyNotebookComment">
                  {isActive && onCommentDraftChange ? (
                    <>
                      <textarea
                        value={commentDraft ?? ex.comment ?? ""}
                        onChange={(e) => onCommentDraftChange(e.target.value)}
                        placeholder="Your comment or notes…"
                        rows={4}
                        spellCheck
                        autoCorrect="on"
                        autoCapitalize="sentences"
                      />
                      {onSaveComment ? (
                        <button type="button" disabled={saveBusy || !(commentDraft ?? ex.comment)?.trim()} onClick={onSaveComment}>
                          Save comment
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <div className="studyNotebookCommentText">
                      {ex.comment?.trim() || ex.summary?.trim() || (
                        <span className="studySideMuted">Tap to add a comment…</span>
                      )}
                    </div>
                  )}
                </div>
              </article>
            );
          })
        )}

        {activeExcerptId ? (
          <div className="studyNotebookInkZone">
            <div className="studySideTitle">Write with Apple Pencil</div>
            <div className="studySideMuted">Pencil writes here · finger types in the comment box above.</div>
            <canvas
              ref={canvasRef}
              className="studyNotebookInkCanvas"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            />
            <div className="studySideActions">
              <button type="button" disabled={inkDisabled || busy || !hasInk} onClick={() => void recognizeInk()}>
                {busy ? "Recognizing…" : "Recognize ink"}
              </button>
              <button type="button" disabled={inkDisabled} onClick={clearInk}>
                Clear
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
