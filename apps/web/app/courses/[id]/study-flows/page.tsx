"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../../../components/async-state";
import { StudyArtifactView } from "../../../../components/study-artifact-view";
import { StudyNotebook, type PaperStyle } from "../../../../components/study-notebook";
import { recognizeHandwriting } from "../../../../lib/handwriting-recognize";
import { apiGet, apiGetArrayBuffer, apiPost, toErrorMessage } from "../../../../lib/api";
import { speakText, stopSpeaking } from "../../../../lib/speech";
import {
  loadBookmarkLocal,
  saveBookmarkLocal,
  type StudyFlowBookmark,
} from "../../../../lib/studyflow-nav";
import {
  ACTION_MENU,
  actionLabel,
  cloneTemplateToSteps,
  DEFAULT_FLOW_TEMPLATE,
  loadTemplate,
  saveTemplateLocal,
  type ExcerptStep,
  type FlowTemplate,
  type FlowTemplateStep,
  type StudyExcerpt,
  type StudyFlowAction,
} from "../../../../lib/studyflow-actions";
import type { Resource, StudyFlow, StudyFlowRun } from "../../../../lib/types";

const PdfReader = dynamic(
  () => import("../../../../components/pdf-reader").then((m) => m.PdfReader),
  { ssr: false, loading: () => <div className="studyPdfLoading">Loading PDF reader…</div> }
);

type ResourceSection = {
  key: string;
  title: string;
  kind: string;
  page_start: number | null;
  page_end: number | null;
};

type MenuState = { x: number; y: number; text: string; mode: "select" | "context" } | null;

type ScoreResult = {
  score: number;
  coverage: number;
  verbatim_penalty: number;
  feedback: string;
};

type AiStatus = { configured: boolean; message: string; model: string | null };

type SavedNoteInfo = {
  notebook_id: string;
  notebook_title: string;
  document_title: string;
};

function isPdfResource(r: Resource): boolean {
  return (r.mime_type || "").includes("pdf") || (r.original_filename || r.title || "").toLowerCase().endsWith(".pdf");
}

export default function CourseStudyFlowsPage({ params }: { params: { id: string } }) {
  const courseId = params.id;
  const [flow, setFlow] = useState<StudyFlow | null>(null);
  const [resources, setResources] = useState<Resource[]>([]);
  const [sections, setSections] = useState<ResourceSection[]>([]);
  const [sectionKey, setSectionKey] = useState("");
  const [pdfData, setPdfData] = useState<ArrayBuffer | null>(null);
  const [pdfLoadError, setPdfLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1.25);
  const [pageInput, setPageInput] = useState("1");

  const [template, setTemplate] = useState<FlowTemplate>(DEFAULT_FLOW_TEMPLATE);
  const [editingFlow, setEditingFlow] = useState(false);
  const [excerpts, setExcerpts] = useState<StudyExcerpt[]>([]);
  const [activeExcerptId, setActiveExcerptId] = useState<string | null>(null);

  const [menu, setMenu] = useState<MenuState>(null);
  const [selectedText, setSelectedText] = useState("");
  const [commentDraft, setCommentDraft] = useState("");
  const [askDraft, setAskDraft] = useState("");
  const [askAnswer, setAskAnswer] = useState<string | null>(null);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [summaryScore, setSummaryScore] = useState<ScoreResult | null>(null);
  const [hideSource, setHideSource] = useState(false);
  const [artifactView, setArtifactView] = useState<Record<string, unknown> | null>(null);
  const [quizPassed, setQuizPassed] = useState<boolean | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [savedNote, setSavedNote] = useState<SavedNoteInfo | null>(null);
  const [workspaceView, setWorkspaceView] = useState<"resource" | "notebook">("resource");
  const [paperStyle, setPaperStyle] = useState<PaperStyle>("notebook");
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarDate, setCalendarDate] = useState("");
  const [calendarTime, setCalendarTime] = useState("");
  const [bookmark, setBookmark] = useState<StudyFlowBookmark | null>(null);
  const [bookmarkFlash, setBookmarkFlash] = useState<string | null>(null);
  const [findOpen, setFindOpen] = useState(false);
  const [findQuery, setFindQuery] = useState("");
  const [findHits, setFindHits] = useState<
    { page_number: number | null; snippet: string; chunk_id: string }[]
  >([]);
  const [findIndex, setFindIndex] = useState(0);
  const [findBusy, setFindBusy] = useState(false);
  const [textPreview, setTextPreview] = useState<string | null>(null);
  const findInputRef = useRef<HTMLInputElement | null>(null);
  const placeRestoredRef = useRef(false);
  const skipAutoBookmarkRef = useRef(true);
  const stubUpgradeAttemptedRef = useRef<string | null>(null);

  const run = flow?.active_run ?? null;
  const attached = resources.find((r) => r.id === run?.resource_id) || null;
  const isPdf = !!attached && isPdfResource(attached);
  const isPlainText =
    !!attached &&
    !isPdf &&
    ((attached.mime_type || "").startsWith("text/") ||
      (attached.original_filename || "").toLowerCase().endsWith(".txt"));
  const readableResources = useMemo(() => {
    const rows = [...resources];
    rows.sort((a, b) => {
      const ap = isPdfResource(a) ? 0 : 1;
      const bp = isPdfResource(b) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return a.title.localeCompare(b.title);
    });
    return rows;
  }, [resources]);
  const activeExcerpt = excerpts.find((e) => e.id === activeExcerptId) || null;
  const activeStep: ExcerptStep | null = activeExcerpt
    ? activeExcerpt.steps[activeExcerpt.cursor_step_index] || null
    : null;

  const progressSummary = useMemo(() => {
    const doneExcerpts = excerpts.filter((e) => e.steps.every((s) => s.status === "done")).length;
    const stepDone = activeExcerpt ? activeExcerpt.steps.filter((s) => s.status === "done").length : 0;
    const stepTotal = activeExcerpt?.steps.length || 0;
    return `${excerpts.length} excerpt${excerpts.length === 1 ? "" : "s"} · ${doneExcerpts} complete · active ${stepDone}/${stepTotal} steps`;
  }, [excerpts, activeExcerpt]);

  const persistProgress = useCallback(
    async (
      nextExcerpts: StudyExcerpt[],
      nextActive: string | null,
      nextTemplate?: FlowTemplate,
      nextBookmark?: StudyFlowBookmark | null
    ) => {
      if (!run) return;
      const bm = nextBookmark === undefined ? bookmark : nextBookmark;
      const progress = {
        excerpts: nextExcerpts,
        active_excerpt_id: nextActive,
        flow_template: nextTemplate || template,
        bookmark: bm,
      };
      const withProgress = await apiPost<StudyFlowRun>(`/study-flows/runs/${run.id}/advance`, {
        step_key: run.current_step_key || "highlight_ask",
        payload_json: { studyflow_v2: progress },
        complete: false,
      });
      setFlow((prev) =>
        prev
          ? {
              ...prev,
              active_run: {
                ...withProgress,
                progress_json: {
                  ...(withProgress.progress_json || {}),
                  ...progress,
                },
              },
            }
          : prev
      );
    },
    [run, template, bookmark]
  );

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [flowRow, resourceRows, status] = await Promise.all([
        apiGet<StudyFlow>(`/study-flows/by-course/${courseId}`),
        apiGet<Resource[]>(`/resources?course_id=${encodeURIComponent(courseId)}&limit=100`),
        apiGet<AiStatus>("/ai/status").catch(() => ({
          configured: false,
          message: "Could not load agent status.",
          model: null,
        })),
      ]);
      setFlow(flowRow);
      setResources(resourceRows);
      setAiStatus(status);
      const tpl = loadTemplate(courseId);
      const fromRun = (flowRow.active_run?.progress_json as { flow_template?: FlowTemplate } | null)?.flow_template;
      const resolved = fromRun?.steps?.length ? fromRun : tpl;
      setTemplate(resolved);
      saveTemplateLocal(courseId, resolved);

      const progress = (flowRow.active_run?.progress_json || {}) as {
        excerpts?: StudyExcerpt[];
        active_excerpt_id?: string;
        bookmark?: StudyFlowBookmark | null;
      };
      // Also recover from step payload mirror
      const stepPayload = flowRow.active_run?.steps?.find((s) => s.step_key === "read" || s.step_key === "highlight_ask")
        ?.payload_json as {
        studyflow_v2?: {
          excerpts?: StudyExcerpt[];
          active_excerpt_id?: string;
          bookmark?: StudyFlowBookmark | null;
        };
      } | undefined;
      const mirrored = stepPayload?.studyflow_v2;
      const nextExcerpts = progress.excerpts || mirrored?.excerpts || [];
      const nextActive = progress.active_excerpt_id || mirrored?.active_excerpt_id || nextExcerpts[0]?.id || null;
      setExcerpts(nextExcerpts);
      setActiveExcerptId(nextActive);
      const bm = progress.bookmark || mirrored?.bookmark || loadBookmarkLocal(courseId);
      setBookmark(bm);
      placeRestoredRef.current = false;
      skipAutoBookmarkRef.current = true;
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    async function loadPdf() {
      if (!run?.resource_id || !isPdf) {
        setPdfData(null);
        return;
      }
      try {
        const buf = await apiGetArrayBuffer(`/resources/${run.resource_id}/content`);
        if (!cancelled) {
          setPdfData(buf);
          setPdfLoadError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setPdfData(null);
          setPdfLoadError(toErrorMessage(e));
        }
      }
    }
    void loadPdf();
    return () => {
      cancelled = true;
    };
  }, [run?.resource_id, isPdf]);

  useEffect(() => {
    let cancelled = false;
    async function loadText() {
      if (!run?.resource_id || !isPlainText) {
        setTextPreview(null);
        return;
      }
      try {
        const buf = await apiGetArrayBuffer(`/resources/${run.resource_id}/content`);
        const text = new TextDecoder().decode(buf);
        if (!cancelled) setTextPreview(text);
      } catch {
        if (!cancelled) setTextPreview(null);
      }
    }
    void loadText();
    return () => {
      cancelled = true;
    };
  }, [run?.resource_id, isPlainText]);

  // Thin Canvas page stubs (filename-only) → ask API to upgrade to embedded PDF.
  useEffect(() => {
    if (!attached || isPdf || !isPlainText || textPreview == null) return;
    const thin =
      textPreview.trim().length < 220 &&
      (textPreview.trim().split(/\s+/).length <= 8 || !/\s/.test(textPreview.trim()));
    if (!thin) return;
    if (stubUpgradeAttemptedRef.current === attached.id) return;
    stubUpgradeAttemptedRef.current = attached.id;
    let cancelled = false;
    async function upgrade() {
      try {
        await apiPost(`/resources/${attached!.id}/reindex`, {});
        if (!cancelled) await refresh();
      } catch {
        /* keep stub; user can pick PDF manually */
      }
    }
    void upgrade();
    return () => {
      cancelled = true;
    };
  }, [attached, isPdf, isPlainText, textPreview, refresh]);

  useEffect(() => {
    let cancelled = false;
    async function loadSections() {
      if (!run?.resource_id || !isPdf) {
        setSections([]);
        return;
      }
      try {
        const rows = await apiGet<ResourceSection[]>(`/resources/${run.resource_id}/sections`);
        if (!cancelled) setSections(rows);
      } catch {
        if (!cancelled) setSections([]);
      }
    }
    void loadSections();
    return () => {
      cancelled = true;
    };
  }, [run?.resource_id, isPdf]);

  useEffect(() => () => stopSpeaking(), []);

  async function updateExcerpts(next: StudyExcerpt[], nextActive: string | null = activeExcerptId) {
    setExcerpts(next);
    setActiveExcerptId(nextActive);
    try {
      await persistProgress(next, nextActive);
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function savePlaceBookmark(opts?: { snippet?: string | null; announce?: boolean }) {
    if (!run?.resource_id) {
      setError("Attach a textbook before bookmarking.");
      return;
    }
    const next: StudyFlowBookmark = {
      resource_id: run.resource_id,
      page,
      excerpt_id: activeExcerptId,
      section_key: sectionKey || null,
      snippet: (opts?.snippet ?? selectedText ?? activeExcerpt?.text ?? "").slice(0, 240) || null,
      updated_at: new Date().toISOString(),
    };
    setBookmark(next);
    saveBookmarkLocal(courseId, next);
    try {
      await persistProgress(excerpts, activeExcerptId, undefined, next);
      if (opts?.announce !== false) {
        setBookmarkFlash(`Bookmark saved · page ${next.page}`);
        window.setTimeout(() => setBookmarkFlash(null), 2500);
      }
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function runFind(query: string) {
    const q = query.trim();
    if (!q || !run?.resource_id) {
      setFindHits([]);
      return;
    }
    setFindBusy(true);
    try {
      const hits = await apiGet<
        { page_number: number | null; snippet: string; chunk_id: string }[]
      >(
        `/search?q=${encodeURIComponent(q)}&resource_id=${encodeURIComponent(run.resource_id)}&course_id=${encodeURIComponent(courseId)}&limit=30`
      );
      setFindHits(hits);
      setFindIndex(0);
      const firstPage = hits[0]?.page_number;
      if (firstPage) goToPage(firstPage);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setFindBusy(false);
    }
  }

  function jumpFind(delta: number) {
    if (!findHits.length) return;
    const next = (findIndex + delta + findHits.length) % findHits.length;
    setFindIndex(next);
    const p = findHits[next]?.page_number;
    if (p) goToPage(p);
  }

  useEffect(() => {
    if (isLoading || !run || placeRestoredRef.current) return;
    placeRestoredRef.current = true;
    const activeRun = run;
    const sp = new URLSearchParams(window.location.search);
    const excerptId = sp.get("excerpt_id");
    const pageParam = sp.get("page");
    const resourceId = sp.get("resource_id");

    async function apply() {
      if (resourceId && activeRun.resource_id !== resourceId) {
        try {
          const next = await apiPost<StudyFlowRun>(`/study-flows/runs/${activeRun.id}/attach-resource`, {
            resource_id: resourceId,
          });
          setFlow((prev) => (prev ? { ...prev, active_run: next } : prev));
        } catch (e) {
          setError(toErrorMessage(e));
        }
      }
      if (excerptId) {
        const ex = excerpts.find((e) => e.id === excerptId);
        if (ex) {
          setActiveExcerptId(ex.id);
          setSelectedText(ex.text);
          goToPage(pageParam ? Number(pageParam) || ex.page : ex.page);
          if (ex.section_key) setSectionKey(ex.section_key);
          skipAutoBookmarkRef.current = false;
          return;
        }
      }
      if (pageParam) {
        goToPage(Number(pageParam) || 1);
        skipAutoBookmarkRef.current = false;
        return;
      }
      const bm = bookmark || loadBookmarkLocal(courseId);
      if (bm) {
        if (bm.resource_id && activeRun.resource_id !== bm.resource_id) {
          try {
            const next = await apiPost<StudyFlowRun>(`/study-flows/runs/${activeRun.id}/attach-resource`, {
              resource_id: bm.resource_id,
            });
            setFlow((prev) => (prev ? { ...prev, active_run: next } : prev));
          } catch {
            /* keep current resource */
          }
        }
        goToPage(bm.page);
        if (bm.excerpt_id && excerpts.some((e) => e.id === bm.excerpt_id)) {
          setActiveExcerptId(bm.excerpt_id);
        }
        if (bm.section_key) setSectionKey(bm.section_key);
      }
      skipAutoBookmarkRef.current = false;
    }
    void apply();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once after initial load
  }, [isLoading, run?.id, excerpts.length]);

  useEffect(() => {
    if (skipAutoBookmarkRef.current || isLoading || !run?.resource_id) return;
    const handle = window.setTimeout(() => {
      const next: StudyFlowBookmark = {
        resource_id: run.resource_id!,
        page,
        excerpt_id: activeExcerptId,
        section_key: sectionKey || null,
        snippet: bookmark?.snippet || null,
        updated_at: new Date().toISOString(),
      };
      setBookmark(next);
      saveBookmarkLocal(courseId, next);
      void persistProgress(excerpts, activeExcerptId, undefined, next).catch(() => undefined);
    }, 900);
    return () => window.clearTimeout(handle);
  }, [page, activeExcerptId, sectionKey, run?.resource_id, isLoading]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setFindOpen(true);
        window.setTimeout(() => findInputRef.current?.focus(), 0);
      }
      if (mod && e.key.toLowerCase() === "g" && findOpen) {
        e.preventDefault();
        jumpFind(e.shiftKey ? -1 : 1);
      }
      if (e.key === "Escape" && findOpen) {
        setFindOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [findOpen, findHits, findIndex]);

  async function attachResource(resourceId: string) {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<StudyFlowRun>(`/study-flows/runs/${run.id}/attach-resource`, {
        resource_id: resourceId,
      });
      setFlow((prev) => (prev ? { ...prev, active_run: next } : prev));
      setPage(1);
      setPageInput("1");
      setSectionKey("");
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function goToPage(next: number) {
    if (!pageCount && next < 1) return;
    const clamped = pageCount ? Math.min(pageCount, Math.max(1, next)) : Math.max(1, next);
    setPage(clamped);
    setPageInput(String(clamped));
    setMenu(null);
  }

  function onChapterChange(key: string) {
    setSectionKey(key);
    const sec = sections.find((s) => s.key === key);
    if (sec?.page_start) goToPage(sec.page_start);
  }

  async function readAloudText(text: string) {
    const t = text.trim();
    if (!t) return;
    setSpeaking(true);
    setMenu(null);
    await speakText(t, {
      onEnd: () => setSpeaking(false),
      onError: (msg) => {
        setSpeaking(false);
        setError(msg);
      },
    });
  }

  function createExcerptFromText(text: string, opts?: { openFirst?: boolean }) {
    const steps = cloneTemplateToSteps(template);
    const excerpt: StudyExcerpt = {
      id: crypto.randomUUID(),
      text: text.trim(),
      page,
      section_key: sectionKey || null,
      steps,
      cursor_step_index: 0,
      created_at: new Date().toISOString(),
    };
    const next = [excerpt, ...excerpts];
    void updateExcerpts(next, excerpt.id);
    setSelectedText(text.trim());
    setHideSource(false);
    setArtifactView(null);
    setQuizPassed(null);
    setCommentDraft("");
    setAskDraft("");
    setAskAnswer(null);
    setSummaryDraft("");
    setSummaryScore(null);
    if (opts?.openFirst !== false) {
      openActionForExcerpt(excerpt, excerpt.steps[0]?.action || "comment");
    }
    return excerpt;
  }

  function openActionForExcerpt(excerpt: StudyExcerpt, action: StudyFlowAction) {
    setActiveExcerptId(excerpt.id);
    setSelectedText(excerpt.text);
    setHideSource(action === "hide_recall_summarize");
    if (action === "flashcards" || action === "quiz" || action === "sample_problem") {
      void runStudyLabAction(excerpt, action);
    }
  }

  function injectOneTimeAction(action: StudyFlowAction, text?: string) {
    let excerpt = activeExcerpt;
    if (!excerpt && text?.trim()) {
      excerpt = createExcerptFromText(text, { openFirst: false });
    }
    if (!excerpt) {
      setError("Highlight text first.");
      return;
    }
    if (action === "read_aloud") {
      void readAloudText(excerpt.text);
      return;
    }
    const step: ExcerptStep = {
      id: crypto.randomUUID(),
      action,
      status: "active",
      one_time: true,
    };
    const steps = [...excerpt.steps];
    const insertAt = Math.min(excerpt.cursor_step_index + 1, steps.length);
    steps.splice(insertAt, 0, step);
    // Mark previous active as pending if needed
    const nextExcerpt: StudyExcerpt = {
      ...excerpt,
      steps: steps.map((s, i) => ({
        ...s,
        status: i === insertAt ? "active" : s.status === "active" ? "pending" : s.status,
      })),
      cursor_step_index: insertAt,
    };
    const base = excerpts.some((e) => e.id === excerpt.id) ? excerpts : [excerpt, ...excerpts];
    const next = base.map((e) => (e.id === excerpt!.id ? nextExcerpt : e));
    void updateExcerpts(next, excerpt.id);
    openActionForExcerpt(nextExcerpt, action);
    setMenu(null);
  }

  function markStepDone(excerptId: string, stepId: string, patch?: Partial<StudyExcerpt>) {
    const excerpt = excerpts.find((e) => e.id === excerptId);
    if (!excerpt) return;
    let steps = excerpt.steps.map((s) => (s.id === stepId ? { ...s, status: "done" as const } : s));
    let cursor = excerpt.cursor_step_index;
    const cur = excerpt.steps[cursor];
    if (cur?.id === stepId) {
      const nextIdx = cursor + 1;
      if (nextIdx < steps.length) {
        steps = steps.map((s, i) => (i === nextIdx ? { ...s, status: "active" } : s));
        cursor = nextIdx;
      } else {
        cursor = steps.length;
      }
    }
    const nextExcerpt: StudyExcerpt = { ...excerpt, ...patch, steps, cursor_step_index: cursor };
    void updateExcerpts(
      excerpts.map((e) => (e.id === excerptId ? nextExcerpt : e)),
      excerptId
    );
    if (nextExcerpt.steps[cursor]) {
      openActionForExcerpt(nextExcerpt, nextExcerpt.steps[cursor].action);
    }
  }

  function restartExcerpt(excerptId: string) {
    const excerpt = excerpts.find((e) => e.id === excerptId);
    if (!excerpt) return;
    const steps = cloneTemplateToSteps(template);
    const nextExcerpt: StudyExcerpt = { ...excerpt, steps, cursor_step_index: 0 };
    void updateExcerpts(
      excerpts.map((e) => (e.id === excerptId ? nextExcerpt : e)),
      excerptId
    );
    setQuizPassed(null);
    setArtifactView(null);
    openActionForExcerpt(nextExcerpt, steps[0]?.action || "comment");
  }

  async function saveToNotes(opts: {
    highlight: string;
    student_text: string;
    kind: string;
    latex?: string | null;
  }) {
    if (!run) return;
    const saved = await apiPost<SavedNoteInfo>(`/study-flows/runs/${run.id}/save-note`, {
      highlight: opts.highlight,
      student_text: opts.student_text,
      kind: opts.kind,
      latex: opts.latex || null,
      step_key: activeStep?.action || "comment",
      page_number: page || null,
      section_hint: sectionKey || opts.highlight || null,
    });
    setSavedNote(saved);
    setWorkspaceView("notebook");
  }

  async function saveComment() {
    if (!activeExcerpt || !commentDraft.trim()) return;
    setBusy(true);
    try {
      await saveToNotes({
        highlight: activeExcerpt.text,
        student_text: commentDraft.trim(),
        kind: "comment",
      });
      markStepDone(activeExcerpt.id, activeStep?.id || "", { comment: commentDraft.trim() });
      setCommentDraft("");
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function askAgent() {
    if (!activeExcerpt || !askDraft.trim()) return;
    setBusy(true);
    try {
      const message = `Regarding this passage:\n"""${activeExcerpt.text}"""\n\n${askDraft.trim()}`;
      const res = await apiPost<{ answer: string }>("/ai/ask", {
        message,
        course_id: courseId,
        resource_ids: run?.resource_id ? [run.resource_id] : undefined,
        allow_general_knowledge: true,
        allow_web_lookup: true,
      });
      setAskAnswer(res.answer);
      await saveToNotes({
        highlight: activeExcerpt.text,
        student_text: `${askDraft.trim()}\n\nAgent: ${res.answer}`,
        kind: "ask",
      });
      if (activeStep?.action === "ask_cursor") {
        markStepDone(activeExcerpt.id, activeStep.id);
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function scoreSummary() {
    if (!activeExcerpt || !summaryDraft.trim()) return;
    setBusy(true);
    try {
      const score = await apiPost<ScoreResult>("/study-flows/score", {
        source_text: activeExcerpt.text.slice(0, 12000),
        student_text: summaryDraft.trim(),
      });
      setSummaryScore(score);
      await saveToNotes({
        highlight: activeExcerpt.text,
        student_text: summaryDraft.trim(),
        kind: "summary",
      });
      if (activeStep && (activeStep.action === "summarize" || activeStep.action === "hide_recall_summarize")) {
        markStepDone(activeExcerpt.id, activeStep.id, { summary: summaryDraft.trim() });
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function runStudyLabAction(excerpt: StudyExcerpt, action: "flashcards" | "quiz" | "sample_problem") {
    if (!run?.resource_id) return;
    setBusy(true);
    setError(null);
    setArtifactView(null);
    try {
      const endpoint =
        action === "flashcards" ? "/ai/flashcards" : action === "quiz" ? "/ai/quizzes" : "/ai/sample-problems";
      const pageStart = Math.max(1, excerpt.page - 1);
      const pageEnd = excerpt.page + 2;
      const created = await apiPost<{
        artifact_id: string;
        title?: string;
        cards?: unknown[];
        items?: unknown[];
        problems?: unknown[];
      }>(endpoint, {
        course_id: courseId,
        resource_ids: [run.resource_id],
        section_keys: excerpt.section_key ? [excerpt.section_key] : sectionKey ? [sectionKey] : [],
        page_start: pageStart,
        page_end: pageEnd,
        title: `${actionLabel(action)} · p${excerpt.page}`,
        context_text: excerpt.text,
      });
      const detail = await apiGet<{ content_json: Record<string, unknown>; artifact_type: string }>(
        `/ai/artifacts/${created.artifact_id}`
      );
      setArtifactView({ ...detail.content_json, _type: detail.artifact_type });
      if (action !== "quiz" && activeStep?.action === action) {
        markStepDone(excerpt.id, activeStep.id);
      }
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function onQuizPass(pass: boolean) {
    if (!activeExcerpt || !activeStep || activeStep.action !== "quiz") return;
    setQuizPassed(pass);
    if (pass) {
      markStepDone(activeExcerpt.id, activeStep.id);
      return;
    }
    const policy = activeStep.on_fail || "restart_sequence";
    if (policy === "restart_sequence") {
      restartExcerpt(activeExcerpt.id);
    } else if (policy === "retry_step") {
      setArtifactView(null);
      void runStudyLabAction(activeExcerpt, "quiz");
    } else {
      markStepDone(activeExcerpt.id, activeStep.id);
    }
  }

  /** Returns the recognized text; the notebook inserts it at the caret. */
  async function onRecognizeInk(imageBase64: string, mode: "text" | "math"): Promise<string> {
    try {
      const res = await recognizeHandwriting(imageBase64, mode);
      return (res.text || "").trim();
    } catch (e) {
      setError(toErrorMessage(e));
      return "";
    }
  }

  function saveFlowTemplate(next: FlowTemplate) {
    setTemplate(next);
    saveTemplateLocal(courseId, next);
    void persistProgress(excerpts, activeExcerptId, next);
  }

  async function scheduleOnCalendar() {
    if (!activeExcerpt) return;
    setBusy(true);
    try {
      let due: string | null = null;
      if (calendarDate) {
        due = calendarTime ? new Date(`${calendarDate}T${calendarTime}`).toISOString() : `${calendarDate}T12:00:00.000Z`;
      }
      await apiPost("/tasks", {
        course_id: courseId,
        title: `StudyFlow: ${activeExcerpt.text.slice(0, 80)}`,
        status: "todo",
        task_type: "reading",
        due_at: due,
        logistics_json: {
          kind: "studyflow",
          course_id: courseId,
          resource_id: run?.resource_id,
          excerpt_id: activeExcerpt.id,
          page: activeExcerpt.page,
          studyflow: true,
        },
      });
      setCalendarOpen(false);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function renderActionPanel() {
    if (!activeExcerpt || !activeStep) {
      return (
        <div className="studySideCard">
          <div className="studySideTitle">StudyFlow</div>
          <div className="studySideMuted">Highlight text to start this excerpt’s StudyFlow sequence.</div>
        </div>
      );
    }
    const action = activeStep.action;
    return (
      <div className="studySideCard">
        <div className="studySideTitle">
          Step: {actionLabel(action)}
          {activeStep.one_time ? " (one-time)" : ""}
        </div>
        <div className="studyQuote">
          {activeExcerpt.text.slice(0, 280)}
          {activeExcerpt.text.length > 280 ? "…" : ""}
        </div>

        {action === "comment" ? (
          <>
            <textarea
              value={commentDraft}
              onChange={(e) => setCommentDraft(e.target.value)}
              rows={4}
              placeholder="Your comment…"
              spellCheck
              autoCorrect="on"
              autoCapitalize="sentences"
            />
            <button type="button" disabled={busy || !commentDraft.trim()} onClick={saveComment}>
              Save comment & continue
            </button>
          </>
        ) : null}

        {action === "ask_cursor" ? (
          <>
            <textarea value={askDraft} onChange={(e) => setAskDraft(e.target.value)} rows={3} placeholder="Ask about this passage…" />
            <button type="button" disabled={busy || !askDraft.trim() || !aiStatus?.configured} onClick={askAgent}>
              Ask Cursor
            </button>
            {askAnswer ? <div className="studySideMuted" style={{ whiteSpace: "pre-wrap" }}>{askAnswer}</div> : null}
          </>
        ) : null}

        {action === "summarize" || action === "hide_recall_summarize" ? (
          <>
            <textarea
              value={summaryDraft}
              onChange={(e) => setSummaryDraft(e.target.value)}
              rows={6}
              placeholder={action === "hide_recall_summarize" ? "Write from memory…" : "Summarize this excerpt…"}
            />
            <button type="button" disabled={busy || !summaryDraft.trim()} onClick={scoreSummary}>
              Score & continue
            </button>
            {summaryScore ? (
              <div className="studySideMuted">
                Score {Math.round(summaryScore.score * 100)}% — {summaryScore.feedback}
              </div>
            ) : null}
          </>
        ) : null}

        {action === "flashcards" || action === "sample_problem" ? (
          <>
            <button type="button" disabled={busy} onClick={() => runStudyLabAction(activeExcerpt, action)}>
              {busy ? "Generating…" : `Generate ${actionLabel(action)}`}
            </button>
            {artifactView ? (
              <div style={{ maxHeight: 280, overflow: "auto" }}>
                <StudyArtifactView
                  artifactType={String(artifactView._type || action)}
                  content={artifactView}
                />
              </div>
            ) : null}
          </>
        ) : null}

        {action === "quiz" ? (
          <>
            <button type="button" disabled={busy} onClick={() => runStudyLabAction(activeExcerpt, "quiz")}>
              {busy ? "Generating…" : "Generate quiz"}
            </button>
            {artifactView ? (
              <>
                <div style={{ maxHeight: 240, overflow: "auto" }}>
                  <StudyArtifactView artifactType="quiz" content={artifactView} />
                </div>
                <div className="studySideActions">
                  <button type="button" onClick={() => onQuizPass(true)}>
                    I passed
                  </button>
                  <button type="button" onClick={() => onQuizPass(false)}>
                    I failed (restart)
                  </button>
                </div>
                {quizPassed === false ? <div className="studySideMuted">Restarting sequence…</div> : null}
              </>
            ) : null}
          </>
        ) : null}

        {action === "read_aloud" ? (
          <button type="button" onClick={() => readAloudText(activeExcerpt.text)}>
            Read aloud
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="studyFlowShell">
      <div className="studyFlowHeader">
        <div>
          <h1 style={{ margin: 0 }}>StudyFlows</h1>
          <p className="pageIntro" style={{ marginBottom: 0 }}>
            Highlight text to start a per-excerpt StudyFlow sequence.
          </p>
        </div>
        <div className="studySideActions">
          <button type="button" onClick={() => setEditingFlow((v) => !v)}>
            {editingFlow ? "Close flow editor" : "Edit flow"}
          </button>
        </div>
      </div>

      {aiStatus ? (
        <div className={`studyAgentBanner${aiStatus.configured ? " isReady" : " isMissing"}`}>
          {aiStatus.configured
            ? `Cursor agent ready (${aiStatus.model || "auto"}).`
            : aiStatus.message}
        </div>
      ) : null}

      {bookmarkFlash ? <div className="studySavedNote">{bookmarkFlash}</div> : null}

      {savedNote ? (
        <div className="studySavedNote">
          Saved to {savedNote.notebook_title} / {savedNote.document_title}.{" "}
          <Link href={`/notebooks?course_id=${encodeURIComponent(courseId)}`}>Open notebooks</Link>
        </div>
      ) : null}

      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {isLoading ? <LoadingState label="Loading StudyFlow..." /> : null}

      {!isLoading && flow && run ? (
        <ContentState>
          {editingFlow ? (
            <div className="studyResourceBar">
              <div style={{ fontWeight: 600 }}>Flow template</div>
              <div className="studySideMuted">Ordered actions for each new highlight. Quiz can restart the sequence on fail.</div>
              <div style={{ display: "grid", gap: 8 }}>
                {template.steps.map((s, idx) => (
                  <div key={s.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <span>{idx + 1}.</span>
                    <select
                      value={s.action}
                      onChange={(e) => {
                        const steps = template.steps.map((x) =>
                          x.id === s.id ? { ...x, action: e.target.value as StudyFlowAction } : x
                        );
                        saveFlowTemplate({ steps });
                      }}
                    >
                      {ACTION_MENU.map((a) => (
                        <option key={a.key} value={a.key}>
                          {a.label}
                        </option>
                      ))}
                    </select>
                    {s.action === "quiz" ? (
                      <>
                        <label style={{ display: "flex", gap: 4, alignItems: "center", fontSize: 13 }}>
                          <input
                            type="checkbox"
                            checked={!!s.gate}
                            onChange={(e) => {
                              const steps = template.steps.map((x) =>
                                x.id === s.id ? { ...x, gate: e.target.checked } : x
                              );
                              saveFlowTemplate({ steps });
                            }}
                          />
                          Pass gate
                        </label>
                        <select
                          value={s.on_fail || "restart_sequence"}
                          onChange={(e) => {
                            const steps = template.steps.map((x) =>
                              x.id === s.id
                                ? { ...x, on_fail: e.target.value as FlowTemplateStep["on_fail"] }
                                : x
                            );
                            saveFlowTemplate({ steps });
                          }}
                        >
                          <option value="restart_sequence">On fail: restart</option>
                          <option value="retry_step">On fail: retry</option>
                          <option value="continue">On fail: continue</option>
                        </select>
                      </>
                    ) : null}
                    <button
                      type="button"
                      disabled={idx === 0}
                      onClick={() => {
                        if (idx === 0) return;
                        const steps = [...template.steps];
                        [steps[idx - 1], steps[idx]] = [steps[idx], steps[idx - 1]];
                        saveFlowTemplate({ steps });
                      }}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      disabled={idx === template.steps.length - 1}
                      onClick={() => {
                        if (idx >= template.steps.length - 1) return;
                        const steps = [...template.steps];
                        [steps[idx + 1], steps[idx]] = [steps[idx], steps[idx + 1]];
                        saveFlowTemplate({ steps });
                      }}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => saveFlowTemplate({ steps: template.steps.filter((x) => x.id !== s.id) })}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() =>
                  saveFlowTemplate({
                    steps: [
                      ...template.steps,
                      { id: crypto.randomUUID(), action: "comment" },
                    ],
                  })
                }
              >
                Add step
              </button>
            </div>
          ) : null}

          <div className="studyResourceBar">
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>Textbook / reading</span>
                <select
                  value={run.resource_id || ""}
                  disabled={busy}
                  onChange={(e) => e.target.value && attachResource(e.target.value)}
                  style={{ minWidth: 280, padding: 8 }}
                >
                  <option value="">Select a resource…</option>
                  {readableResources.map((r) => (
                    <option key={r.id} value={r.id}>
                      {isPdfResource(r) ? "PDF · " : ""}
                      {r.title}
                      {r.source_type === "canvas_page" && !isPdfResource(r) ? " (page)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              {isPdf && sections.length > 0 ? (
                <label style={{ display: "grid", gap: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Chapter / section</span>
                  <select
                    value={sectionKey}
                    onChange={(e) => onChapterChange(e.target.value)}
                    style={{ minWidth: 280, padding: 8 }}
                  >
                    <option value="">Jump to section…</option>
                    {sections.map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.kind === "chapter" ? "Ch" : "§"} {s.key} {s.title}
                        {s.page_start ? ` (p${s.page_start})` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          </div>

          {run.resource_id ? (
            <div className="studyWorkspace">
              <div className="studyToolbar">
                <div className="studyToolbarGroup">
                  <span className="studyToolbarLabel">Highlight</span>
                  <span className="studyToolbarHint">Select or right-click for actions</span>
                </div>
                <div className="studyToolbarGroup">
                  <button type="button" onClick={() => setScale((s) => Math.max(0.7, Number((s - 0.15).toFixed(2))))}>
                    −
                  </button>
                  <span>Zoom {Math.round(scale * 100)}%</span>
                  <button type="button" onClick={() => setScale((s) => Math.min(2.5, Number((s + 0.15).toFixed(2))))}>
                    +
                  </button>
                </div>
                <div className="studyToolbarGroup">
                  <button type="button" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
                    ‹
                  </button>
                  <span>Page</span>
                  <input
                    className="studyPageInput"
                    value={pageInput}
                    onChange={(e) => setPageInput(e.target.value)}
                    onBlur={() => goToPage(Number(pageInput) || page)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") goToPage(Number(pageInput) || page);
                    }}
                  />
                  <span>/ {pageCount || "—"}</span>
                  <button type="button" disabled={!pageCount || page >= pageCount} onClick={() => goToPage(page + 1)}>
                    ›
                  </button>
                </div>
                {speaking ? (
                  <button type="button" onClick={() => { stopSpeaking(); setSpeaking(false); }}>
                    Stop reading
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    setFindOpen(true);
                    window.setTimeout(() => findInputRef.current?.focus(), 0);
                  }}
                  title="Find in textbook (Ctrl+F)"
                >
                  Find
                </button>
                <button
                  type="button"
                  disabled={busy || !run.resource_id}
                  onClick={() => void savePlaceBookmark()}
                  title="Bookmark this page and resume here next time"
                >
                  Bookmark
                </button>
                <button
                  type="button"
                  className={workspaceView === "notebook" ? "isActive" : ""}
                  onClick={() => setWorkspaceView((v) => (v === "resource" ? "notebook" : "resource"))}
                  title="Switch between the textbook and your study notebook"
                >
                  {workspaceView === "resource" ? "Open notebook" : "Back to resource"}
                </button>
                {bookmark ? (
                  <span className="studyBookmarkChip" title={bookmark.snippet || undefined}>
                    Saved p{bookmark.page}
                    {bookmark.snippet ? ` · “${bookmark.snippet.slice(0, 40)}${bookmark.snippet.length > 40 ? "…" : ""}”` : ""}
                  </span>
                ) : null}
              </div>

              {findOpen ? (
                <div>
                  <form
                    className="studyFindBar"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void runFind(findQuery);
                    }}
                  >
                    <input
                      ref={findInputRef}
                      value={findQuery}
                      onChange={(e) => setFindQuery(e.target.value)}
                      placeholder="Find in this textbook…"
                      aria-label="Find in textbook"
                    />
                    <button type="submit" disabled={findBusy || !findQuery.trim()}>
                      {findBusy ? "…" : "Search"}
                    </button>
                    <button type="button" disabled={!findHits.length} onClick={() => jumpFind(-1)}>
                      Prev
                    </button>
                    <button type="button" disabled={!findHits.length} onClick={() => jumpFind(1)}>
                      Next
                    </button>
                    <span className="studyBookmarkChip">
                      {findHits.length ? `${findIndex + 1}/${findHits.length}` : "Ctrl+F"}
                    </span>
                    <button type="button" onClick={() => setFindOpen(false)}>
                      Close
                    </button>
                  </form>
                  {findHits.length > 0 ? (
                    <div className="studyFindHits">
                      {findHits.map((h, i) => (
                        <button
                          key={h.chunk_id}
                          type="button"
                          className={`studyFindHit${i === findIndex ? " isActive" : ""}`}
                          onClick={() => {
                            setFindIndex(i);
                            if (h.page_number) goToPage(h.page_number);
                          }}
                        >
                          <strong>p{h.page_number ?? "?"}</strong>
                          <span>{h.snippet.slice(0, 160)}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className={`studyWorkspaceBody${workspaceView === "notebook" ? " isNotebookView" : ""}`}>
                {workspaceView === "resource" ? (
                  <div>
                    <div
                      className="studyDocPane"
                      style={hideSource ? { opacity: 0.2, pointerEvents: "none" } : undefined}
                      onContextMenu={(e) => {
                        const sel = window.getSelection()?.toString().trim() || selectedText || activeExcerpt?.text || "";
                        if (!sel) return;
                        e.preventDefault();
                        setSelectedText(sel);
                        setMenu({ x: e.clientX, y: e.clientY, text: sel, mode: "context" });
                      }}
                    >
                      {isPdf && pdfData ? (
                        <PdfReader
                          data={pdfData}
                          page={page}
                          scale={scale}
                          highlightQuery={findOpen ? findQuery : ""}
                          onPageCount={setPageCount}
                          onTextSelect={({ text, x, y, showMenu }) => {
                            setSelectedText(text);
                            if (showMenu) {
                              setMenu({ x, y, text, mode: "select" });
                            }
                          }}
                          onClearSelect={() => {
                            setMenu(null);
                          }}
                        />
                      ) : isPdf && pdfLoadError ? (
                        <div className="studyPdfError">Couldn’t download PDF ({pdfLoadError}).</div>
                      ) : isPdf ? (
                        <div className="studyPdfLoading">Loading PDF…</div>
                      ) : isPlainText && textPreview != null ? (
                        <div className="studyTextDoc">
                          {textPreview.trim().length < 220 ? (
                            <div className="studyPdfError" style={{ marginBottom: 12 }}>
                              This Canvas page is only a filename stub — the embedded PDF isn’t synced yet.
                              Reconnect Canvas on the Dashboard → Sync now, then re-open this reading.
                            </div>
                          ) : null}
                          <pre
                            style={{
                              whiteSpace: "pre-wrap",
                              margin: 0,
                              color: "#f9fafb",
                              fontFamily: "ui-sans-serif, system-ui, sans-serif",
                              fontSize: 15,
                              lineHeight: 1.5,
                            }}
                            onMouseUp={(e) => {
                              const sel = window.getSelection()?.toString().trim() || "";
                              if (!sel) return;
                              setSelectedText(sel);
                              setMenu({ x: e.clientX, y: e.clientY, text: sel, mode: "select" });
                            }}
                          >
                            {textPreview}
                          </pre>
                        </div>
                      ) : (
                        <EmptyState message="Select a PDF textbook / reading above." />
                      )}
                    </div>
                    <div className="studyProgressStrip">{progressSummary}</div>
                  </div>
                ) : (
                  <div className="studyNotebookPane">
                    <StudyNotebook
                      excerpts={excerpts}
                      activeExcerptId={activeExcerptId}
                      paperStyle={paperStyle}
                      onPaperStyleChange={setPaperStyle}
                      onSelectExcerpt={(id) => {
                        setActiveExcerptId(id);
                        const ex = excerpts.find((e) => e.id === id);
                        if (ex) {
                          setSelectedText(ex.text);
                          setCommentDraft(ex.comment || "");
                          goToPage(ex.page);
                        }
                      }}
                      onRecognizeInk={onRecognizeInk}
                      inkDisabled={false}
                      commentDraft={commentDraft}
                      onCommentDraftChange={setCommentDraft}
                      onSaveComment={saveComment}
                      saveBusy={busy}
                    />
                  </div>
                )}

                <aside className="studySidePane">
                  {activeExcerpt ? (
                    <div className="studySideCard">
                      <div className="studySideTitle">Checklist</div>
                      <ol className="studyChecklist">
                        {activeExcerpt.steps.map((s, i) => (
                          <li key={s.id} className={`studyCheckItem is-${s.status}`}>
                            <button
                              type="button"
                              onClick={() => {
                                const next = {
                                  ...activeExcerpt,
                                  cursor_step_index: i,
                                  steps: activeExcerpt.steps.map((x, idx) => ({
                                    ...x,
                                    status:
                                      idx === i
                                        ? ("active" as const)
                                        : x.status === "done"
                                          ? ("done" as const)
                                          : ("pending" as const),
                                  })),
                                };
                                void updateExcerpts(
                                  excerpts.map((e) => (e.id === activeExcerpt.id ? next : e)),
                                  activeExcerpt.id
                                );
                                openActionForExcerpt(next, s.action);
                              }}
                            >
                              {i + 1}. {actionLabel(s.action)}
                              {s.one_time ? " *" : ""} — {s.status}
                            </button>
                          </li>
                        ))}
                      </ol>
                      <button type="button" onClick={() => setCalendarOpen(true)}>
                        Add to calendar
                      </button>
                    </div>
                  ) : null}

                  {renderActionPanel()}
                </aside>
              </div>
            </div>
          ) : (
            <EmptyState message="Choose a textbook PDF above to start reading." />
          )}
        </ContentState>
      ) : null}

      {calendarOpen && activeExcerpt ? (
        <div className="studyModalBackdrop" onClick={() => setCalendarOpen(false)}>
          <div className="studyModal" onClick={(e) => e.stopPropagation()}>
            <div className="studySideTitle">Schedule StudyFlow excerpt</div>
            <label>
              Date (optional)
              <input type="date" value={calendarDate} onChange={(e) => setCalendarDate(e.target.value)} />
            </label>
            <label>
              Time (optional)
              <input type="time" value={calendarTime} onChange={(e) => setCalendarTime(e.target.value)} />
            </label>
            <div className="studySideActions">
              <button type="button" disabled={busy} onClick={scheduleOnCalendar}>
                Save to calendar
              </button>
              <button type="button" onClick={() => setCalendarOpen(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {menu ? (
        <div
          className="studyHighlightMenu"
          style={{
            left: Math.min(menu.x, typeof window !== "undefined" ? window.innerWidth - 240 : menu.x),
            top: Math.min(menu.y, typeof window !== "undefined" ? window.innerHeight - 320 : menu.y),
          }}
          onContextMenu={(e) => e.preventDefault()}
        >
          {menu.mode === "select" ? (
            <button
              type="button"
              onClick={() => {
                createExcerptFromText(menu.text);
                setMenu(null);
              }}
            >
              Start StudyFlow on highlight
            </button>
          ) : null}
          <button type="button" onClick={() => readAloudText(menu.text)}>
            Read aloud
          </button>
          <button type="button" onClick={() => injectOneTimeAction("ask_cursor", menu.text)}>
            Ask Cursor
          </button>
          {ACTION_MENU.filter((a) => !["ask_cursor", "read_aloud"].includes(a.key)).map((a) => (
            <button key={a.key} type="button" onClick={() => injectOneTimeAction(a.key, menu.text)}>
              {a.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => {
              setSelectedText(menu.text);
              void savePlaceBookmark({ snippet: menu.text });
              setMenu(null);
            }}
          >
            Bookmark this place
          </button>
          <button
            type="button"
            onClick={() => {
              if (!activeExcerpt) createExcerptFromText(menu.text);
              setCalendarOpen(true);
              setMenu(null);
            }}
          >
            Add to calendar
          </button>
        </div>
      ) : null}
    </div>
  );
}
