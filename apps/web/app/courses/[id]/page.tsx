"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../../components/async-state";
import { apiGet, toErrorMessage } from "../../../lib/api";
import type { Course, Notebook, Resource, Task } from "../../../lib/types";

export default function CourseOverviewPage({ params }: { params: { id: string } }) {
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
      setCourse(await apiGet<Course>(`/courses/${params.id}`));
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

  const openTasks = tasks.filter((t) => t.status !== "done");
  const base = `/courses/${params.id}`;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Overview</h1>
        <p className="pageIntro">Everything for this course in one place.</p>
      </div>

      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading overview..." /> : null}

      {!isLoading && !error && course ? (
        <>
          <div className="card" style={{ display: "grid", gap: 8 }}>
            <div style={{ fontWeight: 700, fontSize: 18 }}>{course.name}</div>
            <div style={{ color: "#555" }}>
              {course.code ?? "No code"} · {course.term ?? "No term"}
            </div>
            <div className="statRow">
              <span>{openTasks.length} open task(s)</span>
              <span>{resources.length} resource(s)</span>
              <span>{notebooks.length} notebook(s)</span>
              {gradeSummary ? (
                <span>
                  {gradeSummary.weighted_completion_pct}% complete ({gradeSummary.done_tasks}/
                  {gradeSummary.total_tasks})
                </span>
              ) : null}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            {[
              { href: `${base}/resources`, label: "Resources", detail: `${resources.length} files` },
              { href: `${base}/notebooks`, label: "Notebooks", detail: `${notebooks.length} notebooks` },
              { href: `${base}/tasks`, label: "Tasks", detail: `${openTasks.length} open` },
              { href: `${base}/study-flows`, label: "StudyFlows", detail: "Read & practice" },
              { href: `${base}/study-lab`, label: "Study Lab", detail: "Summaries & practice" },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="card"
                style={{ textDecoration: "none", color: "inherit", display: "grid", gap: 4 }}
              >
                <div style={{ fontWeight: 700 }}>{item.label}</div>
                <div style={{ color: "#555", fontSize: 13 }}>{item.detail}</div>
              </Link>
            ))}
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Open tasks</div>
            {openTasks.length === 0 ? (
              <EmptyState message="No open tasks. Add some under Tasks." />
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {openTasks.slice(0, 6).map((t) => (
                  <li key={t.id} style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>{t.title}</span>
                    {t.due_at ? <span style={{ color: "#555", marginLeft: 8 }}>due {t.due_at}</span> : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}

      {!isLoading && !error && !course ? <EmptyState message="Course not found." /> : null}
    </div>
  );
}
