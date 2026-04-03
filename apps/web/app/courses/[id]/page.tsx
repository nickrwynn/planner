"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../../components/async-state";
import { apiGet, toErrorMessage } from "../../../lib/api";
import type { Course, Notebook, Resource, Task } from "../../../lib/types";

export default function CourseDetailPage({ params }: { params: { id: string } }) {
  const [course, setCourse] = useState<Course | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [gradeSummary, setGradeSummary] = useState<{
    weighted_completion_pct: number;
    done_tasks: number;
    total_tasks: number;
  } | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const c = await apiGet<Course>(`/courses/${params.id}`);
      setCourse(c);
      setTasks(await apiGet<Task[]>(`/courses/${params.id}/tasks`));
      setResources(await apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(params.id)}`));
      setNotebooks(await apiGet<Notebook[]>(`/notebooks?course_id=${encodeURIComponent(params.id)}`));
      setGradeSummary(await apiGet(`/courses/${params.id}/grade-summary`));
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Course</h1>
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading course..." /> : null}
      {!isLoading && !error && !course ? <EmptyState message="Course not found." /> : null}
      {course && (
        <div className="card" style={{ display: "grid", gap: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>{course.name}</div>
          <div style={{ color: "#555" }}>
            {course.code ?? "—"} • {course.term ?? "—"}
          </div>
          <div style={{ display: "flex", gap: 12, color: "#555", fontSize: 13 }}>
            <span>{tasks.length} task(s)</span>
            <span>{resources.length} resource(s)</span>
            <span>{notebooks.length} notebook(s)</span>
            {gradeSummary ? (
              <span>
                completion={gradeSummary.weighted_completion_pct}% ({gradeSummary.done_tasks}/{gradeSummary.total_tasks})
              </span>
            ) : null}
          </div>
          <div style={{ display: "flex", gap: 12, fontSize: 13 }}>
            <a href="/tasks">Open tasks</a>
            <a href="/resources">Open resources</a>
            <a href="/notes">Open notes</a>
          </div>
          <div style={{ color: "#555", fontSize: 12 }}>id: {course.id}</div>
        </div>
      )}

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Tasks</div>
        <div style={{ display: "grid", gap: 6 }}>
          {tasks.map((t) => (
            <div key={t.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600 }}>{t.title}</div>
                <div style={{ color: "#555", fontSize: 12 }}>{t.status}</div>
              </div>
              <div style={{ color: "#555", fontSize: 12 }}>{t.id}</div>
            </div>
          ))}
          {!isLoading && !error && tasks.length === 0 ? <EmptyState message="No tasks." /> : null}
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Resources</div>
        <div style={{ display: "grid", gap: 6 }}>
          {resources.map((r) => (
            <div key={r.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  <Link href={`/resources/${r.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                    {r.title}
                  </Link>
                </div>
                <div style={{ color: "#555", fontSize: 12 }}>index={r.index_status}</div>
              </div>
              <div style={{ color: "#555", fontSize: 12 }}>{r.id}</div>
            </div>
          ))}
          {!isLoading && !error && resources.length === 0 ? <EmptyState message="No resources." /> : null}
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Notebooks</div>
        <div style={{ display: "grid", gap: 6 }}>
          {notebooks.map((n) => (
            <div key={n.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div style={{ fontWeight: 600 }}>
                <Link href={`/notebooks/${n.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                  {n.title}
                </Link>
              </div>
              <div style={{ color: "#555", fontSize: 12 }}>{n.id}</div>
            </div>
          ))}
          {!isLoading && !error && notebooks.length === 0 ? <EmptyState message="No notebooks." /> : null}
        </div>
      </div>
    </div>
  );
}

