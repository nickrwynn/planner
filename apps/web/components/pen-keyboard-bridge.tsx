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

function insertText(el: HTMLInputElement | HTMLTextAreaElement, text: string) {
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? el.value.length;
  const next = `${el.value.slice(0, start)}${text}${el.value.slice(end)}`;
  const nativeSetter = Object.getOwnPropertyDescriptor(
    el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
    "value"
  )?.set;
  nativeSetter?.call(el, next);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  const caret = start + text.length;
  try {
    el.setSelectionRange(caret, caret);
  } catch {
    // ignore
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
  const lastPointerType = useRef<string>("touch");

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
    setPenSheetOpen(true);
  }, []);

  const closePenSheet = useCallback(() => setPenSheetOpen(false), []);

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      lastPointerType.current = e.pointerType || "touch";
      const target = e.target;
      if (!(target instanceof Element)) return;
      if (target.closest(".penBridgeSheet") || target.closest(".studyInkPad") || target.closest(".studyInkCanvas")) {
        return;
      }
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
        // Keep focus for insertion, but open pen sheet instead of fighting the OS keyboard.
        targetRef.current = editable;
        setPenSheetOpen(true);
      } else if (mode === "keyboard" || (mode === "auto" && e.pointerType !== "pen")) {
        setPenSheetOpen(false);
      }
    }

    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [mode]);

  const onRecognize = useCallback(async (imageBase64: string, recognizeMode: "text" | "math") => {
    const { apiPost } = await import("../lib/api");
    const res = await apiPost<{ text: string; latex?: string | null }>("/ai/handwriting", {
      image_base64: imageBase64,
      mode: recognizeMode,
    });
    const text = (recognizeMode === "math" && res.latex ? res.latex : res.text || "").trim();
    if (!text) return;
    const el = targetRef.current;
    if (el && document.contains(el)) {
      el.focus();
      insertText(el, text + (text.endsWith("\n") ? "" : " "));
    }
  }, []);

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
          <InkPad onRecognize={onRecognize} />
        </div>
      ) : null}
    </InputModeContext.Provider>
  );
}
