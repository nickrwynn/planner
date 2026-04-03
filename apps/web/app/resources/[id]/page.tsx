"use client";

import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../../components/async-state";
import { apiGet, apiPost, toErrorMessage } from "../../../lib/api";
import type { Resource } from "../../../lib/types";

type BackgroundJob = {
  id: string;
  status: string;
  job_type: string;
  attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

type ChunkPreview = {
  id: string;
  chunk_index: number;
  page_number: number | null;
  text_preview: string;
};

export default function ResourceDetailPage({ params }: { params: { id: string } }) {
  const [resource, setResource] = useState<Resource | null>(null);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [chunks, setChunks] = useState<ChunkPreview[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isReindexing, setIsReindexing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [r, j, c] = await Promise.all([
        apiGet<Resource>(`/resources/${params.id}`),
        apiGet<BackgroundJob[]>(`/resources/${params.id}/jobs`),
        apiGet<ChunkPreview[]>(`/resources/${params.id}/chunks`),
      ]);
      setResource(r);
      setJobs(j);
      setChunks(c);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!resource) return;
    const isProcessing =
      resource.parse_status === "parsing" ||
      resource.ocr_status === "running" ||
      resource.index_status === "queued" ||
      resource.index_status === "pending";
    if (!isProcessing) return;
    const t = setInterval(() => {
      refresh();
    }, 2000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resource?.parse_status, resource?.ocr_status, resource?.index_status, params.id]);

  const indexErr =
    resource?.metadata_json && typeof resource.metadata_json === "object" && resource.metadata_json !== null
      ? (resource.metadata_json as { index_error?: string }).index_error
      : undefined;
  const ocrErr =
    resource?.metadata_json && typeof resource.metadata_json === "object" && resource.metadata_json !== null
      ? (resource.metadata_json as { ocr_error?: string }).ocr_error
      : undefined;

  async function reindex() {
    if (!resource || isReindexing) return;
    setIsReindexing(true);
    setError(null);
    try {
      await apiPost<Resource>(`/resources/${resource.id}/reindex`, {});
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsReindexing(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Resource</h1>
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading resource..." /> : null}
      {!isLoading && !error && !resource ? <EmptyState message="Resource not found." /> : null}
      {resource && (
        <>
          <div className="card" style={{ display: "grid", gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{resource.title}</div>
            <div style={{ color: "#555" }}>id: {resource.id}</div>
            <div style={{ color: "#555" }}>type: {resource.resource_type ?? "—"}</div>
            <div style={{ color: "#555" }}>
              statuses: parse={resource.parse_status} • ocr={resource.ocr_status} • index={resource.index_status}
            </div>
            {indexErr && (
              <div style={{ color: "#b91c1c", fontSize: 14, whiteSpace: "pre-wrap" }}>
                <strong>Index error:</strong> {indexErr}
              </div>
            )}
            {ocrErr && (
              <div style={{ color: "#b91c1c", fontSize: 14, whiteSpace: "pre-wrap" }}>
                <strong>OCR error:</strong> {ocrErr}
              </div>
            )}
            <div style={{ color: "#555" }}>storage_path: {resource.storage_path ?? "—"}</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button onClick={refresh} style={{ width: "fit-content", padding: "8px 12px" }}>
                Refresh
              </button>
              <button
                onClick={reindex}
                disabled={isReindexing}
                style={{ width: "fit-content", padding: "8px 12px" }}
              >
                {isReindexing ? "Reindexing..." : "Reindex"}
              </button>
            </div>
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Background jobs</div>
            {!isLoading && !error && jobs.length === 0 ? (
              <EmptyState message="No jobs recorded yet." />
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: 8,
                      padding: 10,
                      fontSize: 13,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>
                      {job.job_type} • {job.status} • attempts {job.attempts}
                    </div>
                    <div style={{ color: "#555" }}>id: {job.id}</div>
                    {job.last_error && (
                      <div style={{ color: "#b91c1c", marginTop: 6, whiteSpace: "pre-wrap" }}>{job.last_error}</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Indexed chunks (preview)</div>
            {!isLoading && !error && chunks.length === 0 ? (
              <EmptyState message="No chunks yet — wait for indexing or reindex from the API." />
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {chunks.map((ch) => (
                  <div key={ch.id} style={{ borderBottom: "1px solid #eee", paddingBottom: 8 }}>
                    <div style={{ fontSize: 12, color: "#555" }}>
                      chunk {ch.chunk_index}
                      {ch.page_number != null ? ` • page ${ch.page_number}` : ""}
                    </div>
                    <div style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>{ch.text_preview}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
