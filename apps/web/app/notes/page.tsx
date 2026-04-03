"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPost, apiPatch, toErrorMessage } from "../../lib/api";
import type { Notebook, NoteDocument, NotePage, Resource } from "../../lib/types";
import { HandwritingCanvas, type InkElement } from "../../components/HandwritingCanvas";

export default function NotesPage() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [docs, setDocs] = useState<NoteDocument[]>([]);
  const [pages, setPages] = useState<NotePage[]>([]);
  const [linkedResources, setLinkedResources] = useState<Resource[]>([]);

  const [notebookId, setNotebookId] = useState<string>("");
  const [docId, setDocId] = useState<string>("");

  const [newDocTitle, setNewDocTitle] = useState("");
  const [newPageIndex, setNewPageIndex] = useState(0);
  const [text, setText] = useState("");
  const [handwritingEnabled, setHandwritingEnabled] = useState(false);
  const [ink, setInk] = useState<InkElement | null>(null);
  const [linkedResourceId, setLinkedResourceId] = useState<string>("");

  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const [selectedPageId, setSelectedPageId] = useState<string>("");
  const selectedPage = useMemo(
    () => pages.find((p) => p.id === selectedPageId) ?? pages[0] ?? null,
    [pages, selectedPageId]
  );

  async function refresh() {
    setError(null);
    setIsLoading(true);
    try {
      const nbs = await apiGet<Notebook[]>("/notebooks");
      setNotebooks(nbs);
      const nb = notebookId || nbs[0]?.id || "";
      setNotebookId(nb);
      if (!nb) return;
      const selectedNotebook = nbs.find((n) => n.id === nb);
      if (selectedNotebook?.course_id) {
        setLinkedResources(
          await apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(selectedNotebook.course_id)}&limit=100&offset=0`)
        );
      } else {
        setLinkedResources([]);
      }

      const d = await apiGet<NoteDocument[]>(`/notebooks/${nb}/note-documents`);
      setDocs(d);
      const did = docId || d[0]?.id || "";
      setDocId(did);
      if (!did) {
        setPages([]);
        return;
      }
      const ps = await apiGet<NotePage[]>(`/note-documents/${did}/pages`);
      setPages(ps);
      const preferred = selectedPageId || ps[0]?.id || "";
      setSelectedPageId(preferred);
      const p0 = ps.find((p) => p.id === preferred) ?? ps[0] ?? null;
      if (p0?.extracted_text !== undefined) setText(p0.extracted_text ?? "");
      // Load ink element if present
      const data = (p0?.page_data_json ?? null) as any;
      const inkEl =
        data && typeof data === "object" && Array.isArray(data.elements)
          ? (data.elements.find((e: any) => e && e.type === "ink") as InkElement | undefined)
          : undefined;
      setInk(inkEl ?? { id: "ink1", type: "ink", strokes: [] });
      const linked =
        data && typeof data === "object" && typeof data.linked_resource_id === "string"
          ? (data.linked_resource_id as string)
          : "";
      setLinkedResourceId(linked);
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

  async function createDoc() {
    if (!notebookId || !newDocTitle.trim()) return;
    setError(null);
    try {
      await apiPost<NoteDocument>("/note-documents", { notebook_id: notebookId, title: newDocTitle, note_type: "typed" });
      setNewDocTitle("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function createPage() {
    if (!docId) return;
    setError(null);
    try {
      const page = await apiPost<NotePage>("/note-pages", {
        note_document_id: docId,
        page_index: newPageIndex,
        text: ""
      });
      setSelectedPageId(page.id);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function savePage() {
    if (!selectedPage) return;
    setError(null);
    try {
      const normalizedText = text.trim();
      const fallbackInkText =
        handwritingEnabled && ink && normalizedText.length === 0
          ? `[handwriting-only note, strokes=${ink.strokes.length}]`
          : normalizedText;
      const payload: Record<string, unknown> = { text: fallbackInkText };
      if (handwritingEnabled && ink) {
        payload.page_data_json = {
          version: 1,
          linked_resource_id: linkedResourceId || null,
          elements: [
            { id: "text1", type: "text", content: fallbackInkText },
            ink
          ]
        };
      } else if (linkedResourceId) {
        payload.page_data_json = {
          version: 1,
          linked_resource_id: linkedResourceId,
          elements: [{ id: "text1", type: "text", content: fallbackInkText }]
        };
      }
      await apiPatch<NotePage>(`/note-pages/${selectedPage.id}`, payload);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function deleteDoc() {
    if (!docId) return;
    if (!window.confirm("Delete this document and all its pages?")) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/note-documents/${docId}`);
      setDocId("");
      setPages([]);
      setText("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function deletePage() {
    if (!selectedPage) return;
    if (!window.confirm("Delete this page?")) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/note-pages/${selectedPage.id}`);
      setPages([]);
      setText("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Notes</h1>
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading notes..." /> : null}

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Notebook</div>
          <select
            value={notebookId}
            onChange={(e) => {
              setNotebookId(e.target.value);
              setDocId("");
              refresh();
            }}
            style={{ padding: 8 }}
          >
            {notebooks.map((n) => (
              <option key={n.id} value={n.id}>
                {n.title}
              </option>
            ))}
          </select>
          <button onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>
        {!isLoading && !error && notebooks.length === 0 ? (
          <EmptyState message="No notebooks yet. Create one in Notebooks first." />
        ) : null}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Document</div>
          <select
            value={docId}
            onChange={(e) => {
              setDocId(e.target.value);
              refresh();
            }}
            style={{ padding: 8 }}
          >
            {docs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
          <input
            value={newDocTitle}
            onChange={(e) => setNewDocTitle(e.target.value)}
            placeholder="New doc title"
            style={{ padding: 8, minWidth: 220 }}
          />
          <button onClick={createDoc} style={{ padding: "8px 12px" }}>
            Create doc
          </button>
          <button onClick={deleteDoc} style={{ padding: "8px 12px" }} disabled={!docId}>
            Delete doc
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Pages</div>
          <input
            type="number"
            value={newPageIndex}
            onChange={(e) => setNewPageIndex(Number(e.target.value))}
            style={{ padding: 8, width: 90 }}
            min={0}
          />
          <button onClick={createPage} style={{ padding: "8px 12px" }}>
            Add page
          </button>
          <div style={{ color: "#555", fontSize: 12 }}>Loaded pages: {pages.length}</div>
        </div>
      </div>

      <div className="card" style={{ display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>Typed page editor</div>
        {!isLoading && !selectedPage ? <EmptyState message="Create a page to start writing." /> : null}
        {selectedPage && (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 600, fontSize: 12 }}>Select page</div>
              <select
                value={selectedPage.id}
                onChange={(e) => {
                  setSelectedPageId(e.target.value);
                  const p = pages.find((x) => x.id === e.target.value);
                  setText(p?.extracted_text ?? "");
                  const data = (p?.page_data_json ?? null) as any;
                  const inkEl =
                    data && typeof data === "object" && Array.isArray(data.elements)
                      ? (data.elements.find((el: any) => el && el.type === "ink") as InkElement | undefined)
                      : undefined;
                  setInk(inkEl ?? { id: "ink1", type: "ink", strokes: [] });
                  setLinkedResourceId(
                    data && typeof data === "object" && typeof data.linked_resource_id === "string"
                      ? (data.linked_resource_id as string)
                      : ""
                  );
                }}
                style={{ padding: 8 }}
              >
                {pages.map((p) => (
                  <option key={p.id} value={p.id}>
                    page {p.page_index + 1}
                  </option>
                ))}
              </select>
              <div style={{ color: "#555", fontSize: 12 }}>id: {selectedPage.id}</div>
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={12}
              style={{ width: "100%", padding: 10, fontFamily: "inherit" }}
            />
            <div style={{ height: 8 }} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ fontWeight: 600, fontSize: 12 }}>Linked resource</div>
              <select value={linkedResourceId} onChange={(e) => setLinkedResourceId(e.target.value)} style={{ padding: 8 }}>
                <option value="">None</option>
                {linkedResources.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ height: 8 }} />
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={handwritingEnabled}
                onChange={(e) => setHandwritingEnabled(e.target.checked)}
              />
              <span style={{ fontWeight: 600 }}>Handwriting</span>
              <span style={{ color: "#555", fontSize: 12 }}>(minimal save/load only)</span>
            </label>
            {handwritingEnabled && (
              <HandwritingCanvas
                key={selectedPage.id}
                initial={ink ?? undefined}
                onChange={(el) => setInk(el)}
              />
            )}
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button onClick={savePage} style={{ padding: "8px 12px" }}>
                Save
              </button>
              <button onClick={deletePage} style={{ padding: "8px 12px" }}>
                Delete page
              </button>
              <div style={{ color: "#555", fontSize: 12 }}>
                This page is indexed via linked ResourceChunks, so it should show up in Search/Agent once saved.
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

