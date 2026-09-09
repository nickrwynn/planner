"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../../../lib/api";
import type { Notebook } from "../../../../lib/types";

export default function CourseNotebooksPage({ params }: { params: { id: string } }) {
  const courseId = params.id;
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      setNotebooks(await apiGet<Notebook[]>(`/notebooks?course_id=${encodeURIComponent(courseId)}`));
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    try {
      await apiPost<Notebook>("/notebooks", { course_id: courseId, title: title.trim() });
      setTitle("");
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onRename(n: Notebook) {
    const next = window.prompt("New notebook title", n.title);
    if (!next?.trim()) return;
    try {
      await apiPatch<Notebook>(`/notebooks/${n.id}`, { title: next.trim() });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onDelete(n: Notebook) {
    if (!window.confirm(`Delete notebook "${n.title}"?`)) return;
    try {
      await apiDelete<{ ok: boolean }>(`/notebooks/${n.id}`);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Notebooks</h1>
        <p className="pageIntro">Course notes live here. Open a notebook to add pages.</p>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Create notebook</div>
        <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Notebook title"
            style={{ padding: 8, minWidth: 260 }}
          />
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!title.trim()}>
            Create
          </button>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </form>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Notebooks</div>
        {isLoading ? <LoadingState label="Loading notebooks..." /> : null}
        {!isLoading && notebooks.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 8 }}>
              {notebooks.map((n) => (
                <div key={n.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ fontWeight: 600 }}>
                    <Link href={`/notebooks/${n.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                      {n.title}
                    </Link>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => onRename(n)} style={{ padding: "6px 10px" }}>
                      Rename
                    </button>
                    <button onClick={() => onDelete(n)} style={{ padding: "6px 10px" }}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </ContentState>
        ) : null}
        {!isLoading && !error && notebooks.length === 0 ? (
          <EmptyState message="No notebooks yet." />
        ) : null}
      </div>
    </div>
  );
}
