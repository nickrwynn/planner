"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../../../lib/api";
import {
  matchingRuleForTask,
  nextDueForRule,
  parseProblemsText,
  planDueDatesForTasks,
  problemsToText,
  readDueRules,
  WEEKDAY_OPTIONS,
  writeDueRules,
  type DueScheduleRule,
} from "../../../../lib/due-schedule";
import type { Course, Task } from "../../../../lib/types";

function toLocalInputValue(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatLogistics(task: Task): string[] {
  const logistics = task.logistics_json || {};
  const lines: string[] = [];
  const problems = logistics.problems;
  if (Array.isArray(problems) && problems.length) {
    lines.push(`Problems: ${problems.join(", ")}`);
  } else if (typeof problems === "string" && problems.trim()) {
    lines.push(`Problems: ${problems}`);
  }
  if (logistics.points_possible != null) lines.push(`Points: ${String(logistics.points_possible)}`);
  if (Array.isArray(logistics.submission_types) && logistics.submission_types.length) {
    lines.push(`Submit via: ${logistics.submission_types.join(", ")}`);
  }
  if (typeof logistics.unlock_at === "string" && logistics.unlock_at) {
    lines.push(`Unlocks: ${new Date(logistics.unlock_at).toLocaleString()}`);
  }
  if (typeof logistics.lock_at === "string" && logistics.lock_at) {
    lines.push(`Locks: ${new Date(logistics.lock_at).toLocaleString()}`);
  }
  if (typeof logistics.html_url === "string" && logistics.html_url) {
    lines.push(`Open in Canvas: ${logistics.html_url}`);
  }
  if (logistics.allowed_attempts != null) lines.push(`Attempts: ${String(logistics.allowed_attempts)}`);
  return lines;
}

type EditDraft = {
  title: string;
  taskType: string;
  dueAt: string;
  description: string;
  purpose: string;
  problems: string;
};

export default function CourseTasksPage({ params }: { params: { id: string } }) {
  const courseId = params.id;
  const [course, setCourse] = useState<Course | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [taskType, setTaskType] = useState("assignment");
  const [problems, setProblems] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);

  const [ruleTaskType, setRuleTaskType] = useState("assignment");
  const [ruleTitleContains, setRuleTitleContains] = useState("HW");
  const [ruleWeekday, setRuleWeekday] = useState(4);
  const [ruleTime, setRuleTime] = useState("23:59");

  const dueRules = useMemo(() => readDueRules(course?.grading_schema_json), [course?.grading_schema_json]);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [courseRow, taskRows] = await Promise.all([
        apiGet<Course>(`/courses/${courseId}`),
        apiGet<Task[]>(`/courses/${courseId}/tasks`),
      ]);
      setCourse(courseRow);
      setTasks(taskRows);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function saveDueRules(nextRules: DueScheduleRule[]) {
    if (!course) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await apiPatch<Course>(`/courses/${courseId}`, {
        grading_schema_json: writeDueRules(course.grading_schema_json, nextRules),
      });
      setCourse(updated);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function addDueRule() {
    const [hRaw, mRaw] = ruleTime.split(":");
    const hour = Math.min(23, Math.max(0, Number(hRaw) || 23));
    const minute = Math.min(59, Math.max(0, Number(mRaw) || 0));
    const rule: DueScheduleRule = {
      id: crypto.randomUUID(),
      task_type: ruleTaskType,
      title_contains: ruleTitleContains.trim(),
      weekday: ruleWeekday,
      hour,
      minute,
      enabled: true,
    };
    await saveDueRules([...dueRules, rule]);
  }

  async function applyDueSchedules(mode: "next" | "previous" = "next") {
    setBusy(true);
    setError(null);
    try {
      // Always overwrite existing due dates. Stagger weekly by title order:
      // HW1 → next Thursday, HW2 → the Thursday after, … (never one shared date).
      const candidates = tasks.filter((task) => {
        if (task.status === "done") return false;
        return !!matchingRuleForTask(task, dueRules);
      });
      const byRule = new Map<string, { rule: DueScheduleRule; tasks: Task[] }>();
      for (const task of candidates) {
        const rule = matchingRuleForTask(task, dueRules);
        if (!rule) continue;
        const bucket = byRule.get(rule.id) || { rule, tasks: [] };
        bucket.tasks.push(task);
        byRule.set(rule.id, bucket);
      }

      let updatedCount = 0;
      const now = new Date();
      const preview: string[] = [];
      for (const { rule, tasks: matched } of byRule.values()) {
        const planned = planDueDatesForTasks(matched, rule, mode, now);
        for (const { task, due } of planned) {
          await apiPatch<Task>(`/tasks/${task.id}`, { due_at: due.toISOString() });
          updatedCount += 1;
          if (preview.length < 6) {
            preview.push(
              `${task.title.slice(0, 40)} → ${due.toLocaleString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
              })}`
            );
          }
        }
      }
      await refresh();
      if (!updatedCount) {
        setError("No open tasks matched your schedules.");
      } else {
        window.alert(
          `Updated ${updatedCount} task${updatedCount === 1 ? "" : "s"} (overwrote prior due dates):\n\n${preview.join("\n")}${
            updatedCount > preview.length ? `\n…and ${updatedCount - preview.length} more` : ""
          }`
        );
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const problemList = parseProblemsText(problems);
      let resolvedDue = dueAt ? new Date(dueAt) : null;
      if (!resolvedDue) {
        const rule = matchingRuleForTask({ title: title.trim(), task_type: taskType }, dueRules);
        if (rule) resolvedDue = nextDueForRule(rule);
      }
      await apiPost<Task>("/tasks", {
        course_id: courseId,
        title: title.trim(),
        task_type: taskType,
        due_at: resolvedDue ? resolvedDue.toISOString() : null,
        description: problemList.length ? `Problems: ${problemList.join(", ")}` : null,
        status: "todo",
        logistics_json: problemList.length ? { problems: problemList } : {},
      });
      setTitle("");
      setDueAt("");
      setProblems("");
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function markDone(taskId: string) {
    try {
      await apiPatch<Task>(`/tasks/${taskId}`, { status: "done" });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  function startEdit(task: Task) {
    setEditingId(task.id);
    setDraft({
      title: task.title,
      taskType: task.task_type || "assignment",
      dueAt: task.due_at ? toLocalInputValue(new Date(task.due_at)) : "",
      description: task.description || "",
      purpose: task.purpose || "",
      problems: problemsToText(task.logistics_json?.problems) || "",
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(null);
  }

  async function saveEdit(task: Task) {
    if (!draft?.title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const problemList = parseProblemsText(draft.problems);
      const nextLogistics: Record<string, unknown> = { ...(task.logistics_json || {}) };
      if (problemList.length) nextLogistics.problems = problemList;
      else delete nextLogistics.problems;

      await apiPatch<Task>(`/tasks/${task.id}`, {
        title: draft.title.trim(),
        task_type: draft.taskType,
        due_at: draft.dueAt ? new Date(draft.dueAt).toISOString() : null,
        description: draft.description.trim() || null,
        purpose: draft.purpose.trim() || null,
        logistics_json: nextLogistics,
      });
      cancelEdit();
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteTask(taskId: string) {
    if (!window.confirm("Delete this task?")) return;
    try {
      await apiDelete<{ ok: boolean }>(`/tasks/${taskId}`);
      if (editingId === taskId) cancelEdit();
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Tasks</h1>
        <p className="pageIntro">
          Edit due dates and problem lists. Set repeating due schedules (e.g. HW every Thursday) once and apply them.
        </p>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Repeating due schedules</div>
        <p style={{ margin: "0 0 10px", fontSize: 13, color: "var(--muted)" }}>
          Example: titles containing “HW”, due every Thursday at 11:59 PM. Apply{" "}
          <strong>overwrites</strong> existing due dates and staggers weekly (HW 1 → next Thursday, HW 2 → the week
          after, …)—not the same date on every assignment.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
          <select value={ruleTaskType} onChange={(e) => setRuleTaskType(e.target.value)} style={{ padding: 8 }}>
            <option value="assignment">Assignment</option>
            <option value="exam">Exam</option>
            <option value="reading">Reading</option>
            <option value="project">Project</option>
            <option value="other">Other</option>
          </select>
          <input
            value={ruleTitleContains}
            onChange={(e) => setRuleTitleContains(e.target.value)}
            placeholder='Title contains (e.g. HW)'
            style={{ padding: 8, minWidth: 140 }}
          />
          <select value={ruleWeekday} onChange={(e) => setRuleWeekday(Number(e.target.value))} style={{ padding: 8 }}>
            {WEEKDAY_OPTIONS.map((d) => (
              <option key={d.value} value={d.value}>
                Every {d.label}
              </option>
            ))}
          </select>
          <input type="time" value={ruleTime} onChange={(e) => setRuleTime(e.target.value)} style={{ padding: 8 }} />
          <button type="button" disabled={busy} onClick={() => void addDueRule()} style={{ padding: "8px 12px" }}>
            Add schedule
          </button>
        </div>
        {dueRules.length === 0 ? (
          <div style={{ fontSize: 13, color: "#6b7280" }}>No schedules yet.</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            {dueRules.map((r) => (
              <li key={r.id} style={{ fontSize: 13 }}>
                <strong>{r.task_type}</strong>
                {r.title_contains ? ` · title contains “${r.title_contains}”` : ""} · every{" "}
                {WEEKDAY_OPTIONS.find((d) => d.value === r.weekday)?.label} at{" "}
                {`${String(r.hour).padStart(2, "0")}:${String(r.minute).padStart(2, "0")}`}
                {" · "}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void saveDueRules(dueRules.map((x) => (x.id === r.id ? { ...x, enabled: !x.enabled } : x)))}
                  style={{ fontSize: 12 }}
                >
                  {r.enabled ? "On" : "Off"}
                </button>
                {" · "}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void saveDueRules(dueRules.filter((x) => x.id !== r.id))}
                  style={{ fontSize: 12 }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <button
            type="button"
            disabled={busy || !dueRules.length}
            onClick={() => void applyDueSchedules("next")}
            style={{ padding: "8px 12px" }}
          >
            Apply weekly schedule (overwrite)
          </button>
          <button
            type="button"
            disabled={busy || !dueRules.length}
            onClick={() => void applyDueSchedules("previous")}
            style={{ padding: "8px 12px" }}
          >
            Apply previous weeks (overwrite)
          </button>
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Add task</div>
        <form onSubmit={onCreate} style={{ display: "grid", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Task title (e.g. HW 1)"
              style={{ padding: 8, minWidth: 240 }}
            />
            <select value={taskType} onChange={(e) => setTaskType(e.target.value)} style={{ padding: 8 }}>
              <option value="assignment">Assignment</option>
              <option value="exam">Exam</option>
              <option value="reading">Reading</option>
              <option value="project">Project</option>
              <option value="other">Other</option>
            </select>
            <input
              type="datetime-local"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              style={{ padding: 8 }}
              title="Leave blank to use a matching repeating schedule"
            />
            <button type="submit" style={{ padding: "8px 12px" }} disabled={busy || !title.trim()}>
              Add
            </button>
            <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
              Refresh
            </button>
          </div>
          <input
            value={problems}
            onChange={(e) => setProblems(e.target.value)}
            placeholder="Problems (optional): 1.1, 1.3, 1.5"
            style={{ padding: 8, maxWidth: 520 }}
          />
          {!dueAt && matchingRuleForTask({ title, task_type: taskType }, dueRules) ? (
            <div style={{ fontSize: 12, color: "#0f766e" }}>
              Will use schedule → due {nextDueForRule(matchingRuleForTask({ title, task_type: taskType }, dueRules)!).toLocaleString()}
            </div>
          ) : null}
        </form>
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>All tasks</div>
        {isLoading ? <LoadingState label="Loading tasks..." /> : null}
        {!isLoading && tasks.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 10 }}>
              {tasks.map((t) => {
                const logistics = formatLogistics(t);
                const isEditing = editingId === t.id && draft;
                const matched = matchingRuleForTask(t, dueRules);
                return (
                  <div
                    key={t.id}
                    style={{
                      display: "grid",
                      gap: 8,
                      borderTop: "1px solid #e5e7eb",
                      paddingTop: 10,
                    }}
                  >
                    {isEditing && draft ? (
                      <div style={{ display: "grid", gap: 8 }}>
                        <input
                          value={draft.title}
                          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                          style={{ padding: 8 }}
                          aria-label="Title"
                        />
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <select
                            value={draft.taskType}
                            onChange={(e) => setDraft({ ...draft, taskType: e.target.value })}
                            style={{ padding: 8 }}
                          >
                            <option value="assignment">Assignment</option>
                            <option value="exam">Exam</option>
                            <option value="reading">Reading</option>
                            <option value="project">Project</option>
                            <option value="other">Other</option>
                          </select>
                          <input
                            type="datetime-local"
                            value={draft.dueAt}
                            onChange={(e) => setDraft({ ...draft, dueAt: e.target.value })}
                            style={{ padding: 8 }}
                          />
                          <button type="button" onClick={() => setDraft({ ...draft, dueAt: "" })} style={{ padding: "8px 10px" }}>
                            Clear due
                          </button>
                          {matched ? (
                            <>
                              <button
                                type="button"
                                onClick={() => setDraft({ ...draft, dueAt: toLocalInputValue(previousDueForRule(matched)) })}
                                style={{ padding: "8px 10px" }}
                              >
                                Set last {WEEKDAY_OPTIONS.find((d) => d.value === matched.weekday)?.label}
                              </button>
                              <button
                                type="button"
                                onClick={() => setDraft({ ...draft, dueAt: toLocalInputValue(nextDueForRule(matched)) })}
                                style={{ padding: "8px 10px" }}
                              >
                                Set next {WEEKDAY_OPTIONS.find((d) => d.value === matched.weekday)?.label}
                              </button>
                            </>
                          ) : null}
                        </div>
                        <input
                          value={draft.problems}
                          onChange={(e) => setDraft({ ...draft, problems: e.target.value })}
                          placeholder="Problems: 1.1, 1.3, 1.5"
                          style={{ padding: 8 }}
                        />
                        <textarea
                          value={draft.description}
                          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                          placeholder="Description / notes from class"
                          rows={3}
                          style={{ padding: 8 }}
                        />
                        <textarea
                          value={draft.purpose}
                          onChange={(e) => setDraft({ ...draft, purpose: e.target.value })}
                          placeholder="Purpose / why (optional)"
                          rows={2}
                          style={{ padding: 8 }}
                        />
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <button type="button" disabled={busy} onClick={() => void saveEdit(t)} style={{ padding: "8px 12px" }}>
                            Save
                          </button>
                          <button type="button" onClick={cancelEdit} style={{ padding: "8px 12px" }}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                          <div>
                            <div style={{ fontWeight: 600, textDecoration: t.status === "done" ? "line-through" : "none" }}>
                              {t.title}
                              {t.source_type === "canvas" ? (
                                <span style={{ marginLeft: 8, fontSize: 11, color: "#1d4ed8" }}>Canvas</span>
                              ) : null}
                            </div>
                            <div style={{ color: "#555", fontSize: 13 }}>
                              {(t.task_type || "task").toUpperCase()} · {t.status}
                              {matched ? " · schedule match" : ""}
                            </div>
                          </div>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {t.status !== "done" ? (
                              <button onClick={() => markDone(t.id)} style={{ padding: "6px 10px" }}>
                                Done
                              </button>
                            ) : null}
                            <button onClick={() => startEdit(t)} style={{ padding: "6px 10px" }}>
                              Edit
                            </button>
                            <button onClick={() => deleteTask(t.id)} style={{ padding: "6px 10px" }}>
                              Delete
                            </button>
                          </div>
                        </div>
                        <div style={{ display: "grid", gap: 4, fontSize: 13, color: "#374151" }}>
                          <div>
                            <strong>When:</strong>{" "}
                            {t.due_at ? new Date(t.due_at).toLocaleString() : "No due date"}
                          </div>
                          <div>
                            <strong>What:</strong> {t.description || "—"}
                          </div>
                          <div>
                            <strong>Why:</strong> {t.purpose || "—"}
                          </div>
                          <div>
                            <strong>Logistics:</strong>{" "}
                            {logistics.length ? (
                              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                                {logistics.map((line) => (
                                  <li key={line}>
                                    {line.startsWith("Open in Canvas: ") ? (
                                      <a href={line.slice("Open in Canvas: ".length)} target="_blank" rel="noreferrer">
                                        Open in Canvas
                                      </a>
                                    ) : (
                                      line
                                    )}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              "—"
                            )}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </ContentState>
        ) : null}
        {!isLoading && !error && tasks.length === 0 ? <EmptyState message="No tasks yet." /> : null}
      </div>
    </div>
  );
}
