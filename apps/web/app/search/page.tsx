"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiGet, toErrorMessage } from "../../lib/api";

type SearchHit = {
  resource_id: string;
  resource_title: string;
  resource_type?: string | null;
  chunk_id: string;
  chunk_index: number;
  page_number: number | null;
  snippet: string;
  score?: number | null;
};

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  async function run(query: string) {
    setError(null);
    setHits([]);
    setHasSearched(true);
    if (!query.trim()) return;
    setIsLoading(true);
    try {
      const hits = await apiGet<SearchHit[]>(
        `/search?q=${encodeURIComponent(query)}&limit=20`
      );
      setHits(hits);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // quick UX: if user refreshes, don't auto-run
  }, []);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Search</h1>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Query</div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(q);
          }}
          style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search your indexed resources…"
            style={{ padding: 8, minWidth: 320 }}
          />
          <button type="submit" style={{ padding: "8px 12px" }}>
            Search
          </button>
        </form>
        {error ? <ErrorState message={error} onRetry={() => run(q)} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          Results
          {hasSearched ? ` (${hits.length})` : ""}
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {isLoading ? <LoadingState label="Searching..." /> : null}
          {hits.map((h) => (
            <div key={h.chunk_id} style={{ display: "grid", gap: 4 }}>
              <div style={{ color: "#555", fontSize: 12, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <Link href={`/resources/${h.resource_id}`} style={{ textDecoration: "none" }}>
                  {h.resource_title}
                </Link>
                {h.resource_type ? (
                  <span style={{ padding: "2px 6px", borderRadius: 999, background: "#eef2ff", color: "#1e3a8a" }}>
                    {h.resource_type}
                  </span>
                ) : null}
                <span>page={h.page_number ?? "—"}</span>
                <span>chunk={h.chunk_index}</span>
                {h.score != null ? <span>score={h.score.toFixed(4)}</span> : null}
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{h.snippet}</div>
            </div>
          ))}
          {!isLoading && hasSearched && hits.length === 0 ? <EmptyState message="No results." /> : null}
          {!isLoading && !hasSearched ? <EmptyState message="Run a query to see results." /> : null}
        </div>
      </div>
    </div>
  );
}

