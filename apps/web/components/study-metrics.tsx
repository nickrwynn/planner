"use client";

import {
  actionLabel,
  effectiveDifficulty,
  excerptEffort,
  formatDuration,
  stepMetrics,
  type Difficulty,
  type ExcerptStep,
  type StudyExcerpt,
} from "../lib/studyflow-actions";

type StudyMetricsProps = {
  excerpt: StudyExcerpt;
  activeStep: ExcerptStep | null;
  onRateStep: (stepId: string, difficulty: Difficulty) => void;
};

const RATINGS: { key: Difficulty; label: string }[] = [
  { key: "easy", label: "Easy" },
  { key: "medium", label: "Medium" },
  { key: "hard", label: "Hard" },
];

function Meter({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="metricRow">
      <span className="metricLabel">{label}</span>
      {value === null ? (
        <span className="studySideMuted">not measured yet</span>
      ) : (
        <>
          <span className="metricBar">
            <span
              className={`metricFill ${value >= 85 ? "is-high" : value >= 60 ? "is-mid" : "is-low"}`}
              style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
            />
          </span>
          <span className="metricValue">{value}%</span>
        </>
      )}
    </div>
  );
}

/**
 * Effort and understanding for the active excerpt. These are the inputs the
 * calendar planner uses, so everything shown here is measured rather than
 * estimated — except the remaining-time figure, which is explicitly an
 * estimate scaled by this student's own pace.
 */
export function StudyMetrics({ excerpt, activeStep, onRateStep }: StudyMetricsProps) {
  const effort = excerptEffort(excerpt);
  const activeMetrics = activeStep ? stepMetrics(activeStep) : null;
  const activeRating = activeStep ? effectiveDifficulty(activeStep) : null;

  return (
    <div className="studySideCard">
      <div className="studySideTitle">Progress & effort</div>

      <div className="metricRow">
        <span className="metricLabel">Time on this excerpt</span>
        <span className="metricValue">{formatDuration(effort.totalMs)}</span>
      </div>
      <div className="metricRow">
        <span className="metricLabel">Steps done</span>
        <span className="metricValue">
          {effort.doneSteps}/{effort.totalSteps}
        </span>
      </div>
      <div className="metricRow">
        <span className="metricLabel">Est. remaining</span>
        <span className="metricValue">
          {effort.remainingMinutes > 0 ? `${effort.remainingMinutes} min` : "—"}
        </span>
      </div>

      <Meter label="Mastery" value={effort.masteryPct} />
      <Meter label="Comprehension" value={effort.comprehensionPct} />

      <div className="metricRow">
        <span className="metricLabel">Effort mix</span>
        <span className="metricChips">
          <span className="metricChip is-easy">{effort.easy} easy</span>
          <span className="metricChip is-medium">{effort.medium} med</span>
          <span className="metricChip is-hard">{effort.hard} hard</span>
        </span>
      </div>

      {activeStep ? (
        <div className="metricRate">
          <div className="studySideMuted">
            {actionLabel(activeStep.action)} · {formatDuration(activeMetrics?.elapsed_ms ?? 0)}
            {activeRating ? ` · rated ${activeRating}` : ""}
          </div>
          <div className="studyInkModes">
            {RATINGS.map((r) => (
              <button
                key={r.key}
                type="button"
                className={activeRating === r.key ? "isActive" : ""}
                onClick={() => onRateStep(activeStep.id, r.key)}
                title={`Rate this step ${r.label.toLowerCase()}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
