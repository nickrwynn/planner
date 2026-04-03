"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import type { Course, Notebook } from "../../lib/types";

export default function NotebooksPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [parentId, setParentId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function refresh(nextCourseId?: string) {
    setError(null);
    setIsLoading(true);
    try {
      const cs = await apiGet<Course[]>("/courses");
      setCourses(cs);
      const selected = nextCourseId ?? courseId ?? cs[0]?.id ?? "";
      setCourseId(selected);
      if (selected) {
        setNotebooks(await apiGet<Notebook[]>(`/notebooks?course_id=${encodeURIComponent(selected)}`));
      } else {
        setNotebooks([]);
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
      await apiPost<Notebook>("/notebooks", { course_id: courseId, parent_id: parentId || null, title });
      setTitle("");
      setParentId("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onRename(n: Notebook) {
    const next = window.prompt("New notebook title", n.title);
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch<Notebook>(`/notebooks/${n.id}`, { title: next.trim() });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onDelete(n: Notebook) {
    if (!window.confirm(`Delete notebook "${n.title}"? This will delete its documents/pages.`)) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/notebooks/${n.id}`);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Notebooks</h1>

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

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Create notebook</div>
        <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Notebook title"
            style={{ padding: 8, minWidth: 260 }}
          />
          <select value={parentId} onChange={(e) => setParentId(e.target.value)} style={{ padding: 8 }}>
            <option value="">No parent (root)</option>
            {notebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.title}
              </option>
            ))}
          </select>
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!courseId || !title}>
            Create
          </button>
        </form>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Notebooks</div>
        <div style={{ display: "grid", gap: 8 }}>
          {isLoading ? <LoadingState label="Loading..." /> : null}
          {notebooks.map((n) => (
            <div key={n.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  <Link href={`/notebooks/${n.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                    {n.title}
                  </Link>
                </div>
                <div style={{ color: "#555", fontSize: 13 }}>
                  course={n.course_id ?? "—"} • parent={n.parent_id ?? "root"}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button onClick={() => onRename(n)} style={{ padding: "6px 10px" }}>
                  Rename
                </button>
                <button onClick={() => onDelete(n)} style={{ padding: "6px 10px" }}>
                  Delete
                </button>
                <div style={{ color: "#555", fontSize: 12 }}>{n.id}</div>
              </div>
            </div>
          ))}
          {!isLoading && !error && notebooks.length === 0 ? (
            <EmptyState message="No notebooks for this course yet." />
          ) : null}
        </div>
      </div>
    </div>
  );
}

