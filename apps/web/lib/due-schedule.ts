/** Course-level recurring due schedules stored in course.grading_schema_json.due_schedule_rules */

export type DueScheduleRule = {
  id: string;
  /** Matches Task.task_type (assignment, exam, …) */
  task_type: string;
  /** Optional case-insensitive title filter, e.g. "HW" or "Homework" */
  title_contains: string;
  /** JS Date.getDay(): 0=Sun … 6=Sat */
  weekday: number;
  hour: number;
  minute: number;
  enabled: boolean;
};

export const WEEKDAY_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Sunday" },
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
];

export function readDueRules(grading: unknown): DueScheduleRule[] {
  if (!grading || typeof grading !== "object") return [];
  const raw = (grading as { due_schedule_rules?: unknown }).due_schedule_rules;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((r): r is DueScheduleRule => !!r && typeof r === "object" && typeof (r as DueScheduleRule).id === "string")
    .map((r) => ({
      id: r.id,
      task_type: r.task_type || "assignment",
      title_contains: r.title_contains || "",
      weekday: Number.isFinite(r.weekday) ? Number(r.weekday) : 4,
      hour: Number.isFinite(r.hour) ? Number(r.hour) : 23,
      minute: Number.isFinite(r.minute) ? Number(r.minute) : 59,
      enabled: r.enabled !== false,
    }));
}

export function writeDueRules(grading: unknown, rules: DueScheduleRule[]): Record<string, unknown> {
  const base =
    grading && typeof grading === "object" && !Array.isArray(grading)
      ? { ...(grading as Record<string, unknown>) }
      : {};
  return { ...base, due_schedule_rules: rules };
}

export function taskMatchesDueRule(
  task: { title: string; task_type?: string | null },
  rule: DueScheduleRule
): boolean {
  if (!rule.enabled) return false;
  if (rule.task_type && (task.task_type || "assignment") !== rule.task_type) return false;
  const needle = rule.title_contains.trim().toLowerCase();
  if (needle && !task.title.toLowerCase().includes(needle)) return false;
  return true;
}

/** Next occurrence of rule weekday at local hour:minute (today if still upcoming). */
export function nextDueForRule(rule: DueScheduleRule, from: Date = new Date()): Date {
  const d = new Date(from);
  d.setSeconds(0, 0);
  d.setHours(rule.hour, rule.minute, 0, 0);
  const delta = (rule.weekday - from.getDay() + 7) % 7;
  d.setDate(from.getDate() + delta);
  if (delta === 0 && d.getTime() <= from.getTime()) {
    d.setDate(d.getDate() + 7);
  }
  return d;
}

/** Most recent occurrence on/before `from`. */
export function previousDueForRule(rule: DueScheduleRule, from: Date = new Date()): Date {
  const d = new Date(from);
  d.setSeconds(0, 0);
  d.setHours(rule.hour, rule.minute, 0, 0);
  const delta = (from.getDay() - rule.weekday + 7) % 7;
  d.setDate(from.getDate() - delta);
  if (delta === 0 && d.getTime() > from.getTime()) {
    d.setDate(d.getDate() - 7);
  }
  return d;
}

/**
 * Nth weekly occurrence for a rule.
 * index 0 = next (or previous) due; 1 = one week further in that direction, etc.
 */
export function dueOccurrenceForRule(
  rule: DueScheduleRule,
  index: number,
  mode: "next" | "previous" = "next",
  from: Date = new Date()
): Date {
  const n = Math.max(0, Math.floor(index));
  const base = mode === "next" ? nextDueForRule(rule, from) : previousDueForRule(rule, from);
  const d = new Date(base);
  d.setDate(d.getDate() + (mode === "next" ? n : -n) * 7);
  return d;
}

/** Sort HW 1, HW 2, HW 10… in assignment order (not lexicographic). */
export function compareTasksForSchedule(
  a: { title: string; created_at?: string | null },
  b: { title: string; created_at?: string | null }
): number {
  const chunks = (s: string) =>
    s
      .toLowerCase()
      .split(/(\d+)/)
      .filter(Boolean)
      .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
  const ac = chunks(a.title || "");
  const bc = chunks(b.title || "");
  const len = Math.max(ac.length, bc.length);
  for (let i = 0; i < len; i += 1) {
    const x = ac[i];
    const y = bc[i];
    if (x == null) return -1;
    if (y == null) return 1;
    if (typeof x === "number" && typeof y === "number") {
      if (x !== y) return x - y;
      continue;
    }
    const xs = String(x);
    const ys = String(y);
    if (xs !== ys) return xs < ys ? -1 : 1;
  }
  const at = a.created_at ? Date.parse(a.created_at) : 0;
  const bt = b.created_at ? Date.parse(b.created_at) : 0;
  return at - bt;
}

export function matchingRuleForTask(
  task: { title: string; task_type?: string | null },
  rules: DueScheduleRule[]
): DueScheduleRule | null {
  // Prefer the most specific enabled rule (longest title filter), then first match.
  const matches = rules.filter((r) => taskMatchesDueRule(task, r));
  if (!matches.length) return null;
  return [...matches].sort(
    (a, b) => (b.title_contains.trim().length || 0) - (a.title_contains.trim().length || 0)
  )[0];
}

/** Build staggered weekly due dates for tasks that match a rule (index 0 = base week). */
export function planDueDatesForTasks<T extends { title: string; task_type?: string | null; created_at?: string | null }>(
  tasks: T[],
  rule: DueScheduleRule,
  mode: "next" | "previous" = "next",
  from: Date = new Date()
): Array<{ task: T; due: Date }> {
  const sorted = [...tasks].sort(compareTasksForSchedule);
  return sorted.map((task, index) => ({
    task,
    due: dueOccurrenceForRule(rule, index, mode, from),
  }));
}

export function parseProblemsText(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function problemsToText(problems: unknown): string {
  if (Array.isArray(problems)) return problems.map(String).join(", ");
  if (typeof problems === "string") return problems;
  return "";
}
