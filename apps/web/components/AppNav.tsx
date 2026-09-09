"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { clearAuthSession, getStoredAuthUser, isBearerAuthMode, type AuthUser } from "../lib/auth";

const TABS = [
  { href: "/", label: "Dashboard" },
  { href: "/courses", label: "Courses" },
  { href: "/calendar", label: "Calendar" },
] as const;

type InProgressFlow = {
  course_id: string;
  course_name: string;
  course_code?: string | null;
  run_id: string;
  resource_id?: string | null;
  excerpt_id?: string | null;
  page?: number | null;
  label: string;
  detail: string;
  steps_done: number;
  steps_total: number;
};

function flowHref(item: InProgressFlow): string {
  const params = new URLSearchParams();
  if (item.excerpt_id) params.set("excerpt_id", item.excerpt_id);
  if (item.page != null) params.set("page", String(item.page));
  if (item.resource_id) params.set("resource_id", item.resource_id);
  const qs = params.toString();
  return `/courses/${item.course_id}/study-flows${qs ? `?${qs}` : ""}`;
}

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [flows, setFlows] = useState<InProgressFlow[]>([]);
  const [user, setUser] = useState<AuthUser | null>(null);

  const refreshFlows = useCallback(async () => {
    try {
      const rows = await apiGet<InProgressFlow[]>("/study-flows/in-progress");
      setFlows(rows);
    } catch {
      setFlows([]);
    }
  }, []);

  useEffect(() => {
    const syncUser = () => setUser(isBearerAuthMode() ? getStoredAuthUser() : null);
    syncUser();
    window.addEventListener("aos-auth-changed", syncUser);
    return () => window.removeEventListener("aos-auth-changed", syncUser);
  }, []);

  useEffect(() => {
    void refreshFlows();
    const onFocus = () => void refreshFlows();
    window.addEventListener("focus", onFocus);
    const id = window.setInterval(() => void refreshFlows(), 45000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(id);
    };
  }, [refreshFlows, pathname]);

  function isActive(href: string) {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  function logout() {
    clearAuthSession();
    router.replace("/login");
  }

  return (
    <div className="appNavStack">
      <nav className="topNav" aria-label="Primary">
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            className={`navLink${isActive(tab.href) ? " navLinkActive" : ""}`}
            href={tab.href}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {user ? (
        <div className="sidebarAuth">
          <div className="sidebarAuthEmail" title={user.email}>
            {user.name || user.email}
          </div>
          <button type="button" className="sidebarAuthLogout" onClick={logout}>
            Sign out
          </button>
        </div>
      ) : null}

      <section className="sidebarStudyFlows" aria-label="In-progress StudyFlows">
        <div className="sidebarStudyFlowsHead">StudyFlows</div>
        {flows.length === 0 ? (
          <p className="sidebarStudyFlowsEmpty">No active flows yet. Open a course and start a highlight.</p>
        ) : (
          <ul className="sidebarStudyFlowsList">
            {flows.map((f) => {
              const href = flowHref(f);
              const active = pathname.startsWith(`/courses/${f.course_id}/study-flows`);
              return (
                <li key={`${f.course_id}-${f.excerpt_id || f.run_id}`}>
                  <Link className={`sidebarStudyFlowLink${active ? " isActive" : ""}`} href={href} title={f.label}>
                    <span className="sidebarStudyFlowCourse">
                      {f.course_code || f.course_name}
                    </span>
                    <span className="sidebarStudyFlowLabel">{f.label}</span>
                    <span className="sidebarStudyFlowDetail">{f.detail}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
