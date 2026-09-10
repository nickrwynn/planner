"use client";

import type { ReactNode } from "react";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
      <div data-testid="loading-state" style={{ color: "var(--fg-muted)" }}>
      {label}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  retryLabel = "Retry",
  retryTestId = "retry-button",
  title = "Request failed",
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  retryTestId?: string;
  title?: string;
}) {
  return (
    <div
      data-testid="error-state"
      style={{
        display: "grid",
        gap: 8,
        border: "1px solid var(--danger)",
        borderRadius: "var(--radius)",
        padding: 10,
        background: "var(--danger-soft)",
      }}
    >
      <div style={{ color: "var(--danger)", fontWeight: 600 }}>{title}</div>
      <div style={{ color: "var(--danger-fg)", whiteSpace: "pre-wrap" }}>{message}</div>
      {onRetry ? (
        <button
          type="button"
          data-testid={retryTestId}
          onClick={onRetry}
          style={{ width: "fit-content", padding: "8px 12px" }}
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div data-testid="empty-state" style={{ display: "grid", gap: 8, color: "var(--fg-muted)" }}>
      <div>{message}</div>
      {action}
    </div>
  );
}

export function ContentState({ children }: { children: ReactNode }) {
  return <div data-testid="content-state">{children}</div>;
}
