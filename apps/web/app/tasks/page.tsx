"use client";

import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import type { Course, Task } from "../../lib/types";

export default function TasksPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [courseId, setCourseId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState("assignment");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function refresh() {
    setError(null);
    setIsLoading(true);
    try {
      const cs = await apiGet<Course[]>("/courses");
      setCourses(cs);
      const selected = courseId || cs[0]?.id || "";
      setCourseId(selected);
      if (selected) {
        setTasks(await apiGet<Task[]>(`/courses/${selected}/tasks`));
      } else {
        setTasks([]);
      }
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

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!courseId) return;
    setError(null);
    try {
      await apiPost<Task>("/tasks", { course_id: courseId, title, task_type: taskType });
      setTitle("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function markDone(taskId: string) {
    setError(null);
    try {
      await apiPatch<Task>(`/tasks/${taskId}`, { status: "done" });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function renameTask(task: Task) {
    const next = window.prompt("New task title", task.title);
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch<Task>(`/tasks/${task.id}`, { title: next.trim() });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function deleteTask(taskId: string) {
    if (!window.confirm("Delete this task?")) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/tasks/${taskId}`);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Tasks</h1>

      <div className="card">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 600 }}>Course</div>
          <select value={courseId} onChange={(e) => setCourseId(e.target.value)} style={{ padding: 8 }}>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code ? `${c.code} — ` : ""}{c.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>

        <div style={{ height: 12 }} />

        <div style={{ fontWeight: 600, marginBottom: 8 }}>Create task</div>
        <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title"
            style={{ padding: 8, minWidth: 260 }}
          />
          <select value={taskType} onChange={(e) => setTaskType(e.target.value)} style={{ padding: 8 }}>
            <option value="assignment">Assignment</option>
            <option value="exam">Exam</option>
            <option value="reading">Reading</option>
            <option value="project">Project</option>
            <option value="other">Other</option>
          </select>
          <button type="submit" style={{ padding: "8px 12px" }} disabled={!courseId || !title}>
            Create
          </button>
        </form>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Tasks</div>
        <div style={{ display: "grid", gap: 8 }}>
          {isLoading ? <LoadingState label="Loading tasks..." /> : null}
          {tasks.map((t) => (
            <div key={t.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{t.title}</div>
                <div style={{ color: "#555", fontSize: 13 }}>
                  {(t.task_type || "task").toUpperCase()} • {t.status}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {t.status !== "done" && (
                  <button onClick={() => markDone(t.id)} style={{ padding: "6px 10px" }}>
                    Mark done
                  </button>
                )}
                <button onClick={() => renameTask(t)} style={{ padding: "6px 10px" }}>
                  Rename
                </button>
                <button onClick={() => deleteTask(t.id)} style={{ padding: "6px 10px" }}>
                  Delete
                </button>
                <div style={{ color: "#555", fontSize: 12 }}>{t.id}</div>
              </div>
            </div>
          ))}
          {!isLoading && !error && tasks.length === 0 ? <EmptyState message="No tasks for this course yet." /> : null}
        </div>
      </div>
    </div>
  );
}

