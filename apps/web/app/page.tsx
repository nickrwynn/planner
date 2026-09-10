"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/async-state";
import { CanvasConnectPanel } from "../components/canvas-connect-panel";
import { apiGet, toErrorMessage } from "../lib/api";
import { applyTheme, getStoredTheme, THEME_PRESETS, type ThemeId } from "../lib/theme";
import {
  getPreferredVoiceUri,
  getSpeechRate,
  isSpeechSupported,
  listVoices,
  setPreferredVoiceUri,
  setSpeechRate,
  speakText,
  stopSpeaking,
} from "../lib/speech";
import type { Course, Resource, Task } from "../lib/types";

type HealthResponse = {
  status: string;
  postgres?: { ok: boolean };
  redis?: { ok: boolean };
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
  const [courses, setCourses] = useState<Course[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [planner, setPlanner] = useState<PlannerNext>({ task: null, reasons: [] });
  const [upcomingPlan, setUpcomingPlan] = useState<PlannerUpcoming>({ tasks: [] });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [theme, setTheme] = useState<ThemeId>("default");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [voiceUri, setVoiceUri] = useState<string>("");
  const [speechRate, setSpeechRateState] = useState(1);
  const [speechPreviewBusy, setSpeechPreviewBusy] = useState(false);

  useEffect(() => {
    setTheme(getStoredTheme());
    setVoiceUri(getPreferredVoiceUri() || "");
    setSpeechRateState(getSpeechRate());
    void listVoices().then((v) => setVoices(v));
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [nextHealth, nextCourses, nextTasks, nextResources, nextPlanner, nextUpcoming] = await Promise.all([
        apiGet<HealthResponse>("/health"),
        apiGet<Course[]>("/courses"),
        apiGet<Task[]>("/tasks?limit=100&offset=0"),
        apiGet<Resource[]>("/resources?limit=100&offset=0"),
        apiGet<PlannerNext>("/planner/next"),
        apiGet<PlannerUpcoming>("/planner/upcoming?limit=8"),
      ]);
      setHealth(nextHealth);
      setCourses(nextCourses);
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
  const courseName = useMemo(() => {
    const map = new Map(courses.map((c) => [c.id, c.name]));
    return (id: string | null | undefined) => (id ? map.get(id) ?? "Course" : "Course");
  }, [courses]);

  const upcoming = useMemo(() => {
    if (upcomingPlan.tasks.length > 0) return upcomingPlan.tasks;
    return [...openTasks]
      .sort((a, b) => {
        if (!a.due_at && !b.due_at) return 0;
        if (!a.due_at) return 1;
        if (!b.due_at) return -1;
        return Date.parse(a.due_at) - Date.parse(b.due_at);
      })
      .slice(0, 8);
  }, [openTasks, upcomingPlan.tasks]);

  const healthy = health.status === "ok" && health.postgres?.ok && health.redis?.ok;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Dashboard</h1>
        <p className="pageIntro">Management overview — what needs attention, what to do next.</p>
      </div>

      <CanvasConnectPanel />

      <div className="card" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ fontWeight: 600 }}>Style preset</div>
        <select
          aria-label="App style preset"
          value={theme}
          onChange={(e) => {
            const next = e.target.value as ThemeId;
            setTheme(next);
            applyTheme(next);
          }}
          style={{ padding: 8 }}
        >
          {THEME_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div className="card" style={{ display: "grid", gap: 10 }}>
        <div style={{ fontWeight: 600 }}>Read aloud voice</div>
        {!isSpeechSupported() ? (
          <div style={{ fontSize: 13, color: "var(--muted)" }}>
            This browser doesn’t expose speech synthesis. On iPad Safari / the StudyFlows app, voices should appear here.
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select
                aria-label="Read aloud voice"
                value={voiceUri}
                onChange={(e) => {
                  const next = e.target.value;
                  setVoiceUri(next);
                  setPreferredVoiceUri(next || null);
                }}
                style={{ padding: 8, minWidth: 260, maxWidth: "100%" }}
              >
                <option value="">System default (English preferred)</option>
                {voices.map((v) => (
                  <option key={v.voiceURI} value={v.voiceURI}>
                    {v.name} ({v.lang}){v.default ? " · default" : ""}
                  </option>
                ))}
              </select>
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                Speed
                <input
                  type="range"
                  min={0.7}
                  max={1.4}
                  step={0.05}
                  value={speechRate}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setSpeechRateState(next);
                    setSpeechRate(next);
                  }}
                />
                <span>{speechRate.toFixed(2)}×</span>
              </label>
              <button
                type="button"
                style={{ padding: "8px 12px" }}
                disabled={speechPreviewBusy}
                onClick={() => {
                  setSpeechPreviewBusy(true);
                  void speakText(
                    "This is your StudyFlows read aloud voice. You can use it on highlights and StudyFlow steps.",
                    {
                      voiceUri: voiceUri || null,
                      onEnd: () => setSpeechPreviewBusy(false),
                      onError: () => setSpeechPreviewBusy(false),
                    }
                  );
                }}
              >
                {speechPreviewBusy ? "Playing…" : "Preview"}
              </button>
              <button type="button" style={{ padding: "8px 12px" }} onClick={() => stopSpeaking()}>
                Stop
              </button>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              Used by Read aloud in StudyFlows. {voices.length} voice{voices.length === 1 ? "" : "s"} available.
            </div>
          </>
        )}
      </div>

      {isLoading ? <LoadingState label="Loading dashboard..." /> : null}
      {!isLoading && error ? (
        <ErrorState title="Dashboard unavailable" message={error} onRetry={refresh} />
      ) : null}

      {!isLoading && !error ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
            <div className="card">
              <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>System</div>
              <div style={{ fontWeight: 700, fontSize: 20 }}>{healthy ? "Healthy" : "Check stack"}</div>
            </div>
            <Link href="/courses" className="card" style={{ textDecoration: "none", color: "inherit" }}>
              <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>Courses</div>
              <div style={{ fontWeight: 700, fontSize: 20 }}>{courses.length}</div>
            </Link>
            <Link href="/calendar" className="card" style={{ textDecoration: "none", color: "inherit" }}>
              <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>Open tasks</div>
              <div style={{ fontWeight: 700, fontSize: 20 }}>{openTasks.length}</div>
            </Link>
            <div className="card">
              <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>Resources</div>
              <div style={{ fontWeight: 700, fontSize: 20 }}>{resources.length}</div>
            </div>
          </div>

          <div className="card">
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Suggested next</div>
            {planner.task ? (
              <div style={{ display: "grid", gap: 6 }}>
                <div style={{ fontWeight: 700 }}>{planner.task.title}</div>
                <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>
                  {courseName(planner.task.course_id)}
                  {planner.task.due_at ? ` · due ${new Date(planner.task.due_at).toLocaleString()}` : ""}
                </div>
                {planner.reasons.length ? (
                  <div style={{ color: "var(--fg-muted)", fontSize: 12 }}>{planner.reasons.join(" · ")}</div>
                ) : null}
                <Link href={`/courses/${planner.task.course_id}/tasks`} className="mutedLink">
                  Open in course tasks →
                </Link>
              </div>
            ) : (
              <EmptyState message="You're clear — no open tasks right now." />
            )}
          </div>

          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ fontWeight: 600 }}>Coming up</div>
              <Link href="/calendar" className="mutedLink">
                Calendar →
              </Link>
            </div>
            {upcoming.length === 0 ? (
              <EmptyState message="No upcoming work. Add due dates on course tasks." />
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {upcoming.map((t) => (
                  <li key={t.id} style={{ marginBottom: 8 }}>
                    <Link
                      href={`/courses/${t.course_id}/tasks`}
                      style={{ fontWeight: 600, textDecoration: "none", color: "inherit" }}
                    >
                      {t.title}
                    </Link>
                    <div style={{ color: "var(--fg-muted)", fontSize: 12 }}>
                      {courseName(t.course_id)}
                      {t.due_at ? ` · ${new Date(t.due_at).toLocaleString()}` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {failedIndex.length > 0 ? (
            <div className="card" style={{ borderColor: "var(--danger)", background: "var(--danger-soft)" }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Indexing issues ({failedIndex.length})</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {failedIndex.slice(0, 6).map((r) => (
                  <li key={r.id}>
                    <Link href={`/resources/${r.id}`} style={{ fontWeight: 600 }}>
                      {r.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="card" style={{ display: "grid", gap: 8 }}>
            <div style={{ fontWeight: 600 }}>Quick actions</div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link href="/courses" className="mutedLink">
                Manage courses
              </Link>
              <Link href="/calendar" className="mutedLink">
                Plan your week
              </Link>
            </div>
            <div style={{ color: "var(--fg-muted)", fontSize: 12 }}>
              Canvas sync is configured above. Ask lives in the right pane.
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
