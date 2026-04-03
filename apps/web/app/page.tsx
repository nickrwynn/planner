"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/async-state";
import { apiGet, toErrorMessage } from "../lib/api";

type HealthResponse = {
  status: string;
  postgres?: { ok: boolean; error?: string | null };
  redis?: { ok: boolean; error?: string | null };
};

type Task = {
  id: string;
  title: string;
  due_at?: string | null;
  status: string;
  course_id: string;
};

type Resource = {
  id: string;
  title: string;
  index_status: string;
  parse_status: string;
  course_id: string | null;
};

type PlannerNext = {
  task: Task | null;
  reasons: string[];
};

type PlannerUpcoming = {
  tasks: Task[];
};

export default function Home() {
  const [health, setHealth] = useState<HealthResponse>({ status: "unreachable" });
  const [tasks, setTasks] = useState<Task[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [planner, setPlanner] = useState<PlannerNext>({ task: null, reasons: [] });
  const [upcomingPlan, setUpcomingPlan] = useState<PlannerUpcoming>({ tasks: [] });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [nextHealth, nextTasks, nextResources, nextPlanner, nextUpcoming] = await Promise.all([
        apiGet<HealthResponse>("/health"),
        apiGet<Task[]>("/tasks?limit=100&offset=0"),
        apiGet<Resource[]>("/resources?limit=100&offset=0"),
        apiGet<PlannerNext>("/planner/next"),
        apiGet<PlannerUpcoming>("/planner/upcoming?limit=8"),
      ]);
      setHealth(nextHealth);
      setTasks(nextTasks);
      setResources(nextResources);
      setPlanner(nextPlanner);
      setUpcomingPlan(nextUpcoming);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const openTasks = useMemo(() => tasks.filter((t) => t.status !== "done"), [tasks]);
  const failedIndex = useMemo(() => resources.filter((r) => r.index_status === "failed"), [resources]);
  const upcoming = useMemo(() => {
    if (upcomingPlan.tasks.length > 0) return upcomingPlan.tasks;
    return [...openTasks].sort((a, b) => {
      if (!a.due_at && !b.due_at) return 0;
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;
      const ta = Date.parse(a.due_at);
      const tb = Date.parse(b.due_at);
      if (Number.isNaN(ta) && Number.isNaN(tb)) return String(a.due_at).localeCompare(String(b.due_at));
      if (Number.isNaN(ta)) return 1;
      if (Number.isNaN(tb)) return -1;
      return ta - tb;
    });
  }, [openTasks, upcomingPlan.tasks]);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Dashboard</h1>
      {isLoading ? <LoadingState label="Loading dashboard..." /> : null}
      {!isLoading && error ? (
        <ErrorState
          title="Dashboard unavailable"
          message={error}
          onRetry={refresh}
        />
      ) : null}

      {!isLoading && !error ? (
        <>
          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Stack health</div>
            <pre
              style={{
                background: "#0b1020",
                color: "#e6edf3",
                padding: 12,
                borderRadius: 6,
                overflowX: "auto",
              }}
            >
              {JSON.stringify(health, null, 2)}
            </pre>
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Suggested next</div>
            {planner.task ? (
              <div style={{ fontSize: 14 }}>
                <div style={{ fontWeight: 600 }}>{planner.task.title}</div>
                {planner.task.due_at ? (
                  <div style={{ color: "#555", marginTop: 4 }}>Due {planner.task.due_at}</div>
                ) : null}
                <div style={{ color: "#555", marginTop: 6, fontSize: 12 }}>
                  {planner.reasons.join(" · ")}
                </div>
                <a href="/tasks" style={{ display: "inline-block", marginTop: 8, fontSize: 13 }}>
                  Open tasks
                </a>
              </div>
            ) : (
              <EmptyState message="No open tasks — you're clear or add tasks first." />
            )}
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Upcoming tasks ({openTasks.length} open)</div>
            {upcoming.length === 0 ? (
              <EmptyState message="No open tasks. Add tasks from the Tasks page." />
            ) : (
              <ul style={{ margin: 0, paddingLeft: 20, color: "#333" }}>
                {upcoming.map((t) => (
                  <li key={t.id} style={{ marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>{t.title}</span>
                    {t.due_at ? (
                      <span style={{ color: "#555", marginLeft: 8, fontSize: 13 }}>due {t.due_at}</span>
                    ) : null}
                    <span style={{ color: "#555", marginLeft: 8, fontSize: 12 }}>({t.status})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {failedIndex.length > 0 ? (
            <div className="card" style={{ borderColor: "#fecaca", background: "#fff7f7" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Indexing issues ({failedIndex.length})</div>
              <div style={{ fontSize: 14, color: "#555" }}>
                These resources did not finish indexing. Open each resource for error details and jobs.
              </div>
              <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
                {failedIndex.slice(0, 6).map((r) => (
                  <li key={r.id}>
                    <a href={`/resources/${r.id}`} style={{ fontWeight: 600 }}>
                      {r.title}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Library</div>
            <div style={{ color: "#555", fontSize: 14 }}>
              {resources.length} resource(s) total. Upload files from Resources, run Search and Ask from the right
              agent pane, and use Study Lab for summaries and flashcards.
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
