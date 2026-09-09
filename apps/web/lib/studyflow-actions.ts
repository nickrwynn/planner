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

export type ExcerptStep = {
  id: string;
  action: StudyFlowAction;
  status: "pending" | "active" | "done" | "failed";
  one_time?: boolean;
  gate?: boolean;
  on_fail?: OnFailPolicy;
  artifact?: unknown;
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
  return template.steps.map((s, idx) => ({
    id: crypto.randomUUID(),
    action: s.action,
    status: idx === 0 ? "active" : "pending",
    gate: s.gate,
    on_fail: s.on_fail,
  }));
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
