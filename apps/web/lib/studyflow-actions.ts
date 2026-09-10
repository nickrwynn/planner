export type StudyFlowAction =
  | "comment"
  | "summarize"
  | "hide_recall_summarize"
  | "flashcards"
  | "quiz"
  | "sample_problem"
  | "ask_cursor"
  | "read_aloud";

export type OnFailPolicy = "restart_sequence" | "retry_step" | "continue";

export type FlowTemplateStep = {
  id: string;
  action: StudyFlowAction;
  gate?: boolean;
  on_fail?: OnFailPolicy;
};

export type FlowTemplate = {
  steps: FlowTemplateStep[];
};

/** Effort rating: green = easy, yellow = medium, red = hard. */
export type Difficulty = "easy" | "medium" | "hard";

export type StepMetrics = {
  /** Accumulated focus time on this step. */
  elapsed_ms: number;
  /** How many times the step was entered; >1 means it was retried. */
  attempts: number;
  difficulty?: Difficulty;
  /** "manual" wins over "auto" so a user rating is never overwritten. */
  difficulty_source?: "auto" | "manual";
  /** Quiz / recall outcome, 0-100. */
  mastery_pct?: number;
  /** Summary-scoring outcome, 0-100. */
  comprehension_pct?: number;
};

export type ExcerptStep = {
  id: string;
  action: StudyFlowAction;
  status: "pending" | "active" | "done" | "failed";
  one_time?: boolean;
  gate?: boolean;
  on_fail?: OnFailPolicy;
  artifact?: unknown;
  /** Set while the step is the active one; null when the clock is not running. */
  started_at?: string | null;
  metrics?: StepMetrics;
};

/**
 * A finished attempt at a step, kept after the flow restarts.
 *
 * Without this, failing a gate and restarting the sequence would erase the
 * evidence that the material was hard — which is the single most useful signal
 * a study planner has.
 */
export type StepRecord = {
  action: StudyFlowAction;
  elapsed_ms: number;
  difficulty?: Difficulty;
  mastery_pct?: number;
  comprehension_pct?: number;
  at: string;
};

export type StudyExcerpt = {
  id: string;
  text: string;
  page: number;
  section_key?: string | null;
  steps: ExcerptStep[];
  cursor_step_index: number;
  created_at: string;
  comment?: string;
  summary?: string;
  /** Attempts from earlier passes through the flow. */
  history?: StepRecord[];
};

export const ACTION_MENU: { key: StudyFlowAction; label: string }[] = [
  { key: "comment", label: "Comment" },
  { key: "summarize", label: "Summarize" },
  { key: "hide_recall_summarize", label: "Hide, recall & summarize" },
  { key: "flashcards", label: "Flashcards" },
  { key: "quiz", label: "Quiz" },
  { key: "sample_problem", label: "Sample problem" },
  { key: "ask_cursor", label: "Ask Cursor" },
  { key: "read_aloud", label: "Read aloud" },
];

export const DEFAULT_FLOW_TEMPLATE: FlowTemplate = {
  steps: [
    { id: "t1", action: "comment" },
    { id: "t2", action: "sample_problem" },
    { id: "t3", action: "summarize" },
    { id: "t4", action: "flashcards" },
    { id: "t5", action: "hide_recall_summarize" },
    { id: "t6", action: "quiz", gate: true, on_fail: "restart_sequence" },
  ],
};

export function actionLabel(action: StudyFlowAction): string {
  return ACTION_MENU.find((a) => a.key === action)?.label || action;
}

export function cloneTemplateToSteps(template: FlowTemplate): ExcerptStep[] {
  const now = new Date().toISOString();
  return template.steps.map((s, idx) => ({
    id: crypto.randomUUID(),
    action: s.action,
    status: idx === 0 ? "active" : "pending",
    gate: s.gate,
    on_fail: s.on_fail,
    // The first step's clock starts as soon as the flow is created.
    started_at: idx === 0 ? now : null,
    metrics: { elapsed_ms: 0, attempts: idx === 0 ? 1 : 0 },
  }));
}

/**
 * The template as un-started steps, for showing the flow before the student has
 * highlighted anything. Unlike `cloneTemplateToSteps` this starts no clock and
 * marks nothing active, so every course page shows the same shape whether or
 * not it has excerpts yet.
 */
export function previewStepsFromTemplate(template: FlowTemplate): ExcerptStep[] {
  return template.steps.map((s) => ({
    id: s.id,
    action: s.action,
    status: "pending",
    gate: s.gate,
    on_fail: s.on_fail,
    started_at: null,
    metrics: { elapsed_ms: 0, attempts: 0 },
  }));
}

/**
 * Typical focus time per step, in seconds. Used as the yardstick for effort:
 * taking much longer than this is the main signal that a step was hard.
 */
export const EXPECTED_STEP_SECONDS: Record<StudyFlowAction, number> = {
  comment: 90,
  summarize: 240,
  hide_recall_summarize: 300,
  flashcards: 180,
  quiz: 300,
  sample_problem: 420,
  ask_cursor: 120,
  read_aloud: 60,
};

export const EMPTY_METRICS: StepMetrics = { elapsed_ms: 0, attempts: 0 };

export function stepMetrics(step: ExcerptStep): StepMetrics {
  return step.metrics ?? EMPTY_METRICS;
}

/**
 * Rate a step red/yellow/green from how long it took, whether it needed
 * retries, and any score it produced. Returns "medium" when there is no
 * evidence either way.
 */
export function deriveDifficulty(
  action: StudyFlowAction,
  metrics: StepMetrics
): Difficulty {
  const expectedMs = (EXPECTED_STEP_SECONDS[action] ?? 180) * 1000;
  const ratio = metrics.elapsed_ms > 0 ? metrics.elapsed_ms / expectedMs : 0;
  const scores = [metrics.mastery_pct, metrics.comprehension_pct].filter(
    (v): v is number => typeof v === "number"
  );
  const worstScore = scores.length ? Math.min(...scores) : null;

  // Retries or a poor score mean hard regardless of the clock.
  if (metrics.attempts > 1) return "hard";
  if (worstScore !== null && worstScore < 60) return "hard";
  if (ratio > 1.6) return "hard";

  if (ratio > 0 && ratio < 0.7 && (worstScore === null || worstScore >= 85)) {
    return "easy";
  }
  return "medium";
}

/** The rating to display: a manual rating always wins. */
export function effectiveDifficulty(step: ExcerptStep): Difficulty | null {
  const metrics = stepMetrics(step);
  if (metrics.difficulty && metrics.difficulty_source === "manual") {
    return metrics.difficulty;
  }
  // No evidence yet — do not colour the step.
  if (metrics.elapsed_ms === 0 && metrics.attempts === 0) return metrics.difficulty ?? null;
  return metrics.difficulty ?? deriveDifficulty(step.action, metrics);
}

export type ExcerptEffort = {
  totalMs: number;
  doneSteps: number;
  totalSteps: number;
  masteryPct: number | null;
  comprehensionPct: number | null;
  hard: number;
  medium: number;
  easy: number;
  /** Estimated remaining minutes, using measured pace where available. */
  remainingMinutes: number;
};

/** Snapshot the steps that carry evidence, for keeping across a restart. */
export function archiveSteps(excerpt: StudyExcerpt): StepRecord[] {
  const at = new Date().toISOString();
  return excerpt.steps
    .filter((s) => {
      const m = stepMetrics(s);
      return (
        m.elapsed_ms > 0 ||
        typeof m.mastery_pct === "number" ||
        typeof m.comprehension_pct === "number"
      );
    })
    .map((s) => {
      const m = stepMetrics(s);
      return {
        action: s.action,
        elapsed_ms: m.elapsed_ms,
        difficulty: effectiveDifficulty(s) ?? undefined,
        mastery_pct: m.mastery_pct,
        comprehension_pct: m.comprehension_pct,
        at,
      };
    });
}

/** Roll a single excerpt's step metrics into the numbers a planner needs. */
export function excerptEffort(excerpt: StudyExcerpt): ExcerptEffort {
  let totalMs = 0;
  let doneSteps = 0;
  const mastery: number[] = [];
  const comprehension: number[] = [];
  let hard = 0;
  let medium = 0;
  let easy = 0;
  let remainingSeconds = 0;

  // Earlier passes count toward time, scores and effort mix.
  for (const record of excerpt.history ?? []) {
    totalMs += record.elapsed_ms;
    if (typeof record.mastery_pct === "number") mastery.push(record.mastery_pct);
    if (typeof record.comprehension_pct === "number") {
      comprehension.push(record.comprehension_pct);
    }
    if (record.difficulty === "hard") hard += 1;
    else if (record.difficulty === "easy") easy += 1;
    else if (record.difficulty === "medium") medium += 1;
  }

  for (const step of excerpt.steps) {
    const metrics = stepMetrics(step);
    totalMs += metrics.elapsed_ms;
    if (typeof metrics.mastery_pct === "number") mastery.push(metrics.mastery_pct);
    if (typeof metrics.comprehension_pct === "number") {
      comprehension.push(metrics.comprehension_pct);
    }
    if (step.status === "done") {
      doneSteps += 1;
      const rating = effectiveDifficulty(step);
      if (rating === "hard") hard += 1;
      else if (rating === "easy") easy += 1;
      else if (rating === "medium") medium += 1;
    } else {
      remainingSeconds += EXPECTED_STEP_SECONDS[step.action] ?? 180;
    }
  }

  const average = (values: number[]) =>
    values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;

  // If this student runs slower or faster than the baseline, carry that pace
  // into the remaining estimate.
  const expectedDoneSeconds = excerpt.steps
    .filter((s) => s.status === "done")
    .reduce((sum, s) => sum + (EXPECTED_STEP_SECONDS[s.action] ?? 180), 0);
  const pace =
    expectedDoneSeconds > 0 && totalMs > 0
      ? Math.min(3, Math.max(0.4, totalMs / 1000 / expectedDoneSeconds))
      : 1;

  return {
    totalMs,
    doneSteps,
    totalSteps: excerpt.steps.length,
    masteryPct: average(mastery),
    comprehensionPct: average(comprehension),
    hard,
    medium,
    easy,
    remainingMinutes: Math.round((remainingSeconds * pace) / 60),
  };
}

export function formatDuration(ms: number): string {
  if (ms <= 0) return "—";
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

/**
 * A single stretch of work credited to one step. `started_at` survives a
 * reload, so without this cap a step left open overnight would be credited
 * with hours of "focus time" and poison the effort ratings.
 */
const MAX_SESSION_MS = 30 * 60 * 1000;

/**
 * Move the clock to `activeIndex`: bank the time spent on whatever step was
 * running, and start timing the new one.
 */
export function retimeSteps(steps: ExcerptStep[], activeIndex: number): ExcerptStep[] {
  const now = Date.now();
  return steps.map((step, index) => {
    const metrics = { ...stepMetrics(step) };
    let started = step.started_at ?? null;

    if (started) {
      const startedMs = Date.parse(started);
      if (Number.isFinite(startedMs) && now > startedMs) {
        metrics.elapsed_ms += Math.min(now - startedMs, MAX_SESSION_MS);
      }
      started = null;
    }

    if (index === activeIndex) {
      started = new Date(now).toISOString();
      // Only a genuine redo counts as another attempt — clicking around the
      // stepper to look at a step in progress must not inflate the count.
      const isRedo = step.status === "done" || step.status === "failed";
      metrics.attempts = isRedo ? (metrics.attempts || 1) + 1 : Math.max(1, metrics.attempts || 0);
    }

    return { ...step, started_at: started, metrics };
  });
}

/** Bank elapsed time without starting a new clock (used when finishing). */
export function bankElapsed(steps: ExcerptStep[]): ExcerptStep[] {
  return retimeSteps(steps, -1);
}

export function templateStorageKey(courseId: string): string {
  return `studyflow_template:${courseId}`;
}

export function loadTemplate(courseId: string): FlowTemplate {
  try {
    const raw = localStorage.getItem(templateStorageKey(courseId));
    if (!raw) return DEFAULT_FLOW_TEMPLATE;
    const parsed = JSON.parse(raw) as FlowTemplate;
    if (!parsed?.steps?.length) return DEFAULT_FLOW_TEMPLATE;
    return parsed;
  } catch {
    return DEFAULT_FLOW_TEMPLATE;
  }
}

export function saveTemplateLocal(courseId: string, template: FlowTemplate): void {
  localStorage.setItem(templateStorageKey(courseId), JSON.stringify(template));
}
