"use client";

import { usePathname } from "next/navigation";
import { AgentDock } from "./agent-dock";
import { AppNav } from "./AppNav";
import { AuthGate } from "./auth-gate";
import { InputModeProvider } from "./pen-keyboard-bridge";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isBare = pathname === "/login" || pathname === "/oauth/done";

  if (isBare) {
    return <AuthGate>{children}</AuthGate>;
  }

  return (
    <AuthGate>
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
    </AuthGate>
  );
}
