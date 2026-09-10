"use client";

import {
  actionLabel,
  effectiveDifficulty,
  formatDuration,
  stepMetrics,
  type ExcerptStep,
} from "../lib/studyflow-actions";

type StudyFlowStepperProps = {
  steps: ExcerptStep[];
  activeIndex: number;
  onSelect: (index: number) => void;
  /** Preview mode: the flow is shown but no excerpt exists to run it against. */
  disabled?: boolean;
};

/** Short labels keep the strip readable when a flow has many steps. */
const SHORT_LABELS: Record<string, string> = {
  comment: "Comment",
  ask_cursor: "Ask",
  sample_problem: "Sample",
  summarize: "Summarize",
  flashcards: "Flashcards",
  hide_recall_summarize: "Hide & recall",
  quiz: "Quiz",
  read_aloud: "Read aloud",
};

/**
 * The flow as a horizontal track: completed steps are shaded, the current step
 * is green, and upcoming steps are plain. Each finished step carries its
 * effort rating and the time it took.
 */
export function StudyFlowStepper({ steps, activeIndex, onSelect, disabled }: StudyFlowStepperProps) {
  if (!steps.length) return null;

  return (
    <nav
      className={`flowStepper${disabled ? " is-preview" : ""}`}
      aria-label="Study flow progress"
    >
      <ol className="flowStepperTrack">
        {steps.map((step, index) => {
          const metrics = stepMetrics(step);
          const rating = step.status === "done" ? effectiveDifficulty(step) : null;
          const isActive = index === activeIndex && step.status !== "done";
          const stateClass = isActive
            ? "is-active"
            : step.status === "done"
              ? "is-done"
              : step.status === "failed"
                ? "is-failed"
                : "is-pending";

          const detail = step.status === "done" ? formatDuration(metrics.elapsed_ms) : null;

          return (
            <li key={step.id} className={`flowStep ${stateClass}`}>
              <button
                type="button"
                onClick={() => onSelect(index)}
                disabled={disabled}
                aria-current={isActive ? "step" : undefined}
                title={
                  disabled
                    ? `${actionLabel(step.action)} — highlight a passage to start`
                    : rating
                      ? `${actionLabel(step.action)} — ${rating}, ${formatDuration(metrics.elapsed_ms)}`
                      : actionLabel(step.action)
                }
              >
                <span className="flowStepIndex">{index + 1}</span>
                <span className="flowStepLabel">
                  {SHORT_LABELS[step.action] || actionLabel(step.action)}
                  {step.one_time ? " *" : ""}
                </span>
                {rating ? <span className={`flowStepDot is-${rating}`} aria-label={rating} /> : null}
                {detail ? <span className="flowStepTime">{detail}</span> : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
