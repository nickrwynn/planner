"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { suggestFromCloud, suggestOnDevice, type CompletionSource } from "../lib/text-complete";
import { learnFromText } from "../lib/text-predict";

type SmartTextAreaProps = {
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  placeholder?: string;
  courseId?: string;
  className?: string;
  style?: React.CSSProperties;
};

const CLOUD_IDLE_MS = 700;

/**
 * Textarea with inline completion. Suggestions come from the device first and
 * only fall back to the cloud after you pause. Press Tab (or → at the end of
 * the text) to accept.
 */
export function SmartTextArea({
  value,
  onChange,
  rows = 12,
  placeholder,
  courseId,
  className,
  style,
}: SmartTextAreaProps) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const mirrorRef = useRef<HTMLDivElement | null>(null);
  const cloudTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);
  const [suggestion, setSuggestion] = useState("");
  const [source, setSource] = useState<CompletionSource>("none");

  const caretAtEnd = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return false;
    return ta.selectionStart === ta.value.length && ta.selectionEnd === ta.value.length;
  }, []);

  const clearSuggestion = useCallback(() => {
    setSuggestion("");
    setSource("none");
  }, []);

  const refreshSuggestion = useCallback(
    async (text: string) => {
      const mySeq = ++seq.current;
      if (cloudTimer.current) clearTimeout(cloudTimer.current);
      if (!caretAtEnd() || !text.trim()) {
        clearSuggestion();
        return;
      }

      const local = await suggestOnDevice(text);
      if (mySeq !== seq.current) return;
      if (local.text) {
        setSuggestion(local.text);
        setSource(local.source);
        return;
      }

      clearSuggestion();
      // Nothing on-device: ask the cloud, but only once typing pauses.
      cloudTimer.current = setTimeout(() => {
        void (async () => {
          const cloud = await suggestFromCloud(text, { courseId });
          if (mySeq !== seq.current) return;
          if (cloud.text && caretAtEnd()) {
            setSuggestion(cloud.text);
            setSource(cloud.source);
          }
        })();
      }, CLOUD_IDLE_MS);
    },
    [caretAtEnd, clearSuggestion, courseId]
  );

  useEffect(() => {
    return () => {
      if (cloudTimer.current) clearTimeout(cloudTimer.current);
    };
  }, []);

  // Keep the ghost-text mirror scrolled in step with the textarea.
  function syncScroll() {
    const ta = taRef.current;
    const mirror = mirrorRef.current;
    if (ta && mirror) mirror.scrollTop = ta.scrollTop;
  }

  function accept() {
    if (!suggestion) return;
    const next = value + suggestion;
    onChange(next);
    clearSuggestion();
    requestAnimationFrame(() => {
      const ta = taRef.current;
      if (ta) {
        ta.selectionStart = next.length;
        ta.selectionEnd = next.length;
      }
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!suggestion) return;
    if (e.key === "Tab" || (e.key === "ArrowRight" && caretAtEnd())) {
      e.preventDefault();
      accept();
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      clearSuggestion();
    }
  }

  return (
    <div className="smartTextWrap">
      <div ref={mirrorRef} className="smartTextMirror" aria-hidden="true">
        {value}
        {suggestion ? <span className="smartTextGhost">{suggestion}</span> : null}
      </div>
      <textarea
        ref={taRef}
        className={`smartTextArea${className ? ` ${className}` : ""}`}
        style={style}
        rows={rows}
        placeholder={placeholder}
        value={value}
        spellCheck
        autoCorrect="on"
        autoCapitalize="sentences"
        onScroll={syncScroll}
        onKeyDown={onKeyDown}
        onClick={clearSuggestion}
        onBlur={() => {
          learnFromText(value);
        }}
        onChange={(e) => {
          const next = e.target.value;
          onChange(next);
          void refreshSuggestion(next);
        }}
      />
      {suggestion ? (
        <button
          type="button"
          className="smartTextHint"
          // Keep focus in the textarea so accepting does not dismiss the keyboard.
          onMouseDown={(e) => e.preventDefault()}
          onClick={accept}
        >
          Accept “{suggestion.trim()}” · {source === "cloud" ? "cloud assist" : "on-device"}
        </button>
      ) : null}
    </div>
  );
}
