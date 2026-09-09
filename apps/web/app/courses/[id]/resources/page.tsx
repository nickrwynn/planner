"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../../../components/async-state";
import { DocumentScan } from "../../../../components/document-scan";
import { apiDelete, apiGet, apiPatch, apiPost, apiPostForm, toErrorMessage } from "../../../../lib/api";
import type { Resource, ResourceBatchUploadResult } from "../../../../lib/types";

type GoogleStatus = {
  connected: boolean;
  oauth_configured: boolean;
  account_email?: string | null;
  account_name?: string | null;
  last_sync_error?: string | null;
};

type DriveFile = {
  id: string;
  name: string;
  mime_type?: string | null;
  modified_time?: string | null;
  size?: number | null;
};

function moduleMeta(r: Resource): { name: string; position: number } {
  const meta = (r.metadata_json && typeof r.metadata_json === "object" ? r.metadata_json : {}) as Record<
    string,
    unknown
  >;
  const name = typeof meta.canvas_module_name === "string" && meta.canvas_module_name.trim()
    ? meta.canvas_module_name.trim()
    : r.source_type?.startsWith("canvas")
      ? "Other Canvas materials"
      : "Uploaded & other";
  const position =
    typeof meta.canvas_module_position === "number"
      ? meta.canvas_module_position
      : Number(meta.canvas_module_position) || (name === "Uploaded & other" ? 10_000 : 9_000);
  return { name, position };
}

export default function CourseResourcesPage({ params }: { params: { id: string } }) {
  const courseId = params.id;
  const [resources, setResources] = useState<Resource[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [batchResults, setBatchResults] = useState<ResourceBatchUploadResult[]>([]);

  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [driveQuery, setDriveQuery] = useState("");
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [driveBusy, setDriveBusy] = useState(false);
  const [driveBanner, setDriveBanner] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [rows, status] = await Promise.all([
        apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(courseId)}`),
        apiGet<GoogleStatus>("/integrations/google/status").catch(() => null),
      ]);
      setResources(rows);
      setGoogleStatus(status);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("google") === "connected") {
      setDriveBanner("Google Drive connected. Search and import files below.");
    } else if (params.get("google") === "error") {
      setDriveBanner(`Google Drive failed${params.get("reason") ? `: ${params.get("reason")}` : ""}.`);
    }
    refresh();
  }, [refresh]);

  const groupedResources = useMemo(() => {
    const groups = new Map<string, { position: number; items: Resource[] }>();
    for (const r of resources) {
      const { name, position } = moduleMeta(r);
      const g = groups.get(name) || { position, items: [] };
      g.position = Math.min(g.position, position);
      g.items.push(r);
      groups.set(name, g);
    }
    return [...groups.entries()]
      .sort((a, b) => a[1].position - b[1].position || a[0].localeCompare(b[0]))
      .map(([name, g]) => ({
        name,
        items: g.items.slice().sort((a, b) => a.title.localeCompare(b.title)),
      }));
  }, [resources]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("course_id", courseId);
      if (title) form.append("title", title);
      await apiPostForm<Resource>("/resources/upload", form);
      setFile(null);
      setTitle("");
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onBulkUpload(e: React.FormEvent) {
    e.preventDefault();
    const input = (e.target as HTMLFormElement).elements.namedItem("bulk") as HTMLInputElement | null;
    const files = Array.from(input?.files ?? []);
    if (files.length === 0) return;
    setError(null);
    setBatchResults([]);
    try {
      const form = new FormData();
      for (const f of files) form.append("files", f);
      form.append("course_id", courseId);
      setBatchResults(await apiPostForm<ResourceBatchUploadResult[]>("/resources/upload-batch", form));
      if (input) input.value = "";
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function connectGoogle() {
    setDriveBusy(true);
    setError(null);
    try {
      const returnTo = `/courses/${courseId}/resources`;
      const res = await apiPost<{ authorize_url: string }>("/integrations/google/oauth/start", {
        return_to: returnTo,
      });
      const { openOAuthAuthorizeUrl } = await import("../../../../lib/oauth-browser");
      const mode = await openOAuthAuthorizeUrl(res.authorize_url);
      if (mode === "browser") {
        setDriveBanner(
          "Complete Google sign-in in the browser window. When it finishes, return here and tap Refresh."
        );
      }
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setDriveBusy(false);
    }
  }

  async function disconnectGoogle() {
    if (!window.confirm("Disconnect Google Drive from StudyFlows?")) return;
    setDriveBusy(true);
    try {
      setGoogleStatus(await apiDelete<GoogleStatus>("/integrations/google/disconnect"));
      setDriveFiles([]);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setDriveBusy(false);
    }
  }

  async function searchDrive(e?: React.FormEvent) {
    e?.preventDefault();
    setDriveBusy(true);
    setError(null);
    try {
      const q = driveQuery.trim();
      const rows = await apiGet<DriveFile[]>(
        `/integrations/google/files?limit=30${q ? `&q=${encodeURIComponent(q)}` : ""}`
      );
      setDriveFiles(rows);
      if (!rows.length) setDriveBanner("No matching Drive files (PDFs, text, images, or Google Docs).");
      else setDriveBanner(null);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setDriveBusy(false);
    }
  }

  async function importDriveFile(f: DriveFile) {
    setImportingId(f.id);
    setError(null);
    try {
      await apiPost("/integrations/google/import", {
        file_id: f.id,
        course_id: courseId,
        title: f.name,
      });
      setDriveBanner(`Imported “${f.name}”. Indexing will run in the background.`);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setImportingId(null);
    }
  }

  async function onRename(r: Resource) {
    const next = window.prompt("New resource title", r.title);
    if (!next?.trim()) return;
    try {
      await apiPatch<Resource>(`/resources/${r.id}`, { title: next.trim() });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onDelete(r: Resource) {
    if (!window.confirm(`Delete resource "${r.title}"?`)) return;
    try {
      await apiDelete<{ ok: boolean }>(`/resources/${r.id}`);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onSendToNotes(r: Resource) {
    setError(null);
    try {
      const result = await apiPost<{ pages_created: number; note_document_id: string }>(
        `/resources/${r.id}/send-to-notes`,
        {}
      );
      window.alert(`Sent ${result.pages_created} page(s) to notes (doc ${result.note_document_id}).`);
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Resources</h1>
        <p className="pageIntro">
          Upload textbooks and readings, or import from Google Drive. Indexed PDFs/images can be sent into notes for
          StudyFlows.
        </p>
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ fontWeight: 600 }}>Upload textbook / reading</div>
        <form onSubmit={onUpload} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (optional)"
            style={{ padding: 8, minWidth: 220 }}
          />
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!file}>
            Upload
          </button>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </form>
        <form onSubmit={onBulkUpload} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input name="bulk" type="file" multiple />
          <button type="submit" style={{ padding: "8px 12px" }}>
            Bulk upload
          </button>
        </form>
        {batchResults.length > 0 ? (
          <div style={{ display: "grid", gap: 4, fontSize: 13 }}>
            {batchResults.map((row, idx) => (
              <div key={`${row.filename}-${idx}`} style={{ color: row.status === "accepted" ? "#166534" : "#b91c1c" }}>
                {row.status.toUpperCase()}: {row.filename}
                {row.reason ? ` — ${row.reason}` : ""}
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <DocumentScan
          onPdfReady={async (pdf) => {
            setError(null);
            const form = new FormData();
            // Explicit filename helps iOS Blob/File fallbacks through multipart upload.
            form.append("file", pdf, pdf.name || "Scan.pdf");
            form.append("course_id", courseId);
            form.append("title", (pdf.name || "Scan.pdf").replace(/\.pdf$/i, "") || "Scan");
            await apiPostForm<Resource>("/resources/upload", form);
            await refresh();
          }}
        />
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ fontWeight: 600 }}>Google Drive</div>
        <div style={{ fontSize: 13, color: "#555" }}>
          Connect your Google account, then import PDFs, images, text files, or Google Docs (exported as PDF) into this
          course.
        </div>
        {driveBanner ? (
          <div style={{ fontSize: 13, color: driveBanner.toLowerCase().includes("fail") ? "#b91c1c" : "#166534" }}>
            {driveBanner}
          </div>
        ) : null}
        {googleStatus?.connected ? (
          <div style={{ fontSize: 13, color: "#166534" }}>
            Connected{googleStatus.account_email ? ` as ${googleStatus.account_email}` : ""}
            {googleStatus.account_name ? ` (${googleStatus.account_name})` : ""}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "#6b7280" }}>
            {googleStatus?.oauth_configured === false
              ? "Google OAuth is not configured yet. Add GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET to the server .env, set the redirect URI in Google Cloud Console to https://app.mystudyflow.app/backend/integrations/google/oauth/callback, then restart the API. Connect opens Google in an in-app/system browser."
              : "Not connected — Connect opens Google sign-in in a browser window for authorization."}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {!googleStatus?.connected ? (
            <button type="button" disabled={driveBusy || googleStatus?.oauth_configured === false} onClick={connectGoogle} style={{ padding: "8px 12px" }}>
              Connect Google Drive
            </button>
          ) : (
            <>
              <button type="button" disabled={driveBusy} onClick={() => void searchDrive()} style={{ padding: "8px 12px" }}>
                Browse recent files
              </button>
              <button type="button" disabled={driveBusy} onClick={disconnectGoogle} style={{ padding: "8px 12px" }}>
                Disconnect
              </button>
            </>
          )}
        </div>
        {googleStatus?.connected ? (
          <>
            <form onSubmit={searchDrive} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                value={driveQuery}
                onChange={(e) => setDriveQuery(e.target.value)}
                placeholder="Search Drive by name…"
                style={{ padding: 8, minWidth: 220 }}
              />
              <button type="submit" disabled={driveBusy} style={{ padding: "8px 12px" }}>
                Search
              </button>
            </form>
            {driveFiles.length > 0 ? (
              <div style={{ display: "grid", gap: 8 }}>
                {driveFiles.map((f) => (
                  <div key={f.id} style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{f.name}</div>
                      <div style={{ fontSize: 12, color: "#6b7280" }}>
                        {f.mime_type || "file"}
                        {f.modified_time ? ` · ${new Date(f.modified_time).toLocaleString()}` : ""}
                      </div>
                    </div>
                    <button
                      type="button"
                      style={{ padding: "6px 10px" }}
                      disabled={importingId === f.id}
                      onClick={() => void importDriveFile(f)}
                    >
                      {importingId === f.id ? "Importing…" : "Import"}
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      {error ? <ErrorState message={error} onRetry={refresh} /> : null}

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Course files</div>
        <div style={{ fontSize: 13, color: "#555", marginBottom: 8 }}>
          Grouped like Canvas modules (Week 1…, Student Resources, …). Re-sync Canvas to refresh.
        </div>
        {isLoading ? <LoadingState label="Loading resources..." /> : null}
        {!isLoading && groupedResources.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 16 }}>
              {groupedResources.map((group) => (
                <div key={group.name} style={{ display: "grid", gap: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 14, borderTop: "1px solid #e5e7eb", paddingTop: 10 }}>
                    {group.name}
                    <span style={{ marginLeft: 8, fontWeight: 500, color: "#6b7280" }}>{group.items.length}</span>
                  </div>
                  {group.items.map((r) => (
                    <div key={r.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <div>
                        <div style={{ fontWeight: 600 }}>
                          <Link href={`/resources/${r.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                            {r.title}
                          </Link>
                          {r.source_type === "google_drive" ? (
                            <span style={{ marginLeft: 8, fontSize: 11, color: "#0f766e" }}>Drive</span>
                          ) : r.source_type?.startsWith("canvas") ? (
                            <span style={{ marginLeft: 8, fontSize: 11, color: "#1d4ed8" }}>Canvas</span>
                          ) : null}
                        </div>
                        <div style={{ color: "#555", fontSize: 13 }}>
                          {r.resource_type ?? "file"} · index={r.index_status}
                        </div>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          onClick={() => onSendToNotes(r)}
                          style={{ padding: "6px 10px" }}
                          disabled={!(r.index_status === "done" || r.lifecycle_state === "searchable")}
                          title="Requires indexed text chunks"
                        >
                          Send to notes
                        </button>
                        <button onClick={() => onRename(r)} style={{ padding: "6px 10px" }}>
                          Rename
                        </button>
                        <button onClick={() => onDelete(r)} style={{ padding: "6px 10px" }}>
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </ContentState>
        ) : null}
        {!isLoading && !error && resources.length === 0 ? (
          <EmptyState message="No resources yet. Upload a file, sync Canvas, or import from Google Drive." />
        ) : null}
      </div>
    </div>
  );
}
