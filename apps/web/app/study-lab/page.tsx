"use client";

import { useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import type { Course, Resource } from "../../lib/types";

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
  user_id: string;
  course_id: string | null;
  artifact_type: string;
  title: string;
  source_resource_ids_json: string[] | null;
  content_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export default function StudyLabPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [artifactType, setArtifactType] = useState<ArtifactType>("summary");
  const [artifacts, setArtifacts] = useState<ArtifactListItem[]>([]);
  const [artifactDetail, setArtifactDetail] = useState<StudyArtifactDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const selectedIds = useMemo(() => Object.keys(selected).filter((k) => selected[k]), [selected]);
  const artifactsForCourse = useMemo(() => {
    if (!courseId) return artifacts;
    return artifacts.filter((a) => a.course_id === courseId);
  }, [artifacts, courseId]);

  async function refresh(nextCourseId?: string) {
    setError(null);
    setIsLoading(true);
    try {
      const cs = await apiGet<Course[]>("/courses");
      setCourses(cs);
      const selectedCourse = nextCourseId ?? courseId ?? cs[0]?.id ?? "";
      setCourseId(selectedCourse);
      if (selectedCourse) {
        const rs = await apiGet<Resource[]>(
          `/resources?course_id=${encodeURIComponent(selectedCourse)}&limit=100&offset=0`
        );
        setResources(rs);
      } else {
        setResources([]);
      }
      setArtifacts(await apiGet<ArtifactListItem[]>("/ai/artifacts?limit=50&offset=0"));
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

  async function loadArtifactDetail(id: string) {
    setDetailLoading(true);
    setDetailError(null);
    try {
      setArtifactDetail(await apiGet<StudyArtifactDetail>(`/ai/artifacts/${id}`));
    } catch (e) {
      setDetailError(toErrorMessage(e));
      setArtifactDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function runGeneration() {
    if (selectedIds.length === 0) return;
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
        course_id: courseId || null,
        resource_ids: selectedIds
      });
      await refresh();
      if (created.artifact_id) {
        await loadArtifactDetail(created.artifact_id);
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsRunning(false);
    }
  }

  async function renameArtifact() {
    if (!artifactDetail) return;
    const next = window.prompt("Artifact title", artifactDetail.title);
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch(`/ai/artifacts/${artifactDetail.id}`, { title: next.trim() });
      await loadArtifactDetail(artifactDetail.id);
      await refresh(courseId);
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function regenerateArtifact() {
    if (!artifactDetail) return;
    setError(null);
    try {
      const next = await apiPost<StudyArtifactDetail>(`/ai/artifacts/${artifactDetail.id}/regenerate`, {
        course_id: artifactDetail.course_id,
        resource_ids: artifactDetail.source_resource_ids_json ?? []
      });
      await refresh(courseId);
      await loadArtifactDetail(next.id);
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function exportArtifact(format: "json" | "markdown") {
    if (!artifactDetail) return;
    setError(null);
    try {
      const payload = await apiGet<Record<string, unknown>>(
        `/ai/artifacts/${artifactDetail.id}/export?format=${format}`
      );
      const body =
        format === "markdown"
          ? String(payload.markdown ?? "")
          : JSON.stringify(payload, null, 2);
      const ext = format === "markdown" ? "md" : "json";
      const blob = new Blob([body], { type: format === "markdown" ? "text/markdown" : "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${artifactDetail.title.replace(/\s+/g, "_").toLowerCase() || "artifact"}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Study Lab</h1>

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

          <div style={{ fontWeight: 600, marginLeft: 8 }}>Generate</div>
          <select value={artifactType} onChange={(e) => setArtifactType(e.target.value as ArtifactType)} style={{ padding: 8 }}>
            <option value="summary">summary</option>
            <option value="flashcards">flashcards</option>
            <option value="quiz">quiz</option>
            <option value="sample-problems">sample problems</option>
          </select>

          <button onClick={runGeneration} disabled={isRunning || selectedIds.length === 0} style={{ padding: "8px 12px" }}>
            {isRunning ? "Generating…" : "Generate"}
          </button>
          <button onClick={() => refresh()} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>

        <div style={{ marginTop: 12, color: "#555", fontSize: 13 }}>
          Select resources below. Generation requires OPENAI_API_KEY on the API container.
        </div>

        {error ? <ErrorState message={error} onRetry={() => refresh()} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Resources</div>
        <div style={{ display: "grid", gap: 6 }}>
          {resources.map((r) => (
            <label key={r.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={!!selected[r.id]}
                onChange={(e) => setSelected((prev) => ({ ...prev, [r.id]: e.target.checked }))}
              />
              <span style={{ fontWeight: 600 }}>{r.title}</span>
              <span style={{ color: "#555", fontSize: 12 }}>
                {r.resource_type ?? "—"} • index={r.index_status}
              </span>
            </label>
          ))}
          {isLoading ? <LoadingState label="Loading resources..." /> : null}
          {!isLoading && !error && resources.length === 0 ? <EmptyState message="No resources in this course yet." /> : null}
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Recent artifacts</div>
        <div style={{ display: "grid", gap: 8 }}>
          {artifactsForCourse.map((a) => (
            <div key={a.id} style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{a.title}</div>
                <div style={{ color: "#555", fontSize: 12 }}>{a.artifact_type}</div>
              </div>
              <button type="button" onClick={() => loadArtifactDetail(a.id)} style={{ padding: "6px 12px", fontSize: 12 }}>
                View
              </button>
            </div>
          ))}
          {!isLoading && !error && artifactsForCourse.length === 0 ? (
            <EmptyState message="No artifacts for this course yet. Generate one from selected resources above." />
          ) : null}
        </div>
      </div>

      {(detailLoading || artifactDetail || detailError) && (
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Artifact detail</div>
          {detailLoading && <LoadingState label="Loading artifact..." />}
          {!detailLoading && detailError ? (
            <ErrorState message={detailError} onRetry={() => (artifactDetail ? loadArtifactDetail(artifactDetail.id) : refresh())} />
          ) : null}
          {!detailLoading && artifactDetail && (
            <div style={{ display: "grid", gap: 10 }}>
              <div style={{ fontSize: 14 }}>
                <strong>{artifactDetail.title}</strong>{" "}
                <span style={{ color: "#555", fontSize: 12 }}>({artifactDetail.artifact_type})</span>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="button" onClick={renameArtifact} style={{ padding: "6px 10px", fontSize: 12 }}>
                  Rename
                </button>
                <button type="button" onClick={regenerateArtifact} style={{ padding: "6px 10px", fontSize: 12 }}>
                  Regenerate
                </button>
                <button type="button" onClick={() => exportArtifact("json")} style={{ padding: "6px 10px", fontSize: 12 }}>
                  Export JSON
                </button>
                <button
                  type="button"
                  onClick={() => exportArtifact("markdown")}
                  style={{ padding: "6px 10px", fontSize: 12 }}
                >
                  Export Markdown
                </button>
              </div>
              <pre
                style={{
                  background: "#0b1020",
                  color: "#e6edf3",
                  padding: 12,
                  borderRadius: 6,
                  overflowX: "auto",
                  fontSize: 12,
                  maxHeight: 420
                }}
              >
                {JSON.stringify(
                  {
                    content_json: artifactDetail.content_json,
                    metadata_json: artifactDetail.metadata_json,
                    sources: artifactDetail.source_resource_ids_json
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
