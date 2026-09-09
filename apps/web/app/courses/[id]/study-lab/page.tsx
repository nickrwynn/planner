"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../../../components/async-state";
import { StudyArtifactView } from "../../../../components/study-artifact-view";
import { apiGet, apiPost, toErrorMessage } from "../../../../lib/api";
import type { Resource } from "../../../../lib/types";

type ArtifactType = "summary" | "flashcards" | "quiz" | "sample-problems";

type ArtifactListItem = {
  id: string;
  course_id: string | null;
  artifact_type: string;
  title: string;
  created_at: string;
};

type StudyArtifactDetail = {
  id: string;
  title: string;
  artifact_type: string;
  content_json: Record<string, unknown> | null;
};

type ResourceSection = {
  key: string;
  title: string;
  kind: string;
  page_start: number | null;
  page_end: number | null;
  chunk_index_start: number;
};

function isLikelyTextbook(r: Resource): boolean {
  const mime = (r.mime_type || "").toLowerCase();
  const name = (r.original_filename || r.title || "").toLowerCase();
  return mime.includes("pdf") || name.endsWith(".pdf");
}

export default function CourseStudyLabPage({ params }: { params: { id: string } }) {
  const courseId = params.id;
  const [resources, setResources] = useState<Resource[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [sectionsByResource, setSectionsByResource] = useState<Record<string, ResourceSection[]>>({});
  const [selectedSections, setSelectedSections] = useState<Record<string, boolean>>({});
  const [sectionsLoading, setSectionsLoading] = useState(false);
  const [artifactType, setArtifactType] = useState<ArtifactType>("summary");
  const [artifacts, setArtifacts] = useState<ArtifactListItem[]>([]);
  const [artifactDetail, setArtifactDetail] = useState<StudyArtifactDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const selectedIds = useMemo(() => Object.keys(selected).filter((k) => selected[k]), [selected]);
  const selectedSectionKeys = useMemo(
    () => Object.keys(selectedSections).filter((k) => selectedSections[k]),
    [selectedSections]
  );
  const artifactsForCourse = useMemo(
    () => artifacts.filter((a) => a.course_id === courseId),
    [artifacts, courseId]
  );
  const primaryTextbookId = useMemo(() => {
    const textbooks = selectedIds.filter((id) => {
      const r = resources.find((x) => x.id === id);
      return r && isLikelyTextbook(r);
    });
    return textbooks[0] || null;
  }, [selectedIds, resources]);
  const activeSections = primaryTextbookId ? sectionsByResource[primaryTextbookId] || [] : [];

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      setResources(
        await apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(courseId)}&limit=100&offset=0`)
      );
      setArtifacts(await apiGet<ArtifactListItem[]>("/ai/artifacts?limit=50&offset=0"));
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    async function loadSections() {
      if (!primaryTextbookId) {
        setSelectedSections({});
        return;
      }
      if (sectionsByResource[primaryTextbookId]) return;
      setSectionsLoading(true);
      try {
        const rows = await apiGet<ResourceSection[]>(`/resources/${primaryTextbookId}/sections`);
        if (cancelled) return;
        setSectionsByResource((prev) => ({ ...prev, [primaryTextbookId]: rows }));
      } catch (e) {
        if (!cancelled) setError(toErrorMessage(e));
      } finally {
        if (!cancelled) setSectionsLoading(false);
      }
    }
    void loadSections();
    return () => {
      cancelled = true;
    };
  }, [primaryTextbookId, sectionsByResource]);

  async function loadArtifactDetail(id: string) {
    try {
      setArtifactDetail(await apiGet<StudyArtifactDetail>(`/ai/artifacts/${id}`));
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  function toggleResource(id: string, checked: boolean) {
    setSelected((prev) => ({ ...prev, [id]: checked }));
    if (!checked) {
      // Clear section picks when deselecting the active textbook.
      setSelectedSections({});
    }
  }

  async function runGeneration() {
    if (selectedIds.length === 0) return;
    if (primaryTextbookId && activeSections.length > 0 && selectedSectionKeys.length === 0) {
      setError("Pick at least one chapter/section under the textbook (or deselect the PDF to use other resources).");
      return;
    }
    setIsRunning(true);
    setError(null);
    try {
      const endpoint =
        artifactType === "summary"
          ? "/ai/summaries"
          : artifactType === "flashcards"
            ? "/ai/flashcards"
            : artifactType === "quiz"
              ? "/ai/quizzes"
              : "/ai/sample-problems";
      const created = await apiPost<{ artifact_id: string }>(endpoint, {
        course_id: courseId,
        resource_ids: selectedIds,
        section_keys: selectedSectionKeys,
      });
      await refresh();
      if (created.artifact_id) await loadArtifactDetail(created.artifact_id);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Study Lab</h1>
        <p className="pageIntro">
          Turn this course&apos;s resources into summaries, flashcards, quizzes, or practice problems.
        </p>
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select
            value={artifactType}
            onChange={(e) => setArtifactType(e.target.value as ArtifactType)}
            style={{ padding: 8 }}
          >
            <option value="summary">Summary</option>
            <option value="flashcards">Flashcards</option>
            <option value="quiz">Quiz</option>
            <option value="sample-problems">Sample problems</option>
          </select>
          <button
            onClick={runGeneration}
            disabled={isRunning || selectedIds.length === 0}
            style={{ padding: "8px 12px" }}
          >
            {isRunning ? "Generating…" : "Generate"}
          </button>
          <button onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>
        <div style={{ color: "#555", fontSize: 13 }}>
          Select a textbook, then choose chapter/section(s). Generation uses that page range only.
        </div>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Resources</div>
        {isLoading ? <LoadingState label="Loading resources..." /> : null}
        {!isLoading && resources.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 6 }}>
              {resources.map((r) => (
                <div key={r.id}>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={!!selected[r.id]}
                      onChange={(e) => toggleResource(r.id, e.target.checked)}
                    />
                    <span style={{ fontWeight: 600 }}>{r.title}</span>
                    <span style={{ color: "#555", fontSize: 12 }}>index={r.index_status}</span>
                  </label>
                  {selected[r.id] && primaryTextbookId === r.id ? (
                    <div
                      style={{
                        marginLeft: 28,
                        marginTop: 8,
                        marginBottom: 8,
                        padding: 10,
                        border: "1px solid #e5e7eb",
                        borderRadius: 8,
                        background: "#fafafa",
                        display: "grid",
                        gap: 6,
                        maxHeight: 280,
                        overflowY: "auto",
                      }}
                    >
                      <div style={{ fontWeight: 600, fontSize: 13 }}>Chapters / sections</div>
                      {sectionsLoading && !sectionsByResource[r.id] ? (
                        <LoadingState label="Scanning textbook headings…" />
                      ) : null}
                      {activeSections.length === 0 && !sectionsLoading ? (
                        <div style={{ color: "#666", fontSize: 13 }}>
                          No numbered sections detected yet. Generate will use the whole PDF (or try Reindex on
                          Resources).
                        </div>
                      ) : null}
                      {activeSections.map((s) => {
                        const pageLabel =
                          s.page_start != null
                            ? `p${s.page_start}${s.page_end != null && s.page_end !== s.page_start ? `–${s.page_end}` : ""}`
                            : "pages ?";
                        return (
                          <label key={s.key} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13 }}>
                            <input
                              type="checkbox"
                              checked={!!selectedSections[s.key]}
                              onChange={(e) =>
                                setSelectedSections((prev) => ({ ...prev, [s.key]: e.target.checked }))
                              }
                            />
                            <span>
                              <strong>
                                {s.kind === "chapter" ? "Ch" : "§"} {s.key}
                              </strong>{" "}
                              {s.title}{" "}
                              <span style={{ color: "#6b7280" }}>({pageLabel})</span>
                            </span>
                          </label>
                        );
                      })}
                      {selectedSectionKeys.length > 0 ? (
                        <div style={{ color: "#166534", fontSize: 12 }}>
                          {selectedSectionKeys.length} section{selectedSectionKeys.length === 1 ? "" : "s"} selected
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </ContentState>
        ) : null}
        {!isLoading && resources.length === 0 ? (
          <EmptyState message="No resources in this course yet. Upload files under Resources first." />
        ) : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Recent for this course</div>
        {artifactsForCourse.length === 0 ? (
          <EmptyState message="No study artifacts yet." />
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {artifactsForCourse.map((a) => (
              <div key={a.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{a.title}</div>
                  <div style={{ color: "#555", fontSize: 12 }}>{a.artifact_type}</div>
                </div>
                <button type="button" onClick={() => loadArtifactDetail(a.id)} style={{ padding: "6px 12px" }}>
                  View
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {artifactDetail ? (
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 8 }}>
            {artifactDetail.title}{" "}
            <span style={{ color: "#555", fontWeight: 400 }}>({artifactDetail.artifact_type})</span>
          </div>
          <StudyArtifactView
            artifactType={artifactDetail.artifact_type}
            content={artifactDetail.content_json}
          />
          <details>
            <summary style={{ cursor: "pointer", color: "#555", fontSize: 12 }}>Raw JSON</summary>
            <pre
              style={{
                margin: "8px 0 0",
                whiteSpace: "pre-wrap",
                background: "#0b1020",
                color: "#e6edf3",
                padding: 12,
                borderRadius: 8,
                overflowX: "auto",
                fontSize: 12,
              }}
            >
              {JSON.stringify(artifactDetail.content_json, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}
