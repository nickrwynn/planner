"use client";

import { useEffect, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { canRecognizeOnDevice } from "../lib/handwriting-native";
import {
  getLastRecognition,
  getPointerSamples,
  pointerTypeCounts,
  subscribeDiagnostics,
} from "../lib/ink-diagnostics";

/**
 * What the pen and the recogniser actually did.
 *
 * Poor recognition has several very different causes — the wrong engine, a bad
 * crop, or the browser reporting the Pencil as a finger — and they are
 * indistinguishable from the outside. This shows which one is happening.
 */
export function InkDiagnostics() {
  const [, force] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => subscribeDiagnostics(() => force((n) => n + 1)), []);

  const native = Capacitor.isNativePlatform();
  const visionReady = canRecognizeOnDevice();
  const last = getLastRecognition();
  const counts = pointerTypeCounts();
  const samples = getPointerSamples();

  return (
    <details className="inkDiagnostics" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Diagnostics</summary>

      <div className="inkDiagRow">
        <span>Native app</span>
        <span>{native ? "yes" : "no (plain browser)"}</span>
      </div>
      <div className="inkDiagRow">
        <span>Apple Vision</span>
        <span>{visionReady ? "available" : "not available"}</span>
      </div>
      <div className="inkDiagRow">
        <span>Pointer types seen</span>
        <span>
          {Object.keys(counts).length
            ? Object.entries(counts)
                .map(([type, n]) => `${type}×${n}`)
                .join(", ")
            : "none yet"}
        </span>
      </div>
      {samples[0] ? (
        <div className="inkDiagRow">
          <span>Last pointer</span>
          <span>
            {samples[0].type || "(empty)"} · pressure {samples[0].pressure.toFixed(2)} ·{" "}
            {samples[0].surface}
          </span>
        </div>
      ) : null}

      {last ? (
        <>
          <div className="inkDiagRow">
            <span>Engine used</span>
            <span>{last.engine}</span>
          </div>
          <div className="inkDiagRow">
            <span>Time taken</span>
            <span>{last.ms} ms</span>
          </div>
          <div className="inkDiagRow">
            <span>Image sent</span>
            <span>{(last.imageBytes / 1024).toFixed(1)} KB, mode {last.mode}</span>
          </div>
          {last.error ? (
            <div className="inkDiagRow">
              <span>Error</span>
              <span>{last.error}</span>
            </div>
          ) : null}
          <div className="inkDiagText">{last.text || "(nothing recognised)"}</div>
          {last.imageDataUrl ? (
            <>
              <div className="studySideMuted" style={{ fontSize: 11 }}>
                Exactly what the recogniser received:
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="inkDiagImage" src={last.imageDataUrl} alt="Ink sent for recognition" />
            </>
          ) : null}
        </>
      ) : (
        <div className="studySideMuted" style={{ fontSize: 12 }}>
          Write something to see how it was read.
        </div>
      )}
    </details>
  );
}
