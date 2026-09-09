"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function CourseSubnav({ courseId, courseName }: { courseId: string; courseName?: string }) {
  const pathname = usePathname();
  const base = `/courses/${courseId}`;
  const onOverview = pathname === base;

  return (
    <div className="courseSubnavWrap">
      <div className="courseSubnavHeader">
        <Link href="/courses" className="mutedLink">
          ← Courses
        </Link>
        {courseName ? (
          onOverview ? (
            <div className="courseSubnavTitle">{courseName}</div>
          ) : (
            <Link href={base} className="courseSubnavTitleLink">
              {courseName}
            </Link>
          )
        ) : null}
      </div>
    </div>
  );
}
