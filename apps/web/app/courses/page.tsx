"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ContentState, EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import type { Course } from "../../lib/types";

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [term, setTerm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(true);

  async function refresh() {
    setError(null);
    setIsLoading(true);
    try {
      const courseRows = await apiGet<Course[]>("/courses");
      setCourses(courseRows);
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const sorted = useMemo(
    () => [...courses].sort((a, b) => a.name.localeCompare(b.name)),
    [courses]
  );

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      await apiPost<Course>("/courses", {
        name: name.trim(),
        code: code.trim() || null,
        term: term.trim() || null,
        source_type: "manual",
      });
      setName("");
      setCode("");
      setTerm("");
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onRename(course: Course) {
    const next = window.prompt("New course name", course.name);
    if (!next?.trim()) return;
    try {
      await apiPatch<Course>(`/courses/${course.id}`, { name: next.trim() });
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  async function onDelete(course: Course) {
    if (!window.confirm(`Delete course "${course.name}"? This removes its tasks, resources, and notebooks.`)) {
      return;
    }
    try {
      await apiDelete<{ ok: boolean }>(`/courses/${course.id}`);
      await refresh();
    } catch (err) {
      setError(toErrorMessage(err));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div>
        <h1 style={{ margin: 0 }}>Courses</h1>
        <p className="pageIntro">
          Add courses manually anytime — including Blackboard / Brightspace classes we don’t sync yet. Connect Canvas on
          the{" "}
          <Link href="/" className="mutedLink">
            Dashboard
          </Link>
          .
        </p>
      </div>

      <div className="card" style={{ display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>Canvas LMS</div>
        <div style={{ fontSize: 13, color: "var(--fg-muted)" }}>
          Sign in, sync courses, and import assignments from the{" "}
          <Link href="/" className="mutedLink">
            Dashboard → Canvas
          </Link>{" "}
          section.
        </div>
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div>
            <div style={{ fontWeight: 700 }}>Add a course manually</div>
            <div style={{ color: "var(--fg-muted)", fontSize: 13, marginTop: 4 }}>
              Use this for any class your school LMS doesn’t support here yet. Upload PDFs on the course Resources
              page.
            </div>
          </div>
          <button type="button" onClick={() => setShowCreate((v) => !v)} style={{ padding: "8px 12px" }}>
            {showCreate ? "Hide" : "Add course"}
          </button>
        </div>
        {showCreate ? (
          <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Course name (e.g. MATH Probability)"
              style={{ padding: 8, minWidth: 240 }}
              required
            />
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Code (optional, e.g. MATH 411)"
              style={{ padding: 8, minWidth: 140 }}
            />
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Term (optional, e.g. Fall 2026)"
              style={{ padding: 8, minWidth: 140 }}
            />
            <button type="submit" style={{ padding: "8px 12px" }} disabled={!name.trim()}>
              Create course
            </button>
          </form>
        ) : null}
      </div>

      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Your courses</div>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </div>

        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
        {isLoading ? <LoadingState label="Loading courses..." /> : null}

        {!isLoading && sorted.length > 0 ? (
          <ContentState>
            <div style={{ display: "grid", gap: 8 }}>
              {sorted.map((c) => (
                <div
                  key={c.id}
                  className="card"
                  style={{ padding: 12, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}
                >
                  <div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <Link
                        href={`/courses/${c.id}`}
                        style={{ textDecoration: "none", color: "inherit", fontWeight: 700, fontSize: 16 }}
                      >
                        {c.name}
                      </Link>
                      {c.source_type === "canvas" ? (
                        <span style={{ fontSize: 11, color: "var(--accent)", border: "1px solid var(--accent)", padding: "1px 6px" }}>
                          Canvas
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, color: "var(--fg-muted)", border: "1px solid var(--border-strong)", padding: "1px 6px" }}>
                          Manual
                        </span>
                      )}
                    </div>
                    <div style={{ color: "var(--fg-muted)", fontSize: 13 }}>
                      {c.code || "No code"} · {c.term || "No term"}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => onRename(c)} style={{ padding: "6px 10px" }}>
                      Rename
                    </button>
                    <button onClick={() => onDelete(c)} style={{ padding: "6px 10px" }}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </ContentState>
        ) : null}

        {!isLoading && !error && sorted.length === 0 ? (
          <EmptyState
            message="No courses yet. Add one locally, or connect Canvas on the Dashboard and sync."
            action={
              <button type="button" onClick={() => setShowCreate(true)} style={{ padding: "8px 12px" }}>
                Add your first course
              </button>
            }
          />
        ) : null}
      </div>
    </div>
  );
}
