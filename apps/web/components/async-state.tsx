"use client";

import type { ReactNode } from "react";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div data-testid="loading-state" style={{ color: "#555" }}>
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
      style={{ display: "grid", gap: 8, border: "1px solid #fecaca", borderRadius: 8, padding: 10, background: "#fff7f7" }}
    >
      <div style={{ color: "#b91c1c", fontWeight: 600 }}>{title}</div>
      <div style={{ color: "#7f1d1d", whiteSpace: "pre-wrap" }}>{message}</div>
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
    <div data-testid="empty-state" style={{ display: "grid", gap: 8, color: "#555" }}>
      <div>{message}</div>
      {action}
    </div>
  );
}
