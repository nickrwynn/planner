"use client";

import { useCallback, useEffect, useState } from "react";
import { CourseSubnav } from "../../../components/CourseSubnav";
import { ErrorState, LoadingState } from "../../../components/async-state";
import { apiGet, toErrorMessage } from "../../../lib/api";
import type { Course } from "../../../lib/types";

export default function CourseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { id: string };
}) {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    setIsLoading(true);
    try {
      setCourse(await apiGet<Course>(`/courses/${params.id}`));
    } catch (e) {
      setError(toErrorMessage(e));
      setCourse(null);
    } finally {
      setIsLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {isLoading ? <LoadingState label="Loading course..." /> : null}
      {error ? <ErrorState message={error} onRetry={refresh} /> : null}
      {!isLoading && !error ? (
        <CourseSubnav courseId={params.id} courseName={course?.name} />
      ) : null}
      {children}
    </div>
  );
}
