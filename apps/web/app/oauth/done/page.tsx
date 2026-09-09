"use client";

import { useEffect, useMemo, useState } from "react";

/**
 * Landing page after Google (or other) OAuth in a popup / in-app browser.
 * Must stay public (no StudyFlows login) so the OAuth window never asks for JWT.
 */
export default function OAuthDonePage() {
  const [closed, setClosed] = useState(false);
  const params = useMemo(() => {
    if (typeof window === "undefined") return { ok: false, reason: "", provider: "google" };
    const sp = new URLSearchParams(window.location.search);
    const status = sp.get("google") || sp.get("status") || "";
    return {
      ok: status === "connected" || status === "ok" || status === "success",
      reason: sp.get("reason") || "",
      provider: sp.get("provider") || "google",
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function finish() {
      // Notify opener (desktop popup) if present.
      try {
        if (window.opener && !window.opener.closed) {
          window.opener.postMessage(
            { type: "studyflows-oauth", provider: params.provider, ok: params.ok, reason: params.reason },
            window.location.origin
          );
        }
      } catch {
        // ignore
      }

      // Desktop popup: close ourselves.
      try {
        window.close();
        if (!cancelled) setClosed(true);
      } catch {
        // ignore
      }

      // Native Capacitor Browser cannot be closed from this Safari-view context;
      // the main app polls Drive status and calls Browser.close().
    }
    void finish();
  }, [params.ok, params.provider, params.reason]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
        background: "var(--bg, #111827)",
        color: "var(--text, #f9fafb)",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ maxWidth: 420, textAlign: "center", display: "grid", gap: 12 }}>
        <div style={{ fontSize: 22, fontWeight: 700 }}>StudyFlows</div>
        {params.ok ? (
          <>
            <div style={{ fontSize: 18, fontWeight: 600 }}>Google Drive connected</div>
            <p style={{ margin: 0, opacity: 0.85, lineHeight: 1.45 }}>
              You can return to the StudyFlows app. This window should close automatically.
            </p>
          </>
        ) : (
          <>
            <div style={{ fontSize: 18, fontWeight: 600 }}>Connection didn’t finish</div>
            <p style={{ margin: 0, opacity: 0.85, lineHeight: 1.45 }}>
              {params.reason ? `Reason: ${params.reason}. ` : ""}
              Close this window and try Connect again in StudyFlows.
            </p>
          </>
        )}
        {!closed ? (
          <button
            type="button"
            onClick={() => {
              try {
                window.close();
              } catch {
                // ignore
              }
              setClosed(true);
            }}
            style={{
              marginTop: 8,
              padding: "10px 14px",
              borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.2)",
              background: "rgba(255,255,255,0.08)",
              color: "inherit",
              cursor: "pointer",
            }}
          >
            Close window
          </button>
        ) : (
          <p style={{ margin: 0, fontSize: 13, opacity: 0.7 }}>You can close this tab now.</p>
        )}
      </div>
    </main>
  );
}
