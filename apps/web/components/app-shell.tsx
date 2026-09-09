"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import LoginForm from "../app/login/login-form";
import { getStoredAccessToken, isBearerAuthMode } from "../lib/auth";
import { AgentDock } from "./agent-dock";
import { AppNav } from "./AppNav";
import { InputModeProvider } from "./pen-keyboard-bridge";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const path = pathname || "/";
  const bearer = isBearerAuthMode();
  const isOauthDone = path === "/oauth/done";
  // Read the token only after mount; the server can't see localStorage and a
  // mismatched first client render breaks hydration.
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setToken(getStoredAccessToken());
    sync();
    window.addEventListener("aos-auth-changed", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("aos-auth-changed", sync);
      window.removeEventListener("storage", sync);
    };
  }, [path]);

  const needsAuth = bearer && !isOauthDone && !token;

  if (needsAuth) {
    return <LoginForm />;
  }

  if (path === "/login" || isOauthDone) {
    return <>{children}</>;
  }

  return (
    <InputModeProvider>
      <div className="appShell">
        <aside className="sidebar">
          <div className="brandMark">StudyFlows</div>
          <AppNav />
        </aside>
        <div className="mainPane">{children}</div>
        <AgentDock />
      </div>
    </InputModeProvider>
  );
}
