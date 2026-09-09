import type { Task } from "./types";

export type StudyFlowBookmark = {
  resource_id: string;
  page: number;
  excerpt_id?: string | null;
  section_key?: string | null;
  snippet?: string | null;
  updated_at: string;
};

export function studyflowHrefFromTask(task: Task): string | null {
  const log = (task.logistics_json || {}) as Record<string, unknown>;
  const isStudyflow = log.kind === "studyflow" || log.studyflow === true;
  if (!isStudyflow) return null;
  const courseId = task.course_id || (typeof log.course_id === "string" ? log.course_id : null);
  if (!courseId) return null;
  const params = new URLSearchParams();
  if (typeof log.excerpt_id === "string" && log.excerpt_id) params.set("excerpt_id", log.excerpt_id);
  if (log.page != null && String(log.page)) params.set("page", String(log.page));
  if (typeof log.resource_id === "string" && log.resource_id) params.set("resource_id", log.resource_id);
  const qs = params.toString();
  return `/courses/${courseId}/study-flows${qs ? `?${qs}` : ""}`;
}

export function isStudyflowTask(task: Task): boolean {
  return studyflowHrefFromTask(task) != null;
}

function bookmarkKey(courseId: string): string {
  return `studyflow_bookmark:${courseId}`;
}

export function loadBookmarkLocal(courseId: string): StudyFlowBookmark | null {
  try {
    const raw = localStorage.getItem(bookmarkKey(courseId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StudyFlowBookmark;
    if (!parsed?.resource_id || !parsed.page) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveBookmarkLocal(courseId: string, bookmark: StudyFlowBookmark): void {
  localStorage.setItem(bookmarkKey(courseId), JSON.stringify(bookmark));
}
