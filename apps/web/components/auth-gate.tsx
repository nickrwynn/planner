"use client";

/** Pass-through — auth is handled in AppShell so login never hydrates as a blank swap. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
