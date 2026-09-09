"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost, apiPut, toErrorMessage } from "../lib/api";
import { canAutoCaptureCanvasSession, captureCanvasSession } from "../lib/canvas-login";
import { canvasBaseUrlFromEmail, CONNECT_CANVAS_EMAIL, CONNECT_CANVAS_FLAG } from "../lib/canvas-school";
import type { CanvasStatus, CanvasSyncResult } from "../lib/types";

type CanvasConnectPanelProps = {
  compact?: boolean;
};

function clearConnectCanvasQuery() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("connectCanvas")) return;
    url.searchParams.delete("connectCanvas");
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, "", next);
  } catch {
    // ignore
  }
}

export function CanvasConnectPanel({ compact }: CanvasConnectPanelProps) {
  const [canvasStatus, setCanvasStatus] = useState<CanvasStatus | null>(null);
  const [canvasBaseUrl, setCanvasBaseUrl] = useState("https://canvas.tamu.edu");
  const [canvasToken, setCanvasToken] = useState("");
  const [sessionCookie, setSessionCookie] = useState("");
  const [qrUrl, setQrUrl] = useState("");
  const [showPat, setShowPat] = useState(false);
  const [canvasBusy, setCanvasBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<CanvasSyncResult | null>(null);
  const [oauthBanner, setOauthBanner] = useState<string | null>(null);
  const [nativeCanvasLogin, setNativeCanvasLogin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const autoConnectStarted = useRef(false);

  async function refresh() {
    setError(null);
    try {
      const status = await apiGet<CanvasStatus>("/integrations/canvas/status");
      setCanvasStatus(status);
      if (!canvasBaseUrl) {
        setCanvasBaseUrl(status.base_url || status.default_base_url || "");
      }
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function connectSessionAndSync(sessionValue: string, baseUrl?: string) {
    const status = await apiPost<CanvasStatus>("/integrations/canvas/session", {
      base_url: (baseUrl ?? canvasBaseUrl).trim() || null,
      session_cookie: sessionValue.trim(),
    });
    setCanvasStatus(status);
    setSessionCookie("");
    const result = await apiPost<CanvasSyncResult>("/integrations/canvas/sync", {});
    setSyncResult(result);
    setOauthBanner("Canvas connected and synced.");
    await refresh();
  }

  async function onSignInWithCanvas(overrideBase?: string) {
    const base = (overrideBase ?? canvasBaseUrl).trim() || "https://canvas.tamu.edu";
    setCanvasBusy(true);
    setError(null);
    setSyncResult(null);
    try {
      const captured = await captureCanvasSession(base);
      if (captured.baseUrl) setCanvasBaseUrl(captured.baseUrl);
      await connectSessionAndSync(captured.sessionCookie, captured.baseUrl || base);
    } catch (err) {
      const message = toErrorMessage(err);
      if (!message.toLowerCase().includes("cancel")) {
        setError(message);
      }
    } finally {
      setCanvasBusy(false);
    }
  }

  useEffect(() => {
    const isNative = canAutoCaptureCanvasSession();
    setNativeCanvasLogin(isNative);
    const params = new URLSearchParams(window.location.search);
    const canvas = params.get("canvas");
    const wantsConnect =
      params.get("connectCanvas") === "1" ||
      (() => {
        try {
          return sessionStorage.getItem(CONNECT_CANVAS_FLAG) === "1";
        } catch {
          return false;
        }
      })();

    let hintBase = "";
    try {
      hintBase = sessionStorage.getItem("aos_canvas_base_hint") || "";
      const email = sessionStorage.getItem(CONNECT_CANVAS_EMAIL) || "";
      if (!hintBase && email) hintBase = canvasBaseUrlFromEmail(email);
    } catch {
      // ignore
    }
    if (hintBase) setCanvasBaseUrl(hintBase);

    if (canvas === "connected") {
      setOauthBanner("Canvas OAuth connected. Syncing courses…");
    } else if (canvas === "error") {
      setOauthBanner(`Canvas OAuth failed${params.get("reason") ? `: ${params.get("reason")}` : ""}.`);
    } else if (wantsConnect) {
      setOauthBanner(
        isNative
          ? "Account created — opening Canvas sign-in (NetID / Duo)…"
          : "Account created — set your Canvas URL, then tap Sign in with Canvas (best in the iPad app)."
      );
    }

    void refresh().then(() => {
      void (async () => {
        if (canvas === "connected") {
          try {
            setCanvasBusy(true);
            const result = await apiPost<CanvasSyncResult>("/integrations/canvas/sync", {});
            setSyncResult(result);
            setOauthBanner("Canvas connected and synced.");
            await refresh();
          } catch (err) {
            setOauthBanner("Canvas OAuth connected, but sync failed — tap Sync now.");
            setError(toErrorMessage(err));
          } finally {
            setCanvasBusy(false);
          }
          return;
        }

        if (!wantsConnect || autoConnectStarted.current) return;
        autoConnectStarted.current = true;
        try {
          sessionStorage.removeItem(CONNECT_CANVAS_FLAG);
          sessionStorage.removeItem(CONNECT_CANVAS_EMAIL);
          sessionStorage.removeItem("aos_canvas_base_hint");
        } catch {
          // ignore
        }
        clearConnectCanvasQuery();

        const status = await apiGet<CanvasStatus>("/integrations/canvas/status").catch(() => null);
        if (status?.connected) {
          setOauthBanner("Canvas already connected.");
          return;
        }

        const base = hintBase || "https://canvas.tamu.edu";
        setCanvasBaseUrl(base);
        if (isNative) {
          await onSignInWithCanvas(base);
          return;
        }
        // Web: OAuth if configured; otherwise leave URL filled and prompt Sign in / cookie.
        if (status?.oauth_configured) {
          setOauthBanner("Account created — continuing to Canvas OAuth…");
          setCanvasBusy(true);
          try {
            const started = await apiPost<{ authorize_url: string }>("/integrations/canvas/oauth/start", {
              base_url: base,
            });
            window.location.href = started.authorize_url;
          } catch (err) {
            setError(toErrorMessage(err));
            setOauthBanner("Account created — Canvas URL is filled from your school email. Tap Sign in with Canvas or use a fallback below.");
            setCanvasBusy(false);
          }
        }
      })();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onConnectOAuth() {
    setCanvasBusy(true);
    setError(null);
    setSyncResult(null);
    try {
      const started = await apiPost<{ authorize_url: string }>("/integrations/canvas/oauth/start", {
        base_url: canvasBaseUrl.trim() || null,
      });
      window.location.href = started.authorize_url;
    } catch (err) {
      setError(toErrorMessage(err));
      setCanvasBusy(false);
    }
  }

  async function onConnectSession(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionCookie.trim()) return;
    setCanvasBusy(true);
    setError(null);
    setSyncResult(null);
    try {
      await connectSessionAndSync(sessionCookie);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setCanvasBusy(false);
    }
  }

  async function onConnectQr(e: React.FormEvent) {
    e.preventDefault();
    if (!qrUrl.trim()) return;
    setCanvasBusy(true);
    setError(null);
    setSyncResult(null);
    try {
      const status = await apiPost<CanvasStatus>("/integrations/canvas/oauth/qr", {
        qr_url: qrUrl.trim(),
      });
      setCanvasStatus(status);
      setQrUrl("");
      const result = await apiPost<CanvasSyncResult>("/integrations/canvas/sync", {});
      setSyncResult(result);
      setOauthBanner("Canvas connected via QR and synced.");
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setCanvasBusy(false);
    }
  }

  async function onConnectPat(e: React.FormEvent) {
    e.preventDefault();
    if (!canvasBaseUrl.trim() || !canvasToken.trim()) return;
    setCanvasBusy(true);
    setError(null);
    setSyncResult(null);
    try {
      const status = await apiPut<CanvasStatus>("/integrations/canvas", {
        base_url: canvasBaseUrl.trim(),
        access_token: canvasToken.trim(),
      });
      setCanvasStatus(status);
      setCanvasToken("");
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setCanvasBusy(false);
    }
  }

  async function onSyncCanvas() {
    setCanvasBusy(true);
    setError(null);
    try {
      const result = await apiPost<CanvasSyncResult>("/integrations/canvas/sync", {});
      setSyncResult(result);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setCanvasBusy(false);
    }
  }

  return (
    <div className="card" style={{ display: "grid", gap: 10 }}>
      <div style={{ fontWeight: 700 }}>Canvas</div>
      {!compact ? (
        <div style={{ color: "#555", fontSize: 14 }}>
          {nativeCanvasLogin
            ? "Sign in once with NetID / Duo in the app. StudyFlows captures the session and syncs courses automatically."
            : "In the StudyFlows iPad app, Canvas sign-in is automatic after NetID / Duo. On the web, use the fallback below or OAuth."}
        </div>
      ) : null}
      {oauthBanner ? (
        <div style={{ fontSize: 13, color: oauthBanner.includes("failed") ? "#b91c1c" : "#166534" }}>{oauthBanner}</div>
      ) : null}
      {error ? <div style={{ fontSize: 13, color: "#b91c1c" }}>{error}</div> : null}
      {canvasStatus?.connected ? (
        <div style={{ fontSize: 13, color: "#166534" }}>
          Connected{canvasStatus.canvas_user_name ? ` as ${canvasStatus.canvas_user_name}` : ""}
          {canvasStatus.auth_mode ? ` · ${canvasStatus.auth_mode}` : ""}
          {canvasStatus.base_url ? ` · ${canvasStatus.base_url}` : ""}
          {canvasStatus.last_synced_at
            ? ` · last sync ${new Date(canvasStatus.last_synced_at).toLocaleString()}`
            : " · not synced yet"}
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "#6b7280" }}>
          Not connected — enter your Canvas URL, then tap <strong>Sign in with Canvas</strong>. Sync stays off until
          that succeeds.
        </div>
      )}

      <div style={{ display: "grid", gap: 8 }}>
        <input
          value={canvasBaseUrl}
          onChange={(e) => setCanvasBaseUrl(e.target.value)}
          placeholder="https://canvas.tamu.edu"
          style={{ padding: 8, maxWidth: 420 }}
          autoComplete="off"
        />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <button
            type="button"
            onClick={() => void onSignInWithCanvas()}
            style={{ padding: "8px 12px", fontWeight: 600 }}
            disabled={canvasBusy}
          >
            {canvasBusy ? "Working…" : "Sign in with Canvas"}
          </button>
          <button
            type="button"
            onClick={onSyncCanvas}
            style={{ padding: "8px 12px" }}
            disabled={canvasBusy || !canvasStatus?.connected}
            title={!canvasStatus?.connected ? "Connect with Sign in with Canvas first" : "Sync courses from Canvas"}
          >
            Sync now
          </button>
        </div>
        {!canvasStatus?.connected ? (
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            Typing the URL alone does nothing — you must sign in (NetID / Duo) so StudyFlows can capture the session.
          </div>
        ) : null}
      </div>

      {!compact ? (
        <>
          <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}>
              Web fallback: paste browser session cookie
            </summary>
            <form onSubmit={onConnectSession} style={{ display: "grid", gap: 8, marginTop: 8 }}>
              <textarea
                value={sessionCookie}
                onChange={(e) => setSessionCookie(e.target.value)}
                placeholder="canvas_session value"
                rows={3}
                style={{ padding: 8, maxWidth: 560, fontFamily: "inherit" }}
              />
              <button type="submit" style={{ padding: "8px 12px", width: "fit-content" }} disabled={canvasBusy || !sessionCookie.trim()}>
                Connect with browser session
              </button>
            </form>
          </details>

          <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}>
              OAuth developer key
            </summary>
            <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
              <button
                type="button"
                onClick={onConnectOAuth}
                style={{ padding: "8px 12px", width: "fit-content" }}
                disabled={canvasBusy || !canvasStatus?.oauth_configured}
              >
                Connect with Canvas OAuth
              </button>
            </div>
          </details>

          <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}>
              Alternate: mobile QR login URL
            </summary>
            <form onSubmit={onConnectQr} style={{ display: "grid", gap: 8, marginTop: 8 }}>
              <textarea
                value={qrUrl}
                onChange={(e) => setQrUrl(e.target.value)}
                placeholder="https://sso.canvaslms.com/canvas/login?…"
                rows={3}
                style={{ padding: 8, maxWidth: 560, fontFamily: "inherit" }}
              />
              <button type="submit" style={{ padding: "8px 12px", width: "fit-content" }} disabled={canvasBusy || !qrUrl.trim()}>
                Connect with QR OAuth
              </button>
            </form>
          </details>

          <details style={{ marginTop: 4 }} open={showPat}>
            <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }} onClick={() => setShowPat((v) => !v)}>
              Advanced: personal access token
            </summary>
            <form onSubmit={onConnectPat} style={{ display: "grid", gap: 8, marginTop: 8 }}>
              <input
                value={canvasToken}
                onChange={(e) => setCanvasToken(e.target.value)}
                placeholder="Personal access token"
                type="password"
                style={{ padding: 8, maxWidth: 420 }}
                autoComplete="off"
              />
              <button
                type="submit"
                style={{ padding: "8px 12px", width: "fit-content" }}
                disabled={canvasBusy || !canvasBaseUrl.trim() || !canvasToken.trim()}
              >
                Connect with PAT
              </button>
            </form>
          </details>
        </>
      ) : null}

      {syncResult ? (
        <div style={{ fontSize: 13, color: "#374151" }}>
          Synced {syncResult.courses_upserted} courses, {syncResult.assignments_upserted} assignments
          {typeof syncResult.files_upserted === "number" ? `, ${syncResult.files_upserted} files` : ""}
        </div>
      ) : null}
    </div>
  );
}
