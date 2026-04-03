"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, apiPostForm, toErrorMessage } from "../../lib/api";
import type { Course, Resource, ResourceBatchUploadResult } from "../../lib/types";

export default function ResourcesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [bulkFiles, setBulkFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [resourceType, setResourceType] = useState("pdf");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [batchResults, setBatchResults] = useState<ResourceBatchUploadResult[]>([]);

  async function refresh(nextCourseId?: string) {
    setError(null);
    setIsLoading(true);
    try {
      const cs = await apiGet<Course[]>("/courses");
      setCourses(cs);
      const selected = nextCourseId ?? courseId ?? cs[0]?.id ?? "";
      setCourseId(selected);
      if (selected) {
        setResources(await apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(selected)}`));
      } else {
        setResources([]);
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId) return;
    setError(null);
    try {
      await apiPost<Resource>("/resources", { course_id: courseId, title, resource_type: resourceType });
      setTitle("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId || !file) return;
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("course_id", courseId);
      if (title) form.append("title", title);
      if (resourceType) form.append("resource_type", resourceType);

      await apiPostForm<Resource>("/resources/upload", form);
      setFile(null);
      setTitle("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onBulkUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId || bulkFiles.length === 0) return;
    setError(null);
    setBatchResults([]);
    try {
      const form = new FormData();
      for (const f of bulkFiles) form.append("files", f);
      form.append("course_id", courseId);
      if (resourceType) form.append("resource_type", resourceType);
      const result = await apiPostForm<ResourceBatchUploadResult[]>("/resources/upload-batch", form);
      setBatchResults(result);
      setBulkFiles([]);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onRename(r: Resource) {
    const next = window.prompt("New resource title", r.title);
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch<Resource>(`/resources/${r.id}`, { title: next.trim() });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onDelete(r: Resource) {
    if (!window.confirm(`Delete resource "${r.title}"?`)) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/resources/${r.id}`);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Resources</h1>

      <div className="card">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 600 }}>Course</div>
          <select
            value={courseId}
            onChange={(e) => {
              setCourseId(e.target.value);
              refresh(e.target.value);
            }}
            style={{ padding: 8 }}
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code ? `${c.code} — ` : ""}{c.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => refresh()} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>

        <div style={{ height: 12 }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Upload file (PDF/image)</div>
        <form onSubmit={onUpload} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ padding: 8, minWidth: 260 }}
          />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (optional)"
            style={{ padding: 8, minWidth: 260 }}
          />
          <select value={resourceType} onChange={(e) => setResourceType(e.target.value)} style={{ padding: 8 }}>
            <option value="pdf">pdf</option>
            <option value="image">image</option>
            <option value="link">link</option>
            <option value="other">other</option>
          </select>
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!courseId || !file}>
            Upload
          </button>
        </form>

        <div style={{ height: 16 }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Bulk upload</div>
        <form onSubmit={onBulkUpload} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            type="file"
            multiple
            onChange={(e) => setBulkFiles(Array.from(e.target.files ?? []))}
            style={{ padding: 8, minWidth: 260 }}
          />
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!courseId || bulkFiles.length === 0}>
            Upload {bulkFiles.length || ""} file(s)
          </button>
        </form>
        {batchResults.length > 0 && (
          <div style={{ marginTop: 8, display: "grid", gap: 4, fontSize: 13 }}>
            {batchResults.map((row, idx) => (
              <div key={`${row.filename}-${idx}`} style={{ color: row.status === "accepted" ? "#166534" : "#b91c1c" }}>
                {row.status.toUpperCase()}: {row.filename}
                {row.reason ? ` — ${row.reason}` : ""}
              </div>
            ))}
          </div>
        )}

        <div style={{ height: 16 }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Create resource (metadata only)</div>
        <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Resource title"
            style={{ padding: 8, minWidth: 260 }}
          />
          <select value={resourceType} onChange={(e) => setResourceType(e.target.value)} style={{ padding: 8 }}>
            <option value="pdf">pdf</option>
            <option value="image">image</option>
            <option value="link">link</option>
            <option value="other">other</option>
          </select>
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!courseId || !title}>
            Create
          </button>
        </form>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Resources</div>
        <div style={{ display: "grid", gap: 8 }}>
          {isLoading ? <LoadingState label="Loading..." /> : null}
          {resources.map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  <Link href={`/resources/${r.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                    {r.title}
                  </Link>
                </div>
                <div style={{ color: "#555", fontSize: 13 }}>
                  {r.resource_type ?? "—"} • parse={r.parse_status} • ocr={r.ocr_status} • index={r.index_status}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button onClick={() => onRename(r)} style={{ padding: "6px 10px" }}>
                  Rename
                </button>
                <button onClick={() => onDelete(r)} style={{ padding: "6px 10px" }}>
                  Delete
                </button>
                <div style={{ color: "#555", fontSize: 12 }}>{r.id}</div>
              </div>
            </div>
          ))}
          {!isLoading && !error && resources.length === 0 ? (
            <EmptyState message="No resources for this course yet." />
          ) : null}
        </div>
      </div>
    </div>
  );
}

