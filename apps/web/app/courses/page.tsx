"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../../components/async-state";
import { apiDelete, apiGet, apiPatch, apiPost, toErrorMessage } from "../../lib/api";
import type { Course } from "../../lib/types";

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [gradingSchema, setGradingSchema] = useState("{\"target_grade\": 90}");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function refresh() {
    setError(null);
    setIsLoading(true);
    try {
      setCourses(await apiGet<Course[]>("/courses"));
    } catch (e) {
      setError(toErrorMessage(e));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      let schemaObj: Record<string, unknown> | null = null;
      try {
        schemaObj = gradingSchema.trim() ? (JSON.parse(gradingSchema) as Record<string, unknown>) : null;
      } catch {
        throw new Error("Invalid grading schema JSON");
      }
      await apiPost<Course>("/courses", { name, code: code || null, grading_schema_json: schemaObj });
      setName("");
      setCode("");
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onRename(course: Course) {
    const next = window.prompt("New course name", course.name);
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch<Course>(`/courses/${course.id}`, { name: next.trim() });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onEditGrading(course: Course) {
    const current = JSON.stringify(course.grading_schema_json ?? {}, null, 2);
    const next = window.prompt("Edit grading schema JSON", current);
    if (next == null) return;
    setError(null);
    try {
      const parsed = next.trim() ? JSON.parse(next) : null;
      await apiPatch<Course>(`/courses/${course.id}`, { grading_schema_json: parsed });
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  async function onDelete(course: Course) {
    if (!window.confirm(`Delete course "${course.name}"? This will delete its tasks/resources/notebooks.`)) return;
    setError(null);
    try {
      await apiDelete<{ ok: boolean }>(`/courses/${course.id}`);
      await refresh();
    } catch (e) {
      setError(toErrorMessage(e));
    }
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <h1 style={{ margin: 0 }}>Courses</h1>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Create course</div>
        <form onSubmit={onCreate} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Course name"
            style={{ padding: 8, minWidth: 240 }}
          />
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Code (optional)"
            style={{ padding: 8, minWidth: 140 }}
          />
          <button type="submit" style={{ padding: "8px 12px" }}>
            Create
          </button>
          <button type="button" onClick={refresh} style={{ padding: "8px 12px" }}>
            Refresh
          </button>
        </form>
        <div style={{ height: 8 }} />
        <textarea
          value={gradingSchema}
          onChange={(e) => setGradingSchema(e.target.value)}
          rows={4}
          style={{ width: "100%", padding: 8, fontFamily: "monospace" }}
          placeholder='{"target_grade": 90, "categories":[{"name":"Exams","weight":0.5}]}'
        />
        {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>All courses</div>
        <div style={{ display: "grid", gap: 8 }}>
          {isLoading ? <LoadingState label="Loading..." /> : null}
          {courses.map((c) => (
            <div key={c.id} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600 }}>
                  <Link href={`/courses/${c.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                    {c.name}
                  </Link>
                </div>
                <div style={{ color: "#555", fontSize: 13 }}>
                  {c.code ? c.code : "—"} • {c.term ?? "—"}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button onClick={() => onRename(c)} style={{ padding: "6px 10px" }}>
                  Rename
                </button>
                <button onClick={() => onEditGrading(c)} style={{ padding: "6px 10px" }}>
                  Grading
                </button>
                <button onClick={() => onDelete(c)} style={{ padding: "6px 10px" }}>
                  Delete
                </button>
                <div style={{ color: "#555", fontSize: 12 }}>{c.id}</div>
              </div>
            </div>
          ))}
          {!isLoading && !error && courses.length === 0 ? <EmptyState message="No courses yet." /> : null}
        </div>
      </div>
    </div>
  );
}

