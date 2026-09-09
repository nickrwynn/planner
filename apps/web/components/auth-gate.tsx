"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getStoredAccessToken, isBearerAuthMode } from "../lib/auth";

const PUBLIC_PATHS = new Set(["/login"]);

/** When API is in bearer mode, require a stored JWT before showing the app shell. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(!isBearerAuthMode());

  useEffect(() => {
    if (!isBearerAuthMode()) {
      setReady(true);
      return;
    }
    const token = getStoredAccessToken();
    const isPublic = PUBLIC_PATHS.has(pathname || "");
    if (!token && !isPublic) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/")}`);
      setReady(false);
      return;
    }
    if (token && isPublic) {
      router.replace("/");
      setReady(false);
      return;
    }
    setReady(true);
  }, [pathname, router]);

  if (!ready) {
    return <div className="authGateLoading">Checking session…</div>;
  }
  return <>{children}</>;
}
