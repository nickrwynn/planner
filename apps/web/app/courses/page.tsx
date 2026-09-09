"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, toErrorMessage } from "../../lib/api";
import { canAutoCaptureCanvasSession, captureCanvasSession } from "../../lib/canvas-login";
import type { CanvasStatus, CanvasSyncResult, Course } from "../../lib/types";

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [term, setTerm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(true);

  const [canvasStatus, setCanvasStatus] = useState<CanvasStatus | null>(null);
  const [canvasBaseUrl, setCanvasBaseUrl] = useState("");
  const [canvasToken, setCanvasToken] = useState("");
  const [sessionCookie, setSessionCookie] = useState("");
  const [qrUrl, setQrUrl] = useState("");
  const [showPat, setShowPat] = useState(false);
  const [canvasBusy, setCanvasBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<CanvasSyncResult | null>(null);
  const [oauthBanner, setOauthBanner] = useState<string | null>(null);
  const [nativeCanvasLogin, setNativeCanvasLogin] = useState(false);

  async function refresh() {
    setError(null);
    setIsLoading(true);
    try {
      const [courseRows, status] = await Promise.all([
        apiGet<Course[]>("/courses"),
        apiGet<CanvasStatus>("/integrations/canvas/status"),
      ]);
      setCourses(courseRows);
      setCanvasStatus(status);
      if (!canvasBaseUrl) {
        setCanvasBaseUrl(status.base_url || status.default_base_url || "");
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    setNativeCanvasLogin(canAutoCaptureCanvasSession());
    const params = new URLSearchParams(window.location.search);
    const canvas = params.get("canvas");
    const google = params.get("google");
    if (canvas === "connected") {
      setOauthBanner("Canvas OAuth connected. Syncing courses…");
    } else if (canvas === "error") {
      setOauthBanner(`Canvas OAuth failed${params.get("reason") ? `: ${params.get("reason")}` : ""}.`);
    } else if (google === "connected") {
      setOauthBanner("Google Drive connected. Open a course → Resources to import files.");
    } else if (google === "error") {
      setOauthBanner(`Google Drive OAuth failed${params.get("reason") ? `: ${params.get("reason")}` : ""}.`);
    }
    void refresh().then(() => {
      if (canvas !== "connected") return;
      void (async () => {
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
      })();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sorted = useMemo(
    () => [...courses].sort((a, b) => a.name.localeCompare(b.name)),
    [courses]
  );

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      await apiPost<Course>("/courses", {
        name: name.trim(),
        code: code.trim() || null,
        term: term.trim() || null,
        source_type: "manual",
      });
      setName("");
      setCode("");
      setTerm("");
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onRename(course: Course) {
    const next = window.prompt("New course name", course.name);
    if (!next?.trim()) return;
    try {
      await apiPatch<Course>(`/courses/${course.id}`, { name: next.trim() });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onDelete(course: Course) {
    if (!window.confirm(`Delete course "${course.name}"? This removes its tasks, resources, and notebooks.`)) {
      return;
    }
    try {
      await apiDelete<{ ok: boolean }>(`/courses/${course.id}`);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

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

  async function onSignInWithCanvas() {
    const base = canvasBaseUrl.trim() || "https://canvas.tamu.edu";
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
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Courses</h1>
        <p className="pageIntro">
          Add courses manually anytime — including Blackboard / Brightspace classes we don’t sync yet. Canvas users can
          also import below.
        </p>
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700 }}>Add a course manually</div>
            <div style={{ color: "#555", fontSize: 13, marginTop: 4 }}>
              Use this for any class your school LMS doesn’t support here yet (Blackboard, Brightspace, etc.). You can
              upload PDFs or import from Google Drive on the course Resources page.
            </div>
          </div>
          <button type="button" onClick={() => setShowCreate((v) => !v)} style={{ padding: "8px 12px" }}>
            {showCreate ? "Hide" : "Add course"}
          </button>
        </div>
        {showCreate ? (
          <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Course name (e.g. MATH Probability)"
              style={{ padding: 8, minWidth: 240 }}
              required
            />
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Code (optional, e.g. MATH 411)"
              style={{ padding: 8, minWidth: 140 }}
            />
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Term (optional, e.g. Fall 2026)"
              style={{ padding: 8, minWidth: 140 }}
            />
            <button type="submit" style={{ padding: "8px 12px" }} disabled={!name.trim()}>
              Create course
            </button>
          </form>
        ) : null}
      </div>

      <div className="card" style={{ display: "grid", gap: 10 }}>
        <div style={{ fontWeight: 700 }}>Canvas</div>
        <div style={{ color: "#555", fontSize: 14 }}>
          {nativeCanvasLogin
            ? "Sign in once with NetID / Duo in the app. StudyFlows captures the session and syncs courses automatically."
            : "In the StudyFlows iPad app, Canvas sign-in is automatic after NetID / Duo. On the web, browsers block reading Canvas cookies — use the fallback below or a school OAuth developer key."}
        </div>
        {oauthBanner ? (
          <div style={{ fontSize: 13, color: oauthBanner.includes("failed") ? "#b91c1c" : "#166534" }}>{oauthBanner}</div>
        ) : null}
        {canvasStatus?.connected ? (
          <div style={{ fontSize: 13, color: "#166534" }}>
            Connected{canvasStatus.canvas_user_name ? ` as ${canvasStatus.canvas_user_name}` : ""}
            {canvasStatus.auth_mode ? ` · ${canvasStatus.auth_mode}` : ""}
            {canvasStatus.base_url ? ` · ${canvasStatus.base_url}` : ""}
            {canvasStatus.last_synced_at
              ? ` · last sync ${new Date(canvasStatus.last_synced_at).toLocaleString()} (${canvasStatus.last_sync_status || "n/a"})`
              : " · not synced yet"}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "#6b7280" }}>Not connected</div>
        )}
        {canvasStatus?.last_sync_error ? (
          <div style={{ fontSize: 13, color: "#b91c1c" }}>{canvasStatus.last_sync_error}</div>
        ) : null}

        <div style={{ display: "grid", gap: 8 }}>
          <input
            value={canvasBaseUrl}
            onChange={(e) => setCanvasBaseUrl(e.target.value)}
            placeholder="https://canvas.tamu.edu"
            style={{ padding: 8, maxWidth: 420 }}
            autoComplete="off"
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {nativeCanvasLogin ? (
              <button type="button" onClick={onSignInWithCanvas} style={{ padding: "8px 12px" }} disabled={canvasBusy}>
                {canvasBusy ? "Working…" : "Sign in with Canvas"}
              </button>
            ) : null}
            <button
              type="button"
              onClick={onSyncCanvas}
              style={{ padding: "8px 12px" }}
              disabled={canvasBusy || !canvasStatus?.connected}
            >
              Sync now
            </button>
          </div>
        </div>

        <details style={{ marginTop: 4 }}>
          <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}>
            Web fallback: paste browser session cookie
          </summary>
          <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#374151" }}>
              <li>
                Open{" "}
                <a href={canvasBaseUrl || "https://canvas.tamu.edu"} target="_blank" rel="noreferrer">
                  Canvas
                </a>{" "}
                and log in (NetID / Duo).
              </li>
              <li>
                DevTools → Application → Cookies → your Canvas domain → copy <code>canvas_session</code>.
              </li>
              <li>Paste below → Connect (syncs automatically).</li>
            </ol>
            <form onSubmit={onConnectSession} style={{ display: "grid", gap: 8 }}>
              <textarea
                value={sessionCookie}
                onChange={(e) => setSessionCookie(e.target.value)}
                placeholder="canvas_session value (or full Cookie header containing canvas_session=…)"
                rows={3}
                style={{ padding: 8, maxWidth: 560, fontFamily: "inherit" }}
              />
              <button type="submit" style={{ padding: "8px 12px", width: "fit-content" }} disabled={canvasBusy || !sessionCookie.trim()}>
                Connect with browser session
              </button>
            </form>
          </div>
        </details>

        <details style={{ marginTop: 4 }}>
          <summary style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}>
            Later: OAuth developer key (proper long-term path)
          </summary>
          <div style={{ display: "grid", gap: 8, marginTop: 8 }}>
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              {canvasStatus?.oauth_configured
                ? "Developer key is configured."
                : "Needs CANVAS_OAUTH_CLIENT_ID / CANVAS_OAUTH_CLIENT_SECRET from school admin."}
            </div>
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
              placeholder="https://sso.canvaslms.com/canvas/login?domain=…&code=…"
              rows={3}
              style={{ padding: 8, maxWidth: 560, fontFamily: "inherit" }}
            />
            <button type="submit" style={{ padding: "8px 12px", width: "fit-content" }} disabled={canvasBusy || !qrUrl.trim()}>
              Connect with QR OAuth
            </button>
          </form>
        </details>

        <details style={{ marginTop: 4 }} open={showPat}>
          <summary
            style={{ cursor: "pointer", fontSize: 13, color: "#374151" }}
            onClick={() => setShowPat((v) => !v)}
          >
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

        {syncResult ? (
          <div style={{ fontSize: 13, color: "#374151" }}>
            Synced {syncResult.courses_upserted} courses, {syncResult.assignments_upserted} assignments,{" "}
            {syncResult.syllabi_upserted} syllabi
            {typeof syncResult.files_upserted === "number" ? `, ${syncResult.files_upserted} files` : ""}
            {typeof syncResult.notebooks_upserted === "number"
              ? `, ${syncResult.notebooks_upserted} notebooks`
              : ""}
            {syncResult.errors.length ? ` · ${syncResult.errors.length} warning(s)` : ""}
          </div>
        ) : null}
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Your courses</div>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>

        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
        {isLoading ? <LoadingState label="Loading courses..." /> : null}

        {!isLoading && sorted.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 8 }}>
              {sorted.map((c) => (
                <div
                  key={c.id}
                  className="card"
                  style={{ padding: 12, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}
                >
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <Link
                        href={`/courses/${c.id}`}
                        style={{ textDecoration: "none", color: "inherit", fontWeight: 700, fontSize: 16 }}
                      >
                        {c.name}
                      </Link>
                      {c.source_type === "canvas" ? (
                        <span style={{ fontSize: 11, color: "#1d4ed8", border: "1px solid #93c5fd", padding: "1px 6px" }}>
                          Canvas
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, color: "#374151", border: "1px solid #d1d5db", padding: "1px 6px" }}>
                          Manual
                        </span>
                      )}
                    </div>
                    <div style={{ color: "#555", fontSize: 13 }}>
                      {c.code || "No code"} · {c.term || "No term"}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => onRename(c)} style={{ padding: "6px 10px" }}>
                      Rename
                    </button>
                    <button onClick={() => onDelete(c)} style={{ padding: "6px 10px" }}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </ContentState>
        ) : null}

        {!isLoading && !error && sorted.length === 0 ? (
          <EmptyState
            message="No courses yet. Add one locally, or connect Canvas OAuth and sync."
            action={
              <button type="button" onClick={() => setShowCreate(true)} style={{ padding: "8px 12px" }}>
                Add your first course
              </button>
            }
          />
        ) : null}
      </div>
    </div>
  );
}
