"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import { isStudyflowTask, studyflowHrefFromTask } from "../../lib/studyflow-nav";
import { parseProblemsText, problemsToText } from "../../lib/due-schedule";
import type { Course, Notebook, PlannerLabel, Resource, ResourceChunk, Task } from "../../lib/types";

type PlannerKind = "event" | "todo" | "homework" | "reading" | "note" | "focus" | "studyflow";
type Difficulty = "red" | "yellow" | "green";

type Logistics = {
  kind?: PlannerKind | string;
  difficulty?: Difficulty | string;
  target?: string;
  source_task_id?: string;
  notebook_id?: string;
  resource_id?: string;
  planner_label_id?: string;
  planner_label_name?: string;
  studyflow?: boolean;
  excerpt_id?: string;
  course_id?: string;
  page?: number | string;
};

type CatalogOption = {
  key: string;
  source: "task" | "notebook" | "resource";
  sourceId: string;
  title: string;
  label: string;
  target?: string;
};

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, delta: number) {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1);
}

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function toLocalInputValue(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function logisticsOf(task: Task): Logistics {
  return (task.logistics_json as Logistics | null) || {};
}

function plannerKind(task: Task): PlannerKind {
  const kind = logisticsOf(task).kind;
  if (kind === "studyflow" || logisticsOf(task).studyflow) return "reading";
  if (kind === "event" || kind === "todo" || kind === "homework" || kind === "reading" || kind === "note" || kind === "focus") {
    return kind;
  }
  if (task.task_type === "reading") return "reading";
  if (task.task_type === "assignment" || task.task_type === "exam" || task.task_type === "project") return "homework";
  return "todo";
}

function difficultyOf(task: Task): Difficulty {
  const d = logisticsOf(task).difficulty;
  if (d === "red" || d === "yellow" || d === "green") return d;
  return "yellow";
}

function formatTime(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

const DIFFICULTY_META: Record<Difficulty, { label: string; bg: string; border: string; text: string }> = {
  red: { label: "Red — hard / high friction", bg: "#fef2f2", border: "#fecaca", text: "#991b1b" },
  yellow: { label: "Yellow — medium", bg: "#fffbeb", border: "#fde68a", text: "#92400e" },
  green: { label: "Green — easy wins", bg: "#f0fdf4", border: "#bbf7d0", text: "#166534" },
};

export default function CalendarPage() {
  const router = useRouter();
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [tasks, setTasks] = useState<Task[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedDay, setSelectedDay] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);

  // Shared add form
  const [addKind, setAddKind] = useState<PlannerKind>("todo");
  const [title, setTitle] = useState("");
  const [ownerKey, setOwnerKey] = useState(""); // "" | "course:uuid" | "label:uuid" | "__add_new__"
  const [labels, setLabels] = useState<PlannerLabel[]>([]);
  const [newLabelName, setNewLabelName] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("yellow");
  const [readingTarget, setReadingTarget] = useState("");
  const [dueLocal, setDueLocal] = useState("");
  const [topFocusDraft, setTopFocusDraft] = useState("");
  const [catalogOptions, setCatalogOptions] = useState<CatalogOption[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogKey, setCatalogKey] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDueLocal, setEditDueLocal] = useState("");
  const [editTarget, setEditTarget] = useState("");
  const [editDifficulty, setEditDifficulty] = useState<Difficulty>("yellow");
  const [editProblems, setEditProblems] = useState("");
  const [editDescription, setEditDescription] = useState("");

  const courseId = ownerKey.startsWith("course:") ? ownerKey.slice("course:".length) : "";
  const labelId = ownerKey.startsWith("label:") ? ownerKey.slice("label:".length) : "";
  const addingNewLabel = ownerKey === "__add_new__";

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [nextTasks, nextCourses, nextLabels] = await Promise.all([
        apiGet<Task[]>("/tasks?limit=200&offset=0"),
        apiGet<Course[]>("/courses"),
        apiGet<PlannerLabel[]>("/planner/labels"),
      ]);
      setTasks(nextTasks);
      setCourses(nextCourses);
      setLabels(nextLabels);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Load course assignments / chapters when homework or reading + course is selected.
  useEffect(() => {
    let cancelled = false;
    async function loadCatalog() {
      if (!courseId || (addKind !== "homework" && addKind !== "reading")) {
        setCatalogOptions([]);
        setCatalogKey("");
        setCatalogLoading(false);
        return;
      }
      setCatalogLoading(true);
      try {
        if (addKind === "homework") {
          const courseTasks = await apiGet<Task[]>(
            `/courses/${encodeURIComponent(courseId)}/tasks?limit=200&offset=0`
          );
          if (cancelled) return;
          const options = courseTasks
            .filter((t) => {
              const type = (t.task_type || "").toLowerCase();
              const title = (t.title || "").toLowerCase();
              // Canvas often stores "Reading N, …" as assignments; keep those for Reading.
              if (/^reading\b/.test(title)) return false;
              return type === "assignment" || type === "exam" || type === "project" || t.source_type === "canvas";
            })
            .filter((t) => t.status !== "done")
            .map((t) => {
              const due = t.due_at
                ? formatTime(t.due_at) || new Date(t.due_at).toLocaleDateString()
                : "no due date";
              return {
                key: `task:${t.id}`,
                source: "task" as const,
                sourceId: t.id,
                title: t.title,
                label: `${t.title} · ${due}`,
              };
            });
          setCatalogOptions(options);
        } else {
          const [notebooks, resources, courseTasks] = await Promise.all([
            apiGet<Notebook[]>(`/notebooks?course_id=${encodeURIComponent(courseId)}`),
            apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(courseId)}&limit=100`),
            apiGet<Task[]>(`/courses/${encodeURIComponent(courseId)}/tasks?limit=200&offset=0`),
          ]);
          if (cancelled) return;

          const sectionNotebooks = notebooks
            .filter((n) => /^section\s+\d+(\.\d+)*/i.test(n.title) || /\bch(apter)?\.?\s*\d+/i.test(n.title) || /\b\d+\.\d+\b/.test(n.title))
            .map((n) => ({
              key: `notebook:${n.id}`,
              source: "notebook" as const,
              sourceId: n.id,
              title: n.title,
              label: n.title,
              target: n.title.replace(/^section\s+/i, "§"),
            }));

          const readingTasks = courseTasks
            .filter((t) => {
              if (t.status === "done") return false;
              const type = (t.task_type || "").toLowerCase();
              const title = (t.title || "").toLowerCase();
              return type === "reading" || /^reading\b/.test(title);
            })
            .map((t) => ({
              key: `task:${t.id}`,
              source: "task" as const,
              sourceId: t.id,
              title: t.title,
              label: t.due_at
                ? `${t.title} · due ${formatTime(t.due_at) || new Date(t.due_at).toLocaleDateString()}`
                : t.title,
              target: typeof logisticsOf(t).target === "string" ? String(logisticsOf(t).target) : undefined,
            }));

          const readingResources = resources
            .filter((r) => {
              const rt = (r.resource_type || "").toLowerCase();
              const st = (r.source_type || "").toLowerCase();
              return (
                rt === "page" ||
                rt === "syllabus" ||
                rt === "file" ||
                st.includes("canvas_page") ||
                st.includes("syllabus") ||
                (r.mime_type || "").includes("pdf")
              );
            })
            .map((r) => ({
              key: `resource:${r.id}`,
              source: "resource" as const,
              sourceId: r.id,
              title: r.title,
              label: `${r.title}${r.resource_type ? ` · ${r.resource_type}` : ""}`,
            }));

          // Best-effort page ranges for a few resources (keeps form snappy).
          const withPages = await Promise.all(
            readingResources.slice(0, 12).map(async (opt) => {
              try {
                const chunks = await apiGet<ResourceChunk[]>(
                  `/resources/${opt.sourceId}/chunks?limit=50`
                );
                const pages = chunks
                  .map((c) => c.page_number)
                  .filter((n): n is number => typeof n === "number");
                if (!pages.length) return opt;
                const min = Math.min(...pages);
                const max = Math.max(...pages);
                const target = min === max ? `p. ${min}` : `pp. ${min}–${max}`;
                return {
                  ...opt,
                  target,
                  label: `${opt.title} · ${target}`,
                };
              } catch {
                return opt;
              }
            })
          );
          const remaining = readingResources.slice(12);
          if (cancelled) return;
          setCatalogOptions([...sectionNotebooks, ...readingTasks, ...withPages, ...remaining]);
        }
        setCatalogKey("");
      } catch (e) {
        if (!cancelled) {
          setCatalogOptions([]);
          setError(toErrorMessage(e));
        }
      } finally {
        if (!cancelled) setCatalogLoading(false);
      }
    }
    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [courseId, addKind]);

  const selectedCatalog = useMemo(
    () => catalogOptions.find((o) => o.key === catalogKey) || null,
    [catalogOptions, catalogKey]
  );

  function applyCatalogSelection(key: string) {
    setCatalogKey(key);
    if (!key) return;
    const opt = catalogOptions.find((o) => o.key === key);
    if (!opt) return;
    setTitle(opt.title);
    if (addKind === "reading") {
      setReadingTarget(opt.target || "");
    }
  }

  const itemOwnerLabel = useMemo(() => {
    const courseMap = new Map(courses.map((c) => [c.id, c.name]));
    const labelMap = new Map(labels.map((l) => [l.id, l.name]));
    return (task: Task) => {
      if (task.course_id) return courseMap.get(task.course_id) ?? "Course";
      const logistics = logisticsOf(task);
      if (typeof logistics.planner_label_name === "string" && logistics.planner_label_name.trim()) {
        return logistics.planner_label_name;
      }
      if (typeof logistics.planner_label_id === "string") {
        return labelMap.get(logistics.planner_label_id) ?? "Custom type";
      }
      return "General";
    };
  }, [courses, labels]);

  async function createNewLabel() {
    const name = newLabelName.trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    try {
      const created = await apiPost<PlannerLabel>("/planner/labels", { name });
      setLabels((prev) => {
        if (prev.some((l) => l.id === created.id)) return prev;
        return [...prev, created].sort((a, b) => a.name.localeCompare(b.name));
      });
      setOwnerKey(`label:${created.id}`);
      setNewLabelName("");
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelectedLabel() {
    if (!labelId) return;
    const label = labels.find((l) => l.id === labelId);
    if (!label) return;
    if (!window.confirm(`Delete type “${label.name}”? Existing items keep their text but lose this type.`)) return;
    setBusy(true);
    setError(null);
    try {
      await apiDelete(`/planner/labels/${labelId}`);
      setLabels((prev) => prev.filter((l) => l.id !== labelId));
      setOwnerKey("");
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const tasksByDay = useMemo(() => {
    const map = new Map<string, Task[]>();
    for (const task of tasks) {
      if (!task.due_at) continue;
      const due = new Date(task.due_at);
      if (Number.isNaN(due.getTime())) continue;
      const key = dayKey(due);
      const list = map.get(key) ?? [];
      list.push(task);
      map.set(key, list);
    }
    return map;
  }, [tasks]);

  const undatedOpen = useMemo(
    () => tasks.filter((t) => t.status !== "done" && !t.due_at && plannerKind(t) !== "focus"),
    [tasks]
  );

  const dayPlan = useMemo(() => {
    if (!selectedDay) {
      return {
        all: [] as Task[],
        events: [] as Task[],
        todos: { red: [] as Task[], yellow: [] as Task[], green: [] as Task[] },
        homework: [] as Task[],
        reading: [] as Task[],
        notes: [] as Task[],
        focus: null as Task | null,
      };
    }
    const all = (tasksByDay.get(dayKey(selectedDay)) ?? []).slice().sort((a, b) => {
      const ta = a.due_at ? new Date(a.due_at).getTime() : 0;
      const tb = b.due_at ? new Date(b.due_at).getTime() : 0;
      return ta - tb;
    });
    const events: Task[] = [];
    const todos = { red: [] as Task[], yellow: [] as Task[], green: [] as Task[] };
    const homework: Task[] = [];
    const reading: Task[] = [];
    const notes: Task[] = [];
    let focus: Task | null = null;
    for (const task of all) {
      const kind = plannerKind(task);
      if (kind === "focus") {
        focus = task;
        continue;
      }
      if (kind === "event") {
        events.push(task);
        continue;
      }
      if (kind === "note") {
        notes.push(task);
        continue;
      }
      if (kind === "reading") {
        reading.push(task);
        continue;
      }
      if (kind === "homework") {
        homework.push(task);
        continue;
      }
      todos[difficultyOf(task)].push(task);
    }
    return { all, events, todos, homework, reading, notes, focus };
  }, [selectedDay, tasksByDay]);

  useEffect(() => {
    setTopFocusDraft(dayPlan.focus?.title || "");
  }, [dayPlan.focus?.id, dayPlan.focus?.title, selectedDay]);

  const cells = useMemo(() => {
    const first = startOfMonth(cursor);
    const startWeekday = first.getDay();
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const prevDays = new Date(cursor.getFullYear(), cursor.getMonth(), 0).getDate();
    const out: { date: Date; inMonth: boolean }[] = [];

    for (let i = startWeekday - 1; i >= 0; i -= 1) {
      out.push({
        date: new Date(cursor.getFullYear(), cursor.getMonth() - 1, prevDays - i),
        inMonth: false,
      });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      out.push({ date: new Date(cursor.getFullYear(), cursor.getMonth(), day), inMonth: true });
    }
    while (out.length % 7 !== 0) {
      const last = out[out.length - 1].date;
      out.push({
        date: new Date(last.getFullYear(), last.getMonth(), last.getDate() + 1),
        inMonth: false,
      });
    }
    return out;
  }, [cursor]);

  const monthLabel = cursor.toLocaleString(undefined, { month: "long", year: "numeric" });
  const today = new Date();

  function openDay(date: Date) {
    setSelectedDay(date);
    const due = new Date(date);
    due.setHours(17, 0, 0, 0);
    setDueLocal(toLocalInputValue(due));
    setTitle("");
    setAddKind("todo");
    setDifficulty("yellow");
    setReadingTarget("");
    setOwnerKey("");
    setNewLabelName("");
    setCatalogKey("");
    setCatalogOptions([]);
  }

  async function createPlannerItem(opts: {
    kind: PlannerKind;
    title: string;
    difficulty?: Difficulty;
    target?: string;
    courseId?: string;
    labelId?: string;
    labelName?: string;
    dueLocal?: string;
    taskType?: string | null;
    catalog?: CatalogOption | null;
  }) {
    const trimmed = opts.title.trim();
    if (!trimmed || !selectedDay) return;
    setBusy(true);
    setError(null);
    try {
      let dueAt: string;
      if (opts.dueLocal) {
        dueAt = new Date(opts.dueLocal).toISOString();
      } else {
        const due = new Date(selectedDay);
        due.setHours(opts.kind === "note" || opts.kind === "focus" ? 12 : 17, 0, 0, 0);
        dueAt = due.toISOString();
      }

      // Scheduling an existing course assignment/reading onto this day (no duplicate).
      if (opts.catalog?.source === "task" && (opts.kind === "homework" || opts.kind === "reading")) {
        const existing = tasks.find((t) => t.id === opts.catalog!.sourceId);
        const nextLogistics: Record<string, unknown> = {
          ...(existing?.logistics_json || {}),
          kind: opts.kind,
        };
        if (opts.kind === "reading" && opts.target?.trim()) {
          nextLogistics.target = opts.target.trim();
        }
        await apiPatch<Task>(`/tasks/${opts.catalog.sourceId}`, {
          due_at: dueAt,
          logistics_json: nextLogistics,
          status: existing?.status === "done" ? "todo" : existing?.status || "todo",
        });
        setTitle("");
        setReadingTarget("");
        setCatalogKey("");
        await refresh();
        return;
      }

      const logistics: Record<string, unknown> = { kind: opts.kind };
      if (opts.kind === "todo") logistics.difficulty = opts.difficulty || "yellow";
      if (opts.kind === "reading" && opts.target?.trim()) logistics.target = opts.target.trim();
      if (opts.catalog?.source === "notebook") logistics.notebook_id = opts.catalog.sourceId;
      if (opts.catalog?.source === "resource") logistics.resource_id = opts.catalog.sourceId;
      if (opts.labelId) {
        logistics.planner_label_id = opts.labelId;
        if (opts.labelName) logistics.planner_label_name = opts.labelName;
      }

      let taskType: string | null = opts.taskType ?? null;
      if (!taskType) {
        if (opts.kind === "homework") taskType = "assignment";
        else if (opts.kind === "reading") taskType = "reading";
        else taskType = "other";
      }

      await apiPost<Task>("/tasks", {
        course_id: opts.courseId || null,
        title: trimmed,
        task_type: taskType,
        due_at: dueAt,
        status: "todo",
        logistics_json: logistics,
      });
      setTitle("");
      setReadingTarget("");
      setCatalogKey("");
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const selectedLabel = labelId ? labels.find((l) => l.id === labelId) : null;
    await createPlannerItem({
      kind: addKind,
      title,
      difficulty,
      target: readingTarget,
      courseId: courseId || undefined,
      labelId: selectedLabel?.id,
      labelName: selectedLabel?.name,
      dueLocal: dueLocal || undefined,
      catalog: selectedCatalog,
    });
  }

  async function saveTopFocus() {
    if (!selectedDay) return;
    const trimmed = topFocusDraft.trim();
    setBusy(true);
    setError(null);
    try {
      if (dayPlan.focus) {
        if (!trimmed) {
          await apiPatch(`/tasks/${dayPlan.focus.id}`, { status: "done" });
        } else {
          await apiPatch(`/tasks/${dayPlan.focus.id}`, { title: trimmed });
        }
      } else if (trimmed) {
        await createPlannerItem({ kind: "focus", title: trimmed });
        return;
      }
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleDone(task: Task) {
    setBusy(true);
    setError(null);
    try {
      await apiPatch<Task>(`/tasks/${task.id}`, {
        status: task.status === "done" ? "todo" : "done",
      });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteItem(task: Task) {
    if (!window.confirm(`Delete “${task.title}”?`)) return;
    setBusy(true);
    setError(null);
    try {
      await apiDelete(`/tasks/${task.id}`);
      if (editingId === task.id) setEditingId(null);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(task: Task) {
    setEditingId(task.id);
    setEditTitle(task.title);
    setEditDueLocal(task.due_at ? toLocalInputValue(new Date(task.due_at)) : "");
    setEditTarget(typeof logisticsOf(task).target === "string" ? String(logisticsOf(task).target) : "");
    setEditDifficulty(difficultyOf(task));
    setEditProblems(problemsToText((task.logistics_json || {}).problems));
    setEditDescription(task.description || "");
  }

  function cancelEdit() {
    setEditingId(null);
    setEditTitle("");
    setEditDueLocal("");
    setEditTarget("");
    setEditProblems("");
    setEditDescription("");
  }

  async function saveEdit(task: Task) {
    const trimmed = editTitle.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      const kind = plannerKind(task);
      const problemList = parseProblemsText(editProblems);
      const nextLogistics: Record<string, unknown> = {
        ...(task.logistics_json || {}),
        kind,
      };
      if (kind === "todo") nextLogistics.difficulty = editDifficulty;
      if (kind === "reading") {
        if (editTarget.trim()) nextLogistics.target = editTarget.trim();
        else delete nextLogistics.target;
      }
      if (problemList.length) nextLogistics.problems = problemList;
      else delete nextLogistics.problems;
      await apiPatch<Task>(`/tasks/${task.id}`, {
        title: trimmed,
        description: editDescription.trim() || null,
        due_at: kind === "note" || kind === "focus" ? task.due_at : editDueLocal ? new Date(editDueLocal).toISOString() : null,
        logistics_json: nextLogistics,
      });
      setEditingId(null);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function PlannerItem({
    task,
    extra,
    showTime = false,
  }: {
    task: Task;
    extra?: string;
    showTime?: boolean;
  }) {
    const kind = plannerKind(task);
    const isEditing = editingId === task.id;
    const timeLabel = showTime || kind === "event" ? formatTime(task.due_at) : "";

    if (isEditing) {
      return (
        <div style={{ display: "grid", gap: 8, padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
          <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} style={{ padding: 8 }} aria-label="Edit title" />
          {kind === "todo" ? (
            <select
              value={editDifficulty}
              onChange={(e) => setEditDifficulty(e.target.value as Difficulty)}
              style={{ padding: 8, maxWidth: 220 }}
            >
              <option value="red">Red (hard)</option>
              <option value="yellow">Yellow (medium)</option>
              <option value="green">Green (easy)</option>
            </select>
          ) : null}
          {kind === "reading" ? (
            <input
              value={editTarget}
              onChange={(e) => setEditTarget(e.target.value)}
              placeholder="Target pages / sections"
              style={{ padding: 8, maxWidth: 320 }}
            />
          ) : null}
          {kind !== "note" && kind !== "focus" ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="datetime-local"
                value={editDueLocal}
                onChange={(e) => setEditDueLocal(e.target.value)}
                style={{ padding: 8, maxWidth: 280 }}
              />
              <button type="button" onClick={() => setEditDueLocal("")} style={{ padding: "6px 10px" }}>
                Clear due
              </button>
            </div>
          ) : null}
          <input
            value={editProblems}
            onChange={(e) => setEditProblems(e.target.value)}
            placeholder="Problems: 1.1, 1.3, 1.5"
            style={{ padding: 8, maxWidth: 420 }}
          />
          <textarea
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            placeholder="Notes / what was assigned in class"
            rows={2}
            style={{ padding: 8, maxWidth: 520 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" disabled={busy || !editTitle.trim()} onClick={() => saveEdit(task)} style={{ padding: "6px 10px" }}>
              Save
            </button>
            <button type="button" disabled={busy} onClick={cancelEdit} style={{ padding: "6px 10px" }}>
              Cancel
            </button>
          </div>
        </div>
      );
    }

    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: 8,
          alignItems: "start",
          padding: "6px 0",
          borderBottom: "1px solid #f3f4f6",
        }}
      >
        <input
          type="checkbox"
          checked={task.status === "done"}
          disabled={busy}
          onChange={() => toggleDone(task)}
          aria-label={`Mark ${task.title} done`}
        />
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontWeight: 600,
              textDecoration: task.status === "done" ? "line-through" : "none",
              opacity: task.status === "done" ? 0.55 : 1,
              whiteSpace: kind === "note" ? "pre-wrap" : undefined,
            }}
          >
            {timeLabel ? <span style={{ color: "#1e3a5f", marginRight: 8 }}>{timeLabel}</span> : null}
            {(() => {
              const href = studyflowHrefFromTask(task);
              if (href) {
                return (
                  <Link href={href} style={{ color: "inherit", textDecoration: "underline", textUnderlineOffset: 2 }}>
                    {task.title}
                  </Link>
                );
              }
              return task.title;
            })()}
          </div>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {itemOwnerLabel(task)}
            {extra ? ` · ${extra}` : ""}
            {!showTime && kind !== "event" && kind !== "note" && task.due_at ? ` · ${formatTime(task.due_at)}` : ""}
          </div>
          {problemsToText((task.logistics_json || {}).problems) ? (
            <div style={{ fontSize: 12, color: "#374151", marginTop: 2 }}>
              Problems: {problemsToText((task.logistics_json || {}).problems)}
            </div>
          ) : null}
          <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
            {isStudyflowTask(task) ? (
              <Link
                href={studyflowHrefFromTask(task) || "#"}
                style={{ padding: "4px 8px", fontSize: 12, border: "1px solid #d1d5db", textDecoration: "none", color: "inherit" }}
              >
                Open flow
              </Link>
            ) : null}
            <button type="button" disabled={busy} onClick={() => startEdit(task)} style={{ padding: "4px 8px", fontSize: 12 }}>
              Edit
            </button>
            <button type="button" disabled={busy} onClick={() => deleteItem(task)} style={{ padding: "4px 8px", fontSize: 12 }}>
              Delete
            </button>
          </div>
        </div>
      </div>
    );
  }

  function Section({
    title: sectionTitle,
    children,
    color,
    count,
  }: {
    title: string;
    children: ReactNode;
    color?: string;
    count: number;
  }) {
    if (count === 0 && !children) return null;
    return (
      <div style={{ display: "grid", gap: 6 }}>
        <div
          style={{
            fontWeight: 700,
            fontSize: 13,
            letterSpacing: 0.02,
            color: color || "#111827",
            borderBottom: `2px solid ${color || "#e5e7eb"}`,
            paddingBottom: 4,
          }}
        >
          {sectionTitle}
          {count > 0 ? <span style={{ fontWeight: 500, color: "#6b7280", marginLeft: 8 }}>{count}</span> : null}
        </div>
        {count === 0 ? <div style={{ fontSize: 13, color: "#9ca3af" }}>Nothing here yet.</div> : children}
      </div>
    );
  }

  const openTodoCount =
    dayPlan.todos.red.filter((t) => t.status !== "done").length +
    dayPlan.todos.yellow.filter((t) => t.status !== "done").length +
    dayPlan.todos.green.filter((t) => t.status !== "done").length;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Calendar</h1>
        <p className="pageIntro">
          Click a day to open your daily planner — timeline, ADHD to-dos, homework, reading, and notes. Use courses or
          your own remembered types.
        </p>
      </div>

      <div className="card" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button type="button" onClick={() => setCursor((c) => addMonths(c, -1))} style={{ padding: "8px 12px" }}>
            ←
          </button>
          <div style={{ fontWeight: 700, minWidth: 180, textAlign: "center" }}>{monthLabel}</div>
          <button type="button" onClick={() => setCursor((c) => addMonths(c, 1))} style={{ padding: "8px 12px" }}>
            →
          </button>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={() => setCursor(startOfMonth(new Date()))} style={{ padding: "8px 12px" }}>
            Today
          </button>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>
      </div>

      {isLoading ? <LoadingState label="Loading calendar..." /> : null}
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}

      {!isLoading && !error ? (
        <>
          <div className="calendarGrid" aria-label="Month calendar">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
              <div key={d} style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", padding: "0 4px" }}>
                {d}
              </div>
            ))}
            {cells.map(({ date, inMonth }) => {
              const key = dayKey(date);
              const dayTasks = (tasksByDay.get(key) ?? []).filter((t) => plannerKind(t) !== "focus");
              const isToday = sameDay(date, today);
              const isSelected = selectedDay ? sameDay(date, selectedDay) : false;
              return (
                <button
                  key={key + String(inMonth)}
                  type="button"
                  className={`calendarCell${inMonth ? "" : " calendarCellMuted"}${isSelected ? " calendarCellSelected" : ""}`}
                  style={{
                    textAlign: "left",
                    cursor: "pointer",
                    outline: isToday ? "2px solid #111827" : undefined,
                    borderColor: isSelected ? "#1d4ed8" : undefined,
                  }}
                  onClick={() => openDay(date)}
                >
                  <div className="calendarDayNum">{date.getDate()}</div>
                  {dayTasks.slice(0, 3).map((t) => {
                    const href = studyflowHrefFromTask(t);
                    if (href) {
                      return (
                        <span
                          key={t.id}
                          className="calendarEvent"
                          title={`${itemOwnerLabel(t)} · Open StudyFlow`}
                          role="link"
                          tabIndex={0}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            router.push(href);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              router.push(href);
                            }
                          }}
                          style={{ cursor: "pointer", textDecoration: "underline" }}
                        >
                          {t.title}
                        </span>
                      );
                    }
                    return (
                      <span key={t.id} className="calendarEvent" title={itemOwnerLabel(t)}>
                        {t.title}
                      </span>
                    );
                  })}
                  {dayTasks.length > 3 ? (
                    <div style={{ fontSize: 11, color: "#6b7280" }}>+{dayTasks.length - 3} more</div>
                  ) : null}
                </button>
              );
            })}
          </div>

          {selectedDay ? (
            <div className="card" style={{ display: "grid", gap: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 18 }}>
                    {selectedDay.toLocaleDateString(undefined, {
                      weekday: "long",
                      month: "long",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
                    Daily planner · grows with what you add
                    {dayPlan.all.length ? ` · ${dayPlan.all.filter((t) => plannerKind(t) !== "focus").length} items` : ""}
                  </div>
                </div>
                <button type="button" onClick={() => setSelectedDay(null)} style={{ padding: "6px 10px" }}>
                  Close
                </button>
              </div>

              <div style={{ display: "grid", gap: 6 }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: "#1e3a5f" }}>Top focus</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <input
                    value={topFocusDraft}
                    onChange={(e) => setTopFocusDraft(e.target.value)}
                    placeholder="One main focus for the day…"
                    style={{ padding: 8, flex: "1 1 220px", minWidth: 180 }}
                  />
                  <button type="button" disabled={busy} onClick={saveTopFocus} style={{ padding: "8px 12px" }}>
                    Save focus
                  </button>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gap: 16,
                  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                  alignItems: "start",
                }}
              >
                <div style={{ display: "grid", gap: 16 }}>
                  {dayPlan.events.length > 0 ? (
                    <Section title="Timeline" color="#1e3a5f" count={dayPlan.events.length}>
                      {dayPlan.events.map((t) => (
                        <PlannerItem key={t.id} task={t} showTime />
                      ))}
                    </Section>
                  ) : null}

                  {(openTodoCount > 0 ||
                    dayPlan.todos.red.length + dayPlan.todos.yellow.length + dayPlan.todos.green.length > 0) && (
                    <div style={{ display: "grid", gap: 10 }}>
                      <div style={{ fontWeight: 700, fontSize: 13, color: "#111827" }}>Daily to-do</div>
                      {(["red", "yellow", "green"] as Difficulty[]).map((band) => {
                        const items = dayPlan.todos[band];
                        if (items.length === 0) return null;
                        const meta = DIFFICULTY_META[band];
                        return (
                          <div
                            key={band}
                            style={{
                              background: meta.bg,
                              border: `1px solid ${meta.border}`,
                              padding: 10,
                              display: "grid",
                              gap: 4,
                            }}
                          >
                            <div style={{ fontWeight: 700, fontSize: 12, color: meta.text }}>{meta.label}</div>
                            {items.map((t) => (
                              <PlannerItem key={t.id} task={t} />
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {dayPlan.homework.length > 0 ? (
                    <Section title="Homework" color="#6d28d9" count={dayPlan.homework.length}>
                      {dayPlan.homework.map((t) => (
                        <PlannerItem key={t.id} task={t} extra={t.task_type || undefined} />
                      ))}
                    </Section>
                  ) : null}

                  {dayPlan.reading.length > 0 ? (
                    <Section title="Daily reading" color="#0f766e" count={dayPlan.reading.length}>
                      {dayPlan.reading.map((t) => (
                        <PlannerItem
                          key={t.id}
                          task={t}
                          extra={typeof logisticsOf(t).target === "string" ? `target: ${logisticsOf(t).target}` : undefined}
                        />
                      ))}
                    </Section>
                  ) : null}

                  {dayPlan.notes.length > 0 ? (
                    <Section title="Notes" color="#374151" count={dayPlan.notes.length}>
                      {dayPlan.notes.map((t) => (
                        <PlannerItem key={t.id} task={t} />
                      ))}
                    </Section>
                  ) : null}

                  {dayPlan.all.filter((t) => plannerKind(t) !== "focus").length === 0 ? (
                    <EmptyState message="Empty day — add a timeline block, to-do, homework, reading, or note below." />
                  ) : null}
                </div>
              </div>

              <form onSubmit={onCreate} style={{ display: "grid", gap: 8, borderTop: "1px solid #e5e7eb", paddingTop: 12 }}>
                <div style={{ fontWeight: 600 }}>Add to this day</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <select
                    value={addKind}
                    onChange={(e) => {
                      setAddKind(e.target.value as PlannerKind);
                      setCatalogKey("");
                      setTitle("");
                      setReadingTarget("");
                    }}
                    style={{ padding: 8 }}
                  >
                    <option value="todo">To-do</option>
                    <option value="event">Timeline event</option>
                    <option value="homework">Homework</option>
                    <option value="reading">Reading</option>
                    <option value="note">Note</option>
                  </select>
                  {addKind === "todo" ? (
                    <select
                      value={difficulty}
                      onChange={(e) => setDifficulty(e.target.value as Difficulty)}
                      style={{ padding: 8 }}
                    >
                      <option value="red">Red (hard)</option>
                      <option value="yellow">Yellow (medium)</option>
                      <option value="green">Green (easy)</option>
                    </select>
                  ) : null}
                  <select
                    value={ownerKey}
                    onChange={(e) => {
                      setOwnerKey(e.target.value);
                      setCatalogKey("");
                      setTitle("");
                      setReadingTarget("");
                      setNewLabelName("");
                    }}
                    style={{ padding: 8, minWidth: 220 }}
                  >
                    <option value="">No type / course</option>
                    <option value="__add_new__">Add new type…</option>
                    {labels.length > 0 ? (
                      <optgroup label="My types">
                        {labels.map((l) => (
                          <option key={l.id} value={`label:${l.id}`}>
                            {l.name}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                    {courses.length > 0 ? (
                      <optgroup label="Courses">
                        {courses.map((c) => (
                          <option key={c.id} value={`course:${c.id}`}>
                            {c.name}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                  </select>
                </div>

                {addingNewLabel ? (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                    <input
                      value={newLabelName}
                      onChange={(e) => setNewLabelName(e.target.value)}
                      placeholder="New type name (e.g. Gym, Errands)"
                      style={{ padding: 8, flex: "1 1 200px", maxWidth: 320 }}
                    />
                    <button
                      type="button"
                      disabled={busy || !newLabelName.trim()}
                      onClick={createNewLabel}
                      style={{ padding: "8px 12px" }}
                    >
                      Save type
                    </button>
                  </div>
                ) : null}

                {labelId ? (
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, color: "#6b7280" }}>
                      Using type: {labels.find((l) => l.id === labelId)?.name || "Custom"}
                    </span>
                    <button type="button" disabled={busy} onClick={deleteSelectedLabel} style={{ padding: "4px 8px", fontSize: 12 }}>
                      Delete type
                    </button>
                  </div>
                ) : null}

                {(addKind === "homework" || addKind === "reading") && courseId ? (
                  <div style={{ display: "grid", gap: 6 }}>
                    <select
                      value={catalogKey}
                      onChange={(e) => applyCatalogSelection(e.target.value)}
                      disabled={catalogLoading}
                      style={{ padding: 8, maxWidth: 560 }}
                    >
                      <option value="">
                        {catalogLoading
                          ? "Loading course items…"
                          : addKind === "homework"
                            ? "Choose an assignment…"
                            : "Choose a chapter / reading…"}
                      </option>
                      {catalogOptions.map((opt) => (
                        <option key={opt.key} value={opt.key}>
                          {opt.label}
                        </option>
                      ))}
                      <option value="__custom__">Custom (type below)</option>
                    </select>
                    {!catalogLoading && catalogOptions.length === 0 ? (
                      <div style={{ fontSize: 12, color: "#6b7280" }}>
                        {addKind === "homework"
                          ? "No open assignments found for this course — type a custom title below, or sync Canvas."
                          : "No section notebooks / readings found — type a custom chapter below, or sync Canvas."}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {(addKind === "homework" || addKind === "reading") && !courseId ? (
                  <div style={{ fontSize: 12, color: "#6b7280" }}>
                    Pick a course to choose from its assignments or chapters. Custom types use a free-text title.
                  </div>
                ) : null}

                <input
                  value={title}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    if (catalogKey && catalogKey !== "__custom__") setCatalogKey("__custom__");
                  }}
                  placeholder={
                    addKind === "note"
                      ? "Note…"
                      : addKind === "event"
                        ? "Event title"
                        : addKind === "reading"
                          ? "Material / chapter"
                          : addKind === "homework"
                            ? "Assignment title"
                            : "Title"
                  }
                  style={{ padding: 8, maxWidth: 520 }}
                />
                {addKind === "reading" ? (
                  <input
                    value={readingTarget}
                    onChange={(e) => setReadingTarget(e.target.value)}
                    placeholder="Target pages / sections (e.g. pp. 12–18)"
                    style={{ padding: 8, maxWidth: 320 }}
                  />
                ) : null}
                {addKind !== "note" ? (
                  <input
                    type="datetime-local"
                    value={dueLocal}
                    onChange={(e) => setDueLocal(e.target.value)}
                    style={{ padding: 8, maxWidth: 280 }}
                  />
                ) : null}
                <button
                  type="submit"
                  style={{ padding: "8px 12px", width: "fit-content" }}
                  disabled={busy || !title.trim() || addingNewLabel}
                >
                  {selectedCatalog && selectedCatalog.source === "task"
                    ? `Schedule ${addKind} today`
                    : `Add ${addKind === "todo" ? "to-do" : addKind}`}
                </button>
              </form>
            </div>
          ) : null}

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Open tasks without due dates</div>
            {undatedOpen.length === 0 ? (
              <EmptyState message="Nice — every open task has a due date, or you're clear." />
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {undatedOpen.slice(0, 12).map((t) => (
                  <li key={t.id} style={{ marginBottom: 6 }}>
                    {t.course_id ? (
                      <Link href={`/courses/${t.course_id}/tasks`} style={{ fontWeight: 600, color: "inherit" }}>
                        {t.title}
                      </Link>
                    ) : (
                      <span style={{ fontWeight: 600 }}>{t.title}</span>
                    )}
                    <span style={{ color: "#555", marginLeft: 8, fontSize: 12 }}>{itemOwnerLabel(t)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
