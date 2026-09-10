"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { recognizeHandwriting } from "../lib/handwriting-recognize";
import { planInsertion, spliceText, type InsertionSpan } from "../lib/pen-insert";
import { InkPad } from "./ink-pad";

export type InputMode = "auto" | "pen" | "keyboard";

type InputModeContextValue = {
  mode: InputMode;
  setMode: (mode: InputMode) => void;
  penSheetOpen: boolean;
  openPenSheet: (target?: HTMLInputElement | HTMLTextAreaElement | null) => void;
  closePenSheet: () => void;
};

const InputModeContext = createContext<InputModeContextValue | null>(null);
const STORAGE_KEY = "studyflows_input_mode";

function isEditable(el: EventTarget | null): el is HTMLInputElement | HTMLTextAreaElement {
  if (!(el instanceof HTMLElement)) return false;
  if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly;
  if (el instanceof HTMLInputElement) {
    const type = (el.type || "text").toLowerCase();
    if (["button", "checkbox", "radio", "file", "submit", "reset", "hidden", "range", "color"].includes(type)) {
      return false;
    }
    return !el.disabled && !el.readOnly;
  }
  return false;
}

/**
 * Write into a field without focusing it.
 *
 * Focus is deliberately not taken: on iPadOS, focusing a text field raises the
 * on-screen keyboard, which is exactly what the pen flow is meant to avoid.
 * React is notified through the native value setter plus an input event.
 */
function writeValue(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string,
  caret: number
) {
  const nativeSetter = Object.getOwnPropertyDescriptor(
    el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
    "value"
  )?.set;
  nativeSetter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  try {
    el.setSelectionRange(caret, caret);
  } catch {
    // Fields that don't support selection ranges, e.g. type="email".
  }
}

export function useInputMode(): InputModeContextValue {
  const ctx = useContext(InputModeContext);
  if (!ctx) {
    throw new Error("useInputMode must be used within InputModeProvider");
  }
  return ctx;
}

export function InputModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<InputMode>("auto");
  const [penSheetOpen, setPenSheetOpen] = useState(false);
  const targetRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  /** What the last recognition pass wrote, so the next pass can refine it. */
  const spanRef = useRef<InsertionSpan | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) as InputMode | null;
      if (stored === "auto" || stored === "pen" || stored === "keyboard") setModeState(stored);
    } catch {
      // ignore
    }
  }, []);

  const setMode = useCallback((next: InputMode) => {
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
    if (next === "keyboard") setPenSheetOpen(false);
  }, []);

  const openPenSheet = useCallback((target?: HTMLInputElement | HTMLTextAreaElement | null) => {
    if (target) targetRef.current = target;
    spanRef.current = null;
    setPenSheetOpen(true);
  }, []);

  const closePenSheet = useCallback(() => {
    spanRef.current = null;
    setPenSheetOpen(false);
  }, []);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".penBridgeSheet") || target.closest(".studyInkPad") || target.closest(".studyInkCanvas")) {
        return;
      }
      // The study notebook is its own pen surface — it must not open the sheet.
      if (target.closest(".studyPaper")) return;
      if (target.closest(".docScan") || target.closest("canvas")) return;

      const editable = isEditable(target)
        ? target
        : (() => {
            const near = target.closest("input, textarea");
            return isEditable(near) ? near : null;
          })();

      if (!editable) return;

      const wantPen =
        mode === "pen" || (mode === "auto" && e.pointerType === "pen");

      if (wantPen) {
        // Without this the browser focuses the field it just heard a tap on,
        // and iPadOS raises the keyboard over the ink sheet.
        e.preventDefault();
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
        if (targetRef.current !== editable) spanRef.current = null;
        targetRef.current = editable;
        setPenSheetOpen(true);
      } else if (mode === "auto" && e.pointerType === "touch") {
        setPenSheetOpen(false);
        editable.focus();
      } else if (mode === "keyboard") {
        setPenSheetOpen(false);
      }
    }

    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [mode]);

  const onRecognize = useCallback(
    async (imageBase64: string, recognizeMode: "text" | "math", session: number) => {
      const res = await recognizeHandwriting(imageBase64, recognizeMode);
      const text = (recognizeMode === "math" && res.latex ? res.latex : res.text || "").trim();
      if (!text) return null;
      const el = targetRef.current;
      if (!el || !document.contains(el)) return res.source;

      // Each pass re-reads all the ink on the pad, so a pass belonging to the
      // same ink session overwrites what the last one wrote. Appending instead
      // would turn "cat" into "c ca cat".
      const caret = {
        start: el.selectionStart ?? el.value.length,
        end: el.selectionEnd ?? el.value.length,
      };
      const plan = planInsertion(spanRef.current, session, caret);
      const addition = text.endsWith("\n") ? text : `${text} `;
      const { value, span } = spliceText(el.value, plan, addition);
      writeValue(el, value, span.end);
      spanRef.current = { session, ...span };
      return res.source;
    },
    []
  );

  const value = useMemo(
    () => ({ mode, setMode, penSheetOpen, openPenSheet, closePenSheet }),
    [mode, setMode, penSheetOpen, openPenSheet, closePenSheet]
  );

  return (
    <InputModeContext.Provider value={value}>
      {children}
      <div className="inputModeBar" role="toolbar" aria-label="Pen or keyboard">
        {(
          [
            ["auto", "Auto"],
            ["pen", "Pen"],
            ["keyboard", "Type"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={mode === id ? "isActive" : ""}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
        <button type="button" onClick={() => openPenSheet()} title="Open ink pad">
          Ink
        </button>
      </div>
      {penSheetOpen ? (
        <div className="penBridgeSheet">
          <div className="penBridgeSheetHeader">
            <strong>Write with Apple Pencil</strong>
            <button type="button" onClick={closePenSheet}>
              Done
            </button>
          </div>
          <p className="penBridgeHint">
            Auto mode: Pencil opens ink · finger/tap opens the keyboard. Recognized text goes into the focused field.
          </p>
          <InkPad penOnly={mode === "auto"} onRecognize={onRecognize} />
        </div>
      ) : null}
    </InputModeContext.Provider>
  );
}
