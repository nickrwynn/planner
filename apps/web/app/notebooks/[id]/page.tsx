"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../../components/async-state";
import { apiGet, apiPost, toErrorMessage } from "../../../lib/api";
import type { NoteDocument, Notebook } from "../../../lib/types";

export default function NotebookDetailPage({ params }: { params: { id: string } }) {
  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [docs, setDocs] = useState<NoteDocument[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      setNotebook(await apiGet<Notebook>(`/notebooks/${params.id}`));
      setDocs(await apiGet<NoteDocument[]>(`/notebooks/${params.id}/note-documents`));
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function createDoc(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setError(null);
    try {
      await apiPost<NoteDocument>("/note-documents", {
        notebook_id: params.id,
        title: newTitle.trim(),
        note_type: "typed"
      });
      setNewTitle("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Notebook</h1>
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading notebook..." /> : null}
      {!isLoading && !error && !notebook ? <EmptyState message="Notebook not found." /> : null}
      {notebook && (
        <div className="card" style={{ display: "grid", gap: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{notebook.title}</div>
          <div style={{ color: "#555", fontSize: 12 }}>id: {notebook.id}</div>
        </div>
      )}

      {notebook ? (
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Create document</div>
          <form onSubmit={createDoc} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Document title"
              style={{ padding: 8, minWidth: 240 }}
            />
            <button type="submit" style={{ padding: "8px 12px" }} disabled={!newTitle.trim()}>
              Create
            </button>
            <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
              Refresh
            </button>
          </form>
        </div>
      ) : null}

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Documents</div>
        <div style={{ display: "grid", gap: 8 }}>
          {docs.map((d) => (
            <div key={d.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div style={{ fontWeight: 600 }}>{d.title}</div>
              <div style={{ color: "#555", fontSize: 12 }}>{d.id}</div>
            </div>
          ))}
          {!isLoading && !error && docs.length === 0 ? <EmptyState message="No documents yet." /> : null}
        </div>
      </div>
    </div>
  );
}

