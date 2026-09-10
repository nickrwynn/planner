import { expect, test } from "@playwright/test";
import {
  archiveSteps,
  deriveDifficulty,
  effectiveDifficulty,
  excerptEffort,
  formatDuration,
  previewStepsFromTemplate,
  retimeSteps,
  type ExcerptStep,
  type StudyExcerpt,
} from "../lib/studyflow-actions";

/** Pure metrics logic — no browser needed. */

const step = (over: Partial<ExcerptStep> = {}): ExcerptStep => ({
  id: over.id ?? "s1",
  action: over.action ?? "comment",
  status: over.status ?? "pending",
  started_at: over.started_at ?? null,
  metrics: over.metrics ?? { elapsed_ms: 0, attempts: 0 },
  ...over,
});

const excerpt = (steps: ExcerptStep[], history?: StudyExcerpt["history"]): StudyExcerpt => ({
  id: "e1",
  text: "sample",
  page: 1,
  steps,
  cursor_step_index: 0,
  created_at: new Date().toISOString(),
  history,
});

test.describe("difficulty rating", () => {
  test("much slower than expected is hard", () => {
    // comment baseline is 90s; 300s is well over the 1.6x threshold.
    expect(deriveDifficulty("comment", { elapsed_ms: 300_000, attempts: 1 })).toBe("hard");
  });

  test("a retry is hard regardless of speed", () => {
    expect(deriveDifficulty("comment", { elapsed_ms: 10_000, attempts: 2 })).toBe("hard");
  });

  test("a low score is hard even when fast", () => {
    expect(
      deriveDifficulty("quiz", { elapsed_ms: 20_000, attempts: 1, mastery_pct: 0 })
    ).toBe("hard");
  });

  test("fast with a strong score is easy", () => {
    expect(
      deriveDifficulty("comment", { elapsed_ms: 30_000, attempts: 1, comprehension_pct: 92 })
    ).toBe("easy");
  });

  test("fast but mediocre score is not easy", () => {
    expect(
      deriveDifficulty("comment", { elapsed_ms: 30_000, attempts: 1, comprehension_pct: 70 })
    ).toBe("medium");
  });

  test("no evidence yet is medium", () => {
    expect(deriveDifficulty("comment", { elapsed_ms: 0, attempts: 0 })).toBe("medium");
  });

  test("a manual rating beats the derived one", () => {
    const s = step({
      action: "comment",
      // Timing alone would say hard.
      metrics: {
        elapsed_ms: 600_000,
        attempts: 1,
        difficulty: "easy",
        difficulty_source: "manual",
      },
    });
    expect(effectiveDifficulty(s)).toBe("easy");
  });

  test("an unstarted step gets no rating", () => {
    expect(effectiveDifficulty(step())).toBeNull();
  });
});

test.describe("timing", () => {
  test("banks elapsed time when the clock moves on", () => {
    const started = new Date(Date.now() - 5_000).toISOString();
    const steps = [
      step({ id: "a", status: "active", started_at: started }),
      step({ id: "b" }),
    ];
    const next = retimeSteps(steps, 1);
    expect(next[0].started_at).toBeNull();
    expect(next[0].metrics!.elapsed_ms).toBeGreaterThanOrEqual(4_900);
    // The new step's clock is now running.
    expect(next[1].started_at).not.toBeNull();
    expect(next[1].metrics!.attempts).toBe(1);
  });

  test("a step left open overnight is capped, not credited with hours", () => {
    const started = new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString();
    const next = retimeSteps([step({ id: "a", status: "active", started_at: started })], -1);
    // Capped at the 30 minute session ceiling.
    expect(next[0].metrics!.elapsed_ms).toBe(30 * 60 * 1000);
  });

  test("revisiting an in-progress step does not inflate attempts", () => {
    let steps = [step({ id: "a", status: "active", started_at: new Date().toISOString() })];
    steps = retimeSteps(steps, 0);
    steps = retimeSteps(steps, 0);
    steps = retimeSteps(steps, 0);
    expect(steps[0].metrics!.attempts).toBe(1);
  });

  test("re-entering a finished step counts a new attempt", () => {
    const done = step({ id: "a", status: "done", metrics: { elapsed_ms: 1000, attempts: 1 } });
    const next = retimeSteps([done], 0);
    expect(next[0].metrics!.attempts).toBe(2);
  });
});

test.describe("excerpt rollup", () => {
  test("aggregates time, scores and effort mix over done steps", () => {
    const ex = excerpt([
      step({
        id: "a",
        action: "comment",
        status: "done",
        metrics: { elapsed_ms: 30_000, attempts: 1, comprehension_pct: 90 },
      }),
      step({
        id: "b",
        action: "quiz",
        status: "done",
        metrics: { elapsed_ms: 600_000, attempts: 1, mastery_pct: 50 },
      }),
      step({ id: "c", action: "flashcards", status: "pending" }),
    ]);
    const effort = excerptEffort(ex);
    expect(effort.totalMs).toBe(630_000);
    expect(effort.doneSteps).toBe(2);
    expect(effort.totalSteps).toBe(3);
    expect(effort.comprehensionPct).toBe(90);
    expect(effort.masteryPct).toBe(50);
    expect(effort.easy).toBe(1);
    expect(effort.hard).toBe(1);
    expect(effort.remainingMinutes).toBeGreaterThan(0);
  });

  test("history from an earlier pass still counts", () => {
    const ex = excerpt(
      [step({ id: "a", action: "comment", status: "pending" })],
      [
        {
          action: "quiz",
          elapsed_ms: 120_000,
          difficulty: "hard",
          mastery_pct: 0,
          at: new Date().toISOString(),
        },
      ]
    );
    const effort = excerptEffort(ex);
    expect(effort.totalMs).toBe(120_000);
    expect(effort.hard).toBe(1);
    expect(effort.masteryPct).toBe(0);
  });

  test("a failed gate survives being archived for a restart", () => {
    const ex = excerpt([
      step({
        id: "q",
        action: "quiz",
        status: "failed",
        metrics: {
          elapsed_ms: 90_000,
          attempts: 1,
          mastery_pct: 0,
          difficulty: "hard",
          difficulty_source: "auto",
        },
      }),
      step({ id: "z", action: "comment", status: "pending" }),
    ]);
    const archived = archiveSteps(ex);
    expect(archived).toHaveLength(1);
    expect(archived[0]).toMatchObject({ action: "quiz", mastery_pct: 0, difficulty: "hard" });
  });

  test("pace scales the remaining estimate", () => {
    // Took 4x the 90s baseline on the one done step, so remaining should be
    // inflated well past the raw 300s (5 min) baseline for summarize.
    const slow = excerpt([
      step({
        id: "a",
        action: "comment",
        status: "done",
        metrics: { elapsed_ms: 360_000, attempts: 1 },
      }),
      step({ id: "b", action: "summarize", status: "pending" }),
    ]);
    expect(excerptEffort(slow).remainingMinutes).toBeGreaterThan(5);
  });
});

test.describe("flow preview", () => {
  const template = {
    steps: [
      { id: "t1", action: "comment" as const },
      { id: "t2", action: "summarize" as const, gate: true },
      { id: "t3", action: "quiz" as const, on_fail: "restart_sequence" as const },
    ],
  };

  test("template preview starts nothing", () => {
    const steps = previewStepsFromTemplate(template);

    expect(steps.map((s) => s.action)).toEqual(["comment", "summarize", "quiz"]);
    // Nothing is active and no clock is running, so an untouched course page
    // can show the flow without recording time against it.
    expect(steps.every((s) => s.status === "pending")).toBe(true);
    expect(steps.every((s) => s.started_at === null)).toBe(true);
    expect(steps.every((s) => (s.metrics?.attempts ?? 0) === 0)).toBe(true);
    expect(steps.every((s) => (s.metrics?.elapsed_ms ?? 0) === 0)).toBe(true);
  });

  test("preview keeps gate settings so the track matches the real flow", () => {
    const steps = previewStepsFromTemplate(template);
    expect(steps[1].gate).toBe(true);
    expect(steps[2].on_fail).toBe("restart_sequence");
  });

  test("an empty preview excerpt reports an estimate but no measurements", () => {
    const effort = excerptEffort(excerpt(previewStepsFromTemplate(template)));

    expect(effort.doneSteps).toBe(0);
    expect(effort.totalSteps).toBe(3);
    expect(effort.totalMs).toBe(0);
    expect(effort.masteryPct).toBeNull();
    expect(effort.comprehensionPct).toBeNull();
    // The remaining estimate still works, which is what makes the empty card useful.
    expect(effort.remainingMinutes).toBeGreaterThan(0);
  });
});

test.describe("duration formatting", () => {
  test("renders human units", () => {
    expect(formatDuration(0)).toBe("—");
    expect(formatDuration(45_000)).toBe("45s");
    expect(formatDuration(120_000)).toBe("2m");
    expect(formatDuration(150_000)).toBe("2m 30s");
    expect(formatDuration(3_900_000)).toBe("1h 5m");
  });
});
